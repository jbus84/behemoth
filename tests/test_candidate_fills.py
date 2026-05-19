from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.candidate_fills import candidate_id


def test_candidate_id_is_deterministic_and_12_hex():
    a = candidate_id(
        "EURUSD", "oco", "oco_first_touch", 1000, 6, "high_vol_cluster",
        {"horizon": 6, "barrier_pips": 2.0},
    )
    b = candidate_id(
        "EURUSD", "oco", "oco_first_touch", 1000, 6, "high_vol_cluster",
        {"horizon": 6, "barrier_pips": 2.0},
    )
    assert a == b
    assert len(a) == 12
    assert all(c in "0123456789abcdef" for c in a)


def test_candidate_id_differs_when_params_differ():
    a = candidate_id(
        "EURUSD", "oco", "oco_first_touch", 1000, 6, "r",
        {"horizon": 6, "barrier_pips": 2.0},
    )
    b = candidate_id(
        "EURUSD", "oco", "oco_first_touch", 1000, 6, "r",
        {"horizon": 6, "barrier_pips": 3.0},
    )
    assert a != b


def test_candidate_id_is_param_order_independent():
    a = candidate_id("EURUSD", "oco", "f", 1000, 6, "r", {"a": 1, "b": 2})
    b = candidate_id("EURUSD", "oco", "f", 1000, 6, "r", {"b": 2, "a": 1})
    assert a == b
