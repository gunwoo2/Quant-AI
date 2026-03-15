from fastapi import APIRouter, Query
from services.rating_history_service import get_rating_history

router = APIRouter()


@router.get(
    "/stock/rating-history/{ticker}",
    summary="AI Rating History (등급 변동 이력)",
)
def api_rating_history(
    ticker: str,
    limit: int = Query(20, ge=1, le=100),
):
    return get_rating_history(ticker, limit)