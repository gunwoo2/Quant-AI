"""
layer2_scoring.py — Layer 2 NLP/Sentiment Scoring Engine v3.1
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

batch_layer2_v2.py 에서 import 하여 사용.
scoring_engine.py의 Sigmoid 함수를 공유.

주요 개선:
  1. 뉴스 감성 → 신뢰도 가중 + 최근성 + Sigmoid 보정
  2. 애널리스트 → Sigmoid 변환 + 컨센서스 모멘텀
  3. 내부자 → 금액 비중 + 최근성 가중 + Sigmoid 정규화
  4. 최종 통합 → 동적 가중 (결측 시 재분배)
"""

import math
import numpy as np
from typing import Optional, Dict, List, Tuple


# ═══════════════════════════════════════════════════════════════
#  공통 유틸 (scoring_engine.py 의존 최소화 — 독립 실행 가능)
# ═══════════════════════════════════════════════════════════════

def _safe_float(v, default: float = 0.0) -> float:
    """안전한 float 변환"""
    if v is None:
        return default
    try:
        return float(v)
    except (ValueError, TypeError):
        return default


def _sigmoid(x: float, midpoint: float = 50.0, steepness: float = 0.1) -> float:
    """범용 시그모이드: 0~100 → 0~100"""
    try:
        z = -steepness * (x - midpoint)
        return 100.0 / (1.0 + math.exp(z))
    except OverflowError:
        return 0.0 if z > 0 else 100.0


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


# ═══════════════════════════════════════════════════════════════
#  1. 뉴스 감성 점수 (News Sentiment Score)
# ═══════════════════════════════════════════════════════════════

def calc_news_sentiment_score(
    avg_sentiment: float,         # -1 ~ +1 FinBERT 평균
    total_articles: int = 0,
    positive_count: int = 0,
    negative_count: int = 0,
    neutral_count: int = 0,
    avg_confidence: float = 0.5,  # FinBERT 평균 confidence
    recent_24h_ratio: float = 0.5,  # 24시간 내 뉴스 비율
) -> Dict:
    """
    뉴스 감성 → 0~100 점수
    
    v3.0: (avg_sentiment + 1) * 50 (단순 선형)
    v3.1: Sigmoid 보정 + 신뢰도 가중 + 최근성 + 볼륨 보너스
    
    학술 근거:
    - Tetlock (2007): 미디어 감성이 주가 수익률 예측
    - 뉴스 수가 많을수록 시그널 신뢰도 증가 (Law of Large Numbers)
    """
    avg_s = _safe_float(avg_sentiment, 0.0)
    total = max(0, int(_safe_float(total_articles, 0)))
    pos   = max(0, int(_safe_float(positive_count, 0)))
    neg   = max(0, int(_safe_float(negative_count, 0)))
    conf  = _safe_float(avg_confidence, 0.5)
    recency = _safe_float(recent_24h_ratio, 0.5)
    
    # ── (A) Base Score: Sigmoid 변환 ──
    # avg_sentiment [-1, +1] → linear [0, 100] → Sigmoid 보정
    linear_score = (avg_s + 1.0) * 50.0
    # Sigmoid: 중립(50) 근처 민감, 극단 포화
    base_score = _sigmoid(linear_score, midpoint=50.0, steepness=0.08)
    
    # ── (B) Polarity Ratio Bonus ──
    # 긍정 기사 비율이 높으면 보너스, 부정이면 페널티
    if total > 0:
        polarity = (pos - neg) / total  # -1 ~ +1
        polarity_adj = polarity * 10.0   # ±10점
    else:
        polarity_adj = 0.0
    
    # ── (C) Volume Confidence ──
    # 뉴스 수가 많을수록 점수의 확신도 증가 (중립에서 벗어남)
    # 1건: 0.3, 5건: 0.7, 10건+: 0.9, 20건+: 1.0
    if total == 0:
        vol_confidence = 0.0
    else:
        vol_confidence = min(1.0, 0.3 + 0.07 * total)
    
    # ── (D) FinBERT Confidence 가중 ──
    # 모델 자체의 확신이 낮으면 중립 쪽으로 조정
    model_weight = 0.5 + 0.5 * min(1.0, conf)  # 0.5 ~ 1.0
    
    # ── (E) Recency Boost ──
    # 최근 24h 뉴스 비율이 높으면 시의성 보너스
    recency_mult = 0.8 + 0.4 * recency  # 0.8 ~ 1.2
    
    # ── 통합 ──
    # 중립(50)에서의 편차에 신뢰도/확신도 곱하기
    deviation = (base_score - 50.0 + polarity_adj) * vol_confidence * model_weight * recency_mult
    final_score = round(_clamp(50.0 + deviation), 2)
    
    return {
        "news_score": final_score,
        "news_base_score": round(base_score, 2),
        "news_polarity_adj": round(polarity_adj, 2),
        "news_vol_confidence": round(vol_confidence, 3),
        "news_model_weight": round(model_weight, 3),
        "news_recency_mult": round(recency_mult, 3),
        "news_article_count": total,
    }


