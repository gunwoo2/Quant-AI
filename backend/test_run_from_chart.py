"""run_from_chart.py — Step 4.5부터 재실행 (1~5.4 완료)"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv()
from db_pool import init_pool
init_pool()
from datetime import datetime, date

d = date.today()
start = datetime.now()
print(f"\n{'='*60}")
print(f"  Step 4.5부터 재실행 — {d}")
print(f"  (1~4 완료, L2 뉴스/감성/애널 완료)")
print(f"{'='*60}")

# # Step 4.5: 차트 패턴
# print("\n── 4.5 차트패턴 ──")
# try:
#     from batch.batch_chart_patterns import run_chart_patterns
#     run_chart_patterns(d)
# except Exception as e:
#     print(f"❌ 차트패턴: {e}")

# # Step 4.6: Fear & Greed
# print("\n── 4.6 Fear&Greed ──")
# try:
#     from batch.batch_fear_greed import run_fear_greed
#     run_fear_greed(d)
# except Exception as e:
#     print(f"❌ Fear&Greed: {e}")

# # Step 5: Layer 2 — 1~4 스킵, 5/6 내부자 + 6/6 스코어링만
# print("\n── 5/10 Layer 2 (5/6 내부자 + 6/6 스코어링만) ──")
# try:
#     from batch.batch_layer2_v2 import run_insider_collection, run_layer2_scoring
#     print("\n  ── L2 Step 5/6: 내부자 거래 수집 ──")
#     run_insider_collection()
#     print("\n  ── L2 Step 6/6: Layer 2 최종 스코어링 ──")
#     run_layer2_scoring()
# except Exception as e:
#     print(f"❌ Layer 2: {e}")

# # Step 5.7: 거시지표
# print("\n── 5.7 거시지표 ──")
# try:
#     from batch.batch_macro import run_macro
#     run_macro()
# except Exception as e:
#     print(f"❌ 거시지표: {e}")

# # Step 6: 최종 합산
# print("\n── 6/10 최종 합산 ──")
# try:
#     from batch.batch_final_score import run_final_score
#     run_final_score(d)
# except Exception as e:
#     print(f"❌ 최종 합산: {e}")

# Step 7: 트레이딩 시그널
print("\n── 7/10 트레이딩 시그널 ──")
try:
    from batch.batch_trading_signals import run_trading_signals
    run_trading_signals(calc_date=d, dry_run=True)
except Exception as e:
    print(f"❌ 시그널: {e}")

# Step 8: 알림
print("\n── 8/10 알림 ──")
try:
    from notifier import notify_batch_complete
    elapsed = (datetime.now() - start).total_seconds()
    notify_batch_complete(d, elapsed, {"note": "4.5부터 재실행"})
except Exception as e:
    print(f"❌ 알림: {e}")

elapsed = (datetime.now() - start).total_seconds()
print(f"\n{'='*60}")
print(f"  완료: {elapsed:.0f}초 ({elapsed/60:.1f}분)")
print(f"{'='*60}")