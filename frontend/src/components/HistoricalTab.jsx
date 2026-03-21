import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { C, FONT, chgColor } from '../styles/tokens';
import { useOutletContext } from 'react-router-dom';
import api from '../api';


/* ═══════════════════════════════════════════════
   커스텀 캘린더 팝업 컴포넌트
   ─ global.css .cal-* 클래스 사용
   ═══════════════════════════════════════════════ */
const WEEKDAYS = ['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT'];

const CalendarPicker = ({ value, onChange, onClose, anchorRef, label }) => {
  const today = new Date();
  const selected = value ? new Date(value + 'T00:00:00') : null;
  const [viewYear, setViewYear] = useState(selected ? selected.getFullYear() : today.getFullYear());
  const [viewMonth, setViewMonth] = useState(selected ? selected.getMonth() : today.getMonth());
  const popupRef = useRef(null);

  // 팝업 위치 계산
  const [pos, setPos] = useState({ top: 0, left: 0 });
  useEffect(() => {
    if (anchorRef?.current) {
      const rect = anchorRef.current.getBoundingClientRect();
      setPos({ top: rect.bottom + 8, left: rect.left });
    }
  }, [anchorRef]);

  // 외부 클릭 닫기
  useEffect(() => {
    const handler = (e) => {
      if (popupRef.current && !popupRef.current.contains(e.target)) onClose();
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [onClose]);

  const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate();
  const firstDayOfWeek = new Date(viewYear, viewMonth, 1).getDay();
  const prevMonthDays = new Date(viewYear, viewMonth, 0).getDate();

  const prevMonth = () => {
    if (viewMonth === 0) { setViewYear(y => y - 1); setViewMonth(11); }
    else setViewMonth(m => m - 1);
  };
  const nextMonth = () => {
    if (viewMonth === 11) { setViewYear(y => y + 1); setViewMonth(0); }
    else setViewMonth(m => m + 1);
  };

  const fmt = (y, m, d) => `${y}-${String(m + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
  const todayStr = fmt(today.getFullYear(), today.getMonth(), today.getDate());

  const handleSelect = (day) => {
    onChange(fmt(viewYear, viewMonth, day));
    onClose();
  };

  const quickSelect = (months) => {
    const d = new Date();
    d.setMonth(d.getMonth() - months);
    onChange(fmt(d.getFullYear(), d.getMonth(), d.getDate()));
    onClose();
  };

  // 달력 셀 생성
  const cells = [];
  // 이전달 채움
  for (let i = firstDayOfWeek - 1; i >= 0; i--) {
    cells.push({ day: prevMonthDays - i, current: false });
  }
  // 이번달
  for (let d = 1; d <= daysInMonth; d++) {
    cells.push({ day: d, current: true });
  }
  // 다음달 채움
  const remaining = 42 - cells.length;
  for (let d = 1; d <= remaining; d++) {
    cells.push({ day: d, current: false });
  }

  return (
    <>
      <div className="cal-overlay" onClick={onClose} />
      <div className="cal-popup" ref={popupRef}
        style={{ position: 'fixed', top: pos.top, left: pos.left }}>

        <div style={{ fontSize: 9, fontWeight: 700, color: C.primary, letterSpacing: 1.5,
                      marginBottom: 8, fontFamily: FONT.mono }}>{label}</div>

        <div className="cal-header">
          <button onClick={prevMonth}>‹</button>
          <span className="cal-title">
            {viewYear}.{String(viewMonth + 1).padStart(2, '0')}
          </span>
          <button onClick={nextMonth}>›</button>
        </div>

        <div className="cal-weekdays">
          {WEEKDAYS.map(w => <span key={w}>{w}</span>)}
        </div>

        <div className="cal-grid">
          {cells.map((cell, i) => {
            const dateStr = cell.current ? fmt(viewYear, viewMonth, cell.day) : '';
            const isToday = dateStr === todayStr;
            const isSelected = selected && dateStr === value;
            const cls = [
              'cal-day',
              !cell.current && 'other-month',
              isToday && 'today',
              isSelected && 'selected',
            ].filter(Boolean).join(' ');

            return (
              <div key={i} className={cls}
                onClick={() => cell.current && handleSelect(cell.day)}>
                {cell.day}
              </div>
            );
          })}
        </div>

        <div className="cal-quick">
          <button onClick={() => quickSelect(1)}>1M</button>
          <button onClick={() => quickSelect(3)}>3M</button>
          <button onClick={() => quickSelect(6)}>6M</button>
          <button onClick={() => quickSelect(12)}>1Y</button>
          <button onClick={() => quickSelect(24)}>2Y</button>
        </div>
      </div>
    </>
  );
};


/* ═══════════════════════════════════════════════
   날짜 입력 필드 (클릭하면 캘린더 팝업)
   ═══════════════════════════════════════════════ */
const DateField = ({ label, value, onChange }) => {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <label style={{
        fontSize: 9, color: C.labelColor, fontWeight: 700,
        letterSpacing: 1, textTransform: 'uppercase', fontFamily: FONT.mono,
      }}>{label}</label>
      <div ref={ref} onClick={() => setOpen(true)} style={{
        padding: '6px 10px', fontSize: 12, fontFamily: FONT.sans,
        backgroundColor: C.inputBg, border: `1px solid ${C.inputBorder}`,
        borderRadius: 4, color: C.textSec, cursor: 'pointer',
        minWidth: 130, userSelect: 'none',
        transition: '0.15s',
        borderColor: open ? C.primary : C.inputBorder,
      }}>
        {value || 'SELECT'}
        <span style={{ marginLeft: 8, fontSize: 10, color: C.labelColor }}>📅</span>
      </div>
      {open && (
        <CalendarPicker
          value={value}
          onChange={onChange}
          onClose={() => setOpen(false)}
          anchorRef={ref}
          label={label}
        />
      )}
    </div>
  );
};


/* ═══════════════════════════════════════════════
   드래그 & 리사이즈 플로팅 차트
   ═══════════════════════════════════════════════ */
const FloatingChart = ({ ticker, onClose }) => {
  const [scale, setScale] = useState(1.2);
  const [position, setPosition] = useState({ x: 550, y: 150 });
  const [isDragging, setIsDragging] = useState(false);
  const offset = useRef({ x: 0, y: 0 });
  const BASE_WIDTH = 600, BASE_HEIGHT = 380;

  useEffect(() => {
    const script = document.createElement('script');
    script.src = 'https://s3.tradingview.com/tv.js';
    script.async = true;
    script.onload = () => {
      if (window.TradingView) {
        new window.TradingView.widget({
          autosize: true, symbol: `NASDAQ:${ticker}`, interval: 'D',
          timezone: 'Etc/UTC', theme: 'dark', style: '1', locale: 'en',
          container_id: 'tv_chart_container',
          backgroundColor: 'rgba(19, 23, 34, 0)',
        });
      }
    };
    document.head.appendChild(script);
    const esc = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', esc);
    return () => window.removeEventListener('keydown', esc);
  }, [ticker, onClose]);

  const handleMouseDown = (e) => {
    if (e.target.type === 'range') return;
    setIsDragging(true);
    offset.current = { x: e.clientX - position.x, y: e.clientY - position.y };
  };

  useEffect(() => {
    const move = (e) => { if (isDragging) setPosition({ x: e.clientX - offset.current.x, y: e.clientY - offset.current.y }); };
    const up = () => setIsDragging(false);
    if (isDragging) { window.addEventListener('mousemove', move); window.addEventListener('mouseup', up); }
    return () => { window.removeEventListener('mousemove', move); window.removeEventListener('mouseup', up); };
  }, [isDragging]);

  return (
    <div style={{
      position: 'fixed', left: position.x, top: position.y,
      width: BASE_WIDTH * scale, height: BASE_HEIGHT * scale,
      backgroundColor: `${C.bgDark}bf`, backdropFilter: 'blur(15px)',
      borderRadius: 12, border: `1px solid ${C.golden}66`,
      boxShadow: '0 30px 60px rgba(0,0,0,0.5)', zIndex: 9999, overflow: 'hidden',
      cursor: isDragging ? 'grabbing' : 'auto',
      transition: isDragging ? 'none' : 'width 0.1s, height 0.1s',
    }}>
      <div onMouseDown={handleMouseDown} style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '10px 15px', backgroundColor: `${C.golden}26`,
        borderBottom: `1px solid ${C.golden}33`, cursor: 'grab',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 15 }}>
          <span style={{ color: C.yolk, fontSize: 11, fontWeight: 900, fontFamily: FONT.sans }}>{ticker} CHART</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8,
                        paddingLeft: 10, borderLeft: `1px solid ${C.white}1a` }}>
            <span style={{ color: C.golden, fontSize: 9, fontWeight: 'bold', fontFamily: FONT.sans }}>SIZE</span>
            <input type="range" min="0.8" max="2.2" step="0.1" value={scale}
              onChange={(e) => setScale(parseFloat(e.target.value))}
              style={{ accentColor: C.primary, width: 60, cursor: 'pointer' }} />
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ color: C.labelColor, fontSize: 9, fontFamily: FONT.sans }}>ESC TO CLOSE</span>
          <button onClick={onClose} style={{
            background: 'none', border: 'none', color: C.neutral,
            fontSize: 16, cursor: 'pointer', padding: '0 4px', fontWeight: 'bold',
          }}>✕</button>
        </div>
      </div>
      <div id="tv_chart_container" style={{ height: 'calc(100% - 40px)', width: '100%' }} />
    </div>
  );
};


/* ═══════════════════════════════════════════════
   메인 HistoricalTab
   ═══════════════════════════════════════════════ */
const HistoricalTab = () => {
  const { ticker } = useOutletContext();
  const [isChartOpen, setIsChartOpen] = useState(false);

  const { initialStart, initialEnd } = useMemo(() => {
    const now = new Date();
    const s = new Date(); s.setMonth(s.getMonth() - 3);
    return { initialStart: s.toISOString().split('T')[0], initialEnd: now.toISOString().split('T')[0] };
  }, []);

  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState(false);
  const [startDate, setStartDate] = useState(initialStart);
  const [endDate, setEndDate] = useState(initialEnd);
  const [frequency, setFrequency] = useState('1d');

  const fetchHistory = useCallback(async () => {
    if (!ticker) return;
    setFetchError(false);
    try {
      setLoading(true);
      const res = await api.get(`/api/stock/historical/${ticker}`, {
        params: { start: startDate, end: endDate, frequency },
      });
      let rows = Array.isArray(res.data?.ohlcv) ? res.data.ohlcv : [];
      if (startDate) rows = rows.filter(r => r.date >= startDate);
      if (endDate) rows = rows.filter(r => r.date <= endDate);
      if (frequency === '1wk') rows = aggregateByPeriod(rows, 'week');
      else if (frequency === '1mo') rows = aggregateByPeriod(rows, 'month');
      rows.sort((a, b) => b.date.localeCompare(a.date));
      setData(rows);
    } catch (err) { console.error(err); setFetchError(true); }
    finally { setLoading(false); }
  }, [ticker, startDate, endDate, frequency]);

  useEffect(() => { fetchHistory(); }, [fetchHistory]);

  return (
    <div style={{ width: '100%', maxWidth: 1400, margin: '0 auto', position: 'relative' }}>

      {/* 에러 배너 */}
      {fetchError && (
        <div style={{
          background: C.bgDeeper, border: `1px solid ${C.primary}40`,
          borderLeft: `3px solid ${C.primary}`, borderRadius: 6,
          padding: '8px 16px', marginBottom: 16,
          fontSize: 11, color: C.up, fontFamily: FONT.sans,
        }}>
          ⚠ 가격 이력 데이터를 불러오지 못했습니다. 백엔드 연결 및 ticker를 확인해주세요.
        </div>
      )}

      {/* 차트 토글 */}
      <div style={{ display: 'flex', justifyContent: 'flex-start', marginBottom: 15 }}>
        <button onClick={() => setIsChartOpen(!isChartOpen)}
          className="chart-toggle-btn"
          style={{
            background: 'none', border: `1px solid ${C.borderHi}`,
            color: C.neutral, fontSize: 10, padding: '7px 15px',
            borderRadius: 4, cursor: 'pointer', fontWeight: 'bold',
            fontFamily: FONT.sans, transition: '0.3s',
          }}>
          {isChartOpen ? '✕ HIDE ANALYSIS' : '📊 SHOW ANALYSIS CHART'}
        </button>
      </div>

      {/* ── 필터 바 ── */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end',
        padding: '12px 20px', border: `1px solid ${C.border}`, borderRadius: 8,
        marginBottom: 10, backgroundColor: C.surface,
      }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <button onClick={() => { setStartDate(initialStart); setEndDate(initialEnd); setFrequency('1d'); }}
            className="reset-btn" style={{
              padding: '5px 14px', fontSize: 10, fontWeight: 800, fontFamily: FONT.sans,
              background: 'transparent', border: `1px solid ${C.primary}`,
              color: C.primary, borderRadius: 4, cursor: 'pointer', letterSpacing: 0.5,
            }}>
            RESET TO 3M DEFAULT
          </button>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
            <DateField label="START" value={startDate} onChange={setStartDate} />
            <span style={{ color: C.inputBorder, marginTop: 18, fontFamily: FONT.sans }}>~</span>
            <DateField label="END" value={endDate} onChange={setEndDate} />
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, alignItems: 'flex-end' }}>
          <label style={{
            fontSize: 9, color: C.labelColor, fontWeight: 700,
            letterSpacing: 1, textTransform: 'uppercase', fontFamily: FONT.sans,
          }}>DATA FREQUENCY</label>
          <div style={{
            display: 'flex', gap: 4, padding: 3,
            border: `1px solid ${C.inputBorder}`, borderRadius: 6,
            backgroundColor: C.inputBg,
          }}>
            {[{ id: '1d', label: 'Daily' }, { id: '1wk', label: 'Weekly' }, { id: '1mo', label: 'Monthly' }].map(f => (
              <button key={f.id} onClick={() => setFrequency(f.id)} style={{
                padding: '4px 12px', fontSize: 10, fontWeight: 700,
                fontFamily: FONT.sans, border: 'none', borderRadius: 4,
                cursor: 'pointer', transition: '0.2s',
                backgroundColor: frequency === f.id ? C.primary : 'transparent',
                color: frequency === f.id ? C.white : C.labelColor,
              }}>{f.label}</button>
            ))}
          </div>
        </div>
      </div>

      {/* ── 테이블 ── */}
      <div style={{
        borderRadius: 8, border: `1px solid ${C.border}`,
        overflow: 'auto', maxHeight: 650, backgroundColor: C.surface,
      }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: FONT.sans, tableLayout: 'fixed' }}>
          <thead style={{ position: 'sticky', top: 0, zIndex: 10, backgroundColor: C.inputBg }}>
            <tr style={{ borderBottom: `2px solid ${C.cardBg}` }}>
              <th style={{ ...thBase, textAlign: 'left', width: 110, paddingLeft: 20 }}>DATE</th>
              <th style={thBase}>OPEN</th>
              <th style={thBase}>CLOSE</th>
              <th style={thBase}>CHANGE%</th>
              <th style={thBase}>VOLUME</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan="5" style={loadingTd}>LOADING...</td></tr>
            ) : data.length === 0 ? (
              <tr><td colSpan="5" style={{ ...loadingTd, color: C.borderHi }}>
                데이터가 없습니다. 날짜 범위를 확인하세요.
              </td></tr>
            ) : data.map((item, index) => {
              const close = Number(item?.close || 0);
              const prevClose = data[index + 1] ? Number(data[index + 1].close) : close;
              const changePct = prevClose !== 0 ? ((close - prevClose) / prevClose * 100).toFixed(2) : '0.00';
              const isUp = parseFloat(changePct) >= 0;
              return (
                <tr key={index} className="h-row" style={{ borderBottom: `1px solid ${C.surface}`, transition: 'background-color 0.15s' }}>
                  <td style={{ ...tdBase, color: C.textSec, fontWeight: 600, textAlign: 'left', paddingLeft: 20 }}>{item.date}</td>
                  <td style={tdBase}>{Number(item.open).toFixed(2)}</td>
                  <td style={{ ...tdBase, fontWeight: 800, color: C.white }}>{close.toFixed(2)}</td>
                  <td style={{ ...tdBase, color: isUp ? C.up : C.down, fontWeight: 800 }}>
                    {isUp ? '▲' : '▼'} {Math.abs(changePct)}%
                  </td>
                  <td style={tdBase}>{Number(item.volume).toLocaleString()}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {isChartOpen && <FloatingChart ticker={ticker} onClose={() => setIsChartOpen(false)} />}

      <style>{`
        .chart-toggle-btn:hover { color: ${C.yolk} !important; border-color: ${C.yolk} !important; background: ${C.yolk}0d !important; }
        .h-row:hover { background-color: ${C.bgDark} !important; }
      `}</style>
    </div>
  );
};


/* ═══════════════════════════════════════════════
   주간/월간 집계 헬퍼
   ═══════════════════════════════════════════════ */
function aggregateByPeriod(rows, period) {
  if (!rows.length) return [];
  const buckets = {};
  rows.forEach(r => {
    const d = new Date(r.date);
    let key;
    if (period === 'week') {
      const day = d.getDay();
      const monday = new Date(d);
      monday.setDate(d.getDate() - ((day + 6) % 7));
      key = monday.toISOString().split('T')[0];
    } else {
      key = r.date.substring(0, 7);
    }
    if (!buckets[key]) {
      buckets[key] = { date: r.date, open: Number(r.open), high: -Infinity, low: Infinity, close: Number(r.close), volume: 0, firstDate: r.date, lastDate: r.date };
    }
    const b = buckets[key];
    if (r.date < b.firstDate) { b.firstDate = r.date; b.open = Number(r.open); }
    if (r.date > b.lastDate)  { b.lastDate = r.date; b.close = Number(r.close); }
    b.high = Math.max(b.high, Number(r.high || r.close));
    b.low  = Math.min(b.low, Number(r.low || r.close));
    b.volume += Number(r.volume || 0);
  });
  return Object.values(buckets).map(b => ({
    date: period === 'week' ? b.firstDate : b.lastDate,
    open: b.open, high: b.high, low: b.low, close: b.close, volume: b.volume,
  }));
}


/* ═══════════════════════════════════════════════
   공유 스타일 (토큰 기반)
   ═══════════════════════════════════════════════ */
const thBase = {
  padding: '10px 12px', fontSize: 10, fontWeight: 800,
  color: C.labelColor, letterSpacing: 1.2,
  textAlign: 'right', textTransform: 'uppercase',
  fontFamily: FONT.sans,
};

const tdBase = {
  padding: '8px 12px', fontSize: 12,
  color: C.textGray, textAlign: 'right', fontWeight: 500,
  fontFamily: FONT.sans,
};

const loadingTd = {
  padding: 40, textAlign: 'center',
  color: C.primary, fontSize: 13, fontWeight: 800,
  letterSpacing: 2, fontFamily: FONT.sans,
};

export default HistoricalTab;