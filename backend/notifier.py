"""
notifier.py — QUANT AI v4.0 Premium + Public 알림 시스템
========================================================
2-Tier 구조:
  [PREMIUM] 개인 전용 13웹훅 (v4 고도화: IB/학술 방법론)
  [PUBLIC]  공개 채널 5웹훅  (MORNING / BUY / SELL / RISK / REPORT)

Premium 방법론:
  Goldman Conviction + Bridgewater Because + Grinold IC
  MAE/MFE + Brinson Attribution + Historical VaR + Stress Test

웹훅 18개 (채널 배치는 자유):
  예) #프리미엄_매수 채널에 MY_BUY + MY_ADD + MY_BOUNCE 웹훅 3개 등록
  코드는 웹훅별로 분리 전송 → 채널 통합/분리는 .env만 바꾸면 됨

.env 웹훅:
  # ── Premium (개인) 13개 ──
  DISCORD_WEBHOOK_MY_BUY / SELL / PROFIT / ADD / FIRE / BOUNCE
  DISCORD_WEBHOOK_MY_REPORT / ALERT / MORNING / PERF / SYSTEM / RISK / BACKTEST
  # ── Public (공개) 5개 ──
  DISCORD_WEBHOOK_PUB_MORNING / BUY / SELL / RISK / REPORT
  # ── Fallback ──
  DISCORD_WEBHOOK_URL
"""
import os
import logging
import math
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Any, Tuple

import requests

logger = logging.getLogger("notifier")

# ═══════════════════════════════════════════════════════════
#  설정 + 웹훅 매핑 (18개)
# ═══════════════════════════════════════════════════════════

CHANNEL = os.environ.get("NOTIFY_CHANNEL", "discord").lower()

# ── Premium (개인) 13웹훅 ──
_WEBHOOK_MY = {
    "BUY":      os.environ.get("DISCORD_WEBHOOK_MY_BUY", ""),
    "SELL":     os.environ.get("DISCORD_WEBHOOK_MY_SELL", ""),
    "PROFIT":   os.environ.get("DISCORD_WEBHOOK_MY_PROFIT", ""),
    "ADD":      os.environ.get("DISCORD_WEBHOOK_MY_ADD", ""),
    "FIRE":     os.environ.get("DISCORD_WEBHOOK_MY_FIRE", ""),
    "BOUNCE":   os.environ.get("DISCORD_WEBHOOK_MY_BOUNCE", ""),
    "REPORT":   os.environ.get("DISCORD_WEBHOOK_MY_REPORT", ""),
    "ALERT":    os.environ.get("DISCORD_WEBHOOK_MY_ALERT", ""),
    "MORNING":  os.environ.get("DISCORD_WEBHOOK_MY_MORNING", ""),
    "PERF":     os.environ.get("DISCORD_WEBHOOK_MY_PERF", ""),
    "SYSTEM":   os.environ.get("DISCORD_WEBHOOK_MY_SYSTEM", ""),
    "RISK":     os.environ.get("DISCORD_WEBHOOK_MY_RISK", ""),
    "BACKTEST": os.environ.get("DISCORD_WEBHOOK_MY_BACKTEST", ""),
}

# ── Public (공개) 5웹훅 ──
_WEBHOOK_PUB = {
    "MORNING":  os.environ.get("DISCORD_WEBHOOK_PUB_MORNING", ""),
    "BUY":      os.environ.get("DISCORD_WEBHOOK_PUB_BUY", ""),
    "SELL":     os.environ.get("DISCORD_WEBHOOK_PUB_SELL", ""),
    "RISK":     os.environ.get("DISCORD_WEBHOOK_PUB_RISK", ""),
    "REPORT":   os.environ.get("DISCORD_WEBHOOK_PUB_REPORT", ""),
}

_FALLBACK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")

VERSION = "v4.0"
FOOTER_BASE = f"QUANT AI {VERSION}"


def _get_url(tier: str, ch: str) -> str:
    """tier='MY'|'PUB', ch='BUY' etc. → 웹훅 URL"""
    wmap = _WEBHOOK_MY if tier == "MY" else _WEBHOOK_PUB
    url = wmap.get(ch.upper(), "")
    if url:
        return url
    if _FALLBACK_URL:
        return _FALLBACK_URL
    for v in wmap.values():
        if v:
            return v
    return ""


# ═══════════════════════════════════════════════════════════
#  회사명 헬퍼
# ═══════════════════════════════════════════════════════════

_COMPANY_NAMES = {
    "AAPL": "Apple", "MSFT": "Microsoft", "GOOGL": "Alphabet",
    "GOOG": "Alphabet", "AMZN": "Amazon", "NVDA": "NVIDIA",
    "META": "Meta Platforms", "TSLA": "Tesla", "BRK.B": "Berkshire Hathaway",
    "JPM": "JPMorgan Chase", "V": "Visa", "JNJ": "Johnson & Johnson",
    "UNH": "UnitedHealth", "HD": "Home Depot", "PG": "Procter & Gamble",
    "MA": "Mastercard", "XOM": "ExxonMobil", "ABBV": "AbbVie",
    "MRK": "Merck", "AVGO": "Broadcom", "COST": "Costco",
    "PEP": "PepsiCo", "KO": "Coca-Cola", "LLY": "Eli Lilly",
    "TMO": "Thermo Fisher", "WMT": "Walmart", "CSCO": "Cisco",
    "MCD": "McDonald's", "CRM": "Salesforce", "ACN": "Accenture",
    "ABT": "Abbott Labs", "DHR": "Danaher", "LIN": "Linde",
    "ADBE": "Adobe", "CMCSA": "Comcast", "NKE": "Nike",
    "TXN": "Texas Instruments", "PM": "Philip Morris", "NEE": "NextEra Energy",
    "BMY": "Bristol-Myers", "RTX": "RTX Corp", "NFLX": "Netflix",
    "AMD": "AMD", "INTC": "Intel", "QCOM": "Qualcomm",
    "UPS": "UPS", "INTU": "Intuit", "T": "AT&T",
    "AMGN": "Amgen", "GS": "Goldman Sachs", "MS": "Morgan Stanley",
    "BA": "Boeing", "CAT": "Caterpillar", "DE": "John Deere",
    "DIS": "Disney", "PYPL": "PayPal", "SQ": "Block Inc",
    "SHOP": "Shopify", "NOW": "ServiceNow", "SNOW": "Snowflake",
    "UBER": "Uber", "ABNB": "Airbnb", "COIN": "Coinbase",
    "PLTR": "Palantir", "ARM": "ARM Holdings", "PANW": "Palo Alto Networks",
    "CRWD": "CrowdStrike", "ZS": "Zscaler", "NET": "Cloudflare",
    "DDOG": "Datadog", "MDB": "MongoDB", "TEAM": "Atlassian",
    "WDAY": "Workday", "VEEV": "Veeva Systems", "CDNS": "Cadence Design",
    "SNPS": "Synopsys", "KLAC": "KLA Corp", "LRCX": "Lam Research",
    "AMAT": "Applied Materials", "MRVL": "Marvell Tech",
    "ON": "ON Semiconductor", "MCHP": "Microchip Tech",
    "ETN": "Eaton Corp", "EMR": "Emerson Electric", "HON": "Honeywell",
    "MMC": "Marsh McLennan", "AIG": "AIG", "TRV": "Travelers",
    "ALL": "Allstate", "MET": "MetLife", "PRU": "Prudential",
    "CI": "Cigna", "ELV": "Elevance Health", "HUM": "Humana",
    "CVS": "CVS Health", "MCK": "McKesson", "CAH": "Cardinal Health",
    "BIIB": "Biogen", "MRNA": "Moderna", "ZTS": "Zoetis",
    "CME": "CME Group", "ICE": "Intercontinental Exchange",
    "MSCI": "MSCI Inc", "FIS": "Fidelity National", "ADP": "ADP",
    "WFC": "Wells Fargo", "BAC": "Bank of America", "C": "Citigroup",
    "USB": "U.S. Bancorp", "PNC": "PNC Financial", "SCHW": "Charles Schwab",
    "BLK": "BlackRock", "SPGI": "S&P Global", "MCO": "Moody's",
    "MU": "Micron", "PAYX": "Paychex", "CPRT": "Copart",
    "FAST": "Fastenal", "ODFL": "Old Dominion", "UNP": "Union Pacific",
    "CSX": "CSX Corp", "NSC": "Norfolk Southern", "FDX": "FedEx",
    "VZ": "Verizon", "TMUS": "T-Mobile", "CHTR": "Charter Comm",
    "EA": "Electronic Arts", "TTWO": "Take-Two",
    "SPY": "SPDR S&P 500 ETF", "QQQ": "Invesco QQQ", "IWM": "iShares Russell 2000",
}

