"""
batch/batch_xgboost.py — Factor Interaction (XGBoost) + Explainable AI (SHAP)
==============================================================================
AI 모듈 #4 + #5: XGBoost ML 스코어링 + SHAP 설명

핵심 기능:
  1. Feature 구축: 3개 레이어 점수 + 서브팩터 + 매크로 = 18개
  2. Label 생성: 5일 Forward Return 상위 20% = 1 (Binary Classification)
  3. Walk-Forward 학습: 미래 데이터 절대 사용 금지
  4. 일일 추론: 학습된 모델로 전 종목 AI Score 생성
  5. 앙상블: stat_score × 0.7 + ai_score × 0.3 = final
  6. SHAP: TreeExplainer로 종목별 기여도 분해
  7. 주간 재학습: 일요일 최신 60일 데이터로 모델 업데이트

학술 참조:
  - Chen & Guestrin (2016) "XGBoost: A Scalable Tree Boosting System"
  - Lundberg & Lee (2017) "SHAP: A Unified Approach to Interpreting Model Predictions"
  - López de Prado (2018) "Advances in Financial Machine Learning"
    → Walk-Forward Validation, Purged K-Fold

실행:
  - 추론: 매일 배치 Step 6.8 (1~2초)
  - 학습: 매주 일요일 Step 6.8에서 자동 판단 (30~60초)

월비용: $0 (XGBoost + SHAP 로컬 연산)
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
from datetime import datetime, date, timedelta
from pathlib import Path
from db_pool import get_cursor

try:
    import xgboost as xgb
    _HAS_XGB = True
except ImportError:
    _HAS_XGB = False
    print("[XGB] ⚠️ xgboost 미설치 — pip install xgboost")

try:
    import shap
    _HAS_SHAP = True
except ImportError:
    _HAS_SHAP = False
    print("[XGB] ⚠️ shap 미설치 — pip install shap")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 상수
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MODEL_DIR = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) / "models"
MODEL_DIR.mkdir(exist_ok=True)

# Feature 정의 (18개)
FEATURE_NAMES = [
    "layer1_score", "layer2_score", "layer3_score",
    "moat_score", "value_score", "momentum_score", "stability_score",
    "news_score", "analyst_score", "insider_score",
    "section_a_tech", "section_b_flow", "section_c_macro",
    "macro_score", "risk_appetite", "vix_close",
    "market_regime_num", "sector_code_num",
]

FEATURE_DISPLAY = {
    "layer1_score":      "기본면 (L1)",
    "layer2_score":      "심리면 (L2)",
    "layer3_score":      "기술면 (L3)",
    "moat_score":        "경쟁우위 (ROIC/GPA/FCF)",
    "value_score":       "가치 (EV/EBIT, P/B)",
    "momentum_score":    "모멘텀 (실적추세)",
    "stability_score":   "안정성 (변동성/배당)",
    "news_score":        "뉴스 감성",
    "analyst_score":     "애널리스트 평가",
    "insider_score":     "내부자 거래",
    "section_a_tech":    "기술지표 (RSI/MACD)",
    "section_b_flow":    "수급 (공매도/풋콜)",
    "section_c_macro":   "시장환경 (VIX/섹터ETF)",
    "macro_score":       "글로벌 매크로",
    "risk_appetite":     "위험선호지수",
    "vix_close":         "VIX 공포지수",
    "market_regime_num": "시장 국면",
    "sector_code_num":   "업종",
}

REGIME_MAP = {"BULL": 2, "NEUTRAL": 1, "BEAR": 0, "CRISIS": -1}

# 학습 파라미터
XGB_PARAMS = {
    "objective": "binary:logistic",
    "eval_metric": "auc",
    "n_estimators": 300,
    "max_depth": 4,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 20,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "random_state": 42,
    "n_jobs": -1,
}
EARLY_STOPPING = 30
TRAIN_DAYS = 60         # 학습 데이터 기간
FORWARD_HORIZON = 5     # 5영업일 Forward Return
TOP_QUANTILE = 0.20     # 상위 20% = Label 1
MIN_TRAIN_SAMPLES = 500 # 최소 학습 데이터
AI_WEIGHT_DEFAULT = 0.30 # 앙상블 기본 비중


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 테이블 생성
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _ensure_tables():
    with get_cursor() as cur:
        # ML 모델 메타데이터
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ml_model_meta (
                id            SERIAL PRIMARY KEY,
                model_name    VARCHAR(50) DEFAULT 'xgb_v1',
                trained_date  DATE NOT NULL,
                train_samples INT,
                train_auc     NUMERIC(6,4),
                valid_auc     NUMERIC(6,4),
                feature_count INT,
                model_path    TEXT,
                is_active     BOOLEAN DEFAULT FALSE,
                notes         TEXT,
                created_at    TIMESTAMPTZ DEFAULT NOW()
            )
        """)

        # AI 점수 + SHAP 저장
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ai_scores_daily (
                id            SERIAL PRIMARY KEY,
                stock_id      INT NOT NULL,
                calc_date     DATE NOT NULL,
                ai_score      NUMERIC(6,2),
                ai_proba      NUMERIC(6,4),
                ensemble_score NUMERIC(6,2),
                stat_score    NUMERIC(6,2),
                ai_weight     NUMERIC(4,2),
                shap_top5_pos JSONB,
                shap_top5_neg JSONB,
                shap_all      JSONB,
                shap_base     NUMERIC(8,4),
                model_id      INT,
                updated_at    TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(stock_id, calc_date)
            )
        """)

        # Feature Importance 기록 (모델별)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS xgb_feature_importance (
                id            SERIAL PRIMARY KEY,
                model_id      INT NOT NULL,
                feature_name  VARCHAR(50) NOT NULL,
                importance    NUMERIC(8,6),
                rank          INT,
                UNIQUE(model_id, feature_name)
            )
        """)

        cur.execute("CREATE INDEX IF NOT EXISTS idx_ai_scores_date ON ai_scores_daily(calc_date)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_ai_scores_stock ON ai_scores_daily(stock_id, calc_date)")

    print("[XGB] ✅ 테이블 확인 완료")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Feature 구축
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _build_features(target_date: date, with_label: bool = False) -> tuple:
    """
    18개 Feature Matrix 구축.

    with_label=True: 학습용 (Forward Return Label 포함)
    with_label=False: 추론용 (오늘 기준)

    Returns:
        (stock_ids, X, y, feature_names)
        y is None if with_label=False
    """
    # 매크로 데이터 (날짜별 1회)
    macro = _get_macro_data(target_date)
    regime_num = macro.get("regime_num", 1)
    vix = macro.get("vix_close", 20.0)
    macro_score_val = macro.get("macro_score", 50.0)
    risk_app = macro.get("risk_appetite", 0.0)

    # Forward Return 기준일 (label용)
    fwd_date = target_date + timedelta(days=int(FORWARD_HORIZON * 1.5))

    with get_cursor() as cur:
        label_join = ""
        label_select = ""
        label_where = ""

        if with_label:
            label_select = """,
                (p_fwd.close_price - p_now.close_price) / NULLIF(p_now.close_price, 0) * 100
                    AS fwd_return"""
            label_join = f"""
            LEFT JOIN LATERAL (
                SELECT close_price FROM stock_prices_daily
                WHERE stock_id = s.stock_id AND trade_date >= '{fwd_date}'::date
                ORDER BY trade_date ASC LIMIT 1
            ) p_fwd ON TRUE
            LEFT JOIN LATERAL (
                SELECT close_price FROM stock_prices_daily
                WHERE stock_id = s.stock_id AND trade_date <= '{target_date}'::date
                ORDER BY trade_date DESC LIMIT 1
            ) p_now ON TRUE"""
            label_where = "AND p_now.close_price > 0 AND p_fwd.close_price IS NOT NULL"

        cur.execute(f"""
            SELECT
                s.stock_id, s.ticker,
                COALESCE(s.sector_id, 0) AS sector_id,
                -- Layer scores
                sfs.weighted_score AS stat_score,
                sfs.layer1_score,
                sfs.layer2_score,
                sfs.layer3_score,
                -- Layer1 sub-scores
                l1.moat_score, l1.value_score, l1.momentum_score, l1.stability_score,
                -- Layer2 sub-scores
                l2.news_sentiment_score AS news_score, l2.analyst_rating_score AS analyst_score, l2.insider_signal_score AS insider_score,
                -- Layer3 sub-scores
                ti.section_a_technical AS section_a_tech,
                ti.section_b_flow,
                ti.section_c_macro
                {label_select}
            FROM stocks s
            LEFT JOIN LATERAL (
                SELECT weighted_score, layer1_score, layer2_score, layer3_score
                FROM stock_final_scores
                WHERE stock_id = s.stock_id AND calc_date <= %s
                ORDER BY calc_date DESC LIMIT 1
            ) sfs ON TRUE
            LEFT JOIN LATERAL (
                SELECT moat_score, value_score, momentum_score, stability_score
                FROM stock_layer1_analysis
                WHERE stock_id = s.stock_id AND calc_date <= %s
                ORDER BY calc_date DESC LIMIT 1
            ) l1 ON TRUE
            LEFT JOIN LATERAL (
                SELECT news_sentiment_score AS news_score, analyst_rating_score AS analyst_score, insider_signal_score AS insider_score
                FROM layer2_scores
                WHERE stock_id = s.stock_id AND calc_date <= %s
                ORDER BY calc_date DESC LIMIT 1
            ) l2 ON TRUE
            LEFT JOIN LATERAL (
                SELECT section_a_technical, section_b_flow, section_c_macro
                FROM technical_indicators
                WHERE stock_id = s.stock_id AND calc_date <= %s
                ORDER BY calc_date DESC LIMIT 1
            ) ti ON TRUE
            {label_join}
            WHERE s.is_active = TRUE
              AND sfs.weighted_score IS NOT NULL
              {label_where}
        """, (target_date, target_date, target_date, target_date))
        rows = cur.fetchall()

    if not rows:
        return [], np.array([]), None, FEATURE_NAMES

    stock_ids = []
    features = []
    labels = []

    for r in rows:
        f = lambda v: float(v) if v is not None else np.nan

        feat = [
            f(r.get("layer1_score")),
            f(r.get("layer2_score")),
            f(r.get("layer3_score")),
            f(r.get("moat_score")),
            f(r.get("value_score")),
            f(r.get("momentum_score")),
            f(r.get("stability_score")),
            f(r.get("news_score")),
            f(r.get("analyst_score")),
            f(r.get("insider_score")),
            f(r.get("section_a_tech")),
            f(r.get("section_b_flow")),
            f(r.get("section_c_macro")),
            f(macro_score_val),
            f(risk_app),
            f(vix),
            float(regime_num),
            float(r.get("sector_id", 0)),
        ]

        stock_ids.append(r["stock_id"])
        features.append(feat)

        if with_label and r.get("fwd_return") is not None:
            labels.append(float(r["fwd_return"]))

    X = np.array(features, dtype=np.float32)

    # NaN → 열 중앙값으로 대체
    for col in range(X.shape[1]):
        mask = np.isnan(X[:, col])
        if mask.any():
            median = np.nanmedian(X[:, col])
            X[mask, col] = median if not np.isnan(median) else 0.0

    y = None
    if with_label and labels:
        returns = np.array(labels)
        threshold = np.percentile(returns, 100 * (1 - TOP_QUANTILE))
        y = (returns >= threshold).astype(int)

    return stock_ids, X, y, FEATURE_NAMES


