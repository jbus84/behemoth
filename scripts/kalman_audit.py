import polars as pl
import numpy as np
from kalman_filter import KalmanFilterReg

DATA_DIR = "/Users/danielfisher/repositories/behemoth/data/pairs"

def run_audit():
    # Load Index Pair
    path = f"{DATA_DIR}/pairs_indices_4h.parquet"
    print(f"Loading {path}...")
    df = pl.read_parquet(path).sort("timestamp")

    # Extract Arrays
    # NSX (y), SPX (x)
    # Use Log Prices for better beta stability? Pairs usually done on log returns or log prices.
    # Let's use Log Prices.

    y_raw = np.log(df["close_NSXUSD"].to_numpy())
    x_raw = np.log(df["close_SPXUSD"].to_numpy()) # Wait, column might be close_SPXUSD based on build script
    ts = df["timestamp"].to_list()

    # Initialize Kalman
    # Q=1e-5 (Beta drifting slowly), R=1e-3 (Noise)
    kf = KalmanFilterReg(Q=1e-5, R=1e-3)

    betas = []
    spreads = []

    # Loop (Can't vectorize online Kalman easily)
    for i in range(len(y_raw)):
        beta, spread = kf.update(x_raw[i], y_raw[i])
        betas.append(beta)
        # Standardized Spread?
        # The 'spread' return from update is (y - beta_pred * x) RECURSIVE residuals.
        # This is good for Z-score.
        spreads.append(spread)

    betas = np.array(betas)
    spreads = np.array(spreads)

    # Generate Z-Score
    # Rolling Std of Spread (e.g. 50 periods = 200 hours? or 20 periods?)
    # 20 periods seems standard for Bollinger bands.

    import pandas as pd
    s_series = pd.Series(spreads)
    z_score = (s_series - s_series.rolling(30).mean()) / s_series.rolling(30).std()

    # Strategy Logic
    # Short Pair (Short NSX, Long SPX) when Z > 2.0
    # Long Pair (Long NSX, Short SPX) when Z < -2.0
    # Exit when Z crosses 0 or stop?

    # Let's use simple vector logic first
    signals = np.zeros(len(z_score))
    # signals[z_score > 2.0] = -1
    # signals[z_score < -2.0] = 1

    # Stateful Simulation for Holds
    position = 0 # 0, 1, -1
    entry_price = 0
    pnl = []

    for i in range(1, len(z_score)):
        z = z_score.iloc[i-1] # Signal lag 1
        curr_z = z_score.iloc[i]

        # PnL Calculation
        # Log Return of Spread?
        # Approx: Position * (Spread[t] - Spread[t-1])?
        # More accurately: Position * ( (Y[t]-Y[t-1]) - Beta * (X[t]-X[t-1]) )
        # Let's use simple Spread Delta.

        step_pnl = 0
        if position != 0:
            # Spread change. If Long Spread (pos=1), we want Spread to Go Up (Z to -2 -> 0)
            # Wait, if Z is -2, Spread is Low. We Buy. We want Spread to Mean Revert (increase) to 0.
            # So Pnl = (Spread[i] - Spread[i-1]) * Position
            step_pnl = (spreads[i] - spreads[i-1]) * position

        pnl.append(step_pnl)

        # Logic
        if position == 0:
            if z > 2.0:
                position = -1 # Sell High
            elif z < -2.0:
                position = 1 # Buy Low
        elif position == 1: # Long
            if z > 0: position = 0 # Reverted
            # Time stop logic would go here
        elif position == -1: # Short
            if z < 0: position = 0 # Reverted

    cum_pnl = np.cumsum(pnl)
    print("--- Kalman Results (Index Pair) ---")
    print(f"Total PnL (Spread Units): {cum_pnl[-1]:.4f}")

    # Plot or stats
    print(f"Final Beta: {betas[-1]:.4f}")

    # Sharpe
    ret = np.array(pnl)
    sharpe = np.mean(ret) / np.std(ret) * np.sqrt(252*6) # 4H bars per day?
    print(f"Sharpe: {sharpe:.2f}")

    print(f"Sharpe: {sharpe:.2f}")

