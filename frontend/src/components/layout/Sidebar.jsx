/**
 * Sidebar.jsx
 *
 * 수정 사항
 *   1. API STATUS 색상 → 그레이(#555) + D85604(primary) 2색만 사용
 *   2. 전체 폰트 Inter
 *   3. 글자 크기 업
 */

import { useState } from "react";
import { C, FONT, SECTORS, SECTOR_STATS } from "../../styles/tokens";

const W_OPEN  = 210;
const W_CLOSE = 54;

export default function Sidebar({ activeSector, onSectorClick }) {
  const [open,        setOpen]        = useState(true);
  const [showFlyout,  setShowFlyout]  = useState(false);

  return (
    <aside style={{
      width:    open ? W_OPEN : W_CLOSE,
      minWidth: open ? W_OPEN : W_CLOSE,
      height:   "100%",
      background: "#0a0a0a",
      borderRight: `1px solid ${C.border}`,
      display: "flex", flexDirection: "column",
      transition: "width 0.2s ease",
      position: "relative", zIndex: 50,
      flexShrink: 0, overflow: "visible",
      fontFamily: "'Inter', sans-serif",
    }}>

      {/* ── 로고 + 토글 */}
      <div style={{
        display: "flex", alignItems: "center",
        justifyContent: open ? "space-between" : "center",
        padding: open ? "0 14px" : 0,
        height: 52, borderBottom: `1px solid ${C.border}`,
        flexShrink: 0,
      }}>
        {open && (
          <span style={{
            fontFamily: "'Inter', sans-serif",
            fontSize: 14, fontWeight: 1000,
            color: C.textGray, letterSpacing: 2,
          }}>
            SIDE BAR
          </span>
        )}
        <button onClick={() => setOpen(v => !v)} style={{
          background: "none", border: "none",
          color: C.textGray, cursor: "pointer",
          padding: 8, fontSize: 15, lineHeight: 1,
        }}>
          {open ? "✕" : "☰"}
        </button>
      </div>

      {/* ── 메뉴 */}
      <nav style={{ flex: 1, padding: "6px 0", overflow: "visible" }}>

        {/* HOME */}
        <NavItem icon="🏠" label="HOME" open={open}
          onClick={() => window.open(window.location.origin + "/main", "_blank")} />

        {/* SECTORS + flyout */}
        <div style={{ position: "relative" }}
          onMouseEnter={() => setShowFlyout(true)}
          onMouseLeave={() => setShowFlyout(false)}
        >
          <NavItem icon="📊" label="SECTORS" open={open}
            active={!!activeSector} arrow={open} />
          {showFlyout && (
            <SectorFlyout
              activeSector={activeSector}
              onSelect={(key) => { onSectorClick?.(key); setShowFlyout(false); }}
            />
          )}
        </div>

        {/* HEATMAP */}
        <NavItem icon="🔥" label="HEATMAP" open={open}
          onClick={() => window.open("https://finviz.com/map.ashx", "_blank")} />

        {/* 구분선 */}
        <div style={{ height: 1, background: C.border, margin: open ? "10px 14px" : "10px 10px" }} />

        {/* API STATUS 타이틀 */}
        {open && (
          <div style={{
            fontSize: 10, color: C.textMuted,
            letterSpacing: 1.5, padding: "4px 14px 8px",
            fontFamily: "'Inter', sans-serif",
          }}>
            API STATUS
          </div>
        )}

        {/* API 항목 — 그레이 + primary 2색만 */}
        {[
          { label: "FDR",       status: "OK",   ok: true  },
          { label: "SEC EDGAR", status: "OK",   ok: true  },
          { label: "KIS API",   status: "OK",   ok: true  },
          { label: "DART (KR)", status: "IDLE", ok: false },
          { label: "FINRA",     status: "T+1",  ok: false },
          { label: "FRED API",  status: "OK",   ok: true  },
        ].map(a => (
          <div key={a.label} style={{
            display: "flex", alignItems: "center",
            justifyContent: open ? "space-between" : "center",
            padding: open ? "3px 14px" : "4px 0",
          }}>
            {open && (
              <span style={{ fontSize: 11, color: C.textMuted }}>
                {a.label}
              </span>
            )}
            <span style={{
              fontFamily: "'Inter', sans-serif",
              fontSize: 10, fontWeight: 700,
              // OK → primary(D85604) / 나머지 → 그레이
              color: a.ok ? C.primary : "#555555",
            }}>
              ●{open ? ` ${a.status}` : ""}
            </span>
          </div>
        ))}
      </nav>

      {/* ── 배치 정보
      {open && (
        <div style={{
          borderTop: `1px solid ${C.border}`,
          padding: "8px 14px",
          fontSize: 11, color: C.textMuted, lineHeight: 1.7,
        }}>
          <div>종목 <span style={{ color: C.textGray }}>510개</span></div>
          <div>배치 <span style={{ color: C.textGray }}>03-09 02:14</span></div>
        </div>
      )} */}
    </aside>
  );
}

