"""batch_insider.py — 내부자 거래 (L2 Finnhub 위임)"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def run_insider_trades():
    print("[INSIDER] L2 GroupB에서 Finnhub 수집 완료 → skip")

if __name__ == "__main__":
    run_insider_trades()