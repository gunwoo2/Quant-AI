#!/bin/bash
# ═══════════════════════════════════════════════════
#  QUANT AI v3.3 — 일일 배치 (수동 실행용)
# ═══════════════════════════════════════════════════
#  사용법: cd ~/Quant-AI/backend && bash run_batch.sh
#
#  ★ 자동 실행은 scheduler.py 사용 권장
#    python3 -m batch.scheduler
# ═══════════════════════════════════════════════════

cd ~/Quant-AI/backend

echo ""
echo "=========================================="
echo "  QUANT AI v3.3 일일 배치 시작"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="

echo "=== 1/9 DAILY PRICE ==="
python3 -m batch.batch_ticker_item_daily

echo "=== 2/9 LAYER3 (기술적 분석) ==="
python3 -m batch.batch_layer3_v2

echo "=== 3/9 LAYER2 (뉴스/감성) ==="
python3 -m batch.batch_layer2_v2

echo "=== 4/9 INSIDER (내부자거래) ==="
python3 -m batch.batch_insider

echo "=== 5/9 MACRO (거시지표) ==="
python3 -m batch.batch_macro

echo "=== 6/9 FINAL SCORE (최종합산) ==="
python3 -m batch.batch_final_score

echo "=== 7/9 TRADING SIGNALS (매매시그널) ==="
python3 -m batch.batch_trading_signals

echo "=== 8/9 BATCH COMPLETE NOTIFY ==="
python3 -c "
from dotenv import load_dotenv; load_dotenv()
from db_pool import init_pool; init_pool()
from notifier import send_message
from datetime import date
send_message(f'✅ 수동 배치 완료 ({date.today()})', signal_type='REPORT')
print('[NOTIFY] 배치 완료 알림 발송')
"

echo ""
echo "=========================================="
echo "  ALL DONE — $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="
