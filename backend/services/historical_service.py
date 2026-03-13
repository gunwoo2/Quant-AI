from db_pool import get_cursor


def get_historical(ticker: str) -> dict | None:
    """
    HistoricalTab 데이터.
    - OHLCV: stock_prices_daily (최근 1년)
    - 재무 차트: stock_financials (연간 최근 5년)
    """

    # 종목 존재 확인
    with get_cursor() as cur:
        cur.execute(
            "SELECT stock_id FROM stocks WHERE ticker = %s AND is_active = TRUE",
            (ticker.upper(),)
        )
        row = cur.fetchone()
    if not row:
        return None
    stock_id = row["stock_id"]

    # ── OHLCV (최근 1년) ──────────────────────────────
    ohlcv_sql = """
        SELECT
            trade_date,
            open_price   AS open,
            high_price   AS high,
            low_price    AS low,
            close_price  AS close,
            adj_close_price AS adj_close,
            volume
        FROM stock_prices_daily
        WHERE stock_id = %s
          AND trade_date >= CURRENT_DATE - INTERVAL '1 year'
        ORDER BY trade_date ASC
    """

    # ── 재무 차트용 연간 데이터 (최근 5년) ──────────────
    fin_sql = """
        SELECT
            fiscal_year,
            period_end_date,
            revenue,
            gross_profit,
            ebit,
            net_income,
            free_cash_flow,
            operating_cash_flow,
            roic,
            operating_leverage,
            total_debt,
            cash_and_equivalents,
            net_debt_ebitda,
            eps_actual
        FROM stock_financials
        WHERE stock_id = %s
          AND report_type = 'ANNUAL'
        ORDER BY fiscal_year DESC
        LIMIT 5
    """

    with get_cursor() as cur:
        cur.execute(ohlcv_sql, (stock_id,))
        ohlcv_rows = cur.fetchall()

        cur.execute(fin_sql, (stock_id,))
        fin_rows = cur.fetchall()

    def _f(v):
        return float(v) if v is not None else None

    # OHLCV 변환
    ohlcv = []
    for r in ohlcv_rows:
        ohlcv.append({
            "date":     str(r["trade_date"]),
            "open":     _f(r["open"]),
            "high":     _f(r["high"]),
            "low":      _f(r["low"]),
            "close":    _f(r["close"]),
            "adjClose": _f(r["adj_close"]),
            "volume":   int(r["volume"]) if r["volume"] else None,
        })

    # 재무 차트 변환 (연도 오름차순으로 뒤집기)
    fin_rows = list(reversed(fin_rows))
    financial_charts = {
        "revenue":      [],
        "grossProfit":  [],
        "netIncome":    [],
        "fcf":          [],
        "ocf":          [],
        "roic":         [],
        "opLeverage":   [],
        "debtSolvency": [],
        "eps":          [],
    }
    for r in fin_rows:
        year = str(r["fiscal_year"])
        financial_charts["revenue"].append({
            "year": year, "value": _f(r["revenue"])
        })
        financial_charts["grossProfit"].append({
            "year": year, "value": _f(r["gross_profit"])
        })
        financial_charts["netIncome"].append({
            "year": year, "value": _f(r["net_income"])
        })
        financial_charts["fcf"].append({
            "year": year, "value": _f(r["free_cash_flow"])
        })
        financial_charts["ocf"].append({
            "year": year, "value": _f(r["operating_cash_flow"])
        })
        financial_charts["roic"].append({
            "year": year, "value": _f(r["roic"])
        })
        financial_charts["opLeverage"].append({
            "year": year, "value": _f(r["operating_leverage"])
        })
        financial_charts["debtSolvency"].append({
            "year": year,
            "totalDebt": _f(r["total_debt"]),
            "cash":      _f(r["cash_and_equivalents"]),
            "netDebtEbitda": _f(r["net_debt_ebitda"])
        })
        financial_charts["eps"].append({
            "year": year, "value": _f(r["eps_actual"])
        })

    return {
        "ticker":          ticker.upper(),
        "ohlcv":           ohlcv,
        "financialCharts": financial_charts,
    }