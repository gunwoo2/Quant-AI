/**
 * MarketStatus.jsx — v3
 *
 * GET /api/market/status → {
 *   isOpen, session, etStr, nextOpen,         ← US (NYSE)
 *   krIsOpen, krSession, kstStr, krNextOpen   ← KR (KRX)
 * }
 *
 * 🇺🇸 NYSE 미국 현지시간(ET) 기준 미국장 상태
 * 🇰🇷 KRX  한국 시간(KST) 기준 한국장 상태
 */

import { useState, useEffect } from "react";
import { C, FONT } from "../../styles/tokens";
import api from "../../api";

/* ── 세션 메타 ── */
const SESSION_META = {
  OPEN:        { label: "장중",    labelEn: "OPEN",   color: "#22c55e", pulse: true  },
  PRE_MARKET:  { label: "프리장",  labelEn: "PRE",    color: "#fbbf24", pulse: true  },
  AFTER_HOURS: { label: "시간외",  labelEn: "AFTER",  color: "#00F5FF", pulse: true  },
  CLOSED:      { label: "휴장",    labelEn: "CLOSED", color: "#555",    pulse: false },
};

/* ── 로컬 Fallback (API 실패 대비) ── */
function isDST(now) {
  const y = now.getUTCFullYear();
  const mar = new Date(Date.UTC(y, 2, 1));
  mar.setUTCDate(1 + ((7 - mar.getUTCDay()) % 7) + 7);
  const nov = new Date(Date.UTC(y, 10, 1));
  nov.setUTCDate(1 + ((7 - nov.getUTCDay()) % 7));
  return now >= mar && now < nov;
}

function getLocalFallback() {
  const now   = new Date();
  const utcMs = now.getTime() + now.getTimezoneOffset() * 60000;
  const dow   = new Date(utcMs).getUTCDay();
  const isWd  = dow >= 1 && dow <= 5;

  const etOffset = isDST(now) ? -4 : -5;
  const etNow = new Date(utcMs + etOffset * 3600000);
  const etMin = etNow.getUTCHours() * 60 + etNow.getUTCMinutes();

  let usSession = "CLOSED";
  if (isWd) {
    if      (etMin >= 240 && etMin < 570)  usSession = "PRE_MARKET";
    else if (etMin >= 570 && etMin < 960)  usSession = "OPEN";
    else if (etMin >= 960 && etMin < 1200) usSession = "AFTER_HOURS";
  }

  const kstNow = new Date(utcMs + 9 * 3600000);
  const kstMin = kstNow.getUTCHours() * 60 + kstNow.getUTCMinutes();

  let krSession = "CLOSED";
  if (isWd) {
    if      (kstMin >= 510 && kstMin < 540)  krSession = "PRE_MARKET";   // 08:30~09:00
    else if (kstMin >= 540 && kstMin < 930)  krSession = "OPEN";         // 09:00~15:30
    else if (kstMin >= 930 && kstMin < 1080) krSession = "AFTER_HOURS";  // 15:30~18:00
  }

  const fmt = d =>
    `${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")}`;

  return {
    usSession, krSession,
    etStr: fmt(etNow), kstStr: fmt(kstNow),
  };
}

/* ── StatusDot ── */
function StatusDot({ session }) {
  const meta = SESSION_META[session] ?? SESSION_META.CLOSED;
  return (
    <span style={{ position: "relative", display: "inline-flex", width: 7, height: 7, flexShrink: 0 }}>
      <span style={{
        display: "block", width: 7, height: 7, borderRadius: "50%",
        background: meta.color,
        boxShadow: meta.pulse ? `0 0 6px ${meta.color}` : "none",
        position: "relative", zIndex: 1,
      }} />
      {meta.pulse && (
        <span style={{
          position: "absolute", inset: 0, borderRadius: "50%",
          background: meta.color, opacity: 0,
          animation: "mkt-pulse 1.8s ease-out infinite",
        }} />
      )}
      <style>{`
        @keyframes mkt-pulse {
          0%   { transform: scale(1);   opacity: 0.7; }
          100% { transform: scale(2.6); opacity: 0;   }
        }
      `}</style>
    </span>
  );
}

/* ── MarketChip (개선) ── */
function MarketChip({ flag, exchange, timezone, timeStr, session }) {
  const meta = SESSION_META[session] ?? SESSION_META.CLOSED;
  const isOpen = session === "OPEN";

  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 8,
      padding: "4px 10px",
      borderRadius: 8,
      background: isOpen ? `${meta.color}08` : "transparent",
      border: isOpen ? `1px solid ${meta.color}20` : "1px solid transparent",
      transition: "all 0.3s",
    }}>
      {/* 국기 + Dot */}
      <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
        <span style={{ fontSize: 14, lineHeight: 1 }}>{flag}</span>
        <StatusDot session={session} />
      </div>

      {/* 텍스트 */}
      <div style={{ lineHeight: 1.2 }}>
        {/* 거래소 + 타임존 */}
        <div style={{
          fontSize: 8, color: "#666", letterSpacing: 0.8,
          fontWeight: 700, fontFamily: "monospace",
        }}>
          {exchange} · {timezone}
        </div>
        {/* 시간 + 상태 */}
        <div style={{ display: "flex", alignItems: "baseline", gap: 4 }}>
          <span style={{
            fontSize: 13, color: "#e8e8e8", fontWeight: 700,
            fontFamily: "monospace", letterSpacing: 0.5,
          }}>
            {timeStr}
          </span>
          <span style={{
            fontSize: 9, fontWeight: 800, color: meta.color,
            letterSpacing: 0.5,
            padding: "1px 4px",
            borderRadius: 3,
            background: `${meta.color}12`,
          }}>
            {meta.label}
          </span>
        </div>
      </div>
    </div>
  );
}

/* ── Main Component ── */
export default function MarketStatus() {
  const [s, setS] = useState(() => getLocalFallback());

  const refresh = () => {
    const local = getLocalFallback();

    api.get("/api/market/status")
      .then(res => {
        const d = res.data;
        setS({
          usSession:  d.session    ?? local.usSession,
          krSession:  d.krSession  ?? local.krSession,
          etStr:      d.etStr      ?? local.etStr,
          kstStr:     d.kstStr     ?? local.kstStr,
        });
      })
      .catch(() => setS(local));
  };

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 30000);
    return () => clearInterval(id);
  }, []);

  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 6,
      fontFamily: FONT.mono, paddingRight: 4,
    }}>
      <MarketChip
        flag="🇺🇸"
        exchange="NYSE"
        timezone="ET"
        timeStr={s.etStr}
        session={s.usSession}
      />
      <div style={{ width: 1, height: 24, background: "#222" }} />
      <MarketChip
        flag="🇰🇷"
        exchange="KRX"
        timezone="KST"
        timeStr={s.kstStr}
        session={s.krSession}
      />
    </div>
  );
}
