/**
 * MarketMarquee.jsx — v3 (TradingView Ticker Tape fallback)
 *
 * 전략:
 *  1순위: 백엔드 GET /api/market/indices (FinanceDataReader)
 *  2순위: API 실패/빈배열 → TradingView Ticker Tape 임베딩
 *  3순위: 하드코딩 fallback (완전 오프라인)
 *
 * ★ API 빈배열 시 5초 간격 최대 3회 재시도
 * ★ 5분마다 자동 갱신
 */

/**
 * MarketMarquee.jsx — v4 (TradingView Ticker Tape Only)
 *
 * ★ 100% TradingView 임베딩 — 백엔드 API 호출 없음
 * ★ 실시간 데이터, 자동 갱신, 안정적
 */

import { useEffect, useRef } from "react";
import { C } from "../../styles/tokens";

// ── TradingView Ticker Tape 심볼 목록 ──
const TV_SYMBOLS = [
  { proName: "FOREXCOM:SPXUSD",   title: "S&P 500" },
  { proName: "FOREXCOM:NSXUSD",   title: "NASDAQ" },
  { proName: "FOREXCOM:DJI",      title: "DOW" },
  { proName: "KRX:KOSPI",         title: "KOSPI" },
  { proName: "KRX:KOSDAQ",        title: "KOSDAQ" },
  { proName: "FX_IDC:USDKRW",    title: "USD/KRW" },
  { proName: "BITSTAMP:BTCUSD",   title: "BTC" },
  { proName: "BITSTAMP:ETHUSD",   title: "ETH" },
  { proName: "CBOE:VIX",          title: "VIX" },
  { proName: "TVC:GOLD",          title: "GOLD" },
  { proName: "TVC:USOIL",         title: "WTI" },
  { proName: "TVC:DXY",           title: "DXY" },
  { proName: "TVC:US10Y",         title: "US 10Y" },
  { proName: "TVC:US02Y",         title: "US 2Y" },
  { proName: "FX:EURUSD",         title: "EUR/USD" },
  { proName: "FX:USDJPY",         title: "USD/JPY" },
];

export default function MarketMarquee() {
  const containerRef = useRef(null);

  useEffect(() => {
    if (!containerRef.current) return;
    containerRef.current.innerHTML = "";

    const wrapper = document.createElement("div");
    wrapper.className = "tradingview-widget-container";

    const inner = document.createElement("div");
    inner.className = "tradingview-widget-container__widget";
    wrapper.appendChild(inner);

    const script = document.createElement("script");
    script.src =
      "https://s3.tradingview.com/external-embedding/embed-widget-ticker-tape.js";
    script.async = true;
    script.innerHTML = JSON.stringify({
      symbols: TV_SYMBOLS,
      showSymbolLogo: false,
      isTransparent: true,
      displayMode: "regular",
      colorTheme: "dark",
      locale: "en",
    });
    wrapper.appendChild(script);

    containerRef.current.appendChild(wrapper);

    return () => {
      if (containerRef.current) containerRef.current.innerHTML = "";
    };
  }, []);

  return (
    <div
      ref={containerRef}
      style={{
        width: "100%",
        height: 46,
        overflow: "hidden",
        background: C.bgDeeper,
        borderBottom: `1px solid ${C.border}`,
      }}
    />
  );
}


// API 호출 안함. 트뷰 임베딩으로 전환 (API 오류 너무많음)
// import { useState, useEffect, useRef, useCallback } from "react";
// import { C, FONT } from "../../styles/tokens";
// import api from "../../api";

// // ── Fallback 데이터 (API 완전 실패 시)
// const FALLBACK = [
//   { label: "S&P 500",   val: "—", chg: "—", up: true  },
//   { label: "NASDAQ",    val: "—", chg: "—", up: true  },
//   { label: "DOW",       val: "—", chg: "—", up: true  },
//   { label: "KOSPI",     val: "—", chg: "—", up: false },
//   { label: "KOSDAQ",    val: "—", chg: "—", up: false },
//   { label: "BTC/USD",   val: "—", chg: "—", up: true  },
//   { label: "ETH/USD",   val: "—", chg: "—", up: true  },
//   { label: "VIX",       val: "—", chg: "—", up: false },
//   { label: "GOLD",      val: "—", chg: "—", up: true  },
//   { label: "WTI OIL",   val: "—", chg: "—", up: false },
//   { label: "DXY",       val: "—", chg: "—", up: false },
//   { label: "10Y YIELD", val: "—", chg: "—", up: false },
// ];

