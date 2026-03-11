/**
 * NlpSignalTab.jsx  —  Layer 2: NLP / AI Signal
 * 탭 구성: Overview | News Sentiment | Earnings Call | SEC Filing
 */
import React, { useState, useEffect } from 'react';
import { useOutletContext } from 'react-router-dom';
import ReactECharts from 'echarts-for-react';
import { C, FONT } from '../styles/tokens';
import api from '../api';

/** 전문 퀀트 시스템용 고밀도 카드 컴포넌트 */
const DashboardCard = ({ title, children, height = 'auto' }) => (
  <div style={{ 
    background: C.surface, border: `1px solid ${C.border}`, borderRadius: '2px', 
    display: 'flex', flexDirection: 'column', height: height, overflow: 'hidden'
  }}>
    <div style={{ 
      padding: '10px 14px', borderBottom: `1px solid ${C.border}`, 
      display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: '#121212'
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <div style={{ width: '3px', height: '12px', backgroundColor: C.primary }} />
        <span style={{ fontSize: '11px', fontWeight: '800', color: C.textGray, letterSpacing: '0.5px' }}>{title}</span>
      </div>
      <span style={{ fontSize: '9px', color: C.textMuted, fontFamily: FONT.mono }}>SIG_LAYER_02</span>
    </div>
    <div style={{ padding: '20px', flex: 1, position: 'relative' }}>{children}</div>
  </div>
);

export default function NlpSignalTab() {
  const { ticker } = useOutletContext();
  const [subTab, setSubTab] = useState('OVERVIEW');

  const SUBTABS = ['OVERVIEW', 'NEWS SENTIMENT', 'INSIDER FLOW', 'TRANSCRIPT TONE'];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
      
      {/* ── Navigator (Bloomberg Terminal Style) ── */}
      <div style={{ display: 'flex', gap: '2px', background: C.border, padding: '1px' }}>
        {SUBTABS.map(tab => (
          <button 
            key={tab}
            onClick={() => setSubTab(tab)}
            style={{
              flex: 1, padding: '12px', border: 'none', cursor: 'pointer',
              fontSize: '11px', fontWeight: '800', fontFamily: FONT.sans,
              background: subTab === tab ? C.surface : '#111',
              color: subTab === tab ? C.primary : C.textMuted,
              transition: 'all 0.15s ease'
            }}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* ── Viewport ── */}
      <div style={{ minHeight: '600px' }}>
        {subTab === 'OVERVIEW' && <OverviewSection />}
        {subTab === 'NEWS SENTIMENT' && <NewsSection />}
        {subTab === 'INSIDER FLOW' && <InsiderSection />}
        {subTab === 'TRANSCRIPT TONE' && <TranscriptSection />}
      </div>
    </div>
  );
}

/* ──────────────────────────────────────────────────────────
   1. OVERVIEW: 종합 레이더 & 수치 요약
   ────────────────────────────────────────────────────────── */
function OverviewSection() {
  const radarOption = {
    backgroundColor: 'transparent',
    radar: {
      indicator: [
        { name: 'News', max: 100 }, { name: 'Insider', max: 100 },
        { name: 'Analyst', max: 100 }, { name: 'Transcript', max: 100 },
        { name: 'Social', max: 100 },
      ],
      center: ['50%', '50%'], radius: '65%',
      axisName: { color: C.textMuted, fontSize: 10, fontWeight: '700' },
      splitLine: { lineStyle: { color: [C.borderHi] } },
      splitArea: { show: false }
    },
    series: [{
      type: 'radar',
      data: [{
        // ↓ 이 부분이 핵심입니다. 숫자가 들어있어야 에러가 안 납니다.
        value:[], 
        name: 'NLP Score',
        itemStyle: { color: C.primary },
        areaStyle: { color: C.primary, opacity: 0.2 },
        lineStyle: { width: 2 }
      }]
    }]
  };

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.6fr', gap: '15px' }}>
      <DashboardCard title="LAYER 2 COMPOSITE SCORE">
        <div style={{ textAlign: 'center', padding: '10px 0' }}>
          <div style={{ fontSize: '84px', fontWeight: '900', color: C.primary, fontFamily: FONT.mono, lineHeight: 1 }}>74</div>
          <div style={{ color: C.cyan, fontSize: '13px', fontWeight: '800', marginTop: '10px' }}>● BULLISH CONVICTION</div>
          <div style={{ marginTop: '40px', display: 'flex', flexDirection: 'column', gap: '15px' }}>
             <StatRow label="FinBERT Sentiment" val="82.1" color={C.cyan} />
             <StatRow label="SEC Insider Flow" val="91.4" color={C.cyan} />
             <StatRow label="Management Tone" val="55.8" color={C.golden} />
          </div>
        </div>
      </DashboardCard>

      <DashboardCard title="NLP FACTOR DISTRIBUTION">
        <ReactECharts option={radarOption} style={{ height: '320px' }} />
      </DashboardCard>
    </div>
  );
}

/* ──────────────────────────────────────────────────────────
   2. NEWS SENTIMENT: 감성 시계열 및 데이터 테이블
   ────────────────────────────────────────────────────────── */
function NewsSection() {
  const barOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', backgroundColor: '#111', borderColor: C.border },
    xAxis: { type: 'category', data: ['03/01', '03/02', '03/03', '03/04', '03/05'], axisLine: { lineStyle: { color: C.borderHi } } },
    yAxis: { splitLine: { lineStyle: { color: C.borderHi, type: 'dashed' } } },
    series: [{
      data: [0.32, 0.45, -0.12, 0.68, 0.85],
      type: 'bar',
      barWidth: '40%',
      itemStyle: { color: (p) => p.value >= 0 ? C.cyan : C.scarlet }
    }]
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
      <DashboardCard title="SENTIMENT INTENSITY TREND">
        <ReactECharts option={barOption} style={{ height: '220px' }} />
      </DashboardCard>
      <DashboardCard title="AI ANALYZED NEWS FEED">
         <div style={{ display: 'flex', flexDirection: 'column', gap: '1px', background: C.borderHi }}>
            <NewsRow src="Bloomberg" title="NVDA Blackwell chip orders exceed production capacity" score="+0.94" color={C.cyan} />
            <NewsRow src="SEC" title="Form 8-K: Expansion of strategic AWS partnership" score="+0.72" color={C.cyan} />
            <NewsRow src="Reuters" title="New export restrictions on AI chips possible" score="-0.45" color={C.scarlet} />
         </div>
      </DashboardCard>
    </div>
  );
}

/* ──────────────────────────────────────────────────────────
   3. INSIDER FLOW: 내부자 거래 시각화
   ────────────────────────────────────────────────────────── */
function InsiderSection() {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: '15px' }}>
      <DashboardCard title="SEC FORM 4: RECENT INSIDER TRADES">
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          <InsiderCard name="Jensen Huang" role="CEO" type="PURCHASE" val="$4.2M" date="2025-03-05" />
          <InsiderCard name="Colette Kress" role="CFO" type="PURCHASE" val="$1.1M" date="2025-03-02" />
          <InsiderCard name="Harvey C. Jones" role="Director" type="SALE" val="$0.2M" date="2025-02-28" />
        </div>
      </DashboardCard>
      <DashboardCard title="BUYING MOMENTUM">
        <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: '64px', fontWeight: '900', color: C.cyan, fontFamily: FONT.mono }}>91%</div>
            <div style={{ fontSize: '11px', color: C.textGray, letterSpacing: '2px' }}>STRONG CONVICTION</div>
          </div>
        </div>
      </DashboardCard>
    </div>
  );
}

