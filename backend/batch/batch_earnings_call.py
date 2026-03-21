"""
batch/batch_earnings_call.py — 어닝콜 텍스트 감성 분석
=======================================================
Step 6: 어닝콜 트랜스크립트 → FinBERT → 경영진 자신감 점수

데이터 소스: Finnhub /stock/transcripts (무료 tier)
분석 방법:
  1. CEO/CFO 발언만 추출
  2. 각 발언을 FinBERT로 감성 분석
  3. 경영진 자신감 = CEO감성×0.6 + CFO감성×0.4
  4. earnings_call_sentiment 테이블 저장
  5. L2 스코어링 시 반영 (layer2_scoring.py)

Scheduler 연동:
  - 분기 1회 실행 (또는 최근 transcript 없으면 수집)
  - run_earnings_call_analysis() 호출
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

try:
    import patch_numpy_adapter
except ImportError:
    pass

import time
import requests
from datetime import datetime, date
from db_pool import get_cursor
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")


# ═══════════════════════════════════════════════════════════
# FinBERT 로딩 (batch_layer2_v2와 공유)
# ═══════════════════════════════════════════════════════════

_finbert_pipeline = None

def _get_finbert():
    global _finbert_pipeline
    if _finbert_pipeline is not None:
        return _finbert_pipeline
    try:
        from transformers import pipeline
        _finbert_pipeline = pipeline(
            "sentiment-analysis",
            model="ProsusAI/finbert",
            tokenizer="ProsusAI/finbert",
            device=-1,
            truncation=True,
            max_length=512,
        )
        print("[EC] FinBERT 모델 로드 완료")
        return _finbert_pipeline
    except Exception as e:
        print(f"[EC] FinBERT 로드 실패, 키워드 fallback 사용: {e}")
        _finbert_pipeline = "FALLBACK"
        return "FALLBACK"


def _analyze_text(text: str) -> tuple:
    """텍스트 → (score: -1~+1, label, confidence)"""
    model = _get_finbert()
    
    if model == "FALLBACK" or model is None:
        # 간단 키워드 기반 fallback
        text_l = text.lower()
        pos_words = ["strong", "growth", "exceed", "record", "confident", "optimistic",
                     "robust", "beat", "upside", "momentum", "opportunity"]
        neg_words = ["weak", "decline", "miss", "concern", "challenge", "headwind",
                     "difficult", "uncertain", "slowdown", "pressure", "risk"]
        pos = sum(1 for w in pos_words if w in text_l)
        neg = sum(1 for w in neg_words if w in text_l)
        total = pos + neg
        if total == 0:
            return (0.0, "NEUTRAL", 0.3)
        score = (pos - neg) / total
        label = "POSITIVE" if score > 0.1 else ("NEGATIVE" if score < -0.1 else "NEUTRAL")
        return (round(score, 4), label, 0.5)
    
    try:
        result = model(text[:512])[0]
        label_raw = result["label"].lower()
        conf = round(result["score"], 4)
        if label_raw == "positive": return (conf, "POSITIVE", conf)
        elif label_raw == "negative": return (-conf, "NEGATIVE", conf)
        else: return (0.0, "NEUTRAL", conf)
    except:
        return (0.0, "NEUTRAL", 0.3)


# ═══════════════════════════════════════════════════════════
# C-Level 판별
# ═══════════════════════════════════════════════════════════

def _is_ceo(name: str, role: str = "") -> bool:
    combined = (name + " " + role).lower()
    # "vice president"는 CEO가 아님 → president 앞에 vice 체크
    if "ceo" in combined or "chief executive" in combined:
        return True
    if "president" in combined and "vice" not in combined:
        return True
    return False

def _is_cfo(name: str, role: str = "") -> bool:
    combined = (name + " " + role).lower()
    return any(k in combined for k in ["cfo", "chief financial", "finance"])

def _is_executive(name: str, role: str = "") -> bool:
    combined = (name + " " + role).lower()
    return any(k in combined for k in [
        "ceo", "cfo", "coo", "cto", "chief", "president", "vp",
        "vice president", "director", "head of", "svp", "evp"])


# ═══════════════════════════════════════════════════════════
# Finnhub Transcript 수집
# ═══════════════════════════════════════════════════════════

def _fetch_transcript(ticker: str, year: int, quarter: int) -> dict:
    """Finnhub에서 어닝콜 트랜스크립트 조회"""
    url = "https://finnhub.io/api/v1/stock/transcripts"
    params = {
        "symbol": ticker,
        "year": year,
        "quarter": quarter,
        "token": FINNHUB_API_KEY,
    }
    try:
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if data and "transcript" in data and data["transcript"]:
                return data
        return None
    except Exception as e:
        print(f"[EC] {ticker} Q{quarter}/{year} 조회 실패: {e}")
        return None


def _get_latest_quarter():
    """현재 기준 최근 분기"""
    now = datetime.now()
    q = (now.month - 1) // 3  # 0,1,2,3
    if q == 0:
        return now.year - 1, 4
    return now.year, q


# ═══════════════════════════════════════════════════════════
# 경영진 자신감 분석
# ═══════════════════════════════════════════════════════════

def _analyze_transcript(transcript_data: dict) -> dict:
    """
    트랜스크립트 → 경영진 자신감 점수
    
    Returns:
      ceo_sentiment: -1~+1
      cfo_sentiment: -1~+1  
      mgmt_confidence: 0~100
      exec_count: 분석된 발언자 수
      total_segments: 전체 발언 수
    """
    speakers = transcript_data.get("transcript", [])
    if not speakers:
        return None
    
    ceo_scores = []
    cfo_scores = []
    exec_scores = []
    
    for speaker in speakers:
        name = speaker.get("name", "")
        role = speaker.get("role", "")
        speeches = speaker.get("speech", [])
        
        if not speeches:
            continue
        
        # Analyst 질문은 스킵
        if "analyst" in role.lower() or "question" in role.lower():
            continue
        
        # 발언 결합 (최대 3000자 → 512 토큰으로 잘림)
        full_text = " ".join(speeches)[:3000]
        
        if not full_text.strip():
            continue
        
        # 긴 텍스트는 청크로 나눠 분석 후 평균
        chunks = [full_text[i:i+500] for i in range(0, len(full_text), 500)]
        chunk_scores = []
        for chunk in chunks[:5]:  # 최대 5 청크
            score, label, conf = _analyze_text(chunk)
            chunk_scores.append(score * conf)  # confidence 가중
        
        if not chunk_scores:
            continue
            
        avg_score = sum(chunk_scores) / len(chunk_scores)
        
        if _is_ceo(name, role):
            ceo_scores.append(avg_score)
        elif _is_cfo(name, role):
            cfo_scores.append(avg_score)
        elif _is_executive(name, role):
            exec_scores.append(avg_score)
    
    # CEO/CFO 감성 평균
    ceo_avg = sum(ceo_scores) / len(ceo_scores) if ceo_scores else None
    cfo_avg = sum(cfo_scores) / len(cfo_scores) if cfo_scores else None
    
    # 경영진 자신감 = CEO×0.6 + CFO×0.4
    # CEO 없으면 CFO만, 둘 다 없으면 executive 평균
    if ceo_avg is not None and cfo_avg is not None:
        mgmt_raw = ceo_avg * 0.6 + cfo_avg * 0.4
    elif ceo_avg is not None:
        mgmt_raw = ceo_avg
    elif cfo_avg is not None:
        mgmt_raw = cfo_avg
    elif exec_scores:
        mgmt_raw = sum(exec_scores) / len(exec_scores)
    else:
        return None
    
    # -1~+1 → 0~100
    mgmt_confidence = round((mgmt_raw + 1) * 50, 2)
    mgmt_confidence = max(0.0, min(100.0, mgmt_confidence))
    
    return {
        "ceo_sentiment": round(ceo_avg, 4) if ceo_avg is not None else None,
        "cfo_sentiment": round(cfo_avg, 4) if cfo_avg is not None else None,
        "mgmt_confidence_score": mgmt_confidence,
        "exec_count": len(ceo_scores) + len(cfo_scores) + len(exec_scores),
        "total_segments": len(speakers),
    }


# ═══════════════════════════════════════════════════════════
# 메인 실행
# ═══════════════════════════════════════════════════════════

def run_earnings_call_analysis(calc_date: date = None):
    """
    활성 종목의 최근 분기 어닝콜 분석
    - 이미 분석된 분기는 스킵
    - API Rate Limit: 60 calls/min → 1초 대기
    """
    if calc_date is None:
        calc_date = datetime.now().date()
    
    year, quarter = _get_latest_quarter()
    print(f"[EC] ▶ 어닝콜 분석 시작: Q{quarter}/{year}")
    
    # 활성 종목 조회
    with get_cursor() as cur:
        cur.execute("SELECT stock_id, ticker FROM stocks WHERE is_active = TRUE")
        stocks = [dict(r) for r in cur.fetchall()]
    
    # 이미 분석된 종목 스킵
    already = set()
    with get_cursor() as cur:
        cur.execute("""
            SELECT stock_id FROM earnings_call_sentiment
            WHERE fiscal_year = %s AND fiscal_quarter = %s
        """, (year, quarter))
        already = {r["stock_id"] for r in cur.fetchall()}
    
    targets = [s for s in stocks if s["stock_id"] not in already]
    print(f"[EC] 대상: {len(targets)}종목 (이미 분석: {len(already)}종목 스킵)")
    
    if not targets:
        print("[EC] ✅ 분석할 종목 없음 (이미 완료)")
        return {"ok": 0, "fail": 0, "skip": len(already)}
    
    ok, fail, no_data = 0, 0, 0
    
    for i, s in enumerate(targets):
        stock_id = s["stock_id"]
        ticker = s["ticker"]
        
        try:
            # API 호출 (rate limit 준수)
            if i > 0 and i % 55 == 0:
                print(f"[EC] Rate limit 대기 (60초)...")
                time.sleep(62)
            
            transcript = _fetch_transcript(ticker, year, quarter)
            time.sleep(1.1)  # 1초 대기 (60 calls/min)
            
            if not transcript:
                no_data += 1
                continue
            
            # 분석
            result = _analyze_transcript(transcript)
            
            if not result:
                no_data += 1
                continue
            
            # DB 저장
            with get_cursor() as cur:
                cur.execute("""
                    INSERT INTO earnings_call_sentiment (
                        stock_id, fiscal_year, fiscal_quarter, calc_date,
                        ceo_sentiment, cfo_sentiment,
                        mgmt_confidence_score, exec_count, total_segments
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (stock_id, fiscal_year, fiscal_quarter) DO UPDATE SET
                        ceo_sentiment         = EXCLUDED.ceo_sentiment,
                        cfo_sentiment         = EXCLUDED.cfo_sentiment,
                        mgmt_confidence_score = EXCLUDED.mgmt_confidence_score,
                        exec_count            = EXCLUDED.exec_count,
                        total_segments        = EXCLUDED.total_segments,
                        calc_date             = EXCLUDED.calc_date
                """, (stock_id, year, quarter, calc_date,
                      result["ceo_sentiment"], result["cfo_sentiment"],
                      result["mgmt_confidence_score"],
                      result["exec_count"], result["total_segments"]))
            
            ok += 1
            if ok <= 5 or ok % 20 == 0:
                ceo_s = f"CEO={result['ceo_sentiment']:.2f}" if result['ceo_sentiment'] else "CEO=N/A"
                cfo_s = f"CFO={result['cfo_sentiment']:.2f}" if result['cfo_sentiment'] else "CFO=N/A"
                print(f"[EC] {ticker}: {ceo_s} {cfo_s} → conf={result['mgmt_confidence_score']} ✓")
        
        except Exception as e:
            fail += 1
            if fail <= 3:
                print(f"[EC] {ticker} 실패: {e}")
    
    print(f"[EC] ✅ 완료: 성공={ok} 실패={fail} 데이터없음={no_data}")
    return {"ok": ok, "fail": fail, "no_data": no_data}


# ═══════════════════════════════════════════════════════════
# DDL (테이블 생성 SQL)
# ═══════════════════════════════════════════════════════════

DDL = """
-- 어닝콜 감성 분석 결과 테이블
CREATE TABLE IF NOT EXISTS earnings_call_sentiment (
    id              SERIAL PRIMARY KEY,
    stock_id        INTEGER NOT NULL REFERENCES stocks(stock_id),
    fiscal_year     INTEGER NOT NULL,
    fiscal_quarter  INTEGER NOT NULL,
    calc_date       DATE NOT NULL,
    ceo_sentiment   NUMERIC(6,4),       -- -1 ~ +1
    cfo_sentiment   NUMERIC(6,4),       -- -1 ~ +1
    mgmt_confidence_score NUMERIC(6,2), -- 0 ~ 100
    exec_count      INTEGER DEFAULT 0,
    total_segments  INTEGER DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (stock_id, fiscal_year, fiscal_quarter)
);

CREATE INDEX IF NOT EXISTS idx_ec_sentiment_stock
    ON earnings_call_sentiment (stock_id, fiscal_year DESC, fiscal_quarter DESC);
"""


if __name__ == "__main__":
    from db_pool import init_pool
    init_pool()
    
    # 테이블 생성
    with get_cursor() as cur:
        cur.execute(DDL)
    print("[EC] 테이블 생성/확인 완료")
    
    # 실행
    run_earnings_call_analysis()