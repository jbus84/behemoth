from __future__ import annotations

import concurrent.futures
import random
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from scripts.era.puct import (
    Node,
    puct_search,
    select_diversity,
    select_diversity_with_history,
    select_diversity_with_llm_prior,
    select_thompson,
)
from scripts.era_scalp.bayes_edge import edge_verdict, monthly_net
from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.cost_aware_score import (
    GRID_H,
    GRID_H_SHORT,
    GRID_Q,
    _sidak_z,
    effective_n_tests,
    fair_node_value,
    fast_lower_bound,
)
from scripts.era_scalp.cost_model import realistic_cost
from scripts.era_scalp.deflated_selection import (
    deflated_edge_prob,
    is_significant_after_deflation,
)
from scripts.era_scalp.load_splits import _pip_size
from scripts.era_scalp.sandbox import causality_probe, run_program
from scripts.era_scalp.temporal_robustness import (
    is_temporally_robust,
    temporal_robustness_verdict,
)
from scripts.era_scalp.trade_harness import evaluate_fair_price_trades, evaluate_trades


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
    seed_compositions: dict | None = None              # name -> composition dict (atomic mode seeds)
    branch_tags: dict | None = None                    # name -> branch label (diversity)
    ideas: list | None = None                          # research-idea prompts for `propose`
    propose: Callable | None = None                    # (parent_src, score, logs, idea) -> src
    recombine: Callable | None = None                  # (srcA, scoreA, srcB, scoreB) -> src
    c_branch: float = 0.7
    p_recombine: float = 0.25
    # ── rich-loop hooks (optional; only the run_era_eur directional/fair port uses these).
    #    All default off/None so the cross-symbol path (era_xs) is unaffected. ───────────
    propose_branch: Callable | None = None              # (payload, score, logs, branch, rich_template, cache_dir) -> src
    propose_branch_with_prior: Callable | None = None   # -> (src, prior)
    propose_dimension_locked: Callable | None = None    # (...,target_dimension,...) -> (src, prior)
    propose_atomic: Callable | None = None              # (comp, score, slot, concept, cache_dir) -> (comp, prior)
    recombine_branch: Callable | None = None             # (payA,scoreA,brA, payB,scoreB,brB, cross_text, cache_dir) -> src
    recombine_atomic: Callable | None = None            # (compA, scoreA, compB, scoreB, cache_dir) -> (comp, prior)
    cross_branch_index: dict | None = None              # (branchA, branchB) -> recombination prompt text
    self_correct_fn: Callable | None = None             # (failed_src, error_log, branch, template, cache_dir) -> src
    extract_composition: Callable | None = None         # (src, fallback_comp, cache_dir) -> comp|None
    render_payload: Callable | None = None              # payload(str|dict) -> src   (composition_to_source)
    sanitize_composition: Callable | None = None        # payload -> payload
    extract_concepts: Callable | None = None            # payload -> list[str]
    select_with_history: Callable | None = None         # diversity selector (history-aware)
    select_with_llm_prior: Callable | None = None       # diversity selector (LLM-prior-aware)
    rich_templates: dict | None = None                  # branch -> prompt template
    concept_taxonomy: dict | None = None                # for dimension-locking cycle
    tracker: Any = None                                 # optional ExpansionTracker
    archive: Any = None                                 # optional WinnerArchive
    atomic_mode: bool = False
    dimension_locked: bool = False
    self_correct: bool = False
    use_llm_prior: bool = False
    parallel_expansions: int = 1
    branch_depth_limit: int = 3
    p_cross_branch: float = 0.3
    verbose: bool = False

    def __post_init__(self):
        if self.grid_q is None:
            self.grid_q = list(GRID_Q)
        if self.grid_h is None:
            self.grid_h = list(GRID_H)


