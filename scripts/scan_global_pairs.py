
import polars as pl
import numpy as np
import pandas as pd
import os
import glob
from itertools import combinations
from kalman_filter import KalmanFilterReg
from statsmodels.tsa.stattools import adfuller

DATA_DIR = "data/global_1h"

def scan_pairs_1h():
    print("--- GLOBAL PAIR SCANNER 1H (REPORT MODE) ---")

    if not os.path.exists(DATA_DIR):
        print("Data dir not found.")
        return

    files = glob.glob(os.path.join(DATA_DIR, "*.parquet"))
    print(f"Loading {len(files)} 1H datasets...")

    master_df = None
    cols_map = {}

    for f in files:
        try:
            df = pl.read_parquet(f)
            asset = os.path.basename(f).replace("_1h.parquet", "")
            col = f"close_{asset}"
            if col not in df.columns: continue

            df_sub = df.select(["timestamp", col])

            if master_df is None:
                master_df = df_sub
            else:
                master_df = master_df.join(df_sub, on="timestamp", how="inner")

            cols_map[asset] = col
        except Exception as e:
            print(f"Error loading {f}: {e}")

    if master_df is None: return

    master_df = master_df.sort("timestamp")
    assets = list(cols_map.keys())

    # Pre-calc logs/rets
    data_map = {}
    ret_map = {}

    for a in assets:
        p = master_df[cols_map[a]].to_numpy()
        l = np.log(p)
        r = np.diff(l, prepend=l[0])
        r[0] = 0
        data_map[a] = l
        ret_map[a] = r

    pairs = list(combinations(assets, 2))
    print(f"Scanning {len(pairs)} 1H combinations...")

    results = []

    for i, (y_name, x_name) in enumerate(pairs):
        y_log = data_map[y_name]
        x_log = data_map[x_name]
        y_ret = ret_map[y_name]
        x_ret = ret_map[x_name]

        # Betas (Window ~ 500 bars)
        kf_lev = KalmanFilterReg(Q=1e-5, R=1e-3)
        betas_lev = []
        for k in range(len(y_log)):
            b, _ = kf_lev.update(x_log[k], y_log[k])
            betas_lev.append(b)
        sig_beta = np.mean(betas_lev[-500:]) if len(betas_lev) > 500 else np.mean(betas_lev)

        kf_ret = KalmanFilterReg(Q=1e-5, R=1e-3)
        betas_ret = []
        for k in range(len(y_ret)):
            b, _ = kf_ret.update(x_ret[k], y_ret[k])
            betas_ret.append(b)
        hedge_beta = np.mean(betas_ret[-500:]) if len(betas_ret) > 500 else np.mean(betas_ret)

        mismatch = hedge_beta / sig_beta if abs(sig_beta) > 0.01 else 999.0

        # Stationarity
        spreads = y_log - np.array(betas_lev) * x_log
        s_clean = spreads[250:]
        s_clean = s_clean[~np.isnan(s_clean)]

        pval = 1.0
        if len(s_clean) > 50:
            try:
                adf = adfuller(s_clean)
                pval = adf[1]
            except: pass

        tier = "Avoid"
        beta_ok = (0.7 <= abs(mismatch) <= 1.3)
        stat_strong = (pval < 0.01)
        stat_med = (pval < 0.05)

        if beta_ok and stat_strong: tier = "Tier 1: Strategic"
        elif beta_ok and stat_med: tier = "Tier 2: Tactical"

        res = {
            "Y": y_name,
            "X": x_name,
            "Tier": tier,
            "SignalBeta": sig_beta,
            "Mismatch": mismatch,
            "ADF_PVal": pval
        }
        results.append(res)

    df_res = pd.DataFrame(results)
    df_res.sort_values("ADF_PVal", inplace=True)
    df_res.to_csv("docs/global_pair_scan.csv", index=False)
    print("Report saved to docs/global_pair_scan.csv")

if __name__ == "__main__":
    scan_pairs_1h()
