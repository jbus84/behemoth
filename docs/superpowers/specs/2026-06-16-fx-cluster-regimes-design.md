# Cluster-discovered FX regimes (`fx_cluster`)

**Date:** 2026-06-16
**Branch / worktree:** `worktree-fx-cluster-regimes`
**Status:** Design approved; kill-test milestone only.

---

## 1. Motivation

Every prior intraday FX line in this repo has been a supervised, hand-specified signal
(USD-factor residual reversion, range bands, directional time bars) and almost all died
at the ~0.7bps Razor cost wall or on a look-ahead/stale-bar artifact. This is a
**deliberately different lens**: instead of positing a signal, we let unsupervised
structure in the data surface *recurring market situations* and then ask, causally and
net of cost, whether any of those situations carry a tradeable forward edge.

The approach takes inspiration from the existing thread (the equal-weighted USD factor,
the residual-vs-factor object, the honest-bar discipline, the cost wall, the
decomposition-of-gross-vs-cost-vs-significance habit) but is **not** anchored to it.

**Goal:** Use UMAP + HDBSCAN to discover recurring `(pair, time)` "situations" across the
dollar complex whose forward outcome — a vol-scaled, persistence-screened *level shift* —
is profitable **net of cost, out of sample**, at a **multi-hour-to-1-day** horizon.

**Non-goals (this milestone):** position sizing, portfolio construction, live paper
trading, full walk-forward refit, parameter optimization. Those only happen if the
kill-test passes.

---

## 2. Design decisions (locked during brainstorming)

| Decision | Choice | Why |
|---|---|---|
| Holding timescale | Multi-hour to ~1 day | Moves are large enough (10s of bps) that ~0.7bps cost is small-but-real; the natural home for "identify a new level and exit at profit". Intraday-scalp slams the cost wall; multi-day has too few events for clustering. |
| Unit of observation | `(pair, time)` situation, "A-enriched" | One point = one pair at one time; ~6× the data; directly tradeable ("*this* pair is in a paying setup"); both temporal and spatial axes are first-class. Regime features from the market-snapshot view are baked into each point. |
| Target | Vol-scaled **symmetric triple-barrier** + persistence filter | Causal, variable-duration, fast over millions of points; captures "move to the new level, exit". "Holds long enough" enters as a *cluster-quality screen* (MFE/MAE, hold-time), not as the label. |
| First milestone | **Cheap kill-test** (single causal split) | One question: does *any* cluster show OOS-stable edge net of cost, block-bootstrap significant, FDR-controlled? If not → cheap documented NO-GO. Matches the repo's probe-then-confirm pattern. |

---

## 3. Architecture

Pipeline of single-purpose modules in a new `scripts/fx_cluster/` package. Data flows
strictly left to right; every stage is causal (uses only information available at or
before time `t`).

```
raw ticks ──► bars.py ──► features.py ──► embed.py ──► cluster.py ──► score.py ──► killtest.py
  (dukascopy)  honest      causal,         UMAP        HDBSCAN +     per-cluster    single causal
               hourly      pair-norm       (fit/       approximate_  scoring,       split → GO/NO-GO
               bars        feature         transform)  predict       persistence,   report
                           vectors                                   direction,
                                                                     bootstrap, FDR
       labels.py (triple-barrier outcomes) feeds score.py in parallel with cluster labels.
```

### 3.1 Module responsibilities and interfaces

Each module is independently understandable and testable. Interfaces are polars
DataFrames / numpy arrays with documented columns.

- **`bars.py`** — Build honest time bars from raw dukascopy ticks (extend the existing
  `scripts/fx_coint/build_rawtick_timebars.py` pattern to an **hourly** frequency; last
  *tick* before each boundary, never a tick-count resample). Output cached parquet per
  pair: `bucket, bid, ask, mid, n_ticks`.
  - *Depends on:* raw ticks at `~/Desktop/dukascopy_ticks/{SYM}/*_ticks.parquet`.
  - *Provides:* `load_bars(sym) -> DataFrame`.

- **`features.py`** — Build the causal, pair-relative feature matrix (Section 4). One row
  per `(pair, t)`; all features computed from data `<= t`, z-scored with causal rolling
  stats so points from different pairs are comparable.
  - *Depends on:* `bars.py`, the USD-factor construction (Section 4.2).
  - *Provides:* `build_features(bars_by_pair) -> (DataFrame[pair, t, f_0..f_k], feature_names)`.

- **`labels.py`** — Vol-scaled symmetric triple-barrier outcomes per `(pair, t)`:
  realized **net** return for long and for short, plus MFE, MAE, and hold-time. Exit
  modeled at the actual bid/ask of the exit bar; cost applied per Section 5.2.
  - *Depends on:* `bars.py` (and intrabar path — see Section 5.1 fidelity note).
  - *Provides:* `build_labels(bars_by_pair, k, patience) -> DataFrame[pair, t, ret_long, ret_short, mfe, mae, hold_bars, exit_reason]`.

