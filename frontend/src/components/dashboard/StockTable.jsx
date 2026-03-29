/**
 * StockTable.jsx — v5.1
 *
 * v5.1 변경:
 *   ✅ 정렬 수정: grade/signal 모두 커스텀 order로 정렬 (한글 시그널도 매핑)
 *   ✅ 필터 단순화: Grade 필터 1개만 (전체 등급 대상)
 *   ✅ Signal 색상 = Grade 동일 색상 체계 (gradeColor 사용)
 *   ✅ 티커 호버 = yolk(#F3BE26) 색상
 *   ✅ 폰트 = FONT.sans 전체 통일
 *   ✅ 헤더 3세트 시각 분리 유지 (QUANT / AI / FINAL)
 *   ✅ 디폴트 정렬: ai_signal desc, 3번째 클릭 정렬 해제
 */
import { useState, useMemo, useEffect, useCallback, useRef } from "react";
import { C, FONT, SECTORS, MOCK_STOCKS, gradeColor, gradeLabel, gradeTextColor, chgColor, sectorByBackendName } from "../../styles/tokens";
import { DeleteConfirmModal } from "./Modals";
import api from "../../api";

const GRADES    = ["ALL", "S", "A+", "A", "B+", "B", "C", "D"];
const COUNTRIES = ["ALL", "US", "KR", "JP"];

// ── 정렬용 숫자 매핑 (높을수록 좋음) ──
const _GRADE_ORDER  = { "S": 7, "A+": 6, "A": 5, "B+": 4, "B": 3, "C": 2, "D": 1 };

// 영문 시그널 → 정렬 순서 (7단계 + 5단계 모두 커버)
const _SIGNAL_ORDER = {
  "STRONG_BUY": 7, "BUY": 6, "OUTPERFORM": 5, "HOLD": 4,
  "UNDERPERFORM": 3, "SELL": 2, "STRONG_SELL": 1,
};

// 한글 시그널 → 정렬 순서 (혹시 한글로 내려올 경우 대비)
const _SIGNAL_KO_ORDER = {
  "강력매수": 7, "매수": 6, "우수": 5, "보유": 4,
  "부진": 3, "매도": 2, "강력매도": 1,
};

// 영문 → 한글 변환
const _SIGNAL_KO = {
  "STRONG_BUY": "강력매수", "BUY": "매수", "OUTPERFORM": "우수",
  "HOLD": "보유", "UNDERPERFORM": "부진", "SELL": "매도", "STRONG_SELL": "강력매도",
};

// 시그널 → 등급 매핑 (signal에 grade 색상 적용하기 위함)
const _SIGNAL_TO_GRADE = {
  "STRONG_BUY": "S", "BUY": "A+", "OUTPERFORM": "A", "HOLD": "B+",
  "UNDERPERFORM": "B", "SELL": "C", "STRONG_SELL": "D",
  // 한글도 매핑
  "강력매수": "S", "매수": "A+", "우수": "A", "보유": "B+",
  "부진": "B", "매도": "C", "강력매도": "D",
};

// 시그널 정렬값 가져오기 (영문/한글 모두 대응)
function getSignalOrder(val) {
  if (val == null) return -1;
  return _SIGNAL_ORDER[val] ?? _SIGNAL_KO_ORDER[val] ?? -1;
}

// 시그널 → 한글 변환 (이미 한글이면 그대로)
function toSignalKo(sig) {
  if (!sig) return "—";
  return _SIGNAL_KO[sig] || sig;
}

// 시그널 → gradeColor 색상 (등급 색상 체계 동일 적용)
function signalToColor(sig) {
  const g = _SIGNAL_TO_GRADE[sig];
  return g ? gradeColor(g) : C.textMuted;
}

// score → grade 변환 (backend grade_utils.py 로직 동일)
function scoreToGrade(score) {
  if (score == null) return null;
  const s = Number(score);
  if (s >= 90) return "S";
  if (s >= 80) return "A+";
  if (s >= 70) return "A";
  if (s >= 60) return "B+";
  if (s >= 50) return "B";
  if (s >= 40) return "C";
  return "D";
}

// score → signal 변환
function scoreToSignal(score) {
  if (score == null) return null;
  const s = Number(score);
  if (s >= 80) return "STRONG_BUY";
  if (s >= 65) return "BUY";
  if (s >= 50) return "OUTPERFORM";
  if (s >= 40) return "HOLD";
  if (s >= 30) return "UNDERPERFORM";
  if (s >= 20) return "SELL";
  return "STRONG_SELL";
}

