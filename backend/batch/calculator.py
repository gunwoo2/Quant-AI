"""
Layer 1 각 섹션별 점수 계산 함수 (설계서 2.2 기준).
모든 입력값은 _f() 헬퍼로 float 변환 후 사용.
"""
import numpy as np
from decimal import Decimal


def _f(v):
    """Decimal, np.float64, str 등 모두 float으로 안전 변환"""
    if v is None:
        return None
    try:
        return float(v)
    except Exception:
        return None


def percentile_to_points(pct: float, max_points: float) -> float:
    """
    섹터 내 백분위 → 점수 변환 (설계서 2.1)
    Top 10%→만점 / Top 30%→80% / Top 50%→60% / Top 70%→40% / Bottom 30%→0
    """
    if pct is None:
        return 0.0
    pct = float(pct)
    if pct >= 90:   return float(max_points)
    if pct >= 70:   return round(max_points * 0.80, 2)
    if pct >= 50:   return round(max_points * 0.60, 2)
    if pct >= 30:   return round(max_points * 0.40, 2)
    return 0.0


# ── MOAT (35%) ──────────────────────────────────────────
def calc_moat_scores(fin: dict, pct: dict) -> dict:
    roic_score = percentile_to_points(_f(pct.get("roic_percentile")), 30)
    gpa_score  = percentile_to_points(_f(pct.get("gpa_percentile")),  25)
    fcf_score  = percentile_to_points(_f(pct.get("fcf_margin_percentile")), 20)

    accruals = _f(fin.get("accruals_quality"))
    if accruals is None:      accruals_score = 0.0
    elif accruals <= -0.05:   accruals_score = 15.0
    elif accruals <= 0.0:     accruals_score = 11.0
    elif accruals <= 0.05:    accruals_score = 7.0
    elif accruals <= 0.10:    accruals_score = 3.0
    else:                     accruals_score = 0.0

    nde_score = percentile_to_points(_f(pct.get("net_debt_ebitda_percentile")), 10)
    total = round(roic_score + gpa_score + fcf_score + accruals_score + nde_score, 2)

    return {
        "roic_score":             roic_score,
        "gpa_score":              gpa_score,
        "fcf_margin_score":       fcf_score,
        "accruals_quality_score": accruals_score,
        "net_debt_ebitda_score":  nde_score,
        "total_moat_score":       total,
    }


# ── VALUE (25%) ─────────────────────────────────────────
def calc_value_scores(fin: dict, pct: dict) -> dict:
    ey_score  = percentile_to_points(_f(pct.get("ev_ebit_percentile")), 35)
    evf_score = percentile_to_points(_f(pct.get("ev_fcf_percentile")),  30)
    pb_score  = percentile_to_points(_f(pct.get("pb_percentile")),      20)
    peg_score = percentile_to_points(_f(pct.get("peg_percentile")),     15)
    total = round(ey_score + evf_score + pb_score + peg_score, 2)

    return {
        "earnings_yield_score": ey_score,
        "ev_fcf_score":         evf_score,
        "pb_score":             pb_score,
        "peg_score":            peg_score,
        "total_value_score":    total,
    }


# ── MOMENTUM (25%) ──────────────────────────────────────
def calc_momentum_scores(fin: dict, fin_prev: dict, pct: dict) -> dict:
    f_raw = _calc_f_score(fin, fin_prev)
    if f_raw >= 8:    f_pts = 30.0
    elif f_raw >= 6:  f_pts = 22.0
    elif f_raw >= 4:  f_pts = 14.0
    elif f_raw >= 2:  f_pts = 6.0
    else:             f_pts = 0.0

    ato_cur  = _f(fin.get("asset_turnover"))
    ato_prev = _f((fin_prev or {}).get("asset_turnover"))
    ato_accel = None
    if ato_cur is not None and ato_prev is not None:
        ato_accel = round(ato_cur - ato_prev, 4)
        if ato_accel > 0.05:     ato_score = 20.0
        elif ato_accel > 0.02:   ato_score = 15.0
        elif ato_accel > 0:      ato_score = 10.0
        elif ato_accel > -0.02:  ato_score = 5.0
        else:                    ato_score = 0.0
    else:
        ato_score = 0.0

    oplev_score = percentile_to_points(_f(pct.get("op_leverage_percentile")), 15)
    total = round(f_pts + ato_score + oplev_score, 2)

    return {
        "f_score_raw":             f_raw,
        "f_score_points":          f_pts,
        "earnings_revision_ratio": None,
        "earnings_revision_score": 0.0,
        "ato_acceleration_score":  ato_score,
        "op_leverage_score":       oplev_score,
        "earnings_surprise_pct":   None,
        "earnings_surprise_score": 0.0,
        "total_momentum_score":    total,
    }


