"""Shared utilities for the Phase 0 scalp-discovery sandbox.

Self-contained: defines the Pepperstone-Razor cost model locally (the family scripts
import DEFAULT_COST_BPS from here) so the sandbox has no dependency on untracked modules.
All features are causal (`.shift(1)` on rolling/ewm, `.shift(-h)` only on forward returns).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import polars as pl

from scripts.fx_coint.flow_proxies import quote_ofi, tick_rule_signs

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Pepperstone-Razor round-trip cost (bps), commission + tight raw spread.
DEFAULT_COST_BPS: dict[str, float] = {
    "EURUSD": 0.64,
    "GBPUSD": 0.80,
    "AUDUSD": 0.88,
    "USDJPY": 0.72,
    "USDCHF": 0.88,
    "USDCAD": 0.88,
}


def _pip_size(symbol: str) -> float:
    return 0.01 if str(symbol).upper().endswith("JPY") else 0.0001


def load_raw_ticks(symbol: str, year: int) -> pl.DataFrame:
    """Load raw dukascopy tick parquets for symbol+year.

    Files: ~/Desktop/dukascopy_ticks/{SYMBOL}/{SYMBOL}_YYYYMM_ticks.parquet.
    Columns: timestamp, bid, ask, mid, spread, log_return.
    """
    sym = symbol.upper()
    src = Path.home() / "Desktop" / "dukascopy_ticks" / sym
    if not src.exists():
        raise FileNotFoundError(f"Raw tick directory not found: {src}")
    files = sorted(src.glob(f"{sym}_{year}*_ticks.parquet"))
    if not files:
        raise FileNotFoundError(f"No tick parquet files for {sym} {year} in {src}")
    return pl.concat([pl.read_parquet(f) for f in files]).sort("timestamp")


def build_enriched_1m_bars(ticks: pl.DataFrame, symbol: str) -> pd.DataFrame:
    """True 1-min time bars with intra-bar microstructure aggregates (OHLC on bid/ask,
    mean tick-rule flow + OFI, tick count, quote-revision count, derived ratios)."""
    tsign = tick_rule_signs(ticks["mid"].to_numpy())
    ofi = quote_ofi(ticks["bid"].to_numpy(), ticks["ask"].to_numpy())

    t = (
        ticks.sort("timestamp")
        .with_columns(
            pl.Series("tsign", tsign),
            pl.Series("ofi", ofi),
            pl.col("timestamp").dt.truncate("1m").alias("bucket"),
        )
        .with_columns(
            pl.col("bid").diff().over("bucket").alias("db"),
            pl.col("ask").diff().over("bucket").alias("da"),
        )
        .with_columns(
            ((pl.col("db").abs() > 0) | (pl.col("da").abs() > 0)).cast(pl.Int8).alias("rev")
        )
    )

    bars = (
        t.group_by("bucket")
        .agg(
            pl.col("mid").last().alias("mid"),
            pl.col("bid").last().alias("bid"),
            pl.col("ask").last().alias("ask"),
            pl.col("bid").first().alias("open_bid"),
            pl.col("bid").max().alias("high_bid"),
            pl.col("bid").min().alias("low_bid"),
            pl.col("ask").first().alias("open_ask"),
            pl.col("ask").max().alias("high_ask"),
            pl.col("tsign").mean().alias("flow_tick"),
            pl.col("ofi").mean().alias("flow_ofi"),
            pl.len().alias("n_ticks"),
            pl.col("rev").sum().alias("quote_revisions"),
        )
        .sort("bucket")
    )

    pip = _pip_size(symbol)
    bars = bars.with_columns(
        pl.col("bucket").dt.hour().alias("hour_utc"),
        ((pl.col("ask") - pl.col("bid")) / pl.col("mid") * 10_000).alias("spread_bps"),
        ((pl.col("high_bid") - pl.col("low_bid")) / pip).alias("range_pips"),
        ((pl.col("bid") - pl.col("open_bid")) / pip).alias("bar_move_pips"),  # close=last bid
        pl.col("n_ticks").alias("tick_volume"),
    ).with_columns(
        (60.0 / pl.col("tick_volume")).alias("tick_rate_hz"),
        pl.when(pl.col("bid") - pl.col("open_bid") > 0)
        .then(1.0)
        .when(pl.col("bid") - pl.col("open_bid") < 0)
        .then(-1.0)
        .otherwise(0.0)
        .alias("bar_return_sign"),
    )
    return bars.sort("bucket").to_pandas()


def save_enriched_bars(df: pd.DataFrame, symbol: str, freq: str = "1m") -> Path:
    out_dir = _REPO_ROOT / "data" / "tick_bars"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{symbol.upper()}_{freq}_enriched.parquet"
    df.to_parquet(path)
    return path


def compute_forward_returns(df: pd.DataFrame, horizons: list[int]) -> pd.DataFrame:
    """Forward log-returns fwd_ret_h = log(mid[t+h] / mid[t]) (causal label)."""
    mid = df["mid"].astype(float)
    for h in horizons:
        df[f"fwd_ret_{h}"] = np.log(mid.shift(-h) / mid)
    return df


def _zscore(x: pd.Series, window: int = 24, minp: int = 8) -> pd.Series:
    mu = x.rolling(window, min_periods=minp).mean().shift(1)
    sd = x.rolling(window, min_periods=minp).std(ddof=0).shift(1)
    return (x - mu) / sd.replace(0, np.nan)


def add_rolling_features(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Causal rolling features for Families B and D (all windows `.shift(1)`)."""
    pip = _pip_size(symbol)
    df = df.copy()
    close_bid = df["bid"].astype(float)

    df["vel_pips_h1"] = (close_bid - close_bid.shift(1)) / pip
    df["accel_pips"] = df["vel_pips_h1"] - df["vel_pips_h1"].shift(1)
    df["tick_rate_z"] = _zscore(df["tick_volume"].astype(float) / 60.0)
    df["spread_z"] = _zscore(df["spread_bps"].astype(float))
    df["quote_revision_rate_z"] = _zscore(df["quote_revisions"].astype(float))

    brs = df["bar_return_sign"].astype(float)
    df["directional_persistence_8"] = brs.rolling(8, min_periods=4).sum().shift(1)
    df["signed_flow_24"] = brs.rolling(24, min_periods=8).sum().shift(1)

    abs_ret = df["vel_pips_h1"].abs()
    roll_abs = abs_ret.rolling(24, min_periods=8).mean().shift(1)
    df["vol_cluster_score"] = (abs_ret / roll_abs.replace(0, np.nan)).fillna(1.0)

    prev_close = close_bid.shift(1)
    df["slip_proxy_pips"] = (
        ((close_bid - prev_close).abs() / pip).rolling(24, min_periods=8).quantile(0.75).shift(1)
    )
    # velocity z at a few horizons (w-bar velocity, vol-normalised)
    for w in (1, 2, 5, 10):
        vw = (close_bid - close_bid.shift(w)) / pip
        df[f"vel_z_h{w}"] = _zscore(vw)
    return df