_db_name_cache: Dict[str, str] = {}


def _load_names_from_db():
    global _db_name_cache
    if _db_name_cache:
        return
    try:
        from db_pool import get_cursor
        with get_cursor() as cur:
            cur.execute("SELECT ticker, company_name FROM stocks WHERE company_name IS NOT NULL")
            for row in cur.fetchall():
                name = row["company_name"]
                if len(name) > 22:
                    name = name[:20] + "\u2026"
                _db_name_cache[row["ticker"]] = name
    except Exception:
        pass


def _tn(ticker: str) -> str:
    """'**AAPL** (Apple)'"""
    if not _db_name_cache:
        try:
            _load_names_from_db()
        except Exception:
            pass
    name = _db_name_cache.get(ticker) or _COMPANY_NAMES.get(ticker, "")
    return f"**{ticker}** ({name})" if name else f"**{ticker}**"


def _tn_short(ticker: str) -> str:
    return f"**{ticker}**"


# ═══════════════════════════════════════════════════════════
#  색상 / 이모지 상수
# ═══════════════════════════════════════════════════════════

class C:
    GREEN  = 0x22c55e
    RED    = 0xef4444
    YELLOW = 0xf59e0b
    BLUE   = 0x3b82f6
    PURPLE = 0x8b5cf6
    ORANGE = 0xf97316
    CYAN   = 0x06b6d4
    GRAY   = 0x6b7280


_GRADE_COLOR = {
    "S": 0xffd700, "A+": 0x22c55e, "A": 0x22c55e,
    "B+": 0x3b82f6, "B": 0x3b82f6,
    "C": 0xf59e0b, "D": 0xef4444,
}

_GRADE_CONVICTION = {
    "S": "\U0001f525 VERY HIGH", "A+": "\u2b06\ufe0f HIGH", "A": "\u2b06\ufe0f HIGH",
    "B+": "\u27a1\ufe0f MEDIUM", "B": "\u27a1\ufe0f MEDIUM",
    "C": "\u2b07\ufe0f LOW", "D": "\u2b07\ufe0f LOW",
}

_REGIME_EMOJI = {
    "BULL": "\U0001f7e2", "NEUTRAL": "\U0001f7e1", "BEAR": "\U0001f534", "CRISIS": "\U0001f6a8"
}
_REGIME_COLOR = {
    "BULL": C.GREEN, "NEUTRAL": C.YELLOW, "BEAR": C.RED, "CRISIS": 0x7f1d1d
}


# ═══════════════════════════════════════════════════════════
#  저수준 전송
# ═══════════════════════════════════════════════════════════

def _send_discord(embeds: list, tier: str = "MY", ch: str = "REPORT") -> bool:
    url = _get_url(tier, ch)
    if not url:
        logger.warning(f"[NOTIFY] 웹훅 미설정 tier={tier} ch={ch}")
        return False
    payload = {"embeds": embeds[:10]}
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code in (200, 204):
            return True
        logger.error(f"[DISCORD/{tier}-{ch}] {r.status_code}: {r.text[:200]}")
        return False
    except Exception as e:
        logger.error(f"[DISCORD/{tier}-{ch}] 전송 실패: {e}")
        return False


# ═══════════════════════════════════════════════════════════
#  유틸
# ═══════════════════════════════════════════════════════════

def _score_bar(score: float, width: int = 10) -> str:
    filled = round(score / 100 * width)
    empty = width - filled
    block = '\u2588' * filled
    light = '\u2591' * empty
    return f"{block}{light} {score:.1f}"


def _layer_breakdown(l1: float, l2: float, l3: float) -> str:
    return f"L1 `{l1:.0f}` | L2 `{l2:.0f}` | L3 `{l3:.0f}`"


def _delta_arrow(old: float, new: float) -> str:
    diff = new - old
    if diff > 5: return "\u2b06\ufe0f"
    elif diff > 0: return "\u2197\ufe0f"
    elif diff > -5: return "\u2198\ufe0f"
    else: return "\u2b07\ufe0f"


def _pnl_emoji(pnl: float) -> str:
    if pnl >= 10: return "\U0001f680"
    if pnl >= 5: return "\U0001f4c8"
    if pnl >= 0: return "\u2705"
    if pnl >= -5: return "\U0001f4c9"
    return "\U0001f4a5"


def _regime_text(regime: str) -> str:
    emoji = _REGIME_EMOJI.get(regime.upper(), "\u26aa")
    return f"{emoji} {regime.upper()}"


def _format_money(val: float) -> str:
    if abs(val) >= 1_000_000:
        return f"${val/1_000_000:,.1f}M"
    elif abs(val) >= 1_000:
        return f"${val:,.0f}"
    return f"${val:,.2f}"


def _grade_rank(grade: str) -> int:
    return {"D": 1, "C": 2, "B": 3, "B+": 4, "A": 5, "A+": 6, "S": 7}.get(grade, 0)


# ═══════════════════════════════════════════════════════════
#  1. MORNING — 모닝 브리핑
#     MY_MORNING: 국면+IC+적중률+국면확률+포폴+시그널요약
#     PUB_MORNING: 국면+시그널건수
# ═══════════════════════════════════════════════════════════

