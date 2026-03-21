"""
portfolio/portfolio_builder.py — 3중 블렌딩 포트폴리오 구성 엔진
===================================================================
v3.2 (균등비중+섹터한도) → v3.3 (RP+HK+Conv 블렌딩)

파이프라인:
  1. 섹터 부스트 (sector_rotation)
  2. 상관관계 필터 (correlation_filter)
  3. 3중 블렌딩 비중 계산
     a) Risk Parity — 공분산 기반 동일 리스크 기여
     b) Half-Kelly — 승률/손익비 기반 최적 베팅
     c) Score Conviction — 등급×점수 확신도
  4. 국면별 블렌딩 비율 (α,β,γ) 적용
  5. 제약조건 (섹터한도, 종목한도, 현금비율)
  6. 포지션 사이징 (shares 계산)
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from scipy.optimize import minimize


# ═══════════════════════════════════════════════════════════
#  데이터 구조
# ═══════════════════════════════════════════════════════════

@dataclass
class PortfolioStock:
    stock_id: int
    ticker: str
    sector: str
    final_score: float
    signal_strength: float = 0
    current_price: float = 0
    atr_14: float = 0
    grade: str = ""
    # 비중 상세
    rp_weight: float = 0       # Risk Parity 비중
    hk_weight: float = 0       # Half-Kelly 비중
    conv_weight: float = 0     # Conviction 비중
    blended_weight: float = 0  # 블렌딩 후
    final_weight: float = 0    # 제약조건 적용 후
    # 결과
    shares: int = 0
    position_value: float = 0
    weight_pct: float = 0
    stop_loss_price: float = 0


@dataclass
class TargetPortfolio:
    stocks: List[PortfolioStock] = field(default_factory=list)
    total_invested: float = 0
    cash_balance: float = 0
    num_sectors: int = 0
    regime: str = "NEUTRAL"
    blend_method: str = ""      # 블렌딩 비율 설명
    optimization_time_ms: float = 0


# ═══════════════════════════════════════════════════════════
#  메인 빌더
# ═══════════════════════════════════════════════════════════

def build_portfolio(
    buy_candidates: list,
    account_value: float,
    regime: str,
    price_history: Optional[pd.DataFrame] = None,
    existing_tickers: Optional[List[str]] = None,
    dd_mult: float = 1.0,
    cb_mult: float = 1.0,
    cfg=None,
) -> TargetPortfolio:
    """
    3중 블렌딩 포트폴리오 구성.

    Parameters
    ----------
    buy_candidates : list of dict
        각 종목 정보 (stock_id, ticker, sector, final_score, grade,
                     current_price, atr_14, rsi_value, layer3_score, ...)
    account_value : float
        총 계좌 평가액
    regime : str
        현재 시장 국면
    price_history : DataFrame, optional
        종가 DataFrame (columns=tickers, index=dates) — RP/상관 계산용
    existing_tickers : list, optional
        기존 보유 종목 (상관관계 필터용)
    dd_mult : float
        DrawdownController 배수
    cb_mult : float
        CircuitBreaker 배수
    """
    import time
    t0 = time.time()

    if cfg is None:
        from risk.trading_config import DynamicConfig
        cfg = DynamicConfig()
        cfg.apply_regime(regime)

    if not buy_candidates:
        return TargetPortfolio(cash_balance=account_value, regime=regime)

    # ── Step 1: 점수 정렬 + 상위 후보 ──
    candidates = sorted(buy_candidates, key=lambda x: x.get("final_score", 0), reverse=True)
    candidates = candidates[:30]

    # ── Step 2: 섹터 부스트 ──
    try:
        from portfolio.sector_rotation import SectorRotation
        sr = SectorRotation()
        candidates = sr.adjust_candidate_scores(candidates, regime)
        candidates.sort(key=lambda x: x.get("sector_adjusted_score", x["final_score"]), reverse=True)
    except ImportError:
        pass

    # ── Step 3: 상관관계 필터 ──
    if price_history is not None and not price_history.empty:
        try:
            from portfolio.correlation_filter import CorrelationFilter
            corr_threshold = getattr(cfg, "correlation_max", 0.75)
            cf = CorrelationFilter(threshold=corr_threshold)
            candidates = cf.filter_candidates(candidates, existing_tickers or [], price_history)
        except ImportError:
            pass

    # ── Step 4: 종목 수 제한 ──
    max_pos = getattr(cfg, "max_positions", 15)
    candidates = candidates[:max_pos]

    if not candidates:
        return TargetPortfolio(cash_balance=account_value, regime=regime)

    N = len(candidates)
    tickers = [c["ticker"] for c in candidates]

    # ── Step 5: 3중 비중 계산 ──

    # (a) Risk Parity Weights
    rp_weights = _calc_risk_parity(tickers, price_history, N)

    # (b) Half-Kelly Weights
    hk_weights = _calc_half_kelly(candidates, N)

    # (c) Conviction Weights
    conv_weights = _calc_conviction(candidates, N, cfg)

    # ── Step 6: 국면별 블렌딩 ──
    alpha = getattr(cfg, "blend_rp", 0.40)
    beta = getattr(cfg, "blend_hk", 0.30)
    gamma = getattr(cfg, "blend_conv", 0.30)

    blended = alpha * rp_weights + beta * hk_weights + gamma * conv_weights

    # 정규화
    if blended.sum() > 0:
        blended = blended / blended.sum()

    # DD/CB 배수 적용
    effective_mult = dd_mult * cb_mult
    investable_pct = 1.0 - getattr(cfg, "cash_minimum", 0.20)
    investable = account_value * investable_pct * effective_mult

    # ── Step 7: 제약조건 적용 ──
    max_pct = getattr(cfg, "max_position_pct", 0.08)
    sector_max_pct = getattr(cfg, "sector_max_pct", 0.30)

    final_weights = _apply_constraints(
        blended, candidates, max_pct, sector_max_pct, account_value
    )

    # ── Step 8: 포지션 사이징 ──
    stocks = []
    total_invested = 0
    sector_counts = set()
    stop_atr_mult = getattr(cfg, "stop_loss_atr_mult", 1.8)

    for i, c in enumerate(candidates):
        w = final_weights[i]
        pos_value = investable * w
        price = c["current_price"]
        atr = c.get("atr_14", 0)

        if price <= 0 or pos_value < price:
            continue

        shares = int(pos_value / price)
        actual_value = shares * price
        stop_loss = round(price - stop_atr_mult * atr, 2) if atr > 0 else round(price * 0.92, 2)

        ps = PortfolioStock(
            stock_id=c["stock_id"],
            ticker=c["ticker"],
            sector=c.get("sector", "99"),
            final_score=c["final_score"],
            grade=c.get("grade", ""),
            current_price=price,
            atr_14=atr,
            rp_weight=round(float(rp_weights[i]), 4),
            hk_weight=round(float(hk_weights[i]), 4),
            conv_weight=round(float(conv_weights[i]), 4),
            blended_weight=round(float(blended[i]), 4),
            final_weight=round(float(w), 4),
            shares=shares,
            position_value=round(actual_value, 2),
            weight_pct=round(actual_value / account_value * 100, 2),
            stop_loss_price=max(0, stop_loss),
        )
        stocks.append(ps)
        total_invested += actual_value
        sector_counts.add(c.get("sector", "99"))

    elapsed = (time.time() - t0) * 1000

    return TargetPortfolio(
        stocks=stocks,
        total_invested=round(total_invested, 2),
        cash_balance=round(account_value - total_invested, 2),
        num_sectors=len(sector_counts),
        regime=regime,
        blend_method=f"RP={alpha:.0%} HK={beta:.0%} Conv={gamma:.0%}",
        optimization_time_ms=round(elapsed, 1),
    )


# ═══════════════════════════════════════════════════════════
#  비중 계산 함수
# ═══════════════════════════════════════════════════════════

def _calc_risk_parity(
    tickers: list, price_history: Optional[pd.DataFrame], n: int
) -> np.ndarray:
    """Risk Parity: 공분산 기반 동일 리스크 기여"""
    if price_history is None or price_history.empty:
        return np.ones(n) / n

    available = [t for t in tickers if t in price_history.columns]
    if len(available) < 2:
        return np.ones(n) / n

    returns = price_history[available].pct_change().dropna().tail(120)
    if len(returns) < 30:
        return np.ones(n) / n

    cov = returns.cov().values

    # Ledoit-Wolf Shrinkage (간이)
    n_obs = len(returns)
    shrink = min(1.0, max(0.0, (n_obs - 2) / (n_obs * (n_obs + 2))))
    target = np.diag(np.diag(cov))
    cov_shrunk = (1 - shrink) * cov + shrink * target

    # 역변동성 비중 → scipy 최적화
    vols = np.sqrt(np.diag(cov_shrunk))
    vols[vols == 0] = 1e-8
    inv_vol = 1.0 / vols
    rp = inv_vol / inv_vol.sum()

    # 만약 종목 수가 맞지 않으면 매핑
    full_weights = np.ones(n) / n
    idx_map = {t: i for i, t in enumerate(available)}
    for j, t in enumerate(tickers):
        if t in idx_map:
            full_weights[j] = rp[idx_map[t]]

    # 재정규화
    if full_weights.sum() > 0:
        full_weights = full_weights / full_weights.sum()

    return full_weights


def _calc_half_kelly(candidates: list, n: int) -> np.ndarray:
    """Half-Kelly: 승률/손익비 기반 최적 베팅"""
    weights = np.zeros(n)
    for i, c in enumerate(candidates):
        score = c.get("final_score", 50)
        # 점수 → 승률 근사 (선형 매핑: 50점=45%, 90점=75%)
        win_rate = 0.45 + (score - 50) / 40 * 0.30
        win_rate = max(0.10, min(0.90, win_rate))
        # 점수 → 손익비 (50점=1.2, 90점=2.5)
        wl_ratio = 1.2 + (score - 50) / 40 * 1.3
        wl_ratio = max(0.5, wl_ratio)

        full_kelly = (win_rate * wl_ratio - (1 - win_rate)) / wl_ratio
        half_kelly = max(0, full_kelly * 0.5)

        # 점수 스케일링
        scale = score / 100.0
        weights[i] = half_kelly * scale

    if weights.sum() > 0:
        weights = weights / weights.sum()

    return weights


def _calc_conviction(candidates: list, n: int, cfg) -> np.ndarray:
    """Conviction: 등급×점수 확신도 비중"""
    from risk.trading_config import GRADE_CONVICTION

    weights = np.zeros(n)
    for i, c in enumerate(candidates):
        score = c.get("final_score", 50)
        grade = c.get("grade", "B")
        grade_mult = GRADE_CONVICTION.get(grade, 1.0)

        conviction = max(0, (score - 50)) / 50  # 0~1
        weights[i] = (1 + conviction) * grade_mult

    if weights.sum() > 0:
        weights = weights / weights.sum()

    return weights


def _apply_constraints(
    weights: np.ndarray,
    candidates: list,
    max_position_pct: float,
    sector_max_pct: float,
    account_value: float,
) -> np.ndarray:
    """제약조건 적용 (종목 한도, 섹터 한도)"""
    n = len(weights)
    capped = weights.copy()

    # 종목별 상한
    for i in range(n):
        if capped[i] > max_position_pct:
            capped[i] = max_position_pct

    # 섹터별 상한
    sector_weights = {}
    for i, c in enumerate(candidates):
        sec = c.get("sector", "99")
        if sec not in sector_weights:
            sector_weights[sec] = []
        sector_weights[sec].append(i)

    for sec, indices in sector_weights.items():
        sec_total = sum(capped[i] for i in indices)
        if sec_total > sector_max_pct:
            scale = sector_max_pct / sec_total
            for i in indices:
                capped[i] *= scale

    # 재정규화
    if capped.sum() > 0:
        capped = capped / capped.sum()

    return capped
