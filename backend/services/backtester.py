"""
Backtesting Engine using Backtrader + QuantStats
Industry-standard event-driven backtesting with professional performance analytics
"""
import backtrader as bt
import quantstats as qs
import numpy as np
import pandas as pd
import logging
from io import StringIO
from datetime import datetime

logger = logging.getLogger(__name__)


# ============================================================
# Backtrader Strategies
# ============================================================

class GoldenCrossStrategy(bt.Strategy):
    params = (("short_window", 5), ("long_window", 20),
              ("commission", 0.00015), ("tax", 0.0023))

    def __init__(self):
        self.sma_short = bt.indicators.SMA(self.data.close, period=self.p.short_window)
        self.sma_long = bt.indicators.SMA(self.data.close, period=self.p.long_window)
        self.crossover = bt.indicators.CrossOver(self.sma_short, self.sma_long)
        self.order = None

    def next(self):
        if self.order:
            return
        if not self.position:
            if self.crossover > 0:
                self.order = self.buy()
        else:
            if self.crossover < 0:
                self.order = self.sell()

    def notify_order(self, order):
        if order.status in [order.Completed, order.Canceled, order.Margin, order.Rejected]:
            self.order = None


class RSIStrategy(bt.Strategy):
    params = (("rsi_period", 14), ("rsi_oversold", 30), ("rsi_overbought", 70),
              ("commission", 0.00015), ("tax", 0.0023))

    def __init__(self):
        self.rsi = bt.indicators.RSI(self.data.close, period=self.p.rsi_period)
        self.order = None

    def next(self):
        if self.order:
            return
        if not self.position:
            if self.rsi < self.p.rsi_oversold:
                self.order = self.buy()
        else:
            if self.rsi > self.p.rsi_overbought:
                self.order = self.sell()

    def notify_order(self, order):
        if order.status in [order.Completed, order.Canceled, order.Margin, order.Rejected]:
            self.order = None


class MACDStrategy(bt.Strategy):
    params = (("fast", 12), ("slow", 26), ("signal", 9),
              ("commission", 0.00015), ("tax", 0.0023))

    def __init__(self):
        self.macd = bt.indicators.MACD(
            self.data.close,
            period_me1=self.p.fast,
            period_me2=self.p.slow,
            period_signal=self.p.signal,
        )
        self.crossover = bt.indicators.CrossOver(self.macd.macd, self.macd.signal)
        self.order = None

    def next(self):
        if self.order:
            return
        if not self.position:
            if self.crossover > 0:
                self.order = self.buy()
        else:
            if self.crossover < 0:
                self.order = self.sell()

    def notify_order(self, order):
        if order.status in [order.Completed, order.Canceled, order.Margin, order.Rejected]:
            self.order = None


class BollingerStrategy(bt.Strategy):
    params = (("period", 20), ("devfactor", 2.0),
              ("commission", 0.00015), ("tax", 0.0023))

    def __init__(self):
        self.bb = bt.indicators.BollingerBands(
            self.data.close, period=self.p.period, devfactor=self.p.devfactor
        )
        self.order = None

    def next(self):
        if self.order:
            return
        if not self.position:
            if self.data.close[0] < self.bb.lines.bot[0]:
                self.order = self.buy()
        else:
            if self.data.close[0] > self.bb.lines.top[0]:
                self.order = self.sell()

    def notify_order(self, order):
        if order.status in [order.Completed, order.Canceled, order.Margin, order.Rejected]:
            self.order = None


# Trade recorder analyzer
class TradeRecorder(bt.Analyzer):
    """Records all trade details for display"""

    def __init__(self):
        self.trades = []
        self.current_trade = None

    def notify_trade(self, trade):
        if trade.isopen:
            self.current_trade = {
                "date": self.strategy.data.datetime.date(0).strftime("%Y-%m-%d"),
                "action": "매수",
                "price": round(trade.price, 0),
                "shares": abs(trade.size),
                "value": round(abs(trade.price * trade.size), 0),
                "pnl": None,
            }
            self.trades.append(self.current_trade)
        elif trade.isclosed:
            self.trades.append({
                "date": self.strategy.data.datetime.date(0).strftime("%Y-%m-%d"),
                "action": "매도",
                "price": round(trade.price, 0),
                "shares": abs(trade.size),
                "value": round(abs(trade.price * trade.size), 0),
                "pnl": round(trade.pnl, 0),
            })

    def get_analysis(self):
        return {"trades": self.trades}


# ============================================================
# Main backtest runner
# ============================================================

