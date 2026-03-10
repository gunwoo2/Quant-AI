/**
 * StockTable.jsx
 *
 * 수정 사항
 *   1. 글자 크기 전체 업
 *   2. 스코어 바 색상 → #e8e8e8 (숫자 기반 동일 색상)
 *   3. 폰트 → Inter
 *   4. 정렬: 오름차순 → 내림차순 → 정렬해제 3단계
 */

import { useState, useMemo, useEffect } from "react";
import { C, FONT, SECTORS, MOCK_STOCKS, gradeColor, gradeLabel } from "../../styles/tokens";
import { AddTickerModal, DeleteConfirmModal } from "./Modals";

const GRADES    = ["ALL", "S", "A+", "A", "B+", "B", "C", "D"];
const COUNTRIES = ["ALL", "US", "KR", "JP"];

const COLUMNS = [
  { key: "ticker", label: "TICKER",  width: 100 },
  { key: "name",   label: "COMPANY", width: 220 },
  { key: "sector", label: "SECTOR",  width: 150 },
  { key: "grade",  label: "GRADE",   width: 72  },
  { key: "score",  label: "SCORE",   width: 130 },
  { key: "price",  label: "PRICE",   width: 110 },
  { key: "chg",    label: "CHG%",    width: 90  },
  { key: "l1",     label: "L1",      width: 72, tip: "퀀트 레이팅 (Fundamental)"    },
  { key: "l2",     label: "L2",      width: 72, tip: "텍스트·감성 신호 (NLP/AI)"    },
  { key: "l3",     label: "L3",      width: 72, tip: "시장 신호 (Price/Order Flow)" },
  { key: "signal", label: "SIGNAL",  width: 140 },
];

const sectorEn = (key) => SECTORS.find(s => s.key === key)?.en ?? key;

// 정렬 3단계: null → desc → asc → null
function nextSort(current, clickedKey, sortKey) {
  if (sortKey !== clickedKey) return { key: clickedKey, dir: "desc" };
  if (current === "desc")     return { key: clickedKey, dir: "asc"  };
  return { key: null, dir: null };  // 3번째 클릭 → 정렬 해제
}

