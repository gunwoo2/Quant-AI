"""
analytics/ — 분석/검증 엔진
===========================
Decision Audit + Performance Attribution
+ Validation Engine + Backtest Engine + Data Quality (V2 통합)
"""
from analytics.decision_audit import DecisionAudit
from analytics.performance_attribution import PerformanceAttribution, AttributionReport

__all__ = [
    "DecisionAudit",
    "PerformanceAttribution", "AttributionReport",
]

# V2 모듈은 lazy import (무거운 의존성)
def get_validation_engine():
    from analytics.validation_engine import ValidationEngine
    return ValidationEngine

def get_backtest_engine():
    from analytics.backtest_engine import BacktestEngine
    return BacktestEngine

def get_data_quality():
    from analytics.data_quality import DataQualityChecker
    return DataQualityChecker
