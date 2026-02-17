#!/usr/bin/env python3
"""
Causal WFO ML gate on acceleration continuation contract (h bars).

Workflow per fold:
1) Build train-only acceleration threshold (quantile over abs accel).
2) Filter to actionable rows (abs accel >= threshold).
3) Fit classifier on early-train slice, tune gate threshold on late-train slice.
4) Evaluate baseline vs gated on OOS year.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from behemoth.config import ACTIVE_LEG_HIGH, ACTIVE_LEG_LOW
from scripts.lib.robust_kf_features import compute_robust_kf_series_features
from scripts.report_strategy_fx_comm_multi_tf import (
    OIL_LINKED_PAIRS,
    PAIR_WHITELIST_BASE,
    _metrics_with_risk,
)
from scripts.sweep_exit_params_short_tf import _build_pair_states
from pipelines.build_events_h1 import (
    PAIRS as H1_PAIRS,
    compute_kalman_states as compute_kalman_states_m60,
    compute_z_scores as compute_z_scores_m60,
    load_pair_data as load_pair_data_m60,
)


BAR_MINUTES = {"m5": 5, "m15": 15, "m60": 60}
MODEL_SEED_OFFSET = {"hgbt": 101, "logit": 211}


def _parse_float_grid(s: str) -> list[float]:
    vals = [float(x.strip()) for x in str(s).split(",") if x.strip()]
    if not vals:
        raise ValueError("Empty float grid")
    return vals


def _parse_str_grid(s: str) -> list[str]:
    vals = [x.strip().lower() for x in str(s).split(",") if x.strip()]
    if not vals:
        raise ValueError("Empty model grid")
    return vals


def _first_hit_contract(path: np.ndarray, tp_bps: float, sl_bps: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return pnl, duration_bars, outcome for directed horizon path."""
    horizon = int(path.shape[1])
    tp_hit = path >= float(tp_bps)
    sl_hit = path <= -float(sl_bps)

    any_tp = tp_hit.any(axis=1)
    any_sl = sl_hit.any(axis=1)
    k_tp = np.where(any_tp, tp_hit.argmax(axis=1) + 1, 99)
    k_sl = np.where(any_sl, sl_hit.argmax(axis=1) + 1, 99)

    outcome = np.where(k_tp < k_sl, 1, np.where(k_sl < k_tp, -1, 0))
    duration = np.where(outcome == 1, k_tp, np.where(outcome == -1, k_sl, horizon)).astype(int)
    pnl = np.where(outcome == 1, float(tp_bps), np.where(outcome == -1, -float(sl_bps), path[:, horizon - 1]))
    return pnl.astype(float), duration.astype(int), outcome.astype(int)


def _build_robust_lookup(state_cache: dict[str, dict[str, dict]]) -> dict[str, dict[str, dict[str, np.ndarray]]]:
    out: dict[str, dict[str, dict[str, np.ndarray]]] = {"m5": {}, "m15": {}, "m60": {}}
    for tf, pair_map in state_cache.items():
        for pair, st in pair_map.items():
            z = np.asarray(st.get("z", []), dtype=float)
            ts = np.asarray(st.get("ts", []), dtype="int64")
            if len(z) == 0 or len(ts) == 0:
                continue
            feats = compute_robust_kf_series_features(
                z=z,
                ts_ns=ts,
                student_df=5.0,
                huber_c=2.5,
                ew_alpha=0.04,
                tod_alpha=0.05,
                jump_prior=0.04,
                jump_var_mult=9.0,
            )
            feats["ts"] = ts
            out[tf][pair] = feats
    return out


