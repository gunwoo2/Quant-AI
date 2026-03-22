"""
batch/calculator.py — Layer 1 점수 계산 v3.1 (Step 3: 품질 게이트 추가)
========================================================================
Step 1: **kwargs (sector_code 흡수)
Step 2: scoring_engine 연동, scipy 제거
Step 3: 입력 데이터 품질 검증 (_validate_inputs → _data_quality)
"""
import numpy as np
from decimal import Decimal


# ═══════════════════════════════════════════════════════════
# scoring_engine 선택적 import
# ═══════════════════════════════════════════════════════════

_HAS_SE = False
try:
    from utils.scoring_engine import sigmoid_score as _se_sigmoid
    from utils.scoring_engine import inverse_sigmoid_score as _se_inverse
    from utils.scoring_engine import zscore_to_sigmoid as _se_zscore
    from utils.scoring_engine import linear_interp_score as _se_linear
    _HAS_SE = True
except ImportError:
    pass


# ═══════════════════════════════════════════════════════════
# 헬퍼
# ═══════════════════════════════════════════════════════════

def _f(v):
    if v is None: return None
    try: return float(v)
    except: return None


# ═══════════════════════════════════════════════════════════
# 데이터 품질 검증 (Step 3)
# ═══════════════════════════════════════════════════════════

_VALID_RANGES = {
    "roic":           (-0.5, 2.0),
    "gpa":            (-0.5, 3.0),
    "fcf_margin":     (-2.0, 1.0),
    "ev_ebit":        (-50, 500),
    "ev_fcf":         (-50, 500),
    "pb":             (-5, 200),
    "eps_diluted":    (-100, 500),
    "net_debt_ebitda":(-10, 50),
    "asset_growth":   (-0.5, 3.0),
    "asset_turnover": (0, 10),
    "accruals_quality":(-1, 1),
    "dividend_yield": (0, 0.3),
}

def _validate_inputs(fin: dict, pct: dict) -> dict:
    """입력 데이터 품질 검증 → quality_score(0~1) + flags"""
    flags = []
    missing_count = 0

    critical = ["roic", "ev_ebit", "fcf_margin", "eps_diluted", "revenue"]
    for field in critical:
        if fin.get(field) is None:
            missing_count += 1
            flags.append(f"MISSING:{field}")

    for field, (lo, hi) in _VALID_RANGES.items():
        val = _f(fin.get(field))
        if val is not None and (val < lo or val > hi):
            flags.append(f"OUTLIER:{field}={val:.2f}")

    pct_fields = ["roic_percentile", "gpa_percentile", "fcf_margin_percentile",
                  "ev_ebit_percentile", "ev_fcf_percentile", "pb_percentile"]
    pct_ok = sum(1 for f in pct_fields if pct.get(f) is not None)
    if pct_ok < len(pct_fields):
        flags.append(f"PCT_MISSING:{len(pct_fields)-pct_ok}/{len(pct_fields)}")

    outlier_count = sum(1 for f in flags if "OUTLIER" in f)
    penalty = missing_count * 0.15 + outlier_count * 0.05
    quality_score = max(0.0, min(1.0, 1.0 - penalty))

    return {
        "quality_score": round(quality_score, 2),
        "flags": flags,
        "missing_count": missing_count,
        "pct_coverage": f"{pct_ok}/{len(pct_fields)}",
    }


# ═══════════════════════════════════════════════════════════
# 코어 스코어링 함수
# ═══════════════════════════════════════════════════════════

def sigmoid_score(percentile, max_points, steepness=10.0, midpoint=50.0):
    if _HAS_SE: return _se_sigmoid(percentile, max_points, steepness, midpoint)
    if percentile is None: return 0.0
    pct = max(0.0, min(100.0, float(percentile)))
    x = steepness * (pct - midpoint) / 100.0
    sigma = 1.0 / (1.0 + np.exp(-x))
    sig_min = 1.0 / (1.0 + np.exp(steepness * midpoint / 100.0))
    sig_max = 1.0 / (1.0 + np.exp(-steepness * (100.0 - midpoint) / 100.0))
    denom = sig_max - sig_min
    if denom < 1e-10: return 0.0
    return round(max(0.0, min(1.0, (sigma - sig_min) / denom)) * max_points, 2)

