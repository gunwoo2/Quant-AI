"""
notification/templates.py — Discord Embed 템플릿
===================================================
각 알림 유형별 Embed 생성 함수.
notifier.py에서 호출하여 일관된 형식의 메시지를 생성합니다.
"""
from datetime import date
from typing import List, Dict, Optional


# ═══════════════════════════════════════════════════════════
#  색상 상수
# ═══════════════════════════════════════════════════════════

COLORS = {
    "BUY":     0x22c55e,  # green
    "SELL":    0xef4444,  # red
    "PROFIT":  0xfbbf24,  # amber
    "ADD":     0xf59e0b,  # yellow
    "FIRE":    0xf97316,  # orange
    "BOUNCE":  0x06b6d4,  # cyan
    "REPORT":  0x3b82f6,  # blue
    "ALERT":   0xff0000,  # red
    "MORNING": 0xfbbf24,  # amber
    "PERF":    0x8b5cf6,  # purple
    "SYSTEM":  0x78716c,  # gray
    "RISK":    0xea580c,  # deep orange
    "BACKTEST":0x06b6d4,  # cyan
}

REGIME_EMOJI = {"BULL": "🟢", "NEUTRAL": "🟡", "BEAR": "🔴", "CRISIS": "🚨"}


def regime_header(regime: str, regime_detail: dict) -> str:
    emoji = REGIME_EMOJI.get(regime, "⚪")
    spy = regime_detail.get("spy_price", 0)
    vix = regime_detail.get("vix_close", 0)
    txt = f"{emoji} 시장: **{regime}** | SPY ${spy:,.2f}"
    if vix:
        txt += f" | VIX {vix:.1f}"
    return txt


# ═══════════════════════════════════════════════════════════
#  매수 Embed
# ═══════════════════════════════════════════════════════════

def buy_embeds(calc_date: date, regime: str, regime_detail: dict, signals: list) -> list:
    embeds = [{
        "title": f"💵 돈 복사 시작 — {calc_date} ({len(signals)}건)",
        "description": regime_header(regime, regime_detail),
        "color": COLORS["BUY"],
    }]
    for s in signals[:8]:
        embeds.append({
            "title": f"🟢 BUY {s['ticker']}",
            "fields": [
                {"name": "등급", "value": f"{s.get('grade', '')} ({s['score']:.1f}점)", "inline": True},
                {"name": "매수가", "value": f"${s['price']:,.2f}", "inline": True},
                {"name": "수량", "value": f"{s['shares']}주", "inline": True},
                {"name": "투자금", "value": f"${s['amount']:,.0f}", "inline": True},
                {"name": "비중", "value": f"{s['weight']:.1f}%", "inline": True},
                {"name": "손절가", "value": f"${s['stop_loss']:,.2f}", "inline": True},
            ],
            "color": COLORS["BUY"],
            "footer": {"text": f"섹터: {s.get('sector', 'N/A')}"},
        })
    return embeds


def sell_embeds(calc_date: date, signals: list) -> list:
    loss = [s for s in signals if s.get("pnl_pct", 0) < 0]
    if not loss:
        return []
    embeds = [{
        "title": f"🏃 탈출은 지능순 — {calc_date} ({len(loss)}건)",
        "description": "손절 매도! 더 늦기 전에 빠져나와라",
        "color": COLORS["SELL"],
    }]
    for s in loss[:8]:
        pnl = s.get("pnl_pct", 0)
        loss_amt = abs(s.get("price", 0) - s.get("entry_price", 0)) * s.get("shares", 0)
        embeds.append({
            "title": f"🔴 SELL {s['ticker']} ({pnl:+.1f}%)",
            "fields": [
                {"name": "사유", "value": s.get("reason", "STOP_LOSS"), "inline": True},
                {"name": "현재가", "value": f"${s.get('price', 0):,.2f}", "inline": True},
                {"name": "매수가", "value": f"${s.get('entry_price', 0):,.2f}", "inline": True},
                {"name": "손실액", "value": f"-${loss_amt:,.0f}", "inline": True},
                {"name": "보유일", "value": f"{s.get('holding_days', 0)}일", "inline": True},
            ],
            "color": COLORS["SELL"],
        })
    return embeds


