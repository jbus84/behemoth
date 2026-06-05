"""Cross-symbol residual scalping as a RunSpec for the unified ERA engine.

Reuses the cross-symbol stat-arb seeds + CrossSectionContext from `scripts.era`, and the
shared engine (search loop + guards: temporal robustness, DSR, effective-m Sidak) from
`era_engine`. The only problem-specific piece is `xs_score_frame`: it turns a program's
cross-sectional residual into a net-of-realistic-cost, single-leg, USD-aligned fade trade.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.era.context import CrossSectionContext
from scripts.era.llm import propose_program, recombine_program
from scripts.era.sandbox import causality_probe as _xs_causality_probe
from scripts.era.sandbox import run_program as _xs_run_program
from scripts.era.seeds import RESEARCH_IDEAS, SEED_PROGRAMS
from scripts.era_scalp.cost_aware_score import GRID_Q
from scripts.era_scalp.era_engine import RunSpec
from scripts.era_scalp.harness import scale_signal


def xs_score_frame(out, split, q, h):
    """Net-of-cost cross-symbol residual trade frame.

    Fade the USD-aligned cross-sectional dislocation: enter when |scaled residual| is in
    the top-q, side = -sign(residual)*usd_sign, net = side*y_fwd - cost. y_fwd is at the
    dataset's build horizon, so `h` is fixed by the data (grid_h is a single value)."""
    raw = np.asarray(out, float)
    z = scale_signal(raw)
    y = np.asarray(split.y_fwd, float)
    cost = np.asarray(split.cost, float)
    fin = np.isfinite(z) & np.isfinite(y) & np.isfinite(cost)
    if fin.sum() < 2:
        return pd.DataFrame({"net": np.array([]), "test_month": np.array([])})
    thr = np.quantile(np.abs(z[fin]), q)
    entry = fin & (np.abs(z) >= thr)
    side = -np.sign(raw) * int(split.usd_sign)
    net = side * y - cost
    return pd.DataFrame({"net": net[entry], "test_month": np.asarray(split.test_month)[entry]})


def crosssym_spec(cache_dir: str = "/tmp/era_xs_cache", horizon: int = 3) -> RunSpec:
    """RunSpec for cross-symbol residual scalping (config + writers; data passed separately)."""
    def context_factory(s):
        return CrossSectionContext(r=s.r, names=s.names, target=s.target,
                                   usd_sign=s.usd_sign, hour=s.hour)

    # The cross-symbol sandbox hardcodes the 'residual' entry fn, so drop required_fn.
    def run_program(src, ctx, timeout=10.0, required_fn=None):
        return _xs_run_program(src, ctx, timeout=timeout)

    def causality_probe(src, ctx, out, required_fn=None):
        return _xs_causality_probe(src, ctx, out)

    return RunSpec(
        name="cross_symbol",
        required_fn="residual",
        run_program=run_program,
        causality_probe=causality_probe,
        context_factory=context_factory,
        score_frame=xs_score_frame,
        grid_q=list(GRID_Q),
        grid_h=[horizon],
        aggregate="robust",
        seed_programs=dict(SEED_PROGRAMS),
        branch_tags={name: name for name in SEED_PROGRAMS},  # each stat-arb family its own branch
        ideas=list(RESEARCH_IDEAS),
        propose=lambda ps, psc, lg, idea: propose_program(ps, psc, lg, idea, cache_dir=cache_dir),
        recombine=lambda a, sa, b, sb: recombine_program(a, sa, b, sb, cache_dir=cache_dir),
    )


def main() -> None:
    import argparse
    from pathlib import Path

    from scripts.era.load_splits import build_splits
    from scripts.era_scalp.era_engine import engine_verdict, run_era_search

    ap = argparse.ArgumentParser(description="Cross-symbol residual scalping via the unified ERA engine")
    ap.add_argument("--target", default="EURUSD")
    ap.add_argument("--bar-ticks", type=int, default=100)
    ap.add_argument("--tom-dir", default="data/analysis/tick_opportunity_mining")
    ap.add_argument("--velocity-dir", default="data/analysis/tick_velocity")
    ap.add_argument("--horizon", type=int, default=3)
    ap.add_argument("--budget", type=int, default=40)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default="/tmp/era_xs/verdict.md")
    args = ap.parse_args()

    splits = build_splits(args.target, args.bar_ticks, Path(args.tom_dir),
                          Path(args.velocity_dir), horizon=args.horizon)
    spec = crosssym_spec(horizon=args.horizon)
    nodes = run_era_search(spec, splits, budget=args.budget, seed=args.seed)
    rows = engine_verdict(spec, nodes, splits, top_k=5)

    lines = [f"# Cross-symbol residual verdict — {args.target} "
             f"({args.bar_ticks}tick, h={args.horizon}, budget={args.budget})\n"]
    for r in rows:
        hv = r["holdout"]
        htxt = (f"holdout raw={hv['mean']:+.3f} lb={hv['lb']:+.3f} n={hv['n']}"
                if hv else "holdout: program error")
        tv = r["temporal"]
        ttxt = (f"P(edge>0)={tv['p_positive']:.2f} worst-win={tv['worst_window_p_positive']:.2f} "
                f"robust={r['robust']}" if tv and tv.get("status") == "ok"
                else f"temporal:{tv.get('status') if tv else 'n/a'}")
        lines.append(f"- [{r['branch']}] val={r['val']:+.3f} | {htxt} | {ttxt} "
                     f"| DSR={r['dsr']:.2f} sig={r['dsr_sig']}")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join(lines) + "\n")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
