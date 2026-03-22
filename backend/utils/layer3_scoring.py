"""
utils/layer3_scoring.py — Layer 3 기술 지표 스코어링 v3.3
=========================================================
v3.2 → v3.3:
  - MACD 스코어링 추가 (5점)
  - OBV 스코어링 실구현 (5점) — OBV-Price divergence + trend
  - Trend Stability 스코어링 실구현 (8점) — R² + Slope
  - 배점: Section A Technical = 55점 만점
    Mom(15) + 52W(10) + Trend(8) + RSI(7) + MACD(5) + OBV(5) + Vol(5) + Structural(5)
  - NaN/Inf 입력 방어 유지
"""
import numpy as np


def _safe_num(v):
    """NaN, Inf, 비숫자 → None 안전 변환"""
    if v is None:
        return None
    try:
        fv = float(v)
        if np.isnan(fv) or np.isinf(fv):
            return None
        return fv
    except (TypeError, ValueError):
        return None


def _clamp(v, lo, hi):
    return float(max(lo, min(hi, v)))


def sigmoid_score(value, mid=50.0, k=0.1, out_min=0.0, out_max=100.0):
    """범용 Sigmoid (Layer 3 전용)"""
    if value is None:
        return out_min
    try:
        fv = float(value)
        if np.isnan(fv) or np.isinf(fv):
            return out_min
    except (TypeError, ValueError):
        return out_min
    z = k * (fv - mid)
    z = _clamp(z, -20.0, 20.0)
    sig = 1.0 / (1.0 + np.exp(-z))
    return float(round(out_min + (out_max - out_min) * sig, 2))


# ═══════════════════════════════════════════════════════════
# 개별 스코어링 함수 (Section A: 55점 만점)
# ═══════════════════════════════════════════════════════════

def score_relative_momentum(rel_mom_pct):
    """상대 모멘텀 12-1 (0~15점)"""
    rel_mom_pct = _safe_num(rel_mom_pct)
    if rel_mom_pct is None:
        return 0.0
    return sigmoid_score(rel_mom_pct, mid=8.0, k=0.12, out_min=0.0, out_max=15.0)


def score_52w_high(dist52):
    """52주 고가 대비 위치 (0~10점). dist52 = current/52w_high (0~1)"""
    dist52 = _safe_num(dist52)
    if dist52 is None:
        return 0.0
    return sigmoid_score(dist52, mid=0.85, k=15.0, out_min=0.0, out_max=10.0)


def score_trend_stability(trend_r2=None, trend_slope=None, cur_price=None):
    """
    추세 안정성 (0~8점)
    - R² 높을수록 → 안정적 추세 → 높은 점수
    - slope>0 (상승추세) 일 때 보너스
    - slope 정규화: slope/price로 % 변환
    """
    r2 = _safe_num(trend_r2)
    slope = _safe_num(trend_slope)
    price = _safe_num(cur_price)

    if r2 is None:
        return 0.0

    # R² 기반 (0~6점): R²=0.7이상이면 높은 점수
    r2_score = sigmoid_score(r2, mid=0.5, k=8.0, out_min=0.0, out_max=6.0)

    # 방향성 보너스 (0~2점): slope>0 이면서 R² 높으면 보너스
    dir_bonus = 0.0
    if slope is not None and r2 > 0.3:
        # slope를 가격 대비 %로 정규화
        if price and price > 0:
            slope_pct = (slope / price) * 100  # 일일 % 변화
        else:
            slope_pct = slope * 0.01  # fallback

        if slope_pct > 0:
            dir_bonus = min(2.0, slope_pct * 10.0)  # 0.1%/day → 1점, 0.2%+ → 2점
        else:
            dir_bonus = max(-1.0, slope_pct * 5.0)  # 하락 추세는 감점 (최대 -1)

    return _clamp(round(r2_score + dir_bonus, 2), 0.0, 8.0)


def score_rsi(rsi14):
    """
    RSI (0~7점)
    - 50 근처 = 중립 (적정)
    - 30~50 (살짝 과매도) = 매수 기회 → 높은 점수
    - <20 극단 과매도 = 위험 감점
    - >75 과매수 = 감점
    """
    rsi14 = _safe_num(rsi14)
    if rsi14 is None:
        return 0.0
    r = rsi14
    # 가우시안: 45 근처가 최적 (약간 과매도가 매수 기회)
    gaussian = float(np.exp(-0.5 * ((r - 45) / 20) ** 2))
    base = gaussian * 7.0
    if r < 25:
        base = max(base, 3.5 + (25 - r) / 25 * 1.5)  # 과매도 반등 기대
    if r > 75:
        base -= (r - 75) / 25 * base * 0.8  # 과매수 감점
    if r < 15:
        base *= 0.5  # 극단 과매도 = 위험
    return _clamp(round(base, 2), 0.0, 7.0)


