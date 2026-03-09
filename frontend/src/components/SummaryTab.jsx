import React, { useState, useEffect } from 'react';
import { useOutletContext } from 'react-router-dom';
import TradingViewWidget from './TradingViewWidget';
import MetricCard from './MetricCard';

export default function SummaryTab() {
  const { ticker, realtime } = useOutletContext();
  const [activeNewsTab, setActiveNewsTab] = useState('news');
  const [displayList, setDisplayList] = useState([]); // 뉴스 또는 공시 목록 저장
  const [loading, setLoading] = useState(true);

  // 데이터 가져오기 (뉴스 또는 공시)
  useEffect(() => {
    const fetchData = async () => {
      if (!ticker) return;
      setLoading(true);
      try {
        // 탭에 따라 엔드포인트 분기
        const endpoint = activeNewsTab === 'news' ? `/api/news/${ticker}` : `/api/filings/${ticker}`;
        const response = await fetch(endpoint);
        
        if (!response.ok) throw new Error('Fetch Error');
        const data = await response.json();
        setDisplayList(data);
      } catch (error) {
        console.error("Data fetch error:", error);
        setDisplayList([]);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [ticker, activeNewsTab]); // 탭이 바뀔 때마다 다시 fetch

  // 기존 지표 데이터 (건드리지 않음)
  const valuationStats = [
    { label: 'EPS (TTM)', value: realtime?.eps ? `$${Number(realtime.eps).toFixed(2)}` : 'N/A', tooltip: { title: 'EPS (주당순이익)', formula: '당기순이익 ÷ 총 발행 주식 수', meaning: '주식 1주가 벌어들인 돈.', standard: '우상향이 좋습니다.' } },
    { label: 'PER (실시간)', value: realtime?.per ? `${Number(realtime.per).toFixed(2)}x` : 'N/A', tooltip: { title: 'PER (주가수익비율)', formula: '주가 ÷ EPS', meaning: '이익 대비 주가 수준.', standard: '15~20배가 적정선.' } },
    { label: 'Forward PER', value: realtime?.forwardPer ? `${Number(realtime.forwardPer).toFixed(2)}x` : 'N/A', tooltip: { title: 'Forward PER', formula: '주가 ÷ 예상 EPS', meaning: '미래 가치 대비 주가.', standard: '현재 PER보다 낮으면 성장 신호.' } },
    { label: 'PBR', value: realtime?.pbr ? `${Number(realtime.pbr).toFixed(2)}` : 'N/A', tooltip: { title: 'PBR (주가순자산비율)', formula: '주가 ÷ BPS', meaning: '자산 대비 주가 수준.', standard: '1배 미만은 저평가.' } },
  ];

  const profitabilityStats = [
    { label: 'ROE (자기자본)', value: realtime?.roe ? `${Number(realtime.roe).toFixed(2)}%` : 'N/A', tooltip: { title: 'ROE', formula: '순이익 ÷ 자기자본', meaning: '자본 효율성.', standard: '15% 이상 우량.' } },
    { label: 'ROA (총자산)', value: realtime?.roa ? `${Number(realtime.roa).toFixed(2)}%` : 'N/A', tooltip: { title: 'ROA', formula: '순이익 ÷ 총자산', meaning: '자산 운용 수익률.', standard: '5~10% 양호.' } },
    { label: 'ROI (투자)', value: realtime?.roi ? `${Number(realtime.roi).toFixed(2)}%` : 'N/A', tooltip: { title: 'ROI', formula: '순이익 ÷ 투자자본', meaning: '실질 투자 수익.', standard: '10% 이상 합격.' } },
    { label: 'ROIC [TTM_12개월 합산] (투하자본)', value: realtime?.roic ? `${Number(realtime.roic).toFixed(2)}%` : 'N/A', tooltip: { title: 'ROIC', formula: '영업이익 ÷ 투하자본', meaning: '영업 효율성.', standard: '15% 이상 독점적 해자.' } },
  ];

  const SectionHeader = ({ title, subTitle, question, description, color }) => (
    <div style={{ marginBottom: '15px', padding: '0 4px', borderTop: `2px solid ${color}`, paddingTop: '16px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
        <h3 style={{ color: '#fff', fontSize: '15px', margin: 0, fontWeight: '800' }}>{title}</h3>
        <span style={{ color: '#555', fontSize: '12px', fontWeight: '600' }}>({subTitle})</span>
        <span style={{ backgroundColor: `${color}15`, color: color, padding: '2px 10px', borderRadius: '4px', fontSize: '11px', fontWeight: '900', marginLeft: '8px', border: `1px solid ${color}33` }}>{question}</span>
      </div>
      <p style={{ color: '#777', fontSize: '12px', margin: 0, lineHeight: '1.5' }}>{description}</p>
    </div>
  );

  const gridContainerStyle = { display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', backgroundColor: '#0a0a0a', border: '1px solid #1a1a1a', borderRadius: '12px', overflow: 'hidden', marginBottom: '30px' };
  const subTabStyle = (isActive) => ({ padding: '10px 20px', cursor: 'pointer', fontSize: '14px', fontWeight: '700', color: isActive ? '#D85604' : '#666', borderBottom: isActive ? '2px solid #D85604' : '2px solid transparent', transition: '0.3s' });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '25px', padding: '20px' }}>
      
      {/* 1. 차트 영역 */}
      <div style={{ height: '450px', backgroundColor: '#111', borderRadius: '12px', overflow: 'hidden', border: '1px solid #222' }}>
        <TradingViewWidget symbol={ticker || 'AAPL'} />
      </div>

      {/* 2. 지표 영역 */}
      <div style={{ padding: '28px', backgroundColor: '#0f0f0f', borderRadius: '20px', border: '1px solid #1a1a1a', boxShadow: '0 10px 30px rgba(0,0,0,0.5)' }}>
        <SectionHeader title="Valuation" subTitle="가치 평가" question="Value: 주가가 저렴한가?" description="현재 주가가 기업의 내재가치나 이익 대비 어느 수준인지 측정합니다." color="#D85604" />
        <div style={gridContainerStyle}>
          {valuationStats.map((stat, idx) => (
            <MetricCard key={idx} {...stat} isLastInRow={idx === 3} accentColor="#D85604" />
          ))}
        </div>

        <SectionHeader title="Profitability" subTitle="수익성 분석" question="Quality: 돈을 얼마나 잘 버는가?" description="자본과 자산을 얼마나 효율적으로 사용하여 이익을 창출하는지 측정합니다." color="#F3BE26" />
        <div style={gridContainerStyle}>
          {profitabilityStats.map((stat, idx) => (
            <MetricCard key={idx} {...stat} isLastInRow={idx === 3} accentColor="#F3BE26" />
          ))}
        </div>
      </div>

      {/* 3. 하단 뉴스/공시 섹션 */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.8fr 1.2fr', gap: '30px' }}>
        <div>
          <div style={{ display: 'flex', borderBottom: '1px solid #222', marginBottom: '20px' }}>
            <div style={subTabStyle(activeNewsTab === 'news')} onClick={() => setActiveNewsTab('news')}>Latest News</div>
          </div>
          
          <div style={{ display: 'flex', flexDirection: 'column', gap: '25px' }}>
            {loading ? (
              <div style={{ color: '#D85604', textAlign: 'center', padding: '40px' }}>Loading Intel...</div>
            ) : displayList.length > 0 ? (
              displayList.map((item, idx) => (
                <div key={idx} onClick={() => window.open(item.url, '_blank')} style={{ display: 'flex', gap: '20px', cursor: 'pointer' }}>
                  {/* 뉴스일 때만 썸네일 노출, 공시는 아이콘으로 대체 가능 (현재는 공통 레이아웃 유지) */}
                  <div style={{ minWidth: '140px', height: '90px', backgroundColor: '#222', borderRadius: '8px', overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    {item.thumbnail ? (
                        <img src={item.thumbnail} alt="thumb" style={{ width: '100%', height: '100%', objectFit: 'cover', opacity: 0.7 }} />
                    ) : (
                        <div style={{ color: '#AD1B02', fontWeight: 'bold', fontSize: '20px' }}>{item.type}</div>
                    )}
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', gap: '10px', marginBottom: '5px', fontSize: '12px' }}>
                      <span style={{ color: activeNewsTab === 'news' ? '#D85604' : '#AD1B02', fontWeight: '700' }}>{item.source}</span>
                      <span style={{ color: '#555' }}>{item.time}</span>
                    </div>
                    <h4 style={{ color: '#fff', fontSize: '16px', margin: '0 0 8px 0', lineHeight: '1.3' }}>{item.title}</h4>
                    <p style={{ color: '#888', fontSize: '13px', margin: 0, display: '-webkit-box', WebkitLineClamp: '2', WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                      {item.content}
                    </p>
                  </div>
                </div>
              ))
            ) : (
              <div style={{ color: '#555', textAlign: 'center', padding: '40px' }}>No data found for {ticker}.</div>
            )}
          </div>
        </div>

        {/* AI Rating History (기존 디자인 보존) */}
        <div style={{ padding: '25px', backgroundColor: '#0a0a0a', border: '1px solid #222', borderRadius: '16px', alignSelf: 'start' }}>
          <h3 style={{ color: '#fff', fontSize: '16px', marginBottom: '25px', display: 'flex', alignItems: 'center', gap: '10px', fontWeight: '800' }}>
            <span style={{ width: '3px', height: '15px', backgroundColor: '#D85604' }}></span>
            AI Rating History
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            {[{ date: '2026-02-28', grade: 'S', color: '#D85604', desc: 'Premium Outlook' },
              { date: '2026-02-15', grade: 'A+', color: '#F3BE26', desc: 'Strong Growth' },
              { date: '2026-01-30', grade: 'A', color: '#E88D14', desc: 'Stable' }].map((item, idx) => (
              <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <div style={{ color: item.color, fontWeight: '900', fontSize: '18px' }}>{item.grade}</div>
                  <div style={{ color: '#555', fontSize: '11px', fontWeight: '700' }}>{item.desc}</div>
                </div>
                <div style={{ color: '#666', fontSize: '12px', fontFamily: 'monospace' }}>{item.date}</div>
              </div>
            ))}
          </div>
          <button style={{ width: '100%', marginTop: '30px', padding: '12px', borderRadius: '8px', backgroundColor: 'transparent', color: '#D85604', border: '1px solid #D85604', fontWeight: '800', cursor: 'pointer', fontSize: '13px' }}>Download Report (PDF)</button>
        </div>
      </div>
    </div>
  );
}