/**
 * StockTable.jsx — v4 (백엔드 API 연결)
 *
 * 변경:
 *  - MOCK_STOCKS → GET /api/stocks 실제 호출
 *  - 섹터 필터: backendName 역매핑으로 정확한 비교
 *  - 삭제: DELETE /api/ticker 실제 호출 후 목록에서 제거
 *  - API 실패 시 MOCK_STOCKS fallback + 배너 표시
 *  - null 값 안전 처리 (배치잡 전 score/price 등 null 가능)
 */

import { useState, useMemo, useEffect, useCallback } from "react";
import { C, FONT, SECTORS, MOCK_STOCKS, gradeColor, gradeLabel, gradeTextColor, chgColor, signalColor, sectorByBackendName } from "../../styles/tokens";
import { DeleteConfirmModal } from "./Modals";
import api from "../../api";

const GRADES    = ["ALL", "S", "A+", "A", "B+", "B", "C", "D"];
const COUNTRIES = ["ALL", "US", "KR", "JP"];

// 정렬용 숫자 매핑 (높을수록 좋음)
const _GRADE_ORDER = { "S": 7, "A+": 6, "A": 5, "B+": 4, "B": 3, "C": 2, "D": 1 };
const _SIGNAL_ORDER = {
  "STRONG_BUY": 7, "BUY": 6, "OUTPERFORM": 5, "HOLD": 4,
  "UNDERPERFORM": 3, "SELL": 2, "STRONG_SELL": 1,
};

// ── 컬럼 총합 목표 ~870px (사이드바 210 포함 시 1080px → 1280px 이상 화면에서 스크롤 없음)
const COLUMNS = [
  { key: "ticker",    label: "TICKER",    width: 74  },
  { key: "name",      label: "COMPANY",   width: 140 },
  { key: "sector",    label: "SECTOR",    width: 80  },
  { key: "price",     label: "PRICE",     width: 82  },
  { key: "chg",       label: "CHG%",      width: 62  },
  { key: "l1",        label: "L1",        width: 44,  tip: "퀀트 레이팅 (Fundamental)"     },
  { key: "l2",        label: "L2",        width: 44,  tip: "텍스트·감성 신호 (NLP/AI)"     },
  { key: "l3",        label: "L3",        width: 44,  tip: "시장 신호 (Price/Order Flow)"  },
  { key: "score",     label: "SCORE",     width: 62,  tip: "L1+L2+L3 가중합 (Stat)"      },
  { key: "signal",    label: "Q.SIG",     width: 72,  tip: "퀀트 전용 시그널 (Stat 기반)"  },
  { key: "ai_score",  label: "AI",        width: 48,  tip: "XGBoost AI 예측 점수"          },
  { key: "ensemble",  label: "ENSEMBLE",  width: 68,  tip: "Stat×0.7 + AI×0.3 통합"       },
  { key: "grade",     label: "GRADE",     width: 48  },
  { key: "ai_signal", label: "SIGNAL",    width: 80,  tip: "퀀트+AI 최종 시그널"           },
];
// 체크박스(28) + 컬럼합(968) + 좌우패딩(32) = 1028px

function nextSort(dir, clickedKey, sortKey) {
  if (sortKey !== clickedKey) return { key: clickedKey, dir: "desc" };
  if (dir === "desc")          return { key: clickedKey, dir: "asc"  };
  return { key: null, dir: null };
}

/** sector_name (API) → 프론트 표시용 짧은 이름 */
const sectorDisplay = (apiName) => {
  if (!apiName) return "—";
  const found = sectorByBackendName(apiName);
  return found ? found.en : apiName.split(" ")[0];
};