def run_fx_audit():
    # Load FX Pair
    path = f"{DATA_DIR}/pairs_fx_4h.parquet"
    print(f"\nLoading {path}...")
    df = pl.read_parquet(path).sort("timestamp")

    # FX: EUR (y) vs GBP (x)
    # y = beta * x

    y_raw = np.log(df["close_EURUSD"].to_numpy())
    x_raw = np.log(df["close_GBPUSD"].to_numpy())

    kf = KalmanFilterReg(Q=1e-5, R=1e-3)

    betas = []
    spreads = []

    for i in range(len(y_raw)):
        beta, spread = kf.update(x_raw[i], y_raw[i])
        betas.append(beta)
        spreads.append(spread)

    betas = np.array(betas)
    spreads = np.array(spreads)

    # Z-Score
    import pandas as pd
    s_series = pd.Series(spreads)
    z_score = (s_series - s_series.rolling(30).mean()) / s_series.rolling(30).std()

    # Backtest
    signals = np.zeros(len(z_score))
    position = 0
    pnl = []

    for i in range(1, len(z_score)):
        z = z_score.iloc[i-1]
        curr_z = z_score.iloc[i]

        # PnL
        step_pnl = 0
        if position != 0:
            step_pnl = (spreads[i] - spreads[i-1]) * position

        pnl.append(step_pnl)

        if position == 0:
            if z > 2.0: position = -1
            elif z < -2.0: position = 1
        elif position == 1:
            if z > 0: position = 0
        elif position == -1:
            if z < 0: position = 0

    cum_pnl = np.cumsum(pnl)
    print("--- Kalman Results (FX Pair: EUR/GBP) ---")
    print(f"Total PnL (Spread Units): {cum_pnl[-1]:.4f}")
    print(f"Final Beta: {betas[-1]:.4f}")

    ret = np.array(pnl)
    sharpe = np.mean(ret) / np.std(ret) * np.sqrt(252*6)
    print(f"Sharpe: {sharpe:.2f}")

    print(f"Sharpe: {sharpe:.2f}")

def run_dow_audit():
    path = f"{DATA_DIR}/pairs_dow_spx_4h.parquet"
    print(f"\nLoading {path}...")
    df = pl.read_parquet(path).sort("timestamp")

    # Dow (UDX) vs SPX (close_SPXUSD)
    y_raw = np.log(df["close_UDXUSD"].to_numpy())
    x_raw = np.log(df["close_SPXUSD"].to_numpy())

    kf = KalmanFilterReg(Q=1e-5, R=1e-3)
    betas, spreads = [], []
    for i in range(len(y_raw)):
        beta, spread = kf.update(x_raw[i], y_raw[i])
        betas.append(beta)
        spreads.append(spread)

    # Backtest
    spreads = np.array(spreads)
    import pandas as pd
    s_series = pd.Series(spreads)
    z_score = (s_series - s_series.rolling(30).mean()) / s_series.rolling(30).std()

    signals = np.zeros(len(z_score))
    position, pnl = 0, []

    for i in range(1, len(z_score)):
        z = z_score.iloc[i-1]
        step_pnl = 0
        if position != 0: step_pnl = (spreads[i] - spreads[i-1]) * position
        pnl.append(step_pnl)

        if position == 0:
            if z > 2.0: position = -1
            elif z < -2.0: position = 1
        elif position == 1:
            if z > 0: position = 0
        elif position == -1:
            if z < 0: position = 0

    ret = np.array(pnl)
    sharpe = np.mean(ret) / np.std(ret) * np.sqrt(252*6)
    print("--- Kalman Results (Dow/SPX: Value/Growth) ---")
    print(f"Total PnL: {np.sum(pnl):.4f}")
    print(f"Sharpe: {sharpe:.2f}")

def run_euro_audit():
    path = f"{DATA_DIR}/pairs_dax_ftse_4h.parquet"
    print(f"\nLoading {path}...")
    df = pl.read_parquet(path).sort("timestamp")

    # DAX (GRX) vs FTSE (UKX)
    y_raw = np.log(df["close_GRXEUR"].to_numpy())
    x_raw = np.log(df["close_UKXGBP"].to_numpy())

    kf = KalmanFilterReg(Q=1e-5, R=1e-3)
    betas, spreads = [], []
    for i in range(len(y_raw)):
        beta, spread = kf.update(x_raw[i], y_raw[i])
        betas.append(beta)
        spreads.append(spread)

    # Backtest
    spreads = np.array(spreads)
    import pandas as pd
    s_series = pd.Series(spreads)
    z_score = (s_series - s_series.rolling(30).mean()) / s_series.rolling(30).std()

    signals = np.zeros(len(z_score))
    position, pnl = 0, []

    for i in range(1, len(z_score)):
        z = z_score.iloc[i-1]
        step_pnl = 0
        if position != 0: step_pnl = (spreads[i] - spreads[i-1]) * position
        pnl.append(step_pnl)

        if position == 0:
            if z > 2.0: position = -1
            elif z < -2.0: position = 1
        elif position == 1:
            if z > 0: position = 0
        elif position == -1:
            if z < 0: position = 0

    ret = np.array(pnl)
    sharpe = np.mean(ret) / np.std(ret) * np.sqrt(252*6)
    print("--- Kalman Results (DAX/FTSE: Euro Core) ---")
    print(f"Total PnL: {np.sum(pnl):.4f}")
    print(f"Sharpe: {sharpe:.2f}")

