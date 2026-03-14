"""
ticker_service.py — 티커 등록 서비스
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
프론트에서 티커 추가 시 호출.
① stocks 테이블 등록 (즉시 응답)
② 백그라운드: OHLCV 5년 + 실시간가격 + 재무제표(연간+분기) 수집

역할 분담:
  - ticker_service: 원시 데이터(raw) 수집 & INSERT
  - batch_ticker_item_daily: 파생지표 계산 & UPDATE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import yfinance as yf
import FinanceDataReader as fdr
from db_pool import get_cursor
from datetime import datetime, timedelta
from fastapi import BackgroundTasks
import pandas as pd
import numpy as np
import traceback
import time as _time


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 헬퍼
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _normalize_exchange(raw: str) -> str:
    return {
        "NMS": "NASDAQ", "NGM": "NASDAQ", "NCM": "NASDAQ", "NAS": "NASDAQ",
        "NYQ": "NYSE",   "NYS": "NYSE",
        "ASE": "AMEX",   "AMX": "AMEX",
    }.get(raw, "NASDAQ")


def _normalize_sector(raw: str) -> str:
    return {
        "Technology":             "45",
        "Healthcare":             "35",
        "Financial Services":     "40",
        "Consumer Cyclical":      "25",
        "Consumer Defensive":     "30",
        "Industrials":            "20",
        "Energy":                 "10",
        "Materials":              "15",
        "Real Estate":            "60",
        "Utilities":              "55",
        "Communication Services": "50",
    }.get(raw, "45")


def _f(v):
    """안전한 float 변환. None/NaN/Inf → None"""
    if v is None:
        return None
    try:
        fv = float(v)
        if np.isnan(fv) or np.isinf(fv):
            return None
        return fv
    except Exception:
        return None


def _v(df, keys: list, col):
    """DataFrame(재무제표)에서 값 추출. 여러 키 후보를 시도."""
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


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. OHLCV 5년 → stock_prices_daily
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _fetch_and_insert_ohlcv(stock_id: int, ticker: str) -> int:
    t0 = _time.time()
    df = None

    # 1차: FDR
    try:
        df = fdr.DataReader(ticker, start=(datetime.today() - timedelta(days=365*5)).strftime("%Y-%m-%d"))
        if df is None or df.empty:
            raise ValueError("빈 데이터")
        print(f"  [OHLCV] FDR 수집 OK: {len(df)}건")
    except Exception as e1:
        print(f"  [OHLCV] FDR 실패: {e1}")
        # 2차: yf.download
        try:
            df = yf.download(ticker, period="5y", auto_adjust=True, progress=False)
            if df is None or df.empty:
                raise ValueError("빈 데이터")
            print(f"  [OHLCV] yfinance 수집 OK: {len(df)}건")
        except Exception as e2:
            print(f"  [OHLCV] ❌ 완전 실패: {e2}")
            return 0

    df = df.dropna(subset=["Close"])
    df.index = pd.to_datetime(df.index).tz_localize(None)

    rows = []
    for trade_date, row in df.iterrows():
        c = _f(row.get("Close")) or 0
        if c <= 0:
            continue
        rows.append((
            stock_id, trade_date.date(),
            _f(row.get("Open")) or 0, _f(row.get("High")) or 0,
            _f(row.get("Low")) or 0, c, c,
            int(_f(row.get("Volume")) or 0), "FDR",
        ))

    if not rows:
        return 0

    with get_cursor() as cur:
        cur.executemany("""
            INSERT INTO stock_prices_daily (
                stock_id, trade_date,
                open_price, high_price, low_price,
                close_price, adj_close_price, volume, data_source
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (stock_id, trade_date) DO UPDATE SET
                open_price=EXCLUDED.open_price, high_price=EXCLUDED.high_price,
                low_price=EXCLUDED.low_price, close_price=EXCLUDED.close_price,
                adj_close_price=EXCLUDED.adj_close_price, volume=EXCLUDED.volume
        """, rows)

    print(f"  [OHLCV] ✅ {len(rows)}건 INSERT ({_time.time()-t0:.1f}초)")
    return len(rows)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. 실시간 가격 → stock_prices_realtime
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _upsert_realtime_price(stock_id: int, ticker: str, tk: yf.Ticker = None):
    t0 = _time.time()
    try:
        if tk is None:
            tk = yf.Ticker(ticker)

        price, prev, vol = None, None, None

        # 1차: fast_info
        try:
            fi    = tk.fast_info
            price = float(fi["last_price"])
            prev  = float(fi["previous_close"])
            vol   = int(fi.get("regular_market_volume") or 0)
        except Exception:
            pass

        # 2차: history fallback (가격 + 거래량)
        if not price or price <= 0:
            try:
                hist = tk.history(period="2d")
                if hist is not None and not hist.empty:
                    price = float(hist["Close"].iloc[-1])
                    prev  = float(hist["Close"].iloc[-2]) if len(hist) > 1 else price
                    vol   = int(hist["Volume"].iloc[-1])
            except Exception:
                pass

        # 3차: volume이 아직 0이거나 None이면 → stock_prices_daily 최신 행
        if not vol or vol <= 0:
            try:
                with get_cursor() as cur:
                    cur.execute("""
                        SELECT volume FROM stock_prices_daily
                        WHERE stock_id = %s
                        ORDER BY trade_date DESC LIMIT 1
                    """, (stock_id,))
                    row = cur.fetchone()
                    if row and row["volume"]:
                        vol = int(row["volume"])
            except Exception:
                pass

        if not price or price <= 0:
            print(f"  [REALTIME] ❌ 가격 수집 실패")
            return

        prev = prev or price
        vol  = vol or 0
        chg_amt = round(price - prev, 4)
        chg_pct = round((chg_amt / prev * 100) if prev else 0, 4)

        with get_cursor() as cur:
            cur.execute("""
                INSERT INTO stock_prices_realtime (
                    stock_id, current_price, price_change, price_change_pct,
                    volume_today, data_source, updated_at
                ) VALUES (%s,%s,%s,%s,%s,'yfinance',NOW())
                ON CONFLICT (stock_id) DO UPDATE SET
                    current_price=EXCLUDED.current_price,
                    price_change=EXCLUDED.price_change,
                    price_change_pct=EXCLUDED.price_change_pct,
                    volume_today=EXCLUDED.volume_today, updated_at=NOW()
            """, (stock_id, price, chg_amt, chg_pct, vol))

        print(f"  [REALTIME] ✅ ${price:.2f} ({chg_pct:+.2f}%) vol={vol:,} ({_time.time()-t0:.1f}초)")
    except Exception as e:
        print(f"  [REALTIME] ❌ {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. 재무제표 (연간 + 분기) → stock_financials
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _fetch_and_insert_financials(stock_id: int, ticker: str, tk: yf.Ticker = None):
    """
    원시 재무 데이터 수집 (연간 + 분기).
    파생지표는 배치잡에서 계산.
    """
    t0 = _time.time()

    if tk is None:
        tk = yf.Ticker(ticker)

    # ── yfinance 프로퍼티 순차 수집 ──
    info = {}
    try:
        info = tk.info or {}
        print(f"  [FIN] info OK ({_time.time()-t0:.1f}초)")
    except Exception as e:
        print(f"  [FIN] info 실패: {e}")

    annual_income = None
    try:
        annual_income = tk.financials
        cnt = len(annual_income.columns) if annual_income is not None and not annual_income.empty else 0
        print(f"  [FIN] 연간 Income OK: {cnt}개년 ({_time.time()-t0:.1f}초)")
    except Exception as e:
        print(f"  [FIN] 연간 Income 실패: {e}")

    annual_balance = None
    try:
        annual_balance = tk.balance_sheet
        cnt = len(annual_balance.columns) if annual_balance is not None and not annual_balance.empty else 0
        print(f"  [FIN] 연간 Balance OK: {cnt}개년 ({_time.time()-t0:.1f}초)")
    except Exception as e:
        print(f"  [FIN] 연간 Balance 실패: {e}")

    annual_cash = None
    try:
        annual_cash = tk.cashflow
        cnt = len(annual_cash.columns) if annual_cash is not None and not annual_cash.empty else 0
        print(f"  [FIN] 연간 CashFlow OK: {cnt}개년 ({_time.time()-t0:.1f}초)")
    except Exception as e:
        print(f"  [FIN] 연간 CashFlow 실패: {e}")

    qtr_income = None
    try:
        qtr_income = tk.quarterly_financials
        cnt = len(qtr_income.columns) if qtr_income is not None and not qtr_income.empty else 0
        print(f"  [FIN] 분기 Income OK: {cnt}분기 ({_time.time()-t0:.1f}초)")
    except Exception as e:
        print(f"  [FIN] 분기 Income 실패: {e}")

    qtr_balance = None
    try:
        qtr_balance = tk.quarterly_balance_sheet
        cnt = len(qtr_balance.columns) if qtr_balance is not None and not qtr_balance.empty else 0
        print(f"  [FIN] 분기 Balance OK: {cnt}분기 ({_time.time()-t0:.1f}초)")
    except Exception as e:
        print(f"  [FIN] 분기 Balance 실패: {e}")

    qtr_cash = None
    try:
        qtr_cash = tk.quarterly_cashflow
        cnt = len(qtr_cash.columns) if qtr_cash is not None and not qtr_cash.empty else 0
        print(f"  [FIN] 분기 CashFlow OK: {cnt}분기 ({_time.time()-t0:.1f}초)")
    except Exception as e:
        print(f"  [FIN] 분기 CashFlow 실패: {e}")

    shares     = _f(info.get("sharesOutstanding")) or 1
    market_cap = _f(info.get("marketCap")) or 0

    def _build_rows(report_type: str) -> list:
        if report_type == "ANNUAL":
            income, balance, cashflow = annual_income, annual_balance, annual_cash
        else:
            income, balance, cashflow = qtr_income, qtr_balance, qtr_cash

        ref_df = None
        for df in [income, balance, cashflow]:
            if df is not None and not df.empty:
                ref_df = df
                break
        if ref_df is None:
            return []

        rows = []
        for i, col in enumerate(ref_df.columns):
            try:
                period_end = pd.to_datetime(col).date()
                year    = period_end.year
                quarter = 0 if report_type == "ANNUAL" else ((period_end.month - 1) // 3 + 1)

                # Income Statement
                revenue      = _v(income, ["Total Revenue", "Revenue"], col)
                gross_profit = _v(income, ["Gross Profit"], col)
                ebit         = _v(income, ["EBIT", "Operating Income"], col)
                net_income   = _v(income, ["Net Income", "Net Income Common Stockholders"], col)
                eps_actual   = _v(income, ["Basic EPS", "Diluted EPS"], col)
                income_tax   = _v(income, ["Tax Provision", "Income Tax Expense"], col)
                pretax       = _v(income, ["Pretax Income", "Income Before Tax"], col)

                # EBITDA
                ebitda = _v(income, ["EBITDA", "Normalized EBITDA"], col)
                if ebitda is None and ebit is not None:
                    da = _v(cashflow, ["Depreciation And Amortization",
                                       "Depreciation & Amortization",
                                       "Depreciation Amortization Depletion"], col)
                    if da is not None:
                        ebitda = ebit + abs(da)

                # Balance Sheet
                total_assets = _v(balance, ["Total Assets"], col)
                total_equity = _v(balance, [
                    "Stockholders Equity", "Total Equity Gross Minority Interest",
                    "Common Stock Equity", "Ordinary Shares Equity",
                ], col)
                total_debt = _v(balance, [
                    "Total Debt", "Total Non Current Liabilities Net Minority Interest",
                    "Long Term Debt", "Long Term Debt And Capital Lease Obligation",
                ], col)
                cash = _v(balance, [
                    "Cash And Cash Equivalents",
                    "Cash Cash Equivalents And Short Term Investments",
                    "Cash Financial", "Cash And Short Term Investments",
                ], col)
                invested_cap = _v(balance, ["Invested Capital", "Total Capitalization"], col)
                if invested_cap is None and total_equity is not None:
                    invested_cap = (total_equity or 0) + (total_debt or 0) - (cash or 0)

                bvps = round(total_equity / shares, 4) if (total_equity and shares) else None

                # Cash Flow
                ocf = _v(cashflow, [
                    "Operating Cash Flow",
                    "Cash Flowsfrom Operating Activities",
                    "Cash Flow From Continuing Operating Activities",
                ], col)
                capex = _v(cashflow, [
                    "Capital Expenditure",
                    "Purchase Of Property Plant And Equipment",
                    "Net PPE Purchase And Sale",
                ], col)
                divs = _v(cashflow, [
                    "Common Stock Dividend Paid", "Cash Dividends Paid",
                    "Payment Of Dividends And Other Cash Distributions",
                ], col)

                fcf = None
                if ocf is not None and capex is not None:
                    fcf = ocf + capex
                elif ocf is not None:
                    fcf = ocf

                # EV (최신 연간행만)
                ev = None
                if i == 0 and report_type == "ANNUAL" and market_cap > 0:
                    ev = market_cap + (total_debt or 0) - (cash or 0)

                rows.append((
                    stock_id, year, quarter, period_end, report_type,
                    revenue, gross_profit, ebit, net_income,
                    eps_actual, None,
                    total_assets, total_equity, total_debt, cash,
                    invested_cap, bvps,
                    ocf, fcf, capex, divs,
                    income_tax, pretax,
                    ebitda, ev,
                    None, None, None, None,
                    None, None, None,
                    None, None, None, None,
                    "yfinance", "US-GAAP",
                ))
            except Exception as e:
                print(f"  [FIN] {report_type} {col} 파싱 오류: {e}")
                continue
        return rows

    annual_rows    = _build_rows("ANNUAL")
    quarterly_rows = _build_rows("QUARTERLY")
    all_rows       = annual_rows + quarterly_rows

    if not all_rows:
        print(f"  [FIN] ❌ 재무 데이터 없음")
        return

    with get_cursor() as cur:
        cur.executemany("""
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
                %s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s,%s,
                %s,%s,%s,%s,
                %s,%s,
                %s,%s,
                %s,%s,%s,%s,
                %s,%s,%s,
                %s,%s,
                %s,%s,
                %s,%s
            )
            ON CONFLICT (stock_id, fiscal_year, fiscal_quarter, report_type)
            DO UPDATE SET
                period_end_date      = EXCLUDED.period_end_date,
                revenue              = EXCLUDED.revenue,
                gross_profit         = EXCLUDED.gross_profit,
                ebit                 = EXCLUDED.ebit,
                net_income           = EXCLUDED.net_income,
                eps_actual           = EXCLUDED.eps_actual,
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
        """, all_rows)

    elapsed = round(_time.time() - t0, 1)
    print(f"  [FIN] ✅ 연간 {len(annual_rows)}건 + 분기 {len(quarterly_rows)}건 ({elapsed}초)")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 백그라운드 수집
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _background_collect(stock_id: int, ticker: str, tk: yf.Ticker):
    """각 단계 독립 실행 — 하나 실패해도 나머지 계속 진행"""
    total_start = _time.time()
    print(f"\n{'='*50}")
    print(f"[BG] ▶ {ticker} (stock_id={stock_id}) 수집 시작")
    print(f"{'='*50}")

    try:
        print(f"\n[BG] Step 1/3: OHLCV 5년...")
        _fetch_and_insert_ohlcv(stock_id, ticker)
    except Exception as e:
        print(f"  [OHLCV] ❌ 예외: {e}")
        traceback.print_exc()

    try:
        print(f"\n[BG] Step 2/3: 실시간 가격...")
        _upsert_realtime_price(stock_id, ticker, tk=tk)
    except Exception as e:
        print(f"  [REALTIME] ❌ 예외: {e}")
        traceback.print_exc()

    try:
        print(f"\n[BG] Step 3/3: 재무제표 (연간+분기)...")
        _fetch_and_insert_financials(stock_id, ticker, tk=tk)
    except Exception as e:
        print(f"  [FIN] ❌ 예외: {e}")
        traceback.print_exc()

    total_elapsed = round(_time.time() - total_start, 1)
    print(f"\n{'='*50}")
    print(f"[BG] ■ {ticker} 완료 (총 {total_elapsed}초)")
    print(f"{'='*50}\n")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 메인: 티커 추가
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def add_ticker(ticker: str, background_tasks: BackgroundTasks) -> dict:
    try:
        ticker = ticker.strip().upper()
        tk   = yf.Ticker(ticker)
        info = tk.info

        if not info or (
            info.get("regularMarketPrice") is None
            and info.get("currentPrice") is None
        ):
            symbol_type = info.get("quoteType") if info else None
            if not symbol_type:
                return {"success": False, "error": f"존재하지 않는 티커: {ticker}"}

        company_name  = info.get("longName") or info.get("shortName") or ticker
        description   = info.get("longBusinessSummary")
        exchange_code = _normalize_exchange(info.get("exchange", "NASDAQ"))
        sector_code   = _normalize_sector(info.get("sector", ""))
        shares_out    = info.get("sharesOutstanding")
        float_shares  = info.get("floatShares")

        listing_date  = info.get("firstTradeDateEpochUtc")
        if listing_date:
            listing_date = datetime.fromtimestamp(listing_date).strftime("%Y-%m-%d")

        with get_cursor() as cur:
            cur.execute(
                "SELECT exchange_id FROM exchanges WHERE exchange_code = %s",
                (exchange_code,)
            )
            row = cur.fetchone()
            if not row:
                return {"success": False, "error": f"거래소 없음: {exchange_code}"}
            exchange_id = row["exchange_id"]

            cur.execute("SELECT market_id FROM markets WHERE market_code = 'US'")
            market_id = cur.fetchone()["market_id"]

            cur.execute(
                "SELECT sector_id FROM sectors WHERE sector_code = %s AND market_id = %s",
                (sector_code, market_id)
            )
            sector_row = cur.fetchone()
            sector_id  = sector_row["sector_id"] if sector_row else None

            cur.execute("""
                INSERT INTO stocks (
                    ticker, company_name, company_name_en,
                    exchange_id, market_id, sector_id,
                    currency_code, shares_outstanding, float_shares,
                    description, listing_date, is_active
                ) VALUES (%s,%s,%s,%s,%s,%s,'USD',%s,%s,%s,%s,TRUE)
                ON CONFLICT (ticker, exchange_id) DO UPDATE SET
                    company_name=EXCLUDED.company_name,
                    sector_id=EXCLUDED.sector_id,
                    shares_outstanding=EXCLUDED.shares_outstanding,
                    float_shares=EXCLUDED.float_shares,
                    description=EXCLUDED.description,
                    is_active=TRUE, updated_at=NOW()
                RETURNING stock_id
            """, (
                ticker, company_name, company_name,
                exchange_id, market_id, sector_id,
                shares_out, float_shares,
                description, listing_date,
            ))
            stock_id = cur.fetchone()["stock_id"]

            cur.execute("""
                INSERT INTO stock_like_counts (stock_id, like_count, updated_at)
                VALUES (%s, 0, NOW())
                ON CONFLICT (stock_id) DO NOTHING
            """, (stock_id,))

        background_tasks.add_task(_background_collect, stock_id, ticker, tk)

        return {
            "success":  True,
            "ticker":   ticker,
            "stock_id": stock_id,
            "message":  "종목 등록 완료. OHLCV/재무 데이터는 백그라운드에서 수집 중입니다."
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 티커 비활성화
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def deactivate_tickers(tickers: list[str]) -> dict:
    try:
        with get_cursor() as cur:
            cur.execute("""
                UPDATE stocks SET is_active = FALSE, updated_at = NOW()
                WHERE ticker = ANY(%s)
            """, (tickers,))
        return {"success": True, "deleted": tickers}
    except Exception as e:
        return {"success": False, "error": str(e)}
