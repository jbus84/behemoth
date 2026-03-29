"""TDD tests for the candidate registry."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.behemoth.core.registry import CandidateRegistry

LOCK_DIR = Path("configs/research/governance/oco")
MODELS_DIR = Path("models/oco")

_has_model_artifacts = MODELS_DIR.exists() and any(MODELS_DIR.glob("*.cbm"))
_skip_no_models = pytest.mark.skipif(
    not _has_model_artifacts,
    reason="model artifacts not present (gitignored)",
)


class TestRegistryLoading:
    @_skip_no_models
    def test_loads_from_json_dir(self):
        reg = CandidateRegistry.load(LOCK_DIR)
        assert len(reg.symbols) > 0
        assert "EURUSD" in reg.symbols
        assert "GBPUSD" in reg.symbols

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

        def sha256(path: Path) -> str:
            return hashlib.sha256(path.read_bytes()).hexdigest()

        lock = {
            "symbol": "EURUSD",
            "frozen_at_utc": "2026-03-25T00:00:00Z",
            "artifacts": {
                "live_deployable": True,
                "model_cbm_path": "models/oco/EURUSD_model_2026-02.cbm",
                "model_cbm_sha256": sha256(model_cbm),
                "model_threshold_json_path": "models/oco/EURUSD_model_2026-02.json",
                "model_threshold_json_sha256": sha256(model_thr),
                "model_month": "2026-02",
            },
            "locked_runtime": {"production_cap_pips": 1.2},
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


@_skip_no_models
class TestCandidateGeneration:
    @pytest.fixture
    def registry(self) -> CandidateRegistry:
        return CandidateRegistry.load(LOCK_DIR)

    def test_gbpusd_has_candidates(self, registry):
        cands = registry.get_candidates("GBPUSD")
        assert len(cands) >= 1

    def test_unknown_symbol_returns_empty(self, registry):
        assert registry.get_candidates("XYZABC") == []

    def test_model_binding_present(self, registry):
        binding = registry.get_model_binding("EURUSD")
        assert binding is not None
        assert binding["model_cbm_path"].endswith(".cbm")
        assert binding["model_threshold_json_path"].endswith(".json")
        assert len(str(binding["model_cbm_sha256"])) == 64
        assert len(str(binding["model_threshold_json_sha256"])) == 64

    def test_candidate_fields_populated(self, registry):
        cands = registry.get_candidates("GBPUSD")
        assert cands, "Expected GBPUSD to have candidates"
        c = cands[0]
        assert c.symbol == "GBPUSD"
        assert c.bar_ticks == 100
        assert c.horizon in (5, 6)
        assert c.barrier_pips in (2.0, 3.0)
        assert c.regime_desc != ""
        assert "oco_first_touch_clean" in c.candidate_uid

    def test_candidate_uid_format(self, registry):
        cands = registry.get_candidates("GBPUSD")
        for c in cands:
            # WFO output format is library|symbol|bar_ticks|hN|state_id
            # Wait, the state_id IS the candidate_uid in the JSON
            # so it should be e.g. oco_first_touch_clean__high_range_q70__k2
            assert "__" in c.candidate_uid
            assert c.candidate_uid.startswith("oco_first_touch_clean")

    def test_all_candidates_count(self, registry):
        all_cands = registry.all_candidates()
        expected = sum(len(registry.get_candidates(sym)) for sym in registry.symbols)
        assert len(all_cands) == expected
        assert len(all_cands) > 0
