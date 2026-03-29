#!/usr/bin/env python3
"""Robustness checks for OCO monthly WFO predictions."""

from __future__ import annotations

import argparse
import logging
import math
from pathlib import Path

import numpy as np
import pandas as pd
from tqdm import tqdm


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
    for _m, g in d.groupby("test_month", sort=True):
        thr = float(np.quantile(g["pred_prob"].to_numpy(dtype=float), float(q)))
        x = g[g["pred_prob"] >= thr].copy()
        x["quantile"] = float(q)
        x["threshold"] = float(thr)
        out.append(x)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def _select_events(
    d: pd.DataFrame,
    *,
    q: float,
    use_exec_selection: bool,
    execution_quantile: float,
) -> pd.DataFrame:
    if (
        bool(use_exec_selection)
        and abs(float(q) - float(execution_quantile)) <= 1e-12
        and "selected_exec" in d.columns
    ):
        x = d[pd.to_numeric(d["selected_exec"], errors="coerce").fillna(0).astype(int) == 1].copy()
        x["quantile"] = float(q)
        if "threshold_exec" in d.columns:
            x["threshold"] = pd.to_numeric(x["threshold_exec"], errors="coerce")
        x["selection_mode"] = "exec_flag"
        return x
    x = _select_by_quantile(d, float(q))
    if not x.empty:
        x["selection_mode"] = "monthly_quantile"
    return x


def _build_state_key_from_candidate_uid(uid: pd.Series) -> pd.Series:
    parts = uid.astype(str).str.split("|", n=4, expand=True)
    if parts.shape[1] < 5:
        return pd.Series(np.nan, index=uid.index, dtype=object)
    state_id = parts[4].astype(str)
    bar_ticks = parts[2].astype(str)
    # parts[3] is e.g. "h6" — strip leading "h" to get the numeric horizon
    horizon = parts[3].astype(str).str.lstrip("h")
    return state_id + "|" + bar_ticks + "|" + horizon


def _apply_reduced_core_schedule_filter(
    d: pd.DataFrame,
    *,
    reduced_state_schedule_csv: Path | None,
) -> tuple[pd.DataFrame, str]:
    if reduced_state_schedule_csv is None:
        return d, "all_candidates"
    p = Path(reduced_state_schedule_csv)
    if not p.exists():
        raise FileNotFoundError(f"reduced_state_schedule_csv not found: {p}")
    try:
        s = pd.read_csv(p)
    except pd.errors.EmptyDataError:
        raise RuntimeError(
            f"reduced_state_schedule_csv is empty: {p}\n"
            "Run the reduced-core mining pipeline first to populate this file, e.g.:\n"
            "  uv run python scripts/select_oco_reduced_core_rolling.py"
        ) from None
    if s.empty:
        raise RuntimeError(
            f"reduced_state_schedule_csv has no rows: {p}\n"
            "Run the reduced-core mining pipeline first to populate this file, e.g.:\n"
            "  uv run python scripts/select_oco_reduced_core_rolling.py"
        )
    if "test_month" not in s.columns:
        raise ValueError("reduced_state_schedule_csv missing required column: test_month")
    if "state_key" not in s.columns:
        req = {"state_id", "bar_ticks", "horizon"}
        miss = sorted(req - set(s.columns))
        if miss:
            raise ValueError(
                "reduced_state_schedule_csv missing state_key and cannot derive it; missing columns: "
                + ",".join(miss)
            )
        s["state_key"] = (
            s["state_id"].astype(str)
            + "|"
            + pd.to_numeric(s["bar_ticks"], errors="coerce").fillna(-1).astype(int).astype(str)
            + "|"
            + pd.to_numeric(s["horizon"], errors="coerce").fillna(-1).astype(int).astype(str)
        )
    s["test_month"] = s["test_month"].astype(str)
    s = s[["test_month", "state_key"]].dropna().drop_duplicates().copy()
    if "candidate_uid" not in d.columns:
        raise ValueError(
            "predictions parquet missing required column for reduced-core filtering: candidate_uid"
        )
    dd = d.copy()
    dd["state_key"] = _build_state_key_from_candidate_uid(dd["candidate_uid"])
    dd["test_month"] = dd["test_month"].astype(str)
    dd = dd.merge(s, on=["test_month", "state_key"], how="inner")
    return dd, "reduced_core_schedule"


