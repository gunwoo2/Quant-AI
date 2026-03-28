"""
batch/batch_cross_asset.py — Cross-Asset Intelligence (AI Module #1)
====================================================================
글로벌 15개 자산 시그널 → Layer 3 Section C 보강.

개선점: Z-Score 정규화, Sigmoid 변환, 주식-채권 상관관계 추적,
       데이터 품질 등급, 벌크 수집

스케줄: Step 1.5 (가격 수집 직후) | 소요: ~5-10초 | 비용: $0
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import patch_numpy_adapter
except ImportError:
    pass

import math
import yfinance as yf
import numpy as np
import pandas as pd
from datetime import date, timedelta
from db_pool import get_cursor

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 설정
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ASSETS = {
    "TLT": "미국 장기국채 20Y+",   "SHY": "미국 단기국채 1-3Y",
    "HYG": "하이일드 회사채",       "LQD": "투자등급 회사채",
    "GLD": "금",                   "USO": "원유",
    "CPER": "구리",                "UUP": "달러인덱스",
    "EEM": "이머징마켓",            "FXI": "중국",
    "EWJ": "일본",                 "QQQ": "나스닥100",
    "IWM": "러셀2000 소형주",
}

MOM_WINDOW = 20
ZSCORE_WINDOW = 60
LOOKBACK_DAYS = 120


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 테이블 생성
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _ensure_table():
    with get_cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS cross_asset_daily (
                id                      SERIAL PRIMARY KEY,
                calc_date               DATE NOT NULL UNIQUE,
                tlt_close NUMERIC(10,2), shy_close NUMERIC(10,2),
                hyg_close NUMERIC(10,2), lqd_close NUMERIC(10,2),
                gld_close NUMERIC(10,2), uso_close NUMERIC(10,2),
                cper_close NUMERIC(10,2), uup_close NUMERIC(10,2),
                eem_close NUMERIC(10,2), fxi_close NUMERIC(10,2),
                ewj_close NUMERIC(10,2), qqq_close NUMERIC(10,2),
                iwm_close NUMERIC(10,2), spy_close NUMERIC(10,2),
                risk_appetite_idx NUMERIC(8,4), spread_momentum NUMERIC(8,4),
                safe_haven_momentum NUMERIC(8,4), dollar_momentum NUMERIC(8,4),
                global_growth_momentum NUMERIC(8,4), small_large_ratio NUMERIC(8,4),
                copper_gold_ratio NUMERIC(8,4), hy_spread_proxy NUMERIC(8,4),
                risk_appetite_zscore NUMERIC(6,3), spread_zscore NUMERIC(6,3),
                safe_haven_zscore NUMERIC(6,3), dollar_zscore NUMERIC(6,3),
                global_growth_zscore NUMERIC(6,3), breadth_zscore NUMERIC(6,3),
                stock_bond_corr_20d NUMERIC(6,4),
                risk_appetite_score NUMERIC(4,2), rate_spread_score NUMERIC(4,2),
                safe_haven_score NUMERIC(4,2), dollar_score NUMERIC(4,2),
                global_growth_score NUMERIC(4,2), breadth_score NUMERIC(4,2),
                copper_gold_score NUMERIC(4,2), hy_spread_score NUMERIC(4,2),
                cross_asset_total NUMERIC(5,2),
                data_quality VARCHAR(10) DEFAULT 'FULL',
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_cross_asset_date ON cross_asset_daily(calc_date DESC)")
    print("[CROSS-ASSET] ✅ 테이블 확인")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 데이터 수집
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _fetch_prices() -> pd.DataFrame:
    tickers = list(ASSETS.keys()) + ["SPY"]
    end = date.today()
    start = end - timedelta(days=LOOKBACK_DAYS)
    print(f"[CROSS-ASSET] 📡 {len(tickers)}개 자산 수집 ({start} ~ {end})...")
    try:
        df = yf.download(tickers, start=str(start), end=str(end + timedelta(days=1)),
                         interval="1d", progress=False, threads=True)
        if isinstance(df.columns, pd.MultiIndex):
            closes = df["Close"] if "Close" in df.columns.get_level_values(0) else df["Adj Close"]
        else:
            closes = df
        if hasattr(closes.columns, 'droplevel') and closes.columns.nlevels > 1:
            try:
                closes.columns = closes.columns.droplevel(1)
            except:
                pass
        closes = closes.dropna(how="all")
        print(f"[CROSS-ASSET] ✅ {len(closes)}일 × {len(closes.columns)}자산 수집")
        return closes
    except Exception as e:
        print(f"[CROSS-ASSET] ❌ 수집 실패: {e}")
        return pd.DataFrame()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 유틸리티
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _safe_pct(series, window=MOM_WINDOW):
    if series is None or len(series) < window + 1:
        return None
    try:
        cur = float(series.iloc[-1])
        past = float(series.iloc[-(window + 1)])
        return round((cur - past) / past * 100, 4) if past != 0 else None
    except:
        return None


def _safe_zscore(val, series, window=ZSCORE_WINDOW):
    if val is None or series is None or len(series) < window:
        return None
    try:
        recent = series.tail(window).dropna()
        if len(recent) < 20:
            return None
        m, s = float(recent.mean()), float(recent.std())
        return round((val - m) / s, 3) if s > 1e-8 else 0.0
    except:
        return None


def _safe_corr(s1, s2, window=20):
    if s1 is None or s2 is None or min(len(s1), len(s2)) < window:
        return None
    try:
        r1 = s1.pct_change().tail(window).dropna()
        r2 = s2.pct_change().tail(window).dropna()
        if min(len(r1), len(r2)) < 10:
            return None
        c = float(r1.corr(r2))
        return round(c, 4) if not np.isnan(c) else None
    except:
        return None


def _col(df, name):
    return df[name].dropna() if name in df.columns else None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 지표 계산
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def calc_indicators(df: pd.DataFrame) -> dict:
    spy  = _col(df, "SPY");  tlt = _col(df, "TLT");  shy = _col(df, "SHY")
    hyg  = _col(df, "HYG");  lqd = _col(df, "LQD");  gld = _col(df, "GLD")
    uso  = _col(df, "USO");  cper = _col(df, "CPER"); uup = _col(df, "UUP")
    eem  = _col(df, "EEM");  fxi = _col(df, "FXI");   ewj = _col(df, "EWJ")
    qqq  = _col(df, "QQQ");  iwm = _col(df, "IWM")
    r = {}

    # 1. Risk Appetite: (HYG/LQD) × (SPY/TLT) 20d 변화율
    try:
        idx = (hyg / lqd) * (spy / tlt)
        r["risk_appetite_idx"] = _safe_pct(idx)
        r["risk_appetite_zscore"] = _safe_zscore(r["risk_appetite_idx"],
                                                  idx.pct_change(MOM_WINDOW) * 100)
    except:
        r["risk_appetite_idx"] = r["risk_appetite_zscore"] = None

    # 2. 금리 스프레드: SHY/TLT 비율 변화
    try:
        sp = shy / tlt
        r["spread_momentum"] = _safe_pct(sp)
        r["spread_zscore"] = _safe_zscore(r["spread_momentum"],
                                           sp.pct_change(MOM_WINDOW) * 100)
    except:
        r["spread_momentum"] = r["spread_zscore"] = None

    # 3. 안전자산: (GLD + TLT) 평균 모멘텀
    try:
        gm, tm = _safe_pct(gld), _safe_pct(tlt)
        vals = [v for v in [gm, tm] if v is not None]
        r["safe_haven_momentum"] = round(sum(vals) / len(vals), 4) if vals else None
        r["safe_haven_zscore"] = _safe_zscore(
            r["safe_haven_momentum"],
            ((gld.pct_change(MOM_WINDOW) + tlt.pct_change(MOM_WINDOW)) / 2 * 100)
            if gld is not None and tlt is not None else None)
    except:
        r["safe_haven_momentum"] = r["safe_haven_zscore"] = None

    # 4. 달러
    r["dollar_momentum"] = _safe_pct(uup)
    try:
        r["dollar_zscore"] = _safe_zscore(r["dollar_momentum"],
                                           uup.pct_change(MOM_WINDOW) * 100 if uup is not None else None)
    except:
        r["dollar_zscore"] = None

    # 5. 글로벌 성장
    try:
        vals = [v for v in [_safe_pct(eem), _safe_pct(fxi), _safe_pct(ewj)] if v is not None]
        r["global_growth_momentum"] = round(sum(vals) / len(vals), 4) if vals else None
        r["global_growth_zscore"] = _safe_zscore(
            r["global_growth_momentum"],
            ((eem.pct_change(MOM_WINDOW) + fxi.pct_change(MOM_WINDOW) + ewj.pct_change(MOM_WINDOW)) / 3 * 100)
            if all(x is not None for x in [eem, fxi, ewj]) else None)
    except:
        r["global_growth_momentum"] = r["global_growth_zscore"] = None

    # 6. 소형주/대형주
    try:
        ratio = iwm / spy
        r["small_large_ratio"] = _safe_pct(ratio)
        r["breadth_zscore"] = _safe_zscore(r["small_large_ratio"],
                                            ratio.pct_change(MOM_WINDOW) * 100)
    except:
        r["small_large_ratio"] = r["breadth_zscore"] = None

    # 7. 구리/금
    try:
        cg = cper / gld
        r["copper_gold_ratio"] = _safe_pct(cg)
    except:
        r["copper_gold_ratio"] = None

    # 8. 하이일드 스프레드 (역방향)
    hyg_pct = _safe_pct(hyg)
    r["hy_spread_proxy"] = round(-hyg_pct, 4) if hyg_pct is not None else None

    # 주식-채권 상관관계
    r["stock_bond_corr_20d"] = _safe_corr(spy, tlt, 20)

    # 종가 저장
    for t in list(ASSETS.keys()) + ["SPY"]:
        c = _col(df, t)
        r[f"{t.lower()}_close"] = round(float(c.iloc[-1]), 2) if c is not None and len(c) > 0 else None

    return r


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 스코어링
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _z2s(z, max_pts, inverted=False):
    """Z-Score → 점수 (Sigmoid 변환). inverted=True: 역방향 지표"""
    if z is None:
        return max_pts / 2
    if inverted:
        z = -z
    try:
        prob = 1.0 / (1.0 + math.exp(-z * 1.2))
    except OverflowError:
        prob = 1.0 if z > 0 else 0.0
    return round(prob * max_pts, 2)


def _lin(val, lo, hi, max_pts, inverted=False):
    """선형 보간 fallback"""
    if val is None:
        return max_pts / 2
    v = -val if inverted else val
    if v <= lo:
        return 0.0
    if v >= hi:
        return max_pts
    return round((v - lo) / (hi - lo) * max_pts, 2)


def score_cross_asset(ind: dict) -> dict:
    """8개 지표 → 8개 점수 (총 20점)"""
    s = {}

    # 1. Risk Appetite (4점)
    z = ind.get("risk_appetite_zscore")
    s["risk_appetite_score"] = _z2s(z, 4.0) if z is not None else _lin(ind.get("risk_appetite_idx"), -3, 3, 4.0)

    # 2. 금리 스프레드 (2점)
    z = ind.get("spread_zscore")
    s["rate_spread_score"] = _z2s(z, 2.0) if z is not None else _lin(ind.get("spread_momentum"), -2, 2, 2.0)

    # 3. 안전자산 (2점, 역방향)
    z = ind.get("safe_haven_zscore")
    s["safe_haven_score"] = _z2s(z, 2.0, inverted=True) if z is not None else _lin(ind.get("safe_haven_momentum"), -3, 1, 2.0, inverted=True)

    # 4. 달러 (2점, 역방향)
    z = ind.get("dollar_zscore")
    s["dollar_score"] = _z2s(z, 2.0, inverted=True) if z is not None else _lin(ind.get("dollar_momentum"), -3, 2, 2.0, inverted=True)

    # 5. 글로벌 성장 (3점)
    z = ind.get("global_growth_zscore")
    s["global_growth_score"] = _z2s(z, 3.0) if z is not None else _lin(ind.get("global_growth_momentum"), -3, 3, 3.0)

    # 6. 시장 심도 (3점): 소형주 + 구리/금 + 하이일드 합산
    z_b = ind.get("breadth_zscore")
    base = _z2s(z_b, 1.5) if z_b is not None else _lin(ind.get("small_large_ratio"), -2, 2, 1.5)
    cg = _lin(ind.get("copper_gold_ratio"), -3, 3, 0.75)
    hy = _lin(ind.get("hy_spread_proxy"), -2, 3, 0.75, inverted=True)
    s["breadth_score"] = round(min(base + cg + hy, 3.0), 2)
    s["copper_gold_score"] = round(cg, 2)
    s["hy_spread_score"] = round(hy, 2)

    # 주식-채권 상관관계 감점 (양의 상관 = 동시 하락 위험)
    corr = ind.get("stock_bond_corr_20d")
    penalty = min(2.0, max(0, (corr - 0.3)) * 4.0) if corr is not None and corr > 0.3 else 0.0

    total = sum(v for k, v in s.items() if k not in ("copper_gold_score", "hy_spread_score"))
    s["cross_asset_total"] = round(max(0.0, min(20.0, total - penalty)), 2)

    return s


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 메인 실행
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run_cross_asset(calc_date: date = None):
    if calc_date is None:
        calc_date = date.today()

    _ensure_table()

    df = _fetch_prices()
    if df.empty or len(df) < MOM_WINDOW + 5:
        print("[CROSS-ASSET] ❌ 데이터 부족")
        return None

    ind = calc_indicators(df)

    filled = sum(1 for k, v in ind.items() if not k.endswith("_close") and v is not None)
    quality = "FULL" if filled >= 7 else "PARTIAL" if filled >= 4 else "POOR"
    print(f"[CROSS-ASSET] 📊 지표 {filled}/8 계산 (품질: {quality})")

    scores = score_cross_asset(ind)

    # DB 저장
    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO cross_asset_daily (
                calc_date,
                tlt_close, shy_close, hyg_close, lqd_close,
                gld_close, uso_close, cper_close, uup_close,
                eem_close, fxi_close, ewj_close, qqq_close, iwm_close, spy_close,
                risk_appetite_idx, spread_momentum, safe_haven_momentum,
                dollar_momentum, global_growth_momentum,
                small_large_ratio, copper_gold_ratio, hy_spread_proxy,
                risk_appetite_zscore, spread_zscore, safe_haven_zscore,
                dollar_zscore, global_growth_zscore, breadth_zscore,
                stock_bond_corr_20d,
                risk_appetite_score, rate_spread_score, safe_haven_score,
                dollar_score, global_growth_score, breadth_score,
                copper_gold_score, hy_spread_score, cross_asset_total,
                data_quality
            ) VALUES (
                %s, %s,%s,%s,%s, %s,%s,%s,%s, %s,%s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s,%s, %s,
                %s,%s,%s,%s,%s,%s,%s,%s,%s, %s
            )
            ON CONFLICT (calc_date) DO UPDATE SET
                tlt_close=EXCLUDED.tlt_close, shy_close=EXCLUDED.shy_close,
                hyg_close=EXCLUDED.hyg_close, lqd_close=EXCLUDED.lqd_close,
                gld_close=EXCLUDED.gld_close, uso_close=EXCLUDED.uso_close,
                cper_close=EXCLUDED.cper_close, uup_close=EXCLUDED.uup_close,
                eem_close=EXCLUDED.eem_close, fxi_close=EXCLUDED.fxi_close,
                ewj_close=EXCLUDED.ewj_close, qqq_close=EXCLUDED.qqq_close,
                iwm_close=EXCLUDED.iwm_close, spy_close=EXCLUDED.spy_close,
                risk_appetite_idx=EXCLUDED.risk_appetite_idx,
                spread_momentum=EXCLUDED.spread_momentum,
                safe_haven_momentum=EXCLUDED.safe_haven_momentum,
                dollar_momentum=EXCLUDED.dollar_momentum,
                global_growth_momentum=EXCLUDED.global_growth_momentum,
                small_large_ratio=EXCLUDED.small_large_ratio,
                copper_gold_ratio=EXCLUDED.copper_gold_ratio,
                hy_spread_proxy=EXCLUDED.hy_spread_proxy,
                risk_appetite_zscore=EXCLUDED.risk_appetite_zscore,
                spread_zscore=EXCLUDED.spread_zscore,
                safe_haven_zscore=EXCLUDED.safe_haven_zscore,
                dollar_zscore=EXCLUDED.dollar_zscore,
                global_growth_zscore=EXCLUDED.global_growth_zscore,
                breadth_zscore=EXCLUDED.breadth_zscore,
                stock_bond_corr_20d=EXCLUDED.stock_bond_corr_20d,
                risk_appetite_score=EXCLUDED.risk_appetite_score,
                rate_spread_score=EXCLUDED.rate_spread_score,
                safe_haven_score=EXCLUDED.safe_haven_score,
                dollar_score=EXCLUDED.dollar_score,
                global_growth_score=EXCLUDED.global_growth_score,
                breadth_score=EXCLUDED.breadth_score,
                copper_gold_score=EXCLUDED.copper_gold_score,
                hy_spread_score=EXCLUDED.hy_spread_score,
                cross_asset_total=EXCLUDED.cross_asset_total,
                data_quality=EXCLUDED.data_quality, updated_at=NOW()
        """, (
            calc_date,
            ind.get("tlt_close"), ind.get("shy_close"), ind.get("hyg_close"), ind.get("lqd_close"),
            ind.get("gld_close"), ind.get("uso_close"), ind.get("cper_close"), ind.get("uup_close"),
            ind.get("eem_close"), ind.get("fxi_close"), ind.get("ewj_close"), ind.get("qqq_close"),
            ind.get("iwm_close"), ind.get("spy_close"),
            ind.get("risk_appetite_idx"), ind.get("spread_momentum"),
            ind.get("safe_haven_momentum"), ind.get("dollar_momentum"),
            ind.get("global_growth_momentum"), ind.get("small_large_ratio"),
            ind.get("copper_gold_ratio"), ind.get("hy_spread_proxy"),
            ind.get("risk_appetite_zscore"), ind.get("spread_zscore"),
            ind.get("safe_haven_zscore"), ind.get("dollar_zscore"),
            ind.get("global_growth_zscore"), ind.get("breadth_zscore"),
            ind.get("stock_bond_corr_20d"),
            scores.get("risk_appetite_score"), scores.get("rate_spread_score"),
            scores.get("safe_haven_score"), scores.get("dollar_score"),
            scores.get("global_growth_score"), scores.get("breadth_score"),
            scores.get("copper_gold_score"), scores.get("hy_spread_score"),
            scores.get("cross_asset_total"), quality,
        ))

    # 결과 출력
    print(f"\n[CROSS-ASSET] ✅ {calc_date} 저장 완료")
    for k, max_p in [("risk_appetite_score", 4), ("rate_spread_score", 2),
                      ("safe_haven_score", 2), ("dollar_score", 2),
                      ("global_growth_score", 3), ("breadth_score", 3)]:
        print(f"  {k:<25s} {scores.get(k, 0):>5.1f}/{max_p}")

    corr = ind.get("stock_bond_corr_20d")
    if corr is not None and corr > 0.3:
        print(f"  ⚠️ 주식-채권 양의 상관 ({corr:.2f}) → 감점 적용")

    print(f"  {'─'*35}")
    print(f"  {'cross_asset_total':<25s} {scores.get('cross_asset_total', 0):>5.1f}/20 (품질: {quality})")

    return {"indicators": ind, "scores": scores, "quality": quality}


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    from db_pool import init_pool
    init_pool()
    run_cross_asset()