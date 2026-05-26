"""Barrier-touch payoff simulator."""

from __future__ import annotations

from typing import Protocol

import pandas as pd

from src.behemoth.governance.tick_exact_shared import TickStreamProvider


class BarrierTouchAdapter(Protocol):
    """Family adapter surface required by the barrier-touch simulator."""

    def simulate_one_entry(
        self,
        tick_stream: pd.DataFrame,
        entry_bar: pd.Series,
        params: dict[str, object],
    ) -> float: ...


def simulate_state_barrier_touch(
    *,
    entries: pd.DataFrame,
    adapter: BarrierTouchAdapter,
    tick_provider: TickStreamProvider,
) -> pd.DataFrame:
    """Replay ticks for each entry and delegate payoff logic to the adapter."""
    fills: list[dict[str, object]] = []

    for _, entry in entries.iterrows():
        start_ts = pd.Timestamp(entry["entry_ts"])
        end_ts = start_ts + pd.Timedelta(seconds=float(entry["horizon_seconds"]))
        tick_stream = tick_provider.get(
            symbol=str(entry["symbol"]),
            start_ts=start_ts,
            end_ts=end_ts,
        )
        realized_pips = adapter.simulate_one_entry(
            tick_stream=tick_stream,
            entry_bar=entry,
            params=entry.to_dict(),
        )
        fills.append(
            {
                "state_id": entry["state_id"],
                "entry_ts": entry["entry_ts"],
                "entry_month": start_ts.strftime("%Y-%m"),
                "realized_pips": float(realized_pips),
            }
        )

    return pd.DataFrame(fills)
