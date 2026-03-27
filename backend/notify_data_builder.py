"""
notify_data_builder.py — QUANT AI v4.0 알림 데이터 계산 엔진
=============================================================
설계서: NOTIFICATION_V4_DESIGN.md 기반 구현

notifier_v4.py는 "포맷+전송"만 담당.
이 모듈이 "계산+데이터 조립"을 담당.

scheduler → notify_data_builder → notifier_v4
  (DB로드)     (계산 로직)         (Discord 전송)

구현 방법론:
  ① Goldman Conviction + Bridgewater Because → build_buy_rationale()
  ② Grinold-Kahn IC + Hit Rate              → calc_signal_ic(), calc_hit_rate()
  ③ MAE/MFE + Devil's Advocate              → build_sell_analysis()
  ④ Historical VaR + Stress Test            → build_risk_dashboard()
  ⑤ Brinson Attribution                     → build_weekly_brinson()
  ⑥ Regime Probability                      → calc_regime_probability()
"""
import math
import numpy as np
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Any
from collections import defaultdict

from db_pool import get_cursor

import logging
logger = logging.getLogger("notify_builder")


# ═══════════════════════════════════════════════════════════
#  1. BUY — 투자 근거 카드 (Goldman Conviction + Bridgewater Because)
# ═══════════════════════════════════════════════════════════

