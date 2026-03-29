#!/usr/bin/env python3
"""Run a frozen-month offset screen without retraining or state reselection."""

from __future__ import annotations

import argparse
import contextlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import polars as pl

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_global_tick_bars import _aggregate_from_base  # noqa: E402
from scripts.build_tick_opportunity_ml_dataset import _build_oco_events  # noqa: E402
from scripts.build_tick_velocity_dataset import _build_symbol_dataset  # noqa: E402
from scripts.run_offset_tickbar_robustness import (  # noqa: E402
    ACTIVE_SYMBOLS,
    DEFAULT_OFFSET_BAR_DIR,
    DEFAULT_OUT_DIR,
    DEFAULT_STOP_LIMIT_CAPS,
    DEFAULT_STRESS_COST_GRID,
    DEFAULT_TICK_ROOT,
    _load_csv,
    _load_parquet,
    _offset_stage_root,
    _parse_symbols,
    _pct_delta,
    _run_cmd,
    _safe_float,
    _safe_int,
)
from scripts.run_tick_opportunity_mining import _prepare_frame, _quantiles  # noqa: E402
from scripts.run_tick_opportunity_monthly_wfo import (  # noqa: E402
    _select_candidate_universe,
)

try:
    from catboost import CatBoostClassifier
except Exception:
    CatBoostClassifier = None  # type: ignore[assignment]


DEFAULT_SCREEN_OFFSETS = tuple(range(0, 100, 10))
DEFAULT_FROZEN_ROOT = "data/analysis/tick_opportunity_mining/frozen_models"
DEFAULT_BAR_TICKS_GRID = (100, 1000, 2000)


def _parse_csv_ints(raw: str | None) -> list[int]:
    vals: list[int] = []
    for tok in str(raw or "").split(","):
        t = tok.strip()
        if t:
            vals.append(int(t))
    return vals


def _frozen_event_window(
    wfo_cfg: dict[str, Any],
) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    eval_start_month = str(wfo_cfg.get("eval_start_month", "")).strip()
    eval_end_month = str(wfo_cfg.get("eval_end_month", "")).strip()
    if not eval_start_month or not eval_end_month:
        return None, None
    rolling_train_months = int(wfo_cfg.get("rolling_train_months", 0) or 0)
    hist_start_period = pd.Period(eval_start_month, freq="M") - rolling_train_months
    start_ts = hist_start_period.to_timestamp(how="start").tz_localize("UTC")
    end_period = pd.Period(eval_end_month, freq="M")
    end_ts_excl = (end_period + 1).to_timestamp(how="start").tz_localize("UTC")
    return start_ts, end_ts_excl


def _symbol_configs(symbol: str) -> tuple[Path, Path]:
    s = str(symbol).lower().strip()
    return (
        ROOT
        / f"configs/research/experiments/{s}_tick_opportunity_monthly_wfo_oco_fullcap_2025.yaml",
        ROOT / f"configs/research/experiments/{s}_oco_reduced_core_rolling_2025.yaml",
    )


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("PyYAML required") from exc
    obj = yaml.safe_load(path.read_text(encoding="utf-8"))
    return dict(obj or {})


def _canonical_paths(symbol: str) -> dict[str, Path]:
    wfo_cfg, reduced_cfg = _symbol_configs(symbol)
    wfo = _load_yaml(wfo_cfg)
    reduced = _load_yaml(reduced_cfg)
    candidate_dir = Path(str(wfo.get("candidate_dir", "data/analysis/tick_opportunity_mining")))
    dataset_dir = Path(str(wfo.get("dataset_dir", "data/analysis/tick_velocity")))
    out_dir = Path(str(wfo.get("out_dir", "data/analysis/tick_opportunity_mining")))
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir
    return {
        "candidate_dir": candidate_dir if candidate_dir.is_absolute() else ROOT / candidate_dir,
        "dataset_dir": dataset_dir if dataset_dir.is_absolute() else ROOT / dataset_dir,
        "wfo_out_dir": out_dir,
        "pred_path": ROOT / Path(str(reduced["pred_path"])),
        "reduced_schedule_csv": ROOT / Path(str(reduced["out_state_schedule_csv"])),
        "wfo_cfg": wfo_cfg,
        "reduced_cfg": reduced_cfg,
    }


def _frozen_symbol_root(frozen_root: Path, symbol: str) -> Path:
    return frozen_root / symbol


def _manifest_path(frozen_root: Path, symbol: str) -> Path:
    return _frozen_symbol_root(frozen_root, symbol) / f"{symbol}_model_manifest.csv"


def _quantiles_path(frozen_root: Path, symbol: str, bar_ticks: int) -> Path:
    return (
        _frozen_symbol_root(frozen_root, symbol) / f"{symbol}_{int(bar_ticks)}tick_quantiles.json"
    )


def _load_model_manifest(frozen_root: Path, symbol: str) -> pd.DataFrame:
    return _load_csv(_manifest_path(frozen_root, symbol))


