"""
Auto Scalping API Router
완전 자동 스캘핑 시스템 제어 엔드포인트

아키텍처:
  실시간 매매: 룰 기반 엔진 (지연 없음)
  AI 리뷰: 1일 1~2회 수동/스케줄 호출 (Claude API)
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from services.auto_scalper import auto_scalper
from services.ai_advisor import ai_advisor
from services.trade_analyzer import trade_brain
from services.skill_preset import preset_manager
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auto-scalping", tags=["AutoScalping"])


class AutoScalpConfigUpdate(BaseModel):
    config: dict


@router.get("/status")
def get_status():
    """전체 자동 스캘핑 상태 (포지션, 시그널, 통계, 설정 포함)"""
    return auto_scalper.get_status()


@router.post("/start")
async def start_auto_scalping():
    """자동 스캘핑 시작 (종목 검색 → 구독 → 매매 자동 진행)"""
    from services.kiwoom_ws import kiwoom_ws_manager
    from services.kiwoom_provider import kiwoom

    # 인증 확인
    token = kiwoom.get_access_token()
    if not token:
        return {"success": False, "message": "키움 인증이 필요합니다. 먼저 로그인하세요."}

    # WebSocket 연결 확인 및 자동 연결 시도
    import asyncio
    if not kiwoom_ws_manager.connected:
        logger.warning("WebSocket not connected. Attempting auto-connect for auto scalping...")
        if not kiwoom_ws_manager.keep_running:
            kiwoom_ws_manager.keep_running = True
            asyncio.create_task(kiwoom_ws_manager.run())
        for _ in range(20):
            if kiwoom_ws_manager.connected:
                break
            await asyncio.sleep(0.5)
        if not kiwoom_ws_manager.connected:
            return {"success": False, "message": "WebSocket 연결 실패. 키움 인증 상태를 확인하세요."}

    # WebSocket 로그인 완료까지 대기 (연결 != 로그인)
    if not kiwoom_ws_manager.logged_in_event.is_set():
        logger.info("WS connected but login not yet complete. Waiting...")
        try:
            await asyncio.wait_for(kiwoom_ws_manager.logged_in_event.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            logger.error("WS login timed out (10s)")
            return {"success": False, "message": "WebSocket 로그인 시간 초과. 키움 인증 상태를 확인하세요."}

    result = await auto_scalper.start()

    # 엔진 시작 성공 시 → 감시 종목 실시간 구독 (중복 호출이지만 안전장치)
    if result.get("success") and result.get("targets"):
        await kiwoom_ws_manager.subscribe_stocks(result["targets"], append=True)
        logger.info(f"Auto scalper targets subscribed to WS: {result['targets']}")

    return result


@router.post("/stop")
async def stop_auto_scalping():
    """자동 스캘핑 중지 (모든 포지션 청산)"""
    result = await auto_scalper.stop()
    return result


@router.get("/config")
def get_config():
    """현재 자동 스캘핑 설정 조회"""
    return auto_scalper.config.to_dict()


@router.post("/config")
def update_config(req: AutoScalpConfigUpdate):
    """자동 스캘핑 설정 업데이트"""
    try:
        auto_scalper.update_config(req.config)
        return {"success": True, "message": "설정 업데이트 완료", "config": auto_scalper.config.to_dict()}
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.get("/signals")
def get_signals():
    """최근 시그널 목록"""
    return {"signals": list(auto_scalper.signal_log)}


@router.get("/trades")
def get_trades():
    """거래 내역"""
    return {
        "trades": [
            {
                "code": t.code, "side": t.side,
                "entry_price": t.entry_price, "exit_price": t.exit_price,
                "quantity": t.quantity,
                "gross_pnl": t.gross_pnl, "net_pnl": t.net_pnl,
                "commission": round(t.commission, 0),
                "pnl_pct": t.pnl_pct,
                "strategy": t.strategy,
                "hold_seconds": t.hold_seconds,
                "exit_reason": t.exit_reason,
                "entry_time": t.entry_time, "exit_time": t.exit_time,
            }
            for t in auto_scalper.trade_history
        ],
        "total": len(auto_scalper.trade_history),
    }


@router.get("/positions")
def get_positions():
    """현재 보유 포지션"""
    status = auto_scalper.get_status()
    return {"positions": status["positions"]}


@router.get("/targets")
def get_targets():
    """현재 감시 중인 종목 목록 및 점수"""
    return {
        "targets": auto_scalper.scanner.current_targets,
        "scores": auto_scalper.scanner.stock_scores,
    }


@router.post("/scan")
async def force_scan():
    """종목 강제 재검색"""
    if not auto_scalper.running:
        return {"success": False, "message": "엔진이 실행 중이 아닙니다."}

    from services.kiwoom_ws import kiwoom_ws_manager

    old_targets = list(auto_scalper.scanner.current_targets)
    await auto_scalper._do_scan()
    new_targets = auto_scalper.scanner.current_targets

    # 새 종목 구독 (로그인 상태 확인 포함)
    added = [c for c in new_targets if c not in old_targets]
    if added and kiwoom_ws_manager.connected and kiwoom_ws_manager.logged_in_event.is_set():
        await kiwoom_ws_manager.subscribe_stocks(added, append=True)
    elif new_targets and kiwoom_ws_manager.connected and kiwoom_ws_manager.logged_in_event.is_set():
        # 새 종목이 없어도 전체 타겟이 구독됐는지 확인
        await kiwoom_ws_manager.subscribe_stocks(new_targets, append=True)

    return {
        "success": True,
        "previous": old_targets,
        "current": new_targets,
        "added": added,
    }


# ════════════════════════════════════════════
#  AI 감독관 엔드포인트 (1일 1~2회 수동/스케줄 호출)
# ════════════════════════════════════════════

class ReviewApplyRequest(BaseModel):
    parameter_changes: dict


@router.get("/ai-status")
def get_ai_status():
    """AI 감독관 상태 조회"""
    return ai_advisor.get_status()


@router.post("/ai-review/daily")
def run_daily_review():
    """
    일간 전략 리뷰 실행 (Claude API 호출)
    오늘의 거래 성과를 분석하고 파라미터 조정안 제시
    """
    if not ai_advisor.available:
        return {"success": False, "message": "ANTHROPIC_API_KEY가 설정되지 않았습니다."}

    trade_history = [
        {
            "code": t.code, "strategy": t.strategy,
            "net_pnl": t.net_pnl, "pnl_pct": t.pnl_pct,
            "hold_seconds": t.hold_seconds,
            "exit_reason": t.exit_reason,
        }
        for t in auto_scalper.trade_history
    ]
    stats = dict(auto_scalper.stats)
    brain_data = trade_brain.brain if trade_brain else {}
    current_config = auto_scalper.config.to_dict()

    result = ai_advisor.daily_strategy_review(
        trade_history, stats, brain_data, current_config
    )

    if "error" in result:
        return {"success": False, "message": result["error"]}

    return {
        "success": True,
        "review": result,
        "message": "일간 리뷰 완료. 파라미터 변경을 적용하려면 /ai-review/apply를 호출하세요.",
    }


@router.post("/ai-review/weekly")
def run_weekly_review():
    """
    주간 심층 리뷰 실행 (Claude API 호출)
    일주일 전략 트렌드 분석 및 근본적 전략 재설계 검토
    """
    if not ai_advisor.available:
        return {"success": False, "message": "ANTHROPIC_API_KEY가 설정되지 않았습니다."}

    brain_data = trade_brain.brain if trade_brain else {}
    current_config = auto_scalper.config.to_dict()
    weekly_trades = [
        {
            "code": t.code, "strategy": t.strategy,
            "net_pnl": t.net_pnl, "pnl_pct": t.pnl_pct,
            "hold_seconds": t.hold_seconds,
            "exit_reason": t.exit_reason,
        }
        for t in auto_scalper.trade_history
    ]

    result = ai_advisor.weekly_deep_review(brain_data, current_config, weekly_trades)

    if "error" in result:
        return {"success": False, "message": result["error"]}

    return {
        "success": True,
        "review": result,
        "message": "주간 심층 리뷰 완료.",
    }


@router.post("/ai-review/apply")
def apply_review_changes(req: ReviewApplyRequest):
    """AI 리뷰 결과의 파라미터 변경을 엔진에 적용"""
    result = ai_advisor.apply_review_changes(req.parameter_changes)
    return {"success": True, **result}


@router.post("/ai-review/apply-latest")
def apply_latest_review():
    """가장 최근 리뷰의 파라미터 변경을 엔진에 자동 적용"""
    if not ai_advisor.last_review_result:
        return {"success": False, "message": "적용할 리뷰 결과가 없습니다."}

    changes = ai_advisor.last_review_result.get("parameter_changes", {})
    if not changes:
        return {"success": True, "message": "변경할 파라미터가 없습니다.", "applied": {}}

    result = ai_advisor.apply_review_changes(changes)
    return {"success": True, **result}


@router.get("/ai-review/history")
def get_review_history(limit: int = 20):
    """AI 리뷰 히스토리 조회"""
    return {"reviews": ai_advisor.get_reviews(limit)}


# ════════════════════════════════════════════
#  프리셋 관리 엔드포인트
# ════════════════════════════════════════════

class PresetCreateRequest(BaseModel):
    name: str
    display_name: str
    description: str = ""
    strategies: dict = {}
    risk: dict = {}
    order: dict = {}
    stock_filter: dict = {}


class PresetUpdateRequest(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    strategies: Optional[dict] = None
    risk: Optional[dict] = None
    order: Optional[dict] = None
    stock_filter: Optional[dict] = None


@router.get("/presets")
def list_presets():
    """프리셋 목록 + 성과"""
    return {"presets": preset_manager.list_presets()}


@router.get("/presets/{name}")
def get_preset(name: str):
    """프리셋 상세"""
    preset = preset_manager.load_preset(name)
    if not preset:
        return {"success": False, "message": f"프리셋 '{name}'을 찾을 수 없습니다."}
    return {"success": True, "preset": preset.to_dict()}


@router.post("/presets")
def create_preset(req: PresetCreateRequest):
    """새 프리셋 생성"""
    from services.skill_preset import SkillPreset
    preset = SkillPreset(
        name=req.name,
        display_name=req.display_name,
        description=req.description,
        created_by="user",
        strategies=req.strategies,
        risk=req.risk,
        order=req.order,
        stock_filter=req.stock_filter,
    )
    success = preset_manager.save_preset(preset)
    return {"success": success, "message": "프리셋 생성 완료" if success else "저장 실패"}


@router.put("/presets/{name}")
def update_preset(name: str, req: PresetUpdateRequest):
    """프리셋 수정"""
    preset = preset_manager.load_preset(name)
    if not preset:
        return {"success": False, "message": f"프리셋 '{name}'을 찾을 수 없습니다."}

    if req.display_name is not None:
        preset.display_name = req.display_name
    if req.description is not None:
        preset.description = req.description
    if req.strategies is not None:
        preset.strategies = req.strategies
    if req.risk is not None:
        preset.risk = req.risk
    if req.order is not None:
        preset.order = req.order
    if req.stock_filter is not None:
        preset.stock_filter = req.stock_filter

    preset.version += 1
    success = preset_manager.save_preset(preset)
    return {"success": success, "preset": preset.to_dict()}


@router.delete("/presets/{name}")
def delete_preset(name: str):
    """프리셋 삭제"""
    success = preset_manager.delete_preset(name)
    return {"success": success}


@router.post("/presets/{name}/activate")
def activate_preset(name: str):
    """프리셋 활성화 (런타임 교체)"""
    success = auto_scalper.switch_preset(name)
    if success:
        return {"success": True, "message": f"프리셋 '{name}' 활성화 완료", "active": name}
    return {"success": False, "message": f"프리셋 '{name}' 활성화 실패"}


@router.post("/presets/{name}/clone")
def clone_preset(name: str):
    """프리셋 복제"""
    preset = preset_manager.load_preset(name)
    if not preset:
        return {"success": False, "message": f"프리셋 '{name}'을 찾을 수 없습니다."}

    from services.skill_preset import SkillPreset
    clone = SkillPreset.from_dict(preset.to_dict())
    clone.name = f"{name}_copy"
    clone.display_name = f"{preset.display_name} (복사본)"
    clone.created_by = "user"
    clone.version = 1
    clone.performance = {
        "total_trades": 0, "wins": 0, "losses": 0, "total_net_pnl": 0,
        "recent_20_trades": [], "win_rate": 0, "recent_win_rate": 0,
        "last_used": "", "active_since": "",
    }
    success = preset_manager.save_preset(clone)
    return {"success": success, "new_name": clone.name}


@router.post("/presets/{name}/optimize")
def optimize_preset(name: str):
    """AI 프리셋 최적화"""
    if not ai_advisor.available:
        return {"success": False, "message": "ANTHROPIC_API_KEY가 설정되지 않았습니다."}
    result = ai_advisor.optimize_preset(name)
    return result


@router.get("/presets/auto-switch/status")
def get_auto_switch_status():
    """자동 전환 상태"""
    return {
        "enabled": preset_manager.auto_switch_enabled,
        "min_trades": preset_manager.auto_switch_min_trades,
        "active_preset": preset_manager.get_active().name if preset_manager.get_active() else None,
        "best_preset": preset_manager.get_best_preset(),
    }


@router.post("/presets/auto-switch/toggle")
def toggle_auto_switch():
    """자동 전환 ON/OFF"""
    preset_manager.auto_switch_enabled = not preset_manager.auto_switch_enabled
    preset_manager._registry["auto_switch_enabled"] = preset_manager.auto_switch_enabled
    preset_manager._save_registry()
    return {"enabled": preset_manager.auto_switch_enabled}


@router.post("/reset-all")
async def reset_all():
    """전체 리셋: 엔진 정지 + brain + config + 프리셋 전부 초기화"""
    # 엔진 정지
    if auto_scalper.running:
        await auto_scalper.stop()

    # 프리셋 매니저 리셋 (brain.json, config, presets 전부 삭제 후 재생성)
    preset_manager.reset_all()

    # trade_brain 재초기화
    try:
        trade_brain.brain = trade_brain._default_brain()
        trade_brain._save_brain()
    except Exception:
        pass

    # auto_scalper 재초기화
    auto_scalper.config = auto_scalper.config.__class__()
    auto_scalper.strategy = auto_scalper.strategy.__class__(auto_scalper.config)
    auto_scalper.risk = auto_scalper.risk.__class__(auto_scalper.config)
    auto_scalper.active_preset_name = "aggressive"
    auto_scalper.stats = {
        "started_at": None, "total_signals": 0, "total_trades": 0,
        "wins": 0, "losses": 0,
        "total_gross_pnl": 0.0, "total_net_pnl": 0.0, "total_commission": 0.0,
    }
    auto_scalper.trade_history.clear()
    auto_scalper.signal_log.clear()

    return {
        "success": True,
        "message": "전체 리셋 완료. 5개 기본 프리셋으로 재시작합니다.",
        "presets": preset_manager.list_presets(),
    }
