"""Two follow-ups on the AUDUSD jump-fade-120min candidate:

1. Hour-of-day / day-of-week breakdown -- DESCRIPTIVE ONLY (no subsetting/filtering,
   since the half-hour "top-third" filter already turned out to be a multiplicity
   artifact that didn't replicate). Just: is the effect roughly uniform across the day
   and week, or concentrated in a way that would need explaining?

2. AUD-family cross-symbol test + combination -- run the identical fixed rule (z>4 jump
   flag, fade over 120min/24x5m bars) on AUDCAD, AUDJPY, AUDNZD (the other AUD crosses
   with cached data), independent of AUDUSD. If this is a genuine AUD-specific liquidity/
   flow mechanism (as the USD-commonality filter suggested), it should show up here too,
   not just in the one USD-major pairing. Then build a pooled AUD-book: at each 5m bar,
   equal-weight the fade return across whichever AUD pairs have a flagged jump at that
   bar, and see if pooling improves stability (diversification) the way the engineered
   FX book combined sleeves in project_fx_engineered_book.

AUDCAD/AUDJPY/AUDNZD have no verified real-spread figure anywhere in this repo (only
AUDUSD's 0.1pip Razor figure is verified) -- swept across plausible ranges, explicitly
flagged as estimates, not asserted as fact.
"""

from __future__ import annotations

import numpy as np
import polars as pl

from scripts.fx_coint.eurusd_cusum_probe import add_features, load_5m

H = 24  # 120min
COMMISSION_RT_BPS = 0.60

AUD_PAIRS = ["AUDUSD", "AUDCAD", "AUDJPY", "AUDNZD"]
VERIFIED_SPREAD_PIPS = {"AUDUSD": 0.1}  # Razor, verified (usd_factor_pepperstone_cost.py)
UNVERIFIED_SPREAD_SWEEP = {
    "AUDCAD": (0.4, 0.7, 1.2),
    "AUDJPY": (0.3, 0.5, 0.9),
    "AUDNZD": (0.8, 1.3, 2.0),
}


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


def real_cost_bps(symbol: str, avg_mid: float, spread_pips: float) -> float:
    pip_size = 0.01 if symbol == "AUDJPY" else 0.0001
    return spread_pips * pip_size / avg_mid * 1e4 + COMMISSION_RT_BPS


def get_jump_frame(symbol: str) -> pl.DataFrame:
    df = load_5m(symbol)
    df = add_features(df)
    return df.filter(
        pl.col("bp_sigma").is_not_null() & pl.col("is_jump") & pl.col(f"fwd_{H}").is_not_null()
    ).with_columns(pl.col("bucket").dt.year().alias("year"))


