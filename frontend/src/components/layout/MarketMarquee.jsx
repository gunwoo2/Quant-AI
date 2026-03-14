/**
 * MarketMarquee.jsx — v2 (백엔드 API 연결)
 *
 * GET /api/market/indices
 *   { symbol, label, category, val, chg, up }
 *   category: US_INDEX | KR_INDEX | GLOBAL_INDEX | FX | BOND | COMMODITY | CRYPTO
 *
 * - API 성공 시 실시간 데이터 표시
 * - API 실패 시 하드코딩 Fallback
 * - 5분마다 자동 갱신
 */

import { useState, useEffect, useRef } from "react";
import { C, FONT } from "../../styles/tokens";
import api from "../../api";

// ── Fallback 데이터 (API 실패 시 사용)
const FALLBACK = [
  { label: "S&P 500",   val: "—",     chg: "—",     up: true  },
  { label: "NASDAQ",    val: "—",     chg: "—",     up: true  },
  { label: "DOW",       val: "—",     chg: "—",     up: true  },
  { label: "KOSPI",     val: "—",     chg: "—",     up: false },
  { label: "KOSDAQ",    val: "—",     chg: "—",     up: false },
  { label: "BTC/USD",   val: "—",     chg: "—",     up: true  },
  { label: "ETH/USD",   val: "—",     chg: "—",     up: true  },
  { label: "VIX",       val: "—",     chg: "—",     up: false },
  { label: "GOLD",      val: "—",     chg: "—",     up: true  },
  { label: "WTI OIL",   val: "—",     chg: "—",     up: false },
  { label: "DXY",       val: "—",     chg: "—",     up: false },
  { label: "10Y YIELD", val: "—",     chg: "—",     up: false },
];

/** API 응답 → 마켓 아이템 변환 */
function formatItem(item) {
  const val = item.val != null
    ? Number(item.val).toLocaleString("en-US", { maximumFractionDigits: 2 })
    : "—";
  const chgNum = item.chg != null ? Number(item.chg) : null;
  const chg = chgNum != null ? `${Math.abs(chgNum).toFixed(2)}%` : "—";

  return { label: item.label, val, chgRaw: chgNum, chg, up: item.up };
}

export default function MarketMarquee() {
  const [items, setItems]   = useState(FALLBACK);
  const [paused, setPaused] = useState(false);
  const intervalRef = useRef(null);

  const fetchIndices = () => {
    api.get("/api/market/indices")
      .then(res => {
        if (Array.isArray(res.data) && res.data.length > 0) {
          setItems(res.data.map(formatItem));
        }
      })
      .catch(() => {
        // fallback 유지
      });
  };

  useEffect(() => {
    fetchIndices();
    // 5분마다 갱신
    intervalRef.current = setInterval(fetchIndices, 5 * 60 * 1000);
    return () => clearInterval(intervalRef.current);
  }, []);

  // 두 배로 복제해서 끊김없는 무한 스크롤
  const doubled = [...items, ...items];

  return (
    <div
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      style={{
        background: "#0a0a0a",
        borderBottom: `1px solid ${C.border}`,
        height: 30,
        // 중요: 가로 스크롤 방지를 위한 핵심 설정
        overflow: "hidden", 
        position: "relative",
        width: "100%",
        maxWidth: "100vw", // 브라우저 너비를 절대 넘지 못하게 차단
        flexShrink: 0,
        boxSizing: "border-box"
      }}
    >
      {/* 좌우 페이드 마스크 */}
      <div style={{
        position: "absolute", left: 0, top: 0, bottom: 0, width: 40, zIndex: 2,
        background: "linear-gradient(to right, #0a0a0a, transparent)",
        pointerEvents: "none",
      }} />
      <div style={{
        position: "absolute", right: 0, top: 0, bottom: 0, width: 40, zIndex: 2,
        background: "linear-gradient(to left, #0a0a0a, transparent)",
        pointerEvents: "none",
      }} />

      <style>{`
        @keyframes marquee {
          0%   { transform: translateX(0); }
          100% { transform: translateX(-50%); }
        }
        .marquee-track {
          display: flex;
          align-items: center;
          height: 100%;
          width: max-content;
          animation: marquee 80s linear infinite;
          will-change: transform;
        }
        .marquee-track.paused { animation-play-state: paused; }
      `}</style>

      <div className={`marquee-track${paused ? " paused" : ""}`}>
        {doubled.map((item, i) => (
          <div key={i} style={{
            display: "flex", alignItems: "center", gap: 6,
            padding: "0 18px",
            borderRight: `1px solid ${C.border}`,
            height: "100%", whiteSpace: "nowrap", cursor: "default",
          }}>
            <span style={{ fontFamily: FONT.sans, fontSize: 10, color: C.textcontent, letterSpacing: 0.5 }}>
              {item.label}
            </span>
            <span style={{ fontFamily: FONT.mono, fontSize: 11, fontWeight: 600, color: C.textPri }}>
              {item.val}
            </span>
            {item.chgRaw != null && (
              <span style={{
                fontFamily: FONT.mono, fontSize: 10, fontWeight: 600,
                color: item.up ? C.cyan : C.scarlet,
              }}>
                {item.up ? "▲" : "▼"} {item.chg}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}