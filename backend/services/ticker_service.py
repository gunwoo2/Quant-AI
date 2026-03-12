import yfinance as yf
from db_pool import get_cursor


def add_ticker(ticker: str) -> dict:
    """
    종목 추가.
    1. yfinance로 기본 정보 수집
    2. stocks 테이블 INSERT
    3. stock_like_counts 초기화
    """
    try:
        info = yf.Ticker(ticker).info

        company_name    = info.get("longName") or info.get("shortName") or ticker
        description     = info.get("longBusinessSummary")  # 추가
        exchange_code   = _normalize_exchange(info.get("exchange", "NASDAQ"))
        sector_code     = _normalize_sector(info.get("sector", ""))
        shares_out      = info.get("sharesOutstanding")
        float_shares    = info.get("floatShares")

        with get_cursor() as cur:
            cur.execute(
                "SELECT exchange_id FROM exchanges WHERE exchange_code = %s",
                (exchange_code,)
            )
            row = cur.fetchone()
            if not row:
                return {"success": False, "error": f"거래소 없음: {exchange_code}"}
            exchange_id = row["exchange_id"]

            cur.execute("SELECT market_id FROM markets WHERE market_code = 'US'")
            market_id = cur.fetchone()["market_id"]

            cur.execute(
                "SELECT sector_id FROM sectors WHERE sector_code = %s AND market_id = %s",
                (sector_code, market_id)
            )
            sector_row = cur.fetchone()
            sector_id = sector_row["sector_id"] if sector_row else None

            cur.execute("""
                INSERT INTO stocks (
                    ticker, company_name, company_name_en,
                    exchange_id, market_id, sector_id,
                    currency_code, shares_outstanding, float_shares,
                    description,                          
                    is_active
                ) VALUES (%s, %s, %s, %s, %s, %s, 'USD', %s, %s, %s, TRUE)
                ON CONFLICT (ticker, exchange_id) DO UPDATE
                SET is_active    = TRUE,
                    description  = EXCLUDED.description,
                    updated_at   = NOW()
                RETURNING stock_id
            """, (
                ticker, company_name, company_name,
                exchange_id, market_id, sector_id,
                shares_out, float_shares,
                description
            ))
            stock_id = cur.fetchone()["stock_id"]

            cur.execute("""
                INSERT INTO stock_like_counts (stock_id, like_count, updated_at)
                VALUES (%s, 0, NOW())
                ON CONFLICT (stock_id) DO NOTHING
            """, (stock_id,))

        return {"success": True, "ticker": ticker, "stock_id": stock_id}

    except Exception as e:
        return {"success": False, "error": str(e)}


def deactivate_tickers(tickers: list[str]) -> dict:
    """
    종목 삭제 - 실제 삭제 아닌 is_active = FALSE (데이터 보존)
    """
    with get_cursor() as cur:
        cur.execute("""
            UPDATE stocks
            SET is_active = FALSE, updated_at = NOW()
            WHERE ticker = ANY(%s)
            RETURNING ticker
        """, (tickers,))
        deleted = [row["ticker"] for row in cur.fetchall()]

    return {"success": True, "deleted": deleted}


# ── 내부 헬퍼 ──────────────────────────────────────────

def _normalize_exchange(exchange: str) -> str:
    """yfinance exchange 코드 → DB exchange_code 변환"""
    mapping = {
        "NMS": "NASDAQ",
        "NGM": "NASDAQ",
        "NCM": "NASDAQ",
        "NYQ": "NYSE",
        "NYSEArca": "NYSE",
        "PCX": "NYSE",
        "ASE": "AMEX",
    }
    return mapping.get(exchange, "NASDAQ")


def _normalize_sector(sector: str) -> str:
    """yfinance sector 문자열 → GICS sector_code 변환"""
    mapping = {
        "Energy":                 "10",
        "Basic Materials":        "15",
        "Industrials":            "20",
        "Consumer Cyclical":      "25",
        "Consumer Defensive":     "30",
        "Healthcare":             "35",
        "Financial Services":     "40",
        "Technology":             "45",
        "Communication Services": "50",
        "Utilities":              "55",
        "Real Estate":            "60",
    }
    return mapping.get(sector, "45")  # 기본값 IT