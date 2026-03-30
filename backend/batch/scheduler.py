"""
scheduler.py — QUANT AI v5.0 (v4.0 + DQ Gate + Ensemble + Regime + AutoPilot)
=====================================================
v4.0 변경 (v3.4 → v4.0):
  - APScheduler 자체 cron 탑재: 평일 ET 20:30 (애프터마켓 20:00 + 30분)
  - main.py에서 모닝 브리핑 스케줄 제거 → 배치 Step 8에서 통합
  - _s_weekly/_s_monthly → notifier 시그니처 정합성 수정
  - 모든 notify 호출은 _s_notify_all() 한 곳에서만 발생

타임라인:
  미국 정규장 마감  ET 16:00
  애프터마켓 마감   ET 20:00
  배치 시작         ET 20:30 (KST 09:30) ← 여기서 run_all()
  배치 완료         약 ET 21:00~21:30
  Step 8            → 디코 일괄 알림 (배치 끝나자마자)

실행 방법:
  1) standalone: python -m batch.scheduler          (APScheduler 대기)
  2) 수동:       python -m batch.scheduler --now     (즉시 1회 실행)
  3) 날짜 지정:  python -m batch.scheduler --date 2026-03-25
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from datetime import datetime, date, timedelta
import traceback


# ═══════════════════════════════════════════════════════════
#  배치 파이프라인 메인
# ═══════════════════════════════════════════════════════════

def run_all(calc_date: date = None):
    """
    QUANT AI v5.0 일일 배치.
    
    v4.0 대비 추가:
      Step 0:   Data Quality Gate (데이터 품질 관문)
      Step 5.3: Options Flow (IV/Skew/Put-Call 실데이터)
      Step 5.5: Macro Regime HMM (6-State 국면 분류)
      Step 6.3: Stacking Ensemble (기존 XGBoost → 3-Model)
      Step 7.5: AutoPilot (자가진화 엔진)
    """
    if calc_date is None:
        calc_date = datetime.now().date()
    start_all = datetime.now()
    results = {}
    print(f"\n{'='*60}\n  QUANT AI v5.0 일일 배치 — {calc_date}\n{'='*60}")

    # ══════════ PHASE 1: 데이터 품질 + 수집 ══════════

    results["0_dq"]      = _run_step("0/16 Data Quality Gate",  lambda: _s_dq_gate(calc_date))
    results["1_price"]   = _run_step("1/16 가격 수집",          lambda: _s_price(calc_date))
    results["2_fin"]     = _run_step("2/16 파생 재무",          lambda: _s_fin())
    results["3_l1"]      = _run_step("3/16 Layer 1",            lambda: _s_l1(calc_date))
    results["4_l3"]      = _run_step("4/16 Layer 3",            lambda: _s_l3(calc_date))
    results["4.5_pat"]   = _run_step("4.5 차트패턴",            lambda: _s_chart_patterns(calc_date))
    results["4.6_fg"]    = _run_step("4.6 Fear & Greed",        lambda: _s_fear_greed(calc_date))
    results["4.7_pc"]    = _run_step("4.7 Put/Call Ratio",      lambda: _s_put_call(calc_date))
    results["4.8_ca"]    = _run_step("4.8 Cross-Asset",         lambda: _s_cross_asset(calc_date))
    results["5_l2"]      = _run_step("5/16 Layer 2",            lambda: _s_l2())

    if _should_earnings(calc_date):
        results["5.1_ec"] = _run_step("5.1 어닝콜",             lambda: _s_ec(calc_date))
    else:
        results["5.1_ec"] = "SKIP"

    # ══════════ PHASE 2: 선행지표 + 매크로 ══════════

    results["5.3_options"] = _run_step("5.3 Options Flow",       lambda: _s_options(calc_date))
    results["5.5_regime"]  = _run_step("5.5 Macro Regime",       lambda: _s_regime(calc_date))

    # ══════════ PHASE 3: 합산 + ML + 앙상블 ══════════

    results["6_final"]   = _run_step("6/16 최종 합산",          lambda: _s_final(calc_date))
    results["6.3_ens"]   = _run_step("6.3 Stacking Ensemble",   lambda: _s_ensemble(calc_date))
    results["6.5_ic"]    = _run_step("6.5 IC Guard v2",         lambda: _s_factor_monitor(calc_date))
    results["6.7_decay"] = _run_step("6.7 Alpha Decay",         lambda: _s_alpha_decay(calc_date))

    # ══════════ PHASE 4: 시그널 ══════════

    results["7_trading"] = _run_step("7/16 Trading Signals",    lambda: _s_trading(calc_date))

    # ══════════ PHASE 5: 자가진화 ══════════

    results["7.5_pilot"] = _run_step("7.5 AutoPilot",           lambda: _s_auto_pilot(calc_date))

    # ══════════ PHASE 6: 알림 ══════════

    results["8_notify"]  = _run_step("8/16 일괄 알림 전송",     lambda: _s_notify_all(calc_date, results, start_all))

    if calc_date.weekday() == 5:
        results["9_weekly"] = _run_step("9/16 주간 성과",       lambda: _s_weekly(calc_date))
    else:
        results["9_weekly"] = "SKIP"

    if calc_date.day == 1:
        results["10_monthly"] = _run_step("10/16 월간 성과",    lambda: _s_monthly(calc_date))
    else:
        results["10_monthly"] = "SKIP"

    elapsed = datetime.now() - start_all
    ok   = sum(1 for v in results.values() if v == "OK")
    fail = sum(1 for v in results.values() if isinstance(v, str) and v.startswith("FAIL"))
    skip = sum(1 for v in results.values() if v == "SKIP")
    print(f"\n{'='*60}\n  v5.0 결과: 성공={ok} 실패={fail} 스킵={skip} | 소요: {elapsed}\n{'='*60}")
    return results


def _s_price(d):
    from batch.batch_ticker_item_daily import run_daily_price
    run_daily_price(d)

def _s_fin():
    """오답노트 #6: run_supplement_financials()는 인자 없음"""
    from batch.batch_ticker_item_daily import run_supplement_financials
    run_supplement_financials()

