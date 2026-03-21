"""
trading_config.py — Trading Engine 파라미터 중앙 관리 v3.1
==========================================================
모든 수치는 여기서 변경. 백테스트 시 override 가능.

v3.0 → v3.1 변경:
  ① 확신도: step → 연속함수 (Two-part: ramp + sigmoid)
  ② 국면 배수: 4단계 → 연속함수
  ③ VIX 관련 파라미터 추가 (Z-score 기반)
"""
from dataclasses import dataclass
import numpy as np


@dataclass
class TradingConfig:
    """트레이딩 엔진 전체 설정"""

    # ── 자본금 ──
    initial_capital: float = 100_000.0

    # ── 매매 시그널 조건 (기본값 = adaptive floor) ──
    buy_score_min: float = 65.0
    buy_l3_min: float = 55.0
    buy_rsi_max: float = 75.0
    sell_score_max: float = 45.0
    sell_consecutive_days: int = 2

    # ── 포지션 사이징 ──
    risk_per_trade: float = 0.015
    stop_loss_atr_mult: float = 2.0
    trailing_stop_atr_mult: float = 3.0

    # ── 확신도 v3.1: 연속함수 파라미터 ──
    conviction_max: float = 1.5        # 최대 배수
    conviction_entry_min: float = 55.0  # 매수 가능 최소 점수
    conviction_full_at: float = 65.0    # 1.0x 배수 시작 점수
    conviction_sigmoid_mid: float = 72.0
    conviction_sigmoid_k: float = 0.15

    # ── Hard Limits ──
    max_position_pct: float = 0.15
    max_sector_pct: float = 0.30
    max_positions: int = 20
    min_positions: int = 8
    min_trade_amount: float = 500.0

    # ── 현금 비율 (국면별) ──
    cash_min_bull: float = 0.05
    cash_min_neutral: float = 0.15
    cash_min_bear: float = 0.30
    cash_min_crisis: float = 0.50

    # ── VIX 관련 (v3.1) ──
    vix_crisis_threshold: float = 30.0    # 절대값 임계 (후순위)
    vix_zscore_crisis: float = 2.0        # Z-score > 2.0 → CRISIS 후보
    vix_zscore_alert: float = 1.5         # Z-score > 1.5 → ALERT (레벨 다운)

    # ── 리밸런싱 ──
    rebalance_day: int = 0
    min_rebalance_delta: float = 0.02

    # ── 퇴장 ──
    max_holding_days: int = 60
    min_return_for_hold: float = 0.05

    # ── 거래 비용 ──
    commission_per_trade: float = 0.0
    slippage_pct: float = 0.0005

    # ── 포트폴리오 레벨 리스크 ──
    daily_loss_limit: float = -0.03
    weekly_loss_limit: float = -0.05
    monthly_loss_limit: float = -0.10

    # ── 상관관계 ──
    correlation_threshold: float = 0.7
    max_stocks_per_sector: int = 4

    # ── 실적 블랙아웃 (v3.1) ──
    earnings_blackout_days: int = 3  # 발표일 ± N일

    def get_conviction_multiplier(self, score: float) -> float:
        """
        Final Score → 확신도 배수 (v3.1 연속함수)
        
        score < 55:  0.0 (매수 불가)
        55~65: 0→1.0 (선형 램프업)
        65+:   1.0→1.5 (Sigmoid)
        """
        if score < self.conviction_entry_min:
            return 0.0
        
        if score < self.conviction_full_at:
            t = (score - self.conviction_entry_min) / (
                self.conviction_full_at - self.conviction_entry_min
            )
            return round(t * 1.0, 4)
        
        z = self.conviction_sigmoid_k * (score - self.conviction_sigmoid_mid)
        z = float(np.clip(z, -500, 500))
        sig = 1.0 / (1.0 + np.exp(-z))
        return round(1.0 + sig * (self.conviction_max - 1.0), 4)

    def get_regime_multiplier(self, regime: str) -> float:
        """시장 국면 → 포지션 배수"""
        return {
            "BULL": 1.0,
            "NEUTRAL": 0.7,
            "BEAR": 0.4,
            "CRISIS": 0.2,
        }.get(regime, 0.7)

    def get_cash_minimum(self, regime: str) -> float:
        """시장 국면 → 최소 현금 비율"""
        return {
            "BULL": self.cash_min_bull,
            "NEUTRAL": self.cash_min_neutral,
            "BEAR": self.cash_min_bear,
            "CRISIS": self.cash_min_crisis,
        }.get(regime, self.cash_min_neutral)