- **`embed.py`** — Thin causal UMAP wrapper: `fit(train_X)`, `transform(X)`. Fixed modest
  hyperparameters; fit on train only.
  - *Provides:* `Embedder` with `.fit(X) / .transform(X) -> Z`.

- **`cluster.py`** — Thin HDBSCAN wrapper: `fit(train_Z)` → cluster labels +
  `approximate_predict(Z)` for OOS points → `(label, membership_strength)`. Noise label
  `-1` = no trade.
  - *Provides:* `Clusterer` with `.fit(Z) -> labels` and `.predict(Z) -> (labels, strengths)`.

- **`score.py`** — Per-cluster × side scoring on a given (train) fold: mean net return,
  win rate, block-bootstrap t-stat (time blocks), MFE/MAE & hold-time summaries; the
  **persistence filter**; **direction assignment**; cluster **selection**; **BH-FDR**
  across selected clusters.
  - *Depends on:* labels + cluster labels.
  - *Provides:* `score_clusters(labels_df, cluster_labels, fold) -> ClusterReport`,
    `select_clusters(report, cost, margin) -> selection`.

- **`killtest.py`** — Orchestrator: train/test split, fit embed+cluster+select on train,
  assign test causally, simulate selected clusters on test, aggregate OOS, write the
  GO/NO-GO report to `docs/analysis/fx_cluster_killtest_report.md`.

---

## 4. Feature vector (one per `(pair, t)`)

~20–30 features in three blocks. **Every feature is causal** (data `<= t`) and **z-scored
with causal rolling statistics** (long rolling or expanding window ending at `t`) so a
EURUSD point and a USDCHF point are legitimately comparable in the same embedding.

### 4.1 Temporal block (own-pair path)
- Vol-normalized returns over 1h, 4h, 12h, 24h lookbacks.
- EWMA realized-vol level; vol-regime (current vol ÷ its rolling median).
- Position within recent range over 24h and 5d: `(mid − min) / (max − min)`.
- Distance from recent N-bar high/low in vol units; bars-since-last high/low.
- Trend / sign-consistency of recent returns (e.g. fraction of last N returns positive).
- Recent spread level and tick-intensity (`n_ticks`) regime — liquidity-state proxies.

### 4.2 Spatial block (cross-currency)
- **USD factor:** equal-weighted dollar factor return over the lookbacks. The factor is
  the EW mean of the 6 USD-oriented log returns (EW ≈ PC1 at ~0.997 in the prior thread,
  so no estimation / no look-ahead).
- **Residual vs factor:** this pair's oriented return minus the factor, z-scored (the
  known reversion object).
- Cross-sectional dispersion of the 6 residuals (regime).
- Risk PC2 (risk-on/off) state — built causally (rolling) or as a fixed economic basket;
  if rolling PCA proves fragile, fall back to a commodity-vs-safe-haven basket.
- Rolling beta/correlation of this pair to the factor.
- Cross-sectional rank of this pair's recent move within the complex.

### 4.3 Regime-context block (market snapshot, baked into each point)
- Complex-wide vol regime and dispersion regime.
- Factor-trend strength.
- Session / time-of-day (cyclic encoding), day-of-week.

### 4.4 Pairs
6 majors: EURUSD, GBPUSD, AUDUSD, USDCHF, USDCAD, USDJPY. **USDJPY is flagged** and held
out of the pooled fit by default (the thread's repeated finding that JPY behaves
differently); it is re-introduced only if it forms clean, separately-profitable clusters.

---

## 5. Target / labels

### 5.1 Vol-scaled symmetric triple-barrier
From each point `(pair, t)`:
- Profit barrier at `+k·σ_t`, stop at `−k·σ_t`, where `σ_t` is a **causal EWMA** vol
  estimate of the per-bar return; patience (vertical) barrier at ~1 trading day.
- Compute the outcome for **both** long and short (so clusters self-reveal as fade vs
  follow): whichever barrier is hit first; if neither, exit at the patience cap.
- Record realized **net** return per side, plus **MFE, MAE, hold-time (bars), exit
  reason**.

**Intrabar fidelity note:** first-touch on hourly OHLC-from-ticks can be ambiguous when
both barriers fall inside one bar. For honesty we resolve the barrier-hit time at finer
resolution — either from the underlying ticks for the candidate bars, or a conservative
"stop-before-target within an ambiguous bar" rule. The implementation plan will pick one;
the conservative rule is the default to avoid optimistic labels.

### 5.2 Cost & fills
- Entry at the point's bar close; exit at the **actual bid/ask** of the exit bar (cross
  the real spread at the moment, per the thread's tick-exact lesson).