def _load_threshold_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _ensure_canonical_exports(
    *,
    symbol: str,
    frozen_root: Path,
    fail_fast: bool,
) -> tuple[pd.DataFrame, dict[int, dict[str, float]], dict[str, Path]]:
    paths = _canonical_paths(symbol)
    sym_root = _frozen_symbol_root(frozen_root, symbol)
    models_dir = sym_root / "models"
    manifest_path = _manifest_path(frozen_root, symbol)
    sym_root.mkdir(parents=True, exist_ok=True)

    manifest = _load_csv(manifest_path)
    canonical_mtime = max(
        paths["pred_path"].stat().st_mtime if paths["pred_path"].exists() else 0.0,
        _canonical_events_path(paths, symbol, _load_yaml(paths["wfo_cfg"])).stat().st_mtime
        if _canonical_events_path(paths, symbol, _load_yaml(paths["wfo_cfg"])).exists()
        else 0.0,
    )
    manifest_mtime = manifest_path.stat().st_mtime if manifest_path.exists() else 0.0
    refresh_exports = manifest.empty or manifest_mtime < canonical_mtime
    if not refresh_exports and not manifest.empty:
        for _, rec in manifest.iterrows():
            if (
                not Path(str(rec.get("model_cbm_path", ""))).exists()
                or not Path(str(rec.get("model_threshold_json_path", ""))).exists()
            ):
                refresh_exports = True
                break

    if refresh_exports:
        export_tmp = sym_root / "_export_tmp"
        export_tmp.mkdir(parents=True, exist_ok=True)
        cmd = [
            sys.executable,
            str(ROOT / "scripts/run_tick_opportunity_monthly_wfo.py"),
            "--config",
            str(paths["wfo_cfg"]),
            "--dataset-dir",
            str(paths["dataset_dir"]),
            "--candidate-dir",
            str(paths["candidate_dir"]),
            "--out-dir",
            str(export_tmp),
            "--model-export-dir",
            str(models_dir),
            "--report-out",
            str(export_tmp / f"{symbol.lower()}_frozen_export_report.md"),
        ]
        ok, msg = _run_cmd(cmd, fail_fast=fail_fast)
        if not ok:
            raise RuntimeError(msg)

        rows: list[dict[str, Any]] = []
        for cbm_path in sorted(models_dir.glob(f"{symbol}_model_*.cbm")):
            month = cbm_path.stem.split("_")[-1]
            thr_path = cbm_path.with_suffix(".json")
            imp_path = models_dir / f"{symbol}_feature_importance_{month}.csv"
            if not thr_path.exists():
                raise FileNotFoundError(f"missing threshold json for {cbm_path.name}")
            thr = _load_threshold_json(thr_path)
            rows.append(
                {
                    "symbol": symbol,
                    "test_month": month,
                    "model_cbm_path": str(cbm_path),
                    "model_threshold_json_path": str(thr_path),
                    "feature_importance_csv": str(imp_path) if imp_path.exists() else "",
                    "threshold_exec": float(thr.get("threshold_exec", np.nan)),
                    "threshold_source": str(thr.get("threshold_source", "")),
                    "features_json": json.dumps(list(thr.get("features", []))),
                }
            )
        manifest = pd.DataFrame(rows).sort_values("test_month").reset_index(drop=True)
        manifest.to_csv(manifest_path, index=False)
        shutil.rmtree(export_tmp, ignore_errors=True)

    candidate_csv = paths["candidate_dir"] / f"{symbol}_oco_candidates.csv"
    cands = pd.read_csv(candidate_csv)
    cands = _select_candidate_universe(
        cands,
        symbol=symbol,
        min_train_count=int(_load_yaml(paths["wfo_cfg"]).get("min_candidate_train_count", 15000)),
        max_candidates=int(_load_yaml(paths["wfo_cfg"]).get("max_candidates_per_library", 300)),
    )
    bar_ticks_used = (
        sorted(cands["bar_ticks"].astype(int).unique().tolist()) if not cands.empty else [100]
    )
    quantiles: dict[int, dict[str, float]] = {}
    wfo_cfg = _load_yaml(paths["wfo_cfg"])
    train_years = {
        int(x.strip())
        for x in str(wfo_cfg.get("train_years_for_state_fit", "2022,2023,2024")).split(",")
        if x.strip()
    }
    for bt in bar_ticks_used:
        q_path = _quantiles_path(frozen_root, symbol, int(bt))
        if (
            q_path.exists()
            and not refresh_exports
            and q_path.stat().st_mtime >= manifest_path.stat().st_mtime
        ):
            quantiles[int(bt)] = {
                k: float(v) for k, v in json.loads(q_path.read_text(encoding="utf-8")).items()
            }
            continue
        df = _prepare_frame(
            paths["dataset_dir"] / f"{symbol}_{int(bt)}tick_velocity.parquet",
            symbol=symbol,
            horizons=sorted(
                cands[cands["bar_ticks"].astype(int) == int(bt)]["horizon"]
                .astype(int)
                .unique()
                .tolist()
            ),
        )
        fit_df = df[df["year"].isin(train_years)].copy().reset_index(drop=True)
        q_fit = {k: float(v) for k, v in _quantiles(fit_df).items()}
        q_path.write_text(json.dumps(q_fit, indent=2), encoding="utf-8")
        quantiles[int(bt)] = q_fit
    return manifest, quantiles, paths


def _build_frozen_events(
    *,
    symbol: str,
    velocity_dir: Path,
    candidate_dir: Path,
    quantiles_by_ticks: dict[int, dict[str, float]],
    wfo_cfg: dict[str, Any],
) -> pd.DataFrame:
    c_path = candidate_dir / f"{symbol}_oco_candidates.csv"
    if not c_path.exists():
        return pd.DataFrame()
    cands = pd.read_csv(c_path)
    cands = _select_candidate_universe(
        cands,
        symbol=symbol,
        min_train_count=int(wfo_cfg.get("min_candidate_train_count", 15000)),
        max_candidates=int(wfo_cfg.get("max_candidates_per_library", 300)),
    )
    if cands.empty:
        return pd.DataFrame()

    eval_start_ts, eval_end_ts_excl = _frozen_event_window(wfo_cfg)

    parts: list[pd.DataFrame] = []
    for bt in sorted(cands["bar_ticks"].astype(int).unique().tolist()):
        sub = cands[cands["bar_ticks"].astype(int) == int(bt)].copy()
        path = velocity_dir / f"{symbol}_{int(bt)}tick_velocity.parquet"
        if sub.empty or not path.exists():
            continue
        horizons = sorted(sub["horizon"].astype(int).unique().tolist())
        d = _prepare_frame(path, symbol=symbol, horizons=horizons)
        if eval_start_ts is not None and eval_end_ts_excl is not None:
            eval_df = (
                d[(d["close_ts"] >= eval_start_ts) & (d["close_ts"] < eval_end_ts_excl)]
                .copy()
                .reset_index(drop=True)
            )
        else:
            eval_df = (
                d[d["year"] == int(wfo_cfg.get("eval_year", 2025))].copy().reset_index(drop=True)
            )
        if eval_df.empty:
            continue
        q_fit = quantiles_by_ticks.get(int(bt))
        if not q_fit:
            continue
        ev = _build_oco_events(
            split_name="eval",
            df=eval_df,
            q_fit=q_fit,
            cands=sub,
            max_events_per_candidate=int(wfo_cfg.get("max_events_per_candidate", 20000)),
            symbol=symbol,
            hold_mode=str(wfo_cfg.get("oco_hold_mode", "from_touch")),
            include_no_touch=bool(wfo_cfg.get("oco_include_no_touch", True)),
        )
        if not ev.empty:
            parts.append(ev)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def _ensure_offset_bars(
    *,
    symbols: list[str],
    offsets: list[int],
    tick_root: Path,
    offset_bar_dir: Path,
    bar_ticks_grid: list[int],
    overwrite: bool,
    fail_fast: bool,
) -> None:
    base_ticks = 100
    args = [
        sys.executable,
        str(ROOT / "scripts/build_global_tick_bars_offset.py"),
        "--tick-root",
        str(tick_root),
        "--output-dir",
        str(offset_bar_dir),
        "--symbols",
        ",".join(symbols),
        "--offsets",
        ",".join(str(x) for x in offsets),
        "--bar-ticks",
        str(int(base_ticks)),
        "--price-source",
        "bid",
        "--timestamp-mode",
        "as_utc",
        "--summary-csv",
        str(offset_bar_dir / f"build_summary_{int(base_ticks)}tick.csv"),
    ]
    if overwrite:
        args.append("--overwrite")
    ok, msg = _run_cmd(args, fail_fast=fail_fast)
    if not ok:
        raise RuntimeError(msg)

    for symbol in symbols:
        for offset in offsets:
            base_path = (
                offset_bar_dir / f"{symbol}_{int(base_ticks)}tick_offset_{int(offset):03d}.parquet"
            )
            if not base_path.exists():
                raise FileNotFoundError(f"missing base offset bar parquet: {base_path}")
            base_bars = pl.read_parquet(base_path)
            for target_ticks in sorted(
                set(int(x) for x in bar_ticks_grid if int(x) > int(base_ticks))
            ):
                out_path = (
                    offset_bar_dir
                    / f"{symbol}_{int(target_ticks)}tick_offset_{int(offset):03d}.parquet"
                )
                bars, _ = _aggregate_from_base(
                    base_bars,
                    symbol=symbol,
                    target_ticks=int(target_ticks),
                    base_ticks=int(base_ticks),
                )
                if bars.height == 0:
                    raise RuntimeError(
                        f"empty aggregated offset bars for {symbol} offset={offset} target_ticks={target_ticks}"
                    )
                out_path.parent.mkdir(parents=True, exist_ok=True)
                bars.write_parquet(out_path)


