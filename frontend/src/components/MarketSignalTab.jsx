/**
 * MarketSignalTab.jsx  —  Layer 3: 시장 신호 (Market Signal)
 *
 * API: GET /api/stock/layer3/{ticker}
 * 구조: A.기술지표(55점) + B.수급·구조(25점) + C.시장환경(20점) = 100점
 *
 * v3.2 — Chart Patterns + Fear & Greed 실데이터 연결
 *   ✅ Chart Patterns: data.patterns (batch_chart_patterns → chart_patterns 테이블)
 *   ✅ Fear & Greed:   data.fearGreed (batch_fear_greed → market_fear_greed 테이블)
 *   ⏳ Phase 2 잔여:   Fed Rate, Options Flow, Dark Pool (유료 API 대기)
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

/* ── Fear & Greed 공용 ── */
const fgColor = (v) => {
  if (v == null) return T.textMuted;
  if (v <= 25) return T.down;
  if (v <= 45) return T.accent;
  if (v <= 55) return T.neutral;
  if (v <= 75) return T.warn;
  return T.up;
};
const fgLabel = (v) => {
  if (v == null) return 'N/A';
  if (v <= 25) return '극단 공포 (Extreme Fear)';
  if (v <= 45) return '공포 (Fear)';
  if (v <= 55) return '중립 (Neutral)';
  if (v <= 75) return '탐욕 (Greed)';
  return '극단 탐욕 (Extreme Greed)';
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

  const [crossAsset, setCrossAsset] = useState(null);

  useEffect(() => {
    if (!ticker) return;
    setLoading(true);
    setError(null);
    api.get(`/api/stock/layer3/${ticker}`)
      .then(res => { setData(res.data); setLoading(false); })
      .catch(err => { setError(err.response?.data?.detail || '데이터 로드 실패'); setLoading(false); });

    /* Cross-Asset 별도 로드 (실패해도 무시) */
    api.get('/api/market/cross-asset')
      .then(res => setCrossAsset(res.data))
      .catch(() => setCrossAsset(null));
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
      {tab==='MACRO'     && <MacroTab data={data} crossAsset={crossAsset} />}
      {tab==='PHASE2'    && <Phase2Tab />}
    </div>
  );
}


/* ════════════════════════════════════════════════════════════ */
/*  1. OVERVIEW TAB (+ Chart Patterns 미니 + Fear & Greed 미니)*/
/* ════════════════════════════════════════════════════════════ */
function OverviewTab({ data }) {
  const ov = data.overview || {};
  const rawTotal = ov.totalScore;
  const sections = ov.sections || [];
  const total = (rawTotal && rawTotal > 0) 
    ? rawTotal 
    : sections.reduce((sum, s) => sum + (s.score || 0), 0) || null;
  const radar = ov.radar || [];
  const indicators = ov.indicators || [];

  /* ── 신규: patterns + fearGreed ── */
  const patterns = data.patterns || [];
  const fg = data.fearGreed || {};
  const activePatterns = patterns.filter(p => p.confidence > 0);
  const bullish = activePatterns.filter(p => p.direction === 'BULLISH').length;
  const bearish = activePatterns.filter(p => p.direction === 'BEARISH').length;

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

          {/* 섹션별 바 */}
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

        {/* ★ 신규: Fear & Greed 미니 카드 */}
        <Card>
          <SL right={fg.date || ''}>FEAR & GREED INDEX (공포·탐욕)</SL>
          <div style={{ display:'flex', alignItems:'center', gap:16 }}>
            <div style={{ fontSize:42, fontWeight:900, color:fgColor(fg.value), fontFamily:FONT.sans, lineHeight:1 }}>
              {fg.value != null ? Math.round(fg.value) : '—'}
            </div>
            <div style={{ flex:1 }}>
              <div style={{ fontSize:11, fontWeight:700, color:fgColor(fg.value), marginBottom:4 }}>
                {fg.label || fgLabel(fg.value)}
              </div>
              {fg.prev != null && (
                <div style={{ fontSize:9, color:T.textMuted }}>
                  전일: {Math.round(fg.prev)} ({fg.value != null ? (fg.value > fg.prev ? '+' : '') : ''}{fg.value != null && fg.prev != null ? Math.round(fg.value - fg.prev) : '—'})
                </div>
              )}
              {/* 게이지 바 */}
              <div style={{ height:6, background:T.borderHi, borderRadius:3, position:'relative', marginTop:8 }}>
                <div style={{ position:'absolute', left:0, top:0, width:'25%', height:'100%', background:`${T.down}60`, borderRadius:'3px 0 0 3px' }} />
                <div style={{ position:'absolute', left:'25%', top:0, width:'25%', height:'100%', background:`${T.accent}60` }} />
                <div style={{ position:'absolute', left:'50%', top:0, width:'25%', height:'100%', background:`${T.warn}60` }} />
                <div style={{ position:'absolute', left:'75%', top:0, width:'25%', height:'100%', background:`${T.up}60`, borderRadius:'0 3px 3px 0' }} />
                {fg.value != null && (
                  <div style={{ position:'absolute', left:`${fg.value}%`, top:-3, width:3, height:12, background:T.text, borderRadius:1, transition:'left 0.5s ease' }} />
                )}
              </div>
              <div style={{ display:'flex', justifyContent:'space-between', marginTop:3 }}>
                <span style={{ fontSize:7, color:T.down }}>극단공포</span>
                <span style={{ fontSize:7, color:T.neutral }}>중립</span>
                <span style={{ fontSize:7, color:T.up }}>극단탐욕</span>
              </div>
            </div>
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
               : total >= 35 ? '시장 모멘텀이 약화되고 있습니다. 방어적 전략을 권장합니다.'
               : '시장 환경이 비우호적이며, 리스크 관리가 최우선입니다.'}
            </div>
          </div>
        </Card>
      </div>

      {/* 우측: 레이더 + 지표 테이블 + 차트패턴 미니 */}
      <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
        {/* 레이더 차트 */}
        {radarData.length > 0 && (
          <Card>
            <SL>FACTOR RADAR (요인 레이더)</SL>
            <ResponsiveContainer width="100%" height={260}>
              <RadarChart data={radarData} cx="50%" cy="50%" outerRadius="68%">
                <PolarGrid stroke={T.border} />
                <PolarAngleAxis dataKey="subject" tick={{ fill:T.textSub, fontSize:9, fontFamily:FONT.sans }} />
                <PolarRadiusAxis tick={false} axisLine={false} domain={[0,100]} />
                <Radar name="Score" dataKey="pct" stroke={T.l3} fill={T.l3} fillOpacity={0.2} strokeWidth={2} />
                <Tooltip contentStyle={tt} formatter={(v) => [`${v.toFixed(1)}%`, 'Score']} />
              </RadarChart>
            </ResponsiveContainer>
          </Card>
        )}

        {/* ★ 신규: Chart Patterns 미니 카드 */}
        <Card>
          <SL right={`${activePatterns.length}개 감지`}>CHART PATTERNS (차트 패턴)</SL>
          {activePatterns.length > 0 ? (
            <>
              <div style={{ display:'flex', gap:8, marginBottom:10, flexWrap:'wrap' }}>
                {bullish > 0 && <Badge color={T.up}>▲ BULLISH ×{bullish}</Badge>}
                {bearish > 0 && <Badge color={T.down}>▼ BEARISH ×{bearish}</Badge>}
                {activePatterns.length - bullish - bearish > 0 && <Badge color={T.neutral}>— NEUTRAL ×{activePatterns.length - bullish - bearish}</Badge>}
              </div>
              <div style={{ display:'flex', flexDirection:'column', gap:6 }}>
                {activePatterns.slice(0, 4).map((p, i) => {
                  const dirColor = p.direction === 'BULLISH' ? T.up : p.direction === 'BEARISH' ? T.down : T.neutral;
                  return (
                    <div key={i} style={{ display:'flex', alignItems:'center', justifyContent:'space-between', padding:'6px 10px', background:T.surface, border:`1px solid ${T.border}`, borderRadius:2 }}>
                      <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                        <span style={{ width:6, height:6, borderRadius:'50%', background:dirColor }} />
                        <span style={{ fontSize:10, color:T.text }}>{p.name}</span>
                      </div>
                      <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                        <Badge color={dirColor}>{p.direction}</Badge>
                        <span style={{ fontSize:12, fontWeight:800, color:dirColor, fontFamily:FONT.sans }}>{p.confidence}%</span>
                      </div>
                    </div>
                  );
                })}
                {activePatterns.length > 4 && (
                  <div style={{ fontSize:9, color:T.textMuted, textAlign:'center', paddingTop:4 }}>
                    + {activePatterns.length - 4}개 더 → Technical 탭에서 상세 보기
                  </div>
                )}
              </div>
            </>
          ) : (
            <div style={{ padding:20, textAlign:'center' }}>
              <div style={{ fontSize:11, color:T.textMuted }}>감지된 차트 패턴 없음</div>
              <div style={{ fontSize:9, color:T.borderHi, marginTop:4 }}>최근 3일간 분석 결과 유의미한 패턴이 발견되지 않았습니다.</div>
            </div>
          )}
        </Card>

        {/* 지표 테이블 */}
        {indicators.length > 0 && (
          <Card>
            <SL right={`${indicators.length}개 지표`}>KEY INDICATORS (주요 지표 요약)</SL>
            <table style={{ width:'100%', borderCollapse:'collapse' }}>
              <thead><tr style={{ borderBottom:`1px solid ${T.border}` }}>
                <TH>지표</TH><TH right>값</TH><TH right>점수</TH><TH right>배점</TH>
              </tr></thead>
              <tbody>
                {indicators.map((ind, i) => {
                  const c = scoreColor(ind.score, ind.max);
                  return (
                    <tr key={i} style={{ borderBottom:`1px solid ${T.border}` }}>
                      <TD><span style={{ fontWeight:600 }}>{ind.name}</span></TD>
                      <TD style={{ textAlign:'right', fontFamily:FONT.sans }}>{ind.value ?? '—'}{ind.unit ? ` ${ind.unit}` : ''}</TD>
                      <TD style={{ textAlign:'right', fontWeight:700, color:c, fontFamily:FONT.sans }}>{ind.score != null ? ind.score.toFixed(1) : '—'}</TD>
                      <TD style={{ textAlign:'right', color:T.textMuted, fontFamily:FONT.sans }}>/{ind.max}</TD>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </Card>
        )}
      </div>
    </div>
  );
}


/* ════════════════════════════════════════════════════════════ */
/*  2. TECHNICAL TAB (기존 + Chart Patterns 실데이터)           */
/* ════════════════════════════════════════════════════════════ */
function TechnicalTab({ data }) {
  const tech = data.technical || {};
  const indicators = tech.indicators || [];
  const structural = tech.structural || {};

  /* ★ 신규: 차트 패턴 실데이터 */
  const patterns = data.patterns || [];
  const activePatterns = patterns.filter(p => p.confidence > 0);
  const inactivePatterns = patterns.filter(p => !p.confidence || p.confidence === 0);

  const sigLabel = (s, max) => {
    if (s == null) return { text:'N/A', color:T.textMuted };
    const pct = s / max;
    if (pct >= 0.75) return { text:'STRONG', color:T.up };
    if (pct >= 0.5) return { text:'NEUTRAL', color:T.warn };
    if (pct >= 0.25) return { text:'WEAK', color:T.accent };
    return { text:'BEARISH', color:T.down };
  };

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:16 }}>

      {/* 기술지표 테이블 */}
      <Card>
        <SL right={`${indicators.length}개 기술지표 · 55점 만점`}>TECHNICAL INDICATORS (기술적 지표)</SL>
        {indicators.length > 0 ? (
          <table style={{ width:'100%', borderCollapse:'collapse' }}>
            <thead><tr style={{ borderBottom:`1px solid ${T.border}` }}>
              <TH>지표</TH><TH right>현재값</TH><TH right>점수</TH><TH right>배점</TH><TH right>%</TH><TH right>시그널</TH>
            </tr></thead>
            <tbody>
              {indicators.map((ind, i) => {
                const c = scoreColor(ind.score, ind.max);
                const sl = sigLabel(ind.score, ind.max);
                return (
                  <tr key={i} style={{ borderBottom:`1px solid ${T.border}` }}>
                    <TD><span style={{ fontWeight:600 }}>{ind.name}</span></TD>
                    <TD style={{ textAlign:'right', fontFamily:FONT.sans }}>{ind.value ?? '—'}{ind.unit ? ` ${ind.unit}` : ''}</TD>
                    <TD style={{ textAlign:'right', fontWeight:700, color:c, fontFamily:FONT.sans }}>{ind.score != null ? ind.score.toFixed(1) : '—'}</TD>
                    <TD style={{ textAlign:'right', color:T.textMuted, fontFamily:FONT.sans }}>/{ind.max}</TD>
                    <TD style={{ textAlign:'right', fontFamily:FONT.sans }}>
                      <span style={{ fontSize:10, color:c }}>{ind.pct != null ? `${ind.pct}%` : '—'}</span>
                    </TD>
                    <TD style={{ textAlign:'right' }}><Badge color={sl.color}>{sl.text}</Badge></TD>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : (
          <div style={{ padding:20, textAlign:'center', color:T.textMuted, fontSize:11 }}>기술지표 데이터 없음</div>
        )}
      </Card>

      {/* 구조적 시그널 */}
      {structural && (structural.goldenCross != null || structural.deathCross != null || structural.bbSqueeze != null) && (
        <Card>
          <SL>STRUCTURAL SIGNALS (구조적 시그널)</SL>
          <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:10 }}>
            {[
              { label:'골든크로스 (Golden Cross)', val:structural.goldenCross, good:true },
              { label:'데스크로스 (Death Cross)', val:structural.deathCross, good:false },
              { label:'볼린저 스퀴즈 (BB Squeeze)', val:structural.bbSqueeze, good:null },
              { label:'구조적 점수 (Structural Score)', val:structural.score, isScore:true, max:8 },
            ].map((item, i) => {
              let color = T.textMuted;
              let display = '—';
              if (item.isScore) {
                color = scoreColor(item.val, item.max);
                display = item.val != null ? `${item.val.toFixed(1)} / ${item.max}` : '—';
              } else if (item.val === true) {
                color = item.good ? T.up : T.down;
                display = '감지됨 ✓';
              } else if (item.val === false) {
                display = '미감지';
              }
              return (
                <div key={i} style={{ padding:'10px 12px', background:T.surface, border:`1px solid ${T.border}`, borderRadius:2 }}>
                  <div style={{ fontSize:9, color:T.textMuted, marginBottom:6 }}>{item.label}</div>
                  <div style={{ fontSize:14, fontWeight:700, color, fontFamily:FONT.sans }}>{display}</div>
                </div>
              );
            })}
          </div>
        </Card>
      )}

      {/* ★ 신규: Chart Patterns 상세 (실데이터) */}
      <Card>
        <SL right={`${activePatterns.length}개 감지 / ${patterns.length}개 분석`}>CHART PATTERN DETECTION (차트 패턴 탐지)</SL>
        
        {activePatterns.length > 0 ? (
          <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill, minmax(220px, 1fr))', gap:10 }}>
            {activePatterns.map((p, i) => {
              const dirColor = p.direction === 'BULLISH' ? T.up : p.direction === 'BEARISH' ? T.down : T.neutral;
              return (
                <div key={i} style={{ padding:'12px 14px', background:T.surface, border:`1px solid ${dirColor}25`, borderLeft:`3px solid ${dirColor}`, borderRadius:2 }}>
                  <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:6 }}>
                    <span style={{ fontSize:10, fontWeight:700, color:T.text }}>{p.name}</span>
                    <Badge color={dirColor}>{p.direction}</Badge>
                  </div>
                  <div style={{ display:'flex', alignItems:'baseline', gap:4, marginBottom:6 }}>
                    <span style={{ fontSize:24, fontWeight:900, color:dirColor, fontFamily:FONT.sans }}>{p.confidence}%</span>
                    <span style={{ fontSize:9, color:T.textMuted }}>confidence</span>
                  </div>
                  <GaugeBar val={p.confidence} max={100} color={dirColor} height={3} />
                  {p.desc && <div style={{ fontSize:9, color:T.textMuted, marginTop:6, lineHeight:1.5 }}>{p.desc}</div>}
                  {p.type && <div style={{ fontSize:8, color:T.borderHi, marginTop:4 }}>TYPE: {p.type}</div>}
                </div>
              );
            })}
          </div>
        ) : (
          <div style={{ padding:24, textAlign:'center' }}>
            <div style={{ fontSize:22, marginBottom:6 }}>📊</div>
            <div style={{ fontSize:11, color:T.textMuted }}>감지된 차트 패턴 없음</div>
            <div style={{ fontSize:9, color:T.borderHi, marginTop:4 }}>최근 3일간 Double Bottom, Bollinger Squeeze, RSI Divergence, Volume Climax, S/R 접근 분석 완료</div>
          </div>
        )}

        {/* 미감지 패턴 (접혀 있는 상태) */}
        {inactivePatterns.length > 0 && (
          <div style={{ marginTop:12, paddingTop:12, borderTop:`1px solid ${T.border}` }}>
            <div style={{ fontSize:9, color:T.borderHi, marginBottom:6 }}>미감지 패턴:</div>
            <div style={{ display:'flex', gap:6, flexWrap:'wrap' }}>
              {inactivePatterns.map((p, i) => (
                <span key={i} style={{ fontSize:8, padding:'2px 6px', background:T.surface, border:`1px solid ${T.border}`, borderRadius:2, color:T.textMuted }}>{p.name}</span>
              ))}
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}


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
/*  4. MACRO TAB — 시장환경 (VIX + SPY + Sector ETF + F&G)    */
/* ════════════════════════════════════════════════════════════ */
function MacroTab({ data, crossAsset }) {
  const macro = data.macro || {};
  const vix = macro.vix || {};
  const spy = macro.spy || {};
  const etfs = macro.sectorEtfs || [];
  const myScore = macro.mySectorScore;

  /* ★ 신규: Fear & Greed 실데이터 */
  const fg = data.fearGreed || {};

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
      {/* 1행: VIX + SPY + 섹터점수 + F&G */}
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
            <span style={{ fontSize:36, fontWeight:900, color:etfScoreColor(myScore), fontFamily:FONT.sans, lineHeight:1 }}>{myScore != null ? myScore.toFixed(1) : '—'}</span>
            <span style={{ fontSize:11, color:T.textMuted }}>/ 10</span>
          </div>
          <GaugeBar val={myScore} max={10} color={etfScoreColor(myScore)} height={4} />
          <div style={{ fontSize:9, color:T.textMuted, marginTop:6 }}>해당 섹터 ETF의 이동평균 분석 점수</div>
        </Card>

        {/* ★ 신규: Fear & Greed 카드 (기존 4번째 자리 교체) */}
        <Card style={{ background: fg.value != null ? `${fgColor(fg.value)}08` : 'transparent' }}>
          <div style={{ fontSize:9, color:T.textMuted, marginBottom:5 }}>Fear & Greed Index</div>
          <div style={{ fontSize:36, fontWeight:900, color:fgColor(fg.value), fontFamily:FONT.sans, lineHeight:1 }}>
            {fg.value != null ? Math.round(fg.value) : '—'}
          </div>
          <div style={{ fontSize:10, color:fgColor(fg.value), marginTop:6, fontWeight:600 }}>
            {fg.label || fgLabel(fg.value)}
          </div>
          {fg.prev != null && (
            <div style={{ fontSize:9, color:T.textMuted, marginTop:4 }}>
              전일: {Math.round(fg.prev)} ({fg.value > fg.prev ? '+' : ''}{Math.round((fg.value || 0) - fg.prev)})
            </div>
          )}
        </Card>
      </div>

      {/* ★ 신규: Fear & Greed 상세 카드 */}
      {fg.value != null && (
        <Card>
          <SL right={fg.date || ''}>FEAR & GREED INDEX — 시장 심리 상세</SL>
          <div style={{ display:'grid', gridTemplateColumns:'260px 1fr', gap:24 }}>
            {/* 좌: 게이지 */}
            <div>
              <div style={{ display:'flex', alignItems:'flex-end', gap:12, marginBottom:14 }}>
                <div style={{ fontSize:56, fontWeight:900, color:fgColor(fg.value), fontFamily:FONT.sans, lineHeight:1 }}>
                  {Math.round(fg.value)}
                </div>
                <div style={{ paddingBottom:4 }}>
                  <div style={{ fontSize:12, fontWeight:700, color:fgColor(fg.value) }}>{fg.label || fgLabel(fg.value)}</div>
                  <div style={{ fontSize:9, color:T.textMuted }}>0 (극단 공포) ~ 100 (극단 탐욕)</div>
                </div>
              </div>
              {/* 게이지 바 */}
              <div style={{ height:10, background:T.borderHi, borderRadius:5, position:'relative', overflow:'hidden' }}>
                <div style={{ position:'absolute', left:0, top:0, width:'25%', height:'100%', background:`${T.down}70` }} />
                <div style={{ position:'absolute', left:'25%', top:0, width:'25%', height:'100%', background:`${T.accent}70` }} />
                <div style={{ position:'absolute', left:'50%', top:0, width:'25%', height:'100%', background:`${T.warn}70` }} />
                <div style={{ position:'absolute', left:'75%', top:0, width:'25%', height:'100%', background:`${T.up}70` }} />
              </div>
              {fg.value != null && (
                <div style={{ position:'relative', marginTop:-13 }}>
                  <div style={{ position:'absolute', left:`calc(${fg.value}% - 6px)`, transition:'left 0.5s ease' }}>
                    <div style={{ width:3, height:16, background:T.text, borderRadius:1 }} />
                  </div>
                </div>
              )}
              <div style={{ display:'flex', justifyContent:'space-between', marginTop:10, fontSize:8 }}>
                <span style={{ color:T.down }}>극단 공포 (0)</span>
                <span style={{ color:T.accent }}>공포 (25)</span>
                <span style={{ color:T.neutral }}>중립 (50)</span>
                <span style={{ color:T.warn }}>탐욕 (75)</span>
                <span style={{ color:T.up }}>극단 탐욕 (100)</span>
              </div>
            </div>

            {/* 우: 과거 비교 */}
            <div>
              <div style={{ fontSize:9, fontWeight:700, color:T.textMuted, letterSpacing:1.5, marginBottom:10 }}>HISTORICAL COMPARISON (과거 비교)</div>
              <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
                {[
                  { label:'전일 (Previous Close)', val:fg.prev },
                  { label:'1주일 전 (1 Week Ago)', val:fg.oneWeek },
                  { label:'1개월 전 (1 Month Ago)', val:fg.oneMonth },
                  { label:'1년 전 (1 Year Ago)', val:fg.oneYear },
                ].map((item, i) => {
                  const diff = (item.val != null && fg.value != null) ? fg.value - item.val : null;
                  return (
                    <div key={i} style={{ display:'flex', justifyContent:'space-between', alignItems:'center', padding:'6px 10px', background:T.surface, borderRadius:2 }}>
                      <span style={{ fontSize:10, color:T.textSub }}>{item.label}</span>
                      <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                        <span style={{ fontSize:12, fontWeight:700, color:fgColor(item.val), fontFamily:FONT.sans }}>
                          {item.val != null ? Math.round(item.val) : '—'}
                        </span>
                        {diff != null && (
                          <span style={{ fontSize:10, fontWeight:600, color:diff >= 0 ? T.up : T.down }}>
                            {diff >= 0 ? '▲' : '▼'}{Math.abs(Math.round(diff))}
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
              <div style={{ fontSize:8, color:T.borderHi, marginTop:8 }}>
                ※ Fear & Greed 상승 = 시장 낙관 증가 (과열 경계) · 하락 = 공포 증가 (역발상 기회)
              </div>
            </div>
          </div>
        </Card>
      )}

      {/* 섹터 ETF 히트맵 테이블 */}
      {etfs.length > 0 && (
        <Card>
          <SL right={`${etfs.length}개 섹터 ETF`}>SECTOR ETF HEATMAP (섹터별 ETF 추세)</SL>
          <table style={{ width:'100%', borderCollapse:'collapse' }}>
            <thead><tr style={{ borderBottom:`1px solid ${T.border}` }}>
              <TH>섹터</TH><TH>ETF</TH><TH right>종가</TH><TH right>MA20</TH><TH right>MA50</TH><TH right>추세</TH><TH right>점수</TH>
            </tr></thead>
            <tbody>
              {etfs.map((e, i) => {
                const c = etfScoreColor(e.score);
                const trend = etfTrendLabel(e.close, e.ma20, e.ma50);
                const trendColor = trend.includes('↑') ? T.up : trend.includes('↓') ? T.down : T.neutral;
                return (
                  <tr key={i} style={{ borderBottom:`1px solid ${T.border}` }}>
                    <TD><span style={{ fontWeight:600 }}>{ETF_NAMES[e.sectorCode] || e.sectorCode}</span></TD>
                    <TD style={{ fontFamily:FONT.sans, fontWeight:600, color:T.l3 }}>{e.symbol}</TD>
                    <TD style={{ textAlign:'right', fontFamily:FONT.sans }}>${e.close?.toFixed(2) || '—'}</TD>
                    <TD style={{ textAlign:'right', fontFamily:FONT.sans, color:T.textMuted }}>${e.ma20?.toFixed(2) || '—'}</TD>
                    <TD style={{ textAlign:'right', fontFamily:FONT.sans, color:T.textMuted }}>${e.ma50?.toFixed(2) || '—'}</TD>
                    <TD style={{ textAlign:'right', fontWeight:600, color:trendColor }}>{trend}</TD>
                    <TD style={{ textAlign:'right' }}>
                      <span style={{ fontSize:12, fontWeight:700, color:c, fontFamily:FONT.sans }}>{e.score != null ? e.score.toFixed(1) : '—'}</span>
                      <span style={{ fontSize:9, color:T.textMuted }}> /10</span>
                    </TD>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
      )}

      {/* ★ Cross-Asset Intelligence */}
      {crossAsset && crossAsset.signals && (
        <Card>
          <SL right={crossAsset.calcDate || ''}>CROSS-ASSET INTELLIGENCE (글로벌 자산 시그널)</SL>
          
          {/* 총점 + 데이터 품질 */}
          <div style={{ display:'flex', alignItems:'center', gap:16, marginBottom:16 }}>
            <div style={{ display:'flex', alignItems:'baseline', gap:6 }}>
              <span style={{ fontSize:36, fontWeight:900, color:scoreColor(crossAsset.totalScore, 100), fontFamily:FONT.sans, lineHeight:1 }}>
                {crossAsset.totalScore != null ? crossAsset.totalScore.toFixed(1) : '—'}
              </span>
              <span style={{ fontSize:11, color:T.textMuted }}>/ 100</span>
            </div>
            <Badge color={crossAsset.totalScore >= 60 ? T.up : crossAsset.totalScore >= 40 ? T.warn : T.down}>
              {crossAsset.totalScore >= 70 ? 'RISK-ON' : crossAsset.totalScore >= 50 ? 'NEUTRAL' : crossAsset.totalScore >= 30 ? 'CAUTIOUS' : 'RISK-OFF'}
            </Badge>
            <span style={{ fontSize:8, color:T.borderHi, marginLeft:'auto' }}>
              DATA: {crossAsset.dataQuality}
            </span>
          </div>

          {/* 8개 시그널 그리드 */}
          <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:8, marginBottom:16 }}>
            {crossAsset.signals.map((sig, i) => {
              const sigColor = sig.signal === 'BULLISH' ? T.up : sig.signal === 'BEARISH' ? T.down : T.neutral;
              return (
                <div key={i} style={{ padding:'10px 12px', background:T.surface, border:`1px solid ${sigColor}20`, borderLeft:`3px solid ${sigColor}`, borderRadius:2 }}>
                  <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:6 }}>
                    <span style={{ fontSize:9, fontWeight:700, color:T.text }}>{sig.nameKr || sig.name}</span>
                    <Badge color={sigColor}>{sig.signal}</Badge>
                  </div>
                  <div style={{ display:'flex', alignItems:'baseline', gap:4, marginBottom:4 }}>
                    <span style={{ fontSize:20, fontWeight:900, color:sigColor, fontFamily:FONT.sans }}>{sig.score != null ? sig.score.toFixed(1) : '—'}</span>
                    <span style={{ fontSize:9, color:T.textMuted }}>/{sig.max || 10}</span>
                  </div>
                  <GaugeBar val={sig.score} max={sig.max || 10} color={sigColor} height={3} />
                  {sig.zscore != null && (
                    <div style={{ fontSize:8, color:T.borderHi, marginTop:4 }}>z={sig.zscore}</div>
                  )}
                </div>
              );
            })}
          </div>

          {/* 주요 자산 가격 */}
          {crossAsset.assets && (
            <div style={{ paddingTop:12, borderTop:`1px solid ${T.border}` }}>
              <div style={{ fontSize:9, color:T.borderHi, marginBottom:8 }}>ASSET PRICES (주요 자산 가격)</div>
              <div style={{ display:'flex', gap:8, flexWrap:'wrap' }}>
                {Object.entries(crossAsset.assets).filter(([,v]) => v != null).map(([sym, price]) => (
                  <span key={sym} style={{ fontSize:9, padding:'3px 8px', background:T.surface, border:`1px solid ${T.border}`, borderRadius:2, fontFamily:FONT.sans }}>
                    <span style={{ color:T.l3, fontWeight:600 }}>{sym}</span>
                    <span style={{ color:T.textMuted, marginLeft:4 }}>${price}</span>
                  </span>
                ))}
              </div>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}



/* ════════════════════════════════════════════════════════════ */
/*  5. PHASE 2 TAB — 잔여 목업 (Fed Rate, Options Flow, Dark Pool) */
/* ════════════════════════════════════════════════════════════ */
function Phase2Tab() {

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
          <Badge color={T.up}>Chart Patterns ✅ LIVE</Badge>
          <Badge color={T.up}>Fear & Greed ✅ LIVE</Badge>
        </div>
        <div style={{ fontSize:10, color:T.textSub, lineHeight:1.8 }}>
          아래 기능들은 <span style={{ color:T.phase2, fontWeight:700 }}>유료 API 구독 후</span> 활성화됩니다.
          현재는 <span style={{ color:T.warn, fontWeight:600 }}>목업 미리보기</span>만 제공됩니다.<br/>
          <span style={{ color:T.up }}>✅ Chart Patterns</span>과 <span style={{ color:T.up }}>✅ Fear & Greed Index</span>는 실데이터로 전환 완료되었습니다.
          각각 Technical 탭과 Macro 탭에서 확인하세요.
        </div>
        <div style={{ display:'flex', gap:16, marginTop:10, flexWrap:'wrap' }}>
          {[
            { name:'Fed Rate Cycle (연준금리)', api:'FRED API', status:'목업' },
            { name:'Options Flow (옵션흐름)', api:'Unusual Whales / Tradier', status:'목업' },
            { name:'Dark Pool Volume', api:'Quandl / S3 Partners', status:'목업' },
          ].map((item, i) => (
            <div key={i} style={{ padding:'6px 12px', background:T.surface, border:`1px solid ${T.border}`, borderRadius:2, flex:'0 0 auto' }}>
              <div style={{ fontSize:10, fontWeight:600, color:T.text }}>{item.name}</div>
              <div style={{ fontSize:8, color:T.textMuted }}>{item.api} · <span style={{ color:T.phase2 }}>{item.status}</span></div>
            </div>
          ))}
        </div>
      </div>

      {/* ── 1행: Fed Rate ── */}
      <PreviewCard title="연준 금리 사이클 (FED RATE CYCLE)" api="FRED API">
        <ResponsiveContainer width="100%" height={160}>
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

      {/* ── 2행: Options Flow + Dark Pool ── */}
      <div style={{ display:'grid', gridTemplateColumns:'2fr 1fr', gap:16 }}>
        <PreviewCard title="이상 옵션 흐름 (UNUSUAL OPTIONS FLOW)" api="Unusual Whales / Tradier">
          <table style={{ width:'100%', borderCollapse:'collapse' }}>
            <thead><tr style={{ borderBottom:`1px solid ${T.border}` }}>
              <TH>시간</TH><TH>유형</TH><TH>행사가</TH><TH>만기</TH><TH>프리미엄</TH><TH>센티먼트</TH><TH>이상감지</TH>
            </tr></thead>
            <tbody>
              {mockOptionsFlow.map((o, i) => (
                <tr key={i} style={{ borderBottom:`1px solid ${T.border}` }}>
                  <TD style={{ fontFamily:FONT.sans }}>{o.time}</TD>
                  <TD><Badge color={o.type==='CALL' ? T.up : T.down}>{o.type}</Badge></TD>
                  <TD style={{ fontFamily:FONT.sans }}>{o.strike}</TD>
                  <TD style={{ fontFamily:FONT.sans, fontSize:10 }}>{o.exp}</TD>
                  <TD style={{ fontFamily:FONT.sans, fontWeight:600 }}>{o.premium}</TD>
                  <TD><Badge color={o.sentiment==='BULLISH' ? T.up : T.down}>{o.sentiment}</Badge></TD>
                  <TD>{o.unusual ? <Badge color={T.warn}>⚡ UNUSUAL</Badge> : <span style={{ fontSize:9, color:T.textMuted }}>정상</span>}</TD>
                </tr>
              ))}
            </tbody>
          </table>
        </PreviewCard>

        <PreviewCard title="다크풀 거래량 (DARK POOL)" api="Quandl / S3">
          <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
            <div>
              <div style={{ fontSize:9, color:T.textMuted }}>다크풀 비중</div>
              <div style={{ fontSize:28, fontWeight:900, color:T.l3, fontFamily:FONT.sans }}>{mockDarkPool.pct}%</div>
              <div style={{ fontSize:9, color:T.textMuted }}>평균: {mockDarkPool.avgPct}%</div>
            </div>
            <div>
              <div style={{ fontSize:9, color:T.textMuted }}>순매수 비율</div>
              <div style={{ fontSize:20, fontWeight:800, color:T.up, fontFamily:FONT.sans }}>+{mockDarkPool.netBuy}%</div>
            </div>
            <Badge color={T.up}>{mockDarkPool.trend}</Badge>
          </div>
        </PreviewCard>
      </div>
    </div>
  );
}
