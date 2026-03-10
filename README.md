# ⬡ QUANT AI — 멀티팩터 AI 투자 시그널 시스템

> 펀더멘털 퀀트 팩터 × AI 텍스트 분석 × 시장 신호를 결합한 3-Layer 매수/매도 시그널 플랫폼  
> React + Vite (Frontend) · Flask + PostgreSQL (Backend) · Python 배치잡 (Data Pipeline)

---

## 🏗 Repository 구조

```
quant-ai/
├── backend/                        # FastAPI 기반 백엔드
│   ├── main.py                     # 앱 진입점 및 라우트 설정
│   ├── routes/
│   │   └── stock_routes.py         # 6개 핵심 API 엔드포인트 정의
│   ├── services/
│   │   ├── api_service.py          # 실시간 시세 및 비즈니스 로직 통합
│   │   ├── kis_api_service.py      # KIS API 연동 (상세 실시간 시세)
│   │   ├── calculator.py           # 퀀트 점수 계산 엔진 (MOAT, VALUE 등)
│   │   ├── db_pool.py              # ★ Connection Pool + TTL Cache 관리
│   │   └── sector_percentile.py    # ★ 섹터 내 상대적 백분위 계산 로직
│   ├── job/
│   │   └── batch_ticker_daily.py   # 매일 02:00 실행되는 데이터 배치 작업
│   └── secret_info/
│       └── config.py               # API 키 및 보안 설정 관리
├── frontend/
│   ├── src/                        # React(Vite) 프론트엔드
│   │   ├── main.jsx                # 앱 마운트 및 진입점
│   │   ├── App.jsx                 # 전역 라우터 및 Route 트리 정의
│   │   ├── Layout.jsx              # 공통 레이아웃 래퍼 (Main/Footer)
│   │   ├── api.js                  # Axios 인스턴스 (운영/로컬 URL 분기)
│   │   ├── pages/                  # 페이지 단위 컴포넌트
│   │   │   ├── MainDashboard.jsx   # 메인 스크리너 페이지
│   │   │   └── StockDetail.jsx     # 종목 상세 페이지 (탭 레이아웃)
│   │   ├── components/             # 기능별 재사용 컴포넌트
│   │   │   ├── layout/             # Topbar, Sidebar, MarketMarquee, Status
│   │   │   ├── dashboard/          # StockTable(필터/정렬), Modals(추가/삭제)
│   │   │   ├── tabs/               # 상세 페이지 내 6개 분석 탭
│   │   │   │   ├── SummaryTab.jsx      # 종합 요약 및 뉴스
│   │   │   │   ├── QuantRatingTab.jsx  # Layer 1: 퀀트 점수 (Radar Chart)
│   │   │   │   ├── NlpSignalTab.jsx    # Layer 2: 감성 분석 (AI Summary)
│   │   │   │   ├── MarketSignalTab.jsx # Layer 3: 기술 지표 (Technical)
│   │   │   │   ├── FinancialsTab.jsx   # 재무제표 (ECharts)
│   │   │   │   └── HistoricalTab.jsx   # 가격 이력 (OHLCV)
│   │   │   ├── TradingViewWidget.jsx   # 공용 차트 위젯 래퍼
│   │   │   └── MetricCard.jsx          # 툴팁 포함 지표 카드
│   │   └── styles/                 # 디자인 시스템
│   │       ├── tokens.js           # ★ 색상, 폰트, 섹터/Mock 데이터 상수
│   │       └── global.css          # 전역 스타일 및 CSS 변수
│   └── package.json
├── docs/                           # 프로젝트 설계 및 기술 문서
│   └── QUANT_AI_설계서_v2.0.docx
└── README.md

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🗑  레거시 파일 (비활성, 삭제 예정)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

components/Header.jsx           → layout/Topbar.jsx + dashboard/Modals.jsx 로 대체
components/Sidebar.jsx          → layout/Sidebar.jsx 로 대체
components/MainTable.jsx        → dashboard/StockTable.jsx 로 대체
components/MarketHoursWidget.jsx→ layout/MarketStatus.jsx 로 대체
pages/Dashboard.jsx             → pages/MainDashboard.jsx 로 대체


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔗  데이터 흐름 요약
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

URL 파라미터 흐름:
  /main/:sectorId
    └─ MainDashboard (useParams)
         ├─ Sidebar      (activeSector prop)
         └─ StockTable   (filterSector prop → useEffect로 select 동기화)

상세 페이지 데이터 흐름:
  /stock/:ticker/:tabId
    └─ StockDetail (GET /api/stock/detail/:ticker)
         └─ <Outlet context={{ ticker, header, realtime, quantData }}>
              └─ 각 탭 컴포넌트 (useOutletContext() 로 수신)

ADD TICKER 버튼 위치:
  ① Topbar (항상 표시 — 메인 페이지)
  ② StockDetail GlobalBar (항상 표시 — 상세 페이지)

디자인 토큰 의존 관계:
  styles/tokens.js
    ├─ C (색상 객체)          → 전 컴포넌트
    ├─ FONT                   → 전 컴포넌트
    ├─ SECTORS                → Sidebar, StockTable, Modals
    ├─ SECTOR_STATS           → Sidebar SectorFlyout
    ├─ MOCK_STOCKS            → StockTable (백엔드 연결 전 임시)
    ├─ gradeColor(g)          → StockTable, QuantRatingTab
    └─ gradeLabel(g)          → StockTable
---

## 🗂 3-Layer 시그널 아키텍처

| Layer | 역할 | 가중치 | 데이터 소스 | 업데이트 |
|-------|------|--------|------------|---------|
| **L1 퀀트 레이팅** | MOAT·VALUE·MOMENTUM·STABILITY | **50%** | FDR + SEC EDGAR | 매일 배치 |
| **L2 텍스트·감성** | 뉴스·어닝콜·내부자거래·애널리스트 | **25%** | Finnhub·FMP·SEC Form4 | 이벤트 즉시 |
| **L3 시장 신호** | 차트패턴·기술지표·공매도·거시 | **25%** | FDR·FINRA·FRED | 매일 |

---

## 🔌 API 통합 설계 — 목적별 단일 소스 원칙

| 용도 | API | 비용 | 신뢰도 | 비고 |
|------|-----|------|--------|------|
| OHLCV / 기술지표 | **FinanceDataReader (FDR)** | 무료 | ★★★★★ | US·KR·JP·CN·VN·BR 다국가 지원 |
| 미국 재무제표 | **SEC EDGAR XBRL** | 무료 | ★★★★★ | 법적 공시. 최고 신뢰도 |
| 한국 재무제표 | **DART Open API** | 무료 | ★★★★★ | Phase 2 |
| 일본 재무제표 | **EDINET API** | 무료 | ★★★★☆ | Phase 2 |
| 실시간 시세 | **KIS API** | 무료 | ★★★★★ | 상세 페이지 진입 시만 호출 |
| 시세 Fallback | yfinance | 무료 | ★★★☆☆ | KIS 실패 시만. 배치잡 사용 금지 |
| 뉴스 Sentiment | **Finnhub API** | 무료(100/일) | ★★★★☆ | Phase 2. FinBERT 로컬 결합 |
| 애널리스트 등급 | **FMP API** | $14+/mo | ★★★★★ | Phase 2 |
| 어닝콜 Transcript | **FMP API** | $14+/mo | ★★★★☆ | Phase 2 |
| 공매도 데이터 | **FINRA Short Volume** | 무료 | ★★★★★ | Phase 2. T+1 |
| 거시지표 (VIX) | **FRED API** | 무료 | ★★★★★ | Phase 3 |
| 내부자거래 | **SEC Form 4 (EDGAR)** | 무료 | ★★★★★ | Phase 2. 현 인프라 즉시 확장 |

---

## 🗺 WBS (Work Breakdown Structure)

### Phase 1 — 핵심 안정화 (1~4주) 🔴 최우선

| ID | 작업 | 상세 | 파일 | 이슈 |
|----|------|------|------|------|
| P1-01 | `/stocks` 속도 최적화 | KIS 제거 → DB close_price 직접 조회. **50초→1초** | `stock_routes.py` | [#1] |
| P1-02 | Connection Pool + 캐시 | `ThreadedConnectionPool`. `/sectors` **5초→0.1초** | `db_pool.py` (신규) | [#2] |
| P1-03 | 점수 일치화 | 배치↔실시간 통일. DB 직접 조회. **NVDA 90↔60점 해결** | `api_service.py` | [#3] |
| P1-04 | 섹터 Percentile | ROIC·GPA·EV/EBIT·FCF 섹터 내 Percentile 적용 | `sector_percentile.py` (신규) | [#4] |
| P1-05 | STABILITY 섹션 신설 | Low-Vol·EPS Stability·Dividend. TECH → Layer3 이동 | `calculator.py` | [#5] |

### Phase 2 — 텍스트·시장 신호 (5~10주) 🟠 높음

| ID | 작업 | 파일 |
|----|------|------|
| P2-01 | 뉴스 Sentiment (FinBERT) | `news_service.py` |
| P2-02 | 애널리스트 등급 추적 (FMP) | `analyst_service.py` |
| P2-03 | 내부자거래 SEC Form 4 | `insider_service.py` |
| P2-04 | 공매도 FINRA T+1 | `short_service.py` |
| P2-05 | 차트 패턴 Detection (8개) | `pattern_service.py` |
| P2-06 | 한국 시장 (DART + KRX) | `dart_service.py` |

### Phase 3 — AI·거시 신호 (11~16주) 🟡 중간

| ID | 작업 | 파일 |
|----|------|------|
| P3-01 | 어닝콜 Tone 분석 (Claude/GPT) | `earnings_nlp.py` |
| P3-02 | VIX·FRED 거시지표 연동 | `macro_service.py` |
| P3-03 | 섹터 ETF 자금 흐름 | `etf_flow_service.py` |
| P3-04 | 일본·인도 시장 추가 | `global_service.py` |

### Phase 4 — 글로벌 확장 (17~24주) 🟢 낮음

- 홍콩·베트남·브라질 시장 (HKEX·HOSE·B3)
- Put/Call 옵션 플로우 이상 탐지
- 통합 시그널 대시보드 고도화

### Phase 5 — ML 최적화 (6개월+) 🔵 장기

- XGBoost 백테스트 기반 팩터 가중치 학습
- Earnings Surprise 사전 예측 모델
- 국가별 AI 팩터 가중치 자동 최적화

---

## 📊 GitHub Project Board 설정

### Milestone 설정
```
Phase 1 → Due: +4주
Phase 2 → Due: +10주
Phase 3 → Due: +16주
Phase 4 → Due: +24주
```

### Label 설정
```
phase-1, phase-2, phase-3, phase-4, phase-5
backend, frontend, data-pipeline, infra
bug, enhancement, performance
priority-critical, priority-high, priority-medium, priority-low
```

### Issues 생성 예시 (Phase 1)

**Issue #1: [P1-01] /api/stocks 속도 최적화**
```
Labels: phase-1, backend, performance, priority-critical
Milestone: Phase 1

