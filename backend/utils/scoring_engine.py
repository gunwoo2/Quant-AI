"""
scoring_engine.py — QUANT AI v3.1 Universal Scoring Engine
============================================================
v3.0: 모든 점수 변환을 Sigmoid/연속함수로 통합
v3.1: +AssetGrowth, +ShareholderYield, +12-1MOM 변환 함수
      +MOAT에 AssetGrowth·F-Score 통합, VALUE에서 PEG→SHY
      +Layer3에 12-1MOM·ShortTermReversal 통합

원칙:
  1. 모든 "if pct >= X: return Y" 패턴을 Sigmoid으로 교체
  2. 절대값 기반 지표는 Z-score or Percentile 변환 후 Sigmoid
  3. 이산값(F-Score 0~9)은 Linear Interpolation
  4. 경계값 점프 최대 허용: 1점 이내 (인접 값 간)

참고 논문:
  - Cooper, Gulen, Schill (2008) — Asset Growth Effect
  - Mebane Faber (2013) — Shareholder Yield
  - Jegadeesh & Titman (1993) — 12-1 Month Momentum
  - Ilmanen et al. (2021) — Factor-Based Investing
"""

import numpy as np
from typing import Optional, Dict, Tuple, List
from dataclasses import dataclass, field


# ═══════════════════════════════════════════════════════════
# §1. Universal Transform Functions
# ═══════════════════════════════════════════════════════════

def sigmoid_score(percentile: float, max_points: float,
                  steepness: float = 10.0, midpoint: float = 50.0) -> float:
    """
    Universal Sigmoid: 백분위 → 점수 (연속)

    Parameters
    ----------
    percentile : float  0~100 범위의 백분위
    max_points : float  이 항목의 최대 점수
    steepness  : float  S-curve 기울기 (10=완만, 15=중간, 20=급격)
    midpoint   : float  S-curve의 중심점 (기본 50 = 중앙)

    Returns
    -------
    float : 0 ~ max_points 범위의 점수
    """
    if percentile is None:
        return 0.0

    pct = float(percentile)
    pct = max(0.0, min(100.0, pct))

    x = steepness * (pct - midpoint) / 100.0
    sigma = 1.0 / (1.0 + np.exp(-x))

    sig_min = 1.0 / (1.0 + np.exp(steepness * midpoint / 100.0))
    sig_max = 1.0 / (1.0 + np.exp(-steepness * (100.0 - midpoint) / 100.0))

    normalized = (sigma - sig_min) / (sig_max - sig_min)
    normalized = max(0.0, min(1.0, normalized))

    return round(normalized * max_points, 2)


def zscore_to_sigmoid(value: float, mean: float, std: float,
                      max_points: float, steepness: float = 10.0) -> float:
    """
    Z-Score → Percentile → Sigmoid 변환

    절대값 지표를 먼저 Z-score로 정규화한 뒤 Sigmoid으로 점수화.
    """
    if value is None or std is None:
        return max_points * 0.5

    if std == 0 or std < 1e-10:
        return max_points * 0.5

    z = (float(value) - float(mean)) / float(std)
    pct = 100.0 / (1.0 + np.exp(-1.7 * z))

    return sigmoid_score(pct, max_points, steepness)


def linear_interp_score(discrete_value: int, max_discrete: int,
                        max_points: float, min_points: float = 0.0) -> float:
    """
    이산값 → 선형 보간 점수 (F-Score 0~9 등)

    F=9→max_points, F=0→min_points, 사이는 균등 간격
    """
    if discrete_value is None:
        return min_points

    ratio = float(discrete_value) / float(max_discrete)
    ratio = max(0.0, min(1.0, ratio))

    return round(min_points + (max_points - min_points) * ratio, 2)


def inverse_sigmoid_score(percentile: float, max_points: float,
                          steepness: float = 10.0) -> float:
    """
    역방향 Sigmoid: 낮을수록 좋은 지표 (PBR, EV/EBIT, Asset Growth 등)
    """
    return sigmoid_score(100.0 - percentile, max_points, steepness)


# ═══════════════════════════════════════════════════════════
# §1-B. 신규 팩터 변환 함수 (v3.1)
# ═══════════════════════════════════════════════════════════

