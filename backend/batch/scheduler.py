"""
scheduler.py — QUANT AI v5.1 (v5.0 + SET A: Paper Trading + SHAP Notes + Cross-Val)
=====================================================
v5.1 변경 (v5.0 → v5.1 SET A):
  ★ Step 0.5 신규: Cross-Source Validation (A-5)
  ★ Step 7.3 신규: Paper Trading Engine (A-1)
  ★ Step 7.7 신규: SHAP Research Notes (A-4)
  ★ A-3 (BUY 캘리브레이션)은 trading_config.py 교체로 자동 적용
  ★ 알림에 Paper Trading 요약 + Research Notes 추가

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
  4) 백테스트:   python -m batch.scheduler --backtest --backtest-track both  (A-2)
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
    QUANT AI v5.1 일일 배치.
    
    v5.1 SET A 추가:
      Step 0.5: Cross-Source Validation (A-5)
      Step 7.3: Paper Trading Engine (A-1)
      Step 7.7: SHAP Research Notes (A-4)
    
    v5.0 추가:
      Step 0:   Data Quality Gate
      Step 5.3: Options Flow
      Step 5.5: Macro Regime HMM
      Step 6.3: Stacking Ensemble
      Step 7.5: AutoPilot
    """
    if calc_date is None:
        calc_date = datetime.now().date()
    start_all = datetime.now()
    results = {}
    print(f"\n{'='*60}\n  QUANT AI v5.1 일일 배치 — {calc_date}\n{'='*60}")

    # ══════════ PHASE 1: 데이터 품질 + 수집 ══════════

    results["0_dq"]        = _run_step("0/18 Data Quality Gate",      lambda: _s_dq_gate(calc_date))
    results["0.5_crossval"]= _run_step("0.5 Cross-Source Validation", lambda: _s_cross_validation(calc_date))  # ★ A-5
    results["1_price"]     = _run_step("1/18 가격 수집",              lambda: _s_price(calc_date))
    results["2_fin"]       = _run_step("2/18 파생 재무",              lambda: _s_fin())
    results["3_l1"]        = _run_step("3/18 Layer 1",                lambda: _s_l1(calc_date))
    results["4_l3"]        = _run_step("4/18 Layer 3",                lambda: _s_l3(calc_date))
    results["4.5_pat"]     = _run_step("4.5 차트패턴",                lambda: _s_chart_patterns(calc_date))
    results["4.6_fg"]      = _run_step("4.6 Fear & Greed",            lambda: _s_fear_greed(calc_date))
    results["4.7_pc"]      = _run_step("4.7 Put/Call Ratio",          lambda: _s_put_call(calc_date))
    results["4.8_ca"]      = _run_step("4.8 Cross-Asset",             lambda: _s_cross_asset(calc_date))
    results["5_l2"]        = _run_step("5/18 Layer 2",                lambda: _s_l2())

    if _should_earnings(calc_date):
        results["5.1_ec"]  = _run_step("5.1 어닝콜",                 lambda: _s_ec(calc_date))
    else:
        results["5.1_ec"]  = "SKIP"

    # ══════════ PHASE 2: 선행지표 + 매크로 ══════════

    results["5.3_options"] = _run_step("5.3 Options Flow",            lambda: _s_options(calc_date))
    results["5.5_regime"]  = _run_step("5.5 Macro Regime",            lambda: _s_regime(calc_date))

    # ══════════ PHASE 3: 합산 + ML + 앙상블 ══════════

    results["6_final"]     = _run_step("6/18 최종 합산",              lambda: _s_final(calc_date))
    results["6.3_ens"]     = _run_step("6.3 Stacking Ensemble",       lambda: _s_ensemble(calc_date))
    results["6.5_ic"]      = _run_step("6.5 IC Guard v2",             lambda: _s_factor_monitor(calc_date))
    results["6.7_decay"]   = _run_step("6.7 Alpha Decay",             lambda: _s_alpha_decay(calc_date))

    # ══════════ PHASE 4: 시그널 ══════════

    results["7_trading"]   = _run_step("7/18 Trading Signals",        lambda: _s_trading(calc_date))

    # ══════════ PHASE 4.5: Paper Trading (★ A-1 신규) ══════════

    results["7.3_paper"]   = _run_step("7.3 Paper Trading",           lambda: _s_paper_trading(calc_date))

    # ══════════ PHASE 5: 자가진화 ══════════

    results["7.5_pilot"]   = _run_step("7.5 AutoPilot",               lambda: _s_auto_pilot(calc_date))

    # ══════════ PHASE 5.5: Research Notes (★ A-4 신규) ══════════

    results["7.7_notes"]   = _run_step("7.7 Research Notes",          lambda: _s_research_notes(calc_date))

    # ══════════ PHASE 6: 알림 ══════════

    results["8_notify"]    = _run_step("8/18 일괄 알림 전송",         lambda: _s_notify_all(calc_date, results, start_all))

    if calc_date.weekday() == 5:
        results["9_weekly"]  = _run_step("9/18 주간 성과",            lambda: _s_weekly(calc_date))
    else:
        results["9_weekly"]  = "SKIP"

    if calc_date.day == 1:
        results["10_monthly"]= _run_step("10/18 월간 성과",           lambda: _s_monthly(calc_date))
    else:
        results["10_monthly"]= "SKIP"

    elapsed = datetime.now() - start_all
    ok   = sum(1 for v in results.values() if v == "OK")
    fail = sum(1 for v in results.values() if isinstance(v, str) and v.startswith("FAIL"))
    skip = sum(1 for v in results.values() if v == "SKIP")
    print(f"\n{'='*60}\n  v5.1 결과: 성공={ok} 실패={fail} 스킵={skip} | 소요: {elapsed}\n{'='*60}")
    return results


