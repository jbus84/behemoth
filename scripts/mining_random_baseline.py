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

    Vectorised: draws all n_draws entry-sets upfront, calls
    family.measure_gross ONCE on the flattened (n_draws * n_entries)
    indices, and reshapes back to per-draw means. Same RNG seed yields
    bit-identical control statistics as the per-draw loop.
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

    n_draws = int(n_draws)
    n_entries = int(n_entries)
    # Per-row rng.choice loop is load-bearing: a 2D `size` with replace=False
    # would enforce global uniqueness across the whole output, not per-draw
    # uniqueness. Do not vectorise this loop.
    draws = np.stack([
        rng.choice(n_rows, size=n_entries, replace=False)
        for _ in range(n_draws)
    ])
    gross_flat = np.asarray(
        family.measure_gross(frame, draws.ravel(), params),
        dtype=float,
    )
    if gross_flat.shape[0] != n_draws * n_entries:
        raise ValueError(
            f"MiningFamily {getattr(family, 'name', '?')!r}.measure_gross returned "
            f"length {gross_flat.shape[0]} for {n_draws * n_entries} entries — "
            f"this violates the family protocol (measure_gross must return "
            f"len(entries) floats). This is a bug in the family implementation; "
            f"do not silently mask."
        )
    gross_per_draw = gross_flat.reshape(n_draws, n_entries)
    finite_mask = np.isfinite(gross_per_draw)
    finite_counts = finite_mask.sum(axis=1)
    with np.errstate(invalid="ignore"):
        sums = np.where(finite_mask, gross_per_draw, 0.0).sum(axis=1)
        control = np.where(finite_counts > 0, sums / finite_counts, np.nan)

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