def notify_morning_briefing(
    calc_date: date,
    regime: str,
    regime_detail: dict,
    signal_summary: dict = None,
    regime_proba: dict = None,
    ic_data: dict = None,
    hit_rate: dict = None,
    fear_greed: dict = None,
    portfolio_summary: dict = None,
):
    today_str = calc_date.strftime("%Y-%m-%d")
    r_emoji = _REGIME_EMOJI.get(regime.upper(), "⚪")
    r_color = _REGIME_COLOR.get(regime.upper(), C.BLUE)

    spy = regime_detail.get("spy_price", 0)
    vix = regime_detail.get("vix_close", 0)
    sma200 = regime_detail.get("sma_200", 0)
    spy_vs_sma = ((spy / sma200 - 1) * 100) if sma200 > 0 else 0
    futures = regime_detail.get("futures_pct", 0)
    vix_chg = regime_detail.get("vix_change_pct", 0)

    sig = signal_summary or {}
    buy_cnt = sig.get("buy_count", 0)
    sell_cnt = sig.get("sell_count", 0)
    fire_cnt = sig.get("fire_count", 0)
    add_cnt = sig.get("add_count", 0)
    bounce_cnt = sig.get("bounce_count", 0)

    sig_lines = []
    if buy_cnt: sig_lines.append(f"🟢 매수 **{buy_cnt}**건")
    if sell_cnt: sig_lines.append(f"🔴 매도 **{sell_cnt}**건")
    if fire_cnt: sig_lines.append(f"🚨 긴급매도 **{fire_cnt}**건")
    if add_cnt: sig_lines.append(f"📈 추가매수 **{add_cnt}**건")
    if bounce_cnt: sig_lines.append(f"🔵 반등기회 **{bounce_cnt}**건")
    if not sig_lines:
        sig_lines = ["시그널 없음"]

    # ── Premium (MY_MORNING) ──
    my_fields = [
        {"name": "시장 국면", "value": f"{r_emoji} **{regime.upper()}**", "inline": True},
        {"name": "SPY", "value": f"${spy:,.2f}", "inline": True},
        {"name": "VIX", "value": f"{vix:.1f}", "inline": True},
        {"name": "SPY vs SMA200", "value": f"{spy_vs_sma:+.1f}%", "inline": True},
        {"name": "선물", "value": f"{futures:+.2f}%", "inline": True},
        {"name": "VIX 변동", "value": f"{vix_chg:+.1f}%", "inline": True},
    ]

    if fear_greed:
        fg_val = fear_greed.get("value", 50)
        fg_label = fear_greed.get("label", "Neutral")
        my_fields.append({"name": "Fear & Greed", "value": f"{fg_val} ({fg_label})", "inline": True})

    if ic_data:
        ic_val = ic_data.get("ic", 0)
        ic_trend = "📈" if ic_data.get("ic_trend", 0) > 0 else "📉"
        my_fields.append({
            "name": "📡 시그널 IC",
            "value": f"`{ic_val:.3f}` {ic_trend} (30일 Spearman)",
            "inline": True,
        })

    if hit_rate:
        hr = hit_rate.get("hit_rate", 0) * 100
        my_fields.append({
            "name": "🎯 적중률",
            "value": f"`{hr:.1f}%` ({hit_rate.get('hits', 0)}/{hit_rate.get('total', 0)}건, 5일 기준)",
            "inline": True,
        })

    if regime_proba:
        stay_pct = regime_proba.get("stay_probability", 0) * 100
        days_in = regime_proba.get("days_in_regime", 0)
        my_fields.append({
            "name": "🔮 국면 지속 확률",
            "value": f"`{stay_pct:.0f}%` (연속 {days_in}일째)",
            "inline": True,
        })

    ps = portfolio_summary or {}
    ps_lines = ""
    if ps:
        ps_lines = (
            f"\n\n💼 **포트폴리오**\n"
            f"총자산 {_format_money(ps.get('total_value', 0))} | "
            f"일간 {ps.get('daily_return', 0):+.2f}% | "
            f"포지션 {ps.get('num_positions', 0)}개 | "
            f"현금 {ps.get('cash_pct', 0):.1f}%"
        )

    my_embeds = [{
        "title": f"☀️ 모닝 브리핑 — {today_str}",
        "description": (
            f"{'  |  '.join(sig_lines)}"
            f"{ps_lines}"
            f"\n\n▸ 상세 → 각 채널 확인"
        ),
        "color": r_color,
        "fields": my_fields,
        "footer": {"text": f"{FOOTER_BASE} | 모닝 브리핑"},
    }]

    # ── Public (PUB_MORNING) ──
    pub_embeds = [{
        "title": f"☀️ 모닝 브리핑 — {today_str}",
        "description": (
            f"시장 국면: {r_emoji} **{regime.upper()}**\n"
            f"SPY `${spy:,.2f}` | VIX `{vix:.1f}` | 선물 `{futures:+.2f}%`\n\n"
            f"{'  |  '.join(sig_lines)}"
        ),
        "color": r_color,
        "footer": {"text": f"{FOOTER_BASE} | 모닝 브리핑"},
    }]

    _send_discord(my_embeds, "MY", "MORNING")
    _send_discord(pub_embeds, "PUB", "MORNING")
    print(f"[NOTIFY] ☀️ 모닝 브리핑 → MY_MORNING + PUB_MORNING")


# ═══════════════════════════════════════════════════════════
#  2. 매수/매도 통합 진입점
#     MY_BUY: 투자근거카드 (Goldman Conviction + Bridgewater Because)
#     PUB_BUY: 종목 + 등급 + 매수가
#     MY_SELL: MAE/MFE + 점수변화
#     PUB_SELL: 사유 + 매도가
#     MY_PROFIT: 익절 분리
#     MY_REPORT: 포트폴리오 현황
# ═══════════════════════════════════════════════════════════

def notify_daily_signals(
    calc_date: date,
    regime: str,
    regime_detail: dict,
    buy_signals: list,
    sell_signals: list,
    portfolio_summary: dict = None,
):
    today_str = calc_date.strftime("%Y-%m-%d")

    # ──────────────────────────────────
    #  BUY
    # ──────────────────────────────────
    if buy_signals:
        _send_buy_premium(today_str, regime, buy_signals)
        _send_buy_public(today_str, regime, buy_signals)
    else:
        no_embed = [{
            "title": f"📋 오늘 매수 시그널 없음 — {today_str}",
            "description": f"국면: {_regime_text(regime)} | 조건 충족 종목 없음",
            "color": C.GRAY,
            "footer": {"text": f"{FOOTER_BASE} | 매수 없음"},
        }]
        _send_discord(no_embed, "MY", "BUY")

    # ──────────────────────────────────
    #  SELL
    # ──────────────────────────────────
    if sell_signals:
        _send_sell_premium(today_str, sell_signals)
        _send_sell_public(today_str, sell_signals)
        _send_profit_premium(today_str, sell_signals)

    # ──────────────────────────────────
    #  포트폴리오 현황 → MY_REPORT
    # ──────────────────────────────────
    if portfolio_summary:
        ps = portfolio_summary
        ps_embed = [{
            "title": f"💼 포트폴리오 현황 — {today_str}",
            "color": C.GREEN if ps.get("daily_return", 0) >= 0 else C.RED,
            "fields": [
                {"name": "총 자산", "value": _format_money(ps.get("total_value", 0)), "inline": True},
                {"name": "일간 수익률", "value": f"{ps.get('daily_return', 0):+.2f}%", "inline": True},
                {"name": "포지션", "value": f"{ps.get('num_positions', 0)}개", "inline": True},
                {"name": "현금 비율", "value": f"{ps.get('cash_pct', 0):.1f}%", "inline": True},
            ],
            "footer": {"text": f"{FOOTER_BASE} | 포트폴리오"},
        }]
        _send_discord(ps_embed, "MY", "REPORT")


