# Dukascopy Demo Certification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a thin operator-facing certification layer so tomorrow's Dukascopy demo run can prove all 6 symbols reach `READY`, ingest ticks, and show live `/predict` activity with easy Grafana/Prometheus observation.

**Architecture:** Reuse the existing observability stack and provisioned JForex dashboard instead of adding a second stack. Add one focused automated guard test for the dashboard/Makefile assets, extend the existing Grafana JSON with certification panels, add a one-command monitoring helper target in `Makefile`, and update operator-facing docs with the exact certification flow and pass/fail rules.

**Tech Stack:** GNU Make, Grafana dashboard JSON, Prometheus, pytest, mkdocs, existing JForex Prometheus metrics

---

## File Structure

- `tests/test_jforex_demo_certification_assets.py`
  - Focused regression guard for the new certification assets.
  - Verifies the provisioned JForex dashboard JSON contains the required readiness/predict panels and that the Makefile exposes the certification target/help text.
- `provisioning/dashboards/behemoth_jforex.json`
  - Existing JForex runtime dashboard.
  - Extend it with a certification row for readiness state, entries allowed, staleness, transitions/timeouts, and predict-path health.
- `Makefile`
  - Add a dedicated certification helper target, add it to `.PHONY`, and add a help entry.
  - Keep `jforex-live` unchanged; the helper target is for setup/observability only.
- `docs/monitoring.md`
  - Add the certification dashboard location, the new helper target, and the exact observation surfaces.
- `docs/strategy_bible/operator_runbook.md`
  - Add the certification checklist and pass/conditional-fail/fail interpretation for tomorrow's run.

## Task 1: Add Focused Asset Guards

**Files:**
- Create: `tests/test_jforex_demo_certification_assets.py`
- Read for context: `provisioning/dashboards/behemoth_jforex.json`
- Read for context: `Makefile`

- [ ] **Step 1: Write the failing dashboard coverage test**

```python
import json
from pathlib import Path


def test_jforex_dashboard_contains_demo_certification_panels() -> None:
    dashboard = json.loads(Path("provisioning/dashboards/behemoth_jforex.json").read_text(encoding="utf-8"))
    titles = {panel["title"] for panel in dashboard["panels"]}

    assert "JForex Symbol Readiness" in titles
    assert "JForex Entries Allowed" in titles
    assert "JForex Tick Staleness" in titles
    assert "JForex Predict Health" in titles
```

- [ ] **Step 2: Write the failing Makefile target/help test**

```python
from pathlib import Path


def test_makefile_exposes_demo_cert_monitor_target() -> None:
    makefile = Path("Makefile").read_text(encoding="utf-8")

    assert "demo-cert-monitor:" in makefile
    assert '"demo-cert-monitor"' in makefile
```

- [ ] **Step 3: Run the new focused tests to verify they fail**

Run: `uv run pytest -q tests/test_jforex_demo_certification_assets.py`

Expected: FAIL because the new certification panels and Make target do not exist yet.

- [ ] **Step 4: Commit the failing tests**

```bash
git add tests/test_jforex_demo_certification_assets.py
git commit -m "test: add dukascopy demo certification asset guards"
```

## Task 2: Extend The Provisioned JForex Dashboard

**Files:**
- Modify: `provisioning/dashboards/behemoth_jforex.json`
- Test: `tests/test_jforex_demo_certification_assets.py`

- [ ] **Step 1: Add a readiness state panel**

Use Prometheus query:

```json
{
  "expr": "behemoth_jforex_live_readiness_state",
  "legendFormat": "{{symbol}}"
}
```

Title:

```json
"title": "JForex Symbol Readiness"
```

- [ ] **Step 2: Add an entries-allowed panel**

Use Prometheus query:

```json
{
  "expr": "behemoth_jforex_live_entries_allowed",
  "legendFormat": "{{symbol}} entries"
}
```

Title:

```json
"title": "JForex Entries Allowed"
```

- [ ] **Step 3: Add a tick staleness panel with a visible 30s threshold**

Use Prometheus query:

```json
{
  "expr": "behemoth_jforex_live_tick_staleness_seconds",
  "legendFormat": "{{symbol}} stale"
}
```

Title:

```json
"title": "JForex Tick Staleness"
```

- [ ] **Step 4: Add readiness transition/timeout visibility**

Use Prometheus queries:

```json
{
  "expr": "sum by (symbol, from_state, to_state) (rate(behemoth_jforex_live_readiness_transitions_total[5m]))",
  "legendFormat": "{{symbol}} {{from_state}}→{{to_state}}"
}
```

```json
{
  "expr": "sum by (symbol) (rate(behemoth_jforex_live_readiness_timeouts_total[5m]))",
  "legendFormat": "{{symbol}} timeout"
}
```

Title:

```json
"title": "JForex Readiness Transitions"
```

- [ ] **Step 5: Add predict-path health visibility**

Use Prometheus queries:

```json
{
  "expr": "sum by (symbol) (rate(behemoth_jforex_predict_calls_total[5m]))",
  "legendFormat": "{{symbol}} predict"
}
```

```json
{
  "expr": "sum by (symbol) (rate(behemoth_jforex_predict_failures_total[5m]))",
  "legendFormat": "{{symbol}} failures"
}
```

```json
{
  "expr": "sum by (symbol) (rate(behemoth_jforex_predict_warmup_422_total[5m]))",
  "legendFormat": "{{symbol}} warmup422"
}
```

Title:

```json
"title": "JForex Predict Health"
```

- [ ] **Step 6: Run the focused asset tests**

Run: `uv run pytest -q tests/test_jforex_demo_certification_assets.py`

