/**
 * StockTable.jsx — v3 (필드 순서 변경)
 *
 * 수정:
 * 1. 필드 순서 재배치: Ticker -> Name -> Sector -> Price -> Chg% -> L1 -> L2 -> L3 -> Score -> Grade -> Signal
 * 2. 기존의 모든 스타일, 로직, 압축된 컬럼 너비 유지
 */

import { useState, useMemo, useEffect } from "react";
import { C, SECTORS, MOCK_STOCKS, gradeColor, gradeLabel } from "../../styles/tokens";
import { DeleteConfirmModal } from "./Modals";

const GRADES    = ["ALL", "S", "A+", "A", "B+", "B", "C", "D"];
const COUNTRIES = ["ALL", "US", "KR", "JP"];

// ── 컬럼 순서 및 너비 재배치 (요청하신 순서대로)
const COLUMNS = [
  { key: "ticker", label: "TICKER",   width: 84  },
  { key: "name",   label: "COMPANY", width: 210 },
  { key: "sector", label: "SECTOR",   width: 110 },
  { key: "price",  label: "PRICE",   width: 105 },
  { key: "chg",    label: "CHG%",    width: 82  },
  { key: "l1",     label: "L1",      width: 60, tip: "퀀트 레이팅 (Fundamental)"      },
  { key: "l2",     label: "L2",      width: 60, tip: "텍스트·감성 신호 (NLP/AI)"      },
  { key: "l3",     label: "L3",      width: 60, tip: "시장 신호 (Price/Order Flow)"  },
  { key: "score",  label: "SCORE",   width: 120 },
  { key: "grade",  label: "GRADE",   width: 56  },
  { key: "signal", label: "SIGNAL",  width: 120 },
];

const sectorEn = (key) => SECTORS.find(s => s.key === key)?.en ?? key;

function nextSort(dir, clickedKey, sortKey) {
  if (sortKey !== clickedKey) return { key: clickedKey, dir: "desc" };
  if (dir === "desc")          return { key: clickedKey, dir: "asc"  };
  return { key: null, dir: null };
}

