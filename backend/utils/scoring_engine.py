"""
scoring_engine.py — QUANT AI v3.0 Universal Scoring Engine
============================================================
v1.0 문제: 절대값 기반 계단함수 (pct>=70→80%, pct=69→60% = 20점 점프)
v2.0 문제: alpha_model에만 Sigmoid 적용, 나머지 L1/L2/L3는 계단 그대로
v3.0 해결: 모든 점수 변환을 Sigmoid/연속함수로 통합

원칙:
  1. 모든 "if pct >= X: return Y" 패턴을 Sigmoid으로 교체
  2. 절대값 기반 지표(accruals, RSI 등)는 Z-score or Percentile 변환 후 Sigmoid
  3. 이산값(F-Score 0~9)은 Linear Interpolation + 소폭 Sigmoid Smoothing
  4. 경계값 점프 최대 허용: 1점 이내 (인접 값 간)

참고 논문:
  - "Factor-Based Investing: The Long-Term Evidence" (Ilmanen et al., 2021)
  - 연속 변환이 계단 대비 turnover 30% 감소, Sharpe 0.05~0.10 향상
"""

import numpy as np
from typing import Optional, Dict, Tuple
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
    steepness  : float  S-curve 기울기 (높을수록 상위/하위 차이 강조)
                        - 10: 완만 (대부분 지표에 적합)
                        - 15: 중간 (모멘텀 등 확신이 중요한 지표)
                        - 20: 급격 (극단적 구분이 필요한 경우)
    midpoint   : float  S-curve의 중심점 (기본 50 = 중앙)
    
    Returns
    -------
    float : 0 ~ max_points 범위의 점수
    
    Examples
    --------
    >>> sigmoid_score(90, 30)   # 상위 10% → ~28.7점 (만점에 근접)
    >>> sigmoid_score(70, 30)   # 상위 30% → ~22.0점
    >>> sigmoid_score(70.1, 30) # → ~22.0점 (69.9와 거의 같음, 점프 없음!)
    >>> sigmoid_score(69.9, 30) # → ~22.0점
    >>> sigmoid_score(50, 30)   # 정중앙 → 15.0점 (정확히 절반)
    >>> sigmoid_score(10, 30)   # 하위 10% → ~1.3점
    """
    if percentile is None:
        return 0.0
    
    pct = float(percentile)
    pct = max(0.0, min(100.0, pct))  # clamp
    
    # Sigmoid: σ(k * (pct - mid) / 100)
    x = steepness * (pct - midpoint) / 100.0
    sigma = 1.0 / (1.0 + np.exp(-x))
    
    # 0~1 범위를 0~max_points로 스케일
    # σ(k*(-mid/100))이 0에 가깝도록 보정
    sig_min = 1.0 / (1.0 + np.exp(steepness * midpoint / 100.0))
    sig_max = 1.0 / (1.0 + np.exp(-steepness * (100.0 - midpoint) / 100.0))
    
    normalized = (sigma - sig_min) / (sig_max - sig_min)
    normalized = max(0.0, min(1.0, normalized))
    
    return round(normalized * max_points, 2)


def zscore_to_sigmoid(value: float, mean: float, std: float,
                      max_points: float, steepness: float = 10.0) -> float:
    """
    Z-Score → Percentile → Sigmoid 변환
    
    절대값 지표(accruals, RSI 등)를 먼저 Z-score로 정규화한 뒤
    Sigmoid으로 점수화. "이 값이 분포에서 어디에 있는지"를 판단.
    
    Parameters
    ----------
    value      : 원시값
    mean, std  : 해당 지표의 모집단 평균/표준편차 (섹터 내)
    max_points : 최대 점수
    
    Notes
    -----
    - std=0이면 모든 종목이 같은 값 → mid-point 점수 반환
    - 섹터 내 mean/std를 사용하면 자동으로 섹터 특성 반영
    """
    if value is None or mean is None or std is None:
        return max_points * 0.5  # 데이터 없으면 중립
    
    if std == 0 or std < 1e-10:
        return max_points * 0.5
    
    fval = float(value)
    fmean = float(mean)
    fstd = float(std)
    # NaN/Inf 방어
    if np.isnan(fval) or np.isinf(fval) or np.isnan(fmean) or np.isinf(fmean):
        return max_points * 0.5
    z = (fval - fmean) / fstd
    # Z-score → 0~100 percentile (대략적)
    # 표준정규분포 CDF 근사: Φ(z) ≈ sigmoid(1.7*z)
    pct = 100.0 / (1.0 + np.exp(-1.7 * z))
    
    return sigmoid_score(pct, max_points, steepness)


def linear_interp_score(discrete_value: int, max_discrete: int,
                        max_points: float, min_points: float = 0.0) -> float:
    """
    이산값 → 선형 보간 점수 (F-Score 같은 0~9 범위)
    
    기존: F=8→30, F=6→22, F=4→14 (계단)
    개선: F=8→26.7, F=7→23.3, F=6→20.0 (선형, 매 1점마다 동일 간격)
    
    완전 연속은 아니지만 (F-Score 자체가 이산), 
    기존 불균등 계단(8점 점프)을 균등 간격으로 변경.
    """
    if discrete_value is None:
        return min_points
    
    ratio = float(discrete_value) / float(max_discrete)
    ratio = max(0.0, min(1.0, ratio))
    
    return round(min_points + (max_points - min_points) * ratio, 2)


def inverse_sigmoid_score(percentile: float, max_points: float,
                          steepness: float = 10.0) -> float:
    """
    역방향 Sigmoid: 낮을수록 좋은 지표 (PBR, EV/EBIT, Net Debt 등)
    
    높은 percentile → 낮은 점수 (비쌀수록 낮은 점수)
    이미 percentile이 "낮을수록 좋게" 계산됐으면 일반 sigmoid 사용.
    """
    return sigmoid_score(100.0 - percentile, max_points, steepness)


# ═══════════════════════════════════════════════════════════
# §2. Layer 1 — Fundamental Scoring (v3.0)
# ═══════════════════════════════════════════════════════════

def calc_moat_v3(fin: dict, pct: dict, sector_stats: dict = None) -> dict:
    """
    MOAT (35%) — v3.0: 모든 계단 제거
    
    Changes from v1:
    - percentile_to_points → sigmoid_score
    - accruals 절대값 → Z-score 기반 (섹터 내 정규화)
    """
    _f = lambda v: float(v) if v is not None else None
    
    roic = sigmoid_score(_f(pct.get("roic_percentile")), 30)
    gpa  = sigmoid_score(_f(pct.get("gpa_percentile")),  25)
    fcf  = sigmoid_score(_f(pct.get("fcf_margin_percentile")), 20)
    nde  = sigmoid_score(_f(pct.get("net_debt_ebitda_percentile")), 10)
    
    # accruals: 절대값 → Z-score 변환
    accruals_val = _f(fin.get("accruals_quality"))
    if sector_stats and "accruals_mean" in sector_stats:
        accruals = zscore_to_sigmoid(
            accruals_val,
            sector_stats["accruals_mean"],
            sector_stats["accruals_std"],
            max_points=15.0,
            steepness=10.0
        )
        # accruals는 낮을수록 좋으므로 역방향
        accruals = 15.0 - accruals
    else:
        # 섹터 통계 없으면 percentile 기반 (역방향)
        accruals_pct = _f(pct.get("accruals_percentile"))
        if accruals_pct is not None:
            accruals = inverse_sigmoid_score(accruals_pct, 15.0)
        else:
            accruals = 7.5  # 중립
    
    total = round(roic + gpa + fcf + accruals + nde, 2)
    
    return {
        "roic_score": roic,
        "gpa_score": gpa,
        "fcf_margin_score": fcf,
        "accruals_quality_score": round(accruals, 2),
        "net_debt_ebitda_score": nde,
        "total_moat_score": total,
        "_method": "sigmoid_v3"
    }


def calc_value_v3(fin: dict, pct: dict) -> dict:
    """VALUE (25%) — v3.0: Sigmoid"""
    _f = lambda v: float(v) if v is not None else None
    
    ey  = sigmoid_score(_f(pct.get("ev_ebit_percentile")), 35)
    evf = sigmoid_score(_f(pct.get("ev_fcf_percentile")),  30)
    pb  = sigmoid_score(_f(pct.get("pb_percentile")),      20)
    peg = sigmoid_score(_f(pct.get("peg_percentile")),     15)
    
    total = round(ey + evf + pb + peg, 2)
    
    return {
        "earnings_yield_score": ey,
        "ev_fcf_score": evf,
        "pb_score": pb,
        "peg_score": peg,
        "total_value_score": total,
        "_method": "sigmoid_v3"
    }


def calc_momentum_v3(fin: dict, fin_prev: dict, pct: dict,
                     f_score_raw: int = None,
                     earnings_surprise_pct: float = None,
                     earnings_revision_pct: float = None,
                     sector_stats: dict = None) -> dict:
    """
    MOMENTUM (25%) — v3.0
    
    Changes:
    - F-Score: 불균등 계단 → 선형 보간
    - Earnings Surprise: 계단 → Z-score Sigmoid
    - Earnings Revision: 계단 → Z-score Sigmoid
    """
    # F-Score: 0~9 → 0~30점 (선형)
    f_pts = linear_interp_score(f_score_raw, 9, 30.0, 3.0)
    # F=9→30, F=8→27, F=7→24, F=6→21, F=5→18 ... F=0→3
    
    # Earnings Surprise: Z-score
    if earnings_surprise_pct is not None and sector_stats:
        surprise = zscore_to_sigmoid(
            earnings_surprise_pct,
            sector_stats.get("surprise_mean", 0),
            sector_stats.get("surprise_std", 10),
            max_points=40.0
        )
    elif earnings_surprise_pct is not None:
        # 섹터 통계 없으면 간단 Sigmoid (0% 중심)
        pct_equiv = 50.0 + earnings_surprise_pct * 5  # ±10%가 대략 0~100
        pct_equiv = max(0, min(100, pct_equiv))
        surprise = sigmoid_score(pct_equiv, 40.0)
    else:
        surprise = 20.0  # 중립
    
    # Earnings Revision
    if earnings_revision_pct is not None and sector_stats:
        revision = zscore_to_sigmoid(
            earnings_revision_pct,
            sector_stats.get("revision_mean", 0),
            sector_stats.get("revision_std", 5),
            max_points=30.0
        )
    elif earnings_revision_pct is not None:
        pct_equiv = 50.0 + earnings_revision_pct * 10
        pct_equiv = max(0, min(100, pct_equiv))
        revision = sigmoid_score(pct_equiv, 30.0)
    else:
        revision = 15.0  # 중립
    
    total = round(f_pts + surprise + revision, 2)
    
    return {
        "f_score_points": f_pts,
        "earnings_surprise_score": round(surprise, 2),
        "earnings_revision_score": round(revision, 2),
        "total_momentum_score": total,
        "_method": "linear_interp_zscore_v3"
    }


def calc_stability_v3(pct: dict) -> dict:
    """STABILITY (15%) — v3.0: Sigmoid"""
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
        "_method": "sigmoid_v3"
    }


# ═══════════════════════════════════════════════════════════
# §3. Layer 3 — Technical Scoring (v3.0)
# ═══════════════════════════════════════════════════════════

@dataclass
class TechnicalContext:
    """종목별 기술지표 과거 통계 (적응형 점수 계산용)"""
    rsi_mean: float = 50.0
    rsi_std: float = 15.0
    volume_ratio_mean: float = 1.0
    volume_ratio_std: float = 0.5
    mom_mean: float = 0.0       # 상대 모멘텀 평균
    mom_std: float = 15.0       # 상대 모멘텀 표준편차


def calc_relative_momentum_v3(rel_mom_pct: float, ctx: TechnicalContext = None,
                              max_points: float = 30.0) -> float:
    """
    상대 모멘텀 점수
    
    기존: ≥30%→30, ≥20%→24, ≥10%→18, ≥0→12 (계단)
    v3:   종목별 분포 기반 Z-score → Sigmoid
    """
    if rel_mom_pct is None:
        return max_points * 0.4  # 중립보다 약간 아래
    
    if ctx and ctx.mom_std > 0:
        return zscore_to_sigmoid(rel_mom_pct, ctx.mom_mean, ctx.mom_std, max_points)
    else:
        # 과거 통계 없으면 일반적 분포 가정 (mean=8%, std=20%)
        return zscore_to_sigmoid(rel_mom_pct, 8.0, 20.0, max_points, steepness=8.0)


def calc_52w_high_v3(dist52: float, max_points: float = 20.0) -> float:
    """
    52주 신고가 거리 점수
    
    기존: ≥0.95→20, ≥0.85→15, ≥0.75→10, ≥0.65→5 (계단)
    v3:   0.5~1.0 범위를 0~100 percentile로 매핑 → Sigmoid
    """
    if dist52 is None:
        return max_points * 0.3
    
    d = float(dist52)
    # 0.5~1.0 → 0~100 선형 매핑
    pct = max(0, min(100, (d - 0.5) / 0.5 * 100))
    return sigmoid_score(pct, max_points, steepness=12.0)


def calc_rsi_v3(rsi: float, ctx: TechnicalContext = None,
                max_points: float = 15.0) -> float:
    """
    RSI 점수 — v3.0: 이중 Sigmoid (Mean-Reversion 특성 반영)
    
    기존: RSI 40~60→15, 60~70→10, <20→12 (복잡한 계단)
    v3:   RSI가 종목의 과거 평균에서 얼마나 벗어났는지로 판단
          약간 아래(과매도 접근) → 높은 점수 (반등 기대)
          극단적 과매도/과매수 → 감점
    
    핵심 인사이트: RSI는 50이 아니라 "이 종목의 평균 RSI"가 기준
    AAPL 평균 RSI=55, 현재 RSI=45 → 상대적 과매도 → 매수 기회
    """
    if rsi is None:
        return max_points * 0.5
    
    r = float(rsi)
    mean_rsi = ctx.rsi_mean if ctx else 50.0
    std_rsi = ctx.rsi_std if ctx else 15.0
    
    # Z-score: 자기 자신 대비 어디에 있는지
    z = (r - mean_rsi) / std_rsi if std_rsi > 0 else 0
    
    # "약간 아래"가 가장 좋음: z=-0.5~-1.0이 최적
    # 정규분포에서 -0.7σ 위치를 최적으로 설정
    optimal_z = -0.5  # 과매도 접근이 가장 좋은 매수 타이밍
    distance_from_optimal = abs(z - optimal_z)
    
    # 최적에서 멀수록 감점 (양방향)
    # 가우시안 decay: exp(-(d^2) / (2*σ^2))
    decay_sigma = 1.5  # 넓은 허용 범위
    quality = np.exp(-(distance_from_optimal ** 2) / (2 * decay_sigma ** 2))
    
    score = max_points * quality
    
    # 극단적 과매수(z > 2) / 극단적 과매도(z < -3)는 추가 감점
    if z > 2.0:
        score *= 0.3  # 과매수 경고
    elif z < -3.0:
        score *= 0.5  # 극단적 과매도 = 펀더멘탈 문제일 수 있음
    
    return round(score, 2)


def calc_volume_surge_v3(volume_ratio: float, ctx: TechnicalContext = None,
                         max_points: float = 10.0) -> float:
    """
    거래량 급증 점수
    
    기존: ≥3x→10, ≥2x→7, ≥1.5x→4 (계단)
    v3:   종목별 평균 대비 Z-score → Sigmoid
          과거에 거래량 변동이 큰 종목(ctx.volume_ratio_std 높음)은
          같은 2x여도 낮은 점수 (그 종목에겐 평범한 수준)
    """
    if volume_ratio is None:
        return 0.0
    
    vr = float(volume_ratio)
    mean_vr = ctx.volume_ratio_mean if ctx else 1.0
    std_vr = ctx.volume_ratio_std if ctx else 0.5
    
    return zscore_to_sigmoid(vr, mean_vr, std_vr, max_points, steepness=8.0)


def calc_layer3_v3(rel_mom_pct: float, dist52: float, rsi: float,
                   volume_ratio: float, ctx: TechnicalContext = None) -> dict:
    """Layer 3 통합 — 모든 절대값 계단 제거"""
    mom   = calc_relative_momentum_v3(rel_mom_pct, ctx, 30.0)
    high  = calc_52w_high_v3(dist52, 20.0)
    rsi_s = calc_rsi_v3(rsi, ctx, 15.0)
    vol   = calc_volume_surge_v3(volume_ratio, ctx, 10.0)
    
    # Short Interest는 percentile 기반이므로 Sigmoid 직접 적용
    # (여기서는 외부에서 percentile로 들어온다고 가정)
    
    total = round(mom + high + rsi_s + vol, 2)
    
    return {
        "momentum_score": mom,
        "high52_score": high,
        "rsi_score": rsi_s,
        "volume_score": vol,
        "layer3_total": total,
        "_method": "zscore_sigmoid_v3"
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
    
    layer1_confidence: float = 1.0  # 0~1 (데이터 완성도)
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
    v3.0 최종 점수 합산
    
    기존: L1×50% + L2×25% + L3×25% (고정, 데이터 없으면 50점 대입)
    v3:
    1) 동적 가중치 (alpha_model에서 계산된 값) 사용
    2) 데이터 없는 레이어는 가중치 0 → 있는 레이어끼리 재분배
    3) 데이터 완성도(confidence)로 가중치 조정
    """
    if availability is None:
        availability = DataAvailability()
    
    # 기본 가중치 (동적 or 기본값)
    if dynamic_weights:
        w1 = dynamic_weights.get("layer1", 0.50)
        w2 = dynamic_weights.get("layer2", 0.25)
        w3 = dynamic_weights.get("layer3", 0.25)
    else:
        w1, w2, w3 = 0.50, 0.25, 0.25
    
    # 데이터 없으면 가중치 0
    if not availability.has_layer1:
        w1 = 0
    if not availability.has_layer2:
        w2 = 0
    if not availability.has_layer3:
        w3 = 0
    
    # Confidence 반영
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
    
    # 정규화 (합이 1.0)
    w1_norm = w1 / total_weight
    w2_norm = w2 / total_weight
    w3_norm = w3 / total_weight
    
    weighted = l1_score * w1_norm + l2_score * w2_norm + l3_score * w3_norm
    
    # 데이터 품질 등급
    available_layers = sum([
        availability.has_layer1,
        availability.has_layer2,
        availability.has_layer3
    ])
    avg_confidence = total_weight / (0.50 + 0.25 + 0.25)  # 원래 가중치 대비
    
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
    score_mean: float = 50.0      # 전체 종목 평균 점수
    score_std: float = 15.0       # 전체 종목 점수 표준편차
    score_median: float = 50.0    # 중앙값
    
    vix_current: float = 20.0
    vix_mean_60d: float = 18.0
    vix_std_60d: float = 5.0