def score_macd(macd_line=None, macd_signal=None, macd_histogram=None,
               prev_histogram=None, cur_price=None):
    """
    MACD 스코어 (0~5점)
    
    3가지 신호를 복합 평가:
    1. Histogram 부호 (양수=강세, 음수=약세): 0~2점
    2. Histogram 방향 (증가=강세 강화, 감소=약화): 0~1.5점
    3. MACD-Signal 크로스오버 (골든크로스 근접): 0~1.5점
    
    모든 값은 가격 대비 정규화하여 종목간 비교 가능
    """
    macd_l = _safe_num(macd_line)
    macd_s = _safe_num(macd_signal)
    hist = _safe_num(macd_histogram)
    prev_hist = _safe_num(prev_histogram)
    price = _safe_num(cur_price)

    if hist is None:
        return 0.0

    # 가격 대비 정규화 (AAPL $200의 MACD 2.0 vs 소형주 $5의 MACD 0.1)
    norm = max(abs(price), 1.0) if price else 100.0
    hist_pct = (hist / norm) * 100  # % 단위

    score = 0.0

    # 1) Histogram 부호 (0~2점)
    # 양수 = 단기 > 장기 → 강세
    if hist_pct > 0:
        score += min(2.0, sigmoid_score(hist_pct, mid=0.1, k=15.0, out_min=0.0, out_max=2.0))
    else:
        # 음수지만 0에 가까우면 (약세 약화) 약간의 점수
        score += max(0.0, sigmoid_score(-hist_pct, mid=0.5, k=-10.0, out_min=0.0, out_max=0.8))

    # 2) Histogram 방향 변화 (0~1.5점)
    if prev_hist is not None:
        prev_pct = (prev_hist / norm) * 100
        delta = hist_pct - prev_pct  # 양수 = 강세 강화

        if delta > 0:
            # 히스토그램 증가 (약세→강세 전환 or 강세 강화)
            score += min(1.5, delta * 5.0)
        else:
            # 감소는 약간 감점만 (트렌드 약화)
            score += max(-0.5, delta * 2.0)

    # 3) 크로스오버 근접성 (0~1.5점)
    if macd_l is not None and macd_s is not None:
        gap_pct = ((macd_l - macd_s) / norm) * 100
        if gap_pct > 0:
            # MACD > Signal (강세 영역)
            score += min(1.5, sigmoid_score(gap_pct, mid=0.05, k=20.0, out_min=0.0, out_max=1.5))
        elif gap_pct > -0.1:
            # 곧 골든크로스 (약세→강세 전환 임박)
            score += 0.8  # 기대감 점수

    return _clamp(round(score, 2), 0.0, 5.0)


def score_obv(obv_trend=None, price_trend=None, obv_current=None, obv_ma20=None):
    """
    OBV 스코어 (0~5점)
    
    2가지 신호:
    1. OBV-Price Divergence (0~3점):
       - OBV↑ + Price↓ = 숨은 매수세 → 강한 매수 신호 (3점)
       - OBV↑ + Price↑ = 건강한 상승 (2점)
       - OBV↓ + Price↑ = 위험한 상승 (약세 다이버전스) (0점)
       - OBV↓ + Price↓ = 확인된 하락 (0.5점)
    2. OBV vs MA20 (0~2점):
       - OBV > MA20 → 거래량 흐름 강세
       - OBV < MA20 → 거래량 흐름 약세
    """
    score = 0.0

    # 1) OBV-Price Divergence
    if obv_trend is not None and price_trend is not None:
        obv_t = str(obv_trend).upper()
        price_t = str(price_trend).upper()

        if obv_t == "UP" and price_t == "DOWN":
            score += 3.0   # 강세 다이버전스 (최고 신호)
        elif obv_t == "UP" and price_t == "UP":
            score += 2.0   # 건강한 상승 추세
        elif obv_t == "UP" and price_t == "FLAT":
            score += 1.8   # 매수세 유입 중
        elif obv_t == "FLAT" and price_t in ("UP", "FLAT"):
            score += 1.2   # 중립
        elif obv_t == "FLAT" and price_t == "DOWN":
            score += 1.5   # 하락에도 매도세 없음
        elif obv_t == "DOWN" and price_t == "UP":
            score += 0.3   # 약세 다이버전스 (위험)
        elif obv_t == "DOWN" and price_t == "DOWN":
            score += 0.5   # 확인된 하락
        elif obv_t == "DOWN" and price_t == "FLAT":
            score += 0.5   # 매도세 유입

    # 2) OBV vs MA20
    obv_c = _safe_num(obv_current)
    obv_m = _safe_num(obv_ma20)
    if obv_c is not None and obv_m is not None and obv_m != 0:
        ratio = obv_c / abs(obv_m) if obv_m != 0 else 1.0
        if ratio > 1.05:
            score += min(2.0, (ratio - 1.0) * 10.0)  # 5%↑ → 0.5점, 20%↑ → 2점
        elif ratio > 0.95:
            score += 1.0  # 중립 범위
        else:
            score += max(0.0, ratio * 0.5)  # MA20 아래 = 약세

    return _clamp(round(score, 2), 0.0, 5.0)


