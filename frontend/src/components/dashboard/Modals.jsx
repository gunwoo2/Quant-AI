/**
 * Modals.jsx
 * AddTickerModal — SSE 스트리밍 실제 로직 포함 (Header.jsx 참고)
 * DeleteConfirmModal — 강력 경고, DELETE 타이핑 확인
 * 버그픽스: C.orange → C.primary
 */

import { useState, useEffect } from "react";
import { C, FONT, SECTORS } from "../../styles/tokens";
import api from "../../api";

/* ─────────────────────────────────────────────────
   ADD TICKER MODAL
───────────────────────────────────────────────── */
export function AddTickerModal({ onClose, onAdd }) {
  const [ticker,   setTicker]   = useState("");
  const [sector,   setSector]   = useState("");
  const [sectors,  setSectors]  = useState([]);
  const [isSaving, setIsSaving] = useState(false);
  const [streamMsg,setStreamMsg]= useState("");
  const [error,    setError]    = useState("");

  // 섹터 목록 로드
  useEffect(() => {
    api.get("/api/sectors")
      .then(res => {
        if (Array.isArray(res.data) && res.data.length > 0) {
          setSectors(res.data);
          const first = res.data[0];
          const firstId = String(first.id || first).replace(/[^a-zA-Z]/g, "").toLowerCase();
          setSector(firstId);
        }
      })
      .catch(() => {
        // fallback: tokens.js의 SECTORS 사용
        setSectors(SECTORS.map(s => ({ id: s.key, ko: s.label })));
        setSector(SECTORS[0]?.key || "");
      });
  }, []);

  const handleAdd = async () => {
    const val = ticker.trim().toUpperCase();
    if (!val) { setError("티커를 입력해주세요."); return; }

    setIsSaving(true);
    setStreamMsg("연결 중...");
    setError("");

    try {
      let country = "US";
      if (val.endsWith(".KS") || val.endsWith(".KQ")) country = "KR";

      const response = await fetch("/api/add-ticker-stream/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker: val, sector, country }),
      });

      const reader  = response.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value);
        for (const line of chunk.split("\n\n")) {
          if (!line.startsWith("data: ")) continue;
          try {
            const data = JSON.parse(line.replace("data: ", ""));
            setStreamMsg(data.message || "");
            if (data.status === "success") {
              alert("성공적으로 추가되었습니다!");
              onAdd?.(val);
              onClose?.();
              window.location.reload();
              return;
            }
            if (data.status === "error") {
              setError(data.message || "오류가 발생했습니다.");
              setIsSaving(false);
              setStreamMsg("");
              return;
            }
          } catch {}
        }
      }
    } catch (e) {
      setError(e.message || "오류가 발생했습니다.");
      setStreamMsg("");
      setIsSaving(false);
    }
  };

  return (
    <Overlay onBgClick={() => !isSaving && onClose?.()}>
      <ModalBox title="+ ADD TICKER" onClose={() => !isSaving && onClose?.()}>
        <p style={{ fontFamily: FONT.sans, fontSize: 13, color: C.textGray, marginBottom: 20 }}>
          분석할 주식의 티커를 입력하고 섹터를 지정하세요.
          <br />
          <span style={{ fontSize: 11, color: C.textMuted }}>예: AAPL, NVDA, MSFT, 005930.KS</span>
        </p>

        {/* TICKER 입력 */}
        <label style={labelStyle}>TICKER SYMBOL</label>
        <input
          autoFocus
          value={ticker}
          onChange={e => { setTicker(e.target.value.toUpperCase()); setError(""); }}
          onKeyDown={e => e.key === "Enter" && !isSaving && handleAdd()}
          placeholder="예: NVDA, 005930.KS"
          disabled={isSaving}
          style={{
            ...inputStyle,
            borderColor: error ? C.red : C.border,
            color: C.cyan,
            letterSpacing: 2,
            fontFamily: FONT.mono,
            fontSize: 15,
            fontWeight: 700,
          }}
        />

        {/* SECTOR 선택 */}
        <label style={{ ...labelStyle, marginTop: 16 }}>SELECT SECTOR</label>
        <select
          value={sector}
          onChange={e => setSector(e.target.value)}
          disabled={isSaving}
          style={{ ...inputStyle, cursor: "pointer" }}
        >
          {sectors.map((opt, idx) => {
            const raw  = opt.id || opt;
            const sId  = String(raw).replace(/[^a-zA-Z]/g, "").toLowerCase();
            const sKo  = String(opt.ko || opt.label || raw)
              .replace(/[a-zA-Z()']/g, "").replace(/,/g, "").trim();
            return (
              <option key={sId + idx} value={sId} style={{ background: "#1a1a1a" }}>
                {sKo || sId.toUpperCase()} ({sId.toUpperCase()})
              </option>
            );
          })}
        </select>

        {/* 에러 메시지 */}
        {error && (
          <p style={{ fontFamily: FONT.sans, fontSize: 12, color: C.red, marginTop: 8 }}>
            ⚠ {error}
          </p>
        )}

        {/* 스트리밍 상태 */}
        {isSaving && streamMsg && (
          <div style={{
            marginTop: 12, padding: "10px 14px",
            background: "#0a0a0a", border: `1px solid ${C.border}`,
            borderRadius: 4, fontFamily: FONT.mono,
            fontSize: 11, color: C.primary,
          }}>
            ⟳ {streamMsg}
          </div>
        )}

        {/* 버튼 */}
        <div style={{ display: "flex", gap: 10, marginTop: 24 }}>
          <button
            onClick={() => !isSaving && onClose?.()}
            disabled={isSaving}
            style={secondaryBtn}
          >
            취소
          </button>
          <button
            onClick={handleAdd}
            disabled={isSaving}
            style={{ ...primaryBtn, opacity: isSaving ? 0.7 : 1, cursor: isSaving ? "not-allowed" : "pointer" }}
          >
            {isSaving ? (streamMsg || "분석 중...") : "저장하기"}
          </button>
        </div>
      </ModalBox>
    </Overlay>
  );
}

/* ─────────────────────────────────────────────────
   DELETE CONFIRM MODAL
───────────────────────────────────────────────── */
export function DeleteConfirmModal({ tickers, onClose, onConfirm }) {
  const [confirmText, setConfirmText] = useState("");
  const required  = "DELETE";
  const canDelete = confirmText === required;

  return (
    <Overlay onBgClick={onClose}>
      <ModalBox title="⚠ 티커 삭제 경고" onClose={onClose} danger>
        {/* 경고 박스 */}
        <div style={{
          background: `${C.red}12`,
          border: `1px solid ${C.red}60`,
          borderRadius: 4, padding: "14px 16px", marginBottom: 16,
        }}>
          <p style={{ fontFamily: FONT.sans, fontSize: 13, color: C.red, fontWeight: 700, marginBottom: 8 }}>
            이 작업은 되돌릴 수 없습니다!
          </p>
          <ul style={{ fontFamily: FONT.sans, fontSize: 12, color: C.textGray, paddingLeft: 16, margin: 0, lineHeight: 1.8 }}>
            <li>선택한 <strong style={{ color: C.textPri }}>{tickers.length}개 종목</strong>의 ticker_header 레코드가 삭제됩니다.</li>
            <li>가격 이력(ticker_item)과 퀀트 점수는 <strong style={{ color: "#00F5FF" }}>보존</strong>됩니다.</li>
            <li>재추가 시 기존 데이터를 재사용합니다.</li>
          </ul>
        </div>

        {/* 삭제 대상 티커 */}
        <p style={{ fontFamily: FONT.mono, fontSize: 11, color: C.textMuted, marginBottom: 6 }}>삭제 대상:</p>
        <div style={{
          display: "flex", flexWrap: "wrap", gap: 6,
          marginBottom: 20, maxHeight: 80, overflowY: "auto",
        }}>
          {tickers.map(t => (
            <span key={t} style={{
              fontFamily: FONT.mono, fontSize: 11, color: C.primary,
              background: `${C.primary}15`, border: `1px solid ${C.primary}40`,
              borderRadius: 3, padding: "2px 8px",
            }}>
              {t}
            </span>
          ))}
        </div>

        {/* 확인 입력 */}
        <p style={{ fontFamily: FONT.sans, fontSize: 12, color: C.textGray, marginBottom: 8 }}>
          삭제하려면 아래에{" "}
          <strong style={{ color: C.red, letterSpacing: 1 }}>DELETE</strong>를 입력하세요.
        </p>
        <input
          autoFocus
          value={confirmText}
          onChange={e => setConfirmText(e.target.value)}
          placeholder="DELETE"
          style={{
            ...inputStyle,
            fontFamily: FONT.mono, fontSize: 14, letterSpacing: 2,
            borderColor: canDelete ? C.red : C.border,
            color: canDelete ? C.red : C.textGray,
            textAlign: "center",
          }}
        />

        <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
          <button onClick={onClose} style={secondaryBtn}>취소</button>
          <button
            onClick={() => canDelete && onConfirm?.()}
            disabled={!canDelete}
            style={{
              ...dangerBtn,
              opacity: canDelete ? 1 : 0.4,
              cursor: canDelete ? "pointer" : "not-allowed",
            }}
          >
            {tickers.length}개 종목 영구삭제
          </button>
        </div>
      </ModalBox>
    </Overlay>
  );
}

/* ─────────────────────────────────────────────────
   공용 레이아웃 컴포넌트
───────────────────────────────────────────────── */
function Overlay({ children, onBgClick }) {
  return (
    <div
      onClick={e => e.target === e.currentTarget && onBgClick?.()}
      style={{
        position: "fixed", inset: 0,
        background: "rgba(0,0,0,0.82)",
        backdropFilter: "blur(4px)",
        display: "flex", alignItems: "center", justifyContent: "center",
        zIndex: 1000,
      }}
    >
      {children}
    </div>
  );
}

function ModalBox({ children, title, onClose, danger }) {
  return (
    <div style={{
      background: "#111",
      border: `1px solid ${danger ? C.red + "60" : C.border}`,
      borderRadius: 8, width: 440, maxWidth: "92vw",
      padding: "22px 26px", position: "relative",
      boxShadow: danger ? `0 0 40px ${C.red}20` : "0 20px 60px rgba(0,0,0,0.8)",
    }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 18 }}>
        <span style={{
          fontFamily: FONT.mono, fontSize: 13, fontWeight: 700,
          color: danger ? C.red : C.primary, letterSpacing: 0.5,
        }}>
          {title}
        </span>
        <button onClick={onClose} style={{
          background: "none", border: "none", color: C.textMuted,
          cursor: "pointer", fontSize: 16, padding: 4, lineHeight: 1,
        }}>✕</button>
      </div>
      {children}
    </div>
  );
}

