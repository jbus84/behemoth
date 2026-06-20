"""Phase 0 Family A: Tick-Scale Flow Orthogonalization.

Hypothesis: the component of flow uncorrelated to contemporaneous price returns
carries microstructure alpha at the 1-min scale.

Usage:
    uv run python scripts/fx_coint/phase0_family_a.py --symbol EURUSD --year 2024
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.fx_coint.phase0_scalp_common import (
    DEFAULT_COST_BPS,
    add_rolling_features,
    build_enriched_1m_bars,
    compute_forward_returns,
    evaluate_family,
    load_raw_ticks,
    save_enriched_bars,
)


def build_flow_residual_signal(df: pd.DataFrame, window: int = 5) -> pd.Series:
    """Causal rolling OLS: flow ~ a + b * mid_ret, fit on [t-window, t); residual at t."""
    df = df.copy()
    mid_ret = np.log(df["mid"].astype(float) / df["mid"].astype(float).shift(1))
    flow = df["flow_tick"].astype(float)
    n = len(df)
    resid = np.full(n, np.nan)
    mr = mid_ret.to_numpy()
    fl = flow.to_numpy()
    for i in range(window, n):
        x = mr[i - window:i]
        y = fl[i - window:i]
        m = np.isfinite(x) & np.isfinite(y)
        if m.sum() < 3 or not np.isfinite(mr[i]) or not np.isfinite(fl[i]):
            continue
        A = np.column_stack([np.ones(m.sum()), x[m]])
        try:
            beta = np.linalg.lstsq(A, y[m], rcond=None)[0]
        except np.linalg.LinAlgError:
            continue
        resid[i] = fl[i] - (beta[0] + beta[1] * mr[i])
    return pd.Series(resid, index=df.index)


def _load(sym: str, year: int, enriched: Path | None) -> pd.DataFrame:
    if enriched and enriched.exists():
        return pd.read_parquet(enriched)
    ticks = load_raw_ticks(sym, year)
    df = build_enriched_1m_bars(ticks, sym)
    save_enriched_bars(df, sym, "1m")
    return df


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="EURUSD")
    p.add_argument("--year", type=int, default=2024)
    p.add_argument("--horizons", nargs="+", type=int, default=[1, 3, 5, 10])
    p.add_argument("--window", type=int, default=5)
    p.add_argument("--enriched-parquet", type=Path, default=None)
    args = p.parse_args()

    sym = args.symbol.upper()
    cost_frac = DEFAULT_COST_BPS.get(sym, 0.80) / 10_000

    df = _load(sym, args.year, args.enriched_parquet)
    df = add_rolling_features(df, sym)
    df = compute_forward_returns(df, args.horizons)
    signal = build_flow_residual_signal(df, window=args.window)

    results = {}
    for h in args.horizons:
        col = f"fwd_ret_{h}"
        if col not in df.columns:
            continue
        r = evaluate_family(signal, df[col], cost_frac=cost_frac, entry_quantile=0.90)
        results[f"h{h}"] = r
        print(f"Family-A {sym} h={h}: {r['verdict']}  net_lb95={r['net_lb95_bps']:.4f}  n={r['n_entries']}")

    print(json.dumps({"family": "A", "symbol": sym, "year": args.year,
                      "horizons": args.horizons, "window": args.window,
                      "cost_bps": DEFAULT_COST_BPS.get(sym, 0.80), "results": results}, indent=2))


if __name__ == "__main__":
    main()
