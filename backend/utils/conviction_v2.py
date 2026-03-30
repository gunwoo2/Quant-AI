"""
utils/conviction_v2.py — Multi-Dimensional Conviction Score v2 + Dynamic Alpha Decay
=======================================================================================
Day 4 신규 | 기존 adaptive_scoring.py의 compute_conviction을 5차원으로 확장

5차원 Conviction:
  1. 앙상블 합의 (25pt) — Disagreement 낮으면 점수 UP
  2. 예측 구간 (25pt) — Conformal 구간 좁으면 점수 UP  
  3. 팩터 다면성 (20pt) — L1+L2+L3 모두 양수면 점수 UP
  4. 시그널 신선도 (15pt) — 오래된 시그널 감점
  5. Regime 적합성 (15pt) — 현재 국면에 유리한 섹터면 점수 UP

Dynamic Alpha Decay:
  기존: 등급별 고정 유효기간 (S=10일)
  신규: IC Half-Life 실측 기반 → 데이터 부족시 고정값 Fallback

사용:
  from utils.conviction_v2 import compute_conviction_v2, get_dynamic_expiry
"""
import numpy as np
import logging
from datetime import date
from db_pool import get_cursor

logger = logging.getLogger("conviction_v2")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Conviction Score v2 (5차원)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def compute_conviction_v2(
    # 차원 1: 앙상블 합의
    disagreement=0.5,
    # 차원 2: 예측 구간
    conformal_width=50.0,
    conformal_median_width=40.0,
    # 차원 3: 팩터 다면성
    layer1_score=50, layer2_score=50, layer3_score=50,
    # 차원 4: 시그널 신선도
    signal_age_days=0, dynamic_expiry=7,
    # 차원 5: Regime 적합성
    regime_equity_impact=0.0, sector_regime_fit=0.0,
):
    """
    5차원 Conviction Score (0~100).

    왜 5차원인가:
      단순 점수가 높아도 "왜 높은지"가 다르면 확신도가 달라야 함

      Case A: L1↑, L2↑, L3↑, 3모델 동의, 구간 좁음
        → conviction 95 → 적극 매매
      Case B: L1↑, L2↓, L3↓, 모델 불일치, 구간 넓음
        → conviction 35 → 패스

    Returns:
        dict: {conviction, breakdown: {consensus, interval, diversity, freshness, regime_fit}}
    """

    # ── 차원 1: 앙상블 합의 (0~25) ──
    # disagreement: 0=완전합의 → 25pt, 0.25+ → 0pt
    consensus = max(0, 25 * (1 - min(disagreement, 0.25) * 4))

    # ── 차원 2: 예측 구간 (0~25) ──
    # width가 median보다 좁으면 점수 UP
    if conformal_median_width > 0:
        width_ratio = conformal_width / conformal_median_width
        interval_score = max(0, 25 * (1 - min(width_ratio, 2.0) / 2.0))
    else:
        interval_score = 12.5  # 데이터 없으면 중립

    # ── 차원 3: 팩터 다면성 (0~20) ──
    # L1, L2, L3 모두 50 이상 = 3레이어 동의
    layers = [layer1_score, layer2_score, layer3_score]
    above_avg = sum(1 for s in layers if s is not None and s > 50)
    below_avg = sum(1 for s in layers if s is not None and s < 35)

    if above_avg >= 3:
        diversity = 20.0    # 3레이어 전부 강함
    elif above_avg == 2:
        diversity = 14.0    # 2레이어 강함
    elif above_avg == 1 and below_avg == 0:
        diversity = 10.0    # 1레이어만 강, 나머지 중립
    elif below_avg >= 2:
        diversity = 3.0     # 2레이어 이상 약함
    else:
        diversity = 8.0     # 혼재

    # ── 차원 4: 시그널 신선도 (0~15) ──
    # 생성 직후 = 15pt, 만료 직전 = 0pt
    if dynamic_expiry > 0:
        freshness = max(0, 15 * (1 - signal_age_days / max(dynamic_expiry, 1)))
    else:
        freshness = 7.5  # 데이터 없으면 중립

    # ── 차원 5: Regime 적합성 (0~15) ──
    # equity_impact: -1(CRISIS)~+1(RISK_ON)
    # sector_regime_fit: -1~+1 (해당 섹터가 현재 국면에서 유리한지)
    combined_regime = (regime_equity_impact + sector_regime_fit + 1) / 3
    regime_score = max(0, min(15, 15 * combined_regime))

    # ── 합산 ──
    total = round(consensus + interval_score + diversity + freshness + regime_score, 1)
    total = max(0, min(100, total))

    return {
        "conviction": total,
        "breakdown": {
            "consensus": round(consensus, 1),
            "prediction_interval": round(interval_score, 1),
            "factor_diversity": round(diversity, 1),
            "freshness": round(freshness, 1),
            "regime_fit": round(regime_score, 1),
        }
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Dynamic Alpha Decay — IC Half-Life 기반 시그널 만료
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DEFAULT_EXPIRY = {
    "S": 10, "A+": 8, "A": 6, "B+": 5, "B": 4, "C": 3, "D": 2,
}


def get_dynamic_expiry(grade, calc_date=None):
    """
    IC Half-Life 기반 동적 시그널 만료.

    방법:
      1. alpha_decay_daily 테이블에서 해당 등급의 horizon별 IC 조회
      2. IC가 최대값의 50%로 떨어지는 시점 = Half-Life
      3. Half-Life = 시그널 유효기간

    예: S등급 IC 추이
      1일: IC=0.12 (최대)
      5일: IC=0.10
      10일: IC=0.06 ← 50% → Half-Life = 10일!

    Fallback: 데이터 부족시 DEFAULT_EXPIRY (원칙 2)
    """
    if calc_date is None:
        calc_date = date.today()

    fallback = DEFAULT_EXPIRY.get(grade, 5)

    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT horizon_days, avg_ic
                FROM alpha_decay_daily
                WHERE grade = %s
                  AND calc_date >= %s - INTERVAL '90 days'
                  AND avg_ic IS NOT NULL
                ORDER BY horizon_days ASC
            """, (grade, calc_date))
            rows = cur.fetchall()

        if not rows or len(rows) < 3:
            return fallback

        ic_curve = [(int(r["horizon_days"]), float(r["avg_ic"])) for r in rows]
        max_ic = max(ic for _, ic in ic_curve)

        if max_ic <= 0:
            return max(2, fallback // 2)  # IC가 전부 음수 → 짧은 만료

        half_ic = max_ic * 0.5
        for days, ic in ic_curve:
            if ic <= half_ic:
                return max(2, min(20, days))  # 2~20일 범위

        # 모든 horizon에서 50% 안 떨어지면 → 가장 긴 horizon
        return min(20, ic_curve[-1][0])

    except Exception as e:
        logger.debug(f"[DECAY] dynamic expiry 조회 실패: {e}")
        return fallback


def get_sector_regime_fit(sector_code, regime_name):
    """
    섹터 × Regime 적합도 (-1 ~ +1).

    경험적 규칙:
      RISK_ON: 기술(+1), 소비재(+0.5), 유틸리티(-0.5)
      CRISIS: 유틸리티(+0.5), 헬스케어(+0.3), 기술(-0.5)
    """
    SECTOR_REGIME_FIT = {
        # sector_code: {regime: fit}
        "XLK": {"RISK_ON_RALLY": 1.0, "GOLDILOCKS": 0.7, "REFLATION": 0.0,
                "STAGFLATION": -0.5, "DEFLATION_SCARE": -0.5, "CRISIS": -0.8},
        "XLF": {"RISK_ON_RALLY": 0.8, "GOLDILOCKS": 0.5, "REFLATION": 0.5,
                "STAGFLATION": -0.3, "DEFLATION_SCARE": -0.7, "CRISIS": -1.0},
        "XLE": {"RISK_ON_RALLY": 0.3, "GOLDILOCKS": 0.2, "REFLATION": 1.0,
                "STAGFLATION": 0.5, "DEFLATION_SCARE": -0.8, "CRISIS": -0.5},
        "XLV": {"RISK_ON_RALLY": -0.2, "GOLDILOCKS": 0.3, "REFLATION": 0.0,
                "STAGFLATION": 0.5, "DEFLATION_SCARE": 0.5, "CRISIS": 0.8},
        "XLU": {"RISK_ON_RALLY": -0.5, "GOLDILOCKS": 0.0, "REFLATION": -0.3,
                "STAGFLATION": 0.3, "DEFLATION_SCARE": 0.7, "CRISIS": 0.5},
        "XLY": {"RISK_ON_RALLY": 0.8, "GOLDILOCKS": 0.5, "REFLATION": 0.2,
                "STAGFLATION": -0.7, "DEFLATION_SCARE": -0.5, "CRISIS": -0.7},
        "XLP": {"RISK_ON_RALLY": -0.3, "GOLDILOCKS": 0.1, "REFLATION": 0.0,
                "STAGFLATION": 0.5, "DEFLATION_SCARE": 0.5, "CRISIS": 0.6},
        "XLI": {"RISK_ON_RALLY": 0.6, "GOLDILOCKS": 0.5, "REFLATION": 0.7,
                "STAGFLATION": -0.3, "DEFLATION_SCARE": -0.5, "CRISIS": -0.6},
        "XLRE": {"RISK_ON_RALLY": 0.3, "GOLDILOCKS": 0.4, "REFLATION": -0.2,
                 "STAGFLATION": -0.5, "DEFLATION_SCARE": 0.3, "CRISIS": -0.3},
        "XLC": {"RISK_ON_RALLY": 0.7, "GOLDILOCKS": 0.5, "REFLATION": 0.0,
                "STAGFLATION": -0.3, "DEFLATION_SCARE": -0.3, "CRISIS": -0.5},
        "XLB": {"RISK_ON_RALLY": 0.4, "GOLDILOCKS": 0.3, "REFLATION": 0.8,
                "STAGFLATION": -0.2, "DEFLATION_SCARE": -0.6, "CRISIS": -0.5},
    }

    sector_str = str(sector_code).upper() if sector_code else ""
    profile = SECTOR_REGIME_FIT.get(sector_str, {})
    return profile.get(regime_name, 0.0)