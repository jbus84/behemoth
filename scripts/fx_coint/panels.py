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
