"""
Trading API Router
Endpoints for stock order placement, cancellation, balance, and order history
"""
from fastapi import APIRouter
from models.schemas import OrderRequest, OrderModifyRequest, OrderCancelRequest
from services.kiwoom_provider import kiwoom
from services.kiwoom_ws import kiwoom_ws_manager
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/trading", tags=["Trading"])


@router.get("/status")
def trading_status():
    """Check if trading API is available (Kiwoom auth status)"""
    is_sim = kiwoom.is_simulation
    has_auth = kiwoom.is_auth_available
    token_ok = kiwoom.get_access_token() is not None if has_auth else False
    return {
        "available": token_ok,
        "simulation": is_sim,
        "ws_connected": kiwoom_ws_manager.connected,
        "ws_subscribed": len(kiwoom_ws_manager.subscribed_codes),
        "realtime_stocks": len(kiwoom_ws_manager.realtime_data),
        "message": "모의투자 모드" if is_sim else "실거래 모드",
        "auth_error": kiwoom._auth_fail_msg if kiwoom._auth_failed else None,
        "has_account_no": bool(kiwoom.account_no),
        "has_app_key": bool(kiwoom.app_key),
        "has_secret_key": bool(kiwoom.secret_key),
        "auth_failed": kiwoom._auth_failed,
    }


@router.post("/login")
async def login():
    """Explicitly trigger Kiwoom API login (token acquisition)"""
    if not kiwoom.app_key or not kiwoom.secret_key:
        return {
            "success": False,
            "logged_in": False,
            "message": "KIWOOM_APP_KEY / KIWOOM_SECRET_KEY 환경변수가 설정되지 않았습니다.",
        }

    # Reset auth failure state to allow retry
    kiwoom._auth_failed = False

    token = kiwoom.get_access_token()
    if token:
        # Also try to connect WebSocket if not connected
        if not kiwoom_ws_manager.connected:
            import asyncio
            # Ensure clean state before restarting
            if not kiwoom_ws_manager.keep_running:
                kiwoom_ws_manager.keep_running = True
                asyncio.create_task(kiwoom_ws_manager.run())
            # If keep_running is already True, run() loop will reconnect on its own

        return {
            "success": True,
            "logged_in": True,
            "simulation": kiwoom.is_simulation,
            "message": "로그인 성공" + (" (모의투자)" if kiwoom.is_simulation else " (실거래)"),
        }
    else:
        return {
            "success": False,
            "logged_in": False,
            "message": kiwoom._auth_fail_msg or "토큰 발급에 실패했습니다.",
        }


@router.post("/logout")
async def logout():
    """Disconnect from Kiwoom API"""
    kiwoom.access_token = None
    kiwoom.token_expiry = None
    await kiwoom_ws_manager.disconnect(permanent=True)
    return {"success": True, "message": "로그아웃 되었습니다."}


@router.get("/account-summary")
def account_summary():
    """Get a compact account summary (login status + balance overview)"""
    # Use consistent auth check: try to get a valid token
    token = kiwoom.get_access_token()
    token_ok = token is not None
    ws_connected = kiwoom_ws_manager.connected

    result = {
        "logged_in": token_ok,
        "simulation": kiwoom.is_simulation,
        "ws_connected": ws_connected,
        "has_keys": bool(kiwoom.app_key and kiwoom.secret_key and kiwoom.account_no),
        "balance": None,
        "balance_error": None,
    }

    if token_ok:
        try:
            balance = kiwoom.get_account_balance()
            if balance and "_error" in balance:
                # API returned an error (e.g. device auth failure)
                result["balance_error"] = balance["_error"]
                logger.warning(f"account-summary: Kiwoom API error: {balance['_error']}")
            elif balance:
                result["balance"] = {
                    "cash": balance["cash"],
                    "total_eval": balance["total_eval"],
                    "total_pnl": balance["total_pnl"],
                    "total_pnl_pct": balance["total_pnl_pct"],
                    "holding_count": len(balance["holdings"]),
                }
            else:
                result["balance_error"] = "잔고 조회 실패 (인증 오류)"
                logger.warning("account-summary: get_account_balance returned None")
        except Exception as e:
            result["balance_error"] = f"잔고 조회 오류: {str(e)}"
            logger.error(f"account-summary balance error: {e}")

    return result


@router.post("/order")
def place_order(req: OrderRequest):
    """Place a buy or sell order"""
    logger.info(f"Order request: {req.order_type} {req.code} qty={req.quantity} price={req.price} type={req.price_type}")

    if req.order_type not in ("buy", "sell"):
        return {"success": False, "message": "order_type은 'buy' 또는 'sell'이어야 합니다."}
    if req.quantity <= 0:
        return {"success": False, "message": "주문수량은 1 이상이어야 합니다."}
    if req.price_type == "limit" and req.price <= 0:
        return {"success": False, "message": "지정가 주문 시 가격을 입력해야 합니다."}

    result = kiwoom.place_order(
        code=req.code,
        order_type=req.order_type,
        quantity=req.quantity,
        price=req.price,
        price_type=req.price_type,
    )
    return result


@router.post("/order/modify")
def modify_order(req: OrderModifyRequest):
    """Modify an existing order"""
    logger.info(f"Modify order: {req.org_order_no} -> qty={req.quantity} price={req.price}")

    if req.quantity <= 0 or req.price <= 0:
        return {"success": False, "message": "정정 수량과 가격은 0보다 커야 합니다."}

    result = kiwoom.modify_order(
        org_order_no=req.org_order_no,
        code=req.code,
        quantity=req.quantity,
        price=req.price,
    )
    return result


