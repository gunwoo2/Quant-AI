import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useOutletContext } from 'react-router-dom';
import api from '../api';

// --- 드래그 및 크기 조절 가능한 플로팅 차트 컴포넌트 ---
const FloatingChart = ({ ticker, onClose }) => {
  // 기본 크기를 20% 키운 값으로 설정 (600 * 1.2 = 720)
  const [scale, setScale] = useState(1.2);
  const [position, setPosition] = useState({ x: 550, y: 150 });
  const [isDragging, setIsDragging] = useState(false);
  const offset = useRef({ x: 0, y: 0 });

  const BASE_WIDTH = 600;
  const BASE_HEIGHT = 380;

  useEffect(() => {
    const script = document.createElement('script');
    script.src = 'https://s3.tradingview.com/tv.js';
    script.async = true;
    script.onload = () => {
      if (window.TradingView) {
        new window.TradingView.widget({
          autosize: true,
          symbol: `NASDAQ:${ticker}`,
          interval: 'D',
          timezone: 'Etc/UTC',
          theme: 'dark',
          style: '1',
          locale: 'en',
          container_id: 'tv_chart_container',
          backgroundColor: "rgba(19, 23, 34, 0)",
        });
      }
    };
    document.head.appendChild(script);

    const handleKeyDown = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [ticker, onClose]);

  const handleMouseDown = (e) => {
    // 슬라이더 클릭 시 드래그 방지
    if (e.target.type === 'range') return;
    setIsDragging(true);
    offset.current = { x: e.clientX - position.x, y: e.clientY - position.y };
  };

  useEffect(() => {
    const handleMouseMove = (e) => {
      if (!isDragging) return;
      setPosition({ x: e.clientX - offset.current.x, y: e.clientY - offset.current.y });
    };
    const handleMouseUp = () => setIsDragging(false);
    if (isDragging) {
      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
    }
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDragging]);

  return (
    <div style={{
      ...floatingContainerStyle,
      left: `${position.x}px`,
      top: `${position.y}px`,
      // 배율에 따른 크기 적용
      width: `${BASE_WIDTH * scale}px`,
      height: `${BASE_HEIGHT * scale}px`,
      cursor: isDragging ? 'grabbing' : 'auto',
      transition: isDragging ? 'none' : 'width 0.1s, height 0.1s'
    }}>
      <div style={headerStyle} onMouseDown={handleMouseDown}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '15px' }}>
          <span style={{ color: '#F3BE26', fontSize: '11px', fontWeight: '900' }}>{ticker} CHART</span>
          
          {/* 크기 조절 슬라이더 추가 */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', paddingLeft: '10px', borderLeft: '1px solid rgba(255,255,255,0.1)' }}>
            <span style={{ color: '#E88D14', fontSize: '9px', fontWeight: 'bold' }}>SIZE</span>
            <input 
              type="range" min="0.8" max="2.2" step="0.1" 
              value={scale} 
              onChange={(e) => setScale(parseFloat(e.target.value))}
              style={{ accentColor: '#D85604', width: '60px', cursor: 'pointer' }}
            />
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <span style={{ color: '#666', fontSize: '9px' }}>ESC TO CLOSE</span>
          <button onClick={onClose} style={closeIconStyle}>✕</button>
        </div>
      </div>
      <div id="tv_chart_container" style={{ height: 'calc(100% - 40px)', width: '100%' }} />
    </div>
  );
};

