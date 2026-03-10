/**
 * MarketSignalTab.jsx  —  Layer 3: Market Signal (Price / Order Flow)
 * 탭 구성: Overview | Technical | Options Flow | Dark Pool
 */
import React, { useState, useEffect } from 'react';
import { useOutletContext } from 'react-router-dom';
import api from '../api';

const C = {
  primary: '#D85604', cyan: '#0891b2', teal: '#00F5FF',
  green: '#22c55e', red: '#ef4444', golden: '#E88D14',
  bg: '#000', surface: '#0f0f0f', card: '#111',
  border: '#1a1a1a', borderHi: '#2d2d2d',
  textPri: '#e8e8e8', textGray: '#a0a0a0', textMuted: '#555',
};

const SUBTABS = [
  { id: 'overview',  label: 'Overview' },
  { id: 'technical', label: 'Technical Indicators' },
  { id: 'options',   label: 'Options Flow' },
  { id: 'darkpool',  label: 'Dark Pool' },
];

// Mock 기술 지표 데이터
const MOCK_INDICATORS = [
  { name: 'RSI (14)',          value: '58.4',  signal: 'NEUTRAL',  sig_color: '#E88D14', desc: '중립 구간. 과매수/과매도 아님.' },
  { name: 'MACD',             value: '+0.82', signal: 'BULLISH',  sig_color: '#22c55e', desc: 'Signal Line 위. 상승 모멘텀.' },
  { name: 'Bollinger Bands',  value: 'Mid',   signal: 'NEUTRAL',  sig_color: '#E88D14', desc: '밴드 중간. 방향성 대기 중.' },
  { name: 'MA 50 vs MA 200',  value: 'Above', signal: 'BULLISH',  sig_color: '#22c55e', desc: '골든크로스 유지 중.' },
  { name: 'Volume (Avg 20D)', value: '+34%',  signal: 'BULLISH',  sig_color: '#22c55e', desc: '평균 대비 거래량 급증.' },
  { name: 'ATR (14)',         value: '8.24',  signal: 'NEUTRAL',  sig_color: '#E88D14', desc: '변동성 보통 수준.' },
  { name: 'Stoch RSI',        value: '71.2',  signal: 'BEARISH',  sig_color: '#ef4444', desc: '과매수 진입 주의.' },
  { name: 'CCI (20)',         value: '+82',   signal: 'BULLISH',  sig_color: '#22c55e', desc: '상방 압력 지속.' },
];

