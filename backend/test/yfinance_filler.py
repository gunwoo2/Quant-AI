import yfinance as yf
import pandas as pd
from datetime import datetime
from database import get_db_connection

# --- 설정 ---
TICKER = "NVDA"

def fetch_and_insert_yahoo():
    conn = get_db_connection()
    cur = conn.cursor()
    
    print(f"🔍 [야후 파이낸스] {TICKER} 데이터 수집 시작...")

    try:
        # 1. 야후 파이낸스 티커 객체 생성
        stock = yf.Ticker(TICKER)

        # 2. 과거 시세 가져오기 (최근 2년치)
        hist = stock.history(period="2y")
        
        # 3. 추가 지표 (PER, ROE 등) - 현재 시점 값
        info = stock.info
        current_per = float(info.get('trailingPE', 0))
        current_f_per = float(info.get('forwardPE', 0))
        current_roa = float(info.get('returnOnAssets', 0)) * 100
        current_roe = float(info.get('returnOnEquity', 0)) * 100
        
        count = 0
        for date, row in hist.iterrows():
            date_str = date.strftime('%Y-%m-%d')
            
            # [핵심] 모든 데이터를 파이썬 기본 float/int로 변환하여 에러 방지
            val = {
                "ticker": TICKER,
                "date": date_str,
                "open": float(row['Open']),
                "high": float(row['High']),
                "low": float(row['Low']),
                "close": float(row['Close']),
                "volume": int(row['Volume']),
                "per": current_per,
                "f_per": current_f_per,
                "roa": current_roa,
                "roe": current_roe
            }
            
            query = """
                INSERT INTO ticker_item 
                (ticker, trading_date, open_price, high_price, low_price, close_price, volume, per, forward_per, roa, roe, roic)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (ticker, trading_date) DO UPDATE SET
                close_price = EXCLUDED.close_price,
                volume = EXCLUDED.volume;
            """
            
            cur.execute(query, (
                val["ticker"], val["date"], 
                round(val["open"], 2), round(val["high"], 2), 
                round(val["low"], 2), round(val["close"], 2), 
                val["volume"],
                round(val["per"], 2), round(val["f_per"], 2),
                round(val["roa"], 2), round(val["roe"], 2),
                0 # ROIC
            ))
            count += 1

        conn.commit()
        print(f"✅ 성공: {count}개의 {TICKER} 데이터가 'ticker_item'에 저장되었습니다.")

    except Exception as e:
        print(f"🚨 오류 발생: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    fetch_and_insert_yahoo()