# Doc-First Documentation Update Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the highest-priority documentation issues from the audit by rewriting the key manual docs, correcting generator-driven report titles, and regenerating only the affected report families.

**Architecture:** This batch combines direct markdown rewrites for the main entrypoint and operator-facing docs with targeted generator/template fixes for derived report families. The implementation updates the manual docs first, patches the title emitters second, then regenerates and verifies the affected reports.

**Tech Stack:** Markdown, Python report builders, `rg`, `sed`, `uv run`, repo docs under `docs/`, generator/report scripts under `scripts/`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `docs/index.md` | **MODIFY** | Correct active-universe and top-level summary framing |
| `docs/deployment.md` | **MODIFY** | Clarify empty generated sections and deployment interpretation |
| `docs/analysis/index.md` | **MODIFY** | Reclassify core versus compatibility/legacy-facing reports |
| `docs/walkthrough.md` | **MODIFY** | Provide meaningful onboarding flow and doc entry order |
| `docs/analysis/ftmo_risk_compliance_report.md` | **MODIFY** | Add compatibility/legacy framing to FTMO and cBot material |
| `scripts/...` report generator path for monthly WFO docs | **MODIFY** | Correct symbol-derived H1 generation |
| `scripts/...` report generator path for TestClient parity docs | **MODIFY** | Correct runtime/harness-derived H1 generation |
| affected generated WFO report files | **REGENERATE** | Refresh titles after generator fix |
| affected generated TestClient parity report files | **REGENERATE** | Refresh titles after generator fix |

### Task 1: Locate the Generator Paths and Confirm Regeneration Commands

**Files:**
- Read: `scripts/`
- Read: existing affected generated reports

- [ ] **Step 1: Find the code path that emits monthly WFO report titles**

Run: `rg -n "Tick Opportunity Monthly WFO|3M->1M" scripts`
Expected: identify the script or helper that builds monthly WFO report markdown

- [ ] **Step 2: Find the code path that emits TestClient parity report titles**

Run: `rg -n "cTrader Execution Parity|TestClient Execution Parity|HistData cTrader Execution Parity" scripts`
Expected: identify the script or helper that builds parity report markdown

- [ ] **Step 3: Confirm how to regenerate only the affected report families**

Expected: concrete commands for the WFO reports and the TestClient parity reports, without requiring a full docs rebuild first

- [ ] **Step 4: Stop and surface any blocker if regeneration needs unavailable upstream artifacts**

Expected: either proceed with local regeneration or report the exact missing dependency

### Task 2: Update `docs/index.md`

**Files:**
- Modify: `docs/index.md`

- [ ] **Step 1: Rewrite the active-system summary**

Required changes:
- present the active six-symbol universe
- keep the current strategy description aligned with the strategy manual
- preserve the doc’s role as the top-level landing page

- [ ] **Step 2: Rewrite the expected-gross summary**

Required changes:
- either include all active symbols or explicitly explain any intentional subset
- avoid a silent four-symbol presentation

- [ ] **Step 3: Verify the page still points readers to the right authorities**

Expected: manual, strategy bible, generated snapshot, and operator runbook references remain clear

### Task 3: Update `docs/deployment.md`

**Files:**
- Modify: `docs/deployment.md`

- [ ] **Step 1: Inspect how the current generated empty sections are presented**

Expected: identify where blank cells and `months_used = 0` are currently exposed without explanation

- [ ] **Step 2: Rewrite the surrounding prose or section framing**

Required change:
- clearly state when generated deployment summary sections do not yet contain usable values
- prevent the page from reading like valid populated deployment evidence when it is empty

- [ ] **Step 3: Preserve the page’s deployment checklist utility**

Expected: promotion checklist and runtime framing remain usable after the rewrite

### Task 4: Update `docs/analysis/index.md`

**Files:**
- Modify: `docs/analysis/index.md`

- [ ] **Step 1: Reorganize report groups for clarity**

Required direction:
- keep core active OCO/JForex-governance reports easy to find
- separate compatibility/legacy-style items from current-core materials

- [ ] **Step 2: Fix the false “Legacy Reports _empty_” posture**

Expected: the catalog no longer claims legacy is empty while surfacing cTrader/HistData-style items in active symbol sections

- [ ] **Step 3: Keep links intact**

Expected: existing linked report paths remain valid after the reorganization

### Task 5: Update `docs/walkthrough.md`