- Apply a flat commission of ~0.6bps round-trip (cTrader Razor: $3.00/side) plus the
  realized quoted spread crossed. The combined floor used for selection is ~0.7bps RT;
  the report sensitivities also show net at +50% spread stress.

### 5.3 Persistence filter (the "holds" requirement)
A cluster qualifies for trading only if its winning trades come from **sustained** moves,
not 1-bar spikes:
- High MFE-to-MAE ratio on the winning side.
- Non-trivial median hold-time (more than a small number of bars).
Thresholds are set by economic reasoning on the train fold and reported; they are a
*screen on which clusters we trust*, never part of the label or the clustering.

---

## 6. Causality & validation

The subtle look-ahead risk in a clustering pipeline is that the **embedding and clusters
themselves** can encode the future if fit on the whole sample. Controls:

1. **Honest bars** — built from raw ticks (no tick-count→time resampling). Eliminates the
   stale-close artifact that inflated the prior thread ~2×.
2. **Causal features** — all rolling/EWMA/z-score statistics use only data `<= t`. No
   full-sample normalization.
3. **Train-only fit** — UMAP and HDBSCAN are fit on the **train** span only. Test points
   are embedded with `UMAP.transform` and assigned with `hdbscan.approximate_predict`.
   Clusters never see test geometry.
4. **Train-only cluster scoring** — direction and profitability per cluster are read from
   **train folds only**, frozen, then applied to test.
5. **Cross-sectional dependence** — at each `t` the 6 pairs' points are correlated.
   Significance uses a **block bootstrap over time** (resample time-blocks, not rows) so
   t-stats are not inflated by treating correlated same-timestamp trades as independent.
6. **Multiplicity** — many candidate clusters → **BH-FDR** across the selected clusters.
7. **Hyperparameter discipline** — UMAP/HDBSCAN/barrier hyperparameters are fixed by
   reasoning with at most minimal train-only sensitivity checks; choices and any sweep
   are reported honestly to keep the multiple-testing surface visible.

### 6.1 Kill-test protocol
- **Train:** 2018-01 → 2023-12. **Test:** 2024-01 → 2026-06.
- Fit bars→features→UMAP→HDBSCAN on train; score, persistence-filter, and select clusters
  (+ direction) on train; **freeze**.
- Assign test points causally; simulate the selected clusters' frozen side; exit per
  triple-barrier with honest fills net of cost.
- **Aggregate OOS:** net return/trade, block-bootstrap t-stat, positive-period fraction,
  per-year breakdown; BH-FDR across selected clusters; explicit
  gross-vs-cost-vs-significance decomposition.

### 6.2 GO / NO-GO decision
- **GO candidate:** ≥1 (ideally a few) cluster with OOS net edge **clearing the ~0.7bps
  cost floor with margin**, **FDR-significant** under the block bootstrap, **stable across
  the OOS span** (not carried by one quarter/year), and wins driven by sustained moves
  (persistence filter holds OOS). → proceed to walk-forward milestone.
- **NO-GO:** nothing survives. Write up the negative result (what was tried, where it
  died) and stop. This is a success of the kill-test, not a failure.

---

## 7. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Cross-sectional dependence inflates t-stats | Time-block bootstrap; positive-*period* fraction, not positive-*trade*. |
| HDBSCAN cluster instability | Use membership strength; `approximate_predict` for OOS; perturbation/seed check; require economically-sized clusters (`min_cluster_size` in the hundreds). |
| Clusters don't recur OOS (regime drift) | This is exactly what the kill-test measures; honest OOS assignment, no refit. |
| Cost wall at multi-hour | Vol-scaled barriers keep gross targets ≫ 0.7bps; report at +50% spread stress; decomposition habit. |
| Multiplicity from feature/hyperparameter freedom | Fix by reasoning, minimal train-only tuning, BH-FDR, honest reporting. |
| Look-ahead in the embedding | Train-only fit + causal transform/predict (Section 6, controls 3–4). |
| USDJPY contaminating the pooled fit | Held out by default; re-introduced only if it clusters cleanly on its own. |
| Rolling PCA for risk-PC2 is fragile on 6 assets | Fall back to a fixed economic basket (commodity vs safe-haven) for the risk feature. |

---

## 8. Dependencies
- New: `umap-learn`, `hdbscan` (add via `uv`). Existing: polars, numpy, scipy/sklearn.

## 9. Deliverables (kill-test milestone)
- `scripts/fx_cluster/` package (modules in Section 3.1).
- Cached honest hourly bars under `data/tick_bars/{SYM}_1h_raw.parquet`.
- `docs/analysis/fx_cluster_killtest_report.md` — the GO/NO-GO writeup with the
  decomposition, per-year table, and decision.
- Tests for the causal-discipline-critical units (feature causality, label barrier logic,
  train-only fit / OOS assignment, block bootstrap).
