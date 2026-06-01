from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.era_scalp.bayes_edge import edge_verdict
from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.fade_seeds import FADE_SEED_PROGRAMS
from scripts.era_scalp.load_splits import _pip_size
from scripts.era_scalp.sandbox import run_program
from scripts.era_scalp.trade_harness import evaluate_trades

DIRECTIONS = {"fade": 1.0, "continue": -1.0}
GRID_Q = [0.90, 0.95, 0.99]
GRID_H = [100, 200, 400]
MIN_TRADES = 200
MIN_MONTHS_SEL = 6


def dev_signal(split_data) -> np.ndarray:
    """The fixed fair-dislocation dev (fair_fade seed) on a split's feature context."""
    ctx = FeatureContext(X=split_data.X, names=split_data.names, hour=split_data.hour)
    sig, err, _ = run_program(FADE_SEED_PROGRAMS["fair_fade"], ctx, required_fn="signal")
    if err is not None:
        raise RuntimeError(f"dev_signal failed: {err}")
    return sig


def cell_net(signal: np.ndarray, split_data, symbol: str, direction: str,
             q: float, h: int) -> pd.DataFrame:
    """Trade frame for one (direction, q, h) cell. direction in {'fade','continue'}."""
    sgn = DIRECTIONS[direction]
    return evaluate_trades(sgn * np.asarray(signal, float), split_data.mid, split_data.cost,
                           split_data.test_month, _pip_size(symbol), q, h)


def diagnostics(net_frame: pd.DataFrame) -> dict:
    """De-inflated panel: trade count, month count, month-hit-rate, trade-weighted raw mean."""
    n = int(len(net_frame))
    if n == 0:
        return {"n_trades": 0, "n_months": 0, "month_hit": 0.0, "raw_mean": float("nan")}
    g = net_frame.groupby("test_month")["net"].mean()
    return {
        "n_trades": n,
        "n_months": int(g.shape[0]),
        "month_hit": float((g > 0).mean()),
        "raw_mean": float(net_frame["net"].mean()),
    }


def credibility(net_frame: pd.DataFrame, seed: int = 0, fast: bool = False) -> dict | None:
    """Single-symbol monthly posterior summary {p_positive, mean, lo, hi}, or None if too thin.

    fast=True uses short chains for the validation selection sweep (ranking only)."""
    kw = {"num_warmup": 300, "num_samples": 300} if fast else {}
    try:
        post = edge_verdict({"_": net_frame}, seed=seed, **kw)
    except ValueError:
        return None
    return post.pooled


def select_on_validation(signal: np.ndarray, split_data, symbol: str) -> dict | None:
    """Pick the (direction, q, h) maximising the lower credible bound among cells passing the
    sample guard (>= MIN_TRADES trades, >= MIN_MONTHS_SEL months) on the validation split."""
    best = None
    for direction in DIRECTIONS:
        for q in GRID_Q:
            for h in GRID_H:
                frame = cell_net(signal, split_data, symbol, direction, q, h)
                diag = diagnostics(frame)
                if diag["n_trades"] < MIN_TRADES or diag["n_months"] < MIN_MONTHS_SEL:
                    continue
                cred = credibility(frame, fast=True)
                if cred is None:
                    continue
                val = {**cred, **diag}
                cand = {"direction": direction, "q": q, "h": h, "val": val}
                key = (val["lo"], val["raw_mean"])
                if best is None or key > (best["val"]["lo"], best["val"]["raw_mean"]):
                    best = cand
    return best
