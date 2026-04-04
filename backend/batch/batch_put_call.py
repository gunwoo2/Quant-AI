"""
batch/batch_put_call.py — 종목별 Put/Call Ratio 수집 (yfinance options)
======================================================================
Layer 3 Section B의 풋콜비율(7점) 실데이터 공급.

기존 문제: put_call_score = 3.5 하드코딩 (모든 종목 동일)
해결: yfinance 옵션 체인에서 종목별 P/C ratio 계산

전략:
  1. 시총 상위 150종목: 개별 옵션 P/C ratio 계산
  2. 나머지 종목: 시장 전체 P/C (SPY 기반) 적용
  3. 결과를 put_call_daily 테이블에 저장
  4. batch_layer3_flow_macro.py가 이 테이블에서 읽어서 점수화

스코어링 (역발상 Contrarian 지표, 7점 만점):
  P/C < 0.5   → 극단적 낙관(콜 과다) → 하락 경고  → 1.0점
  P/C 0.5-0.7 → 낙관 편향             → 경계       → 2.5점
  P/C 0.7-1.0 → 중립                  → 중립       → 3.5점
  P/C 1.0-1.3 → 공포 편향             → 역발상 매수 → 5.0점
  P/C > 1.3   → 극단적 공포(풋 과다)  → 강한 매수  → 6.5점

스케줄: 매일 배치 (Step 4 Layer 3 이전에 실행)
소요시간: ~5-8분 (150종목 × 2-3초)
API 비용: ❌ 없음 (yfinance 무료)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import patch_numpy_adapter
except ImportError:
    pass

import yfinance as yf
import numpy as np
from datetime import datetime, date, timedelta
from db_pool import get_cursor


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 설정
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TOP_N_INDIVIDUAL = 150       # 개별 P/C 계산할 종목 수
MAX_EXPIRY_DAYS  = 45        # 만기 45일 이내 옵션만
MIN_OPEN_INTEREST = 100      # 최소 미결제약정 (노이즈 필터)
MARKET_TICKER    = "SPY"     # 시장 전체 P/C 대용


def _ensure_table():
    """put_call_daily 테이블 생성"""
    with get_cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS put_call_daily (
                id              SERIAL PRIMARY KEY,
                stock_id        INT NOT NULL,
                calc_date       DATE NOT NULL,
                put_oi          BIGINT,
                call_oi         BIGINT,
                put_volume      BIGINT,
                call_volume     BIGINT,
                pc_ratio_oi     NUMERIC(6,4),
                pc_ratio_volume NUMERIC(6,4),
                pc_score        NUMERIC(4,2),
                source          VARCHAR(20) DEFAULT 'yfinance',
                updated_at      TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(stock_id, calc_date)
            )
        """)
    print("[P/C] ✅ put_call_daily 테이블 확인")


def score_put_call(pc_ratio: float) -> float:
    """
    P/C ratio → 7점 만점 스코어 (역발상 Contrarian)

    핵심: P/C가 높을수록(대중이 공포) → 매수 기회 → 높은 점수
          P/C가 낮을수록(대중이 탐욕) → 하락 경고 → 낮은 점수

    참고: CBOE 평균 P/C ≈ 0.7~0.8
    """
    if pc_ratio is None:
        return 3.5  # 중립

    r = float(pc_ratio)

    if r < 0.4:
        return 0.5   # 극단적 콜 편향 → 위험
    elif r < 0.5:
        return 1.0
    elif r < 0.6:
        return 2.0
    elif r < 0.7:
        return 2.5
    elif r < 0.8:
        return 3.0   # 정상 범위 하단
    elif r < 0.9:
        return 3.5   # 중립
    elif r < 1.0:
        return 4.0   # 약간 공포
    elif r < 1.1:
        return 4.5
    elif r < 1.3:
        return 5.5   # 공포 → 역발상 매수
    elif r < 1.5:
        return 6.0   # 강한 공포
    else:
        return 6.5   # 극단적 공포 → 강한 역발상 매수


