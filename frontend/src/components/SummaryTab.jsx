/**
 * SummaryTab.jsx — v5.1
 *
 * v5.1: 이전 디자인(v4) 유지 + AI Explainability(SHAP) 섹션만 추가
 *
 * 렌더 순서:
 *   1. TradingView 차트 (450px)
 *   2. Signal Strip (80px 등급 뱃지 + 큰 게이지)
 *   3. Valuation + Profitability
 *   4. ★ AI Explainability (SHAP Waterfall)
 *   5. Signal Summary + AI Rating History
 */
import React, { useState, useEffect } from "react";
import { useOutletContext } from "react-router-dom";
import TradingViewWidget from "./TradingViewWidget";
import MetricCard from "./MetricCard";
import api from "../api";
import { C, FONT, gradeColor, chgColor, signalColor } from "../styles/tokens";

const GRADE_SIGNAL = {
  S:  { label: "STRONG BUY",   color: C.cyan },
  "A+": { label: "BUY",        color: C.cyan },
  A:  { label: "OUTPERFORM",   color: C.primary },
  "B+": { label: "HOLD",       color: C.golden },
  B:  { label: "UNDERPERFORM", color: C.golden },
  C:  { label: "SELL",         color: C.down },
  D:  { label: "STRONG SELL",  color: C.gradeD },
};

function fmt(v, digits = 2) {
  return v != null ? Number(v).toFixed(digits) : null;
}

