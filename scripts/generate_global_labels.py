
import polars as pl
import numpy as np
import os
import sys
sys.path.append(os.path.join(os.getcwd(), 'scripts'))
from kalman_filter import KalmanFilterReg

DATA_DIR = "data/global_15m"

def get_data(file_x, file_y, col_x, col_y):
    try:
        p_x = os.path.join(DATA_DIR, file_x)
        p_y = os.path.join(DATA_DIR, file_y)
        df_x = pl.read_parquet(p_x).rename({col_x: "X"})
        df_y = pl.read_parquet(p_y).rename({col_y: "Y"})
        df = df_x.join(df_y, on="timestamp", how="inner").sort("timestamp")
        df = df.filter(pl.col("timestamp").dt.year().is_in(list(range(2018, 2026))))
        return df
    except Exception as e:
        print(f"Error loading {file_x}/{file_y}: {e}")
        return None

def run_labeller():
    print("--- GLOBAL META MODEL LABELLING SCAN ---")
    
    pairs = [
        ("EUR/GBP", "EURUSD_15m.parquet", "GBPUSD_15m.parquet", "close_EURUSD", "close_GBPUSD"),
        ("Gold/Oil", "BCOUSD_15m.parquet", "XAUUSD_15m.parquet", "close_BCOUSD", "close_XAUUSD"), # X=Oil, Y=Gold
        ("Oil/Silver", "BCOUSD_15m.parquet", "XAGUSD_15m.parquet", "close_BCOUSD", "close_XAGUSD"), # X=Oil, Y=Silver
        ("AUD/NZD", "NZDUSD_15m.parquet", "AUDUSD_15m.parquet", "close_NZDUSD", "close_AUDUSD"), # X=NZD, Y=AUD
        ("CAC/NZD", "NZDUSD_15m.parquet", "FRXEUR_15m.parquet", "close_NZDUSD", "close_FRXEUR") # X=NZD, Y=CAC
    ]
    
    thresh_scan = [1.0, 1.25, 1.5, 2.0]
    results = {t: 0 for t in thresh_scan}
    pair_counts = {p[0]: {t: 0 for t in thresh_scan} for p in pairs}
    
    kf = KalmanFilterReg(Q=1e-5, R=1e-3)
    
    for name, fx, fy, cx, cy in pairs:
        print(f"Scanning {name}...")
        df = get_data(fx, fy, cx, cy)
        if df is None: continue
        
        y = np.log(df["Y"].to_numpy())
        x = np.log(df["X"].to_numpy())
        
        errors = []
        betas = []
        
        # Kalman
        for i in range(len(y)):
            if i < 10: mu_y, mu_x = y[i], x[i]
            else: mu_y, mu_x = np.mean(y[max(0,i-500):i]), np.mean(x[max(0,i-500):i])
            b, _ = kf.update(x[i]-mu_x, y[i]-mu_y)
            betas.append(b)
            errors.append((y[i]-mu_y) - b*(x[i]-mu_x))
            
        # Count Events
        for i in range(500, len(y)):
            beta = betas[i]
            window = errors[i-500:i]
            mu, std = np.mean(window), np.std(window)
            if std < 1e-6: continue
            z = (errors[i] - mu) / std
            
            # Simple Count (Any crossing of threshold)
            # To avoid duplicate counts for the same event, we only count entry triggers (crossing from below/above)
            # Logic: If abs(z) > thresh AND abs(prev_z) < thresh.
            
            prev_z = (errors[i-1] - mu) / std # approx prev z
            
            for t in thresh_scan:
                # Trigger Condition: Crosses OUT set threshold
                triggered = False
                if z > t and prev_z <= t: triggered = True
                if z < -t and prev_z >= -t: triggered = True
                
                if triggered:
                    results[t] += 1
                    pair_counts[name][t] += 1
                    
    print("\n--- GLOBAL AGGREGATE RESULTS (2 YEARS) ---")
    print("| Threshold | Total Events | Events/Year | ML Viability |")
    print("|---|---|---|---|")
    for t in thresh_scan:
        total = results[t]
        per_year = total / 2
        viability = "High" if per_year > 1000 else "Medium" if per_year > 500 else "Low"
        print(f"| {t} | {total} | {per_year:.0f} | {viability} |")
        
    print("\n--- BREAKDOWN BY PAIR (Z=1.5) ---")
    for name in pair_counts:
        print(f"{name}: {pair_counts[name][1.5]} events")

if __name__ == "__main__":
    run_labeller()
