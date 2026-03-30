"""
portfolio/regime_risk_manager.py — Regime-Aware Portfolio + Risk v1.0
======================================================================
Day 5 신규 | 블루프린트 원칙 2 "Degrade Gracefully" — 위기 시 자동 방어

3개 엔진을 하나로:
  1. Black-Litterman Optimizer: 시장 균형 + AI 전망 = 최적 가중치
  2. Regime Risk Budget: 국면별 자동 투자비중/포지션/손절 조정
  3. Transaction Cost Filter: 순이익 < 비용이면 거래 안 함

연결:
  Conformal confidence → BL View 확신도
  Macro Regime → Risk Budget 자동 전환
  Conviction v2 → 종목별 포지션 크기

사용: portfolio_builder.py, risk_manager.py에서 import
"""
import numpy as np
import json
import logging
from datetime import date
from db_pool import get_cursor

logger = logging.getLogger("regime_risk_manager")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Regime-Aware Risk Budget
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

REGIME_RISK_BUDGET = {
    #                    max_position  max_invested  stop_loss  max_drawdown  max_stocks
    "RISK_ON_RALLY":    {"pos": 0.12, "inv": 0.95, "sl": 0.08, "mdd": 0.12, "n": 15},
    "GOLDILOCKS":       {"pos": 0.10, "inv": 0.90, "sl": 0.07, "mdd": 0.10, "n": 12},
    "REFLATION":        {"pos": 0.08, "inv": 0.80, "sl": 0.06, "mdd": 0.08, "n": 10},
    "STAGFLATION":      {"pos": 0.06, "inv": 0.65, "sl": 0.05, "mdd": 0.07, "n": 8},
    "DEFLATION_SCARE":  {"pos": 0.05, "inv": 0.50, "sl": 0.04, "mdd": 0.06, "n": 6},
    "CRISIS":           {"pos": 0.04, "inv": 0.30, "sl": 0.03, "mdd": 0.05, "n": 4},
}


