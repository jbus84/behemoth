"""
Particle Filter Experiment (H1)
Comparing Kalman Filter vs Particle Filter for Beta Estimation on Cointegrated Pairs.
Target: SPX/DAX (High performing index pair).
"""

import numpy as np
import pandas as pd
import polars as pl
import matplotlib.pyplot as plt
from scipy.stats import t as t_dist
from scipy.stats import norm
import sys
import os
from pathlib import Path

# Add project root
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from behemoth.core.kalman import KalmanFilterReg
from behemoth.core.zscore import compute_z_scores

# --- PARTICLE FILTER IMPLEMENTATION ---

class ParticleFilterReg:
    """
    Bootstrap Particle Filter for regression: y = beta * x + noise
    State: beta (scalar)
    """
    def __init__(self, num_particles=1000, R=1e-3, Q=1e-5, likelihood_dist="normal", df=3):
        self.N = num_particles
        self.R = R
        self.Q = Q
        self.particles = np.zeros(self.N) # Betas
        self.weights = np.ones(self.N) / self.N
        self.dist = likelihood_dist
        self.df = df # Degrees of freedom for t-dist
        
    def update(self, x, y):
        """
        SIR (Sampling Importance Resampling) Step
        """
        # 1. Predict (Propagation)
        # Random walk evolution: beta_t = beta_{t-1} + noise
        process_noise = np.random.normal(0, np.sqrt(self.Q), self.N)
        self.particles += process_noise
        
        # 2. Update (Weighting)
        # Likelihood p(y | x, beta)
        y_preds = self.particles * x
        residuals = y - y_preds
        
        if self.dist == "normal":
            # Gaussian Likelihood
            # L = exp(-0.5 * res^2 / R)
            # We can ignore constants for weights normalization
            log_likelihoods = -0.5 * (residuals**2) / self.R
            # Numerical stability: shift log-likelihoods
            max_log = np.max(log_likelihoods)
            likelihoods = np.exp(log_likelihoods - max_log)
            # likelihoods = norm.pdf(residuals, 0, np.sqrt(self.R))
            
        elif self.dist == "t":
            # Student-t Likelihood (Heavy tails)
            # Scale R needs to be converted to scale parameter for t-dist
            # var = scale^2 * df / (df-2) => scale = sqrt(var * (df-2)/df)
            # For simplicity, treat sqrt(R) as scale
            scale = np.sqrt(self.R)
            likelihoods = t_dist.pdf(residuals, self.df, loc=0, scale=scale)
            
        self.weights *= likelihoods
        self.weights += 1.e-300 # Avoid zero
        self.weights /= np.sum(self.weights)
        
        # 3. Estimation (Mean)
        beta_est = np.sum(self.particles * self.weights)
        res_est = y - beta_est * x
        
        # 4. Resample
        # Effective sample size
        N_eff = 1.0 / np.sum(self.weights**2)
        if N_eff < self.N / 2:
            self.resample()
            
        return beta_est, res_est
    
    def resample(self):
        cumulative_sum = np.cumsum(self.weights)
        cumulative_sum[-1] = 1.0 # Ensure last is 1
        indexes = np.searchsorted(cumulative_sum, np.random.random(self.N))
        
        self.particles = self.particles[indexes]
        self.weights = np.ones(self.N) / self.N

# --- PIPELINE ---

def load_data(pair_name="SPX/DAX"):
    # Load H1 Pair Data (re-using logic from build_events_h1)
    # We need the source parquets.
    # We'll use the CSV if available to avoid raw data loading complexity?
    # No, CSV has static z-scores. We need to re-calculate beta.
    # We need Y and X raw logs.
    
    # Let's mock load or assume paths.
    # Mapping from build_events_h1:
    # SPX/DAX -> SPXUSD_1h.parquet (Y), GRXEUR_1h.parquet (X)
    
    data_dir = Path("data/global_1h")
    y_path = data_dir / "SPXUSD_1h.parquet"
    x_path = data_dir / "GRXEUR_1h.parquet"
    
    if not y_path.exists() or not x_path.exists():
        print("Data files not found.")
        return None, None, None
        
    df_y = pl.read_parquet(y_path).rename({"close": "Y"})
    df_x = pl.read_parquet(x_path).rename({"close": "X"})
    
    # Join on timestamp
    df = df_y.join(df_x, on="timestamp", how="inner").sort("timestamp")
    
    y = np.log(df["Y"].to_numpy())
    x = np.log(df["X"].to_numpy())
    ts = df["timestamp"].to_numpy()
    
    return y, x, ts