def _get_macro_data(target_date: date) -> dict:
    """매크로 데이터 조회"""
    result = {"regime_num": 1, "vix_close": 20.0, "macro_score": 50.0, "risk_appetite": 0.0}
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT regime FROM market_regime
                WHERE regime_date <= %s ORDER BY regime_date DESC LIMIT 1
            """, (target_date,))
            row = cur.fetchone()
            if row:
                result["regime_num"] = REGIME_MAP.get(row["regime"], 1)

            cur.execute("""
                SELECT macro_score, risk_appetite
                FROM cross_asset_daily
                WHERE calc_date <= %s ORDER BY calc_date DESC LIMIT 1
            """, (target_date,))
            row = cur.fetchone()
            if row:
                if row.get("macro_score"):
                    result["macro_score"] = float(row["macro_score"])
                if row.get("risk_appetite"):
                    result["risk_appetite"] = float(row["risk_appetite"])

            cur.execute("""
                SELECT value FROM macro_indicators
                WHERE indicator_name = 'VIX'
                ORDER BY recorded_date DESC LIMIT 1
            """)
            row = cur.fetchone()
            if row and row["value"]:
                result["vix_close"] = float(row["value"])
    except Exception:
        pass
    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 학습 (Walk-Forward)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _train_model(calc_date: date) -> dict:
    """
    Walk-Forward 학습.

    Train: calc_date - 60일 ~ calc_date - 10일
    Valid: calc_date - 10일 ~ calc_date
    """
    if not _HAS_XGB:
        return {"error": "xgboost not installed"}

    print(f"[XGB] 🔧 학습 시작 (Train: {TRAIN_DAYS}일, Forward: {FORWARD_HORIZON}일)")

    # 학습 데이터 수집: 여러 날짜의 스냅샷
    all_X = []
    all_y = []

    train_end = calc_date - timedelta(days=10)
    train_start = train_end - timedelta(days=TRAIN_DAYS)

    # 5일 간격으로 스냅샷 (과도한 중복 방지)
    snapshot_dates = []
    d = train_start
    while d <= train_end:
        snapshot_dates.append(d)
        d += timedelta(days=5)

    print(f"[XGB] 스냅샷 날짜: {len(snapshot_dates)}개 ({train_start} ~ {train_end})")

    for sd in snapshot_dates:
        stock_ids, X, y, _ = _build_features(sd, with_label=True)
        if y is not None and len(y) > 0:
            all_X.append(X)
            all_y.append(y)

    if not all_X:
        print("[XGB] ❌ 학습 데이터 없음")
        return {"error": "no training data"}

    X_train = np.vstack(all_X)
    y_train = np.concatenate(all_y)

    print(f"[XGB] 학습 데이터: {X_train.shape[0]:,} samples × {X_train.shape[1]} features")
    print(f"[XGB] Label 분포: {int(y_train.sum())} positive / {len(y_train) - int(y_train.sum())} negative")

    if X_train.shape[0] < MIN_TRAIN_SAMPLES:
        print(f"[XGB] ❌ 데이터 부족: {X_train.shape[0]} < {MIN_TRAIN_SAMPLES}")
        return {"error": "insufficient data"}

    # Validation 데이터
    val_ids, X_val, y_val, _ = _build_features(train_end + timedelta(days=5), with_label=True)

    # 학습
    model = xgb.XGBClassifier(**XGB_PARAMS)

    eval_set = [(X_train, y_train)]
    if y_val is not None and len(y_val) > 0:
        eval_set.append((X_val, y_val))

    model.fit(
        X_train, y_train,
        eval_set=eval_set,
        verbose=False,
    )

    # 성능 평가
    from sklearn.metrics import roc_auc_score
    train_proba = model.predict_proba(X_train)[:, 1]
    train_auc = round(roc_auc_score(y_train, train_proba), 4)

    valid_auc = None
    if y_val is not None and len(y_val) > 10:
        val_proba = model.predict_proba(X_val)[:, 1]
        try:
            valid_auc = round(roc_auc_score(y_val, val_proba), 4)
        except Exception:
            valid_auc = None

    print(f"[XGB] Train AUC: {train_auc}")
    print(f"[XGB] Valid AUC: {valid_auc}")

    # 모델 저장
    model_filename = f"xgb_{calc_date.isoformat()}.pkl"
    model_path = str(MODEL_DIR / model_filename)
    joblib.dump(model, model_path)
    print(f"[XGB] 모델 저장: {model_path}")

    # DB 메타 저장
    with get_cursor() as cur:
        # 기존 모델 비활성화
        cur.execute("UPDATE ml_model_meta SET is_active = FALSE WHERE is_active = TRUE")

        cur.execute("""
            INSERT INTO ml_model_meta
                (model_name, trained_date, train_samples, train_auc, valid_auc,
                 feature_count, model_path, is_active, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE, %s)
            RETURNING id
        """, (
            "xgb_v1", calc_date, X_train.shape[0], train_auc, valid_auc,
            len(FEATURE_NAMES), model_path,
            f"snapshots={len(snapshot_dates)}, label_pos={int(y_train.sum())}",
        ))
        model_id = cur.fetchone()["id"]

    # Feature Importance 저장
    importances = model.feature_importances_
    sorted_idx = np.argsort(importances)[::-1]
    print(f"\n[XGB] Feature Importance TOP 10:")
    with get_cursor() as cur:
        for rank, idx in enumerate(sorted_idx[:10], 1):
            fname = FEATURE_NAMES[idx]
            imp = round(float(importances[idx]), 6)
            print(f"  {rank:2d}. {FEATURE_DISPLAY.get(fname, fname):25s}  {imp:.4f}")
            cur.execute("""
                INSERT INTO xgb_feature_importance (model_id, feature_name, importance, rank)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (model_id, feature_name) DO UPDATE SET
                    importance = EXCLUDED.importance, rank = EXCLUDED.rank
            """, (model_id, fname, imp, rank))

    return {
        "model_id": model_id,
        "train_auc": train_auc,
        "valid_auc": valid_auc,
        "train_samples": X_train.shape[0],
        "model_path": model_path,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 추론 + SHAP
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _load_active_model():
    """활성 모델 로드"""
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT id, model_path FROM ml_model_meta
                WHERE is_active = TRUE
                ORDER BY trained_date DESC LIMIT 1
            """)
            row = cur.fetchone()

        if row and row["model_path"] and os.path.exists(row["model_path"]):
            model = joblib.load(row["model_path"])
            return model, row["id"]
    except Exception as e:
        print(f"[XGB] 모델 로드 실패: {e}")

    return None, None


