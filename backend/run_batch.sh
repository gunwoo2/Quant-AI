cd ~/Quant-AI/backend

echo ""
echo "=========================================="
echo "  QUANT AI v3.3 �쇱씪 諛곗튂 �쒖옉"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="

echo "=== 1/9 DAILY PRICE ==="
python3 -m batch.batch_ticker_item_daily

echo "=== 2/9 LAYER3 (湲곗닠�� 遺꾩꽍) ==="
python3 -m batch.batch_layer3_v2

echo "=== 3/9 LAYER2 (�댁뒪/媛먯꽦) ==="
python3 -m batch.batch_layer2_v2

echo "=== 4/9 INSIDER (�대��먭굅��) ==="
python3 -m batch.batch_insider

echo "=== 5/9 MACRO (嫄곗떆吏���) ==="
python3 -m batch.batch_macro

echo "=== 6/9 FINAL SCORE (理쒖쥌�⑹궛) ==="
python3 -m batch.batch_final_score

echo "=== 7/9 TRADING SIGNALS (留ㅻℓ�쒓렇��) ==="
python3 -m batch.batch_trading_signals

echo "=== 8/9 BATCH COMPLETE NOTIFY ==="
python3 -c "
from dotenv import load_dotenv; load_dotenv()
from db_pool import init_pool; init_pool()
from notifier import send_message
from datetime import date
send_message(f'�� �섎룞 諛곗튂 �꾨즺 ({date.today()})', signal_type='REPORT')
print('[NOTIFY] 諛곗튂 �꾨즺 �뚮┝ 諛쒖넚')
"

echo ""
echo "=========================================="
echo "  ALL DONE �� $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="