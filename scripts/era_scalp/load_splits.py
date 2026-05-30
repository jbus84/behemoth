from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.era_scalp.score_program import ScalpSplitData


def cap_recent(split: ScalpSplitData, max_bars: int | None) -> ScalpSplitData:
    """Return the most-recent `max_bars` of a split (contiguous, time-ordered).

    Used to bound the DISCOVERY-loop scoring split so a sensible-but-heavy
    program (e.g. an O(n*W) rolling estimator) does not blow the 10s sandbox
    timeout on the full ~200k-bar validation set and get silently dropped. A
    contiguous recent slice is used (NOT stride-sampling) so trailing-window /
    EWMA programs stay meaningful. The holdout is always scored on full data.
    """
    n = split.X.shape[0]
    if max_bars is None or n <= max_bars:
        return split
    sl = slice(n - max_bars, None)
    return ScalpSplitData(
        X=split.X[sl],
        names=split.names,
        hour=None if split.hour is None else split.hour[sl],
        y_fwd=split.y_fwd[sl],
        cost=split.cost[sl],
        test_month=split.test_month[sl],
        close_ts=None if split.close_ts is None else split.close_ts[sl],
    )

# Causal, stationary feature whitelist (audited backward/.shift(1) in
# scripts/build_tick_velocity_dataset.py). Excludes y_fwd_*, raw OHLC,
# cost_est_pips, close_ts, bar_ticks.
WHITELIST: list[str] = [
    "spread_pips", "spread_z", "tick_volume", "tick_rate_hz", "tick_rate_z",
    "tick_burst", "tick_burst_score", "high_pos_tick", "low_pos_tick",
    "hl_pos_delta_tick", "bar_return_sign", "vel_pips_h1", "vel_pips_h2",
    "vel_pips_h5", "vel_pips_h10", "vel_z_h1", "vel_z_h2", "vel_z_h5",
    "vel_z_h10", "accel_pips", "hour_utc",
]


def build_splits(
    symbol: str,
    parquet_path: Path,
    horizon: int = 1,
    train=("2018", "2019", "2020", "2021", "2022", "2023"),
    validation=("2024",),
    holdout=("2025", "2026"),
) -> dict[str, ScalpSplitData]:
    df = pd.read_parquet(parquet_path)
    df["close_ts"] = pd.to_datetime(df["close_ts"], utc=True, errors="coerce")
    df = df[df["close_ts"].notna()].sort_values("close_ts").reset_index(drop=True)
    df["year"] = df["close_ts"].dt.strftime("%Y")
    df["test_month"] = df["close_ts"].dt.strftime("%Y-%m")
    ycol = f"y_fwd_pips_h{horizon}"

    def _split(years, embargo_tail: bool) -> ScalpSplitData:
        d = df[df["year"].isin(years)].reset_index(drop=True)
        if embargo_tail and len(d) > horizon:
            d = d.iloc[: len(d) - horizon].reset_index(drop=True)
        return ScalpSplitData(
            X=d[WHITELIST].to_numpy(float),
            names=list(WHITELIST),
            hour=d["hour_utc"].to_numpy(float),
            y_fwd=d[ycol].to_numpy(float),
            cost=d["cost_est_pips"].to_numpy(float),
            test_month=d["test_month"].to_numpy(),
            close_ts=d["close_ts"].to_numpy(),
        )

    return {
        "train": _split(train, embargo_tail=True),
        "validation": _split(validation, embargo_tail=True),
        "holdout": _split(holdout, embargo_tail=False),
    }
