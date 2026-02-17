#!/usr/bin/env python3
"""
Sweep causal strategy-family mixes focused on exposure reduction.

Stage-A families implemented:
- MOM_PERSIST
- MOM_BURST
- REV_EXHAUSTION
- REV_QUICKFAIL

For each timeframe mix (m5/m15/m60), this script:
1) Builds trades from raw bar states with causal entry/exit rules.
2) Applies causal guardrail and pair Sharpe filter.
3) Computes return, DD, and exposure metrics.
4) Scores/ranks mixes under exposure-reduction constraints.
"""

from __future__ import annotations

import argparse
import itertools
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from behemoth.config import ACTIVE_LEG_HIGH, ACTIVE_LEG_LOW
from behemoth.core.active_leg import select_active_leg
from behemoth.core.exit_contract import build_exit_contract
from pipelines.build_events_h1 import (
    PAIRS as H1_PAIRS,
    compute_kalman_states as compute_kalman_states_h1,
    compute_z_scores as compute_z_scores_h1,
    load_pair_data as load_pair_data_h1,
)
from pipelines.build_events_m15 import (
    PAIRS as M15_PAIRS,
    compute_kalman_states as compute_kalman_states_m15,
    compute_z_scores as compute_z_scores_m15,
    load_pair_data as load_pair_data_m15,
)
from pipelines.build_events_m5 import (
    PAIRS as M5_PAIRS,
    compute_kalman_states as compute_kalman_states_m5,
    compute_z_scores as compute_z_scores_m5,
    load_pair_data as load_pair_data_m5,
)
from scripts.report_strategy_fx_comm_multi_tf import (
    OIL_LINKED_PAIRS,
    PAIR_WHITELIST_BASE,
    _apply_guardrail,
    _derive_risk_bps,
    _filter_pairs_by_sharpe,
    _metrics_with_risk,
    _normalize_ts_ns,
)


@dataclass(frozen=True)
class TfBundle:
    pair_specs: list[tuple]
    load_pair_data: callable
    compute_kalman_states: callable
    compute_z_scores: callable
    tf_key: str
    bar_minutes: int


@dataclass(frozen=True)
class FamilySpec:
    family: str
    strategy_type: str
    z_enter: float
    min_gap: int
    n_confirm: int
    vel_min: float
    accel_min: float
    accel_max: float
    hold_mult: float
    z_stop: float
    timeout_mode: str
    exit_variant: str
    quickfail_bars: int
    quickfail_progress_frac: float
    mom_flip_bars: int


TF_BUNDLES = {
    "m5": TfBundle(M5_PAIRS, load_pair_data_m5, compute_kalman_states_m5, compute_z_scores_m5, "m5", 5),
    "m15": TfBundle(M15_PAIRS, load_pair_data_m15, compute_kalman_states_m15, compute_z_scores_m15, "m15", 15),
    "m60": TfBundle(H1_PAIRS, load_pair_data_h1, compute_kalman_states_h1, compute_z_scores_h1, "m60", 60),
}


FAMILY_LIBRARY: dict[str, FamilySpec] = {
    "MOM_PERSIST": FamilySpec(
        family="MOM_PERSIST",
        strategy_type="MOM",
        z_enter=1.7,
        min_gap=20,
        n_confirm=3,
        vel_min=0.0,
        accel_min=0.0,
        accel_max=0.0,
        hold_mult=0.90,
        z_stop=3.2,
        timeout_mode="adaptive_entry_z",
        exit_variant="baseline",
        quickfail_bars=0,
        quickfail_progress_frac=0.0,
        mom_flip_bars=3,
    ),
    "MOM_BURST": FamilySpec(
        family="MOM_BURST",
        strategy_type="MOM",
        z_enter=1.9,
        min_gap=30,
        n_confirm=1,
        vel_min=0.18,
        accel_min=0.08,
        accel_max=0.0,
        hold_mult=0.70,
        z_stop=2.9,
        timeout_mode="adaptive_entry_z",
        exit_variant="soft_cross",
        quickfail_bars=0,
        quickfail_progress_frac=0.0,
        mom_flip_bars=2,
    ),
    "REV_EXHAUSTION": FamilySpec(
        family="REV_EXHAUSTION",
        strategy_type="REV",
        z_enter=2.6,
        min_gap=28,
        n_confirm=1,
        vel_min=0.0,
        accel_min=0.0,
        accel_max=0.10,
        hold_mult=0.75,
        z_stop=3.1,
        timeout_mode="adaptive_entry_z",
        exit_variant="soft_cross",
        quickfail_bars=0,
        quickfail_progress_frac=0.0,
        mom_flip_bars=0,
    ),
    "REV_QUICKFAIL": FamilySpec(
        family="REV_QUICKFAIL",
        strategy_type="REV",
        z_enter=2.3,
        min_gap=35,
        n_confirm=1,
        vel_min=0.0,
        accel_min=0.0,
        accel_max=0.25,
        hold_mult=0.60,
        z_stop=3.0,
        timeout_mode="adaptive_entry_z",
        exit_variant="baseline",
        quickfail_bars=18,
        quickfail_progress_frac=0.10,
        mom_flip_bars=0,
    ),
}


