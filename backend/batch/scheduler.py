"""
scheduler.py — QUANT AI v3.3
============================
미장 애프터마켓 종료(20:00 ET) + 1시간 = **21:00 ET 자동 실행**

실행 방법:
  cd ~/Quant-AI/backend
  python3 -m batch.scheduler          # 포그라운드
  nohup python3 -m batch.scheduler &  # 백그라운드 (권장)

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


def run_all(calc_date: date = None):
    """10단계 일일 배치 파이프라인 (수동 호출 가능)"""
    if calc_date is None:
        calc_date = datetime.now().date()
    start_all = datetime.now()
    results = {}
    print(f"\n{'='*60}\n  QUANT AI v3.3 일일 배치 — {calc_date}\n{'='*60}")

    results["1_price"]    = _run_step("1/10 가격 수집",         lambda: _s_price(calc_date))
    results["2_fin"]      = _run_step("2/10 파생 재무",         lambda: _s_fin(calc_date))
    results["3_l1"]       = _run_step("3/10 Layer 1",           lambda: _s_l1(calc_date))
    results["4_l3"]       = _run_step("4/10 Layer 3",           lambda: _s_l3(calc_date))
    results["5_l2"]       = _run_step("5/10 Layer 2",           lambda: _s_l2(calc_date))

    if _should_earnings(calc_date):
        results["5.5_ec"]  = _run_step("5.5 어닝콜",           lambda: _s_ec(calc_date))
    else:
        results["5.5_ec"]  = "SKIP"

    results["5.6_insider"] = _run_step("5.6 내부자거래",       lambda: _s_insider())
    results["5.7_macro"]   = _run_step("5.7 거시지표",         lambda: _s_macro())
    results["6_final"]     = _run_step("6/10 최종 합산",       lambda: _s_final(calc_date))
    results["7_trading"]   = _run_step("7/10 트레이딩 시그널",  lambda: _s_trading(calc_date))
    results["8_notify"]    = _run_step("8/10 일일 알림",       lambda: _s_notify(calc_date, results, start_all))

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
    print(f"\n{'='*60}\n  결과: 성공={ok} 실패={fail} 스킵={skip} | 소요: {elapsed}\n{'='*60}")
    return results


# ══════════════════════════════════════════════
#  Step 함수
# ══════════════════════════════════════════════

def _s_price(d):
    from batch.batch_ticker_item_daily import run_daily_price; run_daily_price(d)

def _s_fin(d):
    from batch.batch_ticker_item_daily import run_supplement_financials; run_supplement_financials(d)

def _s_l1(d):
    from batch.batch_ticker_item_daily import run_quant_score; run_quant_score(d)

def _s_l3(d):
    from batch.batch_layer3_v2 import run_all as r; r(d)

def _s_l2(d):
    from batch.batch_layer2_v2 import run_all as r; r(d)

def _s_ec(d):
    from batch.batch_earnings_call import run_earnings_call_analysis; run_earnings_call_analysis(d)

def _s_insider():
    from batch.batch_insider import run_insider_trades; run_insider_trades()

def _s_macro():
    from batch.batch_macro import run_macro; run_macro()

def _s_final(d):
    from batch.batch_final_score import run_final_score; run_final_score(d)

def _s_trading(d):
    live = os.environ.get("TRADING_LIVE", "0") == "1"
    from batch.batch_trading_signals import run_trading_signals
    run_trading_signals(calc_date=d, dry_run=not live)

def _s_notify(d, results, start_time):
    """배치 완료 알림 → Discord REPORT 채널"""
    try:
        from notifier import notify_batch_complete
        elapsed = (datetime.now() - start_time).total_seconds()
        notify_batch_complete(d, elapsed, results)
        print(f"  [NOTIFY] ✅ 배치 완료 알림 발송")
    except Exception as e:
        print(f"  [NOTIFY] ⚠ 알림 실패: {e}")
        # fallback: 직접 send_message
        try:
            from notifier import send_message
            ok = sum(1 for v in results.values() if v == "OK")
            fail = sum(1 for v in results.values() if isinstance(v, str) and v.startswith("FAIL"))
            send_message(
                f"{'✅' if fail == 0 else '⚠️'} 일일 배치 완료 ({d})\n"
                f"성공: {ok} | 실패: {fail} | 소요: {(datetime.now() - start_time).total_seconds():.0f}초",
                signal_type="REPORT"
            )
        except Exception as e2:
            print(f"  [NOTIFY] ⚠ fallback 알림도 실패: {e2}")


def _s_weekly(d):
    """주간 성과 리포트 → Discord REPORT 채널"""
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
        from notifier import send_discord_embed
        embeds = [{
            "title": f"📊 주간 성과 리포트 — {d}",
            "color": 0x22c55e if week_return >= 0 else 0xef4444,
            "fields": [
                {"name": "주간 수익률", "value": f"{week_return:+.2f}%", "inline": True},
                {"name": "총 자산", "value": f"${end_val:,.0f}", "inline": True},
                {"name": "매수", "value": f"{trades.get('BUY', 0)}건", "inline": True},
                {"name": "매도", "value": f"{trades.get('SELL', 0)}건", "inline": True},
            ],
            "footer": {"text": "QUANT AI v3.3 주간 리포트"},
        }]
        send_discord_embed(embeds, signal_type="REPORT")
        print(f"  ✅ 주간 리포트 발송 (수익률: {week_return:+.2f}%)")
    except Exception as e:
        print(f"  ⚠️ 주간 리포트 실패: {e}")


def _s_monthly(d):
    """월간 성과 리포트 → Discord REPORT 채널"""
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

    first = float(row["first_val"])
    last = float(row["last_val"])
    month_return = (last - first) / first * 100 if first > 0 else 0
    max_dd = (float(row["min_val"]) - float(row["max_val"])) / float(row["max_val"]) * 100

    try:
        from notifier import send_discord_embed
        embeds = [{
            "title": f"🏆 월간 성과 리포트 — {month_start.strftime('%Y-%m')}",
            "color": 0x22c55e if month_return >= 0 else 0xef4444,
            "fields": [
                {"name": "월간 수익률", "value": f"{month_return:+.2f}%", "inline": True},
                {"name": "최대 낙폭", "value": f"{max_dd:.1f}%", "inline": True},
                {"name": "총 자산", "value": f"${last:,.0f}", "inline": True},
            ],
            "footer": {"text": "QUANT AI v3.3 월간 리포트"},
        }]
        send_discord_embed(embeds, signal_type="REPORT")
        print(f"  ✅ 월간 리포트 발송 (수익률: {month_return:+.2f}%)")
    except Exception as e:
        print(f"  ⚠️ 월간 리포트 실패: {e}")


# ══════════════════════════════════════════════
#  유틸
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


def _should_earnings(d):
    if os.environ.get("FORCE_EARNINGS") == "1":
        return True
    return d.month in (1, 4, 7, 10) and 10 <= d.day <= 20


# ══════════════════════════════════════════════
#  ★ APScheduler 자동 실행
# ══════════════════════════════════════════════
#
#  미장 애프터마켓: 16:00~20:00 ET
#  배치 시작:       21:00 ET (애프터 종료 +1시간)
#  = KST 10:00 (서머타임) / 11:00 (겨울)
#
#  평일(월~금)만 실행

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

    scheduler = BlockingScheduler(timezone="US/Eastern")

    # ── 평일 21:00 ET: 일일 배치 ──
    scheduler.add_job(
        run_all,
        CronTrigger(day_of_week="mon-fri", hour=21, minute=0, timezone="US/Eastern"),
        id="daily_batch",
        name="일일 배치 (21:00 ET)",
        misfire_grace_time=3600,  # 1시간 내 미실행 건은 즉시 실행
    )

    # ── 토요일 09:00 ET: 주간 성과 리포트 ──
    scheduler.add_job(
        lambda: _s_weekly(datetime.now().date()),
        CronTrigger(day_of_week="sat", hour=9, minute=0, timezone="US/Eastern"),
        id="weekly_report",
        name="주간 성과 리포트",
    )

    # ── 매월 1일 09:00 ET: 월간 성과 리포트 ──
    scheduler.add_job(
        lambda: _s_monthly(datetime.now().date()),
        CronTrigger(day=1, hour=9, minute=0, timezone="US/Eastern"),
        id="monthly_report",
        name="월간 성과 리포트",
    )

    print("=" * 60)
    print("  🤖 QUANT AI v3.3 Scheduler 시작")
    print("=" * 60)
    print(f"  일일 배치:   평일 21:00 ET (애프터마켓 종료 +1h)")
    print(f"  주간 리포트: 토요일 09:00 ET")
    print(f"  월간 리포트: 매월 1일 09:00 ET")
    print(f"  현재 시각:   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 시작 알림
    try:
        from notifier import send_message
        send_message("🤖 QUANT AI Scheduler 시작됨 — 평일 21:00 ET 자동 배치", signal_type="SYSTEM")
    except Exception:
        pass

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\n[Scheduler] 종료됨")
        try:
            from notifier import send_message
            send_message("🔧 QUANT AI Scheduler 종료됨", signal_type="SYSTEM")
        except Exception:
            pass


# ══════════════════════════════════════════════
#  진입점
# ══════════════════════════════════════════════

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    from db_pool import init_pool
    init_pool()

    # --now 옵션: 즉시 1회 실행
    if "--now" in sys.argv:
        print("▶ 즉시 실행 모드")
        run_all()
    else:
        # 기본: APScheduler 자동 실행
        start_scheduler()
