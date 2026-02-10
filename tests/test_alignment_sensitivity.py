import numpy as np
import analyze_alignment_sensitivity as align


def test_align_series_shift_positive():
    ts = np.array([10, 20, 30, 40])
    y = np.array([1, 2, 3, 4])
    x = np.array([5, 6, 7, 8])
    ts_s, y_s, x_s = align._align_series(ts, y, x, 1)
    assert ts_s.tolist() == [10, 20, 30]
    assert y_s.tolist() == [1, 2, 3]
    assert x_s.tolist() == [6, 7, 8]


def test_align_series_shift_negative():
    ts = np.array([10, 20, 30, 40])
    y = np.array([1, 2, 3, 4])
    x = np.array([5, 6, 7, 8])
    ts_s, y_s, x_s = align._align_series(ts, y, x, -1)
    assert ts_s.tolist() == [20, 30, 40]
    assert y_s.tolist() == [2, 3, 4]
    assert x_s.tolist() == [5, 6, 7]
