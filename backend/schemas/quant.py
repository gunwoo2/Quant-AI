from pydantic import BaseModel
from typing import Optional


# ── MOAT 섹션 ──────────────────────────────────────────
class MoatMetrics(BaseModel):
    # 원시값 (재무제표에서)
    roic:          Optional[float] = None   # NOPAT / Invested Capital
    gpa:           Optional[float] = None   # Gross Profit / Total Assets (Novy-Marx 2013)
    fcfMargin:     Optional[float] = None   # FCF / Revenue
    accrualsQual:  Optional[float] = None   # (Net Income - OCF) / Assets (Sloan 1996)
    netDebtEbitda: Optional[float] = None   # (총부채 - 현금) / EBITDA

    # 세부 점수 (0~만점)
    roicScore:          Optional[float] = None  # 0~30
    gpaScore:           Optional[float] = None  # 0~25
    fcfMarginScore:     Optional[float] = None  # 0~20
    accrualsScore:      Optional[float] = None  # 0~15
    netDebtEbitdaScore: Optional[float] = None  # 0~10

    totalMoatScore: Optional[float] = None      # 0~100


# ── VALUE 섹션 ──────────────────────────────────────────
class ValueMetrics(BaseModel):
    # 원시값
    earningsYield: Optional[float] = None   # EBIT / EV (Greenblatt)
    evFcf:         Optional[float] = None   # EV / FCF
    pbRatio:       Optional[float] = None   # Book Value / Market Cap (Fama-French)
    pegRatio:      Optional[float] = None   # PER / EPS성장률 (Lynch 1989)

    # 세부 점수
    earningsYieldScore: Optional[float] = None  # 0~35
    evFcfScore:         Optional[float] = None  # 0~30
    pbScore:            Optional[float] = None  # 0~20
    pegScore:           Optional[float] = None  # 0~15

    totalValueScore: Optional[float] = None     # 0~100


# ── MOMENTUM 섹션 ──────────────────────────────────────
class MomentumMetrics(BaseModel):
    # 원시값
    fScoreRaw:            Optional[int]   = None  # Piotroski 0~9
    earningsRevisionRatio: Optional[float] = None  # 상향건수/(상향+하향) 비율
    atoAcceleration:      Optional[float] = None  # ΔAsset Turnover (당기-전기)
    opLeverage:           Optional[float] = None  # 영업이익변화율 / 매출변화율
    earningsSurprisePct:  Optional[float] = None  # (실제EPS-추정EPS)/|추정EPS|

    # 세부 점수
    fScorePoints:          Optional[float] = None  # 0~30
    earningsRevisionScore: Optional[float] = None  # 0~25
    atoAccelerationScore:  Optional[float] = None  # 0~20
    opLeverageScore:       Optional[float] = None  # 0~15
    earningsSurpriseScore: Optional[float] = None  # 0~10

    totalMomentumScore: Optional[float] = None     # 0~100


# ── STABILITY 섹션 ──────────────────────────────────────
class StabilityMetrics(BaseModel):
    # 원시값
    annualizedVol250d:       Optional[float] = None  # 250일 연간화 표준편차
    epsCv3y:                 Optional[float] = None  # 3년 EPS 변동계수 CV=σ/μ
    dividendConsecutiveYears: Optional[int]  = None  # 연속 배당 연수

    # 세부 점수
    lowVolScore:              Optional[float] = None  # 0~40 (Blitz & van Vliet 2007)
    earningsStabilityScore:   Optional[float] = None  # 0~35
    dividendConsistencyScore: Optional[float] = None  # 0~25

    totalStabilityScore: Optional[float] = None       # 0~100


# ── 기술지표 (Layer 3에서 이동, 타이밍 조절자) ──────────
class TechnicalData(BaseModel):
    relativeMomentumPct: Optional[float] = None  # 12-1 상대 수익률 vs SPY
    dist52W:             Optional[float] = None  # 현재가/52주 고점 비율
    trendR2:             Optional[float] = None  # 90일 회귀 R²
    rsi14:               Optional[float] = None  # RSI 14일
    obvTrend:            Optional[str]   = None  # UP/DOWN/FLAT
    goldenCross:         Optional[bool]  = None  # MA50 > MA200
    deathCross:          Optional[bool]  = None  # MA50 < MA200
    ma50:                Optional[float] = None
    ma200:               Optional[float] = None


# ── 섹터 백분위 ──────────────────────────────────────────
class SectorPercentile(BaseModel):
    roicPercentile:    Optional[float] = None
    gpaPercentile:     Optional[float] = None
    fcfPercentile:     Optional[float] = None
    evEbitPercentile:  Optional[float] = None
    lowVolPercentile:  Optional[float] = None


# ── 최종 응답 ──────────────────────────────────────────
class QuantResponse(BaseModel):
    ticker:     str
    calcDate:   Optional[str]   = None

    # Layer 1 최종 점수
    totalScore:    Optional[float] = None   # 0~100 (섹터 Percentile 보정 후)
    rawScore:      Optional[float] = None   # 0~100 (보정 전)

    # 섹션별 가중 점수 (각 섹션 총점 × 섹션 가중치)
    moatWeighted:      Optional[float] = None   # moat × 35%
    valueWeighted:     Optional[float] = None   # value × 25%
    momentumWeighted:  Optional[float] = None   # momentum × 25%
    stabilityWeighted: Optional[float] = None   # stability × 15%

    # 섹션 상세
    moat:      MoatMetrics
    value:     ValueMetrics
    momentum:  MomentumMetrics
    stability: StabilityMetrics
    technical: TechnicalData
    sectorPercentile: SectorPercentile