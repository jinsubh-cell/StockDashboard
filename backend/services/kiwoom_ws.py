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
        
        # In-memory store for real-time stock prices updated by the websocket
        # Format: {"005930": {"price": 187400, "change": 13900, "change_pct": 8.01, "volume": 29497246, "updated_at": timestamp}}
        self.realtime_data = {}

    async def connect(self):
        # Check if Kiwoom auth is available before attempting WS connection
        if not kiwoom.is_auth_available:
            logger.info("Kiwoom auth not available, skipping WS connection.")
            self.connected = False
            return

        try:
            # Try to get token first, before opening the socket
            token = kiwoom.access_token
            if not token or (kiwoom.token_expiry and datetime.now().timestamp() > kiwoom.token_expiry):
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

                if response.get('trnm') == 'LOGIN':
                    if response.get('return_code') != 0:
                        logger.error(f"WS Login Failed: {response.get('return_msg')}")
                        await self.disconnect()
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
                        self.keep_running = False
                        await self.disconnect()

                elif response.get('trnm') == 'REAL':
                    # Parse REAL message updates (e.g. 0B: 주식체결)
                    body = response.get('body', {})
                    msg_type = body.get('type')
                    if msg_type == '0B':  
                        data_arr = body.get('data', [])
                        logger.debug(f"WS REAL 0B: {body}")
                        if isinstance(data_arr, list):
                            for item in data_arr:
                                # Sometimes `REAL` data is an array of strings depending on fid format
                                # Based on typical Kiwoom spec, we will handle both list of dicts or handle failure gracefully.
                                if isinstance(item, dict):
                                    code = item.get("stk_cd") or item.get("code")
                                    if code:
                                        try:
                                            price = int(str(item.get("cur_prc", "0")).replace('+', '').replace('-', '').strip())
                                            change = int(str(item.get("pred_pre", "0")).replace('+', '').replace('-', '').strip())
                                            change_pct = float(str(item.get("flu_rt", "0")).replace('+', '').replace('-', '').strip())
                                            
                                            if '-' in str(item.get("flu_rt", "")):
                                                change = -change
                                                change_pct = -change_pct
                                                
                                            volume = int(str(item.get("trde_qty", "0")).strip() or 0)
                                            
                                            self.realtime_data[code] = {
                                                "code": code,
                                                "price": price,
                                                "change": change,
                                                "change_pct": change_pct,
                                                "volume": volume,
                                                "updated_at": datetime.now().timestamp()
                                            }
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
            else:
                # Use longer delay when auth is known to be failing
                delay = 60 if not kiwoom.is_auth_available else 5
                logger.debug(f"WS not connected. Retrying in {delay}s.")
                await asyncio.sleep(delay)

    async def disconnect(self):
        self.keep_running = False
        self.logged_in_event.clear()
        if self.connected and self.websocket:
            await self.websocket.close()
            self.connected = False
            logger.info('Kiwoom WS Disconnected.')

    async def subscribe_stocks(self, stock_codes: list, append: bool = False):
        """
        Subscribe to real-time execution (0B) for a list of stocks.
        """
        if not stock_codes:
            return

        # Wait for login to complete
        logger.info("Waiting for WS Login before subscribing...")
        await self.logged_in_event.wait()
        
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
                    'type': ['0B']
                }]
            }
            await self.send_message(packet)

# Global Instance
kiwoom_ws_manager = KiwoomWebSocketManager(SOCKET_URL)
