"""
news_service.py — 종목별 뉴스 조회 (newsapi.org)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import os
import requests
from typing import Optional
from datetime import datetime, timedelta


NEWS_API_URL = "https://newsapi.org/v2/everything"


def get_news_by_ticker(
    ticker: str,
    company_name: Optional[str] = None,
    page_size: int = 10,
) -> list[dict]:
    """
    종목 관련 뉴스 조회.
    Returns: [{source, time, title, content, thumbnail, url}, ...]
    """
    api_key = os.getenv("NEWS_API_KEY", "")

    if not api_key:
        print("[NEWS] ⚠️  NEWS_API_KEY is empty!")
        return []

    # 검색 쿼리
    query = ticker
    if company_name:
        short_name = company_name.split(",")[0].split(" Inc")[0].split(" Corp")[0].strip()
        if short_name and short_name.upper() != ticker.upper():
            query = f'"{short_name}" OR "{ticker}"'

    # ★ Free plan: 최근 1일만 허용 → 오늘 기준 어제부터 조회
    #   실패 시 from 파라미터 없이 재시도
    from_date = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")

    params = {
        "q":        query,
        "from":     from_date,
        "sortBy":   "publishedAt",
        "language": "en",
        "pageSize": page_size,
        "apiKey":   api_key,
    }

    print(f"[NEWS] ticker={ticker}, q={query}, from={from_date}")

    raw = _call_api(params, ticker)

    # ★ from 날짜 에러 시 → from 제거하고 재시도 (API 기본값 사용)
    if raw is None:
        print("[NEWS] Retrying without 'from' parameter...")
        params.pop("from", None)
        raw = _call_api(params, ticker)

    if raw is None:
        return []

    articles = []
    for art in raw.get("articles", []):
        title = art.get("title") or ""
        if "[Removed]" in title or not title.strip():
            continue

        articles.append({
            "source":    art.get("source", {}).get("name", "Unknown"),
            "time":      (art.get("publishedAt") or "")[:10],
            "title":     title,
            "content":   art.get("description") or "",
            "thumbnail": art.get("urlToImage") or "",
            "url":       art.get("url") or "",
        })

    print(f"[NEWS] ✅ Returning {len(articles)} articles")
    return articles


def _call_api(params: dict, ticker: str) -> dict | None:
    """newsapi.org 호출 + 에러 핸들링"""
    try:
        resp = requests.get(NEWS_API_URL, params=params, timeout=10)
        raw = resp.json()

        status = raw.get("status", "unknown")
        total  = raw.get("totalResults", 0)
        print(f"[NEWS] Response: status={resp.status_code}, api_status={status}, total={total}")

        if status != "ok":
            err_msg = raw.get("message", "")
            print(f"[NEWS] ❌ API Error: {err_msg}")
            return None

        return raw

    except Exception as e:
        print(f"[NEWS] ❌ Request failed: {e}")
        return None
