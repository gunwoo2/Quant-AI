# QUANT AI — 멀티레이어 퀀트 + AI 투자 시스템

<div align="center">

```
 ██████╗ ██╗   ██╗ █████╗ ███╗   ██╗████████╗     █████╗ ██╗
██╔═══██╗██║   ██║██╔══██╗████╗  ██║╚══██╔══╝    ██╔══██╗██║
██║   ██║██║   ██║███████║██╔██╗ ██║   ██║       ███████║██║
██║▄▄ ██║██║   ██║██╔══██║██║╚██╗██║   ██║       ██╔══██║██║
╚██████╔╝╚██████╔╝██║  ██║██║ ╚████║   ██║       ██║  ██║██║
 ╚══▀▀═╝  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═══╝   ╚═╝       ╚═╝  ╚═╝╚═╝
```

**3-Layer Quant Scoring + XGBoost AI + Self-Improving Engine**

US/KR 534종목 | 10-Step Daily Pipeline | Discord Real-Time Alerts

</div>

---

## 📐 System Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                        DATA SOURCES                              │
│  FMP · FRED · KIS · FINRA · Yahoo · News · Earnings · SEC       │
└───────────────────────┬──────────────────────────────────────────┘
                        ▼
┌──────────────────────────────────────────────────────────────────┐
│                   10-STEP DAILY PIPELINE                         │
│                                                                  │
│  Step 1  가격 수집 (FMP/KIS)                                      │
│  Step 2  파생 재무 계산                                            │
│  Step 3  Layer 1 — Fundamental (재무 퀀트)                         │
│  Step 4  Layer 3 — Market Signal (기술적 + 수급 + 매크로)           │
│  Step 5  Layer 2 — Sentiment (NLP 감성 + 애널리스트 + 내부자)       │
│  Step 6  Final Score — 가중합산 + Cross-Sectional 등급              │
│  Step 6.3  XGBoost AI — 학습/추론 + SHAP 설명                     │
│  Step 6.5  Factor IC — 자가개선 가중치 최적화                       │
│  Step 6.7  Alpha Decay — 시그널 반감기 추적                        │
│  Step 7  Trading Signal — 매매 시그널 + 리스크 관리                 │
│  Step 8  Discord 알림 — 전 채널 일괄 전송                          │
│  Step 9  주간 성과 리포트 (금요일)                                  │
│  Step 10 월간 성과 리포트 (월초)                                   │
│                                                                  │
└───────────────────────┬──────────────────────────────────────────┘
                        ▼
┌──────────────────────────────────────────────────────────────────┐
│                     OUTPUT LAYER                                 │
│                                                                  │
│  📊 Web Dashboard (React)     📱 Discord Alerts (16개 채널)       │
│  📈 Backtest Engine           🤖 AI Explainability (SHAP)        │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## 🏗️ Architecture

### Final Score 산출 구조

```
                        ┌─────────────┐
                  ┌────►│   Layer 1   │ Fundamental ──── 50%
                  │     │  (100점)    │ (동적 조정)
                  │     └─────────────┘
                  │
  Raw Data ───────┼────►┌─────────────┐
  (11 Sources)    │     │   Layer 2   │ Sentiment ───── 25%
                  │     │  (100점)    │ (동적 조정)
                  │     └─────────────┘
                  │
                  │     ┌─────────────┐
                  └────►│   Layer 3   │ Market Sig ──── 25%
                        │  (100점)    │ (동적 조정)
                        └──────┬──────┘
                               │
                    Adaptive Weighted Sum
                               │
                        ┌──────▼──────┐
                        │  Stat Score │ ←── 퀀트 통계 점수
                        │  (0~100)    │
                        └──────┬──────┘
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                     │
    ┌─────▼─────┐     ┌───────▼──────┐      ┌──────▼──────┐
    │ Stat × 70%│     │  AI × 30%   │      │ Cross-Sect  │
    │           │     │  (XGBoost)   │      │ Percentile  │
    └─────┬─────┘     └───────┬──────┘      │ (Barra MAD) │
          │                   │              └──────┬──────┘
          └─────────┬─────────┘                     │
                    ▼                               ▼
            ┌──────────────┐               ┌──────────────┐
            │  Ensemble    │               │    Grade     │
            │   Score      │───────────────│  S/A+/A/B+   │
            │  (0~100)     │               │  /B/C/D      │
            └──────────────┘               └──────────────┘
```