def calc_asset_growth_score(
    asset_growth: float,
    max_points: float = 10.0,
    sector_stats: dict = None,
    steepness: float = 10.0
) -> float:
    """
    Asset Growth Score — Cooper, Gulen & Schill (2008)

    공식: AG = (TotalAssets_t − TotalAssets_{t-1}) / TotalAssets_{t-1}

    ★ 낮을수록 좋음 (과잉투자 회피 팩터)
    - AG > 30%  : 과잉투자 가능성 → 낮은 점수
    - AG ~ 0~5% : 안정적 성장 → 높은 점수
    - AG < -10% : 자산 축소 (구조조정) → 중간 점수

    변환: Z-score → inverse sigmoid  (섹터 내 정규화)
    Fallback: 섹터 통계 없으면 경험적 분포 가정 (mean=8%, std=15%)

    Parameters
    ----------
    asset_growth  : float  자산 증가율 (소수, 0.08 = 8%)
    max_points    : float  최대 배점
    sector_stats  : dict   {"ag_mean": float, "ag_std": float}
    """
    if asset_growth is None:
        return max_points * 0.5  # 데이터 없으면 중립

    ag = float(asset_growth)

    # 섹터 통계 기반 Z-score → 역방향 (낮을수록 좋음)
    mean = 0.08  # 경험적 기본값: S&P500 평균 자산 증가율 ~8%
    std  = 0.15  # 경험적 기본값

    if sector_stats:
        mean = sector_stats.get("ag_mean", mean)
        std  = sector_stats.get("ag_std", std)

    if std < 1e-10:
        return max_points * 0.5

    z = (ag - mean) / std
    # Z-score → percentile
    pct = 100.0 / (1.0 + np.exp(-1.7 * z))
    # 역방향: AG가 높으면(percentile 높으면) 점수 낮음
    return inverse_sigmoid_score(pct, max_points, steepness)


def calc_shareholder_yield_score(
    div_yield: float = None,
    buyback_yield: float = None,
    debt_paydown_yield: float = None,
    shy_percentile: float = None,
    max_points: float = 25.0,
    sector_stats: dict = None,
    steepness: float = 10.0
) -> Tuple[float, float]:
    """
    Shareholder Yield Score — Mebane Faber (2013)

    공식: SHY = Dividend Yield + Net Buyback Yield + Debt Paydown Yield
      - Dividend Yield     = Annual Dividends / Market Cap
      - Net Buyback Yield  = (Shares Repurchased − Shares Issued) / Market Cap
      - Debt Paydown Yield = Net Debt Reduction / Market Cap (양수=부채 상환)

    ★ 높을수록 좋음 (주주 환원 총량)
    - SHY > 8%  : 매우 높은 주주 환원 → 최고 점수
    - SHY ~ 3%  : 평균적 → 중간 점수
    - SHY < 0%  : 희석 + 부채 증가 → 낮은 점수

    반환: (score, shy_raw)

    Parameters
    ----------
    div_yield          : float  배당 수익률 (소수, 0.02 = 2%)
    buyback_yield      : float  자사주 매입 수익률 (소수)
    debt_paydown_yield : float  부채 상환 수익률 (소수)
    shy_percentile     : float  이미 계산된 SHY 백분위 (있으면 직접 사용)
    max_points         : float  최대 배점
    sector_stats       : dict   {"shy_mean", "shy_std"}
    """
    # SHY raw 계산
    d = float(div_yield or 0)
    b = float(buyback_yield or 0)
    p = float(debt_paydown_yield or 0)
    shy_raw = d + b + p

    # 모든 구성요소가 None이면 데이터 없음
    if div_yield is None and buyback_yield is None and debt_paydown_yield is None:
        if shy_percentile is not None:
            return sigmoid_score(shy_percentile, max_points, steepness), None
        return max_points * 0.5, None

    # percentile이 이미 있으면 직접 사용
    if shy_percentile is not None:
        return sigmoid_score(shy_percentile, max_points, steepness), shy_raw

    # Z-score 기반
    mean = 0.03  # S&P500 평균 SHY ~3%
    std  = 0.04  # 경험적 기본값

    if sector_stats:
        mean = sector_stats.get("shy_mean", mean)
        std  = sector_stats.get("shy_std", std)

    if std < 1e-10:
        return max_points * 0.5, shy_raw

    score = zscore_to_sigmoid(shy_raw, mean, std, max_points, steepness)
    return score, shy_raw