def _s_l1(d):
    from batch.batch_ticker_item_daily import run_quant_score
    run_quant_score(d)

def _s_l3(d):
    """오답노트 #5: batch_layer3_v2.run_all(d)"""
    from batch.batch_layer3_v2 import run_all as r
    r(d)

def _s_l2():
    """오답노트 #7: batch_layer2_v2.run_all()은 인자 없음"""
    from batch.batch_layer2_v2 import run_all as r
    r()

def _s_ec(d):
    from batch.batch_earnings_call import run_earnings_call_analysis
    run_earnings_call_analysis(d)

def _s_final(d):
    from batch.batch_final_score import run_final_score
    run_final_score(d)



def _s_factor_monitor(d):
    """Self-Improving Engine: IC 계산 + (월초) 가중치 최적화"""
    from batch.batch_factor_monitor import run_factor_monitor
    run_factor_monitor(d)


def _s_chart_patterns(d):
    from batch.batch_chart_patterns import run_chart_patterns
    run_chart_patterns(d)

def _s_fear_greed(d):
    from batch.batch_fear_greed import run_fear_greed
    run_fear_greed(d)

def _s_put_call(d):
    from batch.batch_put_call import run_put_call
    run_put_call(d)

def _s_cross_asset(d):
    from batch.batch_cross_asset import run_cross_asset
    run_cross_asset(d)

def _s_xgboost(d):
    from batch.batch_xgboost import run_xgboost
    run_xgboost(d)

def _s_alpha_decay(d):
    from batch.batch_alpha_decay import run_alpha_decay
    run_alpha_decay(d)


def _s_trading(d):
    """트레이딩 시그널 계산 (알림 없이 DB 저장만)"""
    live = os.environ.get("TRADING_LIVE", "0") == "1"
    from batch.batch_trading_signals import run_trading_signals
    run_trading_signals(calc_date=d, dry_run=not live)


# ═══════════════════════════════════════════════════════════
#  Step 8: 일괄 알림 — 배치 완료 후 한 번에 전부 전송
# ═══════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════
#  v5.0 신규 Step 함수들
# ═══════════════════════════════════════════════════════════

def _s_dq_gate(d):
    """Step 0: Data Quality Gate"""
    from utils.data_quality_gate import run_data_quality_gate
    return run_data_quality_gate(d)

def _s_options(d):
    """Step 5.3: Options Flow (IV/Skew/Put-Call)"""
    from batch.batch_options_flow import run_options_flow
    return run_options_flow(d)

def _s_regime(d):
    """Step 5.5: Macro Regime HMM"""
    from batch.batch_macro_regime import run_macro_regime
    return run_macro_regime(d)

def _s_ensemble(d):
    """Step 6.3: Stacking Ensemble (XGBoost+LightGBM+Ridge)"""
    try:
        from batch.batch_ensemble import run_ensemble
        return run_ensemble(d)
    except ImportError:
        from batch.batch_xgboost import run_xgboost
        return run_xgboost(d)

def _s_auto_pilot(d):
    """Step 7.5: AutoPilot Self-Evolution"""
    from batch.batch_auto_pilot import run_auto_pilot
    return run_auto_pilot(d)