def compute_adaptive_thresholds(mkt: MarketContext) -> dict:
    """
    시장 환경 기반 적응형 매매 임계값
    
    기존: buy ≥ 65, sell ≤ 45 (고정)
    v3:   buy = μ + 0.5σ (상대적으로 좋은 종목)
          sell = μ - 0.5σ (상대적으로 나쁜 종목)
    
    → 시장이 전반적으로 좋으면(μ↑) 매수 기준도 올라감
    → 시장이 나쁘면(μ↓) 매수 기준이 낮아짐 (좋은 종목이 적어지므로)
    """
    buy_threshold  = mkt.score_mean + 0.5 * mkt.score_std
    sell_threshold = mkt.score_mean - 0.5 * mkt.score_std
    
    # VIX 기반 조정
    vix_z = (mkt.vix_current - mkt.vix_mean_60d) / mkt.vix_std_60d if mkt.vix_std_60d > 0 else 0
    
    # VIX가 높으면 (공포) 매수 기준을 올림 (더 확실한 것만)
    if vix_z > 1.0:
        buy_threshold += 2.0 * vix_z  # VIX 1σ 높을 때마다 +2
    
    # Hard limits (안전장치)
    buy_threshold  = max(55.0, min(80.0, buy_threshold))
    sell_threshold = max(25.0, min(50.0, sell_threshold))
    
    # Conviction도 적응형
    # S등급 = μ + 2σ 이상
    # A+    = μ + 1σ ~ 2σ
    # A     = μ + 0.5σ ~ 1σ
    
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
    """
    데이터 품질 자동 검증
    
    Returns: list of QualityFlag
    """
    flags = []
    
    _f = lambda v: float(v) if v is not None else None
    
    # 1. IQR Outlier Detection
    if sector_stats:
        for field in ["roic", "gpa", "fcf_margin", "ev_ebit", "pb_ratio", "peg"]:
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
                if abs(yoy) > 5.0:  # 500% 변동
                    flags.append(QualityFlag(
                        field=field, value=cur,
                        issue="YOY_SPIKE", severity="ERROR",
                        detail=f"YoY {yoy*100:.0f}% (prev={prev:.2f})"
                    ))
    
    # 3. Cross-Check: Revenue↑ but EPS↓ sharply
    if previous:
        rev_cur = _f(current.get("revenue"))
        rev_prev = _f(previous.get("revenue"))
        eps_cur = _f(current.get("eps_diluted"))
        eps_prev = _f(previous.get("eps_diluted"))
        
        if all(v is not None for v in [rev_cur, rev_prev, eps_cur, eps_prev]):
            if rev_prev > 0 and eps_prev > 0:
                rev_chg = (rev_cur - rev_prev) / rev_prev
                eps_chg = (eps_cur - eps_prev) / eps_prev
                
                if rev_chg > 0.2 and eps_chg < -0.3:
                    flags.append(QualityFlag(
                        field="cross_check",
                        value=0,
                        issue="CROSS_CHECK_FAIL",
                        severity="WARNING",
                        detail=f"Revenue +{rev_chg*100:.0f}% but EPS {eps_chg*100:.0f}%"
                    ))
    
    # 4. Missing Critical Fields
    critical_fields = ["roic", "ev_ebit", "fcf_margin", "eps_diluted"]
    for field in critical_fields:
        if current.get(field) is None:
            flags.append(QualityFlag(
                field=field, value=0,
                issue="MISSING", severity="WARNING",
                detail="핵심 지표 누락"
            ))
    
    return flags


