"""
batch_layer3_v2.py  —  Layer 3 Market Signal (V2.0 FINAL)

점수 구조: A.기술지표(55) + B.수급·구조(25) + C.시장환경(20) = 100점
데이터: FDR(무료) + FINRA(무료) + yfinance(무료)
"""

import sys, os, traceback, urllib.request
from datetime import datetime, date, timedelta
from contextlib import suppress

import numpy as np
import pandas as pd
import FinanceDataReader as fdr

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db_pool import get_cursor

# ═══════════════════════════════════════════════════════
#  상수
# ═══════════════════════════════════════════════════════

SECTOR_ETF_MAP = {
    "10": "XLE",  "15": "XLB",  "20": "XLI",  "25": "XLY",
    "30": "XLP",  "35": "XLV",  "40": "XLF",  "45": "XLK",
    "50": "XLC",  "55": "XLU",  "60": "XLRE",
}

# ═══════════════════════════════════════════════════════
#  유틸리티
# ═══════════════════════════════════════════════════════

def _safe(v, digits=6):
    """Decimal/np/None → float 안전 변환"""
    if v is None:
        return None
    try:
        f = float(v)
        if np.isnan(f) or np.isinf(f):
            return None
        return round(f, digits)
    except Exception:
        return None


# ═══════════════════════════════════════════════════════
#  기술지표 계산 (원시값)
# ═══════════════════════════════════════════════════════

def calc_rsi_wilder(close: pd.Series, period: int = 14):
    """Wilder's EWM RSI — TradingView/Bloomberg 표준
    
    ※ SMA RSI와 1~3pt 차이 발생. EWM이 업계 표준.
    """
    if len(close) < period + 1:
        return None
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta.clip(upper=0))
    # Wilder smoothing: alpha = 1/period
    avg_gain = gain.ewm(alpha=1/period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period).mean()
    last_loss = avg_loss.iloc[-1]
    if last_loss == 0 or np.isnan(last_loss):
        return 100.0 if avg_gain.iloc[-1] > 0 else 50.0
    rs = avg_gain.iloc[-1] / last_loss
    return round(100 - (100 / (1 + rs)), 2)


def calc_macd(close: pd.Series):
    """MACD(12,26,9) — 히스토그램 + 전일 히스토그램"""
    if len(close) < 35:
        return None, None, None, None
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    hist = macd_line - signal_line
    return (
        round(float(macd_line.iloc[-1]), 4),
        round(float(signal_line.iloc[-1]), 4),
        round(float(hist.iloc[-1]), 4),
        round(float(hist.iloc[-2]), 4) if len(hist) >= 2 else None,
    )


def calc_bollinger(close: pd.Series, period: int = 20, k: float = 2.0):
    """Bollinger Band + Squeeze(30일 최소 밴드폭) 탐지"""
    n = len(close)
    if n < period + 30:
        return None, None, None, False
    ma  = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = ma + k * std
    lower = ma - k * std
    width = (upper - lower) / ma  # 밴드폭 비율

    cur_w = float(width.iloc[-1])
    min_w = float(width.tail(30).min())
    # Squeeze = 현재 밴드폭이 30일 최소에 근접 (5% 이내)
    squeeze = cur_w <= min_w * 1.05 if min_w > 0 else False

    return (
        round(float(upper.iloc[-1]), 4),
        round(float(lower.iloc[-1]), 4),
        round(cur_w, 4),
        squeeze,
    )


def calc_obv_ma(close: pd.Series, volume: pd.Series):
    """OBV + OBV MA20 교차 + 가격 MA20 대비 방향"""
    if len(close) < 21 or len(volume) < 21:
        return None, None, "NEUTRAL", "NEUTRAL"

    sign = np.sign(close.diff())
    obv = (sign * volume).fillna(0).cumsum()
    obv_ma20 = obv.rolling(20).mean()

    obv_now   = float(obv.iloc[-1])
    obv_ma_v  = float(obv_ma20.iloc[-1]) if not np.isnan(obv_ma20.iloc[-1]) else obv_now

    obv_trend = "UP" if obv_now > obv_ma_v else ("DOWN" if obv_now < obv_ma_v else "NEUTRAL")

    price_ma20 = float(close.tail(20).mean())
    price_now  = float(close.iloc[-1])
    ratio = price_now / price_ma20 if price_ma20 > 0 else 1.0
    if ratio > 1.01:
        price_trend = "UP"
    elif ratio < 0.99:
        price_trend = "DOWN"
    else:
        price_trend = "NEUTRAL"

    return obv_now, obv_ma_v, obv_trend, price_trend


def calc_ma20_streak(close: pd.Series) -> int:
    """종가 > MA20 연속 일수 (최대 30일까지 탐색)"""
    if len(close) < 20:
        return 0
    ma20 = close.rolling(20).mean()
    streak = 0
    for i in range(len(close) - 1, max(19, len(close) - 31), -1):
        val = ma20.iloc[i]
        if np.isnan(val):
            break
        if close.iloc[i] > val:
            streak += 1
        else:
            break
    return streak


