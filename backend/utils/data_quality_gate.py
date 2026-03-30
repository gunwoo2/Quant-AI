"""
utils/data_quality_gate.py — Data Quality Gate v1.0
====================================================
Day 1 신규 모듈 | 설계 원칙 2 "Graceful Degradation" 구현체

매일 배치 최초 Step (Step 0)으로 실행되어:
  1. 각 데이터 소스의 결측률/이상치/최신성 검사
  2. 기준 미달 소스 → DEGRADED(50% 감소) 또는 DISABLED(차단)
  3. 나머지 소스로 가중치 재정규화
  4. 모든 판단을 system_telemetry에 기록

사용:
  gate = DataQualityGate(calc_date)
  status = gate.check_all()
  multipliers = gate.get_weight_multipliers()
  → batch_final_score.py에서 multipliers 적용
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
import json
from datetime import date, datetime
from enum import Enum
from db_pool import get_cursor

logger = logging.getLogger("data_quality_gate")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 상태 정의
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class SourceStatus(Enum):
    OK       = "OK"         # 정상 → 가중치 유지
    DEGRADED = "DEGRADED"   # 부분 결측 → 가중치 50% 감소
    DISABLED = "DISABLED"   # 사용 불가 → 가중치 0, 나머지 재정규화
    STALE    = "STALE"      # 오래됨(>N일) → DEGRADED 취급


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 품질 기준 상수
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# (결측률 max, 노후 max일, 이상치 max, 최소 샘플수)
QUALITY_THRESHOLDS = {
    "L1_FUNDAMENTAL":  {"miss_max": 0.05, "stale_max": 3, "anomaly_max": 0.02, "min_samples": 300},
    "L2_SENTIMENT":    {"miss_max": 0.20, "stale_max": 5, "anomaly_max": 0.05, "min_samples": 200},
    "L3_TECHNICAL":    {"miss_max": 0.10, "stale_max": 2, "anomaly_max": 0.03, "min_samples": 300},
    "L3_FLOW_MACRO":   {"miss_max": 0.25, "stale_max": 3, "anomaly_max": 0.10, "min_samples": 100},
    "CROSS_ASSET":     {"miss_max": 0.05, "stale_max": 2, "anomaly_max": 0.05, "min_samples": 10},
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 테이블 보장
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def ensure_telemetry_table():
    """system_telemetry 테이블 생성 (없으면)"""
    with get_cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS system_telemetry (
                id           SERIAL PRIMARY KEY,
                calc_date    DATE NOT NULL,
                category     VARCHAR(50) NOT NULL,
                metric_name  VARCHAR(100) NOT NULL,
                metric_value NUMERIC(12,6),
                detail       JSONB,
                created_at   TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_telemetry_date_cat
            ON system_telemetry(calc_date, category)
        """)
    print("[DQ-GATE] ✅ system_telemetry 테이블 확인")


