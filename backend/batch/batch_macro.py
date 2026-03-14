"""
매일 09:00 실행 (Phase 3).
FDR/FRED → 거시지표 수집 → macro_indicators.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import FinanceDataReader as fdr
from datetime import datetime, timedelta
from db_pool import get_cursor


MACRO_TARGETS = [
    ("^VIX",    "VIX",         "VOLATILITY"),
    ("US10YT",  "US10Y_YIELD", "BOND"),
    ("US2YT",   "US2Y_YIELD",  "BOND"),
    ("GC=F",    "GOLD",        "COMMODITY"),
    ("CL=F",    "OIL_WTI",     "COMMODITY"),
    ("USD/KRW", "USD_KRW",     "FX"),
    ("S&P500",  "SP500",       "INDEX"),
]


def run_macro():
    calc_date = datetime.now().date()
    ok, fail  = 0, 0

    for symbol, name, category in MACRO_TARGETS:
        try:
            df = fdr.DataReader(symbol)
            if df is None or df.empty:
                fail += 1
                continue

            latest = df.iloc[-1]
            prev   = df.iloc[-2] if len(df) > 1 else latest
            val    = float(latest["Close"])
            chg    = round((val - float(prev["Close"])) / float(prev["Close"]) * 100, 4) \
                     if float(prev["Close"]) != 0 else 0

            with get_cursor() as cur:
                cur.execute("""
                    INSERT INTO macro_indicators (
                        indicator_name, indicator_category,
                        value, change_pct, recorded_date, data_source
                    ) VALUES (%s,%s,%s,%s,%s,'FDR')
                    ON CONFLICT (indicator_name, recorded_date) DO UPDATE SET
                        value      = EXCLUDED.value,
                        change_pct = EXCLUDED.change_pct
                """, (name, category, val, chg, calc_date))

            ok += 1
            print(f"[MACRO] {name}: {val} ({chg:+.2f}%) ✓")

        except Exception as e:
            fail += 1
            print(f"[MACRO] {symbol} 실패: {e}")

    print(f"[MACRO] 완료: {ok}성공 / {fail}실패")


if __name__ == "__main__":
    from db_pool import init_pool
    init_pool()
    run_macro()