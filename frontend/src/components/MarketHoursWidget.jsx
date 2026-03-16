import { useState, useEffect } from 'react';
import api from '../api';

/**
 * MarketHoursWidget — v3
 * 미국(NYSE/NASDAQ) + 한국(KRX) 장 상태를 실시간으로 표시
 * 
 * ★ 백엔드 /api/market/status API 연동
 * ★ API 실패 시 클라이언트 자체 계산 Fallback
 * ★ 30초마다 자동 갱신
 */

/* ── 클라이언트 Fallback 계산 ── */
function getMarketStatus(now) {
  const utcMs = now.getTime() + now.getTimezoneOffset() * 60000;

  const year = now.getUTCFullYear();
  const isDST = (() => {
    const marchSecondSun = new Date(Date.UTC(year, 2, 1));
    marchSecondSun.setUTCDate(1 + ((7 - marchSecondSun.getUTCDay()) % 7) + 7);
    const novFirstSun = new Date(Date.UTC(year, 10, 1));
    novFirstSun.setUTCDate(1 + ((7 - novFirstSun.getUTCDay()) % 7));
    return now >= marchSecondSun && now < novFirstSun;
  })();
  const etOffset = isDST ? -4 : -5;
  const etMs = utcMs + etOffset * 3600000;
  const etNow = new Date(etMs);
  const etDay = etNow.getUTCDay();
  const etMin = etNow.getUTCHours() * 60 + etNow.getUTCMinutes();

  let usStatus = 'closed';
  let usLabel = 'Closed';
  if (etDay >= 1 && etDay <= 5) {
    if      (etMin >= 240 && etMin < 570)  { usStatus = 'pre';     usLabel = 'Pre-Market'; }
    else if (etMin >= 570 && etMin < 960)  { usStatus = 'regular'; usLabel = 'Regular';    }
    else if (etMin >= 960 && etMin < 1200) { usStatus = 'after';   usLabel = 'After-Hours';}
  }

  const kstMs = utcMs + 9 * 3600000;
  const kstNow = new Date(kstMs);
  const kstDay = kstNow.getUTCDay();
  const kstMin = kstNow.getUTCHours() * 60 + kstNow.getUTCMinutes();

  let krStatus = 'closed';
  let krLabel = 'Closed';
  if (kstDay >= 1 && kstDay <= 5) {
    if      (kstMin >= 480 && kstMin < 540)  { krStatus = 'pre';     krLabel = 'Pre-Market'; }
    else if (kstMin >= 540 && kstMin < 930)  { krStatus = 'regular'; krLabel = 'Regular';    }
    else if (kstMin >= 930 && kstMin < 1080) { krStatus = 'after';   krLabel = 'After-Hours';}
  }

  return { usStatus, usLabel, etNow, krStatus, krLabel, kstNow };
}

/* ── 시간 포맷 (★ getUTCHours 사용 — KST 이중적용 방지) ── */
function fmtTime(d) {
  return String(d.getUTCHours()).padStart(2, '0') + ':' + String(d.getUTCMinutes()).padStart(2, '0');
}

/* ── API etStr에서 "HH:MM" 추출 (어떤 형태가 와도 대응) ── */
function extractTime(str) {
  if (!str) return null;
  // "2026-03-16 09:21 ET" → "09:21"
  // "09:21" → "09:21"
  const m = str.match(/(\d{2}:\d{2})/);
  return m ? m[1] : null;
}

/* ── API 세션키 → 위젯 상태 변환 (한글/영문 모두 대응) ── */
const SESSION_MAP = {
  'OPEN':        { status: 'regular', label: 'Regular'     },
  'PRE_MARKET':  { status: 'pre',     label: 'Pre-Market'  },
  'AFTER_HOURS': { status: 'after',   label: 'After-Hours' },
  'CLOSED':      { status: 'closed',  label: 'Closed'      },
  '정규장':       { status: 'regular', label: 'Regular'     },
  '프리마켓':     { status: 'pre',     label: 'Pre-Market'  },
  '동시호가':     { status: 'pre',     label: 'Pre-Market'  },
  '애프터마켓':   { status: 'after',   label: 'After-Hours' },
  '시간외':       { status: 'after',   label: 'After-Hours' },
  '장 마감':      { status: 'closed',  label: 'Closed'      },
  '주말 휴장':    { status: 'closed',  label: 'Closed'      },
  '공휴일 휴장':  { status: 'closed',  label: 'Closed'      },
};

function mapSession(raw) {
  if (!raw) return null;
  return SESSION_MAP[raw] || SESSION_MAP[raw.trim()] || null;
}

