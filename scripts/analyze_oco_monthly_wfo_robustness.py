#!/usr/bin/env python3
"""Robustness checks for OCO monthly WFO predictions."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd


def _parse_float_list(raw: str) -> list[float]:
    return [float(x.strip()) for x in str(raw).split(",") if x.strip()]


def _bootstrap_lb95(vals: np.ndarray, *, paths: int, seed: int) -> float:
    x = np.asarray(vals, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) == 0 or int(paths) <= 0:
        return float("nan")
    rng = np.random.default_rng(int(seed))
    n = len(x)
    means: list[np.ndarray] = []
    batch = 250
    for i in range(0, int(paths), batch):
        b = min(batch, int(paths) - i)
        idx = rng.integers(0, n, size=(b, n))
        means.append(x[idx].mean(axis=1))
    m = np.concatenate(means) if means else np.array([], dtype=float)
    if len(m) == 0:
        return float("nan")
    return float(np.quantile(m, 0.05))


def _normal_pvalue_mean_gt0(mean: float, std: float, n: int) -> float:
    if not np.isfinite(mean) or not np.isfinite(std) or int(n) <= 1:
        return float("nan")
    if std <= 1e-12:
        return 0.0 if mean > 0 else 1.0
    se = std / math.sqrt(float(n))
    if se <= 1e-12:
        return 0.0 if mean > 0 else 1.0
    z = mean / se
    cdf = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
    return float(1.0 - cdf)


def _p_adjust_bonferroni(p: np.ndarray) -> np.ndarray:
    out = np.asarray(p, dtype=float).copy()
    m = np.isfinite(out).sum()
    if m <= 0:
        return out
    out[np.isfinite(out)] = np.minimum(out[np.isfinite(out)] * float(m), 1.0)
    return out


def _p_adjust_fdr_bh(p: np.ndarray) -> np.ndarray:
    vals = np.asarray(p, dtype=float)
    out = np.full_like(vals, np.nan)
    mask = np.isfinite(vals)
    if not np.any(mask):
        return out
    pv = vals[mask]
    n = len(pv)
    order = np.argsort(pv)
    ranked = pv[order]
    adj = ranked * n / (np.arange(n) + 1)
    adj = np.minimum.accumulate(adj[::-1])[::-1]
    adj = np.clip(adj, 0.0, 1.0)
    out_vals = np.empty(n, dtype=float)
    out_vals[order] = adj
    out[mask] = out_vals
    return out


def _select_by_quantile(d: pd.DataFrame, q: float) -> pd.DataFrame:
    out: list[pd.DataFrame] = []
    for m, g in d.groupby("test_month", sort=True):
        thr = float(np.quantile(g["pred_prob"].to_numpy(dtype=float), float(q)))
        x = g[g["pred_prob"] >= thr].copy()
        x["quantile"] = float(q)
        x["threshold"] = float(thr)
        out.append(x)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def run(
    *,
    pred_path: Path,
    quantiles: list[float],
    bootstrap_paths: int,
    stress_extra_cost_grid: list[float],
    out_summary_csv: Path,
    out_monthly_csv: Path,
    out_report: Path,
    seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    d = pd.read_parquet(pred_path).copy()
    req = ["test_month", "pred_prob", "target_gross_pips", "target_gross_pos"]
    miss = [c for c in req if c not in d.columns]
    if miss:
        raise ValueError(f"missing columns in predictions parquet: {miss}")
    d = d.dropna(subset=req).copy()
    d["test_month"] = d["test_month"].astype(str)
    d["pred_prob"] = pd.to_numeric(d["pred_prob"], errors="coerce")
    d["target_gross_pips"] = pd.to_numeric(d["target_gross_pips"], errors="coerce")
    d = d.dropna(subset=["pred_prob", "target_gross_pips"]).copy()

    rows: list[dict[str, float | int | str]] = []
    monthly_rows: list[dict[str, float | int | str]] = []
    for i, q in enumerate(quantiles):
        s = _select_by_quantile(d, float(q))
        if s.empty:
            continue
        gross = s["target_gross_pips"].to_numpy(dtype=float)
        lb95_trade = _bootstrap_lb95(gross, paths=int(bootstrap_paths), seed=int(seed) + i * 11)

        mon = (
            s.groupby("test_month", as_index=False)
            .agg(
                rows=("target_gross_pips", "size"),
                mean_gross=("target_gross_pips", "mean"),
                median_gross=("target_gross_pips", "median"),
                pos_rate=("target_gross_pos", "mean"),
            )
            .sort_values("test_month")
            .reset_index(drop=True)
        )
        mon_means = mon["mean_gross"].to_numpy(dtype=float)
        lb95_month = _bootstrap_lb95(mon_means, paths=int(bootstrap_paths), seed=int(seed) + i * 17 + 3)
        pval = _normal_pvalue_mean_gt0(float(np.mean(mon_means)), float(np.std(mon_means, ddof=1)) if len(mon_means) > 1 else float("nan"), len(mon_means))
        positive_months = int(np.sum(mon_means > 0.0))

        for _, r in mon.iterrows():
            monthly_rows.append(
                {
                    "quantile": float(q),
                    "test_month": str(r["test_month"]),
                    "rows": int(r["rows"]),
                    "mean_gross_pips": float(r["mean_gross"]),
                    "median_gross_pips": float(r["median_gross"]),
                    "pos_rate": float(r["pos_rate"]),
                }
            )

        row = {
            "quantile": float(q),
            "rows": int(len(s)),
            "months": int(mon["test_month"].nunique()),
            "coverage": float(len(s) / max(len(d), 1)),
            "mean_gross_pips": float(np.mean(gross)),
            "median_gross_pips": float(np.median(gross)),
            "pos_rate": float(np.mean(gross > 0.0)),
            "lb95_trade_mean_gross_pips": float(lb95_trade),
            "lb95_month_mean_gross_pips": float(lb95_month),
            "positive_months": int(positive_months),
            "pvalue_month_mean_gt0": float(pval),
        }
        for c in stress_extra_cost_grid:
            net = gross - float(c)
            row[f"mean_net_pips_costplus_{c:.2f}"] = float(np.mean(net))
            row[f"lb95_trade_mean_net_pips_costplus_{c:.2f}"] = float(
                _bootstrap_lb95(net, paths=int(bootstrap_paths), seed=int(seed) + i * 23 + int(round(c * 100)))
            )
        rows.append(row)

    summary = pd.DataFrame(rows).sort_values("quantile").reset_index(drop=True)
    monthly = pd.DataFrame(monthly_rows).sort_values(["quantile", "test_month"]).reset_index(drop=True)
    if not summary.empty:
        p = summary["pvalue_month_mean_gt0"].to_numpy(dtype=float)
        summary["pvalue_bonferroni"] = _p_adjust_bonferroni(p)
        summary["pvalue_fdr_bh"] = _p_adjust_fdr_bh(p)

    out_summary_csv.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(out_summary_csv, index=False)
    out_monthly_csv.parent.mkdir(parents=True, exist_ok=True)
    monthly.to_csv(out_monthly_csv, index=False)

    lines: list[str] = []
    lines.append("# OCO Monthly WFO Robustness")
    lines.append("")
    lines.append(f"- predictions: `{pred_path}`")
    lines.append(f"- quantiles: `{','.join(str(x) for x in quantiles)}`")
    lines.append(f"- bootstrap_paths: `{int(bootstrap_paths)}`")
    lines.append(f"- stress_extra_cost_grid: `{','.join(str(x) for x in stress_extra_cost_grid)}`")
    lines.append("")
    lines.append("## Summary")
    lines.append(summary.to_markdown(index=False) if not summary.empty else "_empty_")
    lines.append("")
    lines.append("## Monthly Details")
    lines.append(monthly.to_markdown(index=False) if not monthly.empty else "_empty_")
    lines.append("")
    out_report.parent.mkdir(parents=True, exist_ok=True)
    out_report.write_text("\n".join(lines), encoding="utf-8")
    return summary, monthly


def main() -> None:
    p = argparse.ArgumentParser(description="Robustness checks for OCO monthly WFO predictions")
    p.add_argument("--pred-path", default="data/analysis/tick_opportunity_mining/wfo_2025_m3to1_oco_fast/EURUSD_oco_monthly_predictions.parquet")
    p.add_argument("--quantiles", default="0.5,0.6,0.7,0.8,0.9,0.95")
    p.add_argument("--bootstrap-paths", type=int, default=2000)
    p.add_argument("--stress-extra-cost-grid", default="0.1,0.2,0.3,0.5")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out-summary-csv", default="data/analysis/tick_opportunity_mining/wfo_2025_m3to1_oco_fast/EURUSD_oco_robustness_summary.csv")
    p.add_argument("--out-monthly-csv", default="data/analysis/tick_opportunity_mining/wfo_2025_m3to1_oco_fast/EURUSD_oco_robustness_monthly.csv")
    p.add_argument("--report-out", default="docs/analysis/eurusd_oco_monthly_wfo_robustness_report.md")
    args = p.parse_args()

    run(
        pred_path=Path(str(args.pred_path)),
        quantiles=_parse_float_list(str(args.quantiles)),
        bootstrap_paths=int(args.bootstrap_paths),
        stress_extra_cost_grid=_parse_float_list(str(args.stress_extra_cost_grid)),
        out_summary_csv=Path(str(args.out_summary_csv)),
        out_monthly_csv=Path(str(args.out_monthly_csv)),
        out_report=Path(str(args.report_out)),
        seed=int(args.seed),
    )


if __name__ == "__main__":
    main()
