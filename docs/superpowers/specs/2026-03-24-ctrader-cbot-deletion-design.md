# cTrader / cBot Deletion — Design Spec

**Date:** 2026-03-24
**Status:** Approved

---

## Problem

The codebase contains a substantial body of cTrader and cBot tooling that is entirely dead. The platform is now JForex-only. This code adds noise, inflates test counts, and is confusing to anyone reading the codebase.

---

## Goal

Remove all cTrader/cBot scripts, tests, source files, and Makefile targets in a single clean commit, leaving the test suite green.

---

## Dependency note: ordering with Sub-project B

`scripts/build_ftmo_allocator_monitoring_report.py` and `scripts/reconcile_ftmo_reservations.py` are currently used as backends by the `account_risk_*` wrapper scripts. They are **not** deleted here — Sub-project B (FTMO rename) converts those wrappers to standalone implementations and then deletes the old files. Sub-project A (this spec) deletes only pure cTrader/cBot code.

---

## What Gets Deleted

### Scripts (`scripts/`)

| File | Reason |
|------|--------|
| `build_ctrader_ab_parity_report.py` | cTrader A/B parity — dead |
| `build_ctrader_debug_bundle.py` | cTrader debug — dead |
| `evaluate_ftmo_challenge_run.py` | FTMO Challenge eval — dead |
| `export_ctrader_custom_data.py` | cTrader custom data export — dead |
| `manage_ctrader_debug_session.py` | cTrader debug session — dead |
| `reconcile_ctrader_vs_research.py` | cTrader reconciliation — dead |
| `replay_cbot_testclient.py` | cBot replay — dead |
| `replay_dukascopy_testclient.py` | thin wrapper over `replay_cbot_testclient` — dead with it |
| `replay_histdata_cbot_surrogate.py` | cBot surrogate replay — dead |
| `replay_histdata_cbot_testclient.py` | cBot testclient replay — dead |
| `validate_ctrader_execution_parity.py` | cTrader execution parity — dead |
| `validate_histdata_ctrader_execution_parity.py` | histdata cTrader parity — dead |
| `verify_cbot_handshake.py` | cBot handshake — dead |

### `scripts/run_offset_tickbar_robustness.py` — subprocess dependency

This script invokes `replay_histdata_cbot_testclient.py` as a subprocess (line ~1019). With that script deleted, this call would fail. The fix: remove the subprocess invocation entirely from `run_offset_tickbar_robustness.py`. The offset robustness study was designed for cBot parity; the JForex equivalent (if needed) is a separate future task. The script itself (and its Makefile target `offset-robustness-study`) is kept but the cBot subprocess call is removed or replaced with a `NotImplementedError` guard.

### Tests (`tests/`)

| File | Reason |
|------|--------|
| `test_build_ctrader_ab_parity_report.py` | tests deleted script |
| `test_build_ctrader_debug_bundle.py` | tests deleted script |
| `test_build_ftmo_allocator_monitoring_report.py` | tests deleted script (deleted here even though the script stays until Sub-project B — tests test the old ftmo script, not the wrapper) |
| `test_evaluate_ftmo_challenge_run.py` | tests deleted script |
| `test_export_ctrader_custom_data.py` | tests deleted script |
| `test_ftmo_risk.py` | tests cTrader-era FTMO risk tooling (covered by `test_account_risk.py` after Sub-project B) |
| `test_manage_ctrader_debug_session.py` | tests deleted script |
| `test_reconcile_ctrader_vs_research.py` | tests deleted script |
| `test_reconcile_ftmo_reservations.py` | tests the old ftmo reservations script (deleted here; wrapper is tested separately) |
| `test_replay_histdata_cbot_surrogate.py` | tests deleted script |
| `test_replay_histdata_cbot_testclient.py` | tests deleted script |
| `test_validate_histdata_ctrader_execution_parity.py` | tests deleted script |

### Source directory

| Path | Reason |
|------|--------|
| `src/cbot/` | C# cTrader robot and plugin — dead platform |

### Makefile targets to remove

