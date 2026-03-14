"""
매일 06:00 실행 (Phase 2).
Finnhub 뉴스 수집 → yfinance 애널리스트 레이팅 수집.
FinBERT 없이 간단한 키워드 기반 감성 분석 (Phase 2 초기).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import yfinance as yf
from datetime import datetime, date, timedelta
from db_pool import get_cursor

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")

POSITIVE_WORDS = {"beat", "exceed", "upgrade", "outperform", "buy", "growth",
                  "record", "strong", "raise", "bullish", "profit", "surge"}
NEGATIVE_WORDS = {"miss", "downgrade", "underperform", "sell", "decline",
                  "cut", "weak", "bearish", "loss", "fall", "disappoint"}


def _simple_sentiment(text: str) -> tuple:
    """키워드 기반 간단 감성 분석 (FinBERT 대체용 Phase 2 초기)"""
    words = text.lower().split()
    pos = sum(1 for w in words if w in POSITIVE_WORDS)
    neg = sum(1 for w in words if w in NEGATIVE_WORDS)
    if pos > neg:   return 0.6, "POSITIVE"
    if neg > pos:   return -0.6, "NEGATIVE"
    return 0.0, "NEUTRAL"


def run_news_collection():
    """Finnhub 뉴스 수집 → news_articles + news_sentiment_scores"""
    if not FINNHUB_API_KEY:
        print("[NEWS] FINNHUB_API_KEY 없음 - 스킵")
        return

    with get_cursor() as cur:
        cur.execute("SELECT stock_id, ticker FROM stocks WHERE is_active = TRUE")
        stocks = [dict(r) for r in cur.fetchall()]

    ok, fail = 0, 0
    from_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    to_date   = datetime.now().strftime("%Y-%m-%d")

    for s in stocks:
        stock_id = s["stock_id"]
        ticker   = s["ticker"]

        try:
            resp = requests.get(
                f"https://finnhub.io/api/v1/company-news",
                params={"symbol": ticker, "from": from_date, "to": to_date,
                        "token": FINNHUB_API_KEY},
                timeout=10
            )
            articles = resp.json() if resp.status_code == 200 else []

            for art in articles[:10]:  # 종목당 최대 10건
                url   = art.get("url", "")
                title = art.get("headline", "")
                if not url or not title:
                    continue

                with get_cursor() as cur:
                    cur.execute("""
                        INSERT INTO news_articles (
                            stock_id, published_at, title,
                            content_snippet, url, source_name, data_source
                        ) VALUES (%s, to_timestamp(%s), %s, %s, %s, %s, 'FINNHUB')
                        ON CONFLICT (url) DO NOTHING
                        RETURNING news_id
                    """, (stock_id, art.get("datetime"), title,
                          art.get("summary", "")[:500], url,
                          art.get("source", "")))
                    row = cur.fetchone()
                    if not row:
                        continue
                    news_id = row["news_id"]

                    score, label = _simple_sentiment(title)
                    cur.execute("""
                        INSERT INTO news_sentiment_scores (
                            news_id, stock_id, sentiment_score,
                            sentiment_label, confidence, model_version, analyzed_at
                        ) VALUES (%s,%s,%s,%s,%s,'keyword-v1',NOW())
                        ON CONFLICT (news_id) DO NOTHING
                    """, (news_id, stock_id, score, label, 0.6))

            ok += 1
        except Exception as e:
            fail += 1
            print(f"[NEWS] {ticker} 실패: {e}")

    print(f"[NEWS] 완료: {ok}성공 / {fail}실패")


def run_analyst_ratings():
    """yfinance 애널리스트 레이팅 수집 → analyst_ratings"""
    with get_cursor() as cur:
        cur.execute("SELECT stock_id, ticker FROM stocks WHERE is_active = TRUE")
        stocks = [dict(r) for r in cur.fetchall()]

    ok, fail = 0, 0

    for s in stocks:
        stock_id = s["stock_id"]
        ticker   = s["ticker"]

        try:
            tk = yf.Ticker(ticker)
            recs = tk.recommendations
            if recs is None or recs.empty:
                continue

            # 최근 90일 레이팅만
            cutoff = datetime.now() - timedelta(days=90)
            recs = recs[recs.index >= cutoff] if hasattr(recs.index, 'tz_localize') else recs.tail(20)

            upgrade_count   = 0
            downgrade_count = 0
            buy_count       = 0
            hold_count      = 0
            sell_count      = 0

            for idx, row in recs.iterrows():
                action = str(row.get("To Grade", "") or "").upper()
                if "BUY" in action or "OUTPERFORM" in action or "OVERWEIGHT" in action:
                    buy_count += 1
                    upgrade_count += 1
                elif "HOLD" in action or "NEUTRAL" in action or "EQUAL" in action:
                    hold_count += 1
                elif "SELL" in action or "UNDERPERFORM" in action or "UNDERWEIGHT" in action:
                    sell_count += 1
                    downgrade_count += 1

            total = buy_count + hold_count + sell_count
            if total == 0:
                continue

            buy_pct  = round(buy_count  / total * 100, 2)
            sell_pct = round(sell_count / total * 100, 2)

            # 애널리스트 점수 계산 (0~100)
            analyst_score = round(buy_pct * 0.7 + (upgrade_count / max(total, 1)) * 30, 2)

            with get_cursor() as cur:
                cur.execute("""
                    INSERT INTO analyst_rating_aggregates (
                        stock_id, calc_date,
                        total_analysts, buy_count, hold_count, sell_count,
                        buy_pct, sell_pct,
                        upgrade_count_90d, downgrade_count_90d,
                        net_upgrade_90d, layer2_analyst_score
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (stock_id, calc_date) DO UPDATE SET
                        total_analysts     = EXCLUDED.total_analysts,
                        buy_count          = EXCLUDED.buy_count,
                        hold_count         = EXCLUDED.hold_count,
                        sell_count         = EXCLUDED.sell_count,
                        upgrade_count_90d  = EXCLUDED.upgrade_count_90d,
                        downgrade_count_90d = EXCLUDED.downgrade_count_90d,
                        layer2_analyst_score = EXCLUDED.layer2_analyst_score
                """, (stock_id, datetime.now().date(),
                      total, buy_count, hold_count, sell_count,
                      buy_pct, sell_pct,
                      upgrade_count, downgrade_count,
                      upgrade_count - downgrade_count, analyst_score))

            ok += 1
            print(f"[ANALYST] {ticker}: Buy={buy_count} Hold={hold_count} Sell={sell_count} ✓")

        except Exception as e:
            fail += 1
            print(f"[ANALYST] {ticker} 실패: {e}")

    print(f"[ANALYST] 완료: {ok}성공 / {fail}실패")


def run_all():
    run_news_collection()
    run_analyst_ratings()


if __name__ == "__main__":
    from db_pool import init_pool
    init_pool()
    run_all()