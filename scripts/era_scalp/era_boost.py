"""PUCT-built boosting feature search as a RunSpec for the unified ERA engine.

A node renders to build_features(ctx) (sandboxed, causality-probed). boost_spec closes
over the train split: run_program builds features on train + the scored split, trains a
small CatBoost on train, and returns predictions for the scored split -> the generic
score_program/score_frame/engine_verdict work unchanged."""
from __future__ import annotations

import hashlib
import random as _random

import numpy as np

from scripts.era_scalp.boosting_sandbox import causality_probe as _bf_causality
from scripts.era_scalp.boosting_sandbox import run_program as _bf_run
from scripts.era_scalp.boosting_scorer import complexity_penalty, train_predict
from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.cost_model import realistic_cost
from scripts.era_scalp.era_engine import RunSpec, engine_verdict, run_search_rich
from scripts.era_scalp.feature_concepts import (
    FEATURE_CONCEPT_TAXONOMY,
    FEATURE_SEED_COMPOSITIONS,
    composition_to_features_source,
)
from scripts.era_scalp.load_splits import _pip_size
from scripts.era_scalp.trade_harness import evaluate_fair_price_trades, evaluate_trades


def _forward_target(mid: np.ndarray, h: int, pip: float) -> np.ndarray:
    """Forward h-bar return in pips (label for the GBDT). NaN in the last h rows."""
    mid = np.asarray(mid, float)
    fwd = np.full(mid.shape, np.nan)
    fwd[:-h] = (mid[h:] - mid[:-h]) / pip
    return fwd


def _sanitize(comp):
    if not isinstance(comp, dict):
        return {"skeleton": "default", "operators": {}, "params": {"w": 20}}
    ops = comp.get("operators", {})
    ops = {k: v for k, v in ops.items() if isinstance(v, str) and v in FEATURE_CONCEPT_TAXONOMY}
    return {"skeleton": "default", "operators": ops, "params": comp.get("params", {"w": 20})}


def mutate_composition(parent, score, logs, idea, *, cache_dir=None, seed=0):
    """Deterministic mutation: add/swap/drop one feature operator. Returns (comp, prior)."""
    rng = _random.Random(hash((repr(parent), seed)) & 0xFFFFFFFF)
    comp = _sanitize(parent)
    ops = dict(comp["operators"])
    concepts = list(FEATURE_CONCEPT_TAXONOMY)
    action = rng.choice(["add", "swap", "drop"]) if ops else "add"
    if action == "add":
        ops[f"s{len(ops)}"] = rng.choice(concepts)
    elif action == "swap" and ops:
        ops[rng.choice(list(ops))] = rng.choice(concepts)
    elif action == "drop" and len(ops) > 1:
        del ops[rng.choice(list(ops))]
    w = int(comp["params"].get("w", 20))
    params = {"w": max(2, w + rng.choice([-8, 0, 8]))}
    return {"skeleton": "default", "operators": ops, "params": params}, 0.5


def recombine_compositions(comp_a, score_a, comp_b, score_b, *, cache_dir=None):
    """Union the two parents' operators (favouring the higher-scoring parent's window)."""
    a, b = _sanitize(comp_a), _sanitize(comp_b)
    ops = {**a["operators"], **b["operators"]}
    params = a["params"] if score_a >= score_b else b["params"]
    return {"skeleton": "default", "operators": ops, "params": params}, 0.5


def _halve(split):
    """Split a TradeSplitData in half by time -> (V1, V2)."""
    from dataclasses import replace
    n = len(split.mid)
    m = n // 2
    def cut(s, a, b):
        return replace(s, X=s.X[a:b], hour=(None if s.hour is None else s.hour[a:b]),
                       mid=s.mid[a:b], cost=s.cost[a:b], test_month=s.test_month[a:b],
                       spread_pips=(None if s.spread_pips is None else s.spread_pips[a:b]))
    return cut(split, 0, m), cut(split, m, n)


