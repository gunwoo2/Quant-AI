"""
batch_layer2.py — Layer 2: NLP 감성 + 애널리스트 + 내부자 거래
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

매일 06:00 ET 실행 (scheduler.py에서 호출)

파이프라인:
  1. Finnhub 뉴스 수집         → news_articles
  2. FinBERT 감성 분석         → news_sentiment_scores (AI 점수)
  3. 일별 감성 집계            → news_sentiment_daily
  4. yfinance 애널리스트 수집  → analyst_rating_aggregates
  5. Finnhub 내부자 거래 수집  → insider_transactions + insider_signal_aggregates
  6. Layer 2 최종 스코어링     → layer2_scores (★ Final Score가 읽는 핵심 테이블)

가중치: 뉴스 40% + 애널리스트 35% + 내부자 25%
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from l2_time_decay_patch import run_news_daily_aggregate_v2

import requests
import time
import yfinance as yf
import numpy as np
from datetime import datetime, date, timedelta
from db_pool import get_cursor

# ── API Keys ──
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")

# ── Layer 2 가중치 ──
W_NEWS     = 0.40
W_ANALYST  = 0.35
W_INSIDER  = 0.25

# ── FinBERT 모델 (Lazy Load) ──
_finbert_pipeline = None

def _get_finbert():
    """FinBERT 파이프라인 Lazy Load (최초 호출 시 1회만 로드)"""
    global _finbert_pipeline
    if _finbert_pipeline is None:
        print("[FINBERT] 모델 로딩 중... (최초 1회, ~30초)")
        try:
            from transformers import pipeline
            _finbert_pipeline = pipeline(
                "sentiment-analysis",
                model="ProsusAI/finbert",
                tokenizer="ProsusAI/finbert",
                device=-1,               # CPU 모드
                truncation=True,
                max_length=512,
            )
            print("[FINBERT] ✅ 모델 로드 완료")
        except Exception as e:
            print(f"[FINBERT] ❌ 모델 로드 실패: {e}")
            print("[FINBERT] fallback → 키워드 기반 분석 사용")
            _finbert_pipeline = "FALLBACK"
    return _finbert_pipeline


# ── 이벤트 분류 키워드 (FinBERT 보조) ──
EVENT_PATTERNS = {
    "EARNINGS":    ["earnings", "revenue beat", "revenue miss", "eps beat", "eps miss",
                    "quarterly results", "profit", "financial results"],
    "M&A":         ["acquisition", "acquire", "merger", "takeover", "buyout", "deal"],
    "GUIDANCE":    ["guidance", "outlook", "forecast", "raise guidance", "lower guidance",
                    "full-year", "expects"],
    "ANALYST":     ["upgrade", "downgrade", "price target", "rating", "initiate",
                    "overweight", "underweight"],
    "REGULATORY":  ["fda", "sec", "approval", "regulation", "compliance", "investigation",
                    "lawsuit", "antitrust"],
    "MANAGEMENT":  ["ceo", "cfo", "appoint", "resign", "executive", "board"],
    "BUYBACK":     ["buyback", "repurchase", "share repurchase"],
    "DIVIDEND":    ["dividend", "payout", "yield increase", "dividend cut"],
}

EVENT_WEIGHT = {
    "M&A": 1.3, "EARNINGS": 1.2, "GUIDANCE": 1.15, "REGULATORY": 1.2,
    "ANALYST": 1.1, "MANAGEMENT": 1.05, "BUYBACK": 1.05, "DIVIDEND": 1.0,
    "GENERAL": 1.0,
}


def _classify_event(text: str) -> str:
    """뉴스 텍스트에서 이벤트 유형 분류 (규칙 기반)"""
    text_lower = text.lower()
    for event_type, keywords in EVENT_PATTERNS.items():
        if any(kw in text_lower for kw in keywords):
            return event_type
    return "GENERAL"


def _analyze_sentiment(text: str) -> tuple:
    """
    FinBERT 감성 분석 (fallback: 키워드 기반)
    Returns: (score: float [-1~+1], label: str, confidence: float [0~1])
    """
    model = _get_finbert()

    if model == "FALLBACK" or model is None:
        return _keyword_sentiment(text)

    try:
        result = model(text[:512])[0]
        label_raw  = result["label"].lower()     # positive / negative / neutral
        confidence = round(result["score"], 4)

        if label_raw == "positive":
            score = confidence
            label = "POSITIVE"
        elif label_raw == "negative":
            score = -confidence
            label = "NEGATIVE"
        else:
            score = 0.0
            label = "NEUTRAL"

        return (round(score, 4), label, confidence)

    except Exception as e:
        print(f"[FINBERT] 추론 실패, fallback 사용: {e}")
        return _keyword_sentiment(text)


def _keyword_sentiment(text: str) -> tuple:
    """키워드 기반 감성 분석 (FinBERT 로드 실패 시 fallback)"""
    POSITIVE = {"beat","exceed","upgrade","outperform","buy","growth",
                "record","strong","raise","bullish","profit","surge",
                "soar","breakthrough","approval","innovation","accelerate"}
    NEGATIVE = {"miss","downgrade","underperform","sell","decline",
                "cut","weak","bearish","loss","fall","disappoint",
                "warning","lawsuit","investigation","recall","default"}

    words = set(text.lower().split())
    pos = len(words & POSITIVE)
    neg = len(words & NEGATIVE)

    if pos > neg:   return (0.5, "POSITIVE", 0.55)
    if neg > pos:   return (-0.5, "NEGATIVE", 0.55)
    return (0.0, "NEUTRAL", 0.50)


# ═══════════════════════════════════════════════════════════════
#  1. FINNHUB 뉴스 수집
# ═══════════════════════════════════════════════════════════════
def run_news_collection():
    """Finnhub 뉴스 수집 → news_articles"""
    if not FINNHUB_API_KEY:
        print("[NEWS] ⚠️  FINNHUB_API_KEY 없음 - 스킵")
        return

    with get_cursor() as cur:
        cur.execute("SELECT stock_id, ticker FROM stocks WHERE is_active = TRUE")
        stocks = [dict(r) for r in cur.fetchall()]

    ok, fail = 0, 0
    from_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    to_date   = datetime.now().strftime("%Y-%m-%d")

    for s in stocks:
        stock_id, ticker = s["stock_id"], s["ticker"]
        try:
            resp = requests.get(
                "https://finnhub.io/api/v1/company-news",
                params={"symbol": ticker, "from": from_date, "to": to_date,
                        "token": FINNHUB_API_KEY},
                timeout=10
            )
            if resp.status_code != 200:
                continue

            articles = resp.json()
            inserted = 0

            for art in articles[:10]:
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
                    if cur.fetchone():
                        inserted += 1

            ok += 1
            if inserted > 0:
                print(f"[NEWS] {ticker}: {inserted}건 수집")

            time.sleep(1.1)  # Finnhub rate limit: 60 calls/min

        except Exception as e:
            fail += 1
            print(f"[NEWS] {ticker} 실패: {e}")

    print(f"[NEWS] ✅ 완료: {ok}성공 / {fail}실패 (전체 {len(stocks)}종목)")


# ═══════════════════════════════════════════════════════════════
#  2. FINBERT 감성 분석 (미분석 뉴스 대상)
# ═══════════════════════════════════════════════════════════════
def run_finbert_analysis():
    """미분석 뉴스에 FinBERT 감성 분석 실행 → news_sentiment_scores"""

    # 아직 sentiment가 없는 뉴스 조회
    with get_cursor() as cur:
        cur.execute("""
            SELECT a.news_id, a.stock_id, a.title,
                   COALESCE(a.content_snippet, '') AS snippet
            FROM   news_articles a
            LEFT JOIN news_sentiment_scores s ON a.news_id = s.news_id
            WHERE  s.sentiment_id IS NULL
              AND  a.published_at >= NOW() - INTERVAL '3 days'
            ORDER BY a.published_at DESC
            LIMIT 500
        """)
        unscored = [dict(r) for r in cur.fetchall()]

    if not unscored:
        print("[FINBERT] 분석할 미분석 뉴스 없음")
        return

    print(f"[FINBERT] {len(unscored)}건 분석 시작...")
    ok, fail = 0, 0

    for art in unscored:
        try:
            # 제목 + 본문 snippet 결합 (FinBERT는 512 토큰 제한)
            text = art["title"]
            if art["snippet"]:
                text += ". " + art["snippet"][:300]

            score, label, confidence = _analyze_sentiment(text)
            event_type = _classify_event(text)

            # 이벤트 가중치 적용
            event_w = EVENT_WEIGHT.get(event_type, 1.0)
            adjusted_score = round(max(-1, min(1, score * event_w)), 4)

            with get_cursor() as cur:
                cur.execute("""
                    INSERT INTO news_sentiment_scores (
                        news_id, stock_id, sentiment_score,
                        sentiment_label, confidence, model_version, analyzed_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (news_id) DO UPDATE SET
                        sentiment_score = EXCLUDED.sentiment_score,
                        sentiment_label = EXCLUDED.sentiment_label,
                        confidence      = EXCLUDED.confidence,
                        model_version   = EXCLUDED.model_version,
                        analyzed_at     = NOW()
                """, (art["news_id"], art["stock_id"],
                      adjusted_score, label, confidence,
                      'finbert-v1+event'))

            ok += 1
        except Exception as e:
            fail += 1
            if fail <= 3:
                print(f"[FINBERT] 분석 실패 (news_id={art['news_id']}): {e}")

    print(f"[FINBERT] ✅ 완료: {ok}건 분석 / {fail}건 실패")


# ═══════════════════════════════════════════════════════════════
#  3. 일별 뉴스 감성 집계 → news_sentiment_daily
# ═══════════════════════════════════════════════════════════════
def run_news_daily_aggregate():
    """오늘 기준 종목별 뉴스 감성 집계 → news_sentiment_daily + layer2_news_score"""

    today = date.today()

    with get_cursor() as cur:
        # 최근 24시간 뉴스 감성 집계
        cur.execute("""
            SELECT
                a.stock_id,
                ROUND(AVG(s.sentiment_score), 4) AS avg_score,
                COUNT(*) FILTER (WHERE s.sentiment_label = 'POSITIVE') AS pos_cnt,
                COUNT(*) FILTER (WHERE s.sentiment_label = 'NEGATIVE') AS neg_cnt,
                COUNT(*) FILTER (WHERE s.sentiment_label = 'NEUTRAL')  AS neu_cnt,
                COUNT(*) AS total
            FROM news_articles a
            JOIN news_sentiment_scores s ON a.news_id = s.news_id
            WHERE a.published_at >= NOW() - INTERVAL '48 hours'
            GROUP BY a.stock_id
        """)
        rows = [dict(r) for r in cur.fetchall()]

    if not rows:
        print("[NEWS-AGG] 집계할 데이터 없음")
        return

    ok = 0
    for r in rows:
        # avg_sentiment (-1 ~ +1) → news_score (0 ~ 100)
        avg = float(r["avg_score"]) if r["avg_score"] else 0.0
        news_score = round((avg + 1) * 50, 2)       # -1→0, 0→50, +1→100
        news_score = max(0, min(100, news_score))

        with get_cursor() as cur:
            cur.execute("""
                INSERT INTO news_sentiment_daily (
                    stock_id, sentiment_date, avg_sentiment_score,
                    positive_count, negative_count, neutral_count,
                    total_articles, layer2_news_score
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (stock_id, sentiment_date) DO UPDATE SET
                    avg_sentiment_score = EXCLUDED.avg_sentiment_score,
                    positive_count      = EXCLUDED.positive_count,
                    negative_count      = EXCLUDED.negative_count,
                    neutral_count       = EXCLUDED.neutral_count,
                    total_articles      = EXCLUDED.total_articles,
                    layer2_news_score   = EXCLUDED.layer2_news_score
            """, (r["stock_id"], today, avg,
                  r["pos_cnt"], r["neg_cnt"], r["neu_cnt"],
                  r["total"], news_score))
        ok += 1

    print(f"[NEWS-AGG] ✅ {ok}종목 일별 집계 완료")


# ═══════════════════════════════════════════════════════════════
#  4. 애널리스트 레이팅 수집 + 스코어링
# ═══════════════════════════════════════════════════════════════
def run_analyst_ratings():
    """yfinance 애널리스트 레이팅 수집 → analyst_rating_aggregates
    
    ★ v2: recommendations_summary (집계) 우선 사용
           recommendations (개별) fallback
    """
    with get_cursor() as cur:
        cur.execute("SELECT stock_id, ticker FROM stocks WHERE is_active = TRUE")
        stocks = [dict(r) for r in cur.fetchall()]

    ok, fail = 0, 0

    for s in stocks:
        stock_id, ticker = s["stock_id"], s["ticker"]
        try:
            yf_ticker = yf.Ticker(ticker)

            # ── 방법 1: recommendations_summary (최신 yfinance) ──
            recs_summary = None
            try:
                recs_summary = yf_ticker.recommendations_summary
            except Exception:
                pass

            if recs_summary is not None and not recs_summary.empty:
                latest = recs_summary.iloc[0]
                strong_buy = int(latest.get("strongBuy", 0))
                buy_count  = int(latest.get("buy", 0)) + strong_buy
                hold_count = int(latest.get("hold", 0))
                sell_count = int(latest.get("sell", 0)) + int(latest.get("strongSell", 0))

                total = buy_count + hold_count + sell_count
                if total > 0:
                    buy_pct  = round(buy_count / total * 100, 2)
                    sell_pct = round(sell_count / total * 100, 2)

                    buy_score = buy_pct
                    upgrade_momentum = 50  # summary에는 upgrade/downgrade 없으므로 중립
                    coverage_bonus = min(total / 20, 1.0) * 100

                    analyst_score = round(
                        buy_score * 0.40 +
                        upgrade_momentum * 0.30 +
                        coverage_bonus * 0.30,
                        2
                    )
                    analyst_score = max(0, min(100, analyst_score))

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
                                total_analysts       = EXCLUDED.total_analysts,
                                buy_count            = EXCLUDED.buy_count,
                                hold_count           = EXCLUDED.hold_count,
                                sell_count           = EXCLUDED.sell_count,
                                buy_pct              = EXCLUDED.buy_pct,
                                sell_pct             = EXCLUDED.sell_pct,
                                upgrade_count_90d    = EXCLUDED.upgrade_count_90d,
                                downgrade_count_90d  = EXCLUDED.downgrade_count_90d,
                                net_upgrade_90d      = EXCLUDED.net_upgrade_90d,
                                layer2_analyst_score = EXCLUDED.layer2_analyst_score
                        """, (stock_id, date.today(),
                              total, buy_count, hold_count, sell_count,
                              buy_pct, sell_pct,
                              0, 0, 0, analyst_score))
                    ok += 1
                    continue

            # ── 방법 2: recommendations (개별 레이팅) fallback ──
            recs = None
            try:
                recs = yf_ticker.recommendations
            except Exception:
                pass

            if recs is None or recs.empty:
                continue

            buy_count, hold_count, sell_count = 0, 0, 0
            upgrade_count, downgrade_count = 0, 0

            for _, row in recs.iterrows():
                grade = str(
                    row.get("toGrade",
                    row.get("To Grade",
                    row.get("to_grade", "")))
                ).upper()
                action = str(
                    row.get("action",
                    row.get("Action", ""))
                ).upper()

                if any(g in grade for g in ["BUY", "OUTPERFORM", "OVERWEIGHT", "STRONG BUY"]):
                    buy_count += 1
                elif any(g in grade for g in ["HOLD", "NEUTRAL", "MARKET PERFORM", "EQUAL", "PEER PERFORM"]):
                    hold_count += 1
                elif any(g in grade for g in ["SELL", "UNDERPERFORM", "UNDERWEIGHT"]):
                    sell_count += 1

                if "UP" in action:
                    upgrade_count += 1
                elif "DOWN" in action:
                    downgrade_count += 1

            total = buy_count + hold_count + sell_count
            if total == 0:
                continue

            buy_pct  = round(buy_count / total * 100, 2)
            sell_pct = round(sell_count / total * 100, 2)

            net_upgrade = upgrade_count - downgrade_count
            buy_score = buy_pct
            upgrade_momentum = 50 + (net_upgrade / max(total, 1)) * 100
            upgrade_momentum = max(0, min(100, upgrade_momentum))
            coverage_bonus = min(total / 20, 1.0) * 100

            analyst_score = round(
                buy_score * 0.40 +
                upgrade_momentum * 0.30 +
                coverage_bonus * 0.30,
                2
            )
            analyst_score = max(0, min(100, analyst_score))

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
                        total_analysts       = EXCLUDED.total_analysts,
                        buy_count            = EXCLUDED.buy_count,
                        hold_count           = EXCLUDED.hold_count,
                        sell_count           = EXCLUDED.sell_count,
                        buy_pct              = EXCLUDED.buy_pct,
                        sell_pct             = EXCLUDED.sell_pct,
                        upgrade_count_90d    = EXCLUDED.upgrade_count_90d,
                        downgrade_count_90d  = EXCLUDED.downgrade_count_90d,
                        net_upgrade_90d      = EXCLUDED.net_upgrade_90d,
                        layer2_analyst_score = EXCLUDED.layer2_analyst_score
                """, (stock_id, date.today(),
                      total, buy_count, hold_count, sell_count,
                      buy_pct, sell_pct,
                      upgrade_count, downgrade_count,
                      net_upgrade, analyst_score))
            ok += 1

        except Exception as e:
            fail += 1
            if fail <= 5:
                print(f"[ANALYST] {ticker} 실패: {e}")

    print(f"[ANALYST] ✅ 완료: {ok}성공 / {fail}실패")


# ═══════════════════════════════════════════════════════════════
#  5. 내부자 거래 수집 + 스코어링 (Finnhub)
# ═══════════════════════════════════════════════════════════════
C_LEVEL_TITLES = {"ceo", "cfo", "coo", "cto", "president", "chief"}

def _is_c_level(title: str) -> bool:
    return any(t in title.lower() for t in C_LEVEL_TITLES) if title else False


def run_insider_collection():
    """Finnhub 내부자 거래 수집 → insider_transactions + insider_signal_aggregates"""
    if not FINNHUB_API_KEY:
        print("[INSIDER] ⚠️  FINNHUB_API_KEY 없음 - 스킵")
        return

    with get_cursor() as cur:
        cur.execute("SELECT stock_id, ticker FROM stocks WHERE is_active = TRUE")
        stocks = [dict(r) for r in cur.fetchall()]

    ok, fail = 0, 0

    for s in stocks:
        stock_id, ticker = s["stock_id"], s["ticker"]
        try:
            resp = requests.get(
                "https://finnhub.io/api/v1/stock/insider-transactions",
                params={"symbol": ticker, "token": FINNHUB_API_KEY},
                timeout=10
            )
            if resp.status_code != 200:
                continue

            data = resp.json().get("data", [])
            cutoff = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")

            # 90일 내 거래만 필터
            recent = [t for t in data if (t.get("transactionDate") or "") >= cutoff]

            c_level_buy_value = 0.0
            insider_buy_count = 0
            insider_sell_count = 0
            c_level_buying = 0
            large_sell_alert = False

            for txn in recent[:30]:
                name   = txn.get("name", "Unknown")
                change = txn.get("change", 0)             # + = buy, - = sell
                value  = abs(txn.get("transactionPrice", 0) * change) if txn.get("transactionPrice") else 0
                txn_date = txn.get("transactionDate", "")
                is_c = _is_c_level(name)

                if change > 0:
                    insider_buy_count += 1
                    if is_c:
                        c_level_buy_value += value
                        c_level_buying += 1
                elif change < 0:
                    insider_sell_count += 1
                    # CEO 대규모 매도 체크 (설계서: 지분 20%+ 매도 → 경보)
                    ownership_pct = txn.get("share", 0)
                    if is_c and "ceo" in name.lower() and ownership_pct and ownership_pct > 20:
                        large_sell_alert = True

                # INSERT individual transaction
                txn_type = "BUY" if change > 0 else "SELL"
                with get_cursor() as cur:
                    cur.execute("""
                        INSERT INTO insider_transactions (
                            stock_id, insider_name, insider_title,
                            is_c_level, transaction_date, transaction_type,
                            shares_transacted, price_per_share, total_value,
                            filing_date
                        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT DO NOTHING
                    """, (stock_id, name, "",
                          is_c, txn_date, txn_type,
                          abs(change), txn.get("transactionPrice"),
                          round(value, 2),
                          txn.get("filingDate")))

            # ── 내부자 스코어링 (0~100) ──
            insider_score = 50.0     # 기본 중립

            # C-레벨 매수 보너스
            insider_score += c_level_buying * 15              # CEO/CFO 매수 1건 = +15

            # 임원 3명+ 동시 매수 (30일) → 집단 매수 보너스
            if insider_buy_count >= 3:
                insider_score += 20

            # 일반 매도 페널티
            insider_score -= insider_sell_count * 3

            # CEO 대규모 매도 → 강력 페널티
            if large_sell_alert:
                insider_score -= 40

            insider_score = max(0, min(100, round(insider_score, 2)))

            # 시그널 판별
            if insider_score >= 70:
                signal = "BULLISH"
            elif insider_score <= 30:
                signal = "BEARISH"
            else:
                signal = "NEUTRAL"

            # INSERT aggregate
            with get_cursor() as cur:
                cur.execute("""
                    INSERT INTO insider_signal_aggregates (
                        stock_id, calc_date,
                        c_level_net_buy_30d, insider_count_buying_30d,
                        large_sell_alert, net_insider_signal,
                        layer2_insider_score
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (stock_id, calc_date) DO UPDATE SET
                        c_level_net_buy_30d    = EXCLUDED.c_level_net_buy_30d,
                        insider_count_buying_30d = EXCLUDED.insider_count_buying_30d,
                        large_sell_alert        = EXCLUDED.large_sell_alert,
                        net_insider_signal      = EXCLUDED.net_insider_signal,
                        layer2_insider_score    = EXCLUDED.layer2_insider_score
                """, (stock_id, date.today(),
                      round(c_level_buy_value, 2), insider_buy_count,
                      large_sell_alert, signal, insider_score))

            ok += 1
            time.sleep(1.1)  # Finnhub rate limit: 60 calls/min

        except Exception as e:
            fail += 1
            if fail <= 5:
                print(f"[INSIDER] {ticker} 실패: {e}")

    print(f"[INSIDER] ✅ 완료: {ok}성공 / {fail}실패")


# ═══════════════════════════════════════════════════════════════
#  6. ★★★ LAYER 2 최종 스코어링 → layer2_scores
# ═══════════════════════════════════════════════════════════════
def run_layer2_scoring():
    """
    3개 서브 점수 통합 → layer2_scores INSERT
    
    layer2_total = news × 40% + analyst × 35% + insider × 25%
    
    ★ batch_final_score.py가 이 테이블을 읽어서 Final Score를 계산함
    """
    today = date.today()

    with get_cursor() as cur:
        cur.execute("SELECT stock_id, ticker FROM stocks WHERE is_active = TRUE")
        stocks = [dict(r) for r in cur.fetchall()]

    ok, skip = 0, 0

    for s in stocks:
        stock_id, ticker = s["stock_id"], s["ticker"]

        # ── 서브 점수 조회 ──
        news_score    = None
        analyst_score = None
        insider_score = None

        with get_cursor() as cur:
            # 뉴스 감성 점수 (최근 3일 내)
            cur.execute("""
                SELECT layer2_news_score FROM news_sentiment_daily
                WHERE stock_id = %s AND sentiment_date >= %s - INTERVAL '3 days'
                ORDER BY sentiment_date DESC LIMIT 1
            """, (stock_id, today))
            row = cur.fetchone()
            if row:
                news_score = float(row["layer2_news_score"]) if row["layer2_news_score"] else None

            # 애널리스트 점수 (최근 7일 내)
            cur.execute("""
                SELECT layer2_analyst_score FROM analyst_rating_aggregates
                WHERE stock_id = %s AND calc_date >= %s - INTERVAL '7 days'
                ORDER BY calc_date DESC LIMIT 1
            """, (stock_id, today))
            row = cur.fetchone()
            if row:
                analyst_score = float(row["layer2_analyst_score"]) if row["layer2_analyst_score"] else None

            # 내부자 거래 점수 (최근 7일 내)
            cur.execute("""
                SELECT layer2_insider_score FROM insider_signal_aggregates
                WHERE stock_id = %s AND calc_date >= %s - INTERVAL '7 days'
                ORDER BY calc_date DESC LIMIT 1
            """, (stock_id, today))
            row = cur.fetchone()
            if row:
                insider_score = float(row["layer2_insider_score"]) if row["layer2_insider_score"] else None

        # ── 최종 통합 점수 계산 ──
        # 데이터 없는 서브는 50(중립)으로 대체
        ns = news_score    if news_score    is not None else 50.0
        as_ = analyst_score if analyst_score is not None else 50.0
        is_ = insider_score if insider_score is not None else 50.0

        layer2_total = round(ns * W_NEWS + as_ * W_ANALYST + is_ * W_INSIDER, 2)
        layer2_total = max(0, min(100, layer2_total))

        with get_cursor() as cur:
            cur.execute("""
                INSERT INTO layer2_scores (
                    stock_id, calc_date,
                    news_sentiment_score, earnings_call_score,
                    analyst_rating_score, insider_signal_score,
                    layer2_total_score
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (stock_id, calc_date) DO UPDATE SET
                    news_sentiment_score = EXCLUDED.news_sentiment_score,
                    earnings_call_score  = EXCLUDED.earnings_call_score,
                    analyst_rating_score = EXCLUDED.analyst_rating_score,
                    insider_signal_score = EXCLUDED.insider_signal_score,
                    layer2_total_score   = EXCLUDED.layer2_total_score
            """, (stock_id, today,
                  ns,    # news_sentiment_score
                  None,  # earnings_call_score (Phase 3)
                  as_,   # analyst_rating_score
                  is_,   # insider_signal_score
                  layer2_total))

        ok += 1

    print(f"[L2-SCORE] ✅ {ok}종목 Layer 2 점수 산출 완료")
    print(f"[L2-SCORE] 가중치: News({W_NEWS:.0%}) + Analyst({W_ANALYST:.0%}) + Insider({W_INSIDER:.0%})")


# ═══════════════════════════════════════════════════════════════
#  전체 파이프라인 실행
# ═══════════════════════════════════════════════════════════════
def run_all():
    """Layer 2 전체 파이프라인 (scheduler에서 호출)"""
    print("=" * 60)
    print(f"[LAYER2] 파이프라인 시작: {datetime.now()}")
    print("=" * 60)

    # Step 1: 뉴스 수집
    print("\n── Step 1/6: 뉴스 수집 (Finnhub) ──")
    run_news_collection()

    # Step 2: FinBERT 감성 분석
    print("\n── Step 2/6: FinBERT 감성 분석 ──")
    run_finbert_analysis()

    # Step 3: 일별 감성 집계
    print("\n── Step 3/6: 일별 뉴스 감성 집계 ──")
    run_news_daily_aggregate_v2()

    # Step 4: 애널리스트 레이팅
    print("\n── Step 4/6: 애널리스트 레이팅 수집 ──")
    run_analyst_ratings()

    # Step 5: 내부자 거래
    print("\n── Step 5/6: 내부자 거래 수집 ──")
    run_insider_collection()

    # Step 6: Layer 2 최종 스코어링
    print("\n── Step 6/6: Layer 2 최종 스코어링 ──")
    run_layer2_scoring()

    print("\n" + "=" * 60)
    print(f"[LAYER2] ✅ 파이프라인 완료: {datetime.now()}")
    print("=" * 60)


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    from db_pool import init_pool
    init_pool()
    run_all()