def _build_velocity_for_offset(
    *,
    symbol: str,
    offset: int,
    offset_bar_dir: Path,
    stage_root: Path,
    bar_ticks_grid: list[int],
) -> Path:
    velocity_dir = stage_root / "velocity"
    velocity_dir.mkdir(parents=True, exist_ok=True)
    for bar_ticks in sorted(set(int(x) for x in bar_ticks_grid if int(x) > 0)):
        bar_path = (
            offset_bar_dir / f"{symbol}_{int(bar_ticks)}tick_offset_{int(offset):03d}.parquet"
        )
        if not bar_path.exists():
            raise FileNotFoundError(f"offset bar parquet missing: {bar_path}")
        out_path = velocity_dir / f"{symbol}_{int(bar_ticks)}tick_velocity.parquet"
        ds = _build_symbol_dataset(
            symbol=symbol,
            bar_path=bar_path,
            bar_ticks=int(bar_ticks),
            vel_horizons=[1, 2, 5, 10],
            target_horizons=[1, 2, 3, 4, 5, 6],
            vol_window=96,
            cost_window=288,
        )
        if ds.empty:
            raise RuntimeError(
                f"empty velocity dataset for {symbol} offset={offset} bar_ticks={bar_ticks}"
            )
        ds["timestamp_mode"] = "as_utc"
        ds.to_parquet(out_path, index=False)
    return velocity_dir


def _canonical_events_path(paths: dict[str, Path], symbol: str, wfo_cfg: dict[str, Any]) -> Path:
    eval_year = wfo_cfg.get("eval_year")
    if eval_year is None:
        eval_start_month = str(wfo_cfg.get("eval_start_month", "")).strip()
        eval_year = int(eval_start_month.split("-", 1)[0]) if eval_start_month else 2025
    return paths["wfo_out_dir"] / f"{symbol}_oco_events_eval{int(eval_year)}.parquet"


def _with_test_month(df: pd.DataFrame, *, close_col: str = "close_ts") -> pd.DataFrame:
    out = df.copy()
    out[close_col] = pd.to_datetime(out[close_col], utc=True, errors="coerce")
    out = out[out[close_col].notna()].copy()
    out["test_month"] = out[close_col].dt.strftime("%Y-%m")
    return out


def _add_event_ordinal(df: pd.DataFrame, *, close_col: str = "close_ts") -> pd.DataFrame:
    out = _with_test_month(df, close_col=close_col)
    out = out.sort_values(["test_month", "candidate_uid", close_col], kind="stable").reset_index(
        drop=True
    )
    out["event_ordinal"] = out.groupby(["test_month", "candidate_uid"]).cumcount().astype(int)
    out["scored_row_id"] = (
        out["test_month"].astype(str)
        + "|"
        + out["candidate_uid"].astype(str)
        + "|"
        + out["event_ordinal"].astype(str)
    )
    out["frozen_event_id"] = out["scored_row_id"]
    return out


def _load_canonical_event_universe(events_path: Path, pred_path: Path) -> pd.DataFrame:
    wanted_cols = [
        "candidate_uid",
        "close_ts",
        "library",
        "target_gross_pips",
        "target_gross_pos",
        "event_ordinal",
        "scored_row_id",
    ]
    try:
        import pyarrow.parquet as pq

        avail_cols = set(pq.read_schema(events_path).names) if events_path.exists() else set()
    except Exception:
        avail_cols = set()
    cols = [c for c in wanted_cols if c in avail_cols] if avail_cols else wanted_cols[:5]
    ev = _load_parquet(events_path, columns=cols)
    if ev.empty:
        return pd.DataFrame(
            columns=["candidate_uid", "close_ts", "test_month", "event_ordinal", "frozen_event_id"]
        )
    ev = _with_test_month(ev, close_col="close_ts")
    pred = _load_parquet(pred_path, columns=["candidate_uid", "close_ts", "test_month"])
    if pred.empty:
        return pd.DataFrame(
            columns=["candidate_uid", "close_ts", "test_month", "event_ordinal", "frozen_event_id"]
        )
    pred["close_ts"] = pd.to_datetime(pred["close_ts"], utc=True, errors="coerce")
    pred["test_month"] = pred["test_month"].astype(str)
    ev = ev.merge(
        pred[["candidate_uid", "close_ts", "test_month"]].drop_duplicates(),
        on=["candidate_uid", "close_ts", "test_month"],
        how="inner",
    )
    if "scored_row_id" in ev.columns and ev["scored_row_id"].notna().any():
        ev["event_ordinal"] = pd.to_numeric(ev.get("event_ordinal"), errors="coerce").astype(
            "Int64"
        )
        missing_ord = ev["event_ordinal"].isna()
        if bool(missing_ord.any()):
            rebuilt = _add_event_ordinal(
                ev.loc[missing_ord, ["candidate_uid", "close_ts", "test_month"]],
                close_col="close_ts",
            )
            ev.loc[missing_ord, "event_ordinal"] = rebuilt["event_ordinal"].to_numpy()
            ev.loc[missing_ord, "scored_row_id"] = rebuilt["scored_row_id"].to_numpy()
        ev["event_ordinal"] = ev["event_ordinal"].astype(int)
        ev["frozen_event_id"] = ev["scored_row_id"].astype(str)
    else:
        ev = _add_event_ordinal(ev, close_col="close_ts")
    ev = ev.rename(columns={"close_ts": "canonical_close_ts"})
    return ev


