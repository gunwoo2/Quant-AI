"""
batch/batch_final_score.py — 최종 점수 합산 v4.0 (Adaptive Threshold)
=====================================================================
v4.0 변경:
  ★ Cross-Sectional Percentile 기반 등급 (Barra USE4 방법론)
  ★ Absolute Floor Cap (쓰레기 1등 방지)
  ★ Rating Momentum — EMA Smoothing (Frazzini 2018)
  ★ Dispersion Guard — Factor Compression 감지
  ★ Conviction Score — 다차원 확신도
  ★ 2-Pass 방식: Pass1 점수계산 → Pass2 백분위 등급부여

v3.1 유지:
  - final_score_engine 적응형 합산 (동적 가중치 + Shrinkage)
  - L2/L3 결측 시 가중치 재분배
  - data_completeness, confidence_level
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import patch_numpy_adapter
except ImportError:
    pass

import numpy as np
from datetime import datetime, date
from db_pool import get_cursor
from utils.adaptive_scoring import (
    compute_cross_sectional_percentiles,
    percentile_to_grade,
    apply_absolute_floor,
    grade_to_signal,
    smooth_percentile,
    compute_dispersion_ratio,
    compute_conviction,
    calc_adaptive_conviction_signal,
    GRADE_ORDER,
)


# ═══════════════════════════════════════════════════════════
# final_score_engine import (없으면 자체 구현)
# ═══════════════════════════════════════════════════════════

try:
    from utils.final_score_engine import calc_final_weighted_score
    _HAS_FSE = True
except ImportError:
    _HAS_FSE = False

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


def _f(v):
    if v is None: return None
    try: return float(v)
    except (TypeError, ValueError): return None


def _signal_to_opinion(signal):
    return {"STRONG_BUY":"강력매수","BUY":"매수","HOLD":"보유",
            "SELL":"매도","STRONG_SELL":"강력매도"}.get(signal, "보유")


# ═══════════════════════════════════════════════════════════
# EMA 히스토리 조회/저장
# ═══════════════════════════════════════════════════════════

def _load_yesterday_smoothed(calc_date):
    """어제의 smoothed percentile rank 조회."""
    result = {}
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT stock_id, percentile_rank
                FROM stock_final_scores
                WHERE calc_date = (
                    SELECT MAX(calc_date) FROM stock_final_scores
                    WHERE calc_date < %s
                )
            """, (calc_date,))
            for r in cur.fetchall():
                result[r["stock_id"]] = float(r["percentile_rank"]) if r["percentile_rank"] else None
    except Exception:
        pass  # 첫 실행이면 빈 dict
    return result


def _get_stock_history_days(stock_id, calc_date):
    """종목의 점수 히스토리 일수."""
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) as cnt FROM stock_final_scores
                WHERE stock_id = %s AND calc_date < %s
            """, (stock_id, calc_date))
            return cur.fetchone()["cnt"]
    except Exception:
        return 0


def _load_historical_std(calc_date, lookback=60):
    """최근 N일 횡단면 분산 평균 (Dispersion Guard용)."""
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT AVG(score_std) as avg_std
                FROM daily_score_stats
                WHERE calc_date >= %s::date - %s AND calc_date < %s
            """, (calc_date, lookback, calc_date))
            row = cur.fetchone()
            if row and row["avg_std"]:
                return float(row["avg_std"])
    except Exception:
        pass
    return None


def _save_daily_stats(calc_date, scores):
    """일별 점수 통계 저장 (Dispersion Guard 히스토리)."""
    try:
        arr = np.array(scores, dtype=float)
        with get_cursor() as cur:
            cur.execute("""
                INSERT INTO daily_score_stats (calc_date, score_mean, score_std, score_median, stock_count)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (calc_date) DO UPDATE SET
                    score_mean = EXCLUDED.score_mean,
                    score_std = EXCLUDED.score_std,
                    score_median = EXCLUDED.score_median,
                    stock_count = EXCLUDED.stock_count
            """, (calc_date,
                  round(float(np.mean(arr)), 4),
                  round(float(np.std(arr)), 4),
                  round(float(np.median(arr)), 4),
                  len(arr)))
    except Exception as e:
        print(f"  [STATS] daily_score_stats 저장 실패 (테이블 미생성?): {e}")


# ═══════════════════════════════════════════════════════════
# 메인 실행
# ═══════════════════════════════════════════════════════════