def run_boost_search(splits, *, symbol="EURUSD", target="forward", horizon=12,
                     budget=20, seed=0, cache_dir=".era_boost_cache",
                     complexity_per_feat=0.02, k_folds=4, embargo=50):
    """PUCT feature search: select on V1, confirm on V2, holdout once."""
    v1, v2 = _halve(splits["validation"])
    spec = boost_spec(splits["train"], symbol=symbol, target=target, horizon=horizon,
                      complexity_per_feat=complexity_per_feat, seed=seed,
                      k_folds=k_folds, embargo=embargo)
    nodes = run_search_rich(spec, {"validation": v1}, budget=budget, seed=seed,
                            cache_dir=cache_dir)
    # apply complexity penalty to node value using logged n_feat (fallback: len(operators))
    def penalised(n):
        nf = 0
        comp = _sanitize(getattr(n, "payload", {}))
        nf = len(comp["operators"])
        return n.score - complexity_penalty(nf, complexity_per_feat)
    ranked = sorted([n for n in nodes if n.score > -1e6 + 1], key=penalised, reverse=True)
    if not ranked:
        return {"survivor": None, "holdout": None}
    best = ranked[0]
    src = spec.render_payload(best.payload)
    # confirm on V2
    from scripts.era_scalp.era_engine import score_program
    v2_val, _, _, _ = score_program(src, spec, v2)
    # holdout once (engine_verdict at best cell)
    verdict = engine_verdict(spec, [best], {"validation": v1, "holdout": splits.get("holdout")},
                             top_k=1)
    return {
        "survivor": {"branch": best.branch, "val_v1": float(best.score),
                     "val_v1_penalised": float(penalised(best)), "val_v2": float(v2_val),
                     "n_feat": len(_sanitize(best.payload)["operators"]), "src": src},
        "holdout": verdict[0] if verdict else None,
    }


def boost_spec(train_split, *, symbol: str = "EURUSD", target: str = "forward",
               horizon: int = 12, grid_q=None, complexity_per_feat: float = 0.02,
               seed: int = 0, timeout: float = 20.0, seed_only: bool = False,
               k_folds: int = 4, embargo: int = 50) -> RunSpec:
    """RunSpec where PUCT searches feature compositions feeding a fixed CatBoost.

    target='forward' (lower-turnover real shot) or 'fair' (intraday calibration)."""
    pip = _pip_size(symbol)
    grid_q = grid_q or [0.80, 0.90, 0.95]
    y_train = _forward_target(train_split.mid, horizon, pip) if train_split is not None else None
    _cache: dict[str, np.ndarray] = {}

    def _features(src, ctx):
        feats, err, _ = _bf_run(src, ctx, timeout=timeout)
        return feats, err

    def context_factory(split):
        return FeatureContext(X=split.X, names=split.names, hour=split.hour)

    def run_program(src, ctx, timeout=timeout, required_fn="build_features"):
        # 1) features on the scored split
        Xpred, err = _features(src, ctx)
        if err is not None:
            return None, err, ""
        # 2) train (cached by src): features on train + CatBoost fit
        key = hashlib.sha1(src.encode()).hexdigest()
        if key not in _cache:
            tctx = FeatureContext(X=train_split.X, names=train_split.names, hour=train_split.hour)
            Xtr, terr = _features(src, tctx)
            if terr is not None:
                return None, terr, ""
            _cache[key] = ("model", Xtr)
        _, Xtr = _cache[key]
        try:
            preds = train_predict(Xtr, y_train, Xpred, seed=seed,
                                  k_folds=k_folds, embargo=embargo)
        except Exception as e:  # catboost failure -> reject node
            return None, f"catboost: {e}", ""
        # stash feature count on the array for the complexity penalty via score_frame
        return preds, None, f"n_feat={Xpred.shape[1]}"

    def causality_probe(src, ctx, out, required_fn="build_features"):
        # probe the FEATURE code, not the predictions
        feats, err, _ = _bf_run(src, ctx, timeout=timeout)
        if err is not None:
            return False, f"feature exec: {err}"
        return _bf_causality(src, ctx, feats)

    def score_frame(out, split, q, h):
        if target == "fair":
            return evaluate_fair_price_trades(out, split.mid, realistic_cost(split.spread_pips),
                                              split.test_month, pip, q, h)
        return evaluate_trades(out, split.mid, realistic_cost(split.spread_pips),
                               split.test_month, pip, q, h)

    return RunSpec(
        name=f"boost_{target}_h{horizon}",
        required_fn="build_features",
        run_program=(None if seed_only else run_program),
        causality_probe=causality_probe,
        context_factory=context_factory,
        score_frame=score_frame,
        grid_q=list(grid_q),
        grid_h=[horizon],
        aggregate="robust",
        atomic_mode=True,
        seed_compositions=dict(FEATURE_SEED_COMPOSITIONS),
        render_payload=lambda comp: composition_to_features_source(
            "default", _sanitize(comp)["operators"], _sanitize(comp)["params"]),
        branch_tags={k: k for k in FEATURE_SEED_COMPOSITIONS},
        propose_atomic=mutate_composition,
        recombine_atomic=recombine_compositions,
        ideas=["Compose causal microstructure features (flow, vol regime, reversal, "
               "liquidity, quote-revision) for a boosted forward-return model."],
    )