def scoring_spec(symbol: str, *, fair_price_mode: bool = False) -> RunSpec:
    """Build the scoring half of a RunSpec for per-symbol directional / fair-price search.

    This is the single definition of net-of-realistic-cost scoring — `score_program` over
    this spec replaces the retired CostAwarePerSymbolScorer (parity-proven, #316).
    Directional: robust (mean-std) aggregation over GRID_H with required_fn='signal'.
    Fair-price: best-cell (Šidák/effective-m) over GRID_H_SHORT with required_fn='estimate_fair'.
    Callers (run_era_eur) layer the loop hooks on top via dataclasses.replace."""
    pip = _pip_size(symbol)

    def _ctx(s):
        return FeatureContext(X=s.X, names=s.names, hour=s.hour)

    if fair_price_mode:
        def score_frame(out, split, q, h):
            return evaluate_fair_price_trades(out, split.mid, realistic_cost(split.spread_pips),
                                              split.test_month, pip, q, h)
        return RunSpec(name=symbol, required_fn="estimate_fair", run_program=run_program,
                       causality_probe=causality_probe, context_factory=_ctx,
                       score_frame=score_frame, grid_h=list(GRID_H_SHORT), aggregate="best_cell")

    def score_frame(out, split, q, h):
        return evaluate_trades(out, split.mid, realistic_cost(split.spread_pips),
                               split.test_month, pip, q, h)
    return RunSpec(name=symbol, required_fn="signal", run_program=run_program,
                   causality_probe=causality_probe, context_factory=_ctx,
                   score_frame=score_frame, grid_h=list(GRID_H), aggregate="robust")


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


def _holdout_edge(spec: RunSpec, out, split, name: str = "program", min_trades: int = 50,
                  num_warmup: int = 500, num_samples: int = 500, num_chains: int = 2):
    """Holdout edge at the best-by-P(edge>0) (q,h) cell via the hierarchical MCMC
    edge_verdict — mirrors run_era_eur.holdout_verdict so the engine is a faithful
    superset. Returns the pooled posterior + q/h/n_trades/raw_mean, or None."""
    best = None
    for q in spec.grid_q:
        for h in spec.grid_h:
            frame = spec.score_frame(out, split, q, h)
            if len(frame) < min_trades:
                continue
            try:
                post = edge_verdict({name: frame}, num_warmup=num_warmup,
                                    num_samples=num_samples, num_chains=num_chains)
            except ValueError:
                continue
            p = post.pooled["p_positive"]
            if best is None or p > best["p_positive"]:
                best = {**post.pooled, "q": q, "h": h, "n_trades": int(len(frame)),
                        "raw_mean": float(frame["net"].mean())}
    return best