def build_buy_rationale(stock_id: int, ticker: str, calc_date: date,
                        base_signal: dict) -> dict:
    """
    매수 시그널에 v4 투자근거 데이터를 보강.
    
    추가 데이터:
      - L1/L2/L3 서브스코어 전체 조회
      - Conviction Level (HIGH/MEDIUM/LOW)
      - Because... 근거 텍스트 자동 생성
      - 섹터 집중도 + 포폴 내 상관관계 체크
      - R:R 비율 (목표가 vs 손절가)
      - 어닝 일정 체크
    """
    result = dict(base_signal)  # 기존 데이터 복사

    try:
        # ── L1 서브스코어 (moat/value/momentum/stability) ──
        with get_cursor() as cur:
            # Moat
            cur.execute("""
                SELECT roic_score, gpa_score, fcf_margin_score,
                       net_debt_ebitda_score, f_score_points, total_moat_score
                FROM quant_moat_scores
                WHERE stock_id = %s ORDER BY calc_date DESC LIMIT 1
            """, (stock_id,))
            moat = _row_to_dict(cur.fetchone())

            # Value
            cur.execute("""
                SELECT earnings_yield_score, ev_fcf_score, pb_score,
                       total_value_score
                FROM quant_value_scores
                WHERE stock_id = %s ORDER BY calc_date DESC LIMIT 1
            """, (stock_id,))
            value = _row_to_dict(cur.fetchone())

            # Momentum
            cur.execute("""
                SELECT f_score_raw, f_score_points, earnings_surprise_score,
                       earnings_revision_score, total_momentum_score
                FROM quant_momentum_scores
                WHERE stock_id = %s ORDER BY calc_date DESC LIMIT 1
            """, (stock_id,))
            momentum = _row_to_dict(cur.fetchone())

            # Stability
            cur.execute("""
                SELECT price_volatility_score, beta_score, dividend_score,
                       total_stability_score
                FROM quant_stability_scores
                WHERE stock_id = %s ORDER BY calc_date DESC LIMIT 1
            """, (stock_id,))
            stability = _row_to_dict(cur.fetchone())

        result["l1_sub"] = {
            "moat": moat, "value": value,
            "momentum": momentum, "stability": stability,
        }

        # ── L2 서브스코어 (news/analyst/insider) ──
        with get_cursor() as cur:
            cur.execute("""
                SELECT news_sentiment_score, analyst_rating_score,
                       insider_signal_score, layer2_total_score
                FROM layer2_scores
                WHERE stock_id = %s ORDER BY calc_date DESC LIMIT 1
            """, (stock_id,))
            l2 = _row_to_dict(cur.fetchone())

            # 뉴스 상세
            cur.execute("""
                SELECT avg_sentiment_score, positive_count, negative_count,
                       total_articles, layer2_news_score
                FROM news_sentiment_daily
                WHERE stock_id = %s ORDER BY sentiment_date DESC LIMIT 1
            """, (stock_id,))
            news_detail = _row_to_dict(cur.fetchone())

        result["l2_sub"] = l2
        result["l2_news_detail"] = news_detail

        # ── L3 서브스코어 (기술적 지표) ──
        with get_cursor() as cur:
            cur.execute("""
                SELECT rsi_14, macd_signal, bb_position,
                       adx_14, obv_trend,
                       COALESCE(layer3_total_score, layer3_technical_score) as l3_total,
                       trend_score, momentum_score as tech_momentum,
                       volume_score, volatility_score, pattern_score
                FROM technical_indicators
                WHERE stock_id = %s ORDER BY calc_date DESC LIMIT 1
            """, (stock_id,))
            l3 = _row_to_dict(cur.fetchone())

        result["l3_sub"] = l3

        # ── Final Scores ──
        with get_cursor() as cur:
            cur.execute("""
                SELECT layer1_score, layer2_score, layer3_score,
                       weighted_score, grade, signal
                FROM stock_final_scores
                WHERE stock_id = %s AND calc_date = %s
            """, (stock_id, calc_date))
            final = _row_to_dict(cur.fetchone())

        l1 = _safe_float(final.get("layer1_score"), 50)
        l2_score = _safe_float(final.get("layer2_score"), 50)
        l3_score = _safe_float(final.get("layer3_score"), 50)
        result["l1_score"] = l1
        result["l2_score"] = l2_score
        result["l3_score"] = l3_score

        # ── Conviction Level (설계서 기준) ──
        dc = 1.0  # data completeness
        if l1 >= 80 and (l2_score >= 70 or l3_score >= 70) and dc >= 1.0:
            conviction = "HIGH"
        elif result.get("score", 0) >= 72 and l1 >= 65:
            conviction = "MEDIUM"
        else:
            conviction = "LOW"
        result["conviction"] = conviction

        # ── Because... 근거 자동 생성 (Bridgewater 방식) ──
        because = _build_because(l1, l2_score, l3_score, moat, value, 
                                 momentum, stability, l2, l3, news_detail)
        result["because"] = because

        # ── 섹터 집중도 체크 ──
        sector = result.get("sector", "")
        if sector:
            with get_cursor() as cur:
                cur.execute("""
                    SELECT SUM(pp2.shares * pp2.entry_price) as sector_val
                    FROM portfolio_positions pp2
                    WHERE pp2.status = 'OPEN' AND pp2.portfolio_id = 1
                      AND pp2.stock_id IN (
                          SELECT s2.stock_id FROM stocks s2 
                          JOIN sectors sec2 ON s2.sector_id = sec2.sector_id 
                          WHERE sec2.sector_code = %s
                      )
                """, (sector,))
                row = cur.fetchone()
                sector_val = float(row["sector_val"] or 0) if row else 0

                cur.execute("""
                    SELECT total_value FROM portfolio_daily_snapshot
                    WHERE portfolio_id = 1 ORDER BY snapshot_date DESC LIMIT 1
                """)
                total_row = cur.fetchone()
                total_val = float(total_row["total_value"] or 1) if total_row else 1

            sector_pct = (sector_val / total_val * 100) if total_val > 0 else 0
            result["sector_concentration"] = {
                "sector": sector, "pct": round(sector_pct, 1),
                "limit": 35, "warning": sector_pct > 30,
            }

        # ── 포폴 내 상관관계 체크 (상위 1개) ──
        result["correlation_warning"] = _check_correlation(stock_id, ticker)

        # ── 어닝 임박 체크 ──
        with get_cursor() as cur:
            cur.execute("""
                SELECT report_date, timing FROM earnings_calendar
                WHERE stock_id = %s AND report_date >= %s AND report_date <= %s + 21
                ORDER BY report_date LIMIT 1
            """, (stock_id, calc_date, calc_date))
            earnings = cur.fetchone()
        if earnings:
            days_until = (earnings["report_date"] - calc_date).days
            result["earnings_nearby"] = {
                "date": str(earnings["report_date"]),
                "days_until": days_until,
                "timing": earnings.get("timing", ""),
                "warning": days_until <= 7,
            }

        # ── R:R 비율 ──
        price = result.get("price", 0)
        stop = result.get("stop_loss", 0)
        if price > 0 and stop > 0:
            risk = price - stop
            # 목표가: ATR 기반 또는 등급별 기대수익
            target_pct = {"S": 15, "A+": 12, "A": 10, "B+": 8, "B": 6}.get(
                result.get("grade", "B"), 7)
            target_price = price * (1 + target_pct / 100)
            reward = target_price - price
            rr = round(reward / risk, 1) if risk > 0 else 0
            result["target_price"] = round(target_price, 2)
            result["rr_ratio"] = rr

    except Exception as e:
        logger.warning(f"[BUY-RATIONALE] {ticker} 보강 실패: {e}")

    return result


