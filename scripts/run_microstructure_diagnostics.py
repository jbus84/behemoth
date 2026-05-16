#!/usr/bin/env python3
"""Post-mining diagnostic: compare microstructure regime quality vs baseline.

Reads the candidate CSVs from `data/analysis/tick_opportunity_mining/`
and emits a report to `data/analysis/microstructure_regime_diagnostics/`.

Usage:
    uv run python scripts/run_microstructure_diagnostics.py --symbol EURUSD
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--mining-dir", default="data/analysis/tick_opportunity_mining")
    parser.add_argument("--output-dir", default="data/analysis/microstructure_regime_diagnostics")
    args = parser.parse_args()

    mining_dir = Path(args.mining_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    oco_path = mining_dir / f"{args.symbol}_oco_candidates.csv"
    if not oco_path.exists():
        print(f"No candidates found at {oco_path}")
        return

    df = pd.read_csv(oco_path)
    df["regime"] = df["regime_desc"].str.split(";").str[0]

    baseline = df[df["regime"] == "all"]["mean_gross_pips_train"].mean()
    new_regimes = ["high_intensity", "high_activity", "persistent_flow", "negative_flow", "high_vol_cluster"]

    rows = []
    for r in new_regimes:
        subset = df[df["regime"] == r]
        if len(subset) == 0:
            continue
        rows.append({
            "regime": r,
            "candidate_count": len(subset),
            "train_count_mean": subset["train_count"].mean(),
            "mean_gross_train": subset["mean_gross_pips_train"].mean(),
            "baseline_mean_gross": baseline,
            "delta_vs_baseline": subset["mean_gross_pips_train"].mean() - baseline,
            "tier_a_pct": (subset["quality_tier"] == "A").mean() * 100,
        })

    report = pd.DataFrame(rows)
    out_path = output_dir / f"{args.symbol}_microstructure_regime_report.csv"
    report.to_csv(out_path, index=False)
    print(f"Report written to {out_path}")
    print(report.to_string(index=False))


if __name__ == "__main__":
    main()
