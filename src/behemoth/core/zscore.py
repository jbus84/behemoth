import numpy as np
import pandas as pd


def compute_z_scores(errors, window=750):
    """
    Compute Z-scores using rolling mean/std of PREVIOUS 'window' errors (excluding current).
    Vectorized O(N) implementation.
    """
    if len(errors) < window + 1:
        return np.zeros(len(errors))

    series = pd.Series(errors)
    # Compute rolling stats for the window, then shift by 1 so that
    # stats at index i depend only on i-window ... i-1
    stats = series.rolling(window=window).agg(["mean", "std"]).shift(1)

    mu = stats["mean"].to_numpy()
    std = stats["std"].to_numpy()
    z_scores = np.zeros(len(errors))

    # Mask valid indices where we have stats
    valid = ~np.isnan(mu) & (std > 1e-6)
    
    if np.any(valid):
        z_scores[valid] = (errors[valid] - mu[valid]) / std[valid]

    return z_scores