// // ── TradingView Ticker Tape 심볼 목록
// const TV_SYMBOLS = [
//   { proName: "FOREXCOM:SPXUSD",  title: "S&P 500" },
//   { proName: "FOREXCOM:NSXUSD",  title: "NASDAQ" },
//   { proName: "FOREXCOM:DJI",     title: "DOW" },
//   { proName: "KRX:KOSPI",        title: "KOSPI" },
//   { proName: "KRX:KOSDAQ",       title: "KOSDAQ" },
//   { proName: "BITSTAMP:BTCUSD",  title: "BTC/USD" },
//   { proName: "BITSTAMP:ETHUSD",  title: "ETH/USD" },
//   { proName: "CBOE:VIX",         title: "VIX" },
//   { proName: "TVC:GOLD",         title: "GOLD" },
//   { proName: "TVC:USOIL",        title: "WTI OIL" },
//   { proName: "TVC:DXY",          title: "DXY" },
//   { proName: "TVC:US10Y",        title: "10Y YIELD" },
// ];

// /** API 응답 → 마켓 아이템 변환 */
// function formatItem(item) {
//   const val = item.val != null && item.val !== 0
//     ? Number(item.val).toLocaleString("en-US", { maximumFractionDigits: 2 })
//     : "—";
//   const chgNum = item.chg != null ? Number(item.chg) : null;
//   const chg = chgNum != null ? `${Math.abs(chgNum).toFixed(2)}%` : "—";
//   return { label: item.label, val, chgRaw: chgNum, chg, up: item.up };
// }


// /* ═══════════════════════════════════════
//    TradingView Ticker Tape (fallback UI)
//    ═══════════════════════════════════════ */
// function TVTickerTape() {
//   const containerRef = useRef(null);

//   useEffect(() => {
//     if (!containerRef.current) return;
//     // 기존 내용 클리어
//     containerRef.current.innerHTML = "";

//     const script = document.createElement("script");
//     script.src = "https://s3.tradingview.com/external-embedding/embed-widget-ticker-tape.js";
//     script.async = true;
//     script.innerHTML = JSON.stringify({
//       symbols: TV_SYMBOLS,
//       showSymbolLogo: false,
//       isTransparent: true,
//       displayMode: "regular",
//       colorTheme: "dark",
//       locale: "en",
//     });

//     const wrapper = document.createElement("div");
//     wrapper.className = "tradingview-widget-container";
//     const inner = document.createElement("div");
//     inner.className = "tradingview-widget-container__widget";
//     wrapper.appendChild(inner);
//     wrapper.appendChild(script);
//     containerRef.current.appendChild(wrapper);

//     return () => {
//       if (containerRef.current) containerRef.current.innerHTML = "";
//     };
//   }, []);

//   return (
//     <div ref={containerRef} style={{
//       width: "100%", height: 46, overflow: "hidden",
//       background: C.bgDeeper, borderBottom: `1px solid ${C.border}`,
//     }} />
//   );
// }


// /* ═══════════════════════════════════════
//    자체 Marquee (API 데이터)
//    ═══════════════════════════════════════ */
// function CustomMarquee({ items, paused, setPaused }) {
//   const doubled = [...items, ...items];
//   return (
//     <div
//       onMouseEnter={() => setPaused(true)}
//       onMouseLeave={() => setPaused(false)}
//       style={{
//         background: C.bgDeeper,
//         borderBottom: `1px solid ${C.border}`,
//         height: 30,
//         overflow: "hidden",
//         position: "relative",
//         width: "100%",
//         maxWidth: "100vw",
//         flexShrink: 0,
//         boxSizing: "border-box",
//       }}
//     >
//       {/* 좌우 페이드 마스크 */}
//       <div style={{
//         position: "absolute", left: 0, top: 0, bottom: 0, width: 40, zIndex: 2,
//         background: `linear-gradient(to right, ${C.bgDeeper}, transparent)`,
//         pointerEvents: "none",
//       }} />
//       <div style={{
//         position: "absolute", right: 0, top: 0, bottom: 0, width: 40, zIndex: 2,
//         background: `linear-gradient(to left, ${C.bgDeeper}, transparent)`,
//         pointerEvents: "none",
//       }} />

