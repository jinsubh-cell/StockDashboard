"""
Scalping API Router
Endpoints for controlling the scalping engine, monitoring, and configuration
"""
from fastapi import APIRouter
from pydantic import BaseModel
from services.scalping_engine import scalping_engine
from services.scalp_picker import scalp_picker
from services.kiwoom_ws import kiwoom_ws_manager
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/scalping", tags=["Scalping"])


class ScalpStartRequest(BaseModel):
    codes: list[str]  # Target stock codes


class ScalpConfigUpdate(BaseModel):
    config: dict


@router.get("/status")
def get_status():
    """Get full scalping engine status (positions, signals, trades, stats)"""
    return scalping_engine.get_status()


@router.post("/start")
async def start_scalping(req: ScalpStartRequest):
    """Start the scalping engine for target stocks"""
    if not req.codes:
        return {"success": False, "message": "대상 종목을 선택해 주세요."}

    # Ensure WebSocket is connected before starting
    if not kiwoom_ws_manager.connected:
        logger.warning("WebSocket not connected. Attempting to connect before scalping start...")
        import asyncio
        # Trigger connection if not already running
        if not kiwoom_ws_manager.keep_running:
            kiwoom_ws_manager.keep_running = True
            asyncio.create_task(kiwoom_ws_manager.run())

        # Wait up to 10 seconds for connection
        for _ in range(20):
            if kiwoom_ws_manager.connected:
                break
            await asyncio.sleep(0.5)

        if not kiwoom_ws_manager.connected:
            return {
                "success": False,
                "message": "WebSocket 연결 실패. 키움 인증 상태를 확인하세요. (실시간 데이터 수신 불가)"
            }

    # Subscribe to real-time data for these stocks (0A: 호가, 0B: 체결)
    try:
        await kiwoom_ws_manager.subscribe_stocks(req.codes, append=True)
        logger.info(f"Subscribed {len(req.codes)} stocks for scalping: {req.codes}")
    except Exception as e:
        logger.error(f"Failed to subscribe stocks for scalping: {e}")
        return {"success": False, "message": f"실시간 데이터 구독 실패: {str(e)}"}

    result = await scalping_engine.start(req.codes)
    return result


@router.post("/stop")
async def stop_scalping():
    """Stop the scalping engine and close all positions"""
    result = await scalping_engine.stop()
    return result


@router.post("/config")
def update_config(req: ScalpConfigUpdate):
    """Update scalping configuration"""
    try:
        scalping_engine.update_config(req.config)
        return {"success": True, "message": "설정이 업데이트되었습니다.", "config": scalping_engine.config.to_dict()}
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.get("/config")
def get_config():
    """Get current scalping configuration"""
    return scalping_engine.config.to_dict()


@router.get("/signals")
def get_signals():
    """Get recent signals"""
    return {"signals": list(scalping_engine.signal_log)}


@router.get("/trades")
def get_trades():
    """Get trade history"""
    return {"trades": [t.__dict__ for t in scalping_engine.trade_log]}


# ─── Stock Picker ───

@router.get("/picker/scan")
async def picker_scan(force: bool = False):
    """Scan and rank stocks for scalping suitability"""
    import asyncio
    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(None, scalp_picker.scan, force)
    return {"candidates": results, "count": len(results)}


@router.get("/picker/config")
def picker_config():
    """Get picker configuration"""
    return scalp_picker.config.to_dict()


class PickerConfigUpdate(BaseModel):
    config: dict


@router.post("/picker/config")
def update_picker_config(req: PickerConfigUpdate):
    """Update picker configuration"""
    try:
        scalp_picker.update_config(req.config)
        return {"success": True, "config": scalp_picker.config.to_dict()}
    except Exception as e:
        return {"success": False, "message": str(e)}
