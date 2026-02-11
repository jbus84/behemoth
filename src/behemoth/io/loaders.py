import os

import polars as pl


def load_pair_data(data_dir, fx, fy, cx, cy, start_year=2018, end_year=2025):
    try:
        p_x = os.path.join(data_dir, fx)
        p_y = os.path.join(data_dir, fy)
        df_x = pl.read_parquet(p_x).rename({cx: "X"})
        df_y = pl.read_parquet(p_y).rename({cy: "Y"})
        df = df_x.join(df_y, on="timestamp", how="inner").sort("timestamp")
        df = df.filter(pl.col("timestamp").dt.year().is_in(list(range(start_year, end_year + 1))))
        return df
    except Exception as e:
        print(f"Error loading {fx}/{fy}: {e}")
        return None
