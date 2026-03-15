import FinanceDataReader as fdr
from datetime import datetime, time, timedelta
import pytz
import json
import pandas_market_calendars as mcal


NY_TZ  = pytz.timezone("America/New_York")
KST_TZ = pytz.timezone("Asia/Seoul")

# ── 미국 시장 (NYSE) ──
US_MARKET_OPEN       = time(9, 30)
US_MARKET_CLOSE      = time(16, 0)
US_PRE_MARKET_OPEN   = time(4, 0)
US_AFTER_HOURS_CLOSE = time(20, 0)

# ── 한국 시장 (KRX) ──
KR_MARKET_OPEN       = time(9, 0)
KR_MARKET_CLOSE      = time(15, 30)
KR_PRE_MARKET_OPEN   = time(8, 30)    # 동시호가
KR_AFTER_HOURS_CLOSE = time(18, 0)    # 시간외 단일가


# ──────────────────────────────────────────────────────────
#  MarketMarquee 전체 심볼 정의
# ──────────────────────────────────────────────────────────
MARQUEE_TARGETS = [
    ("S&P500",   "S&P 500",      "US_INDEX"),
    ("IXIC",     "NASDAQ",       "US_INDEX"),
    ("DJI",      "DOW",          "US_INDEX"),
    ("^VIX",     "VIX",          "US_INDEX"),

    ("KS11",     "KOSPI",        "KR_INDEX"),
    ("KQ11",     "KOSDAQ",       "KR_INDEX"),

    ("N225",     "니케이225",     "GLOBAL_INDEX"),
    ("HSI",      "항셍",          "GLOBAL_INDEX"),
    ("000001.SS","상하이",        "GLOBAL_INDEX"),
    ("FTSE",     "FTSE100",      "GLOBAL_INDEX"),
    ("GDAXI",    "DAX",          "GLOBAL_INDEX"),

    ("USD/KRW",  "달러/원",       "FX"),
    ("USD/EUR",  "달러/유로",     "FX"),
    ("USD/CNY",  "달러/위안",     "FX"),
    ("USD/JPY",  "달러/엔",       "FX"),

    ("^NYICDX",  "달러인덱스",    "FX"),

    ("US10YT",   "미국10년채",    "BOND"),
    ("US5YT",    "미국5년채",     "BOND"),
    ("US30YT",   "미국30년채",    "BOND"),

    ("GC=F",     "금",            "COMMODITY"),
    ("SI=F",     "은",            "COMMODITY"),
    ("CL=F",     "WTI유",         "COMMODITY"),
    ("BZ=F",     "브렌트유",      "COMMODITY"),
    ("NG=F",     "천연가스",      "COMMODITY"),
    ("HG=F",     "구리",          "COMMODITY"),

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
    """미국 + 한국 시장 상태 통합 반환"""
    now_utc = datetime.now(pytz.utc)

    # ── 미국 (NYSE) ──
    us = _get_us_status(now_utc)

    # ── 한국 (KRX) ──
    kr = _get_kr_status(now_utc)

    return {
        # 미국 시장
        "isOpen":    us["isOpen"],
        "session":   us["session"],
        "etStr":     us["etStr"],
        "nextOpen":  us["nextOpen"],
        # 한국 시장
        "krIsOpen":  kr["isOpen"],
        "krSession": kr["session"],
        "kstStr":    kr["kstStr"],
        "krNextOpen": kr["nextOpen"],
    }


# ──────────────────────────────────────────────────────────
#  미국 시장 상태 (NYSE)
# ──────────────────────────────────────────────────────────
def _get_us_status(now_utc: datetime) -> dict:
    now_ny   = now_utc.astimezone(NY_TZ)
    now_time = now_ny.time()
    today    = now_ny.date()

    res = {
        "isOpen":   False,
        "session":  "CLOSED",
        "etStr":    now_ny.strftime("%H:%M"),
        "nextOpen": None,
    }

    nyse     = mcal.get_calendar("NYSE")
    schedule = nyse.schedule(start_date=str(today), end_date=str(today))

    if schedule.empty:
        res["nextOpen"] = _next_us_open(now_ny)
    elif US_MARKET_OPEN <= now_time < US_MARKET_CLOSE:
        res["isOpen"]  = True
        res["session"] = "OPEN"
    elif US_PRE_MARKET_OPEN <= now_time < US_MARKET_OPEN:
        res["session"] = "PRE_MARKET"
    elif US_MARKET_CLOSE <= now_time < US_AFTER_HOURS_CLOSE:
        res["session"] = "AFTER_HOURS"
    else:
        res["nextOpen"] = _next_us_open(now_ny)

    return res


def _next_us_open(now_ny: datetime) -> str:
    nyse = mcal.get_calendar("NYSE")
    next_days = nyse.schedule(
        start_date=str((now_ny + timedelta(days=1)).date()),
        end_date=str((now_ny + timedelta(days=10)).date()),
    )
    if next_days.empty:
        return "미정"
    return f"{next_days.index[0].date()} 09:30 ET"


# ──────────────────────────────────────────────────────────
#  한국 시장 상태 (KRX)
# ──────────────────────────────────────────────────────────
def _get_kr_status(now_utc: datetime) -> dict:
    now_kst  = now_utc.astimezone(KST_TZ)
    now_time = now_kst.time()
    today    = now_kst.date()
    dow      = now_kst.weekday()   # 0=Mon … 6=Sun

    res = {
        "isOpen":   False,
        "session":  "CLOSED",
        "kstStr":   now_kst.strftime("%H:%M"),
        "nextOpen": None,
    }

    # 주말 체크
    if dow >= 5:
        res["nextOpen"] = _next_kr_open(now_kst)
        return res

    # 한국 공휴일 체크 (KRX 캘린더)
    try:
        krx = mcal.get_calendar("XKRX")
        schedule = krx.schedule(start_date=str(today), end_date=str(today))
        if schedule.empty:
            res["nextOpen"] = _next_kr_open(now_kst)
            return res
    except Exception:
        # XKRX 캘린더 없으면 주말만 체크하고 넘어감
        pass

    # 시간대별 판별
    if KR_MARKET_OPEN <= now_time < KR_MARKET_CLOSE:
        res["isOpen"]  = True
        res["session"] = "OPEN"
    elif KR_PRE_MARKET_OPEN <= now_time < KR_MARKET_OPEN:
        res["session"] = "PRE_MARKET"
    elif KR_MARKET_CLOSE <= now_time < KR_AFTER_HOURS_CLOSE:
        res["session"] = "AFTER_HOURS"
    else:
        res["nextOpen"] = _next_kr_open(now_kst)

    return res


def _next_kr_open(now_kst: datetime) -> str:
    """다음 한국 개장일 계산"""
    try:
        krx = mcal.get_calendar("XKRX")
        next_days = krx.schedule(
            start_date=str((now_kst + timedelta(days=1)).date()),
            end_date=str((now_kst + timedelta(days=10)).date()),
        )
        if not next_days.empty:
            return f"{next_days.index[0].date()} 09:00 KST"
    except Exception:
        # XKRX 없으면 단순 주말 스킵
        d = now_kst + timedelta(days=1)
        while d.weekday() >= 5:
            d += timedelta(days=1)
        return f"{d.date()} 09:00 KST"
    return "미정"

