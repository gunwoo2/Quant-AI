"""
alpha_model.py — Institutional Grade Alpha Model
═══════════════════════════════════════════════════════════
기존 고정 가중치(50/25/25) 대체:
  1. Fama-MacBeth Cross-Sectional Regression (동적 팩터 가중치)
  2. IC / ICIR 모니터링 (팩터 유효성 실시간 추적)
  3. Regime-Conditional Weights (국면별 가중치)
  4. Sector-Specific Weights (섹터별 가중치)
  5. Sigmoid Score Transform (Cliff Effect 제거)
  6. Interaction Terms (Value Trap 감지 등)
  7. Alpha Decay (시그널 감쇠 모델)

참조: AQR "Value and Momentum Everywhere" (2013)
      Barra Risk Model, Axioma Factor Model
"""
import numpy as np
import pandas as pd
from scipy.special import expit as sigmoid  # 1/(1+e^-x)
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import date, timedelta
import warnings
warnings.filterwarnings("ignore")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 상수 & Prior
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 기본 Prior 가중치 (현행 시스템과 동일, Bayesian Shrinkage 대상)
PRIOR_LAYER_WEIGHTS = {"L1": 0.50, "L2": 0.25, "L3": 0.25}

PRIOR_FACTOR_WEIGHTS = {
    "MOAT": 0.35, "VALUE": 0.25, "MOMENTUM": 0.25, "STABILITY": 0.15,
}

# 섹터별 Prior 가중치 (도메인 지식 기반)
SECTOR_FACTOR_PRIORS = {
    "Technology":           {"MOAT": 0.40, "VALUE": 0.15, "MOMENTUM": 0.30, "STABILITY": 0.15},
    "Healthcare":           {"MOAT": 0.35, "VALUE": 0.20, "MOMENTUM": 0.25, "STABILITY": 0.20},
    "Financials":           {"MOAT": 0.25, "VALUE": 0.30, "MOMENTUM": 0.20, "STABILITY": 0.25},
    "Consumer Discretionary": {"MOAT": 0.30, "VALUE": 0.25, "MOMENTUM": 0.30, "STABILITY": 0.15},
    "Consumer Staples":     {"MOAT": 0.25, "VALUE": 0.25, "MOMENTUM": 0.20, "STABILITY": 0.30},
    "Industrials":          {"MOAT": 0.30, "VALUE": 0.25, "MOMENTUM": 0.25, "STABILITY": 0.20},
    "Energy":               {"MOAT": 0.20, "VALUE": 0.35, "MOMENTUM": 0.30, "STABILITY": 0.15},
    "Utilities":            {"MOAT": 0.20, "VALUE": 0.25, "MOMENTUM": 0.15, "STABILITY": 0.40},
    "Materials":            {"MOAT": 0.25, "VALUE": 0.30, "MOMENTUM": 0.30, "STABILITY": 0.15},
    "Real Estate":          {"MOAT": 0.25, "VALUE": 0.30, "MOMENTUM": 0.20, "STABILITY": 0.25},
    "Communication Services": {"MOAT": 0.35, "VALUE": 0.20, "MOMENTUM": 0.30, "STABILITY": 0.15},
}

