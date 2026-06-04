from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import random
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from scripts.era.llm import (
    extract_composition_from_source,
    propose_atomic_change,
    propose_branch_program,
    propose_branch_program_with_prior,
    propose_dimension_locked_program,
    recombine_atomic_compositions,
    recombine_branch_program,
    self_correct_program,
)
from scripts.era.puct import (
    Node,
    puct_search,
    select_diversity,
    select_diversity_with_history,
    select_diversity_with_llm_prior,
    select_thompson,
)
from scripts.era_scalp.atomic_concepts import (
    CONCEPT_TAXONOMY,
    composition_to_source,
    extract_concepts_from_composition,
    extract_concepts_from_source,
)
from scripts.era_scalp.bayes_edge import edge_verdict
from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.cost_aware_score import (
    GRID_H,
    GRID_H_SHORT,
    GRID_Q,
    CostAwarePerSymbolScorer,
)
from scripts.era_scalp.cost_model import realistic_cost
from scripts.era_scalp.fade_seeds import (
    CROSS_BRANCH_INDEX as FADE_CROSS_BRANCH_INDEX,
)
from scripts.era_scalp.fade_seeds import (
    FADE_SEED_PROGRAMS,
)
from scripts.era_scalp.fade_seeds import (
    RICH_TEMPLATES as FADE_RICH_TEMPLATES,
)
from scripts.era_scalp.fade_seeds import (
    SEED_BRANCH_TAGS as FADE_SEED_BRANCH_TAGS,
)
from scripts.era_scalp.fair_seeds import (
    CROSS_BRANCH_INDEX as FAIR_CROSS_BRANCH_INDEX,
)
from scripts.era_scalp.fair_seeds import (
    FAIR_SEED_COMPOSITIONS,
    FAIR_SEED_PROGRAMS,
)
from scripts.era_scalp.fair_seeds import (
    RICH_TEMPLATES as FAIR_RICH_TEMPLATES,
)
from scripts.era_scalp.fair_seeds import (
    SEED_BRANCH_TAGS as FAIR_SEED_BRANCH_TAGS,
)
from scripts.era_scalp.load_splits import _pip_size, build_trade_splits
from scripts.era_scalp.sandbox import run_program
from scripts.era_scalp.trade_harness import evaluate_fair_price_trades, evaluate_trades
from scripts.era_scalp.tree_tracker import TreeTracker


class WinnerArchive:
    """Persist evolved programs that score above a threshold.

    Programs are written to data/era_winners/{symbol}/{timestamp}_{score}_{branch}_{hash}.py
    with YAML frontmatter containing score, holdout stats, and parent lineage.
    """

    def __init__(self, symbol: str, threshold: float = -0.5,
                 root: Path | None = None):
        self.symbol = symbol
        self.threshold = threshold
        self.root = root or Path("data/era_winners")
        self.dir = self.root / symbol
        self.dir.mkdir(parents=True, exist_ok=True)
        self._seen: set[str] = set()

    def _key(self, src: str) -> str:
        return hashlib.sha256(src.encode()).hexdigest()[:12]

    def save(self, src: str, score: float, mean: float, se: float,
             branch: str | None, parent: Node | None,
             holdout: dict | None = None) -> Path | None:
        """Save program if score > threshold and not already saved."""
        if score <= self.threshold:
            return None
        key = self._key(src)
        if key in self._seen:
            return None
        self._seen.add(key)

        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        fname = f"{ts}_val{score:+.3f}_{branch or 'unknown'}_{key}.py"
        path = self.dir / fname

        meta = {
            "symbol": self.symbol,
            "score": float(score),
            "mean": float(mean),
            "se": float(se),
            "branch": branch,
            "parent_score": float(parent.score) if parent else None,
            "parent_branch": parent.branch if parent else None,
            "holdout": holdout,
            "timestamp": ts,
        }

        lines = [
            '"""',
            json.dumps(meta, indent=2, default=str),
            '"""',
            "",
            src,
        ]
        path.write_text("\n".join(lines))
        print(f"[archive] saved {path}")
        return path


SYMBOL_DEFAULT = "EURUSD"
TRIVIAL_ROOT = (
    "def signal(ctx):\n"
    "    return ctx.col('vel_pips_h1') * 0.0 + ctx.col('vel_pips_h1')\n"
)

