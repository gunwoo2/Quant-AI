"""
notifier.py — QUANT AI 13채널 알림 시스템 v3.6
================================================
Discord 채널별 웹후크 + Slack/Telegram 지원.

v3.6 변경 (디자인 시스템 적용):
  - 디자인 스펙 (DISCORD_DESIGN_SPEC.md) 완전 반영
  - 타이틀 통일: [이모지] [유형] — YYYY-MM-DD
  - footer 통일: QUANT AI v3.5 | [카테고리]
  - fields 기반 3열 inline 레이아웃
  - 티커 볼드 + (회사명) 표기
  - "돈 복사 시작" → "매수 추천"
  - "탈출은 지능순" → "매도 시그널"
  - 포트폴리오 현황 → REPORT 채널 전용 (BUY에서 제거)
  - MORNING: 요약만, 상세는 각 채널

.env 설정:
  DISCORD_WEBHOOK_BUY / SELL / PROFIT / ADD / FIRE / BOUNCE / REPORT / ALERT / MORNING / PERF / SYSTEM / RISK / BACKTEST
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

# ── Discord 채널별 웹후크 매핑 (개인 MY_ + 공용 PUB_ 이중 구조) ──
# .env 변수명: DISCORD_WEBHOOK_MY_xxx (개인), DISCORD_WEBHOOK_PUB_xxx (공용)
_WEBHOOK_MY = {
    "BUY":      os.environ.get("DISCORD_WEBHOOK_MY_BUY", ""),
    "SELL":     os.environ.get("DISCORD_WEBHOOK_MY_SELL", ""),
    "PORTFOLIO":os.environ.get("DISCORD_WEBHOOK_MY_PORTFOLIO", ""),
    "MORNING":  os.environ.get("DISCORD_WEBHOOK_MY_MORNING", ""),
    "RISK":     os.environ.get("DISCORD_WEBHOOK_MY_RISK", ""),
}

_WEBHOOK_PUB = {
    "BUY":      os.environ.get("DISCORD_WEBHOOK_PUB_BUY", ""),
    "SELL":     os.environ.get("DISCORD_WEBHOOK_PUB_SELL", ""),
    "PROFIT":   os.environ.get("DISCORD_WEBHOOK_PUB_PROFIT", ""),
    "ADD":      os.environ.get("DISCORD_WEBHOOK_PUB_ADD_DOWN", ""),
    "ADD_UP":   os.environ.get("DISCORD_WEBHOOK_PUB_ADD_UP", ""),
    "FIRE":     os.environ.get("DISCORD_WEBHOOK_PUB_FIRE", ""),
    "BOUNCE":   os.environ.get("DISCORD_WEBHOOK_PUB_BOUNCE", ""),
    "REPORT":   os.environ.get("DISCORD_WEBHOOK_PUB_REPORT", ""),
    "ALERT":    os.environ.get("DISCORD_WEBHOOK_PUB_ALERT", ""),
    "MORNING":  os.environ.get("DISCORD_WEBHOOK_PUB_MORNING", ""),
    "SYSTEM":   os.environ.get("DISCORD_WEBHOOK_PUB_SYSTEM", ""),
    "PERF":     os.environ.get("DISCORD_WEBHOOK_PUB_REPORT", ""),  # PERF→REPORT 공유
    "RISK":     os.environ.get("DISCORD_WEBHOOK_PUB_ALERT", ""),   # RISK→ALERT 공유
    "BACKTEST": os.environ.get("DISCORD_WEBHOOK_PUB_REPORT", ""),  # BACKTEST→REPORT 공유
}

_FALLBACK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")


def _get_discord_url(signal_type: str = "REPORT", private: bool = False) -> str:
    """채널 URL 조회. private=True면 개인채널, False면 공용채널"""
    st = signal_type.upper()
    if private:
        url = _WEBHOOK_MY.get(st, "")
        if url:
            return url
    url = _WEBHOOK_PUB.get(st, "")
    if url:
        return url
    if _FALLBACK_URL:
        return _FALLBACK_URL
    # 아무거나 있는 URL 반환
    for v in _WEBHOOK_PUB.values():
        if v:
            return v
    for v in _WEBHOOK_MY.values():
        if v:
            return v
    return ""


# ═══════════════════════════════════════════════════════════
#  회사명 헬퍼 — 티커 → 볼드 티커 (회사명)
# ═══════════════════════════════════════════════════════════

# S&P 500 주요 종목 풀네임 (빈번 종목 우선)
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
    "BA": "Boeing", "CAT": "Caterpillar", "DE": "Deere & Co",
    "ISRG": "Intuitive Surgical", "SPGI": "S&P Global", "BLK": "BlackRock",
    "AXP": "American Express", "MDLZ": "Mondelez", "GILD": "Gilead",
    "SYK": "Stryker", "NOW": "ServiceNow", "BKNG": "Booking Holdings",
    "ADI": "Analog Devices", "LRCX": "Lam Research", "AMAT": "Applied Materials",
    "REGN": "Regeneron", "VRTX": "Vertex Pharma", "PANW": "Palo Alto Networks",
    "SNPS": "Synopsys", "CDNS": "Cadence Design", "KLAC": "KLA Corp",
    "MRVL": "Marvell Tech", "FTNT": "Fortinet", "ABNB": "Airbnb",
    "PYPL": "PayPal", "ORCL": "Oracle", "IBM": "IBM",
    "GE": "GE Aerospace", "LMT": "Lockheed Martin", "MMM": "3M",
    "DIS": "Walt Disney", "CVX": "Chevron", "PFE": "Pfizer",
    "WFC": "Wells Fargo", "BAC": "Bank of America", "C": "Citigroup",
    "USB": "U.S. Bancorp", "SCHW": "Charles Schwab",
    "SO": "Southern Co", "DUK": "Duke Energy", "D": "Dominion Energy",
    "CL": "Colgate-Palmolive", "PLD": "Prologis", "AMT": "American Tower",
    "CCI": "Crown Castle", "O": "Realty Income", "SPG": "Simon Property",
    "SBUX": "Starbucks", "TGT": "Target", "LOW": "Lowe's",
    "F": "Ford", "GM": "General Motors", "RIVN": "Rivian",
    "PLTR": "Palantir", "COIN": "Coinbase", "SQ": "Block Inc",
    "SHOP": "Shopify", "SNOW": "Snowflake", "DDOG": "Datadog",
    "CRWD": "CrowdStrike", "ZS": "Zscaler", "NET": "Cloudflare",
    "UBER": "Uber", "LYFT": "Lyft", "DASH": "DoorDash",
    "ARM": "Arm Holdings", "SMCI": "Super Micro", "MU": "Micron",
    "ON": "ON Semiconductor", "MCHP": "Microchip Tech",
    "ETN": "Eaton Corp", "EMR": "Emerson Electric", "HON": "Honeywell",
    "MMC": "Marsh McLennan", "AIG": "AIG", "TRV": "Travelers",
    "ALL": "Allstate", "MET": "MetLife", "PRU": "Prudential",
    "CI": "Cigna", "ELV": "Elevance Health", "HUM": "Humana",
    "CVS": "CVS Health", "MCK": "McKesson", "CAH": "Cardinal Health",
    "BIIB": "Biogen", "MRNA": "Moderna", "ZTS": "Zoetis",
    "A": "Agilent", "BDX": "Becton Dickinson", "BSX": "Boston Scientific",
    "EW": "Edwards Lifesciences", "MDT": "Medtronic",
    "CME": "CME Group", "ICE": "Intercontinental Exchange",
    "MSCI": "MSCI Inc", "FIS": "Fidelity National", "ADP": "ADP",
    "PAYX": "Paychex", "CPRT": "Copart", "FAST": "Fastenal",
    "ODFL": "Old Dominion", "UNP": "Union Pacific", "CSX": "CSX Corp",
    "NSC": "Norfolk Southern", "FDX": "FedEx",
    "VZ": "Verizon", "TMUS": "T-Mobile", "CHTR": "Charter Comm",
    "EA": "Electronic Arts", "ATVI": "Activision", "TTWO": "Take-Two",
    "ROKU": "Roku", "SPOT": "Spotify", "WBD": "Warner Bros Discovery",
    "SPY": "SPDR S&P 500 ETF", "QQQ": "Invesco QQQ", "IWM": "iShares Russell 2000",
    "DIA": "SPDR Dow Jones", "VTI": "Vanguard Total Market",
}

# DB에서 로드된 이름 캐시 (런타임에 채워짐)
_db_name_cache: Dict[str, str] = {}


def _load_names_from_db():
    """stocks 테이블에서 회사명 로드 (최초 1회)"""
    global _db_name_cache
    if _db_name_cache:
        return
    try:
        from db_pool import get_cursor
        with get_cursor() as cur:
            cur.execute("SELECT ticker, company_name FROM stocks WHERE company_name IS NOT NULL")
            for row in cur.fetchall():
                name = row["company_name"]
                # 너무 길면 자름 (20자)
                if len(name) > 22:
                    name = name[:20] + "…"
                _db_name_cache[row["ticker"]] = name
    except Exception:
        pass  # DB 불가 시 하드코딩 맵 사용


def _tn(ticker: str) -> str:
    """티커 → '**AAPL** (Apple)' 형식 반환"""
    # DB 캐시 시도
    if not _db_name_cache:
        try:
            _load_names_from_db()
        except Exception:
            pass

    name = _db_name_cache.get(ticker) or _COMPANY_NAMES.get(ticker, "")
    if name:
        return f"**{ticker}** ({name})"
    return f"**{ticker}**"


def _tn_short(ticker: str) -> str:
    """짧은 버전: '**AAPL**' — 공간 부족할 때"""
    return f"**{ticker}**"


# ═══════════════════════════════════════════════════════════
#  저수준 전송
# ═══════════════════════════════════════════════════════════

def _send_discord(content: str = None, embeds: list = None, signal_type: str = "REPORT", private: bool = False) -> bool:
    """Discord 전송. private=True면 개인+공용 둘 다, False면 공용만"""
    sent = False
    # 공용 채널
    url = _get_discord_url(signal_type, private=False)
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
            sent = True
        else:
            logger.error(f"[DISCORD/{signal_type}] {r.status_code}: {r.text[:200]}")
    except Exception as e:
        logger.error(f"[DISCORD/{signal_type}] 전송 실패: {e}")

    # 개인 채널에도 동시 발송 (BUY/SELL/MORNING/RISK만)
    if signal_type.upper() in ("BUY", "SELL", "MORNING", "RISK"):
        my_url = _get_discord_url(signal_type, private=True)
        if my_url and my_url != url:
            try:
                requests.post(my_url, json=payload, timeout=10)
            except Exception:
                pass

    return sent


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
#  1. 매수 추천 → BUY 채널 | 매도 시그널 → SELL 채널 | 익절 → PROFIT 채널
# ═══════════════════════════════════════════════════════════

def notify_daily_signals(
    calc_date: date,
    regime: str,
    regime_detail: dict,
    buy_signals: list,
    sell_signals: list,
    portfolio_summary: dict,
):
    """
    일일 트레이딩 시그널 — BUY / SELL / PROFIT 채널 분리 발송
    
    디자인 변경:
      - "돈 복사 시작" → "매수 추천"
      - "탈출은 지능순" → "매도 시그널"
      - 포트폴리오 현황 → BUY에서 제거 (REPORT 전용)
      - 티커: **AAPL** (Apple) 형식
      - fields 3열 inline 레이아웃
    """

    # ── BUY 시그널 → BUY 채널 ──
    if buy_signals:
        buy_embeds = []
        for s in buy_signals[:8]:
            ticker = s["ticker"]
            grade = s.get("grade", "")
            score = s["score"]
            sector = s.get("sector", "")
            sector_str = f" | {sector}" if sector else ""

            embed = {
                "title": f"■ {ticker}",
                "description": f"등급 {grade} | {score:.1f}점{sector_str}",
                "color": 0x22c55e,
                "fields": [
                    {"name": "매수가", "value": f"${s['price']:,.2f}", "inline": True},
                    {"name": "수량", "value": f"{s['shares']}주", "inline": True},
                    {"name": "금액", "value": f"${s['amount']:,.0f}", "inline": True},
                    {"name": "비중", "value": f"{s['weight']:.1f}%", "inline": True},
                    {"name": "손절가", "value": f"${s['stop_loss']:,.2f} (-{s.get('stop_pct', 10):.0f}%)", "inline": True},
                ],
            }
            buy_embeds.append(embed)

        # 헤더 embed (맨 앞에 삽입)
        header = {
            "title": f"🟢 매수 추천 ({len(buy_signals)}건) — {calc_date}",
            "color": 0x22c55e,
            "footer": {"text": "QUANT AI v3.5 | 매수 추천"},
        }
        buy_embeds.insert(0, header)

        _send_discord(embeds=buy_embeds[:10], signal_type="BUY")
        print(f"[NOTIFY] 🟢 매수 추천 → BUY 채널 ({len(buy_signals)}건)")

    # ── SELL 시그널 → SELL/PROFIT 채널 분리 ──
    if sell_signals:
        loss_signals = [s for s in sell_signals if s.get("pnl_pct", 0) < 0]
        profit_signals = [s for s in sell_signals if s.get("pnl_pct", 0) >= 0]

        # 손절 → SELL 채널
        if loss_signals:
            sell_embeds = [{
                "title": f"🔴 매도 시그널 ({len(loss_signals)}건) — {calc_date}",
                "color": 0xef4444,
                "footer": {"text": "QUANT AI v3.5 | 매도 시그널"},
            }]
            for s in loss_signals[:8]:
                ticker = s["ticker"]
                reason = s.get("reason", "SELL")
                embed = {
                    "title": f"■ {ticker}",
                    "description": f"사유: {reason}",
                    "color": 0xef4444,
                    "fields": [
                        {"name": "매입가", "value": f"${s.get('entry_price', 0):,.2f}", "inline": True},
                        {"name": "현재가", "value": f"${s.get('price', 0):,.2f}", "inline": True},
                        {"name": "손익률", "value": f"{s.get('pnl_pct', 0):+.1f}%", "inline": True},
                        {"name": "보유 기간", "value": f"{s.get('holding_days', 0)}일", "inline": True},
                        {"name": "수량", "value": f"{s.get('shares', 0)}주", "inline": True},
                    ],
                }
                sell_embeds.append(embed)
            _send_discord(embeds=sell_embeds[:10], signal_type="SELL")
            print(f"[NOTIFY] 🔴 매도 시그널 → SELL 채널 ({len(loss_signals)}건)")

        # 익절 → PROFIT 채널
        if profit_signals:
            profit_embeds = [{
                "title": f"💰 수익 실현 ({len(profit_signals)}건) — {calc_date}",
                "color": 0xfbbf24,
                "footer": {"text": "QUANT AI v3.5 | 수익 실현"},
            }]
            for s in profit_signals[:8]:
                ticker = s["ticker"]
                gain = abs(s.get("price", 0) - s.get("entry_price", 0)) * s.get("shares", 0)
                embed = {
                    "title": f"■ {ticker}",
                    "color": 0xfbbf24,
                    "fields": [
                        {"name": "매입가", "value": f"${s.get('entry_price', 0):,.2f}", "inline": True},
                        {"name": "현재가", "value": f"${s.get('price', 0):,.2f}", "inline": True},
                        {"name": "수익률", "value": f"+{s.get('pnl_pct', 0):.1f}%", "inline": True},
                        {"name": "보유 기간", "value": f"{s.get('holding_days', 0)}일", "inline": True},
                        {"name": "수량", "value": f"{s.get('shares', 0)}주", "inline": True},
                        {"name": "실현 수익", "value": f"+${gain:,.0f}", "inline": True},
                    ],
                }
                profit_embeds.append(embed)
            _send_discord(embeds=profit_embeds[:10], signal_type="PROFIT")
            print(f"[NOTIFY] 💰 수익 실현 → PROFIT 채널 ({len(profit_signals)}건)")

    # 시그널 0건이면 REPORT 채널에 안내
    if not buy_signals and not sell_signals:
        no_signal_embed = [{
            "title": f"📋 오늘의 시그널: 없음 — {calc_date}",
            "description": "매수/매도 조건을 충족하는 종목이 없습니다.\n기존 포트폴리오 유지.",
            "color": 0x78716c,
            "footer": {"text": "QUANT AI v3.5 | 일일 시그널"},
        }]
        _send_discord(embeds=no_signal_embed, signal_type="REPORT")
        print("[NOTIFY] 📋 시그널 없음 → REPORT 채널")


# ═══════════════════════════════════════════════════════════
#  2. 추가 매수 → ADD 채널
# ═══════════════════════════════════════════════════════════

def notify_add_position(calc_date: date, add_signals: list):
    """보유종목 추가 매수 (물타기/피라미딩) 알림 → ADD 채널"""
    if not add_signals:
        return

    add_embeds = [{
        "title": f"📈 추가 매수 ({len(add_signals)}건) — {calc_date}",
        "color": 0xf59e0b,
        "footer": {"text": "QUANT AI v3.5 | 추가 매수"},
    }]

    for s in add_signals[:8]:
        ticker = s["ticker"]
        embed = {
            "title": f"■ {ticker}",
            "description": (
                f"등급 {s.get('grade', '?')} | {s.get('score', 0):.1f}점 "
                f"| 현재 수익률 {s.get('pnl_pct', 0):+.1f}%"
            ),
            "color": 0xf59e0b,
            "fields": [
                {"name": "추가 수량", "value": f"{s.get('shares', 0)}주", "inline": True},
                {"name": "매수가", "value": f"${s.get('price', 0):,.2f}", "inline": True},
                {"name": "평단 개선", "value": f"{s.get('avg_down_pct', 0):+.1f}%", "inline": True},
            ],
        }
        add_embeds.append(embed)

    # 마지막에 주의 문구
    add_embeds.append({
        "description": "⚠️ 손절가 재설정 필요",
        "color": 0xf59e0b,
    })

    _send_discord(embeds=add_embeds[:10], signal_type="ADD")
    print(f"[NOTIFY] 📈 추가 매수 → ADD 채널 ({len(add_signals)}건)")


# ═══════════════════════════════════════════════════════════
#  3. 긴급 매도 → FIRE 채널
# ═══════════════════════════════════════════════════════════

def notify_fire_sell(calc_date: date, fire_signals: list, trigger: str = ""):
    """서킷브레이커/긴급 매도 알림 → FIRE 채널"""
    if not fire_signals:
        return

    total_loss = sum(
        abs(s.get("price", 0) - s.get("entry_price", 0)) * s.get("shares", 0)
        for s in fire_signals
    )

    fire_embeds = [{
        "title": f"🚨 긴급 매도 ({len(fire_signals)}건) — {calc_date}",
        "description": (
            f"⚡ 트리거: {trigger or '서킷브레이커/DD 경보'}\n"
            f"💸 총 예상 손실: **-${total_loss:,.0f}**"
        ),
        "color": 0xdc2626,
        "footer": {"text": "QUANT AI v3.5 | 긴급 매도"},
    }]

    for s in fire_signals[:8]:
        ticker = s["ticker"]
        loss = abs(s.get("price", 0) - s.get("entry_price", 0)) * s.get("shares", 0)
        embed = {
            "title": f"■ {ticker}",
            "description": f"사유: {s.get('reason', 'CIRCUIT_BREAKER')} | {s.get('pnl_pct', 0):+.1f}%",
            "color": 0xdc2626,
            "fields": [
                {"name": "매입가", "value": f"${s.get('entry_price', 0):,.2f}", "inline": True},
                {"name": "현재가", "value": f"${s.get('price', 0):,.2f}", "inline": True},
                {"name": "예상 손실", "value": f"-${loss:,.0f}", "inline": True},
                {"name": "수량", "value": f"{s.get('shares', 0)}주", "inline": True},
            ],
        }
        fire_embeds.append(embed)

    fire_embeds.append({
        "description": "⚠️ 즉시 확인 필요",
        "color": 0xdc2626,
    })

    _send_discord(embeds=fire_embeds[:10], signal_type="FIRE")
    print(f"[NOTIFY] 🚨 긴급 매도 → FIRE 채널 ({len(fire_signals)}건)")


# ═══════════════════════════════════════════════════════════
#  4. 반등 매수 → BOUNCE 채널
# ═══════════════════════════════════════════════════════════

def notify_bounce_opportunity(calc_date: date, bounce_signals: list):
    """급락 후 반등 매수 기회 알림 → BOUNCE 채널"""
    if not bounce_signals:
        return

    bounce_embeds = [{
        "title": f"🔄 반등 매수 기회 ({len(bounce_signals)}건) — {calc_date}",
        "description": "고점수 종목 급락 → RSI 과매도 진입",
        "color": 0x06b6d4,
        "footer": {"text": "QUANT AI v3.5 | 반등 매수"},
    }]

    for s in bounce_signals[:8]:
        ticker = s["ticker"]
        embed = {
            "title": f"■ {ticker}",
            "description": f"등급 {s.get('grade', '?')} | {s.get('score', 0):.1f}점",
            "color": 0x06b6d4,
            "fields": [
                {"name": "현재가", "value": f"${s.get('price', 0):,.2f}", "inline": True},
                {"name": "낙폭", "value": f"{s.get('drop_7d', 0):+.1f}%", "inline": True},
                {"name": "RSI", "value": f"{s.get('rsi', 50):.0f}", "inline": True},
                {"name": "거래량 배율", "value": f"x{s.get('volume_ratio', 1):.1f}", "inline": True},
            ],
        }
        bounce_embeds.append(embed)

    _send_discord(embeds=bounce_embeds[:10], signal_type="BOUNCE")
    print(f"[NOTIFY] 🔄 반등 매수 → BOUNCE 채널 ({len(bounce_signals)}건)")


# ═══════════════════════════════════════════════════════════
#  5. 모닝 브리핑 → MORNING 채널
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
    signal_summary: dict = None,
):
    """
    매일 장 시작 전 모닝 브리핑 → MORNING 채널
    
    디자인 변경:
      - 시그널 상세 제거 → 요약만 (상세는 각 채널 안내)
      - fields 기반 3열 레이아웃
    """
    regime_emoji = {"BULL": "🟢", "NEUTRAL": "🟡", "BEAR": "🔴", "CRISIS": "🚨"}.get(regime, "⚪")
    spy = regime_detail.get("spy_price", 0)
    vix = regime_detail.get("vix_close", 0)
    futures = regime_detail.get("futures_pct", 0)
    vix_chg = regime_detail.get("vix_change_pct", 0)

    embeds = [{
        "title": f"☀️ 모닝 브리핑 — {calc_date}",
        "color": 0x3b82f6,
        "fields": [
            {"name": "시장 국면", "value": f"{regime_emoji} {regime}", "inline": True},
            {"name": "SPY", "value": f"${spy:,.2f}", "inline": True},
            {"name": "VIX", "value": f"{vix:.1f}" if vix else "N/A", "inline": True},
            {"name": "선물", "value": f"{futures:+.2f}%", "inline": True},
            {"name": "VIX 변동", "value": f"{vix_chg:+.1f}%", "inline": True},
        ],
        "footer": {"text": "QUANT AI v3.5 | 모닝 브리핑"},
    }]

    # ── 시그널 요약 (상세는 각 채널) ──
    if signal_summary:
        buy_cnt = signal_summary.get("buy", 0)
        sell_cnt = signal_summary.get("sell", 0)
        profit_cnt = signal_summary.get("profit", 0)
        summary_text = f"매수 추천: {buy_cnt}건 | 매도: {sell_cnt}건 | 익절: {profit_cnt}건"
        channels = []
        if buy_cnt > 0:
            channels.append("#매수-추천")
        if sell_cnt > 0:
            channels.append("#매도-시그널")
        if profit_cnt > 0:
            channels.append("#수익-실현")
        channel_text = "\n▸ 상세 → " + " ".join(channels) + " 채널 확인" if channels else ""

        embeds.append({
            "title": "📊 오늘의 시그널 요약",
            "description": summary_text + channel_text,
            "color": 0x3b82f6,
        })

    # ── 포트폴리오 현황 ──
    if portfolio_summary:
        tv = portfolio_summary.get("total_value", 0)
        dr = portfolio_summary.get("daily_return", 0)
        np_ = portfolio_summary.get("num_positions", 0)
        cash = portfolio_summary.get("cash_pct", 0)
        embeds.append({
            "title": "💼 포트폴리오",
            "color": 0x3b82f6,
            "fields": [
                {"name": "총 자산", "value": f"${tv:,.0f}", "inline": True},
                {"name": "전일 수익", "value": f"{dr:+.2f}%", "inline": True},
                {"name": "보유", "value": f"{np_}종목", "inline": True},
                {"name": "현금 비율", "value": f"{cash:.1f}%", "inline": True},
            ],
        })

    # ── 오늘의 매수 후보 TOP 5 ──
    if top_buys:
        buy_text = "\n".join([
            f"{'🥇🥈🥉'[i] if i < 3 else '▫️'} {_tn(s['ticker'])} "
            f"{s.get('grade', '')} ({s.get('score', 0):.1f}점) @ ${s.get('price', 0):,.2f}"
            for i, s in enumerate(top_buys[:5])
        ])
        embeds.append({
            "title": "🎯 오늘의 매수 후보 TOP 5",
            "description": buy_text,
            "color": 0x22c55e,
        })

    # ── 등급 변경 ──
    if grade_changes:
        gc_text = "\n".join([
            f"{'⬆️' if g['direction'] == 'UP' else '⬇️'} {_tn_short(g['ticker'])} "
            f"{g['old_grade']} → **{g['new_grade']}** ({g.get('score', 0):.1f}점)"
            for g in grade_changes[:8]
        ])
        embeds.append({
            "title": f"📊 등급 변경 ({len(grade_changes)}건)",
            "description": gc_text,
            "color": 0x8b5cf6,
        })

    # ── 어닝 발표 예정 ──
    if earnings_today:
        earn_text = "\n".join([
            f"📅 {_tn_short(e['ticker'])} | {e.get('time', 'TBD')} | "
            f"EPS 예상: ${e.get('eps_estimate', 0):.2f}"
            for e in earnings_today[:5]
        ])
        embeds.append({
            "title": f"📅 어닝 발표 ({len(earnings_today)}건)",
            "description": earn_text,
            "color": 0xf97316,
        })

    # ── 관심 종목 ──
    if watchlist:
        watch_text = "\n".join([
            f"👀 {_tn_short(w['ticker'])} | {w.get('reason', '')} | {w.get('score', 0):.1f}점"
            for w in watchlist[:5]
        ])
        embeds.append({
            "title": "👀 관심 종목",
            "description": watch_text,
            "color": 0x78716c,
        })

    _send_discord(embeds=embeds[:10], signal_type="MORNING")
    print(f"[NOTIFY] ☀️ 모닝 브리핑 → MORNING 채널")


# ═══════════════════════════════════════════════════════════
#  6. 일일 성과 → PERF 채널
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
    """일일 포트폴리오 성과 리포트 → PERF 채널"""
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
        fields.append({"name": "🏆 최고", "value": f"{_tn_short(best_ticker)} ({best_pnl:+.1f}%)", "inline": True})
    if worst_ticker:
        fields.append({"name": "💀 최저", "value": f"{_tn_short(worst_ticker)} ({worst_pnl:+.1f}%)", "inline": True})

    embeds = [{
        "title": f"📈 일일 성과 — {calc_date}",
        "color": color,
        "fields": fields,
        "footer": {"text": "QUANT AI v3.5 | 일일 성과"},
    }]
    _send_discord(embeds=embeds, signal_type="PERF")
    print(f"[NOTIFY] 📈 일일 성과 → PERF 채널 ({daily_return:+.2f}%)")


# ═══════════════════════════════════════════════════════════
#  7. 등급 변경 → ALERT 채널
# ═══════════════════════════════════════════════════════════

def notify_grade_changes(calc_date: date, upgrades: list, downgrades: list):
    """보유종목 등급 변경 알림 → ALERT 채널"""
    if not upgrades and not downgrades:
        return

    embeds = []

    if downgrades:
        down_text = "\n".join([
            f"⬇️ {_tn_short(g['ticker'])} {g['old_grade']} → **{g['new_grade']}** "
            f"| {g.get('old_score', 0):.1f} → {g.get('new_score', 0):.1f}점"
            for g in downgrades[:8]
        ])
        embeds.append({
            "title": f"⚠️ 등급 변경 — {calc_date}",
            "description": f"⬇️ **하락** ({len(downgrades)}건)\n{down_text}",
            "color": 0xef4444,
        })

    if upgrades:
        up_text = "\n".join([
            f"⬆️ {_tn_short(g['ticker'])} {g['old_grade']} → **{g['new_grade']}** "
            f"| {g.get('old_score', 0):.1f} → {g.get('new_score', 0):.1f}점"
            for g in upgrades[:8]
        ])
        embeds.append({
            "title": f"✨ 등급 변경 — {calc_date}" if not downgrades else None,
            "description": f"⬆️ **상승** ({len(upgrades)}건)\n{up_text}",
            "color": 0x22c55e,
        })
        # title 중복 방지
        if downgrades:
            embeds[-1].pop("title", None)

    # footer는 마지막 embed에만
    embeds[-1]["footer"] = {"text": "QUANT AI v3.5 | 등급 변경"}

    _send_discord(embeds=embeds[:10], signal_type="ALERT")
    print(f"[NOTIFY] 📊 등급 변경 → ALERT 채널 (⬆{len(upgrades)} ⬇{len(downgrades)})")


# ═══════════════════════════════════════════════════════════
#  8. 어닝 D-Day → ALERT 채널
# ═══════════════════════════════════════════════════════════

def notify_earnings_alert(calc_date: date, earnings_stocks: list):
    """보유종목 어닝 발표 당일 알림 → ALERT 채널"""
    if not earnings_stocks:
        return

    earn_embeds = [{
        "title": f"📅 어닝 D-Day ({len(earnings_stocks)}건) — {calc_date}",
        "color": 0xf59e0b,
        "footer": {"text": "QUANT AI v3.5 | 어닝 알림"},
    }]

    for e in earnings_stocks[:8]:
        ticker = e["ticker"]
        embed = {
            "title": f"■ {ticker} | {e.get('time', 'TBD')}",
            "color": 0xf59e0b,
            "fields": [
                {"name": "EPS 예상", "value": f"${e.get('eps_estimate', 0):.2f}", "inline": True},
                {"name": "매출 예상", "value": f"${e.get('rev_estimate', 0)/1e9:.1f}B", "inline": True},
                {"name": "등급", "value": f"{e.get('grade', '?')}", "inline": True},
                {"name": "보유", "value": f"{e.get('shares', 0)}주", "inline": True},
            ],
        }
        earn_embeds.append(embed)

    earn_embeds.append({
        "description": "⚠️ 어닝 전후 변동성 주의",
        "color": 0xf59e0b,
    })

    _send_discord(embeds=earn_embeds[:10], signal_type="ALERT")
    print(f"[NOTIFY] 📅 어닝 D-Day → ALERT 채널 ({len(earnings_stocks)}건)")


# ═══════════════════════════════════════════════════════════
#  9. 긴급 알림 → ALERT 채널
# ═══════════════════════════════════════════════════════════

def notify_emergency(title: str, message: str):
    embeds = [{
        "title": f"🚨 {title}",
        "description": message,
        "color": 0xff0000,
        "footer": {"text": "QUANT AI v3.5 | 긴급 알림"},
    }]
    _send_discord(embeds=embeds, signal_type="ALERT")
    if CHANNEL in ("slack", "all"):
        _send_slack(f"🚨 {title}\n{message}")
    if CHANNEL in ("telegram", "all"):
        _send_telegram(f"🚨 <b>{title}</b>\n{message}")
    print(f"[NOTIFY] 🚨 긴급 알림 → ALERT 채널")


# ═══════════════════════════════════════════════════════════
#  10. 리스크 경고 → RISK 채널
# ═══════════════════════════════════════════════════════════

def notify_risk_warning(
    calc_date: date,
    dd_mode: str,
    drawdown_pct: float,
    cb_level: str = "",
    losing_streak: int = 0,
    concentration_warn: list = None,
):
    """리스크 상태 경고 → RISK 채널"""
    dd_emoji = {"NORMAL": "🟢", "CAUTION": "🟡", "WARNING": "🟠", "DANGER": "🔴", "CRITICAL": "🚨"}

    fields = [
        {"name": "DD 단계", "value": f"{dd_emoji.get(dd_mode, '⚪')} {dd_mode}", "inline": True},
        {"name": "낙폭", "value": f"{drawdown_pct:.1f}%", "inline": True},
    ]
    if cb_level:
        fields.append({"name": "서킷브레이커", "value": f"{cb_level}", "inline": True})
        fields.append({"name": "연패", "value": f"{losing_streak}연패", "inline": True})
    if concentration_warn:
        warn_text = " | ".join([f"{w['sector']} {w['pct']:.0f}%" for w in concentration_warn[:3]])
        fields.append({"name": "집중도 경고", "value": warn_text, "inline": False})

    embeds = [{
        "title": f"⚠️ 리스크 경고 — {calc_date}",
        "color": 0xf97316,
        "fields": fields,
        "footer": {"text": "QUANT AI v3.5 | 리스크"},
    }]
    _send_discord(embeds=embeds, signal_type="RISK")
    print(f"[NOTIFY] ⚠️ 리스크 경고 → RISK 채널 (DD: {dd_mode})")


# ═══════════════════════════════════════════════════════════
#  11. 시장 국면 전환 → ALERT 채널
# ═══════════════════════════════════════════════════════════

def notify_regime_change(calc_date: date, old_regime: str, new_regime: str, detail: str = ""):
    old_e = {"BULL": "🟢", "NEUTRAL": "🟡", "BEAR": "🔴", "CRISIS": "🚨"}.get(old_regime, "⚪")
    new_e = {"BULL": "🟢", "NEUTRAL": "🟡", "BEAR": "🔴", "CRISIS": "🚨"}.get(new_regime, "⚪")
    embeds = [{
        "title": f"🔄 시장 국면 전환 — {calc_date}",
        "description": f"{old_e} **{old_regime}** → {new_e} **{new_regime}**\n\n{detail}",
        "color": 0xff6600,
        "footer": {"text": "QUANT AI v3.5 | 국면 전환"},
    }]
    _send_discord(embeds=embeds, signal_type="ALERT")
    print(f"[NOTIFY] 🔄 국면 전환 → ALERT ({old_regime} → {new_regime})")


# ═══════════════════════════════════════════════════════════
#  12. 배치 완료 → SYSTEM 채널
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

    # 소요시간 포맷
    mins, secs = divmod(int(elapsed_seconds), 60)
    time_str = f"{mins}분 {secs}초" if mins > 0 else f"{secs}초"

    embeds = [{
        "title": f"{status_emoji} 배치 완료 — {calc_date}",
        "description": "\n".join(detail_lines),
        "color": 0x22c55e if fail == 0 else 0xef4444,
        "fields": [
            {"name": "성공", "value": f"{ok}건", "inline": True},
            {"name": "실패", "value": f"{fail}건", "inline": True},
            {"name": "소요 시간", "value": time_str, "inline": True},
        ],
        "footer": {"text": "QUANT AI v3.5 | 시스템"},
    }]
    _send_discord(embeds=embeds, signal_type="SYSTEM")
    print(f"[NOTIFY] {status_emoji} 배치 완료 → SYSTEM 채널")


# ═══════════════════════════════════════════════════════════
#  13. 주간 리밸런싱 → REPORT 채널
# ═══════════════════════════════════════════════════════════

def notify_weekly_rebalance(calc_date: date, buys: list, sells: list, adjusts: list, turnover: float):
    lines = []
    for b in buys[:5]:
        lines.append(f"🟢 매수: {_tn_short(b['ticker'])} {b.get('shares', 0)}주")
    for s in sells[:5]:
        lines.append(f"🔴 매도: {_tn_short(s['ticker'])} {s.get('shares', 0)}주")
    for a in adjusts[:5]:
        direction = "⬆️" if a.get("direction") == "UP" else "⬇️"
        lines.append(f"{direction} 조정: {_tn_short(a['ticker'])} {a.get('shares', 0)}주")

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
        "footer": {"text": "QUANT AI v3.5 | 주간 리밸런싱"},
    }]
    _send_discord(embeds=embeds, signal_type="REPORT")
    print(f"[NOTIFY] 🔄 리밸런싱 → REPORT 채널")


# ═══════════════════════════════════════════════════════════
#  14. 주간 성과 → REPORT 채널
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
    fields = [
        {"name": "주간 수익률", "value": f"{week_return:+.2f}%", "inline": True},
        {"name": "SPY", "value": f"{spy_return:+.2f}%", "inline": True},
        {"name": "알파", "value": f"{alpha:+.2f}%", "inline": True},
        {"name": "총 자산", "value": f"${total_value:,.0f}", "inline": True},
        {"name": "승률", "value": f"{win_rate:.0f}%", "inline": True},
        {"name": "거래 수", "value": f"{num_trades}건", "inline": True},
    ]
    if best_ticker:
        fields.append({"name": "🏆 MVP", "value": f"{_tn_short(best_ticker)} ({best_pnl:+.1f}%)", "inline": True})
    if worst_ticker:
        fields.append({"name": "💀 최악", "value": f"{_tn_short(worst_ticker)} ({worst_pnl:+.1f}%)", "inline": True})

    embeds = [{
        "title": f"📊 주간 성과 리포트 — {calc_date}",
        "color": 0x22c55e if week_return >= 0 else 0xef4444,
        "fields": fields,
        "footer": {"text": "QUANT AI v3.5 | 주간 리포트"},
    }]
    _send_discord(embeds=embeds, signal_type="REPORT")
    print(f"[NOTIFY] 📊 주간 리포트 → REPORT 채널 ({week_return:+.2f}%)")


# ═══════════════════════════════════════════════════════════
#  15. 백테스트 결과 → BACKTEST 채널
# ═══════════════════════════════════════════════════════════

def notify_backtest_result(
    period_start: date,
    period_end: date,
    strategy_name: str = "QUANT AI v3.5 Multi-Factor",
    total_return: float = 0,
    annual_return: float = 0,
    max_drawdown: float = 0,
    sharpe_ratio: float = 0,
    win_rate: float = 0,
    spy_alpha: float = 0,
    num_trades: int = 0,
    avg_holding_days: int = 0,
):
    """백테스트 결과 알림 → BACKTEST 채널"""
    embeds = [{
        "title": f"🧪 백테스트 완료 — {period_start} ~ {period_end}",
        "description": f"전략: {strategy_name}",
        "color": 0x8b5cf6,
        "fields": [
            {"name": "총 수익률", "value": f"{total_return:+.1f}%", "inline": True},
            {"name": "연환산", "value": f"{annual_return:+.1f}%", "inline": True},
            {"name": "최대 낙폭", "value": f"{max_drawdown:.1f}%", "inline": True},
            {"name": "샤프 비율", "value": f"{sharpe_ratio:.2f}", "inline": True},
            {"name": "승률", "value": f"{win_rate:.1f}%", "inline": True},
            {"name": "SPY 알파", "value": f"{spy_alpha:+.1f}%", "inline": True},
            {"name": "거래 수", "value": f"{num_trades}건", "inline": True},
            {"name": "평균 보유", "value": f"{avg_holding_days}일", "inline": True},
        ],
        "footer": {"text": "QUANT AI v3.5 | 백테스트"},
    }]
    _send_discord(embeds=embeds, signal_type="BACKTEST")
    print(f"[NOTIFY] 🧪 백테스트 → BACKTEST 채널 ({total_return:+.1f}%)")



# ═══════════════════════════════════════════════════════════
#  안전장치용 함수 (scheduler 연동)
# ═══════════════════════════════════════════════════════════

def check_price_freshness(max_stale_hours: int = 24) -> dict:
    """stock_prices_realtime 가격 신선도 검증"""
    try:
        from db_pool import get_cursor
        from datetime import datetime, timedelta
        cutoff = datetime.now() - timedelta(hours=max_stale_hours)
        with get_cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) as total,
                       COUNT(*) FILTER (WHERE spr.updated_at >= %s) as fresh,
                       COUNT(*) FILTER (WHERE spr.updated_at < %s OR spr.updated_at IS NULL) as stale
                FROM stock_prices_realtime spr
                JOIN stocks s ON s.stock_id = spr.stock_id
                WHERE s.is_active = TRUE
            """, (cutoff, cutoff))
            row = cur.fetchone()
        total = int(row["total"] or 0)
        stale = int(row["stale"] or 0)
        stale_pct = round(stale / total * 100, 1) if total > 0 else 100
        stale_list = []
        if stale > 0:
            with get_cursor() as cur:
                cur.execute("""SELECT s.ticker FROM stock_prices_realtime spr
                    JOIN stocks s ON s.stock_id = spr.stock_id
                    WHERE s.is_active = TRUE AND (spr.updated_at < %s OR spr.updated_at IS NULL)
                    LIMIT 10""", (cutoff,))
                stale_list = [{"ticker": r["ticker"]} for r in cur.fetchall()]
        import os
        threshold = int(os.environ.get("PRICE_FAIL_THRESHOLD_PCT", "10"))
        return {"total": total, "fresh": int(row["fresh"] or 0), "stale_count": stale,
                "stale_pct": stale_pct, "stale": stale_list, "abort": stale_pct >= threshold}
    except Exception as e:
        logger.error(f"[FRESHNESS] 검증 실패: {e}")
        return {"total": 0, "fresh": 0, "stale_count": 0, "stale_pct": 0, "stale": [], "abort": False}


def notify_price_fetch_failure(calc_date, error_msg: str, stale_tickers: list = None):
    """가격 수집 실패 긴급 알림"""
    stale_str = ", ".join(stale_tickers[:10]) if stale_tickers else "N/A"
    embeds = [{"title": "🚨 가격 수집 실패 — 배치 중단", "color": 0xFF0000,
        "fields": [{"name": "날짜", "value": str(calc_date), "inline": True},
                   {"name": "오류", "value": str(error_msg)[:200], "inline": False},
                   {"name": "Stale 종목", "value": stale_str, "inline": False}],
        "footer": {"text": "QUANT AI 안전장치 발동"}}]
    _send_discord(embeds=embeds, signal_type="ALERT")
    logger.warning(f"[NOTIFY] 가격 수집 실패: {error_msg[:100]}")