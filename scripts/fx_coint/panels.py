from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from scripts.fx_coint.instruments import MAJORS

TICK_DIR = Path("data/tick_bars")


def resample_fine(df: pd.DataFrame, freq: str) -> pd.DataFrame:
    """Resample raw tick bars to a regular grid of log-mid + mean spread.

    Empty bins (no underlying ticks) are dropped — never forward-filled, so no
    fabricated prices across gaps/weekends. Returns a DatetimeIndex frame.
    """
    d = df.copy()
    d["close_ts"] = pd.to_datetime(d["close_ts"], utc=True, errors="coerce")
    d = d[d["close_ts"].notna()].set_index("close_ts").sort_index()
    mid = (d["close_bid"] + d["close_ask"]) / 2.0
    g = pd.DataFrame({"mid": mid, "spread": d["spread"]}).resample(freq)
    out = pd.DataFrame({
        "logmid": np.log(g["mid"].last()),
        "spread": g["spread"].mean(),
    })
    return out.dropna()


def load_fine(symbol: str, freq: str = "5min", bar: str = "100tick") -> pd.DataFrame:
    path = TICK_DIR / f"{symbol}_{bar}.parquet"
    return resample_fine(pd.read_parquet(path), freq)


def align_panel(per_symbol: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Inner-join per-symbol fine frames into a MultiIndex-column panel.

    Columns are (symbol, field) with field in {logmid, spread}. Inner join keeps
    only grid timestamps present in every leg; result has no NaNs.
    """
    frames = []
    for sym, f in per_symbol.items():
        cols = pd.MultiIndex.from_product([[sym], ["logmid", "spread"]])
        frames.append(pd.DataFrame(f[["logmid", "spread"]].to_numpy(),
                                   index=f.index, columns=cols))
    panel = pd.concat(frames, axis=1, join="inner").sort_index()
    return panel.dropna()


def load_aligned(freq: str = "5min", bar: str = "100tick",
                 symbols: list[str] | None = None) -> pd.DataFrame:
    syms = symbols or MAJORS
    return align_panel({s: load_fine(s, freq, bar) for s in syms})


def coarsen(fine_panel: pd.DataFrame, freq: str) -> pd.DataFrame:
    """Coarsen a fine MultiIndex panel: logmid=last, spread=mean per window."""
    out = {}
    for sym in fine_panel.columns.get_level_values(0).unique():
        g = fine_panel[sym].resample(freq)
        out[(sym, "logmid")] = g["logmid"].last()
        out[(sym, "spread")] = g["spread"].mean()
    res = pd.DataFrame(out)
    res.columns = pd.MultiIndex.from_tuples(res.columns)
    return res.dropna()


def walk_forward_windows(frame: pd.DataFrame, train_years: int = 2,
                         step_years: int = 1, purge: str = "5D"):
    """Yield (train_df, oos_df) tuples: rolling train_years window, the next
    step_years as OOS, separated by a purge gap. Look-ahead safe."""
    purge_td = pd.Timedelta(purge)
    start = frame.index.min().normalize()
    end = frame.index.max()
    wins = []
    tr_start = start
    while True:
        tr_end = tr_start + pd.DateOffset(years=train_years)
        oos_start = tr_end + purge_td
        oos_end = oos_start + pd.DateOffset(years=step_years)
        if oos_start >= end:
            break
        train = frame[(frame.index >= tr_start) & (frame.index < tr_end)]
        oos = frame[(frame.index >= oos_start) & (frame.index < oos_end)]
        if len(train) > 0 and len(oos) > 0:
            wins.append((train, oos))
        tr_start = tr_start + pd.DateOffset(years=step_years)
    return wins
