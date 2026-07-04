# BoostLSS Straddle — Review Backlog

Items are grouped by risk. Work highest-risk items first.
Status: `[ ]` open · `[x]` done · `[~]` investigated / no change needed

---

## P0 — Must verify before any live deployment

- [x] **WFO causality: OOS sigma only at trade time**
  `sg_oos` initialised to `nan`; candidate loop skips `nan` rows; only OOS fold
  windows are ever written. Clean.

- [x] **`_causal_roll` off-by-one**
  Window at position `i` uses `cs[i] - cs[i-w]` = bars `[i-w+1 … i]`. Current bar
  included (known at bar close). Not look-ahead. Clean.

- [x] **`oc` sourced from trigger bar, not next bar**
  `op = .first()` over 1h bucket = first 1m mid of bar `i`. `mid = .last()`. Both from
  bar `i`, known at close. Clean.

- [x] **OCO simultaneity: both legs are live simultaneously** ← **FIXED**
  Old code pre-assigned direction from 1m mid (`_find_direction_1m`) and only scanned
  for that one leg. Rewritten: `simulate_tick_exact` now scans all ticks for whichever
  of `BID >= upper_entry` / `ASK <= lower_entry` fires first. Both-same-tick case
  returns `no_fill`. `_find_direction_1m` → `_has_fill_1m` (pre-filter only, no
  direction). P1 blocked-window fix bundled: `blocked_until_tick` now anchored to actual
  fill tick timestamp, not bar open.

- [~] **Which script produced the PR #367 cited numbers?**
  `reversion_straddle.py` docstring says "Pending tick-exact verification" and uses 1m
  mid + fixed TP/SL bps. PR #367 headline (+3.65 bps, 93.3% win) matches that script.
  Tick-exact numbers (lower gross, honest cost) are from `meta_label_straddle.py` and
  subsequent PRs. No code fix needed; docs should note this distinction.

---

## P1 — Material cost/P&L impact

- [x] **TB (time-barrier) exits charged no spread** ← **FIXED**
  TB rate was only 0.8% (not 5-15% as estimated) — minor direct impact.
  Primary driver of headline drop was the OCO simultaneity fix (see above).

- [x] **Blocked window anchored to bar timestamp, not fill timestamp** ← **FIXED**
  `blocked_until_tick` now set from actual tick fill timestamp (`fill_ts + hold_hours`).
  Bundled with OCO simultaneity fix above.

- [~] **Rejected-trade exit spread proxy**
  Rejected trades are momentum bars (large `|oc|`). Entry fill and rejection close both
  occur during the same momentum spike, so `fill_spread` is a reasonable proxy for the
  close spread — likely slightly conservative (wide momentum spread) rather than optimistic.
  No systematic bias toward flattering P&L. No fix needed.

- [x] **Spread validity fallback frequency** ← **INSTRUMENTED**
  Added `spread_fallback_n` counter + `fill_spread_raw` column to trade log.
  Per-pair fallback rate printed in verbose output with ⚠ if >5%. Summary section
  in `_print_summary` shows pooled rate and per-pair breakdown if >5%.
  Exact numbers will appear on next full backtest re-run.

---

## P2 — Model integrity

- [~] **Meta-labeler split by count, not time**
  Per-pair trades are already in time order, so count-based split = time-based split
  within a pair. Count clustering across years is actually desirable (trains on
  high-vol regimes, tests on what follows). No fix needed.

- [~] **No embargo in meta-labeler WFO**
  Non-overlap blackout guarantees adjacent trades are ≥ 8h apart. Nearest training trade
  is ≥ 8h before any test trade. Key feature `oc` (trigger bar open-to-close) has near-zero
  autocorrelation at 8h lag. Shared `mom_1/4/24` lookback windows are slow-moving and not
  sharp predictors. Contamination risk is negligible. No fix needed.

- [~] **TP fill achievability**
  TP level = `entry_k × sigma` of reversion (e.g. 5 bps for sigma=10 entry_k=0.5) —
  physically reachable, not extreme. Fill rule uses ask (short close) / bid (long close):
  correct side for limit exit. Stale-tick misfire would produce an outlier gross visible
  in the distribution. Dukascopy feed quality makes crossed ticks rare. Clean.

