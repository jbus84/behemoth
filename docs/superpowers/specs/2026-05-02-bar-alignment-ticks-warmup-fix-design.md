# Bar Alignment Ticks — warmup load fix

**Date:** 2026-05-02
**Status:** Design

## Goal

Make the warmup tick pre-load align bar boundaries to the candidate's `bar_ticks` instead of a hard-coded 100, so the runtime's open-bar accumulator at start matches what governance had at the same moment. Same fix in matrix runners (Python) and the live runtime warmup loader (Java). Introduce **Bar Alignment Ticks** as the canonical term and remove the misleading "phase bar ticks" name.

## Context

Stage 14 outcome parity for 2026-04 fails for 5/6 symbols at 85–98% coverage despite Stage 13 passing. Investigation traced this to the warmup loader sizing pre-load ticks with mod-100 alignment while candidates use 1000-tick bars. The runtime's open-bar accumulator at start_ts therefore differs from governance's by 0–999 ticks, shifting every subsequent 1000-tick bar boundary.

Confirming evidence on EURUSD 2026-04 monthly recert:

- Local surrogate (parquet ticks, same source as governance): 261/262 predict_cycle close_ts close *earlier* than nearest governance bar by a near-constant ~50s. Pure tick-count offset translated through varying tick rate.
- Real-JForex matrix (broker ticks): same pattern, larger time-deltas (varying 7–323s by day) due to varying tick rate.
- Local-surrogate and real-matrix both report 51/56 = 91.1% coverage on EURUSD — same shortfall, same root cause.

The bug location:

- `scripts/run_jforex_dukascopy_matrix.py:280` — `keep = warmup_ticks + (full_pre_count % phase_bar_ticks)` with `phase_bar_ticks=100`.
- `scripts/run_local_jforex_surrogate_matrix.py` — same pattern.
- `src/jforex/src/main/java/com/behemoth/jforex/live/HistoricalWarmupLoader.java:39` — same pattern; this is the **live runtime** warmup loader, so the bug also manifests in production.

`LiveReadinessCoordinator.java`'s `PHASE_BAR_TICKS=100` is unrelated — it's the bar size used for the live readiness signal (`warmup_bar_count_100` in `live_symbol_readiness.json`). Out of scope for this change; can be renamed to `READINESS_BAR_TICKS` in a follow-up if desired.

## Term — Bar Alignment Ticks

Add to `UBIQUITOUS_LANGUAGE.md` in the live-runtime-contract group:

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Bar Alignment Ticks** | The tick-count modulus used when sizing **Warmup** loads so the runtime's open-bar accumulator at start matches what governance had at the same moment. Equals the largest candidate `bar_ticks` in the active universe. | Phase bar ticks, alignment window |

Update the existing **Warmup** entry's aliases to also include "phase warmup".

## Matrix runners (Python)

Both `scripts/run_jforex_dukascopy_matrix.py` and `scripts/run_local_jforex_surrogate_matrix.py`.

**Hard rename, no compat shim:**

- CLI flag: `--phase-bar-ticks` → `--bar-align-ticks`.
- `RunConfig` field: `phase_bar_ticks` → `bar_align_ticks`.
- Env var (surrogate only): `BEHEMOTH_LOCAL_JFOREX_PHASE_BAR_TICKS` → `BEHEMOTH_LOCAL_JFOREX_BAR_ALIGN_TICKS`.
- The `bar_ticks` field of the `/backfill` payload in `_prime_api_with_warmup` continues to use `cfg.bar_align_ticks`.

**Default behaviour:**

- Default = `0` (auto sentinel), same pattern as `--warmup-ticks`.
- When auto: `align = max_bar_ticks_for_symbols(...)` from the existing `scripts/_matrix_warmup.py` helper. The same call already derives `warmup_ticks`, so the cost is one extra tuple element.
- Explicit `--bar-align-ticks N` overrides.
- On auto-derive, print a single line: `[matrix] auto-computed --bar-align-ticks=1000`.
- If auto-derive cannot find any locked predictions (helper returns `0`), the runner aborts with a clear error: `bar_align_ticks could not be auto-derived from <model_month> locked predictions; pass --bar-align-ticks explicitly`. Silent fallback would re-introduce the bug class.

**Alignment formula** in the warmup loader (renamed `_load_phase_aligned_warmup_ticks` → `_load_aligned_warmup_ticks`):

```python
align = int(cfg.bar_align_ticks)
keep = (int(cfg.warmup_ticks) // align) * align + (full_pre_count % align)
```

Replaces `keep = warmup_ticks + (full_pre_count % phase_bar_ticks)`. Property: `keep mod align == full_pre_count mod align`, so the runtime's open-bar accumulator at start_ts matches governance's by construction.

**Makefile** (`Makefile:311,325,337,360`): rename the `PHASE_BAR_TICKS` make var to `BAR_ALIGN_TICKS`; update the four invocation sites to pass `--bar-align-ticks $(or $(BAR_ALIGN_TICKS),0)` so the default is auto rather than 100.

## Live runtime warmup loader (Java)

`src/jforex/src/main/java/com/behemoth/jforex/live/HistoricalWarmupLoader.java`:

- Remove the `private static final int PHASE_BAR_TICKS = 100` constant.
- Replace line 39's `int keep = config.liveWarmupTicks() + (preCount % PHASE_BAR_TICKS);` with:

  ```java
  int align = config.liveBarAlignTicks();
  int keep = (config.liveWarmupTicks() / align) * align + (preCount % align);
  ```

`src/jforex/src/main/java/com/behemoth/jforex/config/JForexSessionConfig.java`:

