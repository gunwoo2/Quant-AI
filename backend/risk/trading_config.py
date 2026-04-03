"""
risk/trading_config.py — 국면별 동적 트레이딩 설정 v5.1
========================================================
v5.1 변경사항 (SET A-3):
  ★ buy_score_min (절대점수) → buy_percentile_min (상대순위) 전환
  ★ buy_grade_min 추가: 등급 기반 fallback
  ★ absolute_score_floor 추가: 쓰레기 1등 방지 (40점 미만 매수 금지)
  ★ DD CAUTION → percentile에 +3 (점수 +2 → percentile +3)
  ★ DD=0% 초기 상태에서 CAUTION 과잉 제한 방지 로직

근거:
  - Barra USE4: Cross-Sectional Z-Score 기반 (절대 점수 사용 안 함)
  - Jegadeesh & Titman (1993): 상대 순위 기반 모멘텀 전략
  - 현재 점수 분포: mean=47, σ=6.9 → 절대 62점 = 상위 1.5%뿐
  - Percentile 전환 시: NEUTRAL 상위 18% = ~96종목 후보 → 필터 후 15~30 BUY
"""
from dataclasses import dataclass, field
from typing import Dict, Optional


# ═══════════════════════════════════════════════════════════
#  등급 ↔ Percentile 매핑 (batch_final_score와 일치)
# ═══════════════════════════════════════════════════════════

GRADE_PERCENTILE_MAP = {
    "S":  97,   # 상위 3%
    "A+": 92,   # 상위 8%
    "A":  82,   # 상위 18%
    "B+": 62,   # 상위 38%
    "B":  42,   # 상위 58%
    "C":  22,   # 상위 78%
    "D":  10,   # 상위 90%
}

GRADE_ORDER = {"S": 7, "A+": 6, "A": 5, "B+": 4, "B": 3, "C": 2, "D": 1, "F": 0}


# ═══════════════════════════════════════════════════════════
#  국면별 파라미터 테이블 v5.1
# ═══════════════════════════════════════════════════════════

REGIME_PARAMS = {
    "BULL": {
        "max_positions":       20,
        "max_position_pct":    0.10,
        "cash_minimum":        0.10,
        # ── v5.1: Percentile 기반 매수 임계값 ──
        "buy_percentile_min":  62,     # B+ 이상 (상위 38%)
        "buy_grade_min":       "B+",   # fallback
        "absolute_score_floor": 40,    # 쓰레기 1등 방지
        # ── 기존 유지 (하위 호환) ──
        "buy_score_min":       58,     # legacy (percentile 우선)
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
        "blend_rp": 0.30,
        "blend_hk": 0.40,
        "blend_conv": 0.30,
    },
    "NEUTRAL": {
        "max_positions":       15,
        "max_position_pct":    0.08,
        "cash_minimum":        0.20,
        # ── v5.1: Percentile 기반 ──
        "buy_percentile_min":  75,     # A~B+ 사이 (상위 25%)
        "buy_grade_min":       "A",
        "absolute_score_floor": 40,
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
        # ── v5.1: Percentile 기반 ──
        "buy_percentile_min":  88,     # A+ 근처 (상위 12%)
        "buy_grade_min":       "A+",
        "absolute_score_floor": 42,
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
        # ── v5.1: Percentile 기반 ──
        "buy_percentile_min":  95,     # S등급 근처 (상위 5%)
        "buy_grade_min":       "S",
        "absolute_score_floor": 45,
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
    max_positions: int = 15
    max_position_pct: float = 0.08
    cash_minimum: float = 0.20
    buy_score_min: float = 62
    buy_percentile_min: float = 75       # v5.1 추가
    buy_grade_min: str = "A"             # v5.1 추가
    absolute_score_floor: float = 40     # v5.1 추가
    buy_l3_min: float = 55
    buy_rsi_max: float = 70
    stop_loss_atr_mult: float = 1.8
    trailing_stop_atr_mult: float = 2.5
    sector_max_pct: float = 0.30
    position_size_mult: float = 0.80
    rebalance_freq_days: int = 7
    initial_capital: float = 100000.0       # v5.1 FIX: batch_trading_signals 호환


class DynamicConfig(TradingConfig):
    """
    국면(regime) + DD모드에 따라 파라미터 자동 전환.
    
    v5.1: Percentile 기반 매수 임계값 + DD CAUTION 개선
    """
    regime: str = "NEUTRAL"
    dd_mode: str = "NORMAL"

    # 블렌딩 비율
    blend_rp: float = 0.15
    blend_hk: float = 0.10
    blend_conv: float = 0.75

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

    def apply_dd_override(self, dd_mode: str, current_dd_pct: float = None):
        """
        DD 모드에 따라 추가 제한 적용.
        v5.1: DD=0% (운영 초기)이면 CAUTION이어도 NORMAL로 처리
        """
        self.dd_mode = dd_mode

        # v5.1: 운영 초기 DD=0% → CAUTION 과잉 제한 방지
        if dd_mode == "CAUTION" and current_dd_pct is not None and current_dd_pct >= 0:
            dd_mode = "NORMAL"
            self.dd_mode = "NORMAL"
            print(f"  [DD-FIX] DD={current_dd_pct:.1f}% >= 0 → CAUTION→NORMAL 전환 (운영 초기 보호)")

        if dd_mode == "NORMAL":
            self._dd_buy_allowed = True
            self._dd_force_reduce = False
            self._dd_position_mult_override = None

        elif dd_mode == "CAUTION":
            self._dd_buy_allowed = True
            # v5.1: percentile 기반으로 전환
            self.buy_percentile_min = min(self.buy_percentile_min + 3, 98)
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

    def check_buy_threshold(self, candidate: dict) -> tuple:
        """
        v5.1: Percentile 기반 매수 임계값 검사.
        
        3중 검증:
          1차: percentile_rank >= buy_percentile_min
          2차: grade >= buy_grade_min (fallback)
          3차: absolute_score_floor (쓰레기 방지)
        
        Returns:
            (passed: bool, reason: str)
        """
        pct = candidate.get("percentile_rank", 0)
        grade = candidate.get("grade", "D")
        score = candidate.get("final_score", 0)

        # 3차: Absolute Floor (쓰레기 1등 방지)
        if score < self.absolute_score_floor:
            return False, f"Floor: score {score:.1f} < {self.absolute_score_floor}"

        # 1차: Percentile 기반 (주 필터)
        if pct < self.buy_percentile_min:
            return False, f"Pct: {pct:.0f} < {self.buy_percentile_min:.0f}"

        return True, f"PASS (pct={pct:.0f}, grade={grade}, score={score:.1f})"

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
            "buy_percentile_min": self.buy_percentile_min,
            "buy_grade_min": self.buy_grade_min,
            "absolute_score_floor": self.absolute_score_floor,
            "buy_score_min": self.buy_score_min,  # legacy
            "position_mult": f"{self.effective_position_mult:.2f}",
            "stop_loss_atr": self.stop_loss_atr_mult,
            "trailing_atr": self.trailing_stop_atr_mult,
            "blend": f"RP={self.blend_rp:.0%} HK={self.blend_hk:.0%} Conv={self.blend_conv:.0%}",
        }