def calc_mom_12_1_score(
    ret_12m: float,
    ret_1m: float,
    spy_ret_12m: float = None,
    spy_ret_1m: float = None,
    max_points: float = 30.0,
    ctx: 'TechnicalContext' = None,
    steepness: float = 10.0
) -> Tuple[float, float]:
    """
    12-1 Month Momentum Score — Jegadeesh & Titman (1993)

    공식:
      abs_mom  = ret_12m − ret_1m            (최근 1개월 제거)
      spy_mom  = spy_ret_12m − spy_ret_1m
      rel_mom  = abs_mom − spy_mom           (SPY 대비 상대)

    ★ 높을수록 좋음 (상대 모멘텀 강도)
    - rel_mom > +30%  : 시장 대비 압도적 초과 수익
    - rel_mom ~ 0%    : 시장 수준
    - rel_mom < -10%  : 상대 약세

    반환: (score, rel_mom_raw)

    Parameters
    ----------
    ret_12m     : float  12개월 누적 수익률 (소수, 0.20 = 20%)
    ret_1m      : float  최근 1개월 수익률 (소수)
    spy_ret_12m : float  SPY 12개월 수익률 (없으면 절대 모멘텀만)
    spy_ret_1m  : float  SPY 1개월 수익률
    max_points  : float  최대 배점
    ctx         : TechnicalContext  (mom_mean, mom_std)
    """
    if ret_12m is None:
        return max_points * 0.4, None  # 데이터 없으면 중립 약간 아래

    r12 = float(ret_12m)
    r1  = float(ret_1m or 0)

    # 절대 12-1 모멘텀
    abs_mom = r12 - r1

    # 상대 모멘텀 (SPY 대비)
    if spy_ret_12m is not None:
        spy_mom = float(spy_ret_12m) - float(spy_ret_1m or 0)
        rel_mom = abs_mom - spy_mom
    else:
        rel_mom = abs_mom  # SPY 데이터 없으면 절대값

    # 퍼센트로 변환 (0.20 → 20.0)
    rel_mom_pct = rel_mom * 100.0

    # Z-score 기반 변환
    if ctx and hasattr(ctx, 'mom_mean') and ctx.mom_std > 0:
        score = zscore_to_sigmoid(
            rel_mom_pct, ctx.mom_mean, ctx.mom_std, max_points, steepness
        )
    else:
        # 경험적 분포 가정 (S&P500 12-1MOM: mean≈8%, std≈20%)
        score = zscore_to_sigmoid(
            rel_mom_pct, 8.0, 20.0, max_points, steepness=8.0
        )

    return score, round(rel_mom * 100, 2)  # (점수, raw%)


def calc_short_term_reversal_score(
    ret_1m: float,
    max_points: float = 10.0,
    ctx: 'TechnicalContext' = None
) -> float:
    """
    Short-Term Reversal Score

    최근 1개월 과매도 → 반등 기대 (Jegadeesh 1990)
    ret_1m이 낮을수록(과매도) → 높은 점수

    변환: inverse zscore_to_sigmoid
    """
    if ret_1m is None:
        return max_points * 0.5

    r1_pct = float(ret_1m) * 100.0

    if ctx and hasattr(ctx, 'ret1m_mean') and hasattr(ctx, 'ret1m_std') and ctx.ret1m_std > 0:
        mean, std = ctx.ret1m_mean, ctx.ret1m_std
    else:
        mean, std = 0.5, 8.0  # 경험적 (월 수익률 평균 0.5%, 표준편차 8%)

    if std < 1e-10:
        return max_points * 0.5

    z = (r1_pct - mean) / std
    pct = 100.0 / (1.0 + np.exp(-1.7 * z))
    # 역방향: 최근 하락 클수록 반등 기대 → 높은 점수
    return inverse_sigmoid_score(pct, max_points, steepness=8.0)


# ═══════════════════════════════════════════════════════════
# §2. Layer 1 — Fundamental Scoring (v3.1)
# ═══════════════════════════════════════════════════════════

