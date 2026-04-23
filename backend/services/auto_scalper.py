"""
Auto Scalping System - 완전 자동 초단타 스캘핑 시스템

Features:
1. 자동 종목 검색 (거래량/변동성/스프레드 기반)
2. 자동 매수/매도 (6개 전략 + 컨센서스 시그널)
3. 자동 종목 로테이션 (성과 기반 교체)
4. KRX 장 시간 자동 관리
5. 호가 단위 자동 적용
6. 트레일링 스탑
7. 거래비용 반영 손익 계산
8. TA-Lib 기반 고급 지표

Cycle:
  [종목 검색] → [실시간 구독] → [시그널 감지] → [매수] → [모니터링] → [매도]
       ↑                                                                    ↓
       └────────────── [성과 평가 → 종목 교체] ←─────────────────────────────┘
"""
import asyncio
import json
import logging
import time
import numpy as np
from datetime import datetime, time as dtime
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, List, Tuple

logger = logging.getLogger(__name__)

# 설정 파일 경로
_CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "trading_journals"
_AUTO_CONFIG_FILE = _CONFIG_DIR / "auto_scalp_config.json"

# 매매일지 & AI 두뇌 & 프리셋 매니저
from services.trade_journal import trade_journal
from services.trade_analyzer import trade_brain
from services.skill_preset import preset_manager

# TA-Lib (optional but recommended)
try:
    import talib
    HAS_TALIB = True
    logger.info("TA-Lib loaded successfully")
except ImportError:
    HAS_TALIB = False
    logger.warning("TA-Lib not available, using fallback indicators")


# ═══════════════════════════════════════════════════════
#  KRX Market Rules
# ═══════════════════════════════════════════════════════

def get_tick_size(price: int) -> int:
    """KRX 호가 단위 (2024~ 기준)"""
    if price < 2000: return 1
    if price < 5000: return 5
    if price < 20000: return 10
    if price < 50000: return 50
    if price < 200000: return 100
    if price < 500000: return 500
    return 1000

