import FinanceDataReader as fdr
from datetime import datetime, time, timedelta
import pytz
import json
import pandas_market_calendars as mcal


NY_TZ = pytz.timezone("America/New_York")
MARKET_OPEN       = time(9, 30)
MARKET_CLOSE      = time(16, 0)
PRE_MARKET_OPEN   = time(4, 0)
AFTER_HOURS_CLOSE = time(20, 0)


# ──────────────────────────────────────────────────────────
#  MarketMarquee 전체 심볼 정의
# ──────────────────────────────────────────────────────────
MARQUEE_TARGETS = [
    # 미국 지수
    ("S&P500",   "S&P 500",      "US_INDEX"),
    ("IXIC",     "NASDAQ",       "US_INDEX"),
    ("DJI",      "DOW",          "US_INDEX"),
    ("^VIX",     "VIX",          "US_INDEX"),

    # 한국 지수
    ("KS11",     "KOSPI",        "KR_INDEX"),
    ("KQ11",     "KOSDAQ",       "KR_INDEX"),

    # 글로벌 지수
    ("N225",     "니케이225",     "GLOBAL_INDEX"),
    ("HSI",      "항셍",          "GLOBAL_INDEX"),
    ("000001.SS","상하이",        "GLOBAL_INDEX"),
    ("FTSE",     "FTSE100",      "GLOBAL_INDEX"),
    ("GDAXI",    "DAX",          "GLOBAL_INDEX"),

    # 환율
    ("USD/KRW",  "달러/원",       "FX"),
    ("USD/EUR",  "달러/유로",     "FX"),
    ("USD/CNY",  "달러/위안",     "FX"),
    ("USD/JPY",  "달러/엔",       "FX"),

    # 달러 인덱스
    ("^NYICDX",  "달러인덱스",    "FX"),

    # 미국 국채
    ("US10YT",   "미국10년채",    "BOND"),
    ("US5YT",    "미국5년채",     "BOND"),
    ("US30YT",   "미국30년채",    "BOND"),

    # 상품 선물
    ("GC=F",     "금",            "COMMODITY"),
    ("SI=F",     "은",            "COMMODITY"),
    ("CL=F",     "WTI유",         "COMMODITY"),
    ("BZ=F",     "브렌트유",      "COMMODITY"),
    ("NG=F",     "천연가스",      "COMMODITY"),
    ("HG=F",     "구리",          "COMMODITY"),

    # 암호화폐
    ("BTC/USD",  "비트코인",      "CRYPTO"),
    ("ETH/USD",  "이더리움",      "CRYPTO"),
]


def _fetch_one(symbol: str, label: str, category: str) -> dict:
    """단일 심볼 데이터 조회. 실패 시 기본값 반환."""
    try:
        df = fdr.DataReader(symbol)
        if df is None or df.empty:
            raise ValueError("데이터 없음")

        latest     = df.iloc[-1]
        prev       = df.iloc[-2] if len(df) > 1 else latest
        close      = float(latest["Close"])
        prev_close = float(prev["Close"])
        chg        = round((close - prev_close) / prev_close * 100, 2) if prev_close else 0.0

        return {
            "symbol":   symbol,
            "label":    label,
            "category": category,
            "val":      round(close, 4),
            "chg":      chg,
            "up":       chg >= 0,
        }
    except Exception:
        return {
            "symbol":   symbol,
            "label":    label,
            "category": category,
            "val":      0.0,
            "chg":      0.0,
            "up":       False,
        }


def get_market_indices() -> list[dict]:
    """MarketMarquee 전체 데이터 반환"""
    return [_fetch_one(sym, label, cat) for sym, label, cat in MARQUEE_TARGETS]


def get_market_status() -> dict:
    """미국 시장 상태 및 시간 정보 반환"""
    # 1. 시간대 설정
    now_utc = datetime.now(pytz.utc)
    now_ny = now_utc.astimezone(NY_TZ)
    now_time = now_ny.time()
    today = now_ny.date()

    # 2. 결과용 공통 필드 미리 생성
    res = {
        "isOpen": False,
        "session": "CLOSED",
        "etStr": now_ny.strftime("%H:%M"),
        "kstStr": datetime.now(pytz.timezone("Asia/Seoul")).strftime("%H:%M"),
        "currentET": now_ny.strftime("%H:%M:%S"),
        "nextOpen": None
    }

    # 3. 휴장일 체크
    nyse = mcal.get_calendar("NYSE")
    schedule = nyse.schedule(start_date=str(today), end_date=str(today))

    if schedule.empty:
        res["session"] = "CLOSED"
        res["nextOpen"] = _next_open_str(now_ny)
    
    # 4. 개장 상태 판별 (시간별)
    elif MARKET_OPEN <= now_time < MARKET_CLOSE:
        res["isOpen"] = True
        res["session"] = "OPEN"
    elif PRE_MARKET_OPEN <= now_time < MARKET_OPEN:
        res["session"] = "PRE_MARKET"
    elif MARKET_CLOSE <= now_time < AFTER_HOURS_CLOSE:
        res["session"] = "AFTER_HOURS"
    else:
        res["session"] = "CLOSED"
        res["nextOpen"] = _next_open_str(now_ny)

    # 5. [디버그 프린트] 터미널에서 확인용
    # print("\n" + "="*40)
    # print(f" [DEBUG] NY TIME: {res['currentET']} | SESSION: {res['session']}")
    # print("="*40)

    return res


def _next_open_str(now_ny: datetime) -> str:
    """공휴일 포함해서 다음 개장일 계산"""
    nyse = mcal.get_calendar("NYSE")
    next_days = nyse.schedule(
        start_date=str((now_ny + timedelta(days=1)).date()),
        end_date=str((now_ny + timedelta(days=10)).date())  # 최대 10일 앞까지 탐색
    )
    if next_days.empty:
        return "미정"

    next_open_date = next_days.index[0].date()
    return f"{next_open_date} 09:30 ET"