export default function SummaryTab() {
  const { ticker, realtime } = useOutletContext();
  const [ratingHistory, setRatingHistory] = useState(null);
  const [shapData, setShapData] = useState(null);
  const [shapLoading, setShapLoading] = useState(false);

  useEffect(() => {
    if (!ticker) return;
    api.get(`/api/stock/rating-history/${ticker}`)
      .then(res => setRatingHistory(res.data || []))
      .catch(() => setRatingHistory([
        { date: "2026-02-28", grade: "S",  desc: "Alpha Peak",     score: 88.4 },
        { date: "2026-02-14", grade: "A+", desc: "High Conviction", score: 80.1 },
        { date: "2026-01-31", grade: "A",  desc: "Growth Stable",   score: 71.3 },
        { date: "2025-12-28", grade: "A",  desc: "Growth Stable",   score: 68.9 },
      ]));

    /* ★ SHAP 데이터 로드 */
    setShapLoading(true);
    api.get(`/api/stock/explain/${ticker}`)
      .then(res => { setShapData(res.data); setShapLoading(false); })
      .catch(() => { setShapData(null); setShapLoading(false); });
  }, [ticker]);

  const signal = GRADE_SIGNAL[realtime?.grade] ?? { label: "N/A", color: C.textMuted };

  const valuationStats = [
    { label: "EPS (TTM)", value: fmt(realtime?.eps) ? `$${fmt(realtime.eps)}` : "N/A",
      tooltip: { title: "EPS", formula: "당기순이익 ÷ 총발행주식", meaning: "1주가 벌어들인 돈", standard: "우상향이 좋습니다." } },
    { label: "PER", value: fmt(realtime?.per) ? `${fmt(realtime.per)}x` : "N/A",
      tooltip: { title: "PER", formula: "주가 ÷ EPS", meaning: "이익 대비 주가", standard: "15~20배가 적정선." } },
    { label: "Forward PER", value: fmt(realtime?.forwardPer) ? `${fmt(realtime.forwardPer)}x` : "N/A",
      tooltip: { title: "Forward PER", formula: "주가 ÷ 예상 EPS", meaning: "미래 가치 대비 주가", standard: "현재 PER보다 낮으면 성장 신호." } },
    { label: "PBR", value: fmt(realtime?.pbr) ? `${fmt(realtime.pbr)}` : "N/A",
      tooltip: { title: "PBR", formula: "주가 ÷ BPS", meaning: "자산 대비 주가", standard: "1배 미만은 저평가." } },
  ];

  const profitabilityStats = [
    { label: "ROE", value: fmt(realtime?.roe) ? `${fmt(realtime.roe)}%` : "N/A",
      tooltip: { title: "ROE", formula: "순이익 ÷ 자기자본", meaning: "자본 효율성", standard: "15% 이상 우량." } },
    { label: "ROA", value: fmt(realtime?.roa) ? `${fmt(realtime.roa)}%` : "N/A",
      tooltip: { title: "ROA", formula: "순이익 ÷ 총자산", meaning: "자산 운용 수익률", standard: "5~10% 양호." } },
    { label: "ROIC", value: realtime?.roic != null
        ? `${(Math.abs(Number(realtime.roic)) <= 1 ? (Number(realtime.roic) * 100).toFixed(2) : Number(realtime.roic).toFixed(2))}%`
        : "N/A",
      tooltip: { title: "ROIC", formula: "NOPAT ÷ 투하자본", meaning: "투하자본 수익률", standard: "10% 이상 양호." } },
    { label: "Score (L1)", value: realtime?.l1 != null ? `${Number(realtime.l1).toFixed(1)}` : "N/A",
      tooltip: { title: "Quant Score L1", formula: "MOAT+VALUE+MOMENTUM+STABILITY", meaning: "퀀트 종합 점수", standard: "70 이상 우수." } },
  ];

  const gridStyle = {
    display: "grid", gridTemplateColumns: "repeat(4, 1fr)",
    backgroundColor: C.bgDeeper, border: `1px solid ${C.cardBg}`,
    borderRadius: 12, overflow: "hidden", marginBottom: 30,
  };

  const SectionHeader = ({ title, subTitle, question, description, color }) => (
    <div style={{ marginBottom: 15, borderTop: `2px solid ${color}`, paddingTop: 16 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6, flexWrap: "wrap" }}>
        <h3 style={{ color: C.textPri, fontSize: 15, margin: 0, fontWeight: 800, fontFamily: FONT.sans }}>{title}</h3>
        <span style={{ color: C.textMuted, fontSize: 12 }}>({subTitle})</span>
        <span style={{ background: `${color}15`, color, padding: "2px 10px", borderRadius: 4, fontSize: 11, fontWeight: 900, border: `1px solid ${color}33`, fontFamily: FONT.sans }}>{question}</span>
      </div>
      <p style={{ color: C.textGray, fontSize: 12, margin: 0, lineHeight: 1.5 }}>{description}</p>
    </div>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 25, padding: 20 }}>

      {/* ── 1. TradingView 차트 */}
      <div style={{ height: 450, backgroundColor: C.surface, borderRadius: 12, overflow: "hidden", border: `1px solid ${C.border}` }}>
        <TradingViewWidget symbol={ticker || "AAPL"} />
      </div>

      {/* ── 2. Signal Strip (차트 바로 아래) */}
      <SignalStrip signal={signal} realtime={realtime} />

      {/* ── 3. 가치평가 + 수익성 지표 */}
      <div style={{ padding: 28, backgroundColor: C.bgDark, borderRadius: 20, border: `1px solid ${C.cardBg}` }}>
        <SectionHeader title="Valuation" subTitle="가치 평가" question="Value: 주가가 저렴한가?"
          description="현재 주가가 기업의 내재가치나 이익 대비 어느 수준인지 측정합니다." color={C.primary} />
        <div style={gridStyle}>
          {valuationStats.map((s, i) => <MetricCard key={i} {...s} isLastInRow={i === 3} accentColor={C.primary} />)}
        </div>
        <SectionHeader title="Profitability" subTitle="수익성 분석" question="Quality: 돈을 얼마나 잘 버는가?"
          description="자본과 자산을 얼마나 효율적으로 사용하여 이익을 창출하는지 측정합니다." color={C.yolk} />
        <div style={gridStyle}>
          {profitabilityStats.map((s, i) => <MetricCard key={i} {...s} isLastInRow={i === 3} accentColor={C.yolk} />)}
        </div>
      </div>

      {/* ── ★ 4. AI Explainability (SHAP Waterfall) */}
      <ShapSection data={shapData} loading={shapLoading} />

      {/* ── 5. Signal Summary + AI Rating History */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 450px", gap: 24, alignItems: "start" }}>
        {/* 좌: Signal Summary */}
        <div style={{ padding: 24, backgroundColor: C.bgDeeper, border: `1px solid ${C.cardBg}`, borderRadius: 16 }}>
          <h3 style={{ color: C.textPri, fontSize: 20, fontWeight: 800, marginBottom: 18, display: "flex", alignItems: "center", gap: 8, fontFamily: FONT.sans }}>
            <span style={{ width: 3, height: 14, backgroundColor: C.primary, display: "inline-block" }} />
            Signal Summary
          </h3>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {[
              { label: "Grade",             value: realtime?.grade ?? "—",                          color: signal.color },
              { label: "Quant Score",       value: realtime?.score != null ? Number(realtime.score).toFixed(1) : "—", color: C.textPri },
              { label: "L1 (Quant)",        value: realtime?.l1 ?? "—",                             color: C.textSec },
              { label: "L2 (NLP/AI)",       value: realtime?.l2 ?? "—",                             color: C.textSec },
              { label: "L3 (Market)",       value: realtime?.l3 ?? "—",                             color: C.textSec },
              { label: "Strong Buy Signal", value: realtime?.strong_buy_signal ? "✅ YES" : "—",    color: C.up },
              { label: "Strong Sell Signal",value: realtime?.strong_sell_signal ? "🔴 YES" : "—",   color: C.down },
            ].map(row => (
              <div key={row.label} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 0", borderBottom: `1px solid ${C.cardBg}` }}>
                <span style={{ fontSize: 13, color: C.labelColor, fontFamily: FONT.sans }}>{row.label}</span>
                <span style={{ fontSize: 14, fontWeight: 800, color: row.color, fontFamily: FONT.sans }}>{row.value}</span>
              </div>
            ))}
          </div>
        </div>

        {/* 우: AI Rating History */}
        <div style={{ padding: 24, backgroundColor: C.bgDeeper, border: `1px solid ${C.cardBg}`, borderRadius: 16 }}>
          <h3 style={{ color: C.textPri, fontSize: 20, fontWeight: 800, marginBottom: 18, display: "flex", alignItems: "center", gap: 8, fontFamily: FONT.sans }}>
            <span style={{ width: 3, height: 14, backgroundColor: C.golden, display: "inline-block" }} />
            AI Rating History
          </h3>
          {!ratingHistory ? (
            <div style={{ color: C.textMuted, fontSize: 12, textAlign: "center", padding: 20, fontFamily: FONT.sans }}>LOADING...</div>
          ) : ratingHistory.length === 0 ? (
            <div style={{ color: C.textMuted, fontSize: 12, textAlign: "center", padding: 20 }}>이력 없음</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {ratingHistory.slice(0, 5).map((item, i) => {
                const gc = gradeColor(item.grade);
                return (
                  <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 10px", borderRadius: 8, backgroundColor: C.bgDark, border: `1px solid ${C.cardBg}` }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <span style={{ fontFamily: FONT.sans, fontSize: 12, fontWeight: 900, color: gc, textAlign: "center", minWidth: 32 }}>{item.grade}</span>
                      <div>
                        <div style={{ color: gc, fontWeight: 700, fontSize: 11, fontFamily: FONT.sans }}>{item.desc || ""}</div>
                        {item.score != null && (
                          <div style={{ color: C.textMuted, fontSize: 10, fontFamily: FONT.sans }}>
                            Score {typeof item.score === "number" ? item.score.toFixed(1) : item.score}
                          </div>
                        )}
                      </div>
                    </div>
                    <div style={{ color: C.textMuted, fontSize: 11, fontFamily: FONT.sans }}>{item.date}</div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}


/* ═══════════════════════════════════════════════════════
   ★ ShapSection — AI Explainability (SHAP Waterfall)
   ═══════════════════════════════════════════════════════ */
function ShapSection({ data, loading }) {
  if (loading) {
    return (
      <div style={{ padding: 28, backgroundColor: C.bgDark, borderRadius: 16, border: `1px solid ${C.cardBg}`, textAlign: "center" }}>
        <div style={{ color: C.textMuted, fontSize: 12, fontFamily: FONT.sans }}>AI 분석 로딩 중...</div>
      </div>
    );
  }

  if (!data || data.status === "NO_DATA" || data.aiScore == null) {
    return (
      <div style={{ padding: 28, backgroundColor: C.bgDark, borderRadius: 16, border: `1px solid ${C.cardBg}` }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
          <span style={{ width: 3, height: 14, backgroundColor: C.cyan, display: "inline-block" }} />
          <span style={{ fontSize: 15, fontWeight: 800, color: C.textPri, fontFamily: FONT.sans }}>🤖 AI Explainability</span>
          <span style={{ fontSize: 11, color: C.textMuted }}>XGBoost + SHAP</span>
        </div>
        <div style={{ padding: "20px 0", textAlign: "center" }}>
          <div style={{ fontSize: 12, color: C.textMuted }}>
            {data?.message || "XGBoost 분석 데이터가 아직 없습니다. 배치 실행 후 표시됩니다."}
          </div>
        </div>
      </div>
    );
  }

  const topPos = data.topPositive || [];
  const topNeg = data.topNegative || [];
  const maxShap = Math.max(
    ...topPos.map(p => Math.abs(p.shap || 0)),
    ...topNeg.map(n => Math.abs(n.shap || 0)),
    1
  );

  const aiColor = data.aiScore >= 70 ? C.up : data.aiScore >= 50 ? C.golden : data.aiScore >= 35 ? C.primary : C.down;

  return (
    <div style={{ padding: 28, backgroundColor: C.bgDark, borderRadius: 20, border: `1px solid ${C.cardBg}` }}>
      {/* 헤더 — v4 스타일 borderTop */}
      <div style={{ marginBottom: 20, borderTop: `2px solid ${C.cyan}`, paddingTop: 16 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
          <h3 style={{ color: C.textPri, fontSize: 15, margin: 0, fontWeight: 800, fontFamily: FONT.sans }}>🤖 AI Explainability</h3>
          <span style={{ color: C.textMuted, fontSize: 12 }}>(XGBoost + SHAP)</span>
          <span style={{ background: `${C.cyan}15`, color: C.cyan, padding: "2px 10px", borderRadius: 4, fontSize: 11, fontWeight: 900, border: `1px solid ${C.cyan}33`, fontFamily: FONT.sans }}>
            AI: 왜 이 등급인가?
          </span>
          <span style={{ marginLeft: "auto", fontSize: 11, color: C.textMuted, fontFamily: FONT.sans }}>{data.calcDate}</span>
        </div>
        <p style={{ color: C.textGray, fontSize: 12, margin: 0, lineHeight: 1.5 }}>
          XGBoost 모델이 퀀트 점수를 예측하고, SHAP이 각 팩터의 기여도를 분해합니다.
        </p>
      </div>

      {/* AI Score 카드 4개 */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 28 }}>
        <div style={{ padding: "16px 18px", background: `${aiColor}08`, border: `1px solid ${aiColor}30`, borderRadius: 12, borderLeft: `3px solid ${aiColor}` }}>
          <div style={{ fontSize: 11, color: C.textMuted, marginBottom: 6, fontFamily: FONT.sans }}>AI Score</div>
          <div style={{ fontSize: 32, fontWeight: 900, color: aiColor, fontFamily: FONT.sans }}>{data.aiScore?.toFixed(1)}</div>
        </div>
        <div style={{ padding: "16px 18px", background: C.bgDeeper, border: `1px solid ${C.cardBg}`, borderRadius: 12 }}>
          <div style={{ fontSize: 11, color: C.textMuted, marginBottom: 6, fontFamily: FONT.sans }}>Ensemble Score</div>
          <div style={{ fontSize: 32, fontWeight: 900, color: C.textPri, fontFamily: FONT.sans }}>{data.ensembleScore?.toFixed(1) ?? "—"}</div>
        </div>
        <div style={{ padding: "16px 18px", background: C.bgDeeper, border: `1px solid ${C.cardBg}`, borderRadius: 12 }}>
          <div style={{ fontSize: 11, color: C.textMuted, marginBottom: 6, fontFamily: FONT.sans }}>Stat Score (기존)</div>
          <div style={{ fontSize: 32, fontWeight: 900, color: C.textPri, fontFamily: FONT.sans }}>{data.statScore?.toFixed(1) ?? "—"}</div>
        </div>
        <div style={{ padding: "16px 18px", background: C.bgDeeper, border: `1px solid ${C.cardBg}`, borderRadius: 12 }}>
          <div style={{ fontSize: 11, color: C.textMuted, marginBottom: 6, fontFamily: FONT.sans }}>AI Weight</div>
          <div style={{ fontSize: 32, fontWeight: 900, color: C.cyan, fontFamily: FONT.sans }}>{data.aiWeight != null ? `${(data.aiWeight * 100).toFixed(0)}%` : "—"}</div>
          <div style={{ fontSize: 10, color: C.textMuted, marginTop: 2 }}>base = {data.baseValue?.toFixed(1)}</div>
        </div>
      </div>

      {/* SHAP Waterfall — 좌우 2열 */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
        {/* 상승 기여 요인 */}
        <div>
          <div style={{ fontSize: 13, fontWeight: 700, color: C.up, marginBottom: 12, fontFamily: FONT.sans }}>
            📈 상승 기여 요인 (Positive SHAP)
          </div>
          {topPos.length > 0 ? topPos.map((p, i) => {
            const pct = Math.abs(p.shap || 0) / maxShap * 100;
            return (
              <div key={i} style={{ marginBottom: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                  <span style={{ fontSize: 12, color: C.textPri }}>{p.feature || p.raw}</span>
                  <span style={{ fontSize: 13, fontWeight: 800, color: C.up, fontFamily: FONT.sans }}>+{(p.shap || 0).toFixed(1)}</span>
                </div>
                <div style={{ height: 6, background: C.cardBg, borderRadius: 3 }}>
                  <div style={{ width: `${pct}%`, height: "100%", background: C.up, borderRadius: 3, transition: "width 0.5s" }} />
                </div>
              </div>
            );
          }) : <div style={{ fontSize: 12, color: C.textMuted }}>데이터 없음</div>}
        </div>

        {/* 하락 기여 요인 */}
        <div>
          <div style={{ fontSize: 13, fontWeight: 700, color: C.down, marginBottom: 12, fontFamily: FONT.sans }}>
            📉 하락 기여 요인 (Negative SHAP)
          </div>
          {topNeg.length > 0 ? topNeg.map((n, i) => {
            const pct = Math.abs(n.shap || 0) / maxShap * 100;
            return (
              <div key={i} style={{ marginBottom: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                  <span style={{ fontSize: 12, color: C.textPri }}>{n.feature || n.raw}</span>
                  <span style={{ fontSize: 13, fontWeight: 800, color: C.down, fontFamily: FONT.sans }}>{(n.shap || 0).toFixed(1)}</span>
                </div>
                <div style={{ height: 6, background: C.cardBg, borderRadius: 3 }}>
                  <div style={{ width: `${pct}%`, height: "100%", background: C.down, borderRadius: 3, transition: "width 0.5s" }} />
                </div>
              </div>
            );
          }) : <div style={{ fontSize: 12, color: C.textMuted }}>데이터 없음</div>}
        </div>
      </div>

      {/* 산식 설명 */}
      <div style={{ marginTop: 20, padding: "10px 14px", background: C.bgDeeper, borderRadius: 8, fontSize: 11, color: C.textMuted, fontFamily: FONT.sans }}>
        ⓘ base_value({data.baseValue?.toFixed(1)}) + Σ positive_shap + Σ negative_shap = AI Score({data.aiScore?.toFixed(1)})
        &nbsp;&nbsp;·&nbsp;&nbsp;Ensemble = stat×{data.aiWeight != null ? (1-data.aiWeight).toFixed(2) : "?"} + ai×{data.aiWeight?.toFixed(2) ?? "?"}
      </div>
    </div>
  );
}


/* ═══════════════════════════════════════════════════════
   SignalStrip — 차트 바로 아래 시그널 바 (v4 원본 디자인)
   ═══════════════════════════════════════════════════════ */
function SignalStrip({ signal, realtime }) {
  if (!realtime) return null;

  const score = realtime.score != null ? Number(realtime.score).toFixed(1) : null;
  const grade = realtime.grade ?? "—";
  const gc = gradeColor(grade);

  const layers = [
    { key: "L1", val: realtime.l1, label: "Quant",  color: C.primary },
    { key: "L2", val: realtime.l2, label: "NLP",    color: C.pink },
    { key: "L3", val: realtime.l3, label: "Market", color: C.cyan },
  ];

  return (
    <div style={{
      display: "flex", alignItems: "center", justifyContent: "space-between",
      padding: "30px 24px",
      background: C.bgDeeper,
      border: `2px solid ${C.cardBg}`,
      borderRadius: 12,
      gap: 20,
    }}>

      {/* 좌측: 등급 뱃지 + 시그널 라벨 */}
      <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
        <div style={{
          width: 80, height: 80, borderRadius: 10,
          background: `${gc}18`, border: `2px solid ${gc}55`,
          display: "flex", alignItems: "center", justifyContent: "center",
          fontFamily: FONT.sans, fontSize: 45, fontWeight: 900, color: gc,
        }}>
          {grade}
        </div>
        <div>
          <div style={{ fontSize: 9, color: C.textMuted, letterSpacing: 2, fontFamily: FONT.sans, marginBottom: 2 }}>
            QUANT AI · SIGNAL
          </div>
          <div style={{ fontSize: 30, fontWeight: 900, color: signal.color, fontFamily: FONT.sans, letterSpacing: 1.5 }}>
            {signal.label}
          </div>
        </div>
      </div>

      {/* 중앙: 종합 점수 게이지 */}
      {score && (
        <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
          <div style={{ position: "relative", width: 80, height: 80 }}>
            <svg width="80" height="80" viewBox="0 0 80 80">
              <circle cx="40" cy="40" r="36" fill="none" stroke={C.border} strokeWidth="5" />
              <circle cx="40" cy="40" r="36" fill="none" stroke={gc} strokeWidth="5"
                strokeDasharray={`${(score / 100) * 226.2} 226.2`}
                strokeLinecap="round" transform="rotate(-90 40 40)"
                style={{ transition: "stroke-dasharray 0.8s ease" }}
              />
            </svg>
            <div style={{
              position: "absolute", inset: 0,
              display: "flex", alignItems: "center", justifyContent: "center",
              fontFamily: FONT.sans, fontSize: 22, fontWeight: 900, color: gc,
            }}>
              {score}
            </div>
          </div>
          <div>
            <div style={{ fontSize: 10, color: C.textMuted, letterSpacing: 1.5, fontFamily: FONT.sans }}>TOTAL</div>
            <div style={{ fontSize: 10, color: C.textMuted, letterSpacing: 1.5, fontFamily: FONT.sans }}>SCORE</div>
          </div>
        </div>
      )}

      {/* 구분선 */}
      <div style={{ width: 1, height: 36, background: C.border }} />

      {/* 우측: L1 / L2 / L3 미니 카드 */}
      <div style={{ display: "flex", gap: 10 }}>
        {layers.map(l => (
          <div key={l.key} style={{
            minWidth: 85, textAlign: "center",
            padding: "12px 14px", borderRadius: 10,
            background: C.bgDark,
            border: `1px solid ${C.cardBg}`,
            transition: "all 0.2s ease",
          }}
            onMouseEnter={e => {
              e.currentTarget.style.borderColor = l.color + "99";
              e.currentTarget.style.transform = "translateY(-2px)";
            }}
            onMouseLeave={e => {
              e.currentTarget.style.borderColor = C.cardBg;
              e.currentTarget.style.transform = "translateY(0)";
            }}
          >
            <div style={{ fontSize: 10, color: C.textMuted, letterSpacing: 2, fontFamily: FONT.sans, marginBottom: 5 }}>{l.key}</div>
            <div style={{ fontSize: 24, fontWeight: 800, color: l.val != null ? l.color : C.border, fontFamily: FONT.sans, lineHeight: 1 }}>
              {l.val != null ? Number(l.val).toFixed(1) : "—"}
            </div>
            <div style={{ fontSize: 9, color: C.textMuted, marginTop: 6, fontFamily: FONT.sans, opacity: 0.8 }}>{l.label}</div>
          </div>
        ))}
      </div>
    </div>
  );
}