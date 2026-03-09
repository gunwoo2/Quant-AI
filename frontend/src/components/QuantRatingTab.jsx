import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import api from '../api';
import {
  Radar, RadarChart, PolarGrid, PolarAngleAxis,
  ResponsiveContainer, Tooltip
} from 'recharts';

const QuantRatingTab = () => {
  const { ticker } = useParams();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [isGuideOpen, setIsGuideOpen] = useState(false); // 가이드 섹션 접힘 상태 관리

  useEffect(() => {
    const fetchQuantData = async () => {
      try {
        setLoading(true);
        const res = await api.get(`/api/stock/detail/${ticker}/quant`);
        setData(res.data);
      } catch (err) {
        setData({ error: "데이터 로드 실패" });
      } finally {
        setLoading(false);
      }
    };
    if (ticker) fetchQuantData();
  }, [ticker]);

const getRating = (score) => {
  // S 등급 (80점+): ALPHA PEAK
  if (score >= 80) {
    return {
      label: "S",
      title: "Strong Buy",
      color: "#00F5FF",
      status: "기관급 QVM 팩터 최상단 정렬",
      action: "퀀트 엔진이 포착한 최상위 5% 종목입니다. 구조적 성장과 가격 모멘텀이 결합된 '슈퍼 사이클' 구간입니다."
    };
  }

  // A+ 등급 (72점+): HIGH CONVICTION
  if (score >= 72) {
    return {
      label: "A+",
      title: "Buy",
      color: "#00F5FF",
      status: "펀더멘털 가속화 + 기관 수급 유입",
      action: "확실한 이익 개선과 함께 시장 대비 초과 수익(Alpha)을 창출할 준비가 끝난 종목입니다. 공격적 편입이 유효합니다."
    };
  }

  // A 등급 (65점+): GROWTH STABLE
  if (score >= 65) {
    return {
      label: "A",
      title: "Outperform",
      color: "#D85604",
      status: "안정적 밸류에이션 + 추세 강화",
      action: "시장 지수(S&P 500)를 상회할 체력이 충분합니다. 조정 시마다 비중을 늘려가는 전략이 권장됩니다."
    };
  }

  // B+ 등급 (55점+): MOMENTUM CHASE
  if (score >= 55) {
    return {
      label: "B+",
      title: "Hold",
      color: "#F3BE26",
      status: "팩터간 불균형 또는 에너지 응축",
      action: "기업의 질은 우수하나 가격 반영이 다소 과하거나, 반대로 밸류는 싸지만 모멘텀이 부족한 '관망' 구간입니다."
    };
  }

  // B 등급 (45점+): NEUTRAL ZONE
  if (score >= 45) {
    return {
      label: "B",
      title: "Underperform",
      color: "#AD1B02",
      status: "성장성 정체 및 밸류 부담 발생",
      action: "기대 수익률이 시장 평균을 밑돌 가능성이 높습니다. 신규 진입보다는 타 종목으로의 교체 매매를 고려하십시오."
    };
  }

  // C 등급 (35점+): RISK ALERT
  if (score >= 35) {
    return {
      label: "C",
      title: "Sell",
      color: "#AD1B02",
      status: "펀더멘털 훼손 및 하락 추세 지속",
      action: "성장 엔진이 꺼졌거나 과도한 고평가 영역입니다. 자산 보호를 위해 비중 축소 및 리스크 관리가 시급합니다."
    };
  }

  // D 등급 (35점 미만): AVOID
  return {
    label: "D",
    title: "Strong Sell",
    color: "#AD1B02",
    status: "재무적 리스크 및 역성장 트랩",
    action: "퀀트 지표 상 최하위 구간입니다. 원금 회복이 불투명한 역성장의 늪에 빠져 있으므로 즉시 관심을 끄십시오."
  };
};

  if (loading) return <div style={{ color: '#D85604', textAlign: 'center', padding: '100px', fontWeight: '900', backgroundColor: '#000', height: '100vh' }}>ANALYZING...</div>;
  if (!data || data.error) return <div style={{ color: 'red', textAlign: 'center', padding: '100px', backgroundColor: '#000', height: '100vh' }}>데이터를 불러올 수 없습니다.</div>;

  const rating = getRating(data.totalScore || 0);
  const radarData = [
    { subject: 'MOAT\n(35)', A: data.moatScore || 0, fullMark: 35 },
    { subject: 'VALUE\n(25)', A: data.valueScore || 0, fullMark: 25 },
    { subject: 'GROWTH\n(25)', A: data.growthScore || data.momentumScore || 0, fullMark: 25 }, 
    { subject: 'TECH\n(15)', A: data.technicalScore || 0, fullMark: 25 },
  ];
  
  return (
    <div style={{ backgroundColor: '#000', color: '#fff', padding: '20px', fontFamily: 'Inter, sans-serif' }}>
      
      {/* 🚀 0. 전략 안내 메시지 섹션 (접이식 아코디언 튜닝) */}
      <div style={{ 
        marginBottom: '30px', 
        backgroundColor: '#0A0A0A', 
        borderRadius: '24px', 
        border: '1px solid #1A1A1A',
        backgroundImage: 'linear-gradient(135deg, #0A0A0A 0%, #111 100%)',
        position: 'relative',
        overflow: 'hidden',
        transition: 'all 0.3s ease'
      }}>
        {/* 배경 워터마크 (QVM) */}
        <div style={{ 
          position: 'absolute', right: '-10px', bottom: '-20px', 
          fontSize: '120px', fontWeight: '900', color: '#151515', 
          zIndex: 0, userSelect: 'none', opacity: isGuideOpen ? 1 : 0.3,
          transition: 'opacity 0.4s'
        }}>4-Factor</div>

        {/* 헤더 부분 (클릭 시 토글) */}
        <div 
          onClick={() => setIsGuideOpen(!isGuideOpen)}
          style={{ 
            padding: '20px 40px', 
            cursor: 'pointer', 
            display: 'flex', 
            alignItems: 'center', 
            justifyContent: 'space-between',
            position: 'relative',
            zIndex: 2
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '15px' }}>
            <div style={{ 
              width: '10px', height: '10px', borderRadius: '50%', 
              backgroundColor: '#E669A2', 
              boxShadow: isGuideOpen ? '0 0 12px #E669A2' : '0 0 5px rgba(230, 105, 162, 0.5)' 
            }} />
            <span style={{ fontSize: '13px', fontWeight: '800', color: '#E669A2', letterSpacing: '2px' }}>
              ALPHA HUNTER QUANT ENGINE {!isGuideOpen && <span style={{ color: '#555', marginLeft: '10px', fontWeight: '500' }}>| QVM MODEL STRATEGY</span>}
            </span>
          </div>
          <span style={{ fontSize: '11px', fontWeight: '900', color: '#444', letterSpacing: '1px' }}>
            {isGuideOpen ? 'CLOSE ▲' : 'STRATEGY DETAILS ▼'}
          </span>
        </div>

        {/* 펼쳐지는 상세 내용 */}
        <div style={{ 
          maxHeight: isGuideOpen ? '400px' : '0px', 
          opacity: isGuideOpen ? 1 : 0,
          padding: isGuideOpen ? '0 40px 30px 40px' : '0 40px',
          transition: 'all 0.4s cubic-bezier(0.4, 0, 0.2, 1)',
          position: 'relative',
          zIndex: 1
        }}>
          <div style={{ borderTop: '1px solid #1A1A1A', paddingTop: '20px' }}>
            <h1 style={{ fontSize: '17px', fontWeight: '900', marginBottom: '15px', color: '#fff', lineHeight: '1.5' }}>
            이 모델은 <span style={{ color: '#E669A2' }}>좋은 기업이 시장에서 재평가되는 순간</span>을 포착하기 위한 4-Factor 전략입니다.
            </h1>

            <p style={{ fontSize: '12.5px', color: '#888', lineHeight: '1.8', maxWidth: '850px', margin: 0, fontWeight: '500' }}>
            망하지 않을 재무 체력(Quality)을 갖춘 기업을 선별하고, 
            시장 평균 대비 저평가 구간(Value)에서 접근하며, 
            실적 구조가 개선되기 시작하는 국면(Growth)을 확인합니다. 
            그리고 마지막으로 가격 추세와 수급이 그 변화를 인정하기 시작할 때(Technical) 비중을 실습니다.
            </p>

            <p style={{ fontSize: '12.5px', color: '#888', lineHeight: '1.8', maxWidth: '850px', marginTop: '8px', fontWeight: '500' }}>
            즉, 이 전략은 바닥을 예측하지 않습니다. 
            </p>
            <p style={{ fontSize: '13.5px', color: '#ffffffff', lineHeight: '1.8', maxWidth: '850px', marginTop: '8px', fontWeight: '500' }}>
            대신 기업의 펀더멘털과 시장의 인식 변화가 동시에 정렬되는 구간에서 
            확률적으로 우위가 쌓이는 지점을 공략합니다.
            </p>
          </div>
        </div>
      </div>

      {/* 1. 상단 섹션: 등급 카드 & 레이더 차트 */}
      <div style={{ display: 'flex', gap: '20px', marginBottom: '40px', flexWrap: 'wrap' }}>
        {/* 등급 요약 카드 */}
        <div style={{ flex: 1, minWidth: '350px', backgroundColor: '#0A0A0A', borderRadius: '24px', border: '1px solid #1A1A1A', padding: '30px', position: 'relative', overflow: 'hidden' }}>
          <div style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '4px', backgroundColor: rating.color }} />
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <div style={{ fontSize: '12px', fontWeight: '800', color: '#555', letterSpacing: '2px' }}>OVERALL SCORE</div>
              <div style={{ fontSize: '72px', fontWeight: '900', color: rating.color, lineHeight: '1.1' }}>{data.totalScore}</div>
              <div style={{ fontSize: '18px', fontWeight: '900', color: rating.color, marginTop: '5px' }}>{rating.title}</div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: '80px', fontWeight: '900', color: '#151515', position: 'absolute', right: '20px', top: '20px', zIndex: 0 }}>{rating.label}</div>
            </div>
          </div>
          <div style={{ marginTop: '20px', padding: '15px', backgroundColor: '#111', borderRadius: '12px', position: 'relative', zIndex: 1 }}>
            <div style={{ color: rating.color, fontSize: '11px', fontWeight: '800', marginBottom: '5px' }}>STATUS: {rating.status}</div>
            <div style={{ color: '#eee', fontSize: '13px', lineHeight: '1.5' }}>{rating.action}</div>
          </div>
        </div>

        {/* 레이더 차트 (팩터 밸런스) */}
        <div style={{ flex: 1, minWidth: '350px', backgroundColor: '#0A0A0A', borderRadius: '24px', border: '1px solid #1A1A1A', padding: '30px' }}>
          <div style={{ fontSize: '12px', fontWeight: '800', color: '#555', letterSpacing: '2px', textAlign: 'center', marginBottom: '15px' }}>FACTOR BALANCE</div>
          <div style={{ width: '100%', height: '200px' }}>
            <ResponsiveContainer width="100%" height="100%">
              <RadarChart data={radarData}>
                <PolarGrid stroke="#222" />
                <PolarAngleAxis dataKey="subject" tick={{ fill: '#666', fontSize: 12, fontWeight: 'bold' }} />
                <Tooltip 
                  contentStyle={{ backgroundColor: '#111', border: '1px solid #333', borderRadius: '8px', color: '#fff' }}
                  itemStyle={{ color: rating.color }}
                />
                <Radar dataKey="A" stroke={rating.color} fill={rating.color} fillOpacity={0.4} />
              </RadarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* 2. 하단 상세 섹션 (상세 지표 리스트) */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '50px' }}>
        
        {/* Quality Section */}
        <SectorGroup 
          title="🛡️ MOAT SCORE (Economic Moat)" 
          subtitle="비즈니스의 질적 우위와 자본 효율성 검증" 
          goal="목표: 경쟁자가 침범할 수 없는 수익의 '지속 가능성'을 측정합니다."
          color="#f4f4f4e6" 
          weight="35%"
        >
          <MetricRow 
            label="GPA" 
            value={data.metrics?.gpa?.toFixed(2)} 
            sub="자산 대비 수익성" 
            formula="Gross Profit / Total Assets" 
            scoring="15.75점: 0.45↑ | 12.60점: 0.35↑ | 9.45점: 0.25↑ | 6.30점: 0.15↑ | 0점: 0.15↓"
            // desc="[수익성 끝판왕] '로버트 노비-막스' 공식. 자산 대비 현금을 찍어내는 원천적인 힘을 측정하며, 우량주 판별의 가장 강력한 잣대입니다." 
            desc="총자산 대비 총이익 비율. 자산이 얼마나 생산적으로 작동하는지를 측정하며, 장기 초과수익과 높은 상관관계를 보이는 핵심 Quality 팩터입니다."
          />
          <MetricRow 
            label="ROIC" 
            value={`${(data.metrics?.roic * 100).toFixed(1)}%`} 
            sub="투자자본 수익률" 
            formula="NOPAT / Invested Capital" 
            scoring="14점: 20%↑ | 11.2점: 15%↑ | 8.4점: 10%↑ | 5.6점: 6%↑ | 0점: 6%↓"
            // desc="[자본 효율성] 워런 버핏의 원픽. 외부 조달 자본까지 포함해 얼마나 영리하게 돈을 굴리고 있는지를 보여주는 경제적 해자의 척도입니다." 
            desc="투하 자본 대비 세후 영업이익 수익률. 지속 가능한 경쟁 우위(경제적 해자)의 정량적 대리 지표로 활용됩니다."
          />
          <MetricRow 
            label="Accruals" 
            value={
              data.metrics?.accruals !== undefined 
                ? `${(Number(data.metrics.accruals) * 100).toFixed(2)}%` 
                : "N/A"
            }
            sub="이익의 질 (발생액)" 
            formula="(NI - OCF) / Total Assets" 
            scoring="5.25점: -5%↓ | 4.2점: 0%↓ | 3.15점: 5%↓ | 2.1점: 10%↓ | 0점: 10%↑"
            // desc="[회계 투명성] 장부상 이익과 실제 현금흐름의 괴리를 추적합니다. 수치가 낮을수록 '가짜 이익'이 없는 깨끗하고 정직한 기업입니다." 
            desc="회계상 이익과 실제 현금흐름 간 괴리를 측정합니다. 낮을수록 이익의 질이 높고 향후 수익 지속 가능성이 개선됩니다."
          />
        </SectorGroup>

        {/* Value Section */}
        <SectorGroup 
          title="💎 VALUE SCORE (Intrinsic Value)" 
          subtitle="내재 가치 대비 안전 마진 확보 여부" 
          goal="목표: 훌륭한 기업을 '합리적인 가격' 혹은 '싼 가격'에 선점합니다."
          color="#f4f4f4e6" 
          weight="25%"
        >
          <MetricRow 
            label="EV/EBIT" 
            // 1. null/undefined 체크하여 N/A 표시
            // 2. 숫자인 경우 소수점 1자리까지 표시
            value={
              (data.metrics?.evEbit === 9999) 
                ? "N/A" 
                : data.metrics?.evEbit.toFixed(1)
            }
            sub="기업 가치 배수" 
            formula="Enterprise Value / EBIT" 
            // 데이터 부재 시 중간 점수를 주기로 했으므로 가이드 문구도 수정하는 것이 좋습니다.
            scoring="10점: 8↓ | 8점: 12↓ | 6점: 18↓ | 4점: 25↓ | 0점: 25↑ or 적자"
            // desc="[퀀트 마법공식] 시가총액에 부채까지 고려한 진짜 몸값 대비 이익 비율. 낮을수록 투자 원금 회수 속도가 빠른 저평가 상태입니다. (N/A시 중립 점수)" 
            desc="회계상 이익과 실제 현금흐름 간 괴리를 측정합니다. 낮을수록 이익의 질이 높고 향후 수익 지속 가능성이 개선됩니다."
          />
          <MetricRow 
            label="PEG" 
            value={data.metrics?.peg} 
            sub="성장성 대비 밸류에이션" 
            formula="P/E Ratio / Growth Rate" 
            scoring="10점: 0.8↓ | 8점: 1.0↓ | 6점: 1.5↓ | 4점: 2.0↓ | 0점: 2.0↑"
            // desc="[성장주 마스터] 피터 린치의 핵심 지표. 기업의 성장 가치에 비해 주가가 과열되지 않았는지 판단하여 '합리적인 성장주'를 찾습니다." 
            desc="성장률 대비 가격 부담 수준을 측정합니다. 1 이하 구간은 성장 대비 합리적 가격대로 평가됩니다."
          />
          <MetricRow 
            label="PFCR" 
            value={data.metrics?.pfcr} 
            sub="현금 흐름 배수" 
            formula="Market Cap / FCF" 
            scoring="5점: 10↓ | 4점: 15↓ | 3점: 20↓ | 2점: 30↓ | 0점: 30↑"
            // desc="[진짜 현금력] 회계적 이익이 아닌, 재투자 후 기업이 실제로 손에 쥐는 '잉여현금(FCF)' 대비 주가 수준을 시니컬하게 평가합니다." 
            desc="잉여현금흐름 대비 시가총액 배수. 기업의 실제 현금 창출력이 주가에 과도하게 반영되었는지 판단합니다."
          />
        </SectorGroup>

        {/* Growth & Momentum Section */}
        <SectorGroup 
          title="🚀 GROWTH & MOMENTUM (Fundamental Catalyst)" 
          subtitle="내부 엔진 가동과 실적 폭발의 전조 현상 포착" 
          goal="목표: 주가가 오르기 직전, 내부 지표의 '임계점'을 통과하는 종목을 선점합니다."
          color="#f4f4f4e6" 
          weight="25%"
        >
          <MetricRow 
            label="F-Score" 
            value={`${data.metrics?.fScore}/9`} 
            sub="재무 펀더멘털 개선도" 
            formula="Piotroski 9 Criteria" 
            scoring="15점: 9 | 12점: 7~8 | 9점: 5~6 | 6점: 3~4 | 0점: 0~2"
            // desc="[체질 개선 신호] 9가지 재무 항목을 통해 기업이 전년보다 확실하게 건강해졌는지를 측정하는 강력한 턴어라운드 감별사입니다." 
            desc="9개 재무 항목을 통해 기업의 체질 개선 여부를 계량화합니다. 턴어라운드 초입 구간 탐지에 유용한 지표입니다."
          />
          <MetricRow 
            label="Asset Turnover Acceleration" 
            value={
              data.metrics?.atoacceleration !== undefined 
                ? Number(data.metrics.atoacceleration).toFixed(2) 
                : "N/A"
            }
            sub="자산 회전율 가속도" 
            formula="Current ATO - Prev ATO" 
            scoring="5점: 0.05↑ | 4점: 0.03↑ | 3점: 0.01↑ | 2점: 0↑ | 0점: 0↓"
            // desc="[병목 돌파 - Hidden Alpha] 시장이 뒷북을 치기 전, 기업 내부 자산이 현금으로 바뀌는 속도가 가팔라지는 '물리적 임계점'을 포착합니다." 
            desc="자산 회전율 변화율을 측정합니다. 운영 효율성 개선이 실적 서프라이즈로 이어질 가능성을 선행적으로 포착합니다."
          />
          <MetricRow 
            label="Operating Leverage" 
            value={data.metrics?.opLeverage} 
            sub="영업 레버리지" 
            formula="Op Income Growth / Revenue Growth" 
            scoring="5점: 2.0↑ | 4점: 1.5↑ | 3점: 1.2↑ | 2점: 1.0↑ | 0점: 1.0↓"
            // desc="[이익의 폭발력] 고정비 절감 효과로 인해 매출이 조금만 늘어도 이익이 몇 배로 튀어 오르는 '수익 구조의 혁신' 구간을 포착합니다." 
            desc="매출 증가 대비 영업이익 증가 배율. 고정비 구조 개선 시 이익 민감도가 확대되는 구간을 탐지합니다."
          />          
        </SectorGroup>
        {/* Technical Timing Section - QVM Momentum Model */}
        <SectorGroup 
          title="📈 TECHNICAL MOMENTUM (Institutional Confirmation)" 
          subtitle="시장 초과수익과 구조적 추세 형성 여부를 점검"
          goal="목표: 펀더멘털이 준비된 종목이 실제로 자금 유입과 함께 추세를 형성하는지 확인합니다."
          color="#f4f4f4e6"
          weight="15%"
        >

          {/* 1️⃣ Relative Momentum */}
          <MetricRow 
            label="Relative 12M Momentum"
            value={
              data.technical?.relativeMomentumPct === undefined
                ? "N/A"
                : `${data.technical.relativeMomentumPct.toFixed(2)}%`
            }
            sub="시장 대비 초과수익"
            formula="Stock 12M Return - Market 12M Return"
            scoring="6점: +30%↑ | 4.8점: +20%↑ | 3.6점: +10%↑ | 2.4점: 0%↑ | 0점: 0%↓"
            // desc="최근 1년간 시장(S&P500) 대비 얼마나 초과수익을 냈는지 측정합니다. 모멘텀 팩터는 장기적으로 가장 강력한 알파 요인입니다."
            desc="최근 12개월 시장 대비 초과수익률. 글로벌 팩터 리서치에서 가장 일관되게 검증된 알파 요인 중 하나입니다."
          />

          {/* 2️⃣ 52W High Distance */}
          <MetricRow 
            label="52W High Distance"
            value={
              data.technical?.dist52W === undefined
                ? "N/A"
                : `${data.technical.dist52W.toFixed(2)}%`
            }
            sub="신고가 대비 위치"
            formula="(Current - 52W High) / 52W High"
            scoring="4.5점: -5% 이내 | 3.6점: -10% | 2.7점: -20% | 1.8점: -35% | 0점: -35%↓"
            // desc="주가가 52주 신고가 근처에 있을수록 기관 수급이 강하고 추세 지속 확률이 높습니다."
            desc="신고가 대비 현재 위치를 측정합니다. 신고가 인접 구간은 기관 수급이 유지되는 추세 구간일 확률이 높습니다."
          />

          {/* 3️⃣ Trend Stability */}
          <MetricRow 
            label="Trend Stability (R² 90D)"
            value={
              data.technical?.trendR2 === undefined
                ? "N/A"
                : data.technical.trendR2.toFixed(2)
            }
            sub="추세 구조 안정성"
            formula="90일 선형회귀 R²"
            scoring="3점: 0.80↑ | 2.4점: 0.70↑ | 1.8점: 0.60↑ | 1.2점: 0.40↑ | 0점: 0.40↓"
            // desc="최근 90일간 가격이 얼마나 '직선에 가깝게' 상승했는지 측정합니다. R²가 높을수록 기관형 추세로 판단합니다."
            desc="최근 90일 가격 경로의 선형 적합도(R²). 높을수록 변동성 대비 방향성이 일관된 추세 구조로 판단합니다."
          />

          {/* 4️⃣ Volatility Compression */}
          <MetricRow 
            label="Volatility Compression"
            value={
              data.technical?.annualVol === undefined
                ? "N/A"
                : data.technical.annualVol.toFixed(2)
            }
            sub="단기/장기 변동성 비율"
            formula="Std(20D) / Std(120D)"
            scoring="1.5점: 0.6↓ | 1.2점: 0.8↓ | 0.9점: 1.0↓ | 0.6점: 1.2↓ | 0점: 1.2↑"
            // desc="단기 변동성이 장기 대비 낮아질수록 에너지가 응축된 상태입니다. 돌파 직전 구간에서 자주 관찰됩니다."
            desc="단기 대비 장기 변동성 비율. 낮은 값은 에너지 응축 구간으로, 추세 확장의 전조일 수 있습니다."
          />

        </SectorGroup>
      </div>
    </div>
  );
};