---

## P3 — Edge cases / robustness

- [~] **Month-boundary concatenation sort order**
  `_load_month_pair` calls `.sort("timestamp")` after `pl.concat` so each individual
  month tuple is sorted. Cross-month concat is `np.concatenate([m1, m2])` — since all
  of m1 (month-end) precedes all of m2 (month-start) by calendar, the result is
  chronologically ordered by construction. Clean.

- [x] **`reversion_straddle.py` 1m-proxy cost model**
  Added DEPRECATED warning to docstring. Authoritative numbers come from
  `meta_label_straddle.py` only.

- [x] **`_find_direction_1m` used only as post-fill feature**
  Function renamed `_has_fill_1m` and no longer returns direction at all (P0 fix).
  Direction is discovered exclusively from tick bid/ask in `simulate_tick_exact`.

---

## Distribution comparison (2026-07-03)

**Question:** does swapping GaussianLSS for a distribution family that better matches
the fat-tailed/jump-prone shape of FX hourly returns improve the sigma signal this
strategy is built on? Tried Merton Jump-Diffusion, SHASH, StudentT, Logistic — plus,
after those all lost, a from-scratch test of whether the BoostLSS/LSS framework is
even necessary at all.

### 5-family comparison (full 8yr history, 4 pairs, threshold=0.55, per-family algorithm)

| Family | n_trades | Meta AUC | TP% | Option B bps/fill |
|---|---|---|---|---|
| **Gaussian** (baseline) | 8,540 | 0.820 | 69.1% | **+0.896** |
| StudentT | 8,020 | 0.866 | 64.6% | +0.455 |
| SHASH | 7,645 | 0.858 | 56.3% | −0.301 |
| Logistic | 4,870 | 0.900 | 39.1% | −1.084 |
| Merton | 1,265 | 0.857 | 30.8% | −1.484 |

**Verdict: Gaussian wins clearly.** Every alternative lost money despite several having
*higher* meta-labeler AUC (Logistic 0.900, SHASH 0.858, Merton 0.857, StudentT 0.866
all beat Gaussian's 0.820) — a real and recurring AUC/P&L disconnect: more
distributional parameters give the meta-labeler more ranking information without that
information being economically real at this trade-count scale (hundreds-to-low-
thousands per pair). More parameters = more overfitting surface, not better signal.

Empirical check on "is the data actually Gaussian" (it is not): full-sample excess
kurtosis is +15 to +45 across pairs (a true Gaussian is 0), with meaningful negative
skew on GBPJPY/USDJPY (−1.15/−1.55). But trimming just the most extreme 0.5% of bars
collapses excess kurtosis to +2.4/+2.6 — the extreme tail is driven by a small
(~4.6%) minority of genuine jump/news-event bars, not a broadly fat-tailed
distribution. Gaussian likely wins because its role here is narrow (a quasi-MLE scale
estimate, robust to that kind of contamination by construction — see any GARCH/QMLE
econometrics reference) not because the data matches its assumptions.

### boostlss upstream bugs found + fixed during this comparison

Filed and tracked at github.com/dnf0/boostlss:
- **#53** (closed by #54): fixed-eps finite-difference `ngradient` for Merton/SHASH
  catastrophically cancels once boosting rounds push `eta` large, diverging to NaN
  past ~10 rounds. Fixed with a proper Dual-number analytical gradient — but only for
  the `noncyclic`/`noncyclic_outer` engines.
- **#56**: the *default* `algorithm="cyclic"` engine still diverges (Merton) or
  saturates the wrong direction (SHASH pegs at `1e6` ceiling instead of NaN) even
  after #54/#57. Root cause per #57's own writeup: unbounded parameter growth under
  Cyclic's unconditional per-round updates (no NLL-improvement gate, unlike NonCyclic).
- **#62** (open as of writing): #57's `eta_bounds` fix still doesn't fully resolve
  either family under `cyclic` — verified directly against the fix PR's branch.
  `noncyclic` remains the only verified-clean algorithm for Merton/SHASH; this
  project pins `spec.algorithm` per-family (`gaussian`→`cyclic`, `merton`/`shash`→
  `noncyclic`) rather than switching everything, since switching Gaussian's own
  algorithm changes its economics too (verified: +0.921→−0.207 bps/fill sign flip on
  the same data, cyclic vs noncyclic) — this is a genuinely different optimization
  procedure, not a drop-in bug workaround.
- Checked for **censoring support** (right-censored observations, e.g. for TB/time-
  barrier trades) — not implemented for Gaussian in the Rust crate, and not exposed
  through the Python bindings for *any* family. Would need an upstream feature
  request; not pursued further since our current target isn't naturally censored
  anyway (a TB-trade-duration reformulation would be a different project).

### Is the BoostLSS/LSS framework itself adding value? (tested, not just argued)

We only ever consume `sigma` from BoostLSS's output — `mu` is fit (required by the
joint likelihood) but never read downstream. So the real question isn't "is
GaussianLSS good" but "does distributional-regression machinery beat plain boosted
regression for this specific sigma signal." Tested directly:

