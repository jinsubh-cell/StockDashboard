"""
Technical Analysis API Router
"""
from fastapi import APIRouter, Query
from services.data_collector import get_stock_ohlcv, _get_cached, _set_cached
from services.technical import compute_indicators, generate_signals
import numpy as np
import pandas as pd
import asyncio
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/analysis", tags=["Technical Analysis"])


def _get_stock_name_cached(code: str) -> str:
    """Get stock name from cached stock list (no network call)"""
    try:
        from services.data_collector import _TOP_STOCKS_LIST
        for c, n, _ in _TOP_STOCKS_LIST:
            if c == code:
                return n
        stock_list = _get_cached("stock_list")
        if stock_list is not None and not stock_list.empty:
            match = stock_list[stock_list["Code"] == code]
            if not match.empty:
                return match.iloc[0]["Name"]
    except Exception:
        pass
    return code


def _build_indicators_result(code: str, df: pd.DataFrame) -> dict:
    """Build indicators response dict from computed DataFrame"""
    def safe_list(series):
        if isinstance(series, pd.Series):
            arr = series.values
        else:
            arr = np.array(series, dtype=float)
        if len(arr) == 0:
            return []
        rounded = np.round(arr, 2)
        mask = np.isnan(rounded)
        return [None if mask[i] else float(rounded[i]) for i in range(len(rounded))]

    return {
        "code": code,
        "dates": df["Date"].dt.strftime("%Y-%m-%d").tolist() if "Date" in df.columns else [],
        "opens": df["Open"].tolist(),
        "highs": df["High"].tolist(),
        "lows": df["Low"].tolist(),
        "closes": df["Close"].tolist(),
        "volumes": df["Volume"].tolist(),
        "sma_5": safe_list(df.get("SMA_5", pd.Series())),
        "sma_20": safe_list(df.get("SMA_20", pd.Series())),
        "sma_60": safe_list(df.get("SMA_60", pd.Series())),
        "sma_120": safe_list(df.get("SMA_120", pd.Series())),
        "sma_224": safe_list(df.get("SMA_224", pd.Series())),
        "sma_448": safe_list(df.get("SMA_448", pd.Series())),
        "ema_12": safe_list(df.get("EMA_12", pd.Series())),
        "ema_26": safe_list(df.get("EMA_26", pd.Series())),
        "ichimoku_span_a": safe_list(df.get("ISA_9", pd.Series())),
        "ichimoku_span_b": safe_list(df.get("ISB_26", pd.Series())),
        "ichimoku_tenkan": safe_list(df.get("ITS_9", pd.Series())),
        "ichimoku_kijun": safe_list(df.get("IKS_26", pd.Series())),
        "rsi_14": safe_list(df.get("RSI_14", pd.Series())),
        "macd": safe_list(df.get("MACD_12_26_9", pd.Series())),
        "macd_signal": safe_list(df.get("MACDs_12_26_9", pd.Series())),
        "macd_hist": safe_list(df.get("MACDh_12_26_9", pd.Series())),
        "bb_upper": safe_list(df.get("BBU_20_2.0", pd.Series())),
        "bb_middle": safe_list(df.get("BBM_20_2.0", pd.Series())),
        "bb_lower": safe_list(df.get("BBL_20_2.0", pd.Series())),
        "obv": safe_list(df.get("OBV", pd.Series())),
        "atr": safe_list(df.get("ATR_14", pd.Series())),
        "stoch_k": safe_list(df.get("STOCHk_14_3_3", pd.Series())),
        "stoch_d": safe_list(df.get("STOCHd_14_3_3", pd.Series())),
        "cci": safe_list(df.get("CCI_20", pd.Series())),
        "willr": safe_list(df.get("WILLR_14", pd.Series())),
        "adx": safe_list(df.get("ADX_14", pd.Series())),
        "plus_di": safe_list(df.get("PLUS_DI_14", pd.Series())),
        "minus_di": safe_list(df.get("MINUS_DI_14", pd.Series())),
        "mfi": safe_list(df.get("MFI_14", pd.Series())),
        "vwap": safe_list(df.get("VWAP", pd.Series())),
        "sar": safe_list(df.get("SAR", pd.Series())),
    }


def _build_signals_result(code: str, df: pd.DataFrame) -> dict:
    """Build signals response dict from computed DataFrame"""
    signals = generate_signals(df)
    name = _get_stock_name_cached(code)

    buy_count = sum(1 for s in signals if s["signal"] == "buy")
    sell_count = sum(1 for s in signals if s["signal"] == "sell")
    neutral_count = sum(1 for s in signals if s["signal"] == "neutral")

    if buy_count > sell_count + neutral_count:
        overall = "buy"
    elif sell_count > buy_count + neutral_count:
        overall = "sell"
    else:
        overall = "neutral"

    return {
        "code": code,
        "name": name,
        "overall_signal": overall,
        "buy_count": buy_count,
        "sell_count": sell_count,
        "neutral_count": neutral_count,
        "signals": signals,
    }


def _fetch_and_compute(code: str, days: int):
    """Fetch OHLCV + compute indicators (single pass, cached)"""
    cache_key = f"ta_computed_{code}_{days}"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    df = get_stock_ohlcv(code, days=days)
    if df.empty:
        return df

    df = compute_indicators(df)
    _set_cached(cache_key, df, ttl=120)  # Cache computed indicators 2 min
    return df


@router.get("/{code}/all")
async def get_all_analysis(
    code: str,
    days: int = Query(180, ge=30, le=730)
):
    """Combined endpoint: indicators + signals in a single request (fastest)"""
    try:
        loop = asyncio.get_event_loop()
        df = await loop.run_in_executor(None, _fetch_and_compute, code, days)
        if df is None or (isinstance(df, pd.DataFrame) and df.empty):
            return {"error": f"종목 {code}의 데이터를 찾을 수 없습니다."}

        indicators = _build_indicators_result(code, df)
        signals = _build_signals_result(code, df)
        return {"indicators": indicators, "signals": signals}
    except Exception as e:
        logger.error(f"Error in get_all_analysis: {e}")
        return {"error": str(e)}


@router.get("/{code}")
async def get_technical_indicators(
    code: str,
    days: int = Query(180, ge=30, le=730)
):
    """Get all technical indicators for a stock"""
    try:
        loop = asyncio.get_event_loop()
        df = await loop.run_in_executor(None, _fetch_and_compute, code, days)
        if df is None or (isinstance(df, pd.DataFrame) and df.empty):
            return {"error": f"종목 {code}의 데이터를 찾을 수 없습니다."}

        return _build_indicators_result(code, df)
    except Exception as e:
        logger.error(f"Error in get_technical_indicators: {e}")
        return {"error": str(e)}


@router.get("/{code}/signal")
async def get_trade_signals(code: str):
    """Get composite trade signals for a stock"""
    try:
        loop = asyncio.get_event_loop()
        df = await loop.run_in_executor(None, _fetch_and_compute, code, 180)
        if df is None or (isinstance(df, pd.DataFrame) and df.empty):
            return {"error": f"종목 {code}의 데이터를 찾을 수 없습니다."}

        return _build_signals_result(code, df)
    except Exception as e:
        logger.error(f"Error in get_trade_signals: {e}")
        return {"error": str(e)}
