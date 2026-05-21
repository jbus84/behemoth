"""Per-symbol deep-audit report for a tick-opportunity mining run.

Synthesises the per-family candidate CSVs, the candidate-fills parquet, and
the candidate_summary CSV into one markdown report per symbol.

Usage:
    uv run python scripts/build_mining_deep_report.py \\
        --analysis-dir data/analysis/tick_opportunity_mining \\
        --out-dir docs/analysis/mining_deep_report \\
        [--symbol EURUSD]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

# Library -> CSV-stem mapping the orchestrator writes (see
# scripts/run_tick_opportunity_mining.py main() — keep in sync if new
# families add new output files).
FAMILY_CSVS: dict[str, str] = {
    "directional": "_directional_candidates.csv",
    "oco_first_touch": "_oco_candidates.csv",
    "oco_asymmetric": "_oco_asymmetric_candidates.csv",
    "no_touch": "_no_touch_candidates.csv",
    "dollar_residual": "_dollar_residual_candidates.csv",
    "dispersion_rank": "_dispersion_rank_candidates.csv",
    "lead_lag": "_lead_lag_candidates.csv",
}

DEFAULT_SYMBOLS: tuple[str, ...] = (
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD",
)


def _read_csv_safe(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except (pd.errors.EmptyDataError, pd.errors.ParserError):
        return pd.DataFrame()


def _read_fills(analysis_dir: Path, symbol: str) -> pd.DataFrame:
    path = analysis_dir / "candidate_fills" / f"{symbol}_candidate_fills.parquet"
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(path)
    except Exception:
        return pd.DataFrame()


def _md_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_empty_"
    try:
        return df.to_markdown(index=False)
    except Exception:
        return "```\n" + df.to_string(index=False) + "\n```"


def _per_family_summary(
    family_rows: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """One row per family: candidate count, pass rate, mean baseline z,
    best and worst z, and the share of candidates with positive vs
    negative train EV."""
    rows: list[dict] = []
    for fam, df in family_rows.items():
        if df.empty:
            rows.append({
                "family": fam, "n_candidates": 0, "selection_pass": 0,
                "pass_rate": float("nan"),
                "mean_baseline_z": float("nan"),
                "best_baseline_z": float("nan"),
                "worst_baseline_z": float("nan"),
                "mean_gross_train": float("nan"),
                "pos_train_share": float("nan"),
            })
            continue
        z = pd.to_numeric(df.get("random_baseline_z"), errors="coerce")
        mg = pd.to_numeric(df.get("mean_gross_pips_train"), errors="coerce")
        sel = df.get("selection_pass")
        n_pass = int(sel.astype(bool).sum()) if sel is not None else 0
        n = int(len(df))
        rows.append({
            "family": fam,
            "n_candidates": n,
            "selection_pass": n_pass,
            "pass_rate": n_pass / n if n else float("nan"),
            "mean_baseline_z": float(z.mean()) if z.notna().any() else float("nan"),
            "best_baseline_z": float(z.max()) if z.notna().any() else float("nan"),
            "worst_baseline_z": float(z.min()) if z.notna().any() else float("nan"),
            "mean_gross_train": float(mg.mean()) if mg.notna().any() else float("nan"),
            "pos_train_share": (
                float((mg > 0).sum() / mg.notna().sum())
                if mg.notna().any() else float("nan")
            ),
        })
    return pd.DataFrame(rows)


def _per_regime_table(df: pd.DataFrame) -> pd.DataFrame:
    """Mean baseline z and pass rate by regime within one family."""
    if df.empty or "regime_desc" not in df.columns:
        return pd.DataFrame()
    z = pd.to_numeric(df.get("random_baseline_z"), errors="coerce")
    g = df.assign(__z=z, __pass=df.get("selection_pass", False).astype(bool))
    # Coarsen regime_desc to its first segment so per-family extra suffixes
    # (e.g. ";down=5;rr=2") don't fan rows out by every param combo.
    base_regime = g["regime_desc"].astype(str).str.split(";").str[0]
    g["__regime"] = base_regime
    agg = g.groupby("__regime", dropna=False).agg(
        n=("__z", "size"),
        n_pass=("__pass", "sum"),
        mean_z=("__z", "mean"),
        best_z=("__z", "max"),
        worst_z=("__z", "min"),
    )
    agg["pass_rate"] = (agg["n_pass"] / agg["n"]).round(3)
    agg = agg.reset_index().rename(columns={"__regime": "regime"})
    return agg.sort_values("mean_z", ascending=False)


def _top_n(df: pd.DataFrame, n: int, ascending: bool) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    cols = [
        c for c in (
            "candidate_id", "family", "bar_ticks", "horizon",
            "regime_desc", "random_baseline_z", "mean_gross_pips_train",
            "test_count", "selection_pass",
        ) if c in df.columns
    ]
    z = pd.to_numeric(df.get("random_baseline_z"), errors="coerce")
    return (
        df.assign(__z=z)
        .dropna(subset=["__z"])
        .sort_values("__z", ascending=ascending)
        .head(n)[cols]
    )


def _fill_density(fills: pd.DataFrame) -> pd.DataFrame:
    if fills.empty or "family" not in fills.columns:
        return pd.DataFrame()
    g = fills.groupby(["family", "split"], dropna=False).agg(
        n_fills=("gross_pips", "size"),
        mean_gross=("gross_pips", "mean"),
        sum_gross=("gross_pips", "sum"),
        hit_rate=("gross_pips", lambda x: float((x > 0).mean())),
    )
    return g.reset_index()


def _selection_funnel(family_rows: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for fam, df in family_rows.items():
        if df.empty:
            rows.append({"family": fam, "candidates": 0,
                          "selection_pass": 0, "near_miss": 0, "neither": 0})
            continue
        sel = df.get("selection_pass", False).astype(bool)
        nm = df.get("near_miss", False)
        nm = nm.astype(bool) if nm is not None else pd.Series([False] * len(df))
        n = len(df)
        n_pass = int(sel.sum())
        n_near = int((~sel & nm).sum())
        rows.append({
            "family": fam, "candidates": n,
            "selection_pass": n_pass, "near_miss": n_near,
            "neither": n - n_pass - n_near,
        })
    return pd.DataFrame(rows)


def build_report_for_symbol(
    *, analysis_dir: Path, symbol: str, out_dir: Path,
) -> Path:
    family_rows: dict[str, pd.DataFrame] = {}
    for fam, suffix in FAMILY_CSVS.items():
        family_rows[fam] = _read_csv_safe(analysis_dir / f"{symbol}{suffix}")
    fills = _read_fills(analysis_dir, symbol)
    summary = _read_csv_safe(analysis_dir / f"{symbol}_candidate_summary.csv")

    lines: list[str] = []
    lines.append(f"# {symbol} mining deep report")
    lines.append("")
    lines.append("Generated from the per-family candidate CSVs, the candidate-fills "
                 "parquet, and the per-library candidate_summary in")
    lines.append(f"`{analysis_dir}`.")
    lines.append("")

    # Per-library summary (orchestrator-written; legacy two-library view).
    lines.append("## Per-library summary (orchestrator)")
    lines.append(_md_table(summary))
    lines.append("")

    # Per-family deep summary.
    lines.append("## Per-family summary (deep)")
    psum = _per_family_summary(family_rows)
    if not psum.empty:
        psum_disp = psum.copy()
        for c in ("pass_rate", "mean_baseline_z", "best_baseline_z",
                  "worst_baseline_z", "mean_gross_train", "pos_train_share"):
            psum_disp[c] = psum_disp[c].round(3)
    else:
        psum_disp = psum
    lines.append(_md_table(psum_disp))
    lines.append("")
    lines.append("Notes: `pass_rate` = `selection_pass` / `n_candidates`; "
                 "`pos_train_share` = fraction of candidates with "
                 "`mean_gross_pips_train > 0`. `*_baseline_z` is "
                 "`random_baseline_z`, the z-score of candidate gross EV "
                 "against the family's random-entry baseline distribution.")
    lines.append("")

    # Selection funnel.
    lines.append("## Selection funnel")
    lines.append(_md_table(_selection_funnel(family_rows)))
    lines.append("")

    # Per-regime within each non-empty family.
    lines.append("## Per-regime baseline-z (top regime per family)")
    for fam, df in family_rows.items():
        if df.empty:
            continue
        rt = _per_regime_table(df)
        if rt.empty:
            continue
        rt_disp = rt.copy()
        for c in ("mean_z", "best_z", "worst_z"):
            if c in rt_disp.columns:
                rt_disp[c] = rt_disp[c].round(3)
        lines.append(f"### {fam}")
        lines.append(_md_table(rt_disp.head(10)))
        lines.append("")

    # Top positive-edge candidates across all families.
    populated = [
        df.assign(__src=fam) for fam, df in family_rows.items() if not df.empty
    ]
    all_cands = (
        pd.concat(populated, ignore_index=True) if populated else pd.DataFrame()
    )

    lines.append("## Top 20 positive-edge candidates (any family)")
    lines.append(_md_table(_top_n(all_cands, 20, ascending=False).round(3)))
    lines.append("")
    lines.append("## Top 20 negative-edge candidates (any family — potential "
                 "inverse plays)")
    lines.append(_md_table(_top_n(all_cands, 20, ascending=True).round(3)))
    lines.append("")

    # Fill density.
    lines.append("## Fill density (from candidate_fills parquet)")
    fd = _fill_density(fills)
    if not fd.empty:
        fd_disp = fd.copy()
        for c in ("mean_gross", "sum_gross", "hit_rate"):
            fd_disp[c] = fd_disp[c].round(3)
        lines.append(_md_table(fd_disp))
    else:
        lines.append("_no fills logged_")
    lines.append("")

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{symbol}_mining_deep_report.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def build_cross_symbol_index(
    *, out_dir: Path, reports: list[tuple[str, Path]],
) -> Path:
    lines: list[str] = ["# Mining deep reports", ""]
    lines.append("Per-symbol deep-audit reports synthesising the per-family "
                 "candidate CSVs and the candidate-fills parquet from the most "
                 "recent mining run.")
    lines.append("")
    for symbol, path in reports:
        lines.append(f"- [{symbol}]({path.name})")
    lines.append("")
    index = out_dir / "index.md"
    index.write_text("\n".join(lines), encoding="utf-8")
    return index


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    p.add_argument("--analysis-dir",
                   default="data/analysis/tick_opportunity_mining")
    p.add_argument("--out-dir",
                   default="docs/analysis/mining_deep_report")
    p.add_argument("--symbol", default=None,
                   help="Build for one symbol only; default builds for all "
                        "six majors that have a *_candidate_summary.csv.")
    args = p.parse_args()

    analysis_dir = Path(args.analysis_dir)
    out_dir = Path(args.out_dir)

    targets: list[str]
    if args.symbol:
        targets = [args.symbol.upper()]
    else:
        targets = [
            s for s in DEFAULT_SYMBOLS
            if (analysis_dir / f"{s}_candidate_summary.csv").exists()
        ]
        if not targets:
            print(f"no *_candidate_summary.csv found in {analysis_dir}",
                  file=sys.stderr)
            return 1

    written: list[tuple[str, Path]] = []
    for sym in targets:
        path = build_report_for_symbol(
            analysis_dir=analysis_dir, symbol=sym, out_dir=out_dir,
        )
        print(f"wrote: {path}")
        written.append((sym, path))

    if len(written) > 1:
        idx = build_cross_symbol_index(out_dir=out_dir, reports=written)
        print(f"wrote: {idx}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