def _parse_grid(s: str) -> list[str]:
    return [x.strip() for x in str(s).split(",") if x.strip()]


def _parse_family_mixes(s: str, families: list[str]) -> list[dict[str, str]]:
    raw = str(s).strip()
    if raw.lower() in {"all", "*"}:
        return [{"m5": a, "m15": b, "m60": c} for a, b, c in itertools.product(families, repeat=3)]

    mixes: list[dict[str, str]] = []
    parts = [x.strip() for x in raw.split(";") if x.strip()]
    for part in parts:
        m: dict[str, str] = {}
        for tok in [z.strip() for z in part.split(",") if z.strip()]:
            if "=" not in tok:
                raise ValueError(f"Invalid mix token: {tok}")
            tf, fam = tok.split("=", 1)
            tf = tf.strip().lower()
            fam = fam.strip().upper()
            if tf not in {"m5", "m15", "m60"}:
                raise ValueError(f"Unsupported timeframe in mix: {tf}")
            if fam not in families:
                raise ValueError(f"Unsupported family in mix: {fam}")
            m[tf] = fam
        if set(m.keys()) != {"m5", "m15", "m60"}:
            raise ValueError(f"Mix must specify m5,m15,m60 exactly: {part}")
        mixes.append(m)

    if not mixes:
        mixes.append({"m5": "MOM_BURST", "m15": "REV_EXHAUSTION", "m60": "MOM_PERSIST"})
    return mixes


def _mix_id(mix: dict[str, str]) -> str:
    return f"m5_{mix['m5'].lower()}__m15_{mix['m15'].lower()}__m60_{mix['m60'].lower()}"


def _build_pair_states(tf: str, pair_whitelist: list[str], vel_lookback: int) -> dict[str, dict]:
    bundle = TF_BUNDLES[tf]
    states: dict[str, dict] = {}
    for name, fx, fy, cx, cy, *_ in bundle.pair_specs:
        if name not in pair_whitelist:
            continue
        df = bundle.load_pair_data(fx, fy, cx, cy)
        if df is None or len(df) == 0:
            continue

        y = np.log(df["Y"].to_numpy())
        x = np.log(df["X"].to_numpy())
        ts = _normalize_ts_ns(df["timestamp"]).to_numpy(dtype="int64")
        betas, errors, _ = bundle.compute_kalman_states(y, x)
        z = bundle.compute_z_scores(errors)

        z_s = pd.Series(z)
        vel_fast = z_s.diff(int(max(1, vel_lookback))).fillna(0.0).to_numpy(dtype=float)
        accel_fast = pd.Series(vel_fast).diff(int(max(1, vel_lookback))).fillna(0.0).to_numpy(dtype=float)
        vel_1 = z_s.diff(1).fillna(0.0).to_numpy(dtype=float)

        states[name] = {
            "ts": ts,
            "y": y,
            "x": x,
            "betas": betas,
            "z": z,
            "vel_fast": vel_fast,
            "accel_fast": accel_fast,
            "vel_1": vel_1,
        }
    return states


def _pnl_bps(prices: np.ndarray, direction: int, entry_idx: int, exit_idx: int) -> float:
    entry_price = float(prices[entry_idx])
    exit_price = float(prices[exit_idx])
    if direction >= 0:
        return (exit_price - entry_price) * 10000.0
    return -(exit_price - entry_price) * 10000.0