def _map_offset_events_to_canonical_universe(
    *,
    offset_events: pd.DataFrame,
    canonical_events: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if canonical_events.empty:
        return pd.DataFrame(), pd.DataFrame()
    if offset_events.empty:
        merged = canonical_events.copy()
        merged["offset_close_ts"] = pd.NaT
        merged["mapping_status"] = "unmapped"
        return pd.DataFrame(), merged

    off = _add_event_ordinal(offset_events, close_col="close_ts")
    merged = canonical_events.merge(
        off,
        on=["test_month", "candidate_uid", "event_ordinal", "frozen_event_id"],
        how="left",
        suffixes=("", "_offset"),
        validate="one_to_one",
    )
    merged = merged.rename(columns={"close_ts": "offset_close_ts"})
    merged["mapping_status"] = np.where(merged["offset_close_ts"].notna(), "mapped", "unmapped")
    mapped = merged[merged["offset_close_ts"].notna()].copy()
    if not mapped.empty:
        mapped["close_ts"] = mapped["offset_close_ts"]
        for col in ["library", "target_gross_pips", "target_gross_pos"]:
            off_col = f"{col}_offset"
            if off_col in mapped.columns:
                mapped[col] = mapped[off_col]
    return mapped, merged


def _score_frozen_predictions(
    *,
    events: pd.DataFrame,
    manifest: pd.DataFrame,
    wfo_cfg: dict[str, Any],
) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame()
    if CatBoostClassifier is None:
        raise RuntimeError("CatBoost is required for frozen offset screen")
    x = events.copy()
    x["close_ts"] = pd.to_datetime(x["close_ts"], utc=True, errors="coerce")
    x = x[x["close_ts"].notna()].copy()
    x["test_month"] = x["close_ts"].dt.strftime("%Y-%m")

    out_parts: list[pd.DataFrame] = []
    model_cache: dict[str, Any] = {}
    for month, g in x.groupby("test_month", sort=True):
        row = manifest[manifest["test_month"].astype(str) == str(month)]
        if row.empty:
            continue
        rec = row.iloc[0]
        model_path = Path(str(rec["model_cbm_path"]))
        thr_path = Path(str(rec["model_threshold_json_path"]))
        if not model_path.exists() or not thr_path.exists():
            raise FileNotFoundError(f"missing frozen model artifacts for {month}")
        if str(model_path) not in model_cache:
            model = CatBoostClassifier()
            model.load_model(str(model_path))
            model_cache[str(model_path)] = model
        model = model_cache[str(model_path)]
        thr_cfg = _load_threshold_json(thr_path)
        feats = [str(c) for c in json.loads(str(rec["features_json"])) if str(c) in g.columns]
        missing = [c for c in json.loads(str(rec["features_json"])) if c not in g.columns]
        if missing:
            raise ValueError(f"missing frozen model features for {month}: {missing}")
        arr = g[feats].astype(float).to_numpy()
        pred_prob = model.predict_proba(arr)[:, 1].astype(float)
        te = g.copy()
        te["pred_prob"] = pred_prob
        schedule = thr_cfg.get("threshold_schedule", {}) or {}
        static_thr = float(thr_cfg.get("threshold_exec", 0.5))
        mode = str(thr_cfg.get("threshold_source", "default"))
        day_str = te["close_ts"].dt.strftime("%Y-%m-%d")
        thresholds = []
        sources = []
        for d in day_str:
            if d in schedule:
                thresholds.append(float(schedule[d]))
                sources.append(f"{mode}:schedule")
            else:
                thresholds.append(static_thr)
                sources.append(f"{mode}:static_fallback")
        te["threshold_exec"] = np.asarray(thresholds, dtype=float)
        te["selected_exec"] = (
            te["pred_prob"].to_numpy(dtype=float) >= te["threshold_exec"].to_numpy(dtype=float)
        ).astype(int)
        te["threshold_mode"] = mode
        te["threshold_days"] = int(thr_cfg.get("rolling_threshold_days", 0) or 0)
        te["threshold_source"] = np.asarray(sources, dtype=object)
        keep_cols = [
            "library",
            "test_month",
            "close_ts",
            "candidate_uid",
            "pred_prob",
            "target_gross_pips",
            "target_gross_pos",
            "threshold_mode",
            "threshold_days",
            "threshold_exec",
            "selected_exec",
            "threshold_source",
        ]
        for extra_col in [
            "event_ordinal",
            "scored_row_id",
            "frozen_event_id",
            "canonical_close_ts",
        ]:
            if extra_col in te.columns:
                keep_cols.append(extra_col)
        out_parts.append(te[keep_cols].copy())
    return pd.concat(out_parts, ignore_index=True) if out_parts else pd.DataFrame()


def _load_canonical_selected(
    pred_path: Path, schedule_path: Path, canonical_events: pd.DataFrame
) -> pd.DataFrame:
    try:
        import pyarrow.parquet as pq

        avail_cols = set(pq.read_schema(pred_path).names) if pred_path.exists() else set()
    except Exception:
        avail_cols = set()
    wanted_cols = [
        "candidate_uid",
        "close_ts",
        "selected_exec",
        "test_month",
        "event_ordinal",
        "frozen_event_id",
        "scored_row_id",
    ]
    use_cols = [c for c in wanted_cols if c in avail_cols] if avail_cols else wanted_cols[:4]
    pred = _load_parquet(pred_path, columns=use_cols)
    if pred.empty:
        return pd.DataFrame(
            columns=["candidate_uid", "close_ts", "test_month", "event_ordinal", "frozen_event_id"]
        )
    pred["selected_exec"] = (
        pd.to_numeric(pred["selected_exec"], errors="coerce").fillna(0).astype(int)
    )
    pred = pred[pred["selected_exec"] == 1].copy()
    pred["close_ts"] = pd.to_datetime(pred["close_ts"], utc=True, errors="coerce")
    pred["test_month"] = pred["test_month"].astype(str)
    parts = pred["candidate_uid"].astype(str).str.split("|", n=4, expand=True)
    pred["state_id"] = parts[4].astype(str)
    pred["bar_ticks"] = pd.to_numeric(parts[2], errors="coerce").astype(int)
    pred["horizon"] = pd.to_numeric(parts[3].astype(str).str.lstrip("hH"), errors="coerce").astype(
        int
    )
    sched = pd.read_csv(schedule_path)
    keep = sched[["test_month", "state_id", "bar_ticks", "horizon"]].drop_duplicates().copy()
    keep["test_month"] = keep["test_month"].astype(str)
    out = pred.merge(keep, on=["test_month", "state_id", "bar_ticks", "horizon"], how="inner")
    if "scored_row_id" in out.columns and out["scored_row_id"].notna().any():
        out["frozen_event_id"] = out["scored_row_id"].astype(str)
    if (
        "event_ordinal" in out.columns
        and "frozen_event_id" in out.columns
        and out["frozen_event_id"].notna().any()
    ):
        out["event_ordinal"] = pd.to_numeric(out["event_ordinal"], errors="coerce").astype("Int64")
        return (
            out[out["event_ordinal"].notna()]
            .assign(event_ordinal=lambda x: x["event_ordinal"].astype(int))[
                ["candidate_uid", "close_ts", "test_month", "event_ordinal", "frozen_event_id"]
            ]
            .drop_duplicates()
            .reset_index(drop=True)
        )
    if canonical_events.empty:
        return (
            out[["candidate_uid", "close_ts", "test_month"]]
            .drop_duplicates()
            .reset_index(drop=True)
        )
    event_keys = canonical_events[
        ["candidate_uid", "test_month", "event_ordinal", "frozen_event_id", "canonical_close_ts"]
    ].drop_duplicates()
    merged = out.merge(
        event_keys,
        left_on=["candidate_uid", "test_month", "close_ts"],
        right_on=["candidate_uid", "test_month", "canonical_close_ts"],
        how="inner",
    )
    return (
        merged[["candidate_uid", "close_ts", "test_month", "event_ordinal", "frozen_event_id"]]
        .drop_duplicates()
        .reset_index(drop=True)
    )


def _selected_overlap_rate_by_event_id(
    canonical_selected: pd.DataFrame, current_selected: pd.DataFrame
) -> float:
    if canonical_selected.empty and current_selected.empty:
        return 1.0
    if canonical_selected.empty or current_selected.empty:
        return 0.0
    keys = ["test_month", "candidate_uid", "event_ordinal"]
    lhs = canonical_selected[keys].drop_duplicates()
    rhs = current_selected[keys].drop_duplicates()
    left_idx = lhs.set_index(keys).index
    right_idx = rhs.set_index(keys).index
    inter = left_idx.intersection(right_idx)
    union = left_idx.union(right_idx)
    return float(len(inter) / len(union)) if len(union) else float("nan")


def _canonical_state_coverage(
    *,
    selected_keys: pd.DataFrame,
    canonical_schedule: pd.DataFrame,
) -> tuple[float, pd.DataFrame]:
    if canonical_schedule.empty:
        return float("nan"), pd.DataFrame()
    cur = selected_keys.copy()
    if cur.empty:
        cur = pd.DataFrame(columns=["test_month", "state_key"])
    else:
        parts = cur["candidate_uid"].astype(str).str.split("|", n=4, expand=True)
        cur["state_id"] = parts[4].astype(str)
        cur["bar_ticks"] = pd.to_numeric(parts[2], errors="coerce").astype(int)
        cur["horizon"] = pd.to_numeric(
            parts[3].astype(str).str.lstrip("hH"), errors="coerce"
        ).astype(int)
        cur["state_key"] = (
            cur["state_id"].astype(str)
            + "|"
            + cur["bar_ticks"].astype(str)
            + "|"
            + cur["horizon"].astype(str)
        )
        cur = cur[["test_month", "state_key"]].drop_duplicates().copy()
    sched = canonical_schedule.copy()
    sched["covered"] = sched.set_index(["test_month", "state_key"]).index.isin(
        cur.set_index(["test_month", "state_key"]).index
    )
    monthly = sched.groupby("test_month", as_index=False).agg(
        canonical_state_count=("state_key", "nunique"),
        covered_state_count=("covered", "sum"),
    )
    monthly["canonical_state_coverage_rate"] = (
        monthly["covered_state_count"] / monthly["canonical_state_count"]
    )
    overall = float(sched["covered"].mean()) if len(sched) else float("nan")
    return overall, monthly


def _load_canonical_schedule(schedule_path: Path) -> pd.DataFrame:
    sched = pd.read_csv(schedule_path)
    sched["test_month"] = sched["test_month"].astype(str)
    if "state_key" not in sched.columns:
        sched["state_key"] = (
            sched["state_id"].astype(str)
            + "|"
            + pd.to_numeric(sched["bar_ticks"], errors="coerce").astype(int).astype(str)
            + "|"
            + pd.to_numeric(sched["horizon"], errors="coerce").astype(int).astype(str)
        )
    return (
        sched[["test_month", "state_key", "state_id", "bar_ticks", "horizon"]]
        .drop_duplicates()
        .reset_index(drop=True)
    )


def _build_baseline_parity(
    *,
    symbol: str,
    canonical_events: pd.DataFrame,
    mapped_events: pd.DataFrame,
    current_selected: pd.DataFrame,
    canonical_selected: pd.DataFrame,
) -> tuple[dict[str, Any], pd.DataFrame]:
    canonical_event_rows_total = int(len(canonical_events))
    mapped_event_rows_total = int(len(mapped_events))
    canonical_selected_rows_total = int(len(canonical_selected))
    current_selected_rows_total = int(len(current_selected))
    event_rows_exact = canonical_event_rows_total == mapped_event_rows_total
    selected_rows_exact = canonical_selected_rows_total == current_selected_rows_total
    overlap_rate = _selected_overlap_rate_by_event_id(canonical_selected, current_selected)
    selected_overlap_exact = np.isfinite(overlap_rate) and abs(float(overlap_rate) - 1.0) < 1e-12

    missing = canonical_events[
        ["frozen_event_id", "candidate_uid", "test_month", "canonical_close_ts"]
    ].merge(
        mapped_events[["frozen_event_id", "offset_close_ts"]].drop_duplicates(),
        on="frozen_event_id",
        how="left",
    )
    missing["mismatch_reason"] = np.where(missing["offset_close_ts"].notna(), "matched", "unmapped")
    mismatches = missing[missing["mismatch_reason"] != "matched"].copy()

    summary = {
        "symbol": symbol,
        "baseline_event_rows_canonical": canonical_event_rows_total,
        "baseline_event_rows_offset0": mapped_event_rows_total,
        "baseline_selected_rows_canonical": canonical_selected_rows_total,
        "baseline_selected_rows_offset0": current_selected_rows_total,
        "baseline_event_rows_exact_match": bool(event_rows_exact),
        "baseline_selected_rows_exact_match": bool(selected_rows_exact),
        "baseline_selected_overlap_event_id": float(overlap_rate),
        "baseline_parity_pass": bool(
            event_rows_exact and selected_rows_exact and selected_overlap_exact
        ),
        "unmapped_event_rows_total": int((missing["mismatch_reason"] == "unmapped").sum()),
    }
    return summary, mismatches


def _baseline_gate(summary: dict[str, Any]) -> tuple[bool, str]:
    reasons: list[str] = []
    if _safe_int(summary.get("unmapped_event_rows_total")) > 0:
        reasons.append("unmapped_event_rows")
    selected_rows_delta_pct = _pct_delta(
        summary.get("baseline_selected_rows_offset0"),
        summary.get("baseline_selected_rows_canonical"),
    )
    if np.isfinite(selected_rows_delta_pct) and abs(float(selected_rows_delta_pct)) > 20.0:
        reasons.append("selected_rows_delta_gt_20pct")
    return len(reasons) == 0, ",".join(reasons)


def _classify_offset_row(row: dict[str, Any]) -> tuple[str, str, str]:
    reasons: list[str] = []
    diagnostics: list[str] = []
    if (
        np.isfinite(row["selected_rows_delta_pct"])
        and abs(float(row["selected_rows_delta_pct"])) > 20.0
    ):
        reasons.append("selected_rows_delta_gt_20pct")
    if np.isfinite(row["trade_rows_delta_pct"]) and abs(float(row["trade_rows_delta_pct"])) > 20.0:
        reasons.append("trade_rows_delta_gt_20pct")
    if (
        np.isfinite(float(row["lb95_trade_mean_gross_pips_delta"]))
        and float(row["lb95_trade_mean_gross_pips_delta"]) < -0.25
    ):
        reasons.append("lb95_trade_mean_gross_drop")
    if (
        np.isfinite(float(row["lb95_trade_mean_net_pips_delta"]))
        and float(row["lb95_trade_mean_net_pips_delta"]) < -0.25
    ):
        reasons.append("lb95_trade_mean_net_drop")
    if (
        np.isfinite(float(row["canonical_state_coverage_rate"]))
        and float(row["canonical_state_coverage_rate"]) < 0.90
    ):
        diagnostics.append("canonical_state_coverage_lt_90pct")
    if (
        np.isfinite(float(row["candidate_uid_close_ts_overlap_rate"]))
        and float(row["candidate_uid_close_ts_overlap_rate"]) < 0.60
    ):
        diagnostics.append("selected_overlap_lt_0.60")
    status = "degraded" if reasons else "ok"
    return status, ",".join(reasons), ",".join(diagnostics)


def _build_frozen_row(
    *,
    symbol: str,
    offset: int,
    stage_root: Path,
    canonical_selected: pd.DataFrame,
    canonical_events: pd.DataFrame,
    canonical_schedule: pd.DataFrame,
    baseline_row: dict[str, Any] | None,
    mapping_diag: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], pd.DataFrame]:
    pred_path = stage_root / "wfo" / f"{symbol}_oco_monthly_predictions.parquet"
    current_selected = _load_canonical_selected(
        pred_path,
        stage_root / "reduced_core_rolling" / f"{symbol}_oco_reduced_state_schedule.csv",
        canonical_events,
    )
    overlap_rate = _selected_overlap_rate_by_event_id(canonical_selected, current_selected)
    coverage_rate, coverage_monthly = _canonical_state_coverage(
        selected_keys=current_selected, canonical_schedule=canonical_schedule
    )
    robust = _load_csv(stage_root / "robustness" / f"{symbol}_oco_robustness_summary.csv")
    if robust.empty:
        return {
            "symbol": symbol,
            "offset": int(offset),
            "offset_status": "failed_pipeline",
            "failure_reason": "missing_robustness_summary",
        }, coverage_monthly
    robust["quantile"] = pd.to_numeric(robust["quantile"], errors="coerce")
    robust = robust[np.isclose(robust["quantile"], 0.9, equal_nan=False)].copy()
    robust = robust[robust["universe_mode"].astype(str) == "reduced_core_schedule"].copy()
    row0 = robust.iloc[0].to_dict()
    stop = _load_csv(stage_root / "stop_limit" / "summary.csv")
    stop_row = stop.iloc[0].to_dict() if not stop.empty else {}
    tick = _load_csv(stage_root / "tick_exact" / f"{symbol}_oco_tick_exact_summary.csv")
    tick_row = tick.iloc[0].to_dict() if not tick.empty else {}

    out = {
        "symbol": symbol,
        "offset": int(offset),
        "selected_rows_total": int(len(current_selected)),
        "trade_rows_total": _safe_int(row0.get("rows")),
        "mean_gross_pips": _safe_float(row0.get("mean_gross_pips")),
        "mean_net_pips": _safe_float(row0.get("mean_net_pips_costplus_0.10")),
        "lb95_trade_mean_gross_pips": _safe_float(row0.get("lb95_trade_mean_gross_pips")),
        "lb95_trade_mean_net_pips": _safe_float(row0.get("lb95_trade_mean_net_pips_costplus_0.10")),
        "positive_months": _safe_int(row0.get("positive_months")),
        "candidate_uid_close_ts_overlap_rate": overlap_rate,
        "canonical_state_coverage_rate": coverage_rate,
        "canonical_event_rows_total": int(
            (mapping_diag or {}).get("canonical_event_rows_total", len(canonical_events))
        ),
        "mapped_event_rows_total": _safe_int((mapping_diag or {}).get("mapped_event_rows_total")),
        "unmapped_event_rows_total": _safe_int(
            (mapping_diag or {}).get("unmapped_event_rows_total")
        ),
        "baseline_selected_rows_exact_match": np.nan,
        "baseline_event_rows_exact_match": np.nan,
        "execution_fill_rate": 1.0 - max(0.0, 1.0 - _safe_float(stop_row.get("touch_found_rate"))),
        "execution_no_touch_rate": float(1.0 - _safe_float(stop_row.get("touch_found_rate")))
        if stop_row
        else float("nan"),
        "execution_overshoot_p95_pips": _safe_float(stop_row.get("tick_overshoot_p95_pips")),
        "tick_exact_pass": str(tick_row.get("overall_pass", False)).lower() == "true",
        "selected_rows_delta_pct": 0.0,
        "trade_rows_delta_pct": 0.0,
        "mean_gross_pips_delta": 0.0,
        "mean_net_pips_delta": 0.0,
        "lb95_trade_mean_gross_pips_delta": 0.0,
        "lb95_trade_mean_net_pips_delta": 0.0,
        "offset_status": "ok",
        "degrade_reasons": "",
        "diagnostic_reasons": "",
        "failure_reason": "",
        "prediction_path": str(pred_path),
        "reduced_state_schedule_csv": str(
            stage_root / "reduced_core_rolling" / f"{symbol}_oco_reduced_state_schedule.csv"
        ),
        "stop_limit_detail_csv": str(
            stage_root / "stop_limit" / f"{symbol}_stop_limit_tickfill_detail.csv"
        ),
    }
    if baseline_row is not None:
        out["selected_rows_delta_pct"] = _pct_delta(
            out["selected_rows_total"], baseline_row.get("selected_rows_total")
        )
        out["trade_rows_delta_pct"] = _pct_delta(
            out["trade_rows_total"], baseline_row.get("trade_rows_total")
        )
        out["mean_gross_pips_delta"] = _safe_float(out["mean_gross_pips"]) - _safe_float(
            baseline_row.get("mean_gross_pips")
        )
        out["mean_net_pips_delta"] = _safe_float(out["mean_net_pips"]) - _safe_float(
            baseline_row.get("mean_net_pips")
        )
        out["lb95_trade_mean_gross_pips_delta"] = _safe_float(
            out["lb95_trade_mean_gross_pips"]
        ) - _safe_float(baseline_row.get("lb95_trade_mean_gross_pips"))
        out["lb95_trade_mean_net_pips_delta"] = _safe_float(
            out["lb95_trade_mean_net_pips"]
        ) - _safe_float(baseline_row.get("lb95_trade_mean_net_pips"))
        out["offset_status"], out["degrade_reasons"], out["diagnostic_reasons"] = (
            _classify_offset_row(out)
        )
    return out, coverage_monthly.assign(symbol=symbol, offset=int(offset))


