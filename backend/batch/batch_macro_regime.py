"""
batch/batch_macro_regime.py — HMM 6-State Macro Regime Classifier v1.0
=======================================================================
Day 3 신규 | 설계 원칙 2 "Degrade Gracefully" — HMM 미학습시 룰 기반 Fallback

Cross-Asset 8개 파생지표 → HMM → 6개 시장 국면 확률분포 → macro_score

6개 State:
  RISK_ON_RALLY   (+1.0) — 강세 질주, VIX 낮음, 위험자산 강세
  GOLDILOCKS      (+0.7) — 적당한 성장, 낮은 변동성
  REFLATION       (+0.3) — 성장+인플레, 원자재 강세
  STAGFLATION     (-0.4) — 둔화+인플레, 방어적
  DEFLATION_SCARE (-0.7) — 디플레 공포, 안전자산 강세
  CRISIS          (-1.0) — 전면 위기, VIX 급등

학습: 최소 200일 Cross-Asset 이력, 월 1회 재학습
출력: macro_regime_daily 테이블 + system_telemetry 기록
Fallback: HMM 미학습시 VIX+Risk Appetite 룰 기반 (원칙 2)

실행: scheduler.py Step 5.5 | 소요: ~2초 | 비용: $0
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

logger = logging.getLogger("batch_macro_regime")

try:
    from hmmlearn.hmm import GaussianHMM
    _HAS_HMM = True
except ImportError:
    _HAS_HMM = False
    logger.warning("[REGIME] hmmlearn 미설치 — pip install hmmlearn (Fallback 모드 동작)")

try:
    from sklearn.preprocessing import StandardScaler
    _HAS_SK = True
except ImportError:
    _HAS_SK = False

MODEL_DIR = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) / "models"
MODEL_DIR.mkdir(exist_ok=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 상수
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

N_STATES = 6
MIN_TRAIN_DAYS = 200       # HMM 학습 최소 일수
RETRAIN_INTERVAL = 30      # 재학습 주기 (일)

REGIME_NAMES = [
    "RISK_ON_RALLY", "GOLDILOCKS", "REFLATION",
    "STAGFLATION", "DEFLATION_SCARE", "CRISIS"
]

# 주식 시장에 대한 국면별 영향도 (-1.0 ~ +1.0)
EQUITY_IMPACT = {
    "RISK_ON_RALLY":   +1.0,
    "GOLDILOCKS":      +0.7,
    "REFLATION":       +0.3,
    "STAGFLATION":     -0.4,
    "DEFLATION_SCARE": -0.7,
    "CRISIS":          -1.0,
}

# 국면별 레이어 가중치 조정 (batch_final_score.py에서 사용)
REGIME_WEIGHT_PROFILES = {
    #                    L1     L2     L3     L4(macro)
    "RISK_ON_RALLY":   {"L1": 0.35, "L2": 0.25, "L3": 0.30, "L4": 0.10},
    "GOLDILOCKS":      {"L1": 0.40, "L2": 0.20, "L3": 0.30, "L4": 0.10},
    "REFLATION":       {"L1": 0.45, "L2": 0.20, "L3": 0.25, "L4": 0.10},
    "STAGFLATION":     {"L1": 0.55, "L2": 0.15, "L3": 0.15, "L4": 0.15},
    "DEFLATION_SCARE": {"L1": 0.55, "L2": 0.15, "L3": 0.10, "L4": 0.20},
    "CRISIS":          {"L1": 0.60, "L2": 0.10, "L3": 0.10, "L4": 0.20},
}

# HMM 입력 Feature (cross_asset_daily 컬럼)
HMM_FEATURES = [
    "risk_appetite_idx", "spread_momentum", "safe_haven_momentum",
    "dollar_momentum", "global_growth_momentum", "small_large_ratio",
    "copper_gold_ratio", "hy_spread_proxy",
]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 테이블 생성
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _ensure_tables():
    with get_cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS macro_regime_daily (
                id               SERIAL PRIMARY KEY,
                calc_date        DATE NOT NULL UNIQUE,
                dominant_regime  VARCHAR(30),
                regime_probs     JSONB,
                macro_score      NUMERIC(6,2),
                confidence       NUMERIC(6,4),
                equity_impact    NUMERIC(4,2),
                is_fallback      BOOLEAN DEFAULT FALSE,
                hmm_model_date   DATE,
                detail           JSONB,
                created_at       TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_regime_date
            ON macro_regime_daily(calc_date DESC)
        """)
    print("[REGIME] ✅ macro_regime_daily 테이블 확인")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HMM 학습
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _load_cross_asset_history(calc_date, lookback_days=400):
    """cross_asset_daily에서 HMM 학습 데이터 로드"""
    with get_cursor() as cur:
        cols = ", ".join(HMM_FEATURES)
        cur.execute(f"""
            SELECT calc_date, {cols}
            FROM cross_asset_daily
            WHERE calc_date <= %s
              AND calc_date >= %s - INTERVAL '{lookback_days} days'
            ORDER BY calc_date ASC
        """, (calc_date, calc_date))
        rows = cur.fetchall()

    if not rows:
        return None, None

    dates = [r["calc_date"] for r in rows]
    data = []
    for r in rows:
        vals = [float(r[f]) if r[f] is not None else np.nan for f in HMM_FEATURES]
        data.append(vals)

    X = np.array(data, dtype=np.float64)

    # NaN 행 제거
    valid_mask = ~np.any(np.isnan(X), axis=1)
    X = X[valid_mask]
    dates = [d for d, v in zip(dates, valid_mask) if v]

    return X, dates


