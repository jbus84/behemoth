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
from scripts.era.llm import (
    propose_program,
    propose_xs_atomic_change,
    recombine_program,
    recombine_xs_atomic_compositions,
)
from scripts.era.sandbox import causality_probe as _xs_causality_probe
from scripts.era.sandbox import run_program as _xs_run_program
from scripts.era.seeds import RESEARCH_IDEAS, SEED_PROGRAMS
from scripts.era_scalp.cost_aware_score import GRID_Q
from scripts.era_scalp.era_engine import RunSpec, run_search_rich
from scripts.era_scalp.harness import scale_signal
from scripts.era_scalp.xs_atomic_concepts import (
    XS_CONCEPT_TAXONOMY,
    XS_SEED_COMPOSITIONS,
    composition_to_source,
    extract_concepts_from_composition,
)


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


def _sanitize_composition(comp):
    """Coerce a composition's operator values to op-name strings."""
    if not isinstance(comp, dict):
        return comp
    ops = comp.get("operators")
    if isinstance(ops, dict):
        clean = {}
        for slot, val in ops.items():
            if isinstance(val, str):
                clean[slot] = val
            elif isinstance(val, (list, tuple)) and val and isinstance(val[0], str):
                clean[slot] = val[0]
        comp = {**comp, "operators": clean}
    return comp


def crosssym_spec(
    cache_dir: str = "/tmp/era_xs_cache",
    horizon: int = 3,
    atomic_mode: bool = False,
) -> RunSpec:
    """RunSpec for cross-symbol residual scalping (config + writers; data passed separately)."""
    def context_factory(s):
        return CrossSectionContext(r=s.r, names=s.names, target=s.target,
                                   usd_sign=s.usd_sign, hour=s.hour)

    # The cross-symbol sandbox hardcodes the 'residual' entry fn, so drop required_fn.
    def run_program(src, ctx, timeout=10.0, required_fn=None):
        return _xs_run_program(src, ctx, timeout=timeout)

    def causality_probe(src, ctx, out, required_fn=None):
        return _xs_causality_probe(src, ctx, out)

    seed_compositions = None
    spec_seed_programs = dict(SEED_PROGRAMS)
    render_payload = None
    propose_atomic = None
    recombine_atomic = None
    concept_taxonomy = None
    extract_concepts_fn = None

    # Atomic-mode tuning defaults
    dimension_locked = False
    self_correct = False
    parallel_expansions = 1

    rich_templates = None
    branch_tags = {name: name for name in SEED_PROGRAMS}
    if atomic_mode:
        seed_compositions = dict(XS_SEED_COMPOSITIONS)
        spec_seed_programs = None
        render_payload = composition_to_source
        propose_atomic = propose_xs_atomic_change
        recombine_atomic = recombine_xs_atomic_compositions
        concept_taxonomy = XS_CONCEPT_TAXONOMY
        dimension_locked = True
        self_correct = False
        parallel_expansions = 2
        rich_templates = {
            "baseline": (
                "Cross-symbol residual scalper.  Measure idiosyncratic dislocation of a "
                "target FX pair vs its peer basket.  Fade rich (sell) / cheap (buy)."
            ),
        }
        # Map seeds to concept categories for diversity-aware selection
        branch_tags = {
            name: XS_CONCEPT_TAXONOMY.get(
                comp.get("operators", {}).get("base", "loo_z"),
                ("base", ""),
            )[0]
            for name, comp in XS_SEED_COMPOSITIONS.items()
        }

        def extract_concepts_fn(payload):
            if isinstance(payload, dict):
                return extract_concepts_from_composition(payload)
            return []

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
        seed_programs=spec_seed_programs,
        seed_compositions=seed_compositions,
        branch_tags=branch_tags,
        ideas=list(RESEARCH_IDEAS),
        propose=lambda ps, psc, lg, idea: propose_program(ps, psc, lg, idea, cache_dir=cache_dir),
        recombine=lambda a, sa, b, sb: recombine_program(a, sa, b, sb, cache_dir=cache_dir),
        render_payload=render_payload,
        sanitize_composition=_sanitize_composition,
        extract_concepts=extract_concepts_fn,
        propose_atomic=propose_atomic,
        recombine_atomic=recombine_atomic,
        concept_taxonomy=concept_taxonomy,
        atomic_mode=atomic_mode,
        dimension_locked=dimension_locked,
        self_correct=self_correct,
        parallel_expansions=parallel_expansions,
        rich_templates=rich_templates,
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
    ap.add_argument("--atomic", action="store_true", help="Use atomic composition mode (run_search_rich)")
    args = ap.parse_args()

    splits = build_splits(args.target, args.bar_ticks, Path(args.tom_dir),
                          Path(args.velocity_dir), horizon=args.horizon)
    spec = crosssym_spec(horizon=args.horizon, atomic_mode=args.atomic)

    if spec.atomic_mode:
        nodes = run_search_rich(spec, splits, budget=args.budget, seed=args.seed)
    else:
        nodes = run_era_search(spec, splits, budget=args.budget, seed=args.seed)
    rows = engine_verdict(spec, nodes, splits, top_k=5)

    mode_tag = " atomic" if args.atomic else ""
    lines = [f"# Cross-symbol residual verdict{mode_tag} — {args.target} "
             f"({args.bar_ticks}tick, h={args.horizon}, budget={args.budget})\n"]
    for r in rows:
        hv = r["holdout"]
        htxt = (f"holdout raw={hv['mean']:+.3f} lb={hv.get('lo', np.nan):+.3f} n={hv.get('n_trades', 0)}"
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