def calc_moat_v3(fin: dict, pct: dict, sector_stats: dict = None,
                 f_score_raw: int = None) -> dict:
    """
    MOAT (35%) — v3.1

    v3.0: ROIC(30) + GPA(25) + FCF(20) + Accruals(15) + NetDebt(10)
    v3.1: ROIC(25) + GPA(20) + FCF(15) + Accruals(10) + NetDebt(10)
         + AssetGrowth(10) + F-Score(10) = 100

    변경 사유:
      - AssetGrowth: 과잉투자 기업 회피 (Cooper 2008, 장기 수익률 -4%/yr)
      - F-Score: 재무 건전성 → MOAT이 더 적합 (Piotroski 2000)
      - 기존 항목 배점 미세 조정하여 합계 100점 유지
    """
    _f = lambda v: float(v) if v is not None else None

    roic = sigmoid_score(_f(pct.get("roic_percentile")), 25)
    gpa  = sigmoid_score(_f(pct.get("gpa_percentile")),  20)
    fcf  = sigmoid_score(_f(pct.get("fcf_margin_percentile")), 15)
    nde  = sigmoid_score(_f(pct.get("net_debt_ebitda_percentile")), 10)

    # Accruals: Z-score 역방향 (낮을수록 좋음)
    accruals_val = _f(fin.get("accruals_quality"))
    if sector_stats and "accruals_mean" in sector_stats:
        accruals = zscore_to_sigmoid(
            accruals_val,
            sector_stats["accruals_mean"],
            sector_stats["accruals_std"],
            max_points=10.0
        )
        accruals = 10.0 - accruals  # 역방향
    else:
        accruals_pct = _f(pct.get("accruals_percentile"))
        if accruals_pct is not None:
            accruals = inverse_sigmoid_score(accruals_pct, 10.0)
        else:
            accruals = 5.0  # 중립

    # ★ 신규: Asset Growth (낮을수록 좋음)
    ag_val = _f(fin.get("asset_growth"))
    ag_score = calc_asset_growth_score(ag_val, 10.0, sector_stats)

    # ★ 신규: F-Score (MOMENTUM에서 이동)
    f_pts = linear_interp_score(f_score_raw, 9, 10.0, 1.0)
    # F=9→10, F=5→6.6, F=0→1

    total = round(roic + gpa + fcf + accruals + nde + ag_score + f_pts, 2)

    return {
        "roic_score": roic,
        "gpa_score": gpa,
        "fcf_margin_score": fcf,
        "accruals_quality_score": round(accruals, 2),
        "net_debt_ebitda_score": nde,
        "asset_growth_score": round(ag_score, 2),
        "f_score_points": round(f_pts, 2),
        "total_moat_score": total,
        "_method": "sigmoid_v3.1"
    }


def calc_value_v3(fin: dict, pct: dict, sector_stats: dict = None) -> dict:
    """
    VALUE (25%) — v3.1

    v3.0: EV/EBIT(35) + EV/FCF(30) + PB(20) + PEG(15) = 100
    v3.1: EV/EBIT(30) + EV/FCF(25) + PB(20) + SHY(25) = 100

    변경 사유:
      - PEG 제거: 컨센서스 의존 + 음수 EPS 시 무의미
      - SHY 추가: 배당+자사주매입+부채상환 통합 주주환원 지표
      - 상위 항목 배점 미세 조정
    """
    _f = lambda v: float(v) if v is not None else None

    ey  = sigmoid_score(_f(pct.get("ev_ebit_percentile")), 30)
    evf = sigmoid_score(_f(pct.get("ev_fcf_percentile")),  25)
    pb  = sigmoid_score(_f(pct.get("pb_percentile")),      20)

    # ★ 신규: Shareholder Yield (PEG 대체)
    shy_score, shy_raw = calc_shareholder_yield_score(
        div_yield=_f(fin.get("dividend_yield")),
        buyback_yield=_f(fin.get("buyback_yield")),
        debt_paydown_yield=_f(fin.get("debt_paydown_yield")),
        shy_percentile=_f(pct.get("shy_percentile")),
        max_points=25.0,
        sector_stats=sector_stats
    )

    total = round(ey + evf + pb + shy_score, 2)

    return {
        "earnings_yield_score": ey,
        "ev_fcf_score": evf,
        "pb_score": pb,
        "shy_score": round(shy_score, 2),
        "shy_raw": shy_raw,
        "total_value_score": total,
        "_method": "sigmoid_v3.1"
    }