FAIR_TRIVIAL_ROOT = (
    "def estimate_fair(ctx):\n"
    "    r = ctx.col('vel_pips_h1'); n = r.shape[0]; a = 0.02\n"
    "    p = np.cumsum(np.where(np.isfinite(r), r, 0.0))\n"
    "    ew = np.empty(n); acc = p[0]\n"
    "    for i in range(n):\n"
    "        acc = (1 - a) * acc + a * p[i]; ew[i] = acc\n"
    "    return ew\n"
)


def run_search(splits, symbol, budget, select_policy="diversity", seed=0,
               cache_dir="/tmp/era_eur_cache", p_recombine=0.25, p_cross_branch=0.35,
               c_branch=0.7, branch_depth_limit=3, seed_programs=None, archive=None,
               fair_price_mode: bool = False,
               tracker: TreeTracker | None = None,
               warm_start: bool = False,
               concept_mode: bool = False,
               dimension_locked: bool = False,
               self_correct: bool = False,
               parallel_expansions: int = 1,
               use_llm_prior: bool = False,
               resume_tree: bool = False,
               verbose: bool = False,
               atomic_mode: bool = False):
    """Branch-aware ERA-PUCT search with zarrduck-inspired improvements.

    New features
    ------------
    dimension_locked : bool
        When proposing (not recombining), force the LLM to make exactly ONE atomic
        tweak in a specific dimension (e.g. 'roll_bounce', 'barzykin_impact').
        Dimensions cycle through CONCEPT_TAXONOMY keys.
    self_correct : bool
        When sandbox/static_check rejects a candidate, send the error log + parent
        baseline back to the LLM for 1-2 repair attempts before giving up.
    parallel_expansions : int
        Generate this many candidate programs in parallel per PUCT step (using
        ThreadPoolExecutor), evaluate all, and keep the best-scoring child.
        Budget is interpreted as total PUCT steps, not total LLM calls.
    use_llm_prior : bool
        Ask the LLM to self-assess confidence (0-1) for each proposal.  The prior
        feeds into the PUCT exploration bonus, focusing search on high-confidence
        proposals.  Uses select_diversity_with_llm_prior.
    resume_tree : bool
        If tracker has a saved tree state (from a previous interrupted run), load
        it and resume search from the frontier instead of rebuilding from seeds.
    verbose : bool
        Print detailed progress messages for every expansion (branch selected,
        score result, self-correction attempts, archive saves, etc.).
    atomic_mode : bool
        If True, Node payloads store atomic concept *compositions* (skeleton +
        operators + params) instead of complete source code.  The LLM proposes by
        swapping ONE operator slot; recombination merges slots from two parents.
        Programs are rendered from compositions before scoring.
    """
    scorer = CostAwarePerSymbolScorer(splits, symbol, fair_price_mode=fair_price_mode)
    rng = random.Random(seed)
    nprng = np.random.default_rng(seed)

    seed_branch_tags = FAIR_SEED_BRANCH_TAGS if fair_price_mode else FADE_SEED_BRANCH_TAGS
    rich_templates = FAIR_RICH_TEMPLATES if fair_price_mode else FADE_RICH_TEMPLATES
    cross_branch_index = FAIR_CROSS_BRANCH_INDEX if fair_price_mode else FADE_CROSS_BRANCH_INDEX

    # ── Payload rendering helper ────────────────────────────────────────────
    def _render_payload(payload) -> str:
        """Render node payload to source string (atomic mode = composition dict)."""
        if atomic_mode and isinstance(payload, dict):
            return composition_to_source(payload)
        return str(payload)

    def _extract_concepts(payload) -> list[str]:
        """Extract concept tags from payload."""
        if atomic_mode and isinstance(payload, dict):
            return extract_concepts_from_composition(payload)
        if concept_mode:
            return extract_concepts_from_source(str(payload))
        return []

    # ── Optional: resume from saved tree state ───────────────────────────────
    forest: list[Node] = []
    if resume_tree and tracker is not None:
        resumed = tracker.load_tree_state()
        if resumed:
            forest = [n for n in resumed if n.parent is None]
            print(f"[resume] loaded {len(resumed)} nodes ({len(forest)} roots) from tree state")

    if not forest:
        if atomic_mode and fair_price_mode:
            # Atomic mode: load seed compositions
            seed_compositions = FAIR_SEED_COMPOSITIONS
            if seed_programs is not None:
                # Map seed_programs dict keys to compositions
                seed_compositions = {k: FAIR_SEED_COMPOSITIONS.get(k, {"skeleton": "simple", "operators": {"base": "slow_ewma"}, "params": {}})
                                     for k in seed_programs}
            for name, comp in seed_compositions.items():
                src = composition_to_source(comp)
                v, mean, se, lg = scorer.score(src, "validation")
                branch = seed_branch_tags.get(name, "baseline")
                concepts = _extract_concepts(comp)
                node = Node(payload=comp, score=v, parent=None, logs=lg, mean=mean, se=se, branch=branch, concepts=concepts)
                forest.append(node)
                if tracker is not None:
                    tracker.log_node(src, branch, concepts, v, mean, se, None, 0)
        else:
            # Legacy mode: load complete source strings
            if seed_programs is None:
                seed_programs = FAIR_SEED_PROGRAMS if fair_price_mode else FADE_SEED_PROGRAMS
            for name, src in seed_programs.items():
                v, mean, se, lg = scorer.score(src, "validation")
                branch = seed_branch_tags.get(name, "baseline")
                concepts = _extract_concepts(src)
                node = Node(payload=src, score=v, parent=None, logs=lg, mean=mean, se=se, branch=branch, concepts=concepts)
                forest.append(node)
                if tracker is not None:
                    tracker.log_node(src, branch, concepts, v, mean, se, None, 0)

    all_nodes: list[Node] = list(forest)

    # Collect branch list for cross-branch jumps
    branch_pool = list(set(n.branch for n in all_nodes if n.branch is not None))

    def _branch_template(branch: str | None) -> str:
        return rich_templates.get(branch or "baseline", rich_templates["baseline"])

    # Dimension-locking state: cycle through atomic concept keys
    concept_keys = list(CONCEPT_TAXONOMY.keys()) if dimension_locked else []
    _dim_idx = 0

    # Track consecutive expansions within the same branch
    _last_branch: str | None = None
    _branch_depth: int = 0

    # ── Inner expansion logic ───────────────────────────────────────────────

    def _generate_single_candidate(parent: Node) -> tuple[object, str, float]:
        """Generate one candidate program or composition.

        Returns (payload, branch, prior_prob).
        In atomic_mode payload is a composition dict; otherwise a source string.
        """
        nonlocal _dim_idx

        # Atomic mode: compositions instead of source strings
        if atomic_mode and isinstance(parent.payload, dict):
            parent_comp = parent.payload
            _parent_src = _render_payload(parent_comp)

            # Decide: recombine vs propose
            if rng.random() < p_recombine and len(all_nodes) >= 2:
                cands = sorted(all_nodes, key=lambda n: n.score, reverse=True)
                parent_a = cands[0]
                parent_b = next(
                    (n for n in cands[1:] if n.branch != parent_a.branch), cands[1]
                )
                branch_a = parent_a.branch or "baseline"
                branch_b = parent_b.branch or "baseline"
                if verbose:
                    print(f"  [gen] atomic recombining {branch_a} + {branch_b}")
                child_comp, prior = recombine_atomic_compositions(
                    parent_a.payload, parent_a.score,
                    parent_b.payload, parent_b.score,
                    cache_dir=cache_dir,
                )
                child_branch = branch_a
                if not child_comp:
                    # Fallback: deterministic merge of operator dicts
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

            # Propose: change ONE operator slot
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
                # Find which slot could hold this dimension
                ops = parent_comp.get("operators", {})
                cat = CONCEPT_TAXONOMY.get(target_dim, ("", ""))[0]
                slot_map = {
                    "base": "base", "microstructure": "correction",
                    "calendar": "calendar", "volatility": "vol_adaptation",
                    "combination": "combination",
                }
                target_slot = slot_map.get(cat, "correction")
                if verbose:
                    print(f"  [gen] atomic propose [{target_branch}] slot={target_slot}→{target_dim} parent_val={parent.score:+.3f}")
                child_comp, prior = propose_atomic_change(
                    parent_comp, parent.score, target_slot, target_dim,
                    cache_dir=cache_dir,
                )
                if not child_comp:
                    # Fallback: deterministic slot swap
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

            # Non-dimension-locked atomic propose: ask LLM to improve any slot
            if verbose:
                print(f"  [gen] atomic propose [{target_branch}] parent_val={parent.score:+.3f}")
            # Pick a random slot to mutate
            ops = parent_comp.get("operators", {})
            slots = list(ops.keys()) or ["base"]
            target_slot = rng.choice(slots)
            # Pick a random concept from the same category
            cat = CONCEPT_TAXONOMY.get(ops.get(target_slot, ""), ("", ""))[0]
            candidates = [c for c, (cat2, _) in CONCEPT_TAXONOMY.items() if cat2 == cat and c != ops.get(target_slot)]
            new_concept = rng.choice(candidates) if candidates else ops.get(target_slot)
            child_comp, prior = propose_atomic_change(
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

        # ── Legacy (non-atomic) path ──────────────────────────────────────────
        # Decide: recombine vs propose
        if rng.random() < p_recombine and len(all_nodes) >= 2:
            cands = sorted(all_nodes, key=lambda n: n.score, reverse=True)
            parent_a = cands[0]
            parent_b = next(
                (n for n in cands[1:] if n.branch != parent_a.branch), cands[1]
            )
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
            child_src = recombine_branch_program(
                parent_a.payload, parent_a.score, branch_a,
                parent_b.payload, parent_b.score, branch_b,
                cross_text, cache_dir=cache_dir,
            )
            child_branch = branch_a
            if verbose:
                print(f"  [gen] recombination done → {child_branch}")
            return child_src, child_branch, 0.5  # recombination has no LLM prior

        # Propose: stay in branch or jump
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
            if use_llm_prior:
                child_src, prior = propose_dimension_locked_program(
                    parent.payload, parent.score, parent.logs,
                    branch=target_branch or "baseline",
                    rich_template=template,
                    target_dimension=target_dim,
                    cache_dir=cache_dir,
                )
            else:
                child_src, prior = propose_dimension_locked_program(
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
            child_src, prior = propose_branch_program_with_prior(
                parent.payload, parent.score, parent.logs,
                branch=target_branch or "baseline",
                rich_template=template,
                cache_dir=cache_dir,
            )
        else:
            if verbose:
                print(f"  [gen] propose [{target_branch}] parent_val={parent.score:+.3f}")
            child_src = propose_branch_program(
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

    def _try_self_correct(parent: Node, failed_payload, error_log: str, branch: str) -> Node | None:
        """Ask LLM to repair a failed candidate. Returns new Node or None."""
        if not self_correct:
            return None
        # Always work with source strings for self-correction
        failed_src = _render_payload(failed_payload)
        template = _branch_template(branch)
        corrected = self_correct_program(failed_src, error_log, branch, template, cache_dir=cache_dir)
        if not corrected.strip():
            return None
        # In atomic mode, try to preserve composition dicts so descendants remain atomic
        child_payload = corrected
        if atomic_mode and isinstance(failed_payload, dict):
            recovered = extract_composition_from_source(corrected, failed_payload, cache_dir=cache_dir)
            if recovered:
                child_payload = recovered
        v, mean, se, lg = scorer.score(corrected, "validation")
        concepts = _extract_concepts(child_payload)
        child = Node(
            payload=child_payload, score=v, parent=parent, logs=lg,
            mean=mean, se=se, branch=branch, concepts=concepts,
        )
        return child

    def _score_and_log(child_payload, child_branch: str, prior: float,
                         parent: Node) -> Node:
        """Score a candidate (rendered from composition if atomic), apply self-correction, log, and return Node."""
        child_src = _render_payload(child_payload)
        v, mean, se, lg = scorer.score(child_src, "validation")

        # Self-correction: if program failed, try once to fix it
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
                    archive.save(_render_payload(child.payload), child.score, child.mean, child.se, child.branch, parent, None)
                if tracker is not None:
                    tracker.log_node(_render_payload(child.payload), child.branch, child.concepts or [],
                                     child.score, child.mean, child.se,
                                     parent_payload=_render_payload(parent.payload) if parent else None,
                                     generation=len(all_nodes))
                return child
            if verbose:
                print(f"    [score] self-correction FAILED, giving up [{child_branch}]")

        concepts = _extract_concepts(child_payload)
        child = Node(
            payload=child_payload, score=v, parent=parent, logs=lg,
            mean=mean, se=se, branch=child_branch, concepts=concepts,
            prior_prob=prior,
        )
        all_nodes.append(child)
        valid = v > -1e6 + 1
        if verbose:
            status = "VALID" if valid else "INVALID"
            print(f"    [score] {status} val={v:+.3f} [{child_branch}] concepts={concepts}")
        if archive is not None and valid:
            archive.save(child_src, v, mean, se, child_branch, parent, None)
        if tracker is not None:
            tracker.log_node(child_src, child_branch, concepts, v, mean, se,
                             parent_payload=_render_payload(parent.payload) if parent else None,
                             generation=len(all_nodes))
        return child

    def expand(parent: Node) -> Node:
        nonlocal _last_branch, _branch_depth

        if parallel_expansions > 1:
            if verbose:
                print(f"  [expand] parallel={parallel_expansions} from [{parent.branch}] val={parent.score:+.3f}")
            # Generate N candidates in parallel, pick best
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
                # Fallback: generate one synchronously
                child_payload, child_branch, prior = _generate_single_candidate(parent)
                return _score_and_log(child_payload, child_branch, prior, parent)

            # Score all candidates (some may be cached, most won't be)
            scored = []
            for child_payload, child_branch, prior in candidates:
                node = _score_and_log(child_payload, child_branch, prior, parent)
                scored.append(node)
            # Return best-scoring child for PUCT continuation
            best = max(scored, key=lambda n: n.score)
            if verbose:
                scores = ", ".join(f"{n.score:+.3f}" for n in scored)
                print(f"  [expand] parallel results: [{scores}] → best={best.score:+.3f} [{best.branch}]")
            # Update branch-depth tracker so parallel expansions count toward depth limits
            if _last_branch == best.branch:
                _branch_depth += 1
            else:
                _last_branch = best.branch
                _branch_depth = 1
            return best
        else:
            child_payload, child_branch, prior = _generate_single_candidate(parent)
            # Update branch-depth tracker
            if _last_branch == child_branch:
                _branch_depth += 1
            else:
                _last_branch = child_branch
                _branch_depth = 1
            return _score_and_log(child_payload, child_branch, prior, parent)

    # Progress logging
    _expansion_count = 0

    def _expand_logged(parent: Node) -> Node:
        nonlocal _expansion_count
        _expansion_count += 1
        if verbose:
            print(f"[{_expansion_count}/{budget}] SELECT [{parent.branch}] val={parent.score:+.3f} visits={parent.visits} concepts={getattr(parent, 'concepts', [])}")
        child = expand(parent)
        if _expansion_count % 10 == 0 or _expansion_count == budget:
            valid = [n for n in all_nodes if n.score > -1e6 + 1]
            best = max((n.score for n in valid), default=float("-inf"))
            best_node = max(valid, key=lambda n: n.score) if valid else None
            branches = {}
            for n in all_nodes:
                b = n.branch or "unknown"
                branches[b] = branches.get(b, 0) + 1
            print(f"\n[ERA progress] expansions={_expansion_count}/{budget}  nodes={len(all_nodes)}  "
                  f"valid={len(valid)}  best_score={best:.3f}  best_branch={best_node.branch if best_node else 'n/a'}  branches={branches}\n")
        return child

    # Selection function
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
            # Both prior-aware variants accept branch_priors/concept_priors/concept_synergy_fn.
            # Use a distinct name so the closure captures only this narrower type (not the
            # plain select_diversity from the else-branch, which lacks those kwargs).
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
        _select_fn = None  # default rank-based select

    nodes = puct_search(forest, _expand_logged, budget=budget, c_puct=1.0, seed=seed, select_fn=_select_fn)

    # Save tree state for resumption
    if tracker is not None:
        tracker.save_tree_state(nodes)

    return nodes


def holdout_verdict(src, split_holdout, symbol, fair_price_mode: bool = False):
    """Net-of-realistic-cost EUR holdout posterior at the best-by-(q,h) cell. None on program error."""
    d = split_holdout
    ctx = FeatureContext(X=d.X, names=d.names, hour=d.hour)
    required_fn = "estimate_fair" if fair_price_mode else "signal"
    out, err, _ = run_program(src, ctx, required_fn=required_fn)
    if err is not None:
        return None
    cost = realistic_cost(d.spread_pips)
    pip = _pip_size(symbol)
    grid_h = GRID_H_SHORT if fair_price_mode else GRID_H
    best = None
    for q in GRID_Q:
        for h in grid_h:
            if fair_price_mode:
                frame = evaluate_fair_price_trades(out, d.mid, cost, d.test_month, pip, q, h)
            else:
                frame = evaluate_trades(out, d.mid, cost, d.test_month, pip, q, h)
            if len(frame) < 50:
                continue
            try:
                post = edge_verdict({symbol: frame})
            except ValueError:
                continue
            p = post.pooled["p_positive"]
            if best is None or p > best["p_positive"]:
                best = {**post.pooled, "q": q, "h": h, "n_trades": int(len(frame)),
                        "raw_mean": float(frame["net"].mean())}
    return best


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default=SYMBOL_DEFAULT)
    ap.add_argument("--tv-dir", default="data/analysis/tick_velocity")
    ap.add_argument("--budget", type=int, default=40)
    ap.add_argument("--policy", default="diversity",
                    choices=["thompson", "rank", "diversity"],
                    help="selection policy: thompson=posterior sampling, rank=UCB, "
                         "diversity=branch-aware UCB with exploration bonus")
    ap.add_argument("--no-seeds", action="store_true", help="rediscovery control")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default="/tmp/era_eur/verdict.md")
    ap.add_argument("--c-branch", type=float, default=0.7,
                    help="diversity bonus weight for branch-aware selection (default 0.7)")
    ap.add_argument("--p-recombine", type=float, default=0.25,
                    help="probability of cross-parent recombination vs single-parent propose (default 0.25)")
    ap.add_argument("--p-cross-branch", type=float, default=0.35,
                    help="probability of jumping to a different branch's template on propose (default 0.35)")
    ap.add_argument("--branch-depth-limit", type=int, default=3,
                    help="max consecutive expansions within the same branch before forcing a cross-branch jump (default 3)")
    ap.add_argument("--archive-threshold", type=float, default=-0.5,
                    help="save programs with validation score above this threshold to data/era_winners/ (default -0.5)")
    ap.add_argument("--fair-price", action="store_true",
                    help="fair-price mode: programs define estimate_fair(ctx) and we trade on deviations (h=1-20)")
    ap.add_argument("--warm-start", action="store_true",
                    help="load historical branch/concept priors from data/era_trees/ to bias selection")
    ap.add_argument("--concept-mode", action="store_true",
                    help="extract atomic concepts from programs and enable concept-level warm-start priors")
    ap.add_argument("--dimension-locked", action="store_true",
                    help="force LLM to make exactly ONE atomic tweak per proposal (cycles through concept dimensions)")
    ap.add_argument("--self-correct", action="store_true",
                    help="when sandbox rejects a candidate, send error log + parent back to LLM for repair")
    ap.add_argument("--parallel-expansions", type=int, default=1,
                    help="generate N candidates in parallel per PUCT step and keep the best (default 1)")
    ap.add_argument("--use-llm-prior", action="store_true",
                    help="ask LLM for self-assessed confidence (0-1) and use it in PUCT exploration bonus")
    ap.add_argument("--resume-tree", action="store_true",
                    help="resume from saved tree state instead of rebuilding from seeds")
    ap.add_argument("--verbose", action="store_true",
                    help="print detailed progress for every expansion (branch selected, score result, self-correction, etc.)")
    ap.add_argument("--atomic-mode", action="store_true",
                    help="store atomic concept compositions instead of full source; LLM tweaks one operator slot at a time")
    args = ap.parse_args()
    grid_h = GRID_H_SHORT if args.fair_price else GRID_H
    # For fair-price mode, score on all historical data (2018-2024) so the Bayesian
    # monthly-net posterior has ~84 months of statistical power.  Holdout stays 2025-26.
    if args.fair_price:
        sp = build_trade_splits(
            args.symbol, Path(args.tv_dir) / f"{args.symbol}_100tick_velocity.parquet",
            embargo=max(grid_h),
            train=("2018", "2019", "2020", "2021", "2022", "2023"),
            validation=("2018", "2019", "2020", "2021", "2022", "2023", "2024"),
            holdout=("2025", "2026"),
        )
    else:
        sp = build_trade_splits(args.symbol, Path(args.tv_dir) / f"{args.symbol}_100tick_velocity.parquet",
                                embargo=max(grid_h))
    if args.no_seeds:
        seed_programs = {"_root": FAIR_TRIVIAL_ROOT if args.fair_price else TRIVIAL_ROOT}
    else:
        seed_programs = None
    archive = WinnerArchive(args.symbol, threshold=args.archive_threshold)
    tracker = TreeTracker(args.symbol) if (args.warm_start or args.concept_mode or args.resume_tree) else None
    if tracker is not None:
        tracker.start_run(budget=args.budget, seed=args.seed, mode="fair_price" if args.fair_price else "fade",
                          extra_meta={"dimension_locked": args.dimension_locked,
                                      "parallel_expansions": args.parallel_expansions,
                                      "use_llm_prior": args.use_llm_prior})

    nodes = run_search(sp, args.symbol, budget=args.budget, select_policy=args.policy,
                       seed=args.seed, seed_programs=seed_programs,
                       p_recombine=args.p_recombine, p_cross_branch=args.p_cross_branch,
                       c_branch=args.c_branch, branch_depth_limit=args.branch_depth_limit,
                       archive=archive, fair_price_mode=args.fair_price,
                       tracker=tracker, warm_start=args.warm_start, concept_mode=args.concept_mode,
                       dimension_locked=args.dimension_locked, self_correct=args.self_correct,
                       parallel_expansions=args.parallel_expansions,
                       use_llm_prior=args.use_llm_prior, resume_tree=args.resume_tree,
                       verbose=args.verbose, atomic_mode=args.atomic_mode)
    ranked = sorted([n for n in nodes if n.score > -1e6 + 1], key=lambda n: n.score, reverse=True)
    # Deduplicate by payload so the same generated program doesn't dominate the top-5 display.
    seen_payloads: set[str] = set()
    unique_ranked = []
    for nd in ranked:
        payload_key = json.dumps(nd.payload, sort_keys=True) if isinstance(nd.payload, dict) else nd.payload
        if payload_key not in seen_payloads:
            seen_payloads.add(payload_key)
            unique_ranked.append(nd)
    mode_label = "fair-price" if args.fair_price else "cost-aware"
    flags = []
    if args.dimension_locked:
        flags.append("dim-locked")
    if args.self_correct:
        flags.append("self-correct")
    if args.use_llm_prior:
        flags.append("llm-prior")
    if args.parallel_expansions > 1:
        flags.append(f"parallel={args.parallel_expansions}")
    if args.atomic_mode:
        flags.append("atomic")
    flags_str = f" | {','.join(flags)}" if flags else ""
    lines = [f"# {mode_label} PUCT verdict — {args.symbol} (policy={args.policy}, "
             f"seeds={'no' if args.no_seeds else 'yes'}, budget={args.budget}{flags_str})\n"]
    for nd in unique_ranked[:5]:
        src = composition_to_source(nd.payload) if isinstance(nd.payload, dict) else nd.payload
        hv = holdout_verdict(src, sp["holdout"], args.symbol, fair_price_mode=args.fair_price)
        tag = "SEED" if nd.parent is None else "evolved"
        branch_tag = f"[{nd.branch}]" if nd.branch else ""
        if hv:
            lines.append(f"- [{tag}] {branch_tag} val={nd.score:+.3f} | holdout P={hv['p_positive']:.3f} "
                         f"raw={hv['raw_mean']:+.3f} (q{hv['q']} h{hv['h']} n={hv['n_trades']})")
            # Archive top-5 holdout results as well
            archive.save(src, nd.score, nd.mean, nd.se, nd.branch, nd.parent, hv)
            # Log holdout to tracker for concept-level posterior updates
            if tracker is not None:
                tracker.log_node(src, nd.branch or "unknown", nd.concepts or [],
                                 nd.score, nd.mean, nd.se,
                                 parent_payload=(composition_to_source(nd.parent.payload) if isinstance(nd.parent.payload, dict) else nd.parent.payload) if nd.parent else None,
                                 generation=0, holdout_p=hv.get("p_positive"), holdout_raw=hv.get("raw_mean"))
        else:
            lines.append(f"- [{tag}] {branch_tag} val={nd.score:+.3f} | holdout: program error")
    if tracker is not None:
        tracker.end_run(extra_meta={"best_val": float(unique_ranked[0].score) if unique_ranked else None})
        summary = tracker.summary()
        lines.append("\n## TreeTracker summary")
        lines.append(f"- branches tracked: {summary['branches_tracked']}")
        lines.append(f"- concepts tracked: {summary['concepts_tracked']}")
        if summary['top_branches']:
            lines.append("- top branches: " + ", ".join(f"{b}({s:.2f})" for b, s, _ in summary['top_branches']))
        if summary['top_concepts']:
            lines.append("- top concepts: " + ", ".join(f"{c}({s:.2f})" for c, s, _ in summary['top_concepts'][:5]))
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join(lines) + "\n")
    print(f"wrote {args.out}")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
