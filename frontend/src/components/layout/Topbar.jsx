/**
 * TopBar.jsx
 * 상단 네비게이션 바
 * - 탭: SCREENER · SIGNALS · SECTORS · MARKET
 * - 우측: 미국/한국 장 시간 + 현재 시각
 */

import { useState } from "react";
import { C, FONT } from "../../styles/tokens";
import MarketStatus from "./MarketStatus";

const TABS = [
  { key: "SCREENER", label: "SCREENER" },
  { key: "SIGNALS",  label: "SIGNALS"  },
  { key: "SECTORS",  label: "SECTORS"  },
  { key: "MARKET",   label: "MARKET"   },
];

export default function TopBar({ activeTab, onTabChange }) {
  return (
    <div style={{
      height: 52,
      background: "#0a0a0a",
      borderBottom: `1px solid ${C.border}`,
      display: "flex",
      alignItems: "center",
      padding: "0 20px 0 0",
      flexShrink: 0,
      position: "sticky",
      top: 0,
      zIndex: 40,
    }}>
      {/* 헤더 타이틀 */}
      <div style={{
        padding: "0 20px",
        fontFamily: FONT.mono,
        fontSize: 10,
        color: C.textMuted,
        letterSpacing: 1.5,
        borderRight: `1px solid ${C.border}`,
        height: "100%",
        display: "flex",
        alignItems: "center",
        whiteSpace: "nowrap",
      }}>
        QUANT AI INTELLIGENCE DASHBOARD
      </div>

      {/* 탭 */}
      <nav style={{
        display: "flex",
        alignItems: "center",
        height: "100%",
        flex: 1,
        paddingLeft: 8,
      }}>
        {TABS.map(tab => (
          <TabBtn
            key={tab.key}
            label={tab.label}
            active={activeTab === tab.key}
            onClick={() => onTabChange(tab.key)}
          />
        ))}
      </nav>

      {/* 우측: 마켓 상태 */}
      <MarketStatus />
    </div>
  );
}

function TabBtn({ label, active, onClick }) {
  const [hovered, setHovered] = useState(false);
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        fontFamily: FONT.mono,
        fontSize: 11,
        letterSpacing: 0.8,
        color: active ? C.primary : hovered ? C.textPri : C.textMuted,
        background: "none",
        border: "none",
        borderBottom: active ? `2px solid ${C.primary}` : "2px solid transparent",
        height: "100%",
        padding: "0 16px",
        cursor: "pointer",
        transition: "color 0.12s, border-color 0.12s",
      }}
    >
      {label}
    </button>
  );
}