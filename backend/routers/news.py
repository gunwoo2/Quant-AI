"""
routers/news.py — 뉴스 API 라우터
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GET /api/news/{ticker}  → 종목 관련 뉴스 목록
"""

from fastapi import APIRouter, Query
from services.news_service import get_news_by_ticker
from db_pool import get_cursor

router = APIRouter()


@router.get(
    "/news/{ticker}",
    summary="종목별 뉴스 조회 (newsapi.org)",
)
def api_get_news(ticker: str, limit: int = Query(10, ge=1, le=30)):
    """
    티커에 관련된 최신 뉴스를 반환한다.
    company_name을 DB에서 가져와 검색 정확도를 높인다.
    """
    # DB에서 회사명 조회 (검색 정확도 향상)
    company_name = None
    try:
        with get_cursor() as cur:
            cur.execute(
                "SELECT company_name FROM stocks WHERE ticker = %s LIMIT 1",
                (ticker.upper(),)
            )
            row = cur.fetchone()
            if row:
                company_name = row["company_name"]
    except Exception:
        pass

    articles = get_news_by_ticker(
        ticker=ticker.upper(),
        company_name=company_name,
        page_size=limit,
    )

    return articles

