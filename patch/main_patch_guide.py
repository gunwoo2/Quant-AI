"""
main.py 패치 가이드 — 신규 라우터 등록
======================================

아래 2줄을 main.py의 라우터 import/register 부분에 추가합니다.

1. import 추가 (기존 optional import 블록 근처):
"""

# ── 기존 optional import 패턴 따라서 추가 ──
# try:
#     from routers import explain as _explain_router
#     from routers import cross_asset as _cross_asset_router
# except ImportError:
#     _explain_router = None
#     _cross_asset_router = None

# ── 라우터 등록 (기존 optional 패턴) ──
# if _explain_router:
#     app.include_router(_explain_router.router, prefix="/api", tags=["AI Explain"])
# if _cross_asset_router:
#     app.include_router(_cross_asset_router.router, prefix="/api", tags=["Cross-Asset"])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 또는 간단하게 (try-except 방식):
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MAIN_PY_PATCH = """
# ── 신규 라우터 (v3.3) ──
try:
    from routers import explain
    app.include_router(explain.router, prefix="/api", tags=["AI Explain"])
    print("[MAIN] ✅ explain router loaded")
except Exception as e:
    print(f"[MAIN] ⚠ explain router skip: {e}")

try:
    from routers import cross_asset
    app.include_router(cross_asset.router, prefix="/api", tags=["Cross-Asset"])
    print("[MAIN] ✅ cross_asset router loaded")
except Exception as e:
    print(f"[MAIN] ⚠ cross_asset router skip: {e}")
"""
