"""TDD tests for the candidate registry."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.behemoth.core.registry import CandidateRegistry

LOCK_DIR = Path("configs/research/governance/oco")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_symbol_lock(
    sym: str,
    lock_dir: Path,
    state_rows: list[dict],
    live_deployable: bool = True,
    model_suffix: str = "2026-02",
) -> None:
    """Write a self-consistent v3 lock file + fake model artifacts for one symbol."""
    # Create model files in bundle-relative models/ directory
    models_dir = lock_dir / "models"
    models_dir.mkdir(exist_ok=True)
    cbm = models_dir / f"{sym}_model_{model_suffix}.cbm"
    thr = models_dir / f"{sym}_model_{model_suffix}.json"
    cbm.write_bytes(b"fake-cbm-" + sym.encode())
    thr.write_text('{"threshold": 0.5}')

    lock = {
        "schema_version": 3,
        "symbol": sym,
        "bundle": {
            "month": model_suffix,
            "dir_relpath": ".",
            "family": "oco_first_touch",
        },
        "artifacts": {
            "model_cbm": {"path": f"models/{cbm.name}", "sha256": _sha256(cbm)},
            "model_threshold_json": {"path": f"models/{thr.name}", "sha256": _sha256(thr)},
        },
        "deployability": {"live_deployable": live_deployable, "model_month": model_suffix},
        "locked_runtime": {"production_cap_pips": 1.2},
        "state_universe": {"rows": state_rows},
    }
    (lock_dir / f"{sym}_oco_first_touch_live_lock.json").write_text(json.dumps(lock))


@pytest.fixture
def hermetic_registry(tmp_path: Path) -> CandidateRegistry:
    """Self-consistent registry with EURUSD and GBPUSD, no real artifacts needed."""
    lock_dir = tmp_path / "locks"
    lock_dir.mkdir()

    _write_symbol_lock(
        "EURUSD",
        lock_dir,
        state_rows=[
            {
                "symbol": "EURUSD",
                "bar_ticks": 100,
                "horizon": 5,
                "barrier_pips": 2.0,
                "state_id": "oco_first_touch__high_range_q70__k1",
                "regime_desc": "high_range_q70",
            }
        ],
    )
    _write_symbol_lock(
        "GBPUSD",
        lock_dir,
        state_rows=[
            {
                "symbol": "GBPUSD",
                "bar_ticks": 100,
                "horizon": 5,
                "barrier_pips": 2.0,
                "state_id": "oco_first_touch__high_range_q70__k2",
                "regime_desc": "high_range_q70",
            },
            {
                "symbol": "GBPUSD",
                "bar_ticks": 100,
                "horizon": 6,
                "barrier_pips": 3.0,
                "state_id": "oco_first_touch__med_range_q50__k1",
                "regime_desc": "med_range_q50",
            },
        ],
    )

    return CandidateRegistry.load(lock_dir)


class TestRegistryLoading:
    def test_loads_from_json_dir(self, hermetic_registry: CandidateRegistry):
        assert len(hermetic_registry.symbols) > 0
        assert "EURUSD" in hermetic_registry.symbols
        assert "GBPUSD" in hermetic_registry.symbols

    def test_invalid_dir_raises(self):
        with pytest.raises(FileNotFoundError):
            CandidateRegistry.load(Path("configs/not_a_real_dir"))

    def test_load_resolves_model_paths_against_models_dir(self, tmp_path: Path):
        """V3 paths are bundle-relative; verify they resolve correctly."""
        lock_dir = tmp_path / "locks"
        lock_dir.mkdir()

        # Create model files in bundle-relative location
        models_dir = lock_dir / "models"
        models_dir.mkdir()
        model_cbm = models_dir / "EURUSD_model_2026-02.cbm"
        model_thr = models_dir / "EURUSD_model_2026-02.json"
        model_cbm.write_bytes(b"cbm-bytes")
        model_thr.write_text('{"threshold": 0.5}')

        lock = {
            "schema_version": 3,
            "symbol": "EURUSD",
            "bundle": {
                "month": "2026-02",
                "dir_relpath": ".",
                "family": "oco_first_touch",
            },
            "artifacts": {
                "model_cbm": {"path": "models/EURUSD_model_2026-02.cbm", "sha256": _sha256(model_cbm)},
                "model_threshold_json": {"path": "models/EURUSD_model_2026-02.json", "sha256": _sha256(model_thr)},
            },
            "deployability": {"live_deployable": True, "model_month": "2026-02"},
            "locked_runtime": {
                "production_cap_pips": 1.2,
                "threshold_mode": "rolling_days",
                "rolling_threshold_days": 20,
                "rolling_threshold_min_history": 300,
                "execution_quantile": 0.9,
            },
            "state_universe": {
                "rows": [
                    {
                        "symbol": "EURUSD",
                        "bar_ticks": 100,
                        "horizon": 5,
                        "barrier_pips": 2.0,
                        "state_id": "oco_first_touch__high_range_q70__k2",
                        "regime_desc": "high_range_q70",
                    }
                ]
            },
        }
        (lock_dir / "EURUSD_oco_first_touch_live_lock.json").write_text(json.dumps(lock))

        reg = CandidateRegistry.load(lock_dir)

        assert reg.symbols == ["EURUSD"]
        bundle_paths = reg.get_bundle_paths("EURUSD")
        assert bundle_paths is not None
        cbm_path = bundle_paths.model_cbm()
        json_path = bundle_paths.model_threshold_json()
        assert cbm_path.is_file()
        assert cbm_path.name == "EURUSD_model_2026-02.cbm"
        assert json_path.is_file()
        assert json_path.name == "EURUSD_model_2026-02.json"
        assert bundle_paths.model_month == "2026-02"


class TestCandidateGeneration:
    def test_gbpusd_has_candidates(self, hermetic_registry: CandidateRegistry):
        cands = hermetic_registry.get_candidates("GBPUSD")
        assert len(cands) >= 1

    def test_unknown_symbol_returns_empty(self, hermetic_registry: CandidateRegistry):
        assert hermetic_registry.get_candidates("XYZABC") == []

    def test_model_binding_present(self, hermetic_registry: CandidateRegistry):
        bundle_paths = hermetic_registry.get_bundle_paths("EURUSD")
        assert bundle_paths is not None
        cbm_path = bundle_paths.model_cbm()
        json_path = bundle_paths.model_threshold_json()
        assert str(cbm_path).endswith(".cbm")
        assert str(json_path).endswith(".json")

    def test_candidate_fields_populated(self, hermetic_registry: CandidateRegistry):
        cands = hermetic_registry.get_candidates("GBPUSD")
        assert cands, "Expected GBPUSD to have candidates"
        c = cands[0]
        assert c.symbol == "GBPUSD"
        assert c.bar_ticks == 100
        assert c.horizon in (5, 6)
        assert c.barrier_pips in (2.0, 3.0)
        assert c.regime_desc != ""
        assert "oco_first_touch" in c.candidate_uid

    def test_candidate_uid_format(self, hermetic_registry: CandidateRegistry):
        cands = hermetic_registry.get_candidates("GBPUSD")
        for c in cands:
            assert "__" in c.candidate_uid
            assert c.candidate_uid.startswith("oco_first_touch")

    def test_all_candidates_count(self, hermetic_registry: CandidateRegistry):
        all_cands = hermetic_registry.all_candidates()
        expected = sum(
            len(hermetic_registry.get_candidates(sym))
            for sym in hermetic_registry.symbols
        )
        assert len(all_cands) == expected
        assert len(all_cands) > 0


def test_candidate_spec_rejects_lookahead_clean_family():
    """A lock that deploys a first_touch_clean candidate must be rejected
    at load time — its win rate is look-ahead-biased and not live-achievable.
    See docs/superpowers/specs/2026-05-15-oco-lookahead-bias-removal-design.md.
    """
    from src.behemoth.core.registry import CandidateSpec

    row = {
        "symbol": "EURUSD", "bar_ticks": 1000, "horizon": 6,
        "barrier_pips": 2.0,
        "state_id": "oco_first_touch_clean__all__k2",
        "regime_desc": "all;barrier=2.0",
    }
    with pytest.raises(ValueError, match="first_touch_clean"):
        CandidateSpec.from_row(row)


def test_candidate_spec_accepts_first_touch_family():
    from src.behemoth.core.registry import CandidateSpec
    row = {
        "symbol": "EURUSD", "bar_ticks": 1000, "horizon": 6,
        "barrier_pips": 2.0,
        "state_id": "oco_first_touch__all__k2",
        "regime_desc": "all;barrier=2.0",
    }
    spec = CandidateSpec.from_row(row)
    assert spec.candidate_uid == "oco_first_touch__all__k2"