//       <style>{`
//         @keyframes marquee-scroll {
//           0%   { transform: translateX(0); }
//           100% { transform: translateX(-50%); }
//         }
//         .mq-track {
//           display: flex;
//           align-items: center;
//           height: 100%;
//           width: max-content;
//           animation: marquee-scroll 80s linear infinite;
//           will-change: transform;
//         }
//         .mq-track.paused { animation-play-state: paused; }
//       `}</style>

//       <div className={`mq-track${paused ? " paused" : ""}`}>
//         {doubled.map((item, i) => (
//           <div key={i} style={{
//             display: "flex", alignItems: "center", gap: 6,
//             padding: "0 18px",
//             borderRight: `1px solid ${C.border}`,
//             height: "100%", whiteSpace: "nowrap", cursor: "default",
//           }}>
//             <span style={{ fontFamily: FONT.sans, fontSize: 10, color: C.textSec, letterSpacing: 0.5 }}>
//               {item.label}
//             </span>
//             <span style={{ fontFamily: FONT.mono, fontSize: 11, fontWeight: 600, color: C.textPri }}>
//               {item.val}
//             </span>
//             {item.chgRaw != null && (
//               <span style={{
//                 fontFamily: FONT.mono, fontSize: 10, fontWeight: 600,
//                 color: item.up ? C.up : C.down,
//               }}>
//                 {item.up ? "▲" : "▼"} {item.chg}
//               </span>
//             )}
//           </div>
//         ))}
//       </div>
//     </div>
//   );
// }


// /* ═══════════════════════════════════════
//    메인 MarketMarquee
//    ═══════════════════════════════════════ */
// export default function MarketMarquee() {
//   const [items, setItems]     = useState(FALLBACK);
//   const [paused, setPaused]   = useState(false);
//   const [useTV, setUseTV]     = useState(false);     // TradingView fallback 사용 여부
//   const [apiOk, setApiOk]     = useState(false);     // API 데이터 수신 성공 여부
//   const retryRef              = useRef(0);
//   const intervalRef           = useRef(null);

//   const fetchIndices = useCallback(() => {
//     api.get("/api/market/indices")
//       .then(res => {
//         if (Array.isArray(res.data) && res.data.length > 0) {
//           // val이 전부 0이면 아직 캐시 미완성
//           const hasReal = res.data.some(d => d.val != null && d.val !== 0);
//           if (hasReal) {
//             setItems(res.data.map(formatItem));
//             setApiOk(true);
//             setUseTV(false);
//             retryRef.current = 0;
//           } else {
//             // 백엔드 캐시 빌딩 중 → 재시도
//             throw new Error("cache_building");
//           }
//         } else {
//           // 빈 배열 → 캐시 아직 없음, 재시도
//           throw new Error("empty");
//         }
//       })
//       .catch(() => {
//         retryRef.current += 1;
//         if (retryRef.current <= 3) {
//           // 5초 후 재시도
//           setTimeout(fetchIndices, 5000);
//         } else {
//           // 3회 실패 → TradingView Ticker Tape로 전환
//           console.log("[MarketMarquee] API 실패 3회 → TradingView Ticker Tape 전환");
//           setUseTV(true);
//         }
//       });
//   }, []);

//   useEffect(() => {
//     fetchIndices();
//     // 5분마다 갱신 (API 성공 이후)
//     intervalRef.current = setInterval(() => {
//       retryRef.current = 0;
//       fetchIndices();
//     }, 5 * 60 * 1000);
//     return () => clearInterval(intervalRef.current);
//   }, [fetchIndices]);

//   // TradingView fallback
//   if (useTV && !apiOk) {
//     return <TVTickerTape />;
//   }

//   // 자체 Marquee (API 데이터 or fallback)
//   return <CustomMarquee items={items} paused={paused} setPaused={setPaused} />;
// }
