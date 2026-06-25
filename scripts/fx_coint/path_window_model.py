"""Path-aware directional model (Stage 1): does the W-bar path into an entry carry
directional information that point-in-time features miss, at N=30/50?

Flattens a window of per-bar path channels and feeds it as X to the existing
walk-forward harness (pnl_walkforward.model_oos_pnl). Benchmarks against the
point-in-time 30-feature design matrix on identical events. Per-symbol primary,
pooled reference. Verdict gates Stage 2 (torch GRU/TCN).

Usage: uv run python scripts/fx_coint/path_window_model.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))


def path_channels(logp, f, vol) -> list[np.ndarray]:
    """Per-bar path channels in fixed order: [log_return, vol, intra_bar_mom, hl_pos_frac]."""
    log_return = np.diff(np.asarray(logp, dtype=float), prepend=float(logp[0]))
    return [log_return,
            np.asarray(vol, dtype=float),
            np.asarray(f["intra_bar_mom"], dtype=float),
            np.asarray(f["hl_pos_frac"], dtype=float)]


def build_window_matrix(channels, entry, W: int) -> np.ndarray:
    """Flatten the W-bar window ending at each entry into a (len(entry), W*C) matrix.

    Row i = concatenate over channels of ch[entry[i]-W+1 : entry[i]+1] (channel-major).
    Raises ValueError if any entry[i] < W-1 (window would underflow).
    """
    entry = np.asarray(entry)
    if entry.min() < W - 1:
        raise ValueError(f"entry index {int(entry.min())} < W-1={W - 1}; window underflows")
    rows = np.empty((len(entry), W * len(channels)), dtype=float)
    for i, e in enumerate(entry):
        rows[i] = np.concatenate([ch[e - W + 1:e + 1] for ch in channels])
    return rows
