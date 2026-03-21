"""
notifier.py — QUANT AI 8채널 알림 시스템 v3.3
================================================
Discord 채널별 웹후크 + Slack/Telegram 지원.

.env 설정:
  # 채널별 (권장)
  DISCORD_WEBHOOK_BUY=https://discord.com/api/webhooks/...
  DISCORD_WEBHOOK_SELL=https://discord.com/api/webhooks/...
  DISCORD_WEBHOOK_PROFIT=https://discord.com/api/webhooks/...
  DISCORD_WEBHOOK_ADD=https://discord.com/api/webhooks/...
  DISCORD_WEBHOOK_FIRE=https://discord.com/api/webhooks/...
  DISCORD_WEBHOOK_BOUNCE=https://discord.com/api/webhooks/...
  DISCORD_WEBHOOK_REPORT=https://discord.com/api/webhooks/...
  DISCORD_WEBHOOK_ALERT=https://discord.com/api/webhooks/...

  # 통합 fallback (선택 — 채널별 미설정 시 사용)
  DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

  NOTIFY_CHANNEL=discord   # discord / slack / telegram / all
"""
import os
import logging
from datetime import datetime, date
from typing import List, Optional

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
    """시그널 유형 → Discord 웹후크 URL (채널별 → fallback 순)"""
    url = _WEBHOOK_MAP.get(signal_type.upper(), "")
    if url:
        return url
    if _FALLBACK_URL:
        return _FALLBACK_URL
    # 아무 채널이라도 설정된 게 있으면 사용
    for v in _WEBHOOK_MAP.values():
        if v:
            return v
    return ""


# ═══════════════════════════════════════════════════════════
#  저수준 전송
# ═══════════════════════════════════════════════════════════

def _send_discord(content: str = None, embeds: list = None, signal_type: str = "REPORT") -> bool:
    """Discord Webhook 전송 (채널별 라우팅)"""
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
    """설정된 채널로 텍스트 전송"""
    sent = False
    if CHANNEL in ("discord", "all"):
        sent = _send_discord(content=text, signal_type=signal_type) or sent
    if CHANNEL in ("slack", "all"):
        sent = _send_slack(text) or sent
    if CHANNEL in ("telegram", "all"):
        sent = _send_telegram(text) or sent
    return sent


def send_discord_embed(embeds: list, signal_type: str = "REPORT"):
    """Discord 전용 Embed 전송 (리치 포맷)"""
    return _send_discord(embeds=embeds, signal_type=signal_type)


# ═══════════════════════════════════════════════════════════
#  시그널 알림
# ═══════════════════════════════════════════════════════════

def notify_daily_signals(
    calc_date: date,
    regime: str,
    regime_detail: dict,
    buy_signals: list,
    sell_signals: list,
    portfolio_summary: dict,
):
    """일일 트레이딩 시그널 알림 (Discord Embed — 채널별 분리)"""
    # ── 1. 헤더 + 시장 국면 (REPORT 채널) ──
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
        "footer": {"text": "QUANT AI v3.3 | 투자 참고용, 투자 판단은 본인 책임"},
    }

    # 포트폴리오 현황 embed
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

    # ── 2. BUY 시그널 → BUY 채널 ──
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

    # ── 3. SELL 시그널 → SELL 채널 (손절) / PROFIT 채널 (익절) ──
    if sell_signals:
        loss_signals = [s for s in sell_signals if s.get("pnl_pct", 0) < 0]
        profit_signals = [s for s in sell_signals if s.get("pnl_pct", 0) >= 0]

        if loss_signals:
            sell_lines = []
            for s in loss_signals[:8]:
                pnl_str = f"{s.get('pnl_pct', 0):+.1f}%"
                line = f"**{s['ticker']}** | {s.get('reason', 'SELL')} | 보유 {s.get('holding_days', 0)}일 | {pnl_str}"
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
                pnl_str = f"{s.get('pnl_pct', 0):+.1f}%"
                line = f"**{s['ticker']}** | {s.get('reason', 'PROFIT')} | 보유 {s.get('holding_days', 0)}일 | 💰 {pnl_str}"
                profit_lines.append(line)
            profit_embeds = [header_embed, {
                "title": f"💰 칼춤 피날레 ({len(profit_signals)}건)",
                "description": "\n".join(profit_lines),
                "color": 0xfbbf24,
            }]
            _send_discord(embeds=profit_embeds, signal_type="PROFIT")
            print(f"[NOTIFY] 💰 익절 알림 → PROFIT 채널 ({len(profit_signals)}건)")

    # ── 4. 시그널 없음 → REPORT 채널 ──
    if not buy_signals and not sell_signals:
        no_signal_embeds = [header_embed, {
            "title": "📋 시그널 없음",
            "description": "오늘은 매수/매도 조건을 충족하는 종목이 없습니다.",
            "color": 0x888888,
        }]
        if port_embed:
            no_signal_embeds.append(port_embed)
        _send_discord(embeds=no_signal_embeds, signal_type="REPORT")
        print("[NOTIFY] 📋 시그널 없음 → REPORT 채널")

    # Slack/Telegram fallback (텍스트)
    text = _embeds_to_text([header_embed] + ([port_embed] if port_embed else []))
    if CHANNEL in ("slack", "all"):
        _send_slack(text)
    if CHANNEL in ("telegram", "all"):
        _send_telegram(text)