// sector_code → SECTORS key
function toSectorKey(row) {
  if (!row) return null;
  if (row.sector_code) {
    const found = SECTORS.find(s => s.code === String(row.sector_code));
    if (found) return found.key;
  }
  if (row.sector) {
    const found = sectorByBackendName(row.sector);
    if (found) return found.key;
  }
  return null;
}

// ── 컬럼 정의 (group 속성으로 3세트 구분) ──
const INIT_COLUMNS = [
  { key: "ticker",    label: "TICKER",    w: 74,  min: 60,  group: "info" },
  { key: "name",      label: "COMPANY",   w: 145, min: 80,  group: "info" },
  { key: "sector",    label: "SECTOR",    w: 130, min: 80,  group: "info" },
  { key: "price",     label: "PRICE",     w: 82,  min: 60,  group: "info" },
  { key: "chg",       label: "CHG%",      w: 64,  min: 50,  group: "info" },
  { key: "l1",        label: "L1",        w: 44,  min: 36,  group: "quant", tip: "퀀트 레이팅 (Fundamental)" },
  { key: "l2",        label: "L2",        w: 44,  min: 36,  group: "quant", tip: "텍스트·감성 신호 (NLP/AI)" },
  { key: "l3",        label: "L3",        w: 44,  min: 36,  group: "quant", tip: "시장 신호 (Price/Order Flow)" },
  { key: "score",     label: "SCORE",     w: 62,  min: 50,  group: "quant", tip: "L1+L2+L3 가중합 (Stat)" },
  { key: "grade",     label: "Q.GRADE",   w: 56,  min: 44,  group: "quant", tip: "퀀트 전용 등급" },
  { key: "signal",    label: "Q.SIG",     w: 70,  min: 56,  group: "quant", tip: "퀀트 전용 시그널" },
  { key: "ai_score",  label: "AI",        w: 48,  min: 36,  group: "ai",    tip: "XGBoost AI 예측 점수" },
  { key: "ensemble",  label: "ENSEMBLE",  w: 68,  min: 50,  group: "ai",    tip: "Stat×0.7 + AI×0.3" },
  { key: "ai_grade",  label: "GRADE",     w: 56,  min: 44,  group: "final", tip: "최종 등급 (퀀트+AI)" },
  { key: "ai_signal", label: "F.SIGNAL",  w: 76,  min: 56,  group: "final", tip: "최종 시그널 (퀀트+AI)" },
];

// 그룹 메타
const GROUP_META = {
  info:  { label: "",       borderColor: "transparent" },
  quant: { label: "QUANT",  borderColor: C.primary },
  ai:    { label: "AI",     borderColor: C.cyan },
  final: { label: "FINAL",  borderColor: C.pink },
};

// 3클릭 정렬: desc → asc → 해제
function nextSort(prev, clickedKey) {
  if (prev.key !== clickedKey) return { key: clickedKey, dir: "desc" };
  if (prev.dir === "desc")     return { key: clickedKey, dir: "asc" };
  return { key: null, dir: null };
}


