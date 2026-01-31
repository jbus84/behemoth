import argparse
from pathlib import Path

import numpy as np
import polars as pl


def _update_sums(sums, x, y):
    # weights = |x| to weight by burst magnitude
    w = np.abs(x)
    mask = np.isfinite(x) & np.isfinite(y) & np.isfinite(w)
    if not mask.any():
        return
    x = x[mask]
    y = y[mask]
    w = w[mask]

    sums["count"] += len(x)
    sums["sum_w"] += w.sum()
    sums["sum_wx"] += (w * x).sum()
    sums["sum_wy"] += (w * y).sum()
    sums["sum_wx2"] += (w * x * x).sum()
    sums["sum_wy2"] += (w * y * y).sum()
    sums["sum_wxy"] += (w * x * y).sum()


def _weighted_corr(sums):
    if sums["sum_w"] <= 0:
        return np.nan
    mean_x = sums["sum_wx"] / sums["sum_w"]
    mean_y = sums["sum_wy"] / sums["sum_w"]
    cov = sums["sum_wxy"] / sums["sum_w"] - mean_x * mean_y
    var_x = sums["sum_wx2"] / sums["sum_w"] - mean_x * mean_x
    var_y = sums["sum_wy2"] / sums["sum_w"] - mean_y * mean_y
    if var_x <= 0 or var_y <= 0:
        return np.nan
    return cov / np.sqrt(var_x * var_y)


def analyze_burst_lead_lag(
    idx_name: str,
    tick_root: str,
    year: int = 2025,
    max_lag_s: int = 60,
    burst_bps: float = 2.0,
    by_month: bool = False,
):
    months = [f"{year}{m:02d}" for m in range(1, 13)]
    fx_pairs = ["EURUSD", "GBPUSD", "USDCHF", "USDJPY"]

    root = Path(tick_root)
    idx_dir = root / idx_name

    def _init_results():
        return {
            fx_name: {
                lag: {
                    "count": 0,
                    "sum_w": 0.0,
                    "sum_wx": 0.0,
                    "sum_wy": 0.0,
                    "sum_wx2": 0.0,
                    "sum_wy2": 0.0,
                    "sum_wxy": 0.0,
                }
                for lag in range(0, max_lag_s + 1)
            }
            for fx_name in fx_pairs
        }

    results = {}
    if by_month:
        results = {ym: _init_results() for ym in months}
    else:
        results = _init_results()

    for ym in months:
        idx_path = idx_dir / f"{idx_name}_{ym}_ticks.parquet"
        if not idx_path.exists():
            continue

        idx = (
            pl.read_parquet(idx_path)
            .select(["timestamp", "mid"])
            .rename({"mid": "idx_px"})
            .sort("timestamp")
        )

        for fx_name in fx_pairs:
            fx_path = root / fx_name / f"{fx_name}_{ym}_ticks.parquet"
            if not fx_path.exists():
                continue

            fx = (
                pl.read_parquet(fx_path)
                .select(["timestamp", "mid"])
                .rename({"mid": "fx_px"})
                .sort("timestamp")
            )

            start = max(idx["timestamp"].min(), fx["timestamp"].min())
            end = min(idx["timestamp"].max(), fx["timestamp"].max())
            grid = (
                pl.datetime_range(start, end, "1s", eager=True)
                .to_frame("timestamp")
                .with_columns(pl.col("timestamp").dt.cast_time_unit("ns"))
                .sort("timestamp")
            )

            combined = grid.join_asof(idx, on="timestamp", strategy="backward")
            combined = combined.join_asof(fx, on="timestamp", strategy="backward").drop_nulls()

            if len(combined) < max_lag_s + 10:
                continue

            combined = combined.with_columns(
                [
                    ((pl.col("idx_px") / pl.col("idx_px").shift(1)) - 1).alias("idx_ret_1s"),
                    (((pl.col("fx_px") / pl.col("fx_px").shift(5)) - 1) * 10000).alias(
                        "fx_ret_5s"
                    ),
                ]
            ).drop_nulls()

            bursts = combined.filter(pl.col("fx_ret_5s").abs() >= burst_bps)
            if len(bursts) == 0:
                continue

            x = bursts["fx_ret_5s"].to_numpy()
            burst_idx = bursts.select(pl.arange(0, pl.len()).alias("idx")).to_series().to_numpy()

            idx_ret = combined["idx_ret_1s"].to_numpy()

            for lag in range(0, max_lag_s + 1):
                y_idx = burst_idx + lag
                y_idx = y_idx[y_idx < len(idx_ret)]
                if len(y_idx) == 0:
                    continue
                y = idx_ret[y_idx]
                x_use = x[: len(y_idx)]
                if by_month:
                    _update_sums(results[ym][fx_name][lag], x_use, y)
                else:
                    _update_sums(results[fx_name][lag], x_use, y)

    def _summarize(res):
        summary = []
        for fx_name in fx_pairs:
            best = None
            for lag in range(0, max_lag_s + 1):
                corr = _weighted_corr(res[fx_name][lag])
                count = res[fx_name][lag]["count"]
                if np.isnan(corr) or count == 0:
                    continue
                if best is None or abs(corr) > abs(best["corr"]):
                    best = {"lag": lag, "corr": corr, "count": count}
            if best:
                summary.append(
                    {
                        "FX Pair": fx_name,
                        "Peak Lag (s)": best["lag"],
                        "Weighted Corr": round(best["corr"], 4),
                        "Samples": best["count"],
                    }
                )
        return pl.DataFrame(summary)

    if by_month:
        monthly = []
        for ym in months:
            if ym not in results:
                continue
            summary = _summarize(results[ym])
            if len(summary) == 0:
                continue
            summary = summary.with_columns(pl.lit(ym).alias("Month"))
            monthly.append(summary)
        if monthly:
            return pl.concat(monthly).select(["Month", "FX Pair", "Peak Lag (s)", "Weighted Corr", "Samples"])
        return pl.DataFrame([])

    return _summarize(results)


def main():
    parser = argparse.ArgumentParser(
        description="Lead-lag during FX burst events (weighted by burst size)."
    )
    parser.add_argument("--idx", required=True, help="Index symbol (NSXUSD or SPXUSD)")
    parser.add_argument("--tick-root", default="/Users/danielfisher/Desktop/tick")
    parser.add_argument("--year", type=int, default=2025)
    parser.add_argument("--max-lag", type=int, default=60)
    parser.add_argument("--burst-bps", type=float, default=2.0)
    parser.add_argument("--by-month", action="store_true")
    args = parser.parse_args()

    res = analyze_burst_lead_lag(
        args.idx,
        args.tick_root,
        year=args.year,
        max_lag_s=args.max_lag,
        burst_bps=args.burst_bps,
        by_month=args.by_month,
    )
    print(f"\n--- Burst Lead/Lag (Weighted) for {args.idx} ---")
    if args.by_month and len(res) > 0:
        print(res.sort(["Month", "Weighted Corr"], descending=[False, True]))
    else:
        print(res.sort("Weighted Corr", descending=True))


if __name__ == "__main__":
    main()
