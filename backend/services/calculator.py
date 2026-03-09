"""
/home/gguakim33/stock-app/stock-app/backend/services/calculator.py
퀀트 레이팅 및 각 지표 계산 로직
"""
import pandas as pd
import numpy as np
import yfinance as yf
from sklearn.linear_model import LinearRegression
import traceback
from scipy import stats

class FinancialLogic:
    @staticmethod
    def safe_div(a, b, default=0.0):
        try:
            val_a = float(a if a is not None else 0)
            val_b = float(b if b is not None else 0)
            return val_a / val_b if val_b != 0 else default
        except: return default

    @staticmethod
    def safe_val(v, default=0.0):
        try:
            if v is None or pd.isna(v): return default
            # 리스트나 시리즈로 들어올 경우 마지막 값 추출
            if isinstance(v, (list, np.ndarray, pd.Series)):
                return float(v[-1]) if len(v) > 0 else default
            return float(v)
        except: return default

    @staticmethod
    def calc_gpa(gross_profit, total_assets):
        return FinancialLogic.safe_div(gross_profit, total_assets)

    @staticmethod
    def calc_tax_rate(tax, pretax):
        r = FinancialLogic.safe_div(tax, pretax, 0.2)
        return max(0.0, min(r, 0.4))

    @staticmethod
    def calc_nopat(op_income, tax_rate):
        return FinancialLogic.safe_val(op_income) * (1 - tax_rate)

    @staticmethod
    def calc_invested_capital(total_debt, equity, cash):
        ic = FinancialLogic.safe_val(total_debt) + FinancialLogic.safe_val(equity) - FinancialLogic.safe_val(cash)
        return max(ic, 1.0)

    @staticmethod
    def calc_roic(nopat, ic):
        return FinancialLogic.safe_div(nopat, ic)

    @staticmethod
    def calc_accruals(net_income, op_cf, assets):
        return FinancialLogic.safe_div(FinancialLogic.safe_val(net_income) - FinancialLogic.safe_val(op_cf), assets)

    @staticmethod
    def calc_growth_rate(cur, prev):
        p = FinancialLogic.safe_val(prev)
        if p == 0: return 0.0
        return ((FinancialLogic.safe_val(cur) - p) / abs(p)) * 100

    @staticmethod
    def calc_peg(market_cap, net_income, growth_rate):
        per = FinancialLogic.safe_div(market_cap, net_income, 999.0)
        if growth_rate <= 0: return 5.0
        return FinancialLogic.safe_div(per, growth_rate, 5.0)

    @staticmethod
    def calc_ev(market_cap, debt, cash):
        return FinancialLogic.safe_val(market_cap) + FinancialLogic.safe_val(debt) - FinancialLogic.safe_val(cash)

    @staticmethod
    def calc_ev_ebit(ev, ebit):
        val_ebit = FinancialLogic.safe_val(ebit)
        if val_ebit <= 0: return 999.0
        return FinancialLogic.safe_div(ev, val_ebit)

    @staticmethod
    def calc_pfcr(market_cap, fcf):
        val_fcf = FinancialLogic.safe_val(fcf)
        if val_fcf <= 0: return 999.0
        return FinancialLogic.safe_div(market_cap, val_fcf)

    @staticmethod
    def calc_ato(revenue, assets):
        return FinancialLogic.safe_div(revenue, assets)

    @staticmethod
    def calc_op_leverage(rev, rev_prev, op, op_prev):
        rev_growth = FinancialLogic.safe_div(FinancialLogic.safe_val(rev) - FinancialLogic.safe_val(rev_prev), rev_prev)
        op_growth = FinancialLogic.safe_div(FinancialLogic.safe_val(op) - FinancialLogic.safe_val(op_prev), abs(FinancialLogic.safe_val(op_prev)))
        if abs(rev_growth) < 0.0001: return 1.0
        return FinancialLogic.safe_div(op_growth, rev_growth, 1.0)

    @staticmethod
    def calc_f_score(d):
        score = 0
        L = FinancialLogic
        try:
            ni, ni_p = L.safe_val(d.get("net_income")), L.safe_val(d.get("net_income_prev"))
            ocf = L.safe_val(d.get("op_cf"))
            ta, ta_p = L.safe_val(d.get("total_assets"), 1), L.safe_val(d.get("total_assets_prev"), 1)
            if ni > 0: score += 1
            if ocf > 0: score += 1
            if L.safe_div(ni, ta) > L.safe_div(ni_p, ta_p): score += 1
            if ocf > ni: score += 1
            ltd, ltd_p = L.safe_val(d.get("long_term_debt")), L.safe_val(d.get("long_term_debt_prev"))
            if L.safe_div(ltd, ta) < L.safe_div(ltd_p, ta_p): score += 1
            ca, cl = L.safe_val(d.get("current_assets")), L.safe_val(d.get("current_liab"))
            ca_p, cl_p = L.safe_val(d.get("current_assets_prev")), L.safe_val(d.get("current_liab_prev"))
            if L.safe_div(ca, cl) > L.safe_div(ca_p, cl_p): score += 1
            score += 1 
            gp, gp_p = L.safe_val(d.get("gross_profit")), L.safe_val(d.get("gross_profit_prev"))
            rev, rev_p = L.safe_val(d.get("revenue")), L.safe_val(d.get("revenue_prev"))
            if L.safe_div(gp, rev) > L.safe_div(gp_p, rev_p): score += 1
            if L.safe_div(rev, ta) > L.safe_div(rev_p, ta_p): score += 1
        except: pass
        return score

