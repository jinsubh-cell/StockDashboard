"""
Market Data API Router
Endpoints for stock prices, indices, and search
"""
from fastapi import APIRouter, Query, BackgroundTasks
from services.data_collector import (
    get_market_indices,
    get_top_stocks,
    get_stock_ohlcv,
    get_stock_info,
    search_stocks,
)
from services.market_provider import market_provider
from services.kiwoom_provider import kiwoom
from services.kiwoom_ws import kiwoom_ws_manager
from pykrx import stock as krx
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/market", tags=["Market"])


@router.get("/indices")
def get_indices():
    """Get major market indices (KOSPI, KOSDAQ, etc.)"""
    try:
        indices = get_market_indices()
        return {"indices": indices}
    except Exception as e:
        logger.error(f"Error in get_indices: {e}")
        return {"indices": [], "error": str(e)}


@router.get("/stocks")
def get_stocks(
    count: int = Query(30, ge=1, le=100),
    market: str = Query("ALL")
):
    """Get top stocks by market cap (KOSPI, KOSDAQ, or ALL)"""
    try:
        stocks = get_top_stocks(count, market=market)
        return {"stocks": stocks, "count": len(stocks)}
    except Exception as e:
        logger.error(f"Error in get_stocks: {e}")
        return {"stocks": [], "error": str(e)}


@router.get("/stock/{code}")
async def get_stock_detail(code: str, background_tasks: BackgroundTasks):
    """Get detailed stock information - fast path via Naver, no PyKrx blocking"""
    try:
        import asyncio
        loop = asyncio.get_event_loop()

        # 1. Get name from cached stock list (instant, no network call)
        name = _get_stock_name(code)

        # 2. Real-time price from WS cache (instant) or Naver (async ~1s)
        real_time = kiwoom_ws_manager.realtime_data.get(code)
        if not real_time:
            real_time = await loop.run_in_executor(None, market_provider.get_current_price, code)

        if real_time and real_time.get("price"):
            close = real_time["price"]
            change = real_time["change"]
            change_pct = real_time["change_pct"]
            volume = real_time["volume"]
            open_price = real_time.get("open", 0)
            high_price = real_time.get("high", 0)
            low_price = real_time.get("low", 0)
            # Estimate prev_close from price and change
            prev_close = close - change if change else close
        else:
            # Fallback: FDR OHLCV (slower, ~2s)
            df = get_stock_ohlcv(code, days=5)
            if df.empty:
                return {"error": f"종목 {code}의 데이터를 찾을 수 없습니다."}
            last = df.iloc[-1]
            prev = df.iloc[-2] if len(df) >= 2 else last
            close = float(last["Close"])
            open_price = float(last.get("Open", 0))
            high_price = float(last.get("High", 0))
            low_price = float(last.get("Low", 0))
            prev_close = float(prev["Close"])
            change = close - prev_close
            change_pct = (change / prev_close * 100) if prev_close > 0 else 0
            volume = int(last.get("Volume", 0))

        # 3. Use cached stock info if available, fetch in background if not
        from services.data_collector import _get_cached
        cached_info = _get_cached(f"info_{code}")
        info = cached_info or {}

        # Fetch detailed info in background (non-blocking)
        if not cached_info:
            background_tasks.add_task(_background_fetch_info, code)

        result_data = {
            "code": code,
            "name": name,
            "close": close,
            "open": round(open_price, 0),
            "high": round(high_price, 0),
            "low": round(low_price, 0),
            "volume": volume,
            "change": round(change, 0),
            "change_pct": round(change_pct, 2),
            "prev_close": round(prev_close, 0),
            "market_cap": info.get("market_cap"),
            "foreign_rate": info.get("foreign_rate"),
            "shares": info.get("shares"),
        }

        # Subscribe to websocket for future real-time updates
        background_tasks.add_task(
            kiwoom_ws_manager.subscribe_stocks,
            [code],
            append=True
        )

        return result_data
    except Exception as e:
        logger.error(f"Error in get_stock_detail: {e}")
        return {"error": str(e)}


def _get_stock_name(code: str) -> str:
    """Get stock name from cached stock list (no network call)"""
    try:
        from services.data_collector import get_krx_stock_list, _get_cached
        stock_list = _get_cached("stock_list")
        if stock_list is not None and not stock_list.empty:
            match = stock_list[stock_list["Code"] == code]
            if not match.empty:
                return match.iloc[0]["Name"]
        # Check pre-defined top stocks
        from services.data_collector import _TOP_STOCKS_LIST
        for c, n, _ in _TOP_STOCKS_LIST:
            if c == code:
                return n
    except Exception:
        pass
    return code


def _background_fetch_info(code: str):
    """Fetch stock info in background and cache it"""
    try:
        get_stock_info(code)
    except Exception as e:
        logger.warning(f"Background info fetch for {code}: {e}")


@router.get("/stock/{code}/history")
async def get_stock_history(
    code: str,
    days: int = Query(90, ge=5, le=730)
):
    """Get OHLCV history for a stock"""
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        df = await loop.run_in_executor(None, get_stock_ohlcv, code, days)
        if df.empty:
            return {"error": f"종목 {code}의 데이터를 찾을 수 없습니다."}

        result = {
            "code": code,
            "dates": df["Date"].dt.strftime("%Y-%m-%d").tolist() if "Date" in df.columns else [],
            "opens": df["Open"].tolist(),
            "highs": df["High"].tolist(),
            "lows": df["Low"].tolist(),
            "closes": df["Close"].tolist(),
            "volumes": df["Volume"].tolist(),
        }
        return result
    except Exception as e:
        logger.error(f"Error in get_stock_history: {e}")
        return {"error": str(e)}


@router.get("/search")
async def search_stocks_api(q: str = Query(..., min_length=1)):
    """Search stocks by name or code"""
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, search_stocks, q)
        return {"results": results}
    except Exception as e:
        logger.error(f"Error in search: {e}")
        return {"results": [], "error": str(e)}
