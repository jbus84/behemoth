#!/usr/bin/env python3
"""Generate Dukascopy/TestClient Stage 13 artifacts.

This producer is intentionally small: it runs a supplied replay implementation,
materializes the replay summary used by Stage 13 validation, and persists the
runtime-events evidence bundle expected by the validator.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

import pandas as pd

DEFAULT_RUNTIME_EVENTS_FILENAME_SUFFIX = "_jforex_runtime_events.csv"
DEFAULT_REPLAY_SUMMARY_FILENAME_SUFFIX = "_dukascopy_testclient_replay_summary.csv"


@dataclass(frozen=True)
class DukascopyTestClientArtifactOutputs:
    symbol: str
    replay_summary_path: Path
    runtime_events_path: Path
    certification_outcome: str
    go_decision: str


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return bool(value)
    txt = str(value).strip().lower()
    if txt in {"1", "true", "yes", "y", "pass", "green"}:
        return True
    if txt in {"0", "false", "no", "n", "fail", "red"}:
        return False
    return False


def _pick_value(payload: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in payload:
            return payload[key]
    return default


def _normalise_symbol(symbol: str) -> str:
    cleaned = str(symbol).strip().upper()
    if not cleaned:
        raise ValueError("symbol must be non-empty")
    return cleaned


def generate_dukascopy_testclient_artifacts(
    *,
    symbol: str,
    tick_root: Path,
    out_dir: Path,
    start_ts: str,
    end_ts: str,
    replay_impl: Callable[..., Mapping[str, Any]],
) -> DukascopyTestClientArtifactOutputs:
    symbol = _normalise_symbol(symbol)
    out_dir = Path(out_dir)
    tick_root = Path(tick_root)
    out_dir.mkdir(parents=True, exist_ok=True)

    replay_result = replay_impl(
        symbol=symbol,
        tick_root=tick_root,
        out_dir=out_dir,
        start_ts=start_ts,
        end_ts=end_ts,
    )
    if not isinstance(replay_result, Mapping):
        replay_result = {}

    signal_pass = _as_bool(
        _pick_value(
            replay_result,
            "dukascopy_testclient_signal_parity_pass",
            "signal_pass",
            "jforex_signal_parity_pass",
            default=False,
        )
    )
    execution_pass = _as_bool(
        _pick_value(
            replay_result,
            "dukascopy_testclient_execution_parity_pass",
            "execution_pass",
            "jforex_execution_parity_pass",
            default=False,
        )
    )
    certification_pass = signal_pass and execution_pass
    certification_outcome = "PASS" if certification_pass else "FAIL"
    go_decision = "GO" if certification_pass else "NO_GO"

    replay_summary_path = out_dir / f"{symbol}{DEFAULT_REPLAY_SUMMARY_FILENAME_SUFFIX}"
    runtime_events_path = out_dir / f"{symbol}{DEFAULT_RUNTIME_EVENTS_FILENAME_SUFFIX}"

    replay_summary = pd.DataFrame(
        [
            {
                "symbol": symbol,
                "dukascopy_testclient_signal_parity_pass": signal_pass,
                "dukascopy_testclient_execution_parity_pass": execution_pass,
                "stage13_dukascopy_testclient_pass": certification_pass,
                "certification_outcome": certification_outcome,
                "go_decision": go_decision,
                "evaluated_at_utc": _now_utc(),
            }
        ]
    )
    replay_summary.to_csv(replay_summary_path, index=False)

    runtime_events_rows = _pick_value(
        replay_result,
        "runtime_events_rows",
        "runtime_events",
        "events",
        default=[],
    )
    if runtime_events_rows is None:
        runtime_events_rows = []
    if isinstance(runtime_events_rows, pd.DataFrame):
        runtime_events = runtime_events_rows.copy()
    elif isinstance(runtime_events_rows, Mapping):
        runtime_events = pd.DataFrame([dict(runtime_events_rows)])
    else:
        runtime_events = pd.DataFrame(list(runtime_events_rows))
    if not runtime_events.empty:
        runtime_events.to_csv(runtime_events_path, index=False)

    return DukascopyTestClientArtifactOutputs(
        symbol=symbol,
        replay_summary_path=replay_summary_path,
        runtime_events_path=runtime_events_path,
        certification_outcome=certification_outcome,
        go_decision=go_decision,
    )
