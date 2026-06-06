from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.cross_symbol import _USD_SIGN, CROSS_SYMBOLS, get_or_build_cross_symbol_frame
from scripts.era_scalp.basket_context import BasketSplit

_REFERENCE = "EURUSD"


def build_basket_panel(
    bar_ticks: int,
    velocity_dir,
    horizon: int = 3,
    train=("2025-01", "2025-02", "2025-03", "2025-04", "2025-05", "2025-06"),
    validation=("2025-07", "2025-08", "2025-09", "2025-10"),
    holdout=("2025-11", "2025-12", "2026-01", "2026-02"),
):
    """Build {train,validation,holdout} BasketSplits aligned on the reference grid.

    r comes from the reference frame's xs_ret_z__{sym} columns (USD-aligned, all symbols).
    y_fwd_panel / cost_panel are each symbol's own forward return / cost, merged backward
    (look-ahead-free) onto the reference close_ts grid."""
    velocity_dir = Path(velocity_dir)
    ref = get_or_build_cross_symbol_frame(_REFERENCE, bar_ticks, velocity_dir, [horizon]).copy()
    ref["close_ts"] = pd.to_datetime(ref["close_ts"], utc=True)
    # reference's own usd-aligned column (mirrors cross_symbol._usd_aligned_ret_z)
    ref[f"xs_ret_z__{_REFERENCE}"] = int(_USD_SIGN[_REFERENCE]) * pd.to_numeric(
        ref["ret_z"], errors="coerce"
    )
    ref["test_month"] = ref["close_ts"].dt.strftime("%Y-%m")
    ref = ref.sort_values("close_ts").reset_index(drop=True)

    ycol = f"y_fwd_pips_h{horizon}"
    base = ref[["close_ts", "test_month", "hour_utc"]].copy()
    r_cols = [f"xs_ret_z__{s}" for s in CROSS_SYMBOLS]
    r_panel = ref[r_cols].copy()

    # per-symbol forward-return + cost, merged backward onto the reference grid
    yfwd = pd.DataFrame(index=ref.index)
    cost = pd.DataFrame(index=ref.index)
    for s in CROSS_SYMBOLS:
        cs = get_or_build_cross_symbol_frame(s, bar_ticks, velocity_dir, [horizon]).copy()
        cs["close_ts"] = pd.to_datetime(cs["close_ts"], utc=True)
        right = cs[["close_ts", ycol, "cost_est_pips"]].dropna(subset=["close_ts"])
        right = right.sort_values("close_ts").reset_index(drop=True)
        merged = pd.merge_asof(base[["close_ts"]], right, on="close_ts", direction="backward")
        yfwd[s] = merged[ycol].to_numpy(float)
        cost[s] = merged["cost_est_pips"].to_numpy(float)

    def _split(months):
        mask = base["test_month"].isin(months).to_numpy()
        return BasketSplit(
            r=r_panel.to_numpy(float)[mask],
            y_fwd_panel=yfwd.to_numpy(float)[mask],
            cost_panel=cost.to_numpy(float)[mask],
            names=list(CROSS_SYMBOLS),
            test_month=base["test_month"].to_numpy()[mask],
            hour=base["hour_utc"].to_numpy(float)[mask],
        )

    return {"train": _split(train), "validation": _split(validation), "holdout": _split(holdout)}
