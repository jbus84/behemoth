"""Uniform 1h-grid multi-horizon tail-long net-edge re-test."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.fx_coint.reg_signal_hunt import FEATURE_COLS, build_panel  # noqa: E402


def build_horizon_panel(bars: pd.DataFrame, H: int, vol_lookback: int = 24) -> pd.DataFrame:
    panel = build_panel(bars, vol_lookback=vol_lookback).reset_index(drop=True)
    b = bars.reset_index(drop=True)
    mid = b["mid"].to_numpy()
    contig = b["contig"].to_numpy()
    n = len(b)
    fwd = np.full(n, np.nan)
    # forward-H window [i, i+H] valid only if bars i+1..i+H are all contiguous
    for i in range(n - H):
        if contig[i + 1:i + 1 + H].all():
            fwd[i] = (np.log(mid[i + H]) - np.log(mid[i])) * 1e4
    fwd_by_bucket = dict(zip(b["bucket"].to_numpy(), fwd, strict=False))
    rf = panel["bucket"].map(lambda x: fwd_by_bucket.get(x, np.nan)).to_numpy()
    out = panel.copy()
    out["ret_fwd_bps"] = rf
    out["target_z"] = rf / (out["sigma_h"].to_numpy() * np.sqrt(H))
    keep = np.isfinite(out["ret_fwd_bps"].to_numpy()) & np.isfinite(out["target_z"].to_numpy())
    return out[keep].reset_index(drop=True)[FEATURE_COLS + ["bucket", "sigma_h", "ret_fwd_bps", "target_z"]]
