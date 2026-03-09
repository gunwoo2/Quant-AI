"""
/home/gguakim33/stock-app/stock-app/backend/services/api_service.py
퀀트 레이팅 및 지표/재무제표 관련 로직은 /home/gguakim33/stock-app/stock-app/backend/services/calculator.py 에서 수행
"""
import yfinance as yf
import requests
import json
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
import numpy as np
from scipy import stats
import traceback
from sklearn.linear_model import LinearRegression
import pytz
from secret_info.config import settings 
from services.kis_api_service import get_kis_realtime_price, get_access_token
import concurrent.futures
from services.calculator import (
    get_quant_rating as calculate_quant_scores, 
    get_technical_timing as calculate_technical_timing,
    calculate_financial_metrics
)
import traceback

# 기존 개별 변수 대신 settings 객체 활용 (유지보수 용이)
APP_KEY = settings.KIS_APP_KEY
APP_SECRET = settings.KIS_APP_SECRET
BASE_URL = settings.KIS_BASE_URL

# ==========================
# 1️⃣ Yahoo Fallback
# ==========================
def get_yahoo_price(ticker):
    """KIS 실패 시 보조용으로 사용 (fast_info 사용으로 속도 개선)"""
    try:
        stock = yf.Ticker(ticker)
        info = stock.fast_info
        curr = info.last_price
        prev = info.previous_close
        
        if not curr or not prev:
            return {"price": 0, "change": 0, "amount_change": 0} # 기본값 추가

        change_amount = curr - prev # 👈 금액 계산
        change_rate = (change_amount / prev) * 100
        
        return {
            "price": round(float(curr), 2),
            "change": round(float(change_rate), 2),
            "amount_change": round(float(change_amount), 2), # 👈 필드 추가
            "changesPercentage": round(float(change_rate), 2)
        }
    except Exception:
        return {"price": 0, "change": 0, "amount_change": 0}


def fetch_price(ticker):
    try:
        # 1. KIS 우선 시도
        res = get_kis_realtime_price(ticker)
        
        # 2. 결과가 없거나, 가격이 0이거나, 필드가 비어있으면 Yahoo로 보완
        if not res or res.get("price", 0) <= 0:
            # print(f"ℹ️ {ticker}: KIS 데이터 불완전, Yahoo 호출 중...")
            res = get_yahoo_price(ticker)
            
        # 3. 최종적으로도 데이터가 없으면 None 반환 (리스트에서 제외되도록)
        if not res or res.get("price", 0) <= 0:
            return ticker, None
            
        return ticker, res
    except Exception as e:
        print(f"🚨 fetch_price 예외: {e}")
        return ticker, None


def get_multiple_realtime_prices(ticker_list):
    if not ticker_list: return {}
    
    get_access_token() # 토큰 사전 확보
    unique_tickers = list(set([t.strip().upper() for t in ticker_list if t]))
    results = {}

    import concurrent.futures
    # 💡 속도 최적화: max_workers를 10~15 사이로 유지하는 것이 
    # 한투 서버의 ConnectionError를 줄이는 데 가장 효과적입니다.
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
        future_to_ticker = {executor.submit(fetch_price, t): t for t in unique_tickers}
        
        for future in concurrent.futures.as_completed(future_to_ticker):
            ticker, data = future.result()
            if data:
                results[ticker] = data

    return results

# ==========================
# 2️⃣ 메인 함수 (병렬 처리 최적화)
# ==========================
def get_multiple_realtime_prices(ticker_list):
    if not ticker_list: return {}
    
    get_access_token() # 토큰 사전 확보
    unique_tickers = list(set([t.strip().upper() for t in ticker_list if t]))
    results = {}

    import concurrent.futures
    # max_workers를 15로 조절 (한투 초당 호출 제한 방어)
    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
        future_to_ticker = {executor.submit(fetch_price, t): t for t in unique_tickers}
        
        for future in concurrent.futures.as_completed(future_to_ticker):
            ticker, data = future.result()
            # 💡 데이터가 있는 경우만 딕셔너리에 추가 (상폐/에러 종목 자동 스킵)
            if data:
                results[ticker] = data

    return results

# ==========================
# 3️⃣ 단일 종목 상세 데이터 (재무 지표 포함)
# ==========================
def get_stock_realtime_data(ticker):
    ticker = ticker.strip().upper()
    kis_data = get_kis_realtime_price(ticker)
    
    if not kis_data:
        fallback = get_yahoo_price(ticker)
        result = {
            "price": fallback.get("price", 0), 
            "change": 0, # 밑에서 야후 info로 보정됨
            "amount_change": fallback.get("amount_change", 0), # 👈 추가
            "changesPercentage": fallback.get("change", 0),
            "isUp": fallback.get("change", 0) >= 0, 
            "exchange": "N/A", "eps": 0, "per": 0, "pbr": 0
        }
    else:
        result = {
            "price": kis_data.get("price", 0), 
            "change": kis_data.get("change", 0),
            "amount_change": kis_data.get("amount_change", 0), # 👈 1순위: KIS 데이터에서 가져옴
            "changesPercentage": kis_data.get("changesPercentage", 0),
            "isUp": kis_data.get("changesPercentage", 0) >= 0,
            "exchange": "US", 
            "eps": kis_data.get("eps", 0), 
            "per": kis_data.get("per", 0), 
            "pbr": kis_data.get("pbr", 0)
        }

    # 2. Yahoo Finance 보완 로직 부분
    try:
        yt = yf.Ticker(ticker)
        info = yt.info

        # [A] 등락 정보 보완 (야후 info 우선일 때도 금액 계산)
        if result["amount_change"] == 0: # 금액이 없으면 보완
            y_price = info.get("regularMarketPrice") or result["price"]
            y_prev = info.get("regularMarketPreviousClose")
            if y_price and y_prev:
                result["amount_change"] = round(y_price - y_prev, 2) # 👈 여기도 업데이트
                result["change"] = round(((y_price - y_prev) / y_prev) * 100, 2)
                result["changesPercentage"] = result["change"]
                result["isUp"] = result["amount_change"] >= 0

        # [B] 재무제표 데이터 로드 (EBIT, 자산, 자본 등 추출용)
        # info에 없으면 이 데이터프레임들을 뒤집니다.
        fn = yt.get_financials()
        bs = yt.get_balance_sheet()

        if fn is None or fn.empty or bs is None or bs.empty:
            result["roic"] = 0
            return result

        # 🔹 컬럼 최신순 정렬 (Yahoo 컬럼 순서 방어)
        fn = yt.financials if not yt.financials.empty else yt.quarterly_financials
        bs = yt.balance_sheet if not yt.balance_sheet.empty else yt.quarterly_balance_sheet

        # 데이터가 아예 없으면 중단
        if fn.empty or bs.empty:
            print(f"⚠️ [ROIC ERROR] {ticker} - Financial data not found on Yahoo.")
            result["roic"] = 0
            return result

        # 최신순 정렬
        fn = fn.sort_index(axis=1, ascending=False)
        bs = bs.sort_index(axis=1, ascending=False)

        def get_val(df, keys):
            """대소문자 무시 및 부분 일치 검색으로 값 추출"""
            # 인덱스를 모두 소문자/공백제거로 변환하여 비교
            df_index_clean = [str(idx).lower().replace(" ", "") for idx in df.index]
            
            for k in keys:
                clean_k = k.lower().replace(" ", "")
                if clean_k in df_index_clean:
                    idx = df_index_clean.index(clean_k)
                    val = df.iloc[idx].iloc[0] # 최신 열 값
                    if pd.notna(val):
                        return float(val)
            return 0.0

        # --- 데이터 추출 (더 강력해진 후보군) ---
        ebit = get_val(fn, ['EBIT', 'Operating Income', 'Normalized EBIT', 'OperatingIncome'])
        net_income = get_val(fn, ['Net Income Common Stockholders', 'Net Income', 'NetIncome'])
        total_assets = get_val(bs, ['Total Assets', 'TotalAssets'])
        
        # 세금 및 세전이익
        tax_provision = get_val(fn, ['Tax Provision', 'Income Tax Expense', 'TaxProvision'])
        pretax_income = get_val(fn, ['Pretax Income', 'Income Before Tax', 'PretaxIncome'])
        
        # 자본 및 부채
        total_equity = get_val(bs, ['Stockholders Equity', 'Total Equity', 'Common Stock Equity', 'TotalStockholdersEquity'])
        total_debt = get_val(bs, ['Total Debt', 'Long Term Debt', 'TotalDebt'])
        cash = get_val(bs, ['Cash And Cash Equivalents', 'Cash Financial', 'CashAndCashEquivalents'])

        # --- 로직 보정 ---
        # EBIT 역산 (ebit이 0일 때만)
        if ebit == 0 and net_income != 0:
            int_exp = get_val(fn, ['Interest Expense', 'InterestExpense'])
            ebit = net_income + tax_provision + int_exp

        # 세율 계산 (비정상적이면 21% 적용)
        tax_rate = tax_provision / pretax_income if pretax_income > 0 else 0.21
        tax_rate = max(0, min(tax_rate, 0.5)) # 0% ~ 50% 사이로 제한

        nopat = ebit * (1 - tax_rate)
        invested_capital = (total_equity + total_debt) - cash

        # 최종 ROIC
        if invested_capital > 0:
            result["roic"] = round((nopat / invested_capital) * 100, 2)
        else:
            result["roic"] = 0

        # 로그 확인용
        # print(f"📊 [FINAL DEBUG] {ticker} | EBIT: {ebit} | IC: {invested_capital} | ROIC: {result['roic']}")

        result["roa"] = round((net_income / total_assets * 100), 2) if total_assets > 0 else 0
        result["roe"] = round((net_income / total_equity * 100), 2) if total_equity > 0 else 0
        result["roi"] = round((net_income / (total_equity + total_debt) * 100), 2) if (total_equity + total_debt) > 0 else 0

        # EPS 및 PER 최종 보완
        if result["eps"] == 0:
            result["eps"] = round(net_income / shares, 2) if shares > 0 else info.get("trailingEps", 0)
        
        curr_price = result["price"]
        forward_eps = info.get("forwardEps") or 0
        result["forwardPer"] = round(curr_price / forward_eps, 2) if forward_eps > 0 else round(info.get("forwardPE", 0), 2)
        
        # KIS 지표가 0일 때만 야후값으로 덮어쓰기
        if result["per"] == 0: result["per"] = info.get("trailingPE", 0)
        if result["pbr"] == 0: result["pbr"] = info.get("priceToBook", 0)

        # print(f"✅ [SUCCESS] {ticker} - ROE: {result['roe']}%, ROIC: {result['roic']}%")

    except Exception as e:
        print(f"🔥 [DEBUG ERROR] {ticker} Supplement Failed: {e}")
        # 에러 발생 시 기본값 보장
        for m in ["roic", "roa", "roe", "roi", "forwardPer"]:
            result.setdefault(m, 0)

    return result

