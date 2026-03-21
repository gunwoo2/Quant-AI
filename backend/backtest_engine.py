"""
backtest_engine.py — 풀 백테스트 엔진
기존 DB의 stock_prices_daily + stock_final_scores 데이터를 사용해
과거 기간에 대해 전체 트레이딩 시뮬레이션 수행.

★ 핵심: Look-Ahead Bias 완전 제거
  - T일 종가 데이터로 시그널 생성 → T+1일 시가로 주문 실행
"""
import numpy as np
import pandas as pd
from datetime import date, timedelta, datetime
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from collections import defaultdict
import json


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 데이터 구조
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class BacktestPosition:
    """백테스트 내 포지션"""
    stock_id: int
    ticker: str
    sector: str
    entry_date: date
    entry_price: float
    shares: int
    stop_loss: float
    trailing_stop: float
    highest_price: float

    def unrealized_pnl(self, current_price: float) -> float:
        return (current_price - self.entry_price) * self.shares

    def unrealized_pct(self, current_price: float) -> float:
        if self.entry_price <= 0:
            return 0
        return (current_price - self.entry_price) / self.entry_price

    def holding_days(self, current_date: date) -> int:
        return (current_date - self.entry_date).days


@dataclass
class BacktestTrade:
    """거래 기록"""
    ticker: str
    trade_type: str          # BUY, SELL
    trade_date: date
    price: float
    shares: int
    amount: float
    # SELL인 경우
    entry_price: float = 0
    holding_days: int = 0
    pnl: float = 0
    pnl_pct: float = 0
    sell_reason: str = ""


@dataclass
class DailySnapshot:
    """일일 스냅샷"""
    date: date
    total_value: float
    cash: float
    invested: float
    daily_return: float
    cumulative_return: float
    drawdown: float
    num_positions: int
    regime: str
    spy_cumulative: float = 0


