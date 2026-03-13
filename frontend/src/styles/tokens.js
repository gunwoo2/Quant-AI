/**
 * tokens.js — QUANT AI Design Tokens
 *
 * 색상 체계
 *   1순위 메인    : #D85604  (PwC Orange)
 *   2순위         : #AD1B02 · #E88D14 · #F3BE26
 *   3순위 포인트  : #E669A2 · #00F5FF
 *   상승 / Buy    : #00F5FF  (cyan)
 *   하락 / Sell   : #AD1B02  (scarlet)
 *   포인트 텍스트 : #E669A2  (pink)
 *   티커 hover    : #F3BE26  (yolk)
 *   나머지        : 블랙·그레이 다크모드
 */

export const C = {
  // ── 브랜드
  primary:  "#D85604",   // PwC Orange — 메인 강조
  scarlet:  "#AD1B02",   // 하락 · Sell · 위험
  golden:   "#E88D14",   // 보조 강조
  yolk:     "#F3BE26",   // 티커 hover
  pink:     "#E669A2",   // 포인트 텍스트 · TOP 티커
  cyan:     "#00F5FF",   // 상승 · Buy · 최상위 등급
  green:    "#00FF00",   // 상승 2순위
  red:      "#FF0033",   // 하락 2순위

  // ── 배경 / 서피스
  bgDeep:   "#000000",
  bgDark:   "#0f0f0f",
  surface:  "#111111",
  cardBg:   "#1a1a1a",

  // ── 테두리
  border:   "#2d2d2d",
  borderHi: "#3d3d3d",

  // ── 텍스트
  textPri:   "#e8e8e8",
  textGray:  "#a0a0a0",
  textMuted: "#555555",
  textcontent: "#b0b0b0",

  // ── 게이지 / 바
  gaugeTrack: "#2d2d2d",
  gaugebar: "#686868"
};

export const FONT = {
  mono: "'Courier New', monospace",
  sans: "'Inter', sans-serif",
};
 
/** 등급 → 색상 */
export const gradeColor = (g) => ({
  "S":  "#66ddee",
  "A+": "#F3BE26",
  "A":  "#F3BE26",
  "B+": "#D85604",
  "B":  "#D85604",
  "C":  "#7a0000",
  "D":  "#FF0033",
}[g] ?? C.textGray);
 
/** 등급 → 투자의견 레이블 */
export const gradeLabel = (g) => ({
  "S":  "Strong Buy",
  "A+": "Buy",
  "A":  "Outperform",
  "B+": "Hold",
  "B":  "Underperform",
  "C":  "Sell",
  "D":  "Strong Sell",
}[g] ?? "—");
 
/**
 * SECTORS — 섹터 목록
 *
 * 필드:
 *   key         : 프론트엔드 내부 키 (URL param 등으로 사용)
 *   label       : 한글 표시명
 *   en          : 영문 약칭 (UI 표시용)
 *   backendName : DB/API에서 반환되는 sector_name (JOIN 키)
 *   code        : GICS 섹터 코드 (API ?sector=45 필터용)
 *   icon        : 이모지 아이콘
 */
export const SECTORS = [
  { key: "TECHNOLOGY",        label: "정보통신기술",      en: "Technology",       backendName: "Information Technology",  code: "45", icon: "💻" },
  { key: "FINANCIALS",        label: "금융",              en: "Financials",       backendName: "Financials",              code: "40", icon: "🏦" },
  { key: "CONSUMER_CYCLICAL", label: "자유/경기 소비재",   en: "Consumer Cyc.",    backendName: "Consumer Discretionary",  code: "25", icon: "🛍" },
  { key: "REAL_ESTATE",       label: "부동산",             en: "Real Estate",      backendName: "Real Estate",             code: "60", icon: "🏢" },
  { key: "INDUSTRIALS",       label: "산업재",             en: "Industrials",      backendName: "Industrials",             code: "20", icon: "⚙️" },
  { key: "ENERGY",            label: "에너지",             en: "Energy",           backendName: "Energy",                  code: "10", icon: "⚡" },
  { key: "MATERIALS",         label: "원자재",             en: "Materials",        backendName: "Materials",               code: "15", icon: "🪨" },
  { key: "UTILITIES",         label: "유틸리티",           en: "Utilities",        backendName: "Utilities",               code: "55", icon: "🔌" },
  { key: "HEALTHCARE",        label: "헬스케어",           en: "Healthcare",       backendName: "Health Care",             code: "35", icon: "💊" },
  { key: "COMMUNICATION",     label: "통신서비스",          en: "Communication",    backendName: "Communication Services",  code: "50", icon: "📡" },
  { key: "CONSUMER_STAPLES",  label: "필수소비재",          en: "Consumer Sta.",    backendName: "Consumer Staples",        code: "30", icon: "🛒" },
];
 
/**
 * sectorByCode(gicsCode) — GICS 코드 → SECTORS 엔트리
 * 백엔드 /api/sectors 응답(key:"45")을 프론트 SECTORS와 매핑할 때 사용
 */
export const sectorByCode = (code) =>
  SECTORS.find(s => s.code === String(code)) ?? null;
 
/**
 * sectorByBackendName(name) — DB sector_name → SECTORS 엔트리
 * /api/stocks 응답(sector:"Information Technology")을 프론트 키로 매핑
 */
