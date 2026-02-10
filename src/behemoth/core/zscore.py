import numpy as np


def compute_z_scores(errors, window=500):
    z_scores = np.zeros(len(errors))
    for i in range(window, len(errors)):
        window_data = errors[i - window : i]
        mu, std = np.mean(window_data), np.std(window_data)
        if std > 1e-6:
            z_scores[i] = (errors[i] - mu) / std
    return z_scores