@router.post("/order/cancel")
def cancel_order(req: OrderCancelRequest):
    """Cancel an existing order"""
    logger.info(f"Cancel order: {req.org_order_no} qty={req.quantity}")

    result = kiwoom.cancel_order(
        org_order_no=req.org_order_no,
        code=req.code,
        quantity=req.quantity,
    )
    return result


@router.get("/balance")
def get_balance():
    """Get account balance and holdings"""
    balance = kiwoom.get_account_balance()
    if balance is None:
        return {
            "error": "잔고 조회에 실패했습니다. 키움 인증 상태를 확인하세요.",
            "auth_available": kiwoom.is_auth_available,
            "has_token": kiwoom.access_token is not None,
            "auth_failed": kiwoom._auth_failed,
            "auth_fail_msg": kiwoom._auth_fail_msg,
        }
    if "_error" in balance:
        return {"error": balance["_error"]}
    return balance


@router.get("/balance-debug")
def get_balance_debug():
    """Debug endpoint: raw Kiwoom API response for kt00018"""
    import requests as req
    token = kiwoom.get_access_token()
    if not token:
        return {"error": "No valid token", "auth_failed": kiwoom._auth_failed, "auth_fail_msg": kiwoom._auth_fail_msg}

    url = f"{kiwoom.base_url}/api/dostk/acnt"
    payload = {
        "acnt_no": kiwoom.account_no,
        "qry_tp": "1",
        "dmst_stex_tp": "KRX",
    }
    headers = kiwoom._get_headers("kt00018")
    try:
        res = req.post(url, headers=headers, json=payload, timeout=10)
        try:
            return {"status_code": res.status_code, "response": res.json()}
        except ValueError:
            return {"status_code": res.status_code, "raw_body": res.text[:500]}
    except Exception as e:
        return {"error": str(e)}


@router.get("/orders")
def get_orders():
    """Get order history (filled, pending, cancelled)"""
    orders = kiwoom.get_order_history()
    return {"orders": orders}


@router.get("/ws-debug")
def ws_debug():
    """Debug WebSocket state"""
    from services.auto_scalper import auto_scalper
    return {
        "ws_connected": kiwoom_ws_manager.connected,
        "ws_keep_running": kiwoom_ws_manager.keep_running,
        "ws_logged_in": kiwoom_ws_manager.logged_in_event.is_set(),
        "subscribed_codes": list(kiwoom_ws_manager.subscribed_codes)[:20],
        "subscribed_count": len(kiwoom_ws_manager.subscribed_codes),
        "realtime_data_count": len(kiwoom_ws_manager.realtime_data),
        "realtime_codes": list(kiwoom_ws_manager.realtime_data.keys())[:10],
        "orderbook_count": len(kiwoom_ws_manager.orderbook_data),
        "orderbook_codes": list(kiwoom_ws_manager.orderbook_data.keys())[:10],
        "auto_scalper_running": auto_scalper.running,
        "auto_scalper_state": auto_scalper.state.value if hasattr(auto_scalper.state, 'value') else str(auto_scalper.state),
        "auto_scalper_targets": auto_scalper.scanner.current_targets,
        "auto_scalper_tick_buffers": {k: v.count for k, v in auto_scalper.tick_buffers.items()},
        "ws_msg_count": getattr(kiwoom_ws_manager, 'ws_msg_count', 0),
        "ws_msg_log": list(getattr(kiwoom_ws_manager, 'ws_msg_log', [])),
    }


@router.post("/ws-subscribe-test")
async def ws_subscribe_test():
    """Debug: manually subscribe auto scalper targets"""
    from services.auto_scalper import auto_scalper
    targets = auto_scalper.scanner.current_targets
    if not targets:
        targets = ["005930"]  # Samsung as fallback

    logger.info(f"[WS-TEST] Subscribing targets: {targets}")
    logger.info(f"[WS-TEST] WS connected={kiwoom_ws_manager.connected}, logged_in={kiwoom_ws_manager.logged_in_event.is_set()}")
    logger.info(f"[WS-TEST] Before subscribe: subscribed_codes={len(kiwoom_ws_manager.subscribed_codes)}")

    await kiwoom_ws_manager.subscribe_stocks(targets, append=True)

    logger.info(f"[WS-TEST] After subscribe: subscribed_codes={len(kiwoom_ws_manager.subscribed_codes)}")

    return {
        "subscribed": targets,
        "total_subscribed": len(kiwoom_ws_manager.subscribed_codes),
        "targets_in_subs": [t for t in targets if t in kiwoom_ws_manager.subscribed_codes],
    }


@router.get("/realtime/{code}")
def get_realtime_price(code: str):
    """Get real-time price from WebSocket data (if available)"""
    rt = kiwoom_ws_manager.realtime_data.get(code)
    ob = kiwoom_ws_manager.orderbook_data.get(code)
    if rt:
        result = {**rt}
        if ob:
            result["bid"] = ob.get("bid", 0)
            result["ask"] = ob.get("ask", 0)
            result["bid_qty"] = ob.get("bid_qty", 0)
            result["ask_qty"] = ob.get("ask_qty", 0)
        return result
    return {"error": "실시간 데이터 없음", "code": code}
