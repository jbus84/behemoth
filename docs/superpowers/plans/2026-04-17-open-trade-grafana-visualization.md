# Open Trade Grafana Visualization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the JForex Grafana open-trade section easier to interpret by turning the current merged heatmap table into a wider timeline table with a clear expiry-progress cue.

**Architecture:** Keep the existing Prometheus metrics and instant queries, and change only the Grafana JSON. Add test coverage that locks in the intended table structure, then update the `Open Positions` panel to compute expiry progress from elapsed and remaining bars using Grafana transformations and render that progress as a gauge-style cell instead of coloring every numeric column.

**Tech Stack:** Grafana dashboard JSON provisioning, Prometheus instant queries, pytest, Python `json`

**Target branch:** `fix/open-trade-grafana-viz`  
**Target commit:** `26b73e316db7340e9f33f051c3d1cc1b7ba9afdc`  
**Worktree:** `/Users/danielfisher/repositories/behemoth/.worktrees/open-trade-grafana-viz`

---

## File Structure

- `provisioning/dashboards/behemoth_jforex.json`
  - Modify the `Open Positions` table panel and adjacent layout widths.
- `tests/test_jforex_demo_certification_assets.py`
  - Extend the existing dashboard asset test file with assertions covering the redesigned open-trade table.

### Task 1: Lock In The New Open-Trade Table Contract

**Files:**
- Modify: `tests/test_jforex_demo_certification_assets.py`
- Read for context: `provisioning/dashboards/behemoth_jforex.json`

- [ ] **Step 1: Write the failing dashboard asset test**

Add a new test below `test_jforex_dashboard_contains_demo_certification_panels()`:

```python
def test_open_positions_panel_uses_timeline_table_layout() -> None:
    dashboard_path = Path("provisioning/dashboards/behemoth_jforex.json")
    dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
    panels_by_title = {panel["title"]: panel for panel in dashboard["panels"]}

    open_positions = panels_by_title["Open Positions"]
    assert open_positions["type"] == "table"
    assert open_positions["gridPos"]["w"] >= 10
    assert open_positions["options"]["sortBy"] == [{"displayName": "Bars remaining", "desc": False}]

    targets = {target["refId"]: target for target in open_positions["targets"]}
    assert targets["A"]["expr"] == "behemoth_open_position_age_bars > 0"
    assert targets["B"]["expr"] == "behemoth_open_position_bars_remaining > 0"
    assert targets["C"]["expr"] == "behemoth_open_position_age_seconds / 60 > 0"
    assert all(target["instant"] is True for target in targets.values())

    transformations = open_positions["transformations"]
    add_total = transformations[1]
    add_progress = transformations[2]
    organize = transformations[3]

    assert add_total["id"] == "calculateField"
    assert add_total["options"]["alias"] == "Lifecycle total"
    assert add_progress["id"] == "calculateField"
    assert add_progress["options"]["alias"] == "Progress to expiry"

    rename_map = organize["options"]["renameByName"]
    assert rename_map["Value #B"] == "Bars remaining"
    assert rename_map["Value #C"] == "Age (min)"

    overrides = {
        override["matcher"]["options"]: override["properties"]
        for override in open_positions["fieldConfig"]["overrides"]
    }
    progress_props = {prop["id"]: prop["value"] for prop in overrides["Progress to expiry"]}
    remaining_props = {prop["id"]: prop["value"] for prop in overrides["Bars remaining"]}
    age_props = {prop["id"]: prop["value"] for prop in overrides["Age (min)"]}

    assert progress_props["custom.cellOptions"]["type"] == "gauge"
    assert progress_props["unit"] == "percent"
    assert remaining_props["custom.cellOptions"]["type"] == "auto"
    assert age_props["custom.cellOptions"]["type"] == "auto"
```

- [ ] **Step 2: Run the targeted test and verify it fails**

Run:

```bash
uv run pytest -q tests/test_jforex_demo_certification_assets.py::test_open_positions_panel_uses_timeline_table_layout
```

Expected: `FAIL` because the current panel width is `8`, it does not yet define calculated lifecycle/progress fields, and the current table still uses background-colored numeric cells.

- [ ] **Step 3: Commit the failing test**

Run:

```bash
git add tests/test_jforex_demo_certification_assets.py
git commit -m "test: lock open positions grafana table contract"
```

### Task 2: Redesign The Grafana Panel To Match The New Contract

**Files:**
- Modify: `provisioning/dashboards/behemoth_jforex.json:928-1189`
- Test: `tests/test_jforex_demo_certification_assets.py`

- [ ] **Step 1: Update the `Open Positions` panel layout and field presentation**

In the panel titled `Open Positions`, make these structural changes:

```json
{
  "gridPos": {
    "h": 8,
    "w": 12,
    "x": 12,
    "y": 40
  },
  "fieldConfig": {
    "defaults": {
      "custom": {
        "align": "center",
        "cellOptions": {
          "type": "auto"
        },
        "inspect": false
      }
    }
  }
}
```

Apply these override rules:

