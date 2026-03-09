import React, { useState, useEffect, useMemo } from "react";
import { useOutletContext } from "react-router-dom";
import ReactECharts from "echarts-for-react";

const CHART_INFO = {
  revenueProfits: {
    title: "Revenue & Profit (매출과 이익)",
    meaning: "회사가 얼마나 많이 팔았는지(매출)와 본업에서 실제로 얼마를 벌었는지(영업이익 또는 순이익)를 함께 보여줍니다.",
    importance: "매출 성장만으로는 기업의 질을 판단하기 어렵습니다. 매출과 함께 이익이 동반 성장하는지 확인해야 '성장의 질'을 평가할 수 있습니다.",
    criteria: "매출과 영업이익이 함께 우상향하는 구조가 이상적입니다. 매출은 증가하지만 이익이 정체되거나 감소한다면 비용 구조 악화나 경쟁 심화를 의심해야 합니다."
  },

  fcfYield: {
    title: "FCF Margin / Cash Flow (수익의 질 - 현금흐름)",
    meaning: "회계상 이익이 아니라 실제 회사 통장에 남는 '진짜 현금(Free Cash Flow, FCF)'을 확인합니다.",
    importance: "회계 이익은 조정될 수 있지만 현금 흐름은 조작이 어렵습니다. 장기적으로 FCF가 순이익과 비슷하거나 더 높다면 매우 건강한 기업으로 흑자 도산을 막고 배당이나 투자를 할 수 있는 실질적인 체력을 갖고있다는 뜻입니다.",
    criteria: "장기적으로 FCF(녹색)가 순이익(노랑)과 비슷하거나 더 높게 유지되는 것이 이상적입니다. 이익은 나는데 현금이 마이너스라면 '가짜 수익'일 가능성이 큽니다."
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
    criteria: "영업이익 성장률이 매출 성장률보다 빠르게 증가한다면 긍정적인 영업 레버리지가 발생하고 있는 것입니다. 이때 주가가 가장 탄력적으로 상승하는 경우가 많습니다."
  },

  solvency: {
    title: "Debt Solvency (부채 안정성)",
    meaning: "기업이 벌어들이는 현금으로 부채를 충분히 감당할 수 있는지 평가합니다.",
    importance: "금리 상승기나 경기 침체에서 기업이 생존할 수 있는 재무 안정성을 판단하는 핵심 요소입니다.",
    criteria: "순부채 막대가 아래쪽(녹색)으로 뻗어 있다면 빚보다 현금이 많은 '초우량' 상태입니다. 반대로 위쪽(빨강)이 너무 길면 이자 갚느라 성장이 더딜 수 있습니다. 추가적으로 Net Debt / EBITDA가 2 이하이면 재무 안정성이 높은 기업으로 평가됩니다."
  },

  ruleOf40: {
    title: "Rule of 40 (성장과 수익의 균형)",
    meaning: "매출 성장률과 FCF 마진을 합산해 기업의 성장성과 수익성을 동시에 평가하는 SaaS 산업의 핵심 지표입니다.",
    importance: "성장만 하고 돈은 못 버는지, 돈만 벌고 성장은 멈췄는지 체크하여 '균형 잡힌 우량 기업'을 골라냅니다.",
    criteria: "매출 성장률 + FCF 마진(초록바)이 주황색 가이드라인(Target 40%)을 뚫고 올라와 있다면 우수한 SaaS 기업으로 평가됩니다."
  }
};

