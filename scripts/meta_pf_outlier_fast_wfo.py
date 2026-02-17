#!/usr/bin/env python3
"""
Fast-hold causal WFO with robust-KF outlier/meta features.

Core behavior:
- Short legs (m5/m15) are re-priced with entry-time frozen exits:
  TP at +target_bps, SL at -stop_bps, timeout at max_hold_bars (default 2).
- Meta model predicts probability of hitting TP within 2 bars.
- Threshold + size policy (full/half/skip) chosen on train-only folds.
- Promotion gates require >=5 bps/trade and reduced time-in-market.
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
from scripts.lib.robust_kf_features import add_robust_kf_features, compute_robust_kf_series_features
from scripts.report_strategy_fx_comm_multi_tf import (
    OIL_LINKED_PAIRS,
    PAIR_WHITELIST_BASE,
    _apply_guardrail,
    _derive_risk_bps,
    _metrics_with_risk,
    _normalize_ts_ns,
)
from scripts.sweep_exit_params_short_tf import _build_pair_states
from pipelines.build_events_h1 import (
    PAIRS as M60_PAIRS,
    compute_kalman_states as compute_kalman_states_m60,
    compute_z_scores as compute_z_scores_m60,
    load_pair_data as load_pair_data_m60,
)

EVENT_PATHS = {
    ("m5", "MOM"): ("data/events/events_m5_8yr_v3_mom.csv", "pair"),
    ("m5", "REV"): ("data/events/events_m5_8yr_v3_rev.csv", "pair"),
    ("m15", "MOM"): ("data/events/events_m15_8yr_v3_mom.csv", "pair"),
    ("m15", "REV"): ("data/events/events_m15_8yr_v3_rev.csv", "pair"),
    ("m60", "MOM"): ("data/events/events_h1_8yr_v3_mom.csv", "symbol"),
    ("m60", "REV"): ("data/events/events_h1_8yr_v3_rev.csv", "symbol"),
}

FAST_MAX_BARS = 4


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
    vals = [float(t.strip()) for t in str(s).split(",") if t.strip()]
    if not vals:
        raise ValueError("Grid cannot be empty")
    return sorted({float(v) for v in vals})


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
        m: dict[str, str] = {}
        for tok in [x.strip() for x in part.split(",") if x.strip()]:
            if "=" not in tok:
                raise ValueError(f"Invalid mix token: {tok}")
            tf, strat = tok.split("=", 1)
            tf = tf.strip().lower()
            strat = _normalize_strategy_spec(strat.strip())
            if tf not in {"m5", "m15", "m60"}:
                raise ValueError(f"Unsupported timeframe: {tf}")
            m[tf] = strat
        if set(m.keys()) != {"m5", "m15", "m60"}:
            raise ValueError(f"Mix must set m5,m15,m60: {part}")
        if m["m5"] == "NONE" or m["m15"] == "NONE":
            raise ValueError("m5 and m15 cannot be NONE")
        out.append(m)
    if not out:
        out.append({"m5": "MOM", "m15": "MOM+REV", "m60": "REV"})
    return out


def _mix_id(mix: dict[str, str]) -> str:
    def _t(spec: str) -> str:
        return "".join(x.strip().lower() for x in str(spec).split("+") if x.strip())

    return f"m5_{_t(mix['m5'])}__m15_{_t(mix['m15'])}__m60_{_t(mix['m60'])}"


def _load_events(path: str, strategy: str, timeframe: str, pair_col: str, pair_whitelist: list[str]) -> pd.DataFrame:
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
        dur_col = "duration_bars" if "duration_bars" in df.columns else "duration"
        d = pd.to_numeric(df[dur_col], errors="coerce").fillna(0).astype(int).clip(lower=0)
        bar_ns = int(pd.Timedelta(minutes=bar_minutes).value)
        df["exit_ts"] = df["timestamp"] + d * bar_ns

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
            "z_score": pd.to_numeric(df["z_score"], errors="coerce"),
            "z_velocity": pd.to_numeric(df.get("z_velocity", np.nan), errors="coerce"),
            "z_accel": pd.to_numeric(df.get("z_accel", np.nan), errors="coerce"),
            "rolling_win_rate_10": pd.to_numeric(df.get("rolling_win_rate_10", np.nan), errors="coerce"),
            "rolling_avg_pnl_10": pd.to_numeric(df.get("rolling_avg_pnl_10", np.nan), errors="coerce"),
            "active_leg": df.get("active_leg", "UNKNOWN").astype(str),
            "side": df["side"].astype(str),
        }
    )
    out = out.dropna(subset=["pair", "timestamp", "pnl_bps"]).copy()
    return out.sort_values(["timestamp", "pair"]).reset_index(drop=True)


def _attach_fast_path_columns(short_df: pd.DataFrame, state_cache: dict[str, dict[str, dict]]) -> pd.DataFrame:
    out = short_df.copy()
    out["entry_idx"] = -1
    for h in range(1, FAST_MAX_BARS + 1):
        out[f"fast_pnl_{h}"] = np.nan
        out[f"fast_ts_{h}"] = np.nan
    out["fast_valid_max"] = False

    for i, row in out.iterrows():
        tf = str(row["timeframe"])  # m5/m15
        pair = str(row["pair"])
        st = state_cache.get(tf, {}).get(pair)
        if st is None:
            continue
        idx = st["ts_to_idx"].get(int(row["timestamp"]))
        if idx is None:
            continue

        prices = st["y"] if str(row["active_leg"]).upper() == "Y" else st["x"]
        side = 1 if str(row["side"]).upper() == "LONG" else -1
        if side == 0:
            continue

        n = len(prices)
        if idx + 1 >= n:
            continue

        p0 = float(prices[idx])
        valid_max = True
        for h in range(1, FAST_MAX_BARS + 1):
            j = idx + h
            if j < n:
                ph = float(prices[j])
                pnlh = float(side * (ph - p0) * 10000.0)
                tsh = int(st["ts"][j])
            else:
                prev = min(n - 1, idx + max(1, h - 1))
                ph = float(prices[prev])
                pnlh = float(side * (ph - p0) * 10000.0)
                tsh = int(st["ts"][prev])
                valid_max = False
            out.at[i, f"fast_pnl_{h}"] = pnlh
            out.at[i, f"fast_ts_{h}"] = float(tsh)

        out.at[i, "entry_idx"] = int(idx)
        out.at[i, "fast_valid_max"] = bool(valid_max)

    out = out[out["entry_idx"] >= 0].copy()
    for h in range(1, FAST_MAX_BARS + 1):
        out[f"fast_ts_{h}"] = out[f"fast_ts_{h}"].astype("int64")
    return out


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
        ts_to_idx = {int(t): i for i, t in enumerate(ts)}
        states[name] = {
            "y": y,
            "x": x,
            "z": z_scores,
            "ts": ts,
            "ts_to_idx": ts_to_idx,
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
    for tf, pairs in state_cache.items():
        out[tf] = {}
        for pair, st in pairs.items():
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


def _attach_context_robust_features(
    df: pd.DataFrame,
    lookup: dict[str, dict[str, dict[str, np.ndarray]]],
    source_tf: str,
    prefix: str,
) -> pd.DataFrame:
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
        ts = feat["ts"]
        idx = int(np.searchsorted(ts, ts_ns, side="right") - 1)
        if idx < 0:
            continue
        for c in cols:
            arr = feat.get(c)
            if arr is not None and idx < len(arr):
                out.at[i, f"{prefix}_{c}"] = float(arr[idx])
    return out


def _apply_outlier_candidate_gate(df: pd.DataFrame, gate_mode: str, z_thr_m5: float, z_thr_m15: float) -> pd.DataFrame:
    out = df.copy()
    m5_flag = pd.to_numeric(out.get("m5_kf_robust_z", 0.0), errors="coerce").abs() >= float(z_thr_m5)
    m15_flag = pd.to_numeric(out.get("kf_robust_z", 0.0), errors="coerce").abs() >= float(z_thr_m15)
    mode = str(gate_mode).lower()
    if mode == "or":
        hit = m5_flag | m15_flag
    elif mode == "and":
        hit = m5_flag & m15_flag
    elif mode == "none":
        hit = pd.Series(True, index=out.index)
    else:
        raise ValueError(f"Unsupported gate mode: {gate_mode}")
    out["outlier_m5_flag"] = m5_flag.astype(bool)
    out["outlier_m15_flag"] = m15_flag.astype(bool)
    out["candidate_gate_hit"] = hit.astype(bool)
    return out


def _apply_fast_exit_contract(short_df: pd.DataFrame, target_bps: float, stop_bps: float, max_hold_bars: int) -> pd.DataFrame:
    if int(max_hold_bars) < 1 or int(max_hold_bars) > FAST_MAX_BARS:
        raise ValueError(f"This fast mode supports max_hold_bars in [1,{FAST_MAX_BARS}]")

    d = short_df.copy()
    pnl_steps = [
        pd.to_numeric(d[f"fast_pnl_{h}"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        for h in range(1, FAST_MAX_BARS + 1)
    ]
    ts_steps = [
        pd.to_numeric(d[f"fast_ts_{h}"], errors="coerce").fillna(0).to_numpy(dtype="int64")
        for h in range(1, FAST_MAX_BARS + 1)
    ]

    pnl = np.zeros(len(d), dtype=float)
    exitts = np.zeros(len(d), dtype="int64")
    dur = np.ones(len(d), dtype=int)
    reason = np.full(len(d), "timeout", dtype=object)

    rem = np.ones(len(d), dtype=bool)
    for h in range(1, int(max_hold_bars) + 1):
        ph = pnl_steps[h - 1]
        tsh = ts_steps[h - 1]
        tp = rem & (ph >= float(target_bps))
        sl = rem & (ph <= -float(stop_bps))

        pnl[tp] = ph[tp]
        exitts[tp] = tsh[tp]
        dur[tp] = h
        reason[tp] = "tp"

        pnl[sl] = ph[sl]
        exitts[sl] = tsh[sl]
        dur[sl] = h
        reason[sl] = "sl"
        rem = rem & ~(tp | sl)

    if np.any(rem):
        h = int(max_hold_bars)
        ph = pnl_steps[h - 1]
        tsh = ts_steps[h - 1]
        pnl[rem] = ph[rem]
        exitts[rem] = tsh[rem]
        dur[rem] = h
        reason[rem] = f"timeout_{h}bar"

    d["pnl_bps"] = pnl
    d["exit_ts"] = exitts
    d["duration_bars"] = dur
    d["max_hold_bars"] = int(max_hold_bars)
    d["exit_reason"] = reason
    p1 = pnl_steps[0]
    p2 = pnl_steps[1] if FAST_MAX_BARS >= 2 else pnl_steps[0]
    p4 = np.maximum.reduce(pnl_steps[: min(FAST_MAX_BARS, 4)])
    d["hit_target_within_1bar"] = (p1 >= float(target_bps))
    d["hit_target_within_2bars"] = (np.maximum(p1, p2) >= float(target_bps))
    d["hit_target_within_4bars"] = (p4 >= float(target_bps))
    d["hit_target_within_maxhold"] = (d["exit_reason"].astype(str) == "tp")
    return d


def _feature_matrix(df: pd.DataFrame) -> pd.DataFrame:
    ts = pd.to_datetime(df["timestamp"], unit="ns", utc=True)
    num = pd.DataFrame(
        {
            "abs_z": df["z_score"].abs().astype(float),
            "z_velocity": pd.to_numeric(df["z_velocity"], errors="coerce").astype(float),
            "z_accel": pd.to_numeric(df["z_accel"], errors="coerce").astype(float),
            "rolling_win_rate_10": pd.to_numeric(df["rolling_win_rate_10"], errors="coerce").astype(float),
            "rolling_avg_pnl_10": pd.to_numeric(df["rolling_avg_pnl_10"], errors="coerce").astype(float),
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
            "kf_abs_z": pd.to_numeric(df.get("kf_abs_z", 0.0), errors="coerce").astype(float),
            "kf_innov": pd.to_numeric(df.get("kf_innov", 0.0), errors="coerce").astype(float),
            "kf_innov_std": pd.to_numeric(df.get("kf_innov_std", 0.0), errors="coerce").astype(float),
            "kf_robust_z": pd.to_numeric(df.get("kf_robust_z", 0.0), errors="coerce").astype(float),
            "kf_student_loglik": pd.to_numeric(df.get("kf_student_loglik", 0.0), errors="coerce").astype(float),
            "kf_tod_scale": pd.to_numeric(df.get("kf_tod_scale", 1.0), errors="coerce").astype(float),
            "kf_huber_weight": pd.to_numeric(df.get("kf_huber_weight", 1.0), errors="coerce").astype(float),
            "kf_jump_prob": pd.to_numeric(df.get("kf_jump_prob", 0.0), errors="coerce").astype(float),
            "kf_z_vel": pd.to_numeric(df.get("kf_z_vel", 0.0), errors="coerce").astype(float),
            "kf_z_accel": pd.to_numeric(df.get("kf_z_accel", 0.0), errors="coerce").astype(float),
            "m5_kf_abs_z": pd.to_numeric(df.get("m5_kf_abs_z", 0.0), errors="coerce").astype(float),
            "m5_kf_robust_z": pd.to_numeric(df.get("m5_kf_robust_z", 0.0), errors="coerce").astype(float),
            "m5_kf_student_loglik": pd.to_numeric(df.get("m5_kf_student_loglik", 0.0), errors="coerce").astype(float),
            "m5_kf_tod_scale": pd.to_numeric(df.get("m5_kf_tod_scale", 1.0), errors="coerce").astype(float),
            "m5_kf_jump_prob": pd.to_numeric(df.get("m5_kf_jump_prob", 0.0), errors="coerce").astype(float),
            "m5_kf_z_vel": pd.to_numeric(df.get("m5_kf_z_vel", 0.0), errors="coerce").astype(float),
            "m5_kf_z_accel": pd.to_numeric(df.get("m5_kf_z_accel", 0.0), errors="coerce").astype(float),
            "m60_kf_abs_z": pd.to_numeric(df.get("m60_kf_abs_z", 0.0), errors="coerce").astype(float),
            "m60_kf_robust_z": pd.to_numeric(df.get("m60_kf_robust_z", 0.0), errors="coerce").astype(float),
            "m60_kf_student_loglik": pd.to_numeric(df.get("m60_kf_student_loglik", 0.0), errors="coerce").astype(float),
            "m60_kf_tod_scale": pd.to_numeric(df.get("m60_kf_tod_scale", 1.0), errors="coerce").astype(float),
            "m60_kf_jump_prob": pd.to_numeric(df.get("m60_kf_jump_prob", 0.0), errors="coerce").astype(float),
            "m60_kf_z_vel": pd.to_numeric(df.get("m60_kf_z_vel", 0.0), errors="coerce").astype(float),
            "m60_kf_z_accel": pd.to_numeric(df.get("m60_kf_z_accel", 0.0), errors="coerce").astype(float),
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
    return pd.concat([num, pd.get_dummies(cat, drop_first=False, dtype=float)], axis=1).fillna(0.0)


def _pair_filter_set(train_guard_df: pd.DataFrame, cutoff: float) -> set[str]:
    if train_guard_df.empty:
        return set()
    keep: set[str] = set()
    for pair, sub in train_guard_df.groupby("pair", sort=True):
        pnl = sub["pnl_bps"].to_numpy(dtype=float)
        if len(pnl) < 40:
            continue
        sd = float(np.std(pnl, ddof=1)) if len(pnl) > 1 else 0.0
        sh = float(np.mean(pnl) / sd * np.sqrt(252.0)) if sd > 1e-12 else 0.0
        if sh >= cutoff:
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
    cagr = -1.0 if 1.0 + total_return <= 0.0 else float((1.0 + total_return) ** (365.25 / days) - 1.0)

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


def _time_ordered_split(df: pd.DataFrame, labeled_mask: pd.Series, calibration_frac: float) -> tuple[pd.Series, pd.Series]:
    cf = float(np.clip(calibration_frac, 0.0, 0.5))
    idx = df.index[labeled_mask].to_numpy()
    if len(idx) < 250:
        return labeled_mask.copy(), pd.Series(False, index=df.index)

    ordered = df.loc[idx].sort_values(["timestamp", "exit_ts"]).index.to_numpy()
    cut = int(round(len(ordered) * (1.0 - cf)))
    cut = max(80, min(cut, len(ordered) - 80))
    tr = set(ordered[:cut].tolist())
    cal = set(ordered[cut:].tolist())
    tr_mask = df.index.to_series().isin(tr)
    cal_mask = df.index.to_series().isin(cal)
    return tr_mask, cal_mask


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


def _fit_model_with_calibration(
    tr_df: pd.DataFrame,
    te_df: pd.DataFrame,
    X_all: pd.DataFrame,
    y_tr: pd.Series,
    enable_calibration: bool,
    calibration_method: str,
    calibration_frac: float,
    random_state: int,
) -> dict:
    tr_idx = tr_df.index
    te_idx = te_df.index
    X_tr = X_all.loc[tr_idx]
    X_te = X_all.loc[te_idx]

    labeled = y_tr.notna()
    if int(labeled.sum()) < 200:
        raise RuntimeError("Not enough labeled rows for model fit")

    tr_mask, cal_mask = _time_ordered_split(tr_df, labeled, calibration_frac=calibration_frac)
    if len(np.unique(y_tr.loc[tr_mask].astype(int).to_numpy())) < 2:
        tr_mask = labeled.copy()
        cal_mask = pd.Series(False, index=tr_df.index)

    model = HistGradientBoostingClassifier(
        max_depth=4,
        learning_rate=0.05,
        max_iter=350,
        min_samples_leaf=80,
        random_state=int(random_state),
    )
    model.fit(X_tr.loc[tr_mask], y_tr.loc[tr_mask].astype(int))

    p_raw_tr = model.predict_proba(X_tr)[:, 1].astype(float)
    p_raw_te = model.predict_proba(X_te)[:, 1].astype(float)
    p_cal_tr = p_raw_tr.copy()
    p_cal_te = p_raw_te.copy()

    cal = {
        "effective_method": "none",
        "n_train_model": int(tr_mask.sum()),
        "n_train_cal": int(cal_mask.sum()),
        "brier_raw": np.nan,
        "brier_cal": np.nan,
        "logloss_raw": np.nan,
        "logloss_cal": np.nan,
    }
    if enable_calibration and calibration_method != "none" and int(cal_mask.sum()) >= 100:
        y_cal = y_tr.loc[cal_mask].astype(int).to_numpy()
        p_raw_cal = p_raw_tr[cal_mask.to_numpy()]
        calibrator, meta = _fit_calibrator(calibration_method, p_raw_cal=p_raw_cal, y_cal=y_cal)
        p_cal_tr = calibrator(p_raw_tr)
        p_cal_te = calibrator(p_raw_te)
        p_cal_cal = calibrator(p_raw_cal)
        cal.update(
            {
                "effective_method": meta.get("effective_method", "none"),
                "brier_raw": float(brier_score_loss(y_cal, np.clip(p_raw_cal, 1e-6, 1 - 1e-6))),
                "brier_cal": float(brier_score_loss(y_cal, np.clip(p_cal_cal, 1e-6, 1 - 1e-6))),
                "logloss_raw": float(log_loss(y_cal, np.clip(p_raw_cal, 1e-6, 1 - 1e-6))),
                "logloss_cal": float(log_loss(y_cal, np.clip(p_cal_cal, 1e-6, 1 - 1e-6))),
            }
        )

    return {
        "proba_raw_tr": pd.Series(np.clip(p_raw_tr, 0.0, 1.0), index=tr_df.index),
        "proba_raw_te": pd.Series(np.clip(p_raw_te, 0.0, 1.0), index=te_df.index),
        "proba_cal_tr": pd.Series(np.clip(p_cal_tr, 0.0, 1.0), index=tr_df.index),
        "proba_cal_te": pd.Series(np.clip(p_cal_te, 0.0, 1.0), index=te_df.index),
        "calib_info": cal,
    }


def _threshold_pairs(grid: list[float], enable_half_size: bool) -> list[tuple[float, float]]:
    if not enable_half_size:
        return [(float(t), float(t)) for t in grid]
    out: list[tuple[float, float]] = []
    for t1 in grid:
        for t2 in grid:
            if t2 >= t1:
                out.append((float(t1), float(t2)))
    return out


def _gate_short(short_df: pd.DataFrame, proba_bad: pd.Series, t1: float, t2: float, enable_half_size: bool) -> tuple[pd.DataFrame, pd.DataFrame]:
    d = short_df.copy()
    p = proba_bad.reindex(d.index).fillna(1.0).to_numpy(dtype=float)
    if enable_half_size:
        action = np.where(p <= t1, "keep_full", np.where(p <= t2, "keep_half", "skip"))
        mult = np.where(p <= t1, 1.0, np.where(p <= t2, 0.5, 0.0))
    else:
        action = np.where(p <= t1, "keep_full", "skip")
        mult = np.where(p <= t1, 1.0, 0.0)

    d["p_bad_2bar"] = p
    d["cluster_gate_action"] = action
    d["size_mult"] = mult.astype(float)

    kept = d[d["size_mult"] > 0.0].copy()
    kept["pnl_bps"] = kept["pnl_bps"].astype(float) * kept["size_mult"].astype(float)
    return kept, d


def _eval_variant(short_kept: pd.DataFrame, long_df: pd.DataFrame, risk_bps: float, pair_keep: set[str] | None) -> tuple[pd.DataFrame, dict[str, float]]:
    pre = pd.concat([short_kept, long_df], ignore_index=True).sort_values(["timestamp", "pair"]).reset_index(drop=True)
    guard = _apply_guardrail(pre)
    if pair_keep is not None and len(pair_keep):
        guard = guard[guard["pair"].astype(str).isin(pair_keep)].copy().reset_index(drop=True)
    m = _metrics_with_risk(guard, risk_bps=risk_bps)
    return guard, m


def _norm01(series: pd.Series) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce").astype(float)
    lo = float(s.min())
    hi = float(s.max())
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return pd.Series(np.full(len(s), 0.5, dtype=float), index=s.index)
    return (s - lo) / (hi - lo)


def _select_train_policy(
    train_short_base: pd.DataFrame,
    train_long: pd.DataFrame,
    proba_bad_train: pd.Series,
    threshold_grid: list[float],
    pair_keep_fixed: set[str],
    risk_bps: float,
    min_mean_bps: float,
    min_trade_frac: float,
    retain_annualized_frac: float,
    min_tim_reduction_pct: float,
    single_day_tol_bps: float,
    enable_half_size: bool,
    train_mc_paths: int,
    train_mc_block_days: int,
    random_state: int,
    strict_hard_promotion: bool,
) -> tuple[float, float, pd.DataFrame, dict[str, float]]:
    base_short = train_short_base.copy()
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
        kept, _ = _gate_short(train_short_base, proba_bad_train, t1=t1, t2=t2, enable_half_size=enable_half_size)
        guard, m = _eval_variant(kept, train_long, risk_bps=risk_bps, pair_keep=pair_keep_fixed)

        mc = _block_bootstrap_daily(
            guard,
            n_paths=max(60, int(train_mc_paths)),
            block_days=max(1, int(train_mc_block_days)),
            seed=int(random_state + round((t1 + t2) * 1000)),
        )
        cand_mc_p95_single_day_loss = (
            float(np.percentile(mc["single_day_loss_bps"].to_numpy(dtype=float), 95)) if not mc.empty else np.inf
        )

        mean_pass = float(m["mean_pnl_per_trade_bps"]) >= float(min_mean_bps)
        trade_pass = float(m["trades"]) >= float(min_trade_frac) * float(base_m["trades"])
        ann_pass = float(m["annualized_bps_calendar"]) >= float(retain_annualized_frac) * float(base_m["annualized_bps_calendar"])
        tim_pass = float(m["time_in_market_pct"]) <= float(base_m["time_in_market_pct"]) * (1.0 - float(min_tim_reduction_pct) / 100.0)
        dd_pass = float(m["worst_single_day_bps"]) >= float(base_m["worst_single_day_bps"]) - float(single_day_tol_bps)
        mc_pass = float(cand_mc_p95_single_day_loss) <= float(base_mc_p95_single_day_loss)

        hard_pass = bool(mean_pass and trade_pass and ann_pass and tim_pass and dd_pass and mc_pass)
        eligible = bool(trade_pass and ann_pass)

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
                "time_in_market_pct": float(m["time_in_market_pct"]),
                "avg_trade_duration_bars": float(m["avg_trade_duration_bars"]),
                "mc_p95_single_day_loss_bps": float(cand_mc_p95_single_day_loss),
                "base_mc_p95_single_day_loss_bps": float(base_mc_p95_single_day_loss),
                "mean_pass": bool(mean_pass),
                "trade_pass": bool(trade_pass),
                "ann_pass": bool(ann_pass),
                "tim_pass": bool(tim_pass),
                "dd_pass": bool(dd_pass),
                "mc_pass": bool(mc_pass),
                "hard_pass": bool(hard_pass),
                "eligible": bool(eligible),
            }
        )

    grid = pd.DataFrame(rows)
    tim_reduction = float(base_m["time_in_market_pct"]) - pd.to_numeric(grid["time_in_market_pct"], errors="coerce").astype(float)
    dd_improvement = pd.to_numeric(grid["worst_single_day_bps"], errors="coerce").astype(float) - float(base_m["worst_single_day_bps"])
    grid["score"] = (
        0.40 * _norm01(grid["mean_pnl_per_trade_bps"])
        + 0.30 * _norm01(tim_reduction)
        + 0.20 * _norm01(grid["sharpe"])
        + 0.10 * _norm01(grid["worst_single_day_bps"])
    )
    grid["tim_reduction_better"] = tim_reduction.astype(float)
    grid["dd_improvement_better"] = dd_improvement.astype(float)

    hard = grid[grid["hard_pass"]].copy()
    forced_passthrough = False
    if not hard.empty:
        cand = hard
        fallback_reason = ""
    else:
        if bool(strict_hard_promotion):
            cand = grid[grid["eligible"]].copy()
            if cand.empty:
                cand = grid.copy()
                forced_passthrough = True
            fallback_reason = "hard_gates_unmet_strict"
        else:
            cand = grid[grid["eligible"]].copy()
            if cand.empty:
                cand = grid.copy()
            fallback_reason = "hard_gates_unmet"

    if forced_passthrough:
        chosen = pd.Series(
            {
                "t1": 1.0,
                "t2": 1.0,
                "trades": int(base_m["trades"]),
                "mean_pnl_per_trade_bps": float(base_m["mean_pnl_per_trade_bps"]),
                "sharpe": float(base_m["sharpe"]),
                "annualized_bps_calendar": float(base_m["annualized_bps_calendar"]),
                "worst_single_day_bps": float(base_m["worst_single_day_bps"]),
                "max_daily_dd_bps": float(base_m["max_daily_dd_bps"]),
                "time_in_market_pct": float(base_m["time_in_market_pct"]),
                "avg_trade_duration_bars": float(base_m["avg_trade_duration_bars"]),
                "mc_p95_single_day_loss_bps": float(base_mc_p95_single_day_loss),
                "base_mc_p95_single_day_loss_bps": float(base_mc_p95_single_day_loss),
                "mean_pass": bool(float(base_m["mean_pnl_per_trade_bps"]) >= float(min_mean_bps)),
                "trade_pass": True,
                "ann_pass": True,
                "tim_pass": True,
                "dd_pass": True,
                "mc_pass": True,
                "hard_pass": False,
                "eligible": True,
                "score": 0.0,
                "tim_reduction_better": 0.0,
                "dd_improvement_better": 0.0,
            }
        )
        grid = pd.concat([grid, pd.DataFrame([chosen.to_dict()])], ignore_index=True)
        fallback_reason = "hard_gates_unmet_strict_passthrough"
    else:
        chosen = cand.sort_values(
            ["hard_pass", "tim_reduction_better", "dd_improvement_better", "mean_pnl_per_trade_bps", "sharpe", "score"],
            ascending=[False, False, False, False, False, False],
        ).iloc[0]

    meta = {
        "fallback_reason": fallback_reason,
        "selected_hard_pass": bool(chosen["hard_pass"]),
        "base_trades": int(base_m["trades"]),
        "base_mean_pnl_per_trade_bps": float(base_m["mean_pnl_per_trade_bps"]),
        "base_annualized_bps_calendar": float(base_m["annualized_bps_calendar"]),
        "base_time_in_market_pct": float(base_m["time_in_market_pct"]),
        "base_worst_single_day_bps": float(base_m["worst_single_day_bps"]),
        "base_max_daily_dd_bps": float(base_m["max_daily_dd_bps"]),
        "base_mc_p95_single_day_loss_bps": float(base_mc_p95_single_day_loss),
    }
    return float(chosen["t1"]), float(chosen["t2"]), grid, meta


def main() -> None:
    p = argparse.ArgumentParser(description="Fast-hold robust-KF/meta WFO (1-2 bar exits)")
    p.add_argument("--exclude-oil", action="store_true", default=True)
    p.add_argument("--mixes", default="m5=MOM,m15=MOM+REV,m60=REV")
    p.add_argument("--decision-clock", default="m15", choices=["m15", "m5"])
    p.add_argument("--m60-features-only", action="store_true", default=True)
    p.add_argument("--start-test-year", type=int, default=2020)
    p.add_argument("--end-test-year", type=int, default=2025)
    p.add_argument("--embargo-days", type=int, default=5)
    p.add_argument("--pair-sharpe-cutoff", type=float, default=0.30)

    p.add_argument("--enable-fast-exit-mode", action="store_true", default=True)
    p.add_argument("--target-bps", type=float, default=5.0)
    p.add_argument("--stop-bps-grid", default="5.0,7.5,10.0")
    p.add_argument("--max-hold-bars", type=int, default=4)
    p.add_argument("--horizons", default="1,2,3,4")

    p.add_argument("--enable-calibration", action="store_true", default=True)
    p.add_argument("--calibration-method", default="isotonic", choices=["isotonic", "platt", "none"])
    p.add_argument("--calibration-frac", type=float, default=0.20)

    p.add_argument("--threshold-grid", default="0.05,0.10,0.15,0.20,0.25,0.30,0.35,0.40")
    p.add_argument("--enable-half-size", action="store_true", default=True)
    p.add_argument("--outlier-gate-mode", default="or", choices=["or", "and", "none"])
    p.add_argument("--outlier-z-threshold-m5", type=float, default=2.5)
    p.add_argument("--outlier-z-threshold-m15", type=float, default=2.5)
    p.add_argument("--strict-hard-promotion", action="store_true", default=True)

    p.add_argument("--min-mean-bps", type=float, default=5.0)
    p.add_argument("--min-trade-frac", type=float, default=0.35)
    p.add_argument("--retain-annualized-frac", type=float, default=0.70)
    p.add_argument("--min-time-in-market-reduction-pct", type=float, default=10.0)
    p.add_argument("--single-day-tol-bps", type=float, default=0.0)

    p.add_argument("--train-mc-paths", type=int, default=150)
    p.add_argument("--train-mc-block-days", type=int, default=20)
    p.add_argument("--mc-paths", type=int, default=1000)
    p.add_argument("--mc-block-days", type=int, default=20)

    p.add_argument("--random-state", type=int, default=42)
    p.add_argument("--out-prefix", default="meta_pf_outlier_fast_m15")

    p.add_argument("--feature-stack", default="robust_kf", choices=["cluster", "robust_kf", "both"])
    p.add_argument("--robust-student-df", type=float, default=5.0)
    p.add_argument("--robust-huber-c", type=float, default=2.5)
    p.add_argument("--robust-ew-alpha", type=float, default=0.04)
    p.add_argument("--robust-tod-alpha", type=float, default=0.05)
    p.add_argument("--robust-jump-prior", type=float, default=0.04)
    p.add_argument("--robust-jump-var-mult", type=float, default=9.0)
    args = p.parse_args()

    if int(args.max_hold_bars) < 1 or int(args.max_hold_bars) > FAST_MAX_BARS:
        raise ValueError(f"--max-hold-bars must be within [1,{FAST_MAX_BARS}]")

    horizons = [int(x.strip()) for x in str(args.horizons).split(",") if x.strip()]
    if any(h < 1 or h > FAST_MAX_BARS for h in horizons):
        raise ValueError(f"--horizons supports only 1..{FAST_MAX_BARS}")

    pair_whitelist = list(PAIR_WHITELIST_BASE)
    if args.exclude_oil:
        pair_whitelist = [x for x in pair_whitelist if x not in OIL_LINKED_PAIRS]

    mixes = _parse_strategy_mixes(args.mixes)
    threshold_grid = _parse_grid(args.threshold_grid)
    stop_grid = _parse_grid(args.stop_bps_grid)
    folds = _make_folds(args.start_test_year, args.end_test_year, args.embargo_days)

    print(f"Building state cache for fast 1-{FAST_MAX_BARS} bar repricing + robust-KF context...")
    state_cache = {
        "m5": _build_pair_states("m5", pair_whitelist),
        "m15": _build_pair_states("m15", pair_whitelist),
        "m60": _build_pair_states_m60(pair_whitelist),
    }

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
    scored_rows: list[pd.DataFrame] = []
    calibration_rows: list[dict] = []

    oos_base_rows: list[pd.DataFrame] = []
    oos_cand_rows: list[pd.DataFrame] = []
    oos_prom_rows: list[pd.DataFrame] = []

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

        decision_tf = str(args.decision_clock).lower()
        short_all = loaded[decision_tf].reset_index(drop=True)
        long_all = _empty_events_frame()
        if not bool(args.m60_features_only):
            long_all = loaded["m60"].reset_index(drop=True)
        has_long_leg = (not bool(args.m60_features_only)) and (str(mix["m60"]).upper() != "NONE")
        if short_all.empty or (has_long_leg and long_all.empty):
            print("  skip mix: empty short dataset or empty required long dataset")
            continue

        short_all["trade_id"] = np.arange(len(short_all), dtype=np.int64)
        short_all["mix_id"] = mix_name
        long_all["trade_id"] = -1
        long_all["mix_id"] = mix_name

        short_all = _attach_fast_path_columns(short_all, state_cache)
        if args.feature_stack in {"cluster", "both"}:
            short_all = add_cluster_state_features(short_all)
        else:
            # Keep schema stable for `_feature_matrix` when cluster features are disabled.
            short_all["realized_loss_streak_3"] = 0.0
            short_all["realized_pnl_sum_5"] = 0.0
            short_all["realized_pnl_sum_10"] = 0.0
            short_all["realized_pnl_sum_20"] = 0.0
            short_all["realized_dd_from_local_peak_20"] = 0.0
            short_all["trade_arrival_rate_1d"] = 0.0
            short_all["trade_arrival_rate_3d"] = 0.0
            short_all["recent_vol_proxy_20"] = 0.0
            short_all["session_loss_rate_20"] = 0.0

        if args.feature_stack in {"robust_kf", "both"}:
            short_all = add_robust_kf_features(
                short_all,
                state_cache=state_cache,
                student_df=float(args.robust_student_df),
                huber_c=float(args.robust_huber_c),
                ew_alpha=float(args.robust_ew_alpha),
                tod_alpha=float(args.robust_tod_alpha),
                jump_prior=float(args.robust_jump_prior),
                jump_var_mult=float(args.robust_jump_var_mult),
            )
            short_all = _attach_context_robust_features(short_all, robust_lookup, source_tf="m5", prefix="m5")
            short_all = _attach_context_robust_features(short_all, robust_lookup, source_tf="m60", prefix="m60")
        else:
            short_all["kf_abs_z"] = 0.0
            short_all["kf_innov"] = 0.0
            short_all["kf_innov_std"] = 1.0
            short_all["kf_robust_z"] = 0.0
            short_all["kf_student_loglik"] = 0.0
            short_all["kf_tod_scale"] = 1.0
            short_all["kf_huber_weight"] = 1.0
            short_all["kf_jump_prob"] = 0.0
            short_all["m5_kf_abs_z"] = 0.0
            short_all["m5_kf_robust_z"] = 0.0
            short_all["m5_kf_student_loglik"] = 0.0
            short_all["m5_kf_tod_scale"] = 1.0
            short_all["m5_kf_jump_prob"] = 0.0
            short_all["m60_kf_abs_z"] = 0.0
            short_all["m60_kf_robust_z"] = 0.0
            short_all["m60_kf_student_loglik"] = 0.0
            short_all["m60_kf_tod_scale"] = 1.0
            short_all["m60_kf_jump_prob"] = 0.0

        short_all = _apply_outlier_candidate_gate(
            short_all,
            gate_mode=str(args.outlier_gate_mode),
            z_thr_m5=float(args.outlier_z_threshold_m5),
            z_thr_m15=float(args.outlier_z_threshold_m15),
        )
        X_all = _feature_matrix(short_all)

        risk_bps = _derive_risk_bps(pd.concat([short_all, long_all], ignore_index=True), fallback=100.0)
        print(f"  loaded short={len(short_all)} long={len(long_all)} risk_bps={risk_bps:.2f}")

        for fold in folds:
            print(f"\n  Fold {fold.test_year}:")
            tr_short_base_full = short_all[short_all["timestamp"] < fold.train_end_ts_ns].copy()
            te_short_base_full = short_all[
                (short_all["timestamp"] >= fold.test_start_ts_ns) & (short_all["timestamp"] < fold.test_end_ts_ns)
            ].copy()
            tr_long = long_all[long_all["timestamp"] < fold.train_end_ts_ns].copy()
            te_long = long_all[
                (long_all["timestamp"] >= fold.test_start_ts_ns) & (long_all["timestamp"] < fold.test_end_ts_ns)
            ].copy()

            tr_short_base = tr_short_base_full[tr_short_base_full["candidate_gate_hit"]].copy()
            te_short_base = te_short_base_full[te_short_base_full["candidate_gate_hit"]].copy()
            if len(tr_short_base) < 1200 or te_short_base.empty:
                print("    skip: insufficient train/test short trades")
                continue

            best = None
            stop_ablation = []

            for stop_bps in stop_grid:
                tr_short = _apply_fast_exit_contract(
                    tr_short_base,
                    target_bps=float(args.target_bps),
                    stop_bps=float(stop_bps),
                    max_hold_bars=int(args.max_hold_bars),
                )
                te_short = _apply_fast_exit_contract(
                    te_short_base,
                    target_bps=float(args.target_bps),
                    stop_bps=float(stop_bps),
                    max_hold_bars=int(args.max_hold_bars),
                )

                # primary label: TP before SL/timeout within max_hold (<=2 bars)
                y2_tr = pd.Series((tr_short["exit_reason"].astype(str) == "tp").astype(int), index=tr_short.index)
                # secondary short horizon label
                y1_tr = pd.Series((pd.to_numeric(tr_short["fast_pnl_1"], errors="coerce") >= float(args.target_bps)).astype(int), index=tr_short.index)

                if int(y2_tr.sum()) < 100 or int((1 - y2_tr).sum()) < 100:
                    continue

                fit2 = _fit_model_with_calibration(
                    tr_df=tr_short,
                    te_df=te_short,
                    X_all=X_all,
                    y_tr=y2_tr,
                    enable_calibration=bool(args.enable_calibration),
                    calibration_method=args.calibration_method,
                    calibration_frac=float(args.calibration_frac),
                    random_state=int(args.random_state + fold.test_year + round(stop_bps * 100)),
                )

                # Optional 1-bar head for diagnostics
                fit1 = _fit_model_with_calibration(
                    tr_df=tr_short,
                    te_df=te_short,
                    X_all=X_all,
                    y_tr=y1_tr,
                    enable_calibration=bool(args.enable_calibration),
                    calibration_method=args.calibration_method,
                    calibration_frac=float(args.calibration_frac),
                    random_state=int(args.random_state + 1000 + fold.test_year + round(stop_bps * 100)),
                )

                base_tr_short = tr_short.copy()
                base_tr_short["cluster_gate_action"] = "keep_full"
                base_tr_short["size_mult"] = 1.0
                base_tr_guard, _ = _eval_variant(base_tr_short, tr_long, risk_bps=risk_bps, pair_keep=None)
                pair_keep = _pair_filter_set(base_tr_guard, cutoff=float(args.pair_sharpe_cutoff))

                t1, t2, tgrid, meta = _select_train_policy(
                    train_short_base=tr_short,
                    train_long=tr_long,
                    proba_bad_train=(1.0 - fit2["proba_cal_tr"]),
                    threshold_grid=threshold_grid,
                    pair_keep_fixed=pair_keep,
                    risk_bps=risk_bps,
                    min_mean_bps=float(args.min_mean_bps),
                    min_trade_frac=float(args.min_trade_frac),
                    retain_annualized_frac=float(args.retain_annualized_frac),
                    min_tim_reduction_pct=float(args.min_time_in_market_reduction_pct),
                    single_day_tol_bps=float(args.single_day_tol_bps),
                    enable_half_size=bool(args.enable_half_size),
                    train_mc_paths=int(args.train_mc_paths),
                    train_mc_block_days=int(args.train_mc_block_days),
                    random_state=int(args.random_state + fold.test_year + round(stop_bps * 100)),
                    strict_hard_promotion=bool(args.strict_hard_promotion),
                )

                g = tgrid.copy()
                g["mix_id"] = mix_name
                g["fold_year"] = int(fold.test_year)
                g["stop_bps"] = float(stop_bps)
                grid_rows.append(g)

                chosen = g[(np.isclose(g["t1"], t1)) & (np.isclose(g["t2"], t2))].head(1)
                if chosen.empty:
                    continue
                r = chosen.iloc[0]
                rank = (
                    int(bool(r["hard_pass"])),
                    float(r["score"]),
                    float(r["mean_pnl_per_trade_bps"]),
                    float(r["sharpe"]),
                )

                stop_ablation.append(
                    {
                        "mix_id": mix_name,
                        "year": int(fold.test_year),
                        "stop_bps": float(stop_bps),
                        "t1": float(t1),
                        "t2": float(t2),
                        "score": float(r["score"]),
                        "hard_pass": bool(r["hard_pass"]),
                        "mean_pnl_per_trade_bps": float(r["mean_pnl_per_trade_bps"]),
                        "sharpe": float(r["sharpe"]),
                        "annualized_bps_calendar": float(r["annualized_bps_calendar"]),
                        "worst_single_day_bps": float(r["worst_single_day_bps"]),
                        "time_in_market_pct": float(r["time_in_market_pct"]),
                        "fallback_reason": str(meta.get("fallback_reason", "")),
                    }
                )

                if best is None or rank > best["rank"]:
                    best = {
                        "rank": rank,
                        "stop_bps": float(stop_bps),
                        "t1": float(t1),
                        "t2": float(t2),
                        "fit2": fit2,
                        "fit1": fit1,
                        "meta": meta,
                        "pair_keep": pair_keep,
                    }

            if best is None:
                print("    skip: no viable stop/threshold policy")
                continue

            tr_short = _apply_fast_exit_contract(
                tr_short_base,
                target_bps=float(args.target_bps),
                stop_bps=float(best["stop_bps"]),
                max_hold_bars=int(args.max_hold_bars),
            )
            te_short = _apply_fast_exit_contract(
                te_short_base,
                target_bps=float(args.target_bps),
                stop_bps=float(best["stop_bps"]),
                max_hold_bars=int(args.max_hold_bars),
            )
            te_short_all = _apply_fast_exit_contract(
                te_short_base_full,
                target_bps=float(args.target_bps),
                stop_bps=float(best["stop_bps"]),
                max_hold_bars=int(args.max_hold_bars),
            )

            base_te_short = te_short.copy()
            base_te_short["cluster_gate_action"] = "keep_full"
            base_te_short["size_mult"] = 1.0
            base_guard, m_base = _eval_variant(base_te_short, te_long, risk_bps=risk_bps, pair_keep=best["pair_keep"])

            cand_short_kept, cand_scored_cand = _gate_short(
                te_short,
                (1.0 - best["fit2"]["proba_cal_te"]),
                t1=float(best["t1"]),
                t2=float(best["t2"]),
                enable_half_size=bool(args.enable_half_size),
            )
            te_non = te_short_all[~te_short_all["candidate_gate_hit"]].copy()
            te_non["cluster_gate_action"] = "skip_outlier_gate"
            te_non["size_mult"] = 0.0
            te_non["p_bad_2bar"] = 1.0
            cand_scored = (
                pd.concat([cand_scored_cand, te_non], ignore_index=False)
                .sort_values(["timestamp", "pair", "trade_id"])
                .reset_index(drop=True)
            )
            cand_guard, m_cand = _eval_variant(cand_short_kept, te_long, risk_bps=risk_bps, pair_keep=best["pair_keep"])

            mc_base = _block_bootstrap_daily(
                base_guard,
                n_paths=max(80, int(args.train_mc_paths)),
                block_days=max(1, int(args.train_mc_block_days)),
                seed=int(args.random_state + 111 + fold.test_year),
            )
            mc_cand = _block_bootstrap_daily(
                cand_guard,
                n_paths=max(80, int(args.train_mc_paths)),
                block_days=max(1, int(args.train_mc_block_days)),
                seed=int(args.random_state + 211 + fold.test_year),
            )
            base_mc_p95 = float(np.percentile(mc_base["single_day_loss_bps"].to_numpy(dtype=float), 95)) if not mc_base.empty else np.inf
            cand_mc_p95 = float(np.percentile(mc_cand["single_day_loss_bps"].to_numpy(dtype=float), 95)) if not mc_cand.empty else np.inf

            oos_mean_pass = float(m_cand["mean_pnl_per_trade_bps"]) >= float(args.min_mean_bps)
            oos_trade_pass = float(m_cand["trades"]) >= float(args.min_trade_frac) * float(m_base["trades"])
            oos_ann_pass = float(m_cand["annualized_bps_calendar"]) >= float(args.retain_annualized_frac) * float(m_base["annualized_bps_calendar"])
            oos_tim_pass = float(m_cand["time_in_market_pct"]) <= float(m_base["time_in_market_pct"]) * (1.0 - float(args.min_time_in_market_reduction_pct) / 100.0)
            oos_dd_pass = float(m_cand["worst_single_day_bps"]) >= float(m_base["worst_single_day_bps"]) - float(args.single_day_tol_bps)
            oos_mc_pass = float(cand_mc_p95) <= float(base_mc_p95)
            oos_hard = bool(oos_mean_pass and oos_trade_pass and oos_ann_pass and oos_tim_pass and oos_dd_pass and oos_mc_pass)
            promote_on_fold = bool(oos_hard) if bool(args.strict_hard_promotion) else True
            prom_guard = cand_guard.copy() if promote_on_fold else base_guard.copy()
            m_prom = _metrics_with_risk(prom_guard, risk_bps=risk_bps)

            y2_te = (te_short["exit_reason"].astype(str) == "tp").astype(int)
            y1_te = (pd.to_numeric(te_short["fast_pnl_1"], errors="coerce") >= float(args.target_bps)).astype(int)
            pred_hi = cand_scored_cand["cluster_gate_action"].astype(str).isin(["skip", "keep_half"]).to_numpy()
            pos2_bad = y2_te.to_numpy(dtype=int) == 0
            precision2 = float(np.sum(pred_hi & pos2_bad) / max(np.sum(pred_hi), 1)) if np.sum(pred_hi) else 0.0
            recall2 = float(np.sum(pred_hi & pos2_bad) / max(np.sum(pos2_bad), 1)) if np.sum(pos2_bad) else 0.0

            fold_rows.append(
                {
                    "mix_id": mix_name,
                    "year": int(fold.test_year),
                    "target_bps": float(args.target_bps),
                    "stop_bps": float(best["stop_bps"]),
                    "max_hold_bars": int(args.max_hold_bars),
                    "t1": float(best["t1"]),
                    "t2": float(best["t2"]),
                    "selection_objective": "fast_dd_time_market",
                    "threshold_policy": "train_only",
                    "feature_stack": str(args.feature_stack),
                    "decision_clock": str(args.decision_clock),
                    "outlier_gate_mode": str(args.outlier_gate_mode),
                    "fallback_reason": str(best["meta"].get("fallback_reason", "")),
                    "candidate_gate_train_frac": float(tr_short_base_full["candidate_gate_hit"].mean()) if len(tr_short_base_full) else 0.0,
                    "candidate_gate_test_frac": float(te_short_base_full["candidate_gate_hit"].mean()) if len(te_short_base_full) else 0.0,
                    "cluster_precision_2bar": float(precision2),
                    "cluster_recall_2bar": float(recall2),
                    "base_trades": int(m_base["trades"]),
                    "base_mean_pnl_per_trade_bps": float(m_base["mean_pnl_per_trade_bps"]),
                    "base_sharpe": float(m_base["sharpe"]),
                    "base_annualized_bps_calendar": float(m_base["annualized_bps_calendar"]),
                    "base_worst_single_day_bps": float(m_base["worst_single_day_bps"]),
                    "base_max_daily_dd_bps": float(m_base["max_daily_dd_bps"]),
                    "base_time_in_market_pct": float(m_base["time_in_market_pct"]),
                    "base_avg_trade_duration_bars": float(m_base["avg_trade_duration_bars"]),
                    "candidate_trades": int(m_cand["trades"]),
                    "candidate_mean_pnl_per_trade_bps": float(m_cand["mean_pnl_per_trade_bps"]),
                    "candidate_sharpe": float(m_cand["sharpe"]),
                    "candidate_annualized_bps_calendar": float(m_cand["annualized_bps_calendar"]),
                    "candidate_worst_single_day_bps": float(m_cand["worst_single_day_bps"]),
                    "candidate_max_daily_dd_bps": float(m_cand["max_daily_dd_bps"]),
                    "candidate_time_in_market_pct": float(m_cand["time_in_market_pct"]),
                    "candidate_avg_trade_duration_bars": float(m_cand["avg_trade_duration_bars"]),
                    "delta_mean_bps": float(m_cand["mean_pnl_per_trade_bps"] - m_base["mean_pnl_per_trade_bps"]),
                    "delta_sharpe": float(m_cand["sharpe"] - m_base["sharpe"]),
                    "delta_annualized_bps_calendar": float(m_cand["annualized_bps_calendar"] - m_base["annualized_bps_calendar"]),
                    "delta_worst_single_day_bps": float(m_cand["worst_single_day_bps"] - m_base["worst_single_day_bps"]),
                    "delta_max_daily_dd_bps": float(m_cand["max_daily_dd_bps"] - m_base["max_daily_dd_bps"]),
                    "delta_time_in_market_pct": float(m_cand["time_in_market_pct"] - m_base["time_in_market_pct"]),
                    "mc_base_p95_single_day_loss_bps": float(base_mc_p95),
                    "mc_candidate_p95_single_day_loss_bps": float(cand_mc_p95),
                    "oos_mean_pass": bool(oos_mean_pass),
                    "oos_trade_pass": bool(oos_trade_pass),
                    "oos_ann_pass": bool(oos_ann_pass),
                    "oos_tim_pass": bool(oos_tim_pass),
                    "oos_dd_pass": bool(oos_dd_pass),
                    "oos_mc_pass": bool(oos_mc_pass),
                    "oos_hard_pass": bool(oos_hard),
                    "promoted_on_fold": bool(oos_hard) if bool(args.strict_hard_promotion) else True,
                }
            )

            calibration_rows.append(
                {
                    "mix_id": mix_name,
                    "year": int(fold.test_year),
                    "target_bps": float(args.target_bps),
                    "stop_bps": float(best["stop_bps"]),
                    "t1": float(best["t1"]),
                    "t2": float(best["t2"]),
                    "feature_stack": str(args.feature_stack),
                    "calibration_method_2bar": str(best["fit2"]["calib_info"]["effective_method"]),
                    "calibration_method_1bar": str(best["fit1"]["calib_info"]["effective_method"]),
                    "brier_2bar_raw": best["fit2"]["calib_info"]["brier_raw"],
                    "brier_2bar_cal": best["fit2"]["calib_info"]["brier_cal"],
                    "logloss_2bar_raw": best["fit2"]["calib_info"]["logloss_raw"],
                    "logloss_2bar_cal": best["fit2"]["calib_info"]["logloss_cal"],
                    "brier_1bar_raw": best["fit1"]["calib_info"]["brier_raw"],
                    "brier_1bar_cal": best["fit1"]["calib_info"]["brier_cal"],
                    "logloss_1bar_raw": best["fit1"]["calib_info"]["logloss_raw"],
                    "logloss_1bar_cal": best["fit1"]["calib_info"]["logloss_cal"],
                }
            )

            common = {
                "mix_id": mix_name,
                "fold_year": int(fold.test_year),
                "selection_objective": "fast_dd_time_market",
                "threshold_policy": "train_only",
                "feature_stack": str(args.feature_stack),
                "target_bps": float(args.target_bps),
                "stop_bps": float(best["stop_bps"]),
                "max_hold_bars": int(args.max_hold_bars),
                "t1": float(best["t1"]),
                "t2": float(best["t2"]),
                "oos_hard_pass": bool(oos_hard),
                "outlier_gate_mode": str(args.outlier_gate_mode),
                "decision_clock": str(args.decision_clock),
                "m60_features_only": bool(args.m60_features_only),
            }

            bdf = base_guard.copy()
            for k, v in common.items():
                bdf[k] = v
            bdf["variant"] = "baseline_fast_causal"
            bdf["promoted_source"] = "baseline"
            oos_base_rows.append(bdf)

            cdf = cand_guard.copy()
            for k, v in common.items():
                cdf[k] = v
            cdf["variant"] = "meta_fast_candidate"
            cdf["promoted_source"] = "candidate"
            oos_cand_rows.append(cdf)

            pdf = prom_guard.copy()
            for k, v in common.items():
                pdf[k] = v
            pdf["variant"] = "meta_fast_promoted"
            pdf["promoted_source"] = "candidate" if promote_on_fold else "baseline_hard_fail"
            oos_prom_rows.append(pdf)

            s = cand_scored[
                [
                    "trade_id",
                    "pair",
                    "timeframe",
                    "strategy_type",
                    "timestamp",
                    "exit_ts",
                    "pnl_bps",
                    "duration_bars",
                    "exit_reason",
                    "cluster_gate_action",
                    "size_mult",
                    "p_bad_2bar",
                    "candidate_gate_hit",
                    "outlier_m5_flag",
                    "outlier_m15_flag",
                    "hit_target_within_1bar",
                    "hit_target_within_2bars",
                ]
            ].copy()
            s["mix_id"] = mix_name
            s["fold_year"] = int(fold.test_year)
            s["target_bps"] = float(args.target_bps)
            s["stop_bps"] = float(best["stop_bps"])
            s["max_hold_bars"] = int(args.max_hold_bars)
            s["t1"] = float(best["t1"])
            s["t2"] = float(best["t2"])
            p2_raw_by_id = te_short.assign(_p=(1.0 - best["fit2"]["proba_raw_te"])).set_index("trade_id")["_p"].to_dict()
            p2_cal_by_id = te_short.assign(_p=(1.0 - best["fit2"]["proba_cal_te"])).set_index("trade_id")["_p"].to_dict()
            p1_cal_by_id = te_short.assign(_p=(1.0 - best["fit1"]["proba_cal_te"])).set_index("trade_id")["_p"].to_dict()
            y2_by_id = te_short.assign(_y=y2_te.astype(int)).set_index("trade_id")["_y"].to_dict()
            y1_by_id = te_short.assign(_y=y1_te.astype(int)).set_index("trade_id")["_y"].to_dict()
            s["p_bad_2bar_raw"] = s["trade_id"].map(p2_raw_by_id).fillna(1.0).astype(float)
            s["p_bad_2bar_calibrated"] = s["trade_id"].map(p2_cal_by_id).fillna(1.0).astype(float)
            s["p_bad_1bar_calibrated"] = s["trade_id"].map(p1_cal_by_id).fillna(1.0).astype(float)
            s["setup_good_2bar_label"] = s["trade_id"].map(y2_by_id).fillna(0).astype(int)
            s["setup_good_1bar_label"] = s["trade_id"].map(y1_by_id).fillna(0).astype(int)
            s["expected_move_bps_2bar"] = (1.0 - s["p_bad_2bar_calibrated"]) * float(args.target_bps) - s["p_bad_2bar_calibrated"] * float(best["stop_bps"])
            s["expected_move_bps_1bar"] = (1.0 - s["p_bad_1bar_calibrated"]) * float(args.target_bps) - s["p_bad_1bar_calibrated"] * float(best["stop_bps"])
            scored_rows.append(s)

            print(
                f"    stop={best['stop_bps']:.2f} t1={best['t1']:.2f} t2={best['t2']:.2f} "
                f"| base_mean={m_base['mean_pnl_per_trade_bps']:.2f} "
                f"| cand_mean={m_cand['mean_pnl_per_trade_bps']:.2f} "
                f"| base_tim={m_base['time_in_market_pct']:.1f}% "
                f"| cand_tim={m_cand['time_in_market_pct']:.1f}% "
                f"| oos_hard_pass={oos_hard}"
            )

    if not fold_rows:
        raise RuntimeError("No valid folds produced")

    folds_df = pd.DataFrame(fold_rows).sort_values(["mix_id", "year"]).reset_index(drop=True)
    grid_df = pd.concat(grid_rows, ignore_index=True) if grid_rows else pd.DataFrame()
    scored_df = pd.concat(scored_rows, ignore_index=True) if scored_rows else pd.DataFrame()
    calib_df = pd.DataFrame(calibration_rows).sort_values(["mix_id", "year"]).reset_index(drop=True)

    oos_base = pd.concat(oos_base_rows, ignore_index=True) if oos_base_rows else pd.DataFrame()
    oos_cand = pd.concat(oos_cand_rows, ignore_index=True) if oos_cand_rows else pd.DataFrame()
    oos_prom = pd.concat(oos_prom_rows, ignore_index=True) if oos_prom_rows else pd.DataFrame()

    summary_rows = []
    for mix_name in sorted(folds_df["mix_id"].astype(str).unique().tolist()):
        for label, sub in [
            ("baseline_fast_causal", oos_base[oos_base["mix_id"] == mix_name].copy()),
            ("meta_fast_candidate", oos_cand[oos_cand["mix_id"] == mix_name].copy()),
            ("meta_fast_promoted", oos_prom[oos_prom["mix_id"] == mix_name].copy()),
        ]:
            if sub.empty:
                continue
            r = _derive_risk_bps(sub, fallback=100.0)
            m = _metrics_with_risk(sub, risk_bps=r)
            summary_rows.append(
                {
                    "mix_id": mix_name,
                    "variant": label,
                    "selection_objective": "fast_dd_time_market",
                    "threshold_policy": "train_only",
                    "feature_stack": str(args.feature_stack),
                    "decision_clock": str(args.decision_clock),
                    "outlier_gate_mode": str(args.outlier_gate_mode),
                    "oos_hard_pass_rate": float(sub["oos_hard_pass"].mean()) if "oos_hard_pass" in sub.columns else np.nan,
                    **m,
                }
            )

        s = pd.DataFrame([x for x in summary_rows if x["mix_id"] == mix_name])
        if {"baseline_fast_causal", "meta_fast_promoted"}.issubset(set(s["variant"].tolist())):
            b = s.loc[s["variant"] == "baseline_fast_causal"].iloc[0]
            pmt = s.loc[s["variant"] == "meta_fast_promoted"].iloc[0]
            summary_rows.append(
                {
                    "mix_id": mix_name,
                    "variant": "meta_fast_promoted_minus_baseline",
                    "selection_objective": "fast_dd_time_market",
                    "threshold_policy": "train_only",
                    "feature_stack": str(args.feature_stack),
                    "decision_clock": str(args.decision_clock),
                    "outlier_gate_mode": str(args.outlier_gate_mode),
                    "oos_hard_pass_rate": float(pmt["oos_hard_pass_rate"]),
                    "trades": int(pmt["trades"] - b["trades"]),
                    "mean_pnl_per_trade_bps": float(pmt["mean_pnl_per_trade_bps"] - b["mean_pnl_per_trade_bps"]),
                    "sharpe": float(pmt["sharpe"] - b["sharpe"]),
                    "annualized_bps_calendar": float(pmt["annualized_bps_calendar"] - b["annualized_bps_calendar"]),
                    "worst_single_day_bps": float(pmt["worst_single_day_bps"] - b["worst_single_day_bps"]),
                    "max_daily_dd_bps": float(pmt["max_daily_dd_bps"] - b["max_daily_dd_bps"]),
                    "time_in_market_pct": float(pmt["time_in_market_pct"] - b["time_in_market_pct"]),
                    "avg_trade_duration_bars": float(pmt["avg_trade_duration_bars"] - b["avg_trade_duration_bars"]),
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
    calib_path = out_dir / f"{args.out_prefix}_fold_calibration.csv"
    mc_paths_path = out_dir / f"{args.out_prefix}_mc_daily_paths.csv"
    mc_summary_path = out_dir / f"{args.out_prefix}_mc_daily_summary.csv"

    folds_df.to_csv(folds_path, index=False)
    grid_df.to_csv(grid_path, index=False)
    summary_df.to_csv(summary_path, index=False)
    pd.concat([oos_base, oos_cand, oos_prom], ignore_index=True).to_csv(trades_path, index=False)
    scored_df.to_csv(scored_path, index=False)
    calib_df.to_csv(calib_path, index=False)

    mc_rows = []
    for mix_name in sorted(summary_df["mix_id"].dropna().unique().tolist()):
        for variant, vdf in [
            ("baseline_fast_causal", oos_base[oos_base["mix_id"] == mix_name].copy()),
            ("meta_fast_promoted", oos_prom[oos_prom["mix_id"] == mix_name].copy()),
        ]:
            if vdf.empty:
                continue
            mc = _block_bootstrap_daily(
                vdf,
                n_paths=int(args.mc_paths),
                block_days=int(args.mc_block_days),
                seed=int(args.random_state + (17 if variant == "meta_fast_promoted" else 0)),
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
    print(f"- {calib_path}")
    if not mc_summary.empty:
        print(f"- {mc_paths_path}")
        print(f"- {mc_summary_path}")


if __name__ == "__main__":
    main()
