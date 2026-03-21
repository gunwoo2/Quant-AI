"""
risk/risk_manager.py — 8중 안전장치 리스크 관리 엔진
=====================================================
[종목 레벨 6중]
  ① Hard Stop       — entry - N×ATR (국면별 N 동적)
  ② Trailing Stop   — 고점 대비 (수익률별 강화)
  ③ Rating Stop     — STRONG_SELL + 점수 하락 속도
  ④ Volatility Stop — ATR 급등 시 손절 강화
  ⑤ Time Decay      — 장기 보유 + 저수익 → 기회비용
  ⑥ Liquidity Stop  — 거래량 급감 시 탈출

[포트폴리오 레벨 2중]
  ⑦ Correlation Stop — 포폴 내 상관관계 급등
  ⑧ Portfolio Risk   — 일/주/월 손실 한도
"""
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import date


# ═══════════════════════════════════════════════════════════
#  결과 데이터
# ═══════════════════════════════════════════════════════════

@dataclass
class RiskCheck:
    """리스크 체크 결과"""
    should_sell: bool = False
    partial_sell_pct: float = 0.0       # 부분 매도 비율 (0.5 = 50%)
    reason: Optional[str] = None
    severity: str = "NONE"              # NONE / LOW / MEDIUM / HIGH / CRITICAL
    new_trailing_stop: Optional[float] = None
    tighten_stop: bool = False          # 손절 강화 필요?
    # 포트폴리오 레벨
    portfolio_halt: bool = False
    portfolio_reduce: bool = False
    portfolio_liquidate: bool = False


# ═══════════════════════════════════════════════════════════
#  종목 레벨 8중 안전장치
# ═══════════════════════════════════════════════════════════

def check_position_risk(
    entry_price: float,
    current_price: float,
    highest_price: float,
    atr_14: float,
    atr_20d_avg: float,
    stop_loss_price: float,
    trailing_stop: float,
    final_score: float,
    recent_scores: List[float],
    signal: str,
    holding_days: int,
    volume_today: float = 0,
    volume_20d_avg: float = 0,
    cfg=None,
) -> RiskCheck:
    """
    개별 포지션 8중 안전장치 체크.

    Parameters
    ----------
    atr_14 : float          현재 14일 ATR
    atr_20d_avg : float     20일 평균 ATR (변동성 기준선)
    volume_today : float    당일 거래량
    volume_20d_avg : float  20일 평균 거래량

    Returns
    -------
    RiskCheck
    """
    if cfg is None:
        from risk.trading_config import TradingConfig
        cfg = TradingConfig()

    result = RiskCheck()
    pnl_pct = (current_price - entry_price) / entry_price if entry_price > 0 else 0

    # ── ① Hard Stop (국면별 ATR 배수) ──
    if current_price <= stop_loss_price:
        result.should_sell = True
        result.reason = "HARD_STOP"
        result.severity = "CRITICAL"
        return result

    # ── ② Trailing Stop (수익률별 강화) ──
    if atr_14 > 0:
        # 수익률에 따라 트레일링 타이트닝
        if pnl_pct >= 0.20:
            trail_mult = 1.0      # +20% 이상: 매우 타이트
        elif pnl_pct >= 0.10:
            trail_mult = 1.5      # +10% 이상: 타이트
        else:
            trail_mult = cfg.trailing_stop_atr_mult

        new_trailing = highest_price - (trail_mult * atr_14)

        if new_trailing > trailing_stop:
            result.new_trailing_stop = round(new_trailing, 2)

        effective_trailing = max(trailing_stop, new_trailing) if new_trailing else trailing_stop

        if current_price <= effective_trailing and effective_trailing > stop_loss_price:
            result.should_sell = True
            result.reason = "TRAILING_STOP"
            result.severity = "HIGH"
            return result

    # ── ③ Rating Stop (STRONG_SELL + 점수 하락 속도) ──
    if signal == "STRONG_SELL":
        result.should_sell = True
        result.reason = "STRONG_SELL_SIGNAL"
        result.severity = "HIGH"
        return result

    # 점수 하락 속도 감지: 3일간 -15점 이상
    if len(recent_scores) >= 3:
        score_drop = recent_scores[0] - recent_scores[-1]  # 최신 - 3일전 (음수=하락)
        if score_drop < -15:
            result.should_sell = True
            result.reason = f"SCORE_FREEFALL({score_drop:+.0f}pts/3d)"
            result.severity = "HIGH"
            return result

    # 연속 저점수
    sell_score_max = getattr(cfg, "sell_score_max", 40)
    sell_days = getattr(cfg, "sell_consecutive_days", 3)
    if len(recent_scores) >= sell_days:
        if all(s < sell_score_max for s in recent_scores[:sell_days]):
            result.should_sell = True
            result.reason = f"RATING_DROP({sell_days}d<{sell_score_max})"
            result.severity = "MEDIUM"
            return result

    # ── ④ Volatility Stop (ATR 급등) ──
    if atr_20d_avg > 0 and atr_14 > 0:
        atr_ratio = atr_14 / atr_20d_avg

        # ATR 3배 급등 → 즉시 50% 축소
        if atr_ratio >= 3.0:
            result.partial_sell_pct = 0.50
            result.reason = f"VOLATILITY_SPIKE(ATR x{atr_ratio:.1f})"
            result.severity = "HIGH"
            return result

        # ATR 2배 급등 → 손절 강화 (1단계 타이트)
        if atr_ratio >= 2.0:
            result.tighten_stop = True
            result.severity = "MEDIUM"
            # 즉시 매도는 아니지만, 트레일링 스톱 1단계 상향
            tighter_trail = highest_price - (1.5 * atr_14)
            if tighter_trail > (result.new_trailing_stop or trailing_stop):
                result.new_trailing_stop = round(tighter_trail, 2)

    # ── ⑤ Time Decay (기회비용) ──
    max_hold = getattr(cfg, "max_holding_days", 90)

    if holding_days >= 90 and pnl_pct < 0.08:
        result.should_sell = True
        result.reason = f"TIME_DECAY_90D(pnl={pnl_pct:.1%})"
        result.severity = "MEDIUM"
        return result

    if holding_days >= 60 and pnl_pct < 0.05:
        result.should_sell = True
        result.reason = f"TIME_DECAY_60D(pnl={pnl_pct:.1%})"
        result.severity = "MEDIUM"
        return result

    if holding_days >= 30 and pnl_pct < 0.03:
        # 30일 관찰 모드 — 경고만
        result.severity = "LOW"
        result.reason = f"TIME_WATCH_30D(pnl={pnl_pct:.1%})"
        # 매도는 안 함, 모니터링

    # ── ⑥ Liquidity Stop (거래량 급감) ──
    if volume_20d_avg > 0 and volume_today > 0:
        vol_ratio = volume_today / volume_20d_avg

        if vol_ratio < 0.3:
            # 거래량 30% 미만 — 유동성 경고
            # 3일 연속은 batch에서 카운트 (여기서는 1일 기준)
            result.severity = "MEDIUM"
            result.reason = f"LOW_LIQUIDITY(vol={vol_ratio:.0%})"
            # 매도 여부는 연속일 기준으로 batch에서 판단

    # ── Profit Taking (이익실현) ──
    profit_take = getattr(cfg, "profit_take_pct", 0.25)
    if pnl_pct >= profit_take:
        # 전량 매도가 아닌 부분 익절 (50%)
        result.partial_sell_pct = 0.50
        result.reason = f"PROFIT_TAKE({pnl_pct:.1%}>={profit_take:.0%})"
        result.severity = "LOW"
        return result

    return result


