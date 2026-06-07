"""Smoke test driver for crypto cross-sectional flow boosting.

Runs a shallow PUCT search (budget=12) over flow-centric feature compositions,
training a pooled CatBoost on 32-pair hourly kline data and scoring a proportional
portfolio net of taker fees.

Usage:
    uv run python -m scripts.research.crypto_flow_boost_smoke

Data: reads /tmp/crypto_panel_ext.parquet (from crypto_flow_xs_exec.py ingest).
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.era_scalp.crypto_boost_spec import (  # noqa: E402
    build_crypto_splits,
    run_crypto_boost_search,
)


def main() -> None:
    panel_path = "/tmp/crypto_panel_ext.parquet"
    if not Path(panel_path).exists():
        print(f"ERROR: panel not found at {panel_path}")
        print("Run crypto_flow_xs_exec.py ingest first.")
        sys.exit(1)

    print("Building crypto splits ...")
    splits = build_crypto_splits(panel_path)
    for k, v in splits.items():
        print(f"  {k}: {v.n_bars} bars × {len(v.symbols)} symbols")

    print("\nRunning shallow PUCT search (budget=12, horizon=6) ...")
    result = run_crypto_boost_search(
        splits, budget=12, seed=0, horizon=6,
        cache_dir=".crypto_boost_cache",
    )

    survivor = result.get("survivor")
    holdout = result.get("holdout")

    if survivor is None:
        print("\nNo survivor found (all nodes rejected).")
        return

    print("\n=== Survivor ===")
    print(f"  branch:        {survivor['branch']}")
    print(f"  val_v1:        {survivor['val_v1']:.3f}")
    print(f"  val_v1_pen:    {survivor['val_v1_penalised']:.3f}")
    print(f"  val_v2:        {survivor['val_v2']:.3f}")
    print(f"  n_feat:        {survivor['n_feat']}")

    if holdout:
        h = holdout.get("holdout")
        tv = holdout.get("temporal")
        print("\n=== Holdout ===")
        if h:
            print(f"  p_positive:    {h.get('p_positive', 'N/A'):.3f}")
            print(f"  mean:          {h.get('mean', 'N/A'):.3f}")
            print(f"  raw_mean:      {h.get('raw_mean', 'N/A'):.3f}")
            print(f"  q/h/n_trades:  {h.get('q', 'N/A')}/{h.get('h', 'N/A')}/{h.get('n_trades', 'N/A')}")
        print(f"  robust:        {holdout.get('robust', 'N/A')}")
        print(f"  dsr_sig:       {holdout.get('dsr_sig', 'N/A')}")
        if tv:
            print(f"  temporal p+:   {tv.get('p_positive', 'N/A'):.3f}")
            print(f"  worst_win_p+:  {tv.get('worst_window_p_positive', 'N/A'):.3f}")

    print("\nDone.")


if __name__ == "__main__":
    main()
