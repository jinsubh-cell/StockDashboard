"""
Scalping Stock Picker - 초단타 종목 선정 엔진

스캘핑에 적합한 종목을 실시간 데이터 기반으로 선별합니다.

Selection Criteria:
1. 거래량 활성도 (Volume Activity) - 당일 거래량이 충분히 높은 종목
2. 변동성 (Intraday Volatility) - 당일 고-저 변동폭이 적절한 종목
3. 호가 스프레드 (Spread) - 매수-매도 호가 차이가 좁은 종목
4. 틱 빈도 (Tick Frequency) - 체결이 빈번하게 발생하는 종목
5. 가격대 적합성 (Price Range) - 스캘핑에 적합한 가격대 종목
6. 모멘텀 강도 (Short-term Momentum) - 단기 추세가 형성된 종목
"""
import logging
import time
import numpy as np
from datetime import datetime
from typing import Optional
from collections import deque

logger = logging.getLogger(__name__)


# ─── Scoring Weights ───

DEFAULT_WEIGHTS = {
    "volume": 0.25,         # 거래량 활성도
    "volatility": 0.20,     # 변동성
    "spread": 0.15,         # 호가 스프레드 (낮을수록 좋음)
    "tick_freq": 0.15,      # 틱 빈도
    "price_fit": 0.10,      # 가격대 적합성
    "momentum": 0.15,       # 모멘텀 강도
}


# ─── Config ───

class PickerConfig:
    def __init__(self):
        # Volume criteria
        self.min_volume: int = 500_000          # 최소 거래량 (50만주)
        self.volume_rank_top: int = 50           # 거래량 상위 N개 대상

        # Volatility criteria
        self.min_volatility_pct: float = 0.5     # 최소 변동률 0.5%
        self.max_volatility_pct: float = 5.0     # 최대 변동률 5% (너무 급변하면 위험)
        self.ideal_volatility_pct: float = 1.5   # 이상적 변동률

        # Price range
        self.min_price: int = 1_000              # 최소 가격 (1천원)
        self.max_price: int = 500_000            # 최대 가격 (50만원)
        self.ideal_price_low: int = 5_000        # 이상적 가격대 하한
        self.ideal_price_high: int = 100_000     # 이상적 가격대 상한

        # Spread
        self.max_spread_pct: float = 0.3         # 최대 스프레드 0.3%

        # Tick frequency
        self.min_ticks_per_minute: float = 5     # 분당 최소 체결 수

        # Momentum
        self.momentum_window: int = 20           # 최근 N틱 기반 모멘텀

        # Output
        self.top_n: int = 10                     # 상위 N개 추천
        self.weights: dict = DEFAULT_WEIGHTS.copy()

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items()}

    @classmethod
    def from_dict(cls, d: dict):
        config = cls()
        for k, v in d.items():
            if k == "weights":
                config.weights = v
            elif hasattr(config, k):
                expected_type = type(getattr(config, k))
                setattr(config, k, expected_type(v))
        return config


# ─── Individual Scoring Functions ───

def score_volume(volume: int, avg_volume: float, config: PickerConfig) -> float:
    """
    거래량 점수: 당일 거래량이 높을수록 높은 점수.
    평균 대비 비율도 고려 (거래량 급증 = 높은 점수)
    """
    if volume < config.min_volume:
        return 0.0

    # Base score: log-scaled volume (거래량이 높을수록 점수 상승, log로 극단값 방지)
    base = min(np.log10(max(volume, 1)) / np.log10(50_000_000), 1.0)  # 5천만주 기준 정규화

    # Bonus: average volume ratio
    if avg_volume > 0:
        ratio = volume / avg_volume
        ratio_bonus = min(ratio / 3.0, 0.3)  # 3배 이상이면 최대 보너스
    else:
        ratio_bonus = 0

    return min(base + ratio_bonus, 1.0)


def score_volatility(high: float, low: float, close: float, config: PickerConfig) -> float:
    """
    변동성 점수: 고저 대비 변동폭이 이상적 범위에 가까울수록 높은 점수.
    너무 낮으면(횡보) 0, 너무 높으면(급변) 낮은 점수.
    """
    if close <= 0 or high <= 0 or low <= 0:
        return 0.0

    volatility_pct = (high - low) / close * 100

    if volatility_pct < config.min_volatility_pct:
        return 0.0
    if volatility_pct > config.max_volatility_pct:
        return max(0, 0.5 - (volatility_pct - config.max_volatility_pct) * 0.1)

    # Bell curve around ideal volatility
    ideal = config.ideal_volatility_pct
    diff = abs(volatility_pct - ideal)
    return max(0, 1.0 - (diff / ideal) ** 2)


