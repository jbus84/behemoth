from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from scripts.export_ctrader_custom_data import run


def _write_hist_parquet(path: Path, rows: list[dict[str, object]]) -> None:
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


def test_export_ctrader_custom_data_writes_manifest_and_deduped_csv(tmp_path: Path) -> None:
    tick_root = tmp_path / "tick"
    p = tick_root / "EURUSD" / "EURUSD_202507_ticks.parquet"
    _write_hist_parquet(
        p,
        [
            {"timestamp": "2025-07-07T00:00:01Z", "bid": 1.1001, "ask": 1.1003},
            {"timestamp": "2025-07-07T00:00:00Z", "bid": 1.1000, "ask": 1.1002},
            {"timestamp": "2025-07-07T00:00:01Z", "bid": 1.1001, "ask": 1.1003},
            {"timestamp": "2025-07-07T00:00:02Z", "bid": 1.1002, "ask": 1.1004},
        ],
    )

    out_dir = tmp_path / "out"
    manifest_path, summary_path, summary_df = run(
        symbol="EURUSD",
        tick_root=tick_root,
        source="histdata",
        start_ts="2025-07-07T00:00:00Z",
        end_ts="2025-07-07T00:00:03Z",
        out_dir=out_dir,
        overwrite=True,
    )

    assert manifest_path.exists()
    assert summary_path.exists()
    assert len(summary_df) == 1

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "1.0"
    assert manifest["symbol"] == "EURUSD"
    assert manifest["data_type"] == "tick"
    assert manifest["columns"] == ["timestamp_utc", "bid", "ask"]
    assert manifest["summary_csv"] == "export_summary.csv"

    csv_path = out_dir / manifest["files"][0]["path"]
    csv_df = pd.read_csv(csv_path)
    assert list(csv_df.columns) == ["timestamp_utc", "bid", "ask"]
    assert len(csv_df) == 3
    assert list(csv_df["timestamp_utc"]) == sorted(csv_df["timestamp_utc"].tolist())

    row = summary_df.iloc[0]
    assert row["source"] == "histdata"
    assert int(row["input_rows"]) == 4
    assert int(row["export_rows"]) == 3
    assert int(row["dropped_duplicate_rows"]) == 1


def test_export_ctrader_custom_data_rejects_crossed_quotes(tmp_path: Path) -> None:
    tick_root = tmp_path / "tick"
    p = tick_root / "EURUSD" / "EURUSD_202507_ticks.parquet"
    _write_hist_parquet(
        p,
        [{"timestamp": "2025-07-07T00:00:00Z", "bid": 1.1003, "ask": 1.1002}],
    )

    with pytest.raises(ValueError, match="ask < bid"):
        run(
            symbol="EURUSD",
            tick_root=tick_root,
            start_ts="2025-07-07T00:00:00Z",
            end_ts="2025-07-07T00:00:01Z",
            out_dir=tmp_path / "out",
            overwrite=True,
        )


def test_export_ctrader_custom_data_supports_anchor_tick_counts(tmp_path: Path) -> None:
    tick_root = tmp_path / "tick"
    rows: list[dict[str, object]] = []
    for i in range(10):
        rows.append(
            {
                "timestamp": f"2025-07-07T00:00:{i:02d}Z",
                "bid": 1.1000 + (i * 0.0001),
                "ask": 1.1002 + (i * 0.0001),
            }
        )
    _write_hist_parquet(tick_root / "EURUSD" / "EURUSD_202507_ticks.parquet", rows)

    out_dir = tmp_path / "out"
    manifest_path, summary_path, summary_df = run(
        symbol="EURUSD",
        tick_root=tick_root,
        start_ts="2025-07-07T00:00:04Z",
        end_ts="2025-07-07T00:00:09Z",
        out_dir=out_dir,
        overwrite=True,
        anchor_ts="2025-07-07T00:00:04Z",
        ticks_before_anchor=3,
        ticks_after_anchor=4,
    )

    assert manifest_path.exists()
    assert summary_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    csv_path = out_dir / manifest["files"][0]["path"]
    csv_df = pd.read_csv(csv_path)
    assert len(csv_df) == 8
    assert csv_df.iloc[0]["timestamp_utc"] == "2025-07-07T00:00:01.000000Z"
    assert csv_df.iloc[-1]["timestamp_utc"] == "2025-07-07T00:00:08.000000Z"

    row = summary_df.iloc[0]
    assert int(row["ticks_before_anchor_requested"]) == 3
    assert int(row["ticks_after_anchor_requested"]) == 4
    assert int(row["export_rows_before_anchor"]) == 3
    assert int(row["export_rows_at_or_after_anchor"]) == 5


def test_export_ctrader_custom_data_count_mode_still_covers_requested_end(tmp_path: Path) -> None:
    tick_root = tmp_path / "tick"
    rows: list[dict[str, object]] = []
    for i in range(20):
        rows.append(
            {
                "timestamp": f"2025-07-07T00:00:{i:02d}Z",
                "bid": 1.2000 + (i * 0.0001),
                "ask": 1.2002 + (i * 0.0001),
            }
        )
    _write_hist_parquet(tick_root / "EURUSD" / "EURUSD_202507_ticks.parquet", rows)

    out_dir = tmp_path / "out"
    manifest_path, _, summary_df = run(
        symbol="EURUSD",
        tick_root=tick_root,
        start_ts="2025-07-07T00:00:10Z",
        end_ts="2025-07-07T00:00:20Z",
        out_dir=out_dir,
        overwrite=True,
        anchor_ts="2025-07-07T00:00:10Z",
        ticks_before_anchor=3,
        ticks_after_anchor=4,
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    csv_path = out_dir / manifest["files"][0]["path"]
    csv_df = pd.read_csv(csv_path)
    assert csv_df.iloc[0]["timestamp_utc"] == "2025-07-07T00:00:07.000000Z"
    assert csv_df.iloc[-1]["timestamp_utc"] == "2025-07-07T00:00:19.000000Z"

    row = summary_df.iloc[0]
    assert int(row["requested_window_rows"]) == 10
    assert bool(row["requested_window_covered_to_end"]) is True


def test_export_ctrader_custom_data_supports_dukascopy_source_metadata(tmp_path: Path) -> None:
    tick_root = tmp_path / "dukascopy_ticks"
    p = tick_root / "EURUSD" / "EURUSD_202507_ticks.parquet"
    _write_hist_parquet(
        p,
        [
            {"timestamp": "2025-07-07T00:00:00Z", "bid": 1.1000, "ask": 1.1002},
            {"timestamp": "2025-07-07T00:00:01Z", "bid": 1.1001, "ask": 1.1003},
        ],
    )

    manifest_path, _, summary_df = run(
        symbol="EURUSD",
        source="dukascopy",
        tick_root=tick_root,
        start_ts="2025-07-07T00:00:00Z",
        end_ts="2025-07-07T00:00:02Z",
        out_dir=tmp_path / "out",
        overwrite=True,
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["source"]["kind"] == "dukascopy_parquet"
    assert summary_df.iloc[0]["source"] == "dukascopy"
