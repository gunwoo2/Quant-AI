"""
batch/batch_final_score.py — 최종 점수 합산 v3.1 (Step 4: 적응형)
================================================================
변경:
  - final_score_engine 적응형 합산 (동적 가중치 + Shrinkage)
  - L2/L3 결측 시 50.0 하드코딩 → 가중치 재분배
  - data_completeness, confidence_level DB 저장
  - L3 컬럼 COALESCE (layer3_total_score ∥ layer3_technical_score)
  - Strong Buy/Sell 다층 판별
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import patch_numpy_adapter
except ImportError:
    pass

from datetime import datetime, date
from db_pool import get_cursor
from utils.grade_utils import score_to_grade, score_to_signal


# ═══════════════════════════════════════════════════════════
# final_score_engine import (없으면 자체 구현)
# ═══════════════════════════════════════════════════════════

try:
    from utils.final_score_engine import calc_final_weighted_score, calc_conviction_signal
    _HAS_FSE = True
except ImportError:
    _HAS_FSE = False


# ── 자체 구현 (final_score_engine 없을 때 폴백) ──

W_L1, W_L2, W_L3 = 0.50, 0.25, 0.25
SHRINKAGE_ALPHA = 0.15

def _clamp(v, lo, hi):
    return float(max(lo, min(hi, v)))

if not _HAS_FSE:
    def calc_final_weighted_score(layer1_score=None, layer2_score=None, layer3_score=None):
        layers = {"L1": (layer1_score, W_L1), "L2": (layer2_score, W_L2), "L3": (layer3_score, W_L3)}
        available = {}
        missing_count = 0
        for name, (score, base_w) in layers.items():
            if score is not None:
                available[name] = (float(score), base_w)
            else:
                missing_count += 1

        if not available:
            return {"weighted_score": 50.0, "data_completeness": 0.0,
                    "l1_weight_actual": 0.0, "l2_weight_actual": 0.0,
                    "l3_weight_actual": 0.0, "confidence_level": "LOW"}

        total_w = sum(w for _, w in available.values())
        actual = {n: w / total_w for n, (_, w) in available.items()}
        weighted = sum(s * actual[n] for n, (s, _) in available.items())
        shrinkage = missing_count * SHRINKAGE_ALPHA
        weighted = weighted * (1.0 - shrinkage) + 50.0 * shrinkage
        weighted = _clamp(round(weighted, 2), 0.0, 100.0)
        dc = len(available) / 3.0
        conf = "HIGH" if dc >= 1.0 else ("MEDIUM" if dc >= 0.67 else "LOW")
        return {"weighted_score": weighted, "data_completeness": round(dc, 2),
                "l1_weight_actual": round(actual.get("L1", 0), 4),
                "l2_weight_actual": round(actual.get("L2", 0), 4),
                "l3_weight_actual": round(actual.get("L3", 0), 4),
                "confidence_level": conf}

    def calc_conviction_signal(weighted_score, layer1_score=None,
                                layer2_score=None, layer3_score=None,
                                data_completeness=1.0):
        l1 = layer1_score or 50.0; l2 = layer2_score or 50.0; l3 = layer3_score or 50.0
        sb, ss, reason = False, False, ""
        if data_completeness >= 0.67 and weighted_score >= 72 and l1 >= 65:
            if l2 >= 55 or l3 >= 55:
                sb = True; r = []
                if l1 >= 70: r.append("L1강세")
                if l2 >= 60: r.append("NLP긍정")
                if l3 >= 65: r.append("기술강세")
                reason = "+".join(r) or "종합고점수"
        if weighted_score <= 35 and l1 <= 40:
            ss = True; r = []
            if l1 <= 30: r.append("L1약세")
            if l2 <= 35: r.append("NLP부정")
            if l3 <= 30: r.append("기술약세")
            reason = "+".join(r) or "종합저점수"
        return {"strong_buy_signal": sb, "strong_sell_signal": ss, "conviction_reason": reason}


def _f(v):
    if v is None: return None
    try: return float(v)
    except: return None


def _signal_to_opinion(signal):
    return {"STRONG_BUY":"강력매수","BUY":"매수","HOLD":"보유",
            "SELL":"매도","STRONG_SELL":"강력매도"}.get(signal, "보유")


# ═══════════════════════════════════════════════════════════
# 메인 실행
# ═══════════════════════════════════════════════════════════

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
                   COALESCE(l3.layer3_total_score, l3.layer3_technical_score) AS layer3_score
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
                SELECT DISTINCT ON (stock_id) stock_id,
                       layer3_total_score, layer3_technical_score
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
            l1_raw = _f(s.get("layer1_score"))
            l2_raw = _f(s.get("layer2_total_score"))
            l3_raw = _f(s.get("layer3_score"))

            # ── 적응형 합산 ──
            result = calc_final_weighted_score(
                layer1_score=l1_raw,
                layer2_score=l2_raw,
                layer3_score=l3_raw,
            )

            weighted = result["weighted_score"]
            dc       = result["data_completeness"]
            conf     = result["confidence_level"]

            grade   = score_to_grade(weighted)
            signal  = score_to_signal(weighted)
            opinion = _signal_to_opinion(signal)

            # ── Strong Buy/Sell ──
            conviction = calc_conviction_signal(
                weighted, l1_raw, l2_raw, l3_raw, dc)

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
                      l1_raw or 0, l2_raw or 0, l3_raw or 0,
                      weighted, grade, signal, opinion,
                      conviction["strong_buy_signal"],
                      conviction["strong_sell_signal"]))

                # stock_rating_history
                cur.execute("""
                    INSERT INTO stock_rating_history (
                        stock_id, rating_date,
                        layer1_score, layer2_score, layer3_score,
                        weighted_score, grade, signal
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (stock_id, rating_date) DO UPDATE SET
                        layer1_score   = EXCLUDED.layer1_score,
                        layer2_score   = EXCLUDED.layer2_score,
                        layer3_score   = EXCLUDED.layer3_score,
                        weighted_score = EXCLUDED.weighted_score,
                        grade          = EXCLUDED.grade,
                        signal         = EXCLUDED.signal
                """, (stock_id, calc_date,
                      l1_raw or 0, l2_raw or 0, l3_raw or 0,
                      weighted, grade, signal))

                # high_conviction_signals (Strong Buy/Sell만)
                if conviction["strong_buy_signal"] or conviction["strong_sell_signal"]:
                    cur.execute("""
                        INSERT INTO high_conviction_signals (
                            stock_id, calc_date,
                            layer1_score, layer2_score, layer3_score,
                            final_score, signal_type, reason
                        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (stock_id, calc_date) DO UPDATE SET
                            layer1_score = EXCLUDED.layer1_score,
                            layer2_score = EXCLUDED.layer2_score,
                            layer3_score = EXCLUDED.layer3_score,
                            final_score  = EXCLUDED.final_score,
                            signal_type  = EXCLUDED.signal_type,
                            reason       = EXCLUDED.reason
                    """, (stock_id, calc_date,
                          l1_raw or 0, l2_raw or 0, l3_raw or 0,
                          weighted,
                          "STRONG_BUY" if conviction["strong_buy_signal"] else "STRONG_SELL",
                          conviction["conviction_reason"]))

            ok += 1
            l1_str = f"{l1_raw:.1f}" if l1_raw else "N/A"
            l2_str = f"{l2_raw:.1f}" if l2_raw else "N/A"
            l3_str = f"{l3_raw:.1f}" if l3_raw else "N/A"

            if ok <= 7 or ok % 50 == 0:
                extra = f" [{conf}]" if conf != "HIGH" else ""
                print(f"  {ticker}: L1={l1_str} L2={l2_str} L3={l3_str} "
                      f"→ {weighted} ({grade}/{signal}){extra}")

        except Exception as e:
            fail += 1
            if fail <= 3:
                print(f"[FINAL] {ticker} fail: {e}")

    print(f"[FINAL] ✅ 완료 성공={ok} 실패={fail}")
    return {"ok": ok, "fail": fail}


if __name__ == "__main__":
    from db_pool import init_pool
    init_pool()
    run_final_score()