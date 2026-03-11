/**
 * NlpSignalTab.jsx  —  Layer 2: 텍스트·감성 신호 (NLP / AI)
 *
 * 설계서 v2.0 반영 항목:
 *  ✅ 뉴스 Sentiment (FinBERT, 이벤트 태깅)
 *  ✅ 애널리스트 Revision (EPS 상향/하향 비율, Upgrade/Downgrade 이력) ← 기존 누락
 *  ✅ 내부자거래 Signal (SEC Form 4, CEO 20%↑ 매도 경보 로직)
 *  ✅ Earnings Call Tone (CEO/CFO 발언 분기별 Tone 점수)
 *
 * 디자인: Bloomberg Terminal × Seeking Alpha — 단색 위주, 데이터 밀도 우선
 */
import React, { useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine,
  AreaChart, Area, Cell, ComposedChart, Line,
  RadarChart, PolarGrid, PolarAngleAxis, Radar,
} from 'recharts';
import { C, FONT } from '../styles/tokens';

/* ─────────────────────────────────────────────
   Design Tokens
───────────────────────────────────────────── */
const T = {
  bg:       '#0a0a0a',
  surface:  '#0f0f0f',
  card:     '#111111',
  border:   '#1e1e1e',
  borderHi: '#2a2a2a',
  text:     '#e2e2e2',
  textSub:  '#888888',
  textMuted:'#444444',
  accent:   '#D85604',
  up:       '#22c55e',
  down:     '#ef4444',
  neutral:  '#a0a0a0',
  l2:       '#9b59b6',
};

const tt = { backgroundColor:'#111', border:`1px solid #2a2a2a`, borderRadius:2, fontSize:10, color:'#e2e2e2', fontFamily:FONT.sans, padding:'7px 12px' };

/* ─────────────────────────────────────────────
   공용 컴포넌트
───────────────────────────────────────────── */
const SL = ({ children, right }) => (
  <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:14 }}>
    <span style={{ fontSize:9, fontWeight:700, letterSpacing:2, color:T.textMuted, textTransform:'uppercase', fontFamily:FONT.sans }}>{children}</span>
    {right && <span style={{ fontSize:9, color:T.textMuted, fontFamily:FONT.sans }}>{right}</span>}
  </div>
);

const Card = ({ children, style = {} }) => (
  <div style={{ background:T.card, border:`1px solid ${T.border}`, borderRadius:2, padding:'18px 20px', ...style }}>
    {children}
  </div>
);

const MiniBar = ({ val, max = 100, color = T.accent }) => (
  <div style={{ height:2, background:T.borderHi, borderRadius:1 }}>
    <div style={{ width:`${Math.min(val/max,1)*100}%`, height:'100%', background:color }} />
  </div>
);

const Badge = ({ children, color }) => (
  <span style={{ fontSize:9, fontWeight:800, padding:'2px 6px', borderRadius:2,
    background:`${color}18`, color, border:`1px solid ${color}35`, letterSpacing:0.5, fontFamily:FONT.sans, whiteSpace:'nowrap' }}>
    {children}
  </span>
);

const PhaseTag = ({ n }) => (
  <span style={{ fontSize:9, color: n===2 ? '#f59e0b88' : T.textMuted, fontFamily:FONT.sans }}>P{n}</span>
);

const TH = ({ children, right }) => (
  <th style={{ padding:'7px 14px', textAlign: right ? 'right' : 'left', fontSize:9,
    color:T.textMuted, fontWeight:700, letterSpacing:1.5, textTransform:'uppercase', fontFamily:FONT.sans }}>
    {children}
  </th>
);
const TD = ({ children, style = {} }) => (
  <td style={{ padding:'10px 14px', fontSize:11, color:T.textSub, ...style }}>{children}</td>
);

/* ═══════════════════════════════════════════
   SUBTAB 네비게이터
═══════════════════════════════════════════ */
const SUBTABS = [
  { id:'OVERVIEW',    label:'Overview'          },
  { id:'NEWS',        label:'News Sentiment'    },
  { id:'ANALYST',     label:'Analyst Revision'  },
  { id:'INSIDER',     label:'Insider Flow'      },
  { id:'TRANSCRIPT',  label:'Earnings Call'     },
];

