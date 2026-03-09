import requests
import json
import os
import sys

# 시스템 경로 설정
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.join(current_dir, "..")
sys.path.insert(0, os.path.abspath(backend_dir))

from secret_info.config import settings

def get_access_token():
    url = f"{settings.KIS_BASE_URL}/oauth2/tokenP"
    payload = {
        "grant_type": "client_credentials",
        "appkey": settings.KIS_APP_KEY,
        "appsecret": settings.KIS_APP_SECRET
    }
    res = requests.post(url, data=json.dumps(payload))
    return res.json().get("access_token") if res.status_code == 200 else None

def safe_float(value, default=0.0):
    """빈 문자열이나 None을 안전하게 float으로 변환"""
    if value is None or str(value).strip() == "":
        return default
    try:
        return float(value)
    except ValueError:
        return default

def test_overseas_price(ticker_list):
    token = get_access_token()
    if not token: return

    url = f"{settings.KIS_BASE_URL}/uapi/overseas-price/v1/quotations/price"
    headers = {
        "Content-Type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": settings.KIS_APP_KEY,
        "appsecret": settings.KIS_APP_SECRET,
        "tr_id": "HHDFS76200200",
        "custtype": "P"
    }

    for ticker in ticker_list:
        ticker = ticker.strip().upper()
        found = False
        
        for exch in ["NAS", "NYS", "AMS"]:
            params = {"AUTH": "", "EXCD": exch, "SYMB": ticker}
            try:
                res = requests.get(url, headers=headers, params=params, timeout=5)
                output = res.json().get("output")

                # 데이터가 있고, 현재가(last)가 비어있지 않은 경우만 처리
                if output and output.get("last"):
                    curr = safe_float(output.get("last"))
                    base = safe_float(output.get("base"))
                    open_p = safe_float(output.get("open")) # 🚨 'open_p' 변수 정의
                    high = safe_float(output.get("high"))
                    low = safe_float(output.get("low"))
                    vol = safe_float(output.get("tvol"))

                    # 등락 계산
                    diff = round(curr - base, 4)
                    rate = round((diff / base * 100), 2) if base > 0 else 0.0

                    print(f"\n======== [ {ticker} / {exch} ] ========")
                    print(f"📈 현재가: ${curr}")
                    print(f"📊 등락률: {rate}% (전일대비: {diff})")
                    print(f"🌅 시가: ${open_p} | ⛰ 고가: ${high} | 📉 저가: ${low}")
                    print(f"🔄 거래량: {int(vol)}")
                    
                    found = True
                    break # 데이터를 찾았으므로 다음 거래소 조회 안 함
            except Exception:
                continue # 에러 발생 시(데이터 없음 등) 다음 거래소로 조용히 이동

        if not found:
            print(f"❌ {ticker}: 모든 거래소에서 데이터를 찾을 수 없습니다.")

if __name__ == "__main__":
    test_overseas_price(["AAPL", "TSLA", "NVDA"])