def profit_embeds(calc_date: date, signals: list) -> list:
    profs = [s for s in signals if s.get("pnl_pct", 0) >= 0]
    if not profs:
        return []
    embeds = [{
        "title": f"💃 칼춤 피날레 — {calc_date} ({len(profs)}건)",
        "description": "수익 실현! 이게 투자지~",
        "color": COLORS["PROFIT"],
    }]
    for s in profs[:8]:
        pnl = s.get("pnl_pct", 0)
        prof_amt = (s.get("price", 0) - s.get("entry_price", 0)) * s.get("shares", 0)
        embeds.append({
            "title": f"💰 PROFIT {s['ticker']} ({pnl:+.1f}%)",
            "fields": [
                {"name": "사유", "value": s.get("reason", "PROFIT_TAKE"), "inline": True},
                {"name": "매도가", "value": f"${s.get('price', 0):,.2f}", "inline": True},
                {"name": "수익액", "value": f"+${prof_amt:,.0f}", "inline": True},
                {"name": "보유일", "value": f"{s.get('holding_days', 0)}일", "inline": True},
            ],
            "color": COLORS["PROFIT"],
        })
    return embeds


def add_embeds(calc_date: date, signals: list) -> list:
    if not signals:
        return []
    embeds = [{
        "title": f"🥲 희망고문 — {calc_date} ({len(signals)}건)",
        "description": "점수는 좋은데 가격이 떨어졌다.. 평단 낮출 기회?",
        "color": COLORS["ADD"],
    }]
    for s in signals[:8]:
        embeds.append({
            "title": f"🟡 물타기 {s['ticker']} ({s.get('drop_pct', 0):+.1f}%)",
            "fields": [
                {"name": "등급", "value": f"{s.get('grade', '')} ({s['score']:.1f}점)", "inline": True},
                {"name": "현재가", "value": f"${s['current_price']:,.2f}", "inline": True},
                {"name": "새 평단", "value": f"${s.get('new_avg_price', 0):,.2f}", "inline": True},
                {"name": "추가", "value": f"+{s['add_shares']}주 (${s['add_amount']:,.0f})", "inline": True},
            ],
            "color": COLORS["ADD"],
        })
    return embeds


def fire_embeds(calc_date: date, signals: list) -> list:
    if not signals:
        return []
    embeds = [{
        "title": f"🔥 풀악셀 — {calc_date} ({len(signals)}건)",
        "description": "오르는 종목 + 올라가는 점수 = 더 태워!",
        "color": COLORS["FIRE"],
    }]
    for s in signals[:8]:
        embeds.append({
            "title": f"🔥 불타기 {s['ticker']} ({s.get('gain_pct', 0):+.1f}%)",
            "fields": [
                {"name": "등급", "value": f"{s.get('grade', '')} ({s['score']:.1f}점)", "inline": True},
                {"name": "현재가", "value": f"${s['current_price']:,.2f}", "inline": True},
                {"name": "추가", "value": f"+{s['add_shares']}주 (${s['add_amount']:,.0f})", "inline": True},
                {"name": "점수추세", "value": s.get("score_trend", "↑"), "inline": True},
            ],
            "color": COLORS["FIRE"],
        })
    return embeds


def bounce_embeds(calc_date: date, signals: list) -> list:
    if not signals:
        return []
    embeds = [{
        "title": f"🚀 지구 내핵 도착 — {calc_date} ({len(signals)}건)",
        "description": "바닥 다지고 반등 시작! 기술적 반전 포착",
        "color": COLORS["BOUNCE"],
    }]
    for s in signals[:8]:
        embeds.append({
            "title": f"🚀 반등 {s['ticker']}",
            "fields": [
                {"name": "등급", "value": f"{s.get('grade', '')} ({s['score']:.1f}점)", "inline": True},
                {"name": "현재가", "value": f"${s['current_price']:,.2f}", "inline": True},
                {"name": "RSI", "value": f"{s.get('rsi', 50):.0f} (과매도 탈출)", "inline": True},
                {"name": "시그널", "value": s.get("reason", "RSI 반등"), "inline": True},
            ],
            "color": COLORS["BOUNCE"],
        })
    return embeds


