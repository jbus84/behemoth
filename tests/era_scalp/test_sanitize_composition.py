from scripts.era_scalp.run_era_eur import _sanitize_composition


def test_flattens_list_operator_to_first_name():
    comp = {"skeleton": "base_plus_correction",
            "operators": {"base": "slow_ewma", "correction": ["almgren_impact", "roll_bounce"],
                          "combination": "additive_blend"},
            "params": {"alpha": 0.05}}
    out = _sanitize_composition(comp)
    assert out["operators"]["correction"] == "almgren_impact"   # first op-name kept
    assert out["operators"]["base"] == "slow_ewma"
    assert out["operators"]["combination"] == "additive_blend"
    assert out["params"] == {"alpha": 0.05}                     # params untouched


def test_drops_non_string_non_list_values():
    comp = {"operators": {"base": "slow_ewma", "correction": 123, "x": None, "y": {"nested": 1}}}
    out = _sanitize_composition(comp)
    assert out["operators"] == {"base": "slow_ewma"}            # 123/None/dict dropped


def test_empty_list_dropped():
    comp = {"operators": {"base": "slow_ewma", "correction": []}}
    out = _sanitize_composition(comp)
    assert out["operators"] == {"base": "slow_ewma"}


def test_clean_composition_unchanged():
    comp = {"skeleton": "simple", "operators": {"base": "slow_ewma"}, "params": {"alpha": 0.05}}
    assert _sanitize_composition(comp)["operators"] == {"base": "slow_ewma"}


def test_noop_on_non_dict_payload():
    assert _sanitize_composition("def estimate_fair(ctx):\n    return None\n") == "def estimate_fair(ctx):\n    return None\n"


def test_concept_lookup_safe_after_sanitize():
    # the exact crash: CONCEPT_TAXONOMY.get(op_value) with a list op_value
    from scripts.era_scalp.atomic_concepts import CONCEPT_TAXONOMY
    comp = {"operators": {"correction": ["almgren_impact", "roll_bounce"]}}
    ops = _sanitize_composition(comp)["operators"]
    # must be hashable / lookupable now
    assert CONCEPT_TAXONOMY.get(ops["correction"], ("", ""))[0] == "microstructure"
