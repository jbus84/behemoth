#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = REPO_ROOT / "configs" / "research" / "experiments"
TARGET_DIR = REPO_ROOT / "configs" / "research" / "experiments_dukascopy_candidate"

ACTIVE_CONFIGS = (
    "eurusd_tick_opportunity_mining.yaml",
    "eurusd_tick_opportunity_monthly_wfo_oco_fullcap_2025.yaml",
    "eurusd_oco_reduced_core_rolling_2025.yaml",
    "gbpusd_tick_opportunity_mining.yaml",
    "gbpusd_tick_opportunity_monthly_wfo_oco_fullcap_2025.yaml",
    "gbpusd_oco_reduced_core_rolling_2025.yaml",
    "usdjpy_tick_opportunity_mining.yaml",
    "usdjpy_tick_opportunity_monthly_wfo_oco_fullcap_2025.yaml",
    "usdjpy_oco_reduced_core_rolling_2025.yaml",
    "usdchf_tick_opportunity_mining.yaml",
    "usdchf_tick_opportunity_monthly_wfo_oco_fullcap_2025.yaml",
    "usdchf_oco_reduced_core_rolling_2025.yaml",
    "audusd_tick_opportunity_mining.yaml",
    "audusd_tick_opportunity_monthly_wfo_oco_fullcap_2025.yaml",
    "audusd_oco_reduced_core_rolling_2025.yaml",
    "usdcad_tick_opportunity_mining.yaml",
    "usdcad_tick_opportunity_monthly_wfo_oco_fullcap_2025.yaml",
    "usdcad_oco_reduced_core_rolling_2025.yaml",
)


def _rewrite_content(content: str) -> str:
    staged_replacements = (
        (
            "data/analysis/tick_opportunity_mining/stop_limit_tickfill_fullcap",
            "__DUKASCOPY_CANDIDATE_STOP_LIMIT__",
        ),
        (
            "data/analysis/tick_opportunity_mining/wfo_2025_m3to1_oco_fullcap",
            "__DUKASCOPY_CANDIDATE_WFO__",
        ),
        (
            "data/analysis/tick_opportunity_mining/reduced_core_rolling",
            "__DUKASCOPY_CANDIDATE_REDUCED_ROLLING__",
        ),
        ("data/analysis/tick_opportunity_mining/reduced_core", "__DUKASCOPY_CANDIDATE_REDUCED__"),
        ("data/analysis/tick_opportunity_mining", "__DUKASCOPY_CANDIDATE_MINING__"),
    )
    final_replacements = (
        (
            "__DUKASCOPY_CANDIDATE_STOP_LIMIT__",
            "data/analysis/tick_opportunity_mining_dukascopy_candidate/stop_limit_tickfill_fullcap",
        ),
        (
            "__DUKASCOPY_CANDIDATE_WFO__",
            "data/analysis/tick_opportunity_mining_dukascopy_candidate/wfo_2025_m3to1_oco_fullcap",
        ),
        (
            "__DUKASCOPY_CANDIDATE_REDUCED_ROLLING__",
            "data/analysis/tick_opportunity_mining_dukascopy_candidate/reduced_core_rolling",
        ),
        (
            "__DUKASCOPY_CANDIDATE_REDUCED__",
            "data/analysis/tick_opportunity_mining_dukascopy_candidate/reduced_core",
        ),
        (
            "__DUKASCOPY_CANDIDATE_MINING__",
            "data/analysis/tick_opportunity_mining_dukascopy_candidate",
        ),
        ("data/analysis/tick_velocity", "data/analysis/tick_velocity_dukascopy_candidate"),
        ("docs/analysis/", "docs/analysis/dukascopy_candidate/"),
        ("_report.md", "_dukascopy_candidate_report.md"),
    )
    for old, new in staged_replacements:
        content = content.replace(old, new)
    for old, new in final_replacements:
        content = content.replace(old, new)
    return content


def generate_configs(overwrite: bool) -> list[Path]:
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name in ACTIVE_CONFIGS:
        src = SOURCE_DIR / name
        dst = TARGET_DIR / name
        if dst.exists() and not overwrite:
            continue
        rewritten = _rewrite_content(src.read_text())
        dst.write_text(rewritten)
        written.append(dst)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Dukascopy candidate experiment configs.")
    parser.add_argument(
        "--overwrite", action="store_true", help="Overwrite existing candidate configs."
    )
    args = parser.parse_args()

    written = generate_configs(overwrite=args.overwrite)
    print(f"wrote_configs={len(written)} target_dir={TARGET_DIR}")
    for path in written:
        print(path.relative_to(REPO_ROOT))


if __name__ == "__main__":
    main()
