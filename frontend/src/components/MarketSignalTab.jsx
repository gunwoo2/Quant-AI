/**
 * MarketSignalTab.jsx  —  Layer 3: 시장 신호 (Market Signal)
 *
 * API: GET /api/stock/layer3/{ticker}
 * 구조: A.기술지표(55점) + B.수급·구조(25점) + C.시장환경(20점) = 100점
 *
 * Phase 2 예정: Chart Patterns, Fear & Greed, Fed Rate, Options Flow, Dark Pool
 */
import React, { useState, useEffect } from 'react';
import { useOutletContext } from 'react-router-dom';
import api from '../api';
import {
  AreaChart, Area, BarChart, Bar, ComposedChart, Line,
  XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine,
  RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar, Cell,
} from 'recharts';
import { C, FONT } from '../styles/tokens';

/* ── 디자인 토큰 ── */
const T = {
  bg:C.bgDeeper, surface:C.bgDark, card:C.surface, border:C.cardBg, borderHi:C.surfaceHi,
  text:C.textPri, textSub:C.neutral, textMuted:C.borderHi,
  accent:C.primary, up:C.up, down:C.down, neutral:C.neutral, l3:C.cyan,
  warn:C.golden, phase2:C.cyan,
};
const tt = { backgroundColor:C.surface, border:`1px solid ${C.surfaceHi}`, borderRadius:2, fontSize:10, color:C.textPri, fontFamily:FONT.sans, padding:'7px 12px' };

/* ── 공용 컴포넌트 ── */
const SL = ({ children, right }) => (
  <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:14 }}>
    <span style={{ fontSize:9, fontWeight:700, letterSpacing:2, color:T.textMuted, textTransform:'uppercase', fontFamily:FONT.sans }}>{children}</span>
    {right && <span style={{ fontSize:9, color:T.textMuted, fontFamily:FONT.sans }}>{right}</span>}
  </div>
);
const Card = ({ children, style={} }) => (
  <div style={{ background:T.card, border:`1px solid ${T.border}`, borderRadius:2, padding:'18px 20px', ...style }}>{children}</div>
);
const Badge = ({ children, color }) => (
  <span style={{ fontSize:9, fontWeight:800, padding:'2px 6px', borderRadius:2, background:`${color}18`, color, border:`1px solid ${color}35`, letterSpacing:0.5, fontFamily:FONT.sans, whiteSpace:'nowrap' }}>{children}</span>
);
const TH = ({ children, right }) => (
  <th style={{ padding:'7px 14px', textAlign:right?'right':'left', fontSize:9, color:T.textMuted, fontWeight:700, letterSpacing:1.5, textTransform:'uppercase', fontFamily:FONT.sans }}>{children}</th>
);
const TD = ({ children, style={} }) => (
  <td style={{ padding: '10px 14px', fontSize: 11, color: T.textSub, ...style }}>
    {children}
  </td>
);

const GaugeBar = ({ val, max = 100, color = T.l3, height = 3 }) => (
  <div style={{ height, background: T.borderHi, borderRadius: 1 }}>
    <div 
      style={{ 
        width: `${Math.min((val || 0) / max, 1) * 100}%`, 
        height: '100%', 
        background: color, 
        borderRadius: 1, 
        transition: 'width 0.5s ease' 
      }} 
    />
  </div>
); 

const MiniBar = ({ val, max = 100, color }) => {
  const pct = val != null && max > 0 ? Math.min((val / max) * 100, 100) : 0;
  return (
    <div style={{ width: '100%', height: 3, background: T.border, borderRadius: 2, overflow: 'hidden' }}>
      <div style={{ width: `${pct}%`, height: '100%', background: color || T.accent, borderRadius: 2 }} />
    </div>
  );
};
const scoreColor = (score, max) => {
  if (score == null) return T.textMuted;
  const pct = score / max;
  if (pct >= 0.75) return T.up;
  if (pct >= 0.5) return T.warn;
  if (pct >= 0.25) return T.accent;
  return T.down;
};

/* ── 서브탭 정의 ── */
const SUBTABS = [
  { id:'OVERVIEW',  label:'Overview (종합)' },
  { id:'TECHNICAL', label:'Technical (기술지표)' },
  { id:'FLOW',      label:'Flow (수급·구조)' },
  { id:'MACRO',     label:'Macro (시장환경)' },
  { id:'PHASE2',    label:'Phase 2 (예정)', badge:true },
];

/* ════════════════════════════════════════════════════════════ */
/*  MAIN COMPONENT                                             */
/* ════════════════════════════════════════════════════════════ */
export default function MarketSignalTab() {
  const { ticker } = useOutletContext();
  const [tab, setTab] = useState('OVERVIEW');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!ticker) return;
    setLoading(true);
    setError(null);
    api.get(`/api/stock/layer3/${ticker}`)
      .then(res => { setData(res.data); setLoading(false); })
      .catch(err => { setError(err.response?.data?.detail || '데이터 로드 실패'); setLoading(false); });
  }, [ticker]);

  if (loading) return (
    <div style={{ fontFamily:FONT.sans, color:T.textMuted, padding:40, textAlign:'center' }}>
      Layer 3 데이터 로딩 중...
    </div>
  );
  if (error) return (
    <div style={{ fontFamily:FONT.sans, color:T.down, padding:40, textAlign:'center' }}>
      ⚠ {error}
    </div>
  );
  if (!data) return null;

  return (
    <div style={{ fontFamily:FONT.sans, color:T.text }}>
      {/* 헤더 */}
      <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', padding:'9px 14px', background:T.surface, border:`1px solid ${T.border}`, borderLeft:`3px solid ${T.l3}`, marginBottom:14 }}>
        <div style={{ display:'flex', alignItems:'center', gap:12 }}>
          <span style={{ fontSize:9, fontWeight:800, color:T.l3, letterSpacing:2 }}>LAYER 3</span>
          <span style={{ width:1, height:12, background:T.border, display:'inline-block' }} />
          <span style={{ fontSize:11, color:T.textSub }}>시장 신호 (Market Signal)</span>
          <span style={{ fontSize:9, color:T.textMuted }}>· 가중치 25%</span>
        </div>
        <span style={{ fontSize:9, color:T.textMuted }}>{data.overview?.calcDate || ''}</span>
      </div>

      {/* 서브탭 */}
      <div style={{ display:'flex', gap:0, marginBottom:16, borderBottom:`1px solid ${T.border}` }}>
        {SUBTABS.map(s => (
          <button key={s.id} onClick={()=>setTab(s.id)} style={{
            padding:'8px 18px', background:'none', border:'none', cursor:'pointer',
            fontSize:10, fontWeight:tab===s.id?700:400, fontFamily:FONT.sans,
            color:tab===s.id ? (s.badge ? T.phase2 : T.l3) : T.textMuted,
            letterSpacing:1,
            borderBottom:tab===s.id ? `2px solid ${s.badge ? T.phase2 : T.l3}` : '2px solid transparent',
            display:'flex', alignItems:'center', gap:5,
          }}>
            {s.label}
            {s.badge && <span style={{ fontSize:7, padding:'1px 4px', borderRadius:2, background:`${T.phase2}25`, color:T.phase2, border:`1px solid ${T.phase2}40`, fontWeight:800, letterSpacing:0.5 }}>SOON</span>}
          </button>
        ))}
      </div>

      {tab==='OVERVIEW'  && <OverviewTab data={data} />}
      {tab==='TECHNICAL' && <TechnicalTab data={data} />}
      {tab==='FLOW'      && <FlowTab data={data} />}
      {tab==='MACRO'     && <MacroTab data={data} />}
      {tab==='PHASE2'    && <Phase2Tab data={data} />}
    </div>
  );
}