> **가중치는 고정이 아닙니다.** Self-Improving Engine (Step 6.5)이 매일 Factor IC를 측정하고, IC가 음수인 레이어의 가중치를 자동으로 낮춥니다.

---

## 📊 Layer 1 — Fundamental (재무 퀀트)

> **100점 만점 | 4개 카테고리 | Sigmoid 연속변환**

모든 재무지표는 **섹터 내 백분위**로 변환한 뒤, **Sigmoid 함수**로 연속 점수화합니다.
계단함수(if-else) 대신 Sigmoid를 쓰는 이유: 턴오버 감소 + 경계값 노이즈 제거.

```
                L1 = MOAT × 35% + VALUE × 25% + MOMENTUM × 25% + STABILITY × 15%
```

### 1-A. MOAT (경쟁우위) — 35점

기업의 **지속 가능한 경쟁력**을 측정합니다.

| 지표 | 배점 | 산식 | 의미 |
|------|------|------|------|
| **ROIC** | 30% | sigmoid(ROIC 섹터 백분위) | 투하자본 대비 수익성. 워런 버핏이 가장 중시하는 지표 |
| **GPA** (매출총이익/총자산) | 25% | sigmoid(GPA 섹터 백분위) | Novy-Marx(2013) "Quality" 팩터. 자산 효율성 |
| **FCF Margin** | 20% | sigmoid(FCF/매출 백분위) | 실제 현금 창출력. 분식회계 방어 |
| **Net Debt/EBITDA** | 10% | sigmoid(부채비율 역백분위) | 재무 건전성. 낮을수록 좋음 |
| **Accruals** | 15% | inverse_sigmoid(발생액 비율) | 이익의 질. 높으면 감점 (분식 위험) |

### 1-B. VALUE (가치) — 25점

기업의 **주가 대비 내재가치**를 측정합니다.

| 지표 | 배점 | 산식 | 의미 |
|------|------|------|------|
| **EV/EBIT** | 35% | sigmoid(EV/EBIT 역백분위) | 기업가치 대비 영업이익. PER보다 자본구조 중립적 |
| **EV/FCF** | 30% | sigmoid(EV/FCF 역백분위) | 기업가치 대비 잉여현금흐름 |
| **P/B** | 20% | sigmoid(PBR 역백분위) | 주가 대비 장부가. 자산주 발굴 |
| **PEG** | 15% | sigmoid(PEG 역백분위) | 성장률 대비 주가 적정성 |

### 1-C. MOMENTUM (실적 모멘텀) — 25점

기업의 **실적 추세와 시장 기대 대비 성과**를 측정합니다.

| 지표 | 배점 | 산식 | 의미 |
|------|------|------|------|
| **Earnings Surprise** | 40% | Z-score → Sigmoid | 실적 서프라이즈 (컨센서스 대비). Ball & Brown(1968) |
| **Earnings Revision** | 30% | Z-score → Sigmoid | 애널리스트 추정치 변화 추세 |
| **Analyst Consensus** | 30% | sigmoid(목표가 백분위) | 시장 컨센서스 평균 |

### 1-D. STABILITY (안정성) — 15점

기업의 **예측 가능성과 변동성**을 측정합니다.

| 지표 | 배점 | 산식 | 의미 |
|------|------|------|------|
| **Revenue Stability** | 30% | sigmoid(매출 안정성 백분위) | 매출 변동성이 낮을수록 고점수 |
| **EPS Stability** | 30% | sigmoid(EPS 안정성 백분위) | 이익 예측 가능성 |
| **Beta** | 25% | sigmoid(베타 역백분위) | 시장 대비 변동성. 낮을수록 안정 |
| **Dividend Consistency** | 15% | sigmoid(배당 일관성 백분위) | 배당 이력 안정성 |

### Sigmoid 변환 함수