def run_audnzd_audit():
    path = f"{DATA_DIR}/pairs_aud_nzd_4h.parquet"
    if not os.path.exists(path): return
    print(f"\nLoading {path}...")
    df = pl.read_parquet(path).sort("timestamp")

    # AUDUSD vs NZDUSD
    y_raw = np.log(df["close_AUDUSD"].to_numpy())
    x_raw = np.log(df["close_NZDUSD"].to_numpy())

    kf = KalmanFilterReg(Q=1e-5, R=1e-3)
    betas, spreads = [], []
    for i in range(len(y_raw)):
        beta, spread = kf.update(x_raw[i], y_raw[i])
        betas.append(beta)
        spreads.append(spread)

    spreads = np.array(spreads)
    import pandas as pd
    s_series = pd.Series(spreads)
    z_score = (s_series - s_series.rolling(30).mean()) / s_series.rolling(30).std()

    signals = np.zeros(len(z_score))
    position, pnl = 0, []

    for i in range(1, len(z_score)):
        z = z_score.iloc[i-1]
        step_pnl = 0
        if position != 0: step_pnl = (spreads[i] - spreads[i-1]) * position
        pnl.append(step_pnl)

        if position == 0:
            if z > 2.0: position = -1
            elif z < -2.0: position = 1
        elif position == 1: if z > 0: position = 0
        elif position == -1: if z < 0: position = 0

    ret = np.array(pnl)
    sharpe = np.mean(ret) / np.std(ret) * np.sqrt(252*6)
    print("--- Kalman Results (AUD/NZD: Synthetic) ---")
    print(f"Sharpe: {sharpe:.2f}")

def run_eurchf_audit():
    path = f"{DATA_DIR}/pairs_eur_chf_4h.parquet"
    if not os.path.exists(path): return
    print(f"\nLoading {path}...")
    df = pl.read_parquet(path).sort("timestamp")

    # EURUSD vs USDCHF
    # Note: USDCHF is inversely correlated to EURUSD usually.
    # Expect negative beta.
    y_raw = np.log(df["close_EURUSD"].to_numpy())
    x_raw = np.log(df["close_USDCHF"].to_numpy())

    kf = KalmanFilterReg(Q=1e-5, R=1e-3)
    betas, spreads = [], []
    for i in range(len(y_raw)):
        beta, spread = kf.update(x_raw[i], y_raw[i])
        betas.append(beta)
        spreads.append(spread)

    spreads = np.array(spreads)
    import pandas as pd
    s_series = pd.Series(spreads)
    z_score = (s_series - s_series.rolling(30).mean()) / s_series.rolling(30).std()

    position, pnl = 0, []
    for i in range(1, len(z_score)):
        z = z_score.iloc[i-1]
        step_pnl = 0
        if position != 0: step_pnl = (spreads[i] - spreads[i-1]) * position
        pnl.append(step_pnl)

        if position == 0:
            if z > 2.0: position = -1
            elif z < -2.0: position = 1
        elif position == 1: if z > 0: position = 0
        elif position == -1: if z < 0: position = 0

    ret = np.array(pnl)
    sharpe = np.mean(ret) / np.std(ret) * np.sqrt(252*6)
    print("--- Kalman Results (EUR/CHF: Synthetic) ---")
    print(f"Sharpe: {sharpe:.2f}")

def run_oil_audit():
    path = f"{DATA_DIR}/pairs_oil_4h.parquet"
    if not os.path.exists(path): return
    print(f"\nLoading {path}...")
    df = pl.read_parquet(path).sort("timestamp")

    # Brent (BCO) vs WTI
    y_raw = np.log(df["close_BCOUSD"].to_numpy())
    x_raw = np.log(df["close_WTIUSD"].to_numpy())

    kf = KalmanFilterReg(Q=1e-5, R=1e-3)
    betas, spreads = [], []
    for i in range(len(y_raw)):
        beta, spread = kf.update(x_raw[i], y_raw[i])
        betas.append(beta)
        spreads.append(spread)

    spreads = np.array(spreads)
    import pandas as pd
    s_series = pd.Series(spreads)
    z_score = (s_series - s_series.rolling(30).mean()) / s_series.rolling(30).std()

    position, pnl = 0, []
    for i in range(1, len(z_score)):
        z = z_score.iloc[i-1]
        step_pnl = 0
        if position != 0: step_pnl = (spreads[i] - spreads[i-1]) * position
        pnl.append(step_pnl)

        if position == 0:
            if z > 2.0: position = -1
            elif z < -2.0: position = 1
        elif position == 1: if z > 0: position = 0
        elif position == -1: if z < 0: position = 0

    ret = np.array(pnl)
    sharpe = np.mean(ret) / np.std(ret) * np.sqrt(252*6)
    print("--- Kalman Results (Brent/WTI: Oil Arb) ---")
    print(f"Sharpe: {sharpe:.2f}")

if __name__ == "__main__":
    run_audit()
    run_fx_audit()
    run_dow_audit()
    run_euro_audit()
    run_audnzd_audit()
    run_eurchf_audit()
    run_oil_audit()
