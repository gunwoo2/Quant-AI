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
def calc_momentum_scores(fin: dict, fin_prev: dict, pct: dict,
                         qtr_eps_hist: list = None) -> dict:
    """
    모멘텀 점수 계산.
    
    qtr_eps_hist: 분기 eps_actual 리스트 (최신순, 최대 8분기)
      예: [Q4_2025, Q3_2025, Q2_2025, Q1_2025, Q4_2024, Q3_2024, ...]
    
    Earnings Surprise:
      최신 분기 eps vs 전년 동기 eps (YoY 서프라이즈)
      surprise_pct = (eps[0] - eps[4]) / |eps[4]|
      
    Earnings Revision (EPS 추세):
      최근 4분기 순차적 eps 변화율 평균 (상향/하향 추세)
      revision_ratio = mean of ((eps[i] - eps[i+1]) / |eps[i+1]|) for i=0..2
    """
    f_raw = _calc_f_score(fin, fin_prev)
    if f_raw >= 8:    f_pts = 30.0
    elif f_raw >= 6:  f_pts = 22.0
    elif f_raw >= 4:  f_pts = 14.0
    elif f_raw >= 2:  f_pts = 6.0
    else:             f_pts = 0.0

    # ── ATO Acceleration ──
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

    # ── Operating Leverage (절대값 기준) ──
    # 공식: OpIncome Growth Rate / Revenue Growth Rate
    op_lev_val = _f(fin.get("operating_leverage"))
    if op_lev_val is not None:
        if op_lev_val >= 2.0:      oplev_score = 15.0
        elif op_lev_val >= 1.5:    oplev_score = 12.0
        elif op_lev_val >= 1.0:    oplev_score = 9.0
        elif op_lev_val >= 0.5:    oplev_score = 6.0
        elif op_lev_val >= 0:      oplev_score = 3.0
        else:                      oplev_score = 0.0
    else:
        oplev_score = percentile_to_points(_f(pct.get("op_leverage_percentile")), 15)
        

    # ── Earnings Surprise (YoY 분기 비교) ──
    surprise_pct = None
    surprise_score = 0.0
    if qtr_eps_hist and len(qtr_eps_hist) >= 5:
        # qtr_eps_hist[0] = 최신분기, qtr_eps_hist[4] = 전년 동기
        latest_eps = _f(qtr_eps_hist[0])
        yoy_eps    = _f(qtr_eps_hist[4])
        if latest_eps is not None and yoy_eps is not None and yoy_eps != 0:
            surprise_pct = round((latest_eps - yoy_eps) / abs(yoy_eps), 4)
            if surprise_pct > 0.10:    surprise_score = 20.0
            elif surprise_pct > 0.05:  surprise_score = 15.0
            elif surprise_pct > 0:     surprise_score = 10.0
            elif surprise_pct > -0.05: surprise_score = 5.0
            else:                      surprise_score = 0.0

    # ── Earnings Revision (최근 분기 EPS 추세) ──
    revision_ratio = None
    revision_score = 0.0
    if qtr_eps_hist and len(qtr_eps_hist) >= 4:
        # 최근 3개 구간의 변화율 평균
        changes = []
        for i in range(min(3, len(qtr_eps_hist) - 1)):
            cur_eps  = _f(qtr_eps_hist[i])
            prev_eps = _f(qtr_eps_hist[i + 1])
            if cur_eps is not None and prev_eps is not None and prev_eps != 0:
                changes.append((cur_eps - prev_eps) / abs(prev_eps))
        
        if changes:
            revision_ratio = round(sum(changes) / len(changes), 4)
            if revision_ratio > 0.10:    revision_score = 20.0
            elif revision_ratio > 0.05:  revision_score = 15.0
            elif revision_ratio > 0:     revision_score = 10.0
            elif revision_ratio > -0.05: revision_score = 5.0
            else:                        revision_score = 0.0

    total = round(f_pts + ato_score + oplev_score
                  + surprise_score + revision_score, 2)

    return {
        "f_score_raw":             f_raw,
        "f_score_points":          f_pts,
        "earnings_revision_ratio": revision_ratio,
        "earnings_revision_score": revision_score,
        "ato_acceleration_score":  ato_score,
        "op_leverage_score":       oplev_score,
        "earnings_surprise_pct":   surprise_pct,
        "earnings_surprise_score": surprise_score,
        "total_momentum_score":    total,
    }


def _calc_f_score(fin: dict, fin_prev: dict) -> int:
    """Piotroski F-Score 9개 이진 지표"""
    score = 0
    prev  = fin_prev or {}

    ni  = _f(fin.get("net_income"))
    ocf = _f(fin.get("operating_cash_flow"))
    ta  = _f(fin.get("total_assets"))
    fcf = _f(fin.get("free_cash_flow"))
    debt   = _f(fin.get("total_debt"))
    equity = _f(fin.get("total_equity"))
    rev    = _f(fin.get("revenue"))
    ebit   = _f(fin.get("ebit"))

    prev_ni     = _f(prev.get("net_income"))
    prev_ocf    = _f(prev.get("operating_cash_flow"))
    prev_ta     = _f(prev.get("total_assets"))
    prev_debt   = _f(prev.get("total_debt"))
    prev_equity = _f(prev.get("total_equity"))
    prev_rev    = _f(prev.get("revenue"))
    prev_ebit   = _f(prev.get("ebit"))

    # 1. ROA > 0
    if ni and ta and ta != 0 and ni / ta > 0:
        score += 1
    # 2. OCF > 0
    if ocf and ocf > 0:
        score += 1
    # 3. ROA 증가
    if ni and ta and prev_ni and prev_ta and ta != 0 and prev_ta != 0:
        if ni / ta > prev_ni / prev_ta:
            score += 1
    # 4. OCF > NI (발생주의 품질)
    if ocf and ni and ocf > ni:
        score += 1
    # 5. 레버리지 감소 (부채비율)
    if debt and equity and prev_debt and prev_equity:
        if equity != 0 and prev_equity != 0:
            if debt / equity < prev_debt / prev_equity:
                score += 1
    # 6. 유동성 (간이: 매출 증가)
    if rev and prev_rev and prev_rev != 0:
        if rev > prev_rev:
            score += 1
    # 7. 신주발행 없음 (간이: 자본 변화 없음)
    if equity and prev_equity:
        if equity <= prev_equity * 1.05:
            score += 1
    # 8. 매출총이익률 증가
    if ebit and rev and prev_ebit and prev_rev:
        if rev != 0 and prev_rev != 0:
            if ebit / rev > prev_ebit / prev_rev:
                score += 1
    # 9. 자산회전율 증가
    if rev and ta and prev_rev and prev_ta:
        if ta != 0 and prev_ta != 0:
            if rev / ta > prev_rev / prev_ta:
                score += 1

    return score


