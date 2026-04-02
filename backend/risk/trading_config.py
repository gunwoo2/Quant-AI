"""
risk/trading_config.py — 국면별 동적 트레이딩 설정
=====================================================
국면(BULL/NEUTRAL/BEAR/CRISIS) + DD모드에 따라
모든 파라미터가 자동으로 전환됩니다.
"""
from dataclasses import dataclass, field
from typing import Dict, Optional


# ═══════════════════════════════════════════════════════════
#  국면별 파라미터 테이블
# ═══════════════════════════════════════════════════════════

REGIME_PARAMS = {
    "BULL": {
        "max_positions":       20,
        "max_position_pct":    0.10,
        "cash_minimum":        0.10,
        "buy_score_min":       58,
        "buy_l3_min":          45,
        "buy_rsi_max":         75,
        "stop_loss_atr_mult":  2.0,
        "trailing_stop_atr_mult": 3.0,
        "sector_max_pct":      0.35,
        "position_size_mult":  1.0,
        "rebalance_freq_days": 7,
        "min_holding_days":    5,
        "profit_take_pct":     0.30,
        "max_sector_names":    11,
        "correlation_max":     0.80,
        "turnover_budget_monthly": 0.30,
        # 블렌딩 비율 (RP / HK / Conv)
        "blend_rp": 0.30,
        "blend_hk": 0.40,
        "blend_conv": 0.30,
    },
    "NEUTRAL": {
        "max_positions":       15,
        "max_position_pct":    0.08,
        "cash_minimum":        0.20,
        "buy_score_min":       62,
        "buy_l3_min":          55,
        "buy_rsi_max":         70,
        "stop_loss_atr_mult":  1.8,
        "trailing_stop_atr_mult": 2.5,
        "sector_max_pct":      0.30,
        "position_size_mult":  0.80,
        "rebalance_freq_days": 7,
        "min_holding_days":    5,
        "profit_take_pct":     0.25,
        "max_sector_names":    8,
        "correlation_max":     0.75,
        "turnover_budget_monthly": 0.25,
        "blend_rp": 0.40,
        "blend_hk": 0.30,
        "blend_conv": 0.30,
    },
    "BEAR": {
        "max_positions":       10,
        "max_position_pct":    0.06,
        "cash_minimum":        0.35,
        "buy_score_min":       68,
        "buy_l3_min":          65,
        "buy_rsi_max":         65,
        "stop_loss_atr_mult":  1.5,
        "trailing_stop_atr_mult": 2.0,
        "sector_max_pct":      0.25,
        "position_size_mult":  0.50,
        "rebalance_freq_days": 3,
        "min_holding_days":    3,
        "profit_take_pct":     0.20,
        "max_sector_names":    5,
        "correlation_max":     0.65,
        "turnover_budget_monthly": 0.20,
        "blend_rp": 0.50,
        "blend_hk": 0.20,
        "blend_conv": 0.30,
    },
    "CRISIS": {
        "max_positions":       5,
        "max_position_pct":    0.04,
        "cash_minimum":        0.60,
        "buy_score_min":       72,
        "buy_l3_min":          75,
        "buy_rsi_max":         60,
        "stop_loss_atr_mult":  1.2,
        "trailing_stop_atr_mult": 1.5,
        "sector_max_pct":      0.20,
        "position_size_mult":  0.30,
        "rebalance_freq_days": 1,
        "min_holding_days":    1,
        "profit_take_pct":     0.15,
        "max_sector_names":    3,
        "correlation_max":     0.50,
        "turnover_budget_monthly": 0.50,
        "blend_rp": 0.70,
        "blend_hk": 0.10,
        "blend_conv": 0.20,
    },
}

# 등급별 확신도 배수
GRADE_CONVICTION = {
    "S+": 1.50, "S": 1.30, "A+": 1.20, "A": 1.10,
    "B+": 1.00, "B": 0.90, "C+": 0.80, "C": 0.70,
    "D+": 0.60, "D": 0.50, "F": 0.30,
}


# ═══════════════════════════════════════════════════════════
#  기본 Config (하위 호환)
# ═══════════════════════════════════════════════════════════