def _entry_direction(spec: FamilySpec, i: int, st: dict) -> int | None:
    z = float(st["z"][i])
    az = abs(z)
    if az < float(spec.z_enter):
        return None

    vel = float(st["vel_fast"][i])
    acc = float(st["accel_fast"][i])

    if spec.family == "MOM_PERSIST":
        n = int(max(1, spec.n_confirm))
        if i < n:
            return None
        win = st["z"][i - n + 1 : i + 1]
        if len(win) < n:
            return None
        s = np.sign(z)
        if s == 0:
            return None
        if np.any(np.sign(win) != s):
            return None
        if float(np.min(np.abs(win))) < (float(spec.z_enter) * 0.80):
            return None
        return 1 if z > 0.0 else -1

    if spec.family == "MOM_BURST":
        if abs(vel) < float(spec.vel_min) or abs(acc) < float(spec.accel_min):
            return None
        if np.sign(vel) != np.sign(z):
            return None
        return 1 if z > 0.0 else -1

    if spec.family in {"REV_EXHAUSTION", "REV_QUICKFAIL"}:
        if np.sign(vel) == np.sign(z):
            return None
        if abs(acc) > float(spec.accel_max):
            return None
        return -1 if z > 0.0 else 1

    return None


def _simulate_family_trade(tf: str, spec: FamilySpec, st: dict, entry_idx: int, direction: int, active_leg: str) -> tuple[float, int, str, int]:
    prices = st["y"] if active_leg == "Y" else st["x"]
    z = st["z"]
    vel_1 = st["vel_1"]

    entry_z = float(z[entry_idx])
    contract = build_exit_contract(
        timeframe=tf,
        entry_z=entry_z,
        timeout_mode=str(spec.timeout_mode),
        variant=str(spec.exit_variant),
        z_stop=float(spec.z_stop),
    )
    max_hold = int(max(1, min(500, round(float(contract.max_hold_bars) * float(spec.hold_mult)))))

    cross = float(contract.cross_zero_buffer_abs_z)
    stop = float(contract.stop_win_level_abs_z)
    use_stop = bool(contract.use_stop_win)

    end_idx = min(entry_idx + max_hold, len(z) - 1)
    opp_streak = 0
    entry_abs_z = abs(entry_z)

    for j in range(entry_idx + 1, end_idx + 1):
        z_j = float(z[j])

        if spec.family == "REV_QUICKFAIL":
            bars = j - entry_idx
            if bars >= int(spec.quickfail_bars):
                progressed = abs(z_j) <= (entry_abs_z * (1.0 - float(spec.quickfail_progress_frac)))
                if not progressed:
                    return _pnl_bps(prices, direction, entry_idx, j), int(bars), "STALE_KILL", int(j)

        if spec.family == "MOM_PERSIST":
            if float(vel_1[j]) * float(direction) < 0.0:
                opp_streak += 1
            else:
                opp_streak = 0
            if opp_streak >= int(spec.mom_flip_bars):
                return _pnl_bps(prices, direction, entry_idx, j), int(j - entry_idx), "MOM_FLIP", int(j)

        if spec.strategy_type == "MOM":
            if direction == 1:
                if z_j < -cross:
                    return _pnl_bps(prices, direction, entry_idx, j), int(j - entry_idx), "LOSS_REV", int(j)
                if use_stop and z_j > stop:
                    return _pnl_bps(prices, direction, entry_idx, j), int(j - entry_idx), "WIN_MOM", int(j)
            else:
                if z_j > cross:
                    return _pnl_bps(prices, direction, entry_idx, j), int(j - entry_idx), "LOSS_REV", int(j)
                if use_stop and z_j < -stop:
                    return _pnl_bps(prices, direction, entry_idx, j), int(j - entry_idx), "WIN_MOM", int(j)
        else:
            if direction == 1:
                if z_j > cross:
                    return _pnl_bps(prices, direction, entry_idx, j), int(j - entry_idx), "WIN_REV", int(j)
                if use_stop and z_j < -stop:
                    return _pnl_bps(prices, direction, entry_idx, j), int(j - entry_idx), "LOSS_MOM", int(j)
            else:
                if z_j < -cross:
                    return _pnl_bps(prices, direction, entry_idx, j), int(j - entry_idx), "WIN_REV", int(j)
                if use_stop and z_j > stop:
                    return _pnl_bps(prices, direction, entry_idx, j), int(j - entry_idx), "LOSS_MOM", int(j)

    return _pnl_bps(prices, direction, entry_idx, end_idx), int(end_idx - entry_idx), "TIMEOUT", int(end_idx)


