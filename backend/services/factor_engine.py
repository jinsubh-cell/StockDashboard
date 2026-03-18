"""
Factor Analysis Engine
Multi-factor quant model using TA-Lib indicators and QuantStats metrics
Implements Fama-French inspired factor scoring for Korean equities
"""
import numpy as np
import pandas as pd
import talib
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def compute_factor_scores(
    stocks_data: list[dict],
    weights: Optional[dict] = None,
) -> list[dict]:
    """
    Compute multi-factor scores for a list of stocks.

    Factors (enhanced):
    - Momentum: Multi-period momentum with decay (1M, 3M, 6M weighted)
    - Value: Market cap efficiency (inverse of market_cap/price)
    - Quality: Risk-adjusted return quality (Sharpe-like + volume stability)
    - Volatility: Downside risk (semi-deviation based, not symmetric)
    """
    if not stocks_data:
        return []

    if weights is None:
        weights = {
            "momentum": 0.30,
            "value": 0.25,
            "quality": 0.25,
            "volatility": 0.20,
        }

    # Normalize weights
    total_w = sum(weights.values())
    weights = {k: v / total_w for k, v in weights.items()}

    results = []
    for stock in stocks_data:
        try:
            scores = _compute_single_stock_factors(stock)
            if scores:
                results.append({**stock, **scores})
        except Exception as e:
            logger.error(f"Error computing factors for {stock.get('code')}: {e}")

    if not results:
        return []

    # Normalize each factor to 0-100 scale (min-max)
    factor_keys = ["momentum_raw", "value_raw", "quality_raw", "volatility_raw"]
    for key in factor_keys:
        values = [r.get(key, 0) for r in results]
        min_v, max_v = min(values), max(values)
        range_v = max_v - min_v if max_v != min_v else 1
        score_key = key.replace("_raw", "_score")
        for r in results:
            r[score_key] = round(((r.get(key, 0) - min_v) / range_v) * 100, 1)

    # Compute total score
    for r in results:
        total = (
            r.get("momentum_score", 0) * weights.get("momentum", 0.25) +
            r.get("value_score", 0) * weights.get("value", 0.25) +
            r.get("quality_score", 0) * weights.get("quality", 0.25) +
            r.get("volatility_score", 0) * weights.get("volatility", 0.25)
        )
        r["total_score"] = round(total, 1)

    # Rank
    results.sort(key=lambda x: x["total_score"], reverse=True)
    for i, r in enumerate(results):
        r["rank"] = i + 1

    return results


def _compute_single_stock_factors(stock: dict) -> dict:
    """Compute raw factor values for a single stock using TA-Lib"""
    history = stock.get("history", [])

    if not history or len(history) < 20:
        # Minimal data: use basic metrics
        change_pct = stock.get("change_pct", 0)
        volume = stock.get("volume", 0)
        market_cap = stock.get("market_cap", 0)
        close = stock.get("close", 0)

        return {
            "momentum_raw": change_pct,
            "value_raw": _safe_inverse(market_cap / max(close, 1)) if close > 0 else 0,
            "quality_raw": np.log1p(volume) if volume > 0 else 0,
            "volatility_raw": 50,
        }

    closes = np.array(history, dtype=float)

    # ===== Momentum Factor (Multi-period weighted) =====
    # Weight recent momentum more heavily: 1M(50%) + 3M(30%) + 6M(20%)
    n = len(closes)
    m1 = min(21, n - 1)   # ~1 month
    m3 = min(63, n - 1)   # ~3 months
    m6 = min(126, n - 1)  # ~6 months

    ret_1m = (closes[-1] / closes[-m1] - 1) * 100 if closes[-m1] > 0 else 0
    ret_3m = (closes[-1] / closes[-m3] - 1) * 100 if closes[-m3] > 0 else 0
    ret_6m = (closes[-1] / closes[-m6] - 1) * 100 if n > m6 and closes[-m6] > 0 else ret_3m

    # Multi-period momentum with recency bias
    momentum = ret_1m * 0.5 + ret_3m * 0.3 + ret_6m * 0.2

    # ===== Value Factor =====
    market_cap = stock.get("market_cap", 0)
    close = stock.get("close", 1)
    value = _safe_inverse(market_cap / max(close, 1)) * 1e6 if close > 0 else 0

    # ===== Quality Factor (Risk-adjusted returns + trend strength) =====
    daily_returns = np.diff(closes) / closes[:-1]

    # Sharpe-like: mean return / std
    mean_ret = np.mean(daily_returns)
    std_ret = np.std(daily_returns)
    sharpe_like = (mean_ret / max(std_ret, 1e-10)) * np.sqrt(252)

    # ADX proxy via TA-Lib for trend quality (needs H/L/C)
    # Since we only have closes, use RSI stability as quality proxy
    rsi = talib.RSI(closes, timeperiod=14)
    valid_rsi = rsi[~np.isnan(rsi)]
    rsi_stability = 100 - np.std(valid_rsi) if len(valid_rsi) > 0 else 50

    # Combine: higher Sharpe-like + stable RSI = higher quality
    quality = sharpe_like * 10 + rsi_stability * 0.5

    # ===== Volatility Factor (Downside semi-deviation based) =====
    # Only penalize negative returns (downside risk)
    neg_returns = daily_returns[daily_returns < 0]
    if len(neg_returns) > 0:
        downside_vol = np.std(neg_returns) * np.sqrt(252) * 100
    else:
        downside_vol = 0
    volatility_score = 100 - min(downside_vol, 100)

    return {
        "momentum_raw": round(momentum, 2),
        "value_raw": round(value, 6),
        "quality_raw": round(quality, 2),
        "volatility_raw": round(volatility_score, 2),
    }


def _safe_inverse(x: float) -> float:
    """Safely compute 1/x"""
    if x == 0 or np.isnan(x) or np.isinf(x):
        return 0
    return 1.0 / x