```python
def sigmoid_score(percentile, max_points):
    """
    Ilmanen (2021) "Investing Amid Low Expected Returns" 참조.
    계단함수 대비 장점: 경계값 노이즈 제거, 턴오버 30% 감소.

    percentile: 0~100 (섹터 내 순위)
    max_points: 해당 항목 최대 점수
    """
    x = (percentile - 50) / 15  # 50을 중심으로 정규화
    return max_points / (1 + exp(-x))
```

---

## 📡 Layer 2 — Sentiment (NLP/감성 분석)

> **100점 만점 | 3개 소스 | 동적 가중치 재분배**

텍스트/비정형 데이터에서 시장 심리를 추출합니다.

```
           L2 = NEWS × 40% + ANALYST × 35% + INSIDER × 25%
              (데이터 없는 소스는 가중치 자동 재분배)
```

### 2-A. News Sentiment — 40%

| 항목 | 설명 |
|------|------|
| **소스** | 뉴스 기사 수집 (제목 + 본문) |
| **분석** | Sentiment Score (-1 ~ +1) |
| **시간 가중** | 최신 뉴스에 높은 가중치 (Time Decay) |
| **정규화** | 0~100 점수 변환 |

### 2-B. Analyst Rating — 35%

| 항목 | 설명 |
|------|------|
| **소스** | 애널리스트 투자의견 + 목표가 |
| **강매수/매수 비율** | 전체 애널리스트 중 긍정 비율 |
| **목표가 괴리율** | 현재가 대비 컨센서스 목표가 상승여력 |
| **의견 변화 추세** | 최근 30일 의견 변화 방향 |

### 2-C. Insider Trading — 25%

| 항목 | 설명 |
|------|------|
| **소스** | FINRA 내부자 거래 공시 |
| **순매수 금액** | 내부자 매수 - 매도 금액 |
| **거래 빈도** | 다수 내부자 동시 매수 → 강한 신호 |
| **직급 가중** | CEO/CFO 거래에 높은 가중치 |

### 동적 가중치 재분배

데이터가 없는 소스의 가중치를 다른 소스에 비례 배분합니다:

```python
# 예: Insider 데이터 없는 경우
# 원래: News 40% + Analyst 35% + Insider 25%
# 재분배: News 53% + Analyst 47% + Insider 0%
```

---

## 📈 Layer 3 — Market Signal (기술적 분석 + 수급 + 매크로)

> **100점 만점 | 3개 섹션 | Section A(55) + B(25) + C(20)**

가격/거래량 데이터 + 수급 + 매크로 환경을 종합합니다.

```
         L3 = Section A (Technical, 55점)
            + Section B (Supply/Demand, 25점)
            + Section C (Macro Environment, 20점)
            → 100점 정규화
```

### 3-A. Section A — Technical Indicators (55점 만점)

| 지표 | 배점 | 설명 |
|------|------|------|
| **상대 모멘텀** (12-1M) | 15점 | Jegadeesh & Titman(1993). 12개월 수익률 - 직전 1개월 |
| **52주 신고가 거리** | 10점 | 현재가 vs 52주 최고가 괴리율. George & Hwang(2004) |
| **추세 안정성** (R², Slope) | 8점 | 90일 회귀선 R² + 기울기. 추세 지속 가능성 |
| **RSI (14일)** | 7점 | 과매수/과매도 판단. 30~70 구간 세분화 |
| **MACD** | 5점 | MACD-Signal 크로스오버 + 히스토그램 가속도 |
| **OBV (On-Balance Volume)** | 5점 | OBV-Price Divergence 감지. 숨은 매수세/매도세 |
| **거래량 급증** | 5점 | 20일 평균 대비 거래량 비율. RSI 조건부 가중 |

**Structural Bonus** (별도):
- Golden/Death Cross (MA50 vs MA200)
- 볼린저밴드 Squeeze → Breakout 감지
- MA20 연속 돌파 일수
- 52주 신고가 Breakout

### 3-B. Section B — Supply/Demand (25점 만점)

| 지표 | 배점 | 소스 | 설명 |
|------|------|------|------|
| **공매도 비율** (SVR) | 10점 | FINRA | Short Volume Ratio. 5일 평균 추세 포함 |
| **풋/콜 비율** | 7점 | CBOE | Put/Call Ratio. 극단값 = 역발상 시그널 |
| **Structural Signal** | 8점 | 계산 | 차트 패턴 기반 구조적 매수/매도 압력 |

