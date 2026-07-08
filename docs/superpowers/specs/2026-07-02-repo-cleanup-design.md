# Repo Cleanup Design — Keep Straddle + JForex, Remove Governance + Experiments

**Date:** 2026-07-02
**Status:** Approved scope (Daniel, 2026-07-02) — ready for implementation plan.

**Decisions confirmed:**
1. Keep the live runtime too (FastAPI runtime + JForex execution scaffold).
2. Do the `core/` de-tangle as part of this cleanup.
3. Discard `.worktrees/` (9 GB) — audited, nothing unique to rescue (see audit below).
4. **Drop the live OCO model system entirely** — remove the tick-opportunity-mining
   pipeline (`run_tick_opportunity_mining.py`, `run_tick_opportunity_monthly_wfo.py`,
   `retrain_all_parallel.py`, `onboard_symbol.py`, freeze/cert tooling) and the
   CatBoost `.cbm` model-serving path. Replace `/predict` with a placeholder that
   returns `{"predictions": [], "actions": []}`. boostlss_xs is the straddle logic
   to keep; wiring it into the runtime is a separate follow-up project, not this
   cleanup. (This supersedes the earlier "Approach A keeps the mining pipeline"
   framing — the de-tangle is now deletion + placeholder, not a static-spec loader.)

## Goal

Shrink the repo to the working live trading system only: the straddle model, the
Python runtime that serves it, and the JForex client. Remove the governance /
certification machinery, all non-straddle modelling, and the experiment heap.
Git history is retained on GitHub, so deletion is safe — old code stays
recoverable via `git log`.

## Straddle-logic preserve inventory (verified 2026-07-02)

All straddle logic lives on `main` and is well-contained — nothing to rescue
from the orphaned worktrees:

- `scripts/boostlss_xs/` — the model: `meta_label_straddle.py`,
  `reversion_straddle.py`, `meta_label_v2.py`, `meta_labeler.py`,
  `causal_validation.py`, `features.py`, `model.py`, `flagging.py`, `universe.py`,
  `config.py` (the "definitive live config, 14 G10 pairs, excl 18–21 UTC"),
  `run.py`, `BACKLOG.md`.
- `tests/test_boostlss_xs_{features,flagging,meta_labeler,universe}.py` — 4 tests.
- `boostlss` + `xgboostlss` deps in `pyproject.toml` / `uv.lock`.
- The live execution path that *runs* the straddle: `src/behemoth/api/`,
  `src/behemoth/runtime/`, the live-primitive subset of `src/behemoth/core/`,
  `src/behemoth/risk/`, `src/jforex/`. (This is the keep set below.)

**Worktree audit:** `.worktrees/{fix-tick-exact,codex,fix-cross-symbol}` are all
plain checkouts of `main` at `2d5da48e` with no uncommitted straddle/boostlss
file changes — only the same deleted-`data/analysis/` status the root already
tracks. The 9 GB is each worktree's checked-out `data/` (tick-velocity parquets),
not unique code. `models/` is empty (gitignored). **Safe to discard.**

The `scripts/fx_coint/*straddle*` and `scripts/run_tick_opportunity_mining.py`
"straddle" mentions are an unrelated FX long/short probe concept and the mining
pipeline — experiments, removable, not part of the preserve inventory.

## Scope (confirmed)

Keep the working live trading system: the straddle model, the FastAPI runtime
JForex calls, the live execution engine, and JForex itself.

**Keep set:**
- `scripts/boostlss_xs/` — straddle model (training / meta-labeling / features).
- `src/behemoth/api/` — FastAPI prediction server JForex calls.
- `src/behemoth/runtime/` — live execution engine (barriers, state machine, orders, bar alignment).
- `src/behemoth/core/` — domain primitives shared by the above (but see the
  tangle section — parts of `core/` are governance and must be untangled).
- `src/behemoth/risk/` — account risk / reservation state machine.
- `src/jforex/` — Java/Dukascopy client (91 files).
- `data/tick_bars/` — the model input.

## The central finding: `core/` is tangled

The keep-set does **not** import the removable subpackages (`governance/`,
`parity/`, `diagnostics/`, `ops/`, `live_restart/`) directly. The real tangle is
**inside `src/behemoth/core/`**, which mixes two kinds of code:

**Live primitives (keep):**
- `schemas.py`, `features.py`, `feature_engine.py`, `feature_pipeline.py`,
  `feature_validator.py`, `regime_quantile_contract.py`, `horizon_feature_config.py`,
  `bundle_paths.py` (partly).

**Governance / cert machinery currently used by the live server (untangle or
rewrite):**
- `governance_validator.py`, `governance_lock_loader.py`
- `historical_prediction_stage.py`, `historical_registry.py`
- `model_registry.py`, `registry.py`, `candidate_catalog.py`,
  `unified_candidate_registry.py`

`api/server.py` and `predict_orchestrator.py` import all of the above. They
encode the model-month / candidate / governance-lock contract that the
certification pipeline produces. To remove governance cleanly, the prediction
path must be rewritten to load the boostlss_xs straddle model **directly**
(without the candidate/governance registry layer). This is the only
non-mechanical part of the cleanup; everything else is directory deletion.

## What gets removed

### Code
- `src/behemoth/governance/` — freeze, selection, stage_contracts, state_assembly,
  tick_exact_*, verdict.
