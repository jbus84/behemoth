from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import replace
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
    fast_lower_bound,
)
from scripts.era_scalp.cost_model import realistic_cost
from scripts.era_scalp.deflated_selection import (
    deflated_edge_prob,
    is_significant_after_deflation,
)
from scripts.era_scalp.era_engine import run_search_rich, scoring_spec
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
from scripts.era_scalp.load_splits import TradeSplitData, _pip_size, build_trade_splits
from scripts.era_scalp.sandbox import run_program
from scripts.era_scalp.temporal_robustness import (
    is_temporally_robust,
    temporal_robustness_verdict,
)
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


def _sanitize_composition(comp):
    """Coerce a composition's operator values to op-name strings.

    LLM recombination occasionally emits a list (or other non-string) for a slot's
    operator; a list value is unhashable and crashes CONCEPT_TAXONOMY / _ALL_OPERATORS
    lookups downstream. Keep string values, flatten a non-empty list/tuple to its first
    string element, drop anything else. Non-dict payloads (source strings) pass through."""
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
            # else: drop the slot
        comp = {**comp, "operators": clean}
    return comp


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
    spec = _build_run_spec(
        splits, symbol, fair_price_mode=fair_price_mode, seed_programs=seed_programs,
        tracker=tracker, archive=archive, atomic_mode=atomic_mode,
        dimension_locked=dimension_locked, self_correct=self_correct,
        use_llm_prior=use_llm_prior, parallel_expansions=parallel_expansions,
        branch_depth_limit=branch_depth_limit, p_cross_branch=p_cross_branch,
        p_recombine=p_recombine, c_branch=c_branch, concept_mode=concept_mode,
        verbose=verbose,
    )
    return run_search_rich(
        spec, splits, budget=budget, seed=seed, cache_dir=cache_dir,
        select_policy=select_policy, warm_start=warm_start,
        concept_mode=concept_mode, resume_tree=resume_tree,
    )


def _build_run_spec(splits, symbol, *, fair_price_mode, seed_programs, tracker, archive,
                    atomic_mode, dimension_locked, self_correct, use_llm_prior,
                    parallel_expansions, branch_depth_limit, p_cross_branch, p_recombine,
                    c_branch, concept_mode, verbose):
    """Layer run_era_eur's writers / seeds / constants / flags onto the shared scoring spec
    (era_engine.scoring_spec) so the engine (run_search_rich) drives the search. Scoring is
    parity-equivalent to the retired CostAwarePerSymbolScorer (#316)."""
    if fair_price_mode:
        rich_templates, cross_branch_index = FAIR_RICH_TEMPLATES, FAIR_CROSS_BRANCH_INDEX
        seed_branch_tags = FAIR_SEED_BRANCH_TAGS
    else:
        rich_templates, cross_branch_index = FADE_RICH_TEMPLATES, FADE_CROSS_BRANCH_INDEX
        seed_branch_tags = FADE_SEED_BRANCH_TAGS

    # Resolve seeds (mirrors the legacy run_search seed-loading branch)
    seed_compositions = None
    spec_seed_programs = seed_programs
    if atomic_mode and fair_price_mode:
        seed_compositions = FAIR_SEED_COMPOSITIONS
        if seed_programs is not None:
            seed_compositions = {
                k: FAIR_SEED_COMPOSITIONS.get(k, {"skeleton": "simple", "operators": {"base": "slow_ewma"}, "params": {}})
                for k in seed_programs
            }
        spec_seed_programs = None
    elif seed_programs is None:
        spec_seed_programs = FAIR_SEED_PROGRAMS if fair_price_mode else FADE_SEED_PROGRAMS

    def extract_concepts(payload):
        if atomic_mode and isinstance(payload, dict):
            return extract_concepts_from_composition(payload)
        if concept_mode:
            return extract_concepts_from_source(str(payload))
        return []

    return replace(
        scoring_spec(symbol, fair_price_mode=fair_price_mode),
        seed_programs=spec_seed_programs, seed_compositions=seed_compositions,
        branch_tags=seed_branch_tags, rich_templates=rich_templates,
        cross_branch_index=cross_branch_index, concept_taxonomy=CONCEPT_TAXONOMY,
        render_payload=composition_to_source, sanitize_composition=_sanitize_composition,
        extract_concepts=extract_concepts,
        propose_branch=propose_branch_program,
        propose_branch_with_prior=propose_branch_program_with_prior,
        propose_dimension_locked=propose_dimension_locked_program,
        propose_atomic=propose_atomic_change,
        recombine_branch=recombine_branch_program,
        recombine_atomic=recombine_atomic_compositions,
        self_correct_fn=self_correct_program,
        extract_composition=extract_composition_from_source,
        tracker=tracker, archive=archive,
        atomic_mode=atomic_mode, dimension_locked=dimension_locked,
        self_correct=self_correct, use_llm_prior=use_llm_prior,
        parallel_expansions=parallel_expansions, branch_depth_limit=branch_depth_limit,
        p_cross_branch=p_cross_branch, p_recombine=p_recombine, c_branch=c_branch,
        verbose=verbose,
    )


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