def calc_trend_r2_log(close: pd.Series, window: int = 90):
    """90일 log(종가) 선형회귀 → R², slope
    
    ※ log 변환: 고가주/저가주 간 기울기 비교 왜곡 제거
    """
    if len(close) < window:
        return None, None
    y = np.log(close.tail(window).values.astype(float))
    if np.any(np.isnan(y)) or np.any(np.isinf(y)):
        return None, None
    x = np.arange(window, dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    y_pred = slope * x + intercept
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    r2 = round(1 - ss_res / ss_tot, 4) if ss_tot > 0 else 0.0
    return r2, round(float(slope), 6)


# ═══════════════════════════════════════════════════════
#  [A] 기술지표 점수화 — 55점 만점
# ═══════════════════════════════════════════════════════

def score_relative_momentum(rel_mom) -> float:
    """① 12-1 상대모멘텀 → 0~15점
    
    rel_mom = (종목 12-1 mom) - (SPY 12-1 mom)
    양수면 시장보다 강하다는 의미.
    구간을 현실 분포에 맞게 조정 (30% 초과는 극소수 → 25%로 하향)
    """
    if rel_mom is None:
        return 0.0
    p = rel_mom * 100  # → %
    if p >= 25:  return 15.0
    if p >= 15:  return 12.0
    if p >= 8:   return 9.0
    if p >= 0:   return 6.0
    if p >= -8:  return 3.0
    return 0.0


def score_52w_high(ratio) -> float:
    """② 52주 고가 대비 현재가 위치 → 0~10점"""
    if ratio is None:
        return 0.0
    r = ratio * 100  # → %
    if r >= 95:  return 10.0
    if r >= 85:  return 8.0
    if r >= 75:  return 6.0
    if r >= 65:  return 4.0
    if r >= 55:  return 2.0
    return 0.0


def score_trend_r2(r2, slope) -> float:
    """③ Trend R² + Slope → 0~8점
    
    R²≥0.7 + 양의기울기 = 안정 상승추세 → 만점
    R² 높아도 기울기 음이면 안정 하락 → 감점
    """
    if r2 is None:
        return 0.0
    if r2 >= 0.7:
        if slope is not None and slope > 0:
            return 8.0
        return 4.0   # R² 높지만 하락 추세 → 반만
    if r2 >= 0.5:
        return 4.0 if (slope is not None and slope > 0) else 2.0
    if r2 >= 0.3:
        return 2.0
    return 0.0


def score_rsi(rsi) -> float:
    """④ Wilder RSI(14) → 0~7점
    
    40~60: 건강한 중립 = 만점 (추세 지속 구간)
    <30:  과매도 = 6점 (반등 기회, 역추세에도 점수)
    >80:  극과매수 = 0점 (단기 조정 위험)
    """
    if rsi is None:
        return 0.0
    if 40 <= rsi <= 60:    return 7.0
    if rsi < 30:           return 6.0  # 과매도 반등
    if 60 < rsi <= 70:     return 5.0
    if 30 <= rsi < 40:     return 4.0
    if 70 < rsi <= 80:     return 2.0
    return 0.0  # >80 극과매수


def score_macd(hist, prev_hist) -> float:
    """⑤ MACD Histogram → 0~5점
    
    상향교차(전일-/오늘+) = 추세 전환 초기 → 만점
    하향교차(전일+/오늘-) = 추세 꺾임 → 0점
    """
    if hist is None:
        return 0.0
    if prev_hist is not None:
        if prev_hist < 0 and hist > 0:   return 5.0  # 상향 교차
        if prev_hist > 0 and hist < 0:   return 0.0  # 하향 교차
    if hist > 0:
        if prev_hist is not None and hist > prev_hist:
            return 4.0  # 양(+), 증가중
        return 2.0      # 양(+), 감소중
    else:
        if prev_hist is not None and hist > prev_hist:
            return 2.0  # 음(-), 올라오는중 (반등 전조)
        return 0.0      # 음(-), 더 떨어지는중


def score_obv(obv_trend: str, price_trend: str) -> float:
    """⑥ OBV vs MA20 × 가격방향 → 0~5점
    
    OBV↑+가격↑ = 매집+상승 = 만점
    OBV↓+가격↑ = 분산+상승 = 위험 경고 (1점)
    OBV↑+가격↓ = 매집+하락 = 반등 잠재 (3점)
    """
    matrix = {
        ("UP",      "UP"):      5.0,
        ("UP",      "NEUTRAL"): 4.0,
        ("UP",      "DOWN"):    3.0,
        ("NEUTRAL", "UP"):      3.0,
        ("NEUTRAL", "NEUTRAL"): 2.0,
        ("NEUTRAL", "DOWN"):    1.0,
        ("DOWN",    "UP"):      1.0,
        ("DOWN",    "NEUTRAL"): 1.0,
        ("DOWN",    "DOWN"):    0.0,
    }
    return matrix.get((obv_trend, price_trend), 2.0)


def score_volume_surge(ratio) -> float:
    """⑦ 거래량 / 20일 평균 → 0~5점
    
    주의: Volume Surge + 가격 상승 = 강세 확인
          Volume Surge + 가격 하락 = 투매 (이것만으론 판단 불가)
    → 여기서는 순수 surge 크기만 점수화. 방향은 OBV에서 잡음.
    """
    if ratio is None:
        return 0.0
    if ratio >= 3.0:  return 5.0
    if ratio >= 2.0:  return 3.0
    if ratio >= 1.5:  return 2.0
    if ratio >= 1.0:  return 1.0
    return 0.0


# ═══════════════════════════════════════════════════════
#  [B] 수급·구조 시그널 점수화 — 25점 만점
# ═══════════════════════════════════════════════════════

def score_golden_cross(ma50, ma200) -> float:
    """⑨-A GC/DC → 0~2점"""
    if ma50 is None or ma200 is None:
        return 1.0   # 데이터 부족 → 중립
    return 2.0 if ma50 > ma200 else 0.0


def score_bb_squeeze(squeeze: bool, close_price, bb_upper) -> float:
    """⑨-B BB Squeeze + 돌파 → 0~2점"""
    if not squeeze:
        return 0.0
    if bb_upper is not None and close_price is not None and close_price > bb_upper:
        return 2.0   # Squeeze + 상단 돌파 = 강세 폭발
    return 1.0       # Squeeze 중 (대기)


def score_ma20_streak(days: int) -> float:
    """⑨-C MA20 연속 상회 → 0~2점"""
    if days >= 5:    return 2.0
    if days >= 3:    return 1.0
    return 0.0


def score_breakout_52w(is_breakout: bool) -> float:
    """⑨-D 52주 신고가 돌파 → 0~2점"""
    return 2.0 if is_breakout else 0.0


def score_short_volume(svr_5d) -> float:
    """⑧ Short Volume Ratio 5일평균 → 0~10점
    
    시장 평균 SVR ≈ 40%. 낮을수록 강세.
    5일 평균 사용 → 단일일 노이즈 70% 감소.
    """
    if svr_5d is None:
        return 5.0  # 데이터 없으면 중립
    if svr_5d < 0.30:  return 10.0
    if svr_5d < 0.35:  return 8.0
    if svr_5d < 0.40:  return 6.0
    if svr_5d < 0.45:  return 4.0
    if svr_5d < 0.50:  return 2.0
    return 0.0


def score_put_call(pc) -> float:
    """⑩ Put/Call Ratio → 0~7점
    
    낮을수록 Call 우세 = 강세 센티먼트.
    yfinance 실패 시 중립 3점.
    """
    if pc is None:
        return 3.0  # graceful degradation
    if pc <= 0.5:   return 7.0
    if pc <= 0.7:   return 5.0
    if pc <= 0.9:   return 4.0
    if pc <= 1.1:   return 3.0
    if pc <= 1.3:   return 1.0
    return 0.0


# ═══════════════════════════════════════════════════════
#  [C] 시장 환경 점수화 — 20점 만점
# ═══════════════════════════════════════════════════════

def score_vix(vix) -> float:
    """⑪ VIX → 0~10점 (역발상: 공포=매수기회)
    
    VIX > 30: 극단 공포 → 역사적으로 매수 적기
    VIX < 12: 극단 안도 → 과열 경고
    """
    if vix is None:
        return 4.0  # 중립
    if vix > 30:   return 10.0
    if vix > 25:   return 8.0
    if vix > 20:   return 6.0
    if vix > 15:   return 4.0
    if vix > 12:   return 2.0
    return 0.0


def score_sector_etf(close, ma20, ma50) -> float:
    """⑫ 섹터 ETF 이평선 위치 → 0~10점"""
    if close is None or ma20 is None:
        return 4.0  # 중립
    if ma50 is not None and close > ma20 and ma20 > ma50:
        return 10.0  # 정배열 상승
    if close > ma20:
        return 7.0
    if ma20 > 0 and abs(close - ma20) / ma20 < 0.01:
        return 4.0   # 횡보
    if ma50 is not None and close < ma20 and ma20 < ma50:
        return 0.0   # 역배열 하락
    return 1.0


# ═══════════════════════════════════════════════════════
#  SPY 벤치마크 사전 로드
# ═══════════════════════════════════════════════════════

def _load_spy_momentum():
    """SPY 12-1 모멘텀 사전 계산. 없으면 (None, None)"""
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT close_price
                FROM stock_prices_daily
                WHERE stock_id = (
                    SELECT stock_id FROM stocks
                    WHERE ticker = 'SPY' LIMIT 1
                )
                ORDER BY trade_date DESC LIMIT 252
            """)
            rows = cur.fetchall()
        if not rows or len(rows) < 60:
            return None, None
        prices = [float(r["close_price"]) for r in reversed(rows)]
        n = len(prices)
        if n >= 252:
            ret12 = (prices[-1] - prices[0]) / prices[0]
        else:
            ret12 = (prices[-1] - prices[0]) / prices[0]
        ret1 = (prices[-1] - prices[-min(21, n)]) / prices[-min(21, n)]
        return ret12, ret1
    except Exception as e:
        print(f"[L3] SPY 로드 실패: {e}")
        return None, None


# ═══════════════════════════════════════════════════════
#  Phase 1: run_technical_indicators (A.기술지표 55점)
# ═══════════════════════════════════════════════════════

def run_technical_indicators(calc_date: date = None):
    """[A] 기술지표 7개 + 구조적 시그널 4개 계산·저장"""

    if calc_date is None:
        calc_date = datetime.now().date()

    print(f"[L3-TECH] ▶ 시작 calc_date={calc_date}")

    # ── 전 종목 목록 ──
    with get_cursor() as cur:
        cur.execute("""
            SELECT s.stock_id, s.ticker,
                   COALESCE(sec.sector_code, '') AS sector_code
            FROM stocks s
            LEFT JOIN sectors sec ON s.sector_id = sec.sector_id
            WHERE s.is_active = TRUE
        """)
        stocks = [dict(r) for r in cur.fetchall()]

    if not stocks:
        print("[L3-TECH] ⚠ 활성 종목 없음")
        return

    print(f"[L3-TECH] 대상: {len(stocks)}종목")

    # ── SPY 사전 로드 ──
    spy_ret12, spy_ret1 = _load_spy_momentum()
    spy_mom = (spy_ret12 - spy_ret1) if spy_ret12 is not None else None
    if spy_mom is not None:
        print(f"[L3-TECH] SPY 12-1 Mom = {spy_mom*100:.2f}%")
    else:
        print("[L3-TECH] ⚠ SPY 없음 → 절대 모멘텀 fallback")

    ok, fail = 0, 0

    for stk in stocks:
        sid    = stk["stock_id"]
        ticker = stk["ticker"]

        try:
            # ── 가격 로드 (300일) ──
            with get_cursor() as cur:
                cur.execute("""
                    SELECT trade_date, open_price, high_price,
                           low_price, close_price, volume
                    FROM stock_prices_daily
                    WHERE stock_id = %s
                    ORDER BY trade_date DESC
                    LIMIT 300
                """, (sid,))
                rows = [dict(r) for r in cur.fetchall()]

            if len(rows) < 30:
                fail += 1
                continue

            df = pd.DataFrame(rows).sort_values("trade_date").reset_index(drop=True)

            close  = df["close_price"].astype(float)
            volume = df["volume"].apply(lambda x: float(x) if x else 0).astype(float)
            high   = df["high_price"].astype(float)

            # ── volume=0 미완결 행 제거 (장전 배치 대비) ──
            while len(close) > 30 and volume.iloc[-1] <= 0:
                df    = df.iloc[:-1]
                close = close.iloc[:-1]
                volume = volume.iloc[:-1]
                high  = high.iloc[:-1]

            n = len(close)
            if n < 30:
                fail += 1
                continue

            price_now = float(close.iloc[-1])

            # ═══════════════════════════════════
            #  원시값 계산
            # ═══════════════════════════════════

            # ① Relative Momentum 12-1
            if n >= 252:
                r12 = (price_now - float(close.iloc[-252])) / float(close.iloc[-252])
                r1  = (price_now - float(close.iloc[-21])) / float(close.iloc[-21])
                s_mom_raw = r12 - r1
                rel_mom = (s_mom_raw - spy_mom) if spy_mom is not None else s_mom_raw
            elif n >= 60:
                # 데이터 252일 미만 → 보유 기간 전체 사용
                r_all = (price_now - float(close.iloc[0])) / float(close.iloc[0])
                r1    = (price_now - float(close.iloc[-21])) / float(close.iloc[-21])
                s_mom_raw = r_all - r1
                rel_mom = (s_mom_raw - spy_mom) if spy_mom is not None else s_mom_raw
            else:
                rel_mom = None

            # ② 52W High Position
            high52 = float(high.tail(min(252, n)).max())
            dist52 = price_now / high52 if high52 > 0 else None

            # ③ Trend R² (log 회귀)
            r2, slope = calc_trend_r2_log(close)

            # ④ RSI Wilder
            rsi14 = calc_rsi_wilder(close)

            # ⑤ MACD
            macd_l, macd_s, macd_h, macd_ph = calc_macd(close)

            # ⑥ OBV + MA20
            obv_v, obv_ma_v, obv_trend, price_trend = calc_obv_ma(close, volume)

            # ⑦ Volume Surge
            vol_avg20 = float(volume.tail(20).mean()) if n >= 20 else None
            vol_surge = (float(volume.iloc[-1]) / vol_avg20) if vol_avg20 and vol_avg20 > 0 else None

            # 보조값
            ma50  = float(close.tail(50).mean()) if n >= 50 else None
            ma200 = float(close.tail(200).mean()) if n >= 200 else None

            # Bollinger
            bb_up, bb_lo, bb_w, bb_sq = calc_bollinger(close)

            # MA20 연속 상회
            streak = calc_ma20_streak(close)

            # 52W Breakout
            breakout = (dist52 is not None and dist52 >= 1.0)

            # ═══════════════════════════════════
            #  점수 계산
            # ═══════════════════════════════════

            s1 = score_relative_momentum(rel_mom)
            s2 = score_52w_high(dist52)
            s3 = score_trend_r2(r2, slope)
            s4 = score_rsi(rsi14)
            s5 = score_macd(macd_h, macd_ph)
            s6 = score_obv(obv_trend, price_trend)
            s7 = score_volume_surge(vol_surge)

            sec_a = round(s1 + s2 + s3 + s4 + s5 + s6 + s7, 2)

            # 구조적 시그널 (⑨, 8점 만점)
            s9a = score_golden_cross(ma50, ma200)
            s9b = score_bb_squeeze(bb_sq, price_now, bb_up)
            s9c = score_ma20_streak(streak)
            s9d = score_breakout_52w(breakout)
            structural = round(s9a + s9b + s9c + s9d, 2)

            # ═══════════════════════════════════
            #  DB UPSERT
            # ═══════════════════════════════════

            with get_cursor() as cur:
                cur.execute("""
                    INSERT INTO technical_indicators (
                        stock_id, calc_date,
                        relative_momentum_12_1, relative_momentum_score,
                        high_52w, high_52w_position_ratio, high_52w_score,
                        trend_r2_90d, trend_slope_90d, trend_stability_score,
                        rsi_14, rsi_score,
                        macd_line, macd_signal, macd_histogram, macd_score,
                        obv_current, obv_ma20, obv_trend, obv_score,
                        volume_20d_avg, volume_surge_ratio, volume_surge_score,
                        golden_cross, death_cross, ma_50, ma_200,
                        bb_upper, bb_lower, bb_width, bb_squeeze,
                        golden_cross_score, bb_squeeze_score,
                        ma20_streak_days, ma20_streak_score,
                        breakout_52w, breakout_52w_score,
                        structural_signal_score,
                        section_a_technical,
                        layer3_technical_score
                    ) VALUES (
                        %(sid)s, %(dt)s,
                        %(rel_mom)s, %(s1)s,
                        %(h52)s, %(d52)s, %(s2)s,
                        %(r2)s, %(slope)s, %(s3)s,
                        %(rsi)s, %(s4)s,
                        %(ml)s, %(ms)s, %(mh)s, %(s5)s,
                        %(obv)s, %(obv_ma)s, %(obv_t)s, %(s6)s,
                        %(va20)s, %(vsurge)s, %(s7)s,
                        %(gc)s, %(dc)s, %(m50)s, %(m200)s,
                        %(bbu)s, %(bbl)s, %(bbw)s, %(bbsq)s,
                        %(s9a)s, %(s9b)s,
                        %(streak)s, %(s9c)s,
                        %(brk)s, %(s9d)s,
                        %(struct)s,
                        %(seca)s,
                        %(seca)s
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
                        layer3_technical_score  = EXCLUDED.layer3_technical_score
                """, {
                    "sid": sid, "dt": calc_date,
                    "rel_mom": _safe(rel_mom), "s1": s1,
                    "h52": _safe(high52, 2), "d52": _safe(dist52, 4), "s2": s2,
                    "r2": _safe(r2, 4), "slope": _safe(slope), "s3": s3,
                    "rsi": _safe(rsi14, 2), "s4": s4,
                    "ml": _safe(macd_l, 4), "ms": _safe(macd_s, 4),
                    "mh": _safe(macd_h, 4), "s5": s5,
                    "obv": _safe(obv_v, 0), "obv_ma": _safe(obv_ma_v, 0),
                    "obv_t": obv_trend, "s6": s6,
                    "va20": _safe(vol_avg20, 0), "vsurge": _safe(vol_surge, 2),
                    "s7": s7,
                    "gc": (ma50 is not None and ma200 is not None and ma50 > ma200),
                    "dc": (ma50 is not None and ma200 is not None and ma50 < ma200),
                    "m50": _safe(ma50, 2), "m200": _safe(ma200, 2),
                    "bbu": _safe(bb_up, 2), "bbl": _safe(bb_lo, 2),
                    "bbw": _safe(bb_w, 4), "bbsq": bool(bb_sq),
                    "s9a": s9a, "s9b": s9b,
                    "streak": streak, "s9c": s9c,
                    "brk": bool(breakout), "s9d": s9d,
                    "struct": structural,
                    "seca": sec_a,
                })

            ok += 1

        except Exception as e:
            print(f"[L3] {ticker} 실패: {e}")
            traceback.print_exc()
            fail += 1

    print(f"[L3-TECH] ✅ 완료 성공={ok} 실패={fail}")


# ═══════════════════════════════════════════════════════
#  Phase 2: run_market_environment (C.시장환경 20점)
# ═══════════════════════════════════════════════════════

def run_market_environment(calc_date: date = None):
    """VIX + 섹터 ETF 11개 수집·점수화"""

    if calc_date is None:
        calc_date = datetime.now().date()
    print(f"[L3-MACRO] ▶ 시작 calc_date={calc_date}")

    # ── VIX ──
    vix_close, vix_sc = None, 4.0
    try:
        vdf = fdr.DataReader("^VIX")
        if vdf is not None and len(vdf) > 0:
            vix_close = round(float(vdf.iloc[-1]["Close"]), 2)
            vix_sc = score_vix(vix_close)
            print(f"[L3-MACRO] VIX = {vix_close} → {vix_sc}점")
    except Exception as e:
        print(f"[L3-MACRO] ⚠ VIX 실패: {e} → 중립 4점")

    # ── SPY MA ──
    spy_c, spy_m50, spy_m200 = None, None, None
    try:
        sdf = fdr.DataReader("SPY")
        if sdf is not None and len(sdf) >= 200:
            spy_c   = round(float(sdf.iloc[-1]["Close"]), 2)
            spy_m50 = round(float(sdf["Close"].tail(50).mean()), 2)
            spy_m200 = round(float(sdf["Close"].tail(200).mean()), 2)
    except Exception:
        pass

    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO market_signal_daily
                (calc_date, vix_close, vix_score, spy_close, spy_ma50, spy_ma200)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (calc_date) DO UPDATE SET
                vix_close = EXCLUDED.vix_close,
                vix_score = EXCLUDED.vix_score,
                spy_close = EXCLUDED.spy_close,
                spy_ma50  = EXCLUDED.spy_ma50,
                spy_ma200 = EXCLUDED.spy_ma200
        """, (calc_date, vix_close, vix_sc, spy_c, spy_m50, spy_m200))

    # ── 섹터 ETF ──
    etf_ok = 0
    for code, sym in SECTOR_ETF_MAP.items():
        try:
            edf = fdr.DataReader(sym)
            if edf is None or len(edf) < 50:
                continue
            ec  = round(float(edf.iloc[-1]["Close"]), 2)
            em20 = round(float(edf["Close"].tail(20).mean()), 2)
            em50 = round(float(edf["Close"].tail(50).mean()), 2)
            esc = score_sector_etf(ec, em20, em50)

            with get_cursor() as cur:
                cur.execute("""
                    INSERT INTO sector_etf_daily
                        (calc_date, sector_code, etf_symbol,
                         etf_close, etf_ma20, etf_ma50, sector_etf_score)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (calc_date, sector_code) DO UPDATE SET
                        etf_close = EXCLUDED.etf_close,
                        etf_ma20  = EXCLUDED.etf_ma20,
                        etf_ma50  = EXCLUDED.etf_ma50,
                        sector_etf_score = EXCLUDED.sector_etf_score
                """, (calc_date, code, sym, ec, em20, em50, esc))
            etf_ok += 1
        except Exception as e:
            print(f"[L3-MACRO] ⚠ {sym} 실패: {e}")

    print(f"[L3-MACRO] ✅ VIX 완료, 섹터 ETF {etf_ok}/{len(SECTOR_ETF_MAP)}개")


# ═══════════════════════════════════════════════════════
#  Phase 3: run_short_volume (B.수급 ⑧ 10점)
# ═══════════════════════════════════════════════════════

def run_short_volume(calc_date: date = None):
    """FINRA RegSHO 일일 Short Volume 수집 (다중 URL + 7일 rollback)"""

    if calc_date is None:
        calc_date = datetime.now().date()
    print(f"[L3-SHORT] ▶ 시작 calc_date={calc_date}")

    # ━━━ 1. FINRA 파일 다운로드 (다중 URL + 7일 rollback) ━━━
    FINRA_URLS = [
        "https://cdn.finra.org/equity/regsho/daily/CNMSshvol{dt}.txt",   # 2024~ 신규 CDN
        "http://regsho.finra.org/CNMSshvol{dt}.txt",                     # 레거시 URL
    ]

    raw = None
    td = None
    for offset in range(1, 8):
        candidate = calc_date - timedelta(days=offset)
        if candidate.weekday() >= 5:   # 토=5, 일=6 스킵
            continue
        dt_str = candidate.strftime("%Y%m%d")
        for url_tpl in FINRA_URLS:
            url = url_tpl.format(dt=dt_str)
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                resp = urllib.request.urlopen(req, timeout=15)
                raw = resp.read().decode("utf-8")
                td = candidate
                print(f"[L3-SHORT] ✅ FINRA 파일 확보: {url}")
                break
            except Exception as e:
                print(f"[L3-SHORT]   시도 {candidate} ({url.split('/')[-1]}) → {type(e).__name__}: {e}")
        if raw is not None:
            break

    if raw is None or td is None:
        print(f"[L3-SHORT] ⚠ 최근 7일 내 FINRA 파일 없음 → 전일값 유지")
        return

    data_lines = raw.strip().split("\n")
    print(f"[L3-SHORT] 파일 라인수: {len(data_lines)}")
    if data_lines:
        print(f"[L3-SHORT] 헤더: {data_lines[0][:100]}")
    if len(data_lines) > 1:
        print(f"[L3-SHORT] 샘플: {data_lines[1][:100]}")

    # ━━━ 2. 우리 종목 목록 ━━━
    with get_cursor() as cur:
        cur.execute("SELECT stock_id, ticker FROM stocks WHERE is_active = TRUE")
        tmap = {r["ticker"]: r["stock_id"] for r in cur.fetchall()}

    print(f"[L3-SHORT] 매칭 대상: {len(tmap)}종목 ({', '.join(sorted(tmap.keys())[:5])}...)")

    # ━━━ 3. 파싱 + DB 저장 ━━━
    ok = 0
    matched_tickers = []
    for line in data_lines[1:]:   # 첫 줄(헤더) 스킵
        parts = line.split("|")
        if len(parts) < 5:
            continue
        sym = parts[1].strip()
        if sym not in tmap:
            continue
        sid = tmap[sym]
        try:
            sv  = int(float(parts[2])) + int(float(parts[3]))   # ShortVolume + ShortExemptVolume (소수점 대응)
            tv  = int(float(parts[4]))
            if tv == 0:
                continue
            svr = round(sv / tv, 4)

            # 이전 4일치 조회 → 5일 이동평균
            with get_cursor() as cur:
                cur.execute("""
                    SELECT short_volume_ratio FROM short_volume_daily
                    WHERE stock_id = %s ORDER BY trade_date DESC LIMIT 4
                """, (sid,))
                prev = [float(r["short_volume_ratio"]) for r in cur.fetchall()
                        if r["short_volume_ratio"] is not None]

            pool = prev + [svr]
            svr5 = round(sum(pool[-5:]) / len(pool[-5:]), 4)
            sc   = score_short_volume(svr5)

            with get_cursor() as cur:
                cur.execute("""
                    INSERT INTO short_volume_daily
                        (stock_id, trade_date, short_volume, total_volume,
                         short_volume_ratio, svr_5d_avg, short_volume_score)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (stock_id, trade_date) DO UPDATE SET
                        short_volume = EXCLUDED.short_volume,
                        total_volume = EXCLUDED.total_volume,
                        short_volume_ratio = EXCLUDED.short_volume_ratio,
                        svr_5d_avg = EXCLUDED.svr_5d_avg,
                        short_volume_score = EXCLUDED.short_volume_score
                """, (sid, td, sv, tv, svr, svr5, sc))
            ok += 1
            matched_tickers.append(f"{sym}(SVR={svr:.1%}→{sc:.0f}점)")
        except Exception as e:
            print(f"[L3-SHORT] {sym} 파싱실패: {e}")

    if matched_tickers:
        for t in matched_tickers:
            print(f"  {t}")
    print(f"[L3-SHORT] ✅ 완료 {ok}/{len(tmap)}종목 (날짜={td})")


# ═══════════════════════════════════════════════════════
#  Phase 4: run_put_call_ratio (B.수급 ⑩ 7점)
# ═══════════════════════════════════════════════════════

def run_put_call_ratio(calc_date: date = None):
    """yfinance 옵션체인 P/C Ratio (실패 허용 + 상세 로그)"""

    if calc_date is None:
        calc_date = datetime.now().date()
    print(f"[L3-PC] ▶ 시작 calc_date={calc_date}")

    try:
        import yfinance as yf
        import time as _time
    except ImportError:
        print("[L3-PC] ⚠ yfinance 없음 → 전종목 중립 3점")
        _set_all_pc_neutral(calc_date)
        return

    with get_cursor() as cur:
        cur.execute("SELECT stock_id, ticker FROM stocks WHERE is_active = TRUE")
        stocks = [dict(r) for r in cur.fetchall()]

    ok, fail, neutral = 0, 0, 0
    for s in stocks:
        sid, ticker = s["stock_id"], s["ticker"]
        pc_sc = 3.0   # 기본 중립 (graceful degradation)
        status = "중립(기본값)"
        try:
            t = yf.Ticker(ticker)
            exps = t.options
            if exps:
                chain = t.option_chain(exps[0])
                cv = chain.calls["volume"].sum()
                pv = chain.puts["volume"].sum()
                if cv and cv > 0:
                    pc = float(pv / cv)
                    pc_sc = score_put_call(pc)
                    status = f"P/C={pc:.2f} → {pc_sc:.1f}점"
                    ok += 1
                else:
                    status = "거래량0 → 중립3점"
                    neutral += 1
            else:
                status = "옵션만기없음 → 중립3점"
                neutral += 1
            _time.sleep(2.0)  # Rate limit 강화
        except Exception as e:
            fail += 1
            status = f"실패({str(e)[:40]}) → 중립3점"

        with suppress(Exception):
            with get_cursor() as cur:
                cur.execute("""
                    UPDATE technical_indicators SET put_call_score = %s
                    WHERE stock_id = %s AND calc_date = %s
                """, (pc_sc, sid, calc_date))

        print(f"  {ticker:6s}: {status}")

    print(f"[L3-PC] ✅ 실측={ok} 중립={neutral} 실패={fail} (총{ok+neutral+fail}종목)")


def _set_all_pc_neutral(calc_date: date):
    """yfinance 불가 시 전종목 P/C 중립값"""
    with suppress(Exception):
        with get_cursor() as cur:
            cur.execute("""
                UPDATE technical_indicators SET put_call_score = 3.0
                WHERE calc_date = %s
            """, (calc_date,))


# ═══════════════════════════════════════════════════════
#  Phase 5: run_layer3_final (A+B+C = 100점 합산)
# ═══════════════════════════════════════════════════════

def run_layer3_final(calc_date: date = None):
    """기술(55) + 수급·구조(25) + 시장환경(20) = L3 최종점수 (상세 로그)"""

    if calc_date is None:
        calc_date = datetime.now().date()
    print(f"[L3-FINAL] ▶ 시작 calc_date={calc_date}")

    # VIX 점수
    vix_sc = 4.0
    with get_cursor() as cur:
        cur.execute("SELECT vix_score FROM market_signal_daily WHERE calc_date = %s",
                    (calc_date,))
        row = cur.fetchone()
        if row and row["vix_score"] is not None:
            vix_sc = float(row["vix_score"])

    # 섹터 ETF 점수 캐시
    sec_etf = {}
    with get_cursor() as cur:
        cur.execute("SELECT sector_code, sector_etf_score FROM sector_etf_daily WHERE calc_date = %s",
                    (calc_date,))
        for r in cur.fetchall():
            sec_etf[str(r["sector_code"]).strip()] = float(r["sector_etf_score"])

    # Short Volume 점수 캐시 (가장 최근)
    sv_scores = {}
    with get_cursor() as cur:
        cur.execute("""
            SELECT stock_id, short_volume_score FROM short_volume_daily
            WHERE trade_date = (SELECT MAX(trade_date) FROM short_volume_daily WHERE trade_date <= %s)
        """, (calc_date,))
        for r in cur.fetchall():
            sv_scores[int(r["stock_id"])] = float(r["short_volume_score"])

    print(f"[L3-FINAL] VIX점수={vix_sc}, 섹터ETF={len(sec_etf)}개 (keys={list(sec_etf.keys())}), 공매도={len(sv_scores)}종목")

    # 티커 맵
    ticker_map = {}
    with get_cursor() as cur:
        cur.execute("SELECT stock_id, ticker FROM stocks WHERE is_active = TRUE")
        ticker_map = {r["stock_id"]: r["ticker"] for r in cur.fetchall()}

    # 종목별 합산
    with get_cursor() as cur:
        cur.execute("""
            SELECT t.stock_id, t.section_a_technical,
                   t.structural_signal_score, t.put_call_score,
                   COALESCE(sec.sector_code, '') AS sector_code
            FROM technical_indicators t
            JOIN stocks s ON t.stock_id = s.stock_id
            LEFT JOIN sectors sec ON s.sector_id = sec.sector_id
            WHERE t.calc_date = %s
        """, (calc_date,))
        rows = [dict(r) for r in cur.fetchall()]

    ok = 0
    for r in rows:
        sid = r["stock_id"]
        ticker = ticker_map.get(sid, f"ID:{sid}")
        sector = str(r.get("sector_code") or "").strip()

        sec_a = float(r.get("section_a_technical") or 0)

        sv_sc     = sv_scores.get(sid, 5.0)        # Short Volume (중립 5)
        struct_sc = float(r.get("structural_signal_score") or 0)
        pc_sc     = float(r.get("put_call_score") or 3.0)
        sec_b     = round(sv_sc + struct_sc + pc_sc, 2)

        etf_sc = sec_etf.get(sector, 4.0)          # 섹터 ETF (중립 4)
        sec_c  = round(vix_sc + etf_sc, 2)

        total  = round(sec_a + sec_b + sec_c, 2)

        # 상세 로그 — 기본값 사용 여부 표시
        sv_tag  = "" if sid in sv_scores else "(기본값)"
        etf_tag = "" if sector in sec_etf else "(기본값)"
        print(f"  {ticker:6s} A={sec_a:5.1f}/55  "
              f"B={sec_b:5.1f}/25(SV={sv_sc:.0f}{sv_tag}+ST={struct_sc:.0f}+PC={pc_sc:.0f})  "
              f"C={sec_c:5.1f}/20(VIX={vix_sc:.0f}+ETF={etf_sc:.0f}{etf_tag})  "
              f"→ TOTAL={total:5.1f}/100")

        with get_cursor() as cur:
            cur.execute("""
                UPDATE technical_indicators SET
                    short_volume_score  = %s,
                    vix_score           = %s,
                    sector_etf_score    = %s,
                    section_b_flow      = %s,
                    section_c_macro     = %s,
                    layer3_total_score  = %s,
                    layer3_technical_score = %s
                WHERE stock_id = %s AND calc_date = %s
            """, (sv_sc, vix_sc, etf_sc, sec_b, sec_c, total, total, sid, calc_date))
        ok += 1

    print(f"[L3-FINAL] ✅ {ok}종목 L3 최종점수 산출")


# ═══════════════════════════════════════════════════════
#  ALL-IN-ONE
# ═══════════════════════════════════════════════════════

def run_all(calc_date: date = None):
    """Layer 3 전체 배치 (순서 보장)"""
    if calc_date is None:
        calc_date = datetime.now().date()

    print(f"\n{'='*60}")
    print(f"  Layer 3 배치 시작 — {calc_date}")
    print(f"{'='*60}\n")

    run_technical_indicators(calc_date)
    run_market_environment(calc_date)
    run_short_volume(calc_date)
    run_put_call_ratio(calc_date)
    run_layer3_final(calc_date)

    print(f"\n{'='*60}")
    print(f"  Layer 3 배치 완료")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    import db_pool
    db_pool.init_pool()
    try:
        run_all()
    finally:
        db_pool.close_pool()