def run_experiment():
    print("--- Loading Data for SPX/DAX ---")
    y, x, ts = load_data()
    if y is None: return
    
    print(f"Loaded {len(y)} bars.")
    
    # Pre-processing (Rolling Center)
    window = 750
    y_s = pd.Series(y)
    x_s = pd.Series(x)
    
    mu_y = y_s.rolling(window=window, min_periods=1).mean().shift(1).to_numpy().copy()
    mu_x = x_s.rolling(window=window, min_periods=1).mean().shift(1).to_numpy().copy()
    
    # Fill startup NaNs
    mu_y[:window] = y[:window] # Or 0? Kalman implementation uses y[i] if warmup
    mu_x[:window] = x[:window]
    mu_y = np.nan_to_num(mu_y, nan=y[0]) 
    mu_x = np.nan_to_num(mu_x, nan=x[0])
    
    y_centered = y - mu_y
    x_centered = x - mu_x
    
    # --- 1. Kalman Filter (Baseline) ---
    print("\nRunning Kalman Filter...")
    kf = KalmanFilterReg(Q=1e-5, R=1e-3)
    kf_betas = []
    kf_errors = []
    
    for i in range(len(y)):
        b, res = kf.update(x_centered[i], y_centered[i])
        kf_betas.append(b)
        kf_errors.append(res)
        
    kf_z = compute_z_scores(np.array(kf_errors), window=window)
    
    # --- 2. Particle Filter (Student-t) ---
    print("Running Particle Filter (T-Distribution)...")
    pf = ParticleFilterReg(num_particles=500, Q=1e-5, R=1e-3, likelihood_dist="t", df=3)
    pf_betas = []
    pf_errors = []
    
    for i in range(len(y)):
        if i % 5000 == 0: print(f"  Step {i}/{len(y)}")
        b, res = pf.update(x_centered[i], y_centered[i])
        pf_betas.append(b)
        pf_errors.append(res)
        
    pf_z = compute_z_scores(np.array(pf_errors), window=window)
    
    # --- Comparison ---
    df_res = pd.DataFrame({
        "ts": ts,
        "kf_beta": kf_betas,
        "pf_beta": pf_betas,
        "kf_z": kf_z,
        "pf_z": pf_z
    })
    
    # Simple Trading Simulation (Vectorized)
    # Long if Z < -1.5, Short if Z > 1.5. Exit at 0.
    thresh = 1.5
    
    def sim_pnl(z_scores, name):
        pnl = []
        pos = 0 # -1, 0, 1
        entry_price = 0
        
        # Simplified PnL (Z-score mean reversion proxy)
        # Actually need PnL based on y and x prices.
        # Approximation: Profit ~ -pos * delta(spread)
        # spread = y - beta*x. 
        # delta(spread) ~ spread_t - spread_{t-1}
        # better: use y and x returns.
        
        # Let's just count signal quality (Win Rate of entries)
        # Or simple simulation:
        # Enter when |Z| > 1.5. Exit when Z crosses 0.
        
        count = 0
        wins = 0
        total_ret = 0
        
        in_trade = False
        entry_idx = 0
        direction = 0
        
        for i in range(1000, len(z_scores)):
            z = z_scores[i]
            
            if not in_trade:
                # MOMENTUM LOGIC (Follow the trend)
                if z > thresh:
                    in_trade = True
                    direction = 1 # Long Spread (Betting on divergence increasing)
                    entry_idx = i
                elif z < -thresh:
                    in_trade = True
                    direction = -1 # Short Spread (Betting on divergence increasing)
                    entry_idx = i
            else:
                # Exit condition: Cross Zero (Trend reversal?) or Stop (huge win?)
                
                exit_signal = False
                
                # Cross Zero (Loss of trend / Mean Reversion)
                # For Momentum, if Z returns to 0, the trend is dead.
                if (direction == 1 and z < 0) or (direction == -1 and z > 0):
                    exit_signal = True
                    
                if exit_signal:
                    # Calculate PnL
                    # PnL approx = direction * (Spread_exit - Spread_entry)
                    # Spread = y - beta*x
                    # We need realized spread values.
                    # Let's use the error term (residual) as proxy for spread mean deviation
                    # Entry Residual ~ Z_entry * std
                    # Exit Residual ~ Z_exit * std
                    # This is rough but indicative.
                    
                    # Alternatively, calculating from Y and X logs:
                    # pnl = direction * ( (y[i]-y[entry]) - beta * (x[i]-x[entry]) )
                    # Use current beta or entry beta? Usually hedge ratio fixed at entry.
                    b = kf_betas[entry_idx] if name=="KF" else pf_betas[entry_idx]
                    
                    ret_y = y[i] - y[entry_idx]
                    ret_x = x[i] - x[entry_idx]
                    
                    # Profit = dir * (RetY - Beta * RetX)
                    trade_pnl = direction * (ret_y - b * ret_x) 
                    
                    if trade_pnl > 0: wins += 1
                    total_ret += trade_pnl
                    count += 1
                    in_trade = False
                    
        return count, wins, total_ret * 10000 # bps
        
    print("\n--- RESULTS ---")
    k_tr, k_w, k_pnl = sim_pnl(kf_z, "KF")
    p_tr, p_w, p_pnl = sim_pnl(pf_z, "PF")
    
    print(f"Kalman Filter: Trades={k_tr}, Wins={k_w} ({k_w/k_tr:.1%}%), PnL={k_pnl:.0f} bps")
    print(f"Particle Filter: Trades={p_tr}, Wins={p_w} ({p_w/p_tr:.1%}%), PnL={p_pnl:.0f} bps")
    
    # Correlation of betas
    beta_corr = np.corrcoef(kf_betas, pf_betas)[0,1]
    print(f"Beta Correlation: {beta_corr:.4f}")

if __name__ == "__main__":
    run_experiment()
