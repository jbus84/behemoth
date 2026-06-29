"""Four-channel flagging from BoostLSS predicted distribution parameters."""
from __future__ import annotations

import numpy as np

_MU_MAD_MULTIPLIER = 1.5  # |pred_mu| > 1.5 × unconditional MAD(y)
_SIGMA_PERCENTILE = 20.0  # pred_sigma below 20th pctile of OOS sigma
_NU_GEV_THRESHOLD = 0.2  # |pred_nu| > 0.2 for GEV → tail-asymmetry flag


def flag_channels(
    preds: dict[str, np.ndarray],
    y: np.ndarray,
    family: str,
    mu_threshold: float | np.ndarray | None = None,
    sigma_threshold: float | np.ndarray | None = None,
) -> dict[str, np.ndarray]:
    """Convert predicted parameters to binary flags and magnitudes.

    Args:
        preds: output of BoostLssWFO.fit_predict() — {"mu", "sigma"} and optionally "nu"
        y: full target array (used to compute unconditional MAD threshold)
        family: "GaussianLSS" or "GEVLSS"
        mu_threshold: scalar, per-row array, or None (falls back to full-sample 1.5×MAD(y))
        sigma_threshold: scalar, per-row array, or None (falls back to full-OOS 20th pctile)

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

    oos_mask = ~np.isnan(mu)

    # --- mu threshold ---
    if isinstance(mu_threshold, np.ndarray):
        # Per-row array: use element-wise
        _mu_thresh_arr = mu_threshold
    else:
        # Scalar or None: compute full-sample fallback
        if mu_threshold is None:
            y_valid = y[~np.isnan(y)]
            uncond_mad = 1.4826 * float(np.median(np.abs(y_valid - np.median(y_valid))))
            scalar_mu = _MU_MAD_MULTIPLIER * max(uncond_mad, 1e-9)
        else:
            scalar_mu = float(mu_threshold)
        _mu_thresh_arr = np.full(n, scalar_mu)

    # --- sigma threshold ---
    if isinstance(sigma_threshold, np.ndarray):
        _sigma_thresh_arr = sigma_threshold
    else:
        if sigma_threshold is None:
            oos_sigma = sigma[~np.isnan(sigma)]
            scalar_sigma = (
                float(np.percentile(oos_sigma, _SIGMA_PERCENTILE))
                if len(oos_sigma) > 0
                else 0.0
            )
        else:
            scalar_sigma = float(sigma_threshold)
        _sigma_thresh_arr = np.full(n, scalar_sigma)

    # Initialise output arrays with NaN
    mu_flag = np.full(n, np.nan)
    mu_mag = np.full(n, np.nan)
    sigma_flag = np.full(n, np.nan)
    sigma_mag = np.full(n, np.nan)
    nu_flag = np.full(n, np.nan)
    nu_mag = np.full(n, np.nan)
    direction = np.full(n, np.nan)

    # mu: threshold guard only applies when threshold was derived from y (not caller-supplied)
    caller_supplied_mu = isinstance(mu_threshold, (np.ndarray, float, int)) and mu_threshold is not None
    if not caller_supplied_mu:
        y_valid_all = y[~np.isnan(y)]
        uncond_mad_check = (
            1.4826 * float(np.median(np.abs(y_valid_all - np.median(y_valid_all))))
            if len(y_valid_all) > 0
            else 0.0
        )
        if uncond_mad_check < 1e-12:
            mu_flag[oos_mask] = 0.0
        else:
            effective_thresh = _mu_thresh_arr[oos_mask]
            effective_thresh = np.where(effective_thresh < 1e-9, 1e-9, effective_thresh)
            mu_flag[oos_mask] = (np.abs(mu[oos_mask]) > effective_thresh).astype(float)
    else:
        effective_thresh = _mu_thresh_arr[oos_mask]
        effective_thresh = np.where(effective_thresh < 1e-9, 1e-9, effective_thresh)
        mu_flag[oos_mask] = (np.abs(mu[oos_mask]) > effective_thresh).astype(float)

    mu_mag[oos_mask] = np.abs(mu[oos_mask]) / np.where(
        _mu_thresh_arr[oos_mask] < 1e-9, 1e-9, _mu_thresh_arr[oos_mask]
    )

    sigma_flag[oos_mask] = (sigma[oos_mask] < _sigma_thresh_arr[oos_mask]).astype(float)
    sigma_mag[oos_mask] = sigma[oos_mask]

    if nu is not None:
        # GEVLSS: |nu| > threshold signals asymmetric tail
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