STRATEGY_MAP = {
    "golden_cross": GoldenCrossStrategy,
    "rsi": RSIStrategy,
    "macd": MACDStrategy,
    "bollinger": BollingerStrategy,
}

STRATEGY_NAMES = {
    "golden_cross": "골든크로스",
    "rsi": "RSI 과매수/과매도",
    "macd": "MACD 크로스오버",
    "bollinger": "볼린저밴드",
}


def run_backtest(
    df: pd.DataFrame,
    strategy: str,
    initial_capital: float = 10_000_000,
    commission: float = 0.00015,
    tax: float = 0.0023,
    short_window: int = 5,
    long_window: int = 20,
    rsi_oversold: int = 30,
    rsi_overbought: int = 70,
) -> dict:
    """
    Run backtest using Backtrader engine with QuantStats metrics.

    Strategies: golden_cross, rsi, macd, bollinger
    """
    if strategy not in STRATEGY_MAP:
        return {"error": f"알 수 없는 전략: {strategy}"}

    if df.empty or len(df) < max(long_window, 60):
        return {"error": "데이터가 부족합니다. 최소 60일 이상의 데이터가 필요합니다."}

    try:
        # Prepare data for Backtrader
        bt_df = df[["Date", "Open", "High", "Low", "Close", "Volume"]].copy()
        bt_df["Date"] = pd.to_datetime(bt_df["Date"])
        bt_df.set_index("Date", inplace=True)
        bt_df = bt_df.sort_index()

        # Setup Cerebro engine
        cerebro = bt.Cerebro()
        cerebro.broker.setcash(initial_capital)
        cerebro.broker.setcommission(commission=commission + tax)

        # Add data feed
        data_feed = bt.feeds.PandasData(dataname=bt_df)
        cerebro.adddata(data_feed)

        # Add strategy with parameters
        strategy_cls = STRATEGY_MAP[strategy]
        kwargs = {"commission": commission, "tax": tax}
        if strategy == "golden_cross":
            kwargs.update({"short_window": short_window, "long_window": long_window})
        elif strategy == "rsi":
            kwargs.update({"rsi_oversold": rsi_oversold, "rsi_overbought": rsi_overbought})
        cerebro.addstrategy(strategy_cls, **kwargs)

        # Add analyzers
        cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                           timeframe=bt.TimeFrame.Days, riskfreerate=0.035)
        cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
        cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
        cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="tradeanalyzer")
        cerebro.addanalyzer(TradeRecorder, _name="traderecorder")
        cerebro.addanalyzer(bt.analyzers.TimeReturn, _name="timereturn")

        # Size: all-in per trade
        cerebro.addsizer(bt.sizers.AllInSizer, percents=95)

        # Run
        results = cerebro.run()
        strat = results[0]

        # Extract analyzers
        sharpe_data = strat.analyzers.sharpe.get_analysis()
        dd_data = strat.analyzers.drawdown.get_analysis()
        returns_data = strat.analyzers.returns.get_analysis()
        trade_data = strat.analyzers.tradeanalyzer.get_analysis()
        trade_records = strat.analyzers.traderecorder.get_analysis()
        time_returns = strat.analyzers.timereturn.get_analysis()

        final_value = cerebro.broker.getvalue()
        total_return = (final_value - initial_capital) / initial_capital * 100

        # Sharpe ratio
        sharpe_ratio = sharpe_data.get("sharperatio", 0) or 0

        # Max drawdown
        max_drawdown = dd_data.get("max", {}).get("drawdown", 0) or 0

        # CAGR
        trading_days = len(bt_df)
        years = trading_days / 252
        cagr = ((final_value / initial_capital) ** (1 / max(years, 0.01)) - 1) * 100 if initial_capital > 0 else 0

        # Win rate from trade analyzer
        total_closed = trade_data.get("total", {}).get("closed", 0) or 0
        won = trade_data.get("won", {}).get("total", 0) or 0
        win_rate = (won / total_closed * 100) if total_closed > 0 else 0

        # Build equity curve using QuantStats-compatible returns
        equity_dates = list(bt_df.index.strftime("%Y-%m-%d"))

        # Build equity curve from time returns
        equity_curve = [initial_capital]
        for date in bt_df.index:
            ret = time_returns.get(date, 0) or 0
            equity_curve.append(equity_curve[-1] * (1 + ret))
        equity_curve = equity_curve[1:]  # Remove initial seed

        # Benchmark: buy-and-hold
        closes = bt_df["Close"].values
        if closes[0] > 0:
            benchmark_shares = int(initial_capital / closes[0])
            remaining_cash = initial_capital - benchmark_shares * closes[0]
            benchmark_curve = [float(benchmark_shares * c + remaining_cash) for c in closes]
        else:
            benchmark_curve = [initial_capital] * len(closes)

        # QuantStats enhanced metrics
        qs_metrics = _compute_quantstats_metrics(time_returns, bt_df.index)

        result = {
            "strategy": STRATEGY_NAMES.get(strategy, strategy),
            "initial_capital": initial_capital,
            "final_value": round(final_value, 0),
            "total_return": round(total_return, 2),
            "cagr": round(cagr, 2),
            "sharpe_ratio": round(float(sharpe_ratio), 3),
            "max_drawdown": round(max_drawdown, 2),
            "win_rate": round(win_rate, 1),
            "total_trades": total_closed * 2,  # buy + sell
            "equity_curve": [round(e, 0) for e in equity_curve],
            "equity_dates": equity_dates,
            "benchmark_curve": [round(b, 0) for b in benchmark_curve],
            "trades": trade_records.get("trades", []),
            # QuantStats enhanced metrics
            "sortino_ratio": qs_metrics.get("sortino_ratio", 0),
            "calmar_ratio": qs_metrics.get("calmar_ratio", 0),
            "profit_factor": qs_metrics.get("profit_factor", 0),
            "avg_win": qs_metrics.get("avg_win", 0),
            "avg_loss": qs_metrics.get("avg_loss", 0),
            "volatility": qs_metrics.get("volatility", 0),
        }

        return result

    except Exception as e:
        logger.error(f"Backtrader backtest failed: {e}", exc_info=True)
        # Fallback to simple vectorized backtest
        return _fallback_backtest(df, strategy, initial_capital, commission, tax,
                                 short_window, long_window, rsi_oversold, rsi_overbought)


