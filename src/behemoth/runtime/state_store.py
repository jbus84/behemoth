"""Abstract interface for state persistence.

Decouples StateManager from DuckDB, enabling testing with in-memory stores
and supporting future persistence layers (PostgreSQL, SQLite, etc).
"""

from __future__ import annotations

import threading
from typing import Any, Protocol


class StateStoreResult:
    """Minimal result wrapper for query execution."""

    def __init__(
        self,
        rows: list[tuple[Any, ...]] | None = None,
        duckdb_result: Any = None,
        df: Any = None,
    ) -> None:
        self._rows = rows or []
        self._duckdb_result = duckdb_result
        self._df = df

    def fetchall(self) -> list[tuple[Any, ...]]:
        """Return all rows from query result."""
        return self._rows

    def fetchone(self) -> tuple[Any, ...] | None:
        """Return first row from query result, or None if empty."""
        return self._rows[0] if self._rows else None

    def fetchdf(self) -> Any:
        """Return result as DataFrame (DuckDB only).

        Requires that the result was created with a DuckDB result object
        or that the DataFrame was cached at construction time.

        Returns:
            pandas DataFrame
        """
        if self._df is not None:
            return self._df
        if self._duckdb_result is None:
            raise RuntimeError("fetchdf() not available for this result")
        return self._duckdb_result.fetchdf()


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
        """Execute SQL statement using DuckDB."""
        with self._lock:
            result = self._con.execute(sql, params or [])
            rows = result.fetchall()
            df = result.fetchdf()
            return StateStoreResult(rows, duckdb_result=result, df=df)

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
    """In-memory implementation of StateStore for testing.

    Stores tables as dicts of row lists. Suitable for unit tests that don't
    require full SQL semantics, but need state isolation.
    """

    def __init__(self) -> None:
        """Initialize empty in-memory store."""
        self._tables: dict[str, list[dict[str, Any]]] = {}
        self._in_transaction = False

    def execute(self, sql: str, params: list[Any] | None = None) -> StateStoreResult:
        """Execute SQL statement (minimal implementation for testing)."""
        # This is a stub. Real implementation would parse SQL and delegate to _tables.
        # For now, return empty result - intended for tests that mock StateStore.
        return StateStoreResult([])

    def executemany(self, sql: str, params: list[list[Any]]) -> None:
        """Execute SQL statement multiple times (no-op for in-memory store)."""
        pass

    def begin(self) -> None:
        """Begin transaction (no-op in in-memory store)."""
        self._in_transaction = True

    def commit(self) -> None:
        """Commit transaction (no-op in in-memory store)."""
        self._in_transaction = False

    def rollback(self) -> None:
        """Rollback transaction (no-op in in-memory store)."""
        self._in_transaction = False

    def close(self) -> None:
        """Close store (no-op for in-memory store)."""
        pass
