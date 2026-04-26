# Ubiquitous Language Propagation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Propagate the approved ubiquitous language across the active OCO docs and operator-facing text so governance/live terminology is consistent without changing runtime semantics.

**Architecture:** Treat this as a layered docs refactor, not a global search-and-replace. Update the glossary and master manual first, then normalize operator and certification docs, then run a selective long-tail cleanup driven by grep. Verify with `mkdocs build`, grep audits, and a final diff review.

**Tech Stack:** Markdown docs, repo docs under `docs/`, operator-facing Python script/help text under `scripts/`, `rg`, `git`, `uv run mkdocs build`

---

## File Structure

- Modify: `UBIQUITOUS_LANGUAGE.md`
  - Canonical glossary for governance/live/process/research terminology.
- Modify: `docs/STRATEGY_MASTER_MANUAL.md`
  - Canonical prose synthesis for the active OCO system.
- Modify: `docs/strategy_bible/stage_02_opportunity_mining.md`
  - Stage-2 naming for mining versus later fitting/selection.
- Modify: `docs/strategy_bible/stage_03_monthly_wfo.md`
  - Stage-3 naming for monthly WFO, model fit, threshold fit, and month semantics.
- Modify: `docs/strategy_bible/stage_05_reduced_core.md`
  - Stage-5 naming for shortlist versus allowed states.
- Modify: `docs/strategy_bible/stage_12_api_parity.md`
  - Stage-12 certification semantics.
- Modify: `docs/strategy_bible/stage_13_dukascopy_testclient_parity.md`
  - Stage-13 certification semantics and live/governance parity wording.
- Modify: `docs/strategy_bible/operator_runbook.md`
  - Operator-facing use of promotion, deployment period, and runtime terms.
- Modify: `docs/analysis/operator_action_report.md`
  - High-signal operator report for FAIL versus NO_GO semantics.
- Modify: `docs/analysis/stage13_dukascopy_testclient_report.md`
  - Active certification summary wording.
- Modify: `docs/analysis/stage14_jforex_runtime_certification_report.md`
  - Active certification summary wording.
- Modify: `docs/analysis/live_demo_vs_offline_comparison_20260417.md`
  - Replace “offline” shorthand with governance/runtime parity language where appropriate.
- Modify: `docs/deployment.md`
  - Clarify governance runtime, live runtime, promotion, and restart wording.
- Modify: `docs/validation.md`
  - Align validation/certification wording with glossary.
- Modify: `scripts/validate_stage14_jforex_runtime_certification.py`
  - Normalize operator-facing aliases/comments/help text around `NO_GO` where safe.
- Modify: `scripts/run_monthly_recert.py`
  - Normalize printed operator wording if it still uses `NOGO`/ambiguous phrasing.

## Task 1: Audit and Lock the Canonical Vocabulary

**Files:**
- Modify: `UBIQUITOUS_LANGUAGE.md`
- Modify: `docs/STRATEGY_MASTER_MANUAL.md`

- [ ] **Step 1: Audit canonical term usage before editing**

Run:

```bash
rtk rg -n "Governance Runtime|Live Runtime|Monthly Recert|Deployment Period|NO_GO|NOGO|NO-GO|semantic parity|Runtime Variance|Material Drift|Parity Breach|training" UBIQUITOUS_LANGUAGE.md docs/STRATEGY_MASTER_MANUAL.md
```

Expected:

- glossary already contains the approved vocabulary
- master manual still contains older phrasing such as broad `training`, plain `promotion`, and no explicit governance/live runtime pairing

- [ ] **Step 2: Update the master manual to anchor the new vocabulary**

Edit `docs/STRATEGY_MASTER_MANUAL.md` so the orientation and stage sections explicitly define:

```md
- the active system as a **Governance Runtime** plus **Live Runtime** pair
- `Promotion` as approval of the certified artifact/lock set
- `Monthly Recert` as the official promotion-gating certification run
- `Deployment Period` as the governed period the promoted artifacts apply to
- research/fitting versus hardening versus certification versus promotion
- semantic parity rather than exact trade matching
```

Also normalize obvious wording such as:

```md
- "monthly walk-forward selection + thresholding" -> "Monthly WFO fitting, scoring, and thresholding"
- "reduced-core selection" -> "Reduced-Core Rolling selection"
- "promotion" references that really mean deployability gating
```

- [ ] **Step 3: Review the canonical diff for semantic precision**

Run:

```bash
git diff -- UBIQUITOUS_LANGUAGE.md docs/STRATEGY_MASTER_MANUAL.md
```

Expected:

- wording changes only
- no accidental changes to numerical thresholds, artifact paths, or stage ordering

- [ ] **Step 4: Commit the canonical vocabulary pass**