@dataclass
class TradingConfig:
    """고정 파라미터 (하위 호환용 — DynamicConfig 사용 권장)"""
    initial_capital: float = 100_000
    max_positions: int = 15
    max_position_pct: float = 0.08
    cash_minimum: float = 0.20
    buy_score_min: float = 70
    buy_l3_min: float = 55
    buy_rsi_max: float = 70
    stop_loss_atr_mult: float = 1.8
    trailing_stop_atr_mult: float = 2.5
    sector_max_pct: float = 0.30
    position_size_mult: float = 0.80
    sell_score_max: float = 40
    sell_consecutive_days: int = 3
    max_holding_days: int = 90
    min_return_for_hold: float = 0.05
    rebalance_freq_days: int = 7
    daily_loss_limit: float = -0.03
    weekly_loss_limit: float = -0.05
    monthly_loss_limit: float = -0.10

    def get_conviction_multiplier(self, grade: str) -> float:
        return GRADE_CONVICTION.get(grade, 1.0)


# ═══════════════════════════════════════════════════════════
#  Dynamic Config (국면+DD 자동 전환)
# ═══════════════════════════════════════════════════════════

@dataclass
class DynamicConfig(TradingConfig):
    """
    국면(regime) + DD모드에 따라 파라미터 자동 전환.

    사용법:
        cfg = DynamicConfig()
        cfg.apply_regime("BEAR")
        cfg.apply_dd_override("CAUTION")
    """
    regime: str = "NEUTRAL"
    dd_mode: str = "NORMAL"

    # 블렌딩 비율
    blend_rp: float = 0.40
    blend_hk: float = 0.30
    blend_conv: float = 0.30

    # 추가 파라미터
    min_holding_days: int = 5
    profit_take_pct: float = 0.25
    max_sector_names: int = 8
    correlation_max: float = 0.75
    turnover_budget_monthly: float = 0.25

    # DD 오버라이드 상태
    _dd_buy_allowed: bool = True
    _dd_force_reduce: bool = False
    _dd_position_mult_override: Optional[float] = None

    def apply_regime(self, regime: str):
        """국면에 따라 모든 파라미터 자동 설정"""
        self.regime = regime
        params = REGIME_PARAMS.get(regime, REGIME_PARAMS["NEUTRAL"])
        for key, value in params.items():
            if hasattr(self, key):
                setattr(self, key, value)

    def apply_dd_override(self, dd_mode: str):
        """DD 모드에 따라 추가 제한 적용"""
        self.dd_mode = dd_mode

        if dd_mode == "NORMAL":
            self._dd_buy_allowed = True
            self._dd_force_reduce = False
            self._dd_position_mult_override = None

        elif dd_mode == "CAUTION":
            self._dd_buy_allowed = True
            self.buy_score_min = min(self.buy_score_min + 2, 95)
            self.position_size_mult *= 0.8
            self.trailing_stop_atr_mult = max(self.trailing_stop_atr_mult - 0.3, 1.0)

        elif dd_mode == "WARNING":
            self._dd_buy_allowed = False
            self.position_size_mult *= 0.5
            self.cash_minimum = max(self.cash_minimum, 0.40)
            self.rebalance_freq_days = 1

        elif dd_mode == "DANGER":
            self._dd_buy_allowed = False
            self._dd_force_reduce = True
            self._dd_position_mult_override = 0.5
            self.cash_minimum = max(self.cash_minimum, 0.60)

        elif dd_mode == "EMERGENCY":
            self._dd_buy_allowed = False
            self._dd_force_reduce = True
            self._dd_position_mult_override = 0.0
            self.cash_minimum = 1.0

    @property
    def buy_allowed(self) -> bool:
        return self._dd_buy_allowed

    @property
    def force_reduce(self) -> bool:
        return self._dd_force_reduce

    @property
    def effective_position_mult(self) -> float:
        if self._dd_position_mult_override is not None:
            return self._dd_position_mult_override
        return self.position_size_mult

    def get_regime_multiplier(self) -> float:
        return {"BULL": 1.0, "NEUTRAL": 0.8, "BEAR": 0.5, "CRISIS": 0.3}.get(self.regime, 0.7)

    def summary(self) -> dict:
        return {
            "regime": self.regime,
            "dd_mode": self.dd_mode,
            "buy_allowed": self.buy_allowed,
            "max_positions": self.max_positions,
            "cash_minimum": f"{self.cash_minimum:.0%}",
            "buy_score_min": self.buy_score_min,
            "position_mult": f"{self.effective_position_mult:.2f}",
            "stop_loss_atr": self.stop_loss_atr_mult,
            "trailing_atr": self.trailing_stop_atr_mult,
            "blend": f"RP={self.blend_rp:.0%} HK={self.blend_hk:.0%} Conv={self.blend_conv:.0%}",
        }