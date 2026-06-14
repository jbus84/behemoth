# FX USD-Factor Residual Mean-Reversion — Causal Selector Probe

**Date:** 2026-06-14  
**Branch:** worktree-fx-usd-factor-residual (PR #334+)  
**Question:** Can a supervised causal selector predict which 6–12 bps residual dislocations will revert next hour, lifting gross/net enough to clear measured spread cost?

---

## 1. Data & Method

- **Symbols:** 6 USD majors (EURUSD, GBPUSD, USDJPY, USDCHF, USDCAD, AUDUSD).
- **Bars:** 1000tick parquet → 5min aligned panel → hourly coarsen.
- **Factor:** Equal-weighted oriented USD-strength log return (no beta estimation, fully causal).
- **Residual:** Pair return minus factor.
- **Target band:** 6–12 bps |residual| (the "moderate-dislocation sweet spot" identified in PR #334).
- **Cost:** Measured hourly mean relative spread (`spread / mid`) per pair, not a fixed commission.
- **Label:** `y = 1` if fade wins (`−sign(residual_t) * residual_{t+1} > 0`).
- **Walk-forward:** 2-year train, 1-year OOS, 5-day purge gap. 7 windows spanning 2018–2026.

### Causal features (all known at entry hour `t`)

1. **Factor regime** — 6h & 12h rolling mean of intra-hour factor efficiency (`|net| / Σ|sub|`).
2. **Residual volatility** — 6h & 12h rolling std of pair residual.
3. **Cross-pair breadth** — fraction of pairs whose |residual| > 1σ (24h rolling).
4. **Cross-sectional dispersion** — std of residuals across the 6 pairs.
5. **Intra-hour path** — efficiency ratio + close-position from 5min sub-bars within the hour.
6. **Residual autocorrelation** — lag-1 correlation over 24h rolling window.
7. **Residual persistence** — signed sum over past 3h & 6h.
8. **Spread percentile** — current spread vs 24h median.
9. **Calendar** — UTC hour, day-of-week.
10. **Dislocation size** — |residual_t| in bps.

### Models

- **Baseline:** Always fade every pair-hour in the 6–12 bps band.
- **Logistic Regression** (`sklearn`, `C=1.0`, standardized features). Threshold selected on train to maximize net t-stat.
- **CatBoost** (`depth=4`, `iterations=200`, `l2_leaf_reg=5`). Only run if LR shows material OOS gross lift.

---

## 2. Results (aggregated across 7 walk-forward windows)

| Model      | Active% | n/window | Gross (bps) | Gross t | Net (bps) | Net t | Win% | Pos-month% |
|------------|---------|----------|-------------|---------|-----------|-------|------|------------|
| Baseline   | 100.0   | 1,193    | **+0.673**  | 1.2     | **−0.203**| −0.4  | 52.6 | 54         |
| Logistic   | 25.8    | 278      | **+0.761**  | 0.7     | **−0.101**| −0.1  | 52.3 | 55         |
| CatBoost   | 28.6    | 260      | **+0.649**  | 0.4     | **−0.185**| −0.4  | 55.1 | 49         |

### Interpretation

- **The 6–12 bps band is sub-cost on a 6-pair cross-sectional basis.** Baseline gross +0.67 bps, net −0.20 bps after measured spreads. The earlier EURUSD-only finding of net +0.18/+0.24 bps (at a 0.65 fixed commission) does **not** generalize to a diversified 6-pair book because wider-spread pairs (GBPUSD, USDCHF, USDCAD, AUDUSD) drag the average cost above the average capture.
- **Logistic regression produces marginal gross lift** (+0.09 bps) by filtering out some losing trades, but the lift is far below the spread cost. Net improves from −0.20 to −0.10 bps — still negative.
- **CatBoost does not help.** Despite astronomical train-set net t-stats (16–19), OOS gross is actually *lower* than baseline (+0.649 vs +0.673). The model overfits the training noise; more capacity makes it worse, not better.
- **Win rates are barely above coin-flip.** Even the "selected" subset is ~52–55% — the signal is too faint for a binary classifier to separate reliably.

### LR coefficients (last window)

| Feature            | Coef   | Directional interpretation                     |
|--------------------|--------|--------------------------------------------------|
| factor_eff_6       | −0.15  | Lower efficiency (choppy) → slightly more revert  |
| pers_3             | +0.21  | Recent persistence → model thinks revert (noise?) |
| factor_eff_12      | +0.12  | Contradicts the 6h version                       |
| res_vol_12         | +0.08  | Higher vol → slightly more revert                |
| dispersion         | +0.07  | More dispersion → slightly more revert           |
| intra_efficiency   | +0.06  | Higher intra-hour efficiency → more revert       |
| pers_6             | −0.11  | Longer persistence → less revert                 |
| breadth            | −0.07  | More pairs dislocating → less revert             |
| spr_pct            | −0.06  | Wider spread → less revert                       |
| disloc_bps         | −0.01  | Size within band → negligible                    |

Coefficients are small, inconsistent across windows, and do not point to a robust causal structure. The model is essentially fitting noise.

---

## 3. Honest verdict

### 3a. The "sub-cost" result in §2 was a COST-MODEL ARTIFACT (corrected)

The §2 selector charged each pair its **Dukascopy quoted spread** as cost (avg ≈ 0.87 bps, with AUDUSD ~1.49). That is *not* the user's execution cost. At a Pepperstone-Razor-style account the cost is **commission-dominated and roughly UNIFORM**: ~0.3 pip/side ×2 + near-zero raw spread ≈ **0.7 bps round-trip for every major**. Charging Dukascopy spreads spuriously sinks the wide-spread pairs (AUDUSD swings −0.80 → +0.04 just by using the right cost). Also confirmed: the `spread` column is the full ask−bid, so round-trip cost referenced to mid = **1× quoted spread** (a 2× "round-trip" correction is a double-count).

Per-pair always-fade, 6–12 bps band, at flat 0.7 bps commission:

| Residual | Mean net/pair | Pairs net>0 |
|---|---|---|
| **1-factor (dollar)** | −0.03 | 3/6 (EURUSD +0.13, GBPUSD +0.06, USDCHF +0.11) |
| **2-factor (dollar+risk)** | **+0.08** | **4/6** (adds USDCAD +0.15; USDCHF +0.11→+0.29) |
| 3-factor | +0.02 | 3/6 (over-removes) |

So under the *correct* cost model the book is **~break-even to mildly positive**, not −0.20 sub-cost. EURUSD is the most stable winner (~+0.13–0.19).

### 3b. Does improving the USD factor help? YES — *structure*, not *estimation*

- More PCs of the same dollar factor: **no** (EW ≈ PC1 at 0.997).
- A **2-factor** model (dollar + a risk/carry PC2, 17% of variance): **yes**. Mean net/pair −0.03 → +0.08, 3/6 → 4/6 pairs positive, win rates +1–2 pts. The gain concentrates in the safe-haven/commodity pairs (USDCHF, USDCAD) whose 1-factor residual still carried an un-removed common component. 3-factor over-removes (scrubs signal).
- **Caveat:** PCA removal is full-sample (in-sample) → optimistic upper bound. A causal *rolling* 2-factor is the next build.

### 3c. Modeling (LR/CatBoost) still adds ~no gross lift

Independent of the cost fix (lift is gross): logistic gives only ~+0.09 bps gross lift, CatBoost overfits (train t 16–19, worse OOS). The *selection* edge is faint. The leverage is in **the 2nd factor and pair selection**, not a classifier.

---

## 4. What *would* help (scoped to this signal)

| Lever                     | Expected impact | Honest assessment                        |
|---------------------------|-----------------|------------------------------------------|
| Restrict to tight pairs   | High            | EURUSD-only or tight-3 book may clear cost; test next |
| Lower cost (ECN/commission) | High            | Commission-based broker (~0.3 bps/side) vs spread-betting (~1.2–1.8 bps); decisive |
| Lower frequency (daily/weekly) | High       | Cost negligible vs move size; only other surviving FX edge lives here |
| More sophisticated model  | Low/negative    | Signal is below noise floor; capacity → overfit |
| Exact 5-min sub-bar timing| Marginal        | Already engineered; no transformative leverage left |

---

## 5. Files / artifacts

- `scripts/fx_coint/residual_selector.py` — causal selector (walk-forward LR + CatBoost); cost = flat commission.
- `scripts/fx_coint/usd_factor_nfactor_probe.py` — 1- vs 2- vs 3-factor residual comparison under commission cost.
- `tests/fx_coint/test_residual_selector.py` — look-ahead guard + regime-lift + cost smoke tests.
- `scripts/fx_coint/usd_factor_residual_probe.py` — original hourly probe.
- `scripts/fx_coint/usd_factor_move_distribution.py` — cost-sensitivity by move-size band.

---

## 5b. Kalman state-space on the residual — does NOT help at hourly

Tested whether decomposing the residual price into a random-walk (permanent) +
AR(1) (transitory/mean-reverting) state and fading the filtered *stretch* beats
thresholding the raw |residual move|. (`usd_factor_kalman_residual.py`; EW
factor, train-only MLE params, causal *filtered* states, OOS tail.)

Result: **Kalman stretch loses to simple |move| thresholding on 5/6 pairs at 1h**
(matched trade count). Reason: φ ≈ 0.69 → ~1–2h half-life; reversion is so fast
that the *last hour's move already is the stretch*, and integrating older history
adds stale noise. Simple thresholding is near-optimal for a 1h-half-life signal.

Lone exception: EURUSD at a 3h hold (Kalman +0.48 vs baseline +0.18) — longer
holds let the level-stretch matter, but isolated (GBPUSD reverses). Implication:
state-space decomposition is the right tool at *slower* reversion → another
argument for the **daily/weekly port**, not hourly.

## 5c. 4-hour timeframe (PCA) — body fades, tail is a fragile mirage

Stepped up to 4h bars (`usd_factor_4h_probe.py`, PCA 1- and 2-factor, commission
cost). PC structure unchanged (PC1 60%, PC2 17%). Findings:
- Pooled reversion *weaker* than hourly (lag-1 corr −0.039 vs −0.058) — fast
  hourly reversion averages out.
- The moderate band (p75–95) that worked hourly is ~breakeven/negative at 4h.
- The big-dislocation **top-10% tail** had strong *aggregate* net (+0.5..+1.0 bps,
  5/6 pairs) — opposite to hourly where the extreme tail was non-reverting info.
- **But per-year it is NOT robust:** win ~53–55% (coin-flip), every pair has
  multiple large losing years, aggregates carried by 2–3 outlier years
  (GBPUSD swings −2.27 → +3.96). Classic tail-concentration mirage.

Timeframe verdict: robust reversion lives at **hourly** (cost-gated, 9/9 yrs
gross+); the proven tradeable edge lives at **weekly+**; **4h is the worst of
both** — less robust than hourly, not the weekly edge. Do not pursue 4h.

## 5d. Timeframe sweep: 30m / 1h / 4h / daily (PCA) — a U-shape

`usd_factor_4h_probe.py <freq>` runs any frequency. Pooled lag-1 residual corr
(1-factor): 15m −0.077, 30m −0.074, 1h −0.058, 4h −0.039, daily −0.033. It
strengthens toward higher frequency but **PLATEAUS at 15–30m (~−0.075)** — it
does NOT keep exploding toward the tick. Pure bid-ask/tick bounce would keep
growing; a plateau argues for a *genuine ~15–30 min reversion timescale* in the
residual mid (mildly reassuring vs the microstructure-illusion worry).

| TF | Robust (per-yr)? | Net @0.7 commission | Verdict |
|---|---|---|---|
| **15m** | ✅ 5/6 pairs 8–9/9 yrs, win 57–62% | net+ (EUR/GBP/CHF 9/9) | as 30m; USDJPY fails fast end (2/9) |
| **30m** | ✅ 8–9/9 yrs, win 58–62% | net+ (USDCHF +1/yr every yr) | strongest on paper; microstructure-contamination risk |
| 1h | ✅ 9/9 gross+ | marginal | cost-gated |
| 4h | ❌ tail mirage | fragile | skip |
| daily | small-n/noisy | big but unstable (USDCHF clean) | overlaps proven weekly |
| weekly+ | ✅ proven | clears cost | the macro edge |

30m is the most statistically robust result here (look-ahead-clean 1-factor body
net +0.15..+0.26, 2-factor stronger). BUT capture uses **mid** prices + flat
commission; the frequency-scaling warns a chunk may be non-tradeable
microstructure that dies once you cross the real spread at the stressed moment
(the [[project_fx_range_band_maker_illusion]] pattern). **Decisive test: tick-exact
fills at the 30m boundary (real ask/bid).** Until then 30m is unproven, not real.

## 6. Next (if continuing this thread)

1. **Causal rolling 2-factor residual** — confirm the in-sample 2-factor lift (§3b) survives out-of-sample with a rolling factor estimate.
2. **Tick-exact fills on the 6–12 bps band** — the margin-deciding test; band is moderate (not event candles) so fills should be benign.
3. **Lower-frequency port** — daily/weekly factor-residual reversion, where cost is negligible and a richer factor model converts directly to P&L.
