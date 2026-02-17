#!/usr/bin/env python3
"""
Causal walk-forward directional meta-model over robust-KF acceleration regimes.

Design:
- Actionable regimes are per-timeframe train-quantile thresholds on |kf_z_accel|.
- Direction labels are 1-bar forward triple-barrier style classes on raw 1-bar move:
  +1 (up hit), -1 (down hit), 0 (neutral).
- Model predicts directional probabilities on actionable rows for m15/m60.
- Policy can override baseline direction when confidence and EV are high.
- Promotion is strict: candidate must clear hard OOS gates, else baseline passthrough.
"""

from __future__ import annotations

import argparse
import itertools
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pipelines.build_events_h1 import (
    PAIRS as M60_PAIRS,
    compute_kalman_states as compute_kalman_states_m60,
    compute_z_scores as compute_z_scores_m60,
    load_pair_data as load_pair_data_m60,
)
from scripts.lib.robust_kf_features import compute_robust_kf_series_features
from scripts.report_strategy_fx_comm_multi_tf import (
    OIL_LINKED_PAIRS,
    PAIR_WHITELIST_BASE,
    _apply_guardrail,
    _derive_risk_bps,
    _filter_pairs_by_sharpe,
    _metrics_with_risk,
    _normalize_ts_ns,
)
from scripts.sweep_exit_params_short_tf import _build_pair_states

EVENT_PATHS = {
    ("m5", "MOM"): ("data/events/events_m5_8yr_v3_mom.csv", "pair"),
    ("m5", "REV"): ("data/events/events_m5_8yr_v3_rev.csv", "pair"),
    ("m15", "MOM"): ("data/events/events_m15_8yr_v3_mom.csv", "pair"),
    ("m15", "REV"): ("data/events/events_m15_8yr_v3_rev.csv", "pair"),
    ("m60", "MOM"): ("data/events/events_h1_8yr_v3_mom.csv", "symbol"),
    ("m60", "REV"): ("data/events/events_h1_8yr_v3_rev.csv", "symbol"),
}

BASELINE_VARIANT = "baseline"
BASELINE_POLICY = "adaptive_entry_z"


@dataclass(frozen=True)
class FoldWindow:
    test_year: int
    train_end_ts_ns: int
    test_start_ts_ns: int
    test_end_ts_ns: int


def _year_bounds_ns(year: int) -> tuple[int, int]:
    start = pd.Timestamp(year=year, month=1, day=1, tz="UTC")
    end = pd.Timestamp(year=year + 1, month=1, day=1, tz="UTC")
    return int(start.value), int(end.value)


def _make_folds(start_year: int, end_year: int, embargo_days: int) -> list[FoldWindow]:
    out: list[FoldWindow] = []
    embargo_ns = int(pd.Timedelta(days=embargo_days).value)
    for year in range(start_year, end_year + 1):
        test_start, test_end = _year_bounds_ns(year)
        out.append(
            FoldWindow(
                test_year=int(year),
                train_end_ts_ns=int(test_start - embargo_ns),
                test_start_ts_ns=int(test_start),
                test_end_ts_ns=int(test_end),
            )
        )
    return out


def _parse_grid(s: str, cast=float) -> list:
    vals = [cast(x.strip()) for x in str(s).split(",") if x.strip()]
    if not vals:
        raise ValueError("Grid cannot be empty")
    return list(sorted(set(vals)))


def _parse_bool(v: str | bool) -> bool:
    if isinstance(v, bool):
        return v
    t = str(v).strip().lower()
    if t in {"1", "true", "t", "yes", "y"}:
        return True
    if t in {"0", "false", "f", "no", "n"}:
        return False
    raise ValueError(f"Invalid bool token: {v}")


def _normalize_strategy_spec(raw_spec: str) -> str:
    tokens = [t.strip().upper() for t in str(raw_spec).split("+") if t.strip()]
    if not tokens:
        raise ValueError(f"Empty strategy spec: {raw_spec}")
    if "NONE" in tokens:
        if len(tokens) != 1:
            raise ValueError(f"NONE cannot be combined with others: {raw_spec}")
        return "NONE"
    for tok in tokens:
        if tok not in {"MOM", "REV"}:
            raise ValueError(f"Unsupported strategy token: {tok}")
    ordered = [tok for tok in ["MOM", "REV"] if tok in set(tokens)]
    return "+".join(ordered)


def _parse_strategy_mixes(s: str) -> list[dict[str, str]]:
    raw = str(s).strip()
    if raw.lower() in {"all", "*"}:
        out: list[dict[str, str]] = []
        for m5, m15, m60 in itertools.product(["MOM", "REV"], repeat=3):
            out.append({"m5": m5, "m15": m15, "m60": m60})
        return out

    out: list[dict[str, str]] = []
    for part in [x.strip() for x in raw.split(";") if x.strip()]:
        mix: dict[str, str] = {}
        for tok in [x.strip() for x in part.split(",") if x.strip()]:
            if "=" not in tok:
                raise ValueError(f"Invalid mix token: {tok}")
            tf, strat = tok.split("=", 1)
            tf = tf.strip().lower()
            strat = _normalize_strategy_spec(strat)
            if tf not in {"m5", "m15", "m60"}:
                raise ValueError(f"Unsupported timeframe in mix token: {tf}")
            mix[tf] = strat
        if set(mix.keys()) != {"m5", "m15", "m60"}:
            raise ValueError(f"Mix must set m5,m15,m60 exactly: {part}")
        if mix["m15"] == "NONE":
            raise ValueError("m15 cannot be NONE")
        out.append(mix)
    if not out:
        out.append({"m5": "MOM", "m15": "MOM+REV", "m60": "REV"})
    return out


def _mix_id(mix: dict[str, str]) -> str:
    def _norm(spec: str) -> str:
        return "".join(x.strip().lower() for x in str(spec).split("+") if x.strip())

    return f"m5_{_norm(mix['m5'])}__m15_{_norm(mix['m15'])}__m60_{_norm(mix['m60'])}"


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


def _load_events(path: str, strategy: str, timeframe: str, pair_col: str, pair_whitelist: list[str]) -> pd.DataFrame:
    df = pd.read_csv(path)
    if pair_col != "pair":
        df = df.rename(columns={pair_col: "pair"})

    if "strategy_type" in df.columns:
        df = df[df["strategy_type"].astype(str).str.upper() == strategy].copy()
    if "entry_exit_variant" in df.columns:
        df = df[df["entry_exit_variant"].astype(str) == BASELINE_VARIANT].copy()
    if "exit_policy" in df.columns:
        df = df[df["exit_policy"].astype(str) == BASELINE_POLICY].copy()

    df = df[df["pair"].isin(pair_whitelist)].copy()
    if df.empty:
        return _empty_events_frame()

    df["timestamp"] = _normalize_ts_ns(df["timestamp"])
    if "exit_ts" in df.columns:
        df["exit_ts"] = _normalize_ts_ns(df["exit_ts"])
    else:
        bar_minutes = {"m5": 5, "m15": 15, "m60": 60}[timeframe]
        dur_col = "duration_bars" if "duration_bars" in df.columns else "duration"
        d = pd.to_numeric(df[dur_col], errors="coerce").fillna(0).astype(int).clip(lower=0)
        bar_ns = int(pd.Timedelta(minutes=bar_minutes).value)
        df["exit_ts"] = df["timestamp"] + d * bar_ns

    if "duration_bars" not in df.columns:
        if "duration" in df.columns:
            df["duration_bars"] = pd.to_numeric(df["duration"], errors="coerce")
        else:
            df["duration_bars"] = np.nan

    if "max_hold_bars" not in df.columns:
        df["max_hold_bars"] = np.nan

    if "z_score" not in df.columns and "entry_z" in df.columns:
        df["z_score"] = pd.to_numeric(df["entry_z"], errors="coerce")
    else:
        df["z_score"] = pd.to_numeric(df.get("z_score", np.nan), errors="coerce")

    if "side" not in df.columns:
        if "direction" in df.columns:
            d = pd.to_numeric(df["direction"], errors="coerce").fillna(0.0)
            df["side"] = np.where(d >= 0.0, "LONG", "SHORT")
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
            "z_score": pd.to_numeric(df.get("z_score", np.nan), errors="coerce"),
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


