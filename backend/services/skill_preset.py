"""
스킬 프리셋 시스템 - 매매 스킬 세트 관리

각 프리셋 = 전략 조합 + 파라미터 + 리스크 설정 + 종목 필터의 묶음
여러 프리셋을 저장/로드/교체하며, 성과를 독립 추적하여
승률 기반으로 자동 전환 또는 AI 최적화를 수행한다.

저장 위치: trading_journals/skill_presets/
"""
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)

_PRESETS_DIR = Path(__file__).resolve().parent.parent.parent / "trading_journals" / "skill_presets"
_REGISTRY_FILE = _PRESETS_DIR / "_registry.json"


# ═══════════════════════════════════════════════════════
#  SkillPreset 데이터 구조
# ═══════════════════════════════════════════════════════

@dataclass
class SkillPreset:
    # 메타데이터
    name: str = ""
    display_name: str = ""
    description: str = ""
    version: int = 1
    created_at: str = ""
    updated_at: str = ""
    created_by: str = "system"  # system | ai | user

    # 전략 조합: {전략명: {enabled, weight, params}}
    strategies: dict = field(default_factory=dict)

    # 리스크 설정
    risk: dict = field(default_factory=dict)

    # 주문 설정
    order: dict = field(default_factory=dict)

    # 종목 선정 조건
    stock_filter: dict = field(default_factory=dict)

    # 성과 추적
    performance: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "created_by": self.created_by,
            "strategies": self.strategies,
            "risk": self.risk,
            "order": self.order,
            "stock_filter": self.stock_filter,
            "performance": self.performance,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SkillPreset":
        return cls(
            name=d.get("name", ""),
            display_name=d.get("display_name", ""),
            description=d.get("description", ""),
            version=d.get("version", 1),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
            created_by=d.get("created_by", "system"),
            strategies=d.get("strategies", {}),
            risk=d.get("risk", {}),
            order=d.get("order", {}),
            stock_filter=d.get("stock_filter", {}),
            performance=d.get("performance", _default_performance()),
        )

    def get_strategy_params(self, strategy_name: str) -> dict:
        """전략의 파라미터 반환"""
        s = self.strategies.get(strategy_name, {})
        return s.get("params", {})

    def is_strategy_enabled(self, strategy_name: str) -> bool:
        """전략 활성화 여부"""
        s = self.strategies.get(strategy_name, {})
        return s.get("enabled", False)

    def get_strategy_weight(self, strategy_name: str) -> float:
        """전략 가중치"""
        s = self.strategies.get(strategy_name, {})
        return s.get("weight", 1.0)


def _default_performance() -> dict:
    return {
        "total_trades": 0,
        "wins": 0,
        "losses": 0,
        "total_net_pnl": 0,
        "recent_20_trades": [],
        "win_rate": 0.0,
        "recent_win_rate": 0.0,
        "last_used": "",
        "active_since": "",
    }


# ═══════════════════════════════════════════════════════
#  기본 프리셋 5개 정의
# ═══════════════════════════════════════════════════════

