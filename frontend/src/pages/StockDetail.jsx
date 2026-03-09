import React, { useState, useEffect } from 'react';
import { useParams, useLocation, useNavigate, Outlet } from 'react-router-dom'; // 2번 줄 유지
import api from '../api';

export default function StockDetail() {
  const { ticker } = useParams();
  const location = useLocation();
  const navigate = useNavigate();

  const [stockData, setStockData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [isDescOpen, setIsDescOpen] = useState(false);

  useEffect(() => {
    const fetchStockDetail = async () => {
      try {
        setLoading(true);
        // 백엔드 주소가 /api/stock/${ticker} 인지 다시 한번 확인해보세요!
        const res = await api.get(`/api/stock/detail/${ticker}`);
        setStockData(res.data);
      } catch (err) {
        console.error("데이터 로드 실패:", err);
        setStockData(null);
      } finally {
        setLoading(false);
      }
    };
    fetchStockDetail();
  }, [ticker]);

  if (loading) return (
    <div style={{ backgroundColor: '#000', minHeight: '100vh', display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
      <div style={{ color: '#D85604', fontSize: '20px', fontWeight: 'bold', letterSpacing: '2px' }}>LOADING DATA...</div>
    </div>
  );

  if (!stockData) return (
    <div style={{ color: '#fff', padding: '100px', textAlign: 'center', backgroundColor: '#000', minHeight: '100vh' }}>
      <h2 style={{ color: '#AD1B02' }}>Stock Not Found</h2>
      <p style={{ color: '#666' }}>요청하신 티커({ticker})의 정보를 찾을 수 없습니다.</p>
      <button onClick={() => navigate('/')} style={{ background: 'none', border: '1px solid #D85604', color: '#D85604', padding: '10px 20px', cursor: 'pointer', marginTop: '20px' }}>메인으로 돌아가기</button>
    </div>
  );

  const { header, realtime } = stockData;
  const pathParts = location.pathname.split('/');
  const lastPath = pathParts[pathParts.length - 1];
  const currentTab = lastPath === ticker ? 'summary' : lastPath;

  const tabs = [
    { id: 'summary', label: 'Summary' },
    { id: 'historical', label: 'Historical' },
    { id: 'financials', label: 'Financials' },
    { id: 'quant-rating', label: 'Quant Rating' },
    { id: 'rating', label: 'AI Rating' },
  ];

  return (
    <div style={{ backgroundColor: '#000', color: '#fff', minHeight: '100vh', padding: '30px 50px' }}>
      
      {/* 1. 상단 헤더: 네온 오렌지 포인트 */}
      <div style={{ marginBottom: '40px', borderLeft: '4px solid #D85604', paddingLeft: '20px' }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: '15px' }}>
          <h1 style={{ fontSize: '52px', color: '#D85604', margin: 0, fontWeight: '900', letterSpacing: '-1px' }}>
            {header.ticker}
          </h1>
          <span style={{ fontSize: '24px', color: '#555', fontWeight: '600' }}>{header.name}</span>
        </div>
        
        {realtime && (
          <div style={{ marginTop: '5px', display: 'flex', alignItems: 'center', gap: '15px' }}>
            <span style={{ fontSize: '30px', fontWeight: '800', fontFamily: 'monospace' }}>
              ${realtime.price?.toLocaleString(undefined, { minimumFractionDigits: 2 })}
            </span>
            <div style={{ 
              display: 'flex', alignItems: 'center', gap: '8px', 
              color: realtime.change >= 0 ? '#AD1B02' : '#0066FF',
              backgroundColor: realtime.change >= 0 ? 'rgba(173, 27, 2, 0.1)' : 'rgba(0, 102, 255, 0.1)',
              padding: '4px 12px', borderRadius: '4px', fontSize: '18px', fontWeight: '700'
            }}>
              {realtime.change > 0 ? '▲' : realtime.change < 0 ? '▼' : ''} 
              {Math.abs(realtime.amount_change || 0).toFixed(2)} ({realtime.changesPercentage}%)
            </div>
          </div>
        )}
      </div>

      {/* 2. 회사 설명: 다크 카드 디자인 */}
      <div style={{ 
        backgroundColor: '#080808', 
        padding: '30px', 
        borderRadius: '12px', 
        border: '1px solid #1a1a1a', 
        marginBottom: '40px',
        boxShadow: '0 10px 30px rgba(0,0,0,0.5)'
      }}>
        <h4 style={{ margin: '0 0 15px 0', color: '#E88D14', fontSize: '12px', textTransform: 'uppercase', letterSpacing: '2px', fontWeight: '800' }}>
          Company Profile
        </h4>
        <p style={{ 
          margin: 0, fontSize: '16px', lineHeight: '1.8', color: '#999',
          display: '-webkit-box',
          WebkitLineClamp: isDescOpen ? 'unset' : '3',
          WebkitBoxOrient: 'vertical',
          overflow: 'hidden',
          transition: 'all 0.3s'
        }}>
          {header.description || "No description available for this stock."}
        </p>
        <button 
          onClick={() => setIsDescOpen(!isDescOpen)}
          style={{ 
            background: 'none', border: 'none', color: '#E669A2', // Chinese Pink 포인트
            padding: '12px 0 0 0', cursor: 'pointer', fontSize: '13px', fontWeight: 'bold', textTransform: 'uppercase'
          }}
        >
          {isDescOpen ? 'Collapse ▲' : 'Read More ▼'}
        </button>
      </div>

      {/* 3. 내비게이션 탭: 세련된 언더라인 애니메이션 스타일 */}
      <div style={{ display: 'flex', gap: '40px', borderBottom: '1px solid #111', marginBottom: '30px' }}>
        {tabs.map((tab) => {
          const isActive = currentTab === tab.id;
          return (
            <div 
              key={tab.id} 
              style={{
                padding: '15px 0',
                cursor: 'pointer',
                fontSize: '14px',
                fontWeight: '800',
                textTransform: 'uppercase',
                letterSpacing: '1px',
                color: isActive ? '#D85604' : '#444',
                borderBottom: isActive ? '3px solid #D85604' : '3px solid transparent',
                transition: 'all 0.3s ease',
                position: 'relative',
                top: '1px'
              }}
              onClick={() => navigate(`/stock/${ticker}/${tab.id}`)}
              onMouseEnter={(e) => !isActive && (e.target.style.color = '#888')}
              onMouseLeave={(e) => !isActive && (e.target.style.color = '#444')}
            >
              {tab.label}
            </div>
          );
        })}
      </div>

      {/* 컨텐츠 영역 */}
      <div style={{ padding: '10px 0' }}>
        {/* stockData 안에 quant 관련 데이터가 들어있을 테니 함께 넘겨줍니다 */}
        <Outlet context={{ 
          ticker, 
          header, 
          realtime, 
          quantData: stockData.quant // 또는 백엔드에서 주는 데이터 키값에 맞춰서 수정
        }} /> 
      </div>
    </div>
  );
}