- `src/behemoth/parity/` — all runtime-parity checks.
- `src/behemoth/diagnostics/` — feature_parity, findings, live_governance_deviation.
- `src/behemoth/ops/` — process_graph, process_registry, stage_dag.
- `src/behemoth/live_restart/` — reconciliation, runtime_artifacts.
- `scripts/governance/`, `scripts/era/`, `scripts/era_scalp/`, `scripts/era_tick/`,
  `scripts/fx_coint/`, `scripts/fx_cluster/`, `scripts/tick_ofi/`,
  `scripts/research/`, `scripts/legacy/`.
- The ~106 top-level experiment scripts in `scripts/*.py` (tick mining,
  microstructure, velocity, etc.) — keep only what the straddle or runtime
  imports (audit first; likely none).
- `find_best_per_branch.py`, `find_winner.py`, `test_indices.py`, `amp`,
  stray `java_pid*` files, `.DS_Store`, `__pycache__`, `catboost_info/`,
  `graphify-out/`, `src/behemoth/graphify-out/`, `src/graphify-out/`.

### Tests
- `tests/era*`, `tests/fx_*`, `tests/governance/`, `tests/parity/`, and the
  long tail of `tests/test_*` that cover removed machinery (audit per import).

### Docs / config / build
- `site/` (mkdocs build), `docs/` governance/cert pages (audit), top-level
  `ANALYSIS_*.md`, `ARCHITECTURAL_*.md`, `REMAINING_*.md`, `GRAPH_REPORT.md`.
- `Makefile` governance/cert targets: `monthly-recert`, `monthly-build`,
  `retrain-all`, `audit-all`, `freeze-*`, `validate-*`, `dukascopy-*`,
  `local-jforex-parity*`, `jforex-*`, `promote-live`, `seed-threshold`, etc.
  Keep only `test`, `test-java`, `quality` (slimmed), `jforex-live`,
  `pr`, `docs` (slimmed).
- `configs/research/`, `configs/process/` if governance-only.

### Data
- `data/analysis/` (governance-locked outputs), `data/backtest_reconcile/`.
- Keep `data/tick_bars/` (straddle input).

### Local disk cruft (not in git, but huge)
- `.worktrees/` is **9.1 GB** of orphaned worktrees (not in `git worktree list`).
  Safe to delete — they are stale session worktrees. (Per memory, root checkout
  is also stale/dirty; consider doing this work from a fresh worktree on
  `origin/main`.)
- `.venv/` 1.7 GB — regenerate via `uv sync` after cleanup.

## Approaches considered

### A. In-place surgical cleanup (recommended)
Delete the removable dirs/tests/docs/data in one PR branch off `origin/main`,
then surgically rewrite `api/server.py` + `predict_orchestrator.py` to load the
straddle model directly and drop the `core/` governance modules. Slim the
Makefile. Verify `make test` + `make test-java` pass.

- **Pro:** preserves a working live system; smallest blast radius; history on
  GitHub still holds everything; reviewable in a single (large) PR.
- **Con:** the `core/` de-tangle is real refactor work; one big diff is hard to
  review.

### B. Fresh repo / squash rebuild
Start a new repo (or orphan branch) with only the keep-set copied in, slimmed.
- **Pro:** pristine result, no dead code smell, tiny repo.
- **Con:** loses the granular git history of the kept code on this branch
  (recoverable on GitHub but not in the new repo's blame); harder to verify
  nothing was missed; re-establishing CI / pre-commit / build wiring from
  scratch.

### C. `git filter-repo` history rewrite
Rewrite history to drop the removed paths entirely, including past blobs.
- **Pro:** repo size shrinks for clones too; clean history.
- **Con:** rewrites all commit SHAs — breaks every existing clone, PR, and
  GitHub link in memory/docs; force-push required; the `.git` is only 185 MB so
  the size win is marginal and not worth the disruption. **Not recommended.**

**Recommendation: Approach A**, done in a fresh worktree on `origin/main`,
shipped as a PR. Keep history intact; the 9 GB is local worktree cruft, not in
git, so no history rewrite is needed to reclaim disk.

## Phased plan (Approach A)

**Phase 0 — Prep.** Create a clean worktree on `origin/main`. Delete local
`.worktrees/` cruft on the side (non-git). Snapshot the keep-set's current
`make test` + `make test-java` baseline.

**Phase 1 — Mechanical deletion.** Remove the clearly-removable dirs, tests,
docs, data, Makefile targets, stray files. Commit. (`make quality` will flag
broken imports — expected; Phase 2 fixes them.)

**Phase 2 — De-tangle `core/`.** The refactor: rewrite the prediction path in
`api/server.py` + `predict_orchestrator.py` to load the boostlss_xs straddle
model directly (config + model file), removing dependence on
`governance_validator`, `governance_lock_loader`, `historical_*`,
`*_registry`, `candidate_catalog`, `unified_candidate_registry`. Move retained
governance-free primitives into a slimmer `core/` (or inline). Delete the
governance `core/` modules.

**Phase 3 — Verify.** `make test` (slimmed suite) green; `make test-java`
green; `uv sync` from scratch; `make jforex-live` smoke (if creds available).
`make quality` clean.

**Phase 4 — Docs + memory.** Update `CLAUDE.md`, `AGENTS.md`, `UBIQUITOUS_LANGUAGE.md`,
`CONTEXT.md` to reflect the slimmer repo. Drop governance memory entries that
no longer apply; record the cleanup.

## Open questions

None — scope confirmed. Proceed to implementation plan.