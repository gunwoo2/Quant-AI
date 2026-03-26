import React from 'react';
import { C } from '../styles/tokens';

const Footer = () => {
  return (
    <footer style={{
      width: '100%',
      backgroundColor: '#000000',
      borderTop: '1px solid #2d2d2d',
      padding: '40px 0',
      marginTop: 'auto'
    }}>
      <div style={{
        maxWidth: '1200px',
        margin: '0 auto',
        padding: '0 40px',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: '20px'
      }}>
        {/* 로고 및 슬로건 */}
        <div style={{ textAlign: 'center' }}>
          <div style={{ 
            color: '#D85604', 
            fontSize: '12px', 
            fontWeight: '800', 
            letterSpacing: '4px',
            marginBottom: '4px'
          }}>
            QUANT TRADING ADVISOR
          </div>
          <div style={{ color: '#444', fontSize: '10px', letterSpacing: '1px' }}>
            ADVANCED ALGORITHMIC TRADING SOLUTIONS
          </div>
        </div>

        {/* 법적 고지 (퀀트 사이트 필수 요소) */}
        <div style={{ 
          color: '#333', 
          fontSize: '11px', 
          textAlign: 'center', 
          lineHeight: '1.6',
          maxWidth: '500px'
        }}>
          © 2026 GunWoo KIM. All rights reserved. Market data is based on the previous trading day. Batch processing is performed daily at 10:00 AM KST.
          This platform is intended for professional investors and institutional use only.
        </div>

        {/* 시스템 스테이터스 */}
        <div style={{
          display: 'flex',
          gap: '15px',
          fontSize: '10px',
          color: '#555',
          fontFamily: 'monospace',
          border: '1px solid #111',
          padding: '4px 12px',
          borderRadius: '2px'
        }}>
          <span>STATUS: <span style={{color: C.up}}>●</span> ONLINE</span>
          <span style={{color: '#222'}}>|</span>
          <span>VERSION: 1.1.0-PRO</span>
          <span style={{color: '#222'}}>|</span>
          <span>LAST DEPLOY: 2026-03-026</span>
        </div>
      </div>
    </footer>
  );
};

export default Footer;