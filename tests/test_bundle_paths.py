# tests/test_bundle_paths.py
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.behemoth.core.bundle_paths import BundleIntegrityError, BundlePaths


def _sha256(payload: bytes) -> str:
    h = hashlib.sha256()
    h.update(payload)
    return h.hexdigest()


def _write_v3_bundle(
    tmp_path: Path,
    family: str = "oco_first_touch_clean",
    symbol: str = "EURUSD",
) -> Path:
    bundle_dir = tmp_path / "configs/research/governance/oco_candidate_builds/2026-04"
    (bundle_dir / "models").mkdir(parents=True)
    (bundle_dir / "configs").mkdir(parents=True)

    pred_bytes = b"prediction-bytes"
    states_bytes = b"states-bytes"
    cbm_bytes = b"cbm-bytes"
    thr_bytes = b"thr-bytes"

    (bundle_dir / f"{symbol.lower()}_oco_locked_predictions.parquet").write_bytes(pred_bytes)
    (bundle_dir / f"{symbol.lower()}_oco_allowed_states.csv").write_bytes(states_bytes)
    (bundle_dir / "models" / f"{symbol}_model_2026-04.cbm").write_bytes(cbm_bytes)
    (bundle_dir / "models" / f"{symbol}_model_2026-04.json").write_bytes(thr_bytes)

    lock = {
        "schema_version": 3,
        "symbol": symbol,
        "bundle": {"month": "2026-04", "dir_relpath": str(bundle_dir), "family": family},
        "artifacts": {
            "predictions": {
                "path": f"{symbol.lower()}_oco_locked_predictions.parquet",
                "sha256": _sha256(pred_bytes),
            },
            "allowed_states_csv": {
                "path": f"{symbol.lower()}_oco_allowed_states.csv",
                "sha256": _sha256(states_bytes),
            },
            "model_cbm": {
                "path": f"models/{symbol}_model_2026-04.cbm",
                "sha256": _sha256(cbm_bytes),
            },
            "model_threshold_json": {
                "path": f"models/{symbol}_model_2026-04.json",
                "sha256": _sha256(thr_bytes),
            },
        },
        "deployability": {"live_deployable": True, "model_month": "2026-04"},
    }
    lock_path = bundle_dir / f"{symbol.lower()}_oco_live_lock.json"
    lock_path.write_text(json.dumps(lock, indent=2))
    return lock_path


def test_from_lock_resolves_predictions(tmp_path: Path) -> None:
    lock_path = _write_v3_bundle(tmp_path)

    bp = BundlePaths.from_lock(lock_path)

    expected = lock_path.parent / "eurusd_oco_locked_predictions.parquet"
    assert bp.predictions() == expected
    assert bp.allowed_states_csv() == lock_path.parent / "eurusd_oco_allowed_states.csv"
    assert bp.model_cbm() == lock_path.parent / "models" / "EURUSD_model_2026-04.cbm"
    assert bp.model_threshold_json() == lock_path.parent / "models" / "EURUSD_model_2026-04.json"


def test_rejects_absolute_path_in_artifact(tmp_path: Path) -> None:
    lock_path = _write_v3_bundle(tmp_path)
    data = json.loads(lock_path.read_text())
    data["artifacts"]["predictions"]["path"] = str(lock_path.parent / "x.parquet")
    lock_path.write_text(json.dumps(data))

    with pytest.raises(BundleIntegrityError, match="must be bundle-relative"):
        BundlePaths.from_lock(lock_path)


def test_rejects_parent_escape(tmp_path: Path) -> None:
    lock_path = _write_v3_bundle(tmp_path)
    data = json.loads(lock_path.read_text())
    data["artifacts"]["predictions"]["path"] = "../escape.parquet"
    lock_path.write_text(json.dumps(data))

    with pytest.raises(BundleIntegrityError, match="must be bundle-relative"):
        BundlePaths.from_lock(lock_path)


def test_rejects_schema_v2(tmp_path: Path) -> None:
    lock_path = _write_v3_bundle(tmp_path)
    data = json.loads(lock_path.read_text())
    data["schema_version"] = 2
    lock_path.write_text(json.dumps(data))

    with pytest.raises(BundleIntegrityError, match="schema_version=3"):
        BundlePaths.from_lock(lock_path)


def test_predictions_call_verifies_sha(tmp_path: Path) -> None:
    lock_path = _write_v3_bundle(tmp_path)
    bp = BundlePaths.from_lock(lock_path)
    # Corrupt the on-disk file after construction.
    (lock_path.parent / "eurusd_oco_locked_predictions.parquet").write_bytes(b"corrupted")
    with pytest.raises(BundleIntegrityError, match="sha256 mismatch"):
        bp.predictions()


