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
"""
scheduler.py — QUANT AI v3.4
============================
v3.4 변경:
  - 모닝 브리핑 Step 추가 (장 시작 전)
  - 등급 변경 감지 + 알림
  - 어닝 D-day 알림
  - 일일 성과 리포트
  - 리스크 경고 알림 연결
  - ADD/FIRE/BOUNCE 시그널 연결

스케줄:
  평일 08:00 ET  — 모닝 브리핑 (장 시작 전)
  평일 21:00 ET  — 일일 배치 (14단계)
  토요일 09:00 ET — 주간 성과 리포트
  매월 1일 09:00 ET — 월간 성과 리포트
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, date, timedelta
import traceback
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("scheduler")


def run_all(calc_date: date = None):
    """14단계 일일 배치 파이프라인"""
    if calc_date is None:
        calc_date = datetime.now().date()
    start_all = datetime.now()
    results = {}
    print(f"\n{'='*60}")
    print(f"  QUANT AI v3.4 일일 배치 — {calc_date}")
    print(f"{'='*60}")

    # ── Phase 1: 데이터 수집 ──
    results["1_price"]    = _run_step("1/14 가격 수집",           lambda: _s_price(calc_date))
    results["2_fin"]      = _run_step("2/14 파생 재무",           lambda: _s_fin(calc_date))
    results["3_l1"]       = _run_step("3/14 Layer 1",             lambda: _s_l1(calc_date))
    results["4_l3"]       = _run_step("4/14 Layer 3",             lambda: _s_l3(calc_date))
    results["5_l2"]       = _run_step("5/14 Layer 2",             lambda: _s_l2(calc_date))

    if _should_earnings(calc_date):
        results["5.5_ec"]  = _run_step("5.5 어닝콜",             lambda: _s_ec(calc_date))
    else:
        results["5.5_ec"]  = "SKIP"

    results["5.6_insider"] = _run_step("5.6 내부자거래",          lambda: _s_insider())
    results["5.7_macro"]   = _run_step("5.7 거시지표",            lambda: _s_macro())

    # ── Phase 2: 계산 ──
    results["6_final"]     = _run_step("6/14 최종 합산",          lambda: _s_final(calc_date))

    # ── Phase 3: 시그널 + 알림 ──
    results["7_trading"]   = _run_step("7/14 트레이딩 시그널",     lambda: _s_trading(calc_date))
    results["8_grade"]     = _run_step("8/14 등급 변경 감지",      lambda: _s_grade_change(calc_date))
    results["9_earnings"]  = _run_step("9/14 어닝 D-day",         lambda: _s_earnings_alert(calc_date))
    results["10_risk"]     = _run_step("10/14 리스크 점검",        lambda: _s_risk_check(calc_date))
    results["11_perf"]     = _run_step("11/14 일일 성과",          lambda: _s_daily_performance(calc_date))
    results["12_notify"]   = _run_step("12/14 배치 완료 알림",     lambda: _s_notify(calc_date, results, start_all))

    # Step 13: 주간 성과 리포트 (토요일)
    if calc_date.weekday() == 5:
        results["13_weekly"] = _run_step("13/14 주간 성과",       lambda: _s_weekly(calc_date))
    else:
        results["13_weekly"] = "SKIP"

    # Step 14: 월간 성과 리포트 (매월 1일)
    if calc_date.day == 1:
        results["14_monthly"] = _run_step("14/14 월간 성과",      lambda: _s_monthly(calc_date))
    else:
        results["14_monthly"] = "SKIP"

    elapsed = datetime.now() - start_all
    ok   = sum(1 for v in results.values() if v == "OK")
    fail = sum(1 for v in results.values() if isinstance(v, str) and v.startswith("FAIL"))
    skip = sum(1 for v in results.values() if v == "SKIP")
    print(f"\n{'='*60}")
    print(f"  결과: 성공={ok} 실패={fail} 스킵={skip} | 소요: {elapsed}")
    print(f"{'='*60}")
    return results


def run_morning(calc_date: date = None):
    """모닝 브리핑 (장 시작 전 별도 실행)"""
    if calc_date is None:
        calc_date = datetime.now().date()
    print(f"\n{'='*60}")
    print(f"  ☀️ 모닝 브리핑 — {calc_date}")
    print(f"{'='*60}")
    _s_morning_briefing(calc_date)


# ══════════════════════════════════════════════
#  기존 Step 함수 (1~7)
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
    from batch.batch_layer2_v2 import run_all as r; r()

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


# ══════════════════════════════════════════════
#  ★ 신규 Step 함수 (8~14)
# ══════════════════════════════════════════════

def _s_grade_change(d):
    """등급 변경 감지 → 알림"""
    from db_pool import get_cursor

    # 오늘 vs 어제 등급 비교 (보유종목 + 전체 주요 변동)
    with get_cursor() as cur:
        cur.execute("""
            SELECT t.stock_id, s.ticker,
                   t.final_grade  AS new_grade, t.final_score AS new_score,
                   y.final_grade  AS old_grade, y.final_score AS old_score
            FROM stock_final_scores t
            JOIN stock_final_scores y
                ON t.stock_id = y.stock_id
                AND y.calc_date = (
                    SELECT MAX(calc_date) FROM stock_final_scores
                    WHERE calc_date < t.calc_date
                )
            JOIN stocks s ON t.stock_id = s.stock_id
            WHERE t.calc_date = %s
              AND t.final_grade IS NOT NULL
              AND y.final_grade IS NOT NULL
              AND t.final_grade != y.final_grade
            ORDER BY ABS(t.final_score - y.final_score) DESC
            LIMIT 20
        """, (d,))
        changes = [dict(r) for r in cur.fetchall()]

    if not changes:
        print("  등급 변경 없음")
        return

    grade_order = {"S": 7, "A+": 6, "A": 5, "B+": 4, "B": 3, "C": 2, "D": 1}
    upgrades = []
    downgrades = []
    for c in changes:
        new_rank = grade_order.get(c["new_grade"], 0)
        old_rank = grade_order.get(c["old_grade"], 0)
        item = {
            "ticker": c["ticker"],
            "old_grade": c["old_grade"],
            "new_grade": c["new_grade"],
            "old_score": float(c["old_score"]) if c["old_score"] else 0,
            "new_score": float(c["new_score"]) if c["new_score"] else 0,
        }
        if new_rank > old_rank:
            item["direction"] = "UP"
            upgrades.append(item)
        else:
            item["direction"] = "DOWN"
            downgrades.append(item)

    print(f"  등급변경: ⬆{len(upgrades)} ⬇{len(downgrades)}")

    from notifier import notify_grade_changes
    notify_grade_changes(d, upgrades, downgrades)


def _s_earnings_alert(d):
    """보유종목 어닝 D-day 확인 → 알림"""
    from db_pool import get_cursor

    with get_cursor() as cur:
        # earnings_calls 테이블 또는 yfinance calendar에서 어닝 날짜 확인
        # 간단 방식: stock_fundamentals의 next_earnings_date 활용
        cur.execute("""
            SELECT s.ticker, s.company_name,
                   f.final_grade AS grade
            FROM stocks s
            JOIN stock_final_scores f ON s.stock_id = f.stock_id
                AND f.calc_date = (SELECT MAX(calc_date) FROM stock_final_scores)
            WHERE s.is_active = TRUE
              AND s.next_earnings_date = %s
        """, (d,))
        earnings = [dict(r) for r in cur.fetchall()]

    if not earnings:
        # next_earnings_date 컬럼이 없을 수 있으니 yfinance fallback
        try:
            import yfinance as yf
            # 보유종목만 체크
            with get_cursor() as cur:
                cur.execute("""
                    SELECT DISTINCT s.ticker
                    FROM portfolio_positions pp
                    JOIN stocks s ON pp.stock_id = s.stock_id
                    WHERE pp.status = 'OPEN'
                """)
                held = [r["ticker"] for r in cur.fetchall()]

            earnings = []
            for ticker in held[:20]:
                try:
                    cal = yf.Ticker(ticker).calendar
                    if cal is not None and not cal.empty:
                        earn_date = cal.iloc[0].get("Earnings Date", None)
                        if earn_date and str(earn_date)[:10] == str(d):
                            earnings.append({
                                "ticker": ticker,
                                "time": "TBD",
                                "eps_estimate": float(cal.iloc[0].get("EPS Estimate", 0) or 0),
                                "rev_estimate": float(cal.iloc[0].get("Revenue Estimate", 0) or 0),
                                "grade": "",
                            })
                except Exception:
                    pass
        except Exception as e:
            print(f"  어닝 확인 실패: {e}")

    if not earnings:
        print("  오늘 어닝 발표 종목 없음")
        return

    print(f"  어닝 D-day: {len(earnings)}종목")
    from notifier import notify_earnings_alert
    notify_earnings_alert(d, earnings)


def _s_risk_check(d):
    """리스크 상태 점검 → 경고 알림"""
    from db_pool import get_cursor

    # Drawdown 확인
    with get_cursor() as cur:
        cur.execute("""
            SELECT total_value FROM portfolio_daily_snapshot
            WHERE portfolio_id = 1
            ORDER BY snapshot_date DESC LIMIT 1
        """)
        row = cur.fetchone()
        current_value = float(row["total_value"]) if row and row["total_value"] else 0

        cur.execute("""
            SELECT MAX(total_value) as peak FROM portfolio_daily_snapshot
            WHERE portfolio_id = 1
        """)
        row = cur.fetchone()
        peak_value = float(row["peak"]) if row and row["peak"] else current_value

    dd_pct = (current_value - peak_value) / peak_value * 100 if peak_value > 0 else 0

    if dd_pct > -3:
        dd_mode = "NORMAL"
    elif dd_pct > -7:
        dd_mode = "CAUTION"
    elif dd_pct > -12:
        dd_mode = "WARNING"
    elif dd_pct > -20:
        dd_mode = "DANGER"
    else:
        dd_mode = "CRITICAL"

    # 섹터 집중도 확인
    concentration_warn = []
    with get_cursor() as cur:
        cur.execute("""
            SELECT sec.sector_name,
                   COUNT(*) as cnt,
                   ROUND(COUNT(*)::numeric / NULLIF(SUM(COUNT(*)) OVER(), 0) * 100, 1) as pct
            FROM portfolio_positions pp
            JOIN stocks s ON pp.stock_id = s.stock_id
            LEFT JOIN sectors sec ON s.sector_id = sec.sector_id
            WHERE pp.status = 'OPEN'
            GROUP BY sec.sector_name
            HAVING COUNT(*)::numeric / NULLIF(SUM(COUNT(*)) OVER(), 0) * 100 > 30
        """)
        for r in cur.fetchall():
            concentration_warn.append({
                "sector": r["sector_name"] or "Unknown",
                "pct": float(r["pct"]),
            })

    print(f"  DD: {dd_mode} ({dd_pct:.1f}%) | 집중도 경고: {len(concentration_warn)}건")

    # CAUTION 이상이거나 집중도 경고 시 알림
    if dd_mode != "NORMAL" or concentration_warn:
        from notifier import notify_risk_warning
        notify_risk_warning(
            calc_date=d,
            dd_mode=dd_mode,
            drawdown_pct=abs(dd_pct),
            concentration_warn=concentration_warn,
        )


def _s_daily_performance(d):
    """일일 포트폴리오 성과 리포트"""
    from db_pool import get_cursor

    with get_cursor() as cur:
        # 오늘/어제 포트폴리오 가치
        cur.execute("""
            SELECT snapshot_date, total_value
            FROM portfolio_daily_snapshot
            WHERE portfolio_id = 1
            ORDER BY snapshot_date DESC LIMIT 2
        """)
        rows = cur.fetchall()

    if len(rows) < 2:
        print("  성과 데이터 부족 — 스킵")
        return

    today_val = float(rows[0]["total_value"])
    yesterday_val = float(rows[1]["total_value"])
    daily_return = (today_val - yesterday_val) / yesterday_val * 100 if yesterday_val > 0 else 0

    # SPY 수익률
    spy_return = 0
    with get_cursor() as cur:
        cur.execute("""
            SELECT close_price FROM stock_prices_daily
            WHERE stock_id = (SELECT stock_id FROM stocks WHERE ticker = 'SPY' LIMIT 1)
            ORDER BY trade_date DESC LIMIT 2
        """)
        spy_rows = cur.fetchall()
        if len(spy_rows) == 2:
            spy_today = float(spy_rows[0]["close_price"])
            spy_yesterday = float(spy_rows[1]["close_price"])
            spy_return = (spy_today - spy_yesterday) / spy_yesterday * 100

    # 보유 종목 수
    with get_cursor() as cur:
        cur.execute("SELECT COUNT(*) as cnt FROM portfolio_positions WHERE status = 'OPEN'")
        num_positions = cur.fetchone()["cnt"]

    # 최고/최저 종목
    best_ticker, best_pnl = "", 0
    worst_ticker, worst_pnl = "", 0
    with get_cursor() as cur:
        cur.execute("""
            SELECT s.ticker,
                   ROUND((p.close_price - pp.entry_price) / pp.entry_price * 100, 2) as pnl_pct
            FROM portfolio_positions pp
            JOIN stocks s ON pp.stock_id = s.stock_id
            JOIN stock_prices_daily p ON pp.stock_id = p.stock_id
                AND p.trade_date = (SELECT MAX(trade_date) FROM stock_prices_daily)
            WHERE pp.status = 'OPEN'
            ORDER BY pnl_pct DESC
        """)
        pos_rows = cur.fetchall()
        if pos_rows:
            best_ticker = pos_rows[0]["ticker"]
            best_pnl = float(pos_rows[0]["pnl_pct"])
            worst_ticker = pos_rows[-1]["ticker"]
            worst_pnl = float(pos_rows[-1]["pnl_pct"])

    print(f"  포트폴리오: ${today_val:,.0f} ({daily_return:+.2f}%) vs SPY ({spy_return:+.2f}%)")

    from notifier import notify_daily_performance
    notify_daily_performance(
        calc_date=d,
        portfolio_value=today_val,
        daily_return=daily_return,
        spy_return=spy_return,
        best_ticker=best_ticker,
        best_pnl=best_pnl,
        worst_ticker=worst_ticker,
        worst_pnl=worst_pnl,
        num_positions=num_positions,
        total_pnl=today_val - 50000,  # 초기 자본 대비
    )


def _s_morning_briefing(d):
    """모닝 브리핑 — 장 시작 전"""
    from db_pool import get_cursor

    # 시장 국면
    with get_cursor() as cur:
        cur.execute("""
            SELECT indicator_name, value FROM macro_indicators
            WHERE indicator_name IN ('VIX', 'SP500')
              AND recorded_date = (SELECT MAX(recorded_date) FROM macro_indicators)
        """)
        macro = {r["indicator_name"]: float(r["value"]) for r in cur.fetchall()}

    spy_price = macro.get("SP500", 0)
    vix = macro.get("VIX", 0)
    if vix >= 30: regime = "CRISIS"
    elif vix >= 25: regime = "BEAR"
    elif vix >= 18: regime = "NEUTRAL"
    else: regime = "BULL"

    # Top 5 매수 후보
    with get_cursor() as cur:
        cur.execute("""
            SELECT s.ticker, f.final_grade AS grade, f.final_score AS score,
                   p.close_price AS price
            FROM stock_final_scores f
            JOIN stocks s ON f.stock_id = s.stock_id
            LEFT JOIN stock_prices_daily p ON f.stock_id = p.stock_id
                AND p.trade_date = (SELECT MAX(trade_date) FROM stock_prices_daily)
            WHERE f.calc_date = (SELECT MAX(calc_date) FROM stock_final_scores)
              AND f.final_score IS NOT NULL
              AND p.close_price IS NOT NULL
            ORDER BY f.final_score DESC
            LIMIT 5
        """)
        top_buys = [dict(r) for r in cur.fetchall()]
        for t in top_buys:
            t["score"] = float(t["score"])
            t["price"] = float(t["price"])

    # 등급 변경 (어제 → 오늘)
    grade_changes = []
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT s.ticker,
                       t.final_grade AS new_grade, t.final_score AS new_score,
                       y.final_grade AS old_grade, y.final_score AS old_score
                FROM stock_final_scores t
                JOIN stock_final_scores y
                    ON t.stock_id = y.stock_id
                    AND y.calc_date = (SELECT MAX(calc_date) FROM stock_final_scores WHERE calc_date < %s)
                JOIN stocks s ON t.stock_id = s.stock_id
                WHERE t.calc_date = %s
                  AND t.final_grade != y.final_grade
                ORDER BY ABS(t.final_score - y.final_score) DESC
                LIMIT 8
            """, (d, d))
            for r in cur.fetchall():
                grade_order = {"S": 7, "A+": 6, "A": 5, "B+": 4, "B": 3, "C": 2, "D": 1}
                direction = "UP" if grade_order.get(r["new_grade"], 0) > grade_order.get(r["old_grade"], 0) else "DOWN"
                grade_changes.append({
                    "ticker": r["ticker"],
                    "old_grade": r["old_grade"],
                    "new_grade": r["new_grade"],
                    "score": float(r["new_score"]),
                    "direction": direction,
                })
    except Exception:
        pass

    # 포트폴리오 현황
    portfolio_summary = None
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT total_value FROM portfolio_daily_snapshot
                WHERE portfolio_id = 1 ORDER BY snapshot_date DESC LIMIT 1
            """)
            row = cur.fetchone()
            if row:
                with get_cursor() as cur2:
                    cur2.execute("SELECT COUNT(*) as cnt FROM portfolio_positions WHERE status = 'OPEN'")
                    cnt = cur2.fetchone()["cnt"]
                portfolio_summary = {
                    "total_value": float(row["total_value"]),
                    "daily_return": 0,
                    "num_positions": cnt,
                }
    except Exception:
        pass

    from notifier import notify_morning_briefing
    notify_morning_briefing(
        calc_date=d,
        regime=regime,
        regime_detail={"spy_price": spy_price, "vix_close": vix},
        top_buys=top_buys,
        grade_changes=grade_changes if grade_changes else None,
        portfolio_summary=portfolio_summary,
    )


# ══════════════════════════════════════════════
#  기존 Step 함수 (notify, weekly, monthly)
# ══════════════════════════════════════════════

def _s_notify(d, results, start_time):
    try:
        from notifier import notify_batch_complete
        elapsed = (datetime.now() - start_time).total_seconds()
        notify_batch_complete(d, elapsed, results)
        print(f"  [NOTIFY] ✅ 배치 완료 알림 발송")
    except Exception as e:
        print(f"  [NOTIFY] ⚠ 알림 실패: {e}")
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
            print(f"  [NOTIFY] ⚠ fallback도 실패: {e2}")


def _s_weekly(d):
    from db_pool import get_cursor
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

    # SPY 주간 수익률
    spy_return = 0
    with get_cursor() as cur:
        cur.execute("""
            SELECT close_price FROM stock_prices_daily
            WHERE stock_id = (SELECT stock_id FROM stocks WHERE ticker = 'SPY' LIMIT 1)
              AND trade_date >= %s
            ORDER BY trade_date
        """, (week_start,))
        spy_rows = cur.fetchall()
        if len(spy_rows) >= 2:
            spy_return = (float(spy_rows[-1]["close_price"]) - float(spy_rows[0]["close_price"])) / float(spy_rows[0]["close_price"]) * 100

    from notifier import notify_weekly_report
    notify_weekly_report(
        calc_date=d,
        week_return=week_return,
        total_value=end_val,
        spy_return=spy_return,
    )


def _s_monthly(d):
    from db_pool import get_cursor
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

    from notifier import send_discord_embed
    embeds = [{
        "title": f"🏆 월간 성과 리포트 — {month_start.strftime('%Y-%m')}",
        "color": 0x22c55e if month_return >= 0 else 0xef4444,
        "fields": [
            {"name": "월간 수익률", "value": f"{month_return:+.2f}%", "inline": True},
            {"name": "총 자산", "value": f"${last:,.0f}", "inline": True},
            {"name": "MDD", "value": f"{(float(row['min_val']) - float(row['max_val'])) / float(row['max_val']) * 100:.1f}%", "inline": True},
        ],
        "footer": {"text": "QUANT AI v3.4 월간 리포트"},
    }]
    send_discord_embed(embeds, signal_type="REPORT")
    print(f"  ✅ 월간 리포트 발송 ({month_return:+.2f}%)")


# ══════════════════════════════════════════════
#  유틸리티
# ══════════════════════════════════════════════

def _run_step(name: str, func) -> str:
    print(f"\n── {name} ──")
    try:
        func()
        return "OK"
    except Exception as e:
        print(f"  ❌ {name} 실패: {e}")
        traceback.print_exc()
        return f"FAIL: {str(e)[:100]}"


def _should_earnings(d):
    """어닝 시즌 체크 (1,4,7,10월)"""
    return d.month in (1, 4, 7, 10)


if __name__ == "__main__":
    from db_pool import init_pool
    init_pool()

    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--morning", action="store_true", help="모닝 브리핑만")
    parser.add_argument("--date", type=str, default=None)
    args = parser.parse_args()

    calc_date = date.fromisoformat(args.date) if args.date else date.today()

    if args.morning:
        run_morning(calc_date)
    else:
        run_all(calc_date)