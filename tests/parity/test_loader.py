"""Tests for src/behemoth/parity/loader.py."""
from __future__ import annotations

from pathlib import Path

from behemoth.parity import loader


def test_load_signal_parity_csvs_reads_symbol_rows(tmp_path: Path) -> None:
    (tmp_path / "AUDUSD_jforex_signal_parity_summary.csv").write_text(
        "symbol,jforex_signal_parity_pass,predict_cycles,failed_signal_events\n"
        "AUDUSD,false,0,165\n"
    )
    (tmp_path / "EURUSD_jforex_signal_parity_summary.csv").write_text(
        "symbol,jforex_signal_parity_pass,predict_cycles,failed_signal_events\n"
        "EURUSD,true,136,0\n"
    )
    df = loader.load_signal_parity_csvs(reconcile_dir=tmp_path, pattern="jforex")
    assert set(df["symbol"]) == {"AUDUSD", "EURUSD"}
    assert df.loc[df["symbol"] == "AUDUSD", "predict_cycles"].iloc[0] == 0


def test_load_runtime_events_filters_by_symbol(tmp_path: Path) -> None:
    (tmp_path / "AUDUSD_jforex_runtime_events.csv").write_text(
        "event_ts_utc,symbol,category,event_name,pass,detail\n"
        "2026-04-16T14:25:07.280258Z,AUDUSD,operational,strategy_started,true,x\n"
    )
    df = loader.load_runtime_events(reconcile_dir=tmp_path, symbol="AUDUSD",
                                     pattern="jforex")
    assert len(df) == 1
    assert df.iloc[0]["event_name"] == "strategy_started"


def test_load_governance_lock_returns_dict(tmp_path: Path) -> None:
    lock = tmp_path / "audusd_oco_live_lock.json"
    lock.write_text('{"model_month":"2026-04","lock_hash":"abc","ok":true}')
    out = loader.load_governance_lock(governance_lock_dir=tmp_path, symbol="AUDUSD")
    assert out["model_month"] == "2026-04"


def test_load_signal_parity_csvs_missing_dir_returns_empty(tmp_path: Path) -> None:
    df = loader.load_signal_parity_csvs(
        reconcile_dir=tmp_path / "nope", pattern="jforex"
    )
    assert df.empty
