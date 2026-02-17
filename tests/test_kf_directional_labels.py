from __future__ import annotations

import pandas as pd

from scripts.meta_kf_directional_wfo import _compute_barriers, _label_one_bar


def test_one_bar_barriers_and_labels() -> None:
    df = pd.DataFrame({"one_bar_move_bps": [6.0, -7.0, 0.0, 3.0, -2.0]})

    pt, sl = _compute_barriers(df, pt_q=0.50, sl_q=0.50)
    y = _label_one_bar(df, pt=pt, sl=sl)

    assert pt == 4.5
    assert sl == 4.5
    assert y.tolist() == [1, -1, 0, 0, 0]
