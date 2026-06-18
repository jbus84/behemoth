"""Causal price + order-flow channels for the hourly direction harness."""
from __future__ import annotations

import numpy as np
import pandas as pd


def _zcausal(s: pd.Series, w: int) -> pd.Series:
    mu = s.rolling(w, min_periods=w).mean().shift(1)
    sd = s.rolling(w, min_periods=w).std().shift(1)
    return ((s - mu) / (sd + 1e-12)).fillna(0.0)


def add_channels(df: pd.DataFrame, z_window: int = 24, cum_window: int = 6) -> pd.DataFrame:
    out = df.copy()
    # --- price channels (causal) ---
    out["mid_ret"] = np.log(out["mid"]).diff().fillna(0.0)
    out["norm_ret"] = _zcausal(out["mid_ret"], z_window)
    raw_spread = out["ask"] - out["bid"]
    out["raw_spread_norm"] = _zcausal(raw_spread, z_window)
    # --- raw flow channels (causal z) ---
    for c in ["flow_tick", "flow_ofi", "n_ticks", "rvol_bps", "spread_bps"]:
        out[f"{c}_z"] = _zcausal(out[c], z_window)
    # --- engineered flow channels (causal) ---
    out["cum_flow_tick"] = out["flow_tick"].rolling(cum_window, min_periods=1).sum()
    out["cum_flow_ofi"] = out["flow_ofi"].rolling(cum_window, min_periods=1).sum()
    out["dflow_ofi"] = out["flow_ofi"].diff().fillna(0.0)
    out["ofi_z"] = _zcausal(out["flow_ofi"], z_window)
    out["actflow"] = out["flow_tick"] * out["n_ticks"]
    out["actflow_z"] = _zcausal(out["actflow"], z_window)
    # flow-price divergence: flow_ofi orthogonalised to contemporaneous return,
    # via causal rolling univariate regression residual (beta uses past only).
    x = out["mid_ret"]; y = out["flow_ofi"]
    cov = (x * y).rolling(z_window, min_periods=z_window).mean().shift(1)
    var = (x * x).rolling(z_window, min_periods=z_window).mean().shift(1)
    beta = (cov / (var + 1e-12)).fillna(0.0)
    out["flow_resid"] = (out["flow_ofi"] - beta * out["mid_ret"]).fillna(0.0)
    out["flow_resid_z"] = _zcausal(out["flow_resid"], z_window)
    return out


ARMS: dict[str, list[str]] = {
    "price_only": ["mid_ret", "norm_ret", "raw_spread_norm"],
    "raw_flow": ["flow_tick_z", "flow_ofi_z", "n_ticks_z", "rvol_bps_z", "spread_bps_z"],
    "engineered": ["cum_flow_tick", "cum_flow_ofi", "dflow_ofi", "ofi_z",
                   "actflow_z", "flow_resid_z"],
}
ARMS["both"] = ARMS["price_only"] + ARMS["raw_flow"] + ARMS["engineered"]


def build_panel(df: pd.DataFrame, channels: list[str], lookback: int):
    arr = df[channels].to_numpy(dtype=np.float64)
    n = len(df)
    ns = n - lookback
    X = np.empty((ns, len(channels), lookback), dtype=np.float64)
    for i in range(ns):
        X[i] = arr[i : i + lookback].T
    y = df["tb_label"].to_numpy()[lookback:].astype(np.int8)
    pos = np.arange(ns)
    return X, y, pos
