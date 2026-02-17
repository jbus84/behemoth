#!/usr/bin/env python3
"""
Causal walk-forward early-warning model for loss-cluster detection.

Goal:
- Predict near-term losing clusters on short legs (m5/m15) before entry.
- Gate or downsize entries using calibrated P(cluster_bad).
- Optimize train-only thresholds under DD-first constraints.
"""

from __future__ import annotations

import argparse
import itertools
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.lib.cluster_features import add_cluster_state_features
from scripts.lib.cluster_labels import build_cluster_day_labels, build_cluster_trade_labels, label_distribution
from scripts.report_strategy_fx_comm_multi_tf import (
    OIL_LINKED_PAIRS,
    PAIR_WHITELIST_BASE,
    _apply_guardrail,
    _derive_risk_bps,
    _metrics_with_risk,
    _normalize_ts_ns,
)

EVENT_PATHS = {
    ("m5", "MOM"): ("data/events/events_m5_8yr_v3_mom.csv", "pair"),
    ("m5", "REV"): ("data/events/events_m5_8yr_v3_rev.csv", "pair"),
    ("m15", "MOM"): ("data/events/events_m15_8yr_v3_mom.csv", "pair"),
    ("m15", "REV"): ("data/events/events_m15_8yr_v3_rev.csv", "pair"),
    ("m60", "MOM"): ("data/events/events_h1_8yr_v3_mom.csv", "symbol"),
    ("m60", "REV"): ("data/events/events_h1_8yr_v3_rev.csv", "symbol"),
}


@dataclass(frozen=True)
class FoldWindow:
    test_year: int
    train_end_ts_ns: int
    test_start_ts_ns: int
    test_end_ts_ns: int


def _empty_events_frame() -> pd.DataFrame:
    cols = [
        "pair",
        "timeframe",
        "strategy_type",
        "timestamp",
        "exit_ts",
        "pnl_bps",
        "duration_bars",
        "max_hold_bars",
        "z_score",
        "z_velocity",
        "z_accel",
        "rolling_win_rate_10",
        "rolling_avg_pnl_10",
        "active_leg",
        "side",
    ]
    return pd.DataFrame(columns=cols)


def _year_bounds_ns(year: int) -> tuple[int, int]:
    start = pd.Timestamp(year=year, month=1, day=1, tz="UTC")
    end = pd.Timestamp(year=year + 1, month=1, day=1, tz="UTC")
    return int(start.value), int(end.value)


def _make_folds(start_year: int, end_year: int, embargo_days: int) -> list[FoldWindow]:
    folds: list[FoldWindow] = []
    embargo_ns = int(pd.Timedelta(days=embargo_days).value)
    for year in range(start_year, end_year + 1):
        test_start, test_end = _year_bounds_ns(year)
        train_end = test_start - embargo_ns
        folds.append(
            FoldWindow(
                test_year=year,
                train_end_ts_ns=int(train_end),
                test_start_ts_ns=int(test_start),
                test_end_ts_ns=int(test_end),
            )
        )
    return folds


def _parse_grid(s: str) -> list[float]:
    out: list[float] = []
    for token in str(s).split(","):
        token = token.strip()
        if not token:
            continue
        out.append(float(token))
    if not out:
        raise ValueError("Grid cannot be empty")
    return sorted({float(x) for x in out})


def _normalize_strategy_spec(raw_spec: str) -> str:
    tokens = [t.strip().upper() for t in str(raw_spec).split("+") if t.strip()]
    if not tokens:
        raise ValueError(f"Empty strategy spec: {raw_spec}")
    if "NONE" in tokens:
        if len(tokens) != 1:
            raise ValueError(f"NONE cannot be combined with other strategies: {raw_spec}")
        return "NONE"
    for tok in tokens:
        if tok not in {"MOM", "REV"}:
            raise ValueError(f"Unsupported strategy in mix: {tok}")
    ordered = [tok for tok in ["MOM", "REV"] if tok in set(tokens)]
    return "+".join(ordered)


def _parse_strategy_mixes(s: str) -> list[dict[str, str]]:
    raw = str(s).strip()
    if raw.lower() in {"all", "*"}:
        mixes: list[dict[str, str]] = []
        for m5, m15, m60 in itertools.product(["MOM", "REV"], repeat=3):
            mixes.append({"m5": m5, "m15": m15, "m60": m60})
        return mixes

    mixes: list[dict[str, str]] = []
    parts = [x.strip() for x in raw.split(";") if x.strip()]
    for part in parts:
        m: dict[str, str] = {}
        for tok in part.split(","):
            tok = tok.strip()
            if not tok:
                continue
            if "=" not in tok:
                raise ValueError(f"Invalid mix token: {tok}")
            tf, strat = tok.split("=", 1)
            tf = tf.strip().lower()
            strat = _normalize_strategy_spec(strat.strip())
            if tf not in {"m5", "m15", "m60"}:
                raise ValueError(f"Unsupported timeframe in mix: {tf}")
            m[tf] = strat
        if set(m.keys()) != {"m5", "m15", "m60"}:
            raise ValueError(f"Mix must specify m5,m15,m60 exactly: {part}")
        if m["m5"] == "NONE" or m["m15"] == "NONE":
            raise ValueError("m5 and m15 cannot be NONE in this pipeline.")
        mixes.append(m)
    if not mixes:
        mixes.append({"m5": "MOM", "m15": "MOM+REV", "m60": "REV"})
    return mixes


def _mix_id(mix: dict[str, str]) -> str:
    def _token_id(spec: str) -> str:
        return "".join(part.strip().lower() for part in str(spec).split("+") if part.strip())

    return f"m5_{_token_id(mix['m5'])}__m15_{_token_id(mix['m15'])}__m60_{_token_id(mix['m60'])}"