def _build_pair_states_m60_with_betas(pair_whitelist: list[str]) -> dict[str, dict]:
    states: dict[str, dict] = {}
    for name, fx, fy, cx, cy, *_ in H1_PAIRS:
        if name not in pair_whitelist:
            continue
        df = load_pair_data_m60(fx, fy, cx, cy)
        if df is None or len(df) == 0:
            continue
        y = np.log(np.asarray(df["Y"], dtype=float))
        x = np.log(np.asarray(df["X"], dtype=float))
        ts = np.asarray(df["timestamp"]).astype("int64")
        betas, errors, _ = compute_kalman_states_m60(y, x)
        z_scores = compute_z_scores_m60(errors)
        states[name] = {
            "y": y,
            "x": x,
            "betas": np.asarray(betas, dtype=float),
            "z": np.asarray(z_scores, dtype=float),
            "ts": ts,
        }
    return states


def _context_at_ts(lookup: dict[str, dict[str, dict[str, np.ndarray]]], tf: str, pair: str, ts_ns: np.ndarray, col: str) -> np.ndarray:
    src = lookup.get(tf, {}).get(pair)
    if src is None:
        return np.zeros(len(ts_ns), dtype=float)
    src_ts = np.asarray(src.get("ts", []), dtype="int64")
    arr = np.asarray(src.get(col, []), dtype=float)
    if len(src_ts) == 0 or len(arr) == 0:
        return np.zeros(len(ts_ns), dtype=float)
    idx = np.searchsorted(src_ts, ts_ns, side="right") - 1
    out = np.zeros(len(ts_ns), dtype=float)
    ok = idx >= 0
    if np.any(ok):
        idx_ok = np.clip(idx[ok], 0, len(arr) - 1)
        out[ok] = arr[idx_ok]
    return out


def _timeframe_context(target_tf: str) -> list[str]:
    return [tf for tf in ["m5", "m15", "m60"] if tf != target_tf]