def _s_notify_all(calc_date, results, start_time):
    """
    v4.0 — 모든 알림을 일괄 발송 (notify_data_builder + notifier)

    scheduler → notify_data_builder (계산) → notifier (전송)

    1) IC/적중률/국면확률 계산
    2) 매수 근거 카드 보강 (Goldman Conviction + Bridgewater Because)
    3) 매도 분석 보강 (MAE/MFE + 점수변화 + 역대성과)
    4) 리스크 대시보드 (VaR + Stress + 집중도)
    5) 모닝/시그널/리스크/등급변경/국면전환/배치완료 알림
    """
    from db_pool import get_cursor

    # ═══════════════════════════════════════════════════════
    #  Phase 1: DB에서 기본 데이터 로드
    # ═══════════════════════════════════════════════════════
    regime = None
    regime_detail = {}
    buy_signals_raw = []
    sell_signals_raw = []
    fire_signals = []
    bounce_signals = []
    regime_changed = False
    prev_regime = None
    portfolio_summary = {}
    grade_changes = []

    try:
        # ── 시장 국면 ──
        with get_cursor() as cur:
            cur.execute("""
                SELECT regime, spy_price, spy_ma50, spy_ma200, vix_close,
                       regime_multiplier
                FROM market_regime
                ORDER BY regime_date DESC LIMIT 2
            """)
            rows = cur.fetchall()

        if rows:
            latest = rows[0]
            regime = latest["regime"]
            regime_detail = {
                "spy_price": float(latest["spy_price"] or 0),
                "sma_200": float(latest.get("spy_ma200") or 0),
                "vix_close": float(latest["vix_close"] or 0),
                "regime_multiplier": float(latest.get("regime_multiplier") or 1.0),
            }
            if len(rows) >= 2:
                prev_regime = rows[1]["regime"]
                if prev_regime != regime:
                    regime_changed = True

        # ── 매수 시그널 ──
        with get_cursor() as cur:
            cur.execute("""
                SELECT ts.*, s.ticker, sec.sector_name AS sector, s.stock_id
                FROM trading_signals ts
                JOIN stocks s ON ts.stock_id = s.stock_id
                LEFT JOIN sectors sec ON s.sector_id = sec.sector_id
                WHERE ts.signal_date = %s AND ts.signal_type = 'BUY'
                ORDER BY ts.final_score DESC
            """, (calc_date,))
            for row in cur.fetchall():
                buy_signals_raw.append({
                    "stock_id": row["stock_id"],
                    "ticker": row["ticker"],
                    "score": float(row.get("final_score") or 0),
                    "grade": row.get("grade", row.get("signal_strength", "")),
                    "price": float(row.get("current_price") or 0),
                    "shares": int(row.get("shares") or 0),
                    "amount": float(row.get("amount") or 0),
                    "weight": float(row.get("weight_pct") or 0),
                    "stop_loss": float(row.get("stop_loss") or 0),
                    "stop_pct": float(row.get("stop_pct") or 10),
                    "sector": row.get("sector", ""),
                })

        # ── 매도 시그널 ──
        with get_cursor() as cur:
            cur.execute("""
                SELECT ts.*, s.ticker, sec.sector_name AS sector, s.stock_id
                FROM trading_signals ts
                JOIN stocks s ON ts.stock_id = s.stock_id
                LEFT JOIN sectors sec ON s.sector_id = sec.sector_id
                WHERE ts.signal_date = %s AND ts.signal_type IN ('SELL', 'PROFIT_TAKE', 'STOP_LOSS')
                ORDER BY ts.pnl_pct
            """, (calc_date,))
            for row in cur.fetchall():
                sig = {
                    "stock_id": row["stock_id"],
                    "ticker": row["ticker"],
                    "price": float(row.get("current_price") or 0),
                    "entry_price": float(row.get("entry_price") or 0),
                    "pnl_pct": float(row.get("pnl_pct") or 0),
                    "reason": row.get("sell_reason", row.get("signal_type", "SELL")),
                    "shares": int(row.get("shares") or 0),
                    "holding_days": int(row.get("holding_days") or 0),
                }
                if row.get("signal_type") == 'STOP_LOSS' and float(row.get("pnl_pct") or 0) < -15:
                    fire_signals.append(sig)
                else:
                    sell_signals_raw.append(sig)

        # ── 바닥 반등 ──
        with get_cursor() as cur:
            cur.execute("""
                SELECT ts.*, s.ticker, ti.rsi_14
                FROM trading_signals ts
                JOIN stocks s ON ts.stock_id = s.stock_id
                LEFT JOIN LATERAL (
                    SELECT rsi_14 FROM technical_indicators
                    WHERE stock_id = ts.stock_id ORDER BY calc_date DESC LIMIT 1
                ) ti ON TRUE
                WHERE ts.signal_date = %s AND ts.signal_type = 'BOUNCE'
                ORDER BY ts.final_score DESC
            """, (calc_date,))
            for row in cur.fetchall():
                bounce_signals.append({
                    "ticker": row["ticker"],
                    "score": float(row.get("score") or 0),
                    "grade": row.get("grade", ""),
                    "price": float(row.get("price") or 0),
                    "drop_pct": float(row.get("drop_pct") or 0),
                    "rsi": float(row.get("rsi_14") or 30),
                })

        # ── 포트폴리오 현황 ──
        with get_cursor() as cur:
            cur.execute("""
                SELECT total_value, cash_balance, daily_return_pct
                FROM portfolio_daily_snapshot
                WHERE portfolio_id = 1
                ORDER BY snapshot_date DESC LIMIT 1
            """)
            snap = cur.fetchone()
            if snap:
                tv = float(snap["total_value"] or 0)
                cash = float(snap["cash_balance"] or 0)
                portfolio_summary = {
                    "total_value": tv,
                    "daily_return": float(snap.get("daily_return_pct") or 0),
                    "cash_pct": (cash / tv * 100) if tv > 0 else 100,
                }
            cur.execute("""
                SELECT COUNT(*) as cnt FROM portfolio_positions
                WHERE status = 'OPEN' AND portfolio_id = 1
            """)
            portfolio_summary["num_positions"] = cur.fetchone()["cnt"]

        # ── 등급 변경 ──
        with get_cursor() as cur:
            cur.execute("""
                SELECT s.ticker,
                       f1.grade AS new_grade, f1.weighted_score AS new_score,
                       f0.grade AS old_grade, f0.weighted_score AS old_score
                FROM stock_final_scores f1
                JOIN stock_final_scores f0
                  ON f1.stock_id = f0.stock_id AND f0.calc_date = (
                     SELECT MAX(calc_date) FROM stock_final_scores
                     WHERE stock_id = f1.stock_id AND calc_date < %s
                  )
                JOIN stocks s ON f1.stock_id = s.stock_id
                WHERE f1.calc_date = %s AND f1.grade != f0.grade
                ORDER BY f1.weighted_score DESC
            """, (calc_date, calc_date))
            for row in cur.fetchall():
                grade_changes.append({
                    "ticker": row["ticker"],
                    "old_grade": row["old_grade"],
                    "new_grade": row["new_grade"],
                    "old_score": float(row.get("old_score") or 0),
                    "new_score": float(row.get("new_score") or 0),
                })

    except Exception as e:
        print(f"  [NOTIFY] DB 로드 실패: {e}")
        traceback.print_exc()

    # ═══════════════════════════════════════════════════════
    #  Phase 2: v4 계산 엔진으로 데이터 보강
    # ═══════════════════════════════════════════════════════
    print(f"\n  ── Phase 2: v4 데이터 보강 ──")

    try:
        from notify_data_builder import (
            build_buy_rationale, build_sell_analysis,
            calc_signal_ic, calc_hit_rate, calc_regime_probability,
            build_risk_dashboard, get_fear_greed,
        )
        _HAS_BUILDER = True
    except ImportError:
        print("  ⚠️ notify_data_builder 없음 → 기본 모드")
        _HAS_BUILDER = False

    # ★ v4.1: AI 데이터 빌더
    _HAS_AI_BUILDER = False
    try:
        from notify_data_builder import (
            build_ai_morning_data, build_ai_signal_data,
            build_ai_risk_data, build_ai_batch_summary,
        )
        _HAS_AI_BUILDER = True
    except ImportError:
        print("  ⚠️ AI builder 없음 → AI 알림 스킵")

    # ── 매수 시그널 보강 ──
    buy_signals = []
    if _HAS_BUILDER:
        for sig in buy_signals_raw:
            enriched = build_buy_rationale(
                sig["stock_id"], sig["ticker"], calc_date, sig)
            buy_signals.append(enriched)
        print(f"  ✅ BUY 보강 완료 ({len(buy_signals)}건)")
    else:
        buy_signals = buy_signals_raw

    # ── 매도 시그널 보강 ──
    sell_signals = []
    if _HAS_BUILDER:
        for sig in sell_signals_raw:
            enriched = build_sell_analysis(
                sig["stock_id"], sig["ticker"], calc_date, sig)
            sell_signals.append(enriched)
        print(f"  ✅ SELL 보강 완료 ({len(sell_signals)}건)")
    else:
        sell_signals = sell_signals_raw

    # ── IC / 적중률 / 국면확률 / Fear&Greed ──
    ic_data = None
    hit_rate = None
    regime_proba = None
    fear_greed = None
    risk_data = {}

    if _HAS_BUILDER:
        try:
            ic_data = calc_signal_ic()
            print(f"  ✅ IC 계산: {ic_data.get('ic', 0):.4f}")
        except Exception as e:
            print(f"  ⚠️ IC 계산 실패: {e}")

        try:
            hit_rate = calc_hit_rate()
            print(f"  ✅ 적중률: {hit_rate.get('hit_rate', 0):.1f}%")
        except Exception as e:
            print(f"  ⚠️ 적중률 실패: {e}")

        try:
            regime_proba = calc_regime_probability()
            print(f"  ✅ 국면확률: {regime_proba}")
        except Exception as e:
            print(f"  ⚠️ 국면확률 실패: {e}")

        try:
            fear_greed = get_fear_greed()
        except Exception:
            pass

        try:
            risk_data = build_risk_dashboard(calc_date)
            print(f"  ✅ 리스크 대시보드: {risk_data.get('risk_level', '?')}")
        except Exception as e:
            print(f"  ⚠️ 리스크 대시보드 실패: {e}")

    # ═══════════════════════════════════════════════════════
    #  Phase 3: 일괄 알림 발송
    # ═══════════════════════════════════════════════════════
    # ★ v4.1: AI 데이터 수집
    ai_morning = {}
    ai_risk_data = {}
    ai_batch = {}
    if _HAS_AI_BUILDER:
        try:
            ai_morning = build_ai_morning_data(calc_date)
            print(f"  ✅ AI 모닝 데이터: Top {len(ai_morning.get('ai_top', []))} / Bottom {len(ai_morning.get('ai_bottom', []))}")
        except Exception as e:
            print(f"  ⚠️ AI 모닝 실패: {e}")

        try:
            ai_risk_data = build_ai_risk_data(calc_date)
            danger_cnt = len([d for d in ai_risk_data.get("ic_details", []) if d.get("status") == "DANGER"])
            dead_cnt = len(ai_risk_data.get("decay_dead", []))
            print(f"  ✅ AI 리스크: IC DANGER {danger_cnt}건 / Decay DEAD {dead_cnt}건")
        except Exception as e:
            print(f"  ⚠️ AI 리스크 실패: {e}")

        try:
            ai_batch = build_ai_batch_summary(calc_date)
            print(f"  ✅ AI 배치: AUC={ai_batch.get('auc')} / 추론={ai_batch.get('predict_count')}종목")
        except Exception as e:
            print(f"  ⚠️ AI 배치요약 실패: {e}")

        # 매수 시그널에 AI 데이터 보강
        for s in buy_signals:
            try:
                s["ai_data"] = build_ai_signal_data(s["stock_id"], calc_date)
            except Exception:
                s["ai_data"] = {}

        # 매도 시그널에도
        for s in sell_signals:
            try:
                s["ai_data"] = build_ai_signal_data(s["stock_id"], calc_date)
            except Exception:
                s["ai_data"] = {}

    print(f"\n  ── Phase 3: 알림 발송 ──")

    from notifier import (
        notify_morning_briefing,
        notify_daily_signals,
        notify_add_position,
        notify_fire_sell,
        notify_bounce_opportunity,
        notify_risk_warning,
        notify_grade_changes as notify_grades,
        notify_regime_change,
        notify_batch_complete,
    )

    # (A) 모닝 브리핑 → MY_MORNING + PUB_MORNING
    if regime:
        try:
            signal_summary = {
                "buy_count": len(buy_signals),
                "sell_count": len(sell_signals),
                "fire_count": len(fire_signals),
                "add_count": 0,
                "bounce_count": len(bounce_signals),
            }
            notify_morning_briefing(
                calc_date=calc_date,
                regime=regime,
                regime_detail=regime_detail,
                signal_summary=signal_summary,
                regime_proba=regime_proba,
                ic_data=ic_data,
                hit_rate=hit_rate,
                fear_greed=fear_greed,
                portfolio_summary=portfolio_summary,
                ai_morning=ai_morning,
                ai_risk=ai_risk_data,
            )
            print(f"  ✅ 모닝 브리핑 → MY_MORNING + PUB_MORNING")
        except Exception as e:
            print(f"  ⚠️ 모닝 브리핑 실패: {e}")

    # (B) 매수/매도 시그널 → BUY/SELL/PROFIT + PUB
    if buy_signals or sell_signals:
        try:
            notify_daily_signals(
                calc_date=calc_date,
                regime=regime or "NEUTRAL",
                regime_detail=regime_detail,
                buy_signals=buy_signals,
                sell_signals=sell_signals,
                portfolio_summary=portfolio_summary,
            )
            print(f"  ✅ 시그널 → MY_BUY/SELL/PROFIT + PUB_BUY/SELL")
        except Exception as e:
            print(f"  ⚠️ 시그널 실패: {e}")

    # (C) 긴급 매도 → MY_FIRE
    if fire_signals:
        try:
            notify_fire_sell(calc_date=calc_date, fire_signals=fire_signals)
            print(f"  ✅ 긴급 매도 → MY_FIRE ({len(fire_signals)}건)")
        except Exception as e:
            print(f"  ⚠️ FIRE 실패: {e}")

    # (D) 반등 기회 → MY_BOUNCE
    if bounce_signals:
        try:
            notify_bounce_opportunity(calc_date=calc_date, bounce_signals=bounce_signals)
            print(f"  ✅ 반등 기회 → MY_BOUNCE ({len(bounce_signals)}건)")
        except Exception as e:
            print(f"  ⚠️ BOUNCE 실패: {e}")

    # (E) 리스크 경고 → MY_RISK + PUB_RISK
    if risk_data:
        try:
            notify_risk_warning(
                calc_date=calc_date,
                risk_level=risk_data.get("risk_level", "GREEN"),
                drawdown=risk_data.get("drawdown"),
                var_data=risk_data.get("var"),
                concentration=risk_data.get("concentration"),
                defense_status=risk_data.get("defense"),
                stress_test=risk_data.get("stress_test"),
                correlation=risk_data.get("correlation"),
                ai_risk=ai_risk_data,
            )
            print(f"  ✅ 리스크 → MY_RISK + PUB_RISK ({risk_data.get('risk_level', '?')})")
        except Exception as e:
            print(f"  ⚠️ RISK 실패: {e}")

    # (F) 등급 변경 → MY_ALERT + PUB_REPORT
    if grade_changes:
        try:
            notify_grades(calc_date=calc_date, changes=grade_changes)
            print(f"  ✅ 등급 변경 → MY_ALERT + PUB_REPORT ({len(grade_changes)}건)")
        except Exception as e:
            print(f"  ⚠️ 등급변경 실패: {e}")

    # (G) 국면 전환 → MY_ALERT + PUB_REPORT
    if regime_changed:
        try:
            notify_regime_change(
                calc_date=calc_date,
                old_regime=prev_regime,
                new_regime=regime,
                trigger_detail=regime_detail,
            )
            print(f"  ✅ 국면 전환 → MY_ALERT + PUB_REPORT ({prev_regime}→{regime})")
        except Exception as e:
            print(f"  ⚠️ 국면전환 실패: {e}")

    # (H) 배치 완료 → MY_SYSTEM + PUB_REPORT
    try:
        elapsed = (datetime.now() - start_time).total_seconds()
        ok_cnt = sum(1 for v in results.values() if v == "OK")
        fail_cnt = sum(1 for v in results.values() if isinstance(v, str) and v.startswith("FAIL"))

        step_results = {}
        for k, v in results.items():
            step_name = k.split("_", 1)[1] if "_" in k else k
            step_results[step_name] = {"ok": v == "OK", "duration": ""}

        notify_batch_complete(
            calc_date=calc_date,
            duration_sec=elapsed,
            job_name="Daily Full Pipeline",
            results={
                "success": ok_cnt,
                "fail": fail_cnt,
                "total": ok_cnt + fail_cnt,
                "steps": step_results,
            },
            ai_summary=ai_batch,
        )
        print(f"  ✅ 배치 완료 → MY_SYSTEM + PUB_REPORT")
    except Exception as e:
        print(f"  ⚠️ 배치완료 알림 실패: {e}")

    print(f"\n  ── 알림 발송 완료 ──")