def test_missing_file_raises(tmp_path: Path) -> None:
    lock_path = _write_v3_bundle(tmp_path)
    (lock_path.parent / "eurusd_oco_locked_predictions.parquet").unlink()
    bp = BundlePaths.from_lock(lock_path)
    with pytest.raises(BundleIntegrityError, match="missing artifact"):
        bp.predictions()


def test_bundle_layouts_exposes_oco_family() -> None:
    from src.behemoth.core.bundle_paths import BUNDLE_LAYOUTS, bundle_layout_for

    assert "oco_first_touch_clean" in BUNDLE_LAYOUTS
    layout = bundle_layout_for("oco_first_touch_clean")
    assert {spec.v2_key for spec in layout} >= {
        "predictions",
        "allowed_states_csv",
        "model_cbm",
        "model_threshold_json",
    }


def test_bundle_layouts_rejects_unknown_family() -> None:
    from src.behemoth.core.bundle_paths import bundle_layout_for

    with pytest.raises(BundleIntegrityError, match="unknown family"):
        bundle_layout_for("not_a_real_family")


def test_bundle_paths_exposes_family(tmp_path: Path) -> None:
    lock_path = _write_v3_bundle(tmp_path)

    bp = BundlePaths.from_lock(lock_path)

    assert bp.family == "oco_first_touch_clean"


def test_bundle_paths_rejects_v2_lock(tmp_path: Path) -> None:
    lock_path = _write_v3_bundle(tmp_path)
    data = json.loads(lock_path.read_text())
    data["schema_version"] = 2
    del data["bundle"]["family"]
    lock_path.write_text(json.dumps(data))

    with pytest.raises(BundleIntegrityError, match="schema_version=3"):
        BundlePaths.from_lock(lock_path)


def test_bundle_paths_rejects_missing_family(tmp_path: Path) -> None:
    lock_path = _write_v3_bundle(tmp_path)
    data = json.loads(lock_path.read_text())
    del data["bundle"]["family"]
    lock_path.write_text(json.dumps(data))

    with pytest.raises(BundleIntegrityError, match="bundle.family"):
        BundlePaths.from_lock(lock_path)


def test_non_oco_family_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A registered non-OCO family can be written, read, and validated."""
    from src.behemoth.core.bundle_paths import BUNDLE_LAYOUTS, BundleArtifactSpec

    test_layout = (
        BundleArtifactSpec("predictions", "{symbol_lower}_breakout_predictions.parquet", True),
        BundleArtifactSpec("model_cbm", "models/{symbol_upper}_model_{month}.cbm", True),
        BundleArtifactSpec(
            "model_threshold_json", "models/{symbol_upper}_model_{month}.json", True
        ),
        BundleArtifactSpec("allowed_states_csv", "{symbol_lower}_breakout_states.csv", True),
    )
    monkeypatch.setitem(BUNDLE_LAYOUTS, "test_breakout", test_layout)

    bundle_dir = tmp_path / "test_bundle"
    (bundle_dir / "models").mkdir(parents=True)
    pred = b"p"
    cbm = b"c"
    thr = b"t"
    states = b"s"
    (bundle_dir / "eurusd_breakout_predictions.parquet").write_bytes(pred)
    (bundle_dir / "eurusd_breakout_states.csv").write_bytes(states)
    (bundle_dir / "models" / "EURUSD_model_2026-04.cbm").write_bytes(cbm)
    (bundle_dir / "models" / "EURUSD_model_2026-04.json").write_bytes(thr)

    lock = {
        "schema_version": 3,
        "symbol": "EURUSD",
        "bundle": {
            "month": "2026-04",
            "dir_relpath": str(bundle_dir),
            "family": "test_breakout",
        },
        "artifacts": {
            "predictions": {
                "path": "eurusd_breakout_predictions.parquet",
                "sha256": _sha256(pred),
            },
            "allowed_states_csv": {
                "path": "eurusd_breakout_states.csv",
                "sha256": _sha256(states),
            },
            "model_cbm": {"path": "models/EURUSD_model_2026-04.cbm", "sha256": _sha256(cbm)},
            "model_threshold_json": {
                "path": "models/EURUSD_model_2026-04.json",
                "sha256": _sha256(thr),
            },
        },
        "deployability": {"live_deployable": True, "model_month": "2026-04"},
    }
    lock_path = bundle_dir / "eurusd_breakout_live_lock.json"
    lock_path.write_text(json.dumps(lock))

    parsed = BundlePaths.from_lock(lock_path)
    assert parsed.family == "test_breakout"
    assert parsed.predictions().name == "eurusd_breakout_predictions.parquet"
    assert parsed.model_cbm().name == "EURUSD_model_2026-04.cbm"
