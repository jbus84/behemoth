# Repo Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Shrink the repo to the boostlss_xs straddle logic + the JForex/FastAPI execution scaffold (model-serving replaced by a placeholder), removing all governance, the tick-opportunity-mining pipeline, certification, and experiments.

**Architecture:** Keep two things: (1) `scripts/boostlss_xs/` — the straddle meta-labeler, standalone (writes to `/tmp`, not yet wired into the runtime). (2) `src/jforex/` (Java client) + `src/behemoth/{api,runtime,core,risk}` (FastAPI execution scaffold: state, barriers, OCO orders, bar aggregation, account risk, HTTP surface) — with the CatBoost model-loading + governance-candidate path replaced by a placeholder that returns no predictions. The runtime stands up, JForex connects over the existing HTTP contract, but no trades fire until boostlss_xs is wired in (a later project). Delete the tick-opportunity-mining pipeline, the freeze/governance/cert tooling, the experiment heap, and the governance/parity/diagnostics/ops/live_restart subpackages.

**Tech Stack:** Python 3.10+, polars/numpy/catboost/boostlss/xgboostlss, FastAPI/uvicorn, DuckDB, pytest; Kotlin/Gradle (JForex, Dukascopy SDK); ruff/ty/vulture/xenon/smellcheck quality gate.

## Global Constraints

- Work in a git worktree on `origin/main` (per user rule: never commit to `main`; PRs from worktrees). Root checkout is stale/dirty — do not use it as the base.
- Verdict vocabulary is canonical where used: `PASS`, `FAIL`, `GO`, `NO_GO` (no synonyms).
- After every task that touches Python, run `uv run pytest -q <affected>` and `make quality` before committing. Collection errors redden the whole quality job — fix immediately.
- Git history is retained on GitHub; deletions are safe — do NOT use `git filter-repo` (would rewrite SHAs and break every clone/PR/link for a marginal 185 MB `.git` win).
- Preserve every file in the straddle-logic inventory (verified 2026-07-02): `scripts/boostlss_xs/**` (all `.py` + `BACKLOG.md`), `tests/test_boostlss_xs_{features,flagging,meta_labeler,universe}.py`, and the `boostlss`/`xgboostlss`/`numpyro`/`statsmodels`/`catboost` deps in `pyproject.toml`/`uv.lock`. Do not delete or modify these without an explicit task.
- Commit message style: conventional commits (`feat:`, `fix:`, `chore:`, `docs:`), end with `Co-Authored-By: Claude <noreply@anthropic.com>`.
- End each task with a commit. Each task is independently testable.

## Key finding that shapes the de-tangle (from architecture report, 2026-07-02)

The live runtime never used `boostlss_xs`. It served CatBoost `.cbm` models from `models/oco/*.cbm` produced by `scripts/run_tick_opportunity_monthly_wfo.py` (the tick-opportunity-mining pipeline), loaded through governance locks (`CandidateRegistry` + `BundlePaths` sha256 + `configs/research/governance/oco/` lock JSONs). Because we are dropping that whole system, the de-tangle is deletion + placeholder, not a rebuild:
- `server.py:_load_models` (1058-1108) → no-op placeholder.
- `server.py:_resolve_runtime_contract*` (1644-1712) + `_ensure_model_and_threshold` (1715-1739) → placeholder returning empty candidate list / no model.
- `server.py:_build_decisions` model call (2710) → never reached (no candidates).
- `predict_orchestrator._step_resolve_candidates` (246-282) → placeholder.
- Historical-governance branch (`lifespan` 821-832, `_is_historical_mode()` 445) → deleted.
- Then delete `core/{registry,bundle_paths,candidate_catalog,model_registry,governance_validator,historical_registry,historical_prediction_stage,unified_candidate_registry,governance_lock_loader}.py` (all now unreferenced).

JForex talks only to the FastAPI HTTP surface via governance-free schemas in `core/schemas.py` (`PredictRequest`/`PredictResponse`/`IncomingTick`/`TickBatchRequest` etc.) — unaffected by the de-tangle.

---

## Phase 0 — Prep

### Task 0.1: Create clean worktree on origin/main and capture baseline

**Files:**
- Worktree: `.claude/worktrees/repo-cleanup` (created by EnterWorktree)

- [ ] **Step 1: Fetch origin and create worktree from `origin/main`**

```bash
git fetch origin main
git worktree add -b feat/repo-cleanup origin/main .claude/worktrees/repo-cleanup
```

- [ ] **Step 2: Enter the worktree and sync deps**

In this session: `EnterWorktree` with `path: .claude/worktrees/repo-cleanup`. Then:
```bash
uv sync
```

- [ ] **Step 3: Capture test baselines (what currently passes)**

