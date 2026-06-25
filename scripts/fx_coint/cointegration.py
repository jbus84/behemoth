from __future__ import annotations

import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import adfuller

from scripts.fx_coint.instruments import MAJORS, instrument_weight


def instrument_series(panel: pd.DataFrame, symbol: str) -> pd.Series:
    """Log-price series of any instrument = weights . major logmids.

    Only legs with a nonzero weight are read, so a panel holding a subset of
    MAJORS works as long as it carries every leg the instrument needs. A
    required-but-absent leg is a hard error (no silent zero-fill).
    """
    w = instrument_weight(symbol)
    present = set(panel.columns.get_level_values(0))
    series = pd.Series(0.0, index=panel.index)
    for i, major in enumerate(MAJORS):
        if w[i] == 0.0:
            continue
        if major not in present:
            raise KeyError(f"panel missing leg {major!r} required for {symbol!r}")
        series = series + w[i] * panel[(major, "logmid")]
    return series


def fit_hedge(panel: pd.DataFrame, base: str, hedge: str) -> float:
    """OLS hedge ratio beta: base ~ beta*hedge + const. Estimated on the given slice."""
    y = instrument_series(panel, base).to_numpy()
    x = instrument_series(panel, hedge).to_numpy()
    A = np.column_stack([x, np.ones_like(x)])
    beta, _ = np.linalg.lstsq(A, y, rcond=None)[0]
    return float(beta)


def residual(panel: pd.DataFrame, base: str, hedge: str, beta: float) -> pd.Series:
    """Cointegration residual base - beta*hedge (de-meaned)."""
    s = instrument_series(panel, base) - beta * instrument_series(panel, hedge)
    return s - s.mean()


def eg_test(res: pd.Series) -> float:
    """ADF p-value on the residual (Engle-Granger step 2). Lower = more stationary."""
    return float(adfuller(res.to_numpy(), autolag="AIC")[1])


def half_life(res: pd.Series) -> float:
    """AR(1) mean-reversion half-life in bars: dr_t = a + rho*r_{t-1}; hl = -ln2/ln(1+rho)."""
    r = res.to_numpy()
    lag = r[:-1]
    dr = np.diff(r)
    A = np.column_stack([lag, np.ones_like(lag)])
    rho, _ = np.linalg.lstsq(A, dr, rcond=None)[0]
    if rho >= 0:
        return float("inf")
    return float(-np.log(2) / np.log(1 + rho))


def residual_weight(base: str, hedge: str, beta: float) -> np.ndarray:
    """Net weight vector over MAJORS for the spread base - beta*hedge (for cost)."""
    return instrument_weight(base) - beta * instrument_weight(hedge)
