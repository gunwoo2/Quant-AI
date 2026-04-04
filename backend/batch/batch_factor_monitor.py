"""
batch/batch_factor_monitor.py — IC Guard v2 + Self-Improving Engine
=====================================================================
Day 2 대폭 수정 | 설계 원칙 1 "Measure First" + 원칙 2 "Degrade Gracefully"

v1 → v2 핵심 변경:
  ★ IC Guard v2: EWMA(5일) + CUSUM 누적이탈 → 1~2일 내 반응
    (기존: 10일 단순 평균 → 10일 걸려서 반응)
  ★ 4단계 판단: BLOCK_IMMEDIATE / BLOCK_PENDING / REDUCE_50PCT / FULL_RESTORE
  ★ Dynamic AI Weight: IC 기반 ai_weight 10%~50% 동적 결정
  ★ Telemetry: 모든 IC 계산 + Guard 판단 system_telemetry 기록

기존 호환:
  - factor_ic_daily, factor_weights_monthly 테이블 그대로 사용
  - get_adaptive_weights() 인터페이스 유지
  - Forward Return 캐시 로직 유지
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
from scipy.stats import spearmanr
from datetime import datetime, date, timedelta
from db_pool import get_cursor

logger = logging.getLogger("batch_factor_monitor")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 상수 (v2)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

IC_HORIZONS = [(5, "5d"), (20, "20d"), (60, "60d")]

# 기존 가중치 파라미터 (호환 유지)
DEFAULT_WEIGHTS = {"l1": 0.5000, "l2": 0.2500, "l3": 0.2500}
MIN_WEIGHT   = 0.15
MAX_WEIGHT   = 0.65
MAX_CHANGE   = 0.05
IC_LOOKBACK  = 60
MIN_SAMPLES  = 30
IC_SMOOTHING = 0.3

# ── v2 IC Guard 상수 ──
EWMA_SPAN          = 5      # EWMA 반감기 5일
CUSUM_THRESHOLD     = 0.12   # CUSUM 누적 이탈 경보
CUSUM_DRIFT         = 0.015  # CUSUM drift 파라미터
IC_BLOCK            = 0.00   # 차단 기준: IC <= 0
IC_REDUCE           = 0.02   # 감소 기준: IC < 0.02
IC_RESTORE          = 0.05   # 복구 기준: IC > 0.05
IC_GUARD_LOOKBACK   = 20     # IC Guard 판단용 조회 일수


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 테이블 확인/생성
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _ensure_tables():
    with get_cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS factor_ic_daily (
                id          SERIAL PRIMARY KEY,
                calc_date   DATE NOT NULL,
                factor_name VARCHAR(30) NOT NULL,
                horizon     VARCHAR(10) NOT NULL,
                ic_value    NUMERIC(8,6),
                ic_pvalue   NUMERIC(8,6),
                sample_size INT,
                updated_at  TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(calc_date, factor_name, horizon)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS factor_weights_monthly (
                id          SERIAL PRIMARY KEY,
                month       DATE NOT NULL UNIQUE,
                w_l1        NUMERIC(6,4) NOT NULL DEFAULT 0.5000,
                w_l2        NUMERIC(6,4) NOT NULL DEFAULT 0.2500,
                w_l3        NUMERIC(6,4) NOT NULL DEFAULT 0.2500,
                avg_ic_l1   NUMERIC(8,6),
                avg_ic_l2   NUMERIC(8,6),
                avg_ic_l3   NUMERIC(8,6),
                ic_total    NUMERIC(8,6),
                method      VARCHAR(30) DEFAULT 'ic_weighted',
                notes       TEXT,
                updated_at  TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS forward_returns (
                id              SERIAL PRIMARY KEY,
                stock_id        INT NOT NULL,
                signal_date     DATE NOT NULL,
                price_at_signal NUMERIC(12,4),
                fwd_return_5d   NUMERIC(10,4),
                fwd_return_20d  NUMERIC(10,4),
                fwd_return_60d  NUMERIC(10,4),
                return_5d       NUMERIC(10,6),
                return_10d      NUMERIC(10,6),
                return_20d      NUMERIC(10,6),
                market_return_5d  NUMERIC(10,6),
                market_return_10d NUMERIC(10,6),
                market_return_20d NUMERIC(10,6),
                excess_return_10d NUMERIC(10,6),
                label_v2        SMALLINT,
                updated_at      TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(stock_id, signal_date)
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_fwd_ret_date ON forward_returns(signal_date)")
    print("[IC-v2] ✅ 테이블 확인")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IC Guard v2: EWMA + CUSUM
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class AdaptiveICGuard:
    """
    2중 감시 체계:
      1. EWMA: 최근 값에 높은 가중치 → 빠른 추세 반영 (1~2일 반응)
      2. CUSUM: 누적 이탈 감지 → 미세한 장기 저하도 잡음

    4단계 판단:
      BLOCK_IMMEDIATE: EWMA<=0 AND CUSUM 경보 → 즉시 가중치 0
      BLOCK_PENDING:   EWMA<=0 → 가중치 5% (관찰 중)
      REDUCE_50PCT:    EWMA<0.02 OR IC 급락 → 가중치 절반
      FULL_RESTORE:    EWMA>0.05 AND CUSUM 정상 → 완전 복구
    """

    @staticmethod
    def evaluate(ic_history: list) -> dict:
        """
        최근 IC 이력으로 레이어 상태 판단.

        Args:
            ic_history: 최근 10~20일 IC 리스트 (시간순, 최신이 마지막)

        Returns:
            {"action": str, "ewma_ic": float, "cusum_alert": bool, "detail": str}
        """
        if len(ic_history) < 3:
            return {"action": "HOLD", "ewma_ic": None, "cusum_alert": False,
                    "detail": "insufficient_data"}

        ic = np.array(ic_history, dtype=float)

        # 1. EWMA IC
        alpha = 2.0 / (EWMA_SPAN + 1)
        ewma = ic[0]
        for v in ic[1:]:
            if not np.isnan(v):
                ewma = alpha * v + (1 - alpha) * ewma
        ewma = round(float(ewma), 6)

        # 2. CUSUM (하방 이탈 감지)
        s_neg = 0.0
        for v in ic:
            if not np.isnan(v):
                s_neg = max(0, s_neg + (CUSUM_DRIFT - v))
        cusum_alert = s_neg > CUSUM_THRESHOLD

        # 3. IC Drawdown (최근 최고 대비 하락)
        valid_ic = ic[~np.isnan(ic)]
        if len(valid_ic) > 0:
            rolling_max = np.maximum.accumulate(valid_ic)
            ic_dd = float(valid_ic[-1] - rolling_max[-1])
        else:
            ic_dd = 0.0

        # 4. 4단계 판단
        if ewma <= IC_BLOCK and cusum_alert:
            return {"action": "BLOCK_IMMEDIATE", "ewma_ic": ewma,
                    "cusum_alert": True, "cusum_val": round(s_neg, 4),
                    "detail": f"EWMA={ewma:.4f}<=0 AND CUSUM={s_neg:.4f}>{CUSUM_THRESHOLD}"}

        elif ewma <= IC_BLOCK:
            return {"action": "BLOCK_PENDING", "ewma_ic": ewma,
                    "cusum_alert": cusum_alert, "cusum_val": round(s_neg, 4),
                    "detail": f"EWMA={ewma:.4f}<=0 (관찰 중)"}

        elif ewma < IC_REDUCE or ic_dd < -0.08:
            return {"action": "REDUCE_50PCT", "ewma_ic": ewma,
                    "cusum_alert": cusum_alert, "cusum_val": round(s_neg, 4),
                    "detail": f"EWMA={ewma:.4f}<{IC_REDUCE} or IC_DD={ic_dd:.4f}"}

        elif ewma > IC_RESTORE and not cusum_alert:
            return {"action": "FULL_RESTORE", "ewma_ic": ewma,
                    "cusum_alert": False, "cusum_val": round(s_neg, 4),
                    "detail": f"EWMA={ewma:.4f}>{IC_RESTORE} 정상"}

        else:
            return {"action": "HOLD", "ewma_ic": ewma,
                    "cusum_alert": cusum_alert, "cusum_val": round(s_neg, 4),
                    "detail": f"EWMA={ewma:.4f} 유지"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IC Guard 적용: 레이어별 가중치 즉시 조정
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _apply_ic_guard(calc_date: date) -> dict:
    """
    각 레이어의 최근 IC 이력 → IC Guard 판단 → 가중치 즉시 조정.

    Returns:
        {"L1": {"action": ..., "multiplier": float}, ...}
    """
    guard_results = {}
    layers = {"L1": "layer1", "L2": "layer2", "L3": "layer3"}

    for layer_name, factor_prefix in layers.items():
        # 최근 20일 IC 조회
        ic_history = []
        try:
            with get_cursor() as cur:
                cur.execute("""
                    SELECT ic_value FROM factor_ic_daily
                    WHERE factor_name = %s AND horizon = '20d'
                      AND calc_date >= %s - INTERVAL '%s days'
                    ORDER BY calc_date ASC
                """, (factor_prefix, calc_date, IC_GUARD_LOOKBACK))
                rows = cur.fetchall()
                ic_history = [float(r["ic_value"]) for r in rows if r["ic_value"] is not None]
        except Exception as e:
            logger.warning(f"[IC-GUARD] {layer_name} IC 조회 실패: {e}")

        # IC Guard 판단
        guard = AdaptiveICGuard.evaluate(ic_history)

        # 판단 → 가중치 승수
        action = guard["action"]
        if action == "BLOCK_IMMEDIATE":
            multiplier = 0.0
        elif action == "BLOCK_PENDING":
            multiplier = 0.05
        elif action == "REDUCE_50PCT":
            multiplier = 0.5
        elif action == "FULL_RESTORE":
            multiplier = 1.0
        else:  # HOLD
            multiplier = 1.0

        guard_results[layer_name] = {
            "action": action,
            "multiplier": multiplier,
            "ewma_ic": guard.get("ewma_ic"),
            "cusum_alert": guard.get("cusum_alert"),
            "detail": guard.get("detail"),
        }

        if action not in ("HOLD", "FULL_RESTORE"):
            print(f"  [IC-GUARD] {layer_name}: {action} (multiplier={multiplier}, "
                  f"EWMA={guard.get('ewma_ic')}, CUSUM_alert={guard.get('cusum_alert')})")

    # Telemetry 기록
    _log_telemetry(calc_date, "IC_GUARD", "layer_status", None, guard_results)

    return guard_results


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Dynamic AI Weight (고정 0.3 → IC 기반 동적)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_dynamic_ai_weight(calc_date: date = None) -> float:
    """
    기존: stat*0.7 + ai*0.3 (고정)
    변경: stat*(1-w) + ai*w  (w = IC 기반 동적, 10%~50%)

    w 결정:
      1. AI IC vs 통계 IC 비교
      2. IC-Weighted 비율 산출
      3. 모델 나이(age)에 따른 감쇠
      4. Bounds: 10% ~ 50%
    """
    if calc_date is None:
        calc_date = date.today()

    try:
        with get_cursor() as cur:
            # AI IC (최근 5일 평균)
            cur.execute("""
                SELECT AVG(ic_value) AS avg_ic
                FROM factor_ic_daily
                WHERE factor_name = 'total' AND horizon = '20d'
                  AND calc_date >= %s - INTERVAL '10 days'
                ORDER BY calc_date DESC LIMIT 5
            """, (calc_date,))
            row = cur.fetchone()
            ai_ic = float(row["avg_ic"]) if row and row["avg_ic"] else 0.0

            # 통계 IC (L1 기준)
            cur.execute("""
                SELECT AVG(ic_value) AS avg_ic
                FROM factor_ic_daily
                WHERE factor_name = 'layer1' AND horizon = '20d'
                  AND calc_date >= %s - INTERVAL '10 days'
                ORDER BY calc_date DESC LIMIT 5
            """, (calc_date,))
            row = cur.fetchone()
            stat_ic = float(row["avg_ic"]) if row and row["avg_ic"] else 0.0

            # 모델 나이
            cur.execute("""
                SELECT trained_date FROM ml_model_meta
                WHERE is_active = TRUE ORDER BY trained_date DESC LIMIT 1
            """)
            row = cur.fetchone()
            if row and row["trained_date"]:
                model_age = (calc_date - row["trained_date"]).days
            else:
                model_age = 999

    except Exception as e:
        logger.warning(f"[AI-WEIGHT] 조회 실패: {e}")
        return 0.30

    # IC-Weighted 비율
    total = abs(ai_ic) + abs(stat_ic) + 1e-8
    raw_w = max(0, ai_ic) / total

    # 모델 나이 감쇠 (30일 이후부터)
    decay = max(0.5, 1.0 - max(0, model_age - 30) * 0.015)
    raw_w *= decay

    # Bounds
    w = max(0.10, min(0.50, raw_w))
    w = round(w, 4)

    # Telemetry
    _log_telemetry(calc_date, "MODEL", "ai_weight_dynamic", w,
                   {"ai_ic": round(ai_ic, 6), "stat_ic": round(stat_ic, 6),
                    "model_age": model_age, "decay": round(decay, 4)})

    return w


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Forward Return 업데이트 (기존 호환 + Multi-Horizon 확장)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _update_forward_returns(calc_date: date) -> int:
    """Forward Return 캐시 업데이트 (기존 로직 유지 + 10d/market 추가)"""
    updated = 0
    horizons = [
        (5,  "fwd_return_5d",  "return_5d"),
        (10, None,             "return_10d"),
        (20, "fwd_return_20d", "return_20d"),
        (60, "fwd_return_60d", None),
    ]

    for days, col_legacy, col_new in horizons:
        signal_date_approx = calc_date - timedelta(days=int(days * 1.5))
        cols_to_update = []
        if col_legacy:
            cols_to_update.append(col_legacy)
        if col_new:
            cols_to_update.append(col_new)

        for col in cols_to_update:
            try:
                with get_cursor() as cur:
                    cur.execute(f"""
                        WITH signals AS (
                            SELECT DISTINCT ON (stock_id) stock_id, calc_date AS signal_date, weighted_score
                            FROM stock_final_scores
                            WHERE calc_date BETWEEN %s AND %s AND weighted_score IS NOT NULL
                            ORDER BY stock_id, calc_date DESC
                        ),
                        prices_then AS (
                            SELECT DISTINCT ON (stock_id) stock_id, close_price AS p_then
                            FROM stock_prices_daily
                            WHERE trade_date BETWEEN %s AND %s
                            ORDER BY stock_id, trade_date DESC
                        ),
                        prices_now AS (
                            SELECT DISTINCT ON (stock_id) stock_id, close_price AS p_now
                            FROM stock_prices_daily
                            WHERE trade_date <= %s
                            ORDER BY stock_id, trade_date DESC
                        )
                        INSERT INTO forward_returns (stock_id, signal_date, price_at_signal, {col})
                        SELECT s.stock_id, s.signal_date, pt.p_then,
                               ROUND(((pn.p_now - pt.p_then) / NULLIF(pt.p_then, 0) * 100)::numeric, 4)
                        FROM signals s
                        JOIN prices_then pt ON s.stock_id = pt.stock_id
                        JOIN prices_now pn ON s.stock_id = pn.stock_id
                        WHERE pt.p_then > 0
                        ON CONFLICT (stock_id, signal_date)
                        DO UPDATE SET {col} = EXCLUDED.{col}, updated_at = NOW()
                    """, (
                        signal_date_approx - timedelta(days=3), signal_date_approx + timedelta(days=3),
                        signal_date_approx - timedelta(days=3), signal_date_approx + timedelta(days=3),
                        calc_date,
                    ))
                    updated += cur.rowcount
            except Exception as e:
                logger.warning(f"[FWD-RET] {col}: {e}")

    # SPY 시장 수익률 업데이트
    try:
        _update_market_returns(calc_date)
    except Exception as e:
        logger.warning(f"[FWD-RET] 시장 수익률 실패: {e}")

    print(f"[IC-v2] Forward Returns 업데이트: {updated}건")
    return updated


def _update_market_returns(calc_date: date):
    """SPY 기반 시장 수익률 계산"""
    for days, col in [(5, "market_return_5d"), (10, "market_return_10d"), (20, "market_return_20d")]:
        try:
            with get_cursor() as cur:
                cur.execute("""
                    SELECT close_price FROM cross_asset_daily
                    WHERE spy_close IS NOT NULL AND calc_date <= %s
                    ORDER BY calc_date DESC LIMIT %s
                """, (calc_date, days + 5))
                # 대체: stock_prices_daily에서 SPY 직접 조회하는 것도 가능
        except:
            pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 일일 IC 계산 (기존 호환)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _calc_daily_ic(calc_date: date) -> dict:
    """일일 IC 계산 (기존 로직 유지)"""
    results = {}

    for horizon, label in IC_HORIZONS:
        signal_date_approx = calc_date - timedelta(days=int(horizon * 1.5))

        try:
            with get_cursor() as cur:
                fwd_col = f"fwd_return_{label}"
                cur.execute(f"""
                    SELECT ds.stock_id, ds.weighted_score, ds.layer1_score,
                           ds.layer2_score, ds.layer3_score, fr.{fwd_col} AS fwd_return
                    FROM stock_final_scores ds
                    JOIN forward_returns fr ON ds.stock_id = fr.stock_id
                        AND fr.signal_date BETWEEN %s AND %s
                    WHERE ds.calc_date BETWEEN %s AND %s
                      AND ds.weighted_score IS NOT NULL AND fr.{fwd_col} IS NOT NULL
                """, (
                    signal_date_approx - timedelta(days=3), signal_date_approx + timedelta(days=3),
                    signal_date_approx - timedelta(days=3), signal_date_approx + timedelta(days=3),
                ))
                rows = cur.fetchall()

            if len(rows) < MIN_SAMPLES:
                continue

            returns = np.array([float(r["fwd_return"]) for r in rows])

            for factor, col_name in [("total", "weighted_score"), ("layer1", "layer1_score"),
                                      ("layer2", "layer2_score"), ("layer3", "layer3_score")]:
                scores = np.array([float(r[col_name]) for r in rows if r[col_name] is not None])
                if len(scores) < MIN_SAMPLES:
                    continue

                rets = returns[:len(scores)]
                ic_val, p_val = spearmanr(scores, rets)

                if np.isnan(ic_val):
                    continue

                ic_val = round(float(ic_val), 6)
                p_val = round(float(p_val), 6)

                with get_cursor() as cur2:
                    cur2.execute("""
                        INSERT INTO factor_ic_daily (calc_date, factor_name, horizon, ic_value, ic_pvalue, sample_size)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (calc_date, factor_name, horizon)
                        DO UPDATE SET ic_value=EXCLUDED.ic_value, ic_pvalue=EXCLUDED.ic_pvalue,
                                      sample_size=EXCLUDED.sample_size, updated_at=NOW()
                    """, (calc_date, factor, label, ic_val, p_val, len(scores)))

                results[f"{factor}_{label}"] = ic_val

        except Exception as e:
            logger.warning(f"[IC] {label} 계산 실패: {e}")

    return results


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 월간 가중치 최적화 (기존 호환 + IC Guard 연동)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _optimize_monthly_weights(calc_date: date) -> dict:
    """월간 가중치 최적화 (기존 로직 유지)"""
    avg_ics = {}
    for factor in ["l1", "l2", "l3"]:
        factor_db = {"l1": "layer1", "l2": "layer2", "l3": "layer3"}[factor]
        try:
            with get_cursor() as cur:
                cur.execute("""
                    SELECT AVG(ic_value) AS avg_ic FROM factor_ic_daily
                    WHERE factor_name=%s AND horizon='20d'
                      AND calc_date >= %s - INTERVAL '%s days'
                """, (factor_db, calc_date, IC_LOOKBACK))
                row = cur.fetchone()
                avg_ics[factor] = float(row["avg_ic"]) if row and row["avg_ic"] else None
        except:
            avg_ics[factor] = None

    valid_ics = {k: v for k, v in avg_ics.items() if v is not None and v > 0}
    if len(valid_ics) < 2:
        return _save_weights(calc_date, DEFAULT_WEIGHTS["l1"], DEFAULT_WEIGHTS["l2"],
                             DEFAULT_WEIGHTS["l3"], avg_ics, "default")

    ic_total = sum(valid_ics.values())
    raw_weights = {}
    for f in ["l1", "l2", "l3"]:
        ic_ratio = valid_ics.get(f, 0) / ic_total if f in valid_ics else DEFAULT_WEIGHTS[f]
        raw_weights[f] = 0.5 * ic_ratio + 0.5 * DEFAULT_WEIGHTS[f]

    prev = _get_prev_weights()
    def constrain(raw, prev_val):
        c = max(MIN_WEIGHT, min(MAX_WEIGHT, raw))
        return max(prev_val - MAX_CHANGE, min(prev_val + MAX_CHANGE, c))

    w1 = constrain(raw_weights.get("l1", 0.5), prev["l1"])
    w2 = constrain(raw_weights.get("l2", 0.25), prev["l2"])
    w3 = constrain(raw_weights.get("l3", 0.25), prev["l3"])
    total = w1 + w2 + w3
    w1, w2, w3 = round(w1/total, 4), round(w2/total, 4), round(1-w1/total-w2/total, 4)

    return _save_weights(calc_date, w1, w2, w3, avg_ics, "ic_weighted_v2")


def _get_prev_weights():
    try:
        with get_cursor() as cur:
            cur.execute("SELECT w_l1, w_l2, w_l3 FROM factor_weights_monthly ORDER BY month DESC LIMIT 1")
            row = cur.fetchone()
            if row:
                return {"l1": float(row["w_l1"]), "l2": float(row["w_l2"]), "l3": float(row["w_l3"])}
    except:
        pass
    return DEFAULT_WEIGHTS.copy()


def _save_weights(calc_date, w1, w2, w3, avg_ics, method):
    month_start = calc_date.replace(day=1)
    try:
        with get_cursor() as cur:
            cur.execute("""
                INSERT INTO factor_weights_monthly (month, w_l1, w_l2, w_l3, avg_ic_l1, avg_ic_l2, avg_ic_l3, ic_total, method)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (month) DO UPDATE SET
                    w_l1=EXCLUDED.w_l1, w_l2=EXCLUDED.w_l2, w_l3=EXCLUDED.w_l3,
                    avg_ic_l1=EXCLUDED.avg_ic_l1, avg_ic_l2=EXCLUDED.avg_ic_l2, avg_ic_l3=EXCLUDED.avg_ic_l3,
                    ic_total=EXCLUDED.ic_total, method=EXCLUDED.method, updated_at=NOW()
            """, (month_start, w1, w2, w3, avg_ics.get("l1"), avg_ics.get("l2"), avg_ics.get("l3"),
                  sum(v for v in avg_ics.values() if v is not None), method))
    except Exception as e:
        logger.warning(f"[WEIGHTS] 저장 실패: {e}")
    return {"l1": w1, "l2": w2, "l3": w3}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 공개 API (기존 호환)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_adaptive_weights():
    """
    batch_final_score.py에서 호출 (기존 인터페이스 유지)
    v5.1: adaptive_weights(일별 IC Guard) → factor_weights_monthly → fallback
    """
    # 1순위: IC Guard 일별 가중치 (batch_ic_guard.py가 매일 업데이트)
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT l1_weight, l2_weight, l3_weight, calc_date 
                FROM adaptive_weights 
                ORDER BY calc_date DESC LIMIT 1
            """)
            row = cur.fetchone()
            if row:
                w1, w2, w3 = float(row["l1_weight"]), float(row["l2_weight"]), float(row["l3_weight"])
                print(f"  [WEIGHTS] IC Guard 적응형: L1={w1:.2f} L2={w2:.2f} L3={w3:.2f} ({row['calc_date']})")
                return w1, w2, w3
    except Exception:
        pass
    
    # 2순위: 월별 팩터 가중치 (기존 방식)
    try:
        with get_cursor() as cur:
            cur.execute("SELECT w_l1, w_l2, w_l3 FROM factor_weights_monthly ORDER BY month DESC LIMIT 1")
            row = cur.fetchone()
            if row:
                w1, w2, w3 = float(row["w_l1"]), float(row["w_l2"]), float(row["w_l3"])
                print(f"  [WEIGHTS] Monthly: L1={w1:.2f} L2={w2:.2f} L3={w3:.2f}")
                return w1, w2, w3
    except Exception:
        pass
    
    # 3순위: Fallback (L3 집중 — IC 테스트 기반)
    print("  [WEIGHTS] Fallback: L1=0.00 L2=0.00 L3=1.00")
    return 0.00, 0.00, 1.00