def _build_pair_states_m60(pair_whitelist: list[str]) -> dict[str, dict]:
    states: dict[str, dict] = {}
    for name, fx, fy, cx, cy, *_ in M60_PAIRS:
        if name not in pair_whitelist:
            continue
        df = load_pair_data_m60(fx, fy, cx, cy)
        if df is None or len(df) == 0:
            continue
        y = np.log(df["Y"].to_numpy())
        x = np.log(df["X"].to_numpy())
        ts = _normalize_ts_ns(df["timestamp"]).to_numpy(dtype="int64")
        _, errors, _ = compute_kalman_states_m60(y, x)
        z_scores = compute_z_scores_m60(errors)
        states[name] = {
            "y": y,
            "x": x,
            "z": z_scores,
            "ts": ts,
            "ts_to_idx": {int(t): i for i, t in enumerate(ts)},
        }
    return states


def _build_robust_lookup(
    state_cache: dict[str, dict[str, dict]],
    student_df: float,
    huber_c: float,
    ew_alpha: float,
    tod_alpha: float,
    jump_prior: float,
    jump_var_mult: float,
) -> dict[str, dict[str, dict[str, np.ndarray]]]:
    out: dict[str, dict[str, dict[str, np.ndarray]]] = {}
    for tf, pair_map in state_cache.items():
        out[tf] = {}
        for pair, st in pair_map.items():
            z = np.asarray(st.get("z", []), dtype=float)
            ts = np.asarray(st.get("ts", []), dtype="int64")
            if len(z) == 0 or len(ts) == 0:
                continue
            feats = compute_robust_kf_series_features(
                z=z,
                ts_ns=ts,
                student_df=student_df,
                huber_c=huber_c,
                ew_alpha=ew_alpha,
                tod_alpha=tod_alpha,
                jump_prior=jump_prior,
                jump_var_mult=jump_var_mult,
            )
            feats["ts"] = ts
            out[tf][pair] = feats
    return out


def _side_to_dir(side: str) -> int:
    s = str(side).upper()
    if s == "LONG":
        return 1
    if s == "SHORT":
        return -1
    return 0


def _attach_state_and_robust_features(
    df: pd.DataFrame,
    state_cache: dict[str, dict[str, dict]],
    robust_lookup: dict[str, dict[str, dict[str, np.ndarray]]],
) -> pd.DataFrame:
    out = df.copy()
    own_cols = [
        "kf_abs_z",
        "kf_innov",
        "kf_innov_std",
        "kf_robust_z",
        "kf_student_loglik",
        "kf_tod_scale",
        "kf_huber_weight",
        "kf_jump_prob",
        "kf_z_vel",
        "kf_z_accel",
    ]
    for c in own_cols:
        out[c] = 0.0

    out["side_dir"] = out["side"].map(_side_to_dir).astype(int)
    out["entry_idx"] = -1
    out["one_bar_move_bps"] = np.nan
    out["one_bar_pnl_base"] = np.nan
    out["one_bar_exit_ts"] = np.nan

    for i, row in out.iterrows():
        tf = str(row["timeframe"])
        pair = str(row["pair"])
        ts_ns = int(row["timestamp"])
        side = int(row["side_dir"])
        st = state_cache.get(tf, {}).get(pair)
        feat = robust_lookup.get(tf, {}).get(pair)
        if st is None or feat is None:
            continue
        idx = st["ts_to_idx"].get(ts_ns)
        if idx is None:
            continue
        if idx + 1 >= len(st["ts"]):
            continue

        prices = st["y"] if str(row["active_leg"]).upper() == "Y" else st["x"]
        p0 = float(prices[idx])
        p1 = float(prices[idx + 1])
        move = float((p1 - p0) * 10000.0)

        out.at[i, "entry_idx"] = int(idx)
        out.at[i, "one_bar_move_bps"] = move
        out.at[i, "one_bar_pnl_base"] = float(side * move)
        out.at[i, "one_bar_exit_ts"] = int(st["ts"][idx + 1])
        for c in own_cols:
            arr = feat.get(c)
            if arr is not None and idx < len(arr):
                out.at[i, c] = float(arr[idx])

    out = out[out["entry_idx"] >= 0].copy()
    out["one_bar_exit_ts"] = pd.to_numeric(out["one_bar_exit_ts"], errors="coerce").astype("int64")
    out["one_bar_move_bps"] = pd.to_numeric(out["one_bar_move_bps"], errors="coerce").astype(float)
    out["one_bar_pnl_base"] = pd.to_numeric(out["one_bar_pnl_base"], errors="coerce").astype(float)
    for c in own_cols:
        out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0.0).astype(float)
    return out


def _attach_context_features(df: pd.DataFrame, lookup: dict[str, dict[str, dict[str, np.ndarray]]], source_tf: str, prefix: str) -> pd.DataFrame:
    out = df.copy()
    cols = [
        "kf_abs_z",
        "kf_robust_z",
        "kf_student_loglik",
        "kf_tod_scale",
        "kf_jump_prob",
        "kf_z_vel",
        "kf_z_accel",
    ]
    for c in cols:
        out[f"{prefix}_{c}"] = 0.0

    src = lookup.get(source_tf, {})
    for i, row in out.iterrows():
        pair = str(row["pair"])
        ts_ns = int(row["timestamp"])
        feat = src.get(pair)
        if feat is None:
            continue
        ts = feat.get("ts")
        if ts is None or len(ts) == 0:
            continue
        idx = int(np.searchsorted(ts, ts_ns, side="right") - 1)
        if idx < 0:
            continue
        for c in cols:
            arr = feat.get(c)
            if arr is not None and idx < len(arr):
                out.at[i, f"{prefix}_{c}"] = float(arr[idx])
    return out


