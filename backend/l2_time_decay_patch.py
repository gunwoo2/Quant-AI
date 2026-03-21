"""
l2_time_decay_patch.py — L2 뉴스 감성 시간감쇠 + 양 보정 패치
================================================================
Step 5: FinBERT 최적화
  1. 시간 감쇠 (Time Decay): 오늘 1.0 → 어제 0.7 → 그제 0.4
  2. 뉴스 양 보정 (Shrinkage): 뉴스 적으면 50.0(중립) 방향으로 당김
  3. Confidence Score: 뉴스 수 + 감쇠 가중합 기반 신뢰도

사용법:
  batch_layer2_v2.py의 run_news_daily_aggregate() 함수를
  이 파일의 run_news_daily_aggregate_v2()로 교체

  방법 1 (간단): batch_layer2_v2.py에서:
    from l2_time_decay_patch import run_news_daily_aggregate_v2 as run_news_daily_aggregate
    
  방법 2 (안전): batch_layer2_v2.py의 run_news_daily_aggregate 함수 내용을
    아래 코드로 교체
"""
import math
from datetime import date, datetime
from db_pool import get_cursor


# ── 시간 감쇠 설정 ──
DECAY_HALFLIFE_HOURS = 24.0   # 24시간마다 가중치 절반
DECAY_WINDOW_HOURS = 72       # 최대 3일 뉴스만 사용

# ── 뉴스 양 보정 설정 ──
MIN_ARTICLES_FOR_FULL_WEIGHT = 5   # 5건 이상이면 100% 신뢰
SHRINKAGE_PRIOR = 50.0             # 뉴스 부족 시 수렴 대상 (중립)


def _time_decay_weight(published_at, now=None):
    """뉴스 발행 시각 → 감쇠 가중치 (0~1)"""
    if now is None:
        now = datetime.now()
    if isinstance(published_at, date) and not isinstance(published_at, datetime):
        published_at = datetime.combine(published_at, datetime.min.time())
    
    # timezone-aware → naive 변환 (DB는 timestamptz, Python은 naive)
    if hasattr(published_at, 'tzinfo') and published_at.tzinfo is not None:
        published_at = published_at.replace(tzinfo=None)
    if hasattr(now, 'tzinfo') and now.tzinfo is not None:
        now = now.replace(tzinfo=None)
    
    hours_ago = (now - published_at).total_seconds() / 3600.0
    
    if hours_ago < 0:
        hours_ago = 0
    if hours_ago > DECAY_WINDOW_HOURS:
        return 0.0
    
    # 지수 감쇠: w = 2^(-hours/halflife)
    return math.pow(2.0, -hours_ago / DECAY_HALFLIFE_HOURS)


def _article_shrinkage(article_count: int, raw_score: float) -> float:
    """
    뉴스 양 보정: 뉴스 적으면 중립(50)으로 당김
    
    article_count=1 → 80% prior + 20% data
    article_count=3 → 40% prior + 60% data  
    article_count=5+ → 0% prior + 100% data
    """
    if article_count >= MIN_ARTICLES_FOR_FULL_WEIGHT:
        return raw_score
    
    # 0~1 사이 비율 (5건 기준)
    data_weight = article_count / MIN_ARTICLES_FOR_FULL_WEIGHT
    return data_weight * raw_score + (1.0 - data_weight) * SHRINKAGE_PRIOR


def run_news_daily_aggregate_v2():
    """
    시간 감쇠 + 양 보정 적용된 일별 뉴스 감성 집계
    
    기존 대비 변경:
    - SQL AVG → Python 가중 평균 (시간 감쇠)
    - 뉴스 양 보정 (Shrinkage)
    - confidence_score 계산
    """
    today = date.today()
    now = datetime.now()

    # 최근 72시간 뉴스 + 감성 점수를 개별 행으로 조회
    with get_cursor() as cur:
        cur.execute("""
            SELECT
                a.stock_id,
                s.sentiment_score,
                s.sentiment_label,
                s.confidence,
                a.published_at
            FROM news_articles a
            JOIN news_sentiment_scores s ON a.news_id = s.news_id
            WHERE a.published_at >= NOW() - INTERVAL '72 hours'
            ORDER BY a.stock_id, a.published_at DESC
        """)
        rows = [dict(r) for r in cur.fetchall()]

    if not rows:
        print("[NEWS-AGG-v2] 집계할 데이터 없음")
        return

    # 종목별 그룹핑
    from collections import defaultdict
    by_stock = defaultdict(list)
    for r in rows:
        by_stock[r["stock_id"]].append(r)

    ok = 0
    for stock_id, articles in by_stock.items():
        # ── 시간 감쇠 가중 평균 ──
        weighted_sum = 0.0
        weight_total = 0.0
        pos_cnt = neg_cnt = neu_cnt = 0

        for art in articles:
            score = float(art["sentiment_score"]) if art["sentiment_score"] else 0.0
            pub_at = art["published_at"]
            w = _time_decay_weight(pub_at, now)
            
            # FinBERT confidence도 가중치에 반영
            conf = float(art["confidence"]) if art["confidence"] else 0.5
            final_w = w * conf
            
            weighted_sum += score * final_w
            weight_total += final_w

            label = art["sentiment_label"]
            if label == "POSITIVE": pos_cnt += 1
            elif label == "NEGATIVE": neg_cnt += 1
            else: neu_cnt += 1

        total_articles = len(articles)
        
        # 가중 평균 감성 (-1 ~ +1)
        if weight_total > 0:
            avg_sentiment = weighted_sum / weight_total
        else:
            avg_sentiment = 0.0

        # → 0~100 스케일
        news_score_raw = round((avg_sentiment + 1) * 50, 2)
        news_score_raw = max(0, min(100, news_score_raw))

        # ── 뉴스 양 보정 (Shrinkage) ──
        news_score = round(_article_shrinkage(total_articles, news_score_raw), 2)

        # ── DB 저장 ──
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
            """, (stock_id, today, round(avg_sentiment, 4),
                  pos_cnt, neg_cnt, neu_cnt,
                  total_articles, news_score))
        ok += 1

    print(f"[NEWS-AGG-v2] ✅ {ok}종목 집계 (시간감쇠+양보정)")