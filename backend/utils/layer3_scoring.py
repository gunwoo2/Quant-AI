"""
utils/layer3_scoring.py — Layer 3 기술 지표 스코어링 엔진 v3.1
=================================================================

v3.0 → v3.1 변경:
  - 6개 지표 전부 계단식 if-else → Sigmoid/연속 함수
  - 만점 배분 유지: Mom(30) + 52W(20) + R²(15) + RSI(15) + OBV(10) + Vol(10) = 100

설계 원칙:
  - DB/API 의존 없음 (순수 계산)
  - 함수 시그니처 하위호환 유지
  - scoring_engine.py 공용 함수 사용
"""
import numpy as np
from utils.scoring_engine import sigmoid_score, _clamp


# ═══════════════════════════════════════════════════════════════
#  ① Relative Momentum 12-1 vs SPY (30점 만점)
# ═══════════════════════════════════════════════════════════════

def score_relative_momentum(rel_mom_pct: float) -> float:
    """
    v3.0: 6단계 계단 (0/5/12/18/24/30)
    v3.1: Sigmoid 연속 (mid=10%, k=0.15)
          → rel_mom_pct = 0% → ~15점, +20% → ~25점, -20% → ~5점
    """
    if rel_mom_pct is None:
        return 0.0
    return sigmoid_score(rel_mom_pct, mid=10.0, k=0.15, out_min=0.0, out_max=30.0)


# ═══════════════════════════════════════════════════════════════
#  ② 52W High Position (20점 만점)
# ═══════════════════════════════════════════════════════════════

def score_52w_high(dist52: float) -> float:
    """
    v3.0: 5단계 계단 (0/5/10/15/20)
    v3.1: Sigmoid 연속 (mid=0.85, k=15)
          → dist=0.95 → ~17점, dist=0.75 → ~6점
          52주 고점에 가까울수록 높은 점수
    """
    if dist52 is None:
        return 0.0
    return sigmoid_score(dist52, mid=0.85, k=15.0, out_min=0.0, out_max=20.0)


# ═══════════════════════════════════════════════════════════════
#  ③ Trend Stability R² (15점 만점)
# ═══════════════════════════════════════════════════════════════

def score_trend_r2(r2: float, slope: float = None) -> float:
    """
    v3.0: 4단계 계단 (0/5/10/15)
    v3.1: R² Sigmoid + slope 보너스
          base: sigmoid(R², mid=0.5, k=8) → 0~12
          bonus: slope > 0 이면 +3 (기관 매집 패턴)
    """
    if r2 is None:
        return 0.0
    base = sigmoid_score(r2, mid=0.5, k=8.0, out_min=0.0, out_max=12.0)
    slope_bonus = 3.0 if (slope is not None and slope > 0 and r2 >= 0.4) else 0.0
    return _clamp(base + slope_bonus, 0.0, 15.0)


# ═══════════════════════════════════════════════════════════════
#  ④ RSI 14일 (15점 만점)
# ═══════════════════════════════════════════════════════════════

def score_rsi(rsi14: float) -> float:
    """
    v3.0: 6단계 계단 (0/5/8/10/12/15)
    v3.1: 역-U자 커브 (40~60이 최적, 양 극단 감소)
    
    설계 의도:
      - 40~60 (중립 강세): 만점 15
      - 30~40, 60~70: 약간 감소
      - <30 과매도: 반등 가능성 → 중간 점수 유지 (12)
      - >70 과매수: 위험 → 급감
      - >80 극단 과매수: 0에 수렴
      
    구현: 피크 50 기준 가우시안 + 과매도 보정
    """
    if rsi14 is None:
        return 0.0

    # 가우시안 피크: RSI=50에서 최고, 양쪽으로 감소
    # σ=20 → RSI 30~70에서 높은 점수 유지
    gaussian = np.exp(-0.5 * ((rsi14 - 50) / 20) ** 2)
    base = gaussian * 15.0

    # 과매도 보정: RSI < 30이면 반등 가능성 → 최소 8점 보장
    if rsi14 < 30:
        oversold_bonus = (30 - rsi14) / 30 * 4.0  # 최대 +4
        base = max(base, 8.0 + oversold_bonus)

    # 극단 과매수 패널티: RSI > 75이면 급감
    if rsi14 > 75:
        overbought_penalty = (rsi14 - 75) / 25 * base * 0.8
        base -= overbought_penalty

    return _clamp(round(base, 2), 0.0, 15.0)