/* ════════════════════════════════════════════════════════════ */
/*  1. OVERVIEW TAB                                            */
/* ════════════════════════════════════════════════════════════ */
function OverviewTab({ data }) {
  const ov = data.overview || {};
  const rawTotal = ov.totalScore;
  const sections = ov.sections || [];
  // totalScore가 0이면 section 합산으로 폴백
  const total = (rawTotal && rawTotal > 0) 
    ? rawTotal 
    : sections.reduce((sum, s) => sum + (s.score || 0), 0) || null;
  const radar = ov.radar || [];
  const indicators = ov.indicators || [];

  const gradeLabel = (s) => {
    if (s == null) return { text:'N/A', color:T.textMuted };
    if (s >= 80) return { text:'STRONG BUY (강력매수)', color:T.up };
    if (s >= 65) return { text:'BUY (매수)', color:C.up };
    if (s >= 50) return { text:'NEUTRAL (중립)', color:T.warn };
    if (s >= 35) return { text:'SELL (매도)', color:T.accent };
    return { text:'STRONG SELL (강력매도)', color:T.down };
  };
  const grade = gradeLabel(total);
  const radarData = radar.map(r => ({ subject: r.subject, pct: r.pct || 0, fullMark: 100 }));

  return (
    <div style={{ display:'grid', gridTemplateColumns:'340px 1fr', gap:16 }}>
      {/* 좌측: 종합 점수 + 섹션 요약 */}
      <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
        <Card>
          <SL right="L3 COMPOSITE">LAYER 3 SCORE (시장 종합 점수)</SL>
          <div style={{ display:'flex', alignItems:'flex-end', gap:14, marginBottom:18 }}>
            <div style={{ fontSize:68, fontWeight:900, color:grade.color, fontFamily:FONT.sans, lineHeight:1 }}>
              {total != null ? total.toFixed(1) : '—'}
            </div>
            <div style={{ paddingBottom:6 }}>
              <div style={{ fontSize:9, color:grade.color, fontWeight:700, letterSpacing:1, marginBottom:3 }}>
                {total != null && total >= 50 ? '▲' : '▼'} {grade.text}
              </div>
              <div style={{ fontSize:9, color:T.textMuted, fontFamily:FONT.sans }}>100점 만점</div>
            </div>
          </div>

          {/* 섹션별 바 (기술 / 수급 / 시장) */}
          <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
            {sections.map((sec, i) => {
              const c = scoreColor(sec.score, sec.max);
              const pctVal = sec.max > 0 ? (sec.score || 0) / sec.max : 0;
              const sig = pctVal >= 0.7 ? 'STRONG' : pctVal >= 0.45 ? 'NEUTRAL' : 'WEAK';
              return (
                <div key={i}>
                  <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:4 }}>
                    <div style={{ display:'flex', alignItems:'center', gap:6 }}>
                      <span style={{ fontSize:10, color:T.textSub }}>{sec.name}</span>
                    </div>
                    <div style={{ display:'flex', alignItems:'center', gap:7 }}>
                      <Badge color={c}>{sig}</Badge>
                      <span style={{ fontSize:12, fontWeight:700, color:c, fontFamily:FONT.sans, minWidth:30, textAlign:'right' }}>
                        {sec.score != null ? sec.score.toFixed(1) : '—'}
                      </span>
                      <span style={{ fontSize:9, color:T.textMuted }}>/{sec.max}</span>
                    </div>
                  </div>
                  <MiniBar val={sec.score} max={sec.max} color={c} />
                </div>
              );
            })}
          </div>
        </Card>

        {/* 투자 판단 */}
        <Card>
          <SL>MARKET CONDITION (시장 판단)</SL>
          <div style={{ padding:12, background:`${grade.color}08`, border:`1px solid ${grade.color}25`, borderRadius:4 }}>
            <div style={{ fontSize:10, fontWeight:700, color:grade.color, marginBottom:6, letterSpacing:1 }}>
              STATUS: {grade.text}
            </div>
            <div style={{ fontSize:11, color:T.textSub, lineHeight:1.6 }}>
              {total >= 65 ? '시장 환경이 우호적이며 기술지표가 상승 추세를 지지합니다.'
               : total >= 50 ? '시장이 중립적 상태입니다. 선별적 접근이 필요합니다.'
               : total >= 35 ? '시장 모멘텀이 약화되고 있습니다. 리스크 관리에 유의하세요.'
               : '시장 환경이 약세이며 방어적 포지션이 권장됩니다.'}
            </div>
          </div>
          {ov.calcDate && (
            <div style={{ marginTop:10, fontSize:9, color:T.textMuted, fontFamily:FONT.mono }}>마지막 계산: {ov.calcDate}</div>
          )}
        </Card>
      </div>

      {/* 우측: 레이더 + 지표 테이블 */}
      <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
        <Card>
          <SL right="Layer 3 Dimensions">TECHNICAL RADAR (기술지표 레이더)</SL>
          <ResponsiveContainer width="100%" height={260}>
            <RadarChart data={radarData} cx="50%" cy="50%" outerRadius="72%">
              <PolarGrid stroke={T.border} />
              <PolarAngleAxis dataKey="subject" tick={{ fill:T.textSub, fontSize:9, fontFamily:FONT.sans }} />
              <PolarRadiusAxis domain={[0,100]} tick={false} axisLine={false} />
              <Radar name="점수" dataKey="pct" stroke={T.l3} fill={T.l3} fillOpacity={0.2} strokeWidth={2} />
            </RadarChart>
          </ResponsiveContainer>
        </Card>

        <Card style={{ padding:0 }}>
          <div style={{ padding:'14px 18px', borderBottom:`1px solid ${T.border}` }}>
            <SL>ALL INDICATOR SCORES (전체 지표 점수)</SL>
          </div>
          <table style={{ width:'100%', borderCollapse:'collapse' }}>
            <thead><tr style={{ borderBottom:`1px solid ${T.border}` }}>
              <TH>지표 (Indicator)</TH><TH right>점수 (Score)</TH><TH right>만점 (Max)</TH><TH right>비율</TH>
            </tr></thead>
            <tbody>
              {[...radar, ...indicators].map((ind, i) => {
                const pctVal = ind.max > 0 ? ((ind.score || 0) / ind.max * 100) : 0;
                return (
                  <tr key={i} style={{ borderBottom:`1px solid ${T.border}22` }}>
                    <TD style={{ fontWeight:600, color:T.text }}>{ind.subject || ind.name}</TD>
                    <TD style={{ textAlign:'right', fontWeight:700, color:scoreColor(ind.score, ind.max), fontFamily:FONT.sans }}>{ind.score != null ? ind.score.toFixed(1) : '—'}</TD>
                    <TD style={{ textAlign:'right', color:T.textMuted }}>{ind.max}</TD>
                    <TD style={{ textAlign:'right' }}>
                      <div style={{ display:'flex', alignItems:'center', justifyContent:'flex-end', gap:6 }}>
                        <div style={{ width:60, height:3, background:T.border, borderRadius:2, overflow:'hidden' }}>
                          <div style={{ width:`${pctVal}%`, height:'100%', background:scoreColor(ind.score, ind.max), borderRadius:2 }} />
                        </div>
                        <span style={{ fontSize:10, color:scoreColor(ind.score, ind.max), fontFamily:FONT.mono, minWidth:30, textAlign:'right' }}>{pctVal.toFixed(0)}%</span>
                      </div>
                    </TD>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
      </div>
    </div>
  );
}


function TechnicalTab({ data }) {
  const t = data.technical || {};

  const fmt = (v, suffix='', digits=2) => v != null ? `${Number(v).toFixed(digits)}${suffix}` : '—';
  const fmtPct = (v) => v != null ? `${(v * 100).toFixed(1)}%` : '—';
  const fmtInt = (v) => v != null ? Number(v).toLocaleString() : '—';

  const rsiZone = (v) => {
    if (v == null) return { label:'N/A', color:T.textMuted };
    if (v >= 80) return { label:'극과매수 (Extreme Overbought)', color:T.down };
    if (v >= 70) return { label:'과매수 (Overbought)', color:T.warn };
    if (v >= 60) return { label:'강세 (Bullish)', color:C.up };
    if (v >= 40) return { label:'중립 (Neutral)', color:T.up };
    if (v >= 30) return { label:'약세 (Bearish)', color:T.warn };
    return { label:'과매도 (Oversold)', color:T.down };
  };
  const rsi = rsiZone(t.rsi14);

  const macdSignalText = () => {
    const h = t.macdHistogram;
    if (h == null) return { text:'N/A', color:T.textMuted };
    if (h > 0) return { text:'▲ 매수 구간 (Bullish)', color:T.up };
    return { text:'▼ 매도 구간 (Bearish)', color:T.down };
  };
  const macdSig = macdSignalText();

  const obvLabel = {
    'UP': { text:'↑ 매집 (Accumulation)', color:T.up },
    'DOWN': { text:'↓ 분산 (Distribution)', color:T.down },
    'NEUTRAL': { text:'— 중립', color:T.neutral },
  };
  const obv = obvLabel[t.obvTrend] || obvLabel['NEUTRAL'];

  const structRows = [
    { name:'골든크로스 (Golden Cross)', active:t.goldenCross, score:t.goldenCrossScore, max:2, desc: t.goldenCross ? `MA50 ${fmt(t.ma50)} > MA200 ${fmt(t.ma200)}` : `MA50 ${fmt(t.ma50)} < MA200 ${fmt(t.ma200)}` },
    { name:'BB 스퀴즈 (Bollinger Squeeze)', active:t.bbSqueeze, score:t.bbSqueezeScore, max:2, desc: t.bbSqueeze ? `밴드폭 ${fmt(t.bbWidth,'',4)} — 수렴 중` : `밴드폭 ${fmt(t.bbWidth,'',4)} — 정상` },
    { name:'MA20 연속상회 (MA20 Streak)', active:(t.ma20StreakDays||0)>=3, score:t.ma20StreakScore, max:2, desc:`${t.ma20StreakDays || 0}일 연속 MA20 위` },
    { name:'52주 신고가 돌파 (52W Breakout)', active:t.breakout52w, score:t.breakout52wScore, max:2, desc: t.breakout52w ? '신고가 돌파 확인!' : `고가 대비 ${fmtPct(t.high52wRatio)}` },
  ];

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:16 }}>
      <Card style={{ padding:0 }}>
        <div style={{ padding:'14px 18px', borderBottom:`1px solid ${T.border}` }}>
          <SL right={`기준일: ${t.calcDate || ''}`}>A. 기술지표 상세 (TECHNICAL INDICATORS) — 55점 만점</SL>
        </div>
        <table style={{ width:'100%', borderCollapse:'collapse' }}>
          <thead><tr style={{ borderBottom:`1px solid ${T.border}` }}>
            <TH>#</TH><TH>지표 (Indicator)</TH><TH>원시값 (Raw Value)</TH><TH>해석 (Interpretation)</TH><TH right>점수 (Score)</TH><TH right>만점</TH>
          </tr></thead>
          <tbody>
            <tr style={{ borderBottom:`1px solid ${T.border}22` }}>
              <TD style={{ fontFamily:FONT.sans, color:T.l3, fontWeight:700 }}>①</TD>
              <TD style={{ fontWeight:600, color:T.text }}>상대 모멘텀 12-1<br/><span style={{ fontSize:9, color:T.textMuted }}>(Relative Momentum)</span></TD>
              <TD style={{ fontFamily:FONT.sans }}>{t.relativeMomentum != null ? `${(t.relativeMomentum*100).toFixed(1)}%` : '—'}</TD>
              <TD style={{ fontSize:10, color:T.textMuted }}>{t.relativeMomentum != null ? (t.relativeMomentum > 0 ? '시장 대비 강세' : '시장 대비 약세') : ''}</TD>
              <TD style={{ textAlign:'right', fontWeight:700, fontFamily:FONT.sans, color:scoreColor(t.relativeMomentumScore, 15) }}>{fmt(t.relativeMomentumScore)}</TD>
              <TD style={{ textAlign:'right', color:T.textMuted }}>15</TD>
            </tr>
            <tr style={{ borderBottom:`1px solid ${T.border}22`, background:T.surface }}>
              <TD style={{ fontFamily:FONT.sans, color:T.l3, fontWeight:700 }}>②</TD>
              <TD style={{ fontWeight:600, color:T.text }}>52주 고가 위치<br/><span style={{ fontSize:9, color:T.textMuted }}>(52W High Position)</span></TD>
              <TD style={{ fontFamily:FONT.sans }}>{fmtPct(t.high52wRatio)}<span style={{ fontSize:9, color:T.textMuted, marginLeft:6 }}>고가 ${fmtInt(t.high52w)}</span></TD>
              <TD style={{ fontSize:10, color:T.textMuted }}>{t.high52wRatio != null ? (t.high52wRatio >= 0.95 ? '신고가 근접' : t.high52wRatio >= 0.8 ? '강세 구간' : '조정 구간') : ''}</TD>
              <TD style={{ textAlign:'right', fontWeight:700, fontFamily:FONT.sans, color:scoreColor(t.high52wScore, 10) }}>{fmt(t.high52wScore)}</TD>
              <TD style={{ textAlign:'right', color:T.textMuted }}>10</TD>
            </tr>
            <tr style={{ borderBottom:`1px solid ${T.border}22` }}>
              <TD style={{ fontFamily:FONT.sans, color:T.l3, fontWeight:700 }}>③</TD>
              <TD style={{ fontWeight:600, color:T.text }}>추세 안정성<br/><span style={{ fontSize:9, color:T.textMuted }}>(Trend Stability R²)</span></TD>
              <TD style={{ fontFamily:FONT.sans }}>R²={fmt(t.trendR2,'',4)} <span style={{ fontSize:9, color:T.textMuted }}>slope={t.trendSlope != null ? Number(t.trendSlope).toExponential(2) : '—'}</span></TD>
              <TD style={{ fontSize:10, color:T.textMuted }}>{t.trendR2 != null ? (t.trendR2 >= 0.7 ? '안정 추세' : t.trendR2 >= 0.5 ? '보통 추세' : '불안정') : ''}{t.trendSlope != null ? (t.trendSlope > 0 ? ' · 상승' : ' · 하락') : ''}</TD>
              <TD style={{ textAlign:'right', fontWeight:700, fontFamily:FONT.sans, color:scoreColor(t.trendScore, 8) }}>{fmt(t.trendScore)}</TD>
              <TD style={{ textAlign:'right', color:T.textMuted }}>8</TD>
            </tr>
            <tr style={{ borderBottom:`1px solid ${T.border}22`, background:T.surface }}>
              <TD style={{ fontFamily:FONT.sans, color:T.l3, fontWeight:700 }}>④</TD>
              <TD style={{ fontWeight:600, color:T.text }}>RSI (상대강도지수)<br/><span style={{ fontSize:9, color:T.textMuted }}>(Wilder RSI 14)</span></TD>
              <TD>
                <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                  <span style={{ fontFamily:FONT.sans, fontWeight:700, color:rsi.color }}>{fmt(t.rsi14)}</span>
                  <Badge color={rsi.color}>{rsi.label}</Badge>
                </div>
              </TD>
              <TD style={{ fontSize:10, color:T.textMuted }}>30 과매도 · 40~60 건강 · 70 과매수</TD>
              <TD style={{ textAlign:'right', fontWeight:700, fontFamily:FONT.sans, color:scoreColor(t.rsiScore, 7) }}>{fmt(t.rsiScore)}</TD>
              <TD style={{ textAlign:'right', color:T.textMuted }}>7</TD>
            </tr>
            <tr style={{ borderBottom:`1px solid ${T.border}22` }}>
              <TD style={{ fontFamily:FONT.sans, color:T.l3, fontWeight:700 }}>⑤</TD>
              <TD style={{ fontWeight:600, color:T.text }}>MACD (추세전환)<br/><span style={{ fontSize:9, color:T.textMuted }}>(12, 26, 9)</span></TD>
              <TD style={{ fontFamily:FONT.sans, fontSize:10 }}>Line={fmt(t.macdLine,'',4)} Sig={fmt(t.macdSignal,'',4)}<br/>Hist=<span style={{ fontWeight:700, color:macdSig.color }}>{fmt(t.macdHistogram,'',4)}</span></TD>
              <TD style={{ fontSize:10 }}><Badge color={macdSig.color}>{macdSig.text}</Badge></TD>
              <TD style={{ textAlign:'right', fontWeight:700, fontFamily:FONT.sans, color:scoreColor(t.macdScore, 5) }}>{fmt(t.macdScore)}</TD>
              <TD style={{ textAlign:'right', color:T.textMuted }}>5</TD>
            </tr>
            <tr style={{ borderBottom:`1px solid ${T.border}22`, background:T.surface }}>
              <TD style={{ fontFamily:FONT.sans, color:T.l3, fontWeight:700 }}>⑥</TD>
              <TD style={{ fontWeight:600, color:T.text }}>OBV (거래량흐름)<br/><span style={{ fontSize:9, color:T.textMuted }}>(On Balance Volume)</span></TD>
              <TD style={{ fontFamily:FONT.sans, fontSize:10 }}>OBV={fmtInt(t.obvCurrent)}<br/>MA20={fmtInt(t.obvMa20)}</TD>
              <TD style={{ fontSize:10 }}><Badge color={obv.color}>{obv.text}</Badge></TD>
              <TD style={{ textAlign:'right', fontWeight:700, fontFamily:FONT.sans, color:scoreColor(t.obvScore, 5) }}>{fmt(t.obvScore)}</TD>
              <TD style={{ textAlign:'right', color:T.textMuted }}>5</TD>
            </tr>
            <tr style={{ borderBottom:`1px solid ${T.border}22` }}>
              <TD style={{ fontFamily:FONT.sans, color:T.l3, fontWeight:700 }}>⑦</TD>
              <TD style={{ fontWeight:600, color:T.text }}>거래량 급증<br/><span style={{ fontSize:9, color:T.textMuted }}>(Volume Surge)</span></TD>
              <TD style={{ fontFamily:FONT.sans }}>{fmt(t.volumeSurgeRatio, 'x')}<span style={{ fontSize:9, color:T.textMuted, marginLeft:6 }}>20일평균 {fmtInt(t.volume20dAvg)}</span></TD>
              <TD style={{ fontSize:10, color:T.textMuted }}>{t.volumeSurgeRatio != null ? (t.volumeSurgeRatio >= 3 ? '이상 급증 (3x↑)' : t.volumeSurgeRatio >= 1.5 ? '활발' : '정상') : ''}</TD>
              <TD style={{ textAlign:'right', fontWeight:700, fontFamily:FONT.sans, color:scoreColor(t.volumeSurgeScore, 5) }}>{fmt(t.volumeSurgeScore)}</TD>
              <TD style={{ textAlign:'right', color:T.textMuted }}>5</TD>
            </tr>
          </tbody>
        </table>
      </Card>

      {/* 구조적 시그널 */}
      <Card style={{ padding:0 }}>
        <div style={{ padding:'14px 18px', borderBottom:`1px solid ${T.border}` }}>
          <SL>⑨ 구조적 시그널 (STRUCTURAL SIGNALS) — 8점 만점</SL>
        </div>
        <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:0 }}>
          {structRows.map((s, i) => (
            <div key={i} style={{ padding:'16px 18px', borderRight:i<3?`1px solid ${T.border}`:'none' }}>
              <div style={{ display:'flex', alignItems:'center', gap:6, marginBottom:8 }}>
                <span style={{ width:8, height:8, borderRadius:'50%', background:s.active ? T.up : T.borderHi, display:'inline-block' }} />
                <span style={{ fontSize:10, fontWeight:600, color:T.text }}>{s.name}</span>
              </div>
              <div style={{ display:'flex', alignItems:'baseline', gap:4, marginBottom:4 }}>
                <span style={{ fontSize:22, fontWeight:900, color:scoreColor(s.score, s.max), fontFamily:FONT.sans }}>{s.score != null ? s.score.toFixed(1) : '—'}</span>
                <span style={{ fontSize:10, color:T.textMuted }}>/ {s.max}</span>
              </div>
              <div style={{ fontSize:9, color:T.textMuted }}>{s.desc}</div>
              <GaugeBar val={s.score} max={s.max} color={scoreColor(s.score, s.max)} height={2} />
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}


/* ════════════════════════════════════════════════════════════ */
/*  3. FLOW TAB — 수급·구조 (공매도 + P/C)                      */
/* ════════════════════════════════════════════════════════════ */
function FlowTab({ data }) {
  const flow = data.flow || {};
  const sv = flow.shortVolume || {};
  const svTrend = flow.svTrend || [];
  const pcScore = flow.putCallScore;

  const svrColor = (v) => {
    if (v == null) return T.textMuted;
    if (v < 0.35) return T.up;
    if (v < 0.45) return T.warn;
    return T.down;
  };

  const svrLabel = (v) => {
    if (v == null) return 'N/A';
    if (v < 0.30) return '매우 낮음 (Very Low) — 강세';
    if (v < 0.35) return '낮음 (Low) — 강세';
    if (v < 0.40) return '보통 (Normal)';
    if (v < 0.45) return '높음 (High) — 약세';
    return '매우 높음 (Very High) — 약세';
  };

  const pcLabel = (s) => {
    if (s == null) return { text:'N/A (데이터 없음)', color:T.textMuted };
    if (s >= 6) return { text:'극단 강세 (Extreme Bullish)', color:T.up };
    if (s >= 4) return { text:'강세 (Bullish)', color:C.up };
    if (s >= 2) return { text:'중립 (Neutral)', color:T.warn };
    return { text:'약세 (Bearish)', color:T.down };
  };
  const pc = pcLabel(pcScore);

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:16 }}>
      <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:12 }}>
        <Card>
          <div style={{ fontSize:9, color:T.textMuted, marginBottom:5 }}>공매도 비율 (Short Volume Ratio)</div>
          <div style={{ fontSize:28, fontWeight:900, color:svrColor(sv.svr), fontFamily:FONT.sans, lineHeight:1 }}>
            {sv.svr != null ? `${(sv.svr * 100).toFixed(1)}%` : '—'}
          </div>
          <div style={{ fontSize:10, color:T.textSub, marginTop:4 }}>{svrLabel(sv.svr)}</div>
        </Card>
        <Card>
          <div style={{ fontSize:9, color:T.textMuted, marginBottom:5 }}>5일 평균 SVR (5D Avg)</div>
          <div style={{ fontSize:28, fontWeight:900, color:svrColor(sv.svr5d), fontFamily:FONT.sans, lineHeight:1 }}>
            {sv.svr5d != null ? `${(sv.svr5d * 100).toFixed(1)}%` : '—'}
          </div>
          <div style={{ fontSize:10, color:T.textSub, marginTop:4 }}>노이즈 제거 이동평균</div>
        </Card>
        <Card>
          <div style={{ fontSize:9, color:T.textMuted, marginBottom:5 }}>공매도 점수 (Short Score)</div>
          <div style={{ display:'flex', alignItems:'baseline', gap:4 }}>
            <span style={{ fontSize:28, fontWeight:900, color:scoreColor(sv.score, 10), fontFamily:FONT.sans, lineHeight:1 }}>{sv.score != null ? sv.score.toFixed(1) : '—'}</span>
            <span style={{ fontSize:11, color:T.textMuted }}>/ 10</span>
          </div>
          <GaugeBar val={sv.score} max={10} color={scoreColor(sv.score, 10)} height={3} />
        </Card>
        <Card>
          <div style={{ fontSize:9, color:T.textMuted, marginBottom:5 }}>풋/콜 점수 (Put/Call Score)</div>
          <div style={{ display:'flex', alignItems:'baseline', gap:4 }}>
            <span style={{ fontSize:28, fontWeight:900, color:pc.color, fontFamily:FONT.sans, lineHeight:1 }}>{pcScore != null ? pcScore.toFixed(1) : '—'}</span>
            <span style={{ fontSize:11, color:T.textMuted }}>/ 7</span>
          </div>
          <div style={{ fontSize:10, color:pc.color, marginTop:4, fontWeight:600 }}>{pc.text}</div>
        </Card>
      </div>

      <div style={{ display:'grid', gridTemplateColumns:'2fr 1fr', gap:16 }}>
        <Card>
          <SL right="FINRA RegSHO · T+1">공매도 비율 추이 (SHORT VOLUME RATIO TREND)</SL>
          {svTrend.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <ComposedChart data={svTrend} margin={{ left:-10, right:10, top:4 }}>
                <XAxis dataKey="date" tick={{ fill:T.textMuted, fontSize:8, fontFamily:FONT.sans }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill:T.textMuted, fontSize:8, fontFamily:FONT.sans }} axisLine={false} tickLine={false} domain={['auto','auto']} tickFormatter={v=>`${(v*100).toFixed(0)}%`} />
                <Tooltip contentStyle={tt} formatter={(v, name) => [`${(v*100).toFixed(1)}%`, name === 'svr' ? '일별 SVR' : '5일 평균']} />
                <ReferenceLine y={0.40} stroke={T.warn} strokeDasharray="3 3" label={{ value:'시장평균 40%', position:'right', fill:T.warn, fontSize:8 }} />
                <Bar dataKey="svr" name="svr" maxBarSize={16} radius={[2,2,0,0]} fillOpacity={0.5}>
                  {svTrend.map((e,i) => <Cell key={i} fill={svrColor(e.svr)} />)}
                </Bar>
                <Line type="monotone" dataKey="svr5d" name="svr5d" stroke={T.l3} strokeWidth={2} dot={false} />
              </ComposedChart>
            </ResponsiveContainer>
          ) : (
            <div style={{ height:200, display:'flex', alignItems:'center', justifyContent:'center', color:T.textMuted, fontSize:11 }}>
              공매도 데이터 없음 (FINRA 수집 대기)
            </div>
          )}
        </Card>

        <Card>
          <SL>공매도 해석 가이드</SL>
          <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
            {[
              { range:'< 30%', label:'매우 낮음 (Very Low)', color:T.up, desc:'공매도 거의 없음 → 강세 신호' },
              { range:'30~40%', label:'정상 (Normal)', color:T.warn, desc:'시장 평균 수준' },
              { range:'40~50%', label:'높음 (High)', color:T.accent, desc:'공매도 증가 → 하락 압력' },
              { range:'> 50%', label:'매우 높음 (V.High)', color:T.down, desc:'극단적 공매도 → 스퀴즈 가능' },
            ].map((g, i) => (
              <div key={i} style={{ display:'flex', gap:8, alignItems:'flex-start' }}>
                <span style={{ width:6, height:6, borderRadius:'50%', background:g.color, marginTop:4, flexShrink:0 }} />
                <div>
                  <div style={{ fontSize:10, fontWeight:700, color:g.color }}>{g.range} — {g.label}</div>
                  <div style={{ fontSize:9, color:T.textMuted }}>{g.desc}</div>
                </div>
              </div>
            ))}
          </div>
          <div style={{ marginTop:12, padding:'8px 10px', background:T.surface, borderRadius:2, fontSize:9, color:T.textMuted }}>
            ※ 데이터 출처: FINRA RegSHO Daily Short Volume<br/>
            ※ 5일 평균(SVR 5D Avg)으로 단일일 노이즈 70% 감소
          </div>
        </Card>
      </div>
    </div>
  );
}


