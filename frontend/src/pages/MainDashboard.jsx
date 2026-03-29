/**
 * MainDashboard.jsx — v3
 *
 * 수정:
 *  - stockCount/lastBatch 제거 (Topbar props 제거)
 *  - StockTable에 onResetSector 전달 → Reset 버튼 시 URL도 /main으로
 */
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { C } from "../styles/tokens";
import Topbar        from "../components/layout/Topbar";
import MarketMarquee from "../components/layout/MarketMarquee";
import Sidebar       from "../components/layout/Sidebar";
import StockTable    from "../components/dashboard/StockTable";

export default function MainDashboard() {
  const navigate  = useNavigate();
  const { sectorId } = useParams();
  const [activeTab, setActiveTab] = useState("SCREENER");

  const handleTickerClick = (ticker) => window.open(`/stock/${ticker}/summary`, "_blank", "noopener");

  const handleSectorClick = (key) => {
    if (sectorId === key) navigate("/main");
    else navigate(`/main/${key}`);
    setActiveTab("SCREENER");
  };

  // Reset 버튼 → 사이드바 섹터 선택도 해제 (URL /main으로)
  const handleResetSector = () => navigate("/main");

  return (
    <div style={{
      display: "flex", flexDirection: "column",
      height: "100vh", background: C.bgDeep,
      color: C.textPri, overflow: "hidden",
    }}>
      <Topbar activeTab={activeTab} onTabChange={setActiveTab} />
      <MarketMarquee />

      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        <Sidebar activeSector={sectorId} onSectorClick={handleSectorClick} />

        <main style={{ flex: 1, overflow: "hidden", display: "flex", flexDirection: "column", minWidth: 0 }}>
          {activeTab === "SCREENER" && (
            <StockTable
              filterSector={sectorId}
              onTickerClick={handleTickerClick}
              onResetSector={handleResetSector}
            />
          )}
          {activeTab === "SIGNALS" && <Placeholder label="SIGNALS" sub="뉴스 Sentiment · 어닝콜 Tone — Phase 2" />}
          {activeTab === "SECTORS" && <Placeholder label="SECTORS" sub="섹터 비교 대시보드 — Phase 2" />}
          {activeTab === "MARKET"  && <Placeholder label="MARKET"  sub="거시지표 대시보드 — Phase 3" />}
        </main>
      </div>
    </div>
  );
}

function Placeholder({ label, sub }) {
  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 8 }}>
      <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 13, color: "#555" }}>{label}</div>
      <div style={{ fontFamily: "'Inter', sans-serif", fontSize: 11, color: "#333" }}>{sub}</div>
    </div>
  );
}
