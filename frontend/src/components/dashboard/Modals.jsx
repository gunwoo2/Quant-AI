/**
 * AddTickerModal.jsx
 * 티커 추가 팝업 (현행 스타일 유지 + 색상 토큰 반영)
 */

import { useState } from "react";
import { C, FONT } from "../../styles/tokens";

export function AddTickerModal({ onClose, onAdd }) {
  const [ticker, setTicker] = useState("");
  const [error,  setError]  = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async () => {
    const val = ticker.trim().toUpperCase();
    if (!val) { setError("티커를 입력해주세요."); return; }
    if (!/^[A-Z]{1,5}$/.test(val)) { setError("올바른 티커 형식이 아닙니다. (예: AAPL)"); return; }

    setLoading(true);
    setError("");
    // 실제 구현: API 호출 후 onAdd(val) 호출
    setTimeout(() => {
      setLoading(false);
      onAdd?.(val);
      onClose?.();
    }, 800);
  };

  return (
    <Overlay>
      <ModalBox title="티커 추가" onClose={onClose}>
        <p style={{ fontFamily: FONT.sans, fontSize: 13, color: C.textGray, marginBottom: 16 }}>
          추가할 종목의 티커 심볼을 입력하세요.
          <br />
          <span style={{ fontSize: 11, color: C.textMuted }}>
            예: AAPL, NVDA, MSFT, 005930 (삼성전자)
          </span>
        </p>

        <input
          autoFocus
          value={ticker}
          onChange={e => { setTicker(e.target.value.toUpperCase()); setError(""); }}
          onKeyDown={e => e.key === "Enter" && handleSubmit()}
          placeholder="TICKER"
          style={{
            fontFamily: FONT.mono,
            fontSize: 16,
            fontWeight: 700,
            letterSpacing: 2,
            width: "100%",
            background: C.bgDark,
            border: `1px solid ${error ? C.red : C.border}`,
            borderRadius: 4,
            padding: "10px 14px",
            color: C.cyan,
            outline: "none",
            marginBottom: 8,
            boxSizing: "border-box",
          }}
        />

        {error && (
          <p style={{ fontFamily: FONT.sans, fontSize: 12, color: C.red, marginBottom: 12 }}>
            ⚠ {error}
          </p>
        )}

        <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
          <button onClick={onClose} style={secondaryBtn}>취소</button>
          <button
            onClick={handleSubmit}
            disabled={loading}
            style={{ ...primaryBtn, opacity: loading ? 0.6 : 1 }}
          >
            {loading ? "추가 중..." : "+ 티커 추가"}
          </button>
        </div>
      </ModalBox>
    </Overlay>
  );
}

/**
 * DeleteConfirmModal.jsx
 * 티커 삭제 강력 경고 팝업
 */