def _send_buy_premium(today_str: str, regime: str, buy_signals: list):
    """MY_BUY: 투자근거카드"""
    embeds = [{
        "title": f"🟢 매수 추천 ({len(buy_signals)}건) — {today_str}",
        "description": f"국면: {_regime_text(regime)} | 시그널 기준: Adaptive Threshold",
        "color": C.GREEN,
        "footer": {"text": f"{FOOTER_BASE} | 매수 추천"},
    }]

    for s in buy_signals[:6]:
        ticker = s["ticker"]
        grade = s.get("grade", "?")
        score = s.get("score", 0)
        price = s.get("price", 0)
        conviction = _GRADE_CONVICTION.get(grade, "➡️ MEDIUM")
        color = _GRADE_COLOR.get(grade, C.GREEN)

        l1 = s.get("l1_score", s.get("quant_score", 0))
        l2 = s.get("l2_score", s.get("nlp_score", 0))
        l3 = s.get("l3_score", s.get("technical_score", 0))

        # Because 자동 생성
        because_lines = []
        if l1 >= 70: because_lines.append("▸ 퀀트 펀더멘탈 우수 (수익성/성장성/밸류)")
        if l2 >= 70: because_lines.append("▸ NLP 감성 긍정적 (뉴스/애널리스트)")
        if l3 >= 70: because_lines.append("▸ 기술적 모멘텀 양호 (추세/패턴)")
        if not because_lines:
            layers = {"Quant(L1)": l1, "NLP(L2)": l2, "Tech(L3)": l3}
            best = max(layers, key=layers.get)
            because_lines.append(f"▸ {best} 중심 시그널")

        fields = [
            {"name": "등급", "value": f"**{grade}**", "inline": True},
            {"name": "종합점수", "value": _score_bar(score), "inline": True},
            {"name": "Conviction", "value": conviction, "inline": True},
            {"name": "레이어 분해", "value": _layer_breakdown(l1, l2, l3), "inline": False},
            {"name": "매수가", "value": f"${price:,.2f}", "inline": True},
            {"name": "수량", "value": f"{s.get('shares', 0)}주", "inline": True},
            {"name": "투자금", "value": f"${s.get('amount', 0):,.0f} ({s.get('weight', 0):.1f}%)", "inline": True},
            {"name": "손절가", "value": f"${s.get('stop_loss', 0):,.2f} (-{s.get('stop_pct', 10)}%)", "inline": True},
            {"name": "섹터", "value": s.get("sector", "N/A"), "inline": True},
        ]

        because_text = '\n'.join(because_lines)
        embeds.append({
            "title": f"■ {_tn(ticker)}",
            "description": f"**투자 근거 (Because...)**\n{because_text}",
            "color": color,
            "fields": fields,
        })

    _send_discord(embeds[:10], "MY", "BUY")
    print(f"[NOTIFY] 🟢 MY_BUY → 투자근거카드 ({len(buy_signals)}건)")


def _send_buy_public(today_str: str, regime: str, buy_signals: list):
    """PUB_BUY: 종목 + 등급 + 매수가"""
    embeds = [{
        "title": f"🟢 매수 시그널 ({len(buy_signals)}건) — {today_str}",
        "description": f"국면: {_regime_text(regime)}",
        "color": C.GREEN,
        "footer": {"text": f"{FOOTER_BASE} | 매수 시그널"},
    }]

    for s in buy_signals[:8]:
        embeds.append({
            "title": f"■ {_tn(s['ticker'])}",
            "description": f"등급 **{s.get('grade', '?')}** | {s.get('score', 0):.1f}점 | 매수가 **${s.get('price', 0):,.2f}**",
            "color": _GRADE_COLOR.get(s.get("grade", ""), C.GREEN),
        })

    _send_discord(embeds[:10], "PUB", "BUY")
    print(f"[NOTIFY] 🟢 PUB_BUY → 종목+등급+매수가 ({len(buy_signals)}건)")


def _send_sell_premium(today_str: str, sell_signals: list):
    """MY_SELL: MAE/MFE + 점수변화"""
    stop_cnt = sum(1 for s in sell_signals if s.get("pnl_pct", 0) < 0)
    profit_cnt = len(sell_signals) - stop_cnt

    embeds = [{
        "title": f"🔴 매도 시그널 ({len(sell_signals)}건) — {today_str}",
        "description": f"손절 {stop_cnt}건 | 익절 {profit_cnt}건",
        "color": C.RED,
        "footer": {"text": f"{FOOTER_BASE} | 매도 시그널"},
    }]

    for s in sell_signals[:6]:
        ticker = s["ticker"]
        reason = s.get("reason", "UNKNOWN")
        pnl = s.get("pnl_pct", 0)
        entry = s.get("entry_price", 0)
        price = s.get("price", 0)
        high = s.get("highest_price", price)
        low = s.get("lowest_price", price)
        days = s.get("holding_days", 0)

        mfe = ((high - entry) / entry * 100) if entry > 0 else 0
        mae = ((low - entry) / entry * 100) if entry > 0 else 0
        from_high = ((price - high) / high * 100) if high > 0 else 0

        entry_score = s.get("entry_score", 0)
        curr_score = s.get("current_score", 0)
        entry_grade = s.get("entry_grade", "?")
        curr_grade = s.get("current_grade", "?")
        score_delta = _delta_arrow(entry_score, curr_score) if entry_score > 0 else ""

        color = C.GREEN if pnl >= 0 else C.RED

        fields = [
            {"name": "사유", "value": f"`{reason}`", "inline": True},
            {"name": "보유일", "value": f"{days}일", "inline": True},
            {"name": "수익률", "value": f"{_pnl_emoji(pnl)} **{pnl:+.1f}%**", "inline": True},
            {"name": "매입가", "value": f"${entry:,.2f}", "inline": True},
            {"name": "고점", "value": f"${high:,.2f}", "inline": True},
            {"name": "매도가", "value": f"${price:,.2f}", "inline": True},
        ]

        if entry > 0:
            fields.append({
                "name": "📊 MAE/MFE",
                "value": (
                    f"MFE(최대수익): `{mfe:+.1f}%`\n"
                    f"MAE(최대역행): `{mae:+.1f}%`\n"
                    f"고점 대비: `{from_high:+.1f}%`"
                ),
                "inline": False,
            })

        if entry_score > 0:
            fields.append({
                "name": "📉 점수 변화",
                "value": f"매입: {entry_score:.0f}점({entry_grade}) → 현재: {curr_score:.0f}점({curr_grade}) {score_delta}",
                "inline": False,
            })

        embeds.append({
            "title": f"■ {_tn(ticker)}",
            "color": color,
            "fields": fields,
        })

    _send_discord(embeds[:10], "MY", "SELL")
    print(f"[NOTIFY] 🔴 MY_SELL → MAE/MFE ({len(sell_signals)}건)")


def _send_sell_public(today_str: str, sell_signals: list):
    """PUB_SELL: 사유 + 매도가"""
    embeds = [{
        "title": f"🔴 매도 시그널 ({len(sell_signals)}건) — {today_str}",
        "color": C.RED,
        "footer": {"text": f"{FOOTER_BASE} | 매도 시그널"},
    }]

    for s in sell_signals[:8]:
        pnl = s.get("pnl_pct", 0)
        embeds.append({
            "title": f"■ {_tn(s['ticker'])}",
            "description": f"사유: `{s.get('reason', 'UNKNOWN')}` | 매도가 **${s.get('price', 0):,.2f}** | {_pnl_emoji(pnl)} {pnl:+.1f}%",
            "color": C.GREEN if pnl >= 0 else C.RED,
        })

    _send_discord(embeds[:10], "PUB", "SELL")
    print(f"[NOTIFY] 🔴 PUB_SELL → 사유+매도가 ({len(sell_signals)}건)")


def _send_profit_premium(today_str: str, sell_signals: list):
    """MY_PROFIT: pnl >= 0 익절만 분리"""
    profit_only = [s for s in sell_signals if s.get("pnl_pct", 0) >= 0]
    if not profit_only:
        return

    total_profit = sum(
        abs(s.get("price", 0) - s.get("entry_price", 0)) * s.get("shares", 1)
        for s in profit_only
    )

    embeds = [{
        "title": f"💰 수익 실현 ({len(profit_only)}건) — {today_str}",
        "description": f"총 수익: **+{_format_money(total_profit)}** 🎉",
        "color": C.GREEN,
        "footer": {"text": f"{FOOTER_BASE} | 수익 실현"},
    }]

    for s in profit_only[:6]:
        embeds.append({
            "title": f"■ {_tn(s['ticker'])}",
            "description": (
                f"보유 {s.get('holding_days', 0)}일 | "
                f"수익률 **{s.get('pnl_pct', 0):+.1f}%** 🚀\n"
                f"매입 ${s.get('entry_price', 0):,.2f} → 매도 ${s.get('price', 0):,.2f}"
            ),
            "color": C.GREEN,
        })

    _send_discord(embeds[:10], "MY", "PROFIT")
    print(f"[NOTIFY] 💰 MY_PROFIT → 익절 분리 ({len(profit_only)}건)")


