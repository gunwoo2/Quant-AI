"""
notifier.py — QUANT AI 8채널 알림 시스템 v3.4
================================================
Discord 채널별 웹후크 + Slack/Telegram 지원.

v3.4 변경:
  - ADD/FIRE/BOUNCE 채널 알림 함수 추가
  - 모닝 브리핑 강화
  - 일일 성과 리포트 추가
  - 등급 변경 알림 추가
  - 어닝 D-day 알림 추가
  - 리스크 경고 강화

.env 설정:
  DISCORD_WEBHOOK_BUY / SELL / PROFIT / ADD / FIRE / BOUNCE / REPORT / ALERT
  DISCORD_WEBHOOK_URL  (통합 fallback)
  NOTIFY_CHANNEL=discord
"""
import os
import logging
from datetime import datetime, date
from typing import List, Optional, Dict

import requests

logger = logging.getLogger("notifier")

# ── 설정 ──
SLACK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")
CHANNEL = os.environ.get("NOTIFY_CHANNEL", "discord").lower()

# ── Discord 채널별 웹후크 매핑 ──
_WEBHOOK_MAP = {
    "BUY":     os.environ.get("DISCORD_WEBHOOK_BUY", ""),
    "SELL":    os.environ.get("DISCORD_WEBHOOK_SELL", ""),
    "PROFIT":  os.environ.get("DISCORD_WEBHOOK_PROFIT", ""),
    "ADD":     os.environ.get("DISCORD_WEBHOOK_ADD", ""),
    "FIRE":    os.environ.get("DISCORD_WEBHOOK_FIRE", ""),
    "BOUNCE":  os.environ.get("DISCORD_WEBHOOK_BOUNCE", ""),
    "REPORT":  os.environ.get("DISCORD_WEBHOOK_REPORT", ""),
    "ALERT":   os.environ.get("DISCORD_WEBHOOK_ALERT", ""),
}
_FALLBACK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")


def _get_discord_url(signal_type: str = "REPORT") -> str:
    url = _WEBHOOK_MAP.get(signal_type.upper(), "")
    if url:
        return url
    if _FALLBACK_URL:
        return _FALLBACK_URL
    for v in _WEBHOOK_MAP.values():
        if v:
            return v
    return ""


# ═══════════════════════════════════════════════════════════
#  저수준 전송
# ═══════════════════════════════════════════════════════════

def _send_discord(content: str = None, embeds: list = None, signal_type: str = "REPORT") -> bool:
    url = _get_discord_url(signal_type)
    if not url:
        logger.warning(f"[NOTIFY] Discord 웹후크 미설정 (type={signal_type})")
        return False
    payload = {}
    if content:
        payload["content"] = content[:2000]
    if embeds:
        payload["embeds"] = embeds[:10]
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code in (200, 204):
            return True
        logger.error(f"[DISCORD/{signal_type}] {r.status_code}: {r.text[:200]}")
        return False
    except Exception as e:
        logger.error(f"[DISCORD/{signal_type}] 전송 실패: {e}")
        return False


def _send_slack(text: str) -> bool:
    if not SLACK_URL:
        return False
    try:
        r = requests.post(SLACK_URL, json={"text": text[:4000]}, timeout=10)
        return r.status_code == 200
    except Exception as e:
        logger.error(f"[SLACK] 전송 실패: {e}")
        return False


def _send_telegram(text: str) -> bool:
    if not TG_TOKEN or not TG_CHAT:
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT, "text": text[:4096], "parse_mode": "HTML"},
            timeout=10,
        )
        return r.status_code == 200
    except Exception as e:
        logger.error(f"[TELEGRAM] 전송 실패: {e}")
        return False


def send_message(text: str, signal_type: str = "REPORT"):
    if CHANNEL in ("discord", "all"):
        _send_discord(content=text, signal_type=signal_type)
    if CHANNEL in ("slack", "all"):
        _send_slack(text)
    if CHANNEL in ("telegram", "all"):
        _send_telegram(text)


