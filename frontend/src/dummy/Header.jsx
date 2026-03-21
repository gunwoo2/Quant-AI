import React, { useState, useEffect } from 'react';
import api from '../api';

const overlayStyle = { position: 'fixed', top: 0, left: 0, width: '100%', height: '100%', background: 'rgba(0,0,0,0.85)', display: 'flex', justifyContent: 'center', alignItems: 'center', zIndex: 9999 };
const modalStyle = { background: '#1a1a1a', padding: '30px', borderRadius: '12px', width: '380px', border: '1px solid #333', boxShadow: '0 10px 25px rgba(0,0,0,0.5)' };
const inputStyle = { width: '100%', padding: '12px', marginTop: '15px', background: '#2a2a2a', border: '1px solid #444', color: 'white', boxSizing: 'border-box', borderRadius: '6px', outline: 'none', fontSize: '14px' };

export default function Header() {
  const [showModal, setShowModal] = useState(false);
  const [ticker, setTicker] = useState('');
  const [sector, setSector] = useState('');
  const [sectorOptions, setSectorOptions] = useState([]);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    const fetchSectors = async () => {
      try {
        const res = await api.get('/api/sectors');
        if (res.data && Array.isArray(res.data)) {
          setSectorOptions(res.data);
          const firstRaw = res.data[0]?.id || res.data[0];
          const firstId = String(firstRaw).replace(/[^a-zA-Z]/g, "").toLowerCase();
          setSector(firstId);
        }
      } catch (e) { console.error("섹터 로드 실패:", e); }
    };
    fetchSectors();
  }, []);

  const handleAdd = async () => {
    const trimmedTicker = ticker.trim().toUpperCase();
    if (!trimmedTicker) { alert("티커를 입력해주세요."); return; }
    setIsSaving(true);
    try {
      await api.post("/api/ticker", { ticker: trimmedTicker });
      alert("성공적으로 추가되었습니다!");
      setShowModal(false);
      setTicker('');
      window.location.reload();
    } catch (e) {
      const msg = e.response?.data?.detail || e.message || '오류가 발생했습니다.';
      alert(msg);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div style={{ height: '70px', borderBottom: '1px solid #222', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 30px', background: '#000000' }}>
      <div style={{ color: '#666', fontWeight: '600', fontSize: '12px', letterSpacing: '1px', textTransform: 'uppercase' }}>
        QUANT AI TERMINAL
      </div>
      <button
        onClick={() => setShowModal(true)}
        style={{ backgroundColor: '#D85604', color: 'white', border: 'none', padding: '10px 20px', borderRadius: '6px', fontWeight: '800', cursor: 'pointer', letterSpacing: '0.5px', fontSize: '12px', fontFamily: 'sans-serif' }}
      >
        + ADD TICKER
      </button>

      {showModal && (
        <div style={overlayStyle} onClick={(e) => e.target === e.currentTarget && !isSaving && setShowModal(false)}>
          <div style={modalStyle}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
              <div>
                <label style={{ color: '#D85604', fontSize: '11px', fontWeight: 'bold', letterSpacing: '0.5px' }}>TICKER SYMBOL</label>
                <input placeholder="예: NVDA, 005930.KS" value={ticker} onChange={e => setTicker(e.target.value)} style={inputStyle} disabled={isSaving} />
              </div>
              <div>
                <label style={{ color: '#D85604', fontSize: '11px', fontWeight: 'bold', letterSpacing: '0.5px' }}>SECTOR</label>
                <select value={sector} onChange={e => setSector(e.target.value)} style={{ ...inputStyle, cursor: 'pointer' }} disabled={isSaving}>
                  {sectorOptions.map((s, idx) => {
                    const val = s.id || s.key || String(s);
                    const label = s.en || s.ko || s.label || String(s);
                    return <option key={idx} value={val}>{label}</option>;
                  })}
                </select>
              </div>
              <div style={{ display: 'flex', gap: '10px', marginTop: '5px' }}>
                <button
                  onClick={handleAdd}
                  disabled={isSaving}
                  style={{
                    flex: 1, padding: '12px', background: '#D85604', border: 'none', color: 'white',
                    borderRadius: '6px', fontWeight: '800', cursor: isSaving ? 'wait' : 'pointer', fontSize: '13px',
                    opacity: isSaving ? 0.6 : 1,
                  }}
                >
                  {isSaving ? '추가 중...' : '확인'}
                </button>
                <button
                  onClick={() => !isSaving && setShowModal(false)}
                  style={{ flex: 1, padding: '12px', background: 'transparent', border: '1px solid #333', color: '#888', cursor: 'pointer', borderRadius: '6px', fontSize: '13px' }}
                >
                  취소
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