# ═══════════════════════════════════════════════════════════
#  3. ADD — 추가 매수 → MY_ADD
# ═══════════════════════════════════════════════════════════

def notify_add_position(calc_date: date, add_signals: list):
    if not add_signals:
        return

    embeds = [{
        "title": f"📈 추가 매수 ({len(add_signals)}건) — {calc_date}",
        "color": C.YELLOW,
        "footer": {"text": f"{FOOTER_BASE} | 추가 매수"},
    }]

    for s in add_signals[:6]:
        embeds.append({
            "title": f"■ {_tn(s['ticker'])}",
            "description": (
                f"등급 **{s.get('grade', '?')}** | {s.get('score', 0):.1f}점 | "
                f"현재 수익률 {s.get('pnl_pct', 0):+.1f}%"
            ),
            "color": C.YELLOW,
            "fields": [
                {"name": "추가 수량", "value": f"{s.get('shares', 0)}주", "inline": True},
                {"name": "매수가", "value": f"${s.get('price', 0):,.2f}", "inline": True},
                {"name": "평단 개선", "value": f"{s.get('avg_down_pct', 0):+.1f}%", "inline": True},
            ],
        })

    embeds.append({"description": "⚠️ 손절가 재설정 필요", "color": C.YELLOW})
    _send_discord(embeds[:10], "MY", "ADD")
    print(f"[NOTIFY] 📈 MY_ADD → 추가 매수 ({len(add_signals)}건)")


# ═══════════════════════════════════════════════════════════
#  4. FIRE — 긴급 매도 → MY_FIRE
# ═══════════════════════════════════════════════════════════

def notify_fire_sell(calc_date: date, fire_signals: list, trigger: str = ""):
    if not fire_signals:
        return

    total_loss = sum(
        abs(s.get("price", 0) - s.get("entry_price", 0)) * s.get("shares", 0)
        for s in fire_signals
    )

    embeds = [{
        "title": f"🚨 긴급 매도 ({len(fire_signals)}건) — {calc_date}",
        "description": (
            f"⚡ 트리거: **{trigger or 'CIRCUIT_BREAKER / DD 경보'}**\n"
            f"💸 총 예상 손실: **-{_format_money(total_loss)}**"
        ),
        "color": 0xdc2626,
        "footer": {"text": f"{FOOTER_BASE} | 긴급 매도"},
    }]

    for s in fire_signals[:6]:
        loss = abs(s.get("price", 0) - s.get("entry_price", 0)) * s.get("shares", 0)
        embeds.append({
            "title": f"■ {_tn(s['ticker'])}",
            "description": f"사유: `{s.get('reason', 'CIRCUIT_BREAKER')}` | {s.get('pnl_pct', 0):+.1f}%",
            "color": 0xdc2626,
            "fields": [
                {"name": "매입가", "value": f"${s.get('entry_price', 0):,.2f}", "inline": True},
                {"name": "현재가", "value": f"${s.get('price', 0):,.2f}", "inline": True},
                {"name": "예상 손실", "value": f"-{_format_money(loss)}", "inline": True},
            ],
        })

    embeds.append({"description": "⚠️ 즉시 확인 필요", "color": 0xdc2626})
    _send_discord(embeds[:10], "MY", "FIRE")
    print(f"[NOTIFY] 🚨 MY_FIRE → 긴급 매도 ({len(fire_signals)}건)")


# ═══════════════════════════════════════════════════════════
#  5. BOUNCE — 반등 기회 → MY_BOUNCE
# ═══════════════════════════════════════════════════════════

def notify_bounce_opportunity(calc_date: date, bounce_signals: list):
    if not bounce_signals:
        return

    embeds = [{
        "title": f"🔵 반등 기회 ({len(bounce_signals)}건) — {calc_date}",
        "description": "RSI 과매도 + 지지선 부근 종목",
        "color": C.CYAN,
        "footer": {"text": f"{FOOTER_BASE} | 반등 기회"},
    }]

    for s in bounce_signals[:6]:
        fields = [
            {"name": "RSI", "value": f"{s.get('rsi', 0):.1f}", "inline": True},
            {"name": "현재가", "value": f"${s.get('price', 0):,.2f}", "inline": True},
            {"name": "등급", "value": s.get("grade", "?"), "inline": True},
        ]
        if s.get("support_price"):
            fields.append({"name": "지지선", "value": f"${s['support_price']:,.2f}", "inline": True})
        if s.get("drop_pct"):
            fields.append({"name": "하락폭", "value": f"{s['drop_pct']:+.1f}%", "inline": True})

        embeds.append({
            "title": f"■ {_tn(s['ticker'])}",
            "color": C.CYAN,
            "fields": fields,
        })

    _send_discord(embeds[:10], "MY", "BOUNCE")
    print(f"[NOTIFY] 🔵 MY_BOUNCE → 반등 기회 ({len(bounce_signals)}건)")


# ═══════════════════════════════════════════════════════════
#  6. RISK — 리스크 경고
#     MY_RISK: VaR + Stress + 집중도 + 상관 + 방어상태
#     PUB_RISK: 시장 상황 요약
# ═══════════════════════════════════════════════════════════