### 3-C. Section C — Macro Environment (20점 만점)

| 지표 | 배점 | 소스 | 설명 |
|------|------|------|------|
| **VIX** | 10점 | CBOE | 공포지수. 구간별 점수 (15이하 = 만점) |
| **섹터 ETF 흐름** | 10점 | 계산 | 종목 섹터의 ETF 가격 vs MA20/MA50 위치 |

---

## 🎯 등급 산출 — Cross-Sectional Percentile

> **Barra USE4 + Bridgewater Adaptive Threshold**

### 왜 절대값이 아닌 상대평가인가?

```
문제: 점수 범위가 21~56점. 절대값(70점=A)이면 전 종목 D등급.
해결: 534종목 내 상대 순위로 등급 부여 (정규분포 피라미드).
```

### 백분위 → 등급 매핑

```
  Score 분포          MAD Z-Score         Percentile         Grade
  ───────────       ─────────────       ───────────       ──────────
  각 종목 점수  →   Robust Z-Score  →   Normal CDF  →    등급 배정
                    (Median/MAD)        (0~100%)
```

| 등급 | 백분위 | 비율 | ~종목수 |
|------|--------|------|---------|
| **S** | 97%+ | 상위 3% | ~15종목 |
| **A+** | 92~97% | 상위 5% | ~26종목 |
| **A** | 82~92% | 상위 10% | ~52종목 |
| **B+** | 65~82% | 상위 17% | ~88종목 |
| **B** | 40~65% | 상위 25% | ~130종목 |
| **C** | 15~40% | 하위 25% | ~130종목 |
| **D** | 0~15% | 하위 15% | ~77종목 |

### 안전장치: Absolute Floor

"쓰레기 중 1등" 문제를 방지합니다:

| 원점수 | 최대 등급 |
|--------|----------|
| < 25점 | D (상한) |
| < 30점 | C (상한) |
| < 35점 | B (상한) |
| < 40점 | B+ (상한) |
| ≥ 40점 | 제한 없음 |

### EMA Rating Momentum

급격한 등급 변동을 방지합니다 (Frazzini 2018 "Slow Trading"):

```python
smoothed_pct = today_pct × 0.3 + yesterday_smoothed × 0.7
# Half-life ≈ 2일. 급등락에 천천히 반응.
```

---

## 🤖 AI Module — XGBoost + SHAP

### 구조

```
┌────────────────────────┐
│     18개 Feature        │
│ ┌────────────────────┐ │         ┌──────────────┐
│ │ L1/L2/L3 점수      │ │         │   XGBoost    │
│ │ MOAT/VALUE/MOM/STB │ │────────►│   Binary     │──► ai_score (0~100)
│ │ 뉴스/애널/내부자     │ │         │  Classifier  │
│ │ Tech/Flow/Macro    │ │         └──────┬───────┘
│ │ VIX/Regime/Sector  │ │                │
│ └────────────────────┘ │          SHAP TreeExplainer
└────────────────────────┘                │
                                   ┌──────▼───────┐
                                   │  Top 5 기여   │
                                   │  긍정 / 부정   │
                                   └──────────────┘
```

### Feature 목록 (18개)

| # | Feature | 한글명 | 설명 |
|---|---------|--------|------|
| 1 | layer1_score | 기본면 (L1) | Fundamental 종합 |
| 2 | layer2_score | 심리면 (L2) | Sentiment 종합 |
| 3 | layer3_score | 기술면 (L3) | Market Signal 종합 |
| 4 | moat_score | 경쟁우위 | ROIC/GPA/FCF |
| 5 | value_score | 가치 | EV/EBIT, P/B |
| 6 | momentum_score | 모멘텀 | Earnings Surprise/Revision |
| 7 | stability_score | 안정성 | 변동성/배당 |
| 8 | news_score | 뉴스 감성 | NLP Sentiment |
| 9 | analyst_score | 애널리스트 | 투자의견 |
| 10 | insider_score | 내부자 거래 | 임원 매수/매도 |
| 11 | section_a_tech | 기술지표 | RSI/MACD 등 |
| 12 | section_b_flow | 수급 | 공매도/풋콜 |
| 13 | section_c_macro | 시장환경 | VIX/섹터ETF |
| 14 | macro_score | 매크로 | Cross-Asset |
| 15 | risk_appetite | 리스크 선호도 | HYG/LQD 스프레드 |
| 16 | vix_close | VIX 수준 | 공포지수 |
| 17 | market_regime_num | 시장 국면 | BULL/NEUTRAL/BEAR/CRISIS |
| 18 | sector_code_num | 섹터 코드 | GICS 섹터 |

