from pathlib import Path

from scripts.era_scalp.run_era_eur import _velocity_path


def test_default_is_100tick():
    assert _velocity_path("data/x", "EURUSD") == Path("data/x/EURUSD_100tick_velocity.parquet")


def test_custom_bar_length():
    assert _velocity_path("data/x", "EURUSD", "1000tick") == Path("data/x/EURUSD_1000tick_velocity.parquet")
    assert _velocity_path("/abs/dir", "GBPUSD", "2000tick") == Path("/abs/dir/GBPUSD_2000tick_velocity.parquet")