def score_spread(bid: int, ask: int, price: int, config: PickerConfig) -> float:
    """
    스프레드 점수: 매수-매도 호가 차이가 좁을수록 높은 점수.
    """
    if price <= 0 or bid <= 0 or ask <= 0:
        return 0.5  # 데이터 없으면 중립

    spread = ask - bid
    spread_pct = spread / price * 100

    if spread_pct > config.max_spread_pct:
        return max(0, 0.3 - (spread_pct - config.max_spread_pct) * 0.5)

    # 스프레드가 좁을수록 1에 가까움
    return max(0, 1.0 - spread_pct / config.max_spread_pct)


def score_tick_frequency(tick_count: int, duration_seconds: float, config: PickerConfig) -> float:
    """
    틱 빈도 점수: 분당 체결 횟수가 높을수록 높은 점수.
    """
    if duration_seconds <= 0 or tick_count <= 0:
        return 0.0

    ticks_per_minute = tick_count / (duration_seconds / 60.0)

    if ticks_per_minute < config.min_ticks_per_minute:
        return ticks_per_minute / config.min_ticks_per_minute * 0.5

    # 분당 30틱 이상이면 만점
    return min(ticks_per_minute / 30.0, 1.0)


def score_price_fitness(price: int, config: PickerConfig) -> float:
    """
    가격대 적합성: 이상적 가격대에 가까울수록 높은 점수.
    """
    if price < config.min_price or price > config.max_price:
        return 0.0

    if config.ideal_price_low <= price <= config.ideal_price_high:
        return 1.0

    # 이상적 범위 밖이면 거리에 따라 감점
    if price < config.ideal_price_low:
        return max(0.3, price / config.ideal_price_low)
    else:
        return max(0.3, config.ideal_price_high / price)


