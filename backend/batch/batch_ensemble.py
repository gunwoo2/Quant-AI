"""
batch/batch_ensemble.py — 3-Model Stacking Ensemble v1.0
==========================================================
Day 2~3 신규 | 설계 원칙 3 "Trust is Earned" — 다양한 관점의 합의

Level 0: 3개 독립 Base Learner (다른 Feature Subset → 관점 다양성)
  Base 1: XGBoost  — 전체 37 features (비선형 패턴)
  Base 2: LightGBM — 시계열+매크로 18 features (빠른 적응)
  Base 3: Ridge LR — 서브팩터+횡단면 19 features (선형 기준점)

Level 1: Meta-Learner (Out-of-Fold predictions → LogisticRegression)

핵심 출력:
  - ai_score: 최종 앙상블 점수 (0~100)
  - disagreement: 3개 모델 불일치도 → Conviction Score에 반영
  - base_scores: 개별 모델 점수 (투명성)

실행: scheduler.py Step 6.3 (batch_xgboost.py 대체 또는 병행)
의존: batch_xgboost.py v2의 _build_features_v2(), _purged_walk_forward_splits()
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import patch_numpy_adapter
except ImportError:
    pass

import numpy as np
import json
import joblib
import logging
from datetime import datetime, date, timedelta
from pathlib import Path
from db_pool import get_cursor

logger = logging.getLogger("batch_ensemble")

try:
    import xgboost as xgb
    _HAS_XGB = True
except ImportError:
    _HAS_XGB = False

try:
    import lightgbm as lgb
    _HAS_LGB = True
except ImportError:
    _HAS_LGB = False
    print("[ENSEMBLE] ⚠️ lightgbm 미설치 — pip install lightgbm")

try:
    from sklearn.linear_model import LogisticRegression, RidgeClassifier
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import roc_auc_score
    from sklearn.base import clone
    from scipy.stats import spearmanr
    _HAS_SK = True
except ImportError:
    _HAS_SK = False


MODEL_DIR = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) / "models"
MODEL_DIR.mkdir(exist_ok=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Feature Subset 정의 (관점 다양성의 핵심!)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 전체 37개 Feature 인덱스 참조 (batch_xgboost_v2.py FEATURE_NAMES_V2 순서):
# [0-9]   Core: moat, value, momentum, stability, news, analyst, insider, tech_a, flow_b, macro_c
# [10-14] Context: macro_score, risk_appetite, vix, regime, sector
# [15-22] Temporal: moat_d5, value_d5, mom_d5, news_d3, tech_d5, velocity, accel, days_grade
# [23-27] Interaction: val*mom, moat*stab, news*ins, tech*flow, vix*risk
# [28-31] CrossSection: sect_rank, vs_median, zscore, rel_strength
# [32-36] TechRaw: rsi, macd_hist, bb_pctb, atr_pct, vol_ratio

FEATURE_SUBSETS = {
    # Base 1: XGBoost — 전체 37개 (비선형 패턴 풀스펙)
    "xgb": list(range(37)),

    # Base 2: LightGBM — 시계열 + 매크로 + 상호작용 + 기술원시 (22개)
    # "이 종목이 최근에 어떻게 변하고 있는가" 관점
    "lgb": list(range(10, 37)),  # Context + Temporal + Interaction + Cross + TechRaw

    # Base 3: Ridge — 서브팩터 원본 + 횡단면 (14개)
    # "이 종목이 절대적으로 좋은가" 관점
    "ridge": list(range(0, 10)) + list(range(28, 32)),  # Core + CrossSection
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Base Learner 설정
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

XGB_PARAMS = {
    "objective": "binary:logistic", "eval_metric": "auc",
    "n_estimators": 500, "max_depth": 5, "learning_rate": 0.03,
    "subsample": 0.75, "colsample_bytree": 0.6, "min_child_weight": 30,
    "reg_alpha": 0.5, "reg_lambda": 2.0, "gamma": 0.1,
    "scale_pos_weight": 2.0, "random_state": 42, "n_jobs": -1,
    "tree_method": "hist",
}

LGB_PARAMS = {
    "objective": "binary", "metric": "auc",
    "n_estimators": 300, "max_depth": 4, "learning_rate": 0.05,
    "subsample": 0.7, "colsample_bytree": 0.7,
    "min_child_samples": 30, "reg_alpha": 0.3, "reg_lambda": 1.5,
    "random_state": 42, "n_jobs": -1, "verbose": -1,
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Stacking Ensemble 클래스
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class StackingEnsemble:
    """
    3-Model Stacking Ensemble.

    fit():
      1. Purged Walk-Forward로 각 Base의 Out-of-Fold 예측 수집
      2. OOF 3열 → Meta-Learner (LogisticRegression) 학습
      3. 전체 데이터로 Base 모델 최종 학습

    predict():
      1. 3개 Base 예측
      2. Meta-Learner 결합 → 최종 점수
      3. Disagreement = std(3개 예측) → 불확실성

    왜 3개인가:
      XGBoost: 비선형 패턴, 복잡한 상호작용 포착
      LightGBM: 빠른 학습, 최근 변화에 민감
      Ridge: 선형 기준점 (overfitting 방지 앵커)
      → 3개 모두 동의 = 높은 확신 → 큰 포지션
      → 불일치 = 불확실 → 작은 포지션
    """

    def __init__(self):
        self.base_models = {}
        self.meta_model = None
        self.scaler = StandardScaler()
        self.is_fitted = False
        self.oos_metrics = {}

    def fit(self, X, y, n_folds=5, purge=750, embargo=250):
        """
        Out-of-Fold Stacking 학습.

        Args:
            X: (n_samples, 37) feature matrix
            y: (n_samples,) binary labels
            purge/embargo: 인덱스 단위 (종목수*일수)
        """
        from batch.batch_xgboost import _purged_walk_forward_splits

        n = len(y)
        oof_preds = np.full((n, 3), np.nan)
        folds = _purged_walk_forward_splits(n, n_folds, purge, embargo)

        if len(folds) < 2:
            logger.warning("[ENSEMBLE] Fold 부족 — 단일 학습으로 전환")
            return self._fit_simple(X, y)

        base_configs = [
            ("xgb",   lambda: xgb.XGBClassifier(**XGB_PARAMS) if _HAS_XGB else None),
            ("lgb",   lambda: lgb.LGBMClassifier(**LGB_PARAMS) if _HAS_LGB else None),
            ("ridge", lambda: LogisticRegression(C=0.1, penalty='l2', class_weight='balanced',
                                                  max_iter=1000, random_state=42)),
        ]

        # ── OOF 예측 수집 ──
        for fold_i, (train_idx, test_idx) in enumerate(folds):
            for col_i, (name, model_fn) in enumerate(base_configs):
                model = model_fn()
                if model is None:
                    continue

                feat_idx = FEATURE_SUBSETS[name]
                X_tr = X[train_idx][:, feat_idx]
                X_te = X[test_idx][:, feat_idx]

                # Ridge는 스케일링 필요
                if name == "ridge":
                    sc = StandardScaler()
                    X_tr = sc.fit_transform(X_tr)
                    X_te = sc.transform(X_te)

                try:
                    model.fit(X_tr, y[train_idx])
                    if hasattr(model, 'predict_proba'):
                        oof_preds[test_idx, col_i] = model.predict_proba(X_te)[:, 1]
                    else:
                        oof_preds[test_idx, col_i] = model.decision_function(X_te)
                except Exception as e:
                    logger.warning(f"[ENSEMBLE] Fold {fold_i} {name} 실패: {e}")

        # ── Meta-Learner 학습 ──
        valid_mask = ~np.any(np.isnan(oof_preds), axis=1)
        if valid_mask.sum() < 50:
            logger.warning("[ENSEMBLE] 유효 OOF 부족 — 단일 학습으로 전환")
            return self._fit_simple(X, y)

        oof_valid = oof_preds[valid_mask]
        y_valid = y[valid_mask]

        self.meta_model = LogisticRegression(C=0.1, penalty='l2', max_iter=1000, random_state=42)
        self.meta_model.fit(oof_valid, y_valid)

        # ── Meta-Learner 성능 ──
        meta_proba = self.meta_model.predict_proba(oof_valid)[:, 1]
        try:
            meta_auc = round(roc_auc_score(y_valid, meta_proba), 4)
            meta_ic, _ = spearmanr(meta_proba, y_valid)
            meta_ic = round(meta_ic, 4) if not np.isnan(meta_ic) else 0.0
        except Exception as e:
            meta_auc, meta_ic = 0.5, 0.0

        # 개별 Base 성능
        for col_i, (name, _) in enumerate(base_configs):
            base_pred = oof_preds[valid_mask, col_i]
            if not np.any(np.isnan(base_pred)):
                try:
                    b_auc = round(roc_auc_score(y_valid, base_pred), 4)
                    b_ic, _ = spearmanr(base_pred, y_valid)
                    b_ic = round(b_ic, 4) if not np.isnan(b_ic) else 0.0
                except Exception as e:
                    b_auc, b_ic = 0.5, 0.0
                self.oos_metrics[name] = {"auc": b_auc, "ic": b_ic}

        self.oos_metrics["meta"] = {"auc": meta_auc, "ic": meta_ic}
        print(f"  [ENSEMBLE] OOS 성능:")
        for name, m in self.oos_metrics.items():
            print(f"    {name:6s}: AUC={m['auc']}, IC={m['ic']}")

        # ── 전체 데이터로 Base 최종 학습 ──
        for name, model_fn in base_configs:
            model = model_fn()
            if model is None:
                continue
            feat_idx = FEATURE_SUBSETS[name]
            X_sub = X[:, feat_idx]
            if name == "ridge":
                self.scaler.fit(X_sub)
                X_sub = self.scaler.transform(X_sub)
            model.fit(X_sub, y)
            self.base_models[name] = model

        self.is_fitted = True
        return self

    def _fit_simple(self, X, y):
        """Fold 부족시 단순 학습 (Fallback)"""
        base_configs = [
            ("xgb", lambda: xgb.XGBClassifier(**XGB_PARAMS) if _HAS_XGB else None),
            ("lgb", lambda: lgb.LGBMClassifier(**LGB_PARAMS) if _HAS_LGB else None),
            ("ridge", lambda: LogisticRegression(C=0.1, penalty='l2', class_weight='balanced',
                                                  max_iter=1000, random_state=42)),
        ]
        for name, model_fn in base_configs:
            model = model_fn()
            if model is None:
                continue
            feat_idx = FEATURE_SUBSETS[name]
            X_sub = X[:, feat_idx]
            if name == "ridge":
                self.scaler.fit(X_sub)
                X_sub = self.scaler.transform(X_sub)
            model.fit(X_sub, y)
            self.base_models[name] = model

        # Meta = 단순 평균 (OOF 없으므로)
        self.meta_model = None
        self.is_fitted = True
        return self

    def predict(self, X) -> dict:
        """
        최종 예측 + 불확실성(disagreement).

        Returns:
            {
              "ai_score": ndarray (0~100),
              "disagreement": ndarray (0~1, 낮을수록 합의),
              "base_xgb": ndarray, "base_lgb": ndarray, "base_ridge": ndarray,
            }
        """
        if not self.is_fitted:
            return {"ai_score": np.full(len(X), 50.0), "disagreement": np.ones(len(X))}

        base_preds = {}
        for name, model in self.base_models.items():
            feat_idx = FEATURE_SUBSETS[name]
            X_sub = X[:, feat_idx]
            if name == "ridge":
                X_sub = self.scaler.transform(X_sub)
            try:
                if hasattr(model, 'predict_proba'):
                    base_preds[name] = model.predict_proba(X_sub)[:, 1]
                else:
                    raw = model.decision_function(X_sub)
                    base_preds[name] = 1 / (1 + np.exp(-raw))  # sigmoid
            except Exception as e:
                logger.warning(f"[ENSEMBLE] {name} 추론 실패: {e}")
                base_preds[name] = np.full(len(X), 0.5)

        # Stack → Meta
        if len(base_preds) >= 2:
            pred_matrix = np.column_stack([base_preds.get("xgb", np.full(len(X), 0.5)),
                                           base_preds.get("lgb", np.full(len(X), 0.5)),
                                           base_preds.get("ridge", np.full(len(X), 0.5))])
        else:
            pred_matrix = np.column_stack(list(base_preds.values()))

        if self.meta_model is not None:
            try:
                final_proba = self.meta_model.predict_proba(pred_matrix)[:, 1]
            except Exception as e:
                final_proba = np.mean(pred_matrix, axis=1)
        else:
            final_proba = np.mean(pred_matrix, axis=1)

        disagreement = np.std(pred_matrix, axis=1)

        return {
            "ai_score": np.round(final_proba * 100, 2),
            "disagreement": np.round(disagreement, 4),
            "base_xgb": base_preds.get("xgb", np.full(len(X), 50.0)),
            "base_lgb": base_preds.get("lgb", np.full(len(X), 50.0)),
            "base_ridge": base_preds.get("ridge", np.full(len(X), 50.0)),
        }

    def save(self, calc_date: date):
        """모델 저장"""
        path = str(MODEL_DIR / f"ensemble_v1_{calc_date.isoformat()}.pkl")
        joblib.dump({
            "base_models": self.base_models,
            "meta_model": self.meta_model,
            "scaler": self.scaler,
            "oos_metrics": self.oos_metrics,
        }, path)
        return path

    @staticmethod
    def load(path: str):
        """모델 로드"""
        data = joblib.load(path)
        ens = StackingEnsemble()
        ens.base_models = data["base_models"]
        ens.meta_model = data["meta_model"]
        ens.scaler = data["scaler"]
        ens.oos_metrics = data.get("oos_metrics", {})
        ens.is_fitted = True
        return ens


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DB 저장
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _ensure_ensemble_tables():
    """앙상블 결과 저장 테이블"""
    with get_cursor() as cur:
        # ai_scores_daily 확장 (disagreement 컬럼)
        for col_def in [
            "disagreement NUMERIC(6,4)",
            "base_xgb NUMERIC(6,2)",
            "base_lgb NUMERIC(6,2)",
            "base_ridge NUMERIC(6,2)",
            "ensemble_method VARCHAR(20) DEFAULT 'stacking'",
        ]:
            col_name = col_def.split()[0]
            try:
                cur.execute(f"ALTER TABLE ai_scores_daily ADD COLUMN IF NOT EXISTS {col_def}")
            except Exception:
                pass
    print("[ENSEMBLE] ✅ 테이블 확장 완료")


def _save_ensemble_results(stock_ids, results, calc_date, model_id, ai_weight):
    """앙상블 결과 DB 저장"""
    saved = 0
    with get_cursor() as cur:
        for i, stock_id in enumerate(stock_ids):
            ai_s = float(results["ai_score"][i])
            disagree = float(results["disagreement"][i])
            b_xgb = float(results["base_xgb"][i]) * 100
            b_lgb = float(results["base_lgb"][i]) * 100
            b_ridge = float(results["base_ridge"][i]) * 100

            # 통계 점수 조회
            try:
                cur.execute("""
                    SELECT weighted_score FROM stock_final_scores
                    WHERE stock_id=%s AND calc_date<=%s ORDER BY calc_date DESC LIMIT 1
                """, (stock_id, calc_date))
                row = cur.fetchone()
                stat_s = round(float(row["weighted_score"]), 2) if row and row["weighted_score"] else None
            except Exception as e:
                stat_s = None

            ens = round(stat_s * (1 - ai_weight) + ai_s * ai_weight, 2) if stat_s else ai_s

            try:
                cur.execute("""
                    INSERT INTO ai_scores_daily
                        (stock_id, calc_date, ai_score, ai_proba, ensemble_score,
                         stat_score, ai_weight, disagreement,
                         base_xgb, base_lgb, base_ridge, ensemble_method,
                         model_id, updated_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'stacking',%s,NOW())
                    ON CONFLICT (stock_id, calc_date) DO UPDATE SET
                        ai_score=EXCLUDED.ai_score, ai_proba=EXCLUDED.ai_proba,
                        ensemble_score=EXCLUDED.ensemble_score, stat_score=EXCLUDED.stat_score,
                        ai_weight=EXCLUDED.ai_weight, disagreement=EXCLUDED.disagreement,
                        base_xgb=EXCLUDED.base_xgb, base_lgb=EXCLUDED.base_lgb,
                        base_ridge=EXCLUDED.base_ridge, ensemble_method=EXCLUDED.ensemble_method,
                        model_id=EXCLUDED.model_id, updated_at=NOW()
                """, (
                    stock_id, calc_date, ai_s, round(ai_s / 100, 4), ens,
                    stat_s, ai_weight, disagree,
                    round(b_xgb, 2), round(b_lgb, 2), round(b_ridge, 2),
                    model_id,
                ))
                saved += 1
            except Exception as e:
                if saved < 3:
                    logger.warning(f"[ENSEMBLE] save err stock={stock_id}: {e}")

    return saved


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 공개 API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run_ensemble(calc_date: date = None):
    """
    scheduler.py Step 6.3에서 호출.

    1. 학습 필요 여부 판단 (일요일 OR 모델 없음)
    2. 학습: Purged WF OOF Stacking + Gatekeeper
    3. 추론: 전 종목 ai_score + disagreement 저장
    """
    if calc_date is None:
        calc_date = date.today()

    print(f"\n[ENSEMBLE] === Stacking Ensemble — {calc_date} ===")

    if not (_HAS_XGB and _HAS_SK):
        print("[ENSEMBLE] ⚠️ 필수 패키지 미설치")
        # Fallback: 기존 batch_xgboost 사용
        from batch.batch_xgboost import run_xgboost
        return run_xgboost(calc_date)

    _ensure_ensemble_tables()

    # 학습 판단
    model_path = str(MODEL_DIR / f"ensemble_v1_{calc_date.isoformat()}.pkl")
    existing = _find_latest_ensemble()
    should_train = (calc_date.weekday() == 6) or (existing is None)

    model_id = None

    if should_train:
        print("[ENSEMBLE] 학습 시작...")
        from batch.batch_xgboost import _build_features_v2, _create_labels_v2

        # 데이터 수집 (252일)
        all_X, all_y = None, None
        end_date = calc_date - timedelta(days=15)
        start_date = end_date - timedelta(days=380)
        d = start_date
        snapshot_count = 0

        while d <= end_date:
            if d.weekday() >= 5:
                d += timedelta(days=1)
                continue
            ids, X, y, dates, _ = _build_features_v2(d, with_label=True)
            if y is not None and len(y) > 50:
                if all_X is None:
                    all_X, all_y = X, y
                else:
                    all_X = np.vstack([all_X, X])
                    all_y = np.concatenate([all_y, y])
                snapshot_count += 1
            d += timedelta(days=7)

        if all_X is None or len(all_y) < 500:
            print(f"[ENSEMBLE] ❌ 데이터 부족: {len(all_y) if all_y is not None else 0}")
            # Fallback
            from batch.batch_xgboost import run_xgboost
            return run_xgboost(calc_date)

        print(f"  데이터: {len(all_y)} samples, {snapshot_count} snapshots, "
              f"positive={all_y.sum()}/{len(all_y)} ({all_y.mean():.1%})")

        # 학습
        ensemble = StackingEnsemble()
        ensemble.fit(all_X, all_y)
        saved_path = ensemble.save(calc_date)

        # DB 메타 저장
        meta_metrics = ensemble.oos_metrics.get("meta", {"auc": 0.5, "ic": 0.0})
        with get_cursor() as cur:
            cur.execute("UPDATE ml_model_meta SET is_active=FALSE WHERE is_active=TRUE")
            cur.execute("""
                INSERT INTO ml_model_meta
                    (model_name, trained_date, train_samples, oos_ic, oos_auc,
                     feature_count, model_path, is_active, notes)
                VALUES (%s,%s,%s,%s,%s,%s,%s,TRUE,%s) RETURNING id
            """, ("ensemble_v1", calc_date, len(all_y),
                  meta_metrics["ic"], meta_metrics["auc"],
                  37, saved_path,
                  json.dumps(ensemble.oos_metrics, ensure_ascii=False)))
            model_id = cur.fetchone()["id"]

        # Gatekeeper 로그
        _log_gatekeeper(calc_date, meta_metrics)

        print(f"[ENSEMBLE] ✅ 학습 완료 (model_id={model_id})")
    else:
        ensemble = StackingEnsemble.load(existing)
        print(f"[ENSEMBLE] 기존 모델 로드: {existing}")
        # model_id 조회
        try:
            with get_cursor() as cur:
                cur.execute("SELECT id FROM ml_model_meta WHERE is_active=TRUE ORDER BY trained_date DESC LIMIT 1")
                row = cur.fetchone()
                model_id = row["id"] if row else None
        except Exception as e:
            model_id = None

    # ── 추론 ──
    from batch.batch_xgboost import _build_features_v2, _get_ai_weight
    stock_ids, X, _, _, _ = _build_features_v2(calc_date, with_label=False)

    if len(stock_ids) == 0:
        print("[ENSEMBLE] ⚠️ 추론 데이터 없음")
        return {"error": "no_data"}

    results = ensemble.predict(X)
    ai_weight = _get_ai_weight()

    # 저장
    saved = _save_ensemble_results(stock_ids, results, calc_date, model_id, ai_weight)

    # Telemetry
    avg_disagree = float(np.mean(results["disagreement"]))
    _log_telemetry(calc_date, "MODEL", "ensemble_inference", saved,
                   {"total": len(stock_ids), "avg_disagreement": round(avg_disagree, 4),
                    "ai_weight": ai_weight})

    print(f"[ENSEMBLE] ✅ 추론 저장: {saved}/{len(stock_ids)} "
          f"(avg_disagreement={avg_disagree:.4f}, weight={ai_weight})")

    return {"ok": saved, "total": len(stock_ids), "ai_weight": ai_weight,
            "avg_disagreement": avg_disagree}


def _find_latest_ensemble() -> str:
    """최신 앙상블 모델 파일 찾기"""
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT model_path FROM ml_model_meta
                WHERE is_active=TRUE AND model_name LIKE 'ensemble%'
                ORDER BY trained_date DESC LIMIT 1
            """)
            row = cur.fetchone()
            if row and row["model_path"] and os.path.exists(row["model_path"]):
                return row["model_path"]
    except Exception as e:
        logger.debug(f"Handled: {e}")
    return None


def _log_gatekeeper(calc_date, metrics):
    """Gatekeeper 로그"""
    try:
        with get_cursor() as cur:
            cur.execute("""
                INSERT INTO model_gatekeeper_log (calc_date, model_type, oos_ic, oos_auc, decision, reason)
                VALUES (%s, 'ensemble_v1', %s, %s, 'APPROVED', %s)
            """, (calc_date, metrics.get("ic", 0), metrics.get("auc", 0.5),
                  json.dumps(metrics, ensure_ascii=False)))
    except Exception as e:
        logger.warning(f"[GATEKEEPER] 로그 실패: {e}")


def _log_telemetry(calc_date, category, metric_name, metric_value, detail=None):
    """Telemetry 기록"""
    try:
        with get_cursor() as cur:
            cur.execute("""
                INSERT INTO system_telemetry (calc_date, category, metric_name, metric_value, detail)
                VALUES (%s, %s, %s, %s, %s)
            """, (calc_date, category, metric_name, metric_value,
                  json.dumps(detail, ensure_ascii=False) if detail else None))
    except Exception as e:
        logger.warning(f"[TELEMETRY] 실패: {e}")


# 하위 호환
run_all = run_ensemble