export default function NlpSignalTab() {
  const { ticker } = useOutletContext();
  const [tab, setTab] = useState('OVERVIEW');
  return (
    <div style={{ fontFamily:FONT.sans, color:T.text }}>

      {/* Layer 2 헤더 */}
      <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between',
        padding:'9px 14px', background:T.surface, border:`1px solid ${T.border}`,
        borderLeft:`3px solid ${T.l2}`, marginBottom:14 }}>
        <div style={{ display:'flex', alignItems:'center', gap:12 }}>
          <span style={{ fontSize:9, fontWeight:800, color:T.l2, letterSpacing:2, fontFamily:FONT.sans }}>LAYER 2</span>
          <span style={{ width:1, height:12, background:T.border, display:'inline-block' }} />
          <span style={{ fontSize:11, color:T.textSub }}>텍스트·감성 신호 (NLP / AI)</span>
          <span style={{ fontSize:9, color:T.textMuted, fontFamily:FONT.sans }}>· 가중치 25%</span>
        </div>
        <span style={{ fontSize:9, color:T.textMuted, fontFamily:FONT.sans }}>뉴스 매일 / 내부자 T+2 / 어닝콜 분기</span>
      </div>

      {/* 서브탭 */}
      <div style={{ display:'flex', borderBottom:`1px solid ${T.border}`, marginBottom:20 }}>
        {SUBTABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)} style={{
            padding:'9px 16px', background:'none', border:'none',
            borderBottom: tab === t.id ? `2px solid ${T.accent}` : '2px solid transparent',
            color: tab === t.id ? T.text : T.textMuted,
            fontSize:11, fontWeight: tab === t.id ? 700 : 400,
            cursor:'pointer', transition:'color 0.12s',
            position:'relative', top:1,
          }}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'OVERVIEW'   && <OverviewTab  ticker={ticker} />}
      {tab === 'NEWS'       && <NewsTab      ticker={ticker} />}
      {tab === 'ANALYST'    && <AnalystTab   ticker={ticker} />}
      {tab === 'INSIDER'    && <InsiderTab   ticker={ticker} />}
      {tab === 'TRANSCRIPT' && <TranscriptTab ticker={ticker} />}
    </div>
  );
}

