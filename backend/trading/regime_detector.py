"""
regime_detector.py — 시장 국면(Regime) 감지 v3.1
=================================================
SPY 이동평균선 + VIX Z-score 기반으로 BULL/NEUTRAL/BEAR/CRISIS 판단.

v3.0 → v3.1 변경:
  ① VIX Z-score: (VIX - MA20) / STD20 기반 위기 감지
  ② VIX 절대값 + Z-score 이중 검증
  ③ ALERT 레벨 추가 (Z-score 1.5~2.0: 국면 한 단계 다운그레이드)
  ④ RegimeResult에 vix_zscore 필드 추가

학술 근거: Ang & Timmermann(2012) "Regime Changes and Financial Markets"
  → 다중 지표 조합이 단일 지표 대비 국면 전환 감지 정확도 30% 향상
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Optional


@dataclass
class RegimeResult:
    """시장 국면 판단 결과"""
    regime: str                       # BULL, NEUTRAL, BEAR, CRISIS
    spy_price: float
    spy_ma50: float
    spy_ma200: float
    vix_close: Optional[float]
    vix_zscore: Optional[float] = None  # v3.1 신규
    multiplier: float = 0.7


def detect_regime(
    spy_closes: pd.Series,
    vix_close: Optional[float] = None,
    vix_history: Optional[pd.Series] = None,
    vix_crisis: float = 30.0,
    vix_zscore_crisis: float = 2.0,
    vix_zscore_alert: float = 1.5,
) -> RegimeResult:
    """
    SPY 종가 + VIX → 시장 국면 판단 (v3.1)

    Parameters
    ----------
    spy_closes : pd.Series
        SPY 일별 종가 (최소 200일, 최신이 마지막)
    vix_close : float, optional
        당일 VIX 종가
    vix_history : pd.Series, optional
        최근 20일+ VIX 종가 (Z-score 계산용)
    vix_crisis : float
        CRISIS 판단 VIX 절대값 (기본 30)
    vix_zscore_crisis : float
        VIX Z-score > 이 값 → CRISIS 후보 (기본 2.0)
    vix_zscore_alert : float
        VIX Z-score > 이 값 → 한 단계 다운그레이드 (기본 1.5)

    Returns
    -------
    RegimeResult
    """
    if len(spy_closes) < 200:
        return RegimeResult(
            regime="NEUTRAL",
            spy_price=float(spy_closes.iloc[-1]) if len(spy_closes) > 0 else 0,
            spy_ma50=0, spy_ma200=0, vix_close=vix_close,
            multiplier=0.7,
        )

    price = float(spy_closes.iloc[-1])
    ma50  = float(spy_closes.rolling(50).mean().iloc[-1])
    ma200 = float(spy_closes.rolling(200).mean().iloc[-1])

    above_50  = price > ma50
    above_200 = price > ma200

    # ── Step 1: MA 기반 기본 국면 ──
    if above_200 and above_50:
        regime = "BULL"
        mult = 1.0
    elif above_200 and not above_50:
        regime = "NEUTRAL"
        mult = 0.7
    elif not above_200 and above_50:
        # 200MA 아래지만 50MA 위 = 회복 초기
        regime = "BEAR"
        mult = 0.4
    else:
        regime = "BEAR"
        mult = 0.4

    # ── Step 2: VIX Z-score 계산 ──
    vix_z = None
    if vix_history is not None and len(vix_history) >= 20 and vix_close is not None:
        vix_ma20  = float(vix_history.tail(20).mean())
        vix_std20 = float(vix_history.tail(20).std())
        if vix_std20 > 0.1:
            vix_z = round((vix_close - vix_ma20) / vix_std20, 2)

    # ── Step 3: VIX 기반 국면 조정 ──
    if vix_close is not None:
        # CRISIS 승격: 이중 검증 (절대값 OR Z-score)
        crisis_by_level = vix_close > vix_crisis
        crisis_by_zscore = vix_z is not None and vix_z > vix_zscore_crisis

        # MA 기반 이미 약세이고 + VIX 위험
        if regime in ("BEAR",) and (crisis_by_level or crisis_by_zscore):
            regime = "CRISIS"
            mult = 0.2

        # BULL/NEUTRAL에서 VIX 급등 → 한 단계 다운그레이드
        elif vix_z is not None and vix_z > vix_zscore_alert:
            if regime == "BULL":
                regime = "NEUTRAL"
                mult = 0.7
            elif regime == "NEUTRAL":
                regime = "BEAR"
                mult = 0.4

        # 추가: 양쪽 MA 아래 + VIX 절대값 높음 → CRISIS
        if not above_200 and not above_50:
            if crisis_by_level or crisis_by_zscore:
                regime = "CRISIS"
                mult = 0.2

    return RegimeResult(
        regime=regime,
        spy_price=round(price, 2),
        spy_ma50=round(ma50, 2),
        spy_ma200=round(ma200, 2),
        vix_close=vix_close,
        vix_zscore=vix_z,
        multiplier=mult,
    )


def detect_regime_from_dict(price_dict: dict, vix_close=None, vix_history=None) -> RegimeResult:
    """딕셔너리(date→price) 입력도 지원"""
    df = pd.Series(price_dict).sort_index().astype(float)
    vix_s = pd.Series(vix_history).sort_index().astype(float) if vix_history else None
    return detect_regime(df, vix_close=vix_close, vix_history=vix_s)