def morning_briefing_embed(calc_date, regime, regime_detail, dd_state, risk_report,
                            watchlist, positions_summary, factor_ic=None) -> list:
    emoji = REGIME_EMOJI.get(regime, "⚪")
    spy = regime_detail.get("spy_price", 0)
    vix = regime_detail.get("vix_close", 0)
    dd_pct = getattr(dd_state, "drawdown_pct", 0) * 100 if dd_state else 0
    dd_mode = getattr(dd_state, "mode", "NORMAL")
    dd_m = {"NORMAL": "🟢", "CAUTION": "🟡", "WARNING": "🟠", "DANGER": "🔴", "EMERGENCY": "🚨"}

    fields = [
        {"name": "시장", "value": f"{emoji} {regime}", "inline": True},
        {"name": "SPY", "value": f"${spy:,.2f}", "inline": True},
        {"name": "VIX", "value": f"{vix:.1f}" if vix else "N/A", "inline": True},
        {"name": "DD 모드", "value": f"{dd_m.get(str(dd_mode), '⚪')} {dd_mode} ({dd_pct:+.1f}%)", "inline": True},
    ]

    if risk_report:
        var95 = getattr(risk_report, "var_95_pct", 0)
        fields.append({"name": "VaR(95%)", "value": f"{var95:.2%}", "inline": True})

    if positions_summary:
        fields.append({"name": "보유", "value": f"{positions_summary.get('count', 0)}종목", "inline": True})
        fields.append({"name": "평가액", "value": f"${positions_summary.get('total', 0):,.0f}", "inline": True})
        fields.append({"name": "현금", "value": f"{positions_summary.get('cash_pct', 0):.1f}%", "inline": True})

    embeds = [{
        "title": f"☀️ 출근 도장 — {calc_date}",
        "fields": fields,
        "color": COLORS["MORNING"],
        "footer": {"text": "QUANT AI v3.3 | 투자 참고용"},
    }]

    # 주의 종목
    if watchlist:
        watch_lines = []
        for w in watchlist[:5]:
            watch_lines.append(f"{w.get('emoji', '📌')} {w['ticker']} — {w['note']}")
        embeds[0]["description"] = "\n".join(watch_lines)

    return embeds


def risk_dashboard_embed(calc_date, report) -> list:
    dd_m = {"NORMAL": "🟢", "CAUTION": "🟡", "WARNING": "🟠", "DANGER": "🔴", "EMERGENCY": "🚨"}
    dm = getattr(report, "dd_mode", "NORMAL")

    embeds = [{
        "title": f"📐 리스크 계기판 — {calc_date}",
        "fields": [
            {"name": "DD 모드", "value": f"{dd_m.get(dm, '⚪')} {dm}", "inline": True},
            {"name": "VaR(95%)", "value": f"{report.var_95_pct:.2%} (${report.var_95_dollar:,.0f})", "inline": True},
            {"name": "VaR(99%)", "value": f"{report.var_99_pct:.2%} (${report.var_99_dollar:,.0f})", "inline": True},
            {"name": "CVaR(95%)", "value": f"{report.cvar_95_pct:.2%}", "inline": True},
            {"name": "CF-VaR(99%)", "value": f"{report.cornish_fisher_99_pct:.2%}", "inline": True},
            {"name": "Beta", "value": f"{report.portfolio_beta:.2f}", "inline": True},
            {"name": "변동성(연)", "value": f"{report.portfolio_vol_annual:.1%}", "inline": True},
            {"name": "샤프", "value": f"{report.sharpe_ratio:.2f}", "inline": True},
            {"name": "소르티노", "value": f"{report.sortino_ratio:.2f}", "inline": True},
            {"name": "최대섹터", "value": f"{report.max_sector_pct:.1%}", "inline": True},
            {"name": "평균상관", "value": f"{report.avg_correlation:.2f}", "inline": True},
            {"name": "HHI", "value": f"{report.herfindahl_index:.3f}", "inline": True},
        ],
        "color": COLORS["RISK"],
        "footer": {"text": f"Stress: 2008={report.stress_2008:.1%} | 2020={report.stress_2020:.1%} | VIX40={report.stress_vix40:.1%}"},
    }]

    if report.alerts:
        embeds[0]["description"] = "⚠️ " + " | ".join(report.alerts)

    return embeds


