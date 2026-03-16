"""
batch_final_score.py — 최종 점수 합산 배치 v3.1
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

L1(50%) + L2(25%) + L3(25%) 동적 가중합산 → 등급 산출
→ stock_final_scores, stock_rating_history, high_conviction_signals

v3.1 변경사항:
  - 결측시 50 대체 제거 → 동적 가중치 재분배 + Shrinkage
  - 스코어링 로직을 utils.final_score_engine으로 분리
  - Strong Buy/Sell 조건 세분화 (데이터 완성도 조건 추가)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, date
from db_pool import get_cursor
from utils.grade_utils import score_to_grade, score_to_signal

# ── v3.1: 최종 합산 엔진 ──
from utils.final_score_engine import calc_final_weighted_score, calc_conviction_signal


def _f(v):
    if v is None:
        return None
    try:
        return float(v)
    except Exception:
        return None


def _signal_to_opinion(signal: str) -> str:
    return {
        "STRONG_BUY":  "강력매수",
        "BUY":         "매수",
        "HOLD":        "보유",
        "SELL":        "매도",
        "STRONG_SELL": "강력매도",
    }.get(signal, "보유")


def run_final_score(calc_date: date = None):
    if calc_date is None:
        calc_date = datetime.now().date()

    print(f"[FINAL] ▶ 시작 calc_date={calc_date}")

    stocks = []
    with get_cursor() as cur:
        cur.execute("""
            SELECT s.stock_id, s.ticker,
                   l1.layer1_score,
                   l2.layer2_total_score,
                   l3.layer3_total_score
            FROM stocks s
            LEFT JOIN (
                SELECT DISTINCT ON (stock_id) stock_id, layer1_score
                FROM stock_layer1_analysis
                ORDER BY stock_id, calc_date DESC
            ) l1 ON s.stock_id = l1.stock_id
            LEFT JOIN (
                SELECT DISTINCT ON (stock_id) stock_id, layer2_total_score
                FROM layer2_scores
                ORDER BY stock_id, calc_date DESC
            ) l2 ON s.stock_id = l2.stock_id
            LEFT JOIN (
                SELECT DISTINCT ON (stock_id) stock_id, layer3_total_score
                FROM technical_indicators
                ORDER BY stock_id, calc_date DESC
            ) l3 ON s.stock_id = l3.stock_id
            WHERE s.is_active = TRUE
        """)
        stocks = [dict(r) for r in cur.fetchall()]

    print(f"[FINAL] 대상 종목: {len(stocks)}개")

    ok, fail = 0, 0

    for s in stocks:
        stock_id = s["stock_id"]
        ticker   = s["ticker"]

        try:
            l1 = _f(s.get("layer1_score"))
            l2 = _f(s.get("layer2_total_score"))
            l3 = _f(s.get("layer3_total_score"))

            # ★ v3.1: 동적 가중합산 (결측 → 50 대체 제거)
            result = calc_final_weighted_score(
                layer1_score=l1,
                layer2_score=l2,
                layer3_score=l3,
            )
            weighted = result["weighted_score"]
            data_completeness = result["data_completeness"]

            grade   = score_to_grade(weighted)
            signal  = score_to_signal(weighted)
            opinion = _signal_to_opinion(signal)

            # ★ v3.1: 신호 판별 (데이터 완성도 고려)
            conviction = calc_conviction_signal(
                weighted_score=weighted,
                layer1_score=l1,
                layer2_score=l2,
                layer3_score=l3,
                data_completeness=data_completeness,
            )
            strong_buy  = conviction["strong_buy_signal"]
            strong_sell = conviction["strong_sell_signal"]
            confidence_level = result.get("confidence_level", "HIGH")

            with get_cursor() as cur:
                # stock_final_scores
                cur.execute("""
                    INSERT INTO stock_final_scores (
                        stock_id, calc_date,
                        layer1_score, layer2_score, layer3_score,
                        weighted_score, grade, signal, investment_opinion,
                        strong_buy_signal, strong_sell_signal,
                        data_completeness, confidence_level
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (stock_id, calc_date) DO UPDATE SET
                        layer1_score       = EXCLUDED.layer1_score,
                        layer2_score       = EXCLUDED.layer2_score,
                        layer3_score       = EXCLUDED.layer3_score,
                        weighted_score     = EXCLUDED.weighted_score,
                        grade              = EXCLUDED.grade,
                        signal             = EXCLUDED.signal,
                        investment_opinion = EXCLUDED.investment_opinion,
                        strong_buy_signal  = EXCLUDED.strong_buy_signal,
                        strong_sell_signal = EXCLUDED.strong_sell_signal,
                        data_completeness  = EXCLUDED.data_completeness,
                        confidence_level   = EXCLUDED.confidence_level
                """, (stock_id, calc_date,
                      l1, l2, l3,
                      weighted, grade, signal, opinion,
                      strong_buy, strong_sell,
                      data_completeness, confidence_level))

                # stock_rating_history
                cur.execute("""
                    INSERT INTO stock_rating_history (
                        stock_id, rating_date, score, grade, signal
                    ) VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (stock_id, rating_date) DO UPDATE SET
                        score  = EXCLUDED.score,
                        grade  = EXCLUDED.grade,
                        signal = EXCLUDED.signal
                """, (stock_id, calc_date, weighted, grade, signal))

                # high_conviction_signals
                if strong_buy or strong_sell:
                    sig_type = "STRONG_BUY" if strong_buy else "STRONG_SELL"
                    reason = conviction.get("conviction_reason", "")
                    cur.execute("""
                        INSERT INTO high_conviction_signals (
                            stock_id, signal_date, signal_type,
                            weighted_score, confidence_note
                        ) VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT DO NOTHING
                    """, (stock_id, calc_date, sig_type, weighted, reason))

            ok += 1
            if ok % 20 == 0 or ok <= 5:
                comp_str = f"{data_completeness:.0%}"
                print(f"[FINAL] {ticker}: {weighted} ({grade}/{signal}) "
                      f"[L1={l1} L2={l2} L3={l3}] data={comp_str} conf={confidence_level}")

        except Exception as e:
            fail += 1
            print(f"[FINAL] {ticker} 실패: {e}")

    print(f"[FINAL] ✅ 완료: {ok}성공 / {fail}실패")
    print(f"[FINAL] v3.1 동적 가중 + Shrinkage 적용")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    from db_pool import init_pool
    init_pool()
    run_final_score()
