/**
 * MarketSignalTab.jsx  —  Layer 3: 시장 신호 (Price / Order Flow)
 *
 * 설계서 v2.0 반영 항목:
 *  ✅ 기술 지표: Relative Momentum(12-1), 52W High Position, Trend Stability(R²), RSI, OBV, Volume Surge
 *  ✅ 차트 패턴 Detection: 8개 패턴 (Cup&Handle, Double Bottom, Bull Flag, H&S, etc.)
 *  ✅ 공매도·옵션 흐름: Short Interest%, Put/Call Ratio, Unusual Activity
 *  ✅ 거시지표: VIX, Fear&Greed, 섹터 ETF, 연준 금리 사이클 (Phase 3)
 *
 * 디자인: Bloomberg Terminal × Seeking Alpha — 단색 위주, 데이터 밀도 우선
 */
import React, { useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import {
  AreaChart, Area, BarChart, Bar, ComposedChart, Line,
  XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine,
  RadarChart, PolarGrid, PolarAngleAxis, Radar, Cell,
} from 'recharts';
import { C, FONT } from '../styles/tokens';

const T = {
  bg:'#0a0a0a', surface:'#0f0f0f', card:'#111111', border:'#1e1e1e', borderHi:'#2a2a2a',
  text:'#e2e2e2', textSub:'#888888', textMuted:'#444444',
  accent:'#D85604', up:'#22c55e', down:'#ef4444', neutral:'#a0a0a0', l3:'#0891b2',
};
const tt = { backgroundColor:'#111', border:`1px solid #2a2a2a`, borderRadius:2, fontSize:10, color:'#e2e2e2', fontFamily:FONT.sans, padding:'7px 12px' };

const SL = ({ children, right }) => (
  <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:14 }}>
    <span style={{ fontSize:9, fontWeight:700, letterSpacing:2, color:T.textMuted, textTransform:'uppercase', fontFamily:FONT.sans }}>{children}</span>
    {right && <span style={{ fontSize:9, color:T.textMuted, fontFamily:FONT.sans }}>{right}</span>}
  </div>
);
const Card = ({ children, style={} }) => (
  <div style={{ background:T.card, border:`1px solid ${T.border}`, borderRadius:2, padding:'18px 20px', ...style }}>{children}</div>
);
const MiniBar = ({ val, max=100, color=T.accent }) => (
  <div style={{ height:2, background:T.borderHi, borderRadius:1 }}>
    <div style={{ width:`${Math.min(val/max,1)*100}%`, height:'100%', background:color }} />
  </div>
);
const Badge = ({ children, color }) => (
  <span style={{ fontSize:9, fontWeight:800, padding:'2px 6px', borderRadius:2, background:`${color}18`, color, border:`1px solid ${color}35`, letterSpacing:0.5, fontFamily:FONT.sans, whiteSpace:'nowrap' }}>{children}</span>
);
const TH = ({ children, right }) => (
  <th style={{ padding:'7px 14px', textAlign:right?'right':'left', fontSize:9, color:T.textMuted, fontWeight:700, letterSpacing:1.5, textTransform:'uppercase', fontFamily:FONT.sans }}>{children}</th>
);
const TD = ({ children, style={} }) => <td style={{ padding:'10px 14px', fontSize:11, color:T.textSub, ...style }}>{children}</td>;

const SUBTABS = [
  { id:'OVERVIEW', label:'Overview' },
  { id:'TECHNICAL',label:'Technical' },
  { id:'PATTERNS', label:'Chart Patterns' },
  { id:'FLOW',     label:'Order Flow' },
  { id:'MACRO',    label:'Macro' },
];

