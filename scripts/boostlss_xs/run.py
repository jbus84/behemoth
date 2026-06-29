"""End-to-end BoostLSS XS anomaly detection pipeline.

Usage:
    uv run python scripts/boostlss_xs/run.py \\
        --data-dir /path/to/tick_bars \\
        --output-dir /tmp/boostlss_xs_out \\
        [--families GaussianLSS GEVLSS] \\
        [--horizons 1 2 3 4 5] \\
        [--meta-threshold 0.55]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Ensure repo root is on sys.path when run as a script (uv run python scripts/…)
_REPO_ROOT = str(Path(__file__).parent.parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import numpy as np
import pandas as pd

from scripts.boostlss_xs.features import (
    ALL_FEATURES,
    build_features,
    within_symbol_features,
    xs_features,
)
from scripts.boostlss_xs.flagging import flag_channels
from scripts.boostlss_xs.meta_labeler import MetaLabeler
from scripts.boostlss_xs.model import BoostLssWFO
from scripts.boostlss_xs.universe import load_universe


def _extract_y_raw_per_symbol(universe: dict) -> dict[str, np.ndarray]:
    """Per-symbol vol_std arrays, same valid-row mask as build_features()."""
    result: dict[str, np.ndarray] = {}
    for sym in sorted(universe.keys()):
        df = universe[sym]
        mat = df.select(ALL_FEATURES).to_numpy()
        valid = ~np.any(np.isnan(mat), axis=1)
        result[sym] = df["vol_std"].to_numpy()[valid]
    return result


def _build_horizon_target_per_symbol(
    y_raw_per_sym: dict[str, np.ndarray], horizon: int
) -> np.ndarray:
    """Build forward-sum target per symbol (no cross-symbol bleed), then concat in sorted(keys) order."""
    parts: list[np.ndarray] = []
    for sym in sorted(y_raw_per_sym.keys()):
        y = y_raw_per_sym[sym]
        out = np.full(len(y), np.nan)
        for i in range(len(y) - horizon):
            window = y[i + 1 : i + 1 + horizon]
            if not np.isnan(window).any():
                out[i] = float(np.sum(window))
        parts.append(out)
    return np.concatenate(parts)  # symbol-sorted; caller applies sort_idx


def run_pipeline(
    data_dir: str,
    output_dir: str,
    families: list[str] | None = None,
    horizons: list[int] | None = None,
    meta_threshold: float = 0.55,
) -> None:
    """Run the full BoostLSS XS anomaly pipeline and write trade logs."""
    families = families or ["GaussianLSS", "GEVLSS"]
    horizons = horizons or [1, 2, 3, 4, 5]
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    print("Loading universe...")
    uni = load_universe(data_dir)
    print(f"  {len(uni)} symbols loaded")

    print("Computing within-symbol features...")
    uni = {sym: within_symbol_features(df, sym) for sym, df in uni.items()}

    print("Computing cross-sectional features...")
    uni = xs_features(uni)

    print("Building stacked feature matrix...")
    X, close_ts_arr, feature_names, symbols_arr, sort_idx = build_features(uni)
    print(f"  Feature matrix: {X.shape}")

    print("Building horizon targets...")
    y_raw_per_sym = _extract_y_raw_per_symbol(uni)
    y_by_horizon: dict[int, np.ndarray] = {
        h: _build_horizon_target_per_symbol(y_raw_per_sym, h)[sort_idx]
        for h in horizons
    }

    comparison_rows: list[dict] = []

    for family in families:
        print(f"\n=== Family: {family} ===")
        all_flags: dict[int, dict[str, np.ndarray]] = {}

        for horizon in horizons:
            print(f"  Horizon N={horizon}...")
            y = y_by_horizon[horizon]
            wfo = BoostLssWFO(family=family)
            preds = wfo.fit_predict(X, y, close_ts_arr, embargo=max(horizons))
            flags = flag_channels(
                preds,
                y,
                family,
                mu_threshold=preds.get("mu_threshold_per_row"),
                sigma_threshold=preds.get("sigma_threshold_per_row"),
            )
            all_flags[horizon] = flags

        print("  Running meta-labeler...")
        ml = MetaLabeler(threshold=meta_threshold)
        # direction is consistent across horizons — take from horizon 1
        direction = all_flags[min(horizons)]["direction"]
        meta_probs = ml.fit_predict(
            flags_by_horizon=all_flags,
            y_by_horizon=y_by_horizon,
            direction=direction,
            symbols_arr=list(symbols_arr),
            close_ts_arr=close_ts_arr,
        )

        print("  Building trade log...")
        rows: list[dict] = []
        for i in range(len(X)):
            if np.isnan(meta_probs[i]) or meta_probs[i] < meta_threshold:
                continue
            for h in horizons:
                f = all_flags[h]
                if np.isnan(f["mu_flag"][i]):
                    continue
                rows.append(
                    {
                        "symbol": symbols_arr[i],
                        "close_ts": close_ts_arr[i],
                        "horizon": h,
                        "direction": float(direction[i]),
                        "meta_prob": float(meta_probs[i]),
                        "gross_return": (
                            float(y_by_horizon[h][i])
                            if not np.isnan(y_by_horizon[h][i])
                            else np.nan
                        ),
                        "mu_flag": float(f["mu_flag"][i]),
                        "sigma_flag": float(f["sigma_flag"][i]),
                        "nu_flag": float(f["nu_flag"][i]),
                        "mu_mag": float(f["mu_mag"][i]),
                        "sigma_mag": float(f["sigma_mag"][i]),
                        "nu_mag": float(f["nu_mag"][i]),
                    }
                )

        trade_log = pd.DataFrame(rows)
        out_path = os.path.join(output_dir, f"trade_log_{family}.csv")
        trade_log.to_csv(out_path, index=False)
        print(f"  Trade log: {len(trade_log)} rows → {out_path}")

        if len(trade_log) > 0:
            signed_ret = trade_log["gross_return"] * trade_log["direction"]
            comparison_rows.append(
                {
                    "family": family,
                    "n_trades": len(trade_log),
                    "mean_net_ret_bps": float(signed_ret.mean()),
                    "pos_frac": float((signed_ret > 0).mean()),
                    "mu_flag_rate": float(trade_log["mu_flag"].mean()),
                    "sigma_flag_rate": float(trade_log["sigma_flag"].mean()),
                    "nu_flag_rate": float(trade_log["nu_flag"].mean()),
                }
            )

    if comparison_rows:
        comp = pd.DataFrame(comparison_rows)
        comp_path = os.path.join(output_dir, "family_comparison.csv")
        comp.to_csv(comp_path, index=False)
        print(f"\nComparison summary → {comp_path}")
        print(comp.to_string(index=False))


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="BoostLSS XS anomaly detection pipeline")
    p.add_argument(
        "--data-dir",
        default="/Users/danielfisher/repositories/behemoth/data/tick_bars",
    )
    p.add_argument("--output-dir", default="/tmp/boostlss_xs_out")
    p.add_argument("--families", nargs="+", default=["GaussianLSS", "GEVLSS"])
    p.add_argument("--horizons", nargs="+", type=int, default=[1, 2, 3, 4, 5])
    p.add_argument("--meta-threshold", type=float, default=0.55)
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run_pipeline(
        data_dir=args.data_dir,
        output_dir=args.output_dir,
        families=args.families,
        horizons=args.horizons,
        meta_threshold=args.meta_threshold,
    )
