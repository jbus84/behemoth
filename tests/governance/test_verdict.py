import pandas as pd

from src.behemoth.governance.verdict import (
    compute_family_verdict,
    compute_state_verdicts,
    compute_symbol_verdict,
)


def test_state_verdict_GO_when_selected_and_tick_exact_positive():
    selection = pd.DataFrame(
        [
            {"state_id": "s1", "selected": True},
            {"state_id": "s2", "selected": False},
        ]
    )
    tick_exact = pd.DataFrame(
        [
            {"state_id": "s1", "mean_realized_pips": 0.5},
            {"state_id": "s2", "mean_realized_pips": 0.3},
        ]
    )

    verdicts = compute_state_verdicts(
        selection=selection,
        tick_exact=tick_exact,
        min_realized_pips_pass=0.0,
    )

    assert verdicts.loc[verdicts["state_id"] == "s1", "verdict"].iloc[0] == "GO"
    assert verdicts.loc[verdicts["state_id"] == "s2", "verdict"].iloc[0] == "NO_GO"


def test_state_verdict_NO_GO_when_selected_but_tick_exact_negative():
    selection = pd.DataFrame([{"state_id": "s1", "selected": True}])
    tick_exact = pd.DataFrame([{"state_id": "s1", "mean_realized_pips": -0.2}])

    verdicts = compute_state_verdicts(
        selection=selection,
        tick_exact=tick_exact,
        min_realized_pips_pass=0.0,
    )

    assert verdicts["verdict"].iloc[0] == "NO_GO"


def test_family_verdict_GO_if_any_state_GO():
    state_verdicts = pd.DataFrame(
        [
            {"state_id": "s1", "verdict": "NO_GO"},
            {"state_id": "s2", "verdict": "GO"},
        ]
    )

    assert compute_family_verdict(state_verdicts=state_verdicts) == "GO"


def test_family_verdict_NO_GO_if_all_states_NO_GO():
    state_verdicts = pd.DataFrame(
        [
            {"state_id": "s1", "verdict": "NO_GO"},
            {"state_id": "s2", "verdict": "NO_GO"},
        ]
    )

    assert compute_family_verdict(state_verdicts=state_verdicts) == "NO_GO"


def test_symbol_verdict_GO_when_all_required_families_GO():
    family_verdicts = {
        "oco_first_touch": "GO",
        "directional_run": "GO",
        "lead_lag": "NO_GO",
    }

    v = compute_symbol_verdict(
        family_verdicts=family_verdicts,
        required_families=("oco_first_touch", "directional_run"),
    )

    assert v == "GO"


def test_symbol_verdict_NO_GO_when_any_required_family_NO_GO():
    family_verdicts = {"oco_first_touch": "GO", "directional_run": "NO_GO"}

    v = compute_symbol_verdict(
        family_verdicts=family_verdicts,
        required_families=("oco_first_touch", "directional_run"),
    )

    assert v == "NO_GO"


def test_symbol_verdict_NO_GO_when_required_family_missing():
    family_verdicts = {"oco_first_touch": "GO"}

    v = compute_symbol_verdict(
        family_verdicts=family_verdicts,
        required_families=("oco_first_touch", "directional_run"),
    )

    assert v == "NO_GO"
