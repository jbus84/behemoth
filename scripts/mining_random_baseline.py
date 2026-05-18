"""Random-entry baseline for mined candidates.

For a candidate with N entries, draw N random entry indices from the whole
frame n_draws times, run the family's own measure_gross on each draw, and
score the candidate's gross EV against the control distribution.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from scripts.mining_family import MiningFamily


def random_entry_baseline(
    family: MiningFamily,
    frame: pd.DataFrame,
    params: dict[str, Any],
    *,
    n_entries: int,
    n_draws: int,
    rng: np.random.Generator,
    candidate_gross_ev: float | None = None,
) -> dict[str, float]:
    """Return random_baseline_z / random_baseline_p /
    random_baseline_control_mean for a candidate.

    candidate_gross_ev is the candidate's own mean gross pips; when None the
    z/p fields are NaN but the control mean is still returned.
    """
    n_rows = len(frame)
    nan_result = {
        "random_baseline_z": float("nan"),
        "random_baseline_p": float("nan"),
        "random_baseline_control_mean": float("nan"),
    }
    if n_entries <= 0 or n_entries > n_rows:
        print(
            f"warning: random baseline skipped (n_entries={n_entries}, "
            f"frame rows={n_rows})"
        )
        return nan_result

    control = np.empty(int(n_draws), dtype=float)
    for i in range(int(n_draws)):
        draw = rng.choice(n_rows, size=int(n_entries), replace=False)
        gross = np.asarray(family.measure_gross(frame, draw, params), dtype=float)
        gross = gross[np.isfinite(gross)]
        control[i] = float(np.mean(gross)) if gross.size else float("nan")

    control = control[np.isfinite(control)]
    if control.size == 0:
        return nan_result
    control_mean = float(np.mean(control))
    control_std = float(np.std(control))
    if candidate_gross_ev is None:
        return {
            "random_baseline_z": float("nan"),
            "random_baseline_p": float("nan"),
            "random_baseline_control_mean": control_mean,
        }
    if control_std == 0.0:
        print("warning: random baseline control_std is zero — z/p set to NaN")
        return {
            "random_baseline_z": float("nan"),
            "random_baseline_p": float("nan"),
            "random_baseline_control_mean": control_mean,
        }
    z = (float(candidate_gross_ev) - control_mean) / control_std
    p = float(np.mean(control >= float(candidate_gross_ev)))
    return {
        "random_baseline_z": z,
        "random_baseline_p": p,
        "random_baseline_control_mean": control_mean,
    }
