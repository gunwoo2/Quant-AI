"""
batch/batch_paper_trading.py — Paper Trading Engine v1.0 (SET A-1)
===================================================================
시그널 기반 가상 체결 → 포지션 관리 → 일일 NAV 스냅샷 → 성과 지표 자동 산출

파이프라인:
  1. 오늘의 Trading Signals 조회
  2. SELL 시그널 → 가상 매도 체결 (슬리피지 반영)
  3. BUY 시그널  → 포지션 사이징 → 가상 매수 체결
  4. 보유 종목 시가 평가 (Mark-to-Market)
  5. EOD 스냅샷 저장 (NAV, 현금, 투자금, 수익률)
  6. 월말: 성과 지표 계산 (Sharpe, Sortino, MDD, Alpha, Beta)

설계 근거:
  - Almgren & Chriss (2000): Market Impact = σ × √(V/ADV)
  - GIPS: TWR(시간가중수익률) 기반 성과 보고
  - Harvey et al. (2016): 실시간 Forward 성과만이 과적합 배제 증거

실행:
  scheduler.py Step 7.3에 추가 (Trading Signals 직후)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import math
import json
import logging
import numpy as np
from datetime import datetime, date, timedelta
from db_pool import get_cursor

logger = logging.getLogger("paper_trading")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 상수
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

INITIAL_CASH      = 100_000.00   # 초기 자본금 $100K
COMMISSION_PER_SHARE = 0.005     # $0.005/share (IBKR 기준)
MIN_COMMISSION    = 1.00         # 최소 수수료 $1
BASE_SLIPPAGE_BP  = 10           # 기본 슬리피지 10bp
BENCHMARK_TICKER  = "SPY"
PORTFOLIO_ID      = 1


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 테이블 보장
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def ensure_paper_tables():
    """Paper Trading 관련 테이블 생성 (없으면)"""
    with get_cursor() as cur:
        # 포트폴리오 설정
        cur.execute("""
            CREATE TABLE IF NOT EXISTS paper_portfolio_config (
                portfolio_id   SERIAL PRIMARY KEY,
                name           VARCHAR(100) DEFAULT 'QUANT_AI_v5',
                initial_cash   NUMERIC(14,2) DEFAULT 100000,
                start_date     DATE DEFAULT CURRENT_DATE,
                benchmark      VARCHAR(10) DEFAULT 'SPY',
                slippage_model VARCHAR(20) DEFAULT 'SQRT_IMPACT',
                commission_per_share NUMERIC(6,4) DEFAULT 0.005,
                is_active      BOOLEAN DEFAULT TRUE,
                created_at     TIMESTAMPTZ DEFAULT NOW()
            )
        """)

        # 포지션
        cur.execute("""
            CREATE TABLE IF NOT EXISTS paper_positions (
                position_id    SERIAL PRIMARY KEY,
                portfolio_id   INTEGER DEFAULT 1,
                stock_id       INTEGER NOT NULL,
                ticker         VARCHAR(20) NOT NULL,
                quantity       INTEGER NOT NULL,
                avg_entry_price NUMERIC(12,4) NOT NULL,
                entry_date     DATE NOT NULL,
                entry_signal_id INTEGER,
                current_price  NUMERIC(12,4),
                unrealized_pnl NUMERIC(14,2) DEFAULT 0,
                realized_pnl   NUMERIC(14,2) DEFAULT 0,
                status         VARCHAR(10) DEFAULT 'OPEN',
                exit_date      DATE,
                exit_price     NUMERIC(12,4),
                exit_reason    VARCHAR(50),
                updated_at     TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_paper_pos_status
            ON paper_positions(portfolio_id, status)
        """)

        # 주문 이력
        cur.execute("""
            CREATE TABLE IF NOT EXISTS paper_orders (
                order_id       SERIAL PRIMARY KEY,
                portfolio_id   INTEGER DEFAULT 1,
                stock_id       INTEGER NOT NULL,
                ticker         VARCHAR(20) NOT NULL,
                side           VARCHAR(4) NOT NULL,
                quantity       INTEGER NOT NULL,
                signal_price   NUMERIC(12,4) NOT NULL,
                fill_price     NUMERIC(12,4) NOT NULL,
                slippage_bp    NUMERIC(8,2),
                commission     NUMERIC(8,4),
                total_cost     NUMERIC(14,2),
                order_source   VARCHAR(30),
                fill_date      DATE NOT NULL,
                created_at     TIMESTAMPTZ DEFAULT NOW()
            )
        """)

        # 일일 스냅샷
        cur.execute("""
            CREATE TABLE IF NOT EXISTS paper_daily_snapshot (
                id             SERIAL PRIMARY KEY,
                portfolio_id   INTEGER DEFAULT 1,
                snap_date      DATE NOT NULL,
                nav            NUMERIC(14,2) NOT NULL,
                cash           NUMERIC(14,2) NOT NULL,
                invested_value NUMERIC(14,2) NOT NULL,
                daily_return   NUMERIC(10,6),
                cumulative_return NUMERIC(10,6),
                benchmark_price NUMERIC(12,4),
                benchmark_return NUMERIC(10,6),
                benchmark_cumulative NUMERIC(10,6),
                active_return  NUMERIC(10,6),
                position_count INTEGER,
                drawdown       NUMERIC(10,6),
                max_drawdown   NUMERIC(10,6),
                turnover       NUMERIC(10,6) DEFAULT 0,
                created_at     TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(portfolio_id, snap_date)
            )
        """)

        # 월간 성과 지표
        cur.execute("""
            CREATE TABLE IF NOT EXISTS paper_performance_monthly (
                id             SERIAL PRIMARY KEY,
                portfolio_id   INTEGER DEFAULT 1,
                month          DATE NOT NULL,
                sharpe         NUMERIC(8,4),
                sortino        NUMERIC(8,4),
                calmar         NUMERIC(8,4),
                max_drawdown   NUMERIC(8,4),
                win_rate       NUMERIC(6,4),
                avg_win        NUMERIC(8,4),
                avg_loss       NUMERIC(8,4),
                profit_factor  NUMERIC(8,4),
                annualized_return NUMERIC(8,4),
                annualized_vol NUMERIC(8,4),
                alpha          NUMERIC(8,4),
                beta           NUMERIC(8,4),
                information_ratio NUMERIC(8,4),
                turnover_monthly NUMERIC(8,4),
                avg_holding_days NUMERIC(8,2),
                total_trades   INTEGER DEFAULT 0,
                created_at     TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(portfolio_id, month)
            )
        """)

        # 초기 포트폴리오 없으면 생성
        cur.execute("SELECT COUNT(*) as cnt FROM paper_portfolio_config WHERE portfolio_id = %s", (PORTFOLIO_ID,))
        if cur.fetchone()["cnt"] == 0:
            cur.execute("""
                INSERT INTO paper_portfolio_config (portfolio_id, name, initial_cash, start_date)
                VALUES (%s, 'QUANT_AI_v5_PAPER', %s, CURRENT_DATE)
                ON CONFLICT DO NOTHING
            """, (PORTFOLIO_ID, INITIAL_CASH))

    print("[PAPER] Tables ensured")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 슬리피지 모델 (Almgren-Chriss 간소화)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def calc_fill_price(signal_price: float, side: str, shares: int = 0,
                    adv: float = 0, volatility: float = 0.02) -> tuple:
    """
    가상 체결가 계산.
    
    Square-Root Market Impact (Almgren-Chriss 간소화):
      impact = base_bp + k × σ × √(shares / ADV)
    
    Args:
        signal_price: 시그널 시점 가격 (종가)
        side: 'BUY' or 'SELL'
        shares: 주문 수량
        adv: 20일 평균 거래량
        volatility: 20일 변동성 (연율화 아닌 일일)
    
    Returns:
        (fill_price, slippage_bp)
    """
    base_bp = BASE_SLIPPAGE_BP / 10000  # 10bp = 0.001
    
    # Volume Impact (유동성 기반 추가 슬리피지)
    if adv and adv > 0 and shares > 0:
        participation = shares / adv
        vol_impact = 0.5 * volatility * math.sqrt(participation)
    else:
        vol_impact = 0.002  # 유동성 불명 → 보수적 20bp

    total_slip = base_bp + vol_impact
    total_slip = min(total_slip, 0.05)  # 최대 5% 캡

    if side == "BUY":
        fill = signal_price * (1 + total_slip)
    else:
        fill = signal_price * (1 - total_slip)
    
    slippage_bp_actual = total_slip * 10000
    return round(fill, 4), round(slippage_bp_actual, 2)


def calc_commission(shares: int) -> float:
    """수수료 계산 (IBKR 기준)"""
    comm = shares * COMMISSION_PER_SHARE
    return max(comm, MIN_COMMISSION)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 핵심 엔진
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _get_cash(portfolio_id: int = PORTFOLIO_ID) -> float:
    """현재 현금 잔고 조회"""
    with get_cursor() as cur:
        # 최근 스냅샷에서 현금 조회
        cur.execute("""
            SELECT cash FROM paper_daily_snapshot
            WHERE portfolio_id = %s ORDER BY snap_date DESC LIMIT 1
        """, (portfolio_id,))
        row = cur.fetchone()
        if row:
            return float(row["cash"])
        
        # 스냅샷 없으면 초기 자본
        cur.execute("SELECT initial_cash FROM paper_portfolio_config WHERE portfolio_id = %s", (portfolio_id,))
        row = cur.fetchone()
        return float(row["initial_cash"]) if row else INITIAL_CASH


def _get_open_positions(portfolio_id: int = PORTFOLIO_ID) -> list:
    """현재 보유 포지션 목록"""
    with get_cursor() as cur:
        cur.execute("""
            SELECT position_id, stock_id, ticker, quantity, avg_entry_price, entry_date
            FROM paper_positions
            WHERE portfolio_id = %s AND status = 'OPEN'
        """, (portfolio_id,))
        return [dict(r) for r in cur.fetchall()]


def _get_todays_signals(calc_date: date) -> dict:
    """오늘의 Trading Signals 조회"""
    buys, sells = [], []
    with get_cursor() as cur:
        cur.execute("""
            SELECT stock_id, ticker, action, final_score, grade,
                   target_weight, entry_price, exit_reason,
                   percentile_rank
            FROM trading_signals
            WHERE calc_date = %s AND action IN ('BUY', 'SELL', 'STOP_LOSS')
            ORDER BY final_score DESC
        """, (calc_date,))
        for row in cur.fetchall():
            r = dict(row)
            if r["action"] == "BUY":
                buys.append(r)
            else:
                sells.append(r)
    return {"buys": buys, "sells": sells}


def _get_current_price(stock_id: int, calc_date: date) -> float:
    """종목 최신 종가"""
    with get_cursor() as cur:
        cur.execute("""
            SELECT close_price FROM stock_prices_daily
            WHERE stock_id = %s AND trade_date <= %s
            ORDER BY trade_date DESC LIMIT 1
        """, (stock_id, calc_date))
        row = cur.fetchone()
        return float(row["close_price"]) if row else 0


def _get_volume_avg(stock_id: int, calc_date: date) -> float:
    """20일 평균 거래량 (서브쿼리로 최근 20일 선택 후 평균)"""
    with get_cursor() as cur:
        cur.execute("""
            SELECT AVG(volume) as adv FROM (
                SELECT volume FROM stock_prices_daily
                WHERE stock_id = %s AND trade_date <= %s
                ORDER BY trade_date DESC LIMIT 20
            ) sub
        """, (stock_id, calc_date))
        row = cur.fetchone()
        return float(row["adv"]) if row and row["adv"] else 100000


def _get_benchmark_price(calc_date: date) -> float:
    """SPY 종가"""
    with get_cursor() as cur:
        cur.execute("""
            SELECT p.close_price FROM stock_prices_daily p
            JOIN stocks s ON p.stock_id = s.stock_id
            WHERE s.ticker = %s AND p.trade_date <= %s
            ORDER BY p.trade_date DESC LIMIT 1
        """, (BENCHMARK_TICKER, calc_date))
        row = cur.fetchone()
        return float(row["close_price"]) if row else 0


def execute_sell(position: dict, calc_date: date, reason: str = "SIGNAL_SELL") -> dict:
    """매도 체결"""
    price = _get_current_price(position["stock_id"], calc_date)
    adv = _get_volume_avg(position["stock_id"], calc_date)
    fill_price, slip_bp = calc_fill_price(price, "SELL", position["quantity"], adv)
    commission = calc_commission(position["quantity"])
    
    proceeds = fill_price * position["quantity"] - commission
    cost_basis = position["avg_entry_price"] * position["quantity"]
    realized_pnl = proceeds - cost_basis

    with get_cursor() as cur:
        # 포지션 마감
        cur.execute("""
            UPDATE paper_positions
            SET status = 'CLOSED', exit_date = %s, exit_price = %s,
                exit_reason = %s, realized_pnl = %s, updated_at = NOW()
            WHERE position_id = %s
        """, (calc_date, fill_price, reason, realized_pnl, position["position_id"]))

        # 주문 기록
        cur.execute("""
            INSERT INTO paper_orders
            (portfolio_id, stock_id, ticker, side, quantity, signal_price, fill_price,
             slippage_bp, commission, total_cost, order_source, fill_date)
            VALUES (%s, %s, %s, 'SELL', %s, %s, %s, %s, %s, %s, %s, %s)
        """, (PORTFOLIO_ID, position["stock_id"], position["ticker"],
              position["quantity"], price, fill_price, slip_bp, commission,
              proceeds, reason, calc_date))

    return {"ticker": position["ticker"], "pnl": realized_pnl, "proceeds": proceeds}


def execute_buy(signal: dict, cash: float, nav: float, cfg_max_pct: float,
                calc_date: date) -> dict:
    """매수 체결"""
    stock_id = signal["stock_id"]
    ticker = signal["ticker"]
    price = signal.get("entry_price") or _get_current_price(stock_id, calc_date)
    adv = _get_volume_avg(stock_id, calc_date)
    
    if price <= 0:
        return None

    # 포지션 사이징: NAV의 max_position_pct 또는 남은 현금의 80% 중 작은 값
    target_value = min(nav * cfg_max_pct, cash * 0.80)
    if target_value < 500:  # 최소 $500
        return None

    shares = int(target_value / price)
    if shares <= 0:
        return None

    fill_price, slip_bp = calc_fill_price(price, "BUY", shares, adv)
    commission = calc_commission(shares)
    total_cost = fill_price * shares + commission

    if total_cost > cash:
        shares = int((cash - MIN_COMMISSION) / fill_price)
        if shares <= 0:
            return None
        total_cost = fill_price * shares + calc_commission(shares)

    with get_cursor() as cur:
        # 포지션 생성
        cur.execute("""
            INSERT INTO paper_positions
            (portfolio_id, stock_id, ticker, quantity, avg_entry_price, entry_date, status)
            VALUES (%s, %s, %s, %s, %s, %s, 'OPEN')
        """, (PORTFOLIO_ID, stock_id, ticker, shares, fill_price, calc_date))

        # 주문 기록
        cur.execute("""
            INSERT INTO paper_orders
            (portfolio_id, stock_id, ticker, side, quantity, signal_price, fill_price,
             slippage_bp, commission, total_cost, order_source, fill_date)
            VALUES (%s, %s, %s, 'BUY', %s, %s, %s, %s, %s, %s, 'SIGNAL_BUY', %s)
        """, (PORTFOLIO_ID, stock_id, ticker, shares, price, fill_price,
              slip_bp, commission, total_cost, calc_date))

    return {"ticker": ticker, "shares": shares, "cost": total_cost}


def take_daily_snapshot(calc_date: date) -> dict:
    """EOD 스냅샷 — NAV, 수익률, 벤치마크 대비"""
    positions = _get_open_positions()
    
    # Mark-to-Market
    invested = 0
    for pos in positions:
        price = _get_current_price(pos["stock_id"], calc_date)
        value = price * pos["quantity"]
        invested += value
        # 현재가 업데이트
        with get_cursor() as cur:
            unrealized = (price - pos["avg_entry_price"]) * pos["quantity"]
            cur.execute("""
                UPDATE paper_positions SET current_price = %s, unrealized_pnl = %s, updated_at = NOW()
                WHERE position_id = %s
            """, (price, unrealized, pos["position_id"]))

    # 현금 계산: 초기 자본 + 모든 매도 수익 - 모든 매수 비용
    with get_cursor() as cur:
        cur.execute("""
            SELECT
                COALESCE((SELECT initial_cash FROM paper_portfolio_config WHERE portfolio_id = %s), %s)
                + COALESCE(SUM(CASE WHEN side = 'SELL' THEN total_cost ELSE 0 END), 0)
                - COALESCE(SUM(CASE WHEN side = 'BUY'  THEN total_cost ELSE 0 END), 0)
                AS cash
            FROM paper_orders WHERE portfolio_id = %s
        """, (PORTFOLIO_ID, INITIAL_CASH, PORTFOLIO_ID))
        cash = float(cur.fetchone()["cash"])

    nav = cash + invested
    
    # 이전 NAV
    with get_cursor() as cur:
        cur.execute("""
            SELECT nav, benchmark_price, max_drawdown
            FROM paper_daily_snapshot WHERE portfolio_id = %s
            ORDER BY snap_date DESC LIMIT 1
        """, (PORTFOLIO_ID,))
        prev = cur.fetchone()
    
    prev_nav = float(prev["nav"]) if prev else INITIAL_CASH
    prev_bench = float(prev["benchmark_price"]) if prev and prev["benchmark_price"] else None
    prev_mdd = float(prev["max_drawdown"]) if prev and prev["max_drawdown"] else 0

    daily_return = (nav / prev_nav - 1) if prev_nav > 0 else 0
    cum_return = (nav / INITIAL_CASH - 1)

    # 벤치마크
    bench_price = _get_benchmark_price(calc_date)
    bench_return = (bench_price / prev_bench - 1) if prev_bench and prev_bench > 0 else 0

    # 첫 벤치마크 저장용
    with get_cursor() as cur:
        cur.execute("""
            SELECT benchmark_price FROM paper_daily_snapshot
            WHERE portfolio_id = %s ORDER BY snap_date ASC LIMIT 1
        """, (PORTFOLIO_ID,))
        first = cur.fetchone()
    first_bench = float(first["benchmark_price"]) if first and first["benchmark_price"] else bench_price
    bench_cum = (bench_price / first_bench - 1) if first_bench and first_bench > 0 else 0

    active_return = daily_return - bench_return

    # Drawdown
    with get_cursor() as cur:
        cur.execute("""
            SELECT MAX(nav) as peak FROM paper_daily_snapshot WHERE portfolio_id = %s
        """, (PORTFOLIO_ID,))
        row = cur.fetchone()
    peak = max(float(row["peak"]) if row and row["peak"] else nav, nav)
    drawdown = (nav / peak - 1) if peak > 0 else 0
    max_dd = min(prev_mdd, drawdown)

    # 저장
    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO paper_daily_snapshot
            (portfolio_id, snap_date, nav, cash, invested_value,
             daily_return, cumulative_return,
             benchmark_price, benchmark_return, benchmark_cumulative,
             active_return, position_count, drawdown, max_drawdown)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (portfolio_id, snap_date) DO UPDATE SET
                nav=EXCLUDED.nav, cash=EXCLUDED.cash, invested_value=EXCLUDED.invested_value,
                daily_return=EXCLUDED.daily_return, cumulative_return=EXCLUDED.cumulative_return,
                benchmark_price=EXCLUDED.benchmark_price, benchmark_return=EXCLUDED.benchmark_return,
                benchmark_cumulative=EXCLUDED.benchmark_cumulative,
                active_return=EXCLUDED.active_return, position_count=EXCLUDED.position_count,
                drawdown=EXCLUDED.drawdown, max_drawdown=EXCLUDED.max_drawdown
        """, (PORTFOLIO_ID, calc_date, nav, cash, invested, 
              daily_return, cum_return,
              bench_price, bench_return, bench_cum,
              active_return, len(positions), drawdown, max_dd))

    return {
        "nav": nav, "cash": cash, "invested": invested,
        "daily_return": daily_return, "cum_return": cum_return,
        "bench_cum": bench_cum, "active_return": active_return,
        "positions": len(positions), "drawdown": drawdown, "mdd": max_dd,
    }


