
import numpy as np
import matplotlib.pyplot as plt
from kalman_filter import KalmanFilterReg

def verify_centered_logic():
    print("--- CENTERED KALMAN LOGIC VERIFICATION ---")
    
    # 1. Generate Synthetic Data with Massive Intercept
    np.random.seed(42)
    N = 1000
    x = np.random.normal(10, 1, N) # X centered around 10
    
    TRUE_BETA = 2.5
    INTERCEPT = 1000.0 # The "Level" problem
    
    # y = 2.5x + 1000 + noise
    noise = np.random.normal(0, 0.1, N)
    y = TRUE_BETA * x + INTERCEPT + noise
    
    print(f"True Relation: y = {TRUE_BETA} * x + {INTERCEPT}")
    print(f"Mean Y: {np.mean(y):.2f}, Mean X: {np.mean(x):.2f}")
    
    # 2. Test Raw Kalman (The Bug)
    print("\n[TEST 1] Raw Kalman (No Centering)...")
    kf1 = KalmanFilterReg(Q=1e-5, R=1e-3)
    betas1 = []
    
    for i in range(N):
        b, _ = kf1.update(x[i], y[i])
        betas1.append(b)
        
    avg_beta1 = np.mean(betas1[100:])
    print(f"Estimated Beta: {avg_beta1:.2f}")
    if abs(avg_beta1 - TRUE_BETA) > 1.0:
        print(">> FAIL. Beta absorbed the intercept.")
    else:
        print(">> PASS.")

    # 3. Test Rolling Centered Kalman (The Fix)
    print("\n[TEST 2] Rolling Centered Kalman (Window=50)...")
    kf2 = KalmanFilterReg(Q=1e-5, R=1e-3)
    betas2 = []
    
    y_win, x_win = [], []
    
    for i in range(N):
        y_win.append(y[i])
        x_win.append(x[i])
        if len(y_win) > 50: y_win.pop(0); x_win.pop(0)
        
        # Center
        if len(y_win) < 2:
            my, mx = y[i], x[i]
        else:
            my, mx = np.mean(y_win), np.mean(x_win)
            
        y_c = y[i] - my
        x_c = x[i] - mx
        
        # Feed Centered Data to KF
        b, _ = kf2.update(x_c, y_c)
        betas2.append(b)
        
    avg_beta2 = np.mean(betas2[100:])
    print(f"Estimated Beta: {avg_beta2:.2f}")
    
    err = abs(avg_beta2 - TRUE_BETA)
    print(f"Error: {err:.4f}")
    
    if err < 0.1:
        print(">> PASS. Centering recovered the true slope.")
    else:
        print(">> FAIL. Logic Broken.")

if __name__ == "__main__":
    verify_centered_logic()
