"""
risk/drawdown_controller.py — 5단계 Drawdown Controller
=========================================================
고점 대비 하락폭에 따라 자동 방어 모드 전환.
냉각기(Cooldown) + 점진적 복귀(Gradual Re-entry) 포함.

모드:
  NORMAL    → 정상 운용
  CAUTION   → 매수 50% 축소, 스톱 타이트
  WARNING   → 매수 중단, 약종목 정리
  DANGER    → 50% 강제 축소, 현금 60%
  EMERGENCY → 전량 청산 + 냉각기 5영업일
"""
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum
from typing import Optional


class DDMode(str, Enum):
    NORMAL    = "NORMAL"
    CAUTION   = "CAUTION"
    WARNING   = "WARNING"
    DANGER    = "DANGER"
    EMERGENCY = "EMERGENCY"


# 모드별 임계값 & 액션
DD_THRESHOLDS = {
    DDMode.NORMAL:    {"min_dd": 0.00,  "max_dd": -0.03},
    DDMode.CAUTION:   {"min_dd": -0.03, "max_dd": -0.05},
    DDMode.WARNING:   {"min_dd": -0.05, "max_dd": -0.08},
    DDMode.DANGER:    {"min_dd": -0.08, "max_dd": -0.10},
    DDMode.EMERGENCY: {"min_dd": -0.10, "max_dd": -1.00},
}

# 점진 복귀 스케줄 (냉각기 해제 후)
REENTRY_SCHEDULE = [
    (0,  0.3),   # 해제 직후: 30% 포지션
    (5,  0.5),   # 5영업일 후: 50%
    (10, 0.7),   # 10영업일 후: 70%
    (15, 1.0),   # 15영업일 후: 정상
]


@dataclass
class DDState:
    """Drawdown Controller 상태"""
    mode: DDMode = DDMode.NORMAL
    peak_value: float = 0.0
    current_value: float = 0.0
    drawdown_pct: float = 0.0
    # 냉각기
    cooldown_until: Optional[date] = None
    cooldown_days_remaining: int = 0
    # 점진 복귀
    reentry_start_date: Optional[date] = None
    reentry_position_mult: float = 1.0
    # 액션
    buy_allowed: bool = True
    force_reduce: bool = False
    force_liquidate: bool = False
    position_size_mult: float = 1.0
    action_description: str = ""