### Ensemble Score

```python
ensemble = stat_score × (1 - ai_weight) + ai_score × ai_weight
# ai_weight: 기본 30%, IC 기반 동적 조정 (10~50%)
```

### SHAP Explainability

모든 종목에 대해 **왜 이 점수인지** 설명합니다:

```
NVDA (ai_score: 82.5)
  ✅ 경쟁우위 (ROIC/GPA/FCF)  +15.2  ← 이 팩터가 점수를 가장 많이 올림
  ✅ 기술지표 (RSI/MACD)       +8.7
  ❌ 시장환경 (VIX)            -4.2  ← 이 팩터가 가장 큰 감점 요인
```

---

## 🔄 Self-Improving Engine

시스템이 스스로 학습하고 가중치를 최적화합니다.

### Factor IC Monitor (Step 6.5)

**IC (Information Coefficient)**: 과거 점수와 실현 수익률의 상관관계.

```
IC > 0.05  →  ✅ 유효한 시그널. 가중치 유지/증가
0 < IC < 0.05 → ⚠️ 약한 시그널. 가중치 감소 검토
IC ≤ 0     →  🔴 시그널 무효! 가중치 대폭 축소 또는 0
```

```
매일 계산:
  L1 IC = corr(L1 점수, 5일 후 수익률)
  L2 IC = corr(L2 점수, 5일 후 수익률)
  L3 IC = corr(L3 점수, 5일 후 수익률)

매월 최적화:
  새 가중치 = IC 비율로 자동 배분
  예) L1 IC=0.27, L2 IC=0.05, L3 IC=0.15
    → L1=57%, L2=11%, L3=32%
```

### Alpha Decay Tracker (Step 6.7)

시그널의 **유효기간(반감기)**을 추적합니다:

```
등급별 × 보유기간별 성과 매트릭스:
  [S  | 1D] avg= ? | hit= ? | IC= ?
  [A+ | 5D] avg= ? | hit= ? | IC= ?
  ...

상태 분류:
  ACTIVE → IC > 0.05 (시그널 유효)
  WEAK   → 0 < IC ≤ 0.05 (약화 중)
  DEAD   → IC ≤ 0 (시그널 무효, 퇴출 검토)
```

### AI Weight 동적 조정

```python
# factor_weights_monthly 테이블에서 IC 비교
if ai_ic > stat_ic × 1.2:
    ai_weight = min(0.50, 0.30 + 0.10)  # AI 40%까지 증가
elif ai_ic < stat_ic × 0.5:
    ai_weight = max(0.10, 0.30 - 0.10)  # AI 20%까지 감소
else:
    ai_weight = 0.30  # 기본값 유지
```

---

## ⚡ Trading Signal Pipeline (Step 7)

### 7단계 의사결정 프로세스

```
Step 7/1  시장 국면 판단 ──────────────────────────────────┐
Step 7/2  리스크 상태 평가 (DD + CB)                         │
Step 7/3  보유종목 SELL 스캔                                 │
Step 7/4  BUY 후보 스캔 (534종목)                            ├── Decision Audit
Step 7/5  포트폴리오 구성 (Kelly + Vol Sizing)                │   (전 과정 기록)
Step 7/6  DB 저장                                           │
Step 7/7  Discord 알림                                      │
                                                           ┘
```

### 시장 국면 판단 (Regime Detector v2)

5개 지표 앙상블 투표로 결정:

