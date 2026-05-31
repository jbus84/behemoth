from __future__ import annotations

import pandas as pd


def monthly_net(net_frame: pd.DataFrame) -> pd.DataFrame:
    """Per-month mean net + trade count from a strategy's (net, test_month) trade frame.

    Monthly aggregation de-correlates the within-month overlap of h-bar holds, giving
    near-independent observations for the hierarchical model.
    """
    if len(net_frame) == 0:
        return pd.DataFrame({"test_month": [], "mean_net": [], "n": []})
    g = net_frame.groupby("test_month")["net"]
    return pd.DataFrame({"mean_net": g.mean(), "n": g.size()}).reset_index()