def _make_aggressive() -> SkillPreset:
    """공격형: 빠른 진입/청산, 모멘텀+거래량 중심"""
    return SkillPreset(
        name="aggressive",
        display_name="공격형 스캘핑",
        description="모멘텀과 거래량 급증을 포착하여 빠르게 진입/청산. 높은 거래 빈도.",
        created_by="system",
        strategies={
            "tick_momentum": {
                "enabled": True, "weight": 1.0,
                "params": {"window": 15, "threshold": 0.75}
            },
            "volume_spike": {
                "enabled": True, "weight": 1.0,
                "params": {"spike_mult": 3.0}
            },
            "orderbook_imbalance": {
                "enabled": True, "weight": 1.0,
                "params": {"threshold": 2.0}
            },
            "vwap_deviation": {
                "enabled": False, "weight": 1.0,
                "params": {"window": 60, "entry_deviation": 0.3}
            },
            "bollinger_scalp": {
                "enabled": False, "weight": 1.0,
                "params": {"window": 30, "std": 2.0}
            },
            "rsi_extreme": {
                "enabled": False, "weight": 1.0,
                "params": {"period": 10, "oversold": 25.0, "overbought": 75.0}
            },
            "ema_crossover": {
                "enabled": False, "weight": 1.0,
                "params": {"fast_period": 9, "slow_period": 21}
            },
            "trade_intensity": {
                "enabled": False, "weight": 1.0,
                "params": {"window": 30, "buy_threshold": 2.0, "sell_threshold": 0.5}
            },
            "tick_acceleration": {
                "enabled": False, "weight": 1.0,
                "params": {"window": 20, "threshold": 0.05}
            },
        },
        risk={
            "stop_loss_pct": 0.3,
            "take_profit_pct": 0.8,
            "trailing_stop_pct": 0.3,
            "use_trailing_stop": False,
            "max_position_count": 3,
            "max_daily_loss": 50000,
            "max_hold_seconds": 120,
            "cooldown_seconds": 2,
            "max_daily_trades": 80,
            "max_investment_per_trade": 500000,
        },
        order={
            "quantity": 10,
            "price_type": "market",
            "min_consensus": 2,
        },
        stock_filter={
            "min_price": 5000,
            "max_price": 50000,
            "min_volume": 500000,
            "min_volatility_pct": 1.0,
            "max_volatility_pct": 5.0,
            "min_trade_value": 5_000_000_000,
            "min_tick_frequency": 10,
            "max_spread_pct": 0.25,
            "max_target_stocks": 5,
        },
        performance=_default_performance(),
    )


def _make_stable() -> SkillPreset:
    """안정형: 평균회귀 기반, 낮은 변동 구간"""
    return SkillPreset(
        name="stable",
        display_name="안정형 스캘핑",
        description="VWAP/볼린저/RSI 기반 평균회귀 전략. 안정적 수익, 낮은 변동성 종목.",
        created_by="system",
        strategies={
            "tick_momentum": {
                "enabled": False, "weight": 1.0,
                "params": {"window": 20, "threshold": 0.7}
            },
            "volume_spike": {
                "enabled": False, "weight": 1.0,
                "params": {"spike_mult": 3.0}
            },
            "orderbook_imbalance": {
                "enabled": False, "weight": 1.0,
                "params": {"threshold": 2.0}
            },
            "vwap_deviation": {
                "enabled": True, "weight": 1.0,
                "params": {"window": 60, "entry_deviation": 0.25}
            },
            "bollinger_scalp": {
                "enabled": True, "weight": 1.0,
                "params": {"window": 40, "std": 2.0}
            },
            "rsi_extreme": {
                "enabled": True, "weight": 1.0,
                "params": {"period": 14, "oversold": 30.0, "overbought": 70.0}
            },
            "ema_crossover": {
                "enabled": False, "weight": 1.0,
                "params": {"fast_period": 9, "slow_period": 21}
            },
            "trade_intensity": {
                "enabled": False, "weight": 1.0,
                "params": {"window": 30, "buy_threshold": 2.0, "sell_threshold": 0.5}
            },
            "tick_acceleration": {
                "enabled": False, "weight": 1.0,
                "params": {"window": 20, "threshold": 0.05}
            },
        },
        risk={
            "stop_loss_pct": 0.5,
            "take_profit_pct": 1.5,
            "trailing_stop_pct": 0.4,
            "use_trailing_stop": True,
            "max_position_count": 3,
            "max_daily_loss": 40000,
            "max_hold_seconds": 300,
            "cooldown_seconds": 5,
            "max_daily_trades": 40,
            "max_investment_per_trade": 500000,
        },
        order={
            "quantity": 10,
            "price_type": "market",
            "min_consensus": 2,
        },
        stock_filter={
            "min_price": 10000,
            "max_price": 100000,
            "min_volume": 300000,
            "min_volatility_pct": 0.5,
            "max_volatility_pct": 2.0,
            "min_trade_value": 5_000_000_000,
            "min_tick_frequency": 5,
            "max_spread_pct": 0.2,
            "max_target_stocks": 5,
        },
        performance=_default_performance(),
    )