def _fetch_pc_ratio(ticker: str, max_days: int = MAX_EXPIRY_DAYS) -> dict:
    """
    yfinance에서 종목의 P/C ratio 계산.

    Returns:
        {put_oi, call_oi, put_vol, call_vol, pc_ratio_oi, pc_ratio_volume}
        또는 None (옵션 데이터 없음)
    """
    try:
        tk = yf.Ticker(ticker)
        expirations = tk.options  # ['2026-04-03', '2026-04-10', ...]

        if not expirations:
            print(f"    [P/C] {ticker}: 옵션 만기 없음 (yfinance 문제?)")
            return None

        today = date.today()
        cutoff = today + timedelta(days=max_days)

        total_put_oi = 0
        total_call_oi = 0
        total_put_vol = 0
        total_call_vol = 0

        for exp_str in expirations:
            try:
                exp_date = datetime.strptime(exp_str, '%Y-%m-%d').date()
            except ValueError:
                continue

            if exp_date > cutoff:
                break  # 만기가 너무 먼 옵션은 스킵

            if exp_date < today:
                continue  # 이미 만기된 옵션 스킵

            try:
                chain = tk.option_chain(exp_str)

                # Calls
                calls = chain.calls
                if calls is not None and len(calls) > 0:
                    # 최소 미결제약정 필터
                    valid_calls = calls[calls['openInterest'] >= MIN_OPEN_INTEREST]
                    total_call_oi += int(valid_calls['openInterest'].sum())
                    total_call_vol += int(calls['volume'].fillna(0).sum())

                # Puts
                puts = chain.puts
                if puts is not None and len(puts) > 0:
                    valid_puts = puts[puts['openInterest'] >= MIN_OPEN_INTEREST]
                    total_put_oi += int(valid_puts['openInterest'].sum())
                    total_put_vol += int(puts['volume'].fillna(0).sum())

            except Exception as chain_err:
                print(f"    [P/C] {ticker}/{exp_str}: {chain_err}")
                continue

        if total_call_oi == 0:
            return None

        pc_ratio_oi = round(total_put_oi / total_call_oi, 4) if total_call_oi > 0 else None
        pc_ratio_vol = round(total_put_vol / total_call_vol, 4) if total_call_vol > 0 else None

        return {
            "put_oi": total_put_oi,
            "call_oi": total_call_oi,
            "put_vol": total_put_vol,
            "call_vol": total_call_vol,
            "pc_ratio_oi": pc_ratio_oi,
            "pc_ratio_volume": pc_ratio_vol,
        }

    except Exception as e:
        print(f"  [P/C] ⚠️ {ticker} 옵션 조회 실패: {e}")
        return None


