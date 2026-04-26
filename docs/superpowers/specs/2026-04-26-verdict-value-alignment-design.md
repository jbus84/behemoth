# Verdict Value Alignment — Design Spec

**Date:** 2026-04-26
**Goal:** Align all certification script verdict/status string values and CSV column names with the canonical ubiquitous language. Also ensure agent config files (Claude and Codex) always reference `UBIQUITOUS_LANGUAGE.md` before using domain terminology.

---

## Context

The ubiquitous language (see `UBIQUITOUS_LANGUAGE.md`) defines canonical deployment decision terms:

| Term | Meaning |
|------|---------|
| `PASS` | Process completed correctly and produced valid evidence |
| `FAIL` | Process or evidence is invalid and cannot justify promotion |
| `GO` | Symbol is eligible for deployment |
| `NO_GO` | Symbol intentionally not deployed; process did not fail |

The certification scripts (Stages 13, 14, local JForex surrogate) currently emit lowercase `"pass"`, `"fail"`, and `"nogo"` into CSV output, and two boolean column names use the `_nogo` suffix. These diverge from the canonical terms and create ambiguity when reading reports.

---

## Schema Changes

### Verdict/status string values

Three scripts are both the emit surface and the scope boundary for value migration:

- `scripts/validate_stage14_jforex_runtime_certification.py`
- `scripts/validate_stage13_dukascopy_testclient.py`
- `scripts/validate_local_jforex_surrogate.py`

| Current value | Canonical value | Column(s) affected |
|---|---|---|
| `"nogo"` | `"NO_GO"` | `verdict`, `status` |
| `"pass"` | `"PASS"` | `status` |
| `"fail"` | `"FAIL"` | `status` |

### Boolean column renames

| Current column name | New column name | Script |
|---|---|---|
| `local_jforex_surrogate_nogo` | `local_jforex_surrogate_no_go` | `validate_local_jforex_surrogate.py` |
| `stage13_dukascopy_testclient_nogo` | `stage13_dukascopy_testclient_no_go` | `validate_stage13_dukascopy_testclient.py` |

### What does NOT change

The input-parser alias sets (e.g. `{"no_go", "no-go", "nogo"}` accepted as user input in `validate_stage14_jforex_runtime_certification.py:67`) are user-facing input tolerance, not schema values. Leave them untouched.

Audit scripts with their own internal check schemas (`audit_oco_pipeline_logical_issues.py`, `audit_data_reliability.py`, `check_oco_docs_stage_integrity.py`, `register_docs_run.py`) use lowercase `"pass"`/`"fail"` as an internal convention. These are a different surface and out of scope for this migration.

`RestartVerdict` enum legacy values (`CLEAN_RESUMABLE`, `RECONCILABLE`, `INCOMPATIBLE`) in `src/behemoth/live_restart/reconciliation.py` are also out of scope — they touch live restart code and warrant a separate, careful PR.

---

## Reader Updates

Two scripts parse CSV verdict/status values back in and must be updated to match the new emit values:

- `scripts/run_monthly_recert.py` — guards on `status != "pass"`, `status in {"nogo", "no_go", "no-go"}`
- `scripts/run_promote_live.py` — guard on `status not in ("pass", "nogo")`

### Known pre-existing inconsistency to investigate

`tests/test_run_monthly_recert.py:247` asserts `"USDCAD  NOGO" in out` (no underscore), but `run_monthly_recert.py` already normalises decisions to `"NO_GO"` internally. The implementer must confirm whether the printed summary format strips the underscore or whether this is a stale test assertion, and fix accordingly.

---

## Checked-in CSV Migration

Four files in `data/analysis/backtest_reconcile/` contain old values and column names and must be updated as part of the atomic migration:

- `stage13_dukascopy_testclient_summary.csv` — column `stage13_dukascopy_testclient_nogo`, verdict values
- `local_jforex_surrogate_summary.csv` — column `local_jforex_surrogate_nogo`, verdict values
- `stage14_jforex_runtime_certification_checks.csv` — status values
- `local_jforex_surrogate_checks.csv` — status values

These can be updated by re-running the generating scripts (preferred) or by sed-patching the headers and values directly. Either way, verify with grep that no lowercase `nogo`, `pass`, or `fail` remain after the update.

---

## Agent Config Updates

### Rule (identical in both files)

> Before using any domain term, verdict value, column name, or operator-facing string — read `UBIQUITOUS_LANGUAGE.md`. Use only the canonical terms defined there. Do not invent synonyms or use the aliases listed in the "Aliases to avoid" column.

### Files to update

| File | Action |
|------|--------|
| `CLAUDE.md` | Add a new `## Ubiquitous Language` block |
| `AGENTS.md` | Add a new numbered section before the 5-minute health check |

No changes to `.codex/hooks.json` — terminology instruction belongs in prose, not a shell hook.

---

## Migration Strategy

**Atomic single-pass.** The repo owns every emit site and every reader. No external consumers of these CSVs exist. Compatibility shims or schema versioning would add ceremony for no benefit.

---

## Task Structure

| Task | Files | Commit message |
|------|-------|----------------|
| 1 | `CLAUDE.md`, `AGENTS.md` | `docs: add ubiquitous language rule to agent config files` |
| 2 | 3 emit scripts | `fix: align certification verdict values with ubiquitous language` |
| 3 | 2 reader scripts | `fix: update readers to match canonical verdict values` |
| 4 | 4 checked-in CSVs | `data: regenerate certification CSVs with canonical verdict values` |
| 5 | 7 test files | `test: update assertions to canonical verdict values` |

Final verification after Task 5:
- `pytest` — full suite green
- `rg "nogo|\"pass\"|\"fail\"" scripts/ src/ tests/ data/analysis/backtest_reconcile/` — no hits outside input-parser alias sets and out-of-scope audit scripts

---

## Out of Scope

- `RestartVerdict` enum rename (`CLEAN_RESUMABLE`, `RECONCILABLE`, `INCOMPATIBLE`) — separate PR
- Audit script internal check schemas (`audit_oco_pipeline_logical_issues.py` etc.) — different surface, different risk profile
- Input-parser alias tolerance sets — user-facing, intentional
