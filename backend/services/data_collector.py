"""
Data Collector Service
Fetches real Korean market data using FinanceDataReader and PyKrx
"""
import FinanceDataReader as fdr
from pykrx import stock as krx
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
from functools import lru_cache
import logging

logger = logging.getLogger(__name__)

# Suppress pykrx internal log spam (it has bugs in its logging formatting)
logging.getLogger("pykrx").setLevel(logging.WARNING)

# In-memory cache
_cache = {}
_cache_expiry = {}
CACHE_TTL = 300  # 5 minutes


def _get_cached(key: str):
    if key in _cache and datetime.now().timestamp() < _cache_expiry.get(key, 0):
        return _cache[key]
    return None


def _set_cached(key: str, value, ttl: int = CACHE_TTL):
    _cache[key] = value
    _cache_expiry[key] = datetime.now().timestamp() + ttl


def get_krx_stock_list() -> pd.DataFrame:
    """Get all KRX-listed stocks (2700+ entries)"""
    cached = _get_cached("stock_list")
    if cached is not None:
        return cached

    # Strategy 1: KRX direct download (fastest, most reliable, ~2700 stocks)
    try:
        from io import StringIO
        url = "https://kind.krx.co.kr/corpgeneral/corpList.do?method=download"
        res = requests.get(url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        if res.status_code == 200 and len(res.text) > 1000:
            dfs = pd.read_html(StringIO(res.text), encoding="euc-kr")
            if dfs and len(dfs[0]) > 100:
                raw = dfs[0]
                # Columns: 회사명(0), 시장구분(1), 종목코드(2), ...
                df = pd.DataFrame({
                    "Code": raw.iloc[:, 2].astype(str).str.zfill(6),
                    "Name": raw.iloc[:, 0].astype(str),
                })
                # Filter out non-stock codes (preferreds, etc. with letters)
                df = df[df["Code"].str.match(r"^\d{6}$")]
                df = df.dropna(subset=["Name"])
                if len(df) > 100:
                    logger.info(f"KRX direct download: {len(df)} stocks loaded")
                    _set_cached("stock_list", df, ttl=3600)
                    return df
    except Exception as e:
        logger.warning(f"KRX direct download failed: {e}")

    # Strategy 2: FinanceDataReader
    try:
        df = fdr.StockListing("KRX-DESC")
        if df is not None and not df.empty:
            df = df[["Code", "Name"]]
            _set_cached("stock_list", df, ttl=3600)
            return df
    except Exception as e:
        logger.warning(f"FDR failed: {e}. Trying pykrx...")

    # Strategy 3: PyKrx
    import concurrent.futures

    def _fetch_pykrx_date(delta):
        try:
            d = (datetime.now() - timedelta(days=delta)).strftime("%Y%m%d")
            tickers = krx.get_market_ticker_list(d, market="ALL")
            if tickers:
                data = [{"Code": t, "Name": krx.get_market_ticker_name(t)} for t in tickers]
                if data:
                    return pd.DataFrame(data)
        except Exception as e:
            logger.warning(f"Pykrx fallback failed for delta {delta}: {e}")
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=7) as executor:
        futures = {executor.submit(_fetch_pykrx_date, d): d for d in range(0, 7)}
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res is not None:
                _set_cached("stock_list", res, ttl=3600)
                for f in futures: f.cancel()
                return res

    # Fallback 4: Hardcoded list (last resort)
    fallback_data = [
        {"Code": "005930", "Name": "삼성전자"}, {"Code": "000660", "Name": "SK하이닉스"},
        {"Code": "035420", "Name": "NAVER"}, {"Code": "035720", "Name": "카카오"},
        {"Code": "051910", "Name": "LG화학"}, {"Code": "006400", "Name": "삼성SDI"},
        {"Code": "373220", "Name": "LG에너지솔루션"}, {"Code": "005380", "Name": "현대차"},
        {"Code": "000270", "Name": "기아"}, {"Code": "055550", "Name": "신한지주"},
        {"Code": "105560", "Name": "KB금융"}, {"Code": "028260", "Name": "삼성물산"},
        {"Code": "012330", "Name": "현대모비스"}, {"Code": "068270", "Name": "셀트리온"},
        {"Code": "207940", "Name": "삼성바이오로직스"}, {"Code": "034730", "Name": "SK이노베이션"},
        {"Code": "003670", "Name": "포스코퓨처엠"}, {"Code": "066570", "Name": "LG전자"},
        {"Code": "003550", "Name": "LG"}, {"Code": "247540", "Name": "에코프로비엠"},
    ]
    df = pd.DataFrame(fallback_data)
    _set_cached("stock_list", df, ttl=3600)
    return df


