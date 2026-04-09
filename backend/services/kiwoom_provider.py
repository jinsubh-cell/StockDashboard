import os
import requests
import logging
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root (parent of backend/) or current dir
_env_path = Path(__file__).resolve().parent.parent.parent / '.env'
if _env_path.exists():
    load_dotenv(_env_path)
else:
    load_dotenv()  # fallback to current directory

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
        self.account_no = os.getenv("KIWOOM_ACCOUNT_NO", "")
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
            logger.info(f"Requesting Kiwoom token... (simulation={self.is_simulation})")
            res = requests.post(url, json=payload, headers=headers, timeout=10)
            logger.info(f"Kiwoom auth response: status={res.status_code}")

            # Handle non-JSON responses
            try:
                data = res.json()
            except ValueError as e:
                logger.error(f"Kiwoom auth returned non-JSON response: {e}, body={res.text[:200]}")
                self._mark_auth_failed("Non-JSON response from auth endpoint")
                return None

            logger.info(f"Kiwoom auth data: {data}")

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

        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Connection": "close",
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.app_key,
            "secretkey": self.secret_key,
            "api-id": tr_id,
            "cont-yn": cont_yn,
            "next-key": next_key,
        }
        # Include account number header for account-related APIs
        if self.account_no:
            headers["acnt-no"] = self.account_no
        return headers

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

            # API returns dict with 'tdy_trde_qty_upper' key containing the list
            if isinstance(data, dict):
                return data.get("tdy_trde_qty_upper", [])

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


    # ─── Trading (주문) Methods ───

    def place_order(self, code: str, order_type: str, quantity: int, price: int = 0, price_type: str = "limit"):
        """
        주식 매수/매도 주문 (키움 REST API 공식 스펙)
        매수: kt10000, 매도: kt10001
        엔드포인트: /api/dostk/ordr
        trde_tp: 0=지정가, 3=시장가, 5=조건부지정가, 61=장전시간외시장가, 81=시간외단일가 등
        """
        if not self.is_auth_available:
            return {"success": False, "message": "키움 인증이 필요합니다."}

        try:
            url = f"{self.base_url}/api/dostk/ordr"

            # 거래유형: 0=지정가, 3=시장가
            if price_type == "market":
                trde_tp = "3"
                ord_uv = ""
            else:
                trde_tp = "0"
                ord_uv = str(price)

            payload = {
                "dmst_stex_tp": "KRX",    # 국내거래소구분 (필수)
                "stk_cd": code,            # 종목코드 (필수)
                "ord_qty": str(quantity),   # 주문수량 (필수)
                "ord_uv": ord_uv,          # 주문단가 (지정가 시)
                "trde_tp": trde_tp,        # 거래유형 (필수)
                "cond_uv": "",             # 조건단가
            }

            # 매수: kt10000, 매도: kt10001
            tr_id = "kt10000" if order_type == "buy" else "kt10001"
            res = requests.post(url, headers=self._get_headers(tr_id), json=payload, timeout=10)

            try:
                data = res.json()
            except ValueError:
                return {"success": False, "message": f"키움 주문 응답 파싱 실패 (HTTP {res.status_code})"}

            logger.info(f"Order response ({tr_id}): {data}")

            if data.get("return_code") is not None and int(data.get("return_code", -1)) == 0:
                return {
                    "success": True,
                    "order_no": data.get("ord_no", ""),
                    "message": f"{'매수' if order_type == 'buy' else '매도'} 주문이 접수되었습니다."
                }
            else:
                return {
                    "success": False,
                    "message": data.get("return_msg", str(data))
                }

        except requests.exceptions.Timeout:
            return {"success": False, "message": "주문 요청 시간 초과"}
        except Exception as e:
            logger.error(f"Order error: {e}")
            return {"success": False, "message": f"주문 오류: {str(e)}"}

    def modify_order(self, org_order_no: str, code: str, quantity: int, price: int):
        """
        주문 정정 (kt10002)
        엔드포인트: /api/dostk/ordr
        """
        if not self.is_auth_available:
            return {"success": False, "message": "키움 인증이 필요합니다."}

        try:
            url = f"{self.base_url}/api/dostk/ordr"
            payload = {
                "dmst_stex_tp": "KRX",
                "stk_cd": code,
                "ord_qty": str(quantity),
                "ord_uv": str(price),
                "trde_tp": "0",              # 지정가 정정
                "org_ord_no": org_order_no,
                "cond_uv": "",
            }

            tr_id = "kt10002"
            res = requests.post(url, headers=self._get_headers(tr_id), json=payload, timeout=10)
            data = res.json()

            if data.get("return_code") is not None and int(data.get("return_code", -1)) == 0:
                return {"success": True, "order_no": data.get("ord_no", ""), "message": "주문이 정정되었습니다."}
            return {"success": False, "message": data.get("return_msg", str(data))}

        except Exception as e:
            logger.error(f"Modify order error: {e}")
            return {"success": False, "message": f"정정 오류: {str(e)}"}

    def cancel_order(self, org_order_no: str, code: str, quantity: int):
        """
        주문 취소 (kt10003)
        엔드포인트: /api/dostk/ordr
        """
        if not self.is_auth_available:
            return {"success": False, "message": "키움 인증이 필요합니다."}

        try:
            url = f"{self.base_url}/api/dostk/ordr"
            payload = {
                "dmst_stex_tp": "KRX",
                "stk_cd": code,
                "ord_qty": str(quantity),
                "org_ord_no": org_order_no,
            }

            tr_id = "kt10003"
            res = requests.post(url, headers=self._get_headers(tr_id), json=payload, timeout=10)
            data = res.json()

            if data.get("return_code") is not None and int(data.get("return_code", -1)) == 0:
                return {"success": True, "order_no": data.get("ord_no", ""), "message": "주문이 취소되었습니다."}
            return {"success": False, "message": data.get("return_msg", str(data))}

        except Exception as e:
            logger.error(f"Cancel order error: {e}")
            return {"success": False, "message": f"취소 오류: {str(e)}"}

    def get_account_balance(self):
        """
        계좌평가잔고내역요청 (kt00018) + 계좌별당일현황 (kt00017)
        kt00018: 보유종목, 총평가금액 등
        kt00017: 예수금(d2_entra) 조회

        Returns dict on success, or {"_error": "message"} on API error, or None on auth failure.
        """
        if not self.is_auth_available:
            logger.warning("get_account_balance: auth not available")
            return None

        # Ensure we have a valid token
        token = self.get_access_token()
        if not token:
            logger.warning("get_account_balance: no valid token")
            return None

        try:
            # --- kt00018: 계좌평가잔고내역 ---
            url = f"{self.base_url}/api/dostk/acnt"
            payload = {
                "acnt_no": self.account_no,  # 계좌번호 (필수)
                "qry_tp": "1",           # 조회구분 1:합산, 2:개별
                "dmst_stex_tp": "KRX",   # 국내거래소구분 KRX:한국거래소, NXT:넥스트트레이드
            }

            tr_id = "kt00018"
            logger.info(f"kt00018 request: acnt_no={self.account_no[:4]}****, url={url}")
            res = requests.post(url, headers=self._get_headers(tr_id), json=payload, timeout=10)

            try:
                data = res.json()
            except ValueError:
                logger.error(f"kt00018 returned non-JSON (status {res.status_code}, body={res.text[:200]})")
                return None

            logger.info(f"kt00018 response: return_code={data.get('return_code')}, return_msg={data.get('return_msg', '')}")

            # API 에러 체크 - return error message so UI can display it
            if data.get("return_code") is not None and int(data.get("return_code", 0)) != 0:
                err_msg = data.get("return_msg", str(data))
                logger.error(f"kt00018 error: {err_msg}")
                return {"_error": err_msg}

            # --- kt00017: 예수금 조회 ---
            cash = 0
            try:
                cash_payload = {
                    "acnt_no": self.account_no,  # 계좌번호 (필수)
                }
                res_cash = requests.post(url, headers=self._get_headers("kt00017"), json=cash_payload, timeout=10)
                cash_data = res_cash.json()
                logger.info(f"kt00017 response: return_code={cash_data.get('return_code')}, return_msg={cash_data.get('return_msg', '')}")
                if cash_data.get("return_code") is not None and int(cash_data.get("return_code", 0)) == 0:
                    # d2_entra: D+2 예수금 (실제 출금/매수 가능 금액)
                    cash = int(cash_data.get("d2_entra", "0").lstrip("0") or "0")
                    logger.info(f"kt00017 예수금(d2_entra): {cash}")
                else:
                    logger.warning(f"kt00017 failed: {cash_data.get('return_msg', cash_data)}")
            except Exception as e:
                logger.warning(f"kt00017 cash query failed: {e}")

            # 보유종목 파싱 - kt00018 실제 응답 필드명 기준
            holdings = []
            items = data.get("acnt_evlt_remn_indv_tot", [])
            if isinstance(items, list):
                for item in items:
                    code = item.get("stk_cd", "")
                    qty = int(item.get("remn_qty", "0").lstrip("0") or "0")  # 잔여수량
                    if qty <= 0:
                        continue
                    avg_price = float(item.get("avg_pur_prc", "0"))  # 평균매입가
                    cur_price = float(item.get("cur_prc", "0"))      # 현재가
                    eval_amt = float(item.get("evlt_amt", "0").lstrip("0") or "0")  # 평가금액
                    pnl = float(item.get("evlt_pl", "0").lstrip("0") or "0")        # 평가손익
                    pnl_pct = float(item.get("prft_rt", "0"))        # 수익률

                    holdings.append({
                        "code": code,
                        "name": item.get("stk_nm", code),
                        "quantity": qty,
                        "avg_price": avg_price,
                        "current_price": cur_price,
                        "eval_amount": eval_amt,
                        "pnl": pnl,
                        "pnl_pct": round(pnl_pct, 2),
                    })

            # 합계 데이터 - kt00018 실제 응답 필드명 기준
            total_eval = int(data.get("tot_evlt_amt", "0").lstrip("0") or "0")
            total_purchase = int(data.get("tot_pur_amt", "0").lstrip("0") or "0")
            total_pnl = int(data.get("tot_evlt_pl", "0").lstrip("0") or "0")
            total_pnl_pct = float(data.get("tot_prft_rt", "0"))
            # prsm_dpst_aset_amt: 추정예탁자산금액 (예수금 포함 총자산)
            estimated_asset = int(data.get("prsm_dpst_aset_amt", "0").lstrip("0") or "0")

            return {
                "total_eval": total_eval,
                "total_purchase": total_purchase,
                "total_pnl": total_pnl,
                "total_pnl_pct": total_pnl_pct,
                "cash": cash,
                "estimated_asset": estimated_asset,
                "holdings": holdings,
            }

        except Exception as e:
            logger.error(f"Balance query error: {e}")
            return None

    def get_order_history(self):
        """
        미체결 조회 (ka10075) + 체결 조회 (ka10076)
        엔드포인트: /api/dostk/acnt
        """
        if not self.is_auth_available:
            return []

        orders = []
        url = f"{self.base_url}/api/dostk/acnt"
        base_payload = {
            "acnt_no": self.account_no,  # 계좌번호 (필수)
            "all_stk_tp": "0",      # 전체종목
            "trde_tp": "0",         # 전체거래
            "dmst_stex_tp": "KRX",  # 한국거래소
            "stex_tp": "KRX",       # 거래소구분
        }

        try:
            # 1) 미체결 조회 (ka10075)
            res = requests.post(url, headers=self._get_headers("ka10075"), json=base_payload, timeout=10)
            try:
                data = res.json()
            except ValueError:
                data = {}

            if data.get("return_code") is not None and int(data.get("return_code", -1)) == 0:
                items = data.get("oso", [])
                for item in items:
                    ord_qty = int(item.get("ord_qty", "0").lstrip("0") or "0")
                    filled_qty = int(item.get("ccls_qty", "0").lstrip("0") or "0")
                    buy_sell = item.get("buy_sell_tp", "")
                    order_type = "buy" if buy_sell in ("2", "02") else "sell"

                    orders.append({
                        "order_no": item.get("ord_no", ""),
                        "code": item.get("stk_cd", ""),
                        "name": item.get("stk_nm", ""),
                        "order_type": order_type,
                        "quantity": ord_qty,
                        "price": int(item.get("ord_prc", "0").lstrip("0") or "0"),
                        "filled_quantity": filled_qty,
                        "filled_price": 0,
                        "status": "pending",
                        "order_time": item.get("ord_time", ""),
                    })

            # 2) 체결 조회 (ka10076)
            res2 = requests.post(url, headers=self._get_headers("ka10076"), json=base_payload, timeout=10)
            try:
                data2 = res2.json()
            except ValueError:
                data2 = {}

            if data2.get("return_code") is not None and int(data2.get("return_code", -1)) == 0:
                items2 = data2.get("oso", data2.get("ccls_list", []))
                for item in items2:
                    ord_qty = int(item.get("ord_qty", "0").lstrip("0") or "0")
                    filled_qty = int(item.get("ccls_qty", "0").lstrip("0") or "0")
                    buy_sell = item.get("buy_sell_tp", "")
                    order_type = "buy" if buy_sell in ("2", "02") else "sell"

                    orders.append({
                        "order_no": item.get("ord_no", ""),
                        "code": item.get("stk_cd", ""),
                        "name": item.get("stk_nm", ""),
                        "order_type": order_type,
                        "quantity": ord_qty,
                        "price": int(item.get("ord_prc", "0").lstrip("0") or "0"),
                        "filled_quantity": filled_qty,
                        "filled_price": float(item.get("ccls_prc", "0").lstrip("0") or "0"),
                        "status": "filled" if filled_qty >= ord_qty and ord_qty > 0 else "partial",
                        "order_time": item.get("ord_time", ""),
                    })

            return orders

        except Exception as e:
            logger.error(f"Order history error: {e}")
            return []


kiwoom = KiwoomAPIProvider()
