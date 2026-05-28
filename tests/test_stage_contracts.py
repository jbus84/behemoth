from __future__ import annotations


class TestManifestExists:
    def test_can_import_stage_contracts(self):
        from behemoth.governance.stage_contracts import (
            MINING_LIBRARY_FAMILIES,
            MINING_OUTPUT_LIBRARIES,
        )

        assert isinstance(MINING_LIBRARY_FAMILIES, dict)
        assert "directional" in MINING_LIBRARY_FAMILIES
        assert len(MINING_OUTPUT_LIBRARIES) == 7


class TestMiningAlignsWithManifest:
    def test_mining_output_libraries_match_manifest(self):
        from behemoth.governance.stage_contracts import MINING_OUTPUT_LIBRARIES

        expected = [
            "directional", "oco", "oco_asymmetric", "no_touch",
            "dollar_residual", "dispersion_rank", "lead_lag",
        ]
        assert expected == MINING_OUTPUT_LIBRARIES


class TestManifestInvariants:
    def test_all_manifest_families_are_registered(self):
        from behemoth.governance.stage_contracts import FAMILY_TO_LIBRARY
        from scripts.mining_family import FAMILY_REGISTRY

        manifest_families = set(FAMILY_TO_LIBRARY.keys())
        registry_families = set(FAMILY_REGISTRY.keys())
        assert manifest_families == registry_families, (
            f"manifest families {manifest_families} != registry families {registry_families}"
        )

    def test_quality_tier_library_is_valid(self):
        from behemoth.governance.stage_contracts import QUALITY_TIER_LIBRARY

        valid_tiers = {"directional", "oco", "no_touch"}
        for lib, tier in QUALITY_TIER_LIBRARY.items():
            assert tier in valid_tiers, f"{lib} -> invalid tier {tier}"

    def test_wfo_family_sets_partition_all_families(self):
        from behemoth.governance.stage_contracts import (
            CROSS_SYMBOL_FAMILIES,
            FAMILY_TO_LIBRARY,
            LOCAL_FAMILIES,
        )

        all_families = set(FAMILY_TO_LIBRARY.keys())
        assert all_families == LOCAL_FAMILIES | CROSS_SYMBOL_FAMILIES
        assert not (LOCAL_FAMILIES & CROSS_SYMBOL_FAMILIES)

    def test_mining_output_libraries_match_keys(self):
        from behemoth.governance.stage_contracts import (
            MINING_LIBRARY_FAMILIES,
            MINING_OUTPUT_LIBRARIES,
        )

        assert list(MINING_LIBRARY_FAMILIES.keys()) == MINING_OUTPUT_LIBRARIES

    def test_required_columns_include_wfo_consumed_columns(self):
        from behemoth.governance.stage_contracts import CANDIDATE_REQUIRED_COLUMNS

        wfo_consumed = {
            "family",
            "state_id",
            "symbol",
            "horizon",
            "bar_ticks",
            "train_count",
            "mean_gross_pips_train",
        }
        missing = wfo_consumed - set(CANDIDATE_REQUIRED_COLUMNS)
        assert not missing, f"required columns missing: {missing}"

    def test_build_mining_output_manifest_structure(self):
        from behemoth.governance.stage_contracts import (
            MINING_OUTPUT_LIBRARIES,
            build_mining_output_manifest,
        )

        manifest = build_mining_output_manifest(symbol="EURUSD")
        assert manifest["stage"] == "stage02"
        assert manifest["symbol"] == "EURUSD"
        assert set(manifest["output_files"].keys()) == set(MINING_OUTPUT_LIBRARIES)
        assert manifest["library_families"]["directional"] == [
            "directional", "directional_inverse", "directional_run", "double_touch", "pullback"
        ]

    def test_render_stage_io_contract_returns_markdown_for_stage02(self):
        from behemoth.governance.stage_contracts import render_stage_io_contract

        md = render_stage_io_contract("stage02")
        assert "Stage 02 I/O Contract" in md
        assert "Library → family expansion" in md
        assert "directional_candidates.csv" in md
        assert "directional" in md

    def test_render_stage_io_contract_returns_empty_for_unknown_stage(self):
        from behemoth.governance.stage_contracts import render_stage_io_contract

        assert render_stage_io_contract("stage99") == ""
