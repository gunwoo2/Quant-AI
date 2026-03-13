/**
 * MarketStatus.jsx — v2 (백엔드 API 연결)
 *
 * GET /api/market/status
 *   { isOpen, session: "OPEN"|"CLOSED"|"PRE_MARKET"|"AFTER_HOURS", nextOpen }
 *
 * - API 성공 시 서버 기준 US 세션 상태 반영
 * - API 실패 시 클라이언트 DST 계산 Fallback
 * - 30초마다 자동 갱신
 */

import { useState, useEffect } from "react";
import { C, FONT } from "../../styles/tokens";
import api from "../../api";

// ── 로컬 Fallback: DST 자동 계산
function isDST(now) {
  const y = now.getUTCFullYear();
  const mar = new Date(Date.UTC(y, 2, 1));
  mar.setUTCDate(1 + ((7 - mar.getUTCDay()) % 7) + 7);
  const nov = new Date(Date.UTC(y, 10, 1));
  nov.setUTCDate(1 + ((7 - nov.getUTCDay()) % 7));
  return now >= mar && now < nov;
}

function getLocalStatus() {
  const now   = new Date();
  const utcMs = now.getTime() + now.getTimezoneOffset() * 60000;
  const dow   = new Date(utcMs).getUTCDay();
  const isWd  = dow >= 1 && dow <= 5;

  const etOffset = isDST(now) ? -4 : -5;
  const etNow  = new Date(utcMs + etOffset * 3600000);
  const etMin  = etNow.getUTCHours() * 60 + etNow.getUTCMinutes();

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
    if      (kstMin >= 480 && kstMin < 540)  krSession = "PRE_MARKET";
    else if (kstMin >= 540 && kstMin < 930)  krSession = "OPEN";
    else if (kstMin >= 930 && kstMin < 1080) krSession = "AFTER_HOURS";
  }

  // getLocalStatus 함수 내부 하단 수정
  const fmt = d =>
    `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;

  // 이제 아래 리턴값이 정상적으로 시차가 적용된 시간을 반환합니다.
  return { usSession, krSession, etStr: fmt(etNow), kstStr: fmt(kstNow) };
}

const SESSION_META = {
  OPEN:        { label: "OPEN",   color: C.green, pulse: true  },
  PRE_MARKET:  { label: "PRE",    color: C.golden,  pulse: true  },
  AFTER_HOURS: { label: "AFTER",  color: C.cyan,    pulse: true  },
  CLOSED:      { label: "CLOSED", color: C.textMuted, pulse: false },
};

function StatusDot({ session }) {
  const meta = SESSION_META[session] ?? SESSION_META.CLOSED;
  return (
    <span style={{ position: "relative", display: "inline-flex", width: 8, height: 8, flexShrink: 0 }}>
      <span style={{
        display: "block", width: 8, height: 8, borderRadius: "50%",
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

function MarketChip({ flag, label, timeStr, session }) {
  const meta = SESSION_META[session] ?? SESSION_META.CLOSED;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <StatusDot session={session} />
      <div>
        <div style={{ fontSize: 9, color: C.textMuted, letterSpacing: 0.5 }}>
          {flag} {label}
        </div>
        <div style={{ fontSize: 11, color: C.textPri, fontWeight: 600, lineHeight: 1.2 }}>
          {timeStr}
          <span style={{ fontSize: 9, color: meta.color, marginLeft: 4, fontWeight: 700 }}>
            {meta.label}
          </span>
        </div>
      </div>
    </div>
  );
}

export default function MarketStatus() {
  const [s, setS] = useState(() => getLocalStatus());

  const refresh = () => {
    // getLocalStatus()는 API 응답 전까지만 보여주는 임시 데이터용
    const local = getLocalStatus(); 

    api.get("/api/market/status")
      .then(res => {
        // 🔍 데이터가 잘 오는지 확인용 (필요 없으면 삭제)
        console.log("Market API Data:", res.data);

        setS({
          // 1. 세션 상태 업데이트 (OPEN, CLOSED 등)
          usSession: res.data.session ?? local.usSession,
          krSession: local.krSession, 
          
          // 2. 💡 가장 중요한 부분: 백엔드에서 계산된 정확한 시간을 화면에 표시
          etStr: res.data.etStr ?? local.etStr,     // "21:51" 형태
          kstStr: res.data.kstStr ?? local.kstStr, // "10:51" 형태 (한국 시간)
        });
      })
      .catch((err) => {
        console.error("Market API Error:", err);
        setS(local);
      });
  };

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 30000);
    return () => clearInterval(id);
  }, []);

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 14, fontFamily: FONT.mono, paddingRight: 4 }}>
      <MarketChip flag="🇺🇸" label="US · ET"  timeStr={s.etStr}  session={s.usSession} />
      <div style={{ width: 1, height: 22, background: C.border }} />
      <MarketChip flag="🇰🇷" label="KR · KST" timeStr={s.kstStr} session={s.krSession} />
    </div>
  );
}