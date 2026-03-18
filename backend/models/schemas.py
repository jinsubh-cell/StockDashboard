"""
Pydantic response schemas for the Quant API
"""
from pydantic import BaseModel
from typing import Optional


class StockPrice(BaseModel):
    code: str
    name: str
    close: float
    change: float
    change_pct: float
    open: float
    high: float
    low: float
    volume: int
    market_cap: Optional[float] = None
    sector: Optional[str] = None


class StockHistory(BaseModel):
    dates: list[str]
    opens: list[float]
    highs: list[float]
    lows: list[float]
    closes: list[float]
    volumes: list[int]


class MarketIndex(BaseModel):
    name: str
    value: float
    change: float
    change_pct: float


class TechnicalIndicators(BaseModel):
    dates: list[str]
    closes: list[float]
    sma_20: list[Optional[float]]
    sma_60: list[Optional[float]]
    ema_12: list[Optional[float]]
    ema_26: list[Optional[float]]
    rsi_14: list[Optional[float]]
    macd: list[Optional[float]]
    macd_signal: list[Optional[float]]
    macd_hist: list[Optional[float]]
    bb_upper: list[Optional[float]]
    bb_middle: list[Optional[float]]
    bb_lower: list[Optional[float]]
    obv: list[Optional[float]]
    atr: list[Optional[float]]


class TradeSignal(BaseModel):
    indicator: str
    signal: str  # 'buy', 'sell', 'neutral'
    value: float
    description: str


class SignalSummary(BaseModel):
    code: str
    name: str
    overall_signal: str
    buy_count: int
    sell_count: int
    neutral_count: int
    signals: list[TradeSignal]


class BacktestRequest(BaseModel):
    code: str
    strategy: str  # 'golden_cross', 'rsi', 'macd', 'bollinger'
    start_date: str  # 'YYYY-MM-DD'
    end_date: str
    initial_capital: float = 10_000_000
    commission: float = 0.00015
    tax: float = 0.0023
    # Strategy-specific params
    short_window: int = 5
    long_window: int = 20
    rsi_oversold: int = 30
    rsi_overbought: int = 70


class TradeRecord(BaseModel):
    date: str
    action: str
    price: float
    shares: int
    value: float
    pnl: Optional[float] = None


class BacktestResult(BaseModel):
    strategy: str
    code: str
    name: str
    period: str
    initial_capital: float
    final_value: float
    total_return: float
    cagr: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    total_trades: int
    equity_curve: list[float]
    equity_dates: list[str]
    benchmark_curve: list[float]
    trades: list[TradeRecord]


class FactorScore(BaseModel):
    code: str
    name: str
    momentum_score: float
    value_score: float
    quality_score: float
    volatility_score: float
    total_score: float
    rank: int
    price: float
    change_pct: float


class FactorRanking(BaseModel):
    factors_used: list[str]
    weights: dict[str, float]
    rankings: list[FactorScore]
