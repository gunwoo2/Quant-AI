"""
batch/batch_xgboost.py — XGBoost ML Engine v2.0
=================================================
Day 1~2 전면 교체 | 블루프린트 원칙 1,2,3 모두 적용

v1 → v2 핵심 변경:
  ★ Label v2: 4중 필터 (절대수익 + 초과수익 + 방향일관 + 상위30%)
  ★ Feature v2: 37개 (Leakage 제거 + 시계열/상호작용/횡단면/원시)
  ★ Train: 60일→252일, Purged Walk-Forward 5-Fold
  ★ Gatekeeper: OOS IC>0.02 AND AUC>0.52 → 통과해야 배포 (원칙 3)
  ★ Telemetry: 모든 학습/추론 결과 system_telemetry 기록 (원칙 1)

학술 참조:
  - Lopez de Prado (2018) "Purged K-Fold"
  - Chen & Guestrin (2016) "XGBoost"
  - Lundberg & Lee (2017) "SHAP"
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

logger = logging.getLogger("batch_xgboost")

try:
    import xgboost as xgb
    _HAS_XGB = True
except ImportError:
    _HAS_XGB = False
    print("[XGB] ⚠️ xgboost 미설치")

try:
    import shap
    _HAS_SHAP = True
except ImportError:
    _HAS_SHAP = False

try:
    from sklearn.metrics import roc_auc_score
    from scipy.stats import spearmanr
except ImportError:
    pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 상수 (v2)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MODEL_DIR = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) / "models"
MODEL_DIR.mkdir(exist_ok=True)

# ── v2 학습 파라미터 ──
TRAIN_DAYS          = 252      # 60→252 (1년, Bull+Bear 모두 경험)
PURGE_DAYS          = 15       # Label leakage 방지 (10d forward + 5d buffer)
EMBARGO_DAYS        = 5        # 추가 안전 마진
N_FOLDS             = 5        # Walk-Forward fold 수
MIN_OOS_IC          = 0.02     # Gatekeeper: OOS IC 최소 기준
MIN_OOS_AUC         = 0.52     # Gatekeeper: OOS AUC 최소 기준
MIN_TRAIN_SAMPLES   = 500      # 최소 학습 데이터
EARLY_STOPPING      = 30
AI_WEIGHT_DEFAULT   = 0.30

# ── v2 Label 설정 ──
LABEL_PRIMARY_HORIZON = 10     # 5→10일 (실제 보유기간 맞춤)
LABEL_MIN_ABSOLUTE    = 0.0    # 절대수익 > 0% (Bear market 필터)
LABEL_QUANTILE        = 0.70   # 상위 30% (20→30% 완화, 샘플 확보)

# ── v2 XGBoost 하이퍼파라미터 ──
XGB_PARAMS_V2 = {
    "objective":        "binary:logistic",
    "eval_metric":      "auc",
    "n_estimators":     500,
    "max_depth":        5,
    "learning_rate":    0.03,
    "subsample":        0.75,
    "colsample_bytree": 0.6,
    "min_child_weight": 30,
    "reg_alpha":        0.5,
    "reg_lambda":       2.0,
    "gamma":            0.1,
    "scale_pos_weight": 2.0,
    "random_state":     42,
    "n_jobs":           -1,
    "tree_method":      "hist",
}

# ── v2 Feature 정의 (37개, Leakage 제거) ──

# 서브팩터 원본 (10개) — layer1/2/3_score 제거!
FEATURE_CORE = [
    "moat_score", "value_score", "momentum_score", "stability_score",
    "news_score", "analyst_score", "insider_score",
    "section_a_tech", "section_b_flow", "section_c_macro",
]

# 매크로 컨텍스트 (5개)
FEATURE_CONTEXT = [
    "macro_score", "risk_appetite", "vix_close",
    "market_regime_num", "sector_code_num",
]

# 시계열 변화 (8개) — "추세" 포착
FEATURE_TEMPORAL = [
    "moat_delta_5d", "value_delta_5d", "momentum_delta_5d",
    "news_delta_3d", "tech_delta_5d",
    "score_velocity", "score_acceleration",
    "days_since_grade_change",
]

# 상호작용 (5개) — 비선형 조합
FEATURE_INTERACTION = [
    "value_x_momentum", "moat_x_stability",
    "news_x_insider", "tech_x_flow", "vix_x_risk_appetite",
]

# 횡단면 순위 (4개) — "섹터 내 위치"
FEATURE_CROSS_SECTION = [
    "sector_rank_pctile", "score_vs_sector_median",
    "score_zscore_all", "relative_strength_20d",
]

# 기술적 원시값 (5개)
FEATURE_TECHNICAL_RAW = [
    "rsi_14", "macd_histogram", "bb_pctb",
    "atr_pct", "volume_ratio_20d",
]

FEATURE_NAMES_V2 = (
    FEATURE_CORE + FEATURE_CONTEXT + FEATURE_TEMPORAL +
    FEATURE_INTERACTION + FEATURE_CROSS_SECTION + FEATURE_TECHNICAL_RAW
)

FEATURE_DISPLAY = {
    "moat_score": "경쟁우위", "value_score": "가치", "momentum_score": "모멘텀",
    "stability_score": "안정성", "news_score": "뉴스감성", "analyst_score": "애널리스트",
    "insider_score": "내부자", "section_a_tech": "기술지표", "section_b_flow": "수급",
    "section_c_macro": "시장환경", "macro_score": "매크로", "risk_appetite": "위험선호",
    "vix_close": "VIX", "market_regime_num": "시장국면", "sector_code_num": "업종",
    "moat_delta_5d": "경쟁우위변화5d", "value_delta_5d": "가치변화5d",
    "momentum_delta_5d": "모멘텀변화5d", "news_delta_3d": "뉴스변화3d",
    "tech_delta_5d": "기술변화5d", "score_velocity": "점수속도",
    "score_acceleration": "점수가속도", "days_since_grade_change": "등급변경후일수",
    "value_x_momentum": "가치*모멘텀", "moat_x_stability": "경쟁우위*안정성",
    "news_x_insider": "뉴스*내부자", "tech_x_flow": "기술*수급",
    "vix_x_risk_appetite": "VIX*위험선호",
    "sector_rank_pctile": "섹터내순위", "score_vs_sector_median": "섹터중앙대비",
    "score_zscore_all": "전체Z스코어", "relative_strength_20d": "상대강도20d",
    "rsi_14": "RSI14", "macd_histogram": "MACD히스토그램", "bb_pctb": "BB%B",
    "atr_pct": "ATR%", "volume_ratio_20d": "거래량비율20d",
}

REGIME_MAP = {"BULL": 2, "NEUTRAL": 1, "BEAR": 0, "CRISIS": -1}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 테이블 생성 (기존 호환 + 확장)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _ensure_tables():
    with get_cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ml_model_meta (
                id            SERIAL PRIMARY KEY,
                model_name    VARCHAR(50) DEFAULT 'xgb_v2',
                trained_date  DATE NOT NULL,
                train_samples INT,
                train_auc     NUMERIC(6,4),
                valid_auc     NUMERIC(6,4),
                oos_ic        NUMERIC(8,6),
                oos_auc       NUMERIC(8,6),
                feature_count INT,
                model_path    TEXT,
                is_active     BOOLEAN DEFAULT FALSE,
                notes         TEXT,
                created_at    TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        # oos_ic, oos_auc 컬럼 추가 (기존 테이블이면 ALTER)
        for col in ["oos_ic", "oos_auc"]:
            try:
                cur.execute(f"ALTER TABLE ml_model_meta ADD COLUMN IF NOT EXISTS {col} NUMERIC(8,6)")
            except Exception:
                pass

        cur.execute("""
            CREATE TABLE IF NOT EXISTS ai_scores_daily (
                id             SERIAL PRIMARY KEY,
                stock_id       INT NOT NULL,
                calc_date      DATE NOT NULL,
                ai_score       NUMERIC(6,2),
                ai_proba       NUMERIC(6,4),
                ensemble_score NUMERIC(6,2),
                stat_score     NUMERIC(6,2),
                ai_weight      NUMERIC(4,2),
                shap_top5_pos  JSONB,
                shap_top5_neg  JSONB,
                shap_all       JSONB,
                shap_base      NUMERIC(8,4),
                model_id       INT,
                updated_at     TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(stock_id, calc_date)
            )
        """)

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

        # Forward Returns 확장 (Multi-Horizon)
        for col_def in [
            "return_10d NUMERIC(10,6)",
            "return_20d NUMERIC(10,6)",
            "market_return_5d NUMERIC(10,6)",
            "market_return_10d NUMERIC(10,6)",
            "market_return_20d NUMERIC(10,6)",
            "excess_return_10d NUMERIC(10,6)",
            "label_v2 SMALLINT",
        ]:
            col_name = col_def.split()[0]
            try:
                cur.execute(f"ALTER TABLE forward_returns ADD COLUMN IF NOT EXISTS {col_def}")
            except Exception:
                pass

        cur.execute("CREATE INDEX IF NOT EXISTS idx_ai_scores_date ON ai_scores_daily(calc_date)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_ai_scores_stock ON ai_scores_daily(stock_id, calc_date)")

    print("[XGB-v2] ✅ 테이블 확인 완료")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Label v2: 4중 필터
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _create_labels_v2(returns_10d: np.ndarray, returns_5d: np.ndarray,
                      returns_20d: np.ndarray, market_return_10d: float) -> np.ndarray:
    """
    4중 필터 Label — "진짜 Alpha가 있는 종목만 1"

    필터 1: 절대수익 > 0       → Bear market 쓰레기 제거
    필터 2: 초과수익 > 0       → 시장보다 나은 종목만
    필터 3: 방향 일관성        → 5일/20일 방향 같아야
    필터 4: 상위 30%           → Cross-Sectional 순위

    결과: positive 비율이 시장 국면에 따라 가변 (Bear<5%, Bull 15~25%)
    """
    n = len(returns_10d)
    labels = np.zeros(n, dtype=int)

    # 필터 1: 절대수익 양수
    mask_absolute = returns_10d > LABEL_MIN_ABSOLUTE

    # 필터 2: 초과수익 양수
    excess = returns_10d - market_return_10d
    mask_excess = excess > 0

    # 필터 3: 5일과 20일 방향 일관성
    mask_direction = np.sign(returns_5d) == np.sign(returns_20d)

    # 결합
    combined = mask_absolute & mask_excess & mask_direction
    valid_excess = excess[combined]

    if len(valid_excess) == 0:
        # Bear market: 모든 종목 탈락 → 전원 label=0 (올바른 행동!)
        logger.info(f"[LABEL-v2] Bear market 감지: 모든 종목 label=0 (positive=0/{n})")
        return labels

    # 필터 4: 상위 30%
    threshold = np.percentile(valid_excess, (1 - LABEL_QUANTILE) * 100)
    mask_top = excess >= threshold

    labels = (combined & mask_top).astype(int)
    pos_rate = labels.sum() / max(n, 1)
    logger.info(f"[LABEL-v2] positive={labels.sum()}/{n} ({pos_rate:.1%}), "
                f"threshold={threshold:.4f}, mkt_ret={market_return_10d:.4f}")

    return labels


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Feature v2: 37개 빌더
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _build_features_v2(target_date: date, with_label: bool = False) -> tuple:
    """
    37개 Feature Matrix 구축 (v2).

    Returns: (stock_ids, X, y, dates_arr, feature_names)
    """
    macro = _get_macro_data(target_date)
    regime_num = macro.get("regime_num", 1)
    vix = macro.get("vix_close", 20.0)
    macro_score_val = macro.get("macro_score", 50.0)
    risk_app = macro.get("risk_appetite", 0.0)

    # ── 메인 쿼리: 서브팩터 + 기술적 원시값 ──
    label_select = ""
    label_join = ""
    label_where = ""
    if with_label:
        label_select = """
            , fr.return_5d AS fwd_ret_5d
            , fr.return_10d AS fwd_ret_10d
            , fr.return_20d AS fwd_ret_20d
            , fr.market_return_10d AS mkt_ret_10d
        """
        label_join = f"""
            LEFT JOIN LATERAL (
                SELECT return_5d, return_10d, return_20d, market_return_10d
                FROM forward_returns
                WHERE stock_id = s.stock_id AND calc_date = %s
            ) fr ON TRUE
        """
        label_where = "AND fr.return_10d IS NOT NULL"

    # 현재값 + 5일전값 조회 (시계열 delta 계산용)
    params = [target_date, target_date, target_date, target_date]
    if with_label:
        params.append(target_date)  # forward_returns calc_date

    # 5일 전 날짜 (시계열 delta용)
    prev_date = target_date - timedelta(days=7)  # 영업일 5일 ≈ 달력 7일

    with get_cursor() as cur:
        query = f"""
            SELECT
                s.stock_id,
                s.sector_code,
                -- 현재 L1 서브팩터 (4개)
                l1.moat_score, l1.value_score, l1.momentum_score, l1.stability_score,
                -- 현재 L2 서브팩터 (3개)
                l2.news_sentiment_score AS news_score,
                l2.analyst_rating_score AS analyst_score,
                l2.insider_signal_score AS insider_score,
                -- 현재 L3 서브팩터 (3개)
                ti.section_a_technical AS section_a_tech,
                ti.section_b_flow,
                ti.section_c_macro,
                -- 현재 종합점수 (시계열 delta용)
                sfs.weighted_score,
                sfs.current_grade,
                -- 5일전 서브팩터 (delta 계산용)
                l1_prev.moat_score AS moat_prev,
                l1_prev.value_score AS value_prev,
                l1_prev.momentum_score AS momentum_prev,
                l2_prev.news_sentiment_score AS news_prev,
                ti_prev.section_a_technical AS tech_prev,
                sfs_prev.weighted_score AS score_prev,
                -- 기술적 원시값 (5개)
                ti.rsi_14, ti.macd_histogram, ti.bb_pctb,
                ti.atr_pct, ti.volume_ratio_20d,
                -- 등급 변경 이력
                sfs.calc_date AS score_date
                {label_select}
            FROM stocks s
            LEFT JOIN LATERAL (
                SELECT moat_score, value_score, momentum_score, stability_score
                FROM stock_layer1_analysis
                WHERE stock_id = s.stock_id AND calc_date <= %s
                ORDER BY calc_date DESC LIMIT 1
            ) l1 ON TRUE
            LEFT JOIN LATERAL (
                SELECT news_sentiment_score, analyst_rating_score, insider_signal_score
                FROM layer2_scores
                WHERE stock_id = s.stock_id AND calc_date <= %s
                ORDER BY calc_date DESC LIMIT 1
            ) l2 ON TRUE
            LEFT JOIN LATERAL (
                SELECT section_a_technical, section_b_flow, section_c_macro,
                       rsi_14, macd_histogram, bb_pctb, atr_pct, volume_ratio_20d
                FROM technical_indicators
                WHERE stock_id = s.stock_id AND calc_date <= %s
                ORDER BY calc_date DESC LIMIT 1
            ) ti ON TRUE
            LEFT JOIN LATERAL (
                SELECT weighted_score, current_grade, calc_date
                FROM stock_final_scores
                WHERE stock_id = s.stock_id AND calc_date <= %s
                ORDER BY calc_date DESC LIMIT 1
            ) sfs ON TRUE
            -- 5일전 데이터 (시계열 delta)
            LEFT JOIN LATERAL (
                SELECT moat_score, value_score, momentum_score
                FROM stock_layer1_analysis
                WHERE stock_id = s.stock_id AND calc_date <= '{prev_date}'::date
                ORDER BY calc_date DESC LIMIT 1
            ) l1_prev ON TRUE
            LEFT JOIN LATERAL (
                SELECT news_sentiment_score
                FROM layer2_scores
                WHERE stock_id = s.stock_id AND calc_date <= '{prev_date}'::date
                ORDER BY calc_date DESC LIMIT 1
            ) l2_prev ON TRUE
            LEFT JOIN LATERAL (
                SELECT section_a_technical
                FROM technical_indicators
                WHERE stock_id = s.stock_id AND calc_date <= '{prev_date}'::date
                ORDER BY calc_date DESC LIMIT 1
            ) ti_prev ON TRUE
            LEFT JOIN LATERAL (
                SELECT weighted_score
                FROM stock_final_scores
                WHERE stock_id = s.stock_id AND calc_date <= '{prev_date}'::date
                ORDER BY calc_date DESC LIMIT 1
            ) sfs_prev ON TRUE
            {label_join}
            WHERE s.is_active = TRUE
              AND l1.moat_score IS NOT NULL
              {label_where}
        """
        cur.execute(query, tuple(params))
        rows = cur.fetchall()

    if not rows:
        return [], np.array([]), None, [], FEATURE_NAMES_V2

    _f = lambda v: float(v) if v is not None else np.nan
    _delta = lambda curr, prev: (_f(curr) - _f(prev)) if curr is not None and prev is not None else np.nan

    stock_ids = []
    features = []
    labels_5d, labels_10d, labels_20d, labels_mkt = [], [], [], []
    dates_arr = []

    for r in rows:
        # ── Core (10개) ──
        moat = _f(r.get("moat_score"))
        value = _f(r.get("value_score"))
        momentum = _f(r.get("momentum_score"))
        stability = _f(r.get("stability_score"))
        news = _f(r.get("news_score"))
        analyst = _f(r.get("analyst_score"))
        insider = _f(r.get("insider_score"))
        tech_a = _f(r.get("section_a_tech"))
        flow_b = _f(r.get("section_b_flow"))
        macro_c = _f(r.get("section_c_macro"))

        # ── Context (5개) ──
        ctx_macro = _f(macro_score_val)
        ctx_risk = _f(risk_app)
        ctx_vix = _f(vix)
        ctx_regime = float(regime_num)
        ctx_sector = float(r.get("sector_code", 0) or 0)

        # ── Temporal (8개) ──
        moat_d5 = _delta(r.get("moat_score"), r.get("moat_prev"))
        value_d5 = _delta(r.get("value_score"), r.get("value_prev"))
        mom_d5 = _delta(r.get("momentum_score"), r.get("momentum_prev"))
        news_d3 = _delta(r.get("news_score"), r.get("news_prev"))
        tech_d5 = _delta(r.get("section_a_tech"), r.get("tech_prev"))

        score_curr = _f(r.get("weighted_score"))
        score_prev = _f(r.get("score_prev"))
        velocity = (score_curr - score_prev) / 5.0 if not (np.isnan(score_curr) or np.isnan(score_prev)) else np.nan
        acceleration = np.nan  # 2차 미분은 추가 이력 필요 → 일단 NaN

        days_grade = 0  # 등급 변경 이후 일수 (추후 개선)

        # ── Interaction (5개) ──
        val_x_mom = (value * momentum / 100.0) if not (np.isnan(value) or np.isnan(momentum)) else np.nan
        moat_x_stab = (moat * stability / 100.0) if not (np.isnan(moat) or np.isnan(stability)) else np.nan
        news_x_ins = (news * insider / 100.0) if not (np.isnan(news) or np.isnan(insider)) else np.nan
        tech_x_flow = (tech_a * flow_b / 100.0) if not (np.isnan(tech_a) or np.isnan(flow_b)) else np.nan
        vix_x_risk = (ctx_vix * ctx_risk) if not (np.isnan(ctx_vix) or np.isnan(ctx_risk)) else np.nan

        # ── Cross-Section (4개) → 아래에서 벡터로 계산
        # 일단 placeholder, 벡터 연산 후 채움
        sect_rank = np.nan
        vs_median = np.nan
        zscore_all = np.nan
        rel_str_20d = np.nan

        # ── Technical Raw (5개) ──
        rsi = _f(r.get("rsi_14"))
        macd_hist = _f(r.get("macd_histogram"))
        bb_pctb = _f(r.get("bb_pctb"))
        atr_pct = _f(r.get("atr_pct"))
        vol_ratio = _f(r.get("volume_ratio_20d"))

        feat = [
            moat, value, momentum, stability, news, analyst, insider,
            tech_a, flow_b, macro_c,
            ctx_macro, ctx_risk, ctx_vix, ctx_regime, ctx_sector,
            moat_d5, value_d5, mom_d5, news_d3, tech_d5,
            velocity, acceleration, float(days_grade),
            val_x_mom, moat_x_stab, news_x_ins, tech_x_flow, vix_x_risk,
            sect_rank, vs_median, zscore_all, rel_str_20d,
            rsi, macd_hist, bb_pctb, atr_pct, vol_ratio,
        ]

        stock_ids.append(r["stock_id"])
        features.append(feat)
        dates_arr.append(target_date)

        if with_label:
            labels_5d.append(_f(r.get("fwd_ret_5d")))
            labels_10d.append(_f(r.get("fwd_ret_10d")))
            labels_20d.append(_f(r.get("fwd_ret_20d")))
            labels_mkt.append(_f(r.get("mkt_ret_10d")))

    X = np.array(features, dtype=np.float32)

    # ── Cross-Sectional Features 벡터 계산 ──
    if X.shape[0] > 0:
        # weighted_score 기반 (Core feature 0~9의 평균으로 대체)
        score_proxy = np.nanmean(X[:, 0:10], axis=1)

        # 섹터별 순위 백분율
        sectors = X[:, 14]  # sector_code_num
        for sec_val in np.unique(sectors):
            if np.isnan(sec_val):
                continue
            mask = sectors == sec_val
            sec_scores = score_proxy[mask]
            if len(sec_scores) > 1:
                ranks = np.argsort(np.argsort(-sec_scores)) / len(sec_scores) * 100
                X[mask, 28] = ranks.astype(np.float32)  # sector_rank_pctile
                median = np.nanmedian(sec_scores)
                X[mask, 29] = (sec_scores - median).astype(np.float32)  # vs_sector_median

        # 전체 Z-Score
        mean_all = np.nanmean(score_proxy)
        std_all = np.nanstd(score_proxy)
        if std_all > 0:
            X[:, 30] = ((score_proxy - mean_all) / std_all).astype(np.float32)

        # relative_strength_20d → score_velocity로 대체 (이미 있음)
        X[:, 31] = X[:, 20]  # velocity as proxy

    # NaN → 열 중앙값 대체
    for col in range(X.shape[1]):
        mask = np.isnan(X[:, col])
        if mask.any():
            median = np.nanmedian(X[:, col])
            X[mask, col] = median if not np.isnan(median) else 0.0

    # Label 생성 (v2: 4중 필터)
    y = None
    if with_label and labels_10d:
        ret_10d = np.array(labels_10d, dtype=np.float32)
        ret_5d = np.array(labels_5d, dtype=np.float32)
        ret_20d = np.array(labels_20d, dtype=np.float32)
        mkt_10d = np.nanmedian(labels_mkt) if labels_mkt else 0.0

        valid = ~(np.isnan(ret_10d) | np.isnan(ret_5d) | np.isnan(ret_20d))
        if valid.sum() > 50:
            y_all = np.zeros(len(ret_10d), dtype=int)
            y_valid = _create_labels_v2(ret_10d[valid], ret_5d[valid], ret_20d[valid], mkt_10d)
            y_all[valid] = y_valid
            y = y_all

            # 유효하지 않은 행 제거
            X = X[valid]
            stock_ids_arr = [stock_ids[i] for i in range(len(valid)) if valid[i]]
            dates_arr_f = [dates_arr[i] for i in range(len(valid)) if valid[i]]
            stock_ids = stock_ids_arr
            dates_arr = dates_arr_f
            y = y_valid

    return stock_ids, X, y, dates_arr, FEATURE_NAMES_V2


def _get_macro_data(target_date: date) -> dict:
    """매크로 데이터 조회 — ★ FIX: 올바른 컬럼명 사용"""
    result = {"regime_num": 1, "vix_close": 20.0, "macro_score": 50.0, "risk_appetite": 0.0}
    try:
        with get_cursor() as cur:
            # 국면
            cur.execute("""
                SELECT regime FROM market_regime
                WHERE regime_date <= %s ORDER BY regime_date DESC LIMIT 1
            """, (target_date,))
            row = cur.fetchone()
            if row:
                result["regime_num"] = REGIME_MAP.get(row["regime"], 1)

            # ★ FIX: cross_asset_total (not macro_score), risk_appetite_score (not risk_appetite)
            cur.execute("""
                SELECT cross_asset_total, risk_appetite_score
                FROM cross_asset_daily
                WHERE calc_date <= %s ORDER BY calc_date DESC LIMIT 1
            """, (target_date,))
            row = cur.fetchone()
            if row:
                if row.get("cross_asset_total"):
                    result["macro_score"] = float(row["cross_asset_total"])
                if row.get("risk_appetite_score"):
                    result["risk_appetite"] = float(row["risk_appetite_score"])

            # ★ FIX: VIX는 market_regime 테이블에서 조회
            cur.execute("""
                SELECT vix_close FROM market_regime
                WHERE regime_date <= %s ORDER BY regime_date DESC LIMIT 1
            """, (target_date,))
            row = cur.fetchone()
            if row and row.get("vix_close"):
                result["vix_close"] = float(row["vix_close"])

    except Exception as e:
        logger.warning(f"[XGB-v2] 매크로 조회 실패: {e}")
    return result


def _purged_walk_forward_splits(n_samples, n_folds, purge, embargo):
    """
    시간순 Purged Walk-Forward 분할.
    Expanding Window: 학습셋이 점점 커짐.
    """
    fold_size = n_samples // (n_folds + 1)
    splits = []
    for i in range(n_folds):
        test_start = fold_size * (i + 1)
        test_end = min(fold_size * (i + 2), n_samples)
        train_end = max(0, test_start - purge)
        embargo_start = min(test_end + embargo, n_samples)

        train_idx = list(range(0, train_end))
        test_idx = list(range(test_start, test_end))

        if len(train_idx) > 50 and len(test_idx) > 10:
            splits.append((np.array(train_idx), np.array(test_idx)))
    return splits


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 학습 v2 (Purged WF + Gatekeeper)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _train_model_v2(calc_date: date) -> dict:
    """
    v2 학습: 252일 + Purged Walk-Forward + Gatekeeper.

    원칙 3: OOS IC>0.02 AND AUC>0.52 통과해야만 배포.
    """
    print(f"\n[XGB-v2] === 모델 학습 시작 (v2) — {calc_date} ===")

    # 252일간 날짜별 데이터 수집
    all_stock_ids, all_X, all_y = [], None, None
    all_dates = []
    snapshot_dates = []

    end_date = calc_date - timedelta(days=LABEL_PRIMARY_HORIZON + 5)  # label 확정 가능한 날짜
    start_date = end_date - timedelta(days=int(TRAIN_DAYS * 1.5))  # 영업일 보정

    print(f"  학습 기간: {start_date} ~ {end_date} ({TRAIN_DAYS}영업일 목표)")

    d = start_date
    while d <= end_date:
        if d.weekday() >= 5:
            d += timedelta(days=1)
            continue

        ids, X, y, dates, _ = _build_features_v2(d, with_label=True)
        if y is not None and len(y) > 50:
            if all_X is None:
                all_X = X
                all_y = y
            else:
                all_X = np.vstack([all_X, X])
                all_y = np.concatenate([all_y, y])
            all_stock_ids.extend(ids)
            all_dates.extend(dates)
            snapshot_dates.append(d)

        d += timedelta(days=7)  # 주 1회 스냅샷

    if all_X is None or len(all_y) < MIN_TRAIN_SAMPLES:
        print(f"[XGB-v2] ❌ 데이터 부족: {len(all_y) if all_y is not None else 0} < {MIN_TRAIN_SAMPLES}")
        return {"status": "REJECTED", "reason": "insufficient_data"}

    print(f"  총 샘플: {len(all_y)}, positive: {int(all_y.sum())} ({all_y.mean():.1%})")
    print(f"  스냅샷: {len(snapshot_dates)}개, Features: {all_X.shape[1]}개")

    # ── Purged Walk-Forward CV ──
    folds = _purged_walk_forward_splits(len(all_y), N_FOLDS, PURGE_DAYS * 50, EMBARGO_DAYS * 50)
    # 50 = 대략 종목수/일

    oos_metrics = []
    best_model = None
    best_auc = 0

    for fold_i, (train_idx, test_idx) in enumerate(folds):
        model = xgb.XGBClassifier(**XGB_PARAMS_V2)
        model.fit(
            all_X[train_idx], all_y[train_idx],
            eval_set=[(all_X[test_idx], all_y[test_idx])],
            verbose=False,
        )

        proba = model.predict_proba(all_X[test_idx])[:, 1]
        try:
            oos_auc = round(roc_auc_score(all_y[test_idx], proba), 4)
        except Exception:
            oos_auc = 0.5
        try:
            oos_ic, _ = spearmanr(proba, all_y[test_idx])
            oos_ic = round(oos_ic, 4) if not np.isnan(oos_ic) else 0.0
        except Exception:
            oos_ic = 0.0

        oos_metrics.append({"fold": fold_i, "auc": oos_auc, "ic": oos_ic,
                            "train_n": len(train_idx), "test_n": len(test_idx)})
        print(f"  Fold {fold_i}: AUC={oos_auc}, IC={oos_ic}, train={len(train_idx)}, test={len(test_idx)}")

        if oos_auc > best_auc:
            best_auc = oos_auc
            best_model = model

    # ── Gatekeeper (원칙 3) ──
    avg_ic = round(np.mean([m["ic"] for m in oos_metrics]), 4)
    avg_auc = round(np.mean([m["auc"] for m in oos_metrics]), 4)

    print(f"\n  [GATEKEEPER] 평균 OOS IC={avg_ic}, AUC={avg_auc}")
    print(f"  [GATEKEEPER] 기준: IC>={MIN_OOS_IC}, AUC>={MIN_OOS_AUC}")

    # Gatekeeper 로그 기록
    try:
        with get_cursor() as cur:
            decision = "APPROVED" if (avg_ic >= MIN_OOS_IC and avg_auc >= MIN_OOS_AUC) else "REJECTED"
            reason = f"avg_ic={avg_ic}, avg_auc={avg_auc}, folds={len(oos_metrics)}"
            cur.execute("""
                INSERT INTO model_gatekeeper_log
                    (calc_date, model_type, oos_ic, oos_auc, decision, reason)
                VALUES (%s, 'xgb_v2', %s, %s, %s, %s)
            """, (calc_date, avg_ic, avg_auc, decision, reason))
    except Exception as e:
        logger.warning(f"[GATEKEEPER] 로그 실패: {e}")

    if avg_ic < MIN_OOS_IC or avg_auc < MIN_OOS_AUC:
        print(f"  [GATEKEEPER] ❌ 모델 거부! 이전 모델 유지.")
        # Telemetry
        _log_telemetry(calc_date, "MODEL", "train_rejected", avg_auc,
                       {"avg_ic": avg_ic, "avg_auc": avg_auc, "reason": "below_threshold"})
        return {"status": "REJECTED", "avg_ic": avg_ic, "avg_auc": avg_auc}

    print(f"  [GATEKEEPER] ✅ 모델 승인!")

    # ── 전체 데이터로 최종 모델 학습 ──
    final_model = xgb.XGBClassifier(**XGB_PARAMS_V2)
    final_model.fit(all_X, all_y, verbose=False)

    # 저장
    model_filename = f"xgb_v2_{calc_date.isoformat()}.pkl"
    model_path = str(MODEL_DIR / model_filename)
    joblib.dump(final_model, model_path)
    print(f"  모델 저장: {model_path}")

    # DB 메타 저장
    with get_cursor() as cur:
        cur.execute("UPDATE ml_model_meta SET is_active = FALSE WHERE is_active = TRUE")
        cur.execute("""
            INSERT INTO ml_model_meta
                (model_name, trained_date, train_samples, train_auc, valid_auc,
                 oos_ic, oos_auc, feature_count, model_path, is_active, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s)
            RETURNING id
        """, (
            "xgb_v2", calc_date, all_X.shape[0], avg_auc, avg_auc,
            avg_ic, avg_auc, len(FEATURE_NAMES_V2), model_path,
            f"v2_purged_wf, snapshots={len(snapshot_dates)}, folds={len(oos_metrics)}",
        ))
        model_id = cur.fetchone()["id"]

    # Feature Importance 저장
    importances = final_model.feature_importances_
    sorted_idx = np.argsort(importances)[::-1]
    print(f"\n  Feature Importance TOP 10:")
    with get_cursor() as cur:
        for rank, idx in enumerate(sorted_idx, 1):
            if idx < len(FEATURE_NAMES_V2):
                fname = FEATURE_NAMES_V2[idx]
                imp = round(float(importances[idx]), 6)
                if rank <= 10:
                    print(f"    {rank:2d}. {FEATURE_DISPLAY.get(fname, fname):20s}  {imp:.4f}")
                cur.execute("""
                    INSERT INTO xgb_feature_importance (model_id, feature_name, importance, rank)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (model_id, feature_name) DO UPDATE SET
                        importance = EXCLUDED.importance, rank = EXCLUDED.rank
                """, (model_id, fname, imp, rank))

    # Telemetry
    _log_telemetry(calc_date, "MODEL", "train_approved", avg_auc,
                   {"avg_ic": avg_ic, "avg_auc": avg_auc, "samples": all_X.shape[0],
                    "features": len(FEATURE_NAMES_V2), "folds": len(oos_metrics)})

    return {
        "status": "APPROVED", "model_id": model_id,
        "avg_ic": avg_ic, "avg_auc": avg_auc,
        "train_samples": all_X.shape[0], "model_path": model_path,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 추론 + SHAP (기존 호환, v2 feature 사용)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _load_active_model():
    """활성 모델 로드"""
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT id, model_path, feature_count FROM ml_model_meta
                WHERE is_active = TRUE
                ORDER BY trained_date DESC LIMIT 1
            """)
            row = cur.fetchone()
        if row and row["model_path"] and os.path.exists(row["model_path"]):
            model = joblib.load(row["model_path"])
            return model, row["id"], row.get("feature_count", 18)
    except Exception as e:
        logger.warning(f"[XGB-v2] 모델 로드 실패: {e}")
    return None, None, 18


