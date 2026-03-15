/**
 * SummaryTab.jsx — v5 (Full Redesign)
 *
 * Layout:
 *   1. AI Verdict Card (등급 + 점수 + L1/L2/L3 게이지 + strong signal)
 *   2. TradingView Chart
 *   3. Technical Snapshot (RSI·MA·Cross·52W·Vol·Momentum)
 *   4. AI Rating History (좌) | Latest News (우)
 *
 * API Calls:
 *   - GET /api/stock/rating-history/{ticker}
 *   - GET /api/news/{ticker}?limit=8
 */
import React, { useState, useEffect } from 'react';
import { useOutletContext } from 'react-router-dom';
import TradingViewWidget from './TradingViewWidget';
import api from '../api';

/* ── Design Tokens ── */
const C = {
  bg: '#0a0a0a', surface: '#0f0f0f', card: '#111', border: '#1a1a1a',
  text: '#e8e8e8', sub: '#888', muted: '#555', dark: '#333',
  primary: '#D85604', up: '#22c55e', down: '#ef4444',
  cyan: '#00F5FF', amber: '#E88D14', scarlet: '#AD1B02',
  l1: '#D85604', l2: '#7c3aed', l3: '#0891b2',
};

const GRADE_MAP = {
  'S':  { label: 'STRONG BUY',   color: '#00F5FF' },
  'A+': { label: 'BUY',          color: '#00F5FF' },
  'A':  { label: 'OUTPERFORM',   color: '#D85604' },
  'B+': { label: 'HOLD',         color: '#E88D14' },
  'B':  { label: 'NEUTRAL',      color: '#E88D14' },
  'C':  { label: 'SELL',         color: '#AD1B02' },
  'D':  { label: 'STRONG SELL',  color: '#7a0000' },
};

const SIGNAL_KO = {
  'STRONG_BUY': '강력매수', 'BUY': '매수', 'HOLD': '보유',
  'SELL': '매도', 'STRONG_SELL': '강력매도',
};

function fmt(v, d = 2) { return v != null ? Number(v).toFixed(d) : '—'; }


/* ════════════════════════════════════════════════════════ */
export default function SummaryTab() {
  const { ticker, realtime, quantData } = useOutletContext();
  const [ratingHistory, setRatingHistory] = useState(null);
  const [news, setNews] = useState(null);

  /* ── Data Fetch ── */
  useEffect(() => {
    if (!ticker) return;

    /* Rating History */
    api.get(`/api/stock/rating-history/${ticker}`)
      .then(r => {
        console.log('[SummaryTab] rating-history response:', r.data);
        setRatingHistory(r.data || []);
      })
      .catch(err => {
        console.warn('[SummaryTab] rating-history failed:', err);
        setRatingHistory([]);
      });

    /* ★ News — /api/news/{ticker} 호출 */
    console.log('[SummaryTab] Fetching news for:', ticker);
    api.get(`/api/news/${ticker}`, { params: { limit: 8 } })
      .then(r => {
        console.log('[SummaryTab] news response:', r.data);
        setNews(r.data || []);
      })
      .catch(err => {
        console.warn('[SummaryTab] news fetch failed:', err);
        setNews([]);
      });
  }, [ticker]);

  const tech = quantData?.technical || {};
  const grade = GRADE_MAP[realtime?.grade] ?? { label: 'N/A', color: '#555' };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20, padding: '20px 0' }}>

      {/* ━━ 1. AI VERDICT CARD ━━ */}
      <AIVerdictCard realtime={realtime} grade={grade} />

      {/* ━━ 2. TRADINGVIEW CHART ━━ */}
      <div style={{
        height: 480, background: C.card, borderRadius: 10,
        overflow: 'hidden', border: `1px solid ${C.border}`,
      }}>
        <TradingViewWidget symbol={ticker || 'AAPL'} />
      </div>

      {/* ━━ 3. TECHNICAL SNAPSHOT ━━ */}
      <TechnicalSnapshot tech={tech} realtime={realtime} />

      {/* ━━ 4. AI RATING HISTORY (좌) | NEWS (우) ━━ */}
      <div style={{
        display: 'grid', gridTemplateColumns: '1fr 1fr',
        gap: 20, alignItems: 'start',
      }}>
        <RatingHistoryCard data={ratingHistory} />
        <NewsCard data={news} ticker={ticker} />
      </div>
    </div>
  );
}


