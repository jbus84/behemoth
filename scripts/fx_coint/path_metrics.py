"""Signed path excursions (terminal / max-favorable / max-adverse) in sigma units."""
from __future__ import annotations

import numpy as np


def path_excursions(entry_mid: float, minutes: np.ndarray, side: str,
                    sigma_bps: float) -> dict:
    if len(minutes) < 1 or sigma_bps <= 0:
        return {"terminal_sigma": float("nan"), "mfe_sigma": float("nan"),
                "mae_sigma": float("nan"), "terminal_bps": float("nan"), "n_steps": 0}
    sign = 1.0 if side == "long" else -1.0
    signed_bps = sign * (np.log(minutes) - np.log(entry_mid)) * 1e4
    mfe = float(max(0.0, signed_bps.max()))
    mae = float(min(0.0, signed_bps.min()))
    term = float(signed_bps[-1])
    return {"terminal_sigma": term / sigma_bps, "mfe_sigma": mfe / sigma_bps,
            "mae_sigma": mae / sigma_bps, "terminal_bps": term, "n_steps": len(minutes)}