def _predict_and_explain(calc_date: date) -> dict:
    """일일 추론 + SHAP + 앙상블 저장"""
    model, model_id, feat_count = _load_active_model()
    if model is None:
        print("[XGB-v2] ⚠️ 활성 모델 없음 — 추론 건너뜀")
        return {"error": "no_active_model"}

    # Feature 수에 따라 v1 or v2 빌더 사용
    if feat_count > 20:
        stock_ids, X, _, _, feature_names = _build_features_v2(calc_date, with_label=False)
    else:
        # v1 호환 (기존 모델이 아직 활성인 경우)
        stock_ids, X, _, feature_names = _build_features_v1(calc_date)

    if len(stock_ids) == 0:
        print("[XGB-v2] ⚠️ Feature 데이터 없음")
        return {"error": "no_data"}

    probas = model.predict_proba(X)[:, 1]
    ai_scores = np.round(probas * 100, 2)

    # AI Weight (기존 호환)
    ai_weight = _get_ai_weight()

    # SHAP (비용이 크므로 선택적)
    shap_values_all = None
    base_value = None
    if _HAS_SHAP:
        try:
            explainer = shap.TreeExplainer(model)
            shap_obj = explainer(X[:min(100, len(X))])
            shap_values_all = shap_obj.values
            base_value = float(shap_obj.base_values[0]) if hasattr(shap_obj, 'base_values') else None
        except Exception as e:
            logger.warning(f"[XGB-v2] SHAP 실패: {e}")

    # DB 저장
    saved = 0
    with get_cursor() as cur:
        for i, stock_id in enumerate(stock_ids):
            ai_s = float(ai_scores[i])
            stat_s = _get_stat_score(cur, stock_id, calc_date)
            ens = round(stat_s * (1 - ai_weight) + ai_s * ai_weight, 2) if stat_s else ai_s

            # SHAP 데이터
            shap_data = _build_shap_data(i, shap_values_all, base_value, feature_names)

            try:
                cur.execute("""
                    INSERT INTO ai_scores_daily
                        (stock_id, calc_date, ai_score, ai_proba, ensemble_score,
                         stat_score, ai_weight, shap_top5_pos, shap_top5_neg,
                         shap_all, shap_base, model_id, updated_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
                    ON CONFLICT (stock_id, calc_date) DO UPDATE SET
                        ai_score=EXCLUDED.ai_score, ai_proba=EXCLUDED.ai_proba,
                        ensemble_score=EXCLUDED.ensemble_score, stat_score=EXCLUDED.stat_score,
                        ai_weight=EXCLUDED.ai_weight, shap_top5_pos=EXCLUDED.shap_top5_pos,
                        shap_top5_neg=EXCLUDED.shap_top5_neg, shap_all=EXCLUDED.shap_all,
                        shap_base=EXCLUDED.shap_base, model_id=EXCLUDED.model_id,
                        updated_at=NOW()
                """, (
                    stock_id, calc_date, ai_s, round(float(probas[i]), 4), ens,
                    stat_s, ai_weight,
                    json.dumps(shap_data.get("top5_pos", []), ensure_ascii=False),
                    json.dumps(shap_data.get("top5_neg", []), ensure_ascii=False),
                    json.dumps(shap_data.get("all", {})),
                    shap_data.get("base"), model_id,
                ))
                saved += 1
            except Exception as e:
                if saved < 3:
                    logger.warning(f"  [ERR] stock_id={stock_id}: {e}")

    print(f"[XGB-v2] ✅ 추론+SHAP 저장: {saved}/{len(stock_ids)} (weight={ai_weight})")

    _log_telemetry(calc_date, "MODEL", "inference", saved,
                   {"total": len(stock_ids), "ai_weight": ai_weight, "model_id": model_id})

    return {"ok": saved, "total": len(stock_ids), "ai_weight": ai_weight}


