#!/usr/bin/env python3
"""
test_v33.py — QUANT AI v3.3 모듈 테스트 스크립트
===================================================
기존 서버 영향 없이 v3.3 신규 모듈만 단독 검증합니다.
DB 불필요 — 합성 데이터로 로직만 확인.

실행:
  cd ~/backend
  python test_v33.py

기대 결과:
  모든 TEST PASS → "✅ v3.3 모듈 테스트 전체 통과!"
"""
import sys
import os
import traceback

# backend/ 경로 추가 (패키지 import 가능하도록)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pandas as pd
from datetime import date, timedelta

passed = 0
failed = 0

def run_test(name, func):
    global passed, failed
    try:
        func()
        print(f"  ✅ {name}")
        passed += 1
    except Exception as e:
        print(f"  ❌ {name}: {e}")
        traceback.print_exc()
        failed += 1


# ═══════════════════════════════════════════════════════════
print("=" * 60)
print("  QUANT AI v3.3 — 모듈 테스트")
print("=" * 60)


# ── TEST 1: DynamicConfig (국면별 파라미터 전환) ──
def test_dynamic_config():
    from risk.trading_config import DynamicConfig

    cfg = DynamicConfig()
    cfg.apply_regime("BULL")
    assert cfg.max_positions == 20, f"BULL max_pos={cfg.max_positions}"
    assert cfg.cash_minimum == 0.10

    cfg.apply_regime("CRISIS")
    assert cfg.max_positions == 5
    assert cfg.cash_minimum == 0.60
    assert cfg.buy_score_min == 90

    # DD 오버라이드
    cfg.apply_regime("NEUTRAL")
    cfg.apply_dd_override("WARNING")
    assert cfg.buy_allowed == False, "WARNING이면 매수 불가"
    assert cfg.cash_minimum >= 0.40

    cfg.apply_dd_override("EMERGENCY")
    assert cfg.effective_position_mult == 0.0, "EMERGENCY면 포지션 0"

print("\n── risk/ 패키지 ──")
run_test("DynamicConfig 국면 전환", test_dynamic_config)


# ── TEST 2: Drawdown Controller ──
def test_drawdown_controller():
    from risk.drawdown_controller import DrawdownController, DDMode

    ddc = DrawdownController(cooldown_days=5)
    today = date(2026, 3, 20)

    # NORMAL
    s = ddc.evaluate(today, 100000, 100000)
    assert s.mode == DDMode.NORMAL
    assert s.buy_allowed == True

    # CAUTION (-4%)
    s = ddc.evaluate(today, 96000, 100000)
    assert s.mode == DDMode.CAUTION
    assert s.position_size_mult <= 0.7

    # WARNING (-6%)
    s = ddc.evaluate(today, 94000, 100000)
    assert s.mode == DDMode.WARNING
    assert s.buy_allowed == False

    # DANGER (-9%)
    s = ddc.evaluate(today, 91000, 100000)
    assert s.mode == DDMode.DANGER
    assert s.force_reduce == True

    # EMERGENCY (-12%)
    s = ddc.evaluate(today, 88000, 100000)
    assert s.mode == DDMode.EMERGENCY
    assert s.force_liquidate == True
    assert s.cooldown_until is not None

run_test("Drawdown Controller 5단계", test_drawdown_controller)


# ── TEST 3: Circuit Breaker ──
def test_circuit_breaker():
    from risk.circuit_breaker import CircuitBreaker, CBLevel

    cb = CircuitBreaker()
    today = date(2026, 3, 20)

    # 5연패
    for _ in range(5):
        cb.record_trade(-100)
    s = cb.evaluate(today)
    assert s.level == CBLevel.HALT
    assert s.buy_allowed == False

    # 수익 거래 → 리셋
    cb.record_trade(500)  # 수익 → 연패 리셋 + halt 해제
    s = cb.evaluate(today)
    assert s.level == CBLevel.CLEAR, f"수익 후 CLEAR여야 함: {s.level}"
    assert s.buy_allowed == True

run_test("Circuit Breaker 연패 감지", test_circuit_breaker)


# ── TEST 4: Risk Manager 8중 안전장치 ──
def test_risk_manager():
    from risk.risk_manager import check_position_risk

    # Hard Stop 트리거
    r = check_position_risk(
        entry_price=100, current_price=88, highest_price=110,
        atr_14=3, atr_20d_avg=2.5, stop_loss_price=90,
        trailing_stop=95, final_score=45, recent_scores=[45, 48, 50],
        signal="SELL", holding_days=30, volume_today=500000, volume_20d_avg=1000000,
    )
    assert r.should_sell == True
    assert r.reason == "HARD_STOP"

    # Time Decay (60일 + 3% 수익)
    r2 = check_position_risk(
        entry_price=100, current_price=103, highest_price=105,
        atr_14=2, atr_20d_avg=2, stop_loss_price=94,
        trailing_stop=100, final_score=65, recent_scores=[65, 64, 63],
        signal="HOLD", holding_days=65, volume_today=800000, volume_20d_avg=1000000,
    )
    assert r2.should_sell == True
    assert "TIME_DECAY" in r2.reason

