/**
 * NlpSignalTab.jsx  —  Layer 2: 텍스트·감성 신호 (NLP / AI)
 *
 * v3.4 — API 실데이터 연결 + 한글 병기
 *
 * API: GET /api/stock/layer2/{ticker}
 *  ✅ 뉴스 Sentiment (FinBERT, 이벤트 태깅)
 *  ✅ 애널리스트 Consensus + Upgrade/Downgrade
 *  ✅ 내부자거래 Signal (SEC Form 4, CEO 매도 경보)
 *  ✅ Calibration 상태 (FIXED → ADAPTIVE 전환 표시)
 *  ⏳ Earnings Call Tone (Phase 3 — Mock 유지)
 *
 * 디자인: Bloomberg Terminal × Seeking Alpha — 단색 위주, 데이터 밀도 우선
 */
import React, { useState, useEffect } from 'react';
import { useOutletContext } from 'react-router-dom';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine,
  AreaChart, Area, Cell, ComposedChart, Line,
  RadarChart, PolarGrid, PolarAngleAxis, Radar,
} from 'recharts';
import { C, FONT } from '../styles/tokens';
import api from '../api';

/* ─────────────────────────────────────────────
   Design Tokens
───────────────────────────────────────────── */
const T = {
  bg:C.bgDeeper, surface:C.bgDark, card:C.surface, border:C.cardBg, borderHi:C.surfaceHi,
  text:C.textPri, textSub:C.neutral, textMuted:C.borderHi,
  accent:C.primary, up:C.up, down:C.down, neutral:C.neutral, l2:C.pink, warn:C.golden
};

const tt = { backgroundColor:C.surface, border:`1px solid ${C.surfaceHi}`, borderRadius:2, fontSize:10, color:C.textPri, fontFamily:FONT.sans, padding:'7px 12px' };

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

/* ─────────────────────────────────────────────
   로딩 / 에러 표시
───────────────────────────────────────────── */
const Loader = () => (
  <div style={{ display:'flex', justifyContent:'center', alignItems:'center', height:200, color:T.textMuted, fontSize:15, fontFamily:FONT.sans }}>
    Layer 2 데이터 로딩 중...
  </div>
);
const ErrorMsg = ({ msg }) => (
  <div style={{ padding:'14px 18px', background:`${T.down}08`, border:`1px solid ${T.down}30`,
    borderLeft:`3px solid ${T.down}`, fontSize:10, color:T.down, fontFamily:FONT.sans }}>
    {msg}
  </div>
);

/* ═══════════════════════════════════════════
   SUBTAB 네비게이터
═══════════════════════════════════════════ */
const SUBTABS = [
  { id:'OVERVIEW',    label:'Overview (종합)'              },
  { id:'NEWS',        label:'News Sentiment (뉴스 감성)'   },
  { id:'ANALYST',     label:'Analyst Revision (애널리스트)' },
  { id:'INSIDER',     label:'Insider Flow (내부자 거래)'    },
  { id:'TRANSCRIPT',  label:'(미사용_Phase 2 구현예정) Earnings Call (실적 발표)'    },
];

