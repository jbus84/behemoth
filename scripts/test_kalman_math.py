
import numpy as np
import matplotlib.pyplot as plt
from kalman_filter import KalmanFilterReg

def test_kalman_tracking():
    print("--- KALMAN MATH VERIFICATION ---")
    
    # 1. Generate Synthetic Data
    np.random.seed(42)
    N = 1000
    x = np.random.normal(0, 1, N) # Random independent variable
    
    # True Beta is a Sine Wave (Regime Shift Proxy)
    # Oscillates between +2 and -2
    true_beta = 2.0 * np.sin(np.linspace(0, 4*np.pi, N))
    
    # y = x * beta + noise
    noise = np.random.normal(0, 0.1, N)
    y = x * true_beta + noise
    
    # 2. Run Filter
    kf = KalmanFilterReg(Q=1e-4, R=1e-2) # Fast tuning for this test
    est_betas = []
    
    for i in range(N):
        b, _ = kf.update(x[i], y[i])
        est_betas.append(b)
        
    est_betas = np.array(est_betas)
    
    # 3. Validation
    mse = np.mean((est_betas - true_beta)**2)
    print(f"Mean Squared Error (Beta): {mse:.4f}")
    
    # Check Tracking correlation
    corr = np.corrcoef(est_betas, true_beta)[0,1]
    print(f"Tracking Correlation: {corr:.4f}")
    
    if corr > 0.9:
        print("VERDICT: PASS. Filter tracks dynamic beta accurately.")
    else:
        print("VERDICT: FAIL. Filter fails to track.")
        
    # Check "Locking" (Does it explode?)
    if np.max(np.abs(est_betas)) > 5.0:
        print("VERDICT: UNSTABLE. Beta exploded > 5.0 (True Max 2.0).")
    else:
        print("VERDICT: STABLE.")

if __name__ == "__main__":
    test_kalman_tracking()