```json
[
  {
    "matcher": { "id": "byName", "options": "Bars remaining" },
    "properties": [
      { "id": "custom.width", "value": 110 },
      { "id": "unit", "value": "short" },
      { "id": "decimals", "value": 0 },
      { "id": "custom.cellOptions", "value": { "type": "auto" } }
    ]
  },
  {
    "matcher": { "id": "byName", "options": "Age (min)" },
    "properties": [
      { "id": "custom.width", "value": 90 },
      { "id": "unit", "value": "short" },
      { "id": "decimals", "value": 1 },
      { "id": "custom.cellOptions", "value": { "type": "auto" } }
    ]
  },
  {
    "matcher": { "id": "byName", "options": "Progress to expiry" },
    "properties": [
      { "id": "custom.width", "value": 220 },
      { "id": "unit", "value": "percent" },
      { "id": "min", "value": 0 },
      { "id": "max", "value": 100 },
      { "id": "custom.cellOptions", "value": { "type": "gauge", "mode": "basic" } },
      {
        "id": "thresholds",
        "value": {
          "mode": "absolute",
          "steps": [
            { "color": "green", "value": null },
            { "color": "yellow", "value": 60 },
            { "color": "red", "value": 85 }
          ]
        }
      }
    ]
  }
]
```

Also shrink the adjacent panel titled `Estimated Unrealized Pips by Symbol` so the row still fits a 24-column Grafana grid:

```json
{
  "gridPos": {
    "h": 8,
    "w": 8,
    "x": 4,
    "y": 40
  }
}
```

- [ ] **Step 2: Add the row calculations that derive expiry progress**

Insert two Grafana field-calculation transformations between the existing `merge` and final `organize` transformation:

```json
[
  {
    "id": "merge",
    "options": {}
  },
  {
    "id": "calculateField",
    "options": {
      "mode": "binary",
      "binary": {
        "left": "Value #A",
        "operator": "+",
        "right": "Value #B"
      },
      "alias": "Lifecycle total",
      "replaceFields": false
    }
  },
  {
    "id": "calculateField",
    "options": {
      "mode": "binary",
      "binary": {
        "left": "Value #A",
        "operator": "/",
        "right": "Lifecycle total"
      },
      "alias": "Progress to expiry"
    }
  },
  {
    "id": "organize",
    "options": {
      "renameByName": {
        "Value #A": "Bars elapsed",
        "Value #B": "Bars remaining",
        "Value #C": "Age (min)",
        "Progress to expiry": "Progress to expiry",
        "symbol": "Symbol"
      },
      "excludeByName": {
        "Time": true,
        "__name__": true,
        "instance": true,
        "job": true,
        "Lifecycle total": true
      },
      "indexByName": {
        "symbol": 0,
        "Value #B": 1,
        "Value #C": 2,
        "Progress to expiry": 3
      }
    }
  }
]
```

Keep the existing Prometheus target expressions unchanged and preserve the default ascending sort on `Bars remaining`.

- [ ] **Step 3: Run the targeted dashboard asset test**

Run:

```bash
uv run pytest -q tests/test_jforex_demo_certification_assets.py::test_open_positions_panel_uses_timeline_table_layout
```

Expected: `PASS`

- [ ] **Step 4: Validate the full dashboard asset test file**

Run:

```bash
uv run pytest -q tests/test_jforex_demo_certification_assets.py
```

Expected: `3 passed`

- [ ] **Step 5: Validate the dashboard JSON parses**

Run:

```bash
python3 - <<'PY'
import json
from pathlib import Path

dashboard = Path("provisioning/dashboards/behemoth_jforex.json")
json.loads(dashboard.read_text(encoding="utf-8"))
print("JSON valid")
PY
```

Expected: `JSON valid`

- [ ] **Step 6: Commit the dashboard update**

Run:

```bash
git add provisioning/dashboards/behemoth_jforex.json tests/test_jforex_demo_certification_assets.py
git commit -m "feat: improve open positions grafana readability"
```

### Task 3: Perform Final Visual Verification In Grafana

**Files:**
- Read: `provisioning/dashboards/behemoth_jforex.json`
- Read: `docs/monitoring.md`

- [ ] **Step 1: Start or reuse the observability stack**

Run:

```bash
docker compose up -d prometheus grafana
```

Expected: containers are running or already up-to-date.

- [ ] **Step 2: Inspect the provisioned dashboard in Grafana**

Open:

```text
http://127.0.0.1:3000/d/behemoth-jforex-runtime/behemoth-jforex-runtime?orgId=1
```

Verify:

- `Open Positions (total)` still renders
- `Open Positions` shows `Symbol`, `Bars remaining`, `Age (min)`, and `Progress to expiry`
- the most urgent trade appears first
- the progress column reads as a clear urgency/timeline cue without truncation

- [ ] **Step 3: Capture final status and commit if visual tweaks were required**

If no additional changes were needed, run:

```bash
git status --short
```

Expected: clean worktree.

If a visual tweak was required after review, repeat Task 2’s verification commands and make a follow-up commit describing the specific layout adjustment.
