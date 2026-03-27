from __future__ import annotations

import csv
import json
from types import SimpleNamespace

import pytest

import scripts.run_monthly_build as run_monthly_build


def test_main_builds_candidate_month_bundle(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd, cwd=None):
        calls.append(cmd)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(run_monthly_build.subprocess, "run", fake_run)
    monkeypatch.setattr(
        run_monthly_build,
        "_derive_model_month",
        lambda override=None: "2026-02",
    )
    monkeypatch.setattr(run_monthly_build, "_materialize_bundle_models", lambda bundle_dir: None)
    monkeypatch.setattr(
        run_monthly_build.sys,
        "argv",
        ["run_monthly_build.py"],
    )

    run_monthly_build.main()

    assert calls == [
        [
            "uv",
            "run",
            "python",
            "scripts/sync_candidate_model_artifacts.py",
            "--lock-dir",
            "configs/research/governance/oco",
            "--source-models-dir",
            "models/oco",
            "--target-models-dir",
            "models/oco_dukascopy_candidate",
            "--symbols",
            "EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD",
        ],
        [
            "uv",
            "run",
            "python",
            "scripts/freeze_oco_historical_governance.py",
            "--allow-dirty",
            "--symbols",
            "EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD",
            "--out-dir",
            "configs/research/governance/oco_candidate_builds",
            "--months",
            "2026-02",
            "--config-dir",
            "configs/research/experiments_dukascopy_candidate",
            "--analysis-dir",
            "data/analysis/tick_opportunity_mining_dukascopy_candidate",
            "--models-dir",
            "models/oco_dukascopy_candidate",
        ],
    ]


def test_main_rejects_invalid_model_month(monkeypatch) -> None:
    def fake_run(cmd, cwd=None):
        raise AssertionError("subprocess.run should not be called")

    monkeypatch.setattr(run_monthly_build.subprocess, "run", fake_run)
    monkeypatch.setattr(
        run_monthly_build.sys,
        "argv",
        ["run_monthly_build.py", "--model-month", "2026-2"],
    )

    with pytest.raises(SystemExit, match=r"\[monthly-build\] invalid --model-month: 2026-2"):
        run_monthly_build.main()


def test_run_step_raises_on_nonzero_returncode(monkeypatch) -> None:
    monkeypatch.setattr(
        run_monthly_build.subprocess,
        "run",
        lambda cmd, cwd=None: SimpleNamespace(returncode=2),
    )

    with pytest.raises(SystemExit, match=r"\[monthly-build\] step 1/2: sync_candidate_model_artifacts failed \(rc=2\)"):
        run_monthly_build._run_step(["cmd"], "step 1/2: sync_candidate_model_artifacts")


def test_materialize_bundle_models_copies_and_rewrites_manifest_and_index(tmp_path) -> None:
    bundle_dir = tmp_path / "configs/research/governance/oco_candidate_builds/2026-02"
    bundle_dir.mkdir(parents=True)
    source_models = tmp_path / "models/oco_dukascopy_candidate"
    source_models.mkdir(parents=True)
    cbm_path = source_models / "EURUSD_model_2026-02.cbm"
    thr_path = source_models / "EURUSD_model_2026-02.json"
    cbm_path.write_text("cbm\n")
    thr_path.write_text('{"threshold": 1.23}\n')

    manifest_path = bundle_dir / "eurusd_oco_live_lock.json"
    manifest_path.write_text(
        json.dumps(
            {
                "symbol": "EURUSD",
                "artifacts": {
                    "model_cbm_path": str(cbm_path),
                    "model_threshold_json_path": str(thr_path),
                },
            }
        )
        + "\n"
    )
    index_path = bundle_dir.parent / "index.csv"
    with index_path.open("w", newline="") as f:
        writer = csv.DictWriter(
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
        writer.writeheader()
        writer.writerow(
            {
                "symbol": "EURUSD",
                "month": "2026-02",
                "lock_path": str(manifest_path),
                "allowed_states_path": str(bundle_dir / "eurusd_oco_allowed_states.csv"),
                "model_cbm_path": str(cbm_path),
                "threshold_json_path": str(thr_path),
                "candidates_count": 1,
                "production_cap_pips": 1.2,
                "live_deployable": True,
            }
        )

    run_monthly_build._materialize_bundle_models(bundle_dir)

    copied_cbm = bundle_dir / "models/oco_dukascopy_candidate/EURUSD_model_2026-02.cbm"
    copied_thr = bundle_dir / "models/oco_dukascopy_candidate/EURUSD_model_2026-02.json"
    assert copied_cbm.read_text() == "cbm\n"
    assert copied_thr.read_text() == '{"threshold": 1.23}\n'

    manifest = json.loads(manifest_path.read_text())
    assert manifest["artifacts"]["model_cbm_path"] == str(copied_cbm)
    assert manifest["artifacts"]["model_threshold_json_path"] == str(copied_thr)

    rows = list(csv.DictReader(index_path.open()))
    assert rows[0]["model_cbm_path"] == str(copied_cbm)
    assert rows[0]["threshold_json_path"] == str(copied_thr)
