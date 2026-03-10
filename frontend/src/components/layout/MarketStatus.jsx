/**
 * MarketStatus.jsx
 * 변경사항:
 *   - 정규장(open): 초록 LED 펄스 ✅
 *   - 프리장(pre): 앰버 LED 펄스 (다른 색) ✅
 *   - 애프터(after): 시안 LED 펄스 (다른 색) ✅
 *   - 마감(closed): 회색, 펄스 없음 ✅
 *   - 서머타임 자동 계산 포함
 */

import { useState, useEffect } from "react";
import { C, FONT } from "../../styles/tokens";

function isDST(now) {
  const y = now.getUTCFullYear();
  // 3월 두 번째 일요일
  const mar = new Date(Date.UTC(y, 2, 1));
  mar.setUTCDate(1 + ((7 - mar.getUTCDay()) % 7) + 7);
  // 11월 첫 번째 일요일
  const nov = new Date(Date.UTC(y, 10, 1));
  nov.setUTCDate(1 + ((7 - nov.getUTCDay()) % 7));
  return now >= mar && now < nov;
}

function getMarketStatus() {
  const now      = new Date();
  const utcMs    = now.getTime() + now.getTimezoneOffset() * 60000;
  const utcNow   = new Date(utcMs);
  const dayOfWeek = utcNow.getUTCDay(); // 0=일, 6=토
  const isWeekday = dayOfWeek >= 1 && dayOfWeek <= 5;

  // ── 미국 (ET, 서머타임 자동)
  const etOffset  = isDST(now) ? -4 : -5;
  const etNow     = new Date(utcMs + etOffset * 3600000);
  const etMin     = etNow.getUTCHours() * 60 + etNow.getUTCMinutes();

  let usStatus = "closed";
  if (isWeekday) {
    if      (etMin >= 240  && etMin < 570)  usStatus = "pre";    // 04:00~09:30 ET
    else if (etMin >= 570  && etMin < 960)  usStatus = "open";   // 09:30~16:00 ET
    else if (etMin >= 960  && etMin < 1200) usStatus = "after";  // 16:00~20:00 ET
  }

  // ── 한국 (KST = UTC+9)
  const kstNow = new Date(utcMs + 9 * 3600000);
  const kstMin = kstNow.getUTCHours() * 60 + kstNow.getUTCMinutes();

  let krStatus = "closed";
  if (isWeekday) {
    if      (kstMin >= 480 && kstMin < 540)  krStatus = "pre";   // 08:00~09:00 KST
    else if (kstMin >= 540 && kstMin < 930)  krStatus = "open";  // 09:00~15:30 KST
    else if (kstMin >= 930 && kstMin < 1080) krStatus = "after"; // 15:30~18:00 KST
  }

  const fmt = d =>
    `${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")}`;

  return { usStatus, krStatus, etStr: fmt(etNow), kstStr: fmt(kstNow) };
}

const STATUS_META = {
  open:   { label: "OPEN",   color: "#22c55e", pulse: true  },
  pre:    { label: "PRE",    color: C.golden,  pulse: true  },
  after:  { label: "AFTER",  color: C.cyan,    pulse: true  },
  closed: { label: "CLOSED", color: C.textMuted, pulse: false },
};

function StatusDot({ status }) {
  const { color, pulse } = STATUS_META[status];
  return (
    <span style={{ position: "relative", display: "inline-flex", width: 8, height: 8, flexShrink: 0 }}>
      <span style={{
        display: "block", width: 8, height: 8, borderRadius: "50%",
        background: color,
        boxShadow: pulse ? `0 0 6px ${color}` : "none",
        position: "relative", zIndex: 1,
      }} />
      {pulse && (
        <span style={{
          position: "absolute", inset: 0, borderRadius: "50%",
          background: color, opacity: 0,
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

export default function MarketStatus() {
  const [s, setS] = useState(getMarketStatus());
  useEffect(() => {
    const id = setInterval(() => setS(getMarketStatus()), 30000);
    return () => clearInterval(id);
  }, []);

  const { usStatus, krStatus, etStr, kstStr } = s;

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 14, fontFamily: FONT.mono, paddingRight: 4 }}>
      {/* US */}
      <MarketChip
        flag="🇺🇸"
        label="US · ET"
        timeStr={etStr}
        status={usStatus}
      />
      <div style={{ width: 1, height: 22, background: C.border }} />
      {/* KR */}
      <MarketChip
        flag="🇰🇷"
        label="KR · KST"
        timeStr={kstStr}
        status={krStatus}
      />
    </div>
  );
}

function MarketChip({ flag, label, timeStr, status }) {
  const { color, label: statusLabel } = STATUS_META[status];
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <StatusDot status={status} />
      <div>
        <div style={{ fontSize: 9, color: C.textMuted, letterSpacing: 0.5 }}>
          {flag} {label}
        </div>
        <div style={{ fontSize: 11, color: C.textPri, fontWeight: 600, lineHeight: 1.2 }}>
          {timeStr}
          <span style={{ fontSize: 9, color, marginLeft: 4, fontWeight: 700 }}>
            {statusLabel}
          </span>
        </div>
      </div>
    </div>
  );
}