def _build_because(l1, l2, l3, moat, value, momentum, stability, l2_sub, l3_sub, news):
    """Bridgewater Because... 투자 근거 자동 생성"""
    reasons = []

    # L1 퀀트 근거
    if l1 >= 70:
        sub_reasons = []
        if _safe_float(moat.get("roic_score")) >= 20:
            sub_reasons.append("높은 ROIC")
        if _safe_float(moat.get("fcf_margin_score")) >= 12:
            sub_reasons.append("강한 FCF")
        if _safe_float(value.get("earnings_yield_score")) >= 20:
            sub_reasons.append("매력적 밸류에이션")
        if _safe_float(momentum.get("earnings_surprise_score")) >= 20:
            sub_reasons.append("실적 서프라이즈")
        if _safe_float(stability.get("dividend_score")) >= 8:
            sub_reasons.append("배당 안정성")
        detail = ", ".join(sub_reasons[:3]) if sub_reasons else "종합 양호"
        reasons.append(f"▸ L1 퀀트 우수: {detail}")

    # L2 NLP 근거
    if l2 >= 65:
        sub_reasons = []
        sentiment = _safe_float(news.get("avg_sentiment_score"), 0)
        if sentiment > 0.3:
            sub_reasons.append(f"뉴스 감성 긍정({sentiment:+.2f})")
        if _safe_float(l2_sub.get("analyst_rating_score")) >= 65:
            sub_reasons.append("애널리스트 매수 우위")
        if _safe_float(l2_sub.get("insider_signal_score")) >= 60:
            sub_reasons.append("내부자 매수 신호")
        detail = ", ".join(sub_reasons[:2]) if sub_reasons else "NLP 긍정"
        reasons.append(f"▸ L2 NLP 긍정: {detail}")

    # L3 기술 근거
    if l3 >= 65:
        sub_reasons = []
        rsi = _safe_float(l3_sub.get("rsi_14"), 50)
        if 40 <= rsi <= 70:
            sub_reasons.append(f"RSI {rsi:.0f} 적정")
        if _safe_float(l3_sub.get("trend_score")) >= 15:
            sub_reasons.append("상승 추세")
        if _safe_float(l3_sub.get("tech_momentum")) >= 15:
            sub_reasons.append("모멘텀 강세")
        detail = ", ".join(sub_reasons[:2]) if sub_reasons else "기술적 양호"
        reasons.append(f"▸ L3 기술 양호: {detail}")

    # 약점 (Devil's Advocate)
    weaknesses = []
    if l1 < 50:
        weaknesses.append("L1 퀀트 부진")
    if l2 < 45:
        weaknesses.append("L2 NLP 부정적")
    if l3 < 45:
        weaknesses.append("L3 기술적 약세")
    if weaknesses:
        reasons.append(f"⚠️ 리스크: {', '.join(weaknesses)}")

    if not reasons:
        reasons.append("▸ 종합 점수 기준 매수 조건 충족")

    return reasons


def _check_correlation(stock_id: int, ticker: str) -> Optional[dict]:
    """포폴 내 보유 종목과의 상관관계 체크"""
    try:
        with get_cursor() as cur:
            # 현재 보유 종목 조회
            cur.execute("""
                SELECT pp.stock_id, s.ticker
                FROM portfolio_positions pp
                JOIN stocks s ON pp.stock_id = s.stock_id
                WHERE pp.status = 'OPEN' AND pp.portfolio_id = 1
                LIMIT 20
            """)
            positions = cur.fetchall()

        if not positions:
            return None

        # 최근 60일 가격으로 상관 계산
        target_prices = _get_prices(stock_id, 60)
        if len(target_prices) < 30:
            return None

        max_corr = 0
        max_ticker = ""
        for pos in positions:
            if pos["stock_id"] == stock_id:
                continue
            other_prices = _get_prices(pos["stock_id"], 60)
            if len(other_prices) < 30:
                continue

            # align by length
            min_len = min(len(target_prices), len(other_prices))
            t_ret = np.diff(np.log(target_prices[:min_len]))
            o_ret = np.diff(np.log(other_prices[:min_len]))

            if len(t_ret) > 10 and len(o_ret) > 10:
                corr = float(np.corrcoef(t_ret[:len(o_ret)], o_ret[:len(t_ret)])[0, 1])
                if abs(corr) > abs(max_corr):
                    max_corr = corr
                    max_ticker = pos["ticker"]

        if abs(max_corr) > 0.7:
            return {"ticker": max_ticker, "correlation": round(max_corr, 2),
                    "warning": True}
        return None

    except Exception:
        return None


# ═══════════════════════════════════════════════════════════
#  2. SELL — MAE/MFE + 점수 변화 + 역대 성과
# ═══════════════════════════════════════════════════════════

