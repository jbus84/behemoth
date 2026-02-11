# Red‑Team Logic Tests (Rule‑Based MOM + Guardrail)

Date: 2026-02-07
Scope: M5/M15 rule‑based MOM strategy + loss‑streak guardrail. No full data rebuilds.

## Summary
- **Outcome alignment (M5)**: WARN (signal/PNL mismatch present)
- **Outcome alignment (M15)**: WARN (signal/PNL mismatch present)
- **Guardrail causality (M5)**: PASS
- **Guardrail causality (M15)**: PASS
- **Z-score causality**: PASS
- **Manual parity**: PASS

---

## Outcome alignment (M5)
**Purpose**: Quantify outcome/PNL alignment (WIN_MOM should be >0, LOSS_REV should be <=0).
**Procedure**: Compute fraction of WIN_MOM with pnl<=0 and LOSS_REV with pnl>0.
**Result**: M5: WIN_MOM<=0 = 2.60%, LOSS_REV>0 = 32.41%.
**Verdict**: WARN (signal/PNL mismatch present)

## Outcome alignment (M15)
**Purpose**: Quantify outcome/PNL alignment (WIN_MOM should be >0, LOSS_REV should be <=0).
**Procedure**: Compute fraction of WIN_MOM with pnl<=0 and LOSS_REV with pnl>0.
**Result**: M15: WIN_MOM<=0 = 2.14%, LOSS_REV>0 = 35.19%.
**Verdict**: WARN (signal/PNL mismatch present)

## Guardrail causality (M5)
**Purpose**: Verify loss-streak guardrail uses only past trades and applies cooldown correctly.
**Procedure**: Apply guardrail sequentially and ensure no kept trade falls inside a pause window.
**Result**: M5: trades kept=34959, skipped=186258 (skip_rate=84.20%), violations=0.
**Verdict**: PASS

## Guardrail causality (M15)
**Purpose**: Verify loss-streak guardrail uses only past trades and applies cooldown correctly.
**Procedure**: Apply guardrail sequentially and ensure no kept trade falls inside a pause window.
**Result**: M15: trades kept=27090, skipped=46539 (skip_rate=63.21%), violations=0.
**Verdict**: PASS

## Z-score causality
**Purpose**: Confirm Z-score uses only past data (rolling window).
**Procedure**: Scan builders for compute_z_scores implementation and verify window uses errors[i-window:i].
**Result**: M5 ok=True, M15 ok=True.
**Verdict**: PASS

## Manual parity
**Purpose**: Ensure manual reflects rule-based MOM + guardrail and no ML usage.
**Procedure**: Search manual for key statements (no ML, loss-streak guardrail).
**Result**: no_ml=True, guardrail=True.
**Verdict**: PASS
