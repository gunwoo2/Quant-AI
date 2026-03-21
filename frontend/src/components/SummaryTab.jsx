/**
 * SummaryTab.jsx — v3 (백엔드 API 연결)
 *
 * 데이터 소스: StockDetail Outlet context
 *   { ticker, header, realtime, quantData }
 *
 * realtime 필드 (GET /api/stock/detail/:ticker → .realtime):
 *   price, change, amount_change, changesPercentage
 *   grade, score, l1, l2, l3
 *   eps, per, forwardPer, pbr
 *   roe, roa, roic
 *   strong_buy_signal, strong_sell_signal
 *
 * ※ 뉴스/공시(/api/news, /api/filings)는 백엔드 미구현 → 섹션 숨김
 * ※ rating-history도 미구현 → mock fallback 유지
 */
import React, { useState, useEffect } from 'react';
import { useOutletContext } from 'react-router-dom';
import TradingViewWidget from './TradingViewWidget';
import MetricCard from './MetricCard';
import api from '../api';
import { C, FONT, gradeColor, chgColor, signalColor } from '../styles/tokens';

// grade → 시그널 메타
const GRADE_SIGNAL = {
  'S':  { label: 'STRONG BUY',  color: C.cyan },
  'A+': { label: 'BUY',         color: C.cyan },
  'A':  { label: 'OUTPERFORM',  color: C.primary },
  'B+': { label: 'HOLD',        color: C.golden },
  'B':  { label: 'UNDERPERFORM',color: C.golden },
  'C':  { label: 'SELL',        color: C.down },
  'D':  { label: 'STRONG SELL', color: C.gradeD },
};

function fmt(v, digits = 2) {
  return v != null ? Number(v).toFixed(digits) : null;
}

