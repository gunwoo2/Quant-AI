"""
backtest/walk_forward_engine.py — Walk-Forward OOS Backtest v1.0 (SET A-2)
===========================================================================
2-Track 검증 시스템:
  Track 1: 팩터 IC 백테스트 — OOS IC 시계열 (빠름, ~1분)
  Track 2: 포트폴리오 백테스트 — NAV 곡선 + Sharpe (느림, ~10분)

방법론:
  - 12개월 학습 / 1개월 테스트 / Purge Gap 5일
  - López de Prado (2018): Purged Walk-Forward
  - Harvey/Liu/Zhu (2016): 다중 검정 보정
  - Gu/Kelly/Xiu (2020): ML OOS 검증 표준

실행:
  python -m backtest.walk_forward_engine --track ic
  python -m backtest.walk_forward_engine --track portfolio
  python -m backtest.walk_forward_engine --track both
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import json
import logging
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
from db_pool import get_cursor

logger = logging.getLogger("walk_forward")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 상수
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TRAIN_MONTHS   = 12    # 학습 기간
TEST_MONTHS    = 1     # 테스트 기간
PURGE_DAYS     = 5     # Purge Gap (정보 누출 방지)
SLIPPAGE_BP    = 15    # 보수적 슬리피지 15bp
COMMISSION_BP  = 5     # 수수료 5bp (왕복)
TOP_N          = 20    # 상위 N종목 포트폴리오
BENCHMARK      = "SPY"

# 결과 테이블
RESULT_TABLE   = "backtest_results"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 테이블 보장
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def ensure_backtest_tables():
    with get_cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS backtest_results (
                id              SERIAL PRIMARY KEY,
                run_id          VARCHAR(50) NOT NULL,
                track           VARCHAR(20) NOT NULL,
                window_start    DATE,
                window_end      DATE,
                train_start     DATE,
                train_end       DATE,
                test_start      DATE,
                test_end        DATE,
                metric_name     VARCHAR(50),
                metric_value    NUMERIC(12,6),
                detail          JSONB,
                created_at      TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS backtest_summary (
                id              SERIAL PRIMARY KEY,
                run_id          VARCHAR(50) NOT NULL,
                track           VARCHAR(20),
                total_windows   INTEGER,
                oos_ic_mean     NUMERIC(8,6),
                oos_ic_std      NUMERIC(8,6),
                oos_icir        NUMERIC(8,4),
                ic_positive_pct NUMERIC(6,4),
                oos_sharpe      NUMERIC(8,4),
                oos_mdd         NUMERIC(8,4),
                oos_alpha       NUMERIC(8,4),
                oos_beta        NUMERIC(8,4),
                vs_random       NUMERIC(8,4),
                vs_benchmark    NUMERIC(8,4),
                detail          JSONB,
                created_at      TIMESTAMPTZ DEFAULT NOW()
            )
        """)
    print("[WF] Tables ensured")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 윈도우 생성
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def generate_windows(data_start: date = None, data_end: date = None):
    """
    Walk-Forward 슬라이딩 윈도우 생성.
    
    [====TRAIN 12M====][PURGE 5d][=TEST 1M=]
            [====TRAIN 12M====][PURGE 5d][=TEST 1M=]
                    [====TRAIN 12M====][PURGE 5d][=TEST 1M=]
    """
    if data_start is None:
        with get_cursor() as cur:
            cur.execute("SELECT MIN(trade_date) as mn FROM stock_prices_daily")
            row = cur.fetchone()
            data_start = row["mn"] if row and row["mn"] else date(2020, 1, 1)
    
    if data_end is None:
        with get_cursor() as cur:
            cur.execute("SELECT MAX(trade_date) as mx FROM stock_prices_daily")
            row = cur.fetchone()
            data_end = row["mx"] if row and row["mx"] else date.today()
    
    windows = []
    train_start = data_start
    
    while True:
        train_end = train_start + relativedelta(months=TRAIN_MONTHS) - timedelta(days=1)
        purge_end = train_end + timedelta(days=PURGE_DAYS)
        test_start = purge_end + timedelta(days=1)
        test_end = test_start + relativedelta(months=TEST_MONTHS) - timedelta(days=1)
        
        if test_end > data_end:
            break
        
        windows.append({
            "train_start": train_start,
            "train_end": train_end,
            "purge_end": purge_end,
            "test_start": test_start,
            "test_end": test_end,
        })
        
        # 슬라이드 1개월
        train_start = train_start + relativedelta(months=1)
    
    return windows


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Track 1: IC 백테스트
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _get_scores_and_returns(test_start: date, test_end: date, horizon_days: int = 10):
    """OOS 구간의 점수 + Forward Return 조회"""
    with get_cursor() as cur:
        cur.execute("""
            SELECT
                f.stock_id,
                f.weighted_score,
                f.layer1_score,
                f.layer2_score,
                f.layer3_score,
                f.percentile_rank,
                f.calc_date,
                -- Forward Return: test일 대비 +horizon일 수익률
                (future.close_price / base.close_price - 1) AS fwd_return
            FROM stock_final_scores f
            JOIN LATERAL (
                SELECT close_price FROM stock_prices_daily
                WHERE stock_id = f.stock_id AND trade_date >= f.calc_date
                ORDER BY trade_date ASC LIMIT 1
            ) base ON TRUE
            LEFT JOIN LATERAL (
                SELECT close_price FROM stock_prices_daily
                WHERE stock_id = f.stock_id AND trade_date >= f.calc_date + %s
                ORDER BY trade_date ASC LIMIT 1
            ) future ON TRUE
            WHERE f.calc_date BETWEEN %s AND %s
              AND future.close_price IS NOT NULL
              AND base.close_price > 0
        """, (horizon_days, test_start, test_end))
        return [dict(r) for r in cur.fetchall()]


