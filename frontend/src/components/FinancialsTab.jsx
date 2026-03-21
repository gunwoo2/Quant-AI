import React, { useState, useEffect, useMemo } from "react";
import { C, FONT, chgColor } from '../styles/tokens';
import { useOutletContext } from "react-router-dom";
import ReactECharts from "echarts-for-react";
import api from "../api";

/* ═══════════════════════════════════════════
   차트 가이드 정보 (8개)
   ═══════════════════════════════════════════ */
const CHART_INFO = {
  revenueProfits: {
    title: "Revenue & Profit (매출과 이익)",
    meaning: "회사가 얼마나 많이 팔았는지(매출)와 본업에서 실제로 얼마를 벌었는지(영업이익 또는 순이익)를 함께 보여줍니다.",
    importance: "매출 성장만으로는 기업의 질을 판단하기 어렵습니다. 매출과 함께 이익이 동반 성장하는지 확인해야 '성장의 질'을 평가할 수 있습니다.",
    criteria: "매출과 영업이익이 함께 우상향하는 구조가 이상적입니다. 매출은 증가하지만 이익이 정체되거나 감소한다면 비용 구조 악화나 경쟁 심화를 의심해야 합니다."
  },

  marginTrend: {
    title: "Margin Trend (마진 추세)",
    meaning: "매출 대비 각 이익 단계가 몇 %씩 남는지를 추적합니다. Gross(매출총이익률) → Operating(영업이익률) → Net(순이익률) → FCF(잉여현금흐름 마진).",
    importance: "마진의 방향이 기업의 '수익 체질'을 결정합니다. 매출이 성장해도 마진이 줄면 경쟁력이 약해지고 있다는 신호입니다.",
    criteria: "Gross Margin이 안정적이면서 Operating/Net Margin이 개선되는 추세가 이상적입니다. FCF Margin이 Net Margin보다 높으면 현금 창출력이 우수한 기업입니다."
  },

  earningsQuality: {
    title: "Earnings Quality (이익의 질)",
    meaning: "회계장부상 이익(Net Income)과 실제 현금(Operating Cash Flow)의 차이를 비교합니다. 이 차이(Accruals Gap)가 크면 '장부상 이익은 있지만 현금은 없는' 상태입니다.",
    importance: "Accruals Gap이 지속적으로 양수(NI > OCF)이면 매출채권·재고가 쌓이고 있거나, 공격적 회계 처리 가능성이 있습니다. 이익 조작의 첫 번째 경고 신호입니다.",
    criteria: "OCF(영업현금흐름)가 Net Income보다 높은 것이 건강합니다. Accruals Gap 라인이 0 아래에 있을수록 현금 기반의 탄탄한 이익입니다."
  },

  fcfYield: {
    title: "FCF Margin / Cash Flow (수익의 질 - 현금흐름)",
    meaning: "회계상 이익이 아니라 실제 회사 통장에 남는 '진짜 현금(Free Cash Flow, FCF)'을 확인합니다.",
    importance: "회계 이익은 조정될 수 있지만 현금 흐름은 조작이 어렵습니다. 장기적으로 FCF가 순이익과 비슷하거나 더 높다면 매우 건강한 기업입니다.",
    criteria: "FCF(녹색)가 순이익(노랑)과 비슷하거나 더 높게 유지되는 것이 이상적입니다. 이익은 나는데 현금이 마이너스라면 '가짜 수익'일 가능성이 큽니다."
  },

  roic: {
    title: "Capital Efficiency (자본 효율성 - ROIC)",
    meaning: "사업을 위해 끌어다 쓴 모든 돈(내 자본 + 빌린 부채) 100원당, 1년에 실제로 얼마의 순영업이익을 남겼는지 측정하는 지표입니다.",
    importance: "ROIC는 기업의 경쟁력과 자본 효율성을 보여주는 핵심 지표입니다. 자본 비용(WACC)보다 높은 ROIC를 지속하면 기업 가치는 장기적으로 증가합니다.",
    criteria: "일반적으로 10% 이상이면 양호, 15% 이상이면 우수, 20% 이상이면 매우 경쟁력 있는 기업으로 평가됩니다."
  },

  opLeverage: {
    title: "Operating Leverage (이익의 가속도)",
    meaning: "매출이 조금만 늘어도 이익이 폭발적으로 늘어나는 '대박 구간'에 진입했는지 확인합니다.",
    importance: "고정비 구조가 큰 산업에서는 매출이 증가할수록 이익이 더 빠르게 증가하는 '영업 레버리지'가 발생합니다.",
    criteria: "영업이익 성장률이 매출 성장률보다 빠르게 증가한다면 긍정적인 영업 레버리지가 발생하고 있는 것입니다."
  },

  solvency: {
    title: "Debt Solvency (부채 안정성)",
    meaning: "기업이 벌어들이는 현금으로 부채를 충분히 감당할 수 있는지 평가합니다.",
    importance: "금리 상승기나 경기 침체에서 기업이 생존할 수 있는 재무 안정성을 판단하는 핵심 요소입니다.",
    criteria: "순부채 막대가 아래쪽(녹색)으로 뻗어 있다면 빚보다 현금이 많은 '초우량' 상태입니다. Net Debt / EBITDA가 2 이하이면 재무 안정성이 높습니다."
  },

  ruleOf40: {
    title: "Rule of 40 (성장과 수익의 균형)",
    meaning: "매출 성장률과 FCF 마진을 합산해 기업의 성장성과 수익성을 동시에 평가하는 SaaS 산업의 핵심 지표입니다.",
    importance: "성장만 하고 돈은 못 버는지, 돈만 벌고 성장은 멈췄는지 체크하여 '균형 잡힌 우량 기업'을 골라냅니다.",
    criteria: "매출 성장률 + FCF 마진 합계가 40% 이상이면 우수합니다. 빨간 막대가 점선(40%) 위에 있을수록 좋습니다."
  },
};

