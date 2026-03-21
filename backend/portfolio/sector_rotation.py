"""
portfolio/sector_rotation.py — 국면별 섹터 순환 전략
=====================================================
시장 국면(BULL/NEUTRAL/BEAR/CRISIS)에 따라
선호 섹터에 비중을 가산/감산하여 알파를 추구합니다.

근거: 경기 순환(Business Cycle)에 따른 섹터 성과 차이
  - BULL   → 기술주/소비재 등 성장 섹터 아웃퍼폼
  - BEAR   → 유틸리티/필수소비재 등 방어 섹터 아웃퍼폼
  - CRISIS → 현금 최우선, 방어주만 최소 보유
"""
from typing import Dict, List, Optional
from dataclasses import dataclass


# ═══════════════════════════════════════════════════════════
#  GICS 11 섹터 코드 → 이름 매핑
# ═══════════════════════════════════════════════════════════

SECTOR_NAMES = {
    "10": "Energy",
    "15": "Materials",
    "20": "Industrials",
    "25": "Consumer Discretionary",
    "30": "Consumer Staples",
    "35": "Healthcare",
    "40": "Financials",
    "45": "Information Technology",
    "50": "Communication Services",
    "55": "Utilities",
    "60": "Real Estate",
}


# ═══════════════════════════════════════════════════════════
#  국면별 섹터 선호도 (부스트 %)
# ═══════════════════════════════════════════════════════════

# 값: 해당 섹터 비중에 곱하는 배수 (1.0 = 중립, 1.2 = +20%)
REGIME_SECTOR_PREFS = {
    "BULL": {
        "45": 1.25,  # Tech +25%
        "25": 1.20,  # Consumer Disc +20%
        "20": 1.15,  # Industrials +15%
        "50": 1.10,  # Communication +10%
        "40": 1.05,  # Financials +5%
        "35": 0.95,  # Healthcare -5%
        "55": 0.80,  # Utilities -20%
        "30": 0.85,  # Staples -15%
        "60": 0.90,  # Real Estate -10%
        "10": 1.00,  # Energy =
        "15": 1.00,  # Materials =
    },
    "NEUTRAL": {
        "45": 1.10,  # Tech +10%
        "35": 1.15,  # Healthcare +15%
        "40": 1.10,  # Financials +10%
        "25": 1.00,
        "20": 1.00,
        "50": 1.00,
        "30": 1.05,  # Staples +5%
        "55": 1.00,
        "60": 1.00,
        "10": 0.95,
        "15": 0.95,
    },
    "BEAR": {
        "55": 1.30,  # Utilities +30%
        "35": 1.25,  # Healthcare +25%
        "30": 1.25,  # Staples +25%
        "60": 1.10,  # Real Estate +10%
        "40": 1.00,  # Financials =
        "10": 0.90,  # Energy -10%
        "45": 0.80,  # Tech -20%
        "25": 0.75,  # Consumer Disc -25%
        "20": 0.85,  # Industrials -15%
        "50": 0.85,  # Communication -15%
        "15": 0.90,  # Materials -10%
    },
    "CRISIS": {
        "55": 1.40,  # Utilities +40%
        "35": 1.20,  # Healthcare +20%
        "30": 1.20,  # Staples +20%
        "40": 0.80,  # Financials -20%
        "45": 0.60,  # Tech -40%
        "25": 0.50,  # Consumer Disc -50%
        "20": 0.70,  # Industrials -30%
        "50": 0.70,  # Communication -30%
        "60": 0.80,  # Real Estate -20%
        "10": 0.70,  # Energy -30%
        "15": 0.70,  # Materials -30%
    },
}


@dataclass
class SectorAllocation:
    """섹터 배분 결과"""
    sector_code: str
    sector_name: str
    base_weight: float         # 시장 가중 (S&P500 기준)
    regime_multiplier: float   # 국면 부스트 배수
    adjusted_weight: float     # 조정 후 비중
    current_weight: float      # 현재 포폴 비중 (참고)


