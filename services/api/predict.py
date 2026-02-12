import functools
import numpy as np
import pandas as pd

from behemoth.config import ACTIVE_LEG_HIGH, ACTIVE_LEG_LOW, MIN_GAP_BARS, Z_ENTRY_MOM, Z_STOP
from behemoth.core.active_leg import select_active_leg
from behemoth.core.events import simulate_trade
from behemoth.core.kalman import compute_kalman_states
from behemoth.core.zscore import compute_z_scores
from behemoth.io.loaders import load_pair_data
from pipelines.build_events_m5 import PAIRS as M5_PAIRS
from pipelines.build_events_m15 import PAIRS as M15_PAIRS

PAIR_MAP = {
    "m5": M5_PAIRS,
    "m15": M15_PAIRS,
}

DATA_DIR = {
    "m5": "data/global_5m",
    "m15": "data/global_15m",
}


def _normalize_ts(ts):
    if np.issubdtype(ts.dtype, np.datetime64):
        return ts.astype("datetime64[ns]").astype("int64")
    return ts.astype("int64")


def get_pair_spec(bar: str, pair: str):
    if bar not in PAIR_MAP:
        raise ValueError(f"Unknown bar: {bar}")
    for name, fx, fy, cx, cy, *_ in PAIR_MAP[bar]:
        if name == pair:
            return name, fx, fy, cx, cy
    raise ValueError(f"Unknown pair: {pair}")


def load_pair_series(bar: str, pair: str):
    name, fx, fy, cx, cy = get_pair_spec(bar, pair)
    df = load_pair_data(DATA_DIR[bar], fx, fy, cx, cy)
    if df is None or df.height == 0:
        return None
    y = np.log(df["Y"].to_numpy())
    x = np.log(df["X"].to_numpy())
    ts = _normalize_ts(df["timestamp"].to_numpy())
    return ts, y, x


def compute_exit_ts(
    entry_ts: int, duration: int, bar_minutes: int, ts_series: np.ndarray, entry_idx: int
):
    bar_ns = int(pd.Timedelta(minutes=bar_minutes).value)
    if duration >= 500:
        idx = min(entry_idx + 499, len(ts_series) - 1)
        return int(ts_series[idx])
    return int(entry_ts + duration * bar_ns)


@functools.lru_cache(maxsize=64)
def generate_mom_events_for_pair(bar: str, pair: str) -> tuple[dict, ...]:
    series = load_pair_series(bar, pair)
    if series is None:
        return ()
    ts, y, x = series
    betas, errors, _ = compute_kalman_states(y, x)
    z_scores = compute_z_scores(errors)

    events = []
    last_entry = -10_000
    for i in range(len(z_scores)):
        z = z_scores[i]
        if abs(z) < Z_ENTRY_MOM:
            continue
        if i - last_entry < MIN_GAP_BARS:
            continue
        active = select_active_leg(betas[i], ACTIVE_LEG_LOW, ACTIVE_LEG_HIGH)
        if active is None:
            continue
        direction = 1 if z > 0 else -1
        pnl, duration, outcome = simulate_trade(
            i, direction, "MOM", y, x, z_scores, active, Z_ENTRY_MOM, Z_STOP
        )
        entry_ts = int(ts[i])
        exit_ts = compute_exit_ts(entry_ts, duration, 5 if bar == "m5" else 15, ts, i)
        events.append(
            {
                "pair": pair,
                "entry_ts": entry_ts,
                "exit_ts": exit_ts,
                "side": "LONG" if direction == 1 else "SHORT",
                "active_leg": active,
                "pnl_bps": float(round(pnl, 6)),
                "duration_bars": int(duration),
                "outcome": outcome,
            }
        )
        last_entry = i
    return tuple(events)
