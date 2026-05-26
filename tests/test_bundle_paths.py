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
    family: str = "oco_first_touch",
    symbol: str = "EURUSD",
) -> Path:
    bundle_dir = tmp_path / "configs/research/governance/oco_candidate_builds/2026-04"
    (bundle_dir / "models").mkdir(parents=True)
    (bundle_dir / "configs").mkdir(parents=True)

    pred_bytes = b"prediction-bytes"
    states_bytes = b"states-bytes"
    cbm_bytes = b"cbm-bytes"
    thr_bytes = b"thr-bytes"

    (bundle_dir / f"{symbol.lower()}_oco_first_touch_locked_predictions.parquet").write_bytes(pred_bytes)
    (bundle_dir / f"{symbol.lower()}_oco_first_touch_allowed_states.csv").write_bytes(states_bytes)
    (bundle_dir / "models" / f"{symbol}_oco_first_touch_model_2026-04.cbm").write_bytes(cbm_bytes)
    (bundle_dir / "models" / f"{symbol}_oco_first_touch_model_2026-04.json").write_bytes(thr_bytes)

    lock = {
        "schema_version": 3,
        "symbol": symbol,
        "bundle": {"month": "2026-04", "dir_relpath": str(bundle_dir), "family": family},
        "artifacts": {
            "predictions": {
                "path": f"{symbol.lower()}_oco_first_touch_locked_predictions.parquet",
                "sha256": _sha256(pred_bytes),
            },
            "allowed_states_csv": {
                "path": f"{symbol.lower()}_oco_first_touch_allowed_states.csv",
                "sha256": _sha256(states_bytes),
            },
            "model_cbm": {
                "path": f"models/{symbol}_oco_first_touch_model_2026-04.cbm",
                "sha256": _sha256(cbm_bytes),
            },
            "model_threshold_json": {
                "path": f"models/{symbol}_oco_first_touch_model_2026-04.json",
                "sha256": _sha256(thr_bytes),
            },
        },
        "deployability": {"live_deployable": True, "model_month": "2026-04"},
    }
    lock_path = bundle_dir / f"{symbol.lower()}_oco_first_touch_live_lock.json"
    lock_path.write_text(json.dumps(lock, indent=2))
    return lock_path


def _write_v3_bundle_at(
    bundle_dir: Path,
    symbol: str,
    family: str,
    artifact_basenames: dict[str, str] | None = None,
) -> Path:
    (bundle_dir / "models").mkdir(parents=True, exist_ok=True)
    artifact_basenames = artifact_basenames or {}
    pred_name = artifact_basenames.get(
        "predictions", f"{symbol.lower()}_oco_first_touch_locked_predictions.parquet"
    )
    states_name = artifact_basenames.get(
        "allowed_states_csv", f"{symbol.lower()}_oco_first_touch_allowed_states.csv"
    )
    pred = b"prediction-bytes"
    states = b"states-bytes"
    cbm = b"cbm-bytes"
    thr = b"thr-bytes"
    (bundle_dir / pred_name).write_bytes(pred)
    (bundle_dir / states_name).write_bytes(states)
    (bundle_dir / "models" / f"{symbol}_oco_first_touch_model_2026-04.cbm").write_bytes(cbm)
    (bundle_dir / "models" / f"{symbol}_oco_first_touch_model_2026-04.json").write_bytes(thr)
    lock = {
        "schema_version": 3,
        "symbol": symbol,
        "bundle": {"month": "2026-04", "dir_relpath": str(bundle_dir), "family": family},
        "artifacts": {
            "predictions": {"path": pred_name, "sha256": _sha256(pred)},
            "allowed_states_csv": {"path": states_name, "sha256": _sha256(states)},
            "model_cbm": {
                "path": f"models/{symbol}_oco_first_touch_model_2026-04.cbm",
                "sha256": _sha256(cbm),
            },
            "model_threshold_json": {
                "path": f"models/{symbol}_oco_first_touch_model_2026-04.json",
                "sha256": _sha256(thr),
            },
        },
        "deployability": {"live_deployable": True, "model_month": "2026-04"},
    }
    lock_path = bundle_dir / f"{symbol.lower()}_oco_first_touch_live_lock.json"
    lock_path.write_text(json.dumps(lock, indent=2))
    return lock_path


