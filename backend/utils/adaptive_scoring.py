"""
utils/adaptive_scoring.py — Adaptive Scoring Engine v1.0
=========================================================
Barra USE4 + Bridgewater Adaptive Threshold Framework

학술 참조:
  - MAD Z-Score: Barra Handbook, Huber Robust Statistics (1981)
  - Winsorization: MSCI Barra USE4 (±3σ)
  - Adaptive Threshold: Bridgewater "Pure Alpha"
  - Rating Momentum: Frazzini, Israel, Moskowitz (2018) "Slow Trading"
  - Conviction Scaling: Kelly (1956), Grinold-Kahn (1999)
  - Factor Compression: Lopez de Prado (2018)
"""

import numpy as np
from scipy import stats as sp_stats


# ═══════════════════════════════════════════════════════════
#  상수
# ═══════════════════════════════════════════════════════════

# 백분위 → 등급 커팅 포인트 (정규분포 피라미드)
GRADE_PERCENTILE_CUTS = [
    (97, "S"),    # 상위  3%  (~15종목)
    (92, "A+"),   # 상위  8%  (~26종목)
    (82, "A"),    # 상위 18%  (~52종목)
    (65, "B+"),   # 상위 35%  (~88종목)
    (40, "B"),    # 상위 60%  (~130종목)
    (15, "C"),    # 상위 85%  (~130종목)
    (0,  "D"),    # 하위 15%  (~77종목)
]

# 절대 하한선: 원점수가 이 미만이면 등급 상한 적용
ABSOLUTE_FLOOR_CAPS = [
    (25, "D"),    # score < 25 → 최대 D
    (30, "C"),    # score < 30 → 최대 C
    (35, "B"),    # score < 35 → 최대 B
    (40, "B+"),   # score < 40 → 최대 B+
]

# 등급 서열 (비교용)
GRADE_ORDER = {"S": 7, "A+": 6, "A": 5, "B+": 4, "B": 3, "C": 2, "D": 1}

# 등급 → signal 매핑
GRADE_TO_SIGNAL = {
    "S": "STRONG_BUY", "A+": "STRONG_BUY",
    "A": "BUY", "B+": "BUY",
    "B": "HOLD",
    "C": "SELL",
    "D": "STRONG_SELL",
}

# 국면별 적응형 임계값 파라미터
ADAPTIVE_THRESHOLD_PARAMS = {
    "BULL":    {"absolute_floor": 35, "buy_percentile": 85},
    "NEUTRAL": {"absolute_floor": 38, "buy_percentile": 90},
    "BEAR":    {"absolute_floor": 42, "buy_percentile": 95},
    "CRISIS":  {"absolute_floor": 50, "buy_percentile": 98},
}

# EMA 파라미터
EMA_ALPHA = 0.3          # 오늘 30% + 과거 70%, half-life ≈ 2일
EMA_MIN_HISTORY = 5      # 이 이하면 α=1.0 (즉시 반영)

# Winsorization 한계
WINSOR_LIMIT = 3.0       # ±3σ (MSCI 표준)

# MAD → σ 변환 상수 (정규분포 가정)
MAD_SCALE = 1.4826


# ═══════════════════════════════════════════════════════════
#  Layer A: Cross-Sectional Normalization
# ═══════════════════════════════════════════════════════════

def mad_zscore(values):
    """
    MAD(Median Absolute Deviation) 기반 Robust Z-Score 계산.
    Barra USE4 표준 방법론.

    일반 Z-Score 대비 장점:
    - 극단값(바이오 급등 등)에 강건
    - 소수 종목이 전체 분포를 왜곡하는 것을 방지

    Fallback: MAD≈0일 때 일반 std 사용 → rank-based percentile 전환

    Args:
        values: array-like of raw scores
    Returns:
        z_scores: np.ndarray of robust z-scores (winsorized)
        None: MAD/std 모두 0일 때 (rank-based로 전환 신호)
    """
    arr = np.array(values, dtype=float)
    median = np.median(arr)
    mad = np.median(np.abs(arr - median))

    if mad < 1e-8:
        # MAD ≈ 0: 대부분 동점 → 일반 std로 fallback
        std = np.std(arr)
        if std < 1e-8:
            # std도 0: 완전 동점 → rank-based 전환 신호
            return None
        z = (arr - np.mean(arr)) / std
    else:
        z = (arr - median) / (MAD_SCALE * mad)

    # Winsorization: ±3σ 제한 (MSCI 표준)
    z = np.clip(z, -WINSOR_LIMIT, WINSOR_LIMIT)

    return z


