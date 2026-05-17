from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.build_feature_importance_audit import build_audit


def _write_importance_csv(path: Path, month: str, values: dict[str, float]) -> None:
    row = {"test_month": month, **values}
    pd.DataFrame([row]).to_csv(path, index=False)


def test_build_audit_writes_report_with_three_sections(tmp_path: Path) -> None:
    imp_dir = tmp_path / "models"
    imp_dir.mkdir()
    _write_importance_csv(
        imp_dir / "EURUSD_feature_importance_2025-01.csv",
        "2025-01",
        {"ret_z": 30.0, "hour_utc": 10.0, "hl_first": 0.2, "tick_burst_score": 8.0},
    )
    _write_importance_csv(
        imp_dir / "EURUSD_feature_importance_2025-02.csv",
        "2025-02",
        {"ret_z": 28.0, "hour_utc": 12.0, "hl_first": 0.4, "tick_burst_score": 6.0},
    )

    ml_ready = tmp_path / "eurusd_ml_ready.parquet"
    pd.DataFrame(
        {
            "ret_z": [0.1, 0.2, 0.3, 0.4],
            "hour_utc": [1, 2, 3, 4],
            "hl_first": [0.5, 0.5, 0.5, 0.5],
            "tick_burst_score": [1.0, 2.0, 3.0, 4.0],
            "session_marker": ["LONDON", "NY", "LONDON", "NY"],
        }
    ).to_parquet(ml_ready, index=False)

    out = tmp_path / "audit.md"
    result = build_audit(
        symbol="EURUSD",
        importance_dir=imp_dir,
        ml_ready_path=ml_ready,
        out_path=out,
        dead_weight_floor=1.0,
    )

    assert result == out
    text = out.read_text(encoding="utf-8")
    assert "## Ranked Mean Importance" in text
    assert "## Dead-Weight Flags" in text
    assert "## Orthogonal Expansion Candidates" in text
    # ret_z has the highest mean importance (29.0)
    assert text.index("ret_z") < text.index("tick_burst_score")
    # hl_first mean importance 0.3 < floor 1.0 -> flagged dead weight
    assert "hl_first" in text.split("## Dead-Weight Flags")[1].split("##")[0]


def test_build_audit_raises_when_no_importance_csvs(tmp_path: Path) -> None:
    import pytest

    imp_dir = tmp_path / "models"
    imp_dir.mkdir()
    ml_ready = tmp_path / "eurusd_ml_ready.parquet"
    pd.DataFrame({"ret_z": [0.1, 0.2]}).to_parquet(ml_ready, index=False)

    with pytest.raises(FileNotFoundError, match="feature_importance"):
        build_audit(
            symbol="EURUSD",
            importance_dir=imp_dir,
            ml_ready_path=ml_ready,
            out_path=tmp_path / "audit.md",
            dead_weight_floor=1.0,
        )
