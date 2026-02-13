"""
Verify that incremental Kalman Filter updates match batch calculations.
This test simulates the cBot's behavior: 
1. Send full history (Init) at time T.
2. Send single bar (Update) at time T+1.
3. Compare the resulting Z-score and Beta with a full-history calculation at T+1.
"""
import sys
import numpy as np
import pandas as pd
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from behemoth.core.kalman import compute_kalman_states, KalmanFilterReg
from behemoth.core.zscore import compute_z_scores
from services.api.signals import STATE_KALMAN, STATE_BUFFER, STATE_ERRORS, _get_state_key

def verify_incremental_logic():
    print("Generating synthetic data...")
    np.random.seed(42)
    n = 1000
    # Generate correlated random walk
    x = np.cumsum(np.random.normal(0, 1, n))
    noise = np.random.normal(0, 0.1, n)
    beta_true = 1.5
    y = beta_true * x + noise
    
    # Log transform as per production
    # Shift to positive to avoid log(negative)
    x = x - min(x) + 10
    y = y - min(y) + 10
    
    # Batch run at T (index 800)
    T = 800
    lookback = 750
    
    print(f"Running Match at T={T}...")
    
    # 1. Full Batch at T
    y_slice_T = np.log(y[T-lookback:T])
    x_slice_T = np.log(x[T-lookback:T])
    
    betas_batch_T, errors_batch_T, _ = compute_kalman_states(y_slice_T, x_slice_T, window=lookback)
    z_scores_batch_T = compute_z_scores(errors_batch_T, window=lookback)
    
    # Mimic Signal API State Initialization
    state_key = "test_strategy"
    pair_name = "TEST_PAIR"
    
    # Reset/Init State
    STATE_BUFFER[state_key] = {}
    STATE_KALMAN[state_key] = {}
    STATE_ERRORS[state_key] = {}
    
    # Save Buffer
    STATE_BUFFER[state_key][pair_name] = pd.DataFrame({"y": y_slice_T, "x": x_slice_T})
    STATE_ERRORS[state_key][pair_name] = list(errors_batch_T) # Last 750 errors
    
    # Re-hydrate Kalman State (Burn-in)
    kf_live = KalmanFilterReg(Q=1e-5, R=1e-3)
    check_df = STATE_BUFFER[state_key][pair_name]
    
    # Compute rolling means for burn-in
    # Replicate pandas rolling behavior
    # Note: signals.py logic uses rolling(750) on the buffer
    mu_y_vec = check_df["y"].rolling(750, min_periods=1).mean().shift(1)
    mu_x_vec = check_df["x"].rolling(750, min_periods=1).mean().shift(1)
    
    warmup = 10
    for i in range(len(check_df)):
        if i < warmup:
            # Replicate kalman.py warmup logic: mu = raw value
            mx = check_df["x"].iloc[i]
            my = check_df["y"].iloc[i]
        else:
            mx = mu_x_vec.iloc[i]
            my = mu_y_vec.iloc[i]
            
        if pd.isna(mx) or pd.isna(my): continue
        kf_live.update(check_df["x"].iloc[i] - mx, check_df["y"].iloc[i] - my)
        
    STATE_KALMAN[state_key][pair_name] = kf_live
    
    # Check if State matches Batch at T
    print(f"Batch Beta T: {betas_batch_T[-1]:.6f}")
    print(f"State Beta T: {kf_live.beta[0]:.6f}")
    
    # 2. Incremental Update at T+1
    print(f"\nRunning Incremental Update at T={T+1}...")
    new_y_raw = y[T]
    new_x_raw = x[T]
    new_y = np.log(new_y_raw)
    new_x = np.log(new_x_raw)
    
    # --- Incremental Logic from signals.py ---
    pdf = STATE_BUFFER[state_key][pair_name]
    new_row = pd.DataFrame({"y": [new_y], "x": [new_x]})
    pdf = pd.concat([pdf, new_row], ignore_index=True)
    if len(pdf) > lookback + 50:
        pdf = pdf.iloc[-(lookback + 10):]
    STATE_BUFFER[state_key][pair_name] = pdf
    
    # Rolling Means
    last_window = pdf.iloc[-(lookback+1):-1]
    mu_y = last_window["y"].mean()
    mu_x = last_window["x"].mean()
    
    # KF Update
    kf = STATE_KALMAN[state_key][pair_name]
    beta_inc, error_inc = kf.update(new_x - mu_x, new_y - mu_y)
    
    # Z-Score Update
    # compute stats on PREVIOUS errors (current buffer)
    err_buf = STATE_ERRORS[state_key][pair_name]
    
    err_mean = np.mean(err_buf)
    err_std = np.std(err_buf)
    z_inc = (error_inc - err_mean) / err_std if err_std > 1e-9 else 0.0
    
    # Now update buffer
    err_buf.append(error_inc)
    if len(err_buf) > lookback:
        err_buf.pop(0)

    print(f"Incremental Beta: {beta_inc:.6f}")
    print(f"Incremental Z:    {z_inc:.6f}")
    
    # 3. Reference Batch at T+1
    print(f"\nRunning Reference Batch at T={T+1}...")
    # We need lookback+1 samples to get a Z-score for the last one
    # based on the previous 'lookback' samples.
    y_slice_next = np.log(y[T+1-(lookback+1):T+1])
    x_slice_next = np.log(x[T+1-(lookback+1):T+1])
    
    betas_batch_next, errors_batch_next, _ = compute_kalman_states(y_slice_next, x_slice_next, window=lookback)
    z_scores_batch_next = compute_z_scores(errors_batch_next, window=lookback)
    
    beta_batch_ref = betas_batch_next[-1]
    z_batch_ref = z_scores_batch_next[-1]
    
    print(f"Batch Ref Beta:   {beta_batch_ref:.6f}")
    print(f"Batch Ref Z:      {z_batch_ref:.6f}")
    
    # Comparison
    beta_diff = abs(beta_inc - beta_batch_ref)
    z_diff = abs(z_inc - z_batch_ref)
    
    print(f"\nDifferences:")
    print(f"Beta Diff: {beta_diff:.8f}")
    print(f"Z Diff:    {z_diff:.8f}")
    
    if beta_diff < 1e-4 and z_diff < 1e-2:
        print("\nSUCCESS: Incremental matches Batch within tolerance.")
    else:
        print("\nFAILURE: Significant divergence.")

if __name__ == "__main__":
    verify_incremental_logic()