/* ── 색상 ── */
const STATUS_COLOR = {
  regular: '#22c55e',
  pre:     '#f59e0b',
  after:   '#f97316',
  closed:  '#374151',
};

const STATUS_BG = {
  regular: 'rgba(34, 197, 94, 0.08)',
  pre:     'rgba(245, 158, 11, 0.08)',
  after:   'rgba(249, 115, 22, 0.08)',
  closed:  'rgba(55, 65, 81, 0.08)',
};

/* ── MarketCard ── */
function MarketCard({ flag, name, exchange, status, label, timeStr }) {
  const color = STATUS_COLOR[status];
  const bg    = STATUS_BG[status];

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: '12px',
      padding: '10px 16px',
      backgroundColor: bg,
      border: `1px solid ${color}30`,
      borderRadius: '10px',
      minWidth: '200px',
      transition: 'all 0.5s ease',
    }}>
      {/* LED dot */}
      <div style={{ position: 'relative', width: '10px', height: '10px', flexShrink: 0 }}>
        <div style={{
          width: '10px', height: '10px', borderRadius: '50%',
          backgroundColor: color,
          boxShadow: status !== 'closed' ? `0 0 8px ${color}` : 'none',
        }} />
        {status !== 'closed' && (
          <div style={{
            position: 'absolute', top: 0, left: 0,
            width: '10px', height: '10px', borderRadius: '50%',
            backgroundColor: color,
            animation: 'pulse-ring 1.5s ease-out infinite',
            opacity: 0,
          }} />
        )}
      </div>

      <div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px' }}>
          <span style={{ fontSize: '13px', fontWeight: '800', color: '#fff', letterSpacing: '0.3px' }}>
            {flag} {name}
          </span>
          <span style={{ fontSize: '10px', color: '#555', fontWeight: '600' }}>{exchange}</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '2px' }}>
          <span style={{
            fontSize: '10px', fontWeight: '700', color,
            backgroundColor: `${color}15`,
            padding: '1px 6px', borderRadius: '4px',
            letterSpacing: '0.5px',
          }}>
            {label.toUpperCase()}
          </span>
          <span style={{ fontSize: '11px', color: '#666', fontFamily: 'monospace' }}>{timeStr}</span>
        </div>
      </div>
    </div>
  );
}

export default function MarketHoursWidget() {
  const [data, setData] = useState(() => {
    const local = getMarketStatus(new Date());
    return {
      usStatus: local.usStatus,
      usLabel:  local.usLabel,
      usTime:   fmtTime(local.etNow) + ' ET',
      krStatus: local.krStatus,
      krLabel:  local.krLabel,
      krTime:   fmtTime(local.kstNow) + ' KST',
    };
  });

  useEffect(() => {
    const refresh = () => {
      const now = new Date();
      const local = getMarketStatus(now);

      const fallback = {
        usStatus: local.usStatus,
        usLabel:  local.usLabel,
        usTime:   fmtTime(local.etNow) + ' ET',
        krStatus: local.krStatus,
        krLabel:  local.krLabel,
        krTime:   fmtTime(local.kstNow) + ' KST',
      };

      api.get('/api/market/status')
        .then(res => {
          const d = res.data;
          const usMap   = mapSession(d.session);
          const krMap   = mapSession(d.krSession);
          const etTime  = extractTime(d.etStr);
          const kstTime = extractTime(d.kstStr);

          setData({
            usStatus: usMap   ? usMap.status  : fallback.usStatus,
            usLabel:  usMap   ? usMap.label   : fallback.usLabel,
            usTime:   etTime  ? etTime + ' ET'  : fallback.usTime,
            krStatus: krMap   ? krMap.status  : fallback.krStatus,
            krLabel:  krMap   ? krMap.label   : fallback.krLabel,
            krTime:   kstTime ? kstTime + ' KST' : fallback.krTime,
          });
        })
        .catch(() => setData(fallback));
    };

    refresh();
    const id = setInterval(refresh, 30000);
    return () => clearInterval(id);
  }, []);

  return (
    <>
      <style>{`
        @keyframes pulse-ring {
          0%   { transform: scale(1);   opacity: 0.6; }
          100% { transform: scale(2.8); opacity: 0;   }
        }
      `}</style>

      <div style={{ display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
        <MarketCard
          flag="🇺🇸" name="US Market" exchange="NYSE/NASDAQ"
          status={data.usStatus} label={data.usLabel} timeStr={data.usTime}
        />
        <MarketCard
          flag="🇰🇷" name="KR Market" exchange="KRX"
          status={data.krStatus} label={data.krLabel} timeStr={data.krTime}
        />
      </div>
    </>
  );
}

