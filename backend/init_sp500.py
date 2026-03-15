#!/usr/bin/env python3
"""
init_sp500.py — S&P 500 종목 일괄 등록 (일회성 초기 셋팅)

사용법:
  python -m init_sp500

동작:
  1. Wikipedia에서 S&P 500 리스트 크롤링
  2. yfinance로 종목 정보 조회 (sector, exchange, shares 등)
  3. DB stocks 테이블에 INSERT (ON CONFLICT → UPDATE)
  4. OHLCV/재무 데이터는 등록하지 않음 (별도 배치잡에서 처리)

소요시간: 약 15~20분 (500종목 × yfinance 조회)
"""
import os, time, traceback
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor

# ─── DB 연결 (config.py의 settings 사용) ───
from config import settings

print(f"🔌 DB 연결: {settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}")
conn = psycopg2.connect(settings.DSN)
conn.autocommit = False


# ─── S&P 500 리스트 ───
def get_sp500_list():
    """Wikipedia에서 S&P 500 구성종목 가져오기"""
    import pandas as pd
    import requests
    from io import StringIO

    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

    # ★ Wikipedia가 봇 요청을 차단하므로 User-Agent 필수
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/124.0.0.0 Safari/537.36"
    }
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()

    tables = pd.read_html(StringIO(resp.text))
    df = tables[0]

    tickers = []
    for _, row in df.iterrows():
        ticker = str(row["Symbol"]).strip().replace(".", "-")  # BRK.B → BRK-B
        sector = str(row.get("GICS Sector", ""))
        sub_industry = str(row.get("GICS Sub-Industry", ""))
        company = str(row.get("Security", ""))
        tickers.append({
            "ticker": ticker,
            "company": company,
            "sector_wiki": sector,
            "sub_industry": sub_industry,
        })

    print(f"📋 S&P 500 목록: {len(tickers)}개 종목")
    return tickers


# ─── 섹터 매핑 (GICS → DB sector_code) ───
SECTOR_MAP = {
    "Information Technology":     "45",
    "Health Care":                "35",
    "Financials":                 "40",
    "Consumer Discretionary":     "25",
    "Consumer Staples":           "30",
    "Industrials":                "20",
    "Energy":                     "10",
    "Materials":                  "15",
    "Real Estate":                "60",
    "Utilities":                  "55",
    "Communication Services":     "50",
}

EXCHANGE_MAP = {
    "NMS": "NASDAQ", "NGM": "NASDAQ", "NCM": "NASDAQ", "NAS": "NASDAQ",
    "NYQ": "NYSE",   "NYS": "NYSE",  "PCX": "NYSE",
    "ASE": "AMEX",   "AMX": "AMEX",
}


