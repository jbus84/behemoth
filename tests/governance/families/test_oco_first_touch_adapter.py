import pandas as pd

from src.behemoth.governance.families import get_family_adapter


def test_oco_selection_gate_passes_when_thresholds_met():
    adapter = get_family_adapter("oco_first_touch")
    row = pd.Series({"both_window_rate": 0.7, "p_up_first": 0.5})

    assert adapter.selection_gate(
        row,
        {"min_both_window_rate": 0.5, "min_p_up_first": 0.4},
    ) is True


def test_oco_selection_gate_fails_on_low_both_window_rate():
    adapter = get_family_adapter("oco_first_touch")
    row = pd.Series({"both_window_rate": 0.3, "p_up_first": 0.5})

    assert adapter.selection_gate(
        row,
        {"min_both_window_rate": 0.5, "min_p_up_first": 0.4},
    ) is False
