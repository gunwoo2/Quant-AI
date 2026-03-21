"""
batch/batch_layer3_v2.py — Layer 3 기술지표 배치 v3.1 (Full)
=============================================================
기능:
  - 모든 활성 종목에 대해 기술 지표 계산 + 스코어링 + DB 저장
  - _safe(): np.float64→float 강제 변환 (SQL 리터럴 방지)
  - reversal 컬럼 자동 감지 (있으면 포함, 없으면 폴백)
  - layer3_total_score = layer3_technical_score 동기화
  - run_all = run_technical_indicators (하위호환 alias)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import patch_numpy_adapter
except ImportError:
    pass

import pandas as pd
import numpy as np
from datetime import datetime, date
from db_pool import get_cursor
from utils.layer3_scoring import calc_layer3_score


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 헬퍼
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _f(v):
    if v is None:
        return None
    try:
        return float(v)
    except Exception:
        return None


def _safe(v):
    """DB INSERT 파라미터를 Python 네이티브로 강제 변환"""
    if v is None:
        return None
    if isinstance(v, (np.floating, np.complexfloating)):
        return float(v)
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.bool_):
        return bool(v)
    if isinstance(v, (int, float, str, bool)):
        return v
    try:
        return float(v)
    except (TypeError, ValueError):
        try:
            return str(v)
        except Exception:
            return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 지표 계산 함수
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _calc_rsi(close: pd.Series, period: int = 14) -> float:
    try:
        delta = close.diff()
        gain  = delta.clip(lower=0).rolling(period).mean()
        loss  = (-delta.clip(upper=0)).rolling(period).mean()
        rs    = gain / loss.replace(0, np.nan)
        rsi   = 100 - (100 / (1 + rs))
        val   = rsi.iloc[-1]
        return float(val) if not pd.isna(val) else None
    except Exception:
        return None


def _calc_obv(close: pd.Series, volume: pd.Series) -> tuple:
    try:
        obv = (np.sign(close.diff()) * volume).fillna(0).cumsum()
        obv_current = int(obv.iloc[-1]) if len(obv) > 0 else 0
        if len(obv) < 20:
            return obv_current, "FLAT", "FLAT"
        obv_slope = float(obv.iloc[-1]) - float(obv.iloc[-20])
        obv_trend = "UP" if obv_slope > 0 else ("DOWN" if obv_slope < 0 else "FLAT")
        price_slope = float(close.iloc[-1]) - float(close.iloc[-20])
        threshold = float(close.iloc[-20]) * 0.02
        if price_slope > threshold:
            price_trend = "UP"
        elif price_slope < -threshold:
            price_trend = "DOWN"
        else:
            price_trend = "FLAT"
        return obv_current, obv_trend, price_trend
    except Exception:
        return 0, "FLAT", "FLAT"


def _get_spy_returns(calc_date: date) -> tuple:
    try:
        with get_cursor() as cur:
            cur.execute("SELECT stock_id FROM stocks WHERE ticker = 'SPY' LIMIT 1")
            row = cur.fetchone()
            if not row:
                return None, None
            spy_id = row["stock_id"]
            cur.execute("""
                SELECT trade_date, close_price
                FROM stock_prices_daily
                WHERE stock_id = %s ORDER BY trade_date DESC LIMIT 260
            """, (spy_id,))
            rows = [dict(r) for r in cur.fetchall()]
        if not rows or len(rows) < 22:
            return None, None
        rows.sort(key=lambda x: x["trade_date"])
        closes = [float(r["close_price"]) for r in rows]
        spy_now = closes[-1]
        spy_1m  = closes[-22] if len(closes) >= 22 else spy_now
        spy_12m = closes[0]
        ret_12m = (spy_now - spy_12m) / spy_12m if spy_12m != 0 else 0
        ret_1m  = (spy_now - spy_1m)  / spy_1m  if spy_1m  != 0 else 0
        return ret_12m, ret_1m
    except Exception:
        return None, None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DB INSERT — reversal 컬럼 자동 감지
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_HAS_REVERSAL_COL = None  # None=미확인, True/False=캐시

SQL_WITH_REV = """
    INSERT INTO technical_indicators (
        stock_id, calc_date,
        relative_momentum_12_1, relative_momentum_score,
        high_52w, high_52w_position_ratio, high_52w_score,
        trend_r2_90d, trend_slope_90d, trend_stability_score,
        rsi_14, rsi_score,
        obv_current, obv_trend, obv_score,
        volume_20d_avg, volume_surge_ratio, volume_surge_score,
        golden_cross, death_cross, ma_50, ma_200, vwap,
        reversal_1m_pct, reversal_score,
        layer3_technical_score
    ) VALUES (
        %s,%s, %s,%s, %s,%s,%s, %s,%s,%s, %s,%s, %s,%s,%s,
        %s,%s,%s, %s,%s,%s,%s,%s, %s,%s, %s
    )
    ON CONFLICT (stock_id, calc_date) DO UPDATE SET
        relative_momentum_12_1  = EXCLUDED.relative_momentum_12_1,
        relative_momentum_score = EXCLUDED.relative_momentum_score,
        high_52w                = EXCLUDED.high_52w,
        high_52w_position_ratio = EXCLUDED.high_52w_position_ratio,
        high_52w_score          = EXCLUDED.high_52w_score,
        trend_r2_90d            = EXCLUDED.trend_r2_90d,
        trend_slope_90d         = EXCLUDED.trend_slope_90d,
        trend_stability_score   = EXCLUDED.trend_stability_score,
        rsi_14                  = EXCLUDED.rsi_14,
        rsi_score               = EXCLUDED.rsi_score,
        obv_current             = EXCLUDED.obv_current,
        obv_trend               = EXCLUDED.obv_trend,
        obv_score               = EXCLUDED.obv_score,
        volume_20d_avg          = EXCLUDED.volume_20d_avg,
        volume_surge_ratio      = EXCLUDED.volume_surge_ratio,
        volume_surge_score      = EXCLUDED.volume_surge_score,
        golden_cross            = EXCLUDED.golden_cross,
        death_cross             = EXCLUDED.death_cross,
        ma_50                   = EXCLUDED.ma_50,
        ma_200                  = EXCLUDED.ma_200,
        vwap                    = EXCLUDED.vwap,
        reversal_1m_pct         = EXCLUDED.reversal_1m_pct,
        reversal_score          = EXCLUDED.reversal_score,
        layer3_technical_score  = EXCLUDED.layer3_technical_score,
        layer3_total_score      = EXCLUDED.layer3_technical_score
