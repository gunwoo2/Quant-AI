"""
transaction_cost_v5.py — 거래 비용 모델
========================================
매수/매도 시그널에 슬리피지 + 커미션 + 마켓 임팩트 반영.
batch_trading_signals.py에서 import하여 사용.

사용법:
    from transaction_cost_v5 import TransactionCostModel
    tc = TransactionCostModel()
    cost = tc.estimate_cost(price=150.0, shares=100, side="BUY", volume_20d=2_000_000)
    net_price = tc.apply_cost(price=150.0, shares=100, side="BUY", volume_20d=2_000_000)
"""

import math
from dataclasses import dataclass


@dataclass
class CostBreakdown:
    """거래 비용 상세 내역"""
    commission: float       # 수수료 ($)
    spread_cost: float      # 스프레드 비용 ($)
    slippage: float         # 슬리피지 ($)
    market_impact: float    # 마켓 임팩트 ($)
    total_cost: float       # 총 비용 ($)
    cost_bps: float         # 비용 (bps)
    net_price: float        # 비용 반영 실행가


class TransactionCostModel:
    """
    3-Component 거래 비용 모델
    
    Component 1: 고정 비용 (커미션 + SEC fee)
    Component 2: 스프레드 + 슬리피지 (가격/유동성 기반)
    Component 3: 마켓 임팩트 (주문 규모 / 일평균 거래량)
    
    기관 참고:
        - Almgren & Chriss (2000): 최적 실행 프레임워크
        - Kissell & Glantz (2003): 최적 매매 전략
        - 일반적인 US 대형주: 총 비용 5~15 bps
        - US 중형주: 15~40 bps
        - US 소형주: 40~100+ bps
    """
    
    def __init__(
        self,
        commission_per_share: float = 0.005,   # $0.005/주 (IBKR 기준)
        min_commission: float = 1.0,            # 최소 수수료 $1
        sec_fee_rate: float = 0.0000278,        # SEC fee (매도만, 2024 기준)
        base_spread_bps: float = 3.0,           # 기본 스프레드 3 bps
        slippage_bps: float = 5.0,              # 기본 슬리피지 5 bps  
        impact_coefficient: float = 0.1,        # 마켓 임팩트 계수 (σ * √participation)
        volatility_mult: float = 1.0,           # 변동성 배율
    ):
        self.commission_per_share = commission_per_share
        self.min_commission = min_commission
        self.sec_fee_rate = sec_fee_rate
        self.base_spread_bps = base_spread_bps
        self.slippage_bps = slippage_bps
        self.impact_coefficient = impact_coefficient
        self.volatility_mult = volatility_mult

    def estimate_cost(
        self,
        price: float,
        shares: int,
        side: str = "BUY",      # "BUY" or "SELL"
        volume_20d: float = 0,   # 20일 평균 거래량
        atr_pct: float = 0,      # ATR / price (%)
        urgency: float = 0.5,    # 0=patient, 1=urgent
    ) -> CostBreakdown:
        """거래 비용 추정"""
        
        notional = price * shares
        if notional <= 0:
            return CostBreakdown(0, 0, 0, 0, 0, 0, price)
        
        # ── Component 1: 커미션 ──
        commission = max(self.commission_per_share * shares, self.min_commission)
        
        # SEC fee (매도만)
        if side == "SELL":
            commission += notional * self.sec_fee_rate
        
        # ── Component 2: 스프레드 + 슬리피지 ──
        # 유동성 기반 스프레드 조정
        spread_adj = 1.0
        if volume_20d > 0:
            # 거래량 적으면 스프레드 넓어짐
            daily_dollar_vol = volume_20d * price
            if daily_dollar_vol < 1_000_000:       # $1M 미만 = 저유동
                spread_adj = 3.0
            elif daily_dollar_vol < 10_000_000:     # $10M 미만 = 중유동
                spread_adj = 1.5
            elif daily_dollar_vol > 100_000_000:    # $100M 이상 = 초고유동
                spread_adj = 0.5
        
        spread_bps = self.base_spread_bps * spread_adj
        spread_cost = notional * (spread_bps / 10_000) / 2  # half-spread
        
        # 슬리피지 (변동성 + 긴급도 반영)
        vol_adj = max(atr_pct / 2.0, 1.0) if atr_pct > 0 else 1.0
        slip_bps = self.slippage_bps * vol_adj * (0.5 + urgency)
        slippage = notional * (slip_bps / 10_000)
        
        # ── Component 3: 마켓 임팩트 ──
        # Almgren model 간소화: impact ∝ σ × √(shares / ADV)
        market_impact = 0.0
        if volume_20d > 0 and shares > 0:
            participation_rate = shares / volume_20d
            if participation_rate > 0.001:  # 0.1% 이상이면 임팩트 발생
                vol_factor = max(atr_pct, 1.5) * self.volatility_mult
                market_impact = notional * self.impact_coefficient * vol_factor / 100 * math.sqrt(participation_rate)
        
        # ── 총합 ──
        total_cost = commission + spread_cost + slippage + market_impact
        cost_bps = (total_cost / notional) * 10_000 if notional > 0 else 0
        
        # 비용 반영 실행가
        if side == "BUY":
            net_price = price * (1 + total_cost / notional)
        else:
            net_price = price * (1 - total_cost / notional)
        
        return CostBreakdown(
            commission=round(commission, 2),
            spread_cost=round(spread_cost, 2),
            slippage=round(slippage, 2),
            market_impact=round(market_impact, 2),
            total_cost=round(total_cost, 2),
            cost_bps=round(cost_bps, 1),
            net_price=round(net_price, 4),
        )
    
    def apply_cost(self, price: float, shares: int, side: str = "BUY", **kwargs) -> float:
        """비용 반영된 실행가 반환 (간편 호출)"""
        return self.estimate_cost(price, shares, side, **kwargs).net_price
    
    def is_profitable_after_cost(
        self,
        entry_price: float,
        expected_return_pct: float,
        shares: int,
        volume_20d: float = 0,
        atr_pct: float = 0,
    ) -> tuple[bool, float]:
        """
        비용 감안 후에도 수익인지 판단.
        
        Returns:
            (is_profitable, net_return_pct)
        """
        # 매수 비용
        buy_cost = self.estimate_cost(entry_price, shares, "BUY", volume_20d, atr_pct)
        
        # 예상 매도가
        expected_exit = entry_price * (1 + expected_return_pct / 100)
        sell_cost = self.estimate_cost(expected_exit, shares, "SELL", volume_20d, atr_pct)
        
        # 순수익
        gross_profit = (expected_exit - entry_price) * shares
        total_cost = buy_cost.total_cost + sell_cost.total_cost
        net_profit = gross_profit - total_cost
        
        net_return_pct = (net_profit / (entry_price * shares)) * 100 if shares > 0 else 0
        
        return net_return_pct > 0, round(net_return_pct, 4)


