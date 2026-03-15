import React, { useState, useEffect, useMemo } from "react";
import { useOutletContext } from "react-router-dom";
import ReactECharts from "echarts-for-react";
import api from "../api";

/* ═══════════════════════════════════════════════
   Chart Info — 분석 가이드 텍스트
   ═══════════════════════════════════════════════ */
const CHART_INFO = {
  revenueProfits: {
    title: "Revenue & Profit (매출과 이익)",
    meaning: "회사가 얼마나 많이 팔았는지(매출)와 본업에서 실제로 얼마를 벌었는지(영업이익 또는 순이익)를 함께 보여줍니다.",
    importance: "매출 성장만으로는 기업의 질을 판단하기 어렵습니다. 매출과 함께 이익이 동반 성장하는지 확인해야 '성장의 질'을 평가할 수 있습니다.",
    criteria: "매출과 영업이익이 함께 우상향하는 구조가 이상적입니다. 매출은 증가하지만 이익이 정체되거나 감소한다면 비용 구조 악화나 경쟁 심화를 의심해야 합니다."
  },
  marginTrend: {
    title: "Margin Trend (마진 추세)",
    meaning: "매출 대비 이익의 비율(마진)이 시간이 지나면서 어떻게 변하는지 추적합니다. Gross Margin, Operating Margin, Net Margin, FCF Margin을 한눈에 비교합니다.",
    importance: "마진 개선은 가격결정력, 비용 효율화, 규모의 경제를 반영합니다. 퀀트 모델에서 마진 확장 기업은 시장 평균을 초과하는 수익률을 보이는 경향이 있습니다.",
    criteria: "4개 마진 모두 우상향이면 최고입니다. Gross Margin은 안정적인데 Net Margin이 하락하면 비영업 비용(이자, 세금)에 문제가 있을 수 있습니다. FCF Margin이 Net Margin보다 높으면 이익의 질이 우수합니다."
  },
  earningsQuality: {
    title: "Earnings Quality (이익의 질 — 현금 전환 검증)",
    meaning: "회계상 순이익(Net Income)과 실제 영업에서 들어온 현금(OCF)의 차이(Accruals Gap)를 시각화합니다. 차이가 클수록 이익의 질이 낮습니다.",
    importance: "퀀트 팩터 중 'Quality Factor'의 핵심입니다. 발생액(Accruals)이 큰 기업은 미래 수익률이 낮은 경향이 있으며, 이를 '발생액 이상현상(Accrual Anomaly)'이라 합니다. 반대로 OCF > NI인 기업은 보수적으로 회계 처리하는 고품질 기업입니다.",
    criteria: "OCF(파란색)가 Net Income(노란색)보다 항상 높으면 최고입니다. Accruals Gap(빨간 영역)이 넓어지면 이익 조작 또는 운전자본 악화를 의심해야 합니다. Accruals/Assets 비율이 -5%~+5% 이내면 양호합니다."
  },
  fcfYield: {
    title: "FCF Margin / Cash Flow (수익의 질 - 현금흐름)",
    meaning: "회계상 이익이 아니라 실제 회사 통장에 남는 '진짜 현금(Free Cash Flow, FCF)'을 확인합니다.",
    importance: "회계 이익은 조정될 수 있지만 현금 흐름은 조작이 어렵습니다. 장기적으로 FCF가 순이익과 비슷하거나 더 높다면 매우 건강한 기업입니다.",
    criteria: "FCF(녹색)가 순이익(노랑)과 비슷하거나 더 높게 유지되는 것이 이상적입니다. 이익은 나는데 현금이 마이너스라면 '가짜 수익'일 가능성이 큽니다."
  },
  roic: {
    title: "Capital Efficiency (자본 효율성 - ROIC)",
    meaning: "사업을 위해 끌어다 쓴 모든 돈(내 자본 + 빌린 부채) 100원당, 1년에 실제로 얼마의 순영업이익을 남겼는지 측정합니다.",
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
    criteria: "순부채 막대가 아래쪽(녹색)이면 빚보다 현금이 많은 '초우량' 상태입니다. Net Debt / EBITDA가 2 이하이면 재무 안정성이 높습니다."
  },
  ruleOf40: {
    title: "Rule of 40 (성장과 수익의 균형)",
    meaning: "매출 성장률과 FCF 마진을 합산해 기업의 성장성과 수익성을 동시에 평가하는 핵심 지표입니다.",
    importance: "성장만 하고 돈은 못 버는지, 돈만 벌고 성장은 멈췄는지 체크합니다.",
    criteria: "매출 성장률 + FCF 마진이 40%를 넘으면 성장과 수익 균형이 잡힌 우량 기업입니다."
  },
};

