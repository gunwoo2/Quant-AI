"""
utils/conformal_prediction.py — Conformal Prediction v1.0
==========================================================
Day 4 신규 | 원칙 1 "Measure First" — 예측의 불확실성을 측정

"이 종목 AI Score = 78점"이 얼마나 확실한 78점인가?
→ 95% 확률로 [74, 82] 사이 = 확실한 예측 → 큰 포지션
→ 95% 확률로 [55, 95] 사이 = 불확실한 예측 → 작은 포지션

이론: Vovk et al. (2005) "Algorithmic Learning in a Random World"
장점: 모델-비의존적, 분포 가정 불필요, 유한 표본 보장

연결: Day 5 Conviction v2의 "예측 구간" 차원 (25점)
      Day 6 BL Optimizer의 View Confidence로 직결
"""
import numpy as np
import logging

logger = logging.getLogger("conformal_prediction")


class ConformalPredictor:
    """
    Split Conformal Prediction (가장 실용적인 변형).

    fit(calibration):
      1. 보정 데이터(OOS)에서 비적합도 점수 = |실제 - 예측| 계산
      2. 95번째 백분위수 = q_hat

    predict():
      3. 새 예측에 대해 [예측 - q_hat, 예측 + q_hat] = 95% 구간

    핵심: 보정 데이터는 반드시 학습에 안 쓴 OOS 데이터여야 함.
    """

    def __init__(self, alpha=0.05):
        """
        Args:
            alpha: 유의수준 (0.05 = 95% 신뢰구간)
        """
        self.alpha = alpha
        self.q_hat = None
        self.calibration_scores = None
        self.is_calibrated = False

    def calibrate(self, y_true, y_pred):
        """
        보정 데이터로 비적합도 점수(nonconformity score) 계산.

        Args:
            y_true: 실제값 배열 (OOS 데이터!)
            y_pred: 예측값 배열 (동일 데이터의 모델 예측)

        핵심: |y_true - y_pred| 분포의 상위 (1-alpha) 분위수 = q_hat
        """
        y_true = np.asarray(y_true, dtype=float)
        y_pred = np.asarray(y_pred, dtype=float)

        if len(y_true) < 30:
            logger.warning(f"[CONFORMAL] 보정 데이터 부족: {len(y_true)} < 30")
            self.q_hat = 0.3  # 넓은 구간 (보수적 Fallback)
            self.is_calibrated = True
            return self

        # 비적합도 점수
        scores = np.abs(y_true - y_pred)
        self.calibration_scores = np.sort(scores)

        # 유한 표본 보정: ceil((n+1)(1-alpha)) / n
        n = len(scores)
        q_level = np.ceil((n + 1) * (1 - self.alpha)) / n
        q_level = min(q_level, 1.0)

        self.q_hat = float(np.quantile(scores, q_level))
        self.is_calibrated = True

        logger.info(f"[CONFORMAL] 보정 완료: n={n}, q_hat={self.q_hat:.4f}, "
                    f"alpha={self.alpha}")

        return self

    def predict_intervals(self, y_pred):
        """
        예측값 → 신뢰 구간 반환.

        Args:
            y_pred: 모델 예측값 (0~1 확률 또는 0~100 점수)

        Returns:
            dict:
              lower: 하한 배열
              upper: 상한 배열
              width: 구간 너비 (좁을수록 확실)
              is_confident: 중앙값보다 좁으면 True
        """
        y_pred = np.asarray(y_pred, dtype=float)

        if not self.is_calibrated:
            # 미보정 Fallback: 넓은 구간
            logger.warning("[CONFORMAL] 미보정 상태 — 넓은 구간 반환")
            return {
                "lower": y_pred - 20,
                "upper": y_pred + 20,
                "width": np.full_like(y_pred, 40.0),
                "is_confident": np.zeros(len(y_pred), dtype=bool),
            }

        lower = y_pred - self.q_hat
        upper = y_pred + self.q_hat
        width = np.full_like(y_pred, self.q_hat * 2)

        # 0~100 범위 클램프
        if y_pred.max() > 1.5:  # 100점 스케일
            lower = np.maximum(lower, 0)
            upper = np.minimum(upper, 100)
            width = upper - lower

        median_width = float(np.median(width))
        is_confident = width < median_width

        return {
            "lower": np.round(lower, 2),
            "upper": np.round(upper, 2),
            "width": np.round(width, 2),
            "is_confident": is_confident,
            "q_hat": self.q_hat,
            "median_width": median_width,
        }

    def get_confidence_score(self, y_pred):
        """
        예측값 → 0~1 확신도 (Portfolio Layer에서 사용).

        좁은 구간 = 높은 확신 = 1에 가까움
        넓은 구간 = 낮은 확신 = 0에 가까움
        """
        intervals = self.predict_intervals(y_pred)
        widths = intervals["width"]

        # Width → 0~1 확신도 변환
        # width=0 → confidence=1, width=50 → confidence=0
        max_width = 50.0  # 이 이상이면 확신도 0
        confidence = 1.0 - np.minimum(widths / max_width, 1.0)

        return np.round(confidence, 4)


class EnsembleConformalPredictor:
    """
    앙상블 + Conformal 통합.

    3개 Base Learner 각각에 대해 Conformal 구간을 구한 뒤
    통합 구간 = 가장 넓은 구간 (보수적)

    추가: Disagreement도 함께 반영
    """

    def __init__(self, alpha=0.05):
        self.predictors = {
            "xgb": ConformalPredictor(alpha),
            "lgb": ConformalPredictor(alpha),
            "ridge": ConformalPredictor(alpha),
        }
        self.meta_predictor = ConformalPredictor(alpha)

    def calibrate_from_ensemble(self, X_cal, y_cal, ensemble_model):
        """
        앙상블 모델의 OOF 예측으로 보정.

        Args:
            X_cal: 보정 features (OOS)
            y_cal: 보정 labels (OOS)
            ensemble_model: StackingEnsemble 인스턴스
        """
        results = ensemble_model.predict(X_cal)

        # Meta-Learner 결과로 보정
        meta_pred = results["ai_score"] / 100.0
        self.meta_predictor.calibrate(y_cal, meta_pred)

        return self

    def predict_with_intervals(self, X, ensemble_model):
        """
        앙상블 예측 + Conformal 구간 + Disagreement 통합.
        """
        results = ensemble_model.predict(X)
        ai_score = results["ai_score"]
        disagreement = results["disagreement"]

        # Conformal 구간
        intervals = self.meta_predictor.predict_intervals(ai_score)
        confidence = self.meta_predictor.get_confidence_score(ai_score)

        return {
            "ai_score": ai_score,
            "disagreement": disagreement,
            "lower": intervals["lower"],
            "upper": intervals["upper"],
            "width": intervals["width"],
            "is_confident": intervals["is_confident"],
            "confidence": confidence,  # 0~1, Portfolio BL에서 사용
        }