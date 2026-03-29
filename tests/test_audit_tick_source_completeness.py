from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.audit_tick_source_completeness import run


def _write_tick_parquet(root: Path, symbol: str, month: str) -> None:
    path = root / symbol / f"{symbol}_{month}_ticks.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(
        [
            {
                "timestamp": pd.Timestamp("2025-07-01T00:00:00Z"),
                "bid": 1.1,
                "ask": 1.1002,
            }
        ]
    )
    df.to_parquet(path, index=False)


def test_audit_tick_source_completeness_reports_missing_month(tmp_path: Path) -> None:
    tick_root = tmp_path / "dukascopy_ticks"
    _write_tick_parquet(tick_root, "EURUSD", "202507")

    summary, missing = run(
        tick_root=tick_root,
        symbols=["EURUSD", "GBPUSD"],
        months=["202507"],
        out_summary_csv=tmp_path / "summary.csv",
        out_missing_csv=tmp_path / "missing.csv",
        report_out=tmp_path / "report.md",
    )

    assert len(summary) == 2
    eurusd = summary[summary["symbol"].astype(str) == "EURUSD"].iloc[0]
    gbpusd = summary[summary["symbol"].astype(str) == "GBPUSD"].iloc[0]
    assert eurusd["status"] == "ok"
    assert gbpusd["status"] == "missing"
    assert len(missing) == 1


def test_audit_tick_source_completeness_flags_missing_required_columns(tmp_path: Path) -> None:
    tick_root = tmp_path / "dukascopy_ticks"
    path = tick_root / "EURUSD" / "EURUSD_202507_ticks.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"timestamp": pd.Timestamp("2025-07-01T00:00:00Z"), "bid": 1.1}]).to_parquet(
        path, index=False
    )

    summary, missing = run(
        tick_root=tick_root,
        symbols=["EURUSD"],
        months=["202507"],
        out_summary_csv=tmp_path / "summary.csv",
        out_missing_csv=tmp_path / "missing.csv",
        report_out=tmp_path / "report.md",
    )

    assert len(summary) == 1
    assert summary.iloc[0]["status"] == "invalid"
    assert "missing_columns" in str(summary.iloc[0]["detail"])
    assert len(missing) == 1