def notify_risk_warning(
    calc_date: date,
    risk_level: str = "YELLOW",
    drawdown: dict = None,
    var_data: dict = None,
    concentration: dict = None,
    defense_status: dict = None,
    stress_test: dict = None,
    correlation: dict = None,
):
    today_str = calc_date.strftime("%Y-%m-%d")
    dd = drawdown or {}
    vr = var_data or {}
    conc = concentration or {}
    defense = defense_status or {}
    stress = stress_test or {}
    corr = correlation or {}

    level_color = {"GREEN": C.GREEN, "YELLOW": C.YELLOW, "ORANGE": C.ORANGE, "RED": C.RED}.get(risk_level.upper(), C.YELLOW)
    level_emoji = {"GREEN": "🟢", "YELLOW": "🟡", "ORANGE": "🟠", "RED": "🔴"}.get(risk_level.upper(), "⚠️")

    # ── MY_RISK (풀 대시보드) ──
    my_fields = [
        {"name": "리스크 수준", "value": f"{level_emoji} **{risk_level}**", "inline": True},
    ]

    if dd:
        my_fields.extend([
            {"name": "현재 DD", "value": f"{dd.get('current_dd', 0):+.1f}%", "inline": True},
            {"name": "DD 경과", "value": f"{dd.get('dd_days', 0)}일", "inline": True},
            {"name": "MDD", "value": f"{dd.get('mdd', 0):.1f}%", "inline": True},
        ])

    if vr:
        my_fields.extend([
            {"name": "🌊 VaR 95%",
             "value": f"{_format_money(abs(vr.get('var_95_dollar', 0)))} ({vr.get('var_95_pct', 0):+.1f}%)",
             "inline": True},
            {"name": "🌊 VaR 99%",
             "value": f"{_format_money(abs(vr.get('var_99_dollar', 0)))} ({vr.get('var_99_pct', 0):+.1f}%)",
             "inline": True},
        ])

    if stress:
        lines = [f"▸ {name}: {res.get('impact_pct', 0):+.1f}%" for name, res in list(stress.items())[:4]]
        my_fields.append({"name": "💥 Stress Test", "value": "\n".join(lines), "inline": False})

    if conc:
        conc_lines = []
        ts = conc.get("top_sector", {})
        if ts:
            pct, limit = ts.get("pct", 0), ts.get("limit", 35)
            conc_lines.append(f"섹터: {ts.get('name', '?')} {pct:.0f}% (한도 {limit}%) {'🔴 초과' if pct > limit else '✅'}")
        tk = conc.get("top_stock", {})
        if tk:
            pct, limit = tk.get("pct", 0), tk.get("limit", 10)
            conc_lines.append(f"종목: {tk.get('ticker', '?')} {pct:.1f}% (한도 {limit}%) {'🔴 초과' if pct > limit else '✅'}")
        if conc_lines:
            my_fields.append({"name": "🔗 집중도", "value": "\n".join(conc_lines), "inline": False})

    if corr:
        avg = corr.get("avg_correlation", 0)
        text = f"포폴 평균: `{avg:.2f}` {'⚠️ 높음' if avg > 0.6 else '✅'}"
        if corr.get("top_pair"):
            text += f"\nTop: {corr['top_pair']}"
        my_fields.append({"name": "📊 상관관계", "value": text, "inline": False})

    if defense:
        d_lines = [
            f"DD Controller: **{defense.get('dd_mode', 'NORMAL')}**",
            f"Circuit Breaker: **{'ON 🔴' if defense.get('cb_active') else 'OFF ✅'}**",
        ]
        if defense.get("buy_limit_pct"):
            d_lines.append(f"신규 매수 한도: {defense['buy_limit_pct']}%")
        my_fields.append({"name": "🛡️ 자동 방어", "value": "\n".join(d_lines), "inline": False})

    _send_discord([{
        "title": f"⚠️ 리스크 대시보드 — {today_str}",
        "color": level_color,
        "fields": my_fields,
        "footer": {"text": f"{FOOTER_BASE} | 리스크 대시보드"},
    }], "MY", "RISK")
    print(f"[NOTIFY] ⚠️ MY_RISK → 풀 대시보드 ({risk_level})")

    # ── PUB_RISK (시장 상황) ──
    pub_lines = [f"리스크 수준: {level_emoji} **{risk_level}**"]
    if dd:
        pub_lines.append(f"포폴 DD: `{dd.get('current_dd', 0):+.1f}%` (MDD `{dd.get('mdd', 0):.1f}%`)")
    if defense:
        pub_lines.append(f"방어모드: **{defense.get('dd_mode', 'NORMAL')}** | CB: {'ON 🔴' if defense.get('cb_active') else 'OFF ✅'}")

    _send_discord([{
        "title": f"⚠️ 시장 리스크 — {today_str}",
        "description": "\n".join(pub_lines),
        "color": level_color,
        "footer": {"text": f"{FOOTER_BASE} | 리스크"},
    }], "PUB", "RISK")
    print(f"[NOTIFY] ⚠️ PUB_RISK → 시장 상황 ({risk_level})")


# ═══════════════════════════════════════════════════════════
#  7. REPORT 계열 — 공개채널 PUB_REPORT로 통합 전송
#     7a. 등급 변경 → MY_ALERT + PUB_REPORT
#     7b. 국면 전환 → MY_ALERT + PUB_REPORT
#     7c. 주간 리포트 → MY_REPORT + PUB_REPORT
#     7d. 배치 시작 → MY_SYSTEM + PUB_REPORT
#     7e. 배치 완료 → MY_SYSTEM + PUB_REPORT
# ═══════════════════════════════════════════════════════════

# 7a. 등급 변경
def notify_grade_changes(calc_date: date, changes: list):
    if not changes:
        return

    today_str = calc_date.strftime("%Y-%m-%d")
    upgrades = [c for c in changes if _grade_rank(c.get("new_grade", "")) > _grade_rank(c.get("old_grade", ""))]
    downgrades = [c for c in changes if _grade_rank(c.get("new_grade", "")) < _grade_rank(c.get("old_grade", ""))]

    # ── MY_ALERT (상세) ──
    my_embeds = [{
        "title": f"🔔 등급 변경 ({len(changes)}건) — {today_str}",
        "description": f"⬆️ 상향 {len(upgrades)}건 | ⬇️ 하향 {len(downgrades)}건",
        "color": C.BLUE,
        "footer": {"text": f"{FOOTER_BASE} | 등급 변경"},
    }]

    for c in changes[:8]:
        old_g, new_g = c.get("old_grade", "?"), c.get("new_grade", "?")
        is_up = _grade_rank(new_g) > _grade_rank(old_g)
        arrow = "⬆️" if is_up else "⬇️"
        color = C.GREEN if is_up else C.RED

        fields = [
            {"name": "등급", "value": f"{old_g} → **{new_g}** {arrow}", "inline": True},
            {"name": "점수", "value": f"{c.get('old_score', 0):.1f} → {c.get('new_score', 0):.1f}", "inline": True},
        ]
        if c.get("reason"):
            fields.append({"name": "사유", "value": c["reason"], "inline": False})

        my_embeds.append({
            "title": f"■ {_tn(c.get('ticker', '?'))}",
            "color": color,
            "fields": fields,
        })

    _send_discord(my_embeds[:10], "MY", "ALERT")
    print(f"[NOTIFY] 🔔 MY_ALERT → 등급 변경 ({len(changes)}건)")

    # ── PUB_REPORT (요약) ──
    summary = []
    if upgrades:
        tickers = ", ".join([f"**{c.get('ticker', '?')}**({c.get('new_grade', '?')})" for c in upgrades[:5]])
        summary.append(f"⬆️ 상향: {tickers}")
    if downgrades:
        tickers = ", ".join([f"**{c.get('ticker', '?')}**({c.get('new_grade', '?')})" for c in downgrades[:5]])
        summary.append(f"⬇️ 하향: {tickers}")

    _send_discord([{
        "title": f"🔔 등급 변경 ({len(changes)}건) — {today_str}",
        "description": "\n".join(summary) or "변경 내역 확인",
        "color": C.BLUE,
        "footer": {"text": f"{FOOTER_BASE} | 등급 변경"},
    }], "PUB", "REPORT")
    print(f"[NOTIFY] 🔔 PUB_REPORT → 등급 변경 요약")


# 7b. 국면 전환
def notify_regime_change(
    calc_date: date,
    old_regime: str,
    new_regime: str,
    trigger_detail: dict = None,
):
    today_str = calc_date.strftime("%Y-%m-%d")
    old_e = _REGIME_EMOJI.get(old_regime.upper(), "⚪")
    new_e = _REGIME_EMOJI.get(new_regime.upper(), "⚪")
    color = _REGIME_COLOR.get(new_regime.upper(), C.BLUE)
    detail = trigger_detail or {}

    # ── MY_ALERT (상세) ──
    my_fields = [
        {"name": "전환", "value": f"{old_e} {old_regime} → {new_e} **{new_regime}**", "inline": False},
    ]
    if detail.get("spy_price"):
        my_fields.append({"name": "SPY", "value": f"${detail['spy_price']:,.2f}", "inline": True})
    if detail.get("vix_close"):
        my_fields.append({"name": "VIX", "value": f"{detail['vix_close']:.1f}", "inline": True})
    if detail.get("trigger_reason"):
        my_fields.append({"name": "트리거", "value": detail["trigger_reason"], "inline": False})
    if detail.get("impact"):
        my_fields.append({"name": "영향", "value": detail["impact"], "inline": False})

    _send_discord([{
        "title": f"🔄 국면 전환 — {today_str}",
        "color": color,
        "fields": my_fields,
        "footer": {"text": f"{FOOTER_BASE} | 국면 전환"},
    }], "MY", "ALERT")
    print(f"[NOTIFY] 🔄 MY_ALERT → 국면 전환 ({old_regime}→{new_regime})")

    # ── PUB_REPORT ──
    _send_discord([{
        "title": f"🔄 국면 전환 — {today_str}",
        "description": f"{old_e} {old_regime} → {new_e} **{new_regime}**",
        "color": color,
        "footer": {"text": f"{FOOTER_BASE} | 국면 전환"},
    }], "PUB", "REPORT")
    print(f"[NOTIFY] 🔄 PUB_REPORT → 국면 전환")


