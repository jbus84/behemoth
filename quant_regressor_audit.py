import polars as pl
import numpy as np
import os
from aeon.regression.interval_based import QUANTRegressor

def prepare_data(dataset_path, horizon=60):
    if not os.path.exists(dataset_path): return None, None
    df = pl.read_parquet(dataset_path)
    nodes = ['SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
    anchors = [n for n in nodes]
    
    # 1. Aligned USD Returns (1m)
    def usd_ret(pair, df):
        if pair in ['EURUSD', 'GBPUSD', 'AUDUSD', 'XAUUSD', 'SPXUSD']: return -pl.col(f"{pair}_ret_1m")
        else: return pl.col(f"{pair}_ret_1m")
        
    df = df.with_columns([
        usd_ret(a, df).alias(f"{a}_usd") for a in anchors
    ])
    
    # 2. Target Calculation (60m)
    df = df.with_columns(
        ((pl.col("NSXUSD_mid").shift(-horizon).log() - pl.col("NSXUSD_mid").log()) * 10000).alias("target")
    )
    
    # 3. Extract Windows
    window_len = 15
    stride = 15 # Sample every 15 mins to speed up significantly
    
    macro_data = df.select([f"{a}_usd" for a in anchors]).to_numpy() 
    nsx_target = df['target'].to_numpy() 
    
    X = []
    Y = []
    
    for i in range(window_len, len(macro_data), stride):
        window = macro_data[i-window_len:i].T
        if not np.isnan(nsx_target[i-1]):
            X.append(window)
            Y.append(nsx_target[i-1])
        
    X = np.array(X)
    Y = np.array(Y)
    
    return X, Y

def run_60m_quant_audit():
    print("\n>>> AEON QUANT REGRESSOR 60M AUDIT <<<")
    
    years = ["2023", "2024", "2025"]
    
    # Data Preparation
    data = {}
    for y in years:
        X, Y = prepare_data(f"graph_dataset_1m_{y}.parquet")
        if X is not None:
            data[y] = (X, Y)
            print(f"Loaded {y}: {len(X)} windows.")
    
    if len(data) < 3:
        print("Incomplete data.")
        return

    # WFO Step 1: 2023 -> 2024
    print("\n--- WFO Step 1: Train 2023 -> Test 2024 (H=60) ---")
    Xtr23, Ytr23 = data["2023"]
    Xte24, Yte24 = data["2024"]
    
    reg = QUANTRegressor(random_state=42)
    reg.fit(Xtr23, Ytr23)
    preds = reg.predict(Xte24)
    
    threshold = 5.0 # 5 bps for 1h move
    
    def evaluate(preds, actual, label, thr):
        trades = []
        for p, a in zip(preds, actual):
            if p > thr: trades.append(a - 1.5)
            elif p < -thr: trades.append(-a - 1.5)
        
        trades = np.array(trades)
        print(f" Results for {label} (Thr={thr}bps):")
        if len(trades) > 0:
            print(f"   Trades:   {len(trades)}")
            print(f"   Win Rate: {(trades > 0).mean()*100:.2f}%")
            print(f"   Avg PnL:  {trades.mean():.3f} bps")
        else:
            print("   No trades.")

    evaluate(preds, Yte24, "2024 OOS", threshold)

    # WFO Step 2: 2023+2024 -> 2025
    print("\n--- WFO Step 2: Train 2023+2024 -> Test 2025 (H=60) ---")
    Xtr_comb = np.concatenate([data["2023"][0], data["2024"][0]])
    Ytr_comb = np.concatenate([data["2023"][1], data["2024"][1]])
    Xte25, Yte25 = data["2025"]
    
    reg.fit(Xtr_comb, Ytr_comb)
    preds = reg.predict(Xte25)
    evaluate(preds, Yte25, "2025 OOS", threshold)

if __name__ == "__main__":
    run_60m_quant_audit()
