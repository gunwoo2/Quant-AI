import yfinance as yf

def get_stock_prices(tickers):
    """
    tickers: ['AAPL', 'TSLA', ...] 형태의 리스트
    반환: { 'AAPL': {'price': 180.2, 'change': 1.5}, ... }
    """
    if not tickers:
        return {}
    
    try:
        # 여러 티커를 한 번에 다운로드
        data = yf.download(tickers, period="1d", interval="1m", progress=False)
        result = {}
        
        for ticker in tickers:
            # 티커가 하나일 때와 여러 개일 때 데이터 구조가 다를 수 있어 처리 필요
            try:
                if len(tickers) == 1:
                    current_price = data['Close'].iloc[-1]
                    prev_close = data['Close'].iloc[0]
                else:
                    current_price = data['Close'][ticker].iloc[-1]
                    prev_close = data['Close'][ticker].iloc[0]
                
                # 등락률 계산: ((현재가 - 전일종가) / 전일종가) * 100
                change_pct = ((current_price - prev_close) / prev_close) * 100
                
                result[ticker] = {
                    "price": round(float(current_price), 2),
                    "change": round(float(change_pct), 2)
                }
            except:
                result[ticker] = {"price": 0, "change": 0}
                
        return result
    except Exception as e:
        print(f"Yahoo Finance Error: {e}")
        return {}