class DrawdownController:
    """
    5단계 Drawdown Controller.

    사용법:
        ddc = DrawdownController()
        state = ddc.evaluate(today, current_value, peak_value)
        if not state.buy_allowed:
            # 매수 중단
        if state.force_reduce:
            # 포지션 강제 축소
    """

    def __init__(self, cooldown_days: int = 5, reentry_days: int = 20):
        self.cooldown_days = cooldown_days
        self.reentry_days = reentry_days
        self._cooldown_until: Optional[date] = None
        self._reentry_start: Optional[date] = None
        self._prev_mode: DDMode = DDMode.NORMAL

    def evaluate(
        self,
        today: date,
        current_value: float,
        peak_value: float,
        vix_close: float = 0,
        regime: str = "NEUTRAL",
    ) -> DDState:
        """
        현재 상태 평가 → DDState 반환.

        Parameters
        ----------
        today : date           오늘 날짜
        current_value : float  현재 포트폴리오 가치
        peak_value : float     역대 최고 가치
        vix_close : float      현재 VIX (냉각기 해제 조건)
        regime : str           현재 시장 국면
        """
        state = DDState()
        state.current_value = current_value
        state.peak_value = peak_value

        # 드로다운 계산
        if peak_value > 0:
            state.drawdown_pct = (current_value - peak_value) / peak_value
        else:
            state.drawdown_pct = 0.0

        # ── 냉각기 체크 ──
        if self._cooldown_until and today <= self._cooldown_until:
            state.mode = DDMode.EMERGENCY
            state.cooldown_until = self._cooldown_until
            state.cooldown_days_remaining = (self._cooldown_until - today).days
            state.buy_allowed = False
            state.force_liquidate = True
            state.position_size_mult = 0.0
            state.action_description = f"COOLDOWN: {state.cooldown_days_remaining}일 남음"
            return state

        # ── 냉각기 해제 체크 ──
        if self._cooldown_until and today > self._cooldown_until:
            if self._can_resume(state.drawdown_pct, vix_close, regime):
                self._cooldown_until = None
                self._reentry_start = today
            else:
                # 해제 조건 미충족 → 냉각기 연장
                state.mode = DDMode.EMERGENCY
                state.buy_allowed = False
                state.force_liquidate = True
                state.position_size_mult = 0.0
                state.action_description = "COOLDOWN 연장: 해제 조건 미충족"
                return state

        # ── 점진 복귀 중 ──
        if self._reentry_start:
            days_since = (today - self._reentry_start).days
            mult = self._get_reentry_mult(days_since)
            if mult >= 1.0:
                self._reentry_start = None  # 복귀 완료
            else:
                state.reentry_start_date = self._reentry_start
                state.reentry_position_mult = mult
                state.position_size_mult = mult
                state.buy_allowed = True
                state.action_description = f"GRADUAL REENTRY: mult={mult:.1f} ({days_since}일차)"
                # DD 모드는 현재 DD 기준으로 판단 (아래로)

        # ── DD 모드 판단 ──
        dd = state.drawdown_pct
        if dd > DD_THRESHOLDS[DDMode.NORMAL]["max_dd"]:
            mode = DDMode.NORMAL
        elif dd > DD_THRESHOLDS[DDMode.CAUTION]["max_dd"]:
            mode = DDMode.CAUTION
        elif dd > DD_THRESHOLDS[DDMode.WARNING]["max_dd"]:
            mode = DDMode.WARNING
        elif dd > DD_THRESHOLDS[DDMode.DANGER]["max_dd"]:
            mode = DDMode.DANGER
        else:
            mode = DDMode.EMERGENCY

        state.mode = mode

        # ── 모드별 액션 ──
        if mode == DDMode.NORMAL:
            state.buy_allowed = True
            state.position_size_mult = min(state.position_size_mult, 1.0)
            state.action_description = "정상 운용"

        elif mode == DDMode.CAUTION:
            state.buy_allowed = True
            state.position_size_mult = min(state.position_size_mult, 0.7)
            state.action_description = "매수 50% 축소 / 스톱 타이트"

        elif mode == DDMode.WARNING:
            state.buy_allowed = False
            state.position_size_mult = min(state.position_size_mult, 0.5)
            state.action_description = "매수 중단 / 약종목 정리 / 현금 40%+"

        elif mode == DDMode.DANGER:
            state.buy_allowed = False
            state.force_reduce = True
            state.position_size_mult = min(state.position_size_mult, 0.3)
            state.action_description = "포지션 50% 강제 축소 / 현금 60%+"

        elif mode == DDMode.EMERGENCY:
            state.buy_allowed = False
            state.force_liquidate = True
            state.position_size_mult = 0.0
            state.action_description = "전량 청산 / 냉각기 발동"
            # 냉각기 시작
            if not self._cooldown_until:
                self._cooldown_until = today + timedelta(days=self.cooldown_days + 2)  # 주말 고려
                state.cooldown_until = self._cooldown_until

        # ── 모드 전환 감지 ──
        mode_changed = (mode != self._prev_mode)
        self._prev_mode = mode

        return state

    def _can_resume(self, dd_pct: float, vix: float, regime: str) -> bool:
        """냉각기 해제 조건 체크"""
        if dd_pct < -0.05:
            return False       # DD가 -5% 이내로 회복되지 않음
        if vix > 25:
            return False       # VIX 여전히 높음
        if regime == "CRISIS":
            return False       # 아직 CRISIS 국면
        return True

    def _get_reentry_mult(self, days_since_reentry: int) -> float:
        """점진 복귀 배수 계산"""
        mult = 0.3
        for day_threshold, target_mult in REENTRY_SCHEDULE:
            if days_since_reentry >= day_threshold:
                mult = target_mult
        return mult

    def get_mode_changed(self, new_mode: DDMode) -> bool:
        """이전 모드와 다른지 확인 (알림 트리거용)"""
        return new_mode != self._prev_mode

    def reset(self):
        """상태 초기화 (테스트용)"""
        self._cooldown_until = None
        self._reentry_start = None
        self._prev_mode = DDMode.NORMAL