def build_sell_analysis(stock_id: int, ticker: str, calc_date: date,
                        base_signal: dict) -> dict:
    """
    매도 시그널에 v4 분석 데이터 보강.
    
    추가:
      - MAE/MFE (Maximum Adverse/Favorable Excursion)
      - 매입 시 점수 vs 현재 점수 추적
      - 역대 같은 사유 매도의 성과 통계
    """
    result = dict(base_signal)

    try:
        entry_price = result.get("entry_price", 0)
        current_price = result.get("price", 0)

        # ── MAE/MFE 계산 ──
        with get_cursor() as cur:
            # 포지션 매입일 조회
            cur.execute("""
                SELECT entry_date, entry_price, highest_price, lowest_price
                FROM portfolio_positions
                WHERE stock_id = %s AND portfolio_id = 1
                ORDER BY entry_date DESC LIMIT 1
            """, (stock_id,))
            pos = cur.fetchone()

        if pos:
            ep = float(pos["entry_price"] or entry_price)
            highest = float(pos["highest_price"] or current_price)
            lowest = float(pos["lowest_price"] or current_price)

            mfe = ((highest - ep) / ep * 100) if ep > 0 else 0
            mae = ((lowest - ep) / ep * 100) if ep > 0 else 0
            from_high = ((current_price - highest) / highest * 100) if highest > 0 else 0
            missed_profit = (highest - current_price) * result.get("shares", 0) if highest > current_price else 0

            result["mfe"] = round(mfe, 1)
            result["mae"] = round(mae, 1)
            result["from_high_pct"] = round(from_high, 1)
            result["missed_profit"] = round(missed_profit, 2)
            result["highest_price"] = highest
            result["lowest_price"] = lowest

        # ── 매입 시 점수 vs 현재 점수 ──
        if pos and pos.get("entry_date"):
            entry_date = pos["entry_date"]
            with get_cursor() as cur:
                # 매입일 점수
                cur.execute("""
                    SELECT weighted_score, grade, layer1_score, layer2_score, layer3_score
                    FROM stock_final_scores
                    WHERE stock_id = %s AND calc_date <= %s
                    ORDER BY calc_date DESC LIMIT 1
                """, (stock_id, entry_date))
                entry_scores = _row_to_dict(cur.fetchone())

                # 현재 점수
                cur.execute("""
                    SELECT weighted_score, grade, layer1_score, layer2_score, layer3_score
                    FROM stock_final_scores
                    WHERE stock_id = %s ORDER BY calc_date DESC LIMIT 1
                """, (stock_id,))
                current_scores = _row_to_dict(cur.fetchone())

            if entry_scores and current_scores:
                result["entry_score"] = _safe_float(entry_scores.get("weighted_score"))
                result["entry_grade"] = entry_scores.get("grade", "?")
                result["current_score"] = _safe_float(current_scores.get("weighted_score"))
                result["current_grade"] = current_scores.get("grade", "?")
                result["entry_l1"] = _safe_float(entry_scores.get("layer1_score"))
                result["entry_l2"] = _safe_float(entry_scores.get("layer2_score"))
                result["entry_l3"] = _safe_float(entry_scores.get("layer3_score"))
                result["current_l1"] = _safe_float(current_scores.get("layer1_score"))
                result["current_l2"] = _safe_float(current_scores.get("layer2_score"))
                result["current_l3"] = _safe_float(current_scores.get("layer3_score"))

        # ── 역대 같은 사유 매도 성과 (Devil's Advocate) ──
        reason = result.get("reason", "")
        if reason:
            result["historical_reason_stats"] = _calc_historical_reason_stats(reason)

    except Exception as e:
        logger.warning(f"[SELL-ANALYSIS] {ticker} 보강 실패: {e}")

    return result


def _calc_historical_reason_stats(reason: str) -> dict:
    """역대 같은 사유로 매도한 건의 사후 성과"""
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT ts.stock_id, ts.current_price AS sell_price, ts.signal_date AS sell_date
                FROM trading_signals ts
                WHERE ts.reason = %s
                  AND ts.signal_type IN ('SELL', 'STOP_LOSS', 'PROFIT_TAKE')
                  AND ts.signal_date >= CURRENT_DATE - INTERVAL '180 days'
                ORDER BY ts.signal_date DESC LIMIT 30
            """, (reason,))
            sells = cur.fetchall()

        if len(sells) < 3:
            return {}

        correct = 0
        total = 0
        additional_drops = []

        for s in sells:
            with get_cursor() as cur:
                cur.execute("""
                    SELECT close_price FROM stock_prices_daily
                    WHERE stock_id = %s AND trade_date > %s
                    ORDER BY trade_date LIMIT 1 OFFSET 4
                """, (s["stock_id"], s["sell_date"]))
                row = cur.fetchone()

            if row:
                price_5d = float(row["close_price"])
                sell_price = float(s["sell_price"])
                change = (price_5d - sell_price) / sell_price * 100
                additional_drops.append(change)
                total += 1
                if change < 0:  # 매도 후 더 하락 = 올바른 판단
                    correct += 1

        if total == 0:
            return {}

        return {
            "total_cases": total,
            "correct_pct": round(correct / total * 100, 0),
            "correct_count": correct,
            "avg_5d_change": round(np.mean(additional_drops), 1) if additional_drops else 0,
        }

    except Exception:
        return {}


# ═══════════════════════════════════════════════════════════
#  3. MORNING — Grinold IC + Hit Rate + 국면 확률
# ═══════════════════════════════════════════════════════════

def calc_signal_ic(lookback_days: int = 30, forward_days: int = 5) -> dict:
    """
    Grinold-Kahn Information Coefficient
    시그널 점수와 실제 수익률의 Spearman 상관.
    레이어별(L1/L2/L3) + 종합.
    """
    from scipy import stats as sp_stats

    result = {"ic": 0, "ic_trend": 0, "l1_ic": 0, "l2_ic": 0, "l3_ic": 0}

    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT f.weighted_score, f.layer1_score, f.layer2_score, f.layer3_score,
                       f.calc_date, f.stock_id,
                       (SELECT close_price FROM stock_prices_daily
                        WHERE stock_id = f.stock_id AND trade_date >= f.calc_date
                        ORDER BY trade_date LIMIT 1) AS price_t0,
                       (SELECT close_price FROM stock_prices_daily
                        WHERE stock_id = f.stock_id AND trade_date >= f.calc_date + %s
                        ORDER BY trade_date LIMIT 1) AS price_t5
                FROM stock_final_scores f
                WHERE f.calc_date >= CURRENT_DATE - %s
                  AND f.weighted_score IS NOT NULL
            """, (forward_days, lookback_days))
            rows = cur.fetchall()

        scores, returns = [], []
        l1_scores, l2_scores, l3_scores = [], [], []

        for r in rows:
            p0 = float(r["price_t0"]) if r["price_t0"] else None
            p5 = float(r["price_t5"]) if r["price_t5"] else None
            if p0 and p5 and p0 > 0:
                fwd_ret = (p5 - p0) / p0
                scores.append(float(r["weighted_score"]))
                returns.append(fwd_ret)
                if r["layer1_score"]:
                    l1_scores.append((float(r["layer1_score"]), fwd_ret))
                if r["layer2_score"]:
                    l2_scores.append((float(r["layer2_score"]), fwd_ret))
                if r["layer3_score"]:
                    l3_scores.append((float(r["layer3_score"]), fwd_ret))

        if len(scores) >= 20:
            ic, _ = sp_stats.spearmanr(scores, returns)
            result["ic"] = round(float(ic), 4)

        # 레이어별 IC
        for name, data in [("l1_ic", l1_scores), ("l2_ic", l2_scores), ("l3_ic", l3_scores)]:
            if len(data) >= 20:
                s, r = zip(*data)
                ic_val, _ = sp_stats.spearmanr(s, r)
                result[name] = round(float(ic_val), 4)

        # IC 추이 (현재 vs 2주 전)
        if len(scores) >= 40:
            half = len(scores) // 2
            ic_recent, _ = sp_stats.spearmanr(scores[half:], returns[half:])
            ic_old, _ = sp_stats.spearmanr(scores[:half], returns[:half])
            result["ic_trend"] = round(float(ic_recent) - float(ic_old), 4)

    except ImportError:
        logger.warning("[IC] scipy 없음 - IC 계산 스킵")
    except Exception as e:
        logger.warning(f"[IC] 계산 실패: {e}")

    return result


