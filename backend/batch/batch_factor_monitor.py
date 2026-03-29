"""
batch/batch_factor_monitor.py — Self-Improving Score Engine v1.0
================================================================
AI 모듈 #2: IC(Information Coefficient) 기반 자동 가중치 최적화

핵심 기능:
  1. 일일 IC 계산: 과거 점수 vs 실현 수익률 상관관계
  2. 월간 가중치 최적화: IC 비율로 L1/L2/L3 가중치 자동 조정
  3. Forward Return 추적: 5D/20D/60D 수익률 저장
  4. 팩터 건강도 모니터링: IC Decay 조기 경고

학술 참조:
  - Grinold (1989) "The Fundamental Law of Active Management"
    IR = IC × √BR  (IC가 핵심)
  - Qian & Hua (2004) "Active Risk and Information Ratio"
  - DeMiguel et al. (2009) "Optimal vs Naive Diversification"
    → 가중치 변경 상한 ±5% (과적합 방지)

실행 주기:
  - IC 계산: 매일 (배치 Step 6.5)
  - 가중치 최적화: 매월 1일 (Step 6.5에서 자동 판단)

DB 테이블:
  - factor_ic_daily: 일일 IC 기록
  - factor_weights_monthly: 월간 최적 가중치
  - forward_returns: 종목별 Forward Return 캐시
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import patch_numpy_adapter
except ImportError:
    pass

import numpy as np
from scipy.stats import spearmanr
from datetime import datetime, date, timedelta
from db_pool import get_cursor


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 상수
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# IC 계산 기간 (과거 점수 → 현재까지 수익률)
IC_HORIZONS = [
    (5,  "5d"),
    (20, "20d"),
    (60, "60d"),
]

# 가중치 최적화 파라미터
DEFAULT_WEIGHTS = {"l1": 0.5000, "l2": 0.2500, "l3": 0.2500}
MIN_WEIGHT   = 0.15     # 어떤 레이어도 15% 미만 불가
MAX_WEIGHT   = 0.65     # 어떤 레이어도 65% 초과 불가
MAX_CHANGE   = 0.05     # 한 달 최대 ±5% 변경 (과적합 방지)
IC_LOOKBACK  = 60       # IC 평균 계산 기간 (최근 60일)
MIN_SAMPLES  = 30       # IC 계산 최소 종목 수
IC_SMOOTHING = 0.3      # IC EMA 스무딩 (오늘 30% + 과거 70%)

# IC 건강도 경고 기준
IC_WARNING_THRESHOLD  = 0.01   # IC < 0.01 → "약한 시그널" 경고
IC_DANGER_THRESHOLD   = 0.00   # IC ≤ 0 → "시그널 무효" 위험


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 테이블 확인/생성
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _ensure_tables():
    """필요 테이블 자동 생성 (IF NOT EXISTS)"""
    with get_cursor() as cur:
        # 1. 일일 IC 기록
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

        # 2. 월간 최적 가중치
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

        # 3. Forward Returns 캐시 (일일 IC 계산 가속화)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS forward_returns (
                id              SERIAL PRIMARY KEY,
                stock_id        INT NOT NULL,
                signal_date     DATE NOT NULL,
                price_at_signal NUMERIC(12,2),
                fwd_return_5d   NUMERIC(8,4),
                fwd_return_20d  NUMERIC(8,4),
                fwd_return_60d  NUMERIC(8,4),
                updated_at      TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(stock_id, signal_date)
            )
        """)

        # 인덱스
        cur.execute("CREATE INDEX IF NOT EXISTS idx_factor_ic_date ON factor_ic_daily(calc_date DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_fwd_returns_date ON forward_returns(signal_date)")

    print("[IC] ✅ 테이블 확인 완료")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Step 1: Forward Return 계산
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _calc_forward_returns(calc_date: date):
    """
    과거 시그널에 대한 Forward Return 업데이트.

    로직:
    - 5일 전 시그널 → 오늘까지 수익률 = fwd_return_5d
    - 20일 전 시그널 → fwd_return_20d
    - 60일 전 시그널 → fwd_return_60d
    """
    updated = 0

    for horizon, col in [(5, "fwd_return_5d"), (20, "fwd_return_20d"), (60, "fwd_return_60d")]:
        # horizon 영업일 전 날짜 추정 (달력일 ≈ 영업일 × 1.5)
        signal_date_approx = calc_date - timedelta(days=int(horizon * 1.5))

        try:
            with get_cursor() as cur:
                # 해당 signal_date 근처에 점수가 있었던 종목 찾기
                cur.execute(f"""
                    WITH signals AS (
                        SELECT stock_id, calc_date AS signal_date, weighted_score
                        FROM daily_stock_score
                        WHERE calc_date BETWEEN %s AND %s
                          AND weighted_score IS NOT NULL
                    ),
                    prices_then AS (
                        SELECT DISTINCT ON (stock_id) stock_id, close_price AS p_then, trade_date
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
            print(f"  [WARN] Forward Return ({col}): {e}")

    print(f"[IC] Forward Returns 업데이트: {updated}건")
    return updated


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Step 2: 일일 IC 계산
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _calc_daily_ic(calc_date: date) -> dict:
    """
    오늘 기준 IC(Information Coefficient) 계산.

    IC = Spearman Rank Correlation(N일 전 점수, 현재까지 수익률)

    각 레이어별 + 전체 점수의 IC를 계산하여 factor_ic_daily에 저장.
    """
    results = {}

    for horizon, label in IC_HORIZONS:
        # N 영업일 전 추정
        signal_date_approx = calc_date - timedelta(days=int(horizon * 1.5))

        try:
            with get_cursor() as cur:
                cur.execute("""
                    SELECT
                        ds.stock_id,
                        ds.weighted_score,
                        ds.layer1_score,
                        ds.layer2_score,
                        ds.layer3_score,
                        fr.{fwd_col} AS fwd_return
                    FROM daily_stock_score ds
                    JOIN forward_returns fr
                        ON ds.stock_id = fr.stock_id
                        AND fr.signal_date BETWEEN %s AND %s
                    WHERE ds.calc_date BETWEEN %s AND %s
                      AND ds.weighted_score IS NOT NULL
                      AND fr.{fwd_col} IS NOT NULL
                    ORDER BY ds.stock_id
                """.format(fwd_col=f"fwd_return_{label}"), (
                    signal_date_approx - timedelta(days=3),
                    signal_date_approx + timedelta(days=3),
                    signal_date_approx - timedelta(days=3),
                    signal_date_approx + timedelta(days=3),
                ))
                rows = cur.fetchall()

            if len(rows) < MIN_SAMPLES:
                print(f"  [IC-{label}] 표본 부족: {len(rows)} < {MIN_SAMPLES}")
                continue

            returns = [float(r["fwd_return"]) for r in rows]

            # 각 팩터별 IC 계산
            factors = {
                "total": [float(r["weighted_score"] or 0) for r in rows],
                "l1":    [float(r["layer1_score"] or 0) for r in rows],
                "l2":    [float(r["layer2_score"] or 0) for r in rows],
                "l3":    [float(r["layer3_score"] or 0) for r in rows],
            }

            for factor_name, scores in factors.items():
                # Spearman Rank Correlation
                ic_val, p_val = spearmanr(scores, returns)

                if np.isnan(ic_val):
                    continue

                ic_val = round(float(ic_val), 6)
                p_val = round(float(p_val), 6)

                # DB 저장
                with get_cursor() as cur:
                    cur.execute("""
                        INSERT INTO factor_ic_daily (calc_date, factor_name, horizon, ic_value, ic_pvalue, sample_size)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (calc_date, factor_name, horizon) DO UPDATE SET
                            ic_value = EXCLUDED.ic_value,
                            ic_pvalue = EXCLUDED.ic_pvalue,
                            sample_size = EXCLUDED.sample_size,
                            updated_at = NOW()
                    """, (calc_date, factor_name, label, ic_val, p_val, len(rows)))

                key = f"{factor_name}_{label}"
                results[key] = {"ic": ic_val, "p": p_val, "n": len(rows)}

                # 경고 출력
                status = "✅"
                if ic_val < IC_DANGER_THRESHOLD:
                    status = "🔴 DANGER"
                elif ic_val < IC_WARNING_THRESHOLD:
                    status = "⚠️  WEAK"

                print(f"  [IC-{label}] {factor_name:8s} IC={ic_val:+.4f} (p={p_val:.4f}, n={len(rows)}) {status}")

        except Exception as e:
            print(f"  [ERR] IC-{label}: {e}")

    return results


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Step 3: 월간 가중치 최적화
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _optimize_monthly_weights(calc_date: date) -> dict:
    """
    IC 기반 L1/L2/L3 가중치 자동 최적화.

    알고리즘:
    1. 최근 60일 평균 IC 조회 (20d 기준)
    2. IC 비율로 원시 가중치 계산
    3. 안전장치 적용 (15%~65%, 월 ±5% 제한)
    4. 정규화 (합=1.0)

    참고: DeMiguel et al. (2009) — 과적합 방지를 위해
          naive(1/N) 방향으로 shrinkage 하는 것이 핵심
    """
    print(f"\n[IC] ★ 월간 가중치 최적화 시작 ({calc_date})")

    # 1. 최근 60일 평균 IC 조회 (20d horizon 기준)
    avg_ics = {}
    for factor in ["l1", "l2", "l3"]:
        try:
            with get_cursor() as cur:
                cur.execute("""
                    SELECT AVG(ic_value) AS avg_ic, COUNT(*) AS cnt
                    FROM factor_ic_daily
                    WHERE factor_name = %s
                      AND horizon = '20d'
                      AND calc_date >= %s - INTERVAL '60 days'
                      AND ic_value IS NOT NULL
                """, (factor, calc_date))
                row = cur.fetchone()
                if row and row["avg_ic"] is not None and row["cnt"] >= 10:
                    avg_ics[factor] = max(float(row["avg_ic"]), 0.001)  # 음수 IC → 최소값
                else:
                    avg_ics[factor] = None
        except Exception as e:
            print(f"  [WARN] IC 조회 실패 ({factor}): {e}")
            avg_ics[factor] = None

    print(f"  평균 IC (20d): L1={avg_ics.get('l1')}, L2={avg_ics.get('l2')}, L3={avg_ics.get('l3')}")

    # 2. 유효한 IC가 2개 이상이면 최적화, 아니면 기본값 유지
    valid_ics = {k: v for k, v in avg_ics.items() if v is not None}

    if len(valid_ics) < 2:
        print("  ⚠️  IC 데이터 부족 — 기본 가중치 유지")
        return _save_weights(calc_date, DEFAULT_WEIGHTS["l1"], DEFAULT_WEIGHTS["l2"],
                             DEFAULT_WEIGHTS["l3"], avg_ics, "default_insufficient_data")

    # 3. IC 비율로 원시 가중치 계산 (IC 높을수록 큰 가중치)
    # Shrinkage: IC 기반 50% + 기본값 50% (과적합 방지)
    ic_total = sum(valid_ics.values())
    raw_weights = {}
    for factor in ["l1", "l2", "l3"]:
        if factor in valid_ics:
            ic_ratio = valid_ics[factor] / ic_total
        else:
            ic_ratio = DEFAULT_WEIGHTS[factor]
        # Shrinkage to default: 50% IC기반 + 50% 기본값
        raw_weights[factor] = 0.5 * ic_ratio + 0.5 * DEFAULT_WEIGHTS[factor]

    # 4. 이전 달 가중치 조회
    prev_weights = _get_prev_weights()

    # 5. 안전장치 적용
    def constrain(raw, prev_val):
        clamped = max(MIN_WEIGHT, min(MAX_WEIGHT, raw))
        clamped = max(prev_val - MAX_CHANGE, min(prev_val + MAX_CHANGE, clamped))
        return clamped

    w1 = constrain(raw_weights.get("l1", 0.50), prev_weights["l1"])
    w2 = constrain(raw_weights.get("l2", 0.25), prev_weights["l2"])
    w3 = constrain(raw_weights.get("l3", 0.25), prev_weights["l3"])

    # 6. 정규화 (합 = 1.0)
    total = w1 + w2 + w3
    w1 = round(w1 / total, 4)
    w2 = round(w2 / total, 4)
    w3 = round(1.0 - w1 - w2, 4)  # 반올림 보정

    print(f"  이전: L1={prev_weights['l1']:.4f}, L2={prev_weights['l2']:.4f}, L3={prev_weights['l3']:.4f}")
    print(f"  신규: L1={w1:.4f}, L2={w2:.4f}, L3={w3:.4f}")

    changes = [
        abs(w1 - prev_weights["l1"]),
        abs(w2 - prev_weights["l2"]),
        abs(w3 - prev_weights["l3"]),
    ]
    print(f"  변화: ΔL1={changes[0]:.4f}, ΔL2={changes[1]:.4f}, ΔL3={changes[2]:.4f}")

    return _save_weights(calc_date, w1, w2, w3, avg_ics, "ic_weighted")


def _get_prev_weights() -> dict:
    """이전 달 가중치 조회"""
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT w_l1, w_l2, w_l3 FROM factor_weights_monthly
                ORDER BY month DESC LIMIT 1
            """)
            row = cur.fetchone()
            if row:
                return {
                    "l1": float(row["w_l1"]),
                    "l2": float(row["w_l2"]),
                    "l3": float(row["w_l3"]),
                }
    except Exception:
        pass
    return DEFAULT_WEIGHTS.copy()


