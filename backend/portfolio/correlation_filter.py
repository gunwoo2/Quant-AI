"""
portfolio/correlation_filter.py — 상관관계 기반 분산 필터
==========================================================
1. 진입 필터: 신규 매수 전 기존 보유종목과 상관 체크
2. 모니터링:  포폴 내 상관 급등 감지 → 약한 종목 매도 권고
3. 목표:      포폴 평균 상관 < 0.50 유지
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class CorrelationCheckResult:
    """상관관계 체크 결과"""
    passed: bool = True
    avg_correlation: float = 0.0
    max_correlation: float = 0.0
    max_corr_pair: Tuple[str, str] = ("", "")
    blocking_tickers: List[str] = None       # 상관 높은 기존 보유종목
    suggested_removes: List[str] = None      # 포폴에서 제거 추천

    def __post_init__(self):
        if self.blocking_tickers is None:
            self.blocking_tickers = []
        if self.suggested_removes is None:
            self.suggested_removes = []


class CorrelationFilter:
    """
    상관관계 기반 포트폴리오 분산 관리.

    사용법:
        cf = CorrelationFilter(threshold=0.75)

        # 진입 필터
        result = cf.check_entry("NVDA", existing_tickers, price_history)
        if not result.passed:
            skip NVDA

        # 포폴 모니터링
        monitor = cf.monitor_portfolio(positions, price_history)
        if monitor.avg_correlation > 0.70:
            sell monitor.suggested_removes
    """

    def __init__(self, threshold: float = 0.75, target_avg: float = 0.50, lookback: int = 60):
        self.threshold = threshold
        self.target_avg = target_avg
        self.lookback = lookback

    def build_correlation_matrix(
        self, tickers: List[str], price_history: pd.DataFrame
    ) -> pd.DataFrame:
        """종가 기반 상관행렬 계산"""
        available = [t for t in tickers if t in price_history.columns]
        if len(available) < 2:
            return pd.DataFrame()

        prices = price_history[available].tail(self.lookback)
        returns = prices.pct_change().dropna()

        if len(returns) < 20:
            return pd.DataFrame()

        return returns.corr()

    def check_entry(
        self,
        new_ticker: str,
        existing_tickers: List[str],
        price_history: pd.DataFrame,
    ) -> CorrelationCheckResult:
        """
        신규 종목 진입 전 상관관계 체크.
        기존 보유종목과 상관이 threshold 이상이면 차단.
        """
        result = CorrelationCheckResult()

        all_tickers = existing_tickers + [new_ticker]
        corr_matrix = self.build_correlation_matrix(all_tickers, price_history)

        if corr_matrix.empty or new_ticker not in corr_matrix.columns:
            result.passed = True
            return result

        # 신규 종목과 기존 종목 간 상관
        new_corrs = corr_matrix[new_ticker].drop(new_ticker, errors="ignore")

        high_corr = new_corrs[new_corrs.abs() > self.threshold]

        if not high_corr.empty:
            result.passed = False
            result.blocking_tickers = list(high_corr.index)
            result.max_correlation = float(high_corr.abs().max())
            max_ticker = high_corr.abs().idxmax()
            result.max_corr_pair = (new_ticker, max_ticker)
            return result

        result.avg_correlation = float(new_corrs.abs().mean())
        result.passed = True
        return result

    def monitor_portfolio(
        self,
        tickers: List[str],
        price_history: pd.DataFrame,
        scores: Optional[Dict[str, float]] = None,
    ) -> CorrelationCheckResult:
        """
        포폴 내 상관관계 모니터링.
        평균 상관이 높으면 가장 약한(점수 낮은) 종목 제거 추천.
        """
        result = CorrelationCheckResult()
        corr_matrix = self.build_correlation_matrix(tickers, price_history)

        if corr_matrix.empty:
            return result

        # 상삼각만 추출
        mask = np.triu(np.ones(corr_matrix.shape), k=1).astype(bool)
        upper = corr_matrix.where(mask)
        all_corrs = upper.stack()

        if all_corrs.empty:
            return result

        result.avg_correlation = float(all_corrs.abs().mean())
        result.max_correlation = float(all_corrs.abs().max())

        # max correlation pair
        max_idx = all_corrs.abs().idxmax()
        result.max_corr_pair = max_idx

        # 상관 높은 쌍에서 약한 종목 제거 추천
        if result.avg_correlation > 0.70 and scores:
            high_pairs = all_corrs[all_corrs.abs() > self.threshold]
            remove_candidates = set()
            for (t1, t2), corr_val in high_pairs.items():
                s1 = scores.get(t1, 50)
                s2 = scores.get(t2, 50)
                weaker = t2 if s1 >= s2 else t1
                remove_candidates.add(weaker)

            result.suggested_removes = sorted(
                remove_candidates, key=lambda t: scores.get(t, 0)
            )[:3]  # 최대 3개

        result.passed = result.avg_correlation <= self.target_avg
        return result

    def filter_candidates(
        self,
        candidates: List[dict],
        existing_tickers: List[str],
        price_history: pd.DataFrame,
    ) -> List[dict]:
        """
        매수 후보 리스트에서 상관 높은 종목 제거.
        점수 높은 순으로 하나씩 추가, 추가할 때마다 상관 체크.
        """
        accepted = []
        current = list(existing_tickers)

        for c in candidates:
            ticker = c["ticker"]
            if ticker in current:
                accepted.append(c)
                continue

            check = self.check_entry(ticker, current, price_history)
            if check.passed:
                accepted.append(c)
                current.append(ticker)
            # else: skip (상관 높아서 제외)

        return accepted
