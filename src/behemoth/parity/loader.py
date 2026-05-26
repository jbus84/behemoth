"""Shared input loaders for parity checks.

All loaders are pure readers; they do not write to the filesystem and they
open duckdb/sqlite handles read-only.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.behemoth.core.bundle_paths import lock_filename


def load_signal_parity_csvs(*, reconcile_dir: Path, pattern: str) -> pd.DataFrame:
    """Load every *_<pattern>_signal_parity_summary.csv under reconcile_dir.

    `pattern` is either "jforex" (live / tester) or "local_jforex" (surrogate).
    Returns a concatenated DataFrame with all rows, or an empty frame if the
    directory does not exist.
    """
    if not reconcile_dir.exists():
        return pd.DataFrame()
    suffix = f"_{pattern}_signal_parity_summary.csv"
    frames: list[pd.DataFrame] = []
    for path in sorted(reconcile_dir.glob(f"*{suffix}")):
        try:
            frames.append(pd.read_csv(path))
        except Exception:  # noqa: BLE001
            continue
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def load_runtime_events(
    *, reconcile_dir: Path, symbol: str, pattern: str
) -> pd.DataFrame:
    path = reconcile_dir / f"{symbol.upper()}_{pattern}_runtime_events.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def load_governance_lock(*, governance_lock_dir: Path, symbol: str) -> dict:
    lock = governance_lock_dir / lock_filename(symbol, "oco_first_touch")
    if not lock.exists():
        return {}
    return json.loads(lock.read_text())


def load_active_oco_state(*, runtime_dir: Path, symbol: str) -> list[dict]:
    path = runtime_dir / f"local_jforex_surrogate_{symbol.lower()}_active_oco_state.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text() or "[]")
    return data if isinstance(data, list) else []
