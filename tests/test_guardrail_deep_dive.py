import os
import sys

import pandas as pd

sys.path.append(os.path.join(os.getcwd(), "scripts"))
import analyze_guardrail_deep_dive as gd


def _make_df():
    # 4 trades for one pair, 1 trade for another
    return pd.DataFrame(
        {
            "pair": ["A", "A", "A", "A", "B"],
            "exit_ts": [
                1_000,
                2_000,
                3_000,
                4_000,
                1_500,
            ],
            "pnl_bps": [-1.0, -1.0, -1.0, 2.0, 1.0],
        }
    )


def test_apply_guardrail_skips_after_streak():
    df = _make_df()
    kept, skipped = gd._apply_guardrail(df, loss_threshold=0.0)
    # after 3 losses, the 4th trade should be skipped (cooldown)
    assert len(kept) == 4
    assert len(skipped) == 1


def test_annotate_streaks():
    df = _make_df()
    out = gd._annotate_streaks(df, loss_threshold=0.0)
    # first trade should have prev_loss_streak = 0
    assert out["prev_loss_streak"].iloc[0] == 0
    # trade at exit_ts=3000 for pair A should see streak of 2 before it
    row = out[(out["pair"] == "A") & (out["exit_ts"] == 3000)].iloc[0]
    assert row["prev_loss_streak"] == 2


def test_metrics_guardrail_deep():
    df = _make_df()
    m = gd._metrics(df)
    assert m["trades"] == 5


def test_session_name_unknown():
    assert gd._session_name(25) == "Unknown"


def test_max_dd_empty_guardrail_deep():
    assert gd._max_dd([]) == 0.0


def test_metrics_empty_guardrail_deep():
    empty = pd.DataFrame(columns=["pair", "exit_ts", "pnl_bps"])
    m = gd._metrics(empty)
    assert m["trades"] == 0
