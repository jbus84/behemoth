
import polars as pl
import numpy as np
import os
from kalman_filter import KalmanFilterReg

DATA_DIR_H4 = "data/global_4h"
DATA_DIR_H1 = "data/global_1h"

# Candidate Universe
PAIRS = [
    # Tier 1
    ("FRXEUR", "BCOUSD", "CAC/Oil"),
    ("XAUUSD", "BCOUSD", "Gold/Oil"),
    ("USDCHF", "GRXEUR", "Swiss/DAX"),
    ("FRXEUR", "EURGBP", "CAC/EURGBP"),
    # Tier 2
    ("UDXUSD", "GRXEUR", "USD/DAX"),
    ("FRXEUR", "USDJPY", "CAC/Yen"),
    ("EURUSD", "EURJPY", "Euro/Yen"),
    ("BCOUSD", "XAGUSD", "Oil/Silver"),
    # Tier 3
    ("XAUUSD", "NSXUSD", "Gold/Nasdaq"),
    ("USDCHF", "AUDUSD", "Swiss/Aussie"),
    ("EURUSD", "AUDUSD", "Euro/Aussie"),
]

def audit_robustness():
    print("--- ROBUSTNESS SCAN (2018-2025) [H4] ---")
    print(f"Goal: Find pairs profitable in > 50% of years and Net Positive.")
    
    print("\n| Pair | Total PnL | Win Yrs | 2018 | 2020 | 2022 | 2025 | Consistency |")
    print("|---|---|---|---|---|---|---|---|")
    
    for y_sym, x_sym, label in PAIRS:
        # Check files
        p_y = os.path.join(DATA_DIR_H4, f"{y_sym}_4h.parquet")
        p_x = os.path.join(DATA_DIR_H4, f"{x_sym}_4h.parquet")
        if not os.path.exists(p_y) or not os.path.exists(p_x):
            continue
            
        try:
            df = pl.read_parquet(p_y).rename({f"close_{y_sym}": "Y"}).join(
                pl.read_parquet(p_x).rename({f"close_{x_sym}": "X"}), on="timestamp", how="inner").sort("timestamp")
            
            pnl_map = get_yearly_pnl(df)
            
            years = range(2018, 2026)
            total = sum(pnl_map.values())
            wins = sum(1 for y in years if pnl_map.get(y, 0) > 0)
            
            p18 = pnl_map.get(2018, 0)
            p20 = pnl_map.get(2020, 0)
            p22 = pnl_map.get(2022, 0)
            p25 = pnl_map.get(2025, 0)
            
            # Rating
            rating = "⭐⭐⭐" if wins >= 6 and total > 1000 else \
                     "⭐⭐" if wins >= 5 and total > 0 else \
                     "⭐" if wins >= 4 and total > 0 else "❌"
            
            print(f"| {label} | {total:.0f} | {wins}/8 | {p18:.0f} | {p20:.0f} | {p22:.0f} | {p25:.0f} | {rating} |")
            
        except Exception as e:
            # print(f"Error {label}: {e}")
            pass

def get_yearly_pnl(df):
    y_log = np.log(df["Y"].to_numpy())
    x_log = np.log(df["X"].to_numpy())
    ts = df["timestamp"].to_numpy()
    
    kf = KalmanFilterReg(Q=1e-5, R=1e-3)
    betas, errors = [], []
    y_win, x_win = [], []
    
    # Warmup
    for i in range(len(y_log)):
        y_win.append(y_log[i]); x_win.append(x_log[i])
        if len(y_win)>500: y_win.pop(0); x_win.pop(0)
        if len(y_win) < 10: mu_y, mu_x = y_log[i], x_log[i]
        else: mu_y, mu_x = np.mean(y_win), np.mean(x_win)
        b, _ = kf.update(x_log[i]-mu_x, y_log[i]-mu_y)
        betas.append(b)
        errors.append((y_log[i]-mu_y) - b*(x_log[i]-mu_x))
        
    res = {y: 0.0 for y in range(2018, 2026)}
    in_pos = 0
    entry_beta, entry_y, entry_x = 0., 0., 0.
    cost_bps = 9.0
    
    # H4 Settings
    THRESH = 1.5
    STOP = 3.5
    
    for i in range(500, len(y_log)):
        dt = ts[i]
        yr = dt.astype('datetime64[Y]').astype(int) + 1970
        if yr < 2018 or yr > 2025: continue
        
        window = errors[i-500:i]
        mu, std = np.mean(window), np.std(window)
        if std < 1e-6: continue
        z = (errors[i] - mu) / std
        
        pnl = 0.0
        
        if in_pos == 0:
            if z > THRESH: in_pos = -1; entry_beta=betas[i-1]; entry_y=y_log[i]; entry_x=x_log[i]
            elif z < -THRESH: in_pos = 1; entry_beta=betas[i-1]; entry_y=y_log[i]; entry_x=x_log[i]
        elif in_pos == 1:
            if z > 0.0 or z < -STOP:
                gross = (y_log[i]-entry_y) - entry_beta*(x_log[i]-entry_x)
                pnl = gross * 10000 - cost_bps
                in_pos = 0
        elif in_pos == -1:
            if z < 0.0 or z > STOP:
                gross = -(y_log[i]-entry_y) + entry_beta*(x_log[i]-entry_x)
                pnl = gross * 10000 - cost_bps
                in_pos = 0
                
        if pnl != 0.0: res[yr] += pnl
        
    return res

if __name__ == "__main__":
    audit_robustness()
