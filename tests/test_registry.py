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
    models_dir: Path,
    state_rows: list[dict],
    live_deployable: bool = True,
    model_suffix: str = "2026-02",
) -> None:
    """Write a self-consistent lock file + fake model artifacts for one symbol."""
    cbm = models_dir / f"{sym}_model_{model_suffix}.cbm"
    thr = models_dir / f"{sym}_model_{model_suffix}.json"
    cbm.write_bytes(b"fake-cbm-" + sym.encode())
    thr.write_text('{"threshold": 0.5}')

    lock = {
        "symbol": sym,
        "frozen_at_utc": f"2026-{model_suffix}-01T00:00:00Z",
        "artifacts": {
            "live_deployable": live_deployable,
            "model_cbm_path": f"models/oco/{cbm.name}",
            "model_cbm_sha256": _sha256(cbm),
            "model_threshold_json_path": f"models/oco/{thr.name}",
            "model_threshold_json_sha256": _sha256(thr),
            "model_month": model_suffix,
        },
        "locked_runtime": {"production_cap_pips": 1.2},
        "state_universe": {"rows": state_rows},
    }
    (lock_dir / f"{sym}_oco_live_lock.json").write_text(json.dumps(lock))


@pytest.fixture
def hermetic_registry(tmp_path: Path) -> CandidateRegistry:
    """Self-consistent registry with EURUSD and GBPUSD, no real artifacts needed."""
    lock_dir = tmp_path / "locks"
    models_dir = tmp_path / "models"
    lock_dir.mkdir()
    models_dir.mkdir()

    _write_symbol_lock(
        "EURUSD",
        lock_dir,
        models_dir,
        state_rows=[
            {
                "symbol": "EURUSD",
                "bar_ticks": 100,
                "horizon": 5,
                "barrier_pips": 2.0,
                "state_id": "oco_first_touch_clean__high_range_q70__k1",
                "regime_desc": "high_range_q70",
            }
        ],
    )
    _write_symbol_lock(
        "GBPUSD",
        lock_dir,
        models_dir,
        state_rows=[
            {
                "symbol": "GBPUSD",
                "bar_ticks": 100,
                "horizon": 5,
                "barrier_pips": 2.0,
                "state_id": "oco_first_touch_clean__high_range_q70__k2",
                "regime_desc": "high_range_q70",
            },
            {
                "symbol": "GBPUSD",
                "bar_ticks": 100,
                "horizon": 6,
                "barrier_pips": 3.0,
                "state_id": "oco_first_touch_clean__med_range_q50__k1",
                "regime_desc": "med_range_q50",
            },
        ],
    )

    return CandidateRegistry.load(lock_dir, models_dir=models_dir)


class TestRegistryLoading:
    def test_loads_from_json_dir(self, hermetic_registry: CandidateRegistry):
        assert len(hermetic_registry.symbols) > 0
        assert "EURUSD" in hermetic_registry.symbols
        assert "GBPUSD" in hermetic_registry.symbols

    def test_invalid_dir_raises(self):
        with pytest.raises(FileNotFoundError):
            CandidateRegistry.load(Path("configs/not_a_real_dir"))

    def test_load_resolves_model_paths_against_models_dir(self, tmp_path: Path):
        lock_dir = tmp_path / "locks"
        models_dir = tmp_path / "models_alt"
        lock_dir.mkdir()
        models_dir.mkdir()

        model_cbm = models_dir / "EURUSD_model_2026-02.cbm"
        model_thr = models_dir / "EURUSD_model_2026-02.json"
        model_cbm.write_bytes(b"cbm-bytes")
        model_thr.write_text('{"threshold": 0.5}')

        lock = {
            "symbol": "EURUSD",
            "frozen_at_utc": "2026-03-25T00:00:00Z",
            "artifacts": {
                "live_deployable": True,
                "model_cbm_path": "models/oco/EURUSD_model_2026-02.cbm",
                "model_cbm_sha256": _sha256(model_cbm),
                "model_threshold_json_path": "models/oco/EURUSD_model_2026-02.json",
                "model_threshold_json_sha256": _sha256(model_thr),
                "model_month": "2026-02",
            },
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
                        "state_id": "oco_first_touch_clean__high_range_q70__k2",
                        "regime_desc": "high_range_q70",
                    }
                ]
            },
        }
        (lock_dir / "EURUSD_oco_live_lock.json").write_text(json.dumps(lock))

        reg = CandidateRegistry.load(lock_dir, models_dir=models_dir)

        assert reg.symbols == ["EURUSD"]
        binding = reg.get_model_binding("EURUSD")
        assert binding is not None
        assert Path(binding["model_cbm_path"]) == model_cbm
        assert Path(binding["model_threshold_json_path"]) == model_thr
        assert binding["locked_runtime_overrides"]["threshold_source"] == "rolling_days"
        assert binding["locked_runtime_overrides"]["rolling_threshold_min_history"] == 300


class TestCandidateGeneration:
    def test_gbpusd_has_candidates(self, hermetic_registry: CandidateRegistry):
        cands = hermetic_registry.get_candidates("GBPUSD")
        assert len(cands) >= 1

    def test_unknown_symbol_returns_empty(self, hermetic_registry: CandidateRegistry):
        assert hermetic_registry.get_candidates("XYZABC") == []

    def test_model_binding_present(self, hermetic_registry: CandidateRegistry):
        binding = hermetic_registry.get_model_binding("EURUSD")
        assert binding is not None
        assert binding["model_cbm_path"].endswith(".cbm")
        assert binding["model_threshold_json_path"].endswith(".json")
        assert len(str(binding["model_cbm_sha256"])) == 64
        assert len(str(binding["model_threshold_json_sha256"])) == 64

    def test_candidate_fields_populated(self, hermetic_registry: CandidateRegistry):
        cands = hermetic_registry.get_candidates("GBPUSD")
        assert cands, "Expected GBPUSD to have candidates"
        c = cands[0]
        assert c.symbol == "GBPUSD"
        assert c.bar_ticks == 100
        assert c.horizon in (5, 6)
        assert c.barrier_pips in (2.0, 3.0)
        assert c.regime_desc != ""
        assert "oco_first_touch_clean" in c.candidate_uid

    def test_candidate_uid_format(self, hermetic_registry: CandidateRegistry):
        cands = hermetic_registry.get_candidates("GBPUSD")
        for c in cands:
            assert "__" in c.candidate_uid
            assert c.candidate_uid.startswith("oco_first_touch_clean")

    def test_all_candidates_count(self, hermetic_registry: CandidateRegistry):
        all_cands = hermetic_registry.all_candidates()
        expected = sum(
            len(hermetic_registry.get_candidates(sym))
            for sym in hermetic_registry.symbols
        )
        assert len(all_cands) == expected
        assert len(all_cands) > 0