def notify_emergency(title: str, message: str):
    """긴급 경고 알림 → ALERT 채널"""
    embeds = [{
        "title": f"🚨 {title}",
        "description": message,
        "color": 0xff0000,
        "timestamp": datetime.utcnow().isoformat(),
    }]
    _send_discord(embeds=embeds, signal_type="ALERT")
    text = f"🚨 {title}\n{message}"
    if CHANNEL in ("slack", "all"):
        _send_slack(text)
    if CHANNEL in ("telegram", "all"):
        _send_telegram(text)
    print(f"[NOTIFY] 🚨 긴급 알림 → ALERT 채널: {title}")


def notify_weekly_rebalance(calc_date: date, buys: list, sells: list, adjusts: list, turnover: float):
    """주간 리밸런싱 알림 → REPORT 채널"""
    lines = [f"📋 **주간 리밸런싱** ({calc_date})"]
    if buys:
        lines.append(f"\n🟢 신규 매수 ({len(buys)}건)")
        for b in buys[:5]:
            lines.append(f"  {b['ticker']} {b['shares']}주 @ ${b['price']:,.2f}")
    if sells:
        lines.append(f"\n🔴 매도 ({len(sells)}건)")
        for s in sells[:5]:
            lines.append(f"  {s['ticker']} 전량 | {s.get('reason', 'EXIT')}")
    if adjusts:
        lines.append(f"\n🔄 비중 조정 ({len(adjusts)}건)")
    lines.append(f"\n회전율: {turnover:.1f}%")

    text = "\n".join(lines)
    send_message(text, signal_type="REPORT")
    print(f"[NOTIFY] ✅ 주간 리밸런싱 알림 → REPORT 채널")


def notify_batch_complete(calc_date: date, elapsed_seconds: float, results: dict):
    """배치 완료 알림 → REPORT 채널"""
    ok = sum(1 for v in results.values() if v == "OK")
    fail = sum(1 for v in results.values() if isinstance(v, str) and v.startswith("FAIL"))
    emoji = "✅" if fail == 0 else "⚠️"
    text = (
        f"{emoji} 일일 배치 완료 ({calc_date})\n"
        f"성공: {ok} | 실패: {fail} | 소요: {elapsed_seconds:.0f}초"
    )
    send_message(text, signal_type="REPORT")


# ── 헬퍼 ──

def _embeds_to_text(embeds: list) -> str:
    """Discord Embed → 텍스트 변환 (Slack/Telegram용)"""
    lines = []
    for e in embeds:
        if not e:
            continue
        if e.get("title"):
            lines.append(e["title"])
        if e.get("description"):
            lines.append(e["description"])
        for f in e.get("fields", []):
            lines.append(f"  {f['name']}: {f['value']}")
        lines.append("")
    return "\n".join(lines)