def _predict_and_explain(calc_date: date) -> dict:
    """
    일일 추론 + SHAP 설명.

    1. 활성 모델 로드
    2. 오늘 Feature 구축
    3. predict_proba → ai_score
    4. SHAP TreeExplainer → 종목별 기여도
    5. stat_score × (1-w) + ai_score × w = ensemble
    6. DB 저장
    """
    model, model_id = _load_active_model()
    if model is None:
        print("[XGB] ⚠️ 활성 모델 없음 — 추론 스킵")
        return {"ok": 0, "reason": "no_active_model"}

    # Feature 구축
    stock_ids, X, _, _ = _build_features(calc_date, with_label=False)
    if len(stock_ids) == 0:
        print("[XGB] ⚠️ Feature 데이터 없음")
        return {"ok": 0, "reason": "no_features"}

    print(f"[XGB] 추론: {len(stock_ids)}종목 × {X.shape[1]} features")

    # Predict
    probas = model.predict_proba(X)[:, 1]
    ai_scores = np.round(probas * 100, 2)

    # SHAP 계산
    shap_results = {}
    if _HAS_SHAP:
        try:
            explainer = shap.TreeExplainer(model)
            shap_values = explainer.shap_values(X)
            base_value = float(explainer.expected_value)
            if isinstance(explainer.expected_value, np.ndarray):
                base_value = float(explainer.expected_value[0])

            for i, stock_id in enumerate(stock_ids):
                sv = shap_values[i]
                shap_dict = {
                    FEATURE_NAMES[j]: round(float(sv[j]), 4)
                    for j in range(len(FEATURE_NAMES))
                }

                sorted_feats = sorted(shap_dict.items(), key=lambda x: abs(x[1]), reverse=True)
                top5_pos = [
                    {"feature": FEATURE_DISPLAY.get(k, k), "shap": v, "raw": k}
                    for k, v in sorted_feats if v > 0
                ][:5]
                top5_neg = [
                    {"feature": FEATURE_DISPLAY.get(k, k), "shap": v, "raw": k}
                    for k, v in sorted_feats if v < 0
                ][:5]

                shap_results[stock_id] = {
                    "all": shap_dict,
                    "top5_pos": top5_pos,
                    "top5_neg": top5_neg,
                    "base": base_value,
                }

            print(f"[XGB] SHAP 계산 완료: {len(shap_results)}종목")
        except Exception as e:
            print(f"[XGB] SHAP 계산 실패: {e}")
    else:
        print("[XGB] SHAP 미설치 — 기여도 없이 저장")

    # stat_score 조회 + Ensemble
    stat_scores = {}
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT DISTINCT ON (stock_id) stock_id, weighted_score
                FROM stock_final_scores
                WHERE calc_date <= %s
                ORDER BY stock_id, calc_date DESC
            """, (calc_date,))
            for r in cur.fetchall():
                stat_scores[r["stock_id"]] = float(r["weighted_score"])
    except Exception:
        pass

    # AI Weight 조회 (Self-Improving Engine이 조정)
    ai_weight = _get_ai_weight()

    # DB 저장
    saved = 0
    for i, stock_id in enumerate(stock_ids):
        try:
            ai_s = float(ai_scores[i])
            stat_s = stat_scores.get(stock_id, 50.0)
            ens = round(stat_s * (1 - ai_weight) + ai_s * ai_weight, 2)

            shap_data = shap_results.get(stock_id, {})

            with get_cursor() as cur:
                cur.execute("""
                    INSERT INTO ai_scores_daily
                        (stock_id, calc_date, ai_score, ai_proba, ensemble_score,
                         stat_score, ai_weight, shap_top5_pos, shap_top5_neg,
                         shap_all, shap_base, model_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (stock_id, calc_date) DO UPDATE SET
                        ai_score = EXCLUDED.ai_score,
                        ai_proba = EXCLUDED.ai_proba,
                        ensemble_score = EXCLUDED.ensemble_score,
                        stat_score = EXCLUDED.stat_score,
                        ai_weight = EXCLUDED.ai_weight,
                        shap_top5_pos = EXCLUDED.shap_top5_pos,
                        shap_top5_neg = EXCLUDED.shap_top5_neg,
                        shap_all = EXCLUDED.shap_all,
                        shap_base = EXCLUDED.shap_base,
                        model_id = EXCLUDED.model_id,
                        updated_at = NOW()
                """, (
                    stock_id, calc_date, ai_s, round(float(probas[i]), 4), ens,
                    stat_s, ai_weight,
                    json.dumps(shap_data.get("top5_pos", []), ensure_ascii=False),
                    json.dumps(shap_data.get("top5_neg", []), ensure_ascii=False),
                    json.dumps(shap_data.get("all", {})),
                    shap_data.get("base"),
                    model_id,
                ))
            saved += 1
        except Exception as e:
            if saved < 3:
                print(f"  [ERR] stock_id={stock_id}: {e}")

    print(f"[XGB] ✅ 추론+SHAP 저장: {saved}/{len(stock_ids)}종목 (AI weight={ai_weight})")

    return {"ok": saved, "total": len(stock_ids), "ai_weight": ai_weight, "model_id": model_id}


def _get_ai_weight() -> float:
    """AI 앙상블 비중 조회 (Self-Improving Engine과 연동)"""
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT avg_ic_l1 AS ic_stat, ic_total AS ic_ai
                FROM factor_weights_monthly
                ORDER BY month DESC LIMIT 1
            """)
            row = cur.fetchone()
            if row and row.get("ic_ai") and row.get("ic_stat"):
                ic_ai = float(row["ic_ai"])
                ic_stat = float(row["ic_stat"])
                # AI IC가 stat IC보다 높으면 비중 증가
                if ic_ai > ic_stat * 1.2:
                    return min(0.50, AI_WEIGHT_DEFAULT + 0.10)
                elif ic_ai < ic_stat * 0.5:
                    return max(0.10, AI_WEIGHT_DEFAULT - 0.10)
    except Exception:
        pass
    return AI_WEIGHT_DEFAULT


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 공개 API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_stock_explanation(stock_id: int, calc_date: date = None) -> dict:
    """
    종목별 SHAP 설명 조회 (API 엔드포인트용).

    Returns:
        {"ai_score": 82.5, "base_value": 45.2,
         "top_positive": [...], "top_negative": [...], "all_shap": {...}}
    """
    if calc_date is None:
        calc_date = datetime.now().date()
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT ai_score, shap_base, shap_top5_pos, shap_top5_neg, shap_all,
                       ensemble_score, stat_score, ai_weight
                FROM ai_scores_daily
                WHERE stock_id = %s AND calc_date <= %s
                ORDER BY calc_date DESC LIMIT 1
            """, (stock_id, calc_date))
            row = cur.fetchone()
            if row:
                return {
                    "ai_score": float(row["ai_score"]) if row["ai_score"] else None,
                    "ensemble_score": float(row["ensemble_score"]) if row["ensemble_score"] else None,
                    "stat_score": float(row["stat_score"]) if row["stat_score"] else None,
                    "ai_weight": float(row["ai_weight"]) if row["ai_weight"] else None,
                    "base_value": float(row["shap_base"]) if row["shap_base"] else None,
                    "top_positive": row["shap_top5_pos"] if row["shap_top5_pos"] else [],
                    "top_negative": row["shap_top5_neg"] if row["shap_top5_neg"] else [],
                    "all_shap": row["shap_all"] if row["shap_all"] else {},
                }
    except Exception:
        pass
    return {"ai_score": None, "top_positive": [], "top_negative": []}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 메인 실행
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run_xgboost(calc_date: date = None):
    """
    XGBoost + SHAP 메인 실행.
    Scheduler Step 6.8에서 호출.

    일요일: 재학습 + 추론
    그 외:  추론만
    """
    if calc_date is None:
        calc_date = datetime.now().date()

    print(f"\n{'='*60}")
    print(f"  Factor Interaction (XGBoost) + Explainable AI (SHAP)")
    print(f"  Date: {calc_date}")
    print(f"{'='*60}")

    if not _HAS_XGB:
        print("[XGB] ❌ xgboost 미설치 — pip install xgboost shap scikit-learn")
        return {"ok": 0, "error": "xgboost not installed"}

    _ensure_tables()

    # 일요일 = 재학습
    train_result = None
    if calc_date.weekday() == 6:  # Sunday
        print("\n── 주간 재학습 (일요일) ──")
        train_result = _train_model(calc_date)
    else:
        # 활성 모델 확인
        model, _ = _load_active_model()
        if model is None:
            print("\n── 활성 모델 없음 → 초기 학습 ──")
            train_result = _train_model(calc_date)

    # 추론 + SHAP
    print("\n── 일일 추론 + SHAP ──")
    pred_result = _predict_and_explain(calc_date)

    print(f"\n{'='*60}")
    print(f"  XGBoost + SHAP 완료")
    if train_result:
        print(f"  학습: AUC={train_result.get('train_auc')} (Valid={train_result.get('valid_auc')})")
    print(f"  추론: {pred_result.get('ok', 0)}/{pred_result.get('total', 0)}종목")
    print(f"{'='*60}")

    return {"train": train_result, "predict": pred_result}


run_all = run_xgboost


if __name__ == "__main__":
    import sys
    d = None
    if len(sys.argv) > 1:
        d = date.fromisoformat(sys.argv[1])
    run_xgboost(d)
