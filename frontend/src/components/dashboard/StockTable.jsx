/**
 * StockTable.jsx
 * 메인 종목 테이블
 * - 필터: 티커, 회사명, 섹터, 국가, 등급
 * - 정렬: 각 컬럼 클릭
 * - 체크박스: 선택 후 삭제
 * - 티커 hover: 색상 변화 + 살짝 이동
 * - 우측 상단: 배치 정보 + 티커 추가 버튼
 */

import { useState, useMemo } from "react";
import { C, FONT, SECTORS, MOCK_STOCKS, gradeColor, gradeLabel } from "../../styles/tokens";
import { AddTickerModal, DeleteConfirmModal } from "./Modals";

const GRADES = ["ALL", "S", "A+", "A", "B+", "B", "C", "D"];
const COUNTRIES = ["ALL", "US", "KR", "JP", "CN", "IN"];

const COLUMNS = [
  { key: "ticker",  label: "TICKER",  width: 90,  sortable: true  },
  { key: "name",    label: "COMPANY", width: 220, sortable: true  },
  { key: "sector",  label: "SECTOR",  width: 140, sortable: true  },
  { key: "grade",   label: "GRADE",   width: 70,  sortable: true  },
  { key: "score",   label: "SCORE",   width: 110, sortable: true  },
  { key: "price",   label: "PRICE",   width: 100, sortable: true  },
  { key: "chg",     label: "CHG%",    width: 80,  sortable: true  },
  { key: "l1",      label: "L1",      width: 60,  sortable: true, tooltip: "퀀트 레이팅 (Fundamental)" },
  { key: "l2",      label: "L2",      width: 60,  sortable: true, tooltip: "텍스트·감성 신호 (NLP/AI)" },
  { key: "l3",      label: "L3",      width: 60,  sortable: true, tooltip: "시장 신호 (Price/Order Flow)" },
  { key: "signal",  label: "SIGNAL",  width: 140, sortable: false },
];

const sectorLabel = (key) => SECTORS.find(s => s.key === key)?.en ?? key;

