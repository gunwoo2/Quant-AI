"""
batch/batch_alpha_decay.py — Alpha Decay Tracker v1.0
======================================================
AI 모듈 #3: 시그널 유효기간(Half-Life) 측정 + 자동 비활성화

핵심 기능:
  1. 등급별 Forward Return 매트릭스: S/A+/A/B+/B × 1D/3D/5D/10D/20D
  2. Signal Half-Life 계산: IC가 50%로 감소하는 시점
  3. 등급별 Hit Rate: 시그널 발생 후 양수 수익 비율
  4. Decay IC: 보유기간별 Spearman IC 시계열
  5. 자동 비활성화: IC < 0.02 지속 시 시그널 만료 기간 축소
  6. 주간 Alpha Decay 리포트 (Discord)

학술 참조:
  - Korajczyk & Sadka (2004) "Are Momentum Profits Robust to Trading Costs?"
    → 시그널 유효기간이 짧으면 거래비용에 먹힘
  - Lo (2004) "The Adaptive Markets Hypothesis"
    → 알파는 시장 참여자 증가로 자연 소멸
  - Israel, Moskowitz, Ross (2017) "Can Machines Learn Finance?"
    → 팩터 IC 반감기 = 팩터 "살아있는" 기간

실행 주기:
  - 일일: Forward Return 업데이트 + Decay IC 계산
  - 주간 (금요일): Alpha Decay 리포트 → Discord

DB 테이블:
  - alpha_decay_daily: 일별 등급별 성과 매트릭스
  - signal_halflife: 등급별 Half-Life 기록
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import patch_numpy_adapter
except ImportError:
    pass

import numpy as np
from scipy.stats import spearmanr
from datetime import datetime, date, timedelta
from db_pool import get_cursor


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 상수
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

HORIZONS       = [1, 3, 5, 10, 20]     # 보유기간 (영업일)
GRADES         = ["S", "A+", "A", "B+", "B", "ALL"]
LOOKBACK_DAYS  = 90                     # 분석 대상: 최근 90일 시그널
MIN_SAMPLES    = 5                      # 등급별 최소 시그널 수
IC_FLOOR       = 0.02                   # 이 이하면 "약한 시그널"
IC_DEAD        = 0.00                   # 이 이하면 "사실상 무효"
DEFAULT_EXPIRY = {                      # 기본 시그널 유효기간 (일)
    "S": 10, "A+": 7, "A": 5, "B+": 3, "B": 2,
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 테이블 생성
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _ensure_tables():
    with get_cursor() as cur:
        # 1. 일별 등급별 성과 매트릭스
        cur.execute("""
            CREATE TABLE IF NOT EXISTS alpha_decay_daily (
                id              SERIAL PRIMARY KEY,
                calc_date       DATE NOT NULL,
                grade           VARCHAR(5) NOT NULL,`
                horizon_days    INT NOT NULL,
                avg_return      NUMERIC(8,4),
                median_return   NUMERIC(8,4),
                hit_rate        NUMERIC(6,4),
                decay_ic        NUMERIC(8,6),
                ic_pvalue       NUMERIC(8,6),
                sample_size     INT,
                win_avg         NUMERIC(8,4),
                loss_avg        NUMERIC(8,4),`
                profit_factor   NUMERIC(8,4),
                updated_at      TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(calc_date, grade, horizon_days)
            )
        """)``

        # 2. 등급별 Half-Life 기록``
        cur.execute("""
            CREATE TABLE IF NOT EXISTS signal_halflife (
                id              SERIAL PRIMARY KEY,
                calc_date       DATE NOT NULL,
                grade           VARCHAR(5) NOT NULL,
                half_life_days  NUMERIC(6,2),
                peak_ic         NUMERIC(8,6),
                peak_horizon    INT,`
                recommended_expiry INT,
                status          VARCHAR(20) DEFAULT 'ACTIVE',
                notes           TEXT,
                updated_at      TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(calc_date, grade)
            )
        """)

        # 인덱스
        cur.execute("CREATE INDEX IF NOT EXISTS idx_alpha_decay_date ON alpha_decay_daily(calc_date DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_alpha_decay_grade ON alpha_decay_daily(grade, horizon_days)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_signal_hl_date ON signal_halflife(calc_date DESC)")

    print("[DECAY] ✅ 테이블 확인 완료")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Step 1: 등급별 × 보유기간별 Forward Return + IC 계산
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _calc_decay_matrix(calc_date: date) -> list:
    """
    등급별 × 보유기간별 성과 매트릭스 계산.

    For each (grade, horizon):
      1. 과거 LOOKBACK_DAYS 내 해당 등급 BUY 시그널 수집
      2. 시그널 발생일 종가 → horizon일 후 종가 = Forward Return
      3. IC = Spearman(점수, Forward Return)
      4. Hit Rate = 양수 수익 비율
      5. Profit Factor = |평균 이익| / |평균 손실|
    """
    results = []

    for grade in GRADES:
        for h in HORIZONS:
            # horizon일 이후 가격이 존재할 만큼 오래된 시그널만
            max_signal_date = calc_date - timedelta(days=int(h * 1.6))

            grade_filter = ""
            grade_params = []
            if grade != "ALL":
                grade_filter = "AND sfs.grade = %s"
                grade_params = [grade]

            try:
                with get_cursor() as cur:
                    query = f"""
                        WITH buy_signals AS (
                            SELECT DISTINCT ON (ts.stock_id, ts.signal_date)
                                ts.stock_id,
                                ts.signal_date,
                                COALESCE(sfs.weighted_score, ts.final_score) AS score
                            FROM trading_signals ts
                            LEFT JOIN stock_final_scores sfs
                                ON ts.stock_id = sfs.stock_id
                                AND sfs.calc_date = ts.signal_date
                            WHERE ts.signal_type = 'BUY'
                              AND ts.signal_date >= %s - INTERVAL '{LOOKBACK_DAYS} days'
                              AND ts.signal_date <= %s
                              {grade_filter}
                            ORDER BY ts.stock_id, ts.signal_date
                        ),
                        with_returns AS (
                            SELECT
                                bs.stock_id,
                                bs.signal_date,
                                bs.score,
                                p0.close_price AS entry_price,
                                p1.close_price AS exit_price,
                                CASE WHEN p0.close_price > 0
                                    THEN (p1.close_price - p0.close_price) / p0.close_price * 100
                                    ELSE NULL
                                END AS fwd_return
                            FROM buy_signals bs
                            JOIN LATERAL (
                                SELECT close_price FROM stock_prices_daily
                                WHERE stock_id = bs.stock_id
                                  AND trade_date >= bs.signal_date
                                ORDER BY trade_date ASC LIMIT 1
                            ) p0 ON TRUE
                            JOIN LATERAL (
                                SELECT close_price FROM stock_prices_daily
                                WHERE stock_id = bs.stock_id
                                  AND trade_date >= bs.signal_date + INTERVAL '{h} days'
                                ORDER BY trade_date ASC LIMIT 1
                            ) p1 ON TRUE
                            WHERE p0.close_price > 0
                        )
                        SELECT stock_id, signal_date, score, entry_price, exit_price, fwd_return
                        FROM with_returns
                        WHERE fwd_return IS NOT NULL
                    """
                    params = [calc_date, max_signal_date] + grade_params
                    cur.execute(query, params)
                    rows = cur.fetchall()

                n = len(rows)
                if n < MIN_SAMPLES:
                    results.append({
                        "grade": grade, "horizon": h,
                        "avg_return": None, "median_return": None,
                        "hit_rate": None, "decay_ic": None, "ic_pvalue": None,
                        "sample_size": n, "win_avg": None, "loss_avg": None,
                        "profit_factor": None,
                    })
                    continue

                returns = [float(r["fwd_return"]) for r in rows]
                scores = [float(r["score"]) for r in rows]

                avg_ret = round(float(np.mean(returns)), 4)
                med_ret = round(float(np.median(returns)), 4)

                wins = [r for r in returns if r > 0]
                losses = [r for r in returns if r <= 0]
                hit_rate = round(len(wins) / n, 4) if n > 0 else None

                win_avg = round(float(np.mean(wins)), 4) if wins else 0.0
                loss_avg = round(float(np.mean(losses)), 4) if losses else 0.0
                profit_factor = round(abs(win_avg) / max(abs(loss_avg), 0.01), 4)

                ic_val, p_val = spearmanr(scores, returns)
                ic_val = round(float(ic_val), 6) if not np.isnan(ic_val) else None
                p_val = round(float(p_val), 6) if not np.isnan(p_val) else None

                results.append({
                    "grade": grade, "horizon": h,
                    "avg_return": avg_ret, "median_return": med_ret,
                    "hit_rate": hit_rate, "decay_ic": ic_val, "ic_pvalue": p_val,
                    "sample_size": n, "win_avg": win_avg, "loss_avg": loss_avg,
                    "profit_factor": profit_factor,
                })

                # 로그
                status = ""
                if ic_val is not None:
                    if ic_val < IC_DEAD:
                        status = "🔴 DEAD"
                    elif ic_val < IC_FLOOR:
                        status = "⚠️  WEAK"
                    else:
                        status = "✅"

                print(f"  [{grade:3s}|{h:2d}D] avg={avg_ret:+6.2f}% hit={hit_rate:.0%} "
                      f"IC={ic_val or 0:+.4f} n={n:3d} PF={profit_factor:.2f} {status}")

            except Exception as e:
                print(f"  [ERR] {grade}/{h}D: {e}")
                results.append({
                    "grade": grade, "horizon": h,
                    "avg_return": None, "hit_rate": None, "decay_ic": None,
                    "sample_size": 0, "ic_pvalue": None,
                    "win_avg": None, "loss_avg": None,
                    "median_return": None, "profit_factor": None,
                })

    return results


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Step 2: Half-Life 계산
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _calc_half_life(decay_matrix: list) -> list:
    """
    등급별 IC 반감기 계산.

    방법: 보유기간별 IC 곡선에서 선형 보간으로 IC가 peak의 50%가 되는 시점 추정.
    """
    half_lives = []

    for grade in GRADES:
        grade_data = [r for r in decay_matrix
                      if r["grade"] == grade and r["decay_ic"] is not None]

        if len(grade_data) < 2:
            half_lives.append({
                "grade": grade, "half_life": None, "peak_ic": None,
                "peak_horizon": None, "recommended_expiry": DEFAULT_EXPIRY.get(grade, 5),
                "status": "INSUFFICIENT_DATA",
            })
            continue

        # IC 곡선
        ics = [(r["horizon"], r["decay_ic"]) for r in grade_data]
        ics.sort(key=lambda x: x[0])

        # Peak IC 찾기
        peak_h, peak_ic = max(ics, key=lambda x: abs(x[1]))
        abs_peak = abs(peak_ic)
        half_target = abs_peak / 2.0

        # Half-Life: IC가 peak의 50%로 줄어드는 지점 (선형 보간)
        half_life = None

        if abs_peak > 0.01:  # 의미있는 IC일 때만
            # peak 이후 시점에서 IC가 half_target 이하로 떨어지는 지점
            found_peak = False
            for i in range(len(ics) - 1):
                h_now, ic_now = ics[i]
                h_next, ic_next = ics[i + 1]

                if h_now >= peak_h:
                    found_peak = True

                if found_peak and abs(ic_now) >= half_target and abs(ic_next) < half_target:
                    # 선형 보간
                    if abs(ic_now) - abs(ic_next) > 0:
                        ratio = (abs(ic_now) - half_target) / (abs(ic_now) - abs(ic_next))
                        half_life = round(h_now + ratio * (h_next - h_now), 1)
                    break

            # 끝까지 half_target 이하로 안 떨어지면 → Half-Life > 20일
            if half_life is None and found_peak:
                last_ic = abs(ics[-1][1])
                if last_ic >= half_target:
                    half_life = 25.0  # > 20일 (강한 시그널)

        # Recommended Expiry 계산
        if half_life is not None:
            recommended = max(1, int(half_life * 1.5))  # half-life의 1.5배
            recommended = min(recommended, 30)  # 최대 30일
        else:
            recommended = DEFAULT_EXPIRY.get(grade, 5)

        # 상태 판정
        status = "ACTIVE"
        if peak_ic < IC_DEAD:
            status = "DEAD"
        elif peak_ic < IC_FLOOR:
            status = "WEAK"
        elif half_life is not None and half_life < 2.0:
            status = "FAST_DECAY"

        half_lives.append({
            "grade": grade,
            "half_life": half_life,
            "peak_ic": round(peak_ic, 6) if peak_ic else None,
            "peak_horizon": peak_h,
            "recommended_expiry": recommended,
            "status": status,
        })

        emoji = {"ACTIVE": "✅", "WEAK": "⚠️", "DEAD": "🔴", "FAST_DECAY": "⚡",
                 "INSUFFICIENT_DATA": "❓"}.get(status, "")
        print(f"  {grade:3s} Half-Life={half_life or '?':>5} days | "
              f"Peak IC={peak_ic or 0:+.4f} @{peak_h}D | "
              f"Expiry={recommended}D | {status} {emoji}")

    return half_lives


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Step 3: DB 저장
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _save_decay_matrix(calc_date: date, matrix: list):
    """Decay 매트릭스 DB 저장"""
    saved = 0
    for r in matrix:
        try:
            with get_cursor() as cur:
                cur.execute("""
                    INSERT INTO alpha_decay_daily
                        (calc_date, grade, horizon_days, avg_return, median_return,
                         hit_rate, decay_ic, ic_pvalue, sample_size,
                         win_avg, loss_avg, profit_factor)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (calc_date, grade, horizon_days) DO UPDATE SET
                        avg_return = EXCLUDED.avg_return,
                        median_return = EXCLUDED.median_return,
                        hit_rate = EXCLUDED.hit_rate,
                        decay_ic = EXCLUDED.decay_ic,
                        ic_pvalue = EXCLUDED.ic_pvalue,
                        sample_size = EXCLUDED.sample_size,
                        win_avg = EXCLUDED.win_avg,
                        loss_avg = EXCLUDED.loss_avg,
                        profit_factor = EXCLUDED.profit_factor,
                        updated_at = NOW()
                """, (
                    calc_date, r["grade"], r["horizon"],
                    r["avg_return"], r["median_return"],
                    r["hit_rate"], r["decay_ic"], r["ic_pvalue"],
                    r["sample_size"], r["win_avg"], r["loss_avg"],
                    r["profit_factor"],
                ))
                saved += 1
        except Exception as e:
            print(f"  [SAVE-ERR] {r['grade']}/{r['horizon']}D: {e}")

    print(f"[DECAY] 매트릭스 저장: {saved}/{len(matrix)}건")


def _save_half_lives(calc_date: date, half_lives: list):
    """Half-Life DB 저장"""
    for hl in half_lives:
        try:
            notes = (f"peak_ic={hl.get('peak_ic')}, "
                     f"peak_at={hl.get('peak_horizon')}D, "
                     f"status={hl.get('status')}")
            with get_cursor() as cur:
                cur.execute("""
                    INSERT INTO signal_halflife
                        (calc_date, grade, half_life_days, peak_ic, peak_horizon,
                         recommended_expiry, status, notes)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (calc_date, grade) DO UPDATE SET
                        half_life_days = EXCLUDED.half_life_days,
                        peak_ic = EXCLUDED.peak_ic,
                        peak_horizon = EXCLUDED.peak_horizon,
                        recommended_expiry = EXCLUDED.recommended_expiry,
                        status = EXCLUDED.status,
                        notes = EXCLUDED.notes,
                        updated_at = NOW()
                """, (
                    calc_date, hl["grade"], hl.get("half_life"),
                    hl.get("peak_ic"), hl.get("peak_horizon"),
                    hl.get("recommended_expiry"), hl.get("status"), notes,
                ))
        except Exception as e:
            print(f"  [HL-ERR] {hl['grade']}: {e}")

    print(f"[DECAY] Half-Life 저장: {len(half_lives)}건")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Step 4: Discord 주간 리포트
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _build_weekly_report(calc_date: date, matrix: list, half_lives: list) -> list:
    """
    주간 Alpha Decay 리포트 Discord Embed 생성.
    금요일에만 호출.
    """
    # 등급별 요약 테이블
    header = "```\n등급  | 1D     3D     5D    10D    20D  | HL   Expiry  Status\n"
    header += "─────┼────────────────────────────────┼────────────────────\n"
    rows_text = ""

    for grade in ["S", "A+", "A", "B+", "B"]:
        grade_data = {r["horizon"]: r for r in matrix if r["grade"] == grade}
        hl_data = next((h for h in half_lives if h["grade"] == grade), {})

        cells = []
        for h in HORIZONS:
            d = grade_data.get(h, {})
            avg = d.get("avg_return")
            if avg is not None:
                cells.append(f"{avg:+5.1f}%")
            else:
                cells.append("  N/A ")

        hl_val = hl_data.get("half_life")
        hl_str = f"{hl_val:4.1f}D" if hl_val else " N/A "
        exp_str = f"{hl_data.get('recommended_expiry', '?'):3}D"
        status = hl_data.get("status", "?")

        rows_text += f" {grade:3s}  | {'  '.join(cells)} | {hl_str}  {exp_str}  {status}\n"

    table = header + rows_text + "```"

    # 경고 메시지
    warnings = []
    for hl in half_lives:
        if hl.get("status") == "DEAD":
            warnings.append(f"🔴 {hl['grade']} 등급: IC 무효 — 시그널 사실상 무의미")
        elif hl.get("status") == "WEAK":
            warnings.append(f"⚠️ {hl['grade']} 등급: IC 약함 — 시그널 신뢰도 낮음")
        elif hl.get("status") == "FAST_DECAY":
            warnings.append(f"⚡ {hl['grade']} 등급: 빠른 감쇠 — {hl.get('half_life', '?')}일 내 진입 필요")

    warning_text = "\n".join(warnings) if warnings else "모든 등급 정상 작동 중 ✅"

    # ALL 등급 히트율
    all_data = {r["horizon"]: r for r in matrix if r["grade"] == "ALL"}
    hit_rates = []
    for h in HORIZONS:
        d = all_data.get(h, {})
        hr = d.get("hit_rate")
        if hr is not None:
            hit_rates.append(f"{h}D: {hr:.0%}")
    hit_text = " | ".join(hit_rates) if hit_rates else "데이터 부족"

    embeds = [{
        "title": f"📉 Alpha Decay 주간 리포트 ({calc_date})",
        "color": 0xD85604,
        "fields": [
            {"name": "등급별 Forward Return + Half-Life", "value": table, "inline": False},
            {"name": "Hit Rate (전체)", "value": f"```{hit_text}```", "inline": False},
            {"name": "경고", "value": warning_text, "inline": False},
        ],
        "footer": {"text": "Alpha Decay Tracker v1.0 | 매주 금요일 자동 발행"},
    }]

    return embeds


def _send_weekly_report(calc_date: date, matrix: list, half_lives: list):
    """주간 리포트 Discord 전송"""
    try:
        from notifier import send_discord_embed
        embeds = _build_weekly_report(calc_date, matrix, half_lives)
        send_discord_embed(embeds, signal_type="BACKTEST")
        print("[DECAY] ✅ 주간 리포트 Discord 전송 완료")
    except ImportError:
        print("[DECAY] ⚠️ notifier 없음 — 리포트 출력만")
        embeds = _build_weekly_report(calc_date, matrix, half_lives)
        for e in embeds:
            print(f"  Title: {e['title']}")
            for f in e.get("fields", []):
                print(f"  {f['name']}:")
                print(f"  {f['value'][:300]}")
    except Exception as e:
        print(f"[DECAY] ❌ 리포트 전송 실패: {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 공개 API: 시그널 유효기간 조회
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_signal_expiry(grade: str) -> int:
    """
    등급별 시그널 유효기간(일) 조회.
    batch_trading_signals.py 에서 import하여 사용.

    Returns:
        int: 시그널 유효기간 (영업일)
    """
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT recommended_expiry, status
                FROM signal_halflife
                WHERE grade = %s
                ORDER BY calc_date DESC LIMIT 1
            """, (grade,))
            row = cur.fetchone()
            if row:
                expiry = int(row["recommended_expiry"])
                # DEAD 상태면 유효기간을 1일로 축소
                if row["status"] == "DEAD":
                    return 1
                return expiry
    except Exception:
        pass
    return DEFAULT_EXPIRY.get(grade, 5)


def get_decay_summary() -> dict:
    """최근 Alpha Decay 요약 (API 응답용)"""
    try:
        with get_cursor() as cur:
            # 최근 Half-Life
            cur.execute("""
                SELECT grade, half_life_days, peak_ic, recommended_expiry, status
                FROM signal_halflife
                WHERE calc_date = (SELECT MAX(calc_date) FROM signal_halflife)
                ORDER BY grade
            """)
            hl_rows = cur.fetchall()

            # 최근 ALL 등급 히트율
            cur.execute("""
                SELECT horizon_days, avg_return, hit_rate, decay_ic, sample_size
                FROM alpha_decay_daily
                WHERE calc_date = (SELECT MAX(calc_date) FROM alpha_decay_daily)
                  AND grade = 'ALL'
                ORDER BY horizon_days
            """)
            all_rows = cur.fetchall()

        return {
            "half_lives": [dict(r) for r in hl_rows] if hl_rows else [],
            "overall_performance": [dict(r) for r in all_rows] if all_rows else [],
        }
    except Exception:
        return {"half_lives": [], "overall_performance": []}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 메인 실행
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run_alpha_decay(calc_date: date = None):
    """
    Alpha Decay Tracker 메인 실행.
    Scheduler Step 6.7에서 매일 호출.
    """
    if calc_date is None:
        calc_date = datetime.now().date()

    print(f"\n{'='*60}")
    print(f"  Alpha Decay Tracker v1.0")
    print(f"  Date: {calc_date}")
    print(f"{'='*60}")

    _ensure_tables()

    # Step 1: Decay 매트릭스 계산
    print(f"\n── Step 1: 등급별 × 보유기간별 Decay 매트릭스 ──")
    matrix = _calc_decay_matrix(calc_date)

    valid = [r for r in matrix if r["avg_return"] is not None]
    print(f"\n  계산 완료: {len(valid)}/{len(matrix)} 유효 셀")

    # Step 2: Half-Life 계산
    print(f"\n── Step 2: 등급별 Signal Half-Life ──")
    half_lives = _calc_half_life(matrix)

    # Step 3: DB 저장
    print(f"\n── Step 3: DB 저장 ──")
    _save_decay_matrix(calc_date, matrix)
    _save_half_lives(calc_date, half_lives)

    # Step 4: 주간 리포트 (금요일)
    if calc_date.weekday() == 4:  # 금요일
        print(f"\n── Step 4: 주간 Alpha Decay 리포트 ──")
        _send_weekly_report(calc_date, matrix, half_lives)
    else:
        print(f"\n[DECAY] 주간 리포트: 금요일에 발행 (오늘={calc_date.strftime('%A')})")

    # Summary
    print(f"\n{'='*60}")
    print(f"  Alpha Decay Tracker 완료")
    active = sum(1 for h in half_lives if h.get("status") == "ACTIVE")
    weak = sum(1 for h in half_lives if h.get("status") in ("WEAK", "FAST_DECAY"))
    dead = sum(1 for h in half_lives if h.get("status") == "DEAD")
    print(f"  시그널 상태: ACTIVE={active} | WEAK={weak} | DEAD={dead}")
    print(f"{'='*60}")

    return {
        "ok": 1,
        "valid_cells": len(valid),
        "half_lives": {h["grade"]: h.get("half_life") for h in half_lives},
        "active": active, "weak": weak, "dead": dead,
    }


# 하위호환
run_all = run_alpha_decay


if __name__ == "__main__":
    import sys
    d = None
    if len(sys.argv) > 1:
        d = date.fromisoformat(sys.argv[1])
    run_alpha_decay(d)