def _train_hmm(calc_date):
    """HMM 모델 학습"""
    if not _HAS_HMM or not _HAS_SK:
        logger.warning("[REGIME] hmmlearn/sklearn 미설치 → Fallback 모드")
        return None

    X, dates = _load_cross_asset_history(calc_date)
    if X is None or len(X) < MIN_TRAIN_DAYS:
        logger.warning(f"[REGIME] 데이터 부족: {len(X) if X is not None else 0} < {MIN_TRAIN_DAYS}")
        return None

    print(f"  [REGIME] HMM 학습 데이터: {len(X)}일, Features: {X.shape[1]}개")

    # 스케일링
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # HMM 학습 (여러 번 시도, 최적 선택)
    best_model = None
    best_score = -np.inf

    for seed in [42, 123, 456]:
        try:
            hmm = GaussianHMM(
                n_components=N_STATES, covariance_type="full",
                n_iter=300, random_state=seed, tol=0.01,
            )
            hmm.fit(X_scaled)
            score = hmm.score(X_scaled)

            if score > best_score:
                best_score = score
                best_model = hmm
        except Exception as e:
            logger.warning(f"[REGIME] HMM seed={seed} 실패: {e}")

    if best_model is None:
        logger.warning("[REGIME] HMM 학습 전부 실패 → Fallback 모드")
        return None

    # State → Regime 이름 매핑 (State별 평균 risk_appetite으로 정렬)
    state_means = best_model.means_[:, 0]  # risk_appetite_idx 기준
    sorted_states = np.argsort(state_means)  # 낮은→높은

    # 매핑: 가장 낮은 risk_appetite = CRISIS, 가장 높은 = RISK_ON_RALLY
    state_to_regime = {}
    regime_order = ["CRISIS", "DEFLATION_SCARE", "STAGFLATION",
                    "REFLATION", "GOLDILOCKS", "RISK_ON_RALLY"]
    for i, state_idx in enumerate(sorted_states):
        state_to_regime[int(state_idx)] = regime_order[i]

    # 모델 저장
    model_path = str(MODEL_DIR / f"hmm_regime_{calc_date.isoformat()}.pkl")
    joblib.dump({
        "hmm": best_model,
        "scaler": scaler,
        "state_to_regime": state_to_regime,
        "train_date": calc_date,
        "train_days": len(X),
        "log_likelihood": float(best_score),
    }, model_path)

    print(f"  [REGIME] HMM 학습 완료: score={best_score:.1f}, states={N_STATES}")
    print(f"  [REGIME] State 매핑: {state_to_regime}")

    return model_path


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HMM 예측
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _predict_regime(calc_date, model_path=None):
    """오늘의 매크로 지표 → 국면 확률 분포 + 매크로 점수"""

    # 오늘의 Cross-Asset 지표 조회
    today_data = _get_today_indicators(calc_date)
    if today_data is None:
        return _fallback_prediction(calc_date, reason="no_today_data")

    # 모델 로드
    if model_path is None:
        model_path = _find_latest_model()

    if model_path is None or not os.path.exists(model_path):
        return _fallback_prediction(calc_date, reason="no_model", indicators=today_data)

    try:
        model_data = joblib.load(model_path)
        hmm = model_data["hmm"]
        scaler = model_data["scaler"]
        state_to_regime = model_data["state_to_regime"]
        train_date = model_data.get("train_date")
    except Exception as e:
        logger.warning(f"[REGIME] 모델 로드 실패: {e}")
        return _fallback_prediction(calc_date, reason=f"load_error: {e}", indicators=today_data)

    # 예측
    X = np.array([[today_data.get(f, 0) for f in HMM_FEATURES]], dtype=np.float64)
    X_scaled = scaler.transform(X)

    try:
        probs = hmm.predict_proba(X_scaled)[0]
    except Exception as e:
        logger.warning(f"[REGIME] 예측 실패: {e}")
        return _fallback_prediction(calc_date, reason=f"predict_error: {e}", indicators=today_data)

    # State → Regime 매핑
    regime_probs = {}
    for state_idx in range(N_STATES):
        regime_name = state_to_regime.get(state_idx, f"STATE_{state_idx}")
        regime_probs[regime_name] = round(float(probs[state_idx]), 4)

    # 확률 가중 매크로 점수 (-10 ~ +10)
    macro_score = sum(
        regime_probs.get(name, 0) * EQUITY_IMPACT.get(name, 0) * 10
        for name in REGIME_NAMES
    )

    dominant = max(regime_probs, key=regime_probs.get)
    confidence = regime_probs[dominant]

    return {
        "dominant_regime": dominant,
        "regime_probs": regime_probs,
        "macro_score": round(macro_score, 2),
        "confidence": round(confidence, 4),
        "equity_impact": EQUITY_IMPACT.get(dominant, 0),
        "is_fallback": False,
        "hmm_model_date": train_date,
    }


