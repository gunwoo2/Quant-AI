# (미사용) 아이템 테이블에 근 한달정도 OHLCV 정보 밀어넣기용
import os
import psycopg2
from psycopg2.extras import execute_values  # 👈 벌크 처리를 위한 핵심 도구
import yfinance as yf
import pandas as pd
from datetime import datetime
import time

def get_db_connection():
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "34.67.118.39"),
        database=os.environ.get("DB_NAME", "watchlist"),
        user=os.environ.get("DB_USER", "postgres"),
        password=os.environ.get("DB_PASS", "rlarjsdn123!")
    )

def run_fast_price_batch():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 1. 대상 티커 가져오기
    cur.execute("SELECT ticker FROM ticker_header")
    tickers = [row[0].strip().upper() for row in cur.fetchall()]
    
    # 2. UPSERT SQL 정의 (EXCLUDED 문법 사용)
    # 중복 시 모든 가격 정보를 최신으로 업데이트
    upsert_sql = """
    INSERT INTO ticker_item (
        ticker, trading_date, open_price, high_price, low_price, close_price, 
        volume, per, forward_per, roa, roe, roic
    ) VALUES %s
    ON CONFLICT (ticker, trading_date) 
    DO UPDATE SET 
        open_price = EXCLUDED.open_price,
        high_price = EXCLUDED.high_price,
        low_price = EXCLUDED.low_price,
        close_price = EXCLUDED.close_price,
        volume = EXCLUDED.volume,
        per = EXCLUDED.per,
        forward_per = EXCLUDED.forward_per,
        roa = EXCLUDED.roa,
        roe = EXCLUDED.roe;
    """

    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1mo")
            if hist.empty: continue
            
            info = stock.info
            
            # 데이터를 튜플 리스트로 변환 (메모리에 수집)
            data_values = []
            for date, row in hist.iterrows():
                # NaN(결측치) 처리까지 한 번에 하기 위해 float() 사용
                data_values.append((
                    ticker, date.date(),
                    float(row['Open']), float(row['High']), 
                    float(row['Low']), float(row['Close']),
                    int(row['Volume']),
                    float(info.get('trailingPE', 0) or 0), 
                    float(info.get('forwardPE', 0) or 0),
                    float(info.get('returnOnAssets', 0) or 0), 
                    float(info.get('returnOnEquity', 0) or 0),
                    0.0 # ROIC
                ))
            
            # 3. 일괄 전송 (티커당 쿼리 1번 실행)
            execute_values(cur, upsert_sql, data_values)
            conn.commit()
            
            print(f"✅ Fast Sync: {ticker} ({len(data_values)} rows)")
            time.sleep(0.1) # Yahoo API 차단 방지용 최소 대기
            
        except Exception as e:
            print(f"❌ Error {ticker}: {e}")
            conn.rollback()

    cur.close()
    conn.close()

if __name__ == "__main__":
    start_time = time.time()
    run_fast_price_batch()
    print(f"⏱️ Total Time: {time.time() - start_time:.2f} seconds")