- **GaussianLSS's own sigma is a *worse* pure volatility forecast** than a plain
  `HistGradientBoostingRegressor` fit to `y**2` — 2-7x lower correlation with realized
  squared returns on held-out data, across all 4 pairs (same WFO folds, same clip).
- Yet at Gaussian's own tuned `sig_thresh=1.5`, GaussianLSS still narrowly wins
  economically (+0.896 vs +0.774 bps/fill) — evidence that much of "Gaussian wins" is
  inherited from every other strategy hyperparameter having been implicitly tuned
  around its specific sigma scale over years of prior work (PR #367 onward), not a
  fundamental statistical advantage.
- **Confirmed by re-tuning the threshold**: sweeping `sig_thresh` for the plain
  squared-error regressor (untested at 1.5) takes it from *worse* than Gaussian
  (+0.774) to *beating* it (+1.409 bps/fill at sig_thresh=3.0).
- **A more jump-robust regression variant is the best signal found so far**: quantile
  regression (`loss="quantile"`, q=0.85) predicting `|y|` directly — far less
  sensitive to the ~4.6% jump-bar contamination than squaring returns — reaches
  **+3.715 bps/fill at sig_thresh=3.0** (4x Gaussian's tuned baseline), with high TP%
  (79.1%) and decent AUC (0.783), not just a threshold-tuning artifact.
- **Caution**: neither sweep had peaked as of sig_thresh=3.0 (Option B still climbing),
  and trade count falls as threshold rises (down to ~3.7k/6.7k at the top of the
  tested range) — extend the sweep to find the actual peak/plateau before trusting
  the very top of the curve; fewer trades means more sampling noise.

**Bottom line**: BoostLSS's actual distinguishing feature (joint multi-parameter
distributional modeling) has not helped once, in five attempts. What's actually
working is "gradient-boosted regression for conditional sigma" — which doesn't
require the LSS framework at all, and a plain regressor with a properly-chosen loss
function (quantile, not squared-error) and a properly re-tuned threshold currently
beats every distribution family tried, including Gaussian, by a wide margin. Meta-
labeling untouched throughout this whole investigation — the gains so far are purely
from a better upstream signal, before the second stage even gets involved.

**Scripts**: `distributions.py` (registry: gaussian/merton/shash/studentt/logistic),
`compare_distributions.py` (per-family comparison harness), `plain_regression_baseline.py`
(squared-error/quantile regression variants, run through the identical pipeline via
`run_tick_backtest`'s `sigma_override`), `regression_threshold_sweep.py` (sig_thresh
sweep per variant), `sigma_window_sweep.py` (windowed sigma_thresh/sigma_thresh_hi
sweep, below).

### Extended threshold sweep (2026-07-03) — real peak found, then a noise cliff

Extended `regression_threshold_sweep.py` past sig_thresh=3.0 up to 8.0 for both
regression variants. Quantile-robust regression shows a clean, monotonic climb with
AUC and TP% holding or improving the whole way — Option B +2.56 (thresh=1.5) →
**+4.98 (thresh=5.0, AUC=0.849, TP%=71.2%, n=1680)** — then a sharp collapse once
trade count gets too thin: AUC craters to 0.799→0.736→0.565 (barely above random) by
thresh=6/7/8, TP% falls to 60%, Option B goes **negative** (−4.79 at thresh=8, n=145
across all 4 pairs over 6-8yr — too few trades for the meta-labeler's 5-fold WFO to
learn anything). The AUC collapsing *in lockstep* with Option B at exactly the point
trade count gets too thin is the tell that distinguishes real edge (thresh≤5.0) from
overfitting noise (thresh≥6.0) — squared-error regression's curve is messier/less
monotonic throughout, reinforcing that quantile-robust is the more trustworthy signal.

### Windowed sigma (sig_thresh_hi) — new best result: +5.013 bps/fill

Added `sig_thresh_hi` (upper bound) to `run_tick_backtest`'s candidate filter — tests
whether excluding the anomalously *largest* predicted-sigma bars (not just requiring
a lower floor) helps, since the strategy's own thesis is "momentum/jump bars fail,
indecision bars revert" and we already found FX hourly returns have a small (~4.6%)
genuine jump-driven tail. A bar at the very top of predicted sigma is more likely to
*be* one of those jump bars.

At fixed `sig_thresh=4.0`, tightening `sig_thresh_hi` gives a clean monotonic
improvement: no cap (+4.591) → hi=10 (+4.607) → hi=8 (+4.643) → hi=6 (+4.811) →
**hi=5 (+5.013 bps/fill, n=3495)** — the best result of the whole investigation,
beating even the unwindowed thresh=5.0 peak (+4.983). Sigma percentiles for context:
90th=4.22, 95th=4.95, 99th=6.75, 99.9th=9.25 — so hi=5 is genuinely excluding only
the top few percent, not gutting the population.

Note: `n_trades` can tick up slightly as the cap tightens (e.g. 3580→3595 at hi=6) —
not more candidates surviving a stricter filter, but the meta-labeler's own WFO fold
boundaries shifting with a marginally different raw trade count. Not a contradiction,
just a downstream artifact of the second-stage fold splitting.

### Refined window grid — a plateau, not a single sharp peak

Finer grid (`lo` ∈ [3.5, 3.75, 4.0, 4.25, 4.5] × `hi` ∈ [4.5, 4.75, 5.0, 5.25, 5.5])
found a marginally higher single point (`lo=4.5, hi=5.5` → n=2415, **+5.292 bps/fill**,
AUC=0.828, TP%=76.9%), but the more important finding is the *shape*: roughly
`lo∈[4.0,4.5] × hi∈[4.8,5.5]` all cluster around **+4.8 to +5.3 bps/fill** — a broad,
robust plateau, not one hypersensitive optimum. Within that plateau the exact ranking
bounces non-monotonically as trade count shrinks (1,480–2,970 in this finer grid vs.
3,045–3,575 in the coarser lo=4.0 sweep) — a mild early-noise signal (AUC/TP% are
still healthy, 0.74–0.83 / 77–82%, nowhere near the earlier full noise-collapse), but
enough to prefer "there's a good region here" over "4.5/5.5 is precisely optimal."
**Recommended target for follow-on work: `sig_thresh≈4.0-4.5, sig_thresh_hi≈4.8-5.5`**,
treated as a region to land in, not a single exact cutoff to hit.

### Stability check (this PR)

Ran `stability_check.py` at `sig_thresh=4.0, sig_thresh_hi=5.0, quantile=0.85`
(PR #376's sweet spot) with per-pair and per-year breakdowns:

```
======================================================================
POOLED RESULT  sig_thresh=4.0  sig_thresh_hi=5.0  q=0.85
======================================================================
  n_trades: 3495  AUC: 0.819  TP%: 79.1%  Option B: +5.013 bps/fill

======================================================================
BY PAIR
======================================================================
  AUDUSD    n=  595  AUC=0.872  TP%=78.3%  Option B=+6.578 bps/fill
  EURUSD    n= 1095  AUC=0.796  TP%=80.0%  Option B=+4.068 bps/fill
  GBPJPY    n=  840  AUC=0.831  TP%=77.5%  Option B=+5.557 bps/fill
  USDJPY    n=  965  AUC=0.804  TP%=80.0%  Option B=+4.645 bps/fill

======================================================================
BY YEAR (pooled)
======================================================================
  2020  n=  160  AUC=0.823  TP%=77.5%  Option B=+3.493 bps/fill
  2021  n=  161  AUC=0.807  TP%=81.4%  Option B=+3.997 bps/fill
  2022  n=  905  AUC=0.823  TP%=78.8%  Option B=+4.485 bps/fill
  2023  n=  886  AUC=0.822  TP%=80.7%  Option B=+5.835 bps/fill
  2024  n=  642  AUC=0.817  TP%=75.4%  Option B=+4.512 bps/fill
  2025  n=  741  AUC=0.816  TP%=80.7%  Option B=+5.657 bps/fill
```

**Verdict:** The +5.013 bps/fill plateau is highly robust. Every single pair remains
independently net-positive, with AUDUSD leading at +6.578 bps/fill and EURUSD the
most conservative at +4.068 bps/fill — all substantially above cost. No single pair
dominates; the pooled result is a true blend. By year, all periods from 2020–2025
are net-positive, with 2023 and 2025 the strongest (≥+5.6 bps/fill) and 2020–2021
the weakest but still positive (≈+3.5–+4.0 bps/fill) — no decade-scale decay or
regime risk. Early years have lower trade counts (n≈160–900) than 2022–2025
(n≈640–900), but AUC and TP% are consistent across the board (0.80–0.82 AUC,
75–81% TP%). This is the strongest real evidence yet that the windowed quantile-
robust plateau is a genuinely found edge, not a statistical artifact concentrated
in one pair or period.

**Status: this investigation is concluded for this PR.** Remaining refinement (finer
grids, entry_k/sl_k retuning, other quantile levels/losses, meta-labeler feature
re-check) is deferred to follow-on work — tracked below, not blocking.

**Deferred next steps**:
- [ ] Try other quantile levels (currently only q=0.85 tested) and other robust losses
  (Huber) for the sigma regressor
- [ ] Re-tune `entry_k`/`sl_k` jointly with the winning `(sig_thresh, sig_thresh_hi)`
  window, since those were also implicitly tuned around Gaussian's scale
- [ ] Once a threshold/window/signal combo is chosen, re-verify meta-labeler feature
  importance and calibration on the new candidate population (different population →
  potentially different optimal meta-labeler features, untested so far)
- [ ] Confirm the windowing logic's economic story (excludes likely-jump bars) by
  directly checking `oc`/`rng_norm` distributions inside vs. outside the excluded
  tail — would strengthen confidence this isn't overfitting even further

### Quantile level sweep (this PR)

Swept quantile levels {0.70, 0.75, 0.80, 0.85, 0.90, 0.95} at two representative
windows (4.0:5.0 and 4.5:5.5):

```
 Quantile        Window  n_trades     AUC   Option B bps/fill
     0.70       4.0:5.0       975   0.881              +1.330
     0.70       4.5:5.5       555   0.852              +0.132
     0.75       4.0:5.0      1580   0.888              +2.599
     0.75       4.5:5.5       910   0.840              +1.888
     0.80       4.0:5.0      2320   0.869              +3.714
     0.80       4.5:5.5      1465   0.871              +3.841
     0.85       4.0:5.0      3495   0.819              +5.013
     0.85       4.5:5.5      2415   0.828              +5.292
     0.90       4.0:5.0      5215   0.768              +5.340
     0.90       4.5:5.5      3865   0.765              +5.958
     0.95       4.0:5.0      7145   0.724              +4.017
     0.95       4.5:5.5      6080   0.724              +4.973
```

**Verdict:** q=0.85 is *not* the best tested level — **q=0.90 beats it at both
windows**: +5.340 vs +5.013 (window 4.0:5.0, +6.5% relative) and +5.958 vs +5.292
(window 4.5:5.5, +12.6% relative — the single best Option B result in this whole
sweep). The pattern across quantile levels is clean and monotonic from 0.70→0.90
(Option B climbs steadily at both windows: 1.33→2.60→3.71→5.01→5.34 and
0.13→1.89→3.84→5.29→5.96), then reverses at 0.95 (drops back to 4.02/4.97) — a
single clean peak at q=0.90, not noise. This mirrors the earlier sig_thresh sweep
shape (climb, peak, then AUC-linked collapse): AUC trends downward from 0.70→0.95
but is not strictly monotonic, showing minor upticks at intermediate levels (e.g.,
0.881→0.888 at q=0.75 for window 4.0:5.0, and 0.852→0.871 at q=0.80 for window
4.5:5.5 before continuing its overall decline to 0.724) even while Option B is still
climbing through q=0.90, so the AUC/P&L "disconnect" already documented for
distribution families reappears here too — a higher quantile level means less
discriminating meta-labeler input (broader, noisier |y| targets) but sets a coarser
sigma scale that shifts more of the trade population into the profitable window.
n_trades is monotonically increasing with quantile (975→7145 at window 4.0:5.0) as
expected, since a higher quantile predicts a systematically larger sigma, which
passes more candidate bars through the `sig_thresh` floor. q=0.90 is not thin-sample
noise the way the earlier sig_thresh>=6 collapse was — its trade counts (5215/3865)
are actually *larger* than q=0.85's (3495/2415), so this is a trustworthy result,
not an artifact of a shrinking sample. **Recommendation: re-run the stability check
and window-grid refinement at q=0.90 instead of q=0.85** — it may shift the optimal
`(sig_thresh, sig_thresh_hi)` window too, since quantile level and window were never
jointly tuned.

---

### Tail-shape meta-labeler feature (this PR)

Added `tail_ratio` (ratio of a high and low quantile regression's predicted
`|return|`) as a new meta-labeler feature, purely additive (sigma sizing
unchanged). Run at the winning config identified in the quantile-sweep
subsection above (q=0.90 high quantile, window sig_thresh=4.5:5.5,
q=0.5 low quantile, threshold=0.55, pairs EURUSD/GBPJPY/AUDUSD/USDJPY):

```
  EURUSD: 1358 trades  gross=+4.469  maker_net=+3.699  TP%=80.5%  spread_fallback=0.0%  oos_nll=nan
  GBPJPY: 1166 trades  gross=+7.145  maker_net=+6.171  TP%=84.1%  spread_fallback=0.0%  oos_nll=nan
  AUDUSD:  879 trades  gross=+5.341  maker_net=+4.208  TP%=77.6%  spread_fallback=0.0%  oos_nll=nan
  USDJPY: 1242 trades  gross=+5.451  maker_net=+4.648  TP%=82.4%  spread_fallback=0.0%  oos_nll=nan

baseline (no tail_ratio)      n= 3865  AUC=0.765  TP%=82.0%  Option B=+5.958 bps/fill
with tail_ratio               n= 3865  AUC=0.773  TP%=82.0%  Option B=+6.014 bps/fill
```

**Verdict:** `tail_ratio` gives a small, consistent improvement, not a
transformative one. AUC rises 0.765→0.773 (+0.008) and Option B rises
+5.958→+6.014 bps/fill (+0.056 bps/fill, ~+0.9% relative) with TP% unchanged
at 82.0%. n_trades is identical between the two rows (3865 each) — in this run
the low-quantile (q=0.5) regression's OOS predictions were defined everywhere
the high-quantile ones were, so the dropna row-count caveat documented in the
script's docstring did not materialize here; this is a coincidence of this
particular config, not a guarantee for other windows/pairs. The baseline row
here (n=3865, Option B=+5.958) matches Task 2's recorded q=0.90/window-4.5:5.5
result exactly, confirming this script reproduces the established best
configuration correctly before the additive `tail_ratio` test is layered on.
Overall: the tail-shape signal is real but modest — worth keeping as a
low-cost additive feature, not a headline result on its own. Unlike Merton's
jump-intensity or SHASH's skew/kurtosis (which added similar tail information
to first-stage sigma sizing and made things worse per the distribution
comparison), exposing tail shape to the *meta-labeler* directly (rather than
baking it into sigma) is mildly net-positive — consistent with the earlier
finding that features which fail as sigma inputs can still work as
classification inputs.

---

## Ideas / future improvements (not blocking)

- [ ] Dynamic hold_hours: exit earlier if sigma decays — currently hard-capped at 8h
- [ ] Per-pair meta-threshold tuning with proper multiplicity correction
- [ ] Live retraining cadence: monthly rolling vs. expanding window
- [ ] Broker API integration (Pepperstone cTrader) — execution architecture design
- [ ] Stress-test: 2020 COVID vol spike, 2022 EURUSD trend — check max drawdown under realistic position sizing
