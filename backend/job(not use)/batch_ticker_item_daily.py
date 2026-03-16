"""
========================================================
batch_ticker_item_daily.py  (v3 — 2025 개선판)
========================================================
[변경 이력]
  v3: 5개 이슈 전면 수정
    1. ticker_item per/pbr/eps/roa/roe/roic/roi 미입력 → SEC 추출 로직 강화
    2. forward_per → EPS 3년 CAGR 기반 추정치로 자체 계산
    3. tech_score / total_score → stock_quant_analysis 저장
    4. quant_rank / final_grade → ai_final_rating 배치 말미에 일괄 계산·저장
    5. numeric field overflow → 모든 비율·점수 clamp 처리

[데이터 소스]
  - OHLCV          → FinanceDataReader  (IP 차단 없음)
  - 기술 지표      → FinanceDataReader  (2년치 히스토리)
  - 재무제표 전체  → SEC EDGAR XBRL API (공식 무료 REST API)
  - 시가총액       → FDR 최신 종가 × SEC 발행주식수
  - yfinance       → 완전 제거

[필요 라이브러리 — 추가 설치 없음]
  requests / pandas / numpy / scipy / psycopg2 / FinanceDataReader
========================================================
"""

import os
import sys
import time
import traceback
import psycopg2
import requests
import numpy as np
import pandas as pd
import FinanceDataReader as fdr

from scipy import stats
from datetime import datetime, timedelta
from psycopg2.extras import execute_values

# ─────────────────────────────────────────────────────
# DB 설정 — 환경변수에서 읽기 (Cloud Run Job 환경변수 주입)
# 로컬 테스트 시: export DB_HOST=... 또는 .env 파일 사용
# ─────────────────────────────────────────────────────
DB_HOST = os.environ.get("DB_HOST", "")
DB_NAME = os.environ.get("DB_NAME", "")
DB_USER = os.environ.get("DB_USER", "")
DB_PASS = os.environ.get("DB_PASS", "")


# ════════════════════════════════════════════════════
# 0. 공통 유틸
# ════════════════════════════════════════════════════
def safe_float(v, default=0.0):
    """None / NaN / Inf → default"""
    try:
        if v is None:
            return default
        f = float(v)
        return default if (np.isnan(f) or np.isinf(f)) else f
    except (TypeError, ValueError):
        return default


def safe_div(a, b, default=0.0):
    try:
        fb = safe_float(b)
        return safe_float(a) / fb if fb != 0 else default
    except Exception:
        return default


# ── [FIX 5] Numeric Overflow 방지 ───────────────────
# precision 10, scale 4  →  정수부 최대 6자리 (999999.9999)
# 비율·배수 지표는 최대 ±9999, 점수류는 0~100 으로 clamp
_RATIO_MAX   =  9999.0
_RATIO_MIN   = -9999.0
_SCORE_MAX   =   100.0
_SCORE_MIN   =     0.0
_PERCENT_MAX =   999.0   # ROA/ROE 등 % 단위


def clamp_ratio(v: float, lo=_RATIO_MIN, hi=_RATIO_MAX) -> float:
    """비율/배수 지표를 DB numeric 허용 범위로 제한"""
    return max(lo, min(hi, safe_float(v, 0.0)))


def clamp_score(v: float) -> float:
    """점수(0~100)를 DB numeric 허용 범위로 제한"""
    return max(_SCORE_MIN, min(_SCORE_MAX, safe_float(v, 0.0)))


def clamp_pct(v: float) -> float:
    """퍼센트 비율(ROA, ROE 등)을 ±999% 로 제한"""
    return max(-_PERCENT_MAX, min(_PERCENT_MAX, safe_float(v, 0.0)))


# ════════════════════════════════════════════════════
# 1. DB 연결
# ════════════════════════════════════════════════════
def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        connect_timeout=10,
    )


# ════════════════════════════════════════════════════
# 2. SEC EDGAR 클라이언트
# ════════════════════════════════════════════════════
SEC_HEADERS = {
    "User-Agent": "QuantBatch gguakim22@gmail.com",   # SEC 정책 필수
    "Accept":     "application/json",
}
SEC_FACTS_URL   = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

_cik_cache: dict = {}   # { "AAPL": "0000320193", ... }


def load_cik_map() -> dict:
    global _cik_cache
    if _cik_cache:
        return _cik_cache
    try:
        resp = requests.get(SEC_TICKERS_URL, headers=SEC_HEADERS, timeout=20)
        resp.raise_for_status()
        for entry in resp.json().values():
            t = str(entry["ticker"]).upper()
            c = str(entry["cik_str"]).zfill(10)
            _cik_cache[t] = c
        # print(f"  ✅ SEC CIK 맵 로드: {len(_cik_cache):,}개")
    except Exception as e:
        print(f"  🚨 SEC CIK 맵 실패: {e}")
    return _cik_cache


def get_cik(ticker: str):
    return _cik_cache.get(ticker.upper())


