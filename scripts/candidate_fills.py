"""Per-fill logging for the tick opportunity mining pipeline.

One row per individual fill for every positive-EV candidate, capturing the
fill outcome and a snapshot of the entry-time features. See
docs/superpowers/specs/2026-05-19-candidate-fill-logging-design.md.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def candidate_id(
    symbol: str,
    library_type: str,
    family: str,
    bar_ticks: int,
    horizon: int,
    regime: str,
    params: dict[str, Any],
) -> str:
    """A deterministic 12-hex-char identifier for one mining candidate.

    Stable across runs, so a candidate's fills can be diffed between retrains.
    The param dict is sorted so dict ordering does not affect the hash.
    """
    payload = repr((
        str(symbol),
        str(library_type),
        str(family),
        int(bar_ticks),
        int(horizon),
        str(regime),
        sorted((str(k), repr(v)) for k, v in params.items()),
    ))
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]
