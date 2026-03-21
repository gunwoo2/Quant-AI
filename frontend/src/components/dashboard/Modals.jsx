/**
 * Modals.jsx — v2 (백엔드 API 연결)
 *
 * AddTickerModal  → POST /api/ticker { ticker }
 * DeleteConfirmModal → 삭제 실행은 StockTable에서 (onConfirm 콜백)
 */

import { useState } from "react";
import { C, FONT } from "../../styles/tokens";
import api from "../../api";

/* ── ADD TICKER MODAL ───────────────────────────── */
export function AddTickerModal({ onClose, onAdd }) {
  const [ticker,   setTicker]   = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [progress, setProgress] = useState("");
  const [error,    setError]    = useState("");

  const handleAdd = async () => {
    const val = ticker.trim().toUpperCase();
    if (!val) { setError("티커를 입력해주세요."); return; }

    setIsSaving(true);
    setProgress("서버에 요청 중...");
    setError("");

    try {
      const res = await api.post("/api/ticker", { ticker: val });

      if (res.data?.success) {
        setProgress("✓ 추가 완료!");
        setTimeout(() => { onAdd?.(val); onClose?.(); }, 800);
      } else {
        setError(res.data?.error ?? "추가에 실패했습니다.");
        setIsSaving(false);
        setProgress("");
      }
    } catch (e) {
      const msg =
        e.response?.data?.detail ??
        e.response?.data?.error  ??
        e.message ??
        "오류가 발생했습니다.";
      setError(msg);
      setIsSaving(false);
      setProgress("");
    }
  };

  return (
    <Overlay onBgClick={() => !isSaving && onClose?.()}>
      <ModalBox title="+ ADD TICKER" onClose={() => !isSaving && onClose?.()}>
        <p style={{ fontFamily: FONT.sans, fontSize: 13, color: C.textGray, marginBottom: 20 }}>
          분석할 주식의 티커를 입력하세요.
          <br />
          <span style={{ fontSize: 11, color: C.textMuted }}>예: AAPL, NVDA, MSFT, 005930.KS</span>
        </p>

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
            borderColor: error ? C.down : C.border,
            color: C.cyan, letterSpacing: 2,
            fontFamily: FONT.mono, fontSize: 15, fontWeight: 700,
          }}
        />

        <p style={{ fontFamily: FONT.sans, fontSize: 11, color: C.textMuted, marginTop: 8 }}>
          섹터·거래소는 yfinance가 자동으로 판별합니다.
        </p>

        {error && (
          <p style={{ fontFamily: FONT.sans, fontSize: 12, color: C.down, marginTop: 8 }}>⚠ {error}</p>
        )}

        {isSaving && progress && (
          <div style={{
            marginTop: 12, padding: "10px 14px",
            background: C.bgDeeper, border: `1px solid ${C.border}`,
            borderRadius: 4, fontFamily: FONT.sans, fontSize: 11, color: C.primary,
          }}>
            ⟳ {progress}
          </div>
        )}

        <div style={{ display: "flex", gap: 10, marginTop: 24 }}>
          <button onClick={() => !isSaving && onClose?.()} disabled={isSaving} style={secondaryBtn}>취소</button>
          <button
            onClick={handleAdd} disabled={isSaving}
            style={{ ...primaryBtn, opacity: isSaving ? 0.7 : 1, cursor: isSaving ? "not-allowed" : "pointer" }}
          >
            {isSaving ? (progress || "처리 중...") : "저장하기"}
          </button>
        </div>
      </ModalBox>
    </Overlay>
  );
}

