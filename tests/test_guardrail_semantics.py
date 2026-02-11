import pandas as pd

from behemoth.core.guardrail import apply_loss_streak_guardrail


def test_guardrail_counts_zero_as_loss():
    base = pd.Timestamp("2020-01-01", tz="UTC").value
    day = int(pd.Timedelta(days=1).value)

    trades = pd.DataFrame(
        [
            {"pair": "X", "exit_ts": base + 0 * day, "pnl": -1.0},
            {"pair": "X", "exit_ts": base + 1 * day, "pnl": -1.0},
            {"pair": "X", "exit_ts": base + 2 * day, "pnl": 0.0},
            {"pair": "X", "exit_ts": base + 3 * day, "pnl": -1.0},
            {"pair": "X", "exit_ts": base + 12 * day, "pnl": 1.0},
        ]
    )

    trades = trades.rename(columns={"pnl": "pnl_bps"})
    kept, skipped = apply_loss_streak_guardrail(
        trades,
        loss_threshold=0.0,
        loss_streak=3,
        cooldown_days=7,
        return_skipped=True,
    )

    # Loss streak (including pnl=0) triggers a pause after day 2,
    # so day 3 is skipped, day 12 is kept.
    assert len(kept) == 4
    assert len(skipped) == 1
    assert int(skipped.iloc[0]["exit_ts"]) == base + 3 * day