"""

SQL_NO_REV = """
    INSERT INTO technical_indicators (
        stock_id, calc_date,
        relative_momentum_12_1, relative_momentum_score,
        high_52w, high_52w_position_ratio, high_52w_score,
        trend_r2_90d, trend_slope_90d, trend_stability_score,
        rsi_14, rsi_score,
        obv_current, obv_trend, obv_score,
        volume_20d_avg, volume_surge_ratio, volume_surge_score,
        golden_cross, death_cross, ma_50, ma_200, vwap,
        layer3_technical_score
    ) VALUES (
        %s,%s, %s,%s, %s,%s,%s, %s,%s,%s, %s,%s, %s,%s,%s,
        %s,%s,%s, %s,%s,%s,%s,%s, %s
    )
    ON CONFLICT (stock_id, calc_date) DO UPDATE SET
        relative_momentum_12_1  = EXCLUDED.relative_momentum_12_1,
        relative_momentum_score = EXCLUDED.relative_momentum_score,
        high_52w                = EXCLUDED.high_52w,
        high_52w_position_ratio = EXCLUDED.high_52w_position_ratio,
        high_52w_score          = EXCLUDED.high_52w_score,
        trend_r2_90d            = EXCLUDED.trend_r2_90d,
        trend_slope_90d         = EXCLUDED.trend_slope_90d,
        trend_stability_score   = EXCLUDED.trend_stability_score,
        rsi_14                  = EXCLUDED.rsi_14,
        rsi_score               = EXCLUDED.rsi_score,
        obv_current             = EXCLUDED.obv_current,
        obv_trend               = EXCLUDED.obv_trend,
        obv_score               = EXCLUDED.obv_score,
        volume_20d_avg          = EXCLUDED.volume_20d_avg,
        volume_surge_ratio      = EXCLUDED.volume_surge_ratio,
        volume_surge_score      = EXCLUDED.volume_surge_score,
        golden_cross            = EXCLUDED.golden_cross,
        death_cross             = EXCLUDED.death_cross,
        ma_50                   = EXCLUDED.ma_50,
        ma_200                  = EXCLUDED.ma_200,
        vwap                    = EXCLUDED.vwap,
        layer3_technical_score  = EXCLUDED.layer3_technical_score,
        layer3_total_score      = EXCLUDED.layer3_technical_score