# 7c. 주간 리포트
def notify_weekly_report(
    calc_date: date,
    week_return: float = 0,
    mtd_return: float = 0,
    ytd_return: float = 0,
    since_inception: float = 0,
    sharpe: float = 0,
    sortino: float = 0,
    alpha: float = 0,
    beta: float = 0,
    win_rate: float = 0,
    num_trades: int = 0,
    best_ticker: str = "",
    best_pnl: float = 0,
    worst_ticker: str = "",
    worst_pnl: float = 0,
    brinson: dict = None,
):
    today_str = calc_date.strftime("%Y-%m-%d")
    brs = brinson or {}
    color = C.GREEN if week_return >= 0 else C.RED

    # ── MY_REPORT (Brinson 분해 + Risk-Adjusted) ──
    my_fields = [
        {"name": "주간", "value": f"**{week_return:+.2f}%**", "inline": True},
        {"name": "MTD", "value": f"{mtd_return:+.2f}%", "inline": True},
        {"name": "YTD", "value": f"{ytd_return:+.2f}%", "inline": True},
        {"name": "Inception", "value": f"{since_inception:+.2f}%", "inline": True},
        {"name": "Sharpe", "value": f"{sharpe:.2f}", "inline": True},
        {"name": "Sortino", "value": f"{sortino:.2f}", "inline": True},
        {"name": "Alpha (vs SPY)", "value": f"{alpha:+.2f}%", "inline": True},
        {"name": "Beta", "value": f"{beta:.2f}", "inline": True},
        {"name": "승률", "value": f"{win_rate:.1f}%", "inline": True},
        {"name": "거래 수", "value": f"{num_trades}건", "inline": True},
    ]
    if best_ticker:
        my_fields.append({"name": "🏆 MVP", "value": f"{_tn_short(best_ticker)} ({best_pnl:+.1f}%)", "inline": True})
    if worst_ticker:
        my_fields.append({"name": "💀 Worst", "value": f"{_tn_short(worst_ticker)} ({worst_pnl:+.1f}%)", "inline": True})

    if brs:
        my_fields.append({"name": "📊 수익 분해 (Brinson)", "value": (
            f"총 수익: **{week_return:+.2f}%**\n"
            f"├─ 시장 효과(β): `{brs.get('market_effect', 0):+.2f}%`\n"
            f"├─ 종목선택(α): `{brs.get('selection_effect', 0):+.2f}%`\n"
            f"└─ 현금 드래그: `{brs.get('cash_drag', 0):+.2f}%`"
        ), "inline": False})

    _send_discord([{
        "title": f"📊 주간 리포트 — {today_str}",
        "color": color,
        "fields": my_fields,
        "footer": {"text": f"{FOOTER_BASE} | 주간 리포트"},
    }], "MY", "REPORT")
    print(f"[NOTIFY] 📊 MY_REPORT → 주간 리포트 ({week_return:+.2f}%)")

    # ── PUB_REPORT (간결) ──
    _send_discord([{
        "title": f"📊 주간 리포트 — {today_str}",
        "description": (
            f"주간 수익률: **{week_return:+.2f}%** | 승률: **{win_rate:.0f}%**\n"
            f"거래 {num_trades}건 | YTD {ytd_return:+.2f}%"
        ),
        "color": color,
        "footer": {"text": f"{FOOTER_BASE} | 주간 리포트"},
    }], "PUB", "REPORT")
    print(f"[NOTIFY] 📊 PUB_REPORT → 주간 리포트 (간결)")


# 7d. 배치 시작
def notify_batch_start(calc_date: date, job_name: str = "Daily Batch"):
    today_str = calc_date.strftime("%Y-%m-%d")
    now_str = datetime.now().strftime("%H:%M:%S")

    _send_discord([{
        "title": f"🔄 배치 시작 — {today_str}",
        "description": f"작업: **{job_name}**\n시작: `{now_str}`",
        "color": C.PURPLE,
        "footer": {"text": f"{FOOTER_BASE} | 시스템"},
    }], "MY", "SYSTEM")

    _send_discord([{
        "title": f"🔄 배치 시작 — {today_str}",
        "description": f"작업: **{job_name}** | 시작: `{now_str}`",
        "color": C.PURPLE,
        "footer": {"text": f"{FOOTER_BASE} | 시스템"},
    }], "PUB", "REPORT")
    print(f"[NOTIFY] 🔄 배치 시작 → MY_SYSTEM + PUB_REPORT")


