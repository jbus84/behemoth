"""Reconstruct the intra-hold 1-minute mid path for a ridge-selected entry bar.

The strategy holds the *next* bar after the entry signal (ret_next_bps semantics):
signal at bar with bucket B -> position over window (B, B+freq] -> exit at its close.
The dynamic-exit filter runs on the 1-minute mids inside that window.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import polars as pl

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.fx_coint.reg_signal_hunt import FREQ_MINUTES  # noqa: E402

_NS_PER_MIN = 60_000_000_000


def build_minute_index(sym: str) -> tuple[np.ndarray, np.ndarray]:
    df = pl.read_parquet(_REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet").sort("bucket")
    buckets_ns = df["bucket"].to_numpy().astype("datetime64[ns]").astype("int64")
    mids = df["mid"].to_numpy().astype(float)
    return buckets_ns, mids


def hold_path(
    entry_bucket: np.datetime64,
    freq: str,
    buckets_ns: np.ndarray,
    mids: np.ndarray,
) -> np.ndarray:
    """Return 1m mids in the held window [B+freq, B+2*freq).

    Window: [B+freq, B+2*freq) — the next bar after the signal bar.
    The caller anchors the entry at the signal bar's CLOSE mid (passed separately).
    At hold-to-cap the last minute in this window equals the next bar's close mid,
    so gross == test_actual_bps exactly when no early exit is triggered.
    Task 6 verifies alignment end-to-end.
    """
    step_ns = FREQ_MINUTES[freq] * _NS_PER_MIN
    e = np.datetime64(entry_bucket, "ns").astype("int64")
    i0 = np.searchsorted(buckets_ns, e + step_ns, side="left")
    i1 = np.searchsorted(buckets_ns, e + 2 * step_ns, side="left")
    return mids[i0:i1]


def path_to_volnorm_returns(path_mids: np.ndarray, sigma_bps: float) -> np.ndarray:
    """Log-returns of path in bps, divided by sigma_bps. Length = len(path_mids)-1."""
    if len(path_mids) < 2 or sigma_bps <= 0:
        return np.empty(0)
    lr_bps = (np.log(path_mids[1:]) - np.log(path_mids[:-1])) * 1e4
    return lr_bps / sigma_bps
