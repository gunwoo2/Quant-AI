"""
analytics/performance_attribution.py — Brinson-Fachler 수익 분해
=================================================================
포트폴리오 수익률을 다음으로 분해합니다:

  Total Return = Allocation Effect + Selection Effect + Interaction

  ① Allocation Effect (섹터 배분 효과)
  ② Selection Effect (종목 선택 효과)
  ③ Interaction Effect

주간/월간 리포트에 자동 포함됩니다.
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import date


@dataclass
class SectorAttribution:
    sector: str
    sector_name: str = ""
    portfolio_weight: float = 0.0
    benchmark_weight: float = 0.0
    active_weight: float = 0.0
    portfolio_return: float = 0.0
    benchmark_return: float = 0.0
    allocation_effect: float = 0.0
    selection_effect: float = 0.0
    interaction_effect: float = 0.0
    total_effect: float = 0.0


@dataclass
class AttributionReport:
    period_start: date = None
    period_end: date = None
    portfolio_return: float = 0.0
    benchmark_return: float = 0.0
    active_return: float = 0.0
    total_allocation: float = 0.0
    total_selection: float = 0.0
    total_interaction: float = 0.0
    residual: float = 0.0
    sector_details: List[SectorAttribution] = field(default_factory=list)
    factor_contributions: Dict[str, float] = field(default_factory=dict)
    top_contributors: List[Dict] = field(default_factory=list)
    bottom_contributors: List[Dict] = field(default_factory=list)


SP500_SECTOR_WEIGHTS = {
    "45": 0.30, "35": 0.13, "40": 0.13, "25": 0.10,
    "50": 0.09, "20": 0.09, "30": 0.06, "10": 0.04,
    "55": 0.02, "60": 0.02, "15": 0.02,
}

SECTOR_NAMES = {
    "10": "Energy", "15": "Materials", "20": "Industrials",
    "25": "ConsDisc", "30": "Staples", "35": "Healthcare",
    "40": "Financials", "45": "Tech", "50": "CommSvcs",
    "55": "Utilities", "60": "RealEstate",
}


class PerformanceAttribution:

    def calculate(
        self,
        period_start: date,
        period_end: date,
        positions: Dict[str, dict],
        position_returns: Dict[str, float],
        benchmark_sector_returns: Dict[str, float],
        total_benchmark_return: float,
    ) -> AttributionReport:
        report = AttributionReport(
            period_start=period_start,
            period_end=period_end,
            benchmark_return=total_benchmark_return,
        )

        # ── 포폴 섹터별 비중/수익 집계 ──
        sector_port_weights = {}
        sector_port_return_sums = {}
        total_port_weight = 0

        for ticker, pos in positions.items():
            sector = pos.get("sector", "99")
            w = pos.get("weight", 0)
            r = position_returns.get(ticker, 0)

            if sector not in sector_port_weights:
                sector_port_weights[sector] = 0
                sector_port_return_sums[sector] = 0

            sector_port_weights[sector] += w
            sector_port_return_sums[sector] += w * r
            total_port_weight += w

        # 비중 정규화 (합 = 1.0) — Brinson-Fachler는 100% 투자 가정
        if total_port_weight > 0 and abs(total_port_weight - 1.0) > 0.001:
            for sec in sector_port_weights:
                sector_port_return_sums[sec] /= total_port_weight
                sector_port_weights[sec] /= total_port_weight

        # 섹터별 가중 평균 수익률
        sector_port_returns = {}
        for sec in sector_port_weights:
            w = sector_port_weights[sec]
            if w > 0:
                sector_port_returns[sec] = sector_port_return_sums[sec] / w
            else:
                sector_port_returns[sec] = 0

        # 포폴 전체 수익률
        port_total = sum(
            sector_port_weights.get(s, 0) * sector_port_returns.get(s, 0)
            for s in sector_port_weights
        )
        report.portfolio_return = port_total
        report.active_return = port_total - total_benchmark_return

        # ── Brinson-Fachler 분해 ──
        all_sectors = set(list(sector_port_weights.keys()) + list(SP500_SECTOR_WEIGHTS.keys()))

        total_alloc = 0
        total_select = 0
        total_interact = 0

        for sec in sorted(all_sectors):
            wp = sector_port_weights.get(sec, 0)
            wb = SP500_SECTOR_WEIGHTS.get(sec, 0)
            rb = benchmark_sector_returns.get(sec, 0)

            # 핵심: 포폴에 없는 섹터 → rp를 벤치마크 수익률로 가정 (passive tracking)
            # 투자하지 않은 섹터는 "벤치마크 수준 수익"으로 취급
            if sec in sector_port_returns:
                rp = sector_port_returns[sec]
            else:
                rp = rb  # passive tracking

            alloc = (wp - wb) * (rb - total_benchmark_return)
            select = wb * (rp - rb)
            interact = (wp - wb) * (rp - rb)

            total_alloc += alloc
            total_select += select
            total_interact += interact

            sa = SectorAttribution(
                sector=sec,
                sector_name=SECTOR_NAMES.get(sec, "Unknown"),
                portfolio_weight=round(wp, 4),
                benchmark_weight=round(wb, 4),
                active_weight=round(wp - wb, 4),
                portfolio_return=round(rp, 4),
                benchmark_return=round(rb, 4),
                allocation_effect=round(alloc, 6),
                selection_effect=round(select, 6),
                interaction_effect=round(interact, 6),
                total_effect=round(alloc + select + interact, 6),
            )
            report.sector_details.append(sa)

        report.total_allocation = round(total_alloc, 6)
        report.total_selection = round(total_select, 6)
        report.total_interaction = round(total_interact, 6)
        report.residual = round(
            report.active_return - total_alloc - total_select - total_interact, 6
        )

        # ── Top/Bottom 기여 종목 ──
        contributions = []
        for ticker, pos in positions.items():
            w = pos.get("weight", 0)
            if total_port_weight > 0:
                w = w / total_port_weight
            r = position_returns.get(ticker, 0)
            contribution = w * r
            contributions.append({
                "ticker": ticker,
                "weight": round(w, 4),
                "return": round(r, 4),
                "contribution": round(contribution, 6),
                "pnl_dollar": round(pos.get("position_value", 0) * r, 2),
            })

        contributions.sort(key=lambda x: x["contribution"], reverse=True)
        report.top_contributors = contributions[:5]
        report.bottom_contributors = contributions[-5:][::-1]

        return report

    def save_to_db(self, report: AttributionReport, period_type: str = "WEEKLY"):
        from db_pool import get_cursor
        with get_cursor() as cur:
            cur.execute("""
                INSERT INTO performance_summary
                    (period_type, period_start, period_end,
                     return_pct, vs_spy_pct,
                     allocation_effect, selection_effect)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (period_type, period_start) DO UPDATE SET
                    period_end = EXCLUDED.period_end,
                    return_pct = EXCLUDED.return_pct,
                    vs_spy_pct = EXCLUDED.vs_spy_pct,
                    allocation_effect = EXCLUDED.allocation_effect,
                    selection_effect = EXCLUDED.selection_effect
            """, (
                period_type, report.period_start, report.period_end,
                report.portfolio_return, report.active_return,
                report.total_allocation, report.total_selection,
            ))
        print(f"  ✅ Attribution 저장: {period_type} {report.period_start}~{report.period_end}")