def send_discord_embed(embeds: list, signal_type: str = "REPORT"):
    _send_discord(embeds=embeds, signal_type=signal_type)


def _embeds_to_text(embeds: list) -> str:
    parts = []
    for e in embeds:
        if "title" in e:
            parts.append(e["title"])
        if "description" in e:
            parts.append(e["description"])
        for f in e.get("fields", []):
            parts.append(f"{f['name']}: {f['value']}")
    return "\n".join(parts)


# ═══════════════════════════════════════════════════════════
#  1. 일일 시그널 알림 (BUY / SELL / PROFIT 채널)
# ═══════════════════════════════════════════════════════════

def notify_daily_signals(
    calc_date: date,
    regime: str,
    regime_detail: dict,
    buy_signals: list,
    sell_signals: list,
    portfolio_summary: dict,
):
    """일일 트레이딩 시그널 알림 — 매수/매도/익절 채널별 분리"""
    regime_emoji = {"BULL": "🟢", "NEUTRAL": "🟡", "BEAR": "🔴", "CRISIS": "🚨"}.get(regime, "⚪")
    spy_price = regime_detail.get("spy_price", 0)
    vix = regime_detail.get("vix_close", 0)

    header_embed = {
        "title": f"🤖 QUANT AI — 일일 시그널 ({calc_date})",
        "color": {"BULL": 0x22c55e, "NEUTRAL": 0xf59e0b, "BEAR": 0xef4444, "CRISIS": 0x7f1d1d}.get(regime, 0x888888),
        "fields": [
            {"name": "시장 국면", "value": f"{regime_emoji} **{regime}**", "inline": True},
            {"name": "SPY", "value": f"${spy_price:,.2f}", "inline": True},
            {"name": "VIX", "value": f"{vix:.1f}" if vix else "N/A", "inline": True},
        ],
        "footer": {"text": "QUANT AI v3.4 | 투자 참고용"},
    }

    port_embed = None
    if portfolio_summary:
        tv = portfolio_summary.get("total_value", 0)
        dr = portfolio_summary.get("daily_return", 0)
        vs = portfolio_summary.get("vs_spy", 0)
        np_ = portfolio_summary.get("num_positions", 0)
        cash = portfolio_summary.get("cash_pct", 0)
        port_embed = {
            "title": "💼 포트폴리오 현황",
            "fields": [
                {"name": "총 자산", "value": f"${tv:,.0f}", "inline": True},
                {"name": "오늘 수익", "value": f"{dr:+.2f}%", "inline": True},
                {"name": "vs SPY", "value": f"{vs:+.2f}%", "inline": True},
                {"name": "보유 종목", "value": f"{np_}개", "inline": True},
                {"name": "현금 비율", "value": f"{cash:.1f}%", "inline": True},
            ],
            "color": 0x3b82f6,
        }

    # ── BUY 시그널 → BUY 채널 ──
    if buy_signals:
        buy_lines = []
        for s in buy_signals[:8]:
            line = (
                f"**{s['ticker']}** {s.get('grade', '')} ({s['score']:.1f}점) "
                f"@ ${s['price']:,.2f}\n"
                f"→ {s['shares']}주 매수 | ${s['amount']:,.0f} | 비중 {s['weight']:.1f}%\n"
                f"→ 손절가: ${s['stop_loss']:,.2f}"
            )
            buy_lines.append(line)
        buy_embeds = [header_embed, {
            "title": f"🟢 돈 복사 시작 ({len(buy_signals)}건)",
            "description": "\n\n".join(buy_lines),
            "color": 0x22c55e,
        }]
        if port_embed:
            buy_embeds.append(port_embed)
        _send_discord(embeds=buy_embeds, signal_type="BUY")
        print(f"[NOTIFY] 🟢 매수 알림 → BUY 채널 ({len(buy_signals)}건)")

    # ── SELL 시그널 → SELL/PROFIT 채널 분리 ──
    if sell_signals:
        loss_signals = [s for s in sell_signals if s.get("pnl_pct", 0) < 0]
        profit_signals = [s for s in sell_signals if s.get("pnl_pct", 0) >= 0]

        if loss_signals:
            sell_lines = []
            for s in loss_signals[:8]:
                line = f"**{s['ticker']}** | {s.get('reason', 'SELL')} | 보유 {s.get('holding_days', 0)}일 | {s.get('pnl_pct', 0):+.1f}%"
                sell_lines.append(line)
            sell_embeds = [header_embed, {
                "title": f"🔴 탈출은 지능순 ({len(loss_signals)}건)",
                "description": "\n".join(sell_lines),
                "color": 0xef4444,
            }]
            _send_discord(embeds=sell_embeds, signal_type="SELL")
            print(f"[NOTIFY] 🔴 손절 알림 → SELL 채널 ({len(loss_signals)}건)")

        if profit_signals:
            profit_lines = []
            for s in profit_signals[:8]:
                gain = abs(s.get("price", 0) - s.get("entry_price", 0)) * s.get("shares", 0)
                line = f"**{s['ticker']}** | +{s.get('pnl_pct', 0):.1f}% | 💰 +${gain:,.0f} | 보유 {s.get('holding_days', 0)}일"
                profit_lines.append(line)
            profit_embeds = [header_embed, {
                "title": f"💰 수익 실현 ({len(profit_signals)}건)",
                "description": "\n".join(profit_lines),
                "color": 0xfbbf24,
            }]
            _send_discord(embeds=profit_embeds, signal_type="PROFIT")
            print(f"[NOTIFY] 💰 익절 알림 → PROFIT 채널 ({len(profit_signals)}건)")

    # 시그널 0건이면 REPORT 채널에 안내
    if not buy_signals and not sell_signals:
        no_signal_embed = [header_embed, {
            "title": "📋 오늘의 시그널: 없음",
            "description": "매수/매도 조건을 충족하는 종목이 없습니다.\n기존 포트폴리오 유지.",
            "color": 0x78716c,
        }]
        if port_embed:
            no_signal_embed.append(port_embed)
        _send_discord(embeds=no_signal_embed, signal_type="REPORT")
        print("[NOTIFY] 📋 시그널 없음 → REPORT 채널")