def calc_momentum_v3(fin: dict, fin_prev: dict, pct: dict,
                     earnings_surprise_pct: float = None,
                     earnings_revision_pct: float = None,
                     sector_stats: dict = None) -> dict:
    """
    MOMENTUM (25%) — v3.1

    v3.0: F-Score(30) + Surprise(40) + Revision(30) = 100
    v3.1: Surprise(35) + Revision(25) + ATO_Accel(20) + OpLev(20) = 100

    변경 사유:
      - F-Score → MOAT으로 이동 (재무 건전성은 Quality 영역)
      - Surprise/Revision 비중 유지 (핵심 모멘텀)
      - ATO + OpLev 추가로 100점 채움
    """
    _f = lambda v: float(v) if v is not None else None

    # Earnings Surprise
    if earnings_surprise_pct is not None and sector_stats:
        surprise = zscore_to_sigmoid(
            earnings_surprise_pct,
            sector_stats.get("surprise_mean", 0),
            sector_stats.get("surprise_std", 10),
            max_points=35.0
        )
    elif earnings_surprise_pct is not None:
        pct_equiv = 50.0 + earnings_surprise_pct * 5
        pct_equiv = max(0, min(100, pct_equiv))
        surprise = sigmoid_score(pct_equiv, 35.0)
    else:
        surprise = 17.5  # 중립

    # Earnings Revision
    if earnings_revision_pct is not None and sector_stats:
        revision = zscore_to_sigmoid(
            earnings_revision_pct,
            sector_stats.get("revision_mean", 0),
            sector_stats.get("revision_std", 5),
            max_points=25.0
        )
    elif earnings_revision_pct is not None:
        pct_equiv = 50.0 + earnings_revision_pct * 10
        pct_equiv = max(0, min(100, pct_equiv))
        revision = sigmoid_score(pct_equiv, 25.0)
    else:
        revision = 12.5  # 중립

    # ATO Acceleration (Asset Turnover 가속)
    ato_cur  = _f(fin.get("asset_turnover"))
    ato_prev = _f((fin_prev or {}).get("asset_turnover"))
    if ato_cur is not None and ato_prev is not None:
        ato_accel = ato_cur - ato_prev
        # Z-score 기반 (경험적: mean=0, std=0.05)
        ato_mean = sector_stats.get("ato_accel_mean", 0.0) if sector_stats else 0.0
        ato_std  = sector_stats.get("ato_accel_std", 0.05) if sector_stats else 0.05
        ato_score = zscore_to_sigmoid(ato_accel, ato_mean, ato_std, 20.0)
    else:
        ato_score = 10.0  # 중립

    # Operating Leverage
    oplev_score = sigmoid_score(_f(pct.get("op_leverage_percentile")), 20)

    total = round(surprise + revision + ato_score + oplev_score, 2)

    return {
        "earnings_surprise_score": round(surprise, 2),
        "earnings_revision_score": round(revision, 2),
        "ato_acceleration_score": round(ato_score, 2),
        "op_leverage_score": round(oplev_score, 2),
        "total_momentum_score": total,
        "_method": "zscore_sigmoid_v3.1"
    }


def calc_stability_v3(pct: dict) -> dict:
    """STABILITY (15%) — v3.1: Sigmoid (변경 없음)"""
    _f = lambda v: float(v) if v is not None else None

    rev_vol = sigmoid_score(_f(pct.get("revenue_stability_percentile")), 30)
    eps_vol = sigmoid_score(_f(pct.get("eps_stability_percentile")),     30)
    beta    = sigmoid_score(_f(pct.get("beta_percentile")),             25)
    div     = sigmoid_score(_f(pct.get("div_consistency_percentile")),  15)

    total = round(rev_vol + eps_vol + beta + div, 2)

    return {
        "revenue_stability_score": rev_vol,
        "eps_stability_score": eps_vol,
        "beta_score": beta,
        "dividend_score": div,
        "total_stability_score": total,
        "_method": "sigmoid_v3.1"
    }


# ═══════════════════════════════════════════════════════════
# §3. Layer 3 — Technical Scoring (v3.1)
# ═══════════════════════════════════════════════════════════

@dataclass
class TechnicalContext:
    """종목별 과거 통계 (rolling 기반)"""
    mom_mean: float = 8.0             # 12-1MOM 평균 (%)
    mom_std: float = 20.0             # 12-1MOM 표준편차
    rsi_mean: float = 50.0            # RSI 평균
    rsi_std: float = 15.0             # RSI 표준편차
    volume_ratio_mean: float = 1.0    # 거래량 비율 평균
    volume_ratio_std: float = 0.5     # 거래량 비율 표준편차
    ret1m_mean: float = 0.5           # 1개월 수익률 평균 (%)
    ret1m_std: float = 8.0            # 1개월 수익률 표준편차


def calc_52w_high_v3(dist52: float, max_points: float = 20.0) -> float:
    """
    52주 신고가 거리 점수

    0.5~1.0 → 0~100 percentile 매핑 → Sigmoid
    """
    if dist52 is None:
        return max_points * 0.3

    d = float(dist52)
    pct = max(0, min(100, (d - 0.5) / 0.5 * 100))
    return sigmoid_score(pct, max_points, steepness=12.0)


