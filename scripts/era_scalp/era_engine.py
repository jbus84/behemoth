from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from scripts.era.puct import Node, puct_search, select_diversity
from scripts.era_scalp.bayes_edge import monthly_net
from scripts.era_scalp.cost_aware_score import (
    GRID_H,
    GRID_Q,
    _sidak_z,
    effective_n_tests,
    fair_node_value,
    fast_lower_bound,
)
from scripts.era_scalp.deflated_selection import (
    deflated_edge_prob,
    is_significant_after_deflation,
)
from scripts.era_scalp.temporal_robustness import (
    is_temporally_robust,
    temporal_robustness_verdict,
)


@dataclass
class RunSpec:
    """Configuration that makes the ERA search reusable across problems.

    Only these fields vary between directional / fair-price / cross-symbol; the scoring,
    guards, and (later) search loop are shared. score_frame is the keystone: given a
    program's output array, a split, and a (q,h) cell, it returns a per-trade
    DataFrame[net, test_month] which all the shared machinery consumes."""
    name: str
    required_fn: str                                   # "signal" | "estimate_fair" | "residual"
    run_program: Callable                              # sandbox.run_program for this context type
    causality_probe: Callable                          # sandbox.causality_probe for this context type
    context_factory: Callable[[Any], Any]              # split -> ctx
    score_frame: Callable[[Any, Any, float, int], pd.DataFrame]  # (out, split, q, h) -> net frame
    grid_q: list | None = None
    grid_h: list | None = None
    aggregate: str = "robust"                          # "robust" (mean-std) | "best_cell" (Sidak/eff-m)
    z: float = 1.645
    timeout: float = 10.0
    # ── search-loop config (optional; only needed by run_era_search) ──────────
    seed_programs: dict | None = None                  # name -> program source
    branch_tags: dict | None = None                    # name -> branch label (diversity)
    ideas: list | None = None                          # research-idea prompts for `propose`
    propose: Callable | None = None                    # (parent_src, score, logs, idea) -> src
    recombine: Callable | None = None                  # (srcA, scoreA, srcB, scoreB) -> src
    c_branch: float = 0.7
    p_recombine: float = 0.25

    def __post_init__(self):
        if self.grid_q is None:
            self.grid_q = list(GRID_Q)
        if self.grid_h is None:
            self.grid_h = list(GRID_H)


def score_program(src: str, spec: RunSpec, split) -> tuple[float, float, float, str]:
    """Generic per-program scorer. Reproduces CostAwarePerSymbolScorer, driven by `spec`.

    value = mean(lb)-std(lb) over (q,h) cells when spec.aggregate=='robust' (directional);
    or the effective-m Sidak-corrected best-cell lower bound when 'best_cell' (fair-price).
    Returns (value, mean, se, logs); -1e6 on exec error or causality failure."""
    ctx = spec.context_factory(split)
    out, err, logs = spec.run_program(src, ctx, timeout=spec.timeout, required_fn=spec.required_fn)
    if err is not None:
        return -1e6, float("nan"), float("nan"), f"exec: {err}\n{logs}"
    ok, reason = spec.causality_probe(src, ctx, out, required_fn=spec.required_fn)
    if not ok:
        return -1e6, float("nan"), float("nan"), f"causality_probe: {reason}"
    lbs, cells, cell_series, best = [], [], [], None
    for q in spec.grid_q:
        for h in spec.grid_h:
            frame = spec.score_frame(out, split, q, h)
            lb, mean, se = fast_lower_bound(frame, z=spec.z)
            if not np.isfinite(lb):
                continue
            lbs.append(lb)
            cells.append((mean, se))
            mn = monthly_net(frame)
            cell_series.append(pd.Series(mn["mean_net"].to_numpy(float), index=mn["test_month"].to_numpy()))
            if best is None or lb > best[0]:
                best = (lb, mean, se)
    if not lbs:
        return -1e6, float("nan"), float("nan"), "no admissible (q,h) cell"
    if spec.aggregate == "best_cell":
        m_eff = effective_n_tests(cell_series)
        value = fair_node_value(cells, m=m_eff, z_base=spec.z)
        zc = _sidak_z(spec.z, m_eff)
        bi = int(np.argmax([m - zc * s for m, s in cells]))
        best = (value, cells[bi][0], cells[bi][1])
    else:
        arr = np.asarray(lbs, float)
        value = float(arr.mean() - arr.std())
    return value, best[1], best[2], logs


def _recombination_parents(all_nodes, c_branch, rng):
    """Diversity-aware recombination parents: parent_a via the branch-diversity selector
    (not the greedy top scorer), parent_b = best node from a DIFFERENT branch."""
    parent_a = select_diversity(all_nodes, c_puct=1.0, c_branch=c_branch, rng=rng)
    cands = sorted(all_nodes, key=lambda n: n.score, reverse=True)
    parent_b = next((n for n in cands if n.branch != parent_a.branch), None)
    if parent_b is None:
        parent_b = next((n for n in cands if n is not parent_a), parent_a)
    return parent_a, parent_b


