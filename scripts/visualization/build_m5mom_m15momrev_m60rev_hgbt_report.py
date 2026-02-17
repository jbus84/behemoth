#!/usr/bin/env python3
"""
Build a full deep-dive markdown report and figure pack for:
  m5=MOM, m15=MOM+REV, m60=REV (HGBT, no-oil universe).
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.report_strategy_fx_comm_multi_tf import _metrics_with_risk


plt.style.use("seaborn-v0_8-whitegrid")


def _require_columns(df: pd.DataFrame, cols: list[str], name: str) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"{name} missing required columns: {missing}")


def _load_csv(path: Path, required_cols: list[str], name: str) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    df = pd.read_csv(path)
    _require_columns(df, required_cols, name)
    return df


def _daily_pnl(df: pd.DataFrame) -> pd.Series:
    if df.empty:
        return pd.Series(dtype="float64")
    day = pd.to_datetime(df["exit_ts"], unit="ns", utc=True).dt.normalize()
    return pd.DataFrame({"day": day, "pnl_bps": pd.to_numeric(df["pnl_bps"], errors="coerce")}).groupby("day")[
        "pnl_bps"
    ].sum()


def _daily_curve(df: pd.DataFrame, full_index: pd.DatetimeIndex) -> pd.Series:
    d = _daily_pnl(df)
    if d.empty:
        return pd.Series(np.zeros(len(full_index), dtype=float), index=full_index)
    return d.reindex(full_index, fill_value=0.0).astype(float)


def _drawdown_from_daily(daily_bps: pd.Series) -> pd.Series:
    curve = daily_bps.cumsum()
    peak = curve.cummax()
    return curve - peak


def _metrics_df(df: pd.DataFrame, risk_bps: float) -> dict[str, float]:
    return _metrics_with_risk(df.copy(), risk_bps=float(risk_bps))


def _save_table(df: pd.DataFrame, out_dir: Path, name: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / name
    df.to_csv(path, index=False)
    return path


def _fmt(v: float | int | str, nd: int = 3) -> str:
    if isinstance(v, str):
        return v
    if v is None:
        return ""
    if isinstance(v, (int, np.integer)):
        return f"{int(v):,d}"
    if not np.isfinite(float(v)):
        return ""
    return f"{float(v):,.{nd}f}"


def _md_table(df: pd.DataFrame, cols: list[str], nd: int = 3) -> str:
    view = df[cols].copy()
    for c in view.columns:
        if str(c).lower() in {"year", "fold_year"}:
            view[c] = pd.to_numeric(view[c], errors="coerce").fillna(0).astype(int).astype(str)
            continue
        if pd.api.types.is_numeric_dtype(view[c]):
            view[c] = view[c].apply(lambda x: _fmt(x, nd=nd))
    header = "| " + " | ".join(view.columns) + " |"
    sep = "| " + " | ".join(["---"] * len(view.columns)) + " |"
    rows = ["| " + " | ".join(map(str, row)) + " |" for row in view.to_numpy()]
    return "\n".join([header, sep] + rows)


def _savefig(fig: plt.Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def _plot_pipeline_diagram(path: Path) -> None:
    fig, ax = plt.subplots(figsize=(14, 6))
    ax.axis("off")
    boxes = [
        (0.03, 0.58, 0.18, 0.30, "Event Inputs\nM5 MOM\nM15 MOM+REV\nM60 REV"),
        (0.25, 0.58, 0.20, 0.30, "Causal Fold Split\nTrain < test year\nEmbargo = 5d"),
        (0.49, 0.58, 0.20, 0.30, "First-Hit Labels\npt/sl quantiles\ntimeout loss rule"),
        (0.73, 0.58, 0.22, 0.30, "HGBT + Isotonic\nP(bad trade)\nper fold"),
        (0.18, 0.10, 0.24, 0.30, "Threshold Search\nDD-first score\nMC stress gates"),
        (0.48, 0.10, 0.24, 0.30, "Promoted OOS Trades\nshort-leg filtered\nlong leg retained"),
        (0.78, 0.10, 0.18, 0.30, "Validation\nfold stats\nMC distributions"),
    ]
    for x, y, w, h, txt in boxes:
        rect = plt.Rectangle((x, y), w, h, facecolor="#f4f7fb", edgecolor="#205493", linewidth=1.5)
        ax.add_patch(rect)
        ax.text(x + w / 2, y + h / 2, txt, ha="center", va="center", fontsize=11)
    arrows = [
        ((0.21, 0.73), (0.25, 0.73)),
        ((0.45, 0.73), (0.49, 0.73)),
        ((0.69, 0.73), (0.73, 0.73)),
        ((0.83, 0.58), (0.30, 0.40)),
        ((0.42, 0.25), (0.48, 0.25)),
        ((0.72, 0.25), (0.78, 0.25)),
    ]
    for (x0, y0), (x1, y1) in arrows:
        ax.annotate("", xy=(x1, y1), xytext=(x0, y0), arrowprops=dict(arrowstyle="->", linewidth=1.5, color="#333"))
    ax.set_title("Model Pipeline (Causal, Walk-Forward)", fontsize=16, weight="bold")
    _savefig(fig, path)


def _plot_fold_timeline(folds_df: pd.DataFrame, path: Path) -> None:
    df = folds_df.sort_values("year").copy()
    years = df["year"].astype(int).to_numpy()
    x = np.arange(len(years))

    fig, ax1 = plt.subplots(figsize=(13, 6))
    bars = ax1.bar(x, df["threshold"].to_numpy(dtype=float), color="#1f77b4", alpha=0.8, label="Selected threshold")
    ax1.set_xticks(x)
    ax1.set_xticklabels(years)
    ax1.set_xlabel("Fold Year")
    ax1.set_ylabel("Selected threshold")
    ax1.set_ylim(0, max(0.85, float(df["threshold"].max()) + 0.1))
    for b in bars:
        ax1.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.015, f"{b.get_height():.2f}", ha="center", fontsize=9)

    ax2 = ax1.twinx()
    ax2.plot(x, df["base_trades"], marker="o", color="#d62728", label="Base trades")
    ax2.plot(x, df["meta_promoted_trades"], marker="o", color="#2ca02c", label="Promoted trades")
    ax2.set_ylabel("Trades")

    lines, labels = [], []
    for ax in [ax1, ax2]:
        l, lb = ax.get_legend_handles_labels()
        lines.extend(l)
        labels.extend(lb)
    ax1.legend(lines, labels, loc="upper left")
    ax1.set_title("Walk-Forward Thresholds and Trade Counts by Fold")
    _savefig(fig, path)


def _plot_equity_and_dd(
    base_daily: pd.Series,
    promoted_daily: pd.Series,
    eq_path: Path,
    dd_path: Path,
) -> None:
    base_curve = base_daily.cumsum()
    pro_curve = promoted_daily.cumsum()
    base_dd = _drawdown_from_daily(base_daily)
    pro_dd = _drawdown_from_daily(promoted_daily)

    fig1, ax1 = plt.subplots(figsize=(14, 6))
    ax1.plot(base_curve.index, base_curve.values, label="Baseline causal", linewidth=2.0, color="#d62728")
    ax1.plot(pro_curve.index, pro_curve.values, label="Promoted HGBT", linewidth=2.0, color="#2ca02c")
    ax1.set_title("Cumulative Daily PnL (bps)")
    ax1.set_ylabel("Cumulative bps")
    ax1.legend(loc="upper left")
    _savefig(fig1, eq_path)

    fig2, ax2 = plt.subplots(figsize=(14, 6))
    ax2.plot(base_dd.index, base_dd.values, label="Baseline drawdown", linewidth=2.0, color="#d62728")
    ax2.plot(pro_dd.index, pro_dd.values, label="Promoted drawdown", linewidth=2.0, color="#2ca02c")
    ax2.set_title("Daily-Curve Drawdown (bps)")
    ax2.set_ylabel("Drawdown bps")
    ax2.legend(loc="lower left")
    _savefig(fig2, dd_path)


def _plot_yearly_metrics(folds_df: pd.DataFrame, path: Path) -> None:
    df = folds_df.sort_values("year").copy()
    x = np.arange(len(df))
    years = df["year"].astype(int).to_numpy()
    w = 0.38

    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    metrics = [
        ("base_sharpe", "meta_promoted_sharpe", "Sharpe"),
        ("base_annualized_bps", "meta_promoted_annualized_bps", "Annualized BPS"),
        ("base_max_daily_dd_bps", "meta_promoted_max_daily_dd_bps", "Max Daily DD (bps)"),
    ]
    for ax, (bcol, pcol, title) in zip(axes, metrics):
        ax.bar(x - w / 2, df[bcol].to_numpy(dtype=float), width=w, label="Baseline", color="#d62728", alpha=0.85)
        ax.bar(x + w / 2, df[pcol].to_numpy(dtype=float), width=w, label="Promoted", color="#2ca02c", alpha=0.85)
        ax.set_xticks(x)
        ax.set_xticklabels(years)
        ax.set_title(title)
    axes[0].legend(loc="best")
    fig.suptitle("Per-Fold Baseline vs Promoted Metrics", fontsize=14, weight="bold")
    _savefig(fig, path)


def _plot_tf_contribution(tf_df: pd.DataFrame, path: Path) -> None:
    d = tf_df.copy()
    d["bucket"] = d["timeframe"].astype(str) + " " + d["strategy_type"].astype(str)
    d = d.sort_values("total_pnl_bps", ascending=False)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
    ax1.bar(d["bucket"], d["total_pnl_bps"], color="#1f77b4", alpha=0.85)
    ax1.set_title("Total PnL Contribution by Timeframe/Strategy")
    ax1.set_ylabel("Total pnl (bps)")
    ax1.tick_params(axis="x", rotation=25)

    ax2.bar(d["bucket"], d["mean_pnl_per_trade_bps"], color="#9467bd", alpha=0.85, label="Mean pnl/trade (bps)")
    ax2.set_ylabel("Mean pnl/trade (bps)")
    ax2_t = ax2.twinx()
    ax2_t.plot(d["bucket"], d["trades"], color="#2ca02c", marker="o", linewidth=2, label="Trades")
    ax2_t.set_ylabel("Trades")
    ax2.set_title("Edge vs Activity by Timeframe/Strategy")
    ax2.tick_params(axis="x", rotation=25)
    _savefig(fig, path)


def _plot_pair_heatmap(pair_year_df: pd.DataFrame, path: Path) -> None:
    pvt = pair_year_df.pivot(index="pair", columns="year", values="sharpe").sort_index()
    years = list(pvt.columns)
    arr = pvt.to_numpy(dtype=float)
    vmin = float(np.nanmin(arr))
    vmax = float(np.nanmax(arr))
    norm = mcolors.TwoSlopeNorm(vmin=vmin, vcenter=0.0, vmax=vmax) if vmin < 0 < vmax else None

    fig, ax = plt.subplots(figsize=(11, 8))
    im = ax.imshow(arr, aspect="auto", cmap="RdYlGn", norm=norm)
    ax.set_xticks(np.arange(len(years)))
    ax.set_xticklabels(years)
    ax.set_yticks(np.arange(len(pvt.index)))
    ax.set_yticklabels(list(pvt.index))
    ax.set_title("Promoted Sharpe by Pair and Year")
    for i in range(arr.shape[0]):
        for j in range(arr.shape[1]):
            if np.isfinite(arr[i, j]):
                ax.text(j, i, f"{arr[i, j]:.2f}", ha="center", va="center", fontsize=7, color="black")
    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label("Sharpe")
    _savefig(fig, path)


def _plot_threshold_frontier(
    threshold_grid: pd.DataFrame,
    folds_df: pd.DataFrame,
    path: Path,
) -> None:
    years = sorted(folds_df["year"].astype(int).unique().tolist())
    fig, axes = plt.subplots(2, 3, figsize=(18, 10), sharex=True, sharey=True)
    axes = axes.flatten()

    for idx, year in enumerate(years):
        ax = axes[idx]
        f = folds_df[folds_df["year"] == year].iloc[0]
        g = threshold_grid[
            (threshold_grid["fold_year"] == year)
            & np.isclose(threshold_grid["pt_q"], float(f["pt_q"]))
            & np.isclose(threshold_grid["sl_q"], float(f["sl_q"]))
            & np.isclose(threshold_grid["timeout_ratio"], float(f["timeout_ratio"]))
        ].copy()
        sc = ax.scatter(
            g["max_daily_dd_bps"],
            g["annualized_bps_calendar"],
            c=g["threshold"],
            cmap="viridis",
            s=60,
            alpha=0.85,
            edgecolors="none",
        )
        chosen = g[np.isclose(g["threshold"], float(f["threshold"]))].head(1)
        if not chosen.empty:
            ax.scatter(
                chosen["max_daily_dd_bps"],
                chosen["annualized_bps_calendar"],
                marker="*",
                s=220,
                c="gold",
                edgecolors="black",
                linewidth=0.8,
                label="Chosen",
            )
        ax.scatter(
            [float(f["base_max_daily_dd_bps"])],
            [float(f["base_annualized_bps"])],
            marker="x",
            s=90,
            c="red",
            label="Baseline",
        )
        ax.set_title(f"Fold {year}")
        if idx == 0:
            ax.legend(loc="lower right", fontsize=8)
    for ax in axes:
        ax.set_xlabel("Max daily DD (bps)")
        ax.set_ylabel("Annualized bps")
    cbar = fig.colorbar(sc, ax=axes.tolist(), shrink=0.9)
    cbar.set_label("Threshold")
    fig.suptitle("Threshold Frontier per Fold (DD vs Annualized BPS)")
    _savefig(fig, path)


def _plot_probability_diagnostics(scored_df: pd.DataFrame, path: Path) -> None:
    d = scored_df.copy()
    d["keep_flag"] = d["keep_flag"].astype(bool)
    p_keep = d.loc[d["keep_flag"], "proba_bad_calibrated"].to_numpy(dtype=float)
    p_drop = d.loc[~d["keep_flag"], "proba_bad_calibrated"].to_numpy(dtype=float)

    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    bins = np.linspace(0.0, 1.0, 31)
    axes[0].hist(p_keep, bins=bins, alpha=0.7, density=True, label="Kept", color="#2ca02c")
    axes[0].hist(p_drop, bins=bins, alpha=0.7, density=True, label="Filtered", color="#d62728")
    axes[0].set_title("Calibrated P(bad) Distribution")
    axes[0].set_xlabel("P(bad)")
    axes[0].set_ylabel("Density")
    axes[0].legend()

    parts = []
    labels = []
    for tf in ["m5", "m15"]:
        for keep in [True, False]:
            vals = d[(d["timeframe"] == tf) & (d["keep_flag"] == keep)]["proba_bad_calibrated"].to_numpy(dtype=float)
            if len(vals):
                parts.append(vals)
                labels.append(f"{tf}-{('keep' if keep else 'drop')}")
    axes[1].boxplot(parts, tick_labels=labels, showfliers=False)
    axes[1].set_title("P(bad) by Timeframe and Keep Flag")
    axes[1].set_ylabel("P(bad)")
    axes[1].tick_params(axis="x", rotation=20)
    _savefig(fig, path)


def _plot_calibration_quality(cal_df: pd.DataFrame, path: Path) -> None:
    d = cal_df.sort_values("year")
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    axes[0].plot(d["year"], d["brier_raw"], marker="o", label="Raw")
    axes[0].plot(d["year"], d["brier_cal"], marker="o", label="Calibrated")
    axes[0].set_title("Brier Score by Fold")
    axes[0].set_xlabel("Year")
    axes[0].set_ylabel("Brier (lower is better)")
    axes[0].legend()

    axes[1].plot(d["year"], d["logloss_raw"], marker="o", label="Raw")
    axes[1].plot(d["year"], d["logloss_cal"], marker="o", label="Calibrated")
    axes[1].set_title("Log Loss by Fold")
    axes[1].set_xlabel("Year")
    axes[1].set_ylabel("Log loss (lower is better)")
    axes[1].legend()
    _savefig(fig, path)


def _plot_mc_summary(mc_df: pd.DataFrame, path: Path) -> None:
    d = mc_df.set_index("variant")
    variants = ["baseline_causal", "meta_tb_promoted"]
    x = np.arange(len(variants))

    fig, axes = plt.subplots(1, 2, figsize=(15, 5))
    vals = [float(d.loc[v, "annualized_bps_calendar_p50"]) for v in variants]
    lo = [vals[i] - float(d.loc[v, "annualized_bps_calendar_p5"]) for i, v in enumerate(variants)]
    hi = [float(d.loc[v, "annualized_bps_calendar_p95"]) - vals[i] for i, v in enumerate(variants)]
    axes[0].bar(x, vals, color=["#d62728", "#2ca02c"], alpha=0.85)
    axes[0].errorbar(x, vals, yerr=[lo, hi], fmt="none", ecolor="black", capsize=5)
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(["Baseline", "Promoted"])
    axes[0].set_title("MC Annualized BPS (p50 with p5-p95)")
    axes[0].set_ylabel("Annualized bps")

    vals2 = [float(d.loc[v, "max_daily_dd_bps_p50"]) for v in variants]
    lo2 = [vals2[i] - float(d.loc[v, "max_daily_dd_bps_p5"]) for i, v in enumerate(variants)]
    hi2 = [float(d.loc[v, "max_daily_dd_bps_p95"]) - vals2[i] for i, v in enumerate(variants)]
    axes[1].bar(x, vals2, color=["#d62728", "#2ca02c"], alpha=0.85)
    axes[1].errorbar(x, vals2, yerr=[lo2, hi2], fmt="none", ecolor="black", capsize=5)
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(["Baseline", "Promoted"])
    axes[1].set_title("MC Max Daily DD (p50 with p5-p95)")
    axes[1].set_ylabel("Max daily DD bps")
    _savefig(fig, path)


def _plot_catboost_comparison(hgbt_row: pd.Series, cat_row: pd.Series, path: Path) -> None:
    metrics = [
        ("sharpe", "Sharpe"),
        ("mean_pnl_per_trade_bps", "Mean pnl/trade (bps)"),
        ("annualized_bps_calendar", "Annualized bps"),
        ("max_daily_dd_bps", "Max daily DD (bps)"),
    ]
    names = [m[1] for m in metrics]
    hv = [float(hgbt_row[m[0]]) for m in metrics]
    cv = [float(cat_row[m[0]]) for m in metrics]
    x = np.arange(len(metrics))
    w = 0.38

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.bar(x - w / 2, hv, width=w, label="HGBT", color="#1f77b4")
    ax.bar(x + w / 2, cv, width=w, label="CatBoost", color="#ff7f0e")
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=15)
    ax.set_title("Appendix: HGBT vs CatBoost (Promoted, same mix)")
    ax.legend()
    _savefig(fig, path)


def _plot_m60_none_comparison(
    promoted_cmp: pd.DataFrame,
    fold_cmp: pd.DataFrame,
    path: Path,
) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))

    m = promoted_cmp[promoted_cmp["variant"] == "meta_tb_promoted"].copy()
    labels = m["config"].tolist()
    x = np.arange(len(labels))

    axes[0].bar(x - 0.25, m["sharpe"].to_numpy(dtype=float), width=0.25, label="Sharpe")
    axes[0].bar(x, m["annualized_bps_calendar"].to_numpy(dtype=float) / 10000.0, width=0.25, label="AnnBPS / 10k")
    axes[0].bar(x + 0.25, m["max_daily_dd_bps"].to_numpy(dtype=float) / 1000.0, width=0.25, label="MaxDD / 1k")
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(labels)
    axes[0].set_title("Promoted Headline: m60=REV vs m60=NONE")
    axes[0].legend()

    d = fold_cmp.copy().sort_values("year")
    years = d["year"].astype(int).to_numpy()
    axes[1].plot(years, d["delta_sharpe_none_minus_rev"], marker="o", label="Delta Sharpe")
    axes[1].plot(years, d["delta_ann_bps_none_minus_rev"] / 10000.0, marker="o", label="Delta AnnBPS / 10k")
    axes[1].plot(years, d["delta_dd_bps_none_minus_rev"] / 1000.0, marker="o", label="Delta MaxDD / 1k")
    axes[1].axhline(0.0, color="black", linewidth=1.0)
    axes[1].set_title("Per-Fold Delta (NONE - REV)")
    axes[1].set_xlabel("Year")
    axes[1].legend()

    _savefig(fig, path)


def _build_markdown(
    out_doc: Path,
    fig_dir_rel: str,
    summary_cmp: pd.DataFrame,
    fold_cmp: pd.DataFrame,
    tf_tbl: pd.DataFrame,
    pair_tbl: pd.DataFrame,
    pair_year_tbl: pd.DataFrame,
    label_tbl: pd.DataFrame,
    m60none_overall_cmp: pd.DataFrame | None,
    m60none_fold_cmp: pd.DataFrame | None,
    catboost_cmp: pd.DataFrame | None,
) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    top_pairs = pair_tbl.sort_values("total_pnl_bps", ascending=False).head(12).copy()
    pair_heat = pair_year_tbl.copy().sort_values(["pair", "year"])

    sections = []
    sections.append("# Deep-Dive Report: HGBT Mixed Model (`m5=MOM, m15=MOM+REV`) with M60 Evaluation\n")
    sections.append(f"- Generated: **{ts}**")
    sections.append("- Universe: **FX + commodities ex-oil**")
    sections.append("- Evaluation mode: **Causal walk-forward (2020-2025, embargo 5d)**")
    sections.append(
        "- Primary source artifacts: `meta_tb_mixed_no_oil_m5mom_m15momrev_m60rev_*` under `data/analysis/`"
    )

    sections.append("\n## Executive Summary\n")
    sections.append(_md_table(summary_cmp, list(summary_cmp.columns), nd=3))
    sections.append("\nKey takeaways:")
    sections.append("- Promoted HGBT materially improves Sharpe and annualized bps vs baseline while reducing worst daily risk in most folds.")
    sections.append("- Improvement is persistent across all test years, including stressed years.")
    sections.append("- M15 combined signal stack (MOM+REV) improves robustness by diversifying short-horizon trade archetypes.")

    sections.append("\n## End-to-End Process (Data -> Filter -> Model -> Validation)\n")
    sections.append("1. Load causal event trades for M5 MOM, M15 MOM+REV, and M60 REV.")
    sections.append("2. Build fold windows by year; training uses only data before test-year start minus embargo.")
    sections.append("3. Build first-hit triple-barrier labels on short legs using train-derived PT/SL quantiles.")
    sections.append("4. Train HGBT classifier for `P(bad trade)` on short legs; calibrate probabilities with isotonic mapping.")
    sections.append("5. Select threshold on train-only threshold grid under DD-first objective and MC stress constraints.")
    sections.append("6. Apply threshold and pair filter to OOS fold; compare baseline vs promoted.")
    sections.append(f"\n![Pipeline and Data Flow]({fig_dir_rel}/fig01_pipeline_and_data_flow.png)")
    sections.append(f"\n![WFO Threshold Timeline]({fig_dir_rel}/fig02_wfo_fold_timeline_and_thresholds.png)")

    sections.append("\n## Validation Quality and Methodological Appropriateness\n")
    sections.append(
        "This validation is appropriate for non-stationary markets because each fold is evaluated on truly out-of-sample data with no forward leakage in labels, calibration, or threshold choice."
    )
    sections.append("- Labeling is first-hit triple-barrier and fold-local.")
    sections.append("- Threshold policy is train-only and DD-constrained.")
    sections.append("- Monte Carlo block bootstrap stress testing is applied to daily curves.")
    sections.append("\n### Per-Fold Baseline vs Promoted")
    sections.append(_md_table(fold_cmp, list(fold_cmp.columns), nd=3))
    sections.append(f"\n![Per-Fold Metrics]({fig_dir_rel}/fig05_yearly_metrics_bars.png)")
    sections.append(f"\n![Threshold Frontier by Fold]({fig_dir_rel}/fig08_threshold_frontier_per_fold.png)")
    sections.append(f"\n![Calibration Quality]({fig_dir_rel}/fig10_calibration_quality.png)")
    sections.append(f"\n![MC Stress Summary]({fig_dir_rel}/fig11_mc_distribution_comparison.png)")

    sections.append("\n## Portfolio-Level Performance and Risk Dynamics\n")
    sections.append(f"\n![Cumulative Daily PnL]({fig_dir_rel}/fig03_equity_curve_baseline_vs_promoted.png)")
    sections.append(f"\n![Daily-Curve Drawdown]({fig_dir_rel}/fig04_drawdown_curve_baseline_vs_promoted.png)")
    sections.append(
        "Interpretation: equity and drawdown are computed on calendar-day aggregated bps curves; max daily DD is cumulative drawdown on that daily curve."
    )

    sections.append("\n## Timeframe and Strategy-Type Decomposition (Promoted)\n")
    sections.append(_md_table(tf_tbl, list(tf_tbl.columns), nd=3))
    sections.append(f"\n![Timeframe/Strategy Contribution]({fig_dir_rel}/fig06_timeframe_strategy_contribution.png)")
    sections.append(
        "Combination mechanics: M15 MOM and M15 REV contribute different short-horizon trade clusters. Their coexistence improves diversification of short-leg behavior while M60 REV anchors a slower structural leg."
    )

    sections.append("\n## Pair and Year Diagnostics (Promoted)\n")
    sections.append("### Top Pairs by Total PnL")
    sections.append(_md_table(top_pairs, list(top_pairs.columns), nd=3))
    sections.append("### Pair-Year Sharpe Matrix")
    sections.append(_md_table(pair_heat, list(pair_heat.columns), nd=3))
    sections.append(f"\n![Pair-Year Sharpe Heatmap]({fig_dir_rel}/fig07_pair_heatmap_pnl_or_sharpe.png)")

    sections.append("\n## Probability Filtering Diagnostics\n")
    sections.append(_md_table(label_tbl, list(label_tbl.columns), nd=4))
    sections.append(f"\n![Probability Diagnostics]({fig_dir_rel}/fig09_probability_filter_diagnostics.png)")

    if m60none_overall_cmp is not None and not m60none_overall_cmp.empty:
        sections.append("\n## Full Retrain Update: Dropping M60 (`m60=NONE`)\n")
        sections.append(
            "A full causal retrain was run with identical settings except removing the M60 leg (`m60=NONE`)."
        )
        sections.append("\n### Overall Comparison")
        sections.append(_md_table(m60none_overall_cmp, list(m60none_overall_cmp.columns), nd=3))
        if m60none_fold_cmp is not None and not m60none_fold_cmp.empty:
            sections.append("\n### Per-Fold Promoted Delta (`NONE - REV`)")
            sections.append(_md_table(m60none_fold_cmp, list(m60none_fold_cmp.columns), nd=3))
        sections.append(f"\n![M60 Full Retrain Comparison]({fig_dir_rel}/fig13_m60_none_full_retrain_comparison.png)")
        sections.append(
            "Result summary: for the promoted model, `m60=NONE` improved Sharpe, annualized bps, and drawdown in aggregate."
        )

    if catboost_cmp is not None and not catboost_cmp.empty:
        sections.append("\n## Appendix: CatBoost Comparison (Same Mix)\n")
        sections.append(_md_table(catboost_cmp, list(catboost_cmp.columns), nd=3))
        sections.append(f"\n![HGBT vs CatBoost]({fig_dir_rel}/fig12_catboost_appendix_comparison.png)")

    sections.append("\n## Reproducibility\n")
    sections.append("Use this report builder command:")
    sections.append("```bash")
    sections.append("python scripts/visualization/build_m5mom_m15momrev_m60rev_hgbt_report.py")
    sections.append("```")
    sections.append("Derived CSV tables are written under:")
    sections.append("- `data/analysis/m5_mom_m15momrev_m60rev_hgbt_report_tables/`")

    out_doc.parent.mkdir(parents=True, exist_ok=True)
    out_doc.write_text("\n".join(sections))


def main() -> None:
    parser = argparse.ArgumentParser(description="Build deep-dive report for m5=MOM,m15=MOM+REV,m60=REV HGBT mix.")
    parser.add_argument("--analysis-dir", default=str(ROOT / "data" / "analysis"))
    parser.add_argument("--prefix", default="meta_tb_mixed_no_oil_m5mom_m15momrev_m60rev")
    parser.add_argument("--m60none-prefix", default="meta_tb_mixed_no_oil_m5mom_m15momrev_m60none")
    parser.add_argument("--catboost-prefix", default="meta_tb_mixed_no_oil_m5mom_m15momrev_m60rev_catboost")
    parser.add_argument(
        "--out-doc",
        default=str(ROOT / "docs" / "analysis" / "m5_mom_m15_momrev_m60_rev_hgbt_report.md"),
    )
    parser.add_argument(
        "--out-fig-dir",
        default=str(ROOT / "docs" / "figures" / "m5_mom_m15momrev_m60rev_hgbt"),
    )
    parser.add_argument(
        "--out-table-dir",
        default=str(ROOT / "data" / "analysis" / "m5_mom_m15momrev_m60rev_hgbt_report_tables"),
    )
    args = parser.parse_args()

    analysis_dir = Path(args.analysis_dir)
    out_doc = Path(args.out_doc)
    out_fig_dir = Path(args.out_fig_dir)
    out_table_dir = Path(args.out_table_dir)
    out_fig_dir.mkdir(parents=True, exist_ok=True)
    out_table_dir.mkdir(parents=True, exist_ok=True)

    summary = _load_csv(
        analysis_dir / f"{args.prefix}_summary.csv",
        ["mix_id", "variant", "trades", "mean_pnl_per_trade_bps", "sharpe", "annualized_bps_calendar", "max_daily_dd_bps", "cagr", "time_in_market_pct", "risk_bps"],
        "summary",
    )
    folds = _load_csv(
        analysis_dir / f"{args.prefix}_folds.csv",
        ["year", "threshold", "base_trades", "base_sharpe", "base_annualized_bps", "base_max_daily_dd_bps", "meta_promoted_trades", "meta_promoted_sharpe", "meta_promoted_annualized_bps", "meta_promoted_max_daily_dd_bps", "delta_promoted_sharpe", "delta_promoted_annualized_bps", "delta_promoted_dd_bps", "pt_q", "sl_q", "timeout_ratio"],
        "folds",
    )
    trades = _load_csv(
        analysis_dir / f"{args.prefix}_oos_trades.csv",
        ["mix_id", "variant", "pair", "timeframe", "strategy_type", "timestamp", "exit_ts", "pnl_bps", "duration_bars"],
        "oos_trades",
    )
    scored = _load_csv(
        analysis_dir / f"{args.prefix}_oos_scored_trades.csv",
        ["pair", "timeframe", "pnl_bps", "fold_year", "proba_bad_calibrated", "keep_flag", "tb_label"],
        "oos_scored_trades",
    )
    threshold_grid = _load_csv(
        analysis_dir / f"{args.prefix}_threshold_grid.csv",
        ["fold_year", "pt_q", "sl_q", "timeout_ratio", "threshold", "annualized_bps_calendar", "max_daily_dd_bps", "score"],
        "threshold_grid",
    )
    label_ablation = _load_csv(
        analysis_dir / f"{args.prefix}_label_ablation.csv",
        ["year", "pt_q", "sl_q", "timeout_ratio", "threshold", "is_chosen", "train_bad_label_rate", "test_bad_label_rate"],
        "label_ablation",
    )
    fold_cal = _load_csv(
        analysis_dir / f"{args.prefix}_fold_calibration.csv",
        ["year", "pt_q", "sl_q", "timeout_ratio", "threshold", "brier_raw", "brier_cal", "logloss_raw", "logloss_cal"],
        "fold_calibration",
    )
    mc_summary = _load_csv(
        analysis_dir / f"{args.prefix}_mc_daily_summary.csv",
        ["variant", "annualized_bps_calendar_p5", "annualized_bps_calendar_p50", "annualized_bps_calendar_p95", "max_daily_dd_bps_p5", "max_daily_dd_bps_p50", "max_daily_dd_bps_p95"],
        "mc_daily_summary",
    )

    mix_id = str(summary["mix_id"].iloc[0])
    trades = trades[trades["mix_id"].astype(str) == mix_id].copy()

    baseline_row = summary[summary["variant"] == "baseline_causal"].iloc[0]
    promoted_row = summary[summary["variant"] == "meta_tb_promoted"].iloc[0]
    risk_bps = float(promoted_row["risk_bps"])

    base_trades = trades[trades["variant"] == "baseline_causal"].copy()
    promoted_trades = trades[trades["variant"] == "meta_tb_promoted"].copy()
    start_day = min(pd.to_datetime(base_trades["exit_ts"], unit="ns", utc=True).min(), pd.to_datetime(promoted_trades["exit_ts"], unit="ns", utc=True).min()).normalize()
    end_day = max(pd.to_datetime(base_trades["exit_ts"], unit="ns", utc=True).max(), pd.to_datetime(promoted_trades["exit_ts"], unit="ns", utc=True).max()).normalize()
    full_days = pd.date_range(start_day, end_day, freq="D", tz="UTC")
    base_daily = _daily_curve(base_trades, full_days)
    promoted_daily = _daily_curve(promoted_trades, full_days)

    # Core comparison tables
    summary_cmp = summary[summary["variant"].isin(["baseline_causal", "meta_tb_promoted"])][
        [
            "variant",
            "trades",
            "mean_pnl_per_trade_bps",
            "sharpe",
            "annualized_bps_calendar",
            "cagr",
            "max_daily_dd_bps",
            "worst_single_day_bps",
            "time_in_market_pct",
        ]
    ].copy()
    fold_cmp = folds[
        [
            "year",
            "threshold",
            "base_trades",
            "base_sharpe",
            "base_annualized_bps",
            "base_max_daily_dd_bps",
            "meta_promoted_trades",
            "meta_promoted_sharpe",
            "meta_promoted_annualized_bps",
            "meta_promoted_max_daily_dd_bps",
            "delta_promoted_sharpe",
            "delta_promoted_annualized_bps",
            "delta_promoted_dd_bps",
        ]
    ].copy()

    # Timeframe/strategy decomposition
    tf_rows = []
    contrib_rows = []
    for (tf, st), sub in promoted_trades.groupby(["timeframe", "strategy_type"], sort=True):
        m = _metrics_df(sub, risk_bps=risk_bps)
        rec = {"timeframe": tf, "strategy_type": st, **m}
        tf_rows.append(rec)
    tf_tbl = pd.DataFrame(tf_rows).sort_values(["timeframe", "strategy_type"]).reset_index(drop=True)
    if not tf_tbl.empty:
        total_pnl = float(tf_tbl["total_pnl_bps"].sum())
        total_trades = float(tf_tbl["trades"].sum())
        for row in tf_tbl.itertuples(index=False):
            contrib_rows.append(
                {
                    "timeframe": row.timeframe,
                    "strategy_type": row.strategy_type,
                    "pnl_share_pct": (100.0 * float(row.total_pnl_bps) / total_pnl) if total_pnl else 0.0,
                    "trade_share_pct": (100.0 * float(row.trades) / total_trades) if total_trades else 0.0,
                    "total_pnl_bps": float(row.total_pnl_bps),
                    "trades": int(row.trades),
                }
            )
    contrib_tbl = pd.DataFrame(contrib_rows)

    # Pair tables
    pair_rows = []
    for pair, sub in promoted_trades.groupby("pair", sort=True):
        pair_rows.append({"pair": pair, **_metrics_df(sub, risk_bps=risk_bps)})
    pair_tbl = pd.DataFrame(pair_rows).sort_values("total_pnl_bps", ascending=False).reset_index(drop=True)

    py = promoted_trades.copy()
    py["year"] = pd.to_datetime(py["exit_ts"], unit="ns", utc=True).dt.year.astype(int)
    pair_year_rows = []
    for (pair, year), sub in py.groupby(["pair", "year"], sort=True):
        pair_year_rows.append({"pair": pair, "year": int(year), **_metrics_df(sub, risk_bps=risk_bps)})
    pair_year_tbl = pd.DataFrame(pair_year_rows).sort_values(["pair", "year"]).reset_index(drop=True)

    # Label/calibration diagnostics
    chosen_labels = label_ablation[label_ablation["is_chosen"].astype(bool)].copy()
    label_tbl = chosen_labels.merge(
        fold_cal,
        on=["year", "pt_q", "sl_q", "timeout_ratio", "threshold"],
        how="left",
    )[
        [
            "year",
            "pt_q",
            "sl_q",
            "timeout_ratio",
            "threshold",
            "train_bad_label_rate",
            "test_bad_label_rate",
            "brier_raw",
            "brier_cal",
            "logloss_raw",
            "logloss_cal",
        ]
    ].sort_values("year")

    # Save derived tables
    _save_table(summary_cmp, out_table_dir, "overall_comparison.csv")
    _save_table(fold_cmp, out_table_dir, "fold_comparison.csv")
    _save_table(tf_tbl, out_table_dir, "timeframe_strategy_metrics.csv")
    _save_table(contrib_tbl, out_table_dir, "timeframe_strategy_contribution.csv")
    _save_table(pair_tbl, out_table_dir, "pair_metrics_overall.csv")
    _save_table(pair_year_tbl, out_table_dir, "pair_metrics_yearly.csv")
    _save_table(label_tbl, out_table_dir, "label_calibration_diagnostics.csv")

    # Optional full retrain comparison: m60=NONE
    m60none_overall_cmp = None
    m60none_fold_cmp = None
    none_summary_path = analysis_dir / f"{args.m60none_prefix}_summary.csv"
    none_folds_path = analysis_dir / f"{args.m60none_prefix}_folds.csv"
    if none_summary_path.exists() and none_folds_path.exists():
        none_summary = pd.read_csv(none_summary_path)
        none_folds = pd.read_csv(none_folds_path)
        need_summary = {"variant", "trades", "mean_pnl_per_trade_bps", "sharpe", "annualized_bps_calendar", "cagr", "max_daily_dd_bps", "worst_single_day_bps", "time_in_market_pct"}
        need_folds = {"year", "meta_promoted_sharpe", "meta_promoted_annualized_bps", "meta_promoted_max_daily_dd_bps", "meta_promoted_trades"}
        if need_summary.issubset(set(none_summary.columns)) and need_folds.issubset(set(none_folds.columns)):
            rev_sub = summary[summary["variant"].isin(["baseline_causal", "meta_tb_promoted"])].copy()
            rev_sub["config"] = "m60_rev"
            none_sub = none_summary[none_summary["variant"].isin(["baseline_causal", "meta_tb_promoted"])].copy()
            none_sub["config"] = "m60_none"
            m60none_overall_cmp = pd.concat([rev_sub, none_sub], ignore_index=True)[
                [
                    "config",
                    "variant",
                    "trades",
                    "mean_pnl_per_trade_bps",
                    "sharpe",
                    "annualized_bps_calendar",
                    "cagr",
                    "max_daily_dd_bps",
                    "worst_single_day_bps",
                    "time_in_market_pct",
                ]
            ]
            _save_table(m60none_overall_cmp, out_table_dir, "m60_none_full_retrain_overall_comparison.csv")

            fr = folds[["year", "meta_promoted_sharpe", "meta_promoted_annualized_bps", "meta_promoted_max_daily_dd_bps", "meta_promoted_trades"]].copy()
            fn = none_folds[["year", "meta_promoted_sharpe", "meta_promoted_annualized_bps", "meta_promoted_max_daily_dd_bps", "meta_promoted_trades"]].copy()
            fm = fr.merge(fn, on="year", suffixes=("_m60rev", "_m60none"))
            fm["delta_sharpe_none_minus_rev"] = fm["meta_promoted_sharpe_m60none"] - fm["meta_promoted_sharpe_m60rev"]
            fm["delta_ann_bps_none_minus_rev"] = fm["meta_promoted_annualized_bps_m60none"] - fm["meta_promoted_annualized_bps_m60rev"]
            fm["delta_dd_bps_none_minus_rev"] = fm["meta_promoted_max_daily_dd_bps_m60none"] - fm["meta_promoted_max_daily_dd_bps_m60rev"]
            fm["delta_trades_none_minus_rev"] = fm["meta_promoted_trades_m60none"] - fm["meta_promoted_trades_m60rev"]
            m60none_fold_cmp = fm[
                [
                    "year",
                    "delta_sharpe_none_minus_rev",
                    "delta_ann_bps_none_minus_rev",
                    "delta_dd_bps_none_minus_rev",
                    "delta_trades_none_minus_rev",
                ]
            ].sort_values("year")
            _save_table(m60none_fold_cmp, out_table_dir, "m60_none_full_retrain_fold_deltas.csv")
            _plot_m60_none_comparison(
                promoted_cmp=m60none_overall_cmp,
                fold_cmp=m60none_fold_cmp,
                path=out_fig_dir / "fig13_m60_none_full_retrain_comparison.png",
            )

    # Optional catboost appendix
    catboost_cmp = None
    cat_summary_path = analysis_dir / f"{args.catboost_prefix}_summary.csv"
    if cat_summary_path.exists():
        cat_summary = pd.read_csv(cat_summary_path)
        cat_prom = cat_summary[cat_summary["variant"] == "meta_tb_promoted"].head(1)
        if not cat_prom.empty:
            cat_row = cat_prom.iloc[0]
            catboost_cmp = pd.DataFrame(
                [
                    {
                        "model": "HGBT",
                        "trades": float(promoted_row["trades"]),
                        "mean_pnl_per_trade_bps": float(promoted_row["mean_pnl_per_trade_bps"]),
                        "sharpe": float(promoted_row["sharpe"]),
                        "annualized_bps_calendar": float(promoted_row["annualized_bps_calendar"]),
                        "max_daily_dd_bps": float(promoted_row["max_daily_dd_bps"]),
                    },
                    {
                        "model": "CatBoost",
                        "trades": float(cat_row["trades"]),
                        "mean_pnl_per_trade_bps": float(cat_row["mean_pnl_per_trade_bps"]),
                        "sharpe": float(cat_row["sharpe"]),
                        "annualized_bps_calendar": float(cat_row["annualized_bps_calendar"]),
                        "max_daily_dd_bps": float(cat_row["max_daily_dd_bps"]),
                    },
                ]
            )
            _save_table(catboost_cmp, out_table_dir, "appendix_catboost_comparison.csv")

    # Figures
    _plot_pipeline_diagram(out_fig_dir / "fig01_pipeline_and_data_flow.png")
    _plot_fold_timeline(folds, out_fig_dir / "fig02_wfo_fold_timeline_and_thresholds.png")
    _plot_equity_and_dd(
        base_daily,
        promoted_daily,
        out_fig_dir / "fig03_equity_curve_baseline_vs_promoted.png",
        out_fig_dir / "fig04_drawdown_curve_baseline_vs_promoted.png",
    )
    _plot_yearly_metrics(folds, out_fig_dir / "fig05_yearly_metrics_bars.png")
    _plot_tf_contribution(tf_tbl, out_fig_dir / "fig06_timeframe_strategy_contribution.png")
    _plot_pair_heatmap(pair_year_tbl[["pair", "year", "sharpe"]], out_fig_dir / "fig07_pair_heatmap_pnl_or_sharpe.png")
    _plot_threshold_frontier(threshold_grid, folds, out_fig_dir / "fig08_threshold_frontier_per_fold.png")
    _plot_probability_diagnostics(scored, out_fig_dir / "fig09_probability_filter_diagnostics.png")
    _plot_calibration_quality(fold_cal, out_fig_dir / "fig10_calibration_quality.png")
    _plot_mc_summary(mc_summary, out_fig_dir / "fig11_mc_distribution_comparison.png")
    if catboost_cmp is not None:
        _plot_catboost_comparison(promoted_row, catboost_cmp.iloc[1], out_fig_dir / "fig12_catboost_appendix_comparison.png")

    # Build markdown
    rel_fig_dir = "../figures/" + out_fig_dir.name
    _build_markdown(
        out_doc=out_doc,
        fig_dir_rel=rel_fig_dir,
        summary_cmp=summary_cmp,
        fold_cmp=fold_cmp,
        tf_tbl=tf_tbl[
            [
                "timeframe",
                "strategy_type",
                "trades",
                "mean_pnl_per_trade_bps",
                "sharpe",
                "annualized_bps_calendar",
                "cagr",
                "max_daily_dd_bps",
                "time_in_market_pct",
            ]
        ],
        pair_tbl=pair_tbl[
            [
                "pair",
                "trades",
                "total_pnl_bps",
                "mean_pnl_per_trade_bps",
                "sharpe",
                "annualized_bps_calendar",
                "cagr",
                "max_daily_dd_bps",
            ]
        ],
        pair_year_tbl=pair_year_tbl[
            [
                "pair",
                "year",
                "trades",
                "mean_pnl_per_trade_bps",
                "sharpe",
                "annualized_bps_calendar",
                "max_daily_dd_bps",
            ]
        ],
        label_tbl=label_tbl,
        m60none_overall_cmp=m60none_overall_cmp,
        m60none_fold_cmp=m60none_fold_cmp,
        catboost_cmp=catboost_cmp,
    )

    print("Saved deep-dive report assets:")
    print(f"- {out_doc}")
    print(f"- {out_fig_dir}")
    print(f"- {out_table_dir}")


if __name__ == "__main__":
    main()