def weekly_performance_embed(calc_date, data) -> list:
    ret = data.get("return_pct", 0)
    vs_spy = data.get("vs_spy_pct", 0)
    wr = data.get("win_rate", 0)
    pf = data.get("profit_factor", 0)
    sharpe = data.get("sharpe_ratio", 0)
    mdd = data.get("max_drawdown", 0)

    embeds = [{
        "title": f"🏆 주간 성적표 — {calc_date}",
        "fields": [
            {"name": "총 자산", "value": f"${data.get('end_value', 0):,.0f}", "inline": True},
            {"name": "주간 수익", "value": f"{ret:+.2%}", "inline": True},
            {"name": "vs SPY", "value": f"{vs_spy:+.2%}", "inline": True},
            {"name": "승률", "value": f"{wr:.1%} ({data.get('winning_trades', 0)}/{data.get('total_trades', 0)})", "inline": True},
            {"name": "손익비", "value": f"{pf:.2f}:1", "inline": True},
            {"name": "샤프비율", "value": f"{sharpe:.2f}", "inline": True},
            {"name": "MDD", "value": f"{mdd:.2%}", "inline": True},
            {"name": "회전율", "value": f"{data.get('turnover_pct', 0):.1%}", "inline": True},
            {"name": "거래비용", "value": f"${data.get('total_costs', 0):,.0f}", "inline": True},
        ],
        "color": COLORS["PERF"],
        "footer": {"text": "QUANT AI v3.3 | 투자 참고용, 투자 판단은 본인 책임"},
    }]

    # Top winners / losers
    winners = data.get("top_winners", [])
    losers = data.get("top_losers", [])
    desc_lines = []
    if winners:
        desc_lines.append("🏆 **Top Winners**")
        for w in winners[:3]:
            desc_lines.append(f"  {w['ticker']} {w['pnl_pct']:+.1%} (+${w['pnl_dollar']:,.0f})")
    if losers:
        desc_lines.append("💀 **Worst Losers**")
        for l in losers[:3]:
            desc_lines.append(f"  {l['ticker']} {l['pnl_pct']:+.1%} (-${abs(l['pnl_dollar']):,.0f})")
    if desc_lines:
        embeds[0]["description"] = "\n".join(desc_lines)

    return embeds


def system_warning_embed(category, title, detail, severity="WARNING") -> list:
    sev_colors = {"INFO": 0x3b82f6, "WARNING": 0xf59e0b, "CRITICAL": 0xef4444}
    sev_emoji = {"INFO": "ℹ️", "WARNING": "⚠️", "CRITICAL": "🚨"}
    return [{
        "title": f"{sev_emoji.get(severity, '📌')} {title}",
        "description": detail,
        "color": sev_colors.get(severity, 0x78716c),
        "fields": [
            {"name": "카테고리", "value": category, "inline": True},
            {"name": "심각도", "value": severity, "inline": True},
        ],
        "footer": {"text": "QUANT AI 정비소"},
    }]


def embeds_to_text(embeds: list) -> str:
    """Discord embed → 플레인텍스트 (Slack/Telegram fallback)"""
    lines = []
    for e in embeds:
        if e.get("title"):
            lines.append(e["title"])
        if e.get("description"):
            lines.append(e["description"])
        for f in e.get("fields", []):
            lines.append(f"  {f['name']}: {f['value']}")
        lines.append("")
    return "\n".join(lines)