# ═══════════════════════════════════════════════════════════
#  2. 추가 매수 알림 (ADD 채널) ★ 신규
# ═══════════════════════════════════════════════════════════

def notify_add_position(calc_date: date, add_signals: list):
    """보유종목 추가 매수 (물타기/피라미딩) 알림 → ADD 채널"""
    if not add_signals:
        return

    lines = []
    for s in add_signals[:8]:
        avg_down = s.get("avg_down_pct", 0)
        line = (
            f"**{s['ticker']}** | 현재 {s.get('pnl_pct', 0):+.1f}% "
            f"| 등급 {s.get('grade', '?')} ({s.get('score', 0):.1f}점)\n"
            f"→ {s.get('shares', 0)}주 추가 @ ${s.get('price', 0):,.2f} "
            f"| 평단 {avg_down:+.1f}% 개선"
        )
        lines.append(line)

    embeds = [{
        "title": f"📈 추가 매수 ({len(add_signals)}건) — {calc_date}",
        "description": (
            "보유종목 중 점수 상승 + 가격 하락 → 물타기 기회\n\n"
            + "\n\n".join(lines)
        ),
        "color": 0xf59e0b,
        "footer": {"text": "기존 보유종목 비중 확대 | 손절가 재설정 필요"},
    }]
    _send_discord(embeds=embeds, signal_type="ADD")
    print(f"[NOTIFY] 📈 추가매수 알림 → ADD 채널 ({len(add_signals)}건)")


# ═══════════════════════════════════════════════════════════
#  3. 긴급 매도 알림 (FIRE 채널) ★ 신규
# ═══════════════════════════════════════════════════════════

