"""run_from_l2.py — L2부터 재실행 (Step 5~8)"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv()
from db_pool import init_pool
init_pool()
from datetime import date

d = date.today()
print(f"=== L2부터 재실행 — {d} ===")

# # Step 5: Layer 2
# print("\n── 5/8 Layer 2 ──")
# from batch.batch_layer2_v2 import run_all as l2
# l2()

# # Step 5.5: 내부자거래
# print("\n── 5.5 내부자거래 ──")
# try:
#     from batch.batch_insider import run_insider_trades
#     run_insider_trades()
# except Exception as e:
#     print(f"  skip: {e}")

# Step 5.7: 거시지표
print("\n── 5.7 거시지표 ──")
try:
    from batch.batch_macro import run_macro
    run_macro()
except Exception as e:
    print(f"  skip: {e}")

# Step 6: 최종 합산
print("\n── 6/8 최종 합산 ──")
from batch.batch_final_score import run_final_score
run_final_score(d)

# Step 7: 트레이딩 시그널
print("\n── 7/8 트레이딩 시그널 ──")
from batch.batch_trading_signals import run_trading_signals
run_trading_signals(calc_date=d, dry_run=True)

# Step 8: 알림
print("\n── 8/8 알림 ──")
try:
    from notifier import notify_batch_complete
    notify_batch_complete(d, 0, {"note": "L2부터 수동 재실행"})
    print("  ✅ 알림 발송")
except Exception as e:
    print(f"  알림 skip: {e}")

print("\n=== 완료 ===")