def run_put_call(calc_date: date = None):
    """Put/Call Ratio 배치 실행"""
    if calc_date is None:
        calc_date = date.today()

    _ensure_table()

    # ── 종목 목록 조회 (시총 상위 순) ──
    with get_cursor() as cur:
        cur.execute("""
            SELECT DISTINCT s.stock_id, s.ticker, sp.current_price
            FROM stocks s
            LEFT JOIN stock_prices_realtime sp ON s.stock_id = sp.stock_id
            WHERE s.is_active = TRUE
            ORDER BY sp.current_price DESC NULLS LAST
        """)
        all_stocks = [dict(r) for r in cur.fetchall()]

    total = len(all_stocks)
    top_stocks = all_stocks[:TOP_N_INDIVIDUAL]
    rest_stocks = all_stocks[TOP_N_INDIVIDUAL:]

    print(f"[P/C] 📊 총 {total}종목 (개별: {len(top_stocks)}, 시장P/C 적용: {len(rest_stocks)})")

    # ── 1단계: 시장 전체 P/C (SPY) ──
    print(f"[P/C] 📡 시장 P/C 수집 중 (SPY)...")
    market_pc = _fetch_pc_ratio(MARKET_TICKER, max_days=30)
    market_ratio = (market_pc.get("pc_ratio_oi") or 0.85) if market_pc else 0.85  # 기본 중립
    market_score = score_put_call(market_ratio)
    print(f"[P/C] 📊 시장 P/C (SPY): ratio={market_ratio}, score={market_score}/7")

    # ── 2단계: 상위 종목 개별 P/C ──
    success = 0
    fail = 0
    results = []

    # 옵션 데이터가 없는 것으로 알려진 종목 스킵 (시간 절약)
    SKIP_TICKERS = {"BRK-B", "BF-B", "NVR"}  # 초고가주 또는 특수 티커
    
    for idx, stock in enumerate(top_stocks):
        ticker = stock["ticker"]
        stock_id = stock["stock_id"]
        
        if ticker in SKIP_TICKERS:
            # 시장 P/C 값으로 대체
            results.append({
                "stock_id": stock_id, "ticker": ticker,
                "put_oi": 0, "call_oi": 0, "put_vol": 0, "call_vol": 0,
                "pc_ratio_oi": market_ratio, "pc_ratio_volume": market_ratio,
                "pc_score": market_score, "source": "market_fallback",
            })
            continue

        if idx % 20 == 0 and idx > 0:
            print(f"  [P/C] 진행: {idx}/{len(top_stocks)} (성공: {success}, 실패: {fail})")

        pc_data = _fetch_pc_ratio(ticker)

        if pc_data and pc_data["pc_ratio_oi"] is not None:
            ratio = pc_data["pc_ratio_oi"]
            score = score_put_call(ratio)
            results.append({
                "stock_id": stock_id,
                "ticker": ticker,
                "put_oi": pc_data["put_oi"],
                "call_oi": pc_data["call_oi"],
                "put_vol": pc_data["put_vol"],
                "call_vol": pc_data["call_vol"],
                "pc_ratio_oi": ratio,
                "pc_ratio_volume": pc_data["pc_ratio_volume"],
                "pc_score": score,
                "source": "individual",
            })
            success += 1
        else:
            # 개별 옵션 없음 → 시장 P/C 적용
            results.append({
                "stock_id": stock_id,
                "ticker": ticker,
                "put_oi": None,
                "call_oi": None,
                "put_vol": None,
                "call_vol": None,
                "pc_ratio_oi": market_ratio,
                "pc_ratio_volume": None,
                "pc_score": market_score,
                "source": "market_fallback",
            })
            fail += 1

    # ── 3단계: 나머지 종목 → 시장 P/C 일괄 적용 ──
    for stock in rest_stocks:
        results.append({
            "stock_id": stock["stock_id"],
            "ticker": stock["ticker"],
            "put_oi": None,
            "call_oi": None,
            "put_vol": None,
            "call_vol": None,
            "pc_ratio_oi": market_ratio,
            "pc_ratio_volume": None,
            "pc_score": market_score,
            "source": "market_default",
        })

    # ── 4단계: DB 저장 ──
    saved = 0
    with get_cursor() as cur:
        for r in results:
            try:
                cur.execute("""
                    INSERT INTO put_call_daily
                        (stock_id, calc_date, put_oi, call_oi, put_volume, call_volume,
                         pc_ratio_oi, pc_ratio_volume, pc_score, source)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (stock_id, calc_date) DO UPDATE SET
                        put_oi          = EXCLUDED.put_oi,
                        call_oi         = EXCLUDED.call_oi,
                        put_volume      = EXCLUDED.put_volume,
                        call_volume     = EXCLUDED.call_volume,
                        pc_ratio_oi     = EXCLUDED.pc_ratio_oi,
                        pc_ratio_volume = EXCLUDED.pc_ratio_volume,
                        pc_score        = EXCLUDED.pc_score,
                        source          = EXCLUDED.source,
                        updated_at      = NOW()
                """, (
                    r["stock_id"], calc_date,
                    r["put_oi"], r["call_oi"], r["put_vol"], r["call_vol"],
                    r["pc_ratio_oi"], r["pc_ratio_volume"], r["pc_score"], r["source"],
                ))
                saved += 1
            except Exception as e:
                print(f"  [P/C] ❌ {r['ticker']} 저장 실패: {e}")

    # ── 통계 ──
    individual_ratios = [r["pc_ratio_oi"] for r in results if r["source"] == "individual" and r["pc_ratio_oi"]]
    avg_ratio = np.mean(individual_ratios) if individual_ratios else market_ratio
    median_ratio = np.median(individual_ratios) if individual_ratios else market_ratio

    print(f"\n[P/C] ✅ 완료: {saved}/{len(results)} 저장")
    print(f"  개별 수집: {success}종목 | 시장 P/C fallback: {fail + len(rest_stocks)}종목")
    print(f"  시장 P/C (SPY): {market_ratio:.4f}")
    print(f"  개별 평균 P/C: {avg_ratio:.4f} | 중앙값: {median_ratio:.4f}")

    return {
        "total": len(results),
        "individual": success,
        "market_fallback": fail + len(rest_stocks),
        "market_pc_ratio": market_ratio,
        "avg_pc_ratio": round(avg_ratio, 4),
    }


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    from db_pool import init_pool
    init_pool()
    run_put_call()