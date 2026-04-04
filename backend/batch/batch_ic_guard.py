"""
batch/batch_ic_guard.py — Adaptive IC Guard & Weight Optimizer v3.0
═══════════════════════════════════════════════════════════════════════════

"Two Sigma / AQR / Citadel 수준의 팩터 가중치 자동 최적화"

핵심 알고리즘:
  ★ Bayesian Shrinkage: IC 추정치의 불확실성 반영 (Meucci 2010)
  ★ Block Bootstrap IC 신뢰구간: 시계열 자기상관 보존 (Politis & Romano 1994)
  ★ Factor Crowding Detection: 팩터 간 상관 높으면 분산 강제
  ★ Turnover Penalty: scipy SLSQP 최적화, 변경의 "가치" 계산
  ★ Multi-Horizon IC (5d/10d/20d 동시): 단일 horizon 의존 제거
  ★ IC Decay Curve: IC가 며칠 후 사라지는가 측정
  ★ 6중 Composite: RankIC + Q-Spread + HitRate + TailRatio + Stability + Decay
  ★ ThreadPool 병렬: L1/L2/L3 동시 평가

학술 근거:
  Grinold & Kahn (2000): Active Portfolio Management — IC/IR
  Meucci (2010): Bayesian Estimation of Factor Portfolios
  López de Prado (2018): Advances in Financial ML — CUSUM
  Harvey, Liu & Zhu (2016): Multiple Testing in Factor Research
  Politis & Romano (1994): Block Bootstrap
  DeMiguel, Garlappi & Uppal (2009): 1/N vs Optimization
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json, logging
import numpy as np
from datetime import date, timedelta
from dataclasses import dataclass, field
from typing import List, Dict, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from scipy.stats import spearmanr
from scipy.optimize import minimize
from db_pool import get_cursor

logger = logging.getLogger("ic_guard_v3")

# ── Config ──
IC_LOOKBACK_DAYS    = 30
IC_MIN_CROSS_SECT   = 50
HORIZONS            = [5, 10, 20]
HORIZON_WEIGHTS     = {5: 0.25, 10: 0.50, 20: 0.25}
PRIOR_IC, PRIOR_STRENGTH = 0.0, 30
BOOTSTRAP_N, BLOCK_SIZE  = 200, 5
CROWDING_THRESHOLD  = 0.70
TURNOVER_COST       = 0.02
MIN_IMPROVEMENT     = 0.01
W_MIN, W_MAX        = 0.00, 1.00
W_DAILY_MAX_DELTA   = 0.20
SMOOTH = {"CRISIS": 0.60, "BEAR": 0.40, "NEUTRAL": 0.25, "BULL": 0.15, "CUSUM": 0.55}
METRIC_W = {"rank_ic": 0.25, "quintile_spread": 0.20, "hit_rate": 0.15,
            "tail_ratio": 0.10, "ic_stability": 0.15, "ic_decay_score": 0.15}

@dataclass
class LayerDiag:
    layer: str
    ic_by_horizon: Dict[int, float] = field(default_factory=dict)
    blended_ic: float = 0.0
    raw_ic: float = 0.0
    shrunk_ic: float = 0.0
    posterior_std: float = 0.0
    boot_ci_low: float = 0.0
    boot_ci_high: float = 0.0
    boot_prob_pos: float = 0.5
    quintile_returns: List[float] = field(default_factory=list)
    quintile_spread: float = 0.0
    monotonicity: float = 0.0
    hit_rate: float = 0.5
    tail_ratio: float = 1.0
    daily_ics: List[float] = field(default_factory=list)
    ewma_ic: float = 0.0
    ic_stability: float = 0.0
    ic_decay_curve: Dict[int, float] = field(default_factory=dict)
    ic_decay_score: float = 0.0
    cusum_value: float = 0.0
    cusum_signal: str = "NORMAL"
    composite: float = 0.0
    status: str = "UNKNOWN"
    samples: int = 0
    n_days: int = 0

@dataclass
class CrowdingInfo:
    l1_l2: float = 0.0
    l1_l3: float = 0.0
    l2_l3: float = 0.0
    is_crowded: bool = False
    pairs: List[str] = field(default_factory=list)

# ── Tables ──
def _ensure_tables():
    with get_cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS adaptive_weights (
                id SERIAL PRIMARY KEY, calc_date DATE NOT NULL UNIQUE,
                l1_weight NUMERIC(6,4) NOT NULL, l2_weight NUMERIC(6,4) NOT NULL,
                l3_weight NUMERIC(6,4) NOT NULL, method VARCHAR(30) DEFAULT 'ic_guard_v3',
                ic_l1 NUMERIC(8,6), ic_l2 NUMERIC(8,6), ic_l3 NUMERIC(8,6),
                detail JSONB, created_at TIMESTAMPTZ DEFAULT NOW())""")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ic_guard_log (
                id SERIAL PRIMARY KEY, calc_date DATE NOT NULL, layer VARCHAR(10) NOT NULL,
                rank_ic NUMERIC(8,6), quintile_spread NUMERIC(8,6), hit_rate NUMERIC(6,4),
                tail_ratio NUMERIC(8,4), composite_score NUMERIC(8,6), ewma_ic NUMERIC(8,6),
                cusum_signal VARCHAR(10), samples INTEGER, old_weight NUMERIC(6,4),
                new_weight NUMERIC(6,4), detail JSONB, created_at TIMESTAMPTZ DEFAULT NOW())""")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_icg_date ON ic_guard_log(calc_date)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_aw_date ON adaptive_weights(calc_date)")

# ── Bulk Data Load (Multi-Horizon, 단일 쿼리) ──
def _load_all_data(calc_date: date) -> list:
    start = calc_date - timedelta(days=int(IC_LOOKBACK_DAYS * 2.5))
    mh = max(HORIZONS)
    with get_cursor() as cur:
        cur.execute("""
            WITH base AS (
                SELECT f.stock_id, f.calc_date, f.layer1_score, f.layer2_score, f.layer3_score,
                       f.weighted_score, p0.close_price AS base_price
                FROM stock_final_scores f
                JOIN LATERAL (SELECT close_price FROM stock_prices_daily
                    WHERE stock_id=f.stock_id AND trade_date<=f.calc_date
                    ORDER BY trade_date DESC LIMIT 1) p0 ON TRUE
                WHERE f.calc_date BETWEEN %s AND %s)
            SELECT b.*, p5.close_price AS price_5d, p10.close_price AS price_10d, p20.close_price AS price_20d
            FROM base b
            LEFT JOIN LATERAL (SELECT close_price FROM stock_prices_daily
                WHERE stock_id=b.stock_id AND trade_date>=b.calc_date+5 ORDER BY trade_date LIMIT 1) p5 ON TRUE
            LEFT JOIN LATERAL (SELECT close_price FROM stock_prices_daily
                WHERE stock_id=b.stock_id AND trade_date>=b.calc_date+10 ORDER BY trade_date LIMIT 1) p10 ON TRUE
            LEFT JOIN LATERAL (SELECT close_price FROM stock_prices_daily
                WHERE stock_id=b.stock_id AND trade_date>=b.calc_date+20 ORDER BY trade_date LIMIT 1) p20 ON TRUE
            ORDER BY b.calc_date, b.stock_id
        """, (start, calc_date - timedelta(days=mh)))
        return [dict(r) for r in cur.fetchall()]

def _prepare(rows):
    n = len(rows)
    d = {"l1":np.zeros(n),"l2":np.zeros(n),"l3":np.zeros(n),"weighted":np.zeros(n),
         "dates":np.empty(n,dtype=object),"sids":np.zeros(n,dtype=int)}
    for h in HORIZONS: d[f"ret_{h}d"] = np.full(n, np.nan)
    for i,r in enumerate(rows):
        d["l1"][i]=float(r.get("layer1_score",0) or 0)
        d["l2"][i]=float(r.get("layer2_score",0) or 0)
        d["l3"][i]=float(r.get("layer3_score",0) or 0)
        d["weighted"][i]=float(r.get("weighted_score",0) or 0)
        d["dates"][i]=r.get("calc_date")
        d["sids"][i]=int(r.get("stock_id",0) or 0)
        bp=float(r.get("base_price",0) or 0)
        if bp>0:
            for h in HORIZONS:
                fp=float(r.get(f"price_{h}d",0) or 0)
                if fp>0: d[f"ret_{h}d"][i]=fp/bp-1
    return d

# ── Core Analytics ──
def _bayesian_shrink(raw_ic, n):
    post_mean = (n*raw_ic + PRIOR_STRENGTH*PRIOR_IC) / (n+PRIOR_STRENGTH)
    post_std = 1.0/np.sqrt(n+PRIOR_STRENGTH)
    return post_mean, post_std

def _block_bootstrap(scores, returns, n_boot=BOOTSTRAP_N):
    n=len(scores)
    if n<30: return -1,1,0.5
    bs=min(BLOCK_SIZE,n//5); nb=max(1,n//bs)
    rng=np.random.default_rng(42); ics=[]
    for _ in range(n_boot):
        starts=rng.integers(0,n-bs+1,size=nb)
        idx=np.concatenate([np.arange(s,min(s+bs,n)) for s in starts])[:n]
        if len(idx)<20: continue
        try:
            ic,_=spearmanr(scores[idx],returns[idx])
            if not np.isnan(ic): ics.append(ic)
        except: pass
    if len(ics)<50: return -1,1,0.5
    a=np.array(ics)
    return float(np.percentile(a,5)), float(np.percentile(a,95)), float(np.mean(a>0))

def _quintile_analysis(scores, returns):
    n=len(scores); qs=n//5
    if qs<10: return {"spread":0,"mono":0,"hit":0.5,"tail":1.0,"q_rets":[]}
    order=np.argsort(scores)
    q_rets=[float(np.mean(returns[order[i*qs:(i+1)*qs if i<4 else n]])) for i in range(5)]
    top_q=returns[order[-qs:]]; bot_q=returns[order[:qs]]
    spread=float(np.mean(top_q)-np.mean(bot_q))
    hit=float(np.mean(top_q>0))
    st=np.sort(top_q); q4=max(1,len(st)//4)
    tail=float(np.mean(st[-q4:])/abs(np.mean(st[:q4]))) if abs(np.mean(st[:q4]))>0.001 else 1.0
    tail=np.clip(tail,0.1,10.0)
    try:
        mono,_=spearmanr(q_rets,[1,2,3,4,5]); mono=float(max(0,mono))
    except: mono=0
    return {"spread":spread,"mono":mono,"hit":hit,"tail":tail,"q_rets":q_rets}

def _daily_ics(scores, returns, dates):
    result=[]
    for d in np.unique(dates):
        m=(dates==d)&~np.isnan(returns)
        if m.sum()>=IC_MIN_CROSS_SECT:
            try:
                ic,_=spearmanr(scores[m],returns[m])
                if not np.isnan(ic): result.append(float(ic))
            except: pass
    return result

def _ewma(vals, hl=5):
    if not vals: return 0.0
    a=np.array(vals); alpha=1-np.exp(-np.log(2)/hl)
    w=np.array([(1-alpha)**i for i in range(len(a))])[::-1]; w/=w.sum()
    return float(np.dot(a,w))

def _cusum(vals, threshold=0.08, drift=0.01):
    if len(vals)<3: return "NORMAL",0.0
    cn=0.0
    for v in vals: cn=min(0,cn+v+drift)
    return ("ALERT" if abs(cn)>threshold else "NORMAL"), float(cn)

def _evaluate_layer(layer_name, scores, data, dates):
    dg=LayerDiag(layer=layer_name)
    for h in HORIZONS:
        rk=f"ret_{h}d"; rets=data.get(rk,np.full(len(scores),np.nan))
        v=~(np.isnan(scores)|np.isnan(rets))
        if v.sum()>=IC_MIN_CROSS_SECT:
            try:
                ic,_=spearmanr(scores[v],rets[v])
                dg.ic_by_horizon[h]=float(ic) if not np.isnan(ic) else 0.0
            except: dg.ic_by_horizon[h]=0.0
    dg.blended_ic=sum(dg.ic_by_horizon.get(h,0)*HORIZON_WEIGHTS.get(h,0) for h in HORIZONS)
    dg.raw_ic=dg.blended_ic
    pr=data.get("ret_10d",np.full(len(scores),np.nan))
    v=~(np.isnan(scores)|np.isnan(pr)); s,r,dd=scores[v],pr[v],dates[v]
    dg.samples=int(v.sum())
    if dg.samples<IC_MIN_CROSS_SECT: dg.status="INSUFFICIENT"; return dg
    dg.shrunk_ic,dg.posterior_std=_bayesian_shrink(dg.blended_ic,dg.samples)
    dg.boot_ci_low,dg.boot_ci_high,dg.boot_prob_pos=_block_bootstrap(s,r)
    qa=_quintile_analysis(s,r)
    dg.quintile_returns=qa["q_rets"]; dg.quintile_spread=qa["spread"]
    dg.monotonicity=qa["mono"]; dg.hit_rate=qa["hit"]; dg.tail_ratio=qa["tail"]
    dg.daily_ics=_daily_ics(s,r,dd); dg.n_days=len(dg.daily_ics)
    dg.ewma_ic=_ewma(dg.daily_ics)
    if len(dg.daily_ics)>=3:
        ia=np.array(dg.daily_ics); ist=np.std(ia)
        dg.ic_stability=float(np.mean(ia)/ist) if ist>0.001 else 0.0
        dg.ic_stability=np.clip(dg.ic_stability,-3,3)
    for h in HORIZONS:
        rk=f"ret_{h}d"; rets=data.get(rk,np.full(len(s),np.nan))
        vv=~np.isnan(rets[:len(s)])
        if vv.sum()>=IC_MIN_CROSS_SECT:
            try:
                ic,_=spearmanr(s[vv],rets[vv])
                if not np.isnan(ic): dg.ic_decay_curve[h]=float(ic)
            except: pass
    if dg.ic_decay_curve:
        mx=max(abs(v) for v in dg.ic_decay_curve.values())
        lst=abs(dg.ic_decay_curve.get(max(HORIZONS),0))
        dg.ic_decay_score=float(lst/mx) if mx>0 else 0
    dg.cusum_signal,dg.cusum_value=_cusum(dg.daily_ics)
    ni=np.clip(dg.shrunk_ic/0.15,-1,1)
    nq=np.clip(dg.quintile_spread/0.04,-1,1)
    nh=np.clip((dg.hit_rate-0.5)*4,-1,1)
    nt=np.clip((dg.tail_ratio-1)/2,-1,1)
    ns=np.clip(dg.ic_stability/2,-1,1)
    nd=np.clip(dg.ic_decay_score*2-1,-1,1)
    dg.composite=(METRIC_W["rank_ic"]*ni+METRIC_W["quintile_spread"]*nq+
        METRIC_W["hit_rate"]*nh+METRIC_W["tail_ratio"]*nt+
        METRIC_W["ic_stability"]*ns+METRIC_W["ic_decay_score"]*nd)
    if dg.boot_prob_pos>=0.90 and dg.composite>0.15: dg.status="STRONG"
    elif dg.boot_prob_pos>=0.70 and dg.composite>0: dg.status="MODERATE"
    elif dg.composite>-0.10: dg.status="WEAK"
    else: dg.status="NEGATIVE"
    return dg

# ── Crowding ──
def _detect_crowding(data):
    ca=CrowdingInfo()
    try:
        v=~(np.isnan(data["l1"])|np.isnan(data["l2"])|np.isnan(data["l3"]))
        a,b,c=data["l1"][v],data["l2"][v],data["l3"][v]
        if len(a)>30:
            ca.l1_l2=float(np.corrcoef(a,b)[0,1])
            ca.l1_l3=float(np.corrcoef(a,c)[0,1])
            ca.l2_l3=float(np.corrcoef(b,c)[0,1])
            for nm,cr in [("L1-L2",ca.l1_l2),("L1-L3",ca.l1_l3),("L2-L3",ca.l2_l3)]:
                if abs(cr)>CROWDING_THRESHOLD: ca.pairs.append(nm)
            ca.is_crowded=len(ca.pairs)>0
    except: pass
    return ca

# ── Optimizer (Turnover-Penalized SLSQP) ──
def _get_prev(calc_date):
    try:
        with get_cursor() as cur:
            cur.execute("SELECT l1_weight,l2_weight,l3_weight FROM adaptive_weights WHERE calc_date<%s ORDER BY calc_date DESC LIMIT 1",(calc_date,))
            r=cur.fetchone()
            if r: return {"l1":float(r["l1_weight"]),"l2":float(r["l2_weight"]),"l3":float(r["l3_weight"])}
    except: pass
    return {"l1":0.0,"l2":0.0,"l3":1.0}

def _get_regime():
    try:
        with get_cursor() as cur:
            cur.execute("SELECT regime FROM market_regime ORDER BY calc_date DESC LIMIT 1")
            r=cur.fetchone()
            if r: return r["regime"]
    except: pass
    return "NEUTRAL"

def _optimize(metrics, prev, crowding, regime):
    layers=["l1","l2","l3"]
    comps={l:metrics[l].composite if l in metrics else 0 for l in layers}
    if crowding.is_crowded:
        for pair in crowding.pairs:
            la,lb=pair.lower().split("-")
            if comps.get(la,0)<comps.get(lb,0): comps[la]*=0.7
            else: comps[lb]*=0.7
    def obj(w):
        util=sum(w[i]*comps[layers[i]] for i in range(3))
        turn=sum(abs(w[i]-prev.get(layers[i],0.33)) for i in range(3))
        return -(util-TURNOVER_COST*turn)
    cons=[{"type":"eq","fun":lambda w:sum(w)-1.0}]
    bds=[(W_MIN,W_MAX)]*3
    x0=[prev.get(l,0.33) for l in layers]
    try:
        res=minimize(obj,x0,method="SLSQP",bounds=bds,constraints=cons)
        if res.success: opt={layers[i]:float(res.x[i]) for i in range(3)}
        else: raise ValueError
    except:
        tot=sum(max(0,v) for v in comps.values())
        if tot>0: opt={l:max(0,comps[l])/tot for l in layers}
        else:
            best=max(layers,key=lambda l:comps[l])
            opt={l:(1.0 if l==best else 0.0) for l in layers}
    nu=sum(opt[l]*comps[l] for l in layers)
    ou=sum(prev.get(l,0.33)*comps[l] for l in layers)
    if nu-ou<MIN_IMPROVEMENT: opt=dict(prev)
    ca=any(metrics.get(l,LayerDiag(l)).cusum_signal=="ALERT" for l in layers)
    sf=SMOOTH.get("CUSUM" if ca else regime, SMOOTH["NEUTRAL"])
    sm={}
    for l in layers:
        o=prev.get(l,0.33); n=opt[l]; sm[l]=o*(1-sf)+n*sf
        d=sm[l]-o
        if abs(d)>W_DAILY_MAX_DELTA: sm[l]=o+np.sign(d)*W_DAILY_MAX_DELTA
    tot=sum(sm.values())
    final={l:round(sm[l]/tot,4) for l in layers} if tot>0 else {"l1":0,"l2":0,"l3":1.0}
    return final,sf

# ── Main ──
def run_ic_guard(calc_date=None):
    if calc_date is None: calc_date=date.today()
    print(f"\n[IC-GUARD v3] === Adaptive Weight Optimizer — {calc_date} ===")
    _ensure_tables()
    rows=_load_all_data(calc_date)
    if not rows:
        print("  ⚠️ 데이터 없음"); return _get_prev(calc_date)
    data=_prepare(rows); ud=np.unique(data["dates"])
    print(f"  Data: {len(rows)} samples, {len(ud)} days, horizons={HORIZONS}")
    
    metrics={}
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs={ex.submit(_evaluate_layer,l,data[l],data,data["dates"]):l for l in ["l1","l2","l3"]}
        for f in as_completed(futs):
            l=futs[f]
            try: metrics[l]=f.result()
            except Exception as e: logger.error(f"{l}:{e}"); metrics[l]=LayerDiag(l,status="ERROR")
    
    crowding=_detect_crowding(data)
    
    print(f"\n  {'Layer':<6s} │ {'ShrunkIC':>8s} {'P(>0)':>7s} {'Q-Spr':>7s} {'Hit%':>6s} {'Stab':>6s} {'Decay':>6s} │ {'Comp':>7s} {'CUSUM':>6s} {'Status':>8s}")
    print(f"  {'-'*82}")
    for l in ["l1","l2","l3"]:
        m=metrics[l]
        e={"STRONG":"✅","MODERATE":"🟡","WEAK":"⚠️","NEGATIVE":"❌"}.get(m.status,"❓")
        print(f"  {l.upper():<6s} │ {m.shrunk_ic:>+8.4f} {m.boot_prob_pos:>6.1%} {m.quintile_spread:>+7.4f} {m.hit_rate:>5.1%} {m.ic_stability:>+6.2f} {m.ic_decay_score:>6.2f} │ {m.composite:>+7.4f} {m.cusum_signal:>6s} {e}{m.status:>7s}")
        if m.ic_decay_curve:
            dc=" ".join([f"{h}d:{ic:+.3f}" for h,ic in sorted(m.ic_decay_curve.items())])
            print(f"         │ Decay: {dc}")
    
    if crowding.is_crowded:
        print(f"\n  ⚠️ Crowding: {', '.join(crowding.pairs)}")
    
    prev=_get_prev(calc_date); regime=_get_regime()
    new_w,sf=_optimize(metrics,prev,crowding,regime)
    turn=sum(abs(new_w[l]-prev.get(l,0)) for l in ["l1","l2","l3"])/2
    
    print(f"\n  Regime: {regime} | Smooth: {sf:.2f} | Crowding: {'⚠️' if crowding.is_crowded else '✅'}")
    print(f"  이전: L1={prev['l1']:.4f}  L2={prev['l2']:.4f}  L3={prev['l3']:.4f}")
    print(f"  신규: L1={new_w['l1']:.4f}  L2={new_w['l2']:.4f}  L3={new_w['l3']:.4f}  (turnover:{turn:.1%})")
    
    detail={"version":"v3.0",
        "metrics":{l:{"blended_ic":m.blended_ic,"shrunk_ic":m.shrunk_ic,"post_std":m.posterior_std,
            "boot_ci":[m.boot_ci_low,m.boot_ci_high],"boot_p":m.boot_prob_pos,
            "q_spread":m.quintile_spread,"q_rets":m.quintile_returns,"mono":m.monotonicity,
            "hit":m.hit_rate,"tail":m.tail_ratio,"stab":m.ic_stability,
            "decay":m.ic_decay_curve,"decay_score":m.ic_decay_score,
            "ewma":m.ewma_ic,"cusum":m.cusum_signal,"comp":m.composite,
            "status":m.status,"n":m.samples,"days":m.n_days
        } for l,m in metrics.items()},
        "crowding":{"l1_l2":crowding.l1_l2,"l1_l3":crowding.l1_l3,"l2_l3":crowding.l2_l3,"pairs":crowding.pairs},
        "regime":regime,"sf":sf,"turnover":turn,"prev":prev}
    
    with get_cursor() as cur:
        cur.execute("""INSERT INTO adaptive_weights (calc_date,l1_weight,l2_weight,l3_weight,method,ic_l1,ic_l2,ic_l3,detail)
            VALUES(%s,%s,%s,%s,'ic_guard_v3',%s,%s,%s,%s)
            ON CONFLICT(calc_date) DO UPDATE SET l1_weight=EXCLUDED.l1_weight,l2_weight=EXCLUDED.l2_weight,
            l3_weight=EXCLUDED.l3_weight,method=EXCLUDED.method,ic_l1=EXCLUDED.ic_l1,ic_l2=EXCLUDED.ic_l2,
            ic_l3=EXCLUDED.ic_l3,detail=EXCLUDED.detail""",
            (calc_date,new_w["l1"],new_w["l2"],new_w["l3"],
             metrics.get("l1",LayerDiag("l1")).shrunk_ic,
             metrics.get("l2",LayerDiag("l2")).shrunk_ic,
             metrics.get("l3",LayerDiag("l3")).shrunk_ic,json.dumps(detail,default=str)))
        for l in ["l1","l2","l3"]:
            m=metrics.get(l,LayerDiag(l))
            cur.execute("""INSERT INTO ic_guard_log (calc_date,layer,rank_ic,quintile_spread,hit_rate,tail_ratio,
                composite_score,ewma_ic,cusum_signal,samples,old_weight,new_weight,detail)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (calc_date,l,m.shrunk_ic,m.quintile_spread,m.hit_rate,m.tail_ratio,
                 m.composite,m.ewma_ic,m.cusum_signal,m.samples,prev.get(l),new_w[l],
                 json.dumps({"ic_h":m.ic_by_horizon,"boot":[m.boot_ci_low,m.boot_ci_high],
                     "ics10":m.daily_ics[-10:],"decay":m.ic_decay_curve},default=str)))
    print(f"[IC-GUARD v3] ✅ 완료")
    return new_w

def get_today_weights(calc_date=None):
    if calc_date is None: calc_date=date.today()
    try:
        with get_cursor() as cur:
            cur.execute("SELECT l1_weight,l2_weight,l3_weight,calc_date FROM adaptive_weights WHERE calc_date<=%s ORDER BY calc_date DESC LIMIT 1",(calc_date,))
            r=cur.fetchone()
            if r: return {"l1":float(r["l1_weight"]),"l2":float(r["l2_weight"]),"l3":float(r["l3_weight"]),"source":f"v3_{r['calc_date']}"}
    except: pass
    return {"l1":0.0,"l2":0.0,"l3":1.0,"source":"fallback"}

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser(description="IC Guard v3")
    p.add_argument("--date",type=str,default=None)
    a=p.parse_args()
    d=date.fromisoformat(a.date) if a.date else date.today()
    run_ic_guard(d)
