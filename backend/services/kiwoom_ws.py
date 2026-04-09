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

        # Debug: recent WS messages log
        from collections import deque
        self.ws_msg_log = deque(maxlen=30)
        self.ws_msg_count = 0

        # In-memory store for real-time stock prices updated by the websocket
        # Format: {"005930": {"price": 187400, "change": 13900, "change_pct": 8.01, "volume": 29497246, "updated_at": timestamp}}
        self.realtime_data = {}

        # Order book (호가) data: {"005930": {"bid": price, "ask": price, "bid_qty": qty, "ask_qty": qty, ...}}
        self.orderbook_data = {}

    async def connect(self):
        # Check if Kiwoom auth is available before attempting WS connection
        if not kiwoom.is_auth_available:
            logger.info("Kiwoom auth not available, skipping WS connection.")
            self.connected = False
            return

        # Clear stale state
        self.logged_in_event.clear()

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
        while self.keep_running and self.connected and self.websocket is not None:
            try:
                response = json.loads(await self.websocket.recv())
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
                        # Once logged in, we can start registering items if needed automatically
                        # Registration logic should be handled by the caller or a separate manager

                elif response.get('trnm') == 'PING':
                    await self.send_message(response)

                elif response.get('trnm') == 'SYSTEM':
                    code = response.get('code')
                    msg = response.get('message', '')
                    logger.error(f"WS SYSTEM ERROR [{code}]: {msg}")
                    # If R10001 (App key error, usually mock api key trying to access real ws), stop reconnecting
                    if code == 'R10001':
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

            # Use longer delay when auth is known to be failing
            delay = 60 if not kiwoom.is_auth_available else 5
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