def score_momentum(prices: list[int], config: PickerConfig) -> float:
    """
    모멘텀 강도: 최근 틱들의 방향성 + 가속도.
    방향이 일관되고 가속될수록 높은 점수.
    """
    n = min(len(prices), config.momentum_window)
    if n < 5:
        return 0.5  # 데이터 부족

    recent = prices[-n:]
    changes = [recent[i] - recent[i - 1] for i in range(1, len(recent))]

    if not changes:
        return 0.5

    # Direction consistency
    ups = sum(1 for c in changes if c > 0)
    downs = sum(1 for c in changes if c < 0)
    total = len(changes)
    consistency = max(ups, downs) / total  # 0.5 ~ 1.0

    # Magnitude (absolute average change relative to price)
    avg_change = np.mean([abs(c) for c in changes])
    avg_price = np.mean(recent)
    magnitude = min((avg_change / avg_price * 100) / 0.1, 1.0) if avg_price > 0 else 0  # 0.1% 틱변화 기준

    # Acceleration (later changes bigger than earlier?)
    first_half = np.mean([abs(c) for c in changes[:len(changes) // 2]] or [0])
    second_half = np.mean([abs(c) for c in changes[len(changes) // 2:]] or [0])
    acceleration = min(second_half / first_half, 2.0) / 2.0 if first_half > 0 else 0.5

    return consistency * 0.5 + magnitude * 0.3 + acceleration * 0.2


# ─── Scalp Picker Engine ───

class ScalpPicker:
    def __init__(self):
        self.config = PickerConfig()
        self._last_scan: list[dict] = []
        self._last_scan_time: float = 0

    def update_config(self, new_config: dict):
        self.config = PickerConfig.from_dict(new_config)

    def scan(self, force: bool = False) -> list[dict]:
        """
        Scan and rank stocks for scalping suitability.
        Uses real-time data from WebSocket + historical data from data_collector.
        Returns sorted list of top candidates with scores.
        """
        # Throttle: minimum 10s between scans
        if not force and (time.time() - self._last_scan_time) < 10 and self._last_scan:
            return self._last_scan

        from services.kiwoom_ws import kiwoom_ws_manager
        from services.scalping_engine import scalping_engine
        from services.data_collector import get_top_stocks, get_stock_ohlcv

        candidates = []

        # 1. Get pool of stocks (top by volume + WebSocket active)
        try:
            top_stocks = get_top_stocks(count=self.config.volume_rank_top, market="ALL")
        except Exception:
            top_stocks = []

        # Add any stocks with real-time WebSocket data
        ws_codes = set(kiwoom_ws_manager.realtime_data.keys())
        stock_pool = {}

        for s in top_stocks:
            code = s.get("code", "")
            if code:
                stock_pool[code] = {
                    "code": code,
                    "name": s.get("name", code),
                    "price": s.get("close", s.get("price", 0)),
                    "volume": s.get("volume", 0),
                    "change_pct": s.get("change_pct", 0),
                    "high": s.get("high", 0),
                    "low": s.get("low", 0),
                }

        for code in ws_codes:
            if code not in stock_pool:
                rt = kiwoom_ws_manager.realtime_data.get(code, {})
                stock_pool[code] = {
                    "code": code,
                    "name": code,
                    "price": rt.get("price", 0),
                    "volume": rt.get("volume", 0),
                    "change_pct": rt.get("change_pct", 0),
                    "high": 0,
                    "low": 0,
                }

        # 2. Score each stock
        for code, info in stock_pool.items():
            try:
                price = info["price"]
                if price <= 0:
                    continue

                # Price filter
                if price < self.config.min_price or price > self.config.max_price:
                    continue

                volume = info["volume"]

                # Get historical data for average volume
                try:
                    ohlcv = get_stock_ohlcv(code, days=20)
                    if ohlcv is not None and not ohlcv.empty:
                        avg_volume = float(ohlcv["Volume"].mean())
                        # Use today's high/low if not available from real-time
                        if info["high"] == 0:
                            info["high"] = float(ohlcv.iloc[-1].get("High", price))
                        if info["low"] == 0:
                            info["low"] = float(ohlcv.iloc[-1].get("Low", price))
                    else:
                        avg_volume = volume
                except Exception:
                    avg_volume = volume

                high = info["high"] or price
                low = info["low"] or price

                # Order book data
                ob = kiwoom_ws_manager.orderbook_data.get(code, {})
                bid = ob.get("bid", 0)
                ask = ob.get("ask", 0)

                # Tick buffer data
                tick_buf = scalping_engine.tick_buffers.get(code)
                tick_count = tick_buf.count if tick_buf else 0
                tick_duration = 0
                tick_prices = []
                if tick_buf and tick_buf.count >= 2:
                    tick_duration = tick_buf.ticks[-1].timestamp - tick_buf.ticks[0].timestamp
                    tick_prices = list(tick_buf.prices)

                # Compute individual scores
                vol_score = score_volume(volume, avg_volume, self.config)
                volat_score = score_volatility(high, low, price, self.config)
                spread_score = score_spread(bid, ask, price, self.config)
                tick_score = score_tick_frequency(tick_count, tick_duration, self.config)
                price_score = score_price_fitness(price, self.config)
                mom_score = score_momentum(tick_prices, self.config)

                # Weighted composite score
                w = self.config.weights
                total_score = (
                    vol_score * w.get("volume", 0.25)
                    + volat_score * w.get("volatility", 0.20)
                    + spread_score * w.get("spread", 0.15)
                    + tick_score * w.get("tick_freq", 0.15)
                    + price_score * w.get("price_fit", 0.10)
                    + mom_score * w.get("momentum", 0.15)
                )

                # Volatility percentage
                volatility_pct = round((high - low) / price * 100, 2) if price > 0 else 0
                spread_pct = round((ask - bid) / price * 100, 3) if price > 0 and bid > 0 and ask > 0 else 0

                candidates.append({
                    "code": code,
                    "name": info["name"],
                    "price": price,
                    "volume": volume,
                    "avg_volume": round(avg_volume),
                    "volume_ratio": round(volume / avg_volume, 2) if avg_volume > 0 else 0,
                    "change_pct": round(info["change_pct"], 2),
                    "volatility_pct": volatility_pct,
                    "spread_pct": spread_pct,
                    "tick_count": tick_count,
                    "scores": {
                        "volume": round(vol_score, 3),
                        "volatility": round(volat_score, 3),
                        "spread": round(spread_score, 3),
                        "tick_freq": round(tick_score, 3),
                        "price_fit": round(price_score, 3),
                        "momentum": round(mom_score, 3),
                    },
                    "total_score": round(total_score, 3),
                    "grade": _score_to_grade(total_score),
                })

            except Exception as e:
                logger.warning(f"Error scoring {code}: {e}")

        # Sort by total score descending
        candidates.sort(key=lambda x: x["total_score"], reverse=True)
        result = candidates[:self.config.top_n]

        self._last_scan = result
        self._last_scan_time = time.time()

        return result


def _score_to_grade(score: float) -> str:
    if score >= 0.8:
        return "S"
    elif score >= 0.65:
        return "A"
    elif score >= 0.5:
        return "B"
    elif score >= 0.35:
        return "C"
    else:
        return "D"


# Global Instance
scalp_picker = ScalpPicker()
