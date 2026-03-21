"""
risk/portfolio_risk_monitor.py — 일일 포트폴리오 리스크 모니터
================================================================
매일 VaR/CVaR/Beta/Stress Test를 계산하여 DB에 저장하고,
임계값 초과 시 알림을 발생시킵니다.

risk_model.py (V2)의 기능을 배치 파이프라인에 연동하는 어댑터.
"""
import numpy as np
import pandas as pd
from datetime import date
from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class DailyRiskReport:
    """일일 리스크 리포트"""
    calc_date: date = None
    # VaR
    var_95_pct: float = 0.0
    var_99_pct: float = 0.0
    cvar_95_pct: float = 0.0
    cornish_fisher_99_pct: float = 0.0
    var_95_dollar: float = 0.0
    var_99_dollar: float = 0.0
    # 베타/변동성
    portfolio_beta: float = 0.0
    portfolio_vol_annual: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    # 집중도
    herfindahl_index: float = 0.0
    sector_herfindahl: float = 0.0
    max_sector_pct: float = 0.0
    avg_correlation: float = 0.0
    max_correlation: float = 0.0
    # 컨텍스트
    regime: str = "NEUTRAL"
    dd_mode: str = "NORMAL"
    # 스트레스 테스트
    stress_2008: float = 0.0
    stress_2020: float = 0.0
    stress_vix40: float = 0.0
    # 경고
    alerts: List[str] = None

    def __post_init__(self):
        if self.alerts is None:
            self.alerts = []


