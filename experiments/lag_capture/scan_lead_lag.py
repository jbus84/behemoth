
import polars as pl
import numpy as np
import os

DATA_DIR = "data/global_15m"

# Candidates: (Leader, Laggard, Label)
PAIRS = [
    ("EURUSD", "GBPUSD", "Euro -> Cable"),
    ("GBPUSD", "EURUSD", "Cable -> Euro"),
]

def scan_lead_lag():
    print("--- LEAD-LAG SCANNER (M15) ---")
    print("Searching for 'Lazy Dogs' (Laggards)...")
    print("\n| Leader -> Laggard | Lag 0 (Simul) | Lag 1 (15m) | Lag 2 (30m) | Lag 4 (1h) | Lead Score |")
    print("|---|---|---|---|---|---|")

    for leader, laggard, label in PAIRS:
        p_leader = os.path.join(DATA_DIR, f"{leader}_15m.parquet")
        p_laggard = os.path.join(DATA_DIR, f"{laggard}_15m.parquet")

        if not os.path.exists(p_leader) or not os.path.exists(p_laggard):
            print(f"Missing data for {label}")
            continue

        df_lead = pl.read_parquet(p_leader).rename({f"close_{leader}": "X"})
        df_lag = pl.read_parquet(p_laggard).rename({f"close_{laggard}": "Y"})

        # Join
        df = df_lead.join(df_lag, on="timestamp", how="inner").sort("timestamp")

        # Returns
        x_log = np.log(df["X"].to_numpy())
        y_log = np.log(df["Y"].to_numpy())

        ret_x = np.diff(x_log)
        ret_y = np.diff(y_log)

        # Cross Correlation
        # Shift X forward (X happens, then Y happens)
        # Lag 0
        c0 = np.corrcoef(ret_x, ret_y)[0,1]

        # Lag 1 (X_t-1 vs Y_t) -> Did X predict Y?
        # ret_x[:-1] vs ret_y[1:]
        c1 = np.corrcoef(ret_x[:-1], ret_y[1:])[0,1]

        # Lag 2
        c2 = np.corrcoef(ret_x[:-2], ret_y[2:])[0,1]

        # Lag 4
        c4 = np.corrcoef(ret_x[:-4], ret_y[4:])[0,1]

        # Score: How much of the correlation is "Late"?
        # If C0 is 0.8 and C1 is 0.2, Scote = 0.25.
        # If C0 is 0.8 and C1 is 0.0, Score = 0.0 (Efficient).
        score = abs(c1) / (abs(c0) + 1e-9)

        print(f"| {label} | {c0:.3f} | {c1:.3f} | {c2:.3f} | {c4:.3f} | {score:.2f} |")

if __name__ == "__main__":
    scan_lead_lag()
