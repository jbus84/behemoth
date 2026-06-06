"""PUCT-built boosting feature search as a RunSpec for the unified ERA engine.

A node renders to build_features(ctx) (sandboxed, causality-probed). boost_spec closes
over the train split: run_program builds features on train + the scored split, trains a
small CatBoost on train, and returns predictions for the scored split -> the generic
score_program/score_frame/engine_verdict work unchanged."""
from __future__ import annotations

import hashlib

import numpy as np

from scripts.era_scalp.boosting_sandbox import causality_probe as _bf_causality
from scripts.era_scalp.boosting_sandbox import run_program as _bf_run
from scripts.era_scalp.boosting_scorer import complexity_penalty, train_predict
from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.cost_model import realistic_cost
from scripts.era_scalp.era_engine import RunSpec
from scripts.era_scalp.load_splits import _pip_size
from scripts.era_scalp.trade_harness import evaluate_fair_price_trades, evaluate_trades


def _forward_target(mid: np.ndarray, h: int, pip: float) -> np.ndarray:
    """Forward h-bar return in pips (label for the GBDT). NaN in the last h rows."""
    mid = np.asarray(mid, float)
    fwd = np.full(mid.shape, np.nan)
    fwd[:-h] = (mid[h:] - mid[:-h]) / pip
    return fwd


def boost_spec(train_split, *, symbol: str = "EURUSD", target: str = "forward",
               horizon: int = 12, grid_q=None, complexity_per_feat: float = 0.02,
               seed: int = 0, timeout: float = 20.0) -> RunSpec:
    """RunSpec where PUCT searches feature compositions feeding a fixed CatBoost.

    target='forward' (lower-turnover real shot) or 'fair' (intraday calibration)."""
    pip = _pip_size(symbol)
    grid_q = grid_q or [0.80, 0.90, 0.95]
    y_train = _forward_target(train_split.mid, horizon, pip)
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
            preds = train_predict(Xtr, y_train, Xpred, seed=seed)
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
        run_program=run_program,
        causality_probe=causality_probe,
        context_factory=context_factory,
        score_frame=score_frame,
        grid_q=list(grid_q),
        grid_h=[horizon],
        aggregate="robust",
        atomic_mode=True,
    )
