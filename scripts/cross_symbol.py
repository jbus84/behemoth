"""Cross-symbol alignment infrastructure.

Given a target symbol and a bar_ticks setting, build that symbol's own tick
frame enriched with backward as-of-joined peer returns and a synthetic
mean-market (USD) measure. Tick-native: no resampling, no global clock.

See docs/superpowers/specs/2026-05-19-cross-symbol-alignment-design.md.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

# The 6 FX majors compared against each other.
CROSS_SYMBOLS: list[str] = [
    "EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCAD", "USDCHF",
]

# Sign that orients each symbol's return to "USD strength": +1 when a price
# rise means USD strengthened (USD is the base currency), -1 when a price
# rise means USD weakened (USD is the quote currency).
_USD_SIGN: dict[str, int] = {
    "EURUSD": -1,
    "GBPUSD": -1,
    "AUDUSD": -1,
    "USDJPY": 1,
    "USDCAD": 1,
    "USDCHF": 1,
}


def _usd_aligned_ret_z(frame: pd.DataFrame, symbol: str) -> pd.Series:
    """The symbol's volatility-normalised return oriented to USD strength."""
    ret_z = pd.to_numeric(frame["ret_z"], errors="coerce")
    return _USD_SIGN[symbol] * ret_z


def _align_peer_returns(
    target: pd.DataFrame,
    peers: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """Append one USD-aligned peer return column per peer, backward as-of
    joined onto the target frame's close_ts. Look-ahead-free: each target
    bar at time T sees only peer bars with close_ts <= T."""
    out = target.reset_index(drop=True).copy()
    left = out[["close_ts"]].copy()
    for peer_symbol, peer_frame in peers.items():
        col = f"xs_ret_z__{peer_symbol}"
        right = pd.DataFrame({
            "close_ts": pd.to_datetime(
                peer_frame["close_ts"], utc=True, errors="coerce"
            ),
            col: _usd_aligned_ret_z(peer_frame, peer_symbol).to_numpy(),
        })
        right = right[right["close_ts"].notna()].sort_values(
            "close_ts"
        ).reset_index(drop=True)
        joined = pd.merge_asof(
            left, right, on="close_ts", direction="backward",
        )
        out[col] = joined[col].to_numpy()
    return out


def _rolling_pca_factor(
    mat: np.ndarray,
    *,
    window: int = 500,
    min_periods: int = 200,
) -> np.ndarray:
    """First-principal-component factor, fit on a strictly-trailing window.

    For row i the covariance is estimated from rows [i-window, i-1] only —
    never row i or later — so the factor is look-ahead-free. PC1 is oriented
    so its loadings sum positive: under a common USD factor every column
    loads the same sign, and this fixes the eigenvector's arbitrary sign so
    the factor tracks the shared move rather than its negation."""
    arr = np.asarray(mat, dtype=float)
    n = arr.shape[0]
    out = np.full(n, np.nan, dtype=float)
    for i in range(n):
        lo = max(0, i - window)
        win = arr[lo:i]  # strictly trailing: excludes row i
        win = win[np.isfinite(win).all(axis=1)]
        if len(win) < min_periods:
            continue
        row = arr[i]
        if not np.isfinite(row).all():
            continue
        cov = np.cov(win, rowvar=False)
        _vals, vecs = np.linalg.eigh(cov)  # ascending eigenvalues
        pc1 = vecs[:, -1]                  # largest-eigenvalue eigenvector
        if pc1.sum() < 0.0:
            pc1 = -pc1
        out[i] = float(row @ pc1)
    return out


def _add_market_measures(
    frame: pd.DataFrame,
    target_symbol: str,
    *,
    pca_window: int = 500,
    pca_min_periods: int = 200,
) -> pd.DataFrame:
    """Append mkt_all6, mkt_loo, and mkt_pca to a frame that already carries
    the xs_ret_z__{peer} columns from _align_peer_returns."""
    out = frame.copy()
    peer_cols = sorted(c for c in out.columns if c.startswith("xs_ret_z__"))
    target_usd = _usd_aligned_ret_z(out, target_symbol)
    # 6-wide matrix: the target's own USD-aligned return + the 5 peers.
    six = pd.concat(
        [target_usd.rename(f"xs_ret_z__{target_symbol}")]
        + [out[c] for c in peer_cols],
        axis=1,
    )
    out["mkt_all6"] = six.mean(axis=1, skipna=True).to_numpy()
    out["mkt_loo"] = out[peer_cols].mean(axis=1, skipna=True).to_numpy()
    out["mkt_pca"] = _rolling_pca_factor(
        six.to_numpy(dtype=float),
        window=pca_window,
        min_periods=pca_min_periods,
    )
    return out


def build_cross_symbol_frame(
    target_symbol: str,
    bar_ticks: int,
    dataset_dir: Path,
    horizons: list[int],
) -> pd.DataFrame:
    """Return the target symbol's tick frame enriched with backward
    as-of-joined peer returns and the three market measures.

    All 6 CROSS_SYMBOLS must have a velocity parquet in dataset_dir — a
    coherent cross-section cannot be built from a partial roster.
    """
    from scripts.run_tick_opportunity_mining import _prepare_frame

    if target_symbol not in CROSS_SYMBOLS:
        raise ValueError(
            f"target_symbol {target_symbol!r} is not a cross-symbol major; "
            f"expected one of {CROSS_SYMBOLS}"
        )
    dataset_dir = Path(dataset_dir)
    frames: dict[str, pd.DataFrame] = {}
    for sym in CROSS_SYMBOLS:
        path = dataset_dir / f"{sym}_{int(bar_ticks)}tick_velocity.parquet"
        if not path.exists():
            raise FileNotFoundError(
                f"cross-symbol alignment requires all {len(CROSS_SYMBOLS)} "
                f"majors; missing velocity parquet for {sym}: {path}"
            )
        frames[sym] = _prepare_frame(path, symbol=sym, horizons=horizons)

    target = frames[target_symbol]
    peers = {s: f for s, f in frames.items() if s != target_symbol}
    aligned = _align_peer_returns(target, peers)
    return _add_market_measures(aligned, target_symbol)
