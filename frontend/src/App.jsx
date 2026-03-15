/**
 * App.jsx — 계층 구조 최적화 버전
 */
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Layout from './Layout';
import MainDashboard  from './pages/MainDashboard';
import StockDetail    from './pages/StockDetail';

import SummaryTab      from './components/SummaryTab';
import HistoricalTab   from './components/HistoricalTab';
import FinancialsTab   from './components/FinancialsTab';
import QuantRatingTab  from './components/QuantRatingTab';
import NlpSignalTab    from './components/NlpSignalTab';
import MarketSignalTab from './components/MarketSignalTab';

function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/main" element={<MainDashboard />} />
          <Route path="/main/:sectorId" element={<MainDashboard />} />

          {/* 종목 상세 부모 라우트 */}
          <Route path="/stock/:ticker" element={<StockDetail />}>
            {/* 1. 기본 진입 시 summary로 이동 */}
            <Route index element={<Navigate to="summary" replace />} />
            <Route path="summary" element={<SummaryTab />} />
            <Route path="historical" element={<HistoricalTab />} />
            <Route path="financials" element={<FinancialsTab />} />
            

            {/* 2. Multi-Layer 하위 그룹 */}
            <Route path="multi-layer">
              {/* /stock/:ticker/multi-layer 클릭 시 quant-rating으로 자동 이동 */}
              <Route index element={<Navigate to="quant-rating" replace />} />
              <Route path="quant-rating" element={<QuantRatingTab />} />
              <Route path="nlp-signal" element={<NlpSignalTab />} />
              <Route path="market-signal" element={<MarketSignalTab />} />
            </Route>
          </Route>

          <Route path="/" element={<Navigate to="/main" replace />} />
          <Route path="*" element={<Navigate to="/main" replace />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}

export default App;