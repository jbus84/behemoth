# AGENTS Guide (Repo Onboarding)

This file is the fastest path to becoming productive in this repo.

## 0) Ubiquitous Language

This project has a canonical vocabulary defined in `UBIQUITOUS_LANGUAGE.md`.

Before using any domain term, verdict value, column name, or operator-facing string — read `UBIQUITOUS_LANGUAGE.md`. Use only the canonical terms defined there. Do not invent synonyms or use the aliases listed in the "Aliases to avoid" column.

Key deployment decision terms:
- `PASS` — process completed correctly and produced valid evidence
- `FAIL` — process or evidence is invalid and cannot justify promotion
- `GO` — symbol is eligible for deployment
- `NO_GO` — symbol intentionally not deployed; process did not fail

## 1) What Is Actually Active

The active system is the tick-based OCO stop-limit research/governance pipeline documented in:

- `docs/STRATEGY_MASTER_MANUAL.md`
- `docs/strategy_bible/`
- `docs/analysis/`

Do not treat `README.md` as authoritative for detailed strategy behavior. Read the strategy bible and master manual instead.

Execution runtime direction:

- Python remains the authoritative inference/governance runtime.
- Dukascopy JForex is the active broker-adapter target.
- CTrader/cBot and FTMO paths are legacy compatibility surfaces pending removal after Stage 14 is green.

Branch truth:

- Specs and plans must name the target branch and target commit, and execution must run from a worktree created from that target branch at the target commit or a descendant of it.
- If a required semantic is not on `main`, move the work to the authoritative feature branch.
- branch-semantic drift at final verification is a hard stop, not a docs patching opportunity.

Runtime truth:

- Stage certification verdicts are not authoritative unless they are run against the authoritative local runtime environment and evidence root.
- Worktrees are the default place for implementation and tests, but they are not automatically authoritative for Stage 12, Stage 13, or Stage 14 verdicts.
- Before claiming a stage is green or red, confirm the execution context has the same required local inputs as the root environment:
  - local artifact/evidence files under `data/analysis/backtest_reconcile/`
  - local model/governance inputs used by the target stage
  - machine-local runtime credentials or broker prerequisites
- If that equivalence is not explicit and verified, final stage verdicts must be run from the root checkout or another explicitly designated authoritative runtime worktree.
- Treat “code/tests pass in worktree” and “stage certification is green” as different claims. Do not collapse them.
- JForex-dependent human or agent commands should ensure the shared root `.env` is sourced before execution. Do not commit `.envrc`; prefer command wrappers or an already-loaded shell.

## 2) Active Symbol Universe

- `EURUSD`
- `GBPUSD`
- `USDJPY`
- `USDCHF`
- `AUDUSD`
- `USDCAD`

## 3) Core Data Paths

- Raw ticks (canonical, external local machine): `/Users/danielfisher/Desktop/dukascopy_ticks/<SYMBOL>/<SYMBOL>_YYYYMM_ticks.parquet`
- Raw ticks (legacy HistData compatibility): `/Users/danielfisher/Desktop/tick/<SYMBOL>/<SYMBOL>_YYYYMM_ticks.parquet`
- Tick bars: `data/global_tickbars/<SYMBOL>_{100,1000,2000}tick.parquet`
- Velocity datasets: `data/analysis/tick_velocity/<SYMBOL>_{100,1000,2000}tick_velocity.parquet`
- Main pipeline artifacts: `data/analysis/tick_opportunity_mining/`

Canonical raw tick parquet schema:

- `timestamp` (UTC)
- `bid`
- `ask`
- `mid`
- `spread`
- `log_return`

## 4) Key Scripts (OCO Path)

- Ingestion helper: `scripts/download_histdata_ticks.py`
- Tick bars: `scripts/build_global_tick_bars.py`
- Velocity features: `scripts/build_tick_velocity_dataset.py`
- Stage 2 mining: `scripts/run_tick_opportunity_mining.py`
- Stage 3 monthly WFO (CatBoost): `scripts/run_tick_opportunity_monthly_wfo.py`
- Stage 4 stop-limit realism: `scripts/analyze_oco_stop_limit_tickfill.py`
- Stage 5 reduced-core rolling: `scripts/select_oco_reduced_core_rolling.py`
- Stage 6 tick-exact verifier: `scripts/verify_oco_tick_exact_shortlist.py`
- Stage 8 robustness: `scripts/analyze_oco_monthly_wfo_robustness.py`
- Stage 13 certification: `scripts/validate_stage13_dukascopy_testclient.py`
- Stage 14 certification: `scripts/validate_stage14_jforex_runtime_certification.py`
- Pre-Stage JForex surrogate: `make local-jforex-parity`
- Docs contract: `scripts/validate_oco_docs_contract.py`

Java/JForex runtime:

