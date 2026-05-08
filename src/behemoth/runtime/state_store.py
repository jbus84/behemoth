"""Abstract interface for state persistence.

Decouples StateManager from DuckDB, enabling testing with in-memory stores
and supporting future persistence layers (PostgreSQL, SQLite, etc).
"""

from __future__ import annotations

from typing import Any, Protocol


class StateStoreResult:
    """Minimal result wrapper for query execution."""

    def __init__(self, rows: list[tuple[Any, ...]] | None = None) -> None:
        self._rows = rows or []

    def fetchall(self) -> list[tuple[Any, ...]]:
        """Return all rows from query result."""
        return self._rows

    def fetchone(self) -> tuple[Any, ...] | None:
        """Return first row from query result, or None if empty."""
        return self._rows[0] if self._rows else None


class StateStore(Protocol):
    """Abstract interface for state persistence.

    Implementations (DuckDB, in-memory, etc) handle SQL execution, transactions,
    and schema management. StateManager uses this protocol and doesn't depend on
    any specific database.
    """

    def execute(self, sql: str, params: list[Any] | None = None) -> StateStoreResult:
        """Execute SQL statement, return result."""
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


class DuckDBStateStore:
    """DuckDB implementation of StateStore."""

    def __init__(self, persist_path: str | None = None) -> None:
        """Initialize DuckDB connection.

        Args:
            persist_path: Path to persist database to disk. None = in-memory.
        """
        import duckdb

        if persist_path:
            self._con = duckdb.connect(persist_path)
        else:
            self._con = duckdb.connect()

    def execute(self, sql: str, params: list[Any] | None = None) -> StateStoreResult:
        """Execute SQL statement using DuckDB."""
        result = self._con.execute(sql, params or [])
        rows = result.fetchall()
        return StateStoreResult(rows)

    def begin(self) -> None:
        """Begin DuckDB transaction."""
        self._con.begin()

    def commit(self) -> None:
        """Commit DuckDB transaction."""
        self._con.commit()

    def rollback(self) -> None:
        """Rollback DuckDB transaction."""
        self._con.rollback()

    def raw_connection(self) -> Any:
        """Access raw DuckDB connection for direct API calls (DDL, etc)."""
        return self._con


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

    def begin(self) -> None:
        """Begin transaction (no-op in in-memory store)."""
        self._in_transaction = True

    def commit(self) -> None:
        """Commit transaction (no-op in in-memory store)."""
        self._in_transaction = False

    def rollback(self) -> None:
        """Rollback transaction (no-op in in-memory store)."""
        self._in_transaction = False
