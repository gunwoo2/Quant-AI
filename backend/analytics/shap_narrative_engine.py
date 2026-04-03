"""
analytics/shap_narrative_engine.py — SHAP → 자연어 리서치 노트 v1.0 (SET A-4)
================================================================================
SHAP JSON 데이터를 구조화된 자연어 리서치 노트로 변환.

파이프라인:
  1. ai_scores_daily에서 SHAP 데이터 로드 (shap_top5_pos, shap_top5_neg)
  2. Feature → Category 매핑 (실적, 모멘텀, 밸류에이션, 기술적, 감성 등)
  3. 횡단면 비교 (섹터 내 Z-Score)
  4. Template 기반 자연어 렌더링
  5. 출력: Discord Markdown + DB 저장 + (향후) PDF

설계 근거:
  - Lundberg & Lee (2017): SHAP은 게임이론 기반 Feature Attribution
  - EU AI Act (2024): 금융 AI 설명 가능성 법적 요구
  - 기관 실무: IC 미팅에서 "왜 이 종목?"에 정량적 근거 필요

실행:
  scheduler.py Step 7.7에서 호출 (Trading Signals 이후)
  또는 API에서 개별 종목 요청 시 on-demand 생성
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import logging
import numpy as np
from datetime import datetime, date
from db_pool import get_cursor

logger = logging.getLogger("shap_narrative")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Feature → 카테고리/템플릿 매핑
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FEATURE_MAP = {
    # ── Fundamental (L1) ──
    "eps_growth":       ("실적",       "EPS 성장률 {val:+.1%}"),
    "revenue_growth":   ("실적",       "매출 성장률 {val:+.1%}"),
    "earnings_surprise":("실적",       "어닝 서프라이즈 {val:+.1%}"),
    "roe":              ("수익성",     "ROE {val:.1%}"),
    "roa":              ("수익성",     "ROA {val:.1%}"),
    "gross_margin":     ("수익성",     "매출총이익률 {val:.1%}"),
    "operating_margin": ("수익성",     "영업이익률 {val:.1%}"),
    "net_margin":       ("수익성",     "순이익률 {val:.1%}"),
    "debt_to_equity":   ("재무건전성", "부채비율 {val:.1f}x"),
    "current_ratio":    ("재무건전성", "유동비율 {val:.1f}x"),
    "interest_coverage":("재무건전성", "이자보상배율 {val:.1f}x"),
    "pe_ratio":         ("밸류에이션", "PER {val:.1f}x"),
    "pb_ratio":         ("밸류에이션", "PBR {val:.1f}x"),
    "ev_ebitda":        ("밸류에이션", "EV/EBITDA {val:.1f}x"),
    "ps_ratio":         ("밸류에이션", "PSR {val:.1f}x"),
    "fcf_yield":        ("밸류에이션", "FCF Yield {val:.1%}"),
    "dividend_yield":   ("밸류에이션", "배당수익률 {val:.1%}"),

    # ── Technical (L3) ──
    "momentum_5d":      ("모멘텀",     "5일 수익률 {val:+.1%}"),
    "momentum_10d":     ("모멘텀",     "10일 수익률 {val:+.1%}"),
    "momentum_20d":     ("모멘텀",     "20일 수익률 {val:+.1%}"),
    "momentum_60d":     ("모멘텀",     "60일 수익률 {val:+.1%}"),
    "rsi_14":           ("기술적",     "RSI {val:.0f}"),
    "bb_position":      ("기술적",     "볼린저밴드 {val:.0%} 위치"),
    "macd_histogram":   ("기술적",     "MACD 히스토그램 {val:+.3f}"),
    "volume_surge":     ("수급",       "거래량 급증 {val:.1f}x"),
    "volume_20d_avg":   ("수급",       "20일 평균 거래량 {val:,.0f}"),
    "obv_trend":        ("수급",       "OBV 추세 {val}"),
    "golden_cross":     ("기술적",     "골든크로스 발생"),
    "breakout_52w":     ("기술적",     "52주 신고가 돌파"),
    "bb_squeeze":       ("기술적",     "볼린저밴드 스퀴즈 (돌파 임박)"),
    "relative_momentum":("모멘텀",     "섹터 대비 상대 모멘텀 {val:+.1%}"),
    
    # ── Sentiment (L2) ──
    "news_sentiment":   ("뉴스",       "뉴스 감성 {val:+.2f}"),
    "analyst_revision": ("애널리스트", "애널리스트 목표가 {direction} 조정"),
    "analyst_consensus":("애널리스트", "컨센서스 평균 목표가 {val}"),
    "insider_net":      ("내부자",     "내부자 순매수 {val:+.0f}건"),
    
    # ── Cross-Asset / Macro ──
    "vix_level":        ("매크로",     "VIX {val:.1f}"),
    "put_call_ratio":   ("시장심리",   "풋/콜 비율 {val:.2f}"),
    "sector_momentum":  ("섹터",       "섹터 모멘텀 {val:+.1%}"),
    
    # ── Interaction / Derived ──
    "score_momentum_5d":("스코어변화", "5일 점수 변화 {val:+.1f}"),
    "score_std_5d":     ("스코어변화", "5일 점수 변동성 {val:.2f}"),
    "l1_x_momentum":    ("복합",       "재무×모멘텀 상호작용 {val:+.2f}"),
    "sector_rank":      ("섹터",       "섹터 내 순위 {val:.0f}위"),
}

# 매핑 안 되는 Feature용 기본 템플릿
DEFAULT_TEMPLATE = ("기타", "{feature}: {val:+.3f}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 테이블 보장
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def ensure_research_notes_table():
    with get_cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS research_notes (
                id          SERIAL PRIMARY KEY,
                stock_id    INTEGER NOT NULL,
                ticker      VARCHAR(20) NOT NULL,
                calc_date   DATE NOT NULL,
                grade       VARCHAR(5),
                percentile  NUMERIC(6,2),
                conviction  NUMERIC(6,2),
                bull_case   JSONB,
                bear_case   JSONB,
                summary     TEXT,
                discord_md  TEXT,
                created_at  TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(stock_id, calc_date)
            )
        """)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 핵심 엔진
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _load_shap_data(stock_id: int, calc_date: date) -> dict:
    """SHAP 데이터 로드"""
    with get_cursor() as cur:
        cur.execute("""
            SELECT ai_score, ai_proba, shap_top5_pos, shap_top5_neg, shap_all, shap_base
            FROM ai_scores_daily
            WHERE stock_id = %s AND calc_date = (
                SELECT MAX(calc_date) FROM ai_scores_daily
                WHERE stock_id = %s AND calc_date <= %s
            )
        """, (stock_id, stock_id, calc_date))
        row = cur.fetchone()
        if not row:
            return None
        return dict(row)


