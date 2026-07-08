"""Meta-model v2: reflects the current best understanding after the 2026-07-07
real-tick-execution investigation, not the original 11-pair "hardened core" (which
collapsed to essentially EURUSD alone once real execution mechanics were tested --
see project_fx_idiosyncratic_jump_fade memory for the full history).

Key differences from jumpfade_metamodel.py (v1):
  - Uses the consolidated, validated jumpfade_dataset_loader (real per-event tick
    costs, not a flat per-pair assumption; bug-free leg decomposition)
  - Includes session_q (0-3, 6h UTC quarters) as a feature -- the session2 x
    top-z-tercile interaction was found to carry real signal that a model without
    this feature could not discover on its own
  - Uses the expanded population (z>1.5, not a hard z>4 gate) so the model can find
    the magnitude threshold itself rather than have it imposed
  - Focused on EURUSD by default (the one pair confirmed to survive end to end);
    pass other symbols to test them, understanding they may not carry a real edge
    (GBPUSD's plain rule is cost-sensitive; every cross tested failed on rollover-
    hour liquidity contamination)

Point tick_root at ~/Desktop/tick_icmarkets (once populated via
scripts/download_mt5_ticks.py) to re-run this against real IC Markets spread data
instead of the HistData archive -- one flag, no other changes.
"""

from __future__ import annotations

import argparse

import numpy as np
import polars as pl
from catboost import CatBoostClassifier

from scripts.fx_coint.jumpfade_dataset_loader import build_expanded_realtick_dataset

FEATURE_COLS = ["abs_z", "idio_share", "diurnal_scale", "session_q", "hh"]


def walk_forward(df: pl.DataFrame, p_threshold: float = 0.5) -> None:
    years = sorted(df["year"].unique().to_list())
    test_years = years[3:]  # 3yr minimum training burn-in, matches v1 convention

    all_unf, all_filt = [], []
    print("\n-- purged expanding-window walk-forward --")
    for test_y in test_years:
        train = df.filter(pl.col("year") < test_y)
        test = df.filter(pl.col("year") == test_y)
        if train.height < 500 or test.height < 50:
            continue
        X_train = train.select(FEATURE_COLS).to_pandas()
        y_train = train["win"].to_numpy().astype(int)
        X_test = test.select(FEATURE_COLS).to_pandas()

        model = CatBoostClassifier(iterations=200, depth=4, learning_rate=0.05, verbose=False, random_seed=42)
        model.fit(X_train, y_train)
        p_win = model.predict_proba(X_test)[:, 1]

        net_all = test["net_bps"].to_numpy()
        net_filt = net_all[p_win > p_threshold]
        all_unf.append(net_all)
        all_filt.append(net_filt)
        print(f"  {test_y}  unf n={len(net_all):5d} net={net_all.mean():+.3f}  |  "
              f"filt n={len(net_filt):5d} ({100*len(net_filt)/max(len(net_all),1):.0f}%) "
              f"net={net_filt.mean() if len(net_filt) else float('nan'):+.3f}")

    u = np.concatenate(all_unf)
    f = np.concatenate([a for a in all_filt if len(a)])
    tu = u.mean() / (u.std() / np.sqrt(len(u)))
    tf = f.mean() / (f.std() / np.sqrt(len(f))) if len(f) else float("nan")
    print(f"\nTOTAL: unfiltered n={len(u)} net={u.mean():+.3f} t={tu:+.2f}  |  "
          f"filtered n={len(f)} net={f.mean():+.3f} t={tf:+.2f}")
    print("\nfeature importance (last fold):")
    for name, imp in sorted(zip(FEATURE_COLS, model.get_feature_importance()), key=lambda x: -x[1]):
        print(f"  {name:14s} {imp:6.2f}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="EURUSD")
    p.add_argument("--z-min", type=float, default=1.5)
    p.add_argument("--tick-root", default="/Users/danielfisher/Desktop/tick")
    p.add_argument("--p-threshold", type=float, default=0.5)
    args = p.parse_args()

    print(f"Building expanded real-tick dataset for {args.symbol} (z>{args.z_min}, tick_root={args.tick_root})...")
    df = build_expanded_realtick_dataset(args.symbol, z_min=args.z_min, tick_root=args.tick_root)
    print(f"n={df.height}")
    walk_forward(df, p_threshold=args.p_threshold)


if __name__ == "__main__":
    main()