def inverse_sigmoid_score(percentile, max_points, steepness=10.0, midpoint=50.0):
    if _HAS_SE: return round(max_points - _se_sigmoid(percentile, max_points, steepness, midpoint), 2)
    return round(max_points - sigmoid_score(percentile, max_points, steepness, midpoint), 2)

def zscore_to_sigmoid(value, mean, std, max_points, steepness=10.0):
    if _HAS_SE: return _se_zscore(value, mean, std, max_points, steepness)
    if value is None or mean is None or std is None: return max_points * 0.5
    if std == 0 or std < 1e-10: return max_points * 0.5
    fval, fmean, fstd = float(value), float(mean), float(std)
    if np.isnan(fval) or np.isinf(fval) or np.isnan(fmean) or np.isinf(fmean):
        return max_points * 0.5
    z = (fval - fmean) / fstd
    pct = 100.0 / (1.0 + np.exp(-1.7 * z))
    return sigmoid_score(pct, max_points, steepness)

def linear_interp_score(raw_val, max_raw, max_points, floor=0.0):
    if _HAS_SE: return _se_linear(raw_val, max_raw, max_points, floor)
    if raw_val is None: return floor
    ratio = max(0.0, min(1.0, float(raw_val) / float(max_raw)))
    return round(floor + (max_points - floor) * ratio, 2)

def percentile_to_points(pct, max_points):
    if pct is None: return 0.0
    return sigmoid_score(float(pct), max_points)

def calc_asset_growth_score(ag_val, max_points=10.0):
    if ag_val is None: return 5.0
    return round(max_points - zscore_to_sigmoid(ag_val, 0.08, 0.15, max_points), 2)

def calc_shareholder_yield_score(div_yield=None, buyback_yield=None,
                                  debt_paydown_yield=None, shy_percentile=None, max_points=25.0):
    d = float(div_yield or 0); b = float(buyback_yield or 0); dp = float(debt_paydown_yield or 0)
    shy_raw = round(d + b + dp, 4)
    if shy_percentile is not None: score = sigmoid_score(float(shy_percentile), max_points)
    else: score = zscore_to_sigmoid(shy_raw, 0.03, 0.04, max_points)
    return round(score, 2), shy_raw


# ═══════════════════════════════════════════════════════════
# MOAT (35%)
# ═══════════════════════════════════════════════════════════

def calc_moat_scores(fin: dict, pct: dict, **kwargs) -> dict:
    dq = _validate_inputs(fin, pct)

    roic_score = sigmoid_score(_f(pct.get("roic_percentile")), 25)
    gpa_score  = sigmoid_score(_f(pct.get("gpa_percentile")),  20)
    fcf_score  = sigmoid_score(_f(pct.get("fcf_margin_percentile")), 15)
    nde_score  = sigmoid_score(_f(pct.get("net_debt_ebitda_percentile")), 10)

    accruals_pct = _f(pct.get("accruals_percentile"))
    if accruals_pct is not None:
        accruals_score = inverse_sigmoid_score(accruals_pct, 10)
    else:
        accruals_val = _f(fin.get("accruals_quality"))
        if accruals_val is not None:
            accruals_score = round(10.0 - zscore_to_sigmoid(accruals_val, 0.02, 0.05, 10.0), 2)
        else:
            accruals_score = 5.0

    ag_score = calc_asset_growth_score(_f(fin.get("asset_growth")), 10.0)
    fin_prev = kwargs.get("fin_prev", {})
    f_raw = _calc_f_score(fin, fin_prev) if fin_prev else 0
    f_pts = linear_interp_score(f_raw, 9, 10.0, 1.0)

    total = round(roic_score + gpa_score + fcf_score + accruals_score + nde_score + ag_score + f_pts, 2)

    return {
        "roic_score": roic_score, "gpa_score": gpa_score,
        "fcf_margin_score": fcf_score, "accruals_quality_score": round(accruals_score, 2),
        "net_debt_ebitda_score": nde_score, "total_moat_score": total,
        "asset_growth_score": round(ag_score, 2), "f_score_points": round(f_pts, 2),
        "_data_quality": dq,
    }


# ═══════════════════════════════════════════════════════════
# VALUE (25%)
# ═══════════════════════════════════════════════════════════

