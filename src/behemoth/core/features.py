import numpy as np
from datetime import datetime


def compute_features_at_entry(
    i,
    y,
    x,
    betas,
    errors,
    ret_betas,
    z_scores,
    ts,
    bar_minutes: int,
    lookback_bars: int = 16,
):
    features = {}

    # Signal Quality
    features["z_entry"] = round(z_scores[i], 2)
    prev_i = max(500, i - 5)
    features["z_velocity"] = round(z_scores[i] - z_scores[prev_i], 2)
    features["spread_std"] = round(np.std(errors[max(0, i - 500) : i]) * 10000, 2)
    features["beta_stability"] = round(np.std(betas[max(0, i - 100) : i]), 4)
    sig_beta_lb = np.mean(betas[max(0, i - 500) : i]) if i > 0 else betas[0]
    hedge_beta_lb = np.mean(ret_betas[max(0, i - 500) : i]) if i > 0 else ret_betas[0]
    features["signal_beta_lookback"] = round(sig_beta_lb, 4)
    features["hedge_beta_lookback"] = round(hedge_beta_lb, 4)
    if abs(sig_beta_lb) > 0.01:
        mismatch = hedge_beta_lb / sig_beta_lb
    else:
        mismatch = 0.0
    mismatch = float(np.clip(mismatch, -10.0, 10.0))
    features["beta_mismatch"] = round(mismatch, 3)

    # Explicit bar-by-bar lags (causal)
    features["z_lag1"] = round(z_scores[i - 1], 3) if i >= 1 else 0.0
    features["z_lag2"] = round(z_scores[i - 2], 3) if i >= 2 else 0.0
    features["z_lag3"] = round(z_scores[i - 3], 3) if i >= 3 else 0.0
    features["dz_lag1"] = round(z_scores[i - 1] - z_scores[i - 2], 3) if i >= 2 else 0.0
    features["dz_lag2"] = round(z_scores[i - 2] - z_scores[i - 3], 3) if i >= 3 else 0.0
    features["beta_lag1"] = round(betas[i - 1], 4) if i >= 1 else round(betas[i], 4)
    features["beta_lag2"] = round(betas[i - 2], 4) if i >= 2 else round(betas[i], 4)

    # Market Regime
    features["beta"] = round(betas[i], 4)
    start = max(0, i - 500)
    vol_y = np.std(np.diff(y[start:i]))
    vol_x = np.std(np.diff(x[start:i]))
    features["vol_ratio"] = round(vol_y / vol_x if vol_x > 0 else 1.0, 3)

    if i >= 500:
        corr = np.corrcoef(x[i - 500 : i], y[i - 500 : i])[0, 1]
        features["correlation_500"] = round(corr, 3)
    else:
        features["correlation_500"] = 0.0

    if i >= 100:
        spread = y[i - 100 : i] - betas[i] * x[i - 100 : i]
        slope = np.polyfit(np.arange(100), spread, 1)[0]
        features["trend_strength"] = round(slope / (np.std(spread) + 1e-8), 3)
    else:
        features["trend_strength"] = 0.0

    # Time Context
    entry_ts = ts[i]
    if hasattr(entry_ts, "hour"):
        features["hour"] = entry_ts.hour
        features["day_of_week"] = entry_ts.weekday()
    else:
        dt = np.datetime64(entry_ts, "ns").astype("datetime64[s]").astype(datetime)
        features["hour"] = dt.hour
        features["day_of_week"] = dt.weekday()

    # Technical Context
    lookback = min(i, lookback_bars)
    features["ret_X_16b"] = round((x[i] - x[i - lookback]) * 10000, 2)
    features["ret_Y_16b"] = round((y[i] - y[i - lookback]) * 10000, 2)
    lookback_1h = min(i, max(1, int(60 / bar_minutes)))
    features["ret_X_1h"] = round((x[i] - x[i - lookback_1h]) * 10000, 2)
    features["ret_Y_1h"] = round((y[i] - y[i - lookback_1h]) * 10000, 2)

    if i >= 100:
        atr_y = np.mean([max(y[j : j + 4]) - min(y[j : j + 4]) for j in range(i - 100, i, 4)])
        atr_x = np.mean([max(x[j : j + 4]) - min(x[j : j + 4]) for j in range(i - 100, i, 4)])
        features["atr_ratio"] = round(atr_y / atr_x if atr_x > 0 else 1.0, 3)
    else:
        features["atr_ratio"] = 1.0

    # Barrier Context Features (historical, no leakage)
    if i >= 50:
        recent_returns = np.diff(y[i - 50 : i])
        features["entry_atr"] = round(np.std(recent_returns) * 10000, 2)
    else:
        features["entry_atr"] = 0.0

    # Vol Regime: current vol vs long-term avg
    if i >= 500:
        short_vol = np.std(np.diff(y[i - 50 : i]))
        long_vol = np.std(np.diff(y[i - 500 : i]))
        features["vol_regime"] = round(short_vol / long_vol if long_vol > 0 else 1.0, 2)
    else:
        features["vol_regime"] = 1.0

    return features