def zscore_to_percentile(z_scores):
    """
    Z-Score → Percentile (0~100) 변환.
    정규분포 CDF 사용.
    """
    return sp_stats.norm.cdf(z_scores) * 100.0


def compute_cross_sectional_percentiles(scores):
    """
    전 종목 원점수 → Percentile Rank (0~100).

    파이프라인:
    ① MAD Z-Score (Robust) — Barra USE4
    ② MAD≈0 fallback: 일반 std 사용
    ③ std도 0: Rank-based Percentile (scipy.stats.rankdata)
    ④ Winsorization (±3σ)
    ⑤ Normal CDF → Percentile

    Args:
        scores: list/array of weighted_scores
    Returns:
        percentiles: np.ndarray (0~100)
    """
    arr = np.array(scores, dtype=float)
    z = mad_zscore(arr)

    if z is None:
        # 완전 동점 또는 극단적 분산 부족
        # → Rank-based Percentile (동점은 평균 순위)
        from scipy.stats import rankdata
        ranks = rankdata(arr, method='average')
        pct = (ranks - 1) / max(len(ranks) - 1, 1) * 100.0
        return pct

    pct = zscore_to_percentile(z)
    return pct


# ═══════════════════════════════════════════════════════════
#  등급 산출
# ═══════════════════════════════════════════════════════════

def percentile_to_grade(pct):
    """
    Percentile → 등급 변환.
    정규분포 피라미드 구조: S(3%) > A+(5%) > A(10%) > ...
    """
    for cutoff, grade in GRADE_PERCENTILE_CUTS:
        if pct >= cutoff:
            return grade
    return "D"


def apply_absolute_floor(grade, raw_score):
    """
    절대 하한선 적용.
    원점수가 낮으면 백분위 등급을 상한 제한.

    핵심 안전장치: "쓰레기 중 1등" 문제 방지
    - 전원 28점인 시장에서 1등이 S등급 받는 것을 차단
    """
    for threshold, cap_grade in ABSOLUTE_FLOOR_CAPS:
        if raw_score < threshold:
            # 현재 등급이 cap보다 높으면 cap으로 내림
            if GRADE_ORDER.get(grade, 0) > GRADE_ORDER.get(cap_grade, 0):
                return cap_grade
            return grade
    return grade  # score >= 40: 제한 없음


def grade_to_signal(grade):
    """등급 → 투자 시그널 변환."""
    return GRADE_TO_SIGNAL.get(grade, "HOLD")


# ═══════════════════════════════════════════════════════════
#  Rating Momentum (EMA Smoothing)
# ═══════════════════════════════════════════════════════════

def smooth_percentile(today_pct, yesterday_smoothed, history_days=0):
    """
    EMA 기반 등급 안정화.

    Frazzini (2018): 급격한 신호 변경은 실행 비용 증가.
    → 천천히 반영하는 것이 리스크 대비 수익률 개선.

    Args:
        today_pct: 오늘 계산된 percentile (0~100)
        yesterday_smoothed: 어제의 smoothed percentile (None이면 신규)
        history_days: 이 종목의 히스토리 일수
    Returns:
        smoothed_pct: float
    """
    if yesterday_smoothed is None or history_days < EMA_MIN_HISTORY:
        return today_pct  # 신규 종목: 즉시 반영

    alpha = EMA_ALPHA
    return alpha * today_pct + (1 - alpha) * yesterday_smoothed


# ═══════════════════════════════════════════════════════════
#  Dispersion Guard (Factor Compression 감지)
# ═══════════════════════════════════════════════════════════