export default function NlpSignalTab() {
  const { ticker } = useOutletContext();
  const [tab, setTab] = useState('OVERVIEW');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!ticker) return;
    setLoading(true);
    setError(null);
    api.get(`/api/stock/layer2/${ticker}`)
      .then(res => { setData(res.data); setLoading(false); })
      .catch(err => {
        console.error('[NlpSignalTab] API error:', err);
        setError(err?.response?.data?.detail || 'Layer 2 데이터를 불러올 수 없습니다.');
        setLoading(false);
      });
  }, [ticker]);

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:0 }}>
      {/* 헤더 */}
      <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', padding:'9px 14px', background:T.surface, border:`1px solid ${T.border}`, borderLeft:`3px solid ${C.gaugeBar}`, marginBottom:14 }}>
        <div style={{ display:'flex', alignItems:'center', gap:12 }}>
          <span style={{ fontSize:9, fontWeight:800, color:C.textSec, letterSpacing:2 }}>LAYER 2</span>
          <span style={{ width:1, height:12, background:T.border, display:'inline-block' }} />
          <span style={{ fontSize:11, color:T.textSub }}>NLP 시그널 (AI Sentiment)</span>
          <span style={{ fontSize:9, color:T.textMuted }}>· 가중치 25%</span>
        </div>
        <span style={{ fontSize:9, color:T.textMuted }}>{data?.news?.calcDate || ''}</span>
      </div>

      {/* Subtab bar */}
      <div style={{ display:'flex', gap:0, borderBottom:`1px solid ${T.border}`, marginBottom:16 }}>
        {SUBTABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)} style={{
            background:'none', border:'none', cursor:'pointer',
            padding:'10px 22px', fontSize:10, fontWeight:700,
            color: tab===t.id ? T.warn : T.textMuted,
            borderBottom: tab===t.id ? `2px solid ${T.warn}` : '2px solid transparent',
            letterSpacing:1.2, textTransform:'uppercase', fontFamily:FONT.sans,
            transition:'color 0.12s', position:'relative', top:1,
          }}>
            {t.label}
          </button>
        ))}
      </div>

      {loading && <Loader />}
      {error && <ErrorMsg msg={error} />}

      {!loading && !error && data && <>
        {tab === 'OVERVIEW'   && <OverviewTab  data={data} />}
        {tab === 'NEWS'       && <NewsTab      data={data} />}
        {tab === 'ANALYST'    && <AnalystTab   data={data} />}
        {tab === 'INSIDER'    && <InsiderTab   data={data} />}
        {tab === 'TRANSCRIPT' && <TranscriptTab />}
      </>}
    </div>
  );
}