class SectorRotation:
    """
    국면별 섹터 비중 조절.

    사용법:
        sr = SectorRotation()
        prefs = sr.get_sector_preferences("BEAR")
        adjusted = sr.adjust_candidate_weights(candidates, "BEAR")
    """

    # S&P 500 대략적 시가총액 비중 (2024 기준)
    SP500_SECTOR_WEIGHTS = {
        "45": 0.30,   # Tech
        "35": 0.13,   # Healthcare
        "40": 0.13,   # Financials
        "25": 0.10,   # Consumer Disc
        "50": 0.09,   # Communication
        "20": 0.09,   # Industrials
        "30": 0.06,   # Staples
        "10": 0.04,   # Energy
        "55": 0.02,   # Utilities
        "60": 0.02,   # Real Estate
        "15": 0.02,   # Materials
    }

    def get_sector_preferences(self, regime: str) -> Dict[str, SectorAllocation]:
        """국면별 섹터 배분 계산"""
        prefs = REGIME_SECTOR_PREFS.get(regime, REGIME_SECTOR_PREFS["NEUTRAL"])
        result = {}

        total_raw = 0
        raw_weights = {}
        for code, base in self.SP500_SECTOR_WEIGHTS.items():
            mult = prefs.get(code, 1.0)
            adj = base * mult
            raw_weights[code] = adj
            total_raw += adj

        # 정규화 (합 = 1.0)
        for code, raw in raw_weights.items():
            normalized = raw / total_raw if total_raw > 0 else 0
            result[code] = SectorAllocation(
                sector_code=code,
                sector_name=SECTOR_NAMES.get(code, "Unknown"),
                base_weight=self.SP500_SECTOR_WEIGHTS.get(code, 0),
                regime_multiplier=prefs.get(code, 1.0),
                adjusted_weight=round(normalized, 4),
                current_weight=0,
            )

        return result

    def get_sector_boost(self, sector_code: str, regime: str) -> float:
        """특정 섹터의 국면 부스트 배수"""
        prefs = REGIME_SECTOR_PREFS.get(regime, REGIME_SECTOR_PREFS["NEUTRAL"])
        return prefs.get(sector_code, 1.0)

    def adjust_candidate_scores(
        self, candidates: List[dict], regime: str, boost_factor: float = 0.15
    ) -> List[dict]:
        """
        매수 후보의 점수에 섹터 부스트 반영.
        선호 섹터 종목은 점수가 올라가고, 비선호는 내려감.

        Parameters
        ----------
        boost_factor : float  부스트 영향도 (0.15 = 최대 ±15% 조절)
        """
        prefs = REGIME_SECTOR_PREFS.get(regime, REGIME_SECTOR_PREFS["NEUTRAL"])

        for c in candidates:
            sector = c.get("sector", "99")
            mult = prefs.get(sector, 1.0)
            # 1.2 → +0.15×(1.2-1.0) = +0.03 → 점수 ×1.03
            score_adj = 1.0 + boost_factor * (mult - 1.0)
            c["sector_adjusted_score"] = c.get("final_score", 0) * score_adj
            c["sector_boost"] = round(mult, 2)

        return candidates

    def check_sector_limits(
        self,
        positions: Dict[str, dict],
        sector_max_pct: float = 0.30,
    ) -> Dict[str, dict]:
        """
        현재 포폴의 섹터 집중도 체크.
        Returns dict: {sector_code: {weight, over_limit, excess}}
        """
        sector_values = {}
        total = 0
        for ticker, pos in positions.items():
            sector = pos.get("sector", "99")
            val = pos.get("shares", 0) * pos.get("current_price", 0)
            sector_values[sector] = sector_values.get(sector, 0) + val
            total += val

        result = {}
        for sector, val in sector_values.items():
            weight = val / total if total > 0 else 0
            result[sector] = {
                "name": SECTOR_NAMES.get(sector, "Unknown"),
                "weight": round(weight, 4),
                "value": round(val, 2),
                "over_limit": weight > sector_max_pct,
                "excess": round(max(0, weight - sector_max_pct), 4),
            }

        return result
