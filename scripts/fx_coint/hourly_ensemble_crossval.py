"""Window-clean labeling + ensemble + cross-symbol validation.

1. Window-aware labels: triple barrier labels computed only within each window's data.
2. Ensemble: bag predictions across N random seeds, majority vote.
3. Cross-symbol: test on GBPUSD 2024 (different volatility, different cost).

Usage:
    uv run python scripts/fx_coint/hourly_ensemble_crossval.py
"""
# ruff: noqa: E402

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from aeon.classification.convolution_based import MultiRocketHydraClassifier

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.fx_coint.hourly_multirocket_wfo import (
    DEFAULT_COST_BPS,
    build_feature_panel,
    classify_regime,
    load_hourly,
    simulate_trades,
)
from scripts.fx_coint.hourly_triple_barrier import label_hourly

EXCLUDE = set([
    "flow_tick",
    "flow_ofi",
    "rvol_bps",
    "spread_bps",
    "hour_sin",
    "hour_cos",
    "dow_sin",
    "dow_cos",
])

LOOKBACK = 24
TRAIN_MO = 6
TEST_MO = 1
BARRIER_BPS = 10.0
HORIZON = 12
N_SEEDS = 5


def window_aware_label(df: pd.DataFrame, symbol: str, barrier_bps: float, horizon: int) -> pd.DataFrame:
    """Label the full DataFrame using only its own data (no leakage)."""
    df_pl = pl.from_pandas(df)
    df_pl = label_hourly(df_pl, symbol, barrier_bps=barrier_bps, horizon=horizon)
    return df_pl.to_pandas()


def run_window(
    df: pd.DataFrame,
    symbol: str,
    train_start: pd.Timestamp,
    train_end: pd.Timestamp,
    test_start: pd.Timestamp,
    test_end: pd.Timestamp,
    seeds: list[int],
) -> dict:
    """Run one WFO window with window-aware labels and ensemble."""
    # Slice data for this window + lookback margin
    margin_start = train_start - pd.Timedelta(hours=LOOKBACK * 2)
    window_df = df[(df["bucket"] >= margin_start) & (df["bucket"] < test_end)].copy().reset_index(drop=True)

    # Compute labels using ONLY this window's data
    window_df = window_aware_label(window_df, symbol, BARRIER_BPS, HORIZON)

    # Align indices after lookback offset
    timestamps = window_df["bucket"].iloc[LOOKBACK:].reset_index(drop=True)
    train_mask = (timestamps >= train_start) & (timestamps < train_end)
    test_mask = (timestamps >= test_start) & (timestamps < test_end)
    train_idx = np.where(train_mask.to_numpy())[0]
    test_idx = np.where(test_mask.to_numpy())[0]

    if len(train_idx) < 500 or len(test_idx) < 100:
        return {}

    window_df["regime"] = classify_regime(window_df["rvol_bps"], train_idx)
    X, y, regime = build_feature_panel(window_df, LOOKBACK, exclude_channels=EXCLUDE)
    regime_test = regime.iloc[test_idx].to_numpy()

    X_train, y_train = X[train_idx], y[train_idx]
    X_test, y_test = X[test_idx], y[test_idx]

    if np.unique(y_train).size < 2 or np.unique(y_test).size < 2:
        return {}

    # Ensemble across seeds
    votes = np.zeros((len(seeds), len(y_test)), dtype=np.int8)
    for s_idx, seed in enumerate(seeds):
        clf = MultiRocketHydraClassifier(n_jobs=1, random_state=seed)
        clf.fit(X_train, y_train)
        votes[s_idx] = clf.predict(X_test)

    # Majority vote (break ties toward 0)
    counts_pos = (votes == 1).sum(axis=0)
    counts_neg = (votes == -1).sum(axis=0)
    preds = np.zeros(len(y_test), dtype=np.int8)
    preds[counts_pos > counts_neg] = 1
    preds[counts_neg > counts_pos] = -1

    acc = float((preds == y_test).mean())
    base_df = window_df.iloc[LOOKBACK:].reset_index(drop=True)
    test_df = base_df.iloc[test_idx].copy().reset_index(drop=True)
    cost_bps = DEFAULT_COST_BPS[symbol]
    sim = simulate_trades(test_df, preds, cost_bps, regime_gate=regime_test)

    return {
        "sharpe": sim["net_sharpe"],
        "acc": acc,
        "pos_pct": sim["positive_pct"],
        "n_trades": sim["n_trades"],
        "skipped": sim["skipped"],
        "n_seeds": len(seeds),
        "label_balance": {
            "train_pos": int((y_train == 1).sum()),
            "train_neg": int((y_train == -1).sum()),
            "train_zero": int((y_train == 0).sum()),
            "test_pos": int((y_test == 1).sum()),
            "test_neg": int((y_test == -1).sum()),
            "test_zero": int((y_test == 0).sum()),
        },
    }