STANDARD_ORDER = [
    "Total Revenue", "Cost Of Revenue", "Gross Profit", 
    "Operating Expense", "Operating Income", "Net Income", "EBITDA",
    "Total Assets", "Total Liabilities Net Minority Interest", "Total Equity Gross Minority Interest",
    "Operating Cash Flow", "Investing Cash Flow", "Financing Cash Flow", "Free Cash Flow"
]

def get_financials_data(ticker_symbol, period='annual'):
    try:
        stock = yf.Ticker(ticker_symbol.upper())
        
        # 1. 데이터 확보
        if period == 'quarterly':
            fn, bs, cf = stock.quarterly_financials, stock.quarterly_balance_sheet, stock.quarterly_cashflow
        else:
            fn, bs, cf = stock.financials, stock.balance_sheet, stock.cashflow

        # 데이터 부재 시 백업
        if fn.empty: fn = stock.quarterly_financials if not stock.quarterly_financials.empty else pd.DataFrame()
        if bs.empty: bs = stock.quarterly_balance_sheet if not stock.quarterly_balance_sheet.empty else pd.DataFrame()
        if cf.empty: cf = stock.quarterly_cashflow if not stock.quarterly_cashflow.empty else pd.DataFrame()

        if fn.empty or bs.empty:
            return {"error": "재무제표 데이터를 가져올 수 없습니다."}

        # ---------------------------------------------------------
        # [핵심 추가] 인덱스(날짜) 동기화 로직
        # ---------------------------------------------------------
        # 세 데이터프레임의 공통 열(날짜)을 찾습니다.
        common_cols = fn.columns.intersection(bs.columns).intersection(cf.columns)
        
        # 공통 날짜가 없으면 에러 (보통 데이터가 매우 부족할 때 발생)
        if len(common_cols) == 0:
            return {"error": "재무 항목 간 공통 데이터 시점이 존재하지 않습니다."}

        # 공통 날짜로 필터링하고 과거순으로 정렬
        fn = fn[common_cols].sort_index(axis=1, ascending=True)
        bs = bs[common_cols].sort_index(axis=1, ascending=True)
        cf = cf[common_cols].sort_index(axis=1, ascending=True)
        
        years = [col.strftime('%Y' if period == 'annual' else '%Y-%m') for col in fn.columns]
        # ---------------------------------------------------------

        def format_for_table(df):
            # ... (기존 format_for_table 로직 동일) ...
            formatted_data = []
            for label in df.index:
                row = {"label": str(label)}
                for i, year_str in enumerate(years):
                    val = df.iloc[df.index.get_loc(label), i]
                    row[year_str] = float(val) if not (pd.isna(val) or np.isinf(val)) else 0
                formatted_data.append(row)
            return {"years": years, "data": formatted_data}

        def get_val(df, keywords):
            # ... (기존 get_val 로직 동일) ...
            if df.empty: return [0.0] * len(years)
            df_index_clean = [str(idx).lower().replace(" ", "").replace("_", "") for idx in df.index]
            for k in keywords:
                clean_k = k.lower().replace(" ", "").replace("_", "")
                if clean_k in df_index_clean:
                    idx = df_index_clean.index(clean_k)
                    # 이미 위에서 common_cols로 잘랐으므로 여기서 len(years)와 무조건 일치함
                    return df.iloc[idx].fillna(0).replace([np.inf, -np.inf], 0).tolist()
            return [0.0] * len(years)

        # 핵심 데이터 추출 (이제 모든 리스트의 길이가 len(years)로 동일함)
        revenue = get_val(fn, ['TotalRevenue', 'Revenue'])
        op_income = get_val(fn, ['OperatingIncome', 'EBIT'])
        net_income = get_val(fn, ['NetIncome'])
        ebitda = get_val(fn, ['EBITDA'])
        fcf = get_val(cf, ['FreeCashFlow', 'OperatingCashFlow'])
        total_debt = get_val(bs, ['TotalDebt', 'LongTermDebt'])
        cash = get_val(bs, ['CashAndCashEquivalents'])
        equity = get_val(bs, ['StockholdersEquity'])
        tax_provision_data = get_val(fn, ['TaxProvision'])
        pretax_income_data = get_val(fn, ['PretaxIncome'])
        
        market_cap = stock.info.get('marketCap', 1)

        # 모든 리스트의 길이가 같으므로 이제 'shape (5,) (7,)' 에러가 발생하지 않음
        calc_results = calculate_financial_metrics(
            years, revenue, op_income, ebitda, net_income, fcf, 
            total_debt, cash, equity, market_cap,
            tax_provision=tax_provision_data,  
            pretax_income=pretax_income_data,
            period=period  # 'annual' 또는 'quarterly' 전달
        )
        return {
            "ticker": ticker_symbol,
            "years": years,
            "metrics": {k: v for k, v in calc_results.items() if k != 'netDebt'},
            "raw": {
                "revenue": revenue,
                "opIncome": op_income,
                "netIncome": net_income,
                "fcf": fcf,
                "netDebt": calc_results["netDebt"]
            },
            "incomeStatement": format_for_table(fn),
            "balanceSheet": format_for_table(bs),
            "cashFlow": format_for_table(cf)
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        return {"error": f"백엔드 계산 오류: {str(e)}"}


def get_quant_rating(ticker_symbol):
    try:
        # ==========================================
        # 1. 데이터 수집부 (기존 로직 완벽 유지)
        # ==========================================
        stock = yf.Ticker(ticker_symbol.upper())
        bs = stock.get_balance_sheet()
        fin = stock.get_financials()
        cf = stock.get_cashflow()
        
        if bs.empty: bs = stock.get_quarterly_balance_sheet()
        if fin.empty: fin = stock.get_quarterly_financials()
        if cf.empty: cf = stock.get_quarterly_cashflow()

        def clean_df(df):
            if isinstance(df, pd.DataFrame) and not df.empty:
                df.index = df.index.astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.lower()
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(-1)
            return df

        bs, fin, cf = clean_df(bs), clean_df(fin), clean_df(cf)

        def get_val_safe(df, keyword, col_idx=0, default=0.0):
            if not isinstance(df, pd.DataFrame) or df.empty or len(df.columns) <= col_idx:
                return default
            keyword = keyword.lower().replace(" ", "")
            matches = [i for i in df.index if keyword in i]
            if matches:
                try:
                    val = df.loc[matches]
                    res = val.iloc[col_idx] if isinstance(val, pd.Series) else (val.iloc[0, col_idx] if isinstance(val, pd.DataFrame) else val)
                    return float(res) if pd.notna(res) else default
                except: return default
            return default

        total_assets = get_val_safe(bs, 'totalassets')
        total_assets_prev = get_val_safe(bs, 'totalassets', 1)
        total_equity = get_val_safe(bs, 'stockholdersequity')
        total_debt = get_val_safe(bs, 'totaldebt')
        cash = get_val_safe(bs, 'cashandcashequivalents')
        revenue = get_val_safe(fin, 'totalrevenue')
        revenue_prev = get_val_safe(fin, 'totalrevenue', 1)
        gross_profit = get_val_safe(fin, 'grossprofit')
        gross_profit_prev = get_val_safe(fin, 'grossprofit', 1)
        op_income = get_val_safe(fin, 'operatingincome')
        op_income_prev = get_val_safe(fin, 'operatingincome', 1)
        net_income = get_val_safe(fin, 'netincome')
        net_income_prev = get_val_safe(fin, 'netincome', 1)
        ebit = get_val_safe(fin, 'ebit')
        tax_provision = get_val_safe(fin, 'taxProvision')
        pretax_income = get_val_safe(fin, 'pretaxIncome')
        op_cf = get_val_safe(cf, 'operatingcashflow')
        cap_ex = get_val_safe(cf, 'capitalexpenditure')
        
        info = stock.info
        market_cap = info.get('marketCap', 0)
        current_per = market_cap / net_income if net_income != 0 else 999.0

        long_term_debt = get_val_safe(bs, 'longtermdebt')
        long_term_debt_prev = get_val_safe(bs, 'longtermdebt', 1)
        current_assets = get_val_safe(bs, 'currentassets')
        current_assets_prev = get_val_safe(bs, 'currentassets', 1)
        current_liab = get_val_safe(bs, 'currentliabilities')
        current_liab_prev = get_val_safe(bs, 'currentliabilities', 1)        

        pre_backup_assets = total_assets
        pre_backup_net_income = net_income
        pre_backup_revenue = revenue

        if total_assets == 0: total_assets = info.get('totalAssets', 0)
        if net_income == 0: net_income = info.get('netIncomeToCommon', 0)
        if revenue == 0: revenue = info.get('totalRevenue', 0)

        # ==========================================
        # 🚀 2. 모듈을 활용한 지표 계산 수행 (로직 분리 완료!)
        # ==========================================
        raw_data_dict = {
            'ticker': ticker_symbol.upper(),
            'total_assets': total_assets, 'total_assets_prev': total_assets_prev,
            'total_equity': total_equity, 'total_debt': total_debt, 'cash': cash,
            'revenue': revenue, 'revenue_prev': revenue_prev,
            'gross_profit': gross_profit, 'gross_profit_prev': gross_profit_prev,
            'op_income': op_income, 'op_income_prev': op_income_prev,
            'net_income': net_income, 'net_income_prev': net_income_prev,
            'ebit': ebit, 'tax_provision': tax_provision, 'pretax_income': pretax_income,
            'op_cf': op_cf, 'cap_ex': cap_ex, 'market_cap': market_cap, 'current_per': current_per,
            'long_term_debt': long_term_debt, 'long_term_debt_prev': long_term_debt_prev,
            'current_assets': current_assets, 'current_assets_prev': current_assets_prev,
            'current_liab': current_liab, 'current_liab_prev': current_liab_prev
        }
        
        # calculator.py 호출
        res = calculate_quant_scores(raw_data_dict)

        # [일괄점검] 만약 calculator에서 에러가 나서 필수 키가 누락된 경우 대비
        if "basics" not in res:
            res["basics"] = {"fcf": 0, "growth_rate_pct": 0, "peg_ratio": 0}
        if "moat" not in res:
            res["moat"] = {"gpa": 0, "roic": 0, "accruals": 0, "score": 0, "raw_sum": 0}
        if "value" not in res:
            res["value"] = {"ev_ebit": 0, "pfcr": 0, "score": 0, "raw_sum": 0, "ev": 0}
        if "momentum" not in res:
            res["momentum"] = {"f_score": 0, "ato_acceleration": 0, "score": 0, "raw_sum": 0}

        # ==========================================
        # 3. FULL DEBUG PRINT (터미널 확인용 - 유지됨)
        # ==========================================
        # print(f"✅ CALCULATED | MARKET CAP: {market_cap:.2f}")
        # print(f"✅ CALCULATED | NET INCOME: {net_income:.2f}")
        # print(f"✅ CALCULATED | PER: {current_per:.2f}")
        # print(f"✅ CALCULATED | Net Income Growth: {res['basics']['growth_rate_pct']:.2f}%")
        # print(f"✅ CALCULATED | PEG (Manual): {res['basics']['peg_ratio']:.2f}")

        # print(f"\n{'='*50}")
        # print(f"   📊 [QUANT DEBUG] Ticker: {ticker_symbol.upper()}")
        # print(f"{'='*50}")
        
        debug_list = [
            ("Total Assets (Current)", total_assets), ("Total Assets (Previous)", total_assets_prev),
            ("Total Equity", total_equity), ("Total Debt", total_debt), ("-" * 30, None),
            ("Long Term Debt (Cur)", long_term_debt), ("Long Term Debt (Prev)", long_term_debt_prev),
            ("Current Assets (Cur)", current_assets), ("Current Assets (Prev)", current_assets_prev),
            ("Current Liab (Cur)", current_liab), ("Current Liab (Prev)", current_liab_prev),
            ("-" * 30, None), ("Cash & Equivalents", cash),
            ("Revenue (Current)", revenue), ("Revenue (Previous)", revenue_prev),
            ("Gross Profit", gross_profit), ("Op Income (EBIT)", op_income),
            ("Net Income", net_income), ("Tax Provision", tax_provision),
            ("Pretax Income", pretax_income), ("-" * 30, None),
            ("Operating Cash Flow", op_cf), ("CapEx", cap_ex),
            ("Free Cash Flow", res['basics']['fcf']), ("-" * 30, None),
            ("Market Cap", market_cap), ("PEG Ratio", res['basics']['peg_ratio'])
        ]

        for label, value in debug_list:
            if value is None:
                print(label)
                continue
            status = "✅ OK" if value != 0 else "❌ MISSING"
            val_str = f"{value:,.0f}" if isinstance(value, (int, float)) and value != 0 else str(value)
            print(f"{status.ljust(10)} | {label.ljust(25)}: {val_str}")

        # print(f"{'-'*50}")
        # print(f"💡 Backup Triggered: Assets({'Yes' if pre_backup_assets==0 else 'No'}), "
        #       f"NetInc({'Yes' if pre_backup_net_income==0 else 'No'}), "
        #       f"Rev({'Yes' if pre_backup_revenue==0 else 'No'})")
        # print(f"📦 DF Status: BS({not bs.empty}), FIN({not fin.empty}), CF({not cf.empty})")
        # print(f"{'='*50}\n")
        
        if total_assets == 0 or market_cap == 0:
            return {"error": "재무 데이터가 부족하여 퀀트 평가를 진행할 수 없습니다."}

        # --- [1. QUALITY / MOAT] 디버깅 (Weight 35%) ---
        # print(f"\n{'='*25} [1. QUALITY SCORE DETAIL] {'='*25}")
        m = res['moat']
        # GPA 기준 업데이트 (0.4/0.3/0.2/0.1)
        # print(f"  ▶ GPA: {m['gpa']:.4f} (Target >=0.4:45, >=0.3:35, >=0.2:25, >=0.1:15)")
        # print(f"     => Score: {m['score_gpa']} / 45.0")
        # print(f"  ▶ ROIC: {m['roic']*100:.2f}% (Target >=20%:35, >=15%:30, >=12%:20, >=8%:10)")
        # print(f"     => Score: {m['score_roic']} / 35.0")
        # print(f"  ▶ Accruals: {m['accruals']*100:.2f}% (Target <=-5%:20, <=0%:15, <=5%:10, <=10%:5)")
        # print(f"     => Score: {m['score_accruals']} / 20.0")
        # print(f"  ------------------------------------------------------------")
        # print(f"  🛡️ RAW QUALITY SUM: {m['raw_sum']:.1f} / 100.0")
        # print(f"  🛡️ FINAL WEIGHTED MOAT (35%): {m['score']:.2f} / 35.0")

        # --- [2. VALUE] 디버깅 (Weight 25%) ---
        # print(f"\n{'='*25} [2. VALUE SCORE DETAIL] {'='*25}")
        v = res['value']
        # print(f"  ▶ EV/EBIT: {v['ev_ebit']:.2f} (Target <=10:50, <=15:40, <=20:30, <=25:15)")
        # print(f"     => Score: {v['score_ev']} / 50.0")
        # print(f"  ▶ PEG: {res['basics']['peg_ratio']:.2f} (Target <=0.8:30, <=1.2:25, <=1.8:15, <=2.5:5)")
        # print(f"     => Score: {v['score_peg']} / 30.0")
        # print(f"  ▶ P/FCF (PFCR): {v['pfcr']:.2f} (Target <=10:20, <=15:15, <=20:10, <=30:5)")
        # print(f"     => Score: {v['score_pfcr']} / 20.0")
        # print(f"  ------------------------------------------------------------")
        # print(f"  💎 RAW VALUE SUM: {v['raw_sum']:.1f} / 100.0")
        # print(f"  💎 FINAL WEIGHTED VALUE (25%): {v['score']:.2f} / 25.0")

        # --- [3. MOMENTUM] 디버깅 (Weight 25%) ---
        # print(f"\n{'='*25} [3. MOMENTUM SCORE DETAIL] {'='*25}")
        mom = res['momentum']
        # print(f"  ▶ F-Score: {mom['f_score']} / 9 (Target 9:55, 7-8:45, 5-6:30, 3-4:15)")
        # print(f"     => Score: {mom['score_f']} / 55.0")
        
        # 중요: 'ato_acceleration' 또는 'ato_improvement'가 0으로 찍히지 않도록 키 확인
        ato_val = mom.get('ato_improvement', 0)
        # print(f"  ▶ Δ Asset Turnover: {ato_val:.4f} (Target Δ >=0.05:25, >=0.02:20, >=0:15, >=-0.02:5)")
        # print(f"     => Score: {mom['score_ato']} / 25.0")
        
        # print(f"  ▶ Op Leverage: {mom['op_leverage']:.2f} (Target >=0.25:20, >=0.15:15, >=0.05:10, >=0:5)")
        # print(f"     => Score: {mom['score_oplev']} / 20.0")
        # print(f"  ------------------------------------------------------------")
        # print(f"  🚀 RAW MOMENTUM SUM: {mom['raw_sum']:.1f} / 100.0")
        # print(f"  🚀 FINAL WEIGHTED MOMENTUM (25%): {mom['score']:.2f} / 25.0")

        # --- 최종 TOTAL 합산 ---
        tech_info = res.get('technical', {})
        raw_tech_sum = float(tech_info.get('scores', {}).get('total', 0))
        weighted_tech_score = round(raw_tech_sum * 0.15, 2)

        # --- [4. TECHNICAL] 디버깅 (Weight 15%) ---
        # print(f"\n{'='*25} [4. TECHNICAL SCORE DETAIL] {'='*25}")
        t = res['technical']
        t_scores = t.get('scores', {})

        # trend_r2 대신 t.get('trendR2')를 사용해야 함
        current_trend_r2 = t.get('trendR2', 0)
        # print(f"  ▶ Rel. Momentum: {t.get('relativeMomentumPct', 0):.2f}% (Target >=30%:45, >=20%:35, >=10%:25, >=0%:10)")
        # print(f"  ▶ 52W Position: {t.get('position52W', 0):.2f}% (Target >=95%:25, >=85%:20, >=70%:15, >=55%:5)")
        # print(f"  ▶ Trend R² (90D): {current_trend_r2:.4f}")
        # print(f"  ▶ Annual Vol: {t.get('annualVol', 0):.2f}% (Target <=20%:10, <=30%:8, <=40%:5, <=60%:2)")
        # print(f"  ------------------------------------------------------------")
        # print(f"  📈 RAW TECH SUM: {raw_tech_sum:.1f} / 100.0")
        # print(f"  📈 FINAL WEIGHTED TECH (15%): {weighted_tech_score:.2f} / 15.0")

        # print(f"\n{'#'*60}")
        # print(f"🏆 FINAL QUANT TOTAL SCORE: {res['scores']['total']:.2f} / 100.0")
        # print(f"{'#'*60}\n")

        # 2. 모든 점수를 합산하여 최종 점수 계산 (중복 계산 삭제)
        total_score = round(
            float(res['moat']['score']) + 
            float(res['value']['score']) + 
            float(res['momentum']['score']) + 
            weighted_tech_score, 1
        )

        # 3. 결과 리턴
        return {
            "ticker": ticker_symbol,
            "totalScore": total_score,
            "moatScore": round(res['moat']['score'], 2),
            "valueScore": round(res['value']['score'], 2),
            "momentumScore": round(res['momentum']['score'], 2),
            "technicalScore": weighted_tech_score,       
            "technical": tech_info,             
            "metrics": {
                "gpa": round(res['moat']['gpa'], 4),
                "roic": round(res['moat']['roic'], 4),
                "accruals": round(res['moat']['accruals'], 4),
                "evEbit": round(res['value']['ev_ebit'], 2),
                "peg": round(res['basics']['peg_ratio'], 2),
                "pfcr": round(res['value']['pfcr'], 2),
                "fScore": res['momentum']['f_score'],
                "atoacceleration": round(res['momentum']['ato_improvement'], 4),
                "opLeverage": round(res['momentum']['op_leverage'], 2)
            }
        }

    except Exception as e:
        return {"error": str(e)}


# def get_technical_timing(ticker_symbol, market_symbol="^GSPC"):
#     try:
#         ticker = ticker_symbol.upper()
#         stock = yf.Ticker(ticker)
#         market = yf.Ticker(market_symbol)

#         df = stock.history(period="2y", auto_adjust=True)
#         mkt = market.history(period="2y", auto_adjust=True)

#         if df.empty or mkt.empty: return {"error": "Yahoo 데이터 수신 실패"}

#         close = df['Close'].dropna()
#         market_close = mkt['Close'].dropna()

#         if len(close) < 120 or len(market_close) < 120: return {"error": "히스토리 데이터 부족"}

#         # 💡 calculator.py 모듈 호출로 간소화
#         return calculate_technical_timing(close, market_close)

#     except Exception as e:
#         print(f"❌ TECH ERROR: {str(e)}")
#         traceback.print_exc()
#         return {"error": str(e)}

# if __name__ == "__main__":
#     import uvicorn

# def get_quant_rating(ticker_symbol):
#     try:
#         # Ticker 객체 생성 (대문자로 강제 변환)
#         stock = yf.Ticker(ticker_symbol.upper())
        
#         # [수정 1] 재무제표 강제 로드 시도
#         # yfinance의 내부 캐시 이슈를 피하기 위해 .get_xxx() 메서드 활용 고려
#         bs = stock.get_balance_sheet()
#         fin = stock.get_financials()
#         cf = stock.get_cashflow()
        
#         # 만약 여전히 비어있다면 분기 데이터를 대안으로 시도
#         if bs.empty: bs = stock.get_quarterly_balance_sheet()
#         if fin.empty: fin = stock.get_quarterly_financials()
#         if cf.empty: cf = stock.get_quarterly_cashflow()

#         def clean_df(df):
#             if isinstance(df, pd.DataFrame) and not df.empty:
#                 # 인덱스명을 소문자로 바꾸고 공백/특수문자 제거하여 비교 준비
#                 df.index = df.index.astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.lower()
#                 if isinstance(df.columns, pd.MultiIndex):
#                     df.columns = df.columns.get_level_values(-1)
#             return df

#         bs, fin, cf = clean_df(bs), clean_df(fin), clean_df(cf)

#         # [수정 2] 인덱스 키워드 유연화 (정규식 느낌으로 핵심 단어만 포함되면 추출)
#         def get_val_safe(df, keyword, col_idx=0, default=0.0):
#             if not isinstance(df, pd.DataFrame) or df.empty or len(df.columns) <= col_idx:
#                 return default
            
#             keyword = keyword.lower().replace(" ", "")
#             # 인덱스 중 키워드가 포함된 행 찾기
#             matches = [i for i in df.index if keyword in i]
#             if matches:
#                 try:
#                     val = df.loc[matches]
#                     res = val.iloc[col_idx] if isinstance(val, pd.Series) else (val.iloc[0, col_idx] if isinstance(val, pd.DataFrame) else val)
#                     return float(res) if pd.notna(res) else default
#                 except:
#                     return default
#             return default

#         # 데이터 추출 (키워드를 아주 단순하게 변경)
#         total_assets = get_val_safe(bs, 'totalassets')
#         total_assets_prev = get_val_safe(bs, 'totalassets', 1)
#         total_equity = get_val_safe(bs, 'stockholdersequity')
#         total_debt = get_val_safe(bs, 'totaldebt')
#         cash = get_val_safe(bs, 'cashandcashequivalents')
        
#         revenue = get_val_safe(fin, 'totalrevenue')
#         revenue_prev = get_val_safe(fin, 'totalrevenue', 1)
#         gross_profit = get_val_safe(fin, 'grossprofit')
#         gross_profit_prev = get_val_safe(fin, 'grossprofit', 1)
#         op_income = get_val_safe(fin, 'operatingincome')
#         op_income_prev = get_val_safe(fin, 'operatingincome', 1)
#         net_income = get_val_safe(fin, 'netincome')
#         net_income_prev = get_val_safe(fin, 'netincome', 1)
#         ebit = get_val_safe(fin, 'ebit')
#         tax_provision = get_val_safe(fin, 'taxprovision')
#         pretax_income = get_val_safe(fin, 'pretaxincome')
        
#         op_cf = get_val_safe(cf, 'operatingcashflow')
#         cap_ex = get_val_safe(cf, 'capitalexpenditure')
#         fcf = op_cf - abs(cap_ex)
        
#         info = stock.info
#         market_cap = info.get('marketCap', 0)
#         current_per = market_cap / net_income if net_income != 0 else 999.0
        
#         # 2. EPS 성장률 계산 (올해 순이익 / 작년 순이익)
#         # ※ 주의: 분모가 0이거나 음수면 성장률 측정이 불가능하므로 예외처리
#         if net_income_prev != 0:
#              # (올해 - 작년) / abs(작년) 공식은 작년이 적자여도 방향성을 보여줌
#             growth_rate_pct = ((net_income - net_income_prev) / abs(net_income_prev)) * 100
#         else:
#             growth_rate_pct = 0.0

#         # 3. PEG 계산 (PER / 성장률)
#         if growth_rate_pct > 0 and current_per > 0:
#            # 이익도 나고(PER > 0), 성장도 할 때(Growth > 0)만 정상 계산
#             peg_ratio = current_per / growth_rate_pct
#         elif current_per <= 0:
#             # 적자 기업이라면? PEG는 의미가 없으므로 페널티 부여
#             # (적자 기업은 밸류 점수를 낮게 받도록 5.0 같은 높은 수치 할당)
#             peg_ratio = 5.0 
#         else:
#             # 성장이 없거나 마이너스 성장인 경우
#             peg_ratio = 5.0 if growth_rate_pct < 0 else 1.5

#         # 2. 상단 디버그 출력 (여기서 변수명 확인)
#         print(f"✅ CALCULATED | MARKET CAP: {market_cap:.2f}")
#         print(f"✅ CALCULATED | NET INCOME: {net_income:.2f}")
#         print(f"✅ CALCULATED | PER: {current_per:.2f}")
#         print(f"✅ CALCULATED | Net Income Growth: {growth_rate_pct:.2f}%")
#         print(f"✅ CALCULATED | PEG (Manual): {peg_ratio:.2f}")

#         long_term_debt = get_val_safe(bs, 'longtermdebt')
#         long_term_debt_prev = get_val_safe(bs, 'longtermdebt', 1)
#         current_assets = get_val_safe(bs, 'currentassets')
#         current_assets_prev = get_val_safe(bs, 'currentassets', 1)
#         current_liab = get_val_safe(bs, 'currentliabilities')
#         current_liab_prev = get_val_safe(bs, 'currentliabilities', 1)        

#         # [수정 3] 재무제표가 비었을 때 info에서 최후의 수단으로 긁어오기
#         if total_assets == 0:
#             total_assets = info.get('totalAssets', 0)
#         if net_income == 0:
#             net_income = info.get('netIncomeToCommon', 0)
#         if revenue == 0:
#             revenue = info.get('totalRevenue', 0)

#         # [백업 로직 적용 전 상태 기록]
#         pre_backup_assets = total_assets
#         pre_backup_net_income = net_income
#         pre_backup_revenue = revenue

#         # [수정 3] 재무제표가 비었을 때 info에서 최후의 수단으로 긁어오기
#         if total_assets == 0: total_assets = info.get('totalAssets', 0)
#         if net_income == 0: net_income = info.get('netIncomeToCommon', 0)
#         if revenue == 0: revenue = info.get('totalRevenue', 0)

#         # ==========================================
#         # 🚀 FULL DEBUG PRINT (터미널 확인용)
#         # ==========================================
#         print(f"\n{'='*50}")
#         print(f"   📊 [QUANT DEBUG] Ticker: {ticker_symbol.upper()}")
#         print(f"{'='*50}")
        
#         debug_list = [
#             ("Total Assets (Current)", total_assets),
#             ("Total Assets (Previous)", total_assets_prev),
#             ("Total Equity", total_equity),
#             ("Total Debt", total_debt),
#             ("-" * 30, None),
#             # --- 방금 추가된 부채 및 유동성 지표 ---
#             ("Long Term Debt (Cur)", long_term_debt),
#             ("Long Term Debt (Prev)", long_term_debt_prev),
#             ("Current Assets (Cur)", current_assets),
#             ("Current Assets (Prev)", current_assets_prev),
#             ("Current Liab (Cur)", current_liab),
#             ("Current Liab (Prev)", current_liab_prev),
#             ("-" * 30, None),
#             ("Cash & Equivalents", cash),
#             ("Revenue (Current)", revenue),
#             ("Revenue (Previous)", revenue_prev),
#             ("Gross Profit", gross_profit),
#             ("Op Income (EBIT)", op_income),
#             ("Net Income", net_income),
#             ("Tax Provision", tax_provision),
#             ("Pretax Income", pretax_income),
#             ("-" * 30, None),
#             ("Operating Cash Flow", op_cf),
#             ("CapEx", cap_ex),
#             ("Free Cash Flow", fcf),
#             ("-" * 30, None),
#             ("Market Cap", market_cap),
#             ("PEG Ratio", peg_ratio)
#         ]

#         for label, value in debug_list:
#             if value is None:
#                 print(label)
#                 continue
#             status = "✅ OK" if value != 0 else "❌ MISSING"
#             # 가독성을 위해 큰 숫자는 콤마(,) 표시
#             val_str = f"{value:,.0f}" if isinstance(value, (int, float)) and value != 0 else str(value)
#             print(f"{status.ljust(10)} | {label.ljust(25)}: {val_str}")

#         print(f"{'-'*50}")
#         print(f"💡 Backup Triggered: Assets({'Yes' if pre_backup_assets==0 else 'No'}), "
#               f"NetInc({'Yes' if pre_backup_net_income==0 else 'No'}), "
#               f"Rev({'Yes' if pre_backup_revenue==0 else 'No'})")
#         print(f"📦 DF Status: BS({not bs.empty}), FIN({not fin.empty}), CF({not cf.empty})")
#         print(f"{'='*50}\n")
        
#         if total_assets == 0 or market_cap == 0:
#             return {"error": "재무 데이터가 부족하여 퀀트 평가를 진행할 수 없습니다."}

#         # ==========================================
#         # 1. MOAT SCORE (퀄리티) - 30점
#         # ==========================================
#         gpa = gross_profit / total_assets if total_assets > 0 else 0
#         score_gpa = 5.0 if gpa >= 0.3 else (3.0 if gpa >= 0.2 else 1.0)

#         tax_rate = tax_provision / pretax_income if pretax_income > 0 else 0.2
#         nopat = op_income * (1 - tax_rate)
#         invested_capital = (total_debt + total_equity - cash)
#         roic = nopat / invested_capital if invested_capital > 0 else 0
#         score_roic = 5.0 if roic >= 0.15 else (3.0 if roic >= 0.08 else 1.0)

#         accruals = (net_income - op_cf) / total_assets if total_assets > 0 else 0
#         score_accruals = 5.0 if accruals < 0 else (3.0 if accruals <= 0.05 else 1.0)
        
#         raw_moat_sum = score_gpa + score_roic + score_accruals
#         moat_score = round(raw_moat_sum * (30 / 15), 1)

#         # ==========================================
#         # 🕵️ MOAT SCORE 집중 디버깅 모드
#         # ==========================================
        
#         # 1. GPA (자산대비 매출총이익)
#         print(f"  [GPA]")
#         print(f"    - Gross Profit: {gross_profit:,.0f}")
#         print(f"    - Total Assets: {total_assets:,.0f}")
#         print(f"    => Final GPA: {gpa:.4f} (Target: >=0.3 for 13.4pts)")
#         print(f"    => Assigned Score: {score_gpa} pts")

#         # 2. ROIC (투하자본이익률)
#         print(f"\n  [ROIC]")
#         print(f"    - Tax Rate: {tax_rate:.2%}")
#         print(f"    - NOPAT: {nopat:,.0f}")
#         print(f"    - Invested Capital: {invested_capital:,.0f}")
#         print(f"    => Final ROIC: {roic:.4f} (Target: >=0.15 for 13.3pts)")
#         print(f"    => Assigned Score: {score_roic} pts")

#         # 3. Accruals (발생액 - 회계 투명성)
#         print(f"\n  [Accruals]")
#         print(f"    - Net Income: {net_income:,.0f}")
#         print(f"    - Op CashFlow: {op_cf:,.0f}")
#         print(f"    => Accruals Ratio: {accruals:.4f} (Target: <0 for 13.3pts)")
#         print(f"    => Assigned Score: {score_accruals} pts")

#         print(f"\n🛡️ RAW MOAT SCORE: {raw_moat_sum:.1f} / 15.0")
#         print(f"\n🛡️ TOTAL MOAT SCORE: {moat_score:.1f} / 30.0")
#         print(f"{'-'*60}")

#         # ==========================================
#         # 2. VALUE SCORE (저평가) - 25점
#         # ==========================================
#         # 1. EV/EBIT 계산 (ebit이 없거나 0인 경우 방어)
#         ev = market_cap + total_debt - cash
#         if ebit is not None and ebit != 0:
#             ev_ebit = ev / ebit
#         else:
#             ev_ebit = 9999.0  # 측정이 안 됨을 알리는 임시 플래그 숫자

#         # 2. 스코어링 (측정 불가 시 중간 점수 부여)
#         if ev_ebit == 9999.0:
#             # 데이터가 없어서 측정이 안 되면 '중' 등급인 3.0점 부여
#             score_ev = 3.0 
#         elif 0 < ev_ebit <= 10:
#             score_ev = 5.0
#         elif 10 < ev_ebit <= 20:
#             score_ev = 3.0
#         else:
#             # 적자(음수)이거나 고평가(20배 초과)인 경우 페널티 1.0점
#             score_ev = 1.0

#         score_peg = 5.0 if peg_ratio < 1.0 else (3.0 if peg_ratio <= 1.5 else 1.0)
#         pfcr = market_cap / fcf if fcf > 0 else 999
#         score_pfcr = 5.0 if pfcr < 15 else (3.0 if pfcr <= 25 else 1.0)
        
#         raw_value_score = score_ev + score_peg + score_pfcr
#         value_score = round(raw_value_score * (25 / 15), 1)

#         # ==========================================
#         # 🕵️ VALUE SCORE 집중 디버깅 모드
#         # ==========================================
#         print(f"\n{'-'*20} [VALUE SCORE DETAIL] {'-'*20}")

#         # 1. EV/EBIT 상세
#         print(f"  [EV/EBIT]")
#         print(f"    - MarketCap: {market_cap:,.0f}")
#         print(f"    - TotalDebt: {total_debt:,.0f}")
#         print(f"    - Cash:      {cash:,.0f}")
#         print(f"    - EBIT(Raw): {ebit:,.0f}")
#         print(f"    - Calculated EV: {ev:,.0f}")
#         print(f"    => Final EV/EBIT: {ev_ebit:.2f} (Target: <10 for 10pts)")
#         print(f"    => Assigned Score: {score_ev} pts")

#         # 2. PEG 상세
#         # 상세 출력부 (여기가 1.5로 하드코딩 되어있는지 꼭 확인하세요!)
#         print(f"  [PEG]")
#         print(f"    - PEG Ratio(Raw): {peg_ratio}") 
#         print(f"    => Final PEG: {score_peg:.2f} pts")

#         # 3. PFCR 상세
#         print(f"\n  [PFCR]")
#         print(f"    - MarketCap: {market_cap:,.0f}")
#         print(f"    - FCF(Raw):  {fcf:,.0f}")
#         print(f"    - Op_CF:     {op_cf:,.0f}")
#         print(f"    - CapEx:     {cap_ex:,.0f}")
#         print(f"    => Final PFCR: {pfcr:.2f} (Target: <15 for 10pts)")
#         print(f"    => Assigned Score: {score_pfcr} pts")

#         print(f"\n💎 RAW VALUE SCORE: {raw_value_score} / 15.0")
#         print(f"\n💎 TOTAL VALUE SCORE: {value_score} / 25.0")
#         print(f"{'-'*60}\n")

#         # ==========================================
#         # 3. GROWTH & MOMENTUM - 30점
#         # ==========================================
#         # [3-1] F-Score - 5점 만점
#         f_score = 0
#         if net_income > 0: f_score += 1
#         if op_cf > 0: f_score += 1
#         if (net_income/total_assets if total_assets>0 else 0) > (net_income_prev/total_assets_prev if total_assets_prev>0 else 0): f_score += 1
#         if op_cf > net_income: f_score += 1
#         if (long_term_debt/total_assets if total_assets>0 else 0) < (long_term_debt_prev/total_assets_prev if total_assets_prev>0 else 0): f_score += 1
#         if (current_assets/current_liab if current_liab>0 else 0) > (current_assets_prev/current_liab_prev if current_liab_prev>0 else 0): f_score += 1
#         f_score += 1 # 주식 발행 여부 (간소화)
#         if (gross_profit/revenue if revenue>0 else 0) > (gross_profit_prev/revenue_prev if revenue_prev>0 else 0): f_score += 1
#         if (revenue/total_assets if total_assets>0 else 0) > (revenue_prev/total_assets_prev if total_assets_prev>0 else 0): f_score += 1

#         score_f = 5.0 if f_score >= 7 else (3.0 if f_score >= 4 else 1.0)

#         # [3-2] Asset Turnover Acceleration (자산 회전율 가속도) - 5점 만점
#         # RS(가격 모멘텀)를 대신하여 "병목 돌파"를 잡아냅니다.
#         current_ato = revenue / total_assets if total_assets > 0 else 0
#         prev_ato = revenue_prev / total_assets_prev if total_assets_prev > 0 else 0
#         ato_acceleration = current_ato - prev_ato

#         if ato_acceleration >= 0.05:
#             score_ato = 5.0  # 🔥 보석 발견 (자산 효율성 급증)
#         elif ato_acceleration > 0:
#             score_ato = 3.0  # ✅ 서서히 혈관이 뚫리는 중
#         else:
#             score_ato = 1.0  # ⚠️ 자산이 비효율적으로 묶여있음 (정체)

#         # [3-3] 영업레버리지
#         # 1. 매출 성장률 계산 (분모가 0이면 0.0001 등 아주 작은 수로 대체하거나 0 처리)
#         if revenue_prev != 0:
#             rev_growth = (revenue - revenue_prev) / revenue_prev
#         else:
#             rev_growth = 0  # 이전 매출이 0이면 비교 불능이므로 0 처리

#         # 2. 영업이익 성장률 계산
#         if op_income_prev != 0:
#             op_growth = (op_income - op_income_prev) / op_income_prev
#         else:
#             op_growth = 0  # 이전 이익이 0이면 0 처리

#         # 3. 영업 레버리지 계산 (핵심: 분모인 rev_growth가 0이 아닐 때만 계산)
#         # abs(rev_growth) > 0.0001 처럼 아주 미세한 값이라도 있어야 계산을 진행합니다.
#         if abs(rev_growth) > 0.0001:
#             op_leverage = op_growth / rev_growth
#         else:
#             # 매출 변화가 거의 없을 때(0 포함)는 레버리지 효과가 없으므로 1.0(중립) 처리
#             op_leverage = 1.0

#         # 4. 스코어링 (마이너스 값은 자동으로 1.0점에 배정됨)
#         if op_leverage > 2.0:
#             score_oplev = 5.0
#         elif op_leverage >= 1.0:
#             score_oplev = 3.0
#         else:
#             score_oplev = 1.0  # 마이너스(-) 레버리지나 1.0 미만은 효율 하락으로 판단

#         # [3-4] 모멘텀 총점 계산 (15점 만점 -> 30점 스케일링)
#         # 기(F-Score) + 승(ATO Accel) + 전(Op Leverage) = 15점 만점        
#         raw_momentum_sum = score_f + score_ato + score_oplev
#         momentum_score = round(raw_momentum_sum * (25 / 15), 1)

#         # ==========================================
#         # 🕵️ GROWTH & MOMENTUM 집중 디버깅 모드
#         # ==========================================
#         print(f"\n{'-'*20} [GROWTH & MOMENTUM DETAIL] {'-'*20}")

#         # 1. F-Score 상세 (안전마진 및 턴어라운드)
#         print(f"  [1. Piotroski F-Score]")
#         print(f"    - Net Income > 0: {'✅' if net_income > 0 else '❌'}")
#         print(f"    - Op Cash Flow > 0: {'✅' if op_cf > 0 else '❌'}")
#         print(f"    - ROA Up: {'✅' if (net_income/total_assets if total_assets>0 else 0) > (net_income_prev/total_assets_prev if total_assets_prev>0 else 0) else '❌'}")
#         print(f"    - Accruals (OCF > NI): {'✅' if op_cf > net_income else '❌'}")
#         print(f"    - Leverage Down: {'✅' if (long_term_debt/total_assets if total_assets>0 else 0) < (long_term_debt_prev/total_assets_prev if total_assets_prev>0 else 0) else '❌'}")
#         print(f"    - Liquidity Up: {'✅' if (current_assets/current_liab if current_liab>0 else 0) > (current_assets_prev/current_liab_prev if current_liab_prev>0 else 0) else '❌'}")
#         print(f"    - Margin Up: {'✅' if (gross_profit/revenue if revenue>0 else 0) > (gross_profit_prev/revenue_prev if revenue_prev>0 else 0) else '❌'}")
#         print(f"    - Turnover Up: {'✅' if (revenue/total_assets if total_assets>0 else 0) > (revenue_prev/total_assets_prev if total_assets_prev>0 else 0) else '❌'}")
#         print(f"    => Final F-Score: {f_score} / 9")
#         print(f"    => Assigned Score: {score_f} pts")

#         # 2. Asset Turnover Accel 상세 (병목 돌파 신호 - 원천 데이터 포함)
#         print(f"\n  [2. Asset Turnover Acceleration]")
#         print(f"    - [Current] Revenue: {revenue:,.0f} / Assets: {total_assets:,.0f}")
#         print(f"    - [Prev   ] Revenue: {revenue_prev:,.0f} / Assets: {total_assets_prev:,.0f}")
#         print(f"    - Current ATO (Rev/Assets): {current_ato:.4f}")
#         print(f"    - Prev ATO (Rev/Assets): {prev_ato:.4f}")
#         print(f"    - Acceleration (Diff): {ato_acceleration:.4f} (Target: >0.05)")        
#         print(f"    => Asset Turnover Acceleration: {score_ato} pts")

#         # 3. Operating Leverage 상세 (이익 폭발력)
#         print(f"\n  [3. Operating Leverage]")
#         print(f"    - Revenue Growth: {rev_growth:.2%}")
#         print(f"    - op_income: {op_income:.2%}")
#         print(f"    - op_income_prev: {op_income_prev:.2%}")
#         print(f"    - Op Income Growth: {op_growth:.2%}")
#         print(f"    - Leverage Ratio: {op_leverage:.2f} (Target: >2.0)")
#         print(f"    => Assigned Score: {score_oplev} pts")

#         print(f"\n🚀 RAW MOMENTUM SCORE: {raw_momentum_sum} / 15.0")
#         print(f"\n🚀 TOTAL MOMENTUM SCORE: {momentum_score} / 25.0")
#         print(f"{'-'*60}\n")

#         # [최종 합산]
#         technical_data = get_technical_timing(ticker_symbol)
#         technical_score = technical_data.get("scores", {}).get("total", 0)

#         total_score = round(
#             moat_score + value_score + momentum_score + technical_score,
#             1
#         )

#         return {
#             "ticker": ticker_symbol,
#             "totalScore": total_score,
#             "moatScore": round(moat_score, 1),
#             "valueScore": round(value_score, 1),
#             "momentumScore": round(momentum_score, 1),
#             "technicalScore": technical_score,
#             "technical": technical_data,
#             "metrics": {
#                 "gpa": round(gpa, 4),
#                 "roic": round(roic, 4),
#                 "accruals": round(accruals, 4),
#                 "evEbit": round(ev_ebit, 2),
#                 "peg": round(peg_ratio, 2),
#                 "pfcr": round(pfcr, 2),
#                 "fScore": f_score,
#                 "atoacceleration": round(ato_acceleration, 4),
#                 "opLeverage": round(op_leverage, 2),                
#                 # # "rs": round(rs, 4),
#                 # "stockReturn6m": round(stock_ret, 4),
#                 # "spyReturn6m": round(spy_ret, 4)
#             }
#         }
#     except Exception as e:
#         return {"error": str(e)}


# def get_technical_timing(ticker_symbol, market_symbol="^GSPC"):
#     try:
#         ticker = ticker_symbol.upper()

#         stock = yf.Ticker(ticker)
#         market = yf.Ticker(market_symbol)

#         # 🔹 2년치 확보 (안정성)
#         df = stock.history(period="2y", auto_adjust=True)
#         mkt = market.history(period="2y", auto_adjust=True)

#         if df.empty or mkt.empty:
#             return {"error": "Yahoo 데이터 수신 실패"}

#         close = df['Close'].dropna()
#         market_close = mkt['Close'].dropna()

#         # 🔹 최소 120일 이상 필요
#         if len(close) < 120 or len(market_close) < 120:
#             return {"error": "히스토리 데이터 부족"}

#         # 🔹 공통 길이 맞추기
#         min_len = min(len(close), len(market_close))
#         close = close.tail(min_len)
#         market_close = market_close.tail(min_len)

#         returns = close.pct_change()

#         # =====================================
#         # 1️⃣ Relative 12M Momentum (8점)
#         # =====================================
#         lookback = min(252, min_len)

#         ret_stock = close.iloc[-1] / close.iloc[-lookback] - 1
#         ret_market = market_close.iloc[-1] / market_close.iloc[-lookback] - 1
#         rel_momentum = ret_stock - ret_market

#         if rel_momentum >= 0.20:
#             score_mom = 8
#         elif rel_momentum >= 0.05:
#             score_mom = 5
#         elif rel_momentum > 0:
#             score_mom = 3
#         else:
#             score_mom = 1

#         # =====================================
#         # 2️⃣ 52W High Distance (5점)
#         # =====================================
#         high_52w = close.rolling(252).max().iloc[-1]
#         distance = (close.iloc[-1] - high_52w) / high_52w

#         if distance >= -0.05:
#             score_high = 5
#         elif distance >= -0.15:
#             score_high = 3
#         else:
#             score_high = 1

#         # =====================================
#         # 3️⃣ Trend Stability (90일 R²) (4점)
#         # =====================================
#         trend_days = min(90, min_len)

#         y = close.tail(trend_days).values.reshape(-1, 1)
#         X = np.arange(trend_days).reshape(-1, 1)

#         model = LinearRegression()
#         model.fit(X, y)

#         r2 = model.score(X, y)
#         slope = model.coef_[0][0]

#         if slope > 0 and r2 >= 0.7:
#             score_trend = 4
#         elif slope > 0 and r2 >= 0.4:
#             score_trend = 2
#         else:
#             score_trend = 1

#         # =====================================
#         # 4️⃣ Volatility Compression (3점)
#         # =====================================
#         vol_short = returns.rolling(20).std().iloc[-1]
#         vol_long = returns.rolling(120).std().iloc[-1]

#         vol_ratio = vol_short / vol_long if vol_long and vol_long > 0 else 1.0

#         if vol_ratio <= 0.7:
#             score_vol = 3
#         elif vol_ratio <= 1.0:
#             score_vol = 2
#         else:
#             score_vol = 1

#         # =====================================
#         # TOTAL
#         # =====================================
#         total_score = score_mom + score_high + score_trend + score_vol

#         return {
#             "relativeMomentumPct": round(rel_momentum * 100, 2),
#             "distanceFromHighPct": round(distance * 100, 2),
#             "trendR2": round(r2, 2),
#             "volCompression": round(vol_ratio, 2),
#             "scores": {
#                 "relativeMomentum": score_mom,
#                 "highDistance": score_high,
#                 "trendStability": score_trend,
#                 "volCompression": score_vol,
#                 "total": total_score
#             }
#         }

#     except Exception as e:
#         print(f"❌ TECH ERROR: {str(e)}")
#         traceback.print_exc()
#         return {"error": str(e)}

# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=8080)        

# def get_financials_data(ticker_symbol, period='annual'):
#     try:
#         stock = yf.Ticker(ticker_symbol.upper())
        
#         # 1. 데이터 확보 (연간/분기 선택)
#         if period == 'quarterly':
#             fn, bs, cf = stock.quarterly_financials, stock.quarterly_balance_sheet, stock.quarterly_cashflow
#         else:
#             fn, bs, cf = stock.financials, stock.balance_sheet, stock.cashflow

#         # 데이터 부재 시 백업 로직
#         if fn.empty: fn = stock.quarterly_financials if not stock.quarterly_financials.empty else pd.DataFrame()
#         if bs.empty: bs = stock.quarterly_balance_sheet if not stock.quarterly_balance_sheet.empty else pd.DataFrame()
#         if cf.empty: cf = stock.quarterly_cashflow if not stock.quarterly_cashflow.empty else pd.DataFrame()

#         if fn.empty or bs.empty:
#             return {"error": "재무제표 데이터를 가져올 수 없습니다."}

#         # 2. 정렬: 과거 -> 최신 (좌->우 차트 및 테이블 순서)
#         fn = fn.sort_index(axis=1, ascending=True)
#         bs = bs.sort_index(axis=1, ascending=True)
#         cf = cf.sort_index(axis=1, ascending=True)
        
#         years = [col.strftime('%Y' if period == 'annual' else '%Y-%m') for col in fn.columns]

#         # ---------------------------------------------------------
#         # [NEW] 테이블용 데이터 포맷팅 함수 (DataFrame -> JSON Dict)
#         # ---------------------------------------------------------
#         def format_for_table(df):
#             formatted_data = []
#             for label in df.index:
#                 row = {"label": str(label)}
#                 for i, year_str in enumerate(years):
#                     val = df.iloc[df.index.get_loc(label), i]
#                     # NaN, Inf 처리 및 실수 변환
#                     if pd.isna(val) or np.isinf(val):
#                         row[year_str] = 0
#                     else:
#                         row[year_str] = float(val)
#                 formatted_data.append(row)
#             return {"years": years, "data": formatted_data}

#         # ---------------------------------------------------------
#         # [기존] 지표 계산 로직 (계산부 유지)
#         # ---------------------------------------------------------
#         def get_val(df, keywords):
#             if df.empty: return [0.0] * len(years)
#             df_index_clean = [str(idx).lower().replace(" ", "").replace("_", "") for idx in df.index]
#             for k in keywords:
#                 clean_k = k.lower().replace(" ", "").replace("_", "")
#                 if clean_k in df_index_clean:
#                     idx = df_index_clean.index(clean_k)
#                     return df.iloc[idx].fillna(0).replace([np.inf, -np.inf], 0).tolist()
#             return [0.0] * len(years)

#         # 핵심 지표용 데이터 추출
#         revenue = get_val(fn, ['TotalRevenue', 'Revenue'])
#         op_income = get_val(fn, ['OperatingIncome', 'EBIT'])
#         net_income = get_val(fn, ['NetIncome'])
#         ebitda = get_val(fn, ['EBITDA'])
#         fcf = get_val(cf, ['FreeCashFlow', 'OperatingCashFlow'])
#         total_debt = get_val(bs, ['TotalDebt', 'LongTermDebt'])
#         cash = get_val(bs, ['CashAndCashEquivalents'])
#         equity = get_val(bs, ['StockholdersEquity'])
        
#         def safe_div(a, b): return a / b if b and b != 0 else 0
#         market_cap = stock.info.get('marketCap', 0)

#         metrics = {"roic": [], "ruleOf40": [], "opLeverage": [], "netDebtEbitda": [], "fcfYield": []}
#         for i in range(len(years)):
#             # ROIC
#             nopat = op_income[i] * 0.79 # 가상 세율 21%
#             ic = (equity[i] + total_debt[i] - cash[i])
#             metrics["roic"].append(round(safe_div(nopat, ic) * 100, 2))
            
#             # Rule of 40
#             rev_growth = ((revenue[i] - revenue[i-1]) / abs(revenue[i-1])) * 100 if i > 0 and revenue[i-1] != 0 else 0
#             op_margin = safe_div(op_income[i], revenue[i]) * 100
#             metrics["ruleOf40"].append(round(rev_growth + op_margin, 2))

#             # Op Leverage
#             op_growth = ((op_income[i] - op_income[i-1]) / abs(op_income[i-1])) * 100 if i > 0 and op_income[i-1] != 0 else 0
#             metrics["opLeverage"].append(round(safe_div(op_growth, rev_growth), 2) if rev_growth != 0 else 0)

#             # Net Debt / EBITDA
#             metrics["netDebtEbitda"].append(round(safe_div(total_debt[i] - cash[i], ebitda[i]), 2))

#             # FCF Yield
#             metrics["fcfYield"].append(round(safe_div(fcf[i], market_cap) * 100, 2))

#         # ---------------------------------------------------------
#         # [RETURN] 모든 데이터를 포함하여 반환
#         # ---------------------------------------------------------
#         return {
#             "ticker": ticker_symbol,
#             "years": years,
#             "metrics": metrics,
#             "raw": {
#                 "revenue": revenue,
#                 "opIncome": op_income,
#                 "netIncome": net_income,
#                 "fcf": fcf,
#                 "netDebt": [d - c for d, c in zip(total_debt, cash)]
#             },
#             # 프론트엔드 테이블에서 사용하는 핵심 필드 추가
#             "incomeStatement": format_for_table(fn),
#             "balanceSheet": format_for_table(bs),
#             "cashFlow": format_for_table(cf)
#         }

#     except Exception as e:
#         print(f"Error: {str(e)}")
#         return {"error": f"백엔드 계산 오류: {str(e)}"}







#########################################################
# import yfinance as yf

# # 섹터 매핑 사전
# SECTOR_MAP = {
#     "Technology": "it",
#     "Financial Services": "financials",
#     "Healthcare": "healthcare",
#     "Consumer Cyclical": "discretionary",
#     "Communication Services": "comm",
#     "Industrials": "industrials",
#     "Energy": "energy",
#     "Consumer Defensive": "staples",
#     "Real Estate": "realestate",
#     "Utilities": "utilities",
#     "Basic Materials": "materials"
# }

# def get_stock_realtime_data(ticker):
#     try:
#         stock = yf.Ticker(ticker)
#         info = stock.info
        
#         # [수정] 데이터가 아예 없는 경우만 None 리턴
#         if not info or not info.get('longName'):
#             return None

#         # [수정] 가격 데이터: or 0을 붙여서 절대 None이 되지 않게 함
#         current_price = info.get('currentPrice') or info.get('regularMarketPrice') or 0
#         prev_close = info.get('previousClose') or current_price
#         change = current_price - prev_close
#         pct_change = (change / prev_close * 100) if prev_close != 0 else 0

#         # 섹터 매핑
#         yf_sector_name = info.get('sector', '')
#         mapped_id = SECTOR_MAP.get(yf_sector_name)

#         # [핵심] 여기서 "데이터가 부족합니다"라며 return 하는 조건문을 모두 삭제했습니다.
#         return {
#             "name": info.get('longName', ticker),
#             "price": round(float(current_price), 2),
#             "change": round(float(change), 2),
#             "changesPercentage": round(float(pct_change), 2),
#             "isUp": change >= 0,
#             "eps": info.get('trailingEps') or 0,
#             "per": info.get('trailingPE') or info.get('forwardPE') or 0,
#             "forwardPer": info.get('forwardPE') or 0,
#             "roi": info.get('returnOnAssets') or 0,
#             "roic": info.get('returnOnCapital') or info.get('returnOnEquity') or 0,
#             "industry": info.get('industry', 'N/A'),
#             "exchange": info.get('exchange', 'N/A'),
#             "description": info.get('longBusinessSummary', ''),
#             "yf_mapped_sector": mapped_id
#         }        
#     except Exception as e:
#         print(f"🚨 API_SERVICE Error: {e}")
#         return None