run_test("Risk Manager 8중 안전장치", test_risk_manager)


# ── TEST 5: Correlation Filter ──
def test_correlation_filter():
    from portfolio.correlation_filter import CorrelationFilter

    np.random.seed(42)
    n = 100
    base = np.cumsum(np.random.randn(n) * 0.02)
    prices = pd.DataFrame({
        "AAPL": np.exp(base + np.random.randn(n) * 0.005),
        "MSFT": np.exp(base + np.random.randn(n) * 0.005),  # AAPL과 높은 상관
        "JNJ":  np.exp(np.cumsum(np.random.randn(n) * 0.01)),  # 독립
    })

    cf = CorrelationFilter(threshold=0.75)

    # MSFT 보유 중 AAPL 진입 → 차단
    check = cf.check_entry("AAPL", ["MSFT"], prices)
    assert check.passed == False, "높은 상관 → 차단"

    # MSFT 보유 중 JNJ 진입 → 통과
    check2 = cf.check_entry("JNJ", ["MSFT"], prices)
    assert check2.passed == True, "낮은 상관 → 통과"

print("\n── portfolio/ 패키지 ──")
run_test("Correlation Filter 상관 필터", test_correlation_filter)


# ── TEST 6: Sector Rotation ──
def test_sector_rotation():
    from portfolio.sector_rotation import SectorRotation

    sr = SectorRotation()
    for regime in ["BULL", "NEUTRAL", "BEAR", "CRISIS"]:
        prefs = sr.get_sector_preferences(regime)
        total = sum(p.adjusted_weight for p in prefs.values())
        assert abs(total - 1.0) < 0.01, f"{regime} 비중합 {total}"

    # BEAR에서 Utilities 비중 상승
    bull = sr.get_sector_preferences("BULL")
    bear = sr.get_sector_preferences("BEAR")
    assert bear["55"].adjusted_weight > bull["55"].adjusted_weight

run_test("Sector Rotation 국면별 섹터", test_sector_rotation)


# ── TEST 7: Transaction Cost ──
def test_transaction_cost():
    from portfolio.transaction_cost import TransactionCostModel

    tcm = TransactionCostModel()
    cost = tcm.estimate_cost("AAPL", "BUY", 100, 185.0, adv_shares=50_000_000)
    assert cost.total_cost_pct < 0.005, f"소규모 비용 {cost.total_cost_pct}"

    budget = tcm.check_turnover_budget(100000, 0.25, 15000, 8000)
    assert budget.can_trade == True
    budget2 = tcm.check_turnover_budget(100000, 0.25, 23000, 8000)
    assert budget2.can_trade == False

run_test("Transaction Cost 거래비용", test_transaction_cost)


# ── TEST 8: Position Sizer ──
def test_position_sizer():
    from portfolio.position_sizer import calculate_position_size

    ps = calculate_position_size(
        ticker="NVDA", current_price=890, atr_14=25,
        final_score=85, grade="S", regime="BULL",
        account_value=100000, current_invested=30000,
        sector="45", sector_invested={"45": 10000},
        num_positions=5, dd_mult=1.0, cb_mult=1.0,
    )
    assert ps.shares > 0, "매수 수량 > 0"
    assert ps.weight_pct <= 10.0, f"비중 {ps.weight_pct}% > 10%"
    assert ps.stop_loss_price > 0

    # DD DANGER → 사이징 축소
    ps2 = calculate_position_size(
        ticker="NVDA", current_price=890, atr_14=25,
        final_score=85, grade="S", regime="BULL",
        account_value=100000, current_invested=30000,
        sector="45", sector_invested={"45": 10000},
        num_positions=5, dd_mult=0.3, cb_mult=0.5,
    )
    assert ps2.shares < ps.shares, f"DD+CB 축소: {ps.shares} → {ps2.shares}"

run_test("Position Sizer Kelly+DD", test_position_sizer)