export default function StockTable({ onTickerClick, filterSector }) {
  // ─── 필터 상태
  const [search,       setSearch]       = useState("");
  const [searchName,   setSearchName]   = useState("");
  const [selSector,    setSelSector]    = useState("ALL");
  const [selCountry,   setSelCountry]   = useState("ALL");
  const [selGrade,     setSelGrade]     = useState("ALL");

  // ─── 정렬 상태
  const [sortKey,  setSortKey]  = useState("score");
  const [sortDesc, setSortDesc] = useState(true);

  // ─── 체크박스 상태
  const [checked, setChecked] = useState(new Set());

  // ─── 모달
  const [showAdd,    setShowAdd]    = useState(false);
  const [showDelete, setShowDelete] = useState(false);

  // 외부 섹터 필터 (사이드바 클릭)
  const effectiveSector = filterSector ?? selSector;

  // ─── 필터 + 정렬 처리
  const rows = useMemo(() => {
    let data = [...MOCK_STOCKS];
    if (search)           data = data.filter(s => s.ticker.includes(search.toUpperCase()));
    if (searchName)       data = data.filter(s => s.name.toLowerCase().includes(searchName.toLowerCase()));
    if (effectiveSector !== "ALL") data = data.filter(s => s.sector === effectiveSector);
    if (selCountry !== "ALL")      data = data.filter(s => s.country === selCountry);
    if (selGrade !== "ALL")        data = data.filter(s => s.grade === selGrade);

    data.sort((a, b) => {
      let av = a[sortKey], bv = b[sortKey];
      if (typeof av === "string") av = av.toLowerCase();
      if (typeof bv === "string") bv = bv.toLowerCase();
      if (av < bv) return sortDesc ? 1 : -1;
      if (av > bv) return sortDesc ? -1 : 1;
      return 0;
    });
    return data;
  }, [search, searchName, effectiveSector, selCountry, selGrade, sortKey, sortDesc]);

  const toggleSort = (key) => {
    if (!COLUMNS.find(c => c.key === key)?.sortable) return;
    if (sortKey === key) setSortDesc(v => !v);
    else { setSortKey(key); setSortDesc(true); }
  };

  // 체크박스
  const allIds   = rows.map(r => r.ticker);
  const allChecked = allIds.length > 0 && allIds.every(id => checked.has(id));
  const someChecked = allIds.some(id => checked.has(id));

  const toggleAll = () => {
    if (allChecked) setChecked(new Set());
    else setChecked(new Set(allIds));
  };
  const toggleOne = (ticker) => {
    const next = new Set(checked);
    next.has(ticker) ? next.delete(ticker) : next.add(ticker);
    setChecked(next);
  };

  const checkedList = [...checked];

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>

      {/* ── 필터 바 + 우측 액션 버튼 */}
      <div style={{
        padding: "10px 16px",
        background: "#0c0c0c",
        borderBottom: `1px solid ${C.border}`,
        display: "flex",
        alignItems: "center",
        gap: 8,
        flexWrap: "wrap",
        flexShrink: 0,
      }}>
        {/* 티커 검색 */}
        <FilterInput
          value={search}
          onChange={setSearch}
          placeholder="Ticker"
          width={100}
        />
        {/* 회사명 검색 */}
        <FilterInput
          value={searchName}
          onChange={setSearchName}
          placeholder="Company Name"
          width={180}
        />
        {/* 국가 */}
        <FilterSelect
          value={selCountry}
          onChange={setSelCountry}
          options={COUNTRIES.map(c => ({ value: c, label: c === "ALL" ? "All Countries" : c }))}
        />
        {/* 섹터 */}
        <FilterSelect
          value={selSector}
          onChange={setSelSector}
          options={[
            { value: "ALL", label: "All Sectors" },
            ...SECTORS.map(s => ({ value: s.key, label: s.en }))
          ]}
        />
        {/* 등급 */}
        <FilterSelect
          value={selGrade}
          onChange={setSelGrade}
          options={GRADES.map(g => ({ value: g, label: g === "ALL" ? "All Ratings" : g }))}
        />
        {/* Reset */}
        <button
          onClick={() => { setSearch(""); setSearchName(""); setSelSector("ALL"); setSelCountry("ALL"); setSelGrade("ALL"); }}
          style={{
            fontFamily: FONT.mono, fontSize: 11, color: C.orange,
            background: "none", border: `1px solid ${C.orange}60`,
            borderRadius: 3, padding: "5px 10px", cursor: "pointer",
          }}
        >
          Reset
        </button>

        {/* Spacer */}
        <div style={{ flex: 1 }} />

        {/* 선택 삭제 버튼 */}
        {checkedList.length > 0 && (
          <button
            onClick={() => setShowDelete(true)}
            style={{
              fontFamily: FONT.mono, fontSize: 11, fontWeight: 700,
              color: "#fff", background: C.red,
              border: "none", borderRadius: 3,
              padding: "5px 12px", cursor: "pointer",
            }}
          >
            ✕ {checkedList.length}개 삭제
          </button>
        )}

        {/* 배치 정보 */}
        <div style={{
          fontFamily: FONT.mono, fontSize: 9, color: C.textMuted, textAlign: "right", lineHeight: 1.6,
        }}>
          <div>{rows.length} / {MOCK_STOCKS.length} 종목</div>
          <div>배치: 03-09 02:14 KST</div>
        </div>

        {/* 티커 추가 */}
        <button
          onClick={() => setShowAdd(true)}
          style={{
            fontFamily: FONT.mono, fontSize: 11, fontWeight: 700,
            color: "#fff", background: C.orange,
            border: "none", borderRadius: 3,
            padding: "6px 14px", cursor: "pointer",
            letterSpacing: 0.5, whiteSpace: "nowrap",
          }}
        >
          + ADD TICKER
        </button>
      </div>

      {/* ── 테이블 헤더 */}
      <div style={{
        display: "flex",
        alignItems: "center",
        padding: "0 16px",
        background: "#0a0a0a",
        borderBottom: `1px solid ${C.border}`,
        height: 36,
        flexShrink: 0,
      }}>
        {/* 전체선택 체크박스 */}
        <div style={{ width: 32, flexShrink: 0, display: "flex", alignItems: "center" }}>
          <input
            type="checkbox"
            checked={allChecked}
            ref={el => el && (el.indeterminate = !allChecked && someChecked)}
            onChange={toggleAll}
            style={{ accentColor: C.cyan, cursor: "pointer" }}
          />
        </div>

        {COLUMNS.map(col => (
          <ColHeader
            key={col.key}
            col={col}
            sortKey={sortKey}
            sortDesc={sortDesc}
            onSort={() => toggleSort(col.key)}
          />
        ))}
      </div>

      {/* ── 테이블 바디 */}
      <div style={{ flex: 1, overflowY: "auto" }}>
        {rows.length === 0 ? (
          <div style={{
            display: "flex", alignItems: "center", justifyContent: "center",
            height: "100%", fontFamily: FONT.mono, fontSize: 12, color: C.textMuted,
          }}>
            조건에 맞는 종목이 없습니다.
          </div>
        ) : (
          rows.map((row, i) => (
            <TableRow
              key={row.ticker}
              row={row}
              odd={i % 2 !== 0}
              checked={checked.has(row.ticker)}
              onCheck={() => toggleOne(row.ticker)}
              onClick={() => onTickerClick?.(row.ticker)}
            />
          ))
        )}
      </div>

      {/* ── 모달 */}
      {showAdd    && <AddTickerModal onClose={() => setShowAdd(false)} onAdd={(t) => console.log("추가:", t)} />}
      {showDelete && (
        <DeleteConfirmModal
          tickers={checkedList}
          onClose={() => setShowDelete(false)}
          onConfirm={() => {
            setChecked(new Set());
            setShowDelete(false);
            // 실제 구현: API 호출
            console.log("삭제:", checkedList);
          }}
        />
      )}
    </div>
  );
}

