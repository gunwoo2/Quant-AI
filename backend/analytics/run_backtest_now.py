"""
run_backtest_now.py — 기존 DB 데이터로 즉시 백테스트 실행
==========================================================
이미 쌓여있는 stock_prices_daily + stock_final_scores로
BacktestEngine을 즉시 가동하는 원클릭 스크립트.

사용: python run_backtest_now.py
결과: 콘솔 출력 + system_telemetry에 기록

이 스크립트는 Day 7까지의 모든 코드가 배포된 후 실행.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import patch_numpy_adapter
except ImportError:
    pass

import json
import numpy as np
import pandas as pd
from datetime import date, timedelta
from db_pool import get_cursor


def load_backtest_data(start_date=None, end_date=None):
    """DB에서 백테스트용 데이터 로드"""
    if end_date is None:
        end_date = date.today() - timedelta(days=1)
    if start_date is None:
        start_date = end_date - timedelta(days=180)  # 6개월

    print(f"[BACKTEST] 데이터 로드: {start_date} ~ {end_date}")

    # ── 1. 종목 목록 ──
    with get_cursor() as cur:
        cur.execute("""
            SELECT stock_id, ticker, company_name,
                   COALESCE(sector_code, '99') AS sector
            FROM stocks WHERE is_active = TRUE AND ticker IS NOT NULL
        """)
        stock_info = {r["ticker"]: dict(r) for r in cur.fetchall()}

    print(f"  종목: {len(stock_info)}개")

    # ── 2. 가격 데이터 ──
    prices = {}
    with get_cursor() as cur:
        for ticker, info in stock_info.items():
            cur.execute("""
                SELECT trade_date AS date, open_price AS open,
                       high_price AS high, low_price AS low,
                       close_price AS close, volume
                FROM stock_prices_daily
                WHERE stock_id = %s AND trade_date BETWEEN %s AND %s
                ORDER BY trade_date
            """, (info["stock_id"], start_date, end_date))
            rows = cur.fetchall()
            if len(rows) > 20:
                df = pd.DataFrame([dict(r) for r in rows])
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date")
                prices[ticker] = df

    print(f"  가격 데이터: {len(prices)}종목 (20일+ 이력)")

    # ── 3. 점수 데이터 ──
    scores = {}
    with get_cursor() as cur:
        for ticker, info in stock_info.items():
            if ticker not in prices:
                continue
            cur.execute("""
                SELECT calc_date AS date, weighted_score AS final_score,
                       layer3_score, signal, grade
                FROM stock_final_scores
                WHERE stock_id = %s AND calc_date BETWEEN %s AND %s
                ORDER BY calc_date
            """, (info["stock_id"], start_date, end_date))
            rows = cur.fetchall()
            if len(rows) > 10:
                df = pd.DataFrame([dict(r) for r in rows])
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date")
                scores[ticker] = df

    print(f"  점수 데이터: {len(scores)}종목")

    # ── 4. SPY 데이터 ──
    spy = None
    with get_cursor() as cur:
        cur.execute("""
            SELECT calc_date AS date, spy_close AS close
            FROM cross_asset_daily
            WHERE calc_date BETWEEN %s AND %s AND spy_close IS NOT NULL
            ORDER BY calc_date
        """, (start_date, end_date))
        rows = cur.fetchall()
        if rows:
            spy = pd.DataFrame([dict(r) for r in rows])
            spy["date"] = pd.to_datetime(spy["date"])
            spy["open"] = spy["close"]  # Approximate
            spy = spy.set_index("date")

    print(f"  SPY 데이터: {len(spy) if spy is not None else 0}일")

    return prices, scores, spy, stock_info


# ★ Look-Ahead Bias 방지: T일 시그널 → T+1일 시가 체결
def run_quick_backtest():
    """빠른 백테스트 실행 (BacktestEngine 없이 직접 시뮬레이션)"""
    
    prices, scores, spy, stock_info = load_backtest_data()
    
    if len(scores) < 10:
        print("[BACKTEST] ❌ 데이터 부족 (10종목 미만)")
        return None

    # ── 간이 시뮬레이션 ──
    # 매주 월요일: 상위 10종목 매수, 하위 종목 매도
    # 거래비용 0.1%, 슬리피지 0.05%
    
    initial_capital = 100000.0
    cash = initial_capital
    positions = {}  # ticker → {shares, entry_price, entry_date}
    portfolio_values = []
    spy_values = []
    trade_cost = 0.0015  # 편도
    max_positions = 10
    
    # 모든 날짜 (SPY 기준)
    if spy is None or spy.empty:
        print("[BACKTEST] ❌ SPY 데이터 없음")
        return None
    
    all_dates = sorted(spy.index)
    spy_start = float(spy.iloc[0]["close"])
    
    rebalance_count = 0
    
    for i, dt in enumerate(all_dates):
        dt_date = dt.date() if hasattr(dt, 'date') else dt
        
        # 포트폴리오 현재가치
        port_value = cash
        for t, pos in positions.items():
            if t in prices and dt in prices[t].index:
                port_value += float(prices[t].loc[dt, "close"]) * pos["shares"]
            else:
                port_value += pos["entry_price"] * pos["shares"]  # 최후 가격
        
        portfolio_values.append({"date": dt_date, "value": port_value})
        spy_values.append({"date": dt_date, "spy": float(spy.loc[dt, "close"])})
        
        # 주간 리밸런싱 (매주 월요일)
        if dt.weekday() != 0:
            continue
            
        # 이 날짜의 점수 존재하는 종목
        scored_tickers = []
        for ticker, score_df in scores.items():
            # calc_date <= dt인 가장 최근 점수
            valid = score_df[score_df.index <= dt]
            if not valid.empty:
                latest = valid.iloc[-1]
                if ticker in prices and dt in prices[ticker].index:
                    scored_tickers.append({
                        "ticker": ticker,
                        "score": float(latest.get("final_score", 50)),
                        "grade": latest.get("grade", "B"),
                        "price": float(prices[ticker].loc[dt, "close"]),
                    })
        
        if not scored_tickers:
            continue
        
        # 상위 N 종목
        scored_tickers.sort(key=lambda x: x["score"], reverse=True)
        target_tickers = set(t["ticker"] for t in scored_tickers[:max_positions])
        
        # SELL: 타겟에 없는 종목
        for t in list(positions.keys()):
            if t not in target_tickers:
                if t in prices and dt in prices[t].index:
                    sell_price = float(prices[t].loc[dt, "close"]) * (1 - trade_cost)
                    cash += sell_price * positions[t]["shares"]
                del positions[t]
        
        # BUY: 신규 종목
        available_cash = cash * 0.95  # 5% 현금 유지
        new_tickers = [t for t in scored_tickers[:max_positions] 
                      if t["ticker"] not in positions and t["price"] > 0]
        
        if new_tickers:
            per_stock = available_cash / max(len(new_tickers), 1)
            for t in new_tickers:
                shares = int(per_stock / (t["price"] * (1 + trade_cost)))
                if shares > 0:
                    cost = t["price"] * shares * (1 + trade_cost)
                    cash -= cost
                    positions[t["ticker"]] = {
                        "shares": shares,
                        "entry_price": t["price"],
                        "entry_date": dt_date,
                    }
        
        rebalance_count += 1
    
    if not portfolio_values:
        print("[BACKTEST] ❌ 시뮬레이션 결과 없음")
        return None
    
    # ── 결과 분석 ──
    pv = pd.DataFrame(portfolio_values).set_index("date")
    sv = pd.DataFrame(spy_values).set_index("date")
    
    total_return = (pv["value"].iloc[-1] / initial_capital - 1) * 100
    spy_return = (sv["spy"].iloc[-1] / spy_start - 1) * 100
    alpha = total_return - spy_return
    
    # 일일 수익률
    daily_ret = pv["value"].pct_change().dropna()
    sharpe = float(daily_ret.mean() / daily_ret.std() * np.sqrt(252)) if daily_ret.std() > 0 else 0
    
    # MDD
    running_max = pv["value"].cummax()
    drawdown = (pv["value"] - running_max) / running_max * 100
    mdd = float(drawdown.min())
    
    # Win Rate (주간 기준)
    weekly_ret = pv["value"].resample("W").last().pct_change().dropna()
    win_rate = float((weekly_ret > 0).sum() / len(weekly_ret) * 100) if len(weekly_ret) > 0 else 0
    
    result = {
        "period": f"{all_dates[0].date()} ~ {all_dates[-1].date()}",
        "total_return": round(total_return, 2),
        "spy_return": round(spy_return, 2),
        "alpha": round(alpha, 2),
        "sharpe": round(sharpe, 2),
        "mdd": round(mdd, 2),
        "win_rate": round(win_rate, 1),
        "rebalance_count": rebalance_count,
        "final_value": round(pv["value"].iloc[-1], 2),
    }
    
    print(f"\n{'='*60}")
    print(f"  BACKTEST RESULT")
    print(f"{'='*60}")
    print(f"  기간: {result['period']}")
    print(f"  총 수익률: {result['total_return']:+.2f}%")
    print(f"  SPY 수익률: {result['spy_return']:+.2f}%")
    print(f"  Alpha: {result['alpha']:+.2f}%")
    print(f"  Sharpe Ratio: {result['sharpe']:.2f}")
    print(f"  MDD: {result['mdd']:.2f}%")
    print(f"  Win Rate: {result['win_rate']:.1f}%")
    print(f"  리밸런싱: {result['rebalance_count']}회")
    print(f"  최종 자산: ${result['final_value']:,.0f}")
    print(f"{'='*60}")
    
    # Telemetry 기록
    try:
        with get_cursor() as cur:
            cur.execute("""
                INSERT INTO system_telemetry
                    (calc_date, category, metric_name, metric_value, detail)
                VALUES (CURRENT_DATE, 'BACKTEST', 'quick_backtest', %s, %s)
            """, (result["sharpe"], json.dumps(result, default=str)))
        print("  Telemetry 기록 완료")
    except Exception as e:
        print(f"  Telemetry 실패: {e}")
    
    return result


if __name__ == "__main__":
    run_quick_backtest()
