"""Declarative stage-contract manifest for tick-opportunity governance pipeline.

Single source of truth for:
- family↔library↔artifact-name mapping
- quality-tier library assignments
- required columns per artifact
- stage I/O contracts (input/output glob patterns)

Producers and consumers import from here rather than restating facts.
"""

from __future__ import annotations

from typing import Any

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

STAGE02_CONTRACT: dict[str, Any] = {
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

# === Artifact keys ===
# Whether each stage's primary artifact is uniquely identified by (symbol, family)
# or (symbol, library). Verdict-bearing artifacts (Stage 5 schedules, Stage 6
# tick-exact summaries) and per-family WFO predictions MUST be family-keyed so
# per-family results never collide; only artifacts that genuinely aggregate a
# whole library (the Stage 2 candidate CSVs) may be library-keyed. See ADR 0004.
ARTIFACT_KEY: dict[str, str] = {
    "stage02_candidates": "(symbol, library)",
    "stage03_predictions": "(symbol, family)",
    "stage05_reduced_core": "(symbol, family)",
    "stage06_tick_exact": "(symbol, family)",
}

# Stage 3 WFO writes one per-family directory; real and legitimately-empty runs
# both use the family name (no library-named fallback). Directory has no symbol
# suffix.
WFO_PREDICTION_TEMPLATE: str = (
    "data/analysis/tick_opportunity_mining/wfo_m3to1_{family}_fullcap/"
    "{symbol}_{family}_monthly_predictions.parquet"
)
TICK_EXACT_SUMMARY_TEMPLATE: str = (
    "data/analysis/tick_opportunity_mining/reduced_core/"
    "{symbol}_{family}_tick_exact_summary.csv"
)


def tick_exact_summary_path(*, symbol: str, family: str) -> str:
    """Canonical family-keyed Stage 6 tick-exact summary path (never library-keyed).

    Note: oco_first_touch currently emits under its established `oco` artifact
    slug across the OCO governance stack; canonicalising it to `oco_first_touch`
    is a separate migration. Every other family already conforms to this template.
    """
    return TICK_EXACT_SUMMARY_TEMPLATE.format(symbol=str(symbol).upper(), family=family)


STAGE03_CONTRACT: dict[str, Any] = {
    "stage_id": "stage03",
    "produced_by": "stage02",
    "artifact_key": ARTIFACT_KEY["stage03_predictions"],
    "input_patterns": [
        f"data/analysis/tick_opportunity_mining/{CANDIDATE_FILENAME_TEMPLATE.format(symbol='{symbol}', library=lib)}"
        for lib in MINING_OUTPUT_LIBRARIES
    ],
    "output_patterns": [
        WFO_PREDICTION_TEMPLATE,
        "data/analysis/tick_opportunity_mining/wfo_m3to1_{family}_fullcap/{symbol}_{family}_monthly_metrics.csv",
    ],
}

STAGE06_CONTRACT: dict[str, Any] = {
    "stage_id": "stage06",
    "produced_by": "stage05",
    "artifact_key": ARTIFACT_KEY["stage06_tick_exact"],
    "input_patterns": [
        WFO_PREDICTION_TEMPLATE,
        "data/analysis/tick_opportunity_mining/reduced_core_rolling/{symbol}_{family}_reduced_state_schedule.csv",
    ],
    "output_patterns": [
        TICK_EXACT_SUMMARY_TEMPLATE,
        "data/analysis/tick_opportunity_mining/reduced_core/{symbol}_{family}_tick_exact_monthly.csv",
        "data/analysis/tick_opportunity_mining/reduced_core/{symbol}_{family}_tick_exact_state.csv",
    ],
}


def build_mining_output_manifest(*, symbol: str) -> dict[str, Any]:
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
    contracts = {
        "stage02": (STAGE02_CONTRACT, "Stage 02 I/O Contract"),
        "stage03": (STAGE03_CONTRACT, "Stage 03 I/O Contract"),
        "stage06": (STAGE06_CONTRACT, "Stage 06 I/O Contract"),
    }
    if stage_id not in contracts:
        return ""
    contract, title = contracts[stage_id]

    lines = [f"## {title}", ""]

    if contract.get("produced_by"):
        lines.append(f"**Produced by:** `{contract['produced_by']}`")
        lines.append("")
    if contract.get("artifact_key"):
        lines.append(f"**Artifact key:** `{contract['artifact_key']}`")
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