export const sectorByBackendName = (name) => {
  if (!name) return null;
  return (
    SECTORS.find(s => s.backendName === name) ??
    SECTORS.find(s => s.en.toLowerCase() === name.toLowerCase()) ??
    null
  );
};
 
// ── 섹터 통계 (하드코딩 Fallback — /api/sectors 실패 시 사용)
export const SECTOR_STATS = {
  TECHNOLOGY:        { count: 142, avgScore: 68.4, topTicker: "NVDA" },
  FINANCIALS:        { count:  89, avgScore: 61.2, topTicker: "JPM"  },
  CONSUMER_CYCLICAL: { count:  74, avgScore: 57.8, topTicker: "AMZN" },
  REAL_ESTATE:       { count:  38, avgScore: 48.1, topTicker: "PLD"  },
  INDUSTRIALS:       { count:  67, avgScore: 59.3, topTicker: "CAT"  },
  ENERGY:            { count:  45, avgScore: 55.6, topTicker: "XOM"  },
  MATERIALS:         { count:  29, avgScore: 52.9, topTicker: "FCX"  },
  UTILITIES:         { count:  22, avgScore: 44.3, topTicker: "NEE"  },
  HEALTHCARE:        { count:  91, avgScore: 60.7, topTicker: "LLY"  },
  COMMUNICATION:     { count:  33, avgScore: 63.1, topTicker: "META" },
  CONSUMER_STAPLES:  { count:  41, avgScore: 50.4, topTicker: "COST" },
};
 
// ── Mock 종목 데이터 (API 실패 Fallback)
export const MOCK_STOCKS = [
  { ticker:"ADBE",  name:"Adobe Inc.",                  country:"US", sector:"Information Technology", grade:"S",  score:80.2, l1:82, l2:77, l3:80, price:283.62,  chg:+0.15 },
  { ticker:"CF",    name:"CF Industries Holdings",      country:"US", sector:"Materials",              grade:"S",  score:79.1, l1:81, l2:76, l3:78, price:118.50,  chg:+2.35 },
  { ticker:"DECK",  name:"Deckers Outdoor Corp.",       country:"US", sector:"Consumer Discretionary", grade:"S",  score:78.4, l1:80, l2:74, l3:77, price:104.25,  chg:+0.24 },
  { ticker:"LULU",  name:"Lululemon Athletica Inc.",    country:"US", sector:"Consumer Discretionary", grade:"S",  score:77.8, l1:79, l2:73, l3:76, price:170.13,  chg:+0.14 },
  { ticker:"RL",    name:"Ralph Lauren Corporation",    country:"US", sector:"Consumer Discretionary", grade:"S",  score:77.2, l1:78, l2:75, l3:74, price:338.36,  chg: 0.00 },
  { ticker:"LRCX",  name:"Lam Research Corporation",   country:"US", sector:"Information Technology", grade:"A+", score:74.5, l1:78, l2:70, l3:72, price:195.51,  chg:-1.92 },
  { ticker:"CBOE",  name:"Cboe Global Markets",        country:"US", sector:"Financials",             grade:"A+", score:73.8, l1:75, l2:71, l3:73, price:301.27,  chg:+0.29 },
  { ticker:"DELL",  name:"Dell Technologies Inc.",     country:"US", sector:"Information Technology", grade:"A+", score:72.9, l1:76, l2:68, l3:70, price:146.48,  chg:+0.57 },
  { ticker:"PLTR",  name:"Palantir Technologies",      country:"US", sector:"Information Technology", grade:"A+", score:72.1, l1:74, l2:69, l3:71, price:154.38,  chg:-1.77 },
  { ticker:"RTX",   name:"RTX Corporation",            country:"US", sector:"Industrials",            grade:"A+", score:71.6, l1:73, l2:68, l3:72, price:209.76,  chg:-1.41 },
  { ticker:"FIX",   name:"Comfort Systems USA",        country:"US", sector:"Industrials",            grade:"A",  score:67.3, l1:70, l2:64, l3:65, price:1254.00, chg:-1.96 },
  { ticker:"AOS",   name:"A.O. Smith Corporation",     country:"US", sector:"Industrials",            grade:"A",  score:66.8, l1:68, l2:63, l3:67, price:71.01,   chg:-1.43 },
  { ticker:"NVDA",  name:"NVIDIA Corporation",         country:"US", sector:"Information Technology", grade:"S",  score:88.4, l1:91, l2:82, l3:88, price:875.20,  chg:+3.36 },
  { ticker:"JPM",   name:"JPMorgan Chase & Co.",       country:"US", sector:"Financials",             grade:"A",  score:65.1, l1:68, l2:67, l3:59, price:198.20,  chg:+0.50 },
  { ticker:"XOM",   name:"Exxon Mobil Corporation",    country:"US", sector:"Energy",                 grade:"B+", score:57.4, l1:62, l2:55, l3:51, price:112.30,  chg:-0.90 },
  { ticker:"TSLA",  name:"Tesla, Inc.",                country:"US", sector:"Consumer Discretionary", grade:"B",  score:48.3, l1:45, l2:49, l3:54, price:245.10,  chg:-2.80 },
  { ticker:"PFE",   name:"Pfizer Inc.",                country:"US", sector:"Health Care",            grade:"D",  score:28.1, l1:24, l2:31, l3:30, price:28.10,   chg:-3.10 },
];