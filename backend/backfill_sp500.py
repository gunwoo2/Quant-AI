#!/usr/bin/env python3
"""
backfill_sp500.py — S&P 500 OHLCV / 실시간가격 / 재무제표 일괄 수집 (v6)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
v5 → v6 변경:
  · OHLCV 한투 API **10스레드 병렬** (v5는 순차 → 14시간급)
  · 초당 20건 API 제한을 RateLimiter로 정확히 제어
  · 토큰 1개 공유 (thread-safe)
  · 진행 로그: 50종목마다 + ETA 표시

예상 소요시간:
  · OHLCV 500종목 (2년치): ~20~30분 (v5 대비 10배↑)
  · 재무 500종목: ~15~25분 (8스레드)
  · 합계: ~40~55분

사용법:
  python -m backfill_sp500              # 전체
  python -m backfill_sp500 --skip 100   # 이어하기
  python -m backfill_sp500 --only AAPL MSFT
  python -m backfill_sp500 --skip-ohlcv # 재무만
  python -m backfill_sp500 --skip-fin   # OHLCV만
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import sys, os, time, argparse, traceback, requests, threading
from datetime import datetime, timedelta, date
from concurrent.futures import ThreadPoolExecutor, as_completed

import yfinance as yf
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import settings
from db_pool import init_pool, get_cursor


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 공통 헬퍼
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _f(v):
    if v is None:
        return None
    try:
        fv = float(v)
        return None if (np.isnan(fv) or np.isinf(fv)) else fv
    except Exception:
        return None


def _v(df, keys: list, col):
    if df is None or df.empty or col not in df.columns:
        return None
    for key in keys:
        if key in df.index:
            try:
                val = df.loc[key, col]
                if pd.notna(val):
                    return float(val)
            except Exception:
                pass
    return None


def _get_active_stocks(only_tickers=None):
    with get_cursor() as cur:
        if only_tickers:
            cur.execute("""
                SELECT s.stock_id, s.ticker, s.shares_outstanding,
                       e.exchange_code
                FROM stocks s
                JOIN exchanges e ON s.exchange_id = e.exchange_id
                WHERE s.is_active = TRUE AND s.ticker = ANY(%s)
                ORDER BY s.ticker
            """, (only_tickers,))
        else:
            cur.execute("""
                SELECT s.stock_id, s.ticker, s.shares_outstanding,
                       e.exchange_code
                FROM stocks s
                JOIN exchanges e ON s.exchange_id = e.exchange_id
                WHERE s.is_active = TRUE
                ORDER BY s.ticker
            """)
        return [dict(r) for r in cur.fetchall()]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# API Rate Limiter (초당 N건 제한)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class RateLimiter:
    """Thread-safe 초당 호출 제한"""
    def __init__(self, calls_per_second: int = 18):
        self._interval = 1.0 / calls_per_second
        self._lock = threading.Lock()
        self._last_call = 0.0

    def wait(self):
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_call
            if elapsed < self._interval:
                time.sleep(self._interval - elapsed)
            self._last_call = time.monotonic()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 한국투자증권 API 클라이언트
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

EXCHANGE_TO_EXCD = {
    "NYSE": "NYS", "NASDAQ": "NAS", "AMEX": "AMS",
    "NYS": "NYS", "NAS": "NAS", "AMS": "AMS",
}


class KISClient:
    """한국투자증권 Open API (토큰 thread-safe)"""

    def __init__(self, rate_limiter: RateLimiter):
        self.base_url   = settings.KIS_BASE_URL
        self.app_key    = settings.KIS_APP_KEY
        self.app_secret = settings.KIS_APP_SECRET
        self.token      = None
        self.token_exp  = None
        self._token_lock = threading.Lock()
        self._rl = rate_limiter
        self._ensure_token()

    def _ensure_token(self):
        with self._token_lock:
            if self.token and self.token_exp and datetime.now() < self.token_exp - timedelta(minutes=30):
                return
            url = f"{self.base_url}/oauth2/tokenP"
            body = {
                "grant_type": "client_credentials",
                "appkey":     self.app_key,
                "appsecret":  self.app_secret,
            }
            resp = requests.post(url, json=body, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            self.token = data["access_token"]
            self.token_exp = datetime.now() + timedelta(hours=23)
            print(f"  [KIS] 토큰 발급 완료 (만료: {self.token_exp.strftime('%H:%M')})")

    def _headers(self, tr_id: str) -> dict:
        self._ensure_token()
        return {
            "content-type":  "application/json; charset=utf-8",
            "authorization": f"Bearer {self.token}",
            "appkey":        self.app_key,
            "appsecret":     self.app_secret,
            "tr_id":         tr_id,
            "custtype":      "P",
        }

    def daily_prices(self, excd: str, ticker: str,
                     end_date: str = "", max_pages: int = 6) -> list:
        """해외주식 일봉 조회 (페이징, rate limit 적용)"""
        url = f"{self.base_url}/uapi/overseas-price/v1/quotations/dailyprice"
        all_rows = []
        bymd = end_date
        seen_dates = set()

        for page in range(max_pages):
            self._rl.wait()  # ← 초당 제한 대기

            params = {
                "AUTH": "", "EXCD": excd, "SYMB": ticker,
                "GUBN": "0", "BYMD": bymd, "MODP": "0",
            }
            try:
                resp = requests.get(url, headers=self._headers("HHDFS76240000"),
                                    params=params, timeout=15)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                break

            if data.get("rt_cd") != "0":
                break

            items = data.get("output2", [])
            if not items:
                break

            new_count = 0
            for item in items:
                dt_str = item.get("xymd", "")
                if not dt_str or len(dt_str) != 8 or dt_str in seen_dates:
                    continue
                seen_dates.add(dt_str)
                try:
                    td = date(int(dt_str[:4]), int(dt_str[4:6]), int(dt_str[6:8]))
                    o = float(item.get("open", 0))
                    h = float(item.get("high", 0))
                    l = float(item.get("low", 0))
                    c = float(item.get("clos", 0))
                    v = int(float(item.get("tvol", 0)))
                    if c > 0:
                        all_rows.append((td, o, h, l, c, v))
                        new_count += 1
                except Exception:
                    continue

            # 중복 데이터만 오면 종료 (무한루프 방지)
            if new_count == 0:
                break

            # 마지막 페이지 체크
            if len(items) < 100:
                break

            # 다음 페이지 기준일
            last_dt = items[-1].get("xymd", "")
            if not last_dt or last_dt == bymd:
                break  # 기준일 안 바뀌면 종료
            bymd = last_dt

        return all_rows


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Phase 1: OHLCV + 실시간가격 (한투 API, 10스레드 병렬)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

OHLCV_WORKERS = 10


def _collect_one_ohlcv(kis: KISClient, stock: dict) -> dict:
    """단일 종목 OHLCV 수집 (스레드에서 실행)"""
    stock_id = stock["stock_id"]
    ticker   = stock["ticker"]
    exch     = stock.get("exchange_code", "NASDAQ")
    excd     = EXCHANGE_TO_EXCD.get(exch, "NAS")

    result = {"ticker": ticker, "count": 0, "error": None}

    try:
        rows = kis.daily_prices(excd, ticker)

        if not rows:
            result["error"] = "0건"
            return result

        db_rows = [
            (stock_id, td, o, h, l, c, c, v, "kis")
            for td, o, h, l, c, v in rows
        ]

        with get_cursor() as cur:
            cur.executemany("""
                INSERT INTO stock_prices_daily (
                    stock_id, trade_date,
                    open_price, high_price, low_price,
                    close_price, adj_close_price, volume, data_source
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (stock_id, trade_date) DO UPDATE SET
                    open_price      = EXCLUDED.open_price,
                    high_price      = EXCLUDED.high_price,
                    low_price       = EXCLUDED.low_price,
                    close_price     = EXCLUDED.close_price,
                    adj_close_price = EXCLUDED.adj_close_price,
                    volume          = EXCLUDED.volume
            """, db_rows)

        # ── 실시간가격 ──
        rows.sort(key=lambda x: x[0], reverse=True)
        latest = rows[0]
        price, vol = latest[4], latest[5]

        if price > 0 and len(rows) >= 2:
            prev_close = rows[1][4]
            chg = round(price - prev_close, 4)
            chg_pct = round((chg / prev_close * 100) if prev_close else 0, 4)

            with get_cursor() as cur:
                cur.execute("""
                    INSERT INTO stock_prices_realtime (
                        stock_id, current_price, price_change, price_change_pct,
                        volume_today, data_source, updated_at
                    ) VALUES (%s,%s,%s,%s,%s,'kis',NOW())
                    ON CONFLICT (stock_id) DO UPDATE SET
                        current_price    = EXCLUDED.current_price,
                        price_change     = EXCLUDED.price_change,
                        price_change_pct = EXCLUDED.price_change_pct,
                        volume_today     = EXCLUDED.volume_today,
                        updated_at       = NOW()
                """, (stock_id, price, chg, chg_pct, vol))

        result["count"] = len(rows)

    except Exception as e:
        result["error"] = str(e)

    return result


def collect_ohlcv_parallel(kis: KISClient, stocks: list) -> int:
    """10스레드 병렬 OHLCV 수집"""
    total = len(stocks)
    ok_count = 0
    fail_count = 0
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=OHLCV_WORKERS) as executor:
        futures = {
            executor.submit(_collect_one_ohlcv, kis, s): s["ticker"]
            for s in stocks
        }

        done = 0
        for future in as_completed(futures):
            ticker = futures[future]
            done += 1
            try:
                r = future.result()
                if r["count"] > 0:
                    ok_count += 1
                else:
                    fail_count += 1
            except Exception as e:
                fail_count += 1

            if done % 50 == 0 or done == total:
                elapsed = time.time() - start_time
                rate = done / elapsed if elapsed > 0 else 0
                eta = (total - done) / rate if rate > 0 else 0
                print(f"  [{done}/{total}] ✅{ok_count} ❌{fail_count} "
                      f"| {elapsed:.0f}s 경과 | ETA {eta:.0f}s")

    return ok_count


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Phase 2: 재무제표 (yfinance 병렬)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FIN_WORKERS = 8


def _parse_rows(stock_id, ticker, income_df, balance_df, cash_df,
                shares, market_cap, report_type, max_periods):
    cols = []
    for df in [income_df, balance_df, cash_df]:
        if df is not None and not df.empty:
            cols = list(df.columns)
            break
    if not cols:
        return []

    cols = cols[:max_periods]
    rows = []

    for i, col in enumerate(cols):
        try:
            period_end = pd.to_datetime(col).date()
            year  = period_end.year
            month = period_end.month
            quarter = 0 if report_type == "ANNUAL" else max(1, min(4, (month + 2) // 3))

            revenue      = _v(income_df, ["Total Revenue", "Revenue"], col)
            gross_profit = _v(income_df, ["Gross Profit"], col)
            ebit         = _v(income_df, ["EBIT", "Operating Income"], col)
            net_income   = _v(income_df, ["Net Income", "Net Income Common Stockholders"], col)
            eps_actual   = _v(income_df, ["Basic EPS", "Diluted EPS"], col)
            income_tax   = _v(income_df, ["Tax Provision", "Income Tax Expense"], col)
            pretax       = _v(income_df, ["Pretax Income", "Income Before Tax"], col)

            ebitda = _v(income_df, ["EBITDA", "Normalized EBITDA"], col)
            if ebitda is None and ebit is not None:
                da = _v(cash_df, ["Depreciation And Amortization", "Depreciation & Amortization"], col)
                if da is not None:
                    ebitda = ebit + abs(da)

            total_assets = _v(balance_df, ["Total Assets"], col)
            total_equity = _v(balance_df, [
                "Stockholders Equity", "Total Equity Gross Minority Interest",
                "Common Stock Equity", "Ordinary Shares Equity"], col)
            total_debt = _v(balance_df, [
                "Total Debt", "Total Non Current Liabilities Net Minority Interest",
                "Long Term Debt", "Long Term Debt And Capital Lease Obligation"], col)
            cash = _v(balance_df, [
                "Cash And Cash Equivalents",
                "Cash Cash Equivalents And Short Term Investments",
                "Cash Financial", "Cash And Short Term Investments"], col)
            invested_cap = _v(balance_df, ["Invested Capital", "Total Capitalization"], col)
            if invested_cap is None and total_equity is not None:
                invested_cap = (total_equity or 0) + (total_debt or 0) - (cash or 0)
            bvps = round(total_equity / shares, 4) if (total_equity and shares) else None

            ocf = _v(cash_df, [
                "Operating Cash Flow", "Cash Flowsfrom Operating Activities",
                "Cash Flow From Continuing Operating Activities"], col)
            capex = _v(cash_df, [
                "Capital Expenditure", "Purchase Of Property Plant And Equipment",
                "Net PPE Purchase And Sale"], col)
            divs = _v(cash_df, [
                "Common Stock Dividend Paid", "Cash Dividends Paid",
                "Payment Of Dividends And Other Cash Distributions"], col)
            fcf = (ocf + capex) if (ocf is not None and capex is not None) else (ocf if ocf else None)

            ev = None
            if i == 0 and market_cap > 0:
                ev = market_cap + (total_debt or 0) - (cash or 0)

            rows.append((
                stock_id, year, quarter, period_end, report_type,
                revenue, gross_profit, ebit, net_income, eps_actual, None,
                total_assets, total_equity, total_debt, cash, invested_cap, bvps,
                ocf, fcf, capex, divs,
                income_tax, pretax, ebitda, ev,
                None, None, None, None, None, None, None, None, None, None, None,
                "yfinance", "US-GAAP",
            ))
        except Exception:
            continue

    return rows


INSERT_SQL = """
    INSERT INTO stock_financials (
        stock_id, fiscal_year, fiscal_quarter,
        period_end_date, report_type,
        revenue, gross_profit, ebit, net_income,
        eps_actual, eps_estimated,
        total_assets, total_equity, total_debt, cash_and_equivalents,
        invested_capital, book_value_per_share,
        operating_cash_flow, free_cash_flow, capex, dividends_paid,
        income_tax, pretax_income,
        ebitda, enterprise_value,
        roic, gpa, fcf_margin, accruals_quality,
        ev_ebit, ev_fcf, pb_ratio,
        peg_ratio, net_debt_ebitda,
        asset_turnover, operating_leverage,
        data_source, accounting_standard
    ) VALUES (
        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
    )
    ON CONFLICT (stock_id, fiscal_year, fiscal_quarter, report_type)
    DO UPDATE SET
        period_end_date      = EXCLUDED.period_end_date,
        revenue              = EXCLUDED.revenue,
        gross_profit         = EXCLUDED.gross_profit,
        ebit                 = EXCLUDED.ebit,
        net_income           = EXCLUDED.net_income,
        eps_actual           = EXCLUDED.eps_actual,
        eps_estimated        = COALESCE(EXCLUDED.eps_estimated, stock_financials.eps_estimated),
        total_assets         = EXCLUDED.total_assets,
        total_equity         = EXCLUDED.total_equity,
        total_debt           = EXCLUDED.total_debt,
        cash_and_equivalents = EXCLUDED.cash_and_equivalents,
        invested_capital     = EXCLUDED.invested_capital,
        book_value_per_share = EXCLUDED.book_value_per_share,
        operating_cash_flow  = EXCLUDED.operating_cash_flow,
        free_cash_flow       = EXCLUDED.free_cash_flow,
        capex                = EXCLUDED.capex,
        dividends_paid       = EXCLUDED.dividends_paid,
        income_tax           = EXCLUDED.income_tax,
        pretax_income        = EXCLUDED.pretax_income,
        ebitda               = EXCLUDED.ebitda,
        enterprise_value     = EXCLUDED.enterprise_value,
        data_source          = EXCLUDED.data_source,
        updated_at           = NOW()
"""


def collect_one_financials(stock_id, ticker, shares):
    result = {"ticker": ticker, "annual": 0, "quarterly": 0, "error": None}

    try:
        tk = yf.Ticker(ticker)

        try:
            fi = tk.fast_info
            mkt_cap = float(fi.get("market_cap") or 0)
            sh = float(fi.get("shares") or shares or 1)
        except Exception:
            mkt_cap = 0
            sh = shares or 1

        try:
            rows = _parse_rows(
                stock_id, ticker,
                tk.financials, tk.balance_sheet, tk.cashflow,
                sh, mkt_cap, "ANNUAL", 3
            )
            if rows:
                with get_cursor() as cur:
                    cur.executemany(INSERT_SQL, rows)
                result["annual"] = len(rows)
        except Exception as e:
            result["error"] = f"ANNUAL: {e}"

        try:
            rows = _parse_rows(
                stock_id, ticker,
                tk.quarterly_financials, tk.quarterly_balance_sheet, tk.quarterly_cashflow,
                sh, mkt_cap, "QUARTERLY", 12
            )
            if rows:
                with get_cursor() as cur:
                    cur.executemany(INSERT_SQL, rows)
                result["quarterly"] = len(rows)
        except Exception as e:
            if result["error"]:
                result["error"] += f" | QUARTERLY: {e}"
            else:
                result["error"] = f"QUARTERLY: {e}"

    except Exception as e:
        result["error"] = str(e)

    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 메인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip", type=int, default=0)
    parser.add_argument("--only", nargs="+")
    parser.add_argument("--skip-ohlcv", action="store_true")
    parser.add_argument("--skip-fin", action="store_true")
    args = parser.parse_args()

    init_pool()
    stocks = _get_active_stocks(only_tickers=args.only)

    if args.skip > 0:
        stocks = stocks[args.skip:]

    total = len(stocks)
    shares_map = {s["ticker"]: s.get("shares_outstanding") or 1 for s in stocks}

    print(f"\n{'='*60}")
    print(f"  ⚡ v6 — 한투 API {OHLCV_WORKERS}스레드 병렬 + yfinance 재무")
    print(f"  대상: {total}종목")
    print(f"  OHLCV: {'SKIP' if args.skip_ohlcv else f'한투 API {OHLCV_WORKERS}스레드'}")
    print(f"  재무:  {'SKIP' if args.skip_fin else f'yfinance {FIN_WORKERS}스레드'}")
    print(f"{'='*60}\n")

    start_time = time.time()

    # ════════════════════════════════════════════════════
    # Phase 1: OHLCV (한투 API 병렬)
    # ════════════════════════════════════════════════════
    ohlcv_ok = 0
    if not args.skip_ohlcv:
        print("━━━ Phase 1: OHLCV + 실시간가격 (한투 API 병렬) ━━━")
        rl = RateLimiter(calls_per_second=18)
        kis = KISClient(rl)
        ohlcv_ok = collect_ohlcv_parallel(kis, stocks)
        phase1_sec = round(time.time() - start_time)
        print(f"\n  Phase 1 완료: {ohlcv_ok}/{total}종목 | {phase1_sec}초\n")
    else:
        print("━━━ Phase 1: SKIP ━━━\n")

    # ════════════════════════════════════════════════════
    # Phase 2: 재무제표 (yfinance 병렬)
    # ════════════════════════════════════════════════════
    fin_annual_ok  = 0
    fin_quarter_ok = 0
    fin_fail       = 0

    if not args.skip_fin:
        print("━━━ Phase 2: 재무제표 (yfinance 병렬) ━━━")
        phase2_start = time.time()

        with ThreadPoolExecutor(max_workers=FIN_WORKERS) as executor:
            futures = {}
            for s in stocks:
                f = executor.submit(
                    collect_one_financials,
                    s["stock_id"], s["ticker"], shares_map[s["ticker"]]
                )
                futures[f] = s["ticker"]

            done_count = 0
            for future in as_completed(futures):
                ticker = futures[future]
                done_count += 1
                try:
                    r = future.result()
                    if r["annual"] > 0:
                        fin_annual_ok += 1
                    if r["quarterly"] > 0:
                        fin_quarter_ok += 1
                    if r["error"]:
                        fin_fail += 1
                except Exception:
                    fin_fail += 1

                if done_count % 50 == 0 or done_count == total:
                    elapsed = round(time.time() - phase2_start)
                    rate = done_count / elapsed if elapsed > 0 else 0
                    eta = round((total - done_count) / rate) if rate > 0 else 0
                    print(f"  [{done_count}/{total}] 연간 {fin_annual_ok} | "
                          f"분기 {fin_quarter_ok} | 실패 {fin_fail} | "
                          f"{elapsed}s 경과 | ETA {eta}s")
    else:
        print("━━━ Phase 2: SKIP ━━━\n")

    elapsed_total = round(time.time() - start_time)

    print(f"\n{'='*60}")
    print(f"  ✅ 전체 수집 완료!")
    print(f"  OHLCV+실시간: {ohlcv_ok}/{total}")
    print(f"  연간 재무:     {fin_annual_ok}/{total}")
    print(f"  분기 재무:     {fin_quarter_ok}/{total}")
    print(f"  재무 실패:     {fin_fail}/{total}")
    print(f"  총 소요시간:   {elapsed_total}초 ({elapsed_total//60}분 {elapsed_total%60}초)")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()