# 7e. 배치 완료
def notify_batch_complete(
    calc_date: date,
    duration_sec: float = 0,
    results: dict = None,
    job_name: str = "Daily Batch",
):
    today_str = calc_date.strftime("%Y-%m-%d")
    res = results or {}

    mins = int(duration_sec // 60)
    secs = int(duration_sec % 60)
    duration_str = f"{mins}분 {secs}초" if mins > 0 else f"{secs}초"

    success = res.get("success", 0)
    fail = res.get("fail", 0)
    total = res.get("total", success + fail)
    ok = fail == 0
    emoji = "✅" if ok else "⚠️"

    # ── MY_SYSTEM (상세) ──
    my_fields = [
        {"name": "작업", "value": job_name, "inline": True},
        {"name": "소요시간", "value": duration_str, "inline": True},
        {"name": "결과", "value": f"{emoji} {success}/{total} 성공", "inline": True},
    ]

    steps = res.get("steps", {})
    if steps:
        step_lines = []
        for sn, sr in steps.items():
            s_e = "✅" if sr.get("ok") else "❌"
            s_t = sr.get("duration", "")
            step_lines.append(f"{s_e} {sn} {f'({s_t})' if s_t else ''}")
        my_fields.append({"name": "📋 단계별 결과", "value": "\n".join(step_lines[:10]), "inline": False})

    if fail > 0:
        errors = res.get("errors", [])
        if errors:
            my_fields.append({"name": "❌ 실패 항목", "value": "\n".join(errors[:5]), "inline": False})

    _send_discord([{
        "title": f"{emoji} 배치 완료 — {today_str}",
        "color": C.GREEN if ok else C.YELLOW,
        "fields": my_fields,
        "footer": {"text": f"{FOOTER_BASE} | 시스템"},
    }], "MY", "SYSTEM")
    print(f"[NOTIFY] {emoji} MY_SYSTEM → 배치 완료 ({duration_str})")

    # ── PUB_REPORT (간결) ──
    _send_discord([{
        "title": f"{emoji} 배치 완료 — {today_str}",
        "description": (
            f"작업: **{job_name}**\n"
            f"소요시간: `{duration_str}` | 결과: {emoji} **{success}/{total}** 성공"
        ),
        "color": C.GREEN if ok else C.YELLOW,
        "footer": {"text": f"{FOOTER_BASE} | 시스템"},
    }], "PUB", "REPORT")
    print(f"[NOTIFY] {emoji} PUB_REPORT → 배치 완료 (간결)")


# ═══════════════════════════════════════════════════════════
#  8. PERF — 일일 성과 → MY_PERF
# ═══════════════════════════════════════════════════════════

def notify_daily_performance(
    calc_date: date,
    daily_return: float = 0,
    total_value: float = 0,
    spy_return: float = 0,
    num_positions: int = 0,
    top_gainer: dict = None,
    top_loser: dict = None,
    sector_perf: dict = None,
):
    today_str = calc_date.strftime("%Y-%m-%d")
    alpha = daily_return - spy_return
    emoji = "📈" if daily_return >= 0 else "📉"

    fields = [
        {"name": "일간 수익률", "value": f"**{daily_return:+.2f}%**", "inline": True},
        {"name": "SPY", "value": f"{spy_return:+.2f}%", "inline": True},
        {"name": "Alpha", "value": f"{alpha:+.2f}%", "inline": True},
        {"name": "총 자산", "value": _format_money(total_value), "inline": True},
        {"name": "포지션", "value": f"{num_positions}개", "inline": True},
    ]

    if top_gainer:
        fields.append({
            "name": "🏆 Top",
            "value": f"{_tn_short(top_gainer.get('ticker', '?'))} {top_gainer.get('pnl', 0):+.1f}%",
            "inline": True,
        })
    if top_loser:
        fields.append({
            "name": "💀 Worst",
            "value": f"{_tn_short(top_loser.get('ticker', '?'))} {top_loser.get('pnl', 0):+.1f}%",
            "inline": True,
        })
    if sector_perf:
        lines = [f"{k}: {v:+.1f}%" for k, v in list(sector_perf.items())[:5]]
        fields.append({"name": "📊 섹터 성과", "value": "\n".join(lines), "inline": False})

    _send_discord([{
        "title": f"{emoji} 일일 성과 — {today_str}",
        "color": C.GREEN if daily_return >= 0 else C.RED,
        "fields": fields,
        "footer": {"text": f"{FOOTER_BASE} | 일일 성과"},
    }], "MY", "PERF")
    print(f"[NOTIFY] {emoji} MY_PERF → 일일 성과 ({daily_return:+.2f}%)")


# ═══════════════════════════════════════════════════════════
#  9. 기타 Premium 전용 알림
# ═══════════════════════════════════════════════════════════

def notify_earnings_alert(calc_date: date, tickers: list, days_until: int = 3):
    if not tickers:
        return

    embeds = [{
        "title": f"📅 어닝 임박 ({len(tickers)}건) — {calc_date}",
        "description": f"{days_until}일 이내 실적 발표 예정",
        "color": C.ORANGE,
        "footer": {"text": f"{FOOTER_BASE} | 어닝 알림"},
    }]

    for t in tickers[:8]:
        ticker = t if isinstance(t, str) else t.get("ticker", "?")
        dt = t.get("date", "") if isinstance(t, dict) else ""
        embeds.append({
            "description": f"▸ {_tn(ticker)} — {dt}",
            "color": C.ORANGE,
        })

    _send_discord(embeds[:10], "MY", "ALERT")
    print(f"[NOTIFY] 📅 MY_ALERT → 어닝 임박 ({len(tickers)}건)")


def notify_emergency(calc_date: date, message: str, severity: str = "HIGH"):
    color = C.RED if severity == "HIGH" else C.ORANGE
    _send_discord([{
        "title": f"🚨 긴급 알림 — {calc_date}",
        "description": f"**[{severity}]** {message}",
        "color": color,
        "footer": {"text": f"{FOOTER_BASE} | 긴급"},
    }], "MY", "FIRE")
    print(f"[NOTIFY] 🚨 MY_FIRE → 긴급 ({severity})")


def notify_weekly_rebalance(calc_date: date, rebalance_data: list):
    if not rebalance_data:
        return

    embeds = [{
        "title": f"🔄 주간 리밸런싱 — {calc_date}",
        "description": f"{len(rebalance_data)}건 비중 조정",
        "color": C.BLUE,
        "footer": {"text": f"{FOOTER_BASE} | 리밸런싱"},
    }]

    for r in rebalance_data[:8]:
        embeds.append({
            "title": f"■ {_tn(r.get('ticker', '?'))}",
            "description": (
                f"비중: {r.get('old_weight', 0):.1f}% → **{r.get('new_weight', 0):.1f}%**\n"
                f"조정: {r.get('action', 'ADJUST')} {r.get('shares', 0)}주"
            ),
            "color": C.BLUE,
        })

    _send_discord(embeds[:10], "MY", "REPORT")
    print(f"[NOTIFY] 🔄 MY_REPORT → 리밸런싱 ({len(rebalance_data)}건)")


def notify_backtest_result(
    period_start: date, period_end: date,
    strategy_name: str = "QUANT AI v4.0 Multi-Factor",
    total_return: float = 0, annual_return: float = 0,
    max_drawdown: float = 0, sharpe_ratio: float = 0,
    win_rate: float = 0, spy_alpha: float = 0,
    num_trades: int = 0, avg_holding_days: int = 0,
):
    _send_discord([{
        "title": f"🧪 백테스트 완료 — {period_start} ~ {period_end}",
        "description": f"전략: {strategy_name}",
        "color": C.PURPLE,
        "fields": [
            {"name": "총 수익률", "value": f"{total_return:+.1f}%", "inline": True},
            {"name": "연환산", "value": f"{annual_return:+.1f}%", "inline": True},
            {"name": "최대 낙폭", "value": f"{max_drawdown:.1f}%", "inline": True},
            {"name": "샤프", "value": f"{sharpe_ratio:.2f}", "inline": True},
            {"name": "승률", "value": f"{win_rate:.1f}%", "inline": True},
            {"name": "SPY α", "value": f"{spy_alpha:+.1f}%", "inline": True},
            {"name": "거래 수", "value": f"{num_trades}건", "inline": True},
            {"name": "평균 보유", "value": f"{avg_holding_days}일", "inline": True},
        ],
        "footer": {"text": f"{FOOTER_BASE} | 백테스트"},
    }], "MY", "BACKTEST")
    print(f"[NOTIFY] 🧪 MY_BACKTEST → 백테스트 ({total_return:+.1f}%)")


# ═══════════════════════════════════════════════════════════
#  10. 데이터 품질 → MY_SYSTEM
# ═══════════════════════════════════════════════════════════

def notify_price_fetch_failure(tickers: list, source: str = "FMP"):
    if not tickers:
        return
    _send_discord([{
        "title": f"❌ 가격 수집 실패 ({len(tickers)}건)",
        "description": f"소스: {source}\n종목: {', '.join(tickers[:20])}",
        "color": C.RED,
        "footer": {"text": f"{FOOTER_BASE} | 데이터 품질"},
    }], "MY", "SYSTEM")
    print(f"[NOTIFY] ❌ MY_SYSTEM → 가격 수집 실패 ({len(tickers)}건)")


def check_price_freshness(stale_tickers: list, threshold_hours: int = 24):
    if not stale_tickers:
        return
    _send_discord([{
        "title": f"⚠️ 가격 데이터 노후 ({len(stale_tickers)}건)",
        "description": f"기준: {threshold_hours}시간 이상 미갱신\n{', '.join(stale_tickers[:20])}",
        "color": C.YELLOW,
        "footer": {"text": f"{FOOTER_BASE} | 데이터 품질"},
    }], "MY", "SYSTEM")
    print(f"[NOTIFY] ⚠️ MY_SYSTEM → 데이터 노후 ({len(stale_tickers)}건)")


# ═══════════════════════════════════════════════════════════
#  하위 호환 래퍼 (v3.6 → v4.0)
# ═══════════════════════════════════════════════════════════

def send_message(text: str, signal_type: str = "REPORT"):
    """v3 호환: 단순 텍스트 전송"""
    _send_discord(
        [{"description": text[:4000], "color": C.BLUE, "footer": {"text": f"{FOOTER_BASE} | {signal_type}"}}],
        "MY", signal_type,
    )


def send_discord_embed(embeds: list, signal_type: str = "REPORT"):
    """v3 호환: 직접 embed 전송"""
    _send_discord(embeds, "MY", signal_type)