export default function MarketSignalTab() {
  const { ticker } = useOutletContext();
  const [tab, setTab] = useState('OVERVIEW');
  return (
    <div style={{ fontFamily:FONT.sans, color:T.text }}>
      <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', padding:'9px 14px', background:T.surface, border:`1px solid ${T.border}`, borderLeft:`3px solid ${T.l3}`, marginBottom:14 }}>
        <div style={{ display:'flex', alignItems:'center', gap:12 }}>
          <span style={{ fontSize:9, fontWeight:800, color:T.l3, letterSpacing:2, fontFamily:FONT.sans }}>LAYER 3</span>
          <span style={{ width:1, height:12, background:T.border, display:'inline-block' }} />
          <span style={{ fontSize:11, color:T.textSub }}>시장 신호 (Price / Order Flow)</span>
          <span style={{ fontSize:9, color:T.textMuted, fontFamily:FONT.sans }}>· 가중치 25%</span>
        </div>
        <span style={{ fontSize:9, color:T.textMuted, fontFamily:FONT.sans }}>기술지표 매일 · 공매도 T+1 · VIX 실시간</span>
      </div>

      <div style={{ display:'flex', borderBottom:`1px solid ${T.border}`, marginBottom:20 }}>
        {SUBTABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)} style={{ padding:'9px 16px', background:'none', border:'none', borderBottom:tab===t.id?`2px solid ${T.accent}`:'2px solid transparent', color:tab===t.id?T.text:T.textMuted, fontSize:11, fontWeight:tab===t.id?700:400, cursor:'pointer', transition:'color 0.12s', position:'relative', top:1 }}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'OVERVIEW'  && <OverviewTab  ticker={ticker} />}
      {tab === 'TECHNICAL' && <TechnicalTab ticker={ticker} />}
      {tab === 'PATTERNS'  && <PatternsTab  ticker={ticker} />}
      {tab === 'FLOW'      && <FlowTab      ticker={ticker} />}
      {tab === 'MACRO'     && <MacroTab     ticker={ticker} />}
    </div>
  );
}

/* ── 1. OVERVIEW ── */
function OverviewTab() {
  const radar = [
    { axis:'Momentum', A:85 }, { axis:'Volume',    A:72 },
    { axis:'Volatility', A:68 }, { axis:'Options',  A:74 },
    { axis:'DarkPool', A:55 },
  ];
  const scores = [
    { label:'Relative Momentum (12-1)', score:85, sig:'STRONG',    color:T.up,      note:'SPY 대비 +34% 초과수익 (52주)' },
    { label:'52W High Position',         score:94, sig:'NEAR HIGH', color:T.up,      note:'현재가 / 52주 고점 = 94%' },
    { label:'Trend Stability (R²)',       score:78, sig:'STABLE',   color:T.up,      note:'90일 회귀 R²=0.82 · 기관 매집 신호' },
    { label:'RSI (14일)',                  score:62, sig:'CAUTION',  color:'#f59e0b', note:'RSI 72.4 · 과매수 주의 진입' },
    { label:'OBV Trend',                   score:71, sig:'BULLISH',  color:T.up,      note:'OBV 우상향 + 가격 보합 = 기관 매집' },
    { label:'Volume Surge',                score:58, sig:'WATCH',    color:'#f59e0b', note:'20일 평균 1.8배 · 임계치 미도달' },
  ];
  const signals = [
    { type:'BULLISH', msg:'OBV 이평선 상향 돌파',                 time:'14:20' },
    { type:'BULLISH', msg:'Call Options 대량 체결 (Strike $900)', time:'13:45' },
    { type:'NEUTRAL', msg:'RSI 과매수 진입 주의 (72.4)',          time:'11:10' },
    { type:'BEARISH', msg:'Dark Pool 매도 유동성 일시 증가',      time:'09:30' },
  ];
  return (
    <div style={{ display:'grid', gridTemplateColumns:'340px 1fr', gap:16 }}>
      <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
        <Card>
          <SL right="L3 COMPOSITE">LAYER 3 SCORE</SL>
          <div style={{ display:'flex', alignItems:'flex-end', gap:14, marginBottom:18 }}>
            <div style={{ fontSize:68, fontWeight:900, color:T.text, fontFamily:FONT.sans, lineHeight:1 }}>88</div>
            <div style={{ paddingBottom:6 }}>
              <div style={{ fontSize:9, color:T.up, fontWeight:700, letterSpacing:1, marginBottom:3 }}>▲ STRONG BULLISH SIGNAL</div>
              <div style={{ fontSize:9, color:T.textMuted, fontFamily:FONT.sans }}>타이밍 진입 조건 근접</div>
            </div>
          </div>
          <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
            {scores.map(s => (
              <div key={s.label}>
                <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:4 }}>
                  <span style={{ fontSize:10, color:T.textSub }}>{s.label}</span>
                  <div style={{ display:'flex', gap:7, alignItems:'center' }}>
                    <Badge color={s.color}>{s.sig}</Badge>
                    <span style={{ fontSize:12, fontWeight:700, color:s.color, fontFamily:FONT.sans, minWidth:22, textAlign:'right' }}>{s.score}</span>
                  </div>
                </div>
                <MiniBar val={s.score} color={s.color} />
                <div style={{ fontSize:9, color:T.textMuted, marginTop:2 }}>{s.note}</div>
              </div>
            ))}
          </div>
        </Card>
      </div>
      <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
        <Card>
          <SL right="MULTI-FACTOR RADAR">SIGNAL DISTRIBUTION</SL>
          <ResponsiveContainer width="100%" height={240}>
            <RadarChart data={radar}>
              <PolarGrid stroke={T.borderHi} />
              <PolarAngleAxis dataKey="axis" tick={{ fill:T.textMuted, fontSize:10, fontFamily:FONT.sans }} />
              <Radar name="L3 Score" dataKey="A" stroke={T.l3} fill={T.l3} fillOpacity={0.1} strokeWidth={1.5} />
              <Tooltip contentStyle={tt} formatter={v => [`${v}점`,'Score']} />
            </RadarChart>
          </ResponsiveContainer>
        </Card>
        <Card style={{ padding:0 }}>
          <div style={{ padding:'12px 18px', borderBottom:`1px solid ${T.border}` }}><SL>RECENT SIGNAL LOG</SL></div>
          {signals.map((s,i) => (
            <div key={i} style={{ display:'flex', gap:14, padding:'11px 18px', borderBottom:`1px solid ${T.border}22`, background:i%2?T.surface:'transparent', alignItems:'center' }}>
              <Badge color={s.type==='BULLISH'?T.up:s.type==='BEARISH'?T.down:T.neutral}>{s.type}</Badge>
              <span style={{ fontSize:12, color:T.textSub, flex:1 }}>{s.msg}</span>
              <span style={{ fontSize:9, color:T.textMuted, fontFamily:FONT.sans }}>{s.time}</span>
            </div>
          ))}
        </Card>
      </div>
    </div>
  );
}