export default function StockTable({ onTickerClick, filterSector }) {
  const [search,     setSearch]     = useState("");
  const [searchName, setSearchName] = useState("");
  const [selSector,  setSelSector]  = useState("ALL");
  const [selCountry, setSelCountry] = useState("ALL");
  const [selGrade,   setSelGrade]   = useState("ALL");

  // 사이드바 섹터 선택 → 필터 select 즉시 반영
  useEffect(() => {
    setSelSector(filterSector ?? "ALL");
  }, [filterSector]);

  // 정렬: { key: string|null, dir: "asc"|"desc"|null }
  const [sort, setSort] = useState({ key: "score", dir: "desc" });

  const [checked,    setChecked]    = useState(new Set());
  const [showAdd,    setShowAdd]    = useState(false);
  const [showDelete, setShowDelete] = useState(false);

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
        if (av < bv) return sort.dir === "desc" ? 1  : -1;
        if (av > bv) return sort.dir === "desc" ? -1 : 1;
        return 0;
      });
    }
    return data;
  }, [search, searchName, selSector, selCountry, selGrade, sort]);

  const allIds      = rows.map(r => r.ticker);
  const allChecked  = allIds.length > 0 && allIds.every(id => checked.has(id));
  const someChecked = allIds.some(id => checked.has(id));
  const toggleAll   = () => setChecked(allChecked ? new Set() : new Set(allIds));
  const toggleOne   = (t) => { const n = new Set(checked); n.has(t) ? n.delete(t) : n.add(t); setChecked(n); };

  const reset = () => {
    setSearch(""); setSearchName("");
    setSelSector("ALL"); setSelCountry("ALL"); setSelGrade("ALL");
  };

  const handleSort = (key) => {
    setSort(prev => {
      const next = nextSort(prev.dir, key, prev.key);
      return next;
    });
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden", fontFamily: "'Inter', sans-serif" }}>

      {/* ── 필터 바 */}
      <div style={{
        padding: "10px 18px",
        background: "#0c0c0c",
        borderBottom: `1px solid ${C.border}`,
        display: "flex", alignItems: "center",
        gap: 8, flexWrap: "wrap", flexShrink: 0,
      }}>
        <FInput value={search}     onChange={setSearch}     placeholder="Ticker"       width={95}  />
        <FInput value={searchName} onChange={setSearchName} placeholder="Company Name" width={175} />
        <FSelect value={selCountry} onChange={setSelCountry}
          options={COUNTRIES.map(c => ({ value: c, label: c === "ALL" ? "All Countries" : c }))} />
        <FSelect value={selSector}  onChange={setSelSector}
          options={[{ value: "ALL", label: "All Sectors" }, ...SECTORS.map(s => ({ value: s.key, label: s.en }))]}
          highlight={selSector !== "ALL"} />
        <FSelect value={selGrade}   onChange={setSelGrade}
          options={GRADES.map(g => ({ value: g, label: g === "ALL" ? "All Ratings" : g }))} />

        <button onClick={reset} style={{
          fontFamily: "'Inter', sans-serif", fontSize: 12,
          color: C.primary, background: "none",
          border: `1px solid ${C.primary}55`,
          borderRadius: 3, padding: "5px 11px", cursor: "pointer",
        }}>
          Reset
        </button>

        <div style={{ flex: 1 }} />

        {checked.size > 0 && (
          <button onClick={() => setShowDelete(true)} style={{
            fontFamily: "'Inter', sans-serif", fontSize: 12, fontWeight: 600,
            color: "#fff", background: C.scarlet,
            border: "none", borderRadius: 3,
            padding: "5px 12px", cursor: "pointer",
          }}>
            ✕ {checked.size}개 삭제
          </button>
        )}

        <div style={{
          fontFamily: "'IBM Plex Mono', monospace", fontSize: 10,
          color: C.textMuted, textAlign: "right", lineHeight: 1.7,
        }}>
          <div style={{ color: C.textGray }}>{rows.length} / {MOCK_STOCKS.length} 종목</div>
          <div>배치 03-09 02:14</div>
        </div>

        <button onClick={() => setShowAdd(true)} style={{
          fontFamily: "'Inter', sans-serif", fontSize: 12, fontWeight: 600,
          color: "#fff", background: C.primary,
          border: "none", borderRadius: 3,
          padding: "6px 14px", cursor: "pointer",
          letterSpacing: 0.3, whiteSpace: "nowrap",
        }}>
          + ADD TICKER
        </button>
      </div>

      {/* ── 테이블 헤더 */}
      <div style={{
        display: "flex", alignItems: "center",
        padding: "0 18px",
        background: "#0a0a0a",
        borderBottom: `1px solid ${C.border}`,
        height: 36, flexShrink: 0,
      }}>
        <div style={{ width: 30, flexShrink: 0 }}>
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
      <div style={{ flex: 1, overflowY: "auto" }}>
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

      {showAdd && (
        <AddTickerModal onClose={() => setShowAdd(false)}
          onAdd={t => { console.log("추가:", t); setShowAdd(false); }} />
      )}
      {showDelete && (
        <DeleteConfirmModal tickers={[...checked]}
          onClose={() => setShowDelete(false)}
          onConfirm={() => { setChecked(new Set()); setShowDelete(false); }} />
      )}
    </div>
  );
}

