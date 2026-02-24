#!/usr/bin/env python3
"""Strict monthly WFO on tick opportunity events (3M train -> next month test).

Leakage controls:
- Candidate universe is filtered using train-only candidate metrics
  (`mean_gross_pips_train`, `train_count`) from mining outputs.
- Inside 2025, each test month is predicted using only prior 3 months.
"""

from __future__ import annotations

import argparse
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
    "min_candidate_train_count": 15000,
    "max_candidates_per_library": 300,
    "max_events_per_candidate": 8000,
    "rolling_train_months": 3,
    "min_month_train_rows": 5000,
    "min_month_test_rows": 1500,
    "min_candidate_rows_in_train_window": 300,
    "threshold_quantiles": "0.5,0.6,0.7,0.8,0.9,0.95",
    "seed": 42,
    "out_dir": "data/analysis/tick_opportunity_mining/wfo_2025_m3to1",
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
    x = x[(x["train_count"] >= float(min_train_count)) & (x["mean_gross_pips_train"] > 0.0)].copy()
    x = x.sort_values(["train_count", "mean_gross_pips_train"], ascending=[False, False]).reset_index(drop=True)
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
    min_candidate_train_count: int,
    max_candidates: int,
    max_events_per_candidate: int,
) -> pd.DataFrame:
    lib = str(library).strip().lower()
    if lib not in {"directional", "oco"}:
        raise ValueError(f"bad library: {library}")
    c_path = candidate_dir / f"{symbol}_{lib}_candidates.csv"
    if not c_path.exists():
        return pd.DataFrame()
    c = pd.read_csv(c_path)
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
            )
        if not ev.empty:
            events_parts.append(ev)
        print(f"ok {symbol} {lib} {bt}tick")
    return pd.concat(events_parts, ignore_index=True) if events_parts else pd.DataFrame()


def _feature_cols(d: pd.DataFrame) -> list[str]:
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
    ]
    return [c for c in base if c in d.columns]


def _month_bounds(year: int) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    starts = pd.date_range(f"{int(year)}-01-01", f"{int(year)}-12-01", freq="MS", tz="UTC")
    out: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    for i, s in enumerate(starts):
        e = starts[i + 1] if i + 1 < len(starts) else pd.Timestamp(f"{int(year)+1}-01-01", tz="UTC")
        out.append((s, e))
    return out


def _wfo_monthly(
    d: pd.DataFrame,
    *,
    library: str,
    year: int,
    rolling_train_months: int,
    min_month_train_rows: int,
    min_month_test_rows: int,
    min_candidate_rows_in_train_window: int,
    threshold_quantiles: list[float],
    seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if d.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    if CatBoostClassifier is None:
        raise RuntimeError("CatBoost is required for monthly WFO runner")

    x = d.copy()
    x["close_ts"] = pd.to_datetime(x["close_ts"], utc=True, errors="coerce")
    x = x[x["close_ts"].notna()].sort_values("close_ts").reset_index(drop=True)
    feats = _feature_cols(x)
    for c in feats + ["target_gross_pos", "target_gross_pips"]:
        x[c] = _safe_numeric(x[c])
    x = x.dropna(subset=feats + ["target_gross_pos", "target_gross_pips", "candidate_uid"]).copy()

    months = _month_bounds(int(year))
    metric_rows: list[dict[str, Any]] = []
    thr_rows: list[dict[str, Any]] = []
    pred_rows: list[pd.DataFrame] = []
    for i, (test_start, test_end) in enumerate(months):
        if i < int(rolling_train_months):
            continue
        train_start = months[i - int(rolling_train_months)][0]
        train_end = test_start
        tr = x[(x["close_ts"] >= train_start) & (x["close_ts"] < train_end)].copy()
        te = x[(x["close_ts"] >= test_start) & (x["close_ts"] < test_end)].copy()
        if tr.empty or te.empty:
            continue

        by_cand = tr.groupby("candidate_uid", as_index=False).agg(train_rows=("target_gross_pips", "size"), train_mean_gross=("target_gross_pips", "mean"))
        keep = by_cand[(by_cand["train_rows"] >= int(min_candidate_rows_in_train_window)) & (by_cand["train_mean_gross"] > 0.0)]["candidate_uid"]
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
        p = model.predict_proba(te[feats])[:, 1]
        y = te["target_gross_pos"].astype(int).to_numpy()
        from sklearn.metrics import roc_auc_score, brier_score_loss  # local import

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
            }
        )
        pred_rows.append(pred_chunk)
        g = te["target_gross_pips"].to_numpy(dtype=float)
        for q in threshold_quantiles:
            thr = float(np.quantile(p, float(q)))
            m = p >= thr
            if int(m.sum()) <= 0:
                continue
            gg = g[m]
            thr_rows.append(
                {
                    "library": library,
                    "test_month": test_start.strftime("%Y-%m"),
                    "quantile": float(q),
                    "coverage": float(np.mean(m)),
                    "mean_gross_pips": float(np.mean(gg)),
                    "median_gross_pips": float(np.median(gg)),
                    "pos_rate": float(np.mean(gg > 0.0)),
                    "selected_rows": int(m.sum()),
                }
            )
    preds = pd.concat(pred_rows, ignore_index=True) if pred_rows else pd.DataFrame()
    return pd.DataFrame(metric_rows), pd.DataFrame(thr_rows), preds


