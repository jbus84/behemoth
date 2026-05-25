from pathlib import Path

import pandas as pd
import pytest

from src.behemoth.governance.errors import CandidateSchemaError
from src.behemoth.governance.families import get_family_adapter
from src.behemoth.governance.state_assembly import assemble_states

FIXTURE = Path("tests/governance/fixtures/synthetic_candidates_oco.csv")


def test_assemble_states_groups_by_state_key_cols():
    candidates = pd.read_csv(FIXTURE)
    adapter = get_family_adapter("oco_first_touch")

    states = assemble_states(candidates=candidates, adapter=adapter)

    distinct = candidates.groupby(list(adapter.config.state_key_cols)).ngroups
    assert len(states) == distinct
    assert "state_id" in states.columns


def test_assemble_states_state_id_uses_adapter_formatting():
    candidates = pd.read_csv(FIXTURE)
    adapter = get_family_adapter("oco_first_touch")

    states = assemble_states(candidates=candidates, adapter=adapter)

    state_ids = states["state_id"].tolist()
    assert any("london" in state_id for state_id in state_ids)
    assert any("_2_3_london" in state_id for state_id in state_ids)


def test_assemble_states_aggregates_train_counts_and_weighted_train_pips():
    candidates = pd.read_csv(FIXTURE)
    adapter = get_family_adapter("oco_first_touch")

    states = assemble_states(candidates=candidates, adapter=adapter)

    mask = (
        (states["family"] == "oco_first_touch")
        & (states["barrier_pips"] == 2.0)
        & (states["horizon"] == 3)
        & (states["regime"] == "london")
    )
    row = states[mask].iloc[0]
    assert int(row["candidate_count"]) == 2
    assert int(row["train_count_sum"]) == 1550
    assert row["mean_gross_pips_train_avg"] == pytest.approx(
        ((0.20 * 800) + (0.18 * 750)) / 1550
    )


def test_assemble_states_weighted_average_is_nan_when_weights_sum_to_zero():
    candidates = pd.read_csv(FIXTURE)
    candidates.loc[
        (candidates["barrier_pips"] == 2.0)
        & (candidates["horizon"] == 3)
        & (candidates["regime"] == "london"),
        "train_count",
    ] = 0
    adapter = get_family_adapter("oco_first_touch")

    states = assemble_states(candidates=candidates, adapter=adapter)

    row = states[
        (states["barrier_pips"] == 2.0)
        & (states["horizon"] == 3)
        & (states["regime"] == "london")
    ].iloc[0]
    assert pd.isna(row["mean_gross_pips_train_avg"])


def test_assemble_states_raises_on_missing_state_key_col():
    candidates = pd.read_csv(FIXTURE).drop(columns=["regime"])
    adapter = get_family_adapter("oco_first_touch")

    with pytest.raises(CandidateSchemaError) as exc_info:
        assemble_states(candidates=candidates, adapter=adapter)

    assert "regime" in exc_info.value.missing_cols
