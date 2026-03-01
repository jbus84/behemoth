from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.build_oco_execution_drift_report import run


def _write_symbol_files(base: Path, symbol: str) -> None:
    rows = []
    months = ["2025-01", "2025-02", "2025-03", "2025-04"]
    for i, m in enumerate(months):
        for j in range(20):
            overshoot = 0.1 + 0.02 * i
            touch = 1
            if m == "2025-04" and j < 4:
                overshoot = 0.6  # drift spike
            rows.append(
                {
                    "close_ts": f"{m}-01T00:{j:02d}:00Z",
                    "candidate_uid": f"oco|{symbol}|{j}",
                    "touch_found_tick": touch,
                    "overshoot_tick_pips": overshoot,
                }
            )
    d = pd.DataFrame(rows)
    d.to_csv(base / f"{symbol}_stop_limit_tickfill_detail.csv", index=False)

    caps = pd.DataFrame(
        [
            {"symbol": symbol, "cap_pips": 0.8, "fill_rate": 0.95},
            {"symbol": symbol, "cap_pips": 1.0, "fill_rate": 0.96},
            {"symbol": symbol, "cap_pips": 1.2, "fill_rate": 0.97},
        ]
    )
    caps.to_csv(base / f"{symbol}_stop_limit_tickfill_caps.csv", index=False)


def test_execution_drift_report_outputs(tmp_path: Path) -> None:
    detail_dir = tmp_path / "detail"
    detail_dir.mkdir(parents=True, exist_ok=True)
    for sym in ["EURUSD", "GBPUSD", "USDJPY"]:
        _write_symbol_files(detail_dir, sym)

    monthly, alerts = run(
        symbols=["EURUSD", "GBPUSD", "USDJPY"],
        detail_dir=detail_dir,
        default_cap_pips=1.2,
        baseline_months=3,
        warn_fill_drop=0.01,
        fail_fill_drop=0.02,
        warn_no_touch=0.01,
        fail_no_touch=0.02,
        warn_overshoot_p50=0.01,
        fail_overshoot_p50=0.02,
        warn_overshoot_p95=0.05,
        fail_overshoot_p95=0.10,
        out_monthly_csv=tmp_path / "monthly.csv",
        out_alerts_csv=tmp_path / "alerts.csv",
        report_out=tmp_path / "report.md",
    )
    assert not monthly.empty
    assert not alerts.empty
    required = {
        "symbol",
        "test_month",
        "fill_rate",
        "overshoot_p95_pips",
        "delta_overshoot_p95_pips",
    }
    assert required.issubset(set(monthly.columns))
    assert {"symbol", "metric_id", "band"}.issubset(set(alerts.columns))
