Z_ENTRY_MOM = 1.5
Z_ENTRY_REV = 2.5
Z_STOP = 4.0
Z_LOOKBACK = 750
MIN_GAP_BARS = 20
ACTIVE_LEG_LOW = 0.98
ACTIVE_LEG_HIGH = 1.02
POSITION_SIZE_PCT = 0.01

MOM_ACCEL_THRESH = 0.005 # Optimal for H1 (Sharpe 2.04)
REV_ACCEL_THRESH = 100.0 # DISABLED

LOSS_STREAK = 3
COOLDOWN_DAYS = 7

# Offline-only exit policy controls (backtest/event builders).
# Live API remains on fixed timeout semantics until explicitly migrated.
EXIT_TIMEOUT_MODE_OFFLINE = "adaptive_entry_z"
EXIT_TIMEOUT_MODE_LIVE = "fixed"

# Entry-time exit contract variants for offline evaluation.
# - baseline: legacy cross-zero + stop-win
# - soft_cross: small cross-zero buffer to reduce churn exits
# - no_stop_win: disable stop-win, keep cross-zero + timeout
ENTRY_EXIT_VARIANTS = ("baseline", "soft_cross", "no_stop_win")
ENTRY_EXIT_VARIANT_OFFLINE = "baseline"