def _load_events(
    path: str,
    strategy: str,
    timeframe: str,
    pair_col: str,
    pair_whitelist: list[str],
) -> pd.DataFrame:
    df = pd.read_csv(path)
    if pair_col != "pair":
        df = df.rename(columns={pair_col: "pair"})

    if "strategy_type" in df.columns:
        df = df[df["strategy_type"].astype(str).str.upper() == strategy].copy()
    df = df[df["pair"].isin(pair_whitelist)].copy()
    if df.empty:
        return _empty_events_frame()

    if "entry_exit_variant" in df.columns:
        df = df[df["entry_exit_variant"].astype(str) == "baseline"].copy()
    if "exit_policy" in df.columns:
        df = df[df["exit_policy"].astype(str) == "adaptive_entry_z"].copy()

    df["timestamp"] = _normalize_ts_ns(df["timestamp"])
    if "exit_ts" in df.columns:
        df["exit_ts"] = _normalize_ts_ns(df["exit_ts"])
    else:
        bar_minutes = {"m5": 5, "m15": 15, "m60": 60}[timeframe]
        duration_col = "duration_bars" if "duration_bars" in df.columns else "duration"
        d = pd.to_numeric(df[duration_col], errors="coerce").fillna(0).astype(int).clip(lower=0)
        bar_ns = int(pd.Timedelta(minutes=bar_minutes).value)
        df["exit_ts"] = df["timestamp"] + (d * bar_ns)

    if "duration_bars" in df.columns:
        df["duration_bars"] = pd.to_numeric(df["duration_bars"], errors="coerce")
    elif "duration" in df.columns:
        df["duration_bars"] = pd.to_numeric(df["duration"], errors="coerce")
    else:
        df["duration_bars"] = np.nan

    if "max_hold_bars" in df.columns:
        df["max_hold_bars"] = pd.to_numeric(df["max_hold_bars"], errors="coerce")
    else:
        df["max_hold_bars"] = np.nan

    if "z_score" not in df.columns and "entry_z" in df.columns:
        df["z_score"] = pd.to_numeric(df["entry_z"], errors="coerce")
    else:
        df["z_score"] = pd.to_numeric(df.get("z_score", np.nan), errors="coerce")

    if "side" not in df.columns:
        if "direction" in df.columns:
            dir_num = pd.to_numeric(df["direction"], errors="coerce").fillna(0.0)
            df["side"] = np.where(dir_num >= 0.0, "LONG", "SHORT")
        else:
            df["side"] = "UNKNOWN"

    out = pd.DataFrame(
        {
            "pair": df["pair"].astype(str),
            "timeframe": timeframe,
            "strategy_type": strategy,
            "timestamp": df["timestamp"].astype("int64"),
            "exit_ts": df["exit_ts"].astype("int64"),
            "pnl_bps": pd.to_numeric(df["pnl_bps"], errors="coerce").astype(float),
            "duration_bars": pd.to_numeric(df["duration_bars"], errors="coerce"),
            "max_hold_bars": pd.to_numeric(df["max_hold_bars"], errors="coerce"),
            "z_score": pd.to_numeric(df["z_score"], errors="coerce"),
            "z_velocity": pd.to_numeric(df.get("z_velocity", np.nan), errors="coerce"),
            "z_accel": pd.to_numeric(df.get("z_accel", np.nan), errors="coerce"),
            "rolling_win_rate_10": pd.to_numeric(df.get("rolling_win_rate_10", np.nan), errors="coerce"),
            "rolling_avg_pnl_10": pd.to_numeric(df.get("rolling_avg_pnl_10", np.nan), errors="coerce"),
            "active_leg": df.get("active_leg", "UNKNOWN").astype(str),
            "side": df["side"].astype(str),
        }
    )
    out = out.dropna(subset=["pair", "timestamp", "exit_ts", "pnl_bps"]).copy()
    return out.sort_values(["timestamp", "pair"]).reset_index(drop=True)


def _feature_matrix(df: pd.DataFrame) -> pd.DataFrame:
    ts = pd.to_datetime(df["timestamp"], unit="ns", utc=True)
    num = pd.DataFrame(
        {
            "abs_z": df["z_score"].abs().astype(float),
            "z_velocity": pd.to_numeric(df["z_velocity"], errors="coerce").astype(float),
            "z_accel": pd.to_numeric(df["z_accel"], errors="coerce").astype(float),
            "rolling_win_rate_10": pd.to_numeric(df["rolling_win_rate_10"], errors="coerce").astype(float),
            "rolling_avg_pnl_10": pd.to_numeric(df["rolling_avg_pnl_10"], errors="coerce").astype(float),
            "max_hold_bars": pd.to_numeric(df["max_hold_bars"], errors="coerce").astype(float),
            "entry_hour_utc": ts.dt.hour.astype(float),
            "entry_dow_utc": ts.dt.dayofweek.astype(float),
            "realized_loss_streak_3": pd.to_numeric(df["realized_loss_streak_3"], errors="coerce").astype(float),
            "realized_pnl_sum_5": pd.to_numeric(df["realized_pnl_sum_5"], errors="coerce").astype(float),
            "realized_pnl_sum_10": pd.to_numeric(df["realized_pnl_sum_10"], errors="coerce").astype(float),
            "realized_pnl_sum_20": pd.to_numeric(df["realized_pnl_sum_20"], errors="coerce").astype(float),
            "realized_dd_from_local_peak_20": pd.to_numeric(df["realized_dd_from_local_peak_20"], errors="coerce").astype(float),
            "trade_arrival_rate_1d": pd.to_numeric(df["trade_arrival_rate_1d"], errors="coerce").astype(float),
            "trade_arrival_rate_3d": pd.to_numeric(df["trade_arrival_rate_3d"], errors="coerce").astype(float),
            "recent_vol_proxy_20": pd.to_numeric(df["recent_vol_proxy_20"], errors="coerce").astype(float),
            "session_loss_rate_20": pd.to_numeric(df["session_loss_rate_20"], errors="coerce").astype(float),
        },
        index=df.index,
    )
    cat = pd.DataFrame(
        {
            "pair": df["pair"].astype(str),
            "timeframe": df["timeframe"].astype(str),
            "strategy_type": df["strategy_type"].astype(str),
            "side": df["side"].astype(str),
            "active_leg": df["active_leg"].astype(str),
        },
        index=df.index,
    )
    mat = pd.concat([num, pd.get_dummies(cat, drop_first=False, dtype=float)], axis=1)
    return mat.fillna(0.0)


def _pair_filter_set(train_guard_df: pd.DataFrame, cutoff: float) -> set[str]:
    if train_guard_df.empty:
        return set()
    keep: set[str] = set()
    for pair, sub in train_guard_df.groupby("pair", sort=True):
        pnl = sub["pnl_bps"].to_numpy(dtype=float)
        if len(pnl) < 50:
            continue
        v = float(np.std(pnl, ddof=1)) if len(pnl) > 1 else 0.0
        s = float(np.mean(pnl) / v * np.sqrt(252.0)) if v > 1e-12 else 0.0
        if s >= cutoff:
            keep.add(str(pair))
    if not keep:
        keep = set(train_guard_df["pair"].astype(str).unique().tolist())
    return keep


def _daily_pnl_curve(df: pd.DataFrame) -> pd.Series:
    if df.empty:
        return pd.Series(dtype="float64")
    days = pd.to_datetime(df["exit_ts"], unit="ns", utc=True).dt.normalize()
    daily = df.assign(_day=days).groupby("_day")["pnl_bps"].sum().sort_index()
    full_idx = pd.date_range(daily.index.min(), daily.index.max(), freq="D", tz="UTC")
    return daily.reindex(full_idx, fill_value=0.0)