def _generate_family_trades(tf: str, spec: FamilySpec, states: dict[str, dict]) -> pd.DataFrame:
    rows: list[dict] = []
    warm = 500

    for pair, st in states.items():
        z = st["z"]
        betas = st["betas"]
        ts = st["ts"]

        last_entry = -10**12
        last_exit = -1

        start = max(warm, int(spec.n_confirm) + 1)
        stop = max(start, len(z) - warm)
        for i in range(start, stop):
            if i <= last_exit:
                continue
            if (i - last_entry) < int(spec.min_gap):
                continue

            direction = _entry_direction(spec, i, st)
            if direction is None:
                continue

            active_leg = select_active_leg(float(betas[i]), ACTIVE_LEG_LOW, ACTIVE_LEG_HIGH)
            if active_leg is None:
                continue

            pnl, dur, outcome, exit_idx = _simulate_family_trade(tf, spec, st, i, direction, active_leg)
            if exit_idx <= i:
                continue

            rows.append(
                {
                    "pair": str(pair),
                    "timeframe": tf,
                    "strategy_type": str(spec.strategy_type),
                    "strategy_family": str(spec.family),
                    "timestamp": int(ts[i]),
                    "exit_ts": int(ts[exit_idx]),
                    "pnl_bps": float(pnl),
                    "duration_bars": int(dur),
                    "max_hold_bars": int(max(1, round(dur))),
                    "z_score": float(z[i]),
                    "z_velocity": float(st["vel_fast"][i]),
                    "z_accel": float(st["accel_fast"][i]),
                    "active_leg": str(active_leg),
                    "side": "LONG" if direction > 0 else "SHORT",
                    "entry_idx": int(i),
                    "exit_idx": int(exit_idx),
                    "outcome": str(outcome),
                }
            )
            last_entry = i
            last_exit = exit_idx

    if not rows:
        return pd.DataFrame(columns=[
            "pair", "timeframe", "strategy_type", "strategy_family", "timestamp", "exit_ts", "pnl_bps", "duration_bars", "max_hold_bars", "z_score", "z_velocity", "z_accel", "active_leg", "side", "entry_idx", "exit_idx", "outcome"
        ])

    return pd.DataFrame(rows).sort_values(["timestamp", "pair"]).reset_index(drop=True)


def _norm01(s: pd.Series) -> pd.Series:
    x = pd.to_numeric(s, errors="coerce").astype(float)
    lo = float(x.min())
    hi = float(x.max())
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return pd.Series(np.full(len(x), 0.5, dtype=float), index=x.index)
    return (x - lo) / (hi - lo)