/* ═══════════════════════════════════════════
   1. OVERVIEW
═══════════════════════════════════════════ */
function OverviewTab() {
  const radar = [
    { axis:'News',     score:82 },
    { axis:'Analyst',  score:74 },
    { axis:'Insider',  score:91 },
    { axis:'Earnings', score:56 },
    { axis:'Social',   score:63 },
  ];
  const rows = [
    { label:'FinBERT News Sentiment', score:82, sig:'BULLISH',    color:T.up,      phase:2, note:'최근 30일 평균 감성 +0.61' },
    { label:'Analyst Revision',       score:74, sig:'POSITIVE',   color:'#f59e0b', phase:2, note:'EPS 상향 67% · Upgrade +2건(90일)' },
    { label:'SEC Insider Flow',        score:91, sig:'STRONG BUY', color:T.up,      phase:2, note:'CEO+CFO 동시 매수 포착' },
    { label:'Earnings Call Tone',      score:56, sig:'NEUTRAL',    color:T.neutral, phase:3, note:'Management Tone 중립' },
    { label:'Social Momentum',         score:63, sig:'WATCH',      color:'#f59e0b', phase:3, note:'Google Trends +140% (주간)' },
  ];
  return (
    <div style={{ display:'grid', gridTemplateColumns:'340px 1fr', gap:16 }}>
      <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
        <Card>
          <SL right={`L2 COMPOSITE`}>LAYER 2 SCORE</SL>
          <div style={{ display:'flex', alignItems:'flex-end', gap:14, marginBottom:18 }}>
            <div style={{ fontSize:68, fontWeight:900, color:T.text, fontFamily:FONT.sans, lineHeight:1 }}>74</div>
            <div style={{ paddingBottom:6 }}>
              <div style={{ fontSize:9, color:T.up, fontWeight:700, letterSpacing:1, marginBottom:3 }}>▲ BULLISH CONVICTION</div>
              <div style={{ fontSize:9, color:T.textMuted, fontFamily:FONT.sans }}>100점 만점 · 상위 28%ile</div>
            </div>
          </div>
          <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
            {rows.map(r => (
              <div key={r.label}>
                <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:4 }}>
                  <div style={{ display:'flex', alignItems:'center', gap:6 }}>
                    <span style={{ fontSize:10, color:T.textSub }}>{r.label}</span>
                    <PhaseTag n={r.phase} />
                  </div>
                  <div style={{ display:'flex', alignItems:'center', gap:7 }}>
                    <Badge color={r.color}>{r.sig}</Badge>
                    <span style={{ fontSize:12, fontWeight:700, color:r.color, fontFamily:FONT.sans, minWidth:22, textAlign:'right' }}>{r.score}</span>
                  </div>
                </div>
                <MiniBar val={r.score} color={r.color} />
                <div style={{ fontSize:9, color:T.textMuted, marginTop:2 }}>{r.note}</div>
              </div>
            ))}
          </div>
        </Card>
        <Card>
          <SL>HIGH CONVICTION CONDITIONS</SL>
          {[
            { met:true,  label:'애널리스트 Upgrade 2건 이상 (90일)' },
            { met:true,  label:'CEO 내부자 매수 존재' },
            { met:null,  label:'VIX < 25 (Phase 3)' },
            { met:null,  label:'섹터 ETF 자금 유입 (Phase 3)' },
          ].map(r => (
            <div key={r.label} style={{ display:'flex', alignItems:'center', gap:8, padding:'6px 0', borderBottom:`1px solid ${T.border}22` }}>
              <span style={{ fontSize:12, color: r.met == null ? T.textMuted : r.met ? T.up : T.down }}>
                {r.met == null ? '◦' : r.met ? '✓' : '✗'}
              </span>
              <span style={{ fontSize:10, color: r.met == null ? T.textMuted : T.textSub }}>{r.label}</span>
            </div>
          ))}
        </Card>
      </div>

      <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
        <Card>
          <SL right="5-FACTOR NLP RADAR">SIGNAL DISTRIBUTION</SL>
          <ResponsiveContainer width="100%" height={260}>
            <RadarChart data={radar}>
              <PolarGrid stroke={T.borderHi} />
              <PolarAngleAxis dataKey="axis" tick={{ fill:T.textMuted, fontSize:10, fontFamily:FONT.sans }} />
              <Radar name="L2 Score" dataKey="score" stroke={T.accent} fill={T.accent} fillOpacity={0.1} strokeWidth={1.5} />
              <Tooltip contentStyle={tt} formatter={v => [`${v}점`,'Score']} />
            </RadarChart>
          </ResponsiveContainer>
        </Card>
        <Card>
          <SL>SIGNAL INTERPRETATION</SL>
          <p style={{ fontSize:12, color:T.textSub, lineHeight:1.85, margin:'0 0 12px 0' }}>
            Layer 2 종합 <strong style={{ color:T.text }}>74점</strong>은 Bullish Conviction 구간입니다.
            내부자거래(91점)가 가장 강력한 근거를 제공하며 CEO·CFO 동시 매수 이벤트가 포착됐습니다.
            어닝콜 Tone(56점, Phase 3)은 중립 수준으로 단기 관망 병행을 권장합니다.
          </p>
          <div style={{ padding:'9px 12px', background:T.surface, borderLeft:`2px solid ${T.up}`, fontSize:11, color:T.textSub, lineHeight:1.7 }}>
            <strong style={{ color:T.text }}>High Conviction 2/4 충족</strong> —
            Upgrade 2건 + CEO 매수 동시 조건 충족. 설계서 Strong Buy 발동 조건 근접.
          </div>
        </Card>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════
   2. NEWS — FinBERT 감성 + 이벤트 태깅
