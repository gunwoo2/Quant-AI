"""
signal_generator.py — 매매 시그널 생성기
기존 Final Score + Layer3 + RSI 조합으로 BUY/SELL/HOLD 판단
"""
from dataclasses import dataclass
from typing import List, Optional


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

    # 퇴장 사유 (SELL인 경우)
    sell_reason: Optional[str] = None

    # 스냅샷
    final_score: float = 0.0
    layer3_score: float = 0.0
    rsi_value: float = 50.0
    atr_14: float = 0.0
    current_price: float = 0.0
    sector: str = ""


def generate_buy_signal(
    stock_id: int,
    ticker: str,
    final_score: float,
    layer3_score: float,
    rsi_value: float,
    atr_14: float,
    current_price: float,
    sector: str,
    recent_scores: List[float],   # 최근 5일 final_score 리스트 (최신 먼저)
    regime: str,
    cfg=None,
) -> TradeSignal:
    """
    BUY 시그널 판단: 5가지 조건 ALL 충족

    Parameters
    ----------
    recent_scores : list
        최근 5일 final_score [오늘, 어제, 그제, ...]
    """
    from trading_config import TradingConfig
    if cfg is None:
        cfg = TradingConfig()

    # ① 등급 조건: Final Score >= buy_score_min (65)
    grade_ok = final_score >= cfg.buy_score_min

    # ② 모멘텀 확인: L3 >= buy_l3_min (55)
    momentum_ok = layer3_score >= cfg.buy_l3_min

    # ③ RSI 과매수 필터: RSI < buy_rsi_max (75)
    rsi_ok = rsi_value < cfg.buy_rsi_max

    # ④ 등급 개선 추세: 최근 5일 내 하락 없음 (현재 >= 5일 전 최소값)
    trend_ok = True
    if len(recent_scores) >= 3:
        # 최근 3일 중 2일 이상 하락이면 trend 불량
        drops = sum(1 for i in range(len(recent_scores)-1)
                    if recent_scores[i] < recent_scores[i+1] - 2)
        trend_ok = drops < 2

    # ⑤ 시장 국면 필터: CRISIS가 아니면 OK
    regime_ok = regime != "CRISIS"

    all_ok = grade_ok and momentum_ok and rsi_ok and trend_ok and regime_ok

    # 시그널 강도 = final_score 기반 (60~100 범위)
    strength = min(100, max(0, (final_score - 50) * 2)) if all_ok else 0

    return TradeSignal(
        stock_id=stock_id,
        ticker=ticker,
        signal_type="BUY" if all_ok else "HOLD",
        signal_strength=round(strength, 2),
        grade_ok=grade_ok,
        momentum_ok=momentum_ok,
        rsi_ok=rsi_ok,
        trend_ok=trend_ok,
        regime_ok=regime_ok,
        final_score=final_score,
        layer3_score=layer3_score,
        rsi_value=rsi_value,
        atr_14=atr_14,
        current_price=current_price,
        sector=sector,
    )


def generate_sell_signal(
    stock_id: int,
    ticker: str,
    entry_price: float,
    current_price: float,
    highest_price: float,
    atr_14: float,
    final_score: float,
    recent_scores: List[float],   # 최근 N일 (최신 먼저)
    holding_days: int,
    signal: str,                  # 현재 시그널 (STRONG_SELL 등)
    cfg=None,
) -> TradeSignal:
    """
    SELL 시그널 판단: ANY 조건 충족 시

    Returns SELL signal with sell_reason, or HOLD if no trigger.
    """
    from trading_config import TradingConfig
    if cfg is None:
        cfg = TradingConfig()

    sell_reason = None

    # ① STRONG_SELL 시그널 → 즉시 매도
    if signal == "STRONG_SELL":
        sell_reason = "STRONG_SELL"

    # ② 등급 하락 연속
    elif len(recent_scores) >= cfg.sell_consecutive_days:
        consecutive_low = all(
            s < cfg.sell_score_max for s in recent_scores[:cfg.sell_consecutive_days]
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
            pnl_pct = (current_price - entry_price) / entry_price
            if pnl_pct < cfg.min_return_for_hold:
                sell_reason = "TIME_EXIT"

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
