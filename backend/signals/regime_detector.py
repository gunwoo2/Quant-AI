"""
signal/regime_detector.py — 다중 지표 시장 국면 판단 v2
========================================================
v3.2 (SPY MA + VIX만) → v3.3 (5가지 지표 앙상블)

지표:
  1. SPY 이동평균: 50일/200일 Golden/Death Cross
  2. VIX 수준: 15이하=BULL, 20~30=NEUTRAL/BEAR, 30+=CRISIS
  3. SPY 모멘텀: 20일 수익률 → 추세 강도
  4. 시장 폭(Breadth): MA50 위 종목 비율 (DB에서 가져올 수 있을 때)
  5. 금리 스프레드 대용: SPY vs 유틸리티 상대강도 (방어주 선호 감지)

앙상블 투표 → 최종 국면 결정
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Optional


@dataclass
class RegimeResult:
    """국면 판단 결과"""
    regime: str = "NEUTRAL"         # BULL / NEUTRAL / BEAR / CRISIS
    spy_price: float = 0.0
    spy_ma50: float = 0.0
    spy_ma200: float = 0.0
    vix_close: Optional[float] = None
    multiplier: float = 0.7
    # v2 추가
    spy_momentum_20d: float = 0.0   # 20일 수익률
    trend_score: int = 0            # -2 ~ +2 (Bear ~ Bull)
    signals: dict = None            # 개별 지표 투표

    def __post_init__(self):
        if self.signals is None:
            self.signals = {}


def detect_regime(
    spy_series: pd.Series,
    vix_close: Optional[float] = None,
    breadth_pct: Optional[float] = None,
) -> RegimeResult:
    """
    다중 지표 앙상블로 시장 국면 판단.

    Parameters
    ----------
    spy_series : pd.Series
        SPY 종가 시계열 (최소 250일, index=date)
    vix_close : float, optional
        현재 VIX 종가
    breadth_pct : float, optional
        MA50 위 종목 비율 (0~1)
    """
    result = RegimeResult()

    if spy_series.empty or len(spy_series) < 50:
        return result

    spy_series = spy_series.sort_index().astype(float)
    current = float(spy_series.iloc[-1])
    result.spy_price = current

    votes = {}  # 지표별 투표: +1=BULL, 0=NEUTRAL, -1=BEAR, -2=CRISIS

    # ── 1. 이동평균 (Golden/Death Cross) ──
    ma50 = float(spy_series.tail(50).mean())
    ma200 = float(spy_series.tail(200).mean()) if len(spy_series) >= 200 else ma50
    result.spy_ma50 = round(ma50, 2)
    result.spy_ma200 = round(ma200, 2)

    if current > ma50 > ma200:
        votes["ma_cross"] = 1       # Golden Cross + 가격 위 → BULL
    elif current > ma50 and ma50 <= ma200:
        votes["ma_cross"] = 0       # 가격은 위인데 DC → NEUTRAL
    elif current < ma50 and ma50 > ma200:
        votes["ma_cross"] = 0       # 가격 아래인데 GC → NEUTRAL
    elif current < ma50 < ma200:
        votes["ma_cross"] = -1      # Death Cross + 가격 아래 → BEAR
    else:
        votes["ma_cross"] = 0

    # 가격 vs MA200 이격도
    if ma200 > 0:
        ma200_gap = (current - ma200) / ma200
        if ma200_gap < -0.20:
            votes["ma_cross"] = -2  # MA200 -20% 이하 → CRISIS

    # ── 2. VIX 수준 ──
    result.vix_close = vix_close
    if vix_close is not None:
        if vix_close >= 35:
            votes["vix"] = -2       # CRISIS
        elif vix_close >= 25:
            votes["vix"] = -1       # BEAR
        elif vix_close >= 18:
            votes["vix"] = 0        # NEUTRAL
        else:
            votes["vix"] = 1        # BULL (저변동성)
    else:
        votes["vix"] = 0

    # ── 3. SPY 20일 모멘텀 ──
    if len(spy_series) >= 20:
        mom_20d = (current / float(spy_series.iloc[-20]) - 1)
        result.spy_momentum_20d = round(mom_20d, 4)

        if mom_20d > 0.05:
            votes["momentum"] = 1    # +5% 이상 → 강한 상승
        elif mom_20d > 0.0:
            votes["momentum"] = 0    # 약한 상승
        elif mom_20d > -0.05:
            votes["momentum"] = 0    # 약한 하락
        elif mom_20d > -0.10:
            votes["momentum"] = -1   # 하락 추세
        else:
            votes["momentum"] = -2   # 급락 (-10% 이상)
    else:
        votes["momentum"] = 0

    # ── 4. 시장 폭 (Breadth) ──
    if breadth_pct is not None:
        if breadth_pct > 0.70:
            votes["breadth"] = 1     # 70%+ 위 → 건강한 상승장
        elif breadth_pct > 0.50:
            votes["breadth"] = 0     # 50~70% → 보통
        elif breadth_pct > 0.30:
            votes["breadth"] = -1    # 30~50% → 약세
        else:
            votes["breadth"] = -2    # 30% 미만 → 매우 약세
    # breadth 없으면 투표 안 함

    # ── 5. 변동성 추세 (ATR 기반 대용) ──
    if len(spy_series) >= 40:
        recent_vol = float(spy_series.tail(20).pct_change().std())
        older_vol = float(spy_series.tail(40).head(20).pct_change().std())
        if older_vol > 0:
            vol_ratio = recent_vol / older_vol
            if vol_ratio > 1.5:
                votes["vol_trend"] = -1    # 변동성 급등
            elif vol_ratio < 0.7:
                votes["vol_trend"] = 1     # 변동성 축소 (안정)
            else:
                votes["vol_trend"] = 0
        else:
            votes["vol_trend"] = 0
    else:
        votes["vol_trend"] = 0

    result.signals = votes

    # ── 앙상블 투표 → 최종 국면 ──
    total_score = sum(votes.values())
    num_votes = len(votes)
    result.trend_score = total_score

    # 가중 평균 기반 판단
    if num_votes > 0:
        avg_score = total_score / num_votes
    else:
        avg_score = 0

    # CRISIS 우선: 하나라도 -2가 있고 평균이 음수면
    has_crisis = any(v <= -2 for v in votes.values())
    if has_crisis and avg_score < -0.5:
        result.regime = "CRISIS"
        result.multiplier = 0.3
    elif avg_score >= 0.5:
        result.regime = "BULL"
        result.multiplier = 1.0
    elif avg_score >= -0.3:
        result.regime = "NEUTRAL"
        result.multiplier = 0.7
    elif avg_score >= -1.0:
        result.regime = "BEAR"
        result.multiplier = 0.5
    else:
        result.regime = "CRISIS"
        result.multiplier = 0.3

    return result