def _build_dataset(timeframe: str, h_bars: int, tp_bps: float, sl_bps: float, exclude_oil: bool) -> pd.DataFrame:
    tf = str(timeframe).lower()
    if tf not in BAR_MINUTES:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    horizon = int(h_bars)
    if horizon < 1:
        raise ValueError("h_bars must be >= 1")
    bar_ns = int(pd.Timedelta(minutes=BAR_MINUTES[tf]).value)

    pair_whitelist = list(PAIR_WHITELIST_BASE)
    if bool(exclude_oil):
        pair_whitelist = [p for p in pair_whitelist if p not in OIL_LINKED_PAIRS]

    state_cache = {
        "m5": _build_pair_states("m5", pair_whitelist),
        "m15": _build_pair_states("m15", pair_whitelist),
        "m60": _build_pair_states_m60_with_betas(pair_whitelist),
    }
    states = state_cache[tf]
    robust_lookup = _build_robust_lookup(state_cache)
    parts: list[pd.DataFrame] = []

    for pair, st in states.items():
        z = np.asarray(st["z"], dtype=float)
        ts = np.asarray(st["ts"], dtype="int64")
        beta = np.asarray(st["betas"], dtype=float)
        y = np.asarray(st["y"], dtype=float)
        x = np.asarray(st["x"], dtype=float)
        n = min(len(z), len(ts), len(beta), len(y), len(x))
        if n < 7:
            continue

        z = z[:n]
        ts = ts[:n]
        beta = beta[:n]
        y = y[:n]
        x = x[:n]

        feats = robust_lookup.get(tf, {}).get(pair)
        if feats is None:
            continue
        acc = np.asarray(feats["kf_z_accel"], dtype=float)

        m = n - horizon
        if m <= 0:
            continue
        acc = acc[:m]
        ts0 = ts[:m]
        b = beta[:m]
        z0 = z[:m]

        leg_y = b < float(ACTIVE_LEG_LOW)
        leg_x = b > float(ACTIVE_LEG_HIGH)
        active = leg_y | leg_x

        p = np.empty((horizon + 1, m), dtype=float)
        for k in range(horizon + 1):
            yk = y[k : k + m]
            xk = x[k : k + m]
            p[k] = np.where(leg_y, yk, np.where(leg_x, xk, np.nan))

        direction = np.sign(acc)
        valid = active & np.isfinite(acc) & (direction != 0.0)
        for k in range(horizon + 1):
            valid &= np.isfinite(p[k])
        if not np.any(valid):
            continue

        ts0 = ts0[valid]
        acc0 = acc[valid]
        abs_acc = np.abs(acc0)
        direction = direction[valid]
        z0 = z0[valid]
        b0 = b[valid]
        p0 = p[0, valid]

        path = np.empty((len(ts0), horizon), dtype=float)
        for h in range(1, horizon + 1):
            path[:, h - 1] = direction * (p[h, valid] - p0) * 10000.0

        pnl_clipped, duration, outcome = _first_hit_contract(path, tp_bps=float(tp_bps), sl_bps=float(sl_bps))
        dur_idx = np.clip(duration.astype(int) - 1, 0, horizon - 1)
        pnl_unclipped = path[np.arange(len(path)), dur_idx]
        exit_ts = ts0 + duration.astype("int64") * bar_ns

        dt = pd.to_datetime(ts0, unit="ns", utc=True)
        ctx = {}
        for ctf in _timeframe_context(tf):
            for col in ["kf_robust_z", "kf_tod_scale", "kf_z_vel", "kf_z_accel"]:
                ctx[f"{ctf}_{col}"] = _context_at_ts(robust_lookup, ctf, pair, ts0, col)

        df = pd.DataFrame(
            {
                "pair": pair,
                "timeframe": tf,
                "timestamp": ts0.astype("int64"),
                "exit_ts": exit_ts.astype("int64"),
                "duration_bars": duration.astype(int),
                "pnl_bps_unclipped": pnl_unclipped.astype(float),
                "pnl_bps_clipped": pnl_clipped.astype(float),
                # Primary PnL is set in main() via --primary-pnl.
                "pnl_bps": pnl_unclipped.astype(float),
                "outcome": outcome.astype(int),
                "abs_accel": abs_acc.astype(float),
                "accel_sign": np.sign(acc0).astype(int),
                "z_score": z0.astype(float),
                "beta": b0.astype(float),
                "entry_hour_utc": dt.hour.astype(int),
                "entry_dow_utc": dt.dayofweek.astype(int),
                "kf_abs_z": np.asarray(feats["kf_abs_z"][:m], dtype=float)[valid],
                "kf_robust_z": np.asarray(feats["kf_robust_z"][:m], dtype=float)[valid],
                "kf_student_loglik": np.asarray(feats["kf_student_loglik"][:m], dtype=float)[valid],
                "kf_tod_scale": np.asarray(feats["kf_tod_scale"][:m], dtype=float)[valid],
                "kf_jump_prob": np.asarray(feats["kf_jump_prob"][:m], dtype=float)[valid],
                "kf_z_vel": np.asarray(feats["kf_z_vel"][:m], dtype=float)[valid],
                "kf_z_accel": np.asarray(feats["kf_z_accel"][:m], dtype=float)[valid],
                "good_trade_unclipped": (pnl_unclipped > 0.0).astype(int),
                "good_trade_clipped": (pnl_clipped > 0.0).astype(int),
                "good_trade": (pnl_unclipped > 0.0).astype(int),
            }
        )
        for k, v in ctx.items():
            df[k] = np.asarray(v, dtype=float)
        parts.append(df)

    if not parts:
        raise RuntimeError("No rows produced for dataset")
    out = pd.concat(parts, ignore_index=True)
    return out.sort_values(["timestamp", "pair"]).reset_index(drop=True)