def calc_hit_rate(lookback_count: int = 50, forward_days: int = 5) -> dict:
    """
    최근 N건 BUY 시그널의 적중률 (5일 후 양수 수익 비율)
    """
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT ts.stock_id, ts.current_price AS signal_price, ts.signal_date,
                       (SELECT close_price FROM stock_prices_daily
                        WHERE stock_id = ts.stock_id 
                          AND trade_date >= ts.signal_date + %s
                        ORDER BY trade_date LIMIT 1) AS price_5d
                FROM trading_signals ts
                WHERE ts.signal_type = 'BUY'
                ORDER BY ts.signal_date DESC
                LIMIT %s
            """, (forward_days, lookback_count))
            rows = cur.fetchall()

        hits, total = 0, 0
        for r in rows:
            if r["price_5d"] and r["signal_price"]:
                total += 1
                if float(r["price_5d"]) > float(r["signal_price"]):
                    hits += 1

        return {
            "hit_rate": round(hits / total, 3) if total > 0 else 0,
            "hits": hits, "total": total,
        }
    except Exception as e:
        logger.warning(f"[HIT-RATE] 계산 실패: {e}")
        return {"hit_rate": 0, "hits": 0, "total": 0}


def calc_regime_probability() -> dict:
    """
    현재 국면 지속 확률 추정.
    연속일수 / 평균 지속일수 기반.
    """
    try:
        with get_cursor() as cur:
            # 최근 120일 국면 이력
            cur.execute("""
                SELECT regime_date, regime FROM market_regime
                ORDER BY regime_date DESC LIMIT 120
            """)
            rows = cur.fetchall()

        if not rows:
            return {"stay_probability": 0.5, "days_in_regime": 0}

        current_regime = rows[0]["regime"]

        # 현재 국면 연속일수
        days_in = 0
        for r in rows:
            if r["regime"] == current_regime:
                days_in += 1
            else:
                break

        # 과거 평균 지속일수
        segments = []
        seg_len = 0
        prev = rows[0]["regime"]
        for r in rows:
            if r["regime"] == prev:
                seg_len += 1
            else:
                segments.append(seg_len)
                seg_len = 1
                prev = r["regime"]
        segments.append(seg_len)

        avg_duration = np.mean(segments) if segments else 14

        # 지속 확률 = 1 - (days_in / avg_duration), capped
        stay_prob = max(0.2, min(0.95, 1.0 - (days_in / (avg_duration * 2))))

        return {
            "stay_probability": round(stay_prob, 2),
            "days_in_regime": days_in,
            "avg_duration": round(avg_duration, 0),
            "current_regime": current_regime,
        }
    except Exception as e:
        logger.warning(f"[REGIME-PROB] 계산 실패: {e}")
        return {"stay_probability": 0.5, "days_in_regime": 0}


# ═══════════════════════════════════════════════════════════
#  4. RISK — Historical VaR + Stress Test + 집중도 + 상관
# ═══════════════════════════════════════════════════════════

def build_risk_dashboard(calc_date: date) -> dict:
    """
    리스크 대시보드 전체 데이터 계산.
    - Drawdown: 현재/MDD
    - Historical VaR: 95%/99%
    - Stress Test: COVID/금리/VIX
    - 집중도: 섹터/종목
    - 상관관계: 포폴 평균
    - 방어 상태: DD Controller/CB
    """
    risk = {}

    # ── Drawdown ──
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT total_value, snapshot_date
                FROM portfolio_daily_snapshot
                WHERE portfolio_id = 1
                ORDER BY snapshot_date DESC LIMIT 252
            """)
            snaps = cur.fetchall()

        if snaps:
            values = [float(s["total_value"]) for s in snaps]
            peak = max(values)
            current = values[0]
            current_dd = ((current - peak) / peak * 100) if peak > 0 else 0

            # MDD
            running_max = values[0]
            mdd = 0
            for v in values:
                running_max = max(running_max, v)
                dd = (v - running_max) / running_max * 100
                mdd = min(mdd, dd)

            # DD 경과일
            dd_days = 0
            for v in values:
                if v < peak:
                    dd_days += 1
                else:
                    break

            risk["drawdown"] = {
                "current_dd": round(current_dd, 1),
                "mdd": round(mdd, 1),
                "dd_days": dd_days,
                "peak_value": peak,
            }

            # ── Historical VaR ──
            if len(values) >= 30:
                returns = np.diff(np.array(values)) / np.array(values[:-1])
                var_95 = float(np.percentile(returns, 5))
                var_99 = float(np.percentile(returns, 1))
                risk["var"] = {
                    "var_95_pct": round(var_95 * 100, 1),
                    "var_99_pct": round(var_99 * 100, 1),
                    "var_95_dollar": round(abs(var_95 * current), 0),
                    "var_99_dollar": round(abs(var_99 * current), 0),
                }
    except Exception as e:
        logger.warning(f"[RISK] DD/VaR 실패: {e}")

    # ── Stress Test ──
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT pp.stock_id,
                       (pp.shares * COALESCE(
                           (SELECT close_price FROM stock_prices_daily 
                            WHERE stock_id = pp.stock_id 
                            ORDER BY trade_date DESC LIMIT 1),
                           pp.entry_price
                       )) AS market_value,
                       s.ticker,
                       COALESCE(sec.sector_code, 'Other') AS sector
                FROM portfolio_positions pp
                JOIN stocks s ON pp.stock_id = s.stock_id
                LEFT JOIN sectors sec ON s.sector_id = sec.sector_id
                WHERE pp.status = 'OPEN' AND pp.portfolio_id = 1
            """)
            positions = cur.fetchall()

        if positions:
            total_val = sum(float(p["market_value"] or 0) for p in positions)

            # 시나리오별 섹터 충격 (히스토리컬 기반 근사값)
            scenarios = {
                "2020 COVID": {"Technology": -0.25, "Financials": -0.35, "Healthcare": -0.10,
                               "Energy": -0.50, "Consumer": -0.30, "_default": -0.30},
                "2022 금리 인상": {"Technology": -0.25, "Financials": -0.05, "Utilities": -0.15,
                                    "Real Estate": -0.25, "_default": -0.15},
                "VIX 급등": {"Technology": -0.08, "Financials": -0.06, "_default": -0.05},
            }

            stress_results = {}
            for scenario_name, shocks in scenarios.items():
                scenario_loss = 0
                for pos in positions:
                    sector = pos.get("sector", "")
                    shock = shocks.get(sector, shocks.get("_default", -0.10))
                    mv = float(pos["market_value"] or 0)
                    scenario_loss += mv * shock

                impact_pct = (scenario_loss / total_val * 100) if total_val > 0 else 0
                stress_results[scenario_name] = {
                    "impact_pct": round(impact_pct, 1),
                    "impact_dollar": round(abs(scenario_loss), 0),
                }

            risk["stress_test"] = stress_results

        # ── 집중도 ──
        if positions:
            sector_vals = defaultdict(float)
            for p in positions:
                sector_vals[p.get("sector", "Other")] += float(p["market_value"] or 0)

            top_sector = max(sector_vals.items(), key=lambda x: x[1]) if sector_vals else ("", 0)
            top_stock = max(positions, key=lambda p: float(p["market_value"] or 0))

            risk["concentration"] = {
                "top_sector": {
                    "name": top_sector[0],
                    "pct": round(top_sector[1] / total_val * 100, 1) if total_val > 0 else 0,
                    "limit": 35,
                },
                "top_stock": {
                    "ticker": top_stock["ticker"],
                    "pct": round(float(top_stock["market_value"] or 0) / total_val * 100, 1) if total_val > 0 else 0,
                    "limit": 10,
                },
            }

        # ── 포폴 평균 상관관계 ──
        if positions and len(positions) >= 2:
            corr_result = _calc_portfolio_correlation([p["stock_id"] for p in positions[:15]])
            if corr_result:
                risk["correlation"] = corr_result

    except Exception as e:
        logger.warning(f"[RISK] Stress/집중도 실패: {e}")

    # ── 방어 상태 조회 ──
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT dd_mode, cb_active, buy_limit_pct
                FROM defense_status
                WHERE portfolio_id = 1
                ORDER BY updated_at DESC LIMIT 1
            """)
            defense = cur.fetchone()

        if defense:
            risk["defense"] = {
                "dd_mode": defense.get("dd_mode", "NORMAL"),
                "cb_active": bool(defense.get("cb_active", False)),
                "buy_limit_pct": float(defense.get("buy_limit_pct") or 100),
            }
    except Exception:
        risk["defense"] = {"dd_mode": "NORMAL", "cb_active": False}

    # ── 리스크 레벨 판단 ──
    dd_val = abs(risk.get("drawdown", {}).get("current_dd", 0))
    if dd_val >= 15 or risk.get("defense", {}).get("cb_active"):
        risk["risk_level"] = "RED"
    elif dd_val >= 8 or risk.get("defense", {}).get("dd_mode") == "CAUTION":
        risk["risk_level"] = "ORANGE"
    elif dd_val >= 3:
        risk["risk_level"] = "YELLOW"
    else:
        risk["risk_level"] = "GREEN"

    return risk


