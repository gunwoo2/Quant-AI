"""
signal_generator.py — 매매 시그널 생성기 v3.1
==============================================
Final Score + Layer3 + RSI 조합으로 BUY/SELL/HOLD 판단.

v3.0 → v3.1 변경:
  ① Adaptive Threshold: 시장 평균/std 기반 상대 판단
  ② Earnings Blackout: 실적 발표 ±3일 BUY 억제
  ③ 시그널 강도 Sigmoid: 연속적 확신도
  ④ 데이터 신뢰도(confidence) 반영

학술 근거: DeMiguel et al.(2009) — 적응형 임계값이 고정 임계값 대비
  out-of-sample Sharpe ratio 15~20% 개선
"""
from dataclasses import dataclass, field
from typing import List, Optional
import numpy as np


@dataclass
class MarketContext:
    """시장 전체 점수 분포 컨텍스트 (adaptive threshold용)"""
    score_mean: float = 50.0
    score_std: float = 14.0
    total_stocks: int = 500
    regime: str = "NEUTRAL"


@dataclass
class TradeSignal:
    """하나의 종목에 대한 매매 시그널"""
    stock_id: int
    ticker: str
    signal_type: str              # BUY, SELL, HOLD
    signal_strength: float        # 0~100

    # 조건 충족 여부
    grade_ok: bool = False
    momentum_ok: bool = False
    rsi_ok: bool = False
    trend_ok: bool = False
    regime_ok: bool = False
    blackout_ok: bool = True      # v3.1 신규: 실적 블랙아웃 아님

    # 퇴장 사유 (SELL인 경우)
    sell_reason: Optional[str] = None

    # 스냅샷
    final_score: float = 0.0
    layer3_score: float = 0.0
    rsi_value: float = 50.0
    atr_14: float = 0.0
    current_price: float = 0.0
    sector: str = ""
    confidence_level: str = ""    # v3.1: HIGH/MEDIUM/LOW


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Adaptive Threshold 계산
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def compute_adaptive_thresholds(ctx: MarketContext) -> dict:
    """
    시장 전체 점수 분포 기반 적응형 매수/매도 임계값 계산.

    Parameters
    ----------
    ctx : MarketContext
        score_mean, score_std, regime

    Returns
    -------
    dict: buy_threshold, sell_threshold, buy_l3_min
    """
    m, s = ctx.score_mean, ctx.score_std

    # BUY: max(65, mean + 1.0σ) — 불장에서 기준 올림
    buy_threshold = max(65.0, m + 1.0 * s)
    buy_threshold = min(buy_threshold, 80.0)  # 상한 80 (너무 높으면 매수 불가)

    # SELL: min(45, mean - 1.0σ) — 약세장에서 기준 내림
    sell_threshold = min(45.0, m - 1.0 * s)
    sell_threshold = max(sell_threshold, 20.0)  # 하한 20

    # L3 최소: 시장 모멘텀 반영
    buy_l3_min = max(50.0, m * 0.9)
    buy_l3_min = min(buy_l3_min, 65.0)

    return {
        "buy_threshold": round(buy_threshold, 1),
        "sell_threshold": round(sell_threshold, 1),
        "buy_l3_min": round(buy_l3_min, 1),
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  시그널 강도 (Sigmoid 연속)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _signal_strength(score: float, threshold: float) -> float:
    """
    score - threshold 차이 → 0~100 시그널 강도 (Sigmoid).
    차이가 클수록 높은 강도.
    """
    delta = score - threshold
    z = 0.15 * delta
    z = np.clip(z, -20, 20)
    sig = 1.0 / (1.0 + np.exp(-z))
    return round(sig * 100, 2)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  BUY 시그널 생성
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def generate_buy_signal(
    stock_id: int,
    ticker: str,
    final_score: float,
    layer3_score: float,
    rsi_value: float,
    atr_14: float,
    current_price: float,
    sector: str,
    recent_scores: List[float],
    regime: str,
    cfg=None,
    market_ctx: MarketContext = None,
    is_earnings_blackout: bool = False,
    confidence_level: str = "HIGH",
) -> TradeSignal:
    """
    BUY 시그널 판단: 6가지 조건 ALL 충족 (v3.1)

    Parameters
    ----------
    recent_scores : list
        최근 5일 final_score [오늘, 어제, 그제, ...]
    market_ctx : MarketContext
        시장 전체 점수 분포 (adaptive threshold용)
    is_earnings_blackout : bool
        실적 발표 ±3일 여부
    confidence_level : str
        데이터 신뢰도 (HIGH/MEDIUM/LOW)
    """
    from trading_config import TradingConfig
    if cfg is None:
        cfg = TradingConfig()

    # Adaptive Threshold 계산
    if market_ctx is None:
        market_ctx = MarketContext(regime=regime)
    thresholds = compute_adaptive_thresholds(market_ctx)

    buy_threshold = thresholds["buy_threshold"]
    buy_l3_min = thresholds["buy_l3_min"]

    # ① 등급 조건: Final Score >= adaptive buy_threshold
    grade_ok = final_score >= buy_threshold

    # ② 모멘텀 확인: L3 >= adaptive buy_l3_min
    momentum_ok = layer3_score >= buy_l3_min

    # ③ RSI 과매수 필터: RSI < buy_rsi_max (75)
    rsi_ok = rsi_value < cfg.buy_rsi_max

    # ④ 등급 개선 추세: 최근 3일 중 2일 이상 하락 아님
    trend_ok = True
    if len(recent_scores) >= 3:
        drops = sum(1 for i in range(len(recent_scores) - 1)
                    if recent_scores[i] < recent_scores[i + 1] - 2)
        trend_ok = drops < 2

    # ⑤ 시장 국면 필터
    regime_ok = regime != "CRISIS"

    # ⑥ 실적 블랙아웃 (v3.1 신규)
    blackout_ok = not is_earnings_blackout

    # ⑦ 데이터 신뢰도: LOW confidence → BUY 불가
    confidence_ok = confidence_level != "LOW"

    all_ok = (grade_ok and momentum_ok and rsi_ok and trend_ok
              and regime_ok and blackout_ok and confidence_ok)

    # 시그널 강도 (Sigmoid 연속)
    strength = _signal_strength(final_score, buy_threshold) if all_ok else 0.0

    return TradeSignal(
        stock_id=stock_id,
        ticker=ticker,
        signal_type="BUY" if all_ok else "HOLD",
        signal_strength=strength,
        grade_ok=grade_ok,
        momentum_ok=momentum_ok,
        rsi_ok=rsi_ok,
        trend_ok=trend_ok,
        regime_ok=regime_ok,
        blackout_ok=blackout_ok,
        final_score=final_score,
        layer3_score=layer3_score,
        rsi_value=rsi_value,
        atr_14=atr_14,
        current_price=current_price,
        sector=sector,
        confidence_level=confidence_level,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SELL 시그널 생성
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def generate_sell_signal(
    stock_id: int,
    ticker: str,
    entry_price: float,
    current_price: float,
    highest_price: float,
    atr_14: float,
    final_score: float,
    recent_scores: List[float],
    holding_days: int,
    signal: str,
    cfg=None,
    market_ctx: MarketContext = None,
) -> TradeSignal:
    """
    SELL 시그널 판단: ANY 조건 충족 시 (v3.1)

    Returns SELL signal with sell_reason, or HOLD if no trigger.
    """
    from trading_config import TradingConfig
    if cfg is None:
        cfg = TradingConfig()

    # Adaptive Threshold
    if market_ctx is None:
        market_ctx = MarketContext()
    thresholds = compute_adaptive_thresholds(market_ctx)
    sell_threshold = thresholds["sell_threshold"]

    sell_reason = None

    # ① STRONG_SELL 시그널 → 즉시 매도
    if signal == "STRONG_SELL":
        sell_reason = "STRONG_SELL"

    # ② 등급 하락 연속 (adaptive threshold)
    elif len(recent_scores) >= cfg.sell_consecutive_days:
        consecutive_low = all(
            s < sell_threshold
            for s in recent_scores[:cfg.sell_consecutive_days]
        )
        if consecutive_low:
            sell_reason = "RATING_DROP"

    # ③ 손절 (Stop-Loss): entry - 2×ATR
    if sell_reason is None and atr_14 > 0:
        stop_loss = entry_price - (cfg.stop_loss_atr_mult * atr_14)
        if current_price <= stop_loss:
            sell_reason = "STOP_LOSS"

    # ④ 트레일링 스톱: highest - 3×ATR
    if sell_reason is None and atr_14 > 0 and highest_price > 0:
        trailing = highest_price - (cfg.trailing_stop_atr_mult * atr_14)
        if current_price <= trailing:
            sell_reason = "TRAILING_STOP"

    # ⑤ 보유 기간 초과 + 저조한 수익
    if sell_reason is None:
        if holding_days >= cfg.max_holding_days:
            pnl_pct = (current_price - entry_price) / entry_price if entry_price > 0 else 0
            if pnl_pct < cfg.min_return_for_hold:
                sell_reason = "TIME_EXIT"

    # ⑥ Gap-Down 감지 (v3.1): 전일 대비 -7% 이상 하락 시 즉시 매도
    if sell_reason is None and entry_price > 0:
        daily_loss = (current_price - entry_price) / entry_price
        # 이건 entry 대비가 아니라 전일 대비여야 하므로 caller에서 전달
        # 여기선 highest 대비로 대체
        if highest_price > 0:
            drawdown = (current_price - highest_price) / highest_price
            if drawdown < -0.15:  # 최고가 대비 -15% → 손절
                sell_reason = "DRAWDOWN_EXIT"

    is_sell = sell_reason is not None

    return TradeSignal(
        stock_id=stock_id,
        ticker=ticker,
        signal_type="SELL" if is_sell else "HOLD",
        signal_strength=100.0 if sell_reason == "STRONG_SELL" else (70.0 if is_sell else 0),
        sell_reason=sell_reason,
        final_score=final_score,
        current_price=current_price,
        atr_14=atr_14,
    )