def _make_trend_follow() -> SkillPreset:
    """추세추종: 강한 추세 잡고 트레일링으로 수익 극대화"""
    return SkillPreset(
        name="trend_follow",
        display_name="추세추종 스캘핑",
        description="EMA 크로스 + 모멘텀으로 추세 포착, 트레일링 스탑으로 수익 극대화.",
        created_by="system",
        strategies={
            "tick_momentum": {
                "enabled": True, "weight": 1.0,
                "params": {"window": 20, "threshold": 0.7}
            },
            "volume_spike": {
                "enabled": True, "weight": 0.8,
                "params": {"spike_mult": 2.5}
            },
            "orderbook_imbalance": {
                "enabled": False, "weight": 1.0,
                "params": {"threshold": 2.0}
            },
            "vwap_deviation": {
                "enabled": False, "weight": 1.0,
                "params": {"window": 60, "entry_deviation": 0.3}
            },
            "bollinger_scalp": {
                "enabled": False, "weight": 1.0,
                "params": {"window": 30, "std": 2.0}
            },
            "rsi_extreme": {
                "enabled": False, "weight": 1.0,
                "params": {"period": 10, "oversold": 25.0, "overbought": 75.0}
            },
            "ema_crossover": {
                "enabled": True, "weight": 1.2,
                "params": {"fast_period": 9, "slow_period": 21}
            },
            "trade_intensity": {
                "enabled": False, "weight": 1.0,
                "params": {"window": 30, "buy_threshold": 2.0, "sell_threshold": 0.5}
            },
            "tick_acceleration": {
                "enabled": False, "weight": 1.0,
                "params": {"window": 20, "threshold": 0.05}
            },
        },
        risk={
            "stop_loss_pct": 0.5,
            "take_profit_pct": 2.0,
            "trailing_stop_pct": 0.5,
            "use_trailing_stop": True,
            "max_position_count": 2,
            "max_daily_loss": 50000,
            "max_hold_seconds": 300,
            "cooldown_seconds": 3,
            "max_daily_trades": 50,
            "max_investment_per_trade": 700000,
        },
        order={
            "quantity": 10,
            "price_type": "market",
            "min_consensus": 2,
        },
        stock_filter={
            "min_price": 5000,
            "max_price": 80000,
            "min_volume": 500000,
            "min_volatility_pct": 1.5,
            "max_volatility_pct": 5.0,
            "min_trade_value": 8_000_000_000,
            "min_tick_frequency": 10,
            "max_spread_pct": 0.25,
            "max_target_stocks": 5,
        },
        performance=_default_performance(),
    )


def _make_counter_trend() -> SkillPreset:
    """역추세: 과매수/과매도 구간에서 반대 방향 진입"""
    return SkillPreset(
        name="counter_trend",
        display_name="역추세 스캘핑",
        description="볼린저+RSI+VWAP로 과매수/과매도 감지, 반전 매매. 보수적 컨센서스.",
        created_by="system",
        strategies={
            "tick_momentum": {
                "enabled": False, "weight": 1.0,
                "params": {"window": 20, "threshold": 0.7}
            },
            "volume_spike": {
                "enabled": False, "weight": 1.0,
                "params": {"spike_mult": 3.0}
            },
            "orderbook_imbalance": {
                "enabled": False, "weight": 1.0,
                "params": {"threshold": 2.0}
            },
            "vwap_deviation": {
                "enabled": True, "weight": 1.0,
                "params": {"window": 50, "entry_deviation": 0.4}
            },
            "bollinger_scalp": {
                "enabled": True, "weight": 1.2,
                "params": {"window": 35, "std": 2.2}
            },
            "rsi_extreme": {
                "enabled": True, "weight": 1.0,
                "params": {"period": 12, "oversold": 20.0, "overbought": 80.0}
            },
            "ema_crossover": {
                "enabled": False, "weight": 1.0,
                "params": {"fast_period": 9, "slow_period": 21}
            },
            "trade_intensity": {
                "enabled": False, "weight": 1.0,
                "params": {"window": 30, "buy_threshold": 2.0, "sell_threshold": 0.5}
            },
            "tick_acceleration": {
                "enabled": False, "weight": 1.0,
                "params": {"window": 20, "threshold": 0.05}
            },
        },
        risk={
            "stop_loss_pct": 0.4,
            "take_profit_pct": 1.0,
            "trailing_stop_pct": 0.3,
            "use_trailing_stop": False,
            "max_position_count": 2,
            "max_daily_loss": 30000,
            "max_hold_seconds": 180,
            "cooldown_seconds": 5,
            "max_daily_trades": 40,
            "max_investment_per_trade": 500000,
        },
        order={
            "quantity": 10,
            "price_type": "market",
            "min_consensus": 3,
        },
        stock_filter={
            "min_price": 10000,
            "max_price": 80000,
            "min_volume": 300000,
            "min_volatility_pct": 1.0,
            "max_volatility_pct": 3.0,
            "min_trade_value": 5_000_000_000,
            "min_tick_frequency": 8,
            "max_spread_pct": 0.15,
            "max_target_stocks": 5,
        },
        performance=_default_performance(),
    )


