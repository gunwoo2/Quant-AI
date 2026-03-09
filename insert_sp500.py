import pandas as pd
import requests
import io
import psycopg2
import yfinance as yf
from datetime import datetime
import time

# DB 설정
DB_CONFIG = {
    "host": "34.67.118.39",
    "database": "watchlist",
    "user": "postgres",
    "password": "rlarjsdn123!" # 실제 비밀번호 반영
}

def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)

def get_index_tickers():
    """S&P 500과 Nasdaq 100을 가져와서 통합 리스트 반환"""
    print("📋 종목 리스트 수집 중...")
    headers = {"User-Agent": "Mozilla/5.0"}
    
    # 1. S&P 500 (기존 로직 적용)
    sp500_res = requests.get('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies', headers=headers)
    sp500_df = pd.read_html(io.StringIO(sp500_res.text))
    sp500_data = sp500_df[['Symbol', 'Security', 'GICS Sector']].values.tolist()

    # 2. Nasdaq 100 (추가)
    nasdaq_res = requests.get('https://en.wikipedia.org/wiki/Nasdaq-100', headers=headers)
    nasdaq_df = pd.read_html(io.StringIO(nasdaq_res.text)) # Ticker 컬럼이 있는 표
    nasdaq_data = nasdaq_df[['Ticker', 'Company']].values.tolist()

    # 데이터 정리 (Symbol: [Name, Sector])
    master_dict = {}
    for sym, name, sec in sp500_data:
        master_dict[sym.replace('.', '-')] = [name, sec.lower().replace(' ', '').replace('&', '')]
    
    for sym, name in nasdaq_data:
        ticker = sym.replace('.', '-')
        if ticker not in master_dict:
            master_dict[ticker] = [name, 'technology'] # 나스닥 기본 섹터 임시 지정

    print(f"✅ 총 {len(master_dict)}개 고유 종목 확보")
    return master_dict

def load_all_data():
    ticker_map = get_index_tickers()
    conn = get_db_connection()
    cur = conn.cursor()
    
    for idx, (ticker, info_list) in enumerate(ticker_map.items()):
        try:
            # 20종목마다 3초 휴식 (API 차단 방지)
            if idx > 0 and idx % 20 == 0:
                print("☕ API 과부하 방지 휴식 중...")
                time.sleep(3)

            print(f"[{idx+1}/{len(ticker_map)}] 📥 {ticker} 데이터 수집...")
            stock = yf.Ticker(ticker)
            
            # 1. TICKER_HEADER 업데이트 (기존 로직 유지 + industry 추가)
            name = info_list
            sector = info_list
            
            # 실시간 데이터에서 더 상세한 정보 추출
            y_info = stock.info
            full_name = y_info.get('shortName', name)
            industry = y_info.get('industry', 'N/A')

            cur.execute("""
                INSERT INTO ticker_header (ticker, name, sector, industry)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (ticker) DO UPDATE SET
                    name = EXCLUDED.name,
                    sector = EXCLUDED.sector,
                    industry = EXCLUDED.industry;
            """, (ticker, full_name, sector, industry))

            # 2. 1년치 시세 및 지표 저장 (TICKER_ITEM)
            hist = stock.history(period="1y")
            if hist.empty: continue

            # 지표 데이터 미리 추출
            metrics = (
                y_info.get('trailingPE'),
                y_info.get('priceToBook'),
                y_info.get('returnOnAssets'),
                y_info.get('returnOnEquity')
            )

            for date, row in hist.iterrows():
                cur.execute("""
                    INSERT INTO ticker_item (
                        ticker, trading_date, open_price, high_price, low_price, close_price, volume,
                        per, pbr, roa, roe
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (ticker, trading_date) DO UPDATE SET
                        close_price = EXCLUDED.close_price;
                """, (
                    ticker, date.date(), 
                    float(row['Open']), float(row['High']), float(row['Low']), float(row['Close']), int(row['Volume']),
                    metrics, metrics, metrics, metrics
                ))

            conn.commit()
            time.sleep(0.2)

        except Exception as e:
            print(f"⚠️ {ticker} 에러: {e}")
            conn.rollback()
            continue

    cur.close()
    conn.close()
    print("🏁 모든 작업이 성공적으로 완료되었습니다!")

if __name__ == "__main__":
    load_all_data()