export default function StockTable({ onTickerClick, filterSector, onResetSector }) {
  const [search,     setSearch]     = useState("");
  const [searchName, setSearchName] = useState("");
  const [selSector,  setSelSector]  = useState("ALL");
  const [selCountry, setSelCountry] = useState("ALL");
  const [selGrade,   setSelGrade]   = useState("ALL");
  const [sort,       setSort]       = useState({ key: "score", dir: "desc" });
  const [checked,    setChecked]    = useState(new Set());
  const [showDelete, setShowDelete] = useState(false);

  useEffect(() => {
    setSelSector(filterSector ?? "ALL");
  }, [filterSector]);

  const rows = useMemo(() => {
    let data = [...MOCK_STOCKS];
    if (search)               data = data.filter(s => s.ticker.includes(search.toUpperCase()));
    if (searchName)           data = data.filter(s => s.name.toLowerCase().includes(searchName.toLowerCase()));
    if (selSector  !== "ALL") data = data.filter(s => s.sector  === selSector);
    if (selCountry !== "ALL") data = data.filter(s => s.country === selCountry);
    if (selGrade   !== "ALL") data = data.filter(s => s.grade   === selGrade);
    if (sort.key && sort.dir) {
      data.sort((a, b) => {
        let av = a[sort.key], bv = b[sort.key];
        if (typeof av === "string") { av = av.toLowerCase(); bv = bv.toLowerCase(); }
        if (av < bv) return sort.dir === "desc" ?  1 : -1;
        if (av > bv) return sort.dir === "desc" ? -1 :  1;
        return 0;
      });
    }
    return data;
  }, [search, searchName, selSector, selCountry, selGrade, sort]);

  const allIds     = rows.map(r => r.ticker);
  const allChecked = allIds.length > 0 && allIds.every(id => checked.has(id));
  const someChecked = allIds.some(id => checked.has(id));
  const toggleAll  = () => setChecked(allChecked ? new Set() : new Set(allIds));
  const toggleOne  = (t) => {
    const n = new Set(checked);
    n.has(t) ? n.delete(t) : n.add(t);
    setChecked(n);
  };

  const reset = () => {
    setSearch(""); setSearchName("");
    setSelSector("ALL"); setSelCountry("ALL"); setSelGrade("ALL");
    onResetSector?.();
  };

  const handleSort = (key) => {
    setSort(prev => nextSort(prev.dir, key, prev.key));
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden", fontFamily: "'Inter', sans-serif" }}>

      {/* ── 필터 바 */}
      <div style={{
        padding: "9px 16px",
        background: "#000000",
        borderBottom: `1px solid ${C.border}`,
        display: "flex", alignItems: "center",
        gap: 7, flexWrap: "nowrap", flexShrink: 0,
        overflowX: "auto",
      }}>
        <FInput value={search}     onChange={setSearch}     placeholder="Ticker"     width={80}  />
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

        <div style={{ flex: 1, minWidth: 8 }} />

        {checked.size > 0 && (
          <button onClick={() => setShowDelete(true)} style={{
            fontFamily: "'Inter', sans-serif", fontSize: 12, fontWeight: 700,
            color: "#fff", background: C.scarlet,
            border: "none", borderRadius: 3,
            padding: "6px 13px", cursor: "pointer",
            whiteSpace: "nowrap", flexShrink: 0,
          }}>
            🗑 {checked.size}개 삭제
          </button>
        )}

        <div style={{
          fontFamily: "'Inter', sans-serif", fontSize: 10,
          color: C.textMuted, textAlign: "right", lineHeight: 1.6,
          flexShrink: 0,
        }}>
          <div style={{ color: C.textGray }}>{rows.length} / {MOCK_STOCKS.length} 종목</div>
          <div>Last Batch : '26.03.09 02:14</div>
        </div>
      </div>

      {/* ── 테이블 헤더 */}
      <div style={{
        display: "flex", alignItems: "center",
        padding: "0 16px",
        background: "#000000",
        borderBottom: `1px solid ${C.border}`,
        height: 34, flexShrink: 0,
      }}>
        <div style={{ width: 28, flexShrink: 0 }}>
          <input type="checkbox" checked={allChecked}
            ref={el => el && (el.indeterminate = !allChecked && someChecked)}
            onChange={toggleAll}
            style={{ accentColor: C.primary, cursor: "pointer" }}
          />
        </div>
        {COLUMNS.map(col => (
          <ColHead key={col.key} col={col} sort={sort} onSort={() => handleSort(col.key)} />
        ))}
      </div>

      {/* ── 테이블 바디 */}
      <div style={{ flex: 1, overflowY: "auto", overflowX: "hidden" }}>
        {rows.length === 0
          ? <Empty />
          : rows.map((row, i) => (
            <Row key={row.ticker} row={row} odd={i % 2 !== 0}
              checked={checked.has(row.ticker)}
              onCheck={() => toggleOne(row.ticker)}
              onClick={() => onTickerClick?.(row.ticker)}
            />
          ))
        }
      </div>

      {showDelete && (
        <DeleteConfirmModal tickers={[...checked]}
          onClose={() => setShowDelete(false)}
          onConfirm={() => { setChecked(new Set()); setShowDelete(false); }}
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

/* ── Row (요청하신 필드 순서로 JSX 재배치) */
function Row({ row, odd, checked, onCheck, onClick }) {
  const [rowHov,    setRowHov]    = useState(false);
  const [tickerHov, setTickerHov] = useState(false);

  const gc    = gradeColor(row.grade);
  const label = gradeLabel(row.grade);

  const sigColor =
    row.grade === "S"                         ? C.cyan :
    row.grade === "A"  || row.grade === "A+"  ? C.yolk :
    row.grade === "B+" || row.grade === "B"   ? C.primary :
    row.grade === "C"                         ? C.scarlet : 
    row.grade === 'd'                         ? C.red : "#FF0033";

  return (
    <div onMouseEnter={() => setRowHov(true)} onMouseLeave={() => setRowHov(false)}
      style={{
        display: "flex", alignItems: "center",
        padding: "0 16px", height: 46,
        background: checked ? `${C.primary}12` : rowHov ? "#333333" : odd ? "#030303" : C.bgDeep,
        borderBottom: `1px solid ${C.border}22`,
        cursor: "pointer", transition: "background 0.1s",
        fontFamily: "'Inter', sans-serif",
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
      <div style={{ width: 84, minWidth: 84, flexShrink: 0, padding: "0 4px" }}
        onMouseEnter={() => setTickerHov(true)}
        onMouseLeave={() => setTickerHov(false)}
        onClick={onClick}
      >
        <span style={{
          fontFamily: "'Inter', sans-serif",
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

      {/* 2. COMPANY (NAME) */}
      <div style={{ width: 190, minWidth: 210, flexShrink: 0, padding: "0 4px", overflow: "hidden" }}>
        <span style={{ fontSize: 12, color: C.textGray, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", display: "block" }}>
          {row.name}
        </span>
      </div>

      {/* 3. SECTOR */}
      <div style={{ width: 110, minWidth: 110, flexShrink: 0, padding: "0 4px" }}>
        <span style={{ fontSize: 11, color: C.textMuted }}>{sectorEn(row.sector)}</span>
      </div>

      {/* 4. PRICE */}
      <div style={{ width: 105, minWidth: 105, flexShrink: 0, padding: "0 4px" }}>
        <span style={{ fontFamily: "'Inter', sans-serif", fontSize: 12, color: C.textGray }}>
          ${row.price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </span>
      </div>

      {/* 5. CHG% */}
      <div style={{ width: 82, minWidth: 82, flexShrink: 0, padding: "0 4px" }}>
        <span style={{
          fontFamily: "'Inter', sans-serif", fontSize: 12, fontWeight: 600,
          color: row.chg > 0 ? C.cyan : row.chg < 0 ? C.scarlet : C.textMuted,
        }}>
          {row.chg > 0 ? "▲" : row.chg < 0 ? "▼" : ""}
          {Math.abs(row.chg).toFixed(2)}%
        </span>
      </div>

      {/* 6~8. L1, L2, L3 */}
      {[row.l1, row.l2, row.l3].map((v, i) => (
        <div key={i} style={{ width: 60, minWidth: 60, flexShrink: 0, padding: "0 4px" }}>
          <div style={{ fontFamily: "'Inter', sans-serif", fontSize: 12, color: C.textGray, marginBottom: 2 }}>{v}</div>
          <MiniBar value={v} />
        </div>
      ))}

      {/* 9. SCORE */}
      <div style={{ width: 120, minWidth: 120, flexShrink: 0, padding: "0 4px" }}>
        <div style={{ fontFamily: "'Inter', sans-serif", fontSize: 12, fontWeight: 700, color: C.textGray, marginBottom: 2 }}>
          {row.score.toFixed(1)}
        </div>
        <MiniBar value={row.score} />
      </div>

      {/* 10. GRADE */}
      <div style={{ width: 56, minWidth: 56, flexShrink: 0, padding: "0 4px" }}>
        <span style={{ fontFamily: "'Inter', sans-serif", fontSize: 15, fontWeight: 800, color: gc }}>
          {row.grade}
        </span>
      </div>

      {/* 11. SIGNAL */}
      <div style={{ width: 120, minWidth: 120, flexShrink: 0, padding: "0 4px" }}>
        <span style={{
          fontSize: 10, fontWeight: 700, letterSpacing: 0.2,
          color: sigColor, background: `${sigColor}12`,
          border: `1px solid ${sigColor}35`, borderRadius: 3,
          padding: "3px 7px", display: "inline-block", whiteSpace: "nowrap",
        }}>
          {label}
        </span>
      </div>
    </div>
  );
}

function MiniBar({ value }) {
  return (
    <div style={{ width: "100%", height: 2, background: "#2a2a2a", borderRadius: 1, overflow: "hidden" }}>
      <div style={{ width: `${value}%`, height: "100%", background: C.gaugebar, borderRadius: 1 }} />
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