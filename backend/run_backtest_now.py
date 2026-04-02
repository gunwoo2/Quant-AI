"""
run_backtest_now.py — QUANT AI 백테스트 엔진
=============================================
DB에 쌓인 과거 점수/시그널로 Walk-Forward 백테스트 실행.

사용법:
    python3 run_backtest_now.py                        # 전체 기간
    python3 run_backtest_now.py --start 2026-01-01     # 시작일 지정
    python3 run_backtest_now.py --top 10               # 상위 10종목
    python3 run_backtest_now.py --regime NEUTRAL       # 특정 국면만

출력:
    - Sharpe Ratio, MDD, Calmar Ratio, Win Rate
    - 월별 수익률 히트맵
    - Equity Curve
    - 거래 비용 반영 전/후 비교
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import argparse
import numpy as np
import pandas as pd
from datetime import date, timedelta
from collections import defaultdict

try:
    from db_pool import get_cursor, init_pool
except ImportError:
    pass

from transaction_cost_v5 import TransactionCostModel


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 설정
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

INITIAL_CAPITAL = 100_000
MAX_POSITIONS = 15
POSITION_PCT = 0.06          # 종목당 최대 6%
REBALANCE_DAYS = 5           # 5일마다 리밸런싱
STOP_LOSS_PCT = -10.0        # 손절 -10%
PROFIT_TAKE_PCT = 25.0       # 익절 +25%
MIN_HOLDING_DAYS = 3         # 최소 보유일


class BacktestEngine:
    """Walk-Forward 백테스트 엔진"""

    def __init__(self, initial_capital: float = INITIAL_CAPITAL):
        self.initial_capital = initial_capital
        self.tc_model = TransactionCostModel()

    def load_data(self, start_date: date = None, end_date: date = None) -> pd.DataFrame:
        """DB에서 일별 점수 + 가격 데이터 로드"""
        where_clauses = ["sfs.weighted_score IS NOT NULL"]
        params = []

        if start_date:
            where_clauses.append("sfs.calc_date >= %s")
            params.append(start_date)
        if end_date:
            where_clauses.append("sfs.calc_date <= %s")
            params.append(end_date)

        where_sql = " AND ".join(where_clauses)

        with get_cursor() as cur:
            cur.execute(f"""
                SELECT sfs.stock_id, s.ticker, sfs.calc_date,
                       sfs.weighted_score, sfs.grade, sfs.conviction_score,
                       sp.close_price, sp.volume,
                       ti.rsi_14, ti.atr_14
                FROM stock_final_scores sfs
                JOIN stocks s ON sfs.stock_id = s.stock_id
                LEFT JOIN stock_prices sp 
                    ON sp.stock_id = sfs.stock_id AND sp.price_date = sfs.calc_date
                LEFT JOIN technical_indicators ti
                    ON ti.stock_id = sfs.stock_id AND ti.calc_date = sfs.calc_date
                WHERE {where_sql}
                ORDER BY sfs.calc_date, sfs.weighted_score DESC
            """, params)
            rows = cur.fetchall()

        if not rows:
            print("[BACKTEST] 데이터 없음")
            return pd.DataFrame()

        df = pd.DataFrame([dict(r) for r in rows])
        df['calc_date'] = pd.to_datetime(df['calc_date'])
        print(f"[BACKTEST] 데이터 로드: {len(df):,}행, "
              f"{df['calc_date'].min().date()} ~ {df['calc_date'].max().date()}, "
              f"{df['ticker'].nunique()}종목")
        return df

    def run(self, df: pd.DataFrame, top_n: int = MAX_POSITIONS,
            with_cost: bool = True) -> dict:
        """
        Walk-Forward 백테스트 실행
        
        전략:
          매일 상위 top_n 종목 선정
          리밸런싱 주기마다 교체
          손절/익절 체크
          거래 비용 반영
        """
        if df.empty:
            return {}

        dates = sorted(df['calc_date'].unique())
        
        # 상태 변수
        capital = self.initial_capital
        positions = {}          # {ticker: {shares, entry_price, entry_date}}
        equity_curve = []
        trades = []
        last_rebalance = None
        daily_returns = []
        prev_equity = self.initial_capital

        for dt in dates:
            day_data = df[df['calc_date'] == dt].copy()
            day_data = day_data.dropna(subset=['close_price'])
            if day_data.empty:
                continue

            current_date = dt.date() if hasattr(dt, 'date') else dt
            price_map = dict(zip(day_data['ticker'], day_data['close_price'].astype(float)))
            score_map = dict(zip(day_data['ticker'], day_data['weighted_score'].astype(float)))
            volume_map = dict(zip(day_data['ticker'], day_data['volume'].fillna(1_000_000).astype(float)))

            # ── 1. 기존 포지션 평가 & 손절/익절 ──
            closed = []
            for ticker, pos in list(positions.items()):
                if ticker not in price_map:
                    continue
                current_price = price_map[ticker]
                pnl_pct = (current_price - pos['entry_price']) / pos['entry_price'] * 100
                holding_days = (current_date - pos['entry_date']).days

                should_close = False
                reason = ""
                if pnl_pct <= STOP_LOSS_PCT:
                    should_close, reason = True, "STOP_LOSS"
                elif pnl_pct >= PROFIT_TAKE_PCT:
                    should_close, reason = True, "PROFIT_TAKE"
                elif holding_days >= MIN_HOLDING_DAYS and ticker not in [
                    r['ticker'] for _, r in day_data.nlargest(top_n, 'weighted_score').iterrows()
                ]:
                    should_close, reason = True, "RANK_DROP"

                if should_close:
                    sell_value = current_price * pos['shares']
                    if with_cost:
                        cost = self.tc_model.estimate_cost(
                            current_price, pos['shares'], "SELL",
                            volume_map.get(ticker, 1_000_000))
                        sell_value -= cost.total_cost

                    capital += sell_value
                    trades.append({
                        'ticker': ticker, 'side': 'SELL', 'date': current_date,
                        'price': current_price, 'shares': pos['shares'],
                        'pnl_pct': round(pnl_pct, 2), 'reason': reason,
                        'holding_days': holding_days,
                    })
                    closed.append(ticker)

            for t in closed:
                del positions[t]

            # ── 2. 리밸런싱 체크 ──
            should_rebalance = (
                last_rebalance is None or
                (current_date - last_rebalance).days >= REBALANCE_DAYS
            )

            if should_rebalance:
                # 상위 N 종목 선정
                candidates = day_data.nlargest(top_n, 'weighted_score')
                target_tickers = set(candidates['ticker'].tolist())

                # 신규 매수
                available_slots = top_n - len(positions)
                available_capital = capital

                for _, row in candidates.iterrows():
                    if available_slots <= 0 or available_capital < 1000:
                        break
                    ticker = row['ticker']
                    if ticker in positions:
                        continue

                    price = float(row['close_price'])
                    if price <= 0:
                        continue

                    # 포지션 크기
                    max_invest = min(
                        available_capital * POSITION_PCT,
                        available_capital / max(available_slots, 1)
                    )
                    shares = int(max_invest / price)
                    if shares <= 0:
                        continue

                    buy_value = price * shares
                    if with_cost:
                        cost = self.tc_model.estimate_cost(
                            price, shares, "BUY",
                            volume_map.get(ticker, 1_000_000))
                        buy_value += cost.total_cost

                    if buy_value > available_capital:
                        continue

                    capital -= buy_value
                    positions[ticker] = {
                        'shares': shares, 'entry_price': price,
                        'entry_date': current_date,
                    }
                    trades.append({
                        'ticker': ticker, 'side': 'BUY', 'date': current_date,
                        'price': price, 'shares': shares,
                        'pnl_pct': 0, 'reason': 'SIGNAL',
                        'holding_days': 0,
                    })
                    available_capital -= buy_value
                    available_slots -= 1

                last_rebalance = current_date

            # ── 3. 일일 포트폴리오 가치 ──
            portfolio_value = capital
            for ticker, pos in positions.items():
                if ticker in price_map:
                    portfolio_value += price_map[ticker] * pos['shares']

            equity_curve.append({
                'date': current_date,
                'equity': round(portfolio_value, 2),
                'positions': len(positions),
                'cash': round(capital, 2),
            })

            daily_ret = (portfolio_value - prev_equity) / prev_equity if prev_equity > 0 else 0
            daily_returns.append(daily_ret)
            prev_equity = portfolio_value

        return self._calc_metrics(equity_curve, trades, daily_returns)

    def _calc_metrics(self, equity_curve: list, trades: list, daily_returns: list) -> dict:
        """성과 지표 계산"""
        if not equity_curve:
            return {"error": "데이터 부족"}

        equities = [e['equity'] for e in equity_curve]
        dates = [e['date'] for e in equity_curve]
        returns = np.array(daily_returns)

        # 기본 지표
        total_return = (equities[-1] / equities[0] - 1) * 100
        n_days = len(equities)
        ann_return = total_return * (252 / max(n_days, 1))

        # Sharpe Ratio (risk-free = 4.5%)
        rf_daily = 0.045 / 252
        excess = returns - rf_daily
        sharpe = (np.mean(excess) / np.std(excess) * np.sqrt(252)) if np.std(excess) > 0 else 0

        # Maximum Drawdown
        peak = equities[0]
        max_dd = 0
        for eq in equities:
            peak = max(peak, eq)
            dd = (eq - peak) / peak * 100
            max_dd = min(max_dd, dd)

        # Calmar Ratio
        calmar = ann_return / abs(max_dd) if max_dd != 0 else 0

        # Win Rate
        sell_trades = [t for t in trades if t['side'] == 'SELL']
        wins = sum(1 for t in sell_trades if t['pnl_pct'] > 0)
        win_rate = wins / len(sell_trades) * 100 if sell_trades else 0

        avg_win = np.mean([t['pnl_pct'] for t in sell_trades if t['pnl_pct'] > 0]) if wins > 0 else 0
        avg_loss = np.mean([t['pnl_pct'] for t in sell_trades if t['pnl_pct'] <= 0]) if len(sell_trades) - wins > 0 else 0
        profit_factor = abs(avg_win * wins / (avg_loss * (len(sell_trades) - wins))) if avg_loss != 0 and len(sell_trades) - wins > 0 else 0

        # 월별 수익률
        eq_df = pd.DataFrame(equity_curve)
        eq_df['date'] = pd.to_datetime(eq_df['date'])
        eq_df = eq_df.set_index('date')
        monthly = eq_df['equity'].resample('ME').last().pct_change().dropna() * 100

        result = {
            "period": f"{dates[0]} ~ {dates[-1]}",
            "trading_days": n_days,
            "initial_capital": self.initial_capital,
            "final_equity": round(equities[-1], 2),
            "total_return_pct": round(total_return, 2),
            "annualized_return_pct": round(ann_return, 2),
            "sharpe_ratio": round(sharpe, 3),
            "max_drawdown_pct": round(max_dd, 2),
            "calmar_ratio": round(calmar, 3),
            "total_trades": len(trades),
            "sell_trades": len(sell_trades),
            "win_rate_pct": round(win_rate, 1),
            "avg_win_pct": round(avg_win, 2),
            "avg_loss_pct": round(avg_loss, 2),
            "profit_factor": round(profit_factor, 2),
            "avg_holding_days": round(np.mean([t['holding_days'] for t in sell_trades]), 1) if sell_trades else 0,
            "monthly_returns": monthly.to_dict(),
            "equity_curve": equity_curve,
            "trades": trades,
        }
        return result


def print_report(metrics: dict):
    """백테스트 결과 출력"""
    if "error" in metrics:
        print(f"[BACKTEST] ❌ {metrics['error']}")
        return

    print(f"""
{'='*60}
  QUANT AI 백테스트 결과
  기간: {metrics['period']} ({metrics['trading_days']}일)
{'='*60}

  💰 수익률
    총 수익률:     {metrics['total_return_pct']:+.2f}%
    연환산 수익률:  {metrics['annualized_return_pct']:+.2f}%
    최종 자산:     ${metrics['final_equity']:,.2f}

  📊 리스크 지표
    Sharpe Ratio:  {metrics['sharpe_ratio']:.3f}
    Max Drawdown:  {metrics['max_drawdown_pct']:.2f}%
    Calmar Ratio:  {metrics['calmar_ratio']:.3f}

  🎯 매매 통계
    총 거래:       {metrics['total_trades']}건
    매도 거래:     {metrics['sell_trades']}건
    승률:          {metrics['win_rate_pct']:.1f}%
    평균 수익:     {metrics['avg_win_pct']:+.2f}%
    평균 손실:     {metrics['avg_loss_pct']:.2f}%
    Profit Factor: {metrics['profit_factor']:.2f}
    평균 보유일:   {metrics['avg_holding_days']:.1f}일

  📅 월별 수익률