// ═══════════════════════════════════════════════════════
//  Main Component
// ═══════════════════════════════════════════════════════
export default function StockTable({ filterSector, onTickerClick, onResetSector }) {
  const [stocks, setStocks]           = useState([]);
  const [search, setSearch]           = useState("");
  const [searchName, setSearchName]   = useState("");
  const [selSector, setSelSector]     = useState("ALL");
  const [selCountry, setSelCountry]   = useState("ALL");
  const [selGrade, setSelGrade]       = useState("ALL");
  const [sort, setSort]               = useState({ key: "ai_signal", dir: "desc" });
  const [checked, setChecked]         = useState(new Set());
  const [deleteOpen, setDeleteOpen]   = useState(false);
  const [columns, setColumns]         = useState(INIT_COLUMNS);

  // ── 데이터 로드 + ai_grade/ai_signal 보충
  useEffect(() => {
    api.get("/api/stocks")
      .then(res => {
        if (Array.isArray(res.data)) {
          const enriched = res.data.map(row => ({
            ...row,
            ai_grade:  row.ai_grade  || scoreToGrade(row.ensemble)  || row.grade  || null,
            ai_signal: row.ai_signal || scoreToSignal(row.ensemble) || row.signal || null,
          }));
          setStocks(enriched);
        }
      })
      .catch(() => setStocks(MOCK_STOCKS || []));
  }, []);

  // ── 사이드바 섹터 동기화
  useEffect(() => {
    setSelSector(filterSector || "ALL");
  }, [filterSector]);

  const reset = () => {
    setSearch(""); setSearchName("");
    setSelSector("ALL"); setSelCountry("ALL");
    setSelGrade("ALL");
    onResetSector?.();
  };

  // ── 필터 + 정렬
  const rows = useMemo(() => {
    let data = [...stocks];

    if (search)     data = data.filter(r => r.ticker?.toLowerCase().includes(search.toLowerCase()));
    if (searchName) data = data.filter(r => r.name?.toLowerCase().includes(searchName.toLowerCase()));
    if (selSector  !== "ALL") data = data.filter(r => toSectorKey(r) === selSector);
    if (selCountry !== "ALL") data = data.filter(r => r.country === selCountry);

    // Grade 필터: quant grade OR ai_grade 중 하나라도 매칭
    if (selGrade !== "ALL") {
      data = data.filter(r => r.grade === selGrade || r.ai_grade === selGrade);
    }

    // 정렬
    if (sort.key && sort.dir) {
      data.sort((a, b) => {
        let av = a[sort.key] ?? null;
        let bv = b[sort.key] ?? null;

        // null → 항상 뒤로
        if (av == null && bv == null) return 0;
        if (av == null) return 1;
        if (bv == null) return -1;

        // 등급 정렬
        if (sort.key === "grade" || sort.key === "ai_grade") {
          av = _GRADE_ORDER[av] ?? -1;
          bv = _GRADE_ORDER[bv] ?? -1;
        }
        // 시그널 정렬 (영문/한글 모두 대응)
        else if (sort.key === "signal" || sort.key === "ai_signal") {
          av = getSignalOrder(av);
          bv = getSignalOrder(bv);
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

  const handleSort = (key) => setSort(prev => nextSort(prev, key));

  const handleResize = useCallback((idx, delta) => {
    setColumns(prev => {
      const next = [...prev];
      next[idx] = { ...next[idx], w: Math.max(next[idx].min || 36, next[idx].w + delta) };
      return next;
    });
  }, []);

  // ── 티커 클릭 → 새 창
  const handleTicker = (ticker) => {
    window.open(`/stock/${ticker}/summary`, "_blank", "noopener");
  };

  const handleSectorChange = (val) => {
    setSelSector(val);
    if (val === "ALL") onResetSector?.();
  };

  // 그룹별 컬럼 너비 합산
  const groupWidth = (groupKey) => columns.filter(c => c.group === groupKey).reduce((s, c) => s + c.w, 0);

  return (
    <div style={{ fontFamily: FONT.sans, color: C.textPri }}>

      {/* ── 필터 바 ── */}
      <div style={{
        display: "flex", gap: 8, alignItems: "center", padding: "10px 16px",
        background: C.bgDeeper, borderRadius: 10, marginBottom: 8, flexWrap: "wrap",
      }}>
        <FInput value={search}     onChange={setSearch}     placeholder="Ticker" width={100} />
        <FInput value={searchName} onChange={setSearchName} placeholder="Company Name" width={140} />
        <FSelect value={selCountry} onChange={setSelCountry}
          options={COUNTRIES.map(c => ({ value: c, label: c === "ALL" ? "All Countries" : c }))} />
        <FSelect value={selSector} onChange={handleSectorChange}
          options={[{ value: "ALL", label: "All Sectors" }, ...SECTORS.map(s => ({ value: s.key, label: s.en }))]} />
        <FSelect value={selGrade} onChange={setSelGrade}
          options={GRADES.map(g => ({ value: g, label: g === "ALL" ? "All Grades" : g }))} />

        <button onClick={reset} style={{
          fontFamily: FONT.sans, fontSize: 11, fontWeight: 600,
          color: C.pink, background: "none",
          border: `1px solid ${C.pink}44`, borderRadius: 4,
          padding: "4px 14px", cursor: "pointer",
        }}>Reset</button>
      </div>

      {/* ── 테이블 ── */}
      <div style={{ overflowX: "auto" }}>

        {/* ── 그룹 라벨 행 (QUANT / AI / FINAL) ── */}
        <div style={{
          display: "flex", alignItems: "flex-end", padding: "0 16px", height: 22,
          background: C.bgDeeper,
        }}>
          <div style={{ width: 28, flexShrink: 0 }} />
          <div style={{ width: groupWidth("info"), flexShrink: 0 }} />
          {["quant", "ai", "final"].map(gk => (
            <div key={gk} style={{
              width: groupWidth(gk), flexShrink: 0,
              textAlign: "center", fontSize: 9, fontWeight: 800, letterSpacing: 1.2,
              color: GROUP_META[gk].borderColor,
              borderBottom: `2px solid ${GROUP_META[gk].borderColor}`,
              fontFamily: FONT.sans, lineHeight: "20px",
              marginLeft: 2,
            }}>{GROUP_META[gk].label}</div>
          ))}
        </div>

        {/* ── 컬럼 헤더 ── */}
        <div style={{
          display: "flex", alignItems: "center",
          padding: "0 16px", height: 36,
          background: C.bgDeeper, borderBottom: `1px solid ${C.border}`,
          position: "sticky", top: 0, zIndex: 2,
        }}>
          <div style={{ width: 28, flexShrink: 0 }}>
            <input type="checkbox" checked={allChecked} onChange={toggleAll}
              style={{ accentColor: C.primary, cursor: "pointer" }} />
          </div>
          {columns.map((col, idx) => {
            const prevGroup = idx > 0 ? columns[idx - 1].group : null;
            const showSep = col.group !== "info" && col.group !== prevGroup;
            return (
              <ColHead key={col.key} col={col} sort={sort}
                onSort={() => handleSort(col.key)}
                onResize={(d) => handleResize(idx, d)}
                showSep={showSep}
                groupColor={GROUP_META[col.group]?.borderColor || "transparent"}
              />
            );
          })}
        </div>

        {/* ── 바디 ── */}
        <div style={{ maxHeight: "calc(100vh - 260px)", overflowY: "auto" }}>
          {rows.length === 0 ? (
            <div style={{ textAlign: "center", color: C.textMuted, padding: 40, fontSize: 13, fontFamily: FONT.sans }}>
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
  const [tickerHov, setTickerHov] = useState(false);

  const fmtPrice = (v) => v != null
    ? `$${Number(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    : "—";
  const fmtChg   = (v) => v != null ? `${v > 0 ? "▲" : v < 0 ? "▼" : ""}${Math.abs(v).toFixed(2)}%` : "—";
  const fmtScore = (v) => v != null ? Number(v).toFixed(1) : "—";

  const renderCell = (col) => {
    const w = col.w;
    const colIdx = columns.indexOf(col);
    const prevGroup = colIdx > 0 ? columns[colIdx - 1].group : null;
    const showSep = col.group !== "info" && col.group !== prevGroup;

    const base = {
      width: w, minWidth: w, flexShrink: 0,
      padding: "0 4px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
      borderLeft: showSep ? `1px solid ${GROUP_META[col.group]?.borderColor || C.border}30` : "none",
      fontFamily: FONT.sans,
    };

    switch (col.key) {
      case "ticker":
        return (
          <div key={col.key} style={{ ...base, cursor: "pointer" }}
            onClick={(e) => { e.stopPropagation(); onClick(); }}
            onMouseEnter={() => setTickerHov(true)}
            onMouseLeave={() => setTickerHov(false)}
          >
            <span style={{
              fontSize: tickerHov ? 15 : 13,
              fontWeight: 700,
              color: tickerHov ? C.yolk : C.primary,
              fontFamily: FONT.sans,
              transition: "all 0.15s ease",
            }}>{row.ticker}</span>
          </div>
        );
      case "name":
        return <div key={col.key} style={base}><span style={{ fontSize: 12, color: C.textGray }}>{row.name || "—"}</span></div>;
      case "sector":
        return <div key={col.key} style={base}><span style={{ fontSize: 11, color: C.textMuted }}>{row.sector || "—"}</span></div>;
      case "price":
        return <div key={col.key} style={base}><span style={{ fontSize: 12, fontWeight: 600, color: C.textPri, fontFamily: FONT.sans }}>{fmtPrice(row.price)}</span></div>;
      case "chg": {
        const cc = chgColor(row.chg);
        return <div key={col.key} style={base}><span style={{ fontSize: 11, fontWeight: 700, color: cc, fontFamily: FONT.sans }}>{fmtChg(row.chg)}</span></div>;
      }
      case "l1": case "l2": case "l3":
        return <div key={col.key} style={{ ...base, textAlign: "center" }}><span style={{ fontSize: 12, fontWeight: 600, color: C.textGray, fontFamily: FONT.sans }}>{fmtScore(row[col.key])}</span></div>;
      case "score":
        return (
          <div key={col.key} style={base}>
            <div style={{ fontSize: 12, fontWeight: 700, color: C.textGray, fontFamily: FONT.sans }}>{fmtScore(row.score)}</div>
            <MiniBar value={row.score ?? 0} />
          </div>
        );
      case "grade": {
        const g = row.grade ?? "—";
        return <div key={col.key} style={{ ...base, textAlign: "center" }}><span style={{ fontSize: 14, fontWeight: 800, color: gradeColor(g) }}>{g}</span></div>;
      }
      case "signal": {
        const sig = row.signal;
        const ko = toSignalKo(sig);
        const sc = signalToColor(sig);
        return (
          <div key={col.key} style={base}>
            <span style={{
              fontSize: 9, fontWeight: 700, letterSpacing: 0.2,
              color: sc, background: `${sc}10`,
              border: `1px solid ${sc}25`, borderRadius: 3,
              padding: "2px 5px", display: "inline-block", whiteSpace: "nowrap",
              opacity: 0.85,
            }}>{ko}</span>
          </div>
        );
      }
      case "ai_score":
        return (
          <div key={col.key} style={{ ...base, textAlign: "center" }}>
            {row.ai_score != null
              ? <span style={{ fontSize: 12, fontWeight: 700, color: C.cyan, fontFamily: FONT.sans }}>{Number(row.ai_score).toFixed(1)}</span>
              : <span style={{ fontSize: 10, color: C.border }}>—</span>}
          </div>
        );
      case "ensemble":
        return (
          <div key={col.key} style={base}>
            {row.ensemble != null ? (
              <>
                <div style={{ fontSize: 12, fontWeight: 700, color: C.textPri, fontFamily: FONT.sans }}>{Number(row.ensemble).toFixed(1)}</div>
                <MiniBar value={row.ensemble ?? 0} color={C.cyan} />
              </>
            ) : <span style={{ fontSize: 10, color: C.border }}>—</span>}
          </div>
        );
      case "ai_grade": {
        const g = row.ai_grade ?? "—";
        return <div key={col.key} style={{ ...base, textAlign: "center" }}><span style={{ fontSize: 14, fontWeight: 800, color: gradeColor(g) }}>{g}</span></div>;
      }
      case "ai_signal": {
        const finalSig = row.ai_signal || row.signal;
        const ko = toSignalKo(finalSig);
        const finalColor = signalToColor(finalSig);
        const hasAi = row.ai_signal != null;
        return (
          <div key={col.key} style={base}>
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
        return <div key={col.key} style={base}>—</div>;
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
      <div style={{ width: 28, flexShrink: 0 }}>
        <input type="checkbox" checked={checked} onChange={onCheck}
          onClick={e => e.stopPropagation()}
          style={{ accentColor: C.primary, cursor: "pointer" }} />
      </div>
      {columns.map(col => renderCell(col))}
    </div>
  );
}


// ═══════════════════════════════════════════════════════
//  ColHead
// ═══════════════════════════════════════════════════════
function ColHead({ col, sort, onSort, onResize, showSep, groupColor }) {
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
      borderLeft: showSep ? `1px solid ${groupColor}40` : "none",
    }}>
      <div onClick={onSort}
        onMouseEnter={() => setHov(true)} onMouseLeave={() => setHov(false)}
        title={col.tip || ""}
        style={{
          fontSize: 10, fontWeight: 700,
          color: isActive ? (groupColor !== "transparent" ? groupColor : C.primary) : C.textMuted,
          cursor: "pointer", userSelect: "none", padding: "0 4px",
          letterSpacing: 0.5, fontFamily: FONT.sans,
          whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
          flex: 1,
        }}>
        {col.label}{arrow}
      </div>
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
      <div style={{ width: `${Math.min(Math.max(value, 0), 100)}%`, height: "100%", background: color || C.gaugeBar, borderRadius: 1 }} />
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
        borderRadius: 6, color: C.textPri, fontFamily: FONT.sans,
        outline: "none",
      }} />
  );
}

function FSelect({ value, onChange, options }) {
  return (
    <select value={value} onChange={e => onChange(e.target.value)}
      style={{
        padding: "5px 8px", fontSize: 11,
        background: C.bgDark, border: `1px solid ${C.border}`,
        borderRadius: 6, color: C.textPri, fontFamily: FONT.sans,
        outline: "none", cursor: "pointer",
      }}>
      {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
}