def ensure_gatekeeper_table():
    """model_gatekeeper_log 테이블 생성 (없으면)"""
    with get_cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS model_gatekeeper_log (
                id           SERIAL PRIMARY KEY,
                calc_date    DATE NOT NULL,
                model_type   VARCHAR(50),
                oos_ic       NUMERIC(8,6),
                oos_auc      NUMERIC(8,6),
                decision     VARCHAR(20),
                reason       TEXT,
                created_at   TIMESTAMPTZ DEFAULT NOW()
            )
        """)
    print("[DQ-GATE] ✅ model_gatekeeper_log 테이블 확인")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 메인 클래스
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class DataQualityGate:
    """
    매일 배치 시작 전 데이터 품질 관문.

    동작 순서:
      1. 각 소스별 결측률, 이상치, 최신성 검사
      2. 기준 미달 소스 → DEGRADED 또는 DISABLED
      3. 가중치 승수(multiplier) 생성
      4. system_telemetry에 기록
    """

    def __init__(self, calc_date: date):
        self.calc_date = calc_date
        self.results = {}

    def check_all(self) -> dict:
        """전체 소스 검사 → {소스명: SourceStatus} 반환"""
        checks = {
            "L1_FUNDAMENTAL": self._check_l1,
            "L2_SENTIMENT":   self._check_l2,
            "L3_TECHNICAL":   self._check_l3,
            "L3_FLOW_MACRO":  self._check_l3_flow,
            "CROSS_ASSET":    self._check_cross_asset,
        }

        for source_name, check_fn in checks.items():
            try:
                result = check_fn()
                self.results[source_name] = result
                status_str = result["status"].value
                if result["status"] != SourceStatus.OK:
                    logger.warning(
                        f"[DQ-GATE] {source_name}: {status_str} "
                        f"(miss={result['missing_rate']:.1%}, "
                        f"stale={result['stale_days']}d, "
                        f"samples={result['sample_count']})"
                    )
                else:
                    print(f"  [DQ-GATE] {source_name}: OK "
                          f"(miss={result['missing_rate']:.1%}, samples={result['sample_count']})")
            except Exception as e:
                logger.error(f"[DQ-GATE] {source_name} 검사 실패: {e}")
                self.results[source_name] = {
                    "status": SourceStatus.DISABLED,
                    "missing_rate": 1.0, "stale_days": 999,
                    "anomaly_rate": 0, "sample_count": 0,
                    "detail": f"검사 실패: {e}",
                }

        self._record_telemetry()

        return {name: r["status"] for name, r in self.results.items()}

    def get_weight_multipliers(self) -> dict:
        """
        품질 검사 결과 → 레이어 가중치 승수(multiplier) 반환.

        OK       → 1.0
        DEGRADED → 0.5
        STALE    → 0.5
        DISABLED → 0.0

        batch_final_score.py에서: adjusted_w = base_weight * multiplier → 정규화
        """
        multipliers = {}
        for name, result in self.results.items():
            s = result["status"]
            if s == SourceStatus.OK:
                multipliers[name] = 1.0
            elif s in (SourceStatus.DEGRADED, SourceStatus.STALE):
                multipliers[name] = 0.5
            else:
                multipliers[name] = 0.0
        return multipliers

    # ── 개별 소스 검사 ──

    def _check_l1(self) -> dict:
        """L1 재무 데이터 품질 검사"""
        th = QUALITY_THRESHOLDS["L1_FUNDAMENTAL"]
        with get_cursor() as cur:
            cur.execute("""
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE moat_score IS NULL OR value_score IS NULL) AS missing,
                    COUNT(*) FILTER (WHERE moat_score > 100 OR value_score > 100
                                       OR moat_score < 0 OR value_score < 0) AS anomaly,
                    MAX(calc_date) AS last_date
                FROM stock_layer1_analysis
                WHERE calc_date >= %s - INTERVAL '5 days'
            """, (self.calc_date,))
            row = cur.fetchone()
        return self._evaluate("L1_FUNDAMENTAL", th, row)

    def _check_l2(self) -> dict:
        """L2 NLP/감성 데이터 품질 검사"""
        th = QUALITY_THRESHOLDS["L2_SENTIMENT"]
        with get_cursor() as cur:
            cur.execute("""
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE news_sentiment_score IS NULL
                                       AND analyst_rating_score IS NULL) AS missing,
                    COUNT(*) FILTER (WHERE ABS(news_sentiment_score) > 200) AS anomaly,
                    MAX(calc_date) AS last_date
                FROM layer2_scores
                WHERE calc_date >= %s - INTERVAL '7 days'
            """, (self.calc_date,))
            row = cur.fetchone()
        return self._evaluate("L2_SENTIMENT", th, row)

    def _check_l3(self) -> dict:
        """L3 기술지표 품질 검사"""
        th = QUALITY_THRESHOLDS["L3_TECHNICAL"]
        with get_cursor() as cur:
            cur.execute("""
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE section_a_technical IS NULL) AS missing,
                    COUNT(*) FILTER (WHERE section_a_technical > 100
                                       OR section_a_technical < -10) AS anomaly,
                    MAX(calc_date) AS last_date
                FROM technical_indicators
                WHERE calc_date >= %s - INTERVAL '5 days'
            """, (self.calc_date,))
            row = cur.fetchone()
        return self._evaluate("L3_TECHNICAL", th, row)

    def _check_l3_flow(self) -> dict:
        """L3 수급/매크로 품질 검사"""
        th = QUALITY_THRESHOLDS["L3_FLOW_MACRO"]
        with get_cursor() as cur:
            cur.execute("""
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE section_b_flow IS NULL
                                       AND section_c_macro IS NULL) AS missing,
                    COUNT(*) FILTER (WHERE section_b_flow > 50
                                       OR section_c_macro > 50) AS anomaly,
                    MAX(calc_date) AS last_date
                FROM technical_indicators
                WHERE calc_date >= %s - INTERVAL '5 days'
                  AND (section_b_flow IS NOT NULL OR section_c_macro IS NOT NULL)
            """, (self.calc_date,))
            row = cur.fetchone()
        return self._evaluate("L3_FLOW_MACRO", th, row)

    def _check_cross_asset(self) -> dict:
        """Cross-Asset 품질 검사"""
        th = QUALITY_THRESHOLDS["CROSS_ASSET"]
        with get_cursor() as cur:
            cur.execute("""
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE risk_appetite_idx IS NULL) AS missing,
                    COUNT(*) FILTER (WHERE ABS(risk_appetite_idx) > 20) AS anomaly,
                    MAX(calc_date) AS last_date
                FROM cross_asset_daily
                WHERE calc_date >= %s - INTERVAL '5 days'
            """, (self.calc_date,))
            row = cur.fetchone()
        return self._evaluate("CROSS_ASSET", th, row)

    # ── 공통 평가 ──

    def _evaluate(self, source_name: str, th: dict, row) -> dict:
        """DB 쿼리 결과 → 상태 판정"""
        total = int(row["total"]) if row and row["total"] else 0
        missing = int(row["missing"]) if row and row["missing"] else 0
        anomaly = int(row["anomaly"]) if row and row["anomaly"] else 0
        last_date = row["last_date"] if row else None

        missing_rate = missing / max(total, 1)
        anomaly_rate = anomaly / max(total, 1)
        stale_days = (self.calc_date - last_date).days if last_date else 999

        # 단계적 판정
        if total < th["min_samples"]:
            status = SourceStatus.DISABLED
            detail = f"샘플 부족: {total} < {th['min_samples']}"
        elif missing_rate > th["miss_max"] * 2 or stale_days > th["stale_max"] * 3:
            status = SourceStatus.DISABLED
            detail = f"심각: miss={missing_rate:.1%}, stale={stale_days}d"
        elif missing_rate > th["miss_max"] or anomaly_rate > th["anomaly_max"]:
            status = SourceStatus.DEGRADED
            detail = f"부분 결함: miss={missing_rate:.1%}, anom={anomaly_rate:.1%}"
        elif stale_days > th["stale_max"]:
            status = SourceStatus.STALE
            detail = f"갱신 지연: {stale_days}일"
        else:
            status = SourceStatus.OK
            detail = "정상"

        return {
            "status": status,
            "missing_rate": round(missing_rate, 4),
            "stale_days": stale_days,
            "anomaly_rate": round(anomaly_rate, 4),
            "sample_count": total,
            "detail": detail,
        }

    # ── Telemetry 기록 ──

    def _record_telemetry(self):
        """검사 결과를 system_telemetry에 기록"""
        try:
            ok_count = sum(1 for r in self.results.values()
                          if r["status"] == SourceStatus.OK)
            health_pct = ok_count / max(len(self.results), 1)

            detail_json = {
                name: {
                    "status": r["status"].value,
                    "missing": r["missing_rate"],
                    "stale": r["stale_days"],
                    "samples": r["sample_count"],
                    "detail": r["detail"],
                }
                for name, r in self.results.items()
            }

            with get_cursor() as cur:
                cur.execute("""
                    INSERT INTO system_telemetry
                        (calc_date, category, metric_name, metric_value, detail)
                    VALUES (%s, 'DATA_QUALITY', 'gate_check', %s, %s)
                """, (self.calc_date, health_pct, json.dumps(detail_json, ensure_ascii=False)))

            print(f"  [DQ-GATE] Telemetry 기록 완료 (health={health_pct:.0%})")
        except Exception as e:
            logger.error(f"[DQ-GATE] Telemetry 기록 실패: {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 공개 API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run_data_quality_gate(calc_date: date = None) -> dict:
    """
    scheduler.py Step 0에서 호출.

    Returns:
        {"status_map": {...}, "multipliers": {...}, "health_pct": float}
    """
    if calc_date is None:
        calc_date = date.today()

    print(f"\n[DQ-GATE] === Data Quality Gate — {calc_date} ===")

    ensure_telemetry_table()
    ensure_gatekeeper_table()

    gate = DataQualityGate(calc_date)
    status_map = gate.check_all()
    multipliers = gate.get_weight_multipliers()

    disabled = [k for k, v in status_map.items() if v == SourceStatus.DISABLED]
    degraded = [k for k, v in status_map.items() if v in (SourceStatus.DEGRADED, SourceStatus.STALE)]

    if disabled:
        print(f"  [DQ-GATE] ⚠️  DISABLED 소스: {disabled}")
    if degraded:
        print(f"  [DQ-GATE] ⚡ DEGRADED 소스: {degraded}")

    ok_count = sum(1 for v in status_map.values() if v == SourceStatus.OK)
    health_pct = ok_count / max(len(status_map), 1)
    print(f"  [DQ-GATE] 전체 건강도: {health_pct:.0%} ({ok_count}/{len(status_map)} OK)")

    return {
        "status_map": {k: v.value for k, v in status_map.items()},
        "multipliers": multipliers,
        "health_pct": health_pct,
    }
