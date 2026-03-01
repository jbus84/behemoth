import pandas as pd
import yaml
from pathlib import Path
import json

with open("configs/research/experiments/gbpusd_oco_reduced_core_rolling_2025.yaml") as f:
    cfg = yaml.safe_load(f)

print(f"Loading {cfg['pred_path']}")
try:
    pred = pd.read_parquet(cfg["pred_path"])
except Exception as e:
    print(f"Could not load preds: {e}")
    # try fullcap dir instead of fullcap_gbpusd
    path = cfg["pred_path"].replace("_gbpusd/", "/")
    print(f"Trying {path}")
    pred = pd.read_parquet(path)

print(f"Loaded {len(pred)} prediction rows.")

# simulate the state aggregation
pred["is_signal"] = pred["selected_exec"].fillna(0) > 0
sl_detail = pd.read_csv("data/analysis/tick_opportunity_mining/stop_limit_tickfill_fullcap/GBPUSD_stop_limit_tickfill_detail.csv")
sl_detail["close_ts"] = pd.to_datetime(sl_detail["close_ts"], format="mixed")
sl_detail["is_tickfill"] = 1
sl_detail.rename(columns={"candidate_uid": "state_id"}, inplace=True)
pred["close_ts_dt"] = pd.to_datetime(pred["close_ts"], utc=True)
sl_detail["close_ts_dt"] = pd.to_datetime(sl_detail["close_ts"], utc=True)
pred = pd.merge(pred, sl_detail[["close_ts_dt", "state_id", "is_tickfill", "touch_found_tick"]], on=["close_ts_dt", "state_id"], how="left")
pred["is_tickfill"] = pred["is_tickfill"].fillna(0)

# Aggregate
grouped = pred[pred["is_signal"]].groupby("state_id").agg(
    total_rows=("close_ts", "count"),
    min_month=("test_month", "min"),
    max_month=("test_month", "max"),
    fill_rate=("is_tickfill", "mean"),
    gross_pips_mean=("target_gross_pips", "mean") # use base target
).reset_index()

families = ["oco_first_touch_clean"]
barriers = [2.0, 3.0]
horizons = [5, 6]

def parse_sid(sid):
    parts = sid.split('|')
    if len(parts) < 6: return None, 0, 0
    return parts[4].split('__')[0] + '__' + parts[4].split('__')[-1], int(parts[3][1:]), float(parts[5].split('__')[0])

grouped["family"] = grouped["state_id"].apply(lambda x: parse_sid(x)[0])
grouped["horizon"] = grouped["state_id"].apply(lambda x: parse_sid(x)[1])
grouped["barrier_pips"] = grouped["state_id"].apply(lambda x: parse_sid(x)[2])

mask_fam = grouped["family"].isin(families)
mask_hor = grouped["horizon"].isin(horizons)
mask_bar = grouped["barrier_pips"].isin(barriers)
filtered = grouped[mask_fam & mask_hor & mask_bar]

print(f"\nStates passing base constraints (family, hor, bar): {len(filtered)}")

if len(filtered) > 0:
    min_rows = cfg.get("min_state_avg_rows", 200) * cfg.get("min_train_months", 3)
    print(f"Applying min rows ({min_rows}):")
    pass_rows = filtered[filtered["total_rows"] >= min_rows]
    print(f"Passed min rows: {len(pass_rows)}")
    
    print("\nTop 5 before min rows drop:")
    print(filtered.sort_values(by="total_rows", ascending=False).head(5))
