import analyze_symbol_stability as ss
import pandas as pd


def test_apply_guardrail_symbol_stability():
    df = pd.DataFrame(
        {
            "pair": ["A", "A", "A", "A"],
            "exit_ts": [1, 2, 3, 4],
            "pnl_bps": [-1.0, -1.0, -1.0, 2.0],
        }
    )
    kept = ss._apply_guardrail(df)
    assert len(kept) == 3


def test_metrics_symbol_stability():
    df = pd.DataFrame(
        {
            "pair": ["A", "B"],
            "exit_ts": [1, 2],
            "pnl_bps": [1.0, -1.0],
        }
    )
    m = ss._metrics(df)
    assert m["trades"] == 2


def test_metrics_symbol_stability_empty():
    df = pd.DataFrame(columns=["pair", "exit_ts", "pnl_bps"])
    m = ss._metrics(df)
    assert m["trades"] == 0


def test_max_dd_symbol_stability_empty():
    assert ss._max_dd([]) == 0.0


def test_apply_guardrail_symbol_stability_empty():
    df = pd.DataFrame(columns=["pair", "exit_ts", "pnl_bps"])
    kept = ss._apply_guardrail(df)
    assert kept.empty
