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
        assert manifest["library_families"]["oco"] == ["oco_first_touch"]
        assert manifest["output_files"]["oco"] == "EURUSD_oco_candidates.csv"

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


class TestArtifactKeys:
    def test_verdict_bearing_stages_are_family_keyed(self):
        """Stage 3 predictions and Stage 5/6 verdict artifacts must be keyed by
        (symbol, family) so per-family results never collide. Only the Stage 2
        candidate CSVs (which aggregate a whole library) may be library-keyed.
        Regression for ADR 0004 failure mode 4 (tick-exact verdict collision)."""
        from behemoth.governance.stage_contracts import ARTIFACT_KEY

        assert ARTIFACT_KEY["stage02_candidates"] == "(symbol, library)"
        assert ARTIFACT_KEY["stage03_predictions"] == "(symbol, family)"
        assert ARTIFACT_KEY["stage05_reduced_core"] == "(symbol, family)"
        assert ARTIFACT_KEY["stage06_tick_exact"] == "(symbol, family)"

    def test_stage03_outputs_are_family_keyed_not_library(self):
        from behemoth.governance.stage_contracts import STAGE03_CONTRACT

        for pat in STAGE03_CONTRACT["output_patterns"]:
            assert "{family}" in pat and "{library}" not in pat, pat
            # the directory must not carry a symbol suffix (wfo_m3to1_<family>_fullcap)
            assert "_fullcap_{symbol}" not in pat, pat

    def test_tick_exact_summary_path_is_family_keyed(self):
        """Two families that share the directional candidate library must resolve
        to distinct tick-exact summary files for the same symbol."""
        from behemoth.governance.stage_contracts import tick_exact_summary_path

        p_dir = tick_exact_summary_path(symbol="EURUSD", family="directional")
        p_inv = tick_exact_summary_path(symbol="EURUSD", family="directional_inverse")
        assert p_dir.endswith("EURUSD_directional_tick_exact_summary.csv")
        assert p_inv.endswith("EURUSD_directional_inverse_tick_exact_summary.csv")
        assert p_dir != p_inv

    def test_tick_exact_directional_set_matches_manifest(self):
        """The tick-exact script's directional-library family set must equal the
        manifest's, or families like double_touch fall through to the oco branch
        and write colliding `<symbol>_oco_tick_exact_*` outputs."""
        from behemoth.governance.stage_contracts import MINING_LIBRARY_FAMILIES
        from scripts.verify_tick_exact_shortlist import _DIRECTIONAL_FAMILIES

        assert set(MINING_LIBRARY_FAMILIES["directional"]) == _DIRECTIONAL_FAMILIES

    def test_verify_tick_exact_defaults_match_manifest_and_dont_collide(self):
        """The tick-exact script's derived output paths must be family-keyed and
        agree with the manifest helper (single source of truth)."""
        from behemoth.governance.stage_contracts import tick_exact_summary_path
        from scripts.verify_tick_exact_shortlist import _derive_symbol_defaults

        for fam in ("directional", "directional_inverse", "double_touch", "pullback"):
            d = _derive_symbol_defaults("EURUSD", family=fam)
            assert d["out_summary_csv"] == tick_exact_summary_path(symbol="EURUSD", family=fam)
        # the five directional-library families must not collide
        summaries = {
            _derive_symbol_defaults("EURUSD", family=f)["out_summary_csv"]
            for f in ("directional", "directional_inverse", "directional_run", "double_touch", "pullback")
        }
        assert len(summaries) == 5


class TestOcoFirstTouchSplit:
    """Guardrails for the oco / oco_first_touch library-family split.

    The mining pipeline writes one candidate CSV per *library* (e.g.
    ``<SYM>_oco_candidates.csv``).  Inside that CSV every row carries
    ``family == "oco_first_touch"``.  Downstream WFO, reduced-core and
    tick-exact artifacts are keyed by *family*, but historically the OCO
    governance stack uses the ``oco`` slug in filenames.  Renaming those
    artifacts is a separate migration (Tasks 2-4); this class locks the
    current manifest so nothing drifts prematurely.
    """

    def test_oco_library_contains_only_first_touch_family(self):
        from behemoth.governance.stage_contracts import MINING_LIBRARY_FAMILIES

        assert MINING_LIBRARY_FAMILIES["oco"] == ["oco_first_touch"]

    def test_oco_quality_tier_library_is_oco(self):
        from behemoth.governance.stage_contracts import QUALITY_TIER_LIBRARY

        assert QUALITY_TIER_LIBRARY["oco"] == "oco"
        assert QUALITY_TIER_LIBRARY["oco_asymmetric"] == "oco"

    def test_oco_stage02_candidate_filename_unchanged(self):
        from behemoth.governance.stage_contracts import CANDIDATE_FILENAME_TEMPLATE

        fname = CANDIDATE_FILENAME_TEMPLATE.format(symbol="EURUSD", library="oco")
        assert fname == "EURUSD_oco_candidates.csv"

    def test_oco_first_touch_resolves_to_oco_library(self):
        from behemoth.governance.stage_contracts import FAMILY_TO_LIBRARY

        assert FAMILY_TO_LIBRARY["oco_first_touch"] == "oco"

    def test_no_wfo_reduced_core_hardcoded_first_touch_slug(self):
        """The stage-contract templates must not prematurely hardcode
        ``oco_first_touch`` into WFO or reduced-core paths.  That would bake
        rename pressure into the manifest before the downstream consumers are
        migrated."""
        from behemoth.governance.stage_contracts import (
            STAGE03_CONTRACT,
            STAGE06_CONTRACT,
            TICK_EXACT_SUMMARY_TEMPLATE,
            WFO_PREDICTION_TEMPLATE,
        )

        assert "oco_first_touch" not in WFO_PREDICTION_TEMPLATE
        assert "oco_first_touch" not in TICK_EXACT_SUMMARY_TEMPLATE
        assert "oco_first_touch" not in str(STAGE03_CONTRACT)
        assert "oco_first_touch" not in str(STAGE06_CONTRACT)