/* ═══════════════════════════════════════════
   1. OVERVIEW (종합) — 실데이터
═══════════════════════════════════════════ */
function OverviewTab({ data }) {
  const { overview, confidence } = data;
  const totalScore = overview?.totalScore ?? 50;
  const radar = overview?.radar || [];
  const signals = overview?.signals || [];
  const conviction = overview?.conviction || 'NO DATA';

  const conf = confidence || {};
  const isAdaptive = conf.scoringMode === 'ADAPTIVE';

  const convColor = totalScore >= 75 ? T.up : totalScore >= 65 ? '#4ade80' : totalScore >= 50 ? T.warn : totalScore >= 35 ? T.accent : T.down;
  const convArrow = totalScore >= 50 ? '▲' : '▼';

  return (
    <div style={{ display:'grid', gridTemplateColumns:'340px 1fr', gap:16 }}>
      <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
        {/* Calibration 상태 배너 */}
        <div style={{ padding:'8px 14px', background: isAdaptive ? `${T.up}08` : `${T.accent}08`,
          border:`1px solid ${isAdaptive ? T.up : T.accent}30`,
          borderLeft:`3px solid ${isAdaptive ? T.up : T.accent}`,
          fontSize:9, color: isAdaptive ? T.up : T.accent, fontFamily:FONT.sans }}>
          {isAdaptive ? '🧠' : '📊'} {conf.message || `스코어링 모드: ${conf.scoringMode || 'FIXED'}`}
        </div>

        <Card>
          <SL right="L2 COMPOSITE">LAYER 2 SCORE (AI 분석 점수)</SL>
          <div style={{ display:'flex', alignItems:'flex-end', gap:14, marginBottom:18 }}>
            <div style={{ fontSize:68, fontWeight:900, color:convColor, fontFamily:FONT.sans, lineHeight:1 }}>{totalScore}</div>
            <div style={{ paddingBottom:6 }}>
              <div style={{ fontSize:9, color:convColor, fontWeight:700, letterSpacing:1, marginBottom:3 }}>{convArrow} {conviction}</div>
              <div style={{ fontSize:9, color:T.textMuted, fontFamily:FONT.sans }}>100점 만점</div>
            </div>
          </div>
          <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
            {signals.map(r => (
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
              </div>
            ))}
          </div>
        </Card>

        <Card>
          <SL>DATA CONFIDENCE (데이터 신뢰도)</SL>
          <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
            {[
              { label:'News Articles (뉴스 기사·7일)', val: conf.newsCount || 0, max: 20 },
              { label:'Analyst Coverage (애널리스트 수)', val: conf.analystCount || 0, max: 30 },
              { label:'Insider Txns (내부자 거래·90일)', val: conf.insiderCount || 0, max: 10 },
            ].map(r => (
              <div key={r.label}>
                <div style={{ display:'flex', justifyContent:'space-between', marginBottom:3 }}>
                  <span style={{ fontSize:10, color:T.textSub }}>{r.label}</span>
                  <span style={{ fontSize:10, fontWeight:700, color:T.text, fontFamily:FONT.sans }}>{r.val}</span>
                </div>
                <MiniBar val={r.val} max={r.max} color={
                  r.val >= r.max * 0.7 ? T.up : r.val >= r.max * 0.3 ? '#f59e0b' : T.down
                } />
              </div>
            ))}
            <div style={{ paddingTop:8, borderTop:`1px solid ${T.border}`, display:'flex', justifyContent:'space-between' }}>
              <span style={{ fontSize:9, color:T.textMuted }}>Confidence Grade (신뢰 등급)</span>
              <Badge color={
                conf.grade === 'HIGH' ? T.up : conf.grade === 'MED' ? '#f59e0b' : T.down
              }>{conf.grade || 'N/A'}</Badge>
            </div>
          </div>
        </Card>
      </div>

      {/* Radar */}
      <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
        <Card>
          <SL right="Layer 2 Dimensions">NLP SIGNAL RADAR (신호 레이더)</SL>
          {radar.length > 0 ? (
            <ResponsiveContainer width="100%" height={320}>
              <RadarChart data={radar} cx="50%" cy="50%">
                <PolarGrid stroke={T.borderHi} />
                <PolarAngleAxis dataKey="axis" tick={{ fill:T.textSub, fontSize:10, fontFamily:FONT.sans }} />
                <Radar name="Score" dataKey="score" stroke={T.accent} fill={T.accent}
                  fillOpacity={0.15} strokeWidth={2} dot={{ r:4, fill:T.accent }} />
                <Tooltip contentStyle={tt} />
              </RadarChart>
            </ResponsiveContainer>
          ) : (
            <div style={{ height:320, display:'flex', alignItems:'center', justifyContent:'center', color:T.textMuted, fontSize:11 }}>
              Radar 데이터 없음
            </div>
          )}
        </Card>

        <Card>
          <SL>HIGH CONVICTION CONDITIONS (확신 조건)</SL>
          {[
            { met: (data.analyst?.upgradeCount || 0) >= 2, label: `애널리스트 Upgrade ${data.analyst?.upgradeCount || 0}건 (90일)` },
            { met: (data.insider?.cLevelBuyCount || 0) > 0, label: `CEO/C-Level 매수 ${data.insider?.cLevelBuyCount || 0}건` },
            { met: data.insider?.largeSellAlert === true, label: 'CEO 대규모 매도 경보', warn: true },
            { met: null, label: 'Earnings Call Tone (Phase 3)' },
          ].map(r => (
            <div key={r.label} style={{ display:'flex', alignItems:'center', gap:8, padding:'6px 0', borderBottom:`1px solid ${T.border}22` }}>
              <span style={{ fontSize:12, color: r.met == null ? T.textMuted : r.warn ? (r.met ? T.down : T.up) : (r.met ? T.up : T.textMuted) }}>
                {r.met == null ? '○' : r.warn ? (r.met ? '⚠' : '✓') : (r.met ? '✓' : '○')}
              </span>
              <span style={{ fontSize:10, color: r.met == null ? T.textMuted : T.textSub, fontFamily:FONT.sans }}>{r.label}</span>
            </div>
          ))}
        </Card>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════
   2. NEWS (뉴스 감성) — FinBERT 실데이터
═══════════════════════════════════════════ */
function NewsTab({ data }) {
  const news = data.news || {};
  const trend = news.trend || [];
  const dist = news.distribution || {};
  const articles = news.articles || [];
  const totalArt = dist.total || 1;

  const distBars = [
    { label:'Positive (긍정)', v: Math.round((dist.positive || 0) / totalArt * 100), c:T.up },
    { label:'Neutral (중립)',  v: Math.round((dist.neutral || 0) / totalArt * 100),  c:T.neutral },
    { label:'Negative (부정)', v: Math.round((dist.negative || 0) / totalArt * 100), c:T.down },
  ];

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:16 }}>
      <div style={{ display:'grid', gridTemplateColumns:'1fr 280px', gap:16 }}>
        <Card>
          <SL right="FinBERT · 30일">SENTIMENT INTENSITY TREND (감성 강도 추이)</SL>
          {trend.length > 0 ? (
            <ResponsiveContainer width="100%" height={170}>
              <ComposedChart data={trend} margin={{ left:-20, right:0, top:4, bottom:0 }}>
                <XAxis dataKey="d" tick={{ fill:T.textMuted, fontSize:9, fontFamily:FONT.sans }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill:T.textMuted, fontSize:9, fontFamily:FONT.sans }} axisLine={false} tickLine={false} domain={[-1,1]} />
                <Tooltip contentStyle={tt} formatter={v => [typeof v === 'number' ? v.toFixed(2) : v, 'Sentiment']} />
                <ReferenceLine y={0} stroke={T.borderHi} strokeDasharray="3 3" />
                <Bar dataKey="s" maxBarSize={22} radius={[2,2,0,0]}>
                  {trend.map((e,i) => <Cell key={i} fill={e.s>=0 ? T.up : T.down} fillOpacity={0.65} />)}
                </Bar>
                <Line type="sanstone" dataKey="s" stroke={T.accent} strokeWidth={1.5} dot={false} strokeDasharray="4 2" />
              </ComposedChart>
            </ResponsiveContainer>
          ) : (
            <div style={{ height:170, display:'flex', alignItems:'center', justifyContent:'center', color:T.textMuted, fontSize:11 }}>
              감성 트렌드 데이터 없음
            </div>
          )}
        </Card>
        <Card>
          <SL>DISTRIBUTION (분포)</SL>
          <div style={{ display:'flex', flexDirection:'column', gap:9 }}>
            {distBars.map(d => (
              <div key={d.label}>
                <div style={{ display:'flex', justifyContent:'space-between', marginBottom:3 }}>
                  <span style={{ fontSize:10, color:T.textSub }}>{d.label}</span>
                  <span style={{ fontSize:10, fontWeight:700, color:d.c, fontFamily:FONT.sans }}>{d.v}%</span>
                </div>
                <MiniBar val={d.v} max={100} color={d.c} />
              </div>
            ))}
            <div style={{ paddingTop:8, borderTop:`1px solid ${T.border}`, fontSize:9, color:T.textMuted }}>
              FinBERT F1 ≈ 0.87 (금융 특화) · Avg: {(news.avgSentiment || 0).toFixed(4)}
            </div>
          </div>
        </Card>
      </div>

      <Card style={{ padding:0 }}>
        <div style={{ padding:'12px 20px', borderBottom:`1px solid ${T.border}` }}>
          <SL right={`${articles.length}건 · Finnhub API`}>AI ANALYZED NEWS FEED (AI 뉴스 분석)</SL>
        </div>
        {articles.length > 0 ? (
          <table style={{ width:'100%', borderCollapse:'collapse' }}>
            <thead>
              <tr style={{ borderBottom:`1px solid ${T.border}` }}>
                <TH>Source (출처)</TH><TH>Time (시간)</TH><TH>Label (판정)</TH><TH>Headline (제목)</TH><TH right>Score (점수)</TH><TH right>Conf (확신도)</TH>
              </tr>
            </thead>
            <tbody>
              {articles.map((n,i) => (
                <tr key={i} style={{ borderBottom:`1px solid ${T.border}22`, background:i%2?T.surface:'transparent' }}>
                  <TD style={{ color:T.accent, fontWeight:700, fontFamily:FONT.sans, whiteSpace:'nowrap' }}>{n.src || '-'}</TD>
                  <TD style={{ color:T.textMuted, fontFamily:FONT.sans, whiteSpace:'nowrap' }}>{n.time ? `${n.time} ago` : '-'}</TD>
                  <TD><Badge color={n.label==='POSITIVE'?T.up:n.label==='NEGATIVE'?T.down:T.neutral}>{n.label}</Badge></TD>
                  <TD style={{ lineHeight:1.5 }}>
                    {n.url ? <a href={n.url} target="_blank" rel="noopener noreferrer"
                      style={{ color:T.textSub, textDecoration:'none', borderBottom:`1px dotted ${T.border}` }}>{n.title}</a> : n.title}
                  </TD>
                  <TD style={{ fontWeight:800, fontFamily:FONT.sans, textAlign:'right',
                    color:n.score>0?T.up:n.score<0?T.down:T.neutral, whiteSpace:'nowrap' }}>
                    {n.score>0?'+':''}{(n.score || 0).toFixed(2)}
                  </TD>
                  <TD style={{ fontFamily:FONT.sans, textAlign:'right', fontSize:10, color:T.textMuted }}>
                    {((n.confidence || 0) * 100).toFixed(0)}%
                  </TD>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div style={{ padding:30, textAlign:'center', color:T.textMuted, fontSize:11 }}>분석된 뉴스가 없습니다.</div>
        )}
      </Card>
    </div>
  );
}

/* ═══════════════════════════════════════════
   3. ANALYST (애널리스트) — Consensus 실데이터
═══════════════════════════════════════════ */
function AnalystTab({ data }) {
  const a = data.analyst || {};
  const con = a.consensus || {};

  const revTrend = [];
  if (a.upgradeCount || a.downgradeCount) {
    revTrend.push({ q:'90d Total', up: a.upgradeCount || 0, dn: a.downgradeCount || 0 });
  }

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:16 }}>
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16 }}>
        {/* Consensus Breakdown */}
        <Card>
          <SL right={`${con.total || 0}명`}>CONSENSUS BREAKDOWN (컨센서스 분석)</SL>
          <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
            {[
              { label:'Buy / Strong Buy (매수)', val: con.buy || 0, pct: con.total ? Math.round(con.buy / con.total * 100) : 0, color:T.up },
              { label:'Hold (보유)', val: con.hold || 0, pct: con.total ? Math.round(con.hold / con.total * 100) : 0, color:'#f59e0b' },
              { label:'Sell / Strong Sell (매도)', val: con.sell || 0, pct: con.total ? Math.round(con.sell / con.total * 100) : 0, color:T.down },
            ].map(r => (
              <div key={r.label}>
                <div style={{ display:'flex', justifyContent:'space-between', marginBottom:4 }}>
                  <span style={{ fontSize:10, color:T.textSub }}>{r.label}</span>
                  <div style={{ display:'flex', gap:8, alignItems:'center' }}>
                    <span style={{ fontSize:10, color:T.textMuted, fontFamily:FONT.sans }}>{r.val}명</span>
                    <span style={{ fontSize:12, fontWeight:700, color:r.color, fontFamily:FONT.sans }}>{r.pct}%</span>
                  </div>
                </div>
                <MiniBar val={r.pct} max={100} color={r.color} />
              </div>
            ))}
          </div>
          <div style={{ marginTop:14, paddingTop:10, borderTop:`1px solid ${T.border}`, display:'flex', justifyContent:'space-between', alignItems:'center' }}>
            <span style={{ fontSize:9, color:T.textMuted }}>Analyst Score (애널리스트 점수)</span>
            <span style={{ fontSize:20, fontWeight:900, color:T.text, fontFamily:FONT.sans }}>{a.score || 50}</span>
          </div>
        </Card>

        {/* Upgrade / Downgrade */}
        <Card>
          <SL right="90일">UPGRADE / DOWNGRADE (상향 / 하향)</SL>
          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr 1fr', gap:14, marginBottom:16 }}>
            <div style={{ textAlign:'center' }}>
              <div style={{ fontSize:28, fontWeight:900, color:T.up, fontFamily:FONT.sans }}>{a.upgradeCount || 0}</div>
              <div style={{ fontSize:9, color:T.textMuted, letterSpacing:1 }}>UPGRADES (상향)</div>
            </div>
            <div style={{ textAlign:'center' }}>
              <div style={{ fontSize:28, fontWeight:900, color:T.down, fontFamily:FONT.sans }}>{a.downgradeCount || 0}</div>
              <div style={{ fontSize:9, color:T.textMuted, letterSpacing:1 }}>DOWNGRADES (하향)</div>
            </div>
            <div style={{ textAlign:'center' }}>
              <div style={{ fontSize:28, fontWeight:900, color: (a.netUpgrade||0)>=0?T.up:T.down, fontFamily:FONT.sans }}>
                {(a.netUpgrade||0)>=0?'+':''}{a.netUpgrade||0}
              </div>
              <div style={{ fontSize:9, color:T.textMuted, letterSpacing:1 }}>NET (순변동)</div>
            </div>
          </div>
          {revTrend.length > 0 && (
            <ResponsiveContainer width="100%" height={100}>
              <BarChart data={revTrend} margin={{ left:-20, right:0 }}>
                <XAxis dataKey="q" tick={{ fill:T.textMuted, fontSize:9, fontFamily:FONT.sans }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill:T.textMuted, fontSize:9, fontFamily:FONT.sans }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={tt} />
                <Bar dataKey="up" name="Upgrade (상향)" fill={T.up} fillOpacity={0.7} maxBarSize={30} radius={[2,2,0,0]} />
                <Bar dataKey="dn" name="Downgrade (하향)" fill={T.down} fillOpacity={0.6} maxBarSize={30} radius={[2,2,0,0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </Card>
      </div>

      {/* EPS Revision — Phase 3 */}
      <Card>
        <div style={{ padding:'9px 14px', background:T.surface, border:`1px solid #f59e0b40`,
          borderLeft:`3px solid #f59e0b`, fontSize:9, color:'#f59e0b', fontFamily:FONT.sans }}>
          ⚙ EPS Estimate Revision (EPS 추정치 변동) / Rating Action History (투자의견 이력) — Phase 3에서 FMP API 연동 예정
        </div>
      </Card>
    </div>
  );
}

/* ═══════════════════════════════════════════
   4. INSIDER (내부자 거래) — SEC Form 4 실데이터
═══════════════════════════════════════════ */
function InsiderTab({ data }) {
  const ins = data.insider || {};
  const flow = ins.monthlyFlow || [];
  const trades = ins.trades || [];
  const score = ins.score || 50;
  const signal = ins.signal || 'NEUTRAL';

  const sigColor = signal === 'BULLISH' ? T.up : signal === 'BEARISH' ? T.down : T.neutral;

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:16 }}>
      {ins.largeSellAlert && (
        <div style={{ padding:'9px 14px', background:`${T.down}10`, border:`1px solid ${T.down}40`,
          borderLeft:`3px solid ${T.down}`, fontSize:10, color:T.down, fontFamily:FONT.sans, fontWeight:700 }}>
          ⚠ CEO 대규모 매도 경보 — 보유 지분 20% 이상 처분 가능성
        </div>
      )}

      <div style={{ display:'grid', gridTemplateColumns:'1fr 280px', gap:16 }}>
        <Card>
          <SL right="SEC Form 4 · 6개월">INSIDER NET FLOW (내부자 자금 흐름·$M)</SL>
          {flow.length > 0 ? (
            <ResponsiveContainer width="100%" height={170}>
              <BarChart data={flow} margin={{ left:-10, right:0 }}>
                <XAxis dataKey="m" tick={{ fill:T.textMuted, fontSize:9, fontFamily:FONT.sans }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill:T.textMuted, fontSize:9, fontFamily:FONT.sans }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={tt} />
                <Bar dataKey="buy" name="Buy (매수·$M)" fill={T.up} fillOpacity={0.7} maxBarSize={24} radius={[2,2,0,0]} stackId="a" />
                <Bar dataKey="sell" name="Sell (매도·$M)" fill={T.down} fillOpacity={0.6} maxBarSize={24} radius={[2,2,0,0]} stackId="a" />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div style={{ height:170, display:'flex', alignItems:'center', justifyContent:'center', color:T.textMuted, fontSize:11 }}>
              최근 6개월 거래 데이터 없음
            </div>
          )}
        </Card>
        <Card>
          <SL>INSIDER SIGNAL (내부자 신호)</SL>
          <div style={{ textAlign:'center', marginBottom:14 }}>
            <div style={{ fontSize:48, fontWeight:900, color:T.text, fontFamily:FONT.sans, lineHeight:1 }}>{score}</div>
            <div style={{ marginTop:6 }}><Badge color={sigColor}>{signal}</Badge></div>
          </div>
          <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
            {[
              { label:'Buy Transactions (매수 건수)', val: ins.buyCount || 0, color:T.up },
              { label:'Sell Transactions (매도 건수)', val: ins.sellCount || 0, color:T.down },
              { label:'C-Level Buyers (임원 매수자)', val: ins.cLevelBuyCount || 0, color:'#f59e0b' },
            ].map(r => (
              <div key={r.label} style={{ display:'flex', justifyContent:'space-between', padding:'4px 0', borderBottom:`1px solid ${T.border}22` }}>
                <span style={{ fontSize:10, color:T.textSub }}>{r.label}</span>
                <span style={{ fontSize:12, fontWeight:700, color:r.color, fontFamily:FONT.sans }}>{r.val}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Card style={{ padding:0 }}>
        <div style={{ padding:'12px 18px', borderBottom:`1px solid ${T.border}` }}>
          <SL right={`${trades.length}건 · Finnhub`}>INSIDER TRANSACTION LOG (내부자 거래 기록)</SL>
        </div>
        {trades.length > 0 ? (
          <table style={{ width:'100%', borderCollapse:'collapse' }}>
            <thead>
              <tr style={{ borderBottom:`1px solid ${T.border}` }}>
                <TH>Name (이름)</TH><TH>Role (직책)</TH><TH>Type (유형)</TH><TH right>Shares (주식수)</TH><TH right>Value (금액)</TH><TH>Date (일자)</TH>
              </tr>
            </thead>
            <tbody>
              {trades.map((t,i) => (
                <tr key={i} style={{ borderBottom:`1px solid ${T.border}22`, background:i%2?T.surface:'transparent' }}>
                  <TD style={{ fontWeight:600, color: t.isCLevel ? T.text : T.textSub }}>
                    {t.name} {t.isCLevel && <span style={{ color:'#f59e0b', fontSize:9 }}>★</span>}
                  </TD>
                  <TD style={{ color:T.textMuted }}>{t.role}</TD>
                  <TD>
                    <Badge color={t.type==='BUY'?T.up:T.down}>
                      {t.type==='BUY'?'PURCHASE (매수)':'SALE (매도)'}
                    </Badge>
                  </TD>
                  <TD style={{ textAlign:'right', fontFamily:FONT.sans }}>{t.shares}</TD>
                  <TD style={{ textAlign:'right', fontWeight:700, fontFamily:FONT.sans,
                    color:t.type==='BUY'?T.up:T.down }}>{t.val}</TD>
                  <TD style={{ color:T.textMuted, fontFamily:FONT.sans }}>{t.date}</TD>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div style={{ padding:30, textAlign:'center', color:T.textMuted, fontSize:11 }}>내부자 거래 데이터 없음</div>
        )}
      </Card>
    </div>
  );
}

/* ═══════════════════════════════════════════
   5. TRANSCRIPT (실적 발표) — Phase 3 Mock 유지
═══════════════════════════════════════════ */
function TranscriptTab() {
  const toneRadar = [
    { axis:'Optimism (낙관)',   A:82, B:68 },{ axis:'Certainty (확신)', A:78, B:71 },
    { axis:'Urgency (긴급)',    A:45, B:55 },{ axis:'Risk (위험)',       A:35, B:40 },
    { axis:'Forward (전망)',    A:88, B:73 },{ axis:'Hedging (회피)',    A:22, B:38 },
  ];
  const qHist = [
    { q:"Q1'24", ceo:62, cfo:55 },{ q:"Q2'24", ceo:68, cfo:58 },
    { q:"Q3'24", ceo:71, cfo:61 },{ q:"Q4'24", ceo:82, cfo:67 },
  ];

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:16 }}>
      <div style={{ padding:'9px 14px', background:T.surface, border:`1px solid #f59e0b40`,
        borderLeft:`3px solid #f59e0b`, fontSize:9, color:'#f59e0b', fontFamily:FONT.sans }}>
        ⚙ Phase 3 기능 — Claude/GPT API + FMP Earnings Call Transcript. 현재 Mock 데이터.
      </div>

      {/* ── 기존 UI + Coming Soon 오버레이 래퍼 ── */}
      <div style={{ position:'relative' }}>

        {/* ── 기존 콘텐츠 (그대로 유지) ── */}
        <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16 }}>
          <Card>
            <SL right="Q4'24 vs Q3'24">TONE SHIFT RADAR (톤 변화 레이더)</SL>
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
            <SL>AI TRANSCRIPT INSIGHTS (AI 실적발표 분석)</SL>
            <div style={{ display:'flex', flexDirection:'column', gap:14, marginBottom:16 }}>
              <div style={{ borderLeft:`2px solid ${T.up}`, paddingLeft:12 }}>
                <div style={{ fontSize:9, fontWeight:800, color:T.up, letterSpacing:1.5, marginBottom:4, fontFamily:FONT.sans }}>BULLISH SIGNAL (강세 신호)</div>
                <div style={{ fontSize:11, color:T.textSub, lineHeight:1.75 }}>
                  CEO가 AI 인프라 수요를 'unprecedented'로 언급. 역대 어닝콜 최고 낙관 Tone 기록.
                </div>
              </div>
              <div style={{ borderLeft:`2px solid ${T.down}`, paddingLeft:12 }}>
                <div style={{ fontSize:9, fontWeight:800, color:T.down, letterSpacing:1.5, marginBottom:4, fontFamily:FONT.sans }}>RISK FACTOR (위험 요인)</div>
                <div style={{ fontSize:11, color:T.textSub, lineHeight:1.75 }}>
                  공급 부족에 따른 리드타임 지연 리스크. CFO 재무 가이던스 언어는 중립~보수적.
                </div>
              </div>
            </div>
            <div style={{ fontSize:9, color:T.textMuted, letterSpacing:1.5, marginBottom:8, fontFamily:FONT.sans }}>KEY PHRASES (핵심 키워드)</div>
            <div style={{ display:'flex', gap:5, flexWrap:'wrap', marginBottom:5 }}>
              {['Sovereign AI','Cloud Capex','unprecedented'].map(w => (
                <span key={w} style={{ fontSize:9, padding:'3px 8px', borderRadius:2,
                  background:`${T.up}10`, color:T.up, border:`1px solid ${T.up}30`, fontFamily:FONT.sans }}>{w}</span>
              ))}
            </div>
            <div style={{ display:'flex', gap:5, flexWrap:'wrap' }}>
              {['supply constraints','execution risk'].map(w => (
                <span key={w} style={{ fontSize:9, padding:'3px 8px', borderRadius:2,
                  background:`${T.down}10`, color:T.down, border:`1px solid ${T.down}30`, fontFamily:FONT.sans }}>{w}</span>
              ))}
            </div>
          </Card>
        </div>

        <div style={{ marginTop:16 }}>
          <Card>
            <SL right="CEO·CFO Tone 점수">QUARTERLY TONE HISTORY (분기별 톤 추이)</SL>
            <ResponsiveContainer width="100%" height={160}>
              <ComposedChart data={qHist} margin={{ left:-20, right:0 }}>
                <XAxis dataKey="q" tick={{ fill:T.textMuted, fontSize:9, fontFamily:FONT.sans }} axisLine={false} tickLine={false} />
                <YAxis domain={[40,100]} tick={{ fill:T.textMuted, fontSize:9, fontFamily:FONT.sans }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={tt} />
                <Bar dataKey="ceo" name="CEO" fill={T.accent} fillOpacity={0.6} maxBarSize={30} radius={[2,2,0,0]} />
                <Bar dataKey="cfo" name="CFO" fill={T.borderHi} maxBarSize={30} radius={[2,2,0,0]} />
                <Line type="sanstone" dataKey="ceo" stroke={T.accent} strokeWidth={1.5} dot={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </Card>
        </div>

        {/* ── 반투명 Coming Soon 오버레이 ── */}
        <div style={{
          position:'absolute', inset:0,
          background:'rgba(10, 10, 10, 0.72)',
          backdropFilter:'blur(2px)',
          WebkitBackdropFilter:'blur(2px)',
          display:'flex', flexDirection:'column',
          justifyContent:'center', alignItems:'center',
          zIndex:10, borderRadius:2,
        }}>
          <div style={{
            display:'inline-flex', alignItems:'center', gap:8,
            padding:'10px 28px',
            background:'linear-gradient(135deg, #020a0a 0%, #040808 100%)',
            border:'1.5px solid #E88D14',
            borderRadius:4,
            boxShadow:'0 0 24px rgba(0,229,200,0.15), inset 0 0 12px rgba(0,229,200,0.05)',
          }}>
            <span style={{ fontSize:13 }}>🔴</span>
            <span style={{
              fontSize:11, fontWeight:800, letterSpacing:2,
              color:'#E88D14', fontFamily:FONT.sans, textTransform:'uppercase',
            }}>
              PHASE 2 — COMING SOON
            </span>
          </div>
          <div style={{
            marginTop:10, fontSize:9, color:'#E88D14',
            fontFamily:FONT.sans, letterSpacing:0.5,
          }}>
            유료 API 연동 후 활성화
          </div>
        </div>

      </div>
    </div>
  );
}