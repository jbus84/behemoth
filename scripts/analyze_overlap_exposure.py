#!/usr/bin/env python3
"""
Cross-pair overlap and exposure analysis.
Reports max concurrent trades and pair-group overlap by underlying legs.
Outputs:
- data/analysis/m5_overlap_exposure.csv
- data/analysis/m15_overlap_exposure.csv
"""

from __future__ import annotations

import os
import sys
import numpy as np
import pandas as pd

sys.path.append(os.path.join(os.getcwd(), "scripts"))
from pipelines import build_events_m5 as m5
from pipelines import build_events_m15 as m15

OUT_DIR = "data/analysis"

CONFIGS = [
    ("m5", "data/events/events_m5_8yr_v3_mom.csv", m5, 5),
    ("m15", "data/events/events_m15_8yr_v3_mom.csv", m15, 15),
]


def _pair_map(module):
    return {name: (fx, fy, cx, cy) for name, fx, fy, cx, cy, *_ in module.PAIRS}


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    for label, path, module, bar_minutes in CONFIGS:
        df = pd.read_csv(path, usecols=["pair", "timestamp", "duration_bars"])
        df["timestamp"] = df["timestamp"].astype("int64")
        bar_ns = int(pd.Timedelta(minutes=bar_minutes).value)
        durations = df["duration_bars"].astype(int)
        timeout_adjust = (durations >= 500).astype(int)
        df["exit_ts"] = df["timestamp"] + ((durations - timeout_adjust) * bar_ns)

        pair_info = _pair_map(module)
        # map pair -> legs (X,Y file names for grouping)
        pair_legs = {name: (fx, fy) for name, (fx, fy, *_rest) in pair_info.items()}

        # Build events list
        events = []
        for row in df.itertuples(index=False):
            legs = pair_legs.get(row.pair, (None, None))
            events.append((int(row.timestamp), int(row.exit_ts), row.pair, legs))

        # Overlap counts by shared leg
        shared_overlap = 0
        total_overlap = 0

        # naive O(n^2) but manageable for summary by day: bucket by day for speed
        df["entry_day"] = pd.to_datetime(df["timestamp"], unit="ns", utc=True, errors="coerce").dt.normalize()
        for day, sub in df.groupby("entry_day"):
            subs = []
            for row in sub.itertuples(index=False):
                legs = pair_legs.get(row.pair, (None, None))
                subs.append((int(row.timestamp), int(row.exit_ts), row.pair, legs))
            # check overlaps within day
            for i in range(len(subs)):
                s1, e1, p1, l1 = subs[i]
                for j in range(i + 1, len(subs)):
                    s2, e2, p2, l2 = subs[j]
                    if s2 >= e1 or s1 >= e2:
                        continue
                    total_overlap += 1
                    if l1[0] in l2 or l1[1] in l2:
                        shared_overlap += 1

        overlap_rate = shared_overlap / total_overlap if total_overlap else 0.0

        out = pd.DataFrame(
            [
                {
                    "timeframe": label,
                    "total_overlaps": int(total_overlap),
                    "shared_leg_overlaps": int(shared_overlap),
                    "shared_leg_overlap_rate": float(overlap_rate),
                }
            ]
        )
        out.to_csv(os.path.join(OUT_DIR, f"{label}_overlap_exposure.csv"), index=False)
        print(f"Saved: {OUT_DIR}/{label}_overlap_exposure.csv")


if __name__ == "__main__":
    main()