class PortfolioRiskMonitor:
    """
    일일 포트폴리오 리스크 계산 + DB 저장.

    사용법:
        monitor = PortfolioRiskMonitor()
        report = monitor.calculate(
            today, positions, price_history, spy_returns, total_value
        )
        monitor.save_to_db(report)
        if report.alerts:
            notify(report.alerts)
    """

    # 리스크 임계값
    ALERT_THRESHOLDS = {
        "var_95_pct": -0.025,       # VaR(95%) > -2.5%이면 경고
        "max_sector_pct": 0.35,     # 섹터 35% 초과
        "avg_correlation": 0.65,    # 평균 상관 0.65 초과
        "portfolio_beta": 1.5,      # 베타 1.5 초과
        "portfolio_vol_annual": 0.30,  # 연 변동성 30% 초과
    }

    def calculate(
        self,
        calc_date: date,
        positions: Dict[str, dict],
        price_history: pd.DataFrame,
        spy_returns: pd.Series,
        total_value: float,
        regime: str = "NEUTRAL",
        dd_mode: str = "NORMAL",
    ) -> DailyRiskReport:
        """
        일일 리스크 지표 계산.

        Parameters
        ----------
        positions : dict     {ticker: {shares, current_price, sector, ...}}
        price_history : df   columns=tickers, index=dates, values=close prices
        spy_returns : Series SPY 일일 수익률
        total_value : float  총 포폴 가치
        """
        report = DailyRiskReport(calc_date=calc_date, regime=regime, dd_mode=dd_mode)

        if not positions or price_history.empty:
            return report

        # ── 수익률 매트릭스 ──
        returns = price_history.pct_change().dropna()
        tickers = [t for t in positions if t in returns.columns]
        if not tickers:
            return report

        ret_matrix = returns[tickers]
        weights = self._calc_weights(positions, tickers, total_value)

        # ── 포트폴리오 수익률 ──
        port_returns = (ret_matrix * weights).sum(axis=1)

        # ── VaR / CVaR ──
        report.var_95_pct = float(np.percentile(port_returns, 5))
        report.var_99_pct = float(np.percentile(port_returns, 1))
        report.var_95_dollar = round(report.var_95_pct * total_value, 2)
        report.var_99_dollar = round(report.var_99_pct * total_value, 2)

        # CVaR (Expected Shortfall)
        tail_5 = port_returns[port_returns <= report.var_95_pct]
        report.cvar_95_pct = float(tail_5.mean()) if len(tail_5) > 0 else report.var_95_pct

        # Cornish-Fisher VaR (왜도/첨도 보정)
        report.cornish_fisher_99_pct = self._cornish_fisher_var(port_returns, 0.01)

        # ── Beta ──
        if len(spy_returns) > 30 and len(port_returns) > 30:
            common = port_returns.index.intersection(spy_returns.index)
            if len(common) > 30:
                pr = port_returns.loc[common]
                sr = spy_returns.loc[common]
                cov_ps = np.cov(pr, sr)[0, 1]
                var_s = np.var(sr)
                report.portfolio_beta = round(cov_ps / var_s, 3) if var_s > 0 else 0

        # ── 변동성 ──
        report.portfolio_vol_annual = round(float(port_returns.std() * np.sqrt(252)), 4)

        # ── 샤프/소르티노 ──
        mean_ret = float(port_returns.mean()) * 252
        std_ret = float(port_returns.std()) * np.sqrt(252)
        if std_ret > 0:
            report.sharpe_ratio = round(mean_ret / std_ret, 3)

        downside = port_returns[port_returns < 0]
        downside_std = float(downside.std() * np.sqrt(252)) if len(downside) > 0 else 0
        if downside_std > 0:
            report.sortino_ratio = round(mean_ret / downside_std, 3)

        # ── 집중도 ──
        w_arr = np.array(list(weights.values()))
        report.herfindahl_index = round(float(np.sum(w_arr ** 2)), 4)

        sector_weights = {}
        for t in tickers:
            sec = positions[t].get("sector", "Unknown")
            sector_weights[sec] = sector_weights.get(sec, 0) + weights.get(t, 0)
        sw = np.array(list(sector_weights.values()))
        report.sector_herfindahl = round(float(np.sum(sw ** 2)), 4)
        report.max_sector_pct = round(float(sw.max()), 4) if len(sw) > 0 else 0

        # ── 상관관계 ──
        if len(tickers) >= 2 and len(ret_matrix) > 20:
            corr_matrix = ret_matrix.corr()
            mask = np.triu(np.ones(corr_matrix.shape), k=1).astype(bool)
            upper = corr_matrix.where(mask)
            report.avg_correlation = round(float(upper.stack().mean()), 3)
            report.max_correlation = round(float(upper.stack().max()), 3)

        # ── 스트레스 테스트 (간이) ──
        if report.portfolio_beta != 0:
            report.stress_2008 = round(-0.568 * abs(report.portfolio_beta), 4)
            report.stress_2020 = round(-0.339 * abs(report.portfolio_beta), 4)
            report.stress_vix40 = round(-0.15 * abs(report.portfolio_beta) * (1 + report.portfolio_vol_annual), 4)

        # ── 경고 생성 ──
        report.alerts = self._check_alerts(report)

        return report

    def _calc_weights(self, positions: dict, tickers: list, total_value: float) -> dict:
        """포지션 비중 계산"""
        weights = {}
        for t in tickers:
            pos = positions[t]
            val = pos.get("shares", 0) * pos.get("current_price", 0)
            weights[t] = val / total_value if total_value > 0 else 0
        return weights

    def _cornish_fisher_var(self, returns: pd.Series, alpha: float = 0.01) -> float:
        """Cornish-Fisher VaR (왜도/첨도 보정)"""
        z = float(np.percentile(np.random.standard_normal(10000), alpha * 100))
        s = float(returns.skew()) if len(returns) > 3 else 0
        k = float(returns.kurtosis()) if len(returns) > 3 else 0

        z_cf = z + (z**2 - 1) * s / 6 + (z**3 - 3*z) * k / 24 - (2*z**3 - 5*z) * s**2 / 36
        mu = float(returns.mean())
        sigma = float(returns.std())
        return round(mu + z_cf * sigma, 6)

    def _check_alerts(self, report: DailyRiskReport) -> List[str]:
        """임계값 초과 경고 생성"""
        alerts = []
        t = self.ALERT_THRESHOLDS

        if report.var_95_pct < t["var_95_pct"]:
            alerts.append(f"VaR(95%) {report.var_95_pct:.2%} < {t['var_95_pct']:.2%}")
        if report.max_sector_pct > t["max_sector_pct"]:
            alerts.append(f"섹터집중 {report.max_sector_pct:.1%} > {t['max_sector_pct']:.0%}")
        if report.avg_correlation > t["avg_correlation"]:
            alerts.append(f"상관관계 {report.avg_correlation:.2f} > {t['avg_correlation']:.2f}")
        if abs(report.portfolio_beta) > t["portfolio_beta"]:
            alerts.append(f"Beta {report.portfolio_beta:.2f} > {t['portfolio_beta']:.1f}")
        if report.portfolio_vol_annual > t["portfolio_vol_annual"]:
            alerts.append(f"변동성 {report.portfolio_vol_annual:.1%} > {t['portfolio_vol_annual']:.0%}")

        return alerts

    def save_to_db(self, report: DailyRiskReport):
        """portfolio_risk_daily 테이블에 저장"""
        from db_pool import get_cursor

        with get_cursor() as cur:
            cur.execute("""
                INSERT INTO portfolio_risk_daily
                    (calc_date, var_95_pct, var_99_pct, cvar_95_pct, cornish_fisher_99_pct,
                     var_95_dollar, var_99_dollar, portfolio_beta, portfolio_vol_annual,
                     sharpe_ratio, sortino_ratio, calmar_ratio,
                     herfindahl_index, sector_herfindahl, max_sector_pct,
                     avg_correlation, max_correlation, regime, dd_mode)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (calc_date) DO UPDATE SET
                    var_95_pct = EXCLUDED.var_95_pct,
                    var_99_pct = EXCLUDED.var_99_pct,
                    cvar_95_pct = EXCLUDED.cvar_95_pct,
                    cornish_fisher_99_pct = EXCLUDED.cornish_fisher_99_pct,
                    var_95_dollar = EXCLUDED.var_95_dollar,
                    var_99_dollar = EXCLUDED.var_99_dollar,
                    portfolio_beta = EXCLUDED.portfolio_beta,
                    portfolio_vol_annual = EXCLUDED.portfolio_vol_annual,
                    sharpe_ratio = EXCLUDED.sharpe_ratio,
                    sortino_ratio = EXCLUDED.sortino_ratio,
                    calmar_ratio = EXCLUDED.calmar_ratio,
                    herfindahl_index = EXCLUDED.herfindahl_index,
                    sector_herfindahl = EXCLUDED.sector_herfindahl,
                    max_sector_pct = EXCLUDED.max_sector_pct,
                    avg_correlation = EXCLUDED.avg_correlation,
                    max_correlation = EXCLUDED.max_correlation,
                    regime = EXCLUDED.regime,
                    dd_mode = EXCLUDED.dd_mode
            """, (
                report.calc_date,
                report.var_95_pct, report.var_99_pct,
                report.cvar_95_pct, report.cornish_fisher_99_pct,
                report.var_95_dollar, report.var_99_dollar,
                report.portfolio_beta, report.portfolio_vol_annual,
                report.sharpe_ratio, report.sortino_ratio, report.calmar_ratio,
                report.herfindahl_index, report.sector_herfindahl, report.max_sector_pct,
                report.avg_correlation, report.max_correlation,
                report.regime, report.dd_mode,
            ))

        print(f"  ✅ 리스크 메트릭 DB 저장 (VaR95={report.var_95_pct:.2%}, Beta={report.portfolio_beta:.2f})")
