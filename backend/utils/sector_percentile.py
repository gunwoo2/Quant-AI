import numpy as np
from db_pool import get_cursor


def calc_sector_percentiles(stock_id: int, sector_code: str) -> dict:
    """
    섹터 내 백분위 계산 (설계서 2.1 Sector Neutralization).
    stock_financials 최신 ANNUAL 기준으로 섹터 내 모든 종목과 비교.
    """
    sql = """
        SELECT
            s.stock_id,
            fin.roic,
            fin.gpa,
            fin.fcf_margin,
            fin.ev_ebit,
            fin.ev_fcf,
            fin.pb_ratio,
            fin.peg_ratio,
            fin.net_debt_ebitda,
            stab.annualized_volatility_250d AS low_vol,
            fin.operating_leverage
        FROM stocks s
        JOIN sectors sec ON s.sector_id = sec.sector_id
        LEFT JOIN (
            SELECT DISTINCT ON (stock_id)
                stock_id, roic, gpa, fcf_margin,
                ev_ebit, ev_fcf, pb_ratio, peg_ratio,
                net_debt_ebitda, operating_leverage
            FROM stock_financials
            WHERE report_type = 'ANNUAL'
            ORDER BY stock_id, fiscal_year DESC
        ) fin ON s.stock_id = fin.stock_id
        LEFT JOIN (
            SELECT DISTINCT ON (stock_id)
                stock_id, annualized_volatility_250d
            FROM quant_stability_scores
            ORDER BY stock_id, calc_date DESC
        ) stab ON s.stock_id = stab.stock_id
        WHERE sec.sector_code = %s
          AND s.is_active = TRUE
    """

    with get_cursor() as cur:
        # 1. sector_id 가져오기
        cur.execute(
            "SELECT sector_id FROM sectors WHERE sector_code = %s LIMIT 1",
            (sector_code,)
        )
        sec_row = cur.fetchone()
        sector_id = sec_row["sector_id"] if sec_row else None

        # 2. 위에 작성해둔 sql 실행해서 rows 데이터 가져오기 (★이 부분이 빠져있었습니다!)
        cur.execute(sql, (sector_code,))
        db_rows = cur.fetchall()

    if not db_rows:
        return {}

    rows = [dict(r) for r in db_rows]

    def _pct(values: list, target_val):
        """target_val이 섹터 내 몇 %ile인지 계산"""
        if target_val is None:
            return None
        clean = [v for v in values if v is not None]
        if not clean:
            return None
        arr = np.array(clean, dtype=float)
        return float(np.sum(arr <= float(target_val)) / len(arr) * 100)

    def _pct_inv(values: list, target_val):
        """낮을수록 좋은 지표 (EV/EBIT, Volatility): 역백분위"""
        if target_val is None:
            return None
        clean = [v for v in values if v is not None]
        if not clean:
            return None
        arr = np.array(clean, dtype=float)
        return float(np.sum(arr >= float(target_val)) / len(arr) * 100)

    target = next((r for r in rows if r["stock_id"] == stock_id), None)
    if not target:
        return {}
    
    roic_vals   = [r["roic"]          for r in rows]
    gpa_vals    = [r["gpa"]           for r in rows]
    fcf_vals    = [r["fcf_margin"]    for r in rows]
    eveb_vals   = [r["ev_ebit"]       for r in rows]
    evfc_vals   = [r["ev_fcf"]        for r in rows]
    pb_vals     = [r["pb_ratio"]      for r in rows]
    peg_vals    = [r["peg_ratio"]     for r in rows]
    nde_vals    = [r["net_debt_ebitda"] for r in rows]
    vol_vals    = [r["low_vol"]       for r in rows]
    oplev_vals  = [r["operating_leverage"] for r in rows]
    eps_vals    = [r["gpa"]           for r in rows]  # EPS stability → 배치에서 계산

    return {
        "sector_id":                    sector_id,   # ← 추가
        "roic_percentile":          _pct(roic_vals,   target["roic"]),
        "gpa_percentile":           _pct(gpa_vals,    target["gpa"]),
        "fcf_margin_percentile":    _pct(fcf_vals,    target["fcf_margin"]),
        "ev_ebit_percentile":       _pct_inv(eveb_vals, target["ev_ebit"]),  # 낮을수록 좋음
        "ev_fcf_percentile":        _pct_inv(evfc_vals, target["ev_fcf"]),
        "pb_percentile":            _pct_inv(pb_vals,  target["pb_ratio"]),
        "peg_percentile":           _pct_inv(peg_vals, target["peg_ratio"]),
        "net_debt_ebitda_percentile": _pct_inv(nde_vals, target["net_debt_ebitda"]),
        "low_vol_percentile":       _pct_inv(vol_vals, target["low_vol"]),  # 낮을수록 좋음
        "op_leverage_percentile":   _pct(oplev_vals,  target["operating_leverage"]),
        "eps_stability_percentile": None,  # quant_stability_scores 계산 후 업데이트
    }