/* ── DELETE CONFIRM MODAL ───────────────────────── */
export function DeleteConfirmModal({ tickers, onClose, onConfirm, isLoading }) {
  const [confirmText, setConfirmText] = useState("");
  const canDelete = confirmText === "DELETE" && !isLoading;

  return (
    <Overlay onBgClick={!isLoading ? onClose : undefined}>
      <ModalBox title="⚠ 티커 삭제 경고" onClose={!isLoading ? onClose : undefined} danger>
        <div style={{
          background: `${C.down}12`, border: `1px solid ${C.down}60`,
          borderRadius: 4, padding: "14px 16px", marginBottom: 16,
        }}>
          <p style={{ fontFamily: FONT.sans, fontSize: 13, color: C.down, fontWeight: 700, marginBottom: 8 }}>
            이 작업은 되돌릴 수 없습니다!
          </p>
          <ul style={{ fontFamily: FONT.sans, fontSize: 12, color: C.textGray, paddingLeft: 16, margin: 0, lineHeight: 1.8 }}>
            <li>선택한 <strong style={{ color: C.textPri }}>{tickers.length}개 종목</strong>이 비활성화됩니다.</li>
            <li>가격 이력 및 퀀트 점수는 <strong style={{ color: C.cyan }}>보존</strong>됩니다.</li>
            <li>재추가 시 기존 데이터를 재사용합니다.</li>
          </ul>
        </div>

        <p style={{ fontFamily: FONT.sans, fontSize: 11, color: C.textMuted, marginBottom: 6 }}>삭제 대상:</p>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 20, maxHeight: 80, overflowY: "auto" }}>
          {tickers.map(t => (
            <span key={t} style={{
              fontFamily: FONT.sans, fontSize: 11, color: C.primary,
              background: `${C.primary}15`, border: `1px solid ${C.primary}40`,
              borderRadius: 3, padding: "2px 8px",
            }}>{t}</span>
          ))}
        </div>

        <p style={{ fontFamily: FONT.sans, fontSize: 12, color: C.textGray, marginBottom: 8 }}>
          삭제하려면 아래에 <strong style={{ color: C.down, letterSpacing: 1 }}>DELETE</strong>를 입력하세요.
        </p>
        <input
          autoFocus value={confirmText}
          onChange={e => setConfirmText(e.target.value)}
          placeholder="DELETE" disabled={isLoading}
          style={{
            ...inputStyle, fontFamily: FONT.mono, fontSize: 14,
            letterSpacing: 2, textAlign: "center",
            borderColor: canDelete ? C.down : C.border,
            color: canDelete ? C.down : C.textGray,
          }}
        />

        <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
          <button onClick={onClose} disabled={isLoading} style={secondaryBtn}>취소</button>
          <button
            onClick={() => canDelete && onConfirm?.()}
            disabled={!canDelete}
            style={{ ...dangerBtn, opacity: canDelete ? 1 : 0.4, cursor: canDelete ? "pointer" : "not-allowed" }}
          >
            {isLoading ? "삭제 중..." : `${tickers.length}개 종목 영구삭제`}
          </button>
        </div>
      </ModalBox>
    </Overlay>
  );
}

/* ── 공용 컴포넌트 */
function Overlay({ children, onBgClick }) {
  return (
    <div
      onClick={e => e.target === e.currentTarget && onBgClick?.()}
      style={{
        position: "fixed", inset: 0,
        background: "rgba(0,0,0,0.82)", backdropFilter: "blur(4px)",
        display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000,
      }}
    >{children}</div>
  );
}

function ModalBox({ children, title, onClose, danger }) {
  return (
    <div style={{
      background: "#111",
      border: `1px solid ${danger ? C.down + "60" : C.border}`,
      borderRadius: 8, width: 440, maxWidth: "92vw",
      padding: "22px 26px",
      boxShadow: danger ? `0 0 40px ${C.down}20` : "0 20px 60px rgba(0,0,0,0.8)",
    }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 18 }}>
        <span style={{ fontFamily: FONT.sans, fontSize: 13, fontWeight: 700, color: danger ? C.down : C.primary, letterSpacing: 0.5 }}>
          {title}
        </span>
        {onClose && (
          <button onClick={onClose} style={{ background: "none", border: "none", color: C.textMuted, cursor: "pointer", fontSize: 16, padding: 4 }}>✕</button>
        )}
      </div>
      {children}
    </div>
  );
}

const inputStyle = {
  width: "100%", padding: "10px 13px", marginTop: 6,
  background: "#0f0f0f", border: `1px solid ${C.border}`,
  color: C.textPri, borderRadius: 4, outline: "none",
  fontSize: 13, boxSizing: "border-box", fontFamily: "'Inter', sans-serif",
};
const labelStyle = {
  fontFamily: FONT.sans, fontSize: 10, fontWeight: 700,
  color: C.primary, letterSpacing: 1, display: "block",
};
const primaryBtn = {
  flex: 1, fontFamily: FONT.sans, fontSize: 12, fontWeight: 700,
  letterSpacing: 0.5, background: C.primary, color: "#fff",
  border: "none", borderRadius: 4, padding: "10px 16px",
};
const secondaryBtn = {
  fontFamily: FONT.sans, fontSize: 12, color: C.textGray,
  background: "none", border: `1px solid ${C.border}`,
  borderRadius: 4, padding: "10px 16px", cursor: "pointer",
};
const dangerBtn = {
  flex: 1, fontFamily: FONT.sans, fontSize: 12, fontWeight: 700,
  background: C.down, color: "#fff", border: "none",
  borderRadius: 4, padding: "10px 16px",
};