/* ═══════════════════════════════════════════════
   Table label → 한글 매핑
   ═══════════════════════════════════════════════ */
const KOR_MAP = {
  // Income Statement
  'Total Revenue': '총 매출', 'Gross Profit': '매출 총이익', 'EBIT': '영업이익',
  'Net Income': '순이익', 'EPS (Actual)': '실적 EPS', 'EPS (Estimated)': '예상 EPS',
  // Balance Sheet
  'Total Assets': '총 자산', 'Total Equity': '자기자본', 'Total Debt': '총 부채',
  'Cash': '현금', 'BVPS': '주당 순자산',
  // Cash Flow
  'Operating Cash Flow': '영업현금흐름', 'Free Cash Flow': '잉여현금흐름(FCF)',
  'CapEx': '자본적 지출', 'Dividends Paid': '배당금 지급',
  // Key Ratios
  'ROIC': '투하자본수익률', 'GPA': '매출총이익/자산', 'FCF Margin': 'FCF 마진',
  'Accruals Quality': '발생액 품질', 'EV/EBIT': 'EV/EBIT', 'EV/FCF': 'EV/FCF',
  'P/B Ratio': '주가순자산비율', 'PEG Ratio': 'PEG', 'Op Leverage': '영업 레버리지',
  'Net Debt/EBITDA': '순부채/EBITDA', 'Asset Turnover': '총자산회전율',
};


/* ═══════════════════════════════════════════════
   Highlight rows
   ═══════════════════════════════════════════════ */
const HIGHLIGHT_LABELS = new Set([
  "Total Revenue", "Gross Profit", "Net Income", "Total Assets",
  "Free Cash Flow", "Operating Cash Flow", "ROIC", "EV/EBIT",
]);


/* ═══════════════════════════════════════════════
   Main Component
   ═══════════════════════════════════════════════ */