# ═══════════════════════════════════════════════════════════════
#  ⑤ OBV (10점 만점)
# ═══════════════════════════════════════════════════════════════

def score_obv(obv_trend: str, price_trend: str) -> float:
    """
    v3.0: 6단계 계단 (0/2/4/6/8/10)
    v3.1: OBV 방향 + 가격 방향 결합 매트릭스 (연속화 제한적 → 매트릭스 유지 + 소수점)
    
    사실 OBV는 이산 3-state(UP/FLAT/DOWN)이므로 완전한 연속화 불가.
    → 매트릭스 점수 유지하되, 중간값 세분화
    """
    matrix = {
        ("UP",   "UP"):   10.0,   # OBV↑ + 가격↑ = 정상 상승
        ("UP",   "FLAT"):  8.5,   # OBV↑ + 가격보합 = 기관 매집
        ("UP",   "DOWN"):  6.5,   # 긍정 다이버전스
        ("FLAT", "UP"):    5.0,   # 가격만 상승 = 불안
        ("FLAT", "FLAT"):  4.0,   # 중립
        ("FLAT", "DOWN"):  3.0,   # 완만한 하락
        ("DOWN", "UP"):    2.0,   # 부정 다이버전스 (경고)
        ("DOWN", "FLAT"):  1.0,   # 매도 압력
        ("DOWN", "DOWN"):  0.0,   # OBV↓ + 가격↓ = 하락 확인
    }
    return matrix.get((obv_trend, price_trend), 4.0)


# ═══════════════════════════════════════════════════════════════
#  ⑥ Volume Surge (10점 만점)
# ═══════════════════════════════════════════════════════════════

def score_volume_surge(surge_ratio: float) -> float:
    """
    v3.0: 4단계 계단 (0/2/4/7/10)
    v3.1: Sigmoid 연속 (mid=1.5, k=2.5)
          → ratio=1.0 → ~2.5점, ratio=2.0 → ~6점, ratio=3.0 → ~9점
    """
    if surge_ratio is None:
        return 0.0
    return sigmoid_score(surge_ratio, mid=1.5, k=2.5, out_min=0.0, out_max=10.0)


# ═══════════════════════════════════════════════════════════════
#  최종 Layer 3 점수 합산
# ═══════════════════════════════════════════════════════════════

def calc_layer3_score(
    rel_mom_pct: float,
    dist52: float,
    trend_r2: float,
    trend_slope: float,
    rsi14: float,
    obv_trend: str,
    price_trend: str,
    vol_surge_ratio: float,
) -> dict:
    """
    Layer 3 기술 지표 통합 점수 계산

    Parameters
    ----------
    rel_mom_pct     : Relative momentum vs SPY (%)
    dist52          : 현재가 / 52주 고점 비율 (0~1)
    trend_r2        : 90일 추세 R²
    trend_slope     : 90일 추세 기울기
    rsi14           : RSI 14일
    obv_trend       : OBV 추세 ("UP"/"FLAT"/"DOWN")
    price_trend     : 가격 추세 ("UP"/"FLAT"/"DOWN")
    vol_surge_ratio : 거래량 / 20일 평균 비율

    Returns
    -------
    dict: 6개 서브 점수 + layer3_technical_score
    """
    mom_s   = score_relative_momentum(rel_mom_pct)
    h52_s   = score_52w_high(dist52)
    r2_s    = score_trend_r2(trend_r2, trend_slope)
    rsi_s   = score_rsi(rsi14)
    obv_s   = score_obv(obv_trend, price_trend)
    vol_s   = score_volume_surge(vol_surge_ratio)

    total = round(mom_s + h52_s + r2_s + rsi_s + obv_s + vol_s, 2)
    total = _clamp(total, 0.0, 100.0)

    return {
        "relative_momentum_score": round(mom_s, 2),
        "high_52w_score":          round(h52_s, 2),
        "trend_stability_score":   round(r2_s, 2),
        "rsi_score":               round(rsi_s, 2),
        "obv_score":               round(obv_s, 2),
        "volume_surge_score":      round(vol_s, 2),
        "layer3_technical_score":  total,
    }