/* ═══════════════════════════════════════════
   차트 드롭다운 옵션 (순서 고정)
   ═══════════════════════════════════════════ */
const CHART_OPTIONS = [
  { value: "revenueProfits", label: "① Revenue & Profit" },
  { value: "marginTrend",    label: "② Margin Trend" },
  { value: "earningsQuality",label: "③ Earnings Quality" },
  { value: "fcfYield",       label: "④ FCF / Cash Flow" },
  { value: "roic",           label: "⑤ Efficiency (ROIC)" },
  { value: "opLeverage",     label: "⑥ Operating Leverage" },
  { value: "solvency",       label: "⑦ Solvency (Debt)" },
  { value: "ruleOf40",       label: "⑧ Rule of 40" },
];


/* ═══════════════════════════════════════════
   메인 컴포넌트
   ═══════════════════════════════════════════ */
const FinancialsTab = () => {
  const { ticker } = useOutletContext();
  const [activeSubTab, setActiveSubTab] = useState("incomeStatement");
  const [period, setPeriod] = useState("annual");
  const [chartType, setChartType] = useState("revenueProfits");
  const [financialData, setFinancialData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState(false);

  useEffect(() => {
    const fetchFinancials = async () => {
      setFetchError(false);
      setLoading(true);
      try {
        const res = await api.get(`/api/stock/financials/${ticker}`, { params: { period } });
        setFinancialData(res.data);
      } catch (e) {
        console.error("Financial Data Fetch Error:", e);
        setFetchError(true);
        setFinancialData(null);
      } finally {
        setLoading(false);
      }
    };
    if (ticker) fetchFinancials();
  }, [ticker, period]);

  // ── 데이터 파싱
  const rows = useMemo(() => {
    const src = period === "annual" ? financialData?.annual : financialData?.quarterly;
    return Array.isArray(src)
      ? [...src].sort((a, b) => {
          // 연도 먼저 비교 → 같으면 분기 비교
          if (a.fiscalYear !== b.fiscalYear) return a.fiscalYear - b.fiscalYear;
          return (a.fiscalQuarter || 0) - (b.fiscalQuarter || 0);
        })
      : [];
  }, [financialData, period]);

  // ── ★ 기간 레이블: 분기별이면 "2024 Q1" 형태
  const periods = useMemo(() => {
    return rows.map(r => {
      if (period === "quarterly" && r.fiscalQuarter) {
        return `${r.fiscalYear} Q${r.fiscalQuarter}`;
      }
      return String(r.fiscalYear);
    });
  }, [rows, period]);

  // ── 테이블용 데이터
  const tableData = useMemo(() => {
    if (!rows.length) return [];
    const subMap = {
      incomeStatement: (r) => ({
        "Total Revenue":   r.incomeStatement?.revenue,
        "Gross Profit":    r.incomeStatement?.grossProfit,
        "EBIT":            r.incomeStatement?.ebit,
        "Net Income":      r.incomeStatement?.netIncome,
        "EPS (Actual)":    r.incomeStatement?.epsActual,
        "EPS (Estimated)": r.incomeStatement?.epsEstimated,
      }),
      balanceSheet: (r) => ({
        "Total Assets":  r.balanceSheet?.totalAssets,
        "Total Equity":  r.balanceSheet?.totalEquity,
        "Total Debt":    r.balanceSheet?.totalDebt,
        "Cash":          r.balanceSheet?.cash,
        "BVPS":          r.balanceSheet?.bvps,
      }),
      cashFlow: (r) => ({
        "Operating Cash Flow": r.cashFlow?.ocf,
        "Free Cash Flow":      r.cashFlow?.fcf,
        "CapEx":               r.cashFlow?.capex,
        "Dividends Paid":      r.cashFlow?.dividendsPaid,
      }),
    };
    const getter = subMap[activeSubTab];
    if (!getter) return [];
    const labels = Object.keys(getter(rows[0]));
    return labels.map(label => {
      const row = { label };
      rows.forEach((r, idx) => { row[periods[idx]] = getter(r)[label]; });
      return row;
    });
  }, [rows, activeSubTab, periods]);

  // ── keyRatios 테이블용
  const ratioData = useMemo(() => {
    if (!rows.length) return [];
    const RATIO_KEYS = [
      { key: "roic",           label: "ROIC",            pct: true  },
      { key: "gpa",            label: "GPA",             pct: false },
      { key: "fcfMargin",      label: "FCF Margin",      pct: true  },
      { key: "accrualsQuality",label: "Accruals Quality", pct: true },
      { key: "evEbit",         label: "EV/EBIT",         pct: false },
      { key: "evFcf",          label: "EV/FCF",          pct: false },
      { key: "pbRatio",        label: "P/B Ratio",       pct: false },
      { key: "pegRatio",       label: "PEG Ratio",       pct: false },
      { key: "opLeverage",     label: "Op Leverage",     pct: false },
      { key: "netDebtEbitda",  label: "Net Debt/EBITDA",  pct: false },
      { key: "assetTurnover",  label: "Asset Turnover",  pct: false },
    ];
    return RATIO_KEYS.map(({ key, label, pct }) => {
      const row = { label, pct };
      rows.forEach((r, idx) => { row[periods[idx]] = r.keyRatios?.[key]; });
      return row;
    });
  }, [rows, periods]);


  /* ═══════════════════════════════════════════
     ★ 차트 옵션 빌더 (8개 차트)
     ═══════════════════════════════════════════ */
  const chartOption = useMemo(() => {
    if (!rows || rows.length === 0) return {};

    // 데이터 추출 헬퍼
    const getVal = (pathStr) => {
      return rows.map(r => {
        const parts = pathStr.split(".");
        let cur = r;
        for (const p of parts) { if (cur == null) break; cur = cur[p]; }
        return cur ?? 0;
      });
    };

    // 마진 계산 헬퍼 (소수 → %)
    const pctArr = (nums, denoms) =>
      nums.map((n, i) => (denoms[i] && denoms[i] !== 0 ? Number(((n / denoms[i]) * 100).toFixed(2)) : 0));

    const chartYears = periods;

    // ── 차트별 시리즈 ──
    const getSeries = () => {
      switch (chartType) {

        /* ① Revenue & Profit */
        case "revenueProfits":
          return [
            { name: "Revenue (매출)",        type: "bar",  data: getVal("incomeStatement.revenue"),     itemStyle: { color: C.down } },
            { name: "Gross Profit (총이익)", type: "bar",  data: getVal("incomeStatement.grossProfit"), itemStyle: { color: C.up } },
            { name: "Net Income (순이익)",   type: "line", data: getVal("incomeStatement.netIncome"),   itemStyle: { color: C.yolk }, symbolSize: 8 },
          ];

        /* ② Margin Trend ★ */
        case "marginTrend": {
          const rev  = getVal("incomeStatement.revenue");
          const gp   = getVal("incomeStatement.grossProfit");
          const ebit = getVal("incomeStatement.ebit");
          const ni   = getVal("incomeStatement.netIncome");
          const fcfM = getVal("keyRatios.fcfMargin").map(v => Number(((v || 0) * 100).toFixed(2)));
          return [
            { name: "Gross Margin",  type: "line", data: pctArr(gp, rev),   itemStyle: { color: C.up },      lineStyle: { width: 2.5 }, symbolSize: 7, smooth: true },
            { name: "Op Margin",     type: "line", data: pctArr(ebit, rev), itemStyle: { color: C.golden },   lineStyle: { width: 2.5 }, symbolSize: 7, smooth: true },
            { name: "Net Margin",    type: "line", data: pctArr(ni, rev),   itemStyle: { color: C.yolk },     lineStyle: { width: 2.5 }, symbolSize: 7, smooth: true },
            { name: "FCF Margin",    type: "line", data: fcfM,              itemStyle: { color: C.cyan },     lineStyle: { width: 2.5, type: "dashed" }, symbolSize: 7, smooth: true },
          ];
        }

        /* ③ Earnings Quality ★ */
        case "earningsQuality": {
          const ni  = getVal("incomeStatement.netIncome");
          const ocf = getVal("cashFlow.ocf");
          const gap = ni.map((n, i) => Number((n - (ocf[i] || 0)).toFixed(0)));
          return [
            { name: "Net Income",    type: "bar",  data: ni,  itemStyle: { color: C.yolk, opacity: 0.7 } },
            { name: "OCF",           type: "bar",  data: ocf, itemStyle: { color: C.up, opacity: 0.7 } },
            { name: "Accruals Gap (NI−OCF)", type: "line", yAxisIndex: 1, data: gap, itemStyle: { color: C.pink }, lineStyle: { width: 3 }, symbolSize: 8,
              markLine: { silent: true, symbol: "none", data: [{ yAxis: 0 }], lineStyle: { color: C.textMuted, type: "dashed", width: 1 }, label: { show: false } }
            },
          ];
        }

        /* ④ FCF / Cash Flow */
        case "fcfYield":
          return [
            { name: "OCF (영업현금흐름)",    type: "bar",  data: getVal("cashFlow.ocf"), itemStyle: { color: C.yolk, opacity: 0.4 } },
            { name: "CapEx (설비투자)",       type: "bar",  data: getVal("cashFlow.capex").map(v => Math.abs(v || 0)), itemStyle: { color: C.down, opacity: 0.4 } },
            { name: "Free Cash Flow (FCF)", type: "line", data: getVal("cashFlow.fcf"), itemStyle: { color: C.up }, symbolSize: 10, lineStyle: { width: 3 } },
          ];

        /* ⑤ ROIC */
        case "roic":
          return [
            { name: "Net Income (순이익)", type: "bar", data: getVal("incomeStatement.netIncome"), itemStyle: { color: C.yolk, opacity: 0.2 } },
            { name: "ROIC (%)", type: "line", yAxisIndex: 1, smooth: true, data: getVal("keyRatios.roic").map(v => Number(((v || 0) * 100).toFixed(2))), itemStyle: { color: C.pink }, lineStyle: { width: 3 }, symbolSize: 8,
              markLine: { silent: true, symbol: "none", data: [{ yAxis: 10 }], lineStyle: { color: C.golden, type: "dashed", width: 1 }, label: { formatter: "WACC ~10%", position: "end", color: C.golden, fontSize: 10 } }
            },
            { name: "GPA", type: "line", yAxisIndex: 1, smooth: true, data: getVal("keyRatios.gpa").map(v => Number(((v || 0) * 100).toFixed(2))), itemStyle: { color: C.cyan }, lineStyle: { width: 2, type: "dotted" }, symbolSize: 6 },
          ];

        /* ⑥ Operating Leverage */
        case "opLeverage":
          return [
            { name: "Net Income (순이익)", type: "bar", data: getVal("incomeStatement.netIncome"), itemStyle: { color: C.yolk, opacity: 0.2 } },
            { name: "Op Leverage", type: "line", yAxisIndex: 1, data: getVal("keyRatios.opLeverage").map(v => Number((v || 0).toFixed(2))), itemStyle: { color: C.up }, lineStyle: { width: 3 }, symbolSize: 8 },
          ];

        /* ⑦ Solvency */
        case "solvency": {
          const totalDebt = getVal("balanceSheet.totalDebt");
          const cash = getVal("balanceSheet.cash");
          const netDebt = totalDebt.map((d, i) => d - (cash[i] || 0));
          return [
            { name: "Net Debt (순부채)", type: "bar", data: netDebt, itemStyle: { color: (p) => p.value > 0 ? C.down : C.up } },
            { name: "Net Debt/EBITDA", type: "line", yAxisIndex: 1, data: getVal("keyRatios.netDebtEbitda"), itemStyle: { color: C.white }, lineStyle: { width: 2, type: "dashed" }, symbolSize: 8 },
          ];
        }

        /* ⑧ Rule of 40 */
        case "ruleOf40": {
          const revs = getVal("incomeStatement.revenue");
          const fcfs = getVal("cashFlow.fcf");
          const r40 = revs.map((rev, i) => {
            const growth = i > 0 && revs[i - 1] > 0 ? ((rev - revs[i - 1]) / revs[i - 1]) * 100 : 0;
            const fcfMargin = rev > 0 ? (fcfs[i] / rev) * 100 : 0;
            return Number((growth + fcfMargin).toFixed(2));
          });
          return [{
            name: "Rule of 40 (%)", type: "bar", yAxisIndex: 1,
            data: r40, itemStyle: { color: (p) => p.value >= 40 ? C.up : C.golden, borderRadius: [4, 4, 0, 0] },
            markLine: { silent: true, symbol: "none", data: [{ yAxis: 40 }], lineStyle: { color: C.primary, type: "dashed", width: 2 }, label: { formatter: "Target 40%", position: "end", color: C.primary, fontSize: 10 } },
          }];
        }

        default: return [];
      }
    };

    // ── 우측 Y축 퍼센트 표시 차트 목록
    const pctCharts = ["roic", "ruleOf40", "opLeverage", "solvency", "marginTrend", "earningsQuality"];

    return {
      backgroundColor: "transparent",
      tooltip: { trigger: "axis", backgroundColor: "rgba(20,20,20,0.92)", borderColor: C.border, textStyle: { color: C.textPri, fontSize: 12, fontFamily: FONT.sans } },
      legend: { textStyle: { color: C.textGray, fontSize: 11, fontFamily: FONT.sans }, top: 0 },
      grid: { left: "3%", right: "4%", bottom: "10%", containLabel: true },
      xAxis: {
        type: "category",
        data: chartYears,
        axisLabel: {
          color: C.labelColor,
          fontSize: 11,
          fontFamily: FONT.sans,
          rotate: period === "quarterly" ? 35 : 0,
        },
      },
      yAxis: [
        {
          type: "value",
          splitLine: { lineStyle: { color: C.surfaceAlt } },
          axisLabel: {
            color: C.labelColor, fontSize: 10, fontFamily: FONT.sans,
            formatter: (v) => {
              // marginTrend는 좌축도 % 표시
              if (chartType === "marginTrend") return v.toFixed(0) + "%";
              if (Math.abs(v) >= 1e12) return (v / 1e12).toFixed(1) + "T";
              if (Math.abs(v) >= 1e9)  return (v / 1e9).toFixed(1)  + "B";
              if (Math.abs(v) >= 1e6)  return (v / 1e6).toFixed(1)  + "M";
              return v.toLocaleString();
            },
          },
        },
        {
          type: "value",
          position: "right",
          show: pctCharts.includes(chartType),
          splitLine: { show: false },
          axisLabel: { color: C.yolk, fontSize: 10, fontFamily: FONT.sans, formatter: (v) => v.toFixed(0) + "%" },
        },
      ],
      series: getSeries().map(s => ({ ...s, markLine: s.markLine || null })),
    };
  }, [chartType, rows, periods, period]);


  /* ═══════════════════════════════════════════
     스타일 헬퍼 (토큰 기반)
     ═══════════════════════════════════════════ */
  const btnStyle = (active) => ({
    padding: "8px 16px",
    backgroundColor: active ? C.primary : C.cardBg,
    color: active ? C.white : C.neutral,
    border: "1px solid",
    borderColor: active ? C.primary : C.inputBorder,
    borderRadius: 6, cursor: "pointer",
    fontSize: 12, fontWeight: 600, fontFamily: FONT.sans,
    marginLeft: 5,
  });

  const subTabStyle = (active) => ({
    padding: "12px 20px", cursor: "pointer",
    fontWeight: 700, fontSize: 14, fontFamily: FONT.sans,
    color: active ? C.primary : C.neutral,
    borderBottom: active ? `2px solid ${C.primary}` : "2px solid transparent",
    transition: "0.2s",
  });


  /* ═══════════════════════════════════════════
     렌더링
     ═══════════════════════════════════════════ */
  if (loading) return <div style={{ padding: 100, textAlign: "center", color: C.neutral, fontFamily: FONT.sans }}>LOADING...</div>;
  if (!financialData || financialData.error) return (
    <div style={{ padding: "40px 20px" }}>
      <div style={{ background: C.bgDeeper, border: `1px solid ${C.primary}40`, borderLeft: `3px solid ${C.primary}`, borderRadius: 6, padding: "12px 18px", fontSize: 12, color: C.up, fontFamily: FONT.sans }}>
        ⚠ 재무 데이터를 불러오지 못했습니다.{financialData?.error ? ` (${financialData.error})` : ""}
        <br /><span style={{ color: C.textMuted, fontSize: 11 }}>백엔드 연결 또는 ticker를 확인해주세요.</span>
      </div>
    </div>
  );

  return (
    <div style={{ padding: 20, color: C.textPri, fontFamily: FONT.sans }}>

      {/* 1. 차트 영역 */}
      <div style={{ backgroundColor: C.bgDeeper, padding: 25, borderRadius: 16, border: `1px solid ${C.cardBg}`, marginBottom: 20 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 25 }}>
          <h3 style={{ margin: 0, fontSize: 18, fontWeight: 700, fontFamily: FONT.sans }}>Financial Analysis Charts</h3>
          <select
            value={chartType}
            onChange={e => setChartType(e.target.value)}
            style={{
              backgroundColor: C.surface, color: C.textPri,
              border: `1px solid ${C.inputBorder}`, padding: "8px 12px",
              borderRadius: 8, fontSize: 13, cursor: "pointer", fontFamily: FONT.sans,
            }}
          >
            {CHART_OPTIONS.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>
        <ReactECharts
          option={chartOption}
          style={{ height: "400px" }}
          notMerge={true}
          lazyUpdate={true}
        />
      </div>

      {/* 2. 가이드 박스 */}
      <div style={{ backgroundColor: C.surface, padding: 24, borderRadius: 12, border: `1px solid ${C.border}`, borderLeft: `4px solid ${C.primary}`, marginBottom: 30 }}>
        <h4 style={{ color: C.primary, marginTop: 0, marginBottom: 15, fontSize: 16, fontFamily: FONT.sans }}>
          💡 {CHART_INFO[chartType].title} 분석 가이드
        </h4>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(250px, 1fr))", gap: 20, fontSize: 13, color: C.textSec }}>
          <div><strong style={{ color: C.labelColor, display: "block", marginBottom: 5 }}>의미</strong> {CHART_INFO[chartType].meaning}</div>
          <div><strong style={{ color: C.labelColor, display: "block", marginBottom: 5 }}>중요성</strong> {CHART_INFO[chartType].importance}</div>
        </div>
        <div style={{ marginTop: 15, padding: 12, backgroundColor: C.cardBg, borderRadius: 6, fontSize: 13, border: `1px solid ${C.border}` }}>
          <span style={{ color: C.yolk, fontWeight: "bold" }}>판단 기준:</span>{" "}{CHART_INFO[chartType].criteria}
        </div>
      </div>

      {/* 3. 탭 컨트롤 */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", borderBottom: `1px solid ${C.border}`, marginBottom: 20 }}>
        <div style={{ display: "flex" }}>
          {[
            { id: "incomeStatement", label: "Income(P&L)" },
            { id: "balanceSheet",    label: "Balance(B/S)" },
            { id: "cashFlow",        label: "Cash Flow(CFS)" },
            { id: "keyRatios",       label: "Key Ratios" },
          ].map(tab => (
            <div key={tab.id} onClick={() => setActiveSubTab(tab.id)} style={subTabStyle(activeSubTab === tab.id)}>
              {tab.label}
            </div>
          ))}
        </div>
        <div style={{ marginBottom: 10 }}>
          <button onClick={() => setPeriod("annual")} style={btnStyle(period === "annual")}>Annual(연간)</button>
          <button onClick={() => setPeriod("quarterly")} style={btnStyle(period === "quarterly")}>Quarterly(분기)</button>
        </div>
      </div>

      {/* 4. 테이블 */}
      <FinTable
        periods={periods}
        rows={activeSubTab === "keyRatios" ? ratioData : tableData}
        isRatio={activeSubTab === "keyRatios"}
      />
    </div>
  );
};


/* ═══════════════════════════════════════════
   테이블 서브 컴포넌트
   ═══════════════════════════════════════════ */
const HIGHLIGHT_LABELS = new Set([
  "Total Revenue", "Gross Profit", "Net Income", "Total Assets",
  "Free Cash Flow", "Operating Cash Flow", "ROIC", "EV/EBIT",
]);

function fmtVal(val, isRatio, pct) {
  if (val == null || val === undefined) return "-";
  const n = Number(val);
  if (isNaN(n)) return "-";
  if (isRatio) {
    if (pct) return (n * 100).toFixed(2) + "%";
    return n.toFixed(2);
  }
  return Math.round(n / 1e6).toLocaleString();
}

function FinTable({ periods, rows, isRatio }) {
  if (!rows || rows.length === 0)
    return <div style={{ padding: 40, textAlign: "center", color: C.borderHi, fontSize: 13, fontFamily: FONT.sans }}>데이터가 없습니다.</div>;

  return (
    <div style={{ overflowX: "auto", borderRadius: 12, border: `1px solid ${C.cardBg}`, backgroundColor: C.bgDeeper }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, fontFamily: FONT.sans }}>
        <thead>
          <tr style={{ backgroundColor: C.surface, borderBottom: `1px solid ${C.border}` }}>
            <th style={{
              textAlign: "left", padding: 15, position: "sticky", left: 0,
              backgroundColor: C.surface, zIndex: 10, minWidth: 220,
              color: C.labelColor, fontFamily: FONT.sans,
            }}>
              {isRatio ? "Key Ratios" : "Millions USD"}
            </th>
            {periods.map((p, idx) => (
              <th key={`${p}-${idx}`} style={{ padding: 15, textAlign: "right", color: C.textPri, minWidth: 100, fontFamily: FONT.sans }}>{p}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => {
            const hi = HIGHLIGHT_LABELS.has(row.label);
            return (
              <tr key={i}
                style={{ borderBottom: `1px solid ${C.surface}`, backgroundColor: hi ? `${C.primary}0d` : "transparent" }}
                onMouseEnter={e => e.currentTarget.style.backgroundColor = C.surfaceAlt}
                onMouseLeave={e => e.currentTarget.style.backgroundColor = hi ? `${C.primary}0d` : "transparent"}
              >
                <td style={{
                  padding: "10px 15px", color: hi ? C.primary : C.textGray,
                  fontWeight: hi ? 700 : 400, fontFamily: FONT.sans,
                  position: "sticky", left: 0, backgroundColor: C.bgDeeper,
                  borderRight: `1px solid ${C.cardBg}`, whiteSpace: "nowrap",
                }}>
                  {row.label}
                </td>
                {periods.map((p, idx) => {
                  const val = row[p];
                  return (
                    <td key={`${p}-${idx}`} style={{ padding: "10px 15px", textAlign: "right", color: hi ? C.textPri : C.textSec, fontFamily: FONT.sans }}>
                      {fmtVal(val, isRatio, row.pct)}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default FinancialsTab;