def _load_score_data(stock_id: int, calc_date: date) -> dict:
    """종목 점수 데이터 로드"""
    with get_cursor() as cur:
        cur.execute("""
            SELECT s.ticker, s.company_name, sec.sector_name,
                   f.weighted_score, f.layer1_score, f.layer2_score, f.layer3_score,
                   f.grade, f.percentile_rank, f.conviction_score
            FROM stocks s
            JOIN stock_final_scores f ON s.stock_id = f.stock_id
            LEFT JOIN sectors sec ON s.sector_id = sec.sector_id
            WHERE s.stock_id = %s
              AND f.calc_date = (SELECT MAX(calc_date) FROM stock_final_scores WHERE stock_id = %s AND calc_date <= %s)
        """, (stock_id, stock_id, calc_date))
        row = cur.fetchone()
        return dict(row) if row else None


def _format_feature(feature_name: str, shap_value: float, raw_value=None) -> dict:
    """Feature → 구조화 자연어"""
    mapping = FEATURE_MAP.get(feature_name, None)
    
    if mapping:
        category, template = mapping
        try:
            # 방향 판단
            direction = "상향" if shap_value > 0 else "하향"
            val = raw_value if raw_value is not None else shap_value
            text = template.format(val=val, direction=direction, feature=feature_name)
        except (ValueError, KeyError):
            text = f"{feature_name}: {shap_value:+.3f}"
    else:
        category = "기타"
        text = f"{feature_name}: {shap_value:+.3f}"
    
    # SHAP 영향도 레벨
    abs_shap = abs(shap_value)
    if abs_shap > 0.1:
        impact = "강한"
    elif abs_shap > 0.05:
        impact = "중간"
    else:
        impact = "약한"
    
    return {
        "feature": feature_name,
        "category": category,
        "text": text,
        "shap_value": shap_value,
        "impact": impact,
    }