# ═══════════════════════════════════════════════════════════
#  Step 9: 주간 리포트 (토요일)
#  ★ notifier.notify_weekly_report 시그니처에 맞춰 호출
# ═══════════════════════════════════════════════════════════

def _s_weekly(d):
    """주간 성과 리포트 → Discord REPORT 채널"""
    from db_pool import get_cursor

    week_start = d - timedelta(days=7)

    # ── 주간 수익률 ──
    with get_cursor() as cur:
        cur.execute("""
            SELECT total_value, snapshot_date
            FROM portfolio_daily_snapshot
            WHERE portfolio_id = 1 AND snapshot_date >= %s
            ORDER BY snapshot_date
        """, (week_start,))
        rows = cur.fetchall()

    if len(rows) < 2:
        print("  주간 데이터 부족 — 스킵")
        return

    start_val = float(rows[0]["total_value"])
    end_val = float(rows[-1]["total_value"])
    week_return = (end_val - start_val) / start_val * 100 if start_val > 0 else 0

    # ── MTD / YTD / Inception ──
    mtd_return = 0
    ytd_return = 0
    since_inception = 0
    try:
        with get_cursor() as cur:
            # MTD: 이번 달 1일부터
            month_start = d.replace(day=1)
            cur.execute("""
                SELECT total_value FROM portfolio_daily_snapshot
                WHERE portfolio_id = 1 AND snapshot_date >= %s
                ORDER BY snapshot_date LIMIT 1
            """, (month_start,))
            row = cur.fetchone()
            if row:
                mtd_start = float(row["total_value"])
                mtd_return = (end_val - mtd_start) / mtd_start * 100 if mtd_start > 0 else 0

            # YTD: 올해 1월 1일부터
            year_start = d.replace(month=1, day=1)
            cur.execute("""
                SELECT total_value FROM portfolio_daily_snapshot
                WHERE portfolio_id = 1 AND snapshot_date >= %s
                ORDER BY snapshot_date LIMIT 1
            """, (year_start,))
            row = cur.fetchone()
            if row:
                ytd_start = float(row["total_value"])
                ytd_return = (end_val - ytd_start) / ytd_start * 100 if ytd_start > 0 else 0

            # Since Inception: 가장 오래된 스냅샷
            cur.execute("""
                SELECT total_value FROM portfolio_daily_snapshot
                WHERE portfolio_id = 1
                ORDER BY snapshot_date LIMIT 1
            """)
            row = cur.fetchone()
            if row:
                inception_val = float(row["total_value"])
                since_inception = (end_val - inception_val) / inception_val * 100 if inception_val > 0 else 0
    except Exception as e:
        print(f"  ⚠️ MTD/YTD 계산 실패: {e}")

    # ── 트레이드 통계 ──
    num_trades = 0
    win_rate = 0
    best_ticker = ""
    best_pnl = 0
    worst_ticker = ""
    worst_pnl = 0
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) as cnt
                FROM trading_signals
                WHERE calc_date >= %s AND signal_type IN ('BUY', 'SELL', 'PROFIT_TAKE', 'STOP_LOSS')
            """, (week_start,))
            num_trades = cur.fetchone()["cnt"]

            # 승률: 매도 중 수익 비율
            cur.execute("""
                SELECT COUNT(*) FILTER (WHERE pnl_pct > 0) as wins,
                       COUNT(*) as total
                FROM trading_signals
                WHERE calc_date >= %s AND signal_type IN ('SELL', 'PROFIT_TAKE', 'STOP_LOSS')
            """, (week_start,))
            row = cur.fetchone()
            if row and row["total"] > 0:
                win_rate = row["wins"] / row["total"] * 100

            # Best / Worst
            cur.execute("""
                SELECT s.ticker, ts.pnl_pct
                FROM trading_signals ts
                JOIN stocks s ON ts.stock_id = s.stock_id
                WHERE ts.signal_date >= %s AND ts.signal_type IN ('SELL', 'PROFIT_TAKE', 'STOP_LOSS')
                ORDER BY ts.pnl_pct DESC LIMIT 1
            """, (week_start,))
            row = cur.fetchone()
            if row:
                best_ticker = row["ticker"]
                best_pnl = float(row["pnl_pct"] or 0)

            cur.execute("""
                SELECT s.ticker, ts.pnl_pct
                FROM trading_signals ts
                JOIN stocks s ON ts.stock_id = s.stock_id
                WHERE ts.signal_date >= %s AND ts.signal_type IN ('SELL', 'PROFIT_TAKE', 'STOP_LOSS')
                ORDER BY ts.pnl_pct ASC LIMIT 1
            """, (week_start,))
            row = cur.fetchone()
            if row:
                worst_ticker = row["ticker"]
                worst_pnl = float(row["pnl_pct"] or 0)
    except Exception as e:
        print(f"  ⚠️ 트레이드 통계 실패: {e}")

    # ── Brinson Attribution (옵션) ──
    brinson = None
    try:
        from notify_data_builder import build_weekly_brinson
        brinson = build_weekly_brinson(d)
    except Exception:
        pass

    # ── 알림 발송 (notifier 시그니처 정합) ──
    from notifier import notify_weekly_report
    notify_weekly_report(
        calc_date=d,
        week_return=week_return,
        mtd_return=mtd_return,
        ytd_return=ytd_return,
        since_inception=since_inception,
        win_rate=win_rate,
        num_trades=num_trades,
        best_ticker=best_ticker,
        best_pnl=best_pnl,
        worst_ticker=worst_ticker,
        worst_pnl=worst_pnl,
        brinson=brinson,
    )


# ═══════════════════════════════════════════════════════════
#  Step 10: 월간 리포트 (매월 1일)
#  ★ 주간과 동일 구조, 기간만 다름
# ═══════════════════════════════════════════════════════════

def _s_monthly(d):
    """월간 성과 리포트 → Discord REPORT 채널"""
    from db_pool import get_cursor

    # 전월 1일 ~ 전월 말일
    prev_month_end = d.replace(day=1) - timedelta(days=1)
    month_start = prev_month_end.replace(day=1)

    with get_cursor() as cur:
        cur.execute("""
            SELECT total_value, snapshot_date
            FROM portfolio_daily_snapshot
            WHERE portfolio_id = 1 AND snapshot_date >= %s AND snapshot_date <= %s
            ORDER BY snapshot_date
        """, (month_start, prev_month_end))
        rows = cur.fetchall()

    if len(rows) < 2:
        print("  월간 데이터 부족 — 스킵")
        return

    start_val = float(rows[0]["total_value"])
    end_val = float(rows[-1]["total_value"])
    month_return = (end_val - start_val) / start_val * 100 if start_val > 0 else 0

    # ── YTD / Inception ──
    ytd_return = 0
    since_inception = 0
    try:
        with get_cursor() as cur:
            year_start = d.replace(month=1, day=1)
            cur.execute("""
                SELECT total_value FROM portfolio_daily_snapshot
                WHERE portfolio_id = 1 AND snapshot_date >= %s
                ORDER BY snapshot_date LIMIT 1
            """, (year_start,))
            row = cur.fetchone()
            if row:
                ytd_start = float(row["total_value"])
                ytd_return = (end_val - ytd_start) / ytd_start * 100 if ytd_start > 0 else 0

            cur.execute("""
                SELECT total_value FROM portfolio_daily_snapshot
                WHERE portfolio_id = 1
                ORDER BY snapshot_date LIMIT 1
            """)
            row = cur.fetchone()
            if row:
                inception_val = float(row["total_value"])
                since_inception = (end_val - inception_val) / inception_val * 100 if inception_val > 0 else 0
    except Exception as e:
        print(f"  ⚠️ YTD 계산 실패: {e}")

    # ── 트레이드 통계 ──
    num_trades = 0
    win_rate = 0
    best_ticker = ""
    best_pnl = 0
    worst_ticker = ""
    worst_pnl = 0
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) as cnt
                FROM trading_signals
                WHERE calc_date >= %s AND calc_date <= %s
                  AND signal_type IN ('BUY', 'SELL', 'PROFIT_TAKE', 'STOP_LOSS')
            """, (month_start, prev_month_end))
            num_trades = cur.fetchone()["cnt"]

            cur.execute("""
                SELECT COUNT(*) FILTER (WHERE pnl_pct > 0) as wins,
                       COUNT(*) as total
                FROM trading_signals
                WHERE calc_date >= %s AND calc_date <= %s
                  AND signal_type IN ('SELL', 'PROFIT_TAKE', 'STOP_LOSS')
            """, (month_start, prev_month_end))
            row = cur.fetchone()
            if row and row["total"] > 0:
                win_rate = row["wins"] / row["total"] * 100

            cur.execute("""
                SELECT s.ticker, ts.pnl_pct
                FROM trading_signals ts
                JOIN stocks s ON ts.stock_id = s.stock_id
                WHERE ts.signal_date >= %s AND ts.signal_date <= %s
                  AND ts.signal_type IN ('SELL', 'PROFIT_TAKE', 'STOP_LOSS')
                ORDER BY ts.pnl_pct DESC LIMIT 1
            """, (month_start, prev_month_end))
            row = cur.fetchone()
            if row:
                best_ticker = row["ticker"]
                best_pnl = float(row["pnl_pct"] or 0)

            cur.execute("""
                SELECT s.ticker, ts.pnl_pct
                FROM trading_signals ts
                JOIN stocks s ON ts.stock_id = s.stock_id
                WHERE ts.signal_date >= %s AND ts.signal_date <= %s
                  AND ts.signal_type IN ('SELL', 'PROFIT_TAKE', 'STOP_LOSS')
                ORDER BY ts.pnl_pct ASC LIMIT 1
            """, (month_start, prev_month_end))
            row = cur.fetchone()
            if row:
                worst_ticker = row["ticker"]
                worst_pnl = float(row["pnl_pct"] or 0)
    except Exception as e:
        print(f"  ⚠️ 월간 트레이드 통계 실패: {e}")

    # ── Brinson (옵션) ──
    brinson = None
    try:
        from notify_data_builder import build_weekly_brinson
        brinson = build_weekly_brinson(d)
    except Exception:
        pass

    # ── 알림 발송 (notifier 시그니처 정합) ──
    from notifier import notify_weekly_report
    notify_weekly_report(
        calc_date=d,
        week_return=month_return,
        ytd_return=ytd_return,
        since_inception=since_inception,
        win_rate=win_rate,
        num_trades=num_trades,
        best_ticker=best_ticker,
        best_pnl=best_pnl,
        worst_ticker=worst_ticker,
        worst_pnl=worst_pnl,
        brinson=brinson,
    )