```bash
git add UBIQUITOUS_LANGUAGE.md docs/STRATEGY_MASTER_MANUAL.md
git commit -m "docs: anchor ubiquitous language in glossary and manual"
```

## Task 2: Normalize Stage and Operator Semantics

**Files:**
- Modify: `docs/strategy_bible/stage_02_opportunity_mining.md`
- Modify: `docs/strategy_bible/stage_03_monthly_wfo.md`
- Modify: `docs/strategy_bible/stage_05_reduced_core.md`
- Modify: `docs/strategy_bible/stage_12_api_parity.md`
- Modify: `docs/strategy_bible/stage_13_dukascopy_testclient_parity.md`
- Modify: `docs/strategy_bible/operator_runbook.md`
- Modify: `docs/analysis/operator_action_report.md`
- Modify: `docs/analysis/stage13_dukascopy_testclient_report.md`
- Modify: `docs/analysis/stage14_jforex_runtime_certification_report.md`

- [ ] **Step 1: Audit the main stage/operator docs for overloaded terminology**

Run:

```bash
rtk rg -n "training|failed symbol|failed|NOGO|NO-GO|no-go|month|monthly run|match|matching|offline|promoted system|green month" \
  docs/strategy_bible/stage_02_opportunity_mining.md \
  docs/strategy_bible/stage_03_monthly_wfo.md \
  docs/strategy_bible/stage_05_reduced_core.md \
  docs/strategy_bible/stage_12_api_parity.md \
  docs/strategy_bible/stage_13_dukascopy_testclient_parity.md \
  docs/strategy_bible/operator_runbook.md \
  docs/analysis/operator_action_report.md \
  docs/analysis/stage13_dukascopy_testclient_report.md \
  docs/analysis/stage14_jforex_runtime_certification_report.md
```

Expected:

- Stage 2/3 docs contain broad `training` references
- operator and stage reports contain mixed `NO-GO`, `NOGO`, `fail`, and exact-match phrasing

- [ ] **Step 2: Update the research-stage docs with precise stage vocabulary**

Edit:

- `docs/strategy_bible/stage_02_opportunity_mining.md`
- `docs/strategy_bible/stage_03_monthly_wfo.md`
- `docs/strategy_bible/stage_05_reduced_core.md`

Apply this mapping:

```md
- Stage 2 -> **Opportunity Mining**
- Stage 3 -> **Monthly WFO**, **Model Fit**, **Threshold Fit**
- Stage 5 -> **Reduced-Core Rolling**, **Shortlist**, **Allowed State**
- use `Deployment Period` only when the text means governed deployment scope
- keep literal train/test month wording when discussing WFO chronology
```

- [ ] **Step 3: Update certification/operator docs with FAIL vs NO_GO and parity wording**

Edit:

- `docs/strategy_bible/stage_12_api_parity.md`
- `docs/strategy_bible/stage_13_dukascopy_testclient_parity.md`
- `docs/strategy_bible/operator_runbook.md`
- `docs/analysis/operator_action_report.md`
- `docs/analysis/stage13_dukascopy_testclient_report.md`
- `docs/analysis/stage14_jforex_runtime_certification_report.md`

Apply this mapping:

```md
- process invalidity -> `FAIL`
- symbol non-deployment -> `NO_GO`
- acceptable live/runtime differences -> `Runtime Variance`
- out-of-contract differences -> `Material Drift` or `Parity Breach`
- "match/matching" -> "semantic parity" where exact equality is not intended
```

- [ ] **Step 4: Review the stage/operator diff**

Run:

```bash
git diff -- \
  docs/strategy_bible/stage_02_opportunity_mining.md \
  docs/strategy_bible/stage_03_monthly_wfo.md \
  docs/strategy_bible/stage_05_reduced_core.md \
  docs/strategy_bible/stage_12_api_parity.md \
  docs/strategy_bible/stage_13_dukascopy_testclient_parity.md \
  docs/strategy_bible/operator_runbook.md \
  docs/analysis/operator_action_report.md \
  docs/analysis/stage13_dukascopy_testclient_report.md \
  docs/analysis/stage14_jforex_runtime_certification_report.md
```

Expected:

- active docs read consistently with the glossary
- no metrics, paths, or report meanings are altered

- [ ] **Step 5: Commit the stage/operator pass**

```bash
git add \
  docs/strategy_bible/stage_02_opportunity_mining.md \
  docs/strategy_bible/stage_03_monthly_wfo.md \
  docs/strategy_bible/stage_05_reduced_core.md \
  docs/strategy_bible/stage_12_api_parity.md \
  docs/strategy_bible/stage_13_dukascopy_testclient_parity.md \
  docs/strategy_bible/operator_runbook.md \
  docs/analysis/operator_action_report.md \
  docs/analysis/stage13_dukascopy_testclient_report.md \
  docs/analysis/stage14_jforex_runtime_certification_report.md
git commit -m "docs: normalize stage and operator terminology"
```

