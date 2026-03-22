"""
batch_trading_signals.py — QUANT AI v3.3 트레이딩 시그널 배치
================================================================
v3.3 통합: DynamicConfig + DD 5단계 + CircuitBreaker + CorrelationFilter + DecisionAudit

파이프라인:
  1. 시장 국면 판단 (regime_detector v2)
  2. DD/CB 리스크 상태 평가
  3. 보유종목 SELL 체크 (8중 안전장치)
  4. BUY 후보 스캔 + 다중 필터
  5. 포트폴리오 구성 + Kelly 사이징
  6. DB 저장 + Discord 알림
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import patch_numpy_adapter
except ImportError:
    pass

import importlib.util
import numpy as np
import pandas as pd
from datetime import datetime, date, timedelta
from collections import defaultdict

from db_pool import get_cursor

# ── v3.3 패키지 import ──
from risk.trading_config import DynamicConfig
from risk.drawdown_controller import DrawdownController
from risk.circuit_breaker import CircuitBreaker
from risk.risk_manager import check_position_risk
from portfolio.correlation_filter import CorrelationFilter
from portfolio.position_sizer import calculate_position_size
from analytics.decision_audit import DecisionAudit

# ── signal 패키지 (Python 내장 signal 충돌 우회) ──
def _import_signal_module(name):
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for folder in ["signals", "signal"]:
        path = os.path.join(backend_dir, folder, f"{name}.py")
        if os.path.exists(path):
            spec = importlib.util.spec_from_file_location(f"_{name}", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    raise ImportError(f"signal(s)/{name}.py not found")

_regime_mod = _import_signal_module("regime_detector")
_signal_mod = _import_signal_module("signal_generator")
detect_regime = _regime_mod.detect_regime
generate_buy_signal = _signal_mod.generate_buy_signal
generate_sell_signal = _signal_mod.generate_sell_signal

# 글로벌 상태 (배치 내 단일 인스턴스)
_dd_controller = DrawdownController(cooldown_days=5)
_cb = CircuitBreaker()
_corr_filter = CorrelationFilter(threshold=0.80)


# ═══════════════════════════════════════════════════════════
#  메인 파이프라인
# ═══════════════════════════════════════════════════════════

def run_trading_signals(calc_date: date = None, dry_run: bool = True):
    if calc_date is None:
        calc_date = datetime.now().date()

    print(f"\n{'='*60}")
    print(f"  QUANT AI v3.3 — Trading Signal Pipeline")
    print(f"  Date: {calc_date} | Mode: {'DRY RUN' if dry_run else '⚡ LIVE'}")
    print(f"{'='*60}")

    # ── Step 1: 시장 국면 판단 ──
    print("\n── Step 1/7: 시장 국면 판단 ──")
    regime_result = _detect_market_regime(calc_date)
    regime = regime_result["regime"]
    print(f"  {regime} | SPY=${regime_result['spy_price']:,.2f} | VIX={regime_result.get('vix_close', 'N/A')}")
    _save_regime(calc_date, regime_result)

    # DynamicConfig — 국면별 자동 파라미터
    cfg = DynamicConfig()
    cfg.apply_regime(regime)

    # ── Step 2: DD/CB 리스크 상태 평가 ──
    print("\n── Step 2/7: 리스크 상태 평가 ──")
    current_positions = _load_current_positions()
    stocks = _load_stock_data(calc_date)
    account_value = _get_account_value(current_positions, stocks, cfg)

    # Drawdown 평가
    peak_value = account_value  # TODO: portfolio_daily_snapshot에서 max 조회
    with get_cursor() as cur:
        cur.execute("SELECT MAX(total_value) as peak FROM portfolio_daily_snapshot WHERE portfolio_id = 1")
        row = cur.fetchone()
        if row and row["peak"]:
            peak_value = max(float(row["peak"]), account_value)

    dd_status = _dd_controller.evaluate(calc_date, account_value, peak_value)
    cfg.apply_dd_override(dd_status.mode.name)
    print(f"  DD: {dd_status.mode.name} ({dd_status.drawdown_pct:.1f}%) | Buy={'✅' if dd_status.buy_allowed else '❌'} | Mult={dd_status.position_size_mult:.1f}")

    # Circuit Breaker 평가
    cb_status = _cb.evaluate(calc_date)
    print(f"  CB: {cb_status.level.name} | 연패={cb_status.consecutive_losses} | Buy={'✅' if cb_status.buy_allowed else '❌'}")

    # DecisionAudit 초기화
    audit = DecisionAudit(calc_date=calc_date, regime=regime, dd_mode=dd_status.mode.name)

    # ── Step 3: 보유종목 SELL 체크 ──
    print(f"\n── Step 3/7: 보유종목 SELL 체크 ({len(current_positions)}개) ──")
    sell_signals = []

    for ticker, pos in current_positions.items():
        stock = stocks.get(ticker)
        if not stock:
            continue

        risk = check_position_risk(
            entry_price=pos["entry_price"],
            current_price=stock["current_price"],
            highest_price=pos["highest_price"],
            atr_14=stock.get("atr_14", 0),
            atr_20d_avg=stock.get("atr_14", 0),
            stop_loss_price=pos["stop_loss_price"],
            trailing_stop=pos["trailing_stop"],
            final_score=stock.get("final_score", 50),
            recent_scores=stock.get("recent_scores", []),
            signal=stock.get("signal", "HOLD"),
            holding_days=(calc_date - pos["entry_date"]).days,
            volume_today=stock.get("volume_today", 0),
            volume_20d_avg=stock.get("volume_20d_avg", 0),
        )

        if risk.should_sell:
            pnl_pct = (stock["current_price"] - pos["entry_price"]) / pos["entry_price"] * 100
            sell_signals.append({
                "ticker": ticker,
                "stock_id": pos["stock_id"],
                "reason": risk.reason,
                "price": stock["current_price"],
                "entry_price": pos["entry_price"],
                "holding_days": (calc_date - pos["entry_date"]).days,
                "pnl_pct": pnl_pct,
                "shares": pos["shares"],
            })
            # CB에 거래 기록
            pnl_dollar = (stock["current_price"] - pos["entry_price"]) * pos["shares"]
            _cb.record_trade(pnl_dollar)
            print(f"  🔴 SELL {ticker}: {risk.reason} ({pnl_pct:+.1f}%)")
        else:
            if risk.new_trailing_stop and risk.new_trailing_stop > pos["trailing_stop"]:
                _update_trailing_stop(pos["position_id"], risk.new_trailing_stop, stock["current_price"])

    if not sell_signals:
        print("  매도 대상 없음")
    print(f"  SELL: {len(sell_signals)}건")

    # ── Step 4: BUY 후보 스캔 + 필터 ──
    print(f"\n── Step 4/7: BUY 후보 스캔 ({len(stocks)}종목) ──")
    buy_candidates = []
    held_tickers = list(current_positions.keys())

    # 상관 필터용 가격 데이터
    price_df = _load_price_matrix(calc_date, list(stocks.keys()))

    for ticker, stock in stocks.items():
        rec = audit.create_record(stock_id=stock["stock_id"], ticker=ticker)
        rec.final_score = stock.get("final_score", 0)

        if ticker in current_positions:
            rec.decision = "HOLD_EXISTING"
            audit.add(rec)
            continue

        final_score = stock.get("final_score", 0)
        rsi = stock.get("rsi_14", 50)
        atr = stock.get("atr_14", 0)
        price = stock.get("current_price", 0)

        # 점수 필터
        rec.score_filter = final_score >= cfg.buy_score_min
        if not rec.score_filter:
            rec.decision = "SKIP"
            audit.add(rec)
            continue

        # RSI 필터
        rec.rsi_filter = rsi < 70
        if not rec.rsi_filter:
            rec.decision = "SKIP"
            audit.add(rec)
            continue

        # 국면 필터 (CB/DD)
        rec.regime_filter = True
        rec.dd_filter = dd_status.buy_allowed
        rec.circuit_breaker_filter = cb_status.buy_allowed

        if not dd_status.buy_allowed or not cb_status.buy_allowed:
            rec.decision = "SKIP"
            audit.add(rec)
            continue

        # 유동성 필터
        vol_avg = stock.get("volume_20d_avg", 0)
        rec.liquidity_filter = vol_avg > 100000 if vol_avg else True

        if not rec.liquidity_filter:
            rec.decision = "SKIP"
            audit.add(rec)
            continue

        # 상관 필터
        if price_df is not None and ticker in price_df.columns:
            corr_check = _corr_filter.check_entry(ticker, held_tickers, price_df)
            rec.correlation_filter = corr_check.passed
        else:
            rec.correlation_filter = True

        if not rec.correlation_filter:
            rec.decision = "SKIP"
            audit.add(rec)
            continue

        if price <= 0 or atr <= 0:
            rec.decision = "SKIP"
            audit.add(rec)
            continue

        # 통과! BUY 후보
        rec.decision = "BUY_CANDIDATE"
        audit.add(rec)

        buy_candidates.append({
            "stock_id": stock["stock_id"],
            "ticker": ticker,
            "sector": stock.get("sector", "99"),
            "final_score": final_score,
            "layer3_score": stock.get("layer3_score", 0),
            "rsi_value": rsi,
            "current_price": price,
            "atr_14": atr,
            "grade": stock.get("grade", ""),
        })

    buy_candidates.sort(key=lambda x: x["final_score"], reverse=True)
    print(f"  BUY 후보: {len(buy_candidates)}개")
    for c in buy_candidates[:5]:
        print(f"  🟢 {c['ticker']:6s} {c['grade']:3s} ({c['final_score']:.1f}점) @ ${c['current_price']:,.2f}")

    # ── Step 5: 포트폴리오 구성 + 사이징 ──
    print(f"\n── Step 5/7: 포트폴리오 구성 ──")
    current_invested = sum(
        stocks.get(t, {}).get("current_price", p["entry_price"]) * p["shares"]
        for t, p in current_positions.items()
    )
    sector_invested = defaultdict(float)
    for t, p in current_positions.items():
        sec = stocks.get(t, {}).get("sector", "99")
        sector_invested[sec] += stocks.get(t, {}).get("current_price", p["entry_price"]) * p["shares"]

    buy_signals = []
    num_existing = len(current_positions) - len(sell_signals)
    max_new = max(0, cfg.max_positions - num_existing)

    for c in buy_candidates[:max_new]:
        ps = calculate_position_size(
            ticker=c["ticker"],
            current_price=c["current_price"],
            atr_14=c["atr_14"],
            final_score=c["final_score"],
            grade=c["grade"],
            regime=regime,
            account_value=account_value,
            current_invested=current_invested,
            sector=c["sector"],
            sector_invested=dict(sector_invested),
            num_positions=num_existing + len(buy_signals),
            dd_mult=dd_status.position_size_mult,
            cb_mult=cb_status.position_mult,
        )

        if ps.shares <= 0:
            continue

        buy_signals.append({
            "ticker": c["ticker"],
            "stock_id": c["stock_id"],
            "score": c["final_score"],
            "grade": c["grade"],
            "price": c["current_price"],
            "shares": ps.shares,
            "amount": ps.position_value,
            "weight": ps.weight_pct,
            "stop_loss": ps.stop_loss_price,
            "sector": c["sector"],
        })
        current_invested += ps.position_value
        sector_invested[c["sector"]] += ps.position_value
        held_tickers.append(c["ticker"])

    total_invested = sum(s["amount"] for s in buy_signals)
    print(f"  신규 매수: {len(buy_signals)}건 | 투자금: ${total_invested:,.0f}")

    # ── Step 6/7: DB 저장 ──
    print(f"\n── Step 6/7: DB 저장 ──")
    _save_signals(calc_date, buy_signals, sell_signals, stocks, regime)

    if not dry_run:
        _process_sells(calc_date, sell_signals)
        _process_buys(calc_date, buy_signals)
    else:
        print("  [DRY RUN] 포지션 변경 없음 (시그널만 저장)")

    _save_portfolio_snapshot(calc_date, current_positions, stocks, regime, cfg)

    # Audit 저장 (DB)
    try:
        audit.save_to_db()
    except Exception as e:
        print(f"  ⚠️ Audit 저장 실패: {e}")

    # ── Step 7/7: Discord 알림 ──
    print(f"\n── Step 7/7: Discord 알림 ──")
    try:
        from notifier import notify_daily_signals
        portfolio_summary = {
            "total_value": account_value,
            "cash_pct": max(0, (account_value - current_invested) / account_value * 100) if account_value > 0 else 100,
            "num_positions": num_existing + len(buy_signals),
            "daily_return": 0,
            "vs_spy": 0,
        }
        notify_daily_signals(
            calc_date=calc_date,
            regime=regime,
            regime_detail=regime_result,
            buy_signals=buy_signals,
            sell_signals=sell_signals,
            portfolio_summary=portfolio_summary,
        )
    except Exception as e:
        print(f"  ⚠️ 알림 실패: {e}")

    # 국면 전환 알림
    try:
        _check_regime_change(calc_date, regime)
    except Exception:
        pass


    # ── ★ v3.6: 긴급 매도 + 반등 기회 알림 ──
    fire_signals = [s for s in sell_signals if s.get("reason", "").startswith("HARD_STOP") 
                    or s.get("pnl_pct", 0) < -15]
    if fire_signals:
        try:
            from notifier import notify_fire_sell
            notify_fire_sell(calc_date=calc_date, fire_signals=fire_signals, 
                           trigger="HARD_STOP / 손실 15%+")
        except Exception as e:
            print(f"  ⚠️ 긴급매도 알림 실패: {e}")

    # 반등 기회: 최근 5일 -10% 이상 하락 후 오늘 +2% 이상 반등
    bounce_signals = []
    try:
        from db_pool import get_cursor as _gc
        with _gc() as cur:
            cur.execute("""
                SELECT s.ticker, s.stock_id, spr.current_price, spr.price_change_pct,
                       fs.weighted_score, fs.grade
                FROM stock_prices_realtime spr
                JOIN stocks s ON s.stock_id = spr.stock_id
                LEFT JOIN final_scores fs ON fs.stock_id = s.stock_id AND fs.calc_date = %s
                WHERE spr.price_change_pct > 2.0
                AND s.stock_id IN (
                    SELECT stock_id FROM stock_prices_daily
                    WHERE trade_date >= %s - INTERVAL '5 days'
                    GROUP BY stock_id
                    HAVING MIN(close_price) / MAX(close_price) < 0.90
                )
            """, (calc_date, calc_date))
            for row in cur.fetchall():
                bounce_signals.append({
                    "ticker": row["ticker"],
                    "price": float(row["current_price"]),
                    "today_change": float(row["price_change_pct"] or 0),
                    "score": float(row["weighted_score"] or 0) if row.get("weighted_score") else 0,
                    "grade": row.get("grade", "?"),
                })
    except Exception:
        pass

    if bounce_signals:
        try:
            from notifier import notify_bounce_opportunity
            notify_bounce_opportunity(calc_date=calc_date, bounce_signals=bounce_signals)
        except Exception as e:
            print(f"  ⚠️ 반등기회 알림 실패: {e}")

    # 결과 요약
    print(f"\n{'='*60}")
    print(f"  ✅ v3.3 시그널 파이프라인 완료")
    print(f"  시장: {regime} ({dd_status.mode.name}) | BUY: {len(buy_signals)} | SELL: {len(sell_signals)}")
    print(f"  Audit: {audit.count('BUY_CANDIDATE')} 후보 → {len(buy_signals)} 매수")
    print(f"{'='*60}\n")

    return {
        "regime": regime,
        "dd_mode": dd_status.mode.name,
        "buy_count": len(buy_signals),
        "sell_count": len(sell_signals),
        "buy_signals": buy_signals,
        "sell_signals": sell_signals,
    }


def _load_price_matrix(calc_date: date, tickers: list) -> pd.DataFrame:
    """상관필터용 60일 가격 매트릭스"""
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT s.ticker, p.trade_date, p.close_price
                FROM stock_prices_daily p
                JOIN stocks s ON p.stock_id = s.stock_id
                WHERE p.trade_date >= %s - INTERVAL '90 days'
                  AND p.trade_date <= %s
                  AND s.is_active = TRUE
                ORDER BY p.trade_date
            """, (calc_date, calc_date))
            rows = cur.fetchall()
        if not rows:
            return None
        df = pd.DataFrame([dict(r) for r in rows])
        pivot = df.pivot_table(index='trade_date', columns='ticker', values='close_price')
        return pivot.dropna(axis=1, thresh=40)
    except Exception:
        return None