def _select_comparator(summary: pd.DataFrame, comparator_file: Path | None, comparator_mix: str) -> dict[str, float]:
    if comparator_mix:
        m = summary.loc[summary["mix_id"].astype(str) == str(comparator_mix)]
        if not m.empty:
            r = m.sort_values(["sharpe", "annualized_bps_calendar"], ascending=[False, False]).iloc[0]
            return {
                "mix_id": str(r["mix_id"]),
                "sharpe": float(r["sharpe"]),
                "annualized_bps_calendar": float(r["annualized_bps_calendar"]),
                "max_daily_dd_bps": float(r["max_daily_dd_bps"]),
                "worst_single_day_bps": float(r["worst_single_day_bps"]),
                "time_in_market_pct": float(r["time_in_market_pct"]),
            }

    if comparator_file is not None and comparator_file.exists():
        ext = pd.read_csv(comparator_file)
        need = {"mix_id", "variant", "sharpe", "annualized_bps_calendar", "max_daily_dd_bps"}
        if need.issubset(set(ext.columns)):
            ext = ext[ext["variant"].astype(str) == "meta_tb_promoted"].copy()
            if not ext.empty:
                ext = ext.sort_values(["sharpe", "annualized_bps_calendar"], ascending=[False, False])
                top = ext.iloc[0]
                return {
                    "mix_id": str(top["mix_id"]),
                    "sharpe": float(top["sharpe"]),
                    "annualized_bps_calendar": float(top["annualized_bps_calendar"]),
                    "max_daily_dd_bps": float(top["max_daily_dd_bps"]),
                    "worst_single_day_bps": float(top["worst_single_day_bps"]) if "worst_single_day_bps" in ext.columns else float(top["max_daily_dd_bps"]),
                    "time_in_market_pct": float(top["time_in_market_pct"]) if "time_in_market_pct" in ext.columns else np.nan,
                }

    top = summary.sort_values(["sharpe", "annualized_bps_calendar"], ascending=[False, False]).iloc[0]
    return {
        "mix_id": str(top["mix_id"]),
        "sharpe": float(top["sharpe"]),
        "annualized_bps_calendar": float(top["annualized_bps_calendar"]),
        "max_daily_dd_bps": float(top["max_daily_dd_bps"]),
        "worst_single_day_bps": float(top["worst_single_day_bps"]),
        "time_in_market_pct": float(top["time_in_market_pct"]),
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Sweep causal strategy-family mixes with exposure-focused ranking.")
    p.add_argument("--exclude-oil", action="store_true", default=True)
    p.add_argument("--families", default="MOM_PERSIST,MOM_BURST,REV_EXHAUSTION,REV_QUICKFAIL")
    p.add_argument(
        "--mixes",
        default="all",
        help="semicolon-separated family mixes, e.g. 'm5=MOM_BURST,m15=REV_EXHAUSTION,m60=MOM_PERSIST' or 'all'",
    )
    p.add_argument("--pair-sharpe-cutoff", type=float, default=0.30)
    p.add_argument("--min-time-reduction-frac", type=float, default=0.30)
    p.add_argument("--max-sharpe-drop-frac", type=float, default=0.15)
    p.add_argument("--max-annualized-drop-frac", type=float, default=0.20)
    p.add_argument(
        "--min-dd-improve-frac",
        type=float,
        default=0.15,
        help="minimum required improvement fraction in worst_single_day_bps (single-day DD proxy)",
    )
    p.add_argument("--min-eligible", type=int, default=2)
    p.add_argument("--adaptive-gate-relax", action="store_true", default=True)
    p.add_argument("--no-adaptive-gate-relax", dest="adaptive_gate_relax", action="store_false")
    p.add_argument("--max-relax-steps", type=int, default=12)
    p.add_argument("--relax-time-mult", type=float, default=0.85)
    p.add_argument("--relax-dd-mult", type=float, default=0.80)
    p.add_argument("--relax-sharpe-step", type=float, default=0.10)
    p.add_argument("--relax-annualized-step", type=float, default=0.10)
    p.add_argument("--top-k", type=int, default=5)
    p.add_argument("--vel-lookback", type=int, default=20)
    p.add_argument("--comparator-summary", default="data/analysis/meta_tb_mixed_no_oil_allmix_summary.csv")
    p.add_argument("--comparator-mix", default="")
    p.add_argument("--out-prefix", default="strategy_family_sweep_no_oil")
    args = p.parse_args()

    pair_whitelist = list(PAIR_WHITELIST_BASE)
    if args.exclude_oil:
        pair_whitelist = [x for x in pair_whitelist if x not in OIL_LINKED_PAIRS]

    families = [f.upper() for f in _parse_grid(args.families)]
    for f in families:
        if f not in FAMILY_LIBRARY:
            raise ValueError(f"Unsupported family: {f}")

    mixes = _parse_family_mixes(args.mixes, families=families)
    print(f"Building states for whitelist={len(pair_whitelist)} pairs...")
    state_cache = {
        tf: _build_pair_states(tf, pair_whitelist=pair_whitelist, vel_lookback=int(args.vel_lookback))
        for tf in ["m5", "m15", "m60"]
    }

    family_trades: dict[tuple[str, str], pd.DataFrame] = {}
    for tf in ["m5", "m15", "m60"]:
        for fam in families:
            print(f"Simulating family {fam} on {tf}...")
            fam_df = _generate_family_trades(tf, FAMILY_LIBRARY[fam], state_cache[tf])
            family_trades[(tf, fam)] = fam_df
            print(f"  trades={len(fam_df)}")

    summary_rows: list[dict] = []
    selected_trade_frames: list[pd.DataFrame] = []

    mix_to_guarded: dict[str, pd.DataFrame] = {}

    for mix in mixes:
        mix_id = _mix_id(mix)
        parts = [family_trades[("m5", mix["m5"])], family_trades[("m15", mix["m15"])], family_trades[("m60", mix["m60"])]]
        raw = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
        raw = raw.sort_values(["timestamp", "pair"]).reset_index(drop=True)

        guarded = _apply_guardrail(raw)
        guarded = _filter_pairs_by_sharpe(guarded, cutoff=float(args.pair_sharpe_cutoff))
        risk_bps = _derive_risk_bps(raw, fallback=100.0)
        metrics = _metrics_with_risk(guarded, risk_bps=risk_bps)
        mix_to_guarded[mix_id] = guarded

        summary_rows.append(
            {
                "mix_id": mix_id,
                "m5_family": mix["m5"],
                "m15_family": mix["m15"],
                "m60_family": mix["m60"],
                "raw_trades": int(len(raw)),
                "guardrail_pair_filtered_trades": int(len(guarded)),
                **metrics,
            }
        )

    summary = pd.DataFrame(summary_rows)
    if summary.empty:
        raise RuntimeError("No strategy-family mix produced any rows.")

    comparator = _select_comparator(
        summary=summary,
        comparator_file=(ROOT / args.comparator_summary) if args.comparator_summary else None,
        comparator_mix=args.comparator_mix,
    )

    if not np.isfinite(float(comparator.get("time_in_market_pct", np.nan))):
        # External comparator summaries may predate exposure columns.
        fallback_time = float(
            summary.sort_values(["sharpe", "annualized_bps_calendar"], ascending=[False, False]).iloc[0][
                "time_in_market_pct"
            ]
        )
        comparator["time_in_market_pct"] = fallback_time

    comp_sharpe = float(comparator["sharpe"])
    comp_ann = float(comparator["annualized_bps_calendar"])
    comp_dd = float(comparator["max_daily_dd_bps"])
    comp_worst_day = float(comparator.get("worst_single_day_bps", comparator["max_daily_dd_bps"]))
    comp_time = float(comparator["time_in_market_pct"])

    summary["comparator_mix_id"] = str(comparator["mix_id"])
    summary["comparator_sharpe"] = comp_sharpe
    summary["comparator_annualized_bps"] = comp_ann
    summary["comparator_max_daily_dd_bps"] = comp_dd
    summary["comparator_worst_single_day_bps"] = comp_worst_day
    summary["comparator_time_in_market_pct"] = comp_time

    summary["delta_sharpe"] = summary["sharpe"] - comp_sharpe
    summary["delta_annualized_bps"] = summary["annualized_bps_calendar"] - comp_ann
    summary["delta_max_daily_dd_bps"] = summary["max_daily_dd_bps"] - comp_dd
    summary["delta_worst_single_day_bps"] = summary["worst_single_day_bps"] - comp_worst_day
    summary["delta_time_in_market_pct"] = summary["time_in_market_pct"] - comp_time

    summary["sharpe_drop_frac"] = np.where(comp_sharpe > 1e-9, (comp_sharpe - summary["sharpe"]) / comp_sharpe, 0.0)
    summary["annualized_drop_frac"] = np.where(comp_ann > 1e-9, (comp_ann - summary["annualized_bps_calendar"]) / comp_ann, 0.0)
    summary["dd_improve_frac"] = np.where(abs(comp_dd) > 1e-9, summary["delta_max_daily_dd_bps"] / abs(comp_dd), 0.0)
    summary["single_day_dd_improve_frac"] = np.where(
        abs(comp_worst_day) > 1e-9,
        summary["delta_worst_single_day_bps"] / abs(comp_worst_day),
        0.0,
    )
    if np.isfinite(comp_time) and comp_time > 1e-9:
        summary["time_reduction_frac"] = (comp_time - summary["time_in_market_pct"]) / comp_time
    else:
        summary["time_reduction_frac"] = 0.0

    summary["score"] = (
        0.35 * _norm01(summary["time_reduction_frac"])
        + 0.30 * _norm01(summary["single_day_dd_improve_frac"])
        + 0.20 * _norm01(summary["sharpe"])
        + 0.15 * _norm01(summary["annualized_bps_calendar"])
    )

    min_time_gate = float(args.min_time_reduction_frac)
    max_sharpe_gate = float(args.max_sharpe_drop_frac)
    max_annualized_gate = float(args.max_annualized_drop_frac)
    min_dd_gate = float(args.min_dd_improve_frac)
    relax_steps = 0

    def _eligible_mask() -> pd.Series:
        return (
            (summary["time_reduction_frac"] >= float(min_time_gate))
            & (summary["sharpe_drop_frac"] <= float(max_sharpe_gate))
            & (summary["annualized_drop_frac"] <= float(max_annualized_gate))
            & (summary["single_day_dd_improve_frac"] >= float(min_dd_gate))
            & (summary["trades"] > 200)
        )

    eligible = _eligible_mask()
    target_eligible = max(1, int(args.min_eligible))

    while (
        bool(args.adaptive_gate_relax)
        and int(eligible.sum()) < target_eligible
        and relax_steps < int(max(0, args.max_relax_steps))
    ):
        relax_steps += 1
        min_time_gate = float(min_time_gate * float(args.relax_time_mult))
        min_dd_gate = float(min_dd_gate * float(args.relax_dd_mult))
        max_sharpe_gate = float(min(1.50, max_sharpe_gate + float(args.relax_sharpe_step)))
        max_annualized_gate = float(min(1.50, max_annualized_gate + float(args.relax_annualized_step)))
        eligible = _eligible_mask()

    forced_fill = pd.Series(False, index=summary.index)
    if int(eligible.sum()) < target_eligible:
        n_need = int(target_eligible - int(eligible.sum()))
        fill_idx = (
            summary.loc[~eligible]
            .sort_values(["score", "sharpe", "annualized_bps_calendar"], ascending=[False, False, False])
            .head(n_need)
            .index
        )
        if len(fill_idx):
            eligible.loc[fill_idx] = True
            forced_fill.loc[fill_idx] = True

    summary["eligible"] = eligible
    summary["forced_eligible"] = forced_fill
    summary["eligibility_policy"] = np.where(
        summary["forced_eligible"],
        "forced_rank_fill",
        np.where(relax_steps > 0, "adaptive_relaxed", "strict"),
    )
    summary["eligibility_relax_steps"] = int(relax_steps)
    summary["eligibility_target_min"] = int(target_eligible)
    summary["effective_min_time_reduction_frac"] = float(min_time_gate)
    summary["effective_max_sharpe_drop_frac"] = float(max_sharpe_gate)
    summary["effective_max_annualized_drop_frac"] = float(max_annualized_gate)
    summary["effective_min_dd_improve_frac"] = float(min_dd_gate)

    ranking = summary[summary["eligible"]].copy()
    if ranking.empty:
        ranking = summary.copy()

    ranking = ranking.sort_values(
        ["score", "sharpe", "annualized_bps_calendar", "single_day_dd_improve_frac", "time_reduction_frac"],
        ascending=[False, False, False, False, False],
    ).reset_index(drop=True)
    ranking["rank"] = np.arange(1, len(ranking) + 1)

    top = ranking.head(max(1, int(args.top_k))).copy()
    for r in top.itertuples(index=False):
        mix_id = str(r.mix_id)
        g = mix_to_guarded.get(mix_id)
        if g is None or g.empty:
            continue
        out = g.copy()
        out["mix_id"] = mix_id
        out["variant"] = "family_selected"
        out["rank"] = int(r.rank)
        out["selection_score"] = float(r.score)
        out["eligible"] = bool(r.eligible)
        selected_trade_frames.append(out)

    out_dir = ROOT / "data" / "analysis"
    out_dir.mkdir(parents=True, exist_ok=True)

    summary_path = out_dir / f"{args.out_prefix}_summary.csv"
    rank_path = out_dir / f"{args.out_prefix}_ranking.csv"
    selected_trades_path = out_dir / f"{args.out_prefix}_selected_trades.csv"

    summary.sort_values(["score", "sharpe"], ascending=[False, False]).to_csv(summary_path, index=False)
    ranking.to_csv(rank_path, index=False)
    if selected_trade_frames:
        pd.concat(selected_trade_frames, ignore_index=True).to_csv(selected_trades_path, index=False)
    else:
        pd.DataFrame().to_csv(selected_trades_path, index=False)

    print("Comparator:")
    print(comparator)
    print("\nTop selected mixes:")
    cols = [
        "rank",
        "mix_id",
        "trades",
        "mean_pnl_per_trade_bps",
        "sharpe",
        "annualized_bps_calendar",
        "max_daily_dd_bps",
        "worst_single_day_bps",
        "time_in_market_pct",
        "single_day_dd_improve_frac",
        "time_reduction_frac",
        "eligible",
        "forced_eligible",
        "eligibility_policy",
        "score",
    ]
    print(top[cols].to_string(index=False))
    print("\nSaved:")
    print(f"- {summary_path}")
    print(f"- {rank_path}")
    print(f"- {selected_trades_path}")


if __name__ == "__main__":
    main()
