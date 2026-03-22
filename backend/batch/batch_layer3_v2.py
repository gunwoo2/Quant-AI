"""
batch/batch_layer3_v2.py — Layer 3 기술지표 배치 v3.2 (MACD+OBV Full)
======================================================================
v3.1 → v3.2:
  - MACD 계산 추가 (_calc_macd: EMA12, EMA26, Signal9)
  - OBV 강화: obv_ma20 추가, price_trend 반환
  - Bollinger Band 계산 추가 (_calc_bollinger)
  - 구조적 시그널: golden_cross_score, bb_squeeze_score, ma20_streak, breakout_52w
  - section_a_technical 합산 저장
  - DB 컬럼: macd_line, macd_signal, macd_histogram, macd_score,
             obv_ma20, bb_upper, bb_lower, bb_width, bb_squeeze,
             golden_cross_score, bb_squeeze_score, ma20_streak_days, ma20_streak_score,
             breakout_52w, breakout_52w_score, structural_signal_score,
             section_a_technical
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
    """RSI 계산 (Wilder's Smoothing)"""
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


def _calc_macd(close: pd.Series, fast=12, slow=26, signal=9) -> dict:
    """
    MACD 계산 (순수 가격 데이터만 필요, 유료 API 불필요)
    
    Returns:
        dict with macd_line, macd_signal, macd_histogram, prev_histogram
    """
    try:
        if len(close) < slow + signal:
            return {"macd_line": None, "macd_signal": None,
                    "macd_histogram": None, "prev_histogram": None}
        
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        
        return {
            "macd_line": round(float(macd_line.iloc[-1]), 4) if not pd.isna(macd_line.iloc[-1]) else None,
            "macd_signal": round(float(signal_line.iloc[-1]), 4) if not pd.isna(signal_line.iloc[-1]) else None,
            "macd_histogram": round(float(histogram.iloc[-1]), 4) if not pd.isna(histogram.iloc[-1]) else None,
            "prev_histogram": round(float(histogram.iloc[-2]), 4) if len(histogram) >= 2 and not pd.isna(histogram.iloc[-2]) else None,
        }
    except Exception:
        return {"macd_line": None, "macd_signal": None,
                "macd_histogram": None, "prev_histogram": None}


def _calc_obv(close: pd.Series, volume: pd.Series) -> dict:
    """
    OBV 계산 (enhanced: MA20 추가, price_trend 반환)
    """
    try:
        obv = (np.sign(close.diff()) * volume).fillna(0).cumsum()
        obv_current = int(obv.iloc[-1]) if len(obv) > 0 else 0
        
        # OBV MA20
        obv_ma20 = None
        if len(obv) >= 20:
            obv_ma20 = int(obv.rolling(20).mean().iloc[-1])
        
        # OBV trend (20일 기준)
        if len(obv) < 20:
            return {"obv_current": obv_current, "obv_ma20": obv_ma20,
                    "obv_trend": "FLAT", "price_trend": "FLAT"}
        
        obv_slope = float(obv.iloc[-1]) - float(obv.iloc[-20])
        obv_trend = "UP" if obv_slope > 0 else ("DOWN" if obv_slope < 0 else "FLAT")
        
        # Price trend (20일, 2% threshold)
        price_slope = float(close.iloc[-1]) - float(close.iloc[-20])
        threshold = float(close.iloc[-20]) * 0.02
        if price_slope > threshold:
            price_trend = "UP"
        elif price_slope < -threshold:
            price_trend = "DOWN"
        else:
            price_trend = "FLAT"
        
        return {
            "obv_current": obv_current,
            "obv_ma20": obv_ma20,
            "obv_trend": obv_trend,
            "price_trend": price_trend,
        }
    except Exception:
        return {"obv_current": 0, "obv_ma20": None,
                "obv_trend": "FLAT", "price_trend": "FLAT"}


def _calc_bollinger(close: pd.Series, period=20, num_std=2) -> dict:
    """볼린저 밴드 계산"""
    try:
        if len(close) < period:
            return {"bb_upper": None, "bb_lower": None, "bb_width": None, "bb_squeeze": None}
        
        sma = close.rolling(period).mean()
        std = close.rolling(period).std()
        upper = sma + num_std * std
        lower = sma - num_std * std
        
        bb_upper = round(float(upper.iloc[-1]), 4) if not pd.isna(upper.iloc[-1]) else None
        bb_lower = round(float(lower.iloc[-1]), 4) if not pd.isna(lower.iloc[-1]) else None
        
        # Width = (upper - lower) / middle
        mid = float(sma.iloc[-1]) if not pd.isna(sma.iloc[-1]) else None
        bb_width = None
        bb_squeeze = None
        if bb_upper and bb_lower and mid and mid > 0:
            bb_width = round((bb_upper - bb_lower) / mid, 4)
            # Squeeze: 현재 width가 최근 120일 중 하위 20%이면 스퀴즈
            width_series = (upper - lower) / sma
            width_series = width_series.dropna()
            if len(width_series) >= 20:
                pct_rank = (width_series.rank(pct=True)).iloc[-1]
                bb_squeeze = bool(pct_rank < 0.20)
        
        return {"bb_upper": bb_upper, "bb_lower": bb_lower,
                "bb_width": bb_width, "bb_squeeze": bb_squeeze}
    except Exception:
        return {"bb_upper": None, "bb_lower": None, "bb_width": None, "bb_squeeze": None}


def _calc_ma20_streak(close: pd.Series) -> int:
    """MA20 위/아래 연속 일수 (양수=위, 음수=아래)"""
    try:
        if len(close) < 20:
            return 0
        ma20 = close.rolling(20).mean()
        above = close > ma20
        
        streak = 0
        current_side = above.iloc[-1]
        for i in range(len(above) - 1, -1, -1):
            if pd.isna(above.iloc[i]):
                break
            if above.iloc[i] == current_side:
                streak += 1
            else:
                break
        
        return streak if current_side else -streak
    except Exception:
        return 0


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
# DB INSERT — 컬럼 자동 감지
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_COL_CHECK_DONE = False
_HAS_MACD_COLS = False
_HAS_REVERSAL_COL = False

def _check_columns():
    """technical_indicators 테이블의 컬럼 존재 여부 확인"""
    global _COL_CHECK_DONE, _HAS_MACD_COLS, _HAS_REVERSAL_COL
    if _COL_CHECK_DONE:
        return
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'technical_indicators'
            """)
            cols = {r["column_name"] for r in cur.fetchall()}
        _HAS_MACD_COLS = "macd_line" in cols
        _HAS_REVERSAL_COL = "reversal_1m_pct" in cols
        _COL_CHECK_DONE = True
        print(f"[TECH] Columns: macd={_HAS_MACD_COLS}, reversal={_HAS_REVERSAL_COL}")
    except Exception as e:
        print(f"[TECH] Column check failed: {e}")
        _COL_CHECK_DONE = True


def _ensure_columns():
    """누락된 컬럼 자동 추가 (ALTER TABLE)"""
    _check_columns()
    
    new_cols = {
        "macd_line": "NUMERIC",
        "macd_signal": "NUMERIC",
        "macd_histogram": "NUMERIC",
        "macd_score": "NUMERIC DEFAULT 0",
        "obv_ma20": "BIGINT",
        "bb_upper": "NUMERIC",
        "bb_lower": "NUMERIC",
        "bb_width": "NUMERIC",
        "bb_squeeze": "BOOLEAN",
        "golden_cross_score": "NUMERIC DEFAULT 0",
        "bb_squeeze_score": "NUMERIC DEFAULT 0",
        "ma20_streak_days": "INTEGER DEFAULT 0",
        "ma20_streak_score": "NUMERIC DEFAULT 0",
        "breakout_52w": "BOOLEAN DEFAULT FALSE",
        "breakout_52w_score": "NUMERIC DEFAULT 0",
        "structural_signal_score": "NUMERIC DEFAULT 0",
        "section_a_technical": "NUMERIC DEFAULT 0",
        "section_b_flow": "NUMERIC DEFAULT 0",
        "section_c_macro": "NUMERIC DEFAULT 0",
    }
    
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'technical_indicators'
            """)
            existing = {r["column_name"] for r in cur.fetchall()}
        
        added = []
        for col, dtype in new_cols.items():
            if col not in existing:
                try:
                    with get_cursor() as cur:
                        cur.execute(f"ALTER TABLE technical_indicators ADD COLUMN {col} {dtype}")
                    added.append(col)
                except Exception:
                    pass  # 이미 존재하거나 권한 문제
        
        if added:
            print(f"[TECH] Added columns: {added}")
        
        # 전역 상태 업데이트
        global _HAS_MACD_COLS
        _HAS_MACD_COLS = True
        
    except Exception as e:
        print(f"[TECH] Column ensure failed: {e}")