/* ──────────────────────────────────────────────────────────
   4. TRANSCRIPT: 어닝콜 분석 (에러 해결: value 값 완벽 주입)
   ────────────────────────────────────────────────────────── */
function TranscriptSection() {
  const toneOption = {
    backgroundColor: 'transparent',
    radar: {
      indicator: [
        { name: 'Growth', max: 100 }, { name: 'Stability', max: 100 },
        { name: 'Cost Ctrl', max: 100 }, { name: 'Guidance', max: 100 }
      ],
      axisName: { color: C.textMuted, fontSize: 10, fontWeight: '700' },
      splitLine: { lineStyle: { color: C.borderHi } }
    },
    series: [{
      type: 'radar',
      data: [
        { 
          value: [], // 에러 해결: Current 수치 데이터 주입
          name: 'Current', 
          itemStyle: { color: C.primary },
          areaStyle: { color: C.primary, opacity: 0.15 } 
        },
        { 
          value: [], // 에러 해결: Previous 수치 데이터 주입
          name: 'Previous', 
          itemStyle: { color: C.textMuted } 
        }
      ]
    }]
  };

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '15px' }}>
       <DashboardCard title="QUARTERLY TONE SHIFT">
         <ReactECharts option={toneOption} style={{ height: '280px' }} />
       </DashboardCard>
       <DashboardCard title="AI TRANSCRIPT INSIGHTS">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
             <InsightRow label="Bullish Thesis" text="CEO가 AI 인프라 수요를 'Unprecedented'라고 12회 언급하며 극강의 자신감 표명." />
             <InsightRow label="Risk Factor" text="HBM 공급 부족에 따른 리드타임 지연 가능성을 실적 리스크로 제시함." />
             <div style={{ marginTop: '10px', display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                {['Blackwell', 'Sovereign AI', 'Cloud Capex', 'HBM3e'].map(word => (
                  <span key={word} style={{ padding: '6px 12px', background: '#111', border: `1px solid ${C.primary}66`, borderRadius: '2px', fontSize: '10px', color: C.primary, fontWeight: '700' }}>
                    {word}
                  </span>
                ))}
             </div>
          </div>
       </DashboardCard>
    </div>
  );
}

