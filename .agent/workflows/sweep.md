---
description: Sweep the repository for legacy drift and run consistency checks
---

This workflow executes the standard post-task checks to ensure that no legacy concepts have drifted back into the codebase, and all documentation and tests are perfectly consistent.

// turbo-all
1. Run the legacy drift checker script to ensure no forbidden terms (kalman, old APIs) have re-entered the repo.
`uv run python scripts/check_legacy_drift.py`

2. Run the pytest suite to ensure no tests are broken.
`uv run pytest -q`

3. Verify the docs contract is clean and there are no stage integrity errors.
`uv run python scripts/validate_oco_docs_contract.py --out-checks-csv data/analysis/tick_opportunity_mining/docs_contract_checks.csv --out-issues-csv data/analysis/tick_opportunity_mining/docs_contract_issues.csv --report-out docs/analysis/oco_docs_contract_report.md`
