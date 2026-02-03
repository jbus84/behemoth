
import polars as pl
import numpy as np
import os
from kalman_filter import KalmanFilterReg
from datetime import datetime, timezone

DATA_DIR = "data/global_4h"

PAIRS = [
    ("FRXEUR", "BCOUSD", 9.0, "CAC/Oil"),
    ("XAUUSD", "BCOUSD", 10.0, "Gold/Oil"),
    ("USDCHF", "GRXEUR", 3.0, "Swiss/DAX"),
    ("FRXEUR", "EURGBP", 2.5, "CAC/EURGBP"),
    ("UDXUSD", "GRXEUR", 5.0, "USD/DAX"),
    ("AUDUSD", "USDCAD", 2.0, "AUD/CAD (Control)"),
]

def run_year(y_log, x_log, year, cost_bps):
    kf = KalmanFilterReg(Q=1e-5, R=1e-3)
    betas, errors = [], []
    y_win, x_win = [], []
    
    # Run Filter Full History (No resets to maintain state)
    for i in range(len(y_log)):
        y_win.append(y_log[i]); x_win.append(x_log[i])
        if len(y_win)>500: y_win.pop(0); x_win.pop(0)
        
        if len(y_win) < 10: mu_y, mu_x = y_log[i], x_log[i]
        else: mu_y, mu_x = np.mean(y_win), np.mean(x_win)
        
        b, _ = kf.update(x_log[i]-mu_x, y_log[i]-mu_y)
        betas.append(b)
        errors.append((y_log[i]-mu_y) - b*(x_log[i]-mu_x)) # Re-calc error

    # Evaluation
    # We need timestamp matching to segment by year
    # But for simplicity, we passed log arrays. We need to pass dataframe instead.
    pass

def run_pair_long_term(y_sym, x_sym, cost_bps, label):
    p_y = os.path.join(DATA_DIR, f"{y_sym}_4h.parquet")
    p_x = os.path.join(DATA_DIR, f"{x_sym}_4h.parquet")
    
    try:
        df_y = pl.read_parquet(p_y).rename({f"close_{y_sym}": "Y"})
        df_x = pl.read_parquet(p_x).rename({f"close_{x_sym}": "X"})
        
        df = df_y.join(df_x, on="timestamp", how="inner").sort("timestamp")
        
        y_log = np.log(df["Y"].to_numpy())
        x_log = np.log(df["X"].to_numpy())
        ts = df["timestamp"].to_numpy()
        
        # 1. Run Kalman on Full History
        kf = KalmanFilterReg(Q=1e-5, R=1e-3)
        betas, errors = [], []
        y_win, x_win = [], []
        
        for i in range(len(y_log)):
            y_win.append(y_log[i]); x_win.append(x_log[i])
            if len(y_win)>500: y_win.pop(0); x_win.pop(0)
            if len(y_win) < 10: mu_y, mu_x = y_log[i], x_log[i]
            else: mu_y, mu_x = np.mean(y_win), np.mean(x_win)
            b, _ = kf.update(x_log[i]-mu_x, y_log[i]-mu_y)
            betas.append(b)
            # Use centered error
            errors.append((y_log[i]-mu_y) - b*(x_log[i]-mu_x))
            
        # 2. Slice by Year
        years = range(2018, 2026)
        results = {}
        
        in_pos = 0
        entry_beta, entry_y, entry_x = 0., 0., 0.
        
        # We process sequentially to maintain position state, but bucket PnL by year
        current_year_pnl = 0.0
        
        # Warmup 500
        for i in range(500, len(y_log)):
            dt = ts[i] # numpy datetime64
            yr = dt.astype('datetime64[Y]').astype(int) + 1970 
            
            # Volatility Filter
            if i > 600:
                vol_window = np.diff(y_log[i-100:i])
                vol = np.std(vol_window) * 1000
                
                # Correlation Filter (Returns, Window 50)
                # Need consistent length
                ret_y = np.diff(y_log[i-50:i])
                ret_x = np.diff(x_log[i-50:i])
                if np.std(ret_x) > 1e-9 and np.std(ret_y) > 1e-9:
                   corr = np.corrcoef(ret_x, ret_y)[0,1]
                else:
                   corr = 0.0
            else:
                vol = 0
                corr = 0
            
            # Z-Score
            window = errors[i-500:i]
            mu, std = np.mean(window), np.std(window)
            if std < 1e-6: continue
            z = (errors[i] - mu) / std
            beta = betas[i-1]
            
            pnl = 0.0
            
            # COMBINED FILTER: Vol < 2.5 OR Correlation < -0.25 (Inverse Shock)
            if vol < 2.5 or corr < -0.25:
                # Forces Exit.
                if in_pos != 0:
                     if in_pos == 1:
                         gross = (y_log[i]-entry_y) - entry_beta*(x_log[i]-entry_x)
                     else:
                         gross = -(y_log[i]-entry_y) + entry_beta*(x_log[i]-entry_x)
                     pnl = gross * 10000 - cost_bps
                     in_pos = 0
                else:
                    pass
            else:
                if in_pos == 0:
                    if z > 1.5: in_pos = -1; entry_beta=beta; entry_y=y_log[i]; entry_x=x_log[i]
                    elif z < -1.5: in_pos = 1; entry_beta=beta; entry_y=y_log[i]; entry_x=x_log[i]
                elif in_pos == 1:
                    if z > 0.0 or z < -2.0:
                        gross = (y_log[i]-entry_y) - entry_beta*(x_log[i]-entry_x)
                        pnl = gross * 10000 - cost_bps
                        in_pos = 0
                elif in_pos == -1:
                    if z < 0.0 or z > 2.0:
                        gross = -(y_log[i]-entry_y) + entry_beta*(x_log[i]-entry_x)
                        pnl = gross * 10000 - cost_bps
                        in_pos = 0
            
            if yr not in results: results[yr] = []
            if pnl != 0.0: results[yr].append(pnl)

        # Print Row
        print(f"| {label} | ", end="")
        total_pnl = 0
        for yr in years:
            if yr in results:
                yr_pnl = sum(results[yr])
                total_pnl += yr_pnl
                print(f"{yr_pnl:.0f} | ", end="")
            else:
                print("0 | ", end="")
        
        avg_annual = total_pnl / len(years)
        print(f"**{total_pnl:.0f}** | **{avg_annual:.0f}** |")

    except Exception as e:
        print(f"Error {label}: {e}")

def audit_long_term():
    print("--- 8-YEAR AUDIT (FILTER: Vol > 2.5 AND Corr > -0.25) ---")
    print("| Pair | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | **Total** | **Avg/Yr** |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    
    for y, x, c, l in PAIRS:
        run_pair_long_term(y, x, c, l)

if __name__ == "__main__":
    audit_long_term()