// ── ColHeader
function ColHeader({ col, sortKey, sortDesc, onSort }) {
  const [hovered, setHovered] = useState(false);
  const active = sortKey === col.key;
  return (
    <div
      onClick={onSort}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      title={col.tooltip}
      style={{
        width: col.width, minWidth: col.width, flexShrink: 0,
        fontFamily: FONT.mono, fontSize: 10, letterSpacing: 0.5,
        color: active ? C.cyan : hovered ? C.textGray : C.textMuted,
        cursor: col.sortable ? "pointer" : "default",
        userSelect: "none",
        display: "flex", alignItems: "center", gap: 4,
        padding: "0 6px",
        transition: "color 0.1s",
      }}
    >
      {col.label}
      {active && col.sortable && (
        <span style={{ fontSize: 8 }}>{sortDesc ? "▼" : "▲"}</span>
      )}
      {!active && col.sortable && hovered && (
        <span style={{ fontSize: 8, opacity: 0.4 }}>⇅</span>
      )}
    </div>
  );
}

// ── TableRow
function TableRow({ row, odd, checked, onCheck, onClick }) {
  const [tickerHover, setTickerHover] = useState(false);
  const [rowHover,    setRowHover]    = useState(false);

  const gc = gradeColor(row.grade);
  const signalLabel = gradeLabel(row.grade);
  const signalColor =
    row.grade === "S" || row.grade === "A+" ? C.green :
    row.grade === "A"  ? "#4ade80" :
    row.grade === "B+" ? C.golden :
    row.grade === "B"  ? C.orange :
    row.grade === "C"  ? C.red : C.scarlet;

  return (
    <div
      onMouseEnter={() => setRowHover(true)}
      onMouseLeave={() => setRowHover(false)}
      style={{
        display: "flex",
        alignItems: "center",
        padding: "0 16px",
        height: 46,
        background: checked ? `${C.cyan}08` : rowHover ? `${C.border}40` : odd ? "#0d0d0d" : C.bgDark,
        borderBottom: `1px solid ${C.border}30`,
        transition: "background 0.1s",
        cursor: "pointer",
      }}
    >
      {/* 체크박스 */}
      <div style={{ width: 32, flexShrink: 0 }} onClick={e => { e.stopPropagation(); onCheck(); }}>
        <input
          type="checkbox"
          checked={checked}
          onChange={onCheck}
          onClick={e => e.stopPropagation()}
          style={{ accentColor: C.cyan, cursor: "pointer" }}
        />
      </div>

      {/* TICKER */}
      <div
        style={{ width: 90, minWidth: 90, flexShrink: 0, padding: "0 6px" }}
        onMouseEnter={() => setTickerHover(true)}
        onMouseLeave={() => setTickerHover(false)}
        onClick={onClick}
      >
        <span style={{
          fontFamily: FONT.mono,
          fontSize: 13,
          fontWeight: 700,
          color: tickerHover ? C.cyan : C.orange,
          textDecoration: tickerHover ? "underline" : "none",
          transform: tickerHover ? "translateX(3px)" : "translateX(0)",
          display: "inline-block",
          transition: "all 0.15s ease",
          cursor: "pointer",
        }}>
          {row.ticker}
        </span>
      </div>

      {/* COMPANY */}
      <div style={{ width: 220, minWidth: 220, flexShrink: 0, padding: "0 6px", overflow: "hidden" }}>
        <span style={{
          fontFamily: FONT.sans, fontSize: 12, color: C.textGray,
          whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", display: "block",
        }}>
          {row.name}
        </span>
      </div>

      {/* SECTOR */}
      <div style={{ width: 140, minWidth: 140, flexShrink: 0, padding: "0 6px" }}>
        <span style={{ fontFamily: FONT.mono, fontSize: 10, color: C.textMuted, letterSpacing: 0.3 }}>
          {sectorLabel(row.sector)}
        </span>
      </div>

      {/* GRADE */}
      <div style={{ width: 70, minWidth: 70, flexShrink: 0, padding: "0 6px" }}>
        <span style={{ fontFamily: FONT.mono, fontSize: 15, fontWeight: 800, color: gc }}>
          {row.grade}
        </span>
      </div>

      {/* SCORE */}
      <div style={{ width: 110, minWidth: 110, flexShrink: 0, padding: "0 6px" }}>
        <div style={{ fontFamily: FONT.mono, fontSize: 13, fontWeight: 700, color: C.textPri, marginBottom: 2 }}>
          {row.score.toFixed(1)}
        </div>
        <ScoreBar value={row.score} color={gc} />
      </div>

      {/* PRICE */}
      <div style={{ width: 100, minWidth: 100, flexShrink: 0, padding: "0 6px" }}>
        <span style={{ fontFamily: FONT.mono, fontSize: 12, color: C.textPri }}>
          ${row.price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </span>
      </div>

      {/* CHG% */}
      <div style={{ width: 80, minWidth: 80, flexShrink: 0, padding: "0 6px" }}>
        <span style={{
          fontFamily: FONT.mono, fontSize: 12, fontWeight: 600,
          color: row.chg > 0 ? C.green : row.chg < 0 ? C.red : C.textMuted,
        }}>
          {row.chg > 0 ? "▲" : row.chg < 0 ? "▼" : ""}
          {Math.abs(row.chg).toFixed(2)}%
        </span>
      </div>

      {/* L1 */}
      <LayerCell value={row.l1} color={C.cyan} width={60} />

      {/* L2 */}
      <LayerCell value={row.l2} color="#a78bfa" width={60} />

      {/* L3 */}
      <LayerCell value={row.l3} color="#22d3ee" width={60} />

      {/* SIGNAL */}
      <div style={{ width: 140, minWidth: 140, flexShrink: 0, padding: "0 6px" }}>
        <span style={{
          fontFamily: FONT.mono, fontSize: 10, fontWeight: 700, letterSpacing: 0.3,
          color: signalColor,
          background: `${signalColor}15`,
          border: `1px solid ${signalColor}40`,
          borderRadius: 3, padding: "3px 8px",
          display: "inline-block",
        }}>
          {signalLabel}
        </span>
      </div>
    </div>
  );
}

function LayerCell({ value, color, width }) {
  return (
    <div style={{ width, minWidth: width, flexShrink: 0, padding: "0 6px" }}>
      <div style={{ fontFamily: FONT.mono, fontSize: 11, color, marginBottom: 2 }}>{value}</div>
      <ScoreBar value={value} color={color} />
    </div>
  );
}

function ScoreBar({ value, color }) {
  return (
    <div style={{
      width: "100%", height: 3, background: C.border, borderRadius: 2, overflow: "hidden",
    }}>
      <div style={{
        width: `${value}%`, height: "100%", background: color,
        borderRadius: 2, boxShadow: `0 0 4px ${color}60`,
      }} />
    </div>
  );
}

// ── 필터 서브 컴포넌트
function FilterInput({ value, onChange, placeholder, width }) {
  return (
    <input
      value={value}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
      style={{
        fontFamily: FONT.mono, fontSize: 11, width,
        background: "#111", color: C.textPri,
        border: `1px solid ${C.border}`, borderRadius: 3,
        padding: "5px 10px", outline: "none",
      }}
    />
  );
}

function FilterSelect({ value, onChange, options }) {
  return (
    <select
      value={value}
      onChange={e => onChange(e.target.value)}
      style={{
        fontFamily: FONT.mono, fontSize: 11,
        background: "#111", color: C.textGray,
        border: `1px solid ${C.border}`, borderRadius: 3,
        padding: "5px 8px", outline: "none", cursor: "pointer",
      }}
    >
      {options.map(o => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  );
}

const sectorLabel_ = (key) => SECTORS.find(s => s.key === key)?.en ?? key;