def notify_fire_sell(calc_date: date, fire_signals: list, trigger: str = ""):
    """서킷브레이커/긴급 매도 알림 → FIRE 채널"""
    if not fire_signals:
        return

    lines = []
    total_loss = 0
    for s in fire_signals[:10]:
        loss = abs(s.get("price", 0) - s.get("entry_price", 0)) * s.get("shares", 0)
        total_loss += loss
        line = f"🔥 **{s['ticker']}** | {s.get('reason', 'EMERGENCY')} | {s.get('pnl_pct', 0):+.1f}% | -${loss:,.0f}"
        lines.append(line)

    embeds = [{
        "title": f"🚨 긴급 매도 발동 ({len(fire_signals)}건) — {calc_date}",
        "description": (
            f"**트리거: {trigger or '서킷브레이커/DD 경보'}**\n"
            f"총 예상 손실: **-${total_loss:,.0f}**\n\n"
            + "\n".join(lines)
        ),
        "color": 0xf97316,
        "footer": {"text": "⚠️ 즉시 확인 필요! 자동 매도 or 수동 확인"},
    }]
    _send_discord(embeds=embeds, signal_type="FIRE")
    print(f"[NOTIFY] 🚨 긴급매도 알림 → FIRE 채널 ({len(fire_signals)}건)")


# ═══════════════════════════════════════════════════════════
#  4. 반등 매수 알림 (BOUNCE 채널) ★ 신규
# ═══════════════════════════════════════════════════════════

def notify_bounce_opportunity(calc_date: date, bounce_signals: list):
    """급락 후 반등 매수 기회 알림 → BOUNCE 채널"""
    if not bounce_signals:
        return

    lines = []
    for s in bounce_signals[:8]:
        line = (
            f"🔄 **{s['ticker']}** | {s.get('grade', '?')} ({s.get('score', 0):.1f}점)\n"
            f"→ 7일 낙폭: {s.get('drop_7d', 0):+.1f}% | RSI: {s.get('rsi', 50):.0f}\n"
            f"→ 현재가: ${s.get('price', 0):,.2f} | 52주高 대비: {s.get('vs_52w_high', 0):+.1f}%"
        )
        lines.append(line)

    embeds = [{
        "title": f"🔄 반등 매수 기회 ({len(bounce_signals)}건) — {calc_date}",
        "description": (
            "고점수 종목이 급락 → RSI 과매도 진입\n"
            "기술적 반등 가능성 높은 종목\n\n"
            + "\n\n".join(lines)
        ),
        "color": 0x06b6d4,
        "footer": {"text": "급락 반등 전략 | 소량 분할 매수 권장"},
    }]
    _send_discord(embeds=embeds, signal_type="BOUNCE")
    print(f"[NOTIFY] 🔄 반등매수 알림 → BOUNCE 채널 ({len(bounce_signals)}건)")


# ═══════════════════════════════════════════════════════════
#  5. 모닝 브리핑 (REPORT 채널) — 강화
# ═══════════════════════════════════════════════════════════