# ═══════════════════════════════════════════════════════════
#  유틸
# ═══════════════════════════════════════════════════════════

def _run_step(name: str, fn):
    print(f"\n▶ {name}")
    t0 = datetime.now()
    try:
        fn()
        elapsed = datetime.now() - t0
        print(f"  ✅ {elapsed}")
        return "OK"
    except Exception as e:
        elapsed = datetime.now() - t0
        print(f"  ❌ {e} ({elapsed})")
        traceback.print_exc()
        return f"FAIL: {e}"


def _should_earnings(d):
    """어닝콜 분석 대상일인지 판단"""
    try:
        from db_pool import get_cursor
        with get_cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) as cnt FROM earnings_calendar
                WHERE report_date = %s
            """, (d,))
            return cur.fetchone()["cnt"] > 0
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════
#  APScheduler — 평일 ET 20:30 자동 실행
#  (애프터마켓 20:00 마감 + 30분 = KST 09:30)
# ═══════════════════════════════════════════════════════════

def start_scheduler():
    """standalone 모드: APScheduler로 평일 ET 20:30 자동 실행"""
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger
    import pytz

    et = pytz.timezone("US/Eastern")
    scheduler = BlockingScheduler(timezone=et)

    scheduler.add_job(
        run_all,
        trigger=CronTrigger(
            day_of_week="mon-fri",
            hour=20,
            minute=30,
            timezone=et,
        ),
        id="daily_batch",
        name="Daily Batch Pipeline (ET 20:30)",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    print("=" * 60)
    print("  QUANT AI v4.0 — Batch Scheduler")
    print("  평일 ET 20:30 (KST 09:30) 자동 실행")
    print("  애프터마켓 마감(20:00) + 30분 → 배치 → 디코 알림")
    print("=" * 60)
    print(f"  다음 실행: {scheduler.get_jobs()[0].next_run_time}")
    print("  Ctrl+C로 종료")
    print("=" * 60)

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\n[SCHEDULER] 🛑 종료")


# ═══════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="QUANT AI Batch Scheduler")
    parser.add_argument("--date", type=str, default=None, help="YYYY-MM-DD (수동 실행)")
    parser.add_argument("--now", action="store_true", help="즉시 1회 실행")
    args = parser.parse_args()

    if args.date:
        calc_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        run_all(calc_date)
    elif args.now:
        run_all()
    else:
        # 기본: APScheduler 대기 모드
        start_scheduler()