import xml.etree.ElementTree as ET

# Global session for fast repeated HTTP requests
_fchart_session = requests.Session()
_fchart_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Connection": "keep-alive"
})

def get_stock_ohlcv(code: str, days: int = 365) -> pd.DataFrame:
    """Get OHLCV data for a stock (Fast version using Naver fchart API)"""
    cache_key = f"ohlcv_{code}_{days}"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    try:
        # Convert days to a reasonably safe trading days count (252 a year + buffer)
        # We request exactly 'days' because Naver fchart count logic represents trading days.
        url = f"https://fchart.stock.naver.com/sise.nhn?symbol={code}&timeframe=day&count={days}&requestType=0"
        res = _fchart_session.get(url, timeout=3)
        if res.status_code == 200:
            # Naver returns EUC-KR but requests might not guess it correctly / XML parser hates bytes with EUC-KR
            res.encoding = 'euc-kr' 
            # Remove the xml declaration from the text to avoid 'XML declaration' errors and multi-byte encoding errors
            text = res.text
            if text.startswith("<?xml"):
                text = text.split("?>", 1)[-1].strip()
                
            root = ET.fromstring(text)
            items = root.findall('.//item')
            
            data = []
            for item in items:
                d = item.get("data", "").split("|")
                if len(d) == 6:
                    data.append({
                        "Date": pd.to_datetime(d[0], format="%Y%m%d"),
                        "Open": int(d[1]),
                        "High": int(d[2]),
                        "Low": int(d[3]),
                        "Close": int(d[4]),
                        "Volume": int(d[5])
                    })
                    
            if data:
                df = pd.DataFrame(data)
                # Naver fchart returns newest-first; sort ascending so TA-Lib
                # computes indicators in chronological order (oldest → newest)
                df = df.sort_values("Date").reset_index(drop=True)
                _set_cached(cache_key, df, ttl=1800)  # 30 min cache
                return df
                
    except Exception as e:
        logger.error(f"Fast OHLCV fetch failed for {code}: {e}")

    # Fallback to FinanceDataReader if fast fetch fails
    try:
        df = fdr.DataReader(code, start=(datetime.now() - timedelta(days=days+30)).strftime('%Y-%m-%d'))
        if not df.empty:
            df = df.reset_index()
            # Capitalize columns for TA compatibility
            df.columns = [c.capitalize() if c.lower() in ['date', 'open', 'high', 'low', 'close', 'volume'] else c for c in df.columns]
            _set_cached(cache_key, df, ttl=1800)
            return df
    except Exception as e:
        logger.error(f"Fallback OHLCV fetch failed for {code}: {e}")

    return pd.DataFrame()


def get_stock_info(code: str) -> dict:
    """Get stock details from PyKrx"""
    cache_key = f"info_{code}"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    # Try recent dates if today is weekend/holiday
    info = {}
    for delta in range(0, 7):
        try:
            date = (datetime.now() - timedelta(days=delta)).strftime("%Y%m%d")
            cap_df = krx.get_market_cap(date, market="ALL")
            if cap_df is not None and not cap_df.empty and code in cap_df.index:
                row = cap_df.loc[code]
                info = {
                    "market_cap": int(row.get("시가총액", 0)),
                    "volume": int(row.get("거래량", 0)),
                    "shares": int(row.get("상장주식수", 0)),
                }
                break
        except Exception:
            continue

    # Fallback to fdr if pykrx info fetch fails
    if not info:
        try:
            # get_market_cap in pykrx is for a given date, FDR Marcap is slightly different
            # For specific stock info, we can try fdr.StoockListing if needed, but info_ is often for Detail page.
            # Let's try to get simple info from OHLCV if pykrx fails
            df = get_stock_ohlcv(code, days=5)
            if not df.empty:
                last = df.iloc[-1]
                info["volume"] = int(last.get("Volume", 0))
        except:
            pass

    # Foreign ownership
    for delta in range(0, 7):
        try:
            date = (datetime.now() - timedelta(days=delta)).strftime("%Y%m%d")
            foreign_df = krx.get_exhaustion_rates_of_foreign_investment(date, market="ALL")
            if foreign_df is not None and code in foreign_df.index:
                row = foreign_df.loc[code]
                info["foreign_rate"] = float(row.get("지분율", 0))
                break
        except Exception:
            continue

    if info:
        _set_cached(cache_key, info)
    return info