def run_era_search(spec: RunSpec, splits: dict, budget: int, seed: int = 0) -> list:
    """Shared diversity-PUCT search driven by `spec`. Scores the seed forest on the
    validation split, then expands `budget` times via diversity-aware recombination /
    propose (writers injected on `spec`, so the engine is LLM-agnostic and testable).
    Returns all nodes (seeds + expansions)."""
    rng = random.Random(seed)
    nprng = np.random.default_rng(seed)
    val = splits["validation"]
    tags = spec.branch_tags or {}
    forest = []
    for name, src in (spec.seed_programs or {}).items():
        v, m, se, lg = score_program(src, spec, val)
        forest.append(Node(payload=src, score=v, parent=None, logs=lg, mean=m, se=se,
                           branch=tags.get(name)))
    all_nodes = list(forest)

    def expand(parent):
        if (spec.recombine is not None and rng.random() < spec.p_recombine
                and len(all_nodes) >= 2):
            pa, pb = _recombination_parents(all_nodes, spec.c_branch, nprng)
            child_src = spec.recombine(pa.payload, pa.score, pb.payload, pb.score)
            child_branch = pa.branch
        elif spec.propose is not None:
            idea = rng.choice(spec.ideas) if spec.ideas else ""
            child_src = spec.propose(parent.payload, parent.score, parent.logs, idea)
            child_branch = parent.branch
        else:
            child_src = ""  # no writer injected -> empty program (scored as invalid)
        v, m, se, lg = score_program(child_src, spec, val)
        child = Node(payload=child_src, score=v, parent=parent, logs=lg, mean=m, se=se,
                     branch=child_branch)
        all_nodes.append(child)
        return child

    def _select(ns, c):
        return select_diversity(ns, c_puct=c, c_branch=spec.c_branch, rng=nprng)

    return puct_search(forest, expand, budget=budget, c_puct=1.0, seed=seed, select_fn=_select)


def _best_cell_frame(spec: RunSpec, out, split):
    """The (net, test_month) frame of the (q,h) cell with the highest lower bound."""
    best = None
    for q in spec.grid_q:
        for h in spec.grid_h:
            frame = spec.score_frame(out, split, q, h)
            lb, _, _ = fast_lower_bound(frame, z=spec.z)
            if np.isfinite(lb) and (best is None or lb > best[0]):
                best = (lb, frame)
    return best[1] if best is not None else None


def engine_verdict(spec: RunSpec, nodes: list, splits: dict, top_k: int = 5,
                   temporal: bool = True, num_warmup: int = 400, num_samples: int = 400,
                   num_chains: int = 2) -> list:
    """Annotate the top-K ranked nodes with holdout edge, temporal robustness, and DSR.
    Returns a list of dicts (one per ranked node), reusing the guard modules."""
    ranked = sorted([n for n in nodes if n.score > -1e6 + 1], key=lambda n: n.score, reverse=True)
    trial_means = [n.mean for n in ranked if np.isfinite(n.mean) and np.isfinite(n.se)]
    val = splits["validation"]
    hold = splits.get("holdout")
    rows = []
    for nd in ranked[:top_k]:
        holdout = None
        if hold is not None:
            ctx = spec.context_factory(hold)
            out, err, _ = spec.run_program(nd.payload, ctx, timeout=spec.timeout,
                                           required_fn=spec.required_fn)
            if err is None:
                frame = _best_cell_frame(spec, out, hold)
                if frame is not None and len(frame):
                    lb, mean, se = fast_lower_bound(frame, z=spec.z)
                    holdout = {"lb": lb, "mean": mean, "se": se, "n": int(len(frame))}
        tv = None
        if temporal:
            ctx = spec.context_factory(val)
            out, err, _ = spec.run_program(nd.payload, ctx, timeout=spec.timeout,
                                           required_fn=spec.required_fn)
            if err is None:
                frame = _best_cell_frame(spec, out, val)
                if frame is not None and len(frame):
                    tv = temporal_robustness_verdict(frame, seed=0, num_warmup=num_warmup,
                                                     num_samples=num_samples, num_chains=num_chains)
        dsr = deflated_edge_prob(nd.mean, nd.se, trial_means)
        rows.append({
            "branch": nd.branch, "val": nd.score, "holdout": holdout,
            "temporal": tv, "robust": bool(tv and is_temporally_robust(tv)),
            "dsr": dsr, "dsr_sig": is_significant_after_deflation(dsr),
        })
    return rows