def run_symbol(symbol: str, year: int, seeds: list[int]) -> list[dict]:
    print(f"\n{'=' * 70}")
    print(f"SYMBOL={symbol}  YEAR={year}  SEEDS={seeds}")
    print("=" * 70)

    df = load_hourly(symbol)
    start = pd.Timestamp(f"{year}-01-01")
    end = pd.Timestamp(f"{year + 1}-01-01")
    mask = (df["bucket"] >= start) & (df["bucket"] < end)
    df = df[mask].copy().reset_index(drop=True)

    months = pd.date_range(start, end, freq="MS")
    n_windows = len(months) - TRAIN_MO - TEST_MO

    results = []
    for i in range(n_windows):
        train_start = months[i]
        train_end = months[i + TRAIN_MO]
        test_start = months[i + TRAIN_MO]
        test_end = months[i + TRAIN_MO + TEST_MO] if (i + TRAIN_MO + TEST_MO) < len(months) else end

        r = run_window(df, symbol, train_start, train_end, test_start, test_end, seeds)
        if not r:
            print(f"  Window {i + 1}: skipped (insufficient data)")
            continue

        results.append(r)
        print(
            f"  Window {i + 1}: Sharpe={r['sharpe']: .3f}  "
            f"Acc={r['acc']:.3f}  Pos={r['pos_pct']:.1f}%  "
            f"Trades={r['n_trades']}  Skipped={r['skipped']}"
        )

    if results:
        sherpes = [r["sharpe"] for r in results]
        accs = [r["acc"] for r in results]
        pos_pcts = [r["pos_pct"] for r in results]
        print("-" * 70)
        print(
            f"AVG  Sharpe={np.mean(sherpes): .3f}  Acc={np.mean(accs):.3f}  "
            f"Pos={np.mean(pos_pcts):.1f}%  (N={len(results)} windows)"
        )

    return results


def main():
    # Good seeds from stability test
    seeds = [7, 13, 42, 99, 777]

    # 1. EURUSD 2024 window-clean ensemble
    eur_results = run_symbol("EURUSD", 2024, seeds)

    # 2. GBPUSD 2024 cross-symbol
    gbp_results = run_symbol("GBPUSD", 2024, seeds)

    # 3. EURUSD 2023 out-of-year
    eur23_results = run_symbol("EURUSD", 2023, seeds)

    print("\n" + "=" * 70)
    print("FINAL SUMMARY")
    print("=" * 70)
    for name, results in [
        ("EURUSD 2024", eur_results),
        ("GBPUSD 2024", gbp_results),
        ("EURUSD 2023", eur23_results),
    ]:
        if results:
            sherpes = [r["sharpe"] for r in results]
            print(f"{name:<15s}  AvgSharpe={np.mean(sherpes): .3f}  Std={np.std(sherpes):.3f}  Median={np.median(sherpes): .3f}  N={len(results)}")
        else:
            print(f"{name:<15s}  NO VALID WINDOWS")


if __name__ == "__main__":
    main()
