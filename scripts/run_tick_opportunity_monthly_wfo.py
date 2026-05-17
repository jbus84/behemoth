#!/usr/bin/env python3
"""Strict monthly WFO on tick opportunity events (3M train -> next month test).

Leakage controls:
- Candidate universe is filtered using train-only candidate metrics
  (`mean_gross_pips_train`, `train_count`) from mining outputs.
- Each scored test month is predicted using only prior rolling train months.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

try:
    import yaml
except Exception:
    yaml = None  # type: ignore[assignment]

try:
    from catboost import CatBoostClassifier
except Exception:
    CatBoostClassifier = None  # type: ignore[assignment]

try:
    from scripts.build_tick_opportunity_ml_dataset import (
        _build_directional_events,
        _build_oco_events,
    )
    from scripts.run_tick_opportunity_mining import (
        _parse_ints,
        _prepare_frame,
        _quantiles,
    )
except ModuleNotFoundError:
    from build_tick_opportunity_ml_dataset import (  # type: ignore
        _build_directional_events,
        _build_oco_events,
    )
    from run_tick_opportunity_mining import (  # type: ignore
        _parse_ints,
        _prepare_frame,
        _quantiles,
    )


DEFAULTS: dict[str, Any] = {
    "symbol": "EURUSD",
    "dataset_dir": "data/analysis/tick_velocity",
    "candidate_dir": "data/analysis/tick_opportunity_mining",
    "library": "both",  # directional|oco|both
    "train_years_for_state_fit": "2022,2023,2024",
    "eval_year": 2025,
    "eval_start_month": "",
    "eval_end_month": "",
    "min_candidate_train_count": 15000,
    "max_candidates_per_library": 300,
    "max_events_per_candidate": 8000,
    "rolling_train_months": 3,
    "min_month_train_rows": 5000,
    "min_month_test_rows": 1500,
    "min_candidate_rows_in_train_window": 300,
    "threshold_quantiles": "0.5,0.6,0.7,0.8,0.9,0.95",
    "oco_include_no_touch": True,
    "threshold_mode": "rolling_days",  # rolling_days|train_quantile
    "rolling_threshold_days": 20,
    "rolling_threshold_min_history": 300,
    "execution_quantile": 0.9,
    "oco_hold_mode": "from_touch",  # from_touch|from_start
    "seed": 42,
    "out_dir": "data/analysis/tick_opportunity_mining/wfo_m3to1",
    "report_out": "docs/analysis/eurusd_tick_opportunity_monthly_wfo_report.md",
}


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    if yaml is None:
        raise RuntimeError("PyYAML required for --config")
    obj = yaml.safe_load(path.read_text(encoding="utf-8"))
    if obj is None:
        return {}
    if not isinstance(obj, dict):
        raise ValueError(f"config root must be mapping: {path}")
    return dict(obj)


def _merge_config(args: argparse.Namespace) -> dict[str, Any]:
    cfg = dict(DEFAULTS)
    if str(getattr(args, "config", "")).strip():
        cfg.update(_load_yaml(Path(str(args.config))))
    for k, v in vars(args).items():
        if k == "config":
            continue
        if v is not None:
            cfg[k] = v
    return cfg


def _parse_float_list(raw: str) -> list[float]:
    return [float(x.strip()) for x in str(raw).split(",") if x.strip()]


def _safe_numeric(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").astype(float)


def _select_candidate_universe(
    cands: pd.DataFrame,
    *,
    symbol: str,
    min_train_count: int,
    max_candidates: int,
) -> pd.DataFrame:
    if cands.empty:
        return cands
    x = cands.copy()
    x = x[x["symbol"].astype(str).str.upper() == str(symbol).upper()].copy()
    x["train_count"] = _safe_numeric(x["train_count"]).fillna(0.0)
    x["mean_gross_pips_train"] = _safe_numeric(x["mean_gross_pips_train"])
    # Exclude families removed for look-ahead bias (stale CSVs may still contain them)
    if "family" in x.columns:
        x = x[x["family"].astype(str) != "oco_first_touch_clean"].copy()
    # CatBoost can surface profitable months within near-zero gross regimes; the
    # previous > 0.0 gate was calibrated on look-ahead-biased data. Use > -0.2
    # to pass regimes that outperform the broad market (~-0.3 pips) materially.
    x = x[(x["train_count"] >= float(min_train_count)) & (x["mean_gross_pips_train"] > -0.2)].copy()
    x = x.sort_values(
        ["train_count", "mean_gross_pips_train"], ascending=[False, False]
    ).reset_index(drop=True)
    if int(max_candidates) > 0:
        x = x.head(int(max_candidates)).copy()
    return x


def _build_events_for_library(
    *,
    library: str,
    symbol: str,
    dataset_dir: Path,
    candidate_dir: Path,
    train_years_fit: set[int],
    eval_year: int,
    eval_start_ts: pd.Timestamp | None,
    eval_end_ts_excl: pd.Timestamp | None,
    min_candidate_train_count: int,
    max_candidates: int,
    max_events_per_candidate: int,
    oco_include_no_touch: bool,
    oco_hold_mode: str,
) -> pd.DataFrame:
    lib = str(library).strip().lower()
    if lib not in {"directional", "oco"}:
        raise ValueError(f"bad library: {library}")
    c_path = candidate_dir / f"{symbol}_{lib}_candidates.csv"
    if not c_path.exists():
        return pd.DataFrame()
    try:
        c = pd.read_csv(c_path)
    except pd.errors.EmptyDataError:
        # Empty CSV from upstream mining stage (no-trade condition)
        return pd.DataFrame()
    c = _select_candidate_universe(
        c,
        symbol=symbol,
        min_train_count=int(min_candidate_train_count),
        max_candidates=int(max_candidates),
    )
    if c.empty:
        return pd.DataFrame()

    events_parts: list[pd.DataFrame] = []
    for bt in sorted(c["bar_ticks"].astype(int).unique().tolist()):
        sub = c[c["bar_ticks"].astype(int) == int(bt)].copy()
        if sub.empty:
            continue
        path = dataset_dir / f"{symbol}_{int(bt)}tick_velocity.parquet"
        if not path.exists():
            continue
        horizons = sorted(sub["horizon"].astype(int).unique().tolist())
        d = _prepare_frame(path, symbol=symbol, horizons=horizons)
        fit_df = d[d["year"].isin(train_years_fit)].copy().reset_index(drop=True)
        if eval_start_ts is not None and eval_end_ts_excl is not None:
            eval_df = (
                d[(d["close_ts"] >= eval_start_ts) & (d["close_ts"] < eval_end_ts_excl)]
                .copy()
                .reset_index(drop=True)
            )
        else:
            eval_df = d[d["year"] == int(eval_year)].copy().reset_index(drop=True)
        if fit_df.empty or eval_df.empty:
            continue
        q_fit = _quantiles(fit_df)
        if lib == "directional":
            ev = _build_directional_events(
                split_name="eval",
                df=eval_df,
                q_fit=q_fit,
                cands=sub,
                max_events_per_candidate=int(max_events_per_candidate),
            )
        else:
            ev = _build_oco_events(
                split_name="eval",
                df=eval_df,
                q_fit=q_fit,
                cands=sub,
                max_events_per_candidate=int(max_events_per_candidate),
                symbol=symbol,
                hold_mode=str(oco_hold_mode),
                include_no_touch=bool(oco_include_no_touch),
            )
        if not ev.empty:
            events_parts.append(ev)
        print(f"ok {symbol} {lib} {bt}tick")
    return pd.concat(events_parts, ignore_index=True) if events_parts else pd.DataFrame()


def _attach_stable_event_ids(events: pd.DataFrame) -> pd.DataFrame:
    if events.empty:
        return events.copy()
    out = events.copy()
    out["close_ts"] = pd.to_datetime(out["close_ts"], utc=True, errors="coerce")
    out = out[out["close_ts"].notna()].copy()
    if "test_month" not in out.columns:
        out["test_month"] = out["close_ts"].dt.strftime("%Y-%m")
    out = out.sort_values(["test_month", "candidate_uid", "close_ts"], kind="stable").reset_index(
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
    return out


_MICROSTRUCTURE_FEATURES = [
    "tick_burst_score",
    "quote_revision_rate_z",
    "directional_persistence_8",
    "signed_flow_24",
    "vol_cluster_score",
]


def _feature_cols(d: pd.DataFrame) -> list[str]:
    """Dynamically determine the model feature columns present in the frame.

    IMPORTANT: The returned list includes 13 market features AND 3 structural parameters
    (bar_ticks, horizon, barrier_pips). These structural parameters are critical meta-learning
    state constraints that allow the CatBoost model to partition its thresholds contextually.
    Do NOT remove them under the mistaken belief that they are 'leakage'.
    """
    base = [
        "cost_est_pips",
        "range_pips",
        "ret1_pips",
        "ret_z",
        "ret_abs_z",
        "vel_cost_units_h1",
        "vel_abs_cost_units_h1",
        "spread_z",
        "tick_rate_z",
        "hour_utc",
        "hl_first",
        "hl_first_mean_24",
        "hl_pos_frac_mean_24",
        "bar_ticks",
        "horizon",
        "barrier_pips",
    ] + _MICROSTRUCTURE_FEATURES
    return [c for c in base if c in d.columns]


def _month_bounds(year: int) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    starts = pd.date_range(f"{int(year)}-01-01", f"{int(year)}-12-01", freq="MS", tz="UTC")
    out: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    for i, s in enumerate(starts):
        e = (
            starts[i + 1]
            if i + 1 < len(starts)
            else pd.Timestamp(f"{int(year) + 1}-01-01", tz="UTC")
        )
        out.append((s, e))
    return out


def _month_start(month_txt: str) -> pd.Timestamp:
    p = pd.Period(str(month_txt), freq="M")
    return p.to_timestamp(how="start").tz_localize("UTC")


def _month_bounds_range(
    start_month: str, end_month: str
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    p0 = pd.Period(str(start_month), freq="M")
    p1 = pd.Period(str(end_month), freq="M")
    if p1 < p0:
        raise ValueError(f"end_month before start_month: {end_month} < {start_month}")
    periods = pd.period_range(p0, p1, freq="M")
    out: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    for p in periods:
        s = p.to_timestamp(how="start").tz_localize("UTC")
        e = (p + 1).to_timestamp(how="start").tz_localize("UTC")
        out.append((s, e))
    return out


def _rolling_day_threshold_vector(
    *,
    train_ts: pd.Series,
    train_p: np.ndarray,
    test_ts: pd.Series,
    test_p: np.ndarray,
    q: float,
    lookback_days: int,
    min_history: int,
) -> tuple[np.ndarray, np.ndarray]:
    tr_t = pd.to_datetime(train_ts, utc=True, errors="coerce")
    te_t = pd.to_datetime(test_ts, utc=True, errors="coerce")
    tr_v = np.asarray(train_p, dtype=float)
    te_v = np.asarray(test_p, dtype=float)
    tr_ok = np.isfinite(tr_v) & tr_t.notna().to_numpy()
    te_ok = np.isfinite(te_v) & te_t.notna().to_numpy()
    out = np.full(len(te_v), np.nan, dtype=float)
    src = np.full(len(te_v), "no_history", dtype=object)
    if not np.any(te_ok):
        return out, src

    tr_day = tr_t.dt.floor("D")
    te_day = te_t.dt.floor("D")
    tr_df = pd.DataFrame({"day": tr_day[tr_ok].to_numpy(), "p": tr_v[tr_ok]})
    te_df = pd.DataFrame(
        {"day": te_day[te_ok].to_numpy(), "p": te_v[te_ok], "idx": np.flatnonzero(te_ok)}
    )

    train_by_day: dict[pd.Timestamp, np.ndarray] = {}
    for d, g in tr_df.groupby("day", sort=True):
        train_by_day[pd.Timestamp(d)] = g["p"].to_numpy(dtype=float)

    test_by_day_vals: dict[pd.Timestamp, np.ndarray] = {}
    test_by_day_idx: dict[pd.Timestamp, np.ndarray] = {}
    for d, g in te_df.groupby("day", sort=True):
        dd = pd.Timestamp(d)
        test_by_day_vals[dd] = g["p"].to_numpy(dtype=float)
        test_by_day_idx[dd] = g["idx"].to_numpy(dtype=np.int64)

    # Strictly causal fallback: never use unseen same-month test pools.
    train_fallback = tr_v[tr_ok]
    train_fallback_thr = (
        float(np.quantile(train_fallback, float(q))) if len(train_fallback) else float("nan")
    )

    lookback = pd.Timedelta(days=int(max(1, lookback_days)))
    pool: dict[pd.Timestamp, np.ndarray] = dict(train_by_day)
    pool_items = list(pool.items())
    for day in sorted(test_by_day_idx.keys()):
        start = day - lookback
        parts: list[np.ndarray] = []
        for d, arr in pool_items:
            if start <= d < day:
                parts.append(arr)
        hist = np.concatenate(parts) if parts else np.array([], dtype=float)
        src_label = "rolling_history"
        if len(hist) < int(max(1, min_history)):
            if len(train_fallback):
                hist = train_fallback
                src_label = "train_fallback"
            else:
                hist = np.array([], dtype=float)
                src_label = "no_history"
        thr = float(np.quantile(hist, float(q))) if len(hist) else float(train_fallback_thr)
        if (not np.isfinite(thr)) and src_label != "no_history":
            src_label = "no_history"
        out[test_by_day_idx[day]] = thr
        src[test_by_day_idx[day]] = src_label
        # Accumulate test-day predictions into pool for subsequent days (causal)
        if day in test_by_day_vals:
            pool[day] = test_by_day_vals[day]
            pool_items.append((day, test_by_day_vals[day]))
    return out, src


def _export_train_predictions(
    *,
    train_ts: pd.Series,
    train_p: np.ndarray,
    out_path: Path,
) -> None:
    """Export training predictions as a parquet artifact for live seeding."""
    tr_t = pd.to_datetime(train_ts, utc=True, errors="coerce")
    tr_v = np.asarray(train_p, dtype=float)
    ok = np.isfinite(tr_v) & tr_t.notna().to_numpy()
    df = pd.DataFrame(
        {
            "day": tr_t[ok].dt.floor("D").dt.date,
            "pred_prob": tr_v[ok],
        }
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)


def _wfo_monthly(
    d: pd.DataFrame,
    *,
    library: str,
    symbol: str = "",
    months: list[tuple[pd.Timestamp, pd.Timestamp]],
    score_start_ts: pd.Timestamp | None,
    rolling_train_months: int,
    min_month_train_rows: int,
    min_month_test_rows: int,
    min_candidate_rows_in_train_window: int,
    threshold_quantiles: list[float],
    threshold_mode: str,
    rolling_threshold_days: int,
    rolling_threshold_min_history: int,
    execution_quantile: float,
    seed: int,
    model_export_dir: Path | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if d.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    if CatBoostClassifier is None:
        raise RuntimeError("CatBoost is required for monthly WFO runner")

    x = d.copy()
    x["close_ts"] = pd.to_datetime(x["close_ts"], utc=True, errors="coerce")
    x = x[x["close_ts"].notna()].sort_values("close_ts").reset_index(drop=True)
    feats = _feature_cols(x)
    for c in feats + ["target_gross_pos", "target_gross_pips"]:
        x[c] = _safe_numeric(x[c])
    x = x.dropna(subset=feats + ["target_gross_pos", "target_gross_pips", "candidate_uid"]).copy()

    mode = str(threshold_mode).strip().lower()
    if mode not in {"rolling_days", "train_quantile"}:
        raise ValueError("threshold_mode must be rolling_days|train_quantile")
    exec_q = float(execution_quantile)
    metric_rows: list[dict[str, Any]] = []
    thr_rows: list[dict[str, Any]] = []
    pred_rows: list[pd.DataFrame] = []
    importance_rows: list[dict[str, Any]] = []

    for i, (test_start, test_end) in enumerate(months):
        if i < int(rolling_train_months):
            continue
        if score_start_ts is not None and test_start < score_start_ts:
            continue
        train_start = months[i - int(rolling_train_months)][0]
        train_end = test_start
        tr = x[(x["close_ts"] >= train_start) & (x["close_ts"] < train_end)].copy()
        te = x[(x["close_ts"] >= test_start) & (x["close_ts"] < test_end)].copy()
        if tr.empty or te.empty:
            continue

        by_cand = tr.groupby("candidate_uid", as_index=False).agg(
            train_rows=("target_gross_pips", "size"), train_mean_gross=("target_gross_pips", "mean")
        )
        keep = by_cand[
            (by_cand["train_rows"] >= int(min_candidate_rows_in_train_window))
            & (by_cand["train_mean_gross"] > 0.0)
        ]["candidate_uid"]
        keep_ids = set(keep.astype(str).tolist())
        if not keep_ids:
            continue
        tr = tr[tr["candidate_uid"].astype(str).isin(keep_ids)].copy()
        te = te[te["candidate_uid"].astype(str).isin(keep_ids)].copy()
        if len(tr) < int(min_month_train_rows) or len(te) < int(min_month_test_rows):
            continue
        if tr["target_gross_pos"].nunique() < 2 or te["target_gross_pos"].nunique() < 2:
            continue

        model = CatBoostClassifier(
            loss_function="Logloss",
            eval_metric="AUC",
            iterations=350,
            learning_rate=0.05,
            depth=6,
            l2_leaf_reg=5.0,
            random_seed=int(seed) + i,
            verbose=False,
        )
        model.fit(tr[feats], tr["target_gross_pos"].astype(int))
        p_tr = model.predict_proba(tr[feats])[:, 1]
        p = model.predict_proba(te[feats])[:, 1]
        y = te["target_gross_pos"].astype(int).to_numpy()

        # --- Feature Importance ---
        fi = model.get_feature_importance()
        imp_dict = {"test_month": test_start.strftime("%Y-%m")}
        for f_name, f_val in zip(feats, fi, strict=False):
            imp_dict[f_name] = float(f_val)
        importance_rows.append(imp_dict)

        # ── Export model binary + threshold config for production API ──
        if model_export_dir is not None and symbol:
            model_export_dir.mkdir(parents=True, exist_ok=True)
            month_tag = test_start.strftime("%Y-%m")
            cbm_path = model_export_dir / f"{symbol}_model_{month_tag}.cbm"
            model.save_model(str(cbm_path))

            # Export Importances CSV
            imp_df = pd.DataFrame({"feature": feats, "importance": fi}).sort_values(
                "importance", ascending=False
            )
            imp_path = model_export_dir / f"{symbol}_feature_importance_{month_tag}.csv"
            imp_df.to_csv(imp_path, index=False)

            # Compute execution threshold for live API.
            # In rolling_days mode, compute the rolling threshold vector at
            # exec_q and export the median as a representative static scalar.
            # This closely tracks what WFO scoring actually applied, reducing
            # backtest/live parity drift.
            if mode == "rolling_days":
                exec_thr_vec, _ = _rolling_day_threshold_vector(
                    train_ts=tr["close_ts"],
                    train_p=p_tr,
                    test_ts=te["close_ts"],
                    test_p=p,
                    q=exec_q,
                    lookback_days=int(rolling_threshold_days),
                    min_history=int(rolling_threshold_min_history),
                )
                # Create a schedule of daily thresholds for the test month
                schedule: dict[str, float] = {}
                # exec_thr_vec and te["close_ts"] correspond 1:1
                te_t = pd.to_datetime(te["close_ts"], utc=True, errors="coerce")
                te_day = te_t.dt.strftime("%Y-%m-%d").to_numpy()
                for d_str, t_val in zip(te_day, exec_thr_vec, strict=False):
                    if d_str not in schedule and np.isfinite(t_val):
                        schedule[d_str] = float(t_val)

                finite_thr = exec_thr_vec[np.isfinite(exec_thr_vec)]
                exec_thr = (
                    float(np.median(finite_thr))
                    if len(finite_thr) > 0
                    else float(np.quantile(p_tr, exec_q))
                )
            else:
                exec_thr = float(np.quantile(p_tr, float(exec_q)))
                schedule = {}

            thr_meta = {
                "symbol": symbol,
                "model_month": month_tag,
                "threshold_exec": exec_thr,  # Median/Baseline
                "threshold_schedule": schedule,  # Daily precision
                "execution_quantile": float(exec_q),
                "threshold_source": mode,
                "rolling_threshold_days": int(rolling_threshold_days)
                if mode == "rolling_days"
                else 0,
                "rolling_threshold_min_history": int(rolling_threshold_min_history)
                if mode == "rolling_days"
                else 0,
                "train_rows": int(len(tr)),
                "features": feats,
            }
            thr_path = cbm_path.with_suffix(".json")
            thr_path.write_text(json.dumps(thr_meta, indent=2))
            print(f"exported: {cbm_path} + {thr_path} + {imp_path}")

            # Export training predictions for live seeding
            train_pred_path = model_export_dir / f"{symbol}_train_predictions_{month_tag}.parquet"
            _export_train_predictions(
                train_ts=tr["close_ts"],
                train_p=p_tr,
                out_path=train_pred_path,
            )
            print(f"exported: {train_pred_path}")

        from sklearn.metrics import brier_score_loss, roc_auc_score  # local import

        auc = float(roc_auc_score(y, p))
        brier = float(brier_score_loss(y, p))
        metric_rows.append(
            {
                "library": library,
                "test_month": test_start.strftime("%Y-%m"),
                "train_start": train_start.strftime("%Y-%m-%d"),
                "train_end": train_end.strftime("%Y-%m-%d"),
                "test_start": test_start.strftime("%Y-%m-%d"),
                "test_end": test_end.strftime("%Y-%m-%d"),
                "train_rows": int(len(tr)),
                "test_rows": int(len(te)),
                "train_candidates": int(tr["candidate_uid"].nunique()),
                "test_candidates": int(te["candidate_uid"].nunique()),
                "base_pos_rate": float(np.mean(y)),
                "auc": auc,
                "brier": brier,
            }
        )
        pred_chunk = pd.DataFrame(
            {
                "library": str(library),
                "test_month": test_start.strftime("%Y-%m"),
                "close_ts": pd.to_datetime(te["close_ts"], utc=True, errors="coerce").to_numpy(),
                "candidate_uid": te["candidate_uid"].astype(str).to_numpy(),
                "pred_prob": p.astype(float),
                "target_gross_pips": te["target_gross_pips"].to_numpy(dtype=float),
                "target_gross_pos": te["target_gross_pos"].to_numpy(dtype=int),
                "threshold_mode": mode,
                "threshold_days": int(rolling_threshold_days) if mode == "rolling_days" else 0,
                "threshold_exec": np.full(len(te), np.nan, dtype=float),
                "selected_exec": np.zeros(len(te), dtype=int),
                "threshold_source": np.full(len(te), "unset", dtype=object),
            }
        )
        for extra_col in ["event_ordinal", "scored_row_id"]:
            if extra_col in te.columns:
                pred_chunk[extra_col] = te[extra_col].to_numpy()
        g = te["target_gross_pips"].to_numpy(dtype=float)
        for q in threshold_quantiles:
            if mode == "rolling_days":
                thr_vec, src_vec = _rolling_day_threshold_vector(
                    train_ts=tr["close_ts"],
                    train_p=p_tr,
                    test_ts=te["close_ts"],
                    test_p=p,
                    q=float(q),
                    lookback_days=int(rolling_threshold_days),
                    min_history=int(rolling_threshold_min_history),
                )
            else:
                thr = float(np.quantile(p_tr, float(q)))
                thr_vec = np.full(len(p), float(thr), dtype=float)
                src_vec = np.full(len(p), "train_quantile", dtype=object)
            m = np.isfinite(thr_vec) & (p >= thr_vec)
            if int(m.sum()) <= 0:
                continue
            gg = g[m]
            thr_rows.append(
                {
                    "library": library,
                    "test_month": test_start.strftime("%Y-%m"),
                    "quantile": float(q),
                    "threshold_mode": mode,
                    "threshold_median": float(np.nanmedian(thr_vec)),
                    "threshold_min": float(np.nanmin(thr_vec)),
                    "threshold_max": float(np.nanmax(thr_vec)),
                    "coverage": float(np.mean(m)),
                    "mean_gross_pips": float(np.mean(gg)),
                    "median_gross_pips": float(np.median(gg)),
                    "pos_rate": float(np.mean(gg > 0.0)),
                    "selected_rows": int(m.sum()),
                }
            )
            if abs(float(q) - exec_q) <= 1e-12:
                pred_chunk["threshold_exec"] = thr_vec.astype(float)
                pred_chunk["selected_exec"] = m.astype(int)
                pred_chunk["threshold_source"] = np.asarray(src_vec, dtype=object)
        pred_rows.append(pred_chunk)
    preds = pd.concat(pred_rows, ignore_index=True) if pred_rows else pd.DataFrame()
    importance = pd.DataFrame(importance_rows) if importance_rows else pd.DataFrame()
    return pd.DataFrame(metric_rows), pd.DataFrame(thr_rows), preds, importance


def _write_report(
    report_out: Path,
    metrics: pd.DataFrame,
    thresholds: pd.DataFrame,
    importance: pd.DataFrame,
    cfg: dict[str, Any],
) -> None:
    symbol = str(cfg.get("symbol", "UNKNOWN")).upper().strip() or "UNKNOWN"
    lines: list[str] = []
    lines.append(f"# {symbol} Tick Opportunity Monthly WFO (3M->1M)")
    lines.append("")
    lines.append("## Setup")
    lines.append(f"- library: `{cfg['library']}`")
    lines.append(f"- train_years_for_state_fit: `{cfg['train_years_for_state_fit']}`")
    eval_start_month = str(cfg.get("eval_start_month", "")).strip()
    eval_end_month = str(cfg.get("eval_end_month", "")).strip()
    if eval_start_month and eval_end_month:
        lines.append(f"- eval_window: `{eval_start_month}` .. `{eval_end_month}`")
    else:
        lines.append(f"- eval_year: `{cfg['eval_year']}`")
    lines.append(f"- min_candidate_train_count: `{cfg['min_candidate_train_count']}`")
    lines.append(f"- max_candidates_per_library: `{cfg['max_candidates_per_library']}`")
    lines.append(f"- rolling_train_months: `{cfg['rolling_train_months']}`")
    lines.append(
        f"- oco_include_no_touch: `{cfg.get('oco_include_no_touch', DEFAULTS['oco_include_no_touch'])}`"
    )
    lines.append(f"- threshold_mode: `{cfg.get('threshold_mode', DEFAULTS['threshold_mode'])}`")
    lines.append(
        f"- rolling_threshold_days: `{cfg.get('rolling_threshold_days', DEFAULTS['rolling_threshold_days'])}`"
    )
    lines.append(
        f"- rolling_threshold_min_history: `{cfg.get('rolling_threshold_min_history', DEFAULTS['rolling_threshold_min_history'])}`"
    )
    lines.append(
        f"- execution_quantile: `{cfg.get('execution_quantile', DEFAULTS['execution_quantile'])}`"
    )
    lines.append(f"- oco_hold_mode: `{cfg.get('oco_hold_mode', DEFAULTS['oco_hold_mode'])}`")
    lines.append("")
    lines.append("## Feature Importance")
    if not importance.empty:
        # Calculate mean importance across all months (ignoring 'test_month' col)
        numeric_cols = [c for c in importance.columns if c != "test_month"]
        mean_imp = (
            importance[numeric_cols].mean().sort_values(ascending=False).to_frame("mean_importance")
        )
        mean_imp.index.name = "feature"
        lines.append(mean_imp.reset_index().to_markdown(index=False))
    else:
        lines.append("_empty_")
    lines.append("")
    lines.append("## Monthly Metrics")
    lines.append(metrics.to_markdown(index=False) if not metrics.empty else "_empty_")
    lines.append("")
    lines.append("## Threshold Outcomes")
    lines.append(thresholds.to_markdown(index=False) if not thresholds.empty else "_empty_")
    lines.append("")
    report_out.parent.mkdir(parents=True, exist_ok=True)
    report_out.write_text("\n".join(lines), encoding="utf-8")


def _write_library_outputs(
    *,
    out_dir: Path,
    symbol: str,
    lib: str,
    m: pd.DataFrame,
    t: pd.DataFrame,
    p: pd.DataFrame,
    imp: pd.DataFrame,
) -> list[Path]:
    """Write the four per-library monthly artifacts, always.

    Empty frames are written too: a missing artifact must mean the stage did
    not run, never that it ran and found nothing. Writing an empty file also
    overwrites any stale artifact from a prior run.
    """
    m_out = out_dir / f"{symbol}_{lib}_monthly_metrics.csv"
    t_out = out_dir / f"{symbol}_{lib}_monthly_thresholds.csv"
    p_out = out_dir / f"{symbol}_{lib}_monthly_predictions.parquet"
    imp_out = out_dir / f"{symbol}_{lib}_monthly_importance.csv"
    m.to_csv(m_out, index=False)
    t.to_csv(t_out, index=False)
    p.to_parquet(p_out, index=False)
    imp.to_csv(imp_out, index=False)
    for path in (m_out, t_out, p_out, imp_out):
        print(f"wrote: {path}")
    return [m_out, t_out, p_out, imp_out]


def main() -> None:
    p = argparse.ArgumentParser(
        description="Run strict monthly WFO (3M->1M) on tick opportunity events"
    )
    p.add_argument("--config", default=None)
    p.add_argument("--symbol", default=None)
    p.add_argument("--dataset-dir", default=None)
    p.add_argument("--candidate-dir", default=None)
    p.add_argument("--library", default=None)
    p.add_argument("--train-years-for-state-fit", default=None)
    p.add_argument("--eval-year", type=int, default=None)
    p.add_argument("--eval-start-month", default=None)
    p.add_argument("--eval-end-month", default=None)
    p.add_argument("--min-candidate-train-count", type=int, default=None)
    p.add_argument("--max-candidates-per-library", type=int, default=None)
    p.add_argument("--max-events-per-candidate", type=int, default=None)
    p.add_argument("--rolling-train-months", type=int, default=None)
    p.add_argument("--min-month-train-rows", type=int, default=None)
    p.add_argument("--min-month-test-rows", type=int, default=None)
    p.add_argument("--min-candidate-rows-in-train-window", type=int, default=None)
    p.add_argument("--threshold-quantiles", default=None)
    p.add_argument("--oco-include-no-touch", default=None)
    p.add_argument("--threshold-mode", default=None)
    p.add_argument("--rolling-threshold-days", type=int, default=None)
    p.add_argument("--rolling-threshold-min-history", type=int, default=None)
    p.add_argument("--execution-quantile", type=float, default=None)
    p.add_argument("--oco-hold-mode", default=None)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--out-dir", default=None)
    p.add_argument("--report-out", default=None)
    p.add_argument(
        "--model-export-dir",
        default=None,
        help="Directory to export .cbm models + .json thresholds",
    )
    args = p.parse_args()

    cfg = _merge_config(args)
    if isinstance(cfg.get("oco_include_no_touch"), str):
        cfg["oco_include_no_touch"] = str(cfg["oco_include_no_touch"]).strip().lower() in {
            "1",
            "true",
            "yes",
            "y",
        }
    symbol = str(cfg["symbol"]).upper().strip()
    dataset_dir = Path(str(cfg["dataset_dir"]))
    candidate_dir = Path(str(cfg["candidate_dir"]))
    train_years_fit = set(_parse_ints(str(cfg["train_years_for_state_fit"])))
    eval_year = int(cfg["eval_year"])
    eval_start_month = str(cfg.get("eval_start_month", "")).strip()
    eval_end_month = str(cfg.get("eval_end_month", "")).strip()
    if not eval_end_month:
        today = date.today()
        last_complete = date(today.year, today.month, 1) - timedelta(days=1)
        eval_end_month = f"{last_complete.year}-{last_complete.month:02d}"
    libs_raw = str(cfg["library"]).strip().lower()
    oco_include_no_touch = bool(cfg.get("oco_include_no_touch", DEFAULTS["oco_include_no_touch"]))
    threshold_mode = str(cfg.get("threshold_mode", DEFAULTS["threshold_mode"])).strip().lower()
    if threshold_mode not in {"rolling_days", "train_quantile"}:
        raise ValueError("threshold_mode must be rolling_days|train_quantile")
    oco_hold_mode = str(cfg.get("oco_hold_mode", DEFAULTS["oco_hold_mode"])).strip().lower()
    if oco_hold_mode not in {"from_touch", "from_start"}:
        raise ValueError("oco_hold_mode must be from_touch|from_start")
    libs = ["directional", "oco"] if libs_raw == "both" else [libs_raw]
    for lib in libs:
        if lib not in {"directional", "oco"}:
            raise ValueError("library must be directional|oco|both")

    rolling_train_months = int(cfg["rolling_train_months"])
    if bool(eval_start_month) ^ bool(eval_end_month):
        raise ValueError("eval_start_month and eval_end_month must be set together")
    if eval_start_month and eval_end_month:
        score_start_ts = _month_start(eval_start_month)
        hist_start_period = pd.Period(eval_start_month, freq="M") - rolling_train_months
        hist_start_ts = hist_start_period.to_timestamp(how="start").tz_localize("UTC")
        end_period = pd.Period(eval_end_month, freq="M")
        months = _month_bounds_range(
            hist_start_period.strftime("%Y-%m"), end_period.strftime("%Y-%m")
        )
        eval_filter_start_ts = hist_start_ts
        eval_filter_end_ts_excl = (end_period + 1).to_timestamp(how="start").tz_localize("UTC")
    else:
        score_start_ts = None
        months = _month_bounds(int(eval_year))
        eval_filter_start_ts = None
        eval_filter_end_ts_excl = None

    all_metrics: list[pd.DataFrame] = []
    all_thresholds: list[pd.DataFrame] = []
    all_preds: list[pd.DataFrame] = []
    all_importance: list[pd.DataFrame] = []
    out_dir = Path(str(cfg["out_dir"]))
    out_dir.mkdir(parents=True, exist_ok=True)

    for lib in libs:
        ev = _build_events_for_library(
            library=lib,
            symbol=symbol,
            dataset_dir=dataset_dir,
            candidate_dir=candidate_dir,
            train_years_fit=train_years_fit,
            eval_year=eval_year,
            eval_start_ts=eval_filter_start_ts,
            eval_end_ts_excl=eval_filter_end_ts_excl,
            min_candidate_train_count=int(cfg["min_candidate_train_count"]),
            max_candidates=int(cfg["max_candidates_per_library"]),
            max_events_per_candidate=int(cfg["max_events_per_candidate"]),
            oco_include_no_touch=oco_include_no_touch,
            oco_hold_mode=oco_hold_mode,
        )
        ev = _attach_stable_event_ids(ev)
        ev_path = out_dir / f"{symbol}_{lib}_events_eval{eval_year}.parquet"
        ev.to_parquet(ev_path, index=False)
        print(f"wrote: {ev_path}")
        m, t, p, imp = _wfo_monthly(
            ev,
            library=lib,
            symbol=symbol,
            months=months,
            score_start_ts=score_start_ts,
            rolling_train_months=rolling_train_months,
            min_month_train_rows=int(cfg["min_month_train_rows"]),
            min_month_test_rows=int(cfg["min_month_test_rows"]),
            min_candidate_rows_in_train_window=int(cfg["min_candidate_rows_in_train_window"]),
            threshold_quantiles=_parse_float_list(str(cfg["threshold_quantiles"])),
            threshold_mode=threshold_mode,
            rolling_threshold_days=int(
                cfg.get("rolling_threshold_days", DEFAULTS["rolling_threshold_days"])
            ),
            rolling_threshold_min_history=int(
                cfg.get("rolling_threshold_min_history", DEFAULTS["rolling_threshold_min_history"])
            ),
            execution_quantile=float(cfg.get("execution_quantile", DEFAULTS["execution_quantile"])),
            seed=int(cfg["seed"]),
            model_export_dir=Path(str(cfg.get("model_export_dir", "")))
            if cfg.get("model_export_dir")
            else None,
        )
        _write_library_outputs(
            out_dir=out_dir, symbol=symbol, lib=lib, m=m, t=t, p=p, imp=imp
        )
        if not m.empty:
            all_metrics.append(m)
        if not t.empty:
            all_thresholds.append(t)
        if not p.empty:
            all_preds.append(p)
        if not imp.empty:
            all_importance.append(imp)

    metrics = pd.concat(all_metrics, ignore_index=True) if all_metrics else pd.DataFrame()
    thresholds = pd.concat(all_thresholds, ignore_index=True) if all_thresholds else pd.DataFrame()
    preds = pd.concat(all_preds, ignore_index=True) if all_preds else pd.DataFrame()
    importance = pd.concat(all_importance, ignore_index=True) if all_importance else pd.DataFrame()
    met_all = out_dir / f"{symbol}_monthly_metrics_all.csv"
    thr_all = out_dir / f"{symbol}_monthly_thresholds_all.csv"
    imp_all = out_dir / f"{symbol}_monthly_importance_all.csv"
    metrics.to_csv(met_all, index=False)
    thresholds.to_csv(thr_all, index=False)
    importance.to_csv(imp_all, index=False)
    preds_all = out_dir / f"{symbol}_monthly_predictions_all.parquet"
    preds.to_parquet(preds_all, index=False)
    print(f"wrote: {met_all}")
    print(f"wrote: {thr_all}")
    print(f"wrote: {imp_all}")
    print(f"wrote: {preds_all}")

    report_out = Path(str(cfg["report_out"]))
    _write_report(report_out, metrics, thresholds, importance, cfg)
    print(f"wrote: {report_out}")


if __name__ == "__main__":
    main()
