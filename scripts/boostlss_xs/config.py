"""
Definitive live configuration for the BoostLSS OCO reversion strategy.

Validated on 6yr OOS tick-exact backtest (2020–2025), 17 G10 pairs.
Option B all-in: +1.019 bps/fill (excl. 18–21 UTC dead zone).

Do not modify without re-running meta_label_v2.py and causal_validation.py.
"""

# ── Pair universe ─────────────────────────────────────────────────────────────
# 14 pairs positive all-in after post-bugfix re-run (excl 18-21 UTC).
# Dropped: EURCHF/EURGBP/GBPCHF (reject-cost drag exceeds maker net).
# Previously also excluded: AUDCAD, AUDNZD, EURNZD, GBPNZD (too wide).
LIVE_PAIRS: list[str] = [
    "AUDJPY",
    "AUDUSD",
    "CADJPY",
    "CHFJPY",
    "EURAUD",
    "EURJPY",
    "EURUSD",
    "GBPAUD",
    "GBPJPY",
    "GBPUSD",
    "NZDUSD",
    "USDCAD",
    "USDCHF",
    "USDJPY",
]

# ── Session filter ────────────────────────────────────────────────────────────
# 18–21 UTC: NY-close to Asia-open dead zone. Momentum dominates, reversion
# fails systematically. Dropping these hours costs 3.7% of trades but adds
# +0.187 bps/fill.
EXCLUDED_HOURS_UTC: set[int] = {18, 19, 20, 21}

# ── OCO barrier parameters ───────────────────────────────────────────────────
ENTRY_K: float = 0.5    # entry at close ± entry_k × sigma
SL_K: float    = 1.0    # SL at entry ± sl_k × sigma beyond entry
HOLD_HOURS: int = 8     # max hold before time-based exit

# ── GaussianLSS signal threshold ─────────────────────────────────────────────
SIG_THRESH: float = 1.5  # minimum normalised sigma to trigger OCO placement

# ── Meta-labeler ──────────────────────────────────────────────────────────────
META_THRESHOLD: float = 0.55   # prob_tp threshold: accept >= this, reject below
# Threshold sweep is flat 0.45–0.60; 0.55 chosen for stability margin.

# ── Cost model (Pepperstone Razor) ───────────────────────────────────────────
COMMISSION_RT_BPS: float = 0.70   # round-trip commission, both legs

# Median bid-ask spreads from Dukascopy tick data (bps).
# Used as fallback when fill_spread is unavailable.
SPREAD_BPS: dict[str, float] = {
    "EURUSD": 0.275, "GBPUSD": 0.699, "USDJPY": 0.432,
    "USDCAD": 0.885, "USDCHF": 1.020, "AUDUSD": 1.456,
    "EURAUD": 1.371, "EURCHF": 1.049, "EURGBP": 0.998,
    "EURJPY": 0.625, "GBPAUD": 1.671, "GBPCHF": 1.622,
    "GBPJPY": 1.146, "AUDJPY": 0.862, "CADJPY": 1.218,
    "CHFJPY": 1.278, "NZDUSD": 1.758,
}

# ── Performance summary (OOS, tick-exact, post-bugfix re-run) ────────────────
# Pairs: 17  |  Hours: excl 18–21 UTC  |  Threshold: 0.55
# Option B all-in:  +0.634 bps/fill        (was +1.019 before OCO + TB cost fixes)
# AUC:               0.827
# TP/SL/TB:          67.5% / 31.7% / 0.8%
# Spread fallback:   0.0%  (tick data clean)
# Years positive:    6/6 (2020–2025, all positive after hour filter)
#
# Positive pairs (excl 18-21 UTC):
#   EURUSD +1.441  AUDJPY +1.691  USDJPY +1.314  EURJPY +1.285  GBPUSD +1.079
#   AUDUSD +0.793  CADJPY +0.767  GBPJPY +0.738  NZDUSD +0.487  USDCHF +0.482
#   USDCAD +0.293  CHFJPY +0.368  GBPAUD +0.347  EURAUD +0.059
# Negative pairs (reject-cost drag exceeds maker net):
#   EURCHF -0.274  EURGBP -0.285  GBPCHF -0.328
#
# Previous headline (+1.019) reflected: (a) direction pre-assigned from 1m mid
# (not true simultaneous OCO), (b) TB exits charged commission-only not taker,
# (c) blocked window anchored to bar open not fill time.
