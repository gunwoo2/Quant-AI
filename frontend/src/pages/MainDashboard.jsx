/**
 * MainDashboard.jsx
 * 메인 페이지 — 레이아웃 조립
 *
 * 구조:
 *   [Topbar]
 *   [MarketMarquee]
 *   [Sidebar] | [StockTable]
 */

import { useState } from "react";
import { useNavigate, useParams } from 'react-router-dom'; // 🚀 추가
import { C } from "../styles/tokens";
import Topbar        from "../components/layout/Topbar";
import MarketMarquee from "../components/layout/MarketMarquee";
import Sidebar       from "../components/layout/Sidebar";
import StockTable    from "../components/dashboard/StockTable";

export default function MainDashboard() {
  const navigate = useNavigate(); // 🚀 페이지 이동을 위한 함수
  const { sectorId } = useParams(); // 🚀 URL에서 /main/:sectorId 값을 가져옴 (예: TECHNOLOGY)
  
  const [activeTab, setActiveTab] = useState("SCREENER");

  // 티커(주식 이름) 클릭 시 실행되는 함수
  const handleTickerClick = (ticker) => {
    // 이제 상태값을 바꾸는 게 아니라, 실제 주소로 이동합니다.
    navigate(`/stock/${ticker}/summary`);
  };

  // 사이드바에서 섹터 클릭 시 실행되는 함수
  const handleSectorClick = (key) => {
    if (sectorId === key) {
      navigate("/main"); // 이미 선택된 섹터면 해제 (전체 보기)
    } else {
      navigate(`/main/${key}`); // 해당 섹터 주소로 이동
    }
    setActiveTab("SCREENER");
  };

  return (
    <div style={{
      display: "flex",
      flexDirection: "column",
      height: "100vh",
      background: C.bgDark,
      color: C.textPri,
      overflow: "hidden",
    }}>
      {/* ── 상단 네비게이션 */}
      <Topbar
        activeTab={activeTab}
        onTabChange={setActiveTab}
      />

      {/* ── 마켓 마퀴 (지수 Ticker) */}
      <MarketMarquee />

      {/* ── 본문 영역 */}
      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        {/* 사이드바 */}
        <Sidebar
          activeSector={sectorId} // 🚀 useState 대신 URL 파라미터(sectorId)를 직접 사용
          onSectorClick={handleSectorClick}
        />

        {/* 콘텐츠 영역 */}
        <main style={{ flex: 1, overflow: "hidden", display: "flex", flexDirection: "column" }}>
          {activeTab === "SCREENER" && (
            <StockTable
              filterSector={sectorId} // 🚀 URL 파라미터 전달
              onTickerClick={handleTickerClick} // 🚀 수정된 이동 함수 전달
            />
          )}

          {activeTab === "SIGNALS" && <PlaceholderPage label="SIGNALS — Phase 2 구현 예정" sub="뉴스 Sentiment · 어닝콜 Tone" />}
          {activeTab === "SECTORS" && <PlaceholderPage label="SECTORS — 섹터 비교 대시보드" sub="Phase 2 구현 예정" />}
          {activeTab === "MARKET"  && <PlaceholderPage label="MARKET — 거시지표 대시보드" sub="Phase 3 구현 예정" />}
        </main>
      </div>
    </div>
  );
}

function PlaceholderPage({ label, sub }) {
  return (
    <div style={{
      flex: 1, display: "flex", flexDirection: "column",
      alignItems: "center", justifyContent: "center", gap: 8,
    }}>
      <div style={{ fontSize: 13, color: C.textMuted, fontFamily: "'IBM Plex Mono', monospace" }}>
        {label}
      </div>
      <div style={{ fontSize: 11, color: C.textMuted, fontFamily: "'IBM Plex Mono', monospace" }}>
        {sub}
      </div>
    </div>
  );
}

//#################### 이전 코드 #######################################
// import { useState, useEffect } from 'react';
// import { useParams } from 'react-router-dom';
// import api from '../api';
// import MainTable from '../components/MainTable';

// export default function MainDashboard() {
//   const { sectorId } = useParams();
//   const [allStocks, setAllStocks] = useState([]);
//   const [loading, setLoading] = useState(true);

//   // 섹터별 설명 문구 매핑
//   const sectorDescriptions = {
//     financials: { ko: "금융", desc: "은행, 보험, 자산운용, 투자은행" },
//     discretionary: { ko: "자유/경기 소비재", desc: "자동차, 호텔, 레스토랑, 소매" },
//     realestate: { ko: "부동산", desc: "리츠, 부동산 관리 및 개발" },
//     industrials: { ko: "산업재", desc: "항공우주, 국방, 건설, 기계, 운송" },
//     energy: { ko: "에너지", desc: "석유, 가스, 소모성 연료" },
//     materials: { ko: "원자재", desc: "화학, 금속, 채광, 임업" },
//     utilities: { ko: "유틸리티", desc: "전력, 가스, 수도" },
//     healthcare: { ko: "헬스케어", desc: "제약, 바이오, 의료 장비" },
//     comm: { ko: "통신서비스", desc: "통신 서비스, 미디어, 엔터테인먼트" },
//     staples: { ko: "필수소비재", desc: "음식료, 가정용품, 개인용품" },
//     it: { ko: "정보통신기술", desc: "소프트웨어, 하드웨어, 반도체" }
//   };

//   // ✅ 데이터 요청을 이곳에서만 수행 (중복 제거 핵심)
//   useEffect(() => {
//     const fetchStocks = async () => {
//       try {
//         setLoading(true);
//         const res = await api.get('/api/stocks');
//         setAllStocks(res.data);
//       } catch (e) {
//         console.error("데이터 로드 실패", e);
//       } finally {
//         setLoading(false);
//       }
//     };
//     fetchStocks();
//   }, []);

//   const currentSector = sectorDescriptions[sectorId?.toLowerCase()];

//   return (
//     <div style={{ padding: '30px', backgroundColor: '#000', minHeight: '100vh' }}>
//       <h1 style={{ color: '#fff', fontSize: '24px', fontWeight: '800', marginBottom: '5px' }}>
//         {sectorId ? 'SECTOR INSIGHT' : 'MARKET OVERVIEW'}
//       </h1>
//       <div style={{ width: '40px', height: '3px', backgroundColor: '#D85604', marginBottom: '30px' }} />

//       {sectorId && currentSector && (
//         <div style={{ 
//           backgroundColor: '#111', 
//           borderLeft: '4px solid #D85604', 
//           padding: '25px', 
//           borderRadius: '4px',
//           marginBottom: '30px'
//         }}>
//           <div style={{ display: 'flex', alignItems: 'center', marginBottom: '10px' }}>
//             <span style={{ color: '#D85604', marginRight: '10px', fontSize: '18px' }}>●</span>
//             <h2 style={{ color: '#fff', margin: 0, fontSize: '18px' }}>
//               {currentSector.ko} <span style={{ color: '#555', fontSize: '14px', marginLeft: '8px' }}>{sectorId.toUpperCase()}</span>
//             </h2>
//           </div>
//           <p style={{ color: '#888', margin: 0, fontSize: '14px', letterSpacing: '0.5px' }}>
//             {currentSector.desc}
//           </p>
//         </div>
//       )}

//       {/* ✅ 로딩 상태와 데이터를 props로 전달 */}
//       <MainTable stocks={allStocks} loading={loading} />
//     </div>
//   );
// }