const FinancialsTab = () => {
  const { ticker } = useOutletContext();
  const [activeSubTab, setActiveSubTab] = useState("incomeStatement");
  const [period, setPeriod] = useState("quarterly");          // ★ 기본값: 분기
  const [chartType, setChartType] = useState("revenueProfits");
  const [financialData, setFinancialData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!ticker) return;
    setLoading(true);
    (async () => {
      try {
        const res = await api.get(`/api/stock/financials/${ticker}`, { params: { period } });
        setFinancialData(res.data);
      } catch (e) {
        console.error("financials fetch error", e);
        setFinancialData({ error: String(e) });
      } finally {
        setLoading(false);
      }
    })();
  }, [ticker, period]);

  /* ── rows 정렬 ── */
  const rows = useMemo(() => {
    const src = period === 'annual' ? financialData?.annual : financialData?.quarterly;
    if (!Array.isArray(src)) return [];
    return [...src].sort((a, b) => {
      if (a.fiscalYear !== b.fiscalYear) return a.fiscalYear - b.fiscalYear;
      return (a.fiscalQuarter || 0) - (b.fiscalQuarter || 0);
    });
  }, [financialData, period]);

  /* ── 기간 레이블 (차트 x축, 테이블 헤더) ── */
  const periods = useMemo(() => {
    return rows.map(r => {
      if (period === 'quarterly' && r.fiscalQuarter) {
        return `${r.fiscalYear} Q${r.fiscalQuarter}`;
      }
      return String(r.fiscalYear);
    });
  }, [rows, period]);

  /* ── 테이블 데이터 ── */
  const tableData = useMemo(() => {
    if (!rows.length) return [];
    const subMap = {
      incomeStatement: (r) => ({
        'Total Revenue':    r.incomeStatement?.revenue,
        'Gross Profit':     r.incomeStatement?.grossProfit,
        'EBIT':             r.incomeStatement?.ebit,
        'Net Income':       r.incomeStatement?.netIncome,
        'EPS (Actual)':     r.incomeStatement?.epsActual,
        'EPS (Estimated)':  r.incomeStatement?.epsEstimated,
      }),
      balanceSheet: (r) => ({
        'Total Assets':     r.balanceSheet?.totalAssets,
        'Total Equity':     r.balanceSheet?.totalEquity,
        'Total Debt':       r.balanceSheet?.totalDebt,
        'Cash':             r.balanceSheet?.cash,
        'BVPS':             r.balanceSheet?.bvps,
      }),
      cashFlow: (r) => ({
        'Operating Cash Flow': r.cashFlow?.ocf,
        'Free Cash Flow':      r.cashFlow?.fcf,
        'CapEx':               r.cashFlow?.capex,
        'Dividends Paid':      r.cashFlow?.dividendsPaid,
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

  /* ── Key Ratios 테이블 ── */
  const ratioData = useMemo(() => {
    if (!rows.length) return [];
    const RATIO_KEYS = [
      { key: 'roic',           label: 'ROIC',              pct: true  },
      { key: 'gpa',            label: 'GPA',               pct: false },
      { key: 'fcfMargin',      label: 'FCF Margin',        pct: true  },
      { key: 'accrualsQuality',label: 'Accruals Quality',  pct: true  },
      { key: 'evEbit',         label: 'EV/EBIT',           pct: false },
      { key: 'evFcf',          label: 'EV/FCF',            pct: false },
      { key: 'pbRatio',        label: 'P/B Ratio',         pct: false },
      { key: 'pegRatio',       label: 'PEG Ratio',         pct: false },
      { key: 'opLeverage',     label: 'Op Leverage',       pct: false },
      { key: 'netDebtEbitda',  label: 'Net Debt/EBITDA',   pct: false },
      { key: 'assetTurnover',  label: 'Asset Turnover',    pct: false },
    ];
    return RATIO_KEYS.map(({ key, label, pct }) => {
      const row = { label, pct };
      rows.forEach((r, idx) => { row[periods[idx]] = r.keyRatios?.[key]; });
      return row;
    });
  }, [rows, periods]);

  /* ═══════════════════════════════════════════════
     Chart Options
     ═══════════════════════════════════════════════ */
  const chartOption = useMemo(() => {
    if (!rows || rows.length === 0) return {};

    const getVal = (pathStr) => {
      return rows.map(r => {
        const parts = pathStr.split('.');
        let current = r;
        for (const part of parts) {
          if (current == null) break;
          current = current[part];
        }
        return current ?? 0;
      });
    };

    const getSeries = () => {
      switch (chartType) {
        case "revenueProfits":
          return [
            { name: "Revenue (매출)", type: "bar", data: getVal('incomeStatement.revenue'), itemStyle: { color: '#3b82f6' } },
            { name: "Gross Profit (총이익)", type: "bar", data: getVal('incomeStatement.grossProfit'), itemStyle: { color: '#10b981' } },
            { name: "Net Income (순이익)", type: "line", data: getVal('incomeStatement.netIncome'), itemStyle: { color: '#fbbf24' }, symbolSize: 8 }
          ];

        case "marginTrend": {
          const rev = getVal('incomeStatement.revenue');
          const gp  = getVal('incomeStatement.grossProfit');
          const ebit = getVal('incomeStatement.ebit');
          const ni  = getVal('incomeStatement.netIncome');
          const fcf = getVal('cashFlow.fcf');
          const pct = (arr) => arr.map((v, i) => rev[i] ? Number(((v / rev[i]) * 100).toFixed(2)) : 0);
          return [
            { name: "Gross Margin (%)", type: "line", data: pct(gp), itemStyle: { color: '#3b82f6' }, symbolSize: 6, lineStyle: { width: 2.5 } },
            { name: "Operating Margin (%)", type: "line", data: pct(ebit), itemStyle: { color: '#10b981' }, symbolSize: 6, lineStyle: { width: 2.5 } },
            { name: "Net Margin (%)", type: "line", data: pct(ni), itemStyle: { color: '#fbbf24' }, symbolSize: 6, lineStyle: { width: 2.5 } },
            { name: "FCF Margin (%)", type: "line", data: pct(fcf), itemStyle: { color: '#f472b6' }, symbolSize: 6, lineStyle: { width: 2, type: 'dashed' } },
          ];
        }

        case "earningsQuality": {
          const ni  = getVal('incomeStatement.netIncome');
          const ocf = getVal('cashFlow.ocf');
          const ta  = getVal('balanceSheet.totalAssets');
          const accruals = ni.map((n, i) => n - (ocf[i] || 0));
          const accrualsPct = accruals.map((a, i) => ta[i] ? Number(((a / ta[i]) * 100).toFixed(2)) : 0);
          return [
            { name: "OCF (영업현금흐름)", type: "bar", data: ocf, itemStyle: { color: '#3b82f6' }, barGap: '10%' },
            { name: "Net Income (순이익)", type: "bar", data: ni, itemStyle: { color: '#fbbf24' }, barGap: '10%' },
            {
              name: "Accruals/Assets (%)", type: "line", yAxisIndex: 1, data: accrualsPct,
              itemStyle: { color: '#ef4444' }, lineStyle: { width: 2.5 }, symbolSize: 8,
              markLine: { silent: true, symbol: "none", data: [{ yAxis: 5 }, { yAxis: -5 }], lineStyle: { color: "#10b981", type: "dashed", width: 1.5 }, label: { formatter: "Safe Zone", position: "end", color: "#10b981", fontSize: 10 } },
            }
          ];
        }

        case "fcfYield":
          return [
            { name: "OCF (영업현금흐름)", type: "bar", data: getVal('cashFlow.ocf'), itemStyle: { color: '#fbbf24', opacity: 0.4 } },
            { name: "Free Cash Flow (FCF)", type: "line", data: getVal('cashFlow.fcf'), itemStyle: { color: '#10b981' }, symbolSize: 10 },
            { name: "Net Income (순이익)", type: "line", data: getVal('incomeStatement.netIncome'), itemStyle: { color: '#fbbf24' }, symbolSize: 8, lineStyle: { type: 'dashed' } }
          ];

        case "roic": {
          const roicArr = getVal('keyRatios.roic').map(v => Number((v * 100).toFixed(2)));
          return [{
            name: "ROIC (%)", type: "line", yAxisIndex: 1, data: roicArr,
            itemStyle: { color: '#10b981' }, symbolSize: 10, lineStyle: { width: 3 },
            areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(16,185,129,0.3)' }, { offset: 1, color: 'transparent' }] } },
            markLine: { silent: true, symbol: "none", data: [{ yAxis: 15 }], lineStyle: { color: "#D85604", type: "dashed", width: 2 }, label: { formatter: "Good 15%", position: "end", color: "#D85604" } }
          }];
        }

        case "opLeverage": {
          const rev = getVal('incomeStatement.revenue');
          const ebit = getVal('incomeStatement.ebit');
          const revGr = rev.map((v, i) => i > 0 && rev[i-1] > 0 ? ((v - rev[i-1]) / rev[i-1]) * 100 : 0);
          const ebitGr = ebit.map((v, i) => i > 0 && ebit[i-1] !== 0 ? ((v - ebit[i-1]) / Math.abs(ebit[i-1])) * 100 : 0);
          const opLev = revGr.map((v, i) => v !== 0 ? Number((ebitGr[i] / v).toFixed(2)) : 0);
          return [
            { name: "Revenue Growth (%)", type: "bar", yAxisIndex: 1, data: revGr.map(v => Number(v.toFixed(2))), itemStyle: { color: '#3b82f6', opacity: 0.6 } },
            { name: "EBIT Growth (%)", type: "bar", yAxisIndex: 1, data: ebitGr.map(v => Number(v.toFixed(2))), itemStyle: { color: '#10b981', opacity: 0.6 } },
            { name: "Op Leverage (배수)", type: "line", data: opLev, itemStyle: { color: '#fbbf24' }, symbolSize: 8 }
          ];
        }

        case "solvency": {
          const debt = getVal('balanceSheet.totalDebt');
          const cash = getVal('balanceSheet.cash');
          const netDebt = debt.map((d, i) => d - (cash[i] || 0));
          return [
            { name: "Net Debt (순부채)", type: "bar", data: netDebt.map(v => ({ value: v, itemStyle: { color: v > 0 ? '#ef4444' : '#10b981' } })) },
            { name: "Net Debt/EBITDA", type: "line", yAxisIndex: 1, data: getVal('keyRatios.netDebtEbitda'), itemStyle: { color: '#ffffff' }, lineStyle: { width: 2, type: 'dashed' }, symbolSize: 8 }
          ];
        }

        case "ruleOf40": {
          const revs = getVal('incomeStatement.revenue');
          const fcfs = getVal('cashFlow.fcf');
          const r40 = revs.map((rev, i) => {
            const growth = i > 0 && revs[i-1] > 0 ? ((rev - revs[i-1]) / revs[i-1]) * 100 : 0;
            const fcfMargin = rev > 0 ? (fcfs[i] / rev) * 100 : 0;
            return Number((growth + fcfMargin).toFixed(2));
          });
          return [{
            name: "Rule of 40 (%)", type: "bar", yAxisIndex: 1,
            data: r40.map(v => ({ value: v, itemStyle: { color: v >= 40 ? '#10b981' : v >= 20 ? '#fbbf24' : '#ef4444', borderRadius: [4, 4, 0, 0] } })),
            markLine: { silent: true, symbol: "none", data: [{ yAxis: 40 }], lineStyle: { color: "#D85604", type: "dashed", width: 2 }, label: { formatter: "Target 40%", position: "end", color: "#D85604" } }
          }];
        }

        default: return [];
      }
    };

    const needRightAxis = ["roic", "ruleOf40", "opLeverage", "solvency", "earningsQuality", "marginTrend"].includes(chartType);
    const isPercentOnly = ["marginTrend"].includes(chartType);

    return {
      backgroundColor: 'transparent',
      tooltip: {
        trigger: "axis",
        backgroundColor: 'rgba(20, 20, 20, 0.95)',
        borderColor: '#333',
        textStyle: { color: '#fff', fontSize: 12 },
      },
      legend: { textStyle: { color: "#aaa", fontSize: 11 }, top: 0 },
      grid: { left: '3%', right: '4%', bottom: '12%', containLabel: true },
      xAxis: {
        type: "category",
        data: periods,
        axisLabel: {
          color: "#888",
          fontSize: 11,
          rotate: period === 'quarterly' ? 30 : 0,
          fontWeight: 600,
        },
        axisTick: { alignWithLabel: true },
      },
      yAxis: [
        {
          type: "value",
          show: !isPercentOnly,
          splitLine: { lineStyle: { color: '#161616' } },
          axisLabel: {
            color: "#666", fontSize: 10,
            formatter: (value) => {
              if (Math.abs(value) >= 1e12) return (value / 1e12).toFixed(1) + 'T';
              if (Math.abs(value) >= 1e9) return (value / 1e9).toFixed(1) + 'B';
              if (Math.abs(value) >= 1e6) return (value / 1e6).toFixed(1) + 'M';
              return value.toLocaleString();
            }
          }
        },
        {
          type: "value",
          position: 'right',
          show: needRightAxis || isPercentOnly,
          splitLine: { show: false },
          axisLabel: {
            color: "#fbbf24", fontSize: 10,
            formatter: (value) => value.toFixed(0) + '%'
          }
        }
      ],
      series: getSeries(),
    };
  }, [chartType, rows, periods, period]);

  /* ── Styles ── */
  const btnStyle = (active) => ({
    padding: "8px 16px",
    backgroundColor: active ? "#D85604" : "#1a1a1a",
    color: active ? "#fff" : "#888",
    border: "1px solid",
    borderColor: active ? "#D85604" : "#333",
    borderRadius: "6px",
    cursor: "pointer",
    fontSize: "12px",
    fontWeight: "600",
    fontFamily: "inherit",
    marginLeft: "5px",
    transition: "all 0.15s",
  });

  const subTabStyle = (active) => ({
    padding: "12px 20px",
    cursor: "pointer",
    fontWeight: "700",
    fontSize: "14px",
    color: active ? "#D85604" : "#888",
    borderBottom: active ? "2px solid #D85604" : "2px solid transparent",
    transition: "0.2s",
  });

  /* ── Render ── */
  if (loading) return <div style={{ padding: 100, textAlign: "center", color: "#888" }}>LOADING...</div>;
  if (!financialData || financialData.error) return (
    <div style={{ padding: '40px 20px' }}>
      <div style={{ background: "#1a0800", border: "1px solid #AD1B0240", borderLeft: "3px solid #AD1B02", borderRadius: 6, padding: "12px 18px", fontSize: 12, color: "#AD1B02", fontFamily: "monospace" }}>
        ⚠ 재무 데이터를 불러오지 못했습니다.{financialData?.error ? ` (${financialData.error})` : ""}<br />
        <span style={{ color: "#555", fontSize: 11 }}>백엔드 연결 또는 ticker를 확인해주세요.</span>
      </div>
    </div>
  );

  return (
    <div style={{ padding: "20px", color: "#fff", fontFamily: "-apple-system, sans-serif" }}>
      {/* 1. 차트 영역 */}
      <div style={{ backgroundColor: '#0a0a0a', padding: '25px', borderRadius: '16px', border: '1px solid #1a1a1a', marginBottom: '20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
          <h3 style={{ margin: 0, fontSize: '16px', color: '#fff' }}>Financial Charts</h3>
          <select
            value={chartType}
            onChange={e => setChartType(e.target.value)}
            style={{
              background: '#1a1a1a', color: '#e8e8e8', border: '1px solid #333',
              padding: '8px 14px', borderRadius: '8px', fontSize: '13px',
              cursor: 'pointer', fontWeight: 600,
            }}
          >
            <option value="revenueProfits">Revenue & Profit (매출&이익)</option>
            <option value="marginTrend">Margin Trend (마진 추세)</option>
            <option value="earningsQuality">Earnings Quality (이익의 질)</option>
            <option value="fcfYield">FCF Margin / Cash Flow (현금 흐름)</option>
            <option value="roic">Efficiency (ROIC/자본효율성)</option>
            <option value="opLeverage">Operating Leverage (영업 레버리지)</option>
            <option value="solvency">Solvency_Debt (지급능력 부채)</option>
            <option value="ruleOf40">Rule of 40 (40의 법칙)</option>
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
      {CHART_INFO[chartType] && (
        <div style={{ backgroundColor: '#111', padding: '24px', borderRadius: '12px', border: '1px solid #222', borderLeft: '4px solid #D85604', marginBottom: '30px' }}>
          <h4 style={{ color: '#D85604', marginTop: 0, marginBottom: '15px', fontSize: '16px' }}>
            💡 {CHART_INFO[chartType].title} 분석 가이드
          </h4>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '20px', fontSize: '13px', color: '#ccc' }}>
            <div><strong style={{ color: '#666', display: 'block', marginBottom: '5px' }}>의미</strong> {CHART_INFO[chartType].meaning}</div>
            <div><strong style={{ color: '#666', display: 'block', marginBottom: '5px' }}>중요성</strong> {CHART_INFO[chartType].importance}</div>
          </div>
          <div style={{ marginTop: '15px', padding: '12px', backgroundColor: '#1a1a1a', borderRadius: '6px', fontSize: '13px', border: '1px solid #222' }}>
            <span style={{ color: '#fbbf24', fontWeight: 'bold' }}>판단 기준:</span> {CHART_INFO[chartType].criteria}
          </div>
        </div>
      )}

      {/* 3. 탭 컨트롤 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', borderBottom: '1px solid #222', marginBottom: '20px' }}>
        <div style={{ display: 'flex' }}>
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
        <div style={{ marginBottom: '10px' }}>
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


/* ═══════════════════════════════════════════════
   FinTable Sub-component
   ═══════════════════════════════════════════════ */
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
    return <div style={{ padding: 40, textAlign: 'center', color: '#444', fontSize: 13 }}>데이터가 없습니다.</div>;

  return (
    <div style={{ overflowX: "auto", borderRadius: "12px", border: "1px solid #1a1a1a", backgroundColor: '#0a0a0a' }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12px" }}>
        <thead>
          <tr style={{ backgroundColor: "#111", borderBottom: '1px solid #222' }}>
            <th style={{
              textAlign: "left", padding: "15px", position: 'sticky', left: 0,
              backgroundColor: '#111', zIndex: 10, minWidth: '280px', color: '#666',
            }}>
              {isRatio ? "Key Ratios" : "Millions USD"}
            </th>
            {periods.map(p => (
              <th key={p} style={{ padding: "15px", textAlign: "right", color: "#fff", minWidth: 110, whiteSpace: 'nowrap' }}>{p}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => {
            const hi = HIGHLIGHT_LABELS.has(row.label);
            const kor = KOR_MAP[row.label];
            return (
              <tr key={i}
                style={{ borderBottom: "1px solid #111", backgroundColor: hi ? "rgba(216,86,4,0.05)" : "transparent" }}
                onMouseEnter={e => e.currentTarget.style.backgroundColor = '#161616'}
                onMouseLeave={e => e.currentTarget.style.backgroundColor = hi ? "rgba(216,86,4,0.05)" : "transparent"}
              >
                <td style={{
                  padding: "10px 15px", color: hi ? "#D85604" : "#aaa",
                  fontWeight: hi ? "700" : "400",
                  position: 'sticky', left: 0, backgroundColor: '#0a0a0a',
                  borderRight: '1px solid #1a1a1a', whiteSpace: 'nowrap',
                }}>
                  {row.label}
                  {kor && <span style={{ color: '#555', fontSize: '10px', marginLeft: '6px' }}>({kor})</span>}
                </td>
                {periods.map(p => {
                  const val = row[p];
                  return (
                    <td key={p} style={{ padding: "10px 15px", textAlign: "right", color: hi ? "#fff" : "#eee", fontFamily: 'monospace' }}>
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

