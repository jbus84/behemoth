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
