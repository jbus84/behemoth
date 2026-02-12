
import sys
import time
import numpy as np
import pandas as pd
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent / "src"
sys.path.append(str(project_root))

from behemoth.core.kalman import compute_kalman_states
from behemoth.core.zscore import compute_z_scores

def verify():
    print("Generating synthetic data...")
    n = 1500
    x = np.linspace(0, 10, n)
    # y = 2x + noise
    y = 2.0 * x + np.random.normal(0, 0.1, n)
    window = 750

    print(f"Running optimized compute_kalman_states (n={n}, window={window})...")
    t0 = time.time()
    betas, errors, betas_ret = compute_kalman_states(y, x, window=window)
    t1 = time.time()
    print(f"Kalman time: {(t1-t0)*1000:.2f} ms")

    assert len(betas) == n, f"Betas length mismatch: {len(betas)} vs {n}"
    assert len(errors) == n, f"Errors length mismatch"
    
    # Check for NaNs (except possibly at start if handled that way)
    # With min_periods=1, we shouldn't have NaNs except possibly very start if offset issues
    # But let's check the converged part
    assert not np.isnan(betas[window:]).any(), "NaNs in betas tail"
    assert not np.isnan(errors[window:]).any(), "NaNs in errors tail"
    
    # Check convergence (slope should be ~2)
    final_beta = betas[-1]
    print(f"Final Beta: {final_beta}")
    assert abs(final_beta - 2.0) < 0.1, f"Beta did not converge: {final_beta} (expected ~2.0)"

    print("Running optimized compute_z_scores...")
    t2 = time.time()
    z_scores = compute_z_scores(errors, window=window)
    t3 = time.time()
    print(f"Z-Score time: {(t3-t2)*1000:.2f} ms")

    assert len(z_scores) == n
    # Z-scores should be computed for indices >= window
    # indices < window should be 0 or similar
    print(f"Z-Score stats (tail): mean={np.mean(z_scores[window:]):.4f}, std={np.std(z_scores[window:]):.4f}")
    
    # Check that Z-scores are not all zero in tail
    assert np.abs(z_scores[window:]).max() > 0.1, "Z-scores seem to be all zero/small"

    print("Optimization verified successfully!")

if __name__ == "__main__":
    verify()