def engine_verdict(spec: RunSpec, nodes: list, splits: dict, top_k: int = 5,
                   temporal: bool = True, num_warmup: int = 400, num_samples: int = 400,
                   num_chains: int = 2, holdout_warmup: int = 500, holdout_samples: int = 500,
                   holdout_chains: int = 2) -> list:
    """Annotate the top-K ranked nodes with holdout edge, temporal robustness, and DSR.
    Holdout uses the MCMC edge_verdict at the best-by-P(edge>0) cell (faithful to
    run_era_eur). Returns a list of dicts (one per ranked node)."""
    ranked = sorted([n for n in nodes if n.score > -1e6 + 1], key=lambda n: n.score, reverse=True)
    trial_means = [n.mean for n in ranked if np.isfinite(n.mean) and np.isfinite(n.se)]
    val = splits["validation"]
    hold = splits.get("holdout")
    rows = []
    def _render_payload(payload):
        if spec.atomic_mode and isinstance(payload, dict) and spec.render_payload is not None:
            return spec.render_payload(payload)
        return str(payload)

    for nd in ranked[:top_k]:
        holdout = None
        if hold is not None:
            ctx = spec.context_factory(hold)
            src = _render_payload(nd.payload)
            out, err, _ = spec.run_program(src, ctx, timeout=spec.timeout,
                                           required_fn=spec.required_fn)
            if err is None:
                holdout = _holdout_edge(spec, out, hold, name=spec.name,
                                        num_warmup=holdout_warmup, num_samples=holdout_samples,
                                        num_chains=holdout_chains)
        tv = None
        if temporal:
            ctx = spec.context_factory(val)
            src = _render_payload(nd.payload)
            out, err, _ = spec.run_program(src, ctx, timeout=spec.timeout,
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


def run_search_rich(
    spec: RunSpec,
    splits: dict,
    *,
    budget: int = 60,
    seed: int = 0,
    cache_dir: str = ".era_cache",
    select_policy: str = "diversity",
    warm_start: bool = False,
    concept_mode: bool = False,
    resume_tree: bool = False,
) -> list:
    """Full directional / fair-price ERA-PUCT loop — ported verbatim from
    `run_era_eur.run_search`. Problem-specific writers/constants/flags arrive on `spec`
    (so the engine never imports back into the runner); scoring goes through
    `score_program` (parity-equivalent to CostAwarePerSymbolScorer, #316). Pinned by
    tests/era_scalp/test_run_search_characterization.py."""
    rng = random.Random(seed)
    nprng = np.random.default_rng(seed)

    atomic_mode = spec.atomic_mode
    dimension_locked = spec.dimension_locked
    self_correct = spec.self_correct
    use_llm_prior = spec.use_llm_prior
    parallel_expansions = spec.parallel_expansions
    branch_depth_limit = spec.branch_depth_limit
    p_cross_branch = spec.p_cross_branch
    p_recombine = spec.p_recombine
    c_branch = spec.c_branch
    verbose = spec.verbose
    tracker = spec.tracker
    archive = spec.archive
    rich_templates = spec.rich_templates or {}
    cross_branch_index = spec.cross_branch_index or {}
    concept_taxonomy = spec.concept_taxonomy or {}
    seed_branch_tags = spec.branch_tags or {}

    # Bind writer hooks to locals so every call site is Callable (ty-clean); a genuinely
    # missing hook fails loudly rather than silently degrading.
    def _missing(*_a, **_k):
        raise RuntimeError("required writer hook not set on RunSpec for run_search_rich")

    render_payload = spec.render_payload or str
    sanitize = spec.sanitize_composition or (lambda p: p)
    extract_concepts = spec.extract_concepts or (lambda _p: [])
    propose_branch = spec.propose_branch or _missing
    propose_branch_with_prior = spec.propose_branch_with_prior or _missing
    propose_dimension_locked = spec.propose_dimension_locked or _missing
    propose_atomic = spec.propose_atomic or _missing
    recombine_branch = spec.recombine_branch or _missing
    recombine_atomic = spec.recombine_atomic or _missing
    self_correct_fn = spec.self_correct_fn or _missing
    extract_composition = spec.extract_composition or _missing

    def _score(src):
        return score_program(src, spec, splits["validation"])

    def _render(payload):
        if atomic_mode and isinstance(payload, dict):
            return render_payload(payload)
        return str(payload)

    def _concepts(payload):
        return extract_concepts(payload)

    # ── Optional: resume from saved tree state ──
    forest: list[Node] = []
    if resume_tree and tracker is not None:
        resumed = tracker.load_tree_state()
        if resumed:
            forest = [n for n in resumed if n.parent is None]
            print(f"[resume] loaded {len(resumed)} nodes ({len(forest)} roots) from tree state")

    if not forest:
        if atomic_mode and spec.seed_compositions is not None:
            for name, comp in spec.seed_compositions.items():
                src = _render(comp)
                v, mean, se, lg = _score(src)
                branch = seed_branch_tags.get(name, "baseline")
                concepts = _concepts(comp)
                forest.append(Node(payload=comp, score=v, parent=None, logs=lg, mean=mean,
                                   se=se, branch=branch, concepts=concepts))
                if tracker is not None:
                    tracker.log_node(src, branch, concepts, v, mean, se, None, 0)
        else:
            for name, src in (spec.seed_programs or {}).items():
                v, mean, se, lg = _score(src)
                branch = seed_branch_tags.get(name, "baseline")
                concepts = _concepts(src)
                forest.append(Node(payload=src, score=v, parent=None, logs=lg, mean=mean,
                                   se=se, branch=branch, concepts=concepts))
                if tracker is not None:
                    tracker.log_node(src, branch, concepts, v, mean, se, None, 0)

    all_nodes: list[Node] = list(forest)
    branch_pool = list({n.branch for n in all_nodes if n.branch is not None})

    def _branch_template(branch):
        return rich_templates.get(branch or "baseline", rich_templates["baseline"])

    concept_keys = list(concept_taxonomy.keys()) if dimension_locked else []
    _dim_idx = 0
    _last_branch: str | None = None
    _branch_depth = 0

    def _generate_single_candidate(parent):
        nonlocal _dim_idx

        # Atomic mode: compositions instead of source strings
        if atomic_mode and isinstance(parent.payload, dict):
            parent_comp = sanitize(parent.payload)
            _parent_src = _render(parent_comp)

            if rng.random() < p_recombine and len(all_nodes) >= 2:
                parent_a, parent_b = _recombination_parents(all_nodes, c_branch, nprng)
                branch_a = parent_a.branch or "baseline"
                if verbose:
                    print(f"  [gen] atomic recombining {branch_a} + {parent_b.branch or 'baseline'}")
                child_comp, prior = recombine_atomic(
                    parent_a.payload, parent_a.score,
                    parent_b.payload, parent_b.score,
                    cache_dir=cache_dir,
                )
                child_branch = branch_a
                if not child_comp:
                    ops_a = parent_a.payload.get("operators", {})
                    ops_b = parent_b.payload.get("operators", {})
                    merged_ops = {**ops_a}
                    for slot, op in ops_b.items():
                        if slot not in merged_ops or rng.random() < 0.5:
                            merged_ops[slot] = op
                    child_comp = {
                        "skeleton": parent_a.payload.get("skeleton", "simple"),
                        "operators": merged_ops,
                        "params": {**parent_a.payload.get("params", {}), **parent_b.payload.get("params", {})},
                    }
                    prior = 0.5
                if verbose:
                    print(f"  [gen] atomic recombination done → {child_branch}")
                return child_comp, child_branch, prior

            force_jump = (
                _last_branch == parent.branch
                and _branch_depth >= branch_depth_limit
                and len(branch_pool) > 1
            )
            if force_jump or (rng.random() < p_cross_branch and len(branch_pool) > 1):
                other_branches = [b for b in branch_pool if b != parent.branch]
                target_branch = rng.choice(other_branches) if other_branches else parent.branch
            else:
                target_branch = parent.branch

            if dimension_locked and concept_keys:
                target_dim = concept_keys[_dim_idx % len(concept_keys)]
                _dim_idx += 1
                ops = parent_comp.get("operators", {})
                cat = concept_taxonomy.get(target_dim, ("", ""))[0]
                slot_map = {
                    "base": "base", "microstructure": "correction",
                    "calendar": "calendar", "volatility": "vol_adaptation",
                    "combination": "combination",
                }
                target_slot = slot_map.get(cat, "correction")
                if verbose:
                    print(f"  [gen] atomic propose [{target_branch}] slot={target_slot}→{target_dim} parent_val={parent.score:+.3f}")
                child_comp, prior = propose_atomic(
                    parent_comp, parent.score, target_slot, target_dim,
                    cache_dir=cache_dir,
                )
                if not child_comp:
                    child_comp = {
                        "skeleton": parent_comp.get("skeleton", "simple"),
                        "operators": {**ops, target_slot: target_dim},
                        "params": parent_comp.get("params", {}),
                    }
                    prior = 0.5
                child_branch = target_branch
                if verbose:
                    print(f"  [gen] atomic proposal done → {child_branch} prior={prior:.2f}")
                return child_comp, child_branch, prior

            if verbose:
                print(f"  [gen] atomic propose [{target_branch}] parent_val={parent.score:+.3f}")
            ops = parent_comp.get("operators", {})
            slots = list(ops.keys()) or ["base"]
            target_slot = rng.choice(slots)
            cat = concept_taxonomy.get(ops.get(target_slot, ""), ("", ""))[0]
            candidates = [c for c, (cat2, _) in concept_taxonomy.items() if cat2 == cat and c != ops.get(target_slot)]
            new_concept = rng.choice(candidates) if candidates else ops.get(target_slot)
            child_comp, prior = propose_atomic(
                parent_comp, parent.score, target_slot, new_concept,
                cache_dir=cache_dir,
            )
            if not child_comp:
                child_comp = {
                    "skeleton": parent_comp.get("skeleton", "simple"),
                    "operators": {**ops, target_slot: new_concept},
                    "params": parent_comp.get("params", {}),
                }
                prior = 0.5
            child_branch = target_branch
            if verbose:
                print(f"  [gen] atomic proposal done → {child_branch} prior={prior:.2f}")
            return child_comp, child_branch, prior

        # ── Legacy (non-atomic) path ──
        if rng.random() < p_recombine and len(all_nodes) >= 2:
            parent_a, parent_b = _recombination_parents(all_nodes, c_branch, nprng)
            branch_a = parent_a.branch or "baseline"
            branch_b = parent_b.branch or "baseline"
            if branch_a != branch_b and (branch_a, branch_b) in cross_branch_index:
                cross_text = cross_branch_index[(branch_a, branch_b)]
            else:
                cross_text = (
                    f"Combine these two programs. Parent A is from the {branch_a} branch; "
                    f"Parent B is from the {branch_b} branch."
                )
            if verbose:
                print(f"  [gen] recombining {branch_a} (val={parent_a.score:+.3f}) + {branch_b} (val={parent_b.score:+.3f})")
            child_src = recombine_branch(
                parent_a.payload, parent_a.score, branch_a,
                parent_b.payload, parent_b.score, branch_b,
                cross_text, cache_dir=cache_dir,
            )
            child_branch = branch_a
            if verbose:
                print(f"  [gen] recombination done → {child_branch}")
            return child_src, child_branch, 0.5  # recombination has no LLM prior

        force_jump = (
            _last_branch == parent.branch
            and _branch_depth >= branch_depth_limit
            and len(branch_pool) > 1
        )
        if force_jump or (rng.random() < p_cross_branch and len(branch_pool) > 1):
            other_branches = [b for b in branch_pool if b != parent.branch]
            target_branch = rng.choice(other_branches) if other_branches else parent.branch
        else:
            target_branch = parent.branch

        template = _branch_template(target_branch)

        if dimension_locked and concept_keys:
            target_dim = concept_keys[_dim_idx % len(concept_keys)]
            _dim_idx += 1
            if verbose:
                print(f"  [gen] propose [{target_branch}] dim={target_dim} parent_val={parent.score:+.3f}")
            child_src, prior = propose_dimension_locked(
                parent.payload, parent.score, parent.logs,
                branch=target_branch or "baseline",
                rich_template=template,
                target_dimension=target_dim,
                cache_dir=cache_dir,
            )
            child_branch = target_branch
            if verbose:
                print(f"  [gen] proposal done → {child_branch} prior={prior:.2f}")
            return child_src, child_branch, prior

        if use_llm_prior:
            if verbose:
                print(f"  [gen] propose [{target_branch}] parent_val={parent.score:+.3f} (with LLM prior)")
            child_src, prior = propose_branch_with_prior(
                parent.payload, parent.score, parent.logs,
                branch=target_branch or "baseline",
                rich_template=template,
                cache_dir=cache_dir,
            )
        else:
            if verbose:
                print(f"  [gen] propose [{target_branch}] parent_val={parent.score:+.3f}")
            child_src = propose_branch(
                parent.payload, parent.score, parent.logs,
                branch=target_branch or "baseline",
                rich_template=template,
                cache_dir=cache_dir,
            )
            prior = 0.5
        child_branch = target_branch
        if verbose:
            print(f"  [gen] proposal done → {child_branch} prior={prior:.2f}")
        return child_src, child_branch, prior

    def _try_self_correct(parent, failed_payload, error_log, branch):
        if not self_correct:
            return None
        failed_src = _render(failed_payload)
        template = _branch_template(branch)
        corrected = self_correct_fn(failed_src, error_log, branch, template, cache_dir=cache_dir)
        if not corrected.strip():
            return None
        child_payload = corrected
        if atomic_mode and isinstance(failed_payload, dict):
            recovered = extract_composition(corrected, failed_payload, cache_dir=cache_dir)
            if recovered:
                child_payload = recovered
        v, mean, se, lg = _score(corrected)
        concepts = _concepts(child_payload)
        return Node(payload=child_payload, score=v, parent=parent, logs=lg,
                    mean=mean, se=se, branch=branch, concepts=concepts)

    def _score_and_log(child_payload, child_branch, prior, parent):
        child_payload = sanitize(child_payload)
        child_src = _render(child_payload)
        v, mean, se, lg = _score(child_src)

        if v <= -1e6 + 1 and self_correct:
            if verbose:
                print(f"    [score] FAILED → attempting self-correction [{child_branch}]")
            sc = _try_self_correct(parent, child_payload, lg, child_branch)
            if sc is not None and sc.score > -1e6 + 1:
                child = sc
                child.prior_prob = prior
                all_nodes.append(child)
                if verbose:
                    print(f"    [score] SELF-CORRECTED → val={child.score:+.3f} [{child.branch}]")
                if archive is not None:
                    archive.save(_render(child.payload), child.score, child.mean, child.se, child.branch, parent, None)
                if tracker is not None:
                    tracker.log_node(_render(child.payload), child.branch, child.concepts or [],
                                     child.score, child.mean, child.se,
                                     parent_payload=_render(parent.payload) if parent else None,
                                     generation=len(all_nodes))
                return child
            if verbose:
                print(f"    [score] self-correction FAILED, giving up [{child_branch}]")

        concepts = _concepts(child_payload)
        child = Node(payload=child_payload, score=v, parent=parent, logs=lg,
                     mean=mean, se=se, branch=child_branch, concepts=concepts, prior_prob=prior)
        all_nodes.append(child)
        valid = v > -1e6 + 1
        if verbose:
            status = "VALID" if valid else "INVALID"
            print(f"    [score] {status} val={v:+.3f} [{child_branch}] concepts={concepts}")
        if archive is not None and valid:
            archive.save(child_src, v, mean, se, child_branch, parent, None)
        if tracker is not None:
            tracker.log_node(child_src, child_branch, concepts, v, mean, se,
                             parent_payload=_render(parent.payload) if parent else None,
                             generation=len(all_nodes))
        return child

    def expand(parent):
        nonlocal _last_branch, _branch_depth

        if parallel_expansions > 1:
            if verbose:
                print(f"  [expand] parallel={parallel_expansions} from [{parent.branch}] val={parent.score:+.3f}")
            candidates = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=parallel_expansions) as ex:
                futures = [ex.submit(_generate_single_candidate, parent)
                           for _ in range(parallel_expansions)]
                for fut in futures:
                    try:
                        candidates.append(fut.result())
                    except Exception as e:
                        print(f"[parallel expansion error] {e}")
            if not candidates:
                child_payload, child_branch, prior = _generate_single_candidate(parent)
                return _score_and_log(child_payload, child_branch, prior, parent)

            scored = []
            for child_payload, child_branch, prior in candidates:
                scored.append(_score_and_log(child_payload, child_branch, prior, parent))
            best = max(scored, key=lambda n: n.score)
            if verbose:
                scores = ", ".join(f"{n.score:+.3f}" for n in scored)
                print(f"  [expand] parallel results: [{scores}] → best={best.score:+.3f} [{best.branch}]")
            if _last_branch == best.branch:
                _branch_depth += 1
            else:
                _last_branch = best.branch
                _branch_depth = 1
            return best
        else:
            child_payload, child_branch, prior = _generate_single_candidate(parent)
            if _last_branch == child_branch:
                _branch_depth += 1
            else:
                _last_branch = child_branch
                _branch_depth = 1
            return _score_and_log(child_payload, child_branch, prior, parent)

    _expansion_count = 0

    def _expand_logged(parent):
        nonlocal _expansion_count
        _expansion_count += 1
        if verbose:
            print(f"[{_expansion_count}/{budget}] SELECT [{parent.branch}] val={parent.score:+.3f} visits={parent.visits} concepts={getattr(parent, 'concepts', [])}")
        child = expand(parent)
        if _expansion_count % 10 == 0 or _expansion_count == budget:
            valid = [n for n in all_nodes if n.score > -1e6 + 1]
            best = max((n.score for n in valid), default=float("-inf"))
            best_node = max(valid, key=lambda n: n.score) if valid else None
            branches: dict = {}
            for n in all_nodes:
                b = n.branch or "unknown"
                branches[b] = branches.get(b, 0) + 1
            print(f"\n[ERA progress] expansions={_expansion_count}/{budget}  nodes={len(all_nodes)}  "
                  f"valid={len(valid)}  best_score={best:.3f}  best_branch={best_node.branch if best_node else 'n/a'}  branches={branches}\n")
        return child

    branch_priors = None
    concept_priors = None
    synergy_fn = None
    if warm_start and tracker is not None:
        branch_priors = tracker.compute_branch_priors()
        if concept_mode:
            concept_priors = tracker.compute_concept_priors()
            synergy_fn = tracker.concept_synergy_bonus

    if select_policy == "thompson":
        def _select_fn(ns, c):
            return select_thompson(ns, nprng)
    elif select_policy == "diversity":
        if warm_start and branch_priors:
            warm_selector = select_diversity_with_llm_prior if use_llm_prior else select_diversity_with_history
            def _select_fn(ns, c):
                return warm_selector(
                    ns, c_puct=c, c_branch=c_branch,
                    branch_priors=branch_priors,
                    concept_priors=concept_priors,
                    concept_synergy_fn=synergy_fn,
                    rng=nprng,
                )
        else:
            plain_selector = select_diversity_with_llm_prior if use_llm_prior else select_diversity
            def _select_fn(ns, c):
                return plain_selector(ns, c_puct=c, c_branch=c_branch, rng=nprng)
    else:
        _select_fn = None

    nodes = puct_search(forest, _expand_logged, budget=budget, c_puct=1.0, seed=seed, select_fn=_select_fn)

    if tracker is not None:
        tracker.save_tree_state(nodes)

    return nodes
