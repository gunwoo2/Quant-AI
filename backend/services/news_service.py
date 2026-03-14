"""
news_service.py — 종목별 뉴스 조회 (newsapi.org)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
디테일 페이지에서 티커별 영문 뉴스를 보여준다.
.env의 NEWS_API_KEY를 사용.
"""

import os
import requests
from typing import Optional
from datetime import datetime, timedelta


NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")
NEWS_API_URL = "https://newsapi.org/v2/everything"


def get_news_by_ticker(
    ticker: str,
    company_name: Optional[str] = None,
    page_size: int = 10,
) -> list[dict]:
    """
    종목 관련 뉴스 조회.
    
    ticker: AAPL, MSFT 등
    company_name: Apple Inc. → 검색 정확도 향상용 (선택)
    page_size: 최대 뉴스 수 (기본 10)
    
    Returns: [{source, time, title, content, thumbnail, url}, ...]
    """
    if not NEWS_API_KEY:
        return []

    # 검색 쿼리: 티커 + 회사명 (있으면)
    query = ticker
    if company_name:
        # "Apple" OR "AAPL" — 둘 다 매칭
        short_name = company_name.split(",")[0].split(" Inc")[0].split(" Corp")[0].strip()
        if short_name and short_name.upper() != ticker.upper():
            query = f'"{short_name}" OR "{ticker}"'

    # 최근 30일
    from_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

    params = {
        "q":        query,
        "from":     from_date,
        "sortBy":   "publishedAt",
        "language": "en",
        "pageSize": page_size,
        "apiKey":   NEWS_API_KEY,
    }

    try:
        resp = requests.get(NEWS_API_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[NEWS] {ticker} 요청 실패: {e}")
        return []

    articles = []
    for art in data.get("articles", []):
        # [Removed] 같은 삭제된 기사 필터링
        title = art.get("title") or ""
        if "[Removed]" in title or not title.strip():
            continue

        articles.append({
            "source":    art.get("source", {}).get("name", "Unknown"),
            "time":      (art.get("publishedAt") or "")[:10],
            "title":     title,
            "content":   art.get("description") or "",
            "thumbnail": art.get("urlToImage")
                         or "https://via.placeholder.com/140x90/222/D85604?text=No+Image",
            "url":       art.get("url") or "",
        })

    return articles