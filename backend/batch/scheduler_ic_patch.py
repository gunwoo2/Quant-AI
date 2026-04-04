
# ═══════════════════════════════════════════════════════════════
# scheduler.py에 추가할 IC Guard 스텝 (Step 5.5)
# ═══════════════════════════════════════════════════════════════
#
# 위치: Step 5 (Final Score) 직전에 삽입
# 즉: DQ Gate → L1 → L2 → L3 → [IC Guard] → Final Score → ...
#
# scheduler.py의 step 정의 부분에 아래를 추가:
#
#   results["5.5_ic_guard"] = _run_step("5.5 IC Guard", lambda: _s_ic_guard(calc_date))
#
# 그리고 아래 함수를 정의:

def _s_ic_guard(d):
    """Step 5.5: IC Guard — 매일 레이어 가중치 자동 조정"""
    from batch.batch_ic_guard import run_ic_guard
    weights = run_ic_guard(d)
    print(f"  적응형 가중치: L1={weights['l1']:.2f} L2={weights['l2']:.2f} L3={weights['l3']:.2f}")