def get_quant_rating(input_data):
    L = FinancialLogic
    d = input_data if isinstance(input_data, dict) else {}
    ticker = str(d.get("ticker", "UNKNOWN")).upper()
    
    # [수정] raw_sum을 포함하여 모든 점수 관련 키를 사전에 100% 정의
    res = {
        "ticker": ticker,
        "basics": {"growth_rate_pct": 0, "fcf": 0, "peg_ratio": 5, "marketCap": 0},
        "moat": {
            "gpa": 0, "roic": 0, "accruals": 0, 
            "score_gpa": 0, "score_roic": 0, "score_accruals": 0, 
            "raw_sum": 0, "score": 0
        },
        "value": {
            "ev_ebit": 999, "pfcr": 999, 
            "score_ev": 0, "score_peg": 0, "score_pfcr": 0, 
            "raw_sum": 0, "score": 0
        },
        "momentum": {
            "f_score": 0, "ato_acceleration": 0, "op_leverage": 1, 
            "score_f": 0, "score_ato": 0, "score_oplev": 0, 
            "raw_sum": 0, "score": 0
        },
        "technical": {"scores": {"total": 0}},
        "scores": {"total": 0}
    }

    try:
        # 기술 점수 계산 및 즉시 할당
        res["technical"] = get_technical_timing(ticker)
        
        growth = L.calc_growth_rate(d.get("net_income"), d.get("net_income_prev"))
        fcf = L.safe_val(d.get("op_cf")) - abs(L.safe_val(d.get("cap_ex")))
        res["basics"].update({"growth_rate_pct": growth, "fcf": fcf, "marketCap": L.safe_val(d.get("market_cap"))})
###################################
        # 1. MOAT (35점)
        tax = L.calc_tax_rate(d.get("tax_provision"), d.get("pretax_income"))
        roic = L.calc_roic(L.calc_nopat(d.get("op_income"), tax), L.calc_invested_capital(d.get("total_debt"), d.get("total_equity"), d.get("cash")))
        gpa = L.calc_gpa(d.get("gross_profit"), d.get("total_assets", 1))
        accruals = L.calc_accruals(d.get("net_income"), d.get("op_cf"), d.get("total_assets", 1))
        
        res["moat"]["gpa"] = gpa
        res["moat"]["roic"] = roic
        res["moat"]["accruals"] = accruals
        # GPA: 45점 만점
        res["moat"]["score_gpa"] = 45 if gpa >= 0.4 else 35 if gpa >= 0.3 else 25 if gpa >= 0.2 else 15 if gpa >= 0.1 else 0
        # ROIC: 35점 만점
        res["moat"]["score_roic"] = 35 if roic >= 0.2 else 30 if roic >= 0.15 else 20 if roic >= 0.12 else 10 if roic >= 0.08 else 0
        # Accruals: 20점 만점
        res["moat"]["score_accruals"] = 20 if accruals <= -0.05 else 15 if accruals <= 0 else 10 if accruals <= 0.05 else 5 if accruals <= 0.1 else 0
        
        res["moat"]["raw_sum"] = res["moat"]["score_gpa"] + res["moat"]["score_roic"] + res["moat"]["score_accruals"]
        res["moat"]["score"] = (res["moat"]["raw_sum"] / 100) * 35