- Gradle module: `src/jforex/`
- Main strategy entrypoint: `com.behemoth.jforex.BehemothJForexStrategy`
- Tester runner: `com.behemoth.jforex.JForexTesterRunner`
- Live runner: `com.behemoth.jforex.JForexLiveRunner`
- Local surrogate runner: `com.behemoth.jforex.LocalJForexTesterRunner`
- Official Stage 13 harness: `scripts/replay_dukascopy_testclient.py`
- Official Stage 14 harness: JForex `ITesterClient`
- JForex Prometheus endpoint: `127.0.0.1:9464/metrics`
- Local surrogate Prometheus endpoint default: `127.0.0.1:9465/metrics`

## 5) Config Entry Points

Experiment configs:

- `configs/research/experiments/eurusd_tick_opportunity_mining.yaml`
- `configs/research/experiments/eurusd_tick_opportunity_monthly_wfo_oco_fullcap.yaml`
- `configs/research/experiments/eurusd_oco_reduced_core_rolling.yaml`
- `configs/research/experiments/gbpusd_tick_opportunity_monthly_wfo_oco_fullcap.yaml`
- `configs/research/experiments/gbpusd_oco_reduced_core_rolling.yaml`
- `configs/research/experiments/usdjpy_tick_opportunity_monthly_wfo_oco_fullcap.yaml`
- `configs/research/experiments/usdjpy_oco_reduced_core_rolling.yaml`
- `configs/research/experiments/usdchf_tick_opportunity_mining.yaml`
- `configs/research/experiments/usdchf_tick_opportunity_monthly_wfo_oco_fullcap.yaml`
- `configs/research/experiments/usdchf_oco_reduced_core_rolling.yaml`

Docs/build manifest:

- `configs/research/docs/oco_bible_manifest.yaml`

Governance locks:

- `configs/research/governance/oco/*_oco_live_lock.json`

## 6) 5-Minute Health Check

Run from repo root:

```bash
git status --short
mise install
uv run pytest -q tests/test_oco_docs_contract.py tests/test_tick_opportunity_mining.py tests/test_tick_opportunity_ml_dataset.py tests/test_oco_leakage_label_integrity.py tests/test_monthly_wfo_threshold_causality.py
gradle :jforex-adapter:test
uv run python scripts/validate_oco_docs_contract.py --out-checks-csv data/analysis/tick_opportunity_mining/docs_contract_checks.csv --out-issues-csv data/analysis/tick_opportunity_mining/docs_contract_issues.csv --report-out docs/analysis/oco_docs_contract_report.md
```

Current known docs-contract failure may remain:

- `C4A` (`nan_metric_values`) in `edge_clarity_stage_metrics.csv`

Treat that as a known issue unless user explicitly asks to fix it.

## 7) Standard Docs Rebuild

Fast full docs/gov refresh:

```bash
make docs-contract-ci
make stage13-dukascopy-cert
make stage14-jforex-cert
uv run mkdocs build
```

Serve docs locally:

```bash
make docs
```

Serves at `127.0.0.1:8001`.

## 8) End-to-End Symbol Pipeline (Template)

Replace `<SYM>` and config paths as needed.

1. Build bars:

```bash
uv run python scripts/build_global_tick_bars.py \
  --tick-root /Users/danielfisher/Desktop/tick \
  --output-dir data/global_tickbars \
  --symbols <SYM> \
  --base-ticks 100 \
  --aggregate-multiples 1,10,20 \
  --price-source bid \
  --timestamp-mode as_utc \
  --overwrite
```

2. Build velocity:

```bash
uv run python scripts/build_tick_velocity_dataset.py \
  --tick-root /Users/danielfisher/Desktop/tick \
  --tickbar-dir data/global_tickbars \
  --out-dir data/analysis/tick_velocity \
  --symbols <SYM> \
  --bar-ticks-grid 100,1000,2000 \
  --overwrite
```

3. Mining:

```bash
uv run python scripts/run_tick_opportunity_mining.py --config configs/research/experiments/<sym>_tick_opportunity_mining.yaml
```

4. Monthly WFO:

```bash
uv run python scripts/run_tick_opportunity_monthly_wfo.py --config configs/research/experiments/<sym>_tick_opportunity_monthly_wfo_oco_fullcap.yaml
```

5. Stop-limit realism:

```bash
uv run python scripts/analyze_oco_stop_limit_tickfill.py \
  --symbols <SYM> \
  --pred-paths data/analysis/tick_opportunity_mining/wfo_m3to1_oco_fullcap_<sym>/<SYM>_oco_monthly_predictions.parquet \
  --velocity-dir data/analysis/tick_velocity \
  --tick-root /Users/danielfisher/Desktop/tick \
  --caps 0.5,0.8,1.0,1.2,1.5,2.0 \
  --use-exec-selected true \
  --quantile 0.9 \
  --out-dir data/analysis/tick_opportunity_mining/stop_limit_tickfill_fullcap
```

6. Reduced-core rolling:

```bash
uv run python scripts/select_oco_reduced_core_rolling.py --config configs/research/experiments/<sym>_oco_reduced_core_rolling.yaml
```

7. Tick-exact:

