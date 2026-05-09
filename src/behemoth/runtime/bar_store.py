"""DuckDB-backed bar storage and context retrieval."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.behemoth.core.schemas import BarContext, BarPrices, IncomingTickBar
from src.behemoth.runtime.state_store import StateStore

logger = logging.getLogger("behemoth.runtime.bar_store")

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS tick_bars (
    row_id INTEGER,
    symbol VARCHAR,
    bar_ticks INTEGER,
    ts TIMESTAMP WITH TIME ZONE,
    close_ts TIMESTAMP WITH TIME ZONE,
    open_bid DOUBLE,
    high_bid DOUBLE,
    low_bid DOUBLE,
    close_bid DOUBLE,
    spread DOUBLE,
    tick_volume DOUBLE,
    hl_first DOUBLE,
    hl_pos_frac DOUBLE,
    high_ask DOUBLE,
    close_ask DOUBLE
);
"""

_INSERT_SQL = (
    "INSERT INTO tick_bars VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)

_SELECT_LATEST_SQL = """
SELECT * FROM (
    SELECT row_id, ts, close_ts, open_bid, high_bid, low_bid,
           close_bid, spread, tick_volume, hl_first, hl_pos_frac
    FROM tick_bars
    WHERE symbol = ? AND bar_ticks = ?
    ORDER BY row_id DESC
    LIMIT 600
) sub
ORDER BY row_id ASC
"""


class BarStore:
    """Owns tick_bars table: append, prune, count, context retrieval."""

    def __init__(self, store: StateStore) -> None:
        self._store = store
        self._store.execute(_CREATE_SQL)
        self._row_counters: dict[str, int] = {}
        self._hydrate_counters()

    def _hydrate_counters(self) -> None:
        res = self._store.execute(
            "SELECT symbol, bar_ticks, MAX(row_id) FROM tick_bars GROUP BY symbol, bar_ticks"
        ).fetchall()
        for r in res:
            if r[2] is not None:
                self._row_counters[f"{r[0].upper()}_{r[1]}"] = int(r[2]) + 1

    def append_bar(self, bar: IncomingTickBar) -> None:
        sym = bar.symbol.upper()
        key = f"{sym}_{bar.bar_ticks}"
        idx = self._row_counters.get(key, 0)
        self._store.execute(
            _INSERT_SQL,
            [
                idx, sym, bar.bar_ticks, bar.timestamp, bar.close_ts,
                bar.open_bid, bar.high_bid, bar.low_bid, bar.close_bid,
                bar.spread, bar.tick_volume, bar.hl_first, bar.hl_pos_frac,
                bar.high_ask, bar.close_ask,
            ],
        )
        self._row_counters[key] = idx + 1
        if (idx + 1) % 100 == 0:
            self._prune(sym, bar.bar_ticks, idx + 1)

    def _prune(self, symbol: str, bar_ticks: int, current_idx: int) -> None:
        self._store.execute(
            "DELETE FROM tick_bars WHERE symbol = ? AND bar_ticks = ? AND row_id < ?",
            [symbol, bar_ticks, current_idx - 600],
        )

    def bar_count(self, symbol: str, bar_ticks: int) -> int:
        r = self._store.execute(
            "SELECT COUNT(*) FROM tick_bars WHERE symbol = ? AND bar_ticks = ?",
            [symbol.upper(), bar_ticks],
        ).fetchone()
        return int(r[0]) if r else 0

    def get_latest_bar_context(self, symbol: str, bar_ticks: int) -> BarContext | None:
        return self.get_bar_context(symbol, bar_ticks)

    def get_bar_context(
        self, symbol: str, bar_ticks: int, *, bar_number: int | None = None, side: str | None = None
    ) -> BarContext | None:
        latest = self._get_bar_row(symbol=symbol, bar_ticks=bar_ticks, bar_number=bar_number)
        if latest is None:
            return None
        normalized_side = None if side is None else str(side).strip().upper()
        return BarContext(
            symbol=symbol.upper(),
            bar_ticks=int(bar_ticks),
            bar_idx=int(latest["row_id"]),
            timestamp=latest["timestamp"],
            close_ts=latest["close_ts"],
            spread=float(latest["spread"]) if latest["spread"] is not None else None,
            side=normalized_side,
            bid=BarPrices(
                high=float(latest["high_bid"]),
                low=float(latest["low_bid"]),
                close=float(latest["close_bid"]),
            ),
            ask=BarPrices(
                high=float(latest["high_ask"]),
                low=float(min(latest["high_ask"], latest["close_ask"])),
                close=float(latest["close_ask"]),
            ),
            hl_first=float(latest.get("hl_first", 0.0) or 0.0),
            hl_pos_frac=(
                float(latest["hl_pos_frac"])
                if latest.get("hl_pos_frac") is not None
                else None
            ),
        )

    def _get_bar_row(self, *, symbol: str, bar_ticks: int, bar_number: int | None) -> dict | None:
        row_filter = ""
        params: list[Any] = [symbol.upper(), bar_ticks]
        if bar_number is not None:
            row_filter = "AND row_id = ?"
            params.append(int(bar_number))
        res = self._store.execute(
            "SELECT row_id, ts, close_ts, open_bid, high_bid, low_bid, close_bid, "
            "spread, hl_first, hl_pos_frac, high_ask, close_ask "
            "FROM tick_bars WHERE symbol = ? AND bar_ticks = ? "
            f"{row_filter} "
            "ORDER BY row_id DESC LIMIT 1",
            params,
        ).fetchone()
        if res is None:
            return None
        return {
            "row_id": res[0], "timestamp": res[1], "close_ts": res[2],
            "open_bid": res[3], "high_bid": res[4], "low_bid": res[5],
            "close_bid": res[6], "spread": res[7], "hl_first": res[8] if res[8] is not None else 0.0,
            "hl_pos_frac": res[9], "high_ask": res[10] if res[10] is not None else 0.0,
            "close_ask": res[11] if res[11] is not None else 0.0,
        }

    def get_latest_close_ts(self, symbol: str) -> datetime | None:
        r = self._store.execute(
            "SELECT close_ts FROM tick_bars WHERE symbol = ? ORDER BY row_id DESC LIMIT 1",
            [symbol.upper()],
        ).fetchone()
        return r[0] if r else None

    def get_latest_bar(self, symbol: str, bar_ticks: int) -> dict | None:
        return self._get_bar_row(symbol=symbol, bar_ticks=bar_ticks, bar_number=None)

    def get_latest_bar_id(self, symbol: str) -> int:
        row = self._store.execute(
            "SELECT MAX(row_id) FROM tick_bars WHERE symbol = ?",
            [symbol.upper()],
        ).fetchone()
        return int(row[0]) if row and row[0] is not None else 0

    def get_latest_tick_snapshot(self, symbol: str) -> tuple[float, datetime] | None:
        row = self._store.execute(
            "SELECT close_bid, close_ts FROM tick_bars WHERE symbol = ? ORDER BY close_ts DESC, row_id DESC LIMIT 1",
            [symbol.upper()],
        ).fetchone()
        if not row or row[0] is None:
            return None
        close_ts = row[1]
        if isinstance(close_ts, datetime):
            close_ts = (
                close_ts.replace(tzinfo=timezone.utc)
                if close_ts.tzinfo is None
                else close_ts.astimezone(timezone.utc)
            )
        return float(row[0]), close_ts

    def get_recent_bars_df(self, symbol: str, bar_ticks: int) -> Any:
        """Return DataFrame of recent bars for feature computation."""
        return self._store.execute(_SELECT_LATEST_SQL, [symbol.upper(), bar_ticks]).fetchdf()

    def get_all_symbols(self) -> list[str]:
        res = self._store.execute("SELECT DISTINCT symbol FROM tick_bars").fetchall()
        return [r[0] for r in res]

    def get_last_bar_close_price(self, symbol: str, bar_ticks: int = 100) -> tuple[float, datetime] | None:
        res = self._store.execute(
            "SELECT close_bid, close_ts FROM tick_bars WHERE symbol = ? AND bar_ticks = ? ORDER BY row_id DESC LIMIT 1",
            [symbol.upper(), bar_ticks],
        ).fetchone()
        if res is None:
            return None
        close_bid, close_ts = res
        close_ts = (
            close_ts.replace(tzinfo=timezone.utc)
            if close_ts.tzinfo is None
            else close_ts.astimezone(timezone.utc)
        )
        return float(close_bid), close_ts

    def export_warmup_bars(self, symbol: str, bar_ticks: int, path: Path) -> int:
        row = self._store.execute(
            "SELECT COUNT(*) FROM tick_bars WHERE symbol = ? AND bar_ticks = ?",
            [symbol.upper(), bar_ticks],
        ).fetchone()
        count = int(row[0]) if row else 0
        if count == 0:
            return 0
        self._store.execute(
            f"""
            COPY (
                SELECT row_id, ts, close_ts, open_bid, high_bid, low_bid, close_bid,
                       spread, tick_volume, hl_first, hl_pos_frac, high_ask, close_ask
                FROM tick_bars
                WHERE symbol = ? AND bar_ticks = ?
                ORDER BY row_id
            ) TO '{path}' (FORMAT PARQUET)
            """,
            [symbol.upper(), bar_ticks],
        )
        return count