def _compute_quantstats_metrics(time_returns: dict, index: pd.DatetimeIndex) -> dict:
    """Compute enhanced metrics using QuantStats"""
    try:
        # Convert time_returns dict to pandas Series
        returns_series = pd.Series(
            {date: time_returns.get(date, 0) or 0 for date in index},
            dtype=float
        )
        returns_series.index = pd.to_datetime(returns_series.index)

        if returns_series.empty or returns_series.std() == 0:
            return {}

        sortino = float(qs.stats.sortino(returns_series) or 0)
        calmar = float(qs.stats.calmar(returns_series) or 0)
        vol = float(qs.stats.volatility(returns_series) or 0)
        profit_factor = float(qs.stats.profit_factor(returns_series) or 0)
        avg_win = float(qs.stats.avg_win(returns_series) or 0) * 100
        avg_loss = float(qs.stats.avg_loss(returns_series) or 0) * 100

        return {
            "sortino_ratio": round(sortino, 3) if not np.isnan(sortino) and not np.isinf(sortino) else 0,
            "calmar_ratio": round(calmar, 3) if not np.isnan(calmar) and not np.isinf(calmar) else 0,
            "profit_factor": round(profit_factor, 3) if not np.isnan(profit_factor) and not np.isinf(profit_factor) else 0,
            "avg_win": round(avg_win, 2) if not np.isnan(avg_win) else 0,
            "avg_loss": round(avg_loss, 2) if not np.isnan(avg_loss) else 0,
            "volatility": round(vol * 100, 2) if not np.isnan(vol) else 0,
        }
    except Exception as e:
        logger.warning(f"QuantStats metrics failed: {e}")
        return {}


