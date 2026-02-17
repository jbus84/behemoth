from __future__ import annotations

import pandas as pd

from scripts.lib.cluster_features import add_cluster_state_features
from scripts.lib.cluster_labels import build_cluster_day_labels, build_cluster_trade_labels


def test_build_cluster_trade_labels_horizon() -> None:
    ts0 = pd.Timestamp("2024-01-01 00:00:00", tz="UTC")
    rows = []
    pnls = [100.0, -200.0, -100.0, -50.0, 200.0]
    for i, pnl in enumerate(pnls):
        t = ts0 + pd.Timedelta(hours=i)
        rows.append(
            {
                "pair": "EUR/GBP",
                "timeframe": "m5",
                "strategy_type": "MOM",
                "timestamp": int(t.value),
                "exit_ts": int((t + pd.Timedelta(minutes=20)).value),
                "pnl_bps": pnl,
            }
        )
    df = pd.DataFrame(rows)

    y = build_cluster_trade_labels(df, horizon_trades=2, loss_bps=-250.0)

    assert y.iloc[0] == 1  # next two: -200 + -100 = -300
    assert y.iloc[1] == 0  # next two: -100 + -50 = -150
    assert y.iloc[2] == 0  # next two: -50 + 200 = 150
    assert pd.isna(y.iloc[3])
    assert pd.isna(y.iloc[4])


def test_build_cluster_day_labels_horizon() -> None:
    rows = []
    day0 = pd.Timestamp("2024-01-01 00:00:00", tz="UTC")
    vals = [-500.0, 100.0, 50.0]
    for i, pnl in enumerate(vals):
        t = day0 + pd.Timedelta(days=i)
        rows.append(
            {
                "pair": "EUR/GBP",
                "timeframe": "m15",
                "strategy_type": "REV",
                "timestamp": int(t.value),
                "exit_ts": int((t + pd.Timedelta(hours=2)).value),
                "pnl_bps": pnl,
            }
        )
    df = pd.DataFrame(rows)

    y = build_cluster_day_labels(df, horizon_days=2, loss_bps=-400.0)

    assert y.iloc[0] == 1  # window day0/day1 includes -500
    assert y.iloc[1] == 0  # window day1/day2 min is 50
    assert pd.isna(y.iloc[2])


def test_cluster_features_use_realized_only() -> None:
    t0 = pd.Timestamp("2024-01-01 00:00:00", tz="UTC")
    df = pd.DataFrame(
        [
            {
                "pair": "EUR/GBP",
                "timeframe": "m5",
                "strategy_type": "MOM",
                "timestamp": int((t0 + pd.Timedelta(hours=0)).value),
                "exit_ts": int((t0 + pd.Timedelta(hours=2)).value),
                "pnl_bps": -100.0,
            },
            {
                "pair": "EUR/GBP",
                "timeframe": "m5",
                "strategy_type": "MOM",
                "timestamp": int((t0 + pd.Timedelta(hours=1)).value),
                "exit_ts": int((t0 + pd.Timedelta(hours=1, minutes=30)).value),
                "pnl_bps": 50.0,
            },
            {
                "pair": "EUR/GBP",
                "timeframe": "m5",
                "strategy_type": "MOM",
                "timestamp": int((t0 + pd.Timedelta(hours=3)).value),
                "exit_ts": int((t0 + pd.Timedelta(hours=4)).value),
                "pnl_bps": -20.0,
            },
        ]
    )

    out = add_cluster_state_features(df)

    # First trade has no realized history.
    assert float(out.iloc[0]["realized_pnl_sum_5"]) == 0.0
    assert float(out.iloc[0]["realized_loss_streak_3"]) == 0.0

    # Second trade (entry at +1h) must not see first trade outcome (first exits at +2h).
    assert float(out.iloc[1]["realized_pnl_sum_5"]) == 0.0
    assert float(out.iloc[1]["realized_loss_streak_3"]) == 0.0

    # Third trade (entry at +3h) sees realized outcomes from first two trades.
    assert float(out.iloc[2]["realized_pnl_sum_5"]) == -50.0
    assert float(out.iloc[2]["realized_loss_streak_3"]) >= 1.0