# ── 기본 인스턴스 (import하여 바로 사용) ──
default_tc_model = TransactionCostModel()


def estimate_round_trip_cost(price: float, shares: int, volume_20d: float = 0, atr_pct: float = 0) -> float:
    """왕복 거래 비용 (bps) — 간편 함수"""
    buy = default_tc_model.estimate_cost(price, shares, "BUY", volume_20d, atr_pct)
    sell = default_tc_model.estimate_cost(price, shares, "SELL", volume_20d, atr_pct)
    total_notional = price * shares
    if total_notional <= 0:
        return 0
    return round((buy.total_cost + sell.total_cost) / total_notional * 10_000, 1)


if __name__ == "__main__":
    tc = TransactionCostModel()
    
    # 예시: TSM $340, 10주, 거래량 15M주
    cost = tc.estimate_cost(price=340.0, shares=10, side="BUY", volume_20d=15_000_000, atr_pct=2.1)
    print(f"TSM BUY 10주 @ $340:")
    print(f"  Commission:    ${cost.commission}")
    print(f"  Spread:        ${cost.spread_cost}")
    print(f"  Slippage:      ${cost.slippage}")
    print(f"  Market Impact: ${cost.market_impact}")
    print(f"  Total Cost:    ${cost.total_cost} ({cost.cost_bps} bps)")
    print(f"  Net Price:     ${cost.net_price}")
    
    # 왕복 비용
    rt = estimate_round_trip_cost(340.0, 10, 15_000_000, 2.1)
    print(f"  Round-Trip:    {rt} bps")
    
    # 수익성 판단
    profitable, net_ret = tc.is_profitable_after_cost(340.0, 3.0, 10, 15_000_000, 2.1)
    print(f"\n  예상 수익 3% → 비용 후: {net_ret}% ({'수익' if profitable else '손실'})")