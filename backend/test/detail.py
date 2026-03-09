from flask import Blueprint, render_template
import yfinance as yf
import pandas as pd
import numpy as np
import os

detail_bp = Blueprint('detail', __name__)

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def get_investment_rating(score):
    if score >= 90:
        return "S등급: STRONG BUY (강력 매수)", "rating-strong-buy"
    elif score >= 75:
        return "A등급: BUY (매수)", "rating-buy"
    elif score >= 50:
        return "B등급: HOLD (관망)", "rating-hold"
    else:
        return "C등급: SELL / AVOID (매도 및 주의)", "rating-sell"

@detail_bp.route("/detail/<ticker>")
def ticker_detail(ticker):
    stock = yf.Ticker(ticker)
    info = stock.info
    
    fin = stock.financials
    q_fin = stock.quarterly_financials
    bs = stock.balance_sheet
    cf = stock.cashflow
    
    # 데이터 소스 통일 (5년치 가져오되 최근 1년은 타이밍용, 전체는 이평선용)
    hist = stock.history(period="2y") 
    
    scores = {"quality": 0, "value": 0, "growth": 0, "timing": 0}
    detailed_metrics = {"quality": [], "value": [], "growth": [], "timing": []}
    
    try:
        def get_v(df, label, idx=0):
            return df.loc[label].iloc[idx] if label in df.index and not df.loc[label].empty else 0

        # 1. QUALITY (30%)
        rev = get_v(fin, 'Total Revenue')
        gp = get_v(fin, 'Gross Profit')
        assets = get_v(bs, 'Total Assets', 0) or 1
        gpa = gp / assets
        ni = get_v(fin, 'Net Income')
        equity = get_v(bs, 'Stockholders Equity', 0) or 1
        debt = get_v(bs, 'Total Debt', 0)
        roic = ni / (equity + debt) if (equity + debt) != 0 else 0
        fcf = get_v(cf, 'Free Cash Flow') or (get_v(cf, 'Operating Cash Flow') - abs(get_v(cf, 'Capital Expenditure')))
        fcf_margin = fcf / rev if rev > 0 else 0

        scores['quality'] = (10 if gpa > 0.3 else 6) + (10 if roic > 0.15 else 6) + (10 if fcf_margin > 0.15 else 6)
        detailed_metrics['quality'] = [
            {"label": "GP/A (자산효율성)", "value": f"{gpa:.2f}", "is_good": gpa > 0.3, "description": "자산 대비 매출총이익 비중입니다. 0.5 이상이면 아주 뛰어난 수익성을 의미합니다."},
            {"label": "ROIC (수익성)", "value": f"{roic*100:.1f}%", "is_good": roic > 0.15, "description": "실제 영업에 투입된 자본이 벌어들이는 수익률입니다. 높을수록 경제적 해자가 큽니다."},
            {"label": "FCF Margin", "value": f"{fcf_margin*100:.1f}%", "is_good": fcf_margin > 0.15, "description": "매출 중 현금으로 남는 비율입니다. 이 비율이 높아야 배당과 재투자가 가능합니다."}
        ]

        # 2. VALUE (25%)
        mkt_cap = info.get('marketCap', 1)
        ev = mkt_cap + debt - info.get('totalCash', 0)
        ebit = get_v(fin, 'EBIT') or 1
        ev_ebit = ev / ebit
        peg = info.get('trailingPegRatio', 0) or 1.5
        psr = info.get('priceToSalesTrailing12Months', 0)
        
        scores['value'] = int((8.3 if ev_ebit < 15 else 4) + (8.4 if peg < 1.2 else 4) + (8.3 if psr < 2.0 else 4))
        detailed_metrics['value'] = [
            {"label": "EV/EBIT", "value": f"{ev_ebit:.1f}x", "is_good": ev_ebit < 15, "description": "시가총액뿐 아니라 부채까지 고려한 실질 가치 대비 영업이익 수준입니다."},
            {"label": "PEG Ratio", "value": f"{peg:.2f}", "is_good": peg < 1.0, "description": "PER을 이익성장률로 나눈 값입니다. 보통 1.0 미만이면 매우 저평가로 봅니다."},
            {"label": "P/S (PSR)", "value": f"{psr:.2f}", "is_good": psr < 2.0, "description": "매출액 대비 주가 수준입니다. 성장주가 저평가되어 있는지 판단할 때 유용합니다."}
        ]

        # 3. GROWTH (20%)
        rev_growth = (get_v(q_fin, 'Total Revenue', 0) / get_v(q_fin, 'Total Revenue', 1) - 1) if q_fin.shape[1] > 1 else 0
        op_growth = (get_v(q_fin, 'Operating Income', 0) / get_v(q_fin, 'Operating Income', 1) - 1) if q_fin.shape[1] > 1 else 0
        op_leverage = op_growth / rev_growth if rev_growth > 0 else 0
        prev_rev_growth = (get_v(q_fin, 'Total Revenue', 1) / get_v(q_fin, 'Total Revenue', 2) - 1) if q_fin.shape[1] > 2 else 0
        accel = rev_growth - prev_rev_growth
        
        scores['growth'] = (10 if op_leverage > 1.5 else 5) + (10 if accel > 0 else 5)
        detailed_metrics['growth'] = [
            {"label": "영업 레버리지", "value": f"{op_leverage:.2f}", "is_good": op_leverage > 1.5, "description": "매출이 늘 때 이익이 더 가파르게 증가하는 정도입니다. 기업의 효율성을 나타냅니다."},
            {"label": "매출 가속화", "value": f"{accel*100:+.1f}%", "is_good": accel > 0, "description": "전분기 성장률보다 이번 분기 성장률이 더 빨라졌는지를 측정합니다."}
        ]

        # 4. TIMING (25%) - 스마트 머니 수급 분석
        close = hist['Close']
        high = hist['High']
        low = hist['Low']
        volume = hist['Volume']
        current_price = close.iloc[-1]
        
        # (1) 200일 이평선
        ma200 = close.rolling(window=200).mean().iloc[-1]
        t1 = 6.25 if current_price > ma200 else 0
        
        # (2) VWAP (20일 근사)
        typical_price = (high + low + close) / 3
        vwap = (typical_price * volume).rolling(window=20).sum() / volume.rolling(window=20).sum()
        vwap_val = vwap.iloc[-1]
        t2 = 6.25 if current_price > vwap_val else 1.5
        
        # (3) Squeeze (BB vs KC)
        ma20 = close.rolling(window=20).mean()
        std20 = close.rolling(window=20).std()
        upper_bb = ma20 + (std20 * 2)
        lower_bb = ma20 - (std20 * 2)
        atr20 = (high - low).rolling(window=20).mean()
        upper_kc = ma20 + (atr20 * 1.5)
        lower_kc = ma20 - (atr20 * 1.5)
        is_squeeze = (lower_bb.iloc[-1] > lower_kc.iloc[-1]) and (upper_bb.iloc[-1] < upper_kc.iloc[-1])
        t3 = 6.25 if is_squeeze or (current_price > upper_bb.iloc[-1]) else 1.5
        
        # (4) MFI
        mf = typical_price * volume
        pos_mf = mf.where(typical_price > typical_price.shift(1), 0).rolling(window=14).sum()
        neg_mf = mf.where(typical_price < typical_price.shift(1), 0).rolling(window=14).sum()
        mfi = 100 - (100 / (1 + (pos_mf / neg_mf).iloc[-1]))
        t4 = 6.25 if 20 <= mfi <= 60 else 2

        scores['timing'] = int(t1 + t2 + t3 + t4)
        detailed_metrics['timing'] = [
            {"label": "VWAP (기관평균가)", "value": f"${vwap_val:.2f}", "is_good": current_price > vwap_val, "description": "거래량 가중 평균가입니다. 기관들의 평균 단가로 보며 주가가 이 위에 있어야 유리합니다."},
            {"label": "Squeeze 상태", "value": "응축중" if is_squeeze else "발산", "is_good": is_squeeze, "description": "에너지가 압축된 상태(Squeeze)입니다. 곧 강력한 시세 폭발이 일어날 가능성이 큽니다."},
            {"label": "MFI (자금유입)", "value": f"{mfi:.1f}", "is_good": 20 <= mfi <= 60, "description": "거래량이 실린 수급 지표입니다. 20~60 사이는 스마트 머니가 조용히 매집하는 구간입니다."}
        ]
        

    except Exception as e:
        print(f"Algorithm Error: {e}")

    # total_score = sum(scores.values())
    # rating_text, rating_class = get_investment_rating(total_score)
    
    # history_table = stock.history(period="100d").sort_index(ascending=False)
    # price_history = []
    # for date, row in history_table.iterrows():
    #     price_history.append((date.strftime('%Y-%m-%d'), date.strftime('%a'), round(row['Open'], 2), round(row['Close'], 2), round(row['High'], 2), round(row['Low'], 2), f"{int(row['Volume']):,}"))

    # return render_template("detail.html", ticker=ticker, info=info, total_score=total_score, scores=scores, detailed_metrics=detailed_metrics, rating_text=rating_text, rating_class=rating_class, price_history_extended=price_history)
    # --- [전체 점수 및 등급 계산] ---
    total_score = sum(scores.values())
    rating_text, rating_class = get_investment_rating(total_score)
    
    # --- [주가 히스토리 및 변동률 계산] ---
    # 변동률 계산을 위해 100일보다 하루 더(101일) 가져옵니다.
    history_raw = stock.history(period="101d").sort_index(ascending=False)
    price_history = []

    # 현재 행(i)과 다음 행(i+1, 즉 전일)을 비교하여 변동률 계산
    for i in range(len(history_raw) - 1):
        curr_row = history_raw.iloc[i]
        prev_row = history_raw.iloc[i + 1]
        
        # 전일 종가 대비 변동률 (%)
        if prev_row['Close'] != 0:
            change_pct = ((curr_row['Close'] - prev_row['Close']) / prev_row['Close']) * 100
        else:
            change_pct = 0
            
        date_obj = history_raw.index[i]
        
        price_history.append((
            date_obj.strftime('%Y-%m-%d'),          # 0: 날짜
            date_obj.strftime('%a'),                # 1: 요일
            round(curr_row['Open'], 2),             # 2: 시가
            round(curr_row['Close'], 2),            # 3: 종가
            round(curr_row['High'], 2),             # 4: 고가
            round(curr_row['Low'], 2),              # 5: 저가
            f"{int(curr_row['Volume']):,}",         # 6: 거래량
            round(change_pct, 2)                    # 7: 변동률 (%) - 추가됨
        ))

    return render_template("detail.html", 
                           ticker=ticker, 
                           info=info, 
                           total_score=total_score, 
                           scores=scores, 
                           detailed_metrics=detailed_metrics, 
                           rating_text=rating_text, 
                           rating_class=rating_class, 
                           price_history_extended=price_history)