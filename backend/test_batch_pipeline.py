#!/usr/bin/env python3
"""
test_batch_pipeline.py — 실제 배치 코드 단계별 실행
====================================================
scheduler.py의 실제 함수를 직접 호출합니다.

사용법:
  cd ~/Quant-AI/backend

  # 전체 14단계 실행
  python3 test_batch_pipeline.py --all

  # 모닝 브리핑 (장 시작 전)
  python3 test_batch_pipeline.py --morning

  # Step 7부터 (시그널+알림 — 가장 많이 쓸 것)
  python3 test_batch_pipeline.py --from 7

  # Final Score + 시그널 + 알림
  python3 test_batch_pipeline.py --from 6

  # 특정 단계만
  python3 test_batch_pipeline.py --step 8    # 등급 변경 감지
  python3 test_batch_pipeline.py --step 11   # 일일 성과
  python3 test_batch_pipeline.py --step 12   # 배치 완료 알림
"""
import os, sys, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv()

from datetime import date
from db_pool import init_pool
init_pool()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="QUANT AI 배치 파이프라인 수동 실행")
    parser.add_argument("--all", action="store_true", help="전체 14단계")
    parser.add_argument("--morning", action="store_true", help="모닝 브리핑만")
    parser.add_argument("--from", type=int, dest="from_step", help="이 단계부터 (예: --from 7)")
    parser.add_argument("--step", type=int, help="특정 단계만 (예: --step 8)")
    parser.add_argument("--date", type=str, default=None, help="날짜 (YYYY-MM-DD)")
    args = parser.parse_args()

    calc_date = date.fromisoformat(args.date) if args.date else date.today()

    from batch.scheduler import run_all, run_morning, _run_step
    from batch import scheduler as sched

    if args.morning:
        run_morning(calc_date)
    elif args.all:
        run_all(calc_date)
    elif args.from_step or args.step:
        from datetime import datetime
        start_all = datetime.now()
        results = {}

        # 단계별 매핑 (scheduler.py의 실제 함수)
        STEPS = {
            1:  ("가격 수집",         lambda: sched._s_price(calc_date)),
            2:  ("파생 재무",         lambda: sched._s_fin(calc_date)),
            3:  ("Layer 1",          lambda: sched._s_l1(calc_date)),
            4:  ("Layer 3",          lambda: sched._s_l3(calc_date)),
            5:  ("Layer 2",          lambda: sched._s_l2(calc_date)),
            6:  ("Final Score",      lambda: sched._s_final(calc_date)),
            7:  ("Trading Signal",   lambda: sched._s_trading(calc_date)),
            8:  ("등급 변경 감지",     lambda: sched._s_grade_change(calc_date)),
            9:  ("어닝 D-day",       lambda: sched._s_earnings_alert(calc_date)),
            10: ("리스크 점검",       lambda: sched._s_risk_check(calc_date)),
            11: ("일일 성과",         lambda: sched._s_daily_performance(calc_date)),
            12: ("배치 완료 알림",     lambda: sched._s_notify(calc_date, results, start_all)),
            13: ("주간 성과",         lambda: sched._s_weekly(calc_date)),
            14: ("월간 성과",         lambda: sched._s_monthly(calc_date)),
        }

        if args.step:
            nums = [args.step]
        else:
            nums = [n for n in sorted(STEPS.keys()) if n >= args.from_step]

        print(f"\n{'='*60}")
        print(f"  QUANT AI — 배치 Step {nums} 실행")
        print(f"  날짜: {calc_date}")
        print(f"{'='*60}")

        for num in nums:
            if num not in STEPS:
                print(f"  ❌ 없는 단계: {num}")
                continue
            name, func = STEPS[num]
            results[f"{num}_{name}"] = _run_step(f"{num}/14 {name}", func)

        elapsed = (datetime.now() - start_all).total_seconds()
        ok = sum(1 for v in results.values() if v == "OK")
        fail = sum(1 for v in results.values() if isinstance(v, str) and v.startswith("FAIL"))
        print(f"\n{'='*60}")
        print(f"  결과: 성공={ok} 실패={fail} | 소요: {elapsed:.0f}초")
        print(f"{'='*60}")
    else:
        print("""사용법:
  python3 test_batch_pipeline.py --all           # 전체 14단계
  python3 test_batch_pipeline.py --morning       # 모닝 브리핑
  python3 test_batch_pipeline.py --from 7        # Step 7부터 (시그널+알림)
  python3 test_batch_pipeline.py --from 6        # Step 6부터
  python3 test_batch_pipeline.py --step 8        # 등급 변경만
  python3 test_batch_pipeline.py --step 11       # 일일 성과만
  python3 test_batch_pipeline.py --step 12       # 배치 완료 알림만

단계:
   1  가격 수집          7  Trading Signal    
   2  파생 재무          8  등급 변경 감지 ★NEW
   3  Layer 1           9  어닝 D-day ★NEW
   4  Layer 3          10  리스크 점검 ★NEW
   5  Layer 2          11  일일 성과 ★NEW
   6  Final Score      12  배치 완료 알림
                       13  주간 성과
                       14  월간 성과

별도:
   --morning           ☀️ 모닝 브리핑 ★NEW
""")