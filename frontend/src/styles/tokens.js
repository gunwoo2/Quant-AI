/**
 * tokens.js — QUANT AI Design Tokens v2
 *
 * ★ 모든 컴포넌트는 이 파일의 C 객체만 참조할 것
 * ★ 하드코딩 색상 금지 — C.up / C.down / gradeColor() / chgColor() 사용
 *
 * 색상 체계 (PwC Orange 기반)
 *   메인       : #D85604 (PwC Orange)
 *   보조       : #E88D14 · #F3BE26
 *   포인트     : #E669A2 (pink) · #00F5FF (cyan)
 *   상승/하락  : 한국식 (#FF4444 빨강 / #3B82F6 파랑)
 *   등급       : 오렌지 채도 그라데이션 (S 골드 → D 차콜)
 */

export const C = {
  // ── 브랜드 (PwC)
  primary:  "#D85604",   // PwC Orange — 메인 강조
  golden:   "#E88D14",   // 골든 오렌지 — 보조 강조
  yolk:     "#F3BE26",   // 욜크 — 티커 hover · 차트 포인트

  // ── 포인트 액센트
  pink:     "#E669A2",   // 핑크 — TOP 티커 · 하이라이트
  cyan:     "#00F5FF",   // 사이안 — 포인트 강조 · 링크 · 배지

  // ── 상승 / 하락 (한국식)
  up:       "#FF4444",   // 상승 · 매수 — 밝은 빨강
  down:     "#3B82F6",   // 하락 · 매도 — 밝은 파랑
  neutral:  "#888888",   // 무변동 · 중립
  // 연한 버전 (배경·차트 fill용)
  upDim:    "#FF444433", // 상승 배경 (투명)
  downDim:  "#3B82F633", // 하락 배경 (투명)

  // ── 등급 전용 (오렌지 채도 그라데이션)
  gradeS:   "#00F5FF",   // S  — 사이안 (최상위 등급) ✦
  gradeAP:  "#E88D14",   // A+ — 골든 오렌지
  gradeA:   "#D85604",   // A  — PwC 오렌지
  gradeBP:  "#A0653A",   // B+ — 브론즈
  gradeB:   "#6B5B4E",   // B  — 옅은 브라운
  gradeC:   "#555555",   // C  — 다크 그레이
  gradeD:   "#3A3A3A",   // D  — 차콜

  // ── 배경 / 서피스 (어두운 순서)
  bgDeeper:  "#080808",  // 가장 깊은 배경
  bgDeep:    "#000000",  // body 배경
  bgDark:    "#0f0f0f",  // 일반 배경
  surface:   "#111111",  // 카드 위 서피스
  surfaceAlt:"#161616",  // 서피스 대안
  cardBg:    "#1a1a1a",  // 카드 배경
  surfaceHi: "#252525",  // 강조 서피스 (hover)

  // ── 테두리
  border:   "#2d2d2d",   // 기본 테두리
  borderHi: "#3d3d3d",   // 강조 테두리

  // ── 텍스트
  textPri:     "#e8e8e8", // 기본 텍스트
  textSec:     "#b0b0b0", // 보조 텍스트
  textGray:    "#a0a0a0", // 회색 텍스트
  textMuted:   "#555555", // 비활성 텍스트
  textContent: "#b0b0b0", // 컨텐츠 본문

  // ── 게이지 / 바
  gaugeTrack: "#2d2d2d",
  gaugeBar:   "#686868",

  // ── 인풋 / 컨트롤
  inputBg:     "#0a0a0a",  // input 배경
  inputBorder: "#333333",  // input 테두리
  labelColor:  "#666666",  // 라벨 텍스트
  white:       "#FFFFFF",  // 순백
};

export const FONT = {
  mono: "'IBM Plex Mono', 'Courier New', monospace",
  sans: "'Inter', -apple-system, sans-serif",
};


// ═══════════════════════════════════════════
//  유틸리티 함수
// ═══════════════════════════════════════════

/** 등급 → 색상 (오렌지 그라데이션) */
export const gradeColor = (g) => ({
  "S":  C.gradeS,
  "A+": C.gradeAP,
  "A":  C.gradeA,
  "B+": C.gradeBP,
  "B":  C.gradeB,
  "C":  C.gradeC,
  "D":  C.gradeD,
}[g] ?? C.textGray);

/** 등급 → 텍스트 색상 (배지 위 글자) */
export const gradeTextColor = (g) => {
  if (["S","A+","A"].includes(g)) return "#000000";
  return "#FFFFFF";
};

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

/** 등락률 → 색상 (한국식: 양수=빨강, 음수=파랑) */
export const chgColor = (v) => {
  if (v == null) return C.textGray;
  const n = Number(v);
  if (n > 0) return C.up;
  if (n < 0) return C.down;
  return C.neutral;
};

/** 투자의견 텍스트 색상 — S/A+ = cyan 포인트, 이하 = 등급색 */
export const signalColor = (g) => ({
  "S":  C.cyan,
  "A+": C.pink,
  "A":  C.primary,
  "B+": C.golden,
  "B":  C.gradeBP,
  "C":  C.gradeC,
  "D":  C.gradeD,
}[g] ?? C.textGray);


// ═══════════════════════════════════════════
//  섹터 / Mock 데이터
// ═══════════════════════════════════════════

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

export const sectorByCode = (code) =>
  SECTORS.find(s => s.code === String(code)) ?? null;

export const sectorByBackendName = (name) => {
  if (!name) return null;
  const lower = name.toLowerCase().trim();
  return SECTORS.find(s => s.backendName.toLowerCase() === lower) ?? null;
};

export const MOCK_STOCKS = [
  { ticker:"NVDA", name:"NVIDIA Corp",              sector:"Information Technology", country:"US", price:875.20, chg:3.36,  l1:91, l2:82, l3:88, score:88.4, grade:"S",  signal:"Strong Buy" },
  { ticker:"AAPL", name:"Apple Inc",                 sector:"Information Technology", country:"US", price:192.50, chg:1.24,  l1:78, l2:71, l3:75, score:76.2, grade:"A+", signal:"Buy" },
  { ticker:"MSFT", name:"Microsoft Corp",             sector:"Information Technology", country:"US", price:415.80, chg:-0.87, l1:72, l2:68, l3:70, score:71.0, grade:"A",  signal:"Outperform" },
  { ticker:"TSLA", name:"Tesla Inc",                  sector:"Consumer Discretionary", country:"US", price:178.30, chg:-2.15, l1:55, l2:48, l3:52, score:52.3, grade:"B+", signal:"Hold" },
  { ticker:"INTC", name:"Intel Corp",                 sector:"Information Technology", country:"US", price:32.50,  chg:-0.45, l1:42, l2:38, l3:40, score:41.8, grade:"B",  signal:"Underperform" },
];


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