- Add a new field `int liveBarAlignTicks` (positional after the existing `liveLookbackDays`).
- Validation: `liveBarAlignTicks <= 0` → fail fast at config construction.
- Wire the value through every construction site that builds a `JForexSessionConfig` — the production loader (env-driven), any harness/test loader, and unit-test fixtures. Each gains an explicit `liveBarAlignTicks` argument or env-var read; no defaults.
- For 2026-04 deployment: operator sets it to `1000` in the live config (matches the active candidate universe).

**Drift-detection assertion** in the live runtime startup path (kept conservatively close to where the candidate universe is loaded — exact placement during implementation): assert `max(candidate.bar_ticks for candidate in active_universe) == config.liveBarAlignTicks()`. Fail startup if not. Mitigates the footgun where the candidate universe expands to a larger `bar_ticks` without the operator updating the config.

`LiveReadinessCoordinator.java` is left unchanged — its `PHASE_BAR_TICKS=100` is genuinely about readiness reporting in 100-tick bars, not alignment.

## Tests

**Python:**

- `tests/test_run_jforex_dukascopy_matrix.py` — replace every `phase_bar_ticks=100` fixture with `bar_align_ticks=1000`; the inline test at line 372 keeps its small numeric (`bar_align_ticks=4`) for the unit-level coverage of the formula.
- `tests/test_run_local_jforex_surrogate_matrix.py` — same fixture rename.
- `tests/test_matrix_warmup.py` — add a regression test asserting the new formula with concrete numbers: `align=1000, warmup_ticks=346800, full_pre_count=2547832 → keep == 346000 + 832 == 346832`. Add a parametrised test for varied `(warmup_ticks, align, full_pre_count)` triples asserting `keep % align == full_pre_count % align`.

**Java:**

- `src/jforex/src/test/java/com/behemoth/jforex/live/HistoricalWarmupLoaderTest.java` (create if absent): for known `(liveWarmupTicks, liveBarAlignTicks, preCount)` triples, assert `keep mod liveBarAlignTicks == preCount mod liveBarAlignTicks`.
- `src/jforex/src/test/java/com/behemoth/jforex/config/JForexSessionConfigTest.java` — add a case asserting validation rejects `liveBarAlignTicks <= 0`.

**Operational sanity check (not a unit test):**

After the PR merges, re-run `make monthly-recert MODEL_MONTH=2026-04`. Expected:

- Local-surrogate `signal_coverage_ratio` for EURUSD: 0.911 → ~1.0.
- Real-JForex matrix EURUSD: 0.911 → high, possibly still <1.0 (residual broker-feed deficit, deferred).

If local-surrogate doesn't approach 1.0, the alignment fix didn't land where intended and we re-investigate before promoting.

## Out of scope / accepted risks

**Out of scope:**

- Real-JForex matrix broker-feed deficit (~1% fewer ticks vs parquet). Separate investigation; revisit once alignment is fixed.
- Renaming `LiveReadinessCoordinator.PHASE_BAR_TICKS`. It is the readiness-reporting bar size, not alignment. Optional follow-up.
- Auto-deriving `liveBarAlignTicks` from the candidate registry inside `HistoricalWarmupLoader`. Requires plumbing the registry through. Deferred; mitigated by the startup assertion that compares the configured value to the active universe's max `bar_ticks`.
- Migrating prior `data/analysis/backtest_reconcile/` evidence. Old reports stay as-is; new reports come from the next monthly recert.

**Accepted risks:**

- **Hard rename, no compat shim.** Cached `--phase-bar-ticks` invocations or old env-var consumers fail with a clean error. Desirable because the old value (100) silently produced the broken alignment.
- **`liveBarAlignTicks` is a required config field.** Pre-existing live deployments that don't set it fail to start. Operator runbook update required.
- **Matrix default change (100 → auto).** Re-running cert on the same locked candidate set produces different bars vs the previous (broken) cert. Bar-by-bar comparison across the boundary is not meaningful.

## Operator runbook deltas

- Live runtime config now requires `liveBarAlignTicks` (current value: `1000`).
- Matrix CLI: `--bar-align-ticks 0` (default) auto-derives; pass an explicit value to override.
- Makefile: `BAR_ALIGN_TICKS=` replaces `PHASE_BAR_TICKS=` for explicit overrides.

## Files referenced

- `UBIQUITOUS_LANGUAGE.md` — add Bar Alignment Ticks term, update Warmup aliases.
- `scripts/run_jforex_dukascopy_matrix.py` — rename + alignment formula.
- `scripts/run_local_jforex_surrogate_matrix.py` — rename + alignment formula.
- `scripts/_matrix_warmup.py` — used to derive `align` (no API change required).
- `Makefile` — rename make var and CLI flag at four invocation sites.
- `src/jforex/src/main/java/com/behemoth/jforex/live/HistoricalWarmupLoader.java` — remove `PHASE_BAR_TICKS`, use `liveBarAlignTicks` from config, fix formula.
- `src/jforex/src/main/java/com/behemoth/jforex/config/JForexSessionConfig.java` — add `liveBarAlignTicks` field + validation.
- All construction sites of `JForexSessionConfig` — wire the new field.
- Python tests: `tests/test_run_jforex_dukascopy_matrix.py`, `tests/test_run_local_jforex_surrogate_matrix.py`, `tests/test_matrix_warmup.py`.
- Java tests: `HistoricalWarmupLoaderTest.java`, `JForexSessionConfigTest.java`.
- Failure evidence: `data/analysis/backtest_reconcile/2026-04/monthly_recert/jforex_outcome_parity_summary.csv` and the per-symbol `*_jforex_runtime_events.csv`.
