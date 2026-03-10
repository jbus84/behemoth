from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from src.behemoth.core.historical_governance_validation import (
    failed_checks,
    validate_historical_governance,
)


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _touch(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _write_history_fixture(
    root: Path,
    *,
    symbol: str = "EURUSD",
    month: str = "2025-08",
    model_month: str | None = None,
    include_index: bool = True,
) -> tuple[Path, Path]:
    history_dir = root / "history"
    month_dir = history_dir / month
    month_dir.mkdir(parents=True, exist_ok=True)

    wfo = _touch(root / "artifacts" / "wfo.yaml", "threshold_mode: rolling_days\n")
    reduced = _touch(root / "artifacts" / "reduced.yaml", "locked_quantile: 0.9\n")
    states = _touch(
        month_dir / f"{symbol.lower()}_oco_allowed_states.csv",
        "symbol,bar_ticks,horizon,state_id,family,barrier_pips,regime_desc\n"
        f"{symbol},100,5,oco_first_touch_clean__all__k2,oco_first_touch_clean,2.0,all\n",
    )
    preds = _touch(root / "artifacts" / "predictions.parquet", "dummy_predictions")
    cbm = _touch(root / "artifacts" / f"{symbol}_model_{month}.cbm", "dummy_model")
    thr = _touch(
        root / "artifacts" / f"{symbol}_model_{month}.json",
        json.dumps({"model_month": model_month or month}),
    )
    tick_exact = _touch(root / "artifacts" / "tick_exact_summary.csv", "overall_pass\nTrue\n")
    reduced_sum = _touch(
        root / "artifacts" / "reduced_summary.csv",
        "capacity_pass_monthly_or_annual\nTrue\n",
    )

    lock = {
        "symbol": symbol,
        "artifacts": {
            "wfo_config_path": str(wfo),
            "wfo_config_sha256": _sha(wfo),
            "reduced_config_path": str(reduced),
            "reduced_config_sha256": _sha(reduced),
            "reduced_states_csv_path": str(states),
            "reduced_states_csv_sha256": _sha(states),
            "predictions_path": str(preds),
            "predictions_sha256": _sha(preds),
            "model_cbm_path": str(cbm),
            "model_cbm_sha256": _sha(cbm),
            "model_threshold_json_path": str(thr),
            "model_threshold_json_sha256": _sha(thr),
            "model_month": model_month or month,
            "tick_exact_summary_path": str(tick_exact),
            "tick_exact_summary_sha256": _sha(tick_exact),
            "reduced_summary_path": str(reduced_sum),
            "reduced_summary_sha256": _sha(reduced_sum),
        },
        "state_universe": {
            "rows": [
                {
                    "symbol": symbol,
                    "bar_ticks": 100,
                    "horizon": 5,
                    "state_id": "oco_first_touch_clean__all__k2",
                    "family": "oco_first_touch_clean",
                    "barrier_pips": 2.0,
                    "regime_desc": "all",
                }
            ]
        },
        "historical_backtest": {"target_month": month},
    }
    lock_path = month_dir / f"{symbol.lower()}_oco_live_lock.json"
    lock_path.write_text(json.dumps(lock), encoding="utf-8")

    if include_index:
        index_path = history_dir / "index.csv"
        with index_path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(
                f,
                fieldnames=[
                    "symbol",
                    "month",
                    "lock_path",
                    "allowed_states_path",
                    "model_cbm_path",
                    "threshold_json_path",
                    "candidates_count",
                    "production_cap_pips",
                    "live_deployable",
                ],
            )
            w.writeheader()
            w.writerow(
                {
                    "symbol": symbol,
                    "month": month,
                    "lock_path": str(lock_path),
                    "allowed_states_path": str(states),
                    "model_cbm_path": str(cbm),
                    "threshold_json_path": str(thr),
                    "candidates_count": 1,
                    "production_cap_pips": 1.2,
                    "live_deployable": True,
                }
            )

    return history_dir, lock_path


def test_validate_historical_governance_passes_on_valid_fixture(tmp_path: Path) -> None:
    history_dir, _ = _write_history_fixture(tmp_path)
    checks = validate_historical_governance(
        history_dir,
        required_symbols=["EURUSD"],
        required_months=["2025-08"],
    )
    assert failed_checks(checks) == []


def test_validate_historical_governance_flags_model_month_mismatch(tmp_path: Path) -> None:
    history_dir, _ = _write_history_fixture(tmp_path, model_month="2025-07")
    checks = validate_historical_governance(history_dir)
    bad = failed_checks(checks)
    assert any(c.name == "model_month_matches_parent_month" for c in bad)


def test_validate_historical_governance_flags_index_coverage_gap(tmp_path: Path) -> None:
    history_dir, _ = _write_history_fixture(tmp_path, include_index=False)
    checks = validate_historical_governance(history_dir)
    bad = failed_checks(checks)
    assert any(c.name == "index_csv_exists" for c in bad)
    assert any(c.name == "index_covers_exact_lock_set" for c in bad)