def register_stocks(stock_list):
    """DB에 종목 일괄 등록"""
    import yfinance as yf

    cur = conn.cursor(cursor_factory=RealDictCursor)

    # market_id 조회
    cur.execute("SELECT market_id FROM markets WHERE market_code = 'US'")
    market_id = cur.fetchone()["market_id"]

    total = len(stock_list)
    ok, skip, fail = 0, 0, 0

    for idx, s in enumerate(stock_list):
        ticker = s["ticker"]
        progress = f"[{idx+1}/{total}]"

        try:
            # yfinance 정보 조회
            tk = yf.Ticker(ticker)
            info = tk.info or {}

            company_name = info.get("longName") or info.get("shortName") or s["company"]
            description  = info.get("longBusinessSummary", "")[:2000]
            shares_out   = info.get("sharesOutstanding")
            float_shares = info.get("floatShares")
            ipo_date     = info.get("ipoDate")

            # 거래소
            raw_exchange  = info.get("exchange", "NMS")
            exchange_code = EXCHANGE_MAP.get(raw_exchange, "NASDAQ")

            cur.execute(
                "SELECT exchange_id FROM exchanges WHERE exchange_code = %s",
                (exchange_code,)
            )
            row = cur.fetchone()
            if not row:
                print(f"  {progress} ⚠️  {ticker} 거래소 없음: {exchange_code} → NASDAQ")
                cur.execute("SELECT exchange_id FROM exchanges WHERE exchange_code = 'NASDAQ'")
                row = cur.fetchone()
            exchange_id = row["exchange_id"]

            # 섹터 (Wikipedia GICS → DB sector_code)
            sector_code = SECTOR_MAP.get(s["sector_wiki"], "45")
            # yfinance에서 더 정확한 값이 있으면 대체
            yf_sector = info.get("sector", "")
            yf_map = {
                "Technology": "45", "Healthcare": "35",
                "Financial Services": "40", "Consumer Cyclical": "25",
                "Consumer Defensive": "30", "Industrials": "20",
                "Energy": "10", "Materials": "15",
                "Real Estate": "60", "Utilities": "55",
                "Communication Services": "50",
            }
            if yf_sector in yf_map:
                sector_code = yf_map[yf_sector]

            cur.execute(
                "SELECT sector_id FROM sectors WHERE sector_code = %s AND market_id = %s",
                (sector_code, market_id)
            )
            sector_row = cur.fetchone()
            sector_id  = sector_row["sector_id"] if sector_row else None

            # listing_date
            listing_date = None
            if ipo_date:
                try:
                    listing_date = datetime.strptime(str(ipo_date), "%Y-%m-%d").date()
                except:
                    pass

            # INSERT / UPDATE
            cur.execute("""
                INSERT INTO stocks (
                    ticker, company_name, company_name_en,
                    exchange_id, market_id, sector_id,
                    currency_code, shares_outstanding, float_shares,
                    description, listing_date, is_active
                ) VALUES (%s, %s, %s, %s, %s, %s, 'USD', %s, %s, %s, %s, TRUE)
                ON CONFLICT (ticker, exchange_id) DO UPDATE SET
                    company_name        = EXCLUDED.company_name,
                    company_name_en     = EXCLUDED.company_name_en,
                    sector_id           = EXCLUDED.sector_id,
                    shares_outstanding  = EXCLUDED.shares_outstanding,
                    float_shares        = EXCLUDED.float_shares,
                    description         = EXCLUDED.description,
                    is_active           = TRUE,
                    updated_at          = NOW()
                RETURNING stock_id
            """, (
                ticker, company_name, company_name,
                exchange_id, market_id, sector_id,
                shares_out, float_shares,
                description, listing_date,
            ))
            stock_id = cur.fetchone()["stock_id"]

            # like_counts 초기화
            cur.execute("""
                INSERT INTO stock_like_counts (stock_id, like_count, updated_at)
                VALUES (%s, 0, NOW())
                ON CONFLICT (stock_id) DO NOTHING
            """, (stock_id,))

            conn.commit()
            ok += 1
            print(f"  {progress} ✅ {ticker:6s} → stock_id={stock_id}  {company_name[:40]}")

        except Exception as e:
            conn.rollback()
            fail += 1
            print(f"  {progress} ❌ {ticker:6s} → {str(e)[:80]}")
            traceback.print_exc()

        # yfinance rate limit 방지 (0.5초 간격)
        if (idx + 1) % 10 == 0:
            time.sleep(2)
        else:
            time.sleep(0.5)

    print(f"\n{'='*60}")
    print(f"  S&P 500 등록 완료!")
    print(f"  ✅ 성공: {ok}  ⏭️  스킵: {skip}  ❌ 실패: {fail}")
    print(f"{'='*60}")


def main():
    start = time.time()
    print("=" * 60)
    print("  S&P 500 종목 일괄 등록 시작")
    print("=" * 60)

    stock_list = get_sp500_list()
    register_stocks(stock_list)

    elapsed = round(time.time() - start, 1)
    print(f"\n⏱️  총 소요시간: {elapsed}초")

    conn.close()
    print("DB 연결 종료")


if __name__ == "__main__":
    main()
