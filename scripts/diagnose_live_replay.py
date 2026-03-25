#!/usr/bin/env python3
"""Diagnose live replay parity from raw ticks, governance locks, and models."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import polars as pl

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.behemoth.core.features import compute_feature_matrix_from_bars  # noqa: E402

try:  # pragma: no cover - import availability depends on env
    from catboost import CatBoostClassifier
except Exception:  # pragma: no cover
    CatBoostClassifier = None  # type: ignore[assignment]


ACTIVE_SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD"]


def _markdown_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_empty_"
    try:
        return df.to_markdown(index=False)
    except Exception:
        return "```\n" + df.to_string(index=False) + "\n```"


def _parse_month_token(path: Path, symbol: str) -> str | None:
    stem = path.stem
    prefix = f"{symbol.upper()}_"
    suffix = "_ticks"
    if not stem.startswith(prefix) or not stem.endswith(suffix):
        return None
    month = stem[len(prefix) : -len(suffix)]
    if len(month) == 6 and month.isdigit():
        return f"{month[:4]}-{month[4:]}"
    if len(month) == 7 and month[4] == "-":
        return month
    return None


def _tick_price_frame(ticks: pl.DataFrame) -> pl.DataFrame:
    cols = set(ticks.columns)
    if "bid" in cols:
        price = pl.col("bid").cast(pl.Float64)
    elif "mid" in cols:
        price = pl.col("mid").cast(pl.Float64)
    elif "close" in cols:
        price = pl.col("close").cast(pl.Float64)
    else:
        raise ValueError("ticks frame must include bid, mid, or close price columns")

    if "spread" in cols:
        spread = pl.col("spread").cast(pl.Float64)
    elif {"ask", "bid"}.issubset(cols):
        spread = (pl.col("ask") - pl.col("bid")).cast(pl.Float64)
    else:
        spread = pl.lit(None, dtype=pl.Float64)

    return (
        ticks.select(
            pl.col("timestamp"),
            price.alias("price"),
            spread.alias("spread"),
        )
        .drop_nulls(["timestamp", "price"])
        .sort("timestamp")
    )


def _build_bars_from_ticks(ticks: pl.DataFrame) -> pl.DataFrame:
    """Aggregate ticks into 100-tick bars and drop the final partial bar."""
    if ticks.is_empty():
        return pl.DataFrame(
            schema={
                "timestamp": pl.Datetime(time_zone="UTC"),
                "close_ts": pl.Datetime(time_zone="UTC"),
                "open": pl.Float64,
                "high": pl.Float64,
                "low": pl.Float64,
                "close": pl.Float64,
                "spread": pl.Float64,
                "tick_volume": pl.Int64,
                "hl_first": pl.Int8,
                "hl_pos_frac": pl.Float64,
            }
        )

    df = _tick_price_frame(ticks)
    n_complete = (df.height // 100) * 100
    if n_complete <= 0:
        return pl.DataFrame(
            schema={
                "timestamp": pl.Datetime(time_zone="UTC"),
                "close_ts": pl.Datetime(time_zone="UTC"),
                "open": pl.Float64,
                "high": pl.Float64,
                "low": pl.Float64,
                "close": pl.Float64,
                "spread": pl.Float64,
                "tick_volume": pl.Int64,
                "hl_first": pl.Int8,
                "hl_pos_frac": pl.Float64,
            }
        )

    complete = df.slice(0, n_complete).with_row_index("row_idx").with_columns(
        (pl.col("row_idx") // 100).cast(pl.Int64).alias("bar_id"),
        (pl.col("row_idx") % 100).cast(pl.Int32).alias("bar_pos_tick"),
    )
    complete = complete.with_columns(
        pl.col("price").max().over("bar_id").alias("_bar_high"),
        pl.col("price").min().over("bar_id").alias("_bar_low"),
    )
    bars = (
        complete.group_by("bar_id", maintain_order=True)
        .agg(
            pl.col("timestamp").first().alias("timestamp"),
            pl.col("timestamp").last().alias("close_ts"),
            pl.col("price").first().alias("open"),
            pl.col("price").max().alias("high"),
            pl.col("price").min().alias("low"),
            pl.col("price").last().alias("close"),
            pl.col("spread").mean().alias("spread"),
            pl.len().cast(pl.Int64).alias("tick_volume"),
            pl.when(pl.col("price") == pl.col("_bar_high"))
            .then(pl.col("bar_pos_tick"))
            .otherwise(None)
            .min()
            .cast(pl.Int32)
            .alias("high_pos_tick"),
            pl.when(pl.col("price") == pl.col("_bar_low"))
            .then(pl.col("bar_pos_tick"))
            .otherwise(None)
            .min()
            .cast(pl.Int32)
            .alias("low_pos_tick"),
        )
        .with_columns(
            pl.when(pl.col("high_pos_tick") < pl.col("low_pos_tick"))
            .then(pl.lit(1, dtype=pl.Int8))
            .when(pl.col("high_pos_tick") > pl.col("low_pos_tick"))
            .then(pl.lit(-1, dtype=pl.Int8))
            .otherwise(pl.lit(0, dtype=pl.Int8))
            .alias("hl_first"),
            (
                (pl.col("low_pos_tick") - pl.col("high_pos_tick")).cast(pl.Float64) / 99.0
            ).alias("hl_pos_frac"),
        )
        .select(
            "timestamp",
            "close_ts",
            "open",
            "high",
            "low",
            "close",
            "spread",
            "tick_volume",
            "hl_first",
            "hl_pos_frac",
        )
    )
    return bars


def _load_states(symbol: str, governance_dir: str) -> list[dict]:
    lock_path = Path(governance_dir) / f"{str(symbol).lower()}_oco_live_lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    rows = lock.get("state_universe", {}).get("rows", [])
    if not isinstance(rows, list):
        raise ValueError(f"state_universe.rows must be a list: {lock_path}")
    return [dict(row) for row in rows]


def _load_thresholds(symbol: str, models_dir: str, model_month: str) -> tuple[dict, float]:
    model_dir = Path(models_dir)
    threshold_path = model_dir / f"{symbol.upper()}_model_{model_month}.json"
    thresholds = json.loads(threshold_path.read_text(encoding="utf-8"))
    threshold_exec = float(thresholds.get("threshold_exec", 0.5))
    return thresholds, threshold_exec


def _load_model(symbol: str, models_dir: str, model_month: str) -> Any:
    if CatBoostClassifier is None:
        raise RuntimeError("catboost is required to load replay models")
    model_path = Path(models_dir) / f"{symbol.upper()}_model_{model_month}.cbm"
    model = CatBoostClassifier()
    model.load_model(str(model_path))
    return model


def _score_bars(
    bars: pl.DataFrame,
    symbol: str,
    state: dict,
    model: Any,
    thresholds: dict,
    threshold_exec: float,
) -> pl.DataFrame:
    if bars.is_empty():
        return pl.DataFrame(
            schema={
                "close_ts": pl.Datetime(time_zone="UTC"),
                "state_id": pl.Utf8,
                "pred_prob": pl.Float64,
                "threshold": pl.Float64,
                "selected": pl.Int64,
                "gap": pl.Float64,
            }
        )

    bar_ticks = int(state.get("bar_ticks", 100))
    horizon = int(state.get("horizon", 0))
    barrier_pips = float(state.get("barrier_pips", 0.0))

    feats = compute_feature_matrix_from_bars(
        bars.to_pandas(),
        symbol=symbol,
        bar_ticks=bar_ticks,
        horizon=horizon,
        barrier_pips=barrier_pips,
    )
    if feats is None or feats.empty:
        return pl.DataFrame(
            schema={
                "close_ts": pl.Datetime(time_zone="UTC"),
                "state_id": pl.Utf8,
                "pred_prob": pl.Float64,
                "threshold": pl.Float64,
                "selected": pl.Int64,
                "gap": pl.Float64,
            }
        )

    features_df = feats.copy()
    valid_mask = features_df.notna().all(axis=1)
    valid_features = features_df.loc[valid_mask].copy()
    if valid_features.empty:
        return pl.DataFrame(
            schema={
                "close_ts": pl.Datetime(time_zone="UTC"),
                "state_id": pl.Utf8,
                "pred_prob": pl.Float64,
                "threshold": pl.Float64,
                "selected": pl.Int64,
                "gap": pl.Float64,
            }
        )

    feature_cols = [c for c in valid_features.columns if c not in {"close_ts"}]
    matrix = valid_features[feature_cols].to_numpy(dtype=float)
    probs = np.asarray(model.predict_proba(matrix))[:, 1].astype(float)

    threshold_schedule = thresholds.get("threshold_schedule", {}) or {}
    state_id = str(state.get("state_id", ""))
    close_ts = pd.to_datetime(bars.to_pandas().loc[valid_mask, "close_ts"], utc=True, errors="coerce")
    threshold_values: list[float] = []
    for ts in close_ts:
        day = ts.strftime("%Y-%m-%d") if pd.notna(ts) else ""
        if day in threshold_schedule:
            threshold_values.append(float(threshold_schedule[day]))
        else:
            threshold_values.append(float(threshold_exec if threshold_exec is not None else thresholds.get("threshold_exec", 0.5)))
    threshold_arr = np.asarray(threshold_values, dtype=float)
    selected = (probs >= threshold_arr).astype(int)
    out = pd.DataFrame(
        {
            "close_ts": close_ts,
            "state_id": state_id,
            "pred_prob": probs,
            "threshold": threshold_arr,
            "selected": selected,
            "gap": probs - threshold_arr,
        }
    )
    return pl.from_pandas(out)


def _section_score_distribution(results: pl.DataFrame) -> list[str]:
    lines = ["## Full Score Distribution"]
    if results.is_empty():
        lines.append("_No scored rows available._")
        return lines
    df = results.to_pandas()
    group_cols = ["state_id"]
    if "symbol" in df.columns:
        group_cols = ["symbol", "state_id"]
    summary = (
        df.groupby(group_cols, dropna=False)
        .agg(
            n=("pred_prob", "count"),
            mean_pred_prob=("pred_prob", "mean"),
            median_pred_prob=("pred_prob", "median"),
            threshold=("threshold", "median"),
            selected_rate=("selected", "mean"),
            mean_gap=("gap", "mean"),
        )
        .reset_index()
        .sort_values(["mean_pred_prob"] + group_cols, ascending=[False] + [True] * len(group_cols))
    )
    lines.append(_markdown_table(summary))
    return lines


def _section_near_miss(results: pl.DataFrame) -> list[str]:
    lines = ["## Near-Miss Table"]
    if results.is_empty():
        lines.append("_No scored rows available._")
        return lines
    df = results.to_pandas()
    near = df[df["selected"] == 0].copy()
    if near.empty:
        lines.append("_No near-miss rows available._")
        return lines
    cols = ["close_ts", "state_id", "pred_prob", "threshold", "gap"]
    if "symbol" in near.columns:
        cols = ["symbol"] + cols
    near = near.sort_values(["gap", "close_ts", "state_id"], ascending=[True, True, True]).head(20)
    lines.append(_markdown_table(near[cols]))
    return lines


def _section_sensitivity_sweep(results: pl.DataFrame) -> list[str]:
    lines = ["## Threshold Sensitivity Sweep"]
    if results.is_empty():
        lines.append("_No scored rows available._")
        return lines
    df = results.to_pandas()
    thresholds = [round(x, 2) for x in np.arange(0.50, 0.66, 0.05)]
    lines.append("Threshold grid: " + ", ".join(f"{thr:.2f}" for thr in thresholds))
    rows: list[dict[str, Any]] = []
    for thr in thresholds:
        selected = df["pred_prob"] >= thr
        rows.append(
            {
                "threshold": f"{thr:.2f}",
                "selected_rows": int(selected.sum()),
                "selected_rate": float(selected.mean()),
                "mean_gap": float((df["pred_prob"] - thr).mean()),
            }
        )
    lines.append(_markdown_table(pd.DataFrame(rows)))
    return lines


def _section_score_drift(results: pl.DataFrame) -> list[str]:
    lines = ["## Score Drift"]
    if results.is_empty():
        lines.append("_No scored rows available._")
        return lines
    df = results.to_pandas().sort_values("close_ts")
    if len(df) < 2:
        lines.append("_Insufficient rows for drift analysis._")
        return lines
    split = max(1, len(df) // 2)
    first = df.iloc[:split]
    second = df.iloc[split:]
    rows = pd.DataFrame(
        [
            {
                "window": "first_half",
                "n": int(len(first)),
                "mean_pred_prob": float(first["pred_prob"].mean()),
                "mean_threshold": float(first["threshold"].mean()),
                "mean_gap": float(first["gap"].mean()),
            },
            {
                "window": "second_half",
                "n": int(len(second)),
                "mean_pred_prob": float(second["pred_prob"].mean()),
                "mean_threshold": float(second["threshold"].mean()),
                "mean_gap": float(second["gap"].mean()),
            },
        ]
    )
    lines.append(_markdown_table(rows))
    return lines


def _latest_tick_files(ticks_dir: Path, symbol: str, lookback_months: int) -> list[Path]:
    sym_dir = ticks_dir / symbol
    if not sym_dir.exists():
        return []
    candidates: list[tuple[str, Path]] = []
    for path in sym_dir.glob(f"{symbol}_*_ticks.parquet"):
        month = _parse_month_token(path, symbol)
        if month is None:
            continue
        candidates.append((month, path))
    candidates.sort(key=lambda item: item[0])
    if lookback_months > 0:
        candidates = candidates[-int(lookback_months) :]
    return [path for _, path in candidates]


def _load_ticks(paths: list[Path]) -> pl.DataFrame:
    if not paths:
        return pl.DataFrame()
    frames = [pl.read_parquet(str(path)) for path in paths]
    return pl.concat(frames, how="vertical").sort("timestamp")


def _build_report(results: pl.DataFrame) -> str:
    lines = ["# Live Replay Diagnostic Report", ""]
    lines.extend(_section_score_distribution(results))
    lines.extend([""])
    lines.extend(_section_near_miss(results))
    lines.extend([""])
    lines.extend(_section_sensitivity_sweep(results))
    lines.extend([""])
    lines.extend(_section_score_drift(results))
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticks-dir", required=True)
    parser.add_argument("--models-dir", default="models/oco")
    parser.add_argument("--governance-dir", default="configs/research/governance/oco")
    parser.add_argument("--model-month", required=True)
    parser.add_argument("--lookback-months", type=int, default=1)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    ticks_dir = Path(args.ticks_dir)
    models_dir = Path(args.models_dir)
    governance_dir = Path(args.governance_dir)
    out_path = Path(args.out)

    scored_parts: list[pl.DataFrame] = []
    for symbol in ACTIVE_SYMBOLS:
        tick_paths = _latest_tick_files(ticks_dir, symbol, int(args.lookback_months))
        if not tick_paths:
            continue
        ticks = _load_ticks(tick_paths)
        bars = _build_bars_from_ticks(ticks)
        if bars.is_empty():
            continue
        states = _load_states(symbol, str(governance_dir))
        thresholds, threshold_exec = _load_thresholds(symbol, str(models_dir), str(args.model_month))
        model = _load_model(symbol, str(models_dir), str(args.model_month))
        for state in states:
            scored = _score_bars(
                bars=bars,
                symbol=symbol,
                state=state,
                model=model,
                thresholds=thresholds,
                threshold_exec=threshold_exec,
            )
            if not scored.is_empty():
                scored_parts.append(scored.with_columns(pl.lit(symbol).alias("symbol")))

    results = (
        pl.concat(scored_parts, how="vertical")
        if scored_parts
        else pl.DataFrame(
            schema={
                "close_ts": pl.Datetime(time_zone="UTC"),
                "state_id": pl.Utf8,
                "pred_prob": pl.Float64,
                "threshold": pl.Float64,
                "selected": pl.Int64,
                "gap": pl.Float64,
                "symbol": pl.Utf8,
            }
        )
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(_build_report(results), encoding="utf-8")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