def score_volume_surge(surge_ratio, rsi14=None):
    """거래량 급증 (0~5점)"""
    surge_ratio = _safe_num(surge_ratio)
    rsi14 = _safe_num(rsi14)
    if surge_ratio is None:
        return 0.0
    base = sigmoid_score(surge_ratio, mid=1.5, k=2.0, out_min=0.0, out_max=5.0)
    if rsi14 is not None and float(surge_ratio) > 2.0:
        r = float(rsi14)
        if r < 25:    base *= 0.5   # 과매도에서 거래량 급증 = 투매
        elif r > 75:  base *= 0.6   # 과매수에서 급증 = 과열
    return _clamp(round(base, 2), 0.0, 5.0)


def score_structural_signal(golden_cross=None, death_cross=None,
                            bb_squeeze=None, ma20_streak_days=None,
                            breakout_52w=None):
    """
    구조적 시그널 점수 (0~5점) — 보너스 성격
    - Golden Cross: +2점
    - Death Cross: -1점
    - BB Squeeze 해제: +1점
    - MA20 위 연속 5일+: +1점
    - 52주 신고가 돌파: +1점
    """
    score = 2.5  # 기본 중립

    if golden_cross is True:
        score += 2.0
    elif death_cross is True:
        score -= 1.5

    if bb_squeeze is True:
        score += 1.0  # 스퀴즈 = 큰 움직임 임박

    if ma20_streak_days is not None:
        days = _safe_num(ma20_streak_days)
        if days is not None:
            if days >= 5:
                score += min(1.0, days / 10.0)
            elif days <= -5:
                score -= min(1.0, abs(days) / 10.0)

    if breakout_52w is True:
        score += 1.0

    return _clamp(round(score, 2), 0.0, 5.0)


# ═══════════════════════════════════════════════════════════
# 통합 함수
# ═══════════════════════════════════════════════════════════

def calc_layer3_score(
    rel_mom_pct=None, dist52=None, ret_1m_pct=None, rsi14=None, surge_ratio=None,
    trend_r2=None, trend_slope=None, cur_price=None,
    obv_trend=None, price_trend=None, obv_current=None, obv_ma20=None,
    macd_line=None, macd_signal=None, macd_histogram=None, prev_histogram=None,
    golden_cross=None, death_cross=None, bb_squeeze=None,
    ma20_streak_days=None, breakout_52w=None,
    vol_surge_ratio=None, **kwargs,
):
    """
    Layer 3 Section A 통합 점수 (55점 만점)
    
    배점:
      Mom(15) + 52W(10) + Trend(8) + RSI(7) + MACD(5) + OBV(5) + Vol(5) = 55
    """
    if surge_ratio is None and vol_surge_ratio is not None:
        surge_ratio = vol_surge_ratio

    mom_s     = score_relative_momentum(rel_mom_pct)
    h52_s     = score_52w_high(dist52)
    trend_s   = score_trend_stability(trend_r2, trend_slope, cur_price)
    rsi_s     = score_rsi(rsi14)
    macd_s    = score_macd(macd_line, macd_signal, macd_histogram, prev_histogram, cur_price)
    obv_s     = score_obv(obv_trend, price_trend, obv_current, obv_ma20)
    vol_s     = score_volume_surge(surge_ratio, rsi14)

    # Section A total (55점 만점)
    section_a = _clamp(
        round(mom_s + h52_s + trend_s + rsi_s + macd_s + obv_s + vol_s, 2),
        0.0, 55.0
    )

    # 하위호환: reversal_score는 이제 trend_stability에 흡수
    # 0~100 정규화 점수도 제공 (final_score에서 사용)
    normalized_100 = round(section_a / 55.0 * 100.0, 2)

    return {
        "relative_momentum_score": round(mom_s, 2),
        "high_52w_score": round(h52_s, 2),
        "trend_stability_score": round(trend_s, 2),
        "rsi_score": round(rsi_s, 2),
        "macd_score": round(macd_s, 2),
        "obv_score": round(obv_s, 2),
        "volume_surge_score": round(vol_s, 2),
        "section_a_technical": round(section_a, 2),
        "layer3_technical_score": round(normalized_100, 2),  # 0~100 for final_score compat
        "reversal_score": 0.0,  # deprecated, kept for compat
    }