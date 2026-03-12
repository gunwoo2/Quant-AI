import { useState, useEffect } from 'react';

/**
 * MarketHoursWidget
 * 미국(NYSE/NASDAQ) + 한국(KRX) 장 상태를 실시간으로 표시
 * 색상: 정규장 🟢 / 프리·애프터 🟡🟠 / 마감 ⚫
 */

function getMarketStatus(now) {
  // UTC 기준으로 계산
  const utcMs = now.getTime() + now.getTimezoneOffset() * 60000;

  // ─── 미국 (ET = UTC-5, 서머타임 UTC-4) ───
  // 서머타임 판별: 3월 두 번째 일요일 ~ 11월 첫 번째 일요일
  const year = now.getUTCFullYear();
  const isDST = (() => {
    // 3월 두 번째 일요일
    const marchSecondSun = new Date(Date.UTC(year, 2, 1));
    marchSecondSun.setUTCDate(1 + ((7 - marchSecondSun.getUTCDay()) % 7) + 7);
    // 11월 첫 번째 일요일
    const novFirstSun = new Date(Date.UTC(year, 10, 1));
    novFirstSun.setUTCDate(1 + ((7 - novFirstSun.getUTCDay()) % 7));
    return now >= marchSecondSun && now < novFirstSun;
  })();
  const etOffset = isDST ? -4 : -5;
  const etMs = utcMs + etOffset * 3600000;
  const etNow = new Date(etMs);
  const etDay = etNow.getUTCDay(); // 0=Sun, 6=Sat
  const etMin = etNow.getUTCHours() * 60 + etNow.getUTCMinutes();

  let usStatus = 'closed';
  let usLabel = 'Closed';
  if (etDay >= 1 && etDay <= 5) {
    if (etMin >= 240 && etMin < 570)        { usStatus = 'pre';     usLabel = 'Pre-Market'; }
    else if (etMin >= 570 && etMin < 960)   { usStatus = 'regular'; usLabel = 'Regular';    }
    else if (etMin >= 960 && etMin < 1200)  { usStatus = 'after';   usLabel = 'After-Hours';}
    else                                     { usStatus = 'closed';  usLabel = 'Closed';     }
  }

  // ─── 한국 (KST = UTC+9) ───
  const kstMs = utcMs + 9 * 3600000;
  const kstNow = new Date(kstMs);
  const kstDay = kstNow.getUTCDay();
  const kstMin = kstNow.getUTCHours() * 60 + kstNow.getUTCMinutes();

  let krStatus = 'closed';
  let krLabel = 'Closed';
  if (kstDay >= 1 && kstDay <= 5) {
    if (kstMin >= 480 && kstMin < 540)       { krStatus = 'pre';     krLabel = 'Pre-Market'; }
    else if (kstMin >= 540 && kstMin < 930)  { krStatus = 'regular'; krLabel = 'Regular';    }
    else if (kstMin >= 930 && kstMin < 1080) { krStatus = 'after';   krLabel = 'After-Hours';}
    else                                      { krStatus = 'closed';  krLabel = 'Closed';     }
  }

  return { usStatus, usLabel, etNow, krStatus, krLabel, kstNow };
}

const STATUS_COLOR = {
  regular: '#22c55e',   // green
  pre:     '#f59e0b',   // amber
  after:   '#f97316',   // orange
  closed:  '#374151',   // dark gray
};

const STATUS_BG = {
  regular: 'rgba(34, 197, 94, 0.08)',
  pre:     'rgba(245, 158, 11, 0.08)',
  after:   'rgba(249, 115, 22, 0.08)',
  closed:  'rgba(55, 65, 81, 0.08)',
};

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
      {/* 깜빡이는 LED */}
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
  const [tick, setTick] = useState(new Date());

  useEffect(() => {
    const id = setInterval(() => setTick(new Date()), 60000); // 1분마다 갱신
    return () => clearInterval(id);
  }, []);

  const { usStatus, usLabel, etNow, krStatus, krLabel, kstNow } = getMarketStatus(tick);

  const fmt = (d) => d.toLocaleTimeString('en-US', {
    hour: '2-digit', minute: '2-digit', hour12: false,
    timeZone: 'UTC',
  });

  return (
    <>
      {/* 애니메이션 키프레임 */}
      <style>{`
        @keyframes pulse-ring {
          0%   { transform: scale(1);   opacity: 0.6; }
          100% { transform: scale(2.8); opacity: 0;   }
        }
      `}</style>

      <div style={{ display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
        <MarketCard
          flag="🇺🇸" name="US Market"  exchange="NYSE/NASDAQ"
          status={usStatus} label={usLabel}
          timeStr={`${fmt(etNow)} ET`}
        />
        <MarketCard
          flag="🇰🇷" name="KR Market"  exchange="KRX"
          status={krStatus} label={krLabel}
          timeStr={`${fmt(kstNow)} KST`}
        />
      </div>
    </>
  );
}