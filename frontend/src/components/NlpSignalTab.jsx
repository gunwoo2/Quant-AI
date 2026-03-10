/**
 * NlpSignalTab.jsx  —  Layer 2: NLP / AI Signal
 * 탭 구성: Overview | News Sentiment | Earnings Call | SEC Filing
 */
import React, { useState, useEffect } from 'react';
import { useOutletContext } from 'react-router-dom';
import api from '../api';

const C = {
  primary: '#D85604', purple: '#7c3aed', cyan: '#00F5FF',
  green: '#22c55e', red: '#ef4444', golden: '#E88D14',
  bg: '#000', surface: '#0f0f0f', card: '#111',
  border: '#1a1a1a', borderHi: '#2d2d2d',
  textPri: '#e8e8e8', textGray: '#a0a0a0', textMuted: '#555',
};

const SUBTABS = [
  { id: 'overview',   label: 'Overview' },
  { id: 'news',       label: 'News Sentiment' },
  { id: 'earnings',   label: 'Earnings Call' },
  { id: 'filing',     label: 'SEC Filing' },
];

// mock 뉴스 감성 데이터
const MOCK_NEWS_SENTIMENT = [
  { title: 'Company beats Q4 earnings expectations', source: 'Reuters', time: '2h ago', sentiment: 'positive', score: 0.82 },
  { title: 'New product launch receives mixed reviews', source: 'Bloomberg', time: '5h ago', sentiment: 'neutral', score: 0.12 },
  { title: 'Regulatory scrutiny raises concerns', source: 'WSJ', time: '1d ago', sentiment: 'negative', score: -0.61 },
  { title: 'Analyst upgrades price target to $320', source: 'CNBC', time: '2d ago', sentiment: 'positive', score: 0.75 },
  { title: 'Supply chain disruption may affect margins', source: 'FT', time: '3d ago', sentiment: 'negative', score: -0.44 },
];

const MOCK_EARNINGS = {
  tone: 72, // 0~100 긍정도
  keywords: [
    { word: 'growth', count: 18, sentiment: 'positive' },
    { word: 'expansion', count: 12, sentiment: 'positive' },
    { word: 'uncertainty', count: 7, sentiment: 'negative' },
    { word: 'margin pressure', count: 5, sentiment: 'negative' },
    { word: 'innovation', count: 14, sentiment: 'positive' },
    { word: 'headwinds', count: 6, sentiment: 'negative' },
    { word: 'record revenue', count: 9, sentiment: 'positive' },
    { word: 'guidance raised', count: 4, sentiment: 'positive' },
  ],
  summary: 'CEO 발언 전반적으로 낙관적. 차세대 제품 파이프라인 및 마진 개선에 자신감 표명. 거시경제 불확실성은 일부 언급.',
  date: '2026-01-29',
};

