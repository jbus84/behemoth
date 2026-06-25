"""Causal per-tick feature panel + multi-day split for the ERA tick search.

One streaming pass per symbol-day (reusing the Phase-1 Kalman + regime) produces a panel of
strictly causal features; rolling stats are computed within the day only (never across day
boundaries, so there is no overnight bleed). Panels are cached to parquet. `build_split`
concatenates days into a `TickSplit` whose `X`/`names` feed the sandbox `signal(ctx)` program
and whose `bid`/`ask`/`day` arrays drive the tick-exact executor in `era_exec`.

Feature columns (all causal):
  mid_hat, drift_hat, drift_t, residual_z, regime_code, spread_pips,
  accel, rvol_fast, rvol_slow, eff_ratio, range_z, tick_rate, hour
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.era_tick import pip_size
from scripts.era_tick.micro_price import KalmanMicroPrice
from scripts.era_tick.regime import Regime, RegimeDetector
from scripts.era_tick.tick_replay import TickReplay

FEATURE_NAMES: list[str] = [
    "mid_hat",
    "drift_hat",
    "drift_t",
    "residual_z",
    "regime_code",
    "spread_pips",
    "accel",
    "rvol_fast",
    "rvol_slow",
    "eff_ratio",
    "range_z",
    "tick_rate",
    "hour",
]

_REGIME_CODE = {
    Regime.WARMUP: 0,
    Regime.SHOCK: 1,
    Regime.DRIFT: 2,
    Regime.REVERT: 3,
    Regime.CHURN: 4,
}
DRIFT_CODE = _REGIME_CODE[Regime.DRIFT]

_PANEL_DIR = Path("data/era_tick/panels")
_FAST, _SLOW = 50, 500  # rolling windows (ticks) for realized vol / range_z


@dataclass
class TickSplit:
    """Concatenated multi-day panel. X/names feed the program; bid/ask/day drive fills."""

    X: np.ndarray
    names: list[str]
    hour: np.ndarray
    bid: np.ndarray
    ask: np.ndarray
    mid: np.ndarray
    day: np.ndarray
    pip: float


def _streaming_core(replay: TickReplay) -> dict[str, np.ndarray]:
    """Per-tick Kalman + regime pass (inherently sequential)."""
    kf = KalmanMicroPrice()
    reg = RegimeDetector(pip=replay.pip)
    n = len(replay)
    cols = {
        k: np.zeros(n)
        for k in (
            "bid",
            "ask",
            "mid",
            "dt",
            "hour",
            "spread_pips",
            "mid_hat",
            "drift_hat",
            "drift_t",
            "residual_z",
            "regime_code",
            "eff_ratio",
        )
    }
    for t in replay:
        kf.set_measurement_var(max((0.5 * t.spread) ** 2, 1.0e-12))
        m = kf.update(t.mid, t.dt)
        r = reg.update(t.mid)
        i = t.i
        cols["bid"][i] = t.bid
        cols["ask"][i] = t.ask
        cols["mid"][i] = t.mid
        cols["dt"][i] = t.dt
        cols["hour"][i] = t.ts.hour
        cols["spread_pips"][i] = t.spread / replay.pip
        cols["mid_hat"][i] = m.mid_hat
        cols["drift_hat"][i] = m.drift_hat
        cols["drift_t"][i] = m.drift_t()
        cols["residual_z"][i] = m.residual_z()
        cols["regime_code"][i] = _REGIME_CODE[r.regime]
        cols["eff_ratio"][i] = r.efficiency_ratio
    return cols


def _derived_features(cols: dict[str, np.ndarray], pip: float) -> dict[str, np.ndarray]:
    """Vectorised causal rolling features over the day (shift(1), no future leakage)."""
    mid = pd.Series(cols["mid"])
    ret_pips = mid.diff().fillna(0.0) / pip
    rvol_fast = ret_pips.rolling(_FAST, min_periods=_FAST).std().shift(1)
    rvol_slow = ret_pips.rolling(_SLOW, min_periods=_SLOW).std().shift(1)
    # range_z: current fast realized vol vs its own slow baseline (how active is "now").
    base_mean = rvol_fast.rolling(_SLOW, min_periods=_FAST).mean()
    base_std = rvol_fast.rolling(_SLOW, min_periods=_FAST).std()
    range_z = (rvol_fast - base_mean) / base_std.replace(0.0, np.nan)
    drift = pd.Series(cols["drift_hat"])
    accel = drift.diff(10).shift(1)  # change in drift over 10 ticks, lagged
    # tick_rate: EWMA of ticks/sec (1/dt), causal.
    inv_dt = pd.Series(np.where(cols["dt"] > 0, 1.0 / np.maximum(cols["dt"], 1e-3), 0.0))
    tick_rate = inv_dt.ewm(span=_FAST, min_periods=_FAST).mean().shift(1)
    return {
        "accel": accel.to_numpy(),
        "rvol_fast": rvol_fast.to_numpy(),
        "rvol_slow": rvol_slow.to_numpy(),
        "range_z": range_z.to_numpy(),
        "tick_rate": tick_rate.to_numpy(),
    }


def panel_from_replay(replay: TickReplay, day: str) -> pd.DataFrame:
    """Build the causal feature panel from an in-memory replay (testable; no disk)."""
    if len(replay) == 0:
        return pd.DataFrame()
    cols = _streaming_core(replay)
    cols.update(_derived_features(cols, replay.pip))
    frame = {"day": day, "bid": cols["bid"], "ask": cols["ask"], "mid": cols["mid"]}
    for name in FEATURE_NAMES:
        frame[name] = cols[name]
    df = pd.DataFrame(frame)
    # Non-finite causal features (warmup rows) -> 0.0; a program may still gate them out.
    df[FEATURE_NAMES] = df[FEATURE_NAMES].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return df


def build_panel_day(symbol: str, day: str) -> pd.DataFrame:
    """Build (uncached) the causal feature panel for one symbol-day. Empty df if no ticks."""
    return panel_from_replay(TickReplay.for_day(symbol, day), day)


def load_or_build_panel(symbol: str, day: str) -> pd.DataFrame:
    _PANEL_DIR.mkdir(parents=True, exist_ok=True)
    path = _PANEL_DIR / f"{symbol.upper()}_{day}.parquet"
    if path.exists():
        return pd.read_parquet(path)
    df = build_panel_day(symbol, day)
    if not df.empty:
        df.to_parquet(path)
    return df


def build_split(symbol: str, days: list[str]) -> TickSplit:
    """Concatenate per-day panels into one split for the ERA scorer."""
    frames = [df for d in days if not (df := load_or_build_panel(symbol, d)).empty]
    if not frames:
        raise ValueError(f"{symbol}: no tradable days in {days[:3]}…")
    panel = pd.concat(frames, ignore_index=True)
    return TickSplit(
        X=panel[FEATURE_NAMES].to_numpy(float),
        names=list(FEATURE_NAMES),
        hour=panel["hour"].to_numpy(float),
        bid=panel["bid"].to_numpy(float),
        ask=panel["ask"].to_numpy(float),
        mid=panel["mid"].to_numpy(float),
        day=panel["day"].to_numpy(),
        pip=pip_size(symbol),
    )
