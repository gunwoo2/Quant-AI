import { useState, useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import api from '../api';

export default function Sidebar({ isCollapsed, setIsCollapsed }) {
  const loc = useLocation();
  const [sectors, setSectors] = useState([]);

  useEffect(() => {
    const fetchSectors = async () => {
      try {
        const res = await api.get('/api/sectors');
        if (res?.data && Array.isArray(res.data)) {
          setSectors(res.data);
        }
      } catch (e) {
        console.error("Sidebar data fetch failed:", e);
      }
    };
    fetchSectors();
  }, []);

  const icons = {
    it: '💻', financials: '🏦', healthcare: '💊', discretionary: '🚗',
    staples: '🛒', comm: '📡', industrials: '🏗️', energy: '⚡',
    materials: '🧪', utilities: '🚰', realestate: '🏢'
  };

  const navStyle = (active) => ({
    display: 'flex',
    alignItems: 'center',
    padding: '0 20px',
    color: active ? '#D85604' : '#888',
    textDecoration: 'none',
    backgroundColor: active ? '#111' : 'transparent',
    borderLeft: active ? '3px solid #D85604' : '3px solid transparent',
    transition: 'all 0.2s ease',
    height: '50px',
    width: '100%',
    boxSizing: 'border-box'
  });

  return (
    <div style={{
      width: isCollapsed ? '70px' : '260px',
      backgroundColor: '#000',
      position: 'fixed',
      top: 0, left: 0,
      height: '100vh',
      borderRight: '1px solid #222',
      zIndex: 1000,
      transition: 'width 0.3s ease',
      overflowX: 'hidden'
    }}>
      
      {/* 로고 영역 */}
      <div style={{ display: 'flex', alignItems: 'center', height: '70px', padding: '0 20px', justifyContent: isCollapsed ? 'center' : 'space-between', borderBottom: '1px solid #111' }}>
        {!isCollapsed && <h2 style={{ color: '#D85604', margin: 0, fontSize: '18px', fontWeight: '800', whiteSpace: 'nowrap' }}>QUANT AI</h2>}
        <button onClick={() => setIsCollapsed(!isCollapsed)} style={{ background: 'none', border: 'none', color: '#444', cursor: 'pointer', fontSize: '18px' }}>
          {isCollapsed ? '☰' : '✕'}
        </button>
      </div>

      <nav style={{ marginTop: '10px' }}>
        <Link to="/main" style={navStyle(loc.pathname === '/main')}>
          <span style={{ minWidth: '30px', textAlign: 'center', fontSize: '18px' }}>🏠</span>
          {!isCollapsed && <span style={{ marginLeft: '12px', fontWeight: 'bold' }}>HOME</span>}
        </Link>

        <a href="https://finviz.com/map.ashx" target="_blank" rel="noopener noreferrer" style={navStyle(false)}>
          <span style={{ minWidth: '30px', textAlign: 'center', fontSize: '18px' }}>🔥</span>
          {!isCollapsed && <span style={{ marginLeft: '12px', fontWeight: 'bold' }}>HEATMAP</span>}
        </a>

        {!isCollapsed && <div style={{ padding: '25px 20px 10px', fontSize: '11px', color: '#444', fontWeight: 'bold', letterSpacing: '1px' }}>SECTORS</div>}
        
        {sectors.map((s, idx) => {
          const raw = s.id || s;
          const sId = String(raw).replace(/[^a-zA-Z]/g, "").toLowerCase() || 'unknown';
          const sKo = String(s.ko || raw).replace(/[a-zA-Z()']/g, "").replace(/,/g, "").trim() || sId.toUpperCase();
          
          // 🚨 수정 포인트: includes 대신 정확한 경로 일치 확인
          // util-it-ies에 it가 포함되어 있어도, URL이 "/main/it"이 아니면 불이 켜지지 않음
          const isActive = loc.pathname === `/main/${sId}`;

          return (
            <Link key={sId + idx} to={`/main/${sId}`} style={navStyle(isActive)}>
              <span style={{ minWidth: '30px', textAlign: 'center', fontSize: '16px' }}>
                {icons[sId] || '▪'}
              </span>
              {!isCollapsed && (
                <div style={{ 
                  marginLeft: '12px', 
                  display: 'flex', 
                  alignItems: 'baseline', 
                  flexGrow: 1,
                  minWidth: 0
                }}>
                  <span style={{ 
                    fontSize: '13px', 
                    fontWeight: '500', 
                    color: isActive ? '#D85604' : '#ccc',
                    whiteSpace: 'nowrap'
                  }}>
                    {sKo}
                  </span>
                  <span style={{ 
                    fontSize: '10px', 
                    opacity: 0.3, 
                    marginLeft: '8px', 
                    textTransform: 'uppercase',
                    flexShrink: 0
                  }}>
                    {sId}
                  </span>
                </div>
              )}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}