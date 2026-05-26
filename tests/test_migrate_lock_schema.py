from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


def _sha256(b: bytes) -> str:
    h = hashlib.sha256()
    h.update(b)
    return h.hexdigest()


def _make_v1_bundle(root: Path) -> Path:
    """Build a fixture mirroring the real 2026-04 layout, repo-relative."""
    bundle = root / "configs/research/governance/oco_candidate_builds/2026-04"
    legacy_models = (
        root
        / "configs/research/governance/oco_candidate_builds/2026-04/models/oco_dukascopy_candidate"
    )
    mining_dir = (
        root / "data/analysis/tick_opportunity_mining_dukascopy_candidate/wfo_m3to1_oco_fullcap"
    )
    reduced_dir = (
        root / "data/analysis/tick_opportunity_mining_dukascopy_candidate/reduced_core_rolling"
    )
    tick_dir = root / "data/analysis/tick_opportunity_mining_dukascopy_candidate/reduced_core"
    cfg_dir = root / "configs/research/experiments_dukascopy_candidate"
    bundle.mkdir(parents=True)
    legacy_models.mkdir(parents=True)
    mining_dir.mkdir(parents=True)
    reduced_dir.mkdir(parents=True)
    tick_dir.mkdir(parents=True)
    cfg_dir.mkdir(parents=True)

    pred_b = b"pred"
    states_b = b"states"
    cbm_b = b"cbm"
    thr_b = b"thr"
    src_pred_b = b"src-pred"
    red_sum_b = b"red-sum"
    tick_sum_b = b"tick-sum"
    wfo_b = b"wfo: 1\n"
    red_cfg_b = b"red: 1\n"

    (bundle / "eurusd_oco_locked_predictions.parquet").write_bytes(pred_b)
    (bundle / "eurusd_oco_allowed_states.csv").write_bytes(states_b)
    (legacy_models / "EURUSD_model_2026-04.cbm").write_bytes(cbm_b)
    (legacy_models / "EURUSD_model_2026-04.json").write_bytes(thr_b)
    (mining_dir / "EURUSD_oco_monthly_predictions.parquet").write_bytes(src_pred_b)
    (reduced_dir / "EURUSD_oco_reduced_summary.csv").write_bytes(red_sum_b)
    (tick_dir / "EURUSD_oco_tick_exact_summary.csv").write_bytes(tick_sum_b)
    (cfg_dir / "eurusd_tick_opportunity_monthly_wfo_oco_fullcap.yaml").write_bytes(wfo_b)
    (cfg_dir / "eurusd_oco_reduced_core_rolling.yaml").write_bytes(red_cfg_b)

    v1 = {
        "schema_version": 1,
        "symbol": "EURUSD",
        "frozen_at_utc": "2026-05-01T16:08:12+00:00",
        "git": {"branch": "main", "commit": "deadbeef", "dirty": False},
        "artifacts": {
            "live_deployable": True,
            "model_cbm_path": str(legacy_models / "EURUSD_model_2026-04.cbm"),
            "model_cbm_sha256": _sha256(cbm_b),
            "model_threshold_json_path": str(legacy_models / "EURUSD_model_2026-04.json"),
            "model_threshold_json_sha256": _sha256(thr_b),
            "model_month": "2026-04",
            "model_valid_through": "2026-04-30",
            "predictions_path": "configs/research/governance/oco_candidate_builds/2026-04/eurusd_oco_locked_predictions.parquet",
            "predictions_sha256": _sha256(pred_b),
            "reduced_states_csv_path": "configs/research/governance/oco_candidate_builds/2026-04/eurusd_oco_allowed_states.csv",
            "reduced_states_csv_sha256": _sha256(states_b),
            "source_predictions_path": "data/analysis/tick_opportunity_mining_dukascopy_candidate/wfo_m3to1_oco_fullcap/EURUSD_oco_monthly_predictions.parquet",
            "source_predictions_sha256": _sha256(src_pred_b),
            "reduced_summary_path": "data/analysis/tick_opportunity_mining_dukascopy_candidate/reduced_core_rolling/EURUSD_oco_reduced_summary.csv",
            "reduced_summary_sha256": _sha256(red_sum_b),
            "tick_exact_summary_path": "data/analysis/tick_opportunity_mining_dukascopy_candidate/reduced_core/EURUSD_oco_tick_exact_summary.csv",
            "tick_exact_summary_sha256": _sha256(tick_sum_b),
            "wfo_config_path": "configs/research/experiments_dukascopy_candidate/eurusd_tick_opportunity_monthly_wfo_oco_fullcap.yaml",
            "wfo_config_sha256": _sha256(wfo_b),
            "reduced_config_path": "configs/research/experiments_dukascopy_candidate/eurusd_oco_reduced_core_rolling.yaml",
            "reduced_config_sha256": _sha256(red_cfg_b),
            "tick_exact_overall_pass": True,
            "capacity_overall_pass": True,
        },
        "locked_runtime": {"production_cap_pips": 1.2},
        "state_universe": {"count": 0, "rows": [], "sha256": ""},
    }
    (bundle / "eurusd_oco_live_lock.json").write_text(json.dumps(v1, indent=2))
    return bundle