## Task 3: Broader Sweep Across Current Docs and Operator Text

**Files:**
- Modify: `docs/deployment.md`
- Modify: `docs/validation.md`
- Modify: `docs/analysis/live_demo_vs_offline_comparison_20260417.md`
- Modify: `scripts/validate_stage14_jforex_runtime_certification.py`
- Modify: `scripts/run_monthly_recert.py`

- [ ] **Step 1: Audit the broader current-use surfaces**

Run:

```bash
rtk rg -n "offline|NOGO|NO-GO|no-go|matching|match the|green month|monthly run|promoted system|clean_resumable|reconcilable|incompatible" \
  docs/deployment.md \
  docs/validation.md \
  docs/analysis/live_demo_vs_offline_comparison_20260417.md \
  scripts/validate_stage14_jforex_runtime_certification.py \
  scripts/run_monthly_recert.py
```

Expected:

- `live_demo_vs_offline_comparison_20260417.md` still uses `offline`
- scripts may still accept old aliases or print legacy `NOGO` wording

- [ ] **Step 2: Update docs to use governance/live runtime language**

Edit:

- `docs/deployment.md`
- `docs/validation.md`
- `docs/analysis/live_demo_vs_offline_comparison_20260417.md`

Make these semantic replacements where accurate:

```md
- "offline" -> **Governance Runtime** when contrasting with live
- "live should match" -> **semantic parity**
- "monthly run" -> **Monthly Recert** when it means the promotion-gating certification run
- "month" -> **Deployment Period** when it means the governed deployment scope
```

- [ ] **Step 3: Normalize operator-facing script text without changing behavior**

Edit:

- `scripts/validate_stage14_jforex_runtime_certification.py`
- `scripts/run_monthly_recert.py`

Scope:

```python
# Safe changes only:
# - normalize comments/help text/operator output toward NO_GO
# - keep backward-compatible input aliases such as "no-go" or "nogo" if already accepted
# - do not change verdict logic, parser semantics, or generated report schema
```

- [ ] **Step 4: Run targeted verification for the broader sweep**

Run:

```bash
rtk rg -n "NOGO|NO-GO|green month|clean_resumable|reconcilable|incompatible" docs scripts
```

Expected:

- remaining hits are either historical/intentional or backward-compatible parser aliases
- no current operator doc should rely on the old wording as its primary term

- [ ] **Step 5: Commit the broader sweep**

```bash
git add \
  docs/deployment.md \
  docs/validation.md \
  docs/analysis/live_demo_vs_offline_comparison_20260417.md \
  scripts/validate_stage14_jforex_runtime_certification.py \
  scripts/run_monthly_recert.py
git commit -m "docs: propagate runtime and parity terminology"
```

## Task 4: Long-Tail Cleanup and Final Verification

**Files:**
- Modify: any additional `docs/*.md` or `docs/analysis/*.md` files discovered by grep that are clearly current-use and semantically wrong

- [ ] **Step 1: Run the final long-tail grep audit**

Run:

```bash
rtk rg -n "NOGO|NO-GO|no-go|offline|match(es|ing)? live|live.*match|green month|monthly run" docs
```

Expected:

- a shorter list of remaining hits
- many hits will be historical specs or generated/archival evidence and should be left alone unless they actively mislead current work

- [ ] **Step 2: Apply selective cleanup only where the wording is clearly current and wrong**

Edit only files that meet all of these conditions:

```text
1. current-use rather than archival
2. operator- or governance-relevant
3. unambiguously improved by the canonical glossary
```

Do not rewrite:

```text
- archival reports where the wording is part of the historical record
- generated evidence where editorial cleanup would blur provenance
- old specs unless the old term still misleads current readers
```

- [ ] **Step 3: Run final repo checks**

Run:

```bash
git diff --check
uv run mkdocs build
rtk rg -n "Governance Runtime|Live Runtime|Monthly Recert|Deployment Period|Runtime Variance|Material Drift|Parity Breach" \
  UBIQUITOUS_LANGUAGE.md docs/STRATEGY_MASTER_MANUAL.md docs/strategy_bible docs/deployment.md docs/validation.md docs/analysis
```

Expected:

- `git diff --check` passes
- `mkdocs build` passes
- canonical terms appear in the main current-use docs

- [ ] **Step 4: Review the final diff for scope discipline**

Run:

```bash
git diff --stat main...HEAD
git diff -- main...HEAD
```

Expected:

- docs and safe operator-text changes only
- no runtime behavior changes
- no noisy edits to unrelated historical material

- [ ] **Step 5: Commit the final cleanup**

```bash
git add docs scripts UBIQUITOUS_LANGUAGE.md
git commit -m "docs: finish ubiquitous language propagation sweep"
```