def test_from_lock_resolves_predictions(tmp_path: Path) -> None:
    lock_path = _write_v3_bundle(tmp_path)

    bp = BundlePaths.from_lock(lock_path)

    expected = lock_path.parent / "eurusd_oco_first_touch_locked_predictions.parquet"
    assert bp.predictions() == expected
    assert bp.allowed_states_csv() == lock_path.parent / "eurusd_oco_first_touch_allowed_states.csv"
    assert bp.model_cbm() == lock_path.parent / "models" / "EURUSD_oco_first_touch_model_2026-04.cbm"
    assert bp.model_threshold_json() == lock_path.parent / "models" / "EURUSD_oco_first_touch_model_2026-04.json"


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
    (lock_path.parent / "eurusd_oco_first_touch_locked_predictions.parquet").write_bytes(b"corrupted")
    with pytest.raises(BundleIntegrityError, match="sha256 mismatch"):
        bp.predictions()


def test_missing_file_raises(tmp_path: Path) -> None:
    lock_path = _write_v3_bundle(tmp_path)
    (lock_path.parent / "eurusd_oco_first_touch_locked_predictions.parquet").unlink()
    bp = BundlePaths.from_lock(lock_path)
    with pytest.raises(BundleIntegrityError, match="missing artifact"):
        bp.predictions()


def test_bundle_layouts_exposes_oco_family() -> None:
    from src.behemoth.core.bundle_paths import BUNDLE_LAYOUTS, bundle_layout_for

    assert "oco_first_touch" in BUNDLE_LAYOUTS
    layout = bundle_layout_for("oco_first_touch")
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

    assert bp.family == "oco_first_touch"


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


def test_iter_locks_yields_all_live_locks(tmp_path: Path) -> None:
    from src.behemoth.core.bundle_paths import iter_locks

    bundle = tmp_path / "2026-04"
    bundle.mkdir()
    a = bundle / "eurusd_oco_first_touch_live_lock.json"
    b = bundle / "gbpusd_oco_first_touch_live_lock.json"
    a.write_text("{}")
    b.write_text("{}")
    (bundle / "not_a_lock.json").write_text("{}")

    paths = sorted(iter_locks(bundle))
    assert paths == sorted([a, b])


def test_iter_locks_filters_by_family(tmp_path: Path) -> None:
    """Yield only locks whose bundle.family matches."""
    from src.behemoth.core.bundle_paths import BUNDLE_LAYOUTS, BundleArtifactSpec, iter_locks

    bundle = tmp_path / "2026-04"
    bundle.mkdir()
    oco_lock = _write_v3_bundle_at(bundle, symbol="EURUSD", family="oco_first_touch")
    BUNDLE_LAYOUTS["test_breakout"] = (
        BundleArtifactSpec("predictions", "gbpusd_breakout_predictions.parquet", True),
        BundleArtifactSpec("allowed_states_csv", "gbpusd_breakout_states.csv", True),
        BundleArtifactSpec("model_cbm", "models/GBPUSD_model_2026-04.cbm", True),
        BundleArtifactSpec("model_threshold_json", "models/GBPUSD_model_2026-04.json", True),
    )
    try:
        breakout_lock = _write_v3_bundle_at(
            bundle,
            symbol="GBPUSD",
            family="test_breakout",
            artifact_basenames={
                "predictions": "gbpusd_breakout_predictions.parquet",
                "allowed_states_csv": "gbpusd_breakout_states.csv",
            },
        )

        assert sorted(iter_locks(bundle, family="oco_first_touch")) == [oco_lock]
        assert sorted(iter_locks(bundle, family="test_breakout")) == [breakout_lock]
    finally:
        BUNDLE_LAYOUTS.pop("test_breakout", None)