def notify_morning_briefing(
    calc_date: date,
    regime: str,
    regime_detail: dict,
    top_buys: list = None,
    watchlist: list = None,
    earnings_today: list = None,
    grade_changes: list = None,
    portfolio_summary: dict = None,
):
    """매일 장 시작 전 모닝 브리핑 → REPORT 채널"""
    regime_emoji = {"BULL": "🟢", "NEUTRAL": "🟡", "BEAR": "🔴", "CRISIS": "🚨"}.get(regime, "⚪")
    spy = regime_detail.get("spy_price", 0)
    vix = regime_detail.get("vix_close", 0)

    embeds = [{
        "title": f"☀️ 모닝 브리핑 — {calc_date}",
        "description": (
            f"{regime_emoji} **시장: {regime}** | SPY ${spy:,.2f} | VIX {vix:.1f}\n"
            f"{'─' * 40}"
        ),
        "color": 0xfbbf24,
    }]

    # 포트폴리오 현황
    if portfolio_summary:
        tv = portfolio_summary.get("total_value", 0)
        dr = portfolio_summary.get("daily_return", 0)
        np_ = portfolio_summary.get("num_positions", 0)
        embeds.append({
            "title": "💼 포트폴리오",
            "fields": [
                {"name": "총 자산", "value": f"${tv:,.0f}", "inline": True},
                {"name": "전일 수익", "value": f"{dr:+.2f}%", "inline": True},
                {"name": "보유", "value": f"{np_}종목", "inline": True},
            ],
            "color": 0x3b82f6,
        })

    # 오늘의 매수 후보
    if top_buys:
        buy_text = "\n".join([
            f"{'🥇🥈🥉'[i] if i < 3 else '▫️'} **{s['ticker']}** "
            f"{s.get('grade', '')} ({s.get('score', 0):.1f}점) @ ${s.get('price', 0):,.2f}"
            for i, s in enumerate(top_buys[:5])
        ])
        embeds.append({
            "title": "🎯 오늘의 매수 후보 TOP 5",
            "description": buy_text,
            "color": 0x22c55e,
        })

    # 등급 변경
    if grade_changes:
        gc_text = "\n".join([
            f"{'⬆️' if g['direction'] == 'UP' else '⬇️'} **{g['ticker']}** "
            f"{g['old_grade']} → **{g['new_grade']}** ({g.get('score', 0):.1f}점)"
            for g in grade_changes[:8]
        ])
        embeds.append({
            "title": f"📊 등급 변경 ({len(grade_changes)}건)",
            "description": gc_text,
            "color": 0x8b5cf6,
        })

    # 어닝 발표 예정
    if earnings_today:
        earn_text = "\n".join([
            f"📅 **{e['ticker']}** | {e.get('time', 'TBD')} | "
            f"EPS 예상: ${e.get('eps_estimate', 0):.2f}"
            for e in earnings_today[:5]
        ])
        embeds.append({
            "title": f"📅 오늘 어닝 발표 ({len(earnings_today)}건)",
            "description": earn_text,
            "color": 0xf97316,
        })

    # 관심 종목
    if watchlist:
        watch_text = "\n".join([
            f"👀 **{w['ticker']}** | {w.get('reason', '')} | {w.get('score', 0):.1f}점"
            for w in watchlist[:5]
        ])
        embeds.append({
            "title": "👀 관심 종목",
            "description": watch_text,
            "color": 0x78716c,
        })

    embeds.append({
        "title": "",
        "description": "Good luck today! 🚀",
        "color": 0xfbbf24,
        "footer": {"text": "QUANT AI v3.4 모닝 브리핑 | 매일 장 시작 전 발송"},
    })

    _send_discord(embeds=embeds[:10], signal_type="REPORT")
    print(f"[NOTIFY] ☀️ 모닝 브리핑 → REPORT 채널")


# ═══════════════════════════════════════════════════════════
#  6. 일일 성과 리포트 (REPORT 채널) ★ 신규
# ═══════════════════════════════════════════════════════════

def notify_daily_performance(
    calc_date: date,
    portfolio_value: float,
    daily_return: float,
    spy_return: float,
    best_ticker: str = "",
    best_pnl: float = 0,
    worst_ticker: str = "",
    worst_pnl: float = 0,
    num_positions: int = 0,
    total_pnl: float = 0,
):
    """일일 포트폴리오 성과 리포트 → REPORT 채널"""
    alpha = daily_return - spy_return
    color = 0x22c55e if daily_return >= 0 else 0xef4444

    fields = [
        {"name": "포트폴리오", "value": f"${portfolio_value:,.0f}", "inline": True},
        {"name": "오늘 수익률", "value": f"{daily_return:+.2f}%", "inline": True},
        {"name": "SPY", "value": f"{spy_return:+.2f}%", "inline": True},
        {"name": "알파", "value": f"{alpha:+.2f}%", "inline": True},
        {"name": "보유 종목", "value": f"{num_positions}개", "inline": True},
        {"name": "누적 손익", "value": f"${total_pnl:+,.0f}", "inline": True},
    ]

    if best_ticker:
        fields.append({"name": "🏆 최고", "value": f"{best_ticker} ({best_pnl:+.1f}%)", "inline": True})
    if worst_ticker:
        fields.append({"name": "💀 최저", "value": f"{worst_ticker} ({worst_pnl:+.1f}%)", "inline": True})

    embeds = [{
        "title": f"📊 일일 성과 — {calc_date}",
        "color": color,
        "fields": fields,
        "footer": {"text": "QUANT AI v3.4 | 매일 장 마감 후"},
    }]
    _send_discord(embeds=embeds, signal_type="REPORT")
    print(f"[NOTIFY] 📊 일일 성과 → REPORT 채널 ({daily_return:+.2f}%)")