export default function SummaryTab() {
  const { ticker, realtime } = useOutletContext();
  const [ratingHistory, setRatingHistory] = useState(null);

  // AI Rating History — 백엔드 미구현이므로 mock fallback
  useEffect(() => {
    if (!ticker) return;
    api.get(`/api/stock/rating-history/${ticker}`)
      .then(res => setRatingHistory(res.data || []))
      .catch(() => setRatingHistory([
        { date: '2026-02-28', grade: 'S',  desc: 'Alpha Peak',      score: 88.4 },
        { date: '2026-02-14', grade: 'A+', desc: 'High Conviction',  score: 80.1 },
        { date: '2026-01-31', grade: 'A',  desc: 'Growth Stable',    score: 71.3 },
        { date: '2025-12-28', grade: 'A',  desc: 'Growth Stable',    score: 68.9 },
      ]));
  }, [ticker]);

  const signal = GRADE_SIGNAL[realtime?.grade] ?? { label: 'N/A', color: C.textMuted };

  // ── Valuation — 백엔드 realtime 필드 직접 연결
  const valuationStats = [
    {
      label: 'EPS (TTM)',
      value: fmt(realtime?.eps) ? `$${fmt(realtime.eps)}` : 'N/A',
      tooltip: { title: 'EPS', formula: '당기순이익 ÷ 총발행주식', meaning: '1주가 벌어들인 돈', standard: '우상향이 좋습니다.' },
    },
    {
      label: 'PER',
      value: fmt(realtime?.per) ? `${fmt(realtime.per)}x` : 'N/A',
      tooltip: { title: 'PER', formula: '주가 ÷ EPS', meaning: '이익 대비 주가', standard: '15~20배가 적정선.' },
    },
    {
      label: 'Forward PER',
      value: fmt(realtime?.forwardPer) ? `${fmt(realtime.forwardPer)}x` : 'N/A',
      tooltip: { title: 'Forward PER', formula: '주가 ÷ 예상 EPS', meaning: '미래 가치 대비 주가', standard: '현재 PER보다 낮으면 성장 신호.' },
    },
    {
      label: 'PBR',
      value: fmt(realtime?.pbr) ? `${fmt(realtime.pbr)}` : 'N/A',
      tooltip: { title: 'PBR', formula: '주가 ÷ BPS', meaning: '자산 대비 주가', standard: '1배 미만은 저평가.' },
    },
  ];

  // ── Profitability — roe/roa는 realtime에 있음, roi는 없음(null 처리)
  const profitabilityStats = [
    {
      label: 'ROE',
      value: fmt(realtime?.roe) ? `${fmt(realtime.roe)}%` : 'N/A',
      tooltip: { title: 'ROE', formula: '순이익 ÷ 자기자본', meaning: '자본 효율성', standard: '15% 이상 우량.' },
    },
    {
      label: 'ROA',
      value: fmt(realtime?.roa) ? `${fmt(realtime.roa)}%` : 'N/A',
      tooltip: { title: 'ROA', formula: '순이익 ÷ 총자산', meaning: '자산 운용 수익률', standard: '5~10% 양호.' },
    },
    {
      label: 'ROIC',
      // realtime.roic는 소수 비율(0.5213 = 52.13%) → %로 변환
      value: realtime?.roic != null ? `${(Number(realtime.roic) * 100).toFixed(2)}%` : 'N/A',
      tooltip: { title: 'ROIC', formula: '영업이익 ÷ 투하자본', meaning: '영업 효율성', standard: '15% 이상 독점적 해자.' },
    },
    {
      label: 'Score (L1)',
      value: realtime?.l1 != null ? `${Number(realtime.l1).toFixed(1)}` : 'N/A',
      tooltip: { title: 'Quant Score L1', formula: 'MOAT+VALUE+MOMENTUM+STABILITY', meaning: '퀀트 종합 점수', standard: '70 이상 우수.' },
    },
  ];

  const gridStyle = {
    display: 'grid',
    gridTemplateColumns: 'repeat(4, 1fr)',
    backgroundColor: C.bgDeeper,
    border: '1px solid #1a1a1a',
    borderRadius: '12px',
    overflow: 'hidden',
    marginBottom: '30px',
  };

  const SectionHeader = ({ title, subTitle, question, description, color }) => (
    <div style={{ marginBottom: '15px', borderTop: `2px solid ${color}`, paddingTop: '16px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px', flexWrap: 'wrap' }}>
        <h3 style={{ color: '#fff', fontSize: '15px', margin: 0, fontWeight: '800' }}>{title}</h3>
        <span style={{ color: C.textMuted, fontSize: '12px' }}>({subTitle})</span>
        <span style={{ background: `${color}15`, color, padding: '2px 10px', borderRadius: '4px', fontSize: '11px', fontWeight: '900', border: `1px solid ${color}33` }}>{question}</span>
      </div>
      <p style={{ color: '#777', fontSize: '12px', margin: 0, lineHeight: '1.5' }}>{description}</p>
    </div>
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '25px', padding: '20px' }}>

      {/* ── 0. 시그널 배너 */}
      <SignalBanner signal={signal} realtime={realtime} />

      {/* ── 1. TradingView 차트 */}
      <div style={{ height: '450px', backgroundColor: '#111', borderRadius: '12px', overflow: 'hidden', border: '1px solid #222' }}>
        <TradingViewWidget symbol={ticker || 'AAPL'} />
      </div>

      {/* ── 2. 가치평가 + 수익성 지표 */}
      <div style={{ padding: '28px', backgroundColor: '#0f0f0f', borderRadius: '20px', border: '1px solid #1a1a1a' }}>
        <SectionHeader
          title="Valuation" subTitle="가치 평가"
          question="Value: 주가가 저렴한가?"
          description="현재 주가가 기업의 내재가치나 이익 대비 어느 수준인지 측정합니다."
          color="#D85604"
        />
        <div style={gridStyle}>
          {valuationStats.map((s, i) => <MetricCard key={i} {...s} isLastInRow={i === 3} accentColor="#D85604" />)}
        </div>
        <SectionHeader
          title="Profitability" subTitle="수익성 분석"
          question="Quality: 돈을 얼마나 잘 버는가?"
          description="자본과 자산을 얼마나 효율적으로 사용하여 이익을 창출하는지 측정합니다."
          color="#F3BE26"
        />
        <div style={gridStyle}>
          {profitabilityStats.map((s, i) => <MetricCard key={i} {...s} isLastInRow={i === 3} accentColor="#F3BE26" />)}
        </div>
      </div>

      {/* ── 3. AI Rating History (우측) + 시그널 요약 (좌측) */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: '24px', alignItems: 'start' }}>

        {/* 좌측: 주요 신호 요약 */}
        <div style={{ padding: '24px', backgroundColor: C.bgDeeper, border: '1px solid #1a1a1a', borderRadius: '16px' }}>
          <h3 style={{ color: '#fff', fontSize: '14px', fontWeight: '800', marginBottom: '18px', display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ width: 3, height: 14, backgroundColor: '#D85604', display: 'inline-block' }} />
            Signal Summary
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {[
              { label: 'Grade',              value: realtime?.grade ?? '—',                           color: signal.color },
              { label: 'Quant Score',        value: realtime?.score != null ? Number(realtime.score).toFixed(1) : '—', color: C.textPri },
              { label: 'L1 (Quant)',         value: realtime?.l1 ?? '—',                              color: C.primary },
              { label: 'L2 (NLP/AI)',        value: realtime?.l2 ?? '—',                              color: C.pink },
              { label: 'L3 (Market)',        value: realtime?.l3 ?? '—',                              color: C.cyan },
              { label: 'Strong Buy Signal',  value: realtime?.strong_buy_signal  ? '✅ YES' : '—',   color: C.cyan },
              { label: 'Strong Sell Signal', value: realtime?.strong_sell_signal ? '🔴 YES' : '—',   color: C.down },
            ].map(row => (
              <div key={row.label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 0', borderBottom: '1px solid #1a1a1a' }}>
                <span style={{ fontSize: 12, color: '#666' }}>{row.label}</span>
                <span style={{ fontSize: 14, fontWeight: 800, color: row.color, fontFamily: 'sans-serif' }}>{row.value}</span>
              </div>
            ))}
          </div>
        </div>

        {/* 우측: AI Rating History */}
        <div style={{ padding: '24px', backgroundColor: C.bgDeeper, border: '1px solid #1a1a1a', borderRadius: '16px' }}>
          <h3 style={{ color: '#fff', fontSize: '14px', fontWeight: '800', marginBottom: '18px', display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ width: 3, height: 14, backgroundColor: '#D85604', display: 'inline-block' }} />
            AI Rating History
          </h3>
          {!ratingHistory ? (
            <div style={{ color: C.textMuted, fontSize: 12, textAlign: 'center', padding: 20 }}>Loading...</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              {ratingHistory.map((item, idx) => {
                const gc = GRADE_SIGNAL[item.grade]?.color ?? '#888';
                return (
                  <div key={idx} style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    padding: '12px 0',
                    borderBottom: idx < ratingHistory.length - 1 ? '1px solid #1a1a1a' : 'none',
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <span style={{ fontFamily: 'sans-serif', fontWeight: 900, fontSize: 20, color: gc, width: 32 }}>{item.grade}</span>
                      <div>
                        <div style={{ color: gc, fontWeight: 700, fontSize: 11 }}>{item.desc || ''}</div>
                        {item.score != null && (
                          <div style={{ color: C.textMuted, fontSize: 10, fontFamily: 'sans-serif' }}>
                            Score {typeof item.score === 'number' ? item.score.toFixed(1) : item.score}
                          </div>
                        )}
                      </div>
                    </div>
                    <div style={{ color: C.textMuted, fontSize: 11, fontFamily: 'sans-serif' }}>{item.date}</div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

    </div>
  );
}

/* ── SignalBanner */
function SignalBanner({ signal, realtime }) {
  if (!realtime) return null;
  const layers = [
    { key: 'L1', label: 'Quant',  score: realtime.l1, color: C.primary },
    { key: 'L2', label: 'NLP/AI', score: realtime.l2, color: C.pink },
    { key: 'L3', label: 'Market', score: realtime.l3, color: C.cyan },
  ];
  return (
    <div style={{
      background: `${signal.color}0d`,
      border: `1px solid ${signal.color}30`,
      borderLeft: `4px solid ${signal.color}`,
      borderRadius: 12, padding: '18px 22px',
      display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 16,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
        <div>
          <div style={{ fontSize: 10, color: C.textMuted, fontFamily: 'sans-serif', letterSpacing: 1.5, marginBottom: 4 }}>QUANT AI · FINAL SIGNAL</div>
          <div style={{ fontSize: 26, fontWeight: 900, color: signal.color, fontFamily: 'sans-serif', letterSpacing: 1 }}>{signal.label}</div>
        </div>
        {realtime.score != null && (
          <div style={{ textAlign: 'center', padding: '8px 14px', background: `${signal.color}15`, borderRadius: 8, border: `1px solid ${signal.color}30` }}>
            <div style={{ fontSize: 22, fontWeight: 900, color: signal.color, fontFamily: 'sans-serif' }}>
              {Number(realtime.score).toFixed(1)}
            </div>
            <div style={{ fontSize: 9, color: C.textMuted, letterSpacing: 1 }}>SCORE</div>
          </div>
        )}
      </div>
      <div style={{ display: 'flex', gap: 10 }}>
        {layers.map(l => (
          <div key={l.key} style={{
            padding: '8px 14px', borderRadius: 6,
            background: `${l.color}10`, border: `1px solid ${l.color}30`,
            textAlign: 'center', minWidth: 76,
          }}>
            <div style={{ fontSize: 9, color: C.textMuted, fontFamily: 'sans-serif', letterSpacing: 1, marginBottom: 4 }}>{l.key}</div>
            <div style={{ fontSize: 18, fontWeight: 800, color: l.score != null ? l.color : '#333', fontFamily: 'sans-serif' }}>
              {l.score ?? '—'}
            </div>
            <div style={{ fontSize: 9, color: '#444', marginTop: 3 }}>{l.label}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

// /**
//  * SummaryTab.jsx
//  * 개선 사항: 반응형 UI 최적화, 시그널 배너 레이아웃 수정, 가독성 강화
//  */
// import React, { useState, useEffect } from 'react';
// import { useOutletContext } from 'react-router-dom';
// import TradingViewWidget from './TradingViewWidget';
// import MetricCard from './MetricCard';
// import api from '../api';

// // ── 신호 통합 로직 (L1+L2+L3 종합)
// function computeSignal(realtime) {
//   if (!realtime) return { label: 'N/A', color: C.textMuted, score: null, detail: [] };
//   const grade = realtime.grade || realtime.final_grade;
//   const map = {
//     'S':  { label: 'STRONG BUY',  color: C.cyan, score: 95 },
//     'A+': { label: 'BUY',          color: C.cyan, score: 82 },
//     'A':  { label: 'OUTPERFORM',   color: C.primary, score: 70 },
//     'B+': { label: 'HOLD',         color: C.golden, score: 58 },
//     'B':  { label: 'UNDERPERFORM', color: C.golden, score: 45 },
//     'C':  { label: 'SELL',         color: C.down, score: 30 },
//     'D':  { label: 'STRONG SELL',  color: C.gradeD, score: 15 },
//   };
//   return map[grade] || { label: 'HOLD', color: C.golden, score: 55 };
// }

// export default function SummaryTab() {
//   const { ticker, realtime } = useOutletContext();
//   const [activeNewsTab, setActiveNewsTab] = useState('news');
//   const [displayList,   setDisplayList]   = useState([]);
//   const [newsLoading,   setNewsLoading]   = useState(true);
//   const [ratingHistory, setRatingHistory] = useState([]);

//   const signal = computeSignal(realtime);

//   // 뉴스 / 공시 fetch
//   useEffect(() => {
//     if (!ticker) return;
//     setNewsLoading(true);
//     const endpoint = activeNewsTab === 'news' ? `/api/news/${ticker}` : `/api/filings/${ticker}`;
//     fetch(endpoint)
//       .then(r => r.ok ? r.json() : [])
//       .then(d => setDisplayList(d))
//       .catch(() => setDisplayList([]))
//       .finally(() => setNewsLoading(false));
//   }, [ticker, activeNewsTab]);

//   // AI Rating History fetch
//   useEffect(() => {
//     if (!ticker) return;
//     api.get(`/api/stock/rating-history/${ticker}`)
//       .then(res => setRatingHistory(res.data || []))
//       .catch(() => setRatingHistory([
//         { date: '2026-02-28', grade: 'S',  color: C.cyan, desc: 'Alpha Peak',     score: 88.4 },
//         { date: '2026-02-14', grade: 'A+', color: C.cyan, desc: 'High Conviction', score: 80.1 },
//         { date: '2026-01-31', grade: 'A',  color: C.primary, desc: 'Growth Stable',    score: 71.3 },
//         { date: '2025-12-28', grade: 'A',  color: C.primary, desc: 'Growth Stable',    score: 68.9 },
//       ]));
//   }, [ticker]);

//   const valuationStats = [
//     { label: 'EPS (TTM)',     value: realtime?.eps       ? `$${Number(realtime.eps).toFixed(2)}`       : 'N/A', tooltip: { title: 'EPS', formula: '당기순이익 ÷ 총발행주식', meaning: '1주가 벌어들인 돈', standard: '우상향이 좋습니다.' } },
//     { label: 'PER (실시간)',    value: realtime?.per       ? `${Number(realtime.per).toFixed(2)}x`       : 'N/A', tooltip: { title: 'PER', formula: '주가 ÷ EPS', meaning: '이익 대비 주가', standard: '15~20배가 적정선.' } },
//     { label: 'Forward PER',    value: realtime?.forwardPer? `${Number(realtime.forwardPer).toFixed(2)}x`: 'N/A', tooltip: { title: 'Forward PER', formula: '주가 ÷ 예상 EPS', meaning: '미래 가치 대비 주가', standard: '현재 PER보다 낮으면 성장 신호.' } },
//     { label: 'PBR',            value: realtime?.pbr       ? `${Number(realtime.pbr).toFixed(2)}`        : 'N/A', tooltip: { title: 'PBR', formula: '주가 ÷ BPS', meaning: '자산 대비 주가', standard: '1배 미만은 저평가.' } },
//   ];

//   const profitabilityStats = [
//     { label: 'ROE', value: realtime?.roe  ? `${Number(realtime.roe).toFixed(2)}%`  : 'N/A', tooltip: { title: 'ROE', formula: '순이익 ÷ 자기자본', meaning: '자본 효율성', standard: '15% 이상 우량.' } },
//     { label: 'ROA', value: realtime?.roa  ? `${Number(realtime.roa).toFixed(2)}%`  : 'N/A', tooltip: { title: 'ROA', formula: '순이익 ÷ 총자산', meaning: '자산 운용 수익률', standard: '5~10% 양호.' } },
//     { label: 'ROI', value: realtime?.roi  ? `${Number(realtime.roi).toFixed(2)}%`  : 'N/A', tooltip: { title: 'ROI', formula: '순이익 ÷ 투자자본', meaning: '실질 투자 수익', standard: '10% 이상 합격.' } },
//     { label: 'ROIC', value: realtime?.roic ? `${Number(realtime.roic).toFixed(2)}%` : 'N/A', tooltip: { title: 'ROIC', formula: '영업이익 ÷ 투하자본', meaning: '영업 효율성', standard: '15% 이상 독점적 해자.' } },
//   ];

//   const SectionHeader = ({ title, subTitle, question, description, color }) => (
//     <div style={{ marginBottom: '15px', padding: '0 4px', borderTop: `2px solid ${color}`, paddingTop: '16px' }}>
//       <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '8px', marginBottom: '6px' }}>
//         <h3 style={{ color: '#fff', fontSize: '15px', margin: 0, fontWeight: '800' }}>{title}</h3>
//         <span style={{ color: C.textMuted, fontSize: '12px', fontWeight: '600' }}>({subTitle})</span>
//         <span style={{ backgroundColor: `${color}15`, color, padding: '2px 10px', borderRadius: '4px', fontSize: '11px', fontWeight: '900', border: `1px solid ${color}33` }}>{question}</span>
//       </div>
//       <p style={{ color: '#777', fontSize: '12px', margin: 0, lineHeight: '1.5' }}>{description}</p>
//     </div>
//   );

//   const gridContainerStyle = { 
//     display: 'grid', 
//     gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', 
//     backgroundColor: C.bgDeeper, 
//     border: '1px solid #1a1a1a', 
//     borderRadius: '12px', 
//     overflow: 'hidden', 
//     marginBottom: '30px' 
//   };
  
//   const subTabStyle = isActive => ({ padding: '10px 20px', cursor: 'pointer', fontSize: '14px', fontWeight: '700', color: isActive ? '#D85604' : '#666', borderBottom: isActive ? '2px solid #D85604' : '2px solid transparent', transition: '0.3s' });

//   return (
//     <div style={{ display: 'flex', flexDirection: 'column', gap: '25px', padding: 'clamp(10px, 3vw, 20px)', maxWidth: '1600px', margin: '0 auto' }}>

//       {/* ── 1. TradingView 차트 (최상단) ── */}
//       <div style={{ height: 'clamp(300px, 50vh, 450px)', backgroundColor: '#111', borderRadius: '12px', overflow: 'hidden', border: '1px solid #222' }}>
//         <TradingViewWidget symbol={ticker || 'AAPL'} />
//       </div>

//       {/* ── 2. 최종 시그널 배너 | AI Rating History (병렬 배치) ── */}
//       <div style={{ 
//         display: 'grid', 
//         gridTemplateColumns: 'repeat(auto-fit, minmax(350px, 1fr))', 
//         gap: '20px' 
//       }}>
//         <SignalBanner signal={signal} ticker={ticker} realtime={realtime} />
        
//         {/* AI Rating History 카드 */}
//         <div style={{ padding: '25px', backgroundColor: C.bgDeeper, border: '1px solid #222', borderRadius: '24px', display: 'flex', flexDirection: 'column' }}>
//           <h3 style={{ color: '#fff', fontSize: '16px', marginBottom: '20px', display: 'flex', alignItems: 'center', gap: '10px', fontWeight: '800' }}>
//             <span style={{ width: '3px', height: '15px', backgroundColor: '#D85604', display: 'inline-block' }} />
//             AI Rating History
//           </h3>
//           <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
//             {ratingHistory.map((item, idx) => {
//               const gColor = {
//                 'S': '#00F5FF', 'A+': '#00F5FF', 'A': '#D85604',
//                 'B+': '#E88D14', 'B': '#E88D14', 'C': C.down, 'D': C.gradeD,
//               }[item.grade] || '#888';
//               return (
//                 <div key={idx} style={{
//                   display: 'flex', justifyContent: 'space-between', alignItems: 'center',
//                   padding: '12px 0', borderBottom: idx < ratingHistory.length - 1 ? '1px solid #1a1a1a' : 'none',
//                 }}>
//                   <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
//                     <span style={{ fontFamily: 'sans-serif', fontWeight: '900', fontSize: '18px', color: gColor, width: 32 }}>{item.grade}</span>
//                     <div>
//                       <div style={{ color: gColor, fontWeight: '700', fontSize: '11px' }}>{item.desc || ''}</div>
//                       {item.score && <div style={{ color: C.textMuted, fontSize: '10px', fontFamily: 'sans-serif' }}>Score {item.score.toFixed ? item.score.toFixed(1) : item.score}</div>}
//                     </div>
//                   </div>
//                   <div style={{ color: C.textMuted, fontSize: '11px', fontFamily: 'sans-serif' }}>{item.date}</div>
//                 </div>
//               );
//             })}
//           </div>
//           <button style={{ width: '100%', marginTop: '20px', padding: '12px', borderRadius: '8px', backgroundColor: 'transparent', color: C.primary, border: '1px solid #D85604', fontWeight: '800', cursor: 'pointer', fontSize: '12px', transition: 'all 0.2s' }} onMouseOver={(e) => e.target.style.backgroundColor='#D856041a'} onMouseOut={(e) => e.target.style.backgroundColor='transparent'}>
//             Download Report (PDF)
//           </button>
//         </div>
//       </div>

//       {/* ── 3. 지표 영역 ── */}
//       <div style={{ padding: 'clamp(15px, 4vw, 28px)', backgroundColor: '#0f0f0f', borderRadius: '20px', border: '1px solid #1a1a1a', boxShadow: '0 10px 30px rgba(0,0,0,0.5)' }}>
//         <SectionHeader title="Valuation" subTitle="가치 평가" question="Value: 주가가 저렴한가?" description="현재 주가가 기업의 내재가치나 이익 대비 어느 수준인지 측정합니다." color="#D85604" />
//         <div style={gridContainerStyle}>
//           {valuationStats.map((stat, idx) => <MetricCard key={idx} {...stat} accentColor="#D85604" />)}
//         </div>
//         <SectionHeader title="Profitability" subTitle="수익성 분석" question="Quality: 돈을 얼마나 잘 버는가?" description="자본과 자산을 얼마나 효율적으로 사용하여 이익을 창출하는지 측정합니다." color="#F3BE26" />
//         <div style={gridContainerStyle}>
//           {profitabilityStats.map((stat, idx) => <MetricCard key={idx} {...stat} accentColor="#F3BE26" />)}
//         </div>
//       </div>

//       {/* ── 4. 뉴스 섹션 ── */}
//       <div>
//         <div style={{ display: 'flex', borderBottom: '1px solid #222', marginBottom: '20px' }}>
//           <div style={subTabStyle(activeNewsTab === 'news')} onClick={() => setActiveNewsTab('news')}>Latest Intelligence</div>
//         </div>
        
//         {newsLoading ? (
//           <div style={{ color: C.primary, textAlign: 'center', padding: '40px' }}>Loading Intel...</div>
//         ) : displayList.length > 0 ? (
//           <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(min(100%, 320px), 1fr))', gap: '20px' }}>
//             {displayList.map((item, idx) => (
//               <div key={idx} onClick={() => window.open(item.url, '_blank')} style={{ 
//                 backgroundColor: C.bgDeeper, borderRadius: '12px', border: '1px solid #1a1a1a', 
//                 overflow: 'hidden', cursor: 'pointer', display: 'flex', flexDirection: 'column',
//                 transition: 'transform 0.2s ease',
//               }} onMouseOver={(e) => e.currentTarget.style.transform='translateY(-4px)'} onMouseOut={(e) => e.currentTarget.style.transform='translateY(0)'}>
//                 <div style={{ height: '160px', backgroundColor: '#222', display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden' }}>
//                   {item.thumbnail 
//                     ? <img src={item.thumbnail} alt="thumb" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
//                     : <div style={{ color: '#333', fontWeight: 'bold', fontSize: '32px' }}>{item.type || 'NEWS'}</div>
//                   }
//                 </div>
//                 <div style={{ padding: '15px', flex: 1 }}>
//                   <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px', fontSize: '11px' }}>
//                     <span style={{ color: C.primary, fontWeight: '700' }}>{item.source}</span>
//                     <span style={{ color: C.textMuted }}>{item.time}</span>
//                   </div>
//                   <h4 style={{ color: '#fff', fontSize: '15px', margin: '0 0 10px 0', lineHeight: '1.4', fontWeight: '700' }}>{item.title}</h4>
//                   <p style={{ color: '#777', fontSize: '12px', margin: 0, display: '-webkit-box', WebkitLineClamp: '2', WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>{item.content}</p>
//                 </div>
//               </div>
//             ))}
//           </div>
//         ) : (
//           <div style={{ color: C.textMuted, textAlign: 'center', padding: '40px' }}>No data found for {ticker}.</div>
//         )}
//       </div>
//     </div>
//   );
// }

// /* ── 최종 매수/매도 시그널 배너 (반응형 최적화) ── */
// function SignalBanner({ signal, ticker, realtime }) {
//   if (!realtime) return null;
//   const gColor = signal.color; 
//   const layers = [
//     { key: 'L1', label: 'Quant', score: realtime?.l1 ?? realtime?.score, color: C.primary },
//     { key: 'L2', label: 'NLP/AI', score: realtime?.l2, color: C.pink },
//     { key: 'L3', label: 'Market', score: realtime?.l3, color: C.cyan },
//   ];

//   return (
//     <div style={{
//       backgroundColor: C.bgDeeper, borderRadius: '24px', border: '1px solid #1A1A1A',
//       padding: 'clamp(20px, 5vw, 40px)', position: 'relative', overflow: 'hidden',
//       display: 'flex', flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: '30px',
//       justifyContent: 'space-between'
//     }}>
//       <div style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '4px', backgroundColor: gColor, zIndex: 2 }} />
      
//       {/* 점수 영역 */}
//       <div style={{ zIndex: 1, flex: '1 1 300px' }}>
//         <div style={{ fontSize: '12px', fontWeight: '800', color: C.textMuted, letterSpacing: '2px', marginBottom: '8px' }}>Final SCORE</div>
//         <div style={{ display: 'flex', alignItems: 'baseline', flexWrap: 'wrap', gap: '15px', marginBottom: '5px' }}>
//           <div style={{ fontSize: 'clamp(48px, 10vw, 72px)', fontWeight: '900', color: gColor, lineHeight: '1', fontFamily: 'sans-serif' }}>{signal.score}</div>
//           <div style={{ fontSize: 'clamp(18px, 4vw, 24px)', fontWeight: '900', color: gColor }}>{signal.label}</div>
//         </div>
//         <div style={{ marginTop: '20px', padding: '12px', backgroundColor: '#111', borderRadius: '12px', border: `1px solid ${gColor}20`, maxWidth: '400px' }}>
//           <div style={{ color: gColor, fontSize: '10px', fontWeight: '800', marginBottom: '4px' }}>AI RECOMMENDATION</div>
//           <div style={{ color: '#eee', fontSize: '13px', lineHeight: 1.4 }}>
//             {signal.label === 'STRONG BUY' ? '적극 매수 및 비중 확대 권고' : signal.label === 'SELL' ? '포지션 축소 및 위험 관리 필요' : '현재 포지션 유지 및 관망'}
//           </div>
//         </div>
//       </div>

//       {/* 레이어 영역 */}
//       <div style={{ display: 'flex', gap: '10px', flexWrap: 'nowrap', zIndex: 1, overflowX: 'auto', paddingBottom: '5px' }}>
//         {layers.map(l => (
//           <div key={l.key} style={{ padding: '15px 10px', borderRadius: '16px', backgroundColor: '#0f0f0f', border: '1px solid #1a1a1a', textAlign: 'center', minWidth: '85px', flex: 1 }}>
//             <div style={{ fontSize: '10px', color: C.textMuted, fontWeight: '800', marginBottom: '5px' }}>{l.key}</div>
//             <div style={{ fontSize: '22px', fontWeight: '900', color: l.score ? l.color : '#333', fontFamily: 'sans-serif' }}>{l.score ?? '—'}</div>
//             <div style={{ fontSize: '9px', color: '#777', marginTop: '4px' }}>{l.label}</div>
//           </div>
//         ))}
//       </div>

//       {/* 워터마크 (우측 하단 고정) */}
//       <div style={{ 
//         position: 'absolute', 
//         right: '10px', 
//         bottom: '-10px', 
//         fontSize: 'clamp(80px, 15vw, 150px)', 
//         fontWeight: '900', 
//         color: '#131313', 
//         zIndex: 0, 
//         lineHeight: 1,
//         pointerEvents: 'none',
//         userSelect: 'none'
//       }}>
//         {realtime.grade}
//       </div>
//     </div>
//   );
// }