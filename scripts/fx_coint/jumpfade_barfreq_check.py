"""Does the jump-fade-120min effect survive at other bar frequencies (1m/10m/15m vs the 5m
baseline), across the 6 standard majors?

Same fixed rule throughout: Lee-Mykland jump flag (z>4 vs trailing bipower local vol),
fade over a fixed 120-minute wall-clock horizon, real Pepperstone Razor cost (spread +
0.60bps commission). Only the bar-construction frequency changes -- horizon and bipower
window are always ~120min in wall-clock terms, so bar count scales with frequency
(e.g. 120 bars at 1m, 8 bars at 15m).

Bipower local vol is vectorized here (the eurusd_cusum_probe.py version uses a python loop
that's fine at 5m/~600k rows but too slow at 1m/~2.9M rows).
"""

from __future__ import annotations

import numpy as np
import polars as pl

FREQS = {"1m": 1, "10m": 10, "15m": 15}
HORIZON_MIN = 120
BIPOWER_WINDOW_MIN = 120
JUMP_Z_THRESH = 4.0
COMMISSION_RT_BPS = 0.60

REAL_SPREAD_PIPS = {
    "EURUSD": 0.1, "GBPUSD": 0.2, "AUDUSD": 0.1,
    "USDCAD": 0.5, "USDCHF": 0.4, "USDJPY": 0.3,
}
MAJORS = list(REAL_SPREAD_PIPS)


def load_bars(symbol: str, freq_min: int) -> pl.DataFrame:
    df = pl.read_parquet(f"data/tick_bars/{symbol}_1m_flow.parquet")
    if freq_min == 1:
        return df.select("bucket", "mid").sort("bucket")
    return (
        df.sort("bucket")
        .group_by_dynamic("bucket", every=f"{freq_min}m")
        .agg(pl.col("mid").last().alias("mid"))
        .filter(pl.col("mid").is_not_null())
    )


def rolling_bipower(abs_ret: np.ndarray, w: int) -> np.ndarray:
    n = len(abs_ret)
    if w < 2 or n < w + 2:
        return np.full(n, np.nan)
    prod = abs_ret[1:] * abs_ret[:-1]
    csum = np.concatenate([[0.0], np.cumsum(prod)])
    bp_sigma = np.full(n, np.nan)
    idx = np.arange(w + 1, n)
    lo = idx - w
    hi = idx - 1
    sums = csum[hi] - csum[lo]
    means = sums / (w - 1)
    bp = means * (np.pi / 2)
    bp_sigma[idx] = np.sqrt(np.where(bp > 0, bp, np.nan))
    return bp_sigma


def build(symbol: str, freq_min: int) -> pl.DataFrame:
    df = load_bars(symbol, freq_min)
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
    min_hh_obs = max(30, int(30 * (5 / freq_min)))  # keep a comparable calendar burn-in across freqs
    df = df.filter(pl.col("hh_n_seen") >= min_hh_obs).filter(pl.col("diurnal_scale") > 0)

    w = max(4, round(BIPOWER_WINDOW_MIN / freq_min))
    abs_ret_np = df["abs_ret"].to_numpy()
    bp_sigma = rolling_bipower(abs_ret_np, w)
    df = df.with_columns(pl.Series("bp_sigma", bp_sigma))
    df = df.with_columns((pl.col("ret") / pl.col("bp_sigma")).alias("lm_z"))
    df = df.with_columns((pl.col("lm_z").abs() > JUMP_Z_THRESH).alias("is_jump"))

    h_bars = max(1, round(HORIZON_MIN / freq_min))
    df = df.with_columns((pl.col("mid").log().shift(-h_bars) - pl.col("mid").log()).alias("fwd"))
    return df.with_columns(pl.col("bucket").dt.year().alias("year"))


def fade_stats(fwd: np.ndarray, ret_sign: np.ndarray, cost_bps: float) -> tuple[float, float, float, int]:
    fade = fwd * ret_sign * -1
    n = len(fade)
    if n < 20:
        return float("nan"), float("nan"), float("nan"), n
    gross_bps = float(fade.mean()) * 1e4
    net_bps = gross_bps - cost_bps
    se = fade.std() / np.sqrt(n)
    t = float(fade.mean() / se) if se > 0 else float("nan")
    return gross_bps, net_bps, t, n


def real_cost_bps(symbol: str, avg_mid: float) -> float:
    pip_size = 0.01 if symbol == "USDJPY" else 0.0001
    spread_bps = REAL_SPREAD_PIPS[symbol] * pip_size / avg_mid * 1e4
    return spread_bps + COMMISSION_RT_BPS


def run(symbol: str, freq_label: str, freq_min: int) -> None:
    df = build(symbol, freq_min)
    valid = df.filter(pl.col("bp_sigma").is_not_null() & pl.col("is_jump") & pl.col("fwd").is_not_null())
    cost = real_cost_bps(symbol, float(valid["mid"].mean()))
    fwd = valid["fwd"].to_numpy()
    sgn = valid["ret"].sign().to_numpy()
    gross, net, t, n = fade_stats(fwd, sgn, cost)

    years = sorted(valid["year"].unique().to_list())
    mid_year = years[len(years) // 2] if years else None
    net1 = net2 = t1 = t2 = float("nan")
    n1 = n2 = 0
    if mid_year is not None:
        first = valid.filter(pl.col("year") < mid_year)
        second = valid.filter(pl.col("year") >= mid_year)
        _, net1, t1, n1 = fade_stats(first["fwd"].to_numpy(), first["ret"].sign().to_numpy(), cost)
        _, net2, t2, n2 = fade_stats(second["fwd"].to_numpy(), second["ret"].sign().to_numpy(), cost)

    print(f"  {symbol:8s} {freq_label:4s}  n={n:6d}  cost={cost:.3f}  gross={gross:+7.3f}  net={net:+7.3f}"
          f"  t={t:+6.2f}   | half1 net={net1:+6.3f}(t{t1:+.2f},n{n1})  half2 net={net2:+6.3f}(t{t2:+.2f},n{n2})")


def main() -> None:
    for sym in MAJORS:
        print(f"\n=== {sym} ===")
        for freq_label, freq_min in FREQS.items():
            run(sym, freq_label, freq_min)


if __name__ == "__main__":
    main()
