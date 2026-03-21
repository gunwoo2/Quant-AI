"""
analytics/decision_audit.py — 의사결정 감사 로그
===================================================
모든 BUY/SELL/HOLD/SKIP 결정에 대해 "왜" 기록.

사후 분석:
  - "왜 NVDA를 안 샀지?" → 필터 확인
  - 필터별 hit rate 분석 → 모델 개선
  - 규제 대응: 모든 결정에 근거 존재
"""
from dataclasses import dataclass, field, asdict
from datetime import date
from typing import Optional, List


@dataclass
class AuditRecord:
    """단일 의사결정 기록"""
    decision_date: date = None
    stock_id: int = 0
    ticker: str = ""
    decision: str = ""          # BUY / SELL / HOLD / SKIP / ADD / FIRE / BOUNCE

    # 입력 데이터
    final_score: float = 0
    layer1_score: float = 0
    layer2_score: float = 0
    layer3_score: float = 0
    rsi_14: float = 0
    atr_14: float = 0
    current_price: float = 0
    regime: str = ""
    dd_mode: str = ""

    # 필터 통과 여부 (True = 통과, False = 차단)
    score_filter: bool = False
    rsi_filter: bool = False
    regime_filter: bool = False
    dd_filter: bool = False
    liquidity_filter: bool = False
    correlation_filter: bool = False
    circuit_breaker_filter: bool = False
    turnover_filter: bool = False

    # 결과
    reason: str = ""
    position_size: float = 0
    stop_loss_price: float = 0

    @property
    def all_filters_passed(self) -> bool:
        return all([
            self.score_filter, self.rsi_filter, self.regime_filter,
            self.dd_filter, self.liquidity_filter, self.correlation_filter,
            self.circuit_breaker_filter, self.turnover_filter,
        ])

    @property
    def blocking_filters(self) -> List[str]:
        blocked = []
        if not self.score_filter: blocked.append("SCORE")
        if not self.rsi_filter: blocked.append("RSI")
        if not self.regime_filter: blocked.append("REGIME")
        if not self.dd_filter: blocked.append("DD_MODE")
        if not self.liquidity_filter: blocked.append("LIQUIDITY")
        if not self.correlation_filter: blocked.append("CORRELATION")
        if not self.circuit_breaker_filter: blocked.append("CIRCUIT_BREAKER")
        if not self.turnover_filter: blocked.append("TURNOVER")
        return blocked


class DecisionAudit:
    """
    의사결정 감사 로그 수집 + DB 저장.

    사용법:
        audit = DecisionAudit(calc_date=today, regime="BULL", dd_mode="NORMAL")

        # 매수 결정 기록
        rec = audit.create_record(stock_id=1, ticker="NVDA")
        rec.final_score = 85.3
        rec.score_filter = True
        rec.rsi_filter = True
        ...
        rec.decision = "BUY"
        rec.reason = "All filters passed"
        audit.add(rec)

        # 스킵 결정 기록
        rec2 = audit.create_record(stock_id=2, ticker="INTC")
        rec2.final_score = 42.1
        rec2.score_filter = False
        rec2.decision = "SKIP"
        rec2.reason = "Score below minimum (42.1 < 70)"
        audit.add(rec2)

        # DB 저장
        audit.save_to_db()
        audit.print_summary()
    """

    def __init__(self, calc_date: date, regime: str = "", dd_mode: str = ""):
        self.calc_date = calc_date
        self.regime = regime
        self.dd_mode = dd_mode
        self.records: List[AuditRecord] = []

    def create_record(self, stock_id: int = 0, ticker: str = "") -> AuditRecord:
        """새 레코드 생성 (기본값 채운 상태)"""
        return AuditRecord(
            decision_date=self.calc_date,
            stock_id=stock_id,
            ticker=ticker,
            regime=self.regime,
            dd_mode=self.dd_mode,
        )

    def add(self, record: AuditRecord):
        """레코드 추가"""
        self.records.append(record)

    def save_to_db(self):
        """전체 레코드 DB 일괄 저장"""
        if not self.records:
            return

        from db_pool import get_cursor

        with get_cursor() as cur:
            for r in self.records:
                cur.execute("""
                    INSERT INTO decision_audit
                        (decision_date, stock_id, ticker, decision,
                         final_score, layer1_score, layer2_score, layer3_score,
                         rsi_14, atr_14, current_price, regime, dd_mode,
                         score_filter, rsi_filter, regime_filter, dd_filter,
                         liquidity_filter, correlation_filter, circuit_breaker_filter, turnover_filter,
                         reason, position_size, stop_loss_price)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    r.decision_date, r.stock_id, r.ticker, r.decision,
                    r.final_score, r.layer1_score, r.layer2_score, r.layer3_score,
                    r.rsi_14, r.atr_14, r.current_price, r.regime, r.dd_mode,
                    r.score_filter, r.rsi_filter, r.regime_filter, r.dd_filter,
                    r.liquidity_filter, r.correlation_filter, r.circuit_breaker_filter, r.turnover_filter,
                    r.reason, r.position_size, r.stop_loss_price,
                ))

        print(f"  ✅ Audit 저장: {len(self.records)}건 (BUY={self.count('BUY')} SELL={self.count('SELL')} SKIP={self.count('SKIP')})")

    def count(self, decision: str) -> int:
        return sum(1 for r in self.records if r.decision == decision)

    def print_summary(self):
        """감사 요약 출력"""
        total = len(self.records)
        by_decision = {}
        for r in self.records:
            by_decision[r.decision] = by_decision.get(r.decision, 0) + 1

        # 필터별 차단 통계
        filter_blocks = {}
        skip_records = [r for r in self.records if r.decision == "SKIP"]
        for r in skip_records:
            for f in r.blocking_filters:
                filter_blocks[f] = filter_blocks.get(f, 0) + 1

        print(f"\n  📋 Audit Summary ({self.calc_date})")
        print(f"  총 {total}건: {by_decision}")
        if filter_blocks:
            print(f"  필터별 차단: {filter_blocks}")

    def get_filter_stats(self) -> dict:
        """필터별 통과/차단 비율 (모델 개선용)"""
        stats = {}
        filters = ["score", "rsi", "regime", "dd", "liquidity", "correlation", "circuit_breaker", "turnover"]
        for f_name in filters:
            attr = f"{f_name}_filter"
            passed = sum(1 for r in self.records if getattr(r, attr, False))
            total = len(self.records)
            stats[f_name] = {
                "passed": passed,
                "blocked": total - passed,
                "pass_rate": passed / total if total > 0 else 0,
            }
        return stats