def _daily_curve_stats(daily_bps: np.ndarray) -> dict[str, float]:
    if len(daily_bps) == 0:
        return {
            "annualized_bps_calendar": 0.0,
            "max_daily_dd_bps": 0.0,
            "worst_single_day_bps": 0.0,
            "single_day_loss_bps": 0.0,
            "sharpe_daily_bps": 0.0,
            "cagr_notional": 0.0,
        }

    curve = np.cumsum(daily_bps)
    peak = np.maximum.accumulate(curve)
    dd = curve - peak

    mean = float(np.mean(daily_bps))
    std = float(np.std(daily_bps, ddof=1)) if len(daily_bps) > 1 else 0.0
    sharpe = float(mean / std * np.sqrt(252.0)) if std > 1e-12 else 0.0

    total_return = float(np.sum(daily_bps)) / 10000.0
    days = max(int(len(daily_bps)), 1)
    if 1.0 + total_return <= 0.0:
        cagr = -1.0
    else:
        cagr = float((1.0 + total_return) ** (365.25 / days) - 1.0)

    worst_single_day = float(np.min(daily_bps)) if len(daily_bps) else 0.0

    return {
        "annualized_bps_calendar": float(mean * 365.25),
        "max_daily_dd_bps": float(np.min(dd)),
        "worst_single_day_bps": worst_single_day,
        "single_day_loss_bps": float(max(0.0, -worst_single_day)),
        "sharpe_daily_bps": sharpe,
        "cagr_notional": cagr,
    }


def _block_bootstrap_daily(df: pd.DataFrame, n_paths: int, block_days: int, seed: int) -> pd.DataFrame:
    daily = _daily_pnl_curve(df)
    if daily.empty:
        return pd.DataFrame()
    vals = daily.to_numpy(dtype=float)
    n = len(vals)
    b = max(1, int(block_days))
    starts = np.arange(max(1, n - b + 1))
    rng = np.random.default_rng(seed)

    rows = []
    for i in range(int(n_paths)):
        out = []
        while len(out) < n:
            s = int(starts[rng.integers(0, len(starts))])
            out.extend(vals[s : s + b].tolist())
        sim = np.asarray(out[:n], dtype=float)
        st = _daily_curve_stats(sim)
        st["path"] = int(i)
        rows.append(st)
    return pd.DataFrame(rows)


def _norm01(series: pd.Series) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce").astype(float)
    lo = float(s.min())
    hi = float(s.max())
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return pd.Series(np.full(len(s), 0.5, dtype=float), index=s.index)
    return (s - lo) / (hi - lo)


def _threshold_pairs(grid: list[float], enable_half_size: bool) -> list[tuple[float, float]]:
    if not enable_half_size:
        return [(float(t), float(t)) for t in grid]
    out: list[tuple[float, float]] = []
    for t1 in grid:
        for t2 in grid:
            if t2 >= t1:
                out.append((float(t1), float(t2)))
    return out


