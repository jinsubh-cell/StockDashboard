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


# ─── Trading (주문) ───

class OrderRequest(BaseModel):
    code: str                          # 종목코드
    order_type: str                    # "buy" | "sell"
    quantity: int                      # 주문수량
    price: int = 0                     # 주문가격 (0이면 시장가)
    price_type: str = "limit"          # "limit"(지정가) | "market"(시장가)


class OrderModifyRequest(BaseModel):
    org_order_no: str                  # 원주문번호
    code: str                          # 종목코드
    quantity: int                      # 정정수량
    price: int                         # 정정가격


class OrderCancelRequest(BaseModel):
    org_order_no: str                  # 원주문번호
    code: str                          # 종목코드
    quantity: int                      # 취소수량


class OrderResponse(BaseModel):
    success: bool
    order_no: Optional[str] = None
    message: str


class BalanceItem(BaseModel):
    code: str
    name: str
    quantity: int                      # 보유수량
    avg_price: float                   # 평균매입가
    current_price: float               # 현재가
    eval_amount: float                 # 평가금액
    pnl: float                         # 손익금액
    pnl_pct: float                     # 손익률(%)


class AccountBalance(BaseModel):
    total_eval: float                  # 총평가금액
    total_purchase: float              # 총매입금액
    total_pnl: float                   # 총손익
    total_pnl_pct: float               # 총손익률
    cash: float                        # 예수금
    holdings: list[BalanceItem]


class OrderHistoryItem(BaseModel):
    order_no: str
    code: str
    name: str
    order_type: str                    # "buy" | "sell"
    quantity: int
    price: int
    filled_quantity: int               # 체결수량
    filled_price: float                # 체결가격
    status: str                        # "filled" | "pending" | "cancelled" | "partial"
    order_time: str
