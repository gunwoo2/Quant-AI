"""
test_m7_batch.py — M7 종목만 배치 테스트
========================================
cd backend
python test_m7_batch.py

전체 6단계를 M7(7종목)만 대상으로 실행합니다.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import patch_numpy_adapter  # NumPy→psycopg2 자동 변환
from datetime import date, datetime
from db_pool import init_pool, get_cursor

M7 = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"]


def _f(v):
    """안전 float 변환"""
    if v is None:
        return 0.0
    try:
        return float(v)
    except Exception:
        return 0.0


def setup_m7_only():
    """M7만 active, 나머지 비활성화"""
    with get_cursor() as cur:
        cur.execute("UPDATE stocks SET is_active = FALSE")
        cur.execute(
            "UPDATE stocks SET is_active = TRUE WHERE ticker = ANY(%s)",
            (M7,),
        )
        cur.execute(
            "SELECT ticker FROM stocks WHERE is_active = TRUE ORDER BY ticker"
        )
        tickers = [r["ticker"] for r in cur.fetchall()]
        print(f"\n✅ 활성 종목: {tickers} ({len(tickers)}개)")
        if len(tickers) < 7:
            missing = set(M7) - set(tickers)
            print(f"⚠️  DB에 없는 종목: {missing}")
        return tickers


def restore_all_active():
    """테스트 후 전체 종목 다시 활성화"""
    with get_cursor() as cur:
        cur.execute("UPDATE stocks SET is_active = TRUE")
        cur.execute("SELECT COUNT(*) as cnt FROM stocks WHERE is_active = TRUE")
        cnt = cur.fetchone()["cnt"]
        print(f"\n🔄 전체 종목 복원: {cnt}개 active")


# ════════════════════════════════════════════════════════════
# Step 1: 가격 수집
# ════════════════════════════════════════════════════════════
def step1_price():
    print("\n" + "=" * 60)
    print("  Step 1/6: 가격 수집 (M7)")
    print("=" * 60)
    try:
        from batch.batch_ticker_item_daily import run_daily_price
        run_daily_price(date.today())
        print("✅ Step 1 완료")
        return True
    except Exception as e:
        print(f"❌ Step 1 실패: {e}")
        import traceback; traceback.print_exc()
        return False


# ════════════════════════════════════════════════════════════
# Step 2: 파생 재무지표
# ════════════════════════════════════════════════════════════
def step2_financials():
    print("\n" + "=" * 60)
    print("  Step 2/6: 파생 재무지표 (M7)")
    print("=" * 60)
    try:
        from batch.batch_ticker_item_daily import run_supplement_financials
        run_supplement_financials()
        print("✅ Step 2 완료")
        return True
    except Exception as e:
        print(f"❌ Step 2 실패: {e}")
        import traceback; traceback.print_exc()
        return False


# ════════════════════════════════════════════════════════════
# Step 3: L1 Quant Score
# ════════════════════════════════════════════════════════════
def step3_l1_score():
    print("\n" + "=" * 60)
    print("  Step 3/6: L1 Quant Score (M7)")
    print("=" * 60)
    try:
        from batch.batch_ticker_item_daily import run_quant_score
        run_quant_score(date.today())
        print("✅ Step 3 완료")

        with get_cursor() as cur:
            cur.execute("""
                SELECT s.ticker,
                       la.layer1_score,
                       la.moat_score,
                       la.value_score,
                       la.momentum_score,
                       la.stability_score
                FROM stock_layer1_analysis la
                JOIN stocks s ON la.stock_id = s.stock_id
                WHERE la.calc_date = %s AND s.is_active = TRUE
                ORDER BY la.layer1_score DESC NULLS LAST
            """, (date.today(),))
            rows = cur.fetchall()
            if rows:
                print(f"\n  {'Ticker':8s} {'Moat':>6s} {'Value':>6s} {'Mom':>6s} {'Stab':>6s} {'L1':>8s}")
                print(f"  {'─'*8} {'─'*6} {'─'*6} {'─'*6} {'─'*6} {'─'*8}")
                for r in rows:
                    print(f"  {r['ticker']:8s} "
                          f"{_f(r.get('moat_score')):>6.1f} "
                          f"{_f(r.get('value_score')):>6.1f} "
                          f"{_f(r.get('momentum_score')):>6.1f} "
                          f"{_f(r.get('stability_score')):>6.1f} "
                          f"{_f(r.get('layer1_score')):>8.1f}")
            else:
                print("  (결과 없음)")
        return True
    except Exception as e:
        print(f"❌ Step 3 실패: {e}")
        import traceback; traceback.print_exc()
        return False


# ════════════════════════════════════════════════════════════
# Step 4: L3 기술지표
# ════════════════════════════════════════════════════════════
def step4_l3_technical():
    print("\n" + "=" * 60)
    print("  Step 4/6: L3 기술지표 (M7)")
    print("=" * 60)
    try:
        from batch.batch_layer3_v2 import run_technical_indicators as run_l3
        run_l3(date.today())
        print("✅ Step 4 완료")

        with get_cursor() as cur:
            cur.execute("""
                SELECT s.ticker,
                       ti.relative_momentum_score,
                       ti.high_52w_score,
                       ti.trend_stability_score,
                       ti.rsi_score,
                       ti.obv_score,
                       ti.volume_surge_score,
                       ti.layer3_technical_score
                FROM technical_indicators ti
                JOIN stocks s ON ti.stock_id = s.stock_id
                WHERE ti.calc_date = %s AND s.is_active = TRUE
                ORDER BY ti.layer3_technical_score DESC NULLS LAST
            """, (date.today(),))
            rows = cur.fetchall()
            if rows:
                print(f"\n  {'Ticker':8s} {'Mom':>6s} {'52W':>6s} {'R²':>6s} {'RSI':>6s} {'OBV':>6s} {'Vol':>6s} {'L3':>8s}")
                print(f"  {'─'*8} {'─'*6} {'─'*6} {'─'*6} {'─'*6} {'─'*6} {'─'*6} {'─'*8}")
                for r in rows:
                    print(f"  {r['ticker']:8s} "
                          f"{_f(r.get('relative_momentum_score')):>6.0f} "
                          f"{_f(r.get('high_52w_score')):>6.0f} "
                          f"{_f(r.get('trend_stability_score')):>6.0f} "
                          f"{_f(r.get('rsi_score')):>6.0f} "
                          f"{_f(r.get('obv_score')):>6.0f} "
                          f"{_f(r.get('volume_surge_score')):>6.0f} "
                          f"{_f(r.get('layer3_technical_score')):>8.1f}")
            else:
                print("  (결과 없음)")
        return True
    except Exception as e:
        print(f"❌ Step 4 실패: {e}")
        import traceback; traceback.print_exc()
        return False


# ════════════════════════════════════════════════════════════
# Step 5: L2 뉴스/애널리스트
# ════════════════════════════════════════════════════════════
def step5_l2_news():
    print("\n" + "=" * 60)
    print("  Step 5/6: L2 뉴스/애널리스트 (M7)")
    print("=" * 60)
    try:
        from batch.batch_layer2_v2 import run_all as run_l2
        run_l2()
        print("✅ Step 5 완료")
        return True
    except ImportError as e:
        print(f"⚠️  Step 5 스킵 (모듈 없음): {e}")
        return False
    except Exception as e:
        print(f"❌ Step 5 실패: {e}")
        import traceback; traceback.print_exc()
        return False


# ════════════════════════════════════════════════════════════
# Step 6: 최종 합산
# ════════════════════════════════════════════════════════════
def step6_final_score():
    print("\n" + "=" * 60)
    print("  Step 6/6: 최종 합산 L1(50%)+L2(25%)+L3(25%)")
    print("=" * 60)
    try:
        from batch.batch_final_score import run_final_score
        run_final_score(date.today())
        print("✅ Step 6 완료")

        with get_cursor() as cur:
            cur.execute("""
                SELECT s.ticker,
                       f.layer1_score, f.layer2_score, f.layer3_score,
                       f.weighted_score, f.grade, f.signal
                FROM stock_final_scores f
                JOIN stocks s ON f.stock_id = s.stock_id
                WHERE f.calc_date = %s AND s.is_active = TRUE
                ORDER BY f.weighted_score DESC
            """, (date.today(),))
            rows = cur.fetchall()

            print(f"\n  {'='*65}")
            print(f"  ★ M7 최종 점수 ({date.today()}) ★")
            print(f"  {'='*65}")
            print(f"  {'Ticker':8s} {'L1':>6s} {'L2':>6s} {'L3':>6s} {'Final':>8s} {'Grade':>6s} {'Signal':>12s}")
            print(f"  {'─'*8} {'─'*6} {'─'*6} {'─'*6} {'─'*8} {'─'*6} {'─'*12}")
            for r in rows:
                print(f"  {r['ticker']:8s} "
                      f"{_f(r.get('layer1_score')):>6.1f} "
                      f"{_f(r.get('layer2_score')):>6.1f} "
                      f"{_f(r.get('layer3_score')):>6.1f} "
                      f"{_f(r.get('weighted_score')):>8.1f} "
                      f"{r.get('grade') or '-':>6s} "
                      f"{r.get('signal') or '-':>12s}")
            print(f"  {'='*65}")
        return True
    except Exception as e:
        print(f"❌ Step 6 실패: {e}")
        import traceback; traceback.print_exc()
        return False


# ════════════════════════════════════════════════════════════
# 메인 실행
# ════════════════════════════════════════════════════════════
if __name__ == "__main__":
    start_time = datetime.now()

    print("""
