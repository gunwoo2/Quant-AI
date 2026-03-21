"""
risk/circuit_breaker.py — 연속 손실 자동 정지 (Circuit Breaker)
================================================================
개별 거래 연속 손실을 감지하여 자동으로 매매를 중단합니다.
DD Controller와 독립적으로 작동.

레벨:
  CLEAR   — 정상
  WATCH   — 3연패 → 경고 (관찰)
  HALT    — 5연패 → 신규 매수 3영업일 중단
  REDUCE  — 7연패 → 포지션 50% 축소 + 5영업일 중단
  STOP    — 10연패 → 전량 청산 + 시스템 정지
"""
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum
from typing import Optional, List


class CBLevel(str, Enum):
    CLEAR  = "CLEAR"
    WATCH  = "WATCH"
    HALT   = "HALT"
    REDUCE = "REDUCE"
    STOP   = "STOP"


CB_THRESHOLDS = {
    3:  CBLevel.WATCH,
    5:  CBLevel.HALT,
    7:  CBLevel.REDUCE,
    10: CBLevel.STOP,
}


@dataclass
class CBState:
    """Circuit Breaker 상태"""
    level: CBLevel = CBLevel.CLEAR
    consecutive_losses: int = 0
    buy_allowed: bool = True
    force_reduce: bool = False
    force_liquidate: bool = False
    position_mult: float = 1.0
    halt_until: Optional[date] = None
    halt_days_remaining: int = 0
    action_description: str = ""


class CircuitBreaker:
    """
    연속 손실 감지 + 자동 정지.

    사용법:
        cb = CircuitBreaker()
        cb.record_trade(pnl=-120.50)      # 손실 거래 기록
        cb.record_trade(pnl=350.00)       # 수익 거래 → 리셋
        state = cb.evaluate(today)
    """

    def __init__(self):
        self._consecutive_losses: int = 0
        self._halt_until: Optional[date] = None
        self._trade_history: List[float] = []  # 최근 거래 PnL

    def record_trade(self, pnl: float):
        """거래 결과 기록"""
        self._trade_history.append(pnl)
        if len(self._trade_history) > 50:
            self._trade_history = self._trade_history[-50:]

        if pnl < 0:
            self._consecutive_losses += 1
        else:
            self._consecutive_losses = 0  # 수익 거래 → 리셋
            self._halt_until = None       # 수익 거래 → halt도 해제

    def evaluate(self, today: date) -> CBState:
        """현재 상태 평가"""
        state = CBState()
        state.consecutive_losses = self._consecutive_losses

        # ── 정지 기간 체크 ──
        if self._halt_until and today <= self._halt_until:
            state.halt_until = self._halt_until
            state.halt_days_remaining = (self._halt_until - today).days
            state.buy_allowed = False
            # 이전 레벨에 따라 추가 액션
            if self._consecutive_losses >= 10:
                state.level = CBLevel.STOP
                state.force_liquidate = True
                state.position_mult = 0.0
                state.action_description = f"SYSTEM STOP: {state.halt_days_remaining}일 남음"
            elif self._consecutive_losses >= 7:
                state.level = CBLevel.REDUCE
                state.force_reduce = True
                state.position_mult = 0.5
                state.action_description = f"REDUCE MODE: {state.halt_days_remaining}일 남음"
            else:
                state.level = CBLevel.HALT
                state.position_mult = 0.7
                state.action_description = f"HALT: {state.halt_days_remaining}일 남음"
            return state

        # ── 정지 해제 ──
        if self._halt_until and today > self._halt_until:
            self._halt_until = None

        # ── 연패 레벨 판단 ──
        losses = self._consecutive_losses

        if losses >= 10:
            state.level = CBLevel.STOP
            state.buy_allowed = False
            state.force_liquidate = True
            state.position_mult = 0.0
            state.action_description = f"10연패: 전량 청산 + 시스템 정지"
            if not self._halt_until:
                self._halt_until = today + timedelta(days=10)
                state.halt_until = self._halt_until

        elif losses >= 7:
            state.level = CBLevel.REDUCE
            state.buy_allowed = False
            state.force_reduce = True
            state.position_mult = 0.5
            state.action_description = f"7연패: 50% 축소 + 5일 중단"
            if not self._halt_until:
                self._halt_until = today + timedelta(days=7)
                state.halt_until = self._halt_until

        elif losses >= 5:
            state.level = CBLevel.HALT
            state.buy_allowed = False
            state.position_mult = 0.7
            state.action_description = f"5연패: 매수 3일 중단"
            if not self._halt_until:
                self._halt_until = today + timedelta(days=5)
                state.halt_until = self._halt_until

        elif losses >= 3:
            state.level = CBLevel.WATCH
            state.buy_allowed = True  # 아직 매수 가능
            state.position_mult = 0.8
            state.action_description = f"3연패: 관찰 모드"

        else:
            state.level = CBLevel.CLEAR
            state.buy_allowed = True
            state.position_mult = 1.0
            state.action_description = "정상"

        return state

    def record_daily_portfolio_return(self, daily_return: float):
        """일일 포폴 수익률로 연패 리셋 가능"""
        if daily_return >= 0.01:  # +1% 이상이면 리셋
            self._consecutive_losses = 0

    def force_reset(self):
        """수동 리셋 (관리자용)"""
        self._consecutive_losses = 0
        self._halt_until = None
        self._trade_history = []

    @property
    def stats(self) -> dict:
        """현재 통계"""
        wins = sum(1 for p in self._trade_history if p > 0)
        losses = sum(1 for p in self._trade_history if p <= 0)
        total = len(self._trade_history)
        return {
            "consecutive_losses": self._consecutive_losses,
            "total_trades": total,
            "recent_wins": wins,
            "recent_losses": losses,
            "win_rate": wins / total if total > 0 else 0,
            "halt_until": str(self._halt_until) if self._halt_until else None,
        }
