"""
batch/calculator.py — Layer 1 점수 계산 v3.1
==============================================
v3.0: 계단식 if-else percentile_to_points
v3.1: Sigmoid 연속 변환 (scoring_engine.py 사용)
      +AssetGrowth, +ShareholderYield, F-Score→MOAT 이동

변경 원칙:
  1. 함수 시그니처(이름, 파라미터) 100% 하위호환 유지
  2. 반환 dict 키 → 기존 키 전부 유지 + 신규 키 추가만
  3. 계단식 if-else → sigmoid_score / zscore_to_sigmoid
  4. 각 카테고리 내부 만점 = 100점 (불변)
"""
import numpy as np
from decimal import Decimal

# ── scoring_engine import ──
from utils.scoring_engine import (
    sigmoid_score,
    inverse_sigmoid_score,
    zscore_to_sigmoid,
    linear_interp_score,
    calc_asset_growth_score,
    calc_shareholder_yield_score,
)


# ═══════════════════════════════════════════════════════════
# 헬퍼
# ═══════════════════════════════════════════════════════════

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
    섹터 내 백분위 → 점수 변환

    v3.0: 5단계 계단식
    v3.1: Sigmoid 연속 변환 (인접 1 percentile 차이 < 1점)

    ★ 함수명/시그니처 유지 → 기존 코드에서 직접 호출해도 호환
    """
    if pct is None:
        return 0.0
    return sigmoid_score(float(pct), max_points)


# ═══════════════════════════════════════════════════════════
# MOAT (35%) — v3.1
# ═══════════════════════════════════════════════════════════
#
# v3.0: ROIC(30) + GPA(25) + FCF(20) + Accruals(15) + NDE(10) = 100
# v3.1: ROIC(25) + GPA(20) + FCF(15) + Accruals(10) + NDE(10)
#       + AssetGrowth(10) + F-Score(10) = 100
#
# 변경 사유:
#   AssetGrowth: 과잉투자 기업 회피 (Cooper 2008)
#   F-Score:     재무 건전성 → Quality/MOAT이 더 적합 (Piotroski 2000)
# ═══════════════════════════════════════════════════════════

def calc_moat_scores(fin: dict, pct: dict) -> dict:
    """
    MOAT 점수 계산

    Parameters (변경 없음)
    ----------
    fin : dict  재무 데이터 (accruals_quality, asset_growth 등)
    pct : dict  섹터 백분위 (roic_percentile 등)

    Returns
    -------
    dict : 기존 키 100% 유지 + asset_growth_score, f_score_points 추가
    """
    # 기존 5개 항목 (배점만 조정)
    roic_score = sigmoid_score(_f(pct.get("roic_percentile")), 25)
    gpa_score  = sigmoid_score(_f(pct.get("gpa_percentile")),  20)
    fcf_score  = sigmoid_score(_f(pct.get("fcf_margin_percentile")), 15)
    nde_score  = sigmoid_score(_f(pct.get("net_debt_ebitda_percentile")), 10)

    # Accruals: 역방향 (낮을수록 좋음) — percentile 있으면 사용, 없으면 절대값
    accruals_pct = _f(pct.get("accruals_percentile"))
    if accruals_pct is not None:
        accruals_score = inverse_sigmoid_score(accruals_pct, 10)
    else:
        # 절대값 폴백: 경험적 분포 (S&P500 mean≈0.02, std≈0.05)
        accruals_val = _f(fin.get("accruals_quality"))
        if accruals_val is not None:
            accruals_score = 10.0 - zscore_to_sigmoid(accruals_val, 0.02, 0.05, 10.0)
        else:
            accruals_score = 5.0  # 중립

    # ★ 신규: Asset Growth (낮을수록 좋음)
    ag_val = _f(fin.get("asset_growth"))
    ag_score = calc_asset_growth_score(ag_val, 10.0)

    # ★ 신규: F-Score (MOMENTUM에서 이동)
    # fin에 f_score_raw가 있으면 사용, 없으면 내부 계산
    f_raw = fin.get("f_score_raw")
    if f_raw is None and fin.get("net_income") is not None:
        # fin_prev 정보가 fin 안에 _prev 키로 있을 수 있음
        fin_prev_for_f = {k.replace("_prev", ""): v
                          for k, v in fin.items() if k.endswith("_prev")}
        if fin_prev_for_f:
            f_raw = _calc_f_score(fin, fin_prev_for_f)
    f_pts = linear_interp_score(f_raw, 9, 10.0, 1.0) if f_raw is not None else 5.0

    total = round(roic_score + gpa_score + fcf_score
                  + accruals_score + nde_score + ag_score + f_pts, 2)

    return {
        # 기존 키 (100% 유지)
        "roic_score":             roic_score,
        "gpa_score":              gpa_score,
        "fcf_margin_score":       fcf_score,
        "accruals_quality_score": round(accruals_score, 2),
        "net_debt_ebitda_score":  nde_score,
        "total_moat_score":       total,
        # 신규 키
        "asset_growth_score":     round(ag_score, 2),
        "f_score_points":         round(f_pts, 2),
        "f_score_raw":            f_raw,
    }


# ═══════════════════════════════════════════════════════════
# VALUE (25%) — v3.1
# ═══════════════════════════════════════════════════════════
#
# v3.0: EV/EBIT(35) + EV/FCF(30) + PB(20) + PEG(15) = 100
# v3.1: EV/EBIT(30) + EV/FCF(25) + PB(20) + SHY(25) = 100
#
# 변경 사유:
#   PEG 제거: 컨센서스 의존 + 음수 EPS 시 무의미
#   SHY 추가: 배당+자사주매입+부채상환 통합 (Faber 2013)
# ═══════════════════════════════════════════════════════════

def calc_value_scores(fin: dict, pct: dict) -> dict:
    """
    VALUE 점수 계산

    Parameters (변경 없음)
    ----------
    fin : dict  재무 데이터 (dividend_yield, buyback_yield 등)
    pct : dict  섹터 백분위

    Returns
    -------
    dict : 기존 키 유지 + shy_score 추가, peg_score는 0.0 고정 (하위호환)
    """
    ey_score  = sigmoid_score(_f(pct.get("ev_ebit_percentile")), 30)
    evf_score = sigmoid_score(_f(pct.get("ev_fcf_percentile")),  25)
    pb_score  = sigmoid_score(_f(pct.get("pb_percentile")),      20)

    # ★ SHY (PEG 대체)
    shy_score, shy_raw = calc_shareholder_yield_score(
        div_yield=_f(fin.get("dividend_yield")),
        buyback_yield=_f(fin.get("buyback_yield")),
        debt_paydown_yield=_f(fin.get("debt_paydown_yield")),
        shy_percentile=_f(pct.get("shy_percentile")),
        max_points=25.0,
    )

    total = round(ey_score + evf_score + pb_score + shy_score, 2)

    return {
        # 기존 키 (하위호환: peg_score=0.0 유지)
        "earnings_yield_score": ey_score,
        "ev_fcf_score":         evf_score,
        "pb_score":             pb_score,
        "peg_score":            0.0,        # deprecated — 하위호환용
        "total_value_score":    total,
        # 신규 키
        "shy_score":            round(shy_score, 2),
        "shy_raw":              shy_raw,
    }


# ═══════════════════════════════════════════════════════════
# MOMENTUM (25%) — v3.1
# ═══════════════════════════════════════════════════════════
#
# v3.0: F-Score(30) + ATO(20) + OpLev(15) + Surprise(20) + Revision(15) = 100
# v3.1: Surprise(30) + Revision(20) + ATO(20) + OpLev(15) + Trend(15) = 100
#
# 변경 사유:
#   F-Score → MOAT으로 이동 (재무 건전성 = Quality)
#   Surprise/Revision 비중 유지 (핵심 모멘텀)
#   Trend(EPS 추세 강도) 추가
# ═══════════════════════════════════════════════════════════

def calc_momentum_scores(fin: dict, fin_prev: dict, pct: dict,
                         qtr_eps_hist: list = None) -> dict:
    """
    모멘텀 점수 계산

    Parameters (100% 동일)
    ----------
    fin          : dict  현재 재무 데이터
    fin_prev     : dict  전기 재무 데이터
    pct          : dict  섹터 백분위
    qtr_eps_hist : list  분기 EPS (최신순)

    Returns
    -------
    dict : 기존 키 100% 유지 (f_score_raw/f_score_points는 0으로 하위호환)
    """
    # ── Earnings Surprise (30점) ──
    surprise_pct = None
    surprise_score = 15.0  # 중립
    if qtr_eps_hist and len(qtr_eps_hist) >= 5:
        latest_eps = _f(qtr_eps_hist[0])
        yoy_eps    = _f(qtr_eps_hist[4])
        if latest_eps is not None and yoy_eps is not None and yoy_eps != 0:
            surprise_pct = round((latest_eps - yoy_eps) / abs(yoy_eps), 4)
            # Z-score 기반 (경험적: mean=0.05, std=0.20)
            surprise_score = zscore_to_sigmoid(
                surprise_pct, 0.05, 0.20, 30.0
            )

    # ── Earnings Revision (20점) ──
    revision_ratio = None
    revision_score = 10.0  # 중립
    if qtr_eps_hist and len(qtr_eps_hist) >= 4:
        changes = []
        for i in range(min(3, len(qtr_eps_hist) - 1)):
            cur_e  = _f(qtr_eps_hist[i])
            prev_e = _f(qtr_eps_hist[i + 1])
            if cur_e is not None and prev_e is not None and prev_e != 0:
                changes.append((cur_e - prev_e) / abs(prev_e))
        if changes:
            revision_ratio = round(sum(changes) / len(changes), 4)
            # Z-score 기반 (경험적: mean=0.02, std=0.15)
            revision_score = zscore_to_sigmoid(
                revision_ratio, 0.02, 0.15, 20.0
            )

    # ── ATO Acceleration (20점) ──
    ato_cur  = _f(fin.get("asset_turnover"))
    ato_prev = _f((fin_prev or {}).get("asset_turnover"))
    ato_accel = None
    if ato_cur is not None and ato_prev is not None:
        ato_accel = round(ato_cur - ato_prev, 4)
        # Z-score (경험적: mean=0, std=0.05)
        ato_score = zscore_to_sigmoid(ato_accel, 0.0, 0.05, 20.0)
    else:
        ato_score = 10.0  # 중립

    # ── Operating Leverage (15점) ──
    op_lev_val = _f(fin.get("operating_leverage"))
    if op_lev_val is not None:
        # OpLev 1.0이 중립, 2.0+ 우수, 0 이하 부진
        # Z-score (경험적: mean=1.0, std=1.5)
        oplev_score = zscore_to_sigmoid(op_lev_val, 1.0, 1.5, 15.0)
    else:
        oplev_score = sigmoid_score(
            _f(pct.get("op_leverage_percentile")), 15
        )

    # ── EPS Trend Strength (15점) ── 신규
    # 최근 4분기 EPS가 일관되게 상승하는지 (추세 R² 기반)
    trend_score = 7.5  # 중립
    if qtr_eps_hist and len(qtr_eps_hist) >= 4:
        eps_arr = [_f(e) for e in qtr_eps_hist[:4] if _f(e) is not None]
        if len(eps_arr) >= 4:
            eps_arr_rev = list(reversed(eps_arr))  # 과거→최신 순서
            x = np.arange(len(eps_arr_rev))
            y = np.array(eps_arr_rev)
            if np.std(y) > 0:
                corr = np.corrcoef(x, y)[0, 1]
                # corr > 0 = 상승 추세, r² ≈ 추세 강도
                signed_r2 = corr * corr * np.sign(corr)
                # signed_r2 범위: -1 ~ +1 → percentile 매핑
                pct_equiv = (signed_r2 + 1) / 2 * 100  # 0~100
                trend_score = sigmoid_score(pct_equiv, 15.0)

    total = round(surprise_score + revision_score
                  + ato_score + oplev_score + trend_score, 2)

    return {
        # 기존 키 (100% 하위호환)
        "f_score_raw":             0,     # deprecated (→ MOAT)
        "f_score_points":          0.0,   # deprecated (→ MOAT)
        "earnings_surprise_pct":   surprise_pct,
        "earnings_surprise_score": round(surprise_score, 2),
        "earnings_revision_ratio": revision_ratio,
        "earnings_revision_score": round(revision_score, 2),
        "ato_acceleration_score":  round(ato_score, 2),
        "op_leverage_score":       round(oplev_score, 2),
        "total_momentum_score":    total,
        # 신규 키
        "eps_trend_score":         round(trend_score, 2),
    }


# ═══════════════════════════════════════════════════════════
# F-Score 내부 계산 (변경 없음)
# ═══════════════════════════════════════════════════════════

def _calc_f_score(fin: dict, fin_prev: dict) -> int:
    """Piotroski F-Score 9개 이진 지표 (변경 없음)"""
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


# ═══════════════════════════════════════════════════════════
# STABILITY (15%) — v3.1
# ═══════════════════════════════════════════════════════════
#
# v3.0: EPS_CV(30) + Vol(25) + MDD(25) + Div(20) = 100 (계단식)
# v3.1: EPS_CV(30) + Vol(25) + MDD(25) + Div(20) = 100 (Sigmoid)
#
# 배점 변경 없음, 변환 방식만 계단→Sigmoid
# ═══════════════════════════════════════════════════════════

def calc_stability_scores(price_df, eps_history: list,
                          dividend_years: int, pct: dict) -> dict:
    """
    안정성 점수 계산

    Parameters (100% 동일)
    ----------
    price_df       : DataFrame  trade_date, close_price 컬럼
    eps_history    : list       TTM EPS 시계열
    dividend_years : int        배당 지급 연수
    pct            : dict       섹터 백분위

    Returns
    -------
    dict : 기존 키 100% 유지
    """
    import pandas as pd

    # ── 1. 수익 안정성 (30점) — EPS CV: 낮을수록 좋음 ──
    eps_cv = None
    earnings_stab_score = 15.0  # 중립
    if eps_history and len(eps_history) >= 2:
        arr = [e for e in eps_history if e is not None]
        if len(arr) >= 2:
            mean_val = np.mean(arr)
            if mean_val != 0:
                eps_cv = round(float(np.std(arr) / abs(mean_val)), 4)
                # CV 낮을수록 좋음 → inverse zscore
                # 경험적: S&P500 EPS CV mean≈0.25, std≈0.20
                earnings_stab_score = 30.0 - zscore_to_sigmoid(
                    eps_cv, 0.25, 0.20, 30.0
                )
            else:
                eps_cv = 999.0
                earnings_stab_score = 0.0

    # ── 2. 가격 변동성 (25점) — 낮을수록 좋음 ──
    annual_vol = None
    vol_score = 0.0
    if price_df is not None and len(price_df) >= 60:
        try:
            closes = price_df["close_price"].dropna().astype(float)
            if len(closes) >= 60:
                rets = closes.pct_change().dropna()
                annual_vol = round(float(rets.std() * np.sqrt(252)), 4)
                # 변동성 낮을수록 좋음 → inverse zscore
                # 경험적: S&P500 평균 연변동성 ≈ 0.28, std ≈ 0.12
                vol_score = 25.0 - zscore_to_sigmoid(
                    annual_vol, 0.28, 0.12, 25.0
                )
        except Exception:
            vol_score = 0.0

    # ── 3. 최대 낙폭 MDD (25점) — 낮을수록(절대값 작을수록) 좋음 ──
    mdd_score = 0.0
    if price_df is not None and len(price_df) >= 60:
        try:
            closes = price_df["close_price"].dropna().astype(float)
            if len(closes) >= 60:
                peak = closes.expanding().max()
                dd   = (closes - peak) / peak
                mdd  = float(dd.min())  # 음수
                # MDD가 0에 가까울수록(낙폭 적을수록) 좋음
                # 경험적: S&P500 종목 평균 MDD ≈ -0.30, std ≈ 0.15
                mdd_abs = abs(mdd)
                mdd_score = 25.0 - zscore_to_sigmoid(
                    mdd_abs, 0.30, 0.15, 25.0
                )
        except Exception:
            mdd_score = 0.0

    # ── 4. 배당 지속성 (20점) ──
    # 이산값 → 선형 보간 (0~25년 → 0~20점)
    if dividend_years is not None:
        # 25년 이상이면 만점, 선형 보간
        dy = min(float(dividend_years), 25.0)
        div_score = round(dy / 25.0 * 20.0, 2)
    else:
        div_score = 0.0

    low_vol_score = round(vol_score + mdd_score, 2)
    total = round(earnings_stab_score + low_vol_score + div_score, 2)

    return {
        # 기존 키 100% 유지
        "annualized_volatility_250d":  annual_vol,
        "low_vol_score":               low_vol_score,
        "eps_cv_3y":                   eps_cv,
        "earnings_stability_score":    round(earnings_stab_score, 2),
        "dividend_consecutive_years":  dividend_years,
        "dividend_consistency_score":  round(div_score, 2),
        "total_stability_score":       total,
    }


# ═══════════════════════════════════════════════════════════
# LAYER 1 총점 (변경 없음)
# ═══════════════════════════════════════════════════════════

def calc_layer1_score(moat: dict, value: dict, momentum: dict,
                      stability: dict, pct: dict) -> dict:
    """설계서 2.3 Layer 1 총점 (MOAT 35 + VALUE 25 + MOMENTUM 25 + STABILITY 15)."""
    raw_moat  = moat.get("total_moat_score", 0) or 0
    raw_val   = value.get("total_value_score", 0) or 0
    raw_mom   = momentum.get("total_momentum_score", 0) or 0
    raw_stab  = stability.get("total_stability_score", 0) or 0

    total = round(raw_moat * 0.35 + raw_val * 0.25
                  + raw_mom * 0.25 + raw_stab * 0.15, 2)

    sector_pct_rank = _f(pct.get("overall_percentile"))
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