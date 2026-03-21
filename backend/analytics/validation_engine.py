"""
validation_engine.py — Statistical Validation Engine
═══════════════════════════════════════════════════════
  1. Walk-Forward Optimization (과적합 방지)
  2. Block Bootstrap Monte Carlo (5000 paths, 통계적 유의성)
  3. Permutation Test (시그널 유의미성)
  4. Robustness Ratio (IS vs OOS 비교)
  5. Deflated Sharpe Ratio (다중 검정 보정)

참조: 
  - Marcos López de Prado, "Advances in Financial ML"
  - Harvey/Liu/Zhu "...and the Cross-Section of Expected Returns"
  - Bailey/Borwein/López de Prado "Pseudo-Mathematics & Financial Charlatanism"
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from datetime import date, timedelta


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 데이터 구조
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class WalkForwardResult:
    """Walk-Forward 단일 윈도우 결과"""
    train_start: date
    train_end: date
    test_start: date
    test_end: date
    is_sharpe: float       # In-Sample Sharpe
    oos_sharpe: float      # Out-of-Sample Sharpe
    is_return: float       # IS 수익률
    oos_return: float      # OOS 수익률
    weights_used: Dict[str, float] = field(default_factory=dict)


@dataclass
class MonteCarloResult:
    """Monte Carlo 시뮬레이션 결과"""
    n_simulations: int = 5000
    
    # Sharpe Ratio 분포
    sharpe_mean: float = 0.0
    sharpe_median: float = 0.0
    sharpe_std: float = 0.0
    sharpe_ci_lower: float = 0.0   # 95% CI 하한
    sharpe_ci_upper: float = 0.0   # 95% CI 상한
    
    # 총 수익률 분포
    return_mean: float = 0.0
    return_ci_lower: float = 0.0
    return_ci_upper: float = 0.0
    prob_positive: float = 0.0      # 양수 수익률 확률
    
    # Max Drawdown 분포
    mdd_mean: float = 0.0
    mdd_ci_lower: float = 0.0
    mdd_ci_upper: float = 0.0
    
    # vs 벤치마크
    prob_beat_spy: float = 0.0
    excess_return_ci: Tuple[float, float] = (0.0, 0.0)


@dataclass
class ValidationReport:
    """전체 검증 리포트"""
    # Walk-Forward
    wf_results: List[WalkForwardResult] = field(default_factory=list)
    wf_avg_oos_sharpe: float = 0.0
    wf_robustness_ratio: float = 0.0  # OOS/IS Sharpe 비율
    wf_overfit_warning: bool = False
    
    # Monte Carlo
    mc_result: Optional[MonteCarloResult] = None
    
    # Permutation Test
    permutation_p_value: float = 1.0
    signal_is_significant: bool = False
    
    # Deflated Sharpe Ratio
    deflated_sharpe: float = 0.0
    deflated_sr_is_significant: bool = False
    
    # 종합 판단
    overall_confidence: str = "LOW"  # LOW, MODERATE, HIGH, VERY_HIGH
    red_flags: List[str] = field(default_factory=list)
    green_flags: List[str] = field(default_factory=list)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. Walk-Forward Optimization
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def walk_forward_optimization(
    daily_returns: pd.Series,
    train_months: int = 12,
    test_months: int = 3,
    step_months: int = 3,
) -> List[WalkForwardResult]:
    """
    Walk-Forward Optimization
    
    Train 기간에서 최적화 → Test 기간에서 OOS 성과 측정
    Window를 step_months씩 슬라이딩
    
    Parameters
    ----------
    daily_returns : Series  (index=date, value=daily_return)
    train_months : int      학습 기간 (기본 12개월)
    test_months : int       테스트 기간 (기본 3개월)
    step_months : int       슬라이딩 간격 (기본 3개월)
    """
    results = []
    
    dates = sorted(daily_returns.index)
    if len(dates) < (train_months + test_months) * 21:
        return results
    
    start = dates[0]
    end = dates[-1]
    
    current = start
    while True:
        train_start = current
        train_end = train_start + timedelta(days=train_months * 30)
        test_start = train_end + timedelta(days=1)
        test_end = test_start + timedelta(days=test_months * 30)
        
        if test_end > end:
            break
        
        # Train period returns
        train_rets = daily_returns[
            (daily_returns.index >= train_start) & (daily_returns.index <= train_end)
        ]
        # Test period returns
        test_rets = daily_returns[
            (daily_returns.index >= test_start) & (daily_returns.index <= test_end)
        ]
        
        if len(train_rets) < 60 or len(test_rets) < 20:
            current += timedelta(days=step_months * 30)
            continue
        
        is_sharpe = _compute_sharpe(train_rets)
        oos_sharpe = _compute_sharpe(test_rets)
        
        results.append(WalkForwardResult(
            train_start=train_start,
            train_end=train_end,
            test_start=test_start,
            test_end=test_end,
            is_sharpe=round(is_sharpe, 3),
            oos_sharpe=round(oos_sharpe, 3),
            is_return=round(float(train_rets.sum()) * 100, 2),
            oos_return=round(float(test_rets.sum()) * 100, 2),
        ))
        
        current += timedelta(days=step_months * 30)
    
    return results


def _compute_sharpe(returns: pd.Series, risk_free: float = 0.0) -> float:
    """일일 수익률 → 연환산 Sharpe"""
    if len(returns) < 10:
        return 0.0
    mean = float(returns.mean()) - risk_free / 252
    std = float(returns.std())
    if std == 0:
        return 0.0
    return mean / std * np.sqrt(252)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. Block Bootstrap Monte Carlo
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def block_bootstrap_monte_carlo(
    daily_returns: np.ndarray,
    n_simulations: int = 5000,
    block_size: int = 20,
    n_days: int = 252,
    spy_returns: Optional[np.ndarray] = None,
) -> MonteCarloResult:
    """
    Block Bootstrap Monte Carlo Simulation
    
    블록 단위 리샘플링으로 자기상관 구조 보존
    
    Parameters
    ----------
    daily_returns : array   실제 일일 수익률
    n_simulations : int     시뮬레이션 횟수
    block_size : int        블록 크기 (일)
    n_days : int            시뮬레이션 기간 (거래일)
    spy_returns : array     벤치마크 수익률 (같은 기간)
    """
    result = MonteCarloResult(n_simulations=n_simulations)
    T = len(daily_returns)
    
    if T < block_size * 2:
        return result
    
    sharpes = []
    total_returns = []
    max_drawdowns = []
    
    rng = np.random.default_rng(42)
    
    for _ in range(n_simulations):
        # 블록 리샘플링
        sim_returns = []
        while len(sim_returns) < n_days:
            start = rng.integers(0, T - block_size)
            block = daily_returns[start:start + block_size]
            sim_returns.extend(block)
        sim_returns = np.array(sim_returns[:n_days])
        
        # 성과 지표
        sharpe = _compute_sharpe_from_array(sim_returns)
        sharpes.append(sharpe)
        
        cum = np.cumprod(1 + sim_returns)
        total_ret = (cum[-1] - 1) * 100
        total_returns.append(total_ret)
        
        peak = np.maximum.accumulate(cum)
        dd = (cum - peak) / peak
        max_drawdowns.append(float(dd.min()) * 100)
    
    sharpes = np.array(sharpes)
    total_returns = np.array(total_returns)
    max_drawdowns = np.array(max_drawdowns)
    
    result.sharpe_mean = round(float(np.mean(sharpes)), 3)
    result.sharpe_median = round(float(np.median(sharpes)), 3)
    result.sharpe_std = round(float(np.std(sharpes)), 3)
    result.sharpe_ci_lower = round(float(np.percentile(sharpes, 2.5)), 3)
    result.sharpe_ci_upper = round(float(np.percentile(sharpes, 97.5)), 3)
    
    result.return_mean = round(float(np.mean(total_returns)), 2)
    result.return_ci_lower = round(float(np.percentile(total_returns, 2.5)), 2)
    result.return_ci_upper = round(float(np.percentile(total_returns, 97.5)), 2)
    result.prob_positive = round(float(np.mean(total_returns > 0)), 3)
    
    result.mdd_mean = round(float(np.mean(max_drawdowns)), 2)
    result.mdd_ci_lower = round(float(np.percentile(max_drawdowns, 2.5)), 2)
    result.mdd_ci_upper = round(float(np.percentile(max_drawdowns, 97.5)), 2)
    
    # SPY 대비
    if spy_returns is not None and len(spy_returns) >= block_size:
        spy_sharpe = _compute_sharpe_from_array(spy_returns[:n_days] if len(spy_returns) >= n_days else spy_returns)
        result.prob_beat_spy = round(float(np.mean(sharpes > spy_sharpe)), 3)
        
        spy_total = (np.prod(1 + spy_returns[:n_days]) - 1) * 100 if len(spy_returns) >= n_days else 0
        excess = total_returns - spy_total
        result.excess_return_ci = (
            round(float(np.percentile(excess, 2.5)), 2),
            round(float(np.percentile(excess, 97.5)), 2),
        )
    
    return result


def _compute_sharpe_from_array(rets: np.ndarray) -> float:
    if len(rets) < 10:
        return 0.0
    m = float(np.mean(rets))
    s = float(np.std(rets))
    return m / s * np.sqrt(252) if s > 0 else 0.0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. Permutation Test
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def permutation_test(
    actual_sharpe: float,
    daily_returns: np.ndarray,
    n_permutations: int = 1000,
) -> float:
    """
    시그널 유의미성 Permutation Test
    
    일일 수익률의 순서를 무작위로 섞어 "무작위 전략"의 Sharpe 분포 생성
    실제 Sharpe가 상위 5% 이내 → 시그널 유의미
    
    Returns: p-value (낮을수록 유의미)
    """
    rng = np.random.default_rng(42)
    random_sharpes = []
    
    for _ in range(n_permutations):
        shuffled = rng.permutation(daily_returns)
        s = _compute_sharpe_from_array(shuffled)
        random_sharpes.append(s)
    
    random_sharpes = np.array(random_sharpes)
    # p-value = 무작위 중 실제보다 좋은 비율
    p_value = float(np.mean(random_sharpes >= actual_sharpe))
    return round(p_value, 4)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. Deflated Sharpe Ratio (다중 검정 보정)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def deflated_sharpe_ratio(
    observed_sharpe: float,
    n_trials: int,
    n_observations: int,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
    variance_of_sharpes: float = 1.0,
) -> float:
    """
    Deflated Sharpe Ratio (Bailey & López de Prado, 2014)
    
    여러 전략/파라미터를 시도한 경우, 최고 Sharpe가 운인지 검증
    
    DSR = Φ( (SR - E[max SR]) / σ[max SR] )
    
    Parameters
    ----------
    observed_sharpe : float   관측된 Sharpe
    n_trials : int            시도한 전략 수
    n_observations : int      관측값 수 (일수)
    skewness : float          수익률 왜도
    kurtosis : float          수익률 첨도 (정규=3)
    """
    from scipy.stats import norm
    
    if n_trials <= 0 or n_observations <= 0:
        return 0.0
    
    # Expected max of n_trials standard normals
    euler = 0.5772156649  # Euler-Mascheroni constant
    
    e_max = variance_of_sharpes * (
        (1 - euler) * norm.ppf(1 - 1/n_trials)
        + euler * norm.ppf(1 - 1/(n_trials * np.e))
    )
    
    # Variance correction for non-normal returns
    sr_std = np.sqrt(
        (1 + 0.5 * observed_sharpe**2
         - skewness * observed_sharpe
         + ((kurtosis - 3) / 4) * observed_sharpe**2)
        / (n_observations - 1)
    )
    
    if sr_std <= 0:
        return 0.0
    
    dsr = norm.cdf((observed_sharpe - e_max) / sr_std)
    return round(float(dsr), 4)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. 종합 검증 리포트
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def generate_validation_report(
    daily_returns: np.ndarray,
    spy_returns: Optional[np.ndarray] = None,
    observed_sharpe: float = 0.0,
    n_strategy_trials: int = 10,
) -> ValidationReport:
    """
    전체 통계적 검증 리포트 생성
    
    이 함수 하나로 "이 전략 진짜인가?" 판단 가능
    """
    report = ValidationReport()
    
    rets_series = pd.Series(daily_returns, index=pd.date_range(
        start="2020-01-01", periods=len(daily_returns), freq="B"
    ))
    
    # ── Walk-Forward ──
    print("[VAL] Walk-Forward Optimization 실행...")
    wf = walk_forward_optimization(rets_series, train_months=12, test_months=3)
    report.wf_results = wf
    
    if wf:
        is_sharpes = [w.is_sharpe for w in wf]
        oos_sharpes = [w.oos_sharpe for w in wf]
        report.wf_avg_oos_sharpe = round(float(np.mean(oos_sharpes)), 3)
        
        avg_is = float(np.mean(is_sharpes)) if is_sharpes else 1
        avg_oos = float(np.mean(oos_sharpes)) if oos_sharpes else 0
        report.wf_robustness_ratio = round(avg_oos / avg_is, 3) if avg_is > 0 else 0
        report.wf_overfit_warning = report.wf_robustness_ratio < 0.5
    
    # ── Monte Carlo ──
    print("[VAL] Monte Carlo 시뮬레이션 (5000 paths)...")
    mc = block_bootstrap_monte_carlo(
        daily_returns, n_simulations=5000, spy_returns=spy_returns
    )
    report.mc_result = mc
    
    # ── Permutation Test ──
    print("[VAL] Permutation Test (1000 shuffles)...")
    p_value = permutation_test(observed_sharpe, daily_returns, n_permutations=1000)
    report.permutation_p_value = p_value
    report.signal_is_significant = p_value < 0.05
    
    # ── Deflated Sharpe Ratio ──
    skew = float(pd.Series(daily_returns).skew()) if len(daily_returns) > 10 else 0
    kurt = float(pd.Series(daily_returns).kurtosis()) + 3 if len(daily_returns) > 10 else 3
    
    dsr = deflated_sharpe_ratio(
        observed_sharpe, n_strategy_trials,
        len(daily_returns), skew, kurt
    )
    report.deflated_sharpe = dsr
    report.deflated_sr_is_significant = dsr > 0.95
    
    # ── 종합 판단 ──
    green = 0
    
    if report.wf_robustness_ratio >= 0.6:
        report.green_flags.append(f"WFO Robustness {report.wf_robustness_ratio:.2f} >= 0.6")
        green += 1
    else:
        report.red_flags.append(f"WFO Robustness {report.wf_robustness_ratio:.2f} < 0.6 (과적합 위험)")
    
    if mc.prob_positive >= 0.85:
        report.green_flags.append(f"양수 수익 확률 {mc.prob_positive:.0%} >= 85%")
        green += 1
    elif mc.prob_positive < 0.70:
        report.red_flags.append(f"양수 수익 확률 {mc.prob_positive:.0%} < 70%")
    
    if mc.sharpe_ci_lower > 0.5:
        report.green_flags.append(f"Sharpe 95% CI 하한 {mc.sharpe_ci_lower:.2f} > 0.5")
        green += 1
    elif mc.sharpe_ci_lower < 0:
        report.red_flags.append(f"Sharpe 95% CI 하한 {mc.sharpe_ci_lower:.2f} < 0 (수익 불확실)")
    
    if report.signal_is_significant:
        report.green_flags.append(f"Permutation p-value {p_value:.4f} < 0.05 (유의미)")
        green += 1
    else:
        report.red_flags.append(f"Permutation p-value {p_value:.4f} >= 0.05 (운일 수 있음)")
    
    if report.deflated_sr_is_significant:
        report.green_flags.append(f"Deflated SR {dsr:.3f} > 0.95 (다중검정 통과)")
        green += 1
    
    if green >= 4:
        report.overall_confidence = "VERY_HIGH"
    elif green >= 3:
        report.overall_confidence = "HIGH"
    elif green >= 2:
        report.overall_confidence = "MODERATE"
    else:
        report.overall_confidence = "LOW"
    
    print(f"[VAL] 검증 완료 — 신뢰도: {report.overall_confidence}")
    return report


def print_validation_report(r: ValidationReport):
    """검증 리포트 출력"""
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║           STATISTICAL VALIDATION REPORT                      ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  🔬 WALK-FORWARD OPTIMIZATION                                ║
║  ────────────────────────────                                ║
║  Windows:           {len(r.wf_results):>5d}                  
║  Avg OOS Sharpe:    {r.wf_avg_oos_sharpe:>8.3f}             
║  Robustness Ratio:  {r.wf_robustness_ratio:>8.3f}           
║  Overfit Warning:   {"⚠️ YES" if r.wf_overfit_warning else "✅ NO":>8s}
║                                                              ║
║  🎲 MONTE CARLO ({r.mc_result.n_simulations if r.mc_result else 0} sims)
║  ────────────────────────────                                ║
║  Sharpe 95% CI:     [{r.mc_result.sharpe_ci_lower if r.mc_result else 0:.3f}, {r.mc_result.sharpe_ci_upper if r.mc_result else 0:.3f}]
║  Return 95% CI:     [{r.mc_result.return_ci_lower if r.mc_result else 0:.1f}%, {r.mc_result.return_ci_upper if r.mc_result else 0:.1f}%]
║  P(Return > 0):     {r.mc_result.prob_positive if r.mc_result else 0:.1%}
║  P(Beat SPY):       {r.mc_result.prob_beat_spy if r.mc_result else 0:.1%}
║  MDD 95% CI:        [{r.mc_result.mdd_ci_lower if r.mc_result else 0:.1f}%, {r.mc_result.mdd_ci_upper if r.mc_result else 0:.1f}%]
║                                                              ║
║  📊 SIGNIFICANCE TESTS                                       ║
║  ────────────────────────────                                ║
║  Permutation p-val: {r.permutation_p_value:>8.4f} {"✅" if r.signal_is_significant else "❌"}
║  Deflated SR:       {r.deflated_sharpe:>8.4f} {"✅" if r.deflated_sr_is_significant else "❌"}
║                                                              ║
║  ═══════════════════════════════════════════════              ║
║  OVERALL CONFIDENCE: {r.overall_confidence:>12s}              
║  ═══════════════════════════════════════════════              ║
║                                                              ║
║  ✅ Green Flags:                                              ║""")
    for g in r.green_flags:
        print(f"║     • {g}")
    print("║                                                              ║")
    print("║  🚩 Red Flags:                                                ║")
    for rf in r.red_flags:
        print(f"║     • {rf}")
    print("╚══════════════════════════════════════════════════════════════╝")