# ── SEC XBRL 태그 우선순위 맵 ─────────────────────
_SEC_TAG_MAP = {
    "total_assets":   ["Assets"],
    "current_assets": ["AssetsCurrent"],
    "total_equity":   [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        "CommonStockholdersEquity",
    ],
    "long_term_debt": ["LongTermDebt", "LongTermDebtNoncurrent"],
    "total_debt":     [
        "DebtAndCapitalLeaseObligations",
        "LongTermDebtAndCapitalLeaseObligations",
        "LongTermDebt",
    ],
    "current_liab":   ["LiabilitiesCurrent"],
    "cash":           [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashAndCashEquivalents",
        "CashCashEquivalentsAndShortTermInvestments",
    ],
    "revenue":        [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
    ],
    "gross_profit":   ["GrossProfit"],
    "op_income":      ["OperatingIncomeLoss"],
    "net_income":     [
        "NetIncomeLoss",
        "NetIncomeLossAvailableToCommonStockholdersBasic",
    ],
    "tax_provision":  ["IncomeTaxExpenseBenefit"],
    "pretax_income":  [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    ],
    "op_cf":          ["NetCashProvidedByUsedInOperatingActivities"],
    "cap_ex":         [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "CapitalExpendituresIncurringObligation",
    ],
    # ── EPS: USD 단위 (달러/주) ─────────────────────
    "eps":            ["EarningsPerShareBasic", "EarningsPerShareDiluted"],
    # ── 발행주식수: shares 단위 ──────────────────────
    "shares":         ["CommonStockSharesOutstanding", "CommonStockSharesIssued"],
}


def _extract_annual_vals(ugaap: dict, tags: list, n: int = 3) -> list:
    """
    우선순위 태그를 순서대로 시도 → 10-K/20-F 기준 최신 n개 [최신, 전기, 전전기] 반환.
    없으면 [0.0] * n.
    """
    for tag in tags:
        tag_data = ugaap.get(tag, {})
        units    = tag_data.get("units", {})

        # USD 우선, 없으면 shares 단위 시도
        usd_list = units.get("USD") or units.get("shares") or []
        if not usd_list:
            continue

        # 연간 보고서만 필터
        annual = [
            e for e in usd_list
            if e.get("form") in ("10-K", "20-F")
            and e.get("end")
            and e.get("val") is not None
        ]
        if not annual:
            continue

        # 동일 end 날짜 중 가장 최근 filed 건만 유지
        seen: dict = {}
        for e in annual:
            ed = e["end"]
            if ed not in seen or e.get("filed", "") > seen[ed].get("filed", ""):
                seen[ed] = e

        sorted_vals = sorted(seen.values(), key=lambda x: x["end"], reverse=True)
        result = [safe_float(e["val"]) for e in sorted_vals[:n]]
        while len(result) < n:
            result.append(0.0)
        return result   # [최신, 전기, 전전기]

    return [0.0] * n


def _extract_latest_shares(ugaap: dict) -> float:
    """
    발행주식수: 10-K 외에도 최신 분기 보고서(10-Q)까지 포함해
    가장 최근 filed 값을 사용 (연간보다 더 최신 반영).
    """
    for tag in _SEC_TAG_MAP["shares"]:
        tag_data = ugaap.get(tag, {})
        usd_list = tag_data.get("units", {}).get("shares", [])
        if not usd_list:
            continue

        # 모든 form 허용, filed 기준 최신
        valid = [e for e in usd_list if e.get("filed") and e.get("val") is not None]
        if not valid:
            continue

        latest = max(valid, key=lambda x: x["filed"])
        v = safe_float(latest["val"])
        if v > 1_000:   # 의미 있는 주식수인지 확인
            return v
    return 0.0