# ═══════════════════════════════════════════════════════════════
#  2. 애널리스트 평가 점수 (Analyst Rating Score)
# ═══════════════════════════════════════════════════════════════

def calc_analyst_rating_score(
    buy_count: int = 0,
    hold_count: int = 0,
    sell_count: int = 0,
    upgrade_count_90d: int = 0,
    downgrade_count_90d: int = 0,
    target_price: float = None,
    current_price: float = None,
) -> Dict:
    """
    애널리스트 레이팅 → 0~100 점수
    
    v3.0: buy_score*0.40 + upgrade_momentum*0.30 + coverage_bonus*0.30
    v3.1: Sigmoid 기반 + 가격목표 괴리율 + 컨센서스 모멘텀
    
    학술 근거:
    - Womack (1996): 애널리스트 추천 변경이 주가에 유의미한 영향
    - Barber et al. (2001): 컨센서스 변화가 단순 수준보다 예측력 높음
    """
    buy  = max(0, int(_safe_float(buy_count, 0)))
    hold = max(0, int(_safe_float(hold_count, 0)))
    sell = max(0, int(_safe_float(sell_count, 0)))
    up   = max(0, int(_safe_float(upgrade_count_90d, 0)))
    down = max(0, int(_safe_float(downgrade_count_90d, 0)))
    
    total = buy + hold + sell
    
    if total == 0:
        return {
            "analyst_score": 50.0,  # 데이터 없으면 중립
            "analyst_buy_ratio_score": 50.0,
            "analyst_momentum_score": 50.0,
            "analyst_coverage_score": 0.0,
            "analyst_target_score": 50.0,
            "analyst_count": 0,
            "analyst_data_available": False,
        }
    
    # ── (A) Buy Ratio Score (40%) ──
    buy_pct = buy / total * 100.0  # 0~100
    # Sigmoid: 50% buy → 50점, 80% buy → ~85점, 20% buy → ~15점
    buy_ratio_score = _sigmoid(buy_pct, midpoint=50.0, steepness=0.06)
    
    # ── (B) Consensus Momentum Score (30%) ──
    # 업그레이드 vs 다운그레이드 모멘텀
    net_change = up - down
    total_changes = up + down
    if total_changes > 0:
        momentum_ratio = net_change / total_changes  # -1 ~ +1
        momentum_linear = (momentum_ratio + 1.0) * 50.0  # 0~100
        momentum_score = _sigmoid(momentum_linear, midpoint=50.0, steepness=0.08)
    else:
        momentum_score = 50.0  # 변화 없으면 중립
    
    # ── (C) Coverage Depth Score (15%) ──
    # 많은 애널리스트가 커버 = 정보 풍부
    # 5명: ~40점, 10명: ~65점, 20명: ~85점, 30명+: ~95점
    coverage_score = _sigmoid(total, midpoint=12.0, steepness=0.15)
    
    # ── (D) Target Price Score (15%) ──
    tp = _safe_float(target_price)
    cp = _safe_float(current_price)
    if tp > 0 and cp > 0:
        upside = (tp - cp) / cp  # -1 ~ +∞
        # 업사이드 10% → ~65점, 30% → ~85점, -20% → ~20점
        upside_linear = (upside + 0.5) / 1.0 * 100.0  # -50%→0, 0%→50, 50%→100
        target_score = _sigmoid(_clamp(upside_linear, 0, 100), midpoint=50.0, steepness=0.07)
    else:
        target_score = 50.0  # 데이터 없으면 중립
    
    # ── 통합 ──
    final = round(_clamp(
        buy_ratio_score * 0.40 +
        momentum_score * 0.30 +
        coverage_score * 0.15 +
        target_score * 0.15
    ), 2)
    
    return {
        "analyst_score": final,
        "analyst_buy_ratio_score": round(buy_ratio_score, 2),
        "analyst_momentum_score": round(momentum_score, 2),
        "analyst_coverage_score": round(coverage_score, 2),
        "analyst_target_score": round(target_score, 2),
        "analyst_count": total,
        "analyst_data_available": True,
    }