export default function StockTable({ onTickerClick, filterSector, onResetSector }) {
  // ── 데이터 상태
  const [stocks,      setStocks]      = useState([]);
  const [loading,     setLoading]     = useState(true);
  const [isMockData,  setIsMockData]  = useState(false);

  // ── 필터 상태
  const [search,     setSearch]     = useState("");
  const [searchName, setSearchName] = useState("");
  const [selSector,  setSelSector]  = useState("ALL");
  const [selCountry, setSelCountry] = useState("ALL");
  const [selGrade,   setSelGrade]   = useState("ALL");
  const [sort,       setSort]       = useState({ key: "score", dir: "desc" });

  // ── 체크박스 / 삭제
  const [checked,    setChecked]    = useState(new Set());
  const [showDelete, setShowDelete] = useState(false);
  const [deleting,   setDeleting]   = useState(false);

  // ── /api/stocks 호출
  const fetchStocks = useCallback(() => {
    setLoading(true);
    api.get("/api/stocks")
      .then(res => {
        const data = Array.isArray(res.data) ? res.data : [];
        setStocks(data);
        setIsMockData(false);
      })
      .catch(() => {
        setStocks(MOCK_STOCKS);
        setIsMockData(true);
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { fetchStocks(); }, [fetchStocks]);

  // filterSector (URL param) → selSector 동기화
  useEffect(() => {
    setSelSector(filterSector ?? "ALL");
  }, [filterSector]);

  // ── 필터 / 정렬
  const rows = useMemo(() => {
    let data = [...stocks];

    if (search)               data = data.filter(s => s.ticker?.includes(search.toUpperCase()));
    if (searchName)           data = data.filter(s => s.name?.toLowerCase().includes(searchName.toLowerCase()));

    if (selSector !== "ALL") {
      // key("TECHNOLOGY") → backendName("Information Technology") 역매핑 비교
      const sectorObj = SECTORS.find(s => s.key === selSector);
      if (sectorObj) {
        data = data.filter(s =>
          s.sector === sectorObj.backendName ||
          s.sector === sectorObj.en ||
          sectorByBackendName(s.sector)?.key === selSector
        );
      }
    }

    if (selCountry !== "ALL") data = data.filter(s => s.country === selCountry);
    if (selGrade   !== "ALL") data = data.filter(s => s.grade   === selGrade);

    if (sort.key && sort.dir) {
      data.sort((a, b) => {
        let av = a[sort.key] ?? null;
        let bv = b[sort.key] ?? null;

        // null 처리: null은 항상 뒤로
        if (av == null && bv == null) return 0;
        if (av == null) return 1;
        if (bv == null) return -1;

        // 등급/시그널: 숫자 매핑 후 비교
        if (sort.key === "grade") {
          av = _GRADE_ORDER[av] ?? -1;
          bv = _GRADE_ORDER[bv] ?? -1;
        } else if (sort.key === "signal" || sort.key === "ai_signal") {
          av = _SIGNAL_ORDER[av] ?? -1;
          bv = _SIGNAL_ORDER[bv] ?? -1;
        } else if (typeof av === "string") {
          av = av.toLowerCase();
          bv = String(bv).toLowerCase();
        }

        if (av < bv) return sort.dir === "desc" ?  1 : -1;
        if (av > bv) return sort.dir === "desc" ? -1 :  1;
        return 0;
      });
    }
    return data;
  }, [stocks, search, searchName, selSector, selCountry, selGrade, sort]);

  // ── 체크박스
  const allIds     = rows.map(r => r.ticker);
  const allChecked = allIds.length > 0 && allIds.every(id => checked.has(id));
  const toggleAll  = () => setChecked(allChecked ? new Set() : new Set(allIds));
  const toggleOne  = (t) => {
    const n = new Set(checked);
    n.has(t) ? n.delete(t) : n.add(t);
    setChecked(n);
  };

  // ── 리셋
  const reset = () => {
    setSearch(""); setSearchName("");
    setSelSector("ALL"); setSelCountry("ALL"); setSelGrade("ALL");
    onResetSector?.();
  };

  // ── 정렬
  const handleSort = (key) => {
    setSort(prev => nextSort(prev.dir, key, prev.key));
  };

  // ── 실제 삭제: DELETE /api/ticker
  const handleDelete = async () => {
    const tickers = [...checked];
    setDeleting(true);
    try {
      await api.delete("/api/ticker", { data: { tickers } });
      setStocks(prev => prev.filter(s => !checked.has(s.ticker)));
      setChecked(new Set());
      setShowDelete(false);
    } catch (e) {
      console.error("Delete failed:", e);
      // 실패해도 UI 초기화
      setChecked(new Set());
      setShowDelete(false);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden", fontFamily: "'Inter', sans-serif" }}>

      {/* ── Mock 데이터 배너 */}
      {isMockData && (
        <div style={{
          padding: "5px 16px", background: `${C.golden}12`,
          borderBottom: `1px solid ${C.golden}40`,
          fontSize: 10, color: C.golden, fontFamily: "'Inter', sans-serif",
          display: "flex", alignItems: "center", gap: 8, flexShrink: 0,
        }}>
          ⚠ MOCK DATA — 백엔드 연결 실패. 실제 데이터를 불러오지 못했습니다.
          <button onClick={fetchStocks} style={{ background: "none", border: `1px solid ${C.golden}50`, color: C.golden, fontSize: 10, padding: "2px 8px", cursor: "pointer", borderRadius: 2 }}>
            재시도
          </button>
        </div>
      )}

      {/* ── 필터 바 */}
      <div style={{
        padding: "9px 16px",
        background: "#000000",
        borderBottom: `1px solid ${C.border}`,
        display: "flex", alignItems: "center",
        gap: 7, flexWrap: "nowrap", flexShrink: 0,
        overflowX: "auto",
      }}>
        <FInput value={search}     onChange={setSearch}     placeholder="Ticker"       width={80}  />
        <FInput value={searchName} onChange={setSearchName} placeholder="Company Name" width={150} />
        <FSelect value={selCountry} onChange={setSelCountry}
          options={COUNTRIES.map(c => ({ value: c, label: c === "ALL" ? "All Countries" : c }))} />
        <FSelect value={selSector} onChange={setSelSector}
          options={[{ value: "ALL", label: "All Sectors" }, ...SECTORS.map(s => ({ value: s.key, label: s.en }))]}
          highlight={selSector !== "ALL"} />
        <FSelect value={selGrade} onChange={setSelGrade}
          options={GRADES.map(g => ({ value: g, label: g === "ALL" ? "All Ratings" : g }))} />

        <button onClick={reset} style={{
          fontFamily: "'Inter', sans-serif", fontSize: 12,
          color: C.pink, background: "none",
          border: `1px solid ${C.pink}55`,
          borderRadius: 3, padding: "5px 11px", cursor: "pointer",
          whiteSpace: "nowrap", flexShrink: 0,
        }}>
          Reset
        </button>

        {/* 삭제 버튼 */}
        {checked.size > 0 && (
          <button onClick={() => setShowDelete(true)} style={{
            fontFamily: "'Inter', sans-serif", fontSize: 12,
            color: C.down, background: "none",
            border: `1px solid ${C.down}55`,
            borderRadius: 3, padding: "5px 11px", cursor: "pointer",
            whiteSpace: "nowrap", flexShrink: 0, marginLeft: "auto",
          }}>
            ✕ {checked.size}개 삭제
          </button>
        )}
      </div>

      {/* ── 헤더 + 바디: 단일 가로스크롤 컨테이너로 묶어야 열 정렬 유지 */}
      <div style={{ flex: 1, overflowX: "auto", overflowY: "hidden", display: "flex", flexDirection: "column" }}>

        {/* 헤더 */}
        <div style={{
          display: "flex", alignItems: "center",
          padding: "0 16px", height: 34,
          background: C.bgDeeper,
          borderBottom: `1px solid ${C.border}`,
          flexShrink: 0,
          minWidth: "fit-content",
        }}>
          <div style={{ width: 28, flexShrink: 0 }}>
            <input type="checkbox" checked={allChecked} onChange={toggleAll}
              style={{ accentColor: C.primary, cursor: "pointer" }} />
          </div>
          {COLUMNS.map(col => (
            <ColHead key={col.key} col={col} sort={sort}
              onSort={() => handleSort(col.key)} />
          ))}
        </div>

        {/* 바디: 세로 스크롤만, 가로는 부모 컨테이너가 담당 */}
        <div style={{ flex: 1, overflowY: "auto", overflowX: "visible" }}>
          {loading ? (
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", gap: 10 }}>
              <div style={{ width: 16, height: 16, border: `2px solid ${C.primary}`, borderTopColor: "transparent", borderRadius: "50%", animation: "spin 0.8s linear infinite" }} />
              <span style={{ color: C.textMuted, fontSize: 13, fontFamily: "'Inter', sans-serif" }}>데이터 로딩 중...</span>
              <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
            </div>
          ) : rows.length === 0 ? (
            <Empty />
          ) : (
            rows.map((row, i) => (
              <Row
                key={row.ticker}
                row={row}
                odd={i % 2 === 1}
                checked={checked.has(row.ticker)}
                onCheck={() => toggleOne(row.ticker)}
                onClick={() => onTickerClick?.(row.ticker)}
              />
            ))
          )}
        </div>

      </div>

      {/* ── 푸터 */}
      <div style={{
        borderTop: `1px solid ${C.border}`,
        padding: "5px 16px",
        fontSize: 11, color: C.textMuted,
        background: C.bgDeeper,
        display: "flex", justifyContent: "space-between", alignItems: "center",
        flexShrink: 0,
      }}>
        <span>
          {loading ? "로딩 중..." : `총 ${stocks.length}개 종목 · 필터 결과 ${rows.length}개`}
          {isMockData && <span style={{ color: C.golden, marginLeft: 8 }}>[MOCK]</span>}
        </span>
        {checked.size > 0 && (
          <span style={{ color: C.primary }}>{checked.size}개 선택됨</span>
        )}
      </div>

      {/* ── 삭제 모달 */}
      {showDelete && (
        <DeleteConfirmModal
          tickers={[...checked]}
          onClose={() => setShowDelete(false)}
          onConfirm={handleDelete}
          isLoading={deleting}
        />
      )}
    </div>
  );
}

/* ── ColHead */
function ColHead({ col, sort, onSort }) {
  const [hov, setHov] = useState(false);
  const isActive = sort.key === col.key && sort.dir;
  const arrow = isActive ? (sort.dir === "desc" ? " ▼" : " ▲") : (hov ? " ⇅" : "");

  return (
    <div onClick={onSort}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      title={col.tip}
      style={{
        width: col.width, minWidth: col.width, flexShrink: 0,
        fontFamily: "'Inter', sans-serif", fontSize: 10, fontWeight: 600,
        letterSpacing: 0.4,
        color: isActive ? C.primary : hov ? C.textGray : C.textMuted,
        cursor: "pointer", userSelect: "none",
        display: "flex", alignItems: "center", padding: "0 4px",
      }}
    >
      {col.label}
      <span style={{ fontSize: 7, marginLeft: 2, opacity: hov || isActive ? 1 : 0 }}>{arrow}</span>
    </div>
  );
}

/* ── Row */
function Row({ row, odd, checked, onCheck, onClick }) {
  const [rowHov,    setRowHov]    = useState(false);
  const [tickerHov, setTickerHov] = useState(false);

  const gc    = gradeColor(row.grade);
  const label = gradeLabel(row.grade);

  const sigColor = signalColor(row.grade);

  // null 안전 렌더
  const fmtPrice = (v) => v != null
    ? `$${Number(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    : "—";
  const fmtChg   = (v) => v != null ? `${v > 0 ? "▲" : v < 0 ? "▼" : ""}${Math.abs(v).toFixed(2)}%` : "—";
  const fmtScore = (v) => v != null ? Number(v).toFixed(1) : "—";
  const fmtL     = (v) => v != null ? Number(v).toFixed(0) : "—";

  return (
    <div onMouseEnter={() => setRowHov(true)} onMouseLeave={() => setRowHov(false)}
      style={{
        display: "flex", alignItems: "center",
        padding: "0 16px", height: 46,
        background: checked ? `${C.primary}12` : rowHov ? C.borderHi : odd ? C.bgDeeper : C.bgDeep,
        borderBottom: `1px solid ${C.border}22`,
        cursor: "pointer", transition: "background 0.1s",
        fontFamily: "'Inter', sans-serif",
        minWidth: "fit-content",  // 부모 스크롤 컨테이너 안에서 열 너비 보장
      }}
    >
      {/* 0. 체크박스 */}
      <div style={{ width: 28, flexShrink: 0 }} onClick={e => { e.stopPropagation(); onCheck(); }}>
        <input type="checkbox" checked={checked} onChange={onCheck}
          onClick={e => e.stopPropagation()}
          style={{ accentColor: C.primary, cursor: "pointer" }}
        />
      </div>

      {/* 1. TICKER */}
      <div style={{ width: 74, minWidth: 74, flexShrink: 0, padding: "0 4px" }}
        onMouseEnter={() => setTickerHov(true)}
        onMouseLeave={() => setTickerHov(false)}
        onClick={onClick}
      >
        <span style={{
          fontSize: 13, fontWeight: 850,
          color: tickerHov ? C.yolk : C.primary,
          textDecoration: tickerHov ? "underline" : "none",
          display: "inline-block",
          transform: tickerHov ? "translateX(5px)" : "translateX(0)",
          transition: "all 0.12s ease",
          cursor: "pointer",
        }}>
          {row.ticker}
        </span>
      </div>

      {/* 2. COMPANY */}
      <div style={{ width: 155, minWidth: 155, flexShrink: 0, padding: "0 4px", overflow: "hidden" }}>
        <span style={{ fontSize: 12, color: C.textGray, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", display: "block" }}>
          {row.name ?? "—"}
        </span>
      </div>

      {/* 3. SECTOR — backendName("Information Technology") → 짧은 표시명 */}
      <div style={{ width: 88, minWidth: 88, flexShrink: 0, padding: "0 4px" }}>
        <span style={{ fontSize: 11, color: C.textMuted }}>{sectorDisplay(row.sector)}</span>
      </div>

      {/* 4. PRICE */}
      <div style={{ width: 88, minWidth: 88, flexShrink: 0, padding: "0 4px" }}>
        <span style={{ fontSize: 12, color: C.textGray }}>{fmtPrice(row.price)}</span>
      </div>

      {/* 5. CHG% */}
      <div style={{ width: 68, minWidth: 68, flexShrink: 0, padding: "0 4px" }}>
        <span style={{
          fontSize: 12, fontWeight: 600,
          color: chgColor(row.chg),
        }}>
          {fmtChg(row.chg)}
        </span>
      </div>

      {/* 6~8. L1, L2, L3 */}
      {[row.l1, row.l2, row.l3].map((v, i) => (
        <div key={i} style={{ width: 50, minWidth: 50, flexShrink: 0, padding: "0 4px" }}>
          <div style={{ fontSize: 12, color: C.textGray, marginBottom: 2 }}>{fmtL(v)}</div>
          <MiniBar value={v ?? 0} />
        </div>
      ))}

      {/* 9. SCORE (stat) */}
      <div style={{ width: 62, minWidth: 62, flexShrink: 0, padding: "0 4px" }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: C.textGray, marginBottom: 2 }}>
          {fmtScore(row.score)}
        </div>
        <MiniBar value={row.score ?? 0} />
      </div>

      {/* 10. Q.SIGNAL (퀀트 전용 시그널) */}
      <div style={{ width: 72, minWidth: 72, flexShrink: 0, padding: "0 4px" }}>
        <span style={{
          fontSize: 9, fontWeight: 700, letterSpacing: 0.2,
          color: sigColor, background: `${sigColor}10`,
          border: `1px solid ${sigColor}25`, borderRadius: 3,
          padding: "2px 5px", display: "inline-block", whiteSpace: "nowrap",
          opacity: 0.7,
        }}>
          {row.signal ?? "—"}
        </span>
      </div>

      {/* 11. AI Score (🤖) */}
      <div style={{ width: 48, minWidth: 48, flexShrink: 0, padding: "0 4px", textAlign: "center" }}>
        {row.ai_score != null ? (
          <span style={{ fontSize: 12, fontWeight: 700, color: C.cyan, fontFamily: FONT.mono }}>
            {Number(row.ai_score).toFixed(1)}
          </span>
        ) : (
          <span style={{ fontSize: 10, color: C.border }}>—</span>
        )}
      </div>

      {/* 12. ENSEMBLE (stat+ai) */}
      <div style={{ width: 68, minWidth: 68, flexShrink: 0, padding: "0 4px" }}>
        {row.ensemble != null ? (
          <>
            <div style={{ fontSize: 12, fontWeight: 700, color: C.textPri, marginBottom: 2, fontFamily: FONT.mono }}>
              {Number(row.ensemble).toFixed(1)}
            </div>
            <MiniBar value={row.ensemble ?? 0} color={C.cyan} />
          </>
        ) : (
          <span style={{ fontSize: 10, color: C.border }}>—</span>
        )}
      </div>

      {/* 13. GRADE */}
      <div style={{ width: 48, minWidth: 48, flexShrink: 0, padding: "0 4px" }}>
        <span style={{ fontSize: 15, fontWeight: 800, color: gc }}>
          {row.grade ?? "—"}
        </span>
      </div>

      {/* 14. SIGNAL (퀀트+AI 최종) */}
      <div style={{ width: 80, minWidth: 80, flexShrink: 0, padding: "0 4px" }}>
        {(() => {
          const finalSig = row.ai_signal || row.signal;
          const finalColor = row.ai_signal ? signalColor(row.grade) : sigColor;
          const hasAi = row.ai_signal != null;
          return (
            <span style={{
              fontSize: 10, fontWeight: 700, letterSpacing: 0.2,
              color: finalColor, background: `${finalColor}12`,
              border: `1px solid ${finalColor}35`, borderRadius: 3,
              padding: "3px 6px", display: "inline-block", whiteSpace: "nowrap",
            }}>
              {hasAi && "🤖 "}{finalSig ?? label}
            </span>
          );
        })()}
      </div>
    </div>
  );
}

function MiniBar({ value, color }) {
  return (
    <div style={{ width: "100%", height: 2, background: C.surfaceHi, borderRadius: 1, overflow: "hidden" }}>
      <div style={{ width: `${Math.min(Math.max(value, 0), 100)}%`, height: "100%", background: color || C.gaugebar, borderRadius: 1 }} />
    </div>
  );
}

function Empty() {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", fontSize: 13, color: C.textMuted, fontFamily: "'Inter', sans-serif" }}>
      조건에 맞는 종목이 없습니다.
    </div>
  );
}

function FInput({ value, onChange, placeholder, width }) {
  return (
    <input value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder}
      style={{
        fontFamily: "'Inter', sans-serif", fontSize: 12, width,
        background: "#111", color: "#e8e8e8",
        border: `1px solid ${C.border}`, borderRadius: 3,
        padding: "5px 9px", outline: "none", flexShrink: 0,
      }}
    />
  );
}

function FSelect({ value, onChange, options, highlight }) {
  return (
    <select value={value} onChange={e => onChange(e.target.value)}
      style={{
        fontFamily: "'Inter', sans-serif", fontSize: 12,
        background: "#111", color: highlight ? C.primary : C.textGray,
        border: `1px solid ${highlight ? C.primary : C.border}`,
        borderRadius: 3, padding: "5px 7px", outline: "none", cursor: "pointer", flexShrink: 0,
      }}
    >
      {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
}