from __future__ import annotations
from pathlib import Path
import numpy as np, pandas as pd
from scripts.era.score_program import SplitData

def build_splits(symbol, bar_ticks, tom_dir: Path, velocity_dir: Path, horizon: int = 3,
                 train=("2025-01","2025-02","2025-03","2025-04","2025-05","2025-06"),
                 validation=("2025-07","2025-08","2025-09","2025-10"),
                 holdout=("2025-11","2025-12","2026-01","2026-02")):
    import sys
    sys.path.insert(0, str(Path.cwd()))
    from scripts.cross_symbol import get_or_build_cross_symbol_frame, CROSS_SYMBOLS, _USD_SIGN
    # The cross-symbol frame is built from the velocity dataset, so it already
    # carries y_fwd_pips_h*, cost_est_pips, close_ts, the 5 peer xs_ret_z__<sym>
    # columns and the target's raw ret_z. We read everything from it (a separate
    # velocity merge would collide on y_fwd_pips_h*/cost_est_pips).
    cs = get_or_build_cross_symbol_frame(symbol, bar_ticks, velocity_dir, [horizon]).copy()
    cs["close_ts"] = pd.to_datetime(cs["close_ts"], utc=True)
    # the target's USD-aligned column is not pre-named; derive it (mirrors
    # cross_symbol._usd_aligned_ret_z) so all 6 CROSS_SYMBOLS columns exist.
    cs[f"xs_ret_z__{symbol}"] = int(_USD_SIGN[symbol]) * pd.to_numeric(cs["ret_z"], errors="coerce")
    cs["test_month"] = cs["close_ts"].dt.strftime("%Y-%m")
    cols = [f"xs_ret_z__{s}" for s in CROSS_SYMBOLS]
    ycol = f"y_fwd_pips_h{horizon}"

    def _split(months):
        d = cs[cs["test_month"].isin(months)]
        return SplitData(r=d[cols].to_numpy(float), names=list(CROSS_SYMBOLS),
                         target=symbol, usd_sign=int(_USD_SIGN[symbol]),
                         y_fwd=d[ycol].to_numpy(float),
                         cost=d["cost_est_pips"].to_numpy(float),
                         test_month=d["test_month"].to_numpy(),
                         hour=d["hour_utc"].to_numpy())
    return {"train": _split(train), "validation": _split(validation), "holdout": _split(holdout)}
