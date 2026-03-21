/**
 * Sidebar.jsx — v2 (백엔드 API 연결)
 *
 * GET /api/sectors
 *   { key(GICS code), en, ko, stock_count, avg_score, top_grade }
 *
 * - API 성공 시 실제 종목 수·평균 점수 표시
 * - API 실패 시 SECTOR_STATS fallback
 * - sectorByCode()로 GICS code → 프론트 SECTORS 키 매핑
 */

import { useState, useEffect } from "react";
import { C, FONT, SECTORS, SECTOR_STATS, sectorByCode } from "../../styles/tokens";
import api from "../../api";

const W_OPEN  = 210;
const W_CLOSE = 54;

export default function Sidebar({ activeSector, onSectorClick }) {
  const [open,       setOpen]       = useState(true);
  const [showFlyout, setShowFlyout] = useState(false);
  // key: frontendKey(예: "TECHNOLOGY"), value: { count, avgScore, topGrade }
  const [sectorStats, setSectorStats] = useState(null);

  useEffect(() => {
    api.get("/api/sectors")
      .then(res => {
        if (!Array.isArray(res.data) || res.data.length === 0) return;
        const map = {};
        res.data.forEach(item => {
          // item.key 는 GICS 코드 ("45") 또는 영문명일 수 있음
          const matched = sectorByCode(item.key) ??
            SECTORS.find(s => s.en.toLowerCase() === String(item.en ?? "").toLowerCase());
          if (!matched) return;
          map[matched.key] = {
            count:    item.stock_count ?? 0,
            avgScore: item.avg_score   != null ? Number(item.avg_score).toFixed(1) : "—",
            topGrade: item.top_grade   ?? "—",
          };
        });
        setSectorStats(map);
      })
      .catch(() => {
        // SECTOR_STATS fallback: topTicker → topGrade 없음, 그대로 사용
        setSectorStats(null);
      });
  }, []);

  // sectorStats가 없으면 SECTOR_STATS 기반 fallback 구성
  const getStatFor = (key) => {
    if (sectorStats && sectorStats[key]) {
      const s = sectorStats[key];
      return { count: s.count, avgScore: s.avgScore, top: s.topGrade };
    }
    // Fallback
    const fb = SECTOR_STATS[key];
    if (!fb) return { count: 0, avgScore: "—", top: "—" };
    return { count: fb.count, avgScore: fb.avgScore, top: fb.topTicker };
  };

  return (
    <aside style={{
      width:    open ? W_OPEN : W_CLOSE,
      minWidth: open ? W_OPEN : W_CLOSE,
      height:   "100%",
      background: C.bgDeeper,
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
              getStatFor={getStatFor}
              onSelect={(key) => { onSectorClick?.(key); setShowFlyout(false); }}
            />
          )}
        </div>

        {/* HEATMAP */}
        <NavItem icon="🔥" label="HEATMAP" open={open}
          onClick={() => window.open("https://finviz.com/map.ashx", "_blank")} />

        {/* 구분선 */}
        <div style={{ height: 1, background: C.border, margin: open ? "10px 14px" : "10px 10px" }} />

        {/* API STATUS */}
        {open && (
          <div style={{
            fontSize: 10, color: C.textMuted,
            letterSpacing: 1.5, padding: "4px 14px 8px",
            fontFamily: "'Inter', sans-serif",
          }}>
            API STATUS
          </div>
        )}

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
            {open && <span style={{ fontSize: 11, color: C.textMuted }}>{a.label}</span>}
            <span style={{
              fontFamily: "'Inter', sans-serif",
              fontSize: 10, fontWeight: 700,
              color: a.ok ? C.primary : "#555555",
            }}>
              ●{open ? ` ${a.status}` : ""}
            </span>
          </div>
        ))}
      </nav>
    </aside>
  );
}

/* ── NavItem */
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

/* ── SectorFlyout */
function SectorFlyout({ activeSector, getStatFor, onSelect }) {
  return (
    <div style={{
      position: "absolute", left: "100%", top: 0,
      width: 310,
      background: C.bgDark,
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
        fontSize: 11, color: C.primary,
        letterSpacing: 1, fontWeight: 700,
      }}>
        SECTORS
      </div>

      <div style={{
        display: "grid", gridTemplateColumns: "1fr 46px 54px 56px",
        padding: "5px 14px",
        fontSize: 10, color: C.textMuted,
        borderBottom: `1px solid ${C.border}`,
      }}>
        <span>섹터</span>
        <span style={{ textAlign: "right" }}>종목</span>
        <span style={{ textAlign: "right" }}>Avg</span>
        <span style={{ textAlign: "right" }}>TOP</span>
      </div>

      {SECTORS.map(s => {
        const stat = getStatFor(s.key);
        return (
          <SectorRow
            key={s.key}
            sector={s}
            stat={stat}
            active={activeSector === s.key}
            onSelect={onSelect}
          />
        );
      })}
    </div>
  );
}

function SectorRow({ sector, stat, active, onSelect }) {
  const [hov, setHov] = useState(false);
  const avg = parseFloat(stat.avgScore);
  const scoreColor =
    !isNaN(avg) ? (avg >= 65 ? C.cyan : avg >= 50 ? C.golden : C.down) : C.textMuted;

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
          <div style={{ fontSize: 9, color: C.textMuted }}>{sector.en}</div>
        </div>
      </div>
      <div style={{ fontSize: 11, color: C.textGray, textAlign: "right" }}>
        {stat.count}
      </div>
      <div style={{ fontSize: 11, color: scoreColor, fontWeight: 700, textAlign: "right" }}>
        {stat.avgScore}
      </div>
      <div style={{ fontSize: 11, color: C.pink, textAlign: "right" }}>
        {stat.top}
      </div>
    </button>
  );
}