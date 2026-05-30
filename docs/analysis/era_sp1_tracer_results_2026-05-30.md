# ERA SP1 tracer-bullet results (2026-05-30)

First live run of the ERA dispersion-discovery loop (`scripts/era/`), generator
`qwen3-coder-next` via ollama.com, on EURUSD 2000-tick / horizon 3, budget 20,
scored on the validation split (2025-07..10). Evidence run executed by Opus
(not CI).

## Outcome — the loop works end-to-end

- 14 unique candidate programs written by `qwen3-coder-next`, each statically
  validated, sandbox-executed (no `y_fwd` access), and scored by the continuous
  TaskScore. PUCT explored from the `loo_z` root; the four baselines were seeded.
- **A discovered program ranked #1**, beating every hand-written baseline:

  | rank | score (validation) | program |
  |---|---|---|
  | 1 | **−0.0867** | DISCOVERED (corr-clustered robust-z + dispersion-regime tanh gate) |
  | 2 | −0.1063 | graph_laplacian (seed) |
  | 3 | −0.1141 | robust_z (seed) |
  | 4 | −0.1686 | loo_z (seed) |
  | 5+ | ≤ −0.24 | discovered + dispersion_rank (below top 10) |

  The #1 program *recombined* seeded research ideas (correlation-based peer
  clustering + median/MAD robust z + cross-sectional-dispersion regime gating) —
  exactly ERA's intended behaviour.

## Key finding — the harness is missing session/regime gating

Every score is **negative**: forced to trade all 24h with `|residual| ≥ threshold`
as the *only* entry condition, the dispersion signal is net-negative. The known
edge (`dispersion_rank EURUSD asia__k2`, net-LB95 **+1.22**) is **session-specific**
(asia), and the SP1 harness has **no session / time / dispersion-regime gate**, so
that edge is structurally out of reach — programs can shape only the residual, not
when to trade. This matches expectation and is the diagnostic SP1 was meant to
surface.

## SP1.5 — self-gating added; loop goes net-positive and rediscovers the asia edge

Rather than a harness gate-sweep, we exposed causal gate features to the program
(`ctx.hour` per-bar UTC hour, `ctx.dispersion()` per-bar cross-sectional std) and
let programs **self-gate by returning `np.nan` outside chosen bars** (the scorer
already drops non-finite entries). The qwen prompt documents this; two gated
seeds (`loo_z_asia`, `loo_z_highdisp`) were added.

Re-run (EURUSD 2000-tick/h3, budget 30, cache cleared):

- **Best score flipped from −0.0867 (ungated) to +0.1308 (POSITIVE).**
- The #1 program is **gated to `(hour >= 0) & (hour < 6) & high_dispersion(top 40%)`**
  — i.e. **Asia session + high dispersion** — combined with a leave-one-out peer
  z-score and a cubic cross-sectional rank-fade. qwen **autonomously rediscovered
  the same economic edge we found by hand** (`dispersion_rank asia__k2`, net-LB95
  +1.22) and expressed it as a novel net-positive program.
- Multiple other top discovered programs also self-gate by `hour`+`dispersion`.

This validates the ERA loop end-to-end: given the gating capability, it finds
economically-meaningful, session-conditioned, net-positive dispersion signals
autonomously.

## Next (SP2)

Scale the search budget and add parent recombination; let PUCT expand from all
seeded baselines (currently only the `loo_z` subtree); then **SP3 governance
promotion** — run the winning program through the full Stage 2/3 WFO →
Reduced-Core → Tick-Exact → Robustness ladder + the held-out months to confirm
the +0.13 survives out-of-sample before it is trusted.