def _non_overlap_ic(signal: np.ndarray, fwd: np.ndarray, skip: int = 5) -> tuple[float, float, int]:
    s, f = signal[::skip], fwd[::skip]
    m = np.isfinite(s) & np.isfinite(f)
    s, f = s[m], f[m]
    if len(s) < 10 or np.std(s) == 0 or np.std(f) == 0:
        return (float("nan"), float("nan"), len(s))
    ic = float(np.corrcoef(s, f)[0, 1])
    t = ic * np.sqrt(len(s) - 2) / np.sqrt(max(1e-12, 1.0 - ic**2))
    return (ic, float(t), len(s))


def _empty_result(cost_frac: float, reason: str) -> dict[str, Any]:
    return {
        "n_obs": 0, "n_entries": 0, "entry_freq_per_day": 0.0,
        "gross_mean_bps": 0.0, "net_mean_bps": 0.0, "net_lb95_bps": 0.0,
        "gross_ic": 0.0, "ic_tstat": 0.0, "ic_n": 0,
        "decile_spread_bps": 0.0, "cost_bps": round(cost_frac * 10_000, 4),
        "verdict": "FAIL", "fail_reason": reason,
    }


def is_near_miss(metrics: dict, cost_frac: float) -> bool:
    """Near miss: just below cost AND a corroborating gross signal."""
    net_lb95 = metrics.get("net_lb95_bps", 0.0) / 10_000
    if not (0 > net_lb95 >= -cost_frac):
        return False
    return any([
        metrics.get("gross_ic", 0.0) > 0.03 and metrics.get("ic_tstat", 0.0) > 2.0,
        metrics.get("decile_spread_bps", 0.0) / 10_000 >= 2 * cost_frac,
        metrics.get("net_mean_bps", -1.0) > 0.0,
    ])


def evaluate_family(
    signal: pd.Series,
    fwd_ret: pd.Series,
    cost_frac: float,
    entry_quantile: float = 0.90,
) -> dict[str, Any]:
    """Evaluate a signal net of cost. Entry on the top-|z| tail; side = sign(z)."""
    s = pd.Series(np.asarray(signal, dtype=float)).reset_index(drop=True)
    f = pd.Series(np.asarray(fwd_ret, dtype=float)).reset_index(drop=True)
    valid = np.isfinite(s) & np.isfinite(f)
    s, f = s[valid], f[valid]
    if len(s) < 10:
        return _empty_result(cost_frac, reason="too few valid observations")

    z = (s - s.mean()) / (s.std(ddof=0) + 1e-12)
    thresh = z.abs().quantile(entry_quantile)
    entry = z.abs() >= thresh
    n = int(entry.sum())
    if n < 10:
        return _empty_result(cost_frac, reason="too few entries")

    side = np.sign(z[entry].to_numpy())
    gross = side * f[entry].to_numpy()
    net = gross - cost_frac
    mean_net = float(net.mean())
    se_net = float(net.std(ddof=1) / np.sqrt(n)) if n > 1 else float("inf")
    net_lb95 = mean_net - 1.645 * se_net

    ic, tstat, n_ic = _non_overlap_ic(s.to_numpy(), f.to_numpy(), skip=5)
    extreme = z.abs() >= z.abs().quantile(0.90)
    decile_gross = float((np.sign(z[extreme].to_numpy()) * f[extreme].to_numpy()).mean())

    res = {
        "n_obs": int(valid.sum()),
        "n_entries": n,
        "entry_freq_per_day": round(n / (len(s) / (24 * 60)), 2) if len(s) else 0.0,
        "gross_mean_bps": round(float(gross.mean()) * 10_000, 4),
        "net_mean_bps": round(mean_net * 10_000, 4),
        "net_lb95_bps": round(net_lb95 * 10_000, 4),
        "gross_ic": round(ic, 4) if np.isfinite(ic) else 0.0,
        "ic_tstat": round(tstat, 2) if np.isfinite(tstat) else 0.0,
        "ic_n": n_ic,
        "decile_spread_bps": round(decile_gross * 10_000, 4),
        "cost_bps": round(cost_frac * 10_000, 4),
    }
    res["verdict"] = (
        "PASS" if (net_lb95 > 0 and n >= 20)
        else "NEAR_MISS" if is_near_miss(res, cost_frac)
        else "FAIL"
    )
    return res