const HistoricalTab = () => {
  const { ticker } = useOutletContext();
  // 개선점 1: 초기 상태를 false로 변경 (접속 시 닫혀있음)
  const [isChartOpen, setIsChartOpen] = useState(false);

  const { initialStart, initialEnd } = useMemo(() => {
    const now = new Date();
    const startObj = new Date();
    startObj.setMonth(startObj.getMonth() - 3);
    return { initialStart: startObj.toISOString().split('T'), initialEnd: now.toISOString().split('T') };
  }, []);

  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [startDate, setStartDate] = useState(initialStart);
  const [endDate, setEndDate] = useState(initialEnd);
  const [frequency, setFrequency] = useState('1d');

  const fetchHistory = useCallback(async () => {
    if (!ticker) return;
    try {
      setLoading(true);
      const res = await api.get(`/api/stock/history/${ticker}`, {
        params: { start: startDate, end: endDate, frequency: frequency }
      });
      setData(Array.isArray(res.data) ? res.data : []);
    } catch (err) { console.error(err); } finally { setLoading(false); }
  }, [ticker, startDate, endDate, frequency]);

  useEffect(() => { fetchHistory(); }, [fetchHistory]);

  return (
    <div style={{ width: '100%', maxWidth: '1400px', margin: '0 auto', position: 'relative' }}>
      <div style={{ display: 'flex', justifyContent: 'flex-start', marginBottom: '15px' }}>
        <button 
          onClick={() => setIsChartOpen(!isChartOpen)} 
          className="chart-toggle-btn"
          style={chartToggleBtnStyle}
        >
          {isChartOpen ? '✕ HIDE ANALYSIS' : '📊 SHOW ANALYSIS CHART'}
        </button>
      </div>

      {/* 필터 및 테이블 영역 (기존 스타일 유지) */}
      <div style={filterBarStyle}>
        {/* ... (기존 필터 코드와 동일) */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <button onClick={() => { setStartDate(initialStart); setEndDate(initialEnd); }} className="reset-btn" style={defaultBtnStyle}>
            RESET TO 3M DEFAULT
          </button>
          <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
            <div style={inputGroupStyle}><label style={labelStyle}>START</label><input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} style={inputStyle} /></div>
            <span style={{ color: '#333', marginTop: '18px' }}>~</span>
            <div style={inputGroupStyle}><label style={labelStyle}>END</label><input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} style={inputStyle} /></div>
          </div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', alignItems: 'flex-end' }}>
          <label style={labelStyle}>DATA FREQUENCY</label>
          <div style={freqContainerStyle}>
            {[{ id: '1d', label: 'Daily' }, { id: '1wk', label: 'Weekly' }, { id: '1mo', label: 'Monthly' }].map((f) => (
              <button key={f.id} onClick={() => setFrequency(f.id)}
                style={{ ...freqButtonStyle, backgroundColor: frequency === f.id ? '#D85604' : 'transparent', color: frequency === f.id ? '#fff' : '#666' }}>{f.label}</button>
            ))}
          </div>
        </div>
      </div>

      <div style={tableWrapperStyle}>
        <table style={{ ...tableStyle, tableLayout: 'fixed' }}>
          <thead style={stickyHeaderStyle}>
            <tr style={{ borderBottom: '2px solid #1a1a1a' }}>
              <th style={{ ...thStyle, textAlign: 'left', width: '110px', paddingLeft: '20px' }}>DATE</th>
              <th style={thStyle}>OPEN</th><th style={thStyle}>CLOSE</th><th style={thStyle}>CHANGE%</th><th style={thStyle}>VOLUME</th><th style={thStyle}>PER</th><th style={{ ...thStyle, color: '#D85604' }}>ROIC</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (<tr><td colSpan="7" style={loadingTdStyle}>LOADING...</td></tr>) : data.map((item, index) => {
              const close = Number(item?.close_price || 0);
              const prevClose = data[index + 1] ? Number(data[index + 1].close_price) : close;
              const changePct = prevClose !== 0 ? ((close - prevClose) / prevClose * 100).toFixed(2) : "0.00";
              const isUp = parseFloat(changePct) >= 0;
              return (
                <tr key={index} className="h-row" style={trStyle}>
                  <td style={dateTdStyle}>{item.trading_date}</td>
                  <td style={commonTdStyle}>{Number(item.open_price).toFixed(2)}</td>
                  <td style={{ ...commonTdStyle, fontWeight: '800', color: '#FFFFFF' }}>{close.toFixed(2)}</td>
                  <td style={{ ...commonTdStyle, color: isUp ? '#AD1B02' : '#0066FF', fontWeight: '800' }}>{isUp ? '▲' : '▼'} {Math.abs(changePct)}%</td>
                  <td style={commonTdStyle}>{Number(item.volume).toLocaleString()}</td>
                  <td style={commonTdStyle}>{item.per || '-'}</td>
                  <td style={{ ...commonTdStyle, color: '#F3BE26', fontWeight: 'bold' }}>{item.roic ? `${item.roic}%` : '-'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {isChartOpen && <FloatingChart ticker={ticker} onClose={() => setIsChartOpen(false)} />}

      <style>{`
        .chart-toggle-btn:hover { color: #F3BE26 !important; border-color: #F3BE26 !important; background: rgba(243, 190, 38, 0.05) !important; }
        .h-row:hover { background-color: #0f0f0f !important; }
      `}</style>
    </div>
  );
};

// --- 스타일 객체 (기존 유지) ---
const chartToggleBtnStyle = { background: 'none', border: '1px solid #444', color: '#888', fontSize: '10px', padding: '7px 15px', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold', transition: '0.3s' };
const floatingContainerStyle = { position: 'fixed', backgroundColor: 'rgba(15, 15, 15, 0.75)', backdropFilter: 'blur(15px)', borderRadius: '12px', border: '1px solid rgba(232, 141, 20, 0.4)', boxShadow: '0 30px 60px rgba(0,0,0,0.5)', zIndex: 9999, overflow: 'hidden' };
const headerStyle = { display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 15px', backgroundColor: 'rgba(232, 141, 20, 0.15)', borderBottom: '1px solid rgba(255, 255, 255, 0.05)', cursor: 'grab' };
const closeIconStyle = { background: 'none', border: 'none', color: '#888', cursor: 'pointer', fontSize: '14px' };
const filterBarStyle = { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '25px', padding: '20px', backgroundColor: '#080808', borderRadius: '12px', border: '1px solid #1a1a1a' };
const defaultBtnStyle = { background: 'none', border: '1px solid #D85604', color: '#D85604', fontSize: '9px', padding: '4px 10px', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold' };
const labelStyle = { fontSize: '10px', color: '#555', fontWeight: 'bold', marginBottom: '6px' };
const inputStyle = { backgroundColor: '#111', border: '1px solid #222', color: '#eee', padding: '8px 12px', borderRadius: '6px', fontSize: '12px', outline: 'none' };
const freqContainerStyle = { display: 'flex', backgroundColor: '#000', padding: '4px', borderRadius: '8px', border: '1px solid #111' };
const freqButtonStyle = { border: 'none', padding: '6px 16px', borderRadius: '6px', fontSize: '11px', fontWeight: 'bold', cursor: 'pointer' };
const tableWrapperStyle = { overflowX: 'auto', backgroundColor: '#080808', borderRadius: '12px', border: '1px solid #1a1a1a', maxHeight: '700px' };
const tableStyle = { width: '100%', borderCollapse: 'collapse', textAlign: 'right' };
const stickyHeaderStyle = { position: 'sticky', top: 0, zIndex: 10, backgroundColor: '#080808' };
const trStyle = { borderBottom: '1px solid #111' };
const inputGroupStyle = { display: 'flex', flexDirection: 'column' };
const dateTdStyle = { padding: '18px 10px', textAlign: 'left', paddingLeft: '20px', width: '110px', backgroundColor: 'rgba(216, 86, 4, 0.05)', color: '#e5e5e5', fontWeight: '600', fontSize: '13px', fontFamily: '"JetBrains Mono", monospace' };
const commonTdStyle = { padding: '18px 10px', color: '#bbbbbb', fontSize: '13px', fontFamily: '"JetBrains Mono", monospace' };
const thStyle = { padding: '20px 10px', color: '#444', fontWeight: '900', fontSize: '11px', fontFamily: '"JetBrains Mono", monospace' };
const loadingTdStyle = { padding: '100px', textAlign: 'center', color: '#D85604', fontSize: '13px', fontWeight: 'bold' };

export default HistoricalTab;