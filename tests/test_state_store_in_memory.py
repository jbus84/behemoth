import pytest
from src.behemoth.runtime.state_store import InMemoryStateStore


class TestInMemoryStateStore:
    def test_insert_and_select(self) -> None:
        store = InMemoryStateStore()
        store.execute(
            "CREATE TABLE tick_bars (symbol VARCHAR, bar_ticks INTEGER, close_bid DOUBLE)"
        )
        store.execute(
            "INSERT INTO tick_bars VALUES (?, ?, ?)",
            ["EURUSD", 100, 1.1000],
        )
        result = store.execute(
            "SELECT symbol, bar_ticks, close_bid FROM tick_bars WHERE symbol = ?",
            ["EURUSD"],
        )
        rows = result.fetchall()
        assert len(rows) == 1
        assert rows[0] == ("EURUSD", 100, 1.1000)

    def test_fetchdf(self) -> None:
        store = InMemoryStateStore()
        store.execute(
            "CREATE TABLE tick_bars (symbol VARCHAR, bar_ticks INTEGER)"
        )
        store.execute("INSERT INTO tick_bars VALUES ('EURUSD', 100)")
        df = store.execute("SELECT * FROM tick_bars").fetchdf()
        assert len(df) == 1
        assert df.iloc[0]["symbol"] == "EURUSD"

    def test_executemany(self) -> None:
        store = InMemoryStateStore()
        store.execute("CREATE TABLE t (a INTEGER)")
        store.executemany("INSERT INTO t VALUES (?)", [[1], [2], [3]])
        result = store.execute("SELECT COUNT(*) FROM t")
        assert result.fetchone()[0] == 3

    def test_fetchdf_empty_result_preserves_columns(self) -> None:
        store = InMemoryStateStore()
        store.execute("CREATE TABLE tick_bars (symbol VARCHAR, bar_ticks INTEGER)")
        df = store.execute("SELECT * FROM tick_bars WHERE symbol = 'NONEXISTENT'").fetchdf()
        assert len(df) == 0
        assert list(df.columns) == ["symbol", "bar_ticks"]

    def test_transaction_rollback(self) -> None:
        store = InMemoryStateStore()
        store.execute("CREATE TABLE t (a INTEGER)")
        store.begin()
        store.execute("INSERT INTO t VALUES (1)")
        store.rollback()
        result = store.execute("SELECT COUNT(*) FROM t")
        assert result.fetchone()[0] == 0

    def test_no_such_table_returns_empty(self) -> None:
        store = InMemoryStateStore()
        result = store.execute("SELECT * FROM non_existent_table")
        assert result.fetchall() == []

    def test_executemany_empty_params(self) -> None:
        store = InMemoryStateStore()
        store.execute("CREATE TABLE t (a INTEGER)")
        store.executemany("INSERT INTO t VALUES (?)", [])
        result = store.execute("SELECT COUNT(*) FROM t")
        assert result.fetchone()[0] == 0
