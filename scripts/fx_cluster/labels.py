"""Vol-scaled symmetric triple-barrier outcomes.

For each point (pair, t): a profit barrier at +target and a stop at -target (in
price units), evaluated for a given side (+1 long / -1 short) over <= patience
forward bars, using intrabar mid high/low for touch detection. Same-bar
ambiguity (both barriers inside one bar) resolves CONSERVATIVELY as the stop.
The gross return is in price-difference units; cost is applied in build_labels.
"""

from __future__ import annotations

import math

import numpy as np
import polars as pl

from scripts.fx_cluster import config
from scripts.fx_cluster.causal import ewma_vol


def barrier_outcome(mid: np.ndarray, hi: np.ndarray, lo: np.ndarray,
                    i: int, target: float, patience: int, side: int) -> dict:
    """First-touch outcome for an entry at index i. Returns gross (price diff), mfe, mae,
    hold_bars, exit_reason in {"target","stop","timeout"}. target is in price units."""
    entry = mid[i]
    up = entry + target           # profit for long / stop for short
    dn = entry - target           # stop for long / profit for short
    mfe = mae = 0.0
    n = len(mid)
    last = min(i + patience, n - 1)
    for j in range(i + 1, last + 1):
        # running favourable/adverse excursion (signed by side), in price units
        fav = side * (hi[j] - entry) if side > 0 else side * (lo[j] - entry)
        adv = side * (lo[j] - entry) if side > 0 else side * (hi[j] - entry)
        mfe = max(mfe, fav)
        mae = min(mae, adv)
        hit_up = hi[j] >= up
        hit_dn = lo[j] <= dn
        target_hit = hit_up if side > 0 else hit_dn
        stop_hit = hit_dn if side > 0 else hit_up
        if stop_hit:  # conservative: stop wins same-bar ties
            return {"gross": side * (dn - entry) if side > 0 else side * (up - entry),
                    "mfe": mfe, "mae": mae, "hold_bars": j - i, "exit_reason": "stop"}
        if target_hit:
            return {"gross": side * (up - entry) if side > 0 else side * (dn - entry),
                    "mfe": mfe, "mae": mae, "hold_bars": j - i, "exit_reason": "target"}
    return {"gross": side * (mid[last] - entry), "mfe": mfe, "mae": mae,
            "hold_bars": last - i, "exit_reason": "timeout"}


def build_labels(bars: pl.DataFrame) -> pl.DataFrame:
    """Per-bar triple-barrier outcomes for BOTH sides, net of cost. bars must have
    columns bucket, mid, mid_high, mid_low, bid, ask sorted by bucket."""
    mid = bars["mid"].to_numpy()
    hi = bars["mid_high"].to_numpy()
    lo = bars["mid_low"].to_numpy()
    logret = np.diff(np.log(mid), prepend=np.log(mid[0]))
    sigma = ewma_vol(logret, config.EWMA_LAMBDA)
    spread_bps = ((bars["ask"] - bars["bid"]) / bars["mid"]).to_numpy() * 1e4
    cost_bps = spread_bps + config.COMMISSION_BPS_RT

    rows = []
    n = len(mid)
    for i in range(n):
        target_price = mid[i] * config.K_BARRIER * sigma[i] * math.sqrt(config.TARGET_H)
        rec = {"row": i}
        if target_price <= 0:  # no vol estimate yet -> skip (NaN net)
            rec.update(ret_long=np.nan, ret_short=np.nan, mfe=np.nan, mae=np.nan,
                       hold_bars=0, exit_long="none", exit_short="none")
            rows.append(rec)
            continue
        long_o = barrier_outcome(mid, hi, lo, i, target_price, config.PATIENCE_BARS, +1)
        short_o = barrier_outcome(mid, hi, lo, i, target_price, config.PATIENCE_BARS, -1)
        rec.update(
            ret_long=long_o["gross"] * 1e4 - cost_bps[i],
            ret_short=short_o["gross"] * 1e4 - cost_bps[i],
            mfe=long_o["mfe"] * 1e4, mae=long_o["mae"] * 1e4,
            hold_bars=long_o["hold_bars"],
            exit_long=long_o["exit_reason"], exit_short=short_o["exit_reason"],
        )
        rows.append(rec)
    return bars.with_row_index("row").join(pl.DataFrame(rows), on="row", how="left")
