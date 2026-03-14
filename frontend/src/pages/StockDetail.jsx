/**
 * StockDetail.jsx — v5 (Nested Tab 구조 적용)
 */
import React, { useState, useEffect } from 'react';
import { useParams, useLocation, useNavigate, Outlet } from 'react-router-dom';
import api from '../api';
import { AddTickerModal } from '../components/dashboard/Modals';
import { C, FONT } from "../styles/tokens";

// ── NVDA Mock 데이터
const NVDA_MOCK = {
  header: {
    ticker: "NVDA",
    name: "NVIDIA Corporation",
    description: "NVIDIA Corporation는 GPU, 시스템온칩(SoC) 유닛 등을 설계·제조하는 반도체 기업입니다. 데이터센터, 게이밍, 전문 시각화, 자동차 시장에 플랫폼 솔루션을 공급하며, CUDA 병렬 컴퓨팅 플랫폼을 통해 AI 및 딥러닝 인프라의 핵심 공급자로 자리잡고 있습니다.",
  },
  realtime: {
    price: 875.20,
    change: 3.36,
    amount_change: 28.41,
    changesPercentage: "3.36",
    grade: "S",
    score: 88.4,
    l1: 91, l2: 82, l3: 88,
  },
};

export default function StockDetail() {
  const { ticker } = useParams();
  const location = useLocation();
  const navigate = useNavigate();

  const [stockData, setStockData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [isMock, setIsMock] = useState(false);
  const [isDescOpen, setIsDescOpen] = useState(false);
  const [showAddModal, setShowAddModal] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api.get(`/api/stock/detail/${ticker}`)
      .then(res => { if (!cancelled) { setStockData(res.data); setIsMock(false); } })
      .catch(() => {
        if (!cancelled) {
          const mockData = ticker === "NVDA" ? NVDA_MOCK : {
            header: { ticker, name: `${ticker} (Mock)`, description: "백엔드 연결 전 UI 미리보기용 데이터입니다." },
            realtime: { price: 100.00, change: 1.5, amount_change: 1.50, changesPercentage: "1.50", grade: "A", score: 65.0, l1: 68, l2: 60, l3: 62 },
          };
          setStockData(mockData);
          setIsMock(true);
        }
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [ticker]);

  // ── 경로 파악
  const isMultiLayerPath = location.pathname.includes('multi-layer');

  // 1. 메인 탭 설정
  const mainTabs = [
    { id: 'summary', label: 'Summary' },
    { id: 'historical', label: 'Historical' },
    { id: 'financials', label: 'Financials' },
    { id: 'multi-layer', label: 'Multi-Layer Rating' },
  ];

  // 2. Multi-Layer 내부 서브 탭 설정
  const subTabs = [
    { id: 'quant-rating', label: 'Quant Rating', badge: 'L1', color: C.primary },
    { id: 'nlp-signal', label: 'NLP Signal', badge: 'L2', color: '#7c3aed' },
    { id: 'market-signal', label: 'Market Signal', badge: 'L3', color: '#0891b2' },
  ];

  const GlobalBar = () => (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
      <button onClick={() => navigate('/main')} style={{ background: 'none', border: 'none', color: C.textMuted, cursor: 'pointer', fontSize: 13, padding: 0, fontFamily: FONT.sans }}>
        ← 메인으로
      </button>
      <button onClick={() => setShowAddModal(true)}
        style={{ 
          backgroundColor: C.primary, color: '#fff', border: 'none', 
          padding: '8px 18px', borderRadius: 4, fontWeight: 800, 
          cursor: 'pointer', fontSize: 12, fontFamily: FONT.sans, letterSpacing: 0.5 
        }}
      >
        + ADD TICKER
      </button>
    </div>
  );

  if (loading) return (
    <div style={{ backgroundColor: C.bgDeep, minHeight: '100vh', padding: '30px 50px' }}>
      <GlobalBar />
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 300 }}>
        <div style={{ color: C.primary, fontSize: 18, fontWeight: 'bold', letterSpacing: 2, fontFamily: FONT.sans }}>LOADING...</div>
      </div>
    </div>
  );

  const { header, realtime } = stockData;

  return (
    <div style={{ backgroundColor: C.bgDeep, color: C.textPri, minHeight: '100vh', padding: '30px 50px', fontFamily: FONT.sans }}>
      <GlobalBar />

      {isMock && (
        <div style={{ background: `${C.golden}15`, border: `1px solid ${C.golden}40`, borderLeft: `3px solid ${C.golden}`, borderRadius: 6, padding: '8px 16px', marginBottom: 20, fontSize: 11, color: C.golden }}>
          ⚠ MOCK DATA — 백엔드 미연결. UI 미리보기 전용.
        </div>
      )}

      {/* 1. 헤더 섹션 */}
      <div style={{ marginBottom: 36, borderLeft: `4px solid ${C.primary}`, paddingLeft: 20 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 14, flexWrap: 'wrap' }}>
          <h1 style={{ fontSize: 52, color: C.primary, margin: 0, fontWeight: 900, letterSpacing: '-1px' }}>{header.ticker}</h1>
          <span style={{ fontSize: 20, color: C.textMuted, fontWeight: 600 }}>{header.name}</span>
        </div>
        {realtime && (
          <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 14 }}>
            <span style={{ fontSize: 30, fontWeight: 600 }}>${realtime.price?.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
            <div style={{ 
              color: (realtime.change >= 0) ? C.cyan : C.scarlet, 
              backgroundColor: (realtime.change >= 0) ? `${C.cyan}15` : `${C.scarlet}15`, 
              padding: '5px 20px', 
              borderRadius: 4, 
              fontSize: 17 
            }}>
              {realtime.change > 0 ? '▲' : '▼'} 
              {Math.abs(realtime.amount_change || 0).toFixed(2)} 
              ({Number(realtime.changesPercentage || 0).toFixed(2)}%)
            </div>
          </div>
        )}
      </div>

      {/* 2. 회사 프로필 */}
      <div style={{ backgroundColor: C.surface, padding: 26, borderRadius: 12, border: `1px solid ${C.border}`, marginBottom: 36 }}>
        <h4 style={{ margin: '0 0 10px 0', color: C.golden, fontSize: 10, textTransform: 'uppercase', letterSpacing: 2 }}>Company Profile</h4>
        <p style={{ margin: 0, fontSize: 14, lineHeight: 1.8, color: C.textGray, WebkitLineClamp: isDescOpen ? 'unset' : 2, display: '-webkit-box', WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
          {header.description}
        </p>
        <button onClick={() => setIsDescOpen(!isDescOpen)} style={{ background: 'none', border: 'none', color: C.pink, padding: '10px 0 0 0', cursor: 'pointer', fontSize: 12, fontWeight: 'bold' }}>
          {isDescOpen ? 'Collapse ▲' : 'Read More ▼'}
        </button>
      </div>

      {/* 3. 메인 탭 바 */}
      <div style={{ display: 'flex', borderBottom: `1px solid ${C.border}`, marginBottom: isMultiLayerPath ? 0 : 28 }}>
        {mainTabs.map(tab => {
          // 활성화 조건: 현재 경로가 탭 ID를 포함하거나, multi-layer 그룹 안에 있을 때
          const isActive = (tab.id === 'multi-layer' && isMultiLayerPath) || 
                           (!isMultiLayerPath && location.pathname.endsWith(tab.id));

          return (
            <div key={tab.id}
              onClick={() => {
                // ★ 상대 경로 사용: 현재 /stock/:ticker/ 에 있으므로 자식 경로만 입력
                if (tab.id === 'multi-layer') navigate("multi-layer/quant-rating");
                else navigate(tab.id);
              }}
              style={{
                padding: '12px 24px', cursor: 'pointer', fontSize: 12, fontWeight: 800,
                color: isActive ? C.primary : C.textMuted,
                borderBottom: isActive ? `3px solid ${C.primary}` : '3px solid transparent',
              }}
            >
              {tab.label}
            </div>
          );
        })}
      </div>

      {/* ── 3-1. Multi-Layer 서브 탭 ── */}
      {isMultiLayerPath && (
        <div style={{ display: 'flex', gap: '10px', padding: '18px 0', marginBottom: 28, borderBottom: `1px solid ${C.surface}` }}>
          {subTabs.map(sub => {
            const isSubActive = location.pathname.includes(sub.id);
            return (
              <div key={sub.id}
                onClick={() => navigate(`multi-layer/${sub.id}`)} // ★ 상대 경로
                style={{
                  padding: '8px 16px', borderRadius: '8px', cursor: 'pointer', fontSize: 12, fontWeight: 700,
                  backgroundColor: isSubActive ? `${sub.color}15` : 'transparent',
                  color: isSubActive ? sub.color : C.textMuted,
                  border: `1px solid ${isSubActive ? `${sub.color}40` : C.border}`,
                  display: 'flex', alignItems: 'center', gap: '8px'
                }}
              >
                <span style={{ fontSize: 9, padding: '2px 4px', borderRadius: 4, background: sub.color, color: '#fff' }}>{sub.badge}</span>
                {sub.label}
              </div>
            );
          })}
        </div>
      )}

      {/* ── 4. 컨텐츠 출력 (이곳에 QuantRatingTab 등이 렌더링됨) ── */}
      <div style={{ marginTop: 10 }}>
        <Outlet context={{ ticker, header, realtime, quantData: stockData.quant }} />
      </div>

      {showAddModal && <AddTickerModal onClose={() => setShowAddModal(false)} onAdd={() => setShowAddModal(false)} />}
    </div>
  );
}