from db_pool import get_cursor


def get_quant_detail(ticker: str) -> dict | None:
    sql = """
        SELECT
            s.ticker,
            l1.layer1_score         AS total_score,
            l1.layer1_raw_score     AS raw_score,
            l1.moat_score           AS moat_weighted,
            l1.value_score          AS value_weighted,
            l1.momentum_score       AS momentum_weighted,
            l1.stability_score      AS stability_weighted,
            l1.calc_date,
            moat.roic_score,
            moat.gpa_score,
            moat.fcf_margin_score,
            moat.accruals_quality_score,
            moat.net_debt_ebitda_score,
            moat.total_moat_score,
            val.earnings_yield_score,
            val.ev_fcf_score,
            val.pb_score,
            val.peg_score,
            val.total_value_score,
            mom.f_score_raw,
            mom.f_score_points,
            mom.earnings_revision_score,
            mom.earnings_revision_ratio,
            mom.ato_acceleration_score,
            mom.op_leverage_score,
            mom.earnings_surprise_score,
            mom.earnings_surprise_pct,
            mom.total_momentum_score,
            stab.low_vol_score,
            stab.earnings_stability_score,
            stab.dividend_consistency_score,
            stab.annualized_volatility_250d,
            stab.eps_cv_3y,
            stab.dividend_consecutive_years,
            stab.total_stability_score,
            fin.roic,
            fin.gpa,
            fin.fcf_margin,
            fin.accruals_quality,
            fin.net_debt_ebitda,
            fin.ev_ebit,
            fin.ev_fcf,
            fin.pb_ratio,
            fin.peg_ratio,
            fin.asset_turnover,
            fin.operating_leverage,
            ti.relative_momentum_12_1       AS relative_momentum_pct,
            ti.high_52w_position_ratio      AS dist_52w,
            ti.trend_r2_90d                 AS trend_r2,
            ti.rsi_14,
            ti.obv_trend,
            ti.golden_cross,
            ti.death_cross,
            ti.ma_50,
            ti.ma_200,
            pct.roic_percentile,
            pct.gpa_percentile,
            pct.fcf_margin_percentile,
            pct.ev_ebit_percentile,
            pct.low_vol_percentile
        FROM stocks s
        LEFT JOIN (
            SELECT DISTINCT ON (stock_id)
                stock_id, layer1_score, layer1_raw_score,
                moat_score, value_score, momentum_score, stability_score,
                calc_date
            FROM stock_layer1_analysis
            ORDER BY stock_id, calc_date DESC
        ) l1 ON s.stock_id = l1.stock_id
        LEFT JOIN (
            SELECT DISTINCT ON (stock_id)
                stock_id,
                roic_score, gpa_score, fcf_margin_score,
                accruals_quality_score, net_debt_ebitda_score,
                total_moat_score
            FROM quant_moat_scores
            ORDER BY stock_id, calc_date DESC
        ) moat ON s.stock_id = moat.stock_id
        LEFT JOIN (
            SELECT DISTINCT ON (stock_id)
                stock_id,
                earnings_yield_score, ev_fcf_score, pb_score, peg_score,
                total_value_score
            FROM quant_value_scores
            ORDER BY stock_id, calc_date DESC
        ) val ON s.stock_id = val.stock_id
        LEFT JOIN (
            SELECT DISTINCT ON (stock_id)
                stock_id,
                f_score_raw, f_score_points,
                earnings_revision_score, earnings_revision_ratio,
                ato_acceleration_score, op_leverage_score,
                earnings_surprise_score, earnings_surprise_pct,
                total_momentum_score
            FROM quant_momentum_scores
            ORDER BY stock_id, calc_date DESC
        ) mom ON s.stock_id = mom.stock_id
        LEFT JOIN (
            SELECT DISTINCT ON (stock_id)
                stock_id,
                low_vol_score, earnings_stability_score,
                dividend_consistency_score,
                annualized_volatility_250d,
                eps_cv_3y, dividend_consecutive_years,
                total_stability_score
            FROM quant_stability_scores
            ORDER BY stock_id, calc_date DESC
        ) stab ON s.stock_id = stab.stock_id
        LEFT JOIN (
            SELECT DISTINCT ON (stock_id)
                stock_id,
                roic, gpa, fcf_margin, accruals_quality,
                net_debt_ebitda, ev_ebit, ev_fcf,
                pb_ratio, peg_ratio,
                asset_turnover, operating_leverage
            FROM stock_financials
            WHERE report_type = 'ANNUAL'
            ORDER BY stock_id, fiscal_year DESC
        ) fin ON s.stock_id = fin.stock_id
        LEFT JOIN (
            SELECT DISTINCT ON (stock_id)
                stock_id,
                relative_momentum_12_1, high_52w_position_ratio,
                trend_r2_90d, rsi_14, obv_trend,
                golden_cross, death_cross, ma_50, ma_200
            FROM technical_indicators
            ORDER BY stock_id, calc_date DESC
        ) ti ON s.stock_id = ti.stock_id
        LEFT JOIN (
            SELECT DISTINCT ON (stock_id)
                stock_id,
                roic_percentile, gpa_percentile,
                fcf_margin_percentile, ev_ebit_percentile,
                low_vol_percentile
            FROM sector_percentile_scores
            ORDER BY stock_id, calc_date DESC
        ) pct ON s.stock_id = pct.stock_id
        WHERE s.ticker = %s
          AND s.is_active = TRUE
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

    ev_ebit = _f("ev_ebit")
    earnings_yield = round(1 / ev_ebit, 4) if ev_ebit and ev_ebit != 0 else None

    return {
        "ticker":            row["ticker"],
        "calcDate":          str(row["calc_date"]) if row.get("calc_date") else None,
        "totalScore":        _f("total_score"),
        "rawScore":          _f("raw_score"),
        "moatWeighted":      _f("moat_weighted"),
        "valueWeighted":     _f("value_weighted"),
        "momentumWeighted":  _f("momentum_weighted"),
        "stabilityWeighted": _f("stability_weighted"),
        "moat": {
            "roic":               _f("roic"),
            "gpa":                _f("gpa"),
            "fcfMargin":          _f("fcf_margin"),
            "accrualsQual":       _f("accruals_quality"),
            "netDebtEbitda":      _f("net_debt_ebitda"),
            "roicScore":          _f("roic_score"),
            "gpaScore":           _f("gpa_score"),
            "fcfMarginScore":     _f("fcf_margin_score"),
            "accrualsScore":      _f("accruals_quality_score"),
            "netDebtEbitdaScore": _f("net_debt_ebitda_score"),
            "totalMoatScore":     _f("total_moat_score"),
        },
        "value": {
            "earningsYield":      earnings_yield,
            "evFcf":              _f("ev_fcf"),
            "pbRatio":            _f("pb_ratio"),
            "pegRatio":           _f("peg_ratio"),
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
            "atoAcceleration":       _f("asset_turnover"),
            "atoAccelerationScore":  _f("ato_acceleration_score"),
            "opLeverage":            _f("operating_leverage"),
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
            "roicPercentile":   _f("roic_percentile"),
            "gpaPercentile":    _f("gpa_percentile"),
            "fcfPercentile":    _f("fcf_margin_percentile"),
            "evEbitPercentile": _f("ev_ebit_percentile"),
            "lowVolPercentile": _f("low_vol_percentile"),
        }
    }