def calc_rsi_v3(rsi: float, ctx: TechnicalContext = None,
                max_points: float = 15.0) -> float:
    """
    RSI 점수 — 이중 Sigmoid (Mean-Reversion 특성 반영)

    RSI가 종목의 과거 평균에서 약간 아래(과매도 접근) → 높은 점수
    극단적 과매도/과매수 → 감점
    """
    if rsi is None:
        return max_points * 0.5

    r = float(rsi)
    mean_rsi = ctx.rsi_mean if ctx else 50.0
    std_rsi  = ctx.rsi_std  if ctx else 15.0

    z = (r - mean_rsi) / std_rsi if std_rsi > 0 else 0

    optimal_z = -0.5
    distance_from_optimal = abs(z - optimal_z)

    decay_sigma = 1.5
    quality = np.exp(-(distance_from_optimal ** 2) / (2 * decay_sigma ** 2))

    score = max_points * quality

    if z > 2.0:
        score *= 0.3
    elif z < -3.0:
        score *= 0.5

    return round(score, 2)


def calc_volume_surge_v3(volume_ratio: float, ctx: TechnicalContext = None,
                         max_points: float = 10.0) -> float:
    """거래량 급증 점수 — Z-score Sigmoid"""
    if volume_ratio is None:
        return 0.0

    vr = float(volume_ratio)
    mean_vr = ctx.volume_ratio_mean if ctx else 1.0
    std_vr  = ctx.volume_ratio_std  if ctx else 0.5

    return zscore_to_sigmoid(vr, mean_vr, std_vr, max_points, steepness=8.0)


def calc_short_interest_v3(short_pct: float, max_points: float = 15.0) -> float:
    """
    Short Interest 점수

    낮을수록 좋음 → inverse sigmoid
    (공매도 비율이 낮을수록 시장 신뢰도 높음)
    percentile로 들어올 수도 있고, raw %로 들어올 수도 있음
    """
    if short_pct is None:
        return max_points * 0.5

    sp = float(short_pct)
    # raw % 형태라면 (0~40 범위): 0~100 percentile로 매핑
    # 대부분 0~20% 범위, 20% 이상은 극단
    if sp <= 1.0:
        sp *= 100  # 소수 → 퍼센트 변환

    pct = max(0, min(100, sp / 30.0 * 100))  # 30%를 100%로 매핑
    return inverse_sigmoid_score(pct, max_points, steepness=10.0)


def calc_layer3_v3(
    ret_12m: float = None,
    ret_1m: float = None,
    spy_ret_12m: float = None,
    spy_ret_1m: float = None,
    dist52: float = None,
    rsi: float = None,
    volume_ratio: float = None,
    short_interest: float = None,
    ctx: TechnicalContext = None
) -> dict:
    """
    Layer 3 통합 — v3.1

    v3.0: RelMom(30) + 52WH(20) + RSI(15) + Volume(10) = 75
    v3.1: 12-1MOM(30) + 52WH(20) + RSI(15) + STRev(10) + Volume(10) + ShortInt(15) = 100

    변경 사유:
      - RelMom → 12-1MOM: Jegadeesh-Titman 표준 팩터 (최근 1개월 제거)
      - ShortTermReversal: 1개월 반전 효과 (별도 팩터로 분리)
      - ShortInterest: 공매도 비율 (15점, 기존 미사용분 활용)
    """
    # 12-1 Momentum (30점)
    mom_score, mom_raw = calc_mom_12_1_score(
        ret_12m, ret_1m, spy_ret_12m, spy_ret_1m,
        max_points=30.0, ctx=ctx
    )

    # 52W High (20점)
    high = calc_52w_high_v3(dist52, 20.0)

    # RSI (15점)
    rsi_s = calc_rsi_v3(rsi, ctx, 15.0)

    # Short-Term Reversal (10점)
    st_rev = calc_short_term_reversal_score(ret_1m, 10.0, ctx)

    # Volume Surge (10점)
    vol = calc_volume_surge_v3(volume_ratio, ctx, 10.0)

    # Short Interest (15점)
    si = calc_short_interest_v3(short_interest, 15.0)

    total = round(mom_score + high + rsi_s + st_rev + vol + si, 2)

    return {
        "mom_12_1_score": round(mom_score, 2),
        "mom_12_1_raw": mom_raw,
        "high52_score": high,
        "rsi_score": rsi_s,
        "short_term_reversal_score": round(st_rev, 2),
        "volume_score": vol,
        "short_interest_score": round(si, 2),
        "layer3_total": total,
        "_method": "12-1mom_zscore_sigmoid_v3.1"
    }


