"""
batch/batch_auto_pilot.py — AutoPilot Self-Evolution Engine v1.0
=================================================================
Day 6 신규 | 설계 원칙 3 "Trust is Earned" — 검증 없이 배포 불가

매일 배치 마지막에 실행되는 모델 건강 관리사:
  1. Monitor: 현재 모델 IC/Hit Rate 추적
  2. Diagnose: 재학습 필요 조건 감지
  3. Retrain: 새 모델 자동 학습 시도
  4. Gate: 새 모델이 기존 대비 10%+ 개선 시에만 교체

재학습 트리거 (하나라도 해당되면):
  - IC < 0.02 (5일 평균)
  - 7일간 IC 하락 추세 (ΔIC > -0.03)
  - 모델 나이 > 30일
  - Regime 변경 감지

실행: scheduler.py Step 7.5 (Trading Signal 직후, 알림 직전)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import patch_numpy_adapter
except ImportError:
    pass

import numpy as np
import json
import logging
from datetime import datetime, date, timedelta
from db_pool import get_cursor

logger = logging.getLogger("batch_auto_pilot")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 상수
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

IC_THRESHOLD       = 0.02   # IC 이 미만이면 재학습
IC_DECLINE_DELTA   = 0.03   # 7일간 이만큼 하락하면 재학습
MODEL_AGE_MAX      = 30     # 모델 나이 이 초과면 재학습
IMPROVEMENT_GATE   = 1.10   # 새 모델이 기존 대비 10%+ 개선 필요
COOLDOWN_DAYS      = 3      # 재학습 후 최소 대기일


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Monitor: 현재 모델 상태 추적
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _get_model_health(calc_date):
    """현재 활성 모델의 건강 지표 수집"""
    health = {
        "current_ic": None,
        "ic_7d_ago": None,
        "ic_trend": None,
        "model_age": 999,
        "current_regime": None,
        "model_regime": None,
        "last_retrain": None,
    }

    try:
        with get_cursor() as cur:
            # 최근 5일 평균 IC
            cur.execute("""
                SELECT AVG(ic_value) AS avg_ic FROM (
                    SELECT ic_value FROM factor_ic_daily
                    WHERE factor_name = 'total' AND horizon = '20d'
                      AND calc_date >= %s - INTERVAL '10 days'
                    ORDER BY calc_date DESC LIMIT 5
                ) sub
            """, (calc_date,))
            row = cur.fetchone()
            health["current_ic"] = float(row["avg_ic"]) if row and row["avg_ic"] else None

            # 7일 전 IC (추세 비교)
            cur.execute("""
                SELECT ic_value FROM factor_ic_daily
                WHERE factor_name = 'total' AND horizon = '20d'
                  AND calc_date <= %s - INTERVAL '7 days'
                ORDER BY calc_date DESC LIMIT 1
            """, (calc_date,))
            row = cur.fetchone()
            health["ic_7d_ago"] = float(row["ic_value"]) if row and row["ic_value"] else None

            # IC 추세
            if health["current_ic"] is not None and health["ic_7d_ago"] is not None:
                health["ic_trend"] = round(health["current_ic"] - health["ic_7d_ago"], 6)

            # 모델 나이
            cur.execute("""
                SELECT trained_date FROM ml_model_meta
                WHERE is_active = TRUE ORDER BY trained_date DESC LIMIT 1
            """)
            row = cur.fetchone()
            if row and row["trained_date"]:
                health["model_age"] = (calc_date - row["trained_date"]).days
                health["last_retrain"] = row["trained_date"]

            # 현재 Regime
            cur.execute("""
                SELECT dominant_regime FROM macro_regime_daily
                WHERE calc_date <= %s ORDER BY calc_date DESC LIMIT 1
            """, (calc_date,))
            row = cur.fetchone()
            health["current_regime"] = row["dominant_regime"] if row else None

    except Exception as e:
        logger.warning(f"[AUTOPILOT] 건강 지표 수집 실패: {e}")

    return health


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Diagnose: 재학습 필요 판단
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _should_retrain(health, calc_date):
    """
    재학습 트리거 조건 확인.
    하나라도 해당되면 True + 이유 반환.
    """
    reasons = []

    # 1. IC < threshold
    if health["current_ic"] is not None and health["current_ic"] < IC_THRESHOLD:
        reasons.append(f"ic_low: {health['current_ic']:.4f} < {IC_THRESHOLD}")

    # 2. IC 7일간 하락
    if health["ic_trend"] is not None and health["ic_trend"] < -IC_DECLINE_DELTA:
        reasons.append(f"ic_declining: delta={health['ic_trend']:.4f}")

    # 3. 모델 나이 초과
    if health["model_age"] > MODEL_AGE_MAX:
        reasons.append(f"model_age: {health['model_age']}d > {MODEL_AGE_MAX}d")

    # 4. Regime 변경 (모델 학습 시점과 현재 국면 다름)
    if (health["current_regime"] and health.get("model_regime") and
            health["current_regime"] != health["model_regime"]):
        reasons.append(f"regime_changed: {health['model_regime']} → {health['current_regime']}")

    # 5. Cooldown 체크 (최근 재학습 후 N일 미만이면 스킵)
    if health["last_retrain"]:
        days_since = (calc_date - health["last_retrain"]).days
        if days_since < COOLDOWN_DAYS:
            return False, [f"cooldown: {days_since}d < {COOLDOWN_DAYS}d"]

    return len(reasons) > 0, reasons


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Retrain + Gate: 학습 + 배포 결정
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _attempt_retrain(calc_date, current_ic, reasons):
    """
    재학습 시도 + A/B Gatekeeper.

    원칙 3: 새 모델이 기존 대비 10%+ 개선 증명해야만 배포.
    """
    print(f"  [AUTOPILOT] 재학습 시도 (사유: {reasons})")

    try:
        # Ensemble 학습 시도
        from batch.batch_ensemble import run_ensemble
        result = run_ensemble(calc_date)

        if isinstance(result, dict) and result.get("error"):
            return {"action": "RETRAIN_FAILED", "reason": result["error"]}

        # 새 모델 IC 조회
        with get_cursor() as cur:
            cur.execute("""
                SELECT oos_ic, oos_auc FROM ml_model_meta
                WHERE is_active = TRUE ORDER BY trained_date DESC LIMIT 1
            """)
            row = cur.fetchone()
            new_ic = float(row["oos_ic"]) if row and row["oos_ic"] else 0.0
            new_auc = float(row["oos_auc"]) if row and row["oos_auc"] else 0.5

    except Exception as e:
        logger.warning(f"[AUTOPILOT] 재학습 실패: {e}")
        return {"action": "RETRAIN_FAILED", "reason": str(e)}

    # A/B Gate: 개선 판단
    old_ic = current_ic if current_ic and current_ic > 0 else 0.001
    improvement = new_ic / old_ic

    if improvement >= IMPROVEMENT_GATE:
        print(f"  [AUTOPILOT] ✅ 새 모델 배포! IC: {old_ic:.4f} → {new_ic:.4f} "
              f"(+{(improvement-1)*100:.1f}%)")

        _log_telemetry(calc_date, "AUTOPILOT", "model_deployed", new_ic, {
            "old_ic": round(old_ic, 6), "new_ic": round(new_ic, 6),
            "improvement": round(improvement, 4), "reasons": reasons,
        })

        return {"action": "DEPLOYED", "old_ic": old_ic, "new_ic": new_ic,
                "improvement": improvement}
    else:
        print(f"  [AUTOPILOT] ⚠️ 개선 부족 → 기존 모델 유지 "
              f"(IC: {old_ic:.4f} → {new_ic:.4f}, +{(improvement-1)*100:.1f}% < 10%)")

        # 새 모델 비활성 (이전 모델 복원)
        try:
            with get_cursor() as cur:
                # 가장 최근 활성 모델 말고 그 이전 모델을 다시 활성화
                cur.execute("""
                    UPDATE ml_model_meta SET is_active = TRUE
                    WHERE id = (
                        SELECT id FROM ml_model_meta
                        WHERE is_active = FALSE
                        ORDER BY trained_date DESC LIMIT 1
                    )
                """)
        except Exception:
            pass

        _log_telemetry(calc_date, "AUTOPILOT", "model_kept", old_ic, {
            "new_ic": round(new_ic, 6), "improvement": round(improvement, 4),
            "reason": "insufficient_improvement",
        })

        return {"action": "KEPT_OLD", "old_ic": old_ic, "new_ic": new_ic,
                "improvement": improvement}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 공개 API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run_auto_pilot(calc_date=None):
    """
    scheduler.py Step 7.5에서 호출.

    매일 실행:
      1. Monitor → 모델 건강 추적
      2. Diagnose → 재학습 필요?
      3. (필요시) Retrain → Gate → 배포/유지
      4. Telemetry 기록
    """
    if calc_date is None:
        calc_date = date.today()

    print(f"\n[AUTOPILOT] === Auto-Pilot Check — {calc_date} ===")

    # 1. Monitor
    health = _get_model_health(calc_date)
    ic_str = f"{health['current_ic']:.4f}" if health['current_ic'] is not None else "N/A"
    age_str = f"{health['model_age']}d"
    regime_str = health.get('current_regime', 'N/A')

    print(f"  IC={ic_str}, Age={age_str}, Regime={regime_str}")

    # 2. Diagnose
    should, reasons = _should_retrain(health, calc_date)

    if not should:
        print(f"  [AUTOPILOT] 정상 — 재학습 불필요")
        _log_telemetry(calc_date, "AUTOPILOT", "daily_check", health.get("current_ic"), {
            "action": "NO_RETRAIN", "age": health["model_age"],
            "ic": health.get("current_ic"), "regime": regime_str,
        })
        return {"action": "NO_RETRAIN", "health": health}

    print(f"  [AUTOPILOT] ⚡ 재학습 트리거: {reasons}")

    # 3. Retrain + Gate
    result = _attempt_retrain(calc_date, health.get("current_ic"), reasons)
    result["health"] = health
    result["trigger_reasons"] = reasons

    return result


def _log_telemetry(calc_date, category, metric_name, metric_value, detail=None):
    try:
        with get_cursor() as cur:
            cur.execute("""
                INSERT INTO system_telemetry (calc_date, category, metric_name, metric_value, detail)
                VALUES (%s, %s, %s, %s, %s)
            """, (calc_date, category, metric_name, metric_value,
                  json.dumps(detail, ensure_ascii=False, default=str) if detail else None))
    except Exception as e:
        logger.debug(f"[TELEMETRY] 실패: {e}")


# 하위 호환
run_all = run_auto_pilot
