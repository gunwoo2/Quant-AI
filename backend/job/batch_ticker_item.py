# (미사용) 아이템 테이블에 근 3년치 OHLCV 정보 밀어넣기용
import os
import psycopg2
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

def run_price_batch():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 1. 대상 티커 가져오기
    cur.execute("SELECT ticker FROM ticker_header")
    tickers = [row for row in cur.fetchall()]
    
    for ticker in tickers:
        try:
            # yfinance로 최근 가격 데이터 가져오기 (기술적 지표 계산용)
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1mo") # 최소 한달치는 있어야 지표 계산 가능
            if hist.empty: continue
            
            last_row = hist.iloc[-1]
            info = stock.info
            
            # 기술적 지표 간이 계산 (실제 서비스 로직 적용)
            close_price = last_row['Close']
            
            # DB Insert
            sql = """
            INSERT INTO ticker_item (
                ticker, trading_date, open_price, high_price, low_price, close_price, 
                volume, per, forward_per, roa, roe, roic
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (ticker, trading_date) DO UPDATE SET close_price = EXCLUDED.close_price;
            """
            cur.execute(sql, (
                ticker, datetime.now().date(),
                last_row['Open'], last_row['High'], last_row['Low'], close_price,
                last_row['Volume'],
                info.get('trailingPE', 0), info.get('forwardPE', 0),
                info.get('returnOnAssets', 0), info.get('returnOnEquity', 0),
                0 # ROIC는 아래 퀀트 배치에서 상세 계산 후 업데이트 권장
            ))
            conn.commit()
            print(f"✅ Price Sync: {ticker}")
            time.sleep(0.2) # API 제한 방지
        except Exception as e:
            print(f"❌ Price Error {ticker}: {e}")
            conn.rollback()

    cur.close()
    conn.close()

if __name__ == "__main__":
    run_price_batch()