export function DeleteConfirmModal({ tickers, onClose, onConfirm }) {
  const [confirmText, setConfirmText] = useState("");
  const required = "DELETE";
  const canDelete = confirmText === required;

  return (
    <Overlay>
      <ModalBox title="⚠ 티커 삭제 경고" onClose={onClose} danger>
        {/* 경고 박스 */}
        <div style={{
          background: `${C.red}12`,
          border: `1px solid ${C.red}60`,
          borderRadius: 4,
          padding: "12px 16px",
          marginBottom: 16,
        }}>
          <p style={{ fontFamily: FONT.sans, fontSize: 13, color: C.red, fontWeight: 600, marginBottom: 8 }}>
            이 작업은 되돌릴 수 없습니다!
          </p>
          <ul style={{ fontFamily: FONT.sans, fontSize: 12, color: C.textGray, paddingLeft: 16, margin: 0 }}>
            <li>선택한 {tickers.length}개 종목의 <strong style={{ color: C.textPri }}>ticker_header 레코드가 삭제</strong>됩니다.</li>
            <li>가격 이력(ticker_item)과 퀀트 점수(stock_quant_analysis)는 <strong style={{ color: "#4ade80" }}>보존됩니다.</strong></li>
            <li>나중에 같은 티커를 재추가하면 기존 데이터를 재사용합니다.</li>
          </ul>
        </div>

        {/* 삭제 대상 */}
        <p style={{ fontFamily: FONT.mono, fontSize: 11, color: C.textMuted, marginBottom: 6 }}>
          삭제 대상:
        </p>
        <div style={{
          display: "flex",
          flexWrap: "wrap",
          gap: 6,
          marginBottom: 20,
          maxHeight: 80,
          overflowY: "auto",
        }}>
          {tickers.map(t => (
            <span key={t} style={{
              fontFamily: FONT.mono,
              fontSize: 11,
              color: C.orange,
              background: `${C.orange}15`,
              border: `1px solid ${C.orange}40`,
              borderRadius: 3,
              padding: "2px 8px",
            }}>
              {t}
            </span>
          ))}
        </div>

        {/* 확인 입력 */}
        <p style={{ fontFamily: FONT.sans, fontSize: 12, color: C.textGray, marginBottom: 8 }}>
          삭제하려면 아래 입력창에 <strong style={{ color: C.red, letterSpacing: 1 }}>DELETE</strong> 를 입력하세요.
        </p>
        <input
          autoFocus
          value={confirmText}
          onChange={e => setConfirmText(e.target.value)}
          placeholder="DELETE"
          style={{
            fontFamily: FONT.mono,
            fontSize: 14,
            letterSpacing: 2,
            width: "100%",
            background: C.bgDark,
            border: `1px solid ${canDelete ? C.red : C.border}`,
            borderRadius: 4,
            padding: "8px 12px",
            color: canDelete ? C.red : C.textGray,
            outline: "none",
            marginBottom: 16,
            boxSizing: "border-box",
          }}
        />

        <div style={{ display: "flex", gap: 10 }}>
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
            {tickers.length}개 종목 삭제
          </button>
        </div>
      </ModalBox>
    </Overlay>
  );
}

// ── 공용 레이아웃 컴포넌트
function Overlay({ children }) {
  return (
    <div style={{
      position: "fixed",
      inset: 0,
      background: "rgba(0,0,0,0.75)",
      backdropFilter: "blur(4px)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      zIndex: 1000,
    }}>
      {children}
    </div>
  );
}

function ModalBox({ children, title, onClose, danger }) {
  return (
    <div style={{
      background: "#111",
      border: `1px solid ${danger ? C.red + "60" : C.border}`,
      borderRadius: 6,
      width: 440,
      maxWidth: "90vw",
      padding: "20px 24px",
      position: "relative",
    }}>
      <div style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        marginBottom: 16,
      }}>
        <span style={{
          fontFamily: FONT.mono,
          fontSize: 13,
          fontWeight: 700,
          color: danger ? C.red : C.cyan,
          letterSpacing: 0.5,
        }}>
          {title}
        </span>
        <button
          onClick={onClose}
          style={{
            background: "none",
            border: "none",
            color: C.textMuted,
            cursor: "pointer",
            fontSize: 16,
            padding: 4,
          }}
        >
          ✕
        </button>
      </div>
      {children}
    </div>
  );
}

// ── 버튼 스타일
const primaryBtn = {
  flex: 1,
  fontFamily: FONT.mono,
  fontSize: 12,
  fontWeight: 700,
  letterSpacing: 0.5,
  background: C.orange,
  color: "#fff",
  border: "none",
  borderRadius: 4,
  padding: "9px 16px",
  cursor: "pointer",
};

const secondaryBtn = {
  fontFamily: FONT.mono,
  fontSize: 12,
  color: C.textGray,
  background: "none",
  border: `1px solid ${C.border}`,
  borderRadius: 4,
  padding: "9px 16px",
  cursor: "pointer",
};

const dangerBtn = {
  flex: 1,
  fontFamily: FONT.mono,
  fontSize: 12,
  fontWeight: 700,
  background: C.red,
  color: "#fff",
  border: "none",
  borderRadius: 4,
  padding: "9px 16px",
};