# ═══════════════════════════════════════════════════════════
# §4. Final Score — 적응형 합산
# ═══════════════════════════════════════════════════════════

@dataclass
class DataAvailability:
    """각 레이어 데이터 존재 여부"""
    has_layer1: bool = True
    has_layer2: bool = True
    has_layer3: bool = True

    layer1_confidence: float = 1.0
    layer2_confidence: float = 1.0
    layer3_confidence: float = 1.0


def compute_adaptive_final_score(
    l1_score: float,
    l2_score: float,
    l3_score: float,
    availability: DataAvailability = None,
    dynamic_weights: dict = None
) -> dict:
    """
    v3.1 최종 점수 합산

    데이터 없는 레이어 → 가중치 0 → 있는 레이어끼리 재분배
    """
    if availability is None:
        availability = DataAvailability()

    if dynamic_weights:
        w1 = dynamic_weights.get("layer1", 0.50)
        w2 = dynamic_weights.get("layer2", 0.25)
        w3 = dynamic_weights.get("layer3", 0.25)
    else:
        w1, w2, w3 = 0.50, 0.25, 0.25

    if not availability.has_layer1:
        w1 = 0
    if not availability.has_layer2:
        w2 = 0
    if not availability.has_layer3:
        w3 = 0

    w1 *= availability.layer1_confidence
    w2 *= availability.layer2_confidence
    w3 *= availability.layer3_confidence

    total_weight = w1 + w2 + w3

    if total_weight == 0:
        return {
            "weighted_score": None,
            "grade": "N/A",
            "confidence": "NONE",
            "data_quality": "INSUFFICIENT",
            "note": "모든 레이어 데이터 부재"
        }

    w1_norm = w1 / total_weight
    w2_norm = w2 / total_weight
    w3_norm = w3 / total_weight

    weighted = l1_score * w1_norm + l2_score * w2_norm + l3_score * w3_norm

    available_layers = sum([
        availability.has_layer1,
        availability.has_layer2,
        availability.has_layer3
    ])
    avg_confidence = total_weight / (0.50 + 0.25 + 0.25)

    if available_layers == 3 and avg_confidence > 0.8:
        quality = "HIGH"
    elif available_layers >= 2 and avg_confidence > 0.5:
        quality = "MEDIUM"
    else:
        quality = "LOW"

    return {
        "weighted_score": round(weighted, 2),
        "weights_used": {
            "layer1": round(w1_norm, 3),
            "layer2": round(w2_norm, 3),
            "layer3": round(w3_norm, 3)
        },
        "available_layers": available_layers,
        "data_quality": quality,
        "avg_confidence": round(avg_confidence, 2)
    }


# ═══════════════════════════════════════════════════════════
# §5. Adaptive Thresholds — 시장 환경 적응 임계값
# ═══════════════════════════════════════════════════════════

@dataclass
class MarketContext:
    """현재 시장 환경 통계"""
    score_mean: float = 50.0
    score_std: float = 15.0
    score_median: float = 50.0

    vix_current: float = 20.0
    vix_mean_60d: float = 18.0
    vix_std_60d: float = 5.0


def compute_adaptive_thresholds(mkt: MarketContext) -> dict:
    """시장 환경 기반 적응형 매매 임계값"""
    buy_threshold  = mkt.score_mean + 0.5 * mkt.score_std
    sell_threshold = mkt.score_mean - 0.5 * mkt.score_std

    vix_z = (mkt.vix_current - mkt.vix_mean_60d) / mkt.vix_std_60d if mkt.vix_std_60d > 0 else 0

    if vix_z > 1.0:
        buy_threshold += 2.0 * vix_z

    buy_threshold  = max(55.0, min(80.0, buy_threshold))
    sell_threshold = max(25.0, min(50.0, sell_threshold))

    return {
        "buy_threshold": round(buy_threshold, 1),
        "sell_threshold": round(sell_threshold, 1),
        "conviction_S_min": round(mkt.score_mean + 2.0 * mkt.score_std, 1),
        "conviction_A_plus_min": round(mkt.score_mean + 1.0 * mkt.score_std, 1),
        "conviction_A_min": round(mkt.score_mean + 0.5 * mkt.score_std, 1),
        "vix_z_score": round(vix_z, 2),
        "market_score_mean": round(mkt.score_mean, 1),
        "market_score_std": round(mkt.score_std, 1),
    }


# ═══════════════════════════════════════════════════════════
# §6. Data Quality Gate — 이상치 자동 탐지
# ═══════════════════════════════════════════════════════════

