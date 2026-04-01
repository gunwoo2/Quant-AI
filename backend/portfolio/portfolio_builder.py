"""
portfolio/portfolio_builder.py — Black-Litterman 포트폴리오 최적화 엔진 v5.0
================================================================================
v3.3 (RP+HK+Conv 블렌딩) → v5.0 (Black-Litterman + Regime Risk Budget)

핵심 변경:
  ★ Black-Litterman 모델 도입 (Prior + Views → Posterior)
    - Prior: 시가총액 비례 역최적화 → 균형 기대수익률 (Π)
    - Views: Ensemble Score → 기대 초과수익률 (Q), Conformal → 확신도 (Ω)
    - Posterior: Π + Q = BL 최적 가중치
  ★ Regime-Aware Risk Budget (국면별 자동 리스크 조절)
  ★ Conformal Prediction 신뢰도 → View 확신도(Omega) 연동
  ★ Net Benefit Filter: 기대alpha > 거래비용일 때만 교체

v3.3 유지:
  - 섹터 부스트 (sector_rotation)
  - 상관관계 필터 (correlation_filter)
  - Risk Parity / Half-Kelly / Conviction 블렌딩 (BL Fallback)
  - 국면별 블렌딩 비율
  - 제약조건 (섹터한도, 종목한도, 현금비율)
  - 포지션 사이징 (shares 계산)

학술 참조:
  - Black & Litterman (1992) "Global Portfolio Optimization"
  - He & Litterman (1999) "The Intuition Behind BL"
  - Meucci (2010) "The Black-Litterman Approach"
  - Idzorek (2005) "A Step-by-Step Guide to the BL Model"
"""
import numpy as np
import pandas as pd
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from scipy.optimize import minimize

logger = logging.getLogger("portfolio_builder")


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
    bl_weight: float = 0       # Black-Litterman 비중 (v5.0)
    blended_weight: float = 0  # 블렌딩 후
    final_weight: float = 0    # 제약조건 적용 후
    # BL 상세 (v5.0)
    bl_expected_return: float = 0   # BL 기대수익률
    view_confidence: float = 0      # View 확신도
    conformal_width: float = 0      # 예측 구간 너비
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
    blend_method: str = ""
    optimization_time_ms: float = 0
    bl_used: bool = False           # v5.0: BL 사용 여부
    bl_tau: float = 0.05            # v5.0: BL tau 파라미터


# ═══════════════════════════════════════════════════════════
#  Regime별 리스크 예산 (v5.0)
# ═══════════════════════════════════════════════════════════

REGIME_MAP = {
    "CRISIS": "CRISIS", "DEFLATION_SCARE": "RISK_OFF", "STAGFLATION": "CAUTIOUS",
    "REFLATION": "NEUTRAL", "GOLDILOCKS": "RISK_ON", "RISK_ON_RALLY": "EUPHORIA",
    "RISK_OFF": "RISK_OFF", "CAUTIOUS": "CAUTIOUS", "NEUTRAL": "NEUTRAL",
    "RISK_ON": "RISK_ON", "EUPHORIA": "EUPHORIA", "BEAR": "RISK_OFF", "BULL": "RISK_ON",
}

REGIME_RISK_BUDGET = {
    "CRISIS": {
        "max_invested_pct": 0.30,    # 최대 30% 투자 (70% 현금)
        "max_position_pct": 0.04,    # 종목당 최대 4%
        "sector_max_pct": 0.15,      # 섹터당 최대 15%
        "stop_loss_atr_mult": 1.2,   # 타이트한 손절
        "bl_weight": 0.2,            # BL 비중 낮음 (모델 불확실)
        "cash_minimum": 0.70,
    },
    "RISK_OFF": {
        "max_invested_pct": 0.50,
        "max_position_pct": 0.06,
        "sector_max_pct": 0.20,
        "stop_loss_atr_mult": 1.5,
        "bl_weight": 0.3,
        "cash_minimum": 0.50,
    },
    "CAUTIOUS": {
        "max_invested_pct": 0.70,
        "max_position_pct": 0.07,
        "sector_max_pct": 0.25,
        "stop_loss_atr_mult": 1.8,
        "bl_weight": 0.4,
        "cash_minimum": 0.30,
    },
    "NEUTRAL": {
        "max_invested_pct": 0.80,
        "max_position_pct": 0.08,
        "sector_max_pct": 0.30,
        "stop_loss_atr_mult": 2.0,
        "bl_weight": 0.5,
        "cash_minimum": 0.20,
    },
    "RISK_ON": {
        "max_invested_pct": 0.95,
        "max_position_pct": 0.12,
        "sector_max_pct": 0.35,
        "stop_loss_atr_mult": 2.5,
        "bl_weight": 0.6,
        "cash_minimum": 0.05,
    },
    "EUPHORIA": {
        "max_invested_pct": 0.85,    # 과열: 약간 방어
        "max_position_pct": 0.10,
        "sector_max_pct": 0.30,
        "stop_loss_atr_mult": 1.5,
        "bl_weight": 0.4,
        "cash_minimum": 0.15,
    },
}


