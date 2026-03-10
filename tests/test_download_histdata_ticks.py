from __future__ import annotations

import pandas as pd

from scripts.download_histdata_ticks import _convert_histdata_timestamps


def test_histdata_timestamp_conversion_new_york_dst_summer() -> None:
    raw = pd.Series(["20250708 000000000"])
    ts = _convert_histdata_timestamps(raw, source_tz_policy="america_new_york")
    assert ts.iloc[0].isoformat() == "2025-07-08T04:00:00+00:00"


def test_histdata_timestamp_conversion_new_york_standard_winter() -> None:
    raw = pd.Series(["20251208 000000000"])
    ts = _convert_histdata_timestamps(raw, source_tz_policy="america_new_york")
    assert ts.iloc[0].isoformat() == "2025-12-08T05:00:00+00:00"


def test_histdata_timestamp_conversion_fixed_est() -> None:
    raw = pd.Series(["20250708 000000000"])
    ts = _convert_histdata_timestamps(raw, source_tz_policy="fixed_est")
    assert ts.iloc[0].isoformat() == "2025-07-08T05:00:00+00:00"