def half_split_report(valid: pl.DataFrame, cost_bps: float, label: str) -> None:
    fwd = valid[f"fwd_{H}"].to_numpy()
    sgn = valid["ret"].sign().to_numpy()
    gross, net, t, n = fade_stats(fwd, sgn, cost_bps)
    years = sorted(valid["year"].unique().to_list())
    mid_year = years[len(years) // 2]
    first = valid.filter(pl.col("year") < mid_year)
    second = valid.filter(pl.col("year") >= mid_year)
    _, net1, t1, n1 = fade_stats(first[f"fwd_{H}"].to_numpy(), first["ret"].sign().to_numpy(), cost_bps)
    _, net2, t2, n2 = fade_stats(second[f"fwd_{H}"].to_numpy(), second["ret"].sign().to_numpy(), cost_bps)
    print(f"  {label:28s} n={n:5d}  gross={gross:+7.3f}  net={net:+7.3f}  t={t:+6.2f}"
          f"   | half1 net={net1:+6.3f}(t{t1:+.2f},n{n1})  half2 net={net2:+6.3f}(t{t2:+.2f},n{n2})")


def hour_dow_diagnostic(valid: pl.DataFrame, cost_bps: float) -> None:
    v = valid.with_columns(
        pl.col("bucket").dt.hour().alias("hour"),
        pl.col("bucket").dt.weekday().alias("dow"),  # 1=Mon..7=Sun
        (pl.col(f"fwd_{H}") * pl.col("ret").sign() * -1).alias("fade_ret"),
    )
    print("\n  -- by hour of day (UTC), descriptive only --")
    g = (
        v.group_by("hour")
        .agg(pl.col("fade_ret").mean().alias("m"), pl.len().alias("n"))
        .sort("hour")
        .with_columns(((pl.col("m") * 1e4) - cost_bps).alias("net_bps"))
    )
    for row in g.iter_rows(named=True):
        print(f"    hour={row['hour']:02d}  n={row['n']:4d}  net={row['net_bps']:+7.3f}bps")

    print("\n  -- by day of week, descriptive only --")
    g2 = (
        v.group_by("dow")
        .agg(pl.col("fade_ret").mean().alias("m"), pl.len().alias("n"))
        .sort("dow")
        .with_columns(((pl.col("m") * 1e4) - cost_bps).alias("net_bps"))
    )
    dow_names = {1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat", 7: "Sun"}
    for row in g2.iter_rows(named=True):
        print(f"    {dow_names.get(row['dow'], row['dow']):3s}  n={row['n']:4d}  net={row['net_bps']:+7.3f}bps")


def main() -> None:
    frames: dict[str, pl.DataFrame] = {}
    for sym in AUD_PAIRS:
        frames[sym] = get_jump_frame(sym)

    print("=== AUDUSD: hour-of-day / day-of-week diagnostic (descriptive, no subsetting) ===")
    audusd_cost = real_cost_bps("AUDUSD", float(frames["AUDUSD"]["mid"].mean()), 0.1)
    hour_dow_diagnostic(frames["AUDUSD"], audusd_cost)

    print("\n\n=== AUD-cross replication: same fixed rule, independent pairs ===")
    for sym in ["AUDCAD", "AUDJPY", "AUDNZD"]:
        v = frames[sym]
        avg_mid = float(v["mid"].mean())
        print(f"\n{sym} (no verified spread -- sweeping plausible pip range):")
        for sp in UNVERIFIED_SPREAD_SWEEP[sym]:
            cost = real_cost_bps(sym, avg_mid, sp)
            half_split_report(v, cost, f"@{sp}pip (cost={cost:.2f}bps)")

    print("\n\n=== Pooled AUD-book v2: AUDUSD+AUDCAD+AUDNZD only (drop AUDJPY -- weak/decaying) ===")
    print("(using mid-of-sweep cost per pair; AUDUSD 0.1pip verified)")
    conservative_cost = {
        "AUDUSD": real_cost_bps("AUDUSD", float(frames["AUDUSD"]["mid"].mean()), 0.1),
        "AUDCAD": real_cost_bps("AUDCAD", float(frames["AUDCAD"]["mid"].mean()), 0.7),
        "AUDNZD": real_cost_bps("AUDNZD", float(frames["AUDNZD"]["mid"].mean()), 1.3),
    }
    POOL_PAIRS = ["AUDUSD", "AUDCAD", "AUDNZD"]
    per_bar = []
    for sym in POOL_PAIRS:
        v = frames[sym].select(
            "bucket",
            (pl.col(f"fwd_{H}") * pl.col("ret").sign() * -1 * 1e4 - conservative_cost[sym]).alias(f"net_{sym}")
        )
        per_bar.append(v)
    pooled = per_bar[0]
    for v in per_bar[1:]:
        pooled = pooled.join(v, on="bucket", how="full", coalesce=True)
    net_cols = [f"net_{s}" for s in POOL_PAIRS]
    pooled = pooled.with_columns(
        pl.mean_horizontal([pl.col(c) for c in net_cols]).alias("book_net"),
        pl.sum_horizontal([pl.col(c).is_not_null().cast(pl.Int32) for c in net_cols]).alias("n_active"),
    ).filter(pl.col("n_active") > 0).sort("bucket")

    n = pooled.height
    m = pooled["book_net"].mean()
    se = pooled["book_net"].std() / np.sqrt(n)
    t = m / se if se > 0 else float("nan")
    print(f"\n  pooled book: n_bars_with_>=1_active_jump={n}  mean_net={m:+.3f}bps  t={t:+.2f}")
    years = pooled.with_columns(pl.col("bucket").dt.year().alias("year"))["year"]
    yrs = sorted(years.unique().to_list())
    mid_year = yrs[len(yrs) // 2]
    p1 = pooled.filter(pl.col("bucket").dt.year() < mid_year)
    p2 = pooled.filter(pl.col("bucket").dt.year() >= mid_year)
    for label, p in [("first half", p1), ("second half", p2)]:
        n_, m_ = p.height, p["book_net"].mean()
        se_ = p["book_net"].std() / np.sqrt(n_)
        t_ = m_ / se_ if se_ > 0 else float("nan")
        print(f"    {label:12s} n={n_:5d}  mean_net={m_:+.3f}bps  t={t_:+.2f}")


if __name__ == "__main__":
    main()
