"""Session-aware jump detector: floor the trailing-bipower local-vol estimate with the
diurnal (time-of-day) scale, so the jump flag doesn't fire on ordinary rollover-hour
noise just because the trailing window hasn't caught up to the sudden liquidity drop.

Root cause found 2026-07-07: 82-96% of every tested cross's "idiosyncratic jump"
population fires in the 20-22 UTC NY-close/rollover window, and those flagged events
collapse completely under real tick execution (real spread there is 4-12x wider).
The naive fix (exclude the hours) leaves too few events to trade. This tests whether
raising the jump threshold's local-vol floor during known-thin sessions instead
recovers a real, smaller population rather than just deleting the hours outright.

bp_sigma (trailing 24-bar bipower) reacts only after a liquidity regime shift is
already underway. diurnal_scale (expanding per-half-hour-bucket average |return|,
already computed in eurusd_cusum_probe.py) encodes what THIS specific time-of-day
has historically looked like -- floor bp_sigma with diurnal_scale/0.7979 (same E|Z|
scaling used elsewhere) so the detector expects thinner activity going into a known
low-liquidity window, rather than being surprised by it bar-by-bar.
"""

from __future__ import annotations

import glob
import datetime

import numpy as np
import polars as pl

from scripts.fx_coint.eurusd_cusum_probe import load_5m

H = 24
JUMP_Z_THRESH = 4.0
BIPOWER_WINDOW = 24
COMMISSION = 0.60
CROSS_LEGS = {"CHFJPY": [("USDCHF", -1), ("USDJPY", +1)]}


def leg_proxy_for(legs: list[tuple[str, int]]) -> pl.DataFrame:
    frames = []
    for sym, sign in legs:
        d5 = load_5m(sym).with_columns((pl.col("mid").log().diff() * sign).alias(f"l_{sym}"))
        frames.append(d5.select("bucket", f"l_{sym}"))
    out = frames[0].join(frames[1], on="bucket", how="inner")
    return out.with_columns(pl.sum_horizontal([f"l_{s}" for s, _ in legs]).alias("common_proxy"))


def build_session_aware(sym: str) -> pl.DataFrame:
    df = load_5m(sym)
    df = df.with_columns(
        pl.col("mid").log().diff().alias("ret"),
        (pl.col("bucket").dt.hour() * 2 + (pl.col("bucket").dt.minute() >= 30).cast(pl.Int32)).alias("hh"),
    )
    df = df.with_columns(pl.col("ret").abs().alias("abs_ret"))
    df = df.with_columns(pl.col("abs_ret").shift(1).over("hh").alias("abs_ret_shifted"))
    df = df.with_columns(
        pl.col("abs_ret_shifted").cum_sum().over("hh").alias("_cumsum"),
        pl.col("abs_ret_shifted").is_not_null().cum_sum().over("hh").alias("hh_n_seen"),
    )
    df = df.with_columns((pl.col("_cumsum") / pl.col("hh_n_seen")).alias("diurnal_scale"))
    df = df.filter(pl.col("hh_n_seen") >= 30).filter(pl.col("diurnal_scale") > 0)

    abs_ret_np = df["abs_ret"].to_numpy()
    n = len(abs_ret_np)
    bp_sigma = np.full(n, np.nan)
    w = BIPOWER_WINDOW
    for i in range(w + 1, n):
        window = abs_ret_np[i - w:i]
        bp = np.mean(window[1:] * window[:-1]) * (np.pi / 2)
        bp_sigma[i] = np.sqrt(bp) if bp > 0 else np.nan
    df = df.with_columns(pl.Series("bp_sigma", bp_sigma))

    # session-aware floor: local vol can't be smaller than the diurnal expectation for this time-of-day
    df = df.with_columns((pl.col("diurnal_scale") / 0.7979).alias("diurnal_sigma_est"))
    df = df.with_columns(
        pl.max_horizontal("bp_sigma", "diurnal_sigma_est").alias("bp_sigma_session_aware")
    )

    df = df.with_columns((pl.col("ret") / pl.col("bp_sigma")).alias("lm_z_naive"))
    df = df.with_columns((pl.col("ret") / pl.col("bp_sigma_session_aware")).alias("lm_z_session_aware"))
    df = df.with_columns(
        (pl.col("lm_z_naive").abs() > JUMP_Z_THRESH).alias("is_jump_naive"),
        (pl.col("lm_z_session_aware").abs() > JUMP_Z_THRESH).alias("is_jump_session_aware"),
    )
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
    df = build_session_aware(sym)
    proxy = leg_proxy_for(CROSS_LEGS[sym])
    v = df.join(proxy.select("bucket", "common_proxy"), on="bucket", how="inner")
    v = v.with_columns((pl.col("ret") - pl.col("common_proxy")).alias("idio"))
    v = v.filter(pl.col("idio").abs() > pl.col("common_proxy").abs())
    v = v.filter(pl.col(f"fwd_{H}").is_not_null())

    naive_idio = v.filter(pl.col("is_jump_naive"))
    session_idio = v.filter(pl.col("is_jump_session_aware"))
    print(f"{sym}: naive detector n={naive_idio.height}  session-aware detector n={session_idio.height}")

    real_tick_check(sym, naive_idio, "NAIVE detector (original)")
    real_tick_check(sym, session_idio, "SESSION-AWARE detector (floored)")


if __name__ == "__main__":
    main()
