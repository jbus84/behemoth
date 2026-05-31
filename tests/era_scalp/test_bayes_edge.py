import numpy as np
import pandas as pd

from scripts.era_scalp.bayes_edge import monthly_net


def test_monthly_net_mean_and_count():
    df = pd.DataFrame({
        "net": [1.0, 3.0, 2.0, 2.0],
        "test_month": ["2025-01", "2025-01", "2025-02", "2025-02"],
    })
    out = monthly_net(df).sort_values("test_month").reset_index(drop=True)
    assert list(out["test_month"]) == ["2025-01", "2025-02"]
    assert np.allclose(out["mean_net"], [2.0, 2.0])
    assert list(out["n"]) == [2, 2]


def test_monthly_net_empty():
    out = monthly_net(pd.DataFrame({"net": [], "test_month": []}))
    assert len(out) == 0
    assert set(out.columns) >= {"test_month", "mean_net", "n"}
