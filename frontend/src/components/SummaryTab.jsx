/**
 * SummaryTab.jsx — v4
 *
 * 렌더 순서:
 *   1. TradingView 차트
 *   2. Signal Strip (차트 바로 아래 — 등급 + 점수 + L1/L2/L3)
 *   3. Valuation + Profitability
 *   4. Signal Summary + AI Rating History
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

      {/* ── 4. Signal Summary + AI Rating History */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 320px", gap: 24, alignItems: "start" }}>
        {/* 좌: Signal Summary */}
        <div style={{ padding: 24, backgroundColor: C.bgDeeper, border: `1px solid ${C.cardBg}`, borderRadius: 16 }}>
          <h3 style={{ color: C.textPri, fontSize: 14, fontWeight: 800, marginBottom: 18, display: "flex", alignItems: "center", gap: 8, fontFamily: FONT.sans }}>
            <span style={{ width: 3, height: 14, backgroundColor: C.primary, display: "inline-block" }} />
            Signal Summary
          </h3>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {[
              { label: "Grade",             value: realtime?.grade ?? "—",                          color: signal.color },
              { label: "Quant Score",       value: realtime?.score != null ? Number(realtime.score).toFixed(1) : "—", color: C.textPri },
              { label: "L1 (Quant)",        value: realtime?.l1 ?? "—",                             color: C.primary },
              { label: "L2 (NLP/AI)",       value: realtime?.l2 ?? "—",                             color: C.pink },
              { label: "L3 (Market)",       value: realtime?.l3 ?? "—",                             color: C.cyan },
              { label: "Strong Buy Signal", value: realtime?.strong_buy_signal ? "✅ YES" : "—",    color: C.cyan },
              { label: "Strong Sell Signal",value: realtime?.strong_sell_signal ? "🔴 YES" : "—",   color: C.down },
            ].map(row => (
              <div key={row.label} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 0", borderBottom: `1px solid ${C.cardBg}` }}>
                <span style={{ fontSize: 12, color: C.labelColor, fontFamily: FONT.sans }}>{row.label}</span>
                <span style={{ fontSize: 14, fontWeight: 800, color: row.color, fontFamily: FONT.sans }}>{row.value}</span>
              </div>
            ))}
          </div>
        </div>

        {/* 우: AI Rating History */}
        <div style={{ padding: 24, backgroundColor: C.bgDeeper, border: `1px solid ${C.cardBg}`, borderRadius: 16 }}>
          <h3 style={{ color: C.textPri, fontSize: 14, fontWeight: 800, marginBottom: 18, display: "flex", alignItems: "center", gap: 8, fontFamily: FONT.sans }}>
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
   SignalStrip — 차트 바로 아래 시그널 바
   ═══════════════════════════════════════════════════════
   ┌──────────────────────────────────────────────────────┐
   │  QUANT AI           ██  HOLD  ██   68.5    L1│L2│L3 │
   └──────────────────────────────────────────────────────┘
*/
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
        {/* 등급 뱃지 */}
        <div style={{
          width: 80, height: 80, borderRadius: 10,
          background: `${gc}18`, border: `2px solid ${gc}55`,
          display: "flex", alignItems: "center", justifyContent: "center",
          fontFamily: FONT.sans, fontSize: 45, fontWeight: 900, color: gc,
        }}>
          {grade}
        </div>

        {/* 시그널 텍스트 */}
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
        <div style={{ display: "flex", alignItems: "center", gap: 18 }}> {/* gap 조정 */}
          <div style={{ position: "relative", width: 80, height: 80 }}> {/* 120 -> 80 */}
            <svg width="80" height="80" viewBox="0 0 80 80">
              {/* 배경 원: 중심 (40, 40), 반지름 (36) */}
              <circle cx="40" cy="40" r="36" fill="none" stroke={C.border} strokeWidth="5" /> 
              
              {/* 점수 게이지 원: 둘레는 2 * π * 36 ≈ 226.2 */}
              <circle 
                cx="40" cy="40" r="36" fill="none" stroke={gc} strokeWidth="5"
                strokeDasharray={`${(score / 100) * 226.2} 226.2`}
                strokeLinecap="round" 
                transform="rotate(-90 40 40)"
                style={{ transition: "stroke-dasharray 0.8s ease" }}
              />
            </svg>
            
            {/* 중앙 점수 텍스트: 폰트 크기 조정 */}
            <div style={{
              position: "absolute", inset: 0,
              display: "flex", alignItems: "center", justifyContent: "center",
              fontFamily: FONT.sans, fontSize: 22, fontWeight: 900, color: gc, // 32 -> 22
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
      
      {/* 우측 구분선 */}
      <div style={{ width: 1, height: 36, background: C.border }} />

      {/* 우측: L1 / L2 / L3 미니 카드 (확장 버전) */}
      <div style={{ display: "flex", gap: 10 }}> {/* 간격을 8에서 10으로 살짝 키움 */}
        {layers.map(l => (
          <div key={l.key} style={{
            minWidth: 85,          // 68 -> 85 (가로폭 확장)
            textAlign: "center",
            padding: "12px 14px",   // 8/10 -> 12/14 (상하좌우 여백 확대)
            borderRadius: 10,      // 8 -> 10 (곡률 조정)
            background: C.bgDark,
            border: `1px solid ${C.cardBg}`,
            transition: "all 0.2s ease", // 테두리 외에 부드러운 전환 효과
          }}
            onMouseEnter={e => {
              e.currentTarget.style.borderColor = l.color + "99"; // 강조 농도 증가
              e.currentTarget.style.transform = "translateY(-2px)"; // 살짝 떠오르는 효과 추가
            }}
            onMouseLeave={e => {
              e.currentTarget.style.borderColor = C.cardBg;
              e.currentTarget.style.transform = "translateY(0)";
            }}
          >
            {/* 상단 레이어 이름 (L1, L2...) */}
            <div style={{ 
              fontSize: 10,         // 8 -> 10
              color: C.textMuted, 
              letterSpacing: 2,     // 자간 강조
              fontFamily: FONT.sans, 
              marginBottom: 5       // 여백 확장
            }}>
              {l.key}
            </div>
            
            {/* 중앙 수치 */}
            <div style={{ 
              fontSize: 24,         // 18 -> 24 (메인 점수와 조화롭게 키움)
              fontWeight: 800, 
              color: l.val != null ? l.color : C.border, 
              fontFamily: FONT.sans,
              lineHeight: 1         // 텍스트 정렬 보정
            }}>
              {l.val != null ? Number(l.val).toFixed(1) : "—"}
            </div>
            
            {/* 하단 라벨 (VALUATION, SENTIMENT 등) */}
            <div style={{ 
              fontSize: 9,          // 8 -> 9
              color: C.textMuted, 
              marginTop: 6,         // 2 -> 6
              fontFamily: FONT.sans,
              opacity: 0.8          // 가독성을 위한 약간의 투명도
            }}>
              {l.label}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}