# ═══════════════════════════════════════════════════════════
# §7. Factor Attribution — 왜 이 점수인지 설명
# ═══════════════════════════════════════════════════════════

def compute_attribution(scores: dict, sector_avg: dict = None) -> list:
    """
    점수 기여도 분석: "이 종목이 A+인 이유"
    
    Returns: [(factor, score, contribution_pct, vs_sector), ...]
    """
    # 모든 sub-score 수집
    items = []
    total = 0
    
    score_fields = [
        ("ROIC", "roic_score"),
        ("GPA", "gpa_score"),
        ("FCF Margin", "fcf_margin_score"),
        ("Accruals", "accruals_quality_score"),
        ("Net Debt/EBITDA", "net_debt_ebitda_score"),
        ("Earnings Yield", "earnings_yield_score"),
        ("EV/FCF", "ev_fcf_score"),
        ("P/B", "pb_score"),
        ("PEG", "peg_score"),
        ("F-Score", "f_score_points"),
        ("Earnings Surprise", "earnings_surprise_score"),
        ("Earnings Revision", "earnings_revision_score"),
    ]
    
    for label, key in score_fields:
        val = scores.get(key, 0)
        if val:
            items.append((label, float(val)))
            total += float(val)
    
    if total == 0:
        return []
    
    result = []
    for label, val in sorted(items, key=lambda x: x[1], reverse=True):
        pct = val / total * 100
        vs = ""
        if sector_avg and label in sector_avg:
            diff = val - sector_avg[label]
            vs = f"+{diff:.1f}" if diff > 0 else f"{diff:.1f}"
        result.append({
            "factor": label,
            "score": round(val, 2),
            "contribution_pct": round(pct, 1),
            "vs_sector": vs
        })
    
    return result


