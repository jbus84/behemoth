# Rolling Threshold Min History 300 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Change the canonical rolling-threshold minimum history floor from 1000 to 300 and propagate that value into the March live governance locks used by `main`.

**Architecture:** Update the governance source of truth instead of changing runtime threshold logic. Keep the API behavior unchanged, refresh the frozen March live locks from the updated canonical source, and tighten the targeted tests that currently encode `1000`.

**Tech Stack:** Python, YAML/JSON governance artifacts, pytest

---

### Task 1: Update Canonical Threshold Contract

**Files:**
- Modify: `configs/research/governance/oco_rule_universe_registry.yaml`
- Modify: `scripts/run_tick_opportunity_monthly_wfo.py`

- [ ] **Step 1: Update the governance registry floor**

Set `locked_runtime_contract.rolling_threshold_min_history` to `300` in `configs/research/governance/oco_rule_universe_registry.yaml`.

- [ ] **Step 2: Update the WFO default**

Set `DEFAULTS["rolling_threshold_min_history"]` to `300` in `scripts/run_tick_opportunity_monthly_wfo.py` so future lock freezes inherit the same value.

### Task 2: Refresh March Governance Locks

**Files:**
- Modify: `configs/research/governance/oco/*.json`

- [ ] **Step 1: Regenerate the promoted March lock artifacts**

Refresh the six promoted live lock JSON files so each `thresholds.rolling_threshold_min_history` becomes `300`.

- [ ] **Step 2: Check for drift**

Confirm the refreshed lock values match the canonical source and do not alter unrelated execution contract fields.

### Task 3: Update Tests And Verify

**Files:**
- Modify: `tests/test_oco_live_governance.py`
- Modify: `tests/test_validate_oco_rule_universe_registry.py`

- [ ] **Step 1: Update expectations**

Change test fixtures and string expectations that currently assert `rolling_threshold_min_history: 1000` so they assert `300` instead.

- [ ] **Step 2: Run targeted verification**

Run:

```bash
rtk uv run pytest -q tests/test_oco_live_governance.py tests/test_validate_oco_rule_universe_registry.py
```

Expected: both test files pass with the new canonical floor of `300`.

- [ ] **Step 3: Update graphify**

Run:

```bash
graphify update .
```

Expected: graph artifacts refresh cleanly after the code/config edits.
