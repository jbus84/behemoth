#!/usr/bin/env python3
"""A/B the full-sample (look-ahead) vs causal expanding-quantile conviction threshold.

Scores a single seed program on a symbol's holdout split both ways and reports the
net-edge delta. The delta is the edge inflation attributable to threshold look-ahead.
"""
from __future__ import annotations

from scripts.era_scalp.trade_harness import evaluate_trades


def ab_edge_delta(signal, mid, cost, test_month, pip, q, h,
                  warmup=2000, recompute_every=500) -> dict:
    """Return mean-net and entry-count for both threshold modes plus their delta."""
    full = evaluate_trades(signal, mid, cost, test_month, pip, q, h,
                           causal_threshold=False)
    causal = evaluate_trades(signal, mid, cost, test_month, pip, q, h,
                             causal_threshold=True, warmup=warmup,
                             recompute_every=recompute_every)
    full_mean = float(full["net"].mean()) if len(full) else float("nan")
    causal_mean = float(causal["net"].mean()) if len(causal) else float("nan")
    return {
        "full_mean_net": full_mean,
        "causal_mean_net": causal_mean,
        "full_n": int(len(full)),
        "causal_n": int(len(causal)),
        "delta": full_mean - causal_mean,
    }


def main() -> None:
    import argparse
    from pathlib import Path

    from scripts.era_scalp.context import FeatureContext
    from scripts.era_scalp.cost_model import realistic_cost
    from scripts.era_scalp.fade_seeds import FADE_SEED_PROGRAMS
    from scripts.era_scalp.load_splits import _pip_size, build_trade_splits
    from scripts.era_scalp.sandbox import run_program

    ap = argparse.ArgumentParser()
    ap.add_argument("--seed-name", default="vr_gated_fade")
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--tv-dir", default="data/analysis/tick_velocity")
    ap.add_argument("--q", type=float, default=0.99)
    ap.add_argument("--h", type=int, default=100)
    ap.add_argument("--warmup", type=int, default=20000)
    ap.add_argument("--recompute-every", type=int, default=2000)
    args = ap.parse_args()

    src = FADE_SEED_PROGRAMS[args.seed_name]
    sp = build_trade_splits(
        args.symbol, Path(args.tv_dir) / f"{args.symbol}_100tick_velocity.parquet",
        embargo=args.h,
    )
    d = sp["holdout"]
    ctx = FeatureContext(X=d.X, names=d.names, hour=d.hour)
    sig, err, _ = run_program(src, ctx, required_fn="signal")
    if err is not None:
        raise SystemExit(f"program error: {err}")
    cost = realistic_cost(d.spread_pips)
    out = ab_edge_delta(sig, d.mid, cost, d.test_month, _pip_size(args.symbol),
                        args.q, args.h, warmup=args.warmup,
                        recompute_every=args.recompute_every)
    print(f"seed={args.seed_name} symbol={args.symbol} q={args.q} h={args.h}")
    print(f"  full-sample : mean_net={out['full_mean_net']:+.4f}  n={out['full_n']}")
    print(f"  causal      : mean_net={out['causal_mean_net']:+.4f}  n={out['causal_n']}")
    print(f"  look-ahead inflation (delta) = {out['delta']:+.4f} pips/trade")


if __name__ == "__main__":
    main()
