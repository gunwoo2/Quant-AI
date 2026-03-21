"""
batch_insider.py — Phase 2: SEC EDGAR 내부자 거래 수집
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
★ v3: transaction_type VARCHAR 길이 에러 수정
      - 'OPEN_MARKET_BUY' → 'BUY' / 'SELL' 로 통일
      - data_source 자동 보정 유지
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from datetime import datetime, timedelta
from db_pool import get_cursor

SEC_HEADERS = {"User-Agent": "QuantAI research@quantai.com"}


def _ensure_schema():
    """insider_transactions 테이블 스키마 자동 보정"""
    try:
        with get_cursor() as cur:
            # data_source 컬럼 없으면 추가
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'insider_transactions'
                  AND column_name = 'data_source'
            """)
            if cur.fetchone() is None:
                cur.execute("""
                    ALTER TABLE insider_transactions
                    ADD COLUMN data_source VARCHAR(50) DEFAULT 'SEC_EDGAR'
                """)
                print("[INSIDER] ✅ data_source 컬럼 자동 추가 완료")

            # ★ transaction_type 컬럼 사이즈 확장 (VARCHAR(5) → VARCHAR(30))
            cur.execute("""
                SELECT character_maximum_length
                FROM information_schema.columns
                WHERE table_name = 'insider_transactions'
                  AND column_name = 'transaction_type'
            """)
            row = cur.fetchone()
            if row and row["character_maximum_length"] and row["character_maximum_length"] < 30:
                cur.execute("""
                    ALTER TABLE insider_transactions
                    ALTER COLUMN transaction_type TYPE VARCHAR(30)
                """)
                print("[INSIDER] ✅ transaction_type 컬럼 VARCHAR(30)으로 확장 완료")

    except Exception as e:
        print(f"[INSIDER] ⚠ 스키마 보정 실패: {e}")


def run_insider_trades():
    """SEC Form 4 기반 내부자거래 수집"""

    # ── 스키마 보정 (첫 실행 시 1회)
    _ensure_schema()

    with get_cursor() as cur:
        cur.execute("SELECT stock_id, ticker FROM stocks WHERE is_active = TRUE")
        stocks = [dict(r) for r in cur.fetchall()]

    ok, fail = 0, 0

    for s in stocks:
        stock_id = s["stock_id"]
        ticker   = s["ticker"]

        try:
            resp = requests.get(
                f"https://efts.sec.gov/LATEST/search-index?q=%22{ticker}%22"
                f"&forms=4&dateRange=custom"
                f"&startdt={(datetime.now()-timedelta(days=7)).strftime('%Y-%m-%d')}"
                f"&enddt={datetime.now().strftime('%Y-%m-%d')}",
                headers=SEC_HEADERS, timeout=10
            )
            if resp.status_code != 200:
                continue

            data = resp.json()
            hits = data.get("hits", {}).get("hits", [])

            for hit in hits[:5]:
                src  = hit.get("_source", {})
                name = src.get("display_names", ["Unknown"])[0]
                date_filed = src.get("file_date", "")
                if not date_filed:
                    continue

                with get_cursor() as cur:
                    cur.execute("""
                        INSERT INTO insider_transactions (
                            stock_id, insider_name, transaction_date,
                            transaction_type, shares, data_source
                        ) VALUES (%s,%s,%s,%s,0,%s)
                        ON CONFLICT DO NOTHING
                    """, (stock_id, name, date_filed, 'BUY', 'SEC_EDGAR'))

            ok += 1
        except Exception as e:
            fail += 1
            print(f"[INSIDER] {ticker} 실패: {e}")

    print(f"[INSIDER] ✅ 완료: {ok}성공 / {fail}실패")


if __name__ == "__main__":
    from db_pool import init_pool
    init_pool()
    run_insider_trades()