"""


def _do_insert(stock_id, calc_date,
               rel_mom_pct, rel_mom_score,
               high52, dist52, high52_score,
               trend_r2, trend_slope,
               rsi14, rsi_score,
               obv_current, obv_trend,
               vol_20d_avg, vol_surge_ratio, vol_score,
               golden, death, ma50, ma200, vwap,
               ret_1m_pct, reversal_score,
               l3_score):
    """모든 값을 _safe()로 변환 후 INSERT. reversal 컬럼 자동 감지."""
    global _HAS_REVERSAL_COL

    base = (
        _safe(stock_id), _safe(calc_date),
        _safe(rel_mom_pct), _safe(rel_mom_score),
        _safe(high52), _safe(dist52), _safe(high52_score),
        _safe(trend_r2), _safe(trend_slope), _safe(0.0),
        _safe(rsi14), _safe(rsi_score),
        _safe(obv_current), _safe(obv_trend), _safe(0.0),
        _safe(vol_20d_avg), _safe(vol_surge_ratio), _safe(vol_score),
        _safe(golden), _safe(death), _safe(ma50), _safe(ma200), _safe(vwap),
        _safe(l3_score),
    )
    rev = base[:23] + (_safe(ret_1m_pct), _safe(reversal_score)) + base[23:]

    if _HAS_REVERSAL_COL is None:
        try:
            with get_cursor() as cur:
                cur.execute(SQL_WITH_REV, rev)
            _HAS_REVERSAL_COL = True
            return
        except Exception:
            _HAS_REVERSAL_COL = False
            with get_cursor() as cur:
                cur.execute(SQL_NO_REV, base)
            return

    if _HAS_REVERSAL_COL:
        with get_cursor() as cur:
            cur.execute(SQL_WITH_REV, rev)
    else:
        with get_cursor() as cur:
            cur.execute(SQL_NO_REV, base)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 메인 실행
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run_technical_indicators(calc_date: date = None):
    if calc_date is None:
        calc_date = datetime.now().date()

    stocks = []
    with get_cursor() as cur:
        cur.execute("""
            SELECT s.stock_id, s.ticker
            FROM stocks s WHERE s.is_active = TRUE
        """)
        stocks = [dict(r) for r in cur.fetchall()]

    spy_ret_12m, spy_ret_1m = _get_spy_returns(calc_date)

    if spy_ret_12m is not None:
        print(f"[SPY] 12M={spy_ret_12m*100:.1f}% 1M={spy_ret_1m*100:.1f}%")
    else:
        print("[SPY] 수익률 조회 실패")

    print(f"[TECH] Target: {len(stocks)} stocks")

    ok, fail = 0, 0

    for s in stocks:
        stock_id = s["stock_id"]
        ticker   = s["ticker"]

        try:
            # ── 가격 데이터 조회 ──
            with get_cursor() as cur:
                cur.execute("""
                    SELECT trade_date, open_price, high_price, low_price,
                           close_price, volume
                    FROM stock_prices_daily
                    WHERE stock_id = %s
                    ORDER BY trade_date DESC LIMIT 300
                """, (stock_id,))
                price_rows = [dict(r) for r in cur.fetchall()]

            if not price_rows or len(price_rows) < 30:
                print(f"[TECH] {ticker} skip: 가격 부족 ({len(price_rows)}행)")
                fail += 1
                continue

            df = pd.DataFrame(price_rows).sort_values("trade_date")
            close  = df["close_price"].apply(_f).astype(float)
            volume = df["volume"].apply(lambda x: float(x) if x else 0.0).astype(float)
            high   = df["high_price"].apply(_f).astype(float)
            cur_c  = float(close.iloc[-1])

            # MA
            ma50  = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None
            ma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None
            golden = bool(ma50 > ma200) if (ma50 and ma200) else None
            death  = bool(ma50 < ma200) if (ma50 and ma200) else None

            # RSI
            rsi14 = _calc_rsi(close, 14)

            # OBV
            obv_current, obv_trend, _ = _calc_obv(close, volume)

            # 52W High
            n52 = min(252, len(high))
            high52 = float(high.tail(n52).max())
            dist52 = round(cur_c / high52, 4) if high52 and high52 != 0 else None

            # Relative Momentum 12-1
            rel_mom_pct = None
            ret_1m_pct = None
            if len(close) >= 22:
                c_now = float(close.iloc[-1])
                c_1m  = float(close.iloc[-22])
                if c_1m != 0:
                    ret_1m_pct = round(((c_now - c_1m) / c_1m) * 100, 4)

            if len(close) >= 252:
                c_now = float(close.iloc[-1])
                c_12m = float(close.iloc[-252])
                c_1m  = float(close.iloc[-22]) if len(close) >= 22 else c_now
                if c_12m != 0 and c_1m != 0:
                    stock_12m = (c_now - c_12m) / c_12m
                    stock_1m  = (c_now - c_1m)  / c_1m
                    abs_mom = stock_12m - stock_1m
                    if spy_ret_12m is not None and spy_ret_1m is not None:
                        spy_mom = spy_ret_12m - spy_ret_1m
                        rel_mom_pct = round((abs_mom - spy_mom) * 100, 4)
                    else:
                        rel_mom_pct = round(abs_mom * 100, 4)

            # Trend R²/Slope
            trend_r2 = None
            trend_slope = None
            if len(close) >= 90:
                y = close.tail(90).values.astype(float)
                x = np.arange(len(y))
                try:
                    coeffs = np.polyfit(x, y, 1)
                    trend_slope = round(float(coeffs[0]), 6)
                    y_hat = np.polyval(coeffs, x)
                    ss_res = float(np.sum((y - y_hat) ** 2))
                    ss_tot = float(np.sum((y - y.mean()) ** 2))
                    trend_r2 = round(1 - ss_res / ss_tot, 4) if ss_tot != 0 else None
                except Exception:
                    pass

            # Volume Surge
            vol_20d_avg = None
            vol_surge_ratio = None
            if len(volume) >= 20:
                avg20 = float(volume.tail(20).mean())
                cur_vol = float(volume.iloc[-1])
                if avg20 > 0:
                    vol_20d_avg = int(avg20)
                    vol_surge_ratio = round(cur_vol / avg20, 2)

            # VWAP
            vwap = None
            if len(df) >= 1:
                last = df.iloc[-1]
                h = _f(last["high_price"])
                l = _f(last["low_price"])
                c_val = _f(last["close_price"])
                if all(x is not None for x in [h, l, c_val]):
                    vwap = round((h + l + c_val) / 3, 4)

            # ── 스코어링 ──
            result = calc_layer3_score(
                rel_mom_pct=_f(rel_mom_pct),
                dist52=_f(dist52),
                ret_1m_pct=_f(ret_1m_pct),
                rsi14=_f(rsi14),
                surge_ratio=_f(vol_surge_ratio),
            )

            rel_mom_score  = result["relative_momentum_score"]
            high52_score   = result["high_52w_score"]
            reversal_score = result["reversal_score"]
            rsi_score      = result["rsi_score"]
            vol_score      = result["volume_surge_score"]
            l3_score       = result["layer3_technical_score"]

            # ── DB 저장 ──
            _do_insert(
                stock_id, calc_date,
                rel_mom_pct, rel_mom_score,
                high52, dist52, high52_score,
                trend_r2, trend_slope,
                rsi14, rsi_score,
                obv_current, obv_trend,
                vol_20d_avg, vol_surge_ratio, vol_score,
                golden, death, ma50, ma200, vwap,
                ret_1m_pct, reversal_score,
                l3_score,
            )

            ok += 1
            vol_str = f"{vol_surge_ratio:.2f}" if vol_surge_ratio is not None else "N/A"
            print(f"[TECH] {ticker}: L3={l3_score} "
                  f"(Mom={rel_mom_score:.0f} 52W={high52_score:.0f} "
                  f"STR={reversal_score:.0f} RSI={rsi_score:.0f} "
                  f"Vol={vol_score:.0f}[x{vol_str}]) ✓")

        except Exception as e:
            fail += 1
            print(f"[TECH] {ticker} fail: {e}")

    print(f"[TECH] Done: {ok} ok / {fail} fail")
    return {"ok": ok, "fail": fail}


# ── 별칭 ──
run_all = run_technical_indicators


if __name__ == "__main__":
    from db_pool import init_pool
    init_pool()
    run_technical_indicators()