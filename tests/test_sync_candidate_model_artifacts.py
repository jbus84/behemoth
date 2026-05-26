from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.sync_candidate_model_artifacts import run


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_lock(lock_dir: Path, symbol: str, month: str, cbm: Path, thr: Path) -> None:
    payload = {
        "schema_version": 3,
        "symbol": symbol,
        "bundle": {
            "month": month,
            "dir_relpath": str(lock_dir),
            "family": "oco_first_touch",
        },
        "artifacts": {
            "model_cbm": {
                "path": f"models/{symbol}_model_{month}.cbm",
                "sha256": _sha(cbm),
            },
            "model_threshold_json": {
                "path": f"models/{symbol}_model_{month}.json",
                "sha256": _sha(thr),
            },
        },
        "deployability": {
            "model_month": month,
            "live_deployable": True,
        },
    }
    (lock_dir / f"{symbol.lower()}_oco_first_touch_live_lock.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


def test_run_copies_candidate_artifacts_and_verifies_hashes(tmp_path: Path) -> None:
    lock_dir = tmp_path / "locks"
    source_dir = tmp_path / "models_src"
    target_dir = tmp_path / "models_dst"
    lock_dir.mkdir()
    source_dir.mkdir()
    target_dir.mkdir()

    cbm = source_dir / "EURUSD_model_2026-02.cbm"
    thr = source_dir / "EURUSD_model_2026-02.json"
    cbm.write_bytes(b"cbm")
    thr.write_text('{"threshold": 0.5}', encoding="utf-8")
    _write_lock(lock_dir, "EURUSD", "2026-02", cbm, thr)

    exit_code = run(
        lock_dir=lock_dir,
        source_models_dir=source_dir,
        target_models_dir=target_dir,
        symbols=["EURUSD"],
    )

    assert exit_code == 0
    assert (target_dir / cbm.name).read_bytes() == b"cbm"
    assert (target_dir / thr.name).read_text(encoding="utf-8") == '{"threshold": 0.5}'


def test_run_fails_when_source_artifact_missing(tmp_path: Path) -> None:
    lock_dir = tmp_path / "locks"
    source_dir = tmp_path / "models_src"
    target_dir = tmp_path / "models_dst"
    lock_dir.mkdir()
    source_dir.mkdir()
    target_dir.mkdir()

    cbm = source_dir / "EURUSD_model_2026-02.cbm"
    thr = source_dir / "EURUSD_model_2026-02.json"
    cbm.write_bytes(b"cbm")
    thr.write_text('{"threshold": 0.5}', encoding="utf-8")
    _write_lock(lock_dir, "EURUSD", "2026-02", cbm, thr)
    cbm.unlink()

    exit_code = run(
        lock_dir=lock_dir,
        source_models_dir=source_dir,
        target_models_dir=target_dir,
        symbols=["EURUSD"],
    )

    assert exit_code == 1
    assert not (target_dir / "EURUSD_model_2026-02.cbm").exists()


def test_run_fails_when_source_hash_does_not_match_lock(tmp_path: Path) -> None:
    lock_dir = tmp_path / "locks"
    source_dir = tmp_path / "models_src"
    target_dir = tmp_path / "models_dst"
    lock_dir.mkdir()
    source_dir.mkdir()
    target_dir.mkdir()

    cbm = source_dir / "EURUSD_model_2026-02.cbm"
    thr = source_dir / "EURUSD_model_2026-02.json"
    cbm.write_bytes(b"expected")
    thr.write_text('{"threshold": 0.5}', encoding="utf-8")
    _write_lock(lock_dir, "EURUSD", "2026-02", cbm, thr)
    cbm.write_bytes(b"actual")
    (target_dir / cbm.name).write_bytes(b"stale-cbm")
    (target_dir / thr.name).write_text('{"threshold": "stale"}', encoding="utf-8")

    exit_code = run(
        lock_dir=lock_dir,
        source_models_dir=source_dir,
        target_models_dir=target_dir,
        symbols=["EURUSD"],
    )

    assert exit_code == 1
    assert not (target_dir / cbm.name).exists()
    assert not (target_dir / thr.name).exists()


def test_run_reports_mixed_symbol_outcomes_and_exits_nonzero(tmp_path: Path) -> None:
    lock_dir = tmp_path / "locks"
    source_dir = tmp_path / "models_src"
    target_dir = tmp_path / "models_dst"
    lock_dir.mkdir()
    source_dir.mkdir()
    target_dir.mkdir()

    eur_cbm = source_dir / "EURUSD_model_2026-02.cbm"
    eur_thr = source_dir / "EURUSD_model_2026-02.json"
    eur_cbm.write_bytes(b"eur")
    eur_thr.write_text('{"threshold": 0.5}', encoding="utf-8")
    _write_lock(lock_dir, "EURUSD", "2026-02", eur_cbm, eur_thr)

    gbp_cbm = source_dir / "GBPUSD_model_2026-02.cbm"
    gbp_thr = source_dir / "GBPUSD_model_2026-02.json"
    gbp_cbm.write_bytes(b"gbp")
    gbp_thr.write_text('{"threshold": 0.6}', encoding="utf-8")
    _write_lock(lock_dir, "GBPUSD", "2026-02", gbp_cbm, gbp_thr)
    gbp_thr.unlink()

    exit_code = run(
        lock_dir=lock_dir,
        source_models_dir=source_dir,
        target_models_dir=target_dir,
        symbols=["EURUSD", "GBPUSD"],
    )

    assert exit_code == 1
    assert (target_dir / "EURUSD_model_2026-02.cbm").exists()
    assert not (target_dir / "GBPUSD_model_2026-02.json").exists()


def test_run_fails_when_requested_symbol_has_no_live_lock(
    tmp_path: Path,
    capsys,
) -> None:
    lock_dir = tmp_path / "locks"
    source_dir = tmp_path / "models_src"
    target_dir = tmp_path / "models_dst"
    lock_dir.mkdir()
    source_dir.mkdir()
    target_dir.mkdir()

    cbm = source_dir / "EURUSD_model_2026-02.cbm"
    thr = source_dir / "EURUSD_model_2026-02.json"
    cbm.write_bytes(b"eur")
    thr.write_text('{"threshold": 0.5}', encoding="utf-8")
    _write_lock(lock_dir, "EURUSD", "2026-02", cbm, thr)

    exit_code = run(
        lock_dir=lock_dir,
        source_models_dir=source_dir,
        target_models_dir=target_dir,
        symbols=["EURUSD", "GBPUSD"],
    )

    out = capsys.readouterr().out
    assert exit_code == 1
    assert "[candidate-sync] EURUSD 2026-02 PASS" in out
    assert "[candidate-sync] GBPUSD" in out
    assert "FAIL" in out
    assert "missing live lock" in out
    assert (target_dir / "EURUSD_model_2026-02.cbm").exists()


def test_run_reports_malformed_lock_and_continues(tmp_path: Path, capsys) -> None:
    lock_dir = tmp_path / "locks"
    source_dir = tmp_path / "models_src"
    target_dir = tmp_path / "models_dst"
    lock_dir.mkdir()
    source_dir.mkdir()
    target_dir.mkdir()

    cbm = source_dir / "EURUSD_model_2026-02.cbm"
    thr = source_dir / "EURUSD_model_2026-02.json"
    cbm.write_bytes(b"eur")
    thr.write_text('{"threshold": 0.5}', encoding="utf-8")
    _write_lock(lock_dir, "EURUSD", "2026-02", cbm, thr)
    (lock_dir / "gbpusd_oco_first_touch_live_lock.json").write_text("{bad json", encoding="utf-8")

    exit_code = run(
        lock_dir=lock_dir,
        source_models_dir=source_dir,
        target_models_dir=target_dir,
        symbols=["EURUSD", "GBPUSD"],
    )

    out = capsys.readouterr().out
    assert exit_code == 1
    assert "[candidate-sync] EURUSD 2026-02 PASS" in out
    assert "[candidate-sync] GBPUSD" in out
    assert "FAIL" in out
    assert "malformed lock" in out
    assert (target_dir / cbm.name).exists()
    assert not (target_dir / "GBPUSD_model_2026-02.cbm").exists()


def test_run_reports_structurally_malformed_lock_and_cleans_stale_targets(
    tmp_path: Path,
    capsys,
) -> None:
    lock_dir = tmp_path / "locks"
    source_dir = tmp_path / "models_src"
    target_dir = tmp_path / "models_dst"
    lock_dir.mkdir()
    source_dir.mkdir()
    target_dir.mkdir()

    cbm = source_dir / "EURUSD_model_2026-02.cbm"
    thr = source_dir / "EURUSD_model_2026-02.json"
    cbm.write_bytes(b"eur")
    thr.write_text('{"threshold": 0.5}', encoding="utf-8")
    _write_lock(lock_dir, "EURUSD", "2026-02", cbm, thr)
    (lock_dir / "gbpusd_oco_first_touch_live_lock.json").write_text(
        json.dumps({"symbol": "GBPUSD", "artifacts": ["bad"]}),
        encoding="utf-8",
    )
    (target_dir / "GBPUSD_model_2026-02.cbm").write_bytes(b"stale-cbm")
    (target_dir / "GBPUSD_model_2026-02.json").write_text(
        '{"threshold": "stale"}',
        encoding="utf-8",
    )

    exit_code = run(
        lock_dir=lock_dir,
        source_models_dir=source_dir,
        target_models_dir=target_dir,
        symbols=["EURUSD", "GBPUSD"],
    )

    out = capsys.readouterr().out
    assert exit_code == 1
    assert "[candidate-sync] EURUSD 2026-02 PASS" in out
    assert "[candidate-sync] GBPUSD" in out
    assert "FAIL" in out
    assert "malformed lock metadata" in out
    assert (target_dir / cbm.name).exists()
    assert not (target_dir / "GBPUSD_model_2026-02.cbm").exists()
    assert not (target_dir / "GBPUSD_model_2026-02.json").exists()


def test_run_removes_stale_target_files_when_expected_hash_missing(
    tmp_path: Path,
    capsys,
) -> None:
    lock_dir = tmp_path / "locks"
    source_dir = tmp_path / "models_src"
    target_dir = tmp_path / "models_dst"
    lock_dir.mkdir()
    source_dir.mkdir()
    target_dir.mkdir()

    cbm = source_dir / "EURUSD_model_2026-02.cbm"
    thr = source_dir / "EURUSD_model_2026-02.json"
    cbm.write_bytes(b"eur")
    thr.write_text('{"threshold": 0.5}', encoding="utf-8")
    (lock_dir / "eurusd_oco_first_touch_live_lock.json").write_text(
        json.dumps(
            {
                "schema_version": 3,
                "symbol": "EURUSD",
                "bundle": {
                    "month": "2026-02",
                    "dir_relpath": str(lock_dir),
                    "family": "oco_first_touch",
                },
                "artifacts": {
                    "model_cbm": {
                        "path": f"models/{cbm.name}",
                    },
                    "model_threshold_json": {
                        "path": f"models/{thr.name}",
                    },
                },
                "deployability": {
                    "model_month": "2026-02",
                    "live_deployable": True,
                },
            }
        ),
        encoding="utf-8",
    )
    (target_dir / cbm.name).write_bytes(b"stale-cbm")
    (target_dir / thr.name).write_text('{"threshold": "stale"}', encoding="utf-8")

    exit_code = run(
        lock_dir=lock_dir,
        source_models_dir=source_dir,
        target_models_dir=target_dir,
        symbols=["EURUSD"],
    )

    out = capsys.readouterr().out
    assert exit_code == 1
    assert "[candidate-sync] EURUSD 2026-02 FAIL" in out
    assert "missing expected hash in lock" in out
    assert not (target_dir / cbm.name).exists()
    assert not (target_dir / thr.name).exists()


def test_run_reports_non_object_top_level_lock_payload_and_continues(
    tmp_path: Path,
    capsys,
) -> None:
    lock_dir = tmp_path / "locks"
    source_dir = tmp_path / "models_src"
    target_dir = tmp_path / "models_dst"
    lock_dir.mkdir()
    source_dir.mkdir()
    target_dir.mkdir()

    cbm = source_dir / "EURUSD_model_2026-02.cbm"
    thr = source_dir / "EURUSD_model_2026-02.json"
    cbm.write_bytes(b"eur")
    thr.write_text('{"threshold": 0.5}', encoding="utf-8")
    _write_lock(lock_dir, "EURUSD", "2026-02", cbm, thr)
    (lock_dir / "gbpusd_oco_first_touch_live_lock.json").write_text("[]", encoding="utf-8")

    exit_code = run(
        lock_dir=lock_dir,
        source_models_dir=source_dir,
        target_models_dir=target_dir,
        symbols=["EURUSD", "GBPUSD"],
    )

    out = capsys.readouterr().out
    assert exit_code == 1
    assert "[candidate-sync] EURUSD 2026-02 PASS" in out
    assert "[candidate-sync] GBPUSD" in out
    assert "FAIL" in out
    assert "malformed lock metadata" in out
    assert (target_dir / cbm.name).exists()