/* ─────────────────────────────────────────────────
   공용 스타일
───────────────────────────────────────────────── */
const inputStyle = {
  width: "100%", padding: "10px 13px", marginTop: 6,
  background: "#0f0f0f", border: `1px solid ${C.border}`,
  color: C.textPri, borderRadius: 4, outline: "none",
  fontSize: 13, boxSizing: "border-box",
  fontFamily: "'Inter', sans-serif",
};

const labelStyle = {
  fontFamily: FONT.mono, fontSize: 10, fontWeight: 700,
  color: C.primary, letterSpacing: 1, display: "block",
};

const primaryBtn = {
  flex: 1, fontFamily: FONT.mono, fontSize: 12, fontWeight: 700,
  letterSpacing: 0.5, background: C.primary, color: "#fff",
  border: "none", borderRadius: 4, padding: "10px 16px",
};

const secondaryBtn = {
  fontFamily: FONT.mono, fontSize: 12, color: C.textGray,
  background: "none", border: `1px solid ${C.border}`,
  borderRadius: 4, padding: "10px 16px", cursor: "pointer",
};

const dangerBtn = {
  flex: 1, fontFamily: FONT.mono, fontSize: 12, fontWeight: 700,
  background: C.red, color: "#fff", border: "none",
  borderRadius: 4, padding: "10px 16px",
};