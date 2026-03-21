"""
portfolio/transaction_cost.py — 거래비용 모델
==============================================
슬리피지 + 시장충격(Almgren-Chriss) + 커미션 + 회전율 예산

모든 매매에 대해 실행 비용을 사전 추정하고,
회전율 예산을 초과하면 낮은 우선순위 거래를 스킵합니다.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional
from datetime import date


@dataclass
class TradeCostEstimate:
    """단일 거래 비용 추정"""
    ticker: str
    trade_type: str          # BUY / SELL
    shares: int
    price: float
    notional: float          # shares × price
    # 비용 항목
    commission: float        # 커미션 ($)
    spread_cost: float       # 스프레드 비용 ($)
    market_impact: float     # 시장충격 ($)
    total_cost: float        # 총 비용 ($)
    total_cost_pct: float    # 총 비용 (%)
    participation_rate: float  # ADV 대비 참여율


@dataclass
class TurnoverBudget:
    """월간 회전율 예산"""
    monthly_budget: float      # 월간 회전율 한도 (0.25 = 25%)
    used_this_month: float     # 이번 달 사용된 회전율
    remaining: float           # 남은 예산
    can_trade: bool            # 거래 가능?
    max_trade_value: float     # 남은 예산으로 가능한 최대 거래 금액


class TransactionCostModel:
    """
    거래비용 추정 + 회전율 예산 관리.

    사용법:
        tcm = TransactionCostModel()

        # 단일 거래 비용 추정
        cost = tcm.estimate_cost("NVDA", "BUY", 10, 890.0, adv_shares=2_000_000)

        # 회전율 예산 체크
        budget = tcm.check_turnover_budget(
            account_value=100000, monthly_budget=0.25,
            trades_this_month=15000, new_trade_value=8900
        )
    """

    def __init__(
        self,
        commission_per_share: float = 0.0,        # 대부분 제로
        min_commission: float = 0.0,
        spread_bps: float = 5.0,                   # 평균 스프레드 5bps
        impact_eta: float = 0.02,                   # 일시적 충격 계수
        impact_gamma: float = 0.10,                 # 영구적 충격 계수
    ):
        self.commission_per_share = commission_per_share
        self.min_commission = min_commission
        self.spread_bps = spread_bps
        self.impact_eta = impact_eta
        self.impact_gamma = impact_gamma

    def estimate_cost(
        self,
        ticker: str,
        trade_type: str,
        shares: int,
        price: float,
        adv_shares: float = 1_000_000,
        daily_volatility: float = 0.02,
    ) -> TradeCostEstimate:
        """단일 거래 비용 추정"""
        notional = abs(shares) * price

        # 커미션
        commission = max(
            self.min_commission,
            abs(shares) * self.commission_per_share,
        )

        # 스프레드 비용 (절반만 — 한 방향)
        spread_cost = notional * (self.spread_bps / 10000) / 2

        # 시장충격 (Almgren-Chriss simplified)
        if adv_shares > 0:
            participation_rate = abs(shares) / adv_shares
            temp_impact = self.impact_eta * daily_volatility * (participation_rate ** 0.6)
            perm_impact = self.impact_gamma * daily_volatility * (participation_rate ** 0.5)
            market_impact = (temp_impact + perm_impact) * notional
        else:
            participation_rate = 1.0
            market_impact = notional * 0.005  # fallback 0.5%

        total_cost = commission + spread_cost + market_impact
        total_cost_pct = total_cost / notional if notional > 0 else 0

        return TradeCostEstimate(
            ticker=ticker,
            trade_type=trade_type,
            shares=abs(shares),
            price=price,
            notional=notional,
            commission=round(commission, 2),
            spread_cost=round(spread_cost, 2),
            market_impact=round(market_impact, 2),
            total_cost=round(total_cost, 2),
            total_cost_pct=round(total_cost_pct, 6),
            participation_rate=round(participation_rate, 4),
        )

    def estimate_batch_costs(
        self,
        trades: List[dict],
        adv_map: Dict[str, float] = None,
        vol_map: Dict[str, float] = None,
    ) -> List[TradeCostEstimate]:
        """복수 거래 일괄 비용 추정"""
        if adv_map is None:
            adv_map = {}
        if vol_map is None:
            vol_map = {}

        costs = []
        for t in trades:
            cost = self.estimate_cost(
                ticker=t["ticker"],
                trade_type=t.get("trade_type", "BUY"),
                shares=t["shares"],
                price=t["price"],
                adv_shares=adv_map.get(t["ticker"], 1_000_000),
                daily_volatility=vol_map.get(t["ticker"], 0.02),
            )
            costs.append(cost)

        return costs

    def check_turnover_budget(
        self,
        account_value: float,
        monthly_budget: float,
        trades_this_month: float,
        new_trade_value: float = 0,
    ) -> TurnoverBudget:
        """회전율 예산 체크"""
        budget_dollar = account_value * monthly_budget
        remaining = budget_dollar - trades_this_month
        can_trade = remaining >= new_trade_value

        return TurnoverBudget(
            monthly_budget=monthly_budget,
            used_this_month=trades_this_month / account_value if account_value > 0 else 0,
            remaining=max(0, remaining) / account_value if account_value > 0 else 0,
            can_trade=can_trade,
            max_trade_value=max(0, remaining),
        )

    def filter_by_turnover_budget(
        self,
        trades: List[dict],
        account_value: float,
        monthly_budget: float,
        trades_this_month: float,
    ) -> List[dict]:
        """
        회전율 예산 내에서 거래 필터링.
        우선순위(점수) 높은 순으로 통과, 예산 소진 시 나머지 스킵.
        """
        budget_remaining = account_value * monthly_budget - trades_this_month
        passed = []

        # 점수 높은 순 정렬
        sorted_trades = sorted(trades, key=lambda t: t.get("score", 0), reverse=True)

        for t in sorted_trades:
            value = t.get("shares", 0) * t.get("price", 0)
            if value <= budget_remaining:
                passed.append(t)
                budget_remaining -= value
            # else: skip (예산 초과)

        return passed
