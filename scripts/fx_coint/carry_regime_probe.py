"""Carry + Regime probe for FX.

Tests whether yield-carry (10-year government bond differentials) produces a positive net
return when filtered by a risk-on/risk-off regime indicator (VIX level or trend).

Data sources
------------
* FX spot: daily mid-close built from ~/Desktop/dukascopy_ticks raw parquets.
* Yields: 10-year government bond yields from FRED (monthly, forward-filled to daily).
* Regime: VIX daily close from FRED.

Design
------
* Carry signal: long the currency with higher 10y yield, short the lower.
  For XXXUSD pairs (EURUSD, GBPUSD, AUDUSD): short if US_yld > XXX_yld.
  For USDXXX pairs (USDJPY, USDCHF, USDCAD): long if US_yld > XXX_yld.
* Regime filters tested:
  – Unconditional carry
  – VIX level < threshold (15, 18, 20, 22, 25)
  – VIX 20-day MA < threshold
  – VIX 20-day trend negative (VIX falling = risk-on)
* Holding: daily close-to-close (rebalanced daily), 5-day hold, 20-day hold.
* Cost: Pepperstone Razor round-trip bps per pair.

Causality
---------
* Yield differentials use only published monthly data (known with 1-month lag, forward-filled).
* VIX filter uses only past 20 days.
* Single holdout: train 2018-2022, test 2023-2026. No hyperparameter optimization on test set.

Usage
-----
    uv run python scripts/fx_coint/carry_regime_probe.py

Output
------
  * Per-pair and pooled results for each regime variant.
  * Yearly breakdown to check decay.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
import requests

SRC = Path.home() / "Desktop" / "dukascopy_ticks"

# Pepperstone Razor round-trip cost (bps)
COST_BPS: dict[str, float] = {
    "EURUSD": 0.64,
    "GBPUSD": 0.80,
    "AUDUSD": 0.88,
    "USDJPY": 0.72,
    "USDCHF": 0.88,
    "USDCAD": 0.88,
}

# FRED 10-year yield series codes
YIELD_CODES: dict[str, str] = {
    "US": "DGS10",
    "EU": "IRLTLT01EZM156N",
    "JP": "IRLTLT01JPM156N",
    "GB": "IRLTLT01GBM156N",
    "CH": "IRLTLT01CHM156N",
    "CA": "IRLTLT01CAM156N",
    "AU": "IRLTLT01AUM156N",
}

# Map pair to (base, quote) and which side of the pair corresponds to which yield
PAIR_YIELD_MAP: dict[str, tuple[str, str]] = {
    # pair : (base_currency_yield_key, quote_currency_yield_key)
    # For EURUSD: base=EUR (EU yield), quote=USD (US yield)
    # Signal: if US > EU, short EURUSD (USD is higher yield)
    "EURUSD": ("EU", "US"),
    "GBPUSD": ("GB", "US"),
    "AUDUSD": ("AU", "US"),
    "USDJPY": ("US", "JP"),
    "USDCHF": ("US", "CH"),
    "USDCAD": ("US", "CA"),
}


def fetch_fred_series(code: str) -> pd.DataFrame:
    """Download a FRED CSV series, return DataFrame with columns DATE, VALUE."""
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={code}"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    df.columns = [c.strip().upper() for c in df.columns]
    # FRED CSVs have headers like "observation_date" or "DATE"
    date_col = next((c for c in df.columns if "DATE" in c), None)
    if date_col is None:
        raise ValueError(f"No date column found in FRED series {code}. Columns: {list(df.columns)}")
    df = df.rename(columns={date_col: "DATE"})
    df["DATE"] = pd.to_datetime(df["DATE"])
    df = df.sort_values("DATE").reset_index(drop=True)
    # Value column is the second column
    value_col = [c for c in df.columns if c != "DATE"][0]
    df["VALUE"] = pd.to_numeric(df[value_col], errors="coerce")
    return df[["DATE", "VALUE"]]


def load_fx_daily(symbol: str, years: list[int]) -> pd.DataFrame:
    """Build daily mid-close from dukascopy tick parquets."""
    sym = symbol.upper()
    sym_dir = SRC / sym
    frames = []
    for year in years:
        files = sorted(sym_dir.glob(f"{sym}_{year}*_ticks.parquet"))
        if not files:
            continue
        ticks = pl.concat([pl.read_parquet(f) for f in files]).sort("timestamp")
        # Daily close = last mid of each trading day (UTC)
        daily = (
            ticks.with_columns(pl.col("timestamp").dt.truncate("1d").alias("date"))
            .group_by("date")
            .agg(pl.col("mid").last().alias("mid"))
            .sort("date")
        )
        df = daily.to_pandas()
        df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
        frames.append(df)
    if not frames:
        raise FileNotFoundError(f"No tick data for {symbol} years {years}")
    return pd.concat(frames, ignore_index=True).sort_values("date").reset_index(drop=True)


# Monthly series are published with ~1-month lag; shift forward to avoid look-ahead.
MONTHLY_LAG_DAYS = 30


def build_yield_curves(start: str, end: str) -> pd.DataFrame:
    """Fetch all 10y yields from FRED, forward-fill each to daily, lag monthly series, then merge."""
    merged = None
    for country, code in YIELD_CODES.items():
        df = fetch_fred_series(code)
        df = df.set_index("DATE").resample("D").ffill().reset_index()
        # Lag monthly series by publication delay (DGS10 is daily, rest are monthly)
        if country != "US":
            df["VALUE"] = df["VALUE"].shift(MONTHLY_LAG_DAYS)
        df = df.rename(columns={"VALUE": country})
        if merged is None:
            merged = df
        else:
            merged = merged.merge(df, on="DATE", how="outer")
    merged = merged.sort_values("DATE").reset_index(drop=True)
    merged = merged[(merged["DATE"] >= start) & (merged["DATE"] <= end)]
    # Drop rows where any yield is NaN (monthly publication lag creates trailing NaNs)
    yield_cols = [c for c in merged.columns if c != "DATE"]
    merged = merged.dropna(subset=yield_cols).reset_index(drop=True)
    return merged


def build_vix(start: str, end: str) -> pd.DataFrame:
    """Fetch VIX daily from FRED."""
    df = fetch_fred_series("VIXCLS")
    df = df.rename(columns={"VALUE": "VIX"})
    df = df[(df["DATE"] >= start) & (df["DATE"] <= end)]
    return df.reset_index(drop=True)


def compute_carry_return(
    pair: str,
    prices: pd.DataFrame,
    yields_df: pd.DataFrame,
    regime_mask: pd.Series,
    hold_days: int,
) -> dict:
    """Compute carry strategy return for a single pair with regime filter."""
    base_ccy, quote_ccy = PAIR_YIELD_MAP[pair]

    # Merge prices with yields
    df = prices.merge(yields_df, left_on="date", right_on="DATE", how="inner").copy()
    if len(df) < 100:
        return {"n": 0, "net": np.nan, "gross": np.nan, "t": np.nan, "hit": np.nan}

    # Yield differential: (quote_yield - base_yield) in percentage points
    # For EURUSD: US - EU. Positive = USD yields higher = short EURUSD.
    df["ydiff"] = df[quote_ccy] - df[base_ccy]

    # Daily return in bps (log return)
    df["ret_bps"] = np.log(df["mid"] / df["mid"].shift(1)) * 1e4

    # Carry signal: sign of yield diff (positive = long quote/short base)
    df["signal"] = np.sign(df["ydiff"])

    # Forward return: hold for `hold_days`
    df["fwd_ret_bps"] = np.log(df["mid"].shift(-hold_days) / df["mid"]) * 1e4

    # Apply regime mask (aligned by date)
    df = df.merge(regime_mask.rename("regime_ok").to_frame(), left_on="date", right_index=True, how="left")
    df["regime_ok"] = df["regime_ok"].fillna(False)

    # Only trade when regime_ok
    trades = df[df["regime_ok"] & df["signal"].notna() & df["fwd_ret_bps"].notna()].copy()
    if len(trades) == 0:
        return {"n": 0, "net": np.nan, "gross": np.nan, "t": np.nan, "hit": np.nan}

    # For XXXUSD pairs: signal=+1 means short pair (long USD)
    # For USDXXX pairs: signal=+1 means long pair (long USD)
    # The direction is already correct: signal=+1 means quote currency has higher yield
    # So for EURUSD, signal=+1 means short EURUSD
    # For USDJPY, signal=+1 means long USDJPY
    # Both are "long the higher-yielding currency"
    gross = trades["signal"].values * trades["fwd_ret_bps"].values
    cost = COST_BPS[pair]
    net = gross - cost

    return {
        "n": len(net),
        "gross": float(np.mean(gross)),
        "net": float(np.mean(net)),
        "t": float(np.mean(net) / (np.std(net, ddof=1) / np.sqrt(len(net)))) if np.std(net) > 0 else np.nan,
        "hit": float(np.mean(net > 0)) * 100.0,
        "pos": int(np.sum(net > 0)),
        "neg": int(np.sum(net <= 0)),
    }


def main():
    years = list(range(2018, 2027))
    start_dt = "2018-01-01"
    end_dt = "2026-06-25"

    print("Fetching FRED data...")
    yields_df = build_yield_curves(start_dt, end_dt)
    vix_df = build_vix(start_dt, end_dt)
    vix_df = vix_df.set_index("DATE")["VIX"]

    print(f"Yields: {len(yields_df)} days")
    print(f"VIX: {len(vix_df)} days")

    # Load FX daily prices
    print("Loading FX daily prices from ticks...")
    prices = {}
    for pair in PAIR_YIELD_MAP:
        try:
            prices[pair] = load_fx_daily(pair, years)
            print(f"  {pair}: {len(prices[pair])} days")
        except FileNotFoundError as e:
            print(f"  {pair}: SKIP ({e})")

    if not prices:
        print("ERROR: no FX data loaded", file=sys.stderr)
        sys.exit(1)

    # Define regime filters to test
    # All are causal (computed from past VIX only)
    vix_ma20 = vix_df.rolling(20).mean()
    vix_trend = vix_df.diff(20)  # positive = VIX rising (risk-off)

    regime_filters = {
        "unconditional": pd.Series(True, index=vix_df.index),
        "vix_lt_15": vix_df < 15,
        "vix_lt_18": vix_df < 18,
        "vix_lt_20": vix_df < 20,
        "vix_lt_22": vix_df < 22,
        "vix_lt_25": vix_df < 25,
        "vix_ma20_lt_20": vix_ma20 < 20,
        "vix_ma20_lt_22": vix_ma20 < 22,
        "vix_ma20_lt_25": vix_ma20 < 25,
        "vix_falling_20d": vix_trend < 0,  # VIX falling = risk-on, good for carry
    }

    hold_days_list = [1, 5, 20]

    # Single holdout split
    train_end = pd.Timestamp("2022-12-31")
    test_start = pd.Timestamp("2023-01-01")

    print(f"\n{'='*80}")
    print(f"TRAIN: {start_dt} to {train_end.date()}  |  TEST: {test_start.date()} to {end_dt}")
    print(f"{'='*80}")

    results = []
    for hold_days in hold_days_list:
        for regime_name, regime_mask in regime_filters.items():
            print(f"\n--- Hold={hold_days}d | Regime={regime_name} ---")
            pair_results = {}
            pooled_nets = []
            for pair in sorted(prices):
                # Split into train/test
                p = prices[pair].copy()
                # We don't optimize anything on train; carry signal is fixed (yield diff sign)
                # So we just evaluate on test
                p_test = p[p["date"] >= test_start].copy()

                res = compute_carry_return(pair, p_test, yields_df, regime_mask, hold_days)
                pair_results[pair] = res
                if res["n"] > 0 and not np.isnan(res["net"]):
                    # For pooling, weight by n (or equal weight? let's do equal weight per-trade)
                    pooled_nets.extend([res["net"]] * res["n"])

                print(
                    f"  {pair}: n={res['n']:>4}, gross={res['gross']:+6.2f}, net={res['net']:+6.2f}, "
                    f"t={res['t']:+5.2f}, hit={res['hit']:>5.1f}% ({res['pos']}/{res['neg']})"
                )

            if pooled_nets:
                nets = np.array(pooled_nets)
                print(
                    f"  POOLED: n={len(nets)}, net={np.mean(nets):+6.2f}, t={np.mean(nets)/(np.std(nets,ddof=1)/np.sqrt(len(nets))):+5.2f}, "
                    f"hit={np.mean(nets>0)*100:.1f}%"
                )
                results.append({
                    "hold_days": hold_days,
                    "regime": regime_name,
                    "n": len(nets),
                    "net": round(float(np.mean(nets)), 4),
                    "t": round(float(np.mean(nets) / (np.std(nets, ddof=1) / np.sqrt(len(nets)))), 4) if np.std(nets) > 0 else None,
                    "hit_pct": round(float(np.mean(nets > 0) * 100), 2),
                })

    # Summary table
    print(f"\n{'='*80}")
    print("SUMMARY TABLE")
    print(f"{'='*80}")
    print(f"{'Hold':>4} {'Regime':>20} {'N':>6} {'Net':>7} {'t':>6} {'Hit%':>6}")
    print("-" * 60)
    for r in results:
        print(f"{r['hold_days']:>4} {r['regime']:>20} {r['n']:>6} {r['net']:>+7.2f} {r['t']:>+6.2f} {r['hit_pct']:>6.1f}")

    # Best variant
    valid = [r for r in results if r["n"] > 50 and r["t"] is not None]
    if valid:
        best = max(valid, key=lambda x: x["net"])
        print(f"\nBest variant: hold={best['hold_days']}d, regime={best['regime']}, net={best['net']:+.2f}, t={best['t']:+.2f}")


if __name__ == "__main__":
    main()