def _get_today_indicators(calc_date):
    """오늘의 Cross-Asset 파생지표 조회"""
    try:
        with get_cursor() as cur:
            cols = ", ".join(HMM_FEATURES)
            cur.execute(f"""
                SELECT {cols}, vix_close, spy_close
                FROM cross_asset_daily
                WHERE calc_date <= %s
                ORDER BY calc_date DESC LIMIT 1
            """, (calc_date,))
            row = cur.fetchone()

        if not row:
            return None

        result = {}
        for f in HMM_FEATURES:
            result[f] = float(row[f]) if row[f] is not None else 0.0
        result["vix_close"] = float(row["vix_close"]) if row.get("vix_close") else 20.0
        result["spy_close"] = float(row["spy_close"]) if row.get("spy_close") else 0.0
        return result

    except Exception as e:
        logger.warning(f"[REGIME] 지표 조회 실패: {e}")
        return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Fallback (원칙 2: Graceful Degradation)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _fallback_prediction(calc_date, reason="unknown", indicators=None):
    """
    HMM 사용 불가시 룰 기반 Fallback.
    VIX + Risk Appetite으로 단순 분류.
    """
    vix = 20.0
    ra = 0.0
    if indicators:
        vix = indicators.get("vix_close", 20.0)
        ra = indicators.get("risk_appetite_idx", 0.0)

    # 단순 룰 기반 분류
    if vix > 35:
        regime = "CRISIS"
    elif vix > 28 or ra < -1.5:
        regime = "DEFLATION_SCARE"
    elif ra < -0.5:
        regime = "STAGFLATION"
    elif ra > 1.5:
        regime = "RISK_ON_RALLY"
    elif ra > 0.5:
        regime = "GOLDILOCKS"
    else:
        regime = "REFLATION"

    macro_score = EQUITY_IMPACT[regime] * 10

    print(f"  [REGIME] ⚠️ Fallback 모드: {reason}")
    print(f"  [REGIME] VIX={vix:.1f}, RA={ra:.2f} → {regime} (score={macro_score})")

    return {
        "dominant_regime": regime,
        "regime_probs": {regime: 1.0},
        "macro_score": round(macro_score, 2),
        "confidence": 0.5,  # Fallback이므로 낮은 확신도
        "equity_impact": EQUITY_IMPACT[regime],
        "is_fallback": True,
        "hmm_model_date": None,
        "fallback_reason": reason,
    }


def _find_latest_model():
    """최신 HMM 모델 파일 찾기"""
    models = sorted(MODEL_DIR.glob("hmm_regime_*.pkl"), reverse=True)
    if models:
        return str(models[0])
    return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DB 저장
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _save_regime(calc_date, result):
    """macro_regime_daily에 저장"""
    try:
        with get_cursor() as cur:
            cur.execute("""
                INSERT INTO macro_regime_daily
                    (calc_date, dominant_regime, regime_probs, macro_score,
                     confidence, equity_impact, is_fallback, hmm_model_date, detail)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (calc_date) DO UPDATE SET
                    dominant_regime = EXCLUDED.dominant_regime,
                    regime_probs = EXCLUDED.regime_probs,
                    macro_score = EXCLUDED.macro_score,
                    confidence = EXCLUDED.confidence,
                    equity_impact = EXCLUDED.equity_impact,
                    is_fallback = EXCLUDED.is_fallback,
                    hmm_model_date = EXCLUDED.hmm_model_date,
                    detail = EXCLUDED.detail,
                    created_at = NOW()
            """, (
                calc_date, result["dominant_regime"],
                json.dumps(result.get("regime_probs", {})),
                result["macro_score"], result["confidence"],
                result["equity_impact"], result.get("is_fallback", False),
                result.get("hmm_model_date"),
                json.dumps({k: v for k, v in result.items()
                           if k not in ("regime_probs",)}, default=str),
            ))
    except Exception as e:
        logger.error(f"[REGIME] DB 저장 실패: {e}")