def get_market_indices() -> list[dict]:
    """Get KOSPI, KOSDAQ, KOSPI200 and USD/KRW indices (Real-time via Naver)"""
    cached = _get_cached("indices")
    if cached is not None:
        return cached

    indices = []
    try:
        # Fetch KOSPI, KOSDAQ, KOSPI200 in one call; exchange rate separately
        url = "https://polling.finance.naver.com/api/realtime?query=SERVICE_INDEX:KOSPI,KOSDAQ,KPI200"
        res = requests.get(url, timeout=5)
        data = res.json()
        if data.get("resultCode") == "success":
            name_map = {"KOSPI": "코스피", "KOSDAQ": "코스닥", "KPI200": "코스피 200"}
            for area in data["result"]["areas"]:
                for item in area["datas"]:
                    cd = item.get("cd")
                    nm = name_map.get(cd, "")
                    if nm:
                        val = item.get("nv", 0) / 100
                        cv = item.get("cv", 0) / 100  # cv already has correct sign
                        indices.append({
                            "name": nm,
                            "value": round(val, 2),
                            "change": round(cv, 2),
                            "change_pct": round(item.get("cr", 0), 2),
                        })
    except Exception as e:
        logger.error(f"Index fetch error: {e}")

    # Fetch USD/KRW exchange rate from Naver finance marketindex page
    try:
        import re
        fx_url = "https://finance.naver.com/marketindex/"
        fx_res = requests.get(fx_url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        fx_res.encoding = "euc-kr"
        html = fx_res.text
        # Extract USD block: value and change amount
        usd_block = re.search(r'미국 USD(.*?)일본 JPY', html, re.DOTALL)
        if usd_block:
            nums = re.findall(r'>([\d,]+\.\d+)<', usd_block.group(1))
            if len(nums) >= 2:
                fx_value = float(nums[0].replace(',', ''))
                fx_change = float(nums[1].replace(',', ''))
                # Detect direction: 'down' class means negative
                is_down = 'head_info down' in usd_block.group(1) or 'ico_down' in usd_block.group(1) or '하락' in usd_block.group(1)
                if is_down:
                    fx_change = -fx_change
                fx_pct = round((fx_change / (fx_value - fx_change)) * 100, 2) if fx_value != fx_change else 0
                indices.append({
                    "name": "원/달러 환율",
                    "value": fx_value,
                    "change": fx_change,
                    "change_pct": fx_pct,
                })
    except Exception as e:
        logger.error(f"Exchange rate fetch error: {e}")

    if indices:
        _set_cached("indices", indices, ttl=2)
    return indices


# Pre-defined top stocks by market cap (code, name, shares outstanding)
# This avoids the slow PyKrx market cap lookup on every request
_TOP_STOCKS_LIST = [
    ("005930", "삼성전자", 5969782550), ("000660", "SK하이닉스", 728002365),
    ("207940", "삼성바이오로직스", 66165000), ("373220", "LG에너지솔루션", 234000000),
    ("005380", "현대자동차", 211531506), ("000270", "기아", 404751749),
    ("035420", "NAVER", 163404399), ("006400", "삼성SDI", 68764530),
    ("051910", "LG화학", 70592343), ("035720", "카카오", 443024247),
    ("105560", "KB금융", 403067974), ("055550", "신한지주", 517071397),
    ("028260", "삼성물산", 187887938), ("068270", "셀트리온", 138427370),
    ("012330", "현대모비스", 94381992), ("003670", "포스코퓨처엠", 61105771),
    ("066570", "LG전자", 163647814), ("247540", "에코프로비엠", 72694103),
    ("003550", "LG", 157348757), ("034730", "SK이노베이션", 94483395),
    ("005490", "POSCO홀딩스", 84571230), ("032830", "삼성생명", 200000000),
    ("000810", "삼성화재", 47175000), ("009150", "삼성전기", 74693696),
    ("018260", "삼성SDS", 77377800), ("010140", "삼성중공업", 462398938),
    ("028050", "삼성엔지니어링", 196540497), ("316140", "우리금융지주", 727489080),
    ("086790", "하나금융지주", 291254329), ("004020", "현대제철", 135477917),
]


def get_top_stocks(count: int = 30, market: str = 'ALL') -> list[dict]:
    """
    Get top stocks by market cap.
    market: 'ALL', 'KOSPI', or 'KOSDAQ'
    """
    cache_key = f"top_stocks_{market}_{count}"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    from services.market_provider import market_provider
    from services.kiwoom_ws import kiwoom_ws_manager

    # 1. Determine which codes to fetch
    if market == "ALL" and count <= 30:
        # Use pre-defined list for fastest path (Main dashboard)
        stock_info = {code: {"name": name, "shares": shares}
                      for code, name, shares in _TOP_STOCKS_LIST[:count]}
        codes = list(stock_info.keys())
    else:
        # Fetch dynamically
        try:
            target_market = "KOSPI" if market == "KOSPI" else "KOSDAQ" if market == "KOSDAQ" else "ALL"
            stock_info = {}
            codes = []
            
            # Strategy 1: FinanceDataReader (More stable for full market lists)
            try:
                fdr_market = "KOSPI" if market == "KOSPI" else "KOSDAQ" if market == "KOSDAQ" else "KRX"
                df_fdr = fdr.StockListing(fdr_market)
                if df_fdr is not None and not df_fdr.empty:
                    if "Marcap" in df_fdr.columns:
                        df_fdr = df_fdr.sort_values(by="Marcap", ascending=False)
                    top_df = df_fdr.head(count)
                    for _, row in top_df.iterrows():
                        c = row.get("Code")
                        n = row.get("Name")
                        s = int(row.get("Stocks", 0))
                        if c:
                            stock_info[c] = {"name": n, "shares": s}
                    codes = list(stock_info.keys())
            except Exception as e:
                logger.warning(f"FDR fetch failed for {market}: {e}")

            # Strategy 2: PyKrx (Fallback)
            if not codes:
                for i in range(5):
                    d = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d")
                    try:
                        cap_df = krx.get_market_cap(d, market=target_market)
                        if cap_df is not None and not cap_df.empty:
                            cap_df = cap_df.sort_values(by="시가총액", ascending=False).head(count)
                            for code, row in cap_df.iterrows():
                                try:
                                    name = krx.get_market_ticker_name(code)
                                except:
                                    name = code
                                stock_info[code] = {"name": name, "shares": int(row["상장주식수"])}
                            codes = list(stock_info.keys())
                            break
                    except:
                        continue
            
            # Final Fallback: Hardcoded list
            if not codes:
                stock_info = {code: {"name": name, "shares": shares}
                              for code, name, shares in _TOP_STOCKS_LIST[:count]}
                codes = list(stock_info.keys())
                
        except Exception as e:
            logger.error(f"Failed to fetch stock info for {market}: {e}")
            stock_info = {code: {"name": name, "shares": shares}
                          for code, name, shares in _TOP_STOCKS_LIST[:count]}
            codes = list(stock_info.keys())

    # 1. Check WS cache for any available real-time data
    ws_data = {}
    for code in codes:
        rt = kiwoom_ws_manager.realtime_data.get(code)
        if rt:
            ws_data[code] = rt

    # 2. Batch fetch remaining from Naver (single HTTP call for all missing codes)
    missing_codes = [c for c in codes if c not in ws_data]
    naver_data = {}
    if missing_codes:
        try:
            naver_data = market_provider.get_batch_prices(missing_codes)
        except Exception as e:
            logger.error(f"Batch price fetch failed: {e}")

    # 3. Merge and build result
    result = []
    for code in codes:
        info = stock_info[code]
        price_data = ws_data.get(code) or naver_data.get(code)
        if price_data and price_data.get("price", 0) > 0:
            result.append({
                "code": code,
                "name": info["name"],
                "close": price_data["price"],
                "open": 0,
                "high": 0,
                "low": 0,
                "volume": price_data["volume"],
                "change": price_data["change"],
                "change_pct": price_data["change_pct"],
                "market_cap": price_data["price"] * info["shares"],
            })

    if result:
        result.sort(key=lambda x: x["market_cap"], reverse=True)
        _set_cached(cache_key, result, ttl=10) # 10s cache for expanded lists

    return result


def search_stocks(query: str) -> list[dict]:
    """Search stocks by name or code"""
    stock_list = get_krx_stock_list()
    if stock_list.empty:
        return []

    q = query.lower()
    
    # Try matching columns flexibly
    name_col = next((c for c in stock_list.columns if c.lower() == "name"), None)
    code_col = next((c for c in stock_list.columns if c.lower() == "code"), None)
    
    if not name_col or not code_col:
        logger.warning(f"Columns Name or Code not found in stock list: {stock_list.columns}")
        return []

    mask = (
        stock_list[name_col].str.lower().str.contains(q, na=False) |
        stock_list[code_col].str.contains(q, na=False)
    )
    results = stock_list[mask].head(10)

    codes = [row[code_col] for _, row in results.iterrows()]

    # Batch fetch prices from Naver (single HTTP call, also warms cache for detail page)
    from services.market_provider import market_provider
    prices = {}
    try:
        prices = market_provider.get_batch_prices(codes)
    except Exception:
        pass

    enriched_results = []
    for _, row in results.iterrows():
        code = row[code_col]
        p = prices.get(code, {})
        enriched_results.append({
            "code": code,
            "name": row[name_col],
            "price": p.get("price", 0),
            "change": p.get("change", 0),
            "change_pct": p.get("change_pct", 0),
            "volume": p.get("volume", 0),
        })

    return enriched_results