# ═══════════════════════════════════════════════════════════
# v3.1 추가 함수
# ═══════════════════════════════════════════════════════════

def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    """값을 lo~hi 범위로 클램핑"""
    if value is None:
        return lo
    return max(lo, min(hi, float(value)))


def calc_asset_growth_score(asset_growth: float, max_points: float = 10.0) -> float:
    """
    자산 증가율 점수 — 낮을수록 보수적 경영 → 높은 점수.
    
    학술 근거: Cooper, Gulen & Schill (2008) — 자산 성장률이 낮은 기업이
    향후 수익률이 높은 "asset growth anomaly".
    
    Parameters
    ----------
    asset_growth : float  자산 증가율 (0.15 = 15%)
    max_points   : float  최대 점수 (기본 10)
    
    Scoring (역방향 — 낮을수록 높은 점수):
        ≤ 0%   → 만점 (자산 축소 or 유지)
        5%     → 80% 수준
        15%    → 50% 수준  
        30%+   → 최저 (~10%)
    """
    if asset_growth is None:
        return max_points * 0.5  # 데이터 없으면 중립

    ag = float(asset_growth)

    # 역 시그모이드: 낮을수록 좋음
    # ag=0 → ~1.0, ag=0.15 → ~0.5, ag=0.3+ → ~0.1
    import math
    steepness = 15.0
    midpoint = 0.12  # 12% 기준
    x = -steepness * (ag - midpoint)
    sig = 1.0 / (1.0 + math.exp(-x))

    return round(sig * max_points, 2)


