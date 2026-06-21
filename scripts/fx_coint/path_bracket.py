"""Bracket (stop/take-profit/max-hold) evaluator over a 1-minute mid path."""
from __future__ import annotations

import numpy as np


def evaluate_bracket(entry_mid: float, minutes: np.ndarray, side: str, sigma_bps: float,
                     stop_sigma: float | None, tp_sigma: float | None,
                     cost_bps: float) -> float:
    if len(minutes) < 1 or sigma_bps <= 0:
        return float("nan")
    sign = 1.0 if side == "long" else -1.0
    signed = sign * (np.log(minutes) - np.log(entry_mid)) * 1e4
    stop_bps = None if stop_sigma is None else -stop_sigma * sigma_bps
    tp_bps = None if tp_sigma is None else tp_sigma * sigma_bps
    for i in range(len(signed)):
        hit_stop = stop_bps is not None and signed[i] <= stop_bps
        hit_tp = tp_bps is not None and signed[i] >= tp_bps
        if hit_stop:                       # stop wins ties (conservative)
            return float(signed[i] - cost_bps)
        if hit_tp:
            return float(signed[i] - cost_bps)
    return float(signed[-1] - cost_bps)