def _check_regime_change(calc_date: date, current_regime: str):
    """전일 대비 국면 변경 시 알림"""
    with get_cursor() as cur:
        cur.execute("""
            SELECT regime FROM market_regime
            WHERE regime_date < %s ORDER BY regime_date DESC LIMIT 1
        """, (calc_date,))
        row = cur.fetchone()
    if row and row["regime"] != current_regime:
        old_regime = row["regime"]
        try:
            from notifier import notify_regime_change
            notify_regime_change(
                calc_date=calc_date,
                old_regime=old_regime,
                new_regime=current_regime,
                detail=f"DynamicConfig가 자동으로 파라미터를 조정합니다."
            )
        except Exception:
            # fallback to emergency
            try:
                from notifier import notify_emergency
                notify_emergency(
                    f"시장 국면 전환: {old_regime} → {current_regime}",
                    f"전일 {old_regime}에서 {current_regime}로 변경"
                )
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════
#  DB 헬퍼 함수 (v3.2 호환)
# ═══════════════════════════════════════════════════════════

def _detect_market_regime(calc_date: date) -> dict:
    """DB에서 SPY 가격 + VIX 로딩 → 국면 판단"""
    spy_closes = {}
    vix_close = None

    with get_cursor() as cur:
        # SPY 종가 (최근 250일)
        cur.execute("""
            SELECT p.trade_date, p.close_price
            FROM stock_prices_daily p
            JOIN stocks s ON p.stock_id = s.stock_id
            WHERE s.ticker = 'SPY'
              AND p.trade_date >= %s - INTERVAL '400 days'
              AND p.trade_date <= %s
            ORDER BY p.trade_date
        """, (calc_date, calc_date))
        for row in cur.fetchall():
            spy_closes[row["trade_date"]] = float(row["close_price"])

        # VIX (market_signal_daily에서)
        cur.execute("""
            SELECT vix_close FROM market_signal_daily
            ORDER BY calc_date DESC LIMIT 1
        """)
        vrow = cur.fetchone()
        if vrow and vrow["vix_close"]:
            vix_close = float(vrow["vix_close"])

    if not spy_closes:
        return {"regime": "NEUTRAL", "spy_price": 0, "spy_ma50": 0, "spy_ma200": 0, "vix_close": vix_close}

    spy_series = pd.Series(spy_closes).sort_index().astype(float)
    result = detect_regime(spy_series, vix_close=vix_close)

    return {
        "regime": result.regime,
        "spy_price": result.spy_price,
        "spy_ma50": result.spy_ma50,
        "spy_ma200": result.spy_ma200,
        "vix_close": result.vix_close,
        "multiplier": result.multiplier,
    }