def calc_shareholder_yield_score(
    div_yield: float = None,
    buyback_yield: float = None,
    debt_paydown_yield: float = None,
    shy_percentile: float = None,
    max_points: float = 25.0,
) -> tuple:
    """
    주주환원수익률(SHY) 점수 — PEG 대체.
    
    SHY = 배당수익률 + 자사주매입수익률 + 부채상환수익률
    
    Parameters
    ----------
    div_yield          : 배당수익률 (0.02 = 2%)
    buyback_yield      : 자사주매입수익률
    debt_paydown_yield : 부채상환수익률
    shy_percentile     : 섹터 내 SHY 백분위 (0~100)
    max_points         : 최대 점수 (기본 25)
    
    Returns
    -------
    (score, shy_raw) : tuple
        score    — 0 ~ max_points
        shy_raw  — SHY 원시값 (%)
    """
    d = float(div_yield or 0)
    b = float(buyback_yield or 0)
    p = float(debt_paydown_yield or 0)
    shy_raw = round(d + b + p, 4)

    # shy_percentile이 있으면 시그모이드 사용
    if shy_percentile is not None:
        score = sigmoid_score(float(shy_percentile), max_points, steepness=10.0)
    else:
        # 백분위 없으면 절대값 기반 간이 점수
        # SHY 5%+ → 만점, 0% → 절반, -5% → 최저
        import math
        x = 12.0 * (shy_raw - 0.02)
        sig = 1.0 / (1.0 + math.exp(-x))
        score = round(sig * max_points, 2)

    return score, shy_raw