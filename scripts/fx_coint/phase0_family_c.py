"""Phase 0 Family C: Temporal Lead-Lag via Peer Returns.

Hypothesis: lagged peer returns predict the target's next return during liquid hours.
Causal rolling ridge on peer returns at lags 1..max_lag; trades the fitted prediction.
"""

from __future__ import annotations

import argparse
import json
import sys as _sys
from pathlib import Path as _Path

import numpy as np
import pandas as pd

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

PEERS = ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCHF", "USDCAD"]


def _mid_ret(df: pd.DataFrame) -> pd.Series:
    if "mid_ret" in df.columns:
        return df["mid_ret"].astype(float)
    return np.log(df["mid"].astype(float) / df["mid"].astype(float).shift(1))


def build_peer_lag_signal(
    target_df: pd.DataFrame,
    peer_dfs: dict[str, pd.DataFrame],
    window: int = 50,
    max_lag: int = 3,
    lam: float = 1.0,
) -> pd.Series:
    """Causal rolling ridge: target mid_ret ~ peer mid_ret at lags 1..max_lag.

    The lag matrix is precomputed once (each column already shifted, so it only uses
    information available at decision time). For bar t we fit on rows [t-window, t) and
    predict row t.
    """
    target_sym = target_df.attrs.get("symbol", "")
    peers = [p for p in peer_dfs if p != target_sym]
    n = len(target_df)
    if not peers:
        return pd.Series(np.full(n, np.nan), index=target_df.index)

    # precompute lag matrix X (n, k) — column = peer return shifted by `lag` (causal)
    cols = []
    for peer in peers:
        pr = _mid_ret(peer_dfs[peer]).to_numpy()
        for lag in range(1, max_lag + 1):
            shifted = np.full(n, np.nan)
            if lag < n:
                shifted[lag:] = pr[:-lag] if len(pr) == n else np.nan
            cols.append(shifted)
    X = np.column_stack(cols) if cols else np.empty((n, 0))
    y = _mid_ret(target_df).to_numpy()

    k = X.shape[1]
    sig = np.full(n, np.nan)
    eye = lam * np.eye(k)
    for i in range(window + max_lag, n):
        Xi = X[i - window:i]
        yi = y[i - window:i]
        m = np.isfinite(Xi).all(axis=1) & np.isfinite(yi)
        if m.sum() < max(window // 2, k + 1) or not np.isfinite(X[i]).all():
            continue
        Xm, ym = Xi[m], yi[m]
        try:
            beta = np.linalg.solve(Xm.T @ Xm + eye, Xm.T @ ym)
        except np.linalg.LinAlgError:
            continue
        sig[i] = float(X[i] @ beta)
    return pd.Series(sig, index=target_df.index)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--target", default="EURUSD")
    p.add_argument("--year", type=int, default=2024)
    p.add_argument("--horizons", nargs="+", type=int, default=[1, 3, 5])
    p.add_argument("--window", type=int, default=50)
    p.add_argument("--max-lag", type=int, default=3)
    args = p.parse_args()

    target_sym = args.target.upper()
    peers = [s for s in PEERS if s != target_sym]
    cost_frac = DEFAULT_COST_BPS.get(target_sym, 0.80) / 10_000

    all_bars = {}
    for sym in [target_sym, *peers]:
        ticks = load_raw_ticks(sym, args.year)
        bars = build_enriched_1m_bars(ticks, sym)
        bars.attrs["symbol"] = sym
        all_bars[sym] = bars
        save_enriched_bars(bars, sym, "1m")

    target_df = add_rolling_features(all_bars[target_sym], target_sym)
    target_df.attrs["symbol"] = target_sym
    target_df = compute_forward_returns(target_df, args.horizons)

    # Align peers to the TARGET's 1-min bucket timeline (pairs have different per-minute
    # tick coverage -> different bar counts; without this every peer column is NaN).
    target_buckets = target_df["bucket"]
    peer_dfs = {}
    for s in peers:
        aligned = all_bars[s].set_index("bucket").reindex(target_buckets).reset_index()
        aligned["mid_ret"] = np.log(aligned["mid"].astype(float) / aligned["mid"].astype(float).shift(1))
        aligned.attrs["symbol"] = s
        peer_dfs[s] = aligned

    signal = build_peer_lag_signal(target_df, peer_dfs, window=args.window, max_lag=args.max_lag)
    signal = signal.where(target_df["vol_cluster_score"] > 1.0, np.nan)  # liquid-hours gate

    results = {}
    for h in args.horizons:
        col = f"fwd_ret_{h}"
        if col not in target_df.columns:
            continue
        r = evaluate_family(signal, target_df[col], cost_frac=cost_frac, entry_quantile=0.90)
        results[f"h{h}"] = r
        print(f"Family-C {target_sym} h={h}: {r['verdict']}  net_lb95={r['net_lb95_bps']:.4f}  n={r['n_entries']}")

    print(json.dumps({"family": "C", "symbol": target_sym, "year": args.year,
                      "horizons": args.horizons, "cost_bps": DEFAULT_COST_BPS.get(target_sym, 0.80),
                      "results": results}, indent=2))


if __name__ == "__main__":
    main()
