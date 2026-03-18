"""
Stock Screener Router
- Custom condition scan (자체 조건검색): OHLCV + TA-Lib
- Kiwoom HTS condition search (키움 조건검색): ka10171/172/173/174 via WebSocket
"""
from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import Optional
import asyncio
import logging
import numpy as np
import pandas as pd

from services.data_collector import (
    get_stock_ohlcv, _get_cached, _set_cached,
    _TOP_STOCKS_LIST, get_krx_stock_list
)
from services.technical import compute_indicators
from services.kiwoom_ws import kiwoom_ws_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/screener", tags=["Screener"])

# ─── Pydantic Models ────────────────────────────────────────────────────────────

class Condition(BaseModel):
    type: str               # sma_cross | sma_alignment | rsi | macd_cross
                            # bollinger | volume_spike | price_vs_sma
    direction: Optional[str] = None   # up | down | above | below
                                       # touch_lower | touch_upper
    fast: Optional[int] = None        # SMA cross: fast period
    slow: Optional[int] = None        # SMA cross: slow period
    period: Optional[int] = None      # price_vs_sma: SMA period
    operator: Optional[str] = None    # lt | gt | lte | gte
    value: Optional[float] = None     # RSI threshold value
    multiplier: Optional[float] = None  # volume_spike multiplier


class ScanRequest(BaseModel):
    conditions: list[Condition]
    logic: str = "AND"          # AND | OR
    scan_count: int = 50        # how many stocks to scan (max 100)


class KiwoomSearchRequest(BaseModel):
    seq: str                    # Condition sequence number from ka10171
    search_type: str = "0"      # 0: one-time, 1: realtime


# ─── Condition Evaluator ───────────────────────────────────────────────────────

def _safe(val):
    """Return None if val is NaN/None, else float."""
    if val is None:
        return None
    try:
        f = float(val)
        return None if np.isnan(f) else f
    except Exception:
        return None