/* ─────────────────────────────────────────────────
   1. AI Verdict Card
   ───────────────────────────────────────────────── */
function AIVerdictCard({ realtime, grade }) {
  if (!realtime) return null;

  const layers = [
    { key: 'L1', label: 'Quant Score',   val: realtime.l1, color: C.l1 },
    { key: 'L2', label: 'NLP Sentiment', val: realtime.l2, color: C.l2 },
    { key: 'L3', label: 'Market Signal', val: realtime.l3, color: C.l3 },
  ];

  const hasStrongBuy  = realtime.strong_buy_signal;
  const hasStrongSell = realtime.strong_sell_signal;

  return (
    <div style={{
      background: `linear-gradient(135deg, ${grade.color}06 0%, ${C.card} 100%)`,
      border: `1px solid ${grade.color}20`,
      borderRadius: 12, overflow: 'hidden',
    }}>
      {/* Strong Signal Alert */}
      {(hasStrongBuy || hasStrongSell) && (
        <div style={{
          background: hasStrongBuy ? `${C.up}15` : `${C.down}15`,
          borderBottom: `1px solid ${hasStrongBuy ? C.up : C.down}30`,
          padding: '8px 24px',
          display: 'flex', alignItems: 'center', gap: 8,
        }}>
          <span style={{ fontSize: 12 }}>{hasStrongBuy ? '🔥' : '⚠️'}</span>
          <span style={{
            fontSize: 10, fontWeight: 800, letterSpacing: 1.5,
            color: hasStrongBuy ? C.up : C.down,
          }}>
            {hasStrongBuy ? 'STRONG BUY SIGNAL DETECTED' : 'STRONG SELL SIGNAL DETECTED'}
          </span>
        </div>
      )}

      <div style={{
        padding: '22px 28px',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        flexWrap: 'wrap', gap: 20,
      }}>
        {/* Left: Grade + Signal */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
          <div style={{
            width: 64, height: 64, borderRadius: 14,
            background: `${grade.color}12`, border: `2px solid ${grade.color}35`,
            display: 'flex', flexDirection: 'column',
            alignItems: 'center', justifyContent: 'center',
          }}>
            <div style={{
              fontSize: 26, fontWeight: 900, color: grade.color,
              fontFamily: 'sans-serif', lineHeight: 1,
            }}>
              {realtime.grade || '—'}
            </div>
            <div style={{ fontSize: 7, color: C.muted, letterSpacing: 1, marginTop: 2 }}>GRADE</div>
          </div>
          <div>
            <div style={{
              fontSize: 8, color: C.muted, letterSpacing: 2.5,
              marginBottom: 4, fontFamily: 'sans-serif',
            }}>
              QUANT AI VERDICT
            </div>
            <div style={{
              fontSize: 26, fontWeight: 900, color: grade.color,
              fontFamily: 'sans-serif', letterSpacing: 0.5, lineHeight: 1.1,
            }}>
              {grade.label}
            </div>
            {realtime.score != null && (
              <div style={{ fontSize: 11, color: C.sub, marginTop: 4, fontFamily: 'sans-serif' }}>
                Composite Score: <span style={{ color: grade.color, fontWeight: 800 }}>
                  {Number(realtime.score).toFixed(1)}
                </span>
                <span style={{ color: C.dark }}> / 100</span>
              </div>
            )}
          </div>
        </div>

        {/* Right: L1/L2/L3 Gauges */}
        <div style={{ display: 'flex', gap: 12 }}>
          {layers.map(l => {
            const pct = l.val != null ? Math.min(l.val, 100) : 0;
            return (
              <div key={l.key} style={{
                width: 100, padding: '12px 14px', borderRadius: 10, textAlign: 'center',
                background: `${l.color}08`, border: `1px solid ${l.color}18`,
              }}>
                <div style={{ fontSize: 8, color: C.muted, letterSpacing: 1.5, marginBottom: 6 }}>{l.key}</div>
                <div style={{
                  height: 4, background: `${l.color}15`, borderRadius: 2,
                  marginBottom: 8, overflow: 'hidden',
                }}>
                  <div style={{
                    width: `${pct}%`, height: '100%',
                    background: l.color, borderRadius: 2,
                    transition: 'width 0.6s ease',
                  }} />
                </div>
                <div style={{
                  fontSize: 20, fontWeight: 900, fontFamily: 'sans-serif',
                  color: l.val != null ? l.color : C.dark,
                }}>
                  {l.val != null ? Number(l.val).toFixed(0) : '—'}
                </div>
                <div style={{ fontSize: 8, color: C.dark, marginTop: 2 }}>{l.label}</div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}


/* ─────────────────────────────────────────────────
   3. Technical Snapshot
   ───────────────────────────────────────────────── */
function TechnicalSnapshot({ tech, realtime }) {
  if (!tech || Object.keys(tech).length === 0) return null;

  const rsi = tech.rsi14;
  const rsiColor = rsi != null
    ? rsi >= 70 ? C.down : rsi <= 30 ? C.up : C.sub
    : C.muted;
  const rsiLabel = rsi != null
    ? rsi >= 70 ? 'Overbought' : rsi <= 30 ? 'Oversold' : 'Neutral'
    : '—';

  const ma50  = tech.ma50;
  const ma200 = tech.ma200;
  const price = realtime?.price;

  const items = [
    {
      label: 'RSI (14)',
      value: rsi != null ? Number(rsi).toFixed(1) : '—',
      sub: rsiLabel,
      color: rsiColor,
    },
    {
      label: 'MA 50 / 200',
      value: ma50 != null && ma200 != null
        ? `${Number(ma50).toFixed(0)} / ${Number(ma200).toFixed(0)}`
        : '—',
      sub: tech.goldenCross ? '🟢 Golden Cross'
         : tech.deathCross  ? '🔴 Death Cross'
         : price && ma50 ? (price > ma50 ? 'Above MA50' : 'Below MA50') : '—',
      color: tech.goldenCross ? C.up : tech.deathCross ? C.down
           : price && ma50 ? (price > ma50 ? C.up : C.down) : C.muted,
    },
    {
      label: '52W Position',
      value: tech.dist52W != null ? `${(Number(tech.dist52W) * 100).toFixed(1)}%` : '—',
      sub: tech.dist52W != null
        ? Number(tech.dist52W) >= 0.9 ? 'Near High' : Number(tech.dist52W) <= 0.3 ? 'Near Low' : 'Mid Range'
        : '—',
      color: tech.dist52W != null
        ? Number(tech.dist52W) >= 0.9 ? C.up : Number(tech.dist52W) <= 0.3 ? C.down : C.amber
        : C.muted,
    },
    {
      label: 'Volatility (250d)',
      value: tech.annualizedVol250d != null ? `${(Number(tech.annualizedVol250d) * 100).toFixed(1)}%` : '—',
      sub: tech.annualizedVol250d != null
        ? Number(tech.annualizedVol250d) > 0.5 ? 'High' : Number(tech.annualizedVol250d) < 0.2 ? 'Low' : 'Moderate'
        : '—',
      color: tech.annualizedVol250d != null
        ? Number(tech.annualizedVol250d) > 0.5 ? C.down : Number(tech.annualizedVol250d) < 0.2 ? C.up : C.amber
        : C.muted,
    },
    {
      label: 'Trend R²',
      value: tech.trendR2 != null ? Number(tech.trendR2).toFixed(3) : '—',
      sub: tech.trendR2 != null
        ? Number(tech.trendR2) > 0.7 ? 'Strong' : Number(tech.trendR2) > 0.4 ? 'Moderate' : 'Weak'
        : '—',
      color: tech.trendR2 != null
        ? Number(tech.trendR2) > 0.7 ? C.up : Number(tech.trendR2) > 0.4 ? C.amber : C.down
        : C.muted,
    },
    {
      label: 'Rel. Momentum',
      value: tech.relativeMomentumPct != null ? `${(Number(tech.relativeMomentumPct) * 100).toFixed(1)}%` : '—',
      sub: tech.relativeMomentumPct != null
        ? Number(tech.relativeMomentumPct) > 0 ? 'Outperform' : 'Underperform'
        : '—',
      color: tech.relativeMomentumPct != null
        ? (Number(tech.relativeMomentumPct) > 0 ? C.up : C.down) : C.muted,
    },
  ];

  return (
    <div style={{
      background: C.card, border: `1px solid ${C.border}`,
      borderRadius: 10, padding: '20px 24px',
    }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8, marginBottom: 18,
      }}>
        <span style={{
          width: 3, height: 14, background: C.cyan,
          display: 'inline-block', borderRadius: 1,
        }} />
        <span style={{
          fontSize: 12, fontWeight: 800, color: C.text,
          letterSpacing: 0.5, fontFamily: 'sans-serif',
        }}>
          Technical Snapshot
        </span>
        {tech.obvTrend && (
          <span style={{
            marginLeft: 'auto', fontSize: 9, color: C.muted,
            fontFamily: 'sans-serif', letterSpacing: 1,
          }}>
            OBV: <span style={{
              color: tech.obvTrend === 'BULLISH' ? C.up : tech.obvTrend === 'BEARISH' ? C.down : C.amber,
              fontWeight: 700,
            }}>{tech.obvTrend}</span>
          </span>
        )}
      </div>

      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 0,
        border: `1px solid ${C.border}`, borderRadius: 8, overflow: 'hidden',
      }}>
        {items.map((item, i) => (
          <div key={i} style={{
            padding: '14px 12px', textAlign: 'center',
            borderRight: i < items.length - 1 ? `1px solid ${C.border}` : 'none',
            background: `${item.color}04`,
          }}>
            <div style={{
              fontSize: 8, color: C.muted, letterSpacing: 1,
              marginBottom: 8, fontFamily: 'sans-serif',
            }}>
              {item.label}
            </div>
            <div style={{
              fontSize: 16, fontWeight: 800, color: item.color,
              fontFamily: 'sans-serif', marginBottom: 4,
            }}>
              {item.value}
            </div>
            <div style={{
              fontSize: 9, color: item.color, fontWeight: 600, opacity: 0.8,
            }}>
              {item.sub}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}


/* ─────────────────────────────────────────────────
   4a. AI Rating History Card
   ───────────────────────────────────────────────── */
function RatingHistoryCard({ data }) {
  return (
    <div style={{
      background: C.card, border: `1px solid ${C.border}`,
      borderRadius: 10, padding: '20px 22px', minHeight: 380,
      display: 'flex', flexDirection: 'column',
    }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16,
      }}>
        <span style={{
          width: 3, height: 14, background: C.primary,
          display: 'inline-block', borderRadius: 1,
        }} />
        <span style={{
          fontSize: 12, fontWeight: 800, color: C.text,
          letterSpacing: 0.5, fontFamily: 'sans-serif',
        }}>
          AI Rating History
        </span>
      </div>

      <div style={{ flex: 1, overflowY: 'auto' }}>
        {data === null ? (
          <LoadingPlaceholder />
        ) : data.length === 0 ? (
          <EmptyPlaceholder text="배치 실행 후 이력이 표시됩니다." />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {data.map((item, idx) => {
              const gc = GRADE_MAP[item.grade]?.color ?? '#888';
              const sigLabel = SIGNAL_KO[item.signal] || item.signal || '';
              const prevItem = data[idx + 1];
              const scoreChange = prevItem?.score != null && item.score != null
                ? Number(item.score) - Number(prevItem.score) : null;

              return (
                <div key={idx} style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '10px 0',
                  borderBottom: idx < data.length - 1 ? `1px solid ${C.border}` : 'none',
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <div style={{
                      width: 36, height: 36, borderRadius: 8,
                      background: `${gc}12`, border: `1px solid ${gc}25`,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                    }}>
                      <span style={{
                        fontWeight: 900, fontSize: 15, color: gc,
                        fontFamily: 'sans-serif',
                      }}>{item.grade}</span>
                    </div>
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <span style={{ color: gc, fontWeight: 700, fontSize: 11 }}>{sigLabel}</span>
                        {scoreChange != null && scoreChange !== 0 && (
                          <span style={{
                            fontSize: 9, fontWeight: 700,
                            color: scoreChange > 0 ? C.up : C.down,
                          }}>
                            {scoreChange > 0 ? '▲' : '▼'}{Math.abs(scoreChange).toFixed(1)}
                          </span>
                        )}
                      </div>
                      <div style={{
                        color: C.muted, fontSize: 9, fontFamily: 'sans-serif', marginTop: 2,
                      }}>
                        Score {item.score != null ? Number(item.score).toFixed(1) : '—'}
                        <span style={{ margin: '0 4px', color: C.dark }}>·</span>
                        <span style={{ color: C.l1 }}>L1 {item.l1 ?? '—'}</span>
                        <span style={{ margin: '0 3px', color: C.dark }}>·</span>
                        <span style={{ color: C.l2 }}>L2 {item.l2 ?? '—'}</span>
                        <span style={{ margin: '0 3px', color: C.dark }}>·</span>
                        <span style={{ color: C.l3 }}>L3 {item.l3 ?? '—'}</span>
                      </div>
                    </div>
                  </div>
                  <div style={{
                    color: C.muted, fontSize: 10,
                    fontFamily: 'sans-serif', whiteSpace: 'nowrap',
                  }}>
                    {item.date}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}


/* ─────────────────────────────────────────────────
   4b. Latest News Card
   ───────────────────────────────────────────────── */
function NewsCard({ data, ticker }) {
  return (
    <div style={{
      background: C.card, border: `1px solid ${C.border}`,
      borderRadius: 10, padding: '20px 22px', minHeight: 380,
      display: 'flex', flexDirection: 'column',
    }}>
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        marginBottom: 16,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{
            width: 3, height: 14, background: C.up,
            display: 'inline-block', borderRadius: 1,
          }} />
          <span style={{
            fontSize: 12, fontWeight: 800, color: C.text,
            letterSpacing: 0.5, fontFamily: 'sans-serif',
          }}>
            Latest News
          </span>
        </div>
        <span style={{
          fontSize: 9, color: C.muted, fontFamily: 'sans-serif',
          padding: '3px 8px', background: '#1a1a1a', borderRadius: 4,
        }}>
          {ticker?.toUpperCase()}
        </span>
      </div>

      <div style={{ flex: 1, overflowY: 'auto' }}>
        {data === null ? (
          <LoadingPlaceholder />
        ) : data.length === 0 ? (
          <EmptyPlaceholder text="뉴스를 불러올 수 없습니다." />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {data.map((article, idx) => (
              <a
                key={idx}
                href={article.url}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  display: 'flex', gap: 12, padding: '10px 6px',
                  textDecoration: 'none', borderRadius: 6,
                  borderBottom: idx < data.length - 1 ? `1px solid ${C.border}` : 'none',
                  cursor: 'pointer', transition: 'background 0.15s',
                }}
                onMouseEnter={e => e.currentTarget.style.background = '#151515'}
                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
              >
                {article.thumbnail && (
                  <img
                    src={article.thumbnail}
                    alt=""
                    style={{
                      width: 72, height: 48, objectFit: 'cover', borderRadius: 6,
                      flexShrink: 0, background: '#1a1a1a',
                    }}
                    onError={e => { e.target.style.display = 'none'; }}
                  />
                )}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{
                    fontSize: 12, fontWeight: 600, color: C.text, lineHeight: 1.45,
                    overflow: 'hidden', textOverflow: 'ellipsis',
                    display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
                  }}>
                    {article.title}
                  </div>
                  <div style={{
                    fontSize: 9, color: C.muted, marginTop: 4,
                    fontFamily: 'sans-serif', display: 'flex', alignItems: 'center', gap: 6,
                  }}>
                    <span style={{
                      background: '#1a1a1a', padding: '1px 5px',
                      borderRadius: 3, fontSize: 8,
                    }}>
                      {article.source}
                    </span>
                    <span style={{ color: C.dark }}>·</span>
                    <span>{article.time}</span>
                  </div>
                </div>
              </a>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}


/* ── Shared Placeholders ── */
function LoadingPlaceholder() {
  return (
    <div style={{
      display: 'flex', justifyContent: 'center', alignItems: 'center',
      height: 200, color: C.muted, fontSize: 12,
    }}>
      <div style={{ textAlign: 'center' }}>
        <div style={{
          width: 24, height: 24, border: `2px solid ${C.border}`,
          borderTop: `2px solid ${C.primary}`, borderRadius: '50%',
          animation: 'spin 0.8s linear infinite', margin: '0 auto 10px',
        }} />
        Loading...
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    </div>
  );
}

function EmptyPlaceholder({ text }) {
  return (
    <div style={{
      display: 'flex', justifyContent: 'center', alignItems: 'center',
      height: 200, color: C.muted, fontSize: 12,
      flexDirection: 'column', gap: 8,
    }}>
      <span style={{ fontSize: 24, opacity: 0.3 }}>📭</span>
      {text}
    </div>
  );
}