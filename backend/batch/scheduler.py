"""
APScheduler 기반 배치잡 스케줄러.
실행: python -m batch.scheduler
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
from db_pool import init_pool


def run_with_log(name: str, fn):
    print(f"\n{'='*60}")
    print(f"[SCHEDULER] {name} 시작: {datetime.now()}")
    try:
        fn()
        print(f"[SCHEDULER] {name} 완료: {datetime.now()}")
    except Exception as e:
        print(f"[SCHEDULER] {name} 실패: {e}")


def main():
    init_pool()

    from batch.batch_ticker_item_daily import run_daily_price, run_supplement_financials, run_quant_score
    from batch.batch_layer3 import run_technical_indicators
    from batch.batch_layer2 import run_all as run_layer2
    from batch.batch_final_score import run_final_score
    from batch.batch_insider import run_insider_trades
    from batch.batch_macro import run_macro

    scheduler = BlockingScheduler(timezone="America/New_York")

    # Phase 1 - 매일 02:00 ET (장 마감 후)
    scheduler.add_job(
        lambda: run_with_log("DAILY_PRICE", run_daily_price),
        CronTrigger(hour=2, minute=0), id="daily_price"
    )
    scheduler.add_job(
        lambda: run_with_log("SUPPLEMENT_FINANCIALS", run_supplement_financials),
        CronTrigger(hour=2, minute=30), id="supplement_financials"
    )
    scheduler.add_job(
        lambda: run_with_log("QUANT_SCORE_L1", run_quant_score),
        CronTrigger(hour=3, minute=0), id="quant_score"
    )

    # Phase 2 - 기술지표 03:00 ET
    scheduler.add_job(
        lambda: run_with_log("TECH_INDICATOR", run_technical_indicators),
        CronTrigger(hour=3, minute=30), id="tech_indicator"
    )

    # Phase 2 - 뉴스/애널리스트 06:00 ET
    scheduler.add_job(
        lambda: run_with_log("LAYER2", run_layer2),
        CronTrigger(hour=6, minute=0), id="layer2"
    )

    # Phase 2 - 최종 점수 07:00 ET
    scheduler.add_job(
        lambda: run_with_log("FINAL_SCORE", run_final_score),
        CronTrigger(hour=7, minute=0), id="final_score"
    )

    # Phase 2 - 내부자거래 매 2시간
    scheduler.add_job(
        lambda: run_with_log("INSIDER", run_insider_trades),
        CronTrigger(hour="*/2", minute=0), id="insider"
    )

    # Phase 3 - 거시지표 09:00 ET
    scheduler.add_job(
        lambda: run_with_log("MACRO", run_macro),
        CronTrigger(hour=9, minute=0), id="macro"
    )

    print("=" * 60)
    print("[SCHEDULER] 시작됨")
    print("  02:00 - DAILY_PRICE (전일 OHLCV)")
    print("  02:30 - SUPPLEMENT_FINANCIALS (파생지표 보완)")
    print("  03:00 - QUANT_SCORE L1")
    print("  03:30 - TECH_INDICATOR")
    print("  06:00 - LAYER2 (뉴스/애널리스트)")
    print("  07:00 - FINAL_SCORE (L1+L2+L3)")
    print("  09:00 - MACRO")
    print("  */2h  - INSIDER")
    print("=" * 60)

    scheduler.start()


if __name__ == "__main__":
    main()