def evaluate_conditions(code: str, df: pd.DataFrame,
                        conditions: list[Condition], logic: str) -> dict:
    """Evaluate all conditions on the last row of an indicator DataFrame.
    Returns a dict with match, indicator_snapshot, and triggered conditions.
    """
    if df is None or df.empty or len(df) < 2:
        return {"match": False, "snapshot": {}, "triggered": []}

    last = df.iloc[-1]
    prev = df.iloc[-2]
    results = []
    triggered = []

    for cond in conditions:
        try:
            match = False
            label = ""

            if cond.type == "sma_cross":
                fk = f"SMA_{cond.fast}"
                sk = f"SMA_{cond.slow}"
                cf, cs = _safe(last.get(fk)), _safe(last.get(sk))
                pf, ps = _safe(prev.get(fk)), _safe(prev.get(sk))
                if all(v is not None for v in [cf, cs, pf, ps]):
                    if cond.direction == "up":
                        match = pf <= ps and cf > cs
                        label = f"SMA{cond.fast} 골든크로스 (SMA{cond.slow} 상향돌파)"
                    else:
                        match = pf >= ps and cf < cs
                        label = f"SMA{cond.fast} 데드크로스 (SMA{cond.slow} 하향돌파)"

            elif cond.type == "sma_alignment":
                vals = [_safe(last.get(f"SMA_{p}")) for p in [5, 20, 60, 120]]
                if all(v is not None for v in vals):
                    match = all(vals[i] > vals[i+1] for i in range(3))
                    label = "이동평균 정배열 (5>20>60>120)"

            elif cond.type == "rsi":
                rsi = _safe(last.get("RSI_14"))
                if rsi is not None:
                    op, val = cond.operator, cond.value
                    if op == "lt":   match = rsi < val
                    elif op == "gt": match = rsi > val
                    elif op == "lte": match = rsi <= val
                    elif op == "gte": match = rsi >= val
                    ops = {"lt": "<", "gt": ">", "lte": "≤", "gte": "≥"}
                    label = f"RSI(14) {ops.get(op,op)} {val} (현재 {rsi:.1f})"

            elif cond.type == "macd_cross":
                m  = _safe(last.get("MACD_12_26_9"))
                s  = _safe(last.get("MACDs_12_26_9"))
                pm = _safe(prev.get("MACD_12_26_9"))
                ps = _safe(prev.get("MACDs_12_26_9"))
                if all(v is not None for v in [m, s, pm, ps]):
                    if cond.direction == "up":
                        match = pm <= ps and m > s
                        label = "MACD 골든크로스"
                    else:
                        match = pm >= ps and m < s
                        label = "MACD 데드크로스"

            elif cond.type == "bollinger":
                price = _safe(last.get("Close"))
                upper = _safe(last.get("BBU_20_2.0"))
                lower = _safe(last.get("BBL_20_2.0"))
                if price is not None:
                    if cond.direction == "touch_lower" and lower is not None:
                        match = price <= lower
                        label = f"볼린저 하단밴드 터치 (현재 {price:,.0f} ≤ {lower:,.0f})"
                    elif cond.direction == "touch_upper" and upper is not None:
                        match = price >= upper
                        label = f"볼린저 상단밴드 돌파 (현재 {price:,.0f} ≥ {upper:,.0f})"
                    elif cond.direction == "squeeze":
                        if upper is not None and lower is not None:
                            width = (upper - lower) / _safe(last.get("BBM_20_2.0") or 1) * 100
                            match = width < 5.0
                            label = f"볼린저밴드 수축 (폭 {width:.1f}%)"

            elif cond.type == "volume_spike":
                vols = df["Volume"].values.astype(float)
                if len(vols) >= 21:
                    avg = np.mean(vols[-21:-1])
                    cur = vols[-1]
                    mult = cond.multiplier or 2.0
                    if avg > 0:
                        match = cur >= mult * avg
                        label = f"거래량 급증 ({cur/avg:.1f}배, 기준 {mult}배)"

            elif cond.type == "price_vs_sma":
                price = _safe(last.get("Close"))
                sma   = _safe(last.get(f"SMA_{cond.period}"))
                if price is not None and sma is not None:
                    if cond.direction == "above":
                        match = price > sma
                        label = f"현재가 > SMA{cond.period} ({price:,.0f} > {sma:,.0f})"
                    else:
                        match = price < sma
                        label = f"현재가 < SMA{cond.period} ({price:,.0f} < {sma:,.0f})"

            elif cond.type == "adx_trend":
                adx = _safe(last.get("ADX_14"))
                if adx is not None:
                    match = adx > (cond.value or 25)
                    label = f"강한 추세 (ADX {adx:.1f} > {cond.value or 25})"

            results.append(match)
            if match:
                triggered.append(label)

        except Exception as e:
            logger.debug(f"Condition eval error [{code}]: {e}")
            results.append(False)

    if not results:
        return {"match": False, "snapshot": {}, "triggered": []}

    overall = any(results) if logic == "OR" else all(results)

    # Build snapshot of key indicator values
    snapshot = {}
    for key, col in [("rsi", "RSI_14"), ("macd", "MACD_12_26_9"),
                     ("sma5", "SMA_5"), ("sma20", "SMA_20"),
                     ("sma60", "SMA_60"), ("sma120", "SMA_120"),
                     ("close", "Close"), ("volume", "Volume")]:
        v = _safe(last.get(col))
        if v is not None:
            snapshot[key] = round(v, 2) if key not in ("close", "volume", "sma5",
                                                        "sma20", "sma60", "sma120") \
                             else round(v)

    return {"match": overall, "snapshot": snapshot, "triggered": triggered}


# ─── Scan a Single Stock ───────────────────────────────────────────────────────

