#!/usr/bin/env python3
"""
test_notify.py — Discord 알림 연결 테스트
==========================================
.env에 설정된 웹후크로 실제 테스트 메시지 전송.

실행:
  cd backend
  python test_notify.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv()

from notifier import _WEBHOOK_MAP, _FALLBACK_URL, _get_discord_url, _send_discord, CHANNEL

print("=" * 60)
print("  QUANT AI — Discord 알림 연결 테스트")
print("=" * 60)

# 1. 설정 상태 확인
print("\n── 채널별 웹후크 상태 ──")
configured = 0
for ch_type, url in _WEBHOOK_MAP.items():
    status = "✅ 설정됨" if url else "❌ 미설정"
    if url:
        configured += 1
        # URL 마스킹
        masked = url[:45] + "..." + url[-10:] if len(url) > 60 else url
    else:
        masked = ""
    print(f"  {ch_type:8s} : {status}  {masked}")

print(f"\n  FALLBACK  : {'✅ '+_FALLBACK_URL[:40]+'...' if _FALLBACK_URL else '❌ 미설정 (채널별 URL로 대체)'}")
print(f"  CHANNEL   : {CHANNEL}")
print(f"  설정된 채널: {configured}/8")

if configured == 0 and not _FALLBACK_URL:
    print("\n⚠️  웹후크가 하나도 설정되지 않았습니다! .env 파일을 확인하세요.")
    sys.exit(1)

# 2. 실제 전송 테스트
print("\n── 전송 테스트 ──")
test_embed = {
    "title": "🧪 QUANT AI 알림 테스트",
    "description": "이 메시지가 보이면 Discord 알림이 정상 동작합니다!",
    "color": 0x22c55e,
    "fields": [
        {"name": "버전", "value": "v3.3", "inline": True},
        {"name": "채널 수", "value": f"{configured}개 설정", "inline": True},
    ],
    "footer": {"text": "test_notify.py에서 발송"},
}

# REPORT 채널로 테스트
result = _send_discord(embeds=[test_embed], signal_type="REPORT")
if result:
    print("  ✅ REPORT 채널 전송 성공!")
else:
    # BUY 채널로 재시도
    result = _send_discord(embeds=[test_embed], signal_type="BUY")
    if result:
        print("  ✅ BUY 채널 전송 성공! (REPORT 채널 미설정, BUY로 대체)")
    else:
        print("  ❌ 전송 실패 — URL이 유효한지 확인하세요")

print("\n" + "=" * 60)
if result:
    print("  🎉 Discord 알림 정상 동작!")
else:
    print("  ⚠️  알림 전송 실패 — .env 웹후크 URL 확인 필요")
print("=" * 60)