###################################
        # 2. VALUE (25점)
        peg = L.calc_peg(d.get("market_cap"), d.get("net_income"), growth)
        ev_ebit = L.calc_ev_ebit(L.calc_ev(d.get("market_cap"), d.get("total_debt"), d.get("cash")), d.get("ebit"))
        pfcr = L.calc_pfcr(d.get("market_cap"), fcf)
        
        res["value"]["ev_ebit"] = ev_ebit
        res["value"]["pfcr"] = pfcr
        res["basics"]["peg_ratio"] = peg
        # EV/EBIT: 50점 만점
        res["value"]["score_ev"] = 50 if ev_ebit <= 10 else 40 if ev_ebit <= 15 else 30 if ev_ebit <= 20 else 15 if ev_ebit <= 25 else 0
        # PEG: 30점 만점
        res["value"]["score_peg"] = 30 if peg <= 0.8 else 25 if peg <= 1.2 else 15 if peg <= 1.8 else 5 if peg <= 2.5 else 0
        # PFCR: 20점 만점
        res["value"]["score_pfcr"] = 20 if pfcr <= 10 else 15 if pfcr <= 15 else 10 if pfcr <= 20 else 5 if pfcr <= 30 else 0
        
        res["value"]["raw_sum"] = res["value"]["score_ev"] + res["value"]["score_peg"] + res["value"]["score_pfcr"]
        res["value"]["score"] = (res["value"]["raw_sum"] / 100) * 25

###################################
        # 3. MOMENTUM (25점)
        f_score = L.calc_f_score(d)
        curr_rev = L.safe_val(d.get("revenue"))
        curr_assets = L.safe_val(d.get("total_assets"), 1) # 분모는 최소 1
        curr_ato = L.calc_ato(curr_rev, curr_assets)

        prev_rev = L.safe_val(d.get("revenue_prev"))
        prev_assets = L.safe_val(d.get("total_assets_prev"), 1)
        prev_ato = L.calc_ato(prev_rev, prev_assets)

        ato_improvement = curr_ato - prev_ato
        res["momentum"]["ato_improvement"] = ato_improvement
        res["momentum"]["curr_ato"] = curr_ato
        
        res["momentum"]["f_score"] = f_score
        res["momentum"]["op_leverage"] = L.calc_op_leverage(d.get("revenue"), d.get("revenue_prev"), d.get("op_income"), d.get("op_income_prev"))
        # F-Score: 55점 만점
        res["momentum"]["score_f"] = 55 if f_score >= 9 else 45 if f_score >= 7 else 30 if f_score >= 5 else 15 if f_score >= 3 else 0
        # ATO: 25점 만점
        res["momentum"]["score_ato"] = (
            25 if ato_improvement >= 0.05 else 
            20 if ato_improvement >= 0.02 else 
            15 if ato_improvement >= 0.00 else 
            5  if ato_improvement >= -0.02 else 0
        )
        # OpLev: 20점 만점
        op_lev = res["momentum"]["op_leverage"]
        res["momentum"]["score_oplev"] = 20 if op_lev >= 0.25 else 15 if op_lev >= 0.15 else 10 if op_lev >= 0.05 else 5 if op_lev >= 0 else 0
        
        res["momentum"]["raw_sum"] = res["momentum"]["score_f"] + res["momentum"]["score_ato"] + res["momentum"]["score_oplev"]
        res["momentum"]["score"] = (res["momentum"]["raw_sum"] / 100) * 25

        tech_total = res["technical"]["scores"].get("total", 0)

        # 6. 최종 합산 (에러 원천 차단: res 내부 값만 사용)
        res["scores"]["total"] = (
            res["moat"]["score"] + 
            res["value"]["score"] + 
            res["momentum"]["score"] + 
        # Technical 점수는 get_technical_timing 내부에서 이미 100점 만점 기준으로 산출되어 넘어오므로 15% 적용            
            (tech_total * 0.15)
        )
        
        return res
    except Exception as e:
        traceback.print_exc()
        res["error"] = str(e)
        return res

def calculate_quant_scores(input_data):
    res = get_quant_rating(input_data)
    if "error" in res and len(res) == 1: return res
    try:
        return {
            "ticker": res["ticker"],
            "totalScore": round(res["scores"]["total"], 2),
            "moatScore": round(res['moat']['score'], 2),
            "valueScore": round(res['value']['score'], 2),
            "momentumScore": round(res['momentum']['score'], 2),
            "technicalScore": round(res['technical']['scores']['total'], 2),
            "technical": res['technical'],
            "metrics": {
                "gpa": round(res['moat']['gpa'], 4),
                "roic": round(res['moat']['roic'], 4),
                "accruals": round(res['moat']['accruals'], 4),
                "evEbit": round(res['value']['ev_ebit'], 2),
                "peg": round(res['basics']['peg_ratio'], 2),
                "pfcr": round(res['value']['pfcr'], 2),
                "fScore": res['momentum']['f_score'],
                "atoacceleration": round(res['momentum']['ato_acceleration'], 4),
                "opLeverage": round(res['momentum']['op_leverage'], 2)
            }
        }
    except Exception as e:
        return {"error": f"Format Error: {str(e)}"}

