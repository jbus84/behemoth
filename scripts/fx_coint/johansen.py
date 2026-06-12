from __future__ import annotations

import numpy as np
import pandas as pd
from statsmodels.tsa.vector_ar.vecm import coint_johansen

from scripts.fx_coint.instruments import MAJORS, ccy_weight

# Non-USD currencies whose log-USD values form the Johansen system.
_CCYS = ["EUR", "GBP", "JPY", "CHF", "CAD", "AUD"]


def _logusd_matrix(panel: pd.DataFrame) -> np.ndarray:
    """Map the major logmids to a (T, 6) matrix of currency log-USD values."""
    logmids = {m: panel[(m, "logmid")].to_numpy() for m in MAJORS}
    cols = []
    for c in _CCYS:
        w = ccy_weight(c)
        cols.append(sum(w[i] * logmids[MAJORS[i]] for i in range(len(MAJORS))))
    return np.column_stack(cols)


def johansen_rank(panel: pd.DataFrame, det_order: int = 0, k_ar_diff: int = 1) -> int:
    """Number of cointegrating relations at the 95% trace-stat critical value."""
    mat = _logusd_matrix(panel)
    res = coint_johansen(mat, det_order, k_ar_diff)
    trace = res.lr1
    crit_95 = res.cvt[:, 1]
    return int((trace > crit_95).sum())


def leading_vector_major_weights(panel: pd.DataFrame, det_order: int = 0,
                                 k_ar_diff: int = 1) -> np.ndarray:
    """Leading cointegrating eigenvector, mapped from currency space to a
    (6,) weight vector over MAJORS (so it shares the cost/residual machinery)."""
    mat = _logusd_matrix(panel)
    res = coint_johansen(mat, det_order, k_ar_diff)
    ccy_vec = res.evec[:, 0]  # weights over _CCYS
    major_w = np.zeros(len(MAJORS))
    for c, wc in zip(_CCYS, ccy_vec):
        major_w += wc * ccy_weight(c)
    return major_w