def calc_monthly_metrics(calc_date: date):
    """월간 성과 지표 계산 (Sharpe, Sortino, Alpha, Beta 등)"""
    month_start = calc_date.replace(day=1)
    
    with get_cursor() as cur:
        # 전체 기간 일일 수익률
        cur.execute("""
            SELECT snap_date, daily_return, benchmark_return
            FROM paper_daily_snapshot WHERE portfolio_id = %s
            ORDER BY snap_date
        """, (PORTFOLIO_ID,))
        rows = cur.fetchall()
    
    if len(rows) < 5:
        print("[PAPER] Not enough data for monthly metrics")
        return

    rets = np.array([float(r["daily_return"] or 0) for r in rows])
    bench_rets = np.array([float(r["benchmark_return"] or 0) for r in rows])
    
    # 기본 지표
    n = len(rets)
    ann_factor = 252
    
    mean_ret = np.mean(rets)
    std_ret = np.std(rets, ddof=1) if n > 1 else 0.01
    
    sharpe = (mean_ret / std_ret * np.sqrt(ann_factor)) if std_ret > 0 else 0
    
    downside = rets[rets < 0]
    down_std = np.std(downside, ddof=1) if len(downside) > 1 else std_ret
    sortino = (mean_ret / down_std * np.sqrt(ann_factor)) if down_std > 0 else 0
    
    # MDD
    cum = np.cumprod(1 + rets)
    peak = np.maximum.accumulate(cum)
    dd = cum / peak - 1
    max_dd = float(np.min(dd))
    calmar = (mean_ret * ann_factor / abs(max_dd)) if max_dd != 0 else 0
    
    # Win rate
    trades_pnl = []
    with get_cursor() as cur2:
        cur2.execute("""
            SELECT realized_pnl FROM paper_positions
            WHERE portfolio_id = %s AND status = 'CLOSED'
        """, (PORTFOLIO_ID,))
        trades_pnl = [float(r["realized_pnl"] or 0) for r in cur2.fetchall()]
    
    wins = [p for p in trades_pnl if p > 0]
    losses = [p for p in trades_pnl if p < 0]
    win_rate = len(wins) / len(trades_pnl) if trades_pnl else 0
    avg_win = np.mean(wins) if wins else 0
    avg_loss = np.mean(losses) if losses else 0
    profit_factor = (sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else 99
    
    # Alpha / Beta (CAPM 회귀)
    if len(bench_rets) > 5 and np.std(bench_rets) > 0:
        cov = np.cov(rets, bench_rets)
        beta = cov[0, 1] / cov[1, 1] if cov[1, 1] != 0 else 1
        alpha = (mean_ret - beta * np.mean(bench_rets)) * ann_factor
    else:
        alpha, beta = 0, 1

    # Information Ratio
    active = rets - bench_rets
    te = np.std(active, ddof=1) if len(active) > 1 else 0.01
    ir = (np.mean(active) / te * np.sqrt(ann_factor)) if te > 0 else 0

    ann_return = mean_ret * ann_factor
    ann_vol = std_ret * np.sqrt(ann_factor)

    # 저장
    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO paper_performance_monthly
            (portfolio_id, month, sharpe, sortino, calmar, max_drawdown,
             win_rate, avg_win, avg_loss, profit_factor,
             annualized_return, annualized_vol, alpha, beta,
             information_ratio, total_trades)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (portfolio_id, month) DO UPDATE SET
                sharpe=EXCLUDED.sharpe, sortino=EXCLUDED.sortino,
                calmar=EXCLUDED.calmar, max_drawdown=EXCLUDED.max_drawdown,
                win_rate=EXCLUDED.win_rate, avg_win=EXCLUDED.avg_win,
                avg_loss=EXCLUDED.avg_loss, profit_factor=EXCLUDED.profit_factor,
                annualized_return=EXCLUDED.annualized_return,
                annualized_vol=EXCLUDED.annualized_vol,
                alpha=EXCLUDED.alpha, beta=EXCLUDED.beta,
                information_ratio=EXCLUDED.information_ratio,
                total_trades=EXCLUDED.total_trades
        """, (PORTFOLIO_ID, month_start, sharpe, sortino, calmar, max_dd,
              win_rate, avg_win, avg_loss, profit_factor,
              ann_return, ann_vol, alpha, beta, ir, len(trades_pnl)))

    print(f"[PAPER] Monthly metrics: Sharpe={sharpe:.2f} Sortino={sortino:.2f} "
          f"MDD={max_dd:.1%} Alpha={alpha:.1%} Beta={beta:.2f} IR={ir:.2f}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 메인 파이프라인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run_paper_trading(calc_date: date = None):
    """
    Paper Trading 일일 실행.
    scheduler.py Step 7.3에서 호출.
    """
    if calc_date is None:
        calc_date = datetime.now().date()
    
    print(f"\n{'='*50}")
    print(f"  PAPER TRADING — {calc_date}")
    print(f"{'='*50}")
    
    ensure_paper_tables()
    
    # 1. 시그널 조회
    signals = _get_todays_signals(calc_date)
    print(f"  Signals: {len(signals['buys'])} BUY, {len(signals['sells'])} SELL")
    
    # 2. 현재 상태
    cash = _get_cash()
    positions = _get_open_positions()
    invested = sum(_get_current_price(p["stock_id"], calc_date) * p["quantity"] for p in positions)
    nav = cash + invested
    print(f"  Before: NAV=${nav:,.2f} Cash=${cash:,.2f} Positions={len(positions)}")

    # 3. SELL 처리
    sell_results = []
    sell_tickers = {s["ticker"] for s in signals["sells"]}
    for pos in positions:
        if pos["ticker"] in sell_tickers:
            result = execute_sell(pos, calc_date, "SIGNAL_SELL")
            sell_results.append(result)
            cash += result["proceeds"]
            print(f"    SELL {result['ticker']}: PnL=${result['pnl']:+,.2f}")

    # 4. BUY 처리
    buy_results = []
    # 최대 포지션 수 체크
    open_count = len(positions) - len(sell_results)
    max_new_buys = max(0, 15 - open_count)  # 기본 max 15
    
    for buy_signal in signals["buys"][:max_new_buys]:
        # 이미 보유 중인 종목 스킵
        held_tickers = {p["ticker"] for p in _get_open_positions()}
        if buy_signal["ticker"] in held_tickers:
            continue
        
        result = execute_buy(buy_signal, cash, nav, 0.08, calc_date)
        if result:
            buy_results.append(result)
            cash -= result["cost"]
            print(f"    BUY  {result['ticker']}: {result['shares']}주 ${result['cost']:,.2f}")

    # 5. EOD 스냅샷
    snapshot = take_daily_snapshot(calc_date)
    print(f"\n  After:  NAV=${snapshot['nav']:,.2f} Cash=${snapshot['cash']:,.2f} "
          f"Pos={snapshot['positions']}")
    print(f"  Return: Day={snapshot['daily_return']:+.2%} Cum={snapshot['cum_return']:+.2%} "
          f"Bench={snapshot['bench_cum']:+.2%} Active={snapshot['active_return']:+.2%}")
    print(f"  DD: {snapshot['drawdown']:.2%} | MDD: {snapshot['mdd']:.2%}")

    # 6. 월말 성과 지표
    if calc_date.day >= 28 or (calc_date + timedelta(days=1)).month != calc_date.month:
        calc_monthly_metrics(calc_date)

    return {
        "sells": len(sell_results),
        "buys": len(buy_results),
        "nav": snapshot["nav"],
        "cum_return": snapshot["cum_return"],
        "mdd": snapshot["mdd"],
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CLI
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=str, default=None)
    args = parser.parse_args()
    
    d = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else date.today()
    run_paper_trading(d)