export default function NlpSignalTab() {
  const { ticker } = useOutletContext();
  const [subTab, setSubTab] = useState('overview');
  const [data, setData] = useState(null);

  useEffect(() => {
    // 실제 API 연동 시도, 실패하면 mock 사용
    api.get(`/api/stock/nlp/${ticker}`)
      .then(res => setData(res.data))
      .catch(() => setData(null));
  }, [ticker]);

  // 전체 NLP 점수 (mock or API)
  const nlpScore = data?.score ?? 74;
  const overallSentiment = nlpScore >= 65 ? 'Bullish' : nlpScore >= 45 ? 'Neutral' : 'Bearish';
  const sentimentColor = nlpScore >= 65 ? C.green : nlpScore >= 45 ? C.golden : C.red;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24, padding: '4px 0' }}>

      {/* ── 서브 탭 */}
      <div style={{ display: 'flex', borderBottom: `1px solid ${C.border}`, gap: 0 }}>
        {SUBTABS.map(t => (
          <button key={t.id} onClick={() => setSubTab(t.id)} style={{
            padding: '11px 20px', fontSize: 13, fontWeight: 700, cursor: 'pointer',
            background: 'none', border: 'none',
            borderBottom: subTab === t.id ? `2px solid ${C.purple}` : '2px solid transparent',
            color: subTab === t.id ? C.purple : C.textMuted,
            transition: 'color 0.2s',
          }}>
            {t.label}
          </button>
        ))}
      </div>

      {/* ── Overview */}
      {subTab === 'overview' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>

          {/* 종합 NLP 점수 */}
          <div style={{ gridColumn: '1/-1', background: C.card, border: `1px solid ${C.borderHi}`, borderLeft: `4px solid ${C.purple}`, borderRadius: 10, padding: '24px 28px', display: 'flex', alignItems: 'center', gap: 32 }}>
            <div>
              <div style={{ fontSize: 10, color: C.textMuted, fontFamily: 'monospace', letterSpacing: 1.5, marginBottom: 6 }}>LAYER 2 · NLP / AI SIGNAL SCORE</div>
              <div style={{ fontSize: 52, fontWeight: 900, color: C.purple, fontFamily: 'monospace', lineHeight: 1 }}>{nlpScore}</div>
              <div style={{ fontSize: 14, fontWeight: 700, color: sentimentColor, marginTop: 8 }}>{overallSentiment}</div>
            </div>
            {/* 게이지 바 */}
            <div style={{ flex: 1 }}>
              <ScoreGauge score={nlpScore} color={C.purple} />
            </div>
          </div>

          {/* 소스별 상태 */}
          {[
            { label: 'News Sentiment',    icon: '📰', score: data?.news_score     ?? 78, color: C.green  },
            { label: 'Earnings Call Tone',icon: '🎙️', score: data?.earnings_score ?? 72, color: C.golden },
            { label: 'SEC Filing NLP',    icon: '📄', score: data?.filing_score   ?? 65, color: C.purple },
            { label: 'Social Signal',     icon: '💬', score: data?.social_score   ?? null, color: C.cyan, soon: true },
          ].map(src => (
            <SourceCard key={src.label} {...src} />
          ))}
        </div>
      )}

      {/* ── News Sentiment */}
      {subTab === 'news' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <SectionTitle color={C.purple}>뉴스 감성 분석 — 최근 7일</SectionTitle>

          {/* 감성 분포 바 */}
          <SentimentDistBar
            positive={MOCK_NEWS_SENTIMENT.filter(n => n.sentiment === 'positive').length}
            neutral={MOCK_NEWS_SENTIMENT.filter(n => n.sentiment === 'neutral').length}
            negative={MOCK_NEWS_SENTIMENT.filter(n => n.sentiment === 'negative').length}
            total={MOCK_NEWS_SENTIMENT.length}
          />

          {/* 뉴스 리스트 */}
          {MOCK_NEWS_SENTIMENT.map((item, i) => (
            <NewsRow key={i} item={item} />
          ))}
        </div>
      )}

      {/* ── Earnings Call */}
      {subTab === 'earnings' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          <SectionTitle color={C.purple}>어닝콜 텍스트 분석 · {MOCK_EARNINGS.date}</SectionTitle>

          {/* 긍정도 게이지 */}
          <div style={{ background: C.card, border: `1px solid ${C.borderHi}`, borderRadius: 10, padding: '20px 24px' }}>
            <div style={{ fontSize: 11, color: C.textMuted, fontFamily: 'monospace', marginBottom: 12 }}>CEO / CFO TONE SCORE</div>
            <ScoreGauge score={MOCK_EARNINGS.tone} color={C.golden} showLabel />
          </div>

          {/* 요약 */}
          <div style={{ background: C.card, border: `1px solid ${C.borderHi}`, borderRadius: 10, padding: '20px 24px' }}>
            <div style={{ fontSize: 11, color: C.purple, fontFamily: 'monospace', letterSpacing: 1, marginBottom: 10 }}>AI SUMMARY</div>
            <p style={{ color: C.textGray, fontSize: 14, lineHeight: 1.7, margin: 0 }}>{MOCK_EARNINGS.summary}</p>
          </div>

          {/* 키워드 태그 */}
          <div style={{ background: C.card, border: `1px solid ${C.borderHi}`, borderRadius: 10, padding: '20px 24px' }}>
            <div style={{ fontSize: 11, color: C.purple, fontFamily: 'monospace', letterSpacing: 1, marginBottom: 14 }}>KEY TERMS</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {MOCK_EARNINGS.keywords.map((kw, i) => (
                <span key={i} style={{
                  padding: '5px 12px', borderRadius: 20,
                  fontSize: 12, fontWeight: 600,
                  background: kw.sentiment === 'positive' ? `${C.green}15` : `${C.red}15`,
                  color: kw.sentiment === 'positive' ? C.green : C.red,
                  border: `1px solid ${kw.sentiment === 'positive' ? C.green : C.red}30`,
                }}>
                  {kw.word} <span style={{ opacity: 0.6 }}>×{kw.count}</span>
                </span>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── SEC Filing */}
      {subTab === 'filing' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          <SectionTitle color={C.purple}>SEC 공시 NLP 분석</SectionTitle>
          <ComingSoon label="10-K / 10-Q 리스크팩터 NLP 분석" sub="Phase 2 구현 예정" />
        </div>
      )}
    </div>
  );
}

