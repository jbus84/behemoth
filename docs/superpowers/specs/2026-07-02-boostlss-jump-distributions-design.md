# BoostLSS Alternative Distributions — Jump-Diffusion & SHASH

## Context

The reversion-OCO straddle strategy (`scripts/boostlss_xs/meta_label_straddle.py`) uses
BoostLSS `GaussianLSS` to predict `(mu, sigma)` per 1h bar and sizes OCO entry/SL levels
from the predicted `sigma`. Post-bugfix re-run (PR #374) established an honest baseline:
Option B all-in **+0.634 bps/fill** (17 pairs, excl 18-21 UTC, threshold=0.55).

The upstream `boostlss` crate (git dependency, locked at commit `6b9924e`) has since gained
two new distributional families not yet available in our pinned version:

- **Merton Jump-Diffusion** (`MertonJumpDiffusionLss`) — 5 params: `mu`, `sigma` (diffusion
  drift/vol), `lam` (jump intensity, Poisson rate), `mu_j`, `sigma_j` (jump size mean/vol).
  Separates continuous diffusion from discrete jump risk — directly relevant to a strategy
  whose core finding is "momentum bars fail / indecision bars revert" (jumps ≈ momentum
  continuation risk).
- **SHASH** (`SHASHLss`) — 4 params: `mu`, `sigma`, `nu` (skew), `tau` (kurtosis). Captures
  fat tails and asymmetry that Gaussian cannot.

Upstream HEAD is `47cc78e`, `31` commits ahead of our pin, including the family additions
(`ff851f2`, `857f64b`) and unrelated work (categorical trees, early stopping) that comes
along for the ride but doesn't need engagement.

## Goals

1. Determine whether Merton Jump-Diffusion or SHASH sigma predictions improve OOS
   distributional fit and/or Option B all-in bps/fill versus the GaussianLSS baseline.
2. Determine whether Merton's jump-intensity (`lam`) is a useful new meta-labeler feature —
   the hypothesis being that high predicted jump risk correlates with SL outcomes (momentum
   continuation defeats the reversion trade).
3. Keep the comparison fast and cheap: prove the concept on a small pair subset before
   committing to a full 17-pair run.

## Non-goals

- Not replacing GaussianLSS as the production family until a clear win is shown.
- Not implementing total-variance sizing (diffusion + jump) for Merton — diffusion-only
  sigma is used for OCO sizing, keeping entry_k/sl_k semantics identical to the baseline
  for a clean comparison. Jump risk is captured via the meta-labeler feature, not sizing.
- Not building a general-purpose distribution plugin system beyond what's needed for these
  three families.

## Architecture

### 1. Dependency bump

Bump `boostlss` git pin in `pyproject.toml` (`tool.uv.sources`) from `6b9924e` to upstream
HEAD `47cc78e`. Run `uv sync` and a smoke test:

```python
from boostlss_py import MertonJumpDiffusionLss, SHASHLss, BoostLssModel, PyLinearLearner
```

before touching any strategy code.

### 2. `scripts/boostlss_xs/distributions.py` (new)

A small registry describing each candidate family:

```python
@dataclass
class DistSpec:
    name: str                          # "gaussian" | "merton" | "shash"
    make_family: Callable[[], object]  # () -> boostlss_py family instance
    param_names: list[str]             # learner params, e.g. ["mu","sigma","lam","mu_j","sigma_j"]
    sizing_param: str                  # which predicted param feeds OCO entry/SL ("sigma" for all three)
    extra_features: list[str]          # additional params exposed to meta-labeler (e.g. ["lam"], ["nu","tau"], [])

REGISTRY: dict[str, DistSpec] = {
    "gaussian": DistSpec("gaussian", lambda: PyFamily("GaussianLSS"),
                          ["mu", "sigma"], "sigma", []),
    "merton":   DistSpec("merton", lambda: MertonJumpDiffusionLss(max_jumps=10),
                          ["mu", "sigma", "lam", "mu_j", "sigma_j"], "sigma", ["lam"]),
    "shash":    DistSpec("shash", lambda: SHASHLss(),
                          ["mu", "sigma", "nu", "tau"], "sigma", ["nu", "tau"]),
}
```

### 3. Generalize WFO fitting

`fit_wfo_gaussian` in `meta_label_straddle.py` generalizes to `fit_wfo_dist(X, y, spec: DistSpec)`:
- Adds one `PyTreeLearner` per `spec.param_names` (was hardcoded `["mu", "sigma"]`).
- Returns a `dict[str, np.ndarray]` of OOS predictions keyed by param name, not a single
  sigma array.
- Same 5-fold expanding WFO with `te_start = tr_end + 8` embargo — unchanged.
- Also computes and returns per-fold OOS NLL (diagnostic metric) using the fitted model's
  known negative-log-likelihood, for the "fit quality" side of the comparison.

### 4. `run_tick_backtest` — family-aware

Gains a `family: str = "gaussian"` argument (looked up in `REGISTRY`):
- Sizing sigma comes from `preds[spec.sizing_param]` — drop-in identical to current
  `sbps = np.clip(sg_oos * mad, 0.0, 200.0)` logic, just sourced from the dict.
- Extra params in `spec.extra_features` are merged into each trade row (e.g. `jump_lam`,
  `shash_nu`, `shash_tau`) and appended to a **per-run** `_FEAT_COLS` list — so a GaussianLSS
  run's trade log has no NaN jump/skew columns, and vice versa.
- All existing cost-model logic (fill-time spread, TB=taker, Option B post-fill filter)
  is unchanged and reused as-is.

### 5. `scripts/boostlss_xs/compare_distributions.py` (new)

Orchestrates the comparison:
- Pairs: `EURUSD, GBPJPY, AUDUSD, USDJPY` (mix of tight/wide spread, major/cross).
- For each of `gaussian`, `merton`, `shash`: run WFO → tick-exact backtest → meta-labeler
  fit (with family-appropriate `_FEAT_COLS`).
- Print a side-by-side table:

  | Family   | OOS NLL (avg) | Meta AUC | TP%  | Option B all-in bps/fill |
  |----------|----------------|----------|------|---------------------------|
  | gaussian | ...            | ...      | ...  | ...                       |
  | merton   | ...            | ...      | ...  | ...                       |
  | shash    | ...            | ...      | ...  | ...                       |

- If `merton` wins or is competitive, also report meta-labeler feature importance to check
  whether `jump_lam` ranks meaningfully (validates hypothesis #2 independent of whether
  sigma quality itself improved).

## Error handling

- WFO fold fit failures (convergence issues, degenerate MLE) are caught per-pair/family and
  logged, not fatal — matches existing `except Exception as e: print(...)` pattern in
  `fit_meta_label_wfo`'s per-pair loop.
- NaN `lam`/`nu`/`tau` predictions for a fold are handled by the existing
  `dropna(subset=_FEAT_COLS)` in `fit_meta_label_wfo` — rows with NaN extra-features are
  excluded from meta-labeler training/scoring for that fold only, not the whole run.
- Merton's NLL involves an inner sum over `max_jumps` (default 10) per observation, so WFO
  fits will be measurably slower than 2-param Gaussian. No special handling needed beyond
  the 4-pair scope decision — full 17-pair promotion happens only after a family wins.

## Testing / acceptance

- No new pytest coverage (matches existing informal validation pattern for this codebase's
  research scripts — run + inspect printed summary).
- Acceptance: `compare_distributions.py` runs cleanly end-to-end for all 3 families on the
  4 test pairs and prints the side-by-side table without crashing.
- If a family clearly wins on Option B all-in bps/fill (and the diagnostic NLL doesn't
  contradict it), promote to a full 17-pair run using the same harness used for the
  post-bugfix re-run (PR #374), and update `config.py` accordingly.

## Open questions for later (not blocking this spec)

- Whether SHASH's `nu`/`tau` should also gate OCO placement (pre-filter) similar to the
  jump-filter idea, if the meta-labeler shows they matter.
- Whether a full 17-pair promotion needs its own WFO embargo/split tuning pass, or reuses
  current settings as-is.
