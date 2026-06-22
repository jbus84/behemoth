"""Assess bar types (De Prado AFML ch.2) on FX quote ticks.

No volume in the data => only TICK-based bars are possible:
  TIME   bars (baseline)        : fixed wall-clock interval
  TICK   bars                   : every N quote-ticks
  TIB    tick-imbalance bars    : close when |cum signed-tick| exceeds EWMA expectation
  TRB    tick-runs bars         : close when one-side run-count exceeds EWMA expectation
(Tick rule: b_t = sign(Δmid), zeros carried forward.)

Calibrated so AVERAGE bar duration ~ a target (15/30/60 min). Compares the core
AFML ch.2 claim — info-driven bars give returns closer to IID Normal — via:
  excess kurtosis, |skew|, Jarque-Bera, first-order return autocorrelation,
  and a heteroscedasticity proxy (autocorr of |returns|).

Usage: uv run python scripts/fx_coint/bar_type_assessment.py [SYMBOL] [START_YYYYMM] [END_YYYYMM] [TARGET_MIN]
"""
from __future__ import annotations

import glob
import os
import sys

import numpy as np
import pandas as pd
from scipy import stats

TICK_DIR = os.path.expanduser("~/Desktop/dukascopy_ticks")


def load_ticks(sym: str, start: str, end: str) -> pd.DataFrame:
    files = sorted(glob.glob(f"{TICK_DIR}/{sym}/{sym}_*_ticks.parquet"))
    keep = [f for f in files if start <= os.path.basename(f).split("_")[1] <= end]
    df = pd.concat([pd.read_parquet(f, columns=["timestamp", "mid"]) for f in keep], ignore_index=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def tick_signs(mid: np.ndarray) -> np.ndarray:
    d = np.sign(np.diff(mid, prepend=mid[0]))
    # carry forward zeros (tick rule), vectorized via forward-fill of last nonzero
    idx = np.where(d != 0, np.arange(len(d)), 0)
    np.maximum.accumulate(idx, out=idx)
    out = d[idx]
    out[out == 0] = 1.0  # leading zeros before first move
    return out


def bars_from_endpoints(ts, mid, ends) -> pd.DataFrame:
    """Given sorted tick arrays and bar-end tick indices, build OHLC + duration."""
    rows = []
    start = 0
    for e in ends:
        if e <= start:
            continue
        seg_mid = mid[start:e + 1]
        rows.append((ts[e], seg_mid[0], seg_mid[-1], seg_mid.max(), seg_mid.min(),
                     e - start + 1, (ts[e] - ts[start]) / np.timedelta64(1, "s")))
        start = e + 1
    b = pd.DataFrame(rows, columns=["t", "open", "close", "high", "low", "n_ticks", "dur_s"])
    return b


def tick_bars(ts, mid, N) -> pd.DataFrame:
    ends = np.arange(N - 1, len(mid), N)
    return bars_from_endpoints(ts, mid, ends)


def imbalance_bars(ts, mid, signs, expected_T) -> pd.DataFrame:
    """TIB (fixed-threshold): close when |cumulative signed-tick imbalance| >= H.
    For a +/-1 walk, mean first-passage to |S|=H is H^2, so H=sqrt(N) targets
    an average of ~N ticks/bar (matches the tick/time bars)."""
    H = np.sqrt(expected_T)
    ends = []
    theta = 0.0
    n = len(signs)
    for i in range(n):
        theta += signs[i]
        if abs(theta) >= H:
            ends.append(i)
            theta = 0.0
    return bars_from_endpoints(ts, mid, np.array(ends))


def runs_bars(ts, mid, signs, expected_T) -> pd.DataFrame:
    """TRB (fixed-threshold): close when one-side run-count reaches R=N/2, so a
    balanced bar closes after ~N ticks but a one-sided (informed) burst closes
    sooner."""
    R = max(int(expected_T // 2), 1)
    ends = []
    buys = sells = 0
    n = len(signs)
    for i in range(n):
        if signs[i] > 0:
            buys += 1
        else:
            sells += 1
        if buys >= R or sells >= R:
            ends.append(i)
            buys = sells = 0
    return bars_from_endpoints(ts, mid, np.array(ends))


def time_bars(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    g = df.set_index("timestamp")["mid"].resample(rule, label="right", closed="right")
    b = pd.DataFrame({"close": g.last(), "high": g.max(), "low": g.min(), "n_ticks": g.count()}).dropna()
    b = b[b["n_ticks"] > 0].reset_index().rename(columns={"timestamp": "t"})
    b["dur_s"] = pd.to_timedelta(rule).total_seconds()
    return b


def stats_row(name: str, b: pd.DataFrame, total_days: float) -> dict:
    r = (np.log(b["close"]).diff() * 1e4).dropna().to_numpy()
    r = r[np.abs(r) < 500]
    absr = np.abs(r)
    return dict(
        bar_type=name,
        n_bars=len(b),
        bars_per_day=len(b) / total_days,
        mean_dur_min=b["dur_s"].mean() / 60,
        ret_std=r.std(),
        abs_skew=abs(stats.skew(r)),
        excess_kurt=stats.kurtosis(r),
        jb_stat=stats.jarque_bera(r)[0],
        acf1=pd.Series(r).autocorr(1),          # serial corr of returns (lower=better)
        acf1_absr=pd.Series(absr).autocorr(1),  # vol clustering / heteroscedasticity
    )


def main() -> None:
    sym = sys.argv[1] if len(sys.argv) > 1 else "EURUSD"
    start = sys.argv[2] if len(sys.argv) > 2 else "202301"
    end = sys.argv[3] if len(sys.argv) > 3 else "202412"
    target_min = float(sys.argv[4]) if len(sys.argv) > 4 else 30.0
    pd.set_option("display.width", 220, "display.float_format", lambda x: f"{x:10.4f}")

    print(f"Loading {sym} ticks {start}..{end} ...")
    df = load_ticks(sym, start, end)
    ts = df["timestamp"].to_numpy()
    mid = df["mid"].to_numpy()
    total_days = (ts[-1] - ts[0]) / np.timedelta64(1, "D")
    total_min = total_days * 24 * 60
    N = max(int(round(len(mid) / (total_min / target_min))), 10)  # ticks per target-min bar
    print(f"  {len(mid):,} ticks, {total_days:.0f} days; calibrated N={N} ticks/~{target_min:.0f}min bar")

    print("  computing tick signs ...")
    signs = tick_signs(mid)

    rule = f"{int(target_min)}min"
    builders = {
        f"TIME_{int(target_min)}m": time_bars(df, rule),
        f"TICK_{N}": tick_bars(ts, mid, N),
        "TIB": imbalance_bars(ts, mid, signs, expected_T=N),
        "TRB": runs_bars(ts, mid, signs, expected_T=N),
    }
    rows = [stats_row(name, b, total_days) for name, b in builders.items()]
    res = pd.DataFrame(rows)
    print("\n" + "=" * 120)
    print(f"BAR-TYPE ASSESSMENT — {sym} {start}..{end}, target ~{target_min:.0f}min")
    print("  De Prado ch.2 claim: info-driven bars => returns closer to IID Normal")
    print("  (lower excess_kurt, |skew|, jb_stat, |acf1|; acf1_absr = vol clustering)")
    print("=" * 120)
    print(res.to_string(index=False))


if __name__ == "__main__":
    main()
