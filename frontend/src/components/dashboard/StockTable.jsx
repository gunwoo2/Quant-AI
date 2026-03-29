/**
 * StockTable.jsx — v4.2
 *
 * v4.2 변경:
 *   ✅ 컬럼: Q.Grade, Q.Sig, AI, Ensemble, Grade, Final Signal
 *   ✅ 정렬: Grade/Signal 전용 순서 매핑
 *   ✅ 컬럼 리사이즈 (드래그)
 *   ✅ 티커 클릭 → 새 탭
 *   ✅ AI/Ensemble 데이터 표시
 */
import { useState, useMemo, useEffect, useCallback, useRef } from "react";
import { C, FONT, SECTORS, MOCK_STOCKS, gradeColor, gradeLabel, gradeTextColor, chgColor, signalColor, sectorByBackendName } from "../../styles/tokens";
import { DeleteConfirmModal } from "./Modals";
import api from "../../api";

const GRADES    = ["ALL", "S", "A+", "A", "B+", "B", "C", "D"];
const COUNTRIES = ["ALL", "US", "KR", "JP"];

// 정렬용 숫자 매핑 (높을수록 좋음)
const _GRADE_ORDER  = { "S": 7, "A+": 6, "A": 5, "B+": 4, "B": 3, "C": 2, "D": 1 };
const _SIGNAL_ORDER = {
  "STRONG_BUY": 7, "BUY": 6, "OUTPERFORM": 5, "HOLD": 4,
  "UNDERPERFORM": 3, "SELL": 2, "STRONG_SELL": 1,
};
const _SIGNAL_KO = {
  "STRONG_BUY": "강력매수", "BUY": "매수", "OUTPERFORM": "우수",
  "HOLD": "보유", "UNDERPERFORM": "부진", "SELL": "매도", "STRONG_SELL": "강력매도",
};

const INIT_COLUMNS = [
  { key: "ticker",    label: "TICKER",    w: 74,  min: 60  },
  { key: "name",      label: "COMPANY",   w: 145, min: 80  },
  { key: "sector",    label: "SECTOR",    w: 82,  min: 60  },
  { key: "price",     label: "PRICE",     w: 82,  min: 60  },
  { key: "chg",       label: "CHG%",      w: 64,  min: 50  },
  { key: "l1",        label: "L1",        w: 44,  min: 36, tip: "퀀트 레이팅 (Fundamental)"     },
  { key: "l2",        label: "L2",        w: 44,  min: 36, tip: "텍스트·감성 신호 (NLP/AI)"     },
  { key: "l3",        label: "L3",        w: 44,  min: 36, tip: "시장 신호 (Price/Order Flow)"  },
  { key: "score",     label: "SCORE",     w: 62,  min: 50, tip: "L1+L2+L3 가중합 (Stat)"       },
  { key: "grade",     label: "Q.GRADE",   w: 56,  min: 44, tip: "퀀트 전용 등급"                 },
  { key: "signal",    label: "Q.SIG",     w: 70,  min: 56, tip: "퀀트 전용 시그널 (Stat 기반)"   },
  { key: "ai_score",  label: "AI",        w: 48,  min: 36, tip: "XGBoost AI 예측 점수"           },
  { key: "ensemble",  label: "ENSEMBLE",  w: 68,  min: 50, tip: "Stat×0.7 + AI×0.3"              },
  { key: "ai_grade",  label: "GRADE",     w: 56,  min: 44, tip: "최종 등급 (퀀트+AI)"            },
  { key: "ai_signal", label: "F.SIGNAL",  w: 76,  min: 56, tip: "최종 시그널 (퀀트+AI)"          },
];

function nextSort(dir, clickedKey, sortKey) {
  if (sortKey !== clickedKey) return { key: clickedKey, dir: "desc" };
  if (dir === "desc") return { key: clickedKey, dir: "asc" };
  return { key: null, dir: null };
}