def _calc_f_score(fin: dict, fin_prev: dict) -> int:
    """Piotroski F-Score 9개 이진 지표"""
    score = 0
    prev  = fin_prev or {}

    net   = _f(fin.get("net_income"))
    ta    = _f(fin.get("total_assets"))
    ocf   = _f(fin.get("operating_cash_flow"))
    debt  = _f(fin.get("total_debt"))
    gpa   = _f(fin.get("gpa"))
    ato   = _f(fin.get("asset_turnover"))

    p_net  = _f(prev.get("net_income"))
    p_ta   = _f(prev.get("total_assets"))
    p_debt = _f(prev.get("total_debt"))
    p_gpa  = _f(prev.get("gpa"))
    p_ato  = _f(prev.get("asset_turnover"))

    # 수익성
    roa = net / ta if (net is not None and ta and ta != 0) else None
    if roa is not None and roa > 0:  score += 1
    if ocf is not None and ocf > 0:  score += 1

    p_roa = p_net / p_ta if (p_net is not None and p_ta and p_ta != 0) else None
    if roa is not None and p_roa is not None and roa > p_roa:  score += 1
    if roa is not None and ocf is not None and ta and ta != 0:
        if ocf / ta > net / ta:  score += 1

    # 레버리지
    if debt is not None and p_debt is not None and debt < p_debt:  score += 1

    # 운영 효율
    if ato is not None and p_ato is not None and ato > p_ato:   score += 1
    if gpa is not None and p_gpa  is not None and gpa > p_gpa:  score += 1

    return score


# ── STABILITY (15%) ─────────────────────────────────────
def calc_stability_scores(price_df, eps_history: list,
                           dividend_years: int, pct: dict) -> dict:
    # 250일 연간화 변동성
    annual_vol = None
    if price_df is not None and len(price_df) >= 30:
        try:
            closes  = price_df["close_price"].astype(float)
            returns = closes.pct_change().dropna()
            if len(returns) >= 30:
                annual_vol = round(float(returns.std() * np.sqrt(252)), 4)
        except Exception:
            pass

    low_vol_score = percentile_to_points(_f(pct.get("low_vol_percentile")), 40)

    # 3년 EPS CV
    eps_cv = None
    clean_eps = [_f(e) for e in (eps_history or []) if e is not None]
    if len(clean_eps) >= 3:
        mu = np.mean(clean_eps)
        if abs(mu) > 0.01:
            eps_cv = round(float(np.std(clean_eps) / abs(mu)), 4)

    eps_stability_score = percentile_to_points(
        _f(pct.get("eps_stability_percentile")) or 50, 35
    )

    # 배당 일관성
    dy = dividend_years or 0
    if dy >= 10:    div_score = 25.0
    elif dy >= 5:   div_score = 18.0
    elif dy >= 3:   div_score = 10.0
    elif dy >= 1:   div_score = 5.0
    else:           div_score = 0.0

    total = round(low_vol_score + eps_stability_score + div_score, 2)

    return {
        "annualized_volatility_250d": annual_vol,
        "low_vol_score":              low_vol_score,
        "eps_cv_3y":                  eps_cv,
        "earnings_stability_score":   eps_stability_score,
        "dividend_consecutive_years": dy,
        "dividend_consistency_score": div_score,
        "total_stability_score":      total,
    }


# ── Layer 1 최종 통합 ────────────────────────────────────
def calc_layer1_score(moat: dict, value: dict, momentum: dict,
                      stability: dict, pct: dict) -> dict:
    moat_w      = round(moat["total_moat_score"]          * 0.35, 2)
    value_w     = round(value["total_value_score"]        * 0.25, 2)
    momentum_w  = round(momentum["total_momentum_score"]  * 0.25, 2)
    stability_w = round(stability["total_stability_score"] * 0.15, 2)

    raw = round(moat_w + value_w + momentum_w + stability_w, 2)

    sector_pct = _f(pct.get("roic_percentile")) or 50.0
    adj   = round((sector_pct - 50) / 50 * 5, 2)
    final = round(min(100.0, max(0.0, raw + adj)), 2)

    return {
        "moat_score":             moat_w,
        "value_score":            value_w,
        "momentum_score":         momentum_w,
        "stability_score":        stability_w,
        "layer1_raw_score":       raw,
        "layer1_score":           final,
        "sector_percentile_rank": sector_pct,
        "total_score_adj":        final,
    }