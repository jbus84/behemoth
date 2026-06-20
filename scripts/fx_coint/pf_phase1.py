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
    entry_mid: float,
    side: str,
    tilt: float,
    sigma_bps: float,
    freq: str,
    sym: str,
    minute_idx: tuple,
    params: PFParams,
) -> float:
    """Reconstruct hold path, run filter, apply exit policy, return gross signed bps.

    entry_mid: the bar-CLOSE mid at the signal bucket (bars["mid"] at B).
    The hold window is [B+freq, B+2*freq); entry_mid anchors the log-return.
    At hold-to-cap (no early exit) exit price == minutes[-1] == next bar's close mid,
    so gross == test_actual_bps exactly.

    Returns NaN if path is too short or sigma invalid (caller falls back to fixed-horizon).
    """
    buckets_ns, mids = minute_idx
    minutes = hold_path(entry_bucket, freq, buckets_ns, mids)
    if len(minutes) < 1 or sigma_bps <= 0:
        return float("nan")  # caller falls back to baseline full-bar return
    series = np.concatenate([[entry_mid], minutes])
    obs = path_to_volnorm_returns(series, sigma_bps)
    if len(obs) < 1:
        return float("nan")
    post = run_filter(obs, tilt=float(tilt), params=params)
    xi = exit_index(post, side=side, max_hold=len(obs))
    sign = 1.0 if side == "long" else -1.0
    return float(sign * (np.log(minutes[xi]) - np.log(entry_mid)) * 1e4)


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

    # Build bucket → bar-close mid lookup (keys are np.datetime64[ns])
    _bar_buckets = bars["bucket"].to_numpy().astype("datetime64[ns]")
    _bar_mids = bars["mid"].to_numpy().astype(float)
    close_by_bucket: dict = dict(zip(_bar_buckets, _bar_mids, strict=False))

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
            bk_ns = np.datetime64(bk, "ns")
            entry_mid = close_by_bucket.get(bk_ns)
            if entry_mid is None or not np.isfinite(entry_mid):
                gross_pf = float(act)  # fall back: no bar-close mid available
            else:
                gross_pf = pf_exit_realized_bps(
                    bk, entry_mid, "long", float(tp), sigma_bps, freq, sym, minute_idx, params
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
    """For the strengthened alignment test: compare hold_path cap-exit gross bps
    to the bar-close ret_next_bps (test_actual_bps) for entries where the path is non-empty.

    Uses the corrected construction: entry_mid = bar-close mid at B, minutes = [B+f, B+2f),
    cap-exit gross = sign*(log(minutes[-1]/entry_mid))*1e4.

    Returns array of (cap_exit_gross - test_actual_bps) differences in bps.
    """
    src = _REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"
    bars = build_freq_bars(pl.read_parquet(src), freq)
    panel = build_panel(bars)
    folds = walk_forward(panel, n_folds=n_folds)
    minute_idx = build_minute_index(sym)
    buckets_ns, mids = minute_idx

    _bar_buckets = bars["bucket"].to_numpy().astype("datetime64[ns]")
    _bar_mids = bars["mid"].to_numpy().astype(float)
    close_by_bucket: dict = dict(zip(_bar_buckets, _bar_mids, strict=False))

    diffs: list[float] = []
    for f in folds:
        thr = float(np.quantile(f["train_pred"], q))
        sel = f["test_pred"] >= thr
        test_actuals = f["test_actual_bps"][sel]
        test_buckets = f["test_bucket"][sel]

        for act, bk in zip(test_actuals, test_buckets, strict=False):
            bk_ns = np.datetime64(bk, "ns")
            entry_mid = close_by_bucket.get(bk_ns)
            if entry_mid is None or not np.isfinite(entry_mid):
                continue
            minutes = hold_path(bk, freq, buckets_ns, mids)
            if len(minutes) < 1:
                continue
            # cap-exit: exit at last minute in window = next bar's close mid
            cap_gross = (np.log(minutes[-1]) - np.log(entry_mid)) * 1e4
            diffs.append(float(cap_gross) - float(act))

    return np.array(diffs)
