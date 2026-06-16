# FX Cluster Kill-Test Report

**Verdict: NO_GO** (2026-06-16)

Pool pairs: EURUSD, GBPUSD, AUDUSD, USDCHF, USDCAD (USDJPY held out).
Train 2018-01 .. 2024-01 (185,595 points), Test 2024-01 .. 2026-06 (74,130 points).
Cost floor ~0.6 bps commission + crossed spread.
Pipeline: honest hourly raw-tick bars → 15 causal pair-normalized features → UMAP(15→8,
n_neighbors=30) fit on train → HDBSCAN(min_cluster_size=400, min_samples=20) → OOS via
`approximate_predict` → vol-scaled symmetric triple-barrier labels (±1σ·√8, ~1-day
patience), net of cost → per-cluster scoring (time-block bootstrap + persistence + BH-FDR).

## What was selected

Train clusters scored: **2**; selected: **0**. NO_GO.

## Decomposition (why) — two independent failures

**1. There is no cluster structure to exploit.** HDBSCAN partitioned the 185,595 training
points into exactly **two clusters of ~50/50** (93,078 / 92,517) with **zero noise points**:

| label | n | % |
|---|---|---|
| cl0 | 93,078 | 50.2% |
| cl1 | 92,517 | 49.8% |

With `min_cluster_size=400` (0.2% of the data) HDBSCAN *could* have surfaced many small
dense pockets if recurring "situations" existed. Instead it found a single 2-way split of
one diffuse cloud and flagged nothing as noise. The 15 causal pair-normalized features do
not embed into separable regimes — there are no distinct recurring situations to condition on.

**2. Even taking the two halves as candidates, neither has a forward edge.** Scored on the
train fold (cost already inside the net), and carried to OOS via the frozen clusters:

| cluster | side | n train | train net (bps) | win | boot p | mfe/mae | hold (bars) | gate | OOS n | OOS net | OOS win |
|---|---|---|---|---|---|---|---|---|---|---|---|
| cl0 | short | 93,078 | −1.758 | 0.50 | 1.000 | 0.98 | 8 | FAIL margin + persistence | 37,377 | −1.948 | 0.49 |
| cl1 | long | 92,517 | −1.710 | 0.50 | 1.000 | 1.01 | 8 | FAIL margin + persistence | 36,753 | −1.199 | 0.51 |

- **Win rate is exactly 0.50** on train and 0.49/0.51 OOS — a coin flip. The triple-barrier
  outcome is not conditioned by cluster membership.
- **`mfe/mae ≈ 1.0`** — favourable and adverse excursions are symmetric, so there is no
  "sustained move to a new level" signature (the persistence filter the design was built
  around finds nothing to hold onto).
- **Bootstrap p = 1.000** — the (negative) mean is fully consistent with zero gross edge.
- **Net ≈ −cost.** With ~50% win on symmetric ±1σ barriers, gross ≈ 0 and net ≈ −1.2 to
  −1.9 bps is just the round-trip cost being paid. This is stable from train to OOS.

## Interpretation

The hypothesis was that unsupervised UMAP+HDBSCAN clustering of the dollar complex would
surface recurring (pair, time) situations with an exploitable, persistence-screened
level-shift edge at the multi-hour-to-1-day horizon. The kill-test refutes it on **two
independent grounds**: (a) the causal feature space has no multi-modal cluster structure
(one blob, split 50/50, no noise), and (b) the forward triple-barrier outcome is a coin
flip regardless of how the space is carved, leaving net ≈ −cost. The two failures reinforce
each other — there is neither structure to find nor predictability to capture.

This is consistent with the broader FX thread: intraday FX forward returns are not
conditionable at retail cost; the only surviving edge lives at weekly+ horizons. The
unsupervised lens did not change that conclusion — it confirmed it from a new direction.

## Scope & what would be required to revisit

This is one configuration: one 15-feature set, one UMAP/HDBSCAN parameterization, one
barrier spec, one train/test split. The decisive evidence, though, is the **exactly-0.50
win rate** — that is a property of the forward outcome given the features, not of the
clustering knobs. A different feature set or hyperparameters could change the *number* of
clusters, but the coin-flip forward conditioning is the deeper wall. Any revisit should
therefore start by demonstrating that *some* causal feature conditions the forward outcome
away from 0.50 (a supervised IC probe), before re-investing in the unsupervised machinery.
Per the thread's discipline, that is low priority versus the proven weekly+ direction.

## Reproduce

```bash
uv run python -m scripts.fx_cluster.bars              # build honest hourly bars (once)
uv run python -m scripts.fx_cluster.killtest          # verdict + this report
uv run python -m scripts.fx_cluster.killtest_diagnostics   # the decomposition above
```