| 지표 | 방법 | BULL | BEAR |
|------|------|------|------|
| **MA Cross** | SPY 50일/200일 | Price > MA50 > MA200 | Price < MA50 < MA200 |
| **VIX** | 절대 수준 | < 15 | > 25 |
| **SPY 모멘텀** | 20일 수익률 | > +5% | < -5% |
| **시장 폭** | MA50 위 종목 % | > 60% | < 40% |
| **방어주 선호** | SPY vs Utilities | SPY 강세 | Utilities 강세 |

```
투표 합산 → BULL(+4~+2) / NEUTRAL(+1~-1) / BEAR(-2~-3) / CRISIS(-4~-5)
```

### 국면별 파라미터

| 국면 | BUY 조건 | 포지션 배수 | 최대 보유 |
|------|----------|------------|----------|
| **BULL** | 상위 85%tile | ×1.2 | 20종목 |
| **NEUTRAL** | 상위 90%tile | ×1.0 | 15종목 |
| **BEAR** | 상위 95%tile | ×0.6 | 10종목 |
| **CRISIS** | 상위 98%tile | ×0.3 | 5종목 |

---

## 🛡️ Risk Management

### 3중 안전장치

```
┌────────────────────────────────────────────────┐
│  Level 1: Drawdown Controller                   │
│  ──────────────────────────────                 │
│  DD < 3%  → NORMAL  (매매 정상)                  │
│  DD 3~5%  → CAUTION (포지션 축소)                │
│  DD 5~8%  → WARNING (신규 매수 중단)              │
│  DD 8~10% → DANGER  (포지션 50% 청산)            │
│  DD > 10% → EMERGENCY (전량 청산)                │
├────────────────────────────────────────────────┤
│  Level 2: Circuit Breaker                       │
│  ──────────────────────────────                 │
│  연속 3회 손실 → 매수 잠금                         │
│  연속 5회 손실 → 시스템 일시 정지                   │
│  일일 손실 > 3% → 자동 SELL ALL                   │
├────────────────────────────────────────────────┤
│  Level 3: Position Sizing (Half-Kelly)          │
│  ──────────────────────────────                 │
│  Kelly Criterion: f* = (p×b - q) / b           │
│  Half-Kelly로 보수적 적용 (×0.5)                  │
│  × 변동성 역비례 (ATR 기반)                        │
│  × 등급 확신도 배수 (S: ×1.5, D: ×0.3)           │
│  × 국면 배수 (BULL: ×1.2, CRISIS: ×0.3)         │
│  × DD 배수 + CB 배수                             │
│  → 최종 포지션: 최대 8% 상한                       │
└────────────────────────────────────────────────┘
```

---

## 📱 Discord Alert System

16개 전문 채널로 실시간 알림을 전송합니다.

### 채널 구조

| 채널 | 알림 내용 | 트리거 |
|------|----------|--------|
| **#morning-briefing** | 오늘의 시장 국면 + 포트폴리오 현황 | 배치 시작 |
| **#daily-signals** | 매수/매도 시그널 상세 | Step 7 완료 |
| **#add-position** | 신규 매수 종목 | BUY 시그널 |
| **#fire-sell** | 긴급 매도 | DD/CB 트리거 |
| **#grade-changes** | 등급 변동 (S→A+ 등) | 등급 변경 |
| **#regime-change** | 시장 국면 전환 | BULL↔BEAR 등 |
| **#risk-warning** | 리스크 경고 | DD > 5% |
| **#earnings-alert** | 실적 발표 예정 (3일 전) | 캘린더 |
| **#weekly-report** | 주간 성과 리포트 | 금요일 |
| **#batch-status** | 배치 시작/완료/실패 | 매일 |
| **#ai-analysis** | AI 예측 + SHAP 설명 | Step 6.3 |
| **#bounce-opportunity** | 반등 기회 종목 | 급락 후 조건 충족 |
| **#backtest-result** | 백테스트 결과 | 수동 실행 |
| **#emergency** | 긴급 상황 (시스템 장애 등) | 에러 감지 |

### AI 모닝 브리핑 예시

```
☀️ QUANT AI — Morning Briefing (2026-03-29)

📊 시장 국면: BEAR
  SPY $634.09 | VIX 25.33
  MA50: $642 (아래) | MA200: $628 (위)

📋 포트폴리오 현황:
  보유 0종목 | 투자금 $0 | DD 0.0%

🤖 AI 추론 결과:
  Top 5: GOOG(82.5), AAPL(78.3), MSFT(76.1), ...
  Bottom 5: ...
```