def _build_features_v1(target_date):
    """v1 호환 Feature 빌더 (기존 모델용 Fallback)"""
    macro = _get_macro_data(target_date)
    FEATURE_NAMES_V1 = [
        "layer1_score", "layer2_score", "layer3_score",
        "moat_score", "value_score", "momentum_score", "stability_score",
        "news_score", "analyst_score", "insider_score",
        "section_a_tech", "section_b_flow", "section_c_macro",
        "macro_score", "risk_appetite", "vix_close",
        "market_regime_num", "sector_code_num",
    ]
    with get_cursor() as cur:
        cur.execute("""
            SELECT s.stock_id, s.sector_code,
                   sfs.weighted_score, sfs.layer1_score, sfs.layer2_score, sfs.layer3_score,
                   l1.moat_score, l1.value_score, l1.momentum_score, l1.stability_score,
                   l2.news_sentiment_score AS news_score, l2.analyst_rating_score AS analyst_score,
                   l2.insider_signal_score AS insider_score,
                   ti.section_a_technical AS section_a_tech, ti.section_b_flow, ti.section_c_macro
            FROM stocks s
            LEFT JOIN LATERAL (SELECT * FROM stock_final_scores WHERE stock_id=s.stock_id AND calc_date<=%s ORDER BY calc_date DESC LIMIT 1) sfs ON TRUE
            LEFT JOIN LATERAL (SELECT * FROM stock_layer1_analysis WHERE stock_id=s.stock_id AND calc_date<=%s ORDER BY calc_date DESC LIMIT 1) l1 ON TRUE
            LEFT JOIN LATERAL (SELECT * FROM layer2_scores WHERE stock_id=s.stock_id AND calc_date<=%s ORDER BY calc_date DESC LIMIT 1) l2 ON TRUE
            LEFT JOIN LATERAL (SELECT * FROM technical_indicators WHERE stock_id=s.stock_id AND calc_date<=%s ORDER BY calc_date DESC LIMIT 1) ti ON TRUE
            WHERE s.is_active = TRUE AND sfs.weighted_score IS NOT NULL
        """, (target_date, target_date, target_date, target_date))
        rows = cur.fetchall()
    if not rows:
        return [], np.array([]), None, FEATURE_NAMES_V1
    _f = lambda v: float(v) if v is not None else np.nan
    stock_ids, features = [], []
    for r in rows:
        feat = [_f(r.get("layer1_score")), _f(r.get("layer2_score")), _f(r.get("layer3_score")),
                _f(r.get("moat_score")), _f(r.get("value_score")), _f(r.get("momentum_score")), _f(r.get("stability_score")),
                _f(r.get("news_score")), _f(r.get("analyst_score")), _f(r.get("insider_score")),
                _f(r.get("section_a_tech")), _f(r.get("section_b_flow")), _f(r.get("section_c_macro")),
                _f(macro.get("macro_score")), _f(macro.get("risk_appetite")), _f(macro.get("vix_close")),
                float(macro.get("regime_num", 1)), float(r.get("sector_code", 0) or 0)]
        stock_ids.append(r["stock_id"])
        features.append(feat)
    X = np.array(features, dtype=np.float32)
    for col in range(X.shape[1]):
        mask = np.isnan(X[:, col])
        if mask.any():
            med = np.nanmedian(X[:, col])
            X[mask, col] = med if not np.isnan(med) else 0.0
    return stock_ids, X, None, FEATURE_NAMES_V1


