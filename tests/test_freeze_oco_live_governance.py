"""Tests for freeze_oco_live_governance module."""


import pandas as pd


def test_manifest_deploy_verdict_no_go_for_empty_universe(tmp_path, monkeypatch):
    """An empty reduced-states CSV yields a manifest whose deploy_verdict is
    the canonical NO_GO, with an empty state_universe."""
    from scripts.freeze_oco_live_governance import _state_universe

    empty_states = tmp_path / "EURUSD_oco_reduced_states.csv"
    pd.DataFrame(
        columns=["symbol", "bar_ticks", "horizon", "state_id",
                 "family", "barrier_pips", "regime_desc"]
    ).to_csv(empty_states, index=False)

    states, _sha = _state_universe(empty_states)
    assert states.empty
    # deploy_verdict is derived purely from the universe count:
    from scripts.freeze_oco_live_governance import _deploy_verdict
    assert _deploy_verdict(0) == "NO_GO"
    assert _deploy_verdict(5) == "GO"
