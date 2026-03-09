import requests


def test_fmp_api():
    # v3 대신 공식 문서에서 권장하는 최신 엔드포인트 구조 사용
    url = f"https://financialmodelingprep.com/api/v3/quote/AAPL?apikey={FMP_API_KEY}"
    # 만약 위가 안되면 아래 stable 경로가 신규 사용자용입니다.
    # url = f"https://financialmodelingprep.com/stable/quote?symbol=AAPL&apikey={FMP_API_KEY}"
    
    print(f"📡 최신 API 테스트 요청: {url}")
    
    try:
        response = requests.get(url, timeout=10)
        print(f"✅ 상태 코드: {response.status_code}")
        
        if response.status_code == 200:
            print(f"📦 응답 데이터: {response.json()}")
        else:
            # v3가 막혔다면 stable 경로로 재시도
            print("🔄 v3 차단 확인. stable 경로로 재시도합니다...")
            stable_url = f"https://financialmodelingprep.com/stable/quote?symbol=AAPL&apikey={FMP_API_KEY}"
            res_stable = requests.get(stable_url, timeout=10)
            print(f"✅ stable 상태 코드: {res_stable.status_code}")
            print(f"📦 stable 데이터: {res_stable.json()}")

    except Exception as e:
        print(f"🚨 에러 발생: {e}")

if __name__ == "__main__":
    test_fmp_api()