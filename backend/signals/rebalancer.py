"""
rebalancer.py — 리밸런싱 엔진
정기(주간) + 긴급 리밸런싱 처리
현재 포트폴리오 vs 목표 포트폴리오 비교 → Delta 주문 생성
"""
from dataclasses import dataclass, field
from typing import List, Dict, Tuple
from datetime import date


@dataclass
class RebalanceOrder:
    """리밸런싱 주문"""
    ticker: str
    stock_id: int
    action: str              # BUY, SELL, ADJUST_UP, ADJUST_DOWN
    current_shares: int
    target_shares: int
    delta_shares: int        # 양수=매수, 음수=매도
    current_weight: float
    target_weight: float
    reason: str              # NEW_BUY, EXIT_SELL, WEIGHT_ADJUST, STOP_LOSS ...


@dataclass
class RebalanceResult:
    """리밸런싱 결과"""
    rebalance_date: date = None
    rebalance_type: str = "WEEKLY"    # WEEKLY, EMERGENCY
    orders: List[RebalanceOrder] = field(default_factory=list)
    num_buys: int = 0
    num_sells: int = 0
    num_adjusts: int = 0
    estimated_turnover: float = 0.0   # 회전율 (%)


def calculate_rebalance(
    current_positions: Dict[str, dict],    # {ticker: {shares, current_price, entry_price, sector, ...}}
    target_portfolio: dict,                 # portfolio_builder 결과
    account_value: float,
    rebalance_date: date,
    rebalance_type: str = "WEEKLY",
    cfg=None,
) -> RebalanceResult:
    """
    현재 vs 목표 비교 → 주문 리스트 생성

    Parameters
    ----------
    current_positions : dict
        {ticker: {shares, current_price, entry_price, sector, stock_id}}
    target_portfolio : dict
        {stocks: [{ticker, shares, weight_pct, ...}], cash_balance, ...}
    """
    from trading_config import TradingConfig
    if cfg is None:
        cfg = TradingConfig()

    result = RebalanceResult(
        rebalance_date=rebalance_date,
        rebalance_type=rebalance_type,
    )

    current_tickers = set(current_positions.keys())
    target_stocks = target_portfolio.get("stocks", [])
    target_map = {s["ticker"]: s for s in target_stocks}
    target_tickers = set(target_map.keys())

    total_turnover = 0.0

    # ── SELL: 현재 보유 but 목표에 없음 ──
    for ticker in current_tickers - target_tickers:
        pos = current_positions[ticker]
        shares = pos.get("shares", 0)
        current_weight = (shares * pos.get("current_price", 0)) / account_value * 100 if account_value > 0 else 0

        order = RebalanceOrder(
            ticker=ticker,
            stock_id=pos.get("stock_id", 0),
            action="SELL",
            current_shares=shares,
            target_shares=0,
            delta_shares=-shares,
            current_weight=round(current_weight, 2),
            target_weight=0,
            reason="EXIT_SELL",
        )
        result.orders.append(order)
        result.num_sells += 1
        total_turnover += abs(shares * pos.get("current_price", 0))

    # ── BUY: 목표에 있지만 현재 미보유 ──
    for ticker in target_tickers - current_tickers:
        t = target_map[ticker]
        shares = t.get("shares", 0)
        if shares <= 0:
            continue

        order = RebalanceOrder(
            ticker=ticker,
            stock_id=t.get("stock_id", 0),
            action="BUY",
            current_shares=0,
            target_shares=shares,
            delta_shares=shares,
            current_weight=0,
            target_weight=t.get("weight_pct", 0),
            reason="NEW_BUY",
        )
        result.orders.append(order)
        result.num_buys += 1
        total_turnover += abs(shares * t.get("current_price", 0))

    # ── ADJUST: 양쪽 모두 있음 → 수량 조정 ──
    for ticker in current_tickers & target_tickers:
        pos = current_positions[ticker]
        t = target_map[ticker]
        current_shares = pos.get("shares", 0)
        target_shares = t.get("shares", 0)
        delta = target_shares - current_shares

        current_weight = (current_shares * pos.get("current_price", 0)) / account_value * 100 if account_value > 0 else 0
        target_weight = t.get("weight_pct", 0)

        # 비중 차이가 min_rebalance_delta 미만이면 스킵
        if abs(target_weight - current_weight) < cfg.min_rebalance_delta * 100:
            continue

        if delta == 0:
            continue

        action = "ADJUST_UP" if delta > 0 else "ADJUST_DOWN"
        order = RebalanceOrder(
            ticker=ticker,
            stock_id=pos.get("stock_id", 0),
            action=action,
            current_shares=current_shares,
            target_shares=target_shares,
            delta_shares=delta,
            current_weight=round(current_weight, 2),
            target_weight=target_weight,
            reason="WEIGHT_ADJUST",
        )
        result.orders.append(order)
        result.num_adjusts += 1
        total_turnover += abs(delta * pos.get("current_price", 0))

    result.estimated_turnover = round(total_turnover / account_value * 100, 2) if account_value > 0 else 0

    # 매도 먼저, 매수 나중 순으로 정렬
    priority = {"SELL": 0, "ADJUST_DOWN": 1, "ADJUST_UP": 2, "BUY": 3}
    result.orders.sort(key=lambda o: priority.get(o.action, 9))

    return result
