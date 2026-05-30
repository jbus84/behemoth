# ERA dispersion-coverage evidence (2026-05-30)

Live evidence for the ADR-0005 coverage work (PRs #278 + #279). Generator
`qwen3-coder-next` via `ollama.com`, EURUSD 2000-tick / horizon 3, scored on the
validation split (2025-07..10); held-out = 2025-11..2026-02. Cross-symbol frame
110,906 rows × 82 cols. Two runs, evidence executed by Opus (not CI). Cache cleared
beforehand so every program was generated under the final code + prompt.

Both runs completed with **zero** sandbox timeouts, causality rejections, or exec
errors in the logs — confirming the vectorised `corr_weighted_graph` / `factor_resid`
seeds run cleanly on the real ~30k-row splits (the per-bar loops they replaced would
have approached the 10s timeout).

## Run 1 — rediscovery tracer (`--no-baseline-seeds`, budget 40, 46 nodes)

ADR 0005 requires the loop to *rediscover* the canonical baselines when they are
removed from the seed set. With `dispersion_rank`/`loo_z`/`robust_z`/`graph_laplacian`
removed, **qwen reconstructed the core edge from scratch**: every top program is a
leave-one-out peer residual `(target − peer_mean)/peer_std`, gated to the **Asia
session (UTC hour < 6) AND high cross-sectional dispersion** (causal expanding
percentile / mean+std). This is the same economic structure as the hand-found
`dispersion_rank EURUSD asia__k2` edge (net-LB95 +1.22) — found autonomously.

It also layered on the ADR's transfer ideas, all causally:
- **participation ratio** (target vol vs peer vol — concentration gate),
- **covariance-aware dampening** (down-weight when peers are correlated → less idiosyncratic),
- **dispersion change / acceleration** (regime-shift weighting),
- **rank regression-to-mean** (fade extreme cross-sectional ranks),
- **causal EWMA peer mean/var/cov** state.

| rank | val_score | holdout n | holdout mean_net | holdout month_hit | character |
|---|---|---|---|---|---|
| 1 | **0.2494** | 5 | −2.61 | 0.00 | loo-z + asia + high-disp + participation + cov-dampen + disp-accel (overfit OOS) |
| 2 | 0.1308 | 10 | +0.01 | 0.67 | loo-z + asia + 70th-pct-disp gate + rank fade |
| 3 | 0.1262 | 5 | **+1.20** | **1.00** | loo-z + asia + high-disp + participation + cov-dampen |
| 4 | 0.1262 | 5 | **+1.20** | **1.00** | (duplicate of #3) |
| 5 | 0.1244 | 8 | **+4.12** | 0.33 | loo-z + asia + high-disp + disp-accel |

**BH-FDR holdout survivors (q=0.10): none.** Several programs look promising on the
held-out months (#3/#4: +1.20 mean_net, 100% positive months; #5: +4.12 mean_net) but
each has only 5–10 entries, so none clears Benjamini–Hochberg correction over the
explored set. The #1 by validation overfits badly out-of-sample (−2.61, 0% months) —
exactly the hazard the held-out + BH-FDR gate (gap 6) exists to catch.

## Run 2 — coverage (full seeds, budget 100, 110 nodes)

| rank | val_score | holdout n | holdout mean_net | holdout month_hit | program |
|---|---|---|---|---|---|
| 1 | −0.1063 | 55 | −4.08 | 0.00 | `graph_laplacian` seed (ungated) |
| 2 | −0.1141 | 69 | +0.75 | 0.75 | `robust_z` seed (ungated) |
| 3 | −0.1686 | 59 | +2.81 | 1.00 | `loo_z` seed (ungated) |
| 4 | −0.1967 | 45 | −3.25 | 0.00 | `corr_weighted_graph` seed (vectorised, ran clean live) |
| 5 | −0.2324 | 15 | +1.06 | 0.50 | discovered (ungated EWMA-covariance variant) |

All top-5 are **net-negative on validation** because they trade 24h with no session
gate — reconfirming the SP1 finding that ungated dispersion residuals are net-negative.
In this budget the search stayed in the ungated regime and did **not** rediscover the
Asia + high-dispersion gate that Run 1 found. BH-FDR survivors: none.

## Findings

1. **Coverage achieved.** The loop now reaches the full ADR catalogue: leave-one-out,
   robust median/MAD, correlation-weighted peer graph, factor/covariance residuals,
   participation/concentration, dispersion-regime + dispersion-change, rank-transition,
   and causal EWMA/stateful temporal structure all appeared in generated programs —
   none of which were reachable before #278/#279 (the prompt now exposes the causal
   time axis and the probe keeps it honest).
2. **Rediscovery confirmed (gap 7).** With baselines removed, qwen rebuilt the
   loo-z + Asia + high-dispersion edge autonomously.
3. **Governance gate works (gaps 5–6).** Per-program holdout diagnostics + BH-FDR are
   wired and reported. No program survived OOS multiple-testing — the honest, correct
   outcome at these tiny entry counts; the validation-best program was an OOS overfit.
4. **Baseline composition steers the search.** Removing the strong *ungated* baselines
   (Run 1) pushed PUCT down the gated-seed path and produced the economically-meaningful
   discoveries; with them present (Run 2) the search refined ungated residuals that top
   the validation ranking but are net-negative. The validation-positive edge lives in a
   low-frequency gated regime that few-entry samples can't certify.

## Next (SP3 proper — not in these PRs)

- The promising gated programs (Run 1 #3/#5) have far too few held-out entries to
  certify. Promote them through the **real governance ladder** (Stage 2/3 Monthly WFO →
  Reduced-Core Rolling → Tick-Exact → Robustness) on more data before trusting anything.
- Bias the seed set / exploration toward gated regimes, or raise budget substantially,
  so the full run (not just the ablation) finds the gated edge.
- Run other symbols and bar-ticks. These numbers are validation-split fast-metric
  scores, **not deployable**.
