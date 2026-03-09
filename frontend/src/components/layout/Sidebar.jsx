/**
 * Sidebar.jsx
 * 좌측 사이드바
 * - 접기/펼치기 (240px ↔ 56px)
 * - SECTORS 커서 올리면 우측 flyout (SeekingAlpha 스타일)
 * - HOME, HEATMAP (새 탭), API STATUS
 */

import { useState, useRef } from "react";
import { C, FONT, SECTORS, SECTOR_STATS, gradeColor } from "../../styles/tokens";

const SIDEBAR_OPEN  = 220;
const SIDEBAR_CLOSE = 52;

export default function Sidebar({ onSectorClick, activeSector }) {
  const [open, setOpen]               = useState(true);
  const [sectorFlyout, setSectorFlyout] = useState(false);
  const sectorRef = useRef(null);

  const width = open ? SIDEBAR_OPEN : SIDEBAR_CLOSE;

  return (
    <>
      <aside style={{
        width,
        minWidth: width,
        height: "100%",
        background: "#0a0a0a",
        borderRight: `1px solid ${C.border}`,
        display: "flex",
        flexDirection: "column",
        transition: "width 0.2s ease",
        overflow: "visible",
        position: "relative",
        zIndex: 50,
        flexShrink: 0,
      }}>
        {/* ── 로고 + 토글 */}
        <div style={{
          display: "flex",
          alignItems: "center",
          justifyContent: open ? "space-between" : "center",
          padding: open ? "0 16px" : "0",
          height: 52,
          borderBottom: `1px solid ${C.border}`,
          flexShrink: 0,
        }}>
          {open && (
            <span style={{
              fontFamily: FONT.mono,
              fontSize: 14,
              fontWeight: 700,
              color: C.cyan,
              letterSpacing: 2,
            }}>
              QUANT AI
            </span>
          )}
          <button
            onClick={() => setOpen(v => !v)}
            style={{
              background: "none",
              border: "none",
              color: C.textGray,
              cursor: "pointer",
              padding: 8,
              fontSize: 16,
              lineHeight: 1,
              flexShrink: 0,
            }}
            title={open ? "사이드바 닫기" : "사이드바 열기"}
          >
            {open ? "✕" : "☰"}
          </button>
        </div>

        {/* ── 메뉴 항목들 */}
        <nav style={{ flex: 1, padding: "8px 0", overflowY: "auto", overflowX: "visible" }}>

          {/* HOME */}
          <NavItem
            icon="🏠"
            label="HOME"
            open={open}
            onClick={() => window.open(window.location.href, "_blank")}
          />

          {/* HEATMAP → finviz 새탭 */}
          <NavItem
            icon="🔥"
            label="HEATMAP"
            open={open}
            onClick={() => window.open("https://finviz.com/map.ashx", "_blank")}
          />

          {/* ── SECTORS + flyout */}
          <div style={{ position: "relative" }} ref={sectorRef}>
            <SectionLabel open={open} label="SECTORS" />
            <div
              onMouseEnter={() => setSectorFlyout(true)}
              onMouseLeave={() => setSectorFlyout(false)}
            >
              {SECTORS.map(s => (
                <NavItem
                  key={s.key}
                  icon={s.icon}
                  label={open ? s.label : ""}
                  subLabel={open ? s.en : ""}
                  open={open}
                  active={activeSector === s.key}
                  onClick={() => onSectorClick?.(s.key)}
                />
              ))}

              {/* Flyout 패널 */}
              {sectorFlyout && (
                <SectorFlyout onClose={() => setSectorFlyout(false)} onSelect={onSectorClick} />
              )}
            </div>
          </div>

          {/* API STATUS */}
          <SectionLabel open={open} label="API STATUS" />
          <div style={{ padding: open ? "4px 12px 8px" : "4px 0 8px" }}>
            {[
              { label: "FDR (OHLCV)",   status: "OK",   color: C.green },
              { label: "SEC EDGAR",     status: "OK",   color: C.green },
              { label: "KIS API",       status: "OK",   color: C.green },
              { label: "DART (KR)",     status: "IDLE", color: C.textMuted },
              { label: "FINRA Short",   status: "T+1",  color: C.golden },
              { label: "FRED API",      status: "OK",   color: C.green },
            ].map(api => (
              <div key={api.label} style={{
                display: "flex",
                alignItems: "center",
                justifyContent: open ? "space-between" : "center",
                padding: open ? "3px 4px" : "4px 0",
                gap: 6,
              }}>
                {open && (
                  <span style={{
                    fontFamily: FONT.mono,
                    fontSize: 9,
                    color: C.textMuted,
                    overflow: "hidden",
                    whiteSpace: "nowrap",
                    textOverflow: "ellipsis",
                  }}>
                    {api.label}
                  </span>
                )}
                <span style={{
                  fontFamily: FONT.mono,
                  fontSize: 9,
                  color: api.color,
                  fontWeight: 700,
                  flexShrink: 0,
                }}>
                  ●{open ? ` ${api.status}` : ""}
                </span>
              </div>
            ))}
          </div>
        </nav>

        {/* ── 배치 정보 (하단) */}
        {open && (
          <div style={{
            borderTop: `1px solid ${C.border}`,
            padding: "8px 12px",
            fontFamily: FONT.mono,
            fontSize: 9,
            color: C.textMuted,
            lineHeight: 1.6,
          }}>
            <div>● 종목 수: <span style={{ color: C.textGray }}>510개</span></div>
            <div>● 배치: <span style={{ color: C.textGray }}>03-09 02:14</span></div>
            <div>● 다음: <span style={{ color: C.textGray }}>03-10 02:00</span></div>
          </div>
        )}
      </aside>
    </>
  );
}

