"""
data_quality.py — QUANT AI v3.0 Data Quality & Integrity Engine
================================================================
v1~v2 문제:
  1. 이상치 데이터가 그대로 점수에 반영 (YoY +5000% 같은 오류)
  2. 데이터 결측 시 50점 기본값으로 왜곡
  3. Look-ahead bias 방지 메커니즘 없음

v3 해결:
  1. IQR + Z-score 이상치 자동 탐지/플래그
  2. Winsorization (극단값 클리핑)
  3. Point-in-Time 데이터 사용 검증
  4. Cross-validation (EPS ↔ Revenue 일관성)
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from datetime import date, datetime


# ═══════════════════════════════════════════════════════════
# §1. Quality Flags
# ═══════════════════════════════════════════════════════════

@dataclass
class QualityFlag:
    """데이터 품질 문제 하나"""
    ticker: str
    field: str
    value: float
    issue: str       # OUTLIER, YOY_SPIKE, CROSS_CHECK, MISSING, STALE, LOOKAHEAD
    severity: str    # INFO, WARNING, ERROR, CRITICAL
    detail: str = ""
    action: str = "" # WINSORIZE, EXCLUDE, FLAG_ONLY, USE_PREV


@dataclass
class QualityReport:
    """종목별 품질 리포트"""
    ticker: str
    total_flags: int = 0
    critical_count: int = 0
    error_count: int = 0
    warning_count: int = 0
    flags: List[QualityFlag] = field(default_factory=list)
    
    is_usable: bool = True          # 점수 계산에 사용 가능?
    confidence_penalty: float = 0.0  # 0~1 (1이면 완전 불신)
    
    @property
    def confidence(self) -> float:
        """데이터 신뢰도 0~1"""
        return max(0.0, 1.0 - self.confidence_penalty)


# ═══════════════════════════════════════════════════════════
# §2. Outlier Detection
# ═══════════════════════════════════════════════════════════

class OutlierDetector:
    """
    IQR + Modified Z-Score 기반 이상치 탐지
    
    두 가지 방법 AND 조합:
    - IQR: Q1 - k×IQR ~ Q3 + k×IQR (k=3 for loose, k=1.5 for strict)
    - Modified Z-Score: |0.6745*(x - median)| / MAD > threshold
    
    AND 조합 = 둘 다 이상치일 때만 플래그 → 거짓 양성 최소화
    """
    
    def __init__(self, iqr_factor: float = 3.0, zscore_threshold: float = 3.5):
        self.iqr_factor = iqr_factor
        self.zscore_threshold = zscore_threshold
    
    def detect(self, values: np.ndarray, labels: List[str] = None) -> List[int]:
        """
        이상치 인덱스 반환
        
        Parameters
        ----------
        values : 1D array of float
        labels : 대응하는 종목 레이블 (optional)
        
        Returns
        -------
        list of indices that are outliers
        """
        if len(values) < 10:
            return []  # 샘플 부족
        
        clean = values[~np.isnan(values)]
        if len(clean) < 10:
            return []
        
        # IQR method
        q1, q3 = np.percentile(clean, [25, 75])
        iqr = q3 - q1
        lower_iqr = q1 - self.iqr_factor * iqr
        upper_iqr = q3 + self.iqr_factor * iqr
        
        # Modified Z-Score
        median = np.median(clean)
        mad = np.median(np.abs(clean - median))
        if mad == 0:
            mad = np.std(clean) * 0.6745  # fallback
        
        outliers = []
        for i, v in enumerate(values):
            if np.isnan(v):
                continue
            
            iqr_flag = (v < lower_iqr or v > upper_iqr)
            
            mod_z = 0.6745 * abs(v - median) / mad if mad > 0 else 0
            z_flag = mod_z > self.zscore_threshold
            
            if iqr_flag and z_flag:  # AND = 보수적
                outliers.append(i)
        
        return outliers


# ═══════════════════════════════════════════════════════════
# §3. Winsorization
# ═══════════════════════════════════════════════════════════

def winsorize(values: np.ndarray, lower_pct: float = 1.0, upper_pct: float = 99.0) -> np.ndarray:
    """
    극단값 클리핑 (Winsorization)
    
    1st ~ 99th percentile 범위로 클리핑
    → 이상치의 영향을 제한하되 완전히 제거하지는 않음
    """
    result = values.copy()
    valid = result[~np.isnan(result)]
    
    if len(valid) < 5:
        return result
    
    lo, hi = np.percentile(valid, [lower_pct, upper_pct])
    result = np.where(np.isnan(result), result, np.clip(result, lo, hi))
    
    return result


# ═══════════════════════════════════════════════════════════
# §4. YoY Consistency Check
# ═══════════════════════════════════════════════════════════

def check_yoy_consistency(
    current: Dict[str, float],
    previous: Dict[str, float],
    ticker: str = ""
) -> List[QualityFlag]:
    """
    전년 대비 급변 감지
    
    Rules:
    - Revenue ±500% → ERROR
    - EPS ±1000% → ERROR  
    - Total Assets ±300% → ERROR
    - Net Income sign flip (대규모) → WARNING
    """
    flags = []
    
    checks = [
        ("revenue", 5.0, "ERROR"),
        ("net_income", 10.0, "WARNING"),
        ("eps_diluted", 10.0, "ERROR"),
        ("total_assets", 3.0, "ERROR"),
        ("operating_income", 10.0, "WARNING"),
        ("free_cash_flow", 10.0, "WARNING"),
    ]
    
    for field, max_change, severity in checks:
        cur = current.get(field)
        prev = previous.get(field)
        
        if cur is None or prev is None:
            continue
        
        cur, prev = float(cur), float(prev)
        
        if abs(prev) < 1e-6:
            continue
        
        yoy = (cur - prev) / abs(prev)
        
        if abs(yoy) > max_change:
            flags.append(QualityFlag(
                ticker=ticker,
                field=field,
                value=cur,
                issue="YOY_SPIKE",
                severity=severity,
                detail=f"YoY {yoy*100:+.0f}% (prev={prev:,.0f})",
                action="WINSORIZE" if severity == "ERROR" else "FLAG_ONLY"
            ))
    
    # Cross-check: Revenue↑ but EPS↓ sharply (or vice versa)
    rev_cur, rev_prev = current.get("revenue"), previous.get("revenue")
    eps_cur, eps_prev = current.get("eps_diluted"), previous.get("eps_diluted")
    
    if all(v is not None for v in [rev_cur, rev_prev, eps_cur, eps_prev]):
        rev_cur, rev_prev = float(rev_cur), float(rev_prev)
        eps_cur, eps_prev = float(eps_cur), float(eps_prev)
        
        if abs(rev_prev) > 0 and abs(eps_prev) > 0:
            rev_chg = (rev_cur - rev_prev) / abs(rev_prev)
            eps_chg = (eps_cur - eps_prev) / abs(eps_prev)
            
            # Revenue +20% 이상인데 EPS -30% 이하 → 비용 급증 or 데이터 오류
            if rev_chg > 0.2 and eps_chg < -0.3:
                flags.append(QualityFlag(
                    ticker=ticker,
                    field="cross_check_rev_eps",
                    value=0,
                    issue="CROSS_CHECK",
                    severity="WARNING",
                    detail=f"Revenue +{rev_chg*100:.0f}% but EPS {eps_chg*100:.0f}%",
                    action="FLAG_ONLY"
                ))
    
    return flags


# ═══════════════════════════════════════════════════════════
# §5. Staleness Check
# ═══════════════════════════════════════════════════════════

def check_data_staleness(
    last_financial_date: date,
    last_price_date: date,
    current_date: date = None,
    ticker: str = ""
) -> List[QualityFlag]:
    """
    데이터 신선도 검증
    
    - 재무데이터: 최근 발표일로부터 120일 이상이면 STALE
    - 주가데이터: 3일 이상 안 들어오면 WARNING
    """
    if current_date is None:
        current_date = date.today()
    
    flags = []
    
    if last_financial_date:
        days_old = (current_date - last_financial_date).days
        if days_old > 180:
            flags.append(QualityFlag(
                ticker=ticker,
                field="financial_date",
                value=days_old,
                issue="STALE",
                severity="ERROR",
                detail=f"재무데이터 {days_old}일 경과 (마지막: {last_financial_date})",
                action="EXCLUDE"
            ))
        elif days_old > 120:
            flags.append(QualityFlag(
                ticker=ticker,
                field="financial_date",
                value=days_old,
                issue="STALE",
                severity="WARNING",
                detail=f"재무데이터 {days_old}일 경과",
                action="FLAG_ONLY"
            ))
    
    if last_price_date:
        days_old = (current_date - last_price_date).days
        if days_old > 5:  # 영업일 기준 ~3일
            flags.append(QualityFlag(
                ticker=ticker,
                field="price_date",
                value=days_old,
                issue="STALE",
                severity="WARNING",
                detail=f"주가 {days_old}일 미갱신",
                action="FLAG_ONLY"
            ))
    
    return flags


# ═══════════════════════════════════════════════════════════
# §6. Look-Ahead Bias Prevention
# ═══════════════════════════════════════════════════════════

def validate_point_in_time(
    financial_period_end: date,
    financial_filing_date: date,
    calc_date: date,
    ticker: str = ""
) -> List[QualityFlag]:
    """
    Look-Ahead Bias 방지
    
    재무제표 사용 조건:
    - filing_date <= calc_date (발표 후에만 사용)
    - period_end < calc_date (미래 실적 사용 금지)
    
    Examples
    --------
    2024-Q4 결산 (period_end=2024-12-31, filing=2025-02-15)
    → calc_date=2025-01-15 이면 사용 불가 (아직 발표 안됨)
    → calc_date=2025-02-20 이면 사용 가능
    """
    flags = []
    
    if financial_filing_date and calc_date:
        if financial_filing_date > calc_date:
            flags.append(QualityFlag(
                ticker=ticker,
                field="filing_date",
                value=0,
                issue="LOOKAHEAD",
                severity="CRITICAL",
                detail=f"Filing {financial_filing_date} > calc {calc_date}",
                action="EXCLUDE"
            ))
    
    if financial_period_end and calc_date:
        if financial_period_end >= calc_date:
            flags.append(QualityFlag(
                ticker=ticker,
                field="period_end",
                value=0,
                issue="LOOKAHEAD",
                severity="CRITICAL",
                detail=f"Period end {financial_period_end} >= calc {calc_date}",
                action="EXCLUDE"
            ))
    
    return flags


# ═══════════════════════════════════════════════════════════
# §7. Master Quality Gate
# ═══════════════════════════════════════════════════════════

class DataQualityGate:
    """
    종합 품질 게이트: 모든 검증을 실행하고 최종 판정
    
    Usage
    -----
    gate = DataQualityGate()
    report = gate.run_all_checks(ticker, current, previous, sector_stats, dates)
    
    if report.is_usable:
        score = compute_score(data, confidence=report.confidence)
    else:
        skip this ticker
    """
    
    def __init__(self):
        self.outlier_detector = OutlierDetector(iqr_factor=3.0, zscore_threshold=3.5)
    
    def run_all_checks(
        self,
        ticker: str,
        current: dict,
        previous: dict = None,
        sector_values: dict = None,  # {field: np.array}
        dates: dict = None,           # last_financial_date, last_price_date, etc.
    ) -> QualityReport:
        """모든 품질 검증 실행"""
        report = QualityReport(ticker=ticker)
        
        # 1. 결측 필드 확인
        critical_fields = ["roic", "ev_ebit", "fcf_margin", "eps_diluted", "revenue"]
        for field in critical_fields:
            if current.get(field) is None:
                report.flags.append(QualityFlag(
                    ticker=ticker, field=field, value=0,
                    issue="MISSING", severity="WARNING",
                    detail=f"핵심 지표 {field} 누락",
                    action="FLAG_ONLY"
                ))
        
        # 2. YoY 일관성
        if previous:
            yoy_flags = check_yoy_consistency(current, previous, ticker)
            report.flags.extend(yoy_flags)
        
        # 3. 섹터 내 이상치
        if sector_values:
            for field, values in sector_values.items():
                cur_val = current.get(field)
                if cur_val is not None:
                    all_vals = np.append(values, float(cur_val))
                    outlier_idx = self.outlier_detector.detect(all_vals)
                    if len(all_vals) - 1 in outlier_idx:  # 현재 종목이 이상치
                        report.flags.append(QualityFlag(
                            ticker=ticker, field=field, value=float(cur_val),
                            issue="OUTLIER", severity="WARNING",
                            detail=f"섹터 내 이상치 (IQR+MZS 탐지)",
                            action="WINSORIZE"
                        ))
        
        # 4. 데이터 신선도
        if dates:
            stale_flags = check_data_staleness(
                dates.get("last_financial_date"),
                dates.get("last_price_date"),
                dates.get("calc_date"),
                ticker
            )
            report.flags.extend(stale_flags)
        
        # 5. Look-Ahead Bias
        if dates:
            pit_flags = validate_point_in_time(
                dates.get("period_end"),
                dates.get("filing_date"),
                dates.get("calc_date"),
                ticker
            )
            report.flags.extend(pit_flags)
        
        # ── 최종 판정 ──
        for flag in report.flags:
            if flag.severity == "CRITICAL":
                report.critical_count += 1
            elif flag.severity == "ERROR":
                report.error_count += 1
            elif flag.severity == "WARNING":
                report.warning_count += 1
        
        report.total_flags = len(report.flags)
        
        # Confidence penalty 계산
        report.confidence_penalty = (
            report.critical_count * 0.5 +
            report.error_count * 0.15 +
            report.warning_count * 0.03
        )
        report.confidence_penalty = min(1.0, report.confidence_penalty)
        
        # 사용 가능 여부
        if report.critical_count > 0:
            report.is_usable = False
        elif report.error_count >= 3:
            report.is_usable = False
        
        return report
