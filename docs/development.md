# Development Workflow

## Pre-commit Hooks
We use pre-commit to enforce basic hygiene, type checking, and docs build consistency.

Install hooks:

```bash
make precommit-install
```

Run all hooks manually:

```bash
make precommit-run
```

What runs by default:

- Formatting hygiene: trailing whitespace, EOF newline, YAML/TOML checks, merge conflict markers, large files.
- `ruff` lint + format for Python.
- `ty` type check across `src`, `services`, `scripts`, `tests`.

What runs on `pre-push`:

- OCO docs contract/gov checks via `make docs-contract`.
- Full docs build via `make docs-build` (export OpenAPI + mkdocs build).

If you need to bypass hooks temporarily, use `SKIP=ty,docs-build` with pre-commit. Avoid this for normal development.

## Docs Build
To preview docs locally:

```bash
make docs
```

To build docs:

```bash
make docs-build
```

To run OCO docs contracts explicitly:

```bash
make docs-contract
```

CI-safe (no heavy recompute) contract run:

```bash
make docs-contract-ci
```

## Server CI
GitHub Actions now enforces the same contract server-side:

- `.github/workflows/docs_contract.yml`
- Runs `make docs-contract-ci`, rebuilds strategy-bible snapshots, then `mkdocs build`.
- Uploads contract artifacts (`docs_contract_checks.csv`, registry checks, alert disposition report) for review on failures.

- `.github/workflows/tests_fast.yml`
- Runs focused OCO governance/docs tests:
- `tests/test_build_docs_catalog.py`
- `tests/test_stage_integrity_gate.py`
- `tests/test_execution_drift_report.py`
- `tests/test_threshold_sensitivity_report.py`
- `tests/test_validate_oco_rule_universe_registry.py`
- `tests/test_remediate_oco_monitoring_alerts.py`
- `tests/test_oco_docs_contract.py`

## Test Run
Quick test run:

```bash
make test
```

Postgres integration test:

```bash
make test-postgres
```

## Linting/Formatting
Lint:

```bash
make lint
```

Format:

```bash
make format
```

## Baseline Snapshots
Generate golden baselines for M5/M15 validation:

```bash
make baselines
```

Baseline tests are hard-gated. Any mismatch or pipeline hash change fails CI.

## DB Backup Smoke Test
Run a backup/restore smoke test (requires docker compose up):

```bash
make db-restore-smoke
```
