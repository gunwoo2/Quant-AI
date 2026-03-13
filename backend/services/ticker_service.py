import yfinance as yf
import FinanceDataReader as fdr
from db_pool import get_cursor
from datetime import datetime, timedelta
from fastapi import BackgroundTasks
import pandas as pd


# ── 정규화 헬퍼 ────────────────────────────────────────
def _normalize_exchange(raw: str) -> str:
    return {
        "NMS": "NASDAQ", "NGM": "NASDAQ", "NCM": "NASDAQ",
        "NYQ": "NYSE",   "ASE": "AMEX",
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


# ── 1. OHLCV 5년 → stock_prices_daily ─────────────────
def _fetch_and_insert_ohlcv(stock_id: int, ticker: str) -> int:
    end   = datetime.today()
    start = end - timedelta(days=365 * 5)

    df = None
    try:
        df = fdr.DataReader(ticker, start=start.strftime("%Y-%m-%d"))
        if df is None or df.empty:
            raise ValueError("FDR 빈 데이터")
    except Exception:
        try:
            raw = yf.Ticker(ticker).history(period="5y")
            if raw is None or raw.empty:
                raise ValueError("yfinance 빈 데이터")
            df = raw
        except Exception as e:
            print(f"[OHLCV] {ticker} 수집 실패: {e}")
            return 0

    df = df.dropna(subset=["Close"])
    df.index = pd.to_datetime(df.index).tz_localize(None)

    rows = []
    for trade_date, row in df.iterrows():
        rows.append((
            stock_id,
            trade_date.date(),
            float(row.get("Open")   or 0),
            float(row.get("High")   or 0),
            float(row.get("Low")    or 0),
            float(row.get("Close")  or 0),
            float(row.get("Close")  or 0),
            int(row.get("Volume")   or 0),
            "FDR",
        ))

    if not rows:
        return 0

    with get_cursor() as cur:
        cur.executemany("""
            INSERT INTO stock_prices_daily (
                stock_id, trade_date,
                open_price, high_price, low_price,
                close_price, adj_close_price,
                volume, data_source
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (stock_id, trade_date) DO NOTHING
        """, rows)

    print(f"[OHLCV] {ticker}: {len(rows)}건 INSERT 완료")
    return len(rows)


# ── 2. 실시간 가격 → stock_prices_realtime ─────────────
def _upsert_realtime_price(stock_id: int, ticker: str, tk: yf.Ticker = None):
    try:
        if tk is None:
            tk = yf.Ticker(ticker)

        try:
            fi    = tk.fast_info
            price = float(fi["last_price"])
            prev  = float(fi["previous_close"])
            vol   = int(fi.get("regular_market_volume") or 0)
            if vol == 0:
                raise ValueError("volume 0")
        except Exception:
            hist  = tk.history(period="2d")
            if hist is not None and not hist.empty:
                price = float(hist["Close"].iloc[-1])
                prev  = float(hist["Close"].iloc[-2]) if len(hist) > 1 else price
                vol   = int(hist["Volume"].iloc[-1])
            else:
                info  = tk.info
                price = float(info.get("regularMarketPrice") or 0)
                prev  = float(info.get("previousClose") or price)
                vol   = int(info.get("regularMarketVolume") or 0)

        chg_amt = round(price - prev, 4)
        chg_pct = round((chg_amt / prev * 100) if prev else 0, 4)

        with get_cursor() as cur:
            cur.execute("""
                INSERT INTO stock_prices_realtime (
                    stock_id, current_price,
                    price_change, price_change_pct,
                    volume_today, data_source,
                    updated_at
                ) VALUES (%s, %s, %s, %s, %s, 'yfinance', NOW())
                ON CONFLICT (stock_id) DO UPDATE
                SET current_price    = EXCLUDED.current_price,
                    price_change     = EXCLUDED.price_change,
                    price_change_pct = EXCLUDED.price_change_pct,
                    volume_today     = EXCLUDED.volume_today,
                    data_source      = EXCLUDED.data_source,
                    updated_at       = NOW()
            """, (stock_id, price, chg_amt, chg_pct, vol))

        print(f"[REALTIME] {ticker}: ${price} (chg {chg_pct}%) UPSERT 완료")
    except Exception as e:
        print(f"[REALTIME] {ticker} 실패: {e}")


# ── 3. 재무제표 → stock_financials ────────────────────
def _fetch_and_insert_financials(stock_id: int, ticker: str, tk: yf.Ticker = None):
    if tk is None:
        tk = yf.Ticker(ticker)

    # 한번에 전부 수집
    try:
        info             = tk.info
        annual_income    = tk.financials
        annual_balance   = tk.balance_sheet
        annual_cashflow  = tk.cashflow
        qtr_income       = tk.quarterly_financials
        qtr_balance      = tk.quarterly_balance_sheet
        qtr_cashflow     = tk.quarterly_cashflow
    except Exception as e:
        print(f"[FINANCIALS] {ticker} 수집 실패: {e}")
        return

    # info에서 바로 쓸 수 있는 값들
    shares      = float(info.get("sharesOutstanding") or 1)
    market_cap  = float(info.get("marketCap")         or 0)
    ebitda_info = float(info.get("ebitda")             or 0) or None
    pb_info     = float(info.get("priceToBook")        or 0) or None
    peg_info    = float(info.get("pegRatio")           or 0) or None

    def _v(df, keys, col):
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

    def _build_rows(report_type: str) -> list:
        income   = annual_income   if report_type == "ANNUAL" else qtr_income
        balance  = annual_balance  if report_type == "ANNUAL" else qtr_balance
        cashflow = annual_cashflow if report_type == "ANNUAL" else qtr_cashflow

        if income is None or income.empty:
            return []

        cols = list(income.columns)  # 최신순 정렬
        rows = []

        for i, col in enumerate(cols):
            try:
                period_end = pd.to_datetime(col).date()
                year       = period_end.year
                quarter    = (period_end.month - 1) // 3 + 1 if report_type == "QUARTERLY" else 0

                # Income Statement
                revenue      = _v(income, ["Total Revenue"], col)
                gross_profit = _v(income, ["Gross Profit"], col)
                ebit         = _v(income, ["EBIT", "Operating Income"], col)
                net_income   = _v(income, ["Net Income"], col)
                eps_actual   = _v(income, ["Basic EPS", "Diluted EPS"], col)

                # Balance Sheet
                total_assets = _v(balance, ["Total Assets"], col)
                total_equity = _v(balance, ["Stockholders Equity", "Total Equity Gross Minority Interest"], col)
                total_debt   = _v(balance, ["Total Debt", "Long Term Debt"], col)
                cash         = _v(balance, ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"], col)
                invested_cap = _v(balance, ["Invested Capital"], col)
                bvps         = round(total_equity / shares, 4) if (total_equity and shares) else None

                # Cash Flow
                ocf   = _v(cashflow, ["Operating Cash Flow", "Cash From Operations"], col)
                capex = _v(cashflow, ["Capital Expenditure", "Purchase Of Property Plant And Equipment"], col)
                divs  = _v(cashflow, ["Common Stock Dividend Paid", "Cash Dividends Paid"], col)
                fcf   = (ocf + capex) if (ocf is not None and capex is not None) else None

                # 파생 지표 계산
                gpa            = (gross_profit / total_assets)       if (gross_profit and total_assets)    else None
                fcf_margin     = (fcf / revenue)                     if (fcf and revenue)                  else None
                accruals       = ((net_income - ocf) / total_assets) if (net_income and ocf and total_assets) else None
                asset_turnover = (revenue / total_assets)            if (revenue and total_assets)         else None

                # EV = Market Cap + Total Debt - Cash
                ev = (market_cap + (total_debt or 0) - (cash or 0)) if market_cap else None

                # EV 기반 배수
                ev_ebit = (ev / ebit)  if (ev and ebit and ebit != 0)  else None
                ev_fcf  = (ev / fcf)   if (ev and fcf  and fcf  != 0)  else None

                # EBITDA = EBIT + D&A (최신행만 info에서, 나머지는 근사)
                ebitda = ebitda_info if (i == 0 and report_type == "ANNUAL") else None

                # Net Debt / EBITDA
                net_debt          = ((total_debt or 0) - (cash or 0)) if total_debt else None
                net_debt_ebitda   = (net_debt / ebitda) if (net_debt and ebitda and ebitda != 0) else None

                # Operating Leverage = Δ영업이익 / Δ매출 (전기 대비)
                op_leverage = None
                if i + 1 < len(cols):
                    prev_col     = cols[i + 1]
                    prev_ebit    = _v(income, ["EBIT", "Operating Income"], prev_col)
                    prev_revenue = _v(income, ["Total Revenue"], prev_col)
                    if (prev_ebit and prev_revenue and ebit and revenue
                            and prev_ebit != 0 and prev_revenue != 0):
                        delta_ebit    = (ebit    - prev_ebit)    / abs(prev_ebit)
                        delta_revenue = (revenue - prev_revenue) / abs(prev_revenue)
                        op_leverage   = round(delta_ebit / delta_revenue, 4) if delta_revenue != 0 else None

                # pb, peg - 최신행만 info에서, 나머지 None
                pb  = pb_info  if (i == 0 and report_type == "ANNUAL") else None
                peg = peg_info if (i == 0 and report_type == "ANNUAL") else None

                rows.append((
                    stock_id, year, quarter, period_end, report_type,
                    revenue, gross_profit, ebit, net_income,
                    eps_actual, None,           # eps_estimated → 별도 수집
                    total_assets, total_equity, total_debt, cash,
                    invested_cap, bvps,
                    ocf, fcf, capex, divs,
                    None,                       # roic → 배치잡
                    gpa, fcf_margin, accruals,
                    ev_ebit, ev_fcf, pb,
                    peg, net_debt_ebitda,
                    ebitda, asset_turnover, op_leverage,
                    "yfinance", "US-GAAP",
                ))
            except Exception as e:
                print(f"[FINANCIALS] {ticker} {col} 파싱 오류: {e}")
                continue

        return rows

    annual_rows    = _build_rows("ANNUAL")
    quarterly_rows = _build_rows("QUARTERLY")
    all_rows       = annual_rows + quarterly_rows

    if not all_rows:
        print(f"[FINANCIALS] {ticker}: 재무제표 데이터 없음")
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
                roic, gpa, fcf_margin, accruals_quality,
                ev_ebit, ev_fcf, pb_ratio,
                peg_ratio, net_debt_ebitda,
                ebitda, asset_turnover, operating_leverage,
                data_source, accounting_standard
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s,
                %s, %s, %s,
                %s, %s
            )
            ON CONFLICT (stock_id, fiscal_year, fiscal_quarter, report_type)
            DO UPDATE SET
                revenue              = EXCLUDED.revenue,
                gross_profit         = EXCLUDED.gross_profit,
                ebit                 = EXCLUDED.ebit,
                net_income           = EXCLUDED.net_income,
                eps_actual           = EXCLUDED.eps_actual,
                total_assets         = EXCLUDED.total_assets,
                total_equity         = EXCLUDED.total_equity,
                total_debt           = EXCLUDED.total_debt,
                cash_and_equivalents = EXCLUDED.cash_and_equivalents,
                operating_cash_flow  = EXCLUDED.operating_cash_flow,
                free_cash_flow       = EXCLUDED.free_cash_flow,
                capex                = EXCLUDED.capex,
                gpa                  = EXCLUDED.gpa,
                fcf_margin           = EXCLUDED.fcf_margin,
                accruals_quality     = EXCLUDED.accruals_quality,
                ev_ebit              = EXCLUDED.ev_ebit,
                ev_fcf               = EXCLUDED.ev_fcf,
                pb_ratio             = EXCLUDED.pb_ratio,
                peg_ratio            = EXCLUDED.peg_ratio,
                net_debt_ebitda      = EXCLUDED.net_debt_ebitda,
                ebitda               = EXCLUDED.ebitda,
                asset_turnover       = EXCLUDED.asset_turnover,
                operating_leverage   = EXCLUDED.operating_leverage,
                updated_at           = NOW()
        """, all_rows)

    print(f"[FINANCIALS] {ticker}: 연간 {len(annual_rows)}건 + 분기 {len(quarterly_rows)}건 INSERT 완료")


# ── 백그라운드 수집 작업 ───────────────────────────────
def _background_collect(stock_id: int, ticker: str, tk: yf.Ticker):
    """API 응답 후 백그라운드에서 실행"""
    print(f"[BG] {ticker} 백그라운드 수집 시작")
    _fetch_and_insert_ohlcv(stock_id, ticker)
    _upsert_realtime_price(stock_id, ticker, tk=tk)
    _fetch_and_insert_financials(stock_id, ticker, tk=tk)
    print(f"[BG] {ticker} 백그라운드 수집 완료")


# ── 메인: 티커 추가 ────────────────────────────────────
def add_ticker(ticker: str, background_tasks: BackgroundTasks) -> dict:
    try:
        tk   = yf.Ticker(ticker)
        info = tk.info

        # info가 비어있으면 존재하지 않는 티커
        if not info or info.get("regularMarketPrice") is None and info.get("currentPrice") is None:
            symbol_type = info.get("quoteType")
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
                ) VALUES (%s, %s, %s, %s, %s, %s, 'USD', %s, %s, %s, %s, TRUE)
                ON CONFLICT (ticker, exchange_id) DO UPDATE
                SET is_active   = TRUE,
                    description = EXCLUDED.description,
                    updated_at  = NOW()
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

        # 즉시 응답 후 백그라운드에서 수집
        background_tasks.add_task(_background_collect, stock_id, ticker, tk)

        return {
            "success":  True,
            "ticker":   ticker,
            "stock_id": stock_id,
            "message":  "종목 등록 완료. OHLCV/재무 데이터는 백그라운드에서 수집 중입니다."
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


# ── 티커 비활성화 ──────────────────────────────────────
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