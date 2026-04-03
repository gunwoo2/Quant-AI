"""
batch/set_a_buy_filter_patch.py — SET A-3 BUY 필터 Percentile 전환 패치
========================================================================
이 파일은 batch_trading_signals_v5.py의 BUY 필터 로직을 패치합니다.

적용 방법:
  batch_trading_signals_v5.py에서 아래 코드를 교체하세요.

  === BEFORE (line ~255) ===
    rec.score_filter = final_score >= cfg.buy_score_min
    if not rec.score_filter: ...

  === AFTER ===
    passed, reason = cfg.check_buy_threshold({
        "percentile_rank": stock.get("percentile_rank", 0),
        "grade": stock.get("grade", "D"),
        "final_score": final_score,
    })
    rec.score_filter = passed
    if not rec.score_filter:
        rec.decision = f"SKIP({reason})"
        audit.add(rec)
        continue

  === DD 평가 패치 (line ~163) ===
  BEFORE:
    dd_status = _dd_controller.evaluate(calc_date, account_value, peak_value)
    cfg.apply_dd_override(dd_status.mode.name)
    
  AFTER:
    dd_status = _dd_controller.evaluate(calc_date, account_value, peak_value)
    cfg.apply_dd_override(dd_status.mode.name, current_dd_pct=dd_status.drawdown_pct)
"""