// ── 서브 컴포넌트: NavItem
function NavItem({ icon, label, subLabel, open, active, onClick }) {
  const [hovered, setHovered] = useState(false);
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      title={!open ? label : undefined}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        width: "100%",
        padding: open ? "8px 16px" : "10px 0",
        justifyContent: open ? "flex-start" : "center",
        background: active ? `${C.cyan}12` : hovered ? `${C.border}60` : "none",
        border: "none",
        borderLeft: active ? `2px solid ${C.cyan}` : "2px solid transparent",
        cursor: "pointer",
        transition: "background 0.12s",
        textAlign: "left",
      }}
    >
      <span style={{ fontSize: 14, flexShrink: 0 }}>{icon}</span>
      {open && (
        <div style={{ overflow: "hidden" }}>
          <div style={{
            fontFamily: FONT.sans,
            fontSize: 12,
            fontWeight: 500,
            color: active ? C.cyan : hovered ? C.textPri : C.textGray,
            whiteSpace: "nowrap",
          }}>
            {label}
          </div>
          {subLabel && (
            <div style={{
              fontFamily: FONT.mono,
              fontSize: 9,
              color: C.textMuted,
              letterSpacing: 0.5,
            }}>
              {subLabel}
            </div>
          )}
        </div>
      )}
    </button>
  );
}

// ── 서브 컴포넌트: SectionLabel
function SectionLabel({ open, label }) {
  if (!open) return <div style={{ height: 8 }} />;
  return (
    <div style={{
      fontFamily: FONT.mono,
      fontSize: 9,
      color: C.textMuted,
      letterSpacing: 1.5,
      padding: "12px 16px 4px",
    }}>
      {label}
    </div>
  );
}

// ── 서브 컴포넌트: SectorFlyout (SeekingAlpha 스타일)
function SectorFlyout({ onSelect }) {
  return (
    <div style={{
      position: "absolute",
      left: "100%",
      top: 0,
      width: 320,
      background: "#111",
      border: `1px solid ${C.border}`,
      borderRadius: 4,
      boxShadow: "0 8px 32px rgba(0,0,0,0.8)",
      zIndex: 200,
      overflow: "hidden",
    }}>
      {/* 헤더 */}
      <div style={{
        padding: "10px 16px",
        borderBottom: `1px solid ${C.border}`,
        fontFamily: FONT.mono,
        fontSize: 10,
        color: C.cyan,
        letterSpacing: 1,
        fontWeight: 700,
      }}>
        SECTORS · 섹터별 현황
      </div>

      {/* 테이블 헤더 */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "1fr 50px 60px 80px",
        padding: "5px 16px",
        fontFamily: FONT.mono,
        fontSize: 9,
        color: C.textMuted,
        borderBottom: `1px solid ${C.border}`,
      }}>
        <span>섹터</span>
        <span style={{ textAlign: "right" }}>종목</span>
        <span style={{ textAlign: "right" }}>평균점수</span>
        <span style={{ textAlign: "right" }}>TOP</span>
      </div>

      {/* 섹터 행 */}
      {SECTORS.map(s => {
        const stat = SECTOR_STATS[s.key];
        return (
          <SectorRow key={s.key} sector={s} stat={stat} onSelect={onSelect} />
        );
      })}
    </div>
  );
}

function SectorRow({ sector, stat, onSelect }) {
  const [hovered, setHovered] = useState(false);
  const scoreColor =
    stat.avgScore >= 65 ? C.green :
    stat.avgScore >= 50 ? C.golden : C.red;

  return (
    <button
      onClick={() => onSelect?.(sector.key)}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: "grid",
        gridTemplateColumns: "1fr 50px 60px 80px",
        padding: "7px 16px",
        width: "100%",
        background: hovered ? `${C.border}40` : "none",
        border: "none",
        borderBottom: `1px solid ${C.border}20`,
        cursor: "pointer",
        textAlign: "left",
        transition: "background 0.1s",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <span style={{ fontSize: 12 }}>{sector.icon}</span>
        <div>
          <div style={{ fontFamily: FONT.sans, fontSize: 11, color: C.textPri }}>{sector.label}</div>
          <div style={{ fontFamily: FONT.mono, fontSize: 9, color: C.textMuted }}>{sector.en}</div>
        </div>
      </div>
      <div style={{ fontFamily: FONT.mono, fontSize: 11, color: C.textGray, textAlign: "right" }}>
        {stat.count}
      </div>
      <div style={{ fontFamily: FONT.mono, fontSize: 11, color: scoreColor, textAlign: "right", fontWeight: 700 }}>
        {stat.avgScore}
      </div>
      <div style={{ fontFamily: FONT.mono, fontSize: 11, color: C.cyan, textAlign: "right" }}>
        {stat.topTicker}
      </div>
    </button>
  );
}