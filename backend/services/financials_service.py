from db_pool import get_cursor


def get_financials(ticker: str) -> dict | None:
    """
    FinancialsTab 데이터.
    - 연간/분기 손익계산서, 재무상태표, 현금흐름표, 핵심 지표
    """
    with get_cursor() as cur:
        cur.execute(
            "SELECT stock_id FROM stocks WHERE ticker = %s AND is_active = TRUE",
            (ticker.upper(),)
        )
        row = cur.fetchone()
    if not row:
        return None
    stock_id = row["stock_id"]

    sql = """
        SELECT
            fiscal_year,
            fiscal_quarter,
            period_end_date,
            report_type,

            -- 손익계산서
            revenue,
            gross_profit,
            ebit,
            net_income,
            eps_actual,
            eps_estimated,

            -- 재무상태표
            total_assets,
            total_equity,
            total_debt,
            cash_and_equivalents,
            book_value_per_share,

            -- 현금흐름표
            operating_cash_flow,
            free_cash_flow,
            capex,
            dividends_paid,

            -- 핵심 지표
            roic,
            gpa,
            fcf_margin,
            accruals_quality,
            ev_ebit,
            ev_fcf,
            pb_ratio,
            peg_ratio,
            net_debt_ebitda,
            ebitda,
            asset_turnover,
            operating_leverage

        FROM stock_financials
        WHERE stock_id = %s
        ORDER BY fiscal_year DESC, fiscal_quarter DESC
    """

    with get_cursor() as cur:
        cur.execute(sql, (stock_id,))
        rows = cur.fetchall()

    if not rows:
        return None

    def _f(v):
        return float(v) if v is not None else None

    def _build(rows):
        result = []
        for r in rows:
            result.append({
                "fiscalYear":    r["fiscal_year"],
                "fiscalQuarter": r["fiscal_quarter"],
                "periodEnd":     str(r["period_end_date"]),
                # 손익계산서
                "incomeStatement": {
                    "revenue":       _f(r["revenue"]),
                    "grossProfit":   _f(r["gross_profit"]),
                    "ebit":          _f(r["ebit"]),
                    "netIncome":     _f(r["net_income"]),
                    "epsActual":     _f(r["eps_actual"]),
                    "epsEstimated":  _f(r["eps_estimated"]),
                },
                # 재무상태표
                "balanceSheet": {
                    "totalAssets":    _f(r["total_assets"]),
                    "totalEquity":    _f(r["total_equity"]),
                    "totalDebt":      _f(r["total_debt"]),
                    "cash":           _f(r["cash_and_equivalents"]),
                    "bvps":           _f(r["book_value_per_share"]),
                },
                # 현금흐름표
                "cashFlow": {
                    "ocf":          _f(r["operating_cash_flow"]),
                    "fcf":          _f(r["free_cash_flow"]),
                    "capex":        _f(r["capex"]),
                    "dividendsPaid": _f(r["dividends_paid"]),
                },
                # 핵심 지표
                "keyRatios": {
                    "roic":           _f(r["roic"]),
                    "gpa":            _f(r["gpa"]),
                    "fcfMargin":      _f(r["fcf_margin"]),
                    "accrualsQuality": _f(r["accruals_quality"]),
                    "evEbit":         _f(r["ev_ebit"]),
                    "evFcf":          _f(r["ev_fcf"]),
                    "pbRatio":        _f(r["pb_ratio"]),
                    "pegRatio":       _f(r["peg_ratio"]),
                    "netDebtEbitda":  _f(r["net_debt_ebitda"]),
                    "ebitda":         _f(r["ebitda"]),
                    "assetTurnover":  _f(r["asset_turnover"]),
                    "opLeverage":     _f(r["operating_leverage"]),
                },
            })
        return result

    annual    = [r for r in rows if r["report_type"] == "ANNUAL"]
    quarterly = [r for r in rows if r["report_type"] == "QUARTERLY"]

    return {
        "ticker":    ticker.upper(),
        "annual":    _build(annual),
        "quarterly": _build(quarterly),
    }