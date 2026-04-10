"""
Scalping Engine - 초단타 자동매매 엔진

Strategies:
1. Tick Momentum (틱 모멘텀) - 연속 체결 방향 추적
2. VWAP Deviation (VWAP 이탈) - 단기 VWAP 대비 괴리율
3. Order Book Imbalance (호가 불균형) - 매수/매도 호가잔량 비율
4. Bollinger Scalp (볼린저 스캘핑) - 단기 볼린저밴드 이탈 후 회귀

Risk Management:
- Per-trade stop-loss / take-profit
- Max position size
- Daily loss limit
- Max concurrent positions
"""
import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional
import numpy as np

logger = logging.getLogger(__name__)

# 설정 파일 경로
_CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "trading_journals"
_SCALP_CONFIG_FILE = _CONFIG_DIR / "scalp_config.json"

# 매매일지 & AI 두뇌
from services.trade_journal import trade_journal
from services.trade_analyzer import trade_brain


# ─── Data Structures ───

class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"

class SignalStrength(str, Enum):
    STRONG = "strong"
    NORMAL = "normal"
    WEAK = "weak"

@dataclass
class Tick:
    code: str
    price: int
    volume: int
    timestamp: float
    bid: int = 0          # 최우선 매수호가
    ask: int = 0          # 최우선 매도호가
    bid_qty: int = 0      # 매수호가 잔량
    ask_qty: int = 0      # 매도호가 잔량

@dataclass
class ScalpSignal:
    code: str
    side: Side
    strategy: str
    strength: SignalStrength
    price: int
    reason: str
    timestamp: float = field(default_factory=time.time)

@dataclass
class Position:
    code: str
    side: Side
    entry_price: int
    quantity: int
    entry_time: float
    order_no: str = ""
    stop_loss: int = 0
    take_profit: int = 0
    pnl: float = 0.0

@dataclass
class TradeLog:
    code: str
    side: str
    entry_price: int
    exit_price: int
    quantity: int
    pnl: float
    pnl_pct: float
    strategy: str
    hold_seconds: float
    entry_time: str
    exit_time: str


# ─── Scalping Configuration ───