/* ── 2. TECHNICAL — 6개 지표 전체 ── */
function TechnicalTab() {
  const rsiData = [{ d:'03/01',v:45 },{ d:'03/02',v:52 },{ d:'03/03',v:48 },{ d:'03/04',v:65 },{ d:'03/05',v:72 },{ d:'03/06',v:71 },{ d:'03/07',v:72 }];
  const obvData = [{ d:'03/01',v:820 },{ d:'03/02',v:854 },{ d:'03/03',v:831 },{ d:'03/04',v:892 },{ d:'03/05',v:941 },{ d:'03/06',v:978 },{ d:'03/07',v:1024 }];
  const volData = [{ d:'03/01',v:32 },{ d:'03/02',v:41 },{ d:'03/03',v:29 },{ d:'03/04',v:55 },{ d:'03/05',v:88 },{ d:'03/06',v:62 },{ d:'03/07',v:47 }];
  const inds = [
    { name:'Relative Momentum (12-1)', wt:'30pt', val:'+34.2%',  sig:'BULLISH',   color:T.up,      desc:'SPY 대비 초과수익 ≥30%. 45pt 만점. Jegadeesh-Titman 1993 실증.' },
    { name:'52W High Position',         wt:'20pt', val:'94%',     sig:'NEAR HIGH', color:T.up,      desc:'현재가/52주 고점. ≥95% 최고점 강세. 신고가 돌파 매수 신호.' },
    { name:'Trend Stability (R²)',       wt:'15pt', val:'R²=0.82', sig:'STABLE',   color:T.up,      desc:'90일 회귀 R²≥0.7 = 추세 안정. 기관 매집 신호.' },
    { name:'RSI (14일)',                  wt:'15pt', val:'72.4',   sig:'CAUTION',   color:'#f59e0b', desc:'과매수 >70 진입. 차익실현 고려 구간. 역추세 탐지.' },
    { name:'OBV (On-Balance Volume)',     wt:'10pt', val:'↑ 우상향',sig:'BULLISH',  color:T.up,      desc:'OBV 우상향 + 가격 보합 = 기관 매집. 발산 시 전환 경보.' },
    { name:'Volume Surge (20일 대비)',    wt:'10pt', val:'×1.8',   sig:'WATCH',     color:'#f59e0b', desc:'3배 이상 = 이상 거래 신호. 현재 임계치 미도달.' },
  ];
  return (
    <div style={{ display:'flex', flexDirection:'column', gap:16 }}>
      <Card style={{ padding:0 }}>
        <div style={{ padding:'12px 18px', borderBottom:`1px solid ${T.border}` }}>
          <SL right="FDR · 매일">TECHNICAL INDICATORS — 설계서 6/6 항목</SL>
        </div>
        <table style={{ width:'100%', borderCollapse:'collapse' }}>
          <thead><tr style={{ borderBottom:`1px solid ${T.border}` }}>
            <TH>Indicator</TH><TH>Weight</TH><TH right>Value</TH><TH>Signal</TH><TH>Interpretation</TH>
          </tr></thead>
          <tbody>
            {inds.map((r,i) => (
              <tr key={i} style={{ borderBottom:`1px solid ${T.border}22`, background:i%2?T.surface:'transparent' }}>
                <TD style={{ fontWeight:600, color:T.text, whiteSpace:'nowrap' }}>{r.name}</TD>
                <TD style={{ color:T.textMuted, fontFamily:FONT.sans }}>{r.wt}</TD>
                <TD style={{ textAlign:'right', fontWeight:700, fontFamily:FONT.sans }}>{r.val}</TD>
                <TD><Badge color={r.color}>{r.sig}</Badge></TD>
                <TD style={{ fontSize:10, lineHeight:1.5 }}>{r.desc}</TD>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr 1fr', gap:16 }}>
        {/* RSI */}
        <Card>
          <SL right="14일">RSI MOMENTUM</SL>
          <ResponsiveContainer width="100%" height={150}>
            <AreaChart data={rsiData} margin={{ left:-22,right:0,top:4 }}>
              <defs><linearGradient id="rsiG" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor={T.l3} stopOpacity={0.2}/><stop offset="95%" stopColor={T.l3} stopOpacity={0}/></linearGradient></defs>
              <XAxis dataKey="d" tick={{ fill:T.textMuted, fontSize:8, fontFamily:FONT.sans }} axisLine={false} tickLine={false} />
              <YAxis domain={[0,100]} tick={{ fill:T.textMuted, fontSize:8, fontFamily:FONT.sans }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={tt} formatter={v=>[`RSI ${v}`,'']} />
              <ReferenceLine y={70} stroke="#f59e0b" strokeDasharray="3 3" />
              <ReferenceLine y={30} stroke={T.up}    strokeDasharray="3 3" />
              <Area type="monotone" dataKey="v" stroke={T.l3} fill="url(#rsiG)" strokeWidth={2} dot={false} />
            </AreaChart>
          </ResponsiveContainer>
          <div style={{ display:'flex', justifyContent:'space-between', fontSize:9, color:T.textMuted, marginTop:5 }}>
            <span>Oversold 30</span><span style={{ color:'#f59e0b' }}>Overbought 70</span>
          </div>
        </Card>
        {/* OBV */}
        <Card>
          <SL right="누적">OBV TREND</SL>
          <ResponsiveContainer width="100%" height={150}>
            <AreaChart data={obvData} margin={{ left:-22,right:0,top:4 }}>
              <defs><linearGradient id="obvG" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor={T.up} stopOpacity={0.2}/><stop offset="95%" stopColor={T.up} stopOpacity={0}/></linearGradient></defs>
              <XAxis dataKey="d" tick={{ fill:T.textMuted, fontSize:8, fontFamily:FONT.sans }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill:T.textMuted, fontSize:8, fontFamily:FONT.sans }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={tt} />
              <Area type="monotone" dataKey="v" stroke={T.up} fill="url(#obvG)" strokeWidth={2} dot={false} />
            </AreaChart>
          </ResponsiveContainer>
          <div style={{ fontSize:9, color:T.up, marginTop:5 }}>↑ 우상향 확인 · 기관 매집 신호</div>
        </Card>
        {/* Volume */}
        <Card>
          <SL right="20일 평균 대비">VOLUME SURGE</SL>
          <ResponsiveContainer width="100%" height={150}>
            <BarChart data={volData} margin={{ left:-22,right:0,top:4 }}>
              <XAxis dataKey="d" tick={{ fill:T.textMuted, fontSize:8, fontFamily:FONT.sans }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill:T.textMuted, fontSize:8, fontFamily:FONT.sans }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={tt} formatter={v=>[`${v}M주`,'']} />
              <ReferenceLine y={96} stroke={T.down} strokeDasharray="3 3" />
              <Bar dataKey="v" maxBarSize={20} radius={[2,2,0,0]}>
                {volData.map((e,i) => <Cell key={i} fill={e.v>=96?T.down:T.borderHi} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <div style={{ fontSize:9, color:T.textMuted, marginTop:5 }}>3배↑ 이상 거래 = 이상 신호 임계</div>
        </Card>
      </div>
    </div>
  );
}

/* ── 3. CHART PATTERNS — 8개 패턴 ── */
function PatternsTab() {
  const patterns = [
    { name:'Cup and Handle',   dir:'BUY',    conf:5, status:'DETECTED',      detail:'6~65주 컵 형성 + 손잡이 완성. 저항선 돌파 임박. 목표 +30%.' },
    { name:'Double Bottom',    dir:'BUY',    conf:4, status:'WATCH',          detail:'두 저점 유사 가격 확인. 넥라인($840) 돌파 대기 중.' },
    { name:'Bull Flag',        dir:'BUY',    conf:4, status:'FORMING',        detail:'강한 상승 후 소폭 하락 채널 형성. 채널 상단 돌파 + 거래량 확인 필요.' },
    { name:'Head & Shoulders', dir:'SELL',   conf:5, status:'NOT DETECTED',   detail:'반전 패턴 미감지. 우측 어깨 미형성.' },
    { name:'Inverse H&S',      dir:'BUY',    conf:5, status:'NOT DETECTED',   detail:'저점 3개 구조 미형성.' },
    { name:'BB Squeeze',       dir:'NEUTRAL',conf:3, status:'FORMING',        detail:'Bollinger Band 폭 6주 최소치 수렴. 방향성 돌파 직전.' },
    { name:'VWAP Breakout',    dir:'BUY',    conf:3, status:'CONFIRMED',      detail:'종가 > VWAP 5일 연속. 기관 매수 흔적 지속 확인.' },
    { name:'Golden Cross',     dir:'BUY',    conf:4, status:'CONFIRMED',      detail:'MA50($821) > MA200($745). 중기 상승 전환 완료.' },
  ];
  const sc = s => s==='DETECTED'||s==='CONFIRMED'?T.up:s==='FORMING'||s==='WATCH'?'#f59e0b':T.textMuted;
  const dc = d => d==='BUY'?T.up:d==='SELL'?T.down:T.neutral;
  const stars = n => '★'.repeat(n)+'☆'.repeat(5-n);
  const confirmed = patterns.filter(p=>p.status==='CONFIRMED'||p.status==='DETECTED').length;

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:16 }}>
      <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:12 }}>
        {[
          { l:'탐지됨 (Confirmed/Detected)', v:`${confirmed}개`, c:T.up },
          { l:'형성 중 (Forming/Watch)',      v:'3개', c:'#f59e0b' },
          { l:'미감지',                       v:'2개', c:T.textMuted },
          { l:'매수 신호 패턴',               v:`${patterns.filter(p=>p.dir==='BUY'&&(p.status==='DETECTED'||p.status==='CONFIRMED')).length}개`, c:T.up },
        ].map(s => (
          <Card key={s.l}>
            <div style={{ fontSize:9, color:T.textMuted, marginBottom:5 }}>{s.l}</div>
            <div style={{ fontSize:26, fontWeight:900, color:s.c, fontFamily:FONT.sans }}>{s.v}</div>
          </Card>
        ))}
      </div>
      <Card style={{ padding:0 }}>
        <div style={{ padding:'12px 18px', borderBottom:`1px solid ${T.border}` }}>
          <SL right="pandas-ta · 알고리즘 기반">CHART PATTERN DETECTION — 설계서 8/8 항목</SL>
        </div>
        <table style={{ width:'100%', borderCollapse:'collapse' }}>
          <thead><tr style={{ borderBottom:`1px solid ${T.border}` }}>
            <TH>Pattern</TH><TH>Direction</TH><TH>Reliability</TH><TH>Status</TH><TH>Detail</TH>
          </tr></thead>
          <tbody>
            {patterns.map((p,i) => (
              <tr key={i} style={{ borderBottom:`1px solid ${T.border}22`, background:i%2?T.surface:'transparent' }}>
                <TD style={{ fontWeight:600, color:T.text, whiteSpace:'nowrap' }}>{p.name}</TD>
                <TD><Badge color={dc(p.dir)}>{p.dir}</Badge></TD>
                <TD style={{ fontFamily:FONT.sans, color:'#f59e0b', letterSpacing:1, fontSize:10 }}>{stars(p.conf)}</TD>
                <TD><Badge color={sc(p.status)}>{p.status}</Badge></TD>
                <TD style={{ fontSize:10, lineHeight:1.5, color:T.textMuted }}>{p.detail}</TD>
              </tr>
            ))}
          </tbody>
        </table>
        <div style={{ padding:'8px 18px', borderTop:`1px solid ${T.border}`, fontSize:9, color:T.textMuted, fontFamily:FONT.sans }}>
          CNN 이미지 학습 제외. 알고리즘(룰 기반) 방식 — 설명 가능성·신뢰성 확보 (설계서 4.2)
        </div>
      </Card>
    </div>
  );
}

/* ── 4. ORDER FLOW — 공매도 + 옵션 ── */
function FlowTab() {
  const siTrend = [{ d:'Feb W1',v:1.8 },{ d:'Feb W2',v:2.1 },{ d:'Feb W3',v:2.4 },{ d:'Feb W4',v:2.9 },{ d:'Mar W1',v:2.2 }];
  const pcTrend = [{ d:'03/01',v:0.72 },{ d:'03/02',v:0.81 },{ d:'03/03',v:1.10 },{ d:'03/04',v:0.65 },{ d:'03/05',v:0.58 }];
  const unusual = [
    { type:'CALL', strike:'$950', exp:'Apr 18', vol:'24,800', oi:'8,200',  pm:'$12.4M', flag:true },
    { type:'CALL', strike:'$900', exp:'Mar 21', vol:'18,500', oi:'12,400', pm:'$8.1M',  flag:true },
    { type:'PUT',  strike:'$750', exp:'Apr 18', vol:'9,200',  oi:'3,100',  pm:'$2.8M',  flag:false },
    { type:'PUT',  strike:'$800', exp:'Jun 20', vol:'7,400',  oi:'5,600',  pm:'$4.2M',  flag:false },
  ];
  return (
    <div style={{ display:'flex', flexDirection:'column', gap:16 }}>
      <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:12 }}>
        {[
          { l:'Short Interest %', v:'2.2%',  s:'Float 대비 · 낮음',    c:T.up,      n:'20%↑ = Squeeze 잠재성' },
          { l:'Put/Call Ratio',   v:'0.58',  s:'극단 낙관 경계',         c:'#f59e0b', n:'< 0.6 주의 구간' },
          { l:'Unusual Options',  v:'2건',   s:'평상시 5배↑ Call 감지', c:T.up,      n:'내부자 정보 가능성' },
          { l:'Short Squeeze',    v:'LOW',   s:'공매도 비율 낮음',       c:T.neutral, n:'FINRA T+1 데이터' },
        ].map(s => (
          <Card key={s.l}>
            <div style={{ fontSize:9, color:T.textMuted, marginBottom:5 }}>{s.l}</div>
            <div style={{ fontSize:24, fontWeight:900, color:s.c, fontFamily:FONT.sans, lineHeight:1 }}>{s.v}</div>
            <div style={{ fontSize:10, color:T.textSub, marginTop:4 }}>{s.s}</div>
            <div style={{ fontSize:9, color:T.textMuted, marginTop:2 }}>{s.n}</div>
          </Card>
        ))}
      </div>
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16 }}>
        <Card>
          <SL right="FINRA T+1">SHORT INTEREST TREND (%)</SL>
          <ResponsiveContainer width="100%" height={160}>
            <AreaChart data={siTrend} margin={{ left:-22,right:0,top:4 }}>
              <defs><linearGradient id="siG" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor={T.down} stopOpacity={0.2}/><stop offset="95%" stopColor={T.down} stopOpacity={0}/></linearGradient></defs>
              <XAxis dataKey="d" tick={{ fill:T.textMuted, fontSize:8, fontFamily:FONT.sans }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill:T.textMuted, fontSize:8, fontFamily:FONT.sans }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={tt} formatter={v=>[`${v}%`,'Short Interest']} />
              <ReferenceLine y={20} stroke={T.down} strokeDasharray="3 3" />
              <Area type="monotone" dataKey="v" stroke={T.down} fill="url(#siG)" strokeWidth={1.5} dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        </Card>
        <Card>
          <SL right="5일">PUT/CALL RATIO</SL>
          <ResponsiveContainer width="100%" height={160}>
            <AreaChart data={pcTrend} margin={{ left:-22,right:0,top:4 }}>
              <defs><linearGradient id="pcG" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor={T.l3} stopOpacity={0.2}/><stop offset="95%" stopColor={T.l3} stopOpacity={0}/></linearGradient></defs>
              <XAxis dataKey="d" tick={{ fill:T.textMuted, fontSize:8, fontFamily:FONT.sans }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill:T.textMuted, fontSize:8, fontFamily:FONT.sans }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={tt} formatter={v=>[v.toFixed(2),'P/C Ratio']} />
              <ReferenceLine y={1.2} stroke={T.down}    strokeDasharray="3 3" />
              <ReferenceLine y={0.6} stroke={'#f59e0b'} strokeDasharray="3 3" />
              <Area type="monotone" dataKey="v" stroke={T.l3} fill="url(#pcG)" strokeWidth={1.5} dot={false} />
            </AreaChart>
          </ResponsiveContainer>
          <div style={{ display:'flex', justifyContent:'space-between', fontSize:9, color:T.textMuted, marginTop:5 }}>
            <span style={{ color:'#f59e0b' }}>극단 낙관 &lt;0.6</span>
            <span style={{ color:T.down }}>극단 비관 &gt;1.2</span>
          </div>
        </Card>
      </div>
      <Card style={{ padding:0 }}>
        <div style={{ padding:'12px 18px', borderBottom:`1px solid ${T.border}` }}>
          <SL right="평상시 5배↑">OPTIONS UNUSUAL ACTIVITY</SL>
        </div>
        <table style={{ width:'100%', borderCollapse:'collapse' }}>
          <thead><tr style={{ borderBottom:`1px solid ${T.border}` }}>
            <TH>Type</TH><TH>Strike</TH><TH>Expiry</TH><TH right>Volume</TH><TH right>OI</TH><TH right>Premium</TH><TH>Flag</TH>
          </tr></thead>
          <tbody>
            {unusual.map((r,i) => (
              <tr key={i} style={{ borderBottom:`1px solid ${T.border}22`, background:i%2?T.surface:'transparent' }}>
                <TD><Badge color={r.type==='CALL'?T.up:T.down}>{r.type}</Badge></TD>
                <TD style={{ fontFamily:FONT.sans, fontWeight:700 }}>{r.strike}</TD>
                <TD style={{ color:T.textMuted, fontFamily:FONT.sans }}>{r.exp}</TD>
                <TD style={{ textAlign:'right', fontFamily:FONT.sans }}>{r.vol}</TD>
                <TD style={{ textAlign:'right', fontFamily:FONT.sans }}>{r.oi}</TD>
                <TD style={{ textAlign:'right', fontWeight:700, fontFamily:FONT.sans }}>{r.pm}</TD>
                <TD>{r.flag && <Badge color={T.up}>UNUSUAL</Badge>}</TD>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

/* ── 5. MACRO — VIX, Fear&Greed, ETF, 금리 ── */
function MacroTab() {
  const vixData = [{ d:'Feb W1',v:18.2 },{ d:'Feb W2',v:21.4 },{ d:'Feb W3',v:19.8 },{ d:'Feb W4',v:16.5 },{ d:'Mar W1',v:14.2 }];
  const fgData  = [{ d:'03/01',v:68 },{ d:'03/02',v:72 },{ d:'03/03',v:65 },{ d:'03/04',v:71 },{ d:'03/05',v:74 }];
  const etfFlow = [
    { name:'XLK (Tech)',   flow:+2.4 },{ name:'XLF (Fin)',    flow:+1.1 },
    { name:'XLE (Energy)', flow:-0.8 },{ name:'XLV (Health)', flow:+0.3 },
    { name:'XLI (Indust)', flow:-0.2 },
  ];
  return (
    <div style={{ display:'flex', flexDirection:'column', gap:16 }}>
      <div style={{ padding:'9px 14px', background:T.surface, border:`1px solid #f59e0b40`, borderLeft:`3px solid #f59e0b`, fontSize:9, color:'#f59e0b', fontFamily:FONT.sans }}>
        ⚙ Phase 3 기능 — FRED API (VIX·금리), CNN Business (Fear&Greed), FDR (섹터 ETF). 현재 Mock 데이터.
      </div>
      <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:12 }}>
        {[
          { l:'VIX Index',      v:'14.2',  s:'정상 시장 (< 25)',  c:T.up,      n:'>30 = 극단 공포 → 역발상 매수' },
          { l:'Fear & Greed',   v:'74',    s:'극단 탐욕 경계',    c:'#f59e0b', n:'75~100 = 리스크 축소 플래그' },
          { l:'Fed Fund Rate',  v:'5.25%', s:'동결 국면',          c:T.neutral, n:'인하 시 Growth 팩터 가중치 상향' },
          { l:'Tech ETF (XLK)', v:'+2.4%', s:'섹터 자금 유입',    c:T.up,      n:'유입 섹터 종목 보너스 점수 적용' },
        ].map(s => (
          <Card key={s.l}>
            <div style={{ fontSize:9, color:T.textMuted, marginBottom:5 }}>{s.l}</div>
            <div style={{ fontSize:26, fontWeight:900, color:s.c, fontFamily:FONT.sans, lineHeight:1 }}>{s.v}</div>
            <div style={{ fontSize:10, color:T.textSub, marginTop:4 }}>{s.s}</div>
            <div style={{ fontSize:9, color:T.textMuted, marginTop:2 }}>{s.n}</div>
          </Card>
        ))}
      </div>
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16 }}>
        <Card>
          <SL right="FRED API">VIX INDEX TREND</SL>
          <ResponsiveContainer width="100%" height={160}>
            <AreaChart data={vixData} margin={{ left:-22,right:0,top:4 }}>
              <defs><linearGradient id="vG" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor={T.down} stopOpacity={0.15}/><stop offset="95%" stopColor={T.down} stopOpacity={0}/></linearGradient></defs>
              <XAxis dataKey="d" tick={{ fill:T.textMuted, fontSize:8, fontFamily:FONT.sans }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill:T.textMuted, fontSize:8, fontFamily:FONT.sans }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={tt} formatter={v=>[`VIX ${v}`,'']} />
              <ReferenceLine y={30} stroke={T.down}    strokeDasharray="3 3" />
              <ReferenceLine y={15} stroke={'#f59e0b'} strokeDasharray="3 3" />
              <Area type="monotone" dataKey="v" stroke={T.down} fill="url(#vG)" strokeWidth={1.5} dot={false} />
            </AreaChart>
          </ResponsiveContainer>
          <div style={{ display:'flex', justifyContent:'space-between', fontSize:9, color:T.textMuted, marginTop:5 }}>
            <span style={{ color:'#f59e0b' }}>낙관 &lt;15</span>
            <span style={{ color:T.down }}>극단 공포 &gt;30</span>
          </div>
        </Card>
        <Card>
          <SL right="CNN Business">FEAR & GREED INDEX</SL>
          <ResponsiveContainer width="100%" height={160}>
            <ComposedChart data={fgData} margin={{ left:-22,right:0,top:4 }}>
              <XAxis dataKey="d" tick={{ fill:T.textMuted, fontSize:8, fontFamily:FONT.sans }} axisLine={false} tickLine={false} />
              <YAxis domain={[0,100]} tick={{ fill:T.textMuted, fontSize:8, fontFamily:FONT.sans }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={tt} formatter={v=>[`F&G ${v}`,'']} />
              <ReferenceLine y={75} stroke={'#f59e0b'} strokeDasharray="3 3" />
              <ReferenceLine y={25} stroke={T.up}      strokeDasharray="3 3" />
              <Bar dataKey="v" maxBarSize={20} radius={[2,2,0,0]}>
                {fgData.map((e,i) => <Cell key={i} fill={e.v>75?'#f59e0b':e.v<25?T.up:T.borderHi} fillOpacity={0.7} />)}
              </Bar>
              <Line type="monotone" dataKey="v" stroke={T.accent} strokeWidth={1.5} dot={false} />
            </ComposedChart>
          </ResponsiveContainer>
          <div style={{ display:'flex', justifyContent:'space-between', fontSize:9, color:T.textMuted, marginTop:5 }}>
            <span style={{ color:T.up }}>극단 공포 (역발상 매수)</span>
            <span style={{ color:'#f59e0b' }}>극단 탐욕 (경고)</span>
          </div>
        </Card>
      </div>
      <Card>
        <SL right="FDR · 일간">SECTOR ETF FUND FLOW (B$)</SL>
        <ResponsiveContainer width="100%" height={150}>
          <BarChart data={etfFlow} layout="vertical" margin={{ left:0, right:30 }}>
            <XAxis type="number" tick={{ fill:T.textMuted, fontSize:9, fontFamily:FONT.sans }} axisLine={false} tickLine={false} />
            <YAxis dataKey="name" type="category" tick={{ fill:T.textSub, fontSize:10 }} axisLine={false} tickLine={false} width={100} />
            <Tooltip contentStyle={tt} formatter={v=>[`${v>0?'+':''}${v}B$`,'Net Flow']} />
            <ReferenceLine x={0} stroke={T.borderHi} />
            <Bar dataKey="flow" radius={[0,3,3,0]} maxBarSize={16}>
              {etfFlow.map((e,i) => <Cell key={i} fill={e.flow>0?T.up:T.down} fillOpacity={0.7} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
        <div style={{ fontSize:9, color:T.textMuted, marginTop:6 }}>※ 유입 섹터 종목에 Layer 3 보너스 점수 적용 (설계서 4.4)</div>
      </Card>
    </div>
  );
}