# ═══════════════════════════════════════════════════════════
#  기존 Step 함수들 (v5.0 원본 그대로)
# ═══════════════════════════════════════════════════════════

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

def _s_eps_estimate(d):
    from batch.batch_earnings_estimate import run_earnings_estimate
    return run_earnings_estimate(d)


# ═══════════════════════════════════════════════════════════
#  ★ v5.1 SET A 신규 Step 함수들 (3개)
# ═══════════════════════════════════════════════════════════

def _s_cross_validation(d):
    """Step 0.5: Cross-Source Validation (★ SET A-5)
    FMP ↔ yfinance 교차검증. 실패해도 배치 중단 안 함.
    """
    try:
        from utils.cross_source_validator import run_cross_validation
        result = run_cross_validation(d)
        print(f"  Cross-Val Health: {result.get('health_score', 0):.0f}/100")
        return result
    except ImportError:
        print("  [CROSS-VAL] cross_source_validator 모듈 없음 — skip")
    except Exception as e:
        print(f"  [CROSS-VAL] Error (non-critical): {e}")


def _s_paper_trading(d):
    """Step 7.3: Paper Trading Engine (★ SET A-1)
    시그널 기반 가상 체결 → 포지션 관리 → 일일 NAV → 성과 추적.
    Trading Signals 직후 실행.
    """
    try:
        from batch.batch_paper_trading import run_paper_trading
        result = run_paper_trading(d)
        if result:
            print(f"  Paper NAV: ${result.get('nav', 0):,.2f} | "
                  f"Cum: {result.get('cum_return', 0):+.2%} | "
                  f"MDD: {result.get('mdd', 0):.2%}")
        return result
    except ImportError:
        print("  [PaperTrading] batch_paper_trading 모듈 없음 — skip")
    except Exception as e:
        print(f"  [PaperTrading] Error (non-critical): {e}")
        traceback.print_exc()


def _s_research_notes(d):
    """Step 7.7: SHAP → Research Notes (★ SET A-4)
    상위 20종목 + 등급 변경 종목에 대해 자연어 리서치 노트 자동 생성.
    """
    try:
        from analytics.shap_narrative_engine import run_daily_notes
        result = run_daily_notes(d, top_n=20)
        print(f"  Research Notes: {len(result) if result else 0}개 생성")
        return result
    except ImportError:
        print("  [ResearchNotes] shap_narrative_engine 모듈 없음 — skip")
    except Exception as e:
        print(f"  [ResearchNotes] Error (non-critical): {e}")
        traceback.print_exc()


