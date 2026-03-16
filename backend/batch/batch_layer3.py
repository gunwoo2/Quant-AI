"""
매일 03:30 실행 (Phase 2).
FDR 기술지표 계산 → technical_indicators 저장.
설계서 4.1 기준: 6개 지표 (Momentum 30 + 52W 20 + R² 15 + RSI 15 + OBV 10 + Volume 10) = 100점
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


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 개별 지표 계산 함수
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


def _calc_obv(close: pd.Series, volume: pd.Series) -> tuple:
    """OBV 계산 → (obv_current, obv_trend, price_trend)"""
    try:
        obv = (np.sign(close.diff()) * volume).fillna(0).cumsum()
        obv_current = int(obv.iloc[-1]) if len(obv) > 0 else 0

        if len(obv) < 20:
            return obv_current, "FLAT", "FLAT"

        # OBV 추세 (최근 20일 기준)
        obv_slope = float(obv.iloc[-1]) - float(obv.iloc[-20])
        if obv_slope > 0:    obv_trend = "UP"
        elif obv_slope < 0:  obv_trend = "DOWN"
        else:                obv_trend = "FLAT"

        # 가격 추세 (최근 20일 기준)
        price_slope = float(close.iloc[-1]) - float(close.iloc[-20])
        if price_slope > close.iloc[-20] * 0.02:     price_trend = "UP"
        elif price_slope < -close.iloc[-20] * 0.02:  price_trend = "DOWN"
        else:                                         price_trend = "FLAT"

        return obv_current, obv_trend, price_trend

    except Exception:
        return 0, "FLAT", "FLAT"


def _get_spy_returns(calc_date: date) -> tuple:
    """SPY의 12개월, 1개월 수익률 조회 (DB에서)"""
    try:
        with get_cursor() as cur:
            # stocks에서 SPY의 stock_id 찾기
            cur.execute(
                "SELECT stock_id FROM stocks WHERE ticker = 'SPY' LIMIT 1"
            )
            row = cur.fetchone()
            if not row:
                return None, None

            spy_id = row["stock_id"]
            cur.execute("""
                SELECT trade_date, close_price
                FROM stock_prices_daily
                WHERE stock_id = %s
                ORDER BY trade_date DESC LIMIT 260
            """, (spy_id,))
            rows = [dict(r) for r in cur.fetchall()]

        if not rows or len(rows) < 22:
            return None, None

        rows.sort(key=lambda x: x["trade_date"])
        closes = [float(r["close_price"]) for r in rows]

        spy_now = closes[-1]
        spy_1m  = closes[-22] if len(closes) >= 22 else spy_now
        spy_12m = closes[0] if len(closes) >= 252 else closes[0]

        ret_12m = (spy_now - spy_12m) / spy_12m if spy_12m != 0 else 0
        ret_1m  = (spy_now - spy_1m) / spy_1m if spy_1m != 0 else 0

        return ret_12m, ret_1m

    except Exception:
        return None, None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 설계서 4.1 기준 점수 체계 (0점 시작 → 가산 방식)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _score_relative_momentum(rel_mom_pct: float) -> float:
    """
    ① Relative Momentum 12-1 (30점 만점)
    설계서: vs SPY 상대수익률 기준 6단계
    """
    if rel_mom_pct is None:
        return 0.0
    if rel_mom_pct >= 30:   return 30.0   # 설계서 45pt는 오버슈트 보정 전 기준, 30pt 만점 적용
    if rel_mom_pct >= 20:   return 24.0
    if rel_mom_pct >= 10:   return 18.0
    if rel_mom_pct >= 0:    return 12.0
    if rel_mom_pct >= -10:  return 5.0
    return 0.0


def _score_52w_high(dist52: float) -> float:
    """
    ② 52W High Position (20점 만점)
    설계서: 현재가/52주최고가 비율 기준 5단계
    """
    if dist52 is None:
        return 0.0
    if dist52 >= 0.95:  return 20.0
    if dist52 >= 0.85:  return 15.0
    if dist52 >= 0.75:  return 10.0
    if dist52 >= 0.65:  return 5.0
    return 0.0


def _score_trend_r2(r2: float, slope: float) -> float:
    """
    ③ Trend Stability R² (15점 만점)
    설계서: R² + 기울기 방향 결합 평가
    """
    if r2 is None:
        return 0.0
    if r2 >= 0.7 and slope is not None and slope > 0:
        return 15.0    # R²≥0.7 + 기울기↑ = 기관 매집 패턴
    if r2 >= 0.5:
        return 10.0
    if r2 >= 0.3:
        return 5.0
    return 0.0


def _score_rsi(rsi14: float) -> float:
    """
    ④ RSI 14일 (15점 만점)
    설계서: 과매도 = 반등 가능성 (긍정 점수)
    """
    if rsi14 is None:
        return 0.0
    if 40 <= rsi14 <= 60:   return 15.0   # 중립 강세
    if 60 < rsi14 <= 70:    return 10.0   # 강세 구간
    if 30 <= rsi14 < 40:    return 8.0    # 과매도 접근
    if rsi14 < 20:          return 12.0   # 극단 과매도 → 반등 (설계서 핵심!)
    if 20 <= rsi14 < 30:    return 12.0   # 과매도 → 반등 가능성
    if 70 < rsi14 <= 80:    return 5.0    # 과매수 주의
    return 0.0                             # >80 극단 과매수


def _score_obv(obv_trend: str, price_trend: str) -> float:
    """
    ⑤ OBV (10점 만점)
    설계서: OBV 방향 + 가격 방향 결합 분석
    """
    if obv_trend == "UP" and price_trend == "UP":
        return 10.0    # OBV↑ + 가격↑ = 정상 상승
    if obv_trend == "UP" and price_trend == "FLAT":
        return 8.0     # OBV↑ + 가격보합 = 기관 매집 (설계서 핵심!)
    if obv_trend == "UP" and price_trend == "DOWN":
        return 6.0     # 긍정 다이버전스
    if obv_trend == "FLAT":
        return 4.0     # 중립
    if obv_trend == "DOWN" and price_trend == "UP":
        return 2.0     # 부정 다이버전스 (경고)
    return 0.0         # OBV↓ = 매도 압력


def _score_volume_surge(surge_ratio: float) -> float:
    """
    ⑥ Volume Surge (10점 만점)
    설계서: 현재 거래량 / 20일 평균 거래량 비율
    """
    if surge_ratio is None:
        return 0.0
    if surge_ratio >= 3.0:  return 10.0   # 3배 이상 = 이상 거래
    if surge_ratio >= 2.0:  return 7.0
    if surge_ratio >= 1.5:  return 4.0
    if surge_ratio >= 1.0:  return 2.0
    return 0.0


def _calc_layer3_score(
    rel_mom_score: float, high52_score: float,
    trend_score: float, rsi_score: float,
    obv_score: float, vol_score: float
) -> float:
    """
    Layer 3 최종 점수 (0~100)
    설계서 4.1: 6개 지표 단순 합산 (0점 시작)
    Momentum(30) + 52W(20) + R²(15) + RSI(15) + OBV(10) + Volume(10) = 100
    """
    total = (rel_mom_score + high52_score + trend_score +
             rsi_score + obv_score + vol_score)
    return round(min(100.0, max(0.0, total)), 2)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 메인 실행 함수
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

    # SPY 수익률 사전 계산 (모든 종목 공통)
    spy_ret_12m, spy_ret_1m = _get_spy_returns(calc_date)

    ok, fail = 0, 0

    for s in stocks:
        stock_id = s["stock_id"]
        ticker   = s["ticker"]

        try:
            # ── 가격 데이터 조회 ──
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

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 원시값 계산
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

            # MA 계산 (보조지표용)
            ma50  = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None
            ma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None
            golden = bool(ma50 > ma200) if (ma50 and ma200) else None
            death  = bool(ma50 < ma200) if (ma50 and ma200) else None

            # RSI 14
            rsi14 = _calc_rsi(close, 14)

            # OBV (가격 연동 분석)
            obv_current, obv_trend, price_trend = _calc_obv(close, volume)

            # 52주 고점 대비
            n52 = min(252, len(high))
            high52  = float(high.tail(n52).max())
            cur_c   = float(close.iloc[-1])
            dist52  = round(cur_c / high52, 4) if high52 and high52 != 0 else None

            # ① Relative Momentum 12-1 (vs SPY)
            rel_mom = None
            rel_mom_vs_spy = None
            if len(close) >= 252:
                c_now = float(close.iloc[-1])
                c_12m = float(close.iloc[-252])
                c_1m  = float(close.iloc[-21]) if len(close) >= 21 else c_now
                if c_12m != 0 and c_1m != 0:
                    stock_ret_12m = (c_now - c_12m) / c_12m
                    stock_ret_1m  = (c_now - c_1m) / c_1m
                    abs_mom = stock_ret_12m - stock_ret_1m  # 절대 12-1

                    # SPY 대비 상대 모멘텀
                    if spy_ret_12m is not None and spy_ret_1m is not None:
                        spy_mom = spy_ret_12m - spy_ret_1m
                        rel_mom_vs_spy = round((abs_mom - spy_mom) * 100, 4)
                    else:
                        rel_mom_vs_spy = round(abs_mom * 100, 4)  # fallback

                    rel_mom = round(abs_mom * 100, 4)

            # ③ Trend R² + Slope (90일 선형회귀)
            trend_r2 = None
            trend_slope = None
            if len(close) >= 90:
                y = close.tail(90).values.astype(float)
                x = np.arange(len(y))
                try:
                    coeffs  = np.polyfit(x, y, 1)
                    trend_slope = round(float(coeffs[0]), 6)
                    y_hat   = np.polyval(coeffs, x)
                    ss_res  = float(np.sum((y - y_hat) ** 2))
                    ss_tot  = float(np.sum((y - y.mean()) ** 2))
                    trend_r2 = round(1 - ss_res / ss_tot, 4) if ss_tot != 0 else None
                except Exception:
                    pass

            # ⑥ Volume Surge
            vol_20d_avg = None
            vol_surge_ratio = None
            if len(volume) >= 20:
                avg20 = float(volume.tail(20).mean())
                cur_vol = float(volume.iloc[-1])
                if avg20 > 0:
                    vol_20d_avg = int(avg20)
                    vol_surge_ratio = round(cur_vol / avg20, 2)

            # VWAP (당일 기준, 일봉에서는 근사치)
            vwap = None
            if len(df) >= 1:
                last_row = df.iloc[-1]
                h = _f(last_row["high_price"])
                l = _f(last_row["low_price"])
                c_val = _f(last_row["close_price"])
                v_val = _f(last_row["volume"])
                if all(x is not None for x in [h, l, c_val]):
                    vwap = round((h + l + c_val) / 3, 4)  # 일봉 근사 VWAP

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 설계서 기준 점수 계산 (0점 시작 → 가산)
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

            rel_mom_score   = _score_relative_momentum(rel_mom_vs_spy)
            high52_score    = _score_52w_high(dist52)
            trend_score     = _score_trend_r2(trend_r2, trend_slope)
            rsi_score       = _score_rsi(rsi14)
            obv_score_val   = _score_obv(obv_trend, price_trend)
            vol_score       = _score_volume_surge(vol_surge_ratio)

            l3_score = _calc_layer3_score(
                rel_mom_score, high52_score, trend_score,
                rsi_score, obv_score_val, vol_score
            )

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # DB 저장 (DDL의 모든 컬럼 매핑)
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

            with get_cursor() as cur:
                cur.execute("""
                    INSERT INTO technical_indicators (
                        stock_id, calc_date,
                        -- ① Relative Momentum
                        relative_momentum_12_1, relative_momentum_score,
                        -- ② 52W High
                        high_52w, high_52w_position_ratio, high_52w_score,
                        -- ③ Trend R²
                        trend_r2_90d, trend_slope_90d, trend_stability_score,
                        -- ④ RSI
                        rsi_14, rsi_score,
                        -- ⑤ OBV
                        obv_current, obv_trend, obv_score,
                        -- ⑥ Volume Surge
                        volume_20d_avg, volume_surge_ratio, volume_surge_score,
                        -- 보조지표
                        golden_cross, death_cross, ma_50, ma_200, vwap,
                        -- 최종 점수
                        layer3_technical_score
                    ) VALUES (
                        %s, %s,
                        %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s
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
                        layer3_technical_score  = EXCLUDED.layer3_technical_score
                """, (
                    stock_id, calc_date,
                    # ① Relative Momentum
                    _f(rel_mom_vs_spy),  _f(rel_mom_score),
                    # ② 52W High
                    _f(high52),  _f(dist52),  _f(high52_score),
                    # ③ Trend R²
                    _f(trend_r2),  _f(trend_slope),  _f(trend_score),
                    # ④ RSI
                    _f(rsi14),  _f(rsi_score),
                    # ⑤ OBV
                    obv_current,  obv_trend,  _f(obv_score_val),
                    # ⑥ Volume Surge
                    vol_20d_avg,  _f(vol_surge_ratio),  _f(vol_score),
                    # 보조지표
                    golden,  death,  _f(ma50),  _f(ma200),  _f(vwap),
                    # 최종
                    _f(l3_score),
                ))

            ok += 1
            rsi_str = f"{rsi14:.1f}" if rsi14 is not None else "N/A"
            print(f"[TECH] {ticker}: L3={l3_score} "
                  f"(Mom={rel_mom_score:.0f} 52W={high52_score:.0f} "
                  f"R²={trend_score:.0f} RSI={rsi_score:.0f} "
                  f"OBV={obv_score_val:.0f} Vol={vol_score:.0f}) ✓")

        except Exception as e:
            fail += 1
            print(f"[TECH] {ticker} 실패: {e}")

    print(f"[TECH] 완료: {ok}성공 / {fail}실패")


if __name__ == "__main__":
    from db_pool import init_pool
    init_pool()
    run_technical_indicators()
