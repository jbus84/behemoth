"""Phase 0 Family B: Quote-Revision Continuation.

Hypothesis: elevated quote-revision rate combined with directional persistence
indicates informed flow and predicts continuation.

Signal = quote_revision_rate_z * sign(directional_persistence_8), gated on
quote_revision_rate_z > 1.0 AND persistence above its expanding median.
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


def build_quote_revision_signal(df: pd.DataFrame) -> pd.Series:
    qr = df["quote_revision_rate_z"].astype(float)
    dp = df["directional_persistence_8"].astype(float)
    dp_median = dp.expanding(min_periods=8).median().shift(1)
    signal = qr * np.sign(dp)
    gate = (qr > 1.0) & (dp > dp_median)
    return signal.where(gate, np.nan)


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
    p.add_argument("--horizons", nargs="+", type=int, default=[1, 3, 5])
    p.add_argument("--enriched-parquet", type=Path, default=None)
    args = p.parse_args()

    sym = args.symbol.upper()
    cost_frac = DEFAULT_COST_BPS.get(sym, 0.80) / 10_000

    df = _load(sym, args.year, args.enriched_parquet)
    df = add_rolling_features(df, sym)
    df = compute_forward_returns(df, args.horizons)
    signal = build_quote_revision_signal(df)

    results = {}
    for h in args.horizons:
        col = f"fwd_ret_{h}"
        if col not in df.columns:
            continue
        r = evaluate_family(signal, df[col], cost_frac=cost_frac, entry_quantile=0.90)
        results[f"h{h}"] = r
        print(f"Family-B {sym} h={h}: {r['verdict']}  net_lb95={r['net_lb95_bps']:.4f}  n={r['n_entries']}")

    print(json.dumps({"family": "B", "symbol": sym, "year": args.year,
                      "horizons": args.horizons, "cost_bps": DEFAULT_COST_BPS.get(sym, 0.80),
                      "results": results}, indent=2))


if __name__ == "__main__":
    main()