# ════════════════════════════════════════════════════
# 3. SEC 재무 데이터 추출 (완전 개선)
# ════════════════════════════════════════════════════
def fetch_financial_sec(ticker: str) -> dict:
    """
    [FIX 1] SEC EDGAR XBRL API로 재무제표 추출.
            per/pbr/eps/roa/roe/roic/roi 모두 여기서 계산.
    [FIX 2] forward_per = 현재가 ÷ (EPS × (1 + EPS_CAGR_3y), 보수적 처리)
    """
    _zero = {
        "ticker": ticker,
        "total_assets": 0,    "total_assets_prev": 0,
        "total_equity": 0,    "total_debt": 0,        "cash": 0,
        "revenue": 0,         "revenue_prev": 0,
        "gross_profit": 0,    "gross_profit_prev": 0,
        "op_income": 0,       "op_income_prev": 0,
        "net_income": 0,      "net_income_prev": 0,
        "ebit": 0,            "tax_provision": 0,     "pretax_income": 0,
        "op_cf": 0,           "cap_ex": 0,
        "market_cap": 0,      "current_per": 999.0,
        "long_term_debt": 0,  "long_term_debt_prev": 0,
        "current_assets": 0,  "current_assets_prev": 0,
        "current_liab": 0,    "current_liab_prev": 0,
        # ticker_item 파생 지표
        "eps": 0.0, "eps_prev": 0.0, "eps_2prev": 0.0,
        "per": 0.0, "forward_per": 0.0,
        "pbr": 0.0, "roa": 0.0, "roe": 0.0, "roic": 0.0, "roi": 0.0,
        "shares": 0.0, "last_price": 0.0,
    }

    # ── CIK 조회 ─────────────────────────────────────
    cik = get_cik(ticker)
    if not cik:
        print(f"         ⚠️  CIK 없음 [{ticker}]")
        return _zero

    # ── Company Facts 호출 ───────────────────────────
    url = SEC_FACTS_URL.format(cik=cik)
    try:
        resp = requests.get(url, headers=SEC_HEADERS, timeout=25)
        if resp.status_code == 404:
            print(f"         ⚠️  SEC 404 [{ticker}]")
            return _zero
        resp.raise_for_status()
        ugaap = resp.json().get("facts", {}).get("us-gaap", {})
    except Exception as e:
        print(f"         ⚠️  SEC 요청 실패 [{ticker}]: {e}")
        return _zero

    # ── 연간값 추출 헬퍼 (3년치) ─────────────────────
    def gv(field: str, idx: int = 0) -> float:
        tags = _SEC_TAG_MAP.get(field, [])
        return _extract_annual_vals(ugaap, tags, n=3)[idx]

    # ── 재무제표 원천값 ───────────────────────────────
    total_assets      = gv("total_assets",   0)
    total_assets_prev = gv("total_assets",   1)
    total_equity      = gv("total_equity",   0)
    total_debt        = gv("total_debt",     0)
    long_term_debt    = gv("long_term_debt", 0)
    long_term_debt_p  = gv("long_term_debt", 1)
    cash              = gv("cash",           0)
    current_assets    = gv("current_assets", 0)
    current_assets_p  = gv("current_assets", 1)
    current_liab      = gv("current_liab",   0)
    current_liab_p    = gv("current_liab",   1)
    revenue           = gv("revenue",        0)
    revenue_prev      = gv("revenue",        1)
    gross_profit      = gv("gross_profit",   0)
    gross_profit_prev = gv("gross_profit",   1)
    op_income         = gv("op_income",      0)
    op_income_prev    = gv("op_income",      1)
    net_income        = gv("net_income",     0)
    net_income_prev   = gv("net_income",     1)
    ebit              = gv("op_income",      0)   # EBIT ≈ Operating Income
    tax_provision     = gv("tax_provision",  0)
    pretax_income     = gv("pretax_income",  0)
    op_cf             = gv("op_cf",          0)
    cap_ex            = abs(gv("cap_ex",     0))

    # EPS 3년치
    eps_cur   = gv("eps", 0)
    eps_prev  = gv("eps", 1)
    eps_2prev = gv("eps", 2)

    # 발행주식수 (최신 분기 우선)
    shares = _extract_latest_shares(ugaap)

    # total_debt 없으면 long_term_debt 으로 근사
    if total_debt == 0:
        total_debt = long_term_debt

    # ── 현재 종가 (FDR) ──────────────────────────────
    last_price = 0.0
    market_cap = 0.0
    try:
        today   = datetime.now().strftime("%Y-%m-%d")
        start_p = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
        pdf     = fdr.DataReader(ticker, start_p, today)
        if not pdf.empty:
            last_price = safe_float(pdf["Close"].dropna().iloc[-1])
    except Exception:
        pass

    if shares > 0 and last_price > 0:
        market_cap = shares * last_price

    # ── [FIX 1] EPS: SEC 직접값 우선, fallback = 순이익÷주식수 ─
    eps = eps_cur if eps_cur != 0 else safe_div(net_income, shares)

    # ── [FIX 1] PER ──────────────────────────────────
    per = clamp_ratio(safe_div(last_price, eps)) if eps != 0 else 0.0

    # ── [FIX 2] Forward PER: EPS 3년 CAGR 기반 추정 ─
    #   1) 3년 CAGR 계산 (eps_2prev → eps_cur, 2기간)
    #   2) ±20% 로 캡 (보수적)
    #   3) forward_eps = eps_cur × (1 + clipped_growth)
    #   4) forward_per = 현재가 ÷ forward_eps
    forward_per = 0.0
    if eps != 0:
        if eps_2prev != 0:
            # 2기간 CAGR: (eps_cur/eps_2prev)^(1/2) - 1
            ratio = safe_div(eps_cur, abs(eps_2prev), 1.0)
            cagr  = (max(ratio, 0.0) ** 0.5) - 1.0  # 음수 비율 방지
            if eps_2prev < 0:
                cagr = -cagr  # 방향성 보정
        elif eps_prev != 0:
            # 1기간 성장률
            cagr = safe_div(eps_cur - eps_prev, abs(eps_prev))
        else:
            cagr = 0.0

        # ±20% 보수적 캡
        clipped = max(-0.20, min(cagr, 0.20))
        forward_eps = eps * (1 + clipped)
        if forward_eps != 0:
            forward_per = clamp_ratio(safe_div(last_price, forward_eps))

    # ── [FIX 1] PBR ──────────────────────────────────
    bps = safe_div(total_equity, shares)
    pbr = clamp_ratio(safe_div(last_price, bps)) if bps != 0 else 0.0

    # ── [FIX 1] ROA / ROE (% 단위로 저장) ────────────
    roa = clamp_pct(safe_div(net_income, total_assets) * 100)
    roe = clamp_pct(safe_div(net_income, total_equity) * 100)

    # ── [FIX 1] ROIC ─────────────────────────────────
    tax_rate = max(0.0, min(safe_div(tax_provision, pretax_income, 0.21), 0.40))
    nopat    = op_income * (1 - tax_rate)
    ic       = max(total_debt + total_equity - cash, 1)
    roic     = clamp_pct(safe_div(nopat, ic) * 100)

    # ── [FIX 1] ROI = 순이익 ÷ (자기자본 + 총부채) ───
    roi = clamp_pct(safe_div(net_income, max(total_equity + total_debt, 1)) * 100)

    current_per = safe_div(market_cap, net_income, 999.0)

    return {
        "ticker":              ticker,
        "total_assets":        total_assets,
        "total_assets_prev":   total_assets_prev,
        "total_equity":        total_equity,
        "total_debt":          total_debt,
        "cash":                cash,
        "revenue":             revenue,
        "revenue_prev":        revenue_prev,
        "gross_profit":        gross_profit,
        "gross_profit_prev":   gross_profit_prev,
        "op_income":           op_income,
        "op_income_prev":      op_income_prev,
        "net_income":          net_income,
        "net_income_prev":     net_income_prev,
        "ebit":                ebit,
        "tax_provision":       tax_provision,
        "pretax_income":       pretax_income,
        "op_cf":               op_cf,
        "cap_ex":              cap_ex,
        "market_cap":          market_cap,
        "current_per":         current_per,
        "long_term_debt":      long_term_debt,
        "long_term_debt_prev": long_term_debt_p,
        "current_assets":      current_assets,
        "current_assets_prev": current_assets_p,
        "current_liab":        current_liab,
        "current_liab_prev":   current_liab_p,
        # ticker_item 파생 지표 (모두 clamp 완료)
        "eps":         round(safe_float(eps),         4),
        "eps_prev":    round(safe_float(eps_prev),    4),
        "eps_2prev":   round(safe_float(eps_2prev),   4),
        "per":         round(per,                     4),
        "forward_per": round(forward_per,             4),
        "pbr":         round(pbr,                     4),
        "roa":         round(roa,                     4),
        "roe":         round(roe,                     4),
        "roic":        round(roic,                    4),
        "roi":         round(roi,                     4),
        "shares":      shares,
        "last_price":  last_price,
    }


