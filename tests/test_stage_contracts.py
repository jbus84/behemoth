from __future__ import annotations

import pytest


class TestManifestExists:
    def test_can_import_stage_contracts(self):
        from behemoth.governance.stage_contracts import (
            CANDIDATE_FILENAME_TEMPLATE,
            FAMILY_TO_LIBRARY,
            MINING_LIBRARY_FAMILIES,
            MINING_OUTPUT_LIBRARIES,
            QUALITY_TIER_LIBRARY,
            CANDIDATE_REQUIRED_COLUMNS,
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
        assert MINING_OUTPUT_LIBRARIES == expected
