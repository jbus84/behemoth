"""Cross-symbol residual payoff simulator."""

from __future__ import annotations

from typing import Protocol

import pandas as pd

from src.behemoth.governance.tick_exact_shared import TickStreamProvider


class CrossSymbolAdapter(Protocol):
    """Family adapter surface required by the cross-symbol simulator."""

    def simulate_one_entry(
        self,
        tick_stream: pd.DataFrame,
        entry_bar: pd.Series,
        params: dict[str, object],
        cs_frame: pd.DataFrame,
    ) -> float: ...


def simulate_state_cross_symbol(
    *,
    entries: pd.DataFrame,
    adapter: CrossSymbolAdapter,
    tick_provider: TickStreamProvider,
    cs_frame: pd.DataFrame,
) -> pd.DataFrame:
    """Replay inclusive horizon ticks and delegate cross-symbol payoff logic."""
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
            cs_frame=cs_frame,
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
