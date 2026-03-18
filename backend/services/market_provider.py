import requests
import logging
import time

logger = logging.getLogger(__name__)

# Shared headers
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Connection": "close"
}

# Price cache: {code: {"data": {...}, "ts": timestamp}}
_price_cache = {}
_PRICE_CACHE_TTL = 3  # seconds


class MarketDataProvider:
    """
    Market Data Provider using Naver Finance (Polling API)
    Supports single and batch stock price fetching with short-term caching.
    """
    def __init__(self):
        self.base_url = "https://polling.finance.naver.com/api/realtime"

    def _parse_item(self, item):
        """Parse a single Naver realtime data item into our standard format."""
        code = item.get("cd", "")
        price = int(item.get("nv", 0))
        change_pct = float(item.get("cr", 0))
        change = int(item.get("cv", 0))  # cv already carries correct sign
        return {
            "code": code,
            "price": price,
            "change": change,
            "change_pct": change_pct,
            "volume": int(item.get("aq", 0)),
            "open": int(item.get("ov", 0)),
            "high": int(item.get("hv", 0)),
            "low": int(item.get("lv", 0)),
        }

    def get_current_price(self, code: str):
        """Fetch real-time quote for a single stock, with short-term cache."""
        # Check cache first
        cached = _price_cache.get(code)
        if cached and (time.time() - cached["ts"]) < _PRICE_CACHE_TTL:
            return cached["data"]

        try:
            url = f"{self.base_url}?query=SERVICE_ITEM:{code}"
            res = requests.get(url, headers=_HEADERS, timeout=5)
            data = res.json()
            if data.get("resultCode") == "success":
                areas = data.get("result", {}).get("areas", [])
                if areas and areas[0].get("datas"):
                    parsed = self._parse_item(areas[0]["datas"][0])
                    _price_cache[code] = {"data": parsed, "ts": time.time()}
                    return parsed
        except Exception as e:
            logger.error(f"Error fetching price from Naver for {code}: {e}")
        return None

    def get_batch_prices(self, codes: list[str]) -> dict[str, dict]:
        """
        Fetch real-time quotes for multiple stocks in a single HTTP call.
        Uses cache for recently fetched prices and only requests missing ones.
        """
        if not codes:
            return {}

        result = {}
        now = time.time()

        # Separate cached vs missing
        missing = []
        for code in codes:
            cached = _price_cache.get(code)
            if cached and (now - cached["ts"]) < _PRICE_CACHE_TTL:
                result[code] = cached["data"]
            else:
                missing.append(code)

        if not missing:
            return result

        # Fetch missing from Naver
        chunk_size = 50
        for i in range(0, len(missing), chunk_size):
            chunk = missing[i:i + chunk_size]
            try:
                codes_str = ",".join(chunk)
                url = f"{self.base_url}?query=SERVICE_ITEM:{codes_str}"
                res = requests.get(url, headers=_HEADERS, timeout=10)
                data = res.json()
                if data.get("resultCode") == "success":
                    for area in data.get("result", {}).get("areas", []):
                        for item in area.get("datas", []):
                            parsed = self._parse_item(item)
                            if parsed["price"] > 0:
                                result[parsed["code"]] = parsed
                                _price_cache[parsed["code"]] = {"data": parsed, "ts": time.time()}
            except Exception as e:
                logger.error(f"Batch price fetch error (chunk {i}): {e}")

        return result


market_provider = MarketDataProvider()
