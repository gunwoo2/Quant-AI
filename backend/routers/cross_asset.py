"""
routers/cross_asset.py — Cross-Asset Intelligence API
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

GET /api/market/cross-asset
  → MarketSignalTab MacroTab에 글로벌 자산 히트맵 데이터 공급
"""
from fastapi import APIRouter, HTTPException
from services.cross_asset_service import get_cross_asset_latest

router = APIRouter()


@router.get(
    "/market/cross-asset",
    summary="Cross-Asset Intelligence 최신 데이터",
    description="15개 글로벌 자산 (채권/원자재/환율/EM) 기반 8개 시그널",
)
def api_cross_asset():
    result = get_cross_asset_latest()
    if result is None:
        raise HTTPException(status_code=404, detail="Cross-Asset 데이터가 없습니다.")
    return result