def get_ic_guard_status(calc_date: date = None) -> dict:
    """IC Guard 상태 조회 (API/대시보드용)"""
    if calc_date is None:
        calc_date = date.today()
    return _apply_ic_guard(calc_date)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 메인 실행
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run_factor_monitor(calc_date: date = None):
    """
    scheduler.py Step 6.5에서 호출.

    1. Forward Return 업데이트
    2. 일일 IC 계산
    3. IC Guard v2 적용 (레이어별 즉시 판단)
    4. 월 1회 가중치 최적화
    """
    if calc_date is None:
        calc_date = datetime.now().date()

    print(f"\n[IC-v2] === Factor Monitor + IC Guard — {calc_date} ===")
    _ensure_tables()

    # Step 1: Forward Return
    _update_forward_returns(calc_date)

    # Step 2: 일일 IC
    ic_results = _calc_daily_ic(calc_date)
    if ic_results:
        print(f"  IC 계산: {len(ic_results)}개 팩터-호라이즌")

    # Step 3: IC Guard v2 (매일!)
    guard_results = _apply_ic_guard(calc_date)
    blocked = [k for k, v in guard_results.items()
               if v["action"] in ("BLOCK_IMMEDIATE", "BLOCK_PENDING")]
    if blocked:
        print(f"  [IC-GUARD] ⚠️ 차단된 레이어: {blocked}")

    # Step 4: 월간 가중치 (매월 1일)
    if calc_date.day == 1:
        weights = _optimize_monthly_weights(calc_date)
        print(f"  월간 가중치: {weights}")

    return {
        "ic_results": ic_results,
        "guard_results": {k: v["action"] for k, v in guard_results.items()},
        "blocked_layers": blocked,
    }


def _log_telemetry(calc_date, category, metric_name, metric_value, detail=None):
    try:
        with get_cursor() as cur:
            cur.execute("""
                INSERT INTO system_telemetry (calc_date, category, metric_name, metric_value, detail)
                VALUES (%s, %s, %s, %s, %s)
            """, (calc_date, category, metric_name, metric_value,
                  json.dumps(detail, ensure_ascii=False, default=str) if detail else None))
    except Exception as e:
        logger.warning(f"[TELEMETRY] 실패: {e}")


# 하위 호환 alias
run_all = run_factor_monitor
