"""TDD tests for the candidate registry."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.behemoth.core.registry import CandidateRegistry

LOCK_DIR = Path("configs/research/governance/oco")


class TestRegistryLoading:
    def test_loads_from_json_dir(self):
        reg = CandidateRegistry.load(LOCK_DIR)
        assert len(reg.symbols) > 0
        assert "EURUSD" in reg.symbols
        assert "GBPUSD" in reg.symbols

    def test_invalid_dir_raises(self):
        with pytest.raises(FileNotFoundError):
            CandidateRegistry.load(Path("configs/not_a_real_dir"))


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
