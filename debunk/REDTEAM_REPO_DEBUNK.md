# Red‑Team Debunk (M5/M15 Rule‑Based MOM + Guardrail)

Date: 2026-02-07  
Scope: `docs/STRATEGY_MASTER_MANUAL.md` and M5/M15 rule‑based pipeline only.  
Method: **Code/logic review + small focused checks** (no full dataset rebuilds).

## Executive Summary (Red‑Team)
The current strategy is **rule‑based MOM** with a **mandatory loss‑streak guardrail**. It is **not market‑neutral** in implementation because PnL is realized on a **single active leg**, while entries/exits are driven by a **spread Z‑score**. This mismatch is inherent to the design and must be accepted explicitly: the strategy is a **directional single‑leg trade conditioned on a spread signal**, not a hedged pair trade.

The guardrail is correctly implemented and materially reduces drawdown. However, the same fundamental mismatch remains: **spread‑based exits can be triggered by the non‑active leg**, causing outcomes that may not align with the active‑leg return.

## Key Findings (Critical / High)

### 1) The strategy is directional single‑leg, not market‑neutral
**Where:** dataset builders and guardrail diagnostics

**What the code does:**
- Active leg is selected by beta band (Y if beta<0.98, X if beta>1.02).
- PnL is computed on **active leg only**, not a hedged spread.

**Why this matters:**
- This is **not a market‑neutral spread strategy** in execution.
- Any claims of neutral hedged PnL are incorrect.

### 2) Z‑score exits can be driven by the non‑active leg
**Where:** Z‑score logic in builders vs PnL computation

**What the code does:**
- Entry/exit triggers use spread Z‑score.
- PnL uses only the active leg.

**Why this matters:**
- A Z‑exit can be triggered even when the active leg is flat.
- This creates a structural mismatch between **signal basis** and **P&L basis**.

### 3) Guardrail is mandatory and correctly causal
**Where:** `scripts/report_mom_guardrail_diagnostics.py`

**What the code does:**
- Loss‑streak >= 3 triggers a 14‑day pause per symbol.
- State is updated sequentially and uses only past trades.

**Why this matters:**
- This is the primary DD control and is implemented correctly.
- However, it does not solve the spread vs single‑leg mismatch.

## Medium / Structural Risks

### A) Strategy depends on beta band thresholds
If beta stays in the neutral band (0.98–1.02), the system does nothing. This introduces **sampling bias** and can leave some pairs largely inactive.

### B) Multiple copies of constants across scripts
Thresholds (1.5, 3.5, 500 bars, 20‑bar gap) are duplicated in multiple files. This increases risk of silent divergence.

### C) Guardrail is defined in analysis scripts, not in a live execution module
There is still no dedicated runtime inference/exec module for M5/M15 with guardrail enforcement. The manual is consistent with the analysis scripts, but **runtime integration** remains a risk.

## What Looks Correct (Green)
- Z‑score computation is **causal** (rolling 500‑bar window, no forward look).
- Guardrail logic is **causal** and matches manual semantics.
- Manual now correctly states **no ML/CatBoost usage**.

## Bottom Line (Red‑Team)
The strategy is **directional single‑leg MOM** with a **spread‑based signal** and a **guardrail**. It is **not hedged** or market‑neutral. The guardrail materially reduces drawdown and is implemented correctly, but the signal/PnL mismatch remains a core design risk.

## Recommended Next Attacks (If You Want to Harden It)
1. **Hedged PnL variant**: compute PnL on a beta‑hedged spread and compare outcomes.
2. **Signal/PnL alignment test**: quantify how often Z‑exits are driven by the non‑active leg.
3. **Centralize constants**: move thresholds into one config to prevent drift.
4. **Runtime enforcement**: implement a single production inference layer that enforces guardrails.

## Evidence & References
- Manual: `docs/STRATEGY_MASTER_MANUAL.md`
- Guardrail logic: `scripts/report_mom_guardrail_diagnostics.py`
- Guardrail WFO summary: `docs/analysis/mom_loss_limiter_wfo.md`
- Guardrail outputs (M5/M15):
  - `data/analysis/m5_guardrail_*`
  - `data/analysis/m15_guardrail_*`

**Status:** Updated and aligned with rule‑based MOM strategy.
