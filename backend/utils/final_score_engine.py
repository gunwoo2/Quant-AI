"""
utils/final_score_engine.py — 최종 점수 합산 엔진 v3.1
=================================================================

v3.0 → v3.1 변경:
  - 결측시 50 대체 제거 → 동적 가중치 재분배
  - 데이터 품질 지표 (data_completeness)
  - Strong Buy/Sell 조건 세분화

기본 가중치: L1(50%) + L2(25%) + L3(25%)
결측 레이어 → 가중치를 나머지 레이어에 비례 재분배
"""
import numpy as np
from utils.scoring_engine import _clamp


# ── 기본 가중치 ──
W_L1 = 0.50
W_L2 = 0.25
W_L3 = 0.25

# ── Shrinkage: 결측 레이어 → 사전확률(50)로 당기는 정도 ──
SHRINKAGE_ALPHA = 0.15   # 결측 1개당 15%를 50 방향으로


def calc_final_weighted_score(
    layer1_score: float = None,
    layer2_score: float = None,
    layer3_score: float = None,
) -> dict:
    """
    최종 가중합산 점수 계산

    Parameters
    ----------
    layer1_score : Layer 1 퀀트 점수 (0~100 or None)
    layer2_score : Layer 2 NLP 점수 (0~100 or None)
    layer3_score : Layer 3 기술 점수 (0~100 or None)

    Returns
    -------
    dict:
      weighted_score     : 최종 가중합산 점수 (0~100)
      data_completeness  : 데이터 완성도 (0.0~1.0)
      l1_weight_actual   : 실제 적용된 L1 가중치
      l2_weight_actual   : 실제 적용된 L2 가중치
      l3_weight_actual   : 실제 적용된 L3 가중치
      confidence_level   : "HIGH" / "MEDIUM" / "LOW"
    """
    layers = {
        "L1": (layer1_score, W_L1),
        "L2": (layer2_score, W_L2),
        "L3": (layer3_score, W_L3),
    }

    # ── 가용 레이어와 결측 레이어 분리 ──
    available = {}
    missing_count = 0

    for name, (score, base_w) in layers.items():
        if score is not None:
            available[name] = (float(score), base_w)
        else:
            missing_count += 1

    # ── 전부 결측 → 50.0 ──
    if not available:
        return {
            "weighted_score": 50.0,
            "data_completeness": 0.0,
            "l1_weight_actual": 0.0,
            "l2_weight_actual": 0.0,
            "l3_weight_actual": 0.0,
            "confidence_level": "LOW",
        }

    # ── 동적 가중치 재분배 ──
    total_available_w = sum(w for _, w in available.values())
    actual_weights = {}
    for name, (score, base_w) in available.items():
        actual_weights[name] = base_w / total_available_w  # 비례 재분배

    # ── 가중합산 ──
    weighted = 0.0
    for name, (score, _) in available.items():
        weighted += score * actual_weights[name]

    # ── Shrinkage: 결측 레이어가 많을수록 50으로 수렴 ──
    shrinkage = missing_count * SHRINKAGE_ALPHA
    weighted = weighted * (1.0 - shrinkage) + 50.0 * shrinkage

    weighted = _clamp(round(weighted, 2), 0.0, 100.0)

    # ── 데이터 완성도 ──
    data_completeness = len(available) / 3.0

    # ── 신뢰도 ──
    if data_completeness >= 1.0:
        confidence = "HIGH"
    elif data_completeness >= 0.67:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    return {
        "weighted_score":     weighted,
        "data_completeness":  round(data_completeness, 2),
        "l1_weight_actual":   round(actual_weights.get("L1", 0.0), 4),
        "l2_weight_actual":   round(actual_weights.get("L2", 0.0), 4),
        "l3_weight_actual":   round(actual_weights.get("L3", 0.0), 4),
        "confidence_level":   confidence,
    }


def calc_conviction_signal(
    weighted_score: float,
    layer1_score: float = None,
    layer2_score: float = None,
    layer3_score: float = None,
    data_completeness: float = 1.0,
) -> dict:
    """
    Strong Buy / Strong Sell 시그널 판별

    v3.0: weighted>=72 & l1>=65 & l2>=60
    v3.1: 데이터 완성도 조건 추가 + 다층 확인 강화

    Returns
    -------
    dict:
      strong_buy_signal  : bool
      strong_sell_signal : bool
      conviction_reason  : str (사유)
    """
    l1 = layer1_score if layer1_score is not None else 50.0
    l2 = layer2_score if layer2_score is not None else 50.0
    l3 = layer3_score if layer3_score is not None else 50.0

    strong_buy = False
    strong_sell = False
    reason = ""

    # Strong Buy: 최소 2개 레이어 데이터 필요
    if data_completeness >= 0.67:
        if weighted_score >= 72 and l1 >= 65:
            # 추가 조건: L2 또는 L3 중 하나라도 55 이상
            if l2 >= 55 or l3 >= 55:
                strong_buy = True
                reasons = []
                if l1 >= 70: reasons.append("L1 강세")
                if l2 >= 60: reasons.append("NLP 긍정")
                if l3 >= 65: reasons.append("기술적 강세")
                reason = " + ".join(reasons) if reasons else "종합 고점수"

    # Strong Sell: L1 기반 (가장 신뢰성 높은 레이어)
    if weighted_score <= 35 and l1 <= 40:
        strong_sell = True
        reasons = []
        if l1 <= 30: reasons.append("L1 약세")
        if l2 <= 35: reasons.append("NLP 부정")
        if l3 <= 30: reasons.append("기술적 약세")
        reason = " + ".join(reasons) if reasons else "종합 저점수"

    return {
        "strong_buy_signal":  strong_buy,
        "strong_sell_signal": strong_sell,
        "conviction_reason":  reason,
    }
