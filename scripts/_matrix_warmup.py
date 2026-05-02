"""Compute warmup-tick budget for matrix runners.

Without this, matrix runners default to a fixed --warmup-ticks=30000 which
produces ~30 bars at the candidate's 1000-tick bar size - well below the
runtime's full_warmup_bars gate (max(vol_window, cost_window) + 1 = 289).
The matrix then accumulates bars in real time before predictions can fire,
costing 2-5 days of zero-prediction cycles (and never recovering for the
lowest-tick-rate symbol within a 3-day window).

This module derives the required tick budget from the largest bar_ticks
across the locked candidate set, with a safety margin.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pandas as pd

from src.behemoth.core.features import FeatureConfig

WARMUP_TICKS_AUTO = 0
DEFAULT_MARGIN = 1.2
FALLBACK_WARMUP_TICKS = 30_000


def parse_bar_ticks_from_uid(candidate_uid: str) -> int | None:
    """Extract bar_ticks from a candidate UID of the form ``oco|SYM|N|h*|...``."""
    parts = str(candidate_uid).split("|")
    if len(parts) < 3:
        return None
    try:
        return int(parts[2])
    except (TypeError, ValueError):
        return None


def max_bar_ticks_for_symbols(
    *,
    symbols: Iterable[str],
    locked_predictions_dir: Path,
    model_month: str = "",
) -> int:
    """Return the largest bar_ticks across locked candidates for the given symbols.

    When ``model_month`` is non-empty, looks under
    ``locked_predictions_dir/model_month/<sym>_oco_locked_predictions.parquet``.
    When empty, treats ``locked_predictions_dir`` as a flat directory containing
    ``<sym>_oco_locked_predictions.parquet`` directly.

    Returns 0 when no locked predictions are found.
    """
    max_bt = 0
    base = Path(locked_predictions_dir)
    for sym in symbols:
        filename = f"{sym.lower()}_oco_locked_predictions.parquet"
        path = base / model_month / filename if model_month else base / filename
        if not path.exists():
            continue
        df = pd.read_parquet(path, columns=["candidate_uid"])
        for uid in df["candidate_uid"].drop_duplicates():
            bt = parse_bar_ticks_from_uid(uid)
            if bt is not None and bt > max_bt:
                max_bt = bt
    return max_bt


def compute_required_warmup_ticks(
    *,
    symbols: Iterable[str],
    locked_predictions_dir: Path,
    model_month: str = "",
    margin: float = DEFAULT_MARGIN,
    feature_cfg: FeatureConfig | None = None,
) -> int:
    """Compute warmup-tick budget so the runtime's full_warmup_bars gate
    is satisfied at the largest candidate bar_ticks, with a safety margin.

    Falls back to FALLBACK_WARMUP_TICKS if no locked candidates can be read.
    """
    cfg = feature_cfg or FeatureConfig()
    max_bt = max_bar_ticks_for_symbols(
        symbols=symbols,
        locked_predictions_dir=locked_predictions_dir,
        model_month=model_month,
    )
    if max_bt <= 0:
        return FALLBACK_WARMUP_TICKS
    return int(cfg.full_warmup_bars * max_bt * margin)


def compute_bar_align_ticks(
    *,
    symbols: Iterable[str],
    locked_predictions_dir: Path,
    model_month: str = "",
) -> int:
    """Auto-derive the alignment modulus for warmup tick loading.

    Returns the largest candidate ``bar_ticks`` across the locked set.
    Returns 0 when no locked predictions are discoverable; the matrix
    runner is expected to fail fast in that case rather than fall back
    to a default that re-introduces the alignment bug.
    """
    return max_bar_ticks_for_symbols(
        symbols=symbols,
        locked_predictions_dir=locked_predictions_dir,
        model_month=model_month,
    )


def align_keep(warmup_ticks: int, align: int, full_pre_count: int) -> int:
    """Size the warmup-tick keep window so its modulo matches governance.

    Property: ``align_keep(w, a, p) >= w`` and
    ``align_keep(w, a, p) % a == p % a`` for any non-negative ``w``,
    positive ``a``, non-negative ``p``. This makes the runtime's open-bar
    accumulator at end-of-warmup equal to what governance had at the same
    absolute tick position without shaving the requested Warmup budget.
    """
    if align <= 0:
        raise ValueError(f"align must be > 0, got {align}")
    if warmup_ticks < 0 or full_pre_count < 0:
        raise ValueError("warmup_ticks and full_pre_count must be >= 0")
    return warmup_ticks + ((full_pre_count - warmup_ticks) % align)
