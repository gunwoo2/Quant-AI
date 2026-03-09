// src/components/MetricCard.jsx
import React from 'react';
import Tippy from '@tippyjs/react';
import 'tippy.js/dist/tippy.css'; 
import 'tippy.js/animations/shift-away.css';

const MetricCard = ({ label, value, tooltip, isLastInRow, accentColor = '#D85604' }) => {
  // 툴팁 내용을 구조화하여 렌더링하는 함수
  const renderTooltip = (data) => {
    if (typeof data === 'string') return data;
    
    return (
      <div style={{ padding: '8px', lineHeight: '1.6', minWidth: '180px' }}>
        <div style={{ borderBottom: `1px solid ${accentColor}`, marginBottom: '8px', paddingBottom: '4px' }}>
          <strong style={{ color: accentColor, fontSize: '13px' }}>{data.title}</strong>
        </div>
        <div style={{ fontSize: '11px', color: '#ccc', marginBottom: '4px' }}>
          <span style={{ color: '#888' }}>공식:</span> {data.formula}
        </div>
        <div style={{ fontSize: '12px', color: '#fff', marginBottom: '8px' }}>
          {data.meaning}
        </div>
        <div style={{ 
          fontSize: '11px', 
          backgroundColor: '#222', 
          padding: '6px', 
          borderRadius: '4px', 
          color: '#F3BE26',
          borderLeft: `2px solid #F3BE26`
        }}>
          <strong>판단 기준:</strong> {data.standard}
        </div>
      </div>
    );
  };

  return (
    <div style={{ 
      padding: '24px 20px', 
      display: 'flex', 
      flexDirection: 'column', 
      gap: '8px',
      borderRight: isLastInRow ? 'none' : '1px solid #1a1a1a',
      transition: '0.2s ease',
      cursor: 'help'
    }}
    onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#111'}
    onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
        <span style={{ color: '#666', fontSize: '11px', fontWeight: 'bold', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
          {label}
        </span>
        <Tippy 
          content={renderTooltip(tooltip)}
          animation="shift-away"
          theme="dark"
          maxWidth={250}
        >
          <span style={{ 
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            width: '14px', height: '14px', borderRadius: '50%', 
            border: `1px solid #444`, color: '#666', fontSize: '9px', fontWeight: 'bold'
          }}>?</span>
        </Tippy>
      </div>
      <span style={{ 
        color: value === 'N/A' ? '#444' : '#fff', 
        fontSize: '24px', 
        fontWeight: '800',
        fontFamily: 'Inter, sans-serif'
      }}>
        {value}
      </span>
    </div>
  );
};

export default MetricCard;