# ════════════════════════════════════════════════════
# 4. 영업일 계산
# ════════════════════════════════════════════════════
def get_last_business_day():
    """
    배치 실행 기준: 화~토 09시 KST 실행, 항상 전날 장 데이터 처리.
    - 화(1) 09시 실행 → 월(0) 데이터
    - 수(2) 09시 실행 → 화(1) 데이터
    - 목(3) 09시 실행 → 수(2) 데이터
    - 금(4) 09시 실행 → 목(3) 데이터
    - 토(5) 09시 실행 → 금(4) 데이터  ← 주말 전 마감 데이터
    스케줄대로 실행되면 항상 today - 1일이 정답.
    """
    return datetime.now().date() - timedelta(days=1)


# ════════════════════════════════════════════════════
# 5. FDR: OHLCV
# ════════════════════════════════════════════════════
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

_fdr_executor = ThreadPoolExecutor(max_workers=1)

def _fdr_read(ticker: str, start: str, end: str, timeout: int = 30) -> pd.DataFrame:
    """fdr.DataReader에 타임아웃을 적용한 래퍼. 초과 시 빈 DataFrame 반환."""
    future = _fdr_executor.submit(fdr.DataReader, ticker, start, end)
    try:
        return future.result(timeout=timeout)
    except FuturesTimeoutError:
        print(f"         ⚠️  FDR 타임아웃 [{ticker}] ({timeout}s 초과)")
        return pd.DataFrame()


def fetch_ohlcv_fdr(ticker: str, target_date) -> pd.DataFrame:
    """
    target_date 당일 OHLCV 1행만 반환.
    공휴일 등 데이터 공백 대비 최대 5일 전부터 조회 후 target_date 행만 필터링.
    반환: 해당 날짜 1행 DataFrame 또는 빈 DataFrame
    """
    try:
        start = (target_date - timedelta(days=5)).strftime("%Y-%m-%d")
        end   = target_date.strftime("%Y-%m-%d")
        df    = _fdr_read(ticker, start, end, timeout=30)
        if df.empty:
            return pd.DataFrame()
        df.index = pd.to_datetime(df.index).date
        if target_date in df.index:
            return df.loc[[target_date]]
        return df.tail(1)
    except Exception as e:
        print(f"         ⚠️  FDR OHLCV [{ticker}]: {e}")
        return pd.DataFrame()


def fetch_ohlcv_fdr_history(ticker: str, years: int = 2) -> pd.DataFrame:
    try:
        end   = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=years * 365)).strftime("%Y-%m-%d")
        df    = _fdr_read(ticker, start, end, timeout=60)
        if df.empty:
            return pd.DataFrame()
        df.index = pd.to_datetime(df.index)
        return df
    except Exception as e:
        print(f"         ⚠️  FDR History [{ticker}]: {e}")
        return pd.DataFrame()


# SPY 히스토리 전역 캐시 — 배치 시작 시 1회만 호출, 전 티커 공유
_spy_history_cache: pd.DataFrame = pd.DataFrame()


def get_spy_history() -> pd.DataFrame:
    """SPY 2년치 히스토리를 최초 1회만 로드해 캐시 반환."""
    global _spy_history_cache
    if not _spy_history_cache.empty:
        return _spy_history_cache
    _spy_history_cache = fetch_ohlcv_fdr_history("SPY", years=2)
    # print(f"  ✅ SPY 히스토리 캐시 완료: {len(_spy_history_cache)}행")
    return _spy_history_cache


