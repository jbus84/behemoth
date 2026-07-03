"""
Compare BoostLSS distribution families for the reversion-OCO strategy.

Runs the full pipeline (WFO -> tick-exact backtest -> meta-labeler) once per
distribution family on a small pair subset, and prints a side-by-side table:
OOS NLL (diagnostic fit quality), meta-labeler AUC, TP%, and Option B all-in
bps/fill (the deciding trading metric).

Usage::

    uv run python scripts/boostlss_xs/compare_distributions.py \\
        --data-dir /path/to/tick_bars \\
        --tick-dir /path/to/raw_ticks \\
        --output-dir /tmp/dist_compare \\
        [--pairs EURUSD GBPJPY AUDUSD USDJPY] \\
        [--families gaussian merton shash] \\
        [--threshold 0.55]
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import numpy as np
import pandas as pd

from distributions import get_dist_spec
from meta_label_straddle import (
    _FEAT_COLS,
    _option_b_net_per_fill,
    fit_meta_label_wfo,
    run_tick_backtest,
)

_DEFAULT_PAIRS: list[str] = ["EURUSD", "GBPJPY", "AUDUSD", "USDJPY"]
_DEFAULT_FAMILIES: list[str] = ["gaussian", "merton", "shash"]


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Compare BoostLSS distribution families")
    p.add_argument("--data-dir",   default="/Users/danielfisher/repositories/behemoth/data/tick_bars")
    p.add_argument("--tick-dir",   default="/Users/danielfisher/Desktop/tick")
    p.add_argument("--output-dir", default="/tmp/dist_compare")
    p.add_argument("--pairs",      nargs="+", default=_DEFAULT_PAIRS)
    p.add_argument("--families",   nargs="+", default=_DEFAULT_FAMILIES)
    p.add_argument("--threshold",  type=float, default=0.55)
    p.add_argument("--entry-k",    type=float, default=0.5)
    p.add_argument("--tp-k",       type=float, default=0.5)
    p.add_argument("--sl-k",       type=float, default=1.0)
    p.add_argument("--hold-hours", type=int,   default=8)
    p.add_argument("--sig-thresh", type=float, default=1.5)
    p.add_argument("--tail-rows",  type=int,   default=None,
                    help="Limit each pair to the most recent N rows of 1m data "
                         "(fast sanity-check mode; much cheaper WFO fit).")
    return p.parse_args()


def run_family(
    family: str,
    pairs: list[str],
    data_dir: str,
    tick_dir: str,
    entry_k: float,
    tp_k: float,
    sl_k: float,
    hold_hours: int,
    sig_thresh: float,
    threshold: float,
    tail_rows: int | None = None,
) -> dict:
    spec = get_dist_spec(family)
    feat_cols = _FEAT_COLS + spec.extra_features

    all_nll: list[float] = []
    tick_dfs: list[pd.DataFrame] = []
    for sym in pairs:
        flow_path = os.path.join(data_dir, f"{sym}_1m_flow.parquet")
        tick_path = os.path.join(tick_dir, sym)
        if not os.path.exists(flow_path) or not os.path.isdir(tick_path):
            print(f"  [{family}] {sym}: missing data, skipping")
            continue
        df_sym, fold_nll = run_tick_backtest(
            sym=sym, data_dir=data_dir, tick_dir=tick_dir,
            entry_k=entry_k, tp_k=tp_k, sl_k=sl_k,
            hold_hours=hold_hours, sig_thresh=sig_thresh,
            family=family, tail_rows=tail_rows,
        )
        all_nll.extend(fold_nll)
        if len(df_sym) == 0:
            continue
        tick_dfs.append(df_sym)

    if not tick_dfs:
        return {
            "family": family, "n_trades": 0,
            "oos_nll": float("nan"), "auc": float("nan"),
            "tp_pct": float("nan"), "option_b": float("nan"),
        }

    all_raw = pd.concat(tick_dfs, ignore_index=True)

    oos_dfs: list[pd.DataFrame] = []
    for sym, g in all_raw.groupby("sym"):
        try:
            oos_dfs.append(fit_meta_label_wfo(g.copy(), feat_cols=feat_cols))
        except Exception as e:
            print(f"  [{family}] {sym}: meta-label failed — {e}")

    if not oos_dfs:
        # NOTE: fold_nll can contain inf on some pairs/families — the earliest
        # WFO fold can overflow sigma on a small early training set. This does
        # not affect trading P&L, only this diagnostic, so filter non-finite
        # values before averaging (Task 3 finding).
        finite_nll = [x for x in all_nll if np.isfinite(x)]
        return {
            "family": family, "n_trades": len(all_raw),
            "oos_nll": float(np.mean(finite_nll)) if finite_nll else float("nan"),
            "auc": float("nan"), "tp_pct": float("nan"), "option_b": float("nan"),
        }

    result = pd.concat(oos_dfs, ignore_index=True)
    ob_net = _option_b_net_per_fill(result, threshold)

    finite_nll = [x for x in all_nll if np.isfinite(x)]
    return {
        "family":   family,
        "n_trades": len(result),
        "oos_nll":  float(np.mean(finite_nll)) if finite_nll else float("nan"),
        "auc":      float(result.mean_auc.mean()),
        "tp_pct":   float(result.label.mean()),
        "option_b": ob_net,
    }


if __name__ == "__main__":
    args = _parse_args()
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    for family in args.families:
        print(f"\n{'='*60}\nFamily: {family}\n{'='*60}")
        r = run_family(
            family=family, pairs=args.pairs,
            data_dir=args.data_dir, tick_dir=args.tick_dir,
            entry_k=args.entry_k, tp_k=args.tp_k, sl_k=args.sl_k,
            hold_hours=args.hold_hours, sig_thresh=args.sig_thresh,
            threshold=args.threshold, tail_rows=args.tail_rows,
        )
        results.append(r)

    print(f"\n{'='*76}")
    print("DISTRIBUTION COMPARISON")
    print(f"{'='*76}")
    print(f"  {'Family':<10}  {'n_trades':>8}  {'OOS NLL':>9}  {'Meta AUC':>9}  "
          f"{'TP%':>7}  {'Option B bps/fill':>18}")
    for r in results:
        print(f"  {r['family']:<10}  {r['n_trades']:>8}  {r['oos_nll']:>9.4f}  "
              f"{r['auc']:>9.3f}  {r['tp_pct']:>6.1%}  {r['option_b']:>+18.3f}")

    out_path = os.path.join(args.output_dir, "comparison_summary.csv")
    pd.DataFrame(results).to_csv(out_path, index=False)
    print(f"\nSummary → {out_path}")
