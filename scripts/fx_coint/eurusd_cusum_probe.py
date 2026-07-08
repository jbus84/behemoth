"""Small probe: does a diurnally-adjusted CUSUM/jump feature predict EURUSD 5m forward returns?

Ideas under test (see conversation, not yet tried in this repo):
  - 5-min bars minimum (avoid tick-bounce noise), built from true last-tick-per-minute
    bars already cached (data/tick_bars/EURUSD_1m_flow.parquet), NOT resampled
    tick-count bars (that was the stale-bar artifact in project_fx_usd_factor_residual_reversion).
  - half-hour session buckets (48/day, UTC) as the diurnal-vol denominator, causal
    (expanding mean of |return| in that bucket, up to t-1 only).
  - two-sided CUSUM on the diurnally-standardized return stream, as a feature (not a
    standalone signal) -- does |CUSUM| level predict the sign/magnitude of forward returns.
  - Lee-Mykland-style local jump z-score, as a second, independent feature.

This is a probe: quantile/IC read, real ECN cost overlay (0.6 bps RT), no WFO yet.
If this shows nothing, stop here. If it shows something, it needs the full causal/WFO
gauntlet before it goes anywhere near the meta-labeling book.
"""

from __future__ import annotations

import numpy as np
import polars as pl

COST_BPS = 0.6  # ECN round-trip, matches eurusd_ecn_15m_reversion_wfo.py
FORWARD_BARS = (6, 12, 24)  # 30m / 60m / 120m ahead, on 5m bars
CUSUM_K = 0.5  # reference slack in standardized-return units
JUMP_Z_THRESH = 4.0
BIPOWER_WINDOW = 24  # bars (~2h of 5m bars) for local vol


def load_5m(symbol: str = "EURUSD") -> pl.DataFrame:
    df = pl.read_parquet(f"data/tick_bars/{symbol}_1m_flow.parquet")
    df5 = (
        df.sort("bucket")
        .group_by_dynamic("bucket", every="5m")
        .agg(pl.col("mid").last().alias("mid"), pl.col("n_ticks").sum().alias("n_ticks"))
        .filter(pl.col("mid").is_not_null())
    )
    return df5


def add_features(df: pl.DataFrame) -> pl.DataFrame:
    df = df.with_columns(
        pl.col("mid").log().diff().alias("ret"),
        (pl.col("bucket").dt.hour() * 2 + (pl.col("bucket").dt.minute() >= 30).cast(pl.Int32)).alias("hh"),
    )
    df = df.with_columns(pl.col("ret").abs().alias("abs_ret"))

    # causal per-half-hour-bucket diurnal scale: expanding mean of abs_ret in that bucket, shifted by 1
    df = df.with_columns(pl.col("abs_ret").shift(1).over("hh").alias("abs_ret_shifted"))
    df = df.with_columns(
        pl.col("abs_ret_shifted").cum_sum().over("hh").alias("_cumsum"),
        pl.col("abs_ret_shifted").is_not_null().cum_sum().over("hh").alias("hh_n_seen"),
    )
    df = df.with_columns((pl.col("_cumsum") / pl.col("hh_n_seen")).alias("diurnal_scale"))
    df = df.filter(pl.col("hh_n_seen") >= 30).filter(pl.col("diurnal_scale") > 0)

    df = df.with_columns((pl.col("ret") / pl.col("diurnal_scale") / 0.7979).alias("z"))
    # 0.7979 = E|Z| for standard normal Z, so diurnal_scale*0.7979 approximates local sigma

    # local bipower vol for Lee-Mykland jump z-score, causal trailing window (excludes current bar)
    ret_np = df["ret"].to_numpy()
    abs_ret_np = df["abs_ret"].to_numpy()
    n = len(ret_np)
    bp_sigma = np.full(n, np.nan)
    w = BIPOWER_WINDOW
    for i in range(w + 1, n):
        window = abs_ret_np[i - w:i]  # trailing, excludes bar i
        bp = np.mean(window[1:] * window[:-1]) * (np.pi / 2)
        bp_sigma[i] = np.sqrt(bp) if bp > 0 else np.nan
    df = df.with_columns(pl.Series("bp_sigma", bp_sigma))
    df = df.with_columns((pl.col("ret") / pl.col("bp_sigma")).alias("lm_z"))
    df = df.with_columns((pl.col("lm_z").abs() > JUMP_Z_THRESH).alias("is_jump"))

    # two-sided CUSUM on standardized returns z, causal (sequential, no lookahead)
    z_arr = df["z"].to_numpy()
    s_pos = np.zeros(n)
    s_neg = np.zeros(n)
    for i in range(1, n):
        s_pos[i] = max(0.0, s_pos[i - 1] + z_arr[i] - CUSUM_K)
        s_neg[i] = min(0.0, s_neg[i - 1] + z_arr[i] + CUSUM_K)
    cusum_mag = np.maximum(s_pos, -s_neg)
    df = df.with_columns(pl.Series("cusum_mag", cusum_mag))

    for h in FORWARD_BARS:
        df = df.with_columns((pl.col("mid").log().shift(-h) - pl.col("mid").log()).alias(f"fwd_{h}"))

    return df


