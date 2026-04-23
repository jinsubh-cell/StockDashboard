import asyncio
import websockets
import json
import logging
from datetime import datetime
from services.kiwoom_provider import kiwoom

logger = logging.getLogger(__name__)

SOCKET_URL = 'wss://api.kiwoom.com:10000/api/dostk/websocket'

class KiwoomWebSocketManager:
    def __init__(self, uri):
        self.uri = uri
        self.websocket = None
        self.connected = False
        self.keep_running = True
        self.logged_in_event = asyncio.Event()
        self.subscribed_codes = set()
        # 재연결 시 복구용 백업 (connect()에서 subscribed_codes를 clear하기 전에 여기로 옮김)
        self._pending_resubscribe: set = set()
        # 다음 재연결까지 대기 초(특수 이벤트 후 일시 백오프). run()에서 소모.
        self._reconnect_backoff: int = 0

        # Debug: recent WS messages log
        from collections import deque
        self.ws_msg_log = deque(maxlen=30)
        self.ws_msg_count = 0

        # In-memory store for real-time stock prices updated by the websocket
        # Format: {"005930": {"price": 187400, "change": 13900, "change_pct": 8.01, "volume": 29497246, "updated_at": timestamp}}
        self.realtime_data = {}

        # Order book (호가) data: {"005930": {"bid": price, "ask": price, "bid_qty": qty, "ask_qty": qty, ...}}
        self.orderbook_data = {}

        # Execution (체결) data: {"005930": {"volume": qty, "price": price, "updated_at": timestamp}}
        self.execution_data = {}

        # Watchdog: last time a message was received from the WS server
        self.last_msg_time = 0.0
        # Watchdog timeout: if no message received for this many seconds, force reconnect
        self.watchdog_timeout = 120

        # Post-login callbacks (재연결 후 자동 재구독 등)
        # 각 callback은 coroutine function. LOGIN 성공 직후 create_task로 실행.
        self._post_login_callbacks: list = []

    def register_post_login_callback(self, coro_func):
        """LOGIN 성공 시 호출할 async 콜백 등록. 중복 등록 방지."""
        if coro_func not in self._post_login_callbacks:
            self._post_login_callbacks.append(coro_func)

    async def connect(self):
        # Check if Kiwoom auth is available before attempting WS connection
        if not kiwoom.is_auth_available:
            logger.info("Kiwoom auth not available, skipping WS connection.")
            self.connected = False
            return

        # Clear stale state. 이전 구독은 _pending_resubscribe로 백업해두고
        # LOGIN 성공 직후 자동 재구독한다 (외부 콜백 유무와 무관하게 WS 레이어에서 복구 보장)
        self.logged_in_event.clear()
        if self.subscribed_codes:
            self._pending_resubscribe = set(self.subscribed_codes)
            logger.info(f"[WS] 재연결 대비 구독 백업: {len(self._pending_resubscribe)}개")
        self.subscribed_codes.clear()

        try:
            # Always try to get a fresh/valid token before connecting
            loop = asyncio.get_event_loop()
            token = await loop.run_in_executor(None, kiwoom.get_access_token)

            if not token:
                logger.warning("Cannot connect WS: No Kiwoom access token available. Will retry later.")
                self.connected = False
                return

            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            self.websocket = await websockets.connect(self.uri, additional_headers=headers)
            self.connected = True
            logger.info("Kiwoom WebSocket Connected.")

            login_packet = {
                'trnm': 'LOGIN',
                'token': token
            }
            await self.send_message(login_packet)

        except Exception as e:
            logger.error(f'Kiwoom WS Connect Error: {e}')
            self.connected = False

    async def send_message(self, message):
        if not self.connected or self.websocket is None:
            logger.warning("Cannot send message, WS not connected")
            return
            
        if not isinstance(message, str):
            message = json.dumps(message)
        await self.websocket.send(message)
        logger.debug(f'WS Sent: {message}')

    async def receive_messages(self):
        import time
        self.last_msg_time = time.time()
        while self.keep_running and self.connected and self.websocket is not None:
            try:
                response = json.loads(await asyncio.wait_for(self.websocket.recv(), timeout=30.0))
                self.last_msg_time = time.time()
                self.ws_msg_count += 1
                trnm = response.get('trnm', 'UNKNOWN')
                if trnm == 'REAL':
                    data_list = response.get('data', [])
                    first_item = data_list[0] if data_list else {}
                    item_keys = list(first_item.keys()) if isinstance(first_item, dict) else []
                    vals = first_item.get('values', {}) if isinstance(first_item, dict) else {}
                    self.ws_msg_log.append({
                        "n": self.ws_msg_count,
                        "trnm": trnm,
                        "item_keys": item_keys,
                        "all_fid_keys": sorted(vals.keys()),
                        "values": vals,
                        "grp_no": response.get('grp_no', ''),
                        "data_cnt": len(data_list),
                    })
                else:
                    self.ws_msg_log.append({
                        "n": self.ws_msg_count,
                        "trnm": trnm,
                        "keys": list(response.keys())[:8],
                        "preview": str(response)[:300],
                    })
                if self.ws_msg_count <= 10 or self.ws_msg_count % 200 == 0:
                    logger.info(f"WS msg #{self.ws_msg_count}: trnm={trnm}")

                if response.get('trnm') == 'LOGIN':
                    if response.get('return_code') != 0:
                        logger.error(f"WS Login Failed: {response.get('return_msg')}")
                        await self.disconnect(permanent=False)
                    else:
                        logger.info('WS Login Successful.')
                        self.logged_in_event.set()
                        # 1) WS 레이어 자체 자동 재구독 (외부 콜백 실패에도 견고)
                        if self._pending_resubscribe:
                            codes = list(self._pending_resubscribe)
                            self._pending_resubscribe = set()
                            logger.info(f"[WS] 재연결 자동 재구독 실행: {len(codes)}개 {codes[:5]}...")
                            asyncio.create_task(self.subscribe_stocks(codes, append=False))
                        # 2) Post-login 콜백 실행 (auto_scalper 등 외부 훅)
                        for cb in list(self._post_login_callbacks):
                            try:
                                asyncio.create_task(cb())
                            except Exception as cb_err:
                                logger.error(f"WS post-login callback error: {cb_err}")

                elif response.get('trnm') == 'PING':
                    await self.send_message(response)

                elif response.get('trnm') == 'SYSTEM':
                    code = response.get('code')
                    msg = response.get('message', '')
                    logger.error(f"WS SYSTEM ERROR [{code}]: {msg}")
                    # R10001은 메시지에 따라 의미가 다름:
                    #  - "동일한 App key로 접속" → 중복 세션 (일시적, 재연결 필요)
                    #  - 그 외 → 실제 키 오류 (영구 차단)
                    if code == 'R10001':
                        if '동일한' in msg or '중복' in msg or 'App key' in msg and '접속' in msg:
                            logger.warning("[WS] 중복 세션 감지 → 30초 후 재연결 시도")
                            self._reconnect_backoff = 30
                            await self.disconnect(permanent=False)
                        else:
                            logger.error("Stopping WS reconnect due to invalid App Key for WebSockets.")
                            await self.disconnect(permanent=True)

                elif response.get('trnm') == 'REG':
                    logger.info(f"WS REG response: return_code={response.get('return_code')}, msg={response.get('return_msg')}")

                elif response.get('trnm') == 'REAL':
                    # Parse REAL messages - FID-based format
                    # Format: {"trnm":"REAL", "data":[{"values":{FID:val,...}, "type":"0A"|"0B", "item":"종목코드", "name":"종목명"},...]}
                    data_arr = response.get('data', [])
                    # Fallback for old body-based format
                    if not data_arr and 'body' in response:
                        body = response['body']
                        data_arr = body.get('data', [])

                    if isinstance(data_arr, list):
                        for item in data_arr:
                            if not isinstance(item, dict):
                                continue

                            msg_type = item.get('type', '')
                            code = item.get('item', '') or item.get('stk_cd', '') or item.get('code', '')
                            vals = item.get('values', {})

                            # If no 'values', the item itself is the flat dict (old format)
                            if not vals and not item.get('type'):
                                code = item.get('stk_cd', '') or item.get('code', '')
                                vals = item

                            if not code:
                                continue

                            # 0A: 주식호가 (Order Book)
                            if msg_type == '0A':
                                try:
                                    # FID-based: 27=매수호가1, 28=매도호가1, 41=매수잔량1, 61=매도잔량1
                                    # Also try named keys for compatibility
                                    bid = int(str(vals.get("27", vals.get("bid_prc1", "0"))).replace('+','').replace('-','').strip() or 0)
                                    ask = int(str(vals.get("28", vals.get("ask_prc1", "0"))).replace('+','').replace('-','').strip() or 0)
                                    bid_qty = int(str(vals.get("41", vals.get("bid_qty1", "0"))).replace('+','').replace('-','').strip() or 0)
                                    ask_qty = int(str(vals.get("61", vals.get("ask_qty1", "0"))).replace('+','').replace('-','').strip() or 0)
                                    total_bid_qty = int(str(vals.get("121", vals.get("total_bid_qty", "0"))).replace('+','').replace('-','').strip() or 0)
                                    total_ask_qty = int(str(vals.get("125", vals.get("total_ask_qty", "0"))).replace('+','').replace('-','').strip() or 0)

                                    self.orderbook_data[code] = {
                                        "code": code,
                                        "bid": bid, "ask": ask,
                                        "bid_qty": bid_qty or 0, "ask_qty": ask_qty or 0,
                                        "total_bid_qty": total_bid_qty or bid_qty,
                                        "total_ask_qty": total_ask_qty or ask_qty,
                                        "updated_at": datetime.now().timestamp(),
                                    }
                                except Exception as err:
                                    logger.debug(f"Error parsing WS REAL 0A: {err}")

                            # 0B: 주식체결 (Tick Execution)
                            elif msg_type == '0B':
                                try:
                                    # FID 10=현재가, 11=전일대비, 12=등락률, 13=누적거래량, 15=체결량
                                    raw_price = str(vals.get("10", vals.get("cur_prc", "0")))
                                    raw_change = str(vals.get("11", vals.get("pred_pre", "0")))
                                    raw_pct = str(vals.get("12", vals.get("flu_rt", "0")))
                                    raw_vol = str(vals.get("15", vals.get("13", vals.get("trde_qty", "0"))))

                                    price = int(raw_price.replace('+','').replace('-','').strip() or 0)
                                    change = int(raw_change.replace('+','').replace('-','').strip() or 0)
                                    change_pct = float(raw_pct.replace('+','').replace('-','').strip() or 0)
                                    volume = int(raw_vol.replace('+','').replace('-','').strip() or 0)

                                    # Determine sign from raw strings
                                    if raw_pct.startswith('-'):
                                        change = -change
                                        change_pct = -change_pct

                                    if price <= 0:
                                        continue

                                    self.realtime_data[code] = {
                                        "code": code,
                                        "price": price,
                                        "change": change,
                                        "change_pct": change_pct,
                                        "volume": volume,
                                        "updated_at": datetime.now().timestamp()
                                    }

                                    # Feed scalping engine with tick data
                                    try:
                                        from services.scalping_engine import scalping_engine, Tick
                                        ob = self.orderbook_data.get(code, {})
                                        tick = Tick(
                                            code=code, price=price, volume=volume,
                                            timestamp=datetime.now().timestamp(),
                                            bid=ob.get("bid", 0), ask=ob.get("ask", 0),
                                            bid_qty=ob.get("total_bid_qty", 0),
                                            ask_qty=ob.get("total_ask_qty", 0),
                                        )
                                        scalping_engine.on_tick(tick)
                                    except Exception as se:
                                        logger.debug(f"Scalping engine tick error: {se}")

                                    # Feed auto scalper with tick data
                                    try:
                                        from services.auto_scalper import auto_scalper, Tick as AutoTick
                                        ob = self.orderbook_data.get(code, {})
                                        auto_tick = AutoTick(
                                            code=code, price=price, volume=volume,
                                            timestamp=datetime.now().timestamp(),
                                            bid=ob.get("bid", 0), ask=ob.get("ask", 0),
                                            bid_qty=ob.get("total_bid_qty", 0),
                                            ask_qty=ob.get("total_ask_qty", 0),
                                        )
                                        auto_scalper.on_tick(auto_tick)
                                    except Exception as ae:
                                        logger.debug(f"Auto scalper tick error: {ae}")

                                except Exception as err:
                                    logger.warning(f"Error parsing WS REAL 0B item: {err}")

            except asyncio.TimeoutError:
                # No message received for 30s — check total watchdog time
                import time
                elapsed = time.time() - self.last_msg_time
                logger.warning(f"WS recv timeout (no msg for {elapsed:.0f}s)")
                if elapsed > self.watchdog_timeout:
                    logger.error(f"WS watchdog triggered: no data for {elapsed:.0f}s. Forcing reconnect.")
                    self.connected = False
                    if self.websocket:
                        try:
                            await self.websocket.close()
                        except Exception:
                            pass
                        self.websocket = None
                    break
                # Otherwise keep waiting (PING may have reset things)
                continue
            except websockets.ConnectionClosed:
                logger.warning('Kiwoom WS Server Connection Closed.')
                self.connected = False
                break
            except Exception as e:
                logger.error(f"WS Receive Error: {e}")
                self.connected = False
                break

    async def run(self):
        while self.keep_running:
            if not self.connected or self.websocket is None:
                await self.connect()

            if self.connected:
                await self.receive_messages()
                # After receive_messages returns (disconnected), reset websocket
                self.websocket = None

            if not self.keep_running:
                break

            # 특수 백오프가 설정돼 있으면 우선 사용 (예: R10001 중복세션 → 30s)
            if self._reconnect_backoff > 0:
                delay = self._reconnect_backoff
                self._reconnect_backoff = 0
            else:
                delay = 60 if not kiwoom.is_auth_available else 2
            logger.info(f"WS reconnecting in {delay}s...")
            await asyncio.sleep(delay)

    async def disconnect(self, permanent=True):
        """Disconnect WebSocket. If permanent=False, allow reconnection via run()."""
        if permanent:
            self.keep_running = False
        self.logged_in_event.clear()
        if self.connected and self.websocket:
            try:
                await self.websocket.close()
            except Exception:
                pass
            self.connected = False
            self.websocket = None
            logger.info('Kiwoom WS Disconnected.')

    async def subscribe_stocks(self, stock_codes: list, append: bool = False):
        """
        Subscribe to real-time execution (0B) for a list of stocks.
        """
        if not stock_codes:
            return

        # Wait for login to complete (with timeout)
        logger.info("Waiting for WS Login before subscribing...")
        try:
            await asyncio.wait_for(self.logged_in_event.wait(), timeout=15.0)
        except asyncio.TimeoutError:
            logger.error("WS Login wait timed out (15s). Cannot subscribe stocks.")
            return
        
        if append:
            new_codes = [c for c in stock_codes if c not in self.subscribed_codes]
            if not new_codes:
                return  # already subscribed
            self.subscribed_codes.update(new_codes)
            logger.info(f"Appending WS subscription for {len(new_codes)} stocks.")
            stock_codes_to_send = new_codes
        else:
            self.subscribed_codes = set(stock_codes)
            stock_codes_to_send = stock_codes
            logger.info(f"Refreshing WS subscription for {len(stock_codes)} stocks.")

        # Split into chunks if needed (Kiwoom might limit max items per REG)
        chunk_size = 40
        for i in range(0, len(stock_codes_to_send), chunk_size):
            chunk = stock_codes_to_send[i:i + chunk_size]

            # format required by provided code example
            packet = {
                'trnm': 'REG',
                'grp_no': '1', # Group number
                'refresh': '0' if append else ('1' if i == 0 else '0'), # Refresh previous registrations on first chunk unless appending
                'data': [{
                    'item': chunk,
                    'type': ['0A', '0B']  # 0A: 호가, 0B: 체결
                }]
            }
            logger.info(f"WS REG sending: {len(chunk)} codes, refresh={packet['refresh']}, codes={chunk[:5]}...")
            await self.send_message(packet)
            logger.info(f"WS REG sent successfully. Total subscribed: {len(self.subscribed_codes)}")

# Global Instance
kiwoom_ws_manager = KiwoomWebSocketManager(SOCKET_URL)