---

## 🖥️ Frontend Dashboard

React + Vite 기반 실시간 대시보드.

### 탭 구조

| 탭 | 내용 |
|----|------|
| **Screener** | 534종목 테이블 + 필터 + 정렬 (3세트: Quant/AI/Final) |
| **Signals** | 트레이딩 시그널 현황 |
| **Sectors** | 11개 GICS 섹터별 분석 |
| **Market** | 시장 국면 + Cross-Asset 모니터 |
| **종목 상세** | Summary / Quant / NLP / Market Signal / AI Explainability |

---

## 🗄️ Tech Stack

| 구분 | 기술 |
|------|------|
| **Backend** | Python 3.12 / FastAPI / PostgreSQL |
| **Frontend** | React 18 / Vite / Recharts |
| **AI/ML** | XGBoost / SHAP / NumPy / SciPy |
| **Data** | FMP / FRED / KIS / FINRA / Yahoo Finance |
| **Infra** | Ubuntu Server / PM2 / Nginx |
| **Alert** | Discord Webhook (16채널) |
| **학술 참조** | Barra USE4 / Bridgewater / Ilmanen / Frazzini / Kelly |

---

## 📁 Project Structure

```
backend/
├── batch/               # 10-Step 배치 파이프라인
│   ├── scheduler.py         # 전체 오케스트레이터
│   ├── batch_ticker_item_daily.py  # Step 1-2: 가격/재무
│   ├── batch_layer2_v2.py   # Step 5: Sentiment
│   ├── batch_layer3_v2.py   # Step 4: Market Signal
│   ├── batch_final_score.py # Step 6: 최종 합산
│   ├── batch_xgboost.py     # Step 6.3: AI
│   ├── batch_factor_monitor.py  # Step 6.5: IC Monitor
│   ├── batch_alpha_decay.py # Step 6.7: Alpha Decay
│   └── batch_trading_signals.py # Step 7: Trading
├── utils/               # 스코어링 엔진
│   ├── scoring_engine.py    # L1 Fundamental (Sigmoid v3)
│   ├── layer2_scoring.py    # L2 Sentiment
│   ├── layer3_scoring.py    # L3 Market Signal
│   └── adaptive_scoring.py  # Cross-Sectional Percentile
├── risk/                # 리스크 관리
│   ├── drawdown_controller.py
│   ├── circuit_breaker.py
│   └── risk_model.py
├── portfolio/           # 포트폴리오 구성
│   ├── portfolio_builder.py
│   ├── position_sizer.py   # Half-Kelly
│   └── correlation_filter.py
├── signals/             # 시그널 생성
│   ├── alpha_model.py
│   ├── regime_detector.py
│   └── signal_generator.py
├── services/            # API 서비스 레이어
├── routers/             # FastAPI 엔드포인트
├── schemas/             # Pydantic 모델
├── notifier.py          # Discord 16채널 알림
└── notify_data_builder.py # 알림 데이터 구성

frontend/
├── pages/               # 페이지 라우팅
├── components/          # UI 컴포넌트
│   ├── dashboard/       # StockTable, Heatmap
│   ├── layout/          # Sidebar, MarketMarquee
│   ├── SummaryTab.jsx   # 종목 요약
│   ├── MarketSignalTab.jsx # L3 상세
│   └── NlpSignalTab.jsx # L2 상세
└── styles/tokens.js     # 디자인 토큰
```

---

## 📊 Codebase Stats

| 항목 | 수치 |
|------|------|
| **Backend** | 99 files / 28,616 lines |
| **Frontend** | 24 files / 6,423 lines |
| **Total** | 123 files / 35,039 lines |
| **Data Sources** | 11개 |
| **종목 수** | US 534 + KR (확장 예정) |
| **배치 주기** | 일 1회 (ET 20:30 / KST 09:30) |
| **AI 재학습** | 주 1회 (일요일) |

---

<div align="center">

*Built with 📊 Quantitative Finance + 🤖 Machine Learning + 🧠 Academic Research*

</div>
