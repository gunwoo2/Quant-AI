"""
batch/batch_fear_greed.py — CNN Fear & Greed Index 수집 (v2 — 진단 강화)
========================================================================
CNN Fear & Greed Index를 수집하여 market_fear_greed 테이블에 저장.

v2 변경사항:
  - 각 API 소스별 상세 로깅
  - VIX fallback 시 소스 표시
  - 마지막 성공 소스 로깅
  - CNN API URL 업데이트 (2024+ 엔드포인트)

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
                id             SERIAL PRIMARY KEY,
                calc_date      DATE NOT NULL UNIQUE,
                score          NUMERIC NOT NULL,
                rating         VARCHAR(20),
                previous_close NUMERIC,
                one_week_ago   NUMERIC,
                one_month_ago  NUMERIC,
                one_year_ago   NUMERIC,
                source         VARCHAR(30) DEFAULT 'unknown',
                updated_at     TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        # source 컬럼 추가 (기존 테이블 호환)
        cur.execute("""
            DO $$ BEGIN
                ALTER TABLE market_fear_greed ADD COLUMN IF NOT EXISTS source VARCHAR(30) DEFAULT 'unknown';
            EXCEPTION WHEN others THEN NULL;
            END $$;
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

    score = None
    previous = None
    one_week = None
    one_month = None
    one_year = None
    source_name = "unknown"

    # ── 방법 1: CNN API 직접 호출 ──
    try:
        resp = requests.get(
            "https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
            },
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            fg = data.get("fear_and_greed", {})
            raw_score = fg.get("score")
            if raw_score is not None:
                score = float(raw_score)
                previous = float(fg["previous_close"]) if fg.get("previous_close") else None
                one_week = float(fg["previous_1_week"]) if fg.get("previous_1_week") else None
                one_month = float(fg["previous_1_month"]) if fg.get("previous_1_month") else None
                one_year = float(fg["previous_1_year"]) if fg.get("previous_1_year") else None
                source_name = "cnn_api"
                print(f"[F&G] ✅ CNN API 성공: score={score:.1f}")
            else:
                print(f"[F&G] ⚠️ CNN API 응답은 왔지만 score 없음: {list(fg.keys())}")
        else:
            print(f"[F&G] ⚠️ CNN API HTTP {resp.status_code}")
    except requests.exceptions.Timeout:
        print("[F&G] ⚠️ CNN API 타임아웃 (15초)")
    except requests.exceptions.ConnectionError:
        print("[F&G] ⚠️ CNN API 연결 실패 (네트워크 문제 또는 차단)")
    except Exception as e:
        print(f"[F&G] ⚠️ CNN API 실패: {type(e).__name__}: {e}")

    # ── 방법 2: Alternative.me API (fallback, 암호화폐 F&G) ──
    if score is None:
        try:
            resp = requests.get(
                "https://api.alternative.me/fng/?limit=1&format=json",
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json().get("data", [{}])[0]
                raw_val = data.get("value")
                if raw_val is not None:
                    score = float(raw_val)
                    source_name = "alternative_me"
                    print(f"[F&G] ✅ Alternative.me fallback: score={score:.1f} (⚠ 암호화폐 기반)")
                else:
                    print("[F&G] ⚠️ Alternative.me 응답은 왔지만 value 없음")
            else:
                print(f"[F&G] ⚠️ Alternative.me HTTP {resp.status_code}")
        except Exception as e:
            print(f"[F&G] ⚠️ Alternative.me 실패: {type(e).__name__}: {e}")

    # ── 방법 3: VIX 기반 자체 계산 (최종 fallback) ──
    if score is None:
        try:
            vix_val = None
            vix_date = None

            # market_signal_daily 우선
            with get_cursor() as cur:
                cur.execute("""
                    SELECT vix_close, calc_date FROM market_signal_daily
                    ORDER BY calc_date DESC LIMIT 1
                """)
                row = cur.fetchone()
            if row and row["vix_close"]:
                vix_val = float(row["vix_close"])
                vix_date = row["calc_date"]

            # market_regime fallback
            if vix_val is None:
                with get_cursor() as cur:
                    cur.execute("""
                        SELECT vix_close, regime_date FROM market_regime
                        ORDER BY regime_date DESC LIMIT 1
                    """)
                    row = cur.fetchone()
                if row and row.get("vix_close"):
                    vix_val = float(row["vix_close"])
                    vix_date = row.get("regime_date")

            # macro_indicators fallback
            if vix_val is None:
                with get_cursor() as cur:
                    cur.execute("""
                        SELECT value, recorded_date FROM macro_indicators
                        WHERE indicator_name = 'VIX'
                        ORDER BY recorded_date DESC LIMIT 1
                    """)
                    row = cur.fetchone()
                if row and row["value"]:
                    vix_val = float(row["value"])
                    vix_date = row.get("recorded_date")

            if vix_val is not None:
                # VIX → Fear/Greed 역변환
                # VIX 12 = 100 (Extreme Greed)
                # VIX 20 = 76 (Greed)  
                # VIX 28 = 52 (Neutral)
                # VIX 30 = 46 (Fear)
                # VIX 42 = 10 (Extreme Fear)
                score = max(0, min(100, 100 - (vix_val - 12) * 3))
                source_name = "vix_fallback"

                # 데이터 신선도 경고
                if vix_date:
                    from datetime import timedelta
                    age_days = (calc_date - (vix_date if isinstance(vix_date, date) else vix_date.date() if hasattr(vix_date, 'date') else calc_date)).days
                    if age_days > 3:
                        print(f"[F&G] ⚠️ VIX 데이터가 {age_days}일 전 값입니다! (stale data)")

                print(f"[F&G] ⚠️ VIX fallback: VIX={vix_val:.1f} → score={score:.1f} (외부 API 모두 실패)")
            else:
                print("[F&G] ❌ VIX 데이터도 없음")
        except Exception as e:
            print(f"[F&G] ❌ VIX fallback 실패: {e}")

    # ── 최종 기본값 ──
    if score is None:
        score = 50.0
        source_name = "default"
        print("[F&G] ❌ 모든 소스 실패, 중립(50) 저장")

    rating = _classify_rating(score)

    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO market_fear_greed (
                calc_date, score, rating,
                previous_close, one_week_ago, one_month_ago, one_year_ago,
                source
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (calc_date) DO UPDATE SET
                score          = EXCLUDED.score,
                rating         = EXCLUDED.rating,
                previous_close = EXCLUDED.previous_close,
                one_week_ago   = EXCLUDED.one_week_ago,
                one_month_ago  = EXCLUDED.one_month_ago,
                one_year_ago   = EXCLUDED.one_year_ago,
                source         = EXCLUDED.source,
                updated_at     = NOW()
        """, (calc_date, score, rating,
              previous, one_week, one_month, one_year, source_name))

    emoji = {"Extreme Fear": "😱", "Fear": "😰", "Neutral": "😐", 
             "Greed": "😏", "Extreme Greed": "🤑"}.get(rating, "")
    print(f"[F&G] ✅ {calc_date}: {score:.1f} = {rating} {emoji}  (source: {source_name})")
    
    return {"score": score, "rating": rating, "source": source_name}


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    from db_pool import init_pool
    init_pool()
    run_fear_greed()
