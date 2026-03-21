import React, { useState, useEffect, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';

export default function MainTable({ stocks = [], loading = false }) {
  const { sectorId } = useParams();
  const navigate = useNavigate();
  
  const [filters, setFilters] = useState({
    ticker: '', name: '', country: 'ALL', sector: sectorId || 'ALL', rating: 'ALL'
  });

  // --- 1. 정렬 상태: AI Rating(grade) 오름차순을 디폴트로 설정 ---
  const [sortConfig, setSortConfig] = useState({ key: 'grade', direction: 'asc' });

  const sectorOptions = [
    { id: "financials", ko: "금융" }, { id: "discretionary", ko: "자유/경기 소비재" },
    { id: "realestate", ko: "부동산" }, { id: "industrials", ko: "산업재" },
    { id: "energy", ko: "에너지" }, { id: "materials", ko: "원자재" },
    { id: "utilities", ko: "유틸리티" }, { id: "healthcare", ko: "헬스케어" },
    { id: "comm", ko: "통신서비스" }, { id: "staples", ko: "필수소비재" },
    { id: "it", ko: "정보통신기술" }
  ];

  // 정렬 요청 핸들러 (3단계: 오름 -> 내림 -> 해제)
  const handleSort = (key) => {
    setSortConfig((prev) => {
      if (prev.key !== key) return { key, direction: 'asc' };
      if (prev.direction === 'asc') return { key, direction: 'desc' };
      return { key: null, direction: 'asc' }; // 정렬 해제
    });
  };

  useEffect(() => {
    setFilters(prev => ({ ...prev, sector: sectorId || 'ALL' }));
  }, [sectorId]);

  // --- 2. 필터링 + 정렬 통합 로직 ---
  // --- 2. 필터링 + 정렬 통합 로직 ---
  const processedData = useMemo(() => {
    // 1. 필터링 로직
    let result = stocks.filter(stock => {
      // API 데이터에서 final_grade를 우선 참조 (누락 방지)
      const currentGrade = (stock.final_grade || stock.grade || '').toUpperCase().trim();
      const stockCountry = (stock.country || '').toUpperCase().trim();
      
      // Ticker & Name 필터
      const matchTicker = (stock.ticker || '').toLowerCase().includes(filters.ticker.toLowerCase());
      const matchName = (stock.name || stock.company_name || '').toLowerCase().includes(filters.name.toLowerCase());
      
      // Country 필터 (공백일 경우 US로 간주하는 로직 포함)
      const matchCountry = filters.country === 'ALL' || 
                           (filters.country === 'KR' && (stockCountry === 'KR' || stockCountry === 'KOREA')) ||
                           (filters.country === 'US' && (stockCountry === 'US' || stockCountry === 'USA' || stockCountry === ''));
      
      // Sector 필터
      const matchSector = filters.sector === 'ALL' || 
                          String(stock.sector).toLowerCase().trim() === String(filters.sector).toLowerCase().trim();
      
      // Rating 필터 (중요: stock.final_grade 기준으로 체크)
      const matchRating = filters.rating === 'ALL' || currentGrade === filters.rating;

      return matchTicker && matchName && matchCountry && matchSector && matchRating;
    });

    // 2. 정렬 로직
    if (sortConfig.key) {
      result.sort((a, b) => {
        // 정렬 키가 grade일 경우 실제 데이터인 final_grade를 사용하도록 매핑
        const sortKey = sortConfig.key === 'grade' ? 'final_grade' : sortConfig.key;
        let aVal = a[sortKey];
        let bVal = b[sortKey];

        // [등급 정렬] S(1) -> D(7) 순서이므로 숫자가 작을수록 높은 등급임 (오름차순 시 S가 위로)
        if (sortKey === 'final_grade') {
          const weights = { 'S': 1, 'A+': 2, 'A': 3, 'B+': 4, 'B': 5, 'C': 6, 'D': 7 };
          const aWeight = weights[String(aVal).toUpperCase().trim()] || 99;
          const bWeight = weights[String(bVal).toUpperCase().trim()] || 99;
          
          // 오름차순(asc)일 때 숫자가 작은(높은 등급)게 위로
          return sortConfig.direction === 'asc' ? aWeight - bWeight : bWeight - aWeight;
        }

        // [숫자 정렬] Price, Change 등
        if (!isNaN(aVal) && !isNaN(bVal) && typeof aVal !== 'boolean') {
          return sortConfig.direction === 'asc' ? Number(aVal) - Number(bVal) : Number(bVal) - Number(aVal);
        }

        // [문자 정렬] Ticker, Name 등
        const aStr = String(aVal || '').toLowerCase();
        const bStr = String(bVal || '').toLowerCase();
        return sortConfig.direction === 'asc' 
          ? aStr.localeCompare(bStr) 
          : bStr.localeCompare(aStr);
      });
    }
    return result;
  }, [stocks, filters, sortConfig]);

  const resetFilters = () => setFilters({ ticker: '', name: '', country: 'ALL', sector: 'ALL', rating: 'ALL' });

  const getGradeStyle = (grade) => {
    const g = grade?.toUpperCase().trim() || '-';
    switch (g) {
      case 'S':
        return { label: "S", title: "Strong Buy", color: "#00F5FF", bg: "rgba(0, 245, 255, 0.15)", status: "기관급 QVM 최상단", action: "최상위 5% '슈퍼 사이클'" };
      case 'A+':
        return { label: "A+", title: "Buy", color: "#00F5FF", bg: "rgba(0, 245, 255, 0.15)", status: "펀더멘털 가속화", action: "공격적 편입 유효" };
      case 'A':
        return { label: "A", title: "Outperform", color: "#D85604", bg: "rgba(216, 86, 4, 0.15)", status: "안정적 밸류에이션", action: "조정 시 비중 확대" };
      case 'B+':
        return { label: "B+", title: "Hold", color: "#F3BE26", bg: "rgba(243, 190, 38, 0.15)", status: "에너지 응축 구간", action: "관망 후 대응 권장" };
      case 'B':
        return { label: "B", title: "Underperform", color: "#AD1B02", bg: "rgba(173, 27, 2, 0.15)", status: "성장성 정체 우려", action: "교체 매매 고려" };
      case 'C':
        return { label: "C", title: "Sell", color: "#AD1B02", bg: "rgba(173, 27, 2, 0.15)", status: "하락 추세 지속", action: "리스크 관리 시급" };
      case 'D':
        return { label: "D", title: "Strong Sell", color: "#666", bg: "rgba(102, 102, 102, 0.15)", status: "역성장 트랩", action: "즉시 관심 제외" };
      default:
        return { label: "-", title: "N/A", color: "#444", bg: "transparent", status: "-", action: "-" };
    }
  };
  
  // 스타일 객체
  const thStyle = { padding: '12px 15px', color: '#666', fontWeight: '700', textTransform: 'uppercase', fontSize: '10px', letterSpacing: '1.5px', borderBottom: '1px solid #222', cursor: 'pointer' };
  const tdStyle = { padding: '16px 15px', color: '#eee', borderBottom: '1px solid #111' };
  const filterInputStyle = { padding: '10px 14px', backgroundColor: '#0f0f0f', border: '1px solid #222', color: '#fff', borderRadius: '6px', fontSize: '13px', outline: 'none' };

  if (loading) return <div style={{ color: '#D85604', padding: '40px', textAlign: 'center', backgroundColor: '#000', fontWeight: 'bold' }}>데이터 로딩 중... 장외 시간에는 약 1~2분 정도의 시간이 소요됩니다...</div>;

  return (
    <div style={{ backgroundColor: '#000', padding: '24px', borderRadius: '12px' }}>
      {/* 필터 섹션 */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', marginBottom: '24px', alignItems: 'center' }}>
        <input placeholder="Ticker" value={filters.ticker} onChange={(e) => setFilters({...filters, ticker: e.target.value})} style={{ ...filterInputStyle, width: '100px' }} />
        <input placeholder="Company Name" value={filters.name} onChange={(e) => setFilters({...filters, name: e.target.value})} style={{ ...filterInputStyle, width: '200px' }} />
        <select value={filters.country} onChange={(e) => setFilters({...filters, country: e.target.value})} style={filterInputStyle}>
          <option value="ALL">All Countries</option>
          <option value="KR">KR</option>
          <option value="US">US</option>
        </select>
        <select value={filters.sector} onChange={(e) => setFilters({...filters, sector: e.target.value})} style={filterInputStyle}>
          <option value="ALL">All Sectors</option>
          {sectorOptions.map(opt => <option key={opt.id} value={opt.id}>{opt.ko}</option>)}
        </select>
        <select value={filters.rating} onChange={(e) => setFilters({...filters, rating: e.target.value})} style={filterInputStyle}>
          <option value="ALL">All Ratings</option>
          {['S', 'A+', 'A', 'B+', 'B', 'C', 'D'].map(r => <option key={r} value={r}>{r}</option>)}
        </select>
        <button onClick={resetFilters} style={{ padding: '10px 18px', backgroundColor: 'transparent', color: '#E669A2', border: '1px solid #E669A2', borderRadius: '6px', cursor: 'pointer', fontSize: '12px', fontWeight: 'bold' }}>Reset</button>
      </div>

      <table style={{ width: '100%', borderCollapse: 'separate', borderSpacing: '0 4px', marginTop: '10px', fontSize: '14px' }}>
        <thead>
          <tr>
            <th onClick={() => handleSort('ticker')} style={{ ...thStyle, textAlign: 'left' }}>
              Ticker <span style={{ color: sortConfig.key === 'ticker' ? '#D85604' : '#333' }}>{sortConfig.key === 'ticker' ? (sortConfig.direction === 'asc' ? '↑' : '↓') : '↕'}</span>
            </th>
            <th onClick={() => handleSort('name')} style={{ ...thStyle, textAlign: 'left' }}>
              Name <span style={{ color: sortConfig.key === 'name' ? '#D85604' : '#333' }}>{sortConfig.key === 'name' ? (sortConfig.direction === 'asc' ? '↑' : '↓') : '↕'}</span>
            </th>
            <th onClick={() => handleSort('country')} style={{ ...thStyle, textAlign: 'center' }}>
              Country <span style={{ color: sortConfig.key === 'country' ? '#D85604' : '#333' }}>{sortConfig.key === 'country' ? (sortConfig.direction === 'asc' ? '↑' : '↓') : '↕'}</span>
            </th>
            <th onClick={() => handleSort('sector')} style={{ ...thStyle, textAlign: 'center' }}>
              Sector <span style={{ color: sortConfig.key === 'sector' ? '#D85604' : '#333' }}>{sortConfig.key === 'sector' ? (sortConfig.direction === 'asc' ? '↑' : '↓') : '↕'}</span>
            </th>
            <th onClick={() => handleSort('price')} style={{ ...thStyle, textAlign: 'right' }}>
              Price <span style={{ color: sortConfig.key === 'price' ? '#D85604' : '#333' }}>{sortConfig.key === 'price' ? (sortConfig.direction === 'asc' ? '↑' : '↓') : '↕'}</span>
            </th>
            <th onClick={() => handleSort('change')} style={{ ...thStyle, textAlign: 'right' }}>
              Change <span style={{ color: sortConfig.key === 'change' ? '#D85604' : '#333' }}>{sortConfig.key === 'change' ? (sortConfig.direction === 'asc' ? '↑' : '↓') : '↕'}</span>
            </th>
            <th onClick={() => handleSort('grade')} style={{ ...thStyle, textAlign: 'center' }}>
              AI Rating <span style={{ color: sortConfig.key === 'grade' ? '#D85604' : '#333' }}>{sortConfig.key === 'grade' ? (sortConfig.direction === 'asc' ? '↑' : '↓') : '↕'}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {processedData.map((stock) => {
            // getGradeStyle 함수를 통해 해당 등급의 스타일과 텍스트 정보를 가져옵니다.
            const gradeInfo = getGradeStyle(stock.final_grade);
            
            return (
              <tr 
                key={stock.ticker} 
                style={{ transition: 'all 0.2s ease' }}
                onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#080808'}
                onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
              >
                <td style={{ ...tdStyle, verticalAlign: 'middle' }}>
                  <div 
                    onClick={() => window.open(`/stock/${stock.ticker}/summary`, '_blank')}
                    style={{ color: '#D85604', fontWeight: '900', cursor: 'pointer', transition: 'all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1)', display: 'inline-block', transformOrigin: 'left center', borderBottom: '2px solid transparent', paddingBottom: '2px' }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.color = '#E88D14';
                      e.currentTarget.style.transform = 'translateX(6px) scale(1.15)';
                      e.currentTarget.style.borderBottom = '2px solid #E88D14';
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.color = '#D85604';
                      e.currentTarget.style.transform = 'translateX(0) scale(1)';
                      e.currentTarget.style.borderBottom = '2px solid transparent';
                    }}
                  >
                    {stock.ticker}
                  </div>
                </td>
                <td style={{ ...tdStyle, color: '#ccc' }}>{stock.name || stock.company_name}</td>
                <td style={{ ...tdStyle, fontSize: '11px', color: '#555', textAlign: 'center' }}>{(stock.country || 'US').toUpperCase()}</td>
                <td style={{ ...tdStyle, color: '#555', fontSize: '11px', textAlign: 'center' }}>{stock.sector?.toUpperCase()}</td>
                <td style={{ ...tdStyle, textAlign: 'right', fontWeight: '600', fontFamily: 'monospace', fontSize: '15px' }}>
                  ${Number(stock.price || 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                </td>
                <td style={{ ...tdStyle, textAlign: 'right', fontWeight: '700', color: (stock.change > 0) ? '#AD1B02' : (stock.change < 0) ? '#0066FF' : '#555' }}>
                  {stock.change > 0 ? '▲' : stock.change < 0 ? '▼' : ''} {Math.abs(stock.change || 0).toFixed(2)}%
                </td>
                <td style={{ ...tdStyle, textAlign: 'center' }}>
                  <div style={{ display: 'inline-flex', flexDirection: 'column', alignItems: 'center' }}>
                    {/* AI 등급 뱃지 (S, A+ 등) */}
                    <span style={{ 
                      minWidth: '46px', padding: '3px 0', borderRadius: '4px', 
                      fontSize: '13px', fontWeight: '900', 
                      backgroundColor: gradeInfo.bg, color: gradeInfo.color, 
                      border: `1px solid ${gradeInfo.color}44`, textAlign: 'center', lineHeight: '1' 
                    }}>
                      {stock.final_grade?.toUpperCase() || '-'}
                    </span>
                    
                    {/* 투자 의견 (Strong Buy, Buy, Hold 등) */}
                    <span style={{ 
                      fontSize: '10px', color: gradeInfo.color, fontWeight: 'bold', 
                      marginTop: '4px', letterSpacing: '0.5px', whiteSpace: 'nowrap' 
                    }}>
                      {gradeInfo.title}
                    </span>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}