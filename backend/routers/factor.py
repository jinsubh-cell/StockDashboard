"""
Factor Analysis API Router
"""
from fastapi import APIRouter, Query
from services.data_collector import get_top_stocks, get_stock_ohlcv
from services.factor_engine import compute_factor_scores
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/factor", tags=["Factor Analysis"])


@router.get("/ranking")
def get_factor_ranking(
    count: int = Query(20, ge=5, le=50),
    momentum_w: float = Query(0.30, ge=0, le=1),
    value_w: float = Query(0.25, ge=0, le=1),
    quality_w: float = Query(0.25, ge=0, le=1),
    volatility_w: float = Query(0.20, ge=0, le=1),
):
    """Get stocks ranked by multi-factor scoring"""
    try:
        stocks = get_top_stocks(count)
        if not stocks:
            return {"error": "종목 데이터를 가져올 수 없습니다."}

        # Enrich with short history for factor calculation
        for stock in stocks:
            try:
                df = get_stock_ohlcv(stock["code"], days=90)
                if not df.empty:
                    stock["history"] = df["Close"].tolist()
            except Exception:
                stock["history"] = []

        weights = {
            "momentum": momentum_w,
            "value": value_w,
            "quality": quality_w,
            "volatility": volatility_w,
        }

        rankings = compute_factor_scores(stocks, weights)

        return {
            "factors_used": ["momentum", "value", "quality", "volatility"],
            "weights": weights,
            "rankings": [
                {
                    "code": r["code"],
                    "name": r["name"],
                    "momentum_score": r.get("momentum_score", 0),
                    "value_score": r.get("value_score", 0),
                    "quality_score": r.get("quality_score", 0),
                    "volatility_score": r.get("volatility_score", 0),
                    "total_score": r.get("total_score", 0),
                    "rank": r.get("rank", 0),
                    "price": r.get("close", 0),
                    "change_pct": r.get("change_pct", 0),
                }
                for r in rankings
            ],
        }
    except Exception as e:
        logger.error(f"Error in get_factor_ranking: {e}")
        return {"error": str(e)}
