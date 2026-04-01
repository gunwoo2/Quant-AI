"""
notify_ai_patch.py — AI 모듈 데이터 → 알림 반영 패치
=====================================================
기존 notifier + notify_data_builder에 AI 모듈(#1~#5) 데이터를 연동.

반영 항목:
  [BUY 카드]
    ★ AI Score (XGBoost 확률)
    ★ SHAP TOP 3 기여 요인 ("이 종목이 S등급인 이유")
    ★ Signal Half-Life ("이 시그널 유효기간 7일")
    ★ Layer Agreement ("L1/L2/L3 모두 일치")
    ★ Factor Interaction 태그 ("BUFFETT_SYNERGY")

  [MORNING 브리핑]
    ★ Macro Score (Cross-Asset Intelligence)
    ★ Adaptive Weights (현재 L1/L2/L3 비중)
    ★ IC 건강도 (팩터별 IC 상태)
    ★ XGBoost 모델 상태 (AUC, 재학습일)

사용법:
  기존 코드에 import하여 enrich/format 함수만 호출.

  # notify_data_builder에서:
  from notify_ai_patch import enrich_buy_with_ai, enrich_morning_with_ai

  # notifier에서:
  from notify_ai_patch import format_ai_buy_fields, format_ai_morning_fields
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date, datetime
from db_pool import get_cursor


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# §1. BUY 카드 AI 데이터 수집
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def enrich_buy_with_ai(stock_id: int, calc_date: date, signal_data: dict) -> dict:
    """
    매수 시그널 데이터에 AI 모듈 정보를 추가.
    build_buy_rationale() 호출 후 이 함수로 보강.

    추가 필드:
      ai_score:        XGBoost 확률 × 100 (0~100)
      shap_top3_pos:   양수 기여 TOP 3
      shap_top3_neg:   음수 기여 TOP 3
      signal_expiry:   시그널 유효기간 (일)
      half_life:       IC 반감기 (일)
      layer_agreement: L1/L2/L3 방향 일치도 (0~1)
      factor_tags:     Factor Interaction 태그
      conviction_v5:   5차원 Conviction 점수
    """
    result = dict(signal_data)

    # ── AI Score + SHAP (#4, #5) ──
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT ai_score, ensemble_score, ai_weight,
                       shap_top5_pos, shap_top5_neg, shap_base
                FROM ai_scores_daily
                WHERE stock_id = %s AND calc_date <= %s
                ORDER BY calc_date DESC LIMIT 1
            """, (stock_id, calc_date))
            row = cur.fetchone()
        if row:
            result["ai_score"] = float(row["ai_score"]) if row["ai_score"] else None
            result["ensemble_score"] = float(row["ensemble_score"]) if row["ensemble_score"] else None
            result["ai_weight"] = float(row["ai_weight"]) if row["ai_weight"] else 0.30
            result["shap_top3_pos"] = (row["shap_top5_pos"] or [])[:3]
            result["shap_top3_neg"] = (row["shap_top5_neg"] or [])[:3]
    except Exception:
        pass

    # ── Signal Half-Life (#3) ──
    try:
        grade = signal_data.get("grade", "B")
        with get_cursor() as cur:
            cur.execute("""
                SELECT half_life_days, recommended_expiry, status
                FROM signal_halflife
                WHERE grade = %s
                ORDER BY calc_date DESC LIMIT 1
            """, (grade,))
            row = cur.fetchone()
        if row:
            result["half_life"] = float(row["half_life_days"]) if row["half_life_days"] else None
            result["signal_expiry"] = int(row["recommended_expiry"]) if row["recommended_expiry"] else None
            result["decay_status"] = row["status"]
    except Exception:
        pass

    # ── Layer Agreement + Conviction (#2) ──
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT conviction_score, percentile_rank
                FROM stock_final_scores
                WHERE stock_id = %s AND calc_date <= %s
                ORDER BY calc_date DESC LIMIT 1
            """, (stock_id, calc_date))
            row = cur.fetchone()
        if row:
            result["conviction_v5"] = float(row["conviction_score"]) if row.get("conviction_score") else None
            # Layer agreement: L1/L2/L3 방향 일치도 (점수 기반 추론)
            l1 = signal_data.get("l1_score", 50)
            l2 = signal_data.get("l2_score", 50)
            l3 = signal_data.get("l3_score", 50)
            scores = [s for s in [l1, l2, l3] if s is not None]
            if len(scores) >= 2:
                above = sum(1 for s in scores if s >= 50)
                result["layer_agreement"] = 1.0 if above == len(scores) or above == 0 else 0.6 if above >= 2 else 0.3
    except Exception:
        pass

    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# §2. BUY 카드 AI 필드 포맷팅
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def format_ai_buy_fields(signal_data: dict) -> list:
    """
    AI 데이터를 Discord Embed fields 리스트로 변환.
    기존 fields에 extend하여 사용.

    Returns:
        list of {"name": ..., "value": ..., "inline": bool}
    """
    fields = []

    # AI Score
    ai_score = signal_data.get("ai_score")
    if ai_score is not None:
        ai_bar = _score_bar_mini(ai_score)
        fields.append({
            "name": "🤖 AI Score",
            "value": f"`{ai_score:.1f}/100` {ai_bar}",
            "inline": True,
        })

    # Signal Half-Life + Expiry
    half_life = signal_data.get("half_life")
    expiry = signal_data.get("signal_expiry")
    if expiry:
        hl_text = f"{half_life:.1f}일" if half_life else "측정중"
        fields.append({
            "name": "⏳ 시그널 유효기간",
            "value": f"**{expiry}일** (HL: {hl_text})",
            "inline": True,
        })

    # Layer Agreement
    agreement = signal_data.get("layer_agreement")
    if agreement is not None:
        if agreement >= 0.9:
            ag_text = "✅ 완전 일치"
        elif agreement >= 0.6:
            ag_text = "🟡 대체로 일치"
        else:
            ag_text = "🔴 방향 혼재"
        fields.append({
            "name": "🔗 레이어 일치도",
            "value": f"{ag_text} ({agreement:.0%})",
            "inline": True,
        })

    # SHAP 기여 요인 (최대 3개)
    shap_pos = signal_data.get("shap_top3_pos", [])
    shap_neg = signal_data.get("shap_top3_neg", [])
    if shap_pos or shap_neg:
        shap_lines = []
        for item in shap_pos[:3]:
            name = item.get("feature", "?")
            val = item.get("shap", 0)
            shap_lines.append(f"📈 {name} `+{val:.1f}`")
        for item in shap_neg[:2]:
            name = item.get("feature", "?")
            val = item.get("shap", 0)
            shap_lines.append(f"📉 {name} `{val:.1f}`")

        if shap_lines:
            fields.append({
                "name": "🧠 AI가 본 핵심 요인 (SHAP)",
                "value": "\n".join(shap_lines),
                "inline": False,
            })

    return fields


def _score_bar_mini(score: float, max_score: float = 100) -> str:
    filled = int(score / max_score * 8)
    return "█" * filled + "░" * (8 - filled)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# §3. MORNING 브리핑 AI 데이터 수집
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def enrich_morning_with_ai(calc_date: date) -> dict:
    """
    모닝 브리핑에 추가할 AI 데이터 수집.

    Returns:
        {
            "macro_score": 72,
            "risk_appetite": 1.5,
            "safe_haven": -0.3,
            "adaptive_weights": (0.52, 0.23, 0.25),
            "ic_health": [...],
            "model_status": {...},
            "factor_warnings": [...],
        }
    """
    result = {}

    # ── Cross-Asset Macro (#1) ──
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT macro_score, risk_appetite, safe_haven_demand,
                       yield_spread_proxy, dollar_impact, commodity_cycle, global_risk_on
                FROM cross_asset_daily
                ORDER BY calc_date DESC LIMIT 1
            """)
            row = cur.fetchone()
        if row:
            result["macro_score"] = float(row["macro_score"]) if row["macro_score"] else None
            result["risk_appetite"] = float(row["risk_appetite"]) if row["risk_appetite"] else None
            result["safe_haven"] = float(row["safe_haven_demand"]) if row["safe_haven_demand"] else None
            result["yield_spread"] = float(row["yield_spread_proxy"]) if row["yield_spread_proxy"] else None
    except Exception:
        pass

    # ── Adaptive Weights (#2) ──
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT w_l1, w_l2, w_l3, avg_ic_l1, avg_ic_l2, avg_ic_l3, method
                FROM factor_weights_monthly
                ORDER BY month DESC LIMIT 1
            """)
            row = cur.fetchone()
        if row:
            result["adaptive_weights"] = (
                float(row["w_l1"]), float(row["w_l2"]), float(row["w_l3"]))
            result["weight_method"] = row.get("method", "default")
            result["ic_l1"] = float(row["avg_ic_l1"]) if row.get("avg_ic_l1") else None
            result["ic_l2"] = float(row["avg_ic_l2"]) if row.get("avg_ic_l2") else None
            result["ic_l3"] = float(row["avg_ic_l3"]) if row.get("avg_ic_l3") else None
    except Exception:
        pass

    # ── IC 건강도 (#2) ──
    try:
        from batch.batch_factor_monitor import get_ic_health_summary
        health = get_ic_health_summary()
        result["ic_warnings"] = health.get("warnings", [])
    except Exception:
        result["ic_warnings"] = []

    # ── XGBoost 모델 상태 (#4) ──
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT model_name, trained_date, train_auc, valid_auc
                FROM ml_model_meta
                WHERE is_active = TRUE
                ORDER BY trained_date DESC LIMIT 1
            """)
            row = cur.fetchone()
        if row:
            result["model_status"] = {
                "trained_date": str(row["trained_date"]),
                "train_auc": float(row["train_auc"]) if row["train_auc"] else None,
                "valid_auc": float(row["valid_auc"]) if row["valid_auc"] else None,
            }
    except Exception:
        pass

    # ── v5.0: Ensemble Disagreement + HMM Regime ──
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT AVG(ensemble_disagreement) as avg_dis,
                       COUNT(*) FILTER (WHERE ensemble_disagreement > 0.3) as hi_cnt
                FROM stock_final_scores
                WHERE calc_date = %s AND ensemble_disagreement IS NOT NULL
            """, (calc_date,))
            dr = cur.fetchone()
            if dr and dr["avg_dis"]:
                result["ensemble_disagreement"] = round(float(dr["avg_dis"]), 3)
                result["ensemble_high_dis"] = int(dr["hi_cnt"] or 0)
    except Exception:
        pass

    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT dominant_regime, confidence, equity_impact, is_fallback
                FROM macro_regime_daily WHERE calc_date = %s
            """, (calc_date,))
            rr = cur.fetchone()
            if rr:
                result["hmm_regime"] = rr["dominant_regime"]
                result["hmm_confidence"] = round(float(rr["confidence"] or 0), 2)
                result["hmm_fallback"] = bool(rr["is_fallback"])
    except Exception:
        pass

    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# §4. MORNING 브리핑 AI 필드 포맷팅
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def format_ai_morning_fields(ai_data: dict) -> list:
    """
    AI 데이터를 Morning Briefing embed fields로 변환.
    """
    fields = []

    # Macro Score
    macro = ai_data.get("macro_score")
    if macro is not None:
        if macro >= 65:
            m_emoji = "🟢"
            m_label = "Risk-On"
        elif macro >= 40:
            m_emoji = "🟡"
            m_label = "Neutral"
        else:
            m_emoji = "🔴"
            m_label = "Risk-Off"

        fields.append({
            "name": "🌍 글로벌 매크로",
            "value": f"{m_emoji} `{macro:.0f}/100` ({m_label})",
            "inline": True,
        })

    # Risk Appetite
    ra = ai_data.get("risk_appetite")
    if ra is not None:
        ra_emoji = "📈" if ra > 1 else ("📉" if ra < -1 else "➡️")
        fields.append({
            "name": "위험선호지수",
            "value": f"{ra_emoji} `{ra:+.1f}%`",
            "inline": True,
        })

    # Adaptive Weights
    weights = ai_data.get("adaptive_weights")
    if weights:
        w1, w2, w3 = weights
        method = ai_data.get("weight_method", "default")
        is_adaptive = method != "default"
        indicator = "🔄" if is_adaptive else "📌"
        fields.append({
            "name": f"{indicator} 가중치 (L1/L2/L3)",
            "value": f"`{w1:.0%}` / `{w2:.0%}` / `{w3:.0%}` {'(IC 자동)' if is_adaptive else '(기본값)'}",
            "inline": True,
        })

    # XGBoost Model
    model = ai_data.get("model_status")
    if model:
        auc = model.get("valid_auc") or model.get("train_auc")
        trained = model.get("trained_date", "?")
        if auc:
            fields.append({
                "name": "🤖 XGBoost",
                "value": f"AUC `{auc:.3f}` (학습: {trained})",
                "inline": True,
            })

    # IC 경고
    warnings = ai_data.get("ic_warnings", [])
    if warnings:
        fields.append({
            "name": "⚠️ 팩터 경고",
            "value": "\n".join(warnings[:3]),
            "inline": False,
        })

    return fields


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# §5. 적용 가이드
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#
# ── notify_data_builder.py 수정 ──
#
# build_buy_rationale() 함수 끝에 추가:
#   from notify_ai_patch import enrich_buy_with_ai
#   result = enrich_buy_with_ai(stock_id, calc_date, result)
#
# ── notifier.py 수정 ──
#
# _send_buy_premium() 함수에서 fields 리스트 구성 후:
#   from notify_ai_patch import format_ai_buy_fields
#   ai_fields = format_ai_buy_fields(s)
#   fields.extend(ai_fields)
#
# notify_morning_briefing() 함수에서 my_fields 구성 후:
#   from notify_ai_patch import enrich_morning_with_ai, format_ai_morning_fields
#   ai_morning = enrich_morning_with_ai(calc_date)
#   ai_fields = format_ai_morning_fields(ai_morning)
#   my_fields.extend(ai_fields)
#