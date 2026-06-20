"""Phase 0 Family D: Microstructure Cocktail (RidgeClassifier on enriched features).

Hypothesis: a linear combination of untapped microstructure columns beats cost at the tail.
Expanding-block walk-forward (time-ordered) avoids look-ahead; the classifier's signed
decision_function is the signal strength.
"""

from __future__ import annotations

import argparse
import json
import sys as _sys
from pathlib import Path
from pathlib import Path as _Path

import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeClassifierCV

_ROOT = _Path(__file__).resolve().parents[2]
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))

from scripts.fx_coint.phase0_scalp_common import (  # noqa: E402
    DEFAULT_COST_BPS,
    add_rolling_features,
    build_enriched_1m_bars,
    compute_forward_returns,
    evaluate_family,
    load_raw_ticks,
    save_enriched_bars,
)

FEATURE_COLS = [
    "spread_bps", "spread_z", "tick_volume", "tick_rate_z",
    "bar_return_sign", "vel_pips_h1", "vel_z_h1", "vel_z_h2",
    "accel_pips", "hour_utc", "range_pips",
    "signed_flow_24", "directional_persistence_8",
    "quote_revision_rate_z", "vol_cluster_score", "slip_proxy_pips",
    "flow_tick", "flow_ofi",
]


def build_microstructure_classifier(
    features: pd.DataFrame, target: np.ndarray, horizon: int = 1, n_blocks: int = 6
) -> pd.Series:
    """Expanding-block walk-forward RidgeClassifier; returns signed decision_function.

    Time-ordered blocks: for block b in 1..n_blocks-1, train on [0, b*bs), predict
    [b*bs, (b+1)*bs). Strictly causal (train precedes test)."""
    cols = [c for c in FEATURE_COLS if c in features.columns]
    n = len(features)
    out = np.full(n, np.nan)
    if not cols or n < 2 * n_blocks:
        return pd.Series(out, index=features.index)

    X = features[cols].to_numpy(dtype=float)
    X = np.nan_to_num(X, nan=0.0)
    # strict binary labels {-1,+1}: real 1-min fwd returns include exact zeros, which
    # would create a 3rd class and make decision_function 2-D.
    y = np.where(np.asarray(target, dtype=float) > 0, 1.0, -1.0)
    bs = n // n_blocks
    for b in range(1, n_blocks):
        tr = slice(0, b * bs)
        te = slice(b * bs, (b + 1) * bs if b < n_blocks - 1 else n)
        ytr = y[tr]
        if len(np.unique(ytr[np.isfinite(ytr)])) < 2 or te.start >= n:
            continue
        try:
            clf = RidgeClassifierCV(alphas=(0.1, 1.0, 10.0, 100.0), class_weight="balanced")
            clf.fit(X[tr], ytr)
            out[te] = clf.decision_function(X[te])
        except (ValueError, np.linalg.LinAlgError):
            continue
    return pd.Series(out, index=features.index)


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

    results = {}
    for h in args.horizons:
        col = f"fwd_ret_{h}"
        if col not in df.columns:
            continue
        signal = build_microstructure_classifier(df, np.sign(df[col].to_numpy()), horizon=h)
        r = evaluate_family(signal, df[col], cost_frac=cost_frac, entry_quantile=0.90)
        results[f"h{h}"] = r
        print(f"Family-D {sym} h={h}: {r['verdict']}  net_lb95={r['net_lb95_bps']:.4f}  n={r['n_entries']}")

    print(json.dumps({"family": "D", "symbol": sym, "year": args.year,
                      "horizons": args.horizons, "cost_bps": DEFAULT_COST_BPS.get(sym, 0.80),
                      "results": results}, indent=2))


if __name__ == "__main__":
    main()
