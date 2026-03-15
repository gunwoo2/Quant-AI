"""
매일 03:30 실행 (Phase 2).
FDR 기술지표 계산 → technical_indicators 저장.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from datetime import datetime, date
from db_pool import get_cursor


def _f(v):
    """np.float64, Decimal 등 모두 Python float으로 변환"""
    if v is None:
        return None
    try:
        return float(v)
    except Exception:
        return None


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


def _calc_obv_trend(close: pd.Series, volume: pd.Series) -> str:
    try:
        obv   = (np.sign(close.diff()) * volume).fillna(0).cumsum()
        if len(obv) < 10:
            return "FLAT"
        slope = float(obv.iloc[-1]) - float(obv.iloc[-10])
        if slope > 0:   return "UP"
        if slope < 0:   return "DOWN"
        return "FLAT"
    except Exception:
        return "FLAT"


def _calc_layer3_score(rsi14, golden_cross, obv_trend, dist52, trend_r2) -> float:
    """
    technical_indicators.layer3_technical_score 계산 (0~100).
    NOT NULL 컬럼이므로 반드시 값 반환.
    """
    score = 50.0  # 기본 중립

    # RSI (0~30점)
    if rsi14 is not None:
        if 40 <= rsi14 <= 60:   score += 10
        elif 30 <= rsi14 < 40:  score += 5
        elif 60 < rsi14 <= 70:  score += 5
        elif rsi14 < 30:        score -= 10   # 과매도 반등 가능성 소폭 가산
        elif rsi14 > 70:        score -= 5    # 과매수 위험

    # Golden/Death Cross (0~20점)
    if golden_cross is True:    score += 15
    elif golden_cross is False: score -= 10

    # OBV Trend (0~15점)
    if obv_trend == "UP":       score += 10
    elif obv_trend == "DOWN":   score -= 10

    # 52주 고점 대비 위치 (0~15점)
    if dist52 is not None:
        if dist52 >= 0.95:      score += 15
        elif dist52 >= 0.80:    score += 8
        elif dist52 < 0.60:     score -= 10

    # Trend R² (0~10점)
    if trend_r2 is not None:
        if trend_r2 >= 0.8:     score += 10
        elif trend_r2 >= 0.6:   score += 5

    return round(float(min(100.0, max(0.0, score))), 2)


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

    ok, fail = 0, 0

    for s in stocks:
        stock_id = s["stock_id"]
        ticker   = s["ticker"]

        try:
            price_rows = []
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
                print(f"[TECH] {ticker} 스킵: 가격데이터 부족 ({len(price_rows)}행)")
                fail += 1
                continue

            df = pd.DataFrame(price_rows).sort_values("trade_date")
            close  = df["close_price"].apply(_f).astype(float)
            volume = df["volume"].apply(lambda x: float(x) if x else 0.0).astype(float)
            high   = df["high_price"].apply(_f).astype(float)

            # MA 계산
            ma50  = None
            ma200 = None
            if len(close) >= 50:
                ma50  = float(close.rolling(50).mean().iloc[-1])
            if len(close) >= 200:
                ma200 = float(close.rolling(200).mean().iloc[-1])

            golden = bool(ma50 > ma200) if (ma50 and ma200) else None
            death  = bool(ma50 < ma200) if (ma50 and ma200) else None

            # RSI 14
            rsi14 = _calc_rsi(close, 14)

            # OBV Trend
            obv_trend = _calc_obv_trend(close, volume)

            # 52주 고점 대비
            n52 = min(252, len(high))
            high52  = float(high.tail(n52).max())
            cur_c   = float(close.iloc[-1])
            dist52  = round(cur_c / high52, 4) if high52 and high52 != 0 else None

            # 12-1 상대 모멘텀
            rel_mom = None
            if len(close) >= 252:
                c_now   = float(close.iloc[-1])
                c_12m   = float(close.iloc[-252])
                c_1m    = float(close.iloc[-21]) if len(close) >= 21 else c_now
                if c_12m != 0 and c_1m != 0:
                    ret_12m = (c_now - c_12m) / c_12m
                    ret_1m  = (c_now - c_1m)  / c_1m
                    rel_mom = round((ret_12m - ret_1m) * 100, 4)

            # Trend R² (90일 선형회귀)
            trend_r2 = None
            if len(close) >= 90:
                y = close.tail(90).values.astype(float)
                x = np.arange(len(y))
                try:
                    coeffs  = np.polyfit(x, y, 1)
                    y_hat   = np.polyval(coeffs, x)
                    ss_res  = float(np.sum((y - y_hat) ** 2))
                    ss_tot  = float(np.sum((y - y.mean()) ** 2))
                    trend_r2 = round(1 - ss_res / ss_tot, 4) if ss_tot != 0 else None
                except Exception:
                    pass

            # Layer3 종합 점수 (NOT NULL 컬럼)
            l3_score = _calc_layer3_score(rsi14, golden, obv_trend, dist52, trend_r2)

            with get_cursor() as cur:
                cur.execute("""
                    INSERT INTO technical_indicators (
                        stock_id, calc_date,
                        relative_momentum_12_1, high_52w_position_ratio,
                        trend_r2_90d, rsi_14, obv_trend,
                        golden_cross, death_cross, ma_50, ma_200,
                        layer3_technical_score
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (stock_id, calc_date) DO UPDATE SET
                        relative_momentum_12_1  = EXCLUDED.relative_momentum_12_1,
                        high_52w_position_ratio = EXCLUDED.high_52w_position_ratio,
                        trend_r2_90d            = EXCLUDED.trend_r2_90d,
                        rsi_14                  = EXCLUDED.rsi_14,
                        obv_trend               = EXCLUDED.obv_trend,
                        golden_cross            = EXCLUDED.golden_cross,
                        death_cross             = EXCLUDED.death_cross,
                        ma_50                   = EXCLUDED.ma_50,
                        ma_200                  = EXCLUDED.ma_200,
                        layer3_technical_score  = EXCLUDED.layer3_technical_score
                """, (
                    stock_id, calc_date,
                    _f(rel_mom),  _f(dist52),  _f(trend_r2),
                    _f(rsi14),    obv_trend,
                    golden,       death,
                    _f(ma50),     _f(ma200),
                    _f(l3_score),
                ))

            ok += 1
            rsi_str = f"{rsi14:.1f}" if rsi14 is not None else "N/A"
            print(f"[TECH] {ticker}: RSI={rsi_str} OBV={obv_trend} Golden={golden} L3={l3_score} ✓")

            
        except Exception as e:
            fail += 1
            print(f"[TECH] {ticker} 실패: {e}")

    print(f"[TECH] 완료: {ok}성공 / {fail}실패")


if __name__ == "__main__":
    from db_pool import init_pool
    init_pool()
    run_technical_indicators()