""")
    for month, ret in metrics.get('monthly_returns', {}).items():
        bar = '█' * int(abs(ret)) + ('▒' if abs(ret) % 1 > 0.5 else '')
        sign = '+' if ret > 0 else ''
        print(f"    {month.strftime('%Y-%m') if hasattr(month, 'strftime') else month}: {sign}{ret:.1f}% {bar}")

    print(f"\n{'='*60}")

    # 등급 판정
    sharpe = metrics['sharpe_ratio']
    if sharpe >= 2.0:
        grade = "S (기관급)"
    elif sharpe >= 1.5:
        grade = "A (우수)"
    elif sharpe >= 1.0:
        grade = "B (양호)"
    elif sharpe >= 0.5:
        grade = "C (보통)"
    else:
        grade = "D (개선 필요)"

    print(f"  전략 등급: {grade} (Sharpe {sharpe:.3f})")
    print(f"  ※ 기관 기준: Sharpe > 1.5 (양호), > 2.0 (우수)")
    print(f"{'='*60}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="QUANT AI Backtest")
    parser.add_argument("--start", type=str, default=None, help="시작일 YYYY-MM-DD")
    parser.add_argument("--end", type=str, default=None, help="종료일 YYYY-MM-DD")
    parser.add_argument("--top", type=int, default=MAX_POSITIONS, help="상위 N종목")
    parser.add_argument("--no-cost", action="store_true", help="거래 비용 미반영")
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv()
    init_pool()

    engine = BacktestEngine()
    
    start = date.fromisoformat(args.start) if args.start else None
    end = date.fromisoformat(args.end) if args.end else None

    df = engine.load_data(start, end)
    
    if not df.empty:
        # 비용 반영 백테스트
        print("\n[1/2] 거래 비용 반영 백테스트...")
        result_with_cost = engine.run(df, top_n=args.top, with_cost=not args.no_cost)
        print_report(result_with_cost)
        
        if not args.no_cost:
            # 비용 미반영 비교
            print("\n[2/2] 거래 비용 미반영 (비교용)...")
            result_no_cost = engine.run(df, top_n=args.top, with_cost=False)
            if "total_return_pct" in result_no_cost:
                cost_drag = result_no_cost["total_return_pct"] - result_with_cost.get("total_return_pct", 0)
                print(f"  거래 비용 드래그: {cost_drag:.2f}%p")
                print(f"  비용 미반영 수익: {result_no_cost['total_return_pct']:+.2f}%")
                print(f"  비용 반영 수익:   {result_with_cost.get('total_return_pct', 0):+.2f}%")