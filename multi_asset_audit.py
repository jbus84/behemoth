import polars as pl
import numpy as np
import os
from scipy.stats import spearmanr
import warnings
warnings.filterwarnings("ignore")

def run_multi_asset_audit():
    print(">>> 5M/15M MULTI-ASSET AUDIT (The Basket) <<<")
    
    repo = "/Users/danielfisher/repositories/behemoth"
    years = ["2023", "2024"]
    
    # 1. Load All Data (1m)
    def load_pair(pair_name, file_prefix):
        dfs = []
        for y in years:
            f = os.path.join(repo, f"{file_prefix}_dataset_1m_{y}.parquet")
            if os.path.exists(f):
                try:
                    d = pl.read_parquet(f)
                    # Helper to standardize column name to `pair_name`
                    cols = d.columns
                    target_col = None
                    candidates = [pair_name, pair_name.lower(), f"{pair_name}_mid", "close", "price"]
                    for c in candidates:
                        if c in cols:
                            target_col = c
                            break
                    if target_col:
                        d = d.select([
                            pl.col("timestamp"),
                            pl.col(target_col).alias(pair_name)
                        ])
                        dfs.append(d)
                except Exception as e:
                    print(f"Error loading {f}: {e}")
        if dfs:
            return pl.concat(dfs).sort("timestamp")
        return None

    print("Loading Data...")
    nsx = load_pair("NSXUSD", "graph")
    if nsx is None: nsx = load_pair("NSXUSD", "nsx")
    
    assets = {
        "EURUSD": "eurusd",
        "GBPUSD": "gbpusd",
        "USDJPY": "usdjpy",
        "XAUUSD": "xauusd", # Gold
        "USDCHF": "usdchf"  # Swissie
    }
    
    loaded_assets = {}
    for name, prefix in assets.items():
        df = load_pair(name, prefix)
        if df is not None:
            loaded_assets[name] = df
        else:
            print(f"  Warning: {name} data missing.")

    if nsx is None:
        print("CRITICAL: NSX Data Missing.")
        return

    # 2. Resample and Analyze (5m and 15m)
    timeframes = ["5m", "15m"]
    
    for tf in timeframes:
        print(f"\n=== TIMEFRAME: {tf} ===")
        
        # Resample NSX
        nsx_tf = nsx.group_by_dynamic("timestamp", every=tf, closed="right", label="right").agg([
            pl.col("NSXUSD").last().alias("NSXUSD")
        ]).sort("timestamp")
        
        # Calculate Volatility for Regime
        # Rolling Std Dev of returns. Window = 12 (1 Hour for 5m, 3 Hours for 15m is too slow?) 
        # Let's use 12 periods.
        nsx_tf = nsx_tf.with_columns(
            ((pl.col("NSXUSD") / pl.col("NSXUSD").shift(1) - 1) * 10000).alias("ret"),
        )
        nsx_tf = nsx_tf.with_columns(
            pl.col("ret").rolling_std(12).alias("vol"),
            ((pl.col("NSXUSD").shift(-1) / pl.col("NSXUSD") - 1) * 10000).alias("target_next")
        ).drop_nulls()

        # Define Regime Thresholds
        vol_vals = nsx_tf["vol"].to_numpy()
        d2 = np.percentile(vol_vals, 20)
        d8 = np.percentile(vol_vals, 80)
        print(f"  Vol Thresholds: Low < {d2:.4f} | High > {d8:.4f} bps")

        # Process Assets
        for name, df in loaded_assets.items():
            # Resample Asset
            asset_tf = df.group_by_dynamic("timestamp", every=tf, closed="right", label="right").agg([
                pl.col(name).last().alias(name)
            ]).sort("timestamp")
            
            # Calculate Features
            asset_tf = asset_tf.with_columns(
                ((pl.col(name) / pl.col(name).shift(1) - 1) * 10000).alias(f"{name}_ret")
            ).drop_nulls()
            
            # Join
            joined = nsx_tf.join(asset_tf, on="timestamp", how="inner")
            
            # Filter Regimes
            low_vol = joined.filter(pl.col("vol") < d2)
            high_vol = joined.filter(pl.col("vol") > d8)
            
            # Correlation
            feat = f"{name}_ret"
            target = "target_next"
            
            if len(joined) > 100:
                c_all, _ = spearmanr(joined[feat].to_numpy(), joined[target].to_numpy())
                c_lo, _ = spearmanr(low_vol[feat].to_numpy(), low_vol[target].to_numpy())
                c_hi, _ = spearmanr(high_vol[feat].to_numpy(), high_vol[target].to_numpy())
                
                print(f"  {name:<10}: All={c_all:.4f} | LoVol={c_lo:.4f} | HiVol={c_hi:.4f}")
            else:
                print(f"  {name:<10}: Insufficient Data")

        # --- COMBINED BASKET SCORE ---
        print(f"\n  --- Composite Basket Audit ({tf}) ---")
        # Need to join ALL assets
        full = nsx_tf
        # Signs based on previous run: EUR(+), GBP(+), XAU(+), JPY(-), CHF(-)
        # We will sum them: Score = EUR + GBP + XAU - JPY - CHF
        
        valid_baskets = []
        for name in ["EURUSD", "GBPUSD", "XAUUSD", "USDJPY", "USDCHF"]:
            if name in loaded_assets:
                # Get the asset return column
                # Re-do specific resample to ensure cleanliness
                a = loaded_assets[name].group_by_dynamic("timestamp", every=tf, closed="right", label="right").agg([
                    pl.col(name).last().alias(name)
                ]).sort("timestamp")
                a = a.with_columns(((pl.col(name)/pl.col(name).shift(1)-1)*10000).alias(f"{name}_ret")).drop_nulls()
                
                full = full.join(a.select(["timestamp", f"{name}_ret"]), on="timestamp", how="left")
                valid_baskets.append(name)
        
        full = full.drop_nulls()
        
        if len(valid_baskets) == 5:
            # Construct Signal
            full = full.with_columns(
                (pl.col("EURUSD_ret") + pl.col("GBPUSD_ret") + pl.col("XAUUSD_ret") - pl.col("USDJPY_ret") - pl.col("USDCHF_ret")).alias("basket_score")
            )
            
            # Filter High Vol
            high_vol_basket = full.filter(pl.col("vol") > d8)
            
            c_b, p_b = spearmanr(full["basket_score"].to_numpy(), full["target_next"].to_numpy())
            c_b_hv, p_b_hv = spearmanr(high_vol_basket["basket_score"].to_numpy(), high_vol_basket["target_next"].to_numpy())
            
            print(f"  Basket Score: All={c_b:.4f} | HiVol={c_b_hv:.4f} (Samples: {len(high_vol_basket)})")
            
            if abs(c_b_hv) > 0.05:
                print("  >>> ALPHA DETECTED: Basket Signal > 0.05 <<<")
        else:
            print("  Skipping Basket: Missing Assets.")

if __name__ == "__main__":
    run_multi_asset_audit()