Expected: PASS

- [ ] **Step 7: Commit the dashboard changes**

```bash
git add provisioning/dashboards/behemoth_jforex.json tests/test_jforex_demo_certification_assets.py
git commit -m "feat: add dukascopy demo certification dashboard panels"
```

## Task 3: Add The Certification Helper Target

**Files:**
- Modify: `Makefile`
- Test: `tests/test_jforex_demo_certification_assets.py`

- [ ] **Step 1: Add the new target to `.PHONY`**

Append:

```make
demo-cert-monitor
```

to the long `.PHONY` line.

- [ ] **Step 2: Add the helper target next to `jforex-live`**

Create:

```make
demo-cert-monitor:
	@printf "[demo-cert] Grafana: http://127.0.0.1:3000/d/behemoth-jforex-runtime\n"
	@printf "[demo-cert] Prometheus: http://127.0.0.1:9090\n"
	@printf "[demo-cert] JForex metrics: http://127.0.0.1:9464/metrics\n"
	@printf "[demo-cert] Runtime readiness: data/analysis/backtest_reconcile/runtime/live_symbol_readiness.json\n"
	@printf "[demo-cert] Start monitoring with: make observability-up\n"
	@printf "[demo-cert] Start demo runner with: make jforex-live\n"
```

Do not wrap `jforex-live`; keep it as a separate start command.

- [ ] **Step 3: Add the help entry**

Add:

```make
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "demo-cert-monitor" "Print the Dukascopy demo certification monitoring URLs, metrics, and readiness file"
```

- [ ] **Step 4: Verify the helper target parses and help text is visible**

Run: `make --dry-run demo-cert-monitor`

Expected: shows the six `printf` commands with no parse errors.

Run: `make help | rg demo-cert-monitor`

Expected: one help line describing the new target.

- [ ] **Step 5: Re-run the focused asset tests**

Run: `uv run pytest -q tests/test_jforex_demo_certification_assets.py`

Expected: PASS

- [ ] **Step 6: Commit the Makefile changes**

```bash
git add Makefile tests/test_jforex_demo_certification_assets.py
git commit -m "build: add dukascopy demo certification helper target"
```

## Task 4: Update Operator Docs

**Files:**
- Modify: `docs/monitoring.md`
- Modify: `docs/strategy_bible/operator_runbook.md`

- [ ] **Step 1: Add the monitoring-stack/operator-view section**

Add concise text to `docs/monitoring.md` covering:

- the provisioned JForex dashboard UID/path
- `make observability-up`
- `make demo-cert-monitor`
- the runtime readiness JSON path
- the key certification signals: readiness, entries allowed, staleness, predict calls/failures

- [ ] **Step 2: Add the certification runbook checklist**

Add concise text to `docs/strategy_bible/operator_runbook.md` covering:

1. `make observability-up`
2. open Grafana
3. `make demo-cert-monitor`
4. `make jforex-live`
5. wait for all 6 symbols to reach `READY`
6. confirm staleness stays healthy
7. confirm predict activity for all 6 symbols once bars advance
8. inspect `runtime/live_symbol_readiness.json`
9. classify run as pass / conditional fail / fail

- [ ] **Step 3: Run docs-related checks**

Run: `uv run pytest -q tests/test_oco_docs_contract.py`

Expected: PASS

Run: `uv run mkdocs build`

Expected: succeeds

- [ ] **Step 4: Commit the docs updates**

```bash
git add docs/monitoring.md docs/strategy_bible/operator_runbook.md
git commit -m "docs: add dukascopy demo certification runbook"
```

## Task 5: Final Verification And Tomorrow's Manual Run Checklist

**Files:**
- Check: `Makefile`
- Check: `provisioning/dashboards/behemoth_jforex.json`
- Check: `docs/monitoring.md`
- Check: `docs/strategy_bible/operator_runbook.md`

- [ ] **Step 1: Run the focused certification asset tests**

Run: `uv run pytest -q tests/test_jforex_demo_certification_assets.py`

Expected: PASS

- [ ] **Step 2: Run the broader checks relevant to this change**

Run: `uv run pytest -q tests/test_api_server.py`

Expected: PASS

Run: `gradle :jforex-adapter:test`

Expected: `BUILD SUCCESSFUL`

Run: `uv run mkdocs build`

Expected: succeeds

- [ ] **Step 3: Verify the helper target output**

Run: `make demo-cert-monitor`

Expected:

- prints the Grafana URL
- prints the Prometheus URL
- prints the JForex metrics endpoint
- prints the runtime readiness JSON path
- reminds the operator to run `make observability-up` and `make jforex-live`

- [ ] **Step 4: Tomorrow's manual market-open certification**

Run:

```bash
make observability-up
make demo-cert-monitor
make jforex-live
```

Manual checks:

- all 6 symbols reach `READY`
- `behemoth_jforex_live_entries_allowed` is `1` for all 6 symbols
- `behemoth_jforex_live_tick_staleness_seconds` stays below `30`
- `behemoth_jforex_predict_calls_total` increases for all 6 symbols once bars advance
- no symbol remains `STALE_PAUSED` or `ERROR_PAUSED`
- `data/analysis/backtest_reconcile/runtime/live_symbol_readiness.json` updates during the session

- [ ] **Step 5: Record the operational outcome**

Capture:

- timestamp of run start
- time each symbol first reached `READY`
- any symbol that went stale or paused
- whether each symbol showed predict activity
- overall classification: pass / conditional fail / fail

- [ ] **Step 6: Final worktree check**

Run: `git status --short`

Expected: clean worktree before handoff