def _time_ordered_split(df: pd.DataFrame, frac_tail: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    if df.empty:
        return df.copy(), df.copy()
    ordered = df.sort_values(["timestamp", "pair"]).copy()
    n = len(ordered)
    cut = int(math.floor((1.0 - float(frac_tail)) * n))
    cut = min(max(cut, 1), n - 1) if n > 1 else 0
    return ordered.iloc[:cut].copy(), ordered.iloc[cut:].copy()


def _compute_barriers(train_df: pd.DataFrame, pt_q: float, sl_q: float, ret_col: str = "one_bar_move_bps") -> tuple[float, float]:
    ret = pd.to_numeric(train_df[ret_col], errors="coerce")
    pos = ret[ret > 0.0]
    neg = ret[ret < 0.0].abs()
    pt = float(pos.quantile(float(pt_q))) if len(pos) else 1.0
    sl = float(neg.quantile(float(sl_q))) if len(neg) else 1.0
    return max(pt, 1e-6), max(sl, 1e-6)


def _label_from_returns(ret: pd.Series, pt: float, sl: float) -> pd.Series:
    ret = pd.to_numeric(ret, errors="coerce").fillna(0.0)
    y = np.zeros(len(ret), dtype=int)
    y[ret.to_numpy(dtype=float) >= float(pt)] = 1
    y[ret.to_numpy(dtype=float) <= -float(sl)] = -1
    return pd.Series(y, index=ret.index, dtype="int64")


def _label_one_bar(df: pd.DataFrame, pt: float, sl: float) -> pd.Series:
    return _label_from_returns(df["one_bar_move_bps"], pt=pt, sl=sl)


def _label_z_cross(df: pd.DataFrame, pt: float, sl: float) -> pd.Series:
    return _label_from_returns(df["pnl_bps"], pt=pt, sl=sl)


def _train_quantile_threshold(train_df: pd.DataFrame, col: str, q: float) -> float:
    vals = pd.to_numeric(train_df[col], errors="coerce").abs().replace([np.inf, -np.inf], np.nan).dropna()
    if vals.empty:
        return 0.0
    return float(vals.quantile(float(q)))


def _mark_actionable(df: pd.DataFrame, col: str, threshold: float) -> pd.Series:
    vals = pd.to_numeric(df[col], errors="coerce").abs().fillna(0.0)
    return pd.Series(vals >= float(threshold), index=df.index, dtype=bool)


def _build_feature_matrix(df: pd.DataFrame) -> pd.DataFrame:
    ts = pd.to_datetime(df["timestamp"], unit="ns", utc=True)
    num = pd.DataFrame(
        {
            "abs_z": pd.to_numeric(df.get("z_score", 0.0), errors="coerce").abs().fillna(0.0),
            "z_velocity": pd.to_numeric(df.get("z_velocity", 0.0), errors="coerce").fillna(0.0),
            "z_accel": pd.to_numeric(df.get("z_accel", 0.0), errors="coerce").fillna(0.0),
            "rolling_win_rate_10": pd.to_numeric(df.get("rolling_win_rate_10", 0.0), errors="coerce").fillna(0.0),
            "rolling_avg_pnl_10": pd.to_numeric(df.get("rolling_avg_pnl_10", 0.0), errors="coerce").fillna(0.0),
            "kf_abs_z": pd.to_numeric(df.get("kf_abs_z", 0.0), errors="coerce").fillna(0.0),
            "kf_robust_z": pd.to_numeric(df.get("kf_robust_z", 0.0), errors="coerce").fillna(0.0),
            "kf_student_loglik": pd.to_numeric(df.get("kf_student_loglik", 0.0), errors="coerce").fillna(0.0),
            "kf_tod_scale": pd.to_numeric(df.get("kf_tod_scale", 1.0), errors="coerce").fillna(1.0),
            "kf_jump_prob": pd.to_numeric(df.get("kf_jump_prob", 0.0), errors="coerce").fillna(0.0),
            "kf_z_vel": pd.to_numeric(df.get("kf_z_vel", 0.0), errors="coerce").fillna(0.0),
            "kf_z_accel": pd.to_numeric(df.get("kf_z_accel", 0.0), errors="coerce").fillna(0.0),
            "m5_kf_robust_z": pd.to_numeric(df.get("m5_kf_robust_z", 0.0), errors="coerce").fillna(0.0),
            "m5_kf_tod_scale": pd.to_numeric(df.get("m5_kf_tod_scale", 1.0), errors="coerce").fillna(1.0),
            "m5_kf_z_vel": pd.to_numeric(df.get("m5_kf_z_vel", 0.0), errors="coerce").fillna(0.0),
            "m5_kf_z_accel": pd.to_numeric(df.get("m5_kf_z_accel", 0.0), errors="coerce").fillna(0.0),
            "m15_kf_robust_z": pd.to_numeric(df.get("m15_kf_robust_z", 0.0), errors="coerce").fillna(0.0),
            "m15_kf_tod_scale": pd.to_numeric(df.get("m15_kf_tod_scale", 1.0), errors="coerce").fillna(1.0),
            "m15_kf_z_vel": pd.to_numeric(df.get("m15_kf_z_vel", 0.0), errors="coerce").fillna(0.0),
            "m15_kf_z_accel": pd.to_numeric(df.get("m15_kf_z_accel", 0.0), errors="coerce").fillna(0.0),
            "m60_kf_robust_z": pd.to_numeric(df.get("m60_kf_robust_z", 0.0), errors="coerce").fillna(0.0),
            "m60_kf_tod_scale": pd.to_numeric(df.get("m60_kf_tod_scale", 1.0), errors="coerce").fillna(1.0),
            "m60_kf_z_vel": pd.to_numeric(df.get("m60_kf_z_vel", 0.0), errors="coerce").fillna(0.0),
            "m60_kf_z_accel": pd.to_numeric(df.get("m60_kf_z_accel", 0.0), errors="coerce").fillna(0.0),
            "entry_hour_utc": ts.dt.hour.astype(float),
            "entry_dow_utc": ts.dt.dayofweek.astype(float),
        },
        index=df.index,
    )
    cat = pd.get_dummies(
        pd.DataFrame(
            {
                "pair": df["pair"].astype(str),
                "timeframe": df["timeframe"].astype(str),
                "side": df["side"].astype(str),
                "active_leg": df["active_leg"].astype(str),
            },
            index=df.index,
        ),
        dummy_na=False,
    )
    return pd.concat([num, cat], axis=1).fillna(0.0)


def _align_cols(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    out = df.copy()
    for c in cols:
        if c not in out.columns:
            out[c] = 0.0
    return out[cols].copy()


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -20.0, 20.0)))


def _fit_model_and_predict(
    model_name: str,
    X_fit: pd.DataFrame,
    y_fit: pd.Series,
    X_pred: pd.DataFrame,
    regime_fit: pd.Series | None = None,
    regime_pred: pd.Series | None = None,
    random_state: int = 42,
) -> tuple[np.ndarray, np.ndarray]:
    n = len(X_pred)
    if n == 0:
        return np.zeros(0, dtype=float), np.zeros(0, dtype=float)

    y_arr = y_fit.to_numpy(dtype=int)
    if len(np.unique(y_arr)) < 2:
        return np.full(n, 0.5, dtype=float), np.full(n, 0.5, dtype=float)

    if model_name == "heuristic":
        z_acc = pd.to_numeric(X_pred.get("kf_z_accel", 0.0), errors="coerce").fillna(0.0).to_numpy(dtype=float)
        z_vel = pd.to_numeric(X_pred.get("kf_z_vel", 0.0), errors="coerce").fillna(0.0).to_numpy(dtype=float)
        score = 0.75 * z_acc + 0.25 * z_vel
        p_up = _sigmoid(score)
        p_dn = _sigmoid(-score)
        return p_up, p_dn

    if model_name == "logit":
        clf = LogisticRegression(
            solver="lbfgs",
            class_weight="balanced",
            max_iter=1000,
            random_state=int(random_state),
        )
        clf.fit(X_fit, y_arr)
        proba = clf.predict_proba(X_pred)
        classes = clf.classes_.tolist()
        p_up = proba[:, classes.index(1)] if 1 in classes else np.zeros(n, dtype=float)
        p_dn = proba[:, classes.index(-1)] if -1 in classes else np.zeros(n, dtype=float)
        return p_up, p_dn

    if model_name == "hgbt":
        clf = HistGradientBoostingClassifier(
            loss="log_loss",
            max_depth=4,
            learning_rate=0.05,
            max_iter=350,
            min_samples_leaf=80,
            random_state=int(random_state),
        )
        clf.fit(X_fit, y_arr)
        proba = clf.predict_proba(X_pred)
        classes = clf.classes_.tolist()
        p_up = proba[:, classes.index(1)] if 1 in classes else np.zeros(n, dtype=float)
        p_dn = proba[:, classes.index(-1)] if -1 in classes else np.zeros(n, dtype=float)
        return p_up, p_dn

    if model_name == "dual_head":
        y_up = (y_arr == 1).astype(int)
        y_dn = (y_arr == -1).astype(int)
        up = HistGradientBoostingClassifier(
            loss="log_loss",
            max_depth=4,
            learning_rate=0.05,
            max_iter=300,
            min_samples_leaf=80,
            random_state=int(random_state),
        )
        dn = HistGradientBoostingClassifier(
            loss="log_loss",
            max_depth=4,
            learning_rate=0.05,
            max_iter=300,
            min_samples_leaf=80,
            random_state=int(random_state + 11),
        )
        up.fit(X_fit, y_up)
        dn.fit(X_fit, y_dn)
        p_up = up.predict_proba(X_pred)[:, 1]
        p_dn = dn.predict_proba(X_pred)[:, 1]
        return p_up, p_dn

    if model_name == "regime_expert":
        if regime_fit is None or regime_pred is None:
            raise ValueError("regime_expert requires regime series")
        rf = regime_fit.to_numpy(dtype=int)
        rp = regime_pred.to_numpy(dtype=int)

        p_up = np.full(n, 0.5, dtype=float)
        p_dn = np.full(n, 0.5, dtype=float)

        for regime in [0, 1]:
            tr_mask = rf == regime
            te_mask = rp == regime
            if not bool(np.any(te_mask)):
                continue
            if int(np.sum(tr_mask)) < 100 or len(np.unique(y_arr[tr_mask])) < 2:
                continue
            clf = HistGradientBoostingClassifier(
                loss="log_loss",
                max_depth=4,
                learning_rate=0.05,
                max_iter=250,
                min_samples_leaf=60,
                random_state=int(random_state + regime * 101),
            )
            clf.fit(X_fit.loc[tr_mask], y_arr[tr_mask])
            proba = clf.predict_proba(X_pred.loc[te_mask])
            classes = clf.classes_.tolist()
            if 1 in classes:
                p_up[te_mask] = proba[:, classes.index(1)]
            if -1 in classes:
                p_dn[te_mask] = proba[:, classes.index(-1)]
        return p_up, p_dn

    raise ValueError(f"Unsupported model: {model_name}")


