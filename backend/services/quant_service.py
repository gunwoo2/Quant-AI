from db_pool import get_cursor


def get_quant_detail(ticker: str) -> dict | None:
    """
    퀀트 레이팅 상세 — TTM 기반.
    Forward PER: 컨센서스 우선 → EPS CAGR 폴백
    Operating Leverage: TTM vs 전년TTM
    """
    sql = """
        WITH ttm_flow AS (
            SELECT
                sf_sub.stock_id,
                SUM(sf_sub.revenue)             AS ttm_revenue,
                SUM(sf_sub.ebit)                AS ttm_ebit,
                SUM(sf_sub.net_income)          AS ttm_net_income,
                SUM(sf_sub.operating_cash_flow) AS ttm_ocf,
                SUM(sf_sub.free_cash_flow)      AS ttm_fcf,
                SUM(sf_sub.gross_profit)        AS ttm_gross_profit,
                SUM(sf_sub.ebitda)              AS ttm_ebitda,
                SUM(sf_sub.income_tax)          AS ttm_income_tax,
                SUM(sf_sub.pretax_income)       AS ttm_pretax_income,
                SUM(sf_sub.eps_actual)          AS ttm_eps
            FROM (
                SELECT stock_id, revenue, ebit, net_income,
                       operating_cash_flow, free_cash_flow,
                       gross_profit, ebitda, income_tax, pretax_income,
                       eps_actual,
                       ROW_NUMBER() OVER (
                           PARTITION BY stock_id
                           ORDER BY fiscal_year DESC, fiscal_quarter DESC
                       ) AS rn
                FROM stock_financials
                WHERE report_type = 'QUARTERLY'
            ) sf_sub
            WHERE sf_sub.rn <= 4
            GROUP BY sf_sub.stock_id
        ),
        ttm_prev AS (
            SELECT
                sf_sub.stock_id,
                SUM(sf_sub.revenue) AS prev_revenue,
                SUM(sf_sub.ebit)    AS prev_ebit
            FROM (
                SELECT stock_id, revenue, ebit,
                       ROW_NUMBER() OVER (
                           PARTITION BY stock_id
                           ORDER BY fiscal_year DESC, fiscal_quarter DESC
                       ) AS rn
                FROM stock_financials
                WHERE report_type = 'QUARTERLY'
            ) sf_sub
            WHERE sf_sub.rn BETWEEN 5 AND 8
            GROUP BY sf_sub.stock_id
        ),
        latest_balance AS (
            SELECT DISTINCT ON (stock_id)
                stock_id,
                total_assets         AS latest_ta,
                total_equity         AS latest_equity,
                total_debt           AS latest_debt,
                cash_and_equivalents AS latest_cash,
                invested_capital     AS latest_ic
            FROM stock_financials
            WHERE report_type = 'QUARTERLY'
            ORDER BY stock_id, fiscal_year DESC, fiscal_quarter DESC
        ),
        eps_consensus AS (
            SELECT DISTINCT ON (stock_id)
                stock_id,
                eps_estimated AS consensus_eps
            FROM stock_financials
            WHERE report_type = 'ANNUAL'
              AND eps_estimated IS NOT NULL
            ORDER BY stock_id, fiscal_year DESC
        ),
        eps_annual_hist AS (
            SELECT
                stock_id,
                MAX(CASE WHEN rn = 1 THEN eps_actual END) AS eps_y1,
                MAX(CASE WHEN rn = 4 THEN eps_actual END) AS eps_y4
            FROM (
                SELECT stock_id, eps_actual,
                       ROW_NUMBER() OVER (PARTITION BY stock_id ORDER BY fiscal_year DESC) AS rn
                FROM stock_financials
                WHERE report_type = 'ANNUAL' AND eps_actual IS NOT NULL
            ) sub
            WHERE rn <= 5
            GROUP BY stock_id
        )
        SELECT
            s.ticker,
            s.shares_outstanding,

            -- Layer 1
            l1.layer1_score         AS total_score,
            l1.layer1_raw_score     AS raw_score,
            l1.moat_score           AS moat_weighted,
            l1.value_score          AS value_weighted,
            l1.momentum_score       AS momentum_weighted,
            l1.stability_score      AS stability_weighted,
            l1.calc_date,

            -- MOAT 점수
            moat.roic_score, moat.gpa_score, moat.fcf_margin_score,
            moat.accruals_quality_score, moat.net_debt_ebitda_score,
            moat.total_moat_score,

            -- VALUE 점수
            val.earnings_yield_score, val.ev_fcf_score,
            val.pb_score, val.peg_score, val.total_value_score,

            -- MOMENTUM 점수
            mom.f_score_raw, mom.f_score_points,
            mom.earnings_revision_score, mom.earnings_revision_ratio,
            mom.ato_acceleration_score, mom.op_leverage_score,
            mom.earnings_surprise_score, mom.earnings_surprise_pct,
            mom.total_momentum_score,

            -- STABILITY 점수
            stab.low_vol_score, stab.earnings_stability_score,
            stab.dividend_consistency_score,
            stab.annualized_volatility_250d, stab.eps_cv_3y,
            stab.dividend_consecutive_years, stab.total_stability_score,

            -- TTM 손익
            tf.ttm_revenue, tf.ttm_ebit, tf.ttm_net_income,
            tf.ttm_ocf, tf.ttm_fcf, tf.ttm_gross_profit,
            tf.ttm_ebitda, tf.ttm_income_tax, tf.ttm_pretax_income,
            tf.ttm_eps,

            -- TTM 전년
            tp.prev_revenue, tp.prev_ebit,

            -- 최신 잔액
            lb.latest_ta, lb.latest_equity, lb.latest_debt,
            lb.latest_cash, lb.latest_ic,

            -- Forward PER용
            ec.consensus_eps,
            eah.eps_y1, eah.eps_y4,

            -- 현재가
            rt.current_price AS price,

            -- 기술적 지표
            ti.relative_momentum_12_1  AS relative_momentum_pct,
            ti.high_52w_position_ratio AS dist_52w,
            ti.trend_r2_90d            AS trend_r2,
            ti.rsi_14, ti.obv_trend,
            ti.golden_cross, ti.death_cross,
            ti.ma_50, ti.ma_200,

            -- 섹터 백분위
            pct.roic_percentile, pct.gpa_percentile,
            pct.fcf_margin_percentile, pct.ev_ebit_percentile,
            pct.ev_fcf_percentile, pct.pb_percentile,
            pct.peg_percentile, pct.net_debt_ebitda_percentile,
            pct.low_vol_percentile, pct.eps_stability_percentile,
            pct.op_leverage_percentile

        FROM stocks s
        LEFT JOIN ttm_flow tf     ON s.stock_id = tf.stock_id
        LEFT JOIN ttm_prev tp     ON s.stock_id = tp.stock_id
        LEFT JOIN latest_balance lb ON s.stock_id = lb.stock_id
        LEFT JOIN eps_consensus ec  ON s.stock_id = ec.stock_id
        LEFT JOIN eps_annual_hist eah ON s.stock_id = eah.stock_id
        LEFT JOIN stock_prices_realtime rt ON s.stock_id = rt.stock_id
        LEFT JOIN (
            SELECT DISTINCT ON (stock_id)
                stock_id, layer1_score, layer1_raw_score,
                moat_score, value_score, momentum_score, stability_score,
                calc_date
            FROM stock_layer1_analysis
            ORDER BY stock_id, calc_date DESC
        ) l1 ON s.stock_id = l1.stock_id
        LEFT JOIN (
            SELECT DISTINCT ON (stock_id) stock_id,
                roic_score, gpa_score, fcf_margin_score,
                accruals_quality_score, net_debt_ebitda_score, total_moat_score
            FROM quant_moat_scores ORDER BY stock_id, calc_date DESC
        ) moat ON s.stock_id = moat.stock_id
        LEFT JOIN (
            SELECT DISTINCT ON (stock_id) stock_id,
                earnings_yield_score, ev_fcf_score, pb_score, peg_score, total_value_score
            FROM quant_value_scores ORDER BY stock_id, calc_date DESC
        ) val ON s.stock_id = val.stock_id
        LEFT JOIN (
            SELECT DISTINCT ON (stock_id) stock_id,
                f_score_raw, f_score_points,
                earnings_revision_score, earnings_revision_ratio,
                ato_acceleration_score, op_leverage_score,
                earnings_surprise_score, earnings_surprise_pct,
                total_momentum_score
            FROM quant_momentum_scores ORDER BY stock_id, calc_date DESC
        ) mom ON s.stock_id = mom.stock_id
        LEFT JOIN (
            SELECT DISTINCT ON (stock_id) stock_id,
                low_vol_score, earnings_stability_score, dividend_consistency_score,
                annualized_volatility_250d, eps_cv_3y, dividend_consecutive_years,
                total_stability_score
            FROM quant_stability_scores ORDER BY stock_id, calc_date DESC
        ) stab ON s.stock_id = stab.stock_id
        LEFT JOIN (
            SELECT DISTINCT ON (stock_id) stock_id,
                relative_momentum_12_1, high_52w_position_ratio,
                trend_r2_90d, rsi_14, obv_trend,
                golden_cross, death_cross, ma_50, ma_200
            FROM technical_indicators ORDER BY stock_id, calc_date DESC
        ) ti ON s.stock_id = ti.stock_id
        LEFT JOIN (
            SELECT DISTINCT ON (stock_id) stock_id,
                roic_percentile, gpa_percentile, fcf_margin_percentile,
                ev_ebit_percentile, ev_fcf_percentile, pb_percentile,
                peg_percentile, net_debt_ebitda_percentile,
                low_vol_percentile, eps_stability_percentile,
                op_leverage_percentile
            FROM sector_percentile_scores ORDER BY stock_id, calc_date DESC
        ) pct ON s.stock_id = pct.stock_id
        WHERE s.ticker = %s AND s.is_active = TRUE
        LIMIT 1
    """

    with get_cursor() as cur:
        cur.execute(sql, (ticker.upper(),))
        row = cur.fetchone()

    if not row:
        return None

    row = dict(row)

    def _f(key):
        v = row.get(key)
        return float(v) if v is not None else None

    def _i(key):
        v = row.get(key)
        return int(v) if v is not None else None

    # ── TTM 파생지표 ──
    ttm_rev    = _f("ttm_revenue")
    ttm_ebit   = _f("ttm_ebit")
    ttm_ni     = _f("ttm_net_income")
    ttm_ocf    = _f("ttm_ocf")
    ttm_fcf    = _f("ttm_fcf")
    ttm_gp     = _f("ttm_gross_profit")
    ttm_ebitda = _f("ttm_ebitda")
    ttm_tax    = _f("ttm_income_tax")
    ttm_pretax = _f("ttm_pretax_income")
    ttm_eps    = _f("ttm_eps")

    ta     = _f("latest_ta")
    equity = _f("latest_equity")
    debt   = _f("latest_debt")
    cash   = _f("latest_cash")
    ic     = _f("latest_ic")
    shares = _f("shares_outstanding")
    price  = _f("price")

    market_cap = price * shares if (price and shares) else None

    # ROIC
    roic = None
    if ttm_ebit is not None and ic and ic != 0:
        if ttm_tax is not None and ttm_pretax and ttm_pretax != 0:
            eff_tax = max(0.0, min(abs(ttm_tax / ttm_pretax), 0.50))
        else:
            eff_tax = 0.21
        roic = round(ttm_ebit * (1 - eff_tax) / ic, 4)

    gpa        = round(ttm_gp / ta, 4) if (ttm_gp and ta and ta != 0) else None
    fcf_margin = round(ttm_fcf / ttm_rev, 4) if (ttm_fcf is not None and ttm_rev and ttm_rev != 0) else None
    accruals   = round((ttm_ni - ttm_ocf) / ta, 4) if (ttm_ni is not None and ttm_ocf is not None and ta and ta != 0) else None

    net_debt = ((debt or 0) - (cash or 0)) if debt is not None else None
    nde      = round(net_debt / ttm_ebitda, 4) if (net_debt is not None and ttm_ebitda and ttm_ebitda != 0) else None

    ev       = (market_cap + (debt or 0) - (cash or 0)) if market_cap else None
    ev_ebit  = round(ev / ttm_ebit, 2) if (ev and ttm_ebit and ttm_ebit != 0) else None
    ev_fcf   = round(ev / ttm_fcf, 2)  if (ev and ttm_fcf and ttm_fcf != 0) else None
    pb_ratio = round(market_cap / equity, 2) if (market_cap and equity and equity != 0) else None
    earnings_yield = round(1 / ev_ebit, 4) if ev_ebit and ev_ebit != 0 else None

    # PEG
    peg_ratio = None
    if market_cap and ttm_ni and ttm_ni > 0:
        peg_ratio = round(market_cap / ttm_ni, 2)

    # Asset Turnover
    ato = round(ttm_rev / ta, 4) if (ttm_rev and ta and ta != 0) else None

    # ★ Operating Leverage (TTM vs 전년TTM)
    prev_rev  = _f("prev_revenue")
    prev_ebit = _f("prev_ebit")
    op_leverage = None
    if all(v is not None for v in [ttm_ebit, prev_ebit, ttm_rev, prev_rev]):
        if prev_ebit != 0 and prev_rev != 0:
            ebit_growth = (ttm_ebit - prev_ebit) / abs(prev_ebit)
            rev_growth  = (ttm_rev  - prev_rev)  / abs(prev_rev)
            if rev_growth != 0:
                op_leverage = round(ebit_growth / rev_growth, 4)

    # ★ Forward PER (컨센서스 우선 → CAGR 폴백)
    forward_per = None
    forward_eps = None
    forward_method = None

    # 1순위: 컨센서스
    consensus_eps = _f("consensus_eps")
    if consensus_eps and consensus_eps > 0 and price:
        fwd = round(price / consensus_eps, 2)
        if 0 < fwd <= 200:
            forward_per = fwd
            forward_eps = round(consensus_eps, 4)
            forward_method = "consensus"

    # 2순위: CAGR
    if forward_per is None and ttm_eps and ttm_eps > 0 and price:
        eps_y1 = _f("eps_y1")
        eps_y4 = _f("eps_y4")
        if eps_y1 and eps_y1 > 0 and eps_y4 and eps_y4 > 0:
            cagr = (eps_y1 / eps_y4) ** (1.0 / 3.0) - 1.0
            if -0.30 <= cagr <= 0.80:
                est_eps = round(ttm_eps * (1 + cagr), 4)
                if est_eps > 0:
                    fwd = round(price / est_eps, 2)
                    if 0 < fwd <= 200:
                        forward_per = fwd
                        forward_eps = est_eps
                        forward_method = "cagr"

    return {
        "ticker":            row["ticker"],
        "calcDate":          str(row["calc_date"]) if row.get("calc_date") else None,
        "totalScore":        _f("total_score"),
        "rawScore":          _f("raw_score"),
        "moatWeighted":      _f("moat_weighted"),
        "valueWeighted":     _f("value_weighted"),
        "momentumWeighted":  _f("momentum_weighted"),
        "stabilityWeighted": _f("stability_weighted"),
        "dataSource":        "TTM",
        "moat": {
            "roic":               roic,
            "gpa":                gpa,
            "fcfMargin":          fcf_margin,
            "accrualsQual":       accruals,
            "netDebtEbitda":      nde,
            "roicScore":          _f("roic_score"),
            "gpaScore":           _f("gpa_score"),
            "fcfMarginScore":     _f("fcf_margin_score"),
            "accrualsScore":      _f("accruals_quality_score"),
            "netDebtEbitdaScore": _f("net_debt_ebitda_score"),
            "totalMoatScore":     _f("total_moat_score"),
        },
        "value": {
            "earningsYield":      earnings_yield,
            "evEbit":             ev_ebit,
            "evFcf":              ev_fcf,
            "pbRatio":            pb_ratio,
            "pegRatio":           peg_ratio,
            "forwardPer":         forward_per,
            "forwardEps":         forward_eps,
            "forwardMethod":      forward_method,
            "earningsYieldScore": _f("earnings_yield_score"),
            "evFcfScore":         _f("ev_fcf_score"),
            "pbScore":            _f("pb_score"),
            "pegScore":           _f("peg_score"),
            "totalValueScore":    _f("total_value_score"),
        },
        "momentum": {
            "fScoreRaw":             _i("f_score_raw"),
            "fScorePoints":          _f("f_score_points"),
            "earningsRevisionRatio": _f("earnings_revision_ratio"),
            "earningsRevisionScore": _f("earnings_revision_score"),
            "atoAcceleration":       ato,
            "atoAccelerationScore":  _f("ato_acceleration_score"),
            "opLeverage":            op_leverage,
            "opLeverageScore":       _f("op_leverage_score"),
            "earningsSurprisePct":   _f("earnings_surprise_pct"),
            "earningsSurpriseScore": _f("earnings_surprise_score"),
            "totalMomentumScore":    _f("total_momentum_score"),
        },
        "stability": {
            "annualizedVol250d":        _f("annualized_volatility_250d"),
            "epsCv3y":                  _f("eps_cv_3y"),
            "dividendConsecutiveYears": _i("dividend_consecutive_years"),
            "lowVolScore":              _f("low_vol_score"),
            "earningsStabilityScore":   _f("earnings_stability_score"),
            "dividendConsistencyScore": _f("dividend_consistency_score"),
            "totalStabilityScore":      _f("total_stability_score"),
        },
        "technical": {
            "relativeMomentumPct": _f("relative_momentum_pct"),
            "dist52W":             _f("dist_52w"),
            "trendR2":             _f("trend_r2"),
            "rsi14":               _f("rsi_14"),
            "obvTrend":            row.get("obv_trend"),
            "goldenCross":         row.get("golden_cross"),
            "deathCross":          row.get("death_cross"),
            "ma50":                _f("ma_50"),
            "ma200":               _f("ma_200"),
        },
        "sectorPercentile": {
            "roicPercentile":          _f("roic_percentile"),
            "gpaPercentile":           _f("gpa_percentile"),
            "fcfPercentile":           _f("fcf_margin_percentile"),
            "evEbitPercentile":        _f("ev_ebit_percentile"),
            "evFcfPercentile":         _f("ev_fcf_percentile"),
            "pbPercentile":            _f("pb_percentile"),
            "pegPercentile":           _f("peg_percentile"),
            "netDebtEbitdaPercentile": _f("net_debt_ebitda_percentile"),
            "lowVolPercentile":        _f("low_vol_percentile"),
            "epsStabilityPercentile":  _f("eps_stability_percentile"),
            "opLeveragePercentile":    _f("op_leverage_percentile"),
        },
        "ttmRaw": {
            "revenue":         ttm_rev,
            "ebit":            ttm_ebit,
            "netIncome":       ttm_ni,
            "ocf":             ttm_ocf,
            "fcf":             ttm_fcf,
            "grossProfit":     ttm_gp,
            "ebitda":          ttm_ebitda,
            "totalAssets":     ta,
            "totalEquity":     equity,
            "totalDebt":       debt,
            "cash":            cash,
            "investedCapital": ic,
            "marketCap":       market_cap,
            "ev":              ev,
        },
    }