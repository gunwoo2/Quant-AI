"""
/home/gguakim33/stock-app/stock-app/backend/services/kis_api_service.py
한투 API를 통해 정보 가져오는 로직
"""
import os
import sys
import requests
import json
import time
import threading

# ✅ 경로 및 설정 유지
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.abspath(os.path.join(current_dir, ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from secret_info.config import settings

kis_session = requests.Session()
ACCESS_TOKEN = None
TOKEN_EXPIRE_TIME = 0
token_lock = threading.Lock()

def safe_float(value, default=0.0):
    if value is None or str(value).strip() == "": return default
    try: return float(value)
    except (ValueError, TypeError): return default

def get_access_token():
    global ACCESS_TOKEN, TOKEN_EXPIRE_TIME
    if ACCESS_TOKEN and time.time() < TOKEN_EXPIRE_TIME - 3600:
        return ACCESS_TOKEN
    with token_lock:
        if ACCESS_TOKEN and time.time() < TOKEN_EXPIRE_TIME - 3600:
            return ACCESS_TOKEN
        url = f"{settings.KIS_BASE_URL}/oauth2/tokenP"
        payload = {
            "grant_type": "client_credentials",
            "appkey": settings.KIS_APP_KEY,
            "appsecret": settings.KIS_APP_SECRET
        }
        try:
            res = requests.post(url, json=payload, timeout=5)
            if res.status_code == 200:
                data = res.json()
                ACCESS_TOKEN = data.get("access_token")
                expires_in = int(data.get("expires_in", 86400))
                TOKEN_EXPIRE_TIME = time.time() + expires_in
                return ACCESS_TOKEN
        except Exception as e:
            print(f"🚨 KIS 토큰 예외: {e}")
    return None

def get_kis_realtime_price(ticker):
    token = get_access_token()
    if not token: return None

    ticker = ticker.upper()
    headers = {
        "Content-Type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": settings.KIS_APP_KEY,
        "appsecret": settings.KIS_APP_SECRET,
        "custtype": "P"
    }

    price_url = f"{settings.KIS_BASE_URL}/uapi/overseas-price/v1/quotations/price"
    detail_url = f"{settings.KIS_BASE_URL}/uapi/overseas-price/v1/quotations/price-detail"
    
    # 여러 거래소를 순회하며 데이터를 찾음
    exchanges = ["NAS", "NYS", "AMS"]
    
    for exch in exchanges:
        try:
            # A. 기본 시세 호출
            p_res = kis_session.get(price_url, headers={**headers, "tr_id": "HHDFS76200200"}, 
                                    params={"AUTH": "", "EXCD": exch, "SYMB": ticker}, timeout=0.8)
            
            if p_res.status_code == 200:
                p_data = p_res.json()
                
                # rt_cd가 "0"이고 output 데이터가 존재할 때만 로직 수행
                if p_data.get("rt_cd") == "0" and p_data.get("output"):
                    out = p_data.get("output", {})
                    last = safe_float(out.get("last"))
                    
                    # 🚨 [매우 중요] 해당 거래소에 종목이 없으면 last가 0으로 옴.
                    # 이 경우 '성공'으로 간주해서 루프를 끝내면 안 되고, continue로 다음 거래소를 확인해야 함.
                    if last <= 0:
                        continue

                    # 정상 가격을 찾은 경우 데이터 파싱 시작
                    base = safe_float(out.get("base"))
                    raw_diff = out.get("diff")
                    raw_rate = out.get("rate")

                    # 등락률 계산 (값이 0인 경우 수동 계산)
                    if (raw_diff is None or safe_float(raw_diff) == 0) and last != 0 and base > 0:
                        diff = last - base
                        rate = (diff / base) * 100
                    else:
                        diff = safe_float(raw_diff)
                        rate = safe_float(raw_rate)

                    # 결과 객체 생성 (기존 필드 유지)
                    result = {
                        "price": round(last, 2),
                        "change": round(rate, 2),           # 등락률로 통일
                        "amount_change": round(diff, 2),    # 등락 금액
                        "changesPercentage": round(rate, 2),
                    }

                    # B. 상세 지표 호출 (EPS, PER, PBR 등 수집)
                    try:
                        d_res = kis_session.get(detail_url, headers={**headers, "tr_id": "HHDFS76200200"}, 
                                                params={"AUTH": "", "EXCD": exch, "SYMB": ticker}, timeout=0.8)
                        
                        if d_res.status_code == 200:
                            d_data = d_res.json()
                            if d_data.get("rt_cd") == "0" and d_data.get("output"):
                                d_out = d_data.get("output", {})
                                
                                # 투자 지표 업데이트
                                result.update({
                                    "eps": safe_float(d_out.get("epsx")), 
                                    "per": safe_float(d_out.get("perx")),
                                    "pbr": safe_float(d_out.get("pbrx")),
                                })
                                
                                # 2차 방어: 상세 정보의 base로 등락률 재검증 (원본 로직 유지)
                                if result.get("changesPercentage") == 0:
                                    d_base = safe_float(d_out.get("base"))
                                    if d_base > 0 and last != d_base:
                                        diff_2 = last - d_base
                                        rate_2 = (diff_2 / d_base) * 100
                                        result["change"] = round(rate_2, 2)
                                        result["changesPercentage"] = round(rate_2, 2)
                    except Exception as e:
                        print(f"⚠️ {ticker} 상세지표 호출 중 에러(무시): {e}")

                    # ✅ 유효한 데이터를 찾았으므로 즉시 리턴하여 루프 종료
                    return result

        except Exception as e:
            # 타임아웃이나 네트워크 에러 시 다음 거래소 시도
            continue
            
    # 모든 거래소(NAS, NYS, AMS)를 확인했으나 유효한(last > 0) 데이터를 못 찾은 경우
    # 명확하게 None을 반환해야 api_service.py에서 Yahoo를 호출함.
    return None
            
    # 모든 거래소를 돌았는데도 데이터를 못 찾은 경우만 None 리턴 (그래야 Yahoo가 등판함)
    return None

#####################################################    
# import os
# import sys
# import requests
# import json
# import time
# import threading

# # ✅ 경로 설정
# current_dir = os.path.dirname(os.path.abspath(__file__))
# backend_dir = os.path.abspath(os.path.join(current_dir, ".."))
# if backend_dir not in sys.path:
#     sys.path.insert(0, backend_dir)

# from secret_info.config import settings

# # ✅ 전역 설정
# kis_session = requests.Session()
# ACCESS_TOKEN = None
# TOKEN_EXPIRE_TIME = 0
# token_lock = threading.Lock()

# def safe_float(value, default=0.0):
#     if value is None or str(value).strip() == "":
#         return default
#     try:
#         return float(value)
#     except (ValueError, TypeError):
#         return default

# def get_access_token():
#     """토큰 안전 발급 및 캐싱"""
#     global ACCESS_TOKEN, TOKEN_EXPIRE_TIME
#     if ACCESS_TOKEN and time.time() < TOKEN_EXPIRE_TIME - 3600:
#         return ACCESS_TOKEN

#     with token_lock:
#         if ACCESS_TOKEN and time.time() < TOKEN_EXPIRE_TIME - 3600:
#             return ACCESS_TOKEN

#         url = f"{settings.KIS_BASE_URL}/oauth2/tokenP"
#         payload = {
#             "grant_type": "client_credentials",
#             "appkey": settings.KIS_APP_KEY,
#             "appsecret": settings.KIS_APP_SECRET
#         }

#         try:
#             res = requests.post(url, json=payload, timeout=5)
#             if res.status_code == 200:
#                 data = res.json()
#                 ACCESS_TOKEN = data.get("access_token")
#                 expires_in = int(data.get("expires_in", 86400))
#                 TOKEN_EXPIRE_TIME = time.time() + expires_in
#                 print(f"✅ KIS 토큰 새 발급 성공 (만료: {expires_in // 3600}시간 후)")
#                 return ACCESS_TOKEN
#             else:
#                 print(f"❌ KIS 토큰 발급 실패: {res.text}")
#         except Exception as e:
#             print(f"🚨 KIS 토큰 예외 발생: {e}")
#     return None

# def get_kis_realtime_price(ticker):
#     token = get_access_token()
#     if not token: return None

#     ticker = ticker.upper()
#     url = f"{settings.KIS_BASE_URL}/uapi/overseas-price/v1/quotations/price"
#     headers = {
#         "Content-Type": "application/json",
#         "authorization": f"Bearer {token}",
#         "appkey": settings.KIS_APP_KEY,
#         "appsecret": settings.KIS_APP_SECRET,
#         "tr_id": "HHDFS76200200",
#         "custtype": "P"
#     }

#     # 💡 팁: CVS 같은 종목은 대부분 NYS나 NAS에 있습니다. 
#     # 에러 발생 시 바로 다음 단계(Yahoo)로 넘어가게 설계합니다.
#     for exch in ["NAS", "NYS", "AMS"]:
#         try:
#             # 💡 속도 핵심: timeout을 0.5초로 줄이고, 
#             # 한 번 연결 실패한 거래소는 즉시 패스합니다.
#             res = kis_session.get(url, headers=headers, 
#                                   params={"AUTH": "", "EXCD": exch, "SYMB": ticker}, 
#                                   timeout=0.5)
            
#             if res.status_code == 200:
#                 data = res.json()
#                 if data.get("rt_cd") == "0":
#                     out = data.get("output")
#                     if out and safe_float(out.get("last")) > 0:
#                         last = safe_float(out.get("last"))
#                         base = safe_float(out.get("base"))
#                         rate = safe_float(out.get("rate"))
#                         if rate == 0 and base > 0:
#                             rate = ((last - base) / base) * 100
#                         return {"price": round(last, 2), "change": round(rate, 2)}
                
#                 # 해당 거래소에 종목이 없으면(7) 다음 거래소로 이동
#                 if data.get("rt_cd") == "7": continue
                
#         except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
#             # 🚨 연결 에러 발생 시 로그를 남기지 않고 조용히 None 리턴하여 
#             # 메인 로직에서 Yahoo가 바로 실행되게 합니다.
#             continue
            
#     return None