def _feature_matrix(df: pd.DataFrame) -> pd.DataFrame:
    num_cols = {
        "abs_accel": pd.to_numeric(df["abs_accel"], errors="coerce"),
        "accel_sign": pd.to_numeric(df["accel_sign"], errors="coerce"),
        "z_score": pd.to_numeric(df["z_score"], errors="coerce"),
        "beta": pd.to_numeric(df["beta"], errors="coerce"),
        "entry_hour_utc": pd.to_numeric(df["entry_hour_utc"], errors="coerce"),
        "entry_dow_utc": pd.to_numeric(df["entry_dow_utc"], errors="coerce"),
        "kf_abs_z": pd.to_numeric(df["kf_abs_z"], errors="coerce"),
        "kf_robust_z": pd.to_numeric(df["kf_robust_z"], errors="coerce"),
        "kf_student_loglik": pd.to_numeric(df["kf_student_loglik"], errors="coerce"),
        "kf_tod_scale": pd.to_numeric(df["kf_tod_scale"], errors="coerce"),
        "kf_jump_prob": pd.to_numeric(df["kf_jump_prob"], errors="coerce"),
        "kf_z_vel": pd.to_numeric(df["kf_z_vel"], errors="coerce"),
        "kf_z_accel": pd.to_numeric(df["kf_z_accel"], errors="coerce"),
    }
    for c in df.columns:
        if c.endswith("_kf_robust_z") or c.endswith("_kf_tod_scale") or c.endswith("_kf_z_vel") or c.endswith("_kf_z_accel"):
            num_cols[c] = pd.to_numeric(df[c], errors="coerce")

    num = pd.DataFrame(
        num_cols,
        index=df.index,
    ).fillna(0.0)
    cat = pd.get_dummies(df[["pair", "timeframe"]].astype(str), drop_first=False, dtype=float)
    return pd.concat([num, cat], axis=1).fillna(0.0)


def _align_cols(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    out = df.copy()
    for c in cols:
        if c not in out.columns:
            out[c] = 0.0
    return out[cols].copy()


def _add_lagged_features(df: pd.DataFrame, lag_depth: int) -> pd.DataFrame:
    """
    Add causal lagged features per pair/timeframe.
    Lags are built from past rows only (groupby+shift on time-sorted rows).
    """
    depth = int(max(0, lag_depth))
    if depth <= 0 or df.empty:
        return df

    out = df.sort_values(["pair", "timeframe", "timestamp"]).copy()
    base_cols = [
        "abs_accel",
        "z_score",
        "beta",
        "kf_abs_z",
        "kf_robust_z",
        "kf_student_loglik",
        "kf_tod_scale",
        "kf_jump_prob",
        "kf_z_vel",
        "kf_z_accel",
    ]
    extra_cols = [c for c in out.columns if c.endswith("_kf_robust_z") or c.endswith("_kf_tod_scale") or c.endswith("_kf_z_vel") or c.endswith("_kf_z_accel")]
    lag_cols = [c for c in base_cols + extra_cols if c in out.columns]
    grp = out.groupby(["pair", "timeframe"], sort=False)
    for k in range(1, depth + 1):
        for c in lag_cols:
            out[f"{c}_lag{k}"] = grp[c].shift(k)

    # Missing lags at sequence starts are unknown-in-real-time; use neutral fill.
    lag_created = [c for c in out.columns if c.endswith(tuple([f"_lag{i}" for i in range(1, depth + 1)]))]
    for c in lag_created:
        out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0.0)
    return out.sort_values(["timestamp", "pair"]).reset_index(drop=True)


def _fit_predict(model_name: str, X_fit: pd.DataFrame, y_fit: pd.Series, X_pred: pd.DataFrame, random_state: int) -> np.ndarray:
    y = y_fit.astype(int).to_numpy()
    if len(np.unique(y)) < 2:
        return np.full(len(X_pred), 0.5, dtype=float)

    if model_name == "hgbt":
        model = HistGradientBoostingClassifier(
            loss="log_loss",
            max_depth=4,
            learning_rate=0.05,
            max_iter=350,
            min_samples_leaf=80,
            random_state=int(random_state),
        )
        model.fit(X_fit, y)
        return np.clip(model.predict_proba(X_pred)[:, 1], 0.0, 1.0)

    if model_name == "logit":
        model = LogisticRegression(
            solver="lbfgs",
            class_weight="balanced",
            max_iter=1200,
            random_state=int(random_state),
        )
        model.fit(X_fit, y)
        return np.clip(model.predict_proba(X_pred)[:, 1], 0.0, 1.0)

    raise ValueError(f"Unsupported model: {model_name}")