@dataclass
class ScalpConfig:
    # Strategy toggles
    use_tick_momentum: bool = True
    use_vwap_deviation: bool = True
    use_orderbook_imbalance: bool = True
    use_bollinger_scalp: bool = True

    # Tick Momentum params
    tick_window: int = 20             # 최근 N틱 분석
    tick_momentum_threshold: float = 0.7  # 70% 이상 같은 방향이면 시그널

    # VWAP params
    vwap_window: int = 60             # VWAP 계산 틱 수
    vwap_entry_deviation: float = 0.3  # VWAP 대비 0.3% 이탈 시 진입
    vwap_exit_deviation: float = 0.1   # VWAP 회귀 시 청산

    # Order Book Imbalance params
    imbalance_threshold: float = 2.0   # 매수잔량/매도잔량 비율 2배 이상

    # Bollinger Scalp params
    bb_window: int = 30               # 볼린저 틱 윈도우
    bb_std: float = 2.0               # 표준편차 배수
    bb_squeeze_threshold: float = 0.2  # 밴드폭 0.2% 이하 = 스퀴즈

    # EMA Crossover params (제미나이추천)
    use_ema_cross: bool = False
    ema_fast: int = 9                  # 빠른 EMA 주기
    ema_slow: int = 21                 # 느린 EMA 주기

    # Stochastic params (제미나이추천)
    use_stochastic: bool = False
    stoch_k: int = 5                   # %K 주기
    stoch_d: int = 3                   # %D 주기 (SMA of %K)
    stoch_smooth: int = 3              # %K 스무딩
    stoch_oversold: float = 20.0       # 과매도 임계
    stoch_overbought: float = 80.0     # 과매수 임계

    # MACD params (제미나이추천)
    use_macd: bool = False
    macd_fast: int = 8                 # 빠른 EMA
    macd_slow: int = 21                # 느린 EMA
    macd_signal: int = 5               # 시그널 EMA

    # ALMA params (제미나이추천)
    use_alma: bool = False
    alma_window: int = 21              # ALMA 윈도우
    alma_offset: float = 0.85          # 오프셋 (0~1)
    alma_sigma: float = 6.0            # 시그마

    # 체결강도 필터 (제미나이추천)
    use_execution_strength: bool = False
    exec_strength_threshold: float = 100.0  # 체결강도 100% 이상 시 매수 신호
    exec_strength_window: int = 30          # 체결강도 계산 틱 수

    # Order params
    order_quantity: int = 10           # 기본 주문수량
    price_type: str = "market"         # "market" | "limit"
    limit_offset_ticks: int = 1        # 지정가 시 호가 단위 오프셋

    # Risk Management
    # 왕복 수수료 약 0.21% (매수 0.015% + 매도 0.015% + 거래세 0.18%)
    stop_loss_pct: float = 0.5         # 손절: 0.5% (수수료 포함 실제 -0.71%)
    take_profit_pct: float = 1.5       # 익절: 1.5% (수수료 차감 후 순이익 ~1.29%)
    max_position_count: int = 3        # 최대 동시 포지션
    max_daily_loss: float = 100000     # 일일 최대 손실(원)
    max_hold_seconds: float = 300      # 최대 보유 시간 (5분)
    cooldown_seconds: float = 5        # 매매 후 쿨다운

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items()}

    @classmethod
    def from_dict(cls, d: dict):
        config = cls()
        for k, v in d.items():
            if hasattr(config, k):
                expected_type = type(getattr(config, k))
                setattr(config, k, expected_type(v))
        return config

    def save_to_file(self):
        """설정을 JSON 파일로 저장"""
        try:
            _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            _SCALP_CONFIG_FILE.write_text(
                json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            logger.info(f"[ScalpConfig] 설정 저장 완료: {_SCALP_CONFIG_FILE}")
        except Exception as e:
            logger.error(f"[ScalpConfig] 설정 저장 실패: {e}")

    @classmethod
    def load_from_file(cls):
        """저장된 설정 파일에서 로드, 없으면 기본값"""
        if _SCALP_CONFIG_FILE.exists():
            try:
                d = json.loads(_SCALP_CONFIG_FILE.read_text(encoding="utf-8"))
                config = cls.from_dict(d)
                logger.info(f"[ScalpConfig] 저장된 설정 로드 완료")
                return config
            except Exception as e:
                logger.error(f"[ScalpConfig] 설정 로드 실패, 기본값 사용: {e}")
        return cls()


# ─── Tick Buffer (per-stock ring buffer) ───

class TickBuffer:
    def __init__(self, maxlen: int = 200):
        self.ticks: deque[Tick] = deque(maxlen=maxlen)
        self.prices: deque[int] = deque(maxlen=maxlen)
        self.volumes: deque[int] = deque(maxlen=maxlen)

    def add(self, tick: Tick):
        self.ticks.append(tick)
        self.prices.append(tick.price)
        self.volumes.append(tick.volume)

    @property
    def count(self) -> int:
        return len(self.ticks)

    def last_n_prices(self, n: int) -> list[int]:
        return list(self.prices)[-n:]

    def last_n_volumes(self, n: int) -> list[int]:
        return list(self.volumes)[-n:]

    @property
    def latest(self) -> Optional[Tick]:
        return self.ticks[-1] if self.ticks else None

    def vwap(self, n: int) -> float:
        """Volume-Weighted Average Price over last n ticks"""
        prices = self.last_n_prices(n)
        volumes = self.last_n_volumes(n)
        if not prices or sum(volumes) == 0:
            return 0
        total_pv = sum(p * v for p, v in zip(prices, volumes))
        total_v = sum(volumes)
        return total_pv / total_v

    def bollinger(self, n: int, std_mult: float = 2.0):
        """Bollinger Bands over last n ticks"""
        prices = self.last_n_prices(n)
        if len(prices) < n:
            return None, None, None
        arr = np.array(prices, dtype=float)
        mid = float(np.mean(arr))
        std = float(np.std(arr))
        upper = mid + std_mult * std
        lower = mid - std_mult * std
        return upper, mid, lower

    def ema(self, n: int, period: int) -> Optional[float]:
        """EMA (Exponential Moving Average) over last n prices"""
        prices = self.last_n_prices(n)
        if len(prices) < period:
            return None
        arr = np.array(prices, dtype=float)
        multiplier = 2.0 / (period + 1)
        ema_val = arr[0]
        for p in arr[1:]:
            ema_val = (p - ema_val) * multiplier + ema_val
        return float(ema_val)

    def ema_series(self, prices: list, period: int) -> list[float]:
        """Calculate EMA series from price list"""
        if len(prices) < period:
            return []
        multiplier = 2.0 / (period + 1)
        result = [float(prices[0])]
        for p in prices[1:]:
            result.append((float(p) - result[-1]) * multiplier + result[-1])
        return result

    def stochastic(self, k_period: int, d_period: int, smooth: int = 3):
        """Stochastic %K, %D calculation"""
        n = k_period + d_period + smooth + 10  # enough data
        prices = self.last_n_prices(n)
        if len(prices) < k_period + smooth:
            return None, None

        # Calculate raw %K values
        raw_k_values = []
        for i in range(k_period - 1, len(prices)):
            window = prices[i - k_period + 1:i + 1]
            high = max(window)
            low = min(window)
            if high == low:
                raw_k_values.append(50.0)
            else:
                raw_k_values.append((prices[i] - low) / (high - low) * 100)

        if len(raw_k_values) < smooth:
            return None, None

        # Smooth %K with SMA
        smoothed_k = []
        for i in range(smooth - 1, len(raw_k_values)):
            smoothed_k.append(np.mean(raw_k_values[i - smooth + 1:i + 1]))

        if len(smoothed_k) < d_period:
            return None, None

        # %D = SMA of smoothed %K
        k_val = smoothed_k[-1]
        d_val = np.mean(smoothed_k[-d_period:])
        return float(k_val), float(d_val)

    def macd(self, fast: int, slow: int, signal: int):
        """MACD line, signal line, histogram"""
        n = slow + signal + 10
        prices = self.last_n_prices(n)
        if len(prices) < slow + signal:
            return None, None, None

        fast_ema = self.ema_series(prices, fast)
        slow_ema = self.ema_series(prices, slow)

        if len(fast_ema) < 2 or len(slow_ema) < 2:
            return None, None, None

        # Align lengths
        min_len = min(len(fast_ema), len(slow_ema))
        macd_line = [f - s for f, s in zip(fast_ema[-min_len:], slow_ema[-min_len:])]

        if len(macd_line) < signal:
            return None, None, None

        signal_line = self.ema_series(macd_line, signal)
        if not signal_line:
            return None, None, None

        macd_val = macd_line[-1]
        signal_val = signal_line[-1]
        histogram = macd_val - signal_val
        return float(macd_val), float(signal_val), float(histogram)

    def alma(self, window: int, offset: float = 0.85, sigma: float = 6.0) -> Optional[float]:
        """ALMA (Arnaud Legoux Moving Average)"""
        prices = self.last_n_prices(window)
        if len(prices) < window:
            return None

        m = offset * (window - 1)
        s = window / sigma
        arr = np.array(prices, dtype=float)

        weights = np.exp(-((np.arange(window) - m) ** 2) / (2 * s * s))
        weights /= weights.sum()
        return float(np.dot(arr, weights))

    def execution_strength(self, n: int) -> Optional[float]:
        """체결강도: 매수체결량 / 매도체결량 * 100"""
        if len(self.ticks) < n:
            return None
        recent = list(self.ticks)[-n:]
        buy_vol = 0
        sell_vol = 0
        for i in range(1, len(recent)):
            vol = abs(recent[i].volume)
            if recent[i].price > recent[i - 1].price:
                buy_vol += vol
            elif recent[i].price < recent[i - 1].price:
                sell_vol += vol
            else:
                # 보합 시 이전 방향 유지 (매수호가 체결=매수, 매도호가 체결=매도)
                if recent[i].volume > 0:
                    buy_vol += vol // 2
                    sell_vol += vol // 2
        if sell_vol == 0:
            return 200.0 if buy_vol > 0 else 100.0
        return float(buy_vol / sell_vol * 100)


# ─── Strategy Implementations ───

def strategy_tick_momentum(buf: TickBuffer, config: ScalpConfig) -> Optional[ScalpSignal]:
    """
    틱 모멘텀: 최근 N틱의 가격 변화 방향을 분석.
    같은 방향 비율이 threshold를 넘으면 시그널.
    """
    if buf.count < config.tick_window:
        return None

    prices = buf.last_n_prices(config.tick_window)
    changes = [prices[i] - prices[i - 1] for i in range(1, len(prices))]

    ups = sum(1 for c in changes if c > 0)
    downs = sum(1 for c in changes if c < 0)
    total = len(changes)

    if total == 0:
        return None

    up_ratio = ups / total
    down_ratio = downs / total
    latest = buf.latest

    if up_ratio >= config.tick_momentum_threshold:
        return ScalpSignal(
            code=latest.code, side=Side.BUY, strategy="tick_momentum",
            strength=SignalStrength.STRONG if up_ratio > 0.85 else SignalStrength.NORMAL,
            price=latest.price,
            reason=f"연속 상승 {ups}/{total}틱 ({up_ratio:.0%})"
        )
    elif down_ratio >= config.tick_momentum_threshold:
        return ScalpSignal(
            code=latest.code, side=Side.SELL, strategy="tick_momentum",
            strength=SignalStrength.STRONG if down_ratio > 0.85 else SignalStrength.NORMAL,
            price=latest.price,
            reason=f"연속 하락 {downs}/{total}틱 ({down_ratio:.0%})"
        )
    return None


def strategy_vwap_deviation(buf: TickBuffer, config: ScalpConfig) -> Optional[ScalpSignal]:
    """
    VWAP 이탈: 현재가가 단기 VWAP 대비 일정 비율 이상 이탈하면
    회귀를 예상하고 반대 방향 진입.
    """
    if buf.count < config.vwap_window:
        return None

    vwap = buf.vwap(config.vwap_window)
    if vwap == 0:
        return None

    latest = buf.latest
    deviation_pct = (latest.price - vwap) / vwap * 100

    if deviation_pct <= -config.vwap_entry_deviation:
        return ScalpSignal(
            code=latest.code, side=Side.BUY, strategy="vwap_deviation",
            strength=SignalStrength.STRONG if abs(deviation_pct) > config.vwap_entry_deviation * 1.5 else SignalStrength.NORMAL,
            price=latest.price,
            reason=f"VWAP({int(vwap)}) 대비 {deviation_pct:+.2f}% 이탈 (매수 기회)"
        )
    elif deviation_pct >= config.vwap_entry_deviation:
        return ScalpSignal(
            code=latest.code, side=Side.SELL, strategy="vwap_deviation",
            strength=SignalStrength.STRONG if abs(deviation_pct) > config.vwap_entry_deviation * 1.5 else SignalStrength.NORMAL,
            price=latest.price,
            reason=f"VWAP({int(vwap)}) 대비 {deviation_pct:+.2f}% 이탈 (매도 기회)"
        )
    return None


def strategy_orderbook_imbalance(buf: TickBuffer, config: ScalpConfig) -> Optional[ScalpSignal]:
    """
    호가 불균형: 매수잔량/매도잔량 비율로 방향 판단.
    """
    latest = buf.latest
    if not latest or latest.bid_qty <= 0 or latest.ask_qty <= 0:
        return None

    ratio = latest.bid_qty / latest.ask_qty

    if ratio >= config.imbalance_threshold:
        return ScalpSignal(
            code=latest.code, side=Side.BUY, strategy="orderbook_imbalance",
            strength=SignalStrength.STRONG if ratio > config.imbalance_threshold * 1.5 else SignalStrength.NORMAL,
            price=latest.price,
            reason=f"호가 매수우위 (매수/매도 잔량비 {ratio:.1f}x)"
        )
    elif (1.0 / ratio) >= config.imbalance_threshold:
        return ScalpSignal(
            code=latest.code, side=Side.SELL, strategy="orderbook_imbalance",
            strength=SignalStrength.STRONG if (1.0 / ratio) > config.imbalance_threshold * 1.5 else SignalStrength.NORMAL,
            price=latest.price,
            reason=f"호가 매도우위 (매도/매수 잔량비 {1.0/ratio:.1f}x)"
        )
    return None


def strategy_bollinger_scalp(buf: TickBuffer, config: ScalpConfig) -> Optional[ScalpSignal]:
    """
    볼린저 스캘핑: 밴드 하단 터치 시 매수, 상단 터치 시 매도.
    스퀴즈 상태에서의 돌파도 감지.
    """
    if buf.count < config.bb_window:
        return None

    upper, mid, lower = buf.bollinger(config.bb_window, config.bb_std)
    if upper is None:
        return None

    latest = buf.latest
    price = latest.price
    band_width_pct = (upper - lower) / mid * 100 if mid > 0 else 0

    # 볼린저 밴드 하단 이탈 → 매수 (회귀 기대)
    if price <= lower:
        return ScalpSignal(
            code=latest.code, side=Side.BUY, strategy="bollinger_scalp",
            strength=SignalStrength.STRONG if price < lower * 0.999 else SignalStrength.NORMAL,
            price=price,
            reason=f"BB 하단({int(lower)}) 이탈, 밴드폭 {band_width_pct:.2f}%"
        )
    # 볼린저 밴드 상단 이탈 → 매도
    elif price >= upper:
        return ScalpSignal(
            code=latest.code, side=Side.SELL, strategy="bollinger_scalp",
            strength=SignalStrength.STRONG if price > upper * 1.001 else SignalStrength.NORMAL,
            price=price,
            reason=f"BB ��단({int(upper)}) ��탈, 밴드��� {band_width_pct:.2f}%"
        )
    return None


# ─── Gemini-Recommended Strategies ───

def strategy_ema_crossover(buf: TickBuffer, config: ScalpConfig) -> Optional[ScalpSignal]:
    """
    EMA 크로스오버: 빠른 EMA(9)가 느린 EMA(21)를 상향 돌파하면 매수,
    하향 돌파하면 매도.
    """
    n = config.ema_slow + 10
    if buf.count < n:
        return None

    prices = buf.last_n_prices(n)
    fast_ema = buf.ema_series(prices, config.ema_fast)
    slow_ema = buf.ema_series(prices, config.ema_slow)

    if len(fast_ema) < 3 or len(slow_ema) < 3:
        return None

    min_len = min(len(fast_ema), len(slow_ema))
    f_now, f_prev = fast_ema[-1], fast_ema[-2]
    s_now, s_prev = slow_ema[-min_len + len(fast_ema) - 1], slow_ema[-min_len + len(fast_ema) - 2]

    latest = buf.latest

    # 골든크로스: 빠른선이 느린선을 상향 돌파
    if f_prev <= s_prev and f_now > s_now:
        gap_pct = (f_now - s_now) / s_now * 100
        return ScalpSignal(
            code=latest.code, side=Side.BUY, strategy="ema_cross",
            strength=SignalStrength.STRONG if gap_pct > 0.05 else SignalStrength.NORMAL,
            price=latest.price,
            reason=f"EMA({config.ema_fast}/{config.ema_slow}) 골든크로스 (갭 {gap_pct:.3f}%)"
        )
    # 데드크로스: 빠른선이 느린선을 하향 돌파
    elif f_prev >= s_prev and f_now < s_now:
        gap_pct = (s_now - f_now) / s_now * 100
        return ScalpSignal(
            code=latest.code, side=Side.SELL, strategy="ema_cross",
            strength=SignalStrength.STRONG if gap_pct > 0.05 else SignalStrength.NORMAL,
            price=latest.price,
            reason=f"EMA({config.ema_fast}/{config.ema_slow}) 데드크로스 (갭 {gap_pct:.3f}%)"
        )
    return None


def strategy_stochastic(buf: TickBuffer, config: ScalpConfig) -> Optional[ScalpSignal]:
    """
    스토캐스틱: %K와 %D 크로스를 과매수/과매도 구간에서 감지.
    과매도(20 이하)에서 %K > %D 크로스 → 매수
    과매수(80 이상)에서 %K < %D 크로스 → 매도
    """
    k_val, d_val = buf.stochastic(config.stoch_k, config.stoch_d, config.stoch_smooth)
    if k_val is None or d_val is None:
        return None

    latest = buf.latest

    # 과매도 구간에서 %K가 %D를 상향 돌파
    if k_val < config.stoch_oversold and k_val > d_val:
        return ScalpSignal(
            code=latest.code, side=Side.BUY, strategy="stochastic",
            strength=SignalStrength.STRONG if k_val < config.stoch_oversold * 0.7 else SignalStrength.NORMAL,
            price=latest.price,
            reason=f"Stoch 과매도 반등 (%K={k_val:.1f}, %D={d_val:.1f})"
        )
    # 과매수 구간에서 %K가 %D를 하향 돌파
    elif k_val > config.stoch_overbought and k_val < d_val:
        return ScalpSignal(
            code=latest.code, side=Side.SELL, strategy="stochastic",
            strength=SignalStrength.STRONG if k_val > config.stoch_overbought + (100 - config.stoch_overbought) * 0.3 else SignalStrength.NORMAL,
            price=latest.price,
            reason=f"Stoch 과매수 하락 (%K={k_val:.1f}, %D={d_val:.1f})"
        )
    return None


def strategy_macd(buf: TickBuffer, config: ScalpConfig) -> Optional[ScalpSignal]:
    """
    MACD: MACD선이 시그널선을 돌파할 때 신호 발생.
    히스토그램 변화로 강도 판단.
    """
    macd_val, signal_val, histogram = buf.macd(config.macd_fast, config.macd_slow, config.macd_signal)
    if macd_val is None:
        return None

    # 이전 히스토그램 계산 (간단 근사)
    prices = buf.last_n_prices(config.macd_slow + config.macd_signal + 11)
    if len(prices) < config.macd_slow + config.macd_signal + 2:
        return None
    prev_prices = prices[:-1]
    fast_prev = buf.ema_series(prev_prices, config.macd_fast)
    slow_prev = buf.ema_series(prev_prices, config.macd_slow)
    if not fast_prev or not slow_prev:
        return None
    min_len = min(len(fast_prev), len(slow_prev))
    macd_prev_line = [f - s for f, s in zip(fast_prev[-min_len:], slow_prev[-min_len:])]
    if len(macd_prev_line) < config.macd_signal:
        return None
    signal_prev = buf.ema_series(macd_prev_line, config.macd_signal)
    if not signal_prev:
        return None
    prev_hist = macd_prev_line[-1] - signal_prev[-1]

    latest = buf.latest

    # 히스토그램이 음→양 전환 (MACD가 시그널 상향 돌파)
    if prev_hist <= 0 and histogram > 0:
        return ScalpSignal(
            code=latest.code, side=Side.BUY, strategy="macd",
            strength=SignalStrength.STRONG if histogram > abs(prev_hist) else SignalStrength.NORMAL,
            price=latest.price,
            reason=f"MACD({config.macd_fast},{config.macd_slow},{config.macd_signal}) 매수 전환 (H={histogram:.1f})"
        )
    # 히스토그램이 양→음 전환
    elif prev_hist >= 0 and histogram < 0:
        return ScalpSignal(
            code=latest.code, side=Side.SELL, strategy="macd",
            strength=SignalStrength.STRONG if abs(histogram) > abs(prev_hist) else SignalStrength.NORMAL,
            price=latest.price,
            reason=f"MACD({config.macd_fast},{config.macd_slow},{config.macd_signal}) 매도 전환 (H={histogram:.1f})"
        )
    return None


def strategy_alma(buf: TickBuffer, config: ScalpConfig) -> Optional[ScalpSignal]:
    """
    ALMA 추세 확인: 현재가가 ALMA 위에 있으면 상승 추세 (매수 보조),
    아래에 있으면 하락 추세 (매도 보조). 교차점에서 시그널 발생.
    """
    alma_val = buf.alma(config.alma_window, config.alma_offset, config.alma_sigma)
    if alma_val is None:
        return None

    # 이전 ALMA 근사 (1틱 전)
    prices = buf.last_n_prices(config.alma_window + 1)
    if len(prices) < config.alma_window + 1:
        return None
    prev_prices = prices[:-1]
    if len(prev_prices) < config.alma_window:
        return None
    m = config.alma_offset * (config.alma_window - 1)
    s = config.alma_window / config.alma_sigma
    weights = np.exp(-((np.arange(config.alma_window) - m) ** 2) / (2 * s * s))
    weights /= weights.sum()
    prev_alma = float(np.dot(np.array(prev_prices[-config.alma_window:], dtype=float), weights))

    latest = buf.latest
    price = float(latest.price)
    prev_price = float(prices[-2])

    # 가격이 ALMA를 상향 돌파
    if prev_price <= prev_alma and price > alma_val:
        dev_pct = (price - alma_val) / alma_val * 100
        return ScalpSignal(
            code=latest.code, side=Side.BUY, strategy="alma",
            strength=SignalStrength.STRONG if dev_pct > 0.1 else SignalStrength.NORMAL,
            price=latest.price,
            reason=f"ALMA({config.alma_window}) 상향 돌파 (가격 {price:.0f} > ALMA {alma_val:.0f})"
        )
    # 가격이 ALMA를 하향 돌파
    elif prev_price >= prev_alma and price < alma_val:
        dev_pct = (alma_val - price) / alma_val * 100
        return ScalpSignal(
            code=latest.code, side=Side.SELL, strategy="alma",
            strength=SignalStrength.STRONG if dev_pct > 0.1 else SignalStrength.NORMAL,
            price=latest.price,
            reason=f"ALMA({config.alma_window}) 하향 돌파 (가격 {price:.0f} < ALMA {alma_val:.0f})"
        )
    return None


def strategy_execution_strength(buf: TickBuffer, config: ScalpConfig) -> Optional[ScalpSignal]:
    """
    체결강도 필터: 매수체결량/매도체결량*100이 100% 초과 시 매수 우위,
    100% 미만 시 매도 우위. 급등 구간(150%+)에서 강한 매수 시그널.
    """
    strength = buf.execution_strength(config.exec_strength_window)
    if strength is None:
        return None

    latest = buf.latest

    # 체결강도 150% 이상 → 강한 매수
    if strength >= config.exec_strength_threshold * 1.5:
        return ScalpSignal(
            code=latest.code, side=Side.BUY, strategy="exec_strength",
            strength=SignalStrength.STRONG,
            price=latest.price,
            reason=f"체결강도 급등 ({strength:.1f}%, 임계 {config.exec_strength_threshold}%)"
        )
    # 체결강도 임계값 초과 → 매수
    elif strength >= config.exec_strength_threshold:
        return ScalpSignal(
            code=latest.code, side=Side.BUY, strategy="exec_strength",
            strength=SignalStrength.NORMAL,
            price=latest.price,
            reason=f"체결강도 매수우위 ({strength:.1f}%)"
        )
    # 체결강도 매우 낮음 (50% 이하) → 매도
    elif strength <= 100 - (config.exec_strength_threshold - 100) * 0.5:
        inv = 10000 / strength if strength > 0 else 200
        return ScalpSignal(
            code=latest.code, side=Side.SELL, strategy="exec_strength",
            strength=SignalStrength.STRONG if strength < 40 else SignalStrength.NORMAL,
            price=latest.price,
            reason=f"체결강도 매도우위 ({strength:.1f}%, 역강도 {inv:.1f}%)"
        )
    return None


# ─── Risk Manager ───

class RiskManager:
    def __init__(self, config: ScalpConfig):
        self.config = config
        self.daily_pnl: float = 0.0
        self.last_trade_time: float = 0.0
        self.trade_count: int = 0

    def can_open_position(self, positions: dict) -> tuple[bool, str]:
        """Check if a new position can be opened"""
        # Daily loss limit
        if self.daily_pnl <= -self.config.max_daily_loss:
            return False, f"일일 손실 한도 도달 ({self.daily_pnl:,.0f}원)"

        # Max concurrent positions
        if len(positions) >= self.config.max_position_count:
            return False, f"최대 포지션 수 도달 ({len(positions)}/{self.config.max_position_count})"

        # Cooldown
        elapsed = time.time() - self.last_trade_time
        if elapsed < self.config.cooldown_seconds:
            return False, f"쿨다운 중 ({self.config.cooldown_seconds - elapsed:.1f}초 남음)"

        return True, "OK"

    def check_exit_conditions(self, pos: Position, current_price: int) -> Optional[str]:
        """Check if a position should be closed"""
        if pos.side == Side.BUY:
            pnl_pct = (current_price - pos.entry_price) / pos.entry_price * 100
        else:
            pnl_pct = (pos.entry_price - current_price) / pos.entry_price * 100

        # Stop loss
        if pnl_pct <= -self.config.stop_loss_pct:
            return f"손절 ({pnl_pct:+.2f}%)"

        # Take profit
        if pnl_pct >= self.config.take_profit_pct:
            return f"익절 ({pnl_pct:+.2f}%)"

        # Max hold time
        hold_time = time.time() - pos.entry_time
        if hold_time >= self.config.max_hold_seconds:
            return f"최대 보유시간 초과 ({hold_time:.0f}초)"

        return None

    def record_trade(self, pnl: float):
        self.daily_pnl += pnl
        self.last_trade_time = time.time()
        self.trade_count += 1

    def reset_daily(self):
        self.daily_pnl = 0.0
        self.trade_count = 0


# ─── Scalping Engine ───

class ScalpingEngine:
    def __init__(self):
        self.config = ScalpConfig.load_from_file()
        self.risk = RiskManager(self.config)
        self.running = False
        self.target_codes: list[str] = []

        # Per-stock tick buffers
        self.tick_buffers: dict[str, TickBuffer] = {}

        # Active positions: code -> Position
        self.positions: dict[str, Position] = {}

        # Trade log
        self.trade_log: list[TradeLog] = []

        # Signal log (최근 50개)
        self.signal_log: deque[dict] = deque(maxlen=50)

        # Stats
        self.stats = {
            "started_at": None,
            "total_signals": 0,
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "total_pnl": 0.0,
        }

        # Engine loop task reference
        self._task: Optional[asyncio.Task] = None

    def update_config(self, new_config: dict):
        self.config = ScalpConfig.from_dict(new_config)
        self.risk.config = self.config
        # 파일에 저장 (서버 재시작 시 유지)
        self.config.save_to_file()
        logger.info(f"Scalping config updated + saved: {new_config}")

    def get_or_create_buffer(self, code: str) -> TickBuffer:
        if code not in self.tick_buffers:
            self.tick_buffers[code] = TickBuffer(maxlen=300)
        return self.tick_buffers[code]

    def on_tick(self, tick: Tick):
        """Called when a new tick arrives from WebSocket"""
        buf = self.get_or_create_buffer(tick.code)
        buf.add(tick)

        if not self.running:
            return

        if tick.code not in self.target_codes:
            return

        # 1. Check exit conditions for existing positions
        if tick.code in self.positions:
            pos = self.positions[tick.code]
            exit_reason = self.risk.check_exit_conditions(pos, tick.price)
            if exit_reason:
                self._close_position(tick.code, tick.price, exit_reason)
                return

        # 2. Generate signals from strategies
        signals = self._evaluate_strategies(buf)

        if signals:
            # Use the strongest signal
            best = max(signals, key=lambda s: (
                2 if s.strength == SignalStrength.STRONG else 1 if s.strength == SignalStrength.NORMAL else 0
            ))
            self.stats["total_signals"] += 1
            signal_data = {
                "code": best.code,
                "side": best.side.value,
                "strategy": best.strategy,
                "strength": best.strength.value,
                "price": best.price,
                "reason": best.reason,
                "time": datetime.now().strftime("%H:%M:%S.%f")[:-3],
                "action": "ENTRY" if best.code not in self.positions else "has_position",
            }
            self.signal_log.append(signal_data)

            # 매매일지 신호 기록
            try:
                trade_journal.record_signal(signal_data, engine_type="scalping_engine")
            except Exception as e:
                logger.error(f"[매매일지] 신호 기록 실패: {e}")

            # 3. Open position if allowed
            if best.code not in self.positions:
                can_open, msg = self.risk.can_open_position(self.positions)
                if can_open:
                    self._open_position(best)

    def _evaluate_strategies(self, buf: TickBuffer) -> list[ScalpSignal]:
        signals = []

        if self.config.use_tick_momentum:
            s = strategy_tick_momentum(buf, self.config)
            if s:
                signals.append(s)

        if self.config.use_vwap_deviation:
            s = strategy_vwap_deviation(buf, self.config)
            if s:
                signals.append(s)

        if self.config.use_orderbook_imbalance:
            s = strategy_orderbook_imbalance(buf, self.config)
            if s:
                signals.append(s)

        if self.config.use_bollinger_scalp:
            s = strategy_bollinger_scalp(buf, self.config)
            if s:
                signals.append(s)

        # Gemini-recommended strategies
        if self.config.use_ema_cross:
            s = strategy_ema_crossover(buf, self.config)
            if s:
                signals.append(s)

        if self.config.use_stochastic:
            s = strategy_stochastic(buf, self.config)
            if s:
                signals.append(s)

        if self.config.use_macd:
            s = strategy_macd(buf, self.config)
            if s:
                signals.append(s)

        if self.config.use_alma:
            s = strategy_alma(buf, self.config)
            if s:
                signals.append(s)

        if self.config.use_execution_strength:
            s = strategy_execution_strength(buf, self.config)
            if s:
                signals.append(s)

        return signals

    def _open_position(self, signal: ScalpSignal):
        """Open a new position based on signal"""
        from services.kiwoom_provider import kiwoom

        entry_price = signal.price
        quantity = self.config.order_quantity

        # Calculate stop-loss / take-profit prices
        if signal.side == Side.BUY:
            stop_loss = int(entry_price * (1 - self.config.stop_loss_pct / 100))
            take_profit = int(entry_price * (1 + self.config.take_profit_pct / 100))
        else:
            stop_loss = int(entry_price * (1 + self.config.stop_loss_pct / 100))
            take_profit = int(entry_price * (1 - self.config.take_profit_pct / 100))

        # Place order
        result = kiwoom.place_order(
            code=signal.code,
            order_type=signal.side.value,
            quantity=quantity,
            price=entry_price if self.config.price_type == "limit" else 0,
            price_type=self.config.price_type,
        )

        if result.get("success"):
            pos = Position(
                code=signal.code,
                side=signal.side,
                entry_price=entry_price,
                quantity=quantity,
                entry_time=time.time(),
                order_no=result.get("order_no", ""),
                stop_loss=stop_loss,
                take_profit=take_profit,
            )
            self.positions[signal.code] = pos
            logger.info(f"[SCALP] OPEN {signal.side.value.upper()} {signal.code} @ {entry_price:,} x{quantity} | {signal.strategy}: {signal.reason}")
        else:
            logger.warning(f"[SCALP] Order failed for {signal.code}: {result.get('message')}")

    def _close_position(self, code: str, exit_price: int, reason: str):
        """Close an existing position"""
        from services.kiwoom_provider import kiwoom

        pos = self.positions.get(code)
        if not pos:
            return

        # Place closing order (opposite side)
        close_side = "sell" if pos.side == Side.BUY else "buy"
        result = kiwoom.place_order(
            code=code,
            order_type=close_side,
            quantity=pos.quantity,
            price=exit_price if self.config.price_type == "limit" else 0,
            price_type=self.config.price_type,
        )

        # Calculate P&L
        if pos.side == Side.BUY:
            pnl = (exit_price - pos.entry_price) * pos.quantity
        else:
            pnl = (pos.entry_price - exit_price) * pos.quantity

        pnl_pct = pnl / (pos.entry_price * pos.quantity) * 100
        hold_time = time.time() - pos.entry_time

        # Record
        trade = TradeLog(
            code=code,
            side=pos.side.value,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            quantity=pos.quantity,
            pnl=pnl,
            pnl_pct=round(pnl_pct, 2),
            strategy=reason,
            hold_seconds=round(hold_time, 1),
            entry_time=datetime.fromtimestamp(pos.entry_time).strftime("%H:%M:%S"),
            exit_time=datetime.now().strftime("%H:%M:%S"),
        )
        self.trade_log.append(trade)

        # 매매일지 저장 & AI 학습
        try:
            trade_journal.record_trade(trade.__dict__, engine_type="scalping_engine")
            trade_brain.learn(trade.__dict__)
        except Exception as e:
            logger.error(f"[매매일지/Brain] 기록 실패: {e}")

        # Update stats
        self.risk.record_trade(pnl)
        self.stats["total_trades"] += 1
        self.stats["total_pnl"] += pnl
        if pnl > 0:
            self.stats["wins"] += 1
        else:
            self.stats["losses"] += 1

        del self.positions[code]
        logger.info(f"[SCALP] CLOSE {code} @ {exit_price:,} | P&L: {pnl:+,.0f}원 ({pnl_pct:+.2f}%) | {reason} | {hold_time:.1f}초")

    async def start(self, target_codes: list[str]):
        """Start the scalping engine"""
        if self.running:
            # Already running - add new codes if provided
            added = [c for c in target_codes if c not in self.target_codes]
            if added:
                self.target_codes.extend(added)
                for code in added:
                    self.get_or_create_buffer(code)
                logger.info(f"[SCALP] Added {len(added)} new codes while running: {added}")
                return {"success": True, "message": f"실행 중 - {len(added)}종목 추가됨 (총 {len(self.target_codes)}종목)"}
            return {"success": True, "message": f"이미 실행 중입니다. ({len(self.target_codes)}종목 감시 중)"}

        self.target_codes = target_codes
        self.running = True
        self.stats["started_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.risk.reset_daily()

        # Ensure tick buffers exist for targets
        for code in target_codes:
            self.get_or_create_buffer(code)

        # Start monitoring loop
        self._task = asyncio.create_task(self._monitor_loop())

        logger.info(f"[SCALP] Engine STARTED for {len(target_codes)} stocks: {target_codes}")
        return {"success": True, "message": f"스캘핑 시작: {len(target_codes)}종목"}

    async def stop(self):
        """Stop the scalping engine and close all positions"""
        if not self.running:
            return {"success": False, "message": "실행 중이 아닙니다."}

        self.running = False

        # Close all open positions at market
        for code in list(self.positions.keys()):
            buf = self.tick_buffers.get(code)
            if buf and buf.latest:
                self._close_position(code, buf.latest.price, "엔진 정지 - 전량 청산")

        if self._task:
            self._task.cancel()
            self._task = None

        logger.info("[SCALP] Engine STOPPED")
        return {"success": True, "message": "스캘핑 정지, 포지션 전량 청산"}

    async def _monitor_loop(self):
        """Background loop: check positions for time-based exits"""
        while self.running:
            try:
                for code in list(self.positions.keys()):
                    pos = self.positions.get(code)
                    if not pos:
                        continue
                    buf = self.tick_buffers.get(code)
                    if buf and buf.latest:
                        exit_reason = self.risk.check_exit_conditions(pos, buf.latest.price)
                        if exit_reason:
                            self._close_position(code, buf.latest.price, exit_reason)
            except Exception as e:
                logger.error(f"[SCALP] Monitor loop error: {e}")

            await asyncio.sleep(0.5)

    def get_status(self) -> dict:
        """Get current engine status"""
        positions_data = []
        for code, pos in self.positions.items():
            buf = self.tick_buffers.get(code)
            cur_price = buf.latest.price if buf and buf.latest else pos.entry_price
            if pos.side == Side.BUY:
                pnl = (cur_price - pos.entry_price) * pos.quantity
            else:
                pnl = (pos.entry_price - cur_price) * pos.quantity
            pnl_pct = pnl / (pos.entry_price * pos.quantity) * 100

            positions_data.append({
                "code": code,
                "side": pos.side.value,
                "entry_price": pos.entry_price,
                "current_price": cur_price,
                "quantity": pos.quantity,
                "pnl": round(pnl),
                "pnl_pct": round(pnl_pct, 2),
                "hold_seconds": round(time.time() - pos.entry_time, 1),
                "stop_loss": pos.stop_loss,
                "take_profit": pos.take_profit,
            })

        win_rate = (self.stats["wins"] / self.stats["total_trades"] * 100) if self.stats["total_trades"] > 0 else 0

        return {
            "running": self.running,
            "target_codes": self.target_codes,
            "started_at": self.stats["started_at"],
            "positions": positions_data,
            "position_count": len(self.positions),
            "signals": list(self.signal_log),
            "recent_trades": [t.__dict__ for t in self.trade_log[-20:]],
            "stats": {
                "total_signals": self.stats["total_signals"],
                "total_trades": self.stats["total_trades"],
                "wins": self.stats["wins"],
                "losses": self.stats["losses"],
                "win_rate": round(win_rate, 1),
                "total_pnl": round(self.stats["total_pnl"]),
                "daily_pnl": round(self.risk.daily_pnl),
            },
            "config": self.config.to_dict(),
        }


# Global Instance
scalping_engine = ScalpingEngine()