/* ── ColHead ───────────────────────────────────────── */
function ColHead({ col, sort, onSort }) {
  const [hov, setHov] = useState(false);
  const isActive = sort.key === col.key && sort.dir;

  const arrow = isActive
    ? (sort.dir === "desc" ? " ▼" : " ▲")
    : (hov ? " ⇅" : "");

  return (
    <div
      onClick={onSort}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      title={col.tip}
      style={{
        width: col.width, minWidth: col.width, flexShrink: 0,
        fontFamily: "'Inter', sans-serif",
        fontSize: 11, fontWeight: 500,
        letterSpacing: 0.3,
        color: isActive ? C.primary : hov ? C.textGray : C.textMuted,
        cursor: "pointer", userSelect: "none",
        display: "flex", alignItems: "center",
        padding: "0 6px",
      }}
    >
      {col.label}
      <span style={{ fontSize: 8, marginLeft: 2, opacity: hov || isActive ? 1 : 0 }}>
        {arrow}
      </span>
    </div>
  );
}

/* ── Row ───────────────────────────────────────────── */
function Row({ row, odd, checked, onCheck, onClick }) {
  const [rowHov,    setRowHov]    = useState(false);
  const [tickerHov, setTickerHov] = useState(false);

  const gc    = gradeColor(row.grade);
  const label = gradeLabel(row.grade);

  const sigColor =
    row.grade === "S" || row.grade === "A+" ? C.cyan    :
    row.grade === "A"                       ? "#66ddee" :
    row.grade === "B+"                      ? C.golden  :
    row.grade === "B"                       ? C.primary :
    row.grade === "C"                       ? C.scarlet : "#7a0000";

  return (
    <div
      onMouseEnter={() => setRowHov(true)}
      onMouseLeave={() => setRowHov(false)}
      style={{
        display: "flex", alignItems: "center",
        padding: "0 18px", height: 48,
        background: checked ? `${C.primary}12` : rowHov ? "#191919" : odd ? "#0d0d0d" : C.bgDark,
        borderBottom: `1px solid ${C.border}22`,
        cursor: "pointer", transition: "background 0.1s",
        fontFamily: "'Inter', sans-serif",
      }}
    >
      {/* 체크박스 */}
      <div style={{ width: 30, flexShrink: 0 }} onClick={e => { e.stopPropagation(); onCheck(); }}>
        <input type="checkbox" checked={checked} onChange={onCheck}
          onClick={e => e.stopPropagation()}
          style={{ accentColor: C.primary, cursor: "pointer" }}
        />
      </div>

      {/* TICKER */}
      <div style={{ width: 100, minWidth: 100, flexShrink: 0, padding: "0 6px" }}
        onMouseEnter={() => setTickerHov(true)}
        onMouseLeave={() => setTickerHov(false)}
        onClick={onClick}
      >
        <span style={{
          fontFamily: "'IBM Plex Mono', monospace",
          fontSize: 14, fontWeight: 700,
          color: tickerHov ? C.yolk : C.primary,
          textDecoration: tickerHov ? "underline" : "none",
          display: "inline-block",
          transform: tickerHov ? "translateX(3px)" : "translateX(0)",
          transition: "all 0.14s ease",
          cursor: "pointer",
        }}>
          {row.ticker}
        </span>
      </div>

      {/* COMPANY */}
      <div style={{ width: 220, minWidth: 220, flexShrink: 0, padding: "0 6px", overflow: "hidden" }}>
        <span style={{
          fontSize: 13, color: C.textGray,
          whiteSpace: "nowrap", overflow: "hidden",
          textOverflow: "ellipsis", display: "block",
        }}>
          {row.name}
        </span>
      </div>

      {/* SECTOR */}
      <div style={{ width: 150, minWidth: 150, flexShrink: 0, padding: "0 6px" }}>
        <span style={{ fontSize: 12, color: C.textMuted }}>
          {sectorEn(row.sector)}
        </span>
      </div>

      {/* GRADE */}
      <div style={{ width: 72, minWidth: 72, flexShrink: 0, padding: "0 6px" }}>
        <span style={{
          fontFamily: "'IBM Plex Mono', monospace",
          fontSize: 16, fontWeight: 800, color: gc,
        }}>
          {row.grade}
        </span>
      </div>

      {/* SCORE */}
      <div style={{ width: 130, minWidth: 130, flexShrink: 0, padding: "0 6px" }}>
        <div style={{
          fontFamily: "'sans-serif', monospace",
          fontSize: 14, fontWeight: 700,
          color: "#e8e8e8ff", marginBottom: 3,
        }}>
          {row.score.toFixed(1)}
        </div>
        <MiniBar value={row.score} />
      </div>

      {/* PRICE */}
      <div style={{ width: 110, minWidth: 110, flexShrink: 0, padding: "0 6px" }}>
        <span style={{
          fontFamily: "'IBM Plex Mono', monospace",
          fontSize: 13, color: "#e8e8e8",
        }}>
          ${row.price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </span>
      </div>

      {/* CHG% */}
      <div style={{ width: 90, minWidth: 90, flexShrink: 0, padding: "0 6px" }}>
        <span style={{
          fontFamily: "'IBM Plex Mono', monospace",
          fontSize: 13, fontWeight: 600,
          color: row.chg > 0 ? C.cyan : row.chg < 0 ? C.red : C.textMuted,
        }}>
          {row.chg > 0 ? "▲" : row.chg < 0 ? "▼" : ""}
          {Math.abs(row.chg).toFixed(2)}%
        </span>
      </div>

      {/* L1 L2 L3 — 숫자 + 흰색 게이지 바 */}
      {[row.l1, row.l2, row.l3].map((v, i) => (
        <div key={i} style={{ width: 72, minWidth: 72, flexShrink: 0, padding: "0 6px" }}>
          <div style={{
            fontFamily: "'IBM Plex Mono', monospace",
            fontSize: 13, color: "#e8e8e8", marginBottom: 3,
          }}>
            {v}
          </div>
          <MiniBar value={v} />
        </div>
      ))}

      {/* SIGNAL */}
      <div style={{ width: 140, minWidth: 140, flexShrink: 0, padding: "0 6px" }}>
        <span style={{
          fontSize: 11, fontWeight: 600,
          letterSpacing: 0.2, color: sigColor,
          background: `${sigColor}12`,
          border: `1px solid ${sigColor}35`,
          borderRadius: 3, padding: "3px 8px",
          display: "inline-block",
        }}>
          {label}
        </span>
      </div>
    </div>
  );
}

/* ── MiniBar — 흰색 게이지 (#e8e8e8) ──────────────── */
function MiniBar({ value }) {
  return (
    <div style={{
      width: "100%", height: 3,
      background: "#2a2a2a",
      borderRadius: 2, overflow: "hidden",
    }}>
      <div style={{
        width: `${value}%`, height: "100%",
        background: "#e8e8e8",
        borderRadius: 2,
      }} />
    </div>
  );
}

function Empty() {
  return (
    <div style={{
      display: "flex", alignItems: "center", justifyContent: "center",
      height: "100%", fontSize: 13, color: C.textMuted,
      fontFamily: "'Inter', sans-serif",
    }}>
      조건에 맞는 종목이 없습니다.
    </div>
  );
}

/* ── 필터 서브 컴포넌트 ──────────────────────────────── */
function FInput({ value, onChange, placeholder, width }) {
  return (
    <input
      value={value}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
      style={{
        fontFamily: "'Inter', sans-serif", fontSize: 12, width,
        background: "#111", color: "#e8e8e8",
        border: `1px solid ${C.border}`,
        borderRadius: 3, padding: "5px 10px", outline: "none",
      }}
    />
  );
}

function FSelect({ value, onChange, options, highlight }) {
  return (
    <select
      value={value}
      onChange={e => onChange(e.target.value)}
      style={{
        fontFamily: "'Inter', sans-serif", fontSize: 12,
        background: "#111",
        color: highlight ? C.primary : C.textGray,
        border: `1px solid ${highlight ? C.primary : C.border}`,
        borderRadius: 3, padding: "5px 8px",
        outline: "none", cursor: "pointer",
      }}
    >
      {options.map(o => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  );
}