def _calibrate_probs(
    p: np.ndarray,
    y_bin: np.ndarray,
) -> tuple[np.ndarray, str]:
    if len(p) == 0:
        return p, "none"
    y = y_bin.astype(int)
    if len(np.unique(y)) < 2:
        return np.clip(p, 0.0, 1.0), "none"
    iso = IsotonicRegression(out_of_bounds="clip")
    iso.fit(p, y)
    return np.clip(iso.predict(p), 0.0, 1.0), "isotonic"


def _apply_policy(
    df: pd.DataFrame,
    p_up: np.ndarray,
    p_dn: np.ndarray,
    pt: float,
    sl: float,
    p_min: float,
    ev_min: float,
    target_mode: str,
    policy_mode: str,
    p_move_min: float,
    both_balance_tol: float,
    both_capture_mult: float,
) -> pd.DataFrame:
    out = df.copy()
    if len(out) == 0:
        out["policy_action"] = pd.Series(dtype="object")
        out["pred_dir"] = pd.Series(dtype="int64")
        out["p_up"] = pd.Series(dtype="float64")
        out["p_dn"] = pd.Series(dtype="float64")
        out["ev_up"] = pd.Series(dtype="float64")
        out["ev_dn"] = pd.Series(dtype="float64")
        out["p_conf"] = pd.Series(dtype="float64")
        out["policy_pnl_bps"] = pd.Series(dtype="float64")
        out["override_used"] = pd.Series(dtype="bool")
        return out

    p_up = np.clip(np.asarray(p_up, dtype=float), 0.0, 1.0)
    p_dn = np.clip(np.asarray(p_dn, dtype=float), 0.0, 1.0)
    p_neu = np.maximum(0.0, 1.0 - p_up - p_dn)
    denom = p_up + p_dn + p_neu
    p_up = np.divide(p_up, denom, out=np.full_like(p_up, 1.0 / 3.0), where=denom > 0)
    p_dn = np.divide(p_dn, denom, out=np.full_like(p_dn, 1.0 / 3.0), where=denom > 0)

    ev_up = p_up * float(pt) - p_dn * float(sl)
    ev_dn = p_dn * float(pt) - p_up * float(sl)

    conf = np.maximum(p_up, p_dn)
    pred_dir = np.where(ev_up >= ev_dn, 1, -1)
    pred_ev = np.where(ev_up >= ev_dn, ev_up, ev_dn)
    do_override = (conf >= float(p_min)) & (pred_ev >= float(ev_min))

    if str(policy_mode) not in {"directional", "both_sides"}:
        raise ValueError(f"Unsupported policy_mode: {policy_mode}")
    if str(target_mode) == "z_cross" and str(policy_mode) == "both_sides":
        raise ValueError("policy_mode=both_sides is only supported with target_mode=one_bar")

    if str(target_mode) == "one_bar":
        base = pd.to_numeric(out["one_bar_pnl_base"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        move = pd.to_numeric(out["one_bar_move_bps"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        pred_pnl = pred_dir.astype(float) * move
        action = np.where(do_override, "override", "keep_baseline")
        pnl = np.where(do_override, pred_pnl, base)
        if str(policy_mode) == "both_sides":
            # OCO-style branch: when directional edge is weak but move probability is high and balanced,
            # take a both-sides contract and capture absolute one-bar move.
            move_conf = p_up + p_dn
            spread = np.abs(p_up - p_dn)
            balanced = spread <= float(both_balance_tol)
            # Directional override is only allowed when probabilities are clearly separated.
            do_dir = do_override & ~balanced
            do_both = (~do_dir) & (move_conf >= float(p_move_min)) & balanced
            both_pnl = np.abs(move) * float(both_capture_mult)
            pnl = np.where(do_dir, pred_pnl, base)
            pnl = np.where(do_both, both_pnl, pnl)
            action = np.where(do_dir, "override", "keep_baseline")
            action = np.where(do_both, "both_oco", action)
            do_override = do_dir | do_both
        drop_trade = np.zeros(len(out), dtype=bool)
    elif str(target_mode) == "z_cross":
        base = pd.to_numeric(out["pnl_bps"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        good_conf = (p_up >= float(p_min)) & (ev_up >= float(ev_min))
        bad_conf = (p_dn >= float(p_min)) & (ev_dn >= float(ev_min))
        drop_trade = bad_conf & ~good_conf
        pnl = np.where(drop_trade, np.nan, base)
        action = np.where(drop_trade, "skip", "keep_baseline")
        do_override = drop_trade
    else:
        raise ValueError(f"Unsupported target_mode: {target_mode}")

    out["policy_action"] = action
    out["pred_dir"] = pred_dir.astype(int)
    out["p_up"] = p_up
    out["p_dn"] = p_dn
    out["ev_up"] = ev_up
    out["ev_dn"] = ev_dn
    out["p_conf"] = conf
    out["policy_pnl_bps"] = pnl
    out["override_used"] = do_override.astype(bool)
    out["drop_trade"] = drop_trade.astype(bool)
    return out


def _score_policy(df: pd.DataFrame, risk_bps: float, target_mode: str) -> dict[str, float]:
    if df.empty:
        return {
            "trades": 0,
            "mean_pnl_per_trade_bps": 0.0,
            "sharpe": 0.0,
            "annualized_bps_calendar": 0.0,
            "time_in_market_pct": 0.0,
            "worst_single_day_bps": 0.0,
            "max_daily_dd_bps": 0.0,
            "override_rate": 0.0,
        }
    t = df.copy()
    t["pnl_bps"] = pd.to_numeric(t["policy_pnl_bps"], errors="coerce")
    t = t[t["pnl_bps"].notna()].copy()
    if t.empty:
        return {
            "trades": 0,
            "mean_pnl_per_trade_bps": 0.0,
            "sharpe": 0.0,
            "annualized_bps_calendar": 0.0,
            "time_in_market_pct": 0.0,
            "worst_single_day_bps": 0.0,
            "max_daily_dd_bps": 0.0,
            "override_rate": 0.0,
        }
    if str(target_mode) == "one_bar":
        t["exit_ts"] = pd.to_numeric(t["one_bar_exit_ts"], errors="coerce").fillna(t["timestamp"]).astype("int64")
        t["duration_bars"] = 1
        t["max_hold_bars"] = 1
    elif str(target_mode) == "z_cross":
        t["exit_ts"] = pd.to_numeric(t["exit_ts"], errors="coerce").fillna(t["timestamp"]).astype("int64")
    else:
        raise ValueError(f"Unsupported target_mode: {target_mode}")
    m = _metrics_with_risk(t, risk_bps=risk_bps)
    return {
        "trades": float(m["trades"]),
        "mean_pnl_per_trade_bps": float(m["mean_pnl_per_trade_bps"]),
        "sharpe": float(m["sharpe"]),
        "annualized_bps_calendar": float(m["annualized_bps_calendar"]),
        "time_in_market_pct": float(m["time_in_market_pct"]),
        "worst_single_day_bps": float(m["worst_single_day_bps"]),
        "max_daily_dd_bps": float(m["max_daily_dd_bps"]),
        "override_rate": float(pd.to_numeric(t["override_used"], errors="coerce").fillna(False).mean()),
    }


def _select_pair_set(df: pd.DataFrame, cutoff: float) -> set[str]:
    sel = _filter_pairs_by_sharpe(df, cutoff=float(cutoff))
    return set(sel["pair"].astype(str).unique().tolist())


def _apply_pair_filter(df: pd.DataFrame, keep_pairs: set[str]) -> pd.DataFrame:
    if not keep_pairs:
        return df.iloc[:0].copy()
    return df[df["pair"].astype(str).isin(keep_pairs)].copy()


def _filter_trade_timeframes(df: pd.DataFrame, trade_tfs: set[str]) -> pd.DataFrame:
    return df[df["timeframe"].astype(str).isin(trade_tfs)].copy()


def _train_and_select_model(
    train_df: pd.DataFrame,
    risk_bps: float,
    model_names: list[str],
    p_min_grid: list[float],
    ev_min_grid: list[float],
    pt: float,
    sl: float,
    calibration_frac: float,
    random_state: int,
    target_mode: str,
    policy_mode: str,
    p_move_min: float,
    both_balance_tol: float,
    both_capture_mult: float,
) -> tuple[dict, pd.DataFrame]:
    if len(train_df) < 300:
        raise RuntimeError("Not enough train rows for model selection")

    tr_fit, tr_cal = _time_ordered_split(train_df, frac_tail=float(calibration_frac))
    if len(tr_fit) < 100:
        tr_fit = train_df.copy()
        tr_cal = train_df.copy()

    if str(target_mode) == "one_bar":
        y_fit = _label_one_bar(tr_fit, pt=pt, sl=sl)
        y_cal = _label_one_bar(tr_cal, pt=pt, sl=sl)
    elif str(target_mode) == "z_cross":
        y_fit = _label_z_cross(tr_fit, pt=pt, sl=sl)
        y_cal = _label_z_cross(tr_cal, pt=pt, sl=sl)
    else:
        raise ValueError(f"Unsupported target_mode: {target_mode}")

    X_fit = _build_feature_matrix(tr_fit)
    X_cal = _build_feature_matrix(tr_cal)
    cols = X_fit.columns.tolist()
    X_cal = _align_cols(X_cal, cols)

    out_rows: list[dict] = []
    best: dict | None = None

    reg_fit = (pd.to_numeric(tr_fit.get("kf_tod_scale", 1.0), errors="coerce").fillna(1.0) > float(np.median(tr_fit.get("kf_tod_scale", 1.0)))).astype(int)
    reg_cal = (pd.to_numeric(tr_cal.get("kf_tod_scale", 1.0), errors="coerce").fillna(1.0) > float(np.median(tr_fit.get("kf_tod_scale", 1.0)))).astype(int)

    for model_name in model_names:
        p_up_raw, p_dn_raw = _fit_model_and_predict(
            model_name=model_name,
            X_fit=X_fit,
            y_fit=y_fit,
            X_pred=X_cal,
            regime_fit=reg_fit,
            regime_pred=reg_cal,
            random_state=int(random_state + abs(hash(model_name)) % 10_000),
        )

        p_up_cal, cal_up_method = _calibrate_probs(p_up_raw, (y_cal.to_numpy(dtype=int) == 1).astype(int))
        p_dn_cal, cal_dn_method = _calibrate_probs(p_dn_raw, (y_cal.to_numpy(dtype=int) == -1).astype(int))

        for p_min, ev_min in itertools.product(p_min_grid, ev_min_grid):
            pol = _apply_policy(
                tr_cal,
                p_up=p_up_cal,
                p_dn=p_dn_cal,
                pt=float(pt),
                sl=float(sl),
                p_min=float(p_min),
                ev_min=float(ev_min),
                target_mode=str(target_mode),
                policy_mode=str(policy_mode),
                p_move_min=float(p_move_min),
                both_balance_tol=float(both_balance_tol),
                both_capture_mult=float(both_capture_mult),
            )
            m = _score_policy(pol, risk_bps=float(risk_bps), target_mode=str(target_mode))
            score = (
                0.45 * float(m["mean_pnl_per_trade_bps"])
                + 0.35 * float(m["sharpe"])
                + 0.20 * (float(m["annualized_bps_calendar"]) / 365.25)
            )
            row = {
                "model_name": model_name,
                "p_min": float(p_min),
                "ev_min": float(ev_min),
                "cal_up_method": cal_up_method,
                "cal_dn_method": cal_dn_method,
                **m,
                "score": float(score),
            }
            out_rows.append(row)
            if best is None or row["score"] > best["score"]:
                best = row

    if best is None:
        raise RuntimeError("No model candidate was produced")

    return best, pd.DataFrame(out_rows)


def _fit_final_model_and_score(
    model_name: str,
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    p_min: float,
    ev_min: float,
    pt: float,
    sl: float,
    calibration_frac: float,
    random_state: int,
    target_mode: str,
    policy_mode: str,
    p_move_min: float,
    both_balance_tol: float,
    both_capture_mult: float,
) -> pd.DataFrame:
    if test_df.empty:
        return test_df.copy()

    tr_fit, tr_cal = _time_ordered_split(train_df, frac_tail=float(calibration_frac))
    if len(tr_fit) < 100:
        tr_fit = train_df.copy()
        tr_cal = train_df.copy()

    if str(target_mode) == "one_bar":
        y_fit = _label_one_bar(tr_fit, pt=pt, sl=sl)
        y_cal = _label_one_bar(tr_cal, pt=pt, sl=sl)
    elif str(target_mode) == "z_cross":
        y_fit = _label_z_cross(tr_fit, pt=pt, sl=sl)
        y_cal = _label_z_cross(tr_cal, pt=pt, sl=sl)
    else:
        raise ValueError(f"Unsupported target_mode: {target_mode}")

    X_fit = _build_feature_matrix(tr_fit)
    X_cal = _build_feature_matrix(tr_cal)
    X_te = _build_feature_matrix(test_df)
    cols = X_fit.columns.tolist()
    X_cal = _align_cols(X_cal, cols)
    X_te = _align_cols(X_te, cols)

    reg_fit = (pd.to_numeric(tr_fit.get("kf_tod_scale", 1.0), errors="coerce").fillna(1.0) > float(np.median(tr_fit.get("kf_tod_scale", 1.0)))).astype(int)
    reg_cal = (pd.to_numeric(tr_cal.get("kf_tod_scale", 1.0), errors="coerce").fillna(1.0) > float(np.median(tr_fit.get("kf_tod_scale", 1.0)))).astype(int)
    reg_te = (pd.to_numeric(test_df.get("kf_tod_scale", 1.0), errors="coerce").fillna(1.0) > float(np.median(tr_fit.get("kf_tod_scale", 1.0)))).astype(int)

    p_up_cal_raw, p_dn_cal_raw = _fit_model_and_predict(
        model_name=model_name,
        X_fit=X_fit,
        y_fit=y_fit,
        X_pred=X_cal,
        regime_fit=reg_fit,
        regime_pred=reg_cal,
        random_state=int(random_state + 111),
    )
    p_up_te_raw, p_dn_te_raw = _fit_model_and_predict(
        model_name=model_name,
        X_fit=X_fit,
        y_fit=y_fit,
        X_pred=X_te,
        regime_fit=reg_fit,
        regime_pred=reg_te,
        random_state=int(random_state + 111),
    )

    # Fit calibrators on calibration split raw probs.
    up_iso = IsotonicRegression(out_of_bounds="clip")
    dn_iso = IsotonicRegression(out_of_bounds="clip")

    y_cal_up = (y_cal.to_numpy(dtype=int) == 1).astype(int)
    y_cal_dn = (y_cal.to_numpy(dtype=int) == -1).astype(int)

    if len(np.unique(y_cal_up)) >= 2:
        up_iso.fit(p_up_cal_raw, y_cal_up)
        p_up_te = np.clip(up_iso.predict(p_up_te_raw), 0.0, 1.0)
    else:
        p_up_te = np.clip(p_up_te_raw, 0.0, 1.0)

    if len(np.unique(y_cal_dn)) >= 2:
        dn_iso.fit(p_dn_cal_raw, y_cal_dn)
        p_dn_te = np.clip(dn_iso.predict(p_dn_te_raw), 0.0, 1.0)
    else:
        p_dn_te = np.clip(p_dn_te_raw, 0.0, 1.0)

    scored = _apply_policy(
        test_df,
        p_up=p_up_te,
        p_dn=p_dn_te,
        pt=float(pt),
        sl=float(sl),
        p_min=float(p_min),
        ev_min=float(ev_min),
        target_mode=str(target_mode),
        policy_mode=str(policy_mode),
        p_move_min=float(p_move_min),
        both_balance_tol=float(both_balance_tol),
        both_capture_mult=float(both_capture_mult),
    )
    return scored


def _build_yearly_table(df: pd.DataFrame, risk_bps: float) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["year"])
    w = df.copy()
    w["year"] = pd.to_datetime(w["exit_ts"], unit="ns", utc=True).dt.year
    rows = []
    for year, sub in w.groupby("year", sort=True):
        m = _metrics_with_risk(sub, risk_bps=risk_bps)
        rows.append({"year": int(year), **m})
    return pd.DataFrame(rows)


def _build_pair_tf_table(df: pd.DataFrame, risk_bps: float) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["pair", "timeframe"])
    rows = []
    for (pair, tf), sub in df.groupby(["pair", "timeframe"], sort=True):
        m = _metrics_with_risk(sub, risk_bps=risk_bps)
        rows.append({"pair": str(pair), "timeframe": str(tf), **m})
    return pd.DataFrame(rows)


def main() -> None:
    p = argparse.ArgumentParser(description="Causal directional robust-KF meta WFO")
    p.add_argument("--mixes", default="m5=MOM,m15=MOM+REV,m60=REV")
    p.add_argument("--trade-timeframes", default="m15,m60")
    p.add_argument("--decision-timeframes", default="m15,m60")
    p.add_argument("--models", default="heuristic,logit,hgbt,dual_head,regime_expert")
    p.add_argument("--target-mode", default="z_cross", choices=["z_cross", "one_bar"])
    p.add_argument("--policy-mode", default="directional", choices=["directional", "both_sides"])

    p.add_argument("--start-test-year", type=int, default=2020)
    p.add_argument("--end-test-year", type=int, default=2025)
    p.add_argument("--embargo-days", type=int, default=5)
    p.add_argument("--exclude-oil", action="store_true", default=True)

    p.add_argument("--accel-quantile", type=float, default=0.80)
    p.add_argument("--pt-quantile", type=float, default=0.60)
    p.add_argument("--sl-quantile", type=float, default=0.60)
    p.add_argument("--p-min-grid", default="0.45,0.50,0.55,0.60")
    p.add_argument("--ev-min-grid", default="0.00,0.10,0.20")
    p.add_argument("--p-move-min", type=float, default=0.85)
    p.add_argument("--both-balance-tol", type=float, default=0.08)
    p.add_argument("--both-capture-mult", type=float, default=1.0)
    p.add_argument("--calibration-frac", type=float, default=0.20)

    p.add_argument("--pair-sharpe-cutoff", type=float, default=0.30)

    p.add_argument("--min-mean-bps", type=float, default=5.0)
    p.add_argument("--min-sharpe", type=float, default=2.0)
    p.add_argument("--min-tim-pct", type=float, default=2.0)
    p.add_argument("--max-tim-pct", type=float, default=10.0)
    p.add_argument("--min-single-day-improve-frac", type=float, default=0.10)
    p.add_argument("--max-dd-worse-frac", type=float, default=0.05)
    p.add_argument("--min-fold-mean-bps", type=float, default=-1.0)

    p.add_argument("--robust-student-df", type=float, default=5.0)
    p.add_argument("--robust-huber-c", type=float, default=2.5)
    p.add_argument("--robust-ew-alpha", type=float, default=0.04)
    p.add_argument("--robust-tod-alpha", type=float, default=0.05)
    p.add_argument("--robust-jump-prior", type=float, default=0.04)
    p.add_argument("--robust-jump-var-mult", type=float, default=9.0)

    p.add_argument("--random-state", type=int, default=42)
    p.add_argument("--out-prefix", default="kf_dir_q80_1bar")

    args = p.parse_args()

    trade_tfs = [x.strip().lower() for x in str(args.trade_timeframes).split(",") if x.strip()]
    if not trade_tfs:
        raise ValueError("--trade-timeframes cannot be empty")
    for tf in trade_tfs:
        if tf not in {"m5", "m15", "m60"}:
            raise ValueError("--trade-timeframes supports only m5,m15,m60")
    trade_tfs_set = set(trade_tfs)

    decision_tfs = [x.strip().lower() for x in str(args.decision_timeframes).split(",") if x.strip()]
    for tf in decision_tfs:
        if tf not in {"m15", "m60"}:
            raise ValueError("--decision-timeframes supports only m15,m60")
        if tf not in trade_tfs_set:
            raise ValueError("--decision-timeframes must be a subset of --trade-timeframes")

    model_names = [x.strip() for x in str(args.models).split(",") if x.strip()]
    allowed_models = {"heuristic", "logit", "hgbt", "dual_head", "regime_expert"}
    bad_models = [m for m in model_names if m not in allowed_models]
    if bad_models:
        raise ValueError(f"Unsupported model names: {bad_models}")

    p_min_grid = _parse_grid(args.p_min_grid, cast=float)
    ev_min_grid = _parse_grid(args.ev_min_grid, cast=float)
    if str(args.policy_mode) == "both_sides" and str(args.target_mode) != "one_bar":
        raise ValueError("--policy-mode both_sides requires --target-mode one_bar")
    if float(args.p_move_min) <= 0.0 or float(args.p_move_min) > 1.0:
        raise ValueError("--p-move-min must be in (0, 1]")
    if float(args.both_balance_tol) < 0.0 or float(args.both_balance_tol) > 1.0:
        raise ValueError("--both-balance-tol must be in [0, 1]")
    if float(args.both_capture_mult) <= 0.0:
        raise ValueError("--both-capture-mult must be > 0")

    pair_whitelist = list(PAIR_WHITELIST_BASE)
    if bool(args.exclude_oil):
        pair_whitelist = [p for p in pair_whitelist if p not in OIL_LINKED_PAIRS]

    mixes = _parse_strategy_mixes(args.mixes)
    folds = _make_folds(args.start_test_year, args.end_test_year, args.embargo_days)

    print("Building state cache...")
    state_cache = {
        "m5": _build_pair_states("m5", pair_whitelist),
        "m15": _build_pair_states("m15", pair_whitelist),
        "m60": _build_pair_states_m60(pair_whitelist),
    }
    print("Building robust-KF lookup...")
    robust_lookup = _build_robust_lookup(
        state_cache=state_cache,
        student_df=float(args.robust_student_df),
        huber_c=float(args.robust_huber_c),
        ew_alpha=float(args.robust_ew_alpha),
        tod_alpha=float(args.robust_tod_alpha),
        jump_prior=float(args.robust_jump_prior),
        jump_var_mult=float(args.robust_jump_var_mult),
    )

    fold_rows: list[dict] = []
    grid_rows: list[pd.DataFrame] = []
    oos_base_rows: list[pd.DataFrame] = []
    oos_cand_rows: list[pd.DataFrame] = []
    oos_prom_rows: list[pd.DataFrame] = []
    scored_rows: list[pd.DataFrame] = []

    for mix in mixes:
        mix_name = _mix_id(mix)
        print(f"\n=== Mix: {mix_name} ===")

        loaded: dict[str, pd.DataFrame] = {}
        for tf in ["m5", "m15", "m60"]:
            specs = [x.strip().upper() for x in str(mix[tf]).split("+") if x.strip()]
            tf_frames: list[pd.DataFrame] = []
            for strat in specs:
                if strat == "NONE":
                    continue
                path, pair_col = EVENT_PATHS[(tf, strat)]
                tf_frames.append(_load_events(path, strat, tf, pair_col, pair_whitelist))
            loaded[tf] = pd.concat(tf_frames, ignore_index=True) if tf_frames else _empty_events_frame()

        all_events = pd.concat([loaded["m5"], loaded["m15"], loaded["m60"]], ignore_index=True)
        if all_events.empty:
            print("  skip: no rows")
            continue

        all_events = _attach_state_and_robust_features(all_events, state_cache=state_cache, robust_lookup=robust_lookup)
        # Context stack from all three timeframes.
        all_events = _attach_context_features(all_events, robust_lookup, source_tf="m5", prefix="m5")
        all_events = _attach_context_features(all_events, robust_lookup, source_tf="m15", prefix="m15")
        all_events = _attach_context_features(all_events, robust_lookup, source_tf="m60", prefix="m60")
        all_events = all_events.sort_values(["timestamp", "pair", "timeframe"]).reset_index(drop=True)

        trade_id = np.arange(len(all_events), dtype=np.int64)
        all_events["trade_id"] = trade_id

        for fold in folds:
            print(f"  Fold {fold.test_year}:")
            tr_all = all_events[all_events["timestamp"] < fold.train_end_ts_ns].copy()
            te_all = all_events[(all_events["timestamp"] >= fold.test_start_ts_ns) & (all_events["timestamp"] < fold.test_end_ts_ns)].copy()

            if tr_all.empty or te_all.empty:
                print("    skip: empty train or test")
                continue

            tr_trade = _filter_trade_timeframes(tr_all, trade_tfs=trade_tfs_set)
            te_trade = _filter_trade_timeframes(te_all, trade_tfs=trade_tfs_set)
            if tr_trade.empty or te_trade.empty:
                print("    skip: no trade rows for selected --trade-timeframes")
                continue

            # Base train for pair filter / risk only.
            tr_base_guard = _apply_guardrail(tr_trade)
            pair_keep = _select_pair_set(tr_base_guard, cutoff=float(args.pair_sharpe_cutoff))
            tr_all = _apply_pair_filter(tr_all, pair_keep)
            te_all = _apply_pair_filter(te_all, pair_keep)
            tr_trade = _apply_pair_filter(tr_trade, pair_keep)
            te_trade = _apply_pair_filter(te_trade, pair_keep)
            if tr_all.empty or te_all.empty or tr_trade.empty or te_trade.empty:
                print("    skip: no rows after pair filter")
                continue

            risk_bps = _derive_risk_bps(tr_trade, fallback=100.0)

            # Candidate starts as baseline; directional overrides are patched in.
            cand_te = te_trade.copy()
            cand_te["override_used"] = False
            cand_te["policy_action"] = "none"
            cand_te["model_name"] = "none"
            cand_te["p_up"] = 0.5
            cand_te["p_dn"] = 0.5
            cand_te["ev_up"] = 0.0
            cand_te["ev_dn"] = 0.0
            cand_te["p_conf"] = 0.0
            cand_te["drop_trade"] = False

            fold_grid_parts: list[pd.DataFrame] = []
            tf_choice_rows: list[dict] = []

            for tf in decision_tfs:
                tr_tf = tr_trade[tr_trade["timeframe"] == tf].copy()
                te_tf = te_trade[te_trade["timeframe"] == tf].copy()
                if len(tr_tf) < 500 or te_tf.empty:
                    continue

                q_thr = _train_quantile_threshold(tr_tf, col="kf_z_accel", q=float(args.accel_quantile))
                tr_act = tr_tf[_mark_actionable(tr_tf, col="kf_z_accel", threshold=q_thr)].copy()
                te_act = te_tf[_mark_actionable(te_tf, col="kf_z_accel", threshold=q_thr)].copy()
                if len(tr_act) < 300 or te_act.empty:
                    continue

                ret_col = "one_bar_move_bps" if str(args.target_mode) == "one_bar" else "pnl_bps"
                pt, sl = _compute_barriers(
                    tr_act,
                    pt_q=float(args.pt_quantile),
                    sl_q=float(args.sl_quantile),
                    ret_col=ret_col,
                )

                try:
                    best, tgrid = _train_and_select_model(
                        train_df=tr_act,
                        risk_bps=float(risk_bps),
                        model_names=model_names,
                        p_min_grid=p_min_grid,
                        ev_min_grid=ev_min_grid,
                        pt=float(pt),
                        sl=float(sl),
                        calibration_frac=float(args.calibration_frac),
                        random_state=int(args.random_state + fold.test_year + (15 if tf == "m15" else 60)),
                        target_mode=str(args.target_mode),
                        policy_mode=str(args.policy_mode),
                        p_move_min=float(args.p_move_min),
                        both_balance_tol=float(args.both_balance_tol),
                        both_capture_mult=float(args.both_capture_mult),
                    )
                except RuntimeError:
                    continue

                tgrid["mix_id"] = mix_name
                tgrid["fold_year"] = int(fold.test_year)
                tgrid["timeframe"] = tf
                tgrid["accel_threshold"] = float(q_thr)
                tgrid["pt_bps"] = float(pt)
                tgrid["sl_bps"] = float(sl)
                tgrid["policy_mode"] = str(args.policy_mode)
                tgrid["p_move_min"] = float(args.p_move_min)
                tgrid["both_balance_tol"] = float(args.both_balance_tol)
                tgrid["both_capture_mult"] = float(args.both_capture_mult)
                fold_grid_parts.append(tgrid)

                te_scored = _fit_final_model_and_score(
                    model_name=str(best["model_name"]),
                    train_df=tr_act,
                    test_df=te_act,
                    p_min=float(best["p_min"]),
                    ev_min=float(best["ev_min"]),
                    pt=float(pt),
                    sl=float(sl),
                    calibration_frac=float(args.calibration_frac),
                    random_state=int(args.random_state + fold.test_year + 500 + (15 if tf == "m15" else 60)),
                    target_mode=str(args.target_mode),
                    policy_mode=str(args.policy_mode),
                    p_move_min=float(args.p_move_min),
                    both_balance_tol=float(args.both_balance_tol),
                    both_capture_mult=float(args.both_capture_mult),
                )

                te_scored["mix_id"] = mix_name
                te_scored["fold_year"] = int(fold.test_year)
                te_scored["decision_tf"] = tf
                te_scored["accel_threshold"] = float(q_thr)
                te_scored["pt_bps"] = float(pt)
                te_scored["sl_bps"] = float(sl)
                te_scored["selected_model"] = str(best["model_name"])
                te_scored["selected_p_min"] = float(best["p_min"])
                te_scored["selected_ev_min"] = float(best["ev_min"])
                te_scored["policy_mode"] = str(args.policy_mode)
                scored_rows.append(te_scored)

                tf_choice_rows.append(
                    {
                        "timeframe": tf,
                        "accel_threshold": float(q_thr),
                        "pt_bps": float(pt),
                        "sl_bps": float(sl),
                        "selected_model": str(best["model_name"]),
                        "selected_p_min": float(best["p_min"]),
                        "selected_ev_min": float(best["ev_min"]),
                        "train_actionable_rows": int(len(tr_act)),
                        "test_actionable_rows": int(len(te_act)),
                        "train_actionable_frac": float(len(tr_act) / max(len(tr_tf), 1)),
                        "test_actionable_frac": float(len(te_act) / max(len(te_tf), 1)),
                    }
                )

                # Patch candidate rows for this timeframe and actionable set.
                idx_map = {int(r.trade_id): r for r in te_scored.itertuples(index=False)}
                idx_sel = cand_te[(cand_te["timeframe"] == tf) & (cand_te["trade_id"].isin(idx_map.keys()))].index
                for idx in idx_sel:
                    rid = int(cand_te.at[idx, "trade_id"])
                    r = idx_map[rid]
                    cand_te.at[idx, "p_up"] = float(r.p_up)
                    cand_te.at[idx, "p_dn"] = float(r.p_dn)
                    cand_te.at[idx, "ev_up"] = float(r.ev_up)
                    cand_te.at[idx, "ev_dn"] = float(r.ev_dn)
                    cand_te.at[idx, "p_conf"] = float(r.p_conf)
                    cand_te.at[idx, "model_name"] = str(best["model_name"])
                    cand_te.at[idx, "policy_action"] = str(r.policy_action)
                    do_override = bool(r.override_used)
                    cand_te.at[idx, "override_used"] = do_override
                    if str(args.target_mode) == "one_bar" and do_override:
                        cand_te.at[idx, "pnl_bps"] = float(r.policy_pnl_bps)
                        cand_te.at[idx, "exit_ts"] = int(r.one_bar_exit_ts)
                        cand_te.at[idx, "duration_bars"] = 1
                        cand_te.at[idx, "max_hold_bars"] = 1
                    elif str(args.target_mode) == "z_cross":
                        cand_te.at[idx, "drop_trade"] = bool(r.drop_trade)

            if str(args.target_mode) == "z_cross":
                cand_te = cand_te[~pd.to_numeric(cand_te["drop_trade"], errors="coerce").fillna(False)].copy()

            # Guardrail + metrics.
            base_guard = _apply_guardrail(te_trade)
            cand_guard = _apply_guardrail(cand_te)

            m_base = _metrics_with_risk(base_guard, risk_bps=float(risk_bps))
            m_cand = _metrics_with_risk(cand_guard, risk_bps=float(risk_bps))

            base_abs_worst = abs(float(m_base["worst_single_day_bps"]))
            cand_abs_worst = abs(float(m_cand["worst_single_day_bps"]))
            single_day_improve_ok = cand_abs_worst <= (1.0 - float(args.min_single_day_improve_frac)) * base_abs_worst if base_abs_worst > 0 else True
            dd_worse_ok = abs(float(m_cand["max_daily_dd_bps"])) <= (1.0 + float(args.max_dd_worse_frac)) * abs(float(m_base["max_daily_dd_bps"])) if float(m_base["max_daily_dd_bps"]) != 0 else True

            hard = bool(
                float(m_cand["mean_pnl_per_trade_bps"]) >= float(args.min_mean_bps)
                and float(m_cand["sharpe"]) >= float(args.min_sharpe)
                and float(args.min_tim_pct) <= float(m_cand["time_in_market_pct"]) <= float(args.max_tim_pct)
                and single_day_improve_ok
                and dd_worse_ok
                and float(m_cand["mean_pnl_per_trade_bps"]) >= float(args.min_fold_mean_bps)
            )

            promoted = cand_guard.copy() if hard else base_guard.copy()

            fold_rows.append(
                {
                    "mix_id": mix_name,
                    "year": int(fold.test_year),
                    "risk_bps": float(risk_bps),
                    "base_trades": int(m_base["trades"]),
                    "base_mean_bps": float(m_base["mean_pnl_per_trade_bps"]),
                    "base_sharpe": float(m_base["sharpe"]),
                    "base_annualized_bps": float(m_base["annualized_bps_calendar"]),
                    "base_cagr": float(m_base["cagr"]),
                    "base_tim_pct": float(m_base["time_in_market_pct"]),
                    "base_worst_single_day_bps": float(m_base["worst_single_day_bps"]),
                    "base_max_daily_dd_bps": float(m_base["max_daily_dd_bps"]),
                    "cand_trades": int(m_cand["trades"]),
                    "cand_mean_bps": float(m_cand["mean_pnl_per_trade_bps"]),
                    "cand_sharpe": float(m_cand["sharpe"]),
                    "cand_annualized_bps": float(m_cand["annualized_bps_calendar"]),
                    "cand_cagr": float(m_cand["cagr"]),
                    "cand_tim_pct": float(m_cand["time_in_market_pct"]),
                    "cand_worst_single_day_bps": float(m_cand["worst_single_day_bps"]),
                    "cand_max_daily_dd_bps": float(m_cand["max_daily_dd_bps"]),
                    "single_day_improve_ok": bool(single_day_improve_ok),
                    "dd_worse_ok": bool(dd_worse_ok),
                    "oos_hard_pass": bool(hard),
                    "promoted_on_fold": bool(hard),
                    "promoted_source": "candidate" if hard else "baseline_hard_fail",
                    "decision_tf_count": int(len(tf_choice_rows)),
                    "policy_mode": str(args.policy_mode),
                    "target_mode": str(args.target_mode),
                    "decision_tf_config": "; ".join(
                        [
                            f"{r['timeframe']}:{r['selected_model']}@p{r['selected_p_min']:.2f}/ev{r['selected_ev_min']:.2f}"
                            for r in tf_choice_rows
                        ]
                    ),
                }
            )

            bdf = base_guard.copy()
            bdf["variant"] = "baseline"
            bdf["mix_id"] = mix_name
            bdf["fold_year"] = int(fold.test_year)
            bdf["promoted_source"] = "baseline"
            oos_base_rows.append(bdf)

            cdf = cand_guard.copy()
            cdf["variant"] = "directional_candidate"
            cdf["mix_id"] = mix_name
            cdf["fold_year"] = int(fold.test_year)
            cdf["promoted_source"] = "candidate"
            oos_cand_rows.append(cdf)

            pdf = promoted.copy()
            pdf["variant"] = "directional_promoted"
            pdf["mix_id"] = mix_name
            pdf["fold_year"] = int(fold.test_year)
            pdf["promoted_source"] = "candidate" if hard else "baseline_hard_fail"
            oos_prom_rows.append(pdf)

            if fold_grid_parts:
                grid_rows.append(pd.concat(fold_grid_parts, ignore_index=True))

            print(
                f"    base={m_base['mean_pnl_per_trade_bps']:.3f}bps sh={m_base['sharpe']:.3f} tim={m_base['time_in_market_pct']:.2f}% | "
                f"cand={m_cand['mean_pnl_per_trade_bps']:.3f}bps sh={m_cand['sharpe']:.3f} tim={m_cand['time_in_market_pct']:.2f}% | "
                f"promoted={'yes' if hard else 'no'}"
            )

    if not fold_rows:
        raise RuntimeError("No valid folds produced")

    folds_df = pd.DataFrame(fold_rows).sort_values(["mix_id", "year"]).reset_index(drop=True)
    grid_df = pd.concat(grid_rows, ignore_index=True) if grid_rows else pd.DataFrame()
    oos_base = pd.concat(oos_base_rows, ignore_index=True) if oos_base_rows else pd.DataFrame()
    oos_cand = pd.concat(oos_cand_rows, ignore_index=True) if oos_cand_rows else pd.DataFrame()
    oos_prom = pd.concat(oos_prom_rows, ignore_index=True) if oos_prom_rows else pd.DataFrame()
    oos_all = pd.concat([oos_base, oos_cand, oos_prom], ignore_index=True)
    scored_df = pd.concat(scored_rows, ignore_index=True) if scored_rows else pd.DataFrame()

    summary_rows: list[dict] = []
    yearly_rows: list[dict] = []
    pair_tf_rows: list[dict] = []
    for mix_name in sorted(folds_df["mix_id"].astype(str).unique().tolist()):
        mix_folds = folds_df[folds_df["mix_id"] == mix_name].copy()
        risk_bps = float(mix_folds["risk_bps"].mean()) if len(mix_folds) else 100.0
        for variant, sub in [
            ("baseline", oos_base[oos_base["mix_id"] == mix_name].copy()),
            ("directional_candidate", oos_cand[oos_cand["mix_id"] == mix_name].copy()),
            ("directional_promoted", oos_prom[oos_prom["mix_id"] == mix_name].copy()),
        ]:
            m = _metrics_with_risk(sub, risk_bps=risk_bps)
            summary_rows.append(
                {
                    "mix_id": mix_name,
                    "variant": variant,
                    "folds": int(len(mix_folds)),
                    "oos_hard_pass_rate": float(mix_folds["oos_hard_pass"].mean()) if len(mix_folds) else 0.0,
                    **m,
                }
            )

            yt = _build_yearly_table(sub, risk_bps=risk_bps)
            if not yt.empty:
                yt["mix_id"] = mix_name
                yt["variant"] = variant
                yearly_rows.append(yt)

            ptf = _build_pair_tf_table(sub, risk_bps=risk_bps)
            if not ptf.empty:
                ptf["mix_id"] = mix_name
                ptf["variant"] = variant
                pair_tf_rows.append(ptf)

    summary_df = pd.DataFrame(summary_rows).sort_values(["mix_id", "variant"]).reset_index(drop=True)
    yearly_df = pd.concat(yearly_rows, ignore_index=True) if yearly_rows else pd.DataFrame()
    pair_tf_df = pd.concat(pair_tf_rows, ignore_index=True) if pair_tf_rows else pd.DataFrame()

    out_dir = ROOT / "data" / "analysis"
    out_dir.mkdir(parents=True, exist_ok=True)

    summary_path = out_dir / f"{args.out_prefix}_summary.csv"
    folds_path = out_dir / f"{args.out_prefix}_folds.csv"
    grid_path = out_dir / f"{args.out_prefix}_model_grid.csv"
    trades_path = out_dir / f"{args.out_prefix}_oos_trades.csv"
    scored_path = out_dir / f"{args.out_prefix}_oos_scored.csv"
    yearly_path = out_dir / f"{args.out_prefix}_yearly.csv"
    pair_tf_path = out_dir / f"{args.out_prefix}_pair_timeframe_breakdown.csv"

    summary_df.to_csv(summary_path, index=False)
    folds_df.to_csv(folds_path, index=False)
    grid_df.to_csv(grid_path, index=False)
    oos_all.to_csv(trades_path, index=False)
    scored_df.to_csv(scored_path, index=False)
    yearly_df.to_csv(yearly_path, index=False)
    pair_tf_df.to_csv(pair_tf_path, index=False)

    print("\nSaved:")
    print(f"- {summary_path}")
    print(f"- {folds_path}")
    print(f"- {grid_path}")
    print(f"- {trades_path}")
    print(f"- {scored_path}")
    print(f"- {yearly_path}")
    print(f"- {pair_tf_path}")

    print("\nSummary:")
    print(summary_df.to_string(index=False))


if __name__ == "__main__":
    main()
