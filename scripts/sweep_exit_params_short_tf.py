#!/usr/bin/env python3
"""
Sweep entry-time exit parameters for short timeframes (M5/M15), DD-first.

This script:
1) Uses MOM entry events from the current event datasets (baseline entry variant).
2) Re-simulates exits per parameter combo with entry-time frozen contracts.
3) Applies causal guardrail and pair Sharpe filter.
4) Reports DD + Sharpe + PnL metrics per combo.
"""

from __future__ import annotations

import argparse
import itertools
import os
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

from behemoth.core.events import simulate_trade
from behemoth.core.exit_contract import ExitContract
from behemoth.core.timeout_policy import compute_max_hold_bars
from behemoth.core.active_leg import select_active_leg
from behemoth.config import ACTIVE_LEG_HIGH, ACTIVE_LEG_LOW
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


EVENT_PATHS = {
    "MOM": {
        "m5": ROOT / "data" / "events" / "events_m5_8yr_v3_mom.csv",
        "m15": ROOT / "data" / "events" / "events_m15_8yr_v3_mom.csv",
    },
    "REV": {
        "m5": ROOT / "data" / "events" / "events_m5_8yr_v3_rev.csv",
        "m15": ROOT / "data" / "events" / "events_m15_8yr_v3_rev.csv",
    },
}


@dataclass(frozen=True)
class TfBundle:
    pair_specs: list[tuple]
    load_pair_data: callable
    compute_kalman_states: callable
    compute_z_scores: callable
    tf_key: str


TF_BUNDLES = {
    "m5": TfBundle(M5_PAIRS, load_pair_data_m5, compute_kalman_states_m5, compute_z_scores_m5, "m5"),
    "m15": TfBundle(M15_PAIRS, load_pair_data_m15, compute_kalman_states_m15, compute_z_scores_m15, "m15"),
}


def _parse_float_grid(txt: str) -> list[float]:
    return [float(x.strip()) for x in txt.split(",") if x.strip()]


def _parse_bool_grid(txt: str) -> list[bool]:
    out = []
    for x in txt.split(","):
        v = x.strip().lower()
        if v in {"1", "true", "t", "yes", "y"}:
            out.append(True)
        elif v in {"0", "false", "f", "no", "n"}:
            out.append(False)
        elif v:
            raise ValueError(f"Invalid bool grid token: {x}")
    return out


def _build_pair_states(tf: str, pair_whitelist: list[str]) -> dict[str, dict]:
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
        z_scores = bundle.compute_z_scores(errors)
        ts_to_idx = {int(t): i for i, t in enumerate(ts)}
        states[name] = {
            "y": y,
            "x": x,
            "betas": betas,
            "z": z_scores,
            "ts": ts,
            "ts_to_idx": ts_to_idx,
        }
    return states


def _load_entries_from_events(
    tf: str,
    strategy: str,
    pair_whitelist: list[str],
    states: dict[str, dict],
) -> dict[str, list[dict]]:
    path = EVENT_PATHS[strategy][tf]
    if not path.exists():
        raise FileNotFoundError(f"Missing events file: {path}")
    df = pd.read_csv(path)
    if "pair" not in df.columns and "symbol" in df.columns:
        df = df.rename(columns={"symbol": "pair"})
    if "strategy_type" in df.columns:
        df = df[df["strategy_type"].astype(str).str.upper() == strategy].copy()
    if "entry_exit_variant" in df.columns:
        df = df[df["entry_exit_variant"].astype(str) == "baseline"].copy()
    df = df[df["pair"].isin(pair_whitelist)].copy()
    if df.empty:
        return {}

    df["timestamp"] = _normalize_ts_ns(df["timestamp"])
    if "z_score" in df.columns:
        df["z_score"] = pd.to_numeric(df["z_score"], errors="coerce")
    else:
        df["z_score"] = 0.0
    df = df.dropna(subset=["pair", "timestamp", "side", "active_leg", "z_score"]).copy()

    out: dict[str, list[dict]] = {}
    for pair, sub in df.groupby("pair", sort=True):
        rows = []
        for r in sub.itertuples(index=False):
            direction = 1 if str(r.side).upper() == "LONG" else -1
            ts = int(r.timestamp)
            st = states.get(str(pair))
            if st is None:
                continue
            idx = st["ts_to_idx"].get(ts)
            if idx is None:
                continue
            rows.append(
                {
                    "idx": int(idx),
                    "ts": ts,
                    "direction": int(direction),
                    "active_leg": str(r.active_leg),
                    "entry_z": float(r.z_score),
                }
            )
        out[str(pair)] = rows
    return out


