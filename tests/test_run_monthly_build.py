from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.run_monthly_build as run_monthly_build
import scripts.sync_candidate_model_artifacts as sync_candidate_model_artifacts


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_lock(lock_dir: Path, symbol: str, month: str, cbm: Path, thr: Path) -> None:
    payload = {
        "symbol": symbol,
        "artifacts": {
            "model_month": month,
            "model_cbm_path": f"models/oco/{cbm.name}",
            "model_cbm_sha256": _sha(cbm),
            "model_threshold_json_path": f"models/oco/{thr.name}",
            "model_threshold_json_sha256": _sha(thr),
        },
    }
    (lock_dir / f"{symbol.lower()}_oco_live_lock.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


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
        sys,
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
            "--model-month",
            "2026-02",
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
            "scripts/legacy/freeze_oco_historical_governance.py",
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


def test_monthly_build_does_not_read_promoted_oco_lock_dir(monkeypatch) -> None:
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
        sys,
        "argv",
        ["run_monthly_build.py"],
    )

    run_monthly_build.main()

    captured_sync_cmd = " ".join(calls[0])
    assert "configs/research/governance/oco" not in captured_sync_cmd


def test_main_rejects_invalid_model_month(monkeypatch) -> None:
    def fake_run(cmd, cwd=None):
        raise AssertionError("subprocess.run should not be called")

    monkeypatch.setattr(run_monthly_build.subprocess, "run", fake_run)
    monkeypatch.setattr(
        sys,
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

    with pytest.raises(
        SystemExit,
        match=r"\[monthly-build\] step 1/2: sync_candidate_model_artifacts failed \(rc=2\)",
    ):
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


def test_sync_candidate_model_artifacts_can_use_bundle_or_candidate_lock_source(
    tmp_path: Path,
) -> None:
    bundle_source = tmp_path / "bundle-source"
    bundle_target = tmp_path / "bundle-target"
    bundle_source.mkdir()
    bundle_target.mkdir()

    old_cbm = bundle_source / "EURUSD_model_2026-01.cbm"
    old_thr = bundle_source / "EURUSD_model_2026-01.json"
    old_cbm.write_bytes(b"old-cbm")
    old_thr.write_text('{"threshold": 0.1}', encoding="utf-8")
    latest_cbm = bundle_source / "EURUSD_model_2026-02.cbm"
    latest_thr = bundle_source / "EURUSD_model_2026-02.json"
    latest_cbm.write_bytes(b"latest-cbm")
    latest_thr.write_text('{"threshold": 0.2}', encoding="utf-8")

    exit_code = sync_candidate_model_artifacts.run(
        lock_dir=None,
        source_models_dir=bundle_source,
        target_models_dir=bundle_target,
        symbols=["EURUSD"],
        model_month="2026-02",
    )

    assert exit_code == 0
    assert (bundle_target / latest_cbm.name).read_bytes() == b"latest-cbm"
    assert (bundle_target / latest_thr.name).read_text(encoding="utf-8") == '{"threshold": 0.2}'

    candidate_lock_source = tmp_path / "configs/research/governance/oco_dukascopy_candidate"
    candidate_lock_source.mkdir(parents=True)
    lock_source = tmp_path / "candidate-source"
    lock_target = tmp_path / "candidate-target"
    lock_source.mkdir()
    lock_target.mkdir()

    cbm = lock_source / "EURUSD_model_2026-02.cbm"
    thr = lock_source / "EURUSD_model_2026-02.json"
    cbm.write_bytes(b"candidate-cbm")
    thr.write_text('{"threshold": 0.3}', encoding="utf-8")
    _write_lock(candidate_lock_source, "EURUSD", "2026-02", cbm, thr)

    exit_code = sync_candidate_model_artifacts.run(
        lock_dir=candidate_lock_source,
        source_models_dir=lock_source,
        target_models_dir=lock_target,
        symbols=["EURUSD"],
    )

    assert exit_code == 0
    assert (lock_target / cbm.name).read_bytes() == b"candidate-cbm"
    assert (lock_target / thr.name).read_text(encoding="utf-8") == '{"threshold": 0.3}'


def test_sync_candidate_model_artifacts_requires_requested_model_month(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()

    newer_cbm = source / "EURUSD_model_2026-03.cbm"
    newer_thr = source / "EURUSD_model_2026-03.json"
    newer_cbm.write_bytes(b"newer-cbm")
    newer_thr.write_text('{"threshold": 0.4}', encoding="utf-8")

    exit_code = sync_candidate_model_artifacts.run(
        lock_dir=None,
        source_models_dir=source,
        target_models_dir=target,
        symbols=["EURUSD"],
        model_month="2026-02",
    )

    assert exit_code == 1
    assert not list(target.glob("EURUSD_model_*"))