╔══════════════════════════════════════════════════════════════╗
║   QUANT AI v3.1 — M7 종목 배치 테스트                        ║
║   AAPL · MSFT · GOOGL · AMZN · NVDA · META · TSLA          ║
╚══════════════════════════════════════════════════════════════╝
    """)

    init_pool()

    for folder in ["batch", "utils"]:
        init_path = os.path.join(os.path.dirname(__file__), folder, "__init__.py")
        if not os.path.exists(init_path):
            with open(init_path, "w") as f:
                f.write("")
            print(f"  [SETUP] {folder}/__init__.py 자동 생성")

    tickers = setup_m7_only()

    results = {}
    try:
        results["Step 1 가격수집"] = step1_price()
        results["Step 2 파생재무"] = step2_financials()
        results["Step 3 L1 Score"] = step3_l1_score()
        results["Step 4 L3 기술"]  = step4_l3_technical()
        results["Step 5 L2 NLP"]   = step5_l2_news()
        results["Step 6 최종합산"] = step6_final_score()
    finally:
        restore_all_active()

    elapsed = datetime.now() - start_time

    print(f"\n{'='*60}")
    print(f"  실행 결과 요약")
    print(f"{'='*60}")
    for step, ok in results.items():
        icon = "✅" if ok else "❌"
        print(f"  {icon} {step}")
    print(f"\n  ⏱️  소요 시간: {elapsed}")
    print(f"{'='*60}")
