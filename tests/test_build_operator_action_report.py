from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.build_operator_action_report import run


def test_build_operator_action_report_outputs_status_and_docs(tmp_path: Path) -> None:
    edge_csv = tmp_path / "edge.csv"
    pd.DataFrame(
        [
            {
                "stage_id": 1,
                "symbol": "EURUSD",
                "metric_id": "D16_spread_regime_shift_z",
                "metric_value": 4.0,
                "source_path": "x",
            }
        ]
    ).to_csv(edge_csv, index=False)

    rules_yaml = tmp_path / "rules.yaml"
    rules_yaml.write_text(
        """
version: 1
action_definitions:
  A0_MONITOR: ok
  A3_HALT_AND_REMEDIATE: halt
rules:
  - metric_id: D16_spread_regime_shift_z
    stage_id: 1
    mode: abs_ge
    warn: 2.0
    fail: 3.0
    owner: research
    action_warn: A0_MONITOR
    action_fail: A3_HALT_AND_REMEDIATE
""",
        encoding="utf-8",
    )

    status, report, playbook = run(
        edge_metrics_csv=edge_csv,
        rules_yaml=rules_yaml,
        out_status_csv=tmp_path / "operator_action_status.csv",
        out_report_md=tmp_path / "operator_action_report.md",
        out_playbook_md=tmp_path / "operator_playbook.md",
        symbols=["EURUSD"],
    )

    assert not status.empty
    assert set(["symbol", "metric_id", "band", "action_code"]).issubset(set(status.columns))
    row = status.iloc[0]
    assert row["symbol"] == "EURUSD"
    assert row["band"] == "red"
    assert row["action_code"] == "A3_HALT_AND_REMEDIATE"
    assert report.exists()
    assert playbook.exists()