# ── TEST 9: Regime Detector v2 ──
def test_regime_detector():
    # ※ Python 내장 signal 모듈과 이름 충돌 우회
    #   signal/ 또는 signals/ 어느 쪽이든 동작하도록 importlib 직접 로드
    import importlib.util as _ilu
    rd_path = None
    for _folder in ["signals", "signal"]:
        _candidate = os.path.join(os.path.dirname(os.path.abspath(__file__)), _folder, "regime_detector.py")
        if os.path.exists(_candidate):
            rd_path = _candidate
            break
    assert rd_path is not None, "signal(s)/regime_detector.py 파일을 찾을 수 없습니다"
    _spec = _ilu.spec_from_file_location("_regime_detector", rd_path)
    _mod = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    detect_regime = _mod.detect_regime

    dates = pd.date_range("2025-01-01", periods=250, freq="B")

    # BULL
    np.random.seed(42)
    bull = pd.Series(np.exp(np.cumsum(np.random.randn(250)*0.008+0.0005))*500, index=dates)
    r = detect_regime(bull, vix_close=14)
    assert r.regime == "BULL", f"Expected BULL: {r.regime}"

    # CRISIS
    crisis = pd.Series(np.exp(np.cumsum(np.random.randn(250)*0.02-0.003))*500, index=dates)
    r2 = detect_regime(crisis, vix_close=42)
    assert r2.regime in ("BEAR", "CRISIS"), f"Expected BEAR/CRISIS: {r2.regime}"

print("\n── signal/ 패키지 ──")
run_test("Regime Detector 5지표 앙상블", test_regime_detector)


# ── TEST 10: Performance Attribution ──
def test_attribution():
    from analytics.performance_attribution import PerformanceAttribution

    pa = PerformanceAttribution()
    positions = {
        "NVDA": {"sector": "45", "weight": 0.15, "position_value": 15000},
        "JNJ":  {"sector": "35", "weight": 0.10, "position_value": 10000},
    }
    returns = {"NVDA": 0.08, "JNJ": -0.02}
    bench = {"45": 0.04, "35": 0.01}

    # ※ Brinson-Fachler 정합성: total_benchmark = Σ(wb × rb) 여야 분해합 = active_return
    #   bench에 없는 섹터 rb=0이므로, implied = 0.30*0.04 + 0.13*0.01 = 0.0133
    sp500_w = {"45": 0.30, "35": 0.13, "40": 0.13, "25": 0.10,
               "50": 0.09, "20": 0.09, "30": 0.06, "10": 0.04,
               "55": 0.02, "60": 0.02, "15": 0.02}
    implied_bench = sum(sp500_w.get(s, 0) * bench.get(s, 0) for s in sp500_w)

    report = pa.calculate(date(2026,3,14), date(2026,3,21), positions, returns, bench, implied_bench)

    bk_sum = report.total_allocation + report.total_selection + report.total_interaction
    assert abs(bk_sum - report.active_return) < 0.01, f"분해 합 불일치: {bk_sum} vs {report.active_return}"

print("\n── analytics/ 패키지 ──")
run_test("Performance Attribution", test_attribution)


# ── TEST 11: Decision Audit ──
def test_audit():
    from analytics.decision_audit import DecisionAudit, AuditRecord

    audit = DecisionAudit(calc_date=date(2026,3,20), regime="BULL", dd_mode="NORMAL")
    rec = audit.create_record(stock_id=1, ticker="NVDA")
    rec.final_score = 85
    rec.score_filter = True
    rec.rsi_filter = True
    rec.regime_filter = True
    rec.dd_filter = True
    rec.liquidity_filter = True
    rec.correlation_filter = True
    rec.circuit_breaker_filter = True
    rec.turnover_filter = True
    rec.decision = "BUY"
    audit.add(rec)

    rec2 = audit.create_record(stock_id=2, ticker="INTC")
    rec2.final_score = 42
    rec2.score_filter = False
    rec2.decision = "SKIP"
    audit.add(rec2)

    assert audit.count("BUY") == 1
    assert audit.count("SKIP") == 1
    assert rec.all_filters_passed == True
    assert rec2.all_filters_passed == False
    assert "SCORE" in rec2.blocking_filters

run_test("Decision Audit 의사결정 기록", test_audit)


# ═══════════════════════════════════════════════════════════
#  결과 요약
# ═══════════════════════════════════════════════════════════
print(f"\n{'='*60}")
print(f"  결과: ✅ {passed} PASS / ❌ {failed} FAIL")
print(f"{'='*60}")

if failed == 0:
    print("\n  🎉 v3.3 모듈 테스트 전체 통과!")
    print("  → DDL 실행 후 DB 연동 테스트 가능")
else:
    print(f"\n  ⚠️ {failed}건 실패 — 위 오류 확인 후 재시도")
    sys.exit(1)
