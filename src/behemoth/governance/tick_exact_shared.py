"""Shared tick-exact payoff simulation infrastructure."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.behemoth.governance.errors import TickStreamGapError


@dataclass(frozen=True)
class TickStreamProvider:
    """Load bid/ask ticks for a symbol and inclusive time range."""

    tick_root: Path

    def get(
        self,
        *,
        symbol: str,
        start_ts: pd.Timestamp,
        end_ts: pd.Timestamp,
    ) -> pd.DataFrame:
        path = Path(self.tick_root) / f"{symbol}_ticks.parquet"
        range_repr = f"{start_ts.isoformat()}..{end_ts.isoformat()}"
        if not path.exists():
            raise TickStreamGapError(symbol=symbol, range_repr=range_repr)

        ticks = pd.read_parquet(path)
        ticks = ticks.copy()
        ticks["ts"] = pd.to_datetime(ticks["ts"], utc=True)
        start = _as_utc_timestamp(start_ts)
        end = _as_utc_timestamp(end_ts)
        mask = (ticks["ts"] >= start) & (ticks["ts"] <= end)
        return ticks.loc[mask].reset_index(drop=True)


def aggregate_state_summary(*, fills: pd.DataFrame) -> pd.DataFrame:
    """Aggregate fill outcomes by state."""
    return (
        fills.groupby("state_id", sort=False)
        .agg(
            n_fills=("realized_pips", "count"),
            mean_realized_pips=("realized_pips", "mean"),
            std_realized_pips=("realized_pips", "std"),
            hit_rate=("realized_pips", lambda values: float((values > 0).mean())),
        )
        .reset_index()
    )


def _as_utc_timestamp(value: pd.Timestamp) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


def aggregate_monthly_summary(*, fills: pd.DataFrame) -> pd.DataFrame:
    """Aggregate fill outcomes by state and entry month."""
    return (
        fills.groupby(["state_id", "entry_month"], sort=False)
        .agg(
            n_fills=("realized_pips", "count"),
            mean_realized_pips=("realized_pips", "mean"),
        )
        .reset_index()
    )
