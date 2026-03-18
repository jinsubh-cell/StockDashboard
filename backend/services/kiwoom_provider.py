import os
import requests
import logging
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Auth failure cooldown: avoid hammering Kiwoom when device is not registered
AUTH_FAILURE_COOLDOWN = 300  # 5 minutes

class KiwoomAPIProvider:
    """
    Kiwoom Securities Open API (Next) REST Provider
    """
    def __init__(self):
        self.app_key = os.getenv("KIWOOM_APP_KEY", "")
        self.secret_key = os.getenv("KIWOOM_SECRET_KEY", "")
        self.is_simulation = os.getenv("KIWOOM_IS_SIMULATION", "True").lower() == "true"

        self.base_url = "https://api.kiwoom.com"

        self.access_token = None
        self.token_expiry = None

        # Track auth failures to avoid repeated failed attempts
        self._auth_failed = False
        self._auth_fail_time = 0
        self._auth_fail_msg = ""

        # Load cached token if available
        self._load_cached_token()

    def _load_cached_token(self):
        token_path = os.path.join(os.path.dirname(__file__), ".kiwoom_token.json")
        try:
            if os.path.exists(token_path):
                import json
                with open(token_path, "r") as f:
                    content = f.read().strip()
                    if not content:
                        logger.warning("Cached token file is empty, skipping.")
                        return
                    data = json.loads(content)
                    if data.get("expiry", 0) > datetime.now().timestamp():
                        self.access_token = data.get("token")
                        self.token_expiry = data.get("expiry")
                        logger.info("Loaded cached Kiwoom token.")
                    else:
                        logger.info("Cached Kiwoom token expired, will request new one.")
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Cached token file corrupted, removing: {e}")
            try:
                os.remove(token_path)
            except OSError:
                pass
        except Exception as e:
            logger.warning(f"Failed to load cached token: {e}")

    def _save_cached_token(self):
        try:
            token_path = os.path.join(os.path.dirname(__file__), ".kiwoom_token.json")
            import json
            with open(token_path, "w") as f:
                json.dump({
                    "token": self.access_token,
                    "expiry": self.token_expiry
                }, f)
        except Exception as e:
            logger.warning(f"Failed to save cached token: {e}")

    @property
    def is_auth_available(self):
        """Check if Kiwoom auth is likely to succeed (not in cooldown)."""
        if not self.app_key or not self.secret_key:
            return False
        if self._auth_failed:
            elapsed = datetime.now().timestamp() - self._auth_fail_time
            if elapsed < AUTH_FAILURE_COOLDOWN:
                return False
            # Cooldown expired, allow retry
            self._auth_failed = False
        return True

    def get_access_token(self):
        if self.access_token and self.token_expiry and self.token_expiry > datetime.now().timestamp():
            return self.access_token

        if not self.is_auth_available:
            if self._auth_failed:
                logger.debug(f"Kiwoom auth in cooldown (last failure: {self._auth_fail_msg}). Skipping.")
            return None

        try:
            url = f"{self.base_url}/oauth2/token"
            payload = {
                "grant_type": "client_credentials",
                "appkey": self.app_key,
                "secretkey": self.secret_key
            }
            headers = {
                "Content-Type": "application/json;charset=UTF-8",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Connection": "close"
            }
            res = requests.post(url, json=payload, headers=headers, timeout=10)

            # Handle non-JSON responses
            try:
                data = res.json()
            except ValueError as e:
                logger.error(f"Kiwoom auth returned non-JSON response: {e}")
                self._mark_auth_failed("Non-JSON response from auth endpoint")
                return None

            if "token" in data or "access_token" in data:
                token_val = data.get("token") or data.get("access_token")
                self.access_token = token_val
                expires_in = data.get("expires_in", 86400)
                expires_dt_str = data.get("expires_dt")

                if expires_dt_str:
                    try:
                        self.token_expiry = datetime.strptime(expires_dt_str, "%Y%m%d%H%M%S").timestamp()
                    except Exception:
                        self.token_expiry = datetime.now().timestamp() + int(expires_in)
                else:
                    self.token_expiry = datetime.now().timestamp() + int(expires_in)

                self._auth_failed = False
                self._save_cached_token()
                logger.info("Requested new Kiwoom token and cached it.")
                return self.access_token
            else:
                msg = data.get("return_msg", str(data))
                logger.error(f"Failed to get token, Kiwoom API returned: {data}")
                self._mark_auth_failed(msg)
        except requests.exceptions.Timeout:
            logger.error("Kiwoom auth request timed out.")
            self._mark_auth_failed("Request timeout")
        except Exception as e:
            logger.error(f"Kiwoom auth error: {e}")
            self._mark_auth_failed(str(e))
        return None

    def _mark_auth_failed(self, msg: str):
        self._auth_failed = True
        self._auth_fail_time = datetime.now().timestamp()
        self._auth_fail_msg = msg
        logger.warning(f"Kiwoom auth marked as failed. Cooldown {AUTH_FAILURE_COOLDOWN}s. Reason: {msg}")

    def _get_headers(self, tr_id: str, cont_yn: str = 'N', next_key: str = ''):
        if not self.access_token or (self.token_expiry and datetime.now().timestamp() > self.token_expiry):
            self.get_access_token()
            
        return {
            "Content-Type": "application/json;charset=UTF-8",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Connection": "close",
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.app_key,
            "secretkey": self.secret_key,
            "api-id": tr_id,
            "cont-yn": cont_yn,
            "next-key": next_key
        }

    def get_top_volume_stocks(self):
        """
        당일거래량상위요청 (ka10030)
        """
        if not self.is_auth_available:
            return []

        try:
            url = f"{self.base_url}/api/dostk/rkinfo"
            
            params = {
                'mrkt_tp': '000',  # 시장구분 000:전체, 001:코스피, 101:코스닥
                'sort_tp': '1',    # 정렬구분 1:거래량, 2:거래회전율, 3:거래대금
                'mang_stk_incls': '0', # 관리종목포함 0:관리종목 포함
                'crd_tp': '0',     # 신용구분 0:전체조회
                'trde_qty_tp': '0',# 거래량구분 0:전체조회
                'pric_tp': '0',    # 가격구분 0:전체조회
                'trde_prica_tp': '0', # 거래대금구분 0:전체조회
                'mrkt_open_tp': '0', # 장운영구분 0:전체조회
                'stex_tp': '3',    # 거래소구분 1:KRX, 2:NXT 3.통합
            }

            res = requests.post(url, headers=self._get_headers("ka10030"), json=params, timeout=5)
            try:
                data = res.json()
            except ValueError:
                logger.error(f"Kiwoom ka10030 returned non-JSON response (status {res.status_code})")
                return []

            return data

        except Exception as e:
            logger.error(f"Error fetching top volume from Kiwoom: {e}")
            return []

    def get_current_price(self, code: str):
        """
        주식기본정보요청 (ka10001) - Fetch real-time single stock info
        """
        if not self.is_auth_available:
            return None

        try:
            url = f"{self.base_url}/api/dostk/stkinfo"
            payload = {
                "stk_cd": code
            }
            res = requests.post(url, headers=self._get_headers("ka10001"), json=payload, timeout=5)
            try:
                data = res.json()
            except ValueError:
                logger.error(f"Kiwoom ka10001 returned non-JSON response for {code}")
                return None
            
            # Parse response if successful (ka10001 returns flat dict)
            if data and "cur_prc" in data:
                price = int(str(data.get("cur_prc", "0")).replace('+', '').replace('-', '').strip())
                change = int(str(data.get("pred_pre", "0")).replace('+', '').replace('-', '').strip())
                change_pct = float(str(data.get("flu_rt", "0")).replace('+', '').replace('-', '').strip())
                
                # Check original string sign from flu_rt
                if '-' in str(data.get("flu_rt", "")):
                    change = -change
                    change_pct = -change_pct
                    
                volume = int(str(data.get("trde_qty", "0")).strip() or 0)
                
                return {
                    "code": code,
                    "price": price,
                    "change": change,
                    "change_pct": change_pct,
                    "volume": volume
                }
            return None
        except Exception as e:
            logger.error(f"Error fetching price from Kiwoom for {code}: {e}")
            return None


kiwoom = KiwoomAPIProvider()