# ═══════════════════════════════════════════════════════════
#  7. 등급 변경 알림 (ALERT 채널) ★ 신규
# ═══════════════════════════════════════════════════════════

def notify_grade_changes(calc_date: date, upgrades: list, downgrades: list):
    """보유종목 등급 변경 알림 → ALERT 채널"""
    if not upgrades and not downgrades:
        return

    embeds = []

    if downgrades:
        down_text = "\n".join([
            f"⬇️ **{g['ticker']}** {g['old_grade']} → **{g['new_grade']}** "
            f"| {g.get('old_score', 0):.1f} → {g.get('new_score', 0):.1f}점"
            for g in downgrades[:8]
        ])
        embeds.append({
            "title": f"⚠️ 등급 하락 ({len(downgrades)}건) — {calc_date}",
            "description": down_text + "\n\n⚠️ 손절 기준 재검토 필요",
            "color": 0xef4444,
        })

    if upgrades:
        up_text = "\n".join([
            f"⬆️ **{g['ticker']}** {g['old_grade']} → **{g['new_grade']}** "
            f"| {g.get('old_score', 0):.1f} → {g.get('new_score', 0):.1f}점"
            for g in upgrades[:8]
        ])
        embeds.append({
            "title": f"✨ 등급 상승 ({len(upgrades)}건) — {calc_date}",
            "description": up_text,
            "color": 0x22c55e,
        })

    _send_discord(embeds=embeds[:10], signal_type="ALERT")
    print(f"[NOTIFY] 📊 등급변경 알림 → ALERT 채널 (⬆{len(upgrades)} ⬇{len(downgrades)})")


# ═══════════════════════════════════════════════════════════
#  8. 어닝 D-day 알림 (ALERT 채널) ★ 신규
# ═══════════════════════════════════════════════════════════

def notify_earnings_alert(calc_date: date, earnings_stocks: list):
    """보유종목 어닝 발표 당일 알림 → ALERT 채널"""
    if not earnings_stocks:
        return

    lines = []
    for e in earnings_stocks[:8]:
        line = (
            f"📅 **{e['ticker']}** | {e.get('time', 'TBD')}\n"
            f"→ EPS 예상: ${e.get('eps_estimate', 0):.2f} | "
            f"매출 예상: ${e.get('rev_estimate', 0)/1e9:.1f}B\n"
            f"→ 현재 등급: {e.get('grade', '?')} | 보유: {e.get('shares', 0)}주"
        )
        lines.append(line)

    embeds = [{
        "title": f"📅 보유종목 어닝 발표 D-Day ({len(earnings_stocks)}건) — {calc_date}",
        "description": (
            "⚠️ 어닝 발표 전후 변동성 주의!\n"
            "손절가 확인 & 포지션 축소 검토\n\n"
            + "\n\n".join(lines)
        ),
        "color": 0xf97316,
        "footer": {"text": "어닝 서프라이즈 시 ±5~15% 변동 가능"},
    }]
    _send_discord(embeds=embeds, signal_type="ALERT")
    print(f"[NOTIFY] 📅 어닝 D-day 알림 → ALERT 채널 ({len(earnings_stocks)}건)")


# ═══════════════════════════════════════════════════════════
#  9. 긴급 알림 (ALERT 채널) — 기존
# ═══════════════════════════════════════════════════════════

def notify_emergency(title: str, message: str):
    embeds = [{
        "title": f"🚨 {title}",
        "description": message,
        "color": 0xff0000,
        "footer": {"text": "QUANT AI 긴급 알림 — 즉시 확인 필요"},
    }]
    _send_discord(embeds=embeds, signal_type="ALERT")
    if CHANNEL in ("slack", "all"):
        _send_slack(f"🚨 {title}\n{message}")
    if CHANNEL in ("telegram", "all"):
        _send_telegram(f"🚨 <b>{title}</b>\n{message}")
    print(f"[NOTIFY] 🚨 긴급 알림 → ALERT 채널")


