# Hourly FX flow → direction — Phase 1 results (NO-GO)

**Date:** 2026-06-18  Branch: `fx-coint/hourly-flow-direction`
**Spec:** `docs/superpowers/specs/2026-06-18-hourly-flow-direction-design.md`
**Plan:** `docs/superpowers/plans/2026-06-18-hourly-flow-direction.md`

## Question

Does order-flow (`flow_tick`, `flow_ofi`, engineered cumulative/divergence channels)
give the aeon TS models — or any model — next-k-bar **directional** predictability that
price-only features lack (price-only scored dirAcc ≈ 0.50)?

## Harness integrity

`price_only` control arm stayed at dirAcc ≈ 0.505 (h=1) / 0.511 (h=3) — coin-flip, as it
must. No leakage manufacturing fake edges. The drift-immune rolling-tercile label
(`label_horizon_tercile`, balanced 33/33/33 per month) and pooled block-bootstrap (not
per-window t-stats) are in force throughout.

## Result 1 — dirAcc grid (QUANT, EURUSD 2024, {1,3,6h} × 4 arms)

All cells dirAcc 0.488–0.511 (flat at chance), every arm net-negative after cost. Flow
arms do not beat `price_only`. No cell clears the gate.

## Result 2 — IC needle detector (EURUSD 2024)

Higher-powered: ridge OOS IC of current-bar features vs vol-normalised forward return,
per WFO fold, with sign-stability. Surfaced a **faint short-horizon mean-reversion**
(negative IC at h=3/6, e.g. h=6 price IC −0.050, t −2.8) invisible to dirAcc — BUT it
appeared in `price_only` too (flow added nothing), and nothing survived BH + sign-stability
jointly.

## Result 3 — SCALED IC hunt (6 pairs × 8 years, N≈150k, 288 folds) — DECISIVE

| horizon | arm | mean IC | breadth-t | sign-stab | beats price? |
|--------:|-----|--------:|----------:|----------:|:-----------:|
| 1 | price_only | +0.0105 | +2.99 | 0.58 | — |
| 1 | both | +0.0113 | +2.88 | 0.56 | barely |
| 1 | raw_flow | +0.0061 | +1.64 | 0.48 | no |
| 3 | price_only | −0.0019 | −0.51 | 0.56 | — |
| 6 | price_only | −0.0034 | −0.93 | 0.48 | — |
| (all flow arms, all h) | | ≈0 | <1.7 | ≈0.50 | no |

**Findings:**
1. **The h=3/6 reversion was a false needle.** EURUSD-2024 IC −0.050 (t −2.8) → pooled
   −0.003, breadth-t −0.93, sign-stab 0.48. Collapses under breadth. The single-pair
   signal was noise/year-specific. (Scaling caught the false needle — its purpose.)
2. **Flow carries no independent signal.** Every flow arm breadth-t < 1.7, sign-unstable;
   the orthogonalised divergence channel adds nothing; `both` ≈ `price_only` to 0.0008 IC.
   At N=150k / 288 folds we had power to detect a sign-stable IC ≥ 0.02 trivially — the
   true flow IC is ~0. High-powered NO-GO, not an underpowered shrug.
3. **Only survivor is a non-finding:** h=1 price momentum IC +0.011, breadth-t ≈ 3
   (survives BH on N alone) but **sign-stab 0.58** (≈ coin-flip across slices) and
   **IR ≈ 0.24 gross, pre-cost** vs a 0.64 bps wall. Statistically non-zero at huge N,
   robustly and economically nothing.

## Verdict

**NO-GO.** No flow direction needle at the hourly scale. The reversion lead was noise.
Bars confirmed genuine time-bars (1h truncation of 1-min bars, ≤1min stale) — not the
stale-tick-bar artifact, so the negative result is about the market, not the data.

## Method that worked (keep)

Needle detection = continuous IC (not dirAcc) on a **low-variance ridge** signal +
**vol-normalised target** + **breadth** (pool pairs × years) + **sign-stability across
slices** + BH. Decisive where dirAcc was flat. Fundamental-Law lens: IR = IC·√breadth —
exploit a minute edge via breadth, but only if a sign-stable IC exists. Here it does not.

## Not pursued (Phase 2 gated off)

Cross-sectional flow (pair vs USD basket) was gated on Phase 1 finding a flow edge. Phase
1 is NO-GO, so Phase 2 is not pursued. The scaled IC harness is the tool to reuse if a
future signal candidate appears.