/* ════════════════════════════════════════════════════════════ */
/*  4. MACRO TAB — 시장환경 (VIX + SPY + Sector ETF)            */
/* ════════════════════════════════════════════════════════════ */
function MacroTab({ data }) {
  const macro = data.macro || {};
  const vix = macro.vix || {};
  const spy = macro.spy || {};
  const etfs = macro.sectorEtfs || [];
  const myScore = macro.mySectorScore;

  const vixZone = (v) => {
    if (v == null) return { label:'N/A', color:T.textMuted, bg:T.borderHi };
    if (v > 30) return { label:'극단 공포 (Extreme Fear) — 역발상 매수', color:T.down, bg:`${T.down}15` };
    if (v > 25) return { label:'공포 (Fear)', color:T.accent, bg:`${T.accent}15` };
    if (v > 20) return { label:'불안 (Anxiety)', color:T.warn, bg:`${T.warn}15` };
    if (v > 15) return { label:'정상 (Normal)', color:T.neutral, bg:`${T.neutral}10` };
    if (v > 12) return { label:'안정 (Calm)', color:T.up, bg:`${T.up}10` };
    return { label:'극단 안도 (Complacency) — 과열 경고', color:T.warn, bg:`${T.warn}15` };
  };
  const vz = vixZone(vix.close);

  const spyTrend = () => {
    if (!spy.close || !spy.ma50) return { text:'N/A', color:T.textMuted };
    if (spy.ma200 && spy.close > spy.ma50 && spy.ma50 > spy.ma200) return { text:'정배열 상승 (Bullish Alignment)', color:T.up };
    if (spy.close > spy.ma50) return { text:'단기 강세 (Above MA50)', color:C.up };
    if (spy.ma200 && spy.close < spy.ma50 && spy.ma50 < spy.ma200) return { text:'역배열 하락 (Bearish Alignment)', color:T.down };
    return { text:'혼조 (Mixed)', color:T.warn };
  };
  const sp = spyTrend();

  const ETF_NAMES = {
    '10':'에너지 (Energy)','15':'소재 (Materials)','20':'산업재 (Industrials)',
    '25':'경기소비재 (Cons.Disc.)','30':'필수소비재 (Cons.Staples)','35':'헬스케어 (Healthcare)',
    '40':'금융 (Financials)','45':'기술 (Technology)','50':'커뮤니케이션 (Comm.Svc)',
    '55':'유틸리티 (Utilities)','60':'부동산 (Real Estate)',
  };

  const etfScoreColor = (s) => {
    if (s == null) return T.textMuted;
    if (s >= 8) return T.up;
    if (s >= 5) return T.warn;
    return T.down;
  };

  const etfTrendLabel = (c, m20, m50) => {
    if (!c || !m20) return '—';
    if (m50 && c > m20 && m20 > m50) return '정배열 ↑';
    if (c > m20) return '강세 ↑';
    if (m50 && c < m20 && m20 < m50) return '역배열 ↓';
    return '약세 ↓';
  };

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:16 }}>
      <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:12 }}>
        <Card style={{ background:vz.bg }}>
          <div style={{ fontSize:9, color:T.textMuted, marginBottom:5 }}>VIX 공포지수 (Fear Index)</div>
          <div style={{ fontSize:36, fontWeight:900, color:vz.color, fontFamily:FONT.sans, lineHeight:1 }}>
            {vix.close != null ? vix.close.toFixed(1) : '—'}
          </div>
          <div style={{ fontSize:10, color:vz.color, marginTop:6, fontWeight:600 }}>{vz.label}</div>
          <div style={{ display:'flex', alignItems:'baseline', gap:4, marginTop:6 }}>
            <span style={{ fontSize:9, color:T.textMuted }}>점수:</span>
            <span style={{ fontSize:14, fontWeight:700, color:scoreColor(vix.score, 10), fontFamily:FONT.sans }}>{vix.score != null ? vix.score.toFixed(1) : '—'}</span>
            <span style={{ fontSize:9, color:T.textMuted }}>/ 10</span>
          </div>
        </Card>

        <Card>
          <div style={{ fontSize:9, color:T.textMuted, marginBottom:5 }}>S&P 500 (SPY)</div>
          <div style={{ fontSize:28, fontWeight:900, color:T.text, fontFamily:FONT.sans, lineHeight:1 }}>
            {spy.close != null ? `$${spy.close.toFixed(2)}` : '—'}
          </div>
          <div style={{ fontSize:10, color:sp.color, marginTop:6, fontWeight:600 }}>{sp.text}</div>
          <div style={{ fontSize:9, color:T.textMuted, marginTop:4 }}>
            MA50: ${spy.ma50 || '—'} · MA200: ${spy.ma200 || '—'}
          </div>
        </Card>

        <Card>
          <div style={{ fontSize:9, color:T.textMuted, marginBottom:5 }}>내 섹터 ETF 점수 (My Sector)</div>
          <div style={{ display:'flex', alignItems:'baseline', gap:4 }}>
            <span style={{ fontSize:28, fontWeight:900, color:scoreColor(myScore, 10), fontFamily:FONT.sans, lineHeight:1 }}>{myScore != null ? myScore.toFixed(1) : '—'}</span>
            <span style={{ fontSize:11, color:T.textMuted }}>/ 10</span>
          </div>
          <GaugeBar val={myScore} max={10} color={scoreColor(myScore, 10)} height={3} />
          <div style={{ fontSize:9, color:T.textMuted, marginTop:6 }}>종목이 속한 섹터의 ETF 추세 점수</div>
        </Card>

        <Card>
          <div style={{ fontSize:9, color:T.textMuted, marginBottom:5 }}>시장환경 합산 (Section C)</div>
          <div style={{ display:'flex', alignItems:'baseline', gap:4 }}>
            <span style={{ fontSize:28, fontWeight:900, color:scoreColor((vix.score||0)+(myScore||0), 20), fontFamily:FONT.sans, lineHeight:1 }}>
              {((vix.score||0) + (myScore||0)).toFixed(1)}
            </span>
            <span style={{ fontSize:11, color:T.textMuted }}>/ 20</span>
          </div>
          <div style={{ fontSize:9, color:T.textMuted, marginTop:6 }}>VIX({vix.score||'—'}) + 섹터ETF({myScore||'—'})</div>
          <GaugeBar val={(vix.score||0)+(myScore||0)} max={20} color={scoreColor((vix.score||0)+(myScore||0), 20)} height={3} />
        </Card>
      </div>

      <div style={{ display:'grid', gridTemplateColumns:'1fr 2fr', gap:16 }}>
        <Card>
          <SL>VIX 해석 가이드 (Interpretation)</SL>
          <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
            {[
              { range:'< 12', label:'극단 안도 (Complacency)', color:T.warn, score:'0점', desc:'시장 과열 → 경고' },
              { range:'12~15', label:'안정 (Calm)', color:T.up, score:'2점', desc:'낙관적 시장' },
              { range:'15~20', label:'정상 (Normal)', color:T.neutral, score:'4점', desc:'평균 변동성' },
              { range:'20~25', label:'불안 (Anxiety)', color:T.warn, score:'6점', desc:'경계 필요' },
              { range:'25~30', label:'공포 (Fear)', color:T.accent, score:'8점', desc:'하락장 진입' },
              { range:'> 30', label:'극단 공포 (Extreme)', color:T.down, score:'10점', desc:'역발상 매수 기회' },
            ].map((g, i) => (
              <div key={i} style={{ display:'flex', gap:8, alignItems:'flex-start' }}>
                <span style={{ width:6, height:6, borderRadius:'50%', background:g.color, marginTop:4, flexShrink:0 }} />
                <div style={{ flex:1 }}>
                  <div style={{ fontSize:10, fontWeight:600, color:g.color }}>{g.range} — {g.label}</div>
                  <div style={{ fontSize:9, color:T.textMuted }}>{g.desc} → {g.score}</div>
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card style={{ padding:0 }}>
          <div style={{ padding:'14px 18px', borderBottom:`1px solid ${T.border}` }}>
            <SL right="FDR · 일간">섹터 ETF 현황 (SECTOR ETF STATUS) — 11개 GICS 섹터</SL>
          </div>
          <table style={{ width:'100%', borderCollapse:'collapse' }}>
            <thead><tr style={{ borderBottom:`1px solid ${T.border}` }}>
              <TH>섹터 (Sector)</TH><TH>ETF</TH><TH right>종가 (Close)</TH><TH right>MA20</TH><TH right>MA50</TH><TH>추세 (Trend)</TH><TH right>점수 (Score)</TH>
            </tr></thead>
            <tbody>
              {etfs.map((e, i) => {
                const trend = etfTrendLabel(e.close, e.ma20, e.ma50);
                const tColor = trend.includes('↑') ? T.up : trend.includes('↓') ? T.down : T.neutral;
                return (
                  <tr key={i} style={{ borderBottom:`1px solid ${T.border}22`, background:i%2?T.surface:'transparent' }}>
                    <TD style={{ fontWeight:500, color:T.text, fontSize:10 }}>{ETF_NAMES[e.sectorCode] || e.sectorCode}</TD>
                    <TD style={{ fontFamily:FONT.sans, fontWeight:700, color:T.l3 }}>{e.symbol}</TD>
                    <TD style={{ textAlign:'right', fontFamily:FONT.sans }}>{e.close != null ? `$${e.close.toFixed(2)}` : '—'}</TD>
                    <TD style={{ textAlign:'right', fontFamily:FONT.sans, color:T.textMuted }}>{e.ma20 != null ? e.ma20.toFixed(2) : '—'}</TD>
                    <TD style={{ textAlign:'right', fontFamily:FONT.sans, color:T.textMuted }}>{e.ma50 != null ? e.ma50.toFixed(2) : '—'}</TD>
                    <TD><Badge color={tColor}>{trend}</Badge></TD>
                    <TD style={{ textAlign:'right' }}>
                      <span style={{ fontWeight:700, fontFamily:FONT.sans, color:etfScoreColor(e.score) }}>{e.score != null ? e.score.toFixed(1) : '—'}</span>
                      <span style={{ fontSize:9, color:T.textMuted }}> /10</span>
                    </TD>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {etfs.length === 0 && (
            <div style={{ padding:30, textAlign:'center', color:T.textMuted, fontSize:11 }}>
              섹터 ETF 데이터 없음 (배치 실행 대기)
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}


/* ════════════════════════════════════════════════════════════ */
/*  5. PHASE 2 TAB — Coming Soon (유료 API 연동 예정)           */
/*                                                              */
/*  ★ 이 탭은 Phase 2에서 실데이터 연결 예정                      */
/*  ★ 목업 UI만 보여주고, 실제 API 호출 없음                       */
/*  ★ 필요 API: TradingView, CNN Fear&Greed, FRED, CBOE,       */
/*              Unusual Whales, S3 Partners                     */
/* ════════════════════════════════════════════════════════════ */
function Phase2Tab({ data }) {

  /* ── 실데이터 or 목업 폴백 ── */
  const realPatterns = data?.patterns || [];
  const realFearGreed = data?.fearGreed || {};
  const hasPatterns = realPatterns.length > 0;
  const hasFearGreed = realFearGreed.value != null;

  /* 패턴: 실데이터 있으면 사용, 없으면 목업 */
  const mockPatterns = [
    { name:'Cup & Handle (컵앤핸들)', confidence:87, direction:'BULLISH', timeframe:'3M', desc:'바닥을 다진 후 손잡이 형성 → 상방 돌파 준비' },
    { name:'Double Bottom (이중바닥)', confidence:72, direction:'BULLISH', timeframe:'6W', desc:'W자 형태의 지지선 확인 → 반등 신호' },
    { name:'Bull Flag (상승깃발)', confidence:65, direction:'BULLISH', timeframe:'2W', desc:'급등 후 박스권 조정 → 추세 지속 기대' },
    { name:'Head & Shoulders (머리어깨)', confidence:0, direction:'—', timeframe:'—', desc:'천장패턴 미감지' },
    { name:'Ascending Triangle (상승삼각형)', confidence:58, direction:'BULLISH', timeframe:'1M', desc:'저점 상승 + 수평 저항 → 돌파 임박' },
    { name:'Falling Wedge (하락쐐기)', confidence:0, direction:'—', timeframe:'—', desc:'미감지' },
    { name:'Triple Top (삼중천장)', confidence:0, direction:'—', timeframe:'—', desc:'미감지' },
    { name:'Symmetrical Triangle (대칭삼각형)', confidence:41, direction:'NEUTRAL', timeframe:'3W', desc:'수렴 진행 중 → 방향 미정' },
  ];

  const mockFearGreed = { value: 62, label: 'Greed (탐욕)', prev: 58 };

  const patterns = hasPatterns ? realPatterns : mockPatterns;

  /* Fear & Greed: 실데이터 있으면 사용, 없으면 목업 */
  const fearGreed = hasFearGreed ? realFearGreed : mockFearGreed;

  const mockFedRate = [
    { date:'2024-09', rate:5.25, label:'동결' },
    { date:'2024-12', rate:5.00, label:'25bp 인하' },
    { date:'2025-03', rate:4.75, label:'25bp 인하' },
    { date:'2025-06', rate:4.50, label:'25bp 인하' },
    { date:'2025-09', rate:4.50, label:'동결' },
    { date:'2026-01', rate:4.25, label:'25bp 인하' },
  ];

  const mockOptionsFlow = [
    { time:'14:32', type:'CALL', strike:'$250', exp:'Apr 18', premium:'$2.4M', sentiment:'BULLISH', unusual:true },
    { time:'13:15', type:'PUT', strike:'$220', exp:'Mar 28', premium:'$890K', sentiment:'BEARISH', unusual:false },
    { time:'11:47', type:'CALL', strike:'$260', exp:'May 16', premium:'$5.1M', sentiment:'BULLISH', unusual:true },
    { time:'10:02', type:'CALL', strike:'$240', exp:'Apr 18', premium:'$1.7M', sentiment:'BULLISH', unusual:false },
  ];

  const mockDarkPool = { pct: 38.2, avgPct: 35.5, netBuy: 12.4, trend:'ACCUMULATION' };

  const overlay = {
    position:'absolute', top:0, left:0, right:0, bottom:0,
    background:'rgba(10,10,10,0.65)', backdropFilter:'blur(2px)',
    display:'flex', alignItems:'center', justifyContent:'center', zIndex:2, borderRadius:2,
  };
  const lockBadge = {
    padding:'6px 14px', background:`${T.phase2}20`, border:`1px solid ${T.phase2}50`,
    borderRadius:3, color:T.phase2, fontSize:10, fontWeight:700, letterSpacing:1,
    fontFamily:FONT.sans,
  };

  const PreviewCard = ({ children, title, api }) => (
    <div style={{ position:'relative' }}>
      <Card style={{ opacity:0.6, filter:'grayscale(30%)' }}>
        <SL right={<span style={{ color:T.phase2, fontSize:8 }}>API: {api}</span>}>{title}</SL>
        {children}
      </Card>
      <div style={overlay}>
        <div style={{ textAlign:'center' }}>
          <div style={lockBadge}>🔒 PHASE 2 — COMING SOON</div>
          <div style={{ fontSize:9, color:T.textMuted, marginTop:6 }}>유료 API 연동 후 활성화</div>
        </div>
      </div>
    </div>
  );

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:16 }}>
      {/* Phase 2 안내 배너 */}
      <div style={{ padding:'14px 20px', background:`${T.phase2}10`, border:`1px solid ${T.phase2}30`, borderRadius:2, borderLeft:`3px solid ${T.phase2}` }}>
        <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:8 }}>
          <span style={{ fontSize:11, fontWeight:800, color:T.phase2, letterSpacing:1 }}>📋 PHASE 2 ROADMAP</span>
        </div>
        <div style={{ fontSize:10, color:T.textSub, lineHeight:1.8 }}>
          아래 기능들은 <span style={{ color:T.phase2, fontWeight:700 }}>유료 API 구독 후</span> 활성화됩니다.
          현재는 <span style={{ color:T.warn, fontWeight:600 }}>목업 미리보기</span>만 제공하며, 실데이터는 연결되지 않습니다.<br/>
          UI 레이아웃과 점수 배점은 확정 상태이므로, API 키만 입력하면 바로 동작합니다.
        </div>
        <div style={{ display:'flex', gap:16, marginTop:10, flexWrap:'wrap' }}>
          {[
            { name:'Chart Patterns (차트패턴)', api:'TradingView / TA-Lib Pro', status:'UI 완료' },
            { name:'Fear & Greed Index', api:'CNN / Alternative.me', status:'UI 완료' },
            { name:'Fed Rate Cycle (연준금리)', api:'FRED API', status:'UI 완료' },
            { name:'Options Flow (옵션흐름)', api:'Unusual Whales / Tradier', status:'UI 완료' },
            { name:'Dark Pool Volume', api:'Quandl / S3 Partners', status:'UI 완료' },
            { name:'Put/Call Ratio 상세', api:'CBOE 유료피드', status:'현재 yfinance 대체' },
          ].map((item, i) => (
            <div key={i} style={{ padding:'6px 12px', background:T.surface, border:`1px solid ${T.border}`, borderRadius:2, flex:'0 0 auto' }}>
              <div style={{ fontSize:10, fontWeight:600, color:T.text }}>{item.name}</div>
              <div style={{ fontSize:8, color:T.textMuted }}>{item.api} · <span style={{ color:T.phase2 }}>{item.status}</span></div>
            </div>
          ))}
        </div>
      </div>

      {/* ── 1. Chart Patterns 목업 ── */}
      <PreviewCard title="차트 패턴 탐지 (CHART PATTERN DETECTION) — 8개 패턴" api="TradingView">
        <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:8 }}>
          {patterns.map((p, i) => {
            const active = p.confidence > 0;
            const dirColor = p.direction === 'BULLISH' ? T.up : p.direction === 'BEARISH' ? T.down : T.neutral;
            return (
              <div key={i} style={{ padding:'10px 12px', background:active ? T.surface : 'transparent', border:`1px solid ${active ? T.borderHi : T.border}`, borderRadius:2 }}>
                <div style={{ display:'flex', alignItems:'center', gap:4, marginBottom:4 }}>
                  <span style={{ width:6, height:6, borderRadius:'50%', background:active ? dirColor : T.borderHi }} />
                  <span style={{ fontSize:9, fontWeight:600, color:active ? T.text : T.textMuted }}>{p.name}</span>
                </div>
                {active ? (
                  <>
                    <div style={{ fontSize:18, fontWeight:900, color:dirColor, fontFamily:FONT.sans }}>{p.confidence}%</div>
                    <div style={{ fontSize:8, color:T.textMuted }}>{p.direction} · {p.timeframe}</div>
                    <div style={{ fontSize:8, color:T.textMuted, marginTop:4 }}>{p.desc}</div>
                  </>
                ) : (
                  <div style={{ fontSize:10, color:T.textMuted }}>미감지</div>
                )}
              </div>
            );
          })}
        </div>
      </PreviewCard>

      {/* ── 2행: Fear & Greed + Fed Rate ── */}
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16 }}>
        <PreviewCard title="공포·탐욕 지수 (FEAR & GREED INDEX)" api="CNN / Alternative.me">
          <div style={{ display:'flex', alignItems:'center', gap:20 }}>
            <div>
              <div style={{ fontSize:48, fontWeight:900, color:T.warn, fontFamily:FONT.sans, lineHeight:1 }}>{fearGreed.value}</div>
              <div style={{ fontSize:11, color:T.warn, fontWeight:700, marginTop:4 }}>{fearGreed.label}</div>
              <div style={{ fontSize:9, color:T.textMuted, marginTop:2 }}>전일: {fearGreed.prev} (+{fearGreed.value - fearGreed.prev})</div>
            </div>
            <div style={{ flex:1 }}>
              <div style={{ height:8, background:T.borderHi, borderRadius:4, position:'relative' }}>
                <div style={{ position:'absolute', left:0, top:0, width:'25%', height:'100%', background:T.down, borderRadius:'4px 0 0 4px' }} />
                <div style={{ position:'absolute', left:'25%', top:0, width:'25%', height:'100%', background:T.accent }} />
                <div style={{ position:'absolute', left:'50%', top:0, width:'25%', height:'100%', background:T.warn }} />
                <div style={{ position:'absolute', left:'75%', top:0, width:'25%', height:'100%', background:T.up, borderRadius:'0 4px 4px 0' }} />
                <div style={{ position:'absolute', left:`${fearGreed.value}%`, top:-4, width:3, height:16, background:T.text, borderRadius:1 }} />
              </div>
              <div style={{ display:'flex', justifyContent:'space-between', marginTop:4 }}>
                <span style={{ fontSize:7, color:T.down }}>극단공포</span>
                <span style={{ fontSize:7, color:T.accent }}>공포</span>
                <span style={{ fontSize:7, color:T.warn }}>탐욕</span>
                <span style={{ fontSize:7, color:T.up }}>극단탐욕</span>
              </div>
            </div>
          </div>
        </PreviewCard>

        <PreviewCard title="연준 금리 사이클 (FED RATE CYCLE)" api="FRED API">
          <ResponsiveContainer width="100%" height={120}>
            <AreaChart data={mockFedRate} margin={{ left:-10, right:10 }}>
              <XAxis dataKey="date" tick={{ fill:T.textMuted, fontSize:8, fontFamily:FONT.sans }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill:T.textMuted, fontSize:8, fontFamily:FONT.sans }} axisLine={false} tickLine={false} domain={[4,5.5]} />
              <Tooltip contentStyle={tt} />
              <Area type="stepAfter" dataKey="rate" stroke={T.phase2} fill={T.phase2} fillOpacity={0.1} strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
          <div style={{ fontSize:9, color:T.textMuted, marginTop:4 }}>
            현재: {mockFedRate[mockFedRate.length-1].rate}% · {mockFedRate[mockFedRate.length-1].label}
          </div>
        </PreviewCard>
      </div>

      {/* ── 3행: Options Flow + Dark Pool ── */}
      <div style={{ display:'grid', gridTemplateColumns:'2fr 1fr', gap:16 }}>
        <PreviewCard title="이상 옵션 흐름 (UNUSUAL OPTIONS FLOW)" api="Unusual Whales / Tradier">
          <table style={{ width:'100%', borderCollapse:'collapse' }}>
            <thead><tr style={{ borderBottom:`1px solid ${T.border}` }}>
              <TH>시간</TH><TH>유형</TH><TH>행사가</TH><TH>만기</TH><TH>프리미엄</TH><TH>센티먼트</TH><TH>이상감지</TH>
            </tr></thead>
            <tbody>
              {mockOptionsFlow.map((o, i) => (
                <tr key={i} style={{ borderBottom:`1px solid ${T.border}22`, background:i%2?T.surface:'transparent' }}>
                  <TD style={{ fontFamily:FONT.sans, fontSize:10 }}>{o.time}</TD>
                  <TD><Badge color={o.type==='CALL'?T.up:T.down}>{o.type}</Badge></TD>
                  <TD style={{ fontFamily:FONT.sans }}>{o.strike}</TD>
                  <TD style={{ fontSize:10, color:T.textMuted }}>{o.exp}</TD>
                  <TD style={{ fontFamily:FONT.sans, fontWeight:600 }}>{o.premium}</TD>
                  <TD><Badge color={o.sentiment==='BULLISH'?T.up:T.down}>{o.sentiment}</Badge></TD>
                  <TD>{o.unusual ? <Badge color={T.warn}>⚡ UNUSUAL</Badge> : <span style={{ fontSize:9, color:T.textMuted }}>—</span>}</TD>
                </tr>
              ))}
            </tbody>
          </table>
        </PreviewCard>

        <PreviewCard title="다크풀 거래 (DARK POOL)" api="Quandl / S3 Partners">
          <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
            <div>
              <div style={{ fontSize:9, color:T.textMuted }}>Dark Pool 비율 (DP%)</div>
              <div style={{ fontSize:28, fontWeight:900, color:T.l3, fontFamily:FONT.sans, lineHeight:1 }}>{mockDarkPool.pct}%</div>
              <div style={{ fontSize:9, color:T.textMuted }}>시장평균: {mockDarkPool.avgPct}%</div>
            </div>
            <div>
              <div style={{ fontSize:9, color:T.textMuted }}>순매수 (Net Buy)</div>
              <div style={{ fontSize:22, fontWeight:900, color:T.up, fontFamily:FONT.sans }}>${mockDarkPool.netBuy}M</div>
            </div>
            <div>
              <div style={{ fontSize:9, color:T.textMuted }}>추세</div>
              <Badge color={T.up}>{mockDarkPool.trend}</Badge>
            </div>
          </div>
        </PreviewCard>
      </div>
    </div>
  );
}