# ════════════════════════════════════════════════════
# 5. 기술적 타이밍 지표 (FDR 기반)
# ════════════════════════════════════════════════════
def get_technical_timing_fdr(ticker: str, market_ticker: str = "SPY") -> dict:
    """
    [FIX 3] scores.total 포함 전체 반환값을 stock_quant_analysis 에 저장.
    """
    default = {
        "relativeMomentumPct": 0, "position52W": 0, "dist52W": 0,
        "trendR2": 0, "annualVol": 0, "volComp": 0,
        "scores": {
            "relativeMomentum": 0, "highDistance": 0,
            "trendStability": 0,   "volCompression": 0,
            "total": 0,
        },
    }
    try:
        stock_df  = fetch_ohlcv_fdr_history(ticker, years=2)
        market_df = get_spy_history()   # 캐시 사용 — API 호출 없음

        if stock_df.empty or market_df.empty or len(stock_df) < 120:
            return default

        close   = stock_df["Close"].dropna()
        mkt_c   = market_df["Close"].dropna()
        returns = close.pct_change()

        # 1. Relative 12M Momentum (45pt)
        lb  = min(252, len(close))
        lbm = min(252, len(mkt_c))
        ret_s   = (close.iloc[-1] / close.iloc[-lb]   - 1) if lb  > 1 else 0
        ret_m   = (mkt_c.iloc[-1]  / mkt_c.iloc[-lbm] - 1) if lbm > 1 else 0
        rel_mom = ret_s - ret_m
        s_rel   = (45 if rel_mom >= 0.3 else 35 if rel_mom >= 0.2 else
                   25 if rel_mom >= 0.1 else 10 if rel_mom >= 0   else 0)

        # 2. 52W High Position (25pt)
        high_52 = close.tail(252).max()
        pos_52  = safe_div(close.iloc[-1], high_52)
        dist_52 = pos_52 - 1.0
        s_pos   = (25 if pos_52 >= 0.95 else 20 if pos_52 >= 0.85 else
                   15 if pos_52 >= 0.70 else  5 if pos_52 >= 0.55 else 0)

        # 3. Trend R² 90D (20pt)
        trend_r2 = 0.0
        s_trend  = 0
        y_data   = close.tail(90).values
        if len(y_data) >= 90:
            x_data             = np.arange(len(y_data))
            slope, _, rv, _, _ = stats.linregress(x_data, y_data)
            trend_r2           = rv ** 2
            if   slope > 0 and trend_r2 >= 0.7: s_trend = 20
            elif slope > 0 and trend_r2 >= 0.4: s_trend = 10

        # 4. Annualized Volatility (10pt)
        ann_vol  = safe_float(returns.tail(252).std() * np.sqrt(252))
        vol_comp = safe_float(safe_div(returns.tail(20).std(),
                                       returns.tail(120).std(), 1.0))
        s_vol = (10 if ann_vol <= 0.20 else  8 if ann_vol <= 0.30 else
                  5 if ann_vol <= 0.40 else  2 if ann_vol <= 0.60 else 0)

        total_tech = s_rel + s_pos + s_trend + s_vol

        return {
            "relativeMomentumPct": round(rel_mom * 100, 4),
            "position52W":         round(pos_52  * 100, 4),
            "dist52W":             round(dist_52  * 100, 4),
            "trendR2":             round(float(trend_r2), 4),
            "annualVol":           round(ann_vol  * 100, 4),
            "volComp":             round(float(vol_comp), 4),
            "scores": {
                "relativeMomentum": s_rel,
                "highDistance":     s_pos,
                "trendStability":   s_trend,
                "volCompression":   s_vol,
                "total":            total_tech,
            },
        }
    except Exception as e:
        print(f"         ⚠️  Tech [{ticker}]: {e}")
        return default


# ════════════════════════════════════════════════════
# 6. F-Score (Piotroski 9점)
# ════════════════════════════════════════════════════
def calc_f_score(d: dict) -> int:
    score = 0
    try:
        ni   = safe_float(d.get("net_income"))
        ni_p = safe_float(d.get("net_income_prev"))
        ocf  = safe_float(d.get("op_cf"))
        ta   = max(safe_float(d.get("total_assets")),      1)
        ta_p = max(safe_float(d.get("total_assets_prev")), 1)

        if ni  > 0:                           score += 1
        if ocf > 0:                           score += 1
        if ni / ta > ni_p / ta_p:             score += 1
        if ocf > ni:                          score += 1

        ltd   = safe_float(d.get("long_term_debt"))
        ltd_p = safe_float(d.get("long_term_debt_prev"))
        if safe_div(ltd, ta) < safe_div(ltd_p, ta_p): score += 1

        ca    = safe_float(d.get("current_assets"))
        cl    = max(safe_float(d.get("current_liab")),      1)
        ca_p  = safe_float(d.get("current_assets_prev"))
        cl_p  = max(safe_float(d.get("current_liab_prev")), 1)
        if ca / cl > ca_p / cl_p: score += 1

        score += 1  # 주식발행 (간소화)

        gp    = safe_float(d.get("gross_profit"))
        gp_p  = safe_float(d.get("gross_profit_prev"))
        rev   = max(safe_float(d.get("revenue")),      1)
        rev_p = max(safe_float(d.get("revenue_prev")), 1)
        if gp / rev > gp_p / rev_p:                         score += 1
        if safe_div(rev, ta) > safe_div(rev_p, ta_p):       score += 1
    except Exception:
        pass
    return score