def _fallback_backtest(
    df, strategy, initial_capital, commission, tax,
    short_window, long_window, rsi_oversold, rsi_overbought,
) -> dict:
    """Fallback vectorized backtest if Backtrader fails"""
    import talib

    closes = df["Close"].values.astype(float)
    dates = df["Date"].dt.strftime("%Y-%m-%d").tolist() if "Date" in df.columns else [str(i) for i in range(len(closes))]

    # Generate signals
    signals = np.zeros(len(closes))

    if strategy == "golden_cross":
        sma_s = talib.SMA(closes, timeperiod=short_window)
        sma_l = talib.SMA(closes, timeperiod=long_window)
        for i in range(1, len(closes)):
            if not np.isnan(sma_s[i]) and not np.isnan(sma_l[i]):
                if sma_s[i] > sma_l[i] and sma_s[i-1] <= sma_l[i-1]:
                    signals[i] = 1
                elif sma_s[i] < sma_l[i] and sma_s[i-1] >= sma_l[i-1]:
                    signals[i] = -1
    elif strategy == "rsi":
        rsi = talib.RSI(closes, timeperiod=14)
        for i in range(1, len(closes)):
            if not np.isnan(rsi[i]) and not np.isnan(rsi[i-1]):
                if rsi[i-1] < rsi_oversold and rsi[i] >= rsi_oversold:
                    signals[i] = 1
                elif rsi[i-1] > rsi_overbought and rsi[i] <= rsi_overbought:
                    signals[i] = -1
    elif strategy == "macd":
        macd, signal, _ = talib.MACD(closes, fastperiod=12, slowperiod=26, signalperiod=9)
        for i in range(1, len(closes)):
            if not np.isnan(macd[i]) and not np.isnan(signal[i]):
                if macd[i] > signal[i] and macd[i-1] <= signal[i-1]:
                    signals[i] = 1
                elif macd[i] < signal[i] and macd[i-1] >= signal[i-1]:
                    signals[i] = -1
    elif strategy == "bollinger":
        upper, _, lower = talib.BBANDS(closes, timeperiod=20, nbdevup=2, nbdevdn=2)
        for i in range(1, len(closes)):
            if not np.isnan(lower[i]) and not np.isnan(upper[i]):
                if closes[i] <= lower[i] and closes[i-1] > lower[i-1]:
                    signals[i] = 1
                elif closes[i] >= upper[i] and closes[i-1] < upper[i-1]:
                    signals[i] = -1

    # Simulate
    cash = initial_capital
    shares = 0
    equity_curve = []
    trades = []
    position = False

    for i in range(len(closes)):
        price = closes[i]
        if signals[i] == 1 and not position:
            max_shares = int(cash / (price * (1 + commission)))
            if max_shares > 0:
                cost = max_shares * price * (1 + commission)
                cash -= cost
                shares = max_shares
                position = True
                trades.append({"date": dates[i], "action": "매수", "price": float(price),
                               "shares": max_shares, "value": round(cost, 0), "pnl": None})
        elif signals[i] == -1 and position:
            revenue = shares * price * (1 - commission - tax)
            buy_cost = trades[-1]["value"] if trades else 0
            pnl = revenue - buy_cost
            cash += revenue
            trades.append({"date": dates[i], "action": "매도", "price": float(price),
                           "shares": shares, "value": round(revenue, 0), "pnl": round(pnl, 0)})
            shares = 0
            position = False

        equity_curve.append(float(cash + shares * price))

    final_value = equity_curve[-1] if equity_curve else initial_capital
    total_return = (final_value - initial_capital) / initial_capital * 100
    trading_days = len(closes)
    years = trading_days / 252
    cagr = ((final_value / initial_capital) ** (1 / max(years, 0.01)) - 1) * 100

    equity_arr = np.array(equity_curve)
    daily_returns = np.diff(equity_arr) / equity_arr[:-1] if len(equity_arr) > 1 else np.array([0])
    sharpe = (np.mean(daily_returns) / max(np.std(daily_returns), 1e-10)) * np.sqrt(252) if len(daily_returns) > 0 else 0

    peak = np.maximum.accumulate(equity_arr)
    drawdown = (peak - equity_arr) / np.where(peak > 0, peak, 1)
    max_dd = float(np.max(drawdown)) * 100

    wins = [t for t in trades if t["action"] == "매도" and t.get("pnl") and t["pnl"] > 0]
    losses = [t for t in trades if t["action"] == "매도" and t.get("pnl") and t["pnl"] <= 0]
    total_closed = len(wins) + len(losses)
    win_rate = (len(wins) / total_closed * 100) if total_closed > 0 else 0

    if closes[0] > 0:
        bm_shares = int(initial_capital / closes[0])
        benchmark_curve = [float(bm_shares * c + (initial_capital - bm_shares * closes[0])) for c in closes]
    else:
        benchmark_curve = [initial_capital] * len(closes)

    return {
        "strategy": STRATEGY_NAMES.get(strategy, strategy),
        "initial_capital": initial_capital,
        "final_value": round(final_value, 0),
        "total_return": round(total_return, 2),
        "cagr": round(cagr, 2),
        "sharpe_ratio": round(float(sharpe), 3),
        "max_drawdown": round(max_dd, 2),
        "win_rate": round(win_rate, 1),
        "total_trades": len(trades),
        "equity_curve": [round(e, 0) for e in equity_curve],
        "equity_dates": dates,
        "benchmark_curve": [round(b, 0) for b in benchmark_curve],
        "trades": trades,
        "sortino_ratio": 0,
        "calmar_ratio": 0,
        "profit_factor": 0,
        "avg_win": 0,
        "avg_loss": 0,
        "volatility": 0,
    }