`deploy-cbot`, `deploy-ctrader`, `reconcile-ctrader-run`, `export-ctrader-custom-data`, `ctrader-debug-up`, `ctrader-debug-down`, `ctrader-debug-status`, `cbot-surrogate`, `ctrader-ab-parity-report`, `ctrader-parity`, `histdata-ctrader-parity`, `testclient-parity`, `dukascopy-testclient-parity`, `histdata-testclient-parity`, `ftmo-eval`

Also remove from the `.PHONY` line and remove associated variable definitions (`CTRADER_ROBOT_DST`, `CTRADER_PLUGIN_DST`, etc.).

### `scripts/check_legacy_drift.py`

This script has a `FORBIDDEN_TERMS` list that includes `src/cbot` as a term to detect cBot drift. After `src/cbot/` is deleted, that entry will never match anything (not a bug, but it is dead config). Remove the `src/cbot` entry from `FORBIDDEN_TERMS` to keep the script accurate.

---

## What Stays

- `scripts/build_ftmo_allocator_monitoring_report.py` — stays until Sub-project B replaces it
- `scripts/reconcile_ftmo_reservations.py` — stays until Sub-project B replaces it
- `scripts/run_offset_tickbar_robustness.py` — stays, but cBot subprocess call removed
- `scripts/reconcile_account_risk_reservations.py` — stays (Sub-project B rewrites it standalone)
- `scripts/build_account_risk_monitoring_report.py` — stays (Sub-project B rewrites it standalone)
- All other scripts not listed above

---

## Error Handling / Risk

- No production code paths are affected — all deleted files are standalone scripts
- The only live dependency is the subprocess call in `run_offset_tickbar_robustness.py`, addressed above
- After deletion, run `pytest tests/` — all remaining tests must pass

---

## Testing

No new tests. Success criterion: `pytest tests/` green after deletions and the `run_offset_tickbar_robustness.py` fix, test count reduced by ~12.

---

## Files Changed

| Path | Action |
|------|--------|
| `scripts/build_ctrader_ab_parity_report.py` | Delete |
| `scripts/build_ctrader_debug_bundle.py` | Delete |
| `scripts/evaluate_ftmo_challenge_run.py` | Delete |
| `scripts/export_ctrader_custom_data.py` | Delete |
| `scripts/manage_ctrader_debug_session.py` | Delete |
| `scripts/reconcile_ctrader_vs_research.py` | Delete |
| `scripts/replay_cbot_testclient.py` | Delete |
| `scripts/replay_dukascopy_testclient.py` | Delete |
| `scripts/replay_histdata_cbot_surrogate.py` | Delete |
| `scripts/replay_histdata_cbot_testclient.py` | Delete |
| `scripts/validate_ctrader_execution_parity.py` | Delete |
| `scripts/validate_histdata_ctrader_execution_parity.py` | Delete |
| `scripts/verify_cbot_handshake.py` | Delete |
| `scripts/run_offset_tickbar_robustness.py` | Remove cBot subprocess call |
| `scripts/check_legacy_drift.py` | Remove `src/cbot` from `FORBIDDEN_TERMS` |
| `tests/test_build_ctrader_ab_parity_report.py` | Delete |
| `tests/test_build_ctrader_debug_bundle.py` | Delete |
| `tests/test_build_ftmo_allocator_monitoring_report.py` | Delete |
| `tests/test_evaluate_ftmo_challenge_run.py` | Delete |
| `tests/test_export_ctrader_custom_data.py` | Delete |
| `tests/test_ftmo_risk.py` | Delete |
| `tests/test_manage_ctrader_debug_session.py` | Delete |
| `tests/test_reconcile_ctrader_vs_research.py` | Delete |
| `tests/test_reconcile_ftmo_reservations.py` | Delete |
| `tests/test_replay_histdata_cbot_surrogate.py` | Delete |
| `tests/test_replay_histdata_cbot_testclient.py` | Delete |
| `tests/test_validate_histdata_ctrader_execution_parity.py` | Delete |
| `src/cbot/` | Delete directory |
| `Makefile` | Remove cTrader/cBot targets, variables, and `.PHONY` entries |