def get_risk_params(regime_name=None, calc_date=None):
    """
    현재 Regime에 맞는 리스크 파라미터 반환.

    Returns:
        dict: {pos, inv, sl, mdd, n}
        pos: 개별 종목 최대 비중
        inv: 전체 투자 비중 (나머지 = 현금)
        sl: 스톱로스 비율
        mdd: 최대 허용 낙폭
        n: 최대 종목 수
    """
    if regime_name is None:
        try:
            from batch.batch_macro_regime import get_current_regime
            current = get_current_regime(calc_date)
            regime_name = current.get("dominant_regime", "GOLDILOCKS")
        except Exception:
            regime_name = "GOLDILOCKS"

    params = REGIME_RISK_BUDGET.get(regime_name, REGIME_RISK_BUDGET["GOLDILOCKS"])

    # Telemetry
    _log_telemetry(calc_date or date.today(), "PORTFOLIO", "risk_params", None, {
        "regime": regime_name, **params
    })

    return params


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Simplified Black-Litterman
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def black_litterman_weights(
    tickers,
    expected_returns,      # AI 기대초과수익률 (종목별)
    confidences,           # Conformal confidence (종목별 0~1)
    market_caps=None,      # 시가총액 (없으면 균등)
    risk_aversion=2.5,
    tau=0.05,
):
    """
    Simplified Black-Litterman.

    수학:
      Prior (시장 균형): pi = delta * Sigma * w_mkt
      View (AI 전망): Q = expected_returns, Omega = diag(1/confidence)
      Posterior: E[R] = inv(inv(tau*Sigma) + P'*inv(Omega)*P) * (inv(tau*Sigma)*pi + P'*inv(Omega)*Q)
      Optimal: w = inv(delta*Sigma) * E[R]

    Simplification (종목 수 적을 때):
      종목 간 상관을 무시하고 대각 근사 → 실용적 + 안정적

    Args:
        tickers: 종목 리스트
        expected_returns: AI 기대수익률 (0~1 스케일)
        confidences: Conformal 확신도 (0~1, 높을수록 BL에서 강한 View)
        market_caps: 시가총액 (None이면 균등)

    Returns:
        dict: {ticker: weight}
    """
    n = len(tickers)
    if n == 0:
        return {}

    er = np.asarray(expected_returns, dtype=float)
    conf = np.asarray(confidences, dtype=float)
    conf = np.maximum(conf, 0.05)  # 최소 5% 확신도

    # Market weight (시가총액 비례 or 균등)
    if market_caps is not None:
        mc = np.asarray(market_caps, dtype=float)
        w_mkt = mc / mc.sum()
    else:
        w_mkt = np.ones(n) / n

    # 대각 근사: 종목별 독립 계산 (종목 수 적을 때 안정적)
    # BL 핵심: confidence 높으면 AI view에 비중 부여, 낮으면 시장 균형 유지
    bl_weight = np.zeros(n)
    for i in range(n):
        # View 강도 = 기대수익률 × 확신도
        view_strength = er[i] * conf[i]
        # BL 블렌딩: 시장 균형(1-tau) + AI view(tau * strength)
        bl_weight[i] = w_mkt[i] * (1 + tau * view_strength * risk_aversion)

    # Long-only + 정규화
    bl_weight = np.maximum(bl_weight, 0)
    total = bl_weight.sum()
    if total > 0:
        bl_weight /= total
    else:
        bl_weight = w_mkt

    result = {t: round(float(w), 4) for t, w in zip(tickers, bl_weight)}
    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Transaction Cost Aware Rebalancing
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def filter_trades_by_cost(target_weights, current_weights,
                          expected_alphas, cost_per_trade=0.001):
    """
    거래비용 고려 리밸런싱 필터.

    net_benefit = expected_alpha * weight_change - trade_cost
    net_benefit < 0 → 교체 안 함 (홀딩이 이득)

    Args:
        target_weights: {ticker: target_weight}
        current_weights: {ticker: current_weight}
        expected_alphas: {ticker: expected_alpha} (0~1)
        cost_per_trade: 편도 거래비용 (기본 0.1%)

    Returns:
        list of {ticker, action, weight_change, net_benefit}
    """
    orders = []
    all_tickers = set(list(target_weights.keys()) + list(current_weights.keys()))

    for ticker in all_tickers:
        tw = target_weights.get(ticker, 0)
        cw = current_weights.get(ticker, 0)
        diff = tw - cw

        if abs(diff) < 0.01:  # 1% 미만 차이 무시
            continue

        alpha = expected_alphas.get(ticker, 0)
        trade_cost = abs(diff) * cost_per_trade * 2  # 양방향
        net = alpha * abs(diff) - trade_cost

        if net > 0:
            orders.append({
                "ticker": ticker,
                "action": "BUY" if diff > 0 else "SELL",
                "weight_change": round(diff, 4),
                "net_benefit": round(net, 6),
                "expected_alpha": round(alpha, 4),
                "trade_cost": round(trade_cost, 6),
            })
        else:
            logger.debug(f"[COST-FILTER] {ticker} 스킵: net={net:.6f} < 0 "
                        f"(alpha={alpha:.4f}, cost={trade_cost:.6f})")

    return sorted(orders, key=lambda x: abs(x["net_benefit"]), reverse=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 통합 포트폴리오 빌더
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def build_optimal_portfolio(candidates, regime_name=None, calc_date=None):
    """
    통합 포트폴리오 구축.

    1. Regime Risk Budget → 최대 투자비중/포지션 결정
    2. Black-Litterman → 최적 비중 산출
    3. Risk Budget 적용 → 개별 상한 클램프
    4. Transaction Cost Filter → 불필요한 거래 제거

    Args:
        candidates: list of {
            ticker, stock_id, ai_score, conviction,
            conformal_confidence, expected_alpha,
            layer1_score, layer2_score, layer3_score,
            market_cap (optional)
        }
        regime_name: 현재 국면 (None이면 자동 조회)

    Returns:
        dict: {
            weights: {ticker: weight},
            risk_params: {pos, inv, sl, mdd, n},
            regime: str,
            orders: list,
        }
    """
    if calc_date is None:
        calc_date = date.today()

    # 1. Risk Budget
    risk = get_risk_params(regime_name, calc_date)

    # 2. 상위 N 종목 선정 (conviction 순)
    sorted_cands = sorted(candidates, key=lambda c: c.get("conviction", 0), reverse=True)
    top_n = sorted_cands[:risk["n"]]

    if not top_n:
        return {"weights": {}, "risk_params": risk, "regime": regime_name, "orders": []}

    # 3. BL 최적화
    tickers = [c["ticker"] for c in top_n]
    expected_returns = [c.get("expected_alpha", 0.01) for c in top_n]
    confidences = [c.get("conformal_confidence", 0.5) for c in top_n]
    market_caps = [c.get("market_cap") for c in top_n]
    has_mcap = all(m is not None for m in market_caps)

    bl_weights = black_litterman_weights(
        tickers, expected_returns, confidences,
        market_caps if has_mcap else None,
    )

    # 4. Risk Budget 적용
    max_pos = risk["pos"]
    max_inv = risk["inv"]

    clamped = {}
    for ticker, w in bl_weights.items():
        clamped[ticker] = min(w * max_inv, max_pos)

    # 정규화 (합 <= max_inv)
    total = sum(clamped.values())
    if total > max_inv:
        ratio = max_inv / total
        clamped = {t: round(w * ratio, 4) for t, w in clamped.items()}

    # 5. Transaction Cost Filter (현재 포지션 조회)
    current_weights = _get_current_weights(calc_date)
    expected_alphas = {c["ticker"]: c.get("expected_alpha", 0.01) for c in top_n}
    orders = filter_trades_by_cost(clamped, current_weights, expected_alphas)

    # Telemetry
    _log_telemetry(calc_date, "PORTFOLIO", "optimal_build", len(orders), {
        "regime": regime_name or "auto",
        "n_candidates": len(candidates),
        "n_selected": len(top_n),
        "max_invested": max_inv,
        "total_weight": round(sum(clamped.values()), 4),
        "n_orders": len(orders),
    })

    return {
        "weights": clamped,
        "risk_params": risk,
        "regime": regime_name,
        "orders": orders,
        "n_selected": len(top_n),
    }


def _get_current_weights(calc_date):
    """현재 포지션 비중 조회 (trading_signals 기반)"""
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT s.ticker, ts.position_size
                FROM trading_signals ts
                JOIN stocks s ON ts.stock_id = s.stock_id
                WHERE ts.calc_date = (
                    SELECT MAX(calc_date) FROM trading_signals WHERE calc_date < %s
                )
                AND ts.signal_type IN ('BUY', 'STRONG_BUY', 'HOLD')
                AND ts.position_size > 0
            """, (calc_date,))
            rows = cur.fetchall()
            return {r["ticker"]: float(r["position_size"]) / 100.0 for r in rows if r["position_size"]}
    except Exception as e:
        logger.debug(f"[PORTFOLIO] 현재 포지션 조회 실패: {e}")
    return {}


def _log_telemetry(calc_date, category, metric_name, metric_value, detail=None):
    try:
        with get_cursor() as cur:
            cur.execute("""
                INSERT INTO system_telemetry (calc_date, category, metric_name, metric_value, detail)
                VALUES (%s, %s, %s, %s, %s)
            """, (calc_date, category, metric_name, metric_value,
                  json.dumps(detail, ensure_ascii=False, default=str) if detail else None))
    except Exception as e:
        logger.debug(f"[TELEMETRY] 실패: {e}")