def generate_research_note(stock_id: int, calc_date: date) -> dict:
    """
    종목별 리서치 노트 생성.
    
    Returns:
        {
            "ticker": "AAPL",
            "grade": "A",
            "summary": "...",         # 종합 요약 (2~3줄)
            "bull_case": [...],       # 매수 근거 리스트
            "bear_case": [...],       # 리스크 요인 리스트
            "discord_md": "...",      # Discord Markdown 포맷
        }
    """
    score = _load_score_data(stock_id, calc_date)
    shap = _load_shap_data(stock_id, calc_date)
    
    if not score:
        return None
    
    ticker = score["ticker"]
    company = score.get("company_name", ticker)
    sector = score.get("sector_name", "")
    grade = score.get("grade", "")
    pct = float(score.get("percentile_rank", 0))
    conviction = float(score.get("conviction_score", 0) or 0)
    l1 = float(score.get("layer1_score", 0) or 0)
    l2 = float(score.get("layer2_score", 0) or 0)
    l3 = float(score.get("layer3_score", 0) or 0)
    ws = float(score.get("weighted_score", 0) or 0)
    
    # SHAP 데이터 파싱
    bull_case = []
    bear_case = []
    
    if shap:
        # 양수 SHAP (매수 근거)
        top_pos = shap.get("shap_top5_pos")
        if isinstance(top_pos, str):
            try: top_pos = json.loads(top_pos)
            except: top_pos = []
        if isinstance(top_pos, list):
            for item in top_pos[:5]:
                if isinstance(item, dict):
                    feat = item.get("feature", item.get("name", ""))
                    val = float(item.get("value", item.get("shap_value", 0)))
                    bull_case.append(_format_feature(feat, val))
        
        # 음수 SHAP (리스크)
        top_neg = shap.get("shap_top5_neg")
        if isinstance(top_neg, str):
            try: top_neg = json.loads(top_neg)
            except: top_neg = []
        if isinstance(top_neg, list):
            for item in top_neg[:3]:
                if isinstance(item, dict):
                    feat = item.get("feature", item.get("name", ""))
                    val = float(item.get("value", item.get("shap_value", 0)))
                    bear_case.append(_format_feature(feat, abs(val) * -1))
    
    # SHAP 없으면 레이어 점수 기반 생성
    if not bull_case:
        if l1 >= 55: bull_case.append({"category": "재무", "text": f"재무 건전성 양호 (L1: {l1:.0f})", "impact": "중간"})
        if l2 >= 55: bull_case.append({"category": "뉴스", "text": f"시장 심리 긍정적 (L2: {l2:.0f})", "impact": "중간"})
        if l3 >= 55: bull_case.append({"category": "기술적", "text": f"기술적 지표 양호 (L3: {l3:.0f})", "impact": "중간"})
    if not bear_case:
        if l1 < 45: bear_case.append({"category": "재무", "text": f"재무 지표 약세 (L1: {l1:.0f})", "impact": "중간"})
        if l2 < 45: bear_case.append({"category": "뉴스", "text": f"시장 심리 부정적 (L2: {l2:.0f})", "impact": "중간"})
        if l3 < 45: bear_case.append({"category": "기술적", "text": f"기술적 약세 (L3: {l3:.0f})", "impact": "중간"})
    
    # 종합 요약 생성
    if pct >= 90:
        rank_text = f"상위 {100-pct:.0f}% (매우 우수)"
    elif pct >= 75:
        rank_text = f"상위 {100-pct:.0f}% (우수)"
    elif pct >= 50:
        rank_text = f"상위 {100-pct:.0f}% (평균 이상)"
    else:
        rank_text = f"하위 {100-pct:.0f}%"
    
    bull_summary = "; ".join([b["text"] for b in bull_case[:3]])
    bear_summary = "; ".join([b["text"] for b in bear_case[:2]]) if bear_case else "현재 주요 리스크 요인 없음"
    
    summary = (f"{company}({ticker})은 {sector} 섹터에서 {rank_text}에 위치. "
               f"주요 강점: {bull_summary}. "
               f"주의 요인: {bear_summary}.")
    
    # Discord Markdown
    grade_emoji = {"S": "🏆", "A+": "🥇", "A": "🥈", "B+": "🥉"}.get(grade, "📊")
    
    discord_lines = [
        f"**{grade_emoji} {ticker} — {grade}등급 (상위 {100-pct:.0f}%) | 확신도: {conviction:.1f}/10**",
        f"> {company} | {sector}",
        "",
        "**📈 매수 근거:**",
    ]
    for i, b in enumerate(bull_case[:4], 1):
        discord_lines.append(f"  {i}. [{b['category']}] {b['text']} ({b['impact']} 영향)")
    
    if bear_case:
        discord_lines.append("")
        discord_lines.append("**⚠️ 리스크 요인:**")
        for i, b in enumerate(bear_case[:3], 1):
            discord_lines.append(f"  {i}. [{b['category']}] {b['text']}")
    
    discord_lines.extend([
        "",
        f"📊 `L1:{l1:.0f} | L2:{l2:.0f} | L3:{l3:.0f} | Total:{ws:.1f}`",
        "─" * 40,
    ])
    discord_md = "\n".join(discord_lines)
    
    # DB 저장
    ensure_research_notes_table()
    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO research_notes
            (stock_id, ticker, calc_date, grade, percentile, conviction,
             bull_case, bear_case, summary, discord_md)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (stock_id, calc_date) DO UPDATE SET
                grade=EXCLUDED.grade, percentile=EXCLUDED.percentile,
                conviction=EXCLUDED.conviction, bull_case=EXCLUDED.bull_case,
                bear_case=EXCLUDED.bear_case, summary=EXCLUDED.summary,
                discord_md=EXCLUDED.discord_md
        """, (stock_id, ticker, calc_date, grade, pct, conviction,
              json.dumps(bull_case, ensure_ascii=False),
              json.dumps(bear_case, ensure_ascii=False),
              summary, discord_md))
    
    return {
        "ticker": ticker,
        "grade": grade,
        "percentile": pct,
        "conviction": conviction,
        "summary": summary,
        "bull_case": bull_case,
        "bear_case": bear_case,
        "discord_md": discord_md,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 배치 실행
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run_daily_notes(calc_date: date = None, top_n: int = 20):
    """
    상위 N종목 + 등급 변경 종목에 대해 리서치 노트 자동 생성.
    scheduler.py Step 7.7에서 호출.
    """
    if calc_date is None:
        calc_date = date.today()
    
    print(f"\n[SHAP-NOTE] Generating research notes for {calc_date}")
    ensure_research_notes_table()
    
    # 상위 N종목
    with get_cursor() as cur:
        cur.execute("""
            SELECT f.stock_id, s.ticker, f.grade, f.percentile_rank
            FROM stock_final_scores f
            JOIN stocks s ON f.stock_id = s.stock_id
            WHERE f.calc_date = (
                SELECT MAX(calc_date) FROM stock_final_scores WHERE calc_date <= %s
            )
            ORDER BY f.weighted_score DESC
            LIMIT %s
        """, (calc_date, top_n))
        targets = [dict(r) for r in cur.fetchall()]
    
    # 등급 변경 종목 추가
    with get_cursor() as cur:
        cur.execute("""
            WITH recent AS (
                SELECT stock_id, grade, calc_date,
                       LAG(grade) OVER (PARTITION BY stock_id ORDER BY calc_date) as prev_grade
                FROM stock_final_scores
                WHERE calc_date >= %s - INTERVAL '7 days'
            )
            SELECT stock_id FROM recent
            WHERE calc_date = (SELECT MAX(calc_date) FROM stock_final_scores WHERE calc_date <= %s)
              AND grade != prev_grade
              AND prev_grade IS NOT NULL
        """, (calc_date, calc_date))
        changed_ids = {r["stock_id"] for r in cur.fetchall()}
    
    # 기존 타겟에 없는 변경 종목 추가
    existing_ids = {t["stock_id"] for t in targets}
    for sid in changed_ids - existing_ids:
        with get_cursor() as cur:
            cur.execute("""
                SELECT f.stock_id, s.ticker, f.grade, f.percentile_rank
                FROM stock_final_scores f JOIN stocks s ON f.stock_id = s.stock_id
                WHERE f.stock_id = %s
                ORDER BY f.calc_date DESC LIMIT 1
            """, (sid,))
            row = cur.fetchone()
            if row:
                targets.append(dict(row))
    
    results = []
    for t in targets:
        try:
            note = generate_research_note(t["stock_id"], calc_date)
            if note:
                results.append(note)
        except Exception as e:
            logger.warning(f"Note generation failed for {t.get('ticker')}: {e}")
    
    print(f"[SHAP-NOTE] Generated {len(results)} notes (top {top_n} + {len(changed_ids)} grade changes)")
    return results


if __name__ == "__main__":
    run_daily_notes()
