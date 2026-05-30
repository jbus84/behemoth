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

## Next (SP1.5 / SP2)

Add the ADR's entry gates to the harness so programs/threshold can be conditioned:
`entry = |residual| ≥ threshold AND session/time-bin in allowed AND
dispersion_regime in allowed_bins AND participation ≤ max`. Re-run; expect the
asia-conditioned dispersion edge to become reachable (and net-positive). Also
let PUCT expand from all seeded baselines, not only the `loo_z` subtree.