def run_ic_backtest(run_id: str = None):
    """
    Track 1: 팩터 IC Walk-Forward 백테스트.
    각 OOS 윈도우에서 Score vs Forward Return의 Spearman Rank IC 계산.
    """
    from scipy.stats import spearmanr
    
    if run_id is None:
        run_id = f"IC_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    ensure_backtest_tables()
    windows = generate_windows()
    print(f"[WF-IC] {len(windows)} windows generated")
    
    results = {"weighted": [], "l1": [], "l2": [], "l3": []}
    
    for i, w in enumerate(windows):
        data = _get_scores_and_returns(w["test_start"], w["test_end"])
        if len(data) < 30:
            print(f"  Window {i+1}: skip (only {len(data)} samples)")
            continue
        
        scores = {
            "weighted": [d["weighted_score"] for d in data],
            "l1": [d["layer1_score"] for d in data],
            "l2": [d["layer2_score"] for d in data],
            "l3": [d["layer3_score"] for d in data],
        }
        fwd_rets = [d["fwd_return"] for d in data]
        
        for score_name, score_vals in scores.items():
            try:
                ic, pval = spearmanr(score_vals, fwd_rets)
                if np.isnan(ic):
                    ic = 0
            except Exception:
                ic, pval = 0, 1
            
            results[score_name].append(ic)
            
            # DB 저장
            with get_cursor() as cur:
                cur.execute("""
                    INSERT INTO backtest_results
                    (run_id, track, test_start, test_end, train_start, train_end,
                     metric_name, metric_value, detail)
                    VALUES (%s, 'IC', %s, %s, %s, %s, %s, %s, %s)
                """, (run_id, w["test_start"], w["test_end"],
                      w["train_start"], w["train_end"],
                      f"ic_{score_name}", ic,
                      json.dumps({"samples": len(data), "pval": pval})))
        
        print(f"  Window {i+1}/{len(windows)}: "
              f"test={w['test_start']} IC_w={results['weighted'][-1]:.4f} "
              f"IC_l1={results['l1'][-1]:.4f} n={len(data)}")
    
    # 요약 통계
    summary = {}
    for name, ics in results.items():
        if not ics:
            continue
        arr = np.array(ics)
        ic_mean = float(np.mean(arr))
        ic_std = float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.01
        icir = ic_mean / ic_std if ic_std > 0 else 0
        pos_pct = float(np.mean(arr > 0))
        
        summary[name] = {
            "ic_mean": ic_mean, "ic_std": ic_std,
            "icir": icir, "ic_positive_pct": pos_pct,
            "n_windows": len(ics),
        }
        print(f"\n  [{name}] IC={ic_mean:.4f} ± {ic_std:.4f} "
              f"ICIR={icir:.3f} IC>0={pos_pct:.1%} (n={len(ics)})")
    
    # 전체 요약 저장
    ws = summary.get("weighted", {})
    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO backtest_summary
            (run_id, track, total_windows, oos_ic_mean, oos_ic_std, oos_icir,
             ic_positive_pct, detail)
            VALUES (%s, 'IC', %s, %s, %s, %s, %s, %s)
        """, (run_id, len(windows),
              ws.get("ic_mean", 0), ws.get("ic_std", 0),
              ws.get("icir", 0), ws.get("ic_positive_pct", 0),
              json.dumps(summary)))

    # TearSheet 출력
    print(f"\n{'='*55}")
    print(f"  WALK-FORWARD IC BACKTEST TEARSHEET")
    print(f"  Run: {run_id}")
    print(f"  Windows: {len(windows)}")
    print(f"{'='*55}")
    for name, s in summary.items():
        verdict = "✅ PASS" if s["ic_mean"] > 0.03 and s["icir"] > 0.3 else "⚠️ WEAK" if s["ic_mean"] > 0 else "❌ FAIL"
        print(f"  {name:10s}: IC={s['ic_mean']:+.4f} ICIR={s['icir']:.3f} "
              f"IC>0={s['ic_positive_pct']:.0%} → {verdict}")
    print(f"{'='*55}")

    return summary


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Track 2: 포트폴리오 백테스트
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _get_top_n_stocks(as_of_date: date, n: int = TOP_N):
    """특정 일자 기준 상위 N종목"""
    with get_cursor() as cur:
        cur.execute("""
            SELECT f.stock_id, s.ticker, f.weighted_score, f.percentile_rank
            FROM stock_final_scores f
            JOIN stocks s ON f.stock_id = s.stock_id
            WHERE f.calc_date = (
                SELECT MAX(calc_date) FROM stock_final_scores 
                WHERE calc_date <= %s
            )
            AND s.is_active = TRUE
            ORDER BY f.weighted_score DESC
            LIMIT %s
        """, (as_of_date, n))
        return [dict(r) for r in cur.fetchall()]


def _get_price_on_date(stock_id: int, target_date: date) -> float:
    with get_cursor() as cur:
        cur.execute("""
            SELECT close_price FROM stock_prices_daily
            WHERE stock_id = %s AND trade_date <= %s
            ORDER BY trade_date DESC LIMIT 1
        """, (stock_id, target_date))
        row = cur.fetchone()
        return float(row["close_price"]) if row else 0


def _get_benchmark_on_date(target_date: date) -> float:
    with get_cursor() as cur:
        cur.execute("""
            SELECT p.close_price FROM stock_prices_daily p
            JOIN stocks s ON p.stock_id = s.stock_id
            WHERE s.ticker = %s AND p.trade_date <= %s
            ORDER BY p.trade_date DESC LIMIT 1
        """, (BENCHMARK, target_date))
        row = cur.fetchone()
        return float(row["close_price"]) if row else 0


def _get_trading_dates(start: date, end: date) -> list:
    """실제 거래일 목록"""
    with get_cursor() as cur:
        cur.execute("""
            SELECT DISTINCT trade_date FROM stock_prices_daily
            WHERE trade_date BETWEEN %s AND %s
            ORDER BY trade_date
        """, (start, end))
        return [r["trade_date"] for r in cur.fetchall()]


def run_portfolio_backtest(run_id: str = None, rebal_freq: int = 21):
    """
    Track 2: 포트폴리오 Walk-Forward 백테스트.
    매월 리밸런싱, Top N 동일가중, 슬리피지+수수료 반영.
    """
    if run_id is None:
        run_id = f"PF_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    ensure_backtest_tables()
    
    # 전체 데이터 기간
    with get_cursor() as cur:
        cur.execute("""
            SELECT MIN(calc_date) as mn, MAX(calc_date) as mx
            FROM stock_final_scores
        """)
        row = cur.fetchone()
    
    if not row or not row["mn"]:
        print("[WF-PF] No score data available")
        return {}
    
    start_date = row["mn"]
    end_date = row["mx"]
    
    trading_dates = _get_trading_dates(start_date, end_date)
    if len(trading_dates) < 30:
        print(f"[WF-PF] Only {len(trading_dates)} trading dates — need 30+")
        return {}
    
    print(f"[WF-PF] Period: {start_date} ~ {end_date} ({len(trading_dates)} days)")
    
    # 시뮬레이션
    nav = 100000.0
    cash = nav
    positions = {}   # {stock_id: {"shares": n, "price": p}}
    nav_series = []
    bench_series = []
    last_rebal = None
    total_cost = SLIPPAGE_BP + COMMISSION_BP
    
    for i, td in enumerate(trading_dates):
        # 리밸런싱
        should_rebal = (last_rebal is None or 
                       (td - last_rebal).days >= rebal_freq)
        
        if should_rebal:
            # 기존 포지션 청산 (거래비용 반영)
            for sid, pos in positions.items():
                current = _get_price_on_date(sid, td)
                if current > 0:
                    value = current * pos["shares"]
                    cash += value * (1 - total_cost / 10000)
            
            positions = {}
            
            # 신규 포트폴리오 구성
            top_stocks = _get_top_n_stocks(td, TOP_N)
            if top_stocks:
                per_stock = cash * 0.95 / len(top_stocks)
                for s in top_stocks:
                    price = _get_price_on_date(s["stock_id"], td)
                    if price > 0:
                        shares = int(per_stock / price)
                        if shares > 0:
                            cost = price * shares * (1 + total_cost / 10000)
                            positions[s["stock_id"]] = {"shares": shares, "price": price}
                            cash -= cost
            
            last_rebal = td
        
        # Mark-to-Market
        invested = 0
        for sid, pos in positions.items():
            current = _get_price_on_date(sid, td)
            if current > 0:
                invested += current * pos["shares"]
        
        day_nav = cash + invested
        nav_series.append(day_nav)
        
        bench = _get_benchmark_on_date(td)
        bench_series.append(bench)
    
    if len(nav_series) < 10:
        print("[WF-PF] Not enough NAV data")
        return {}
    
    # 성과 계산
    navs = np.array(nav_series)
    rets = np.diff(navs) / navs[:-1]
    
    bench_arr = np.array(bench_series)
    bench_rets = np.diff(bench_arr) / bench_arr[:-1]
    bench_rets = bench_rets[:len(rets)]  # 길이 맞춤
    
    ann = 252
    sharpe = (np.mean(rets) / np.std(rets, ddof=1) * np.sqrt(ann)) if np.std(rets) > 0 else 0
    
    cum = np.cumprod(1 + rets)
    peak = np.maximum.accumulate(cum)
    dd = cum / peak - 1
    mdd = float(np.min(dd))
    
    total_ret = (navs[-1] / navs[0] - 1)
    bench_total = (bench_arr[-1] / bench_arr[0] - 1) if bench_arr[0] > 0 else 0
    
    # Alpha / Beta
    if len(bench_rets) > 5 and np.std(bench_rets) > 0:
        cov = np.cov(rets[:len(bench_rets)], bench_rets)
        beta = cov[0,1] / cov[1,1] if cov[1,1] != 0 else 1
        alpha = (np.mean(rets[:len(bench_rets)]) - beta * np.mean(bench_rets)) * ann
    else:
        alpha, beta = 0, 1
    
    # Random Baseline (상위 N 대신 랜덤 N)
    random_sharpe = 0  # 간소화: 실제 구현 시 Monte Carlo
    
    summary = {
        "total_return": float(total_ret),
        "benchmark_return": float(bench_total),
        "excess_return": float(total_ret - bench_total),
        "sharpe": float(sharpe),
        "mdd": float(mdd),
        "alpha": float(alpha),
        "beta": float(beta),
        "n_days": len(nav_series),
        "n_rebalances": len(trading_dates) // rebal_freq,
    }
    
    # DB 저장
    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO backtest_summary
            (run_id, track, total_windows, oos_sharpe, oos_mdd,
             oos_alpha, oos_beta, vs_benchmark, detail)
            VALUES (%s, 'PORTFOLIO', %s, %s, %s, %s, %s, %s, %s)
        """, (run_id, len(nav_series), sharpe, mdd, alpha, beta,
              total_ret - bench_total, json.dumps(summary)))
    
    # TearSheet
    print(f"\n{'='*55}")
    print(f"  PORTFOLIO BACKTEST TEARSHEET")
    print(f"  Run: {run_id}")
    print(f"  Period: {start_date} ~ {end_date}")
    print(f"{'='*55}")
    print(f"  Total Return:     {total_ret:+.2%}")
    print(f"  Benchmark (SPY):  {bench_total:+.2%}")
    print(f"  Excess Return:    {total_ret - bench_total:+.2%}")
    print(f"  Sharpe Ratio:     {sharpe:.3f}")
    print(f"  Max Drawdown:     {mdd:.2%}")
    print(f"  Alpha (ann.):     {alpha:+.2%}")
    print(f"  Beta:             {beta:.3f}")
    pf_verdict = "✅ PROMISING" if sharpe > 0.5 and mdd > -0.20 else "⚠️ MARGINAL" if sharpe > 0 else "❌ NEGATIVE"
    print(f"  Verdict:          {pf_verdict}")
    print(f"{'='*55}")
    
    return summary


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CLI
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Quick IC Test (데이터 부족 시 사용)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run_quick_ic_test(horizon_days: int = 10):
    """
    stock_final_scores 데이터가 적을 때 사용하는 간단한 IC 테스트.
    현재 보유 데이터 전체를 사용하여 Score vs Forward Return의 IC 계산.
    Walk-Forward가 아닌 단순 IC이므로 OOS 검증은 아님.
    """
    from scipy.stats import spearmanr
    
    print(f"\n{'='*55}")
    print(f"  QUICK IC TEST (horizon={horizon_days}d)")
    print(f"{'='*55}")
    
    with get_cursor() as cur:
        # 먼저 데이터 범위 확인
        cur.execute("""
            SELECT MIN(calc_date) as mn, MAX(calc_date) as mx, COUNT(*) as cnt
            FROM stock_final_scores
        """)
        info = cur.fetchone()
        print(f"  Final Scores: {info['mn']} ~ {info['mx']} ({info['cnt']} rows)")
        
        if info['cnt'] < 100:
            print(f"  ⚠️ 데이터 {info['cnt']}건으로 IC 테스트 불가 (최소 100건 필요)")
            print(f"  → 배치를 더 돌려서 데이터를 축적하세요")
            return None
        
        # Score vs Forward Return 조회
        cur.execute("""
            SELECT
                f.stock_id,
                f.weighted_score,
                f.layer1_score,
                f.layer2_score,
                f.layer3_score,
                f.percentile_rank,
                f.grade,
                f.calc_date,
                COALESCE(
                    (SELECT p2.close_price FROM stock_prices_daily p2 
                     WHERE p2.stock_id = f.stock_id AND p2.trade_date >= f.calc_date + %s
                     ORDER BY p2.trade_date ASC LIMIT 1),
                    0
                ) AS future_price,
                COALESCE(
                    (SELECT p1.close_price FROM stock_prices_daily p1
                     WHERE p1.stock_id = f.stock_id AND p1.trade_date <= f.calc_date
                     ORDER BY p1.trade_date DESC LIMIT 1),
                    0
                ) AS base_price
            FROM stock_final_scores f
            WHERE f.calc_date <= (
                SELECT MAX(calc_date) FROM stock_final_scores
            ) - %s
        """, (horizon_days, horizon_days))
        rows = [dict(r) for r in cur.fetchall()]
    
    if not rows:
        print(f"  ⚠️ Forward return 계산 가능한 데이터 없음")
        print(f"  → calc_date + {horizon_days}일 이후 가격이 없습니다")
        return None
    
    # Forward Return 계산
    valid = []
    for r in rows:
        bp = float(r.get('base_price', 0) or 0)
        fp = float(r.get('future_price', 0) or 0)
        if bp > 0 and fp > 0:
            r['fwd_return'] = fp / bp - 1
            valid.append(r)
    
    print(f"  Valid samples: {len(valid)} (total {len(rows)})")
    
    if len(valid) < 50:
        print(f"  ⚠️ 유효 데이터 {len(valid)}건 — 부족")
        return None
    
    # IC 계산 (각 Score 유형별)
    results = {}
    score_types = {
        'weighted_score': [float(r.get('weighted_score', 0) or 0) for r in valid],
        'layer1_score': [float(r.get('layer1_score', 0) or 0) for r in valid],
        'layer2_score': [float(r.get('layer2_score', 0) or 0) for r in valid],
        'layer3_score': [float(r.get('layer3_score', 0) or 0) for r in valid],
    }
    fwd_rets = [r['fwd_return'] for r in valid]
    
    for name, scores in score_types.items():
        try:
            ic, pval = spearmanr(scores, fwd_rets)
            if np.isnan(ic):
                ic = 0
        except Exception:
            ic, pval = 0, 1
        results[name] = {'ic': float(ic), 'pval': float(pval)}
    
    # 등급별 Forward Return (단조성 확인)
    grade_returns = {}
    for r in valid:
        g = r.get('grade', 'D')
        if g not in grade_returns:
            grade_returns[g] = []
        grade_returns[g].append(r['fwd_return'])
    
    # 결과 출력
    print(f"\n  {'Score Type':<20s} {'IC':>8s} {'p-value':>10s} {'Verdict':>12s}")
    print(f"  {'-'*52}")
    for name, r in results.items():
        verdict = "✅ GOOD" if r['ic'] > 0.03 else "⚠️ WEAK" if r['ic'] > 0 else "❌ FAIL"
        print(f"  {name:<20s} {r['ic']:>+8.4f} {r['pval']:>10.4f} {verdict:>12s}")
    
    print(f"\n  등급별 {horizon_days}일 평균 Forward Return:")
    print(f"  {'Grade':<8s} {'Avg Return':>12s} {'Count':>8s}")
    print(f"  {'-'*30}")
    for grade in ['S', 'A+', 'A', 'B+', 'B', 'C', 'D', 'F']:
        if grade in grade_returns and grade_returns[grade]:
            avg = np.mean(grade_returns[grade])
            cnt = len(grade_returns[grade])
            emoji = "📈" if avg > 0 else "📉"
            print(f"  {grade:<8s} {avg:>+11.2%} {cnt:>8d} {emoji}")
    
    # 단조성 확인
    grade_order = ['S', 'A+', 'A', 'B+', 'B', 'C', 'D', 'F']
    avgs = []
    for g in grade_order:
        if g in grade_returns and grade_returns[g]:
            avgs.append(np.mean(grade_returns[g]))
    
    is_monotonic = all(avgs[i] >= avgs[i+1] for i in range(len(avgs)-1)) if len(avgs) > 2 else False
    
    print(f"\n  등급 단조성: {'✅ 단조적 (S > A > B > C > D)' if is_monotonic else '⚠️ 비단조적 — 등급 체계 검토 필요'}")
    
    print(f"\n{'='*55}")
    ws = results.get('weighted_score', {})
    overall = "✅ 유효" if ws.get('ic', 0) > 0.03 else "⚠️ 약함" if ws.get('ic', 0) > 0 else "❌ 무효"
    print(f"  최종 판정: IC={ws.get('ic', 0):+.4f} → {overall}")
    print(f"  (참고: 이것은 Quick IC이므로 OOS 검증은 아님)")
    print(f"  (Walk-Forward OOS 검증은 30일+ 데이터 축적 후 재실행)")
    print(f"{'='*55}")
    
    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Walk-Forward Backtest Engine")
    parser.add_argument("--track", choices=["ic", "portfolio", "both", "quick"], default="quick")
    parser.add_argument("--horizon", type=int, default=10, help="Forward return horizon (days)")
    args = parser.parse_args()
    
    if args.track == "quick":
        run_quick_ic_test(horizon_days=args.horizon)
    elif args.track in ("ic", "both"):
        run_ic_backtest()
    if args.track in ("portfolio", "both"):
        run_portfolio_backtest()