def _save_regime(calc_date: date, regime_data: dict):
    """시장 국면 DB 저장"""
    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO market_regime (regime_date, regime, spy_price, spy_ma50, spy_ma200, vix_close, regime_multiplier)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (regime_date) DO UPDATE SET
                regime = EXCLUDED.regime,
                spy_price = EXCLUDED.spy_price,
                spy_ma50 = EXCLUDED.spy_ma50,
                spy_ma200 = EXCLUDED.spy_ma200,
                vix_close = EXCLUDED.vix_close,
                regime_multiplier = EXCLUDED.regime_multiplier
        """, (
            calc_date, regime_data["regime"],
            regime_data["spy_price"], regime_data["spy_ma50"],
            regime_data["spy_ma200"], regime_data.get("vix_close"),
            regime_data.get("multiplier", 0.7),
        ))


def _load_stock_data(calc_date: date) -> dict:
    """전 종목 최신 데이터 로딩 (점수+가격+기술지표)"""
    stocks = {}

    with get_cursor() as cur:
        # Final Score + 가격 + 기술지표 조인
        cur.execute("""
            SELECT
                s.stock_id, s.ticker,
                COALESCE(sec.sector_code, '99') AS sector,
                f.weighted_score AS final_score,
                f.layer1_score, f.layer2_score, f.layer3_score,
                f.grade, f.signal,
                p.close_price AS current_price,
                p.open_price,
                t.rsi_14,
                t.volume_20d_avg
            FROM stocks s
            JOIN stock_final_scores f ON s.stock_id = f.stock_id
                AND f.calc_date = (SELECT MAX(calc_date) FROM stock_final_scores WHERE stock_id = s.stock_id AND calc_date <= %s)
            LEFT JOIN LATERAL (
                SELECT close_price, open_price
                FROM stock_prices_daily
                WHERE stock_id = s.stock_id AND trade_date <= %s
                ORDER BY trade_date DESC LIMIT 1
            ) p ON TRUE
            LEFT JOIN LATERAL (
                SELECT rsi_14, volume_20d_avg
                FROM technical_indicators
                WHERE stock_id = s.stock_id AND calc_date <= %s
                ORDER BY calc_date DESC LIMIT 1
            ) t ON TRUE
            LEFT JOIN sectors sec ON s.sector_id = sec.sector_id
            WHERE s.is_active = TRUE
        """, (calc_date, calc_date, calc_date))

        for row in cur.fetchall():
            r = dict(row)
            ticker = r["ticker"]
            stocks[ticker] = {
                "stock_id": r["stock_id"],
                "ticker": ticker,
                "sector": r.get("sector", "99"),
                "final_score": float(r["final_score"]) if r["final_score"] else 0,
                "layer3_score": float(r["layer3_score"]) if r["layer3_score"] else 0,
                "grade": r.get("grade", ""),
                "signal": r.get("signal", "HOLD"),
                "current_price": float(r["current_price"]) if r["current_price"] else 0,
                "rsi_14": float(r["rsi_14"]) if r["rsi_14"] else 50,
                "atr_14": 0,  # 아래에서 별도 계산
                "recent_scores": [],
            }

    # ATR 14 계산 (종목별)
    _calc_atr_bulk(stocks, calc_date)

    # 최근 5일 점수
    _load_recent_scores(stocks, calc_date)

    return stocks


def _calc_atr_bulk(stocks: dict, calc_date: date):
    """전 종목 ATR 14 벌크 계산"""
    stock_ids = [s["stock_id"] for s in stocks.values()]
    if not stock_ids:
        return

    with get_cursor() as cur:
        for ticker, s in stocks.items():
            cur.execute("""
                SELECT high_price, low_price, close_price
                FROM stock_prices_daily
                WHERE stock_id = %s AND trade_date <= %s
                ORDER BY trade_date DESC LIMIT 15
            """, (s["stock_id"], calc_date))
            rows = [dict(r) for r in cur.fetchall()]

            if len(rows) < 2:
                continue

            # ATR 계산
            trs = []
            for i in range(len(rows) - 1):
                h = float(rows[i]["high_price"] or 0)
                l = float(rows[i]["low_price"] or 0)
                pc = float(rows[i + 1]["close_price"] or 0)
                tr = max(h - l, abs(h - pc), abs(l - pc))
                trs.append(tr)

            if trs:
                s["atr_14"] = sum(trs[:14]) / min(14, len(trs))


def _load_recent_scores(stocks: dict, calc_date: date):
    """최근 5일 Final Score 로딩"""
    with get_cursor() as cur:
        for ticker, s in stocks.items():
            cur.execute("""
                SELECT weighted_score FROM stock_final_scores
                WHERE stock_id = %s AND calc_date <= %s
                ORDER BY calc_date DESC LIMIT 5
            """, (s["stock_id"], calc_date))
            rows = cur.fetchall()
            s["recent_scores"] = [float(r["weighted_score"]) for r in rows if r["weighted_score"]]


def _load_current_positions() -> dict:
    """현재 OPEN 포지션 로딩"""
    positions = {}
    with get_cursor() as cur:
        cur.execute("""
            SELECT pp.position_id, pp.stock_id, s.ticker,
                   pp.entry_date, pp.entry_price, pp.shares,
                   pp.stop_loss_price, pp.trailing_stop, pp.highest_price
            FROM portfolio_positions pp
            JOIN stocks s ON pp.stock_id = s.stock_id
            WHERE pp.status = 'OPEN' AND pp.portfolio_id = 1
        """)
        for row in cur.fetchall():
            r = dict(row)
            positions[r["ticker"]] = {
                "position_id": r["position_id"],
                "stock_id": r["stock_id"],
                "entry_date": r["entry_date"],
                "entry_price": float(r["entry_price"]),
                "shares": int(float(r["shares"])),
                "stop_loss_price": float(r["stop_loss_price"] or 0),
                "trailing_stop": float(r["trailing_stop"] or 0),
                "highest_price": float(r["highest_price"] or r["entry_price"]),
            }
    return positions


def _get_account_value(positions: dict, stocks: dict, cfg) -> float:
    """현재 계좌 평가액"""
    invested = 0
    for ticker, pos in positions.items():
        price = stocks.get(ticker, {}).get("current_price", pos["entry_price"])
        invested += price * pos["shares"]

    # portfolio_daily_snapshot에서 현금 잔고 가져오기
    cash = cfg.initial_capital
    with get_cursor() as cur:
        cur.execute("""
            SELECT cash_balance FROM portfolio_daily_snapshot
            WHERE portfolio_id = 1
            ORDER BY snapshot_date DESC LIMIT 1
        """)
        row = cur.fetchone()
        if row and row["cash_balance"]:
            cash = float(row["cash_balance"])

    return invested + cash


def _update_trailing_stop(position_id: int, new_trailing: float, current_price: float):
    """트레일링 스톱 업데이트"""
    with get_cursor() as cur:
        cur.execute("""
            UPDATE portfolio_positions
            SET trailing_stop = %s, highest_price = GREATEST(highest_price, %s), updated_at = NOW()
            WHERE position_id = %s
        """, (new_trailing, current_price, position_id))


def _save_signals(calc_date, buy_signals, sell_signals, stocks, regime):
    """trading_signals 테이블에 저장"""
    with get_cursor() as cur:
        # BUY
        for s in buy_signals:
            stock = stocks.get(s["ticker"], {})
            cur.execute("""
                INSERT INTO trading_signals
                    (stock_id, signal_date, signal_type, signal_strength,
                     grade_condition, momentum_condition, rsi_condition, trend_condition, regime_condition,
                     final_score, layer3_score, rsi_value, atr_14, current_price)
                VALUES (%s, %s, 'BUY', %s, TRUE, TRUE, TRUE, TRUE, TRUE, %s, %s, %s, %s, %s)
                ON CONFLICT (stock_id, signal_date) DO UPDATE SET
                    signal_type = EXCLUDED.signal_type,
                    signal_strength = EXCLUDED.signal_strength,
                    final_score = EXCLUDED.final_score,
                    current_price = EXCLUDED.current_price
            """, (
                s["stock_id"], calc_date, s["score"],
                stock.get("final_score", 0), stock.get("layer3_score", 0),
                stock.get("rsi_14", 50), stock.get("atr_14", 0),
                s["price"],
            ))

        # SELL
        for s in sell_signals:
            cur.execute("""
                INSERT INTO trading_signals
                    (stock_id, signal_date, signal_type, sell_reason, final_score, current_price)
                VALUES (%s, %s, 'SELL', %s, %s, %s)
                ON CONFLICT (stock_id, signal_date) DO UPDATE SET
                    signal_type = 'SELL',
                    sell_reason = EXCLUDED.sell_reason,
                    current_price = EXCLUDED.current_price
            """, (
                s["stock_id"], calc_date, s["reason"],
                stocks.get(s["ticker"], {}).get("final_score", 0),
                s["price"],
            ))

    print(f"  ✅ 시그널 DB 저장 (BUY={len(buy_signals)}, SELL={len(sell_signals)})")


def _process_sells(calc_date, sell_signals):
    """매도 처리: 포지션 CLOSE + 거래 이력"""
    with get_cursor() as cur:
        for s in sell_signals:
            # 포지션 종료
            cur.execute("""
                UPDATE portfolio_positions
                SET status = 'CLOSED', exit_date = %s, exit_price = %s,
                    exit_reason = %s, realized_pnl = %s, updated_at = NOW()
                WHERE stock_id = %s AND portfolio_id = 1 AND status = 'OPEN'
            """, (
                calc_date, s["price"], s["reason"],
                (s["price"] - s["entry_price"]) * s["shares"],
                s["stock_id"],
            ))

            # 거래 이력
            cur.execute("""
                INSERT INTO trade_history
                    (portfolio_id, stock_id, trade_type, trade_date, price, shares, amount,
                     entry_price, holding_days, realized_pnl, realized_pct, sell_reason)
                VALUES (1, %s, 'SELL', %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                s["stock_id"], calc_date, s["price"], s["shares"],
                s["price"] * s["shares"],
                s["entry_price"], s["holding_days"],
                (s["price"] - s["entry_price"]) * s["shares"],
                s["pnl_pct"] / 100,
                s["reason"],
            ))

    print(f"  ✅ 매도 처리: {len(sell_signals)}건")


