import numpy as np
import pandas as pd


def sharpe_daily(pnls, timestamps, annualization=252):
    """
    Compute Sharpe using daily aggregated PnL (UTC).
    Missing days are filled with 0 PnL to reflect time exposure.
    """
    if pnls is None or timestamps is None:
        return 0.0
    if len(pnls) == 0:
        return 0.0
    ts = pd.to_datetime(timestamps, utc=True, errors="coerce")
    if ts.isna().all():
        return 0.0

    df = pd.DataFrame({"ts": ts, "pnl": np.asarray(pnls, dtype=float)})
    df = df.dropna(subset=["ts"])
    if df.empty:
        return 0.0

    df["date"] = df["ts"].dt.normalize()
    daily = df.groupby("date")["pnl"].sum()
    full_idx = pd.date_range(daily.index.min(), daily.index.max(), freq="D")
    daily = daily.reindex(full_idx, fill_value=0.0)

    std = float(daily.std(ddof=1)) if len(daily) > 1 else 0.0
    if std <= 1e-12:
        return 0.0
    return float(daily.mean() / std * np.sqrt(annualization))


def sharpe_daily_active(pnls, timestamps, annualization=252):
    """
    Compute Sharpe using daily aggregated PnL, but only on active days
    (no zero-fill for missing days).
    """
    if pnls is None or timestamps is None:
        return 0.0
    if len(pnls) == 0:
        return 0.0
    ts = pd.to_datetime(timestamps, utc=True, errors="coerce")
    if ts.isna().all():
        return 0.0

    df = pd.DataFrame({"ts": ts, "pnl": np.asarray(pnls, dtype=float)})
    df = df.dropna(subset=["ts"])
    if df.empty:
        return 0.0

    df["date"] = df["ts"].dt.normalize()
    daily = df.groupby("date")["pnl"].sum()
    std = float(daily.std(ddof=1)) if len(daily) > 1 else 0.0
    if std <= 1e-12:
        return 0.0
    return float(daily.mean() / std * np.sqrt(annualization))


def sharpe_trade(pnls, timestamps, annualization=252):
    """
    Trade-level Sharpe, annualized using average trades/day.
    """
    if pnls is None or timestamps is None:
        return 0.0
    if len(pnls) == 0:
        return 0.0
    arr = np.asarray(pnls, dtype=float)
    std = float(arr.std(ddof=1)) if len(arr) > 1 else 0.0
    if std <= 1e-12:
        return 0.0

    ts = pd.to_datetime(timestamps, utc=True, errors="coerce")
    ts = ts.dropna()
    if ts.empty:
        return 0.0
    # trades per active day
    if hasattr(ts, "dt"):
        days = ts.dt.normalize().nunique()
    else:
        days = pd.Series(ts).dt.normalize().nunique()
    trades_per_day = len(arr) / max(days, 1)
    ann = np.sqrt(annualization * trades_per_day)
    return float(arr.mean() / std * ann)
