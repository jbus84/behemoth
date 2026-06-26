"""Anatomy of a whale event: when does it land, is it one bar, how big?

Event study on hourly bars, pooled 6 majors, USD-oriented. Align on the event bar t and
trace the average cumulative log-price path (bps) from t-5..t+10, anchored so price at
t-1 = 0. Two event definitions:
  FLOW events   : top-1% |flow_tick| bars (a whale is executing)
  RETURN events : top-1% |return| bars (the move itself)

Reports the average path, the size of the move IN the event bar vs the surrounding bars,
the concentration ratio (event-bar move / total move), and the post-event drift vs
reversion. Also a 1000-tick pass for finer (sub-hourly) timing.

Usage: uv run python scripts/fx_coint/whale_anatomy.py
"""
# ruff: noqa: E402
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.fx_coint.feature_ic_definitive import DATA

PAIRS = {"EURUSD": +1, "GBPUSD": +1, "AUDUSD": +1, "USDCAD": -1, "USDCHF": -1, "USDJPY": -1}
PRE, POST = 5, 10


def load_hourly(sym):
    import polars as pl
    d = pl.read_parquet(f"{DATA}/{sym}_1h_flow.parquet").sort("bucket").to_pandas()
    return np.log(d["mid"].to_numpy()), d["flow_tick"].to_numpy()


def _load_tick(sym, suffix):
    import polars as pl
    d = pl.read_parquet(f"{DATA}/{sym}_{suffix}.parquet")
    t = d["timestamp"].to_numpy()
    o = np.argsort(t.astype("datetime64[ns]").astype("int64"))
    mid = ((d["close_bid"].to_numpy() + d["close_ask"].to_numpy()) / 2)[o]
    return np.log(mid), None


def load_tick(sym):
    return _load_tick(sym, "1000tick")


def load_tick100(sym):
    return _load_tick(sym, "100tick")


def event_study(loader, has_flow, by):
    """Average oriented cumulative path (bps) around top-1% events, anchored t-1=0."""
    paths = []
    sizes_event, sizes_total = [], []
    for sym, _sgn in PAIRS.items():
        logp, flow = loader(sym)
        n = len(logp)
        r = np.append(np.nan, np.diff(logp)) * 1e4             # RAW bar return (bps)
        score = np.abs(flow) if (by == "flow" and has_flow) else np.abs(r)
        thr = np.nanquantile(score[np.isfinite(score)], 0.99)
        idx = np.where(score >= thr)[0]
        idx = idx[(idx >= PRE + 1) & (idx < n - POST)]
        for i in idx:
            seg = r[i - PRE: i + POST + 1].copy()              # returns t-PRE..t+POST
            if not np.isfinite(seg).all():
                continue
            cum = np.cumsum(seg)
            cum = cum - cum[PRE - 1]                            # anchor t-1 = 0
            if r[i] < 0:                                        # flip so event-bar move is +
                cum = -cum
            paths.append(cum)
            sizes_event.append(abs(r[i]))
            sizes_total.append(abs(cum[PRE + POST]))
    P = np.array(paths)
    avg = P.mean(axis=0)
    return avg, np.mean(sizes_event), np.median(sizes_event), len(P)


def report(label, loader, has_flow, by):
    avg, ev_mean, ev_med, npaths = event_study(loader, has_flow, by)
    rel = np.arange(-PRE, POST + 1)
    print(f"\n[{label}: top-1% {by} events, n={npaths}]  cumulative bps (t-1=0), event bar = t0")
    print("   t:  " + " ".join(f"{x:>+4d}" for x in rel))
    print("  cum: " + " ".join(f"{v:>+5.1f}" for v in avg))
    event_move = avg[PRE] - avg[PRE - 1]          # the move in the event bar itself
    pre_move = avg[PRE - 1] - avg[0]               # accumulation before
    post_move = avg[PRE + POST] - avg[PRE]         # after the event bar
    peak = np.max(np.abs(avg))
    print(f"  -> event-bar move = {event_move:+.1f} bps | pre(t-5..t-1) = {pre_move:+.1f} | "
          f"post(t..t+10) = {post_move:+.1f}")
    print(f"  -> |event move| mean={ev_mean:.1f} bps median={ev_med:.1f} bps | "
          f"concentration (event-bar / peak) = {abs(event_move) / (peak + 1e-9):.0%}")


def main():
    print("WHALE ANATOMY — when the move lands, one-bar concentration, size")
    report("HOURLY", load_hourly, True, "flow")
    report("HOURLY", load_hourly, True, "return")
    report("1000-TICK", load_tick, False, "return")
    report("100-TICK", load_tick100, False, "return")


if __name__ == "__main__":
    main()
