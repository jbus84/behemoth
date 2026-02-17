#!/usr/bin/env python3
"""Build markdown + figures for cluster early-warning WFO outputs."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]


def _load_required(analysis_dir: Path, prefix: str) -> dict[str, pd.DataFrame]:
    files = {
        "summary": analysis_dir / f"{prefix}_summary.csv",
        "folds": analysis_dir / f"{prefix}_folds.csv",
        "trades": analysis_dir / f"{prefix}_oos_trades.csv",
        "scored": analysis_dir / f"{prefix}_oos_scored_trades.csv",
        "mc_summary": analysis_dir / f"{prefix}_mc_daily_summary.csv",
    }
    out = {}
    for k, p in files.items():
        if p.exists():
            out[k] = pd.read_csv(p)
        else:
            out[k] = pd.DataFrame()
    if out["summary"].empty or out["folds"].empty:
        raise FileNotFoundError(f"Missing required artifacts for prefix={prefix} in {analysis_dir}")
    return out


def _daily_curve(df: pd.DataFrame) -> pd.Series:
    if df.empty:
        return pd.Series(dtype="float64")
    dt = pd.to_datetime(df["exit_ts"], unit="ns", utc=True).dt.normalize()
    daily = df.assign(day=dt).groupby("day")["pnl_bps"].sum().sort_index()
    idx = pd.date_range(daily.index.min(), daily.index.max(), freq="D", tz="UTC")
    return daily.reindex(idx, fill_value=0.0)


def _plot_fold_metrics(folds: pd.DataFrame, out_path: Path) -> None:
    d = folds.sort_values("year").copy()
    years = d["year"].astype(int).to_numpy()
    x = np.arange(len(years))

    fig, axes = plt.subplots(1, 2, figsize=(14, 5), constrained_layout=True)

    axes[0].bar(x - 0.2, d["base_worst_single_day_bps"] / 100.0, width=0.4, label="Baseline")
    axes[0].bar(x + 0.2, d["candidate_worst_single_day_bps"] / 100.0, width=0.4, label="Cluster EW")
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(years)
    axes[0].set_title("Worst Single Day by Fold")
    axes[0].set_ylabel("bps / 100")
    axes[0].legend(frameon=False)

    axes[1].plot(years, d["base_sharpe"], marker="o", label="Baseline")
    axes[1].plot(years, d["candidate_sharpe"], marker="o", label="Cluster EW")
    axes[1].set_title("Sharpe by Fold")
    axes[1].set_xlabel("Fold year")
    axes[1].set_ylabel("Sharpe")
    axes[1].legend(frameon=False)

    fig.savefig(out_path, dpi=220)
    plt.close(fig)


def _plot_precision_recall(folds: pd.DataFrame, out_path: Path) -> None:
    d = folds.sort_values("year").copy()
    fig, ax = plt.subplots(figsize=(9, 4.5), constrained_layout=True)
    ax.plot(d["year"], d["cluster_precision"], marker="o", label="Precision")
    ax.plot(d["year"], d["cluster_recall"], marker="o", label="Recall")
    ax.plot(d["year"], d["oos_hard_pass"].astype(int), marker="x", linestyle="--", label="OOS hard pass")
    ax.set_ylim(0.0, 1.05)
    ax.set_title("Cluster Detection Quality by Fold")
    ax.set_xlabel("Fold year")
    ax.set_ylabel("Rate")
    ax.legend(frameon=False)
    fig.savefig(out_path, dpi=220)
    plt.close(fig)


def _plot_gate_actions(scored: pd.DataFrame, out_path: Path) -> pd.DataFrame:
    if scored.empty:
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.text(0.5, 0.5, "No scored trades", ha="center", va="center")
        ax.axis("off")
        fig.savefig(out_path, dpi=220)
        plt.close(fig)
        return pd.DataFrame()

    g = (
        scored.groupby(["timeframe", "cluster_gate_action"], as_index=False)
        .size()
        .pivot(index="timeframe", columns="cluster_gate_action", values="size")
        .fillna(0.0)
    )
    for c in ["keep_full", "keep_half", "skip"]:
        if c not in g.columns:
            g[c] = 0.0
    g = g[["keep_full", "keep_half", "skip"]]

    fig, ax = plt.subplots(figsize=(9, 5), constrained_layout=True)
    x = np.arange(len(g.index))
    ax.bar(x, g["keep_full"], label="keep_full")
    ax.bar(x, g["keep_half"], bottom=g["keep_full"], label="keep_half")
    ax.bar(x, g["skip"], bottom=g["keep_full"] + g["keep_half"], label="skip")
    ax.set_xticks(x)
    ax.set_xticklabels(g.index.tolist())
    ax.set_title("Gate Actions by Timeframe")
    ax.set_ylabel("Trade count")
    ax.legend(frameon=False)
    fig.savefig(out_path, dpi=220)
    plt.close(fig)

    out = g.reset_index()
    out.columns.name = None
    return out


def _plot_mc_tail(mc_summary: pd.DataFrame, out_path: Path) -> None:
    if mc_summary.empty:
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.text(0.5, 0.5, "No MC summary", ha="center", va="center")
        ax.axis("off")
        fig.savefig(out_path, dpi=220)
        plt.close(fig)
        return

    d = mc_summary[mc_summary["variant"].isin(["baseline_causal", "cluster_ew_promoted"])].copy()
    if d.empty:
        d = mc_summary.copy()

    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5), constrained_layout=True)

    axes[0].bar(
        d["variant"],
        d["single_day_loss_bps_p95"],
        color=["#7f8c8d", "#1f77b4"][: len(d)],
    )
    axes[0].set_title("MC p95 Single-Day Loss")
    axes[0].set_ylabel("loss bps")

    axes[1].bar(
        d["variant"],
        d["annualized_bps_calendar_p50"],
        color=["#7f8c8d", "#1f77b4"][: len(d)],
    )
    axes[1].set_title("MC p50 Annualized bps")
    axes[1].set_ylabel("bps")

    fig.savefig(out_path, dpi=220)
    plt.close(fig)


def _plot_equity(trades: pd.DataFrame, out_path: Path) -> None:
    if trades.empty:
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.text(0.5, 0.5, "No trade data", ha="center", va="center")
        ax.axis("off")
        fig.savefig(out_path, dpi=220)
        plt.close(fig)
        return

    variants = ["baseline_causal", "cluster_ew_promoted"]
    fig, ax = plt.subplots(figsize=(11, 4.5), constrained_layout=True)
    for v in variants:
        sub = trades[trades["variant"] == v].copy()
        if sub.empty:
            continue
        d = _daily_curve(sub)
        if d.empty:
            continue
        ax.plot(d.index, np.cumsum(d.to_numpy(dtype=float)), label=v)
    ax.set_title("Cumulative Daily PnL (bps)")
    ax.set_ylabel("bps")
    ax.set_xlabel("Date")
    ax.legend(frameon=False)
    fig.savefig(out_path, dpi=220)
    plt.close(fig)


def _plot_decile_quality(scored: pd.DataFrame, out_path: Path) -> pd.DataFrame:
    if scored.empty or "cluster_trade_label" not in scored.columns:
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.text(0.5, 0.5, "No labeled scored trades", ha="center", va="center")
        ax.axis("off")
        fig.savefig(out_path, dpi=220)
        plt.close(fig)
        return pd.DataFrame()

    d = scored.copy()
    d = d[d["cluster_trade_label"].notna()].copy()
    if d.empty:
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.text(0.5, 0.5, "No labeled scored trades", ha="center", va="center")
        ax.axis("off")
        fig.savefig(out_path, dpi=220)
        plt.close(fig)
        return pd.DataFrame()

    d["cluster_trade_label"] = d["cluster_trade_label"].astype(int)
    d["decile"] = pd.qcut(d["p_cluster_bad"], q=10, labels=False, duplicates="drop")
    tab = d.groupby("decile", as_index=False).agg(
        n=("cluster_trade_label", "size"),
        bad_rate=("cluster_trade_label", "mean"),
        mean_p=("p_cluster_bad", "mean"),
    )

    fig, ax = plt.subplots(figsize=(9, 4.5), constrained_layout=True)
    ax.plot(tab["decile"], tab["bad_rate"], marker="o", label="Observed bad rate")
    ax.plot(tab["decile"], tab["mean_p"], marker="o", label="Mean predicted p")
    ax.set_title("Risk Decile Quality")
    ax.set_xlabel("Predicted risk decile (low to high)")
    ax.set_ylabel("Probability")
    ax.legend(frameon=False)
    fig.savefig(out_path, dpi=220)
    plt.close(fig)
    return tab


def _md_table(df: pd.DataFrame, cols: list[str]) -> str:
    sub = df[cols].copy()
    for c in sub.columns:
        if pd.api.types.is_bool_dtype(sub[c]):
            sub[c] = sub[c].map(lambda x: "True" if bool(x) else "False")
            continue
        if np.issubdtype(sub[c].dtype, np.number):
            if c == "year" or c.endswith("_year"):
                sub[c] = sub[c].map(lambda x: f"{int(x):d}" if pd.notna(x) else "")
            elif c == "trades" or c.endswith("_trades"):
                sub[c] = sub[c].map(lambda x: f"{int(x):,d}" if pd.notna(x) else "")
            elif c in {"t1", "t2"}:
                sub[c] = sub[c].map(lambda x: f"{x:.2f}" if pd.notna(x) else "")
            else:
                sub[c] = sub[c].map(lambda x: f"{x:,.3f}" if pd.notna(x) else "")
    return sub.to_markdown(index=False)


def main() -> None:
    p = argparse.ArgumentParser(description="Build cluster EW markdown report + figures")
    p.add_argument("--analysis-dir", default=str(ROOT / "data" / "analysis"))
    p.add_argument("--prefix", required=True)
    p.add_argument(
        "--report-path",
        default=str(ROOT / "docs" / "analysis" / "cluster_earlywarning_report.md"),
    )
    p.add_argument(
        "--fig-dir",
        default=str(ROOT / "docs" / "figures" / "cluster_earlywarning"),
    )
    p.add_argument(
        "--tables-dir",
        default=str(ROOT / "data" / "analysis" / "cluster_earlywarning_report_tables"),
    )
    args = p.parse_args()

    analysis_dir = Path(args.analysis_dir)
    report_path = Path(args.report_path)
    fig_dir = Path(args.fig_dir)
    tables_dir = Path(args.tables_dir)

    fig_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    data = _load_required(analysis_dir, args.prefix)
    summary = data["summary"]
    folds = data["folds"]
    trades = data["trades"]
    scored = data["scored"]
    mc_summary = data["mc_summary"]

    # If multi-mix file is provided, report first mix only for visuals.
    mix_ids = sorted(summary["mix_id"].astype(str).unique().tolist())
    mix_id = mix_ids[0]
    summary = summary[summary["mix_id"] == mix_id].copy()
    folds = folds[folds["mix_id"] == mix_id].copy()
    trades = trades[trades["mix_id"] == mix_id].copy() if not trades.empty and "mix_id" in trades.columns else trades
    scored = scored[scored["mix_id"] == mix_id].copy() if not scored.empty and "mix_id" in scored.columns else scored
    mc_summary = mc_summary[mc_summary["mix_id"] == mix_id].copy() if not mc_summary.empty and "mix_id" in mc_summary.columns else mc_summary

    fig_fold = fig_dir / "fig01_fold_metrics.png"
    fig_pr = fig_dir / "fig02_precision_recall.png"
    fig_gate = fig_dir / "fig03_gate_actions.png"
    fig_mc = fig_dir / "fig04_mc_tail.png"
    fig_eq = fig_dir / "fig05_equity_curve.png"
    fig_dec = fig_dir / "fig06_decile_quality.png"

    _plot_fold_metrics(folds, fig_fold)
    _plot_precision_recall(folds, fig_pr)
    gate_tab = _plot_gate_actions(scored, fig_gate)
    _plot_mc_tail(mc_summary, fig_mc)
    _plot_equity(trades, fig_eq)
    dec_tab = _plot_decile_quality(scored, fig_dec)

    gate_tab.to_csv(tables_dir / f"{args.prefix}_gate_actions_by_timeframe.csv", index=False)
    dec_tab.to_csv(tables_dir / f"{args.prefix}_decile_quality.csv", index=False)
    summary.to_csv(tables_dir / f"{args.prefix}_summary_slice.csv", index=False)
    folds.to_csv(tables_dir / f"{args.prefix}_folds_slice.csv", index=False)

    rel_fig = Path("../figures") / Path(args.fig_dir).name

    summary_main = summary[summary["variant"].isin(["baseline_causal", "cluster_ew_promoted"])].copy()

    lines = []
    lines.append(f"# Cluster Early-Warning Report ({mix_id})")
    lines.append("")
    lines.append(f"- Generated from prefix: `{args.prefix}`")
    lines.append(f"- Mix in focus: `{mix_id}`")
    lines.append("")
    lines.append("## Headline Summary")
    lines.append(_md_table(summary_main, [
        "variant",
        "trades",
        "mean_pnl_per_trade_bps",
        "sharpe",
        "annualized_bps_calendar",
        "cagr",
        "worst_single_day_bps",
        "max_daily_dd_bps",
    ]))
    lines.append("")
    lines.append("## Fold Breakdown")
    lines.append(_md_table(folds, [
        "year",
        "t1",
        "t2",
        "base_mean_pnl_per_trade_bps",
        "candidate_mean_pnl_per_trade_bps",
        "base_sharpe",
        "candidate_sharpe",
        "base_worst_single_day_bps",
        "candidate_worst_single_day_bps",
        "cluster_precision",
        "cluster_recall",
        "oos_hard_pass",
    ]))
    lines.append("")
    lines.append("## Figures")
    lines.append("")
    lines.append(f"![Fold Metrics]({rel_fig}/fig01_fold_metrics.png)")
    lines.append("")
    lines.append(f"![Precision Recall]({rel_fig}/fig02_precision_recall.png)")
    lines.append("")
    lines.append(f"![Gate Actions]({rel_fig}/fig03_gate_actions.png)")
    lines.append("")
    lines.append(f"![MC Tail]({rel_fig}/fig04_mc_tail.png)")
    lines.append("")
    lines.append(f"![Equity Curve]({rel_fig}/fig05_equity_curve.png)")
    lines.append("")
    lines.append(f"![Decile Quality]({rel_fig}/fig06_decile_quality.png)")
    lines.append("")
    lines.append("## Interpretation Notes")
    lines.append("- `worst_single_day_bps` is the single worst daily PnL (non-cumulative).")
    lines.append("- `max_daily_dd_bps` is cumulative drawdown measured on the daily equity curve.")
    lines.append("- `cluster_precision/recall` are computed on labeled short-leg trades in each OOS fold.")
    lines.append("- `oos_hard_pass` requires DD improvement plus return/trade floors from the plan.")

    report_path.write_text("\n".join(lines), encoding="utf-8")

    print("Saved report:")
    print(f"- {report_path}")
    print("Saved figures:")
    for pth in [fig_fold, fig_pr, fig_gate, fig_mc, fig_eq, fig_dec]:
        print(f"- {pth}")
    print("Saved tables:")
    print(f"- {tables_dir / (args.prefix + '_summary_slice.csv')}")
    print(f"- {tables_dir / (args.prefix + '_folds_slice.csv')}")
    print(f"- {tables_dir / (args.prefix + '_gate_actions_by_timeframe.csv')}")
    print(f"- {tables_dir / (args.prefix + '_decile_quality.csv')}")


if __name__ == "__main__":
    main()