def _write_report(report_out: Path, metrics: pd.DataFrame, thresholds: pd.DataFrame, cfg: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append("# EURUSD Tick Opportunity Monthly WFO (3M->1M)")
    lines.append("")
    lines.append("## Setup")
    lines.append(f"- library: `{cfg['library']}`")
    lines.append(f"- train_years_for_state_fit: `{cfg['train_years_for_state_fit']}`")
    lines.append(f"- eval_year: `{cfg['eval_year']}`")
    lines.append(f"- min_candidate_train_count: `{cfg['min_candidate_train_count']}`")
    lines.append(f"- max_candidates_per_library: `{cfg['max_candidates_per_library']}`")
    lines.append(f"- rolling_train_months: `{cfg['rolling_train_months']}`")
    lines.append("")
    lines.append("## Monthly Metrics")
    lines.append(metrics.to_markdown(index=False) if not metrics.empty else "_empty_")
    lines.append("")
    lines.append("## Threshold Outcomes")
    lines.append(thresholds.to_markdown(index=False) if not thresholds.empty else "_empty_")
    lines.append("")
    report_out.parent.mkdir(parents=True, exist_ok=True)
    report_out.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser(description="Run strict monthly WFO (3M->1M) on tick opportunity events")
    p.add_argument("--config", default=None)
    p.add_argument("--symbol", default=None)
    p.add_argument("--dataset-dir", default=None)
    p.add_argument("--candidate-dir", default=None)
    p.add_argument("--library", default=None)
    p.add_argument("--train-years-for-state-fit", default=None)
    p.add_argument("--eval-year", type=int, default=None)
    p.add_argument("--min-candidate-train-count", type=int, default=None)
    p.add_argument("--max-candidates-per-library", type=int, default=None)
    p.add_argument("--max-events-per-candidate", type=int, default=None)
    p.add_argument("--rolling-train-months", type=int, default=None)
    p.add_argument("--min-month-train-rows", type=int, default=None)
    p.add_argument("--min-month-test-rows", type=int, default=None)
    p.add_argument("--min-candidate-rows-in-train-window", type=int, default=None)
    p.add_argument("--threshold-quantiles", default=None)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--out-dir", default=None)
    p.add_argument("--report-out", default=None)
    args = p.parse_args()

    cfg = _merge_config(args)
    symbol = str(cfg["symbol"]).upper().strip()
    dataset_dir = Path(str(cfg["dataset_dir"]))
    candidate_dir = Path(str(cfg["candidate_dir"]))
    train_years_fit = set(_parse_ints(str(cfg["train_years_for_state_fit"])))
    eval_year = int(cfg["eval_year"])
    libs_raw = str(cfg["library"]).strip().lower()
    libs = ["directional", "oco"] if libs_raw == "both" else [libs_raw]
    for lib in libs:
        if lib not in {"directional", "oco"}:
            raise ValueError("library must be directional|oco|both")

    all_metrics: list[pd.DataFrame] = []
    all_thresholds: list[pd.DataFrame] = []
    all_preds: list[pd.DataFrame] = []
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
            min_candidate_train_count=int(cfg["min_candidate_train_count"]),
            max_candidates=int(cfg["max_candidates_per_library"]),
            max_events_per_candidate=int(cfg["max_events_per_candidate"]),
        )
        ev_path = out_dir / f"{symbol}_{lib}_events_eval{eval_year}.parquet"
        ev.to_parquet(ev_path, index=False)
        print(f"wrote: {ev_path}")
        m, t, p = _wfo_monthly(
            ev,
            library=lib,
            year=eval_year,
            rolling_train_months=int(cfg["rolling_train_months"]),
            min_month_train_rows=int(cfg["min_month_train_rows"]),
            min_month_test_rows=int(cfg["min_month_test_rows"]),
            min_candidate_rows_in_train_window=int(cfg["min_candidate_rows_in_train_window"]),
            threshold_quantiles=_parse_float_list(str(cfg["threshold_quantiles"])),
            seed=int(cfg["seed"]),
        )
        if not m.empty:
            m_out = out_dir / f"{symbol}_{lib}_monthly_metrics.csv"
            m.to_csv(m_out, index=False)
            print(f"wrote: {m_out}")
            all_metrics.append(m)
        if not t.empty:
            t_out = out_dir / f"{symbol}_{lib}_monthly_thresholds.csv"
            t.to_csv(t_out, index=False)
            print(f"wrote: {t_out}")
            all_thresholds.append(t)
        if not p.empty:
            p_out = out_dir / f"{symbol}_{lib}_monthly_predictions.parquet"
            p.to_parquet(p_out, index=False)
            print(f"wrote: {p_out}")
            all_preds.append(p)

    metrics = pd.concat(all_metrics, ignore_index=True) if all_metrics else pd.DataFrame()
    thresholds = pd.concat(all_thresholds, ignore_index=True) if all_thresholds else pd.DataFrame()
    preds = pd.concat(all_preds, ignore_index=True) if all_preds else pd.DataFrame()
    met_all = out_dir / f"{symbol}_monthly_metrics_all.csv"
    thr_all = out_dir / f"{symbol}_monthly_thresholds_all.csv"
    metrics.to_csv(met_all, index=False)
    thresholds.to_csv(thr_all, index=False)
    preds_all = out_dir / f"{symbol}_monthly_predictions_all.parquet"
    preds.to_parquet(preds_all, index=False)
    print(f"wrote: {met_all}")
    print(f"wrote: {thr_all}")
    print(f"wrote: {preds_all}")

    report_out = Path(str(cfg["report_out"]))
    _write_report(report_out, metrics, thresholds, cfg)
    print(f"wrote: {report_out}")


if __name__ == "__main__":
    main()
