from __future__ import annotations


LEGACY_MAX_HOLD_BARS = 500

# Entry-|z| buckets -> timeout bars by timeframe.
_ADAPTIVE_TIMEOUT_BUCKETS = {
    "m5": [
        (1.5, 2.0, 180),
        (2.0, 2.5, 260),
        (2.5, 3.0, 360),
        (3.0, float("inf"), 500),
    ],
    "m15": [
        (1.5, 2.0, 120),
        (2.0, 2.5, 180),
        (2.5, 3.0, 260),
        (3.0, float("inf"), 400),
    ],
    "m60": [
        (1.5, 2.0, 80),
        (2.0, 2.5, 120),
        (2.5, 3.0, 180),
        (3.0, float("inf"), 280),
    ],
}


def compute_max_hold_bars(timeframe: str, abs_entry_z: float, mode: str = "fixed") -> int:
    if mode == "fixed":
        return LEGACY_MAX_HOLD_BARS

    if mode != "adaptive_entry_z":
        raise ValueError(f"Unsupported timeout mode: {mode}")

    tf = timeframe.lower().strip()
    if tf not in _ADAPTIVE_TIMEOUT_BUCKETS:
        raise ValueError(f"Unsupported timeframe for adaptive timeout: {timeframe}")

    z = max(float(abs_entry_z), 0.0)
    for lo, hi, bars in _ADAPTIVE_TIMEOUT_BUCKETS[tf]:
        if z >= lo and z < hi:
            return max(1, min(int(bars), LEGACY_MAX_HOLD_BARS))

    return LEGACY_MAX_HOLD_BARS
