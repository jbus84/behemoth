#!/usr/bin/env python3
"""
Reusable risk-control utilities.
"""

from __future__ import annotations

import numpy as np


def vol_target_scale(
    vol: float,
    target_vol: float,
    cap: float = 2.0,
    floor: float = 0.2,
    eps: float = 1e-12,
) -> float:
    if not np.isfinite(vol) or vol <= eps or not np.isfinite(target_vol) or target_vol <= eps:
        return 1.0
    scale = target_vol / vol
    return float(np.clip(scale, floor, cap))


def conditional_vol_scale(
    vol: float,
    target_vol: float,
    high_vol_thresh: float,
    cap: float = 2.0,
    floor: float = 0.2,
) -> float:
    if not np.isfinite(vol) or not np.isfinite(high_vol_thresh):
        return 1.0
    if vol <= high_vol_thresh:
        return 1.0
    return vol_target_scale(vol, target_vol, cap=cap, floor=floor)