```bash
uv run pytest -q --co 2>&1 | tail -5 > /tmp/repo-cleanup-baseline-pytest.txt
./gradlew -p src/jforex test 2>&1 | tail -20 > /tmp/repo-cleanup-baseline-java.txt
```
Expected: both run (some tests may already be broken on `main` for unrelated reasons — record, don't fix).

- [ ] **Step 4: Record the straddle-logic preserve inventory is intact**

```bash
ls scripts/boostlss_xs/ && ls tests/test_boostlss_xs_*.py
```
Expected: 11 `.py` files + `BACKLOG.md` in `scripts/boostlss_xs/`, 4 `test_boostlss_xs_*.py` files.

### Task 0.2: Discard local cruft (outside the worktree, on the host root checkout)

**Note:** These are not in git; safe to delete from the host filesystem. They do not affect the worktree.

- [ ] **Step 1: Delete orphaned worktrees (9.1 GB, audited — plain `main` checkouts, nothing unique)**

```bash
cd /Users/danielfisher/repositories/behemoth
rm -rf .worktrees
```
Expected: `du -sh .worktrees` → "No such file or directory".

- [ ] **Step 2: Regenerate `.venv` later via `uv sync` after cleanup** (leave as-is for now; the worktree has its own).

---

## Phase 1 — Delete experiment + research heap (no runtime coupling)

### Task 1.1: Delete experiment script directories

**Files (delete):** `scripts/{era,era_scalp,era_tick,fx_coint,fx_cluster,tick_ofi,research,legacy}/`

- [ ] **Step 1: Delete the experiment script dirs**

```bash
git rm -r scripts/era scripts/era_scalp scripts/era_tick scripts/fx_coint scripts/fx_cluster scripts/tick_ofi scripts/research scripts/legacy
```

- [ ] **Step 2: Delete their test directories**

```bash
git rm -r tests/era tests/era_scalp tests/era_tick tests/fx_cluster tests/fx_coint
```

- [ ] **Step 3: Verify nothing in the keep set imported them**

```bash
grep -rnE "scripts\.(era|fx_coint|fx_cluster|tick_ofi|research|legacy)" src/behemoth scripts/boostlss_xs src/jforex 2>/dev/null
```
Expected: no output. If any hit, stop — that import is a keep-set dependency; resolve before continuing.

- [ ] **Step 4: Run the keep-set tests**

```bash
uv run pytest -q tests/test_boostlss_xs_features.py tests/test_boostlss_xs_flagging.py tests/test_boostlss_xs_meta_labeler.py tests/test_boostlss_xs_universe.py
```
Expected: 4 files pass.

- [ ] **Step 5: Commit**

```bash
git commit -m "chore: delete experiment/research script dirs (era, fx_coint, tick_ofi, research, legacy)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 1.2: Delete top-level experiment scripts (audit each for keep-set imports first)

**Files (delete):** the experiment/research top-level scripts. Keep operational tooling for the live scaffold: `run_jforex_live.py`, `monitor_jforex_health.py`, `provision_observability.py`, `inject_live_observability_data.py`, `build_global_tick_bars.py`, `build_all_1m_data.py`, `download_histdata_ticks.py`, `download_tick_vault_data.py`, `parallel_download.py`, `canonical_tick_feed.py`, `check_daily_tick_coverage.py`, `compare_tick_data_sources.py`, `extract_spotlight_ticks.py`, `simulate_api_e2e_replay.py`, `test_e2e_observability_logging.py`. Delete everything else in `scripts/*.py` (mining, governance, cert, diagnostics-of-removed-systems, reports for removed systems).

**Delete (verified non-keep):**
```bash
git rm scripts/analyze_live_governance_deviation.py \
  scripts/analyze_oco_monthly_wfo_robustness.py scripts/analyze_oco_stop_limit_tickfill.py \
  scripts/audit_data_reliability.py scripts/audit_oco_execution_risk_prelive.py \
  scripts/audit_oco_leakage_label_integrity.py scripts/audit_oco_pipeline_logical_issues.py \
  scripts/audit_runtime_parity.py scripts/audit_tick_source_completeness.py \
  scripts/build_account_risk_monitoring_report.py scripts/build_demo_live_offline_comparison_report.py \
  scripts/build_docs_catalog.py scripts/build_feature_importance_audit.py \
  scripts/build_global_tick_bars_offset.py scripts/build_mining_deep_report.py \
  scripts/build_oco_execution_drift_report.py scripts/build_oco_governance_explainability_report.py \
  scripts/build_oco_strategy_bible.py scripts/build_oco_system_reference_docs.py \
  scripts/build_oco_threshold_sensitivity_report.py scripts/build_operator_action_report.py \
  scripts/build_process_stage_docs.py scripts/build_repro_manifest.py \
  scripts/build_run_delta_dashboard.py scripts/build_symbol_onboarding_playbook.py \
  scripts/build_tick_opportunity_ml_dataset.py scripts/build_tick_velocity_dataset.py \
  scripts/candidate_fills.py scripts/check_cols_parquet.py scripts/check_legacy_drift.py \
  scripts/check_oco_docs_stage_integrity.py scripts/classify_retrain_outcome.py \
  scripts/create_dukascopy_candidate_configs.py scripts/cross_symbol.py \
  scripts/diagnose_jforex_coverage_gaps.py scripts/diagnose_live_audit.py \
  scripts/diagnose_live_performance_gap.py scripts/diagnose_live_replay.py \
  scripts/diagnose_live_thresholds.py scripts/evaluate_low_capacity_track.py \
  scripts/explain_stage.py scripts/freeze_monthly_bundle.py \
  scripts/freeze_oco_live_governance.py scripts/generate_dukascopy_testclient_artifacts.py \
  scripts/migrate_lock_schema.py scripts/mining_family.py scripts/mining_random_baseline.py \
  scripts/onboard_symbol.py scripts/reconcile_account_risk_reservations.py \
  scripts/reconcile_historical_prediction_artifacts.py scripts/reconcile_jforex_outcomes.py \
  scripts/refresh_context_from_graphify.py scripts/register_docs_run.py \
  scripts/remediate_oco_monitoring_alerts.py scripts/remediate_tickvault_cache.py \
  scripts/retrain_all_parallel.py scripts/run_execution_monte_carlo.py \
  scripts/run_jforex_dukascopy_matrix.py scripts/run_local_jforex_surrogate_matrix.py \
  scripts/run_microstructure_diagnostics.py scripts/run_monthly_build.py \
  scripts/run_monthly_recert.py scripts/run_offset_tickbar_frozen_screen.py \
  scripts/run_offset_tickbar_robustness.py scripts/run_promote_live.py \
  scripts/run_stage12_stage13_certification.py scripts/run_tick_opportunity_mining.py \
  scripts/run_tick_opportunity_monthly_wfo.py scripts/seed_rolling_threshold.py \
  scripts/select_directional_rolling.py scripts/select_oco_reduced_core.py \
  scripts/select_reduced_core_regimes.py scripts/short_term_metalabel_probe.py \
  scripts/summarize_runtime_db_run.py scripts/sync_candidate_model_artifacts.py \
  scripts/validate_api_parity.py scripts/validate_bundle.py \
  scripts/validate_execution_monte_carlo.py scripts/validate_live_stage_dag.py \
  scripts/validate_local_jforex_surrogate.py scripts/validate_oco_docs_contract.py \
  scripts/validate_oco_historical_governance.py scripts/validate_oco_live_governance.py \
  scripts/validate_oco_rule_universe_registry.py scripts/validate_process_graph_contract.py \
  scripts/validate_stage13_dukascopy_testclient.py \
  scripts/validate_stage14_jforex_runtime_certification.py \
  scripts/verify_tick_exact_shortlist.py scripts/xs_microstructure_anomaly_probe.py \
  scripts/_matrix_warmup.py scripts/find_best_per_branch.py scripts/find_winner.py \
  scripts/test_indices.py
```

- [ ] **Step 1: Before deleting, confirm none are imported by the keep set**

```bash
for s in diagnose_live_replay mining_family candidate_fills cross_symbol canonical_tick_feed; do
  echo "--- $s ---"; grep -rn "scripts\.$s\b" src/behemoth scripts/boostlss_xs 2>/dev/null | grep -v __pycache__
done
```
Expected: `diagnose_live_replay` only referenced by `src/behemoth/diagnostics/` (deleted in Phase 4); `mining_family` only a comment in `core/bundle_paths.py` (deleted in Phase 3); `candidate_fills`/`cross_symbol` only string/field names, not imports. If any real keep-set import appears, stop and resolve.

- [ ] **Step 2: Delete the scripts** (command above).

- [ ] **Step 3: Delete orphaned top-level tests for removed scripts**

Delete `tests/test_<removed_script>.py` for each removed script. Concretely remove at least:
```bash
git rm tests/test_analyze_oco_monthly_wfo_robustness.py tests/test_audit_data_reliability.py \
  tests/test_audit_oco_execution_risk_prelive.py tests/test_audit_oco_leakage_label_integrity.py \
  tests/test_audit_oco_pipeline_logical_issues.py tests/test_audit_runtime_parity.py \
  tests/test_audit_tick_source_completeness.py tests/test_build_demo_live_offline_comparison_report.py \
  tests/test_build_docs_catalog.py tests/test_build_mining_deep_report.py \
  tests/test_build_oco_system_reference_docs.py tests/test_build_oco_threshold_sensitivity_report.py \
  tests/test_build_oco_execution_drift_report.py tests/test_build_operator_action_report.py \
  tests/test_build_run_delta_dashboard.py tests/test_build_tick_velocity_dataset.py \
  tests/test_build_global_tick_bars_offset.py tests/test_check_daily_tick_coverage.py \
  tests/test_classify_retrain_outcome.py tests/test_compare_tick_data_sources.py \
  tests/test_cross_symbol.py tests/test_cross_symbol_family_configs.py \
  tests/test_directional_canary_configs.py tests/test_download_histdata_ticks.py \
  tests/test_download_tick_vault_data.py tests/test_evaluate_low_capacity_track.py \
  tests/test_execution_monte_carlo.py tests/test_extract_spotlight_ticks.py \
  tests/test_feature_importance_audit.py tests/test_freeze_oco_live_governance.py \
  tests/test_freeze_monthly_bundle.py tests/test_generate_dukascopy_testclient_artifacts.py \
  tests/test_global_tick_bars.py tests/test_migrate_lock_schema.py \
  tests/test_mining_family.py tests/test_mining_random_baseline.py \
  tests/test_oco_candidate_family_allowlist.py tests/test_oco_leakage_label_integrity.py \
  tests/test_oco_live_governance.py tests/test_oco_monthly_wfo_robustness.py \
  tests/test_oco_pipeline_logical_audit.py tests/test_oco_precompute_spread.py \
  tests/test_oco_reduced_core_rolling.py tests/test_remediate_oco_monitoring_alerts.py \
  tests/test_run_jforex_dukascopy_matrix.py tests/test_run_local_jforex_surrogate_matrix.py \
  tests/test_run_monthly_build.py tests/test_run_monthly_recert.py tests/test_run_promote_live.py \
  tests/test_run_stage12_stage13_certification.py tests/test_run_tick_opportunity_monthly_wfo.py \
  tests/test_select_directional_rolling.py tests/test_select_reduced_core_regimes.py \
  tests/test_short_term_metalabel_probe.py tests/test_stage_contracts.py \
  tests/test_stage_dag_contract.py tests/test_stage_integrity_gate.py \
  tests/test_summarize_runtime_db_run.py tests/test_sync_candidate_model_artifacts.py \
  tests/test_tick_opportunity_mining.py tests/test_tick_opportunity_ml_dataset.py \
  tests/test_tick_velocity_dataset.py tests/test_validate_bundle.py \
  tests/test_validate_execution_monte_carlo.py tests/test_validate_live_stage_dag.py \
  tests/test_validate_local_jforex_surrogate.py tests/test_validate_oco_docs_contract.py \
  tests/test_validate_oco_rule_universe_registry.py tests/test_validate_process_graph_contract.py \
  tests/test_validate_stage13_dukascopy_testclient.py \
  tests/test_validate_stage14_jforex_runtime_certification.py \
  tests/test_verify_tick_exact_shortlist.py tests/test_matrix_warmup.py \
  tests/test_microstructure_regimes.py tests/test_process_graph_tools.py \
  tests/test_process_registry.py tests/test_reconcile_jforex_outcomes.py \
  tests/test_register_docs_run.py tests/test_retrain_all_parallel.py \
  tests/test_live_restart_reconciliation.py tests/test_live_governance_deviation.py \
  tests/test_live_threshold_diagnostics.py tests/test_diagnose_live_replay.py \
  tests/test_diagnose_live_audit.py tests/test_diagnose_live_performance_gap.py \
  tests/test_data_reliability_audit.py tests/test_account_risk_monitoring_report.py \
  tests/test_reconcile_account_risk_reservations.py tests/test_build_account_risk_monitoring_report.py \
  tests/test_remediate_tickvault_cache.py tests/test_run_offset_tickbar_frozen_screen.py \
  tests/test_run_offset_tickbar_robustness.py tests/test_monthly_wfo_threshold_causality.py \
  tests/test_check_legacy_drift.py tests/test_canonical_tick_feed.py 2>/dev/null
```
Note: `test_run_jforex_live.py` and `test_monitor_jforex_health.py` are **kept** — they cover the kept operational scripts `run_jforex_live.py`/`monitor_jforex_health.py`; they are deliberately not in the `git rm` above.

- [ ] **Step 4: Run remaining tests to find newly-broken imports**

```bash
uv run pytest -q --co 2>&1 | grep -E "error|Error" | head -30
```
Expected: collection errors for tests importing deleted modules. Delete those test files too (they cover removed code).

- [ ] **Step 5: Repeat until `pytest --co` collects cleanly**, then run keep-set tests:

```bash
uv run pytest -q tests/test_boostlss_xs_features.py tests/test_boostlss_xs_flagging.py tests/test_boostlss_xs_meta_labeler.py tests/test_boostlss_xs_universe.py tests/test_account_risk.py
```
Expected: pass (account_risk is keep).

- [ ] **Step 6: Commit**

```bash
git commit -m "chore: delete experiment/mining/governance/cert top-level scripts + tests

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 1.3: Delete experiment + governance docs, data, configs

**Files (delete):**
- `docs/analysis/` (governance/research verdict docs), `docs/superpowers/specs|plans` for removed experiments (audit — keep this cleanup spec + plan + the boostlss_xs design/plan).
- `data/analysis/` (governance-locked mining outputs), `data/backtest_reconcile/`.
- `configs/research/` (governance lock JSONs + research configs for removed systems).
- Top-level cruft docs: `ANALYSIS_*.md`, `ARCHITECTURAL_*.md`, `REMAINING_*.md`, `GRAPH_REPORT.md`, `CHANGELOG.md` (stale), stray `java_pid*`, `amp`, `.DS_Store` files.

- [ ] **Step 1: Delete governance data + configs**

```bash
git rm -r data/analysis configs/research 2>/dev/null
rm -rf data/backtest_reconcile  # already untracked-deleted on main; ensure gone
find . -name '.DS_Store' -not -path './.git/*' -not -path './.venv/*' -delete
rm -f java_pid98384_stdout java_pid98384_stderr amp
```

- [ ] **Step 2: Delete removed-system docs**

```bash
git rm -r docs/analysis 2>/dev/null
git rm ANALYSIS_HORIZON_400_200.md ANALYSIS_BUDGET_300_TUNED.md \
  ARCHITECTURAL_DEEPENING_COMPLETE.md ARCHITECTURE_IMPROVEMENTS.md \
  REMAINING_ARCHITECTURE_OPPORTUNITIES.md GRAPH_REPORT.md 2>/dev/null
```
Audit `docs/superpowers/specs|plans` — keep `2026-07-02-repo-cleanup-*.md` and `2026-06-29-boostlss-xs-anomaly-meta-labeler*.md`; delete specs/plans for removed systems (era/fx_coint/scalp/flow/cluster/etc.) after a quick `grep -l` check.

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "chore: delete governance data/configs + removed-system docs

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Phase 2 — (folded into Phase 3) De-tangle the runtime

The de-tangle must precede deletion of the `core/` governance modules because `server.py` imports them at module top-level. We rewrite `server.py` + `predict_orchestrator.py` to a placeholder, remove those imports, then delete the now-dead modules in Phase 4.

### Task 2.1: Write a failing test that the placeholder `/predict` returns no predictions

**Files:**
- Test: `tests/test_predict_placeholder.py` (create)

**Interfaces:**
- Produces: assertion that `POST /predict` returns `predictions: []` when no model is configured.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_predict_placeholder.py
"""Placeholder predict path — no model wired in after the mining-pipeline removal."""
from __future__ import annotations

from fastapi.testclient import TestClient


def test_predict_returns_empty_when_no_model(monkeypatch):
    from src.behemoth.api.server import app

    monkeypatch.setenv("BEHEMOTH_SYMBOLS", "EURUSD")
    client = TestClient(app)
    resp = client.post("/predict", json={
        "symbol": "EURUSD",
        "close_ts": "2025-01-01T00:00:00Z",
        "bar_ticks": 100,
        "features": {},
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("predictions", []) == []
```

- [ ] **Step 2: Run it to verify it fails**

```bash
uv run pytest -q tests/test_predict_placeholder.py
```
Expected: FAIL (current path raises 503 "governance registry unavailable" or loads a model).

### Task 2.2: Replace `_load_models` + governance lifespan branch with a no-op placeholder

**Files:**
- Modify: `src/behemoth/api/server.py` (lifespan ~777-870, `_load_models` 1058-1108, imports 40-55)

**Interfaces:**
- Consumes: `AppConfig.symbols` (kept), `TickAggregator` (kept).
- Produces: `_load_models()` is a no-op log; lifespan no longer constructs `_registry`/`_historical_registry`.

- [ ] **Step 1: Replace the lifespan governance branch with a static scaffold**

In `lifespan`, replace the `try:` block (818-850) that does `if _is_historical_mode(): ... else: _registry = CandidateRegistry.load(...)` with:

```python
    try:
        _aggregators = {}
        _cache_manager.reset_all()
        # Model-serving is a placeholder pending boostlss_xs wiring (see
        # docs/superpowers/plans/2026-07-02-repo-cleanup.md). No model is loaded;
        # /predict returns an empty prediction list until a model is wired in.
        _registry = None
        _historical_registry = None
        _historical_entries_loaded = 0
        _historical_preflight_failed_checks = 0
        _historical_preflight_summary = ""
        unique_bar_ticks = {100}
        for bt in unique_bar_ticks:
            _aggregators[bt] = TickAggregator(bar_ticks=bt)
            logger.info("Initialized TickAggregator for %d ticks", bt)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Runtime scaffold startup failed: %s", exc)
        raise
```
Remove the `except FileNotFoundError` / `except BundleIntegrityError` handlers that follow (they reference deleted governance types).

- [ ] **Step 2: Replace `_load_models` with a no-op**

```python
def _load_models() -> None:
    """No-op placeholder. Model-serving was removed with the tick-opportunity-mining
    pipeline; /predict returns empty predictions until boostlss_xs is wired in."""
    _cache_manager.reset_all()
    logger.info("Model loading skipped — placeholder predict path active (no model wired).")
```
Delete `_catboost_cls` (1058-1064) — no longer used.

- [ ] **Step 3: Remove now-unused governance imports from server.py top**

Remove these imports (lines ~45-55) and any others that become unused:
`GovernanceValidator`, `HistoricalPredictionStage`, `HistoricalCandidateRegistry`, `ModelRegistry`, `CandidateRegistry`, `BundleIntegrityError`, `BundlePaths`, `CandidateCatalog`, `CatalogContext`, `_normalize_model_month`. Keep: `schemas`, `features`, `feature_engine`, `regime_quantile_contract`, `PredictionOrchestrator`, `runtime.*`, `risk.*`, `cache_manager`, `dashboard`, `runtime_app_state`.

After editing, run:
```bash
uv run python -c "import src.behemoth.api.server"
```
Expected: no ImportError. If ImportError names a still-needed symbol, restore that import only.

- [ ] **Step 4: Run the placeholder test**

```bash
uv run pytest -q tests/test_predict_placeholder.py
```
Expected: still FAIL or PASS depending on `/predict` handler — next task fixes the handler.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(api): placeholder model-loading path (drop mining/governance startup)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 2.3: Make `/predict` return empty predictions and delete the dead model/contract path

The orchestrator already short-circuits: `execute()` does `if not candidates: return PredictResponse(predictions=[], actions=[])` (predict_orchestrator.py ~200). So the placeholder is: make `_step_resolve_candidates` return `[]`, drop the `_registry is None` guard in `predict()`, then **delete** the now-unreached step-5 model functions (they are never called once step 1 returns `[]`).

**Files:**
- Modify: `src/behemoth/api/server.py` (`predict()` 2441-2477 — drop the registry guard; delete `_resolve_runtime_contract` 1644-1668, `_resolve_runtime_contract_for_family` 1671-1712, `_ensure_model_and_threshold` 1715-1739, `_orchestrator_build_predictions_fn` 2480-2566, `_build_decisions` 2629-2862, `_run_allocator` 2865-2972, `_materialize_predictions` 2975+, and all `_load_historical_prediction_*` / `_resolve_historical_prediction_*` / `_apply_historical_prediction_universe_gate` helpers)
- Modify: `src/behemoth/api/predict_orchestrator.py` (`_step_resolve_candidates` 246-282 → return `[]`; delete `_resolve_historical_aggregate_contract`, `_apply_historical_prediction_universe_gate`, and the `self._is_historical_mode` / `self._historical_registry` wiring in `__init__`/`execute`)

**Interfaces:**
- Produces: `POST /predict` → `200 {"predictions": [], "actions": []}`; no model loaded; step-5 helpers removed.

- [ ] **Step 1: Drop the registry guard in `predict()`**

In `predict()` (server.py ~2452), delete:
```python
    if _registry is None and not _is_historical_mode():
        raise HTTPException(status_code=503, detail="Candidate registry not loaded")
```
`_registry` is now always `None` (Task 2.2); historical mode is gone. Leave the `_state is None` and `_orchestrator is None` guards.

- [ ] **Step 2: Make `_step_resolve_candidates` return `[]`**

Replace the body of `_step_resolve_candidates` (predict_orchestrator.py 246-282) with:
```python
    def _step_resolve_candidates(
        self, req: Any, sym: str, close_ts: datetime
    ) -> list[Any]:
        """Step 1: Placeholder — no candidate catalog/model wired in yet.

        Returning [] makes execute() short-circuit to
        PredictResponse(predictions=[], actions=[]). Re-enable candidate
        resolution when boostlss_xs is wired into the runtime.
        """
        logger.info("Step 1: placeholder — no candidates for %s (no model wired).", sym)
        return []
```
`execute()` already handles `if not candidates: return PredictResponse(predictions=[], actions=[])`, so no other change is needed there. Remove the now-unused `_resolve_historical_aggregate_contract` method and the `_apply_historical_prediction_universe_gate` call (delete the method too). Remove `self._is_historical_mode` / `self._historical_registry` from `__init__` and the `_is_historical_mode` references in `execute`.

- [ ] **Step 3: Delete the now-unreached step-5 / contract / historical helpers in server.py**

`grep` each function to confirm it's only called from the dead step-5 path (or `_step_resolve_candidates`, now replaced), then delete it:
```bash
for f in _resolve_runtime_contract _resolve_runtime_contract_for_family \
         _ensure_model_and_threshold _orchestrator_build_predictions_fn \
         _build_decisions _run_allocator _materialize_predictions \
         _load_historical_prediction_universe _resolve_historical_prediction_payload_overrides \
         _apply_historical_prediction_universe_gate _load_historical_prediction_stage \
         _run_historical_preflight _is_historical_mode _effective_governance_dir \
         _candidate_catalog _cache_key _has_loaded_model_for_symbol _latest_loaded_month_for_symbol; do
  echo "=== $f ==="; grep -n "$f" src/behemoth/api/server.py src/behemoth/api/predict_orchestrator.py | head
done
```
Expected: each is referenced only by other deleted functions or by code already removed. Delete each function definition and any remaining `_resolved_runtime_contract`/`_ResolvedRuntimeContract` dataclass, the `_model_registry`/`_registry`/`_historical_registry` module globals, and `CandidateRegistry`/`CandidateCatalog`/`HistoricalCandidateRegistry`/`ModelRegistry` usages. If a function is still referenced by a kept path, keep it (and note why).

- [ ] **Step 4: Remove the now-unused governance/config imports from server.py + orchestrator**

Re-run:
```bash
uv run python -c "import src.behemoth.api.server" 2>&1 | head
```
Expected: ImportError listing unused-but-still-imported names (e.g. `BundlePaths`, `CandidateCatalog`, `ModelRegistry`, `HistoricalPredictionStage`, `GovernanceValidator`, `regime_quantile_contract` if only used by deleted code). Remove those imports. Repeat until import is clean. Keep `regime_quantile_contract` only if still used by `runtime/` or the feature path.

- [ ] **Step 5: Run the placeholder test — verify PASS**

```bash
uv run pytest -q tests/test_predict_placeholder.py
```
Expected: PASS (200, `predictions: []`).

- [ ] **Step 6: Run the broader api/runtime/risk test suite; fix or delete tests asserting removed behavior**

```bash
uv run pytest -q tests/test_api_server.py tests/test_predict_orchestrator.py tests/test_predict_endpoint_integration.py tests/test_server_routes.py tests/test_runtime_app_state.py 2>&1 | tail -40
```
Expected: failures in tests that assert governance-registry loading, model loading, historical mode, or candidate resolution. For each: if it tests removed behavior, `git rm` it; if it tests kept behavior, rewrite the assertion to expect `predictions == []` (and `actions == []`). Repeat until green.

- [ ] **Step 7: Run vulture to confirm the deleted helpers left no orphans**

```bash
make vulture 2>&1 | grep -E "server\.py|predict_orchestrator\.py" | head
```
Expected: no surviving references to deleted functions. Fix any vulture-flagged now-dead helpers by deleting them too.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor(api): placeholder /predict returns empty predictions; delete dead model path

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 2.4: Delete now-unreferenced governance/model core modules + their tests

**Files (delete):** `src/behemoth/core/{registry,bundle_paths,candidate_catalog,model_registry,governance_validator,historical_registry,historical_prediction_stage,unified_candidate_registry,governance_lock_loader}.py` + their tests.

- [ ] **Step 1: Confirm no keep-set module imports them**

```bash
grep -rnE "core\.(registry|bundle_paths|candidate_catalog|model_registry|governance_validator|historical_registry|historical_prediction_stage|unified_candidate_registry|governance_lock_loader)" src/behemoth/api src/behemoth/runtime src/behemoth/risk src/behemoth/core scripts/boostlss_xs 2>/dev/null | grep -v __pycache__
```
Expected: no output (server.py imports removed in Task 2.2). If hits remain, remove those imports first.

- [ ] **Step 2: Delete the modules**

```bash
git rm src/behemoth/core/registry.py src/behemoth/core/bundle_paths.py \
  src/behemoth/core/candidate_catalog.py src/behemoth/core/model_registry.py \
  src/behemoth/core/governance_validator.py src/behemoth/core/historical_registry.py \
  src/behemoth/core/historical_prediction_stage.py \
  src/behemoth/core/unified_candidate_registry.py \
  src/behemoth/core/governance_lock_loader.py
```
Keep: `core/{schemas,features,feature_engine,feature_pipeline,feature_validator,regime_quantile_contract,horizon_feature_config,__init__}.py`. Audit `core/feature_pipeline.py` and `feature_validator.py` for governance imports — if they import deleted modules, inline the needed bits or delete the governance dependency.

- [ ] **Step 3: Delete their tests**

```bash
git rm tests/test_registry.py tests/test_bundle_paths.py tests/test_candidate_catalog.py \
  tests/test_model_expiry_guard.py tests/test_governance_lock_loader.py \
  tests/test_historical_registry.py tests/test_historical_prediction_stage.py \
  tests/test_api_server_historical.py tests/test_strict_threshold_enforcement.py \
  tests/test_threshold_seeding.py tests/test_oco_candidate_family_allowlist.py 2>/dev/null
```

- [ ] **Step 4: Verify imports + collection**

```bash
uv run python -c "import src.behemoth.api.server; import src.behemoth.runtime.state; import src.behemoth.risk.account"
uv run pytest -q --co 2>&1 | grep -iE "error" | head
```
Expected: clean import; clean collection. Fix any remaining references.

- [ ] **Step 5: Commit**

```bash
git commit -m "refactor(core): delete governance/model registry modules (placeholder runtime)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Phase 3 — Delete governance/parity/diagnostics/ops/live_restart subpackages

### Task 3.1: Delete removable `src/behemoth` subpackages

**Files (delete):** `src/behemoth/{governance,parity,diagnostics,ops,live_restart}/`

- [ ] **Step 1: Confirm keep set does not import them**

```bash
grep -rnE "behemoth\.(governance|parity|diagnostics|ops|live_restart)" src/behemoth/api src/behemoth/runtime src/behemoth/core src/behemoth/risk 2>/dev/null | grep -v __pycache__
```
Expected: no output (verified 2026-07-02 that the keep set only imported `core.governance_validator`, now deleted).

- [ ] **Step 2: Delete the subpackages + their tests**

```bash
git rm -r src/behemoth/governance src/behemoth/parity src/behemoth/diagnostics \
  src/behemoth/ops src/behemoth/live_restart
git rm -r tests/governance tests/parity 2>/dev/null
git rm tests/test_ops_verdicts.py tests/test_process_graph_tools.py tests/test_process_registry.py \
  tests/test_stage_contracts.py tests/test_stage_dag_contract.py tests/test_stage_integrity_gate.py \
  tests/test_audit_trail_persistence.py tests/test_feature_parity.py 2>/dev/null
```

- [ ] **Step 3: Verify clean collection + run keep-set tests**

```bash
uv run pytest -q --co 2>&1 | grep -iE "error" | head
uv run pytest -q tests/test_boostlss_xs_features.py tests/test_boostlss_xs_flagging.py tests/test_boostlss_xs_meta_labeler.py tests/test_boostlss_xs_universe.py tests/test_predict_placeholder.py tests/test_account_risk.py tests/test_barrier_manager.py
```
Expected: clean collection; listed tests pass.

- [ ] **Step 4: Commit**

```bash
git commit -m "chore: delete governance/parity/diagnostics/ops/live_restart subpackages

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Phase 4 — Slim Makefile, pyproject, observability, docs

### Task 4.1: Slim the Makefile to keep-set targets only

**Files:**
- Modify: `Makefile`

- [ ] **Step 1: Keep** `test`, `test-java`, `quality` (+ its sub-targets `ty lint vulture smellcheck radon xenon`), `format`, `precommit-install`, `precommit-run`, `jforex-live`, `pr`, `docs`, `docs-build`. **Delete** targets: `provision`, `observability-up/down`, `onboard-symbol`, `retrain-all`, `clean-data`, `clean-mining-outputs`, `rebuild-all`, `audit-all`, `freeze-live-governance`, `freeze-historical-governance`, `freeze-dukascopy-candidate-governance`, `validate-historical-governance`, `validate-bundles`, `dukascopy-testclient-parity`, `stage12-stage13-cert-artifacts`, `local-jforex-parity*`, `local-jforex-parity-matrix/ordinal/spotlight`, `local-jforex-cert`, `jforex-dukascopy-matrix`, `audit-runtime-parity`, `local-jforex-outcome-parity`, `jforex-outcome-parity`, `monthly-build`, `monthly-recert`, `promote-live`, `validate-live-stage-dag`, `seed-threshold`, `demo-cert-monitor*`, `offset-robustness-study`, `offset-frozen-screen`, `dukascopy-source-audit`, `reconcile-historical-predictions`, `summarize-runtime-db-run`, `account-risk-monitoring-report`, `reconcile-account-risk-reservations`, `check-legacy-drift`, `process-stage-docs`, `process-graph-contract`, `context-refresh`, `docs-contract`, `docs-contract-ci`.

- [ ] **Step 2: Edit `Makefile`** — delete the removed target blocks and any helper variables/scripts they reference. Keep `quality` intact (it's the gate).

- [ ] **Step 3: Verify**

```bash
grep -E "^[a-zA-Z_-]+:" Makefile
make -n test make -n jforex-live make -n quality
```
Expected: only keep-set targets listed; the three `-n` dry-runs print valid commands (no references to deleted scripts).

- [ ] **Step 4: Commit**

```bash
git commit -m "chore(make): slim Makefile to keep-set targets (drop mining/governance/cert)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 4.2: Trim pyproject deps + observability/CI config

**Files:**
- Modify: `pyproject.toml`, `.pre-commit-config.yaml`, `prometheus*.yml`, `alertmanager*.yml`, `docker-compose.yml`, `provisioning/`

- [ ] **Step 1: Audit which deps boostlss_xs + the runtime scaffold actually import**

```bash
grep -rhoE "^(import|from) [a-z_]+" scripts/boostlss_xs src/behemoth 2>/dev/null | sort -u
```
Keep deps used by `boostlss_xs` (boostlss, xgboostlss, numpyro, statsmodels, catboost, scikit-learn, polars, numpy, pandas, pyarrow) and the runtime scaffold (fastapi, uvicorn, duckdb, pydantic, pydantic-settings, pyyaml, prometheus-client, python-json-logger, pytz, tabulate, tqdm, joblib). Remove only deps confirmed unused after the cleanup. **Do not remove `catboost`** (boostlss_xs meta-labeler may use it — verify with `grep -rn catboost scripts/boostlss_xs`; if unused there AND runtime no longer loads models, remove it; otherwise keep).

- [ ] **Step 2: Edit `pyproject.toml`** — remove confirmed-unused deps. Bump version to `0.32.0` (cleanup release).

- [ ] **Step 3: Resync and verify**

```bash
uv sync
uv run python -c "import src.behemoth.api.server; import scripts.boostlss_xs.run"
```
Expected: clean.

- [ ] **Step 4: Audit observability/provisioning config** — keep prometheus/alertmanager/docker-compose only if the live scaffold still emits metrics (it does via `src/behemoth/observability`/`prometheus-client`). Remove governance/cert-specific alert rules and `provisioning/` pieces for removed systems.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: trim pyproject deps + observability config to keep-set surface

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 4.3: Update repo docs (CLAUDE.md, AGENTS.md, README, UBIQUITOUS_LANGUAGE, CONTEXT)

**Files:**
- Modify: `CLAUDE.md`, `AGENTS.md`, `README.md`, `UBIQUITOUS_LANGUAGE.md`, `CONTEXT.md`, `mkdocs.yml`

- [ ] **Step 1: Rewrite `CLAUDE.md`** — drop the governance/cert Quick Start and Stage 12–14 references; replace with: straddle logic in `scripts/boostlss_xs/`, live scaffold in `src/behemoth/{api,runtime,core,risk}` + `src/jforex/`, predict path is a placeholder pending boostlss_xs wiring.

- [ ] **Step 2: Rewrite `AGENTS.md`** — remove worktree-governance, monthly-recert, stage-cert, tick-opportunity-mining sections; keep the git-worktree workflow and the `make test`/`make quality`/`make jforex-live` commands.

- [ ] **Step 3: Trim `UBIQUITOUS_LANGUAGE.md`** — keep verdict values and the straddle/OCO/feature vocabulary; remove governance-stage, candidate-lock, certification vocabulary.

- [ ] **Step 4: Trim `README.md` + `CONTEXT.md` + `mkdocs.yml`** — remove nav references to deleted docs/pages.

- [ ] **Step 5: Build docs to verify no broken references**

```bash
make docs-build 2>&1 | tail -20
```
Expected: builds with no broken-link errors (or fix them).

- [ ] **Step 6: Commit**

```bash
git commit -m "docs: rewrite CLAUDE.md/AGENTS.md/etc for the slimmed repo

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Phase 5 — Final verification

### Task 5.1: Full quality gate + test suite

- [ ] **Step 1: Quality gate**

```bash
make quality
```
Expected: ty/ruff/vulture/smellcheck/radon/xenon all pass. Fix any reported dead code from the cleanup (vulture will flag the newly-unused governance helpers).

- [ ] **Step 2: Full Python test suite**

```bash
uv run pytest -q
```
Expected: all remaining tests pass. The remaining suite should be: boostlss_xs (4), api/runtime scaffold, risk, jforex-adjacent. Record the count.

- [ ] **Step 3: Java/JForex tests**

```bash
make test-java
```
Expected: JForex tests pass (they test the Java client + HTTP contract, unaffected by the placeholder — confirm no Java test hits `/predict` expecting real predictions; if so, update the Java test to expect empty predictions).

- [ ] **Step 4: End-to-end smoke — JForex connects to the placeholder runtime**

```bash
BEHEMOTH_SYMBOLS=EURUSD uv run uvicorn src.behemoth.api.server:app --port 8100 &
sleep 3
curl -s -X POST http://localhost:8100/predict -H 'Content-Type: application/json' \
  -d '{"symbol":"EURUSD","close_ts":"2025-01-01T00:00:00Z","bar_ticks":100,"features":{}}'
```
Expected: `{"predictions":[]}`. Then `kill %1`.

- [ ] **Step 5: Commit any final fixes**

```bash
git add -A
git commit -m "test: verify slimmed repo — quality gate, pytest, jforex, placeholder smoke

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 5.2: Open the PR

- [ ] **Step 1: Push the branch**

```bash
git push -u origin feat/repo-cleanup
```

- [ ] **Step 2: Open PR** via `gh pr create` — title `chore: repo cleanup — keep straddle + jforex scaffold, drop governance/mining/experiments`. Body summarises: keep set, removed systems, placeholder predict path, size reduction (note the 9 GB `.worktrees` was local-only, not in git), and that boostlss_xs→runtime wiring is a follow-up project. End body with the Claude Code attribution line.

- [ ] **Step 3: Update memory** — in this session, write a memory entry recording the cleanup (repo now = boostlss_xs + jforex scaffold + placeholder predict; mining/governance/cert/experiments removed in PR #NNN) and delete/flag stale governance memory entries that no longer apply.

---

## Out of scope (future projects)

- **Wire boostlss_xs into the runtime** — replace the placeholder `/predict` with the boostlss_xs straddle model (produce a deployable artifact from `scripts/boostlss_xs/run.py`, define the candidate/spec mapping from `boostlss_xs/config.py` `LIVE_PAIRS`/`ENTRY_K`/`SL_K`/`HOLD_HOURS`/`EXCLUDED_HOURS_UTC`, feed predictions through the runtime barrier/OCO execution). This is a build, not a cleanup.
- Re-evaluate whether `catboost` dep stays once boostlss_xs wiring lands.