def test_iter_locks_skips_invalid_locks_with_warning(tmp_path: Path, caplog) -> None:
    """A malformed lock does not break the scan."""
    from src.behemoth.core.bundle_paths import iter_locks

    bundle = tmp_path / "2026-04"
    bundle.mkdir()
    good = _write_v3_bundle_at(bundle, symbol="EURUSD", family="oco_first_touch")
    bad = bundle / "broken_oco_first_touch_live_lock.json"
    bad.write_text("{not json")

    assert good in iter_locks(bundle)
    assert bad in iter_locks(bundle)

    with caplog.at_level("WARNING", logger="behemoth.governance"):
        filtered = list(iter_locks(bundle, family="oco_first_touch"))
    assert good in filtered
    assert bad not in filtered
    assert any("failed to parse" in record.message for record in caplog.records)


def test_lock_filename_returns_canonical_form() -> None:
    from src.behemoth.core.bundle_paths import lock_filename

    assert lock_filename("EURUSD", "oco_first_touch") == "eurusd_oco_first_touch_live_lock.json"
    assert lock_filename("eurusd", "oco_first_touch") == "eurusd_oco_first_touch_live_lock.json"


def test_lock_filename_requires_family() -> None:
    """lock_filename takes (symbol, family); passing one arg is a TypeError."""
    from src.behemoth.core.bundle_paths import lock_filename

    assert lock_filename("EURUSD", "directional") == "eurusd_directional_live_lock.json"
    assert lock_filename("eurusd", "oco_first_touch") == "eurusd_oco_first_touch_live_lock.json"

    with pytest.raises(TypeError):
        lock_filename("EURUSD")  # type: ignore[call-arg]


def test_bundle_layouts_keys_match_mining_family_registry() -> None:
    """BUNDLE_LAYOUTS must register every family known to mining."""
    from scripts.mining_family import FAMILY_REGISTRY
    from src.behemoth.core.bundle_paths import BUNDLE_LAYOUTS

    layout_families = set(BUNDLE_LAYOUTS.keys())
    mining_families = set(FAMILY_REGISTRY.keys())

    missing_in_layouts = mining_families - layout_families
    extra_in_layouts = layout_families - mining_families

    assert not missing_in_layouts, f"BUNDLE_LAYOUTS missing families: {missing_in_layouts}"
    assert not extra_in_layouts, f"BUNDLE_LAYOUTS has unknown families: {extra_in_layouts}"


@pytest.mark.parametrize(
    "family",
    [
        "oco_first_touch",
        "oco_asymmetric",
        "directional",
        "directional_inverse",
        "directional_run",
        "double_touch",
        "pullback",
        "no_touch",
        "dollar_residual",
        "dispersion_rank",
        "lead_lag",
    ],
)
def test_bundle_layout_registered_for_every_mining_family(family: str) -> None:
    """Each mining family in FAMILY_REGISTRY has a BUNDLE_LAYOUTS row."""
    from src.behemoth.core.bundle_paths import BUNDLE_LAYOUTS, bundle_layout_for

    assert family in BUNDLE_LAYOUTS
    layout = bundle_layout_for(family)

    # Required artifact keys present
    required_keys = {"predictions", "allowed_states_csv", "model_cbm", "model_threshold_json"}
    keys = {spec.v2_key for spec in layout}
    assert required_keys <= keys


@pytest.mark.parametrize(
    "family",
    [
        "oco_first_touch", "oco_asymmetric", "directional", "directional_inverse",
        "directional_run", "double_touch", "pullback", "no_touch",
        "dollar_residual", "dispersion_rank", "lead_lag",
    ],
)
def test_bundle_layout_templates_render_bundle_relative(family: str) -> None:
    """Every template in every family layout renders to a bundle-relative path."""
    from src.behemoth.core.bundle_paths import bundle_layout_for

    layout = bundle_layout_for(family)
    fmt = {"symbol_lower": "eurusd", "symbol_upper": "EURUSD", "family": family, "month": "2026-04"}
    rendered_paths = set()
    for spec in layout:
        relpath = spec.target_relpath_template.format(**fmt)
        # Bundle-relative: no leading slash, no parent escapes.
        assert not relpath.startswith("/"), f"{family}/{spec.v2_key}: {relpath}"
        assert ".." not in relpath.split("/"), f"{family}/{spec.v2_key}: {relpath}"
        # No unsubstituted tokens.
        assert "{" not in relpath and "}" not in relpath, f"{family}/{spec.v2_key}: unsubstituted token in {relpath}"
        rendered_paths.add(relpath)


