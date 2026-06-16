# FX Cluster Kill-Test Report

**Verdict: NO_GO** (2026-06-16) — *legitimate, after correcting a clustering-parameterization bug.*

Pool pairs: EURUSD, GBPUSD, AUDUSD, USDCHF, USDCAD (USDJPY held out).
Train 2018-01 .. 2024-01 (185,595 points), Test 2024-01 .. 2026-06 (74,130 points).
Cost floor ~0.6 bps commission + crossed spread.
Pipeline: honest hourly raw-tick bars → 15 causal pair-normalized features → **UMAP(15→2,
n_neighbors=30)** fit on train → **HDBSCAN(min_cluster_size=400, min_samples=20,
cluster_selection_method='leaf')** → OOS via `approximate_predict` → vol-scaled symmetric
triple-barrier labels (±1σ·√8, ~1-day patience), net of cost → per-cluster scoring
(time-block bootstrap + persistence + BH-FDR).

## ⚠️ Correction: the first run was a parameterization artifact

The initial configuration used HDBSCAN's default `cluster_selection_method='eom'` on an 8-D
UMAP. It returned **exactly 2 clusters covering 100% of points with zero noise** — which is
the *signature of a degenerate clustering*, not "no structure". EOM (Excess of Mass)
collapses a single connected manifold to its 2 broadest masses, and the 8-D embedding
flattened density contrast (curse of dimensionality). The two "clusters" were simply the
**sign of recent return** (cl0: `trend +0.98`, `ret_1h +0.74`; cl1: `trend −0.98`,
`ret_1h −0.75`) — a trivial momentum bisection, hence the perfect 50/50 and the coin-flip
forward outcome. **The "no structure" reading was wrong.**

Fix (`scripts/fx_cluster/cluster_param_probe.py`): `cluster_selection_method='leaf'` on a
**2-D** UMAP recovers genuine fine-grained structure. Cluster counts by setting:

| embedding | method | min_cluster_size | clusters | noise% |
|---|---|---|---|---|
| 8-D | eom (old) | any (400/100/30) | 2 | 0% |
| 8-D | leaf | 400 | 19 | 81% |
| 2-D | leaf | 400 | **52** | 74% |
| 2-D | leaf | 100 | 223 | 71% |
| 2-D | leaf | 30 | 649 | 73% |

70–90% noise is *healthy* HDBSCAN behaviour (most points are background; dense pockets are
clusters). The corrected config (2-D, leaf, mcs=400) yields **52 economically-sized
clusters**, which is what the kill-test below actually scores.

## Corrected result — 52 real clusters, still NO_GO

Train clusters scored: **52**; selected (beat cost + persistence + BH-FDR): **0**.

The NO_GO now rests on three sound, mutually-reinforcing findings:

**1. No persistence signature anywhere.** `mfe/mae ∈ [0.86, 1.16]` across the 52 clusters —
**0 of 52** pass the persistence filter (≥1.5). Favourable and adverse excursions are
symmetric (random-walk-like) in **every discoverable regime**. The design's core thesis —
that some recurring situation produces a *persistent shift to a new price level that holds*
— is **refuted, not dodged**. There is no regime where price moves and stays.

**2. Train-positive clusters are chance, and don't survive OOS.** Only **9 of 52** clusters
had a positive *train* mean (≈ what you'd expect by chance), and of those just **3 stayed
positive OOS** — none significant, none with a persistence signature, all small-n. The
larger train-positives flip hard negative out of sample (classic small-sample overfitting):

| cluster | train net (bps) | boot p | mfe/mae | OOS net (bps) |
|---|---|---|---|---|
| cl18 | +1.72 | 0.097 | 0.86 | **−6.25** |
| cl17 | +0.74 | 0.287 | 0.88 | **−4.88** |
| cl32 | +0.94 | 0.257 | 0.86 | **−2.73** |
| cl13 | +0.67 | 0.299 | 1.07 | **−2.15** |
| cl12 | +1.11 | 0.234 | 1.07 | +0.59 (n=137, n.s.) |

Only 3 of the 9 stayed OOS-positive at all (e.g. cl12 +1.11→+0.59), but each has p≈0.23+,
n_oos in the low hundreds, and no persistence — the few expected by chance across 52 clusters.

**3. No significance.** Best block-bootstrap p across all clusters = **0.097**; nothing
approaches significance, let alone surviving BH-FDR at α=0.10.

## Interpretation

With the clustering corrected, the dollar complex *does* decompose into ~52 recurring
hourly (pair, time) situations. But none of them carries an exploitable, persistence-screened,
cost-net forward edge that survives out of sample. The decisive, robust fact is the
**universal symmetry of triple-barrier excursions (mfe/mae ≈ 1.0)**: at the multi-hour-to-1-day
horizon there is no regime in which price persistently shifts to a new level — exactly the
behaviour the strategy was designed to harvest. This is consistent with the broader FX
thread (intraday FX is not conditionable at retail cost; only weekly+ survives). The
unsupervised lens confirmed that conclusion from a new direction — and surfaced a
generalisable HDBSCAN lesson (see below).

## Lessons

- **HDBSCAN parameterization:** cluster on a **2-D** UMAP and use
  `cluster_selection_method='leaf'`. The default `'eom'` on a high-D embedding can collapse
  to a couple of giant clusters with **zero noise** — a degenerate result that masquerades
  as "no structure". *2 clusters + 0% noise ⇒ mis-parameterized, not unclusterable.*
- The persistence (mfe/mae) symmetry is the binding wall, not cluster granularity — finer
  clusters (223, 649) only shrink samples and amplify overfitting, they do not create a
  persistence signature.

## What a revisit would require

Don't re-tune clustering knobs. First demonstrate (supervised IC probe) that *some* causal
feature conditions the forward outcome away from a 0.50 win / mfe-mae 1.0 symmetry; only
then is the unsupervised machinery worth re-running. Per the thread's priorities, this is
low priority versus the proven weekly+ direction.

## Reproduce

```bash
uv run python -m scripts.fx_cluster.bars                    # honest hourly bars (once)
uv run python -m scripts.fx_cluster.killtest               # verdict + this report (auto-summary)
uv run python -m scripts.fx_cluster.killtest_diagnostics   # per-cluster decomposition
uv run python -m scripts.fx_cluster.cluster_param_probe    # eom-vs-leaf / 8D-vs-2D evidence
```