def _max_survivable_cost_lb95_trade(
    *,
    stress_levels: list[float],
    stress_lb95: list[float],
) -> tuple[float, str, float, float, float, float]:
    pairs = sorted(
        [
            (float(c), float(v))
            for c, v in zip(stress_levels, stress_lb95, strict=False)
            if np.isfinite(c) and np.isfinite(v)
        ],
        key=lambda x: x[0],
    )
    if not pairs:
        return (
            float("nan"),
            "missing_stress_grid",
            float("nan"),
            float("nan"),
            float("nan"),
            float("nan"),
        )

    xs = [x for x, _ in pairs]
    ys = [y for _, y in pairs]
    if all(y > 0.0 for y in ys):
        cmax = float(max(xs))
        ymax = float(ys[xs.index(cmax)])
        return cmax, "no_failure_in_grid", cmax, cmax, ymax, ymax
    if all(y <= 0.0 for y in ys):
        c0 = float(min(xs))
        y0 = float(ys[xs.index(c0)])
        return 0.0, "fails_at_zero_or_first_grid", 0.0, c0, 0.0, y0

    for j in range(1, len(pairs)):
        lo_c, lo_y = pairs[j - 1]
        hi_c, hi_y = pairs[j]
        if lo_y > 0.0 and hi_y <= 0.0:
            if abs(float(hi_y) - float(lo_y)) <= 1e-12:
                cross = float(hi_c)
            else:
                frac = (0.0 - float(lo_y)) / (float(hi_y) - float(lo_y))
                cross = float(lo_c) + float(frac) * (float(hi_c) - float(lo_c))
            cross = float(min(max(cross, float(lo_c)), float(hi_c)))
            return (
                cross,
                "crossing_interpolated",
                float(lo_c),
                float(hi_c),
                float(lo_y),
                float(hi_y),
            )

    # Defensive fallback for unexpected non-monotone edge cases.
    cmax = float(max(xs))
    ymax = float(ys[xs.index(cmax)])
    return cmax, "fallback_no_crossing_found", cmax, cmax, ymax, ymax


