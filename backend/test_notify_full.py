#!/usr/bin/env python3
"""
test_notify_full.py — 실제 DB 데이터로 전체 알림 파이프라인 테스트
================================================================
1) DB에서 Final Score 상위 종목을 읽어옴
2) 실제 가격/점수로 매수 시그널 생성
3) 가상 매도 시그널도 포함
4) notify_daily_signals() 호출 → Discord 전 채널 발송

= 실제 배치와 동일한 알림 형태가 Discord로 옵니다 =

실행:
  cd ~/Quant-AI/backend
  python3 test_notify_full.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv()

from datetime import date, datetime
from db_pool import init_pool, get_cursor

init_pool()
print("=" * 60)
print("  QUANT AI — 실제 DB 기반 알림 테스트")
print("=" * 60)

# ═══════════════════════════════════════════════════
#  1. DB에서 실제 데이터 읽기
# ═══════════════════════════════════════════════════
print("\n── Step 1: DB에서 데이터 수집 ──")

# Final Score 상위 5종목
with get_cursor() as cur:
    cur.execute("""
        SELECT s.ticker, s.company_name, sec.sector_name,
               f.final_score, f.final_grade,
               p.close_price
        FROM stock_final_scores f
        JOIN stocks s ON f.stock_id = s.stock_id
        LEFT JOIN sectors sec ON s.sector_id = sec.sector_id
        LEFT JOIN stock_prices_daily p 
            ON f.stock_id = p.stock_id 
            AND p.price_date = (SELECT MAX(price_date) FROM stock_prices_daily)
        WHERE f.calc_date = (SELECT MAX(calc_date) FROM stock_final_scores)
          AND f.final_score IS NOT NULL
          AND p.close_price IS NOT NULL
        ORDER BY f.final_score DESC
        LIMIT 5
    """)
    top_stocks = [dict(r) for r in cur.fetchall()]

# Final Score 하위 3종목 (매도 대상)
with get_cursor() as cur:
    cur.execute("""
        SELECT s.ticker, s.company_name,
               f.final_score, f.final_grade,
               p.close_price
        FROM stock_final_scores f
        JOIN stocks s ON f.stock_id = s.stock_id
        LEFT JOIN stock_prices_daily p 
            ON f.stock_id = p.stock_id 
            AND p.price_date = (SELECT MAX(price_date) FROM stock_prices_daily)
        WHERE f.calc_date = (SELECT MAX(calc_date) FROM stock_final_scores)
          AND f.final_score IS NOT NULL
          AND p.close_price IS NOT NULL
        ORDER BY f.final_score ASC
        LIMIT 3
    """)
    bottom_stocks = [dict(r) for r in cur.fetchall()]

# 시장 국면 (VIX, SPY)
with get_cursor() as cur:
    cur.execute("""
        SELECT indicator_name, value 
        FROM macro_indicators 
        WHERE indicator_name IN ('VIX', 'SP500')
          AND recorded_date = (SELECT MAX(recorded_date) FROM macro_indicators)
    """)
    macro = {r["indicator_name"]: r["value"] for r in cur.fetchall()}

spy_price = float(macro.get("SP500", 648.57))
vix_close = float(macro.get("VIX", 23.5))

# 국면 판단
if vix_close >= 30:
    regime = "CRISIS"
elif vix_close >= 25:
    regime = "BEAR"
elif vix_close >= 18:
    regime = "NEUTRAL"
else:
    regime = "BULL"

print(f"  시장: {regime} | SPY=${spy_price:,.2f} | VIX={vix_close:.1f}")
print(f"  매수 후보: {len(top_stocks)}종목 | 매도 후보: {len(bottom_stocks)}종목")

for s in top_stocks:
    print(f"    🟢 {s['ticker']:6s} {s.get('final_grade','?'):3s} {s['final_score']:.1f}점 @ ${s['close_price']:,.2f}")
for s in bottom_stocks:
    print(f"    🔴 {s['ticker']:6s} {s.get('final_grade','?'):3s} {s['final_score']:.1f}점 @ ${s['close_price']:,.2f}")

# ═══════════════════════════════════════════════════
#  2. 시그널 데이터 구성
# ═══════════════════════════════════════════════════
print("\n── Step 2: 시그널 데이터 구성 ──")

total_capital = 50000
per_stock = total_capital / max(len(top_stocks), 1)

buy_signals = []
for s in top_stocks:
    price = float(s["close_price"])
    shares = int(per_stock / price) if price > 0 else 0
    amount = shares * price
    stop_loss = round(price * 0.9, 2)  # -10% 손절
    
    buy_signals.append({
        "ticker": s["ticker"],
        "grade": s.get("final_grade", "B"),
        "score": float(s["final_score"]),
        "price": price,
        "shares": shares,
        "amount": round(amount, 0),
        "weight": round(amount / total_capital * 100, 1),
        "stop_loss": stop_loss,
        "sector": s.get("sector_name", "N/A"),
    })

sell_signals = []
for s in bottom_stocks:
    price = float(s["close_price"])
    fake_entry = round(price * 1.15, 2)  # 가상 매수가 (15% 위)
    pnl_pct = round((price - fake_entry) / fake_entry * 100, 1)
    
    sell_signals.append({
        "ticker": s["ticker"],
        "reason": "STOP_LOSS" if pnl_pct < -8 else "SCORE_DROP",
        "price": price,
        "entry_price": fake_entry,
        "holding_days": 14,
        "pnl_pct": pnl_pct,
        "shares": 10,
    })

print(f"  매수 시그널: {len(buy_signals)}건")
for b in buy_signals:
    print(f"    {b['ticker']} {b['grade']} ({b['score']:.1f}) → {b['shares']}주 @ ${b['price']:,.2f} | 손절 ${b['stop_loss']:,.2f}")
print(f"  매도 시그널: {len(sell_signals)}건")
for s in sell_signals:
    print(f"    {s['ticker']} {s['reason']} | {s['pnl_pct']:+.1f}%")

# ═══════════════════════════════════════════════════
#  3. 알림 발송 (실제 notifier 호출)
# ═══════════════════════════════════════════════════
print("\n── Step 3: Discord 알림 발송 ──")

from notifier import (
    notify_daily_signals, 
    notify_batch_complete,
    _WEBHOOK_MAP, _FALLBACK_URL,
)

# 웹후크 상태
configured = sum(1 for v in _WEBHOOK_MAP.values() if v)
print(f"  설정된 채널: {configured}/8 {'+ FALLBACK' if _FALLBACK_URL else ''}")

regime_detail = {
    "spy_price": spy_price,
    "vix_close": vix_close,
    "sma_200": spy_price * 0.92,
}

portfolio_summary = {
    "total_value": total_capital,
    "daily_return": 1.25,
    "vs_spy": 0.42,
    "num_positions": len(buy_signals),
    "cash_pct": 22.5,
}

# 일일 시그널 알림 (매수 + 매도)
print("\n  📤 일일 시그널 알림 발송 중...")
try:
    notify_daily_signals(
        calc_date=date.today(),
        regime=regime,
        regime_detail=regime_detail,
        buy_signals=buy_signals,
        sell_signals=sell_signals,
        portfolio_summary=portfolio_summary,
    )
    print("  ✅ 일일 시그널 알림 완료!")
except Exception as e:
    print(f"  ❌ 실패: {e}")
    import traceback; traceback.print_exc()

# 배치 완료 알림
print("\n  📤 배치 완료 알림 발송 중...")
try:
    fake_results = {
        "1_price": "OK",
        "2_fin": "OK", 
        "3_l1": "OK",
        "4_l3": "OK",
        "5_l2": "OK",
        "5.5_ec": "SKIP",
        "5.6_insider": "OK",
        "5.7_macro": "OK",
        "6_final": "OK",
        "7_trading": "OK",
    }
    notify_batch_complete(
        calc_date=date.today(),
        elapsed_seconds=342.5,
        results=fake_results,
    )
    print("  ✅ 배치 완료 알림 완료!")
except Exception as e:
    print(f"  ❌ 실패: {e}")
    import traceback; traceback.print_exc()

print("\n" + "=" * 60)
print("  🎉 테스트 완료! Discord 확인하세요:")
print("  - BUY 채널: 매수 시그널 (상위 종목)")
print("  - SELL 채널: 손절 매도 (하위 종목)")
print("  - PROFIT 채널: 익절 매도 (있으면)")
print("  - REPORT 채널: 배치 완료 리포트")
print("=" * 60)