# 시그널 Half-Life (Alpha Decay용, 일 단위)
SIGNAL_HALFLIFE = {
    "MOMENTUM": 5,    # 기술적 모멘텀: 빠르게 소멸
    "SENTIMENT": 3,   # 뉴스 감성: 매우 빠르게 반영
    "VALUE": 60,      # 밸류에이션: 느리게 실현
    "QUALITY": 90,    # 품질(MOAT): 가장 느리게
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 데이터 구조
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class FactorIC:
    """팩터 Information Coefficient 기록"""
    factor_name: str
    ic_values: List[float] = field(default_factory=list)   # 월별 IC 리스트
    dates: List[date] = field(default_factory=list)

    @property
    def mean_ic(self) -> float:
        return float(np.mean(self.ic_values)) if self.ic_values else 0.0

    @property
    def icir(self) -> float:
        """IC Information Ratio = Mean(IC) / Std(IC)"""
        if len(self.ic_values) < 3:
            return 0.0
        std = float(np.std(self.ic_values))
        return float(np.mean(self.ic_values)) / std if std > 0 else 0.0

    @property
    def is_effective(self) -> bool:
        """팩터가 유효한지 (IC > 0.03 AND ICIR > 0.2)"""
        return self.mean_ic > 0.03 and self.icir > 0.2

    @property
    def recent_ic(self) -> float:
        """최근 3개월 평균 IC"""
        recent = self.ic_values[-3:] if len(self.ic_values) >= 3 else self.ic_values
        return float(np.mean(recent)) if recent else 0.0


@dataclass
class DynamicWeights:
    """동적 가중치 결과"""
    layer_weights: Dict[str, float]       # L1, L2, L3 → weight
    factor_weights: Dict[str, float]      # MOAT, VALUE, ... → weight (L1 내)
    regime: str
    sector: str
    shrinkage_factor: float               # 현재 shrinkage 정도
    ic_scores: Dict[str, float]           # 각 팩터 현재 IC
    method: str                           # "PRIOR" | "REGRESSION" | "BLENDED"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AlphaModel 메인 클래스
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class AlphaModel:
    """
    Institutional-Grade Alpha Model

    Usage:
        model = AlphaModel()
        model.update_ic(factor_scores_df, forward_returns_series, calc_date)
        model.fit_weights(factor_scores_df, forward_returns_series, regime)
        weights = model.get_weights(regime="BULL", sector="Technology")
        score = model.compute_alpha_score(factor_dict, regime, sector, signal_age_days)
    """

    def __init__(self, min_months_for_regression: int = 6):
        self.min_months = min_months_for_regression
        self.ic_history: Dict[str, FactorIC] = {}
        self.fitted_weights: Dict[str, Dict[str, float]] = {}  # regime → factor → weight
        self.last_fit_date: Optional[date] = None
        self._months_data = 0

    # ────────────────────────────────────────────
    # 1. Sigmoid Score Transform
    # ────────────────────────────────────────────

    @staticmethod
    def sigmoid_score(percentile: float, max_points: float,
                      steepness: float = 15.0) -> float:
        """
        백분위 → 점수 변환 (Sigmoid, 연속 함수)

        기존: 계단함수 (70pct→80%, 69pct→60%)
        개선: S-curve (70pct→76.4%, 69pct→75.3%)

        Parameters
        ----------
        percentile : float   0~100 백분위
        max_points : float   최대 점수 (예: 30)
        steepness : float    S-curve 기울기 (높을수록 급격)
        """
        if percentile is None:
            return 0.0
        # 정규화: 50을 중심으로 -1 ~ +1 범위
        x = (percentile - 50.0) / steepness
        return round(float(max_points * sigmoid(x)), 2)

    # ────────────────────────────────────────────
    # 2. IC (Information Coefficient) 계산
    # ────────────────────────────────────────────

    def compute_ic(
        self,
        factor_scores: pd.Series,
        forward_returns: pd.Series,
    ) -> float:
        """
        Rank IC = Spearman Correlation(Factor Score, Forward Return)

        Parameters
        ----------
        factor_scores : Series (index=ticker, value=factor_score)
        forward_returns : Series (index=ticker, value=next_period_return)
        """
        # 교집합만
        common = factor_scores.dropna().index.intersection(forward_returns.dropna().index)
        if len(common) < 30:
            return 0.0

        from scipy.stats import spearmanr
        ic, pval = spearmanr(
            factor_scores.loc[common].values,
            forward_returns.loc[common].values,
        )
        return float(ic) if not np.isnan(ic) else 0.0

    def update_ic(
        self,
        factor_scores_df: pd.DataFrame,
        forward_returns: pd.Series,
        calc_date: date,
    ):
        """
        각 팩터의 IC를 업데이트

        Parameters
        ----------
        factor_scores_df : DataFrame
            columns = [MOAT, VALUE, MOMENTUM, STABILITY, SENTIMENT, TECHNICAL]
            index = ticker
        forward_returns : Series
            index = ticker, value = next 21-day return
        """
        for factor in factor_scores_df.columns:
            ic = self.compute_ic(factor_scores_df[factor], forward_returns)

            if factor not in self.ic_history:
                self.ic_history[factor] = FactorIC(factor_name=factor)

            self.ic_history[factor].ic_values.append(ic)
            self.ic_history[factor].dates.append(calc_date)

            # 최근 36개월만 유지
            if len(self.ic_history[factor].ic_values) > 36:
                self.ic_history[factor].ic_values = self.ic_history[factor].ic_values[-36:]
                self.ic_history[factor].dates = self.ic_history[factor].dates[-36:]

        self._months_data += 1

    # ────────────────────────────────────────────
    # 3. Fama-MacBeth Regression → Dynamic Weights
    # ────────────────────────────────────────────

    def fit_weights(
        self,
        historical_data: List[Tuple[pd.DataFrame, pd.Series]],
        regime: str = "ALL",
        ridge_alpha: float = 0.1,
    ):
        """
        Rolling Ridge Regression으로 팩터 가중치 추정

        Parameters
        ----------
        historical_data : list of (factor_scores_df, forward_returns_series)
            각 원소 = 한 달의 cross-section 데이터
        regime : str
            "ALL" | "BULL" | "NEUTRAL" | "BEAR" | "CRISIS"
        """
        if len(historical_data) < self.min_months:
            return  # 데이터 부족 → Prior 사용

        # 모든 월의 데이터 합치기
        all_X = []
        all_y = []
        for scores_df, returns_s in historical_data:
            common = scores_df.dropna().index.intersection(returns_s.dropna().index)
            if len(common) < 20:
                continue
            X = scores_df.loc[common].values
            y = returns_s.loc[common].values
            all_X.append(X)
            all_y.append(y)

        if len(all_X) < self.min_months:
            return

        X = np.vstack(all_X)
        y = np.concatenate(all_y)

        # Z-score 정규화
        X_mean = X.mean(axis=0)
        X_std = X.std(axis=0)
        X_std[X_std == 0] = 1
        X_norm = (X - X_mean) / X_std

        # Ridge Regression
        from numpy.linalg import inv
        n_factors = X_norm.shape[1]
        I = np.eye(n_factors)
        beta = inv(X_norm.T @ X_norm + ridge_alpha * I) @ X_norm.T @ y

        # Softmax → 가중치 (양수 보장 + 합=1)
        exp_beta = np.exp(np.clip(beta, -5, 5))
        data_weights = exp_beta / exp_beta.sum()

        # Bayesian Shrinkage: Prior와 블렌딩
        shrinkage = self._get_shrinkage_factor()
        factor_names = list(PRIOR_FACTOR_WEIGHTS.keys())[:n_factors]
        prior_w = np.array([PRIOR_FACTOR_WEIGHTS.get(f, 0.25) for f in factor_names])
        prior_w = prior_w / prior_w.sum()

        blended = shrinkage * prior_w + (1 - shrinkage) * data_weights
        blended = blended / blended.sum()

        # IC 기반 감쇠: IC < 0인 팩터 가중치 축소
        for i, fname in enumerate(factor_names):
            if fname in self.ic_history:
                recent_ic = self.ic_history[fname].recent_ic
                if recent_ic < -0.03:
                    blended[i] *= 0.1  # 역효과 팩터 → 거의 0
                elif recent_ic < 0:
                    blended[i] *= 0.5  # 무효 팩터 → 반감

        blended = blended / blended.sum()

        self.fitted_weights[regime] = {
            fname: round(float(w), 4) for fname, w in zip(factor_names, blended)
        }
        self.last_fit_date = date.today()

    def _get_shrinkage_factor(self) -> float:
        """데이터 양에 따른 shrinkage (Prior 의존도)"""
        # 24개월 데이터 축적 시 0.3까지 감소
        return max(0.3, 1.0 - self._months_data / 24.0)

    # ────────────────────────────────────────────
    # 4. 가중치 조회
    # ────────────────────────────────────────────

    def get_weights(
        self, regime: str = "BULL", sector: str = "Technology",
    ) -> DynamicWeights:
        """
        현재 최적 가중치 반환

        우선순위: fitted > sector_prior > global_prior
        """
        # Factor weights (L1 내부)
        if regime in self.fitted_weights:
            factor_w = self.fitted_weights[regime]
            method = "REGRESSION"
        elif sector in SECTOR_FACTOR_PRIORS:
            factor_w = SECTOR_FACTOR_PRIORS[sector]
            method = "SECTOR_PRIOR"
        else:
            factor_w = PRIOR_FACTOR_WEIGHTS.copy()
            method = "GLOBAL_PRIOR"

        # Layer weights — 국면별 동적 조정
        layer_w = self._get_regime_layer_weights(regime)

        # IC 점수
        ic_scores = {
            f: round(self.ic_history[f].recent_ic, 4)
            for f in self.ic_history
        }

        return DynamicWeights(
            layer_weights=layer_w,
            factor_weights=factor_w,
            regime=regime,
            sector=sector,
            shrinkage_factor=round(self._get_shrinkage_factor(), 3),
            ic_scores=ic_scores,
            method=method,
        )

    def _get_regime_layer_weights(self, regime: str) -> Dict[str, float]:
        """국면별 Layer 가중치 (L1/L2/L3)"""
        # BEAR/CRISIS: 펀더멘털(L1) 비중↑, 기술적(L3)↓
        # BULL: 기술적(L3)/감성(L2) 비중↑
        regimes = {
            "BULL":    {"L1": 0.45, "L2": 0.28, "L3": 0.27},
            "NEUTRAL": {"L1": 0.50, "L2": 0.25, "L3": 0.25},
            "BEAR":    {"L1": 0.60, "L2": 0.22, "L3": 0.18},
            "CRISIS":  {"L1": 0.65, "L2": 0.20, "L3": 0.15},
        }
        return regimes.get(regime, PRIOR_LAYER_WEIGHTS.copy())

    # ────────────────────────────────────────────
    # 5. Interaction Terms (Value Trap 등)
    # ────────────────────────────────────────────

    @staticmethod
    def compute_interaction_adjustment(
        moat: float, value: float, momentum: float,
        stability: float, sentiment: float, rsi: float,
        regime: str,
    ) -> float:
        """
        팩터 상호작용 보정값 계산

        Returns
        -------
        float : 보정 점수 (-20 ~ +15 범위)
        """
        adjustment = 0.0

        # Value Trap: 싸지만 모멘텀 없음
        if value > 70 and momentum < 30:
            adjustment -= 15.0

        # Quality at Reasonable Price (QARP)
        if moat > 60 and value > 50:
            adjustment += 10.0

        # Momentum Crash 경고: 과열 + 중립/약세 국면
        if momentum > 80 and rsi > 75 and regime in ("NEUTRAL", "BEAR"):
            adjustment -= 10.0

        # Distress Signal: 복합 위험
        if stability < 20 and sentiment < 30:
            adjustment -= 20.0

        # Quality Momentum: 좋은 기업 + 강한 모멘텀
        if moat > 65 and momentum > 65:
            adjustment += 8.0

        # Contrarian Value: 약세장에서 가치주 보너스
        if regime == "BEAR" and value > 70 and stability > 50:
            adjustment += 7.0

        # Sentiment Divergence: 감성 ↑ but 펀더멘털 ↓
        if sentiment > 70 and moat < 35:
            adjustment -= 8.0  # 과대 평가 경고

        return round(np.clip(adjustment, -25, 20), 2)

    # ────────────────────────────────────────────
    # 6. Alpha Decay
    # ────────────────────────────────────────────

    @staticmethod
    def apply_alpha_decay(
        base_score: float,
        signal_age_days: int,
        signal_type: str = "QUALITY",
    ) -> float:
        """
        시그널 감쇠 적용

        α(t) = α₀ × exp(-t × ln(2) / τ)

        Parameters
        ----------
        base_score : float      원래 점수
        signal_age_days : int   시그널 발생 후 경과 일수
        signal_type : str       시그널 유형 → half-life 결정
        """
        tau = SIGNAL_HALFLIFE.get(signal_type, 30)
        decay = np.exp(-signal_age_days * np.log(2) / tau)
        return round(float(base_score * decay), 2)

    # ────────────────────────────────────────────
    # 7. 최종 Alpha Score 계산
    # ────────────────────────────────────────────

    def compute_alpha_score(
        self,
        factor_scores: Dict[str, float],
        regime: str,
        sector: str,
        rsi: float = 50.0,
        signal_age_days: int = 0,
    ) -> Tuple[float, Dict]:
        """
        최종 알파 점수 계산 (0~100)

        Parameters
        ----------
        factor_scores : dict
            {"MOAT": 72, "VALUE": 58, "MOMENTUM": 65, "STABILITY": 80,
             "SENTIMENT": 55, "TECHNICAL": 62}
        regime : str
        sector : str
        rsi : float
        signal_age_days : int

        Returns
        -------
        (final_score, detail_dict)
        """
        weights = self.get_weights(regime, sector)

        # L1 팩터 가중 합산
        l1_factors = ["MOAT", "VALUE", "MOMENTUM", "STABILITY"]
        l1_score = sum(
            factor_scores.get(f, 50) * weights.factor_weights.get(f, 0.25)
            for f in l1_factors
        )

        l2_score = factor_scores.get("SENTIMENT", 50)
        l3_score = factor_scores.get("TECHNICAL", 50)

        # Layer 가중 합산
        lw = weights.layer_weights
        raw_score = l1_score * lw["L1"] + l2_score * lw["L2"] + l3_score * lw["L3"]

        # Interaction adjustment
        interaction = self.compute_interaction_adjustment(
            moat=factor_scores.get("MOAT", 50),
            value=factor_scores.get("VALUE", 50),
            momentum=factor_scores.get("MOMENTUM", 50),
            stability=factor_scores.get("STABILITY", 50),
            sentiment=factor_scores.get("SENTIMENT", 50),
            rsi=rsi,
            regime=regime,
        )

        adjusted = raw_score + interaction

        # Alpha Decay (혼합 half-life)
        if signal_age_days > 0:
            # 각 팩터별 decay 적용 후 재합산 (정밀한 방식)
            decayed_l1 = sum(
                self.apply_alpha_decay(
                    factor_scores.get(f, 50) * weights.factor_weights.get(f, 0.25),
                    signal_age_days,
                    "QUALITY" if f == "MOAT" else f,
                )
                for f in l1_factors
            )
            decayed_l2 = self.apply_alpha_decay(l2_score, signal_age_days, "SENTIMENT")
            decayed_l3 = self.apply_alpha_decay(l3_score, signal_age_days, "MOMENTUM")

            adjusted = (decayed_l1 * lw["L1"] + decayed_l2 * lw["L2"]
                       + decayed_l3 * lw["L3"] + interaction)

        final = round(float(np.clip(adjusted, 0, 100)), 2)

        detail = {
            "l1_score": round(l1_score, 2),
            "l2_score": round(l2_score, 2),
            "l3_score": round(l3_score, 2),
            "raw_weighted": round(raw_score, 2),
            "interaction_adj": interaction,
            "final_score": final,
            "weights_method": weights.method,
            "shrinkage": weights.shrinkage_factor,
            "layer_weights": weights.layer_weights,
            "factor_weights": weights.factor_weights,
            "regime": regime,
            "sector": sector,
        }

        return final, detail
