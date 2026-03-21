"""
portfolio/position_sizer.py — Kelly + 변동성 + DD 포지션 사이징
================================================================
v3.2 (ATR 단순 사이징) → v3.3 (Half-Kelly + 변동성 역비례 + DD 조절)

사이징 3단계:
  1. Base Size: Half-Kelly 기반 최적 베팅
  2. Volatility Adjust: ATR 역비례 변동성 조절
  3. DD/CB Override: 드로다운/서킷브레이커 배수 적용
"""
from dataclasses import dataclass
from typing import Dict, Optional
import math


@dataclass
class PositionSize:
    """포지션 사이징 결과"""
    ticker: str
    shares: int
    position_value: float
    weight_pct: float
    stop_loss_price: float
    risk_amount: float          # 이 포지션의 최대 손실 ($)
    # 사이징 요소
    kelly_fraction: float       # Half-Kelly 비중
    vol_adjustment: float       # 변동성 조절 배수
    conviction_mult: float      # 등급 확신도 배수
    regime_mult: float          # 국면 배수
    dd_mult: float              # DD 모드 배수
    cb_mult: float              # Circuit Breaker 배수
    final_mult: float           # 최종 배수 (all multiplied)
    capped: bool                # 하드 리밋에 걸렸는가
    cap_reason: str             # 캡 사유


def calculate_position_size(
    ticker: str,
    current_price: float,
    atr_14: float,
    final_score: float,
    grade: str,
    regime: str,
    account_value: float,
    current_invested: float,
    sector: str,
    sector_invested: Dict[str, float],
    num_positions: int,
    # V2 추가 인자
    win_rate: float = 0.55,          # 같은 점수대 역사적 승률
    win_loss_ratio: float = 1.8,     # 평균승/평균패 비율
    vol_20d: float = 0.0,            # 20일 변동성 (연환산)
    dd_mult: float = 1.0,            # DD Controller 배수
    cb_mult: float = 1.0,            # Circuit Breaker 배수
    cfg=None,
) -> PositionSize:
    """
    한 종목의 포지션 크기 계산 (v3.3)

    Parameters
    ----------
    win_rate : float        같은 점수 구간의 역사적 승률 (기본 0.55)
    win_loss_ratio : float  평균 승/패 비율 (기본 1.8)
    vol_20d : float         20일 연환산 변동성 (0이면 ATR 기반 추정)
    dd_mult : float         DrawdownController 배수 (0.3~1.0)
    cb_mult : float         CircuitBreaker 배수 (0.5~1.0)
    """
    if cfg is None:
        from risk.trading_config import TradingConfig
        cfg = TradingConfig()

    result = PositionSize(
        ticker=ticker, shares=0, position_value=0, weight_pct=0,
        stop_loss_price=0, risk_amount=0,
        kelly_fraction=0, vol_adjustment=1.0, conviction_mult=1.0,
        regime_mult=1.0, dd_mult=dd_mult, cb_mult=cb_mult,
        final_mult=1.0, capped=False, cap_reason="",
    )

    if current_price <= 0 or atr_14 <= 0 or account_value <= 0:
        return result

    # ── 1. Half-Kelly Fraction ──
    p = max(0.01, min(0.99, win_rate))
    b = max(0.01, win_loss_ratio)
    q = 1 - p
    full_kelly = (p * b - q) / b
    half_kelly = max(0, full_kelly * 0.5)

    # 점수 기반 스케일링
    score_factor = max(0, (final_score - 50)) / 50  # 0~1
    kelly_weight = half_kelly * (0.5 + 0.5 * score_factor)

    # Kelly 상한 (절대 10% 초과 금지)
    kelly_weight = min(kelly_weight, 0.10)
    result.kelly_fraction = round(kelly_weight, 4)

    # ── 2. Volatility Adjustment ──
    if vol_20d > 0:
        target_vol = 0.15  # 목표 포폴 연환산 변동성 15%
        vol_adj = target_vol / vol_20d if vol_20d > 0 else 1.0
        vol_adj = max(0.3, min(2.0, vol_adj))
    else:
        # ATR 기반 근사
        atr_pct = atr_14 / current_price if current_price > 0 else 0.02
        vol_adj = 0.02 / atr_pct if atr_pct > 0 else 1.0
        vol_adj = max(0.3, min(2.0, vol_adj))

    result.vol_adjustment = round(vol_adj, 3)

    # ── 3. Conviction (등급 배수) ──
    conv_mult = cfg.get_conviction_multiplier(grade) if hasattr(cfg, "get_conviction_multiplier") else 1.0
    result.conviction_mult = conv_mult

    # ── 4. Regime 배수 ──
    regime_mult = {"BULL": 1.0, "NEUTRAL": 0.8, "BEAR": 0.5, "CRISIS": 0.3}.get(regime, 0.7)
    result.regime_mult = regime_mult

    # ── 5. 최종 배수 ──
    final_mult = kelly_weight * vol_adj * conv_mult * regime_mult * dd_mult * cb_mult
    result.final_mult = round(final_mult, 4)

    # ── 포지션 금액 ──
    max_pct = getattr(cfg, "max_position_pct", 0.08)
    target_value = account_value * final_mult

    # 하드 리밋 체크
    cap_reason = ""
    hard_max = account_value * max_pct
    if target_value > hard_max:
        target_value = hard_max
        cap_reason = f"MAX_POSITION({max_pct:.0%})"

    # 현금 여유 체크
    available_cash = account_value - current_invested
    cash_min = account_value * getattr(cfg, "cash_minimum", 0.20)
    investable = max(0, available_cash - cash_min)

    if target_value > investable:
        target_value = investable
        cap_reason = cap_reason or "CASH_LIMIT"

    # 섹터 한도 체크
    sector_max = account_value * getattr(cfg, "sector_max_pct", 0.30)
    sector_used = sector_invested.get(sector, 0)
    sector_room = max(0, sector_max - sector_used)

    if target_value > sector_room:
        target_value = sector_room
        cap_reason = cap_reason or "SECTOR_LIMIT"

    if target_value < current_price:
        result.shares = 0
        return result

    # ── 주수 계산 ──
    shares = int(target_value / current_price)
    if shares <= 0:
        return result

    position_value = shares * current_price

    # ── 손절가 ──
    stop_atr_mult = getattr(cfg, "stop_loss_atr_mult", 1.8)
    stop_loss = round(current_price - stop_atr_mult * atr_14, 2)
    risk_amount = (current_price - stop_loss) * shares if stop_loss > 0 else position_value * 0.05

    result.shares = shares
    result.position_value = round(position_value, 2)
    result.weight_pct = round(position_value / account_value * 100, 2)
    result.stop_loss_price = max(0, stop_loss)
    result.risk_amount = round(risk_amount, 2)
    result.capped = bool(cap_reason)
    result.cap_reason = cap_reason

    return result
