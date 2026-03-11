/**
 * MarketSignalTab.jsx  —  Layer 3: Market Signal (Price / Order Flow)
 * 탭 구성: Overview | Technical | Options Flow | Dark Pool
 */
import React, { useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import { 
  Radar, RadarChart, PolarGrid, PolarAngleAxis, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, Tooltip, Cell,
  AreaChart, Area, PieChart, Pie
} from 'recharts';
import { C, FONT } from '../styles/tokens';

/** * 최신 트렌드: Glass-Bento 스타일 카드 
 */
const BentoCard = ({ title, sub, children, gridArea, glow = false }) => (
  <div style={{ 
    gridArea,
    background: 'rgba(15, 15, 15, 0.8)',
    border: `1px solid ${glow ? C.primary + '66' : C.border}`,
    borderRadius: '4px',
    padding: '20px',
    display: 'flex',
    flexDirection: 'column',
    boxShadow: glow ? `0 0 20px ${C.primary}15` : 'none',
    position: 'relative',
    overflow: 'hidden'
  }}>
    <div style={{ marginBottom: '20px', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
      <div>
        <div style={{ fontSize: '11px', fontWeight: '800', color: C.primary, letterSpacing: '1px', marginBottom: '4px' }}>{title}</div>
        <div style={{ fontSize: '10px', color: C.textMuted, fontFamily: FONT.mono }}>{sub}</div>
      </div>
      <div style={{ width: '4px', height: '4px', borderRadius: '50%', background: glow ? C.cyan : C.borderHi }} />
    </div>
    <div style={{ flex: 1, position: 'relative' }}>{children}</div>
  </div>
);

export default function MarketSignalTab() {
  const { ticker } = useOutletContext();
  const [activeTab, setActiveTab] = useState('overview');

  const SUBTABS = [
    { id: 'overview', label: 'OVERVIEW' },
    { id: 'technical', label: 'TECHNICAL' },
    { id: 'flow', label: 'ORDER FLOW' }
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      
      {/* ── Sub-Navigation (Minimalist Underline Style) ── */}
      <div style={{ display: 'flex', gap: '30px', borderBottom: `1px solid ${C.border}`, paddingLeft: '10px' }}>
        {SUBTABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              background: 'none', border: 'none', padding: '15px 0', cursor: 'pointer',
              color: activeTab === tab.id ? C.textPri : C.textMuted,
              fontSize: '11px', fontWeight: '800', letterSpacing: '1px',
              borderBottom: activeTab === tab.id ? `2px solid ${C.primary}` : '2px solid transparent',
              transition: 'all 0.3s'
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* ── Dynamic Content ── */}
      <div style={{ minHeight: '600px' }}>
        {activeTab === 'overview' && <OverviewGrid />}
        {activeTab === 'technical' && <TechnicalGrid />}
        {activeTab === 'flow' && <FlowGrid />}
      </div>
    </div>
  );
}

/* ──────────────────────────────────────────────────────────
   1. OVERVIEW: Layer 3 종합 신호 (Radar + Composite)
   ────────────────────────────────────────────────────────── */
function OverviewGrid() {
  const radarData = [
    { subject: 'Momentum', A: 85, fullMark: 100 },
    { subject: 'Volume', A: 65, fullMark: 100 },
    { subject: 'Volatility', A: 90, fullMark: 100 },
    { subject: 'Options', A: 70, fullMark: 100 },
    { subject: 'DarkPool', A: 55, fullMark: 100 },
  ];

  return (
    <div style={{ 
      display: 'grid', 
      gridTemplateColumns: 'repeat(3, 1fr)', 
      gridTemplateRows: 'repeat(2, 320px)',
      gap: '15px'
    }}>
      <BentoCard title="L3 COMPOSITE SCORE" sub="MARKET_SIGNAL_ALPHA" glow gridArea="1 / 1 / 2 / 2">
        <div style={{ textAlign: 'center', marginTop: '20px' }}>
          <div style={{ fontSize: '80px', fontWeight: '900', color: C.cyan, fontFamily: FONT.mono, lineHeight: 1 }}>88</div>
          <div style={{ color: C.cyan, fontSize: '11px', fontWeight: '800', marginTop: '10px' }}>STRONG BULLISH SIGNAL</div>
          <div style={{ marginTop: '40px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
             <ProgressLine label="Price Momentum" val={85} color={C.cyan} />
             <ProgressLine label="Supply/Demand" val={68} color={C.primary} />
          </div>
        </div>
      </BentoCard>

      <BentoCard title="SIGNAL DISTRIBUTION" sub="MULTI_FACTOR_RADAR" gridArea="1 / 2 / 2 / 4">
        <ResponsiveContainer width="100%" height="100%">
          <RadarChart data={radarData}>
            <PolarGrid stroke={C.borderHi} />
            <PolarAngleAxis dataKey="subject" tick={{ fill: C.textMuted, fontSize: 10, fontWeight: 700 }} />
            <Radar name="Signal" dataKey="A" stroke={C.primary} fill={C.primary} fillOpacity={0.2} />
          </RadarChart>
        </ResponsiveContainer>
      </BentoCard>

      <BentoCard title="RECENT SIGNAL LOG" sub="L3_EVENT_STREAM" gridArea="2 / 1 / 3 / 4">
         <div style={{ display: 'flex', flexDirection: 'column', gap: '1px' }}>
            <SignalRow type="BULLISH" msg="OBV (On-Balance Volume) 이평선 상향 돌파 포착" time="14:20" />
            <SignalRow type="BULLISH" msg="Call Options 대량 체결 (Strike $900)" time="13:45" />
            <SignalRow type="NEUTRAL" msg="RSI 과매수 구간 진입 주의 (현재 72.4)" time="11:10" />
            <SignalRow type="BEARISH" msg="Dark Pool 매도 유동성 일시적 증가" time="09:30" />
         </div>
      </BentoCard>
    </div>
  );
}

/* ──────────────────────────────────────────────────────────
   2. TECHNICAL: 기술적 지표 (RSI, OBV, MACD)
   ────────────────────────────────────────────────────────── */
function TechnicalGrid() {
  const rsiData = [
    { name: '03/01', val: 45 }, { name: '03/02', val: 52 }, { name: '03/03', val: 48 },
    { name: '03/04', val: 65 }, { name: '03/05', val: 72 }
  ];

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '15px' }}>
      <BentoCard title="RSI MOMENTUM (14)" sub="OVERBOUGHT_OVERSOLD_TREND">
        <ResponsiveContainer width="100%" height={250}>
          <AreaChart data={rsiData}>
            <defs>
              <linearGradient id="colorRsi" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={C.cyan} stopOpacity={0.3}/>
                <stop offset="95%" stopColor={C.cyan} stopOpacity={0}/>
              </linearGradient>
            </defs>
            <XAxis dataKey="name" hide />
            <YAxis domain={[0, 100]} hide />
            <Tooltip contentStyle={{ background: '#111', border: `1px solid ${C.borderHi}` }} />
            <Area type="monotone" dataKey="val" stroke={C.cyan} fillOpacity={1} fill="url(#colorRsi)" strokeWidth={3} />
          </AreaChart>
        </ResponsiveContainer>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px', color: C.textMuted, marginTop: '10px' }}>
          <span>BEARISH (30)</span>
          <span>NEUTRAL</span>
          <span style={{ color: C.cyan }}>BULLISH (70)</span>
        </div>
      </BentoCard>

      <BentoCard title="TECHNICAL SIGNALS" sub="INDICATOR_STATUS">
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <IndicatorBar label="MACD Histogram" status="BULLISH" val="+2.4" color={C.cyan} />
          <IndicatorBar label="Bollinger Band" status="SQUEEZE" val="LOW VOL" color={C.primary} />
          <IndicatorBar label="Moving Average" status="GOLDEN CROSS" val="50/200" color={C.cyan} />
          <IndicatorBar label="OBV Trend" status="ACCUMULATING" val="UP" color={C.cyan} />
        </div>
      </BentoCard>
    </div>
  );
}

/* ──────────────────────────────────────────────────────────
   3. FLOW: 옵션 및 다크풀 수급 (BarChart)
   ────────────────────────────────────────────────────────── */
function FlowGrid() {
  const optionData = [
    { type: 'Call', val: 12500, fill: C.cyan },
    { type: 'Put', val: 8400, fill: C.scarlet }
  ];

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.5fr', gap: '15px' }}>
      <BentoCard title="OPTIONS FLOW RATIO" sub="CALL_VS_PUT_VOLUME">
        <ResponsiveContainer width="100%" height={250}>
          <BarChart data={optionData} layout="vertical">
            <XAxis type="number" hide />
            <YAxis dataKey="type" type="category" tick={{ fill: C.textPri, fontSize: 12, fontWeight: 700 }} />
            <Bar dataKey="val" radius={[0, 4, 4, 0]} barSize={40}>
              {optionData.map((entry, index) => <Cell key={`cell-${index}`} fill={entry.fill} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </BentoCard>

      <BentoCard title="DARK POOL ACCUMULATION" sub="INSTITUTION_NET_FLOW">
        <div style={{ height: '200px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: '11px', color: C.textMuted, marginBottom: '10px' }}>NET FLOW (EST.)</div>
            <div style={{ fontSize: '42px', fontWeight: '900', color: C.cyan, fontFamily: FONT.mono }}>+$1.24B</div>
            <div style={{ fontSize: '10px', color: C.textGray, marginTop: '10px' }}>기관 매집 시그널 포착 - 최근 5거래일 연속 유입</div>
          </div>
        </div>
      </BentoCard>
    </div>
  );
}

// ── Helper Components ──

const ProgressLine = ({ label, val, color }) => (
  <div style={{ textAlign: 'left' }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px', color: C.textMuted, marginBottom: '5px' }}>
      <span>{label}</span><span>{val}%</span>
    </div>
    <div style={{ height: '2px', background: '#1a1a1a' }}>
      <div style={{ width: `${val}%`, height: '100%', background: color, boxShadow: `0 0 8px ${color}` }} />
    </div>
  </div>
);

const SignalRow = ({ type, msg, time }) => (
  <div style={{ display: 'flex', gap: '15px', padding: '14px 10px', borderBottom: `1px solid ${C.border}`, alignItems: 'center' }}>
    <span style={{ fontSize: '10px', fontWeight: '900', color: type === 'BULLISH' ? C.cyan : type === 'BEARISH' ? C.scarlet : C.textMuted, minWidth: '60px' }}>{type}</span>
    <span style={{ fontSize: '12px', color: C.textPri, flex: 1 }}>{msg}</span>
    <span style={{ fontSize: '10px', color: C.textMuted, fontFamily: FONT.mono }}>{time}</span>
  </div>
);

const IndicatorBar = ({ label, status, val, color }) => (
  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px', background: '#0a0a0a', border: `1px solid ${C.borderHi}` }}>
    <div>
      <div style={{ fontSize: '10px', color: C.textMuted, fontWeight: '700' }}>{label}</div>
      <div style={{ fontSize: '12px', color: color, fontWeight: '900', marginTop: '2px' }}>{status}</div>
    </div>
    <div style={{ fontSize: '16px', fontWeight: '900', color: C.textPri, fontFamily: FONT.mono }}>{val}</div>
  </div>
);