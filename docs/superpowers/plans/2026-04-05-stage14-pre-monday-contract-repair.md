# Stage 14 Pre-Monday Contract Repair Plan

## Baseline Contract
- Target branch: `main`
- Target commit: `20bf267`
- Authoritative semantics:
  - Stage 14 must separate `certification_outcome` from `go_decision`
  - `NO_GO` is not a certification failure
  - final stage verdicts must be validated from the authoritative local runtime environment
- Required compatibility checks:
  - `scripts/validate_stage14_jforex_runtime_certification.py`
  - `docs/strategy_bible/stage_14_jforex_runtime_certification.md`
  - `make stage14-jforex-cert`

## Task 1: Repair Validator Semantics
- Update `scripts/validate_stage14_jforex_runtime_certification.py` to emit `certification_outcome` and `go_decision`
- Preserve Stage 13 `PASS / NO_GO` semantics instead of treating `NO_GO` as a failed prerequisite by default
- Ensure final outputs cannot emit `FAIL / GO`
- Keep gate-level check rows intact so failure diagnosis remains explicit

## Task 2: Add/Update Test Coverage
- Update Stage 14 validator tests for the two-axis model
- Update any affected Java/report tests if summary contract changes require it
- Add regression coverage for historically or operationally non-go symbols certifying as `PASS / NO_GO`

## Task 3: Repair Authority Doc
- Update `docs/strategy_bible/stage_14_jforex_runtime_certification.md`
- Remove wording that treats `nogo` as a blocked certification path
- Tighten stale placeholder-style sections and align the doc to current Stage 13 semantics

## Task 4: Regenerate Stage 14 Outputs
- Run `make stage14-jforex-cert` against the authoritative local runtime environment
- Regenerate:
  - `data/analysis/backtest_reconcile/stage14_jforex_runtime_certification_summary.csv`
  - `data/analysis/backtest_reconcile/stage14_jforex_runtime_certification_checks.csv`
  - `docs/analysis/stage14_jforex_runtime_certification_report.md`
  - `docs/strategy_bible/generated/stage_14_snapshot.md`
- Confirm outputs are internally correct even if they remain red on current tester artifacts

## Task 5: Verification And Finish
- Run targeted Stage 14 validator tests
- Run any affected Java/report tests
- Run `uv run mkdocs build`
- Review final Stage 14 outputs for correct `PASS|FAIL` and `GO|NO_GO` separation
- If green from a code-quality perspective, prepare branch for PR/merge
