#!/usr/bin/env python3
"""
Causal walk-forward meta-filter using first-hit triple-barrier labels for DD control.

Portfolio under test:
- Short-term legs: M5 REV + M15 REV
- Long-term leg: M60 MOM (H1 source)

Workflow per fold (year):
1) Train only on history before test year with embargo.
2) Build first-hit triple-barrier labels on train from bar paths (per timeframe barriers).
3) Train classifier to estimate P(bad trade) on short-term legs.
4) Select gating threshold on train only with DD-first objective under return/trade constraints.
5) Apply threshold and train-selected pair filter to test year (causal).
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
from catboost import CatBoostClassifier

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from behemoth.core.metrics import sharpe_daily
from scripts.report_strategy_fx_comm_multi_tf import (
    OIL_LINKED_PAIRS,
    PAIR_WHITELIST_BASE,
    _apply_guardrail,
    _derive_risk_bps,
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


def _parse_grid(s: str) -> list[float]:
    out = []
    for token in s.split(","):
        token = token.strip()
        if token:
            out.append(float(token))
    return out


def _parse_objective_weights(s: str) -> dict[str, float]:
    """
    Format: dd=0.45,sharpe=0.35,annualized_bps=0.20
    """
    out = {"dd": 0.45, "sharpe": 0.35, "annualized_bps": 0.20}
    if not s:
        return out
    for token in s.split(","):
        token = token.strip()
        if not token:
            continue
        if "=" not in token:
            raise ValueError(f"Invalid objective weight token: {token}")
        k, v = token.split("=", 1)
        k = k.strip().lower()
        if k == "annualized_bps_calendar":
            k = "annualized_bps"
        if k not in out:
            raise ValueError(f"Unsupported objective weight key: {k}")
        out[k] = float(v)
    total = float(sum(out.values()))
    if total <= 0.0:
        raise ValueError("Objective weights must sum to > 0")
    for k in list(out.keys()):
        out[k] = float(out[k] / total)
    return out


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
    # Canonical order keeps IDs stable regardless of input token order.
    ordered = [tok for tok in ["MOM", "REV"] if tok in set(tokens)]
    return "+".join(ordered)


def _parse_strategy_mixes(s: str) -> list[dict[str, str]]:
    """
    Format:
      "m5=REV,m15=REV,m60=MOM;m5=MOM,m15=REV,m60=MOM"
    """
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
        mixes.append({"m5": "REV", "m15": "REV", "m60": "MOM"})
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
        return df

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


def _compute_barriers(train_short: pd.DataFrame, pt_q: float, sl_q: float) -> dict[str, tuple[float, float]]:
    out: dict[str, tuple[float, float]] = {}
    for tf, sub in train_short.groupby("timeframe", sort=True):
        pos = sub.loc[sub["pnl_bps"] > 0.0, "pnl_bps"]
        neg = sub.loc[sub["pnl_bps"] < 0.0, "pnl_bps"].abs()
        pt = float(pos.quantile(pt_q)) if len(pos) else 1.0
        sl = float(neg.quantile(sl_q)) if len(neg) else 1.0
        out[str(tf)] = (max(pt, 1e-6), max(sl, 1e-6))
    return out


def _side_to_dir(side: str) -> int:
    s = str(side).upper()
    if s == "LONG":
        return 1
    if s == "SHORT":
        return -1
    return 0


def _build_short_state_cache(pair_whitelist: list[str]) -> dict[str, dict[str, dict]]:
    return {
        "m5": _build_pair_states("m5", pair_whitelist),
        "m15": _build_pair_states("m15", pair_whitelist),
    }


def _attach_tb_state_columns(df: pd.DataFrame, state_cache: dict[str, dict[str, dict]]) -> pd.DataFrame:
    """
    Attach state-derived columns needed for first-hit triple-barrier labeling.
    """
    out = df.copy()
    out["side_dir"] = out["side"].map(_side_to_dir).astype(int)
    out["entry_idx"] = -1
    out["tb_final_pnl_bps"] = np.nan
    out["tb_effective_hold"] = np.nan

    for i, row in out.iterrows():
        tf = str(row["timeframe"])
        pair = str(row["pair"])
        st = state_cache.get(tf, {}).get(pair)
        if st is None:
            continue
        idx = st["ts_to_idx"].get(int(row["timestamp"]))
        if idx is None:
            continue
        max_hold = int(max(1, int(float(row["max_hold_bars"])) if pd.notna(row["max_hold_bars"]) else 500))
        prices = st["y"] if str(row["active_leg"]) == "Y" else st["x"]
        end_idx = min(idx + max_hold - 1, len(prices) - 1)
        side_dir = int(out.at[i, "side_dir"])
        if side_dir == 0:
            continue
        entry_price = float(prices[idx])
        final_price = float(prices[end_idx])
        final_pnl = float(side_dir * (final_price - entry_price) * 10000.0)
        out.at[i, "entry_idx"] = int(idx)
        out.at[i, "tb_final_pnl_bps"] = final_pnl
        out.at[i, "tb_effective_hold"] = int(end_idx - idx)

    return out


def _assign_triple_barrier_labels(
    df: pd.DataFrame,
    barriers: dict[str, tuple[float, float]],
    timeout_loss_bad_ratio: float,
    state_cache: dict[str, dict[str, dict]],
) -> pd.Series:
    """
    First-hit triple-barrier labels from bar paths:
    - 0: upper barrier (PT) hit first
    - 1: lower barrier (SL) hit first OR negative timeout-like close
    - -1: neither barrier hit (neutral)
    """
    labels = np.full(len(df), -1, dtype=int)
    for i, row in enumerate(df.itertuples(index=False)):
        tf = str(row.timeframe)
        pair = str(row.pair)
        pt, sl = barriers.get(tf, (1.0, 1.0))
        side_dir = int(getattr(row, "side_dir", 0))
        entry_idx = int(getattr(row, "entry_idx", -1))
        max_hold = int(max(1, int(float(row.max_hold_bars)) if pd.notna(row.max_hold_bars) else 500))

        st = state_cache.get(tf, {}).get(pair)
        if st is None or side_dir == 0 or entry_idx < 0:
            # Conservative fallback for rows without recoverable state.
            pnl = float(row.pnl_bps)
            if pnl <= -sl:
                labels[i] = 1
            elif pnl >= pt:
                labels[i] = 0
            else:
                labels[i] = -1
            continue

        prices = st["y"] if str(row.active_leg) == "Y" else st["x"]
        if entry_idx >= len(prices):
            labels[i] = -1
            continue
        entry_price = float(prices[entry_idx])
        end_idx = min(entry_idx + max_hold - 1, len(prices) - 1)

        hit_label = -1
        for j in range(entry_idx + 1, end_idx + 1):
            pnl_j = float(side_dir * (float(prices[j]) - entry_price) * 10000.0)
            if pnl_j >= pt:
                hit_label = 0
                break
            if pnl_j <= -sl:
                hit_label = 1
                break

        if hit_label != -1:
            labels[i] = hit_label
            continue

        eff_hold = float(getattr(row, "tb_effective_hold", np.nan))
        if not np.isfinite(eff_hold):
            eff_hold = float(max(0, end_idx - entry_idx))
        timeout_like = (eff_hold / float(max_hold)) >= float(timeout_loss_bad_ratio)
        final_pnl = float(getattr(row, "tb_final_pnl_bps", np.nan))
        if not np.isfinite(final_pnl):
            final_pnl = float(side_dir * (float(prices[end_idx]) - entry_price) * 10000.0)
        if timeout_like and final_pnl < 0.0:
            labels[i] = 1
        else:
            labels[i] = -1

    return pd.Series(labels, index=df.index, dtype="int64")


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
        },
        index=df.index,
    )
    cat = pd.DataFrame(
        {
            "pair": df["pair"].astype(str),
            "timeframe": df["timeframe"].astype(str),
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
        s = float(sharpe_daily(sub["pnl_bps"].to_numpy(dtype=float), sub["exit_ts"].to_numpy(dtype="int64")))
        if s >= cutoff:
            keep.add(str(pair))
    if not keep:
        keep = set(train_guard_df["pair"].astype(str).unique().tolist())
    return keep


def _time_ordered_split(
    df: pd.DataFrame,
    labeled_mask: pd.Series,
    calibration_frac: float,
) -> tuple[pd.Series, pd.Series]:
    """
    Split labeled rows into model-train and calibration by time order.
    """
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


def _fit_calibrator(
    method: str,
    p_raw_cal: np.ndarray,
    y_cal: np.ndarray,
):
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


def _norm01(series: pd.Series) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce").astype(float)
    lo = float(s.min())
    hi = float(s.max())
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return pd.Series(np.full(len(s), 0.5, dtype=float), index=s.index)
    return (s - lo) / (hi - lo)


def _eval_variant(
    short_df: pd.DataFrame,
    long_df: pd.DataFrame,
    keep_short_mask: pd.Series,
    risk_bps: float,
    pair_keep: set[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float]]:
    short_kept = short_df.loc[keep_short_mask].copy()
    pre = pd.concat([short_kept, long_df], ignore_index=True).sort_values(["timestamp", "pair"]).reset_index(drop=True)
    guard = _apply_guardrail(pre)
    if pair_keep is not None and len(pair_keep):
        guard = guard[guard["pair"].astype(str).isin(pair_keep)].copy().reset_index(drop=True)
    metrics = _metrics_with_risk(guard, risk_bps=risk_bps)
    return pre, guard, metrics


def _select_threshold_balanced(
    train_short: pd.DataFrame,
    train_long: pd.DataFrame,
    proba_bad_train: pd.Series,
    threshold_grid: list[float],
    pair_keep_fixed: set[str],
    retain_annualized_frac: float,
    min_trade_frac: float,
    risk_bps: float,
    objective_weights: dict[str, float],
    max_ddaily_bps_cap: float | None,
    max_dd_pct_cap: float | None,
    mc_p5_ddaily_cap: float | None,
    ddaily_cap_mult: float,
    ddpct_cap_mult: float,
    mc_p5_cap_mult: float,
    train_mc_paths: int,
    train_mc_block_days: int,
    random_state: int,
) -> tuple[float, pd.DataFrame, dict[str, float]]:
    idx = train_short.index
    base_mask = pd.Series(np.ones(len(train_short), dtype=bool), index=idx)
    _, base_guard_train, _ = _eval_variant(
        train_short, train_long, base_mask, risk_bps=risk_bps, pair_keep=pair_keep_fixed
    )
    base_m_train = _metrics_with_risk(base_guard_train, risk_bps=risk_bps)
    base_mc = _block_bootstrap_daily(
        base_guard_train,
        n_paths=max(50, int(train_mc_paths)),
        block_days=max(1, int(train_mc_block_days)),
        seed=int(random_state),
    )
    base_mc_p5_dd = (
        float(np.percentile(base_mc["max_daily_dd_bps"].to_numpy(dtype=float), 5)) if not base_mc.empty else 0.0
    )

    dd_cap = float(max_ddaily_bps_cap) if max_ddaily_bps_cap is not None else float(base_m_train["max_daily_dd_bps"] * ddaily_cap_mult)
    dd_pct_cap = float(max_dd_pct_cap) if max_dd_pct_cap is not None else float(base_m_train["max_dd_pct"] * ddpct_cap_mult)
    mc_dd_cap = float(mc_p5_ddaily_cap) if mc_p5_ddaily_cap is not None else float(base_mc_p5_dd * mc_p5_cap_mult)

    rows = []
    for thr in threshold_grid:
        keep_mask = (proba_bad_train <= float(thr))
        _, guard_train, m = _eval_variant(
            train_short, train_long, keep_mask, risk_bps=risk_bps, pair_keep=pair_keep_fixed
        )
        mc = _block_bootstrap_daily(
            guard_train,
            n_paths=max(50, int(train_mc_paths)),
            block_days=max(1, int(train_mc_block_days)),
            seed=int(random_state + round(thr * 10000)),
        )
        mc_p5_dd = float(np.percentile(mc["max_daily_dd_bps"].to_numpy(dtype=float), 5)) if not mc.empty else 0.0

        retain_pass = (
            m["annualized_bps_calendar"] >= (retain_annualized_frac * base_m_train["annualized_bps_calendar"])
            and m["trades"] >= (min_trade_frac * base_m_train["trades"])
            and m["trades"] > 100
        )
        dd_pass = m["max_daily_dd_bps"] >= dd_cap
        dd_pct_pass = m["max_dd_pct"] >= dd_pct_cap
        mc_pass = mc_p5_dd >= mc_dd_cap
        strict_pass = bool(retain_pass and dd_pass and dd_pct_pass and mc_pass)

        eligible = (
            m["annualized_bps_calendar"] >= (retain_annualized_frac * base_m_train["annualized_bps_calendar"])
            and m["trades"] >= (min_trade_frac * base_m_train["trades"])
            and m["trades"] > 100
        )
        rows.append(
            {
                "threshold": float(thr),
                "eligible": bool(eligible),
                "strict_pass": strict_pass,
                "retain_pass": bool(retain_pass),
                "dd_pass": bool(dd_pass),
                "dd_pct_pass": bool(dd_pct_pass),
                "mc_pass": bool(mc_pass),
                "dd_cap_bps": float(dd_cap),
                "dd_cap_pct": float(dd_pct_cap),
                "mc_p5_dd_cap_bps": float(mc_dd_cap),
                "mc_p5_dd_bps": float(mc_p5_dd),
                "pairs_kept": int(len(pair_keep_fixed)),
                "trades": int(m["trades"]),
                "mean_pnl_per_trade_bps": float(m["mean_pnl_per_trade_bps"]),
                "sharpe": float(m["sharpe"]),
                "annualized_bps_calendar": float(m["annualized_bps_calendar"]),
                "max_daily_dd_bps": float(m["max_daily_dd_bps"]),
                "max_dd_pct": float(m["max_dd_pct"]),
            }
        )

    grid = pd.DataFrame(rows)
    grid["score"] = (
        objective_weights["dd"] * _norm01(grid["max_daily_dd_bps"])
        + objective_weights["sharpe"] * _norm01(grid["sharpe"])
        + objective_weights["annualized_bps"] * _norm01(grid["annualized_bps_calendar"])
    )

    candidates = grid[grid["strict_pass"]].copy()
    if candidates.empty:
        # Fallback if hard caps are impossible: pick best DD-first viable by retain/trade.
        candidates = grid[grid["eligible"]].copy()
        if candidates.empty:
            candidates = grid.copy()
        fallback_reason = "strict_caps_unmet"
    else:
        fallback_reason = ""

    chosen = candidates.sort_values(
        ["score", "max_daily_dd_bps", "sharpe", "annualized_bps_calendar", "mean_pnl_per_trade_bps"],
        ascending=[False, False, False, False, False],
    ).iloc[0]
    chosen_meta = {
        "fallback_reason": fallback_reason,
        "base_train_annualized_bps": float(base_m_train["annualized_bps_calendar"]),
        "base_train_trades": int(base_m_train["trades"]),
        "base_train_max_daily_dd_bps": float(base_m_train["max_daily_dd_bps"]),
        "base_train_max_dd_pct": float(base_m_train["max_dd_pct"]),
        "base_train_mc_p5_dd_bps": float(base_mc_p5_dd),
    }
    return float(chosen["threshold"]), grid, chosen_meta


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

    return {
        "annualized_bps_calendar": float(mean * 365.25),
        "max_daily_dd_bps": float(np.min(dd)),
        "sharpe_daily_bps": sharpe,
        "cagr_notional": cagr,
    }


def _block_bootstrap_daily(
    df: pd.DataFrame,
    n_paths: int,
    block_days: int,
    seed: int,
) -> pd.DataFrame:
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


def _fit_model_with_optional_calibration(
    tr_short: pd.DataFrame,
    te_short: pd.DataFrame,
    X_all: pd.DataFrame,
    y_tr: pd.Series,
    classifier: str,
    enable_calibration: bool,
    calibration_method: str,
    calibration_frac: float,
    random_state: int,
) -> dict:
    tr_idx = tr_short.index
    te_idx = te_short.index
    X_tr = X_all.loc[tr_idx]
    X_te = X_all.loc[te_idx]
    train_labeled = (y_tr != -1)
    if int(train_labeled.sum()) < 100:
        raise RuntimeError("Not enough labeled trades to fit model.")

    train_mask, cal_mask = _time_ordered_split(tr_short, train_labeled, calibration_frac=calibration_frac)
    # Guard against class collapse in the split.
    if len(np.unique(y_tr.loc[train_mask].astype(int).to_numpy())) < 2:
        train_mask = train_labeled.copy()
        cal_mask = pd.Series(False, index=tr_short.index)

    clf = str(classifier).lower().strip()
    if clf == "catboost":
        model = CatBoostClassifier(
            loss_function="Logloss",
            depth=6,
            learning_rate=0.05,
            iterations=500,
            l2_leaf_reg=3.0,
            random_seed=int(random_state),
            verbose=False,
            allow_writing_files=False,
        )
    else:
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


def main() -> None:
    p = argparse.ArgumentParser(description="Causal triple-barrier meta-filter for mixed REV/MOM portfolio.")
    p.add_argument("--exclude-oil", action="store_true", default=True)
    p.add_argument(
        "--mixes",
        default="m5=REV,m15=REV,m60=MOM",
        help="semicolon-separated strategy mixes, or 'all' for all 8 MOM/REV combinations",
    )
    p.add_argument("--start-test-year", type=int, default=2020)
    p.add_argument("--end-test-year", type=int, default=2025)
    p.add_argument("--embargo-days", type=int, default=5)
    p.add_argument("--pair-sharpe-cutoff", type=float, default=0.30)
    p.add_argument("--pt-quantiles", default="0.60", help="comma-separated pt quantiles for label ablation")
    p.add_argument("--sl-quantiles", default="0.60", help="comma-separated sl quantiles for label ablation")
    p.add_argument(
        "--timeout-loss-bad-ratios",
        default="0.95",
        help="comma-separated timeout-like ratios for negative timeout bad-label rule",
    )
    p.add_argument("--enable-calibration", action="store_true", default=True)
    p.add_argument("--calibration-method", default="isotonic", choices=["isotonic", "platt", "none"])
    p.add_argument("--calibration-frac", type=float, default=0.20)
    p.add_argument("--classifier", default="hgbt", choices=["hgbt", "catboost"])
    p.add_argument("--retain-annualized-frac", type=float, default=0.80)
    p.add_argument("--min-trade-frac", type=float, default=0.50)
    p.add_argument("--threshold-grid", default="0.30,0.35,0.40,0.45,0.50,0.55,0.60,0.65,0.70,0.75,0.80")
    p.add_argument("--objective", default="balanced_dd_sharpe_bps", choices=["balanced_dd_sharpe_bps"])
    p.add_argument("--objective-weights", default="dd=0.45,sharpe=0.35,annualized_bps=0.20")
    p.add_argument("--max-ddaily-bps-cap", type=float, default=None)
    p.add_argument("--max-dd-pct-cap", type=float, default=None)
    p.add_argument("--mc-p5-ddaily-cap", type=float, default=None)
    p.add_argument("--ddaily-cap-mult", type=float, default=0.75)
    p.add_argument("--ddpct-cap-mult", type=float, default=0.75)
    p.add_argument("--mc-p5-cap-mult", type=float, default=0.80)
    p.add_argument("--train-mc-paths", type=int, default=150)
    p.add_argument("--train-mc-block-days", type=int, default=20)
    p.add_argument("--mc-p95-dd-allow-worse-bps", type=float, default=0.0)
    p.add_argument("--random-state", type=int, default=42)
    p.add_argument("--mc-paths", type=int, default=1000, help="block-bootstrap Monte Carlo paths on OOS daily curve")
    p.add_argument("--mc-block-days", type=int, default=20, help="block size in days for daily bootstrap")
    p.add_argument(
        "--out-prefix",
        default="meta_tb_mixed_no_oil",
        help="output prefix under data/analysis/",
    )
    args = p.parse_args()

    pair_whitelist = list(PAIR_WHITELIST_BASE)
    if args.exclude_oil:
        pair_whitelist = [x for x in pair_whitelist if x not in OIL_LINKED_PAIRS]

    mixes = _parse_strategy_mixes(args.mixes)
    objective_weights = _parse_objective_weights(args.objective_weights)
    threshold_grid = _parse_grid(args.threshold_grid)
    pt_quantiles = _parse_grid(args.pt_quantiles)
    sl_quantiles = _parse_grid(args.sl_quantiles)
    timeout_ratios = _parse_grid(args.timeout_loss_bad_ratios)
    folds = _make_folds(args.start_test_year, args.end_test_year, args.embargo_days)

    print("Building state cache for first-hit labels...")
    state_cache = _build_short_state_cache(pair_whitelist)

    fold_rows: list[dict] = []
    threshold_rows: list[pd.DataFrame] = []
    calibration_rows: list[dict] = []
    ablation_rows: list[dict] = []
    oos_base_trades: list[pd.DataFrame] = []
    oos_meta_candidate_trades: list[pd.DataFrame] = []
    oos_meta_promoted_trades: list[pd.DataFrame] = []
    oos_scored_rows: list[pd.DataFrame] = []

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

        short_all = pd.concat(
            [loaded["m5"], loaded["m15"]], ignore_index=True
        ).reset_index(drop=True)
        long_all = loaded["m60"].reset_index(drop=True)
        has_long_leg = str(mix["m60"]).upper() != "NONE"
        if short_all.empty or (has_long_leg and long_all.empty):
            print("  skip mix: empty short dataset or empty required long dataset after filters")
            continue

        short_all["trade_id"] = np.arange(len(short_all), dtype=np.int64)
        long_all["trade_id"] = -1
        short_all["mix_id"] = mix_name
        long_all["mix_id"] = mix_name

        short_all = _attach_tb_state_columns(short_all, state_cache)
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

            if len(tr_short) < 2000 or te_short.empty:
                print("    skip: insufficient train/test short trades")
                continue

            _, train_base_guard, _ = _eval_variant(
                tr_short,
                tr_long,
                keep_short_mask=pd.Series(np.ones(len(tr_short), dtype=bool), index=tr_short.index),
                risk_bps=risk_bps,
                pair_keep=None,
            )
            pair_keep_base = _pair_filter_set(train_base_guard, cutoff=args.pair_sharpe_cutoff)

            best_payload = None
            fold_ablation = []

            for pt_q, sl_q, timeout_ratio in itertools.product(pt_quantiles, sl_quantiles, timeout_ratios):
                barriers = _compute_barriers(tr_short, pt_q=float(pt_q), sl_q=float(sl_q))
                y_tr = _assign_triple_barrier_labels(
                    tr_short,
                    barriers=barriers,
                    timeout_loss_bad_ratio=float(timeout_ratio),
                    state_cache=state_cache,
                )
                y_te = _assign_triple_barrier_labels(
                    te_short,
                    barriers=barriers,
                    timeout_loss_bad_ratio=float(timeout_ratio),
                    state_cache=state_cache,
                )
                if int((y_tr != -1).sum()) < 1000:
                    continue
                if len(np.unique(y_tr[y_tr != -1].astype(int).to_numpy())) < 2:
                    continue

                fit = _fit_model_with_optional_calibration(
                    tr_short=tr_short,
                    te_short=te_short,
                    X_all=X_all,
                    y_tr=y_tr,
                    classifier=args.classifier,
                    enable_calibration=bool(args.enable_calibration),
                    calibration_method=args.calibration_method,
                    calibration_frac=float(args.calibration_frac),
                    random_state=int(args.random_state + fold.test_year + round(1000 * (pt_q + sl_q + timeout_ratio))),
                )

                thr, thr_grid_df, chosen_meta = _select_threshold_balanced(
                    train_short=tr_short,
                    train_long=tr_long,
                    proba_bad_train=fit["proba_cal_tr"],
                    threshold_grid=threshold_grid,
                    pair_keep_fixed=pair_keep_base,
                    retain_annualized_frac=float(args.retain_annualized_frac),
                    min_trade_frac=float(args.min_trade_frac),
                    risk_bps=risk_bps,
                    objective_weights=objective_weights,
                    max_ddaily_bps_cap=args.max_ddaily_bps_cap,
                    max_dd_pct_cap=args.max_dd_pct_cap,
                    mc_p5_ddaily_cap=args.mc_p5_ddaily_cap,
                    ddaily_cap_mult=float(args.ddaily_cap_mult),
                    ddpct_cap_mult=float(args.ddpct_cap_mult),
                    mc_p5_cap_mult=float(args.mc_p5_cap_mult),
                    train_mc_paths=int(args.train_mc_paths),
                    train_mc_block_days=int(args.train_mc_block_days),
                    random_state=int(args.random_state + fold.test_year),
                )

                thr_rows = thr_grid_df.copy()
                thr_rows["mix_id"] = mix_name
                thr_rows["fold_year"] = fold.test_year
                thr_rows["pt_q"] = float(pt_q)
                thr_rows["sl_q"] = float(sl_q)
                thr_rows["timeout_ratio"] = float(timeout_ratio)
                threshold_rows.append(thr_rows)

                chosen_row = thr_grid_df.loc[np.isclose(thr_grid_df["threshold"], float(thr))].iloc[0]
                arow = {
                    "mix_id": mix_name,
                    "year": int(fold.test_year),
                    "pt_q": float(pt_q),
                    "sl_q": float(sl_q),
                    "timeout_ratio": float(timeout_ratio),
                    "threshold": float(thr),
                    "strict_pass": bool(chosen_row["strict_pass"]),
                    "score": float(chosen_row["score"]),
                    "max_daily_dd_bps": float(chosen_row["max_daily_dd_bps"]),
                    "max_dd_pct": float(chosen_row["max_dd_pct"]),
                    "annualized_bps_calendar": float(chosen_row["annualized_bps_calendar"]),
                    "sharpe": float(chosen_row["sharpe"]),
                    "trades": int(chosen_row["trades"]),
                    "fallback_reason": str(chosen_meta.get("fallback_reason", "")),
                    "train_bad_label_rate": float((y_tr == 1).mean()),
                    "train_good_label_rate": float((y_tr == 0).mean()),
                    "test_bad_label_rate": float((y_te == 1).mean()),
                    "test_good_label_rate": float((y_te == 0).mean()),
                    "calibration_method": str(fit["calib_info"]["effective_method"]),
                    "cal_brier_raw": fit["calib_info"]["brier_raw"],
                    "cal_brier_cal": fit["calib_info"]["brier_cal"],
                    "cal_logloss_raw": fit["calib_info"]["logloss_raw"],
                    "cal_logloss_cal": fit["calib_info"]["logloss_cal"],
                    "is_chosen": False,
                }
                fold_ablation.append(arow)

                rank_tuple = (
                    int(bool(chosen_row["strict_pass"])),
                    float(chosen_row["score"]),
                    float(chosen_row["max_daily_dd_bps"]),
                    float(chosen_row["sharpe"]),
                )
                if best_payload is None or rank_tuple > best_payload["rank"]:
                    best_payload = {
                        "rank": rank_tuple,
                        "pt_q": float(pt_q),
                        "sl_q": float(sl_q),
                        "timeout_ratio": float(timeout_ratio),
                        "threshold": float(thr),
                        "fit": fit,
                        "y_te": y_te.copy(),
                        "chosen_row": chosen_row.to_dict(),
                        "chosen_meta": chosen_meta,
                    }

            if best_payload is None:
                print("    skip: no viable label config")
                continue

            for i in range(len(fold_ablation)):
                if (
                    abs(fold_ablation[i]["pt_q"] - best_payload["pt_q"]) < 1e-12
                    and abs(fold_ablation[i]["sl_q"] - best_payload["sl_q"]) < 1e-12
                    and abs(fold_ablation[i]["timeout_ratio"] - best_payload["timeout_ratio"]) < 1e-12
                ):
                    fold_ablation[i]["is_chosen"] = True
            ablation_rows.extend(fold_ablation)

            calibration_rows.append(
                {
                    "mix_id": mix_name,
                    "year": int(fold.test_year),
                    "pt_q": float(best_payload["pt_q"]),
                    "sl_q": float(best_payload["sl_q"]),
                    "timeout_ratio": float(best_payload["timeout_ratio"]),
                    "threshold": float(best_payload["threshold"]),
                    "calibration_method": str(best_payload["fit"]["calib_info"]["effective_method"]),
                    "n_train_model": int(best_payload["fit"]["calib_info"]["n_train_model"]),
                    "n_train_cal": int(best_payload["fit"]["calib_info"]["n_train_cal"]),
                    "brier_raw": best_payload["fit"]["calib_info"]["brier_raw"],
                    "brier_cal": best_payload["fit"]["calib_info"]["brier_cal"],
                    "logloss_raw": best_payload["fit"]["calib_info"]["logloss_raw"],
                    "logloss_cal": best_payload["fit"]["calib_info"]["logloss_cal"],
                }
            )

            _, test_base_guard, m_base = _eval_variant(
                te_short,
                te_long,
                keep_short_mask=pd.Series(np.ones(len(te_short), dtype=bool), index=te_short.index),
                risk_bps=risk_bps,
                pair_keep=pair_keep_base,
            )
            keep_meta_te = best_payload["fit"]["proba_cal_te"] <= float(best_payload["threshold"])
            _, test_meta_guard, m_meta_candidate = _eval_variant(
                te_short,
                te_long,
                keep_short_mask=keep_meta_te,
                risk_bps=risk_bps,
                pair_keep=pair_keep_base,
            )

            mc_base = _block_bootstrap_daily(
                test_base_guard,
                n_paths=max(60, int(args.train_mc_paths)),
                block_days=max(1, int(args.train_mc_block_days)),
                seed=int(args.random_state + 111 + fold.test_year),
            )
            mc_meta = _block_bootstrap_daily(
                test_meta_guard,
                n_paths=max(60, int(args.train_mc_paths)),
                block_days=max(1, int(args.train_mc_block_days)),
                seed=int(args.random_state + 211 + fold.test_year),
            )
            base_mc_p5_ann = (
                float(np.percentile(mc_base["annualized_bps_calendar"].to_numpy(dtype=float), 5)) if not mc_base.empty else -np.inf
            )
            meta_mc_p5_ann = (
                float(np.percentile(mc_meta["annualized_bps_calendar"].to_numpy(dtype=float), 5)) if not mc_meta.empty else -np.inf
            )
            base_mc_p95_dd = (
                float(np.percentile(mc_base["max_daily_dd_bps"].to_numpy(dtype=float), 95)) if not mc_base.empty else -np.inf
            )
            meta_mc_p95_dd = (
                float(np.percentile(mc_meta["max_daily_dd_bps"].to_numpy(dtype=float), 95)) if not mc_meta.empty else -np.inf
            )
            mc_pass = bool(
                (meta_mc_p5_ann >= base_mc_p5_ann)
                and (meta_mc_p95_dd >= (base_mc_p95_dd - float(args.mc_p95_dd_allow_worse_bps)))
            )
            if mc_pass:
                promoted_source = "meta"
                promoted_guard = test_meta_guard
            else:
                promoted_source = "baseline"
                promoted_guard = test_base_guard
            m_meta_promoted = _metrics_with_risk(promoted_guard, risk_bps=risk_bps)
            mc_fail_reason = "" if mc_pass else "mc_promotion_gate_fail"

            fold_rows.append(
                {
                    "mix_id": mix_name,
                    "year": int(fold.test_year),
                    "threshold": float(best_payload["threshold"]),
                    "pt_q": float(best_payload["pt_q"]),
                    "sl_q": float(best_payload["sl_q"]),
                    "timeout_ratio": float(best_payload["timeout_ratio"]),
                    "objective": args.objective,
                    "risk_gate_policy": "strict_dd_caps",
                    "threshold_policy": "train_only",
                    "mc_pass": bool(mc_pass),
                    "mc_fail_reason": mc_fail_reason,
                    "promoted_source": promoted_source,
                    "base_trades": int(m_base["trades"]),
                    "base_sharpe": float(m_base["sharpe"]),
                    "base_cagr": float(m_base["cagr"]),
                    "base_max_daily_dd_bps": float(m_base["max_daily_dd_bps"]),
                    "base_annualized_bps": float(m_base["annualized_bps_calendar"]),
                    "meta_candidate_trades": int(m_meta_candidate["trades"]),
                    "meta_candidate_sharpe": float(m_meta_candidate["sharpe"]),
                    "meta_candidate_cagr": float(m_meta_candidate["cagr"]),
                    "meta_candidate_max_daily_dd_bps": float(m_meta_candidate["max_daily_dd_bps"]),
                    "meta_candidate_annualized_bps": float(m_meta_candidate["annualized_bps_calendar"]),
                    "meta_promoted_trades": int(m_meta_promoted["trades"]),
                    "meta_promoted_sharpe": float(m_meta_promoted["sharpe"]),
                    "meta_promoted_cagr": float(m_meta_promoted["cagr"]),
                    "meta_promoted_max_daily_dd_bps": float(m_meta_promoted["max_daily_dd_bps"]),
                    "meta_promoted_annualized_bps": float(m_meta_promoted["annualized_bps_calendar"]),
                    "delta_promoted_dd_bps": float(m_meta_promoted["max_daily_dd_bps"] - m_base["max_daily_dd_bps"]),
                    "delta_promoted_annualized_bps": float(
                        m_meta_promoted["annualized_bps_calendar"] - m_base["annualized_bps_calendar"]
                    ),
                    "delta_promoted_sharpe": float(m_meta_promoted["sharpe"] - m_base["sharpe"]),
                    "mc_base_p5_annualized_bps": float(base_mc_p5_ann),
                    "mc_meta_p5_annualized_bps": float(meta_mc_p5_ann),
                    "mc_base_p95_dd_bps": float(base_mc_p95_dd),
                    "mc_meta_p95_dd_bps": float(meta_mc_p95_dd),
                }
            )

            common_cols = {
                "mix_id": mix_name,
                "fold_year": int(fold.test_year),
                "selection_objective": args.objective,
                "risk_gate_policy": "strict_dd_caps",
                "threshold_policy": "train_only",
                "mc_pass": bool(mc_pass),
                "threshold": float(best_payload["threshold"]),
                "pt_q": float(best_payload["pt_q"]),
                "sl_q": float(best_payload["sl_q"]),
                "timeout_ratio": float(best_payload["timeout_ratio"]),
            }

            bdf = test_base_guard.copy()
            for k, v in common_cols.items():
                bdf[k] = v
            bdf["variant"] = "baseline_causal"
            bdf["promoted_source"] = "baseline"
            oos_base_trades.append(bdf)

            cdf = test_meta_guard.copy()
            for k, v in common_cols.items():
                cdf[k] = v
            cdf["variant"] = "meta_tb_candidate"
            cdf["promoted_source"] = "meta_candidate"
            oos_meta_candidate_trades.append(cdf)

            pdf = promoted_guard.copy()
            for k, v in common_cols.items():
                pdf[k] = v
            pdf["variant"] = "meta_tb_promoted"
            pdf["promoted_source"] = promoted_source
            oos_meta_promoted_trades.append(pdf)

            scored = te_short[
                ["trade_id", "pair", "timeframe", "strategy_type", "timestamp", "exit_ts", "pnl_bps"]
            ].copy()
            scored["mix_id"] = mix_name
            scored["fold_year"] = int(fold.test_year)
            scored["threshold"] = float(best_payload["threshold"])
            scored["pt_q"] = float(best_payload["pt_q"])
            scored["sl_q"] = float(best_payload["sl_q"])
            scored["timeout_ratio"] = float(best_payload["timeout_ratio"])
            scored["proba_bad_raw"] = best_payload["fit"]["proba_raw_te"].to_numpy(dtype=float)
            scored["proba_bad_calibrated"] = best_payload["fit"]["proba_cal_te"].to_numpy(dtype=float)
            scored["keep_flag"] = keep_meta_te.to_numpy(dtype=bool)
            scored["tb_label"] = best_payload["y_te"].to_numpy(dtype=int)
            scored["calibration_method"] = str(best_payload["fit"]["calib_info"]["effective_method"])
            oos_scored_rows.append(scored)

            print(
                f"    threshold={best_payload['threshold']:.2f} "
                f"| base_dd={m_base['max_daily_dd_bps']:.1f} "
                f"| meta_candidate_dd={m_meta_candidate['max_daily_dd_bps']:.1f} "
                f"| promoted={promoted_source}"
            )

    if not fold_rows:
        raise RuntimeError("No valid folds were produced.")

    folds_df = pd.DataFrame(fold_rows).sort_values(["mix_id", "year"]).reset_index(drop=True)
    grid_df = pd.concat(threshold_rows, ignore_index=True) if threshold_rows else pd.DataFrame()
    calibration_df = pd.DataFrame(calibration_rows).sort_values(["mix_id", "year"]).reset_index(drop=True)
    ablation_df = pd.DataFrame(ablation_rows).sort_values(["mix_id", "year", "score"], ascending=[True, True, False]).reset_index(drop=True)
    oos_base = pd.concat(oos_base_trades, ignore_index=True) if oos_base_trades else pd.DataFrame()
    oos_candidate = pd.concat(oos_meta_candidate_trades, ignore_index=True) if oos_meta_candidate_trades else pd.DataFrame()
    oos_promoted = pd.concat(oos_meta_promoted_trades, ignore_index=True) if oos_meta_promoted_trades else pd.DataFrame()
    scored_df = pd.concat(oos_scored_rows, ignore_index=True) if oos_scored_rows else pd.DataFrame()

    summary_rows = []
    for mix_name, _ in sorted({(r["mix_id"], None) for r in fold_rows}):
        for label, sub in [
            ("baseline_causal", oos_base[oos_base["mix_id"] == mix_name].copy()),
            ("meta_tb_candidate", oos_candidate[oos_candidate["mix_id"] == mix_name].copy()),
            ("meta_tb_promoted", oos_promoted[oos_promoted["mix_id"] == mix_name].copy()),
        ]:
            if sub.empty:
                continue
            r = _derive_risk_bps(sub, fallback=100.0)
            m = _metrics_with_risk(sub, risk_bps=r)
            summary_rows.append(
                {
                    "mix_id": mix_name,
                    "variant": label,
                    "selection_objective": args.objective,
                    "risk_gate_policy": "strict_dd_caps",
                    "threshold_policy": "train_only",
                    "mc_pass_rate": float(sub["mc_pass"].mean()) if "mc_pass" in sub.columns else np.nan,
                    **m,
                }
            )
        s = pd.DataFrame([x for x in summary_rows if x["mix_id"] == mix_name])
        if {"baseline_causal", "meta_tb_promoted"}.issubset(set(s["variant"].tolist())):
            b = s.loc[s["variant"] == "baseline_causal"].iloc[0]
            pmt = s.loc[s["variant"] == "meta_tb_promoted"].iloc[0]
            summary_rows.append(
                {
                    "mix_id": mix_name,
                    "variant": "meta_promoted_minus_baseline",
                    "selection_objective": args.objective,
                    "risk_gate_policy": "strict_dd_caps",
                    "threshold_policy": "train_only",
                    "mc_pass_rate": float(pmt["mc_pass_rate"]),
                    "trades": int(pmt["trades"] - b["trades"]),
                    "mean_pnl_per_trade_bps": float(pmt["mean_pnl_per_trade_bps"] - b["mean_pnl_per_trade_bps"]),
                    "sharpe": float(pmt["sharpe"] - b["sharpe"]),
                    "cagr": float(pmt["cagr"] - b["cagr"]),
                    "annualized_bps_calendar": float(pmt["annualized_bps_calendar"] - b["annualized_bps_calendar"]),
                    "max_daily_dd_bps": float(pmt["max_daily_dd_bps"] - b["max_daily_dd_bps"]),
                    "max_dd_pct": float(pmt["max_dd_pct"] - b["max_dd_pct"]),
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
    ablation_path = out_dir / f"{args.out_prefix}_label_ablation.csv"
    mc_paths_path = out_dir / f"{args.out_prefix}_mc_daily_paths.csv"
    mc_summary_path = out_dir / f"{args.out_prefix}_mc_daily_summary.csv"

    folds_df.to_csv(folds_path, index=False)
    grid_df.to_csv(grid_path, index=False)
    summary_df.to_csv(summary_path, index=False)
    pd.concat([oos_base, oos_candidate, oos_promoted], ignore_index=True).to_csv(trades_path, index=False)
    scored_df.to_csv(scored_path, index=False)
    calibration_df.to_csv(calib_path, index=False)
    ablation_df.to_csv(ablation_path, index=False)

    mc_rows = []
    for mix_name in sorted(summary_df["mix_id"].dropna().unique().tolist()):
        for variant, vdf in [
            ("baseline_causal", oos_base[oos_base["mix_id"] == mix_name].copy()),
            ("meta_tb_promoted", oos_promoted[oos_promoted["mix_id"] == mix_name].copy()),
        ]:
            if vdf.empty:
                continue
            mc = _block_bootstrap_daily(
                vdf,
                n_paths=int(args.mc_paths),
                block_days=int(args.mc_block_days),
                seed=int(args.random_state + (17 if variant == "meta_tb_promoted" else 0)),
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
            for col in ["annualized_bps_calendar", "max_daily_dd_bps", "sharpe_daily_bps", "cagr_notional"]:
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
    print(f"- {ablation_path}")
    if not mc_summary.empty:
        print(f"- {mc_paths_path}")
        print(f"- {mc_summary_path}")


if __name__ == "__main__":
    main()