# ════════════════════════════════════════════════════
# 7. 퀀트 점수 계산 (완전 인라인)
# ════════════════════════════════════════════════════
def calc_quant_scores(d: dict, tech: dict) -> dict:
    """
    [FIX 3] tech_score / total_score 포함.
    [FIX 5] 모든 비율값 clamp 처리.
    반환: stock_quant_analysis 저장에 바로 사용.
    """
    result = {
        "gpa": 0.0,  "roic": 0.0,  "accruals": 0.0,
        "ev_ebit": 0.0, "peg": 0.0, "pfcr": 0.0,
        "f_score": 0,
        "ato_accel": 0.0, "op_lev": 0.0,
        "rel_mom": 0.0, "dist_high": 0.0, "trend_r2": 0.0, "vol_comp": 0.0,
        "moat_score":   0.0,
        "value_score":  0.0,
        "growth_score": 0.0,
        "tech_score":        0.0,   # [FIX 3]
        "total_quant_score": 0.0,   # [FIX 3]
    }
    try:
        ta    = max(safe_float(d.get("total_assets")),   1)
        gp    = safe_float(d.get("gross_profit"))
        op_i  = safe_float(d.get("op_income"))
        ni    = safe_float(d.get("net_income"))
        ni_p  = safe_float(d.get("net_income_prev"))
        ocf   = safe_float(d.get("op_cf"))
        cap   = safe_float(d.get("cap_ex"))
        eq    = safe_float(d.get("total_equity"))
        debt  = safe_float(d.get("total_debt"))
        cash  = safe_float(d.get("cash"))
        ebit  = safe_float(d.get("ebit")) or op_i
        mcap  = safe_float(d.get("market_cap"))
        rev   = safe_float(d.get("revenue"))
        rev_p = safe_float(d.get("revenue_prev"))
        ta_p  = max(safe_float(d.get("total_assets_prev")), 1)
        op_p  = safe_float(d.get("op_income_prev"))
        tax_p = safe_float(d.get("tax_provision"))
        pre_i = safe_float(d.get("pretax_income"))
        fcf   = ocf - abs(cap)

        # ── MOAT (35pt) ───────────────────────────────
        gpa      = safe_div(gp, ta)
        tax_rate = max(0.0, min(safe_div(tax_p, pre_i, 0.21), 0.40))
        nopat    = op_i * (1 - tax_rate)
        ic       = max(debt + eq - cash, 1.0)
        roic_q   = safe_div(nopat, ic)    # 쿼리용 소수 (not %)
        accruals = safe_div(ni - ocf, ta)

        s_gpa  = (45 if gpa >= 0.4  else 35 if gpa >= 0.3  else
                  25 if gpa >= 0.2  else 15 if gpa >= 0.1  else 0)
        s_roic = (35 if roic_q >= 0.20 else 30 if roic_q >= 0.15 else
                  20 if roic_q >= 0.12 else 10 if roic_q >= 0.08 else 0)
        s_acc  = (20 if accruals <= -0.05 else 15 if accruals <= 0    else
                  10 if accruals <=  0.05 else  5 if accruals <= 0.10 else 0)
        moat_score = clamp_score(((s_gpa + s_roic + s_acc) / 100) * 35)

        # ── VALUE (25pt) ──────────────────────────────
        growth  = safe_div(ni - ni_p, max(abs(ni_p), 1)) * 100
        per_v   = safe_div(mcap, ni, 999.0)
        peg     = safe_div(per_v, growth, 5.0) if (growth > 0 and per_v > 0) else 5.0
        ev      = mcap + debt - cash
        ev_ebit = safe_div(ev, ebit, 999.0) if ebit > 0 else 999.0
        pfcr    = safe_div(mcap, fcf, 999.0) if fcf   > 0 else 999.0

        # [FIX 5] 오버플로우 방지 clamp
        peg     = clamp_ratio(peg)
        ev_ebit = clamp_ratio(ev_ebit)
        pfcr    = clamp_ratio(pfcr)

        s_ev   = (50 if ev_ebit <= 10 else 40 if ev_ebit <= 15 else
                  30 if ev_ebit <= 20 else 15 if ev_ebit <= 25 else 0)
        s_peg  = (30 if peg <= 0.8 else 25 if peg <= 1.2 else
                  15 if peg <= 1.8 else  5 if peg <= 2.5 else 0)
        s_pfcr = (20 if pfcr <= 10 else 15 if pfcr <= 15 else
                  10 if pfcr <= 20 else  5 if pfcr <= 30 else 0)
        value_score = clamp_score(((s_ev + s_peg + s_pfcr) / 100) * 25)

        # ── MOMENTUM/GROWTH (25pt) ─────────────────────
        f_score   = calc_f_score(d)
        curr_ato  = safe_div(rev,   ta)
        prev_ato  = safe_div(rev_p, ta_p)
        ato_accel = curr_ato - prev_ato
        rev_g     = safe_div(rev - rev_p, max(abs(rev_p), 1))
        op_g      = safe_div(op_i - op_p, max(abs(op_p),  1))
        op_lev    = safe_div(op_g, rev_g, 1.0) if abs(rev_g) > 0.0001 else 1.0
        op_lev    = clamp_ratio(op_lev, -999.0, 999.0)  # [FIX 5]

        s_f   = (55 if f_score >= 9 else 45 if f_score >= 7 else
                 30 if f_score >= 5 else 15 if f_score >= 3 else 0)
        s_ato = (25 if ato_accel >= 0.05 else 20 if ato_accel >= 0.02 else
                 15 if ato_accel >= 0    else  5 if ato_accel >= -0.02 else 0)
        s_ol  = (20 if op_lev >= 0.25 else 15 if op_lev >= 0.15 else
                 10 if op_lev >= 0.05 else  5 if op_lev >= 0    else 0)
        growth_score = clamp_score(((s_f + s_ato + s_ol) / 100) * 25)

        # ── 기술 지표 ─────────────────────────────────
        tech_s    = tech.get("scores", {})
        tech_raw  = safe_float(tech_s.get("total", 0))        # 0~100
        tech_score= clamp_score(tech_raw * 0.15)               # 15점 가중 (max 15)

        rel_mom   = clamp_ratio(safe_float(tech.get("relativeMomentumPct", 0)) / 100,
                                -9.9, 9.9)
        dist_high = clamp_ratio(safe_float(tech.get("dist52W", 0)) / 100, -9.9, 9.9)
        trend_r2  = clamp_ratio(safe_float(tech.get("trendR2",  0)),  0.0, 1.0)
        vol_comp  = clamp_ratio(safe_float(tech.get("volComp",  0)),  0.0, 9.9)

        # ── [FIX 3] 총점 = 4개 섹션 합산 ─────────────
        total_quant_score = clamp_score(moat_score + value_score + growth_score + tech_score)

        result.update({
            "gpa":               round(clamp_ratio(gpa,      -9.9, 9.9),  6),
            "roic":              round(clamp_ratio(roic_q,   -9.9, 9.9),  6),
            "accruals":          round(clamp_ratio(accruals, -9.9, 9.9),  6),
            "ev_ebit":           round(ev_ebit,  4),
            "peg":               round(peg,      4),
            "pfcr":              round(pfcr,     4),
            "f_score":           int(f_score),
            "ato_accel":         round(clamp_ratio(ato_accel, -9.9, 9.9), 6),
            "op_lev":            round(op_lev,   4),
            "rel_mom":           round(rel_mom,  6),
            "dist_high":         round(dist_high,6),
            "trend_r2":          round(trend_r2, 6),
            "vol_comp":          round(vol_comp, 6),
            "moat_score":        round(moat_score,        4),
            "value_score":       round(value_score,       4),
            "growth_score":      round(growth_score,      4),
            "tech_score":        round(tech_score,        4),   # [FIX 3]
            "total_quant_score": round(total_quant_score, 4),   # [FIX 3]
        })

    except Exception as e:
        print(f"         ⚠️  calc_quant_scores: {e}")
        traceback.print_exc()

    return result