def test_bundle_layout_families_distinct_for_same_symbol_and_month() -> None:
    """Different families produce distinct artifact filenames for the same symbol/month."""
    from src.behemoth.core.bundle_paths import BUNDLE_LAYOUTS

    fmt_base = {"symbol_lower": "eurusd", "symbol_upper": "EURUSD", "month": "2026-04"}
    all_relpaths: list[str] = []
    for family, layout in BUNDLE_LAYOUTS.items():
        fmt = {**fmt_base, "family": family}
        for spec in layout:
            all_relpaths.append(spec.target_relpath_template.format(**fmt))

    # Each rendered path must be unique across families (no collision).
    assert len(all_relpaths) == len(set(all_relpaths)), (
        "duplicate rendered paths across families: "
        f"{[p for p in all_relpaths if all_relpaths.count(p) > 1]}"
    )


def test_directional_family_round_trip(tmp_path: Path) -> None:
    """A directional-family lock can be written, read, and validated end-to-end."""
    import hashlib
    import json
    import subprocess
    import sys

    from src.behemoth.core.bundle_paths import BundlePaths, bundle_layout_for

    bundle_dir = tmp_path / "2026-04"
    (bundle_dir / "models").mkdir(parents=True)

    layout = bundle_layout_for("directional")
    fmt = {"symbol_lower": "eurusd", "symbol_upper": "EURUSD", "family": "directional", "month": "2026-04"}

    # Build a synthetic file per required artifact.
    artifacts_block = {}
    for spec in layout:
        if not spec.required:
            continue
        relpath = spec.target_relpath_template.format(**fmt)
        abs_path = bundle_dir / relpath
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        content = f"synthetic-{spec.v2_key}".encode()
        abs_path.write_bytes(content)
        artifacts_block[spec.v2_key] = {
            "path": relpath,
            "sha256": hashlib.sha256(content).hexdigest(),
        }

    lock = {
        "schema_version": 3,
        "symbol": "EURUSD",
        "bundle": {"month": "2026-04", "dir_relpath": str(bundle_dir), "family": "directional"},
        "artifacts": artifacts_block,
        "deployability": {"live_deployable": True, "model_month": "2026-04"},
    }
    lock_path = bundle_dir / "eurusd_directional_live_lock.json"
    lock_path.write_text(json.dumps(lock))

    # Resolver works.
    parsed = BundlePaths.from_lock(lock_path)
    assert parsed.family == "directional"
    assert parsed.predictions().name == "eurusd_directional_locked_predictions.parquet"
    assert parsed.model_cbm().name == "EURUSD_directional_model_2026-04.cbm"

    # validate_bundle accepts the dir.
    result = subprocess.run(
        [sys.executable, "scripts/validate_bundle.py", str(bundle_dir)],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
    )
    assert result.returncode == 0, result.stderr


def test_bundle_paths_exposes_cross_symbol_scope(tmp_path: Path) -> None:
    from src.behemoth.core.bundle_paths import BundlePaths

    lock = tmp_path / "eurusd_dollar_residual_live_lock.json"
    pred = tmp_path / "eurusd_dollar_residual_locked_predictions.parquet"
    pred.write_text("x", encoding="utf-8")
    lock.write_text(
        json.dumps(
            {
                "schema_version": 3,
                "symbol": "EURUSD",
                "bundle": {
                    "family": "dollar_residual",
                    "model_month": "2026-04",
                    "cross_symbol_scope": {
                        "symbols": ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD"],
                        "alignment": "close_ts_inner_join",
                        "source": "scripts.cross_symbol",
                    },
                },
                "artifacts": {
                    "predictions": {
                        "path": "eurusd_dollar_residual_locked_predictions.parquet",
                        "sha256": hashlib.sha256(b"x").hexdigest(),
                        "required": True,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    paths = BundlePaths.from_lock(lock)

    assert paths.family == "dollar_residual"
    assert paths.cross_symbol_scope["alignment"] == "close_ts_inner_join"
    assert "GBPUSD" in paths.cross_symbol_scope["symbols"]
