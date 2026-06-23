"""Target predictability report card — funnel orchestration.

Two-stage funnel per target: Stage C (well-posedness) gates Stage A (bracketed
intrinsic ceiling). A target failing C hard is flagged ill-posed and Stage A is
skipped to save compute (override with run_ceiling_on_illposed=True).

CLI: `uv run python scripts/fx_coint/target_report.py`
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from target_ceiling import ceiling_bracket  # noqa: E402
from target_wellposedness import (  # noqa: E402
    class_balance,
    effective_n,
    label_noise,
    regime_stability,
    temporal_concentration,
)


@dataclass
class ReportCard:
    name: str
    kind: str
    wellposed: dict
    wellposed_verdict: str
    ceiling: dict | None
    ceiling_verdict: str


def wellposedness_verdict(wp: dict, min_overlap: float = 0.1,
                          max_concentration: float = 0.8) -> str:
    if wp.get("overlap_ratio", 1.0) < min_overlap:
        return "ill-posed"
    if wp.get("top1pct_share", 0.0) > max_concentration:
        return "ill-posed"
    ent = wp.get("entropy", float("nan"))
    if np.isfinite(ent) and ent < 0.1:
        return "ill-posed"
    return "well-posed"


def score_target(name, kind, labels, signal, day_index, split_idx, X, y_ceiling,
                 t1, *, barrier_args=None, run_ceiling_on_illposed=False,
                 rng=None) -> ReportCard:
    wp = {}
    wp.update(effective_n(labels))
    wp.update(temporal_concentration(signal, day_index))
    wp.update(class_balance(labels, kind))
    wp.update(regime_stability(labels, split_idx, kind))
    if barrier_args is not None:
        wp.update(label_noise(barrier_args["logp"], barrier_args["ev"],
                              barrier_args["vert"], barrier_args["width"],
                              barrier_args["perturb"]))
    verdict = wellposedness_verdict(wp)
    if verdict == "ill-posed" and not run_ceiling_on_illposed:
        return ReportCard(name, kind, wp, verdict, None, "skipped")
    cb = ceiling_bracket(X, y_ceiling, t1, kind, rng=rng)
    cv = "signal" if (np.isfinite(cb["lower_p"]) and cb["lower_p"] < 0.05) \
        else "null-indistinguishable"
    return ReportCard(name, kind, wp, verdict, cb, cv)


if __name__ == "__main__":
    pass
