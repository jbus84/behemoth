"""Phase-1 backtest: PF dynamic-exit vs frozen fixed-horizon baseline, same entries."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import polars as pl

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.fx_coint.pf_core import PFParams, run_filter  # noqa: E402
from scripts.fx_coint.pf_exit import exit_index  # noqa: E402
from scripts.fx_coint.pf_paths import (  # noqa: E402
    build_minute_index,
    hold_path,
    path_to_volnorm_returns,
)
from scripts.fx_coint.reg_signal_hunt import (  # noqa: E402
    COST_BPS,
    build_freq_bars,
    build_panel,
)
from scripts.fx_coint.tail_wfo import walk_forward  # noqa: E402


def pf_exit_realized_bps(
    entry_bucket: np.datetime64,
    side: str,
    tilt: float,
    sigma_bps: float,
    freq: str,
    sym: str,
    minute_idx: tuple,
    params: PFParams,
) -> float:
    """Reconstruct hold path, run filter, apply exit policy, return gross signed bps.

    Returns NaN if path is too short (caller falls back to fixed-horizon return).
    """
    buckets_ns, mids = minute_idx
    path = hold_path(entry_bucket, freq, buckets_ns, mids)
    if len(path) < 2 or sigma_bps <= 0:
        return float("nan")  # caller falls back to baseline full-bar return
    obs = path_to_volnorm_returns(path, sigma_bps)
    post = run_filter(obs, tilt=float(tilt), params=params)
    xi = exit_index(post, side=side, max_hold=len(obs))
    # realized gross signed bps from path[0] (bar open) to path[xi+1] (exit minute)
    sign = 1.0 if side == "long" else -1.0
    gross = sign * (np.log(path[xi + 1]) - np.log(path[0])) * 1e4
    return float(gross)


def run_pair_phase1(
    sym: str,
    freq: str = "2h",
    q: float = 0.95,
    n_folds: int = 5,
    params: PFParams | None = None,
) -> dict:
    """Run Phase-1 backtest for one pair: PF-exit vs fixed-horizon baseline.

    Returns aligned arrays over the same ridge-selected long entries (top-q tile):
        net_base (m,): full-bar ret_next_bps - cost  (frozen baseline)
        net_pf   (m,): PF-exit gross - cost
        bucket   (m,): datetime64[ns] entry timestamps
        n              int: number of entries m
    """
    if params is None:
        params = PFParams()

    src = _REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"
    bars = build_freq_bars(pl.read_parquet(src), freq)
    panel = build_panel(bars)
    folds = walk_forward(panel, n_folds=n_folds)
    minute_idx = build_minute_index(sym)
    cost = COST_BPS[sym]

    # Build bucket → sigma_h lookup from the full panel (pandas)
    sig_by_bucket: dict = dict(
        zip(panel["bucket"].to_numpy(), panel["sigma_h"].to_numpy(), strict=False)
    )

    net_base_list: list[float] = []
    net_pf_list: list[float] = []
    bucket_list: list = []

    for f in folds:
        thr = float(np.quantile(f["train_pred"], q))
        sel = f["test_pred"] >= thr
        test_preds = f["test_pred"][sel]
        test_actuals = f["test_actual_bps"][sel]
        test_buckets = f["test_bucket"][sel]

        for tp, act, bk in zip(test_preds, test_actuals, test_buckets, strict=False):
            sigma_bps = float(sig_by_bucket.get(bk, np.nan))
            gross_pf = pf_exit_realized_bps(
                bk, "long", float(tp), sigma_bps, freq, sym, minute_idx, params
            )
            if not np.isfinite(gross_pf):
                gross_pf = float(act)  # fall back to fixed-horizon return
            net_base_list.append(float(act) - cost)
            net_pf_list.append(gross_pf - cost)
            bucket_list.append(bk)

    return {
        "net_base": np.array(net_base_list),
        "net_pf": np.array(net_pf_list),
        "bucket": np.array(bucket_list, dtype="datetime64[ns]"),
        "n": len(net_base_list),
    }


def _collect_alignment_sample(
    sym: str,
    freq: str = "2h",
    q: float = 0.95,
    n_folds: int = 5,
) -> np.ndarray:
    """For the strengthened alignment test: compare hold_path endpoint gross bps
    to the bar-close ret_next_bps for entries where the path is non-empty.

    Returns array of (path_endpoint_gross - bar_close_ret) differences in bps.
    """
    src = _REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"
    bars = build_freq_bars(pl.read_parquet(src), freq)
    panel = build_panel(bars)
    folds = walk_forward(panel, n_folds=n_folds)
    minute_idx = build_minute_index(sym)
    buckets_ns, mids = minute_idx

    diffs: list[float] = []
    for f in folds:
        thr = float(np.quantile(f["train_pred"], q))
        sel = f["test_pred"] >= thr
        test_actuals = f["test_actual_bps"][sel]
        test_buckets = f["test_bucket"][sel]

        for act, bk in zip(test_actuals, test_buckets, strict=False):
            path = hold_path(bk, freq, buckets_ns, mids)
            if len(path) < 2:
                continue
            # path[0] = first 1m bar open AFTER entry bucket (open of the held bar)
            # path[-1] = close of the last 1m bar in the hold window
            path_gross = (np.log(path[-1]) - np.log(path[0])) * 1e4
            diffs.append(float(path_gross) - float(act))

    return np.array(diffs)