def _get_stat_score(cur, stock_id, calc_date):
    """통계 점수 조회"""
    try:
        cur.execute("""
            SELECT weighted_score FROM stock_final_scores
            WHERE stock_id=%s AND calc_date<=%s ORDER BY calc_date DESC LIMIT 1
        """, (stock_id, calc_date))
        row = cur.fetchone()
        return round(float(row["weighted_score"]), 2) if row and row["weighted_score"] else None
    except:
        return None


def _build_shap_data(i, shap_values_all, base_value, feature_names):
    """SHAP 데이터 정리"""
    if shap_values_all is None or i >= len(shap_values_all):
        return {"top5_pos": [], "top5_neg": [], "all": {}, "base": None}
    sv = shap_values_all[i]
    pairs = [(feature_names[j] if j < len(feature_names) else f"f{j}",
              round(float(sv[j]), 4)) for j in range(len(sv))]
    pairs.sort(key=lambda x: x[1], reverse=True)
    return {
        "top5_pos": [{"feature": n, "display": FEATURE_DISPLAY.get(n, n), "shap": v}
                     for n, v in pairs[:5] if v > 0],
        "top5_neg": [{"feature": n, "display": FEATURE_DISPLAY.get(n, n), "shap": v}
                     for n, v in pairs[-5:] if v < 0],
        "all": {n: v for n, v in pairs},
        "base": round(float(base_value), 4) if base_value else None,
    }


