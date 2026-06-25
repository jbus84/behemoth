# Path-Geometry Phase B — Timeframe Pre-screen + Geometry Optimization — Design

Date: 2026-06-21
Status: Design (approved in brainstorming, pending spec review)
Parent: `2026-06-21-conditional-path-geometry-design.md` (Phase B realizes its §2c/§3/§4
  for the gate-1-surviving timeframes)
Scope: FX research — execution geometry for the 2h momentum tail-long edge, and a cheap
  pre-screen of whether the same lever opens 1h/3h/4h.

---

## 1. Motivation & where this sits

Phase A (gate 1) found the 2h tail-long edge's conditional path distribution differs from a
random-offset placebo **specifically in adverse excursion (mae)** — entries draw down less than
the null — while the right tail (mfe) is unchanged. That points at a **stop-loss** lever, not a
take-profit. The 2-3d reversion edge did not shift (STOP). Phase B turns that into a decision:
does an optimized stop (or any bracket geometry) actually beat the fixed-horizon baseline net of
cost, and does the same lever open up adjacent timeframes (1h/3h/4h) that were never validated?

**User decision (brainstorm):** *gate-1 pre-screen across 1h/2h/3h/4h first; only SHIFTED
timeframes enter geometry optimization* — controls the forking-paths surface and reuses the
cheap engine. A stop can only rescue a timeframe that already has a gross edge eaten by its left
tail; it cannot manufacture profit from noise, so a non-shifting timeframe is dropped.

---

## 2. Architecture — two sequenced stages, one plan

### Stage B0 — Timeframe pre-screen (cheap, runs first)
Run the existing Phase-A `gate_one_edge` for tail-long across `{1h, 2h, 3h, 4h}` (each with its
offset-placebo null and ±1–3 bar robustness probe, n_bars=1). Output: the set of **SHIFTED
timeframes** (gate-1 criterion: a metric clears KS and the clustered null at Bonferroni/3).
2h is known to shift; this reveals whether 1h/3h/4h join. Everything downstream operates only
on the surviving set. **A SHIFT is necessary, not sufficient** — survivors still must clear
gates 2–3; the pre-screen prunes, it does not promote.

### Stage B1 — Bracket evaluator
For one entry's 1-minute path (anchored at the signal bar's CLOSE mid), walk forward in σ-units.
Given geometry `(stop = s·σ, take_profit = tp·σ, max_hold = H bars)`, exit at the **first**
minute the signed move crosses `−s` (stop) or `+tp` (TP); else exit at `H`. Per-minute data is
mid only, so a single-minute gap straddling both levels resolves **stop-first** (conservative).
Returns realized net bps after `reg_signal_hunt.COST_BPS[sym]` (one round-trip). Reuses
`path_geometry_paths.hold_path` and the bar-close-mid anchor from `path_ensemble`. Unit-tested
on synthetic paths with known crossings (stop hit, TP hit, neither → max-hold, straddle →
stop-first).

### Stage B1 — Geometry optimizer (causal, reuses ridge WFO folds)
Grid (coarse — DOF discipline):
- `stop ∈ {none, 1σ, 1.5σ, 2σ, 3σ}`
- `take_profit ∈ {none, 2σ, 3σ, 4σ}`
- `max_hold ∈ {native, 2×native}`

The `(none, none, native)` cell **is** the fixed-horizon baseline every cell must beat. TP
remains in the grid as a **falsification check**: gate-1 showed mfe is not shifted, so TP is
expected not to help; an optimizer that crowns a tight TP is an overfit red flag, not a win.

Causal selection: within each expanding `tail_wfo.walk_forward` fold, pick the best geometry
cell by net bps on the **train** trades, apply that one cell to the **test** trades; concatenate
test results across folds → a fully OOS, causally-selected geometry track per (pair, TF).
Pool across pairs for power.

---

## 3. Decision metric, gates 2–3, multiplicity

**Gate 2 — geometry beats baseline.** For each surviving (pair, TF), the OOS causally-selected
geometry track vs the `(none,none,native)` baseline, net of cost:
- **day-clustered t**, **year-block bootstrap 95% CI clearing zero**, **positive-years**,
  **pooled across pairs**. Reported as baseline → best-OOS cell, isolating the marginal lift.

**Gate 3 — null + multiplicity.**
- **Offset-placebo null:** run the *entire* select-on-train / apply-on-test optimizer on
  placebo entries; it must NOT beat baseline (guards against the optimizer being an overfit
  knob).
- **BH-FDR across the full {TF × geometry-cell} grid:** selected survivors must clear it.

GO requires gate 2 AND gate 3.

**Rigor upgrades (from the Phase-A review, mandatory here):**
- Significance and nulls use a **day/block-clustered resample**, NOT IID permutation
  (overlapping/clustered holds violate exchangeability; IID understates variance).
- Report the deciding metric's (mae / net) **jitter curve** (±1–3 bars) so the knife-edge
  entry-timing sensitivity stays visible in the results doc.

---

## 4. Honest expected outcome

Gate-1 located the shift in adverse excursion, so the stop is the only lever with a real prior —
and even it faces a headwind: the 2h edge's net lives in the big winning moves, and a stop also
clips winners that dipped first. The genuinely likely outcomes:
1. a modest-σ stop (≈2–3σ) gives a small net lift by truncating the worst losers without
   clipping many winners — a real, deployable refinement; or
2. **no cell beats baseline** — every left-tail-helping stop clips enough winners to wash out;
   combined with the Phase-1 dynamic-exit NO-GO, this would be a decisive "the 2h edge is
   hold-to-horizon, no geometry" verdict.
TP is expected to fail by construction (falsification check). Either outcome is clean and
recorded.

---

## 5. Phasing & reuse

- **B0** pre-screen → decide surviving timeframes.
- **B1** bracket evaluator (unit-tested) → optimizer (causal WFO) → gates 2–3 on survivors →
  `path_geometry_results.md`.
New modules in the `fx-path-geometry` worktree: `path_bracket.py` (evaluator),
`path_geometry_opt.py` (optimizer + gates + CLI). Reuses Phase-A `path_geometry_paths`,
`path_ensemble`, `path_metrics`, `path_shift_gate`, and `tail_wfo.walk_forward` /
`day_clustered_tstat`, plus the year-block bootstrap from Phase-A's gate.

---

## 6. Out of scope (YAGNI)

- The 2-3d reversion edge (gate-1 STOP — not carried into geometry).
- Take-profit as a *primary* lever (kept only as a falsification check).
- Simulator/bootstrap path augmentation (parent spec Phase C — only if survivor tails are too
  thin to estimate geometry).
- Sub-minute / true tick-exact bracket ordering (1-minute mid + conservative stop-first
  tie-break; revisit only if a GO survives).
- Position sizing (parent spec mentions it; deferred — geometry first, sizing is a later lever).
- New instruments beyond the six majors.
