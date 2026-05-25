"""Forward-return payoff simulator."""

from __future__ import annotations

from typing import Protocol

import pandas as pd

from src.behemoth.governance.tick_exact_shared import TickStreamProvider


class ForwardReturnAdapter(Protocol):
    """Family adapter surface required by the forward-return simulator."""

    def simulate_one_entry(
        self,
        tick_stream: pd.DataFrame,
        entry_bar: pd.Series,
        params: dict[str, object],
    ) -> float: ...


def simulate_state_forward_return(
    *,
    entries: pd.DataFrame,
    adapter: ForwardReturnAdapter,
    tick_provider: TickStreamProvider,
) -> pd.DataFrame:
    """Replay inclusive horizon ticks for each entry and delegate payoff logic."""
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
