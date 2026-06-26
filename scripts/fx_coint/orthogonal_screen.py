"""Sniff for a HIDDEN ORTHOGONAL edge — drivers not in the price-reversion family.

Screens several genuinely different hypotheses on 1000-tick bars, pooled over all 6
majors (incl USDJPY for breadth), USD-oriented, with a causal first-half/second-half
split so only OOS-stable signals survive:

  H1 DAY-OF-WEEK drift   : mean forward N-bar return by weekday (calendar driver)
  H2 HOUR-OF-DAY drift   : mean forward N-bar return by UTC hour bucket (session driver)
  H3 RANGE BREAKOUT      : sign(close vs rolling-W high/low) -> forward N-bar return
                           (momentum in price LEVELS — opposite mechanism to FFD reversion)
  H4 GAP REVERSION       : after a large inter-bar time gap (session break), does the
                           next move revert the gap? (microstructure/liquidity driver)

For each we report the IS vs OOS effect and flag only those that hold OOS with the same
sign and a magnitude that could clear ~1bp cost. This is a SCREEN (find the needle),
not a backtest — survivors get a full causal gauntlet next.

Usage: uv run python scripts/fx_coint/orthogonal_screen.py
"""
# ruff: noqa: E402
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.fx_coint.feature_ic_definitive import DATA, SUFFIX

PAIRS = {"EURUSD": +1, "GBPUSD": +1, "AUDUSD": +1, "USDCAD": -1, "USDCHF": -1, "USDJPY": -1}
N_FWD = 10            # forward horizon in bars
BREAKOUT_W = 50       # rolling window for range breakout


def load(sym):
    import polars as pl
    df = pl.read_parquet(f"{DATA}/{sym}_{SUFFIX}.parquet")
    t = pd.to_datetime(df["timestamp"].to_numpy()).tz_localize(None)
    o = np.argsort(t.to_numpy().astype("datetime64[ns]").astype("int64"))
    mid = ((df["close_bid"].to_numpy() + df["close_ask"].to_numpy()) / 2)[o]
    hi = df["high_bid"].to_numpy()[o]
    lo = df["low_bid"].to_numpy()[o]
    t = t.to_numpy()[o]
    return mid, hi, lo, pd.DatetimeIndex(t)


def build_pooled():
    rows = []
    for sym, sgn in PAIRS.items():
        mid, hi, lo, t = load(sym)
        n = len(mid)
        logp = np.log(mid)
        fwd = np.full(n, np.nan)
        fwd[:n - N_FWD] = (logp[N_FWD:] - logp[:n - N_FWD]) * 1e4 * sgn   # USD-oriented fwd ret
        # breakout state: +1 close above prior-W high, -1 below prior-W low, else 0
        s = pd.Series(mid)
        rmax = s.rolling(BREAKOUT_W).max().shift(1).to_numpy()
        rmin = s.rolling(BREAKOUT_W).min().shift(1).to_numpy()
        brk = np.where(mid > rmax, 1, np.where(mid < rmin, -1, 0)).astype(float)
        # gap: inter-bar minutes (proxy for session break)
        dt_min = np.empty(n)
        dt_min[0] = np.nan
        dt_min[1:] = (t[1:] - t[:-1]) / np.timedelta64(1, "m")
        # last-bar oriented return (for gap reversion)
        r1 = np.empty(n)
        r1[0] = np.nan
        r1[1:] = (logp[1:] - logp[:-1]) * 1e4 * sgn
        rows.append(pd.DataFrame({
            "sym": sym, "t": t, "dow": t.dayofweek, "hour": t.hour,
            "fwd": fwd, "brk": brk, "dt_min": dt_min, "r1": r1,
        }))
    return pd.concat(rows, ignore_index=True).dropna(subset=["fwd"])


def split(df):
    cut = df["t"].quantile(0.5)
    return df[df["t"] <= cut], df[df["t"] > cut]


def bucket_report(name, df_is, df_oos, key):
    print(f"\n[{name}]  mean USD-oriented fwd-{N_FWD}bar ret (bps): IS | OOS  (n_oos)")
    gi = df_is.groupby(key)["fwd"].mean()
    go = df_oos.groupby(key)["fwd"].agg(["mean", "count"])
    for k in sorted(set(gi.index) | set(go.index)):
        i = gi.get(k, np.nan)
        o = go["mean"].get(k, np.nan)
        nc = int(go["count"].get(k, 0))
        same = "OOS-stable" if np.isfinite(i) and np.isfinite(o) and np.sign(i) == np.sign(o) and abs(o) > 0.5 else ""
        print(f"   {key}={k!s:>3}  {i:>+7.2f} | {o:>+7.2f}  (n{nc:>6d}) {same}")


def main():
    df = build_pooled()
    df_is, df_oos = split(df)
    print(f"Pooled 6 majors, {len(df):,} bars, fwd={N_FWD} bars, breakout W={BREAKOUT_W}")

    bucket_report("H1 day-of-week", df_is, df_oos, "dow")
    bucket_report("H2 hour-of-day", df_is, df_oos, "hour")

    # H3 breakout: signed forward return = brk * fwd (continuation if positive)
    print("\n[H3 range breakout]  brk*fwd (continuation>0, reversion<0), oriented-agnostic")
    for label, d in (("IS", df_is), ("OOS", df_oos)):
        m = d[d["brk"] != 0]
        cont = (m["brk"] * (np.sign(m["fwd"]) * np.abs(m["fwd"]))).mean()
        # use raw per-pair fwd magnitude (not oriented) for breakout direction:
        print(f"   {label}: mean(brk*fwd_oriented)={ (m['brk']*m['fwd']).mean():+.3f} bps  n={len(m):,}")

    # H4 gap reversion: large dt_min bars, does -sign(r1) predict fwd? (fade the gap)
    print("\n[H4 gap reversion]  after big inter-bar gap, mean(-sign(r1)*fwd):")
    thr = df["dt_min"].quantile(0.99)
    for label, d in (("IS", df_is), ("OOS", df_oos)):
        g = d[d["dt_min"] >= thr]
        if len(g):
            print(f"   {label}: gap>={thr:.0f}min  mean(-sign(r1)*fwd)={(-np.sign(g['r1'])*g['fwd']).mean():+.3f}  n={len(g):,}")


if __name__ == "__main__":
    main()
