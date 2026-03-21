"""
notification/channels.py — 13채널 웹후크 라우팅
=================================================
.env에서 채널별 웹후크 URL을 읽어 시그널 유형별로 분배.
개별 웹후크가 없으면 DISCORD_WEBHOOK_URL (통합 fallback) 사용.
"""
import os

# 채널 매핑: signal_type → .env key → 채널 설명
CHANNEL_MAP = {
    # 기존 8채널
    "BUY":      {"env": "DISCORD_WEBHOOK_BUY",      "name": "돈 복사 시작",    "emoji": "🟢"},
    "SELL":     {"env": "DISCORD_WEBHOOK_SELL",     "name": "탈출은 지능순",    "emoji": "🔴"},
    "PROFIT":   {"env": "DISCORD_WEBHOOK_PROFIT",   "name": "칼춤 피날레",     "emoji": "💰"},
    "ADD":      {"env": "DISCORD_WEBHOOK_ADD",      "name": "희망고문",        "emoji": "🟡"},
    "FIRE":     {"env": "DISCORD_WEBHOOK_FIRE",     "name": "풀악셀",         "emoji": "🔥"},
    "BOUNCE":   {"env": "DISCORD_WEBHOOK_BOUNCE",   "name": "지구 내핵 도착",  "emoji": "🚀"},
    "REPORT":   {"env": "DISCORD_WEBHOOK_REPORT",   "name": "일일 뻐꾸기",    "emoji": "📊"},
    "ALERT":    {"env": "DISCORD_WEBHOOK_ALERT",    "name": "한강 수온 체크기", "emoji": "🚨"},
    # 신규 5채널
    "MORNING":  {"env": "DISCORD_WEBHOOK_MORNING",  "name": "출근 도장",       "emoji": "☀️"},
    "PERF":     {"env": "DISCORD_WEBHOOK_PERF",     "name": "성적표",         "emoji": "🏆"},
    "SYSTEM":   {"env": "DISCORD_WEBHOOK_SYSTEM",   "name": "정비소",         "emoji": "🔧"},
    "RISK":     {"env": "DISCORD_WEBHOOK_RISK",     "name": "리스크 계기판",   "emoji": "📐"},
    "BACKTEST": {"env": "DISCORD_WEBHOOK_BACKTEST", "name": "실험실",         "emoji": "🧪"},
}


def get_webhook(signal_type: str) -> str:
    """시그널 유형 → Discord 웹후크 URL"""
    ch = CHANNEL_MAP.get(signal_type.upper(), {})
    env_key = ch.get("env", "")
    url = os.environ.get(env_key, "")
    if url:
        return url
    return os.environ.get("DISCORD_WEBHOOK_URL", "")


def get_channel_name(signal_type: str) -> str:
    ch = CHANNEL_MAP.get(signal_type.upper(), {})
    return ch.get("name", signal_type)


def get_channel_emoji(signal_type: str) -> str:
    ch = CHANNEL_MAP.get(signal_type.upper(), {})
    return ch.get("emoji", "📌")


def get_webhook_status() -> dict:
    """모든 채널의 웹후크 설정 상태"""
    return {
        ch_type: {
            "name": info["name"],
            "configured": bool(os.environ.get(info["env"], "")),
            "using_fallback": not bool(os.environ.get(info["env"], "")) and bool(os.environ.get("DISCORD_WEBHOOK_URL", "")),
        }
        for ch_type, info in CHANNEL_MAP.items()
    }
