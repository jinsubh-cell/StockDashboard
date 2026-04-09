"""
Auto Scalping API Router
완전 자동 스캘핑 시스템 제어 엔드포인트
"""
from fastapi import APIRouter
from pydantic import BaseModel
from services.auto_scalper import auto_scalper
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