def _build_entries_from_raw(
    strategy: str,
    states: dict[str, dict],
    min_entry_z_floor: float,
) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for pair, st in states.items():
        z = st["z"]
        betas = st["betas"]
        ts = st["ts"]
        rows: list[dict] = []
        start = 500
        end = max(start, len(z) - 500)
        for i in range(start, end):
            z_i = float(z[i])
            if abs(z_i) < min_entry_z_floor:
                continue
            active = select_active_leg(float(betas[i]), ACTIVE_LEG_LOW, ACTIVE_LEG_HIGH)
            if active is None:
                continue
            if strategy == "MOM":
                direction = 1 if z_i > 0 else -1
            else:  # REV
                direction = -1 if z_i > 0 else 1
            rows.append(
                {
                    "idx": int(i),
                    "ts": int(ts[i]),
                    "direction": int(direction),
                    "active_leg": str(active),
                    "entry_z": z_i,
                }
            )
        out[pair] = rows
    return out


def _simulate_combo(
    tf: str,
    strategy: str,
    states: dict[str, dict],
    entries: dict[str, list[dict]],
    entry_z_min: float,
    min_gap_bars: int,
    cross_zero_buffer: float,
    stop_win_level: float,
    use_stop_win: bool,
    timeout_mode: str,
    timeout_mult: float,
    sharpe_cutoff: float,
) -> dict[str, float]:
    rows = []
    max_hold_default = 500
    for pair, pair_entries in entries.items():
        st = states.get(pair)
        if st is None:
            continue
        y = st["y"]
        x = st["x"]
        z = st["z"]
        ts = st["ts"]
        last_entry_idx = -10**12

        for e in pair_entries:
            if abs(float(e["entry_z"])) < float(entry_z_min):
                continue
            idx = int(e["idx"])
            if idx - last_entry_idx < int(min_gap_bars):
                continue
            base_hold = compute_max_hold_bars(tf, abs_entry_z=abs(float(e["entry_z"])), mode=timeout_mode)
            max_hold = int(round(base_hold * timeout_mult))
            max_hold = max(1, min(max_hold, max_hold_default))

            contract = ExitContract(
                mode=timeout_mode,
                variant="sweep",
                max_hold_bars=max_hold,
                cross_zero_buffer_abs_z=float(cross_zero_buffer),
                stop_win_level_abs_z=float(stop_win_level),
                use_stop_win=bool(use_stop_win),
            )

            pnl, duration, outcome = simulate_trade(
                idx,
                int(e["direction"]),
                strategy,
                y,
                x,
                z,
                str(e["active_leg"]),
                stop=stop_win_level,
                exit_contract=contract,
            )

            if outcome == "TIMEOUT":
                exit_idx = min(idx + max_hold - 1, len(ts) - 1)
            else:
                exit_idx = min(idx + int(duration), len(ts) - 1)

            rows.append(
                {
                    "pair": pair,
                    "timestamp": int(e["ts"]),
                    "exit_ts": int(ts[exit_idx]),
                    "pnl_bps": float(pnl),
                }
            )
            last_entry_idx = idx

    if not rows:
        return {
            "raw_trades": 0,
            "guardrail_trades": 0,
            "selected_trades": 0,
            **_metrics_with_risk(pd.DataFrame(), risk_bps=100.0),
        }

    raw = pd.DataFrame(rows).sort_values(["timestamp", "pair"]).reset_index(drop=True)
    guarded = _apply_guardrail(raw)
    selected = _filter_pairs_by_sharpe(guarded, cutoff=sharpe_cutoff)
    risk_bps = _derive_risk_bps(raw, fallback=100.0)
    metrics = _metrics_with_risk(selected, risk_bps=risk_bps)
    return {
        "raw_trades": int(len(raw)),
        "guardrail_trades": int(len(guarded)),
        "selected_trades": int(len(selected)),
        **metrics,
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Sweep entry-time exit params for short TFs (M5/M15).")
    p.add_argument("--timeframes", default="m15,m5", help="comma list from: m5,m15")
    p.add_argument("--strategy", default="MOM", choices=["MOM", "REV"], help="strategy side to sweep")
    p.add_argument(
        "--entry-source",
        default="raw",
        choices=["raw", "events"],
        help="entry generator source: raw bars (true entry sweep) or existing event files",
    )
    p.add_argument("--exclude-oil", action="store_true", help="exclude oil-linked pairs")
    p.add_argument("--cross-zero-grid", default="0.0,0.1,0.15", help="comma-separated floats")
    p.add_argument("--stop-win-grid", default="3.5,4.0", help="comma-separated floats")
    p.add_argument("--use-stop-win-grid", default="true,false", help="comma-separated bools")
    p.add_argument("--entry-z-grid", default="1.5,1.8,2.0", help="comma-separated floats (>=1.5)")
    p.add_argument("--min-gap-grid", default="20,30,40", help="comma-separated ints")
    p.add_argument("--timeout-mode", default="adaptive_entry_z", choices=["adaptive_entry_z", "fixed"])
    p.add_argument("--timeout-mults", default="0.75,1.0", help="comma-separated floats")
    p.add_argument("--sharpe-cutoff", type=float, default=0.30)
    p.add_argument("--top-k", type=int, default=10)
    args = p.parse_args()

    timeframes = [x.strip() for x in args.timeframes.split(",") if x.strip()]
    for tf in timeframes:
        if tf not in TF_BUNDLES:
            raise ValueError(f"Unsupported timeframe: {tf}")

    pair_whitelist = [p for p in PAIR_WHITELIST_BASE if (not args.exclude_oil or p not in OIL_LINKED_PAIRS)]
    cross_grid = _parse_float_grid(args.cross_zero_grid)
    stop_grid = _parse_float_grid(args.stop_win_grid)
    use_stop_grid = _parse_bool_grid(args.use_stop_win_grid)
    entry_z_grid = _parse_float_grid(args.entry_z_grid)
    min_gap_grid = [int(round(v)) for v in _parse_float_grid(args.min_gap_grid)]
    timeout_mults = _parse_float_grid(args.timeout_mults)

    combos = []
    for entry_z_min, min_gap_bars, cross, stop, use_stop, tm in itertools.product(
        entry_z_grid, min_gap_grid, cross_grid, stop_grid, use_stop_grid, timeout_mults
    ):
        if args.entry_source == "events" and entry_z_min < 1.5:
            # Event files were generated with entry threshold 1.5, so lower thresholds
            # are not recoverable unless using raw-bar entry generation.
            continue
        if not use_stop and stop != stop_grid[0]:
            # stop level is irrelevant when stop-win disabled; keep one canonical value.
            continue
        combos.append((entry_z_min, min_gap_bars, cross, stop, use_stop, tm))

    out_rows = []
    for tf in timeframes:
        print(f"Building states/entries for {tf}...")
        states = _build_pair_states(tf, pair_whitelist)
        if args.entry_source == "raw":
            entries = _build_entries_from_raw(
                strategy=args.strategy,
                states=states,
                min_entry_z_floor=min(entry_z_grid),
            )
        else:
            entries = _load_entries_from_events(tf, args.strategy, pair_whitelist, states)
        print(f"{tf}: pairs={len(states)} entry_rows={sum(len(v) for v in entries.values())}")

        for entry_z_min, min_gap_bars, cross, stop, use_stop, tm in combos:
            m = _simulate_combo(
                tf=tf,
                strategy=args.strategy,
                states=states,
                entries=entries,
                entry_z_min=entry_z_min,
                min_gap_bars=min_gap_bars,
                cross_zero_buffer=cross,
                stop_win_level=stop,
                use_stop_win=use_stop,
                timeout_mode=args.timeout_mode,
                timeout_mult=tm,
                sharpe_cutoff=args.sharpe_cutoff,
            )
            out_rows.append(
                {
                    "timeframe": tf,
                    "exclude_oil": bool(args.exclude_oil),
                    "timeout_mode": args.timeout_mode,
                    "entry_source": args.entry_source,
                    "entry_z_min_abs": float(entry_z_min),
                    "min_gap_bars": int(min_gap_bars),
                    "cross_zero_buffer_abs_z": float(cross),
                    "stop_win_level_abs_z": float(stop),
                    "use_stop_win": bool(use_stop),
                    "timeout_mult": float(tm),
                    "pair_sharpe_cutoff": float(args.sharpe_cutoff),
                    **m,
                }
            )
            print(
                f"{tf} z>={entry_z_min:.2f} gap>={min_gap_bars} cross={cross:.2f} "
                f"stop={stop:.2f} use_stop={use_stop} tm={tm:.2f} "
                f"-> mean={m['mean_pnl_per_trade_bps']:.2f} sharpe={m['sharpe']:.3f} maxDDday={m['max_daily_dd_bps']:.1f}"
            )

    out = pd.DataFrame(out_rows)
    out["strategy_type"] = args.strategy
    out_dir = ROOT / "data" / "analysis"
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = "no_oil" if args.exclude_oil else "with_oil"
    out_path = out_dir / f"exit_param_sweep_short_tf_{args.strategy.lower()}_{args.entry_source}_{suffix}.csv"
    out.to_csv(out_path, index=False)

    print(f"\nSaved sweep results: {out_path}")
    for tf, g in out.groupby("timeframe", sort=True):
        g_nonzero = g[g["trades"] > 0].copy()
        if g_nonzero.empty:
            print(f"\nTop {args.top_k} DD-first candidates for {tf}: no non-zero trade rows")
            continue
        print(f"\nTop {args.top_k} DD-first candidates for {tf}:")
        dd_top = g_nonzero.sort_values(
            ["max_daily_dd_bps", "worst_single_day_bps", "sharpe", "mean_pnl_per_trade_bps"],
            ascending=[False, False, False, False],
        ).head(args.top_k)
        cols = [
            "entry_z_min_abs",
            "min_gap_bars",
            "cross_zero_buffer_abs_z",
            "stop_win_level_abs_z",
            "use_stop_win",
            "timeout_mult",
            "trades",
            "mean_pnl_per_trade_bps",
            "sharpe",
            "cagr",
            "worst_single_day_bps",
            "max_daily_dd_bps",
            "max_dd_pct",
        ]
        print(dd_top[cols].to_string(index=False))


if __name__ == "__main__":
    main()
