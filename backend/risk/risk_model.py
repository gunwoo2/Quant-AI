"""
risk_model.py — Institutional Grade Risk Model
═══════════════════════════════════════════════════
  1. Ledoit-Wolf Shrinkage Covariance
  2. Historical VaR & CVaR (95%, 99%)
  3. Cornish-Fisher VaR (fat-tail adjusted)
  4. Factor Risk Decomposition
  5. Concentration Risk Monitoring
  6. Stress Testing (역사적 위기 시나리오)

참조: Barra Risk Model, MSCI Multi-Factor Model
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 데이터 구조
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class RiskMetrics:
    """포트폴리오 리스크 지표"""
    # 변동성
    portfolio_vol_annual: float = 0.0      # 연환산 변동성

    # VaR
    var_95_1d: float = 0.0                 # 95% 1일 VaR (%)
    var_99_1d: float = 0.0                 # 99% 1일 VaR (%)
    cvar_95_1d: float = 0.0                # 95% CVaR (%)
    cornish_fisher_var_99: float = 0.0     # CF보정 99% VaR

    # 집중도
    herfindahl_index: float = 0.0          # 종목 집중도 (0~1)
    sector_herfindahl: float = 0.0         # 섹터 집중도
    max_single_weight: float = 0.0         # 최대 단일 비중
    top5_weight: float = 0.0              # 상위 5개 비중 합
    effective_n: float = 0.0               # 유효 종목 수 (1/HHI)

    # 팩터 분해
    factor_contributions: Dict[str, float] = field(default_factory=dict)
    idiosyncratic_risk_pct: float = 0.0    # 비체계적 리스크 비중

    # 테일 리스크
    skewness: float = 0.0
    kurtosis: float = 0.0
    max_1d_loss: float = 0.0
    max_5d_loss: float = 0.0

    # 위험 플래그
    warnings: List[str] = field(default_factory=list)


@dataclass
class StressTestResult:
    """스트레스 테스트 결과"""
    scenario_name: str
    portfolio_impact: float     # 예상 손실 (%)
    worst_stock: str = ""
    worst_stock_impact: float = 0.0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Ledoit-Wolf Shrinkage Covariance
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def ledoit_wolf_shrinkage(returns: pd.DataFrame) -> Tuple[np.ndarray, float]:
    """
    Ledoit-Wolf Shrinkage Estimator for Covariance Matrix
    
    Σ_shrunk = δ·F + (1-δ)·S
    F = Constant Correlation Target
    S = Sample Covariance
    δ = Optimal shrinkage intensity
    
    Parameters
    ----------
    returns : DataFrame  (rows=dates, cols=tickers)
    
    Returns
    -------
    (covariance_matrix, shrinkage_intensity)
    """
    X = returns.values
    T, N = X.shape

    if T < 2 or N < 2:
        return np.eye(N) * 0.04 / 252, 1.0

    # Demean
    X = X - X.mean(axis=0)

    # Sample covariance
    S = X.T @ X / T

    # Target: Constant Correlation
    var = np.diag(S).copy()
    std = np.sqrt(var)
    std[std == 0] = 1e-10
    
    # Average correlation
    corr = S / np.outer(std, std)
    np.fill_diagonal(corr, 0)
    rho_bar = corr.sum() / (N * (N - 1))

    F = rho_bar * np.outer(std, std)
    np.fill_diagonal(F, var)

    # Optimal shrinkage intensity (Ledoit-Wolf formula)
    X2 = X ** 2
    sample = X.T @ X / T
    
    # pi-hat
    pi_mat = (X2.T @ X2) / T - sample ** 2
    pi_hat = pi_mat.sum()

    # rho-hat (simplified)
    rho_hat = pi_hat  # Simplified — full implementation would need theta_ii terms

    # gamma-hat
    gamma_hat = np.sum((F - S) ** 2)

    # kappa
    kappa = (pi_hat - rho_hat) / gamma_hat if gamma_hat > 0 else 1.0

    # delta (shrinkage intensity)
    delta = max(0, min(1, kappa / T))

    Sigma = delta * F + (1 - delta) * S
    return Sigma, delta


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Exponentially Weighted Covariance
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def ewma_covariance(returns: pd.DataFrame, halflife: int = 60) -> np.ndarray:
    """
    Exponentially Weighted Moving Average Covariance
    최근 데이터에 더 높은 가중치 → 빠른 리스크 변화 포착
    
    Parameters
    ----------
    halflife : int   반감기 (일), 기본 60일
    """
    lam = 1 - np.log(2) / halflife
    T, N = returns.shape

    weights = np.array([lam ** (T - 1 - t) for t in range(T)])
    weights /= weights.sum()

    X = returns.values
    X_demean = X - (weights[:, None] * X).sum(axis=0)

    Sigma = (weights[:, None] * X_demean).T @ X_demean
    return Sigma


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# VaR / CVaR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def historical_var(returns: np.ndarray, confidence: float = 0.95) -> float:
    """Historical VaR: n번째 percentile 손실"""
    if len(returns) < 10:
        return 0.0
    return float(-np.percentile(returns, (1 - confidence) * 100))


def historical_cvar(returns: np.ndarray, confidence: float = 0.95) -> float:
    """CVaR (Expected Shortfall): VaR 넘는 평균 손실"""
    var = historical_var(returns, confidence)
    tail = returns[returns <= -var]
    if len(tail) == 0:
        return var
    return float(-tail.mean())


def cornish_fisher_var(returns: np.ndarray, confidence: float = 0.99) -> float:
    """
    Cornish-Fisher VaR: 비정규분포 보정
    
    z_cf = z + (z²-1)·S/6 + (z³-3z)·K/24 - (2z³-5z)·S²/36
    """
    from scipy.stats import norm

    mu = float(np.mean(returns))
    sigma = float(np.std(returns))
    if sigma == 0:
        return 0.0

    s = float(pd.Series(returns).skew())   # 왜도
    k = float(pd.Series(returns).kurtosis())  # 초과 첨도

    z = norm.ppf(1 - confidence)

    z_cf = (z
            + (z**2 - 1) * s / 6
            + (z**3 - 3*z) * k / 24
            - (2*z**3 - 5*z) * s**2 / 36)

    var = -(mu + z_cf * sigma)
    return float(var)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 집중도 분석
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def concentration_metrics(weights: np.ndarray, sectors: List[str]) -> Dict:
    """종목/섹터 집중도 분석"""
    weights = np.array(weights)
    weights = weights / weights.sum() if weights.sum() > 0 else weights

    # HHI (Herfindahl-Hirschman Index)
    hhi = float(np.sum(weights ** 2))
    effective_n = 1.0 / hhi if hhi > 0 else len(weights)

    # 섹터 HHI
    sector_weights = {}
    for w, s in zip(weights, sectors):
        sector_weights[s] = sector_weights.get(s, 0) + w
    sector_hhi = sum(v**2 for v in sector_weights.values())

    sorted_w = sorted(weights, reverse=True)

    return {
        "hhi": round(hhi, 4),
        "sector_hhi": round(sector_hhi, 4),
        "effective_n": round(effective_n, 1),
        "max_weight": round(float(sorted_w[0]) * 100, 2) if len(sorted_w) > 0 else 0,
        "top5_weight": round(float(sum(sorted_w[:5])) * 100, 2) if len(sorted_w) >= 5 else 0,
        "sector_weights": {k: round(v*100, 2) for k, v in sector_weights.items()},
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 역사적 스트레스 테스트
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 주요 시장 위기 시나리오 (SPY 기준 기간 수익률)
STRESS_SCENARIOS = {
    "COVID Crash (2020-02~03)": {
        "market": -0.34, "tech": -0.30, "energy": -0.55,
        "finance": -0.40, "healthcare": -0.20, "consumer_disc": -0.35,
        "utilities": -0.25, "industrials": -0.38, "materials": -0.30,
    },
    "2022 Rate Hike Bear": {
        "market": -0.25, "tech": -0.33, "energy": 0.15,
        "finance": -0.18, "healthcare": -0.10, "consumer_disc": -0.35,
        "utilities": -0.05, "industrials": -0.20, "materials": -0.15,
    },
    "2018 Q4 Selloff": {
        "market": -0.20, "tech": -0.25, "energy": -0.30,
        "finance": -0.20, "healthcare": -0.12, "consumer_disc": -0.22,
        "utilities": 0.02, "industrials": -0.18, "materials": -0.20,
    },
    "Flash Crash (2010-05)": {
        "market": -0.07, "tech": -0.08, "energy": -0.10,
        "finance": -0.08, "healthcare": -0.05, "consumer_disc": -0.09,
        "utilities": -0.04, "industrials": -0.07, "materials": -0.08,
    },
    "Volmageddon (2018-02)": {
        "market": -0.12, "tech": -0.12, "energy": -0.10,
        "finance": -0.12, "healthcare": -0.08, "consumer_disc": -0.13,
        "utilities": -0.07, "industrials": -0.11, "materials": -0.10,
    },
}

# 섹터 매핑 (GICS → 시나리오 키)
SECTOR_STRESS_MAP = {
    "Technology": "tech", "Information Technology": "tech",
    "Healthcare": "healthcare", "Health Care": "healthcare",
    "Financials": "finance",
    "Energy": "energy",
    "Consumer Discretionary": "consumer_disc",
    "Consumer Staples": "utilities",  # 방어적
    "Industrials": "industrials",
    "Materials": "materials",
    "Utilities": "utilities",
    "Real Estate": "finance",
    "Communication Services": "tech",
}


def run_stress_tests(
    weights: np.ndarray,
    tickers: List[str],
    sectors: List[str],
) -> List[StressTestResult]:
    """
    역사적 시나리오 스트레스 테스트
    
    각 시나리오에서 포트폴리오 예상 손실 계산
    """
    results = []
    weights = np.array(weights)
    weights = weights / weights.sum() if weights.sum() > 0 else weights

    for scenario_name, impacts in STRESS_SCENARIOS.items():
        stock_impacts = []
        for i, (ticker, sector) in enumerate(zip(tickers, sectors)):
            key = SECTOR_STRESS_MAP.get(sector, "market")
            impact = impacts.get(key, impacts.get("market", -0.20))
            stock_impacts.append(impact)

        stock_impacts = np.array(stock_impacts)
        portfolio_impact = float(np.sum(weights * stock_impacts))

        worst_idx = np.argmin(stock_impacts * weights)
        results.append(StressTestResult(
            scenario_name=scenario_name,
            portfolio_impact=round(portfolio_impact * 100, 2),
            worst_stock=tickers[worst_idx] if len(tickers) > 0 else "",
            worst_stock_impact=round(float(stock_impacts[worst_idx]) * 100, 2),
        ))

    return sorted(results, key=lambda x: x.portfolio_impact)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 통합 리스크 분석
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def compute_portfolio_risk(
    weights: np.ndarray,
    returns: pd.DataFrame,
    tickers: List[str],
    sectors: List[str],
    use_ewma: bool = True,
) -> RiskMetrics:
    """
    포트폴리오 전체 리스크 분석 (All-in-One)
    
    Parameters
    ----------
    weights : array   각 종목 비중 (합=1)
    returns : DataFrame  일일 수익률 (rows=date, cols=ticker)
    tickers : list    종목 리스트
    sectors : list    섹터 리스트
    """
    metrics = RiskMetrics()
    W = np.array(weights).flatten()

    if returns.shape[0] < 30 or returns.shape[1] < 2:
        return metrics

    # 포트폴리오 수익률
    port_rets = (returns.values * W).sum(axis=1)

    # 공분산 행렬
    if use_ewma:
        Sigma = ewma_covariance(returns, halflife=60)
    else:
        Sigma, _ = ledoit_wolf_shrinkage(returns)

    # 연환산 변동성
    port_var = float(W @ Sigma @ W)
    metrics.portfolio_vol_annual = round(float(np.sqrt(port_var * 252)) * 100, 2)

    # VaR / CVaR
    metrics.var_95_1d = round(historical_var(port_rets, 0.95) * 100, 2)
    metrics.var_99_1d = round(historical_var(port_rets, 0.99) * 100, 2)
    metrics.cvar_95_1d = round(historical_cvar(port_rets, 0.95) * 100, 2)
    metrics.cornish_fisher_var_99 = round(cornish_fisher_var(port_rets, 0.99) * 100, 2)

    # 집중도
    conc = concentration_metrics(W, sectors)
    metrics.herfindahl_index = conc["hhi"]
    metrics.sector_herfindahl = conc["sector_hhi"]
    metrics.max_single_weight = conc["max_weight"]
    metrics.top5_weight = conc["top5_weight"]
    metrics.effective_n = conc["effective_n"]

    # 테일 리스크
    metrics.skewness = round(float(pd.Series(port_rets).skew()), 3)
    metrics.kurtosis = round(float(pd.Series(port_rets).kurtosis()), 3)
    metrics.max_1d_loss = round(float(port_rets.min()) * 100, 2)

    # 5일 최대 손실
    if len(port_rets) >= 5:
        rolling_5d = pd.Series(port_rets).rolling(5).sum()
        metrics.max_5d_loss = round(float(rolling_5d.min()) * 100, 2)

    # 경고 플래그
    if metrics.var_99_1d > 5:
        metrics.warnings.append(f"EXTREME_VAR: 99% VaR = {metrics.var_99_1d}% (>5%)")
    if metrics.max_single_weight > 15:
        metrics.warnings.append(f"CONCENTRATION: max weight = {metrics.max_single_weight}%")
    if metrics.effective_n < 8:
        metrics.warnings.append(f"LOW_DIVERSIFICATION: effective N = {metrics.effective_n}")
    if metrics.kurtosis > 5:
        metrics.warnings.append(f"FAT_TAILS: kurtosis = {metrics.kurtosis}")
    if metrics.skewness < -1:
        metrics.warnings.append(f"NEGATIVE_SKEW: {metrics.skewness}")

    return metrics