const SORT_ORDER = {
    incomeStatement: [
    // 1. 매출 및 매출 원가
    { key: "Total Revenue", kor: "총 매출" },
    { key: "Operating Revenue", kor: "영업 수익" },
    { key: "Cost Of Revenue", kor: "매출 원가" },
    { key: "Reconciled Cost Of Revenue", kor: "조정 매출원가" },
    { key: "Gross Profit", kor: "매출 총이익" },

    // 2. 영업 비용 (상세 상각비 포함)
    { key: "Operating Expense", kor: "영업 비용" },
    { key: "Research And Development", kor: "연구 개발비" },
    { key: "Selling General And Administration", kor: "판매관리비" },
    { key: "Depreciation Amortization Depletion Income Statement", kor: "감가상각 및 소모비(IS)" },
    { key: "Depreciation And Amortization In Income Statement", kor: "감가상각비(IS)" },
    { key: "Amortization", kor: "무형자산 상각비(일반)" },
    { key: "Amortization Of Intangibles Income Statement", kor: "무형자산 상각비(IS)" },
    { key: "Reconciled Depreciation", kor: "조정 감가상각비" },
    { key: "Total Expenses", kor: "총 비용" },
    { key: "Operating Income", kor: "영업 이익" },
    { key: "Total Operating Income As Reported", kor: "보고된 영업이익" },

    // 3. 영업외 손익 및 이자 (수익/비용 상세)
    { key: "Net Interest Income", kor: "순이자 손익" },
    { key: "Net Non Operating Interest Income Expense", kor: "순영업외 이자손익" },
    { key: "Interest Expense", kor: "이자 비용" },
    { key: "Interest Expense Non Operating", kor: "영업외 이자비용" },
    { key: "Interest Income", kor: "이자 수익" },
    { key: "Interest Income Non Operating", kor: "영업외 이자수익" },
    { key: "Other Income Expense", kor: "기타 영업외 손익" },
    { key: "Other Non Operating Income Expenses", kor: "기타 비영업 수익/비용" },
    { key: "Gain On Sale Of Security", kor: "유가증권 처분이익" },
    { key: "Special Income Charges", kor: "특별 비용" },
    { key: "Restructuring And Mergern Acquisition", kor: "구조조정 및 M&A 비용" },
    { key: "Total Unusual Items", kor: "총 일회성 항목" },
    { key: "Total Unusual Items Excluding Goodwill", kor: "영업권 제외 일회성 항목" },

    // 4. 세전/세후 이익 및 조정 지표
    { key: "EBITDA", kor: "EBITDA" },
    { key: "Normalized EBITDA", kor: "조정 EBITDA" },
    { key: "EBIT", kor: "EBIT" },
    { key: "Pretax Income", kor: "세전 이익" },
    { key: "Tax Provision", kor: "법인세 비용" },
    { key: "Tax Effect Of Unusual Items", kor: "일회성 항목 세금 효과" },
    { key: "Tax Rate For Calcs", kor: "계산용 실효세율" },
    { key: "Net Income", kor: "당기 순이익" },
    { key: "Net Income Including Noncontrolling Interests", kor: "비지배지분 포함 순이익" },
    { key: "Net Income Continuous Operations", kor: "계속영업 순이익" },
    { key: "Net Income From Continuing Operation Net Minority Interest", kor: "지분 해당 계속영업이익" },
    { key: "Net Income From Continuing And Discontinued Operation", kor: "계속 및 중단영업 순이익" },
    { key: "Net Income Discontinuous Operations", kor: "중단영업 순이익" },
    { key: "Normalized Income", kor: "조정 순이익" },
    { key: "Net Income Common Stockholders", kor: "보통주 귀속 순이익" },
    { key: "Diluted NI Availto Com Stockholders", kor: "희석 보통주 귀속 순이익" },
    { key: "Preferred Stock Dividends", kor: "우선주 배당금" },

    // 5. 주당 지표 및 주식 수
    { key: "Basic EPS", kor: "기본 EPS" },
    { key: "Diluted EPS", kor: "희석 EPS" },
    { key: "Basic Average Shares", kor: "기본 평균 주식수" },
    { key: "Diluted Average Shares", kor: "희석 평균 주식수" }
    ],

    balanceSheet: [
    // 1. 자산 (Assets)
    { key: "Total Assets", kor: "총 자산" },

    // 1-1. 유동 자산
    { key: "Current Assets", kor: "유동 자산" },
    { key: "Cash Cash Equivalents And Short Term Investments", kor: "현금 및 단기투자자산" },
    { key: "Cash And Cash Equivalents", kor: "현금 및 현금성자산" },
    { key: "Receivables", kor: "매출채권 및 미수금" },
    { key: "Gross Accounts Receivable", kor: "총 매출채권(액면)" },
    { key: "Accounts Receivable", kor: "매출채권(순액)" },
    { key: "Allowance For Doubtful Accounts Receivable", kor: "대손충당금" },
    { key: "Other Receivables", kor: "기타 미수금" },
    { key: "Inventory", kor: "재고 자산" },
    { key: "Finished Goods", kor: "제품(완제품)" },
    { key: "Work In Process", kor: "재공품(생산중)" },
    { key: "Raw Materials", kor: "원재료" },
    { key: "Prepaid Assets", kor: "선급 비용" },
    { key: "Other Current Assets", kor: "기타 유동자산" },

    // 1-2. 비유동 자산 (유형자산 상세 포함)
    { key: "Total Non Current Assets", kor: "비유동 자산" },
    { key: "Net PPE", kor: "순 유형자산" },
    { key: "Gross PPE", kor: "총 유형자산" },
    { key: "Accumulated Depreciation", kor: "감가상각 누계액" },
    { key: "Properties", kor: "부동산" },
    { key: "Land And Improvements", kor: "토지 및 개량" },
    { key: "Buildings And Improvements", kor: "건물 및 개량" },
    { key: "Machinery Furniture Equipment", kor: "기계 및 비품" },
    { key: "Construction In Progress", kor: "건설중인 자산" },
    { key: "Goodwill And Other Intangible Assets", kor: "영업권 및 무형자산" },
    { key: "Goodwill", kor: "영업권" },
    { key: "Other Intangible Assets", kor: "기타 무형자산" },
    { key: "Other Non Current Assets", kor: "기타 비유동자산" },

    // 2. 부채 (Liabilities)
    { key: "Total Liabilities Net Minority Interest", kor: "총 부채" },

    // 2-1. 유동 부채
    { key: "Current Liabilities", kor: "유동 부채" },
    { key: "Current Debt And Capital Lease Obligation", kor: "단기 차입금 및 리스 부채" },
    { key: "Current Debt", kor: "단기 차입금" },
    { key: "Other Current Borrowings", kor: "기타 단기 차입" },
    { key: "Current Capital Lease Obligation", kor: "유동 자본리스 부채" },
    { key: "Payables And Accrued Expenses", kor: "매입채무 및 미지급비용" },
    { key: "Accounts Payable", kor: "매입채무" },
    { key: "Payables", kor: "미지급금" },
    { key: "Current Accrued Expenses", kor: "유동 미지급 비용" },
    { key: "Interest Payable", kor: "미지급 이자" },
    { key: "Total Tax Payable", kor: "미지급 법인세" },
    { key: "Pensionand Other Post Retirement Benefit Plans Current", kor: "당기 퇴직연금 및 급여부채" },
    { key: "Current Deferred Liabilities", kor: "유동 이연 부채" },
    { key: "Current Deferred Revenue", kor: "유동 이연 수익" },
    { key: "Other Current Liabilities", kor: "기타 유동부채" },

    // 2-2. 비유동 부채
    { key: "Total Non Current Liabilities Net Minority Interest", kor: "비유동 부채" },
    { key: "Long Term Debt And Capital Lease Obligation", kor: "장기 차입금 및 리스 부채" },
    { key: "Long Term Debt", kor: "장기 차입금" },
    { key: "Long Term Capital Lease Obligation", kor: "장기 자본리스 부채" },
    { key: "Capital Lease Obligations", kor: "자본리스 합계" },
    { key: "Non Current Deferred Liabilities", kor: "비유동 이연 부채" },
    { key: "Non Current Deferred Revenue", kor: "비유동 이연 수익" },
    { key: "Non Current Deferred Taxes Liabilities", kor: "비유동 이연 법인세 부채" },
    { key: "Tradeand Other Payables Non Current", kor: "비유동 매입채무" },
    { key: "Other Non Current Liabilities", kor: "기타 비유동부채" },

    // 3. 자본 (Equity)
    { key: "Total Equity Gross Minority Interest", kor: "총 자본" },
    { key: "Stockholders Equity", kor: "주주 지분" },
    { key: "Common Stock Equity", kor: "보통주 자본" },
    { key: "Capital Stock", kor: "자본금(Capital Stock)" },
    { key: "Common Stock", kor: "보통주(Common Stock)" },
    { key: "Preferred Stock", kor: "우선주" },
    { key: "Preferred Stock Equity", kor: "우선주 자본" },
    { key: "Additional Paid In Capital", kor: "자본 잉여금" },
    { key: "Retained Earnings", kor: "이익 잉여금" },
    { key: "Other Equity Adjustments", kor: "기타 자본 조정" },
    { key: "Gains Losses Not Affecting Retained Earnings", kor: "기타 포괄손익 누계액" },

    // 4. 주요 분석 지표 및 주식 수
    { key: "Total Debt", kor: "총 부채(차입금)" },
    { key: "Net Debt", kor: "순 부채" },
    { key: "Working Capital", kor: "운전 자본" },
    { key: "Invested Capital", kor: "투하 자본" },
    { key: "Total Capitalization", kor: "총 자본화 금액" },
    { key: "Net Tangible Assets", kor: "순 유형 자산" },
    { key: "Tangible Book Value", kor: "유형 자산 장부가치" },
    { key: "Ordinary Shares Number", kor: "보통주 주식수" },
    { key: "Preferred Shares Number", kor: "우선주 주식수" },
    { key: "Treasury Shares Number", kor: "자기주식(자사주) 수" },
    { key: "Share Issued", kor: "발행 주식수" }
    ],

    cashFlow: [
    // 1. 영업활동 현금흐름 (비즈니스 성적표)
    { key: "Operating Cash Flow", kor: "영업활동 현금흐름" },
    { key: "Cash Flow From Continuing Operating Activities", kor: "계속영업 영업현금흐름" },
    { key: "Net Income From Continuing Operations", kor: "계속영업 순이익" },
    
    // 현금 유출입이 없는 비용 가산 (Non-cash items)
    { key: "Depreciation Amortization Depletion", kor: "감가상각 및 소모비(CF)" },
    { key: "Depreciation And Amortization", kor: "감가상각비(CF)" },
    { key: "Depreciation", kor: "유형자산 감가상각비" },
    { key: "Amortization Cash Flow", kor: "무형자산 상각비(CF)" },
    { key: "Amortization Of Intangibles", kor: "무형자산 상각비" },
    { key: "Stock Based Compensation", kor: "주식 기반 보상(SBC)" },
    { key: "Deferred Tax", kor: "이연 법인세 변동" },
    { key: "Deferred Income Tax", kor: "이연 법인세 변동(상세)" },
    { key: "Operating Gains Losses", kor: "영업 자산/부채 관련 손익" },
    { key: "Other Non Cash Items", kor: "기타 비현금성 항목" },
    
    // 운전 자본 변동 (Working Capital)
    { key: "Change In Working Capital", kor: "운전 자본의 변동" },
    { key: "Changes In Account Receivables", kor: "매출채권의 변동(상세)" },
    { key: "Change In Receivables", kor: "매출채권의 변동" },
    { key: "Change In Inventory", kor: "재고 자산의 변동" },
    { key: "Change In Account Payable", kor: "매입채무의 변동(상세)" },
    { key: "Change In Payable", kor: "매입채무의 변동" },
    { key: "Change In Payables And Accrued Expense", kor: "매입채무 및 비용의 변동" },
    { key: "Change In Other Working Capital", kor: "기타 운전 자본의 변동" },

    // 2. 투자활동 현금흐름 (미래 투자 및 자산 매각)
    { key: "Investing Cash Flow", kor: "투자활동 현금흐름" },
    { key: "Cash Flow From Continuing Investing Activities", kor: "계속영업 투자현금흐름" },
    { key: "Net PPE Purchase And Sale", kor: "유형자산 취득 및 처분액" },
    { key: "Capital Expenditure", kor: "자본적 지출(CAPEX)" },
    { key: "Purchase Of PPE", kor: "유형자산 취득" },
    { key: "Sale Of PPE", kor: "유형자산 처분" },
    { key: "Net Business Purchase And Sale", kor: "사업 인수 및 매각" },
    { key: "Purchase Of Business", kor: "사업 인수(M&A)" },
    { key: "Sale Of Business", kor: "사업 매각" },
    { key: "Net Investment Purchase And Sale", kor: "투자자산 매수 및 매각" },
    { key: "Purchase Of Investment", kor: "투자자산 취득" },
    { key: "Sale Of Investment", kor: "투자자산 처분" },
    { key: "Net Other Investing Changes", kor: "기타 투자활동 변동" },

    // 3. 재무활동 현금흐름 (자금 조달 및 주주 환원)
    { key: "Financing Cash Flow", kor: "재무활동 현금흐름" },
    { key: "Cash Flow From Continuing Financing Activities", kor: "계속영업 재무현금흐름" },
    { key: "Net Issuance Payments Of Debt", kor: "부채 발행 및 상환액" },
    { key: "Net Long Term Debt Issuance", kor: "순 장기부채 발행액" },
    { key: "Long Term Debt Issuance", kor: "장기부채 발행" },
    { key: "Long Term Debt Payments", kor: "장기부채 상환" },
    { key: "Issuance Of Debt", kor: "부채 발행(총)" },
    { key: "Repayment Of Debt", kor: "부채 상환(총)" },
    { key: "Net Common Stock Issuance", kor: "보통주 발행 및 취득액" },
    { key: "Common Stock Issuance", kor: "보통주 발행" },
    { key: "Issuance Of Capital Stock", kor: "자본금 발행" },
    { key: "Common Stock Payments", kor: "보통주 취득(자사주 매입)" },
    { key: "Repurchase Of Capital Stock", kor: "자기주식 매입" },
    { key: "Net Preferred Stock Issuance", kor: "우선주 순발행액" },
    { key: "Preferred Stock Issuance", kor: "우선주 발행" },
    { key: "Cash Dividends Paid", kor: "배당금 지급" },
    { key: "Net Other Financing Charges", kor: "기타 재무활동 비용" },

    // 4. 현금 잔액 및 잉여현금흐름
    { key: "Free Cash Flow", kor: "잉여현금흐름(FCF)" },
    { key: "Changes In Cash", kor: "현금의 순증감" },
    { key: "Beginning Cash Position", kor: "기초 현금 잔액" },
    { key: "End Cash Position", kor: "기말 현금 잔액" },

    // 5. 추가 정보
    { key: "Interest Paid Supplemental Data", kor: "이자 지급액(실제)" },
    { key: "Income Tax Paid Supplemental Data", kor: "법인세 납부액(실제)" }
    ]
};