def _model_seed(base_seed: int, year: int, model_name: str, extra: int = 0) -> int:
    # Use deterministic per-model offsets (not Python's randomized hash).
    offset = int(MODEL_SEED_OFFSET.get(str(model_name), 0))
    return int(base_seed) + int(year) + offset + int(extra)


def _metrics_for_col(df: pd.DataFrame, pnl_col: str, risk_bps: float) -> dict[str, float]:
    if df.empty:
        return {
            "trades": 0,
            "mean_pnl_per_trade_bps": 0.0,
            "sharpe": 0.0,
            "time_in_market_pct": 0.0,
            "worst_single_day_bps": 0.0,
            "max_daily_dd_bps": 0.0,
        }
    if pnl_col not in df.columns:
        raise KeyError(f"Missing pnl column: {pnl_col}")
    work = df.copy()
    work["pnl_bps"] = pd.to_numeric(work[pnl_col], errors="coerce").fillna(0.0).astype(float)
    return _metrics_with_risk(work, risk_bps=float(risk_bps))


def _set_primary_pnl(df: pd.DataFrame, primary_pnl: str) -> pd.DataFrame:
    mode = str(primary_pnl).lower().strip()
    if mode not in {"unclipped", "clipped"}:
        raise ValueError(f"Unsupported primary_pnl: {primary_pnl}")
    out = df.copy()
    if mode == "unclipped":
        out["pnl_bps"] = pd.to_numeric(out["pnl_bps_unclipped"], errors="coerce").fillna(0.0).astype(float)
        out["good_trade"] = (out["pnl_bps"] > 0.0).astype(int)
        out["pnl_bps_secondary"] = pd.to_numeric(out["pnl_bps_clipped"], errors="coerce").fillna(0.0).astype(float)
        out["good_trade_secondary"] = out["good_trade_clipped"].astype(int)
    else:
        out["pnl_bps"] = pd.to_numeric(out["pnl_bps_clipped"], errors="coerce").fillna(0.0).astype(float)
        out["good_trade"] = (out["pnl_bps"] > 0.0).astype(int)
        out["pnl_bps_secondary"] = pd.to_numeric(out["pnl_bps_unclipped"], errors="coerce").fillna(0.0).astype(float)
        out["good_trade_secondary"] = out["good_trade_unclipped"].astype(int)
    return out


def _choose_threshold(cal_df: pd.DataFrame, p_good: np.ndarray, grid: list[float], min_trade_frac: float, min_trades_abs: int) -> dict | None:
    base_n = len(cal_df)
    out: list[dict] = []
    for thr in grid:
        keep = p_good >= float(thr)
        n = int(np.sum(keep))
        if n < int(min_trades_abs):
            continue
        frac = float(n / max(base_n, 1))
        if frac < float(min_trade_frac):
            continue
        sub = cal_df.loc[keep].copy()
        m = _metrics_with_risk(sub, risk_bps=100.0)
        out.append(
            {
                "threshold": float(thr),
                "trades": int(m["trades"]),
                "trade_frac": frac,
                "mean_bps": float(m["mean_pnl_per_trade_bps"]),
                "sharpe": float(m["sharpe"]),
                "worst_day_bps": float(m["worst_single_day_bps"]),
                "score": float(m["mean_pnl_per_trade_bps"]) + 0.10 * float(m["sharpe"]) - 0.00005 * abs(float(m["worst_single_day_bps"])),
            }
        )
    if not out:
        return None
    g = pd.DataFrame(out).sort_values(["score", "mean_bps", "trades"], ascending=[False, False, False]).reset_index(drop=True)
    return g.iloc[0].to_dict()


