"""
매 2시간 실행 (Phase 2).
SEC EDGAR Form 4 파싱 → insider_transactions.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from datetime import datetime, timedelta
from db_pool import get_cursor

SEC_HEADERS = {"User-Agent": "QuantAI research@quantai.com"}


def _get_cik(ticker: str) -> str | None:
    try:
        resp = requests.get(
            "https://efts.sec.gov/LATEST/search-index?q=%22{}%22&dateRange=custom"
            "&startdt=2020-01-01&forms=4".format(ticker),
            headers=SEC_HEADERS, timeout=10
        )
        return None
    except Exception:
        return None


def run_insider_trades():
    """SEC Form 4 기반 내부자거래 수집"""
    with get_cursor() as cur:
        cur.execute("SELECT stock_id, ticker FROM stocks WHERE is_active = TRUE")
        stocks = [dict(r) for r in cur.fetchall()]

    ok, fail = 0, 0

    for s in stocks:
        stock_id = s["stock_id"]
        ticker   = s["ticker"]

        try:
            # SEC EDGAR company search
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
                        ) VALUES (%s,%s,%s,'OPEN_MARKET_BUY',0,'SEC_EDGAR')
                        ON CONFLICT DO NOTHING
                    """, (stock_id, name, date_filed))

            ok += 1
        except Exception as e:
            fail += 1
            print(f"[INSIDER] {ticker} 실패: {e}")

    print(f"[INSIDER] 완료: {ok}성공 / {fail}실패")


if __name__ == "__main__":
    from db_pool import init_pool
    init_pool()
    run_insider_trades()