def _write_report(
    symbol: str,
    summary_row: dict[str, Any],
    by_offset: pd.DataFrame,
    coverage: pd.DataFrame,
    out_path: Path,
) -> None:
    def _table(df: pd.DataFrame) -> str:
        if df.empty:
            return "_empty_"
        try:
            return df.to_markdown(index=False)
        except Exception:
            return "```\n" + df.to_string(index=False) + "\n```"

    lines = [
        "# Frozen-Month Offset Screen",
        "",
        f"- symbol: `{symbol}`",
        f"- classification: `{summary_row.get('phase_classification', 'unknown')}`",
        f"- offsets_evaluated: `{summary_row.get('offsets_total', 0)}`",
        "- model_frozen: `true`",
        "- reduced_core_states_frozen: `true`",
        "- retraining_per_offset: `false`",
        "",
        "## By Offset",
        "",
        _table(by_offset),
        "",
        "## Canonical State Coverage",
        "",
        _table(coverage),
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _cleanup_completed_symbol_artifacts(
    *,
    symbol: str,
    offsets: list[int],
    offset_bar_dir: Path,
    out_dir: Path,
    bar_ticks_grid: list[int],
) -> None:
    for offset in offsets:
        shutil.rmtree(_offset_stage_root(out_dir, symbol, int(offset)), ignore_errors=True)
        for bar_ticks in sorted(set(int(x) for x in bar_ticks_grid if int(x) > 0)):
            path = (
                offset_bar_dir / f"{symbol}_{int(bar_ticks)}tick_offset_{int(offset):03d}.parquet"
            )
            with contextlib.suppress(Exception):
                path.unlink(missing_ok=True)


def run(
    *,
    symbols: list[str],
    offsets: list[int],
    tick_root: Path,
    offset_bar_dir: Path,
    frozen_root: Path,
    out_dir: Path,
    retention_mode: str,
    cleanup_completed_artifacts: bool,
    fail_fast: bool,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    out_dir.mkdir(parents=True, exist_ok=True)
    frozen_root.mkdir(parents=True, exist_ok=True)
    _ensure_offset_bars(
        symbols=symbols,
        offsets=offsets,
        tick_root=tick_root,
        offset_bar_dir=offset_bar_dir,
        bar_ticks_grid=list(DEFAULT_BAR_TICKS_GRID),
        overwrite=False,
        fail_fast=fail_fast,
    )

    summary_rows: list[dict[str, Any]] = []
    by_offset_rows: list[dict[str, Any]] = []
    coverage_rows: list[dict[str, Any]] = []

    for symbol in symbols:
        manifest, quantiles_by_ticks, canonical_paths = _ensure_canonical_exports(
            symbol=symbol, frozen_root=frozen_root, fail_fast=fail_fast
        )
        wfo_cfg = _load_yaml(canonical_paths["wfo_cfg"])
        canonical_events = _load_canonical_event_universe(
            _canonical_events_path(canonical_paths, symbol, wfo_cfg),
            canonical_paths["pred_path"],
        )
        canonical_schedule = _load_canonical_schedule(canonical_paths["reduced_schedule_csv"])
        canonical_selected = _load_canonical_selected(
            canonical_paths["pred_path"], canonical_paths["reduced_schedule_csv"], canonical_events
        )
        symbol_rows: list[dict[str, Any]] = []
        baseline_valid = True
        for offset in offsets:
            if int(offset) != 0 and not baseline_valid:
                row = {
                    "symbol": symbol,
                    "offset": int(offset),
                    "offset_status": "baseline_parity_failed",
                    "failure_reason": "offset_000_baseline_parity_failed",
                }
                symbol_rows.append(row)
                by_offset_rows.append(row)
                continue
            stage_root = _offset_stage_root(out_dir, symbol, int(offset))
            reports_dir = stage_root / "tmp_reports"
            for d in [
                stage_root / "velocity",
                stage_root / "wfo",
                stage_root / "stop_limit",
                stage_root / "reduced_core_rolling",
                stage_root / "robustness",
                stage_root / "tick_exact",
                reports_dir,
            ]:
                d.mkdir(parents=True, exist_ok=True)
            try:
                velocity_path = _build_velocity_for_offset(
                    symbol=symbol,
                    offset=int(offset),
                    offset_bar_dir=offset_bar_dir,
                    stage_root=stage_root,
                    bar_ticks_grid=list(DEFAULT_BAR_TICKS_GRID),
                )
                offset_events = _build_frozen_events(
                    symbol=symbol,
                    velocity_dir=velocity_path,
                    candidate_dir=canonical_paths["candidate_dir"],
                    quantiles_by_ticks=quantiles_by_ticks,
                    wfo_cfg=wfo_cfg,
                )
                mapped_events, mapping_details = _map_offset_events_to_canonical_universe(
                    offset_events=offset_events,
                    canonical_events=canonical_events,
                )
                preds = _score_frozen_predictions(
                    events=mapped_events, manifest=manifest, wfo_cfg=wfo_cfg
                )
                preds.to_parquet(
                    stage_root / "wfo" / f"{symbol}_oco_monthly_predictions.parquet", index=False
                )
                shutil.copy2(
                    canonical_paths["reduced_schedule_csv"],
                    stage_root
                    / "reduced_core_rolling"
                    / f"{symbol}_oco_reduced_state_schedule.csv",
                )
            except Exception as exc:
                row = {
                    "symbol": symbol,
                    "offset": int(offset),
                    "offset_status": "failed_pipeline",
                    "failure_reason": str(exc),
                }
                symbol_rows.append(row)
                by_offset_rows.append(row)
                continue

            for cmd in [
                [
                    sys.executable,
                    str(ROOT / "scripts/analyze_oco_stop_limit_tickfill.py"),
                    "--symbols",
                    symbol,
                    "--pred-paths",
                    str(stage_root / "wfo" / f"{symbol}_oco_monthly_predictions.parquet"),
                    "--velocity-dir",
                    str(stage_root / "velocity"),
                    "--tick-root",
                    str(tick_root),
                    "--caps",
                    DEFAULT_STOP_LIMIT_CAPS,
                    "--use-exec-selected",
                    "true",
                    "--quantile",
                    "0.9",
                    "--out-dir",
                    str(stage_root / "stop_limit"),
                ],
                [
                    sys.executable,
                    str(ROOT / "scripts/analyze_oco_monthly_wfo_robustness.py"),
                    "--pred-path",
                    str(stage_root / "wfo" / f"{symbol}_oco_monthly_predictions.parquet"),
                    "--quantiles",
                    "0.5,0.6,0.7,0.8,0.9,0.95",
                    "--bootstrap-paths",
                    "600",
                    "--stress-extra-cost-grid",
                    DEFAULT_STRESS_COST_GRID,
                    "--use-exec-selection",
                    "true",
                    "--execution-quantile",
                    "0.9",
                    "--reduced-state-schedule-csv",
                    str(
                        stage_root
                        / "reduced_core_rolling"
                        / f"{symbol}_oco_reduced_state_schedule.csv"
                    ),
                    "--out-summary-csv",
                    str(stage_root / "robustness" / f"{symbol}_oco_robustness_summary.csv"),
                    "--out-monthly-csv",
                    str(stage_root / "robustness" / f"{symbol}_oco_robustness_monthly.csv"),
                    "--report-out",
                    str(reports_dir / f"{symbol.lower()}_offset_{int(offset):03d}_robustness.md"),
                ],
                [
                    sys.executable,
                    str(ROOT / "scripts/verify_oco_tick_exact_shortlist.py"),
                    "--symbol",
                    symbol,
                    "--dataset-dir",
                    str(stage_root / "velocity"),
                    "--pred-path",
                    str(stage_root / "wfo" / f"{symbol}_oco_monthly_predictions.parquet"),
                    "--shortlist-state-csv",
                    str(
                        stage_root
                        / "reduced_core_rolling"
                        / f"{symbol}_oco_reduced_state_schedule.csv"
                    ),
                    "--locked-quantile",
                    "0.9",
                    "--selection-mode",
                    "auto",
                    "--family-required",
                    "oco_first_touch_clean",
                    "--oco-hold-mode",
                    "from_touch",
                    "--oco-include-no-touch",
                    "true",
                    "--out-summary-csv",
                    str(stage_root / "tick_exact" / f"{symbol}_oco_tick_exact_summary.csv"),
                    "--out-monthly-csv",
                    str(stage_root / "tick_exact" / f"{symbol}_oco_tick_exact_monthly.csv"),
                    "--out-state-csv",
                    str(stage_root / "tick_exact" / f"{symbol}_oco_tick_exact_state.csv"),
                    "--report-out",
                    str(reports_dir / f"{symbol.lower()}_offset_{int(offset):03d}_tick_exact.md"),
                ],
            ]:
                ok, msg = _run_cmd(cmd, fail_fast=fail_fast)
                if not ok:
                    row = {
                        "symbol": symbol,
                        "offset": int(offset),
                        "offset_status": "failed_pipeline",
                        "failure_reason": msg,
                    }
                    symbol_rows.append(row)
                    by_offset_rows.append(row)
                    break
            else:
                baseline = symbol_rows[0] if symbol_rows else None
                row, coverage = _build_frozen_row(
                    symbol=symbol,
                    offset=int(offset),
                    stage_root=stage_root,
                    canonical_selected=canonical_selected,
                    canonical_events=canonical_events,
                    canonical_schedule=canonical_schedule,
                    baseline_row=baseline
                    if baseline and int(baseline.get("offset", -1)) == 0
                    else None,
                    mapping_diag={
                        "canonical_event_rows_total": len(canonical_events),
                        "mapped_event_rows_total": len(mapped_events),
                        "unmapped_event_rows_total": int(
                            (mapping_details.get("mapping_status") == "unmapped").sum()
                        )
                        if not mapping_details.empty
                        else len(canonical_events),
                    },
                )
                if int(offset) == 0:
                    current_selected = _load_canonical_selected(
                        stage_root / "wfo" / f"{symbol}_oco_monthly_predictions.parquet",
                        stage_root
                        / "reduced_core_rolling"
                        / f"{symbol}_oco_reduced_state_schedule.csv",
                        canonical_events,
                    )
                    baseline_summary, baseline_mismatches = _build_baseline_parity(
                        symbol=symbol,
                        canonical_events=canonical_events,
                        mapped_events=mapped_events,
                        current_selected=current_selected,
                        canonical_selected=canonical_selected,
                    )
                    baseline_gate_pass, baseline_gate_reasons = _baseline_gate(baseline_summary)
                    baseline_summary["baseline_gate_pass"] = bool(baseline_gate_pass)
                    baseline_summary["baseline_gate_reasons"] = baseline_gate_reasons
                    baseline_summary["baseline_selected_rows_delta_pct"] = _pct_delta(
                        baseline_summary.get("baseline_selected_rows_offset0"),
                        baseline_summary.get("baseline_selected_rows_canonical"),
                    )
                    row.update(baseline_summary)
                    pd.DataFrame([baseline_summary]).to_csv(
                        out_dir / f"{symbol}_frozen_baseline_parity_summary.csv", index=False
                    )
                    baseline_mismatches.to_csv(
                        out_dir / f"{symbol}_frozen_baseline_mismatches.csv", index=False
                    )
                    baseline_valid = bool(baseline_gate_pass)
                    if not baseline_valid:
                        row["offset_status"] = "baseline_material_drift"
                        row["failure_reason"] = (
                            baseline_gate_reasons or "offset_000_baseline_material_drift"
                        )
                symbol_rows.append(row)
                by_offset_rows.append(row)
                coverage_rows.extend(coverage.to_dict(orient="records"))
                if str(retention_mode) == "compact":
                    keep = int(offset) == 0 or row.get("offset_status") in {
                        "degraded",
                        "baseline_parity_failed",
                        "baseline_material_drift",
                    }
                    if not keep:
                        shutil.rmtree(stage_root, ignore_errors=True)

        sym_df = pd.DataFrame(symbol_rows).sort_values("offset").reset_index(drop=True)
        status_col = sym_df.get("offset_status", pd.Series(dtype=str)).astype(str)
        classification = (
            "material_drift_under_frozen_month"
            if status_col.isin(
                ["degraded", "failed_pipeline", "baseline_parity_failed", "baseline_material_drift"]
            ).any()
            else "stable_under_frozen_month"
        )
        summary_rows.append(
            {
                "symbol": symbol,
                "offsets_total": int(len(sym_df)),
                "phase_classification": classification,
                "retention_mode": retention_mode,
                "report_path": str(
                    (out_dir / "reports" / f"{symbol.lower()}_frozen_offset_screen.md").relative_to(
                        ROOT
                    )
                )
                if out_dir.is_relative_to(ROOT)
                else str(out_dir / "reports" / f"{symbol.lower()}_frozen_offset_screen.md"),
            }
        )
        sym_coverage = (
            pd.DataFrame([r for r in coverage_rows if r.get("symbol") == symbol])
            if coverage_rows
            else pd.DataFrame()
        )
        if not sym_coverage.empty and {"offset", "test_month"}.issubset(sym_coverage.columns):
            sym_coverage = sym_coverage.sort_values(["offset", "test_month"]).reset_index(drop=True)
        _write_report(
            symbol=symbol,
            summary_row=summary_rows[-1],
            by_offset=sym_df,
            coverage=sym_coverage,
            out_path=out_dir / "reports" / f"{symbol.lower()}_frozen_offset_screen.md",
        )
        sym_df.to_csv(out_dir / f"{symbol}_frozen_offset_by_offset.csv", index=False)
        if bool(cleanup_completed_artifacts):
            _cleanup_completed_symbol_artifacts(
                symbol=symbol,
                offsets=offsets,
                offset_bar_dir=offset_bar_dir,
                out_dir=out_dir,
                bar_ticks_grid=list(DEFAULT_BAR_TICKS_GRID),
            )

    summary_df = pd.DataFrame(summary_rows).sort_values("symbol").reset_index(drop=True)
    by_offset_df = (
        pd.DataFrame(by_offset_rows).sort_values(["symbol", "offset"]).reset_index(drop=True)
        if by_offset_rows
        else pd.DataFrame()
    )
    coverage_df = (
        pd.DataFrame(coverage_rows)
        .sort_values(["symbol", "offset", "test_month"])
        .reset_index(drop=True)
        if coverage_rows
        else pd.DataFrame()
    )
    summary_df.to_csv(out_dir / "frozen_offset_screen_summary.csv", index=False)
    coverage_df.to_csv(out_dir / "frozen_offset_state_coverage.csv", index=False)
    return summary_df, by_offset_df


def main() -> None:
    p = argparse.ArgumentParser(description="Run frozen-month offset screen")
    p.add_argument("--symbols", default=",".join(ACTIVE_SYMBOLS))
    p.add_argument("--offsets", default=",".join(str(x) for x in DEFAULT_SCREEN_OFFSETS))
    p.add_argument("--tick-root", default=DEFAULT_TICK_ROOT)
    p.add_argument("--offset-bar-dir", default=DEFAULT_OFFSET_BAR_DIR)
    p.add_argument("--frozen-root", default=DEFAULT_FROZEN_ROOT)
    p.add_argument(
        "--out-dir", default=str(Path(DEFAULT_OUT_DIR).with_name("offset_robustness_frozen"))
    )
    p.add_argument("--retention-mode", choices=["compact", "full"], default="compact")
    p.add_argument("--cleanup-completed-artifacts", action="store_true")
    p.add_argument("--fail-fast", action="store_true")
    args = p.parse_args()

    run(
        symbols=_parse_symbols(str(args.symbols)),
        offsets=sorted(set(_parse_csv_ints(str(args.offsets)))),
        tick_root=Path(str(args.tick_root)),
        offset_bar_dir=Path(str(args.offset_bar_dir)),
        frozen_root=Path(str(args.frozen_root)),
        out_dir=Path(str(args.out_dir)),
        retention_mode=str(args.retention_mode),
        cleanup_completed_artifacts=bool(args.cleanup_completed_artifacts),
        fail_fast=bool(args.fail_fast),
    )


if __name__ == "__main__":
    main()
