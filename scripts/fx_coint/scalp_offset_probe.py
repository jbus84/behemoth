"""Momentum at 20m across BAR-GRID OFFSETS (wall-clock phase) — does a 'weird offset' work?

FX has wall-clock structure (session opens, 16:00 London fix, top-of-hour releases), so the
PHASE of the bar grid may matter. Build 20m bars at offsets 0/5/10/15 min and test the signed
momentum IC + with-momentum tail net at H1 (20-min hold), pooled tight majors, all-hours and
liquid (07-16). Signed IC: +ve = momentum, -ve = reversion.

EXPLORATION on one year — any offset that looks alive MUST then pass the causal multi-year gate
(scalp_causal_validation pattern); single-year + offset-sweep is a mirage factory.

Usage:
    uv run python scripts/fx_coint/scalp_offset_probe.py --year 2024
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_ROOT = _Path(__file__).resolve().parents[2]
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))

import argparse  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import polars as pl  # noqa: E402
from scipy.stats import spearmanr  # noqa: E402

from scripts.fx_coint.phase0_scalp_common import DEFAULT_COST_BPS, load_raw_ticks  # noqa: E402

TIGHT = ["EURUSD", "GBPUSD", "USDJPY"]


def mid_bars(ticks: pl.DataFrame, every_min: int, offset_min: int) -> pd.DataFrame:
    """Lightweight phased time bars: bucket = truncate(ts - offset) + offset."""
    off = pl.duration(minutes=offset_min)
    t = ticks.sort("timestamp").with_columns(
        ((pl.col("timestamp") - off).dt.truncate(f"{every_min}m") + off).alias("bucket")
    )
    bars = t.group_by("bucket").agg(pl.col("mid").last()).sort("bucket").to_pandas()
    bars["bucket"] = pd.to_datetime(bars["bucket"])
    return bars


def eval_offset(year: int, every_min: int, offset_min: int, mom_k: int):
    """Pooled signed momentum IC + with-momentum extreme-tail net (taker), all + liquid."""
    out = {}
    for tag, liq in (("all", False), ("liq", True)):
        ic_s, ic_y, nets = [], [], []
        for sym in TIGHT:
            cf = DEFAULT_COST_BPS[sym] / 10_000
            b = mid_bars(load_raw_ticks(sym, year), every_min, offset_min)
            mid = b["mid"].astype(float)
            r = np.log(mid / mid.shift(1)) * 1e4
            rv = r.rolling(48, min_periods=20).std().shift(1)
            mom = (r.rolling(mom_k, min_periods=1).sum() / (rv * np.sqrt(mom_k))).shift(1)
            fwd = np.log(mid.shift(-1) / mid) * 1e4
            hr = b["bucket"].dt.hour
            keep = np.isfinite(mom) & np.isfinite(fwd)
            if liq:
                keep &= (hr >= 7) & (hr < 16)
            m, fv = mom[keep].to_numpy(), fwd[keep].to_numpy()
            if len(m) < 200:
                continue
            ic_s.append(m)
            ic_y.append(fv)
            # with-momentum extreme tail (top-decile |mom|): trade sign(mom)
            sel = np.abs(m) >= np.quantile(np.abs(m), 0.90)
            nets.append(np.sign(m[sel]) * fv[sel] - cf * 1e4)
        if not ic_s:
            continue
        xs, ys = np.concatenate(ic_s), np.concatenate(ic_y)
        ic = spearmanr(xs, ys).statistic
        net = np.concatenate(nets)
        out[tag] = (ic, float(net.mean()), float((net > 0).mean()), len(net))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2024)
    ap.add_argument("--every", type=int, default=20)
    ap.add_argument("--offsets", nargs="+", type=int, default=[0, 5, 10, 15])
    ap.add_argument("--mom", nargs="+", type=int, default=[1, 2, 3])
    args = ap.parse_args()

    print(f"MOMENTUM @ {args.every}m across bar-grid offsets — pooled tight majors, {args.year}")
    print("  signedIC: +momentum / -reversion; tailNet = with-momentum top-decile net@taker (bps)\n")
    print(f"  {'offset':>7} {'momK':>5} {'sess':>4} {'signedIC':>9} {'tailNet':>8} {'hit':>5} {'n':>6}")
    for off in args.offsets:
        for k in args.mom:
            res = eval_offset(args.year, args.every, off, k)
            for tag in ("all", "liq"):
                if tag not in res:
                    continue
                ic, net, hit, n = res[tag]
                flag = "  <<<" if net > 0 else ""
                print(f"  {f'+{off}m':>7} {k:>5} {tag:>4} {ic:>+9.4f} {net:>8.3f} {hit*100:>4.0f}% {n:>6}{flag}")
        print()


if __name__ == "__main__":
    main()
