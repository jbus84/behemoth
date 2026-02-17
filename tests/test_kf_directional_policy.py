from __future__ import annotations

import pandas as pd

from scripts.meta_kf_directional_wfo import _apply_policy


def test_policy_overrides_only_when_conf_and_ev_pass() -> None:
    df = pd.DataFrame(
        {
            "one_bar_move_bps": [10.0, -8.0, 5.0],
            "one_bar_pnl_base": [-10.0, -8.0, 5.0],
            "one_bar_exit_ts": [1, 2, 3],
            "timestamp": [1, 2, 3],
        }
    )

    out = _apply_policy(
        df,
        p_up=[0.90, 0.10, 0.51],
        p_dn=[0.05, 0.85, 0.49],
        pt=5.0,
        sl=5.0,
        p_min=0.55,
        ev_min=0.10,
        target_mode="one_bar",
        policy_mode="directional",
        p_move_min=0.85,
        both_balance_tol=0.08,
        both_capture_mult=1.0,
    )

    # Row 0: strong up override.
    assert bool(out.loc[0, "override_used"]) is True
    assert float(out.loc[0, "policy_pnl_bps"]) == 10.0

    # Row 1: strong down override (down move is profitable for short).
    assert bool(out.loc[1, "override_used"]) is True
    assert float(out.loc[1, "policy_pnl_bps"]) == 8.0

    # Row 2: confidence below p_min, keep baseline.
    assert bool(out.loc[2, "override_used"]) is False
    assert float(out.loc[2, "policy_pnl_bps"]) == 5.0


def test_policy_z_cross_skips_when_bad_confident() -> None:
    df = pd.DataFrame(
        {
            "pnl_bps": [8.0, -6.0, 3.0],
            "timestamp": [1, 2, 3],
            "exit_ts": [10, 20, 30],
        }
    )
    out = _apply_policy(
        df,
        p_up=[0.20, 0.10, 0.51],
        p_dn=[0.10, 0.90, 0.20],
        pt=5.0,
        sl=5.0,
        p_min=0.55,
        ev_min=0.10,
        target_mode="z_cross",
        policy_mode="directional",
        p_move_min=0.85,
        both_balance_tol=0.08,
        both_capture_mult=1.0,
    )
    assert out.loc[1, "policy_action"] == "skip"
    assert bool(out.loc[1, "drop_trade"]) is True
    assert pd.isna(out.loc[1, "policy_pnl_bps"])
    assert out.loc[0, "policy_action"] == "keep_baseline"


def test_policy_both_sides_oco_uses_abs_move_when_balanced_high_conf() -> None:
    df = pd.DataFrame(
        {
            "one_bar_move_bps": [-12.0, 9.0],
            "one_bar_pnl_base": [-12.0, 9.0],
            "one_bar_exit_ts": [1, 2],
            "timestamp": [1, 2],
        }
    )
    out = _apply_policy(
        df,
        p_up=[0.46, 0.80],
        p_dn=[0.45, 0.10],
        pt=5.0,
        sl=5.0,
        p_min=0.60,
        ev_min=0.10,
        target_mode="one_bar",
        policy_mode="both_sides",
        p_move_min=0.85,
        both_balance_tol=0.03,
        both_capture_mult=1.0,
    )
    assert out.loc[0, "policy_action"] == "both_oco"
    assert float(out.loc[0, "policy_pnl_bps"]) == 12.0
    assert bool(out.loc[0, "override_used"]) is True
    # Strong directional row still takes directional override.
    assert out.loc[1, "policy_action"] == "override"


def test_policy_both_sides_rejected_for_z_cross() -> None:
    df = pd.DataFrame({"pnl_bps": [1.0], "timestamp": [1], "exit_ts": [2]})
    try:
        _apply_policy(
            df,
            p_up=[0.5],
            p_dn=[0.4],
            pt=5.0,
            sl=5.0,
            p_min=0.55,
            ev_min=0.10,
            target_mode="z_cross",
            policy_mode="both_sides",
            p_move_min=0.85,
            both_balance_tol=0.08,
            both_capture_mult=1.0,
        )
    except ValueError as exc:
        assert "policy_mode=both_sides" in str(exc)
    else:
        raise AssertionError("Expected ValueError for z_cross + both_sides")