def _save_weights(calc_date, w1, w2, w3, avg_ics, method) -> dict:
    """월간 가중치 DB 저장"""
    month_start = calc_date.replace(day=1)
    notes = f"IC: L1={avg_ics.get('l1')}, L2={avg_ics.get('l2')}, L3={avg_ics.get('l3')}"

    try:
        with get_cursor() as cur:
            cur.execute("""
                INSERT INTO factor_weights_monthly
                    (month, w_l1, w_l2, w_l3, avg_ic_l1, avg_ic_l2, avg_ic_l3, ic_total, method, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (month) DO UPDATE SET
                    w_l1 = EXCLUDED.w_l1, w_l2 = EXCLUDED.w_l2, w_l3 = EXCLUDED.w_l3,
                    avg_ic_l1 = EXCLUDED.avg_ic_l1, avg_ic_l2 = EXCLUDED.avg_ic_l2,
                    avg_ic_l3 = EXCLUDED.avg_ic_l3, ic_total = EXCLUDED.ic_total,
                    method = EXCLUDED.method, notes = EXCLUDED.notes,
                    updated_at = NOW()
            """, (
                month_start, w1, w2, w3,
                avg_ics.get("l1"), avg_ics.get("l2"), avg_ics.get("l3"),
                sum(v for v in avg_ics.values() if v is not None),
                method, notes,
            ))
        print(f"[IC] ✅ 가중치 저장: L1={w1}, L2={w2}, L3={w3} ({method})")
    except Exception as e:
        print(f"[IC] ❌ 가중치 저장 실패: {e}")

    return {"w_l1": w1, "w_l2": w2, "w_l3": w3, "method": method}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 공개 함수: 가중치 조회 (batch_final_score에서 호출)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_adaptive_weights() -> tuple:
    """
    DB에서 현재 유효 가중치 조회. 없으면 기본값.
    batch_final_score.py에서 import해서 사용.

    Returns:
        (w_l1, w_l2, w_l3) : tuple of float
    """
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT w_l1, w_l2, w_l3 FROM factor_weights_monthly
                WHERE month <= CURRENT_DATE
                ORDER BY month DESC LIMIT 1
            """)
            row = cur.fetchone()
        if row:
            return (float(row["w_l1"]), float(row["w_l2"]), float(row["w_l3"]))
    except Exception:
        pass
    return (0.5000, 0.2500, 0.2500)


def get_ic_health_summary() -> dict:
    """최근 IC 건강도 요약 (Discord 알림용)"""
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT factor_name, horizon,
                       AVG(ic_value) AS avg_ic,
                       MIN(ic_value) AS min_ic,
                       MAX(ic_value) AS max_ic,
                       COUNT(*) AS cnt
                FROM factor_ic_daily
                WHERE calc_date >= CURRENT_DATE - INTERVAL '30 days'
                GROUP BY factor_name, horizon
                ORDER BY factor_name, horizon
            """)
            rows = cur.fetchall()

        summary = {}
        warnings = []
        for r in rows:
            key = f"{r['factor_name']}_{r['horizon']}"
            avg_ic = float(r["avg_ic"]) if r["avg_ic"] else 0
            summary[key] = {
                "avg_ic": round(avg_ic, 4),
                "min_ic": round(float(r["min_ic"]), 4) if r["min_ic"] else None,
                "max_ic": round(float(r["max_ic"]), 4) if r["max_ic"] else None,
                "days": int(r["cnt"]),
            }
            if avg_ic < IC_DANGER_THRESHOLD:
                warnings.append(f"🔴 {key}: IC={avg_ic:.4f} (DANGER)")
            elif avg_ic < IC_WARNING_THRESHOLD:
                warnings.append(f"⚠️ {key}: IC={avg_ic:.4f} (WEAK)")

        return {"factors": summary, "warnings": warnings}
    except Exception:
        return {"factors": {}, "warnings": []}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 메인 실행
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run_factor_monitor(calc_date: date = None):
    """
    일일 IC 모니터링 + (월초면) 가중치 최적화.
    Scheduler Step 6.5에서 호출.
    """
    if calc_date is None:
        calc_date = datetime.now().date()

    print(f"\n{'='*60}")
    print(f"  Self-Improving Score Engine — Factor Monitor")
    print(f"  Date: {calc_date}")
    print(f"{'='*60}")

    _ensure_tables()

    # Step 1: Forward Return 업데이트
    print("\n── Step 1: Forward Return 업데이트 ──")
    _calc_forward_returns(calc_date)

    # Step 2: 일일 IC 계산
    print("\n── Step 2: 일일 IC 계산 ──")
    ic_results = _calc_daily_ic(calc_date)

    # Step 3: 월초면 가중치 최적화
    weights_result = None
    if calc_date.day <= 3:  # 매월 1~3일에 최적화 (주말/공휴일 대비)
        print("\n── Step 3: 월간 가중치 최적화 ──")
        weights_result = _optimize_monthly_weights(calc_date)
    else:
        current = get_adaptive_weights()
        print(f"\n[IC] 현재 가중치: L1={current[0]}, L2={current[1]}, L3={current[2]} (다음 최적화: 월초)")

    # Summary
    print(f"\n{'='*60}")
    print(f"  Factor Monitor 완료")
    print(f"  IC 계산: {len(ic_results)}건")
    print(f"  가중치 최적화: {'수행' if weights_result else '스킵 (월초 아님)'}")
    print(f"{'='*60}")

    return {
        "ic_results": ic_results,
        "weights": weights_result,
        "ok": 1,
    }


# 하위호환 alias
run_all = run_factor_monitor


if __name__ == "__main__":
    import sys
    d = None
    if len(sys.argv) > 1:
        d = date.fromisoformat(sys.argv[1])
    run_factor_monitor(d)