async def _scan_one(loop, sem, code: str, name: str,
                    conditions: list[Condition], logic: str) -> Optional[dict]:
    async with sem:
        try:
            df = await loop.run_in_executor(None, get_stock_ohlcv, code, 180)
            if df is None or df.empty:
                return None
            df = await loop.run_in_executor(None, compute_indicators, df)
            result = evaluate_conditions(code, df, conditions, logic)
            if result["match"]:
                price  = int(df.iloc[-1].get("Close", 0))
                volume = int(df.iloc[-1].get("Volume", 0))
                return {
                    "code": code,
                    "name": name,
                    "price": price,
                    "volume": volume,
                    "snapshot": result["snapshot"],
                    "triggered": result["triggered"],
                }
        except Exception as e:
            logger.debug(f"Scan failed for {code}: {e}")
        return None


# ─── Routes ────────────────────────────────────────────────────────────────────

@router.post("/scan")
async def scan_stocks(req: ScanRequest):
    """Custom condition scan — scans top stocks using our own OHLCV + TA-Lib."""
    if not req.conditions:
        return {"error": "조건을 최소 1개 이상 입력하세요."}

    # Candidate stock list (top stocks from cache or fallback list)
    n = min(req.scan_count, 100)
    cache_key = "screener_stock_candidates"
    candidates = _get_cached(cache_key)
    if candidates is None:
        try:
            df = get_krx_stock_list()
            if df is not None and not df.empty:
                candidates = [
                    (str(row["Code"]).zfill(6), str(row["Name"]))
                    for _, row in df.head(200).iterrows()
                ]
            else:
                candidates = [(c, n) for c, n, _ in _TOP_STOCKS_LIST]
        except Exception:
            candidates = [(c, nm) for c, nm, _ in _TOP_STOCKS_LIST]
        _set_cached(cache_key, candidates, ttl=300)

    targets = candidates[:n]

    # Parallel scan with concurrency limit
    loop = asyncio.get_event_loop()
    sem  = asyncio.Semaphore(8)
    tasks = [_scan_one(loop, sem, code, name, req.conditions, req.logic)
             for code, name in targets]
    raw = await asyncio.gather(*tasks)

    matched = [r for r in raw if r is not None]
    matched.sort(key=lambda x: x.get("volume", 0), reverse=True)

    return {
        "count": len(matched),
        "scanned": len(targets),
        "logic": req.logic,
        "results": matched,
    }


@router.get("/kiwoom/conditions")
async def get_kiwoom_conditions():
    """Return Kiwoom HTS condition list (ka10171 via WebSocket)."""
    if not kiwoom_ws_manager.connected:
        return {"error": "키움 WebSocket 미연결 — 백엔드 시작 시 자동 연결됩니다.", "conditions": []}

    try:
        result = await asyncio.wait_for(
            kiwoom_ws_manager.request_condition_list(), timeout=5.0
        )
        return {"conditions": result}
    except asyncio.TimeoutError:
        return {"error": "키움 조건검색 목록 응답 시간 초과", "conditions": []}
    except Exception as e:
        return {"error": str(e), "conditions": []}


@router.post("/kiwoom/search")
async def kiwoom_condition_search(req: KiwoomSearchRequest):
    """Execute Kiwoom HTS condition search (ka10172 one-time / ka10173 realtime)."""
    if not kiwoom_ws_manager.connected:
        return {"error": "키움 WebSocket 미연결", "results": []}

    try:
        result = await asyncio.wait_for(
            kiwoom_ws_manager.request_condition_search(
                seq=req.seq, search_type=req.search_type
            ),
            timeout=10.0,
        )
        return {"results": result, "count": len(result)}
    except asyncio.TimeoutError:
        return {"error": "키움 조건검색 응답 시간 초과", "results": []}
    except Exception as e:
        return {"error": str(e), "results": []}


@router.delete("/kiwoom/realtime/{seq}")
async def stop_kiwoom_realtime(seq: str):
    """Stop real-time Kiwoom condition monitoring (ka10174)."""
    if not kiwoom_ws_manager.connected:
        return {"ok": False, "error": "WebSocket 미연결"}
    await kiwoom_ws_manager.stop_realtime_condition(seq)
    return {"ok": True}


@router.get("/kiwoom/realtime/results")
async def get_realtime_results():
    """Return currently cached real-time condition search results."""
    return {"results": dict(kiwoom_ws_manager.condition_realtime_results)}