@dataclass
class BacktestResult:
    """백테스트 결과"""
    # 설정
    start_date: date = None
    end_date: date = None
    initial_capital: float = 100000

    # 핵심 성과
    total_return: float = 0
    cagr: float = 0
    sharpe_ratio: float = 0
    sortino_ratio: float = 0
    max_drawdown: float = 0
    calmar_ratio: float = 0

    # 거래 통계
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0
    profit_factor: float = 0
    avg_holding_days: float = 0
    avg_win: float = 0
    avg_loss: float = 0

    # 벤치마크 대비
    spy_return: float = 0
    alpha: float = 0
    beta: float = 0
    information_ratio: float = 0

    # 상세
    daily_snapshots: List[DailySnapshot] = field(default_factory=list)
    trades: List[BacktestTrade] = field(default_factory=list)
    monthly_returns: Dict = field(default_factory=dict)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 백테스트 엔진
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class BacktestEngine:
    """
    풀 백테스트 엔진

    Usage
    -----
    engine = BacktestEngine(config=TradingConfig())
    engine.load_data(prices_df, scores_df, spy_df)
    result = engine.run(start_date, end_date)
    """

    def __init__(self, cfg=None):
        from backend.risk.trading_config import TradingConfig
        self.cfg = cfg or TradingConfig()
        self.positions: Dict[str, BacktestPosition] = {}  # ticker → position
        self.cash = self.cfg.initial_capital
        self.trades: List[BacktestTrade] = []
        self.snapshots: List[DailySnapshot] = []
        self.peak_value = self.cfg.initial_capital

        # 데이터
        self.prices: Dict[str, pd.DataFrame] = {}      # ticker → DataFrame(date, open, high, low, close, volume)
        self.scores: Dict[str, pd.DataFrame] = {}      # ticker → DataFrame(date, final_score, l3_score, signal, grade)
        self.spy: pd.DataFrame = None                   # DataFrame(date, open, close)
        self.stock_info: Dict[str, dict] = {}           # ticker → {stock_id, sector, ...}
        self.trading_days: List[date] = []

    # ────────────────────────────────────────────
    # 데이터 로딩
    # ────────────────────────────────────────────

    def load_data(
        self,
        prices: Dict[str, pd.DataFrame],
        scores: Dict[str, pd.DataFrame],
        spy: pd.DataFrame,
        stock_info: Dict[str, dict],
    ):
        """
        데이터 로딩

        Parameters
        ----------
        prices : dict
            {ticker: DataFrame[date, open, high, low, close, volume]}
        scores : dict
            {ticker: DataFrame[date, final_score, layer3_score, signal, grade]}
        spy : DataFrame
            [date, open, close]
        stock_info : dict
            {ticker: {stock_id, sector}}
        """
        self.prices = prices
        self.scores = scores
        self.spy = spy.set_index("date").sort_index() if "date" in spy.columns else spy.sort_index()
        self.stock_info = stock_info

    def load_from_db(self, start_date: date, end_date: date):
        """
        DB에서 직접 데이터 로딩 (PostgreSQL)
        실제 배포 시 사용
        """
        from db_pool import get_cursor

        # 종목 정보
        with get_cursor() as cur:
            cur.execute("""
                SELECT stock_id, ticker, company_name, sector
                FROM stocks WHERE is_active = TRUE
            """)
            for row in cur.fetchall():
                r = dict(row)
                self.stock_info[r["ticker"]] = r

        tickers = list(self.stock_info.keys())
        print(f"[BT] 종목 {len(tickers)}개 로딩")

        # 가격 데이터
        with get_cursor() as cur:
            for ticker in tickers:
                sid = self.stock_info[ticker]["stock_id"]
                cur.execute("""
                    SELECT trade_date as date,
                           open_price as open, high_price as high,
                           low_price as low, close_price as close,
                           volume
                    FROM stock_prices_daily
                    WHERE stock_id = %s
                      AND trade_date BETWEEN %s AND %s
                    ORDER BY trade_date
                """, (sid, start_date - timedelta(days=300), end_date))
                rows = [dict(r) for r in cur.fetchall()]
                if rows:
                    df = pd.DataFrame(rows)
                    df["date"] = pd.to_datetime(df["date"]).dt.date
                    df = df.set_index("date").sort_index()
                    for col in ["open","high","low","close","volume"]:
                        df[col] = pd.to_numeric(df[col], errors="coerce")
                    self.prices[ticker] = df

        # 점수 데이터
        with get_cursor() as cur:
            for ticker in tickers:
                sid = self.stock_info[ticker]["stock_id"]
                cur.execute("""
                    SELECT calc_date as date, weighted_score as final_score,
                           layer3_score, signal, grade
                    FROM stock_final_scores
                    WHERE stock_id = %s
                      AND calc_date BETWEEN %s AND %s
                    ORDER BY calc_date
                """, (sid, start_date - timedelta(days=30), end_date))
                rows = [dict(r) for r in cur.fetchall()]
                if rows:
                    df = pd.DataFrame(rows)
                    df["date"] = pd.to_datetime(df["date"]).dt.date
                    df = df.set_index("date").sort_index()
                    self.scores[ticker] = df

        # SPY
        if "SPY" in self.prices:
            self.spy = self.prices["SPY"][["open", "close"]].copy()

        print(f"[BT] 가격 {len(self.prices)}개, 점수 {len(self.scores)}개 로딩 완료")

    # ────────────────────────────────────────────
    # ATR 계산
    # ────────────────────────────────────────────

    def _calc_atr(self, ticker: str, as_of: date, period: int = 14) -> float:
        """해당 날짜까지의 ATR 계산 (Look-Ahead 방지)"""
        if ticker not in self.prices:
            return 0
        df = self.prices[ticker]
        mask = df.index <= as_of
        subset = df[mask].tail(period + 1)
        if len(subset) < period:
            return 0

        high = subset["high"].values
        low = subset["low"].values
        close = subset["close"].values

        tr = []
        for i in range(1, len(high)):
            tr.append(max(
                high[i] - low[i],
                abs(high[i] - close[i-1]),
                abs(low[i] - close[i-1]),
            ))
        return float(np.mean(tr[-period:])) if tr else 0

    def _calc_rsi(self, ticker: str, as_of: date, period: int = 14) -> float:
        """해당 날짜까지의 RSI"""
        if ticker not in self.prices:
            return 50
        df = self.prices[ticker]
        closes = df[df.index <= as_of]["close"].tail(period + 5)
        if len(closes) < period + 1:
            return 50
        delta = closes.diff().dropna()
        gain = delta.clip(lower=0).rolling(period).mean()
        loss = (-delta.clip(upper=0)).rolling(period).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        val = rsi.iloc[-1]
        return float(val) if not pd.isna(val) else 50

    def _get_price(self, ticker: str, d: date, field: str = "close") -> Optional[float]:
        """특정 날짜의 가격"""
        if ticker not in self.prices:
            return None
        df = self.prices[ticker]
        if d in df.index:
            v = df.loc[d, field]
            return float(v) if not pd.isna(v) else None
        return None

    def _get_next_open(self, ticker: str, d: date) -> Optional[float]:
        """d 다음 거래일의 시가 (실행가)"""
        if ticker not in self.prices:
            return None
        df = self.prices[ticker]
        future = df[df.index > d]
        if len(future) == 0:
            return None
        return float(future.iloc[0]["open"])

    def _get_score(self, ticker: str, d: date) -> Optional[dict]:
        """해당 날짜의 점수"""
        if ticker not in self.scores:
            return None
        df = self.scores[ticker]
        # 해당일 또는 가장 최근 점수
        available = df[df.index <= d]
        if len(available) == 0:
            return None
        row = available.iloc[-1]
        return {
            "final_score": float(row.get("final_score", 50)),
            "layer3_score": float(row.get("layer3_score", 50)),
            "signal": str(row.get("signal", "HOLD")),
            "grade": str(row.get("grade", "B")),
        }

    def _get_recent_scores(self, ticker: str, d: date, n: int = 5) -> List[float]:
        """최근 N일 final_score"""
        if ticker not in self.scores:
            return []
        df = self.scores[ticker]
        available = df[df.index <= d].tail(n)
        return [float(x) for x in available["final_score"].values][::-1]  # 최신 먼저

    # ────────────────────────────────────────────
    # 시장 국면 감지
    # ────────────────────────────────────────────

    def _detect_regime(self, d: date) -> str:
        """해당 날짜의 시장 국면"""
        if self.spy is None or len(self.spy) == 0:
            return "NEUTRAL"
        spy_data = self.spy[self.spy.index <= d]
        if len(spy_data) < 200:
            return "NEUTRAL"

        closes = spy_data["close"]
        price = float(closes.iloc[-1])
        ma50 = float(closes.rolling(50).mean().iloc[-1])
        ma200 = float(closes.rolling(200).mean().iloc[-1])

        if price > ma200 and price > ma50:
            return "BULL"
        elif price > ma200:
            return "NEUTRAL"
        else:
            return "BEAR"

    # ────────────────────────────────────────────
    # 포트폴리오 가치 계산
    # ────────────────────────────────────────────

    def _portfolio_value(self, d: date) -> float:
        """현재 포트폴리오 총 가치"""
        invested = 0
        for ticker, pos in self.positions.items():
            price = self._get_price(ticker, d)
            if price:
                invested += price * pos.shares
            else:
                invested += pos.entry_price * pos.shares  # fallback
        return self.cash + invested

    # ────────────────────────────────────────────
    # 핵심: 백테스트 실행
    # ────────────────────────────────────────────

    def run(self, start_date: date, end_date: date) -> BacktestResult:
        """
        백테스트 메인 루프

        Parameters
        ----------
        start_date : date   백테스트 시작일
        end_date : date     백테스트 종료일

        Returns
        -------
        BacktestResult
        """
        self.cash = self.cfg.initial_capital
        self.positions = {}
        self.trades = []
        self.snapshots = []
        self.peak_value = self.cfg.initial_capital

        # 거래일 목록 (SPY 기준)
        if self.spy is not None:
            all_dates = sorted([
                d for d in self.spy.index
                if start_date <= d <= end_date
            ])
        else:
            all_dates = []

        if not all_dates:
            print("[BT] 거래일 없음!")
            return BacktestResult()

        self.trading_days = all_dates
        spy_start = float(self.spy.loc[all_dates[0], "close"]) if all_dates[0] in self.spy.index else 100

        prev_value = self.cfg.initial_capital
        weekly_start_value = self.cfg.initial_capital
        monthly_start_value = self.cfg.initial_capital
        prev_month = all_dates[0].month
        prev_week = all_dates[0].isocalendar()[1]
        weekly_return = 0.0
        monthly_return = 0.0

        print(f"[BT] 백테스트 시작: {start_date} → {end_date} ({len(all_dates)} 거래일)")

        for i, today in enumerate(all_dates):
            regime = self._detect_regime(today)

            # ── 주/월 시작 감지 ──
            current_week = today.isocalendar()[1]
            current_month = today.month
            if current_week != prev_week:
                weekly_start_value = prev_value
                prev_week = current_week
            if current_month != prev_month:
                monthly_start_value = prev_value
                prev_month = current_month

            # ── 1. 포트폴리오 레벨 리스크 체크 ──
            daily_ret = (prev_value - self.cfg.initial_capital) / self.cfg.initial_capital if i == 0 else 0
            if prev_value > 0 and i > 0:
                daily_ret = (self._portfolio_value(today) - prev_value) / prev_value
            weekly_return = (prev_value - weekly_start_value) / weekly_start_value if weekly_start_value > 0 else 0
            monthly_return = (prev_value - monthly_start_value) / monthly_start_value if monthly_start_value > 0 else 0

            halt_new_buys = False
            if monthly_return <= self.cfg.monthly_loss_limit:
                # 전량 청산
                self._liquidate_all(today)
                halt_new_buys = True
            elif weekly_return <= self.cfg.weekly_loss_limit:
                halt_new_buys = True
            elif daily_ret <= self.cfg.daily_loss_limit:
                halt_new_buys = True

            # ── 2. 보유 종목 매도 체크 (매일) ──
            sells = []
            for ticker, pos in list(self.positions.items()):
                price = self._get_price(ticker, today)
                if price is None:
                    continue

                # 최고가 업데이트
                if price > pos.highest_price:
                    pos.highest_price = price

                atr = self._calc_atr(ticker, today)
                score_data = self._get_score(ticker, today)
                recent = self._get_recent_scores(ticker, today)
                signal = score_data["signal"] if score_data else "HOLD"
                final_score = score_data["final_score"] if score_data else 50

                from backend.risk.risk_manager import check_position_risk
                risk = check_position_risk(
                    entry_price=pos.entry_price,
                    current_price=price,
                    highest_price=pos.highest_price,
                    atr_14=atr,
                    stop_loss_price=pos.stop_loss,
                    trailing_stop=pos.trailing_stop,
                    final_score=final_score,
                    recent_scores=recent,
                    signal=signal,
                    holding_days=pos.holding_days(today),
                    cfg=self.cfg,
                )

                # 트레일링 스톱 업데이트
                if risk.new_trailing_stop and risk.new_trailing_stop > pos.trailing_stop:
                    pos.trailing_stop = risk.new_trailing_stop

                if risk.should_sell:
                    sells.append((ticker, risk.reason))

            # 매도 실행 (T+1 시가)
            for ticker, reason in sells:
                self._execute_sell(ticker, today, reason)

            # ── 3. 매수 체크 (주간 리밸런싱 날만) ──
            is_rebalance_day = today.weekday() == self.cfg.rebalance_day
            if is_rebalance_day and not halt_new_buys and regime != "CRISIS":
                self._execute_weekly_rebalance(today, regime)

            # ── 4. 일일 스냅샷 ──
            total_val = self._portfolio_value(today)
            daily_return = (total_val - prev_value) / prev_value if prev_value > 0 else 0
            cum_return = (total_val - self.cfg.initial_capital) / self.cfg.initial_capital

            if total_val > self.peak_value:
                self.peak_value = total_val
            drawdown = (total_val - self.peak_value) / self.peak_value if self.peak_value > 0 else 0

            spy_price = float(self.spy.loc[today, "close"]) if today in self.spy.index else spy_start
            spy_cum = (spy_price - spy_start) / spy_start

            self.snapshots.append(DailySnapshot(
                date=today,
                total_value=round(total_val, 2),
                cash=round(self.cash, 2),
                invested=round(total_val - self.cash, 2),
                daily_return=round(daily_return, 6),
                cumulative_return=round(cum_return, 6),
                drawdown=round(drawdown, 6),
                num_positions=len(self.positions),
                regime=regime,
                spy_cumulative=round(spy_cum, 6),
            ))

            prev_value = total_val

            if (i + 1) % 50 == 0:
                print(f"  [{i+1}/{len(all_dates)}] {today} | 자산: ${total_val:,.0f} | 포지션: {len(self.positions)} | {regime}")

        # ── 결과 계산 ──
        return self._compute_results(start_date, end_date)

    # ────────────────────────────────────────────
    # 매수/매도 실행
    # ────────────────────────────────────────────

    def _execute_buy(self, ticker: str, d: date, shares: int, stop_loss: float):
        """매수 실행 (T+1 시가)"""
        exec_price = self._get_next_open(ticker, d)
        if exec_price is None:
            exec_price = self._get_price(ticker, d)
        if exec_price is None or shares <= 0:
            return

        # 슬리피지 적용
        exec_price *= (1 + self.cfg.slippage_pct)
        amount = exec_price * shares + self.cfg.commission_per_trade

        if amount > self.cash:
            shares = int(self.cash / exec_price)
            amount = exec_price * shares + self.cfg.commission_per_trade

        if shares <= 0:
            return

        self.cash -= amount
        atr = self._calc_atr(ticker, d)

        self.positions[ticker] = BacktestPosition(
            stock_id=self.stock_info.get(ticker, {}).get("stock_id", 0),
            ticker=ticker,
            sector=self.stock_info.get(ticker, {}).get("sector", "Unknown"),
            entry_date=d,
            entry_price=round(exec_price, 2),
            shares=shares,
            stop_loss=round(exec_price - self.cfg.stop_loss_atr_mult * atr, 2),
            trailing_stop=round(exec_price - self.cfg.trailing_stop_atr_mult * atr, 2),
            highest_price=exec_price,
        )

        self.trades.append(BacktestTrade(
            ticker=ticker, trade_type="BUY", trade_date=d,
            price=round(exec_price, 2), shares=shares,
            amount=round(amount, 2),
        ))

    def _execute_sell(self, ticker: str, d: date, reason: str):
        """매도 실행 (T+1 시가)"""
        if ticker not in self.positions:
            return
        pos = self.positions[ticker]

        exec_price = self._get_next_open(ticker, d)
        if exec_price is None:
            exec_price = self._get_price(ticker, d)
        if exec_price is None:
            exec_price = pos.entry_price  # fallback

        # 슬리피지 적용
        exec_price *= (1 - self.cfg.slippage_pct)

        amount = exec_price * pos.shares - self.cfg.commission_per_trade
        pnl = (exec_price - pos.entry_price) * pos.shares
        pnl_pct = (exec_price - pos.entry_price) / pos.entry_price if pos.entry_price > 0 else 0
        holding = pos.holding_days(d)

        self.cash += amount

        self.trades.append(BacktestTrade(
            ticker=ticker, trade_type="SELL", trade_date=d,
            price=round(exec_price, 2), shares=pos.shares,
            amount=round(amount, 2),
            entry_price=pos.entry_price,
            holding_days=holding,
            pnl=round(pnl, 2),
            pnl_pct=round(pnl_pct, 4),
            sell_reason=reason,
        ))

        del self.positions[ticker]

    def _liquidate_all(self, d: date):
        """전량 청산"""
        for ticker in list(self.positions.keys()):
            self._execute_sell(ticker, d, "PORTFOLIO_LIQUIDATE")

    # ────────────────────────────────────────────
    # 주간 리밸런싱
    # ────────────────────────────────────────────

    def _execute_weekly_rebalance(self, d: date, regime: str):
        """주간 리밸런싱 — 새 매수 시그널 확인 및 실행"""
        total_val = self._portfolio_value(d)

        # 현재 투자금, 섹터별 투자금
        invested = 0
        sector_invested = defaultdict(float)
        for ticker, pos in self.positions.items():
            price = self._get_price(ticker, d) or pos.entry_price
            val = price * pos.shares
            invested += val
            sector_invested[pos.sector] += val

        # BUY 후보 스캔
        candidates = []
        for ticker, info in self.stock_info.items():
            if ticker in self.positions:  # 이미 보유
                continue
            if ticker == "SPY":  # 벤치마크 제외
                continue

            score_data = self._get_score(ticker, d)
            if not score_data:
                continue

            final_score = score_data["final_score"]
            l3_score = score_data["layer3_score"]

            if final_score < self.cfg.buy_score_min:
                continue
            if l3_score < self.cfg.buy_l3_min:
                continue

            rsi = self._calc_rsi(ticker, d)
            if rsi >= self.cfg.buy_rsi_max:
                continue

            recent = self._get_recent_scores(ticker, d)
            # trend check
            trend_ok = True
            if len(recent) >= 3:
                drops = sum(1 for i in range(len(recent)-1)
                            if recent[i] < recent[i+1] - 2)
                trend_ok = drops < 2
            if not trend_ok:
                continue

            price = self._get_price(ticker, d)
            atr = self._calc_atr(ticker, d)
            if not price or atr <= 0:
                continue

            candidates.append({
                "stock_id": info.get("stock_id", 0),
                "ticker": ticker,
                "sector": info.get("sector", "Unknown"),
                "final_score": final_score,
                "signal_strength": final_score,
                "current_price": price,
                "atr_14": atr,
            })

        if not candidates:
            return

        # Score 순 정렬
        candidates.sort(key=lambda x: x["final_score"], reverse=True)

        # 섹터 분산
        sector_count = defaultdict(int)
        for pos in self.positions.values():
            sector_count[pos.sector] += 1

        selected = []
        for c in candidates:
            sector = c["sector"]
            if sector_count.get(sector, 0) >= self.cfg.max_stocks_per_sector:
                continue
            selected.append(c)
            sector_count[sector] = sector_count.get(sector, 0) + 1
            if len(selected) + len(self.positions) >= self.cfg.max_positions:
                break

        # 포지션 사이징 & 실행
        from backend.portfolio.position_sizer import calculate_position_size
        for c in selected:
            ps = calculate_position_size(
                ticker=c["ticker"],
                current_price=c["current_price"],
                atr_14=c["atr_14"],
                final_score=c["final_score"],
                regime=regime,
                account_value=total_val,
                current_invested=invested,
                sector=c["sector"],
                sector_invested=dict(sector_invested),
                num_positions=len(self.positions),
                cfg=self.cfg,
            )
            if ps.shares > 0:
                self._execute_buy(c["ticker"], d, ps.shares, ps.stop_loss_price)
                invested += ps.position_value
                sector_invested[c["sector"]] += ps.position_value

    # ────────────────────────────────────────────
    # 결과 계산
    # ────────────────────────────────────────────

    def _compute_results(self, start_date: date, end_date: date) -> BacktestResult:
        """백테스트 결과 종합"""
        result = BacktestResult()
        result.start_date = start_date
        result.end_date = end_date
        result.initial_capital = self.cfg.initial_capital
        result.daily_snapshots = self.snapshots
        result.trades = self.trades

        if not self.snapshots:
            return result

        # 기본 수익률
        final_val = self.snapshots[-1].total_value
        result.total_return = round((final_val - self.cfg.initial_capital) / self.cfg.initial_capital * 100, 2)

        # CAGR
        days = (end_date - start_date).days
        years = days / 365.25
        if years > 0 and final_val > 0:
            result.cagr = round(((final_val / self.cfg.initial_capital) ** (1 / years) - 1) * 100, 2)

        # 일일 수익률 시리즈
        daily_rets = np.array([s.daily_return for s in self.snapshots])

        # Sharpe (연환산)
        if len(daily_rets) > 1 and np.std(daily_rets) > 0:
            result.sharpe_ratio = round(
                np.mean(daily_rets) / np.std(daily_rets) * np.sqrt(252), 2
            )

        # Sortino (하방 변동성만)
        neg_rets = daily_rets[daily_rets < 0]
        if len(neg_rets) > 0 and np.std(neg_rets) > 0:
            result.sortino_ratio = round(
                np.mean(daily_rets) / np.std(neg_rets) * np.sqrt(252), 2
            )

        # Max Drawdown
        dd = [s.drawdown for s in self.snapshots]
        result.max_drawdown = round(min(dd) * 100, 2) if dd else 0

        # Calmar
        if result.max_drawdown != 0:
            result.calmar_ratio = round(result.cagr / abs(result.max_drawdown), 2)

        # 거래 통계 (SELL만)
        sell_trades = [t for t in self.trades if t.trade_type == "SELL"]
        result.total_trades = len(sell_trades)
        wins = [t for t in sell_trades if t.pnl > 0]
        losses = [t for t in sell_trades if t.pnl <= 0]
        result.winning_trades = len(wins)
        result.losing_trades = len(losses)
        result.win_rate = round(len(wins) / len(sell_trades) * 100, 2) if sell_trades else 0

        total_profit = sum(t.pnl for t in wins)
        total_loss = abs(sum(t.pnl for t in losses))
        result.profit_factor = round(total_profit / total_loss, 2) if total_loss > 0 else 999

        result.avg_holding_days = round(
            np.mean([t.holding_days for t in sell_trades]), 1
        ) if sell_trades else 0

        result.avg_win = round(np.mean([t.pnl_pct for t in wins]) * 100, 2) if wins else 0
        result.avg_loss = round(np.mean([t.pnl_pct for t in losses]) * 100, 2) if losses else 0

        # SPY 대비
        if self.snapshots:
            result.spy_return = round(self.snapshots[-1].spy_cumulative * 100, 2)
            result.alpha = round(result.total_return - result.spy_return, 2)

        # Beta
        spy_rets = np.array([s.spy_cumulative for s in self.snapshots])
        if len(spy_rets) > 1:
            spy_daily = np.diff(spy_rets)
            port_daily = daily_rets[1:]
            if len(spy_daily) == len(port_daily) and np.var(spy_daily) > 0:
                result.beta = round(
                    np.cov(port_daily, spy_daily)[0, 1] / np.var(spy_daily), 2
                )

        # Information Ratio
        if len(daily_rets) > 1:
            spy_daily_rets = np.diff([0] + [s.spy_cumulative for s in self.snapshots])
            excess = daily_rets - spy_daily_rets[:len(daily_rets)]
            if np.std(excess) > 0:
                result.information_ratio = round(
                    np.mean(excess) / np.std(excess) * np.sqrt(252), 2
                )

        # 월별 수익률
        monthly = defaultdict(float)
        for s in self.snapshots:
            key = f"{s.date.year}-{s.date.month:02d}"
            monthly[key] = round(s.cumulative_return * 100, 2)
        result.monthly_returns = dict(monthly)

        return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 결과 출력 헬퍼
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def print_backtest_summary(r: BacktestResult):
    """백테스트 결과 예쁘게 출력"""
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║               BACKTEST RESULTS SUMMARY                       ║
╠══════════════════════════════════════════════════════════════╣
║  Period:  {r.start_date} → {r.end_date}                     
║  Capital: ${r.initial_capital:,.0f}                          
╠══════════════════════════════════════════════════════════════╣
║  📈 PERFORMANCE                                              ║
║  Total Return:    {r.total_return:>8.2f}%                    
║  CAGR:            {r.cagr:>8.2f}%                            
║  Sharpe Ratio:    {r.sharpe_ratio:>8.2f}                     
║  Sortino Ratio:   {r.sortino_ratio:>8.2f}                    
║  Max Drawdown:    {r.max_drawdown:>8.2f}%                    
║  Calmar Ratio:    {r.calmar_ratio:>8.2f}                     
╠══════════════════════════════════════════════════════════════╣
║  📊 TRADING STATS                                            ║
║  Total Trades:    {r.total_trades:>8d}                       
║  Win Rate:        {r.win_rate:>8.1f}%                        
║  Profit Factor:   {r.profit_factor:>8.2f}                    
║  Avg Hold Days:   {r.avg_holding_days:>8.1f}                 
║  Avg Win:         {r.avg_win:>8.2f}%                         
║  Avg Loss:        {r.avg_loss:>8.2f}%                        
╠══════════════════════════════════════════════════════════════╣
║  🎯 vs BENCHMARK                                             ║
║  SPY Return:      {r.spy_return:>8.2f}%                      
║  Alpha:           {r.alpha:>8.2f}%                           
║  Beta:            {r.beta:>8.2f}                             
║  Info Ratio:      {r.information_ratio:>8.2f}                
╚══════════════════════════════════════════════════════════════╝
""")
