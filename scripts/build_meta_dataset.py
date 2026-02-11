
import polars as pl
import numpy as np
import os
import sys
sys.path.append(os.path.join(os.getcwd(), 'scripts'))
from kalman_filter import KalmanFilterReg

DATA_DIR = "data/global_15m"
OUTPUT_DIR = "data/meta_model"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def get_data(file_x, file_y, col_x, col_y):
    try:
        p_x = os.path.join(DATA_DIR, file_x)
        p_y = os.path.join(DATA_DIR, file_y)
        df_x = pl.read_parquet(p_x).rename({col_x: "X"})
        df_y = pl.read_parquet(p_y).rename({col_y: "Y"})
        df = df_x.join(df_y, on="timestamp", how="inner").sort("timestamp")
        # 8 Years
        df = df.filter(pl.col("timestamp").dt.year().is_in(list(range(2018, 2026))))
        return df
    except Exception as e:
        print(f"Error loading {file_x}/{file_y}: {e}")
        return None

def build_dataset():
    print("--- BUILDING META MODEL DATASET (8 YEARS) ---")

    pairs = [
        # FX & Commodities (Original)
        ("EUR/GBP", "EURUSD_15m.parquet", "GBPUSD_15m.parquet", "close_EURUSD", "close_GBPUSD", 1.6, 1.0),
        ("Gold/Oil", "BCOUSD_15m.parquet", "XAUUSD_15m.parquet", "close_BCOUSD", "close_XAUUSD", 3.0, 3.0),
        ("Oil/Silver", "BCOUSD_15m.parquet", "XAGUSD_15m.parquet", "close_BCOUSD", "close_XAGUSD", 3.0, 3.0),
        ("AUD/NZD", "NZDUSD_15m.parquet", "AUDUSD_15m.parquet", "close_NZDUSD", "close_AUDUSD", 2.0, 2.0),
        ("CAC/NZD", "NZDUSD_15m.parquet", "FRXEUR_15m.parquet", "close_NZDUSD", "close_FRXEUR", 3.0, 3.0),

        # Precious Metals
        ("Gold/Silver", "XAUUSD_15m.parquet", "XAGUSD_15m.parquet", "close_XAUUSD", "close_XAGUSD", 3.0, 3.0),

        # Global Equities (SPX as Anchor)
        ("SPX/DAX", "SPXUSD_15m.parquet", "GRXEUR_15m.parquet", "close_SPXUSD", "close_GRXEUR", 3.0, 2.0),
        ("SPX/CAC", "SPXUSD_15m.parquet", "FRXEUR_15m.parquet", "close_SPXUSD", "close_FRXEUR", 3.0, 2.0),
        ("SPX/FTSE", "SPXUSD_15m.parquet", "UKXGBP_15m.parquet", "close_SPXUSD", "close_UKXGBP", 3.0, 2.0),
        ("SPX/Nikkei", "SPXUSD_15m.parquet", "JPXJPY_15m.parquet", "close_SPXUSD", "close_JPXJPY", 3.0, 2.0),
        ("SPX/HK", "SPXUSD_15m.parquet", "HKXHKD_15m.parquet", "close_SPXUSD", "close_HKXHKD", 4.0, 2.0),
        ("SPX/Dow", "SPXUSD_15m.parquet", "UDXUSD_15m.parquet", "close_SPXUSD", "close_UDXUSD", 2.0, 2.0),
        ("SPX/Nas", "SPXUSD_15m.parquet", "NSXUSD_15m.parquet", "close_SPXUSD", "close_NSXUSD", 2.0, 2.0),

        # Commodity FX
        ("AUD/CAD", "AUDUSD_15m.parquet", "USDCAD_15m.parquet", "close_AUDUSD", "close_USDCAD", 2.0, 2.0),

        # Extended FX Universe (User Request)
        ("EUR/CHF", "EURUSD_15m.parquet", "USDCHF_15m.parquet", "close_EURUSD", "close_USDCHF", 2.0, 2.0), # The "Swissy" inverse
        ("EUR/JPY", "EURUSD_15m.parquet", "USDJPY_15m.parquet", "close_EURUSD", "close_USDJPY", 2.0, 1.0),
        ("GBP/JPY", "GBPUSD_15m.parquet", "USDJPY_15m.parquet", "close_GBPUSD", "close_USDJPY", 2.0, 1.0),
        ("CHF/JPY", "USDCHF_15m.parquet", "USDJPY_15m.parquet", "close_USDCHF", "close_USDJPY", 2.0, 1.0),
        ("EUR/AUD", "EURUSD_15m.parquet", "AUDUSD_15m.parquet", "close_EURUSD", "close_AUDUSD", 2.0, 2.0),
        ("GBP/AUD", "GBPUSD_15m.parquet", "AUDUSD_15m.parquet", "close_GBPUSD", "close_AUDUSD", 2.0, 2.0),
        ("GBP/CAD", "GBPUSD_15m.parquet", "USDCAD_15m.parquet", "close_GBPUSD", "close_USDCAD", 2.0, 2.0),
        ("NZD/CAD", "NZDUSD_15m.parquet", "USDCAD_15m.parquet", "close_NZDUSD", "close_USDCAD", 2.0, 2.0)
    ]

    thresh = 1.5
    stop_level = 3.5

    all_events = []

    for name, fx, fy, cx, cy, cost_y, cost_x in pairs:
        print(f"Processing {name}...")
        df = get_data(fx, fy, cx, cy)
        if df is None: continue

        y = np.log(df["Y"].to_numpy())
        x = np.log(df["X"].to_numpy())
        ts = df["timestamp"].to_numpy()

        kf = KalmanFilterReg(Q=1e-5, R=1e-3)
        betas, errors = [], []

        # State Generation
        for i in range(len(y)):
            if i < 10: mu_y, mu_x = y[i], x[i]
            else: mu_y, mu_x = np.mean(y[max(0,i-500):i]), np.mean(x[max(0,i-500):i])
            b, _ = kf.update(x[i]-mu_x, y[i]-mu_y)
            betas.append(b)
            errors.append((y[i]-mu_y) - b*(x[i]-mu_x))

        in_pos = 0; active_asset = None; entry_price = 0.0; entry_idx = 0

        for i in range(500, len(y)):
            beta = betas[i]
            window = errors[i-500:i]
            mu, std = np.mean(window), np.std(window)
            if std < 1e-6: continue
            z = (errors[i] - mu) / std

            # Regime Logic
            if beta < 0.98: target_asset = 'Y' # Tank = Y -> Mom
            elif beta > 1.02: target_asset = 'X' # Tank = X -> Mom
            else: target_asset = 'NEUTRAL'

            # Entry Logic (Capture Z > 1.5 AND Z < -1.5)
            if in_pos == 0:
                if target_asset == 'Y':
                    if z > thresh: in_pos = 1; active_asset = 'Y'; entry_price = y[i]; entry_idx = i
                    elif z < -thresh: in_pos = -1; active_asset = 'Y'; entry_price = y[i]; entry_idx = i
                elif target_asset == 'X':
                    if z > thresh: in_pos = -1; active_asset = 'X'; entry_price = x[i]; entry_idx = i
                    elif z < -thresh: in_pos = 1; active_asset = 'X'; entry_price = x[i]; entry_idx = i

            # Exit Logic
            elif in_pos != 0:
                closed = False
                pnl = 0.0
                outcome = ""

                curr_y, curr_x = y[i], x[i]

                if active_asset == 'Y':
                    if in_pos == 1:
                        if z < 0: pnl = (curr_y - entry_price)*10000 - cost_y; closed = True; outcome="LOSS_REV"
                        elif z > stop_level: pnl = (curr_y - entry_price)*10000 - cost_y; closed = True; outcome="WIN_MOM"
                    elif in_pos == -1:
                        if z > 0: pnl = -(curr_y - entry_price)*10000 - cost_y; closed = True; outcome="LOSS_REV"
                        elif z < -stop_level: pnl = -(curr_y - entry_price)*10000 - cost_y; closed = True; outcome="WIN_MOM"
                elif active_asset == 'X':
                    if in_pos == -1:
                        if z < 0: pnl = -(curr_x - entry_price)*10000 - cost_x; closed = True; outcome="LOSS_REV"
                        elif z > stop_level: pnl = -(curr_x - entry_price)*10000 - cost_x; closed = True; outcome="WIN_MOM"
                    elif in_pos == 1:
                        if z > 0: pnl = (curr_x - entry_price)*10000 - cost_x; closed = True; outcome="LOSS_REV"
                        elif z < -stop_level: pnl = (curr_x - entry_price)*10000 - cost_x; closed = True; outcome="WIN_MOM"

                if closed:
                    # Save Event
                    # Save Event
                    # Features from ENTRY TIME (entry_idx)
                    entry_beta = betas[entry_idx]

                    # 1. Z-Score at Entry
                    entry_window = errors[entry_idx-500:entry_idx]
                    entry_mu, entry_std = np.mean(entry_window), np.std(entry_window)
                    if entry_std > 1e-6:
                        entry_z = (errors[entry_idx] - entry_mu) / entry_std
                    else:
                        entry_z = 0.0

                    # 2. Volatility Ratio (Y/X) at Entry
                    # Calculate rolling vol over 500 bars
                    start = max(0, entry_idx-500)
                    vol_y = np.std(np.diff(y[start:entry_idx]))
                    vol_x = np.std(np.diff(x[start:entry_idx]))
                    vol_ratio = vol_y / vol_x if vol_x > 0 else 1.0

                    # 3. Z-Velocity (5-bar change)
                    prev_idx = max(0, entry_idx-5)
                    start_prev = max(0, prev_idx-500)
                    prev_window = errors[start_prev:prev_idx]
                    prev_mu, prev_std = np.mean(prev_window), np.std(prev_window)
                    if prev_std > 1e-6:
                        prev_z = (errors[prev_idx] - prev_mu) / prev_std
                    else:
                        prev_z = 0.0
                    z_velocity = entry_z - prev_z

                    # Store Row
                    row = {
                        "pair": name,
                        "timestamp": ts[entry_idx],
                        "year": int(str(ts[entry_idx])[:4]),
                        "beta": entry_beta,
                        "z_entry": round(entry_z, 2),
                        "vol_ratio": round(vol_ratio, 3),
                        "z_velocity": round(z_velocity, 2),
                        "active_leg": active_asset,
                        "side": "LONG" if in_pos == 1 else "SHORT",
                        "outcome": outcome,
                        "pnl_bps": round(pnl, 2),
                        "duration_bars": i - entry_idx
                    }
                    all_events.append(row)

                    in_pos = 0; active_asset = None

    # Save to CSV
    if len(all_events) > 0:
        df_out = pl.DataFrame(all_events)
        out_path = os.path.join(OUTPUT_DIR, "events_m15_8yr.csv")
        df_out.write_csv(out_path)
        print(f"Saved {len(all_events)} events to {out_path}")
        print(df_out.group_by("pair").agg(pl.count("pnl_bps"), pl.mean("pnl_bps")))
    else:
        print("No events found.")

if __name__ == "__main__":
    build_dataset()
