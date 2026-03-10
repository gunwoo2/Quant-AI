/**
 * Topbar.jsx — v3
 *
 * 수정:
 *  1. 종목수/배치시간 완전 제거 (사이드바 하단 중복)
 *  2. ADD TICKER: MarketStatus 바로 왼쪽에 위치
 */
import { useState } from "react";
import { C, FONT } from "../../styles/tokens";
import MarketStatus from "./MarketStatus";
import { AddTickerModal } from "../dashboard/Modals";
import logoImg from "../../assets/logo.png";

const TABS = [
  { key: "SCREENER", label: "SCREENER" },
  { key: "SIGNALS",  label: "SIGNALS"  },
  { key: "SECTORS",  label: "SECTORS"  },
  { key: "MARKET",   label: "MARKET"   },
];

export default function Topbar({ activeTab, onTabChange }) {
  const [showAdd, setShowAdd] = useState(false);

  return (
    <>
      <div style={{
        height: 52,
        background: "#0a0a0a",
        borderBottom: `1px solid ${C.border}`,
        display: "flex",
        alignItems: "center",
        flexShrink: 0,
        zIndex: 40,
      }}>

        {/* ── 1. 로고 */}
        <div style={{
          padding: "0 20px", // 여백을 조금 더 넓게 잡아 시원하게 구성
          fontFamily: "'Inter', sans-serif",
          fontSize: 14, // 가독성을 위해 살짝 키움
          fontWeight: 700,
          color: C.primary, 
          letterSpacing: 1.5,
          borderRight: `1px solid ${C.border}`,
          height: "100%",
          display: "flex", 
          alignItems: "center",
          gap: 10, // 이미지와 텍스트 간격
          whiteSpace: "nowrap", 
          flexShrink: 0,
        }}>
          <img 
            src={logoImg} 
            alt="Logo" 
            style={{ width: 22, height: 22, objectFit: "contain" }} 
          />
          <span style={{ marginTop: 1 }}> {/* 텍스트 수직 정렬 미세조정 */}
            QUANT AI
          </span>
        </div>

        {/* ── 2. 탭 */}
        <nav style={{ display: "flex", alignItems: "center", height: "100%", paddingLeft: 4, flex: 1 }}>
          {TABS.map(tab => (
            <TabBtn key={tab.key} label={tab.label}
              active={activeTab === tab.key}
              onClick={() => onTabChange(tab.key)}
            />
          ))}
        </nav>

        {/* ── 3. ADD TICKER (MarketStatus 바로 왼쪽) */}
        <div style={{ padding: "0 12px", height: "100%", display: "flex", alignItems: "center", borderRight: `1px solid ${C.border}`, flexShrink: 0 }}>
          <button
            onClick={() => setShowAdd(true)}
            style={{
              fontFamily: "'Inter', sans-serif",
              fontSize: 11, fontWeight: 700, letterSpacing: 0.5,
              color: "#fff", background: C.primary,
              border: "none", borderRadius: 3,
              padding: "7px 16px", cursor: "pointer",
              whiteSpace: "nowrap",
              transition: "background 0.15s",
            }}
            onMouseEnter={e => e.currentTarget.style.background = "#AD1B02"}
            onMouseLeave={e => e.currentTarget.style.background = C.primary}
          >
            + ADD TICKER
          </button>
        </div>

        {/* ── 4. MarketStatus (맨 오른쪽 끝) */}
        <div style={{
          padding: "0 16px", height: "100%",
          display: "flex", alignItems: "center",
          flexShrink: 0,
        }}>
          <MarketStatus />
        </div>
      </div>

      {showAdd && (
        <AddTickerModal
          onClose={() => setShowAdd(false)}
          onAdd={t => { console.log("추가:", t); setShowAdd(false); }}
        />
      )}
    </>
  );
}

function TabBtn({ label, active, onClick }) {
  const [hov, setHov] = useState(false);
  return (
    <button onClick={onClick}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        fontFamily: "'Inter', sans-serif",
        fontSize: 11, letterSpacing: 0.8,
        color: active ? C.primary : hov ? C.textPri : C.textMuted,
        background: "none", border: "none",
        borderBottom: active ? `2px solid ${C.primary}` : "2px solid transparent",
        height: "100%", padding: "0 16px",
        cursor: "pointer", transition: "color 0.12s, border-color 0.12s",
      }}
    >
      {label}
    </button>
  );
}