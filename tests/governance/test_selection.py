import pandas as pd

from src.behemoth.governance.families import get_family_adapter
from src.behemoth.governance.selection import (
    apply_capacity_gate,
    apply_family_selection_gate,
    apply_stability_gate,
    select_states_rolling,
)


def test_apply_capacity_gate_passes_state_meeting_floors():
    states = pd.DataFrame(
        [
            {
                "state_id": "s1",
                "avg_monthly_signals": 250.0,
                "annualized_signals": 600.0,
            },
        ]
    )

    out = apply_capacity_gate(
        states=states,
        capacity_floor_monthly=200,
        capacity_floor_annual=500,
    )

    assert out["capacity_pass"].tolist() == [True]


def test_apply_capacity_gate_fails_state_below_monthly_floor():
    states = pd.DataFrame(
        [
            {
                "state_id": "s1",
                "avg_monthly_signals": 150.0,
                "annualized_signals": 600.0,
            },
        ]
    )

    out = apply_capacity_gate(
        states=states,
        capacity_floor_monthly=200,
        capacity_floor_annual=500,
    )

    assert out["capacity_pass"].tolist() == [False]


def test_apply_capacity_gate_fails_state_below_annual_floor():
    states = pd.DataFrame(
        [
            {
                "state_id": "s1",
                "avg_monthly_signals": 250.0,
                "annualized_signals": 400.0,
            },
        ]
    )

    out = apply_capacity_gate(
        states=states,
        capacity_floor_monthly=200,
        capacity_floor_annual=500,
    )

    assert out["capacity_pass"].tolist() == [False]


def test_apply_stability_gate_passes_stable_state():
    state_monthly = pd.DataFrame(
        [
            {"state_id": "s1", "month": "2026-01", "share_of_signals": 0.30},
            {"state_id": "s1", "month": "2026-02", "share_of_signals": 0.32},
            {"state_id": "s1", "month": "2026-03", "share_of_signals": 0.28},
        ]
    )

    out = apply_stability_gate(
        state_monthly=state_monthly,
        max_state_churn=0.45,
        max_top_state_share=0.35,
        max_state_hhi=0.25,
    )

    assert out.loc[out["state_id"] == "s1", "stability_pass"].iloc[0] is True


def test_apply_stability_gate_fails_state_too_concentrated():
    state_monthly = pd.DataFrame(
        [
            {"state_id": "s1", "month": "2026-01", "share_of_signals": 0.50},
            {"state_id": "s1", "month": "2026-02", "share_of_signals": 0.52},
            {"state_id": "s1", "month": "2026-03", "share_of_signals": 0.48},
        ]
    )

    out = apply_stability_gate(
        state_monthly=state_monthly,
        max_state_churn=0.45,
        max_top_state_share=0.35,
        max_state_hhi=0.25,
    )

    assert out.loc[out["state_id"] == "s1", "stability_pass"].iloc[0] is False


def test_apply_family_selection_gate_uses_adapter_hook():
    candidates = pd.DataFrame(
        [
            {"both_window_rate": 0.7, "p_up_first": 0.5},
            {"both_window_rate": 0.3, "p_up_first": 0.5},
        ]
    )

    out = apply_family_selection_gate(
        candidates=candidates,
        adapter=get_family_adapter("oco_first_touch"),
        thresholds={"min_both_window_rate": 0.5, "min_p_up_first": 0.4},
    )

    assert out["selection_gate_pass"].tolist() == [True, False]


def test_select_states_rolling_emits_one_row_per_state_month():
    state_monthly = pd.DataFrame(
        [
            {
                "state_id": "s1",
                "month": "2026-01",
                "monthly_signals": 250,
                "share_of_signals": 0.30,
                "mean_gross_pips": 0.5,
                "both_window_rate": 0.7,
                "p_up_first": 0.5,
            },
            {
                "state_id": "s1",
                "month": "2026-02",
                "monthly_signals": 240,
                "share_of_signals": 0.32,
                "mean_gross_pips": 0.4,
                "both_window_rate": 0.7,
                "p_up_first": 0.5,
            },
            {
                "state_id": "s1",
                "month": "2026-03",
                "monthly_signals": 260,
                "share_of_signals": 0.29,
                "mean_gross_pips": 0.6,
                "both_window_rate": 0.7,
                "p_up_first": 0.5,
            },
            {
                "state_id": "s2",
                "month": "2026-01",
                "monthly_signals": 100,
                "share_of_signals": 0.20,
                "mean_gross_pips": 0.3,
                "both_window_rate": 0.6,
                "p_up_first": 0.45,
            },
            {
                "state_id": "s2",
                "month": "2026-02",
                "monthly_signals": 90,
                "share_of_signals": 0.22,
                "mean_gross_pips": 0.25,
                "both_window_rate": 0.6,
                "p_up_first": 0.45,
            },
            {
                "state_id": "s2",
                "month": "2026-03",
                "monthly_signals": 105,
                "share_of_signals": 0.21,
                "mean_gross_pips": 0.35,
                "both_window_rate": 0.6,
                "p_up_first": 0.45,
            },
        ]
    )

    schedule = select_states_rolling(
        state_monthly=state_monthly,
        adapter=get_family_adapter("oco_first_touch"),
        thresholds={
            "capacity_floor_monthly": 200,
            "capacity_floor_annual": 500,
            "max_state_churn": 0.45,
            "max_top_state_share": 0.35,
            "max_state_hhi": 0.25,
            "state_train_months": 2,
            "min_states": 1,
            "max_states": 12,
            "selection_gates": {
                "min_both_window_rate": 0.5,
                "min_p_up_first": 0.4,
            },
        },
    )

    selected_2026_03 = schedule[
        (schedule["month"] == "2026-03") & (schedule["selected"])
    ]["state_id"].tolist()

    assert selected_2026_03 == ["s1"]


def test_select_states_rolling_emits_current_month_state_absent_from_train_window():
    state_monthly = pd.DataFrame(
        [
            {
                "state_id": "s1",
                "month": "2026-01",
                "monthly_signals": 250,
                "share_of_signals": 0.30,
                "mean_gross_pips": 0.5,
                "both_window_rate": 0.7,
                "p_up_first": 0.5,
            },
            {
                "state_id": "s1",
                "month": "2026-02",
                "monthly_signals": 240,
                "share_of_signals": 0.32,
                "mean_gross_pips": 0.4,
                "both_window_rate": 0.7,
                "p_up_first": 0.5,
            },
            {
                "state_id": "s3",
                "month": "2026-03",
                "monthly_signals": 260,
                "share_of_signals": 0.29,
                "mean_gross_pips": 0.6,
                "both_window_rate": 0.7,
                "p_up_first": 0.5,
            },
        ]
    )

    schedule = select_states_rolling(
        state_monthly=state_monthly,
        adapter=get_family_adapter("oco_first_touch"),
        thresholds={
            "capacity_floor_monthly": 200,
            "capacity_floor_annual": 500,
            "max_state_churn": 0.45,
            "max_top_state_share": 0.35,
            "max_state_hhi": 0.25,
            "state_train_months": 2,
            "min_states": 1,
            "max_states": 12,
            "selection_gates": {
                "min_both_window_rate": 0.5,
                "min_p_up_first": 0.4,
            },
        },
    )

    current_only = schedule[
        (schedule["month"] == "2026-03") & (schedule["state_id"] == "s3")
    ].iloc[0]
    assert current_only["selected"] is False
    assert current_only["capacity_pass"] is False
