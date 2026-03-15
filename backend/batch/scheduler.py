"""
scheduler.py — 배치 스케줄러
전체 실행 순서:
  02:00  DAILY_PRICE      — 전일 OHLCV 수집 (FDR)
  02:30  SUPPLEMENT       — 파생 재무지표 계산
  03:00  QUANT_SCORE L1   — Layer 1 점수
  03:30  LAYER3           — Layer 3 전체 (기술지표+시장환경+수급+합산)
  06:00  LAYER2           — 뉴스/애널리스트
  07:00  FINAL_SCORE      — L1(50%) + L2(25%) + L3(25%)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, date


def run_all(calc_date: date = None):
    if calc_date is None:
        calc_date = datetime.now().date()

    print(f"\n{'='*60}")
    print(f"  QUANT AI 일일 배치 — {calc_date}")
    print(f"{'='*60}\n")

    # ── 1/6 가격 수집 ──
    print("── 1/6 가격 수집 ──")
    try:
        from batch.batch_ticker_item_daily import run_daily_price
        run_daily_price(calc_date)
    except Exception as e:
        print(f"[ERROR] 가격 수집 실패: {e}")

    # ── 2/6 파생 재무지표 ──
    print("\n── 2/6 파생 재무지표 ──")
    try:
        from batch.batch_ticker_item_daily import run_supplement_financials
        run_supplement_financials(calc_date)
    except Exception as e:
        print(f"[ERROR] 파생지표 실패: {e}")

    # ── 3/6 Layer 1 점수 ──
    print("\n── 3/6 Layer 1 점수 ──")
    try:
        from batch.batch_ticker_item_daily import run_quant_score
        run_quant_score(calc_date)
    except Exception as e:
        print(f"[ERROR] L1 실패: {e}")

    # ── 4/6 Layer 3 시장 신호 ──
    print("\n── 4/6 Layer 3 시장 신호 ──")
    try:
        from batch.batch_layer3_v2 import run_all as run_l3
        run_l3(calc_date)
    except Exception as e:
        print(f"[ERROR] L3 실패: {e}")

    # ── 5/6 Layer 2 뉴스/애널리스트 ──
    print("\n── 5/6 Layer 2 뉴스/애널리스트 ──")
    try:
        from batch.batch_layer2_v2 import run_all as run_l2
        run_l2(calc_date)
    except Exception as e:
        print(f"[ERROR] L2 실패: {e}")

    # ── 6/6 최종 점수 합산 ──
    print("\n── 6/6 최종 점수 합산 ──")
    try:
        from batch.batch_final_score import run_final_score
        run_final_score(calc_date)
    except Exception as e:
        print(f"[ERROR] Final Score 실패: {e}")

    print(f"\n{'='*60}")
    print(f"  전체 배치 완료!")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    import db_pool
    db_pool.init_pool()
    try:
        run_all()
    finally:
        db_pool.close_pool()