def report(df: pl.DataFrame) -> None:
    valid = df.filter(pl.col("bp_sigma").is_not_null() & pl.col("cusum_mag").is_not_null())
    print(f"rows usable: {valid.height} / {df.height}")

    print("\n--- CUSUM magnitude decile vs forward return (bps, sign-agnostic |ret|-normalized) ---")
    for h in FORWARD_BARS:
        v = valid.filter(pl.col(f"fwd_{h}").is_not_null()).with_columns(
            pl.col("cusum_mag").qcut(10, labels=[str(i) for i in range(10)]).alias("decile")
        )
        g = (
            v.group_by("decile")
            .agg(
                pl.col(f"fwd_{h}").mean().alias("mean_fwd_bps"),
                pl.col(f"fwd_{h}").count().alias("n"),
                (pl.col(f"fwd_{h}") * pl.col("z").sign() * -1).mean().alias("mean_fade_fwd_bps"),
            )
            .sort("decile")
        )
        g = g.with_columns((pl.col("mean_fwd_bps") * 1e4).alias("mean_fwd_bps"),
                            (pl.col("mean_fade_fwd_bps") * 1e4).alias("mean_fade_fwd_bps"))
        print(f"\nhorizon={h} bars ({h*5}min):")
        print(g)

    print("\n--- jump-flag conditioned forward returns (fade-the-jump, net of 0.6bps RT cost) ---")
    for h in FORWARD_BARS:
        v = valid.filter(pl.col(f"fwd_{h}").is_not_null())
        for flag, label in [(True, "jump bars"), (False, "non-jump bars")]:
            sub = v.filter(pl.col("is_jump") == flag)
            if sub.height == 0:
                continue
            fade_ret = (sub[f"fwd_{h}"] * sub["ret"].sign() * -1)
            gross_bps = float(fade_ret.mean()) * 1e4
            net_bps = gross_bps - COST_BPS
            t = float(fade_ret.mean() / (fade_ret.std() / np.sqrt(sub.height)))
            print(f"h={h*5}min  {label:14s} n={sub.height:7d}  gross={gross_bps:+.3f}bps  "
                  f"net={net_bps:+.3f}bps  t={t:+.2f}")

    print("\n--- half-hour session bucket: mean |ret| and CUSUM magnitude (session structure check) ---")
    g = (
        valid.group_by("hh")
        .agg(pl.col("abs_ret").mean().alias("mean_abs_ret_bps") * 1e4,
             pl.col("cusum_mag").mean().alias("mean_cusum_mag"),
             pl.col("is_jump").mean().alias("jump_rate"))
        .sort("hh")
    )
    print(g)


def main() -> None:
    import sys

    symbol = sys.argv[1] if len(sys.argv) > 1 else "EURUSD"
    print(f"=== {symbol} ===")
    df = load_5m(symbol)
    df = add_features(df)
    report(df)


if __name__ == "__main__":
    main()