# ═══════════════════════════════════════════════════════════════
#  3. 내부자 거래 점수 (Insider Trading Score)
# ═══════════════════════════════════════════════════════════════

def calc_insider_trading_score(
    c_level_buy_count: int = 0,
    c_level_sell_count: int = 0,
    c_level_buy_value: float = 0.0,
    c_level_sell_value: float = 0.0,
    insider_buy_count: int = 0,
    insider_sell_count: int = 0,
    total_buy_value: float = 0.0,
    total_sell_value: float = 0.0,
    large_sell_alert: bool = False,
    market_cap: float = None,
    days_since_last_buy: int = None,
    days_since_last_sell: int = None,
) -> Dict:
    """
    내부자 거래 → 0~100 점수
    
    v3.0: 50 + c_level*15 + cluster*20 - sell*3 - large_sell*40
    v3.1: 금액 비중 + 최근성 가중 + Sigmoid 정규화
    
    학술 근거:
    - Lakonishok & Lee (2001): 내부자 매수가 매도보다 예측력 높음
    - Seyhun (1998): C-Level 거래가 일반 임원보다 정보 우위
    - Cohen et al. (2012): 비정기적 거래가 예측력 보유
    """
    c_buy  = max(0, int(_safe_float(c_level_buy_count, 0)))
    c_sell = max(0, int(_safe_float(c_level_sell_count, 0)))
    c_buy_v  = _safe_float(c_level_buy_value, 0.0)
    c_sell_v = _safe_float(c_level_sell_value, 0.0)
    i_buy  = max(0, int(_safe_float(insider_buy_count, 0)))
    i_sell = max(0, int(_safe_float(insider_sell_count, 0)))
    t_buy_v  = _safe_float(total_buy_value, 0.0)
    t_sell_v = _safe_float(total_sell_value, 0.0)
    mcap = _safe_float(market_cap)
    
    # 데이터 없으면 중립
    if (i_buy + i_sell + c_buy + c_sell) == 0:
        return {
            "insider_score": 50.0,
            "insider_c_level_score": 50.0,
            "insider_cluster_score": 50.0,
            "insider_volume_score": 50.0,
            "insider_recency_score": 50.0,
            "insider_data_available": False,
        }
    
    # ── (A) C-Level Signal Score (35%) ──
    # C-Level 순매수 건수 기반
    c_net = c_buy - c_sell
    # 순매수 2건 이상이면 강한 매수 시그널
    c_linear = 50.0 + c_net * 20.0  # 1건=70, 2건=90, -1건=30
    c_level_score = _sigmoid(_clamp(c_linear, 0, 100), midpoint=50.0, steepness=0.10)
    
    # ── (B) Cluster Buy Score (25%) ──
    # 여러 내부자 동시 매수 → 집단 정보 우위
    net_buyers = i_buy - i_sell
    if i_buy >= 3 and net_buyers > 0:
        cluster_linear = 50.0 + net_buyers * 15.0
    elif i_buy >= 1:
        cluster_linear = 50.0 + net_buyers * 8.0
    else:
        cluster_linear = 50.0 - i_sell * 5.0
    cluster_score = _sigmoid(_clamp(cluster_linear, 0, 100), midpoint=50.0, steepness=0.08)
    
    # ── (C) Volume Significance Score (25%) ──
    # 매수금액 vs 매도금액 비율 + 시총 대비 비중
    net_value = t_buy_v - t_sell_v
    
    if mcap and mcap > 0:
        # 시총 대비 순매수 비율
        value_ratio = net_value / mcap * 100  # %
        # 0.01% = 유의미, 0.1% = 강한 시그널
        vol_linear = 50.0 + value_ratio * 500.0  # 0.01%→55, 0.1%→100
    else:
        # 시총 모르면 절대 금액 기준
        if net_value > 0:
            vol_linear = 50.0 + min(net_value / 1_000_000, 50.0)  # $1M=+1점씩
        else:
            vol_linear = 50.0 + max(net_value / 1_000_000, -50.0)
    volume_score = _sigmoid(_clamp(vol_linear, 0, 100), midpoint=50.0, steepness=0.08)
    
    # ── (D) Recency Score (15%) ──
    # 최근 매수일이 가까울수록 시의성 높음
    d_buy  = _safe_float(days_since_last_buy, 30)
    d_sell = _safe_float(days_since_last_sell, 30)
    
    # 매수 최근성 (7일 이내=100, 30일=50, 60일+=20)
    buy_recency = max(0, 100 - d_buy * 2.5)
    sell_recency = max(0, 100 - d_sell * 2.5)
    
    # 최근 매수 있고 매도 없으면 보너스
    if d_buy < d_sell:
        recency_linear = 50.0 + (buy_recency - sell_recency) * 0.3
    else:
        recency_linear = 50.0 - (sell_recency - buy_recency) * 0.2
    recency_score = _sigmoid(_clamp(recency_linear, 0, 100), midpoint=50.0, steepness=0.08)
    
    # ── Large Sell Alert Override ──
    if large_sell_alert:
        c_level_score = min(c_level_score, 20.0)  # 강제 하향
        volume_score = min(volume_score, 25.0)
    
    # ── 통합 ──
    final = round(_clamp(
        c_level_score * 0.35 +
        cluster_score * 0.25 +
        volume_score * 0.25 +
        recency_score * 0.15
    ), 2)
    
    return {
        "insider_score": final,
        "insider_c_level_score": round(c_level_score, 2),
        "insider_cluster_score": round(cluster_score, 2),
        "insider_volume_score": round(volume_score, 2),
        "insider_recency_score": round(recency_score, 2),
        "insider_data_available": True,
    }