# ═══════════════════════════════════════════════════════════
#  10. 리스크 경고 (ALERT 채널) — 강화
# ═══════════════════════════════════════════════════════════

def notify_risk_warning(
    calc_date: date,
    dd_mode: str,
    drawdown_pct: float,
    cb_level: str = "",
    losing_streak: int = 0,
    concentration_warn: list = None,
):
    """리스크 상태 경고 → ALERT 채널"""
    dd_emoji = {"NORMAL": "🟢", "CAUTION": "🟡", "WARNING": "🟠", "DANGER": "🔴", "CRITICAL": "🚨"}
    fields = [
        {"name": "DD 단계", "value": f"{dd_emoji.get(dd_mode, '⚪')} **{dd_mode}**", "inline": True},
        {"name": "낙폭", "value": f"{drawdown_pct:.1f}%", "inline": True},
    ]
    if cb_level:
        fields.append({"name": "서킷브레이커", "value": f"{cb_level} (연패: {losing_streak})", "inline": True})
    if concentration_warn:
        warn_text = ", ".join([f"{w['sector']}({w['pct']:.0f}%)" for w in concentration_warn[:3]])
        fields.append({"name": "집중도 경고", "value": warn_text, "inline": False})

    embeds = [{
        "title": f"⚠️ 리스크 경고 — {calc_date}",
        "color": 0xea580c,
        "fields": fields,
        "footer": {"text": "매수 제한/포지션 축소 자동 적용 중"},
    }]
    _send_discord(embeds=embeds, signal_type="ALERT")
    print(f"[NOTIFY] ⚠️ 리스크 경고 → ALERT 채널 (DD: {dd_mode})")


# ═══════════════════════════════════════════════════════════
#  11. 시장 국면 전환 (ALERT 채널) — 기존
# ═══════════════════════════════════════════════════════════

def notify_regime_change(calc_date: date, old_regime: str, new_regime: str, detail: str = ""):
    old_e = {"BULL": "🟢", "NEUTRAL": "🟡", "BEAR": "🔴", "CRISIS": "🚨"}.get(old_regime, "⚪")
    new_e = {"BULL": "🟢", "NEUTRAL": "🟡", "BEAR": "🔴", "CRISIS": "🚨"}.get(new_regime, "⚪")
    embeds = [{
        "title": f"🔄 시장 국면 전환 — {calc_date}",
        "description": f"{old_e} **{old_regime}** → {new_e} **{new_regime}**\n\n{detail}",
        "color": 0xff6600,
        "footer": {"text": "DynamicConfig 파라미터 자동 조정됨"},
    }]
    _send_discord(embeds=embeds, signal_type="ALERT")
    print(f"[NOTIFY] 🔄 국면전환 → ALERT ({old_regime} → {new_regime})")


# ═══════════════════════════════════════════════════════════
#  12. 배치 완료 알림 (REPORT 채널) — 기존
# ═══════════════════════════════════════════════════════════

def notify_batch_complete(calc_date: date, elapsed_seconds: float, results: dict):
    ok = sum(1 for v in results.values() if v == "OK")
    fail = sum(1 for v in results.values() if isinstance(v, str) and v.startswith("FAIL"))
    skip = sum(1 for v in results.values() if v == "SKIP")
    status_emoji = "✅" if fail == 0 else "⚠️"

    detail_lines = []
    for k, v in results.items():
        if v == "OK":
            detail_lines.append(f"✅ {k}")
        elif v == "SKIP":
            detail_lines.append(f"⏭ {k}")
        else:
            detail_lines.append(f"❌ {k}: {v}")

    embeds = [{
        "title": f"{status_emoji} 일일 배치 완료 — {calc_date}",
        "description": "\n".join(detail_lines),
        "color": 0x22c55e if fail == 0 else 0xef4444,
        "fields": [
            {"name": "성공", "value": str(ok), "inline": True},
            {"name": "실패", "value": str(fail), "inline": True},
            {"name": "스킵", "value": str(skip), "inline": True},
            {"name": "소요시간", "value": f"{elapsed_seconds:.0f}초", "inline": True},
        ],
        "footer": {"text": "QUANT AI v3.4 배치 시스템"},
    }]
    _send_discord(embeds=embeds, signal_type="REPORT")
    print(f"[NOTIFY] {status_emoji} 배치 완료 → REPORT 채널")