# ════════════════════════════════════════════════════
# 8. 등급 산정 (프론트 getRating 로직 그대로)
# ════════════════════════════════════════════════════
def get_final_grade(total_score: float) -> str:
    """
    [FIX 4] 프론트엔드 getRating 함수와 동일한 등급 기준.
    """
    if   total_score >= 80: return "1"
    elif total_score >= 72: return "2"
    elif total_score >= 65: return "3"
    elif total_score >= 55: return "4"
    elif total_score >= 45: return "5"
    elif total_score >= 35: return "6"
    else:                   return "7"


# ════════════════════════════════════════════════════
# 9. SQL 정의
# ════════════════════════════════════════════════════

UPSERT_ITEM_SQL = """
INSERT INTO ticker_item (
    ticker, trading_date,
    open_price, high_price, low_price, close_price, volume,
    per, forward_per, roa, roe, roic, pbr, eps, roi
) VALUES %s
ON CONFLICT (ticker, trading_date) DO UPDATE SET
    open_price   = EXCLUDED.open_price,
    high_price   = EXCLUDED.high_price,
    low_price    = EXCLUDED.low_price,
    close_price  = EXCLUDED.close_price,
    volume       = EXCLUDED.volume,
    per          = EXCLUDED.per,
    forward_per  = EXCLUDED.forward_per,
    roa          = EXCLUDED.roa,
    roe          = EXCLUDED.roe,
    roic         = EXCLUDED.roic,
    pbr          = EXCLUDED.pbr,
    eps          = EXCLUDED.eps,
    roi          = EXCLUDED.roi;
"""

# [FIX 3] tech_score, total_score 컬럼 추가
# ※ stock_quant_analysis 테이블에 아래 두 컬럼이 추가되어 있어야 합니다:
#   ALTER TABLE stock_quant_analysis ADD COLUMN IF NOT EXISTS tech_score  numeric(10,4);
#   ALTER TABLE stock_quant_analysis ADD COLUMN IF NOT EXISTS total_score numeric(10,4);
UPSERT_QUANT_SQL = """
INSERT INTO stock_quant_analysis (
    ticker, trading_date,
    gpa, roic, accruals, ev_ebit, peg, pfcr, f_score,
    ato_accel, op_lev, rel_mom, dist_high, trend_r2, vol_comp,
    moat_score, value_score, growth_score,
    tech_score, total_quant_score
) VALUES %s
ON CONFLICT (ticker, trading_date) DO UPDATE SET
    gpa               = EXCLUDED.gpa,
    roic              = EXCLUDED.roic,
    accruals          = EXCLUDED.accruals,
    ev_ebit           = EXCLUDED.ev_ebit,
    peg               = EXCLUDED.peg,
    pfcr              = EXCLUDED.pfcr,
    f_score           = EXCLUDED.f_score,
    ato_accel         = EXCLUDED.ato_accel,
    op_lev            = EXCLUDED.op_lev,
    rel_mom           = EXCLUDED.rel_mom,
    dist_high         = EXCLUDED.dist_high,
    trend_r2          = EXCLUDED.trend_r2,
    vol_comp          = EXCLUDED.vol_comp,
    moat_score        = EXCLUDED.moat_score,
    value_score       = EXCLUDED.value_score,
    growth_score      = EXCLUDED.growth_score,
    tech_score        = EXCLUDED.tech_score,
    total_quant_score = EXCLUDED.total_quant_score;
"""

UPDATE_QUANT_RANK_SQL = """
UPDATE stock_quant_analysis
SET quant_rank = %s
WHERE ticker = %s
  AND trading_date = %s;
"""


