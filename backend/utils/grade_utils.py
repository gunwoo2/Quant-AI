def score_to_grade(score: float) -> str:
    if score >= 80: return "S"
    if score >= 72: return "A+"
    if score >= 65: return "A"
    if score >= 55: return "B+"
    if score >= 45: return "B"
    if score >= 35: return "C"
    return "D"


def score_to_signal(score: float) -> str:
    if score >= 72: return "STRONG_BUY"
    if score >= 55: return "BUY"
    if score >= 45: return "HOLD"
    if score >= 35: return "SELL"
    return "STRONG_SELL"


def percentile_to_points(pct: float, max_points: float) -> float:
    """
    섹터 내 백분위 → 점수 변환 (설계서 2.1)
    Top 10% → 만점, Top 30% → 80%, Top 50% → 60%, Top 70% → 40%, Bottom 30% → 0
    """
    if pct >= 90:   return max_points
    if pct >= 70:   return round(max_points * 0.80, 2)
    if pct >= 50:   return round(max_points * 0.60, 2)
    if pct >= 30:   return round(max_points * 0.40, 2)
    return 0.0