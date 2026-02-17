#!/usr/bin/env python3
"""
Select top-2 promoted mixed strategies and materialize filtered report slices.

Inputs:
- meta mixed summary CSV from scripts/meta_triple_barrier_mixed_dd.py
- strategy overall/yearly/pair/pair_yearly CSVs from scripts/report_strategy_fx_comm_multi_tf.py

Outputs:
- recommended top-2 table
- mixed-only top-2 filtered overall/yearly/pair/pair_yearly tables
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


DEFAULT_ANALYSIS_DIR = Path("data/analysis")


def _load_required(path: Path, required: set[str]) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")
    df = pd.read_csv(path)
    missing = sorted(required.difference(df.columns))
    if missing:
        raise ValueError(f"{path} missing required columns: {missing}")
    return df


def _top_k_from_summary(summary: pd.DataFrame, top_k: int) -> pd.DataFrame:
    promoted = summary[summary["variant"].astype(str) == "meta_tb_promoted"].copy()
    baseline = summary[summary["variant"].astype(str) == "baseline_causal"].copy()
    if promoted.empty or baseline.empty:
        raise ValueError("Summary must include both baseline_causal and meta_tb_promoted variants.")

    bcols = [
        "mix_id",
        "trades",
        "mean_pnl_per_trade_bps",
        "sharpe",
        "annualized_bps_calendar",
        "max_daily_dd_bps",
        "max_dd_pct",
    ]
    base = baseline[bcols].rename(
        columns={
            "trades": "base_trades",
            "mean_pnl_per_trade_bps": "base_mean_pnl_per_trade_bps",
            "sharpe": "base_sharpe",
            "annualized_bps_calendar": "base_annualized_bps_calendar",
            "max_daily_dd_bps": "base_max_daily_dd_bps",
            "max_dd_pct": "base_max_dd_pct",
        }
    )

    merged = promoted.merge(base, on="mix_id", how="left")
    merged["delta_trades"] = merged["trades"] - merged["base_trades"]
    merged["delta_mean_pnl_per_trade_bps"] = (
        merged["mean_pnl_per_trade_bps"] - merged["base_mean_pnl_per_trade_bps"]
    )
    merged["delta_sharpe"] = merged["sharpe"] - merged["base_sharpe"]
    merged["delta_annualized_bps_calendar"] = (
        merged["annualized_bps_calendar"] - merged["base_annualized_bps_calendar"]
    )
    merged["delta_max_daily_dd_bps"] = merged["max_daily_dd_bps"] - merged["base_max_daily_dd_bps"]
    merged["delta_max_dd_pct"] = merged["max_dd_pct"] - merged["base_max_dd_pct"]

    ranked = merged.sort_values(["sharpe", "annualized_bps_calendar"], ascending=[False, False]).head(top_k).copy()
    ranked.insert(0, "rank", list(range(1, len(ranked) + 1)))
    return ranked


def _norm01(values: pd.Series) -> pd.Series:
    s = pd.to_numeric(values, errors="coerce").astype(float)
    lo = float(s.min())
    hi = float(s.max())
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return pd.Series(np.full(len(s), 0.5, dtype=float), index=s.index)
    return (s - lo) / (hi - lo)


def _top_k_balanced_exposure(
    summary: pd.DataFrame,
    top_k: int,
    min_time_reduction_frac: float,
    max_sharpe_drop_frac: float,
    max_annualized_drop_frac: float,
    min_dd_improve_frac: float,
) -> pd.DataFrame:
    promoted = summary[summary["variant"].astype(str) == "meta_tb_promoted"].copy()
    baseline = summary[summary["variant"].astype(str) == "baseline_causal"].copy()
    if promoted.empty or baseline.empty:
        raise ValueError("Summary must include both baseline_causal and meta_tb_promoted variants.")

    required = {"mix_id", "time_in_market_pct", "sharpe", "annualized_bps_calendar", "max_daily_dd_bps"}
    missing = sorted(required.difference(set(summary.columns)))
    if missing:
        raise ValueError(f"Summary missing columns required for balanced_exposure objective: {missing}")

    base = baseline[
        [
            "mix_id",
            "trades",
            "mean_pnl_per_trade_bps",
            "sharpe",
            "annualized_bps_calendar",
            "max_daily_dd_bps",
            "max_dd_pct",
            "time_in_market_pct",
        ]
    ].rename(
        columns={
            "trades": "base_trades",
            "mean_pnl_per_trade_bps": "base_mean_pnl_per_trade_bps",
            "sharpe": "base_sharpe",
            "annualized_bps_calendar": "base_annualized_bps_calendar",
            "max_daily_dd_bps": "base_max_daily_dd_bps",
            "max_dd_pct": "base_max_dd_pct",
            "time_in_market_pct": "base_time_in_market_pct",
        }
    )

    merged = promoted.merge(base, on="mix_id", how="left")
    merged["delta_trades"] = merged["trades"] - merged["base_trades"]
    merged["delta_mean_pnl_per_trade_bps"] = (
        merged["mean_pnl_per_trade_bps"] - merged["base_mean_pnl_per_trade_bps"]
    )
    merged["delta_sharpe"] = merged["sharpe"] - merged["base_sharpe"]
    merged["delta_annualized_bps_calendar"] = (
        merged["annualized_bps_calendar"] - merged["base_annualized_bps_calendar"]
    )
    merged["delta_max_daily_dd_bps"] = merged["max_daily_dd_bps"] - merged["base_max_daily_dd_bps"]
    merged["delta_max_dd_pct"] = merged["max_dd_pct"] - merged["base_max_dd_pct"]
    merged["delta_time_in_market_pct"] = merged["time_in_market_pct"] - merged["base_time_in_market_pct"]

    base_time = pd.to_numeric(merged["base_time_in_market_pct"], errors="coerce").astype(float).clip(lower=1e-6)
    base_sharpe = pd.to_numeric(merged["base_sharpe"], errors="coerce").astype(float).clip(lower=1e-6)
    base_ann = pd.to_numeric(merged["base_annualized_bps_calendar"], errors="coerce").astype(float).clip(lower=1e-6)
    base_dd_abs = pd.to_numeric(merged["base_max_daily_dd_bps"], errors="coerce").astype(float).abs().clip(lower=1e-6)

    merged["time_reduction_frac"] = ((base_time - merged["time_in_market_pct"]) / base_time).clip(lower=-10.0, upper=10.0)
    merged["sharpe_drop_frac"] = ((base_sharpe - merged["sharpe"]) / base_sharpe).clip(lower=-10.0, upper=10.0)
    merged["annualized_drop_frac"] = (
        (base_ann - merged["annualized_bps_calendar"]) / base_ann
    ).clip(lower=-10.0, upper=10.0)
    merged["dd_improve_frac"] = (merged["delta_max_daily_dd_bps"] / base_dd_abs).clip(lower=-10.0, upper=10.0)

    eligible = (
        (merged["time_reduction_frac"] >= float(min_time_reduction_frac))
        & (merged["sharpe_drop_frac"] <= float(max_sharpe_drop_frac))
        & (merged["annualized_drop_frac"] <= float(max_annualized_drop_frac))
        & (merged["dd_improve_frac"] >= float(min_dd_improve_frac))
    )
    cand = merged.loc[eligible].copy()
    if cand.empty:
        # Conservative fallback: relax only the time gate while preserving causal quality checks.
        fallback = (
            (merged["sharpe_drop_frac"] <= float(max_sharpe_drop_frac))
            & (merged["annualized_drop_frac"] <= float(max_annualized_drop_frac))
            & (merged["dd_improve_frac"] >= float(min_dd_improve_frac))
        )
        cand = merged.loc[fallback].copy()
    if cand.empty:
        cand = merged.copy()

    cand["score"] = (
        0.35 * _norm01(cand["time_reduction_frac"])
        + 0.30 * _norm01(cand["dd_improve_frac"])
        + 0.20 * _norm01(cand["sharpe"])
        + 0.15 * _norm01(cand["annualized_bps_calendar"])
    )
    ranked = cand.sort_values(
        ["score", "sharpe", "annualized_bps_calendar", "dd_improve_frac", "time_reduction_frac"],
        ascending=[False, False, False, False, False],
    ).head(top_k).copy()
    ranked.insert(0, "rank", list(range(1, len(ranked) + 1)))
    return ranked


def _filter_mixed_top2(df: pd.DataFrame, mixes: list[str]) -> pd.DataFrame:
    if df.empty or "variant" not in df.columns:
        return df.copy()
    if "timeframe" in df.columns:
        df = df[df["timeframe"].astype(str) == "mixed"].copy()
    prefixes = [f"mixed_{m}__" for m in mixes]
    mask = pd.Series(False, index=df.index)
    variants = df["variant"].astype(str)
    for pref in prefixes:
        mask = mask | variants.str.startswith(pref)
    return df[mask].copy()


def _top_k_lowz_ml(summary: pd.DataFrame, top_k: int) -> pd.DataFrame:
    required = {"candidate_id", "mix_id", "score", "eligible", "sharpe", "annualized_bps_calendar"}
    missing = sorted(required.difference(set(summary.columns)))
    if missing:
        raise ValueError(f"Low-Z ML summary missing required columns: {missing}")
    ranked = summary.copy()
    ranked["eligible"] = ranked["eligible"].astype(bool)
    ranked = ranked.sort_values(
        ["eligible", "score", "sharpe", "annualized_bps_calendar"],
        ascending=[False, False, False, False],
    ).head(top_k).copy()
    ranked.insert(0, "rank", list(range(1, len(ranked) + 1)))
    return ranked


def main() -> None:
    parser = argparse.ArgumentParser(description="Select top-2 mixed strategies and write filtered report slices.")
    parser.add_argument(
        "--analysis-dir",
        default=str(DEFAULT_ANALYSIS_DIR),
        help="analysis directory containing summary and strategy report CSVs",
    )
    parser.add_argument(
        "--summary-file",
        default="meta_tb_mixed_no_oil_allmix_summary.csv",
        help="mixed summary CSV generated by meta_triple_barrier_mixed_dd.py",
    )
    parser.add_argument(
        "--summary-kind",
        default="meta_mixed",
        choices=["meta_mixed", "lowz_ml_hardgate"],
        help="schema mode for summary-file",
    )
    parser.add_argument(
        "--overall-file",
        default="strategy_fx_comm_no_oil_overall.csv",
        help="overall report CSV generated by report_strategy_fx_comm_multi_tf.py",
    )
    parser.add_argument(
        "--yearly-file",
        default="strategy_fx_comm_no_oil_yearly.csv",
        help="yearly report CSV generated by report_strategy_fx_comm_multi_tf.py",
    )
    parser.add_argument(
        "--pair-file",
        default="strategy_fx_comm_no_oil_pair.csv",
        help="pair report CSV generated by report_strategy_fx_comm_multi_tf.py",
    )
    parser.add_argument(
        "--pair-yearly-file",
        default="strategy_fx_comm_no_oil_pair_yearly.csv",
        help="pair-yearly report CSV generated by report_strategy_fx_comm_multi_tf.py",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=2,
        help="number of mixes to select by promoted Sharpe/annualized_bps",
    )
    parser.add_argument(
        "--objective",
        default="sharpe",
        choices=["sharpe", "balanced_exposure"],
        help="selection objective for recommended mixes",
    )
    parser.add_argument(
        "--min-time-reduction-frac",
        type=float,
        default=0.30,
        help="for balanced_exposure: minimum fraction reduction in time_in_market_pct vs baseline",
    )
    parser.add_argument(
        "--max-sharpe-drop-frac",
        type=float,
        default=0.15,
        help="for balanced_exposure: maximum allowed Sharpe drop fraction vs baseline",
    )
    parser.add_argument(
        "--max-annualized-drop-frac",
        type=float,
        default=0.20,
        help="for balanced_exposure: maximum allowed annualized_bps drop fraction vs baseline",
    )
    parser.add_argument(
        "--min-dd-improve-frac",
        type=float,
        default=0.15,
        help="for balanced_exposure: minimum required max_daily_dd_bps improvement fraction",
    )
    parser.add_argument(
        "--out-prefix",
        default="strategy_fx_comm_no_oil_mixed_top2",
        help="output prefix for filtered mixed tables",
    )
    parser.add_argument(
        "--recommended-file",
        default="meta_tb_mixed_no_oil_allmix_recommended_top2.csv",
        help="filename for the recommended top-k table",
    )
    args = parser.parse_args()

    analysis_dir = Path(args.analysis_dir)
    summary_path = analysis_dir / args.summary_file
    overall_path = analysis_dir / args.overall_file
    yearly_path = analysis_dir / args.yearly_file
    pair_path = analysis_dir / args.pair_file
    pair_yearly_path = analysis_dir / args.pair_yearly_file

    if args.summary_kind == "lowz_ml_hardgate":
        summary = _load_required(
            summary_path,
            {"candidate_id", "mix_id", "trades", "mean_pnl_per_trade_bps", "sharpe", "annualized_bps_calendar", "score", "eligible"},
        )
    else:
        summary = _load_required(
            summary_path,
            {"mix_id", "variant", "trades", "mean_pnl_per_trade_bps", "sharpe", "annualized_bps_calendar", "max_daily_dd_bps", "max_dd_pct"},
        )
    overall = _load_required(overall_path, {"variant"})
    yearly = _load_required(yearly_path, {"variant"})
    pair = _load_required(pair_path, {"variant"})
    pair_yearly = _load_required(pair_yearly_path, {"variant"})

    if args.summary_kind == "lowz_ml_hardgate":
        top = _top_k_lowz_ml(summary=summary, top_k=max(1, int(args.top_k)))
        # for low-z summary, report uses mix_id in variant prefix.
        mixes = top["mix_id"].astype(str).tolist()
    else:
        if args.objective == "balanced_exposure":
            top = _top_k_balanced_exposure(
                summary=summary,
                top_k=max(1, int(args.top_k)),
                min_time_reduction_frac=float(args.min_time_reduction_frac),
                max_sharpe_drop_frac=float(args.max_sharpe_drop_frac),
                max_annualized_drop_frac=float(args.max_annualized_drop_frac),
                min_dd_improve_frac=float(args.min_dd_improve_frac),
            )
        else:
            top = _top_k_from_summary(summary, top_k=max(1, int(args.top_k)))
        mixes = top["mix_id"].astype(str).tolist()

    out_recommended = analysis_dir / args.recommended_file
    out_overall = analysis_dir / f"{args.out_prefix}_overall.csv"
    out_yearly = analysis_dir / f"{args.out_prefix}_yearly.csv"
    out_pair = analysis_dir / f"{args.out_prefix}_pair.csv"
    out_pair_yearly = analysis_dir / f"{args.out_prefix}_pair_yearly.csv"

    _filter_mixed_top2(overall, mixes).to_csv(out_overall, index=False)
    _filter_mixed_top2(yearly, mixes).to_csv(out_yearly, index=False)
    _filter_mixed_top2(pair, mixes).to_csv(out_pair, index=False)
    _filter_mixed_top2(pair_yearly, mixes).to_csv(out_pair_yearly, index=False)
    top.to_csv(out_recommended, index=False)

    print("Top mixes:")
    for mix in mixes:
        print(f"- {mix}")
    print("\nSaved:")
    print(f"- {out_recommended}")
    print(f"- {out_overall}")
    print(f"- {out_yearly}")
    print(f"- {out_pair}")
    print(f"- {out_pair_yearly}")


if __name__ == "__main__":
    main()