# ═══════════════════════════════════════════════════════════
#  13. 주간 리밸런싱 알림 (REPORT 채널) — 기존
# ═══════════════════════════════════════════════════════════

def notify_weekly_rebalance(calc_date: date, buys: list, sells: list, adjusts: list, turnover: float):
    lines = []
    for b in buys[:5]:
        lines.append(f"🟢 매수: **{b['ticker']}** {b.get('shares', 0)}주")
    for s in sells[:5]:
        lines.append(f"🔴 매도: **{s['ticker']}** {s.get('shares', 0)}주")
    for a in adjusts[:5]:
        direction = "⬆️" if a.get("direction") == "UP" else "⬇️"
        lines.append(f"{direction} 조정: **{a['ticker']}** {a.get('shares', 0)}주")

    embeds = [{
        "title": f"🔄 주간 리밸런싱 — {calc_date}",
        "description": "\n".join(lines) if lines else "변경 없음",
        "color": 0x3b82f6,
        "fields": [
            {"name": "매수", "value": f"{len(buys)}건", "inline": True},
            {"name": "매도", "value": f"{len(sells)}건", "inline": True},
            {"name": "조정", "value": f"{len(adjusts)}건", "inline": True},
            {"name": "턴오버", "value": f"{turnover:.1f}%", "inline": True},
        ],
        "footer": {"text": "QUANT AI v3.4 주간 리밸런싱"},
    }]
    _send_discord(embeds=embeds, signal_type="REPORT")
    print(f"[NOTIFY] 🔄 리밸런싱 → REPORT 채널")


# ═══════════════════════════════════════════════════════════
#  14. 주간/월간 성과 리포트 (REPORT 채널) — 기존 강화
# ═══════════════════════════════════════════════════════════

def notify_weekly_report(
    calc_date: date,
    week_return: float,
    total_value: float,
    spy_return: float = 0,
    win_rate: float = 0,
    best_ticker: str = "",
    best_pnl: float = 0,
    worst_ticker: str = "",
    worst_pnl: float = 0,
    num_trades: int = 0,
):
    alpha = week_return - spy_return
    embeds = [{
        "title": f"📊 주간 성과 리포트 — {calc_date}",
        "color": 0x22c55e if week_return >= 0 else 0xef4444,
        "fields": [
            {"name": "주간 수익률", "value": f"{week_return:+.2f}%", "inline": True},
            {"name": "SPY", "value": f"{spy_return:+.2f}%", "inline": True},
            {"name": "알파", "value": f"{alpha:+.2f}%", "inline": True},
            {"name": "총 자산", "value": f"${total_value:,.0f}", "inline": True},
            {"name": "승률", "value": f"{win_rate:.0f}%", "inline": True},
            {"name": "거래 수", "value": f"{num_trades}건", "inline": True},
        ],
        "footer": {"text": "QUANT AI v3.4 주간 리포트"},
    }]
    if best_ticker:
        embeds[0]["fields"].append({"name": "🏆 MVP", "value": f"{best_ticker} ({best_pnl:+.1f}%)", "inline": True})
    if worst_ticker:
        embeds[0]["fields"].append({"name": "💀 최악", "value": f"{worst_ticker} ({worst_pnl:+.1f}%)", "inline": True})

    _send_discord(embeds=embeds, signal_type="REPORT")
    print(f"[NOTIFY] 📊 주간 리포트 → REPORT 채널 ({week_return:+.2f}%)")