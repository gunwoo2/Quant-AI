"""
routers/layer2.py — Layer 2 NLP 시그널 API
"""
import traceback
from fastapi import APIRouter, HTTPException
from services.layer2_service import get_layer2_data

router = APIRouter()


@router.get(
    "/stock/layer2/{ticker}",
    summary="Layer 2 NLP 시그널 데이터",
    description="뉴스 감성(FinBERT) + 애널리스트 + 내부자 거래 통합",
)
def api_layer2_data(ticker: str):
    try:
        result = get_layer2_data(ticker)
        if result is None:
            raise HTTPException(status_code=404, detail=f"{ticker} 종목을 찾을 수 없습니다.")
        return result
    except HTTPException:
        raise
    except Exception as e:
        print(f"[L2-API] ❌ /stock/layer2/{ticker}: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Layer 2 데이터 조회 실패")

