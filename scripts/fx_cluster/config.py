from __future__ import annotations

from datetime import datetime

# Raw tick source (dukascopy monthly parquets: cols timestamp, bid, ask, mid, spread).
TICK_SRC = "/Users/danielfisher/Desktop/dukascopy_ticks"
BAR_DIR = "data/tick_bars"
REPORT_PATH = "docs/analysis/fx_cluster_killtest_report.md"

PAIRS: list[str] = ["EURUSD", "GBPUSD", "AUDUSD", "USDCHF", "USDCAD", "USDJPY"]
# USDJPY held out of the pooled fit by default (behaves differently; spec section 4.4).
POOL_PAIRS: list[str] = [p for p in PAIRS if p != "USDJPY"]

# Sign that maps a pair's log return to a USD-strength ("dollar") return.
# USD is the QUOTE ccy (XXXUSD): USD up => pair down => -1.
# USD is the BASE ccy (USDXXX): USD up => pair up => +1.
USD_SIGN: dict[str, float] = {
    "EURUSD": -1.0, "GBPUSD": -1.0, "AUDUSD": -1.0,
    "USDJPY": 1.0, "USDCHF": 1.0, "USDCAD": 1.0,
}

FREQ = "1h"  # honest hourly base grid

# Triple-barrier (spec section 5). Barrier = K_BARRIER * sigma_bar * sqrt(TARGET_H).
EWMA_LAMBDA = 0.94          # causal vol smoother
K_BARRIER = 1.0             # barrier width in horizon-vol units
TARGET_H = 8               # horizon scaling (bars) for the barrier size
PATIENCE_BARS = 24          # vertical barrier (~1 trading day of hourly bars)

# Cost (spec section 5.2): cross full quoted spread once (RT taker, referenced to mid)
# plus flat cTrader-Razor commission. In basis points.
COMMISSION_BPS_RT = 0.6
SPREAD_STRESS = 1.5         # report sensitivity: net at +50% spread

# Embedding / clustering (spec section 3).
# HDBSCAN density estimation works best in low-D, so cluster on a 2-D UMAP.
# cluster_selection_method='leaf' is REQUIRED: the default 'eom' collapses this
# manifold to 2 broad masses (a trivial recent-return-sign bisection, 0% noise);
# 'leaf' recovers the fine-grained recurring pockets (tens-to-hundreds of clusters,
# ~70-90% noise = healthy). See scripts/fx_cluster/cluster_param_probe.py.
UMAP_N_COMPONENTS = 2
UMAP_N_NEIGHBORS = 30
UMAP_MIN_DIST = 0.0
HDBSCAN_MIN_CLUSTER_SIZE = 400
HDBSCAN_MIN_SAMPLES = 20
HDBSCAN_CLUSTER_SELECTION = "leaf"
RANDOM_SEED = 17

# Scoring (spec section 6).
BOOTSTRAP_BLOCKS = 5000     # time-block bootstrap resamples
BLOCK_DAYS = 5              # block length for the bootstrap
FDR_ALPHA = 0.10
SELECT_MARGIN_BPS = 0.2     # train net edge must beat cost floor by this margin
PERSIST_MIN_MFE_MAE = 1.5   # winning-side MFE/|MAE| floor
PERSIST_MIN_HOLD_BARS = 3   # median hold-time floor

# Kill-test split (spec section 6.1).
TRAIN_START = datetime(2018, 1, 1)
TRAIN_END = datetime(2024, 1, 1)
TEST_START = datetime(2024, 1, 1)
TEST_END = datetime(2026, 6, 1)