# ════════════════════════════════════════════════════
# 10. 메인 배치
# ════════════════════════════════════════════════════
def run_daily_integrated_batch():
    # ── 처리 대상 영업일 결정 ──────────────────────────
    target_date = get_last_business_day()
    today_date  = datetime.now().date()
    conn = None

    # print(f"📅 처리 대상 영업일: {target_date}  (실행일: {today_date})")
    # print("🗂️  SEC CIK 맵 로딩 중...")
    load_cik_map()

    # print("📈 SPY 히스토리 캐싱 중...")
    get_spy_history()

    try:
        conn = get_db_connection()
        cur  = conn.cursor()

        cur.execute("SELECT ticker FROM ticker_header ORDER BY ticker")
        tickers = [r[0].strip().upper() for r in cur.fetchall()]
        total   = len(tickers)
        # print(f"📋 대상 티커: {total:,}개\n{'─'*60}")

        success_count = 0
        fail_count    = 0

        score_map: dict = {}

        for idx, ticker in enumerate(tickers, 1):
            # print(f"[{idx:>5}/{total}] 🔄 {ticker}", flush=True)

            try:
                # A. OHLCV — target_date 단 1행만 조회
                ohlcv_df = fetch_ohlcv_fdr(ticker, target_date)
                if ohlcv_df.empty:
                    print(f"         ⚠️  OHLCV 없음 — 스킵")
                    fail_count += 1
                    continue

                # B. 재무제표 (SEC)
                fin_raw = fetch_financial_sec(ticker)

                # C. 기술 지표 (FDR 2년치)
                tech = get_technical_timing_fdr(ticker)

                # D. 퀀트 점수
                quant = calc_quant_scores(fin_raw, tech)

                # E. ticker_item 행 구성
                item_values = []
                actual_date = None   # ohlcv_df 실제 날짜 — 두 테이블 날짜 통일용
                for dt, row in ohlcv_df.iterrows():
                    actual_date = dt   # FDR이 반환한 실제 날짜 저장
                    item_values.append((
                        ticker, dt,
                        safe_float(row.get("Open",   0)),
                        safe_float(row.get("High",   0)),
                        safe_float(row.get("Low",    0)),
                        safe_float(row.get("Close",  0)),
                        int(safe_float(row.get("Volume", 0))),
                        round(safe_float(fin_raw["per"]),         4),  # per
                        round(safe_float(fin_raw["forward_per"]), 4),  # forward_per
                        round(safe_float(fin_raw["roa"]),         4),  # roa
                        round(safe_float(fin_raw["roe"]),         4),  # roe
                        round(safe_float(fin_raw["roic"]),        4),  # roic
                        round(safe_float(fin_raw["pbr"]),         4),  # pbr
                        round(safe_float(fin_raw["eps"]),         4),  # eps
                        round(safe_float(fin_raw["roi"]),         4),  # roi
                    ))

                    # ─── 디버깅: 첫 번째 행만 출력 (필요시 주석 해제) ───
                    # if len(item_values) == 1:
                    #     print(f"🔍 [DEBUG {ticker}] DB 입력 직전 데이터 확인:")
                    #     print(f"   - PER: {fin_raw.get('per')}")
                    #     print(f"   - Forward PER: {fin_raw.get('forward_per')}")
                    #     print(f"   - PBR: {fin_raw.get('pbr')}")
                    #     print(f"   - EPS: {fin_raw.get('eps')}")
                    #     print(f"   - ROA/ROE/ROIC: {fin_raw.get('roa')}/{fin_raw.get('roe')}/{fin_raw.get('roic')}")
                    #     print(f"   - ROI: {fin_raw.get('roi')}")

                # F. stock_quant_analysis — actual_date로 ticker_item과 날짜 통일
                quant_values = [(
                    ticker, actual_date,   # target_date 대신 실제 OHLCV 날짜 사용
                    quant["gpa"],          quant["roic"],       quant["accruals"],
                    quant["ev_ebit"],      quant["peg"],        quant["pfcr"],
                    quant["f_score"],
                    quant["ato_accel"],    quant["op_lev"],
                    quant["rel_mom"],      quant["dist_high"],
                    quant["trend_r2"],     quant["vol_comp"],
                    quant["moat_score"],   quant["value_score"],
                    quant["growth_score"],
                    quant["tech_score"],
                    quant["total_quant_score"],
                )]

                # G. DB 저장
                if item_values:
                    execute_values(cur, UPSERT_ITEM_SQL,  item_values)
                if quant_values:
                    execute_values(cur, UPSERT_QUANT_SQL, quant_values)
                conn.commit()

                # 점수 수집 (actual_date 함께 저장 — 배치 말미 quant_rank UPDATE용)
                score_map[ticker] = (quant["total_quant_score"], actual_date)
                success_count += 1
                # print(
                #     f"         ✅ OHLCV {len(item_values)}행 | "
                #     f"Moat {quant['moat_score']:.1f} | "
                #     f"Value {quant['value_score']:.1f} | "
                #     f"Growth {quant['growth_score']:.1f} | "
                #     f"Tech {quant['tech_score']:.1f} | "
                #     f"Total {quant['total_quant_score']:.1f} | "
                #     f"F {quant['f_score']} | "
                #     f"FwdPE {fin_raw['forward_per']:.1f}"
                # )

                # SEC rate limit 대기 (10 req/s 이하)
                time.sleep(0.3)

            except KeyboardInterrupt:
                print("\n🛑 사용자 중단")
                conn.rollback()
                sys.exit(0)

            except Exception as e:
                print(f"         ❌ 오류: {e}")
                conn.rollback()
                fail_count += 1
                continue

        # ── 배치 말미: 등급 계산 → stock_quant_analysis.quant_rank 일괄 UPDATE ──
        if score_map:
            rank_update_rows = []

            for t, (score, adate) in score_map.items():
                grade_value = get_final_grade(score)
                rank_update_rows.append((grade_value, t, adate))

            try:
                cur.executemany(UPDATE_QUANT_RANK_SQL, rank_update_rows)
                conn.commit()
            except Exception as e:
                print(f"  ❌ quant_rank 업데이트 실패: {e}")
                conn.rollback()

    except Exception as e:
        print(f"🚨 치명적 오류: {e}")
        traceback.print_exc()

    finally:
        if conn:
            conn.close()
            # print("🔌 DB 연결 종료")

    # print(f"\n{'='*60}")
    # print(f"  ✅ 성공: {success_count:,}   ❌ 실패: {fail_count:,}   합계: {total:,}")
    # print(f"{'='*60}")


# ════════════════════════════════════════════════════
# 실행
# ════════════════════════════════════════════════════
if __name__ == "__main__":
    t0 = time.time()
    run_daily_integrated_batch()
    elapsed = time.time() - t0
    # print(f"⏱️  총 소요 시간: {elapsed / 60:.1f}분 ({elapsed:.0f}초)")