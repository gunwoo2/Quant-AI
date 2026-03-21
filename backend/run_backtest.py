"""
run_backtest.py — QUANT AI 백테스트 실행 진입점
=================================================

사용법:
  cd backend
  python run_backtest.py                     # 기본 (최근 1년)
  python run_backtest.py --period 2y         # 최근 2년
  python run_backtest.py --start 2024-01-01  # 특정 시작일
  python run_backtest.py --grid              # 가중치 Grid Search 포함

Phase B 목표:
  1. DB에서 과거 가격+점수 로드
  2. backtest_engine.py 실행 (865줄 이미 구현됨)
  3. 거래비용+슬리피지 반영
  4. 결과 리포트 (Sharpe, MDD, 수익률, vs SPY)
  5. 팩터 가중치 검증 (Grid Search)
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import patch_numpy_adapter
except ImportError:
    pass

import argparse
import numpy as np
import pandas as pd
from datetime import date, datetime, timedelta
from collections import defaultdict

from db_pool import init_pool, get_cursor
from backend.risk.trading_config import TradingConfig
from backtest_engine import BacktestEngine, BacktestResult, print_backtest_summary


# ═══════════════════════════════════════════════════════════
#  데이터 로딩 (DB → Engine)
# ═══════════════════════════════════════════════════════════

def load_backtest_data(engine: BacktestEngine, start_date: date, end_date: date):
    """
    DB에서 백테스트 데이터 로딩.
    backtest_engine.load_from_db()를 사용하되,
    stocks 테이블의 sector_id → sector_code 변환 처리.
    """
    print(f"\n[DATA] 데이터 로딩: {start_date} → {end_date}")

    # ── 1. 종목 정보 (sector_id → sector_code 변환) ──
    with get_cursor() as cur:
        cur.execute("""
            SELECT s.stock_id, s.ticker, s.company_name,
                   COALESCE(sec.sector_code, '99') AS sector
            FROM stocks s
            LEFT JOIN sectors sec ON s.sector_id = sec.sector_id
            WHERE s.is_active = TRUE
        """)
        for row in cur.fetchall():
            r = dict(row)
            engine.stock_info[r["ticker"]] = r

    tickers = list(engine.stock_info.keys())
    print(f"[DATA] 종목: {len(tickers)}개")

    # ── 2. 가격 데이터 (벌크 로딩) ──
    load_start = start_date - timedelta(days=400)  # ATR/MA 계산용 여유
    price_count = 0

    with get_cursor() as cur:
        # 벌크 쿼리로 한 번에 로딩 (종목별 루프 대신)
        cur.execute("""
            SELECT s.ticker,
                   p.trade_date AS date,
                   p.open_price AS open,
                   p.high_price AS high,
                   p.low_price AS low,
                   p.close_price AS close,
                   p.volume
            FROM stock_prices_daily p
            JOIN stocks s ON p.stock_id = s.stock_id
            WHERE s.is_active = TRUE
              AND p.trade_date BETWEEN %s AND %s
            ORDER BY s.ticker, p.trade_date
        """, (load_start, end_date))
        rows = [dict(r) for r in cur.fetchall()]

    if rows:
        df_all = pd.DataFrame(rows)
        df_all["date"] = pd.to_datetime(df_all["date"]).dt.date
        for col in ["open", "high", "low", "close", "volume"]:
            df_all[col] = pd.to_numeric(df_all[col], errors="coerce")

        for ticker, group in df_all.groupby("ticker"):
            df_t = group.set_index("date").sort_index().drop(columns=["ticker"])
            engine.prices[ticker] = df_t
            price_count += 1

    print(f"[DATA] 가격: {price_count}개 종목 로딩")

    # ── 3. 점수 데이터 (벌크 로딩) ──
    score_count = 0
    with get_cursor() as cur:
        cur.execute("""
            SELECT s.ticker,
                   f.calc_date AS date,
                   f.weighted_score AS final_score,
                   f.layer3_score,
                   COALESCE(f.signal, 'HOLD') AS signal,
                   f.final_grade AS grade
            FROM stock_final_scores f
            JOIN stocks s ON f.stock_id = s.stock_id
            WHERE s.is_active = TRUE
              AND f.calc_date BETWEEN %s AND %s
            ORDER BY s.ticker, f.calc_date
        """, (start_date - timedelta(days=30), end_date))
        rows = [dict(r) for r in cur.fetchall()]

    if rows:
        df_scores = pd.DataFrame(rows)
        df_scores["date"] = pd.to_datetime(df_scores["date"]).dt.date
        for col in ["final_score", "layer3_score"]:
            df_scores[col] = pd.to_numeric(df_scores[col], errors="coerce")

        for ticker, group in df_scores.groupby("ticker"):
            df_s = group.set_index("date").sort_index().drop(columns=["ticker"])
            engine.scores[ticker] = df_s
            score_count += 1

    print(f"[DATA] 점수: {score_count}개 종목 로딩")

    # ── 4. SPY (벤치마크) ──
    if "SPY" in engine.prices:
        engine.spy = engine.prices["SPY"][["open", "close"]].copy()
        print(f"[DATA] SPY: {len(engine.spy)}일 데이터")
    else:
        print("[DATA] ⚠️  SPY 데이터 없음! 벤치마크 비교 불가")
        # SPY 없으면 빈 DataFrame 생성
        engine.spy = pd.DataFrame(columns=["open", "close"])

    # ── 5. 데이터 품질 체크 ──
    tickers_with_scores = set(engine.scores.keys())
    tickers_with_prices = set(engine.prices.keys())
    both = tickers_with_scores & tickers_with_prices
    print(f"[DATA] 가격+점수 모두 있는 종목: {len(both)}개")

    if len(both) < 10:
        print("[DATA] ⚠️  점수 데이터가 부족합니다!")
        print("[DATA]     배치를 먼저 실행해주세요: python test_m7_batch.py")
        print("[DATA]     또는 전체 배치: python -m batch.scheduler")

    return len(both)


# ═══════════════════════════════════════════════════════════
#  백테스트 실행
# ═══════════════════════════════════════════════════════════

def run_backtest(
    start_date: date = None,
    end_date: date = None,
    initial_capital: float = 100_000,
    commission: float = 1.0,         # $1 per trade
    slippage: float = 0.001,         # 0.1%
) -> BacktestResult:
    """
    메인 백테스트 실행.

    Parameters
    ----------
    start_date : 시작일 (None이면 1년 전)
    end_date   : 종료일 (None이면 오늘)
    """
    if end_date is None:
        end_date = date.today()
    if start_date is None:
        start_date = end_date - timedelta(days=365)

    # 설정
    cfg = TradingConfig(
        initial_capital=initial_capital,
        commission_per_trade=commission,
        slippage_pct=slippage,
    )

    # 엔진 생성
    engine = BacktestEngine(cfg=cfg)

    # 데이터 로딩
    n_stocks = load_backtest_data(engine, start_date, end_date)

    if n_stocks < 5:
        print("\n❌ 백테스트 불가: 점수 데이터가 있는 종목이 5개 미만입니다.")
        print("   먼저 배치를 실행해 점수를 쌓아주세요.")
        return None

    # 백테스트 실행
    print(f"\n{'='*60}")
    print(f"  QUANT AI v3.1 — BACKTEST ENGINE")
    print(f"  Period: {start_date} → {end_date}")
    print(f"  Capital: ${initial_capital:,.0f}")
    print(f"  Commission: ${commission:.2f}/trade")
    print(f"  Slippage: {slippage*100:.2f}%")
    print(f"{'='*60}")

    result = engine.run(start_date, end_date)

    # 결과 출력
    print_backtest_summary(result)

    # 추가 분석
    _print_monthly_returns(result)
    _print_trade_analysis(result)

    return result


# ═══════════════════════════════════════════════════════════
#  가중치 Grid Search
# ═══════════════════════════════════════════════════════════

def run_weight_grid_search(
    start_date: date = None,
    end_date: date = None,
):
    """
    L1:L2:L3 가중치 최적화.
    현재 50:25:25를 포함한 다양한 비율을 테스트.

    주의: 과적합 위험이 있으므로 결과는 참고용입니다.
    """
    if end_date is None:
        end_date = date.today()
    if start_date is None:
        start_date = end_date - timedelta(days=365)

    # 테스트할 가중치 조합 (합계 = 100)
    weight_combos = [
        (50, 25, 25, "현재 (50:25:25)"),
        (60, 20, 20, "L1 강화 (60:20:20)"),
        (40, 30, 30, "L1 약화 (40:30:30)"),
        (50, 30, 20, "L2 강화 (50:30:20)"),
        (50, 20, 30, "L3 강화 (50:20:30)"),
        (45, 25, 30, "기술 강화 (45:25:30)"),
        (55, 25, 20, "재무 강화 (55:25:20)"),
        (40, 35, 25, "NLP 강화 (40:35:25)"),
        (33, 34, 33, "균등 (33:34:33)"),
    ]

    print(f"\n{'='*70}")
    print(f"  QUANT AI — 가중치 Grid Search")
    print(f"  Period: {start_date} → {end_date}")
    print(f"  Combos: {len(weight_combos)}개")
    print(f"{'='*70}")

    # 먼저 데이터 한 번만 로딩
    cfg = TradingConfig()
    engine_base = BacktestEngine(cfg=cfg)
    n_stocks = load_backtest_data(engine_base, start_date, end_date)

    if n_stocks < 5:
        print("\n❌ Grid Search 불가: 점수 데이터 부족")
        return []

    results = []

    for l1_w, l2_w, l3_w, label in weight_combos:
        print(f"\n── {label} ──")

        # 점수 재계산: weighted_score = l1*w1 + l2*w2 + l3*w3
        adjusted_scores = _recalculate_scores(
            engine_base.scores, l1_w/100, l2_w/100, l3_w/100,
            start_date, end_date,
        )

        cfg_test = TradingConfig()
        engine_test = BacktestEngine(cfg=cfg_test)
        engine_test.prices = engine_base.prices
        engine_test.scores = adjusted_scores
        engine_test.spy = engine_base.spy
        engine_test.stock_info = engine_base.stock_info

        try:
            result = engine_test.run(start_date, end_date)
            results.append({
                "label": label,
                "l1_w": l1_w, "l2_w": l2_w, "l3_w": l3_w,
                "total_return": result.total_return,
                "sharpe": result.sharpe_ratio,
                "mdd": result.max_drawdown,
                "win_rate": result.win_rate,
                "trades": result.total_trades,
                "alpha": result.alpha,
            })
            print(f"  Return={result.total_return:.1f}% Sharpe={result.sharpe_ratio:.2f} "
                  f"MDD={result.max_drawdown:.1f}% Alpha={result.alpha:.1f}%")
        except Exception as e:
            print(f"  ❌ 실패: {e}")
            results.append({"label": label, "error": str(e)})

    # 결과 비교 테이블
    _print_grid_results(results)

    return results


def _recalculate_scores(
    original_scores: dict,
    l1_w: float, l2_w: float, l3_w: float,
    start_date: date, end_date: date,
) -> dict:
    """
    DB의 l1/l2/l3 개별 점수로 가중치를 재계산.
    original_scores에 l1/l2/l3이 없으면 final_score를 그대로 사용.
    """
    # DB에서 개별 레이어 점수 가져오기
    layer_scores = {}

    with get_cursor() as cur:
        cur.execute("""
            SELECT s.ticker,
                   f.calc_date AS date,
                   f.layer1_score, f.layer2_score, f.layer3_score,
                   COALESCE(f.signal, 'HOLD') AS signal,
                   f.final_grade AS grade
            FROM stock_final_scores f
            JOIN stocks s ON f.stock_id = s.stock_id
            WHERE s.is_active = TRUE
              AND f.calc_date BETWEEN %s AND %s
            ORDER BY s.ticker, f.calc_date
        """, (start_date - timedelta(days=30), end_date))
        rows = [dict(r) for r in cur.fetchall()]

    if not rows:
        return original_scores

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    for col in ["layer1_score", "layer2_score", "layer3_score"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # 가중치 재계산
    df["final_score"] = (
        df["layer1_score"].fillna(50) * l1_w +
        df["layer2_score"].fillna(50) * l2_w +
        df["layer3_score"].fillna(50) * l3_w
    )

    # 원래 포맷으로 변환
    new_scores = {}
    for ticker, group in df.groupby("ticker"):
        df_s = group[["date", "final_score", "layer3_score", "signal", "grade"]].copy()
        df_s = df_s.set_index("date").sort_index()
        new_scores[ticker] = df_s

    return new_scores


# ═══════════════════════════════════════════════════════════
#  출력 헬퍼
# ═══════════════════════════════════════════════════════════

def _print_monthly_returns(result: BacktestResult):
    """월별 수익률 테이블"""
    if not result.monthly_returns:
        return

    print(f"\n  📅 월별 누적 수익률")
    print(f"  {'─'*40}")

    prev = 0
    for month_key in sorted(result.monthly_returns.keys()):
        cum = result.monthly_returns[month_key]
        monthly = cum - prev
        prev = cum
        bar = "█" * max(0, int(monthly / 2)) if monthly > 0 else "▒" * max(0, int(-monthly / 2))
        sign = "+" if monthly >= 0 else ""
        print(f"  {month_key}  {sign}{monthly:>6.1f}%  {bar}")


def _print_trade_analysis(result: BacktestResult):
    """거래 분석 (상위 5 수익/손실)"""
    sell_trades = [t for t in result.trades if t.trade_type == "SELL"]
    if not sell_trades:
        print("\n  📊 거래 없음")
        return

    # 상위 수익 거래
    top_wins = sorted(sell_trades, key=lambda t: t.pnl, reverse=True)[:5]
    top_losses = sorted(sell_trades, key=lambda t: t.pnl)[:5]

    print(f"\n  🏆 TOP 5 수익 거래")
    print(f"  {'─'*55}")
    for t in top_wins:
        if t.pnl > 0:
            print(f"  {t.ticker:6s} {t.trade_date} +${t.pnl:>8,.0f} ({t.pnl_pct*100:>+5.1f}%) {t.holding_days:>3d}일")

    print(f"\n  💀 TOP 5 손실 거래")
    print(f"  {'─'*55}")
    for t in top_losses:
        if t.pnl < 0:
            print(f"  {t.ticker:6s} {t.trade_date} -${abs(t.pnl):>8,.0f} ({t.pnl_pct*100:>+5.1f}%) {t.holding_days:>3d}일")

    # 매도 사유 분석
    reasons = defaultdict(int)
    for t in sell_trades:
        reasons[t.sell_reason or "UNKNOWN"] += 1

    print(f"\n  📋 매도 사유 분석")
    print(f"  {'─'*35}")
    for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
        print(f"  {reason:20s} {count:>4d}건 ({count/len(sell_trades)*100:.0f}%)")


def _print_grid_results(results: list):
    """Grid Search 결과 비교 테이블"""
    valid = [r for r in results if "error" not in r]
    if not valid:
        print("\n❌ 유효한 결과 없음")
        return

    print(f"\n{'='*75}")
    print(f"  가중치 Grid Search 결과 비교")
    print(f"{'='*75}")
    print(f"  {'가중치':20s} {'Return':>8s} {'Sharpe':>8s} {'MDD':>8s} {'WinRate':>8s} {'Alpha':>8s}")
    print(f"  {'─'*20} {'─'*8} {'─'*8} {'─'*8} {'─'*8} {'─'*8}")

    # Sharpe 기준 정렬
    valid.sort(key=lambda x: x.get("sharpe", 0), reverse=True)

    for r in valid:
        marker = " ★" if r.get("label", "").startswith("현재") else ""
        print(f"  {r['label']:20s} "
              f"{r['total_return']:>7.1f}% "
              f"{r['sharpe']:>8.2f} "
              f"{r['mdd']:>7.1f}% "
              f"{r['win_rate']:>7.1f}% "
              f"{r['alpha']:>7.1f}%{marker}")

    print(f"\n  ★ = 현재 설정")

    # 최적 추천
    best = valid[0]
    print(f"\n  💡 Sharpe 기준 최적: {best['label']}")
    print(f"     Return={best['total_return']:.1f}% Sharpe={best['sharpe']:.2f} MDD={best['mdd']:.1f}%")

    if not valid[0].get("label", "").startswith("현재"):
        print(f"\n  ⚠️  주의: 이 결과는 과거 데이터 기반이므로 과적합 가능성이 있습니다.")
        print(f"     Walk-Forward 검증을 반드시 수행하세요.")


# ═══════════════════════════════════════════════════════════
#  CLI 진입점
# ═══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="QUANT AI v3.1 — 백테스트 실행",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python run_backtest.py                         기본 (최근 1년, $100K)
  python run_backtest.py --period 2y             최근 2년
  python run_backtest.py --period 6m             최근 6개월
  python run_backtest.py --start 2024-01-01      특정 시작일
  python run_backtest.py --capital 50000         자본금 $50K
  python run_backtest.py --grid                  가중치 Grid Search 포함
  python run_backtest.py --grid --period 2y      2년 Grid Search
        """
    )
    parser.add_argument("--start", type=str, default=None,
                        help="시작일 (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default=None,
                        help="종료일 (YYYY-MM-DD)")
    parser.add_argument("--period", type=str, default="1y",
                        help="기간 (6m, 1y, 2y, 3y)")
    parser.add_argument("--capital", type=float, default=100_000,
                        help="초기 자본금 (기본: $100,000)")
    parser.add_argument("--commission", type=float, default=1.0,
                        help="거래 수수료 (기본: $1/trade)")
    parser.add_argument("--slippage", type=float, default=0.001,
                        help="슬리피지 (기본: 0.1%%)")
    parser.add_argument("--grid", action="store_true",
                        help="가중치 Grid Search 실행")

    args = parser.parse_args()

    # 날짜 파싱
    end_date = date.today()
    if args.end:
        end_date = date.fromisoformat(args.end)

    if args.start:
        start_date = date.fromisoformat(args.start)
    else:
        period_map = {
            "3m": 90, "6m": 180, "1y": 365, "2y": 730, "3y": 1095, "5y": 1825
        }
        days = period_map.get(args.period, 365)
        start_date = end_date - timedelta(days=days)

    # DB 연결
    print("""
╔══════════════════════════════════════════════════════════════╗
║              QUANT AI v3.1 — BACKTEST ENGINE                 ║
╚══════════════════════════════════════════════════════════════╝
    """)
    init_pool()

    # 메인 백테스트
    result = run_backtest(
        start_date=start_date,
        end_date=end_date,
        initial_capital=args.capital,
        commission=args.commission,
        slippage=args.slippage,
    )

    # Grid Search (옵션)
    if args.grid and result is not None:
        run_weight_grid_search(start_date, end_date)

    print("\n🎉 백테스트 완료!")


if __name__ == "__main__":
    main()