/* ── 공용 서브 컴포넌트 ── */

function SectionTitle({ children, color }) {
  return (
    <div style={{ fontSize: 12, color: color || C.purple, fontFamily: 'monospace', letterSpacing: 1.5, fontWeight: 700 }}>
      {children}
    </div>
  );
}

function ScoreGauge({ score, color, showLabel }) {
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
        <span style={{ fontSize: 11, color: C.textMuted }}>0</span>
        <span style={{ fontSize: 13, fontWeight: 700, color, fontFamily: 'monospace' }}>{score} / 100</span>
        <span style={{ fontSize: 11, color: C.textMuted }}>100</span>
      </div>
      <div style={{ height: 8, background: '#1a1a1a', borderRadius: 4, overflow: 'hidden' }}>
        <div style={{ width: `${score}%`, height: '100%', background: color, borderRadius: 4, transition: 'width 0.6s ease' }} />
      </div>
    </div>
  );
}

function SourceCard({ label, icon, score, color, soon }) {
  return (
    <div style={{ background: C.card, border: `1px solid ${C.borderHi}`, borderRadius: 10, padding: '18px 20px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
        <div>
          <span style={{ fontSize: 18, marginRight: 8 }}>{icon}</span>
          <span style={{ fontSize: 13, fontWeight: 700, color: C.textGray }}>{label}</span>
        </div>
        {soon
          ? <span style={{ fontSize: 10, color: '#555', padding: '2px 8px', border: '1px solid #333', borderRadius: 3 }}>SOON</span>
          : <span style={{ fontSize: 18, fontWeight: 900, color, fontFamily: 'monospace' }}>{score}</span>
        }
      </div>
      {!soon && <ScoreGauge score={score} color={color} />}
    </div>
  );
}

function SentimentDistBar({ positive, neutral, negative, total }) {
  const pct = v => `${Math.round(v / total * 100)}%`;
  return (
    <div style={{ background: C.card, border: `1px solid ${C.borderHi}`, borderRadius: 10, padding: '16px 20px' }}>
      <div style={{ display: 'flex', gap: 0, height: 20, borderRadius: 4, overflow: 'hidden', marginBottom: 10 }}>
        <div style={{ width: pct(positive), background: C.green }} title={`Positive: ${positive}`} />
        <div style={{ width: pct(neutral),  background: C.golden }} title={`Neutral: ${neutral}`} />
        <div style={{ width: pct(negative), background: C.red }} title={`Negative: ${negative}`} />
      </div>
      <div style={{ display: 'flex', gap: 20 }}>
        {[['Positive', positive, C.green], ['Neutral', neutral, C.golden], ['Negative', negative, C.red]].map(([l, n, c]) => (
          <div key={l} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: c, display: 'inline-block' }} />
            <span style={{ fontSize: 11, color: C.textMuted }}>{l}</span>
            <span style={{ fontSize: 11, fontWeight: 700, color: c }}>{n}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function NewsRow({ item }) {
  const sentColor = item.sentiment === 'positive' ? C.green : item.sentiment === 'negative' ? C.red : C.golden;
  const sentLabel = item.sentiment === 'positive' ? '▲ Positive' : item.sentiment === 'negative' ? '▼ Negative' : '● Neutral';
  return (
    <div style={{ background: C.card, border: `1px solid ${C.borderHi}`, borderRadius: 8, padding: '14px 18px', display: 'flex', alignItems: 'center', gap: 16 }}>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 14, color: C.textPri, fontWeight: 600, marginBottom: 4 }}>{item.title}</div>
        <div style={{ fontSize: 11, color: C.textMuted }}>{item.source} · {item.time}</div>
      </div>
      <div style={{ textAlign: 'right', minWidth: 90 }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: sentColor }}>{sentLabel}</div>
        <div style={{ fontSize: 11, color: C.textMuted, fontFamily: 'monospace' }}>
          {item.score > 0 ? '+' : ''}{item.score.toFixed(2)}
        </div>
      </div>
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