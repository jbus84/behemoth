import os
import sys

import pandas as pd
import numpy as np

sys.path.append(os.path.join(os.getcwd(), "scripts"))
import full_leak_audit as la


def test_scan_forward_index():
    hits = la._scan_forward_index(la.m5)
    assert hits == []


def test_global_bars(tmp_path):
    ts = pd.date_range("2020-01-01", periods=3, freq="D", tz="UTC")
    df = pd.DataFrame({"timestamp": ts, "close_X": [1.0, 1.1, 1.2]})
    path = tmp_path / "X.parquet"
    df.to_parquet(path, index=False)

    series = la._global_bars(str(path), "close_X")
    assert series.name == "close_X"
    assert len(series) == 3
    assert np.issubdtype(series.index.dtype, np.integer)


def test_feature_columns_and_pair_map():
    cols = la._feature_columns(pd.DataFrame())
    assert "z_entry" in cols
    pairs = la._pair_map(la.m5)
    assert isinstance(pairs, dict)
    assert len(pairs) > 0