## 문제
/api/stocks 엔드포인트 응답 50초 소요
원인: 510개 티커 × KIS API 실시간 호출 (max_workers=15)

## 해결 방안
- KIS API 호출 완전 제거
- ticker_item.close_price DB 직접 조회로 교체
- 실시간 현재가는 상세 페이지(/price/:ticker)에서만

## 수정 파일
- backend/routes/stock_routes.py
- backend/services/api_service.py (get_multiple_realtime_prices 중복 제거)

## 목표 응답시간
50초 → 0.3초 이내
```

**Issue #2: [P1-02] Connection Pool + 캐시 적용**
```
Labels: phase-1, backend, performance, priority-critical
Milestone: Phase 1

## 문제
/api/sectors 5초 소요
원인: 요청마다 새 TCP 연결 수립 (2~4초 소요)

## 해결 방안
- psycopg2.pool.ThreadedConnectionPool 도입
- db_pool.py 신규 생성
- 섹터 데이터 TTL 1시간 캐시

## 수정 파일
- backend/services/db_pool.py (신규)
- backend/routes/stock_routes.py (PooledConnection 적용)
```

---

## 🚀 로컬 개발 환경 설정

```bash
# Backend
cd backend
pip install flask psycopg2-binary FinanceDataReader yfinance requests

