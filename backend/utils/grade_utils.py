"""
grade_utils.py — 등급/시그널 변환 유틸리티
==========================================
DB CHECK 제약조건 (stock_final_scores_grade_check):
  허용 등급: S, A+, A, B+, B, C, D

v3.1 등급 체계:
  >= 90  →  S   (최상위, 전체 상위 ~5%)
  >= 80  →  A+  (우수)
  >= 70  →  A   (양호)
  >= 60  →  B+  (평균 이상)
  >= 50  →  B   (평균)
  >= 40  →  C   (평균 이하)
  < 40   →  D   (주의)
"""


# ── DB CHECK 허용 등급 (변경 시 DDL도 함께 수정 필요) ──
VALID_GRADES = {"S", "A+", "A", "B+", "B", "C", "D"}


def score_to_grade(score) -> str:
    """
    점수(0~100) → 등급 변환.
    DB CHECK 제약조건 위반 방지를 위해 VALID_GRADES 외 값은 반환하지 않음.
    """
    if score is None:
        return "C"
    s = float(score)
    if s >= 90:
        return "S"
    if s >= 80:
        return "A+"
    if s >= 70:
        return "A"
    if s >= 60:
        return "B+"
    if s >= 50:
        return "B"
    if s >= 40:
        return "C"
    return "D"


def score_to_signal(score) -> str:
    """점수(0~100) → 투자 시그널 변환."""
    if score is None:
        return "HOLD"
    s = float(score)
    if s >= 80:
        return "STRONG_BUY"
    if s >= 65:
        return "BUY"
    if s >= 45:
        return "HOLD"
    if s >= 30:
        return "SELL"
    return "STRONG_SELL"


def signal_to_opinion(signal: str) -> str:
    """시그널 → 한글 투자의견."""
    return {
        "STRONG_BUY":  "강력매수",
        "BUY":         "매수",
        "HOLD":        "보유",
        "SELL":        "매도",
        "STRONG_SELL": "강력매도",
    }.get(signal, "보유")
