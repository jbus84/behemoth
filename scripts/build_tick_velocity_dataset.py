#!/usr/bin/env python3
"""Build causal velocity datasets from fixed-tick bars.

Primary intent:
- Build modeling-ready datasets with causal, lagged rolling features.
- Preserve strict time ordering for all rolling statistics.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

try:
    from scripts.canonical_tick_feed import DEFAULT_CANONICAL_ROOT
except ModuleNotFoundError:
    from canonical_tick_feed import DEFAULT_CANONICAL_ROOT

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TICK_ROOT = str(DEFAULT_CANONICAL_ROOT)
DEFAULT_TICKBAR_DIR = "data/global_tickbars"
DEFAULT_OUT_DIR = "data/analysis/tick_velocity"


def _is_utc_tz(tz: Any) -> bool:
    if tz is None:
        return False
    txt = str(tz).strip().upper()
    return txt in {"UTC", "UTC+00:00", "UTC+00:00:00"}


def _require_utc_timestamp(s: pd.Series, *, column: str, source: Path) -> pd.Series:
    parsed = pd.to_datetime(s, errors="coerce", utc=False)
    try:
        tz = parsed.dt.tz
    except Exception:
        tz = None
    if not _is_utc_tz(tz):
        raise ValueError(
            f"{source.name}: column '{column}' must be timezone-aware UTC; received tz={tz!r}"
        )
    return parsed.dt.tz_convert("UTC")


def _parse_symbols(raw: str | None) -> list[str]:
    if raw is None or not str(raw).strip():
        return []
    return [x.strip().upper() for x in str(raw).split(",") if x.strip()]


def _parse_int_list(raw: str) -> list[int]:
    out: list[int] = []
    for tok in str(raw).split(","):
        t = tok.strip()
        if not t:
            continue
        out.append(int(t))
    return out


def _parse_bar_ticks_grid(raw: str | None, fallback: int) -> list[int]:
    vals = _parse_int_list(str(raw)) if (raw is not None and str(raw).strip()) else [int(fallback)]
    vals = sorted(set(int(v) for v in vals if int(v) > 0))
    if not vals:
        raise ValueError("bar ticks grid must contain positive integers")
    return vals


def _pip_size(symbol: str) -> float:
    s = str(symbol).upper().strip()
    if s.endswith("JPY"):
        return 0.01
    if s.startswith("XAU"):
        return 0.1
    if s.startswith("XAG"):
        return 0.01
    return 0.0001


def _infer_symbols_from_tickbars(tickbar_dir: Path, bar_ticks: int) -> list[str]:
    pat = f"*_{int(bar_ticks)}tick.parquet"
    out: list[str] = []
    for p in sorted(tickbar_dir.glob(pat)):
        name = p.name.replace(f"_{int(bar_ticks)}tick.parquet", "").strip().upper()
        if name:
            out.append(name)
    return sorted(set(out))


def _infer_symbols_from_tick_root(tick_root: Path) -> list[str]:
    if not tick_root.exists():
        return []
    return sorted([p.name.upper() for p in tick_root.iterdir() if p.is_dir()])


def _ensure_tickbar(
    *,
    symbol: str,
    tickbar_dir: Path,
    tick_root: Path,
    bar_ticks: int,
    price_source: str,
    timestamp_mode: str,
    overwrite: bool,
) -> Path:
    out = tickbar_dir / f"{symbol}_{int(bar_ticks)}tick.parquet"
    if out.exists() and not overwrite:
        return out

    cmd = [
        sys.executable,
        str(ROOT / "scripts/build_global_tick_bars.py"),
        "--tick-root",
        str(tick_root),
        "--output-dir",
        str(tickbar_dir),
        "--symbols",
        str(symbol),
        "--base-ticks",
        str(int(bar_ticks)),
        "--aggregate-multiples",
        "1",
        "--price-source",
        str(price_source),
        "--timestamp-mode",
        str(timestamp_mode),
    ]
    if overwrite:
        cmd.append("--overwrite")

    subprocess.run(cmd, check=True)
    if not out.exists():
        raise FileNotFoundError(f"failed to build {out}")
    return out


def _build_symbol_dataset(
    *,
    symbol: str,
    bar_path: Path,
    bar_ticks: int,
    vel_horizons: list[int],
    target_horizons: list[int],
    vol_window: int,
    cost_window: int,
) -> pd.DataFrame:
    req = ["timestamp", "close_ts", "open", "high", "low", "close", "spread", "tick_volume"]
    d = pd.read_parquet(bar_path)

    miss = [c for c in req if c not in d.columns]
    if miss:
        raise ValueError(f"{bar_path.name}: missing columns: {miss}")

    out = pd.DataFrame(
        {
            "symbol": str(symbol).upper(),
            "bar_ticks": int(bar_ticks),
            "timestamp": _require_utc_timestamp(
                d["timestamp"], column="timestamp", source=bar_path
            ),
            "close_ts": _require_utc_timestamp(d["close_ts"], column="close_ts", source=bar_path),
            "open": pd.to_numeric(d["open"], errors="coerce").astype(float),
            "high": pd.to_numeric(d["high"], errors="coerce").astype(float),
            "low": pd.to_numeric(d["low"], errors="coerce").astype(float),
            "close": pd.to_numeric(d["close"], errors="coerce").astype(float),
            "spread": pd.to_numeric(d["spread"], errors="coerce").astype(float),
            "tick_volume": pd.to_numeric(d["tick_volume"], errors="coerce").astype(float),
        }
    )

    for c in ["high_pos_tick", "low_pos_tick", "hl_first", "hl_pos_delta_tick", "hl_pos_frac"]:
        if c in d.columns:
            out[c] = pd.to_numeric(d[c], errors="coerce").astype(float)

    out = (
        out.dropna(subset=["timestamp", "close_ts", "open", "high", "low", "close"])
        .sort_values("close_ts")
        .reset_index(drop=True)
    )
    if out.empty:
        return out

    pip = float(_pip_size(symbol))
    close = out["close"].astype(float)
    open_ = out["open"].astype(float)
    high = out["high"].astype(float)
    low = out["low"].astype(float)

    out["year"] = out["close_ts"].dt.year.astype(int)
    out["hour_utc"] = out["close_ts"].dt.hour.astype(int)
    out["hour_utc_sin"] = np.sin(2.0 * np.pi * out["hour_utc"] / 24.0)
    out["hour_utc_cos"] = np.cos(2.0 * np.pi * out["hour_utc"] / 24.0)

    out["duration_sec"] = (out["close_ts"] - out["timestamp"]).dt.total_seconds().clip(lower=1e-6)
    out["tick_rate_hz"] = out["tick_volume"] / out["duration_sec"]

    tr_mu = (
        out["tick_rate_hz"]
        .rolling(int(vol_window), min_periods=max(8, int(vol_window) // 3))
        .mean()
        .shift(1)
    )
    tr_sd = (
        out["tick_rate_hz"]
        .rolling(int(vol_window), min_periods=max(8, int(vol_window) // 3))
        .std(ddof=0)
        .shift(1)
    )
    out["tick_rate_z"] = (out["tick_rate_hz"] - tr_mu) / tr_sd.replace(0.0, np.nan)

    out["spread_pips"] = out["spread"] / pip
    out["range_pips"] = (high - low) / pip
    out["bar_move_pips"] = (close - open_) / pip

    if "hl_first" in out.columns:
        out["high_first_flag"] = (out["hl_first"] > 0).astype(float)
        out["low_first_flag"] = (out["hl_first"] < 0).astype(float)
        out["hl_first_mean_24"] = out["hl_first"].rolling(24, min_periods=8).mean().shift(1)
        out["hl_first_mean_96"] = out["hl_first"].rolling(96, min_periods=24).mean().shift(1)

    if "hl_pos_frac" in out.columns:
        out["hl_pos_frac_mean_24"] = out["hl_pos_frac"].rolling(24, min_periods=8).mean().shift(1)
        out["hl_pos_frac_mean_96"] = out["hl_pos_frac"].rolling(96, min_periods=24).mean().shift(1)

    sp_mu = (
        out["spread_pips"]
        .rolling(int(vol_window), min_periods=max(8, int(vol_window) // 3))
        .mean()
        .shift(1)
    )
    sp_sd = (
        out["spread_pips"]
        .rolling(int(vol_window), min_periods=max(8, int(vol_window) // 3))
        .std(ddof=0)
        .shift(1)
    )
    out["spread_z"] = (out["spread_pips"] - sp_mu) / sp_sd.replace(0.0, np.nan)

    out["vel_pips_h1"] = (close - close.shift(1)) / pip
    out[f"vel_{int(bar_ticks)}_pips"] = out["vel_pips_h1"]
    out["accel_pips"] = out["vel_pips_h1"] - out["vel_pips_h1"].shift(1)

    spread_recent = (
        out["spread_pips"]
        .rolling(int(cost_window), min_periods=max(8, int(cost_window) // 4))
        .median()
        .shift(1)
    )
    gap_abs_pips = (open_ - close.shift(1)).abs() / pip
    slip_proxy = (
        gap_abs_pips.rolling(int(cost_window), min_periods=max(8, int(cost_window) // 6))
        .quantile(0.75)
        .shift(1)
    )
    slip_fallback = (
        out["range_pips"]
        .rolling(int(cost_window), min_periods=max(8, int(cost_window) // 6))
        .quantile(0.75)
        .shift(1)
        * 0.2
    )

    out["slip_proxy_pips"] = slip_proxy.fillna(slip_fallback).fillna(0.1).clip(lower=0.01)
    out["cost_est_pips"] = (
        spread_recent.fillna(out["spread_pips"].shift(1)).fillna(out["spread_pips"].median())
        + out["slip_proxy_pips"]
    )

    vol_ref = (
        out["vel_pips_h1"]
        .rolling(int(vol_window), min_periods=max(8, int(vol_window) // 3))
        .std(ddof=0)
        .shift(1)
    )

    for h in sorted(set(int(x) for x in vel_horizons if int(x) > 0)):
        vel = (close - close.shift(h)) / pip
        vel_bps = (1.0 - close / close.shift(h)) * 10000.0
        dt_h = (out["close_ts"] - out["close_ts"].shift(h)).dt.total_seconds().clip(lower=1e-6)
        out[f"vel_pips_h{h}"] = vel
        out[f"vel_bps_h{h}"] = vel_bps
        out[f"vel_pips_per_sec_h{h}"] = vel / dt_h
        out[f"vel_z_h{h}"] = vel / (vol_ref * np.sqrt(float(h)))
        out[f"vel_cost_units_h{h}"] = vel / out["cost_est_pips"].replace(0.0, np.nan)

    for h in sorted(set(int(x) for x in target_horizons if int(x) > 0)):
        out[f"y_fwd_pips_h{h}"] = (close.shift(-h) - open_.shift(-1)) / pip

    out = out.replace([np.inf, -np.inf], np.nan)
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="Build causal velocity datasets from tick bars")
    p.add_argument(
        "--tick-root",
        default=str(DEFAULT_TICK_ROOT),
        help="Raw tick root (used with --auto-build-bars)",
    )
    p.add_argument(
        "--tickbar-dir",
        default=str(DEFAULT_TICKBAR_DIR),
        help="Input directory for *_Ntick parquet files",
    )
    p.add_argument(
        "--out-dir",
        default=str(DEFAULT_OUT_DIR),
        help="Output directory for per-symbol velocity datasets",
    )
    p.add_argument(
        "--symbols",
        default="",
        help="Comma-separated symbols; default=infer from tickbar dir (or tick root)",
    )
    p.add_argument("--bar-ticks", type=int, default=100, help="Tick bars per row")
    p.add_argument(
        "--bar-ticks-grid",
        default="",
        help="Optional comma-separated bar sizes (overrides --bar-ticks)",
    )
    p.add_argument(
        "--vel-horizons",
        default="1,2,5,10",
        help="Velocity horizons in bars (h=1 means 1x bar-ticks)",
    )
    p.add_argument("--target-horizons", default="1,2,3", help="Forward targets in bars")
    p.add_argument(
        "--vol-window", type=int, default=96, help="Rolling window for velocity std normalizer"
    )
    p.add_argument(
        "--cost-window", type=int, default=288, help="Rolling window for spread/slippage context"
    )
    p.add_argument(
        "--price-source", choices=["bid", "mid"], default="bid", help="Used when auto-building bars"
    )
    p.add_argument(
        "--timestamp-mode",
        choices=["as_utc", "utc_naive", "ny_local_tagged_utc"],
        default="as_utc",
        help="How to interpret raw tick timestamps when building bars",
    )
    p.add_argument(
        "--auto-build-bars", action="store_true", help="Build missing *_Ntick bars from raw ticks"
    )
    p.add_argument(
        "--rebuild-bars", action="store_true", help="Force rebuild *_Ntick bars when auto-building"
    )
    p.add_argument("--overwrite", action="store_true", help="Overwrite existing output files")
    p.add_argument("--combined-out", default="", help="Optional combined parquet path")
    args = p.parse_args()

    tick_root = Path(str(args.tick_root))
    tickbar_dir = Path(str(args.tickbar_dir))
    out_dir = Path(str(args.out_dir))
    out_dir.mkdir(parents=True, exist_ok=True)

    bar_ticks_list = _parse_bar_ticks_grid(str(args.bar_ticks_grid), fallback=int(args.bar_ticks))
    vel_horizons = _parse_int_list(str(args.vel_horizons))
    target_horizons = _parse_int_list(str(args.target_horizons))
    if not vel_horizons:
        raise ValueError("--vel-horizons must not be empty")

    symbols = _parse_symbols(str(args.symbols))
    if not symbols:
        inferred: set[str] = set()
        for bt in bar_ticks_list:
            inferred.update(_infer_symbols_from_tickbars(tickbar_dir, bar_ticks=bt))
        symbols = sorted(inferred)
    if not symbols:
        symbols = _infer_symbols_from_tick_root(tick_root)
    if not symbols:
        raise ValueError("No symbols found. Pass --symbols or ensure tick data exists.")

    print(
        f"building velocity datasets: symbols={len(symbols)}, bar_ticks={bar_ticks_list}, "
        f"vel_horizons={vel_horizons}, target_horizons={target_horizons}, timestamp_mode={args.timestamp_mode}"
    )

    built: list[pd.DataFrame] = []
    for bar_ticks in bar_ticks_list:
        for symbol in symbols:
            out_path = out_dir / f"{symbol}_{bar_ticks}tick_velocity.parquet"
            if out_path.exists() and not bool(args.overwrite):
                print(f"skip {symbol} {bar_ticks}tick: exists -> {out_path}")
                continue

            bar_path = tickbar_dir / f"{symbol}_{bar_ticks}tick.parquet"
            need_build = bool(args.rebuild_bars) or (not bar_path.exists())
            if need_build:
                if not bool(args.auto_build_bars):
                    print(
                        f"skip {symbol} {bar_ticks}tick: missing/rebuild required for {bar_path} "
                        f"(pass --auto-build-bars)"
                    )
                    continue
                bar_path = _ensure_tickbar(
                    symbol=str(symbol),
                    tickbar_dir=tickbar_dir,
                    tick_root=tick_root,
                    bar_ticks=bar_ticks,
                    price_source=str(args.price_source),
                    timestamp_mode=str(args.timestamp_mode),
                    overwrite=bool(args.rebuild_bars),
                )

            try:
                ds = _build_symbol_dataset(
                    symbol=str(symbol),
                    bar_path=bar_path,
                    bar_ticks=bar_ticks,
                    vel_horizons=vel_horizons,
                    target_horizons=target_horizons,
                    vol_window=int(args.vol_window),
                    cost_window=int(args.cost_window),
                )
                if ds.empty:
                    print(f"skip {symbol} {bar_ticks}tick: empty dataset after processing")
                    continue

                ds["timestamp_mode"] = str(args.timestamp_mode)
                ds.to_parquet(out_path, index=False)
                print(f"ok {symbol} {bar_ticks}tick: rows={len(ds)} -> {out_path}")
                built.append(
                    ds.assign(_source_symbol=str(symbol), _source_bar_ticks=int(bar_ticks))
                )
            except Exception as e:
                print(f"fail {symbol} {bar_ticks}tick: {e}")

    combined_out = str(args.combined_out).strip()
    if combined_out and built:
        cp = Path(combined_out)
        cp.parent.mkdir(parents=True, exist_ok=True)
        pd.concat(built, axis=0, ignore_index=True).to_parquet(cp, index=False)
        print(f"ok combined: rows={sum(len(x) for x in built)} -> {cp}")

    print("done")


if __name__ == "__main__":
    main()
