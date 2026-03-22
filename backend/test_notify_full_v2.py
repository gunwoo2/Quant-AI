#!/usr/bin/env python3
"""
test_notify_full_v3.py — 개인/공용 전체 Discord 알림 테스트
===========================================================
notifier v3.6 (개인/공용 분리 + 안전장치) 전체 기능 테스트.

실행:
  cd ~/Quant-AI/backend
  python test_notify_full_v3.py

.env에 웹훅 URL이 설정되어 있어야 합니다.
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv()

from datetime import date
from notifier import (
    _WEBHOOK_MY, _WEBHOOK_PUB, _FALLBACK_URL, _send_discord,
    notify_daily_signals,
    notify_add_position,
    notify_fire_sell,
    notify_bounce_opportunity,
    notify_morning_briefing,
    notify_daily_performance,
    notify_grade_changes,
    notify_earnings_alert,
    notify_emergency,
    notify_risk_warning,
    notify_regime_change,
    notify_batch_complete,
    notify_weekly_rebalance,
    notify_weekly_report,
    notify_backtest_result,
    notify_price_fetch_failure,
    check_price_freshness,
)

TODAY = date.today()
DELAY = 1.5  # Discord rate limit 방지

print("=" * 60)
print("  QUANT AI — 개인/공용 전체 알림 테스트 v3")
print("=" * 60)

# ── 웹훅 상태 확인 ──
print("\n── 🔒 개인 채널 웹훅 ──")
my_cnt = 0
for key, url in _WEBHOOK_MY.items():
    status = "✅" if url else "❌"
    if url: my_cnt += 1
    print(f"  MY_{key:12s} : {status}")

print(f"\n── 📢 공용 채널 웹훅 ──")
pub_cnt = 0
for key, url in _WEBHOOK_PUB.items():
    status = "✅" if url else "❌"
    if url: pub_cnt += 1
    print(f"  PUB_{key:12s} : {status}")

print(f"\n  FALLBACK: {'✅' if _FALLBACK_URL else '❌'}")
print(f"  개인: {my_cnt}/{len(_WEBHOOK_MY)} | 공용: {pub_cnt}/{len(_WEBHOOK_PUB)}")

if my_cnt + pub_cnt == 0 and not _FALLBACK_URL:
    print("\n⚠️  웹훅이 하나도 없습니다! .env를 확인하세요.")
    sys.exit(1)

input("\n▶ Enter를 누르면 테스트 시작... (Discord 확인 준비)")


# ══════════════════════════════════════════════════════════
#  1. 매수 추천 → 개인-매수 + 매수-시그널
# ══════════════════════════════════════════════════════════
print("\n── [1] 매수 추천 + 매도 + 익절 ──")
try:
    notify_daily_signals(
        calc_date=TODAY, regime="BULL",
        regime_detail={"spy_price": 548.57, "vix_close": 18.3, "sma_200": 520.0},
        buy_signals=[
            {"ticker": "AAPL", "grade": "A+", "score": 87.5, "price": 235.50,
             "shares": 15, "amount": 3532, "weight": 5.4, "stop_loss": 211.95,
             "stop_pct": 10, "sector": "Technology"},
            {"ticker": "NVDA", "grade": "S", "score": 93.2, "price": 142.80,
             "shares": 25, "amount": 3570, "weight": 5.7, "stop_loss": 128.52,
             "stop_pct": 10, "sector": "Technology"},
        ],
        sell_signals=[
            # 손절 (pnl_pct < 0) → 매도-시그널
            {"ticker": "NFLX", "reason": "STOP_LOSS", "price": 980.00,
             "entry_price": 1050.00, "holding_days": 12, "pnl_pct": -6.7, "shares": 3},
            # 익절 (pnl_pct >= 0) → 매도-시그널
            {"ticker": "META", "reason": "TAKE_PROFIT", "price": 620.00,
             "entry_price": 510.00, "holding_days": 45, "pnl_pct": 21.6, "shares": 8},
        ],
        portfolio_summary={"total_value": 62500, "daily_return": 1.25,
                           "num_positions": 8, "cash_pct": 22.5},
    )
    print("  ✅ 매수(2) + 손절(1) + 익절(1) → 개인-매수/매도 + 매수/매도-시그널")
except Exception as e:
    print(f"  ❌ 실패: {e}")
time.sleep(DELAY)


# ══════════════════════════════════════════════════════════
#  2. 물타기 + 불타기 → 개인-매수 + 매수-시그널
# ══════════════════════════════════════════════════════════
print("\n── [2] 물타기 + 불타기 ──")
try:
    notify_add_position(TODAY, [
        # 물타기 (pnl < 0)
        {"ticker": "TSLA", "pnl_pct": -8.2, "grade": "A", "score": 78.5,
         "shares": 5, "price": 342.00, "avg_down_pct": -4.1},
        # 불타기 (pnl > 0)
        {"ticker": "NVDA", "pnl_pct": 15.3, "grade": "S", "score": 93.2,
         "shares": 10, "price": 142.80, "avg_down_pct": 0},
    ])
    print("  ✅ 물타기(TSLA) + 불타기(NVDA) → 개인-매수 + 매수-시그널")
except Exception as e:
    print(f"  ❌ 실패: {e}")
time.sleep(DELAY)


# ══════════════════════════════════════════════════════════
#  3. 긴급 매도 → 개인-매도 + 매도-시그널
# ══════════════════════════════════════════════════════════
print("\n── [3] 긴급 매도 ──")
try:
    notify_fire_sell(TODAY, [
        {"ticker": "TSLA", "reason": "CIRCUIT_BREAKER", "pnl_pct": -12.3,
         "price": 305.00, "entry_price": 348.00, "shares": 15},
        {"ticker": "COIN", "reason": "DD_ALERT", "pnl_pct": -18.5,
         "price": 195.00, "entry_price": 239.00, "shares": 10},
    ], trigger="VIX 35 돌파 + SPY -3% 급락")
    print("  ✅ 긴급매도(2) → 개인-매도 + 매도-시그널")
except Exception as e:
    print(f"  ❌ 실패: {e}")
time.sleep(DELAY)


# ══════════════════════════════════════════════════════════
#  4. 반등 매수 → 개인-매수 + 매수-시그널
# ══════════════════════════════════════════════════════════
print("\n── [4] 반등 매수 기회 ──")
try:
    notify_bounce_opportunity(TODAY, [
        {"ticker": "META", "grade": "A", "score": 85.0,
         "rsi": 25.3, "drop_7d": -12.5, "volume_ratio": 2.8, "price": 545.00},
    ])
    print("  ✅ 반등 매수(META) → 개인-매수 + 매수-시그널")
except Exception as e:
    print(f"  ❌ 실패: {e}")
time.sleep(DELAY)


# ══════════════════════════════════════════════════════════
#  5. 모닝 브리핑 → 개인-모닝(포폴 포함) + 모닝-브리핑(포폴 없음)
# ══════════════════════════════════════════════════════════
print("\n── [5] 모닝 브리핑 ──")
try:
    notify_morning_briefing(
        calc_date=TODAY, regime="BULL",
        regime_detail={
            "spy_price": 548.57, "vix_close": 18.3,
            "futures_pct": 0.35, "vix_change_pct": -2.1,
        },
        top_buys=[
            {"ticker": "NVDA", "grade": "S", "score": 93.2, "price": 142.80},
            {"ticker": "AAPL", "grade": "A+", "score": 87.5, "price": 235.50},
            {"ticker": "MSFT", "grade": "A+", "score": 86.1, "price": 442.30},
        ],
        grade_changes=[
            {"ticker": "GOOGL", "direction": "UP", "old_grade": "B+",
             "new_grade": "A", "score": 82.5},
        ],
        earnings_today=[
            {"ticker": "AAPL", "time": "AMC", "eps_estimate": 2.35},
        ],
        portfolio_summary={
            "total_value": 62500, "daily_return": 1.25,
            "num_positions": 8, "cash_pct": 22.5,
        },
        signal_summary={"buy": 2, "sell": 1, "profit": 1},
    )
    print("  ✅ 모닝 → 개인-모닝(포폴 포함) + 모닝-브리핑(포폴 없음)")
except Exception as e:
    print(f"  ❌ 실패: {e}")
time.sleep(DELAY)


# ══════════════════════════════════════════════════════════
#  6. 일일 성과 → 개인-리포트 (개인 전용)
# ══════════════════════════════════════════════════════════
print("\n── [6] 일일 성과 (개인 전용) ──")
try:
    notify_daily_performance(
        calc_date=TODAY, portfolio_value=63280,
        daily_return=1.25, spy_return=0.83,
        num_positions=8, total_pnl=3280,
        best_ticker="NVDA", best_pnl=5.2,
        worst_ticker="NFLX", worst_pnl=-2.1,
    )
    print("  ✅ 일일 성과 → 개인-리포트")
except Exception as e:
    print(f"  ❌ 실패: {e}")
time.sleep(DELAY)


# ══════════════════════════════════════════════════════════
#  7. 등급 변경 → 긴급-알림
# ══════════════════════════════════════════════════════════
print("\n── [7] 등급 변경 ──")
try:
    notify_grade_changes(TODAY,
        upgrades=[
            {"ticker": "GOOGL", "old_grade": "B+", "new_grade": "A",
             "old_score": 72.0, "new_score": 82.5},
        ],
        downgrades=[
            {"ticker": "NFLX", "old_grade": "A", "new_grade": "B",
             "old_score": 80.0, "new_score": 55.3},
        ],
    )
    print("  ✅ 등급 변경 → 긴급-알림")
except Exception as e:
    print(f"  ❌ 실패: {e}")
time.sleep(DELAY)


# ══════════════════════════════════════════════════════════
#  8. 어닝 D-Day → 긴급-알림
# ══════════════════════════════════════════════════════════
print("\n── [8] 어닝 D-Day ──")
try:
    notify_earnings_alert(TODAY, [
        {"ticker": "AAPL", "time": "AMC", "eps_estimate": 2.35,
         "rev_estimate": 94.5e9, "grade": "A+"},
        {"ticker": "MSFT", "time": "BMO", "eps_estimate": 3.22,
         "rev_estimate": 68.7e9, "grade": "A+"},
    ])
    print("  ✅ 어닝 D-Day → 긴급-알림")
except Exception as e:
    print(f"  ❌ 실패: {e}")
time.sleep(DELAY)


# ══════════════════════════════════════════════════════════
#  9. 리스크 경고 → 개인-리스크 (개인 전용)
# ══════════════════════════════════════════════════════════
print("\n── [9] 리스크 경고 (개인 전용) ──")
try:
    notify_risk_warning(
        calc_date=TODAY,
        dd_mode="WARNING",
        drawdown_pct=-8.5,
        cb_level="LEVEL_1",
        losing_streak=3,
        concentration_warn=[
            {"sector": "Technology", "pct": 45},
            {"sector": "Consumer", "pct": 28},
        ],
    )
    print("  ✅ 리스크 경고 → 개인-리스크")
except Exception as e:
    print(f"  ❌ 실패: {e}")
time.sleep(DELAY)


# ══════════════════════════════════════════════════════════
#  10. 국면 전환 → 긴급-알림
# ══════════════════════════════════════════════════════════
print("\n── [10] 국면 전환 ──")
try:
    notify_regime_change(TODAY, "BULL", "NEUTRAL",
                         detail="SPY SMA200 하향 돌파 + VIX 25 이상")
    print("  ✅ 국면 전환 → 긴급-알림")
except Exception as e:
    print(f"  ❌ 실패: {e}")
time.sleep(DELAY)


# ══════════════════════════════════════════════════════════
#  11. 긴급 알림 → 개인-리스크 + 긴급-알림
# ══════════════════════════════════════════════════════════
print("\n── [11] 긴급 알림 ──")
try:
    notify_emergency("테스트 긴급 알림", "이것은 시스템 테스트입니다.\n실제 긴급 상황이 아닙니다.")
    print("  ✅ 긴급 → 개인-리스크 + 긴급-알림")
except Exception as e:
    print(f"  ❌ 실패: {e}")
time.sleep(DELAY)


# ══════════════════════════════════════════════════════════
#  12. 배치 완료 → 리포트
# ══════════════════════════════════════════════════════════
print("\n── [12] 배치 완료 ──")
try:
    notify_batch_complete(
        calc_date=TODAY, elapsed_seconds=245.7,
        results={
            "1_price": "OK", "2_fin": "OK", "3_l1": "OK",
            "4_l3": "OK", "5_l2": "OK", "5.5_ec": "SKIP",
            "5.6_insider": "OK", "5.7_macro": "OK",
            "6_final": "OK", "7_trading": "OK",
        },
    )
    print("  ✅ 배치 완료 → 리포트")
except Exception as e:
    print(f"  ❌ 실패: {e}")
time.sleep(DELAY)


# ══════════════════════════════════════════════════════════
#  13. 주간 리포트 → 개인-리포트 + 리포트
# ══════════════════════════════════════════════════════════
print("\n── [13] 주간 리포트 ──")
try:
    notify_weekly_report(
        calc_date=TODAY, week_return=2.35, total_value=64175,
        spy_return=1.10, win_rate=72, num_trades=6,
        best_ticker="NVDA", best_pnl=12.5,
        worst_ticker="NFLX", worst_pnl=-5.2,
    )
    print("  ✅ 주간 리포트 → 개인-리포트 + 리포트")
except Exception as e:
    print(f"  ❌ 실패: {e}")
time.sleep(DELAY)


# ══════════════════════════════════════════════════════════
#  14. 주간 리밸런싱 → 개인-리포트 + 리포트
# ══════════════════════════════════════════════════════════
print("\n── [14] 주간 리밸런싱 ──")
try:
    notify_weekly_rebalance(
        calc_date=TODAY,
        buys=[{"ticker": "AMD", "shares": 20}],
        sells=[{"ticker": "NFLX", "shares": 3}],
        adjusts=[{"ticker": "AAPL", "shares": 5, "direction": "UP"}],
        turnover=12.5,
    )
    print("  ✅ 리밸런싱 → 개인-리포트 + 리포트")
except Exception as e:
    print(f"  ❌ 실패: {e}")
time.sleep(DELAY)


# ══════════════════════════════════════════════════════════
#  15. 백테스트 결과 → 리포트
# ══════════════════════════════════════════════════════════
print("\n── [15] 백테스트 결과 ──")
try:
    notify_backtest_result(
        period_start=date(2024, 1, 1), period_end=date(2025, 3, 20),
        total_return=42.7, annual_return=38.2,
        max_drawdown=-11.3, sharpe_ratio=1.85,
        win_rate=68.5, spy_alpha=18.4,
        num_trades=142, avg_holding_days=23,
    )
    print("  ✅ 백테스트 → 리포트")
except Exception as e:
    print(f"  ❌ 실패: {e}")
time.sleep(DELAY)


# ══════════════════════════════════════════════════════════
#  16. 가격 수집 장애 → 개인-리스크 + 리포트
# ══════════════════════════════════════════════════════════
print("\n── [16] 가격 수집 장애 (안전장치 테스트) ──")
try:
    notify_price_fetch_failure(
        calc_date=TODAY,
        error_msg="yfinance.download() timeout after 30s",
        stale_tickers=["AAPL", "MSFT", "GOOGL", "TSLA", "NVDA"],
    )
    print("  ✅ 가격 장애 → 개인-리스크 + 리포트")
except Exception as e:
    print(f"  ❌ 실패: {e}")


# ══════════════════════════════════════════════════════════
#  완료
# ══════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("  🎉 전체 테스트 완료! (16개 시나리오)")
print("=" * 60)
print("""
  Discord에서 확인할 채널:

  📁 매매
    #☀️ 모닝-브리핑    → [5] 모닝 (포폴 없음)
    #🟢 매수-시그널    → [1]매수 [2]물타기/불타기 [4]반등
    #🔴 매도-시그널    → [1]손절/익절 [3]긴급매도

  📁 레포트
    #🚨 긴급-알림      → [7]등급변경 [8]어닝 [10]국면 [11]긴급
    #📊 리포트         → [12]배치 [13]주간 [14]리밸 [15]백테 [16]장애

  📁 개인용
    #🟢 개인-매수      → [1]매수 [2]물타기/불타기 [4]반등 (수량/금액)
    #🔴 개인-매도      → [1]손절/익절 [3]긴급매도 (수량/손익금)
    #☀️ 개인-모닝      → [5] 모닝 (포폴 포함!)
    #📊 개인-리포트    → [6]일일성과 [13]주간 [14]리밸 (금액)
    #🚨 개인-리스크    → [9]리스크 [11]긴급 [16]장애
""")