export default function MarketSignalTab() {
  const { ticker } = useOutletContext();
  const [subTab, setSubTab] = useState('overview');
  const [data, setData] = useState(null);

  useEffect(() => {
    api.get(`/api/stock/market-signal/${ticker}`)
      .then(res => setData(res.data))
      .catch(() => setData(null));
  }, [ticker]);

  const l3Score = data?.score ?? 68;

  const bullish = MOCK_INDICATORS.filter(i => i.signal === 'BULLISH').length;
  const neutral  = MOCK_INDICATORS.filter(i => i.signal === 'NEUTRAL').length;
  const bearish  = MOCK_INDICATORS.filter(i => i.signal === 'BEARISH').length;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24, padding: '4px 0' }}>

      {/* ── 서브 탭 */}
      <div style={{ display: 'flex', borderBottom: `1px solid ${C.border}`, gap: 0 }}>
        {SUBTABS.map(t => (
          <button key={t.id} onClick={() => setSubTab(t.id)} style={{
            padding: '11px 20px', fontSize: 13, fontWeight: 700, cursor: 'pointer',
            background: 'none', border: 'none',
            borderBottom: subTab === t.id ? `2px solid ${C.cyan}` : '2px solid transparent',
            color: subTab === t.id ? C.cyan : C.textMuted,
            transition: 'color 0.2s',
          }}>
            {t.label}
          </button>
        ))}
      </div>

      {/* ── Overview */}
      {subTab === 'overview' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>

          {/* L3 종합 점수 */}
          <div style={{ gridColumn: '1/-1', background: C.card, border: `1px solid ${C.borderHi}`, borderLeft: `4px solid ${C.cyan}`, borderRadius: 10, padding: '24px 28px', display: 'flex', alignItems: 'center', gap: 32 }}>
            <div>
              <div style={{ fontSize: 10, color: C.textMuted, fontFamily: 'monospace', letterSpacing: 1.5, marginBottom: 6 }}>LAYER 3 · MARKET SIGNAL SCORE</div>
              <div style={{ fontSize: 52, fontWeight: 900, color: C.cyan, fontFamily: 'monospace', lineHeight: 1 }}>{l3Score}</div>
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                <span style={{ fontSize: 11, color: C.textMuted }}>0</span>
                <span style={{ fontSize: 13, fontWeight: 700, color: C.cyan, fontFamily: 'monospace' }}>{l3Score} / 100</span>
                <span style={{ fontSize: 11, color: C.textMuted }}>100</span>
              </div>
              <div style={{ height: 8, background: '#1a1a1a', borderRadius: 4, overflow: 'hidden' }}>
                <div style={{ width: `${l3Score}%`, height: '100%', background: C.cyan, borderRadius: 4 }} />
              </div>
            </div>
          </div>

          {/* 기술 지표 요약 */}
          <SignalSummaryCard bullish={bullish} neutral={neutral} bearish={bearish} />

          {/* 최근 가격 모멘텀 */}
          <div style={{ background: C.card, border: `1px solid ${C.borderHi}`, borderRadius: 10, padding: '18px 20px' }}>
            <div style={{ fontSize: 11, color: C.cyan, fontFamily: 'monospace', letterSpacing: 1, marginBottom: 14 }}>PRICE MOMENTUM</div>
            {[['1W', '+3.4%', true], ['1M', '+8.7%', true], ['3M', '-2.1%', false], ['6M', '+14.2%', true]].map(([p, v, up]) => (
              <div key={p} style={{ display: 'flex', justifyContent: 'space-between', padding: '7px 0', borderBottom: `1px solid ${C.border}` }}>
                <span style={{ fontSize: 12, color: C.textMuted, fontFamily: 'monospace' }}>{p}</span>
                <span style={{ fontSize: 13, fontWeight: 700, color: up ? C.green : C.red, fontFamily: 'monospace' }}>{v}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Technical Indicators */}
      {subTab === 'technical' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <SectionTitle color={C.cyan}>기술적 지표 신호</SectionTitle>

          {/* 신호 카운터 */}
          <div style={{ display: 'flex', gap: 12 }}>
            {[['BULLISH', bullish, C.green], ['NEUTRAL', neutral, C.golden], ['BEARISH', bearish, C.red]].map(([l, n, c]) => (
              <div key={l} style={{ flex: 1, background: C.card, border: `1px solid ${c}30`, borderRadius: 8, padding: '12px 16px', textAlign: 'center' }}>
                <div style={{ fontSize: 22, fontWeight: 900, color: c }}>{n}</div>
                <div style={{ fontSize: 10, color: C.textMuted, fontFamily: 'monospace', letterSpacing: 1 }}>{l}</div>
              </div>
            ))}
          </div>

          {/* 지표 테이블 */}
          <div style={{ background: C.card, border: `1px solid ${C.borderHi}`, borderRadius: 10, overflow: 'hidden' }}>
            {/* 헤더 */}
            <div style={{ display: 'grid', gridTemplateColumns: '1.5fr 0.8fr 1fr 2fr', padding: '10px 18px', background: '#0a0a0a', borderBottom: `1px solid ${C.border}` }}>
              {['INDICATOR', 'VALUE', 'SIGNAL', 'INTERPRETATION'].map(h => (
                <div key={h} style={{ fontSize: 10, color: C.textMuted, fontFamily: 'monospace', letterSpacing: 0.8 }}>{h}</div>
              ))}
            </div>
            {MOCK_INDICATORS.map((ind, i) => (
              <div key={i} style={{
                display: 'grid', gridTemplateColumns: '1.5fr 0.8fr 1fr 2fr',
                padding: '12px 18px',
                background: i % 2 === 0 ? C.card : '#0d0d0d',
                borderBottom: `1px solid ${C.border}20`,
              }}>
                <div style={{ fontSize: 13, color: C.textGray }}>{ind.name}</div>
                <div style={{ fontSize: 13, fontWeight: 700, color: C.textPri, fontFamily: 'monospace' }}>{ind.value}</div>
                <div>
                  <span style={{
                    fontSize: 10, fontWeight: 700, padding: '3px 8px', borderRadius: 3,
                    background: `${ind.sig_color}15`, color: ind.sig_color,
                    border: `1px solid ${ind.sig_color}30`, fontFamily: 'monospace',
                  }}>
                    {ind.signal}
                  </span>
                </div>
                <div style={{ fontSize: 12, color: C.textMuted }}>{ind.desc}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Options Flow */}
      {subTab === 'options' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          <SectionTitle color={C.cyan}>옵션 플로우 분석</SectionTitle>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            <MetricBox label="Put/Call Ratio" value="0.72" sub="매수 우세" color={C.green} />
            <MetricBox label="IV Rank"        value="34%"  sub="변동성 낮음" color={C.golden} />
            <MetricBox label="Unusual Activity" value="↑ Calls" sub="+320% 콜 급증" color={C.green} />
            <MetricBox label="Max Pain"        value="$285" sub="만기일 핀 포인트" color={C.cyan} />
          </div>
          <ComingSoon label="상세 옵션 플로우 스캐너 — Phase 2" sub="대형 기관 블록 거래 탐지 로직 구현 예정" />
        </div>
      )}

      {/* ── Dark Pool */}
      {subTab === 'darkpool' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          <SectionTitle color={C.cyan}>다크풀 / 기관 수급 분석</SectionTitle>
          <ComingSoon label="Dark Pool 거래 데이터 — Phase 3" sub="FINRA ADF/ORF 기반 비공개 체결 분석 구현 예정" />
        </div>
      )}
    </div>
  );
}

/* ── 공용 서브 컴포넌트 ── */
function SectionTitle({ children, color }) {
  return (
    <div style={{ fontSize: 12, color, fontFamily: 'monospace', letterSpacing: 1.5, fontWeight: 700 }}>
      {children}
    </div>
  );
}

function SignalSummaryCard({ bullish, neutral, bearish }) {
  const total = bullish + neutral + bearish;
  return (
    <div style={{ background: C.card, border: `1px solid ${C.borderHi}`, borderRadius: 10, padding: '18px 20px' }}>
      <div style={{ fontSize: 11, color: C.cyan, fontFamily: 'monospace', letterSpacing: 1, marginBottom: 14 }}>SIGNAL SUMMARY</div>
      <div style={{ display: 'flex', gap: 0, height: 12, borderRadius: 6, overflow: 'hidden', marginBottom: 12 }}>
        <div style={{ width: `${bullish/total*100}%`, background: C.green }} />
        <div style={{ width: `${neutral/total*100}%`, background: C.golden }} />
        <div style={{ width: `${bearish/total*100}%`, background: C.red }} />
      </div>
      {[['Bullish', bullish, C.green], ['Neutral', neutral, C.golden], ['Bearish', bearish, C.red]].map(([l, n, c]) => (
        <div key={l} style={{ display: 'flex', justifyContent: 'space-between', padding: '5px 0' }}>
          <span style={{ fontSize: 12, color: C.textMuted }}>{l}</span>
          <span style={{ fontSize: 12, fontWeight: 700, color: c }}>{n} / {total}</span>
        </div>
      ))}
    </div>
  );
}

function MetricBox({ label, value, sub, color }) {
  return (
    <div style={{ background: C.card, border: `1px solid ${C.borderHi}`, borderRadius: 10, padding: '18px 20px' }}>
      <div style={{ fontSize: 11, color: C.textMuted, fontFamily: 'monospace', marginBottom: 8 }}>{label}</div>
      <div style={{ fontSize: 26, fontWeight: 900, color, fontFamily: 'monospace' }}>{value}</div>
      <div style={{ fontSize: 11, color: color, marginTop: 6 }}>{sub}</div>
    </div>
  );
}

function ComingSoon({ label, sub }) {
  return (
    <div style={{ background: C.card, border: `1px dashed ${C.borderHi}`, borderRadius: 10, padding: '60px 24px', textAlign: 'center' }}>
      <div style={{ fontSize: 13, color: C.textMuted, marginBottom: 8 }}>{label}</div>
      <div style={{ fontSize: 11, color: '#333' }}>{sub}</div>
    </div>
  );
}