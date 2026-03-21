"""
utils/layer3_scoring.py — Layer 3 기술 지표 스코어링 v3.1
=========================================================
배점: Mom(25) + 52W(20) + STR(15) + RSI(20) + Vol(20) = 100
자체 내장: sigmoid_score, _clamp (외부 의존 없음)
"""
import numpy as np


def _clamp(v, lo, hi):
    return float(max(lo, min(hi, v)))


def sigmoid_score(value, mid=50.0, k=0.1, out_min=0.0, out_max=100.0):
    """범용 Sigmoid (Layer 3 전용)"""
    if value is None:
        return out_min
    z = k * (float(value) - mid)
    z = _clamp(z, -20.0, 20.0)
    sig = 1.0 / (1.0 + np.exp(-z))
    return float(round(out_min + (out_max - out_min) * sig, 2))


def score_relative_momentum(rel_mom_pct):
    if rel_mom_pct is None: return 0.0
    return sigmoid_score(rel_mom_pct, mid=8.0, k=0.12, out_min=0.0, out_max=25.0)

def score_52w_high(dist52):
    if dist52 is None: return 0.0
    return sigmoid_score(dist52, mid=0.85, k=15.0, out_min=0.0, out_max=20.0)

def score_short_term_reversal(ret_1m_pct):
    if ret_1m_pct is None: return 0.0
    return sigmoid_score(-float(ret_1m_pct), mid=5.0, k=0.12, out_min=0.0, out_max=15.0)

def score_rsi(rsi14):
    if rsi14 is None: return 0.0
    r = float(rsi14)
    gaussian = float(np.exp(-0.5 * ((r - 50) / 20) ** 2))
    base = gaussian * 20.0
    if r < 30:
        base = max(base, 10.0 + (30 - r) / 30 * 5.0)
    if r > 75:
        base -= (r - 75) / 25 * base * 0.8
    return _clamp(round(base, 2), 0.0, 20.0)

def score_volume_surge(surge_ratio, rsi14=None):
    if surge_ratio is None: return 0.0
    base = sigmoid_score(float(surge_ratio), mid=1.5, k=2.0, out_min=0.0, out_max=20.0)
    if rsi14 is not None and float(surge_ratio) > 2.0:
        r = float(rsi14)
        if r < 25:    base *= 0.5
        elif r > 75:  base *= 0.6
    return _clamp(round(base, 2), 0.0, 20.0)


def calc_layer3_score(
    rel_mom_pct=None, dist52=None, ret_1m_pct=None, rsi14=None, surge_ratio=None,
    trend_r2=None, trend_slope=None, obv_trend=None, price_trend=None,
    vol_surge_ratio=None, **kwargs,
):
    """Layer 3 통합 점수. 하위호환 파라미터도 수용."""
    if surge_ratio is None and vol_surge_ratio is not None:
        surge_ratio = vol_surge_ratio
    mom_s = score_relative_momentum(rel_mom_pct)
    h52_s = score_52w_high(dist52)
    str_s = score_short_term_reversal(ret_1m_pct)
    rsi_s = score_rsi(rsi14)
    vol_s = score_volume_surge(surge_ratio, rsi14)
    total = _clamp(round(mom_s + h52_s + str_s + rsi_s + vol_s, 2), 0.0, 100.0)
    return {
        "relative_momentum_score": round(mom_s, 2),
        "high_52w_score": round(h52_s, 2),
        "reversal_score": round(str_s, 2),
        "rsi_score": round(rsi_s, 2),
        "volume_surge_score": round(vol_s, 2),
        "layer3_technical_score": total,
        "trend_stability_score": 0.0,
        "obv_score": 0.0,
    }

# Deprecated
def score_trend_r2(r2=None, slope=None): return 0.0
def score_obv(obv_trend=None, price_trend=None): return 0.0