```bash
uv run python scripts/verify_oco_tick_exact_shortlist.py \
  --symbol <SYM> \
  --dataset-dir data/analysis/tick_velocity \
  --pred-path data/analysis/tick_opportunity_mining/wfo_m3to1_oco_fullcap_<sym>/<SYM>_oco_monthly_predictions.parquet \
  --shortlist-state-csv data/analysis/tick_opportunity_mining/reduced_core_rolling/<SYM>_oco_reduced_state_schedule.csv \
  --locked-quantile 0.9 \
  --selection-mode auto \
  --family-required oco_first_touch_clean \
  --oco-hold-mode from_touch \
  --oco-include-no-touch true
```

8. Robustness:

```bash
uv run python scripts/analyze_oco_monthly_wfo_robustness.py \
  --pred-path data/analysis/tick_opportunity_mining/wfo_m3to1_oco_fullcap_<sym>/<SYM>_oco_monthly_predictions.parquet \
  --quantiles 0.5,0.6,0.7,0.8,0.9,0.95 \
  --bootstrap-paths 600 \
  --stress-extra-cost-grid 0.1,0.2,0.3,0.5
```

## 9) HistData Ingestion (New Months)

Use:

```bash
uv run python scripts/download_histdata_ticks.py \
  --symbols EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD \
  --months 202601,202602 \
  --tick-root /Users/danielfisher/Desktop/tick \
  --source-tz-policy america_new_york \
  --skip-existing true
```

This downloads monthly ZIPs from HistData and writes canonical parquet. It does not keep ZIP/CSV artifacts.
Default policy localizes HistData raw timestamps as `America/New_York` then converts to UTC.

This is now a compatibility-only ingest path. Canonical execution and replay should prefer Dukascopy parquet.

## 10) Tooling

- Python: `uv`
- Java/JForex: Gradle project in `src/jforex`
- Toolchain pinning: `mise.toml`

Recommended setup:

```bash
mise install
uv sync
gradle :jforex-adapter:test
```

Java conventions:

- Keep broker adapter code under `src/jforex/src/main/java/com/behemoth/jforex/`
- Use immutable records for wire/domain payloads where practical
- Put JUnit 5 tests under `src/jforex/src/test/java/`
- Keep JForex-specific code thin; Python remains the decision engine
- Shared Java strategy logic should live below the runtime shim so real JForex and local surrogate runs exercise the same core

## 11) Governance/Docs Integration Notes

- Many governance reports read shared aggregate files in `data/analysis/tick_opportunity_mining/`.
- If you rerun stop-limit with one symbol only, you may overwrite shared summary files. Prefer running all active symbols when updating shared reports.
- After changing symbol universe, regenerate:
  - `oco_execution_drift_*`
  - `oco_threshold_sensitivity*`
  - `oco_alert_disposition.csv`
  - `oco_governance_explainability.csv`
  - strategy bible and docs contract outputs

## 12) Common Pitfalls

- `README.md` can mislead strategy context; use strategy bible/manual instead.
- Some scripts still encode assumptions around historical 3-symbol universe. If adding/removing symbols, check for hardcoded symbol sets.
- Long robustness runs can take several minutes and often produce output only at completion.
- `uv run` can hit sandbox cache permission issues in restricted execution; rerun with elevated permissions when needed.
- Do not delete or rewrite user data under `/Users/danielfisher/Desktop/tick` unless explicitly asked.

## 13) Docs-Driven Blindspots to Check Explicitly

- `docs-contract pass` means docs/artifact contract integrity; it does **not** guarantee all symbols are deployable.
- Treat `stage_09_snapshot` predeploy coverage as mandatory:
  - if `failed_checks` contains `missing_predeploy_json`, governance is incomplete.
  - if `g01_near_fail_count` or `g03_lock_drift_flags` are `nan`, treat as data gap.
- Confirm symbol-level readiness via:
  - `docs/strategy_bible/generated/stage_09_snapshot.md`
  - `docs/analysis/operator_action_report.md`
  - `docs/analysis/oco_alert_remediation_report.md`
- Governance freeze default symbol source is the registry (`configs/research/governance/oco_rule_universe_registry.yaml`).
  - If running with `--symbols` subset, verify you are not unintentionally leaving symbols stale.
- Tiered strictness policy:
  - fail hard on missing predeploy/governance coverage gaps,
  - treat non-green strategy gates as monitored blockers unless user explicitly requests strict all-symbol enforcement.

Quick go/no-go checklist:
1. No `missing_predeploy_json` rows for active symbols in Stage 9.
2. No `A9_DATA_GAP` caused by missing governance diagnostics (`G01/G03`).
3. No unresolved high/critical blockers in operator/remediation reports.
4. Docs contract and mkdocs build both pass on fresh artifacts.

## 14) Definition of Done for Agent Changes

Before finalizing substantial changes:

1. Relevant pipeline scripts executed and artifacts produced.
2. Targeted tests pass.
3. `mkdocs build` succeeds.
4. `docs_contract_checks.csv` regenerated and reviewed.
5. `make stage13-dukascopy-cert` and `make stage14-jforex-cert` executed or explicitly noted as pending when broker artifacts are unavailable.
5. `git status` is clean after commit, and changes are pushed if requested.
