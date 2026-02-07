# Red‑Team Logic Tests (Rule‑Based MOM + Guardrail)

Date: 2026-02-07  
Scope: M5/M15 rule‑based MOM strategy + loss‑streak guardrail. No full data rebuilds.

## Summary
- **Active‑leg vs Z‑exit alignment**: WARN (exit can be driven by non‑active leg moves).
- **Guardrail causality**: PASS (state uses only past trades).
- **Guardrail semantics**: PASS (loss streak >= 3, 14‑day pause, per symbol).
- **Z‑score causality**: PASS (rolling window, no forward data).
- **Manual parity**: PASS (manual matches code for rule‑based MOM + guardrail).

---

## Active‑leg vs Z‑exit alignment
**Purpose**: Verify whether Z‑score exits (driven by spread) can trigger when the active leg does not move, creating misalignment between signal and PnL.  
**Procedure**: Use synthetic series where Y (active leg) is flat while X moves and pushes Z across exit thresholds; run Z‑exit logic on active‑leg PnL.  
**Result**: Z‑based exit can occur without active‑leg movement.  
**Verdict**: **WARN** (expected by design; indicates single‑leg PnL is only indirectly linked to spread Z).

## Guardrail causality
**Purpose**: Ensure loss‑streak guardrail uses only past trades to pause symbols.  
**Procedure**: Review guardrail logic in `scripts/report_mom_guardrail_diagnostics.py` and verify no lookahead is used.  
**Result**: Guardrail state (loss streak, pause_until) is updated sequentially and applied causally.  
**Verdict**: **PASS**.

## Guardrail semantics
**Purpose**: Verify guardrail definition matches the manual.  
**Procedure**: Compare manual rule with code.  
**Result**: Loss streak >= 3 triggers 14‑day pause per symbol, resets after cooldown.  
**Verdict**: **PASS**.

## Z‑score causality
**Purpose**: Confirm Z‑score window uses only historical data.  
**Procedure**: Inspect `compute_z_scores` in dataset builders and confirm rolling window ends at entry index.  
**Result**: Z‑score computed on rolling 500‑bar window (past only).  
**Verdict**: **PASS**.

## Manual parity
**Purpose**: Ensure manual matches code for rule‑based MOM + guardrail.  
**Procedure**: Compare `docs/STRATEGY_MASTER_MANUAL.md` to M5/M15 builder + guardrail scripts.  
**Result**: Manual aligns with rule‑based entry/exit, active‑leg selection, and guardrail semantics.  
**Verdict**: **PASS**.

