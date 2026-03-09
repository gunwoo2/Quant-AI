import React, { useState, useEffect } from 'react';
import api from '../api';

// --- 기존 디자인 스타일 유지 ---
const overlayStyle = { position: 'fixed', top: 0, left: 0, width: '100%', height: '100%', background: 'rgba(0,0,0,0.85)', display: 'flex', justifyContent: 'center', alignItems: 'center', zIndex: 9999 };
const modalStyle = { background: '#1a1a1a', padding: '30px', borderRadius: '12px', width: '380px', border: '1px solid #333', boxShadow: '0 10px 25px rgba(0,0,0,0.5)' };
const inputStyle = { width: '100%', padding: '12px', marginTop: '15px', background: '#2a2a2a', border: '1px solid #444', color: 'white', boxSizing: 'border-box', borderRadius: '6px', outline: 'none', fontSize: '14px' };

export default function Header() {
  const [showModal, setShowModal] = useState(false);
  const [ticker, setTicker] = useState('');
  const [sector, setSector] = useState('');
  const [sectorOptions, setSectorOptions] = useState([]);
  const [isSaving, setIsSaving] = useState(false);
  
  // ✅ 실시간 메시지 상태만 추가 (디자인에 영향 없음)
  const [streamMsg, setStreamMsg] = useState('');

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

  // ✅ SSE 스트리밍 로직 통합
  const handleAdd = async () => {
    const trimmedTicker = ticker.trim().toUpperCase();
    if (!trimmedTicker) { alert("티커를 입력해주세요."); return; }
    
    setIsSaving(true);
    setStreamMsg("연결 중..."); 

    try {
      let detectedCountry = 'US'; 
      if (trimmedTicker.endsWith('.KS') || trimmedTicker.endsWith('.KQ')) detectedCountry = 'KR';

      const response = await fetch('/api/add-ticker-stream/', { 
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker: trimmedTicker, sector, country: detectedCountry })
      });
      
      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value);
        // SSE 데이터 파싱 (여러 줄이 뭉쳐서 들어올 수 있음)
        const lines = chunk.split("\n\n");
        
        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const data = JSON.parse(line.replace("data: ", ""));
              setStreamMsg(data.message); // 메시지 업데이트

              if (data.status === "success") {
                // 1. 팝업 메시지 띄우기
                alert("성공적으로 추가되었습니다!"); 
                
                // 2. 모달 닫기 및 상태 정리
                setShowModal(false);
                setIsSaving(false);
                
                // 3. 페이지 새로고침 (정말 필요하다면)
                window.location.reload(); 
                return;
              }
            } catch (jsonErr) { console.error("JSON 파싱 에러:", jsonErr); }
          }
        }
      }
    } catch (e) {
      console.error("추가 실패:", e);
      alert(e.message || '오류가 발생했습니다.');
      setStreamMsg(''); // 에러 시 초기화
      setIsSaving(false);
    } 
    // ✅ finally에서 무조건 초기화하던 로직을 삭제했습니다.
  };

  return (
    <div style={{ height: '70px', borderBottom: '1px solid #222', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 30px', background: '#000000' }}>
      <div style={{ color: '#666', fontWeight: '600', fontSize: '12px', letterSpacing: '1px', textTransform: 'uppercase' }}>
        Quant AI Intelligence Dashboard
      </div>
      
      <button 
        onClick={() => setShowModal(true)} 
        style={{ backgroundColor: '#D85604', color: 'white', border: 'none', padding: '10px 20px', borderRadius: '6px', fontWeight: '800', cursor: 'pointer', fontSize: '13px', transition: 'all 0.2s' }}
        onMouseOver={(e) => e.target.style.backgroundColor = '#AD1B02'}
        onMouseOut={(e) => e.target.style.backgroundColor = '#D85604'}
      >
        + ADD TICKER
      </button>

      {showModal && (
        <div style={overlayStyle} onClick={(e) => e.target === e.currentTarget && !isSaving && setShowModal(false)}>
          <div style={modalStyle}>
            <h3 style={{ color: 'white', margin: '0 0 10px 0', fontSize: '20px', fontWeight: '800' }}>새 종목 추가</h3>
            <p style={{ color: '#666', fontSize: '13px', marginBottom: '25px' }}>분석할 주식의 티커를 입력하고 섹터를 지정하세요.</p>
            
            <div style={{ marginBottom: '20px' }}>
              <label style={{ color: '#D85604', fontSize: '11px', fontWeight: 'bold', letterSpacing: '0.5px' }}>TICKER SYMBOL</label>
              <input placeholder="예: NVDA, 005930.KS" value={ticker} onChange={e => setTicker(e.target.value)} style={inputStyle} disabled={isSaving} />
            </div>
            
            <div style={{ marginBottom: '10px' }}>
              <label style={{ color: '#D85604', fontSize: '11px', fontWeight: 'bold', letterSpacing: '0.5px' }}>SELECT SECTOR</label>
              <select value={sector} onChange={e => setSector(e.target.value)} style={{ ...inputStyle, cursor: 'pointer' }} disabled={isSaving}>
                {sectorOptions.map((opt, idx) => {
                  const raw = opt.id || opt;
                  const sId = String(raw).replace(/[^a-zA-Z]/g, "").toLowerCase();
                  const sKo = String(opt.ko || raw).replace(/[a-zA-Z()']/g, "").replace(/,/g, "").trim();
                  return <option key={sId + idx} value={sId} style={{ background: '#1a1a1a' }}>{sKo} ({sId.toUpperCase()})</option>;
                })}
              </select>
            </div>

            <div style={{ display: 'flex', gap: '10px', marginTop: '30px' }}>
              <button 
                onClick={handleAdd} 
                disabled={isSaving}
                style={{ 
                  flex: 1, padding: '12px', background: '#D85604', border: 'none', color: 'white', 
                  fontWeight: '800', borderRadius: '6px', opacity: isSaving ? 0.7 : 1, 
                  cursor: isSaving ? 'not-allowed' : 'pointer' 
                }}
              >
                {/* ✅ 버튼 내부 텍스트만 실시간으로 변경 */}
                {isSaving ? (streamMsg || '분석 중...') : '저장하기'}
              </button>
              <button 
                onClick={() => !isSaving && setShowModal(false)} 
                style={{ flex: 1, padding: '12px', background: 'transparent', border: '1px solid #333', color: '#888', cursor: 'pointer', borderRadius: '6px', fontWeight: '600' }}
              >
                취소
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}