def _process_buys(calc_date, buy_signals):
    """매수 처리: 포지션 OPEN + 거래 이력"""
    with get_cursor() as cur:
        for s in buy_signals:
            # 포지션 생성
            cur.execute("""
                INSERT INTO portfolio_positions
                    (portfolio_id, stock_id, entry_date, entry_price, shares, position_value,
                     stop_loss_price, trailing_stop, highest_price, current_price, status)
                VALUES (1, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'OPEN')
            """, (
                s["stock_id"], calc_date, s["price"], s["shares"],
                s["amount"], s["stop_loss"],
                s["price"],  # trailing_stop = entry initially
                s["price"],  # highest_price = entry
                s["price"],
            ))

            # 거래 이력
            cur.execute("""
                INSERT INTO trade_history
                    (portfolio_id, stock_id, trade_type, trade_date, price, shares, amount)
                VALUES (1, %s, 'BUY', %s, %s, %s, %s)
            """, (
                s["stock_id"], calc_date, s["price"], s["shares"], s["amount"],
            ))

    print(f"  ✅ 매수 처리: {len(buy_signals)}건")


def _save_portfolio_snapshot(calc_date, positions, stocks, regime, cfg):
    """일일 포트폴리오 스냅샷 저장"""
    invested = 0
    for ticker, pos in positions.items():
        price = stocks.get(ticker, {}).get("current_price", pos["entry_price"])
        invested += price * pos["shares"]

    cash = _get_account_value(positions, stocks, cfg) - invested
    total = invested + cash

    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO portfolio_daily_snapshot
                (portfolio_id, snapshot_date, total_value, cash_balance, invested_value,
                 num_positions, regime)
            VALUES (1, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (portfolio_id, snapshot_date) DO UPDATE SET
                total_value = EXCLUDED.total_value,
                cash_balance = EXCLUDED.cash_balance,
                invested_value = EXCLUDED.invested_value,
                num_positions = EXCLUDED.num_positions,
                regime = EXCLUDED.regime
        """, (calc_date, total, cash, invested, len(positions), regime))


# ═══════════════════════════════════════════════════════════
#  직접 실행
# ═══════════════════════════════════════════════════════════



if __name__ == "__main__":
    from db_pool import init_pool
    init_pool()

    import argparse
    parser = argparse.ArgumentParser(description="QUANT AI v3.3 Trading Signals")
    parser.add_argument("--live", action="store_true", help="LIVE 모드 (포지션 실변경)")
    parser.add_argument("--date", type=str, default=None, help="기준일 (YYYY-MM-DD)")
    args = parser.parse_args()

    cd = date.fromisoformat(args.date) if args.date else None
    run_trading_signals(calc_date=cd, dry_run=not args.live)