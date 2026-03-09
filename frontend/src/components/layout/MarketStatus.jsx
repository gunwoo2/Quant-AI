/**
 * MarketStatus.jsx
 * 미국 / 한국 장 시간 표시
 * - 정규장: 밝은 색 불
 * - 프리/애프터: 다른 색 불
 * - 종료: 회색 불
 */

import { useState, useEffect } from "react";
import { C, FONT } from "../../styles/tokens";

function getMarketStatus() {
  const now = new Date();

  // UTC 기준으로 계산
  const utcHour   = now.getUTCHours();
  const utcMin    = now.getUTCMinutes();
  const utcTotal  = utcHour * 60 + utcMin; // 분 단위
  const dayOfWeek = now.getUTCDay(); // 0=일, 6=토
  const isWeekday = dayOfWeek >= 1 && dayOfWeek <= 5;

  // ─── US 시장 (ET = UTC-5 겨울 / UTC-4 여름, 여기선 UTC-5 고정)
  // Pre-market:  09:00~14:30 UTC (04:00~09:30 ET)
  // Regular:     14:30~21:00 UTC (09:30~16:00 ET)
  // After-hours: 21:00~01:00 UTC (16:00~20:00 ET)
  let usStatus = "closed";
  if (isWeekday) {
    if (utcTotal >= 9*60 && utcTotal < 14*60+30)  usStatus = "pre";
    else if (utcTotal >= 14*60+30 && utcTotal < 21*60) usStatus = "open";
    else if (utcTotal >= 21*60 || utcTotal < 1*60)  usStatus = "after";
  }

  // ─── KR 시장 (KST = UTC+9)
  // Regular: 09:00~15:30 KST = 00:00~06:30 UTC
  let krStatus = "closed";
  if (isWeekday) {
    if (utcTotal >= 0 && utcTotal < 6*60+30) krStatus = "open";
  }

  // 현재 시간 문자열
  const etOffset = -5;
  const kstOffset = 9;
  const etTime  = new Date(now.getTime() + etOffset * 3600000);
  const kstTime = new Date(now.getTime() + kstOffset * 3600000);
  const fmt = (d) =>
    `${String(d.getUTCHours()).padStart(2,"0")}:${String(d.getUTCMinutes()).padStart(2,"0")}`;

  return { usStatus, krStatus, etStr: fmt(etTime), kstStr: fmt(kstTime) };
}

const STATUS_META = {
  open:   { label: "OPEN",   color: C.green,  glow: true  },
  pre:    { label: "PRE",    color: C.golden, glow: false },
  after:  { label: "AFTER",  color: C.cyan,   glow: false },
  closed: { label: "CLOSED", color: C.textMuted, glow: false },
};

function StatusDot({ status }) {
  const meta = STATUS_META[status];
  return (
    <span style={{
      display: "inline-block",
      width: 7,
      height: 7,
      borderRadius: "50%",
      background: meta.color,
      boxShadow: meta.glow ? `0 0 6px ${meta.color}` : "none",
      flexShrink: 0,
    }} />
  );
}

export default function MarketStatus() {
  const [status, setStatus] = useState(getMarketStatus());

  useEffect(() => {
    const id = setInterval(() => setStatus(getMarketStatus()), 30000);
    return () => clearInterval(id);
  }, []);

  const { usStatus, krStatus, etStr, kstStr } = status;

  return (
    <div style={{
      display: "flex",
      alignItems: "center",
      gap: 16,
      fontFamily: FONT.mono,
    }}>
      {/* US */}
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <StatusDot status={usStatus} />
        <div>
          <div style={{ fontSize: 9, color: C.textMuted, letterSpacing: 0.5 }}>US · ET</div>
          <div style={{ fontSize: 11, color: C.textPri, fontWeight: 600 }}>
            {etStr}
            <span style={{
              fontSize: 9,
              color: STATUS_META[usStatus].color,
              marginLeft: 4,
            }}>
              {STATUS_META[usStatus].label}
            </span>
          </div>
        </div>
      </div>

      <div style={{ width: 1, height: 24, background: C.border }} />

      {/* KR */}
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <StatusDot status={krStatus} />
        <div>
          <div style={{ fontSize: 9, color: C.textMuted, letterSpacing: 0.5 }}>KR · KST</div>
          <div style={{ fontSize: 11, color: C.textPri, fontWeight: 600 }}>
            {kstStr}
            <span style={{
              fontSize: 9,
              color: STATUS_META[krStatus].color,
              marginLeft: 4,
            }}>
              {STATUS_META[krStatus].label}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}