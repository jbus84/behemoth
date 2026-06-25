"""Probe the scalp families at 5m and 15m bars (the cost wall recedes as bar size grows).

Reuses the Phase 0 family signal builders + evaluator, but builds enriched bars at a
configurable freq. EURUSD 2024 (taker cost). Sweeps entry_quantile to check the tail.

Usage:
    uv run python scripts/fx_coint/scalp_tf_probe.py --year 2024 --symbol EURUSD
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

from scripts.fx_coint.flow_proxies import quote_ofi, tick_rule_signs  # noqa: E402
from scripts.fx_coint.phase0_family_a import build_flow_residual_signal  # noqa: E402
from scripts.fx_coint.phase0_family_b import build_quote_revision_signal  # noqa: E402
from scripts.fx_coint.phase0_family_c import build_peer_lag_signal  # noqa: E402
from scripts.fx_coint.phase0_family_d import build_microstructure_classifier  # noqa: E402
from scripts.fx_coint.phase0_scalp_common import (  # noqa: E402
    DEFAULT_COST_BPS,
    _pip_size,
    add_rolling_features,
    compute_forward_returns,
    evaluate_family,
    load_raw_ticks,
)

PEERS = ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCHF", "USDCAD"]


def build_enriched(ticks: pl.DataFrame, symbol: str, freq: str) -> pd.DataFrame:
    """build_enriched_1m_bars generalized to any truncate freq (e.g. 5m, 15m)."""
    tsign = tick_rule_signs(ticks["mid"].to_numpy())
    ofi = quote_ofi(ticks["bid"].to_numpy(), ticks["ask"].to_numpy())
    t = (
        ticks.sort("timestamp")
        .with_columns(
            pl.Series("tsign", tsign),
            pl.Series("ofi", ofi),
            pl.col("timestamp").dt.truncate(freq).alias("bucket"),
        )
        .with_columns(
            pl.col("bid").diff().over("bucket").alias("db"),
            pl.col("ask").diff().over("bucket").alias("da"),
        )
        .with_columns(((pl.col("db").abs() > 0) | (pl.col("da").abs() > 0)).cast(pl.Int8).alias("rev"))
    )
    bars = (
        t.group_by("bucket")
        .agg(
            pl.col("mid").last().alias("mid"), pl.col("bid").last().alias("bid"),
            pl.col("ask").last().alias("ask"), pl.col("bid").first().alias("open_bid"),
            pl.col("bid").max().alias("high_bid"), pl.col("bid").min().alias("low_bid"),
            pl.col("ask").first().alias("open_ask"), pl.col("ask").max().alias("high_ask"),
            pl.col("tsign").mean().alias("flow_tick"), pl.col("ofi").mean().alias("flow_ofi"),
            pl.len().alias("n_ticks"), pl.col("rev").sum().alias("quote_revisions"),
        )
        .sort("bucket")
    )
    pip = _pip_size(symbol)
    bars = bars.with_columns(
        pl.col("bucket").dt.hour().alias("hour_utc"),
        ((pl.col("ask") - pl.col("bid")) / pl.col("mid") * 10_000).alias("spread_bps"),
        ((pl.col("high_bid") - pl.col("low_bid")) / pip).alias("range_pips"),
        ((pl.col("bid") - pl.col("open_bid")) / pip).alias("bar_move_pips"),
        pl.col("n_ticks").alias("tick_volume"),
    ).with_columns(
        (60.0 / pl.col("tick_volume")).alias("tick_rate_hz"),
        pl.when(pl.col("bid") - pl.col("open_bid") > 0).then(1.0)
        .when(pl.col("bid") - pl.col("open_bid") < 0).then(-1.0).otherwise(0.0).alias("bar_return_sign"),
    )
    return bars.sort("bucket").to_pandas()


def run(symbol: str, year: int, freqs: list[str], quantiles: list[float]) -> None:
    cf = DEFAULT_COST_BPS.get(symbol, 0.80) / 10_000
    raw = {symbol: load_raw_ticks(symbol, year)}
    for freq in freqs:
        bars = {symbol: build_enriched(raw[symbol], symbol, freq)}
        df = add_rolling_features(bars[symbol], symbol)
        df = compute_forward_returns(df, [1, 3, 5])
        # peers for family C (aligned to target buckets)
        peer_dfs = {}
        for s in [p for p in PEERS if p != symbol]:
            if s not in raw:
                raw[s] = load_raw_ticks(s, year)
            pb = build_enriched(raw[s], s, freq).set_index("bucket").reindex(df["bucket"]).reset_index()
            pb["mid_ret"] = np.log(pb["mid"].astype(float) / pb["mid"].astype(float).shift(1))
            pb.attrs["symbol"] = s
            peer_dfs[s] = pb
        tdf = df.copy()
        tdf.attrs["symbol"] = symbol

        sigs = {
            "A_flow": build_flow_residual_signal(df, window=5),
            "B_quoterev": build_quote_revision_signal(df),
            "C_leadlag": build_peer_lag_signal(tdf, peer_dfs, window=50, max_lag=3).where(
                df["vol_cluster_score"] > 1.0, np.nan),
            "D_cocktail": build_microstructure_classifier(df, np.sign(df["fwd_ret_1"].to_numpy())),
        }
        nbars = len(df)
        print(f"\n=== {symbol} {freq} ({nbars} bars, h1={freq} h3=3x h5=5x; cost {cf*1e4:.2f}bps) ===")
        print(f"{'family':>12} {'h':>3} {'q':>5} {'n':>6} {'grossIC':>8} {'tailGross':>10} {'net_lb95':>9} {'verdict':>9}")
        for name, s in sigs.items():
            for h in (1, 3, 5):
                for q in quantiles:
                    r = evaluate_family(s, df[f"fwd_ret_{h}"], cf, entry_quantile=q)
                    flag = "  <<<" if r["net_lb95_bps"] > 0 else ""
                    print(f"{name:>12} {h:>3} {q:>5} {r['n_entries']:>6} {r['gross_ic']:>8} "
                          f"{r['decile_spread_bps']:>10} {r['net_lb95_bps']:>9} {r['verdict']:>9}{flag}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="EURUSD")
    p.add_argument("--year", type=int, default=2024)
    p.add_argument("--freqs", nargs="+", default=["5m", "15m"])
    p.add_argument("--quantiles", nargs="+", type=float, default=[0.90, 0.95])
    args = p.parse_args()
    run(args.symbol.upper(), args.year, args.freqs, args.quantiles)


if __name__ == "__main__":
    main()
