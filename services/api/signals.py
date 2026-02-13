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
from sqlalchemy import desc

from behemoth.config import (
    ACTIVE_LEG_HIGH,
    ACTIVE_LEG_LOW,
    MIN_GAP_BARS,
    POSITION_SIZE_PCT,
    Z_ENTRY_MOM,
    Z_LOOKBACK,
    Z_STOP,
    LOSS_STREAK,
    COOLDOWN_DAYS,
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
    "Gold/Silver": ("XAUUSD", "XAGUSD"),
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


def _check_guardrail(
    db: Session, strategy_prefix: str, pair: str
) -> bool:
    """
    Check if pair is in a loss streak (last N trades are losses) 
    AND within cooldown period.
    Returns True if trading should be BLOCKED.
    """
    # Get last N closed positions
    closed = (
        db.query(Position)
        .filter(
            Position.status == PositionStatus.CLOSED,
            Position.pair == pair,
            Position.strategy_id.like(f"{strategy_prefix}%")
        )
        .order_by(desc(Position.exit_ts))
        .limit(LOSS_STREAK)
        .all()
    )

    if len(closed) < LOSS_STREAK:
        return False

    # Check if all are losses (pnl < 0)
    is_streak = all((pos.pnl_bps is not None and float(pos.pnl_bps) < 0) for pos in closed)
    if not is_streak:
        return False

    # Check cooldown
    last_exit = closed[0].exit_ts
    if not last_exit:
        return False

    if last_exit.tzinfo is None:
        last_exit = last_exit.replace(tzinfo=timezone.utc)
    
    now = datetime.now(timezone.utc)
    # Check if within COOLDOWN_DAYS
    delta = now - last_exit
    if delta.days < COOLDOWN_DAYS:
        return True

    return False


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


# ── Global State for Incremental Mode ─────────────────────────────────
# Keyed by strategy_prefix (e.g. "mom_m15") -> pair_name
STATE_BUFFER: dict[str, dict[str, pd.DataFrame]] = {}
STATE_KALMAN: dict[str, dict[str, Any]] = {}  # Stores KalmanFilter objects
STATE_ERRORS: dict[str, dict[str, list[float]]] = {} # Rolling errors for Z-score

def _get_state_key(bar: str) -> str:
    return f"mom_{bar}"

def reset_strategy_state(bar: str):
    key = _get_state_key(bar)
    if key in STATE_BUFFER:
        del STATE_BUFFER[key]
    if key in STATE_KALMAN:
        del STATE_KALMAN[key]
    if key in STATE_ERRORS:
        del STATE_ERRORS[key]
    logger.info(f"State reset for {key}")

@router.post("/reset/{bar}")
def reset_endpoint(bar: str):
    reset_strategy_state(bar)
    return {"status": "ok", "bar": bar}



# ── POST endpoint (production — cBot sends live bars) ─────────────────

@router.post("/signals/{bar}")
def compute_signals(
    bar: str,
    body: BarDataRequest,
    db: Session = Depends(get_db),
    reset: bool = Query(False),
):
    """
    Receives bar data from cBot.
    Mode:
      - valid_bars > 1: Full init/re-init (stateless or state reset)
      - valid_bars == 1: Incremental update (stateful)
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
    
    # Determine mode: Init or Update
    is_init = True
    state_key = f"mom_{bar}"
    
    # Check if we have state for at least one pair or if payload has many bars
    if not reset and STATE_KALMAN.get(state_key):
        # We have state. Check payload size.
        # If payload has 1 bar, it's an update. If >1, it's a re-init.
        # We need to look at the first symbol's data length
        first_len = 0
        for closes in body.bars.values():
            first_len = len(closes)
            break
            
        if first_len == 1:
            is_init = False
    elif not reset and not STATE_KALMAN.get(state_key):
        # Edge Case: Client sends 1 bar (expecting update), but Server has no state (restart)
        # We must tell client to resend full history.
        # Check payload size to confirm it is indeed an incremental attempt
        first_len = 0
        for closes in body.bars.values():
            first_len = len(closes)
            break
            
        if first_len == 1:
             # Client thinks it's incremental, but we have no state -> 409 Conflict
             logger.warning(f"State missing for {state_key} but received incremental update. Requesting reset.")
             raise HTTPException(
                 status_code=409, 
                 detail="State missing. Please resend full history."
             )
    
    if reset:
        reset_strategy_state(bar)
        is_init = True

    # Prepare state dictionaries for this bar timeframe
    if state_key not in STATE_KALMAN:
        STATE_KALMAN[state_key] = {}
    if state_key not in STATE_ERRORS:
        STATE_ERRORS[state_key] = {}
    if state_key not in STATE_BUFFER:
        STATE_BUFFER[state_key] = {}

    ts = datetime.fromisoformat(body.timestamp.replace("Z", "+00:00"))
    
    # Update Account State (Shared)
    account_state = get_or_create_account_state(db, f"mom_{bar}")
    if body.equity:
        account_state.equity = body.equity
        if body.equity > account_state.peak_equity:
            account_state.peak_equity = body.equity
        db.commit()

    equity = float(account_state.equity)
    target_usd = equity * POSITION_SIZE_PCT
    
    signals = []
    z_lookup = {}
    
    # Identify closed positions for Guardrail
    cooldown_cutoff = ts - timedelta(days=settings.guardrail_cooldown_days)
    try:
        recently_closed = (
            db.query(Position)
            .filter(
                Position.strategy_id == f"mom_{bar}", # Changed from strategy to strategy_id
                Position.status == PositionStatus.CLOSED,
                Position.exit_ts >= cooldown_cutoff,
            )
            .all()
        )
        cooldown_pairs = {row.pair for row in recently_closed}
    except Exception:
        cooldown_pairs = set()

    bars = body.bars

    for pair_name, (sym_x, sym_y) in PAIR_SYMBOL_MAP.items():
        if sym_x not in bars or sym_y not in bars:
            continue

        # Check Loss Streak Guardrail
        if _check_guardrail(db, f"mom_{bar}", pair_name):
            continue

        y_vals = np.array(bars[sym_y], dtype=np.float64)
        x_vals = np.array(bars[sym_x], dtype=np.float64)

        # Kalman Filter State
        kf_state = STATE_KALMAN[state_key].get(pair_name)
        
        # ── INITIALIZATION (Full History) ─────────────────────────────
        if is_init or kf_state is None:
            # Full recalculation
            if len(y_vals) < Z_LOOKBACK:
                continue

            # Compute initial state
            y_log = np.log(y_vals)
            x_log = np.log(x_vals)
            
            # Use existing function but extracting final state
            betas, errors, _ = compute_kalman_states(y_log, x_log, window=Z_LOOKBACK)
            
            # Store state: We need a live KF object initialized with the final values
            # Re-create a KF and "fast-forward" it to the current state? 
            # Actually simpler: The KalmanFilterReg class stores P and beta.
            # We can just initialize a new one. But compute_kalman_states does a batch run.
            # To support incremental updates, we need the *final* P and beta from the batch run.
            # Our current `compute_kalman_states` function doesn't return the final P matrix!
            # We need to modify `kalman.py` or inline the logic here.
            # OR: Just run the batch, get the z-score, and for next time,
            # initialize a new KF with loose priors? No, discontinuous.
            
            # Better approach for Init: Run the batch to get history,
            # then instantiate a KF and feed it the last few points to "warm up" P? 
            # Or just refactor `compute_kalman_states` to return the KF object?
            # Let's assume for now we just run batch every time if it's init.
            
            # Z-score calculation
            z_scores = compute_z_scores(errors, window=Z_LOOKBACK)
            z = z_scores[-1]
            beta = betas[-1]
            
            # Persist state for incremental updates
            # unique KF per pair
            kf = KalmanFilterReg(Q=1e-5, R=1e-3)
            # "Hack": We can't easily extract P from the batch function.
            # So for the *transition* to incremental, we might suffer a small discontinuity
            # unless we run the KF loop here.
            # Given we want 100x speedup, let's process the full history *with* the class here
            
            kf = KalmanFilterReg(Q=1e-5, R=1e-3)
            # Batch update the KF to sync state
            rolling_errors = []
            for i in range(len(y_log)):
                 b, err = kf.update(x_log[i], y_log[i]) # Simple 1-var regression logic mismatch? 
                 # Wait, compute_kalman_states uses rolling mean shift. 
                 # We need to replicate that.
            
            # Optimization: 
            # The *first* call is distinct. We can just use the batch function for the signal,
            # BUT we need to prep the creation of the incremental state.
            
            # Let's save the rolling z-score error buffer
            STATE_ERRORS[state_key][pair_name] = list(errors[-Z_LOOKBACK:])
            
            # Re-instantiate a text-book KF and burn through data to get P?
            # Yes, expensive but only happens once.
            kf_live = KalmanFilterReg(Q=1e-5, R=1e-3)
            
            # Need rolling means too!
            # The "Input" to KF is (x - mu_x), (y - mu_y).
            # So we need to maintain Rolling buffers for X and Y too.
            STATE_BUFFER[state_key][pair_name] = pd.DataFrame({"y": y_log, "x": x_log})
            
            # Run KF on (de-meaned) history to prime P and Beta
            # Use pandas rolling on the full buffer
            # MUST match compute_kalman_states logic (min_periods=1)
            check_df = STATE_BUFFER[state_key][pair_name]
            mu_y = check_df["y"].rolling(750, min_periods=1).mean().shift(1)
            mu_x = check_df["x"].rolling(750, min_periods=1).mean().shift(1)
            
            # Burn in
            # This is locally slow (O(N)) but only happens once.
            warmup = 10
            for i in range(len(check_df)):
                if i < warmup:
                    mx = check_df["x"].iloc[i]
                    my = check_df["y"].iloc[i]
                else: 
                    mx = mu_x.iloc[i]
                    my = mu_y.iloc[i]
                
                if pd.isna(mx) or pd.isna(my): continue
                kf_live.update(check_df["x"].iloc[i] - mx, check_df["y"].iloc[i] - my)

            STATE_KALMAN[state_key][pair_name] = kf_live
            
            # signal decision uses the batch result this one time
            
        # ── UPDATE (Incremental) ──────────────────────────────────────
        else:
            # We have STATE_KALMAN and STATE_BUFFER
            # y_vals and x_vals are length 1
            new_y = np.log(y_vals[0])
            new_x = np.log(x_vals[0])
            
            # 1. Update rolling buffers
            pdf = STATE_BUFFER[state_key][pair_name]
            
            # Append new row
            new_row = pd.DataFrame({"y": [new_y], "x": [new_x]})
            pdf = pd.concat([pdf, new_row], ignore_index=True)
            if len(pdf) > Z_LOOKBACK + 50:
                pdf = pdf.iloc[-(Z_LOOKBACK + 10):] # Keep enough for rolling
            STATE_BUFFER[state_key][pair_name] = pdf
            
            # 2. Compute Rolling Means (for just the last point)
            # rolling(750).mean().shift(1) -> effectively mean of [t-750 : t-1]
            last_window = pdf.iloc[-(Z_LOOKBACK+1):-1]
            mu_y = last_window["y"].mean()
            mu_x = last_window["x"].mean()
            
            # 3. Update Kalman
            kf = STATE_KALMAN[state_key][pair_name]
            beta, error = kf.update(new_x - mu_x, new_y - mu_y)
            # The 'beta' returned is the slope. The 'error' is the residual.
            
            # 4. Update Z-Score
            # Compute stats on PREVIOUS errors (current buffer) before append
            err_buf = STATE_ERRORS[state_key][pair_name]
            
            if len(err_buf) > 10: # Avoid div/0 on very short history (unlikely here)
                err_mean = np.mean(err_buf)
                err_std = np.std(err_buf)
                z = (error - err_mean) / err_std if err_std > 1e-9 else 0.0
            else:
                z = 0.0
            
            err_buf.append(error)
            if len(err_buf) > Z_LOOKBACK:
                err_buf.pop(0) 
        
        # ── Signal Generation (Common) ────────────────────────────────
        
        # Exit check needs z_lookup
        z_lookup[pair_name] = z
        
        # Entry check
        if abs(z) >= Z_ENTRY_MOM:
             # Logic for active leg...
             # We need beta to determine active leg.
             # existing function 'select_active_leg' works on float
             active_leg = select_active_leg(beta, ACTIVE_LEG_LOW, ACTIVE_LEG_HIGH)
             
             if active_leg:
                 # Check cooldown again? done above.
                 # Direction
                 side = "LONG" if z > 0 else "SHORT"
                 
                 # Create signal object
                 sig = {
                    "pair": pair_name,
                    "side": side,
                    "active_leg": active_leg,
                    "z_score": round(float(z), 4),
                    "beta": round(float(beta), 6),
                    "leg_x": sym_x,
                    "leg_y": sym_y,
                    "lot_size": 0.0, # handled by cBot fallback or equity
                    "target_usd": round(target_usd, 2)
                 }
                 # Skip logic if already open? cBot handles that, but we can double check db?
                 # No, cBot is source of truth for "is it open right now"
                 signals.append(sig)

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
