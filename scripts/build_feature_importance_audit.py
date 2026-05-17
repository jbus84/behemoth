"""Feature importance + orthogonality audit for the tick-opportunity model.

Reads the WFO per-month feature-importance CSVs and the ml-ready parquet,
writes a markdown report. Informational only — adding new features is a
separate plan.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def _mean_importance(importance_dir: Path, symbol: str) -> pd.Series:
    csvs = sorted(importance_dir.glob(f"{symbol}_feature_importance_*.csv"))
    if not csvs:
        raise FileNotFoundError(
            f"no {symbol}_feature_importance_*.csv files in {importance_dir}. "
            "Run the monthly WFO first (it writes them to model_export_dir)."
        )
    frames = [pd.read_csv(p) for p in csvs]
    merged = pd.concat(frames, ignore_index=True)
    feature_cols = [c for c in merged.columns if c != "test_month"]
    return merged[feature_cols].mean().sort_values(ascending=False)


def _correlation_matrix(ml_ready_path: Path, features: list[str]) -> pd.DataFrame:
    df = pd.read_parquet(ml_ready_path)
    present = [c for c in features if c in df.columns]
    numeric = df[present].apply(pd.to_numeric, errors="coerce")
    return numeric.corr()


def _session_vs_hour(ml_ready_path: Path) -> float | None:
    df = pd.read_parquet(ml_ready_path)
    if "session_marker" not in df.columns or "hour_utc" not in df.columns:
        return None
    codes = pd.factorize(df["session_marker"])[0]
    hour = pd.to_numeric(df["hour_utc"], errors="coerce")
    return float(pd.Series(codes).corr(hour))


def build_audit(
    *,
    symbol: str,
    importance_dir: Path,
    ml_ready_path: Path,
    out_path: Path,
    dead_weight_floor: float,
) -> Path:
    mean_imp = _mean_importance(importance_dir, symbol)
    corr = _correlation_matrix(ml_ready_path, list(mean_imp.index))

    lines: list[str] = [f"# Feature Importance Audit — {symbol}", ""]

    lines.append("## Ranked Mean Importance")
    lines.append("")
    lines.append("| feature | mean_importance |")
    lines.append("| --- | --- |")
    for feat, val in mean_imp.items():
        lines.append(f"| {feat} | {val:.4f} |")
    lines.append("")

    lines.append("## Dead-Weight Flags")
    lines.append("")
    dead = mean_imp[mean_imp < dead_weight_floor]
    if dead.empty:
        lines.append(f"No features below the importance floor ({dead_weight_floor}).")
    else:
        lines.append(f"Features with mean importance below {dead_weight_floor}:")
        lines.append("")
        for feat, val in dead.items():
            lines.append(f"- `{feat}` — {val:.4f}")
    lines.append("")

    lines.append("## Orthogonal Expansion Candidates")
    lines.append("")
    lines.append(
        "New features add the most value when uncorrelated with existing "
        "high-importance features. Highly correlated feature pairs (|corr| > "
        "0.8) below are redundant — expansion should target dimensions not "
        "already covered."
    )
    lines.append("")
    redundant: list[str] = []
    cols = list(corr.columns)
    for i, a in enumerate(cols):
        for b in cols[i + 1 :]:
            c = corr.loc[a, b]
            if pd.notna(c) and abs(c) > 0.8:
                redundant.append(f"- `{a}` ↔ `{b}` — corr {c:.3f}")
    if redundant:
        lines.extend(redundant)
    else:
        lines.append("No redundant feature pairs (|corr| > 0.8) found.")
    lines.append("")
    svh = _session_vs_hour(ml_ready_path)
    if svh is None:
        lines.append(
            "`session_marker` vs `hour_utc`: not computable (column absent)."
        )
    else:
        verdict = "redundant" if abs(svh) > 0.8 else "orthogonal"
        lines.append(
            f"`session_marker` vs `hour_utc`: ordinal-encoded corr {svh:.3f} "
            f"({verdict}). This decides whether `session_marker` is worth "
            "adding as a categorical feature in a follow-up."
        )
    lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--symbol", default="EURUSD")
    p.add_argument("--importance-dir", default="data/models")
    p.add_argument(
        "--ml-ready",
        default="data/analysis/tick_opportunity_mining/ml_ready/EURUSD_ml_ready.parquet",
    )
    p.add_argument("--out", default="docs/analysis/eurusd_feature_importance_audit.md")
    p.add_argument("--dead-weight-floor", type=float, default=1.0)
    args = p.parse_args()

    out = build_audit(
        symbol=args.symbol,
        importance_dir=Path(args.importance_dir),
        ml_ready_path=Path(args.ml_ready),
        out_path=Path(args.out),
        dead_weight_floor=args.dead_weight_floor,
    )
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