# ═══════════════════════════════════════════════════════════
#  Step 8: 일괄 알림 — 배치 완료 후 한 번에 전부 전송
#  (기존 v5.0 알림 파이프라인 100% 보존 + A-1/A-4 알림 추가)
# ═══════════════════════════════════════════════════════════

def _s_notify_all(calc_date, results, start_time):
    """
    v4.0 — 모든 알림을 일괄 발송 (notify_data_builder + notifier)

    scheduler → notify_data_builder (계산) → notifier (전송)

    1) IC/적중률/국면확률 계산
    2) 매수 근거 카드 보강 (Goldman Conviction + Bridgewater Because)
    3) 매도 분석 보강 (MAE/MFE + 점수변화 + 역대성과)
    4) 리스크 대시보드 (VaR + Stress + 집중도)
    5) 모닝/시그널/리스크/등급변경/국면전환/배치완료 알림
    
    v5.1 추가:
    6) Paper Trading 일일 요약 (A-1)
    7) BUY 종목 Research Notes (A-4)
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
            
            spy_price = float(latest["spy_price"] or 0)
            sma_200 = float(latest.get("spy_ma200") or 0)
            vix_now = float(latest["vix_close"] or 0)
            
            # ★ BUG-09 FIX: 전일 대비 변동 계산
            spy_vs_sma200 = round((spy_price / sma_200 - 1) * 100, 1) if sma_200 > 0 else 0
            
            prev_vix = 0
            prev_spy = 0
            if len(rows) >= 2:
                prev_vix = float(rows[1].get("vix_close") or 0)
                prev_spy = float(rows[1].get("spy_price") or 0)
            
            vix_change = round(((vix_now / prev_vix - 1) * 100) if prev_vix > 0 else 0, 1)
            futures_change = round(((spy_price / prev_spy - 1) * 100) if prev_spy > 0 else 0, 2)
            
            regime_detail = {
                "spy_price": spy_price,
                "sma_200": sma_200,
                "vix_close": vix_now,
                "regime_multiplier": float(latest.get("regime_multiplier") or 1.0),
                "spy_vs_sma200": spy_vs_sma200,
                "futures_change": futures_change,
                "vix_change": vix_change,
            }

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

        # ── 매도 시그널 ──  [v5.1 FIX]
        with get_cursor() as cur:
            cur.execute("""
                SELECT ts.*, s.ticker, sec.sector_name AS sector, s.stock_id
                FROM trading_signals ts
                JOIN stocks s ON ts.stock_id = s.stock_id
                LEFT JOIN sectors sec ON s.sector_id = sec.sector_id
                WHERE ts.signal_date = %s 
                  AND ts.signal_type IN ('SELL', 'PROFIT_TAKE', 'STOP_LOSS')
                ORDER BY ts.final_score DESC NULLS LAST
            """, (calc_date,))
            for row in cur.fetchall():
                # ★ FIX: pnl_pct 재계산 (DB에 없거나 0일 때 대비)
                entry_p = float(row.get("entry_price") or 0)
                curr_p = float(row.get("current_price") or 0)
                db_pnl = float(row.get("pnl_pct") or 0)
                
                if db_pnl != 0:
                    pnl_pct = db_pnl
                elif entry_p > 0 and curr_p > 0:
                    pnl_pct = (curr_p - entry_p) / entry_p * 100
                else:
                    pnl_pct = 0

                sig = {
                    "stock_id": row["stock_id"],
                    "ticker": row["ticker"],
                    "price": curr_p,
                    "entry_price": entry_p,
                    "pnl_pct": round(pnl_pct, 2),
                    "reason": row.get("sell_reason", row.get("signal_type", "SELL")),
                    "shares": int(row.get("shares") or 0),
                    "holding_days": int(row.get("holding_days") or 0),
                }
                
                # ★ BUG-05 FIX: 0 < -15 → pnl_pct < -15
                if row.get("signal_type") == 'STOP_LOSS' and pnl_pct < -15:
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

    # ═══════════════════════════════════════════════════════
    #  ★ v5.1 추가: Paper Trading + Research Notes 알림
    # ═══════════════════════════════════════════════════════

    # (H-1) ★ Paper Trading 일일 요약
    try:
        _notify_paper_summary(calc_date)
    except Exception as e:
        print(f"  ⚠️ Paper 요약 실패: {e}")

    # (H-2) ★ BUY 종목 Research Notes
    try:
        _notify_research_notes(calc_date)
    except Exception as e:
        print(f"  ⚠️ Research Notes 실패: {e}")

    # (I) 배치 완료 → MY_SYSTEM + PUB_REPORT
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
#  ★ v5.1: Paper Trading / Research Notes Discord 헬퍼
# ═══════════════════════════════════════════════════════════

def _notify_paper_summary(calc_date):
    """★ v5.1: Paper Trading 일일 요약을 Discord에 발송"""
    try:
        from db_pool import get_cursor
        with get_cursor() as cur:
            cur.execute("""
                SELECT nav, cash, invested_value, daily_return, cumulative_return,
                       benchmark_cumulative, active_return, position_count,
                       drawdown, max_drawdown
                FROM paper_daily_snapshot
                WHERE portfolio_id = 1 AND snap_date = %s
            """, (calc_date,))
            snap = cur.fetchone()
        
        if not snap:
            return

        nav = float(snap["nav"])
        cum = float(snap["cumulative_return"] or 0)
        bench_cum = float(snap["benchmark_cumulative"] or 0)
        mdd = float(snap["max_drawdown"] or 0)
        pos = int(snap["position_count"] or 0)

        from notifier import send_to_channel
        msg = (
            f"**📈 Paper Portfolio Daily Update**\n"
            f"> NAV: ${nav:,.2f} | Positions: {pos}\n"
            f"> Daily: {float(snap['daily_return'] or 0):+.2%} | "
            f"Cumulative: {cum:+.2%}\n"
            f"> SPY Cumulative: {bench_cum:+.2%} | "
            f"Active: {cum - bench_cum:+.2%}\n"
            f"> Drawdown: {float(snap['drawdown'] or 0):.2%} | "
            f"MDD: {mdd:.2%}"
        )
        send_to_channel("MY_SYSTEM", msg)
        print(f"  ✅ Paper 요약 → MY_SYSTEM (NAV=${nav:,.0f})")
    except ImportError:
        # send_to_channel이 없으면 notifier의 다른 방법 시도
        pass
    except Exception as e:
        print(f"  ⚠️ Paper→Discord: {e}")


def _notify_research_notes(calc_date):
    """★ v5.1: BUY 시그널 종목의 리서치 노트를 Discord에 발송"""
    try:
        from db_pool import get_cursor
        with get_cursor() as cur:
            cur.execute("""
                SELECT rn.discord_md
                FROM research_notes rn
                WHERE rn.calc_date = %s
                ORDER BY rn.percentile DESC
                LIMIT 5
            """, (calc_date,))
            notes = cur.fetchall()
        
        if not notes:
            return

        msg_parts = ["**📋 AI Research Notes (Top 종목)**\n"]
        for note in notes:
            if note.get("discord_md"):
                msg_parts.append(note["discord_md"])
        
        if len(msg_parts) > 1:
            full_msg = "\n\n".join(msg_parts)
            if len(full_msg) > 1900:
                full_msg = full_msg[:1900] + "\n...더 많은 노트는 대시보드에서 확인"
            
            from notifier import send_to_channel
            send_to_channel("MY_SYSTEM", full_msg)
            print(f"  ✅ Research Notes → MY_SYSTEM ({len(notes)}건)")
    except ImportError:
        pass
    except Exception as e:
        print(f"  ⚠️ Notes→Discord: {e}")


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

            cur.execute("""
                SELECT COUNT(*) FILTER (WHERE signal_type IN ('SELL','PROFIT_TAKE','STOP_LOSS')) as wins,
                       COUNT(*) as total
                FROM trading_signals
                WHERE calc_date >= %s AND signal_type IN ('SELL', 'PROFIT_TAKE', 'STOP_LOSS')
            """, (week_start,))
            row = cur.fetchone()
            if row and row["total"] > 0:
                win_rate = row["wins"] / row["total"] * 100

            cur.execute("""
                SELECT s.ticker, ts.final_score
                FROM trading_signals ts
                JOIN stocks s ON ts.stock_id = s.stock_id
                WHERE ts.signal_date >= %s AND ts.signal_type IN ('SELL', 'PROFIT_TAKE', 'STOP_LOSS')
                ORDER BY ts.final_score DESC NULLS LAST DESC LIMIT 1
            """, (week_start,))
            row = cur.fetchone()
            if row:
                best_ticker = row["ticker"]
                best_pnl = float(0 or 0)

            cur.execute("""
                SELECT s.ticker, ts.final_score
                FROM trading_signals ts
                JOIN stocks s ON ts.stock_id = s.stock_id
                WHERE ts.signal_date >= %s AND ts.signal_type IN ('SELL', 'PROFIT_TAKE', 'STOP_LOSS')
                ORDER BY ts.final_score DESC NULLS LAST ASC LIMIT 1
            """, (week_start,))
            row = cur.fetchone()
            if row:
                worst_ticker = row["ticker"]
                worst_pnl = float(0 or 0)
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
                SELECT COUNT(*) FILTER (WHERE signal_type IN ('SELL','PROFIT_TAKE','STOP_LOSS')) as wins,
                       COUNT(*) as total
                FROM trading_signals
                WHERE calc_date >= %s AND calc_date <= %s
                  AND signal_type IN ('SELL', 'PROFIT_TAKE', 'STOP_LOSS')
            """, (month_start, prev_month_end))
            row = cur.fetchone()
            if row and row["total"] > 0:
                win_rate = row["wins"] / row["total"] * 100

            cur.execute("""
                SELECT s.ticker, ts.final_score
                FROM trading_signals ts
                JOIN stocks s ON ts.stock_id = s.stock_id
                WHERE ts.signal_date >= %s AND ts.signal_date <= %s
                  AND ts.signal_type IN ('SELL', 'PROFIT_TAKE', 'STOP_LOSS')
                ORDER BY ts.final_score DESC NULLS LAST DESC LIMIT 1
            """, (month_start, prev_month_end))
            row = cur.fetchone()
            if row:
                best_ticker = row["ticker"]
                best_pnl = float(0 or 0)

            cur.execute("""
                SELECT s.ticker, ts.final_score
                FROM trading_signals ts
                JOIN stocks s ON ts.stock_id = s.stock_id
                WHERE ts.signal_date >= %s AND ts.signal_date <= %s
                  AND ts.signal_type IN ('SELL', 'PROFIT_TAKE', 'STOP_LOSS')
                ORDER BY ts.final_score DESC NULLS LAST ASC LIMIT 1
            """, (month_start, prev_month_end))
            row = cur.fetchone()
            if row:
                worst_ticker = row["ticker"]
                worst_pnl = float(0 or 0)
    except Exception as e:
        print(f"  ⚠️ 월간 트레이드 통계 실패: {e}")

    brinson = None
    try:
        from notify_data_builder import build_weekly_brinson
        brinson = build_weekly_brinson(d)
    except Exception:
        pass

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
    print("  QUANT AI v5.1 — Batch Scheduler")
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
    parser = argparse.ArgumentParser(description="QUANT AI v5.1 Batch Scheduler")
    parser.add_argument("--date", type=str, default=None, help="YYYY-MM-DD (수동 실행)")
    parser.add_argument("--now", action="store_true", help="즉시 1회 실행")
    parser.add_argument("--backtest", action="store_true", help="Walk-Forward 백테스트 실행 (A-2)")
    parser.add_argument("--backtest-track", choices=["ic", "portfolio", "both"], default="both",
                        help="백테스트 트랙: ic / portfolio / both")
    args = parser.parse_args()

    if args.backtest:
        # ★ A-2: Walk-Forward 백테스트 (수동 실행)
        print("\n" + "=" * 60)
        print("  Walk-Forward Backtest (SET A-2)")
        print("=" * 60)
        try:
            from backtest.walk_forward_engine import run_ic_backtest, run_portfolio_backtest
            if args.backtest_track in ("ic", "both"):
                run_ic_backtest()
            if args.backtest_track in ("portfolio", "both"):
                run_portfolio_backtest()
        except ImportError as e:
            print(f"  ❌ 백테스트 모듈 없음: {e}")

    elif args.date:
        calc_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        run_all(calc_date)
    elif args.now:
        run_all()
    else:
        start_scheduler()


def _s_eps_estimate(d):
    from batch.batch_earnings_estimate import run_earnings_estimate
    return run_earnings_estimate(d)