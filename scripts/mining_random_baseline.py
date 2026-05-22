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


def _draw_batch_and_score(
    family: MiningFamily,
    frame: pd.DataFrame,
    params: dict[str, Any],
    *,
    n_entries: int,
    n_draws: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Draw `n_draws` entry-sets, call measure_gross ONCE on the flattened
    indices, return the per-draw control means (NaN-bearing, not filtered)."""
    n_rows = len(frame)
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
    return control


def random_entry_baseline(
    family: MiningFamily,
    frame: pd.DataFrame,
    params: dict[str, Any],
    *,
    n_entries: int,
    n_draws: int,
    rng: np.random.Generator,
    candidate_gross_ev: float | None = None,
    probe_draws: int = 20,
    interesting_bar_z: float = 1.5,
    se_margin: float = 2.0,
) -> dict[str, float]:
    """Return random_baseline_z / random_baseline_p /
    random_baseline_control_mean for a candidate.

    Two-stage short-circuit (for speed, when `candidate_gross_ev` is given):

    1. Run `probe_draws` draws (default 20).
    2. Estimate z_partial and its sampling SE. If |z_partial| + se_margin · SE
       is bounded below `interesting_bar_z` (default 1.5), the final |z| is
       statistically certain to land in the boring band — return early.
    3. Otherwise, run the remaining `n_draws - probe_draws` draws and report
       the full-sample statistics. Bit-identical to a single-pass run with
       the same RNG seed (rng.choice is called in the same order regardless
       of whether we batch the draws).

    Setting `probe_draws >= n_draws` disables the short-circuit and is the
    bit-identical path for parity tests.
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
    probe_draws = max(1, min(int(probe_draws), n_draws))

    # Stage 1: probe.
    probe_control = _draw_batch_and_score(
        family, frame, params,
        n_entries=n_entries, n_draws=probe_draws, rng=rng,
    )
    finite_probe = probe_control[np.isfinite(probe_control)]

    # Short-circuit decision (only meaningful when we have a candidate EV
    # AND there are remaining draws we could skip).
    short_circuit = False
    if (
        candidate_gross_ev is not None
        and probe_draws < n_draws
        and finite_probe.size >= 3
    ):
        cm_p = float(np.mean(finite_probe))
        cs_p = float(np.std(finite_probe))
        if cs_p > 0.0:
            z_partial = (float(candidate_gross_ev) - cm_p) / cs_p
            # Approximate SE of the z estimator from `probe_draws` draws.
            # In the noise regime (z ≈ 0), the sampling distribution of
            # the z-statistic over many bootstrap reruns has SE ≈ 1/sqrt(k).
            se_z = 1.0 / float(np.sqrt(probe_draws))
            if abs(z_partial) + se_margin * se_z < float(interesting_bar_z):
                short_circuit = True

    if short_circuit:
        # Report the partial result; downstream consumers treat z near zero
        # as "no edge". Bias is bounded by the gate above.
        return {
            "random_baseline_z": z_partial,
            "random_baseline_p": float(
                np.mean(finite_probe >= float(candidate_gross_ev))
            ),
            "random_baseline_control_mean": cm_p,
        }

    # Stage 2: complete the remaining draws (if any).
    remaining = n_draws - probe_draws
    if remaining > 0:
        more_control = _draw_batch_and_score(
            family, frame, params,
            n_entries=n_entries, n_draws=remaining, rng=rng,
        )
        control = np.concatenate([probe_control, more_control])
    else:
        control = probe_control

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