def align_price(price: int, direction: str = "down") -> int:
    """호가 단위에 맞게 가격 정렬"""
    tick = get_tick_size(price)
    if direction == "down":
        return (price // tick) * tick
    else:
        return ((price + tick - 1) // tick) * tick

def is_market_open() -> Tuple[bool, str]:
    """장 운영 시간 확인"""
    now = datetime.now().time()
    if now < dtime(9, 0, 10):
        return False, "장 시작 전"
    if now >= dtime(15, 19):
        return False, "장 마감 (동시호가)"
    if now < dtime(9, 1, 0):
        return False, "개장 직후 안정화 대기"
    return True, "정상 거래 시간"

def estimate_commission(amount: float, is_sell: bool = False) -> float:
    """거래 수수료 + 세금 추정"""
    commission = amount * 0.00015  # 키움 온라인 수수료 0.015%
    tax = amount * 0.0018 if is_sell else 0  # 매도 시 증권거래세 0.18%
    return commission + tax


# ═══════════════════════════════════════════════════════
#  Data Structures
# ═══════════════════════════════════════════════════════

class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"

class EngineState(str, Enum):
    IDLE = "idle"
    SCANNING = "scanning"
    TRADING = "trading"
    ROTATING = "rotating"
    STOPPED = "stopped"
    MARKET_CLOSED = "market_closed"

@dataclass
class Tick:
    code: str
    price: int
    volume: int
    timestamp: float
    bid: int = 0
    ask: int = 0
    bid_qty: int = 0
    ask_qty: int = 0

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
    highest_since_entry: int = 0  # 트레일링 스탑용
    lowest_since_entry: int = 999999999
    strategy: str = ""
    # ── 근거 소멸 청산(Tier 2) + 본전 보호(Tier 3) 용 진입 시점 메타 ──
    entry_strategies: list = field(default_factory=list)  # ["volume_spike","trade_intensity",...]
    entry_volume_baseline: float = 0.0   # 진입 시점 기준 거래량 평균 (volume_spike 판정용)
    entry_intensity: float = 1.0         # 진입 시점 체결강도 (trade_intensity 판정용)
    entry_imbalance_ratio: float = 1.0   # 진입 시점 매수/매도 호가비 (orderbook_imbalance 판정용)
    entry_bb_mid: float = 0.0            # 진입 시점 볼린저 중심선 (bollinger_scalp 판정용)
    entry_rsi: float = 50.0              # 진입 시점 RSI (rsi_extreme 판정용)
    peak_pnl_pct: float = 0.0            # 보유 중 최고 수익률 (본전 보호용)

@dataclass
class TradeResult:
    code: str
    side: str
    entry_price: int
    exit_price: int
    quantity: int
    gross_pnl: float       # 세전 손익
    net_pnl: float          # 수수료/세금 차감 후 손익
    commission: float       # 수수료+세금
    pnl_pct: float
    strategy: str
    hold_seconds: float
    entry_time: str
    exit_time: str
    exit_reason: str


# ═══════════════════════════════════════════════════════
#  Configuration
# ═══════════════════════════════════════════════════════

@dataclass
class AutoScalpConfig:
    # ── 종목 검색 설정 ──
    scan_interval_seconds: float = 60     # 1분마다 종목 재검색
    max_target_stocks: int = 5            # 동시 감시 종목 수
    min_volume: int = 300_000             # 최소 거래량 30만주
    min_price: int = 5_000                # 최소 가격 5천원 (저가주는 호가단위 대비 수수료 비율 높음)
    max_price: int = 100_000              # 최대 가격 10만원
    min_volatility_pct: float = 0.8       # 최소 변동률 0.8% (수수료 0.21% 커버 필요)
    max_volatility_pct: float = 5.0       # 최대 변동률

    # ── 전략 설정 ──
    use_tick_momentum: bool = True
    use_vwap_deviation: bool = True
    use_orderbook_imbalance: bool = True
    use_bollinger_scalp: bool = True
    use_rsi_extreme: bool = True          # RSI 과매수/과매도
    use_volume_spike: bool = True         # 거래량 급증
    use_ema_crossover: bool = False       # EMA 골든/데드 크로스
    use_trade_intensity: bool = False     # 체결강도 급변
    use_tick_acceleration: bool = False   # 틱 가격 가속도

    # ── 전략 파라미터 ──
    tick_window: int = 20
    tick_momentum_threshold: float = 0.7
    vwap_window: int = 60
    vwap_entry_deviation: float = 0.3
    imbalance_threshold: float = 2.0
    bb_window: int = 30
    bb_std: float = 2.0
    rsi_period: int = 10
    rsi_oversold: float = 25.0
    rsi_overbought: float = 75.0
    volume_spike_mult: float = 3.0        # 평균 대비 3배

    # EMA Crossover params
    ema_fast_period: int = 9
    ema_slow_period: int = 21

    # Trade Intensity params
    intensity_window: int = 30
    intensity_buy_threshold: float = 2.0
    intensity_sell_threshold: float = 0.5

    # Tick Acceleration params
    accel_window: int = 20
    accel_threshold: float = 0.05

    # ── 종목 선정 추가 조건 ──
    min_trade_value: int = 5_000_000_000  # 최소 거래대금 50억
    min_tick_frequency: float = 10.0      # 분당 최소 체결 수
    max_spread_pct: float = 0.25          # 최대 스프레드율

    # ── 컨센서스 (다중 전략 합의) ──
    min_consensus: int = 2                # 최소 2개 전략 합의 시 진입

    # ── 주문 설정 ──
    order_quantity: int = 10
    price_type: str = "market"            # market | limit
    max_investment_per_trade: int = 500_000  # 1회 최대 50만원

    # ── 리스크 관리 ──
    # 왕복 수수료 약 0.21% (매수 0.015% + 매도 0.015% + 거래세 0.18%)
    # 손익분기 = 0.21% → 익절/트레일링은 반드시 수수료 이상이어야 함
    stop_loss_pct: float = 0.5            # 손절 0.5% (수수료 포함 실제 -0.71%)
    take_profit_pct: float = 1.5          # 익절 1.5% (수수료 차감 후 순이익 ~1.29%)
    trailing_stop_pct: float = 0.5        # 트레일링 스탑 0.5% (수수료 차감 후에도 수익 보전)
    use_trailing_stop: bool = True
    max_position_count: int = 3
    max_daily_loss: float = 50_000        # 일일 손실한도 5만원
    max_hold_seconds: float = 600         # 10분 안전망 (Tier 4): 스캘핑에서 시간은 '알람'이지 '트리거'가 아님
    cooldown_seconds: float = 3           # 3초 쿨다운
    max_daily_trades: int = 50            # 일일 최대 거래 횟수

    # ── Tier 2: 진입 근거 소멸 청산 (signal invalidation exit) ──
    # 시그널이 죽으면 시간에 관계없이 청산. 단 스캘핑의 본질은 "근거가 살아있는 한 보유".
    exit_on_signal_loss: bool = True
    signal_loss_volume_recovery: float = 1.2   # volume_spike: 최근 5틱 평균이 기준의 1.2배 이하로 회귀 시
    signal_loss_intensity_drop: float = 0.5    # trade_intensity: 진입 시 대비 50% 이하 추락 시
    signal_loss_imbalance_flip: float = 1.0    # orderbook_imbalance: 호가비 1.0 이하로 역전 시

    # ── Tier 3: 본전 보호 (breakeven protection) ──
    # 한 번이라도 피크에 다녀왔으면 이익을 손실로 만들지 않음.
    breakeven_protect_enabled: bool = True
    breakeven_protect_peak_pct: float = 0.30   # 보유 중 최고 수익률이 이 값 이상이었고
    breakeven_protect_tolerance: float = 0.05  # 현재가 본전±tolerance(%) 권으로 돌아오면 즉시 청산

    # ── 종목 로테이션 ──
    rotation_interval_seconds: float = 600  # 10분마다 성과 평가
    min_rotation_trades: int = 3            # 최소 3회 거래 후 평가
    rotation_loss_threshold: float = -0.5   # 수익률 -0.5% 이하면 교체

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items()}

    @classmethod
    def from_dict(cls, d: dict):
        config = cls()
        for k, v in d.items():
            if hasattr(config, k):
                expected_type = type(getattr(config, k))
                try:
                    setattr(config, k, expected_type(v))
                except (ValueError, TypeError):
                    pass
        return config

    def save_to_file(self):
        """설정을 JSON 파일로 저장"""
        try:
            _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            _AUTO_CONFIG_FILE.write_text(
                json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            logger.info(f"[AutoScalpConfig] 설정 저장 완료: {_AUTO_CONFIG_FILE}")
        except Exception as e:
            logger.error(f"[AutoScalpConfig] 설정 저장 실패: {e}")

    @classmethod
    def load_from_file(cls):
        """저장된 설정 파일에서 로드, 없으면 활성 프리셋 기반"""
        if _AUTO_CONFIG_FILE.exists():
            try:
                d = json.loads(_AUTO_CONFIG_FILE.read_text(encoding="utf-8"))
                config = cls.from_dict(d)
                logger.info("[AutoScalpConfig] 저장된 설정 로드 완료")
                return config
            except Exception as e:
                logger.error(f"[AutoScalpConfig] 설정 로드 실패: {e}")

        # 저장 파일 없으면 활성 프리셋에서 생성
        try:
            active = preset_manager.get_active()
            if active:
                from services.skill_preset import PresetManager
                d = PresetManager._preset_to_config_dict(active)
                config = cls.from_dict(d)
                logger.info(f"[AutoScalpConfig] 프리셋 '{active.name}'에서 설정 로드")
                return config
        except Exception as e:
            logger.warning(f"[AutoScalpConfig] 프리셋 로드 실패, 기본값: {e}")

        return cls()


# ═══════════════════════════════════════════════════════
#  Tick Buffer (per-stock ring buffer)
# ═══════════════════════════════════════════════════════

class TickBuffer:
    """종목별 틱 데이터 링 버퍼 (최대 500틱)"""
    def __init__(self, maxlen: int = 500):
        self.ticks: deque = deque(maxlen=maxlen)

    def add(self, tick: Tick):
        self.ticks.append(tick)

    @property
    def latest(self) -> Optional[Tick]:
        return self.ticks[-1] if self.ticks else None

    def __len__(self):
        return len(self.ticks)

    def prices(self, n: int = 0) -> np.ndarray:
        data = list(self.ticks) if n <= 0 else list(self.ticks)[-n:]
        return np.array([t.price for t in data], dtype=float) if data else np.array([])

    def volumes(self, n: int = 0) -> np.ndarray:
        data = list(self.ticks) if n <= 0 else list(self.ticks)[-n:]
        return np.array([t.volume for t in data], dtype=float) if data else np.array([])

    def vwap(self, n: int = 60) -> float:
        data = list(self.ticks)[-n:]
        if not data:
            return 0.0
        prices = np.array([t.price for t in data], dtype=float)
        volumes = np.array([t.volume for t in data], dtype=float)
        total_vol = volumes.sum()
        if total_vol == 0:
            return float(np.mean(prices))
        return float(np.sum(prices * volumes) / total_vol)


# ═══════════════════════════════════════════════════════
#  Strategy Engine (9 strategies + weight-based consensus)
# ═══════════════════════════════════════════════════════

class StrategyEngine:
    """9개 전략 + 가중치 기반 컨센서스 시그널 생성"""

    def __init__(self, config: AutoScalpConfig):
        self.config = config
        # 프리셋에서 전략별 가중치 로드
        self._weights = {}
        try:
            active = preset_manager.get_active()
            if active:
                for name, s in active.strategies.items():
                    self._weights[name] = s.get("weight", 1.0)
        except Exception:
            pass

    def get_trend(self, buf: TickBuffer) -> str:
        """최근 틱 데이터로 단기 추세 판단 (up/down/neutral)
        강한 추세에서만 방향 반환 (EMA10-EMA20 괴리율 0.15% 이상)
        """
        prices = buf.prices(50)
        if len(prices) < 20:
            return "neutral"
        ema20 = float(np.mean(prices[-20:]))
        ema10 = float(np.mean(prices[-10:]))
        price = float(prices[-1])
        if ema20 <= 0:
            return "neutral"
        # 강한 추세 임계값: EMA 괴리율 0.15% 이상
        diff_pct = abs(ema10 - ema20) / ema20 * 100
        if diff_pct < 0.15:
            return "neutral"
        if ema10 > ema20 and price > ema10:
            return "up"
        elif ema10 < ema20 and price < ema10:
            return "down"
        return "neutral"

    def evaluate(self, code: str, buf: TickBuffer, orderbook: dict) -> List[dict]:
        """모든 활성 전략 평가 → 시그널 리스트 반환"""
        signals = []

        if len(buf) < max(self.config.tick_window, 30):
            return signals

        price = buf.latest.price

        if self.config.use_tick_momentum:
            sig = self._tick_momentum(code, buf, price)
            if sig: signals.append(sig)

        if self.config.use_vwap_deviation:
            sig = self._vwap_deviation(code, buf, price)
            if sig: signals.append(sig)

        if self.config.use_orderbook_imbalance:
            sig = self._orderbook_imbalance(code, buf, price, orderbook)
            if sig: signals.append(sig)

        if self.config.use_bollinger_scalp:
            sig = self._bollinger_scalp(code, buf, price)
            if sig: signals.append(sig)

        if self.config.use_rsi_extreme:
            sig = self._rsi_extreme(code, buf, price)
            if sig: signals.append(sig)

        if self.config.use_volume_spike:
            sig = self._volume_spike(code, buf, price)
            if sig: signals.append(sig)

        if self.config.use_ema_crossover:
            sig = self._ema_crossover(code, buf, price)
            if sig: signals.append(sig)

        if self.config.use_trade_intensity:
            sig = self._trade_intensity(code, buf, price, orderbook)
            if sig: signals.append(sig)

        if self.config.use_tick_acceleration:
            sig = self._tick_acceleration(code, buf, price)
            if sig: signals.append(sig)

        return signals

    def get_consensus(self, signals: List[dict], buf: TickBuffer = None) -> Optional[dict]:
        """가중치 기반 컨센서스 + 추세 필터: 역추세 진입 차단"""
        if not signals:
            return None

        # 추세 판단
        trend = self.get_trend(buf) if buf else "neutral"

        buy_signals = [s for s in signals if s["side"] == Side.BUY]
        sell_signals = [s for s in signals if s["side"] == Side.SELL]

        # 추세 역방향 시그널 필터링 (하락 추세에서 매수 차단, 상승 추세에서 매도 차단)
        if trend == "down":
            buy_signals = []  # 하락 추세에서 매수 금지
        elif trend == "up":
            sell_signals = []  # 상승 추세에서 매도 금지

        buy_weight = sum(self._weights.get(s["strategy"], 1.0) for s in buy_signals)
        sell_weight = sum(self._weights.get(s["strategy"], 1.0) for s in sell_signals)

        if buy_weight >= self.config.min_consensus:
            strategies = [s["strategy"] for s in buy_signals]
            return {
                "side": Side.BUY,
                "strategy": f"consensus({','.join(strategies)})",
                "strength": round(buy_weight, 1),
                "reason": f"매수 합의 (가중치 {buy_weight:.1f} >= {self.config.min_consensus}, 추세={trend})",
            }

        if sell_weight >= self.config.min_consensus:
            strategies = [s["strategy"] for s in sell_signals]
            return {
                "side": Side.SELL,
                "strategy": f"consensus({','.join(strategies)})",
                "strength": round(sell_weight, 1),
                "reason": f"매도 합의 (가중치 {sell_weight:.1f} >= {self.config.min_consensus}, 추세={trend})",
            }

        return None

    # ── Strategy 1: Tick Momentum ──
    def _tick_momentum(self, code, buf, price) -> Optional[dict]:
        prices = buf.prices(self.config.tick_window)
        if len(prices) < self.config.tick_window:
            return None
        changes = np.diff(prices)
        ups = np.sum(changes > 0)
        downs = np.sum(changes < 0)
        total = len(changes)
        if total == 0:
            return None

        up_ratio = ups / total
        down_ratio = downs / total

        if up_ratio >= self.config.tick_momentum_threshold:
            return {"side": Side.BUY, "strategy": "tick_momentum",
                    "reason": f"상승틱 {up_ratio:.0%}"}
        if down_ratio >= self.config.tick_momentum_threshold:
            return {"side": Side.SELL, "strategy": "tick_momentum",
                    "reason": f"하락틱 {down_ratio:.0%}"}
        return None

    # ── Strategy 2: VWAP Deviation ──
    def _vwap_deviation(self, code, buf, price) -> Optional[dict]:
        vwap = buf.vwap(self.config.vwap_window)
        if vwap <= 0:
            return None
        dev_pct = (price - vwap) / vwap * 100

        if dev_pct <= -self.config.vwap_entry_deviation:
            return {"side": Side.BUY, "strategy": "vwap_deviation",
                    "reason": f"VWAP 하회 {dev_pct:.2f}%"}
        if dev_pct >= self.config.vwap_entry_deviation:
            return {"side": Side.SELL, "strategy": "vwap_deviation",
                    "reason": f"VWAP 상회 +{dev_pct:.2f}%"}
        return None

    # ── Strategy 3: Orderbook Imbalance ──
    def _orderbook_imbalance(self, code, buf, price, orderbook) -> Optional[dict]:
        if not orderbook:
            return None
        bid_qty = orderbook.get("bid_qty1", 0) or 0
        ask_qty = orderbook.get("ask_qty1", 0) or 0
        if bid_qty == 0 or ask_qty == 0:
            return None

        ratio = bid_qty / ask_qty
        if ratio >= self.config.imbalance_threshold:
            return {"side": Side.BUY, "strategy": "orderbook_imbalance",
                    "reason": f"매수잔량 {ratio:.1f}배"}
        if (1 / ratio) >= self.config.imbalance_threshold:
            return {"side": Side.SELL, "strategy": "orderbook_imbalance",
                    "reason": f"매도잔량 {1/ratio:.1f}배"}
        return None

    # ── Strategy 4: Bollinger Scalp ──
    def _bollinger_scalp(self, code, buf, price) -> Optional[dict]:
        prices = buf.prices(self.config.bb_window)
        if len(prices) < self.config.bb_window:
            return None
        mid = float(np.mean(prices))
        std = float(np.std(prices))
        if mid <= 0 or std <= 0:
            return None

        upper = mid + self.config.bb_std * std
        lower = mid - self.config.bb_std * std

        if price <= lower:
            return {"side": Side.BUY, "strategy": "bollinger_scalp",
                    "reason": f"하한밴드 도달 ({price}≤{int(lower)})"}
        if price >= upper:
            return {"side": Side.SELL, "strategy": "bollinger_scalp",
                    "reason": f"상한밴드 도달 ({price}≥{int(upper)})"}
        return None

    # ── Strategy 5: RSI Extreme ──
    def _rsi_extreme(self, code, buf, price) -> Optional[dict]:
        prices = buf.prices(self.config.rsi_period + 10)
        if len(prices) < self.config.rsi_period + 1:
            return None

        if HAS_TALIB:
            rsi = talib.RSI(prices, timeperiod=self.config.rsi_period)
            rsi_val = rsi[-1]
        else:
            # Fallback RSI calculation
            deltas = np.diff(prices)
            gains = np.where(deltas > 0, deltas, 0)
            losses = np.where(deltas < 0, -deltas, 0)
            avg_gain = np.mean(gains[-self.config.rsi_period:])
            avg_loss = np.mean(losses[-self.config.rsi_period:])
            if avg_loss == 0:
                rsi_val = 100.0
            else:
                rs = avg_gain / avg_loss
                rsi_val = 100 - (100 / (1 + rs))

        if np.isnan(rsi_val):
            return None

        if rsi_val <= self.config.rsi_oversold:
            return {"side": Side.BUY, "strategy": "rsi_extreme",
                    "reason": f"RSI 과매도 {rsi_val:.0f}"}
        if rsi_val >= self.config.rsi_overbought:
            return {"side": Side.SELL, "strategy": "rsi_extreme",
                    "reason": f"RSI 과매수 {rsi_val:.0f}"}
        return None

    # ── Strategy 6: Volume Spike ──
    def _volume_spike(self, code, buf, price) -> Optional[dict]:
        volumes = buf.volumes(50)
        if len(volumes) < 20:
            return None

        recent_vol = float(np.mean(volumes[-5:]))
        baseline_vol = float(np.mean(volumes[:-5]))
        if baseline_vol <= 0:
            return None

        ratio = recent_vol / baseline_vol
        if ratio < self.config.volume_spike_mult:
            return None

        # 거래량 급증 시 가격 방향으로 진입
        prices = buf.prices(10)
        if len(prices) < 5:
            return None
        price_change = prices[-1] - prices[-5]

        if price_change > 0:
            return {"side": Side.BUY, "strategy": "volume_spike",
                    "reason": f"거래량 {ratio:.1f}배 + 상승"}
        elif price_change < 0:
            return {"side": Side.SELL, "strategy": "volume_spike",
                    "reason": f"거래량 {ratio:.1f}배 + 하락"}
        return None

    # ── Strategy 7: EMA Crossover ──
    def _ema_crossover(self, code, buf, price) -> Optional[dict]:
        """EMA(fast)/EMA(slow) 크로스오버 감지"""
        fast = self.config.ema_fast_period
        slow = self.config.ema_slow_period
        prices = buf.prices(slow + 5)
        if len(prices) < slow + 2:
            return None

        if HAS_TALIB:
            ema_fast = talib.EMA(prices, timeperiod=fast)
            ema_slow = talib.EMA(prices, timeperiod=slow)
        else:
            # Fallback EMA
            def _ema(data, period):
                result = np.zeros_like(data)
                result[0] = data[0]
                mult = 2.0 / (period + 1)
                for i in range(1, len(data)):
                    result[i] = data[i] * mult + result[i - 1] * (1 - mult)
                return result
            ema_fast = _ema(prices, fast)
            ema_slow = _ema(prices, slow)

        if np.isnan(ema_fast[-1]) or np.isnan(ema_slow[-1]):
            return None

        # 크로스 감지: 직전은 반대, 현재는 크로스
        prev_diff = ema_fast[-2] - ema_slow[-2]
        curr_diff = ema_fast[-1] - ema_slow[-1]

        if prev_diff <= 0 and curr_diff > 0:
            return {"side": Side.BUY, "strategy": "ema_crossover",
                    "reason": f"골든크로스 EMA({fast}/{slow})"}
        if prev_diff >= 0 and curr_diff < 0:
            return {"side": Side.SELL, "strategy": "ema_crossover",
                    "reason": f"데드크로스 EMA({fast}/{slow})"}
        return None

    # ── Strategy 8: Trade Intensity (체결강도) ──
    def _trade_intensity(self, code, buf, price, orderbook) -> Optional[dict]:
        """체결강도(매수체결량/매도체결량) 급변 감지"""
        window = self.config.intensity_window
        ticks = list(buf.ticks)[-window:]
        if len(ticks) < window:
            return None

        # 체결 방향 추정: 가격 상승 틱 = 매수 체결, 하락 = 매도 체결
        buy_vol = 0
        sell_vol = 0
        for i in range(1, len(ticks)):
            vol = ticks[i].volume
            if ticks[i].price > ticks[i - 1].price:
                buy_vol += vol
            elif ticks[i].price < ticks[i - 1].price:
                sell_vol += vol
            else:
                buy_vol += vol * 0.5
                sell_vol += vol * 0.5

        if sell_vol <= 0:
            intensity = 10.0
        else:
            intensity = buy_vol / sell_vol

        if intensity >= self.config.intensity_buy_threshold:
            return {"side": Side.BUY, "strategy": "trade_intensity",
                    "reason": f"체결강도 {intensity:.1f} (매수 우위)"}
        if intensity <= self.config.intensity_sell_threshold:
            return {"side": Side.SELL, "strategy": "trade_intensity",
                    "reason": f"체결강도 {intensity:.2f} (매도 우위)"}
        return None

    # ── Strategy 9: Tick Acceleration (틱 가속도) ──
    def _tick_acceleration(self, code, buf, price) -> Optional[dict]:
        """틱 가격 변화의 가속도(2차 미분) 감지"""
        window = self.config.accel_window
        prices = buf.prices(window)
        if len(prices) < window:
            return None

        # 1차 미분 (속도)
        velocity = np.diff(prices)
        # 2차 미분 (가속도)
        acceleration = np.diff(velocity)

        if len(acceleration) < 3:
            return None

        recent_accel = float(np.mean(acceleration[-5:]))
        recent_vel = float(np.mean(velocity[-5:]))
        avg_price = float(np.mean(prices))
        if avg_price <= 0:
            return None

        # 정규화 (가격 대비 비율)
        norm_accel = recent_accel / avg_price

        if norm_accel > self.config.accel_threshold and recent_vel > 0:
            return {"side": Side.BUY, "strategy": "tick_acceleration",
                    "reason": f"상승 가속 ({norm_accel:.4f})"}
        if norm_accel < -self.config.accel_threshold and recent_vel < 0:
            return {"side": Side.SELL, "strategy": "tick_acceleration",
                    "reason": f"하락 가속 ({norm_accel:.4f})"}
        return None


# ═══════════════════════════════════════════════════════
#  Risk Manager
# ═══════════════════════════════════════════════════════

class RiskManager:
    def __init__(self, config: AutoScalpConfig):
        self.config = config
        self.daily_pnl: float = 0.0
        self.daily_trades: int = 0
        self.last_trade_time: float = 0
        self._recent_pnls: list = []
        self._consecutive_losses: int = 0
        self._original_config_snapshot: dict = None

    def can_open(self, positions: dict) -> Tuple[bool, str]:
        """진입 가능 여부 확인"""
        # 장 시간 확인
        market_ok, msg = is_market_open()
        if not market_ok:
            return False, msg

        # 일일 손실 한도
        if self.daily_pnl <= -self.config.max_daily_loss:
            return False, f"일일 손실한도 도달 ({self.daily_pnl:,.0f}원)"

        # 일일 거래 횟수
        if self.daily_trades >= self.config.max_daily_trades:
            return False, f"일일 거래한도 도달 ({self.daily_trades}회)"

        # 최대 포지션 수
        if len(positions) >= self.config.max_position_count:
            return False, f"최대 포지션 도달 ({len(positions)}개)"

        # 쿨다운
        elapsed = time.time() - self.last_trade_time
        if elapsed < self.config.cooldown_seconds:
            return False, f"쿨다운 중 ({elapsed:.1f}s)"

        return True, "OK"

    def check_exit(self, pos: Position, current_price: int) -> Optional[str]:
        """청산 조건 확인 (Tier 1 하드룰 + Tier 4 안전망 시간)"""
        if pos.side == Side.BUY:
            pnl_pct = (current_price - pos.entry_price) / pos.entry_price * 100
        else:
            pnl_pct = (pos.entry_price - current_price) / pos.entry_price * 100

        # peak 업데이트 (Tier 3 본전 보호용)
        if pnl_pct > pos.peak_pnl_pct:
            pos.peak_pnl_pct = pnl_pct

        # Tier 3: 본전 보호 — 피크 갔다 왔으면 이익을 손실로 만들지 않음
        # ⚠️ 수수료(왕복 0.21%) 이상 확보한 상태에서만 작동 (수수료 손실 청산 방지)
        COMMISSION_FLOOR = 0.25  # 왕복수수료+여유
        if self.config.breakeven_protect_enabled:
            if pos.peak_pnl_pct >= max(self.config.breakeven_protect_peak_pct, COMMISSION_FLOOR * 2):
                tol = max(self.config.breakeven_protect_tolerance, COMMISSION_FLOOR)
                if pnl_pct <= tol and pnl_pct >= COMMISSION_FLOOR:
                    return f"본전보호 (피크 +{pos.peak_pnl_pct:.2f}% → 현재 {pnl_pct:+.2f}%)"

        # Tier 1: 손절
        if pnl_pct <= -self.config.stop_loss_pct:
            return f"손절 ({pnl_pct:.2f}%)"

        # 익절 - 트레일링 스탑이 활성화되어 있으면 홀딩, 아니면 즉시 익절
        if pnl_pct >= self.config.take_profit_pct:
            if self.config.use_trailing_stop:
                # 트레일링 스탑 활성 → 익절 목표 도달 후 트레일링으로 수익 극대화
                # (아래 트레일링 스탑 로직에서 처리)
                pass
            else:
                return f"익절 ({pnl_pct:.2f}%)"

        # 트레일링 스탑 (Let Profits Run — 수익 구간별 차등 트레일링폭)
        # 단계적 접근: 큰 수익일수록 더 넓은 트레일링으로 수익 극대화
        # - 0.6%~1.0% 수익: trailing_stop_pct 원래 값 (수익 확보 모드)
        # - 1.0%~2.0% 수익: trailing_stop_pct * 1.5 (상승 추세 따라가기)
        # - 2.0% 이상: trailing_stop_pct * 2.0 (큰 수익 극대화)
        min_profit_for_trailing = 0.60  # 왕복수수료 대비 3배 여유 (최소 이 정도 수익은 확보)
        if pnl_pct >= 2.0:
            dynamic_trail = self.config.trailing_stop_pct * 2.0
        elif pnl_pct >= 1.0:
            dynamic_trail = self.config.trailing_stop_pct * 1.5
        else:
            dynamic_trail = self.config.trailing_stop_pct

        if self.config.use_trailing_stop and pos.side == Side.BUY:
            if current_price > pos.highest_since_entry:
                pos.highest_since_entry = current_price
            trailing_stop = pos.highest_since_entry * (1 - dynamic_trail / 100)
            if current_price <= trailing_stop and pnl_pct > min_profit_for_trailing:
                return f"트레일링스탑 (피크 {pos.peak_pnl_pct:.2f}%→현재 {pnl_pct:+.2f}%, 폭 {dynamic_trail:.2f}%)"

        if self.config.use_trailing_stop and pos.side == Side.SELL:
            if current_price < pos.lowest_since_entry:
                pos.lowest_since_entry = current_price
            trailing_stop = pos.lowest_since_entry * (1 + dynamic_trail / 100)
            if current_price >= trailing_stop and pnl_pct > min_profit_for_trailing:
                return f"트레일링스탑 (피크 {pos.peak_pnl_pct:.2f}%→현재 {pnl_pct:+.2f}%, 폭 {dynamic_trail:.2f}%)"

        # Tier 4: 안전망 시간 — 수수료 손실 구간에서는 강제청산 금지
        # 수수료 구간(-0.25% ~ +0.25%)이면 stop_loss / take_profit이 결정할 때까지 보유
        hold_time = time.time() - pos.entry_time
        if hold_time >= self.config.max_hold_seconds:
            if pnl_pct <= -COMMISSION_FLOOR or pnl_pct >= COMMISSION_FLOOR:
                return f"안전망시간초과 ({hold_time:.0f}초 / 한도 {self.config.max_hold_seconds:.0f}s, {pnl_pct:+.2f}%)"
            # 수수료 손실 구간 → 2배까지 연장 (그래도 안 움직이면 청산)
            if hold_time >= self.config.max_hold_seconds * 2:
                return f"시간최종초과 ({hold_time:.0f}초, {pnl_pct:+.2f}%)"

        return None

    def check_soft_exit(self, pos: Position, current_price: int,
                         buf: 'TickBuffer', orderbook: dict) -> Optional[str]:
        """
        Tier 2: 진입 근거 소멸 청산

        진입 시점의 시그널 근거가 사라지면 청산.
        - volume_spike로 진입 → 거래량이 기준선으로 회귀하면 청산
        - trade_intensity로 진입 → 체결강도가 진입 대비 50% 이하 추락 시 청산
        - orderbook_imbalance로 진입 → 호가비가 1.0 이하로 역전 시 청산
        - bollinger_scalp로 진입 → 가격이 BB 중심선 복귀 시 청산
        - rsi_extreme으로 진입 → RSI 50 통과 시 청산

        단, 이익 중(pnl_pct > 0)에는 근거 소멸이라도 트레일링 스탑에 맡김
        (급하게 튕겨나가지 않도록 - 본전 보호는 이미 Tier 3에서 처리)
        """
        if not self.config.exit_on_signal_loss:
            return None
        if not pos.entry_strategies:
            return None

        # BUY 포지션 기준으로만 구현 (SELL은 시스템상 보유 청산만 하므로 해당 없음)
        if pos.side != Side.BUY:
            return None

        # 현재 손익
        pnl_pct = (current_price - pos.entry_price) / pos.entry_price * 100

        # ⚠️ 수수료 손실 구간(-0.25% ~ +0.25%)에서는 청산 금지 (수수료만 내고 나오기 방지)
        # 근거소멸 청산은 "확실한 손실 확대 방지용"으로만 작동
        COMMISSION_FLOOR = 0.25
        if pnl_pct > -COMMISSION_FLOOR:
            return None  # 손절선 근처까지 손실이어야 근거소멸 청산 의미 있음

        # 최소 보유 시간 (진입 직후 노이즈로 청산되는 것 방지): 8초
        if (time.time() - pos.entry_time) < 8.0:
            return None

        reasons = []
        alive_count = 0  # 아직 살아있는 근거 개수

        for strat in pos.entry_strategies:
            # volume_spike: 최근 거래량이 기준선 근처로 돌아왔나
            if strat == "volume_spike":
                volumes = buf.volumes(50) if buf else np.array([])
                if len(volumes) >= 5 and pos.entry_volume_baseline > 0:
                    recent = float(np.mean(volumes[-5:]))
                    ratio = recent / pos.entry_volume_baseline
                    if ratio <= self.config.signal_loss_volume_recovery:
                        reasons.append(f"거래량소멸({ratio:.1f}×)")
                    else:
                        alive_count += 1
                else:
                    alive_count += 1  # 데이터 부족 시 살아있는 것으로 간주

            # trade_intensity: 체결강도 진입 대비 추락
            elif strat == "trade_intensity":
                if buf and pos.entry_intensity > 0:
                    ticks = list(buf.ticks)[-self.config.intensity_window:]
                    if len(ticks) >= 5:
                        bv = sv = 0.0
                        for i in range(1, len(ticks)):
                            v = ticks[i].volume
                            if ticks[i].price > ticks[i - 1].price:
                                bv += v
                            elif ticks[i].price < ticks[i - 1].price:
                                sv += v
                            else:
                                bv += v * 0.5; sv += v * 0.5
                        cur_intensity = (bv / sv) if sv > 0 else 10.0
                        drop_ratio = cur_intensity / pos.entry_intensity
                        if drop_ratio <= self.config.signal_loss_intensity_drop:
                            reasons.append(f"체결강도소멸({cur_intensity:.1f}/{pos.entry_intensity:.1f})")
                        else:
                            alive_count += 1
                    else:
                        alive_count += 1
                else:
                    alive_count += 1

            # orderbook_imbalance: 호가비 1.0 이하로 역전
            elif strat == "orderbook_imbalance":
                if orderbook:
                    bid_qty = orderbook.get("bid_qty1", 0) or 0
                    ask_qty = orderbook.get("ask_qty1", 0) or 0
                    if ask_qty > 0:
                        cur_ratio = bid_qty / ask_qty
                        if cur_ratio <= self.config.signal_loss_imbalance_flip:
                            reasons.append(f"호가역전({cur_ratio:.2f})")
                        else:
                            alive_count += 1
                    else:
                        alive_count += 1
                else:
                    alive_count += 1

            # bollinger_scalp: BB 중심선 복귀 (매수는 하한에서 진입했으니 중심선 위로 올라오면 소멸)
            elif strat == "bollinger_scalp":
                if buf and pos.entry_bb_mid > 0:
                    if current_price >= pos.entry_bb_mid:
                        reasons.append(f"BB중심복귀({current_price}≥{int(pos.entry_bb_mid)})")
                    else:
                        alive_count += 1
                else:
                    alive_count += 1

            # rsi_extreme: 매수 진입 시 과매도였으니 50 통과 시 소멸
            elif strat == "rsi_extreme":
                if buf:
                    rsi_prices = buf.prices(self.config.rsi_period + 10)
                    if len(rsi_prices) >= self.config.rsi_period + 1:
                        try:
                            if HAS_TALIB:
                                r = talib.RSI(rsi_prices, timeperiod=self.config.rsi_period)
                                cur_rsi = float(r[-1]) if not np.isnan(r[-1]) else 50.0
                            else:
                                deltas = np.diff(rsi_prices)
                                gains = np.where(deltas > 0, deltas, 0)
                                losses = np.where(deltas < 0, -deltas, 0)
                                ag = np.mean(gains[-self.config.rsi_period:])
                                al = np.mean(losses[-self.config.rsi_period:])
                                cur_rsi = 100.0 if al == 0 else 100 - (100 / (1 + ag / al))
                            if cur_rsi >= 50.0:
                                reasons.append(f"RSI회복({cur_rsi:.0f})")
                            else:
                                alive_count += 1
                        except Exception:
                            alive_count += 1
                    else:
                        alive_count += 1
                else:
                    alive_count += 1

            # 기타 전략 (tick_momentum, vwap_deviation, ema_crossover, tick_acceleration):
            # 별도 진입 메타 저장 안 함 → 살아있는 것으로 간주
            else:
                alive_count += 1

        # 모든 진입 근거가 소멸됐을 때만 청산 (하나라도 살아있으면 보유 유지)
        if reasons and alive_count == 0:
            return f"근거소멸 ({', '.join(reasons)})"

        return None

    def record_trade(self, net_pnl: float):
        self.daily_pnl += net_pnl
        self.daily_trades += 1
        self.last_trade_time = time.time()
        self._recent_pnls.append(net_pnl)
        self._adaptive_tune()

    def reset_daily(self):
        self.daily_pnl = 0.0
        self.daily_trades = 0
        self._recent_pnls = []
        self._consecutive_losses = 0

    # ── 룰 기반 실시간 파라미터 미세 조정 ──

    def _adaptive_tune(self):
        """
        최근 거래 성과에 따라 파라미터를 자동 미세 조정 (룰 기반, API 호출 없음)

        규칙:
        1. 연속 3패 → 손절폭 축소, 쿨다운 증가 (방어 모드)
        2. 연속 3승 → 원래 설정 복원 (또는 약간 공격적)
        3. 일일 손실이 한도의 50% 도달 → 포지션 수 축소
        4. 승률 기반 min_consensus 조정
        """
        if not self._recent_pnls:
            return

        # 원래 설정 스냅샷 저장 (최초 1회)
        if self._original_config_snapshot is None:
            self._original_config_snapshot = {
                "stop_loss_pct": self.config.stop_loss_pct,
                "cooldown_seconds": self.config.cooldown_seconds,
                "max_position_count": self.config.max_position_count,
                "max_investment_per_trade": self.config.max_investment_per_trade,
            }

        last_pnl = self._recent_pnls[-1]

        # 연속 손실/승리 카운트
        if last_pnl <= 0:
            self._consecutive_losses += 1
        else:
            self._consecutive_losses = 0

        orig = self._original_config_snapshot

        # 방어모드 제거: 잃을수록 거래 축소하면 복구 불가능
        # max_daily_loss (일일 손실 한도)가 최종 차단선 역할만 수행
        # 연속 손실은 전략/청산 조건에서 해결해야 함 (파라미터 축소로 회피 X)
        pass


# ═══════════════════════════════════════════════════════
#  Stock Scanner (종목 자동 검색)
# ═══════════════════════════════════════════════════════

class StockScanner:
    """실시간 데이터 기반 스캘핑 종목 자동 검색"""

    def __init__(self, config: AutoScalpConfig):
        self.config = config
        self.last_scan_time: float = 0
        self.current_targets: List[str] = []
        self.stock_scores: Dict[str, dict] = {}

    def needs_scan(self) -> bool:
        return time.time() - self.last_scan_time > self.config.scan_interval_seconds

    def scan(self, kiwoom) -> List[str]:
        """키움 API를 통한 종목 스캔"""
        self.last_scan_time = time.time()

        try:
            # 거래량 상위 종목 조회 (ka10030)
            stocks = kiwoom.get_top_volume_stocks()
            if not stocks:
                logger.warning("거래량 상위 종목 조회 실패")
                return self.current_targets

            candidates = []
            for s in stocks:
                raw_code = s.get("stk_cd", "")
                code = raw_code.split("_")[0]  # Remove _AL, _KQ etc. suffixes
                raw_price = str(s.get("cur_prc", "0")).replace(",", "").replace("+", "").replace("-", "")
                price = int(raw_price or "0")
                raw_vol = str(s.get("trde_qty", s.get("trd_qty", "0"))).replace(",", "")
                volume = int(raw_vol or "0")
                raw_pct = str(s.get("flu_rt", s.get("change_pct", "0"))).replace("+", "")
                change_pct = float(raw_pct or "0")

                # 필터링
                if not code or price <= 0:
                    continue
                if price < self.config.min_price or price > self.config.max_price:
                    continue
                if volume < self.config.min_volume:
                    continue
                if abs(change_pct) > self.config.max_volatility_pct:
                    continue

                # 코드 유효성 (6자리 숫자만)
                if not code.isdigit() or len(code) != 6:
                    continue

                # ETF/ETN 제외 (KODEX, TIGER, KOSEF 등은 종목명으로 판별)
                stk_nm = s.get("stk_nm", "")
                etf_keywords = ["KODEX", "TIGER", "KOSEF", "KBSTAR", "HANARO", "SOL", "ACE", "ARIRANG"]
                if any(kw in stk_nm.upper() for kw in etf_keywords):
                    continue

                # 점수 계산
                score = self._score_stock(code, price, volume, change_pct)
                candidates.append((code, score, s.get("stk_nm", code)))

            # 점수 기준 정렬
            candidates.sort(key=lambda x: x[1], reverse=True)

            # Brain 데이터로 룰 기반 종목 필터링 (과거 성과 반영)
            try:
                brain_data = trade_brain.brain if trade_brain else {}
                price_scores = brain_data.get("price_bracket_scores", {})
                if price_scores:
                    filtered = []
                    for code, score, name in candidates:
                        # 해당 가격대의 과거 성과가 극히 나쁘면 감점
                        raw_price = int(str(next(
                            (s.get("cur_prc", "0") for s in stocks
                             if s.get("stk_cd", "").split("_")[0] == code),
                            "0"
                        )).replace(",", "").replace("+", "").replace("-", "") or "0")
                        bracket = f"{(raw_price // 10000) * 10000}-{(raw_price // 10000 + 1) * 10000}"
                        bracket_data = price_scores.get(bracket, {})
                        tc = bracket_data.get("trade_count", 0)
                        if tc >= 5:
                            win_rate = bracket_data.get("wins", 0) / tc
                            if win_rate < 0.2:
                                score *= 0.5  # 승률 20% 미만 가격대 감점
                        filtered.append((code, score, name))
                    candidates = sorted(filtered, key=lambda x: x[1], reverse=True)
            except Exception as e:
                logger.warning(f"[Brain필터] 스킵: {e}")

            top_n = candidates[:self.config.max_target_stocks]

            new_targets = [c[0] for c in top_n]
            for code, score, name in top_n:
                self.stock_scores[code] = {
                    "name": name, "score": score,
                    "selected_at": datetime.now().strftime("%H:%M:%S")
                }

            logger.info(f"종목 스캔 완료: {len(stocks)}개 중 {len(new_targets)}개 선정")
            for code, score, name in top_n:
                logger.info(f"  {code} {name}: score={score:.2f}")

            self.current_targets = new_targets
            return new_targets

        except Exception as e:
            logger.error(f"종목 스캔 오류: {e}")
            return self.current_targets

    def _score_stock(self, code: str, price: int, volume: int, change_pct: float) -> float:
        """스캘핑 적합도 점수 (0~100) - 7개 기준 종합 평가"""
        # 1. 거래대금 (25%) - 최소 기준 미달 즉시 탈락
        trade_value = price * volume
        min_tv = self.config.min_trade_value if hasattr(self.config, 'min_trade_value') else 5_000_000_000
        if trade_value < min_tv:
            return 0

        score = 0.0
        tv_score = min(100, np.log10(max(trade_value, 1)) / np.log10(500_000_000_000) * 100)
        score += tv_score * 0.25

        # 2. 변동성 (20%) - 0.8~3% 벨커브
        ideal_vol = 1.5
        vol_diff = abs(abs(change_pct) - ideal_vol)
        volatility_score = max(0, 100 - vol_diff * 30)
        score += volatility_score * 0.20

        # 3. 호가 스프레드율 (15%) - 0.3% 초과 탈락
        tick = get_tick_size(price)
        spread_pct = tick / price * 100
        max_sp = self.config.max_spread_pct if hasattr(self.config, 'max_spread_pct') else 0.25
        if spread_pct > max_sp * 1.5:
            return 0
        spread_score = max(0, 100 - spread_pct / max_sp * 100)
        score += spread_score * 0.15

        # 4. 체결빈도 (15%) - WS 실시간 데이터 기반
        from services.kiwoom_ws import kiwoom_ws_manager
        tick_freq_score = 50  # 기본값
        exec_store = getattr(kiwoom_ws_manager, 'execution_data', {})
        tick_data = exec_store.get(code, {})
        if tick_data:
            # execution_data에서 최근 체결 건수 추정
            tick_freq_score = min(100, volume / 100000 * 20)
        score += tick_freq_score * 0.15

        # 5. 시간대 유동성 (10%)
        time_mult = self._get_time_multiplier()
        time_score = time_mult * 100
        score += time_score * 0.10

        # 6. 모멘텀 (10%) - 적당한 추세
        momentum_score = min(100, abs(change_pct) * 50)
        score += momentum_score * 0.10

        # 7. Brain 과거 성과 (5%)
        brain_score = 50  # 기본값
        try:
            brain_data = trade_brain.brain if trade_brain else {}
            price_brackets = brain_data.get("price_bracket_scores", {})
            if price < 5000:
                bracket = "~5천"
            elif price < 10000:
                bracket = "5천~1만"
            elif price < 30000:
                bracket = "1만~3만"
            elif price < 50000:
                bracket = "3만~5만"
            else:
                bracket = "5만~"
            bd = price_brackets.get(bracket, {})
            tc = bd.get("count", 0)
            if tc >= 5:
                win_rate = bd.get("wins", 0) / tc
                brain_score = win_rate * 100
        except Exception:
            pass
        score += brain_score * 0.05

        # 작전주/테마주 감점
        if self._is_suspicious(code, price, volume, change_pct):
            score *= 0.8

        return round(score, 2)

    def _is_suspicious(self, code: str, price: int, volume: int, change_pct: float) -> bool:
        """작전주/테마주 의심 종목 감지"""
        # 상한가/하한가 근접 (등락률 +-25% 이상)
        if abs(change_pct) > 25:
            return True
        # 극단적 저가주 (1천원 미만) + 높은 변동성
        if price < 1000 and abs(change_pct) > 10:
            return True
        return False

    @staticmethod
    def _get_time_multiplier() -> float:
        """시간대별 유동성 가중치"""
        now = datetime.now().time()
        if dtime(9, 10) <= now < dtime(10, 0):
            return 1.2  # 최활발
        elif dtime(10, 0) <= now < dtime(11, 30):
            return 1.0
        elif dtime(11, 30) <= now < dtime(13, 0):
            return 0.7  # 점심
        elif dtime(13, 0) <= now < dtime(14, 30):
            return 0.9
        else:
            return 0.6  # 마감 접근

    def should_rotate(self, code: str, trade_results: List[TradeResult]) -> bool:
        """성과 기반 종목 교체 판단"""
        code_trades = [t for t in trade_results if t.code == code]
        if len(code_trades) < self.config.min_rotation_trades:
            return False

        recent = code_trades[-self.config.min_rotation_trades:]
        avg_pnl_pct = np.mean([t.pnl_pct for t in recent])

        if avg_pnl_pct < self.config.rotation_loss_threshold:
            logger.info(f"{code} 종목 교체 대상: 평균수익률 {avg_pnl_pct:.2f}%")
            return True
        return False


# ═══════════════════════════════════════════════════════
#  Auto Scalping System (메인 엔진)
# ═══════════════════════════════════════════════════════

class AutoScalpingSystem:
    """
    완전 자동 스캘핑 시스템

    Lifecycle:
    1. start() → 엔진 시작
    2. scan_and_subscribe() → 종목 검색 + WebSocket 구독
    3. on_tick() → 틱 수신 시 전략 평가 → 자동 매수/매도
    4. _monitor_loop() → 포지션 모니터링 (손절/익절/시간초과)
    5. _rotation_loop() → 종목 성과 평가 → 자동 교체
    6. stop() → 전체 포지션 청산 + 엔진 중지
    """

    def __init__(self, config: AutoScalpConfig = None):
        self.config = config or AutoScalpConfig.load_from_file()
        self.strategy = StrategyEngine(self.config)
        self.risk = RiskManager(self.config)
        self.scanner = StockScanner(self.config)

        self.state = EngineState.IDLE
        self.running = False

        # 활성 프리셋 이름
        active = preset_manager.get_active()
        self.active_preset_name = active.name if active else "aggressive"

        # Data
        self.tick_buffers: Dict[str, TickBuffer] = {}
        self.positions: Dict[str, Position] = {}
        self.trade_history: List[TradeResult] = []
        self.signal_log: deque = deque(maxlen=100)

        # Stats
        self.stats = {
            "started_at": None,
            "total_signals": 0,
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "total_gross_pnl": 0.0,
            "total_net_pnl": 0.0,
            "total_commission": 0.0,
            # 실제 거래 금액 추적 (수수료 제외 전 총액)
            "total_buy_quantity": 0,   # 매수 체결 수량 누적
            "total_buy_amount": 0.0,   # 매수 체결 금액 누적 (원)
            "total_sell_amount": 0.0,  # 매도 체결 금액 누적 (원)
        }

        # Tasks
        self._monitor_task = None
        self._rotation_task = None
        self._rescan_task = None
        self._market_open_task = None  # 09:00 자동 시작 스케줄러

        # 비동기 start 시퀀스의 오류 추적 (라우터에서 조회)
        self._startup_error: Optional[str] = None

        # 잔고 캐시 (매 틱마다 kt00017/kt00018 폭주 방지)
        self._balance_cache: Optional[dict] = None
        self._balance_cache_time: float = 0.0
        self._balance_cache_ttl: float = 15.0  # 15초 캐시

        # 예수금 부족 전역 쿨다운 (돈 없으면 잠시 진입 자체 중단)
        self._insufficient_cash_until: float = 0.0
        self._insufficient_cash_cooldown: float = 60.0  # 60초간 진입 중단

    # ── Lifecycle ──

    async def start(self):
        """엔진 시작"""
        if self.running:
            return {"success": True, "message": "이미 실행 중",
                    "targets": self.scanner.current_targets}

        self.running = True
        self.state = EngineState.SCANNING
        self.risk.reset_daily()
        self.stats["started_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # WS 재연결 후 자동 재구독 콜백 등록 (엔진이 살아있는 동안 유지)
        try:
            from services.kiwoom_ws import kiwoom_ws_manager
            kiwoom_ws_manager.register_post_login_callback(self._resubscribe_targets_after_reconnect)
        except Exception as e:
            logger.warning(f"[WS 재구독 콜백 등록 실패] {e}")

        # 실계좌 보유 종목 동기화 (유령 포지션 방지)
        await self._sync_account_holdings()

        # 종목 검색
        await self._do_scan()

        # 백그라운드 루프 시작
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        self._rotation_task = asyncio.create_task(self._rotation_loop())
        self._rescan_task = asyncio.create_task(self._periodic_rescan_loop())

        self.state = EngineState.TRADING
        logger.info(f"AutoScalper 시작: 감시 종목 {self.scanner.current_targets}")
        return {"success": True, "message": "자동 스캘핑 시작",
                "targets": self.scanner.current_targets}

    async def _sync_account_holdings(self):
        """실계좌 보유 종목을 포지션으로 등록 (유령 포지션 방지)"""
        try:
            from services.kiwoom_provider import kiwoom
            loop = asyncio.get_event_loop()
            balance = await loop.run_in_executor(None, kiwoom.get_account_balance)
            if not balance or not isinstance(balance, dict):
                return
            holdings = balance.get("holdings", [])
            for h in holdings:
                code = h.get("code", "")
                qty = h.get("quantity", 0)
                price = h.get("avg_price", 0) or h.get("current_price", 0)
                if code and qty > 0 and code not in self.positions:
                    # 기존에 추적 안 된 포지션을 Position으로 등록
                    pos = Position(
                        code=code, side=Side.BUY,
                        entry_price=price, quantity=qty,
                        entry_time=time.time(),
                        order_no="sync",
                        stop_loss=price * (1 - self.config.stop_loss_pct / 100),
                        take_profit=price * (1 + self.config.take_profit_pct / 100),
                    )
                    self.positions[code] = pos
                    logger.info(f"[계좌동기화] {code} {qty}주 @ {price}원 → 포지션 등록")
        except Exception as e:
            logger.warning(f"[계좌동기화] 실패 (무시): {e}")

    async def stop(self):
        """엔진 중지 (모든 포지션 청산)"""
        self.running = False
        self.state = EngineState.STOPPED

        # 열린 포지션 강제 청산
        for code in list(self.positions.keys()):
            buf = self.tick_buffers.get(code)
            if buf and buf.latest:
                self._close_position(code, buf.latest.price, "엔진 중지")

        # 백그라운드 태스크 취소
        for task in [self._monitor_task, self._rotation_task, self._rescan_task]:
            if task and not task.done():
                task.cancel()

        logger.info("AutoScalper 중지")
        return {"success": True, "message": "자동 스캘핑 중지"}

    # ── Tick Processing ──

    def on_tick(self, tick: Tick):
        """실시간 틱 수신 → 전략 평가 → 자동 매매"""
        if not self.running or self.state != EngineState.TRADING:
            return

        code = tick.code

        # 버퍼에 추가
        if code not in self.tick_buffers:
            self.tick_buffers[code] = TickBuffer()
        self.tick_buffers[code].add(tick)
        buf = self.tick_buffers[code]

        # 1. 기존 포지션 청산 체크
        if code in self.positions:
            pos = self.positions[code]
            # 트레일링 스탑 업데이트
            if pos.side == Side.BUY and tick.price > pos.highest_since_entry:
                pos.highest_since_entry = tick.price
            if pos.side == Side.SELL and tick.price < pos.lowest_since_entry:
                pos.lowest_since_entry = tick.price

            # Tier 1 (하드룰) + Tier 3 (본전 보호) + Tier 4 (안전망 시간) 통합 체크
            exit_reason = self.risk.check_exit(pos, tick.price)
            if exit_reason:
                self._close_position(code, tick.price, exit_reason)
                return

            # Tier 2: 진입 근거 소멸 청산 (소프트)
            from services.kiwoom_ws import kiwoom_ws_manager as _ws_for_exit
            ob_for_exit = _ws_for_exit.orderbook_data.get(code, {})
            soft_reason = self.risk.check_soft_exit(pos, tick.price, buf, ob_for_exit)
            if soft_reason:
                self._close_position(code, tick.price, soft_reason)
                return

        # 2. 이미 포지션이 있으면 새 진입 안 함
        if code in self.positions:
            return

        # 2.5. 예수금 부족 전역 쿨다운 — 잔고 없으면 신호/전략 평가까지 전부 스킵 (이벤트 루프 보호)
        if time.time() < self._insufficient_cash_until:
            return

        # 3. 진입 가능 여부 확인
        can_open, reason = self.risk.can_open(self.positions)
        if not can_open:
            return

        # 4. 전략 평가
        from services.kiwoom_ws import kiwoom_ws_manager
        orderbook = kiwoom_ws_manager.orderbook_data.get(code, {})

        signals = self.strategy.evaluate(code, buf, orderbook)
        if not signals:
            return

        self.stats["total_signals"] += len(signals)

        # 5. 컨센서스 확인 (추세 필터 포함)
        consensus = self.strategy.get_consensus(signals, buf)
        if not consensus:
            # 시그널은 있지만 합의 미달
            for sig in signals:
                signal_data = {
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "code": code,
                    "side": sig["side"].value,
                    "strategy": sig["strategy"],
                    "reason": sig["reason"],
                    "action": "no_consensus"
                }
                self.signal_log.append(signal_data)
                try:
                    trade_journal.record_signal(signal_data, engine_type="auto_scalper")
                except Exception:
                    pass
            return

        # 6. 룰 기반 진입 필터 + Brain 학습 활용 (개선판)
        try:
            brain_data = trade_brain.brain if trade_brain else {}
            strategy_name = consensus.get("strategy", "")
            strategy_perf = brain_data.get("strategy_scores", {}).get(strategy_name, {})
            tc = strategy_perf.get("trade_count", 0)
            strategy_count = len(consensus.get("strategy", "").split(","))  # 컨센서스 포함 전략 수

            # ── (A) 검증된 우수 조합은 무조건 진입 허용 (승률 50% 이상 & 5건 이상)
            bypass_filter = False
            if tc >= 5:
                win_rate = strategy_perf.get("wins", 0) / tc
                if win_rate >= 0.50:
                    total_pnl = strategy_perf.get("total_pnl", 0)
                    logger.info(f"[우수조합] {strategy_name} 승률 {win_rate:.0%} "
                                f"누적 {total_pnl:+,.0f}원 ({tc}건) → 필터 통과")
                    bypass_filter = True

            # ── (B) 표본 충분 시 저승률 거부 (10건으로 완화)
            if not bypass_filter and tc >= 10:
                win_rate = strategy_perf.get("wins", 0) / tc
                recent_pnls = strategy_perf.get("recent_pnls", [])[-10:]
                recent_loss_count = sum(1 for p in recent_pnls if p <= 0)
                total_pnl = strategy_perf.get("total_pnl", 0)

                # 단일 전략이고 승률 30% 미만이면 거부 (복수 조합은 서로 보완 가능성)
                single_bad = (strategy_count == 1 and win_rate < 0.30)
                multi_bad = (strategy_count >= 2 and win_rate < 0.20)
                losing_streak = (recent_loss_count >= 8)
                chronic_loss = (total_pnl < -3000 and win_rate < 0.35)

                if single_bad or multi_bad or losing_streak or chronic_loss:
                    reject_reason = (f"승률 {win_rate:.0%}, 최근10건 중 {recent_loss_count}패, "
                                     f"누적PnL {total_pnl:+,.0f} (표본 {tc}건)")
                    self.signal_log.append({
                        "time": datetime.now().strftime("%H:%M:%S"),
                        "code": code,
                        "side": consensus["side"].value,
                        "strategy": consensus["strategy"],
                        "reason": consensus["reason"],
                        "action": f"RULE_REJECT: {reject_reason}",
                    })
                    logger.info(f"[룰거부] {code} {consensus['strategy']} - {reject_reason}")
                    return

            # ── (C) 더 우수한 조합이 활성 중이면 저성능 단일 전략 진입 보류
            # 현재 시그널에 어떤 전략이 포함되어 있는지 확인
            if not bypass_filter and strategy_count == 1:
                # 최근 10건 승률이 1건만 낮으면 '더 나은 조합 대기' 모드
                all_scores = brain_data.get("strategy_scores", {})
                better_combo_exists = False
                for sname, perf in all_scores.items():
                    if len(sname.split(",")) >= 2 and perf.get("trade_count", 0) >= 3:
                        pwr = perf.get("wins", 0) / perf.get("trade_count", 1)
                        if pwr >= 0.5:
                            # 이 조합의 전략들이 현재 시그널에 일부 포함돼있으면 기다림
                            combo_strats = set(sname.replace("consensus(", "").replace(")", "").split(","))
                            cur_strats = set(strategy_name.replace("consensus(", "").replace(")", "").split(","))
                            if cur_strats & combo_strats:
                                better_combo_exists = True
                                break
                if better_combo_exists and tc >= 5:
                    cur_wr = strategy_perf.get("wins", 0) / tc
                    if cur_wr < 0.4:
                        logger.info(f"[조합대기] {code} 단일 {strategy_name} 승률 {cur_wr:.0%} "
                                    f"→ 더 나은 조합 대기")
                        return

            # ── (D) 시간대 필터
            current_hour = datetime.now().strftime("%H")
            time_scores = brain_data.get("time_scores", {})
            time_perf = time_scores.get(current_hour, {})
            time_tc = time_perf.get("trade_count", 0)
            if time_tc >= 20:
                time_wr = time_perf.get("wins", 0) / time_tc
                if time_wr < 0.20:
                    logger.info(f"[시간대거부] {current_hour}시 승률 {time_wr:.0%} ({time_tc}건) → 진입 거부")
                    return

        except Exception as e:
            logger.warning(f"[Brain필터] 스킵: {e}")

        # 6-2. 스프레드 검증: 호가 스프레드가 익절 대비 너무 넓으면 거부
        from services.kiwoom_ws import kiwoom_ws_manager as _ws
        ob = _ws.orderbook_data.get(code, {})
        if ob:
            bid1 = ob.get("bid1", 0) or 0
            ask1 = ob.get("ask1", 0) or 0
            if bid1 > 0 and ask1 > 0:
                spread_pct = (ask1 - bid1) / bid1 * 100
                # 스프레드가 익절 목표의 40% 이상이면 수익 내기 어려움
                if spread_pct > self.config.take_profit_pct * 0.4:
                    logger.info(f"[스프레드거부] {code} 스프레드 {spread_pct:.2f}% > TP의 40%")
                    return

        # 7. 진입 실행
        entry_signal = {
            "time": datetime.now().strftime("%H:%M:%S"),
            "code": code,
            "side": consensus["side"].value,
            "strategy": consensus["strategy"],
            "reason": consensus["reason"],
            "action": "ENTRY",
        }
        self.signal_log.append(entry_signal)
        try:
            trade_journal.record_signal(entry_signal, engine_type="auto_scalper")
        except Exception:
            pass
        self._open_position(code, consensus)

    # ── Position Management ──

    # ── WebSocket 재구독 (재연결 복구용) ──

    async def _resubscribe_targets_after_reconnect(self):
        """WS LOGIN 성공 시 호출 — 엔진이 감시 중인 종목을 자동 재구독.
        재연결 직후 subscribed_codes가 비워지므로, 진입/청산 신호를 받으려면 반드시 재구독 필요.
        """
        if not self.running:
            return
        try:
            from services.kiwoom_ws import kiwoom_ws_manager
            targets = list(self.scanner.current_targets or [])
            if not targets:
                logger.info("[WS 재구독] 감시 종목 없음 — 건너뜀")
                return
            logger.info(f"[WS 재구독] 재연결 감지 → {len(targets)}개 종목 재구독 시도")
            await kiwoom_ws_manager.subscribe_stocks(targets, append=False)
            logger.info(f"[WS 재구독] 완료: {targets}")
        except Exception as e:
            logger.error(f"[WS 재구독] 실패: {e}")

    # ── 잔고 캐시 (API 폭주 방지) ──

    def _get_cached_balance(self) -> Optional[dict]:
        """잔고 조회 캐시 (TTL=15초). kt00017/kt00018 동기 HTTP가 매 틱마다 이벤트 루프를 막는 문제 방지."""
        from services.kiwoom_provider import kiwoom
        now = time.time()
        if self._balance_cache is not None and (now - self._balance_cache_time) < self._balance_cache_ttl:
            return self._balance_cache
        try:
            balance = kiwoom.get_account_balance()
            if isinstance(balance, dict):
                self._balance_cache = balance
                self._balance_cache_time = now
                return balance
        except Exception as e:
            logger.warning(f"[잔고 캐시 조회 실패] {e}")
        # 실패 시 마지막 캐시라도 반환 (None 회피)
        return self._balance_cache

    def _invalidate_balance_cache(self):
        """체결/청산 직후 즉시 다음 조회에서 최신 값을 가져오도록 캐시 무효화"""
        self._balance_cache = None
        self._balance_cache_time = 0.0

    # ── 진입 시그널 파싱/스냅샷 (Tier 2 청산용) ──

    @staticmethod
    def _parse_consensus_strategies(strategy_label: str) -> list:
        """'consensus(volume_spike,trade_intensity)' → ['volume_spike','trade_intensity']"""
        if not strategy_label:
            return []
        if "consensus(" in strategy_label:
            inner = strategy_label.split("consensus(", 1)[1].rstrip(")")
            return [s.strip() for s in inner.split(",") if s.strip()]
        return [strategy_label.strip()]

    def _snapshot_entry_context(self, code: str, buf: TickBuffer) -> dict:
        """진입 시점의 각 전략 지표값을 스냅샷 — 나중에 '근거 소멸' 판정에 사용"""
        from services.kiwoom_ws import kiwoom_ws_manager
        ob = kiwoom_ws_manager.orderbook_data.get(code, {}) or {}

        # 거래량 기준선 (volume_spike 판정용): 최근 50틱 중 앞부분 45틱 평균
        volumes = buf.volumes(50)
        if len(volumes) >= 20:
            volume_baseline = float(np.mean(volumes[:-5])) if len(volumes) > 5 else float(np.mean(volumes))
        else:
            volume_baseline = 0.0

        # 체결강도 (trade_intensity 판정용)
        intensity = 1.0
        ticks = list(buf.ticks)[-self.config.intensity_window:]
        if len(ticks) >= 5:
            bv = sv = 0.0
            for i in range(1, len(ticks)):
                v = ticks[i].volume
                if ticks[i].price > ticks[i - 1].price:
                    bv += v
                elif ticks[i].price < ticks[i - 1].price:
                    sv += v
                else:
                    bv += v * 0.5
                    sv += v * 0.5
            intensity = (bv / sv) if sv > 0 else 10.0

        # 호가비 (orderbook_imbalance 판정용)
        bid_qty = ob.get("bid_qty1", 0) or 0
        ask_qty = ob.get("ask_qty1", 0) or 0
        imbalance_ratio = (bid_qty / ask_qty) if ask_qty > 0 else 1.0

        # BB 중심선 (bollinger_scalp 판정용)
        bb_prices = buf.prices(self.config.bb_window)
        bb_mid = float(np.mean(bb_prices)) if len(bb_prices) >= self.config.bb_window else 0.0

        # RSI (rsi_extreme 판정용)
        rsi_val = 50.0
        rsi_prices = buf.prices(self.config.rsi_period + 10)
        if len(rsi_prices) >= self.config.rsi_period + 1:
            try:
                if HAS_TALIB:
                    r = talib.RSI(rsi_prices, timeperiod=self.config.rsi_period)
                    rsi_val = float(r[-1]) if not np.isnan(r[-1]) else 50.0
                else:
                    deltas = np.diff(rsi_prices)
                    gains = np.where(deltas > 0, deltas, 0)
                    losses = np.where(deltas < 0, -deltas, 0)
                    ag = np.mean(gains[-self.config.rsi_period:])
                    al = np.mean(losses[-self.config.rsi_period:])
                    rsi_val = 100.0 if al == 0 else 100 - (100 / (1 + ag / al))
            except Exception:
                rsi_val = 50.0

        return {
            "volume_baseline": volume_baseline,
            "intensity": intensity,
            "imbalance_ratio": imbalance_ratio,
            "bb_mid": bb_mid,
            "rsi": rsi_val,
        }

    def _open_position(self, code: str, consensus: dict):
        """포지션 진입 (룰 기반)"""
        from services.kiwoom_provider import kiwoom

        buf = self.tick_buffers.get(code)
        if not buf or not buf.latest:
            return

        price = buf.latest.price
        if price <= 0:
            logger.warning(f"[진입 거부] {code} 가격이 0 또는 음수")
            return

        side = consensus["side"]

        # SELL 시그널: 보유 포지션이 없으면 공매도 불가 → 무시
        if side == Side.SELL and code not in self.positions:
            return

        max_invest = self.config.max_investment_per_trade

        # 수량 계산 (최대 투자금 기반)
        quantity = min(
            self.config.order_quantity,
            max(1, max_invest // price)
        )

        # 잔고 기반 수량 재조정 (부족 시 가능한 최대 수량으로 축소)
        # 캐시된 잔고 사용 (매 틱마다 kt00017/kt00018 폭주 방지)
        try:
            balance = self._get_cached_balance()
            if isinstance(balance, dict):
                available_cash = int(balance.get("cash", 0) or 0)
            else:
                available_cash = 0
            if available_cash > 0 and side == Side.BUY:
                # 수수료+세금 여유까지 감안해 95% 상한
                max_by_balance = max(0, int(available_cash * 0.95) // price)
                if max_by_balance <= 0:
                    # 예수금 1주 미만 → 전역 쿨다운으로 다른 종목 진입도 잠시 중단
                    self._insufficient_cash_until = time.time() + self._insufficient_cash_cooldown
                    logger.warning(
                        f"[진입 거부] {code} 예수금({available_cash:,}원)이 1주({price:,}원) 금액 미만 "
                        f"→ 전역 쿨다운 {self._insufficient_cash_cooldown:.0f}초"
                    )
                    return
                if max_by_balance < quantity:
                    logger.info(f"[수량 축소] {code} 요청 {quantity}주 → 예수금 한도 {max_by_balance}주 (예수금 {available_cash:,}원)")
                quantity = min(quantity, max_by_balance)
        except Exception as e:
            logger.warning(f"[잔고 조회 실패] {code}: {e} → 기존 수량 유지")

        if quantity <= 0:
            logger.warning(f"[진입 거부] {code} 잔고 부족으로 수량 0")
            return

        # 수수료 대비 수익성 사전 검증
        tp_pct = self.config.take_profit_pct
        trade_amount = price * quantity
        round_trip_fee = estimate_commission(trade_amount, False) + estimate_commission(trade_amount, True)
        min_profit_needed = round_trip_fee * 2
        expected_profit = trade_amount * (tp_pct / 100)
        if expected_profit < min_profit_needed:
            logger.info(f"[진입 거부] {code} 기대수익({expected_profit:,.0f}원) < 최소요구({min_profit_needed:,.0f}원)")
            return

        # 주문 실행
        result = kiwoom.place_order(
            code=code,
            order_type=side.value,
            quantity=quantity,
            price=0 if self.config.price_type == "market" else price,
            price_type=self.config.price_type,
        )

        if result.get("success"):
            order_no = result.get("order_no", "")

            # 체결 발생 → 잔고 캐시 무효화 (다음 조회 시 최신 예수금 반영)
            self._invalidate_balance_cache()

            # 실제 체결 수량/체결가 조회 (요청치가 아닌 실제 체결값을 기록)
            actual_qty = quantity
            actual_price = price
            fill_status = "requested"
            try:
                fill = kiwoom.get_order_fill(order_no, max_attempts=3, sleep_sec=0.4)
                if fill:
                    actual_qty = int(fill.get("filled_quantity", 0) or 0)
                    actual_price = float(fill.get("filled_price", 0) or 0)
                    fill_status = fill.get("status", "filled")
                    if actual_qty <= 0 or actual_price <= 0:
                        # 체결 데이터가 비어있으면 요청치 유지
                        actual_qty = quantity
                        actual_price = price
                        fill_status = "pending"
                else:
                    fill_status = "pending"
            except Exception as e:
                logger.warning(f"[체결 조회 실패] {code}: {e} → 요청 수량/가격으로 기록")

            if actual_qty <= 0:
                logger.warning(f"[진입 실패] {code} 체결수량 0 - 포지션 미생성")
                return

            # AI 조정값이 있으면 포지션별 SL/TP 적용
            sl_pct = self.config.stop_loss_pct
            tp_pct = self.config.take_profit_pct

            # 안전 범위 강제
            sl_pct = max(0.2, min(2.0, sl_pct))
            tp_pct = max(0.3, min(5.0, tp_pct))

            if side == Side.BUY:
                sl = align_price(int(actual_price * (1 - sl_pct / 100)), "down")
                tp = align_price(int(actual_price * (1 + tp_pct / 100)), "up")
            else:
                sl = align_price(int(actual_price * (1 + sl_pct / 100)), "up")
                tp = align_price(int(actual_price * (1 - tp_pct / 100)), "down")

            # 진입 시점 메타 수집 (Tier 2 근거 소멸 청산용)
            entry_strategies = self._parse_consensus_strategies(consensus.get("strategy", ""))
            meta = self._snapshot_entry_context(code, buf)

            pos = Position(
                code=code, side=side, entry_price=actual_price,
                quantity=actual_qty, entry_time=time.time(),
                order_no=order_no,
                stop_loss=sl, take_profit=tp,
                highest_since_entry=actual_price,
                lowest_since_entry=actual_price,
                strategy=consensus["strategy"],
                entry_strategies=entry_strategies,
                entry_volume_baseline=meta["volume_baseline"],
                entry_intensity=meta["intensity"],
                entry_imbalance_ratio=meta["imbalance_ratio"],
                entry_bb_mid=meta["bb_mid"],
                entry_rsi=meta["rsi"],
                peak_pnl_pct=0.0,
            )
            self.positions[code] = pos
            self.stats["total_trades"] += 1

            logger.info(f"[진입] {side.value.upper()} {code} "
                        f"요청={quantity}주@{price:,} → 체결={actual_qty}주@{actual_price:,.0f} ({fill_status}) "
                        f"SL={sl:,} TP={tp:,} "
                        f"전략={consensus['strategy']}")
        else:
            logger.warning(f"주문 실패: {code} - {result.get('message')}")

    def _close_position(self, code: str, exit_price: int, reason: str):
        """포지션 청산"""
        from services.kiwoom_provider import kiwoom

        pos = self.positions.get(code)
        if not pos:
            return

        close_side = "sell" if pos.side == Side.BUY else "buy"
        result = kiwoom.place_order(
            code=code,
            order_type=close_side,
            quantity=pos.quantity,
            price=0,
            price_type="market",
        )

        # 청산 체결 → 잔고 캐시 무효화 + 예수금 부족 쿨다운 해제 (회수된 현금 반영)
        self._invalidate_balance_cache()
        self._insufficient_cash_until = 0.0

        # 실제 체결가/체결수량 조회 (실패하면 모니터링 가격/보유수량 사용)
        actual_exit_price = exit_price
        actual_close_qty = pos.quantity
        try:
            close_order_no = result.get("order_no", "") if isinstance(result, dict) else ""
            if close_order_no:
                fill = kiwoom.get_order_fill(close_order_no, max_attempts=3, sleep_sec=0.4)
                if fill:
                    fq = int(fill.get("filled_quantity", 0) or 0)
                    fp = float(fill.get("filled_price", 0) or 0)
                    if fq > 0 and fp > 0:
                        actual_close_qty = min(pos.quantity, fq)
                        actual_exit_price = fp
        except Exception as e:
            logger.warning(f"[청산 체결 조회 실패] {code}: {e}")

        # 손익 계산 (수수료 포함) - 실제 체결값 기반
        if pos.side == Side.BUY:
            gross_pnl = (actual_exit_price - pos.entry_price) * actual_close_qty
        else:
            gross_pnl = (pos.entry_price - actual_exit_price) * actual_close_qty

        buy_amount = pos.entry_price * actual_close_qty
        sell_amount = actual_exit_price * actual_close_qty
        # 사용하기 쉽도록 exit_price 변수도 체결가로 덮음
        exit_price = actual_exit_price
        commission = estimate_commission(buy_amount, False) + estimate_commission(sell_amount, True)
        net_pnl = gross_pnl - commission
        pnl_pct = (gross_pnl / buy_amount * 100) if buy_amount > 0 else 0

        # 기록 (실제 청산 체결수량 반영)
        trade = TradeResult(
            code=code, side=pos.side.value,
            entry_price=pos.entry_price, exit_price=exit_price,
            quantity=actual_close_qty,
            gross_pnl=gross_pnl, net_pnl=net_pnl, commission=commission,
            pnl_pct=round(pnl_pct, 3),
            strategy=pos.strategy,
            hold_seconds=round(time.time() - pos.entry_time, 1),
            entry_time=datetime.fromtimestamp(pos.entry_time).strftime("%H:%M:%S"),
            exit_time=datetime.now().strftime("%H:%M:%S"),
            exit_reason=reason,
        )
        self.trade_history.append(trade)

        # 매매일지 저장 & AI 학습 & 프리셋 성과 기록
        try:
            trade_journal.record_trade(trade.__dict__, engine_type="auto_scalper")
            trade_brain.learn(trade.__dict__)
            preset_manager.record_trade(self.active_preset_name, net_pnl)
        except Exception as e:
            logger.error(f"[매매일지/Brain/Preset] 기록 실패: {e}")

        # 통계 업데이트
        self.risk.record_trade(net_pnl)
        self.stats["total_trades"] = self.stats.get("total_trades", 0) + 1
        self.stats["total_gross_pnl"] += gross_pnl
        self.stats["total_net_pnl"] += net_pnl
        self.stats["total_commission"] += commission
        # 실제 체결 금액 누적 (진입=매수/청산=매도 기준; SELL 포지션도 동일하게 기록)
        self.stats["total_buy_quantity"] = self.stats.get("total_buy_quantity", 0) + actual_close_qty
        self.stats["total_buy_amount"] = self.stats.get("total_buy_amount", 0.0) + buy_amount
        self.stats["total_sell_amount"] = self.stats.get("total_sell_amount", 0.0) + sell_amount
        if net_pnl > 0:
            self.stats["wins"] += 1
        else:
            self.stats["losses"] += 1

        # 부분 청산 처리: 잔량이 남으면 포지션 유지, 전량 청산시 제거
        remaining = pos.quantity - actual_close_qty
        if remaining > 0:
            pos.quantity = remaining
            logger.info(f"[부분 청산] {code} {actual_close_qty}주 체결 / {remaining}주 잔량 유지")
        else:
            del self.positions[code]

        emoji = "🟢" if net_pnl > 0 else "🔴"
        logger.info(f"[청산] {emoji} {code} {reason} | "
                    f"체결수량={actual_close_qty}주 체결가={actual_exit_price:,.0f} "
                    f"손익={net_pnl:+,.0f}원 (수수료 {commission:,.0f}원) "
                    f"보유 {trade.hold_seconds}초")

    # ── Background Loops ──

    async def _monitor_loop(self):
        """포지션 모니터링 루프 (0.3초마다) - 순수 룰 기반"""
        while self.running:
            try:
                # 장 시간 체크
                market_ok, msg = is_market_open()
                if not market_ok:
                    if self.positions:
                        logger.info(f"장 마감 - 전체 포지션 청산: {msg}")
                        for code in list(self.positions.keys()):
                            buf = self.tick_buffers.get(code)
                            if buf and buf.latest:
                                self._close_position(code, buf.latest.price, msg)

                for code in list(self.positions.keys()):
                    pos = self.positions.get(code)
                    buf = self.tick_buffers.get(code)
                    if not pos or not buf or not buf.latest:
                        continue

                    exit_reason = self.risk.check_exit(pos, buf.latest.price)
                    if exit_reason:
                        self._close_position(code, buf.latest.price, exit_reason)

            except Exception as e:
                logger.error(f"Monitor loop error: {e}")

            await asyncio.sleep(0.3)

    async def _rotation_loop(self):
        """종목 로테이션 루프 - 주기적 재검색 + 성과 기반 교체"""
        scan_count = 0
        while self.running:
            await asyncio.sleep(self.config.rotation_interval_seconds)

            try:
                if not self.running:
                    break

                scan_count += 1

                # 1. 주기적 강제 재검색 (매 scan_interval마다, 최소 rotation_interval 간격)
                if self.scanner.needs_scan():
                    logger.info(f"[Rotation] 주기적 종목 재검색 (#{scan_count})")
                    await self._do_scan()

                # 2. 성과 기반 교체 (거래가 있는 종목만 평가)
                rotated = False
                for code in list(self.scanner.current_targets):
                    if self.scanner.should_rotate(code, self.trade_history):
                        logger.info(f"[Rotation] 종목 교체: {code} (성과 부진)")
                        # 포지션이 있으면 먼저 청산
                        if code in self.positions:
                            buf = self.tick_buffers.get(code)
                            if buf and buf.latest:
                                self._close_position(code, buf.latest.price, "종목 교체")
                        # 재검색
                        await self._do_scan()
                        rotated = True
                        break

                # 3. 장기 무거래 시 강제 재검색 (3회 로테이션(=30분) 동안 매매 0건)
                if not rotated and scan_count % 3 == 0:
                    recent_trades = [t for t in self.trade_history
                                     if (datetime.now() - datetime.strptime(
                                         t.entry_time, "%H:%M:%S")).seconds < 1800]
                    if len(recent_trades) == 0 and len(self.positions) == 0:
                        logger.info(f"[Rotation] 30분 무거래 → 강제 종목 재검색")
                        await self._do_scan()

                # 4. 프리셋 자동 전환 체크
                try:
                    switch_to = preset_manager.check_auto_switch()
                    if switch_to:
                        logger.info(f"[AutoSwitch] 프리셋 자동 전환: {self.active_preset_name} → {switch_to}")
                        # 포지션 전부 청산 후 전환
                        for c in list(self.positions.keys()):
                            b = self.tick_buffers.get(c)
                            if b and b.latest:
                                self._close_position(c, b.latest.price, "프리셋 전환")
                        self.switch_preset(switch_to)
                except Exception as e:
                    logger.warning(f"[AutoSwitch] 체크 실패: {e}")

            except Exception as e:
                logger.error(f"Rotation loop error: {e}")

    async def _do_scan(self):
        """종목 검색 + WebSocket 구독"""
        from services.kiwoom_provider import kiwoom
        from services.kiwoom_ws import kiwoom_ws_manager

        self.state = EngineState.SCANNING
        old_targets = set(self.scanner.current_targets)
        new_targets = self.scanner.scan(kiwoom)
        new_set = set(new_targets)

        # 신규 타겟 + 구독이 소실된 기존 타겟을 모두 포함해 구독 보정
        # (WS 재연결 후 재구독 콜백이 누락된 경우를 대비한 안전망)
        subscribed = kiwoom_ws_manager.subscribed_codes
        missing_existing = [c for c in new_set if c not in subscribed]
        to_subscribe = list(set(missing_existing) | (new_set - old_targets))
        if to_subscribe:
            if kiwoom_ws_manager.connected and kiwoom_ws_manager.logged_in_event.is_set():
                try:
                    await asyncio.wait_for(
                        kiwoom_ws_manager.subscribe_stocks(to_subscribe, append=True),
                        timeout=20.0
                    )
                    lost = set(missing_existing) - (new_set - old_targets)
                    if lost:
                        logger.warning(f"[구독복구] 소실된 기존 타겟 재구독: {list(lost)}")
                    logger.info(f"WebSocket 신규/복구 구독 완료: {to_subscribe}")
                except asyncio.TimeoutError:
                    logger.warning(f"WebSocket 구독 타임아웃: {to_subscribe}")
            else:
                logger.warning(f"WebSocket 미연결/미로그인 - 구독 스킵: connected={kiwoom_ws_manager.connected}, logged_in={kiwoom_ws_manager.logged_in_event.is_set()}")

        self.state = EngineState.TRADING

    async def _periodic_rescan_loop(self):
        """scan_interval_seconds 마다 종목을 재검색하여 최신 거래량 상위 종목으로 갱신"""
        while self.running:
            await asyncio.sleep(self.config.scan_interval_seconds)
            try:
                if not self.running:
                    break
                # 포지션이 열려있으면 재검색 스킵 (진행 중인 거래 보호)
                if self.positions:
                    continue
                logger.info(f"[Rescan] 주기적 종목 재검색 ({self.config.scan_interval_seconds}초 간격)")
                await self._do_scan()
            except Exception as e:
                logger.error(f"[Rescan] 재검색 에러: {e}")

    # ── Status & Config ──

    def update_config(self, new_config: dict):
        """설정 업데이트 + 파일 저장"""
        for k, v in new_config.items():
            if hasattr(self.config, k):
                expected_type = type(getattr(self.config, k))
                try:
                    setattr(self.config, k, expected_type(v))
                except (ValueError, TypeError):
                    pass
        # 전략 엔진 / 리스크 / 스캐너 전체 갱신
        self.strategy = StrategyEngine(self.config)
        self.risk.config = self.config
        self.scanner.config = self.config   # 종목 스캔 필터도 즉시 반영
        # 파일에 저장 (서버 재시작 시 유지)
        self.config.save_to_file()
        logger.info("설정 업데이트 + 저장 완료")

    def switch_preset(self, name: str) -> bool:
        """런타임 프리셋 교체 (전략/리스크/주문 전체 교체)"""
        success = preset_manager.switch_preset(name)
        if success:
            self.active_preset_name = name
            # 엔진 재초기화
            self.strategy = StrategyEngine(self.config)
            self.risk = RiskManager(self.config)
            self.scanner = StockScanner(self.config)
            logger.info(f"[AutoScalper] 프리셋 전환 완료: {name}")
        return success

    def get_status(self) -> dict:
        """현재 상태 반환"""
        # 포지션 정보
        positions_info = []
        for code, pos in self.positions.items():
            buf = self.tick_buffers.get(code)
            cur_price = buf.latest.price if buf and buf.latest else pos.entry_price
            if pos.side == Side.BUY:
                pnl = (cur_price - pos.entry_price) * pos.quantity
                pnl_pct = (cur_price - pos.entry_price) / pos.entry_price * 100
            else:
                pnl = (pos.entry_price - cur_price) * pos.quantity
                pnl_pct = (pos.entry_price - cur_price) / pos.entry_price * 100

            positions_info.append({
                "code": code,
                "side": pos.side.value,
                "entry_price": pos.entry_price,
                "current_price": cur_price,
                "quantity": pos.quantity,
                "pnl": pnl,
                "pnl_pct": round(pnl_pct, 3),
                "hold_seconds": round(time.time() - pos.entry_time, 1),
                "strategy": pos.strategy,
                "stop_loss": pos.stop_loss,
                "take_profit": pos.take_profit,
            })

        # 승률
        total = self.stats["wins"] + self.stats["losses"]
        win_rate = (self.stats["wins"] / total * 100) if total > 0 else 0

        return {
            "state": self.state.value,
            "running": self.running,
            "target_stocks": self.scanner.current_targets,
            "stock_scores": self.scanner.stock_scores,
            "positions": positions_info,
            "stats": {
                **self.stats,
                "win_rate": round(win_rate, 1),
                "daily_pnl": self.risk.daily_pnl,
                "daily_trades": self.risk.daily_trades,
            },
            "recent_signals": list(self.signal_log)[-20:],
            "recent_trades": [
                {
                    "code": t.code, "side": t.side,
                    "entry": t.entry_price, "exit": t.exit_price,
                    "qty": t.quantity,
                    "gross_pnl": t.gross_pnl, "net_pnl": t.net_pnl,
                    "commission": round(t.commission, 0),
                    "pnl_pct": t.pnl_pct,
                    "strategy": t.strategy,
                    "hold_sec": t.hold_seconds,
                    "exit_reason": t.exit_reason,
                    "time": f"{t.entry_time}~{t.exit_time}",
                }
                for t in self.trade_history[-20:]
            ],
            "config": self.config.to_dict(),
            "active_preset": self.active_preset_name,
            "preset_status": preset_manager.get_status(),
            "startup_error": self._startup_error,
            "market_open_scheduler_running": self._market_open_task is not None
                                              and not self._market_open_task.done(),
        }

    # ── Market-Open Auto Scheduler (09:00 자동 시작) ──

    async def market_open_scheduler(self):
        """
        매일 KST 08:58에 깨어나 09:00:00이 되면 자동으로 엔진 시작.
        이미 실행 중이거나 장 외 시간이면 skip.
        주말 skip. 한 번 시작에 성공하면 그 날은 더 시도 안 함.
        """
        logger.info("[MarketOpenScheduler] 시작 — 매일 09:00 자동 가동 대기")
        last_triggered_date = None

        while True:
            try:
                now = datetime.now()
                today = now.date()

                # 주말 skip (토=5, 일=6)
                if now.weekday() >= 5:
                    # 다음 날 00:05까지 대기
                    await asyncio.sleep(3600)  # 1시간 단위 체크
                    continue

                # 오늘 이미 트리거 했으면 다음 날까지 대기
                if last_triggered_date == today:
                    # 다음 날 새벽까지 긴 대기
                    await asyncio.sleep(1800)  # 30분 단위 체크
                    continue

                # 09:00 이전이면 타이밍 맞춰 대기
                target = now.replace(hour=9, minute=0, second=0, microsecond=0)
                if now < target:
                    wait_sec = (target - now).total_seconds()
                    # 08:58 이후면 1초 단위로 정밀 대기, 그 전이면 60초 단위
                    if wait_sec > 120:
                        await asyncio.sleep(min(wait_sec - 120, 300))
                        continue
                    # 2분 이내면 정밀 대기
                    await asyncio.sleep(max(0.5, wait_sec))
                    # 시간 도달
                    if self.running:
                        logger.info("[MarketOpenScheduler] 09:00 도달했으나 이미 실행 중 — skip")
                        last_triggered_date = today
                        continue
                    logger.info("[MarketOpenScheduler] 🕘 09:00 도달 — 자동 시작 트리거")
                    try:
                        # 비동기 start 시퀀스 호출
                        from routers.auto_scalping import _startup_sequence
                        await _startup_sequence()
                        last_triggered_date = today
                        logger.info("[MarketOpenScheduler] ✅ 자동 시작 완료")
                    except Exception as e:
                        logger.error(f"[MarketOpenScheduler] 자동 시작 실패: {e}")
                        # 실패해도 오늘은 더 시도 안 함 (무한 루프 방지)
                        last_triggered_date = today
                else:
                    # 09:00 이후 — 이미 지남 (서버 재시작 등). 장 시간(09:01~15:19)이면 즉시 시작.
                    if not self.running and now.time() >= dtime(9, 1) and now.time() < dtime(15, 19):
                        logger.info("[MarketOpenScheduler] 장 시간 진입 후 엔진 꺼진 상태 감지 → 자동 시작")
                        try:
                            from routers.auto_scalping import _startup_sequence
                            await _startup_sequence()
                            last_triggered_date = today
                        except Exception as e:
                            logger.error(f"[MarketOpenScheduler] 장중 재시작 실패: {e}")
                            last_triggered_date = today
                    else:
                        last_triggered_date = today
                    # 다음 날까지 대기
                    await asyncio.sleep(1800)

            except asyncio.CancelledError:
                logger.info("[MarketOpenScheduler] 중단됨")
                return
            except Exception as e:
                logger.error(f"[MarketOpenScheduler] 예외: {e}")
                await asyncio.sleep(60)

    def ensure_market_open_scheduler(self):
        """이벤트 루프 위에서 스케줄러 태스크 1회 등록"""
        if self._market_open_task is not None and not self._market_open_task.done():
            return
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                self._market_open_task = asyncio.create_task(self.market_open_scheduler())
                logger.info("[MarketOpenScheduler] 태스크 등록 완료")
        except RuntimeError:
            # 이벤트 루프가 아직 없으면 라우터 startup 훅에서 호출
            pass


# ═══════════════════════════════════════════════════════
#  Singleton
# ═══════════════════════════════════════════════════════

auto_scalper = AutoScalpingSystem()
