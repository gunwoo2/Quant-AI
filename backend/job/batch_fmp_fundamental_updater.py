# (미사용) FMP 연결 테스트
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
import time

# ==========================
# 설정 (키 확인 필수!)
# ==========================
FMP_API_KEY = "LI0SFj8woN32bSc3IKjJKEWEZ9kgRAJB"
DB_CONFIG = {
    "host": "34.67.118.39",
    "database": "watchlist",
    "user": "postgres",
    "password": "rlarjsdn123!"
}

def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)

# ==========================
# FMP 데이터 수집 (멀티 엔드포인트 전략)
# ==========================
def get_fmp_fundamentals(ticker):
    # 시도할 엔드포인트 리스트 (가장 상세한 것부터)
    endpoints = [
        f"https://financialmodelingprep.com/api/v3/key-metrics-ttm/{ticker}?apikey={FMP_API_KEY}",
        f"https://financialmodelingprep.com/api/v3/ratios-ttm/{ticker}?apikey={FMP_API_KEY}",
        f"https://financialmodelingprep.com/api/v3/quote/{ticker}?apikey={FMP_API_KEY}"
    ]

    for url in endpoints:
        try:
            res = requests.get(url, timeout=10)
            
            # 403이나 401 뜨면 키 문제거나 플랜 제한임
            if res.status_code != 200:
                print(f"   ⚠️ {ticker} API 응답 오류: {res.status_code} (URL: {url.split('?')})")
                continue

            data = res.json()
            if not data or not isinstance(data, list):
                continue

            d = data
            print(f"   ✅ {ticker} 데이터 확보 성공! (출처: {url.split('?')})")
            
            # 엔드포인트마다 필드명이 다를 수 있으므로 통합 추출
            return {
                "per": d.get("peRatioTTM") or d.get("peRatio") or d.get("pe"),
                "forward_per": d.get("forwardPeRatioTTM") or d.get("forwardPeRatio"),
                "pbr": d.get("pbRatioTTM") or d.get("priceToBookRatioTTM") or d.get("priceToBook"),
                "eps": d.get("netIncomePerShareTTM") or d.get("eps"),
                "roe": d.get("returnOnEquityTTM") or d.get("returnOnEquity"),
                "roa": d.get("returnOnAssetsTTM") or d.get("returnOnAssets"),
                "roi": d.get("returnOnInvestmentTTM") or d.get("returnOnInvestment"),
                "roic": d.get("roicTTM") or d.get("roic")
            }

        except Exception as e:
            print(f"   🚨 {ticker} 호출 중 예외: {e}")
            continue

    return None

# ==========================
# DB 업데이트 (기존 유지)
# ==========================
def update_latest_row(cur, ticker, fundamentals):
    cur.execute("""
        UPDATE ticker_item
        SET
            per = %s, forward_per = %s, pbr = %s, eps = %s,
            roe = %s, roa = %s, roi = %s, roic = %s
        WHERE ticker = %s
        AND trading_date = (SELECT MAX(trading_date) FROM ticker_item WHERE ticker = %s);
    """, (
        fundamentals.get("per"), fundamentals.get("forward_per"), fundamentals.get("pbr"), fundamentals.get("eps"),
        fundamentals.get("roe"), fundamentals.get("roa"), fundamentals.get("roi"), fundamentals.get("roic"),
        ticker, ticker
    ))

def run_fmp_update():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("SELECT DISTINCT ticker FROM ticker_header;")
    tickers = [row["ticker"].upper() for row in cur.fetchall()]

    print(f"\n🚀 총 {len(tickers)}개 종목 FMP 심층 업데이트 시작\n")

    for idx, ticker in enumerate(tickers):
        print(f"[{idx+1}/{len(tickers)}] {ticker} 분석 중...")
        fundamentals = get_fmp_fundamentals(ticker)

        if fundamentals:
            try:
                update_latest_row(cur, ticker, fundamentals)
                conn.commit()
                print(f"   💰 {ticker} DB 업데이트 완료")
            except Exception as e:
                print(f"   ❌ {ticker} DB 에러: {e}")
                conn.rollback()
        else:
            print(f"   💀 {ticker} 모든 경로 실패")
        
        time.sleep(0.2) # 속도 조절

    cur.close()
    conn.close()
    print("\n🏁 모든 작업이 종료되었습니다.")

if __name__ == "__main__":
    run_fmp_update()