def compute_dispersion_ratio(current_scores, historical_std=None):
    """
    현재 횡단면 분산 vs 역사적 분산 비교.

    Lopez de Prado (2018): 팩터 압축 시 분산이 축소되며
    신호 신뢰도가 하락 → 보수적 전환 필요.

    Args:
        current_scores: 오늘 전 종목 점수
        historical_std: 최근 60일 평균 표준편차 (DB 조회)
    Returns:
        ratio: float (1.0 = 정상, <0.5 = 팩터 압축)
    """
    current_std = float(np.std(current_scores))

    # 절대 분산 하한: std < 2이면 무조건 팩터 압축 판정
    # (정상 시장에서 500종목의 std는 보통 6~12)
    MINIMUM_STD = 2.0
    if current_std < MINIMUM_STD:
        return 0.3  # 강한 압축 신호

    if historical_std is None or historical_std < 1e-8:
        return 1.0  # 히스토리 없으면 정상 가정

    return current_std / historical_std


def dispersion_floor_boost(regime, dispersion_ratio):
    """
    팩터 압축 시 절대 하한선 상향.

    Args:
        regime: 시장 국면
        dispersion_ratio: 분산 비율 (<1이면 압축)
    Returns:
        boosted_floor: float
    """
    params = ADAPTIVE_THRESHOLD_PARAMS.get(regime, ADAPTIVE_THRESHOLD_PARAMS["NEUTRAL"])
    base_floor = params["absolute_floor"]

    if dispersion_ratio < 0.5:
        return base_floor * 1.15  # 15% 상향
    elif dispersion_ratio < 0.7:
        return base_floor * 1.05  # 5% 상향
    else:
        return 0  # 방어선 비활성


# ═══════════════════════════════════════════════════════════
#  Layer C: Adaptive Threshold (3중 방어선)
# ═══════════════════════════════════════════════════════════

def compute_adaptive_threshold(all_scores, regime, historical_std=None):
    """
    적응형 매수 임계값 계산.

    threshold = max(방어선1, 방어선2, 방어선3)

    방어선 1: Absolute Floor — 극단 시장 방어
    방어선 2: Percentile Threshold — 상대적 선별
    방어선 3: Dispersion Guard — 팩터 압축 대응

    Args:
        all_scores: 전 종목 weighted_score 배열
        regime: 시장 국면 (BULL/NEUTRAL/BEAR/CRISIS)
        historical_std: 최근 60일 평균 분산 (optional)
    Returns:
        dict: {threshold, floor, pct_threshold, disp_floor, dispersion_ratio, ...}
    """
    params = ADAPTIVE_THRESHOLD_PARAMS.get(regime, ADAPTIVE_THRESHOLD_PARAMS["NEUTRAL"])
    scores_arr = np.array(all_scores, dtype=float)

    # 방어선 1: Absolute Floor
    floor = float(params["absolute_floor"])

    # 방어선 2: Percentile Threshold
    pct_val = float(np.percentile(scores_arr, params["buy_percentile"]))

    # 방어선 3: Dispersion Guard
    disp_ratio = compute_dispersion_ratio(scores_arr, historical_std)
    disp_floor = dispersion_floor_boost(regime, disp_ratio)

    # 방어선 4: 극단 저분산 방어 (std < 2일 때)
    # 점수 차이가 거의 없으면 → 신호 무의미 → 기준을 P90 이상으로 강제 상향
    if disp_ratio < 0.4:
        # 팩터 극단 압축: percentile 기준을 P99로 상향
        extreme_pct = float(np.percentile(scores_arr, 99))
        # P99보다 1점 위로 설정 → 상위 ~5개만 후보
        disp_floor = max(disp_floor, extreme_pct + 0.01)

    # 최종: 4중 max
    threshold = max(floor, pct_val, disp_floor)

    return {
        "threshold": round(threshold, 2),
        "absolute_floor": floor,
        "percentile_threshold": round(pct_val, 2),
        "dispersion_floor": round(disp_floor, 2),
        "dispersion_ratio": round(disp_ratio, 4),
        "buy_percentile": params["buy_percentile"],
        "regime": regime,
        "score_std": round(float(np.std(scores_arr)), 4),
        "score_mean": round(float(np.mean(scores_arr)), 4),
        "candidates_above": int(np.sum(scores_arr >= threshold)),
    }


