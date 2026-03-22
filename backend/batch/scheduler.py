"""
scheduler.py — QUANT AI v3.6
============================
v3.6 변경:
  ★ 안전장치 [2]: Step 1 가격 수집 실패 시 전체 중단 + 긴급 알림
  ★ 안전장치 [1]: Step 7 전 가격 신선도 검증 → stale 종목 경고
  ★ 부분 실패 허용: 10% 미만 실패 시 계속, 10%+ 실패 시 중단

스케줄:
  평일 21:00 ET  — 일일 배치 (10단계)
  토요일 09:00 ET — 주간 성과 리포트
  매월 1일 09:00 ET — 월간 성과 리포트
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, date
import traceback
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("scheduler")

# ── 안전장치 임계값 ──
PRICE_FAIL_THRESHOLD_PCT = int(os.environ.get("PRICE_FAIL_THRESHOLD_PCT", "10"))
# 가격 수집 실패율이 이 % 이상이면 전체 중단


def run_all(calc_date: date = None):
    """10단계 일일 배치 파이프라인 — 안전장치 포함"""
    if calc_date is None:
        calc_date = datetime.now().date()
    start_all = datetime.now()
    results = {}
    print(f"\n{'='*60}\n  QUANT AI v3.6 일일 배치 — {calc_date}\n{'='*60}")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  Step 1: 가격 수집 (★ 안전장치)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    results["1_price"] = _run_step("1/10 가격 수집", lambda: _s_price(calc_date))

    if results["1_price"].startswith("FAIL"):
        # ★ 안전장치 [2]: 가격 수집 전체 실패 → 중단
        print(f"\n🚨 Step 1 가격 수집 실패 — 이후 배치 중단!")
        _emergency_abort(calc_date, results, start_all, results["1_price"])
        return results

    # ★ 안전장치 [1]: 가격 신선도 검증
    stale_info = _check_price_health(calc_date)
    if stale_info and stale_info.get("abort"):
        print(f"\n🚨 가격 데이터 {stale_info['stale_pct']:.0f}% 미갱신 — 이후 배치 중단!")
        results["1_price_health"] = f"FAIL: stale {stale_info['stale_pct']:.0f}%"
        _emergency_abort(calc_date, results, start_all,
                         f"미갱신 종목 {stale_info['stale_count']}개 ({stale_info['stale_pct']:.0f}%)")
        return results
    elif stale_info and stale_info.get("stale_count", 0) > 0:
        results["1_price_health"] = f"WARN: stale {stale_info['stale_count']}개"
        print(f"  ⚠️ 미갱신 종목 {stale_info['stale_count']}개 (임계 미만 → 계속 진행)")
    else:
        results["1_price_health"] = "OK"

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  Step 2~6: 점수 계산
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    results["2_fin"]      = _run_step("2/10 파생 재무",         lambda: _s_fin(calc_date))
    results["3_l1"]       = _run_step("3/10 Layer 1",           lambda: _s_l1(calc_date))
    results["4_l3"]       = _run_step("4/10 Layer 3",           lambda: _s_l3(calc_date))
    results["4.5_pattern"] = _run_step("4.5 차트패턴",           lambda: _s_chart_patterns(calc_date))
    results["4.6_fg"]      = _run_step("4.6 Fear&Greed",        lambda: _s_fear_greed(calc_date))
    results["5_l2"]       = _run_step("5/10 Layer 2",           lambda: _s_l2(calc_date))

    if _should_earnings(calc_date):
        results["5.5_ec"]  = _run_step("5.5 어닝콜",           lambda: _s_ec(calc_date))
    else:
        results["5.5_ec"]  = "SKIP"

    results["5.6_insider"] = _run_step("5.6 내부자거래",       lambda: _s_insider())
    results["5.7_macro"]   = _run_step("5.7 거시지표",         lambda: _s_macro())
    results["6_final"]     = _run_step("6/10 최종 합산",       lambda: _s_final(calc_date))

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  Step 7: 트레이딩 시그널
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    results["7_trading"]   = _run_step("7/10 트레이딩 시그널",  lambda: _s_trading(calc_date))

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  Step 8: 알림 발송
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    results["8_notify"]    = _run_step("8/10 일일 알림",       lambda: _s_notify_all(calc_date, results, start_all))

    # Step 9: 주간 성과 리포트 (토요일)
    if calc_date.weekday() == 5:
        results["9_weekly"] = _run_step("9/10 주간 성과",      lambda: _s_weekly(calc_date))
    else:
        results["9_weekly"] = "SKIP"

    # Step 10: 월간 성과 리포트 (매월 1일)
    if calc_date.day == 1:
        results["10_monthly"] = _run_step("10/10 월간 성과",   lambda: _s_monthly(calc_date))
    else:
        results["10_monthly"] = "SKIP"

    elapsed = datetime.now() - start_all
    ok   = sum(1 for v in results.values() if v == "OK")
    fail = sum(1 for v in results.values() if isinstance(v, str) and v.startswith("FAIL"))
    skip = sum(1 for v in results.values() if v == "SKIP")
    warn = sum(1 for v in results.values() if isinstance(v, str) and v.startswith("WARN"))
    print(f"\n{'='*60}\n  결과: 성공={ok} 실패={fail} 경고={warn} 스킵={skip} | 소요: {elapsed}\n{'='*60}")
    return results


# ══════════════════════════════════════════════
#  ★ 안전장치 함수
# ══════════════════════════════════════════════

def _check_price_health(calc_date: date) -> dict:
    """가격 신선도 검증 → abort 여부 결정"""
    try:
        from notifier import check_price_freshness
        info = check_price_freshness()

        total = info.get("total", 0)
        stale_count = info.get("stale_count", 0)

        if total == 0:
            return {"abort": True, "stale_count": 0, "stale_pct": 100,
                    "message": "realtime 가격 데이터 0건"}

        stale_pct = (stale_count / total) * 100

        if stale_count > 0:
            stale_tickers = [s["ticker"] for s in info.get("stale", [])[:10]]
            print(f"  [HEALTH] 미갱신 종목: {stale_count}/{total} ({stale_pct:.1f}%)")
            print(f"  [HEALTH] 예시: {', '.join(stale_tickers)}")

        return {
            "abort": stale_pct >= PRICE_FAIL_THRESHOLD_PCT,
            "stale_count": stale_count,
            "stale_pct": stale_pct,
            "stale_tickers": [s["ticker"] for s in info.get("stale", [])],
        }
    except Exception as e:
        print(f"  [HEALTH] 신선도 검증 실패: {e}")
        return None  # 검증 불가 → 계속 진행


def _emergency_abort(calc_date: date, results: dict, start_time, error_msg: str):
    """안전장치 발동 → 긴급 알림 + 중단"""
    elapsed = (datetime.now() - start_time).total_seconds()

    try:
        from notifier import notify_price_fetch_failure, notify_batch_complete

        # stale 티커 목록 추출
        stale_tickers = []
        try:
            from notifier import check_price_freshness
            info = check_price_freshness()
            stale_tickers = [s["ticker"] for s in info.get("stale", [])[:20]]
        except Exception:
            pass

        # 긴급 알림
        notify_price_fetch_failure(calc_date, str(error_msg), stale_tickers)

        # 배치 완료 알림 (실패 상태)
        results["ABORT"] = f"FAIL: {error_msg}"
        notify_batch_complete(calc_date, elapsed, results)

    except Exception as e:
        print(f"  [ABORT] 긴급 알림 발송 실패: {e}")
        # 최후의 fallback
        try:
            from notifier import send_message
            send_message(
                f"🚨 배치 긴급 중단 ({calc_date})\n"
                f"사유: {error_msg}\n"
                f"⛔ 수동 확인 필요",
                channel_key="SYSTEM", private=False
            )
        except Exception:
            print(f"  [ABORT] 모든 알림 실패!")


# ══════════════════════════════════════════════
#  Step 함수
# ══════════════════════════════════════════════

def _run_step(name, func):
    print(f"\n── {name} ──")
    t = datetime.now()
    try:
        func()
        print(f"✅ {name} ({(datetime.now()-t).total_seconds():.1f}초)")
        return "OK"
    except Exception as e:
        print(f"❌ {name} ({(datetime.now()-t).total_seconds():.1f}초): {e}")
        traceback.print_exc()
        return f"FAIL: {e}"


def _s_price(d):
    from batch.batch_ticker_item_daily import run_daily_price; run_daily_price(d)

def _s_fin(d):
    from batch.batch_ticker_item_daily import run_supplement_financials; run_supplement_financials()

def _s_l1(d):
    from batch.batch_ticker_item_daily import run_quant_score; run_quant_score(d)

def _s_l3(d):
    from batch.batch_layer3_v2 import run_technical_indicators; run_technical_indicators(d)

def _s_l2(d):
    from batch.batch_layer2_v2 import run_all as r; r()

def _s_ec(d):
    from batch.batch_earnings_call import run_earnings_call_analysis; run_earnings_call_analysis(d)

def _s_insider():
    print('[INSIDER] L2 GroupB에서 처리 완료 → skip')

def _s_macro():
    from batch.batch_macro import run_macro; run_macro()

def _s_final(d):
    from batch.batch_final_score import run_final_score; run_final_score(d)

def _s_chart_patterns(d):
    from batch.batch_chart_patterns import run_chart_patterns; run_chart_patterns(d)

def _s_fear_greed(d):
    from batch.batch_fear_greed import run_fear_greed; run_fear_greed(d)

def _s_trading(d):
    live = os.environ.get("TRADING_LIVE", "0") == "1"
    from batch.batch_trading_signals import run_trading_signals
    run_trading_signals(calc_date=d, dry_run=not live)

def _s_notify_all(calc_date, results, start_time):
    """Step 8: 배치 완료 후 알림 발송"""
    elapsed = (datetime.now() - start_time).total_seconds()
    sent = 0
    # 8a: 배치 완료
    try:
        from notifier import notify_batch_complete
        notify_batch_complete(calc_date, elapsed, results)
        sent += 1
        print(f"  [8a] ✅ 배치 완료 알림")
    except Exception as e:
        print(f"  [8a] ⚠️ {e}")
    # 8b~8g: 추가 알림 (데이터 있을 때만)
    try:
        from db_pool import get_cursor
        GRADE_ORDER = {"S":7,"A+":6,"A":5,"B+":4,"B":3,"C":2,"D":1}
        with get_cursor() as cur:
            cur.execute("""SELECT t.stock_id, s.ticker, t.grade AS tg, y.grade AS pg
                FROM final_scores t JOIN stocks s ON s.stock_id=t.stock_id
                LEFT JOIN final_scores y ON y.stock_id=t.stock_id
                    AND y.calc_date=(SELECT MAX(calc_date) FROM final_scores WHERE stock_id=t.stock_id AND calc_date<%s)
                WHERE t.calc_date=%s AND y.grade IS NOT NULL AND t.grade!=y.grade""", (calc_date, calc_date))
            rows = cur.fetchall()
        up = [r for r in rows if GRADE_ORDER.get(r["tg"],0)-GRADE_ORDER.get(r["pg"],0)>=2]
        dn = [r for r in rows if GRADE_ORDER.get(r["pg"],0)-GRADE_ORDER.get(r["tg"],0)>=2]
        if up or dn:
            from notifier import notify_grade_changes
            notify_grade_changes(calc_date,
                [{"ticker":r["ticker"],"prev_grade":r["pg"],"new_grade":r["tg"]} for r in up],
                [{"ticker":r["ticker"],"prev_grade":r["pg"],"new_grade":r["tg"]} for r in dn])
            sent += 1
            print(f"  [8b] ✅ 등급 변동 (↑{len(up)} ↓{len(dn)})")
        else:
            print(f"  [8b] ─ 등급 변동 없음")
    except Exception as e:
        print(f"  [8b] ⚠️ {e}")
    print(f"\n  📨 알림: {sent}건 발송")

def _s_weekly(d):
    """주간 성과 리포트"""
    from db_pool import get_cursor
    from datetime import timedelta
    week_start = d - timedelta(days=7)

    with get_cursor() as cur:
        cur.execute("""
            SELECT total_value FROM portfolio_daily_snapshot
            WHERE portfolio_id = 1 AND snapshot_date >= %s
            ORDER BY snapshot_date
        """, (week_start,))
        rows = cur.fetchall()

    if len(rows) < 2:
        print("  주간 데이터 부족 — 스킵")
        return

    start_val = float(rows[0]["total_value"])
    end_val = float(rows[-1]["total_value"])
    week_return = (end_val - start_val) / start_val * 100 if start_val > 0 else 0

    with get_cursor() as cur:
        cur.execute("""
            SELECT trade_type, COUNT(*) as cnt
            FROM trade_history
            WHERE trade_date >= %s AND trade_date <= %s
            GROUP BY trade_type
        """, (week_start, d))
        trades = {r["trade_type"]: r["cnt"] for r in cur.fetchall()}

    try:
        from notifier import notify_weekly_report
        notify_weekly_report(
            calc_date=d,
            week_return=week_return,
            total_value=end_val,
            spy_return=0,  # TODO: SPY 수익률 조회
            win_rate=0,
            num_trades=sum(trades.values()),
        )
        print(f"  ✅ 주간 리포트 발송 (수익률: {week_return:+.2f}%)")
    except Exception as e:
        print(f"  ⚠️ 주간 리포트 실패: {e}")


def _s_monthly(d):
    """월간 성과 리포트"""
    from db_pool import get_cursor
    from datetime import timedelta
    month_start = (d.replace(day=1) - timedelta(days=1)).replace(day=1)

    with get_cursor() as cur:
        cur.execute("""
            SELECT MIN(total_value) as min_val, MAX(total_value) as max_val,
                   (array_agg(total_value ORDER BY snapshot_date))[1] as first_val,
                   (array_agg(total_value ORDER BY snapshot_date DESC))[1] as last_val
            FROM portfolio_daily_snapshot
            WHERE portfolio_id = 1 AND snapshot_date >= %s AND snapshot_date < %s
        """, (month_start, d))
        row = cur.fetchone()

    if not row or not row["first_val"]:
        print("  월간 데이터 부족 — 스킵")
        return

    first_v = float(row["first_val"])
    last_v = float(row["last_val"])
    month_return = (last_v - first_v) / first_v * 100 if first_v > 0 else 0

    try:
        from notifier import notify_weekly_report
        notify_weekly_report(
            calc_date=d,
            week_return=month_return,
            total_value=last_v,
        )
        print(f"  ✅ 월간 리포트 발송 (수익률: {month_return:+.2f}%)")
    except Exception as e:
        print(f"  ⚠️ 월간 리포트 실패: {e}")


# ══════════════════════════════════════════════
#  ★ APScheduler 자동 실행
# ══════════════════════════════════════════════

def start_scheduler():
    """APScheduler로 자동 배치 시작"""
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        print("=" * 60)
        print("  ⚠ APScheduler 미설치!")
        print("  pip install apscheduler")
        print("=" * 60)
        print("\n  APScheduler 없이 1회 실행합니다...")
        run_all()
        return

    from dotenv import load_dotenv
    load_dotenv()
    from db_pool import init_pool
    init_pool()

    sched = BlockingScheduler(timezone="US/Eastern")

    sched.add_job(
        run_all,
        CronTrigger(day_of_week="mon-fri", hour=21, minute=0, timezone="US/Eastern"),
        id="daily_batch",
        name="일일 배치 (21:00 ET)",
        misfire_grace_time=3600,
    )

    sched.add_job(
        lambda: _s_weekly(datetime.now().date()),
        CronTrigger(day_of_week="sat", hour=9, minute=0, timezone="US/Eastern"),
        id="weekly_report",
        name="주간 성과 리포트",
    )

    sched.add_job(
        lambda: _s_monthly(datetime.now().date()),
        CronTrigger(day=1, hour=9, minute=0, timezone="US/Eastern"),
        id="monthly_report",
        name="월간 성과 리포트",
    )

    print("=" * 60)
    print("  🤖 QUANT AI v3.6 Scheduler 시작")
    print("=" * 60)
    print(f"  일일 배치:   평일 21:00 ET (애프터마켓 종료 +1h)")
    print(f"  주간 리포트: 토요일 09:00 ET")
    print(f"  월간 리포트: 매월 1일 09:00 ET")
    print(f"  현재 시각:   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  안전장치:    가격실패 {PRICE_FAIL_THRESHOLD_PCT}%↑ 시 중단")
    print("=" * 60)

    try:
        from notifier import send_message
        send_message("🤖 QUANT AI v3.6 Scheduler 시작 — 안전장치 활성화", channel_key="SYSTEM", private=False)
    except Exception:
        pass

    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        print("\n[Scheduler] 종료됨")
        try:
            from notifier import send_message
            send_message("🔧 QUANT AI Scheduler 종료됨", channel_key="SYSTEM", private=False)
        except Exception:
            pass


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    from db_pool import init_pool
    init_pool()

    if "--now" in sys.argv:
        print("▶ 즉시 실행 모드")
        run_all()
    else:
        start_scheduler()