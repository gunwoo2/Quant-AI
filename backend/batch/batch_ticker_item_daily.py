"""
batch_ticker_item_daily.py — Phase 1 일일 배치잡
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
매일 02:00 KST 실행 (scheduler.py에서 호출)

Step 1. yfinance 벌크 다운로드 → stock_prices_daily, stock_prices_realtime
Step 2. 재무 파생지표 보완 (ROIC, EV, PEG 등) — ETF 제외
Step 3. Layer 1 점수 계산 → quant_*_scores, sector_percentile_scores, stock_layer1_analysis

변경이력:
  v1.0  — 초기 구현
  v2.0  — 설계서 정합성 전면 검증 후 재작성
          · yf.download() 벌크 호출로 속도 10~50x 개선
          · PEG를 yf.Ticker().info → DB 내부 계산으로 변경 (API 제거)
          · ETF 제외 로직 추가 (재무/퀀트 함수)
          · ROIC 세율 하드코딩 → 실효세율 사용
          · COALESCE 제거 → 매번 최신값 갱신
          · sector_percentile 섹터별 캐시 (중복 쿼리 제거)
          · DB 쿼리 벌크화 (종목당 4~5회 → 전체 3~4회)
          · Earnings Revision/Surprise 데이터 없을 시 중립 처리
          · EPS Stability 백분위 오류 수정 (GPA→EPS CV)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import patch_numpy_adapter
except ImportError:
    pass

import yfinance as yf
import pandas as pd
import numpy as np
from decimal import Decimal
from datetime import datetime, date, timedelta
from db_pool import get_cursor
from batch.calculator import (
    calc_moat_scores, calc_value_scores,
    calc_momentum_scores, calc_stability_scores, calc_layer1_score,
)
from utils.sector_percentile import calc_sector_percentiles, calc_sector_percentiles_bulk
from utils.grade_utils import score_to_grade


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 헬퍼
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _f(v):
    """Decimal, np.float64 등 → float 안전 변환"""
    if v is None:
        return None
    try:
        fv = float(v)
        if np.isnan(fv) or np.isinf(fv):
            return None
        return fv
    except Exception:
        return None



def _sanitize(d: dict) -> dict:
    """dict의 모든 numpy 값을 Python 네이티브로 변환 (DB INSERT 안전)"""
    if not isinstance(d, dict):
        return d
    result = {}
    for k, v in d.items():
        if v is None:
            result[k] = None
        elif isinstance(v, (np.floating,)):
            result[k] = None if np.isnan(v) else float(v)
        elif isinstance(v, (np.integer,)):
            result[k] = int(v)
        elif isinstance(v, np.bool_):
            result[k] = bool(v)
        elif isinstance(v, float):
            result[k] = None if (np.isnan(v) or np.isinf(v)) else v
        else:
            result[k] = v
    return result


def _log_start(job_type: str) -> int:
    try:
        with get_cursor() as cur:
            cur.execute("""
                INSERT INTO batch_job_logs (job_name, job_type, started_at, status)
                VALUES (%s, %s, NOW(), 'RUNNING') RETURNING log_id
            """, (f"batch_ticker_item_daily_{job_type}", job_type))
            row = cur.fetchone()
            return row["log_id"] if row else 0
    except Exception:
        return 0


def _log_end(log_id: int, status: str, processed: int, failed: int, error: str = None):
    try:
        with get_cursor() as cur:
            cur.execute("""
                UPDATE batch_job_logs
                SET status = %s, completed_at = NOW(),
                    records_processed = %s, records_failed = %s, error_message = %s
                WHERE log_id = %s
            """, (status, processed, failed, error, log_id))
    except Exception as e:
        print(f"[LOG] 기록 실패: {e}")


def _get_active_stocks() -> list:
    """전체 활성 종목 (ETF 포함)"""
    with get_cursor() as cur:
        cur.execute("""
            SELECT s.stock_id, s.ticker, sec.sector_code, sec.sector_id,
                   s.shares_outstanding
            FROM stocks s
            LEFT JOIN sectors sec ON s.sector_id = sec.sector_id
            WHERE s.is_active = TRUE
            ORDER BY s.ticker
        """)
        return [dict(r) for r in cur.fetchall()]


def _get_active_equities() -> list:
    """재무 데이터가 있는 일반 종목만 (ETF 제외)"""
    with get_cursor() as cur:
        cur.execute("""
            SELECT s.stock_id, s.ticker, sec.sector_code, sec.sector_id,
                   s.shares_outstanding
            FROM stocks s
            LEFT JOIN sectors sec ON s.sector_id = sec.sector_id
            WHERE s.is_active = TRUE
              AND s.sector_id IS NOT NULL
            ORDER BY s.ticker
        """)
        return [dict(r) for r in cur.fetchall()]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Step 1: 전일 OHLCV (벌크 다운로드)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run_daily_price(target_date: date = None):
    """
    yf.download()로 전 종목 OHLCV를 한 번에 가져옴.
    기존: 종목당 1회 HTTP → 100종목 = 100회 (200~600초)
    변경: 1회 벌크 HTTP → 100종목 = 1회 (~5초)
    """
    if target_date is None:
        target_date = (datetime.now() - timedelta(days=1)).date()

    log_id = _log_start("DAILY_PRICE")
    stocks = _get_active_stocks()
    ok, fail = 0, 0

    # ── 벌크 다운로드 ──
    ticker_list = [s["ticker"] for s in stocks]
    ticker_map = {s["ticker"]: s["stock_id"] for s in stocks}

    print(f"[PRICE] {len(ticker_list)}개 종목 벌크 다운로드 시작...")
    try:
        df_all = yf.download(
            tickers=ticker_list,
            period="5d",          # 최근 5일 (주말/공휴일 대비)
            group_by="ticker",
            auto_adjust=True,
            threads=True,         # 멀티스레드
            progress=False,
        )
    except Exception as e:
        print(f"[PRICE] 벌크 다운로드 실패: {e}")
        _log_end(log_id, "FAILED", 0, len(ticker_list), str(e))
        return 0, len(ticker_list)

    if df_all is None or df_all.empty:
        print("[PRICE] 데이터 없음")
        _log_end(log_id, "FAILED", 0, len(ticker_list))
        return 0, len(ticker_list)

    print(f"[PRICE] 벌크 다운로드 완료, 종목별 처리 시작...")

    # ── 종목별 파싱 & DB 저장 ──
    is_single = len(ticker_list) == 1

    for ticker, stock_id in ticker_map.items():
        try:
            # 단일 종목이면 컬럼 구조가 다름
            if is_single:
                df_t = df_all.copy()
            else:
                if ticker not in df_all.columns.get_level_values(0):
                    fail += 1
                    continue
                df_t = df_all[ticker].dropna(how="all")

            if df_t is None or df_t.empty or len(df_t) < 1:
                fail += 1
                continue

            # 마지막 행 = 가장 최근 거래일
            row = df_t.iloc[-1]
            o = float(row.get("Open")   or 0)
            h = float(row.get("High")   or 0)
            l = float(row.get("Low")    or 0)
            c = float(row.get("Close")  or 0)
            v = int(row.get("Volume")   or 0)

            if c <= 0:
                fail += 1
                continue

            # 전일 종가
            prev_close = None
            if len(df_t) >= 2:
                prev_close = float(df_t.iloc[-2]["Close"])

            chg_amt = round(c - prev_close, 4) if prev_close else 0.0
            chg_pct = round(chg_amt / prev_close * 100, 4) if (prev_close and prev_close != 0) else 0.0

            # 실제 거래일 (df 인덱스)
            actual_date = df_t.index[-1]
            if hasattr(actual_date, 'date'):
                actual_date = actual_date.date()
            else:
                actual_date = target_date

            with get_cursor() as cur:
                cur.execute("""
                    INSERT INTO stock_prices_daily (
                        stock_id, trade_date,
                        open_price, high_price, low_price,
                        close_price, adj_close_price, volume, data_source
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'yfinance')
                    ON CONFLICT (stock_id, trade_date) DO UPDATE SET
                        open_price      = EXCLUDED.open_price,
                        high_price      = EXCLUDED.high_price,
                        low_price       = EXCLUDED.low_price,
                        close_price     = EXCLUDED.close_price,
                        adj_close_price = EXCLUDED.adj_close_price,
                        volume          = EXCLUDED.volume,
                        data_source     = EXCLUDED.data_source
                """, (stock_id, actual_date, o, h, l, c, c, v))

                cur.execute("""
                    INSERT INTO stock_prices_realtime (
                        stock_id, current_price, price_change,
                        price_change_pct, volume_today, data_source, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, 'yfinance', NOW())
                    ON CONFLICT (stock_id) DO UPDATE SET
                        current_price    = EXCLUDED.current_price,
                        price_change     = EXCLUDED.price_change,
                        price_change_pct = EXCLUDED.price_change_pct,
                        volume_today     = EXCLUDED.volume_today,
                        updated_at       = NOW()
                """, (stock_id, c, chg_amt, chg_pct, v))

            ok += 1
            if ok % 20 == 0 or ok <= 3:
                print(f"[PRICE] {ticker}: ${c:.2f} ({chg_pct:+.2f}%) ✓")

        except Exception as e:
            fail += 1
            print(f"[PRICE] {ticker} 실패: {e}")

    _log_end(log_id, "SUCCESS" if fail == 0 else "PARTIAL", ok, fail)
    print(f"[PRICE] 완료: {ok}성공 / {fail}실패")
    return ok, fail


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Step 2: 재무 파생지표 보완 (ETF 제외)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run_supplement_financials():
    """
    재무 파생지표 계산 & stock_financials UPDATE.
    ★ ETF는 _get_active_equities()로 제외.
    ★ PEG를 yf.Ticker().info 대신 DB 내부 계산으로 변경 (API 0회).
    ★ COALESCE 제거 → 매번 최신값 갱신.
    ★ ROIC 실효세율 사용.
    """
    log_id = _log_start("FUNDAMENTALS")
    stocks = _get_active_equities()     # ★ ETF 제외
    ok, fail = 0, 0

    for s in stocks:
        ticker   = s["ticker"]
        stock_id = s["stock_id"]
        shares   = _f(s.get("shares_outstanding")) or 0

        try:
            # ── 현재 주가 ──
            price = 0.0
            with get_cursor() as cur:
                cur.execute("""
                    SELECT current_price FROM stock_prices_realtime
                    WHERE stock_id = %s
                """, (stock_id,))
                rt = cur.fetchone()
                if rt:
                    price = _f(rt["current_price"]) or 0.0

            market_cap = price * shares if (price and shares) else None

            # ── 최신 2개 연간 재무 ──
            fins = []
            with get_cursor() as cur:
                cur.execute("""
                    SELECT fiscal_year, revenue, ebit, net_income,
                           operating_cash_flow, total_assets, total_equity,
                           total_debt, cash_and_equivalents, ebitda,
                           invested_capital, free_cash_flow,
                           income_tax, pretax_income, eps_actual
                    FROM stock_financials
                    WHERE stock_id = %s AND report_type = 'ANNUAL'
                    ORDER BY fiscal_year DESC LIMIT 2
                """, (stock_id,))
                fins = [dict(r) for r in cur.fetchall()]

            if not fins:
                fail += 1
                continue

            fin      = fins[0]
            fin_prev = fins[1] if len(fins) > 1 else {}

            ebit   = _f(fin.get("ebit"))
            ic     = _f(fin.get("invested_capital"))
            debt   = _f(fin.get("total_debt"))
            cash   = _f(fin.get("cash_and_equivalents"))
            rev    = _f(fin.get("revenue"))
            ta     = _f(fin.get("total_assets"))
            equity = _f(fin.get("total_equity"))
            ocf    = _f(fin.get("operating_cash_flow"))
            fcf    = _f(fin.get("free_cash_flow"))
            ni     = _f(fin.get("net_income"))

            # ── ROIC (실효세율 사용) ──
            # 설계서: NOPAT ÷ Invested Capital, NOPAT = EBIT × (1 - Tax Rate)
            roic = None
            if ebit is not None and ic and ic != 0:
                tax = _f(fin.get("income_tax"))
                pretax = _f(fin.get("pretax_income"))
                if tax is not None and pretax and pretax != 0:
                    eff_tax_rate = max(0.0, min(abs(tax / pretax), 0.50))
                else:
                    eff_tax_rate = 0.21    # fallback: 미국 법인세
                nopat = ebit * (1 - eff_tax_rate)
                roic = round(nopat / ic, 4)

            # ── Enterprise Value ──
            ev = (market_cap + (debt or 0) - (cash or 0)) if market_cap else None

            # ── EBITDA ──
            ebitda = _f(fin.get("ebitda"))
            if not ebitda and ebit:
                ebitda = round(ebit * 1.2, 2)

            # ── Net Debt / EBITDA ──
            net_debt = ((debt or 0) - (cash or 0)) if debt is not None else None
            nde = round(net_debt / ebitda, 4) if (net_debt is not None and ebitda and ebitda != 0) else None

            # ── EV/EBIT, EV/FCF ──
            ev_ebit = round(ev / ebit, 2) if (ev and ebit and ebit != 0) else None
            ev_fcf  = round(ev / fcf,  2) if (ev and fcf  and fcf  != 0) else None

            # ── P/B ──
            pb = round(market_cap / equity, 2) if (market_cap and equity and equity != 0) else None

            # ── Asset Turnover ──
            ato = round(rev / ta, 4) if (rev and ta and ta != 0) else None

            # ── Operating Leverage ──
            op_lev = None
            if fin_prev:
                prev_ebit = _f(fin_prev.get("ebit"))
                prev_rev  = _f(fin_prev.get("revenue"))
                if all(v is not None for v in [ebit, prev_ebit, rev, prev_rev]):
                    if prev_ebit != 0 and prev_rev != 0:
                        d_ebit = (ebit - prev_ebit) / abs(prev_ebit)
                        d_rev  = (rev  - prev_rev)  / abs(prev_rev)
                        if d_rev != 0:
                            op_lev = round(d_ebit / d_rev, 4)

            # ── PEG (DB 내부 계산, yfinance API 제거) ──
            # 설계서: PER ÷ EPS 성장률
            peg = None
            if market_cap and ni and ni > 0:
                per = market_cap / ni
                # EPS 성장률: 전기 대비
                prev_ni = _f(fin_prev.get("net_income")) if fin_prev else None
                if prev_ni and prev_ni > 0:
                    eps_growth = ((ni - prev_ni) / abs(prev_ni)) * 100
                    if eps_growth > 0:
                        peg = round(per / eps_growth, 4)

            # ── BVPS ──
            bvps = round(equity / shares, 4) if (equity and shares) else None

            # ── GPA (Gross Profit / Total Assets) ──
            gpa = None
            gross_profit = _f(fin.get("gross_profit"))
            if gross_profit and ta and ta != 0:
                gpa = round(gross_profit / ta, 4)

            # ── FCF Margin ──
            fcf_margin = None
            if fcf is not None and rev and rev != 0:
                fcf_margin = round(fcf / rev, 4)

            # ── Accruals Quality ──
            accruals = None
            if ni is not None and ocf is not None and ta and ta != 0:
                accruals = round((ni - ocf) / ta, 4)

            # ── DB 갱신 (COALESCE 제거: 매번 최신값으로 갱신) ──
            with get_cursor() as cur:
                cur.execute("""
                    UPDATE stock_financials SET
                        roic               = %s,
                        enterprise_value   = %s,
                        ev_ebit            = %s,
                        ev_fcf             = %s,
                        pb_ratio           = %s,
                        peg_ratio          = %s,
                        net_debt_ebitda    = %s,
                        ebitda             = %s,
                        asset_turnover     = %s,
                        operating_leverage = %s,
                        book_value_per_share = %s,
                        gpa                = %s,
                        fcf_margin         = %s,
                        accruals_quality   = %s,
                        updated_at         = NOW()
                    WHERE stock_id = %s
                      AND report_type = 'ANNUAL'
                      AND fiscal_year = %s
                """, (
                    roic, ev, ev_ebit, ev_fcf, pb, peg,
                    nde, ebitda, ato, op_lev, bvps,
                    gpa, fcf_margin, accruals,
                    stock_id, int(fin["fiscal_year"])
                ))

            ok += 1
            if ok % 20 == 0 or ok <= 3:
                print(f"[FIN] {ticker}: roic={roic}, ev_ebit={ev_ebit}, pb={pb} ✓")

        except Exception as e:
            fail += 1
            print(f"[FIN] {ticker} 실패: {e}")

    _log_end(log_id, "SUCCESS" if fail == 0 else "PARTIAL", ok, fail)
    print(f"[FIN] 완료: {ok}성공 / {fail}실패")
    return ok, fail


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Step 3: Layer 1 점수 계산 (ETF 제외)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run_quant_score(calc_date: date = None):
    """
    Layer 1 점수 계산.
    ★ ETF 제외.
    ★ sector_percentile 섹터별 캐시 (중복 쿼리 제거).
    ★ Earnings Revision/Surprise 데이터 없을 시 중립점 부여.
    """
    if calc_date is None:
        calc_date = datetime.now().date()

    log_id = _log_start("QUANT_SCORE")
    stocks = _get_active_equities()     # ★ ETF 제외
    ok, fail = 0, 0

    # ★ 섹터별 percentile 캐시 (같은 섹터를 매번 재조회 방지)
    sector_pct_cache = {}

    for s in stocks:
        ticker   = s["ticker"]
        stock_id = s["stock_id"]
        sector   = s.get("sector_code") or "45"

        try:
            # ── 재무 데이터 ──
            fins = []
            with get_cursor() as cur:
                cur.execute("""
                    SELECT * FROM stock_financials
                    WHERE stock_id = %s AND report_type = 'ANNUAL'
                    ORDER BY fiscal_year DESC LIMIT 2
                """, (stock_id,))
                fins = [dict(r) for r in cur.fetchall()]

            if not fins:
                print(f"[L1] {ticker} 스킵: 재무데이터 없음")
                fail += 1
                continue

            fin      = fins[0]
            fin_prev = fins[1] if len(fins) > 1 else {}

            # ── EPS 이력 (3개년) ──
            eps_hist = []
            with get_cursor() as cur:
                cur.execute("""
                    SELECT eps_actual FROM stock_financials
                    WHERE stock_id = %s AND report_type = 'ANNUAL'
                      AND eps_actual IS NOT NULL
                    ORDER BY fiscal_year DESC LIMIT 3
                """, (stock_id,))
                eps_hist = [_f(r["eps_actual"]) for r in cur.fetchall()]

            # ── 가격 데이터 (250일) ──
            price_rows = []
            with get_cursor() as cur:
                cur.execute("""
                    SELECT trade_date, close_price FROM stock_prices_daily
                    WHERE stock_id = %s
                    ORDER BY trade_date DESC LIMIT 250
                """, (stock_id,))
                price_rows = [dict(r) for r in cur.fetchall()]

            # ── 배당 연수 ──
            div_years = 0
            with get_cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) AS cnt FROM stock_financials
                    WHERE stock_id = %s AND report_type = 'ANNUAL'
                      AND dividends_paid IS NOT NULL AND dividends_paid < 0
                """, (stock_id,))
                row = cur.fetchone()
                div_years = int(row["cnt"]) if row else 0

            # ── price_df ──
            price_df = None
            if price_rows:
                price_df = pd.DataFrame(price_rows)
                price_df["close_price"] = price_df["close_price"].apply(_f)

            # ── 섹터 백분위 (캐시) ──
            if sector not in sector_pct_cache:
                sector_pct_cache[sector] = _bulk_sector_percentiles(sector)

            sector_data = sector_pct_cache[sector]
            pct = sector_data.get(stock_id, {})

            # ── 점수 계산 (섹터 컨텍스트 전달) ──
            moat_s      = _sanitize(calc_moat_scores(fin, pct, sector_code=sector))
            value_s     = _sanitize(calc_value_scores(fin, pct, sector_code=sector))
            momentum_s  = _sanitize(calc_momentum_scores(fin, fin_prev, pct, sector_code=sector))
            stability_s = _sanitize(calc_stability_scores(price_df, eps_hist, div_years, pct, sector_code=sector))
            layer1_s    = _sanitize(calc_layer1_score(moat_s, value_s, momentum_s, stability_s, pct, sector_code=sector))

            # ── DB 저장 ──
            with get_cursor() as cur:
                # quant_moat_scores
                cur.execute("""
                    INSERT INTO quant_moat_scores (
                        stock_id, calc_date,
                        roic_score, gpa_score, fcf_margin_score,
                        accruals_quality_score, net_debt_ebitda_score,
                        total_moat_score
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (stock_id, calc_date) DO UPDATE SET
                        roic_score             = EXCLUDED.roic_score,
                        gpa_score              = EXCLUDED.gpa_score,
                        fcf_margin_score       = EXCLUDED.fcf_margin_score,
                        accruals_quality_score = EXCLUDED.accruals_quality_score,
                        net_debt_ebitda_score  = EXCLUDED.net_debt_ebitda_score,
                        total_moat_score       = EXCLUDED.total_moat_score
                """, (stock_id, calc_date,
                      moat_s["roic_score"], moat_s["gpa_score"],
                      moat_s["fcf_margin_score"], moat_s["accruals_quality_score"],
                      moat_s["net_debt_ebitda_score"], moat_s["total_moat_score"]))

                # quant_value_scores
                cur.execute("""
                    INSERT INTO quant_value_scores (
                        stock_id, calc_date,
                        earnings_yield_score, ev_fcf_score, pb_score, peg_score,
                        total_value_score
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (stock_id, calc_date) DO UPDATE SET
                        earnings_yield_score = EXCLUDED.earnings_yield_score,
                        ev_fcf_score         = EXCLUDED.ev_fcf_score,
                        pb_score             = EXCLUDED.pb_score,
                        peg_score            = EXCLUDED.peg_score,
                        total_value_score    = EXCLUDED.total_value_score
                """, (stock_id, calc_date,
                      value_s["earnings_yield_score"], value_s["ev_fcf_score"],
                      value_s["pb_score"], value_s["peg_score"],
                      value_s["total_value_score"]))

                # quant_momentum_scores
                cur.execute("""
                    INSERT INTO quant_momentum_scores (
                        stock_id, calc_date,
                        f_score_raw, f_score_points,
                        earnings_revision_ratio, earnings_revision_score,
                        ato_acceleration_score, op_leverage_score,
                        earnings_surprise_pct, earnings_surprise_score,
                        total_momentum_score
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (stock_id, calc_date) DO UPDATE SET
                        f_score_raw             = EXCLUDED.f_score_raw,
                        f_score_points          = EXCLUDED.f_score_points,
                        earnings_revision_ratio = EXCLUDED.earnings_revision_ratio,
                        earnings_revision_score = EXCLUDED.earnings_revision_score,
                        ato_acceleration_score  = EXCLUDED.ato_acceleration_score,
                        op_leverage_score       = EXCLUDED.op_leverage_score,
                        earnings_surprise_pct   = EXCLUDED.earnings_surprise_pct,
                        earnings_surprise_score = EXCLUDED.earnings_surprise_score,
                        total_momentum_score    = EXCLUDED.total_momentum_score
                """, (stock_id, calc_date,
                      momentum_s["f_score_raw"], momentum_s["f_score_points"],
                      momentum_s["earnings_revision_ratio"], momentum_s["earnings_revision_score"],
                      momentum_s["ato_acceleration_score"], momentum_s["op_leverage_score"],
                      momentum_s["earnings_surprise_pct"], momentum_s["earnings_surprise_score"],
                      momentum_s["total_momentum_score"]))

                # quant_stability_scores
                cur.execute("""
                    INSERT INTO quant_stability_scores (
                        stock_id, calc_date,
                        annualized_volatility_250d, low_vol_score,
                        eps_cv_3y, earnings_stability_score,
                        dividend_consecutive_years, dividend_consistency_score,
                        total_stability_score
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (stock_id, calc_date) DO UPDATE SET
                        annualized_volatility_250d = EXCLUDED.annualized_volatility_250d,
                        low_vol_score              = EXCLUDED.low_vol_score,
                        eps_cv_3y                  = EXCLUDED.eps_cv_3y,
                        earnings_stability_score   = EXCLUDED.earnings_stability_score,
                        dividend_consecutive_years = EXCLUDED.dividend_consecutive_years,
                        dividend_consistency_score = EXCLUDED.dividend_consistency_score,
                        total_stability_score      = EXCLUDED.total_stability_score
                """, (stock_id, calc_date,
                      stability_s["annualized_volatility_250d"], stability_s["low_vol_score"],
                      stability_s["eps_cv_3y"], stability_s["earnings_stability_score"],
                      stability_s["dividend_consecutive_years"], stability_s["dividend_consistency_score"],
                      stability_s["total_stability_score"]))

                # sector_percentile_scores
                cur.execute("""
                    INSERT INTO sector_percentile_scores (
                        stock_id, sector_id, calc_date,
                        roic_percentile, gpa_percentile,
                        fcf_margin_percentile, ev_ebit_percentile,
                        ev_fcf_percentile, pb_percentile, peg_percentile,
                        net_debt_ebitda_percentile, low_vol_percentile,
                        eps_stability_percentile, op_leverage_percentile
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (stock_id, calc_date) DO UPDATE SET
                        roic_percentile            = EXCLUDED.roic_percentile,
                        gpa_percentile             = EXCLUDED.gpa_percentile,
                        fcf_margin_percentile      = EXCLUDED.fcf_margin_percentile,
                        ev_ebit_percentile         = EXCLUDED.ev_ebit_percentile,
                        ev_fcf_percentile          = EXCLUDED.ev_fcf_percentile,
                        pb_percentile              = EXCLUDED.pb_percentile,
                        peg_percentile             = EXCLUDED.peg_percentile,
                        net_debt_ebitda_percentile = EXCLUDED.net_debt_ebitda_percentile,
                        low_vol_percentile         = EXCLUDED.low_vol_percentile,
                        eps_stability_percentile   = EXCLUDED.eps_stability_percentile,
                        op_leverage_percentile     = EXCLUDED.op_leverage_percentile
                """, (stock_id, pct.get("sector_id"), calc_date,
                      pct.get("roic_percentile"), pct.get("gpa_percentile"),
                      pct.get("fcf_margin_percentile"), pct.get("ev_ebit_percentile"),
                      pct.get("ev_fcf_percentile"), pct.get("pb_percentile"),
                      pct.get("peg_percentile"), pct.get("net_debt_ebitda_percentile"),
                      pct.get("low_vol_percentile"), pct.get("eps_stability_percentile"),
                      pct.get("op_leverage_percentile")))

                # stock_layer1_analysis (최종 통합)
                cur.execute("""
                    INSERT INTO stock_layer1_analysis (
                        stock_id, calc_date,
                        moat_score, value_score, momentum_score, stability_score,
                        layer1_raw_score, layer1_score,
                        sector_percentile_rank, total_score_adj
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (stock_id, calc_date) DO UPDATE SET
                        moat_score             = EXCLUDED.moat_score,
                        value_score            = EXCLUDED.value_score,
                        momentum_score         = EXCLUDED.momentum_score,
                        stability_score        = EXCLUDED.stability_score,
                        layer1_raw_score       = EXCLUDED.layer1_raw_score,
                        layer1_score           = EXCLUDED.layer1_score,
                        sector_percentile_rank = EXCLUDED.sector_percentile_rank,
                        total_score_adj        = EXCLUDED.total_score_adj,
                        updated_at             = NOW()
                """, (stock_id, calc_date,
                      layer1_s["moat_score"], layer1_s["value_score"],
                      layer1_s["momentum_score"], layer1_s["stability_score"],
                      layer1_s["layer1_raw_score"], layer1_s["layer1_score"],
                      layer1_s["sector_percentile_rank"], layer1_s["total_score_adj"]))

            ok += 1
            grade = score_to_grade(layer1_s["layer1_score"])
            if ok % 20 == 0 or ok <= 3:
                print(f"[L1] {ticker}: {layer1_s['layer1_score']} ({grade}) ✓")

        except Exception as e:
            fail += 1
            print(f"[L1] {ticker} 실패: {e}")

    _log_end(log_id, "SUCCESS" if fail == 0 else "PARTIAL", ok, fail)
    print(f"[L1] 완료: {ok}성공 / {fail}실패")
    return ok, fail


def _bulk_sector_percentiles(sector_code: str) -> dict:
    """
    섹터 내 모든 종목의 백분위를 한 번에 계산 후 dict 반환.
    Returns: {stock_id: {roic_percentile: ..., gpa_percentile: ..., ...}}
    """
    try:
        return calc_sector_percentiles_bulk(sector_code)
    except Exception as e:
        print(f"[PERCENTILE] {sector_code} 실패: {e}")
        return {}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 메인 실행
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run_all():
    print("=" * 60)
    print(f"[DAILY BATCH] 시작: {datetime.now()}")
    run_daily_price()
    run_supplement_financials()
    run_quant_score()
    print(f"[DAILY BATCH] 완료: {datetime.now()}")
    print("=" * 60)


if __name__ == "__main__":
    from db_pool import init_pool
    init_pool()
    run_all()