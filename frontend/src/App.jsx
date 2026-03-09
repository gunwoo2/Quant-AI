/**
 * App.jsx — QUANT AI 루트 컴포넌트
 * 페이지 라우팅: MainDashboard ↔ StockDetail
 *
 * 현재 구현: React Router 없이 상태 기반 라우팅
 * Phase 2에서 react-router-dom으로 교체 권장
 */
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Layout from './Layout';
import MainDashboard from './pages/MainDashboard';
import StockDetail from './pages/StockDetail';

// 탭 컴포넌트들
import SummaryTab from './components/SummaryTab';
import HistoricalTab from './components/HistoricalTab';
import FinancialsTab from './components/FinancialsTab'; 
import QuantRatingTab from './components/QuantRatingTab'; // 파일명 확인 완료

// 임시 컴포넌트 (추후 AI Rating 작업 시 파일 분리 추천)
const RatingTab = () => <div style={{color: '#D85604', padding: '20px'}}>AI Rating: Coming Soon. Something amazing is on its way. Stay tuned!</div>;

function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          {/* 기본 경로 설정 */}
          <Route path="/main" element={<MainDashboard />} />
          <Route path="/main/:sectorId" element={<MainDashboard />} />

          {/* 🚀 주식 상세 페이지 및 중첩 라우트(Tabs) 설정 */}
          <Route path="/stock/:ticker" element={<StockDetail />}>
            {/* 상세페이지 접속 시 기본적으로 summary 탭을 보여줌 */}
            <Route index element={<Navigate to="summary" replace />} />
            
            <Route path="summary" element={<SummaryTab />} /> 
            <Route path="historical" element={<HistoricalTab />} />
            <Route path="financials" element={<FinancialsTab />} />
            <Route path="quant-rating" element={<QuantRatingTab />} />            
            <Route path="rating" element={<RatingTab />} />
          </Route>

          {/* 404 처리 (선택사항) */}
          <Route path="*" element={<Navigate to="/main" />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}

export default App;