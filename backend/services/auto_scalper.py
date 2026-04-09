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
import logging
import time
import numpy as np
from datetime import datetime, time as dtime
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, List, Tuple

logger = logging.getLogger(__name__)

# 매매일지 & AI 두뇌 & AI 어드바이저
from services.trade_journal import trade_journal
from services.trade_analyzer import trade_brain
from services.ai_advisor import ai_advisor

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
    scan_interval_seconds: float = 180    # 3분마다 종목 재검색
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
    max_hold_seconds: float = 300         # 5분 최대 보유
    cooldown_seconds: float = 3           # 3초 쿨다운
    max_daily_trades: int = 50            # 일일 최대 거래 횟수

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
#  Strategy Engine (6 strategies)
# ═══════════════════════════════════════════════════════

class StrategyEngine:
    """6개 전략 + 컨센서스 시그널 생성"""

    def __init__(self, config: AutoScalpConfig):
        self.config = config

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

        return signals

    def get_consensus(self, signals: List[dict]) -> Optional[dict]:
        """컨센서스: 다수 전략이 같은 방향이면 진입"""
        if not signals:
            return None

        buy_signals = [s for s in signals if s["side"] == Side.BUY]
        sell_signals = [s for s in signals if s["side"] == Side.SELL]

        if len(buy_signals) >= self.config.min_consensus:
            strategies = [s["strategy"] for s in buy_signals]
            return {
                "side": Side.BUY,
                "strategy": f"consensus({','.join(strategies)})",
                "strength": len(buy_signals),
                "reason": f"{len(buy_signals)}개 전략 매수 합의",
            }

        if len(sell_signals) >= self.config.min_consensus:
            strategies = [s["strategy"] for s in sell_signals]
            return {
                "side": Side.SELL,
                "strategy": f"consensus({','.join(strategies)})",
                "strength": len(sell_signals),
                "reason": f"{len(sell_signals)}개 전략 매도 합의",
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


# ═══════════════════════════════════════════════════════
#  Risk Manager
# ═══════════════════════════════════════════════════════

class RiskManager:
    def __init__(self, config: AutoScalpConfig):
        self.config = config
        self.daily_pnl: float = 0.0
        self.daily_trades: int = 0
        self.last_trade_time: float = 0

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
        """청산 조건 확인"""
        if pos.side == Side.BUY:
            pnl_pct = (current_price - pos.entry_price) / pos.entry_price * 100
        else:
            pnl_pct = (pos.entry_price - current_price) / pos.entry_price * 100

        # 손절
        if pnl_pct <= -self.config.stop_loss_pct:
            return f"손절 ({pnl_pct:.2f}%)"

        # 익절 - AI에게 홀딩 연장 여부 문의
        if pnl_pct >= self.config.take_profit_pct:
            try:
                pos_data = {
                    "side": pos.side.value,
                    "entry_price": pos.entry_price,
                    "pnl_pct": round(pnl_pct, 2),
                    "hold_seconds": time.time() - pos.entry_time,
                    "drawdown_from_high": round(
                        (pos.highest_since_entry - current_price) / pos.highest_since_entry * 100
                        if pos.side == Side.BUY and pos.highest_since_entry > 0 else 0, 2
                    ),
                }
                tick_data = {"price": current_price, "bid_qty": 0, "ask_qty": 0}
                hold_decision = ai_advisor.should_hold_longer(pos.code, pos_data, tick_data)

                if hold_decision.get("hold"):
                    # AI가 홀딩 연장 결정 → 익절 스킵
                    new_tp = hold_decision.get("new_take_profit_pct")
                    if new_tp and new_tp > self.config.take_profit_pct:
                        # 익절 기준 상향 (다음 check_exit에서 새 기준 적용)
                        override = ai_advisor.get_position_override(pos.code)
                        if override.get("take_profit_pct"):
                            # 포지션의 TP 가격 재설정
                            if pos.side == Side.BUY:
                                pos.take_profit = align_price(
                                    int(pos.entry_price * (1 + new_tp / 100)), "up")
                            else:
                                pos.take_profit = align_price(
                                    int(pos.entry_price * (1 - new_tp / 100)), "down")
                    return None  # 익절하지 않고 계속 보유
            except Exception:
                pass  # AI 실패 시 정상 익절

            return f"익절 ({pnl_pct:.2f}%)"

        # 트레일링 스탑 (수수료 0.21% 이상 수익일 때만 작동 → 수수료 손실 방지)
        min_profit_for_trailing = 0.25  # 왕복수수료(0.21%) + 여유분
        if self.config.use_trailing_stop and pos.side == Side.BUY:
            if current_price > pos.highest_since_entry:
                pos.highest_since_entry = current_price
            trailing_stop = pos.highest_since_entry * (1 - self.config.trailing_stop_pct / 100)
            if current_price <= trailing_stop and pnl_pct > min_profit_for_trailing:
                return f"트레일링스탑 (고점 {pos.highest_since_entry}→현재 {current_price})"

        if self.config.use_trailing_stop and pos.side == Side.SELL:
            if current_price < pos.lowest_since_entry:
                pos.lowest_since_entry = current_price
            trailing_stop = pos.lowest_since_entry * (1 + self.config.trailing_stop_pct / 100)
            if current_price >= trailing_stop and pnl_pct > min_profit_for_trailing:
                return f"트레일링스탑 (저점 {pos.lowest_since_entry}→현재 {current_price})"

        # 최대 보유 시간
        hold_time = time.time() - pos.entry_time
        if hold_time >= self.config.max_hold_seconds:
            return f"시간초과 ({hold_time:.0f}초)"

        return None

    def record_trade(self, net_pnl: float):
        self.daily_pnl += net_pnl
        self.daily_trades += 1
        self.last_trade_time = time.time()

    def reset_daily(self):
        self.daily_pnl = 0.0
        self.daily_trades = 0


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

            # AI 어드바이저가 종목 후보를 검토/재순위화
            try:
                brain_data = trade_brain.brain if trade_brain else {}
                candidates = ai_advisor.evaluate_stock_candidates(candidates, brain_data)
            except Exception as e:
                logger.warning(f"[AI종목선정] 스킵: {e}")

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
        """스캘핑 적합도 점수 (0~100)"""
        score = 0.0

        # 거래량 점수 (30%) - log scale
        vol_score = min(100, np.log10(max(volume, 1)) / np.log10(10_000_000) * 100)
        score += vol_score * 0.30

        # 변동성 점수 (25%) - 1~3% 가 이상적
        ideal_vol = 1.5
        vol_diff = abs(abs(change_pct) - ideal_vol)
        volatility_score = max(0, 100 - vol_diff * 30)
        score += volatility_score * 0.25

        # 가격대 점수 (20%) - 5천~5만원 이상적
        if 5000 <= price <= 50000:
            price_score = 100
        elif 2000 <= price <= 100000:
            price_score = 60
        else:
            price_score = 20
        score += price_score * 0.20

        # 호가 단위 대비 가격 비율 (15%) - 호가단위/가격이 작을수록 좋음
        tick = get_tick_size(price)
        spread_ratio = tick / price * 100
        spread_score = max(0, 100 - spread_ratio * 500)
        score += spread_score * 0.15

        # 방향성 점수 (10%) - 약간의 추세가 있으면 좋음
        momentum_score = min(100, abs(change_pct) * 50)
        score += momentum_score * 0.10

        return round(score, 2)

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
        self.config = config or AutoScalpConfig()
        self.strategy = StrategyEngine(self.config)
        self.risk = RiskManager(self.config)
        self.scanner = StockScanner(self.config)

        self.state = EngineState.IDLE
        self.running = False

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
        }

        # Tasks
        self._monitor_task = None
        self._rotation_task = None

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

        # 종목 검색
        await self._do_scan()

        # 백그라운드 루프 시작
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        self._rotation_task = asyncio.create_task(self._rotation_loop())

        self.state = EngineState.TRADING
        logger.info(f"AutoScalper 시작: 감시 종목 {self.scanner.current_targets}")
        return {"success": True, "message": "자동 스캘핑 시작",
                "targets": self.scanner.current_targets}

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
        for task in [self._monitor_task, self._rotation_task]:
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

            exit_reason = self.risk.check_exit(pos, tick.price)
            if exit_reason:
                self._close_position(code, tick.price, exit_reason)
                return

        # 2. 이미 포지션이 있으면 새 진입 안 함
        if code in self.positions:
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

        # 5. 컨센서스 확인
        consensus = self.strategy.get_consensus(signals)
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

        # 6. AI 어드바이저에게 진입 승인 요청
        try:
            tick_data = {
                "price": buf.latest.price if buf.latest else 0,
                "bid": buf.latest.bid if buf.latest else 0,
                "ask": buf.latest.ask if buf.latest else 0,
                "bid_qty": buf.latest.bid_qty if buf.latest else 0,
                "ask_qty": buf.latest.ask_qty if buf.latest else 0,
            }
            brain_data = trade_brain.brain if trade_brain else {}
            ai_decision = ai_advisor.should_enter(
                code, consensus, tick_data, self.positions, brain_data
            )

            if not ai_decision.get("approve", True):
                # AI가 진입 거부
                self.signal_log.append({
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "code": code,
                    "side": consensus["side"].value,
                    "strategy": consensus["strategy"],
                    "reason": consensus["reason"],
                    "action": f"AI_REJECT: {ai_decision.get('reason', '')}",
                })
                logger.info(f"[AI거부] {code} {consensus['side'].value} - {ai_decision.get('reason', '')}")
                return
        except Exception as e:
            logger.warning(f"[AI진입판단] 스킵: {e}")
            ai_decision = {"approve": True, "adjust": {}}

        # 7. 진입 실행
        entry_signal = {
            "time": datetime.now().strftime("%H:%M:%S"),
            "code": code,
            "side": consensus["side"].value,
            "strategy": consensus["strategy"],
            "reason": consensus["reason"],
            "action": "ENTRY",
            "ai_adjust": ai_decision.get("adjust", {}),
        }
        self.signal_log.append(entry_signal)
        try:
            trade_journal.record_signal(entry_signal, engine_type="auto_scalper")
        except Exception:
            pass
        self._open_position(code, consensus, ai_adjust=ai_decision.get("adjust", {}))

    # ── Position Management ──

    def _open_position(self, code: str, consensus: dict, ai_adjust: dict = None):
        """포지션 진입 (AI 조정값 반영)"""
        from services.kiwoom_provider import kiwoom

        buf = self.tick_buffers.get(code)
        if not buf or not buf.latest:
            return

        price = buf.latest.price
        side = consensus["side"]

        # AI가 조정한 투자금/수량 반영
        max_invest = self.config.max_investment_per_trade
        if ai_adjust and "max_investment_per_trade" in ai_adjust:
            max_invest = max(100_000, min(2_000_000, int(ai_adjust["max_investment_per_trade"])))

        # 수량 계산 (최대 투자금 기반)
        quantity = min(
            self.config.order_quantity,
            max(1, max_invest // price)
        )

        # 수수료 대비 수익성 사전 검증
        tp_pct = (ai_adjust or {}).get("take_profit_pct", self.config.take_profit_pct)
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
            # AI 조정값이 있으면 포지션별 SL/TP 적용
            sl_pct = (ai_adjust or {}).get("stop_loss_pct", self.config.stop_loss_pct)
            tp_pct = (ai_adjust or {}).get("take_profit_pct", self.config.take_profit_pct)

            # 안전 범위 강제
            sl_pct = max(0.2, min(2.0, sl_pct))
            tp_pct = max(0.3, min(5.0, tp_pct))

            if side == Side.BUY:
                sl = align_price(int(price * (1 - sl_pct / 100)), "down")
                tp = align_price(int(price * (1 + tp_pct / 100)), "up")
            else:
                sl = align_price(int(price * (1 + sl_pct / 100)), "up")
                tp = align_price(int(price * (1 - tp_pct / 100)), "down")

            pos = Position(
                code=code, side=side, entry_price=price,
                quantity=quantity, entry_time=time.time(),
                order_no=result.get("order_no", ""),
                stop_loss=sl, take_profit=tp,
                highest_since_entry=price,
                lowest_since_entry=price,
                strategy=consensus["strategy"],
            )
            self.positions[code] = pos
            self.stats["total_trades"] += 1

            logger.info(f"[진입] {side.value.upper()} {code} "
                        f"가격={price:,} 수량={quantity} "
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

        # 손익 계산 (수수료 포함)
        if pos.side == Side.BUY:
            gross_pnl = (exit_price - pos.entry_price) * pos.quantity
        else:
            gross_pnl = (pos.entry_price - exit_price) * pos.quantity

        buy_amount = pos.entry_price * pos.quantity
        sell_amount = exit_price * pos.quantity
        commission = estimate_commission(buy_amount, False) + estimate_commission(sell_amount, True)
        net_pnl = gross_pnl - commission
        pnl_pct = (gross_pnl / buy_amount * 100) if buy_amount > 0 else 0

        # 기록
        trade = TradeResult(
            code=code, side=pos.side.value,
            entry_price=pos.entry_price, exit_price=exit_price,
            quantity=pos.quantity,
            gross_pnl=gross_pnl, net_pnl=net_pnl, commission=commission,
            pnl_pct=round(pnl_pct, 3),
            strategy=pos.strategy,
            hold_seconds=round(time.time() - pos.entry_time, 1),
            entry_time=datetime.fromtimestamp(pos.entry_time).strftime("%H:%M:%S"),
            exit_time=datetime.now().strftime("%H:%M:%S"),
            exit_reason=reason,
        )
        self.trade_history.append(trade)

        # 매매일지 저장 & AI 학습
        try:
            trade_journal.record_trade(trade.__dict__, engine_type="auto_scalper")
            trade_brain.learn(trade.__dict__)
        except Exception as e:
            logger.error(f"[매매일지/Brain] 기록 실패: {e}")

        # 통계 업데이트
        self.risk.record_trade(net_pnl)
        self.stats["total_gross_pnl"] += gross_pnl
        self.stats["total_net_pnl"] += net_pnl
        self.stats["total_commission"] += commission
        if net_pnl > 0:
            self.stats["wins"] += 1
        else:
            self.stats["losses"] += 1

        del self.positions[code]

        # AI 포지션별 오버라이드 정리
        try:
            ai_advisor.on_position_closed(code)
        except Exception:
            pass

        emoji = "🟢" if net_pnl > 0 else "🔴"
        logger.info(f"[청산] {emoji} {code} {reason} | "
                    f"손익={net_pnl:+,.0f}원 (수수료 {commission:,.0f}원) "
                    f"보유 {trade.hold_seconds}초")

    # ── Background Loops ──

    async def _monitor_loop(self):
        """포지션 모니터링 루프 (0.3초마다) + AI 시장 분석"""
        _market_check_counter = 0

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

                # AI 시장 분석 (약 5분마다, 0.3초 * 1000 ≈ 5분)
                _market_check_counter += 1
                if _market_check_counter >= 1000:
                    _market_check_counter = 0
                    try:
                        brain_data = trade_brain.brain if trade_brain else {}
                        await ai_advisor.analyze_market(
                            self.positions, self.stats, brain_data
                        )
                    except Exception as e:
                        logger.warning(f"[AI시장분석] 스킵: {e}")

            except Exception as e:
                logger.error(f"Monitor loop error: {e}")

            await asyncio.sleep(0.3)

    async def _rotation_loop(self):
        """종목 로테이션 루프"""
        while self.running:
            await asyncio.sleep(self.config.rotation_interval_seconds)

            try:
                if not self.running:
                    break

                # 종목 재검색 필요?
                if self.scanner.needs_scan():
                    await self._do_scan()
                    continue

                # 성과 기반 교체
                for code in list(self.scanner.current_targets):
                    if self.scanner.should_rotate(code, self.trade_history):
                        logger.info(f"종목 교체: {code} (성과 부진)")
                        # 포지션이 있으면 먼저 청산
                        if code in self.positions:
                            buf = self.tick_buffers.get(code)
                            if buf and buf.latest:
                                self._close_position(code, buf.latest.price, "종목 교체")
                        # 재검색
                        await self._do_scan()
                        break

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

        # 새 종목 구독 (subscribe_stocks는 리스트 단위 처리)
        to_subscribe = list(new_set - old_targets)
        if to_subscribe:
            if kiwoom_ws_manager.connected and kiwoom_ws_manager.logged_in_event.is_set():
                try:
                    await asyncio.wait_for(
                        kiwoom_ws_manager.subscribe_stocks(to_subscribe, append=True),
                        timeout=20.0
                    )
                    logger.info(f"WebSocket 신규 구독 완료: {to_subscribe}")
                except asyncio.TimeoutError:
                    logger.warning(f"WebSocket 구독 타임아웃: {to_subscribe}")
            else:
                logger.warning(f"WebSocket 미연결/미로그인 - 구독 스킵: connected={kiwoom_ws_manager.connected}, logged_in={kiwoom_ws_manager.logged_in_event.is_set()}")

        self.state = EngineState.TRADING

    # ── Status & Config ──

    def update_config(self, new_config: dict):
        """설정 업데이트"""
        for k, v in new_config.items():
            if hasattr(self.config, k):
                expected_type = type(getattr(self.config, k))
                try:
                    setattr(self.config, k, expected_type(v))
                except (ValueError, TypeError):
                    pass
        # 전략 엔진 갱신
        self.strategy = StrategyEngine(self.config)
        self.risk.config = self.config
        logger.info(f"설정 업데이트 완료")

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
        }


# ═══════════════════════════════════════════════════════
#  Singleton
# ═══════════════════════════════════════════════════════

auto_scalper = AutoScalpingSystem()
