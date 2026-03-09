import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import api from '../api';
import MainTable from '../components/MainTable';

export default function MainDashboard() {
  const { sectorId } = useParams();
  const [allStocks, setAllStocks] = useState([]);
  const [loading, setLoading] = useState(true);

  // 섹터별 설명 문구 매핑
  const sectorDescriptions = {
    financials: { ko: "금융", desc: "은행, 보험, 자산운용, 투자은행" },
    discretionary: { ko: "자유/경기 소비재", desc: "자동차, 호텔, 레스토랑, 소매" },
    realestate: { ko: "부동산", desc: "리츠, 부동산 관리 및 개발" },
    industrials: { ko: "산업재", desc: "항공우주, 국방, 건설, 기계, 운송" },
    energy: { ko: "에너지", desc: "석유, 가스, 소모성 연료" },
    materials: { ko: "원자재", desc: "화학, 금속, 채광, 임업" },
    utilities: { ko: "유틸리티", desc: "전력, 가스, 수도" },
    healthcare: { ko: "헬스케어", desc: "제약, 바이오, 의료 장비" },
    comm: { ko: "통신서비스", desc: "통신 서비스, 미디어, 엔터테인먼트" },
    staples: { ko: "필수소비재", desc: "음식료, 가정용품, 개인용품" },
    it: { ko: "정보통신기술", desc: "소프트웨어, 하드웨어, 반도체" }
  };

  // ✅ 데이터 요청을 이곳에서만 수행 (중복 제거 핵심)
  useEffect(() => {
    const fetchStocks = async () => {
      try {
        setLoading(true);
        const res = await api.get('/api/stocks');
        setAllStocks(res.data);
      } catch (e) {
        console.error("데이터 로드 실패", e);
      } finally {
        setLoading(false);
      }
    };
    fetchStocks();
  }, []);

  const currentSector = sectorDescriptions[sectorId?.toLowerCase()];

  return (
    <div style={{ padding: '30px', backgroundColor: '#000', minHeight: '100vh' }}>
      <h1 style={{ color: '#fff', fontSize: '24px', fontWeight: '800', marginBottom: '5px' }}>
        {sectorId ? 'SECTOR INSIGHT' : 'MARKET OVERVIEW'}
      </h1>
      <div style={{ width: '40px', height: '3px', backgroundColor: '#D85604', marginBottom: '30px' }} />

      {sectorId && currentSector && (
        <div style={{ 
          backgroundColor: '#111', 
          borderLeft: '4px solid #D85604', 
          padding: '25px', 
          borderRadius: '4px',
          marginBottom: '30px'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', marginBottom: '10px' }}>
            <span style={{ color: '#D85604', marginRight: '10px', fontSize: '18px' }}>●</span>
            <h2 style={{ color: '#fff', margin: 0, fontSize: '18px' }}>
              {currentSector.ko} <span style={{ color: '#555', fontSize: '14px', marginLeft: '8px' }}>{sectorId.toUpperCase()}</span>
            </h2>
          </div>
          <p style={{ color: '#888', margin: 0, fontSize: '14px', letterSpacing: '0.5px' }}>
            {currentSector.desc}
          </p>
        </div>
      )}

      {/* ✅ 로딩 상태와 데이터를 props로 전달 */}
      <MainTable stocks={allStocks} loading={loading} />
    </div>
  );
}