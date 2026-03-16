import FinanceDataReader as fdr
from datetime import datetime, time, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import pytz
import json
import pandas_market_calendars as mcal
import threading
import traceback


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
KR_PRE_MARKET_OPEN   = time(8, 30)
KR_AFTER_HOURS_CLOSE = time(18, 0)


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


# ──────────────────────────────────────────────────────────
#  ★ 인메모리 캐시 (서버 블로킹 방지)
# ──────────────────────────────────────────────────────────
_indices_cache: list[dict] = []
_cache_lock = threading.Lock()
_cache_ts: datetime | None = None
CACHE_TTL_SECONDS = 120          # 2분 캐시

_is_fetching = threading.Event()  # 중복 fetch 방지


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


def _refresh_cache_background():
    """백그라운드 스레드에서 28개 심볼을 병렬로 가져와 캐시 갱신"""
    global _indices_cache, _cache_ts

    if _is_fetching.is_set():
        return                       # 이미 다른 스레드가 가져오는 중
    _is_fetching.set()

    try:
        results = []
        # ★ 핵심: ThreadPoolExecutor로 병렬 호출 (28개 → 약 10~15초)
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {
                executor.submit(_fetch_one, sym, label, cat): (sym, label, cat)
                for sym, label, cat in MARQUEE_TARGETS
            }
            for future in as_completed(futures, timeout=30):
                try:
                    results.append(future.result())
                except Exception:
                    sym, label, cat = futures[future]
                    results.append({
                        "symbol": sym, "label": label, "category": cat,
                        "val": 0.0, "chg": 0.0, "up": False,
                    })

        # 원래 순서 유지
        order = {sym: i for i, (sym, _, _) in enumerate(MARQUEE_TARGETS)}
        results.sort(key=lambda x: order.get(x["symbol"], 999))

        with _cache_lock:
            _indices_cache = results
            _cache_ts = datetime.now()
            print(f"[MarketIndices] 캐시 갱신 완료 — {len(results)}개 심볼")

    except Exception as e:
        print(f"[MarketIndices] 캐시 갱신 실패: {e}")
        traceback.print_exc()
    finally:
        _is_fetching.clear()


def get_market_indices() -> list[dict]:
    """
    ★ 즉시 응답: 캐시가 있으면 즉시 반환, 없거나 만료면 백그라운드 갱신 후 반환
    - 첫 호출: 빈 배열 반환 + 백그라운드 갱신 시작 (프론트가 곧 재호출)
    - 이후: 캐시 즉시 반환 (2분마다 백그라운드 갱신)
    """
    global _cache_ts

    now = datetime.now()
    cache_valid = (
        _cache_ts is not None
        and (now - _cache_ts).total_seconds() < CACHE_TTL_SECONDS
        and len(_indices_cache) > 0
    )

    if cache_valid:
        return _indices_cache

    # 캐시 없거나 만료 → 백그라운드 갱신 트리거
    thread = threading.Thread(target=_refresh_cache_background, daemon=True)
    thread.start()

    # 기존 캐시가 있으면 stale이라도 반환 (UX 우선)
    if _indices_cache:
        return _indices_cache

    # 최초 호출 — 캐시 완전 비어있음 → 빈 배열 반환
    # 프론트엔드가 곧 재호출하면 그때는 캐시 있음
    return []


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
#  미국 시장 상태
# ──────────────────────────────────────────────────────────
def _get_us_status(now_utc: datetime) -> dict:
    now_et  = now_utc.astimezone(NY_TZ)
    t       = now_et.time()
    today   = now_et.date()
    weekday = now_et.weekday()

    # NYSE 캘린더
    nyse = mcal.get_calendar("NYSE")
    sched = nyse.schedule(
        start_date=(today - timedelta(days=7)).isoformat(),
        end_date=(today + timedelta(days=14)).isoformat(),
    )

    is_trading_day = today.isoformat() in sched.index.strftime("%Y-%m-%d").tolist()

    if is_trading_day:
        if US_MARKET_OPEN <= t < US_MARKET_CLOSE:
            session = "정규장"
            is_open = True
        elif US_PRE_MARKET_OPEN <= t < US_MARKET_OPEN:
            session = "프리마켓"
            is_open = True
        elif US_MARKET_CLOSE <= t < US_AFTER_HOURS_CLOSE:
            session = "애프터마켓"
            is_open = True
        else:
            session = "장 마감"
            is_open = False
    else:
        if weekday >= 5:
            session = "주말 휴장"
        else:
            session = "공휴일 휴장"
        is_open = False

    # 다음 개장일
    future_days = sched[sched.index > str(today)]
    next_open = (
        future_days.index[0].strftime("%Y-%m-%d")
        if len(future_days) > 0
        else "N/A"
    )

    return {
        "isOpen":   is_open,
        "session":  session,
        "etStr":    now_et.strftime("%Y-%m-%d %H:%M ET"),
        "nextOpen": next_open,
    }


# ──────────────────────────────────────────────────────────
#  한국 시장 상태
# ──────────────────────────────────────────────────────────
def _get_kr_status(now_utc: datetime) -> dict:
    now_kst = now_utc.astimezone(KST_TZ)
    t       = now_kst.time()
    today   = now_kst.date()
    weekday = now_kst.weekday()

    try:
        xkrx = mcal.get_calendar("XKRX")
        sched = xkrx.schedule(
            start_date=(today - timedelta(days=7)).isoformat(),
            end_date=(today + timedelta(days=14)).isoformat(),
        )
        is_trading_day = today.isoformat() in sched.index.strftime("%Y-%m-%d").tolist()
    except Exception:
        is_trading_day = weekday < 5

    if is_trading_day:
        if KR_MARKET_OPEN <= t < KR_MARKET_CLOSE:
            session = "정규장"
            is_open = True
        elif KR_PRE_MARKET_OPEN <= t < KR_MARKET_OPEN:
            session = "동시호가"
            is_open = True
        elif KR_MARKET_CLOSE <= t < KR_AFTER_HOURS_CLOSE:
            session = "시간외"
            is_open = True
        else:
            session = "장 마감"
            is_open = False
    else:
        if weekday >= 5:
            session = "주말 휴장"
        else:
            session = "공휴일 휴장"
        is_open = False

    try:
        future_days = sched[sched.index > str(today)]
        next_open = (
            future_days.index[0].strftime("%Y-%m-%d")
            if len(future_days) > 0
            else "N/A"
        )
    except Exception:
        next_open = "N/A"

    return {
        "isOpen":   is_open,
        "session":  session,
        "kstStr":   now_kst.strftime("%Y-%m-%d %H:%M KST"),
        "nextOpen": next_open,
    }