# 환경변수 설정
cp secret_info/config.example.py secret_info/config.py
# DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD, KIS_APP_KEY 등 설정

# 서버 실행
python main.py

# Frontend
cd frontend
npm install
npm run dev
```

---

## 📈 등급 체계

| 등급 | 점수 | 투자 의견 |
|------|------|----------|
| **S** | ≥ 80 | Strong Buy |
| **A+** | ≥ 72 | Buy |
| **A** | ≥ 65 | Outperform |
| **B+** | ≥ 55 | Hold |
| **B** | ≥ 45 | Underperform |
| **C** | ≥ 35 | Sell |
| **D** | < 35 | Strong Sell |

---

## 🌏 글로벌 시장 확대 로드맵

| 시장 | Phase | 재무 소스 | OHLCV | 비고 |
|------|-------|----------|-------|------|
| 🇺🇸 미국 | Phase 1 (현재) | SEC EDGAR | FDR | 완료 |
| 🇰🇷 한국 | Phase 2 | DART API | FDR / KRX | 외국인·기관 수급 가능 |
| 🇯🇵 일본 | Phase 2 | EDINET | FDR | |
| 🇨🇳 중국·홍콩 | Phase 3 | HKEX CCASS | FDR | 공시 한계 |
| 🇮🇳 인도 | Phase 3 | NSE Filing | FDR | NSE API 우수 |
| 🇻🇳 베트남 | Phase 4 | SSI / Vietstock | FDR / HOSE | |
| 🇧🇷 브라질 | Phase 4 | CVM (SEC 유사) | FDR / B3 | |

---

*Last updated: 2025-03-09 · QUANT AI Project*