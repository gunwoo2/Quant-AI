"""
batch/batch_fear_greed.py — CNN Fear & Greed Index 수집
========================================================
CNN Fear & Greed Index를 수집하여 market_fear_greed 테이블에 저장.

지표 구성 (7개):
  1. Market Momentum (S&P 500 vs 125-day MA)
  2. Stock Price Strength (52주 고가/저가 비율)
  3. Stock Price Breadth (상승/하락 종목 거래량)
  4. Put/Call Options
  5. Market Volatility (VIX)
  6. Safe Haven Demand (채권 vs 주식 수익률 차이)
  7. Junk Bond Demand (하이일드 스프레드)

종합 점수: 0 (Extreme Fear) ~ 100 (Extreme Greed)

DB: market_fear_greed (자동 생성)
스케줄: 매일 1회
API 비용: ❌ 없음 (CNN 무료 엔드포인트)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from datetime import datetime, date
from db_pool import get_cursor


def _ensure_table():
    """market_fear_greed 테이블 자동 생성"""
    with get_cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS market_fear_greed (
                id           SERIAL PRIMARY KEY,
                calc_date    DATE NOT NULL UNIQUE,
                score        NUMERIC NOT NULL,
                rating       VARCHAR(20),
                previous_close NUMERIC,
                one_week_ago   NUMERIC,
                one_month_ago  NUMERIC,
                one_year_ago   NUMERIC,
                updated_at   TIMESTAMPTZ DEFAULT NOW()
            )
        """)
    print("[F&G] ✅ market_fear_greed 테이블 확인")


def _classify_rating(score: float) -> str:
    """점수 → 레이팅 분류"""
    if score <= 25:
        return "Extreme Fear"
    elif score <= 45:
        return "Fear"
    elif score <= 55:
        return "Neutral"
    elif score <= 75:
        return "Greed"
    else:
        return "Extreme Greed"


def run_fear_greed(calc_date: date = None):
    """CNN Fear & Greed Index 수집"""
    if calc_date is None:
        calc_date = date.today()

    _ensure_table()

    # ── 방법 1: CNN API 직접 호출 ──
    score = None
    previous = None
    one_week = None
    one_month = None
    one_year = None

    try:
        # CNN의 Fear & Greed API 엔드포인트
        resp = requests.get(
            "https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            fg = data.get("fear_and_greed", {})
            score = float(fg.get("score", 0))
            previous = float(fg.get("previous_close", 0)) if fg.get("previous_close") else None
            one_week = float(fg.get("previous_1_week", 0)) if fg.get("previous_1_week") else None
            one_month = float(fg.get("previous_1_month", 0)) if fg.get("previous_1_month") else None
            one_year = float(fg.get("previous_1_year", 0)) if fg.get("previous_1_year") else None
            print(f"[F&G] CNN API 성공: score={score:.1f}")
    except Exception as e:
        print(f"[F&G] CNN API 실패: {e}")

    # ── 방법 2: Alternative.me API (fallback) ──
    if score is None:
        try:
            resp = requests.get(
                "https://api.alternative.me/fng/?limit=1&format=json",
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json().get("data", [{}])[0]
                score = float(data.get("value", 50))
                print(f"[F&G] Alternative.me fallback: score={score:.1f}")
        except Exception as e:
            print(f"[F&G] Alternative.me도 실패: {e}")

    # ── 방법 3: VIX 기반 자체 계산 (최종 fallback) ──
    if score is None:
        try:
            with get_cursor() as cur:
                cur.execute("""
                    SELECT vix_close FROM market_regime
                    ORDER BY regime_date DESC LIMIT 1
                """)
                row = cur.fetchone()
            if row and row["vix_close"]:
                vix = float(row["vix_close"])
                # VIX → Fear/Greed 역변환 (VIX 12=Greed 85, VIX 30=Fear 20, VIX 40=Extreme Fear 5)
                score = max(0, min(100, 100 - (vix - 12) * 3))
                print(f"[F&G] VIX fallback: VIX={vix:.1f} → score={score:.1f}")
        except Exception:
            pass

    if score is None:
        score = 50.0  # 아무것도 안 되면 중립
        print("[F&G] ⚠️ 모든 소스 실패, 중립(50) 저장")

    rating = _classify_rating(score)

    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO market_fear_greed (
                calc_date, score, rating,
                previous_close, one_week_ago, one_month_ago, one_year_ago
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (calc_date) DO UPDATE SET
                score = EXCLUDED.score,
                rating = EXCLUDED.rating,
                previous_close = EXCLUDED.previous_close,
                one_week_ago   = EXCLUDED.one_week_ago,
                one_month_ago  = EXCLUDED.one_month_ago,
                one_year_ago   = EXCLUDED.one_year_ago,
                updated_at = NOW()
        """, (calc_date, score, rating,
              previous, one_week, one_month, one_year))

    emoji = {"Extreme Fear": "😱", "Fear": "😰", "Neutral": "😐", 
             "Greed": "😏", "Extreme Greed": "🤑"}.get(rating, "")
    print(f"[F&G] ✅ {calc_date}: {score:.1f} = {rating} {emoji}")
    
    return {"score": score, "rating": rating}


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    from db_pool import init_pool
    init_pool()
    run_fear_greed()