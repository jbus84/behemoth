"""Declarative stage-contract manifest for tick-opportunity governance pipeline.

Single source of truth for:
- family↔library↔artifact-name mapping
- quality-tier library assignments
- required columns per artifact
- stage I/O contracts (input/output glob patterns)

Producers and consumers import from here rather than restating facts.
"""

from __future__ import annotations

import json

# === Stage 02 (Opportunity Mining) -> Stage 03 (Monthly WFO) ===

# Output library names and the families contained in each candidate CSV.
# These match the <SYMBOL>_<library>_candidates.csv files written by
# scripts/run_tick_opportunity_mining.py.
MINING_LIBRARY_FAMILIES: dict[str, list[str]] = {
    "directional": [
        "directional",
        "directional_inverse",
        "directional_run",
        "double_touch",
        "pullback",
    ],
    "oco": ["oco_first_touch"],
    "oco_asymmetric": ["oco_asymmetric"],
    "no_touch": ["no_touch"],
    "dollar_residual": ["dollar_residual"],
    "dispersion_rank": ["dispersion_rank"],
    "lead_lag": ["lead_lag"],
}

# Reverse lookup: family -> library.
# Used by Stage 3 WFO to locate the candidate CSV for a given family.
FAMILY_TO_LIBRARY: dict[str, str] = {
    family: lib
    for lib, families in MINING_LIBRARY_FAMILIES.items()
    for family in families
}

# Families that require cross-symbol context (cs_frame).
CROSS_SYMBOL_FAMILIES: set[str] = {
    "dollar_residual",
    "dispersion_rank",
    "lead_lag",
}

# Local families = everything else.
LOCAL_FAMILIES: set[str] = {
    family
    for lib, families in MINING_LIBRARY_FAMILIES.items()
    for family in families
    if family not in CROSS_SYMBOL_FAMILIES
}

# Quality-tier library: which threshold set each output library uses.
# directional, dollar_residual, dispersion_rank, lead_lag share directional thresholds.
# oco, oco_asymmetric share oco thresholds. no_touch is independent.
QUALITY_TIER_LIBRARY: dict[str, str] = {
    "directional": "directional",
    "oco": "oco",
    "oco_asymmetric": "oco",
    "no_touch": "no_touch",
    "dollar_residual": "directional",
    "dispersion_rank": "directional",
    "lead_lag": "directional",
}

# === Output Artifacts ===

MINING_OUTPUT_LIBRARIES: list[str] = list(MINING_LIBRARY_FAMILIES.keys())

CANDIDATE_FILENAME_TEMPLATE: str = "{symbol}_{library}_candidates.csv"
SUMMARY_FILENAME_TEMPLATE: str = "{symbol}_candidate_summary.csv"
FILLS_FILENAME_TEMPLATE: str = "{symbol}_candidate_fills.parquet"

# === Required Columns ===
# Columns that every consumer of candidate CSVs expects to exist.
CANDIDATE_REQUIRED_COLUMNS: list[str] = [
    "annualized_test_fills",
    "bar_ticks",
    "both_window_rate",
    "both_window_rate_train",
    "candidate_id",
    "candidate_schema_version",
    "family",
    "gross_std_test",
    "hit_rate_gross_test",
    "horizon",
    "mean_flow_persistence_train",
    "mean_gross_pips_test",
    "mean_gross_pips_train",
    "mean_tick_burst_train",
    "mean_vol_cluster_train",
    "median_gross_pips_test",
    "median_gross_pips_train",
    "ml_ready_target_type",
    "p_up_first",
    "quality_score",
    "quality_tier",
    "quality_tier_basis",
    "random_baseline_control_mean",
    "random_baseline_p",
    "random_baseline_z",
    "regime_desc",
    "selection_pass",
    "selection_pass_basis",
    "session_coverage",
    "state_id",
    "symbol",
    "test_count",
    "train_count",
]

# === Stage I/O Contracts ===

STAGE02_CONTRACT: dict[str, any] = {
    "stage_id": "stage02",
    "produced_by": None,
    "input_patterns": [
        "data/analysis/tick_velocity/{symbol}_{bar_ticks}tick_velocity.parquet",
        "configs/research/experiments/{symbol}_tick_opportunity_mining.yaml",
    ],
    "output_patterns": [
        "data/analysis/tick_opportunity_mining/{symbol}_candidate_summary.csv",
        "data/analysis/tick_opportunity_mining/{symbol}_candidate_fills.parquet",
        *[
            f"data/analysis/tick_opportunity_mining/{CANDIDATE_FILENAME_TEMPLATE.format(symbol='{symbol}', library=lib)}"
            for lib in MINING_OUTPUT_LIBRARIES
        ],
    ],
}

STAGE03_CONTRACT: dict[str, any] = {
    "stage_id": "stage03",
    "produced_by": "stage02",
    "input_patterns": [
        f"data/analysis/tick_opportunity_mining/{CANDIDATE_FILENAME_TEMPLATE.format(symbol='{symbol}', library=lib)}"
        for lib in MINING_OUTPUT_LIBRARIES
    ],
    "output_patterns": [
        "data/analysis/tick_opportunity_mining/wfo_m3to1_{library}_fullcap_{symbol}/{symbol}_{library}_monthly_predictions.parquet",
        "data/analysis/tick_opportunity_mining/wfo_m3to1_{library}_fullcap_{symbol}/{symbol}_{library}_monthly_metrics.csv",
    ],
}


def build_mining_output_manifest(*, symbol: str) -> dict[str, any]:
    """Return a JSON-serialisable manifest describing the Stage 02 outputs."""
    return {
        "stage": "stage02",
        "symbol": symbol,
        "library_families": MINING_LIBRARY_FAMILIES,
        "required_columns": CANDIDATE_REQUIRED_COLUMNS,
        "output_files": {
            lib: CANDIDATE_FILENAME_TEMPLATE.format(symbol=symbol, library=lib)
            for lib in MINING_OUTPUT_LIBRARIES
        },
    }


def render_stage_io_contract(stage_id: str) -> str:
    """Return a markdown snippet describing the I/O contract for a stage.

    Called by scripts/build_process_stage_docs.py to inject contract
    metadata into generated stage capsules.
    """
    if stage_id == "stage02":
        contract = STAGE02_CONTRACT
        title = "Stage 02 I/O Contract"
    elif stage_id == "stage03":
        contract = STAGE03_CONTRACT
        title = "Stage 03 I/O Contract"
    else:
        return ""

    lines = [f"## {title}", ""]

    if contract.get("produced_by"):
        lines.append(f"**Produced by:** `{contract['produced_by']}`")
        lines.append("")

    lines.append("**Input artifacts:**")
    for pat in contract["input_patterns"]:
        lines.append(f"- `{pat}`")
    lines.append("")

    lines.append("**Output artifacts:**")
    for pat in contract["output_patterns"]:
        lines.append(f"- `{pat}`")
    lines.append("")

    if stage_id == "stage02":
        lines.append("**Library → family expansion:**")
        lines.append("")
        lines.append("| Library file | Families contained |")
        lines.append("|--------------|--------------------|")
        for lib, families in MINING_LIBRARY_FAMILIES.items():
            fname = CANDIDATE_FILENAME_TEMPLATE.format(symbol="<SYMBOL>", library=lib)
            lines.append(f"| `{fname}` | {', '.join(families)} |")
        lines.append("")

        lines.append("**Required columns per candidate CSV:**")
        lines.append("```")
        lines.append(", ".join(CANDIDATE_REQUIRED_COLUMNS))
        lines.append("```")
        lines.append("")

    return "\n".join(lines)