# ── STABILITY (15%) ──────────────────────────────────────
def calc_stability_scores(price_df, eps_history: list,
                          dividend_years: int, pct: dict) -> dict:
    """
    설계서 2.2.4 안정성 섹션.
    price_df: trade_date, close_price 컬럼 DataFrame.
    eps_history: TTM EPS 시계열 (롤링 TTM, 최신→과거).
    dividend_years: 배당 지급 연수.
    """
    import pandas as pd

    # 1. 수익 안정성 (EPS CV 기반)
    eps_cv = None
    earnings_stab_score = 0.0
    if eps_history and len(eps_history) >= 2:
        arr = [e for e in eps_history if e is not None]
        if len(arr) >= 2:
            mean_val = np.mean(arr)
            eps_cv = round(float(np.std(arr) / abs(mean_val)), 4) if mean_val != 0 else 999.0
            if eps_cv < 0.15:     earnings_stab_score = 30.0
            elif eps_cv < 0.30:   earnings_stab_score = 22.0
            elif eps_cv < 0.50:   earnings_stab_score = 14.0
            elif eps_cv < 0.80:   earnings_stab_score = 6.0
            else:                 earnings_stab_score = 0.0

    # 2. 가격 변동성 (연 변동성)
    annual_vol = None
    vol_score = 0.0
    if price_df is not None and len(price_df) >= 60:
        try:
            closes = price_df["close_price"].dropna().astype(float)
            if len(closes) >= 60:
                rets = closes.pct_change().dropna()
                annual_vol = round(float(rets.std() * np.sqrt(252)), 4)
                if annual_vol < 0.20:   vol_score = 25.0
                elif annual_vol < 0.30: vol_score = 18.0
                elif annual_vol < 0.40: vol_score = 12.0
                elif annual_vol < 0.50: vol_score = 6.0
                else:                   vol_score = 0.0
        except Exception:
            vol_score = 0.0

    # 3. 최대 낙폭 (MDD)
    mdd_score = 0.0
    if price_df is not None and len(price_df) >= 60:
        try:
            closes = price_df["close_price"].dropna().astype(float)
            if len(closes) >= 60:
                peak   = closes.expanding().max()
                dd     = (closes - peak) / peak
                mdd    = float(dd.min())
                if mdd > -0.15:   mdd_score = 25.0
                elif mdd > -0.25: mdd_score = 18.0
                elif mdd > -0.35: mdd_score = 12.0
                elif mdd > -0.50: mdd_score = 6.0
                else:             mdd_score = 0.0
        except Exception:
            mdd_score = 0.0

    # 4. 배당 지속성
    if dividend_years >= 10:  div_score = 20.0
    elif dividend_years >= 5: div_score = 14.0
    elif dividend_years >= 3: div_score = 8.0
    elif dividend_years >= 1: div_score = 4.0
    else:                     div_score = 0.0

    low_vol_score = round(vol_score + mdd_score, 2)
    total = round(earnings_stab_score + low_vol_score + div_score, 2)

    return {
        "annualized_volatility_250d":  annual_vol,
        "low_vol_score":               low_vol_score,
        "eps_cv_3y":                   eps_cv,
        "earnings_stability_score":    earnings_stab_score,
        "dividend_consecutive_years":  dividend_years,
        "dividend_consistency_score":  div_score,
        "total_stability_score":       total,
    }



# ── LAYER 1 총점 ─────────────────────────────────────────
def calc_layer1_score(moat: dict, value: dict, momentum: dict,
                      stability: dict, pct: dict) -> dict:
    """설계서 2.3 Layer 1 총점 (MOAT 35 + VALUE 25 + MOMENTUM 25 + STABILITY 15)."""
    raw_moat  = moat.get("total_moat_score", 0) or 0
    raw_val   = value.get("total_value_score", 0) or 0
    raw_mom   = momentum.get("total_momentum_score", 0) or 0
    raw_stab  = stability.get("total_stability_score", 0) or 0

    total = round(raw_moat * 0.35 + raw_val * 0.25
                  + raw_mom * 0.25 + raw_stab * 0.15, 2)

    # 섹터 내 종합 백분위
    sector_pct_rank = _f(pct.get("overall_percentile"))
    # 보정 점수 (현재는 raw와 동일, Layer 2 적용 시 조정)
    total_score_adj = total

    return {
        "moat_score":              round(raw_moat, 2),
        "value_score":             round(raw_val, 2),
        "momentum_score":          round(raw_mom, 2),
        "stability_score":         round(raw_stab, 2),
        "layer1_raw_score":        total,
        "layer1_score":            total,
        "sector_percentile_rank":  sector_pct_rank,
        "total_score_adj":         total_score_adj,
    }