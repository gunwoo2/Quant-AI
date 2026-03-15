from fastapi import APIRouter
from services.market_service import get_market_indices, get_market_status

router = APIRouter()


@router.get(
    "/market/indices",
    summary="글로벌 지수·환율·원자재·암호화폐",
)
def api_market_indices():
    return get_market_indices()


@router.get(
    "/market/status",
    summary="미국(NYSE) + 한국(KRX) 시장 상태",
)
def api_market_status():
    return get_market_status()