/* ── NavItem ──────────────────────────────────── */
function NavItem({ icon, label, open, active, arrow, onClick }) {
  const [hov, setHov] = useState(false);
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        display: "flex", alignItems: "center", gap: 10,
        width: "100%",
        padding: open ? "10px 14px" : "11px 0",
        justifyContent: open ? "flex-start" : "center",
        background: active ? `${C.primary}18` : hov ? "#1a1a1a" : "none",
        border: "none",
        borderLeft: active ? `2px solid ${C.primary}` : "2px solid transparent",
        cursor: "pointer", transition: "background 0.12s",
      }}
    >
      <span style={{ fontSize: 15, flexShrink: 0 }}>{icon}</span>
      {open && (
        <>
          <span style={{
            fontFamily: "'Inter', sans-serif",
            fontSize: 13, fontWeight: 500, flex: 1,
            color: active ? C.primary : hov ? "#e8e8e8" : C.textGray,
          }}>
            {label}
          </span>
          {arrow && <span style={{ fontSize: 10, color: C.textMuted }}>›</span>}
        </>
      )}
    </button>
  );
}

/* ── SectorFlyout ─────────────────────────────── */
function SectorFlyout({ activeSector, onSelect }) {
  return (
    <div style={{
      position: "absolute", left: "100%", top: 0,
      width: 310,
      background: "#0d0d0d",
      border: `1px solid ${C.border}`,
      borderLeft: `2px solid ${C.primary}`,
      borderRadius: "0 4px 4px 0",
      boxShadow: "6px 0 28px rgba(0,0,0,0.85)",
      zIndex: 200, overflow: "hidden",
      animation: "flyoutIn 0.15s ease",
      fontFamily: "'Inter', sans-serif",
    }}>
      <style>{`
        @keyframes flyoutIn {
          from { opacity: 0; transform: translateX(-8px); }
          to   { opacity: 1; transform: translateX(0); }
        }
      `}</style>

      <div style={{
        padding: "10px 14px",
        borderBottom: `1px solid ${C.border}`,
        fontFamily: "'Inter', sans-serif",
        fontSize: 11, color: C.primary,
        letterSpacing: 1, fontWeight: 700,
      }}>
        SECTORS
      </div>

      <div style={{
        display: "grid", gridTemplateColumns: "1fr 46px 54px 56px",
        padding: "5px 14px",
        fontFamily: "'Inter', sans-serif",
        fontSize: 10, color: C.textMuted,
        borderBottom: `1px solid ${C.border}`,
      }}>
        <span>섹터</span>
        <span style={{ textAlign: "right" }}>종목</span>
        <span style={{ textAlign: "right" }}>Avg</span>
        <span style={{ textAlign: "right" }}>TOP</span>
      </div>

      {SECTORS.map(s => (
        <SectorRow key={s.key} sector={s} stat={SECTOR_STATS[s.key]}
          active={activeSector === s.key}
          onSelect={onSelect} />
      ))}
    </div>
  );
}

function SectorRow({ sector, stat, active, onSelect }) {
  const [hov, setHov] = useState(false);
  // Avg 점수 색: 높으면 cyan, 중간 golden, 낮으면 scarlet
  const scoreColor =
    stat.avgScore >= 65 ? C.cyan :
    stat.avgScore >= 50 ? C.golden : C.scarlet;

  return (
    <button
      onClick={() => onSelect(sector.key)}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        display: "grid", gridTemplateColumns: "1fr 46px 54px 56px",
        padding: "8px 14px", width: "100%",
        background: active ? `${C.primary}18` : hov ? "#1a1a1a" : "none",
        border: "none",
        borderLeft: active ? `2px solid ${C.primary}` : "2px solid transparent",
        borderBottom: `1px solid ${C.border}20`,
        cursor: "pointer", textAlign: "left",
        transition: "background 0.1s",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
        <span style={{ fontSize: 12 }}>{sector.icon}</span>
        <div>
          <div style={{
            fontSize: 12,
            color: active ? C.primary : hov ? "#e8e8e8" : C.textGray,
            fontWeight: active ? 600 : 400,
          }}>
            {sector.label}
          </div>
          <div style={{
            fontFamily: "'Inter', sans-serif",
            fontSize: 9, color: C.textMuted,
          }}>
            {sector.en}
          </div>
        </div>
      </div>
      <div style={{
        fontFamily: "'Inter', sans-serif",
        fontSize: 11, color: C.textGray, textAlign: "right",
      }}>
        {stat.count}
      </div>
      <div style={{
        fontFamily: "'Inter', sans-serif",
        fontSize: 11, color: scoreColor,
        fontWeight: 700, textAlign: "right",
      }}>
        {stat.avgScore}
      </div>
      <div style={{
        fontFamily: "'Inter', sans-serif",
        fontSize: 11, color: C.pink, textAlign: "right",
      }}>
        {stat.topTicker}
      </div>
    </button>
  );
}