"""
Builds ML Feature Dataset for H1 Signals.
Joins Signal Events with:
- Lagged Features (1..30 bars) of the trading pair.
- Cross-Sectional Features (Current Z-Score of major market drivers).
"""
import os
import sys
import numpy as np
import polars as pl
import pandas as pd
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from behemoth.core.kalman import compute_kalman_states as _compute_kalman_states
from behemoth.core.zscore import compute_z_scores as _compute_z_scores
from behemoth.io.loaders import load_pair_data as _load_pair_data
# Import PAIRS config from build_events_h1 to ensure consistency
from pipelines.build_events_h1 import PAIRS, DATA_DIR

OUTPUT_DIR = "data/ml"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def build_features():
    print("--- BUILDING ML FEATURES (H1) ---")
    
    # 1. Load Signal Events
    events_path = "data/events/events_h1_8yr_v3_dual.csv"
    if not os.path.exists(events_path):
        print(f"Error: {events_path} not found. Run pipelines/build_events_h1.py first.")
        return
        
    print(f"Loading events from {events_path}...")
    df_events = pl.read_csv(events_path)
    
    # Convert 'timestamp' to datetime
    # The csv has nanos as numbers (float or int)
    df_events = df_events.with_columns(
        pl.col("timestamp").cast(pl.Int64).cast(pl.Datetime("ns")).dt.replace_time_zone("UTC")
    )
    
    print(f"Loaded {len(df_events)} events.")
    
    # 2. Compute Full History States for All Pairs
    # We need this to get Lags and Cross-Sectional data.
    print("Computing full history states...")
    
    pair_features = {} # Map Pair -> DataFrame with timestamp, z, beta, error_std
    
    # We also want a "Market State" table: Timestamp -> {Pair_Z, Pair_Beta...}
    # To avoid huge memory, we can just store Z-scores of *Key Drivers*.
    # Which are key? All of them? 20 pairs * 4 features * 50k bars = ~4M rows. Fits in memory easily.
    
    market_z = [] # List of DataFrames to join later?
    
    for name, fx, fy, cx, cy, cost_y, cost_x in PAIRS:
        df = _load_pair_data(DATA_DIR, fx, fy, cx, cy)
        if df is None:
            continue

        # Compute Core Indicators
        y = np.log(df["Y"].to_numpy())
        x = np.log(df["X"].to_numpy())
        
        betas, errors, ret_betas = _compute_kalman_states(y, x)
        z_scores = _compute_z_scores(errors, window=750)
        
        # Calculate Volatility (std of errors)
        # rolling_std is intermediate in compute_z_scores, but not returned.
        # We can re-calc roughly or extract if modified.
        # Let's just use abs(error) as a proxy or re-calc rolling std.
        error_series = pd.Series(errors)
        rolling_std = error_series.rolling(window=750).std().fillna(0).to_numpy()
        
        # Create Feature DF for this pair
        # We need Lags 1..30
        
        # Polars is fast at lags
        df_feat = pl.DataFrame({
            "timestamp": df["timestamp"],
            "z": z_scores,
            "beta": betas,
            "vol": rolling_std
        })
        
        # Create Lags
        # We only need lags for the *Signal Pair* when we join to events.
        # But we also want *Current* Z of this pair to be a feature for *Other* pairs.
        
        # Store for Cross-Sectional Lookup
        # Rename col to z_{name}
        df_market = df_feat.select([
            pl.col("timestamp"),
            pl.col("z").alias(f"z_{name}")
        ])
        market_z.append(df_market)
        
        # Store full features for Signal Lookup
        pair_features[name] = df_feat
        
    # 3. Join Market State
    print("Joining Market State (Cross-Sectional)...")
    df_market_state = market_z[0]
    for i in range(1, len(market_z)):
        # Outer join or Inner? Timestamps should mostly align if H1.
        # Inner is safer to avoid NaNs.
        df_market_state = df_market_state.join(market_z[i], on="timestamp", how="inner")
        
    print(f"Market State Shape: {df_market_state.shape}")
    
    # 4. Enrich Events
    print("Enriching Events with Features...")
    
    # We iterate pairs, pull their events, join their specific lagged features, then stack.
    enriched_dfs = []
    
    unique_pairs = df_events["pair"].unique().to_list()
    
    for pair in unique_pairs:
        # Filter events for this pair
        df_sub = df_events.filter(pl.col("pair") == pair)
        if df_sub.height == 0:
            continue
            
        # Get pair features
        if pair not in pair_features:
            continue
        feat_df = pair_features[pair]
        
        # Generate LAGS for this pair's features (1..30)
        # Doing this on the full history (feat_df) is efficient in Polars
        pct_change_exprs = []
        for lag in [1, 2, 3, 5, 8, 13, 21, 30]:
            # Z lag
            pct_change_exprs.append(pl.col("z").shift(lag).alias(f"z_lag_{lag}"))
            # Beta lag
            pct_change_exprs.append(pl.col("beta").shift(lag).alias(f"beta_lag_{lag}"))
            # Vol lag
            pct_change_exprs.append(pl.col("vol").shift(lag).alias(f"vol_lag_{lag}"))
            
        feat_df_lagged = feat_df.with_columns(pct_change_exprs)
        
        # Join Lags to Events
        # Join on Timestamp (Event Timestamp = Signal Bar Timestamp)
        # Note: Event timestamp is when signal occured. Feature timestamp matches.
        # Shift(1) means "Value of PREVIOUS bar".
        # If signal is at T, do we know Z(T)? Yes.
        # But Z(T) *is* the signal trigger.
        # So z_lag_1 is the Z-score 1 hour ago.
        
        df_joined = df_sub.join(feat_df_lagged, on="timestamp", how="left")
        
        # Join Market State (Cross-Sectional)
        # Join on Timestamp
        df_joined = df_joined.join(df_market_state, on="timestamp", how="left")
        
        enriched_dfs.append(df_joined)
        
    if not enriched_dfs:
        print("No enriched events.")
        return

    # Stack
    df_final = pl.concat(enriched_dfs)
    
    # Fill Nulls (if any)
    df_final = df_final.fill_null(0)
    
    # Save
    out_path = os.path.join(OUTPUT_DIR, "features_h1_wide.parquet")
    df_final.write_parquet(out_path)
    print(f"Saved {len(df_final)} enriched events to {out_path}")
    print(f"Feature Count: {len(df_final.columns)}")

if __name__ == "__main__":
    build_features()
