"""Screen the remaining minors/crosses with cached data for the jump-fade-120min effect,
same fixed rule as everywhere else in this investigation (LM jump z>4 vs trailing bipower
vol, fade over 120min/24x5m bars). Unconditioned (no USD-commonality split) -- this is a
first screening pass, same as how AUDCAD/AUDNZD/AUDJPY were originally screened before
the deeper commonality work.

None of these pairs have a verified real spread in this repo -- every cost is a swept
estimate (optimistic/plausible/conservative), explicitly flagged, not asserted as fact.
"""

from __future__ import annotations

import numpy as np
import polars as pl

from scripts.fx_coint.eurusd_cusum_probe import add_features, load_5m

H = 24
COMMISSION_RT_BPS = 0.60

# NZDUSD is a genuine major (7th G10 currency); the rest are crosses. All spread figures
# below are estimates based on typical retail ECN liquidity tiers, NOT verified broker data.
SPREAD_SWEEP_PIPS = {
    "NZDUSD": (0.6, 1.0, 1.5),
    "EURGBP": (0.3, 0.6, 1.0),
    "EURCHF": (0.4, 0.7, 1.2),
    "EURJPY": (0.4, 0.7, 1.2),
    "GBPJPY": (0.6, 1.0, 1.6),
    "GBPCHF": (1.2, 2.0, 3.0),
    "EURAUD": (1.2, 2.0, 3.0),
    "CADJPY": (1.2, 2.0, 3.0),
    "CHFJPY": (1.2, 2.0, 3.0),
    "GBPAUD": (2.0, 3.0, 4.5),
    "EURNZD": (2.0, 3.0, 4.5),
    "GBPNZD": (2.5, 4.0, 6.0),
}
JPY_PAIRS = {"EURJPY", "GBPJPY", "CADJPY", "CHFJPY"}


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
    pip_size = 0.01 if symbol in JPY_PAIRS else 0.0001
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
    print(f"  {label:24s} n={n:5d}  gross={gross:+7.3f}  net={net:+7.3f}  t={t:+6.2f}"
          f"   | half1 net={net1:+6.3f}(t{t1:+.2f},n{n1})  half2 net={net2:+6.3f}(t{t2:+.2f},n{n2})")


def main() -> None:
    for sym, sweep in SPREAD_SWEEP_PIPS.items():
        print(f"\n=== {sym} (unverified spread, sweeping {sweep} pip) ===")
        valid = get_jump_frame(sym)
        for sp in sweep:
            avg_mid = float(valid["mid"].mean())
            cost = real_cost_bps(sym, avg_mid, sp)
            half_split_report(valid, cost, f"@{sp}pip (cost={cost:.2f}bps)")


if __name__ == "__main__":
    main()
