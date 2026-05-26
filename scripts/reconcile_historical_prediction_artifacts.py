#!/usr/bin/env python3
"""Reconcile mutable historical prediction artifacts into frozen month-local files."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

from src.behemoth.core.bundle_paths import iter_locks

try:
    from catboost import CatBoostClassifier
except Exception:  # pragma: no cover
    CatBoostClassifier = None  # type: ignore[assignment]


_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _normalize_month(raw: Any) -> str:
    txt = str(raw or "").strip()
    if len(txt) == 6 and txt.isdigit():
        return f"{txt[:4]}-{txt[4:]}"
    if _MONTH_RE.match(txt):
        return txt
    return ""


def _candidate_uid(*, symbol: str, bar_ticks: int, horizon: int, state_id: str) -> str:
    return f"oco|{symbol.upper()}|{int(bar_ticks)}|h{int(horizon)}|{str(state_id).strip()}"


def _feature_frame_from_bars(
    *,
    rows: pd.DataFrame,
    bars: pd.DataFrame,
    state_meta: pd.DataFrame,
) -> pd.DataFrame:
    if rows.empty:
        return rows.copy()
    merged = rows.merge(
        state_meta[["candidate_uid", "bar_ticks", "horizon", "barrier_pips"]],
        on="candidate_uid",
        how="inner",
        validate="many_to_one",
    )
    if merged.empty:
        return merged
    out = merged.merge(bars, on=["bar_ticks", "close_ts"], how="left", validate="many_to_one")
    out["ret1_pips"] = pd.to_numeric(out.get("vel_pips_h1"), errors="coerce")
    out["ret_z"] = pd.to_numeric(out.get("vel_z_h1"), errors="coerce")
    out["ret_abs_z"] = pd.to_numeric(out.get("vel_z_h1"), errors="coerce").abs()
    out["vel_abs_cost_units_h1"] = pd.to_numeric(
        out.get("vel_cost_units_h1"), errors="coerce"
    ).abs()
    return out


def _thresholds_for_close_ts(
    close_ts: pd.Series, thr_cfg: dict[str, Any]
) -> tuple[pd.Series, pd.Series]:
    schedule = thr_cfg.get("threshold_schedule", {}) or {}
    static_thr = float(thr_cfg.get("threshold_exec", 0.5))
    mode = str(thr_cfg.get("threshold_source", "default"))
    day_str = pd.to_datetime(close_ts, utc=True, errors="coerce").dt.strftime("%Y-%m-%d")
    thr_vals: list[float] = []
    src_vals: list[str] = []
    for d in day_str:
        if d in schedule:
            thr_vals.append(float(schedule[d]))
            src_vals.append(f"{mode}:schedule")
        else:
            thr_vals.append(static_thr)
            src_vals.append(f"{mode}:static_fallback")
    return pd.Series(thr_vals, index=close_ts.index, dtype=float), pd.Series(
        src_vals, index=close_ts.index, dtype=object
    )


def _load_lock(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _find_repo_root(start: Path) -> Path:
    current = start.resolve()
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    return start.resolve()


def _iter_lock_paths(history_dir: Path, symbols: list[str], months: list[str]) -> list[Path]:
    lock_paths = [
        lock_path
        for month_dir in sorted(path for path in history_dir.iterdir() if path.is_dir())
        for lock_path in iter_locks(month_dir)
    ]
    out: list[Path] = []
    symbol_set = {s.upper() for s in symbols if s}
    month_set = {m for m in months if m}
    for p in lock_paths:
        month = p.parent.name.strip()
        if month_set and month not in month_set:
            continue
        try:
            data = _load_lock(p)
        except Exception:
            continue
        symbol = str(data.get("symbol", "")).upper().strip()
        if symbol_set and symbol not in symbol_set:
            continue
        out.append(p)
    return out


def reconcile_lock(
    *,
    lock_path: Path,
    tick_velocity_dir: Path,
    write_lock: bool,
) -> dict[str, Any]:
    if CatBoostClassifier is None:
        raise RuntimeError("CatBoost is required for historical prediction reconciliation")

    lock = _load_lock(lock_path)
    symbol = str(lock.get("symbol", "")).upper().strip()
    month = str(lock_path.parent.name).strip()
    artifacts = dict(lock.get("artifacts", {}) or {})
    if not symbol or not _MONTH_RE.match(month):
        raise ValueError(f"invalid lock metadata: {lock_path}")

    bundle_dir = lock_path.parent

    prov = lock.get("provenance", {})
    pred_prov = prov.get("predictions", {})
    source_predictions_path = str(pred_prov.get("origin", "")).strip()
    if not source_predictions_path:
        # fallback to current predictions path
        source_predictions_path = str(artifacts.get("predictions", {}).get("path", "")).strip()
    model_entry = artifacts.get("model_cbm", {})
    thr_entry = artifacts.get("model_threshold_json", {})
    model_path = bundle_dir / Path(str(model_entry.get("path", "")).strip())
    threshold_path = bundle_dir / Path(str(thr_entry.get("path", "")).strip())

    if not source_predictions_path:
        raise ValueError(f"missing predictions_path in {lock_path}")
    source_pred = Path(source_predictions_path)
    if not source_pred.is_absolute():
        repo_root = _find_repo_root(bundle_dir)
        source_pred = repo_root / source_pred
    if not source_pred.exists():
        raise FileNotFoundError(source_pred)

    if not model_path.exists() or not threshold_path.exists():
        raise FileNotFoundError(f"missing model artifacts for {lock_path}")

    state_rows = lock.get("state_universe", {}).get("rows", [])
    if not isinstance(state_rows, list) or not state_rows:
        raise ValueError(f"no state_universe rows in {lock_path}")
    state_meta = pd.DataFrame(state_rows)
    for col in ["bar_ticks", "horizon", "barrier_pips"]:
        state_meta[col] = pd.to_numeric(state_meta[col], errors="coerce")
    state_meta["candidate_uid"] = state_meta.apply(
        lambda r: _candidate_uid(
            symbol=symbol,
            bar_ticks=int(r["bar_ticks"]),
            horizon=int(r["horizon"]),
            state_id=str(r["state_id"]),
        ),
        axis=1,
    )
    allowed = set(state_meta["candidate_uid"].astype(str))

    pred = pd.read_parquet(source_pred)
    pred["test_month"] = pred.get("test_month", pd.Series(dtype=object)).map(_normalize_month)
    pred["candidate_uid"] = pred.get("candidate_uid", pd.Series(dtype=object)).astype(str)
    pred["close_ts"] = pd.to_datetime(
        pred.get("close_ts", pd.Series(dtype=object)), utc=True, errors="coerce"
    )
    pred = pred[
        (pred["test_month"] == month)
        & (pred["candidate_uid"].isin(allowed))
        & pred["close_ts"].notna()
    ].copy()
    if pred.empty:
        raise ValueError(f"no prediction rows found for {symbol} {month} in {source_pred}")

    bar_ticks_needed = sorted(
        {int(x) for x in state_meta["bar_ticks"].dropna().astype(int).unique().tolist()}
    )
    bar_parts: list[pd.DataFrame] = []
    bar_cols = [
        "close_ts",
        "hour_utc",
        "hl_first",
        "hl_first_mean_24",
        "hl_pos_frac_mean_24",
        "cost_est_pips",
        "range_pips",
        "spread_z",
        "tick_rate_z",
        "vel_pips_h1",
        "vel_z_h1",
        "vel_cost_units_h1",
    ]
    for bt in bar_ticks_needed:
        path = tick_velocity_dir / f"{symbol}_{int(bt)}tick_velocity.parquet"
        if not path.exists():
            raise FileNotFoundError(path)
        bars = pd.read_parquet(path, columns=bar_cols)
        bars["close_ts"] = pd.to_datetime(bars["close_ts"], utc=True, errors="coerce")
        bars = bars[bars["close_ts"].dt.strftime("%Y-%m") == month].copy()
        bars["bar_ticks"] = int(bt)
        bar_parts.append(bars)
    if not bar_parts:
        raise ValueError(f"no bar data loaded for {symbol} {month}")
    bars_all = pd.concat(bar_parts, ignore_index=True)

    feat_rows = _feature_frame_from_bars(rows=pred, bars=bars_all, state_meta=state_meta)
    missing_bars = (
        int(feat_rows["hour_utc"].isna().sum())
        if "hour_utc" in feat_rows.columns
        else len(feat_rows)
    )
    if missing_bars:
        raise ValueError(
            f"{symbol} {month}: {missing_bars} rows missing matching tick_velocity bars"
        )

    thr_cfg = json.loads(threshold_path.read_text(encoding="utf-8"))
    features = [str(x) for x in thr_cfg.get("features", [])]
    if not features:
        raise ValueError(f"threshold json missing features list: {threshold_path}")
    missing_features = [c for c in features if c not in feat_rows.columns]
    if missing_features:
        raise ValueError(f"{symbol} {month}: missing feature columns {missing_features}")

    model = CatBoostClassifier()
    model.load_model(str(model_path))
    arr = feat_rows[features].astype(float).to_numpy()
    feat_rows["pred_prob"] = model.predict_proba(arr)[:, 1].astype(float)
    feat_rows["threshold_exec"], feat_rows["threshold_source"] = _thresholds_for_close_ts(
        feat_rows["close_ts"], thr_cfg
    )
    feat_rows["selected_exec"] = (
        feat_rows["pred_prob"].to_numpy(dtype=float)
        >= feat_rows["threshold_exec"].to_numpy(dtype=float)
    ).astype(int)
    feat_rows["threshold_mode"] = str(thr_cfg.get("threshold_source", "default"))
    feat_rows["threshold_days"] = int(thr_cfg.get("rolling_threshold_days", 0) or 0)
    feat_rows["library"] = (
        feat_rows.get("library", pd.Series(["oco"] * len(feat_rows))).fillna("oco").astype(str)
    )

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
    for extra in ["event_ordinal", "scored_row_id"]:
        if extra in feat_rows.columns:
            keep_cols.append(extra)
    frozen = (
        feat_rows[keep_cols]
        .copy()
        .sort_values(["close_ts", "candidate_uid"])
        .reset_index(drop=True)
    )

    out_path = lock_path.parent / f"{symbol.lower()}_oco_locked_predictions.parquet"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    frozen.to_parquet(out_path, index=False)
    frozen_sha = _sha256(out_path)

    old_hash = str(artifacts.get("predictions", {}).get("sha256", "")).strip()
    if "predictions" not in artifacts:
        artifacts["predictions"] = {}
    artifacts["predictions"]["path"] = f"{symbol.lower()}_oco_locked_predictions.parquet"
    artifacts["predictions"]["sha256"] = frozen_sha
    if "provenance" not in lock:
        lock["provenance"] = {}
    if "predictions" not in lock["provenance"]:
        lock["provenance"]["predictions"] = {}
    if source_pred.is_absolute():
        try:
            origin_rel = str(source_pred.resolve().relative_to(_find_repo_root(bundle_dir)))
        except ValueError:
            origin_rel = str(source_pred.resolve())
    else:
        origin_rel = str(source_pred)
    lock["provenance"]["predictions"]["origin"] = origin_rel
    lock["provenance"]["predictions"]["origin_sha256"] = _sha256(source_pred)

    lock["artifacts"] = artifacts
    if write_lock:
        lock_path.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    source_sha = _sha256(source_pred)
    return {
        "symbol": symbol,
        "month": month,
        "lock_path": str(lock_path),
        "source_predictions_path": str(source_pred),
        "source_predictions_sha256": source_sha,
        "lock_predictions_sha256_before": old_hash,
        "frozen_predictions_path": str(out_path),
        "frozen_predictions_sha256": frozen_sha,
        "rows_reconciled": int(len(frozen)),
        "selected_exec_rows": int(
            pd.to_numeric(frozen["selected_exec"], errors="coerce").fillna(0).astype(int).sum()
        ),
        "lock_updated": bool(write_lock),
    }


def main() -> None:
    p = argparse.ArgumentParser(
        description="Reconcile historical prediction artifacts into frozen month-local files"
    )
    p.add_argument("--history-dir", default="configs/research/governance/oco_history")
    p.add_argument("--tick-velocity-dir", default="data/analysis/tick_velocity")
    p.add_argument("--symbols", default="")
    p.add_argument("--months", default="")
    p.add_argument("--write-lock", default="true")
    p.add_argument("--summary-csv", default="")
    args = p.parse_args()

    history_dir = Path(str(args.history_dir))
    tick_velocity_dir = Path(str(args.tick_velocity_dir))
    symbols = [x.strip().upper() for x in str(args.symbols).split(",") if x.strip()]
    months = [_normalize_month(x) for x in str(args.months).split(",") if _normalize_month(x)]
    write_lock = str(args.write_lock).strip().lower() in {"1", "true", "yes", "y", "on"}

    rows = []
    for lock_path in _iter_lock_paths(history_dir, symbols, months):
        rows.append(
            reconcile_lock(
                lock_path=lock_path,
                tick_velocity_dir=tick_velocity_dir,
                write_lock=write_lock,
            )
        )
    summary = (
        pd.DataFrame(rows).sort_values(["symbol", "month"]).reset_index(drop=True)
        if rows
        else pd.DataFrame()
    )
    if str(args.summary_csv).strip():
        out = Path(str(args.summary_csv))
        out.parent.mkdir(parents=True, exist_ok=True)
        summary.to_csv(out, index=False)
    if summary.empty:
        print("[]")
    else:
        print(summary.to_json(orient="records", indent=2))


if __name__ == "__main__":
    main()