// ═══════════════════════════════════════════════════════
//  Main Component
// ═══════════════════════════════════════════════════════
export default function StockTable({ onSelectTicker }) {
  const [stocks, setStocks] = useState([]);
  const [search, setSearch] = useState("");
  const [searchName, setSearchName] = useState("");
  const [selSector, setSelSector]   = useState("ALL");
  const [selCountry, setSelCountry] = useState("ALL");
  const [selGrade, setSelGrade]     = useState("ALL");
  const [sort, setSort]             = useState({ key: "score", dir: "desc" });
  const [checked, setChecked]       = useState(new Set());
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [columns, setColumns]       = useState(INIT_COLUMNS);

  // ── 데이터 로드
  useEffect(() => {
    api.get("/api/stocks")
      .then(res => { if (Array.isArray(res.data)) setStocks(res.data); })
      .catch(() => setStocks(MOCK_STOCKS || []));
  }, []);

  const reset = () => { setSearch(""); setSearchName(""); setSelSector("ALL"); setSelCountry("ALL"); setSelGrade("ALL"); };

  // ── 필터 + 정렬
  const rows = useMemo(() => {
    let data = [...stocks];
    if (search)      data = data.filter(r => r.ticker?.toLowerCase().includes(search.toLowerCase()));
    if (searchName)  data = data.filter(r => r.name?.toLowerCase().includes(searchName.toLowerCase()));
    if (selSector  !== "ALL") data = data.filter(r => (r.sector_code || sectorByBackendName(r.sector)) === selSector);
    if (selCountry !== "ALL") data = data.filter(r => r.country === selCountry);
    if (selGrade   !== "ALL") data = data.filter(r => r.grade === selGrade);

    if (sort.key && sort.dir) {
      data.sort((a, b) => {
        let av = a[sort.key] ?? null;
        let bv = b[sort.key] ?? null;

        // null → 항상 뒤로
        if (av == null && bv == null) return 0;
        if (av == null) return 1;
        if (bv == null) return -1;

        // 등급: 숫자 매핑
        if (sort.key === "grade" || sort.key === "ai_grade") {
          av = _GRADE_ORDER[av] ?? -1;
          bv = _GRADE_ORDER[bv] ?? -1;
        }
        // 시그널: 숫자 매핑
        else if (sort.key === "signal" || sort.key === "ai_signal") {
          av = _SIGNAL_ORDER[av] ?? -1;
          bv = _SIGNAL_ORDER[bv] ?? -1;
        }
        // 문자열
        else if (typeof av === "string") {
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
  const toggleAll  = () => { setChecked(allChecked ? new Set() : new Set(allIds)); };
  const toggleOne  = (id) => {
    setChecked(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
  };

  const handleSort = (key) => {
    setSort(prev => nextSort(prev.dir, key, prev.key));
  };

  // ── 컬럼 리사이즈
  const handleResize = useCallback((idx, delta) => {
    setColumns(prev => {
      const next = [...prev];
      next[idx] = { ...next[idx], w: Math.max(next[idx].min || 36, next[idx].w + delta) };
      return next;
    });
  }, []);

  // ── 티커 클릭 → 새 탭
  const handleTicker = (ticker) => {
    window.open(`/stock/${ticker}/summary`, "_blank", "noopener");
  };

  return (
    <div style={{ fontFamily: FONT.sans, color: C.textPri }}>

      {/* ── 필터 바 ── */}
      <div style={{ display: "flex", gap: 10, alignItems: "center", padding: "12px 16px",
        background: C.bgDeeper, borderRadius: 10, marginBottom: 12, flexWrap: "wrap" }}>
        <FInput value={search}     onChange={setSearch}     placeholder="Ticker" width={110} />
        <FInput value={searchName} onChange={setSearchName} placeholder="Company Name" width={150} />
        <FSelect value={selCountry} onChange={setSelCountry}
          options={COUNTRIES.map(c => ({ value: c, label: c === "ALL" ? "All Countries" : c }))} />
        <FSelect value={selSector} onChange={setSelSector}
          options={[{ value: "ALL", label: "All Sectors" }, ...SECTORS.map(s => ({ value: s.key, label: s.en }))]} />
        <FSelect value={selGrade} onChange={setSelGrade}
          options={GRADES.map(g => ({ value: g, label: g === "ALL" ? "All Ratings" : g }))} />

        <button onClick={reset} style={{
          fontFamily: "'Inter', sans-serif", fontSize: 12,
          color: C.pink, background: "none",
          border: `1px solid ${C.pink}44`, borderRadius: 4,
          padding: "4px 12px", cursor: "pointer",
        }}>Reset</button>
      </div>

      {/* ── 테이블 ── */}
      <div style={{ overflowX: "auto" }}>
        {/* 헤더 */}
        <div style={{ display: "flex", alignItems: "center",
          padding: "0 16px", height: 36,
          background: C.bgDeeper, borderBottom: `1px solid ${C.border}`,
          position: "sticky", top: 0, zIndex: 2 }}>
          <div style={{ width: 28, flexShrink: 0 }}>
            <input type="checkbox" checked={allChecked} onChange={toggleAll}
              style={{ accentColor: C.primary, cursor: "pointer" }} />
          </div>
          {columns.map((col, idx) => (
            <ColHead key={col.key} col={col} sort={sort}
              onSort={() => handleSort(col.key)}
              onResize={(delta) => handleResize(idx, delta)} />
          ))}
        </div>

        {/* 바디 */}
        <div style={{ maxHeight: "calc(100vh - 220px)", overflowY: "auto" }}>
          {rows.length === 0 ? (
            <div style={{ textAlign: "center", color: C.textMuted, padding: 40, fontSize: 13 }}>
              No matching stocks
            </div>
          ) : rows.map((row, i) => (
            <Row key={row.ticker} row={row} odd={i % 2 === 1}
              checked={checked.has(row.ticker)}
              onCheck={() => toggleOne(row.ticker)}
              onClick={() => handleTicker(row.ticker)}
              columns={columns} />
          ))}
        </div>
      </div>
    </div>
  );
}


// ═══════════════════════════════════════════════════════
//  Row
// ═══════════════════════════════════════════════════════
function Row({ row, odd, checked, onCheck, onClick, columns }) {
  const gc    = gradeColor(row.grade);
  const sigColor = signalColor(row.grade);

  const fmtPrice = (v) => v != null
    ? `$${Number(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    : "—";
  const fmtChg   = (v) => v != null ? `${v > 0 ? "▲" : v < 0 ? "▼" : ""}${Math.abs(v).toFixed(2)}%` : "—";
  const fmtScore = (v) => v != null ? Number(v).toFixed(1) : "—";

  const renderCell = (col) => {
    const w = col.w;
    const base = { width: w, minWidth: w, flexShrink: 0, padding: "0 4px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" };

    switch(col.key) {
      case "ticker":
        return (
          <div key={col.key} style={{ ...base, cursor: "pointer" }} onClick={(e) => { e.stopPropagation(); onClick(); }}>
            <span style={{ fontSize: 13, fontWeight: 700, color: C.primary, fontFamily: FONT.mono }}>{row.ticker}</span>
          </div>
        );
      case "name":
        return (
          <div key={col.key} style={{ ...base }}>
            <span style={{ fontSize: 12, color: C.textGray }}>{row.name || "—"}</span>
          </div>
        );
      case "sector":
        return (
          <div key={col.key} style={{ ...base }}>
            <span style={{ fontSize: 11, color: C.textMuted }}>{row.sector || "—"}</span>
          </div>
        );
      case "price":
        return (
          <div key={col.key} style={{ ...base }}>
            <span style={{ fontSize: 12, fontWeight: 600, color: C.textPri, fontFamily: FONT.mono }}>{fmtPrice(row.price)}</span>
          </div>
        );
      case "chg": {
        const cc = chgColor(row.chg);
        return (
          <div key={col.key} style={{ ...base }}>
            <span style={{ fontSize: 11, fontWeight: 700, color: cc, fontFamily: FONT.mono }}>{fmtChg(row.chg)}</span>
          </div>
        );
      }
      case "l1": case "l2": case "l3":
        return (
          <div key={col.key} style={{ ...base, textAlign: "center" }}>
            <span style={{ fontSize: 12, fontWeight: 600, color: C.textGray, fontFamily: FONT.mono }}>{fmtScore(row[col.key])}</span>
          </div>
        );
      case "score":
        return (
          <div key={col.key} style={{ ...base }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: C.textGray, fontFamily: FONT.mono }}>{fmtScore(row.score)}</div>
            <MiniBar value={row.score ?? 0} />
          </div>
        );
      case "grade": {
        const g = row.grade ?? "—";
        return (
          <div key={col.key} style={{ ...base, textAlign: "center" }}>
            <span style={{ fontSize: 14, fontWeight: 800, color: gc }}>{g}</span>
          </div>
        );
      }
      case "signal": {
        const sig = row.signal;
        const ko = _SIGNAL_KO[sig] || sig || "—";
        return (
          <div key={col.key} style={{ ...base }}>
            <span style={{
              fontSize: 9, fontWeight: 700, letterSpacing: 0.2,
              color: sigColor, background: `${sigColor}10`,
              border: `1px solid ${sigColor}25`, borderRadius: 3,
              padding: "2px 5px", display: "inline-block", whiteSpace: "nowrap",
              opacity: 0.8,
            }}>{ko}</span>
          </div>
        );
      }
      case "ai_score":
        return (
          <div key={col.key} style={{ ...base, textAlign: "center" }}>
            {row.ai_score != null ? (
              <span style={{ fontSize: 12, fontWeight: 700, color: C.cyan, fontFamily: FONT.mono }}>{Number(row.ai_score).toFixed(1)}</span>
            ) : <span style={{ fontSize: 10, color: C.border }}>—</span>}
          </div>
        );
      case "ensemble":
        return (
          <div key={col.key} style={{ ...base }}>
            {row.ensemble != null ? (
              <>
                <div style={{ fontSize: 12, fontWeight: 700, color: C.textPri, fontFamily: FONT.mono }}>{Number(row.ensemble).toFixed(1)}</div>
                <MiniBar value={row.ensemble ?? 0} color={C.cyan} />
              </>
            ) : <span style={{ fontSize: 10, color: C.border }}>—</span>}
          </div>
        );
      case "ai_grade": {
        // ai_grade = grade (현재 동일, 추후 ensemble 기반 분리)
        const g = row.grade ?? "—";
        return (
          <div key={col.key} style={{ ...base, textAlign: "center" }}>
            <span style={{ fontSize: 14, fontWeight: 800, color: gc }}>{g}</span>
          </div>
        );
      }
      case "ai_signal": {
        const finalSig = row.ai_signal || row.signal;
        const ko = _SIGNAL_KO[finalSig] || finalSig || "—";
        const finalColor = row.ai_signal ? C.cyan : sigColor;
        const hasAi = row.ai_signal != null;
        return (
          <div key={col.key} style={{ ...base }}>
            <span style={{
              fontSize: 9, fontWeight: 700, letterSpacing: 0.2,
              color: finalColor, background: `${finalColor}12`,
              border: `1px solid ${finalColor}35`, borderRadius: 3,
              padding: "2px 5px", display: "inline-block", whiteSpace: "nowrap",
            }}>{hasAi ? "🤖 " : ""}{ko}</span>
          </div>
        );
      }
      default:
        return <div key={col.key} style={{ ...base }}>—</div>;
    }
  };

  return (
    <div onClick={onClick} style={{
      display: "flex", alignItems: "center", padding: "0 16px",
      height: 48, cursor: "pointer",
      background: checked ? `${C.primary}08` : odd ? C.bgDeeper : "transparent",
      borderBottom: `1px solid ${C.border}22`,
      transition: "background 0.15s",
    }}
      onMouseEnter={e => { if (!checked) e.currentTarget.style.background = `${C.primary}06`; }}
      onMouseLeave={e => { if (!checked) e.currentTarget.style.background = odd ? C.bgDeeper : "transparent"; }}
    >
      <div style={{ width: 28, flexShrink: 0 }} onClick={e => e.stopPropagation()}>
        <input type="checkbox" checked={checked} onChange={onCheck}
          style={{ accentColor: C.primary, cursor: "pointer" }} />
      </div>
      {columns.map(col => renderCell(col))}
    </div>
  );
}


// ═══════════════════════════════════════════════════════
//  ColHead — 정렬 + 리사이즈 핸들
// ═══════════════════════════════════════════════════════
function ColHead({ col, sort, onSort, onResize }) {
  const [hov, setHov] = useState(false);
  const isActive = sort.key === col.key && sort.dir;
  const arrow = isActive ? (sort.dir === "desc" ? " ▼" : " ▲") : (hov ? " ⇅" : "");

  const dragRef = useRef(null);
  const startResize = (e) => {
    e.preventDefault(); e.stopPropagation();
    const startX = e.clientX;
    const onMove = (ev) => { onResize(ev.clientX - startX); };
    const onUp = () => { document.removeEventListener("mousemove", onMove); document.removeEventListener("mouseup", onUp); };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  };

  return (
    <div style={{
      width: col.w, minWidth: col.w, flexShrink: 0,
      position: "relative", display: "flex", alignItems: "center",
    }}>
      <div onClick={onSort}
        onMouseEnter={() => setHov(true)} onMouseLeave={() => setHov(false)}
        title={col.tip || ""}
        style={{
          fontSize: 10, fontWeight: 700, color: isActive ? C.primary : C.textMuted,
          cursor: "pointer", userSelect: "none", padding: "0 4px",
          letterSpacing: 0.5, fontFamily: FONT.mono,
          whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
          flex: 1,
        }}>
        {col.label}{arrow}
      </div>
      {/* 리사이즈 핸들 */}
      <div ref={dragRef} onMouseDown={startResize}
        style={{
          width: 4, height: "100%", cursor: "col-resize",
          position: "absolute", right: 0, top: 0,
          background: hov ? C.primary + "33" : "transparent",
        }} />
    </div>
  );
}


// ═══════════════════════════════════════════════════════
//  MiniBar
// ═══════════════════════════════════════════════════════
function MiniBar({ value, color }) {
  return (
    <div style={{ width: "100%", height: 2, background: C.surfaceHi, borderRadius: 1, overflow: "hidden" }}>
      <div style={{ width: `${Math.min(Math.max(value, 0), 100)}%`, height: "100%", background: color || C.gaugebar, borderRadius: 1 }} />
    </div>
  );
}


// ═══════════════════════════════════════════════════════
//  필터 컴포넌트
// ═══════════════════════════════════════════════════════
function FInput({ value, onChange, placeholder, width }) {
  return (
    <input value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder}
      style={{
        width: width || 120, padding: "5px 10px", fontSize: 12,
        background: C.bgDark, border: `1px solid ${C.border}`,
        borderRadius: 6, color: C.textPri, fontFamily: FONT.mono,
        outline: "none",
      }} />
  );
}

function FSelect({ value, onChange, options }) {
  return (
    <select value={value} onChange={e => onChange(e.target.value)}
      style={{
        padding: "5px 8px", fontSize: 12,
        background: C.bgDark, border: `1px solid ${C.border}`,
        borderRadius: 6, color: C.textPri, fontFamily: FONT.sans,
        outline: "none", cursor: "pointer",
      }}>
      {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
}