def _get_ai_weight() -> float:
    """AI 앙상블 비중 조회"""
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT avg_ic_l1 AS ic_stat, ic_total AS ic_ai
                FROM factor_weights_monthly ORDER BY month DESC LIMIT 1
            """)
            row = cur.fetchone()
            if row and row.get("ic_ai") and row.get("ic_stat"):
                ic_ai = float(row["ic_ai"])
                ic_stat = float(row["ic_stat"])
                if ic_ai > ic_stat * 1.2:
                    return min(0.50, AI_WEIGHT_DEFAULT + 0.10)
                elif ic_ai < ic_stat * 0.5:
                    return max(0.10, AI_WEIGHT_DEFAULT - 0.10)
    except:
        pass
    return AI_WEIGHT_DEFAULT


def _log_telemetry(calc_date, category, metric_name, metric_value, detail=None):
    """system_telemetry에 기록"""
    try:
        with get_cursor() as cur:
            cur.execute("""
                INSERT INTO system_telemetry (calc_date, category, metric_name, metric_value, detail)
                VALUES (%s, %s, %s, %s, %s)
            """, (calc_date, category, metric_name, metric_value,
                  json.dumps(detail, ensure_ascii=False) if detail else None))
    except Exception as e:
        logger.warning(f"[TELEMETRY] 기록 실패: {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 공개 API (기존 호환)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_stock_explanation(stock_id: int, calc_date: date = None) -> dict:
    """종목별 SHAP 설명 조회 (API 엔드포인트용)"""
    if calc_date is None:
        calc_date = datetime.now().date()
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT ai_score, shap_base, shap_top5_pos, shap_top5_neg, shap_all,
                       ensemble_score, stat_score, ai_weight
                FROM ai_scores_daily
                WHERE stock_id=%s AND calc_date<=%s ORDER BY calc_date DESC LIMIT 1
            """, (stock_id, calc_date))
            row = cur.fetchone()
            if row:
                return {
                    "ai_score": float(row["ai_score"]) if row["ai_score"] else None,
                    "ensemble_score": float(row["ensemble_score"]) if row["ensemble_score"] else None,
                    "stat_score": float(row["stat_score"]) if row["stat_score"] else None,
                    "ai_weight": float(row["ai_weight"]) if row["ai_weight"] else None,
                    "base_value": float(row["shap_base"]) if row["shap_base"] else None,
                    "top_positive": row["shap_top5_pos"] or [],
                    "top_negative": row["shap_top5_neg"] or [],
                    "all_shap": row["shap_all"] or {},
                }
    except:
        pass
    return {"ai_score": None, "top_positive": [], "top_negative": []}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 메인 실행
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run_xgboost(calc_date: date = None):
    """
    scheduler.py Step 6.3에서 호출.

    1. 테이블 확인
    2. 일요일이면 학습 (v2: Purged WF + Gatekeeper)
    3. 매일 추론 + SHAP + 앙상블 저장
    """
    if not _HAS_XGB:
        return {"error": "xgboost not installed"}

    if calc_date is None:
        calc_date = datetime.now().date()

    _ensure_tables()

    # 학습 판단: 일요일 OR 활성 모델 없음
    model, model_id, _ = _load_active_model()
    should_train = (calc_date.weekday() == 6) or (model is None)

    if should_train:
        train_result = _train_model_v2(calc_date)
        if train_result.get("status") == "REJECTED" and model is None:
            print("[XGB-v2] ⚠️ 학습 거부 + 기존 모델 없음 → 추론 불가")
            return train_result
    else:
        train_result = None

    # 추론
    infer_result = _predict_and_explain(calc_date)

    return {
        "train": train_result,
        "inference": infer_result,
    }


# 하위 호환 alias
run_all = run_xgboost