def calc_value_scores(fin: dict, pct: dict, **kwargs) -> dict:
    ey_score  = sigmoid_score(_f(pct.get("ev_ebit_percentile")), 30)
    evf_score = sigmoid_score(_f(pct.get("ev_fcf_percentile")),  25)
    pb_score  = sigmoid_score(_f(pct.get("pb_percentile")),      20)
    shy_score, shy_raw = calc_shareholder_yield_score(
        div_yield=_f(fin.get("dividend_yield")), buyback_yield=_f(fin.get("buyback_yield")),
        debt_paydown_yield=_f(fin.get("debt_paydown_yield")),
        shy_percentile=_f(pct.get("shy_percentile")), max_points=25.0)
    total = round(ey_score + evf_score + pb_score + shy_score, 2)
    return {
        "earnings_yield_score": ey_score, "ev_fcf_score": evf_score,
        "pb_score": pb_score, "peg_score": 0.0, "total_value_score": total,
        "shy_score": round(shy_score, 2), "shy_raw": shy_raw,
    }


# ═══════════════════════════════════════════════════════════
# MOMENTUM (25%)
# ═══════════════════════════════════════════════════════════

def calc_momentum_scores(fin: dict, fin_prev: dict, pct: dict,
                         qtr_eps_hist: list = None, **kwargs) -> dict:
    surprise_pct, surprise_score = None, 15.0
    if qtr_eps_hist and len(qtr_eps_hist) >= 5:
        le, ye = _f(qtr_eps_hist[0]), _f(qtr_eps_hist[4])
        if le is not None and ye is not None and ye != 0:
            surprise_pct = round((le - ye) / abs(ye), 4)
            surprise_score = zscore_to_sigmoid(surprise_pct, 0.05, 0.20, 30.0)

    revision_ratio, revision_score = None, 10.0
    if qtr_eps_hist and len(qtr_eps_hist) >= 4:
        changes = []
        for i in range(min(3, len(qtr_eps_hist) - 1)):
            c, p = _f(qtr_eps_hist[i]), _f(qtr_eps_hist[i+1])
            if c is not None and p is not None and p != 0:
                changes.append((c - p) / abs(p))
        if changes:
            revision_ratio = round(sum(changes)/len(changes), 4)
            revision_score = zscore_to_sigmoid(revision_ratio, 0.02, 0.15, 20.0)

    ato_cur, ato_prev = _f(fin.get("asset_turnover")), _f((fin_prev or {}).get("asset_turnover"))
    if ato_cur is not None and ato_prev is not None:
        ato_score = zscore_to_sigmoid(round(ato_cur - ato_prev, 4), 0.0, 0.05, 20.0)
    else:
        ato_score = 10.0

    op_lev = _f(fin.get("operating_leverage"))
    oplev_score = zscore_to_sigmoid(op_lev, 1.0, 1.5, 15.0) if op_lev is not None else sigmoid_score(_f(pct.get("op_leverage_percentile")), 15)

    trend_score = 7.5
    if qtr_eps_hist and len(qtr_eps_hist) >= 4:
        arr = [_f(e) for e in qtr_eps_hist[:4] if _f(e) is not None]
        if len(arr) >= 4:
            x, y = np.arange(4), np.array(list(reversed(arr)))
            if np.std(y) > 0:
                corr = float(np.corrcoef(x, y)[0, 1])
                trend_score = sigmoid_score((corr*abs(corr)+1)/2*100, 15.0)

    total = round(surprise_score + revision_score + ato_score + oplev_score + trend_score, 2)
    return {
        "f_score_raw": 0, "f_score_points": 0.0,
        "earnings_surprise_pct": surprise_pct, "earnings_surprise_score": round(surprise_score, 2),
        "earnings_revision_ratio": revision_ratio, "earnings_revision_score": round(revision_score, 2),
        "ato_acceleration_score": round(ato_score, 2), "op_leverage_score": round(oplev_score, 2),
        "total_momentum_score": total, "eps_trend_score": round(trend_score, 2),
    }


# ═══════════════════════════════════════════════════════════
# F-Score
# ═══════════════════════════════════════════════════════════

