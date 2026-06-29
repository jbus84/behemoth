"""Four-channel flagging from BoostLSS predicted distribution parameters."""
from __future__ import annotations

import numpy as np

_MU_MAD_MULTIPLIER = 1.5  # |pred_mu| > 1.5 × unconditional MAD(y)
_SIGMA_PERCENTILE = 20.0  # pred_sigma below 20th pctile of OOS sigma
_NU_STUDENT_T_THRESHOLD = 5.0  # pred_nu < 5 for Student-T → fat-tail flag
_NU_GEV_THRESHOLD = 0.2  # |pred_nu| > 0.2 for GEV → tail-asymmetry flag


def flag_channels(
    preds: dict[str, np.ndarray],
    y: np.ndarray,
    family: str,
) -> dict[str, np.ndarray]:
    """Convert predicted parameters to binary flags and magnitudes.

    Args:
        preds: output of BoostLssWFO.fit_predict() — {"mu", "sigma"} and optionally "nu"
        y: full target array (used to compute unconditional MAD threshold)
        family: "GaussianLSS", "StudentTLSS", or "GEVLSS"

    Returns:
        dict with keys: mu_flag, mu_mag, sigma_flag, sigma_mag,
                        nu_flag, nu_mag, direction
        All arrays are same length as preds arrays.
        NaN where preds are NaN (train rows).
        nu_flag/nu_mag are all NaN when family has no nu parameter (e.g. GaussianLSS).
    """
    mu = preds["mu"]
    sigma = preds["sigma"]
    nu = preds.get("nu")
    n = len(mu)

    # Unconditional MAD of y (on non-NaN y values)
    y_valid = y[~np.isnan(y)]
    uncond_mad = 1.4826 * float(np.median(np.abs(y_valid - np.median(y_valid))))
    mu_threshold = _MU_MAD_MULTIPLIER * max(uncond_mad, 1e-9)

    # OOS sigma 20th percentile (only where sigma is not NaN)
    oos_sigma = sigma[~np.isnan(sigma)]
    sigma_threshold = float(np.percentile(oos_sigma, _SIGMA_PERCENTILE)) if len(oos_sigma) > 0 else 0.0

    # Initialise output arrays with NaN
    mu_flag = np.full(n, np.nan)
    mu_mag = np.full(n, np.nan)
    sigma_flag = np.full(n, np.nan)
    sigma_mag = np.full(n, np.nan)
    nu_flag = np.full(n, np.nan)
    nu_mag = np.full(n, np.nan)
    direction = np.full(n, np.nan)

    oos_mask = ~np.isnan(mu)

    if uncond_mad < 1e-12:
        # y has no variation; mu threshold is undefined — treat all mu flags as 0
        mu_flag[oos_mask] = 0.0
    else:
        mu_flag[oos_mask] = (np.abs(mu[oos_mask]) > mu_threshold).astype(float)
    mu_mag[oos_mask] = np.abs(mu[oos_mask])

    sigma_flag[oos_mask] = (sigma[oos_mask] < sigma_threshold).astype(float)
    sigma_mag[oos_mask] = sigma[oos_mask]

    if nu is not None:
        if family == "StudentTLSS":
            nu_flag[oos_mask] = (nu[oos_mask] < _NU_STUDENT_T_THRESHOLD).astype(float)
        else:  # GEVLSS or other families with nu
            nu_flag[oos_mask] = (np.abs(nu[oos_mask]) > _NU_GEV_THRESHOLD).astype(float)
        nu_mag[oos_mask] = nu[oos_mask]
    # else: nu_flag and nu_mag remain all NaN (GaussianLSS has no nu parameter)

    direction[oos_mask] = np.sign(mu[oos_mask])

    return {
        "mu_flag": mu_flag,
        "mu_mag": mu_mag,
        "sigma_flag": sigma_flag,
        "sigma_mag": sigma_mag,
        "nu_flag": nu_flag,
        "nu_mag": nu_mag,
        "direction": direction,
    }
