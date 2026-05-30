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
    cs = get_or_build_cross_symbol_frame(symbol, bar_ticks, velocity_dir, [horizon]).copy()
    cs["close_ts"] = pd.to_datetime(cs["close_ts"], utc=True)
    # The cs_frame carries xs_ret_z__<peer> for the 5 peers plus the target's
    # own raw `ret_z`; the target's USD-aligned column is NOT pre-named. Derive
    # it (mirrors cross_symbol._usd_aligned_ret_z) so all 6 CROSS_SYMBOLS
    # columns exist before selection.
    cs[f"xs_ret_z__{symbol}"] = int(_USD_SIGN[symbol]) * pd.to_numeric(cs["ret_z"], errors="coerce")
    vel = pd.read_parquet(velocity_dir / f"{symbol}_{bar_ticks}tick_velocity.parquet")
    vel["close_ts"] = pd.to_datetime(vel["close_ts"], utc=True)
    keep = ["close_ts", "cost_est_pips", f"y_fwd_pips_h{horizon}", "test_month"] \
        if "test_month" in vel.columns else ["close_ts", "cost_est_pips", f"y_fwd_pips_h{horizon}"]
    m = cs.merge(vel[keep].drop_duplicates("close_ts"), on="close_ts", how="inner")
    if "test_month" not in m.columns:
        m["test_month"] = m["close_ts"].dt.strftime("%Y-%m")
    cols = [f"xs_ret_z__{s}" for s in CROSS_SYMBOLS]
    def _split(months):
        d = m[m["test_month"].isin(months)]
        return SplitData(r=d[cols].to_numpy(float), names=list(CROSS_SYMBOLS),
                         target=symbol, usd_sign=int(_USD_SIGN[symbol]),
                         y_fwd=d[f"y_fwd_pips_h{horizon}"].to_numpy(float),
                         cost=d["cost_est_pips"].to_numpy(float),
                         test_month=d["test_month"].to_numpy())
    return {"train": _split(train), "validation": _split(validation), "holdout": _split(holdout)}
