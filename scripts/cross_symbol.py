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
    target_symbol: str,
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


def _add_market_measures(
    frame: pd.DataFrame,
    target_symbol: str,
) -> pd.DataFrame:
    """Append mkt_all6 and mkt_loo to a frame that already carries the
    xs_ret_z__{peer} columns from _align_peer_returns. mkt_pca is added by a
    later step."""
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
    return out
