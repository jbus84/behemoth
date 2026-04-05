from __future__ import annotations

from pathlib import Path

from scripts.generate_dukascopy_testclient_artifacts import generate_dukascopy_testclient_artifacts


def test_generate_dukascopy_testclient_artifacts_emits_required_paths(tmp_path: Path) -> None:
    outputs = generate_dukascopy_testclient_artifacts(
        symbol="USDJPY",
        tick_root=tmp_path / "ticks",
        out_dir=tmp_path / "backtest_reconcile",
        start_ts="2025-07-07T00:00:00Z",
        end_ts="2025-07-09T00:00:00Z",
        replay_impl=lambda **_: {
            "signal_pass": True,
            "execution_pass": True,
            "runtime_events_rows": [{"event_name": "predict_cycle", "pass": True}],
        },
    )

    assert outputs.replay_summary_path.name == "USDJPY_dukascopy_testclient_replay_summary.csv"
    assert outputs.runtime_events_path.name == "USDJPY_jforex_runtime_events.csv"