# ═══════════════════════════════════════════════════════════
#  Black-Litterman 핵심 로직
# ═══════════════════════════════════════════════════════════

class BlackLittermanOptimizer:
    """
    Black-Litterman 모델.
    
    Flow:
      1. Prior: 시장 균형 기대수익률 (Π = δ * Σ * w_mkt)
      2. Views: AI Score → 초과수익률, Conformal → 확신도
      3. Posterior: BL 결합 → 최적 가중치
    """
    
    def __init__(
        self,
        risk_aversion: float = 2.5,   # δ (시장 위험회피 계수)
        tau: float = 0.05,             # τ (Prior 불확실성)
    ):
        self.delta = risk_aversion
        self.tau = tau
    
    def compute_prior(
        self,
        cov_matrix: np.ndarray,
        market_weights: np.ndarray,
    ) -> np.ndarray:
        """
        균형 기대수익률 Π = δ * Σ * w_mkt.
        
        Parameters:
            cov_matrix: N×N 공분산 행렬 (연율화)
            market_weights: N차원 시가총액 비례 비중
        
        Returns:
            Π (N차원 균형 기대수익률)
        """
        return self.delta * cov_matrix @ market_weights
    
    def compute_posterior(
        self,
        cov_matrix: np.ndarray,
        prior_returns: np.ndarray,
        P: np.ndarray,
        Q: np.ndarray,
        omega: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        BL Posterior 기대수익률 & 공분산.
        
        Parameters:
            cov_matrix: Σ (N×N)
            prior_returns: Π (N)
            P: K×N Pick Matrix (각 View가 참조하는 종목)
            Q: K차원 View Vector (기대 초과수익률)
            omega: K×K View Uncertainty Matrix (대각행렬)
        
        Returns:
            (posterior_returns, posterior_cov)
        """
        tau_sigma = self.tau * cov_matrix
        
        # BL 공식
        # E[R] = [(τΣ)^-1 + P'Ω^-1 P]^-1 × [(τΣ)^-1 Π + P'Ω^-1 Q]
        tau_sigma_inv = np.linalg.inv(tau_sigma)
        omega_inv = np.linalg.inv(omega)
        
        # Posterior precision
        post_precision = tau_sigma_inv + P.T @ omega_inv @ P
        post_cov = np.linalg.inv(post_precision)
        
        # Posterior mean
        post_mean = post_cov @ (tau_sigma_inv @ prior_returns + P.T @ omega_inv @ Q)
        
        return post_mean, post_cov
    
    def optimal_weights(
        self,
        posterior_returns: np.ndarray,
        posterior_cov: np.ndarray,
        constraints: dict = None,
    ) -> np.ndarray:
        """
        Mean-Variance 최적화로 최적 비중 계산.
        
        Maximize: w'μ - (δ/2) w'Σw
        Subject to: w >= 0, Σw = 1
        """
        N = len(posterior_returns)
        
        if constraints is None:
            constraints = {}
        
        max_weight = constraints.get("max_weight", 0.15)
        
        # 목적함수: -utility (minimize)
        def neg_utility(w):
            ret = w @ posterior_returns
            risk = w @ posterior_cov @ w
            return -(ret - 0.5 * self.delta * risk)
        
        # 제약조건
        cons = [
            {"type": "eq", "fun": lambda w: np.sum(w) - 1.0},  # 합=1
        ]
        
        # 범위: Long-Only + max weight
        bounds = [(0, max_weight) for _ in range(N)]
        
        # 초기값: 균등
        w0 = np.ones(N) / N
        
        result = minimize(
            neg_utility, w0,
            method="SLSQP",
            bounds=bounds,
            constraints=cons,
            options={"maxiter": 500, "ftol": 1e-10},
        )
        
        if result.success:
            weights = result.x
            weights = np.maximum(weights, 0)
            weights = weights / weights.sum()
            return weights
        else:
            logger.warning(f"[BL] Optimization failed: {result.message}. Falling back to equal weight.")
            return np.ones(N) / N


def _build_views_from_scores(
    candidates: list,
    cov_matrix: np.ndarray,
    tau: float = 0.05,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    AI Ensemble Score → BL View 변환.
    
    각 종목에 대한 Absolute View:
      Q[i] = (score - 50) / 50 * max_view_return
      Ω[i,i] = τ * σ_i^2 / confidence
    
    Parameters:
        candidates: 후보 종목 리스트
        cov_matrix: N×N 공분산
        tau: BL tau
    
    Returns:
        P (K×N), Q (K), omega (K×K)
    """
    N = len(candidates)
    max_view_return = 0.20  # 최대 View = 연 20% 초과수익
    
    # Absolute views: P = Identity (각 종목 개별 View)
    P = np.eye(N)
    
    # Q: score 기반 기대수익률
    Q = np.zeros(N)
    omega_diag = np.zeros(N)
    
    for i, c in enumerate(candidates):
        score = c.get("final_score", 50)
        confidence = c.get("view_confidence", 0.5)
        conformal_width = c.get("conformal_width", 0.1)
        
        # Score → 초과수익률 (0~100 → -max~+max)
        view_return = (score - 50) / 50 * max_view_return
        Q[i] = view_return
        
        # Omega: 불확실성 (confidence 높으면 Omega 낮음 → 강한 View)
        # Conformal 구간 넓으면 → 불확실 → Omega 높음
        sigma_i = np.sqrt(cov_matrix[i, i]) if cov_matrix[i, i] > 0 else 0.3
        
        # confidence 0~1, conformal_width 높으면 불확실
        certainty = max(0.05, min(confidence, 1.0))
        width_penalty = 1.0 + conformal_width * 5  # 구간 넓으면 불확실성 UP
        
        omega_diag[i] = (tau * sigma_i ** 2) / certainty * width_penalty
    
    omega = np.diag(omega_diag)
    
    return P, Q, omega


def _estimate_market_weights(candidates: list) -> np.ndarray:
    """시가총액 비례 비중 추정 (간이 버전: 가격 기반)"""
    caps = np.array([c.get("market_cap", 0) for c in candidates], dtype=float)
    if caps.sum() > 0 and np.count_nonzero(caps) >= len(candidates) * 0.5:
        weights = caps / caps.sum()
    else:
        prices = np.array([c.get("current_price", 100) for c in candidates], dtype=float)
        weights = prices / prices.sum() if prices.sum() > 0 else np.ones(len(candidates)) / len(candidates)
    return weights


def _estimate_covariance(
    tickers: list,
    price_history: Optional[pd.DataFrame],
    default_vol: float = 0.25,
) -> np.ndarray:
    """공분산 행렬 추정"""
    N = len(tickers)
    
    if price_history is not None and not price_history.empty:
        available = [t for t in tickers if t in price_history.columns]
        if len(available) >= 2:
            returns = price_history[available].pct_change().dropna()
            if len(returns) >= 20:
                cov = returns.cov().values * 252  # 연율화
                
                # 종목 수 맞추기
                if len(available) < N:
                    full_cov = np.eye(N) * default_vol ** 2
                    ticker_idx = {t: i for i, t in enumerate(tickers)}
                    avail_idx = {t: i for i, t in enumerate(available)}
                    for t in available:
                        ti = ticker_idx[t]
                        ai = avail_idx[t]
                        for t2 in available:
                            ti2 = ticker_idx[t2]
                            ai2 = avail_idx[t2]
                            if ai < cov.shape[0] and ai2 < cov.shape[1]:
                                full_cov[ti, ti2] = cov[ai, ai2]
                    return full_cov
                
                return cov
    
    # Fallback: 대각 공분산 (상관=0 가정)
    return np.eye(N) * default_vol ** 2


# ═══════════════════════════════════════════════════════════
#  기존 3중 블렌딩 (BL Fallback)
# ═══════════════════════════════════════════════════════════

def _calc_risk_parity(tickers, price_history, n):
    """Risk Parity 비중"""
    w = np.ones(n) / n
    if price_history is None or price_history.empty:
        return w
    try:
        available = [t for t in tickers if t in price_history.columns]
        if len(available) < 2:
            return w
        rets = price_history[available].pct_change().dropna()
        if len(rets) < 20:
            return w
        vols = rets.std().values * np.sqrt(252)
        inv_vol = 1.0 / np.maximum(vols, 0.01)
        rp = inv_vol / inv_vol.sum()
        # 크기 맞추기
        if len(rp) < n:
            full = np.ones(n) / n
            for i, t in enumerate(available):
                idx = tickers.index(t) if t in tickers else None
                if idx is not None:
                    full[idx] = rp[i]
            return full / full.sum()
        return rp
    except Exception:
        return w


def _calc_half_kelly(candidates, n):
    """Half-Kelly 비중"""
    scores = np.array([c.get("final_score", 50) for c in candidates])
    win_rate = np.clip(scores / 100, 0.3, 0.8)
    odds = np.where(scores > 60, 1.5, 1.0)
    kelly = win_rate - (1 - win_rate) / odds
    hk = np.clip(kelly / 2, 0, 0.25)
    total = hk.sum()
    return hk / total if total > 0 else np.ones(n) / n


def _calc_conviction(candidates, n, cfg=None):
    """Conviction 비중"""
    grade_map = {"S": 1.0, "A+": 0.85, "A": 0.7, "B+": 0.55, "B": 0.4, "C": 0.2, "D": 0.1}
    convictions = []
    for c in candidates:
        g = grade_map.get(c.get("grade", "C"), 0.3)
        s = c.get("final_score", 50) / 100
        convictions.append(g * s)
    w = np.array(convictions)
    total = w.sum()
    return w / total if total > 0 else np.ones(n) / n


def _apply_constraints(weights, candidates, max_pct, sector_max_pct, account_value):
    """제약조건 적용: 종목상한 + 섹터상한"""
    w = weights.copy()
    N = len(w)
    
    # 종목 상한
    for i in range(N):
        if w[i] > max_pct:
            excess = w[i] - max_pct
            w[i] = max_pct
            others = [j for j in range(N) if j != i and w[j] > 0]
            if others:
                share = excess / len(others)
                for j in others:
                    w[j] += share
    
    # 섹터 상한
    sector_weights = {}
    for i, c in enumerate(candidates):
        s = c.get("sector", "99")
        sector_weights.setdefault(s, []).append(i)
    
    for sec, indices in sector_weights.items():
        sec_total = sum(w[i] for i in indices)
        if sec_total > sector_max_pct:
            scale = sector_max_pct / sec_total
            for i in indices:
                w[i] *= scale
    
    # 재정규화
    total = w.sum()
    if total > 0:
        w = w / total
    
    return w


# ═══════════════════════════════════════════════════════════
#  메인 빌더 v5.0
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
    v5.0 Black-Litterman + 3중 블렌딩 포트폴리오 구성.
    
    BL 가용 시: BL 비중과 기존 3중 블렌딩을 국면별 비율로 결합
    BL 불가 시: 기존 3중 블렌딩만 사용 (Graceful Degradation)
    """
    import time
    t0 = time.time()
    
    # Regime별 리스크 예산
    mapped_regime = REGIME_MAP.get(regime, "NEUTRAL")
    risk_budget = REGIME_RISK_BUDGET.get(mapped_regime, REGIME_RISK_BUDGET["NEUTRAL"])
    
    if cfg is None:
        try:
            from risk.trading_config import DynamicConfig
            cfg = DynamicConfig()
            cfg.apply_regime(regime)
        except ImportError:
            cfg = type("Cfg", (), {
                "max_positions": 15,
                "correlation_max": 0.75,
                "cash_minimum": risk_budget["cash_minimum"],
                "max_position_pct": risk_budget["max_position_pct"],
                "sector_max_pct": risk_budget["sector_max_pct"],
                "stop_loss_atr_mult": risk_budget["stop_loss_atr_mult"],
                "blend_rp": 0.40,
                "blend_hk": 0.30,
                "blend_conv": 0.30,
            })()
    
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
    except (ImportError, Exception) as e:
        logger.debug(f"[PB] sector rotation skip: {e}")
    
    # ── Step 3: 상관관계 필터 ──
    if price_history is not None and not price_history.empty:
        try:
            from portfolio.correlation_filter import CorrelationFilter
            corr_threshold = getattr(cfg, "correlation_max", 0.75)
            cf = CorrelationFilter(threshold=corr_threshold)
            candidates = cf.filter_candidates(candidates, existing_tickers or [], price_history)
        except (ImportError, Exception) as e:
            logger.debug(f"[PB] correlation filter skip: {e}")
    
    # ── Step 4: 종목 수 제한 ──
    max_pos = getattr(cfg, "max_positions", 15)
    candidates = candidates[:max_pos]
    
    if not candidates:
        return TargetPortfolio(cash_balance=account_value, regime=regime)
    
    N = len(candidates)
    tickers = [c["ticker"] for c in candidates]
    
    # ═══════════════════════════════════════════════════════
    #  Black-Litterman (v5.0 핵심)
    # ═══════════════════════════════════════════════════════
    
    bl_used = False
    bl_weights = np.ones(N) / N
    bl_expected_returns = np.zeros(N)
    bl_tau = 0.05
    
    try:
        # 공분산 추정
        cov_matrix = _estimate_covariance(tickers, price_history)
        
        # 시장 비중 추정
        market_weights = _estimate_market_weights(candidates)
        
        # BL Optimizer
        bl = BlackLittermanOptimizer(risk_aversion=2.5, tau=bl_tau)
        
        # Prior: 균형 기대수익률
        prior_returns = bl.compute_prior(cov_matrix, market_weights)
        
        # Views: Score → 기대수익률, Conformal → 확신도
        P, Q, omega = _build_views_from_scores(candidates, cov_matrix, bl_tau)
        
        # Posterior
        post_returns, post_cov = bl.compute_posterior(cov_matrix, prior_returns, P, Q, omega)
        
        # 최적 비중
        bl_weights = bl.optimal_weights(
            post_returns, post_cov,
            constraints={"max_weight": risk_budget["max_position_pct"]},
        )
        
        bl_expected_returns = post_returns
        bl_used = True
        logger.info(f"[PB] ✅ BL 최적화 성공 (N={N})")
        
    except Exception as e:
        logger.warning(f"[PB] ⚠️ BL 실패, 기존 블렌딩 사용: {e}")
        bl_weights = np.ones(N) / N
    
    # ═══════════════════════════════════════════════════════
    #  기존 3중 블렌딩 (항상 계산 — Fallback + 블렌딩용)
    # ═══════════════════════════════════════════════════════
    
    rp_weights = _calc_risk_parity(tickers, price_history, N)
    hk_weights = _calc_half_kelly(candidates, N)
    conv_weights = _calc_conviction(candidates, N, cfg)
    
    alpha = getattr(cfg, "blend_rp", 0.40)
    beta = getattr(cfg, "blend_hk", 0.30)
    gamma = getattr(cfg, "blend_conv", 0.30)
    
    traditional = alpha * rp_weights + beta * hk_weights + gamma * conv_weights
    if traditional.sum() > 0:
        traditional = traditional / traditional.sum()
    
    # ═══════════════════════════════════════════════════════
    #  BL + Traditional 최종 블렌딩
    # ═══════════════════════════════════════════════════════
    
    bl_blend = risk_budget.get("bl_weight", 0.5) if bl_used else 0.0
    trad_blend = 1.0 - bl_blend
    
    blended = bl_blend * bl_weights + trad_blend * traditional
    if blended.sum() > 0:
        blended = blended / blended.sum()
    
    blend_desc = f"BL={bl_blend:.0%} + Trad(RP={alpha:.0%}/HK={beta:.0%}/Conv={gamma:.0%})={trad_blend:.0%}"
    
    # ── DD/CB 배수 적용 ──
    effective_mult = dd_mult * cb_mult
    cash_min = risk_budget.get("cash_minimum", getattr(cfg, "cash_minimum", 0.20))
    investable_pct = 1.0 - cash_min
    investable = account_value * investable_pct * effective_mult
    
    # ── 제약조건 적용 ──
    max_pct = risk_budget["max_position_pct"]
    sector_max = risk_budget["sector_max_pct"]
    
    final_weights = _apply_constraints(blended, candidates, max_pct, sector_max, account_value)
    
    # ── 포지션 사이징 ──
    stocks = []
    total_invested = 0
    sector_counts = set()
    stop_atr_mult = risk_budget.get("stop_loss_atr_mult", getattr(cfg, "stop_loss_atr_mult", 1.8))
    
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
            bl_weight=round(float(bl_weights[i]), 4),
            blended_weight=round(float(blended[i]), 4),
            final_weight=round(float(w), 4),
            bl_expected_return=round(float(bl_expected_returns[i]), 6) if bl_used else 0,
            view_confidence=c.get("view_confidence", 0.5),
            conformal_width=c.get("conformal_width", 0.1),
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
        blend_method=blend_desc,
        optimization_time_ms=round(elapsed, 1),
        bl_used=bl_used,
        bl_tau=bl_tau,
    )
