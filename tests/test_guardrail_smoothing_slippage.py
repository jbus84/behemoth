import os
import sys

import pandas as pd

sys.path.append(os.path.join(os.getcwd(), "scripts"))
import analyze_guardrail_smoothing_slippage as gs


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