@dataclass
class QualityFlag:
    field: str
    value: float
    issue: str       # "OUTLIER", "YOY_SPIKE", "CROSS_CHECK_FAIL", "MISSING"
    severity: str    # "WARNING", "ERROR"
    detail: str = ""


def run_data_quality_checks(
    current: dict,
    previous: dict = None,
    sector_stats: dict = None
) -> list:
    """데이터 품질 자동 검증 → list of QualityFlag"""
    flags = []
    _f = lambda v: float(v) if v is not None else None

    # 1. IQR Outlier Detection
    if sector_stats:
        for field in ["roic", "gpa", "fcf_margin", "ev_ebit", "pb_ratio",
                       "asset_growth", "shareholder_yield"]:
            val = _f(current.get(field))
            q1 = sector_stats.get(f"{field}_q1")
            q3 = sector_stats.get(f"{field}_q3")

            if val is not None and q1 is not None and q3 is not None:
                iqr = q3 - q1
                lower = q1 - 3.0 * iqr
                upper = q3 + 3.0 * iqr

                if val < lower or val > upper:
                    flags.append(QualityFlag(
                        field=field, value=val,
                        issue="OUTLIER", severity="WARNING",
                        detail=f"범위 [{lower:.2f}, {upper:.2f}] 밖: {val:.2f}"
                    ))

    # 2. YoY Spike Detection
    if previous:
        for field in ["revenue", "net_income", "eps_diluted", "total_assets"]:
            cur = _f(current.get(field))
            prev = _f(previous.get(field))

            if cur is not None and prev is not None and abs(prev) > 0:
                yoy = (cur - prev) / abs(prev)
                if abs(yoy) > 5.0:
                    flags.append(QualityFlag(
                        field=field, value=cur,
                        issue="YOY_SPIKE", severity="ERROR",
                        detail=f"YoY {yoy*100:.0f}% (prev={prev:.2f})"
                    ))

    # 3. Cross-Check: Revenue↑ but EPS↓ sharply
    if previous:
        rev_cur  = _f(current.get("revenue"))
        rev_prev = _f(previous.get("revenue"))
        eps_cur  = _f(current.get("eps_diluted"))
        eps_prev = _f(previous.get("eps_diluted"))

        if all(v is not None for v in [rev_cur, rev_prev, eps_cur, eps_prev]):
            if rev_prev > 0 and abs(eps_prev) > 0:
                rev_growth = (rev_cur - rev_prev) / rev_prev
                eps_growth = (eps_cur - eps_prev) / abs(eps_prev)

                if rev_growth > 0.1 and eps_growth < -0.3:
                    flags.append(QualityFlag(
                        field="revenue_vs_eps",
                        value=eps_growth,
                        issue="CROSS_CHECK_FAIL",
                        severity="WARNING",
                        detail=f"Rev +{rev_growth*100:.0f}% but EPS {eps_growth*100:.0f}%"
                    ))

    # 4. Asset Growth Spike Check (v3.1 신규)
    ag = _f(current.get("asset_growth"))
    if ag is not None and abs(ag) > 1.0:
        flags.append(QualityFlag(
            field="asset_growth", value=ag,
            issue="OUTLIER", severity="WARNING",
            detail=f"Asset Growth {ag*100:.0f}% — 비정상적 자산 변동"
        ))

    return flags


# ═══════════════════════════════════════════════════════════
# §7. Attribution — 점수 기여도 분석
# ═══════════════════════════════════════════════════════════

def compute_attribution(scores: dict, sector_avg: dict = None) -> dict:
    """점수 기여도 + 섹터 대비 강약점 분석"""
    categories = {
        "moat":      scores.get("total_moat_score", 0),
        "value":     scores.get("total_value_score", 0),
        "momentum":  scores.get("total_momentum_score", 0),
        "stability": scores.get("total_stability_score", 0),
    }

    total = sum(categories.values())
    attribution = {}
    strengths = []
    weaknesses = []

    for cat, val in categories.items():
        pct = round(val / total * 100, 1) if total > 0 else 0
        attribution[cat] = {
            "score": val,
            "contribution_pct": pct,
        }

        if sector_avg and cat in sector_avg:
            diff = val - sector_avg[cat]
            attribution[cat]["vs_sector"] = round(diff, 2)

            if diff > 5:
                strengths.append(cat)
            elif diff < -5:
                weaknesses.append(cat)

    return {
        "attribution": attribution,
        "strengths": strengths,
        "weaknesses": weaknesses,
    }
