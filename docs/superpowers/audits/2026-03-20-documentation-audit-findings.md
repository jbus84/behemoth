# Documentation Audit Findings

## Audit Scope and Method

- Reviewed `275` in-scope rows across repo docs plus current governance/config surfaces recorded in `2026-03-20-documentation-audit-inventory.csv`.
- Used a flat exhaustive audit pass for inventory coverage.
- Used targeted content review on high-authority docs and corpus-wide structural checks for title/path consistency, navigation coverage, legacy labeling, and rendered-output quality.

## Severity Legend

- `high`: misleading enough to change operator or contributor understanding of the active system
- `medium`: materially reduces trust, discoverability, or correct interpretation
- `low`: readability or onboarding weakness that should be improved but is not likely to cause incorrect operational action on its own

## Findings

### F1. Top-level landing page still presents an outdated four-symbol primary set

- Severity: `high`
- Category: `accuracy`, `completeness`
- Affected files:
  - `docs/index.md`
- Evidence:
  - `docs/index.md` lists `Primary symbols: EURUSD, GBPUSD, USDJPY, USDCHF`
  - the active universe in `docs/STRATEGY_MASTER_MANUAL.md` includes `AUDUSD` and `USDCAD`
  - the “Latest Expected Gross” section on the same landing page also omits `AUDUSD` and `USDCAD`
- Impact:
  - new contributors get the wrong impression of the active production universe from the first page
  - operators lose a quick top-level summary for two active symbols
- Proposed fix direction:
  - update the landing page summary to the full six-symbol active universe
  - expand the expected-gross summary to all active symbols or explicitly label it as a subset and explain why

### F2. Fifteen symbol-specific monthly WFO reports have the wrong symbol in the document title

- Severity: `high`
- Category: `consistency`, `traceability`
- Affected files:
  - `docs/analysis/audusd_tick_opportunity_monthly_wfo_report.md`
  - `docs/analysis/audusd_tick_opportunity_monthly_wfo_oco_fullcap_report.md`
  - `docs/analysis/gbpusd_tick_opportunity_monthly_wfo_report.md`
  - `docs/analysis/gbpusd_tick_opportunity_monthly_wfo_oco_fullcap_report.md`
  - `docs/analysis/usdjpy_tick_opportunity_monthly_wfo_report.md`
  - `docs/analysis/usdjpy_tick_opportunity_monthly_wfo_oco_fullcap_report.md`
  - `docs/analysis/usdchf_tick_opportunity_monthly_wfo_report.md`
  - `docs/analysis/usdchf_tick_opportunity_monthly_wfo_oco_fullcap_report.md`
  - `docs/analysis/usdcad_tick_opportunity_monthly_wfo_report.md`
  - `docs/analysis/usdcad_tick_opportunity_monthly_wfo_oco_fullcap_report.md`
  - corresponding `docs/analysis/dukascopy_candidate/*monthly_wfo*report.md` files for `AUDUSD`, `GBPUSD`, `USDJPY`, `USDCHF`, and `USDCAD`
- Evidence:
  - these files are symbol-scoped by pathname but begin with the heading `# EURUSD Tick Opportunity Monthly WFO (3M->1M)`
- Impact:
  - symbol identity is unreliable at the point a reader lands on the page
  - the docs corpus looks template-copied rather than governed
  - report linking and review confidence degrade immediately
- Proposed fix direction:
  - fix the generator/template so the H1 derives from the target symbol
  - regenerate all affected reports rather than patching headings manually

### F3. Twenty-six TestClient parity reports still identify themselves as cTrader parity reports

- Severity: `medium`
- Category: `accuracy`, `authority`
- Affected files:
  - current and candidate TestClient parity reports under `docs/analysis/` and `docs/analysis/dukascopy_candidate/`
- Evidence:
  - multiple files named `*testclient_execution_parity_report.md` or `*dukascopy_testclient_execution_parity_report.md` open with `# cTrader Execution Parity`
  - HistData TestClient files open with `# HistData cTrader Execution Parity`
- Impact:
  - active Dukascopy/TestClient and JForex-facing work is framed with legacy cTrader wording
  - the report family does not clearly communicate what runtime or harness it is actually certifying
- Proposed fix direction:
  - rename report titles and generation labels to reflect `TestClient`, `Dukascopy TestClient`, or `historical API parity` precisely
  - reserve `cTrader` wording only for genuinely cTrader-specific reconciliation docs

### F4. The deployment page publishes generated tables that render as empty shells

- Severity: `medium`
- Category: `actionability`, `trust`
- Affected files:
  - `docs/deployment.md`
- Evidence:
  - the generated “Rolling Snapshot By Symbol” table has blank values for all symbols
  - the “Rolling Trend (Last 3 Months)” table shows `months_used = 0` for every active symbol
- Impact:
  - the page looks broken even though it is presented as current deployment guidance
  - readers cannot tell whether the issue is “no data”, “stale generation”, or “template failure”
- Proposed fix direction:
  - either suppress empty sections entirely or render an explicit “data unavailable / not refreshed” state
  - add a short interpretation note when generated sections have no usable values

### F5. The analysis catalog exposes legacy/candidate-style reports as active symbol docs while claiming legacy reports are empty

- Severity: `medium`
- Category: `navigation`, `audience_fit`
- Affected files:
  - `docs/analysis/index.md`
- Evidence:
  - the symbol sections include `Ctrader`, `Histdata`, and reconciliation documents without legacy or compatibility labeling
  - the same page ends with `Legacy Reports _empty_`
- Impact:
  - new contributors cannot tell which reports are core to the active OCO/JForex direction and which are compatibility or forensic surfaces
  - the catalog buries current-core reports in a mixed list of active and legacy-adjacent material
- Proposed fix direction:
  - split the catalog into `Core`, `Compatibility / Legacy`, `Candidate`, and `Archive` sections
  - stop describing legacy reports as empty while legacy-style reports remain surfaced in active symbol sections

### F6. FTMO and cBot material is still presented too close to active runtime documentation

- Severity: `medium`
- Category: `authority`, `staleness`
- Affected files:
  - `docs/analysis/ftmo_risk_compliance_report.md`
  - `docs/deployment.md`
  - `docs/strategy_bible/generated/stage_10_snapshot.md`
- Evidence:
  - `docs/analysis/ftmo_risk_compliance_report.md` describes an “Active Runtime Profile” and a `cBot Integration` section
  - `docs/deployment.md` still includes FTMO allocator/reconciliation sources in its generated evidence block
  - Stage 10 generated output surfaces FTMO allocator metrics without strong legacy framing
- Impact:
  - contributors can misread FTMO/cBot surfaces as part of the primary runtime path
  - active-vs-legacy boundaries stay blurred even though the repo guidance treats JForex as the active broker-adapter target
- Proposed fix direction:
  - add explicit compatibility-only / legacy framing wherever FTMO or cBot material still appears
  - consider moving these docs into a dedicated compatibility section if they remain useful

### F7. The walkthrough is too thin to function as meaningful onboarding

- Severity: `low`
- Category: `audience_fit`, `actionability`
- Affected files:
  - `docs/walkthrough.md`
- Evidence:
  - the page is only a short transition note away from the deprecated stat-arb system
  - it does not explain the repo entry order, the main runtime split, or the recommended next documents for a contributor
- Impact:
  - the file name implies architecture/onboarding value that the content does not deliver
- Proposed fix direction:
  - either expand it into a real onboarding walkthrough or replace it with a redirect-style page that points clearly to the manual, operator runbook, and strategy bible
