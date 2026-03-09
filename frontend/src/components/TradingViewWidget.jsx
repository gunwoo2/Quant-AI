import React, { useEffect, useRef } from 'react';

export default function TradingViewWidget({ symbol }) {
  const container = useRef();

  useEffect(() => {
    // 1. 기존에 생성된 스크립트나 위젯이 있다면 삭제 (중복 방지)
    if (container.current) {
      container.current.innerHTML = "";
    }

    const script = document.createElement("script");
    script.src = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
    script.type = "text/javascript";
    script.async = true;
    
    // 2. symbol에 거래소 없이 티커만 넣기
    script.innerHTML = JSON.stringify({
      "autosize": true,
      "symbol": symbol, // 'NASDAQ:AAPL' 대신 'AAPL'만 전달
      "interval": "D",
      "timezone": "Etc/UTC",
      "theme": "dark",
      "style": "1",
      "locale": "en",
      "enable_publishing": false,
      "allow_symbol_change": true, // 사용자가 위젯 안에서 직접 티커를 바꿀 수 있게 허용
      "calendar": false,
      "support_host": "https://www.tradingview.com"
    });

    container.current.appendChild(script);
  }, [symbol]);

  return (
    <div 
      className="tradingview-widget-container" 
      ref={container} 
      style={{ height: "100%", width: "100%", backgroundColor: "#000" }} 
    />
  );
}