def _calc_f_score(fin, fin_prev):
    s = 0; p = fin_prev or {}
    ni,ocf,ta = _f(fin.get("net_income")),_f(fin.get("operating_cash_flow")),_f(fin.get("total_assets"))
    debt,eq,rev,ebit = _f(fin.get("total_debt")),_f(fin.get("total_equity")),_f(fin.get("revenue")),_f(fin.get("ebit"))
    pni,pta,pde,peq = _f(p.get("net_income")),_f(p.get("total_assets")),_f(p.get("total_debt")),_f(p.get("total_equity"))
    prev_rev,prev_ebit = _f(p.get("revenue")),_f(p.get("ebit"))
    if ni and ta and ta!=0 and ni/ta>0: s+=1
    if ocf and ocf>0: s+=1
    if ni and ta and pni and pta and ta!=0 and pta!=0 and ni/ta>pni/pta: s+=1
    if ocf and ni and ocf>ni: s+=1
    if debt and eq and pde and peq and eq!=0 and peq!=0 and debt/eq<pde/peq: s+=1
    if rev and prev_rev and prev_rev!=0 and rev>prev_rev: s+=1
    if eq and peq and eq<=peq*1.05: s+=1
    if ebit and rev and prev_ebit and prev_rev and rev!=0 and prev_rev!=0 and ebit/rev>prev_ebit/prev_rev: s+=1
    if rev and ta and prev_rev and pta and ta!=0 and pta!=0 and rev/ta>prev_rev/pta: s+=1
    return s


# ═══════════════════════════════════════════════════════════
# STABILITY (15%)
# ═══════════════════════════════════════════════════════════

def calc_stability_scores(price_df, eps_history, dividend_years, pct, **kwargs):
    import pandas as pd
    eps_cv, es_score = None, 15.0
    if eps_history and len(eps_history) >= 2:
        arr = [e for e in eps_history if e is not None]
        if len(arr) >= 2:
            m = float(np.mean(arr))
            if m != 0:
                eps_cv = round(float(np.std(arr)/abs(m)), 4)
                es_score = round(30.0 - zscore_to_sigmoid(eps_cv, 0.25, 0.20, 30.0), 2)
            else: eps_cv, es_score = 999.0, 0.0

    vol_s, annual_vol = 0.0, None
    if price_df is not None and len(price_df) >= 60:
        try:
            c = price_df["close_price"].dropna().astype(float)
            if len(c) >= 60:
                annual_vol = round(float(c.pct_change().dropna().std()*np.sqrt(252)), 4)
                vol_s = round(25.0 - zscore_to_sigmoid(annual_vol, 0.28, 0.12, 25.0), 2)
        except: pass

    mdd_s = 0.0
    if price_df is not None and len(price_df) >= 60:
        try:
            c = price_df["close_price"].dropna().astype(float)
            if len(c) >= 60:
                peak = c.expanding().max(); dd = (c-peak)/peak
                mdd_s = round(25.0 - zscore_to_sigmoid(abs(float(dd.min())), 0.30, 0.15, 25.0), 2)
        except: pass

    div_s = round(min(float(dividend_years or 0), 25.0)/25.0*20.0, 2)
    low_vol = round(vol_s + mdd_s, 2)
    total = round(es_score + low_vol + div_s, 2)
    return {
        "annualized_volatility_250d": annual_vol, "low_vol_score": low_vol,
        "eps_cv_3y": eps_cv, "earnings_stability_score": round(es_score, 2),
        "dividend_consecutive_years": dividend_years, "dividend_consistency_score": div_s,
        "total_stability_score": total,
    }


# ═══════════════════════════════════════════════════════════
# LAYER 1 총점
# ═══════════════════════════════════════════════════════════

def calc_layer1_score(moat, value, momentum, stability, pct, **kwargs):
    rm = float(moat.get("total_moat_score",0) or 0)
    rv = float(value.get("total_value_score",0) or 0)
    rmm = float(momentum.get("total_momentum_score",0) or 0)
    rs = float(stability.get("total_stability_score",0) or 0)
    total = round(rm*0.35 + rv*0.25 + rmm*0.25 + rs*0.15, 2)
    dq = moat.get("_data_quality", {})
    return {
        "moat_score": round(rm,2), "value_score": round(rv,2),
        "momentum_score": round(rmm,2), "stability_score": round(rs,2),
        "layer1_raw_score": total, "layer1_score": total,
        "sector_percentile_rank": _f(pct.get("overall_percentile")),
        "total_score_adj": total, "_data_quality": dq,
    }