const FinancialsTab = () => {
  const { ticker } = useOutletContext();
  const [activeSubTab, setActiveSubTab] = useState("incomeStatement");
  const [period, setPeriod] = useState("annual");
  const [chartType, setChartType] = useState("revenueProfits");
  const [financialData, setFinancialData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchFinancials = async () => {
      setLoading(true);
      try {
        const res = await fetch(`/api/stock/detail/${ticker}/financials?period=${period}`);
        if (!res.ok) throw new Error("Fetch failed");
        const data = await res.json();
        setFinancialData(data);
      } catch (e) {
        console.error("Financial Data Fetch Error:", e);
      } finally {
        setLoading(false);
      }
    };
    if (ticker) fetchFinancials();
  }, [ticker, period]);

  // 데이터 안전 추출을 위한 useMemo
  const { periods, metrics, raw, tableData } = useMemo(() => {
    return {
      periods: financialData?.years || [],
      metrics: financialData?.metrics || {},
      raw: financialData?.raw || {},
      tableData: financialData?.[activeSubTab]?.data || []
    };
  }, [financialData, activeSubTab]);

  const chartOption = useMemo(() => {
  if (!financialData || !raw || !metrics) return {};

  return {
    backgroundColor: 'transparent',
    tooltip: { 
      trigger: "axis", 
      backgroundColor: 'rgba(20, 20, 20, 0.9)', 
      borderColor: '#333', 
      textStyle: { color: '#fff', fontSize: 12 } 
    },
    legend: { 
      textStyle: { color: "#aaa", fontSize: 11 }, 
      top: 0 
    },
    grid: { left: '3%', right: '4%', bottom: '10%', containLabel: true },
    xAxis: { 
      type: "category", 
      data: periods, 
      axisLabel: { color: "#666", fontSize: 11 } 
    },
    yAxis: [
      {
        type: "value",
        name: "Amount",
        splitLine: { lineStyle: { color: '#161616' } },
        axisLabel: { 
          color: "#666", fontSize: 10,
          formatter: (value) => {
            if (Math.abs(value) >= 1e12) return (value / 1e12).toFixed(1) + 'T';
            if (Math.abs(value) >= 1e9) return (value / 1e9).toFixed(1) + 'B';
            return value.toLocaleString();
          }
        }
      },
      {
        type: "value",
        name: "Ratio (%)",
        position: 'right',
        // solvency 포함, 퍼센트 지표를 쓰는 차트에서만 우측 축 표시
        show: ["roic", "ruleOf40", "opLeverage", "solvency"].includes(chartType),
        splitLine: { show: false },
        axisLabel: { 
          color: "#fbbf24", fontSize: 10,
          formatter: (value) => value.toFixed(0) + '%'
        }
      }
    ],
    series: (function() {
      // 모든 케이스에서 markLine: null을 기본으로 설정하여 Rule of 40의 잔상을 제거합니다.
      switch (chartType) {
        case "revenueProfits": 
          return [
            { name: "Revenue (매출)", type: "bar", data: raw.revenue, itemStyle: { color: '#3b82f6' } },
            { name: "Op. Income (영업이익)", type: "bar", data: raw.opIncome || raw.op_income, itemStyle: { color: '#10b981' } },
            { name: "Net Income (순이익)", type: "line", data: raw.netIncome, itemStyle: { color: '#fbbf24' }, symbolSize: 8, markLine: null }
          ];

        case "fcfYield": 
          return [
            { name: "Net Income (순이익)", type: "bar", data: raw.netIncome, itemStyle: { color: '#fbbf24', opacity: 0.3 } },
            { name: "Free Cash Flow (FCF)", type: "line", data: raw.fcf, itemStyle: { color: '#10b981' }, symbolSize: 10, markLine: null }
          ];

        case "roic": 
          return [
            { name: "Net Income (순이익)", type: "bar", data: raw.netIncome, itemStyle: { color: '#fbbf24', opacity: 0.2 } },
            { name: "ROIC (%)", type: "line", yAxisIndex: 1, smooth: true, data: metrics.roic, itemStyle: { color: '#8b5cf6' }, lineStyle: { width: 3 }, markLine: null }
          ];

        case "opLeverage": 
        // 매출 대비 영업이익률 계산 (임시)
        const opMargin = raw.revenue?.map((rev, i) => 
          rev > 0 ? (raw.opIncome[i] / rev) * 100 : 0
        ) || [];

        return [
          { name: "Net Income (순이익)", type: "bar", data: raw.netIncome, itemStyle: { color: '#fbbf24', opacity: 0.2 } },
          { 
            name: "Op Margin (영업이익률 %)", // 명칭 변경
            type: "line", 
            yAxisIndex: 1, // metrics 데이터가 있다면 그것도 소수점 처리
            data: (metrics.opLeverage || opMargin).map(v => Number(Number(v).toFixed(2))),
            itemStyle: { color: '#10b981' }, 
            lineStyle: { width: 3 }, 
            markLine: null 
          }
        ];

        case "solvency": 
        // 순부채 / 영업이익 비율 계산 및 소수점 1자리 제한
        const debtRatio = raw.netDebt?.map((debt, i) => 
          (raw.opIncome[i] && raw.opIncome[i] !== 0) 
            ? Number((debt / raw.opIncome[i]).toFixed(1)) 
            : 0
        ) || [];

        return [
          { 
            name: "Net Debt (순부채)", 
            type: "bar", 
            data: raw.netDebt || [], 
            itemStyle: { 
              color: (p) => p.value > 0 ? '#ef4444' : '#10b981' 
            } 
          },
          { 
            name: "Debt/Earnings Ratio (채무 상환 능력 지표)", 
            type: "line", 
            yAxisIndex: 1, 
            // 데이터 존재 여부에 따라 소수점 1자리 적용
            data: (metrics.netDebtEbitda || metrics.net_debt_ebitda || debtRatio).map(v => Number(Number(v).toFixed(3))), 
            itemStyle: { color: '#ffffff' }, 
            lineStyle: { width: 2, type: 'dashed' },
            symbolSize: 8,
            connectNulls: true,
            markLine: null 
          }
        ];

        case "ruleOf40": 
          return [
            {
              name: "Rule of 40 (%)",
              type: "bar",
              yAxisIndex: 1,
              data: metrics.ruleOf40,
              itemStyle: { color: "#10b981", borderRadius: [4, 4, 0, 0] },
              markLine: {
                silent: true,
                symbol: "none",
                data: [{ yAxis: 40 }],
                lineStyle: { color: "#D85604", type: "dashed", width: 2 },
                label: { formatter: "Target 40%", position: "end" }
              }
            }
          ];
        default: return [];
      }
    })()
  };
}, [chartType, periods, metrics, raw, financialData]);

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
    marginLeft: "5px"
  });

  const subTabStyle = (active) => ({
    padding: "12px 20px",
    cursor: "pointer",
    fontWeight: "700",
    fontSize: "14px",
    color: active ? "#D85604" : "#888",
    borderBottom: active ? "2px solid #D85604" : "2px solid transparent",
    transition: "0.2s"
  });

  if (loading) return <div style={{ padding: 100, textAlign: "center", color: "#888" }}>LOADING...</div>;
  if (!financialData) return <div style={{ padding: 100, textAlign: "center", color: "#888" }}>데이터를 불러올 수 없습니다.</div>;

  return (
    <div style={{ padding: "20px", color: "#fff", fontFamily: "-apple-system, sans-serif" }}>
      {/* 1. 차트 영역 */}
      <div style={{ backgroundColor: '#0a0a0a', padding: '25px', borderRadius: '16px', border: '1px solid #1a1a1a', marginBottom: '20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '25px' }}>
          <h3 style={{ margin: 0, fontSize: '18px', fontWeight: '700' }}>Financial Analysis Charts</h3>
          <select 
            value={chartType} 
            onChange={e => setChartType(e.target.value)} 
            style={{ backgroundColor: '#111', color: '#fff', border: '1px solid #333', padding: '8px 12px', borderRadius: '8px', fontSize: '13px', cursor: 'pointer' }}
          >
            <option value="revenueProfits">Revenue & Profit</option>
            <option value="fcfYield">EFCF Margin / Cash Flow (FCF)</option>
            <option value="roic">Efficiency (ROIC)</option>
            <option value="opLeverage">Operating Leverage</option>
            <option value="solvency">Solvency (Debt)</option>
            <option value="ruleOf40">Rule of 40</option>
          </select>
        </div>
        <ReactECharts 
          option={chartOption} 
          style={{ height: "400px" }} 
          notMerge={true}  // ✅ 이전 차트 설정을 완전히 지우고 새로 그림
          lazyUpdate={true} 
        />
      </div>

      {/* 2. 가이드 박스 */}
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

      {/* 3. 탭 컨트롤 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', borderBottom: '1px solid #222', marginBottom: '20px' }}>
        <div style={{ display: 'flex' }}>
          {["incomeStatement", "balanceSheet", "cashFlow"].map(tab => (
            <div key={tab} onClick={() => setActiveSubTab(tab)} style={subTabStyle(activeSubTab === tab)}>
              {tab === "incomeStatement" ? "Income(P&L)" : tab === "balanceSheet" ? "Balance(B/S)" : "Cash Flow(CFS)"}
            </div>
          ))}
        </div>
        <div style={{ marginBottom: '10px' }}>
          <button onClick={() => setPeriod("annual")} style={btnStyle(period === "annual")}>Annual(연간)</button>
          <button onClick={() => setPeriod("quarterly")} style={btnStyle(period === "quarterly")}>Quarterly(분기)</button>
        </div>
      </div>

      {/* 4. 테이블 섹션 */}
      <div style={{ overflowX: "auto", borderRadius: "12px", border: "1px solid #1a1a1a", backgroundColor: '#0a0a0a' }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12px" }}>
          <thead>
            <tr style={{ backgroundColor: "#111", color: "#666", borderBottom: '1px solid #222' }}>
              <th style={{ textAlign: "left", padding: "15px", position: 'sticky', left: 0, backgroundColor: '#111', zIndex: 10, minWidth: '280px' }}>
                Millions USD (English / 한글)
              </th>
              {periods.map(p => <th key={p} style={{ padding: "15px", textAlign: "right" }}>{p}</th>)}
            </tr>
          </thead>
          <tbody>
            {(() => {
              if (!tableData || tableData.length === 0) {
                return <tr><td colSpan={periods.length + 1} style={{ padding: 40, textAlign: 'center', color: '#444' }}>데이터가 없습니다.</td></tr>;
              }

              const currentOrder = SORT_ORDER[activeSubTab] || [];
              
              // 1. 정의된 순서에 있는 항목들 추출
              const sortedRows = currentOrder
                .map(target => {
                  const found = tableData.find(d => d.label === target.key);
                  return found ? { ...found, kor: target.kor } : null;
                })
                .filter(Boolean);

              // 2. 나머지 모든 계정과목들 (정의되지 않은 것들) 추출
              const otherRows = tableData.filter(d => !currentOrder.some(target => target.key === d.label));

              // 3. 전체 합쳐서 렌더링 (모든 계정 포함)
              return [...sortedRows, ...otherRows].map((row, i) => {
                const isHighlight = ["Total Revenue", "Operating Income", "Net Income", "Total Assets", "Free Cash Flow"].includes(row.label);
                
                return (
                  <tr 
                    key={i} 
                    style={{ 
                      borderBottom: "1px solid #111",
                      backgroundColor: isHighlight ? "rgba(216, 86, 4, 0.05)" : "transparent"
                    }} 
                    onMouseEnter={e => e.currentTarget.style.backgroundColor = '#161616'} 
                    onMouseLeave={e => e.currentTarget.style.backgroundColor = isHighlight ? "rgba(216, 86, 4, 0.05)" : "transparent"}
                  >
                    <td style={{ 
                      padding: "10px 15px", 
                      color: isHighlight ? "#D85604" : "#aaa", 
                      fontWeight: isHighlight ? "700" : "400",
                      position: 'sticky', 
                      left: 0, 
                      backgroundColor: '#0a0a0a', 
                      borderRight: '1px solid #1a1a1a',
                      whiteSpace: 'nowrap'
                    }}>
                      {row.label} {row.kor ? <span style={{ fontSize: '11px', color: '#666', fontWeight: '400' }}>({row.kor})</span> : ""}
                    </td>
                    {periods.map(p => {
                      const val = row[p];
                      const isRatioOrEps = row.label.toLowerCase().includes("eps") || row.label.toLowerCase().includes("rate") || row.label.toLowerCase().includes("share");
                      
                      return (
                        <td key={p} style={{ 
                          padding: "10px 15px", 
                          textAlign: "right", 
                          color: isHighlight ? "#fff" : "#eee", 
                          fontFamily: 'monospace' 
                        }}>
                          {val !== undefined 
                            ? (isRatioOrEps 
                                ? Number(val).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) 
                                : Math.round(Number(val) / 1e6).toLocaleString())
                            : "-"}
                        </td>
                      );
                    })}
                  </tr>
                );
              });
            })()}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default FinancialsTab;
// import React, { useState, useEffect } from 'react';
// import { useOutletContext } from 'react-router-dom';
// import ReactECharts from "echarts-for-react";

// const FinancialsTab = () => {
//   const { ticker } = useOutletContext();
//   const [activeSubTab, setActiveSubTab] = useState('incomeStatement'); // incomeStatement, balanceSheet, cashFlow
//   const [period, setPeriod] = useState('annual'); // annual 또는 quarterly
//   const [financialData, setFinancialData] = useState(null);
//   const [loading, setLoading] = useState(true);

//   // 백엔드 데이터 Fetch (period 파라미터 포함)
//   useEffect(() => {
//     const fetchFinancials = async () => {
//       setLoading(true);
//       try {
//         // 프록시 설정이 되어 있으므로 상대 경로 사용
//         const response = await fetch(`/api/stock/detail/${ticker}/financials?period=${period}`);
//         if (!response.ok) throw new Error("데이터를 불러오는데 실패했습니다.");
//         const data = await response.json();
//         setFinancialData(data);
//       } catch (error) {
//         console.error("Financials Fetch Error:", error);
//       } finally {
//         setLoading(false);
//       }
//     };

//     if (ticker) fetchFinancials();
//   }, [ticker, period]);

//   if (loading) return <div style={{ color: '#888', padding: '40px', textAlign: 'center' }}>데이터를 불러오는 중...</div>;
//   if (!financialData || financialData.error) {
//     return <div style={{ color: '#888', padding: '40px', textAlign: 'center' }}>재무제표 데이터를 찾을 수 없습니다.</div>;
//   }

//   // 현재 선택된 서브탭 데이터 추출
//   const currentTabContent = financialData[activeSubTab];
//   const periods = currentTabContent?.years || []; // 연도 또는 연-월 리스트
//   const tableData = currentTabContent?.data || [];

//   // 숫자를 Million(백만) 단위로 포맷팅
//   const formatValue = (val) => {
//     if (val === 0 || val === null || val === undefined) return '-';
//     // 야후 파이낸스처럼 가독성을 위해 백만 단위로 절삭
//     return (val / 1e6).toLocaleString(undefined, { 
//       maximumFractionDigits: 0 
//     });
//   };

//   // 스타일 정의
//   const subTabStyle = (id) => ({
//     padding: '12px 20px',
//     cursor: 'pointer',
//     fontSize: '14px',
//     fontWeight: '700',
//     color: activeSubTab === id ? '#D85604' : '#888',
//     borderBottom: activeSubTab === id ? '2px solid #D85604' : '2px solid transparent',
//     transition: '0.2s',
//     whiteSpace: 'nowrap'
//   });

//   const periodBtnStyle = (p) => ({
//     padding: '6px 16px',
//     fontSize: '12px',
//     fontWeight: 'bold',
//     cursor: 'pointer',
//     border: 'none',
//     borderRadius: '6px',
//     backgroundColor: period === p ? '#D85604' : 'transparent',
//     color: period === p ? '#fff' : '#888',
//     transition: '0.3s'
//   });

//   return (
//     <div style={{ padding: '20px', color: '#fff' }}>
//       {/* 상단 타이틀 및 기간 토글 */}
//       <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
//         <h2 style={{ fontSize: '22px', fontWeight: '800', margin: 0 }}>Financials</h2>
        
//         {/* Annual / Quarterly 토글 버튼 */}
//         <div style={{ 
//           display: 'flex', 
//           backgroundColor: '#1a1a1a', 
//           padding: '4px', 
//           borderRadius: '8px',
//           border: '1px solid #333'
//         }}>
//           <button style={periodBtnStyle('annual')} onClick={() => setPeriod('annual')}>Annual</button>
//           <button style={periodBtnStyle('quarterly')} onClick={() => setPeriod('quarterly')}>Quarterly</button>
//         </div>
//       </div>

//       {/* 재무제표 종류 선택 서브 탭 */}
//       <div style={{ display: 'flex', gap: '5px', borderBottom: '1px solid #222', marginBottom: '15px', overflowX: 'auto' }}>
//         <div style={subTabStyle('incomeStatement')} onClick={() => setActiveSubTab('incomeStatement')}>Income Statement</div>
//         <div style={subTabStyle('balanceSheet')} onClick={() => setActiveSubTab('balanceSheet')}>Balance Sheet</div>
//         <div style={subTabStyle('cashFlow')} onClick={() => setActiveSubTab('cashFlow')}>Cash Flow</div>
//       </div>

//       <div style={{ fontSize: '11px', color: '#666', marginBottom: '10px', textAlign: 'right' }}>
//         All numbers in Millions (USD)
//       </div>

//       {/* 데이터 테이블 */}
//       <div style={{ 
//         overflowX: 'auto', 
//         backgroundColor: '#0f0f0f', 
//         borderRadius: '12px', 
//         border: '1px solid #1a1a1a',
//         boxShadow: '0 4px 20px rgba(0,0,0,0.5)'
//       }}>
//         <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'right', fontSize: '13px' }}>
//           <thead>
//             <tr style={{ borderBottom: '1px solid #222', backgroundColor: '#141414' }}>
//               <th style={{ textAlign: 'left', padding: '15px', color: '#aaa', fontWeight: '600', minWidth: '200px' }}>Breakdown</th>
//               {periods.map(p => (
//                 <th key={p} style={{ padding: '15px', color: '#fff', minWidth: '100px' }}>{p}</th>
//               ))}
//             </tr>
//           </thead>
//           <tbody>
//             {tableData.length > 0 ? (
//               tableData.map((row, idx) => (
//                 <tr 
//                   key={idx} 
//                   style={{ 
//                     borderBottom: '1px solid #111',
//                     backgroundColor: idx % 2 === 0 ? 'transparent' : '#141414'
//                   }}
//                   onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#1a1a1a'}
//                   onMouseLeave={(e) => e.currentTarget.style.backgroundColor = idx % 2 === 0 ? 'transparent' : '#141414'}
//                 >
//                   <td style={{ 
//                     textAlign: 'left', 
//                     padding: '12px 15px', 
//                     color: '#eee', 
//                     fontWeight: '500',
//                     position: 'sticky',
//                     left: 0,
//                     backgroundColor: 'inherit' 
//                   }}>
//                     {row.label}
//                   </td>
//                   {periods.map(p => (
//                     <td key={p} style={{ padding: '12px 15px', color: '#fff', fontFamily: 'monospace' }}>
//                       {formatValue(row[p])}
//                     </td>
//                   ))}
//                 </tr>
//               ))
//             ) : (
//               <tr>
//                 <td colSpan={periods.length + 1} style={{ padding: '40px', textAlign: 'center', color: '#555' }}>
//                   해당 기간의 데이터를 표시할 수 없습니다.
//                 </td>
//               </tr>
//             )}
//           </tbody>
//         </table>
//       </div>
      
//       <p style={{ marginTop: '20px', fontSize: '12px', color: '#555' }}>
//         * Data provided by Yahoo Finance. Normalized for {period} reporting periods.
//       </p>
//     </div>
//   );
// };

// export default FinancialsTab;