// --- 서브 컴포넌트: 섹터 그룹 ---
const SectorGroup = ({ title, subtitle, goal, color, weight, children }) => (
  <div style={{ width: '100%' }}>
    <div style={{ 
      borderBottom: `2px solid ${color}`, 
      paddingBottom: '12px', 
      display: 'flex', 
      justifyContent: 'space-between', 
      alignItems: 'flex-end' 
    }}>
      <h2 style={{ fontSize: '22px', fontWeight: '900', color: color, margin: 0 }}>{title}</h2>
      <span style={{ fontSize: '11px', fontWeight: '800', color: '#444', letterSpacing: '1px' }}>WEIGHT: {weight}</span>
    </div>

    <div style={{ 
      padding: '10px 0 20px 0', 
      display: 'flex', 
      flexDirection: 'column', 
      gap: '4px' 
    }}>
      <div style={{ fontSize: '14px', fontWeight: '700', color: '#a2a2a2ff' }}>"{subtitle}"</div>
      <div style={{ fontSize: '12px', fontWeight: '500', color: '#666' }}>{goal}</div>
    </div>

    <div style={{ display: 'flex', flexDirection: 'column', gap: '1px', backgroundColor: '#1A1A1A' }}>
      {children}
    </div>
  </div>
);

// --- 서브 컴포넌트: 개별 지표 행 ---
const MetricRow = ({ label, value, sub, formula, scoring, desc }) => (
  <div style={{ 
    display: 'flex', 
    alignItems: 'center', 
    backgroundColor: '#0A0A0A', 
    padding: '20px 30px', 
    borderBottom: '1px solid #1A1A1A',
    transition: 'background 0.2s ease'
  }}>
    <div style={{ flex: '0 0 40%', display: 'flex', flexDirection: 'column', paddingRight: '20px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
        <span style={{ fontSize: '16px', fontWeight: '900', color: '#D85604', letterSpacing: '-0.5px' }}>{label}</span>
        <span style={{ fontSize: '12px', fontWeight: '700', color: '#888' }}>{sub}</span>
      </div>
      <div style={{ fontSize: '11.5px', color: '#666', lineHeight: '1.5', fontWeight: '400' }}>
        {desc}
      </div>
    </div>

    <div style={{ flex: '0 0 35%', display: 'flex', flexDirection: 'column', gap: '6px', borderLeft: '1px solid #222', paddingLeft: '25px' }}>
      <div style={{ fontSize: '11px', color: '#555' }}>
        <b style={{ color: '#888', marginRight: '6px' }}>FORMULA:</b> 
        <span style={{ color: '#aaa', fontFamily: 'monospace' }}>{formula}</span>
      </div>
      <div style={{ fontSize: '11px', color: '#555' }}>
        <b style={{ color: '#888', marginRight: '6px' }}>TARGET:</b> 
        <span style={{ color: '#F3BE26', fontWeight: '700' }}>{scoring}</span>
      </div>
    </div>

    <div style={{ flex: '1', textAlign: 'right', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
      <div style={{ fontSize: '10px', color: '#444', fontWeight: '900', marginBottom: '2px', letterSpacing: '1px' }}>CURRENT VALUE</div>
      <div style={{ 
        fontSize: '26px', 
        fontWeight: '900', 
        color: '#FFFFFF',
        textShadow: '0 0 15px rgba(216, 86, 4, 0.3)'
      }}>
        {value || '-'}
      </div>
    </div>
  </div>
);

export default QuantRatingTab;