def _concat_trade_splits(a, b):
    """Concatenate two TradeSplitData (time-ordered a then b) for the temporal gate."""
    return TradeSplitData(
        X=np.concatenate([a.X, b.X], axis=0),
        names=a.names,
        hour=None if (a.hour is None or b.hour is None) else np.concatenate([a.hour, b.hour]),
        mid=np.concatenate([a.mid, b.mid]),
        cost=np.concatenate([a.cost, b.cost]),
        test_month=np.concatenate([a.test_month, b.test_month]),
        spread_pips=None if (a.spread_pips is None or b.spread_pips is None)
        else np.concatenate([a.spread_pips, b.spread_pips]),
    )


def _temporal_tiebreak(nodes, verdict_by_id):
    """Sort nodes by (validation score rounded to 2 dp, then worst-window P(edge>0)),
    so robustness breaks near-equal-score ties. Missing/insufficient verdicts sort last."""
    def key(nd):
        v = verdict_by_id.get(id(nd))
        wwp = v["worst_window_p_positive"] if v and v.get("status") == "ok" else -1.0
        return (round(nd.score, 2), wwp)
    return sorted(nodes, key=key, reverse=True)


def _velocity_path(tv_dir, symbol: str, bar: str = "100tick") -> Path:
    """Path to a symbol's velocity parquet for a given bar length (e.g. '100tick', '1000tick')."""
    return Path(tv_dir) / f"{symbol}_{bar}_velocity.parquet"


