"""Intraday cross-sectional FX basket book as a RunSpec for the unified ERA engine.

Sibling to era_xs (single-leg residual fade): this is a dollar-neutral long/short basket.
A program outputs a (n_bars, n_sym) cross-sectional score; the score_frame ranks it into a
banded, top-k/bottom-k, cost-toggled per-rebalance net frame consumed by the shared engine
(guards: temporal robustness, DSR, effective-m Sidak, edge_verdict)."""
from __future__ import annotations

from scripts.era_scalp.basket_context import BasketContext
from scripts.era_scalp.basket_sandbox import causality_probe as _bk_causality_probe
from scripts.era_scalp.basket_sandbox import run_program as _bk_run_program
from scripts.era_scalp.basket_score import make_basket_score_frame, periodic_rebalance
from scripts.era_scalp.basket_seeds import BASKET_RESEARCH_IDEAS, BASKET_SEED_PROGRAMS
from scripts.era_scalp.era_engine import RunSpec

# London/NY overlap (UTC), the deepest-liquidity intraday window.
LONDON_NY_OVERLAP = (12, 16)


def basket_spec(
    horizon: int = 3,
    k: int = 2,
    band: float = 0.0,
    fill_mode: str = "aggressive",
    passive_frac: float = 0.5,
    session=None,
    holding_model=periodic_rebalance,
) -> RunSpec:
    """RunSpec for the cross-sectional basket book (data passed separately via splits).

    fill_mode='aggressive' is the gating verdict; score again with 'passive' to report
    the optimistic bound. session=LONDON_NY_OVERLAP restricts to the liquid window."""

    def context_factory(split):
        return BasketContext(r=split.r, names=split.names, hour=split.hour)

    def run_program(src, ctx, timeout=10.0, required_fn=None):
        return _bk_run_program(src, ctx, timeout=timeout)

    def causality_probe(src, ctx, out, required_fn=None):
        return _bk_causality_probe(src, ctx, out)

    score_frame = make_basket_score_frame(
        k=k, band=band, fill_mode=fill_mode, passive_frac=passive_frac,
        session=session, holding_model=holding_model,
    )

    return RunSpec(
        name=f"basket_k{k}_b{band}_{fill_mode}",
        required_fn="score",
        run_program=run_program,
        causality_probe=causality_probe,
        context_factory=context_factory,
        score_frame=score_frame,
        grid_q=[0.0],
        grid_h=[horizon],
        aggregate="robust",
        seed_programs=dict(BASKET_SEED_PROGRAMS),
        branch_tags={name: name for name in BASKET_SEED_PROGRAMS},
        ideas=list(BASKET_RESEARCH_IDEAS),
    )
