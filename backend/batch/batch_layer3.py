"""
batch_layer3.py — Layer 3 기술지표 배치잡
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
매일 03:30 KST 실행 (scheduler.py에서 호출)
FDR 가격 데이터 → 기술지표 계산 → technical_indicators 저장

설계서 4.1 기준 — 6개 지표 점수 체계:
  ① Relative Momentum 12-1  (30점)  vs SPY 상대수익률
  ② 52W High Position        (20점)  현재가 / 52주최고가
  ③ Trend Stability R²       (15점)  90일 회귀 R² + 기울기
  ④ RSI 14일                 (15점)  역추세 진입 탐지
  ⑤ OBV                      (10점)  거래량-가격 연동 분석
  ⑥ Volume Surge              (10점)  20일 평균 대비 거래량 비율
  ─────────────────────────────────────
  합계                         100점

보조지표 (점수 미반영, 저장만):
  - Golden/Death Cross (MA50 vs MA200)
  - VWAP (일봉 근사치)
  - MA 50 / MA 200

변경이력:
  v1.0  — 초기 구현 (50점 기준 ±가감 방식)
  v2.0  — 설계서 정합성 검증 후 전면 재작성
          · 0점 시작 → 가산 방식으로 변경
          · Volume Surge 신규 구현
          · SPY 대비 상대 모멘텀 구현
          · OBV + 가격 연동 분석 구현
          · volume=0 미완결 행 제거 로직 추가
          · DDL 24개 컬럼 전체 매핑
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from datetime import datetime, date
from db_pool import get_cursor


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 유틸리티
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _f(v):
    """np.float64, Decimal 등 → Python float 변환. None-safe."""
    if v is None:
        return None
    try:
        fv = float(v)
        if np.isnan(fv) or np.isinf(fv):
            return None
        return fv
    except Exception:
        return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 원시값(raw) 계산 함수
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _calc_rsi(close: pd.Series, period: int = 14) -> float | None:
    """RSI 14일 (Wilder's Smoothing 근사)"""
    try:
        if len(close) < period + 1:
            return None
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(period).mean()
        loss = (-delta.clip(upper=0)).rolling(period).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        val = rsi.iloc[-1]
        return float(val) if pd.notna(val) else None
    except Exception:
        return None


def _calc_obv_with_price(close: pd.Series, volume: pd.Series) -> tuple:
    """
    OBV 계산 + 가격 방향 분석
    Returns: (obv_current: int, obv_trend: str, price_trend: str)
    
    설계서 4.1: "OBV 우상향 + 가격 보합 = 기관 매집 신호"
    → OBV 방향과 가격 방향을 독립적으로 판단하여 결합 점수 산출
    """
    try:
        obv = (np.sign(close.diff()) * volume).fillna(0).cumsum()
        obv_current = int(obv.iloc[-1]) if len(obv) > 0 else 0

        if len(obv) < 20:
            return obv_current, "FLAT", "FLAT"

        # OBV 추세: 최근 20일 시작 vs 끝
        obv_20d_start = float(obv.iloc[-20])
        obv_20d_end = float(obv.iloc[-1])
        obv_delta = obv_20d_end - obv_20d_start

        # OBV 변화율이 의미 있는 수준인지 판단 (절대값 기준)
        if obv_delta > 0:
            obv_trend = "UP"
        elif obv_delta < 0:
            obv_trend = "DOWN"
        else:
            obv_trend = "FLAT"

        # 가격 추세: 최근 20일 기준 ±2% 이상 변동만 방향성 있음
        price_start = float(close.iloc[-20])
        price_end = float(close.iloc[-1])
        if price_start == 0:
            price_trend = "FLAT"
        else:
            pct_change = (price_end - price_start) / price_start
            if pct_change > 0.02:
                price_trend = "UP"
            elif pct_change < -0.02:
                price_trend = "DOWN"
            else:
                price_trend = "FLAT"

        return obv_current, obv_trend, price_trend

    except Exception:
        return 0, "FLAT", "FLAT"


def _get_spy_momentum() -> tuple:
    """
    SPY의 12-1 모멘텀 계산 (모든 종목에 공통 사용)
    Returns: (spy_12m_ret, spy_1m_ret) or (None, None)
    
    설계서: "52주 수익률 - SPY 수익률" → 상대 모멘텀
    """
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT stock_id FROM stocks
                WHERE ticker = 'SPY' AND is_active = TRUE
                LIMIT 1
            """)
            row = cur.fetchone()
            if not row:
                return None, None

            spy_id = row["stock_id"]
            cur.execute("""
                SELECT trade_date, close_price
                FROM stock_prices_daily
                WHERE stock_id = %s AND volume > 0
                ORDER BY trade_date DESC
                LIMIT 260
            """, (spy_id,))
            rows = [dict(r) for r in cur.fetchall()]

        if not rows or len(rows) < 22:
            return None, None

        rows.sort(key=lambda x: x["trade_date"])
        closes = [float(r["close_price"]) for r in rows if r["close_price"]]

        if len(closes) < 22:
            return None, None

        spy_now = closes[-1]

        # 1개월(≈21 거래일) 전
        spy_1m = closes[-min(22, len(closes))]
        spy_ret_1m = (spy_now - spy_1m) / spy_1m if spy_1m != 0 else 0

        # 12개월(≈252 거래일) 전 — 데이터가 252일 미만이면 가용 범위의 가장 오래된 것
        spy_12m = closes[0]
        spy_ret_12m = (spy_now - spy_12m) / spy_12m if spy_12m != 0 else 0

        return spy_ret_12m, spy_ret_1m

    except Exception:
        return None, None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 설계서 4.1 기준 — 구간별 점수 함수 (0점 시작 → 가산)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _score_relative_momentum(rel_mom_pct: float | None) -> float:
    """
    ① Relative Momentum 12-1 (만점: 30)
    
    설계서: "52주 수익률 - SPY 수익률"
    DDL:    "0~30 (≥30%→45pt, ≥20%→35pt, ≥10%→25pt)"
    
    설계서 raw(0~45)를 30점 만점으로 비례 매핑:
      ≥30% → 30.0    (raw 45 → 45/45 × 30)
      ≥20% → 23.3    (raw 35 → 35/45 × 30)
      ≥10% → 16.7    (raw 25 → 25/45 × 30)
      ≥ 0% → 10.0    (raw 15 → 15/45 × 30)
      ≥-10%→  3.3    (raw  5 →  5/45 × 30)
      <-10%→  0.0
    """
    if rel_mom_pct is None:
        return 0.0
    if rel_mom_pct >= 30:   return 30.0
    if rel_mom_pct >= 20:   return 23.3
    if rel_mom_pct >= 10:   return 16.7
    if rel_mom_pct >= 0:    return 10.0
    if rel_mom_pct >= -10:  return 3.3
    return 0.0


def _score_52w_high(position_ratio: float | None) -> float:
    """
    ② 52W High Position (만점: 20)
    
    설계서: "현재가 ÷ 52주 고점. ≥95% 강세 / <55% 하락추세"
    DDL:    "0~20"
    
      ≥95% → 20
      ≥85% → 15
      ≥75% → 10
      ≥65% →  5
      <65% →  0  (설계서 "<55% 하락추세" → 0점)
    """
    if position_ratio is None:
        return 0.0
    if position_ratio >= 0.95:  return 20.0
    if position_ratio >= 0.85:  return 15.0
    if position_ratio >= 0.75:  return 10.0
    if position_ratio >= 0.65:  return 5.0
    return 0.0


def _score_trend_r2(r2: float | None, slope: float | None) -> float:
    """
    ③ Trend Stability R² (만점: 15)
    
    설계서: "90일 회귀분석 R². 상승 기울기 + R²≥0.7: 추세 매우 안정. 기관 매집 신호."
    DDL:    "0~15"
    
      R²≥0.7 + 기울기>0 → 15  (★기관매집, 설계서 핵심)
      R²≥0.7 + 기울기≤0 → 10  (안정적이나 하락 추세)
      R²≥0.5             → 10
      R²≥0.3             →  5
      R²<0.3             →  0  (추세 없음, 무방향)
    """
    if r2 is None:
        return 0.0
    if r2 >= 0.7:
        if slope is not None and slope > 0:
            return 15.0     # 상승 추세 + 높은 안정성 = 기관 매집 신호
        return 10.0         # 안정적이지만 하락/횡보
    if r2 >= 0.5:
        return 10.0
    if r2 >= 0.3:
        return 5.0
    return 0.0


def _score_rsi(rsi14: float | None) -> float:
    """
    ④ RSI 14일 (만점: 15)
    
    설계서: "<20: 극단 과매도(반등 매수 타이밍) / >80: 극단 과매수(차익실현 고려). 역추세 진입 탐지."
    DDL:    "0~15"
    
    핵심: 과매도 = 반등 가점 (Mean-Reversion 전략)
    
      40~60  → 15  (중립 강세, 가장 안전한 구간)
      60~70  → 10  (강세)
      <20    → 12  (극단 과매도 → 반등 매수 타이밍, 설계서 핵심!)
      20~30  → 12  (과매도 → 반등 가능)
      30~40  →  8  (약한 과매도 접근)
      70~80  →  5  (과매수 주의)
      >80    →  0  (극단 과매수 → 차익실현)
    """
    if rsi14 is None:
        return 0.0
    if 40 <= rsi14 <= 60:   return 15.0
    if 60 < rsi14 <= 70:    return 10.0
    if rsi14 < 20:          return 12.0   # 극단 과매도 반등
    if 20 <= rsi14 < 30:    return 12.0   # 과매도 반등
    if 30 <= rsi14 < 40:    return 8.0
    if 70 < rsi14 <= 80:    return 5.0
    return 0.0                             # >80 극단 과매수


def _score_obv(obv_trend: str, price_trend: str) -> float:
    """
    ⑤ OBV (만점: 10)
    
    설계서: "OBV 우상향 + 가격 보합 = 기관 매집 신호. 발산(Divergence) 시 전환 경보."
    DDL:    "0~10"
    
      OBV↑ + 가격↑    → 10  (정상 상승 추세)
      OBV↑ + 가격보합  →  8  (★기관매집, 설계서 핵심!)
      OBV↑ + 가격↓    →  6  (긍정 다이버전스: 곧 반전 가능)
      OBV FLAT         →  4  (중립)
      OBV↓ + 가격보합  →  1  (약한 매도 압력)
      OBV↓ + 가격↑    →  2  (부정 다이버전스: 상승 약화 경고)
      OBV↓ + 가격↓    →  0  (매도 압력 집중)
    """
    if obv_trend == "UP":
        if price_trend == "UP":     return 10.0
        if price_trend == "FLAT":   return 8.0    # 기관 매집
        if price_trend == "DOWN":   return 6.0    # 긍정 다이버전스
    if obv_trend == "FLAT":
        return 4.0
    # obv_trend == "DOWN"
    if price_trend == "UP":     return 2.0    # 부정 다이버전스
    if price_trend == "FLAT":   return 1.0
    return 0.0                                 # DOWN + DOWN


def _score_volume_surge(surge_ratio: float | None) -> float:
    """
    ⑥ Volume Surge (만점: 10)
    
    설계서: "20일 평균 대비 3배 이상 거래량 = 이상 거래 신호. 가격 방향성과 결합하여 강도 판단."
    DDL:    "0~10"
    
      ≥3.0배 → 10  (이상 거래: 주요 뉴스 또는 기관 대규모 진입)
      ≥2.0배 →  7
      ≥1.5배 →  4
      ≥1.0배 →  2
      <1.0배 →  0  (거래 침체)
    """
    if surge_ratio is None:
        return 0.0
    if surge_ratio >= 3.0:  return 10.0
    if surge_ratio >= 2.0:  return 7.0
    if surge_ratio >= 1.5:  return 4.0
    if surge_ratio >= 1.0:  return 2.0
    return 0.0


def _calc_layer3_total(
    mom_score: float, high52_score: float, trend_score: float,
    rsi_score: float, obv_score: float, vol_score: float
) -> float:
    """
    Layer 3 최종 점수 (0~100)
    설계서 4.1: 6개 지표 단순 합산
    30 + 20 + 15 + 15 + 10 + 10 = 100
    """
    total = mom_score + high52_score + trend_score + rsi_score + obv_score + vol_score
    return round(min(100.0, max(0.0, total)), 2)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 메인 실행
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run_technical_indicators(calc_date: date = None):
    """Layer 3 기술지표 배치잡 메인 함수"""

    if calc_date is None:
        calc_date = datetime.now().date()

    print(f"[L3-TECH] ▶ 시작 calc_date={calc_date}")

    # ── 전 종목 목록 ──
    stocks = []
    with get_cursor() as cur:
        cur.execute("""
            SELECT s.stock_id, s.ticker
            FROM stocks s
            WHERE s.is_active = TRUE
        """)
        stocks = [dict(r) for r in cur.fetchall()]

    print(f"[L3-TECH] 대상 종목: {len(stocks)}개")

    # ── SPY 모멘텀 사전 계산 (전 종목 공통) ──
    spy_ret_12m, spy_ret_1m = _get_spy_momentum()
    if spy_ret_12m is not None:
        spy_mom_12_1 = spy_ret_12m - spy_ret_1m
        print(f"[L3-TECH] SPY 12-1 Momentum: {spy_mom_12_1*100:.2f}%")
    else:
        spy_mom_12_1 = None
        print("[L3-TECH] ⚠ SPY 데이터 없음 → 절대 모멘텀으로 fallback")

    ok, fail = 0, 0

    for s in stocks:
        stock_id = s["stock_id"]
        ticker = s["ticker"]

        try:
            # ── 가격 데이터 조회 (최근 300일) ──
            with get_cursor() as cur:
                cur.execute("""
                    SELECT trade_date, open_price, high_price,
                           low_price, close_price, volume
                    FROM stock_prices_daily
                    WHERE stock_id = %s
                    ORDER BY trade_date DESC
                    LIMIT 300
                """, (stock_id,))
                price_rows = [dict(r) for r in cur.fetchall()]

            if not price_rows or len(price_rows) < 30:
                fail += 1
                continue

            df = pd.DataFrame(price_rows).sort_values("trade_date").reset_index(drop=True)
            close = df["close_price"].apply(_f).astype(float)
            volume = df["volume"].apply(lambda x: float(x) if x else 0.0).astype(float)
            high = df["high_price"].apply(_f).astype(float)

            # ─────────────────────────────────────────────
            # ★ 핵심: volume=0 미완결 행(장 시작 전) 제거
            #   배치 실행 시점(03:30)에 당일 행이 있으면
            #   volume=0이므로 모든 volume 관련 지표가 왜곡됨
            # ─────────────────────────────────────────────
            while len(close) > 30 and volume.iloc[-1] <= 0:
                close = close.iloc[:-1]
                volume = volume.iloc[:-1]
                high = high.iloc[:-1]
                df = df.iloc[:-1]

            if len(close) < 30:
                fail += 1
                continue

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 원시값(raw) 계산
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

            cur_close = float(close.iloc[-1])

            # --- MA (보조지표용) ---
            ma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None
            ma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None
            golden = bool(ma50 > ma200) if (ma50 is not None and ma200 is not None) else None
            death = bool(ma50 < ma200) if (ma50 is not None and ma200 is not None) else None

            # --- ④ RSI 14 ---
            rsi14 = _calc_rsi(close, 14)

            # --- ⑤ OBV + 가격 연동 ---
            obv_current, obv_trend, price_trend = _calc_obv_with_price(close, volume)

            # --- ② 52주 고점 대비 ---
            n52 = min(252, len(high))
            high52 = float(high.tail(n52).max())
            dist52 = round(cur_close / high52, 4) if high52 > 0 else None

            # --- ① Relative Momentum 12-1 (vs SPY) ---
            rel_mom_raw = None         # 절대 모멘텀 (DB 저장용)
            rel_mom_vs_spy = None      # SPY 대비 상대 (점수 계산용)

            if len(close) >= 252:
                c_now = float(close.iloc[-1])
                c_12m = float(close.iloc[-252])
                c_1m = float(close.iloc[-21]) if len(close) >= 21 else c_now

                if c_12m != 0 and c_1m != 0:
                    stock_ret_12m = (c_now - c_12m) / c_12m
                    stock_ret_1m = (c_now - c_1m) / c_1m
                    stock_mom_12_1 = stock_ret_12m - stock_ret_1m

                    # SPY 대비 상대 모멘텀
                    if spy_mom_12_1 is not None:
                        rel_mom_vs_spy = round((stock_mom_12_1 - spy_mom_12_1) * 100, 4)
                    else:
                        rel_mom_vs_spy = round(stock_mom_12_1 * 100, 4)  # fallback: 절대

                    rel_mom_raw = round(stock_mom_12_1 * 100, 4)

            # --- ③ Trend R² + Slope (90일 선형회귀) ---
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
                    if ss_tot > 0:
                        trend_r2 = round(1 - ss_res / ss_tot, 4)
                except Exception:
                    pass

            # --- ⑥ Volume Surge ---
            vol_20d_avg = None
            vol_surge_ratio = None

            valid_vol = volume[volume > 0]
            if len(valid_vol) >= 21:
                # 가장 최근 완결일 거래량 vs 직전 20일 평균
                cur_vol = float(valid_vol.iloc[-1])
                avg20 = float(valid_vol.iloc[-21:-1].mean())
                if avg20 > 0:
                    vol_20d_avg = int(avg20)
                    vol_surge_ratio = round(cur_vol / avg20, 2)
            elif len(valid_vol) >= 2:
                cur_vol = float(valid_vol.iloc[-1])
                avg_prev = float(valid_vol.iloc[:-1].mean())
                if avg_prev > 0:
                    vol_20d_avg = int(avg_prev)
                    vol_surge_ratio = round(cur_vol / avg_prev, 2)

            # --- VWAP (일봉 근사: (H+L+C)/3) ---
            vwap = None
            last = df.iloc[-1]
            h_val, l_val, c_val = _f(last["high_price"]), _f(last["low_price"]), _f(last["close_price"])
            if all(v is not None for v in [h_val, l_val, c_val]):
                vwap = round((h_val + l_val + c_val) / 3, 4)

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 구간별 점수 계산 (설계서 4.1 기준)
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

            s_mom = _score_relative_momentum(rel_mom_vs_spy)
            s_52w = _score_52w_high(dist52)
            s_r2 = _score_trend_r2(trend_r2, trend_slope)
            s_rsi = _score_rsi(rsi14)
            s_obv = _score_obv(obv_trend, price_trend)
            s_vol = _score_volume_surge(vol_surge_ratio)

            l3_total = _calc_layer3_total(s_mom, s_52w, s_r2, s_rsi, s_obv, s_vol)

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # DB 저장 — DDL 24개 컬럼 전체 매핑
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
                        -- 최종
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
                    _f(rel_mom_vs_spy), _f(s_mom),
                    # ② 52W High
                    _f(high52), _f(dist52), _f(s_52w),
                    # ③ Trend R²
                    _f(trend_r2), _f(trend_slope), _f(s_r2),
                    # ④ RSI
                    _f(rsi14), _f(s_rsi),
                    # ⑤ OBV
                    obv_current, obv_trend, _f(s_obv),
                    # ⑥ Volume Surge
                    vol_20d_avg, _f(vol_surge_ratio), _f(s_vol),
                    # 보조
                    golden, death, _f(ma50), _f(ma200), _f(vwap),
                    # 최종
                    _f(l3_total),
                ))

            ok += 1
            if ok % 50 == 0 or ok <= 5:
                print(
                    f"[L3-TECH] {ticker:6s} L3={l3_total:5.1f} "
                    f"(Mom={s_mom:4.1f} 52W={s_52w:4.1f} R²={s_r2:4.1f} "
                    f"RSI={s_rsi:4.1f} OBV={s_obv:4.1f} Vol={s_vol:4.1f})"
                )

        except Exception as e:
            fail += 1
            print(f"[L3-TECH] {ticker} 실패: {e}")

    print(f"[L3-TECH] ■ 완료: {ok}성공 / {fail}실패")
    return ok, fail


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 직접 실행
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    from db_pool import init_pool
    init_pool()
    run_technical_indicators()