def get_technical_timing(ticker_symbol, market_symbol="^GSPC"):
    rel_mom, pos_52, trend_r2, ann_vol = 0, 0, 0, 0
    s_rel, s_pos, s_trend, s_vol = 0, 0, 0, 0
    try:
        ticker = str(ticker_symbol).upper()
        stock = yf.Ticker(ticker)
        df = stock.history(period="2y", auto_adjust=True)
        mkt = yf.Ticker(market_symbol).history(period="2y", auto_adjust=True)
        if df.empty or mkt.empty: return {"scores": {"total": 0}}
        
        close = df['Close'].dropna()
        returns = close.pct_change()

        # 1. Relative Momentum (45)
        ret_s = (close.iloc[-1] / close.iloc[-252] - 1) if len(close) > 252 else 0
        m_close = mkt['Close'].dropna()
        ret_m = (m_close.iloc[-1] / m_close.iloc[-252] - 1) if len(m_close) > 252 else 0
        rel_mom = ret_s - ret_m
        s_rel = 45 if rel_mom >= 0.3 else 35 if rel_mom >= 0.2 else 25 if rel_mom >= 0.1 else 10 if rel_mom >= 0 else 0

        # 2. 52W Position (25)
        high_52 = close.tail(252).max()
        pos_52 = close.iloc[-1] / high_52 if high_52 > 0 else 0
        # [추가] 실제 이미지에 표시할 "Distance" (예: 0.9927 - 1 = -0.0073)
        dist_52 = pos_52 - 1.0
        s_pos = 25 if pos_52 >= 0.95 else 20 if pos_52 >= 0.85 else 15 if pos_52 >= 0.7 else 5 if pos_52 >= 0.55 else 0

        # 3. Trend Stability ($R^2$ 90D) - 변수 초기화 미리 수행
        y_data = close.tail(90).values
        if len(y_data) >= 90:
            x_data = np.arange(len(y_data))
            # scipy.stats가 정상 임포트되었다면 여기서 연산 수행
            slope, intercept, r_value, p_value, std_err = stats.linregress(x_data, y_data)
            trend_r2 = r_value**2 
        else:
            trend_r2 = 0

        # 4. Volatility (10) - Annualized
        ann_vol = returns.tail(252).std() * np.sqrt(252)
        s_vol = 10 if ann_vol <= 0.2 else 8 if ann_vol <= 0.3 else 5 if ann_vol <= 0.4 else 2 if ann_vol <= 0.6 else 0

        return {
            "relativeMomentumPct": round(rel_mom * 100, 2),
            "position52W": round(pos_52 * 100, 2),
            "dist52W": round(dist_52 * 100, 2),
            "trendR2": round(float(trend_r2), 4),
            "annualVol": round(ann_vol * 100, 2),
            "scores": {"total": s_rel + s_pos + s_trend + s_vol}
        }
    except Exception as e:
        # 실제 어떤 에러인지 프린트해서 확인해보세요
        print(f"Error in get_technical_timing: {e}")
        return {"scores": {"total": 0}, "error": str(e)}

def calculate_financial_metrics(years, revenue, op_income, ebitda, net_income, fcf, total_debt, cash, equity, market_cap, tax_provision, pretax_income, period='annual'):
    L = FinancialLogic()
    try:
        rev_arr, op_arr, m_cap_arr = np.nan_to_num(np.array(revenue, dtype=float)), np.nan_to_num(np.array(op_income, dtype=float)), np.nan_to_num(np.array(market_cap, dtype=float))
        growth_rates = [0.0]
        for i in range(1, len(rev_arr)):
            prev, curr = rev_arr[i-1], rev_arr[i]
            growth_rates.append(((curr - prev) / abs(prev) if prev != 0 else 0) * 100)
        op_margins = [(o / r * 100 if r != 0 else 0) for r, o in zip(rev_arr, op_arr)]
        rule_of_40 = [round(g + m, 2) for g, m in zip(growth_rates, op_margins)]
        tax_rates = [L.calc_tax_rate(t, p) for t, p in zip(tax_provision, pretax_income)]
        nopat = [L.calc_nopat(o, r) for o, r in zip(op_income, tax_rates)]
        ic = [L.calc_invested_capital(d, e, c) for d, e, c in zip(total_debt, equity, cash)]
        roic_arr = [L.calc_roic(n, i) for n, i in zip(nopat, ic)]
        return {
            "roic": (np.array(roic_arr) * 100).round(2).tolist(),
            "fcfYield": (np.nan_to_num(np.array(fcf) / np.where(m_cap_arr == 0, 1, m_cap_arr)) * 100).round(2).tolist(),
            "ruleOf40": rule_of_40, 
            "netDebt": (np.nan_to_num(np.array(total_debt)) - np.nan_to_num(np.array(cash))).tolist(),
            "opMargin": [round(m, 2) for m in op_margins]
        }
    except Exception as e:
        return {"roic": [], "fcfYield": [], "ruleOf40": [], "netDebt": [], "opMargin": []}