def _make_volume_burst() -> SkillPreset:
    """거래량급등: 거래량 폭증 구간 단타"""
    return SkillPreset(
        name="volume_burst",
        display_name="거래량급등 스캘핑",
        description="거래량 급증 + 체결강도 + 모멘텀으로 폭발적 구간 포착. 초단기 보유.",
        created_by="system",
        strategies={
            "tick_momentum": {
                "enabled": True, "weight": 0.8,
                "params": {"window": 10, "threshold": 0.7}
            },
            "volume_spike": {
                "enabled": True, "weight": 1.2,
                "params": {"spike_mult": 2.5}
            },
            "orderbook_imbalance": {
                "enabled": False, "weight": 1.0,
                "params": {"threshold": 2.0}
            },
            "vwap_deviation": {
                "enabled": False, "weight": 1.0,
                "params": {"window": 60, "entry_deviation": 0.3}
            },
            "bollinger_scalp": {
                "enabled": False, "weight": 1.0,
                "params": {"window": 30, "std": 2.0}
            },
            "rsi_extreme": {
                "enabled": False, "weight": 1.0,
                "params": {"period": 10, "oversold": 25.0, "overbought": 75.0}
            },
            "ema_crossover": {
                "enabled": False, "weight": 1.0,
                "params": {"fast_period": 9, "slow_period": 21}
            },
            "trade_intensity": {
                "enabled": True, "weight": 1.0,
                "params": {"window": 20, "buy_threshold": 1.8, "sell_threshold": 0.55}
            },
            "tick_acceleration": {
                "enabled": False, "weight": 1.0,
                "params": {"window": 15, "threshold": 0.04}
            },
        },
        risk={
            "stop_loss_pct": 0.4,
            "take_profit_pct": 0.8,
            "trailing_stop_pct": 0.3,
            "use_trailing_stop": False,
            "max_position_count": 3,
            "max_daily_loss": 50000,
            "max_hold_seconds": 90,
            "cooldown_seconds": 2,
            "max_daily_trades": 80,
            "max_investment_per_trade": 500000,
        },
        order={
            "quantity": 10,
            "price_type": "market",
            "min_consensus": 2,
        },
        stock_filter={
            "min_price": 3000,
            "max_price": 60000,
            "min_volume": 800000,
            "min_volatility_pct": 1.5,
            "max_volatility_pct": 8.0,
            "min_trade_value": 3_000_000_000,
            "min_tick_frequency": 20,
            "max_spread_pct": 0.3,
            "max_target_stocks": 5,
        },
        performance=_default_performance(),
    )


DEFAULT_PRESETS = {
    "aggressive": _make_aggressive,
    "stable": _make_stable,
    "trend_follow": _make_trend_follow,
    "counter_trend": _make_counter_trend,
    "volume_burst": _make_volume_burst,
}


# ═══════════════════════════════════════════════════════
#  PresetManager
# ═══════════════════════════════════════════════════════

