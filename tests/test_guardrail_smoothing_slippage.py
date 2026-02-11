import analyze_guardrail_smoothing_slippage as gs
import pandas as pd


def test_smoothing_skiprate(tmp_path, monkeypatch):
    # Build a fake smoothing impact CSV
    data = pd.DataFrame(
        {
            "pair": ["A", "A"],
            "config": ["cfg", "cfg"],
            "guardrail": ["noguard", "guard"],
            "base_trades": [100, 60],
        }
    )
    out_dir = tmp_path
    data.to_csv(out_dir / "m5_smoothing_strategy_impact.csv", index=False)

    monkeypatch.setattr(gs, "OUT_DIR", str(out_dir))
    res = gs._smoothing_skiprate("m5")
    assert not res.empty
    skip = float(res["skip_rate"].iloc[0])
    assert abs(skip - 0.4) < 1e-6


def test_apply_guardrail_basic():
    df = pd.DataFrame(
        {
            "pair": ["A", "A", "A", "A"],
            "exit_ts": [1, 2, 3, 4],
            "pnl_bps": [-1.0, -1.0, -1.0, 1.0],
        }
    )
    kept = gs._apply_guardrail(df)
    assert len(kept) == 3


def test_metrics_guardrail_smoothing():
    df = pd.DataFrame(
        {
            "pair": ["A", "B"],
            "exit_ts": [1, 2],
            "pnl_bps": [1.0, -1.0],
        }
    )
    m = gs._metrics(df)
    assert m["trades"] == 2


def test_metrics_guardrail_smoothing_empty():
    df = pd.DataFrame(columns=["pair", "exit_ts", "pnl_bps"])
    m = gs._metrics(df)
    assert m["trades"] == 0


def test_max_dd_guardrail_smoothing_empty():
    assert gs._max_dd([]) == 0.0


def test_apply_guardrail_empty():
    df = pd.DataFrame(columns=["pair", "exit_ts", "pnl_bps"])
    kept = gs._apply_guardrail(df)
    assert kept.empty


def test_smoothing_skiprate_missing_columns(tmp_path, monkeypatch):
    data = pd.DataFrame(
        {
            "pair": ["A"],
            "config": ["cfg"],
            "guardrail": ["guard"],
            "base_trades": [10],
        }
    )
    out_dir = tmp_path
    data.to_csv(out_dir / "m15_smoothing_strategy_impact.csv", index=False)

    monkeypatch.setattr(gs, "OUT_DIR", str(out_dir))
    res = gs._smoothing_skiprate("m15")
    assert res.empty
