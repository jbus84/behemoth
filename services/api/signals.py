"""
Signal generation endpoint for live trading.

Two modes:
  GET  /signals/{bar} — Runs Kalman pipeline on parquet data (testing/fallback)
  POST /signals/{bar} — Accepts live bar data from cBot, computes signals on-the-fly

Both return entry signals + exit signals for currently OPEN positions.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from behemoth.config import (
    ACTIVE_LEG_HIGH,
    ACTIVE_LEG_LOW,
    MIN_GAP_BARS,
    POSITION_SIZE_PCT,
    Z_ENTRY_MOM,
    Z_LOOKBACK,
    Z_STOP,
)
from behemoth.core.active_leg import select_active_leg
from behemoth.core.kalman import compute_kalman_states
from behemoth.core.zscore import compute_z_scores
from behemoth.io.loaders import load_pair_data
from pipelines.build_events_m15 import PAIRS as M15_PAIRS
from pipelines.build_events_m5 import PAIRS as M5_PAIRS

from .risk import get_or_create_account_state
from .db import get_db
from .models import Position, PositionStatus

logger = logging.getLogger("behemoth.signals")

router = APIRouter(tags=["signals"])

PAIR_MAP = {
    "m5": M5_PAIRS,
    "m15": M15_PAIRS,
}

DATA_DIR = {
    "m5": "data/global_5m",
    "m15": "data/global_15m",
}

# Minutes per bar for timeout calculation
BAR_MINUTES = {"m5": 5, "m15": 15}

# Maximum bars to hold a position before timeout
MAX_HOLD_BARS = 500

# Mapping from Behemoth pair name → (leg_x_ctrader_symbol, leg_y_ctrader_symbol)
PAIR_SYMBOL_MAP = {
    # FX & Commodities
    "EUR/GBP": ("EURUSD", "GBPUSD"),
    "Gold/Oil": ("BCOUSD", "XAUUSD"),
    "Oil/Silver": ("BCOUSD", "XAGUSD"),
    "AUD/NZD": ("NZDUSD", "AUDUSD"),
    "CAC/NZD": ("NZDUSD", "FRXEUR"),
    "Gold/Silver": ("XAUUSD", "XAGUSD"),
    # Global Equities
    "SPX/DAX": ("SPXUSD", "GRXEUR"),
    "SPX/CAC": ("SPXUSD", "FRXEUR"),
    "SPX/FTSE": ("SPXUSD", "UKXGBP"),
    "SPX/Nikkei": ("SPXUSD", "JPXJPY"),
    "SPX/HK": ("SPXUSD", "HKXHKD"),
    "SPX/Dow": ("SPXUSD", "UDXUSD"),
    "SPX/Nas": ("SPXUSD", "NSXUSD"),
    # Extended FX
    "AUD/CAD": ("AUDUSD", "USDCAD"),
    "EUR/CHF": ("EURUSD", "USDCHF"),
    "EUR/JPY": ("EURUSD", "USDJPY"),
    "GBP/JPY": ("GBPUSD", "USDJPY"),
    "CHF/JPY": ("USDCHF", "USDJPY"),
    "EUR/AUD": ("EURUSD", "AUDUSD"),
    "GBP/AUD": ("GBPUSD", "AUDUSD"),
    "GBP/CAD": ("GBPUSD", "USDCAD"),
    "NZD/CAD": ("NZDUSD", "USDCAD"),
}

# Reverse lookup: for each pair, which symbols are needed
# Built once at import time
REQUIRED_SYMBOLS: set[str] = set()
for leg_x, leg_y in PAIR_SYMBOL_MAP.values():
    REQUIRED_SYMBOLS.add(leg_x)
    REQUIRED_SYMBOLS.add(leg_y)


# ── Pydantic models for POST request ─────────────────────────────────

class BarDataRequest(BaseModel):
    """
    Bar data submitted by the cBot.
    bars: mapping of cTrader symbol name → list of close prices (oldest first)
    """

    bars: dict[str, list[float]]
    current_time: datetime | None = None
    equity: float | None = None


# ── Core signal computation ──────────────────────────────────────────

def _compute_signal_from_arrays(
    name: str, y_prices: np.ndarray, x_prices: np.ndarray, target_usd: float
) -> dict | None:
    """Run Kalman → z-score on price arrays and return signal if actionable."""
    min_len = Z_LOOKBACK + 1
    if len(y_prices) < min_len or len(x_prices) < min_len:
        return None

    # Use the shorter of the two arrays
    n = min(len(y_prices), len(x_prices))
    y = np.log(y_prices[-n:])
    x = np.log(x_prices[-n:])

    betas, errors, _ = compute_kalman_states(y, x, window=Z_LOOKBACK)
    z_scores = compute_z_scores(errors, window=Z_LOOKBACK)

    idx = len(z_scores) - 1
    z = z_scores[idx]
    beta = betas[idx]

    if abs(z) < Z_ENTRY_MOM:
        return None

    # Don't enter if z is already past exit stop — would be exited immediately
    if abs(z) > Z_STOP:
        return None

    active = select_active_leg(beta, ACTIVE_LEG_LOW, ACTIVE_LEG_HIGH)
    if active is None:
        return None

    symbols = PAIR_SYMBOL_MAP.get(name)
    if not symbols:
        return None

    return {
        "pair": name,
        "side": "LONG" if z > 0 else "SHORT",
        "active_leg": active,
        "z_score": round(float(z), 4),
        "beta": round(float(beta), 6),
        "leg_x": symbols[0],
        "leg_y": symbols[1],
        "leg_x": symbols[0],
        "leg_y": symbols[1],
        "target_usd": target_usd,
    }


def _compute_z_from_arrays(
    y_prices: np.ndarray, x_prices: np.ndarray
) -> float | None:
    """Compute latest z-score from price arrays (for exit checks)."""
    min_len = Z_LOOKBACK + 1
    if len(y_prices) < min_len or len(x_prices) < min_len:
        return None

    n = min(len(y_prices), len(x_prices))
    y = np.log(y_prices[-n:])
    x = np.log(x_prices[-n:])

    _, errors, _ = compute_kalman_states(y, x, window=Z_LOOKBACK)
    z_scores = compute_z_scores(errors, window=Z_LOOKBACK)
    return float(z_scores[len(z_scores) - 1])


# ── Exit checking ────────────────────────────────────────────────────

def _check_exits(
    bar: str,
    now: datetime,
    db: Session,
    z_lookup: dict[str, float] | None = None,
) -> list[dict]:
    """
    Check all OPEN positions for exit conditions:
    1. Z crosses zero → close (LOSS_REV)
    2. |Z| > Z_STOP (4.0) → close (WIN_MOM)
    3. 500 bars elapsed since entry → close (TIMEOUT)
    """
    strategy_prefix = f"mom_{bar}"
    bar_mins = BAR_MINUTES.get(bar, 15)

    open_positions = (
        db.query(Position)
        .filter(
            Position.status == PositionStatus.OPEN,
            Position.strategy_id.like(f"{strategy_prefix}%"),
        )
        .all()
    )

    if not open_positions:
        return []

    exits = []
    for pos in open_positions:
        pair = pos.pair
        side = pos.side.value if hasattr(pos.side, "value") else str(pos.side)

        # Check timeout first
        if pos.entry_ts:
            elapsed_minutes = (now - pos.entry_ts.replace(tzinfo=timezone.utc)).total_seconds() / 60
            elapsed_bars = int(elapsed_minutes / bar_mins)
            if elapsed_bars >= MAX_HOLD_BARS:
                exits.append({
                    "position_id": pos.id,
                    "pair": pair,
                    "side": side,
                    "reason": "TIMEOUT",
                    "z_score": None,
                    "bars_held": elapsed_bars,
                })
                continue

        # Get z-score for this pair
        z = z_lookup.get(pair) if z_lookup else None
        if z is None:
            continue

        reason = None
        if side == "LONG":
            if z < 0:
                reason = "Z_CROSS_ZERO"
            elif z > Z_STOP:
                reason = "Z_STOP_WIN"
        elif side == "SHORT":
            if z > 0:
                reason = "Z_CROSS_ZERO"
            elif z < -Z_STOP:
                reason = "Z_STOP_WIN"

        if reason:
            bars_held = None
            if pos.entry_ts:
                elapsed = (now - pos.entry_ts.replace(tzinfo=timezone.utc)).total_seconds() / 60
                bars_held = int(elapsed / bar_mins)
            exits.append({
                "position_id": pos.id,
                "pair": pair,
                "side": side,
                "reason": reason,
                "z_score": round(z, 4),
                "bars_held": bars_held,
            })

    return exits


# ── POST endpoint (production — cBot sends live bars) ─────────────────

@router.post("/signals/{bar}")
def compute_signals(
    bar: str,
    body: BarDataRequest,
    db: Session = Depends(get_db),
):
    """
    Compute entry + exit signals from live bar data submitted by the cBot.

    The cBot sends 750 close prices for each of the 18 unique symbols.
    The API pairs them up and runs Kalman → z-score for each pair.
    """
    if bar not in PAIR_MAP:
        raise HTTPException(status_code=400, detail=f"Unknown bar: {bar}. Use m5 or m15.")

    bars = body.bars
    ts = body.current_time or datetime.now(timezone.utc)

    # Validate we have enough symbols
    missing = REQUIRED_SYMBOLS - bars.keys()
    if missing:
        logger.warning("missing_symbols count=%d symbols=%s", len(missing), sorted(missing))

    signals = []
    z_lookup: dict[str, float] = {}

    # Dynamic Sizing: 1% of current equity
    account_state = get_or_create_account_state(db, f"mom_{bar}")
    
    # Sync with cTrader equity if provided
    if body.equity:
        account_state.equity = body.equity
        if body.equity > account_state.peak_equity:
            account_state.peak_equity = body.equity
        db.commit()

    equity = float(account_state.equity)
    target_usd = equity * POSITION_SIZE_PCT

    # Cooldown: find pairs with positions closed within last MIN_GAP_BARS bars
    bar_mins = BAR_MINUTES.get(bar, 15)
    cooldown_cutoff = ts - timedelta(minutes=bar_mins * MIN_GAP_BARS)
    try:
        recently_closed = (
            db.query(Position.pair)
            .filter(
                Position.status == PositionStatus.CLOSED,
                Position.exit_ts >= cooldown_cutoff,
            )
            .all()
        )
        cooldown_pairs = {row.pair for row in recently_closed}
    except Exception:
        cooldown_pairs = set()

    for pair_name, (sym_x, sym_y) in PAIR_SYMBOL_MAP.items():
        if sym_x not in bars or sym_y not in bars:
            continue

        x_prices = np.array(bars[sym_x], dtype=np.float64)
        y_prices = np.array(bars[sym_y], dtype=np.float64)

        try:
            # Compute entry signal
            sig = _compute_signal_from_arrays(pair_name, y_prices, x_prices, target_usd)
            if sig is not None:
                if pair_name in cooldown_pairs:
                    logger.info("cooldown_skip pair=%s (MIN_GAP_BARS=%d)", pair_name, MIN_GAP_BARS)
                else:
                    signals.append(sig)

            # Compute z-score for exit checks
            z = _compute_z_from_arrays(y_prices, x_prices)
            if z is not None:
                z_lookup[pair_name] = z
        except Exception as exc:
            logger.warning("signal_error pair=%s error=%s", pair_name, exc)

    # Check exit conditions
    try:
        exits = _check_exits(bar, ts, db, z_lookup)
    except Exception as exc:
        logger.warning("exit_check_error error=%s", exc)
        exits = []

    return {
        "bar": bar,
        "signals": signals,
        "exits": exits,
        "checked_pairs": len(PAIR_SYMBOL_MAP),
        "timestamp": ts.isoformat(),
    }


# ── GET endpoint (testing fallback — loads from parquet) ──────────────

def _compute_latest_signal_parquet(
    name: str, fx: str, fy: str, cx: str, cy: str, data_dir: str
) -> dict | None:
    """Run Kalman pipeline on parquet data for one pair."""
    df = load_pair_data(data_dir, fx, fy, cx, cy)
    if df is None or df.height < Z_LOOKBACK + 100:
        return None

    y = np.log(df["Y"].to_numpy())
    x = np.log(df["X"].to_numpy())

    betas, errors, _ = compute_kalman_states(y, x, window=Z_LOOKBACK)
    z_scores = compute_z_scores(errors, window=Z_LOOKBACK)

    idx = len(z_scores) - 1
    z = z_scores[idx]
    beta = betas[idx]

    if abs(z) < Z_ENTRY_MOM:
        return None

    active = select_active_leg(beta, ACTIVE_LEG_LOW, ACTIVE_LEG_HIGH)
    if active is None:
        return None

    symbols = PAIR_SYMBOL_MAP.get(name)
    leg_x = symbols[0] if symbols else fx
    leg_y = symbols[1] if symbols else fy

    return {
        "pair": name,
        "side": "LONG" if z > 0 else "SHORT",
        "active_leg": active,
        "z_score": round(float(z), 4),
        "beta": round(float(beta), 6),
        "leg_x": leg_x,
        "leg_y": leg_y,
    }


@router.get("/signals/{bar}")
def get_signals(
    bar: str,
    current_time: datetime | None = Query(
        default=None, description="Current bar close time"
    ),
    db: Session = Depends(get_db),
):
    """
    Testing/fallback: scan all pairs using parquet data.
    For production use POST /signals/{bar} with live bar data instead.
    """
    if bar not in PAIR_MAP:
        raise HTTPException(status_code=400, detail=f"Unknown bar: {bar}. Use m5 or m15.")

    pairs = PAIR_MAP[bar]
    data_dir = DATA_DIR[bar]
    signals = []
    z_lookup: dict[str, float] = {}

    for entry in pairs:
        name, fx, fy, cx, cy = entry[0], entry[1], entry[2], entry[3], entry[4]
        try:
            sig = _compute_latest_signal_parquet(name, fx, fy, cx, cy, data_dir)
            if sig is not None:
                signals.append(sig)

            # Also compute z for exit checks
            df = load_pair_data(data_dir, fx, fy, cx, cy)
            if df is not None and df.height >= Z_LOOKBACK + 100:
                y = np.log(df["Y"].to_numpy())
                x = np.log(df["X"].to_numpy())
                _, errors, _ = compute_kalman_states(y, x, window=Z_LOOKBACK)
                zs = compute_z_scores(errors, window=Z_LOOKBACK)
                z_lookup[name] = float(zs[len(zs) - 1])
        except Exception as exc:
            logger.warning("signal_error pair=%s error=%s", name, exc)

    ts = current_time or datetime.now(timezone.utc)

    try:
        exits = _check_exits(bar, ts, db, z_lookup)
    except Exception as exc:
        logger.warning("exit_check_error error=%s", exc)
        exits = []

    return {
        "bar": bar,
        "signals": signals,
        "exits": exits,
        "checked_pairs": len(pairs),
        "timestamp": ts.isoformat(),
    }