═══════════════════════════════════════════ */
function NewsTab() {
  const trend = [
    { d:'03/01', s:0.32 },{ d:'03/02', s:0.45 },{ d:'03/03', s:-0.12 },
    { d:'03/04', s:0.68 },{ d:'03/05', s:0.72 },{ d:'03/06', s:0.85 },{ d:'03/07', s:0.61 },
  ];
  const news = [
    { src:'Bloomberg',     time:'2h',  event:'Earnings Beat', score:+0.94, title:'Blackwell chip orders exceed production capacity by 3x' },
    { src:'SEC EDGAR',     time:'5h',  event:'Buyback',       score:+0.82, title:'Form 8-K: $25B share repurchase program authorized' },
    { src:'Reuters',       time:'8h',  event:'Regulatory',    score:-0.45, title:'New AI chip export restrictions under consideration' },
    { src:'WSJ',           time:'1d',  event:'Partnership',   score:+0.71, title:'Strategic AWS deal expands CUDA cloud infrastructure' },
    { src:'FT',            time:'1d',  event:'Guidance',      score:+0.56, title:'Management raises FY2025 revenue guidance by 12%' },
    { src:'Seeking Alpha', time:'2d',  event:'Management',    score:-0.23, title:'COO departure raises execution risk questions' },
  ];
  const dist = [
    { label:'Very Positive', v:28, c:T.up },
    { label:'Positive',      v:35, c:'#86efac' },
    { label:'Neutral',       v:22, c:T.textMuted },
    { label:'Negative',      v:10, c:'#fca5a5' },
    { label:'Very Negative', v:5,  c:T.down },
  ];
  return (
    <div style={{ display:'flex', flexDirection:'column', gap:16 }}>
      <div style={{ display:'grid', gridTemplateColumns:'1fr 280px', gap:16 }}>
        <Card>
          <SL right="FinBERT · 7일">SENTIMENT INTENSITY TREND</SL>
          <ResponsiveContainer width="100%" height={170}>
            <ComposedChart data={trend} margin={{ left:-20, right:0, top:4, bottom:0 }}>
              <XAxis dataKey="d" tick={{ fill:T.textMuted, fontSize:9, fontFamily:FONT.sans }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill:T.textMuted, fontSize:9, fontFamily:FONT.sans }} axisLine={false} tickLine={false} domain={[-1,1]} />
              <Tooltip contentStyle={tt} formatter={v => [v.toFixed(2),'Sentiment']} />
              <ReferenceLine y={0} stroke={T.borderHi} strokeDasharray="3 3" />
              <Bar dataKey="s" maxBarSize={22} radius={[2,2,0,0]}>
                {trend.map((e,i) => <Cell key={i} fill={e.s>=0 ? T.up : T.down} fillOpacity={0.65} />)}
              </Bar>
              <Line type="monotone" dataKey="s" stroke={T.accent} strokeWidth={1.5} dot={false} strokeDasharray="4 2" />
            </ComposedChart>
          </ResponsiveContainer>
        </Card>
        <Card>
          <SL>DISTRIBUTION</SL>
          <div style={{ display:'flex', flexDirection:'column', gap:9 }}>
            {dist.map(d => (
              <div key={d.label}>
                <div style={{ display:'flex', justifyContent:'space-between', marginBottom:3 }}>
                  <span style={{ fontSize:10, color:T.textSub }}>{d.label}</span>
                  <span style={{ fontSize:10, fontWeight:700, color:d.c, fontFamily:FONT.sans }}>{d.v}%</span>
                </div>
                <MiniBar val={d.v} max={40} color={d.c} />
              </div>
            ))}
            <div style={{ paddingTop:8, borderTop:`1px solid ${T.border}`, fontSize:9, color:T.textMuted }}>
              FinBERT F1 ≈ 0.87 (금융 특화)
            </div>
          </div>
        </Card>
      </div>

      <Card style={{ padding:0 }}>
        <div style={{ padding:'12px 20px', borderBottom:`1px solid ${T.border}` }}>
          <SL right="Finnhub API">AI ANALYZED NEWS FEED</SL>
        </div>
        <table style={{ width:'100%', borderCollapse:'collapse' }}>
          <thead>
            <tr style={{ borderBottom:`1px solid ${T.border}` }}>
              <TH>Source</TH><TH>Time</TH><TH>Event</TH><TH>Headline</TH><TH right>Score</TH>
            </tr>
          </thead>
          <tbody>
            {news.map((n,i) => (
              <tr key={i} style={{ borderBottom:`1px solid ${T.border}22`, background:i%2?T.surface:'transparent' }}>
                <TD style={{ color:T.accent, fontWeight:700, fontFamily:FONT.sans, whiteSpace:'nowrap' }}>{n.src}</TD>
                <TD style={{ color:T.textMuted, fontFamily:FONT.sans, whiteSpace:'nowrap' }}>{n.time} ago</TD>
                <TD><Badge color={n.score>0.5?T.up:n.score<0?T.down:T.neutral}>{n.event}</Badge></TD>
                <TD style={{ lineHeight:1.5 }}>{n.title}</TD>
                <TD style={{ fontWeight:800, fontFamily:FONT.sans, textAlign:'right', color:n.score>0?T.up:T.down, whiteSpace:'nowrap' }}>
                  {n.score>0?'+':''}{n.score.toFixed(2)}
                </TD>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

/* ═══════════════════════════════════════════
   3. ANALYST — EPS Revision + Rating Actions
   (설계서 Layer 2 필수 항목 — 기존 누락)
═══════════════════════════════════════════ */
function AnalystTab() {
  const revTrend = [
    { q:"Q1'24", up:5, dn:2 },{ q:"Q2'24", up:4, dn:3 },
    { q:"Q3'24", up:8, dn:1 },{ q:"Q4'24", up:11,dn:2 },{ q:"Q1'25", up:14,dn:3 },
  ];
  const eps = [
    { p:'FY2025E EPS',  cur:11.93, prior:11.20, chg:+6.5 },
    { p:'FY2026E EPS',  cur:15.40, prior:14.10, chg:+9.2 },
    { p:'Revenue FY25 (B)', cur:128.5,prior:121.0,chg:+6.2 },
    { p:'Revenue FY26 (B)', cur:162.0,prior:148.5,chg:+9.1 },
  ];
  const actions = [
    { firm:'Goldman Sachs', date:'2025-03-01', action:'UPGRADE',   from:'Neutral',    to:'Buy',         tp:'$1,100' },
    { firm:'Morgan Stanley',date:'2025-02-28', action:'REITERATE', from:'Overweight', to:'Overweight',  tp:'$1,050' },
    { firm:'JP Morgan',     date:'2025-02-25', action:'UPGRADE',   from:'Neutral',    to:'Overweight',  tp:'$980' },
    { firm:'Bernstein',     date:'2025-02-20', action:'INITIATE',  from:'-',          to:'Outperform',  tp:'$960' },
    { firm:'HSBC',          date:'2025-02-15', action:'DOWNGRADE', from:'Buy',        to:'Hold',        tp:'$800' },
    { firm:'BofA',          date:'2025-02-10', action:'REITERATE', from:'Buy',        to:'Buy',         tp:'$1,000' },
  ];
  const ac = a => a==='UPGRADE'?T.up:a==='DOWNGRADE'?T.down:T.textMuted;

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:16 }}>
      {/* 상단 3열 스코어카드 */}
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr 1fr', gap:16 }}>
        <Card>
          <SL>CONSENSUS (26명)</SL>
          {[{ l:'Strong Buy / Buy', v:18, c:T.up },{ l:'Hold / Neutral', v:7, c:T.neutral },{ l:'Sell', v:1, c:T.down }].map(d => (
            <div key={d.l} style={{ marginBottom:9 }}>
              <div style={{ display:'flex', justifyContent:'space-between', marginBottom:3 }}>
                <span style={{ fontSize:10, color:T.textSub }}>{d.l}</span>
                <span style={{ fontSize:12, fontWeight:700, color:d.c, fontFamily:FONT.sans }}>{d.v}명</span>
              </div>
              <MiniBar val={d.v} max={20} color={d.c} />
            </div>
          ))}
          <div style={{ paddingTop:10, borderTop:`1px solid ${T.border}`, marginTop:4 }}>
            <div style={{ fontSize:9, color:T.textMuted }}>Consensus</div>
            <div style={{ fontSize:20, fontWeight:900, color:T.up, fontFamily:FONT.sans }}>BUY 69%</div>
          </div>
        </Card>

        <Card style={{ textAlign:'center' }}>
          <SL right="90일">REVISION MOMENTUM</SL>
          <div style={{ fontSize:52, fontWeight:900, color:T.up, fontFamily:FONT.sans, lineHeight:1, marginTop:8 }}>74</div>
          <div style={{ fontSize:9, color:T.up, letterSpacing:1.5, marginTop:8 }}>▲ POSITIVE REVISION</div>
          <div style={{ fontSize:10, color:T.textMuted, marginTop:4 }}>EPS 상향 67% · 하향 13%</div>
          <div style={{ marginTop:14, padding:'8px', background:T.surface, borderRadius:2, textAlign:'left' }}>
            <div style={{ fontSize:10, color:T.textSub }}>Upgrade 2건↑ (90일)</div>
            <div style={{ fontSize:9, color:T.up, marginTop:2 }}>✓ Strong Buy 조건 충족</div>
          </div>
        </Card>

        <Card>
          <SL>12M PRICE TARGET</SL>
          <div style={{ textAlign:'center', padding:'4px 0 8px' }}>
            <div style={{ fontSize:9, color:T.textMuted, marginBottom:4 }}>컨센서스 목표가</div>
            <div style={{ fontSize:38, fontWeight:900, fontFamily:FONT.sans }}>$984</div>
            <div style={{ fontSize:11, color:T.up, fontWeight:700 }}>현재가 대비 +12.4%</div>
          </div>
          <div style={{ borderTop:`1px solid ${T.border}`, paddingTop:10 }}>
            {[['High','$1,100'],['Median','$984'],['Low','$800']].map(([k,v]) => (
              <div key={k} style={{ display:'flex', justifyContent:'space-between', marginBottom:5 }}>
                <span style={{ fontSize:10, color:T.textMuted }}>{k}</span>
                <span style={{ fontSize:11, fontFamily:FONT.sans, fontWeight:700 }}>{v}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16 }}>
        <Card>
          <SL right="분기별">UPGRADE vs DOWNGRADE</SL>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={revTrend} margin={{ left:-20, right:0 }}>
              <XAxis dataKey="q" tick={{ fill:T.textMuted, fontSize:9, fontFamily:FONT.sans }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill:T.textMuted, fontSize:9, fontFamily:FONT.sans }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={tt} />
              <Bar dataKey="up" name="Upgrade"   fill={T.up}   fillOpacity={0.7} maxBarSize={22} radius={[2,2,0,0]} />
              <Bar dataKey="dn" name="Downgrade" fill={T.down} fillOpacity={0.6} maxBarSize={22} radius={[2,2,0,0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>

        <Card style={{ padding:0 }}>
          <div style={{ padding:'12px 18px', borderBottom:`1px solid ${T.border}` }}>
            <SL>EPS ESTIMATE REVISION</SL>
          </div>
          <table style={{ width:'100%', borderCollapse:'collapse' }}>
            <thead>
              <tr style={{ borderBottom:`1px solid ${T.border}` }}>
                <TH>Period</TH><TH right>Current</TH><TH right>Prior</TH><TH right>Δ</TH>
              </tr>
            </thead>
            <tbody>
              {eps.map((r,i) => (
                <tr key={i} style={{ borderBottom:`1px solid ${T.border}22`, background:i%2?T.surface:'transparent' }}>
                  <TD>{r.p}</TD>
                  <TD style={{ textAlign:'right', fontWeight:700, fontFamily:FONT.sans }}>{r.cur}</TD>
                  <TD style={{ textAlign:'right', color:T.textMuted, fontFamily:FONT.sans }}>{r.prior}</TD>
                  <TD style={{ textAlign:'right', fontWeight:700, fontFamily:FONT.sans, color:T.up }}>+{r.chg}%</TD>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>

      <Card style={{ padding:0 }}>
        <div style={{ padding:'12px 18px', borderBottom:`1px solid ${T.border}` }}>
          <SL right="FMP API · Phase 2">ANALYST RATING ACTIONS</SL>
        </div>
        <table style={{ width:'100%', borderCollapse:'collapse' }}>
          <thead>
            <tr style={{ borderBottom:`1px solid ${T.border}` }}>
              <TH>Firm</TH><TH>Date</TH><TH>Action</TH><TH>From</TH><TH>To</TH><TH right>Target</TH>
            </tr>
          </thead>
          <tbody>
            {actions.map((r,i) => (
              <tr key={i} style={{ borderBottom:`1px solid ${T.border}22`, background:i%2?T.surface:'transparent' }}>
                <TD style={{ fontWeight:600, color:T.text }}>{r.firm}</TD>
                <TD style={{ color:T.textMuted, fontFamily:FONT.sans }}>{r.date}</TD>
                <TD><Badge color={ac(r.action)}>{r.action}</Badge></TD>
                <TD style={{ color:T.textMuted }}>{r.from}</TD>
                <TD style={{ fontWeight:700, color:ac(r.action) }}>{r.to}</TD>
                <TD style={{ fontWeight:700, fontFamily:FONT.sans, textAlign:'right' }}>{r.tp}</TD>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

/* ═══════════════════════════════════════════
   4. INSIDER — SEC Form 4
═══════════════════════════════════════════ */
function InsiderTab() {
  const flow = [
    { m:'Oct', buy:4.2, sell:0.8 },{ m:'Nov', buy:2.1, sell:1.4 },
    { m:'Dec', buy:6.8, sell:0.3 },{ m:'Jan', buy:3.5, sell:2.1 },
    { m:'Feb', buy:5.3, sell:0.9 },{ m:'Mar', buy:4.1, sell:0.5 },
  ];
  const trades = [
    { name:'Jensen Huang',   role:'CEO',      type:'PURCHASE', shares:'12,000', val:'$4.2M', date:'2025-03-05', note:'임원진 집단 매수 ★★★★★' },
    { name:'Colette Kress',  role:'CFO',      type:'PURCHASE', shares:'4,200',  val:'$1.1M', date:'2025-03-02', note:'' },
    { name:'Mark Stevens',   role:'Director', type:'PURCHASE', shares:'3,100',  val:'$0.8M', date:'2025-02-28', note:'3명 동시 = 내부 저평가 인식' },
    { name:'Harvey C. Jones',role:'Director', type:'SALE',     shares:'700',    val:'$0.2M', date:'2025-02-20', note:'세금 목적 (D코드)' },
  ];
  return (
    <div style={{ display:'flex', flexDirection:'column', gap:16 }}>
      <div style={{ display:'grid', gridTemplateColumns:'1fr 260px', gap:16 }}>
        <Card>
          <SL right="6개월">INSIDER NET FLOW (M$)</SL>
          <ResponsiveContainer width="100%" height={190}>
            <BarChart data={flow} margin={{ left:-20, right:0 }}>
              <XAxis dataKey="m" tick={{ fill:T.textMuted, fontSize:9, fontFamily:FONT.sans }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill:T.textMuted, fontSize:9, fontFamily:FONT.sans }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={tt} formatter={(v,n) => [`$${v}M`,n]} />
              <Bar dataKey="buy"  name="Buy"  fill={T.up}   fillOpacity={0.65} maxBarSize={26} radius={[2,2,0,0]} />
              <Bar dataKey="sell" name="Sell" fill={T.down} fillOpacity={0.5}  maxBarSize={26} radius={[2,2,0,0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
        <Card>
          <SL>CONVICTION SCORE</SL>
          <div style={{ textAlign:'center', padding:'10px 0' }}>
            <div style={{ fontSize:52, fontWeight:900, color:T.up, fontFamily:FONT.sans, lineHeight:1 }}>91</div>
            <div style={{ fontSize:9, color:T.up, letterSpacing:1.5, marginTop:8 }}>STRONG CONVICTION</div>
          </div>
          <div style={{ borderTop:`1px solid ${T.border}`, paddingTop:10, marginTop:8 }}>
            {[['임원진 집단 매수','3명 동시',true],['CEO 대규모 매도','없음',false],
              ['신뢰도','★★★★★',null],['소스','SEC Form 4',null]].map(([k,v,a]) => (
              <div key={k} style={{ display:'flex', justifyContent:'space-between', marginBottom:5 }}>
                <span style={{ fontSize:9, color:T.textMuted }}>{k}</span>
                <span style={{ fontSize:9, fontWeight:700, fontFamily:FONT.sans, color:a===true?T.up:a===false?T.neutral:T.text }}>{v}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Card style={{ padding:0 }}>
        <div style={{ padding:'12px 18px', borderBottom:`1px solid ${T.border}`, display:'flex', justifyContent:'space-between', alignItems:'center' }}>
          <SL>SEC FORM 4 RECENT TRADES</SL>
        </div>
        <div style={{ padding:'8px 18px', background:'#0a0a0a', borderBottom:`1px solid ${T.border}`,
          fontSize:9, color:T.textMuted, fontFamily:FONT.sans }}>
          ⚡ ALERT: CEO 지분 20%↑ 매도 감지 시 Layer 2 단독 경보 발동 (설계서 기준). 현재 미감지.
        </div>
        <table style={{ width:'100%', borderCollapse:'collapse' }}>
          <thead>
            <tr style={{ borderBottom:`1px solid ${T.border}` }}>
              <TH>Name</TH><TH>Role</TH><TH>Type</TH><TH right>Shares</TH><TH right>Value</TH><TH>Date</TH><TH>Note</TH>
            </tr>
          </thead>
          <tbody>
            {trades.map((t,i) => (
              <tr key={i} style={{ borderBottom:`1px solid ${T.border}22`, background:i%2?T.surface:'transparent' }}>
                <TD style={{ fontWeight:600, color:T.text }}>{t.name}</TD>
                <TD style={{ color:T.textMuted }}>{t.role}</TD>
                <TD><Badge color={t.type==='PURCHASE'?T.up:T.down}>{t.type}</Badge></TD>
                <TD style={{ textAlign:'right', fontFamily:FONT.sans }}>{t.shares}</TD>
                <TD style={{ textAlign:'right', fontWeight:700, fontFamily:FONT.sans, color:t.type==='PURCHASE'?T.up:T.down }}>{t.val}</TD>
                <TD style={{ color:T.textMuted, fontFamily:FONT.sans }}>{t.date}</TD>
                <TD style={{ color:T.textMuted, fontSize:10 }}>{t.note}</TD>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

/* ═══════════════════════════════════════════
   5. TRANSCRIPT — 어닝콜 Tone (Phase 3)
═══════════════════════════════════════════ */
function TranscriptTab() {
  const toneRadar = [
    { axis:'Growth Optimism', A:88, B:72 },{ axis:'Cost Control', A:62, B:68 },
    { axis:'Guidance Tone',   A:75, B:60 },{ axis:'Stability',    A:55, B:71 },
    { axis:'Capex Confidence',A:92, B:65 },
  ];
  const qHist = [
    { q:"Q1'24", ceo:62, cfo:70 },{ q:"Q2'24", ceo:68, cfo:72 },
    { q:"Q3'24", ceo:74, cfo:69 },{ q:"Q4'24", ceo:88, cfo:82 },
  ];
  return (
    <div style={{ display:'flex', flexDirection:'column', gap:16 }}>
      <div style={{ padding:'9px 14px', background:T.surface, border:`1px solid #f59e0b40`,
        borderLeft:`3px solid #f59e0b`, fontSize:9, color:'#f59e0b', fontFamily:FONT.sans }}>
        ⚙ Phase 3 기능 — Claude/GPT API + FMP Earnings Call Transcript. 현재 Mock 데이터.
      </div>

      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16 }}>
        <Card>
          <SL right="Q4'24 vs Q3'24">TONE SHIFT RADAR</SL>
          <ResponsiveContainer width="100%" height={250}>
            <RadarChart data={toneRadar}>
              <PolarGrid stroke={T.borderHi} />
              <PolarAngleAxis dataKey="axis" tick={{ fill:T.textMuted, fontSize:9, fontFamily:FONT.sans }} />
              <Radar name="Q4'24" dataKey="A" stroke={T.accent} fill={T.accent} fillOpacity={0.1} strokeWidth={1.5} />
              <Radar name="Q3'24" dataKey="B" stroke={T.borderHi} fill="none" strokeWidth={1} strokeDasharray="4 2" />
              <Tooltip contentStyle={tt} />
            </RadarChart>
          </ResponsiveContainer>
        </Card>

        <Card>
          <SL>AI TRANSCRIPT INSIGHTS</SL>
          <div style={{ display:'flex', flexDirection:'column', gap:14, marginBottom:16 }}>
            <div style={{ borderLeft:`2px solid ${T.up}`, paddingLeft:12 }}>
              <div style={{ fontSize:9, fontWeight:800, color:T.up, letterSpacing:1.5, marginBottom:4, fontFamily:FONT.sans }}>BULLISH SIGNAL</div>
              <div style={{ fontSize:11, color:T.textSub, lineHeight:1.75 }}>
                Jensen Huang CEO가 AI 인프라 수요를 'unprecedented'로 12회 언급. 역대 어닝콜 최고 낙관 Tone 기록. Blackwell GPU 수요가 공급 초과 상황을 구체 수치와 함께 강조.
              </div>
            </div>
            <div style={{ borderLeft:`2px solid ${T.down}`, paddingLeft:12 }}>
              <div style={{ fontSize:9, fontWeight:800, color:T.down, letterSpacing:1.5, marginBottom:4, fontFamily:FONT.sans }}>RISK FACTOR</div>
              <div style={{ fontSize:11, color:T.textSub, lineHeight:1.75 }}>
                HBM 공급 부족에 따른 리드타임 지연이 잠재 리스크로 언급. CFO 재무 가이던스 언어는 중립~보수적.
              </div>
            </div>
          </div>
          <div style={{ fontSize:9, color:T.textMuted, letterSpacing:1.5, marginBottom:8, fontFamily:FONT.sans }}>KEY PHRASES</div>
          <div style={{ display:'flex', gap:5, flexWrap:'wrap', marginBottom:5 }}>
            {['Blackwell','Sovereign AI','Cloud Capex','HBM3e','unprecedented'].map(w => (
              <span key={w} style={{ fontSize:9, padding:'3px 8px', borderRadius:2,
                background:`${T.up}10`, color:T.up, border:`1px solid ${T.up}30`, fontFamily:FONT.sans }}>{w}</span>
            ))}
          </div>
          <div style={{ display:'flex', gap:5, flexWrap:'wrap' }}>
            {['supply constraints','lead time','execution risk'].map(w => (
              <span key={w} style={{ fontSize:9, padding:'3px 8px', borderRadius:2,
                background:`${T.down}10`, color:T.down, border:`1px solid ${T.down}30`, fontFamily:FONT.sans }}>{w}</span>
            ))}
          </div>
        </Card>
      </div>

      <Card>
        <SL right="CEO·CFO Tone 점수">QUARTERLY TONE HISTORY</SL>
        <ResponsiveContainer width="100%" height={160}>
          <ComposedChart data={qHist} margin={{ left:-20, right:0 }}>
            <XAxis dataKey="q" tick={{ fill:T.textMuted, fontSize:9, fontFamily:FONT.sans }} axisLine={false} tickLine={false} />
            <YAxis domain={[40,100]} tick={{ fill:T.textMuted, fontSize:9, fontFamily:FONT.sans }} axisLine={false} tickLine={false} />
            <Tooltip contentStyle={tt} />
            <Bar dataKey="ceo" name="CEO" fill={T.accent} fillOpacity={0.6} maxBarSize={30} radius={[2,2,0,0]} />
            <Bar dataKey="cfo" name="CFO" fill={T.borderHi} maxBarSize={30} radius={[2,2,0,0]} />
            <Line type="monotone" dataKey="ceo" stroke={T.accent} strokeWidth={1.5} dot={{ fill:T.accent, r:3 }} />
          </ComposedChart>
        </ResponsiveContainer>
      </Card>
    </div>
  );
}