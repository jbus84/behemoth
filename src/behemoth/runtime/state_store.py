"""Abstract interface for state persistence.

Decouples StateManager from DuckDB, enabling testing with in-memory stores
and supporting future persistence layers (PostgreSQL, SQLite, etc).
"""

from __future__ import annotations

import threading
from datetime import datetime

import pandas as pd
from typing import Any, Protocol


class StateStoreResult:
    """Minimal result wrapper for query execution.

    Holds either an already-materialised ``rows`` list (SQLite path), a
    cached DataFrame (also SQLite), or a raw DuckDB result object whose
    rows/DataFrame are fetched lazily. DuckDB cursors are exhausted by
    *either* fetchall *or* fetchdf — never both — so we defer the fetch
    until the caller picks one.
    """

    def __init__(
        self,
        rows: list[tuple[Any, ...]] | None = None,
        duckdb_result: Any = None,
        df: Any = None,
    ) -> None:
        self._rows = rows
        self._duckdb_result = duckdb_result
        self._df = df

    def fetchall(self) -> list[tuple[Any, ...]]:
        """Return all rows from query result."""
        if self._rows is not None:
            return self._rows
        if self._duckdb_result is not None:
            self._rows = self._duckdb_result.fetchall()
            return self._rows
        return []

    def fetchone(self) -> tuple[Any, ...] | None:
        """Return first row from query result, or None if empty."""
        rows = self.fetchall()
        return rows[0] if rows else None

    def fetchdf(self) -> Any:
        """Return result as a pandas DataFrame.

        Returns:
            pandas DataFrame, or an empty DataFrame if no rows.
        """
        if self._df is not None:
            return self._df
        if self._duckdb_result is not None:
            self._df = self._duckdb_result.fetchdf()
            return self._df
        return pd.DataFrame()


class StateStore(Protocol):
    """Abstract interface for state persistence.

    Implementations (DuckDB, in-memory, etc) handle SQL execution, transactions,
    and schema management. StateManager uses this protocol and doesn't depend on
    any specific database.
    """

    def execute(self, sql: str, params: list[Any] | None = None) -> StateStoreResult:
        """Execute SQL statement, return result."""
        ...

    def executemany(self, sql: str, params: list[list[Any]]) -> None:
        """Execute SQL statement multiple times with different parameters."""
        ...

    def begin(self) -> None:
        """Begin a transaction."""
        ...

    def commit(self) -> None:
        """Commit current transaction."""
        ...

    def rollback(self) -> None:
        """Rollback current transaction."""
        ...

    def close(self) -> None:
        """Close the store connection."""
        ...


class DuckDBStateStore:
    """DuckDB implementation of StateStore."""

    def __init__(self, persist_path: str | None = None, con: Any = None) -> None:
        """Initialize DuckDB connection.

        Args:
            persist_path: Path to persist database to disk. None = in-memory.
            con: Optional existing DuckDB connection. If provided, persist_path is ignored.
        """
        self._lock = threading.Lock()
        if con is not None:
            self._con = con
            self._owns_connection = False
        else:
            import duckdb

            if persist_path:
                self._con = duckdb.connect(persist_path)
            else:
                self._con = duckdb.connect()
            self._owns_connection = True

    def execute(self, sql: str, params: list[Any] | None = None) -> StateStoreResult:
        """Execute SQL statement using DuckDB.

        Fetching is deferred to the returned ``StateStoreResult`` because a
        DuckDB cursor is exhausted by either ``fetchall`` *or* ``fetchdf`` —
        calling both on the same cursor returns ``None`` from the second.
        """
        with self._lock:
            result = self._con.execute(sql, params or [])
            return StateStoreResult(duckdb_result=result)

    def executemany(self, sql: str, params: list[list[Any]]) -> None:
        """Execute SQL statement multiple times with different parameters."""
        with self._lock:
            self._con.executemany(sql, params)

    def begin(self) -> None:
        """Begin DuckDB transaction."""
        with self._lock:
            self._con.begin()

    def commit(self) -> None:
        """Commit DuckDB transaction."""
        with self._lock:
            self._con.commit()

    def rollback(self) -> None:
        """Rollback DuckDB transaction."""
        with self._lock:
            self._con.rollback()

    def raw_connection(self) -> Any:
        """Access raw DuckDB connection for direct API calls (DDL, etc)."""
        return self._con

    def close(self) -> None:
        """Close DuckDB connection (only if we own it)."""
        with self._lock:
            if self._owns_connection:
                self._con.close()


class InMemoryStateStore:
    """SQLite-backed in-memory implementation of StateStore for testing.

    Provides real SQL semantics without DuckDB connection contention.
    """

    def __init__(self) -> None:
        import sqlite3

        self._con = sqlite3.connect(":memory:")
        self._con.row_factory = sqlite3.Row
        sqlite3.register_adapter(datetime, lambda d: d.isoformat())
        sqlite3.register_converter("timestamp", lambda v: datetime.fromisoformat(v.decode()))
        self._in_transaction = False

    def execute(self, sql: str, params: list[Any] | None = None) -> StateStoreResult:
        import sqlite3
        try:
            cur = self._con.execute(sql, params or [])
            rows = cur.fetchall()
            tuples = [tuple(r) for r in rows]
            if cur.description is not None:
                df = pd.DataFrame(tuples, columns=[d[0] for d in cur.description])
                return StateStoreResult(rows=tuples, df=df)
            return StateStoreResult(rows=tuples)
        except sqlite3.OperationalError as e:
            msg = str(e).lower()
            if "no such table" in msg or "no such column" in msg:
                return StateStoreResult([])
            raise

    def executemany(self, sql: str, params: list[list[Any]]) -> None:
        self._con.executemany(sql, params)

    def begin(self) -> None:
        self._con.execute("BEGIN")
        self._in_transaction = True

    def commit(self) -> None:
        self._con.execute("COMMIT")
        self._in_transaction = False

    def rollback(self) -> None:
        self._con.execute("ROLLBACK")
        self._in_transaction = False

    def close(self) -> None:
        self._con.close()
