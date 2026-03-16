"""
batch_layer2_v2.py — Layer 2: NLP 감성 + 애널리스트 + 내부자 거래
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

매일 06:00 ET 실행 (scheduler.py에서 호출)

파이프라인:
  1. Finnhub 뉴스 수집         → news_articles
  2. FinBERT 감성 분석         → news_sentiment_scores (AI 점수)
  3. 일별 감성 집계            → news_sentiment_daily
  4. yfinance 애널리스트 수집  → analyst_rating_aggregates
  5. Finnhub 내부자 거래 수집  → insider_transactions + insider_signal_aggregates
  6. Layer 2 최종 스코어링     → layer2_scores (★ Final Score가 읽는 핵심 테이블)

v3.1 변경사항:
  - 스코어링 로직을 utils.layer2_scoring 으로 분리
  - Sigmoid 기반 정규화 (계단식 제거)
  - 뉴스: 신뢰도 가중 + 최근성 + 볼륨
  - 애널리스트: Sigmoid + 컨센서스 모멘텀 + 가격목표
  - 내부자: 금액 비중 + Sigmoid 정규화
  - 최종 통합: 동적 가중치 재분배 (결측 → 50 대체 제거)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import yfinance as yf
import numpy as np
from datetime import datetime, date, timedelta
from db_pool import get_cursor

# ── v3.1: Layer 2 스코어링 엔진 ──
from utils.layer2_scoring import (
    calc_news_sentiment_score,
    calc_analyst_rating_score,
    calc_insider_trading_score,
    calc_layer2_total_score,
)

# ── API Keys ──
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")

# ── FinBERT 모델 (Lazy Load) ──
_finbert_pipeline = None


def _get_finbert():
    """FinBERT 모델 로드 (최초 1회)"""
    global _finbert_pipeline
    if _finbert_pipeline is None:
        try:
            from transformers import pipeline as hf_pipeline
            print("[FinBERT] 모델 로딩 중...")
            _finbert_pipeline = hf_pipeline(
                "text-classification",
                model="ProsusAI/finbert",
                tokenizer="ProsusAI/finbert",
                return_all_scores=True,
                truncation=True,
                max_length=512,
            )
            print("[FinBERT] ✅ 로드 완료")
        except Exception as e:
            print(f"[FinBERT] ⚠️  로드 실패: {e} → 키워드 폴백 사용")
            _finbert_pipeline = "FALLBACK"
    return _finbert_pipeline


# ═══════════════════════════════════════════════════════════════
#  이벤트 분류 + 감성 분석 (변경 없음)
# ═══════════════════════════════════════════════════════════════

EVENT_KEYWORDS = {
    "earnings":    ["earnings", "revenue", "profit", "EPS", "quarterly results"],
    "dividend":    ["dividend", "payout", "yield"],
    "fda":         ["FDA", "approval", "clinical trial", "phase"],
    "merger":      ["merger", "acquisition", "M&A", "takeover", "buyout"],
    "legal":       ["lawsuit", "SEC", "investigation", "settlement", "fraud"],
    "management":  ["CEO", "CFO", "appointed", "resigned", "board"],
}


def _classify_event(text: str) -> str:
    """뉴스 텍스트에서 이벤트 유형 분류"""
    text_lower = text.lower()
    for event_type, keywords in EVENT_KEYWORDS.items():
        if any(kw.lower() in text_lower for kw in keywords):
            return event_type
    return "general"


def _analyze_sentiment(text: str) -> tuple:
    """
    FinBERT 감성 분석 → (score, label, confidence)
    score: -1 ~ +1
    """
    model = _get_finbert()

    if model == "FALLBACK" or model is None:
        return _keyword_sentiment(text)

    try:
        results = model(text[:512])
        if results and isinstance(results[0], list):
            scores_dict = {r["label"]: r["score"] for r in results[0]}
        else:
            scores_dict = {r["label"]: r["score"] for r in results}

        pos = scores_dict.get("positive", 0)
        neg = scores_dict.get("negative", 0)
        neu = scores_dict.get("neutral", 0)

        score = pos - neg  # -1 ~ +1
        confidence = max(pos, neg, neu)

        if pos > neg and pos > neu:
            label = "POSITIVE"
        elif neg > pos and neg > neu:
            label = "NEGATIVE"
        else:
            label = "NEUTRAL"

        return round(score, 4), label, round(confidence, 4)

    except Exception as e:
        print(f"[FinBERT] 추론 실패: {e}")
        return _keyword_sentiment(text)


def _keyword_sentiment(text: str) -> tuple:
    """키워드 기반 폴백 감성 분석"""
    text_lower = text.lower()
    pos_words = ["surge", "jump", "beat", "upgrade", "growth", "strong", "record",
                 "profit", "bullish", "outperform", "rally"]
    neg_words = ["drop", "fall", "miss", "downgrade", "loss", "weak", "decline",
                 "bearish", "underperform", "crash", "layoff", "fraud"]

    pos_count = sum(1 for w in pos_words if w in text_lower)
    neg_count = sum(1 for w in neg_words if w in text_lower)

    total = pos_count + neg_count
    if total == 0:
        return 0.0, "NEUTRAL", 0.3

    score = (pos_count - neg_count) / total
    label = "POSITIVE" if score > 0.1 else ("NEGATIVE" if score < -0.1 else "NEUTRAL")
    confidence = min(total / 5, 1.0) * 0.6  # 키워드 방식은 신뢰도 낮음

    return round(score, 4), label, round(confidence, 4)


# ═══════════════════════════════════════════════════════════════
#  1. 뉴스 수집 (Finnhub) — 변경 없음
# ═══════════════════════════════════════════════════════════════

def run_news_collection():
    """Finnhub에서 종목별 최신 뉴스 수집 → news_articles"""
    if not FINNHUB_API_KEY:
        print("[NEWS] ⚠️  FINNHUB_API_KEY 없음 - 스킵")
        return

    with get_cursor() as cur:
        cur.execute("SELECT stock_id, ticker FROM stocks WHERE is_active = TRUE")
        stocks = [dict(r) for r in cur.fetchall()]

    from_date = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
    to_date = datetime.now().strftime("%Y-%m-%d")

    ok, skip, fail = 0, 0, 0

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
                fail += 1
                continue

            articles = resp.json()
            if not articles:
                skip += 1
                continue

            for art in articles[:10]:  # 종목당 최대 10건
                title = art.get("headline", "")
                url = art.get("url", "")
                if not title or not url:
                    continue

                published = datetime.fromtimestamp(art.get("datetime", 0))
                source = art.get("source", "")
                snippet = art.get("summary", "")[:500]

                with get_cursor() as cur:
                    cur.execute("""
                        INSERT INTO news_articles (
                            stock_id, published_at, title, content_snippet,
                            url, source_name, data_source
                        ) VALUES (%s, %s, %s, %s, %s, %s, 'FINNHUB')
                        ON CONFLICT (url) DO NOTHING
                    """, (stock_id, published, title, snippet, url, source))

            ok += 1
        except Exception as e:
            fail += 1
            if fail <= 5:
                print(f"[NEWS] {ticker} 실패: {e}")

    print(f"[NEWS] ✅ 완료: {ok}성공 / {skip}스킵 / {fail}실패")


# ═══════════════════════════════════════════════════════════════
#  2. FinBERT 감성 분석 — 변경 없음
# ═══════════════════════════════════════════════════════════════

def run_finbert_analysis():
    """미분석 뉴스에 FinBERT 감성 분석 수행 → news_sentiment_scores"""
    with get_cursor() as cur:
        cur.execute("""
            SELECT a.news_id, a.stock_id, a.title, a.content_snippet
            FROM news_articles a
            LEFT JOIN news_sentiment_scores s ON a.news_id = s.news_id
            WHERE s.sentiment_id IS NULL
              AND a.published_at >= NOW() - INTERVAL '48 hours'
            ORDER BY a.published_at DESC
            LIMIT 500
        """)
        pending = [dict(r) for r in cur.fetchall()]

    if not pending:
        print("[FINBERT] 분석 대기 뉴스 없음")
        return

    print(f"[FINBERT] 분석 대기: {len(pending)}건")
    ok, fail = 0, 0

    for art in pending:
        try:
            text = art["title"]
            if art.get("content_snippet"):
                text += ". " + art["content_snippet"][:300]

            score, label, confidence = _analyze_sentiment(text)
            event_type = _classify_event(text)

            model_ver = "finbert-v1+event"
            if _finbert_pipeline == "FALLBACK":
                model_ver = "keyword-fallback"

            with get_cursor() as cur:
                cur.execute("""
                    INSERT INTO news_sentiment_scores (
                        news_id, stock_id, sentiment_score, sentiment_label,
                        confidence, model_version, analyzed_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (news_id) DO NOTHING
                """, (art["news_id"], art["stock_id"],
                      score, label, confidence, model_ver))

            ok += 1
        except Exception as e:
            fail += 1
            if fail <= 5:
                print(f"[FINBERT] news_id={art['news_id']} 실패: {e}")

    print(f"[FINBERT] ✅ 완료: {ok}건 분석 / {fail}건 실패")


# ═══════════════════════════════════════════════════════════════
#  3. 일별 뉴스 감성 집계 — v3.1 스코어링 적용 ★
# ═══════════════════════════════════════════════════════════════

def run_news_daily_aggregate():
    """오늘 기준 종목별 뉴스 감성 집계 → news_sentiment_daily + layer2_news_score"""

    today = date.today()

    with get_cursor() as cur:
        # v3.1: confidence, 24h 비율도 함께 조회
        cur.execute("""
            SELECT
                a.stock_id,
                ROUND(AVG(s.sentiment_score), 4) AS avg_score,
                ROUND(AVG(s.confidence), 4) AS avg_confidence,
                COUNT(*) FILTER (WHERE s.sentiment_label = 'POSITIVE') AS pos_cnt,
                COUNT(*) FILTER (WHERE s.sentiment_label = 'NEGATIVE') AS neg_cnt,
                COUNT(*) FILTER (WHERE s.sentiment_label = 'NEUTRAL')  AS neu_cnt,
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE a.published_at >= NOW() - INTERVAL '24 hours') AS recent_24h
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
        total = int(r["total"]) if r["total"] else 0
        recent_24h = int(r["recent_24h"]) if r["recent_24h"] else 0

        # ★ v3.1: layer2_scoring 엔진 사용
        result = calc_news_sentiment_score(
            avg_sentiment=float(r["avg_score"]) if r["avg_score"] else 0.0,
            total_articles=total,
            positive_count=int(r["pos_cnt"]) if r["pos_cnt"] else 0,
            negative_count=int(r["neg_cnt"]) if r["neg_cnt"] else 0,
            neutral_count=int(r["neu_cnt"]) if r["neu_cnt"] else 0,
            avg_confidence=float(r["avg_confidence"]) if r["avg_confidence"] else 0.5,
            recent_24h_ratio=recent_24h / total if total > 0 else 0.5,
        )
        news_score = result["news_score"]

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
            """, (r["stock_id"], today,
                  float(r["avg_score"]) if r["avg_score"] else 0.0,
                  r["pos_cnt"], r["neg_cnt"], r["neu_cnt"],
                  total, news_score))
        ok += 1

    print(f"[NEWS-AGG] ✅ {ok}종목 일별 집계 완료")


# ═══════════════════════════════════════════════════════════════
#  4. 애널리스트 레이팅 수집 + 스코어링 — v3.1 ★
# ═══════════════════════════════════════════════════════════════

def run_analyst_ratings():
    """yfinance 애널리스트 레이팅 수집 → analyst_rating_aggregates"""

    with get_cursor() as cur:
        cur.execute("SELECT stock_id, ticker FROM stocks WHERE is_active = TRUE")
        stocks = [dict(r) for r in cur.fetchall()]

    ok, fail = 0, 0

    for s in stocks:
        stock_id, ticker = s["stock_id"], s["ticker"]
        try:
            yf_ticker = yf.Ticker(ticker)
            recs = yf_ticker.recommendations
            if recs is None or recs.empty:
                continue

            # 90일 내 레이팅만
            cutoff = datetime.now() - timedelta(days=90)
            buy_count, hold_count, sell_count = 0, 0, 0
            upgrade_count, downgrade_count = 0, 0

            for _, row in recs.iterrows():
                grade = str(row.get("toGrade", row.get("To Grade", ""))).upper()
                action = str(row.get("action", row.get("Action", ""))).upper()

                if any(g in grade for g in ["BUY", "OUTPERFORM", "OVERWEIGHT", "STRONG BUY"]):
                    buy_count += 1
                elif any(g in grade for g in ["HOLD", "NEUTRAL", "MARKET PERFORM", "EQUAL"]):
                    hold_count += 1
                elif any(g in grade for g in ["SELL", "UNDERPERFORM", "UNDERWEIGHT"]):
                    sell_count += 1

                if "UPGRADE" in action or "UP" in action:
                    upgrade_count += 1
                elif "DOWNGRADE" in action or "DOWN" in action:
                    downgrade_count += 1

            total = buy_count + hold_count + sell_count
            if total == 0:
                continue

            buy_pct  = round(buy_count / total * 100, 2)
            sell_pct = round(sell_count / total * 100, 2)
            net_upgrade = upgrade_count - downgrade_count

            # ★ v3.1: layer2_scoring 엔진 사용
            # 가격목표 조회 (가용하면)
            target_price = None
            current_price = None
            try:
                info = yf_ticker.info
                target_price = info.get("targetMeanPrice")
                current_price = info.get("currentPrice") or info.get("regularMarketPrice")
            except Exception:
                pass

            result = calc_analyst_rating_score(
                buy_count=buy_count,
                hold_count=hold_count,
                sell_count=sell_count,
                upgrade_count_90d=upgrade_count,
                downgrade_count_90d=downgrade_count,
                target_price=target_price,
                current_price=current_price,
            )
            analyst_score = result["analyst_score"]

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
#  5. 내부자 거래 수집 + 스코어링 (Finnhub) — v3.1 ★
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
            c_level_sell_value = 0.0
            c_level_buying = 0
            c_level_selling = 0
            insider_buy_count = 0
            insider_sell_count = 0
            total_buy_value = 0.0
            total_sell_value = 0.0
            large_sell_alert = False
            last_buy_date = None
            last_sell_date = None

            for txn in recent[:30]:
                name   = txn.get("name", "Unknown")
                change = txn.get("change", 0)
                price  = txn.get("transactionPrice", 0) or 0
                value  = abs(price * change) if price else 0
                txn_date = txn.get("transactionDate", "")
                is_c = _is_c_level(name)

                if change > 0:
                    insider_buy_count += 1
                    total_buy_value += value
                    if is_c:
                        c_level_buy_value += value
                        c_level_buying += 1
                    if not last_buy_date or txn_date > last_buy_date:
                        last_buy_date = txn_date
                elif change < 0:
                    insider_sell_count += 1
                    total_sell_value += value
                    if is_c:
                        c_level_sell_value += value
                        c_level_selling += 1
                    if not last_sell_date or txn_date > last_sell_date:
                        last_sell_date = txn_date
                    # CEO 대규모 매도 체크
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
                          abs(change), price if price else None,
                          round(value, 2),
                          txn.get("filingDate")))

            # ★ v3.1: layer2_scoring 엔진 사용
            # 최근 매수/매도 일수 계산
            days_buy = None
            days_sell = None
            if last_buy_date:
                try:
                    days_buy = (date.today() - datetime.strptime(last_buy_date, "%Y-%m-%d").date()).days
                except Exception:
                    pass
            if last_sell_date:
                try:
                    days_sell = (date.today() - datetime.strptime(last_sell_date, "%Y-%m-%d").date()).days
                except Exception:
                    pass

            result = calc_insider_trading_score(
                c_level_buy_count=c_level_buying,
                c_level_sell_count=c_level_selling,
                c_level_buy_value=c_level_buy_value,
                c_level_sell_value=c_level_sell_value,
                insider_buy_count=insider_buy_count,
                insider_sell_count=insider_sell_count,
                total_buy_value=total_buy_value,
                total_sell_value=total_sell_value,
                large_sell_alert=large_sell_alert,
                market_cap=None,  # yfinance에서 별도 조회 가능
                days_since_last_buy=days_buy,
                days_since_last_sell=days_sell,
            )
            insider_score = result["insider_score"]

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
        except Exception as e:
            fail += 1
            if fail <= 5:
                print(f"[INSIDER] {ticker} 실패: {e}")

    print(f"[INSIDER] ✅ 완료: {ok}성공 / {fail}실패")


# ═══════════════════════════════════════════════════════════════
#  6. ★★★ LAYER 2 최종 스코어링 → layer2_scores — v3.1 ★
# ═══════════════════════════════════════════════════════════════

def run_layer2_scoring():
    """
    3개 서브 점수 통합 → layer2_scores INSERT

    v3.1: 동적 가중치 재분배 (결측 → 50 대체 제거)
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
        news_available    = False
        analyst_available = False
        insider_available = False

        with get_cursor() as cur:
            # 뉴스 감성 점수 (최근 3일 내)
            cur.execute("""
                SELECT layer2_news_score FROM news_sentiment_daily
                WHERE stock_id = %s AND sentiment_date >= %s - INTERVAL '3 days'
                ORDER BY sentiment_date DESC LIMIT 1
            """, (stock_id, today))
            row = cur.fetchone()
            if row and row["layer2_news_score"] is not None:
                news_score = float(row["layer2_news_score"])
                news_available = True

            # 애널리스트 점수 (최근 7일 내)
            cur.execute("""
                SELECT layer2_analyst_score FROM analyst_rating_aggregates
                WHERE stock_id = %s AND calc_date >= %s - INTERVAL '7 days'
                ORDER BY calc_date DESC LIMIT 1
            """, (stock_id, today))
            row = cur.fetchone()
            if row and row["layer2_analyst_score"] is not None:
                analyst_score = float(row["layer2_analyst_score"])
                analyst_available = True

            # 내부자 거래 점수 (최근 7일 내)
            cur.execute("""
                SELECT layer2_insider_score FROM insider_signal_aggregates
                WHERE stock_id = %s AND calc_date >= %s - INTERVAL '7 days'
                ORDER BY calc_date DESC LIMIT 1
            """, (stock_id, today))
            row = cur.fetchone()
            if row and row["layer2_insider_score"] is not None:
                insider_score = float(row["layer2_insider_score"])
                insider_available = True

        # ★ v3.1: 동적 가중 통합 점수 계산
        result = calc_layer2_total_score(
            news_score=news_score,
            analyst_score=analyst_score,
            insider_score=insider_score,
            news_data_available=news_available,
            analyst_data_available=analyst_available,
            insider_data_available=insider_available,
        )
        layer2_total = result["layer2_total_score"]
        data_quality = result["layer2_data_quality"]

        # DB INSERT 시 서브점수가 None이면 None 유지 (v3.0 처럼 50 대체 X)
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
                  news_score,     # None이면 NULL
                  None,           # earnings_call_score (Phase 3)
                  analyst_score,  # None이면 NULL
                  insider_score,  # None이면 NULL
                  layer2_total))

        ok += 1

    print(f"[L2-SCORE] ✅ {ok}종목 Layer 2 점수 산출 완료")
    print(f"[L2-SCORE] v3.1 동적 가중 적용 (데이터 가용성 기반)")


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
    run_news_daily_aggregate()

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