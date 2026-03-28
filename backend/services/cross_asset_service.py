"""
cross_asset_service.py — Cross-Asset Intelligence 서비스
========================================================
GET /api/market/cross-asset 엔드포인트에 데이터를 공급.
batch_cross_asset_v5.py가 cross_asset_daily 테이블에 저장한 데이터를 조회.
"""
from datetime import date
from db_pool import get_cursor


def _f(v, digits=2):
    return round(float(v), digits) if v is not None else None


def get_cross_asset_latest() -> dict | None:
    """
    최신 Cross-Asset 데이터 조회.
    Returns:
        {
            "calcDate": "2026-03-28",
            "totalScore": 62.5,
            "dataQuality": "FULL",
            "assets": { "TLT": 98.5, "GLD": 210.3, ... },
            "signals": [
                {"name":"Risk Appetite","score":7.2,"max":10,"zscore":1.3,"momentum":2.1,"signal":"BULLISH"},
                ...
            ],
            "derived": {
                "copperGoldRatio": 0.045, "hySpreadProxy": -0.8,
                "smallLargeRatio": 0.42, "stockBondCorr20d": -0.15,
            },
        }
    """
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT * FROM cross_asset_daily
                ORDER BY calc_date DESC LIMIT 1
            """)
            row = cur.fetchone()
        if not row:
            return None

        return {
            "calcDate": str(row["calc_date"]),
            "totalScore": _f(row["cross_asset_total"]),
            "dataQuality": row["data_quality"] or "UNKNOWN",
            "assets": {
                "TLT": _f(row["tlt_close"]),
                "SHY": _f(row["shy_close"]),
                "HYG": _f(row["hyg_close"]),
                "LQD": _f(row["lqd_close"]),
                "GLD": _f(row["gld_close"]),
                "USO": _f(row["uso_close"]),
                "CPER": _f(row["cper_close"]),
                "UUP": _f(row["uup_close"]),
                "EEM": _f(row["eem_close"]),
                "FXI": _f(row["fxi_close"]),
                "EWJ": _f(row["ewj_close"]),
                "QQQ": _f(row["qqq_close"]),
                "IWM": _f(row["iwm_close"]),
                "SPY": _f(row["spy_close"]),
            },
            "signals": [
                {
                    "name": "Risk Appetite",
                    "nameKr": "위험선호 지수",
                    "score": _f(row["risk_appetite_score"]),
                    "max": 10,
                    "zscore": _f(row["risk_appetite_zscore"], 3),
                    "momentum": _f(row["risk_appetite_idx"], 4),
                    "signal": _sig(row["risk_appetite_score"]),
                    "desc": "하이일드/투자등급 × 주식/국채 비율 20일 변화",
                },
                {
                    "name": "Rate Spread",
                    "nameKr": "금리 스프레드",
                    "score": _f(row["rate_spread_score"]),
                    "max": 10,
                    "zscore": _f(row["spread_zscore"], 3),
                    "momentum": _f(row["spread_momentum"], 4),
                    "signal": _sig(row["rate_spread_score"]),
                    "desc": "장단기 금리차 프록시 (SHY/TLT 비율 변화)",
                },
                {
                    "name": "Safe Haven",
                    "nameKr": "안전자산 수요",
                    "score": _f(row["safe_haven_score"]),
                    "max": 10,
                    "zscore": _f(row["safe_haven_zscore"], 3),
                    "momentum": _f(row["safe_haven_momentum"], 4),
                    "signal": _sig(row["safe_haven_score"], inverse=True),
                    "desc": "금+장기국채 20일 모멘텀 (상승=Risk-Off)",
                },
                {
                    "name": "Dollar Impact",
                    "nameKr": "달러 영향",
                    "score": _f(row["dollar_score"]),
                    "max": 10,
                    "zscore": _f(row["dollar_zscore"], 3),
                    "momentum": _f(row["dollar_momentum"], 4),
                    "signal": _sig(row["dollar_score"], inverse=True),
                    "desc": "달러 인덱스 20일 변화 (강세=주식 부정)",
                },
                {
                    "name": "Global Growth",
                    "nameKr": "글로벌 성장",
                    "score": _f(row["global_growth_score"]),
                    "max": 10,
                    "zscore": _f(row["global_growth_zscore"], 3),
                    "momentum": _f(row["global_growth_momentum"], 4),
                    "signal": _sig(row["global_growth_score"]),
                    "desc": "이머징+중국+일본+소형주 평균 모멘텀",
                },
                {
                    "name": "Market Breadth",
                    "nameKr": "시장 폭",
                    "score": _f(row["breadth_score"]),
                    "max": 10,
                    "zscore": _f(row["breadth_zscore"], 3),
                    "signal": _sig(row["breadth_score"]),
                    "desc": "소형주/대형주 비율 (IWM/SPY)",
                },
                {
                    "name": "Copper/Gold",
                    "nameKr": "구리/금 비율",
                    "score": _f(row["copper_gold_score"]),
                    "max": 10,
                    "signal": _sig(row["copper_gold_score"]),
                    "desc": "경기 선행지표 (구리↑금↓ = 경기 확장)",
                },
                {
                    "name": "HY Spread",
                    "nameKr": "하이일드 스프레드",
                    "score": _f(row["hy_spread_score"]),
                    "max": 10,
                    "signal": _sig(row["hy_spread_score"]),
                    "desc": "신용 위험 프록시 (HYG/LQD 비율)",
                },
            ],
            "derived": {
                "copperGoldRatio": _f(row["copper_gold_ratio"], 4),
                "hySpreadProxy": _f(row["hy_spread_proxy"], 4),
                "smallLargeRatio": _f(row["small_large_ratio"], 4),
                "stockBondCorr20d": _f(row["stock_bond_corr_20d"], 4),
            },
        }
    except Exception as e:
        print(f"[CROSS-ASSET-SVC] 에러: {e}")
        return None


def _sig(score, inverse=False):
    """점수 → 시그널 라벨"""
    if score is None:
        return "N/A"
    s = float(score)
    if inverse:
        s = 10 - s
    if s >= 7:
        return "BULLISH"
    if s >= 4:
        return "NEUTRAL"
    return "BEARISH"
