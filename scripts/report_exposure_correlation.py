#!/usr/bin/env python3
"""
Compute exposure correlation between MOM trades for M15/M30/M45/H1.
Outputs Pearson correlation for:
- net exposure (LONG=+1, SHORT=-1, summed across active trades)
- active trade count
- binary exposure (any trade active)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Iterable, Tuple

import csv
import math
import numpy as np
import pandas as pd

DATASETS = {
    "M15": ("data/meta_model/events_m15_8yr_v3_dual.csv", 15),
    "M30": ("data/meta_model/events_m30_8yr_v3_dual.csv", 30),
    "M45": ("data/meta_model/events_m45_8yr_v3_dual.csv", 45),
    "H1": ("data/meta_model/events_h1_8yr_v3_dual.csv", 60),
}

GRID_MINUTES = 15


@dataclass
class ExposureSeries:
    net: np.ndarray
    count: np.ndarray
    active: np.ndarray


def _iter_mom_rows(path: str) -> Iterable[Tuple[int, int, int]]:
    with open(path, newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if row.get("strategy_type") != "MOM":
                continue
            ts_raw = row.get("timestamp")
            if ts_raw is None:
                continue
            try:
                ts_ns = int(float(ts_raw))
            except ValueError:
                continue
            side = row.get("side", "").upper()
            sign = 1 if side == "LONG" else -1
            try:
                duration = int(float(row.get("duration_bars", 0)))
            except ValueError:
                duration = 0
            yield ts_ns, sign, duration


def _build_exposure_from_rows(
    rows: Iterable[Tuple[int, int, int]],
    bar_minutes: int,
    grid_start_ns: int,
    grid_end_ns: int,
    grid_minutes: int,
) -> ExposureSeries:
    minute_ns = 60 * 1_000_000_000
    bucket_ns = grid_minutes * minute_ns
    n = int((grid_end_ns - grid_start_ns) // bucket_ns + 1)
    diff_net = np.zeros(n + 1, dtype=float)
    diff_count = np.zeros(n + 1, dtype=float)

    for ts_ns, sign, duration in rows:
        if duration <= 0:
            continue
        start_idx = (ts_ns - grid_start_ns) // bucket_ns
        end_ns = ts_ns + duration * bar_minutes * minute_ns
        end_idx = (end_ns - grid_start_ns) // bucket_ns
        if end_idx <= start_idx:
            continue
        if start_idx < 0:
            start_idx = 0
        if end_idx > n:
            end_idx = n
        diff_net[start_idx] += sign
        diff_net[end_idx] -= sign
        diff_count[start_idx] += 1.0
        diff_count[end_idx] -= 1.0

    net = np.cumsum(diff_net[:-1])
    count = np.cumsum(diff_count[:-1])
    active = (count > 0).astype(float)
    return ExposureSeries(net=net, count=count, active=active)


def _corr_matrix(series_map: Dict[str, np.ndarray]) -> pd.DataFrame:
    keys = list(series_map.keys())
    data = np.zeros((len(keys), len(keys)))
    for i, k1 in enumerate(keys):
        for j, k2 in enumerate(keys):
            s1 = series_map[k1]
            s2 = series_map[k2]
            if np.std(s1) < 1e-9 or np.std(s2) < 1e-9:
                data[i, j] = math.nan
            else:
                data[i, j] = float(np.corrcoef(s1, s2)[0, 1])
    return pd.DataFrame(data, index=keys, columns=keys)


def main() -> None:
    # First pass: determine global grid bounds without holding all dataframes.
    min_ts = None
    max_ts = None
    minute_ns = 60 * 1_000_000_000
    for _, (path, minutes) in DATASETS.items():
        for ts_ns, _, duration in _iter_mom_rows(path):
            min_ts = ts_ns if min_ts is None else min(min_ts, ts_ns)
            end_ns = ts_ns + duration * minutes * minute_ns
            max_ts = end_ns if max_ts is None else max(max_ts, end_ns)

    if min_ts is None or max_ts is None:
        print("No MOM trades found for correlation.")
        return

    bucket_ns = GRID_MINUTES * minute_ns
    grid_start_ns = (min_ts // bucket_ns) * bucket_ns
    grid_end_ns = ((max_ts + bucket_ns - 1) // bucket_ns) * bucket_ns

    exposures = {}
    for label, (path, minutes) in DATASETS.items():
        rows = _iter_mom_rows(path)
        exposures[label] = _build_exposure_from_rows(rows, minutes, grid_start_ns, grid_end_ns, GRID_MINUTES)

    net_corr = _corr_matrix({k: v.net for k, v in exposures.items()})
    count_corr = _corr_matrix({k: v.count for k, v in exposures.items()})
    active_corr = _corr_matrix({k: v.active for k, v in exposures.items()})

    print("\nExposure correlation (net, LONG=+1/SHORT=-1, 15m grid):")
    print(net_corr.round(3).to_string())
    print("\nExposure correlation (active trade count, 15m grid):")
    print(count_corr.round(3).to_string())
    print("\nExposure correlation (binary active, 15m grid):")
    print(active_corr.round(3).to_string())


if __name__ == "__main__":
    main()
