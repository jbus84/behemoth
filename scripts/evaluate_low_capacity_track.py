#!/usr/bin/env python3
"""Low-capacity regime track evaluation harness.

Identifies sub-capacity-but-statistically-robust states from post-CatBoost WFO
predictions, gates them on net-of-cost LB95 + month-consistency, and aggregates
admitted states into a combined low-frequency portfolio with multiple-testing-aware
metrics.

Implements ADR 0005: Low-Capacity Regime-Specific Strategy Track.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats


def _parse_candidate_uid(uid: str) -> dict[str, Any]:
    """Parse candidate_uid format: <lib>|<SYM>|<bar_ticks>|h<h>|<state_id>."""
    parts = str(uid).split("|")
    if len(parts) < 5:
        raise ValueError(f"Invalid candidate_uid format: {uid}")
    return {
        "lib": parts[0],
        "symbol": parts[1],
        "bar_ticks": int(parts[2]),
        "horizon": int(parts[3].lstrip("h")),
        "state_id": parts[4],
    }


def _state_metrics(
    group_df: pd.DataFrame,
) -> dict[str, Any]:
    """Compute per-state metrics from a grouped DataFrame.

    Args:
        group_df: DataFrame with columns [net, test_month, close_ts].
                  Rows are events for a single (symbol, family, bar_ticks, state_id).

    Returns:
        Dictionary with keys: n, years, annualized, avg_month_rows, net_mean,
        net_std, net_lb95, positive_month_share, p_value_ttest.
    """
    n = len(group_df)
    if n == 0:
        return {}

    # Compute distinct test months
    n_distinct_months = group_df["test_month"].nunique()
    years = max(1.0, n_distinct_months / 12.0)
    annualized = n / years

    # Per-month mean net
    monthly_means = group_df.groupby("test_month")["net"].mean()
    positive_months = (monthly_means > 0).sum()
    positive_month_share = positive_months / max(1, len(monthly_means))

    # Overall net stats
    net_mean = group_df["net"].mean()
    net_std = group_df["net"].std(ddof=1) if n > 1 else 0.0

    # LB95: mean - 1.645 * se
    net_se = net_std / np.sqrt(n) if n > 0 else np.nan
    net_lb95 = net_mean - 1.645 * net_se if n >= 2 else np.nan

    # One-sample t-test: H0: mean net <= 0 (one-sided, right tail)
    if n >= 2:
        # scipy.stats.ttest_1samp returns (t, p_two_sided)
        t_stat = net_mean / net_se if net_se > 0 else 0.0
        # One-sided p-value (right tail): P(T > t) for H0: mean > 0
        p_value = stats.t.sf(t_stat, df=n - 1)
    else:
        p_value = np.nan

    return {
        "n": n,
        "years": years,
        "annualized": annualized,
        "n_distinct_months": n_distinct_months,
        "avg_month_rows": n / max(1, n_distinct_months),
        "net_mean": net_mean,
        "net_std": net_std,
        "net_lb95": net_lb95,
        "positive_month_share": positive_month_share,
        "p_value": p_value,
    }


def _apply_gates(
    state_metrics_df: pd.DataFrame,
    capacity_floor: float,
    min_trades: int,
    min_positive_month_share: float,
) -> pd.DataFrame:
    """Apply capacity and low-frequency gates to state metrics.

    Args:
        state_metrics_df: DataFrame with metrics per state.
        capacity_floor: Annualized or monthly row threshold for capacity.
        min_trades: Minimum trade count to consider.
        min_positive_month_share: Minimum fraction of positive months.

    Returns:
        DataFrame with added columns: capacity_pass, lowfreq_pass, admitted.
    """
    df = state_metrics_df.copy()

    # Capacity gate: annualized >= floor OR avg_month_rows >= floor
    df["capacity_pass"] = (df["annualized"] >= capacity_floor) | (
        df["avg_month_rows"] >= capacity_floor
    )

    # Low-frequency gate
    df["lowfreq_pass"] = (
        (df["net_lb95"] > 0)
        & (df["positive_month_share"] >= min_positive_month_share)
        & (df["n"] >= min_trades)
    )

    # Admitted: low-freq gate passes but capacity gate fails
    df["admitted"] = df["lowfreq_pass"] & ~df["capacity_pass"]

    return df


def _bh_correction(p_values: np.ndarray, q: float = 0.10) -> np.ndarray:
    """Benjamini-Hochberg FDR correction.

    Args:
        p_values: Array of p-values.
        q: FDR threshold (default 0.10).

    Returns:
        Boolean array indicating which tests are significant at level q.
    """
    if len(p_values) == 0:
        return np.array([], dtype=bool)

    # Remove NaNs
    valid_mask = ~np.isnan(p_values)
    valid_pvals = p_values[valid_mask]

    if len(valid_pvals) == 0:
        return np.array([False] * len(p_values), dtype=bool)

    # Sort and apply BH
    sorted_indices = np.argsort(valid_pvals)
    sorted_pvals = valid_pvals[sorted_indices]
    m = len(sorted_pvals)

    # BH threshold: find largest i such that p_i <= (i/m) * q
    bh_threshold = np.inf
    for i in range(m - 1, -1, -1):
        if sorted_pvals[i] <= (i + 1) / m * q:
            bh_threshold = sorted_pvals[i]
            break

    # Mark as significant if p <= bh_threshold
    significant = valid_pvals <= bh_threshold
    result = np.array([False] * len(p_values), dtype=bool)
    result[valid_mask] = significant
    return result


def _load_and_process_predictions(
    tom_dir: Path,
    velocity_dir: Path,
    symbols: list[str],
    families: list[str],
    bar_ticks_filter: set[int] | None = None,
) -> pd.DataFrame:
    """Load WFO predictions and join with per-event costs.

    Args:
        tom_dir: Path to tick_opportunity_mining data (WFO predictions).
        velocity_dir: Path to tick_velocity data (per-event costs).
        symbols: List of symbols to process.
        families: List of families to process.

    Returns:
        DataFrame with columns: symbol, family, bar_ticks, horizon, state_id,
        test_month, close_ts, target_gross_pips, cost_est_pips, net.
        Rows are kept only where selected_exec is truthy.
    """
    all_frames = []

    for symbol in symbols:
        for family in families:
            pred_file = tom_dir / f"wfo_m3to1_{family}_fullcap" / f"{symbol}_{family}_monthly_predictions.parquet"

            if not pred_file.exists():
                continue

            pred_df = pd.read_parquet(pred_file)

            # Legitimately-empty WFO runs write a 0-row, no-column parquet.
            # Skip them: no selection column means no tradeable events.
            if "selected_exec" not in pred_df.columns:
                continue

            # Filter by selected_exec (truthy: "true", "1")
            pred_df["selected_exec_bool"] = pred_df["selected_exec"].astype(str).str.lower().isin(
                {"true", "1"}
            )
            pred_df = pred_df[pred_df["selected_exec_bool"]].copy()
            pred_df = pred_df.drop(columns=["selected_exec_bool"])

            if len(pred_df) == 0:
                continue

            # Parse candidate_uid
            parsed = pred_df["candidate_uid"].apply(_parse_candidate_uid)
            pred_df["bar_ticks"] = parsed.apply(lambda x: x["bar_ticks"])
            pred_df["horizon"] = parsed.apply(lambda x: x["horizon"])
            pred_df["state_id"] = parsed.apply(lambda x: x["state_id"])

            # Apply bar_ticks filter if specified
            if bar_ticks_filter is not None:
                pred_df = pred_df[pred_df["bar_ticks"].isin(bar_ticks_filter)].copy()
                if len(pred_df) == 0:
                    continue

            # Ensure close_ts is timezone-aware UTC
            if "close_ts" in pred_df.columns:
                pred_df["close_ts"] = pd.to_datetime(pred_df["close_ts"], utc=True)

            # Load velocity data for this symbol and bar_ticks
            # Velocity file: {velocity_dir}/{SYM}_{bar_ticks}tick_velocity.parquet
            # Create all needed tick counts
            tick_counts = sorted(pred_df["bar_ticks"].unique())

            velocity_data_by_ticks = {}
            for ticks in tick_counts:
                velocity_file = velocity_dir / f"{symbol}_{ticks}tick_velocity.parquet"
                if velocity_file.exists():
                    vel_df = pd.read_parquet(velocity_file)
                    # Ensure close_ts is timezone-aware UTC
                    if "close_ts" in vel_df.columns:
                        vel_df["close_ts"] = pd.to_datetime(vel_df["close_ts"], utc=True)
                    velocity_data_by_ticks[ticks] = vel_df

            # Join per-event costs via a deduped close_ts -> cost map. Using a
            # map (not merge + .values) is robust to duplicate/unordered
            # velocity close_ts, which would otherwise row-explode the left
            # merge and misalign the back-assignment.
            pred_df["cost_est_pips"] = np.nan

            for ticks in tick_counts:
                mask = pred_df["bar_ticks"] == ticks
                if ticks in velocity_data_by_ticks:
                    vel_df = velocity_data_by_ticks[ticks]
                    cost_map = (
                        vel_df.dropna(subset=["close_ts"])
                        .drop_duplicates(subset=["close_ts"], keep="first")
                        .set_index("close_ts")["cost_est_pips"]
                    )
                    pred_df.loc[mask, "cost_est_pips"] = (
                        pred_df.loc[mask, "close_ts"].map(cost_map).to_numpy()
                    )

            # Compute net = target_gross_pips - cost_est_pips
            pred_df["net"] = pred_df["target_gross_pips"] - pred_df["cost_est_pips"]

            # Add symbol and family columns
            pred_df["symbol"] = symbol
            pred_df["family"] = family

            # Keep only needed columns
            pred_df = pred_df[
                [
                    "symbol",
                    "family",
                    "bar_ticks",
                    "horizon",
                    "state_id",
                    "test_month",
                    "close_ts",
                    "target_gross_pips",
                    "cost_est_pips",
                    "net",
                ]
            ]

            all_frames.append(pred_df)

    return pd.concat(all_frames, ignore_index=True) if all_frames else pd.DataFrame()


def _compute_state_metrics_table(df: pd.DataFrame) -> pd.DataFrame:
    """Group by (symbol, family, bar_ticks, state_id) and compute metrics.

    Args:
        df: DataFrame from _load_and_process_predictions.

    Returns:
        DataFrame with one row per state and all computed metrics.
    """
    group_cols = ["symbol", "family", "bar_ticks", "state_id"]

    metrics_list = []
    for name, group_df in df.groupby(group_cols):
        metrics = _state_metrics(group_df)
        if metrics:
            row = {col: name[i] for i, col in enumerate(group_cols)}
            row.update(metrics)
            metrics_list.append(row)

    return pd.DataFrame(metrics_list) if metrics_list else pd.DataFrame()


def _aggregate_portfolio(
    admitted_df: pd.DataFrame,
    predictions_df: pd.DataFrame,
) -> dict[str, Any]:
    """Aggregate metrics across a set of admitted states into a portfolio.

    Args:
        admitted_df: Filtered DataFrame of admitted (or baseline capacity-passing) states.
        predictions_df: Full predictions DataFrame (for event-level data).

    Returns:
        Dictionary with portfolio-level metrics.
    """
    if len(admitted_df) == 0:
        return {}

    # Filter predictions to only admitted states
    state_keys = admitted_df[["symbol", "family", "bar_ticks", "state_id"]].drop_duplicates()
    merged = predictions_df.merge(
        state_keys, on=["symbol", "family", "bar_ticks", "state_id"], how="inner"
    )

    if len(merged) == 0:
        return {}

    # Pooled net stats
    pooled_net = merged["net"]
    n_pooled = len(pooled_net)
    net_mean_pooled = pooled_net.mean()
    net_std_pooled = pooled_net.std(ddof=1) if n_pooled > 1 else 0.0
    net_se_pooled = net_std_pooled / np.sqrt(n_pooled) if n_pooled > 0 else np.nan
    net_lb95_pooled = net_mean_pooled - 1.645 * net_se_pooled if n_pooled >= 2 else np.nan

    # Monthly-series metrics
    monthly_net = merged.groupby("test_month")["net"].mean()
    positive_months_portfolio = (monthly_net > 0).sum()
    positive_month_share_portfolio = positive_months_portfolio / max(1, len(monthly_net))

    # Monthly Sharpe-like
    monthly_mean = monthly_net.mean()
    monthly_std = monthly_net.std()
    monthly_sharpe = monthly_mean / monthly_std if monthly_std > 0 else np.nan

    # Trades per year
    n_months = merged["test_month"].nunique()
    years = max(1.0, n_months / 12.0)
    total_trades_per_year = n_pooled / years

    # Diversification counts
    n_states = admitted_df.shape[0]
    n_symbols = admitted_df["symbol"].nunique()
    n_families = admitted_df["family"].nunique()

    return {
        "n_trades": n_pooled,
        "net_mean": net_mean_pooled,
        "net_lb95": net_lb95_pooled,
        "positive_month_share": positive_month_share_portfolio,
        "total_trades_per_year": total_trades_per_year,
        "n_states": n_states,
        "n_symbols": n_symbols,
        "n_families": n_families,
        "monthly_sharpe": monthly_sharpe,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate low-capacity regime track from WFO predictions."
    )
    parser.add_argument(
        "--symbols",
        default="EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD",
        help="Comma-separated symbol list",
    )
    parser.add_argument(
        "--families",
        default="directional,directional_inverse,directional_run",
        help="Comma-separated family list",
    )
    parser.add_argument(
        "--bar-ticks",
        default="",
        help="Comma-separated bar_ticks to include (e.g. '1000,2000'). Empty = all.",
    )
    parser.add_argument(
        "--tom-dir",
        type=Path,
        default=Path("data/analysis/tick_opportunity_mining"),
        help="Path to tick_opportunity_mining directory",
    )
    parser.add_argument(
        "--velocity-dir",
        type=Path,
        default=Path("data/analysis/tick_velocity"),
        help="Path to tick_velocity directory",
    )
    parser.add_argument(
        "--capacity-floor",
        type=float,
        default=3000.0,
        help="Capacity floor (annualized or monthly rows)",
    )
    parser.add_argument(
        "--min-trades",
        type=int,
        default=200,
        help="Minimum trade count",
    )
    parser.add_argument(
        "--min-positive-month-share",
        type=float,
        default=0.6,
        help="Minimum positive-month share",
    )
    parser.add_argument(
        "--fdr-q",
        type=float,
        default=0.10,
        help="Benjamini-Hochberg FDR threshold",
    )
    parser.add_argument(
        "--out-csv",
        type=Path,
        default=Path("data/analysis/low_capacity_track/admitted_states.csv"),
        help="Output CSV file",
    )
    parser.add_argument(
        "--out-report",
        type=Path,
        default=Path("docs/analysis/low_capacity_track_report.md"),
        help="Output report file",
    )

    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",")]
    families = [f.strip() for f in args.families.split(",")]
    bar_ticks_filter = (
        {int(x.strip()) for x in args.bar_ticks.split(",") if x.strip()}
        if args.bar_ticks
        else None
    )

    # Load and process predictions
    print("Loading predictions and costs...")
    pred_df = _load_and_process_predictions(
        args.tom_dir, args.velocity_dir, symbols, families, bar_ticks_filter
    )

    if len(pred_df) == 0:
        print("No prediction data found. Exiting.")
        return

    # Compute per-state metrics
    print("Computing state metrics...")
    state_metrics_df = _compute_state_metrics_table(pred_df)

    # Apply gates
    print("Applying gates...")
    state_metrics_df = _apply_gates(
        state_metrics_df,
        args.capacity_floor,
        args.min_trades,
        args.min_positive_month_share,
    )

    # Apply BH correction
    print("Applying Benjamini-Hochberg correction...")
    n_states_tested = len(state_metrics_df)
    bh_sig = _bh_correction(state_metrics_df["p_value"].values, q=args.fdr_q)
    state_metrics_df["bh_significant"] = bh_sig
    state_metrics_df["admitted_bh"] = state_metrics_df["admitted"] & state_metrics_df["bh_significant"]

    # Write state CSV
    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    state_metrics_df.to_csv(args.out_csv, index=False)
    print(f"Wrote state metrics to {args.out_csv}")

    # Compute portfolio metrics
    admitted_df = state_metrics_df[state_metrics_df["admitted"]].copy()
    admitted_bh_df = state_metrics_df[state_metrics_df["admitted_bh"]].copy()
    capacity_pass_df = state_metrics_df[state_metrics_df["capacity_pass"]].copy()

    portfolio_admitted = _aggregate_portfolio(admitted_df, pred_df)
    portfolio_admitted_bh = _aggregate_portfolio(admitted_bh_df, pred_df)
    portfolio_capacity = _aggregate_portfolio(capacity_pass_df, pred_df)

    # Generate report
    args.out_report.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out_report, "w") as f:
        f.write("# Low-Capacity Track Evaluation Report\n\n")

        # Per-symbol summary
        f.write("## Per-Symbol Summary\n\n")
        f.write("| Symbol | Directional States | Net-LB95-Positive | Capacity-Pass | Admitted | Admitted (BH) |\n")
        f.write("|---|---|---|---|---|---|\n")

        for symbol in symbols:
            symbol_df = state_metrics_df[state_metrics_df["symbol"] == symbol]
            n_states = len(symbol_df)
            n_lb95_pos = (symbol_df["net_lb95"] > 0).sum()
            n_capacity = symbol_df["capacity_pass"].sum()
            n_admitted = symbol_df["admitted"].sum()
            n_admitted_bh = symbol_df["admitted_bh"].sum()
            f.write(
                f"| {symbol} | {n_states} | {n_lb95_pos} | {n_capacity} | {n_admitted} | {n_admitted_bh} |\n"
            )

        f.write(f"\n**Total states tested:** {n_states_tested}\n\n")

        # Portfolio block: admitted
        f.write("## Portfolio: Admitted States (Raw)\n\n")
        if portfolio_admitted:
            f.write(f"- **Net Mean:** {portfolio_admitted['net_mean']:.4f}\n")
            f.write(f"- **Net LB95:** {portfolio_admitted['net_lb95']:.4f}\n")
            f.write(f"- **Positive-Month Share:** {portfolio_admitted['positive_month_share']:.2%}\n")
            f.write(f"- **Trades/Year:** {portfolio_admitted['total_trades_per_year']:.1f}\n")
            f.write(f"- **Monthly Sharpe:** {portfolio_admitted['monthly_sharpe']:.4f}\n")
            f.write(f"- **States:** {portfolio_admitted['n_states']}\n")
            f.write(f"- **Symbols:** {portfolio_admitted['n_symbols']}\n")
            f.write(f"- **Families:** {portfolio_admitted['n_families']}\n")
        else:
            f.write("No admitted states.\n")

        f.write("\n")

        # Portfolio block: admitted_bh
        f.write("## Portfolio: Admitted States (BH-Filtered)\n\n")
        if portfolio_admitted_bh:
            f.write(f"- **Net Mean:** {portfolio_admitted_bh['net_mean']:.4f}\n")
            f.write(f"- **Net LB95:** {portfolio_admitted_bh['net_lb95']:.4f}\n")
            f.write(f"- **Positive-Month Share:** {portfolio_admitted_bh['positive_month_share']:.2%}\n")
            f.write(f"- **Trades/Year:** {portfolio_admitted_bh['total_trades_per_year']:.1f}\n")
            f.write(f"- **Monthly Sharpe:** {portfolio_admitted_bh['monthly_sharpe']:.4f}\n")
            f.write(f"- **States:** {portfolio_admitted_bh['n_states']}\n")
            f.write(f"- **Symbols:** {portfolio_admitted_bh['n_symbols']}\n")
            f.write(f"- **Families:** {portfolio_admitted_bh['n_families']}\n")
        else:
            f.write("No BH-significant admitted states.\n")

        f.write("\n")

        # Portfolio block: capacity-passing (baseline)
        f.write("## Portfolio: Capacity-Passing States (Baseline)\n\n")
        if portfolio_capacity:
            f.write(f"- **Net Mean:** {portfolio_capacity['net_mean']:.4f}\n")
            f.write(f"- **Net LB95:** {portfolio_capacity['net_lb95']:.4f}\n")
            f.write(f"- **Positive-Month Share:** {portfolio_capacity['positive_month_share']:.2%}\n")
            f.write(f"- **Trades/Year:** {portfolio_capacity['total_trades_per_year']:.1f}\n")
            f.write(f"- **Monthly Sharpe:** {portfolio_capacity['monthly_sharpe']:.4f}\n")
            f.write(f"- **States:** {portfolio_capacity['n_states']}\n")
            f.write(f"- **Symbols:** {portfolio_capacity['n_symbols']}\n")
            f.write(f"- **Families:** {portfolio_capacity['n_families']}\n")
        else:
            f.write("No capacity-passing states.\n")

        f.write("\n")

        # Top admitted states by net_lb95
        f.write("## Top Admitted States (by Net LB95)\n\n")
        top_admitted = admitted_df.nlargest(15, "net_lb95")[
            ["symbol", "family", "bar_ticks", "state_id", "net_lb95", "positive_month_share", "n"]
        ]
        if len(top_admitted) > 0:
            f.write(top_admitted.to_markdown(index=False))
        else:
            f.write("No admitted states.\n")

        f.write("\n")

        # Decision readout
        f.write("## Decision Readout vs ADR 0005\n\n")
        f.write("**Target:** Portfolio net_lb95 > 0 and positive_month_share >= 0.6\n\n")

        if portfolio_admitted:
            target_met = (
                portfolio_admitted["net_lb95"] > 0
                and portfolio_admitted["positive_month_share"] >= 0.6
            )
            f.write(f"**Raw Admitted Portfolio:** {('PASS' if target_met else 'FAIL')}\n")
            f.write(f"  - Net LB95 > 0: {portfolio_admitted['net_lb95'] > 0}\n")
            f.write(f"  - Positive-month share >= 0.6: {portfolio_admitted['positive_month_share'] >= 0.6}\n\n")
        else:
            f.write("**Raw Admitted Portfolio:** FAIL (no states)\n\n")

        if portfolio_admitted_bh:
            target_met_bh = (
                portfolio_admitted_bh["net_lb95"] > 0
                and portfolio_admitted_bh["positive_month_share"] >= 0.6
            )
            f.write(f"**BH-Filtered Admitted Portfolio:** {('PASS' if target_met_bh else 'FAIL')}\n")
            f.write(f"  - Net LB95 > 0: {portfolio_admitted_bh['net_lb95'] > 0}\n")
            f.write(f"  - Positive-month share >= 0.6: {portfolio_admitted_bh['positive_month_share'] >= 0.6}\n")
        else:
            f.write("**BH-Filtered Admitted Portfolio:** FAIL (no states)\n")

    print(f"Wrote report to {args.out_report}")
    print("Done.")


if __name__ == "__main__":
    main()