def _gate_short_by_probability(
    short_df: pd.DataFrame,
    proba_bad: pd.Series,
    t1: float,
    t2: float,
    enable_half_size: bool,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    s = short_df.copy()
    p = proba_bad.reindex(s.index).fillna(1.0).to_numpy(dtype=float)
    if enable_half_size:
        action = np.where(p <= t1, "keep_full", np.where(p <= t2, "keep_half", "skip"))
        mult = np.where(p <= t1, 1.0, np.where(p <= t2, 0.5, 0.0))
    else:
        action = np.where(p <= t1, "keep_full", "skip")
        mult = np.where(p <= t1, 1.0, 0.0)

    s["p_cluster_bad"] = p
    s["cluster_gate_action"] = action
    s["size_mult"] = mult.astype(float)

    kept = s[s["size_mult"] > 0.0].copy()
    kept["pnl_bps"] = kept["pnl_bps"].astype(float) * kept["size_mult"].astype(float)
    return kept, s


def _eval_variant(
    short_kept: pd.DataFrame,
    long_df: pd.DataFrame,
    risk_bps: float,
    pair_keep: set[str] | None,
) -> tuple[pd.DataFrame, dict[str, float]]:
    pre = pd.concat([short_kept, long_df], ignore_index=True).sort_values(["timestamp", "pair"]).reset_index(drop=True)
    guard = _apply_guardrail(pre)
    if pair_keep is not None and len(pair_keep):
        guard = guard[guard["pair"].astype(str).isin(pair_keep)].copy().reset_index(drop=True)
    metrics = _metrics_with_risk(guard, risk_bps=risk_bps)
    return guard, metrics


def _time_ordered_split(
    df: pd.DataFrame,
    labeled_mask: pd.Series,
    calibration_frac: float,
) -> tuple[pd.Series, pd.Series]:
    cal_frac = float(np.clip(calibration_frac, 0.0, 0.5))
    labeled_idx = df.index[labeled_mask].to_numpy()
    if len(labeled_idx) < 200:
        return labeled_mask.copy(), pd.Series(False, index=df.index)

    ordered = df.loc[labeled_idx].sort_values(["exit_ts", "timestamp"]).index.to_numpy()
    cut = int(round(len(ordered) * (1.0 - cal_frac)))
    cut = max(50, min(cut, len(ordered) - 50))
    train_idx = set(ordered[:cut].tolist())
    cal_idx = set(ordered[cut:].tolist())
    train_mask = df.index.to_series().isin(train_idx)
    cal_mask = df.index.to_series().isin(cal_idx)
    return train_mask, cal_mask


def _fit_calibrator(method: str, p_raw_cal: np.ndarray, y_cal: np.ndarray):
    m = str(method).lower()
    if len(y_cal) < 100 or len(np.unique(y_cal)) < 2:
        return lambda p: np.clip(p, 0.0, 1.0), {"effective_method": "none"}

    if m == "isotonic":
        iso = IsotonicRegression(out_of_bounds="clip")
        iso.fit(p_raw_cal, y_cal)
        return lambda p: np.clip(iso.predict(np.asarray(p, dtype=float)), 0.0, 1.0), {"effective_method": "isotonic"}

    if m in {"platt", "sigmoid"}:
        lr = LogisticRegression(solver="lbfgs", max_iter=200)
        lr.fit(p_raw_cal.reshape(-1, 1), y_cal.astype(int))
        return (
            lambda p: np.clip(lr.predict_proba(np.asarray(p, dtype=float).reshape(-1, 1))[:, 1], 0.0, 1.0),
            {"effective_method": "platt"},
        )

    return lambda p: np.clip(p, 0.0, 1.0), {"effective_method": "none"}


def _fit_model_with_optional_calibration(
    tr_short: pd.DataFrame,
    te_short: pd.DataFrame,
    X_all: pd.DataFrame,
    y_tr: pd.Series,
    enable_calibration: bool,
    calibration_method: str,
    calibration_frac: float,
    random_state: int,
) -> dict:
    tr_idx = tr_short.index
    te_idx = te_short.index
    X_tr = X_all.loc[tr_idx]
    X_te = X_all.loc[te_idx]

    train_labeled = y_tr.notna()
    if int(train_labeled.sum()) < 150:
        raise RuntimeError("Not enough labeled trades to fit model.")

    train_mask, cal_mask = _time_ordered_split(tr_short, train_labeled, calibration_frac=calibration_frac)
    if len(np.unique(y_tr.loc[train_mask].astype(int).to_numpy())) < 2:
        train_mask = train_labeled.copy()
        cal_mask = pd.Series(False, index=tr_short.index)

    model = HistGradientBoostingClassifier(
        max_depth=4,
        learning_rate=0.05,
        max_iter=350,
        min_samples_leaf=80,
        random_state=int(random_state),
    )
    model.fit(X_tr.loc[train_mask], y_tr.loc[train_mask].astype(int))

    p_raw_tr = model.predict_proba(X_tr)[:, 1].astype(float)
    p_raw_te = model.predict_proba(X_te)[:, 1].astype(float)
    p_cal_tr = p_raw_tr.copy()
    p_cal_te = p_raw_te.copy()

    calib_info = {
        "effective_method": "none",
        "n_train_model": int(train_mask.sum()),
        "n_train_cal": int(cal_mask.sum()),
        "brier_raw": np.nan,
        "brier_cal": np.nan,
        "logloss_raw": np.nan,
        "logloss_cal": np.nan,
    }
    if enable_calibration and calibration_method != "none" and int(cal_mask.sum()) >= 100:
        y_cal = y_tr.loc[cal_mask].astype(int).to_numpy()
        p_raw_cal = p_raw_tr[cal_mask.to_numpy()]
        calibrator, cmeta = _fit_calibrator(calibration_method, p_raw_cal=p_raw_cal, y_cal=y_cal)
        p_cal_tr = calibrator(p_raw_tr)
        p_cal_te = calibrator(p_raw_te)
        p_cal_cal = calibrator(p_raw_cal)

        calib_info.update(
            {
                "effective_method": cmeta.get("effective_method", "none"),
                "brier_raw": float(brier_score_loss(y_cal, np.clip(p_raw_cal, 1e-6, 1 - 1e-6))),
                "brier_cal": float(brier_score_loss(y_cal, np.clip(p_cal_cal, 1e-6, 1 - 1e-6))),
                "logloss_raw": float(log_loss(y_cal, np.clip(p_raw_cal, 1e-6, 1 - 1e-6))),
                "logloss_cal": float(log_loss(y_cal, np.clip(p_cal_cal, 1e-6, 1 - 1e-6))),
            }
        )

    return {
        "proba_raw_tr": pd.Series(np.clip(p_raw_tr, 0.0, 1.0), index=tr_short.index),
        "proba_raw_te": pd.Series(np.clip(p_raw_te, 0.0, 1.0), index=te_short.index),
        "proba_cal_tr": pd.Series(np.clip(p_cal_tr, 0.0, 1.0), index=tr_short.index),
        "proba_cal_te": pd.Series(np.clip(p_cal_te, 0.0, 1.0), index=te_short.index),
        "calib_info": calib_info,
    }


def _select_thresholds_ddfirst(
    train_short: pd.DataFrame,
    train_long: pd.DataFrame,
    proba_bad_train: pd.Series,
    threshold_grid: list[float],
    pair_keep_fixed: set[str],
    risk_bps: float,
    retain_annualized_frac: float,
    min_trade_frac: float,
    min_mean_bps: float,
    single_day_improvement_frac: float,
    enable_half_size: bool,
    train_mc_paths: int,
    train_mc_block_days: int,
    random_state: int,
) -> tuple[float, float, pd.DataFrame, dict[str, float]]:
    base_short = train_short.copy()
    base_short["cluster_gate_action"] = "keep_full"
    base_short["size_mult"] = 1.0
    base_guard, base_m = _eval_variant(base_short, train_long, risk_bps=risk_bps, pair_keep=pair_keep_fixed)

    base_mc = _block_bootstrap_daily(
        base_guard,
        n_paths=max(60, int(train_mc_paths)),
        block_days=max(1, int(train_mc_block_days)),
        seed=int(random_state),
    )
    base_mc_p95_single_day_loss = (
        float(np.percentile(base_mc["single_day_loss_bps"].to_numpy(dtype=float), 95)) if not base_mc.empty else np.inf
    )

    rows = []
    for t1, t2 in _threshold_pairs(threshold_grid, enable_half_size=enable_half_size):
        kept, _ = _gate_short_by_probability(
            train_short,
            proba_bad_train,
            t1=t1,
            t2=t2,
            enable_half_size=enable_half_size,
        )
        guard, m = _eval_variant(kept, train_long, risk_bps=risk_bps, pair_keep=pair_keep_fixed)
        mc = _block_bootstrap_daily(
            guard,
            n_paths=max(60, int(train_mc_paths)),
            block_days=max(1, int(train_mc_block_days)),
            seed=int(random_state + round(1000 * (t1 + t2))),
        )
        cand_mc_p95_single_day_loss = (
            float(np.percentile(mc["single_day_loss_bps"].to_numpy(dtype=float), 95)) if not mc.empty else np.inf
        )

        target_worst_day = float(base_m["worst_single_day_bps"]) * (1.0 - float(single_day_improvement_frac))
        dd_pass = float(m["worst_single_day_bps"]) >= target_worst_day
        mc_pass = cand_mc_p95_single_day_loss <= base_mc_p95_single_day_loss
        ann_pass = float(m["annualized_bps_calendar"]) >= (float(retain_annualized_frac) * float(base_m["annualized_bps_calendar"]))
        mean_pass = float(m["mean_pnl_per_trade_bps"]) >= float(min_mean_bps)
        trade_pass = float(m["trades"]) >= (float(min_trade_frac) * float(base_m["trades"]))
        hard_pass = bool(dd_pass and mc_pass and ann_pass and mean_pass and trade_pass)

        eligible = bool(ann_pass and mean_pass and trade_pass)
        rows.append(
            {
                "t1": float(t1),
                "t2": float(t2),
                "trades": int(m["trades"]),
                "mean_pnl_per_trade_bps": float(m["mean_pnl_per_trade_bps"]),
                "sharpe": float(m["sharpe"]),
                "annualized_bps_calendar": float(m["annualized_bps_calendar"]),
                "worst_single_day_bps": float(m["worst_single_day_bps"]),
                "max_daily_dd_bps": float(m["max_daily_dd_bps"]),
                "mc_p95_single_day_loss_bps": float(cand_mc_p95_single_day_loss),
                "base_mc_p95_single_day_loss_bps": float(base_mc_p95_single_day_loss),
                "dd_pass": bool(dd_pass),
                "mc_pass": bool(mc_pass),
                "ann_pass": bool(ann_pass),
                "mean_pass": bool(mean_pass),
                "trade_pass": bool(trade_pass),
                "hard_pass": bool(hard_pass),
                "eligible": bool(eligible),
            }
        )

    grid = pd.DataFrame(rows)
    grid["score"] = (
        0.50 * _norm01(grid["worst_single_day_bps"])
        + 0.25 * _norm01(grid["sharpe"])
        + 0.25 * _norm01(grid["annualized_bps_calendar"])
    )

    hard = grid[grid["hard_pass"]].copy()
    if not hard.empty:
        cand = hard
        fallback_reason = ""
    else:
        cand = grid[grid["eligible"]].copy()
        if cand.empty:
            cand = grid.copy()
        fallback_reason = "hard_dd_unmet"

    chosen = cand.sort_values(
        ["score", "worst_single_day_bps", "sharpe", "annualized_bps_calendar"],
        ascending=[False, False, False, False],
    ).iloc[0]

    meta = {
        "fallback_reason": fallback_reason,
        "base_trades": int(base_m["trades"]),
        "base_mean_pnl_per_trade_bps": float(base_m["mean_pnl_per_trade_bps"]),
        "base_annualized_bps_calendar": float(base_m["annualized_bps_calendar"]),
        "base_worst_single_day_bps": float(base_m["worst_single_day_bps"]),
        "base_max_daily_dd_bps": float(base_m["max_daily_dd_bps"]),
        "base_mc_p95_single_day_loss_bps": float(base_mc_p95_single_day_loss),
    }
    return float(chosen["t1"]), float(chosen["t2"]), grid, meta


def main() -> None:
    p = argparse.ArgumentParser(description="Causal early-warning cluster detector (WFO)")
    p.add_argument("--exclude-oil", action="store_true", default=True)
    p.add_argument("--mixes", default="m5=MOM,m15=MOM+REV,m60=REV")
    p.add_argument("--start-test-year", type=int, default=2020)
    p.add_argument("--end-test-year", type=int, default=2025)
    p.add_argument("--embargo-days", type=int, default=5)
    p.add_argument("--pair-sharpe-cutoff", type=float, default=0.30)

    p.add_argument("--cluster-trade-horizon", type=int, default=10)
    p.add_argument("--cluster-trade-loss-bps", type=float, default=-250.0)
    p.add_argument("--cluster-day-horizon", type=int, default=5)
    p.add_argument("--cluster-day-loss-bps", type=float, default=-400.0)

    p.add_argument("--enable-calibration", action="store_true", default=True)
    p.add_argument("--calibration-method", default="isotonic", choices=["isotonic", "platt", "none"])
    p.add_argument("--calibration-frac", type=float, default=0.20)

    p.add_argument("--threshold-grid", default="0.35,0.40,0.45,0.50,0.55,0.60,0.65")
    p.add_argument("--enable-half-size", action="store_true", default=True)

    p.add_argument("--retain-annualized-frac", type=float, default=0.70)
    p.add_argument("--min-trade-frac", type=float, default=0.50)
    p.add_argument("--min-mean-bps", type=float, default=5.0)
    p.add_argument("--single-day-improvement-frac", type=float, default=0.20)

    p.add_argument("--train-mc-paths", type=int, default=150)
    p.add_argument("--train-mc-block-days", type=int, default=20)
    p.add_argument("--mc-paths", type=int, default=1000)
    p.add_argument("--mc-block-days", type=int, default=20)

    p.add_argument("--random-state", type=int, default=42)
    p.add_argument("--out-prefix", default="cluster_ew")
    args = p.parse_args()

    pair_whitelist = list(PAIR_WHITELIST_BASE)
    if args.exclude_oil:
        pair_whitelist = [x for x in pair_whitelist if x not in OIL_LINKED_PAIRS]

    mixes = _parse_strategy_mixes(args.mixes)
    threshold_grid = _parse_grid(args.threshold_grid)
    folds = _make_folds(args.start_test_year, args.end_test_year, args.embargo_days)

    fold_rows: list[dict] = []
    threshold_rows: list[pd.DataFrame] = []
    scored_rows: list[pd.DataFrame] = []
    label_rows: list[dict] = []
    calibration_rows: list[dict] = []

    oos_base_trades: list[pd.DataFrame] = []
    oos_candidate_trades: list[pd.DataFrame] = []
    oos_promoted_trades: list[pd.DataFrame] = []

    for mix in mixes:
        mix_name = _mix_id(mix)
        print(f"\n=== Mix: {mix_name} ===")

        loaded = {}
        for tf in ["m5", "m15", "m60"]:
            specs = [x.strip().upper() for x in str(mix[tf]).split("+") if x.strip()]
            tf_frames = []
            for strat in specs:
                if strat == "NONE":
                    continue
                path, pair_col = EVENT_PATHS[(tf, strat)]
                tf_frames.append(_load_events(path, strat, tf, pair_col, pair_whitelist))
            loaded[tf] = pd.concat(tf_frames, ignore_index=True) if tf_frames else _empty_events_frame()

        short_all = pd.concat([loaded["m5"], loaded["m15"]], ignore_index=True).reset_index(drop=True)
        long_all = loaded["m60"].reset_index(drop=True)
        has_long_leg = str(mix["m60"]).upper() != "NONE"
        if short_all.empty or (has_long_leg and long_all.empty):
            print("  skip mix: empty short dataset or empty required long dataset")
            continue

        short_all["trade_id"] = np.arange(len(short_all), dtype=np.int64)
        short_all["mix_id"] = mix_name
        long_all["trade_id"] = -1
        long_all["mix_id"] = mix_name

        short_all = add_cluster_state_features(short_all)
        X_all = _feature_matrix(short_all)
        risk_bps = _derive_risk_bps(pd.concat([short_all, long_all], ignore_index=True), fallback=100.0)
        print(f"  loaded short={len(short_all)} long={len(long_all)} risk_bps={risk_bps:.2f}")

        for fold in folds:
            print(f"\n  Fold {fold.test_year}:")
            tr_short = short_all[short_all["exit_ts"] < fold.train_end_ts_ns].copy()
            te_short = short_all[
                (short_all["exit_ts"] >= fold.test_start_ts_ns) & (short_all["exit_ts"] < fold.test_end_ts_ns)
            ].copy()
            tr_long = long_all[long_all["exit_ts"] < fold.train_end_ts_ns].copy()
            te_long = long_all[
                (long_all["exit_ts"] >= fold.test_start_ts_ns) & (long_all["exit_ts"] < fold.test_end_ts_ns)
            ].copy()

            if len(tr_short) < 2500 or te_short.empty:
                print("    skip: insufficient train/test short trades")
                continue

            train_base_short = tr_short.copy()
            train_base_short["cluster_gate_action"] = "keep_full"
            train_base_short["size_mult"] = 1.0
            train_base_guard, _ = _eval_variant(train_base_short, tr_long, risk_bps=risk_bps, pair_keep=None)
            pair_keep = _pair_filter_set(train_base_guard, cutoff=float(args.pair_sharpe_cutoff))

            y_trade_tr = build_cluster_trade_labels(
                tr_short,
                horizon_trades=int(args.cluster_trade_horizon),
                loss_bps=float(args.cluster_trade_loss_bps),
            )
            y_day_tr = build_cluster_day_labels(
                tr_short,
                horizon_days=int(args.cluster_day_horizon),
                loss_bps=float(args.cluster_day_loss_bps),
            )
            y_trade_te = build_cluster_trade_labels(
                te_short,
                horizon_trades=int(args.cluster_trade_horizon),
                loss_bps=float(args.cluster_trade_loss_bps),
            )
            y_day_te = build_cluster_day_labels(
                te_short,
                horizon_days=int(args.cluster_day_horizon),
                loss_bps=float(args.cluster_day_loss_bps),
            )

            tr_stats = label_distribution(y_trade_tr)
            te_stats = label_distribution(y_trade_te)
            if int(tr_stats["n_labeled"]) < 1200:
                print("    skip: too few labeled train rows")
                continue
            tr_unique = set(pd.Series(y_trade_tr.dropna().astype(int)).unique().tolist())
            if tr_unique != {0, 1}:
                print("    skip: training labels missing a class")
                continue

            fit = _fit_model_with_optional_calibration(
                tr_short=tr_short,
                te_short=te_short,
                X_all=X_all,
                y_tr=y_trade_tr,
                enable_calibration=bool(args.enable_calibration),
                calibration_method=args.calibration_method,
                calibration_frac=float(args.calibration_frac),
                random_state=int(args.random_state + fold.test_year),
            )

            t1, t2, grid, chosen_meta = _select_thresholds_ddfirst(
                train_short=tr_short,
                train_long=tr_long,
                proba_bad_train=fit["proba_cal_tr"],
                threshold_grid=threshold_grid,
                pair_keep_fixed=pair_keep,
                risk_bps=risk_bps,
                retain_annualized_frac=float(args.retain_annualized_frac),
                min_trade_frac=float(args.min_trade_frac),
                min_mean_bps=float(args.min_mean_bps),
                single_day_improvement_frac=float(args.single_day_improvement_frac),
                enable_half_size=bool(args.enable_half_size),
                train_mc_paths=int(args.train_mc_paths),
                train_mc_block_days=int(args.train_mc_block_days),
                random_state=int(args.random_state + fold.test_year),
            )

            gdf = grid.copy()
            gdf["mix_id"] = mix_name
            gdf["fold_year"] = int(fold.test_year)
            threshold_rows.append(gdf)

            base_short_te = te_short.copy()
            base_short_te["cluster_gate_action"] = "keep_full"
            base_short_te["size_mult"] = 1.0
            base_guard, m_base = _eval_variant(base_short_te, te_long, risk_bps=risk_bps, pair_keep=pair_keep)

            cand_short_te, cand_scored_te = _gate_short_by_probability(
                te_short,
                fit["proba_cal_te"],
                t1=t1,
                t2=t2,
                enable_half_size=bool(args.enable_half_size),
            )
            cand_guard, m_cand = _eval_variant(cand_short_te, te_long, risk_bps=risk_bps, pair_keep=pair_keep)
            promoted_guard = cand_guard.copy()
            m_prom = _metrics_with_risk(promoted_guard, risk_bps=risk_bps)

            mc_base = _block_bootstrap_daily(
                base_guard,
                n_paths=max(60, int(args.train_mc_paths)),
                block_days=max(1, int(args.train_mc_block_days)),
                seed=int(args.random_state + 101 + fold.test_year),
            )
            mc_cand = _block_bootstrap_daily(
                cand_guard,
                n_paths=max(60, int(args.train_mc_paths)),
                block_days=max(1, int(args.train_mc_block_days)),
                seed=int(args.random_state + 201 + fold.test_year),
            )
            base_mc_p95_single_day_loss = (
                float(np.percentile(mc_base["single_day_loss_bps"].to_numpy(dtype=float), 95)) if not mc_base.empty else np.inf
            )
            cand_mc_p95_single_day_loss = (
                float(np.percentile(mc_cand["single_day_loss_bps"].to_numpy(dtype=float), 95)) if not mc_cand.empty else np.inf
            )

            target_worst_day = float(m_base["worst_single_day_bps"]) * (1.0 - float(args.single_day_improvement_frac))
            oos_dd_pass = float(m_cand["worst_single_day_bps"]) >= target_worst_day
            oos_mc_pass = cand_mc_p95_single_day_loss <= base_mc_p95_single_day_loss
            oos_ann_pass = float(m_cand["annualized_bps_calendar"]) >= (
                float(args.retain_annualized_frac) * float(m_base["annualized_bps_calendar"])
            )
            oos_mean_pass = float(m_cand["mean_pnl_per_trade_bps"]) >= float(args.min_mean_bps)
            oos_trade_pass = float(m_cand["trades"]) >= (float(args.min_trade_frac) * float(m_base["trades"]))
            oos_hard_pass = bool(oos_dd_pass and oos_mc_pass and oos_ann_pass and oos_mean_pass and oos_trade_pass)

            high_risk_flag = cand_scored_te["cluster_gate_action"].astype(str).isin(["skip", "keep_half"])
            y_eval = y_trade_te.reindex(cand_scored_te.index)
            eval_mask = y_eval.notna()
            pos_mask = (y_eval == 1) & eval_mask
            pred_mask = high_risk_flag & eval_mask
            precision = float((pos_mask & pred_mask).sum() / max(int(pred_mask.sum()), 1)) if int(pred_mask.sum()) else 0.0
            recall = float((pos_mask & pred_mask).sum() / max(int(pos_mask.sum()), 1)) if int(pos_mask.sum()) else 0.0

            fold_rows.append(
                {
                    "mix_id": mix_name,
                    "year": int(fold.test_year),
                    "t1": float(t1),
                    "t2": float(t2),
                    "threshold_policy": "train_only",
                    "selection_objective": "dd_first_single_day",
                    "fallback_reason": str(chosen_meta.get("fallback_reason", "")),
                    "train_label_rate_bad": float(tr_stats["label_rate_1"]),
                    "test_label_rate_bad": float(te_stats["label_rate_1"]),
                    "cluster_precision": float(precision),
                    "cluster_recall": float(recall),
                    "base_trades": int(m_base["trades"]),
                    "base_mean_pnl_per_trade_bps": float(m_base["mean_pnl_per_trade_bps"]),
                    "base_sharpe": float(m_base["sharpe"]),
                    "base_annualized_bps_calendar": float(m_base["annualized_bps_calendar"]),
                    "base_worst_single_day_bps": float(m_base["worst_single_day_bps"]),
                    "base_max_daily_dd_bps": float(m_base["max_daily_dd_bps"]),
                    "candidate_trades": int(m_cand["trades"]),
                    "candidate_mean_pnl_per_trade_bps": float(m_cand["mean_pnl_per_trade_bps"]),
                    "candidate_sharpe": float(m_cand["sharpe"]),
                    "candidate_annualized_bps_calendar": float(m_cand["annualized_bps_calendar"]),
                    "candidate_worst_single_day_bps": float(m_cand["worst_single_day_bps"]),
                    "candidate_max_daily_dd_bps": float(m_cand["max_daily_dd_bps"]),
                    "delta_worst_single_day_bps": float(m_cand["worst_single_day_bps"] - m_base["worst_single_day_bps"]),
                    "delta_max_daily_dd_bps": float(m_cand["max_daily_dd_bps"] - m_base["max_daily_dd_bps"]),
                    "delta_sharpe": float(m_cand["sharpe"] - m_base["sharpe"]),
                    "delta_annualized_bps_calendar": float(m_cand["annualized_bps_calendar"] - m_base["annualized_bps_calendar"]),
                    "mc_base_p95_single_day_loss_bps": float(base_mc_p95_single_day_loss),
                    "mc_candidate_p95_single_day_loss_bps": float(cand_mc_p95_single_day_loss),
                    "oos_dd_pass": bool(oos_dd_pass),
                    "oos_mc_pass": bool(oos_mc_pass),
                    "oos_ann_pass": bool(oos_ann_pass),
                    "oos_mean_pass": bool(oos_mean_pass),
                    "oos_trade_pass": bool(oos_trade_pass),
                    "oos_hard_pass": bool(oos_hard_pass),
                }
            )

            label_rows.append(
                {
                    "mix_id": mix_name,
                    "year": int(fold.test_year),
                    "label_type": "trade",
                    "train_n_total": int(tr_stats["n_total"]),
                    "train_n_labeled": int(tr_stats["n_labeled"]),
                    "train_rate_bad": float(tr_stats["label_rate_1"]),
                    "test_n_total": int(te_stats["n_total"]),
                    "test_n_labeled": int(te_stats["n_labeled"]),
                    "test_rate_bad": float(te_stats["label_rate_1"]),
                    "horizon": int(args.cluster_trade_horizon),
                    "loss_bps": float(args.cluster_trade_loss_bps),
                }
            )

            tr_day_stats = label_distribution(y_day_tr)
            te_day_stats = label_distribution(y_day_te)
            label_rows.append(
                {
                    "mix_id": mix_name,
                    "year": int(fold.test_year),
                    "label_type": "day",
                    "train_n_total": int(tr_day_stats["n_total"]),
                    "train_n_labeled": int(tr_day_stats["n_labeled"]),
                    "train_rate_bad": float(tr_day_stats["label_rate_1"]),
                    "test_n_total": int(te_day_stats["n_total"]),
                    "test_n_labeled": int(te_day_stats["n_labeled"]),
                    "test_rate_bad": float(te_day_stats["label_rate_1"]),
                    "horizon": int(args.cluster_day_horizon),
                    "loss_bps": float(args.cluster_day_loss_bps),
                }
            )

            calibration_rows.append(
                {
                    "mix_id": mix_name,
                    "year": int(fold.test_year),
                    "t1": float(t1),
                    "t2": float(t2),
                    "calibration_method": str(fit["calib_info"]["effective_method"]),
                    "n_train_model": int(fit["calib_info"]["n_train_model"]),
                    "n_train_cal": int(fit["calib_info"]["n_train_cal"]),
                    "brier_raw": fit["calib_info"]["brier_raw"],
                    "brier_cal": fit["calib_info"]["brier_cal"],
                    "logloss_raw": fit["calib_info"]["logloss_raw"],
                    "logloss_cal": fit["calib_info"]["logloss_cal"],
                }
            )

            common_cols = {
                "mix_id": mix_name,
                "fold_year": int(fold.test_year),
                "selection_objective": "dd_first_single_day",
                "threshold_policy": "train_only",
                "t1": float(t1),
                "t2": float(t2),
                "oos_hard_pass": bool(oos_hard_pass),
            }

            bdf = base_guard.copy()
            for k, v in common_cols.items():
                bdf[k] = v
            bdf["variant"] = "baseline_causal"
            bdf["promoted_source"] = "baseline"
            oos_base_trades.append(bdf)

            cdf = cand_guard.copy()
            for k, v in common_cols.items():
                cdf[k] = v
            cdf["variant"] = "cluster_ew_candidate"
            cdf["promoted_source"] = "candidate"
            oos_candidate_trades.append(cdf)

            pdf = promoted_guard.copy()
            for k, v in common_cols.items():
                pdf[k] = v
            pdf["variant"] = "cluster_ew_promoted"
            pdf["promoted_source"] = "candidate"
            oos_promoted_trades.append(pdf)

            sdf = cand_scored_te[
                ["trade_id", "pair", "timeframe", "strategy_type", "timestamp", "exit_ts", "pnl_bps", "cluster_gate_action", "size_mult", "p_cluster_bad"]
            ].copy()
            sdf["mix_id"] = mix_name
            sdf["fold_year"] = int(fold.test_year)
            sdf["t1"] = float(t1)
            sdf["t2"] = float(t2)
            sdf["proba_bad_raw"] = fit["proba_raw_te"].reindex(cand_scored_te.index).to_numpy(dtype=float)
            sdf["proba_bad_calibrated"] = fit["proba_cal_te"].reindex(cand_scored_te.index).to_numpy(dtype=float)
            sdf["cluster_trade_label"] = y_trade_te.reindex(cand_scored_te.index).astype("Int64")
            sdf["cluster_day_label"] = y_day_te.reindex(cand_scored_te.index).astype("Int64")
            scored_rows.append(sdf)

            print(
                f"    t1={t1:.2f} t2={t2:.2f} "
                f"| base_worst_day={m_base['worst_single_day_bps']:.1f} "
                f"| cand_worst_day={m_cand['worst_single_day_bps']:.1f} "
                f"| oos_hard_pass={oos_hard_pass}"
            )

    if not fold_rows:
        raise RuntimeError("No valid folds produced.")

    folds_df = pd.DataFrame(fold_rows).sort_values(["mix_id", "year"]).reset_index(drop=True)
    grid_df = pd.concat(threshold_rows, ignore_index=True) if threshold_rows else pd.DataFrame()
    scored_df = pd.concat(scored_rows, ignore_index=True) if scored_rows else pd.DataFrame()
    labels_df = pd.DataFrame(label_rows).sort_values(["mix_id", "year", "label_type"]).reset_index(drop=True)
    calib_df = pd.DataFrame(calibration_rows).sort_values(["mix_id", "year"]).reset_index(drop=True)

    oos_base = pd.concat(oos_base_trades, ignore_index=True) if oos_base_trades else pd.DataFrame()
    oos_candidate = pd.concat(oos_candidate_trades, ignore_index=True) if oos_candidate_trades else pd.DataFrame()
    oos_promoted = pd.concat(oos_promoted_trades, ignore_index=True) if oos_promoted_trades else pd.DataFrame()

    summary_rows = []
    mix_ids = sorted(folds_df["mix_id"].astype(str).unique().tolist())
    for mix_name in mix_ids:
        for label, sub in [
            ("baseline_causal", oos_base[oos_base["mix_id"] == mix_name].copy()),
            ("cluster_ew_candidate", oos_candidate[oos_candidate["mix_id"] == mix_name].copy()),
            ("cluster_ew_promoted", oos_promoted[oos_promoted["mix_id"] == mix_name].copy()),
        ]:
            if sub.empty:
                continue
            r = _derive_risk_bps(sub, fallback=100.0)
            m = _metrics_with_risk(sub, risk_bps=r)
            summary_rows.append(
                {
                    "mix_id": mix_name,
                    "variant": label,
                    "selection_objective": "dd_first_single_day",
                    "threshold_policy": "train_only",
                    "oos_hard_pass_rate": float(sub["oos_hard_pass"].mean()) if "oos_hard_pass" in sub.columns else np.nan,
                    **m,
                }
            )

        s = pd.DataFrame([x for x in summary_rows if x["mix_id"] == mix_name])
        if {"baseline_causal", "cluster_ew_promoted"}.issubset(set(s["variant"].tolist())):
            b = s.loc[s["variant"] == "baseline_causal"].iloc[0]
            pmt = s.loc[s["variant"] == "cluster_ew_promoted"].iloc[0]
            summary_rows.append(
                {
                    "mix_id": mix_name,
                    "variant": "cluster_ew_promoted_minus_baseline",
                    "selection_objective": "dd_first_single_day",
                    "threshold_policy": "train_only",
                    "oos_hard_pass_rate": float(pmt["oos_hard_pass_rate"]),
                    "trades": int(pmt["trades"] - b["trades"]),
                    "mean_pnl_per_trade_bps": float(pmt["mean_pnl_per_trade_bps"] - b["mean_pnl_per_trade_bps"]),
                    "sharpe": float(pmt["sharpe"] - b["sharpe"]),
                    "annualized_bps_calendar": float(pmt["annualized_bps_calendar"] - b["annualized_bps_calendar"]),
                    "worst_single_day_bps": float(pmt["worst_single_day_bps"] - b["worst_single_day_bps"]),
                    "max_daily_dd_bps": float(pmt["max_daily_dd_bps"] - b["max_daily_dd_bps"]),
                    "cagr": float(pmt["cagr"] - b["cagr"]),
                }
            )

    summary_df = pd.DataFrame(summary_rows).sort_values(["mix_id", "variant"]).reset_index(drop=True)

    out_dir = ROOT / "data" / "analysis"
    out_dir.mkdir(parents=True, exist_ok=True)
    folds_path = out_dir / f"{args.out_prefix}_folds.csv"
    grid_path = out_dir / f"{args.out_prefix}_threshold_grid.csv"
    summary_path = out_dir / f"{args.out_prefix}_summary.csv"
    trades_path = out_dir / f"{args.out_prefix}_oos_trades.csv"
    scored_path = out_dir / f"{args.out_prefix}_oos_scored_trades.csv"
    labels_path = out_dir / f"{args.out_prefix}_label_stats.csv"
    calib_path = out_dir / f"{args.out_prefix}_fold_calibration.csv"
    mc_paths_path = out_dir / f"{args.out_prefix}_mc_daily_paths.csv"
    mc_summary_path = out_dir / f"{args.out_prefix}_mc_daily_summary.csv"

    folds_df.to_csv(folds_path, index=False)
    grid_df.to_csv(grid_path, index=False)
    summary_df.to_csv(summary_path, index=False)
    pd.concat([oos_base, oos_candidate, oos_promoted], ignore_index=True).to_csv(trades_path, index=False)
    scored_df.to_csv(scored_path, index=False)
    labels_df.to_csv(labels_path, index=False)
    calib_df.to_csv(calib_path, index=False)

    mc_rows = []
    for mix_name in mix_ids:
        for variant, vdf in [
            ("baseline_causal", oos_base[oos_base["mix_id"] == mix_name].copy()),
            ("cluster_ew_promoted", oos_promoted[oos_promoted["mix_id"] == mix_name].copy()),
        ]:
            if vdf.empty:
                continue
            mc = _block_bootstrap_daily(
                vdf,
                n_paths=int(args.mc_paths),
                block_days=int(args.mc_block_days),
                seed=int(args.random_state + (17 if variant == "cluster_ew_promoted" else 0)),
            )
            if mc.empty:
                continue
            mc["variant"] = variant
            mc["mix_id"] = mix_name
            mc_rows.append(mc)

    mc_all = pd.concat(mc_rows, ignore_index=True) if mc_rows else pd.DataFrame()
    if not mc_all.empty:
        q = [1, 5, 10, 50, 90, 95, 99]
        sm_rows = []
        for (mix_name, variant), sub in mc_all.groupby(["mix_id", "variant"], sort=True):
            row = {"mix_id": mix_name, "variant": variant, "n_paths": int(len(sub))}
            for col in [
                "annualized_bps_calendar",
                "max_daily_dd_bps",
                "worst_single_day_bps",
                "single_day_loss_bps",
                "sharpe_daily_bps",
                "cagr_notional",
            ]:
                vals = np.percentile(sub[col].to_numpy(dtype=float), q)
                for qi, v in zip(q, vals):
                    row[f"{col}_p{qi}"] = float(v)
            sm_rows.append(row)
        mc_summary = pd.DataFrame(sm_rows).sort_values(["mix_id", "variant"]).reset_index(drop=True)
        mc_all.to_csv(mc_paths_path, index=False)
        mc_summary.to_csv(mc_summary_path, index=False)
    else:
        mc_summary = pd.DataFrame()

    print("\n=== OOS Summary ===")
    print(summary_df.to_string(index=False))
    print("\n=== Fold Summary ===")
    print(folds_df.to_string(index=False))
    if not mc_summary.empty:
        print("\n=== Block Bootstrap MC (Daily Curve) ===")
        print(mc_summary.to_string(index=False))
    print("\nSaved:")
    print(f"- {folds_path}")
    print(f"- {grid_path}")
    print(f"- {summary_path}")
    print(f"- {trades_path}")
    print(f"- {scored_path}")
    print(f"- {labels_path}")
    print(f"- {calib_path}")
    if not mc_summary.empty:
        print(f"- {mc_paths_path}")
        print(f"- {mc_summary_path}")


if __name__ == "__main__":
    main()
