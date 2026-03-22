"""
batch/batch_chart_patterns.py — 차트 패턴 감지 (17종, 무료)
================================================================
stock_prices_daily 기반 규칙형 패턴 감지 → chart_patterns 테이블

패턴 목록:
  가격 구조: Cup & Handle, Head & Shoulders, Inverse H&S, Double Bottom
  이동평균: Golden Cross, Death Cross, MA20 Cross
  변동성:   Bollinger Squeeze Breakout
  모멘텀:   RSI Divergence, MACD Histogram Reversal
  거래량:   Volume Climax
  레벨:     52주 고/저가 접근
  수렴:     Ascending/Descending/Symmetrical Triangle

DB: chart_patterns (DROP+재생성)
비용: ❌ 없음
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from datetime import datetime, date
from db_pool import get_cursor


def _ensure_table():
    with get_cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS chart_patterns CASCADE")
        cur.execute("""
            CREATE TABLE chart_patterns (
                pattern_id    SERIAL PRIMARY KEY,
                stock_id      INTEGER NOT NULL REFERENCES stocks(stock_id),
                calc_date     DATE NOT NULL,
                pattern_type  VARCHAR(50) NOT NULL,
                pattern_name  VARCHAR(100) NOT NULL,
                direction     VARCHAR(10),
                strength      NUMERIC,
                description   TEXT,
                created_at    TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(stock_id, calc_date, pattern_type)
            )
        """)
    print("[PATTERN] ✅ chart_patterns 테이블 재생성")


def _detect_patterns(stock_id, close, high, low, volume):
    patterns = []
    if len(close) < 50:
        return patterns
    cur_price = float(close.iloc[-1])

    # ── 1. Double Bottom (W 패턴) ──
    try:
        recent = close.tail(60).values
        from scipy.signal import argrelextrema
        local_min_idx = argrelextrema(recent, np.less, order=5)[0]
        if len(local_min_idx) >= 2:
            last_two = local_min_idx[-2:]
            p1, p2 = recent[last_two[0]], recent[last_two[1]]
            if abs(p1 - p2) / max(p1, p2) < 0.03 and cur_price > max(p1, p2) * 1.02:
                patterns.append({"type": "DOUBLE_BOTTOM", "name": "Double Bottom (W)",
                    "direction": "BULLISH", "strength": round(min(80, (cur_price / max(p1, p2) - 1) * 500), 1),
                    "desc": f"저점 ${p1:.1f}/${p2:.1f}, 현재 ${cur_price:.1f}"})
    except ImportError: pass
    except Exception: pass

    # ── 2. Bollinger Squeeze Breakout ──
    try:
        sma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        bb_width = (2 * std20) / sma20
        if len(bb_width.dropna()) >= 20:
            cw = float(bb_width.iloc[-1]); aw = float(bb_width.tail(120).mean()); pw = float(bb_width.iloc[-2])
            if pw < aw * 0.6 and cw > pw * 1.1:
                upper = float(sma20.iloc[-1] + 2 * std20.iloc[-1])
                lower = float(sma20.iloc[-1] - 2 * std20.iloc[-1])
                if cur_price > upper:
                    patterns.append({"type": "BB_BREAKOUT_UP", "name": "BB Squeeze Breakout ↑",
                        "direction": "BULLISH", "strength": 70, "desc": f"스퀴즈 해제 상단 돌파 (BB상단=${upper:.1f})"})
                elif cur_price < lower:
                    patterns.append({"type": "BB_BREAKOUT_DOWN", "name": "BB Squeeze Breakout ↓",
                        "direction": "BEARISH", "strength": 70, "desc": f"스퀴즈 해제 하단 돌파 (BB하단=${lower:.1f})"})
    except Exception: pass

    # ── 3. RSI Divergence ──
    try:
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rsi = 100 - (100 / (1 + gain / loss.replace(0, np.nan)))
        if len(rsi.dropna()) >= 20:
            price_20d = float(close.iloc[-1]) - float(close.iloc[-20])
            rsi_20d = float(rsi.iloc[-1]) - float(rsi.iloc[-20])
            if price_20d < 0 and rsi_20d > 5:
                patterns.append({"type": "RSI_BULL_DIV", "name": "RSI 강세 다이버전스",
                    "direction": "BULLISH", "strength": round(min(90, rsi_20d * 5), 1),
                    "desc": f"가격 {price_20d/float(close.iloc[-20])*100:.1f}%↓, RSI +{rsi_20d:.1f}↑"})
            elif price_20d > 0 and rsi_20d < -5:
                patterns.append({"type": "RSI_BEAR_DIV", "name": "RSI 약세 다이버전스",
                    "direction": "BEARISH", "strength": round(min(90, abs(rsi_20d) * 5), 1),
                    "desc": f"가격 +{price_20d/float(close.iloc[-20])*100:.1f}%↑, RSI {rsi_20d:.1f}↓"})
    except Exception: pass

    # ── 4. Volume Climax ──
    try:
        vol_avg = float(volume.tail(20).mean()); vol_today = float(volume.iloc[-1])
        price_chg = float(close.iloc[-1] - close.iloc[-2])
        if vol_today > vol_avg * 3:
            d = "BULLISH" if price_chg > 0 else "BEARISH"
            patterns.append({"type": "VOLUME_CLIMAX", "name": f"거래량 클라이맥스",
                "direction": d, "strength": round(min(90, (vol_today / vol_avg) * 15), 1),
                "desc": f"거래량 {vol_today/vol_avg:.1f}배 급증, 가격 {price_chg:+.2f}"})
    except Exception: pass

    # ── 5. 52주 고/저가 접근 ──
    try:
        h52 = float(high.tail(252).max()) if len(high) >= 252 else float(high.max())
        l52 = float(low.tail(252).min()) if len(low) >= 252 else float(low.min())
        dh = (h52 - cur_price) / h52 * 100
        dl = (cur_price - l52) / l52 * 100 if l52 > 0 else 999
        if dh < 3:
            patterns.append({"type": "NEAR_52W_HIGH", "name": "52주 신고가 접근",
                "direction": "BULLISH", "strength": round(90 - dh * 10, 1),
                "desc": f"52주 고가 ${h52:.1f}까지 {dh:.1f}%"})
        if dl < 5 and cur_price < float(close.tail(20).mean()):
            patterns.append({"type": "NEAR_52W_LOW", "name": "52주 신저가 접근",
                "direction": "BEARISH", "strength": round(90 - dl * 10, 1),
                "desc": f"52주 저가 ${l52:.1f}까지 {dl:.1f}%"})
    except Exception: pass

    # ── 6. MA20 Cross ──
    try:
        ma20 = float(close.rolling(20).mean().iloc[-1]); prev_c = float(close.iloc[-2])
        if prev_c < ma20 and cur_price > ma20:
            patterns.append({"type": "MA20_CROSS_UP", "name": "MA20 상향 돌파",
                "direction": "BULLISH", "strength": 60, "desc": f"MA20(${ma20:.1f}) 상향 돌파"})
        elif prev_c > ma20 and cur_price < ma20:
            patterns.append({"type": "MA20_CROSS_DOWN", "name": "MA20 하향 이탈",
                "direction": "BEARISH", "strength": 60, "desc": f"MA20(${ma20:.1f}) 하향 이탈"})
    except Exception: pass

    # ── 7. Cup and Handle ──
    try:
        if len(close) >= 120:
            r = close.tail(120).values; mid = len(r) // 2
            cup_low = float(np.min(r[:mid+10])); left_rim = float(r[0]); right_rim = float(r[mid])
            depth = (left_rim - cup_low) / left_rim * 100 if left_rim > 0 else 0
            rim_diff = abs(left_rim - right_rim) / left_rim * 100 if left_rim > 0 else 999
            if 8 < depth < 35 and rim_diff < 5:
                handle_low = float(np.min(r[-20:])); handle_drop = (right_rim - handle_low) / right_rim * 100
                if 2 < handle_drop < 15 and cur_price > right_rim * 0.97:
                    bo = cur_price > max(left_rim, right_rim)
                    patterns.append({"type": "CUP_AND_HANDLE",
                        "name": f"Cup & Handle {'돌파!' if bo else '형성중'}",
                        "direction": "BULLISH", "strength": 85 if bo else 65,
                        "desc": f"컵 깊이 {depth:.1f}%, 핸들 {handle_drop:.1f}%"})
    except Exception: pass

    # ── 8. Head and Shoulders ──
    try:
        if len(close) >= 60:
            r = close.tail(60).values
            from scipy.signal import argrelextrema
            peaks = argrelextrema(r, np.greater, order=5)[0]
            if len(peaks) >= 3:
                pk = peaks[-3:]; p1, p2, p3 = r[pk[0]], r[pk[1]], r[pk[2]]
                if p2 > p1 and p2 > p3 and abs(p1-p3)/max(p1,p3)*100 < 5:
                    neckline = min(r[pk[0]:pk[2]+1])
                    if cur_price < neckline:
                        patterns.append({"type": "HEAD_SHOULDERS", "name": "Head & Shoulders 넥라인 이탈",
                            "direction": "BEARISH", "strength": 80,
                            "desc": f"헤드 ${p2:.1f}, 숄더 ${p1:.1f}/${p3:.1f}, 넥라인 ${neckline:.1f} 이탈"})
    except ImportError: pass
    except Exception: pass

    # ── 9. Inverse Head and Shoulders ──
    try:
        if len(close) >= 60:
            r = close.tail(60).values
            from scipy.signal import argrelextrema
            troughs = argrelextrema(r, np.less, order=5)[0]
            if len(troughs) >= 3:
                tk = troughs[-3:]; t1, t2, t3 = r[tk[0]], r[tk[1]], r[tk[2]]
                if t2 < t1 and t2 < t3 and abs(t1-t3)/max(t1,t3)*100 < 5:
                    neckline = max(r[tk[0]:tk[2]+1])
                    if cur_price > neckline:
                        patterns.append({"type": "INV_HEAD_SHOULDERS", "name": "Inverse H&S 넥라인 돌파!",
                            "direction": "BULLISH", "strength": 80,
                            "desc": f"역헤드 ${t2:.1f}, 넥라인 ${neckline:.1f} 돌파"})
    except ImportError: pass
    except Exception: pass

    # ── 10. Golden Cross / Death Cross ──
    try:
        if len(close) >= 200:
            ma50 = close.rolling(50).mean(); ma200 = close.rolling(200).mean()
            t50, t200 = float(ma50.iloc[-1]), float(ma200.iloc[-1])
            p50, p200 = float(ma50.iloc[-2]), float(ma200.iloc[-2])
            if p50 < p200 and t50 > t200:
                patterns.append({"type": "GOLDEN_CROSS", "name": "Golden Cross",
                    "direction": "BULLISH", "strength": 75, "desc": f"50MA(${t50:.1f}) > 200MA(${t200:.1f})"})
            elif p50 > p200 and t50 < t200:
                patterns.append({"type": "DEATH_CROSS", "name": "Death Cross",
                    "direction": "BEARISH", "strength": 75, "desc": f"50MA(${t50:.1f}) < 200MA(${t200:.1f})"})
    except Exception: pass

    # ── 11. MACD Histogram Reversal ──
    try:
        if len(close) >= 35:
            macd = close.ewm(span=12).mean() - close.ewm(span=26).mean()
            hist = macd - macd.ewm(span=9).mean()
            h0, h1, h2 = float(hist.iloc[-1]), float(hist.iloc[-2]), float(hist.iloc[-3])
            if h2 < 0 and h1 < 0 and h0 > 0:
                patterns.append({"type": "MACD_BULL_CROSS", "name": "MACD 양전환",
                    "direction": "BULLISH", "strength": 65, "desc": f"MACD histogram 0선 상향 ({h1:.3f}→{h0:.3f})"})
            elif h2 > 0 and h1 > 0 and h0 < 0:
                patterns.append({"type": "MACD_BEAR_CROSS", "name": "MACD 음전환",
                    "direction": "BEARISH", "strength": 65, "desc": f"MACD histogram 0선 하향 ({h1:.3f}→{h0:.3f})"})
    except Exception: pass

    # ── 12. Ascending / Descending / Symmetrical Triangle ──
    try:
        if len(close) >= 30:
            hv = high.tail(30).values.astype(float); lv = low.tail(30).values.astype(float)
            x = np.arange(len(hv))
            hs = np.polyfit(x, hv, 1)[0]; ls = np.polyfit(x, lv, 1)[0]
            pl = float(np.mean(hv))
            hsp = hs / pl * 100 * 30; lsp = ls / pl * 100 * 30
            if abs(hsp) < 2 and lsp > 1:
                patterns.append({"type": "ASC_TRIANGLE", "name": "상승 삼각수렴",
                    "direction": "BULLISH", "strength": 60, "desc": "저항 평탄 + 지지 상승"})
            elif hsp < -1 and abs(lsp) < 2:
                patterns.append({"type": "DESC_TRIANGLE", "name": "하강 삼각수렴",
                    "direction": "BEARISH", "strength": 60, "desc": "저항 하락 + 지지 평탄"})
            elif hsp < -1 and lsp > 1:
                patterns.append({"type": "SYM_TRIANGLE", "name": "대칭 삼각수렴",
                    "direction": "NEUTRAL", "strength": 50, "desc": "고점↓ 저점↑ 수렴중"})
    except Exception: pass

    return patterns


def run_chart_patterns(calc_date=None):
    if calc_date is None:
        calc_date = date.today()
    _ensure_table()
    from collections import defaultdict
    with get_cursor() as cur:
        cur.execute("SELECT stock_id, ticker FROM stocks WHERE is_active = TRUE")
        stocks = [dict(r) for r in cur.fetchall()]
    stock_ids = [s["stock_id"] for s in stocks]
    print(f"[PATTERN] 가격 데이터 로딩 ({len(stocks)}종목)...")
    price_groups = defaultdict(list)
    with get_cursor() as cur:
        cur.execute("""SELECT stock_id, trade_date, open_price, high_price, low_price, close_price, volume
            FROM stock_prices_daily WHERE stock_id = ANY(%s) AND trade_date >= %s - INTERVAL '300 days'
            ORDER BY stock_id, trade_date""", (stock_ids, calc_date))
        for r in cur.fetchall():
            price_groups[r["stock_id"]].append(dict(r))
    ok, total_patterns = 0, 0
    for s in stocks:
        sid, ticker = s["stock_id"], s["ticker"]
        rows = price_groups.get(sid, [])
        if len(rows) < 50: continue
        df = pd.DataFrame(rows)
        c = df["close_price"].astype(float); h = df["high_price"].astype(float)
        l = df["low_price"].astype(float); v = df["volume"].astype(float)
        pats = _detect_patterns(sid, c, h, l, v)
        for p in pats:
            # numpy → Python native 변환 (오답노트 #8, #12)
            p["strength"] = float(p["strength"]) if p.get("strength") is not None else None
            with get_cursor() as cur:
                cur.execute("""INSERT INTO chart_patterns (stock_id, calc_date, pattern_type, pattern_name,
                    direction, strength, description) VALUES (%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (stock_id, calc_date, pattern_type) DO UPDATE SET
                    pattern_name=EXCLUDED.pattern_name, direction=EXCLUDED.direction,
                    strength=EXCLUDED.strength, description=EXCLUDED.description
                """, (sid, calc_date, p["type"], p["name"], p["direction"], p["strength"], p["desc"]))
            total_patterns += 1
        ok += 1
        if ok % 100 == 0: print(f"[PATTERN]   {ok}/{len(stocks)} 완료...")
    print(f"[PATTERN] ✅ {ok}종목 분석, {total_patterns}개 패턴 감지")


if __name__ == "__main__":
    from dotenv import load_dotenv; load_dotenv()
    from db_pool import init_pool; init_pool()
    run_chart_patterns()