class PresetManager:
    """프리셋 CRUD + 자동 전환 관리"""

    def __init__(self):
        _PRESETS_DIR.mkdir(parents=True, exist_ok=True)
        self._registry = self._load_registry()

        # 프리셋이 없으면 기본 프리셋 생성
        if not self._registry.get("presets"):
            self.create_default_presets()

        # 활성 프리셋 로드
        active_name = self._registry.get("active_preset", "aggressive")
        self._active: Optional[SkillPreset] = self.load_preset(active_name)
        if not self._active:
            # 활성 프리셋이 없으면 첫 번째 프리셋
            names = list(self._registry.get("presets", {}).keys())
            if names:
                self._active = self.load_preset(names[0])

        # 자동 전환 설정
        self.auto_switch_enabled = self._registry.get("auto_switch_enabled", True)
        self.auto_switch_min_trades = self._registry.get("auto_switch_min_trades", 20)
        self._last_switch_time: float = 0
        self._min_switch_interval: float = 600  # 최소 10분 간격

        logger.info(f"[PresetManager] 초기화 완료 | "
                     f"프리셋 {len(self._registry.get('presets', {}))}개 | "
                     f"활성: {self._active.display_name if self._active else 'None'}")

    # ── 레지스트리 관리 ──

    def _load_registry(self) -> dict:
        if _REGISTRY_FILE.exists():
            try:
                return json.loads(_REGISTRY_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {
            "active_preset": "aggressive",
            "auto_switch_enabled": True,
            "auto_switch_min_trades": 20,
            "presets": {},
            "switch_history": [],
        }

    def _save_registry(self):
        try:
            _REGISTRY_FILE.write_text(
                json.dumps(self._registry, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            logger.error(f"[PresetManager] 레지스트리 저장 실패: {e}")

    # ── CRUD ──

    def load_preset(self, name: str) -> Optional[SkillPreset]:
        """프리셋 파일에서 로드"""
        path = _PRESETS_DIR / f"{name}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return SkillPreset.from_dict(data)
        except Exception as e:
            logger.error(f"[PresetManager] '{name}' 로드 실패: {e}")
            return None

    def save_preset(self, preset: SkillPreset) -> bool:
        """프리셋을 파일로 저장"""
        preset.updated_at = datetime.now().isoformat()
        if not preset.created_at:
            preset.created_at = preset.updated_at

        path = _PRESETS_DIR / f"{preset.name}.json"
        try:
            path.write_text(
                json.dumps(preset.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            # 레지스트리 업데이트
            self._registry.setdefault("presets", {})[preset.name] = {
                "file": f"{preset.name}.json",
                "display_name": preset.display_name,
                "version": preset.version,
            }
            self._save_registry()
            return True
        except Exception as e:
            logger.error(f"[PresetManager] '{preset.name}' 저장 실패: {e}")
            return False

    def delete_preset(self, name: str) -> bool:
        """프리셋 삭제"""
        if name == self._registry.get("active_preset"):
            logger.error(f"[PresetManager] 활성 프리셋 '{name}'은 삭제할 수 없습니다")
            return False
        path = _PRESETS_DIR / f"{name}.json"
        try:
            if path.exists():
                path.unlink()
            self._registry.get("presets", {}).pop(name, None)
            self._save_registry()
            return True
        except Exception as e:
            logger.error(f"[PresetManager] '{name}' 삭제 실패: {e}")
            return False

    def list_presets(self) -> List[dict]:
        """모든 프리셋 요약 정보"""
        result = []
        for name in self._registry.get("presets", {}):
            preset = self.load_preset(name)
            if preset:
                perf = preset.performance
                enabled_strategies = [
                    k for k, v in preset.strategies.items() if v.get("enabled")
                ]
                result.append({
                    "name": preset.name,
                    "display_name": preset.display_name,
                    "description": preset.description,
                    "version": preset.version,
                    "created_by": preset.created_by,
                    "is_active": preset.name == self._registry.get("active_preset"),
                    "strategies": enabled_strategies,
                    "win_rate": perf.get("win_rate", 0),
                    "recent_win_rate": perf.get("recent_win_rate", 0),
                    "total_trades": perf.get("total_trades", 0),
                    "total_net_pnl": perf.get("total_net_pnl", 0),
                })
        return result

    # ── 활성 프리셋 ──

    def get_active(self) -> Optional[SkillPreset]:
        return self._active

    def switch_preset(self, name: str) -> bool:
        """런타임 프리셋 교체"""
        preset = self.load_preset(name)
        if not preset:
            logger.error(f"[PresetManager] '{name}' 프리셋을 찾을 수 없음")
            return False

        old_name = self._active.name if self._active else "none"
        self._active = preset
        self._registry["active_preset"] = name
        preset.performance["active_since"] = datetime.now().isoformat()
        preset.performance["last_used"] = datetime.now().isoformat()

        # 전환 이력 기록
        self._registry.setdefault("switch_history", []).append({
            "from": old_name,
            "to": name,
            "timestamp": datetime.now().isoformat(),
            "reason": "manual",
        })
        if len(self._registry["switch_history"]) > 100:
            self._registry["switch_history"] = self._registry["switch_history"][-100:]

        self._save_registry()
        self.save_preset(preset)
        self._last_switch_time = time.time()

        logger.info(f"[PresetManager] 프리셋 전환: {old_name} → {name} ({preset.display_name})")

        # 엔진에 적용
        self._apply_to_engine(preset)
        return True

    def _apply_to_engine(self, preset: SkillPreset):
        """프리셋 설정을 엔진에 적용"""
        try:
            from services.auto_scalper import auto_scalper
            config_dict = self._preset_to_config_dict(preset)
            auto_scalper.update_config(config_dict)
            logger.info(f"[PresetManager] 엔진 설정 적용: {preset.name}")
        except Exception as e:
            logger.error(f"[PresetManager] 엔진 적용 실패: {e}")

    @staticmethod
    def _preset_to_config_dict(preset: SkillPreset) -> dict:
        """프리셋 → AutoScalpConfig 호환 dict 변환"""
        config = {}

        # 전략 ON/OFF + 파라미터
        strategy_map = {
            "tick_momentum": ("use_tick_momentum", {
                "window": "tick_window", "threshold": "tick_momentum_threshold"
            }),
            "vwap_deviation": ("use_vwap_deviation", {
                "window": "vwap_window", "entry_deviation": "vwap_entry_deviation"
            }),
            "orderbook_imbalance": ("use_orderbook_imbalance", {
                "threshold": "imbalance_threshold"
            }),
            "bollinger_scalp": ("use_bollinger_scalp", {
                "window": "bb_window", "std": "bb_std"
            }),
            "rsi_extreme": ("use_rsi_extreme", {
                "period": "rsi_period", "oversold": "rsi_oversold", "overbought": "rsi_overbought"
            }),
            "volume_spike": ("use_volume_spike", {
                "spike_mult": "volume_spike_mult"
            }),
            "ema_crossover": ("use_ema_crossover", {}),
            "trade_intensity": ("use_trade_intensity", {}),
            "tick_acceleration": ("use_tick_acceleration", {}),
        }

        for strat_name, (config_key, param_map) in strategy_map.items():
            strat = preset.strategies.get(strat_name, {})
            config[config_key] = strat.get("enabled", False)
            for param_key, config_param in param_map.items():
                val = strat.get("params", {}).get(param_key)
                if val is not None:
                    config[config_param] = val

        # 리스크 설정
        config.update(preset.risk)

        # 주문 설정
        if "quantity" in preset.order:
            config["order_quantity"] = preset.order["quantity"]
        if "price_type" in preset.order:
            config["price_type"] = preset.order["price_type"]
        if "min_consensus" in preset.order:
            config["min_consensus"] = preset.order["min_consensus"]

        # 종목 필터
        sf = preset.stock_filter
        for key in ["min_price", "max_price", "min_volume", "min_volatility_pct",
                     "max_volatility_pct", "max_target_stocks"]:
            if key in sf:
                config[key] = sf[key]

        return config

    # ── 성과 추적 ──

    def record_trade(self, preset_name: str, net_pnl: float):
        """거래 성과 기록"""
        preset = self.load_preset(preset_name)
        if not preset:
            return

        perf = preset.performance
        perf["total_trades"] += 1
        perf["total_net_pnl"] += net_pnl
        if net_pnl > 0:
            perf["wins"] += 1
        else:
            perf["losses"] += 1

        # 최근 20건 유지
        perf["recent_20_trades"].append(round(net_pnl, 0))
        if len(perf["recent_20_trades"]) > 20:
            perf["recent_20_trades"] = perf["recent_20_trades"][-20:]

        # 승률 계산
        tc = perf["total_trades"]
        if tc > 0:
            perf["win_rate"] = round(perf["wins"] / tc * 100, 1)

        recent = perf["recent_20_trades"]
        if len(recent) >= 5:
            recent_wins = sum(1 for p in recent if p > 0)
            perf["recent_win_rate"] = round(recent_wins / len(recent) * 100, 1)

        perf["last_used"] = datetime.now().isoformat()
        self.save_preset(preset)

    def get_best_preset(self) -> Optional[str]:
        """최근 20건 승률이 가장 높은 프리셋 반환"""
        best_name = None
        best_rate = -1

        for name in self._registry.get("presets", {}):
            preset = self.load_preset(name)
            if not preset:
                continue
            perf = preset.performance
            if len(perf.get("recent_20_trades", [])) < 5:
                continue  # 데이터 부족
            rate = perf.get("recent_win_rate", 0)
            if rate > best_rate:
                best_rate = rate
                best_name = name

        return best_name

    def check_auto_switch(self) -> Optional[str]:
        """
        자동 전환 체크. 조건:
        1. 자동 전환 활성화
        2. 현재 프리셋 최근 승률 < 40%
        3. 최소 20건 거래 완료
        4. 마지막 전환 후 10분 이상 경과
        5. 더 나은 프리셋이 존재

        Returns: 전환할 프리셋 이름 또는 None
        """
        if not self.auto_switch_enabled or not self._active:
            return None

        # 핑퐁 방지
        if time.time() - self._last_switch_time < self._min_switch_interval:
            return None

        perf = self._active.performance
        recent = perf.get("recent_20_trades", [])
        if len(recent) < self.auto_switch_min_trades:
            return None

        current_rate = perf.get("recent_win_rate", 50)
        if current_rate >= 40:
            return None  # 현재 프리셋 충분히 좋음

        # 더 나은 프리셋 찾기
        best = self.get_best_preset()
        if best and best != self._active.name:
            best_preset = self.load_preset(best)
            if best_preset:
                best_rate = best_preset.performance.get("recent_win_rate", 0)
                if best_rate > current_rate + 10:  # 10%p 이상 차이
                    return best

        return None

    # ── 기본 프리셋 생성 / 리셋 ──

    def create_default_presets(self):
        """5개 기본 프리셋 생성"""
        now = datetime.now().isoformat()
        for name, factory in DEFAULT_PRESETS.items():
            preset = factory()
            preset.created_at = now
            preset.updated_at = now
            self.save_preset(preset)
        self._registry["active_preset"] = "aggressive"
        self._save_registry()
        logger.info(f"[PresetManager] 기본 프리셋 {len(DEFAULT_PRESETS)}개 생성 완료")

    def reset_all(self):
        """전체 리셋: 모든 프리셋 + 성과 초기화"""
        import shutil

        # 기존 프리셋 디렉토리 삭제
        if _PRESETS_DIR.exists():
            shutil.rmtree(_PRESETS_DIR)
        _PRESETS_DIR.mkdir(parents=True, exist_ok=True)

        # brain.json 초기화
        brain_file = _PRESETS_DIR.parent / "brain.json"
        if brain_file.exists():
            brain_file.unlink()

        # auto_scalp_config.json 초기화
        config_file = _PRESETS_DIR.parent / "auto_scalp_config.json"
        if config_file.exists():
            config_file.unlink()

        # ai_reviews.json 초기화
        reviews_file = _PRESETS_DIR.parent / "ai_reviews.json"
        if reviews_file.exists():
            reviews_file.unlink()

        # 레지스트리 초기화
        self._registry = {
            "active_preset": "aggressive",
            "auto_switch_enabled": True,
            "auto_switch_min_trades": 20,
            "presets": {},
            "switch_history": [],
        }

        # 기본 프리셋 재생성
        self.create_default_presets()
        self._active = self.load_preset("aggressive")

        logger.info("[PresetManager] 전체 리셋 완료 - 기본 프리셋으로 재시작")

    def get_status(self) -> dict:
        """전체 상태"""
        return {
            "active_preset": self._active.name if self._active else None,
            "active_display_name": self._active.display_name if self._active else None,
            "auto_switch_enabled": self.auto_switch_enabled,
            "preset_count": len(self._registry.get("presets", {})),
            "switch_history": self._registry.get("switch_history", [])[-10:],
        }


# 싱글톤
preset_manager = PresetManager()
