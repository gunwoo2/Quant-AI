# (미사용) 초기 테이블 설정 시, S&P500 종목 OHLCV 밀어넣기용
import pandas as pd
import requests
import io
import psycopg2
from psycopg2.extras import execute_batch
import yfinance as yf
from datetime import datetime, timedelta
import time

# ==========================
# DB 설정
# ==========================
DB_CONFIG = {
    "host": "34.67.118.39",
    "database": "watchlist",
    "user": "postgres",
    "password": "rlarjsdn123!"
}

def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)


# ==========================
# S&P500 티커 수집
# ==========================
def get_index_tickers():
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    headers = {"User-Agent": "Mozilla/5.0"}

    response = requests.get(url, headers=headers)
    tables = pd.read_html(io.StringIO(response.text))
    df = tables[0]

    tickers = []
    for _, row in df.iterrows():
        ticker = str(row["Symbol"]).replace(".", "-")
        tickers.append(ticker)

    return tickers


# ==========================
# 메인 배치
# ==========================
def load_all_data():

    tickers = get_index_tickers()

    conn = get_db_connection()
    cur = conn.cursor()

    start_date = (datetime.today() - timedelta(days=365*3)).strftime("%Y-%m-%d")

    print("3년치 가격 다운로드 중...")
    price_data = yf.download(
        tickers=tickers,
        start=start_date,
        group_by="ticker",
        auto_adjust=False,
        threads=True,
        progress=True
    )

    print("DB 저장 시작...")

    for idx, ticker in enumerate(tickers):

        try:
            print(f"[{idx+1}/{len(tickers)}] {ticker} 처리 중...")

            stock = yf.Ticker(ticker)
            info = stock.get_info()

            # ---------------------------
            # Yahoo 정보 추출
            # ---------------------------
            company_name = (
                info.get("shortName")
                or info.get("longName")
                or ticker
            )

            sector = info.get("sector")
            industry = info.get("industry")
            exchange = info.get("exchange")
            description = info.get("longBusinessSummary")

            # country는 S&P500이므로 US 고정
            country = "US"

            pe = info.get("trailingPE")
            pbr = info.get("priceToBook")
            roa = info.get("returnOnAssets")
            roe = info.get("returnOnEquity")

            # ---------------------------
            # ticker_header INSERT/UPDATE
            # ---------------------------
            cur.execute("""
                INSERT INTO ticker_header (
                    ticker,
                    company_name,
                    sector,
                    industry,
                    exchange,
                    created_at,
                    description,
                    country
                )
                VALUES (%s, %s, %s, %s, %s, NOW(), %s, %s)
                ON CONFLICT (ticker)
                DO UPDATE SET
                    company_name = EXCLUDED.company_name,
                    sector = EXCLUDED.sector,
                    industry = EXCLUDED.industry,
                    exchange = EXCLUDED.exchange,
                    description = EXCLUDED.description,
                    country = EXCLUDED.country;
            """, (
                ticker,
                company_name,
                sector,
                industry,
                exchange,
                description,
                country
            ))

            # ---------------------------
            # 가격 데이터 저장
            # ---------------------------
            if ticker not in price_data:
                conn.commit()
                continue

            df = price_data[ticker].dropna()
            if df.empty:
                conn.commit()
                continue

            records = []

            for date, row in df.iterrows():
                records.append((
                    ticker,
                    date.date(),
                    float(row["Open"]),
                    float(row["High"]),
                    float(row["Low"]),
                    float(row["Close"]),
                    int(row["Volume"]),
                    pe,
                    pbr,
                    roa,
                    roe
                ))

            execute_batch(cur, """
                INSERT INTO ticker_item (
                    ticker,
                    trading_date,
                    open_price,
                    high_price,
                    low_price,
                    close_price,
                    volume,
                    per,
                    pbr,
                    roa,
                    roe
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (ticker, trading_date)
                DO UPDATE SET
                    open_price = EXCLUDED.open_price,
                    high_price = EXCLUDED.high_price,
                    low_price = EXCLUDED.low_price,
                    close_price = EXCLUDED.close_price,
                    volume = EXCLUDED.volume,
                    per = EXCLUDED.per,
                    pbr = EXCLUDED.pbr,
                    roa = EXCLUDED.roa,
                    roe = EXCLUDED.roe;
            """, records, page_size=1000)

            conn.commit()

            # Yahoo rate limit 완화
            time.sleep(0.3)

        except Exception as e:
            print(f"{ticker} 에러: {e}")
            conn.rollback()
            continue

    cur.close()
    conn.close()

    print("모든 작업 완료")


if __name__ == "__main__":
    load_all_data()