def _log_telemetry(calc_date, metric_name, metric_value, detail=None):
    """system_telemetry 기록"""
    try:
        with get_cursor() as cur:
            cur.execute("""
                INSERT INTO system_telemetry (calc_date, category, metric_name, metric_value, detail)
                VALUES (%s, 'REGIME', %s, %s, %s)
            """, (calc_date, metric_name, metric_value,
                  json.dumps(detail, ensure_ascii=False, default=str) if detail else None))
    except Exception as e:
        logger.debug(f"[TELEMETRY] 기록 실패 (테이블 미생성?): {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 공개 API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_current_regime(calc_date=None):
    """현재 Regime 조회 (다른 모듈에서 호출)"""
    if calc_date is None:
        calc_date = date.today()
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT dominant_regime, macro_score, confidence,
                       equity_impact, regime_probs, is_fallback
                FROM macro_regime_daily
                WHERE calc_date <= %s
                ORDER BY calc_date DESC LIMIT 1
            """, (calc_date,))
            row = cur.fetchone()
            if row:
                return {
                    "dominant_regime": row["dominant_regime"],
                    "macro_score": float(row["macro_score"]) if row["macro_score"] else 0,
                    "confidence": float(row["confidence"]) if row["confidence"] else 0.5,
                    "equity_impact": float(row["equity_impact"]) if row["equity_impact"] else 0,
                    "regime_probs": row["regime_probs"] or {},
                    "is_fallback": row["is_fallback"],
                }
    except Exception as e:
        logger.warning(f"[REGIME] 조회 실패: {e}")
    return {"dominant_regime": "GOLDILOCKS", "macro_score": 7.0,
            "confidence": 0.5, "equity_impact": 0.7, "is_fallback": True}


def get_regime_weight_profile(regime_name=None, calc_date=None):
    """Regime별 레이어 가중치 프로필 반환 (batch_final_score에서 호출)"""
    if regime_name is None:
        current = get_current_regime(calc_date)
        regime_name = current["dominant_regime"]
    return REGIME_WEIGHT_PROFILES.get(regime_name,
                                       REGIME_WEIGHT_PROFILES["GOLDILOCKS"])


def run_macro_regime(calc_date=None):
    """
    scheduler.py Step 5.5에서 호출.

    1. 테이블 확인
    2. 재학습 필요 여부 판단 (매월 1일 or 모델 없음)
    3. 오늘 Regime 예측 (HMM or Fallback)
    4. DB 저장 + Telemetry
    """
    if calc_date is None:
        calc_date = date.today()

    print(f"\n[REGIME] === Macro Regime Classifier — {calc_date} ===")
    _ensure_tables()

    # 재학습 판단
    latest_model = _find_latest_model()
    should_train = False

    if latest_model is None:
        should_train = True
        print("  [REGIME] 기존 모델 없음 → 학습 시도")
    elif calc_date.day <= 3:  # 매월 초 재학습
        should_train = True
        print("  [REGIME] 월간 재학습")

    model_path = latest_model
    if should_train and _HAS_HMM:
        new_path = _train_hmm(calc_date)
        if new_path:
            model_path = new_path

    # 예측
    result = _predict_regime(calc_date, model_path)

    # 저장
    _save_regime(calc_date, result)

    # Telemetry
    _log_telemetry(calc_date, "regime_prediction", result["macro_score"], {
        "dominant": result["dominant_regime"],
        "confidence": result["confidence"],
        "is_fallback": result.get("is_fallback", False),
    })

    # 출력
    fb = " (FALLBACK)" if result.get("is_fallback") else ""
    print(f"  [REGIME] 결과: {result['dominant_regime']}{fb}")
    print(f"  [REGIME] macro_score={result['macro_score']}, "
          f"confidence={result['confidence']:.2%}, "
          f"equity_impact={result['equity_impact']}")

    if not result.get("is_fallback") and result.get("regime_probs"):
        probs = result["regime_probs"]
        top3 = sorted(probs.items(), key=lambda x: x[1], reverse=True)[:3]
        for name, prob in top3:
            print(f"    {name:20s} {prob:.1%}")

    return result


# 하위 호환
run_all = run_macro_regime
