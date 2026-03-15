"""
batch_final_score.py — 최종 점수 합산 배치
L1(50%) + L2(25%) + L3(25%) 가중합산 → 등급 산출
→ stock_final_scores, stock_rating_history, high_conviction_signals
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, date
from db_pool import get_cursor
from utils.grade_utils import score_to_grade, score_to_signal


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
            l1 = _f(s.get("layer1_score"))      or 0.0
            l2 = _f(s.get("layer2_total_score")) or 50.0  # 없으면 중립
            l3 = _f(s.get("layer3_total_score")) or 50.0  # 없으면 중립

            # L1 50% + L2 25% + L3 25%
            weighted = round(l1 * 0.50 + l2 * 0.25 + l3 * 0.25, 2)
            grade    = score_to_grade(weighted)
            signal   = score_to_signal(weighted)
            opinion  = _signal_to_opinion(signal)

            strong_buy  = (weighted >= 72 and l1 >= 65 and l2 >= 60)
            strong_sell = (weighted <= 35 and l1 <= 40)

            with get_cursor() as cur:
                # stock_final_scores
                cur.execute("""
                    INSERT INTO stock_final_scores (
                        stock_id, calc_date,
                        layer1_score, layer2_score, layer3_score,
                        weighted_score, grade, signal, investment_opinion,
                        strong_buy_signal, strong_sell_signal
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (stock_id, calc_date) DO UPDATE SET
                        layer1_score       = EXCLUDED.layer1_score,
                        layer2_score       = EXCLUDED.layer2_score,
                        layer3_score       = EXCLUDED.layer3_score,
                        weighted_score     = EXCLUDED.weighted_score,
                        grade              = EXCLUDED.grade,
                        signal             = EXCLUDED.signal,
                        investment_opinion = EXCLUDED.investment_opinion,
                        strong_buy_signal  = EXCLUDED.strong_buy_signal,
                        strong_sell_signal = EXCLUDED.strong_sell_signal
                """, (stock_id, calc_date,
                      l1, l2, l3,
                      weighted, grade, signal, opinion,
                      strong_buy, strong_sell))

                # stock_rating_history (rating_date 사용!)
                cur.execute("""
                    INSERT INTO stock_rating_history (
                        stock_id, rating_date, grade, signal,
                        weighted_score, layer1_score, layer2_score, layer3_score
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (stock_id, rating_date) DO NOTHING
                """, (stock_id, calc_date, grade, signal,
                      weighted, l1, l2, l3))

                # high_conviction_signals (signal_date 사용!)
                if strong_buy or strong_sell:
                    sig_type = "STRONG_BUY" if strong_buy else "STRONG_SELL"
                    cur.execute("""
                        INSERT INTO high_conviction_signals (
                            stock_id, signal_date, signal_type,
                            layer1_cond_met, layer2_cond_met, layer3_cond_met,
                            market_cond_met, is_active
                        ) VALUES (%s,%s,%s,%s,%s,%s,TRUE,TRUE)
                        ON CONFLICT DO NOTHING
                    """, (stock_id, calc_date, sig_type,
                          l1 >= 65, l2 >= 60, l3 >= 50))

            ok += 1
            print(f"  {ticker}: L1={l1:.1f} L2={l2:.1f} L3={l3:.1f}"
                  f" → {weighted:.1f} ({grade}/{signal})")

        except Exception as e:
            fail += 1
            print(f"  {ticker} 실패: {e}")

    print(f"[FINAL] ✅ 완료 성공={ok} 실패={fail}")


if __name__ == "__main__":
    import db_pool
    db_pool.init_pool()
    try:
        run_final_score()
    finally:
        db_pool.close_pool()

