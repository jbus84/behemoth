from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts.cross_symbol import CROSS_SYMBOLS, _USD_SIGN


def test_cross_symbols_roster_is_the_six_majors():
    assert CROSS_SYMBOLS == [
        "EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCAD", "USDCHF",
    ]


def test_usd_sign_table_orients_to_usd_strength():
    # USD as quote currency -> a price rise means USD weakness -> sign -1.
    assert _USD_SIGN["EURUSD"] == -1
    assert _USD_SIGN["GBPUSD"] == -1
    assert _USD_SIGN["AUDUSD"] == -1
    # USD as base currency -> a price rise means USD strength -> sign +1.
    assert _USD_SIGN["USDJPY"] == 1
    assert _USD_SIGN["USDCAD"] == 1
    assert _USD_SIGN["USDCHF"] == 1
    # Every roster symbol has a sign.
    assert set(_USD_SIGN) == set(CROSS_SYMBOLS)