**Files:**
- Modify: `docs/walkthrough.md`

- [ ] **Step 1: Expand the file into a real onboarding bridge**

Required content:
- what system is active
- how the Python and JForex surfaces relate
- where a contributor should start reading

- [ ] **Step 2: Add a concise recommended reading order**

Expected:
- strategy manual
- strategy bible
- generated snapshot
- operator runbook / analysis catalog as appropriate

- [ ] **Step 3: Keep it concise**

Expected: the page becomes useful without turning into a second copy of the strategy manual

### Task 6: Update `docs/analysis/ftmo_risk_compliance_report.md`

**Files:**
- Modify: `docs/analysis/ftmo_risk_compliance_report.md`

- [ ] **Step 1: Add compatibility framing at the top of the page**

Required change:
- clearly state FTMO/cBot material is compatibility- or legacy-adjacent rather than the primary active runtime path

- [ ] **Step 2: Adjust wording that currently reads as central active runtime guidance**

Expected: “active profile” and cBot integration references are contextualized appropriately

- [ ] **Step 3: Preserve the document’s remaining diagnostic value**

Expected: readers can still understand the FTMO guardrail surface if they need it

### Task 7: Patch the Monthly WFO Report Title Generator

**Files:**
- Modify: exact generator/helper file identified in Task 1
- Regenerate: affected `docs/analysis/*tick_opportunity_monthly_wfo*report.md`
- Regenerate: affected `docs/analysis/dukascopy_candidate/*tick_opportunity_monthly_wfo*report.md`

- [ ] **Step 1: Write the minimal generator change**

Required behavior:
- derive the H1 symbol from the actual report target rather than a hardcoded or leaked default

- [ ] **Step 2: Regenerate the affected WFO reports**

Expected: non-EURUSD files no longer open with `# EURUSD Tick Opportunity Monthly WFO (3M->1M)`

- [ ] **Step 3: Spot-check multiple symbols**

Check at least:
- one current active non-EURUSD WFO report
- one current active non-EURUSD fullcap WFO report
- one candidate non-EURUSD WFO report

### Task 8: Patch the TestClient Parity Report Title Generator

**Files:**
- Modify: exact generator/helper file identified in Task 1
- Regenerate: affected `docs/analysis/*testclient_execution_parity_report.md`
- Regenerate: affected `docs/analysis/dukascopy_candidate/*testclient_execution_parity_report.md`

- [ ] **Step 1: Write the minimal generator change**

Required behavior:
- use a title that matches the actual runtime or harness described by the report
- stop defaulting to `cTrader Execution Parity` when that label is inaccurate

- [ ] **Step 2: Regenerate the affected parity reports**

Expected: incorrect generic `cTrader Execution Parity` headings disappear from the affected TestClient report family

- [ ] **Step 3: Spot-check multiple parity variants**

Check at least:
- one Dukascopy TestClient report
- one HistData TestClient report
- one candidate TestClient report

### Task 9: Verification

**Files:**
- Read: all modified manual docs
- Read: selected regenerated reports

- [ ] **Step 1: Run targeted docs-contract verification**

Run: `uv run pytest -q tests/test_oco_docs_contract.py`
Expected: passing result

- [ ] **Step 2: Re-run targeted text checks for resolved findings**

Examples:
- `rg -n "Primary symbols" docs/index.md`
- `rg -n "^# EURUSD Tick Opportunity Monthly WFO" docs/analysis docs/analysis/dukascopy_candidate`
- `rg -n "^# cTrader Execution Parity|^# HistData cTrader Execution Parity" docs/analysis docs/analysis/dukascopy_candidate`

Expected:
- landing page no longer shows the stale four-symbol framing
- non-EURUSD WFO reports no longer carry EURUSD H1 titles
- affected TestClient reports no longer use incorrect cTrader H1 labels

- [ ] **Step 3: Sanity-read the rewritten manual docs**

Expected: the updated docs read coherently and reflect the agreed design

- [ ] **Step 4: Commit**

```bash
git add docs/index.md \
        docs/deployment.md \
        docs/analysis/index.md \
        docs/walkthrough.md \
        docs/analysis/ftmo_risk_compliance_report.md \
        docs/superpowers/specs/2026-03-20-doc-first-docs-update-design.md \
        docs/superpowers/plans/2026-03-20-doc-first-docs-update.md
git add <generator files> <regenerated report files>
git commit -m "docs: fix high-priority documentation and report labels"
```
