
import polars as pl
import numpy as np
import os
import sys
sys.path.append(os.path.join(os.getcwd(), 'scripts'))
from kalman_filter import KalmanFilterReg

DATA_DIR = "data/global_15m"

def backtest_2024_whip_tank():
    print("--- 2024 WHIP & TANK TEST ---")
    print("Regime: GBP is High Vol (Whip). EUR is Low Vol (Tank).")
    print("Hypothesis: GBP Reversion and EUR Momentum should outperform the inverse.")
    
    # Load Data
    p_eur = os.path.join(DATA_DIR, "EURUSD_15m.parquet")
    p_gbp = os.path.join(DATA_DIR, "GBPUSD_15m.parquet")
    
    df_eur = pl.read_parquet(p_eur).rename({"close_EURUSD": "X"})
    df_gbp = pl.read_parquet(p_gbp).rename({"close_GBPUSD": "Y"})
    
    df = df_eur.join(df_gbp, on="timestamp", how="inner").sort("timestamp")
    df = df.filter(pl.col("timestamp").dt.year() == 2024)
    
    y = np.log(df["Y"].to_numpy()) # GBP
    x = np.log(df["X"].to_numpy()) # EUR
    
    kf = KalmanFilterReg(Q=1e-5, R=1e-3)
    betas, errors = [], []
    
    for i in range(len(y)):
        if i < 10: mu_y, mu_x = y[i], x[i]
        else: mu_y, mu_x = np.mean(y[max(0,i-500):i]), np.mean(x[max(0,i-500):i])
        b, _ = kf.update(x[i]-mu_x, y[i]-mu_y)
        betas.append(b)
        errors.append((y[i]-mu_y) - b*(x[i]-mu_x))
        
    thresh = 2.0
    stop_level = 3.5
    COST_BPS_GBP = 1.6
    COST_BPS_EUR = 1.0
    
    # 1. GBP Reversion (Trading the Whip)
    pnl_gbp_rev = 0.0
    trades_gbp = 0
    in_pos_gbp = 0
    ep_gbp = 0.0
    
    # 2. EUR Momentum (Trading the Tank)
    pnl_eur_mom = 0.0
    trades_eur = 0
    in_pos_eur = 0
    ep_eur = 0.0
    
    for i in range(500, len(y)):
        window = errors[i-500:i]
        mu, std = np.mean(window), np.std(window)
        if std < 1e-6: continue
        z = (errors[i] - mu) / std
        
        # --- GBP STRATEGY (Reversion) ---
        if in_pos_gbp == 0:
            if z > thresh: in_pos_gbp = -1; ep_gbp = y[i] # Sell GBP (Fade High)
            elif z < -thresh: in_pos_gbp = 1; ep_gbp = y[i] # Buy GBP (Fade Low)
        elif in_pos_gbp == 1:
            if z > 0: pnl_gbp_rev += (y[i]-ep_gbp)*10000 - COST_BPS_GBP; in_pos_gbp = 0; trades_gbp += 1
            elif z < -stop_level: pnl_gbp_rev += (y[i]-ep_gbp)*10000 - COST_BPS_GBP; in_pos_gbp = 0; trades_gbp += 1
        elif in_pos_gbp == -1:
            if z < 0: pnl_gbp_rev += -(y[i]-ep_gbp)*10000 - COST_BPS_GBP; in_pos_gbp = 0; trades_gbp += 1
            elif z > stop_level: pnl_gbp_rev += -(y[i]-ep_gbp)*10000 - COST_BPS_GBP; in_pos_gbp = 0; trades_gbp += 1
            
        # --- EUR STRATEGY (Momentum) ---
        # Note: Z is defined as GBP - beta*EUR.
        # So Z > 0 means GBP High / EUR Low.
        # EUR Momentum means: If Z > 0 (EUR Low), we bet EUR goes LOWER? 
        # No, Momentum means following the Move.
        # If Z > 0, it means the Spread widened.
        # If EUR is the Tank (Low Vol), we assume it DRIFTS AWAY from the relationship?
        # Or does Momentum mean "Follow the Spread"?
        # In GBP Momentum (2025), Z > 0 (GBP High) -> Buy GBP.
        # Here Z > 0 (EUR Low) -> Sell EUR?
        # Yes. Betting on Divergence.
        
        if in_pos_eur == 0:
            if z > thresh: in_pos_eur = -1; ep_eur = x[i] # Z High -> EUR Low. Sell EUR.
            elif z < -thresh: in_pos_eur = 1; ep_eur = x[i] # Z Low -> EUR High. Buy EUR.
        # Exit logic: Same as Momentum
        elif in_pos_eur == 1: # Long EUR
             if z > 0: # Reverted (Momentum Failed)
                 # We bought EUR (Z Low). Z went High.
                 # Loss.
                 gross = x[i] - ep_eur
                 pnl_eur_mom += (-gross * 10000) - COST_BPS_EUR # Inverted PnL Logic
                 # Wait, explicit momentum PnL is simpler:
                 # We bet on Continuation.
                 # If Reversion happens (Z crosses 0), we take the loss.
                 # PnL = (Exit - Entry).
                 in_pos_eur = 0; trades_eur += 1
             elif z < -stop_level: # Trend Extension (Win)
                 # We bought EUR at Z=-2. Z went to -3.5.
                 # EUR went UP? Or GBP went DOWN?
                 # If Z went lower, Spread went lower.
                 # Spread = GBP - EUR.
                 # Spread lower means EUR Higher (relative).
                 # So Long EUR wins.
                 # PnL = (x[i] - ep_eur) * 10000 - COST
                 in_pos_eur = 0; trades_eur += 1
                 # Wait, simply calculate Standard Reversion PnL and invert it?
                 # Standard Reversion on EUR:
                 # Z Low -> Sell EUR (Fade).
                 # Correct. Standard is Fade.
                 # PnL_Mom = -1 * PnL_Rev - Cost.
                 pass
        
        # Actually, let's just calculate Standard Reversion PnL for EUR and calculate Momentum PnL as (-Gross - Cost).
        # We did this in previous scripts.
        pass

    # Re-using the explicit loop structure from previous scripts is safer.
    # I will just print the logic I deduced.
    print("Logic: Calculating Standard Reversion first, then Inverting for Momentum.")
    
    # GBP Reversion (Standard)
    # We already have pnl_gbp_rev calculated above.
    
    # EUR Inverted (Momentum)
    pnl_eur_std = 0.0
    pnl_eur_mom = 0.0
    trades_eur = 0
    in_pos_eur = 0
    ep_eur = 0.0
    
    for i in range(500, len(y)):
        window = errors[i-500:i]
        mu, std = np.mean(window), np.std(window)
        if std < 1e-6: continue
        z = (errors[i] - mu) / std
        
        if in_pos_eur == 0:
            if z > thresh: in_pos_eur = 1; ep_eur = x[i] # Standard: Z High -> Buy EUR (Fade)
            elif z < -thresh: in_pos_eur = -1; ep_eur = x[i] # Standard: Z Low -> Sell EUR (Fade)
            
        elif in_pos_eur == 1: # Long EUR
            if z < 0: # Reverted
                pnl = (x[i]-ep_eur)*10000 - COST_BPS_EUR
                pnl_mom = (-(x[i]-ep_eur)*10000) - COST_BPS_EUR
                pnl_eur_std += pnl; pnl_eur_mom += pnl_mom
                in_pos_eur = 0; trades_eur += 1
            elif z > stop_level: # Stop
                pnl = (x[i]-ep_eur)*10000 - COST_BPS_EUR
                pnl_mom = (-(x[i]-ep_eur)*10000) - COST_BPS_EUR
                pnl_eur_std += pnl; pnl_eur_mom += pnl_mom
                in_pos_eur = 0; trades_eur += 1

        elif in_pos_eur == -1: # Short EUR
            if z > 0: # Reverted
                pnl = -(x[i]-ep_eur)*10000 - COST_BPS_EUR
                pnl_mom = -(-(x[i]-ep_eur)*10000) - COST_BPS_EUR
                pnl_eur_std += pnl; pnl_eur_mom += pnl_mom
                in_pos_eur = 0; trades_eur += 1
            elif z < -stop_level: # Stop
                pnl = -(x[i]-ep_eur)*10000 - COST_BPS_EUR
                pnl_mom = -(-(x[i]-ep_eur)*10000) - COST_BPS_EUR
                pnl_eur_std += pnl; pnl_eur_mom += pnl_mom
                in_pos_eur = 0; trades_eur += 1
                
    print(f"| Strategy | 2024 PnL (bps) | Trades |")
    print("|---|---|---|")
    print(f"| GBP Reversion (Whip) | {pnl_gbp_rev:.1f} | {trades_gbp} |")
    print(f"| EUR Momentum (Tank)  | {pnl_eur_mom:.1f} | {trades_eur} |")
    print(f"| (Ref) GBP Momentum   | -208.2 (Known) | |")
    print(f"| (Ref) EUR Reversion  | -414.4 (Known) | |")

if __name__ == "__main__":
    backtest_2024_whip_tank()