def temporal_annotation(payload, sp, symbol, *, fair_price_mode: bool = False, min_trades=50,
                        num_warmup=400, num_samples=400, num_chains=2):
    """Per-symbol temporal-robustness verdict on the combined train+validation span at the
    program's best-by-(q,h) cell. Renders atomic-composition dict payloads to source and uses
    the correct entry fn / trade evaluator for the mode. None on program error / no admissible cell."""
    src = composition_to_source(payload) if isinstance(payload, dict) else payload
    required_fn = "estimate_fair" if fair_price_mode else "signal"
    tv = _concat_trade_splits(sp["train"], sp["validation"])
    ctx = FeatureContext(X=tv.X, names=tv.names, hour=tv.hour)
    out, err, _ = run_program(src, ctx, required_fn=required_fn)
    if err is not None:
        return None
    cost = realistic_cost(tv.spread_pips)
    pip = _pip_size(symbol)
    grid_h = GRID_H_SHORT if fair_price_mode else GRID_H
    best_frame, best_lb = None, None
    for q in GRID_Q:
        for h in grid_h:
            if fair_price_mode:
                frame = evaluate_fair_price_trades(out, tv.mid, cost, tv.test_month, pip, q, h)
            else:
                frame = evaluate_trades(out, tv.mid, cost, tv.test_month, pip, q, h)
            if len(frame) < min_trades:
                continue
            lb, _, _ = fast_lower_bound(frame)
            if np.isfinite(lb) and (best_lb is None or lb > best_lb):
                best_lb, best_frame = lb, frame
    if best_frame is None:
        return None
    return temporal_robustness_verdict(best_frame, seed=0, num_warmup=num_warmup,
                                       num_samples=num_samples, num_chains=num_chains)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default=SYMBOL_DEFAULT)
    ap.add_argument("--tv-dir", default="data/analysis/tick_velocity")
    ap.add_argument("--bar", default="100tick",
                    help="bar-length suffix of the velocity parquet (e.g. 100tick, 1000tick, 2000tick)")
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
    ap.add_argument("--no-temporal-robustness", action="store_true",
                    help="skip the per-symbol temporal-robustness annotation/tie-break on the top-K")
    args = ap.parse_args()
    grid_h = GRID_H_SHORT if args.fair_price else GRID_H
    # For fair-price mode, score on all historical data (2018-2024) so the Bayesian
    # monthly-net posterior has ~84 months of statistical power.  Holdout stays 2025-26.
    if args.fair_price:
        sp = build_trade_splits(
            args.symbol, _velocity_path(args.tv_dir, args.symbol, args.bar),
            embargo=max(grid_h),
            train=("2018", "2019", "2020", "2021", "2022", "2023"),
            validation=("2018", "2019", "2020", "2021", "2022", "2023", "2024"),
            holdout=("2025", "2026"),
        )
    else:
        sp = build_trade_splits(args.symbol, _velocity_path(args.tv_dir, args.symbol, args.bar),
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
    trial_means = [n.mean for n in ranked if np.isfinite(n.mean) and np.isfinite(n.se)]
    n_trials = len(trial_means)
    # Deduplicate by payload so the same generated program doesn't dominate the top-5 display.
    seen_payloads: set[str] = set()
    unique_ranked = []
    for nd in ranked:
        payload_key = json.dumps(nd.payload, sort_keys=True) if isinstance(nd.payload, dict) else nd.payload
        if payload_key not in seen_payloads:
            seen_payloads.add(payload_key)
            unique_ranked.append(nd)
    top = unique_ranked[:5]
    temporal_on = not args.no_temporal_robustness
    tverdicts: dict = {}
    if temporal_on:
        for nd in top:
            tverdicts[id(nd)] = temporal_annotation(nd.payload, sp, args.symbol, fair_price_mode=args.fair_price)
        top = _temporal_tiebreak(top, tverdicts)
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
    lines.append(f"_search trials (admissible programs): {n_trials}_\n")
    for nd in top:
        src = composition_to_source(nd.payload) if isinstance(nd.payload, dict) else nd.payload
        hv = holdout_verdict(src, sp["holdout"], args.symbol, fair_price_mode=args.fair_price)
        tag = "SEED" if nd.parent is None else "evolved"
        branch_tag = f"[{nd.branch}]" if nd.branch else ""
        tstr = ""
        if temporal_on:
            tv = tverdicts.get(id(nd))
            if tv and tv.get("status") == "ok":
                tstr = (f" | temporal: P(edge>0)={tv['p_positive']:.2f} "
                        f"worst-win={tv['worst_window_p_positive']:.2f} "
                        f"tau={tv['tau_mean']:.3f} robust={is_temporally_robust(tv)}")
            elif tv:
                tstr = f" | temporal: {tv.get('status')}"
            else:
                tstr = " | temporal: program error"
        dsr = deflated_edge_prob(nd.mean, nd.se, trial_means)
        dstr = ("" if not np.isfinite(dsr)
                else f" | DSR={dsr:.2f} sig={is_significant_after_deflation(dsr)}")
        if hv:
            lines.append(f"- [{tag}] {branch_tag} val={nd.score:+.3f} | holdout P={hv['p_positive']:.3f} "
                         f"raw={hv['raw_mean']:+.3f} (q{hv['q']} h{hv['h']} n={hv['n_trades']}){tstr}{dstr}")
            # Archive top-5 holdout results as well
            archive.save(src, nd.score, nd.mean, nd.se, nd.branch, nd.parent, hv)
            # Log holdout to tracker for concept-level posterior updates
            if tracker is not None:
                tracker.log_node(src, nd.branch or "unknown", nd.concepts or [],
                                 nd.score, nd.mean, nd.se,
                                 parent_payload=(composition_to_source(nd.parent.payload) if isinstance(nd.parent.payload, dict) else nd.parent.payload) if nd.parent else None,
                                 generation=0, holdout_p=hv.get("p_positive"), holdout_raw=hv.get("raw_mean"))
        else:
            lines.append(f"- [{tag}] {branch_tag} val={nd.score:+.3f} | holdout: program error{tstr}{dstr}")
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