# ═══════════════════════════════════════════════════════════
#  Layer D: Conviction Score (확신도)
# ═══════════════════════════════════════════════════════════

def compute_conviction(percentile_rank, l1_pct, l2_pct, l3_pct,
                       data_completeness=1.0, dispersion_ratio=1.0):
    """
    다차원 확신도 점수.

    conviction = base × consistency × data_quality × dispersion

    Kelly (1956): 최적 비중 ∝ edge
    Grinold-Kahn (1999): position_size ∝ alpha / risk

    Returns:
        dict: {conviction_score, consistency_mult, data_quality_mult, ...}
    """
    # ① Base: 백분위 기반 (0.0 ~ 1.0)
    base = float(percentile_rank) / 100.0

    # ② Consistency: L1/L2/L3 백분위 표준편차
    layer_pcts = []
    if l1_pct is not None:
        layer_pcts.append(float(l1_pct))
    if l2_pct is not None:
        layer_pcts.append(float(l2_pct))
    if l3_pct is not None:
        layer_pcts.append(float(l3_pct))

    if len(layer_pcts) >= 2:
        rank_std = float(np.std(layer_pcts))
        if rank_std < 10:
            consistency = 1.20   # 3레이어 일관됨
        elif rank_std < 20:
            consistency = 1.00   # 보통
        elif rank_std < 30:
            consistency = 0.85   # 불일치
        else:
            consistency = 0.70   # 심한 불일치
    else:
        consistency = 0.80  # 데이터 부족

    # ③ Data Quality
    if data_completeness >= 1.0:
        dq = 1.00
    elif data_completeness >= 0.67:
        dq = 0.85
    else:
        dq = 0.60

    # ④ Dispersion
    if dispersion_ratio < 0.5:
        disp = 0.75
    elif dispersion_ratio < 0.8:
        disp = 0.90
    else:
        disp = 1.00

    conviction = round(base * consistency * dq * disp, 4)

    return {
        "conviction_score": conviction,
        "base": round(base, 4),
        "consistency_mult": consistency,
        "data_quality_mult": dq,
        "dispersion_mult": disp,
    }


# ═══════════════════════════════════════════════════════════
#  Strong Buy/Sell 적응형 판별
# ═══════════════════════════════════════════════════════════

def calc_adaptive_conviction_signal(grade, l1_pct, l2_pct, l3_pct,
                                     data_completeness=1.0):
    """
    적응형 Strong Buy/Sell 판별.

    Strong Buy: 등급 S/A+ + 각 레이어 모두 상위 25%
    Strong Sell: 등급 D + 각 레이어 모두 하위 25%
    """
    sb, ss = False, False
    reason = ""

    pcts = [p for p in [l1_pct, l2_pct, l3_pct] if p is not None]

    if grade in ("S", "A+") and data_completeness >= 0.67:
        if all(p >= 75 for p in pcts):
            sb = True
            reasons = []
            if l1_pct and l1_pct >= 90:
                reasons.append("L1 상위10%")
            if l2_pct and l2_pct >= 90:
                reasons.append("NLP 상위10%")
            if l3_pct and l3_pct >= 90:
                reasons.append("기술 상위10%")
            reason = "+".join(reasons) or "전레이어 강세"

    if grade == "D":
        if all(p <= 25 for p in pcts):
            ss = True
            reasons = []
            if l1_pct and l1_pct <= 10:
                reasons.append("L1 하위10%")
            if l2_pct and l2_pct <= 10:
                reasons.append("NLP 하위10%")
            if l3_pct and l3_pct <= 10:
                reasons.append("기술 하위10%")
            reason = "+".join(reasons) or "전레이어 약세"

    return {
        "strong_buy_signal": sb,
        "strong_sell_signal": ss,
        "conviction_reason": reason,
    }
