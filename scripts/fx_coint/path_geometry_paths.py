"""Intra-hold 1-minute mid-path reconstruction (vendored, verified in PF Phase-1).

Entry signal at bar bucket B; position held over the n_bars bars AFTER B, i.e. the
window [B+freq, B+(n_bars+1)*freq). The entry is anchored by the caller at the signal
bar's CLOSE mid (bars["mid"] at B). At hold-to-cap the last minute equals the held
window's final bar close, so a no-bracket terminal return reproduces the panel
close-to-close return exactly.
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


def hold_path(entry_bucket, freq: str, buckets_ns: np.ndarray, mids: np.ndarray,
              n_bars: int = 1) -> np.ndarray:
    step_ns = FREQ_MINUTES[freq] * _NS_PER_MIN
    e = np.datetime64(entry_bucket, "ns").astype("int64")
    i0 = np.searchsorted(buckets_ns, e + step_ns, side="left")
    i1 = np.searchsorted(buckets_ns, e + (n_bars + 1) * step_ns, side="left")
    return mids[i0:i1]


def path_to_volnorm_returns(path_mids: np.ndarray, sigma_bps: float) -> np.ndarray:
    if len(path_mids) < 2 or sigma_bps <= 0:
        return np.empty(0)
    lr_bps = (np.log(path_mids[1:]) - np.log(path_mids[:-1])) * 1e4
    return lr_bps / sigma_bps
