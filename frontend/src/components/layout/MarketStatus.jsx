/**
 * MarketStatus.jsx — v3
 *
 * GET /api/market/status
 *   { isOpen, session, etStr, krIsOpen, krSession, kstStr, nextOpen, krNextOpen }
 *
 * ★ 핵심 계약:
 *   - session / krSession: 영문 키만 → OPEN | CLOSED | PRE_MARKET | AFTER_HOURS
 *   - etStr / kstStr: "HH:MM" 포맷 (백엔드 v2 이후)
 *   - 30초마다 자동 갱신
 */

import { useState, useEffect, useCallback } from "react";
import { C, FONT } from "../../styles/tokens";
import api from "../../api";

// ── 로컬 Fallback: DST 자동 계산 ──
function isDST(now) {
  const y = now.getUTCFullYear();
  const mar = new Date(Date.UTC(y, 2, 1));
  mar.setUTCDate(1 + ((7 - mar.getUTCDay()) % 7) + 7);
  const nov = new Date(Date.UTC(y, 10, 1));
  nov.setUTCDate(1 + ((7 - nov.getUTCDay()) % 7));
  return now >= mar && now < nov;
}

/** HH:MM 포맷 헬퍼 */
function fmtHM(h, m) {
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

/**
 * 로컬 fallback — API 실패 시 사용
 * ★ KST 기준 요일 판단으로 주말 버그 수정
 */
function getLocalStatus() {
  const now   = new Date();
  const utcMs = now.getTime() + now.getTimezoneOffset() * 60000;

  // ── US (ET 시간)
  const etOffset = isDST(now) ? -4 : -5;
  const etNow  = new Date(utcMs + etOffset * 3600000);
  const etH    = etNow.getUTCHours();
  const etM    = etNow.getUTCMinutes();
  const etMin  = etH * 60 + etM;
  const etWd   = etNow.getUTCDay();       // ET 기준 요일 (0=일 ~ 6=토)
  const etIsWd = etWd >= 1 && etWd <= 5;

  let usSession = "CLOSED";
  if (etIsWd) {
    if      (etMin >= 240 && etMin < 570)  usSession = "PRE_MARKET";
    else if (etMin >= 570 && etMin < 960)  usSession = "OPEN";
    else if (etMin >= 960 && etMin < 1200) usSession = "AFTER_HOURS";
  }

  // ── KR (KST 시간)  ★ KST 기준 요일 사용
  const kstNow = new Date(utcMs + 9 * 3600000);
  const kstH   = kstNow.getUTCHours();
  const kstM   = kstNow.getUTCMinutes();
  const kstMin = kstH * 60 + kstM;
  const kstWd  = kstNow.getUTCDay();       // KST 기준 요일
  const kstIsWd = kstWd >= 1 && kstWd <= 5;

  let krSession = "CLOSED";
  if (kstIsWd) {
    if      (kstMin >= 510 && kstMin < 540)  krSession = "PRE_MARKET";   // 08:30~09:00
    else if (kstMin >= 540 && kstMin < 930)  krSession = "OPEN";          // 09:00~15:30
    else if (kstMin >= 930 && kstMin < 1080) krSession = "AFTER_HOURS";   // 15:30~18:00
  }

  return {
    usSession,
    krSession,
    etStr:  fmtHM(etH, etM),
    kstStr: fmtHM(kstH, kstM),
  };
}

/**
 * API 응답의 시간 문자열에서 HH:MM만 추출
 * "21:57" → "21:57"
 * "2026-03-21 21:57 KST" → "21:57"  (구 버전 호환)
 */
function parseTimeOnly(str) {
  if (!str) return null;
  const m = str.match(/(\d{1,2}:\d{2})/);
  return m ? m[1] : null;
}


const SESSION_META = {
  OPEN:        { label: "OPEN",   color: C.up,        pulse: true  },
  PRE_MARKET:  { label: "PRE",    color: C.golden,    pulse: true  },
  AFTER_HOURS: { label: "AFTER",  color: C.cyan,      pulse: true  },
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
        <div style={{ fontSize: 9, color: C.textMuted, letterSpacing: 0.5, fontFamily: FONT.mono }}>
          {flag} {label}
        </div>
        <div style={{ fontSize: 11, color: C.textPri, fontWeight: 600, lineHeight: 1.2, fontFamily: FONT.mono }}>
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

  const refresh = useCallback(() => {
    const local = getLocalStatus();

    api.get("/api/market/status")
      .then(res => {
        const d = res.data;

        // ★ 영문 세션 키 → SESSION_META 키와 일치하는지 검증
        const validSessions = ["OPEN", "CLOSED", "PRE_MARKET", "AFTER_HOURS"];

        const usSession = validSessions.includes(d.session)
          ? d.session
          : local.usSession;

        const krSession = validSessions.includes(d.krSession)
          ? d.krSession
          : local.krSession;

        // ★ 시간은 항상 HH:MM 만 사용 (구 버전 "YYYY-MM-DD HH:MM TZ" 호환)
        const etStr  = parseTimeOnly(d.etStr)  ?? local.etStr;
        const kstStr = parseTimeOnly(d.kstStr) ?? local.kstStr;

        setS({ usSession, krSession, etStr, kstStr });
      })
      .catch(() => {
        setS(local);
      });
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 30000);
    return () => clearInterval(id);
  }, [refresh]);

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 14, fontFamily: FONT.mono, paddingRight: 4 }}>
      <MarketChip flag="🇺🇸" label="US · ET"  timeStr={s.etStr}  session={s.usSession} />
      <div style={{ width: 1, height: 22, background: C.border }} />
      <MarketChip flag="🇰🇷" label="KR · KST" timeStr={s.kstStr} session={s.krSession} />
    </div>
  );
}