# ═══════════════════════════════════════════════════════════════
#  4. Layer 2 최종 통합 점수 (Dynamic Weighting)
# ═══════════════════════════════════════════════════════════════

# 기본 가중치
BASE_W_NEWS     = 0.40
BASE_W_ANALYST  = 0.35
BASE_W_INSIDER  = 0.25

def calc_layer2_total_score(
    news_score: float = None,
    analyst_score: float = None,
    insider_score: float = None,
    news_data_available: bool = False,
    analyst_data_available: bool = False,
    insider_data_available: bool = False,
) -> Dict:
    """
    Layer 2 최종 통합 점수
    
    v3.0: news*0.40 + analyst*0.35 + insider*0.25 (결측→50)
    v3.1: 데이터 가용성 기반 동적 가중치 재분배
    
    규칙:
    - 3개 모두 가용: 기본 가중치 사용
    - 2개 가용: 누락분 가중치를 남은 2개에 비례 분배
    - 1개 가용: 해당 점수 100% + 중립(50) 쪽으로 축소
    - 0개 가용: 50.0 (완전 중립)
    """
    # 가용 서브점수 수집
    components = []
    total_base_weight = 0.0
    
    if news_data_available and news_score is not None:
        components.append(("news", _safe_float(news_score, 50.0), BASE_W_NEWS))
        total_base_weight += BASE_W_NEWS
    
    if analyst_data_available and analyst_score is not None:
        components.append(("analyst", _safe_float(analyst_score, 50.0), BASE_W_ANALYST))
        total_base_weight += BASE_W_ANALYST
    
    if insider_data_available and insider_score is not None:
        components.append(("insider", _safe_float(insider_score, 50.0), BASE_W_INSIDER))
        total_base_weight += BASE_W_INSIDER
    
    available_count = len(components)
    
    if available_count == 0:
        # 데이터 전무 → 완전 중립
        return {
            "layer2_total_score": 50.0,
            "layer2_confidence": 0.0,
            "layer2_components_used": 0,
            "layer2_news_weight": 0.0,
            "layer2_analyst_weight": 0.0,
            "layer2_insider_weight": 0.0,
            "layer2_data_quality": "NO_DATA",
        }
    
    # 동적 가중치 재분배
    weighted_sum = 0.0
    actual_weights = {}
    for name, score, base_w in components:
        # 기본 가중치를 전체 가용 가중치 합으로 정규화
        actual_w = base_w / total_base_weight
        actual_weights[name] = actual_w
        weighted_sum += score * actual_w
    
    # 데이터 부족 시 중립 쪽으로 축소 (shrinkage)
    # 3개: 100% 신뢰, 2개: 85%, 1개: 60%
    confidence_map = {3: 1.0, 2: 0.85, 1: 0.60}
    confidence = confidence_map[available_count]
    
    # 중립(50)과 혼합
    final_score = round(_clamp(
        weighted_sum * confidence + 50.0 * (1.0 - confidence)
    ), 2)
    
    # 데이터 품질 레벨
    if available_count == 3:
        quality = "FULL"
    elif available_count == 2:
        quality = "PARTIAL"
    else:
        quality = "MINIMAL"
    
    return {
        "layer2_total_score": final_score,
        "layer2_confidence": round(confidence, 2),
        "layer2_components_used": available_count,
        "layer2_news_weight": round(actual_weights.get("news", 0.0), 4),
        "layer2_analyst_weight": round(actual_weights.get("analyst", 0.0), 4),
        "layer2_insider_weight": round(actual_weights.get("insider", 0.0), 4),
        "layer2_data_quality": quality,
    }

