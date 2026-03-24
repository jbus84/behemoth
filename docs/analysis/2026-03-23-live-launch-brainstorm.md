# Behemoth Live Session Launch — Analysis & Brainstorming

This document addresses the outstanding questions regarding capacity gate robustness, EURUSD bridging lag, and documentation contract integrity.

## 1. Capacity Gate Robustness — Brainstorming

The recent failure was caused by a "silent success" pattern where simulation scripts ran without errors but produced 0-row results because the tick data path was hardcoded to a legacy location.

### Proposed Robustness Enhancements

*   **Pre-flight Data Validation**: Add a mandatory check in `scripts/run_tick_opportunity_mining.py` and `scripts/analyze_oco_stop_limit_tickfill.py` that verifies the existence of parity-critical tick data in the `--tick-root` before execution.
*   **Fail-Fast on Zero Result**: If a simulation produces 0 trades or 0 capacity, the script should exit with a non-zero code and a clear error message (e.g., "No data found in tick root"), rather than allowing the governance pipeline to proceed with invalid "pass" states.
*   **CI Metadata Check**: Enhance `make docs-contract` (specifically `validate_oco_docs_contract.py`) to verify that the `capacity_overall_pass` was derived from a non-zero trade count.
*   **Registry-Level Constraints**: Store the expected tick data path in the `CandidateRegistry` (`configs/research/governance/oco_rule_universe_registry.yaml`) to ensure all scripts use a unified, validated source.

## 2. EURUSD BRIDGING Lag Analysis

EURUSD is currently in `BRIDGING` status and is catching up approximately 1 month of tick data (currently reading `2026/02/23`).

### Rationale & Solutions

*   **Why the lag?**: JForex needs to reconstruct the internal state (especially for technical indicators or features with long lookbacks) from the historical start point specified in the model config (`model_month: 2026-02`). 
*   **Persistent Cache**: Once JForex has downloaded and cached these `.bi5` files (under `~/Library/Application Support/JForex/.cache/`), subsequent restarts will be significantly faster as it will only need to read from disk.
*   **Acceleration**: To speed this up, we can pre-warm the JForex cache or ensure that the model lookback requirements are minimized. However, for a stable live session, allowing this one-time "catch-up" is the safest path to ensuring feature parity.

## 3. Docs Contract Failures (oco_docs_contract_report.md)

The current report shows several failures that should be addressed in the next maintenance cycle:

*   **C20 (Taxonomy Unclassified)**: High failure. Indicates that some signals or states in the mining results haven't been mapped to a known classification.
*   **C27 (Canonical Map Validity)**: Indicators/features used in the model are not fully mapped in the canonical feature catalog.
*   **C30 (Stage Integrity)**: Missing or "unclean" integrity checks in the intermediate data artifacts (e.g., duplicates or nan values in stage metrics).
*   **C36 (Recurrence Breach)**: A governance warning that a symbol has remained in a non-green state (like Amber) for more than the allowed cooldown period.

## 4. Logical Issues with Empty Schedules

The `audit_oco_pipeline_logical_issues.py` script currently fails with an `EmptyDataError` when a symbol has no qualifying states in its reduced core schedule. 

*   **Fix**: Wrap the pandas read in a try-except or check file size before reading, allowing the audit to report "Symbol has 0 active states" rather than crashing the pipeline.

---

**Next Steps**: 
- Monitor EURUSD until it reaches `READY`.
- Proceed with trade execution validation once the symbol is active.