def _do_insert(data: dict):
    """통합 INSERT (모든 컬럼). 없는 컬럼은 자동 스킵."""
    
    # Full INSERT (MACD + BB + Structural 포함)
    SQL_FULL = """
        INSERT INTO technical_indicators (
            stock_id, calc_date,
            relative_momentum_12_1, relative_momentum_score,
            high_52w, high_52w_position_ratio, high_52w_score,
            trend_r2_90d, trend_slope_90d, trend_stability_score,
            rsi_14, rsi_score,
            macd_line, macd_signal, macd_histogram, macd_score,
            obv_current, obv_ma20, obv_trend, obv_score,
            volume_20d_avg, volume_surge_ratio, volume_surge_score,
            golden_cross, death_cross, ma_50, ma_200, vwap,
            bb_upper, bb_lower, bb_width, bb_squeeze,
            golden_cross_score, bb_squeeze_score,
            ma20_streak_days, ma20_streak_score,
            breakout_52w, breakout_52w_score,
            structural_signal_score,
            section_a_technical,
            layer3_technical_score
        ) VALUES (
            %(stock_id)s, %(calc_date)s,
            %(rel_mom_pct)s, %(rel_mom_score)s,
            %(high52)s, %(dist52)s, %(high52_score)s,
            %(trend_r2)s, %(trend_slope)s, %(trend_score)s,
            %(rsi14)s, %(rsi_score)s,
            %(macd_line)s, %(macd_signal)s, %(macd_histogram)s, %(macd_score)s,
            %(obv_current)s, %(obv_ma20)s, %(obv_trend)s, %(obv_score)s,
            %(vol_20d_avg)s, %(vol_surge_ratio)s, %(vol_score)s,
            %(golden)s, %(death)s, %(ma50)s, %(ma200)s, %(vwap)s,
            %(bb_upper)s, %(bb_lower)s, %(bb_width)s, %(bb_squeeze)s,
            %(gc_score)s, %(bbs_score)s,
            %(ma20_streak)s, %(ma20_streak_score)s,
            %(breakout_52w)s, %(breakout_52w_score)s,
            %(structural_score)s,
            %(section_a)s,
            %(l3_score)s
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
            macd_line               = EXCLUDED.macd_line,
            macd_signal             = EXCLUDED.macd_signal,
            macd_histogram          = EXCLUDED.macd_histogram,
            macd_score              = EXCLUDED.macd_score,
            obv_current             = EXCLUDED.obv_current,
            obv_ma20                = EXCLUDED.obv_ma20,
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
            bb_upper                = EXCLUDED.bb_upper,
            bb_lower                = EXCLUDED.bb_lower,
            bb_width                = EXCLUDED.bb_width,
            bb_squeeze              = EXCLUDED.bb_squeeze,
            golden_cross_score      = EXCLUDED.golden_cross_score,
            bb_squeeze_score        = EXCLUDED.bb_squeeze_score,
            ma20_streak_days        = EXCLUDED.ma20_streak_days,
            ma20_streak_score       = EXCLUDED.ma20_streak_score,
            breakout_52w            = EXCLUDED.breakout_52w,
            breakout_52w_score      = EXCLUDED.breakout_52w_score,
            structural_signal_score = EXCLUDED.structural_signal_score,
            section_a_technical     = EXCLUDED.section_a_technical,
            layer3_technical_score  = EXCLUDED.layer3_technical_score,
            layer3_total_score      = EXCLUDED.layer3_technical_score
    """
    
    # Fallback (MACD/BB 컬럼 없을 때)
    SQL_BASIC = """
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
            %(stock_id)s, %(calc_date)s,
            %(rel_mom_pct)s, %(rel_mom_score)s,
            %(high52)s, %(dist52)s, %(high52_score)s,
            %(trend_r2)s, %(trend_slope)s, %(trend_score)s,
            %(rsi14)s, %(rsi_score)s,
            %(obv_current)s, %(obv_trend)s, %(obv_score)s,
            %(vol_20d_avg)s, %(vol_surge_ratio)s, %(vol_score)s,
            %(golden)s, %(death)s, %(ma50)s, %(ma200)s, %(vwap)s,
            %(l3_score)s
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
    
    params = {k: _safe(v) for k, v in data.items()}
    
    try:
        with get_cursor() as cur:
            cur.execute(SQL_FULL, params)
    except Exception as e:
        err_str = str(e).lower()
        if "column" in err_str and ("does not exist" in err_str or "not exist" in err_str):
            # 컬럼 없으면 fallback
            with get_cursor() as cur:
                cur.execute(SQL_BASIC, params)
        else:
            raise


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 메인 실행
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run_technical_indicators(calc_date: date = None):
    if calc_date is None:
        calc_date = datetime.now().date()

    # 컬럼 자동 추가
    _ensure_columns()

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

    print(f"[TECH] Target: {len(stocks)} stocks, calc_date={calc_date}")

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

            # ── MA ──
            ma50  = round(float(close.rolling(50).mean().iloc[-1]), 4) if len(close) >= 50 else None
            ma200 = round(float(close.rolling(200).mean().iloc[-1]), 4) if len(close) >= 200 else None
            golden = bool(ma50 > ma200) if (ma50 and ma200) else None
            death  = bool(ma50 < ma200) if (ma50 and ma200) else None

            # ── RSI ──
            rsi14 = _calc_rsi(close, 14)

            # ── MACD (NEW!) ──
            macd = _calc_macd(close)

            # ── OBV (enhanced) ──
            obv = _calc_obv(close, volume)

            # ── Bollinger Bands (NEW!) ──
            bb = _calc_bollinger(close)

            # ── MA20 Streak (NEW!) ──
            ma20_streak = _calc_ma20_streak(close)

            # ── 52W High ──
            n52 = min(252, len(high))
            high52 = round(float(high.tail(n52).max()), 4)
            dist52 = round(cur_c / high52, 4) if high52 and high52 != 0 else None
            
            # 52W 돌파 (오늘 최고가가 252일 최고가와 같으면)
            breakout_52w = False
            if len(high) >= 252:
                prev_high = float(high.iloc[-252:-1].max())
                today_high = float(high.iloc[-1])
                breakout_52w = today_high >= prev_high

            # ── Relative Momentum 12-1 ──
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

            # ── Trend R²/Slope ──
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

            # ── Volume Surge ──
            vol_20d_avg = None
            vol_surge_ratio = None
            if len(volume) >= 20:
                avg20 = float(volume.tail(20).mean())
                cur_vol = float(volume.iloc[-1])
                if avg20 > 0:
                    vol_20d_avg = int(avg20)
                    vol_surge_ratio = round(cur_vol / avg20, 2)

            # ── VWAP ──
            vwap = None
            if len(df) >= 1:
                last = df.iloc[-1]
                h = _f(last["high_price"])
                l = _f(last["low_price"])
                c_val = _f(last["close_price"])
                if all(x is not None for x in [h, l, c_val]):
                    vwap = round((h + l + c_val) / 3, 4)

            # ══════════════════════════════════════════════
            # 스코어링 (calc_layer3_score v3.3)
            # ══════════════════════════════════════════════
            result = calc_layer3_score(
                rel_mom_pct=_f(rel_mom_pct),
                dist52=_f(dist52),
                ret_1m_pct=_f(ret_1m_pct),
                rsi14=_f(rsi14),
                surge_ratio=_f(vol_surge_ratio),
                trend_r2=_f(trend_r2),
                trend_slope=_f(trend_slope),
                cur_price=cur_c,
                obv_trend=obv["obv_trend"],
                price_trend=obv["price_trend"],
                obv_current=obv["obv_current"],
                obv_ma20=obv["obv_ma20"],
                macd_line=macd["macd_line"],
                macd_signal=macd["macd_signal"],
                macd_histogram=macd["macd_histogram"],
                prev_histogram=macd["prev_histogram"],
                golden_cross=golden,
                death_cross=death,
                bb_squeeze=bb["bb_squeeze"],
                ma20_streak_days=ma20_streak,
                breakout_52w=breakout_52w,
            )

            # Structural signal score (golden cross, bb squeeze 등)
            from utils.layer3_scoring import score_structural_signal
            struct_score = score_structural_signal(
                golden_cross=golden,
                death_cross=death,
                bb_squeeze=bb["bb_squeeze"],
                ma20_streak_days=ma20_streak,
                breakout_52w=breakout_52w,
            )

            # ── DB 저장 ──
            _do_insert({
                "stock_id": stock_id,
                "calc_date": calc_date,
                "rel_mom_pct": rel_mom_pct,
                "rel_mom_score": result["relative_momentum_score"],
                "high52": high52,
                "dist52": dist52,
                "high52_score": result["high_52w_score"],
                "trend_r2": trend_r2,
                "trend_slope": trend_slope,
                "trend_score": result["trend_stability_score"],
                "rsi14": rsi14,
                "rsi_score": result["rsi_score"],
                "macd_line": macd["macd_line"],
                "macd_signal": macd["macd_signal"],
                "macd_histogram": macd["macd_histogram"],
                "macd_score": result["macd_score"],
                "obv_current": obv["obv_current"],
                "obv_ma20": obv["obv_ma20"],
                "obv_trend": obv["obv_trend"],
                "obv_score": result["obv_score"],
                "vol_20d_avg": vol_20d_avg,
                "vol_surge_ratio": vol_surge_ratio,
                "vol_score": result["volume_surge_score"],
                "golden": golden,
                "death": death,
                "ma50": ma50,
                "ma200": ma200,
                "vwap": vwap,
                "bb_upper": bb["bb_upper"],
                "bb_lower": bb["bb_lower"],
                "bb_width": bb["bb_width"],
                "bb_squeeze": bb["bb_squeeze"],
                "gc_score": 0.0,   # golden_cross는 structural에 포함
                "bbs_score": 0.0,  # bb_squeeze도 structural에 포함
                "ma20_streak": ma20_streak,
                "ma20_streak_score": 0.0,
                "breakout_52w": breakout_52w,
                "breakout_52w_score": 0.0,
                "structural_score": struct_score,
                "section_a": result["section_a_technical"],
                "l3_score": result["layer3_technical_score"],
            })

            ok += 1
            macd_str = f"{macd['macd_histogram']:.2f}" if macd['macd_histogram'] else "N/A"
            obv_str = obv["obv_trend"]
            vol_str = f"{vol_surge_ratio:.2f}" if vol_surge_ratio is not None else "N/A"
            print(f"[TECH] {ticker}: L3={result['layer3_technical_score']:.1f} "
                  f"SecA={result['section_a_technical']:.1f}/55 "
                  f"(Mom={result['relative_momentum_score']:.1f} "
                  f"52W={result['high_52w_score']:.1f} "
                  f"Tr={result['trend_stability_score']:.1f} "
                  f"RSI={result['rsi_score']:.1f} "
                  f"MACD={result['macd_score']:.1f}[h={macd_str}] "
                  f"OBV={result['obv_score']:.1f}[{obv_str}] "
                  f"Vol={result['volume_surge_score']:.1f}[x{vol_str}]) ✓")

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