# ═══════════════════════════════════════════════════════════
#  포트폴리오 레벨 리스크 체크
# ═══════════════════════════════════════════════════════════

def check_portfolio_risk(
    daily_return: float,
    weekly_return: float,
    monthly_return: float,
    avg_correlation: float = 0.0,
    cfg=None,
) -> RiskCheck:
    """
    포트폴리오 레벨 리스크 체크.

    Parameters
    ----------
    daily_return : float    당일 수익률 (예: -0.025 = -2.5%)
    weekly_return : float   주간 누적 수익률
    monthly_return : float  월간 누적 수익률
    avg_correlation : float 포폴 내 평균 종목 상관관계
    """
    if cfg is None:
        from risk.trading_config import TradingConfig
        cfg = TradingConfig()

    result = RiskCheck()

    # ── ⑦ Correlation Stop ──
    if avg_correlation > 0.85:
        result.portfolio_reduce = True
        result.reason = f"CORRELATION_EXTREME(avg={avg_correlation:.2f})"
        result.severity = "HIGH"
        return result

    if avg_correlation > 0.70:
        result.severity = "MEDIUM"
        result.reason = f"CORRELATION_HIGH(avg={avg_correlation:.2f})"
        # 가장 약한 종목 1개 매도 권고 (batch에서 처리)

    # ── ⑧ Portfolio Loss Limits ──
    monthly_limit = getattr(cfg, "monthly_loss_limit", -0.10)
    weekly_limit = getattr(cfg, "weekly_loss_limit", -0.05)
    daily_limit = getattr(cfg, "daily_loss_limit", -0.03)

    if monthly_return <= monthly_limit:
        result.portfolio_liquidate = True
        result.reason = f"MONTHLY_LOSS({monthly_return:.1%})"
        result.severity = "CRITICAL"
        return result

    if weekly_return <= weekly_limit:
        result.portfolio_reduce = True
        result.reason = f"WEEKLY_LOSS({weekly_return:.1%})"
        result.severity = "HIGH"
        return result

    if daily_return <= daily_limit:
        result.portfolio_halt = True
        result.reason = f"DAILY_LOSS({daily_return:.1%})"
        result.severity = "HIGH"
        return result

    return result
