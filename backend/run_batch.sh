#!/bin/bash
cd ~/Quant-AI/backend

echo "=== 1/7 DAILY PRICE ==="
python3 -m batch.batch_ticker_item_daily

echo "=== 2/7 LAYER3 ==="
python3 -m batch.batch_layer3_v2

echo "=== 3/7 LAYER2 ==="
python3 -m batch.batch_layer2_v2

echo "=== 4/7 INSIDER ==="
python3 -m batch.batch_insider

echo "=== 5/7 MACRO ==="
python3 -m batch.batch_macro

echo "=== 6/7 FINAL SCORE ==="
python3 -m batch.batch_final_score

echo "=== ALL DONE ==="
