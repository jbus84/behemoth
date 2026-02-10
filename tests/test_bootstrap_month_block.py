import os
import sys

import pandas as pd

sys.path.append(os.path.join(os.getcwd(), "scripts"))
import analyze_bootstrap_month_block as bb


def _make_df():
    ts = pd.to_datetime(
        ["2020-01-01", "2020-01-05", "2020-02-01", "2020-02-05", "2020-03-01"],
        utc=True,
    ).view("int64")
    return pd.DataFrame(
        {
            "pair": ["A"] * len(ts),
            "exit_ts": ts,
            "pnl_bps": [1, -1, 2, -2, 1],
            "year_month": [202001, 202001, 202002, 202002, 202003],
        }
    )


def test_month_blocks():
    df = _make_df()
    blocks = bb._month_blocks(df)
    assert len(blocks) == 3


def test_trade_blocks():
    df = _make_df()
    blocks = bb._trade_blocks(df, block_size=2)
    assert len(blocks) == 3


def test_bootstrap_blocks_length():
    df = _make_df()
    blocks = bb._trade_blocks(df, block_size=2)
    sample = bb._bootstrap_blocks(blocks)
    assert len(sample) == len(df)


def test_metrics_and_guardrail():
    df = _make_df()
    # add pnl/exit_ts required by metrics
    df["pnl_bps"] = [1, -1, 2, -2, 1]
    m = bb._metrics(df)
    assert m["trades"] == 5
    guard = bb._apply_guardrail(df)
    assert len(guard) <= len(df)


def test_bootstrap_summary():
    df = _make_df()
    df["pnl_bps"] = [1, -1, 2, -2, 1]
    samples = [df.copy(), df.copy()]
    summary = bb._bootstrap_summary(samples)
    assert "mean_pnl_p50" in summary.columns
