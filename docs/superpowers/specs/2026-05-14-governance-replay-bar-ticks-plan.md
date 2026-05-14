# Generalize governance replay to support 1000-tick bars

## Problem

Live production uses `bar_ticks = 1000` across all symbols (every `configs/research/governance/oco/*_oco_live_lock.json` declares 1000; the live runtime DB has only 1000-tick candidate UIDs). The governance replay infrastructure that runs alongside live (`diagnose_live_replay.py`, consumed by `diagnostics/live_governance_deviation.py`) is hardcoded to 100-tick bars and rejects everything else with `unsupported_governance_state`. Result: every governance-vs-live deviation run today emits zero replayed signals and the live system has no in-distribution way to ask "would the strategy have taken these trades and lost?"

## Scope

In:
- Parameterize bar construction in `scripts/diagnose_live_replay.py::_build_bars_from_ticks` on `bar_ticks` (currently hardcoded to literal `100` and `99.0`).
- Pass `bar_ticks` through `_score_bars` and the replay entry point so the value comes from `state["bar_ticks"]`.
- Drop the `bar_ticks != 100` gate in both `diagnose_live_replay.py::_score_bars` and `src/behemoth/diagnostics/live_governance_deviation.py:416`.
- Update `tests/test_live_governance_deviation.py` to exercise the 1000-tick path.

Out:
- Any change to the production live runtime (already 1000-tick).
- Any change to feature engineering — `compute_feature_matrix_from_bars` already takes `bar_ticks` as a parameter and uses it correctly.
- k2/k3 dual-fire (user has confirmed it is by design).
- Backfilling prior governance deviation runs.

## Files

| File | Change |
|---|---|
| `scripts/diagnose_live_replay.py` | `_build_bars_from_ticks(ticks)` → `_build_bars_from_ticks(ticks, *, bar_ticks)`. Replace literal `100` (lines 89, 109, 116, 124, 125, 207) with the parameter. Replace `99.0` (line 163) with `float(bar_ticks - 1)`. `_score_bars` reads `bar_ticks` from `state` and threads it into `_build_bars_from_ticks` call sites (lines 394, 704). Drop the `if bar_ticks != 100` early-return at lines 369-386. Update the docstring at line 89. |
| `src/behemoth/diagnostics/live_governance_deviation.py` | Remove the `if int(state.get("bar_ticks", 100)) != 100` gate at lines 416-429 (the `unsupported_governance_state` finding). `_score_bars` will now succeed for 1000-tick states. |
| `tests/test_live_governance_deviation.py` | Add a happy-path test with `bar_ticks=1000` exercising the full deviation pipeline on a synthetic tick stream large enough to yield several 1000-tick bars (≥ ~5000 ticks). Confirm `governance_predictions` is non-empty and `findings.csv` no longer contains `unsupported_governance_state`. |

## Verification

1. `uv run pytest -q tests/test_live_governance_deviation.py` passes.
2. Re-run the governance deviation diagnostic against an existing live snapshot:
   ```
   uv run python -m behemoth.diagnostics.live_governance_deviation \
     <existing snapshot args>
   ```
   Confirm:
   - `findings.csv` no longer contains rows with `code = unsupported_governance_state`.
   - `*_governance_predictions.parquet` files are non-empty.
   - `signal_deviation.csv` shows non-zero `governance_selected_signal_count`.
   - `outcome_deviation.csv` shows non-zero `governance_selected_signal_count`.
3. Sanity-check parity: on the same tick stream, governance bar count should equal live bar count to within partial-final-bar tolerance. Existing `bar_deviation.csv` `max_abs_close_delta_pips` is ~1e-12; should remain so.

## Risks

- The hl_pos_frac denominator `99.0` assumes 100-tick bars exactly. Generalizing to `bar_ticks - 1` preserves the invariant that `hl_pos_frac` ∈ [-1, 1] for any bar size, but tests should explicitly cover both 100 and 1000 to catch arithmetic errors.
- Replay may have been emitting an empty result on bar_ticks ≠ 100 for so long that downstream consumers expect empty data; check whether any code branches on empty governance predictions in a way that would surprise on real data. Grep `governance_predictions` callers.
- Larger bars mean fewer bars per tick stream — warmup requirements (16-feature pipeline) may starve on short windows. Not a code bug; an operational note.

## Out-of-scope follow-ups

- Validate that the existing live 1000-tick snapshot, when replayed end-to-end, produces governance-selected signals that match (or are explained by) the live-selected signals. That's the actual question the originator asked. Once this fix lands, that comparison becomes runnable.