def run(
    *,
    pred_path: Path,
    quantiles: list[float],
    bootstrap_paths: int,
    stress_extra_cost_grid: list[float],
    use_exec_selection: bool,
    execution_quantile: float,
    reduced_state_schedule_csv: Path | None,
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
    logging.info(f"Loaded {len(d)} trades from {pred_path}")

    # Filter to reduced core schedule if provided
    d, universe_mode = _apply_reduced_core_schedule_filter(
        d,
        reduced_state_schedule_csv=reduced_state_schedule_csv,
    )
    if reduced_state_schedule_csv:
        logging.info(f"Filtered to {len(d)} trades using {universe_mode}")

    rows: list[dict[str, float | int | str]] = []
    monthly_rows: list[dict[str, float | int | str]] = []
    for i, q in enumerate(tqdm(quantiles, desc="Processing quantiles")):
        s = _select_events(
            d,
            q=float(q),
            use_exec_selection=bool(use_exec_selection),
            execution_quantile=float(execution_quantile),
        )
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
        lb95_month = _bootstrap_lb95(
            mon_means, paths=int(bootstrap_paths), seed=int(seed) + i * 17 + 3
        )
        pval = _normal_pvalue_mean_gt0(
            float(np.mean(mon_means)),
            float(np.std(mon_means, ddof=1)) if len(mon_means) > 1 else float("nan"),
            len(mon_means),
        )
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
            "selection_mode": str(s["selection_mode"].iloc[0])
            if "selection_mode" in s.columns and len(s)
            else "unknown",
            "is_exec_row": int(abs(float(q) - float(execution_quantile)) <= 1e-12),
            "universe_mode": str(universe_mode),
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
                _bootstrap_lb95(
                    net, paths=int(bootstrap_paths), seed=int(seed) + i * 23 + int(round(c * 100))
                )
            )
        stress_levels = [float(c) for c in stress_extra_cost_grid]
        stress_lb95 = [row.get(f"lb95_trade_mean_net_pips_costplus_{c:.2f}") for c in stress_levels]
        max_cost, max_status, lo_c, hi_c, lo_y, hi_y = _max_survivable_cost_lb95_trade(
            stress_levels=stress_levels,
            stress_lb95=stress_lb95,
        )
        row["max_survivable_cost_lb95_trade"] = float(max_cost)
        row["max_survivable_cost_status"] = str(max_status)
        row["survival_bracket_lo"] = float(lo_c)
        row["survival_bracket_hi"] = float(hi_c)
        row["survival_lb95_lo"] = float(lo_y)
        row["survival_lb95_hi"] = float(hi_y)
        rows.append(row)

    summary = pd.DataFrame(rows).sort_values("quantile").reset_index(drop=True)
    monthly = (
        pd.DataFrame(monthly_rows).sort_values(["quantile", "test_month"]).reset_index(drop=True)
    )
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
    lines.append(f"- use_exec_selection: `{bool(use_exec_selection)}`")
    lines.append(f"- execution_quantile: `{float(execution_quantile)}`")
    lines.append(f"- universe_mode: `{universe_mode}`")
    lines.append(
        f"- reduced_state_schedule_csv: `{reduced_state_schedule_csv}`"
        if reduced_state_schedule_csv is not None
        else "- reduced_state_schedule_csv: `_none_`"
    )
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
    p.add_argument(
        "--pred-path",
        default="data/analysis/tick_opportunity_mining/wfo_m3to1_oco_fast/EURUSD_oco_monthly_predictions.parquet",
    )
    p.add_argument("--quantiles", default="0.5,0.6,0.7,0.8,0.9,0.95")
    p.add_argument("--bootstrap-paths", type=int, default=2000)
    p.add_argument("--stress-extra-cost-grid", default="0.1,0.2,0.3,0.5,0.75,1.0,1.25,1.5,1.75,2.0")
    p.add_argument("--use-exec-selection", default="true")
    p.add_argument("--execution-quantile", type=float, default=0.9)
    p.add_argument("--reduced-state-schedule-csv", default="")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument(
        "--out-summary-csv",
        default="data/analysis/tick_opportunity_mining/wfo_m3to1_oco_fast/EURUSD_oco_robustness_summary.csv",
    )
    p.add_argument(
        "--out-monthly-csv",
        default="data/analysis/tick_opportunity_mining/wfo_m3to1_oco_fast/EURUSD_oco_robustness_monthly.csv",
    )
    p.add_argument(
        "--report-out", default="docs/analysis/eurusd_oco_monthly_wfo_robustness_report.md"
    )
    args = p.parse_args()

    run(
        pred_path=Path(str(args.pred_path)),
        quantiles=_parse_float_list(str(args.quantiles)),
        bootstrap_paths=int(args.bootstrap_paths),
        stress_extra_cost_grid=_parse_float_list(str(args.stress_extra_cost_grid)),
        use_exec_selection=str(args.use_exec_selection).strip().lower()
        in {"1", "true", "yes", "y"},
        execution_quantile=float(args.execution_quantile),
        reduced_state_schedule_csv=Path(str(args.reduced_state_schedule_csv))
        if str(args.reduced_state_schedule_csv).strip()
        else None,
        out_summary_csv=Path(str(args.out_summary_csv)),
        out_monthly_csv=Path(str(args.out_monthly_csv)),
        out_report=Path(str(args.report_out)),
        seed=int(args.seed),
    )


if __name__ == "__main__":
    main()
