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
