/**
 * MarketMarquee.jsx
 * 상단 마켓 지수 Marquee 바
 * S&P500, NASDAQ, KOSPI, KOSDAQ, BTC, ETH, VIX, GOLD, SILVER, OIL, DXY
 */

import { useState, useEffect } from "react";
import { C, FONT } from "../../styles/tokens";

const INDICES = [
  { label: "S&P 500",  val: "5,234.18", chg: "+0.89%", up: true  },
  { label: "NASDAQ",   val: "18,892.42",chg: "+1.24%", up: true  },
  { label: "DOW",      val: "39,118.86",chg: "+0.42%", up: true  },
  { label: "KOSPI",    val: "2,641.39", chg: "-0.31%", up: false },
  { label: "KOSDAQ",   val: "874.25",   chg: "+0.18%", up: true  },
  { label: "BTC/USD",  val: "$67,240",  chg: "+2.14%", up: true  },
  { label: "ETH/USD",  val: "$3,512",   chg: "+1.87%", up: true  },
  { label: "VIX",      val: "18.23",    chg: "-4.10%", up: false },
  { label: "GOLD",     val: "$2,312",   chg: "+0.34%", up: true  },
  { label: "SILVER",   val: "$27.14",   chg: "+0.61%", up: true  },
  { label: "WTI OIL",  val: "$79.42",   chg: "-0.88%", up: false },
  { label: "DXY",      val: "103.42",   chg: "-0.21%", up: false },
  { label: "10Y YIELD",val: "4.28%",    chg: "+0.04%", up: false },
  { label: "NIKKEI",   val: "38,820",   chg: "+0.55%", up: true  },
  { label: "HSI",      val: "16,742",   chg: "-0.72%", up: false },
];

export default function MarketMarquee() {
  // 실제 구현 시: API에서 실시간 데이터 fetch
  const items = [...INDICES, ...INDICES]; // 무한 루프용 복제

  return (
    <div style={{
      background: "#0a0a0a",
      borderBottom: `1px solid ${C.border}`,
      height: 30,
      overflow: "hidden",
      position: "relative",
    }}>
      {/* 좌우 페이드 마스크 */}
      <div style={{
        position: "absolute", left: 0, top: 0, bottom: 0, width: 40,
        background: "linear-gradient(to right, #0a0a0a, transparent)",
        zIndex: 2,
      }} />
      <div style={{
        position: "absolute", right: 0, top: 0, bottom: 0, width: 40,
        background: "linear-gradient(to left, #0a0a0a, transparent)",
        zIndex: 2,
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
          animation: marquee 60s linear infinite;
        }
        .marquee-track:hover {
          animation-play-state: paused;
        }
      `}</style>

      <div className="marquee-track">
        {items.map((item, i) => (
          <div key={i} style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            padding: "0 20px",
            borderRight: `1px solid ${C.border}`,
            height: "100%",
            whiteSpace: "nowrap",
            cursor: "default",
          }}>
            <span style={{
              fontFamily: FONT.mono,
              fontSize: 10,
              color: C.textMuted,
              letterSpacing: 0.5,
            }}>
              {item.label}
            </span>
            <span style={{
              fontFamily: FONT.mono,
              fontSize: 11,
              fontWeight: 600,
              color: C.textPri,
            }}>
              {item.val}
            </span>
            <span style={{
              fontFamily: FONT.mono,
              fontSize: 10,
              fontWeight: 600,
              color: item.up ? C.green : C.red,
            }}>
              {item.up ? "▲" : "▼"} {item.chg}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}