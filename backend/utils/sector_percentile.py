"""
sector_percentile.py — 섹터 내 백분위 계산 (★ TTM 기반)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
설계서 2.1 Sector Neutralization 기준.
최근 4분기 QUARTERLY 합산(TTM)으로 섹터 내 모든 종목과 비교.

변경이력:
  v1.0  — 초기 (ANNUAL 기준)
  v2.0  — 벌크 함수 추가
  v3.0  — ★ TTM 기반 전환
          · 손익: 최근 4분기 합산
          · 잔액: 최신 분기 값
          · operating_leverage: TTM vs 전년TTM
          · 모든 파생지표 Python에서 실시간 계산
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import numpy as np
from db_pool import get_cursor


def _f(v):
    """Decimal/str → float 안전 변환"""
    if v is None:
        return None
    try:
        return float(v)
    except Exception:
        return None


def _pct(values: list, target_val):
    """target_val이 리스트 내 몇 %ile인지 (높을수록 좋은 지표)"""
    if target_val is None:
        return None
    clean = [v for v in values if v is not None]
    if not clean:
        return None
    arr = np.array(clean, dtype=float)
    return float(np.sum(arr <= float(target_val)) / len(arr) * 100)


def _pct_inv(values: list, target_val):
    """낮을수록 좋은 지표: 역백분위"""
    if target_val is None:
        return None
    clean = [v for v in values if v is not None]
    if not clean:
        return None
    arr = np.array(clean, dtype=float)
    return float(np.sum(arr >= float(target_val)) / len(arr) * 100)


def _get_sector_rows_ttm(sector_code: str) -> tuple:
    """
    ★ TTM 기반: 섹터 내 모든 종목의 파생지표를 계산.

    SQL로 TTM 손익(4분기 합산) + 최신 잔액을 가져오고,
    Python에서 roic, gpa, fcf_margin, ev_ebit, ev_fcf, pb,
    peg, net_debt_ebitda, operating_leverage 등을 실시간 계산.
    """
    sql = """
        WITH ttm_flow AS (
            SELECT
                sf_sub.stock_id,
                SUM(sf_sub.revenue)             AS ttm_revenue,
                SUM(sf_sub.ebit)                AS ttm_ebit,
                SUM(sf_sub.net_income)          AS ttm_net_income,
                SUM(sf_sub.free_cash_flow)      AS ttm_fcf,
                SUM(sf_sub.gross_profit)        AS ttm_gross_profit,
                SUM(sf_sub.ebitda)              AS ttm_ebitda,
                SUM(sf_sub.income_tax)          AS ttm_income_tax,
                SUM(sf_sub.pretax_income)       AS ttm_pretax_income
            FROM (
                SELECT stock_id, revenue, ebit, net_income,
                       free_cash_flow, gross_profit, ebitda,
                       income_tax, pretax_income,
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
                total_assets, total_equity, total_debt,
                cash_and_equivalents, invested_capital
            FROM stock_financials
            WHERE report_type = 'QUARTERLY'
            ORDER BY stock_id, fiscal_year DESC, fiscal_quarter DESC
        )
        SELECT
            s.stock_id,
            s.shares_outstanding,
            rt.current_price,

            tf.ttm_revenue, tf.ttm_ebit, tf.ttm_net_income,
            tf.ttm_fcf, tf.ttm_gross_profit, tf.ttm_ebitda,
            tf.ttm_income_tax, tf.ttm_pretax_income,

            tp.prev_revenue, tp.prev_ebit,

            lb.total_assets, lb.total_equity, lb.total_debt,
            lb.cash_and_equivalents, lb.invested_capital,

            stab.annualized_volatility_250d AS low_vol,
            stab.eps_cv_3y

        FROM stocks s
        JOIN sectors sec ON s.sector_id = sec.sector_id
        LEFT JOIN ttm_flow tf ON s.stock_id = tf.stock_id
        LEFT JOIN ttm_prev tp ON s.stock_id = tp.stock_id
        LEFT JOIN latest_balance lb ON s.stock_id = lb.stock_id
        LEFT JOIN stock_prices_realtime rt ON s.stock_id = rt.stock_id
        LEFT JOIN (
            SELECT DISTINCT ON (stock_id)
                stock_id, annualized_volatility_250d, eps_cv_3y
            FROM quant_stability_scores
            ORDER BY stock_id, calc_date DESC
        ) stab ON s.stock_id = stab.stock_id
        WHERE sec.sector_code = %s
          AND s.is_active = TRUE
    """

    with get_cursor() as cur:
        cur.execute(
            "SELECT sector_id FROM sectors WHERE sector_code = %s LIMIT 1",
            (sector_code,)
        )
        sec_row = cur.fetchone()
        sector_id = sec_row["sector_id"] if sec_row else None

        cur.execute(sql, (sector_code,))
        db_rows = cur.fetchall()

    if not db_rows:
        return sector_id, []

    # ── Python에서 파생지표 계산 ──
    rows = []
    for r in db_rows:
        r = dict(r)
        price  = _f(r.get("current_price"))
        shares = _f(r.get("shares_outstanding"))
        rev    = _f(r.get("ttm_revenue"))
        ebit   = _f(r.get("ttm_ebit"))
        ni     = _f(r.get("ttm_net_income"))
        fcf    = _f(r.get("ttm_fcf"))
        gp     = _f(r.get("ttm_gross_profit"))
        ebitda = _f(r.get("ttm_ebitda"))
        tax    = _f(r.get("ttm_income_tax"))
        pretax = _f(r.get("ttm_pretax_income"))

        ta     = _f(r.get("total_assets"))
        equity = _f(r.get("total_equity"))
        debt   = _f(r.get("total_debt"))
        cash   = _f(r.get("cash_and_equivalents"))
        ic     = _f(r.get("invested_capital"))

        mcap = price * shares if (price and shares) else None
        ev   = (mcap + (debt or 0) - (cash or 0)) if mcap else None

        # ROIC
        roic = None
        if ebit is not None and ic and ic != 0:
            if tax is not None and pretax and pretax != 0:
                eff_tax = max(0.0, min(abs(tax / pretax), 0.50))
            else:
                eff_tax = 0.21
            roic = round(ebit * (1 - eff_tax) / ic, 4)

        # Operating Leverage (TTM vs 전년TTM)
        prev_rev  = _f(r.get("prev_revenue"))
        prev_ebit = _f(r.get("prev_ebit"))
        op_lev = None
        if all(v is not None for v in [ebit, prev_ebit, rev, prev_rev]):
            if prev_ebit != 0 and prev_rev != 0:
                d_ebit = (ebit - prev_ebit) / abs(prev_ebit)
                d_rev  = (rev  - prev_rev)  / abs(prev_rev)
                if d_rev != 0:
                    op_lev = round(d_ebit / d_rev, 4)

        net_debt = ((debt or 0) - (cash or 0)) if debt is not None else None

        row_calc = {
            "stock_id":            r["stock_id"],
            "roic":                roic,
            "gpa":                 round(gp / ta, 4) if (gp and ta and ta != 0) else None,
            "fcf_margin":          round(fcf / rev, 4) if (fcf is not None and rev and rev != 0) else None,
            "ev_ebit":             round(ev / ebit, 2) if (ev and ebit and ebit != 0) else None,
            "ev_fcf":              round(ev / fcf, 2) if (ev and fcf and fcf != 0) else None,
            "pb_ratio":            round(mcap / equity, 2) if (mcap and equity and equity != 0) else None,
            "peg_ratio":           None,  # PEG는 성장률 필요 → 별도
            "net_debt_ebitda":     round(net_debt / ebitda, 4) if (net_debt is not None and ebitda and ebitda != 0) else None,
            "operating_leverage":  op_lev,
            "low_vol":             _f(r.get("low_vol")),
            "eps_cv_3y":           _f(r.get("eps_cv_3y")),
        }

        # PEG
        if mcap and ni and ni > 0:
            per = mcap / ni
            prev_ni_approx = None
            if prev_rev and rev and rev != 0:
                # 근사: 전년 NI ≈ 현재 NI × (전년 Rev / 현재 Rev)
                pass
            # PEG는 복잡하므로 batch에서 계산된 peg_ratio를 따로 참조하기 어려움
            # → percentile 계산에서 제외하지 않고 None 유지

        rows.append(row_calc)

    return sector_id, rows


def _calc_percentiles_for_stock(target: dict, rows: list, sector_id) -> dict:
    """단일 종목의 백분위를 계산"""
    roic_vals   = [r["roic"]               for r in rows]
    gpa_vals    = [r["gpa"]                for r in rows]
    fcf_vals    = [r["fcf_margin"]         for r in rows]
    eveb_vals   = [r["ev_ebit"]            for r in rows]
    evfc_vals   = [r["ev_fcf"]             for r in rows]
    pb_vals     = [r["pb_ratio"]           for r in rows]
    peg_vals    = [r["peg_ratio"]          for r in rows]
    nde_vals    = [r["net_debt_ebitda"]    for r in rows]
    vol_vals    = [r["low_vol"]            for r in rows]
    oplev_vals  = [r["operating_leverage"] for r in rows]
    eps_cv_vals = [r["eps_cv_3y"]          for r in rows]

    return {
        "sector_id":                    sector_id,
        "roic_percentile":              _pct(roic_vals,   target["roic"]),
        "gpa_percentile":               _pct(gpa_vals,    target["gpa"]),
        "fcf_margin_percentile":        _pct(fcf_vals,    target["fcf_margin"]),
        "ev_ebit_percentile":           _pct_inv(eveb_vals,  target["ev_ebit"]),
        "ev_fcf_percentile":            _pct_inv(evfc_vals,  target["ev_fcf"]),
        "pb_percentile":                _pct_inv(pb_vals,    target["pb_ratio"]),
        "peg_percentile":               _pct_inv(peg_vals,   target["peg_ratio"]),
        "net_debt_ebitda_percentile":   _pct_inv(nde_vals,   target["net_debt_ebitda"]),
        "low_vol_percentile":           _pct_inv(vol_vals,   target["low_vol"]),
        "eps_stability_percentile":     _pct_inv(eps_cv_vals, target["eps_cv_3y"]),
        "op_leverage_percentile":       _pct(oplev_vals,  target["operating_leverage"]),
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 기존 호환 함수 (단일 종목용)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def calc_sector_percentiles(stock_id: int, sector_code: str) -> dict:
    """단일 종목의 섹터 내 백분위 계산 (기존 인터페이스 호환)."""
    sector_id, rows = _get_sector_rows_ttm(sector_code)
    if not rows:
        return {}

    target = next((r for r in rows if r["stock_id"] == stock_id), None)
    if not target:
        return {}

    return _calc_percentiles_for_stock(target, rows, sector_id)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ★ 벌크 함수 (섹터당 1회 조회)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def calc_sector_percentiles_bulk(sector_code: str) -> dict:
    """
    섹터 내 모든 종목의 백분위를 한 번에 계산.
    Returns: {stock_id: {roic_percentile: ..., ...}, ...}
    """
    sector_id, rows = _get_sector_rows_ttm(sector_code)
    if not rows:
        return {}

    result = {}
    for target in rows:
        sid = target["stock_id"]
        result[sid] = _calc_percentiles_for_stock(target, rows, sector_id)

    return result