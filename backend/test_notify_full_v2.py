#!/usr/bin/env python3
"""
test_notify_full_v4.py — QUANT AI v4.0 전체 알림 테스트
=======================================================
Premium 13웹훅 + Public 5웹훅 = 18개 웹훅 전체 검증.

실행:
  cd ~/Quant-AI/backend
  python test_notify_full_v4.py
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv()

from datetime import date
from notifier import (
    _WEBHOOK_MY, _WEBHOOK_PUB, _FALLBACK_URL,
    notify_morning_briefing,
    notify_daily_signals,
    notify_add_position,
    notify_fire_sell,
    notify_bounce_opportunity,
    notify_risk_warning,
    notify_grade_changes,
    notify_regime_change,
    notify_weekly_report,
    notify_batch_start,
    notify_batch_complete,
    notify_daily_performance,
    notify_earnings_alert,
    notify_emergency,
    notify_weekly_rebalance,
    notify_backtest_result,
    notify_price_fetch_failure,
    check_price_freshness,
)

TODAY = date.today()
DELAY = 1.5

print("=" * 64)
print("  QUANT AI v4.0 — 18웹훅 전체 알림 테스트")
print("=" * 64)

# ── 웹훅 상태 ──
print("\n── 🔒 Premium (MY) 웹훅 ──")
my_cnt = 0
for key, url in _WEBHOOK_MY.items():
    status = "✅" if url else "❌"
    if url: my_cnt += 1
    print(f"  MY_{key:12s} : {status}")

print(f"\n── 📢 Public (PUB) 웹훅 ──")
pub_cnt = 0
for key, url in _WEBHOOK_PUB.items():
    status = "✅" if url else "❌"
    if url: pub_cnt += 1
    print(f"  PUB_{key:12s} : {status}")

print(f"\n  FALLBACK: {'✅' if _FALLBACK_URL else '❌'}")
print(f"  Premium: {my_cnt}/{len(_WEBHOOK_MY)} | Public: {pub_cnt}/{len(_WEBHOOK_PUB)}")

if my_cnt + pub_cnt == 0 and not _FALLBACK_URL:
    print("\n⚠️  웹훅 없음! .env 확인하세요.")
    sys.exit(1)

input("\n▶ Enter 누르면 테스트 시작...")


# ── [1] 배치 시작 → MY_SYSTEM + PUB_REPORT ──
print("\n── [1] 배치 시작 ──")
try:
    notify_batch_start(calc_date=TODAY, job_name="Daily Full Pipeline")
    print("  ✅ → MY_SYSTEM + PUB_REPORT")
except Exception as e:
    print(f"  ❌ {e}")
time.sleep(DELAY)


# ── [2] 모닝 브리핑 → MY_MORNING + PUB_MORNING ──
print("\n── [2] 모닝 브리핑 ──")
try:
    notify_morning_briefing(
        calc_date=TODAY, regime="BULL",
        regime_detail={"spy_price": 548.57, "vix_close": 18.3, "sma_200": 520.0,
                       "futures_pct": 0.35, "vix_change_pct": -1.2},
        signal_summary={"buy_count": 3, "sell_count": 1, "fire_count": 0,
                        "add_count": 1, "bounce_count": 2},
        regime_proba={"stay_probability": 0.82, "days_in_regime": 14},
        ic_data={"ic": 0.068, "ic_trend": 0.005},
        hit_rate={"hit_rate": 0.72, "hits": 36, "total": 50},
        fear_greed={"value": 65, "label": "Greed"},
        portfolio_summary={"total_value": 62500, "daily_return": 1.25,
                           "num_positions": 8, "cash_pct": 22.5},
    )
    print("  ✅ → MY_MORNING(상세) + PUB_MORNING(국면+건수)")
except Exception as e:
    print(f"  ❌ {e}")
time.sleep(DELAY)


# ── [3] 매수/매도 → MY_BUY/SELL/PROFIT + PUB_BUY/SELL ──
print("\n── [3] 매수/매도 시그널 ──")
try:
    notify_daily_signals(
        calc_date=TODAY, regime="BULL",
        regime_detail={"spy_price": 548.57, "vix_close": 18.3, "sma_200": 520.0},
        buy_signals=[
            {"ticker": "NVDA", "grade": "S", "score": 93.2, "price": 142.80,
             "shares": 25, "amount": 3570, "weight": 5.7, "stop_loss": 128.52, "stop_pct": 10,
             "sector": "Technology", "l1_score": 88, "l2_score": 92, "l3_score": 95},
            {"ticker": "AAPL", "grade": "A+", "score": 87.5, "price": 235.50,
             "shares": 15, "amount": 3532, "weight": 5.4, "stop_loss": 211.95, "stop_pct": 10,
             "sector": "Technology", "l1_score": 85, "l2_score": 78, "l3_score": 90},
            {"ticker": "JPM", "grade": "A", "score": 82.1, "price": 198.50,
             "shares": 18, "amount": 3573, "weight": 5.5, "stop_loss": 178.65, "stop_pct": 10,
             "sector": "Financials", "l1_score": 90, "l2_score": 72, "l3_score": 68},
        ],
        sell_signals=[
            {"ticker": "NFLX", "reason": "STOP_LOSS", "price": 980.00,
             "entry_price": 1050.00, "holding_days": 12, "pnl_pct": -6.7, "shares": 3,
             "highest_price": 1100.00, "lowest_price": 970.00,
             "entry_score": 78.5, "current_score": 52.3, "entry_grade": "A", "current_grade": "B"},
            {"ticker": "META", "reason": "TAKE_PROFIT", "price": 620.00,
             "entry_price": 510.00, "holding_days": 45, "pnl_pct": 21.6, "shares": 8,
             "highest_price": 635.00, "lowest_price": 505.00,
             "entry_score": 85.0, "current_score": 72.0, "entry_grade": "A+", "current_grade": "A"},
        ],
        portfolio_summary={"total_value": 62500, "daily_return": 1.25,
                           "num_positions": 8, "cash_pct": 22.5},
    )
    print("  ✅ → MY_BUY(투자근거) + PUB_BUY(종목+등급+매수가)")
    print("       MY_SELL(MAE/MFE) + PUB_SELL(사유+매도가)")
    print("       MY_PROFIT(익절분리) + MY_REPORT(포폴현황)")
except Exception as e:
    print(f"  ❌ {e}")
time.sleep(DELAY)


# ── [4] 추가 매수 → MY_ADD ──
print("\n── [4] 추가 매수 ──")
try:
    notify_add_position(calc_date=TODAY, add_signals=[
        {"ticker": "MSFT", "grade": "A", "score": 81.5, "price": 415.00,
         "shares": 5, "pnl_pct": -3.2, "avg_down_pct": -1.5},
    ])
    print("  ✅ → MY_ADD")
except Exception as e:
    print(f"  ❌ {e}")
time.sleep(DELAY)


# ── [5] 긴급 매도 → MY_FIRE ──
print("\n── [5] 긴급 매도 ──")
try:
    notify_fire_sell(calc_date=TODAY, fire_signals=[
        {"ticker": "TSLA", "reason": "CIRCUIT_BREAKER", "price": 165.00,
         "entry_price": 195.00, "pnl_pct": -15.4, "shares": 20},
    ], trigger="VIX 급등 + DD LEVEL 3")
    print("  ✅ → MY_FIRE")
except Exception as e:
    print(f"  ❌ {e}")
time.sleep(DELAY)


# ── [6] 반등 기회 → MY_BOUNCE ──
print("\n── [6] 반등 기회 ──")
try:
    notify_bounce_opportunity(calc_date=TODAY, bounce_signals=[
        {"ticker": "AMZN", "rsi": 28.5, "price": 178.00, "grade": "B+",
         "support_price": 175.00, "drop_pct": -12.3},
    ])
    print("  ✅ → MY_BOUNCE")
except Exception as e:
    print(f"  ❌ {e}")
time.sleep(DELAY)


# ── [7] 리스크 → MY_RISK + PUB_RISK ──
print("\n── [7] 리스크 경고 ──")
try:
    notify_risk_warning(
        calc_date=TODAY, risk_level="YELLOW",
        drawdown={"current_dd": -5.2, "dd_days": 8, "mdd": -8.5},
        var_data={"var_95_pct": -2.0, "var_99_pct": -3.6,
                  "var_95_dollar": 1050, "var_99_dollar": 1890},
        concentration={"top_sector": {"name": "Technology", "pct": 42, "limit": 35},
                        "top_stock": {"ticker": "NVDA", "pct": 8.2, "limit": 10}},
        defense_status={"dd_mode": "CAUTION", "cb_active": False, "buy_limit_pct": 3},
        stress_test={"2020 COVID": {"impact_pct": -24.5}, "2022 금리": {"impact_pct": -13.8},
                     "VIX 급등": {"impact_pct": -5.9}},
        correlation={"avg_correlation": 0.65, "top_pair": "NVDA↔AMD 0.89"},
    )
    print("  ✅ → MY_RISK(풀대시보드) + PUB_RISK(시장상황)")
except Exception as e:
    print(f"  ❌ {e}")
time.sleep(DELAY)


# ── [8] 등급 변경 → MY_ALERT + PUB_REPORT ──
print("\n── [8] 등급 변경 ──")
try:
    notify_grade_changes(calc_date=TODAY, changes=[
        {"ticker": "GOOGL", "old_grade": "B+", "new_grade": "A",
         "old_score": 74.5, "new_score": 82.0, "reason": "L2 NLP 급상승"},
        {"ticker": "BA", "old_grade": "B", "new_grade": "C",
         "old_score": 68.0, "new_score": 55.2, "reason": "L1 수익성 악화"},
    ])
    print("  ✅ → MY_ALERT(상세) + PUB_REPORT(요약)")
except Exception as e:
    print(f"  ❌ {e}")
time.sleep(DELAY)


# ── [9] 국면 전환 → MY_ALERT + PUB_REPORT ──
print("\n── [9] 국면 전환 ──")
try:
    notify_regime_change(
        calc_date=TODAY, old_regime="BULL", new_regime="NEUTRAL",
        trigger_detail={"spy_price": 535.00, "vix_close": 25.8,
                        "trigger_reason": "SPY SMA200 하회 + VIX 25 돌파",
                        "impact": "신규 매수 50% 축소, 방어 모드 전환"},
    )
    print("  ✅ → MY_ALERT + PUB_REPORT")
except Exception as e:
    print(f"  ❌ {e}")
time.sleep(DELAY)


# ── [10] 주간 리포트 → MY_REPORT + PUB_REPORT ──
print("\n── [10] 주간 리포트 ──")
try:
    notify_weekly_report(
        calc_date=TODAY, week_return=2.34, mtd_return=3.82, ytd_return=12.4,
        since_inception=18.7, sharpe=1.85, sortino=2.42,
        alpha=0.72, beta=0.88, win_rate=68.5, num_trades=12,
        best_ticker="NVDA", best_pnl=8.5, worst_ticker="BA", worst_pnl=-4.2,
        brinson={"market_effect": 1.62, "selection_effect": 0.92, "cash_drag": -0.20},
    )
    print("  ✅ → MY_REPORT(Brinson) + PUB_REPORT(간결)")
except Exception as e:
    print(f"  ❌ {e}")
time.sleep(DELAY)


# ── [11] 일일 성과 → MY_PERF ──
print("\n── [11] 일일 성과 ──")
try:
    notify_daily_performance(
        calc_date=TODAY, daily_return=1.25, total_value=62500, spy_return=0.85,
        num_positions=8,
        top_gainer={"ticker": "NVDA", "pnl": 3.8},
        top_loser={"ticker": "BA", "pnl": -1.2},
        sector_perf={"Technology": 2.1, "Financials": 0.8, "Healthcare": -0.5},
    )
    print("  ✅ → MY_PERF")
except Exception as e:
    print(f"  ❌ {e}")
time.sleep(DELAY)


# ── [12] 어닝 임박 → MY_ALERT ──
print("\n── [12] 어닝 임박 ──")
try:
    notify_earnings_alert(calc_date=TODAY, tickers=[
        {"ticker": "AAPL", "date": "2026-04-01"},
        {"ticker": "MSFT", "date": "2026-04-02"},
    ], days_until=3)
    print("  ✅ → MY_ALERT")
except Exception as e:
    print(f"  ❌ {e}")
time.sleep(DELAY)


# ── [13] 리밸런싱 → MY_REPORT ──
print("\n── [13] 리밸런싱 ──")
try:
    notify_weekly_rebalance(calc_date=TODAY, rebalance_data=[
        {"ticker": "NVDA", "old_weight": 8.2, "new_weight": 6.5, "action": "REDUCE", "shares": 5},
    ])
    print("  ✅ → MY_REPORT")
except Exception as e:
    print(f"  ❌ {e}")
time.sleep(DELAY)


# ── [14] 백테스트 → MY_BACKTEST ──
print("\n── [14] 백테스트 ──")
try:
    notify_backtest_result(
        period_start=date(2024, 1, 1), period_end=date(2024, 12, 31),
        total_return=28.5, annual_return=28.5, max_drawdown=-12.3,
        sharpe_ratio=1.85, win_rate=68.5, spy_alpha=5.2,
        num_trades=156, avg_holding_days=18,
    )
    print("  ✅ → MY_BACKTEST")
except Exception as e:
    print(f"  ❌ {e}")
time.sleep(DELAY)


# ── [15] 데이터 품질 → MY_SYSTEM ──
print("\n── [15] 데이터 품질 ──")
try:
    notify_price_fetch_failure(tickers=["RIVN", "LCID"], source="FMP")
    check_price_freshness(stale_tickers=["PLTR", "COIN"], threshold_hours=48)
    print("  ✅ → MY_SYSTEM")
except Exception as e:
    print(f"  ❌ {e}")
time.sleep(DELAY)


# ── [16] 긴급 알림 → MY_FIRE ──
print("\n── [16] 긴급 알림 ──")
try:
    notify_emergency(calc_date=TODAY, message="VIX 40 돌파!", severity="HIGH")
    print("  ✅ → MY_FIRE")
except Exception as e:
    print(f"  ❌ {e}")
time.sleep(DELAY)


# ── [17] 배치 완료 → MY_SYSTEM + PUB_REPORT ──
print("\n── [17] 배치 완료 ──")
try:
    notify_batch_complete(
        calc_date=TODAY, duration_sec=847, job_name="Daily Full Pipeline",
        results={
            "success": 515, "fail": 3, "total": 518,
            "steps": {
                "L1 가격수집": {"ok": True, "duration": "3m 12s"},
                "L2 NLP분석": {"ok": True, "duration": "4m 18s"},
                "L3 기술분석": {"ok": True, "duration": "2m 30s"},
                "최종점수": {"ok": True, "duration": "1m 02s"},
            },
            "errors": ["RIVN: timeout", "LCID: 데이터 없음", "HOOD: 가격 누락"],
        },
    )
    print("  ✅ → MY_SYSTEM(상세) + PUB_REPORT(요약)")
except Exception as e:
    print(f"  ❌ {e}")


# ── 완료 ──
print("\n" + "=" * 64)
print("  ✅ 전체 테스트 완료! (17개 시나리오)")
print("=" * 64)
print("""
  📬 웹훅 18개 전송 요약:

  🔒 Premium (MY)                    📢 Public (PUB)
  ─────────────────────────          ─────────────────────
  MY_MORNING  → 모닝 브리핑          PUB_MORNING → 국면+건수
  MY_BUY      → 투자근거카드          PUB_BUY     → 종목+등급+매수가
  MY_SELL     → MAE/MFE+점수변화      PUB_SELL    → 사유+매도가
  MY_PROFIT   → 익절 분리             PUB_RISK    → 시장 상황
  MY_ADD      → 추가 매수             PUB_REPORT  → 등급/국면/주간/배치
  MY_FIRE     → 긴급 매도
  MY_BOUNCE   → 반등 기회
  MY_RISK     → VaR/Stress/집중도
  MY_ALERT    → 등급변경/국면전환
  MY_PERF     → 일일 성과
  MY_SYSTEM   → 배치+데이터품질
  MY_REPORT   → Brinson+주간
  MY_BACKTEST → 백테스트

  채널 배치 예시:
  #프리미엄_매수  ← MY_BUY + MY_ADD + MY_BOUNCE
  #프리미엄_매도  ← MY_SELL + MY_PROFIT + MY_FIRE
  #프리미엄_리스크 ← MY_RISK + MY_ALERT
  #프리미엄_리포트 ← MY_REPORT + MY_PERF + MY_BACKTEST
  #프리미엄_시스템 ← MY_SYSTEM
  #프리미엄_모닝  ← MY_MORNING
""")
