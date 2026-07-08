"""Second attempt at a session-aware jump detector, after the mean-floor approach
(jumpfade_session_aware_detector.py) failed -- it thinned CHFJPY's population 61%
but barely moved rollover concentration (96.0%->93.8%) and made real-tick net worse.

Root cause of that failure: a mean-based floor targets AVERAGE session magnitude,
but the rollover problem is specifically FAT TAILS (rare, extreme illiquidity gaps),
not elevated average noise. A z-score threshold against any mean-based sigma
implicitly assumes similar kurtosis across sessions -- false here.

This version replaces the Gaussian z-score entirely with an EMPIRICAL, per-half-hour-
bucket, causal (expanding) quantile threshold: flag a jump only if |ret| exceeds the
QUANTILE-th percentile of THAT bucket's own historical |ret| distribution so far.
This directly targets each session's actual tail shape instead of assuming Gaussian
behavior scaled by a mean estimate.
"""

from __future__ import annotations

import glob
import datetime

import numpy as np
import polars as pl

from scripts.fx_coint.eurusd_cusum_probe import load_5m

H = 24
QUANTILE = 0.995  # flag if |ret| exceeds this bucket's own historical percentile
MIN_BUCKET_HISTORY = 200  # min observations in a bucket before trusting its quantile
COMMISSION = 0.60
CROSS_LEGS = {"CHFJPY": [("USDCHF", -1), ("USDJPY", +1)]}


def leg_proxy_for(legs: list[tuple[str, int]]) -> pl.DataFrame:
    frames = []
    for sym, sign in legs:
        d5 = load_5m(sym).with_columns((pl.col("mid").log().diff() * sign).alias(f"l_{sym}"))
        frames.append(d5.select("bucket", f"l_{sym}"))
    out = frames[0].join(frames[1], on="bucket", how="inner")
    return out.with_columns(pl.sum_horizontal([f"l_{s}" for s, _ in legs]).alias("common_proxy"))


def causal_expanding_quantile_flag(abs_ret: np.ndarray, hh: np.ndarray, quantile: float,
                                    min_hist: int, recompute_every: int = 250) -> np.ndarray:
    """For each bar, flag if abs_ret exceeds the `quantile`-th percentile of all
    PRIOR abs_ret values in the same half-hour bucket (causal, no look-ahead).
    Threshold is recomputed only every `recompute_every` new observations per
    bucket (still causal -- only ever uses past data -- just not re-percentiled
    every single bar, which would be prohibitively slow at full scale)."""
    n = len(abs_ret)
    flags = np.zeros(n, dtype=bool)
    bucket_history: dict[int, list[float]] = {h: [] for h in range(48)}
    bucket_thresh: dict[int, float] = dict.fromkeys(range(48), np.inf)
    bucket_since_recompute: dict[int, int] = dict.fromkeys(range(48), 0)
    for i in range(n):
        b = int(hh[i])
        hist = bucket_history[b]
        if len(hist) >= min_hist:
            flags[i] = abs_ret[i] > bucket_thresh[b]
        hist.append(abs_ret[i])
        bucket_since_recompute[b] += 1
        if len(hist) >= min_hist and bucket_since_recompute[b] >= recompute_every:
            bucket_thresh[b] = float(np.percentile(hist, quantile * 100))
            bucket_since_recompute[b] = 0
    return flags


def build(sym: str) -> pl.DataFrame:
    df = load_5m(sym)
    df = df.with_columns(
        pl.col("mid").log().diff().alias("ret"),
        (pl.col("bucket").dt.hour() * 2 + (pl.col("bucket").dt.minute() >= 30).cast(pl.Int32)).alias("hh"),
    )
    df = df.with_columns(pl.col("ret").abs().alias("abs_ret")).drop_nulls("ret")
    abs_ret_np = df["abs_ret"].to_numpy()
    hh_np = df["hh"].to_numpy()
    flags = causal_expanding_quantile_flag(abs_ret_np, hh_np, QUANTILE, MIN_BUCKET_HISTORY)
    df = df.with_columns(pl.Series("is_jump_quantile", flags))
    df = df.with_columns((pl.col("mid").log().shift(-H) - pl.col("mid").log()).alias(f"fwd_{H}"))
    return df


def real_tick_check(sym: str, idio: pl.DataFrame, label: str) -> None:
    rows = idio.select("bucket", "ret").to_dicts()
    n_total = len(rows)
    if n_total < 10:
        print(f"  {label}: n={n_total} too small to test")
        return
    months = sorted({(r["bucket"].year, r["bucket"].month) for r in rows})
    frames = [
        pl.scan_parquet(f).select("timestamp", "spread", "mid")
        for y, m in months
        for f in glob.glob(f"/Users/danielfisher/Desktop/tick/{sym}/{sym}_{y}{m:02d}_ticks.parquet")
    ]
    ticks = pl.concat(frames).sort("timestamp").collect()
    ts = ticks["timestamp"].to_numpy()
    spreads = ticks["spread"].to_numpy()
    mids = ticks["mid"].to_numpy()

    net = []
    for r in rows:
        t0 = r["bucket"]
        if t0.tzinfo is None:
            t0 = t0.replace(tzinfo=datetime.timezone.utc)
        sgn = np.sign(r["ret"])
        if sgn == 0:
            continue
        entry_t = np.datetime64(t0) + np.timedelta64(5, "m")
        exit_t = entry_t + np.timedelta64(120, "m")
        idx_e = np.searchsorted(ts, entry_t, side="left")
        idx_x = np.searchsorted(ts, exit_t, side="left")
        if idx_e >= len(ts) or idx_x >= len(ts):
            continue
        if abs((ts[idx_e] - entry_t) / np.timedelta64(1, "s")) > 90:
            continue
        if abs((ts[idx_x] - exit_t) / np.timedelta64(1, "s")) > 90:
            continue
        gross = -sgn * np.log(mids[idx_x] / mids[idx_e]) * 1e4
        cost = (spreads[idx_e] / mids[idx_e] * 1e4 + spreads[idx_x] / mids[idx_x] * 1e4) / 2 + COMMISSION
        net.append(gross - cost)
    net = np.array(net)
    m = net.mean()
    t = m / (net.std() / np.sqrt(len(net))) if len(net) > 5 else float("nan")
    rollover_n = idio.filter(pl.col("bucket").dt.hour().is_in([20, 21, 22])).height
    print(f"  {label}: n_flagged={n_total}  n_matched={len(net)}  rollover%={100*rollover_n/n_total:.1f}%  "
          f"REAL-TICK net={m:+.3f}bps  t={t:+.2f}")


def main() -> None:
    sym = "CHFJPY"
    df = build(sym)
    proxy = leg_proxy_for(CROSS_LEGS[sym])
    v = df.join(proxy.select("bucket", "common_proxy"), on="bucket", how="inner")
    v = v.with_columns((pl.col("ret") - pl.col("common_proxy")).alias("idio"))
    v = v.filter(pl.col("idio").abs() > pl.col("common_proxy").abs())
    v = v.filter(pl.col(f"fwd_{H}").is_not_null())

    quantile_idio = v.filter(pl.col("is_jump_quantile"))
    print(f"{sym}: quantile detector n={quantile_idio.height}")
    real_tick_check(sym, quantile_idio, "QUANTILE detector (per-bucket empirical tail)")


if __name__ == "__main__":
    main()