def main() -> None:
    p = argparse.ArgumentParser(description="m15 accel-h5 ML gate WFO")
    p.add_argument("--timeframe", default="m15", choices=["m5", "m15", "m60"])
    p.add_argument("--h-bars", type=int, default=5)
    p.add_argument("--tp-bps", type=float, default=6.0)
    p.add_argument("--sl-bps", type=float, default=2.0)
    p.add_argument("--accel-quantile", type=float, default=0.90)
    p.add_argument("--lag-depth", type=int, default=3)
    p.add_argument("--models", default="hgbt,logit")
    p.add_argument("--threshold-grid", default="0.50,0.55,0.60,0.65,0.70,0.75,0.80,0.85,0.90")
    p.add_argument("--fit-frac", type=float, default=0.70)
    p.add_argument("--min-trade-frac-cal", type=float, default=0.10)
    p.add_argument("--min-trades-cal", type=int, default=200)
    p.add_argument("--start-test-year", type=int, default=2020)
    p.add_argument("--end-test-year", type=int, default=2025)
    p.add_argument("--primary-pnl", choices=["unclipped", "clipped"], default="unclipped")
    p.add_argument("--exclude-oil", action="store_true", default=True)
    p.add_argument("--random-state", type=int, default=42)
    p.add_argument("--out-prefix", default="m15_accel_h5_ml_gate")
    args = p.parse_args()

    models = _parse_str_grid(args.models)
    thr_grid = _parse_float_grid(args.threshold_grid)

    print(f"Building {args.timeframe} contract dataset...")
    df = _build_dataset(
        timeframe=str(args.timeframe),
        h_bars=int(args.h_bars),
        tp_bps=float(args.tp_bps),
        sl_bps=float(args.sl_bps),
        exclude_oil=bool(args.exclude_oil),
    )
    print(f"Rows: {len(df):,}")
    df = _add_lagged_features(df, lag_depth=int(args.lag_depth))
    df = _set_primary_pnl(df, primary_pnl=str(args.primary_pnl))

    fold_rows: list[dict] = []
    oos_rows: list[pd.DataFrame] = []

    for year in range(int(args.start_test_year), int(args.end_test_year) + 1):
        test_start = pd.Timestamp(year=year, month=1, day=1, tz="UTC").value
        test_end = pd.Timestamp(year=year + 1, month=1, day=1, tz="UTC").value
        # Causal boundary: training labels must be fully realized before the test window.
        tr = df[df["exit_ts"] < test_start].copy()
        te = df[(df["timestamp"] >= test_start) & (df["timestamp"] < test_end)].copy()
        if len(tr) < 5000 or len(te) < 500:
            continue

        q_thr = float(tr["abs_accel"].quantile(float(args.accel_quantile)))
        trq = tr[tr["abs_accel"] >= q_thr].copy()
        teq = te[te["abs_accel"] >= q_thr].copy()
        if len(trq) < 1000 or len(teq) < 100:
            continue

        trq = trq.sort_values(["timestamp", "pair"]).reset_index(drop=True)
        cut = int(round(len(trq) * float(args.fit_frac)))
        cut = max(500, min(cut, len(trq) - 500))
        fit_df = trq.iloc[:cut].copy()
        cal_df = trq.iloc[cut:].copy()
        if not cal_df.empty:
            # Purge overlap: fit rows cannot consume price-path information from calibration period.
            cal_start_ts = int(cal_df["timestamp"].min())
            fit_df = fit_df[fit_df["exit_ts"] < cal_start_ts].copy()
        if len(fit_df) < 500 or len(cal_df) < 500:
            continue

        X_fit = _feature_matrix(fit_df)
        X_cal = _align_cols(_feature_matrix(cal_df), X_fit.columns.tolist())
        X_te = _align_cols(_feature_matrix(teq), X_fit.columns.tolist())
        y_fit = fit_df["good_trade"].astype(int)

        best: dict | None = None
        for model_name in models:
            p_cal = _fit_predict(
                model_name=model_name,
                X_fit=X_fit,
                y_fit=y_fit,
                X_pred=X_cal,
                random_state=_model_seed(args.random_state, year, model_name),
            )
            chosen = _choose_threshold(
                cal_df=cal_df,
                p_good=p_cal,
                grid=thr_grid,
                min_trade_frac=float(args.min_trade_frac_cal),
                min_trades_abs=int(args.min_trades_cal),
            )
            if chosen is None:
                continue
            chosen["model"] = model_name
            if best is None or float(chosen["score"]) > float(best["score"]):
                best = chosen

        if best is None:
            continue

        p_te = _fit_predict(
            model_name=str(best["model"]),
            X_fit=X_fit,
            y_fit=y_fit,
            X_pred=X_te,
            random_state=_model_seed(args.random_state, year, str(best["model"]), extra=999),
        )
        keep = p_te >= float(best["threshold"])
        gate_te = teq.loc[keep].copy()

        base_m = _metrics_with_risk(teq, risk_bps=100.0)
        gate_m = _metrics_with_risk(gate_te, risk_bps=100.0)
        base_m_sec = _metrics_for_col(teq, pnl_col="pnl_bps_secondary", risk_bps=100.0)
        gate_m_sec = _metrics_for_col(gate_te, pnl_col="pnl_bps_secondary", risk_bps=100.0)
        fold_rows.append(
            {
                "year": int(year),
                "primary_pnl_mode": str(args.primary_pnl),
                "accel_threshold": float(q_thr),
                "model": str(best["model"]),
                "gate_threshold": float(best["threshold"]),
                "cal_trade_frac": float(best["trade_frac"]),
                "base_trades": int(base_m["trades"]),
                "base_mean_bps": float(base_m["mean_pnl_per_trade_bps"]),
                "base_sharpe": float(base_m["sharpe"]),
                "base_tim_pct": float(base_m["time_in_market_pct"]),
                "base_mean_bps_secondary": float(base_m_sec["mean_pnl_per_trade_bps"]),
                "base_sharpe_secondary": float(base_m_sec["sharpe"]),
                "gate_trades": int(gate_m["trades"]),
                "gate_mean_bps": float(gate_m["mean_pnl_per_trade_bps"]),
                "gate_sharpe": float(gate_m["sharpe"]),
                "gate_tim_pct": float(gate_m["time_in_market_pct"]),
                "gate_worst_day_bps": float(gate_m["worst_single_day_bps"]),
                "gate_mean_bps_secondary": float(gate_m_sec["mean_pnl_per_trade_bps"]),
                "gate_sharpe_secondary": float(gate_m_sec["sharpe"]),
                "delta_mean_bps": float(gate_m["mean_pnl_per_trade_bps"] - base_m["mean_pnl_per_trade_bps"]),
            }
        )

        out = teq.copy()
        out["fold_year"] = int(year)
        out["model"] = str(best["model"])
        out["gate_threshold"] = float(best["threshold"])
        out["p_good"] = p_te
        out["keep_trade"] = keep.astype(bool)
        out["primary_pnl_mode"] = str(args.primary_pnl)
        oos_rows.append(out)

        print(
            f"Fold {year}: model={best['model']} thr={best['threshold']:.2f} "
            f"| base={base_m['mean_pnl_per_trade_bps']:.3f}bps ({int(base_m['trades'])}) "
            f"| gate={gate_m['mean_pnl_per_trade_bps']:.3f}bps ({int(gate_m['trades'])})"
        )

    if not fold_rows:
        raise RuntimeError("No valid folds")

    folds_df = pd.DataFrame(fold_rows).sort_values("year").reset_index(drop=True)
    oos_df = pd.concat(oos_rows, ignore_index=True) if oos_rows else pd.DataFrame()
    keep_df = oos_df[oos_df["keep_trade"]].copy() if not oos_df.empty else pd.DataFrame()
    base_df = oos_df.copy()

    base_all = _metrics_with_risk(base_df, risk_bps=100.0) if not base_df.empty else {"trades": 0, "mean_pnl_per_trade_bps": 0.0, "sharpe": 0.0, "time_in_market_pct": 0.0, "worst_single_day_bps": 0.0, "max_daily_dd_bps": 0.0}
    gate_all = _metrics_with_risk(keep_df, risk_bps=100.0) if not keep_df.empty else {"trades": 0, "mean_pnl_per_trade_bps": 0.0, "sharpe": 0.0, "time_in_market_pct": 0.0, "worst_single_day_bps": 0.0, "max_daily_dd_bps": 0.0}
    base_all_sec = _metrics_for_col(base_df, pnl_col="pnl_bps_secondary", risk_bps=100.0)
    gate_all_sec = _metrics_for_col(keep_df, pnl_col="pnl_bps_secondary", risk_bps=100.0)
    secondary_mode = "clipped" if str(args.primary_pnl) == "unclipped" else "unclipped"

    summary_df = pd.DataFrame(
        [
            {
                "variant": "baseline_q_accel",
                "primary_pnl_mode": str(args.primary_pnl),
                "secondary_pnl_mode": secondary_mode,
                "folds": int(len(folds_df)),
                "trades": int(base_all["trades"]),
                "mean_pnl_per_trade_bps": float(base_all["mean_pnl_per_trade_bps"]),
                "sharpe": float(base_all["sharpe"]),
                "time_in_market_pct": float(base_all["time_in_market_pct"]),
                "worst_single_day_bps": float(base_all["worst_single_day_bps"]),
                "max_daily_dd_bps": float(base_all["max_daily_dd_bps"]),
                "mean_pnl_per_trade_bps_secondary": float(base_all_sec["mean_pnl_per_trade_bps"]),
                "sharpe_secondary": float(base_all_sec["sharpe"]),
                "worst_single_day_bps_secondary": float(base_all_sec["worst_single_day_bps"]),
                "max_daily_dd_bps_secondary": float(base_all_sec["max_daily_dd_bps"]),
            },
            {
                "variant": "ml_gated",
                "primary_pnl_mode": str(args.primary_pnl),
                "secondary_pnl_mode": secondary_mode,
                "folds": int(len(folds_df)),
                "trades": int(gate_all["trades"]),
                "mean_pnl_per_trade_bps": float(gate_all["mean_pnl_per_trade_bps"]),
                "sharpe": float(gate_all["sharpe"]),
                "time_in_market_pct": float(gate_all["time_in_market_pct"]),
                "worst_single_day_bps": float(gate_all["worst_single_day_bps"]),
                "max_daily_dd_bps": float(gate_all["max_daily_dd_bps"]),
                "mean_pnl_per_trade_bps_secondary": float(gate_all_sec["mean_pnl_per_trade_bps"]),
                "sharpe_secondary": float(gate_all_sec["sharpe"]),
                "worst_single_day_bps_secondary": float(gate_all_sec["worst_single_day_bps"]),
                "max_daily_dd_bps_secondary": float(gate_all_sec["max_daily_dd_bps"]),
            },
        ]
    )

    out_dir = Path("data/analysis")
    out_dir.mkdir(parents=True, exist_ok=True)
    folds_path = out_dir / f"{args.out_prefix}_folds.csv"
    trades_path = out_dir / f"{args.out_prefix}_oos_scored.csv"
    summary_path = out_dir / f"{args.out_prefix}_summary.csv"
    folds_df.to_csv(folds_path, index=False)
    oos_df.to_csv(trades_path, index=False)
    summary_df.to_csv(summary_path, index=False)

    print("\nSaved:")
    print(f"- {folds_path}")
    print(f"- {trades_path}")
    print(f"- {summary_path}")
    print("\nSummary:")
    print(summary_df.to_string(index=False))


if __name__ == "__main__":
    main()