def _run(bundle: Path, repo_root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            "scripts/migrate_lock_schema.py",
            str(bundle),
            "--repo-root",
            str(repo_root),
        ],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
    )


def test_migration_produces_v3_lock(tmp_path: Path) -> None:
    bundle = _make_v1_bundle(tmp_path)
    result = _run(bundle, tmp_path)
    assert result.returncode == 0, result.stderr

    data = json.loads((bundle / "eurusd_oco_live_lock.json").read_text())
    assert data["schema_version"] == 3
    assert data["bundle"]["family"] == "oco_first_touch"
    assert "artifacts" in data
    for legacy_key in (
        "model_cbm_path",
        "predictions_path",
        "reduced_states_csv_path",
        "source_predictions_path",
        "train_predictions_path",
        "reduced_summary_path",
        "tick_exact_summary_path",
    ):
        assert legacy_key not in data["artifacts"], legacy_key

    for key in ("predictions", "allowed_states_csv", "model_cbm", "model_threshold_json"):
        entry = data["artifacts"][key]
        assert not entry["path"].startswith("/")
        assert ".." not in entry["path"].split("/")


def test_migration_copies_external_artifacts(tmp_path: Path) -> None:
    bundle = _make_v1_bundle(tmp_path)
    _run(bundle, tmp_path)
    # Reduced summary and tick-exact summary originated under data/analysis, must now exist in bundle.
    assert (bundle / "eurusd_oco_first_touch_reduced_summary.csv").is_file()
    assert (bundle / "eurusd_oco_first_touch_tick_exact_summary.csv").is_file()
    # Configs are copied under bundle/configs/.
    assert (bundle / "configs/eurusd_oco_first_touch_reduced.yaml").is_file()


def test_migration_records_provenance(tmp_path: Path) -> None:
    bundle = _make_v1_bundle(tmp_path)
    _run(bundle, tmp_path)
    data = json.loads((bundle / "eurusd_oco_live_lock.json").read_text())
    prov = data["provenance"]
    assert prov["predictions"]["origin"].endswith("EURUSD_oco_monthly_predictions.parquet")
    assert prov["reduced_summary"]["origin"].startswith("data/analysis/")


def test_migration_validates_after_write(tmp_path: Path) -> None:
    bundle = _make_v1_bundle(tmp_path)
    _run(bundle, tmp_path)
    # The bundle should pass validate_bundle.
    result = subprocess.run(
        [sys.executable, "scripts/validate_bundle.py", str(bundle)],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
    )
    assert result.returncode == 0, result.stderr


def test_migration_is_idempotent(tmp_path: Path) -> None:
    bundle = _make_v1_bundle(tmp_path)
    first = _run(bundle, tmp_path)
    assert first.returncode == 0
    before = (bundle / "eurusd_oco_live_lock.json").read_text()
    second = _run(bundle, tmp_path)
    assert second.returncode == 0, second.stderr
    after = (bundle / "eurusd_oco_live_lock.json").read_text()
    assert before == after


def test_v2_migration_to_v3_is_idempotent(tmp_path: Path) -> None:
    bundle = tmp_path / "configs/research/governance/oco_candidate_builds/2026-04"
    bundle.mkdir(parents=True)
    lock = bundle / "eurusd_oco_live_lock.json"
    v2 = {
        "schema_version": 2,
        "symbol": "EURUSD",
        "frozen_at_utc": "2026-05-01T16:08:12+00:00",
        "git": {"branch": "main", "commit": "deadbeef", "dirty": False},
        "bundle": {"month": "2026-04", "dir_relpath": str(bundle.relative_to(tmp_path))},
        "artifacts": {},
        "provenance": {},
        "deployability": {"model_month": "2026-04"},
        "locked_runtime": {},
        "retrain_policy": {},
        "state_universe": {},
        "historical_backtest": {},
    }
    lock.write_text(json.dumps(v2, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    first = _run(bundle, tmp_path)
    assert first.returncode == 0, first.stderr
    data = json.loads(lock.read_text(encoding="utf-8"))
    assert data["schema_version"] == 3
    assert data["bundle"]["family"] == "oco_first_touch"

    before = lock.read_text(encoding="utf-8")
    second = _run(bundle, tmp_path)
    assert second.returncode == 0, second.stderr
    after = lock.read_text(encoding="utf-8")
    assert before == after