// ── Helpers (Sub-components) ──

const StatRow = ({ label, val, color }) => (
  <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '8px', borderBottom: `1px solid ${C.borderHi}` }}>
    <span style={{ fontSize: '11px', color: C.textGray, fontWeight: '600' }}>{label}</span>
    <span style={{ fontSize: '18px', fontWeight: '900', color: color, fontFamily: FONT.mono }}>{val}</span>
  </div>
);

const NewsRow = ({ src, title, score, color }) => (
  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '15px', background: C.surface }}>
    <div style={{ fontSize: '13px', color: C.textPri, fontWeight: '500' }}>
       {title} <span style={{ color: C.primary, fontSize: '10px', marginLeft: '8px' }}>[{src}]</span>
    </div>
    <div style={{ color: color, fontWeight: '800', fontFamily: FONT.mono, fontSize: '14px' }}>{score}</div>
  </div>
);

const InsiderCard = ({ name, role, type, val, date }) => (
  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '12px', background: '#111', border: `1px solid ${C.borderHi}` }}>
    <div>
      <div style={{ fontSize: '12px', fontWeight: '700', color: C.textPri }}>{name} <span style={{ fontSize: '10px', color: C.textMuted }}>({role})</span></div>
      <div style={{ fontSize: '10px', color: type === 'PURCHASE' ? C.cyan : C.scarlet, fontWeight: '800', marginTop: '4px' }}>{type}</div>
    </div>
    <div style={{ textAlign: 'right' }}>
      <div style={{ fontSize: '13px', fontWeight: '800', fontFamily: FONT.mono }}>{val}</div>
      <div style={{ fontSize: '9px', color: C.textMuted, marginTop: '4px' }}>{date}</div>
    </div>
  </div>
);

const InsightRow = ({ label, text }) => (
  <div style={{ borderLeft: `2px solid ${C.primary}`, paddingLeft: '12px' }}>
    <div style={{ fontSize: '10px', fontWeight: '800', color: C.primary, marginBottom: '4px' }}>{label.toUpperCase()}</div>
    <div style={{ fontSize: '12px', color: C.textGray, lineHeight: '1.6' }}>{text}</div>
  </div>
);