def run_final_score(calc_date: date = None):
    if calc_date is None:
        calc_date = datetime.now().date()

    print(f"[FINAL] ▶ 시작 calc_date={calc_date} (Adaptive Scoring v4.0)")

    # ── DB에서 전 종목 원점수 로드 ──
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
    if not stocks:
        print("[FINAL] ⚠️ 종목 없음 — 종료")
        return {"ok": 0, "fail": 0}

    # ══════════════════════════════════════════════
    #  Pass 1: 전 종목 weighted_score 계산
    # ══════════════════════════════════════════════
    print("[FINAL] Pass 1: weighted_score 계산...")

    for s in stocks:
        l1 = _f(s.get("layer1_score"))
        l2 = _f(s.get("layer2_total_score"))
        l3 = _f(s.get("layer3_score"))

        result = calc_final_weighted_score(
            layer1_score=l1, layer2_score=l2, layer3_score=l3)

        s["l1_raw"] = l1
        s["l2_raw"] = l2
        s["l3_raw"] = l3
        s["weighted"] = result["weighted_score"]
        s["dc"] = result["data_completeness"]
        s["conf"] = result["confidence_level"]

    # ══════════════════════════════════════════════
    #  Pass 2: Cross-Sectional 분석 + 등급 부여
    # ══════════════════════════════════════════════
    print("[FINAL] Pass 2: 횡단면 분석 + 등급 부여...")

    # ① 전 종목 점수 배열
    all_weighted = np.array([s["weighted"] for s in stocks])
    all_l1 = np.array([s["l1_raw"] or 50.0 for s in stocks])
    all_l2 = np.array([s["l2_raw"] or 50.0 for s in stocks])
    all_l3 = np.array([s["l3_raw"] or 50.0 for s in stocks])

    # ② Percentile Rank (Barra MAD Z-Score 기반)
    pct_weighted = compute_cross_sectional_percentiles(all_weighted)
    pct_l1 = compute_cross_sectional_percentiles(all_l1)
    pct_l2 = compute_cross_sectional_percentiles(all_l2)
    pct_l3 = compute_cross_sectional_percentiles(all_l3)

    # ③ 일별 통계 저장 (Dispersion Guard 히스토리)
    _save_daily_stats(calc_date, all_weighted)

    # ④ Dispersion ratio
    hist_std = _load_historical_std(calc_date)
    disp_ratio = compute_dispersion_ratio(all_weighted, hist_std)

    # ⑤ EMA 히스토리 로드
    yesterday_smoothed = _load_yesterday_smoothed(calc_date)

    # ⑥ 통계 출력
    print(f"  [STATS] 평균={np.mean(all_weighted):.1f} "
          f"표준편차={np.std(all_weighted):.1f} "
          f"중앙값={np.median(all_weighted):.1f} "
          f"범위=[{np.min(all_weighted):.1f}~{np.max(all_weighted):.1f}]")
    print(f"  [STATS] 분산비율={disp_ratio:.3f} "
          f"(역사적 std={'%.2f' % hist_std if hist_std else 'N/A'})")

    # ══════════════════════════════════════════════
    #  Pass 3: DB 저장
    # ══════════════════════════════════════════════
    ok, fail = 0, 0

    for i, s in enumerate(stocks):
        stock_id = s["stock_id"]
        ticker = s["ticker"]

        try:
            weighted = s["weighted"]
            dc = s["dc"]
            conf = s["conf"]
            l1_raw = s["l1_raw"]
            l2_raw = s["l2_raw"]
            l3_raw = s["l3_raw"]

            # ── Percentile Rank ──
            raw_pct = float(pct_weighted[i])

            # ── EMA Smoothing ──
            prev_smoothed = yesterday_smoothed.get(stock_id)
            hist_days = len(yesterday_smoothed)  # 대략적 추정
            smoothed_pct = smooth_percentile(raw_pct, prev_smoothed,
                                             hist_days if prev_smoothed else 0)

            # ── 등급 산출 (smoothed percentile 기반) ──
            pct_grade = percentile_to_grade(smoothed_pct)
            grade = apply_absolute_floor(pct_grade, weighted)
            signal = grade_to_signal(grade)
            opinion = _signal_to_opinion(signal)

            # ── Conviction Score ──
            conv = compute_conviction(
                smoothed_pct,
                float(pct_l1[i]), float(pct_l2[i]), float(pct_l3[i]),
                dc, disp_ratio)

            # ── Strong Buy/Sell ──
            conviction = calc_adaptive_conviction_signal(
                grade, float(pct_l1[i]), float(pct_l2[i]), float(pct_l3[i]), dc)

            # ── DB 저장: stock_final_scores ──
            with get_cursor() as cur:
                cur.execute("""
                    INSERT INTO stock_final_scores (
                        stock_id, calc_date,
                        layer1_score, layer2_score, layer3_score,
                        weighted_score, grade, signal, investment_opinion,
                        strong_buy_signal, strong_sell_signal,
                        percentile_rank, conviction_score
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
                        percentile_rank    = EXCLUDED.percentile_rank,
                        conviction_score   = EXCLUDED.conviction_score
                """, (stock_id, calc_date,
                      l1_raw, l2_raw, l3_raw,
                      weighted, grade, signal, opinion,
                      conviction["strong_buy_signal"],
                      conviction["strong_sell_signal"],
                      round(smoothed_pct, 2),
                      conv["conviction_score"]))

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
                      l1_raw, l2_raw, l3_raw,
                      weighted, grade, signal))

                # high_conviction_signals
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
                          l1_raw, l2_raw, l3_raw,
                          weighted,
                          "STRONG_BUY" if conviction["strong_buy_signal"] else "STRONG_SELL",
                          conviction["conviction_reason"]))

            ok += 1

            if ok <= 7 or ok % 100 == 0:
                print(f"  {ticker}: {weighted:.1f}점 P{smoothed_pct:.0f} "
                      f"→ {grade}/{signal} conv={conv['conviction_score']:.3f}")

        except Exception as e:
            fail += 1
            if fail <= 3:
                import traceback
                print(f"[FINAL] {ticker} fail: {e}")
                traceback.print_exc()

    # ── 등급 분포 출력 ──
    from collections import Counter
    grade_dist = Counter()
    for s in stocks:
        raw_pct = float(pct_weighted[stocks.index(s)])
        prev = yesterday_smoothed.get(s["stock_id"])
        sp = smooth_percentile(raw_pct, prev, len(yesterday_smoothed) if prev else 0)
        g = apply_absolute_floor(percentile_to_grade(sp), s["weighted"])
        grade_dist[g] += 1

    print(f"\n  [등급 분포]")
    for g in ["S", "A+", "A", "B+", "B", "C", "D"]:
        cnt = grade_dist.get(g, 0)
        bar = "█" * min(cnt, 40)
        print(f"    {g:3s}: {cnt:>4d} {bar}")

    print(f"[FINAL] ✅ 완료 성공={ok} 실패={fail}")
    return {"ok": ok, "fail": fail}


if __name__ == "__main__":
    from db_pool import init_pool
    init_pool()
    run_final_score()