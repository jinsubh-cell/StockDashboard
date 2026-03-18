"""
Backtest API Router
"""
from fastapi import APIRouter
from models.schemas import BacktestRequest
from services.data_collector import get_stock_ohlcv
from services.backtester import run_backtest
from pykrx import stock as krx
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/backtest", tags=["Backtesting"])


@router.post("/run")
def execute_backtest(req: BacktestRequest):
    """Run a backtest with the specified strategy and parameters"""
    try:
        # Calculate days needed from date range
        from datetime import datetime
        start = datetime.strptime(req.start_date, "%Y-%m-%d")
        end = datetime.strptime(req.end_date, "%Y-%m-%d")
        days = (end - start).days + 30  # Extra buffer

        df = get_stock_ohlcv(req.code, days=days)
        if df.empty:
            return {"error": f"종목 {req.code}의 데이터를 찾을 수 없습니다."}

        # Filter by date range
        if "Date" in df.columns:
            df = df[(df["Date"] >= req.start_date) & (df["Date"] <= req.end_date)]

        if len(df) < 30:
            return {"error": "기간 내 데이터가 부족합니다. 최소 30일 이상의 데이터가 필요합니다."}

        name = ""
        try:
            name = krx.get_market_ticker_name(req.code) or req.code
        except Exception:
            name = req.code

        result = run_backtest(
            df=df,
            strategy=req.strategy,
            initial_capital=req.initial_capital,
            commission=req.commission,
            tax=req.tax,
            short_window=req.short_window,
            long_window=req.long_window,
            rsi_oversold=req.rsi_oversold,
            rsi_overbought=req.rsi_overbought,
        )

        if "error" in result:
            return result

        result["code"] = req.code
        result["name"] = name
        result["period"] = f"{req.start_date} ~ {req.end_date}"

        strategy_names = {
            "golden_cross": "골든크로스",
            "rsi": "RSI 과매수/과매도",
            "macd": "MACD 크로스오버",
            "bollinger": "볼린저밴드",
        }
        result["strategy"] = strategy_names.get(req.strategy, req.strategy)

        return result
    except Exception as e:
        logger.error(f"Error in execute_backtest: {e}")
        return {"error": str(e)}