def _calc_portfolio_correlation(stock_ids: list, days: int = 60) -> Optional[dict]:
    """포폴 내 종목 간 평균 상관관계"""
    try:
        price_matrix = {}
        for sid in stock_ids:
            prices = _get_prices(sid, days)
            if len(prices) >= 30:
                price_matrix[sid] = np.diff(np.log(np.array(prices)))

        if len(price_matrix) < 2:
            return None

        keys = list(price_matrix.keys())
        correlations = []
        max_corr = 0
        max_pair = ""

        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                r1 = price_matrix[keys[i]]
                r2 = price_matrix[keys[j]]
                min_len = min(len(r1), len(r2))
                if min_len > 10:
                    corr = float(np.corrcoef(r1[:min_len], r2[:min_len])[0, 1])
                    if not np.isnan(corr):
                        correlations.append(abs(corr))
                        if abs(corr) > abs(max_corr):
                            max_corr = corr

        if not correlations:
            return None

        return {
            "avg_correlation": round(float(np.mean(correlations)), 2),
            "max_correlation": round(max_corr, 2),
        }
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════
#  5. WEEKLY — Brinson Attribution + 국면별 성과
# ═══════════════════════════════════════════════════════════

def build_weekly_brinson(calc_date: date) -> dict:
    """
    Brinson Attribution: 주간 수익을 시장(β) + 종목선택(α) + 현금 분해.
    """
    result = {
        "week_return": 0, "mtd_return": 0, "ytd_return": 0,
        "since_inception": 0, "sharpe": 0, "sortino": 0,
        "alpha": 0, "beta": 0, "win_rate": 0, "num_trades": 0,
        "best_ticker": "", "best_pnl": 0,
        "worst_ticker": "", "worst_pnl": 0,
        "brinson": {},
    }

    try:
        with get_cursor() as cur:
            # 최근 스냅샷 (252일)
            cur.execute("""
                SELECT snapshot_date, total_value, daily_return_pct
                FROM portfolio_daily_snapshot
                WHERE portfolio_id = 1
                ORDER BY snapshot_date DESC LIMIT 252
            """)
            snaps = cur.fetchall()

        if len(snaps) < 5:
            return result

        # 수익률 계산
        values = [float(s["total_value"]) for s in snaps]
        returns = [float(s["daily_return_pct"] or 0) / 100 for s in snaps]

        # 주간/월간/연간
        if len(values) >= 5:
            result["week_return"] = round((values[0] / values[4] - 1) * 100, 2)
        if len(values) >= 21:
            result["mtd_return"] = round((values[0] / values[20] - 1) * 100, 2)
        if len(values) >= 252:
            result["ytd_return"] = round((values[0] / values[-1] - 1) * 100, 2)

        # Sharpe / Sortino (연환산)
        if len(returns) >= 30:
            ret_arr = np.array(returns[:252])
            avg_ret = np.mean(ret_arr)
            std_ret = np.std(ret_arr)
            result["sharpe"] = round(float(avg_ret / std_ret * np.sqrt(252)), 2) if std_ret > 0 else 0

            downside = ret_arr[ret_arr < 0]
            down_std = np.std(downside) if len(downside) > 5 else std_ret
            result["sortino"] = round(float(avg_ret / down_std * np.sqrt(252)), 2) if down_std > 0 else 0

        # Alpha / Beta (vs SPY)
        try:
            with get_cursor() as cur:
                cur.execute("""
                    SELECT close_price FROM stock_prices_daily
                    WHERE stock_id = (SELECT stock_id FROM stocks WHERE ticker = 'SPY' LIMIT 1)
                    ORDER BY trade_date DESC LIMIT 252
                """)
                spy_prices = [float(r["close_price"]) for r in cur.fetchall()]

            if len(spy_prices) >= 30:
                spy_ret = np.diff(np.array(spy_prices[::-1])) / np.array(spy_prices[::-1][:-1])
                port_ret = np.array(returns[:len(spy_ret)])

                if len(port_ret) >= 30 and len(spy_ret) >= 30:
                    min_len = min(len(port_ret), len(spy_ret))
                    beta = float(np.cov(port_ret[:min_len], spy_ret[:min_len])[0, 1] / np.var(spy_ret[:min_len]))
                    alpha = float(np.mean(port_ret[:min_len]) - beta * np.mean(spy_ret[:min_len])) * 252 * 100
                    result["beta"] = round(beta, 2)
                    result["alpha"] = round(alpha, 2)
        except Exception:
            pass

        # 승률 + 거래 수 (주간)
        week_ago = calc_date - timedelta(days=7)
        with get_cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FILTER (WHERE pnl_pct > 0) AS wins,
                       COUNT(*) AS total
                FROM trading_signals
                WHERE calc_date >= %s AND signal_type IN ('SELL', 'PROFIT_TAKE', 'STOP_LOSS')
            """, (week_ago,))
            trade_stats = cur.fetchone()

        if trade_stats and trade_stats["total"] > 0:
            result["win_rate"] = round(trade_stats["wins"] / trade_stats["total"] * 100, 1)
            result["num_trades"] = trade_stats["total"]

        # Best / Worst
        with get_cursor() as cur:
            cur.execute("""
                SELECT s.ticker, ts.final_score
                FROM trading_signals ts JOIN stocks s ON ts.stock_id = s.stock_id
                WHERE ts.signal_date >= %s AND ts.final_score IS NOT NULL
                ORDER BY ts.final_score DESC LIMIT 1
            """, (week_ago,))
            best = cur.fetchone()
            if best:
                result["best_ticker"] = best["ticker"]
                result["best_pnl"] = round(float(best["pnl_pct"]), 1)

            cur.execute("""
                SELECT s.ticker, ts.final_score
                FROM trading_signals ts JOIN stocks s ON ts.stock_id = s.stock_id
                WHERE ts.signal_date >= %s AND ts.final_score IS NOT NULL
                ORDER BY ts.final_score ASC LIMIT 1
            """, (week_ago,))
            worst = cur.fetchone()
            if worst:
                result["worst_ticker"] = worst["ticker"]
                result["worst_pnl"] = round(float(worst["pnl_pct"]), 1)

        # ── Brinson Attribution ──
        # 수익 = 시장효과(β) + 종목선택(α) + 현금드래그
        if result["beta"] and result.get("week_return"):
            spy_week = 0
            if len(spy_prices) >= 5:
                spy_week = (spy_prices[0] / spy_prices[4] - 1) * 100 if spy_prices[4] > 0 else 0

            market_effect = round(result["beta"] * spy_week, 2)
            total_ret = result["week_return"]

            # 현금 비율에 따른 드래그
            try:
                with get_cursor() as cur:
                    cur.execute("""
                        SELECT cash_balance, total_value
                        FROM portfolio_daily_snapshot
                        WHERE portfolio_id = 1 ORDER BY snapshot_date DESC LIMIT 1
                    """)
                    snap = cur.fetchone()
                cash_pct = float(snap["cash_balance"]) / float(snap["total_value"]) * 100 if snap else 0
            except Exception:
                cash_pct = 0

            cash_drag = round(-cash_pct / 100 * spy_week, 2) if spy_week > 0 else 0
            selection = round(total_ret - market_effect - cash_drag, 2)

            result["brinson"] = {
                "market_effect": market_effect,
                "selection_effect": selection,
                "cash_drag": cash_drag,
                "spy_return": round(spy_week, 2),
            }

    except Exception as e:
        logger.warning(f"[WEEKLY] 계산 실패: {e}")

    return result


# ═══════════════════════════════════════════════════════════
#  6. Fear & Greed 조회
# ═══════════════════════════════════════════════════════════

def get_fear_greed() -> Optional[dict]:
    """DB에서 최신 Fear & Greed 값 조회"""
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT fg_value, fg_label FROM fear_greed_index
                ORDER BY calc_date DESC LIMIT 1
            """)
            row = cur.fetchone()
        if row:
            return {"value": int(row["fg_value"]), "label": row["fg_label"]}
    except Exception:
        pass
    return None


# ═══════════════════════════════════════════════════════════
#  유틸
# ═══════════════════════════════════════════════════════════

def _row_to_dict(row) -> dict:
    if row is None:
        return {}
    return dict(row)


def _safe_float(val, default=0.0) -> float:
    if val is None:
        return default
    try:
        f = float(val)
        return f if not (math.isnan(f) or math.isinf(f)) else default
    except (ValueError, TypeError):
        return default


def _get_prices(stock_id: int, days: int = 60) -> list:
    """최근 N일 종가 리스트 (최신→과거)"""
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT close_price FROM stock_prices_daily
                WHERE stock_id = %s ORDER BY trade_date DESC LIMIT %s
            """, (stock_id, days))
            return [float(r["close_price"]) for r in cur.fetchall() if r["close_price"]]
    except Exception:
        return []
