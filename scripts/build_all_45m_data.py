import polars as pl
import os
import glob
import gc
from tqdm import tqdm

SOURCE_DIR = "/Users/danielfisher/Desktop/tick"
TARGET_DIR = "data/global_45m"


def build_all_45m_chunked():
    print("--- BUILDING GLOBAL 45M DATASET (CHUNKED MAP-REDUCE) ---")
    if not os.path.exists(TARGET_DIR):
        os.makedirs(TARGET_DIR)

    assets = [d for d in os.listdir(SOURCE_DIR) if os.path.isdir(os.path.join(SOURCE_DIR, d))]
    print(f"Found {len(assets)} assets.")

    if "XAUUSD" in assets:
        assets.remove("XAUUSD")
        assets.insert(0, "XAUUSD")

    for asset in tqdm(assets):
        asset_dir = os.path.join(SOURCE_DIR, asset)
        target_path = os.path.join(TARGET_DIR, f"{asset}_45m.parquet")

        if os.path.exists(target_path):
            print(f"Skipping {asset}: Already exists.")
            continue

        files = glob.glob(os.path.join(asset_dir, "*_ticks.parquet"))
        if not files:
            continue

        files.sort()

        chunks = []
        for f in files:
            try:
                df_chunk = (
                    pl.scan_parquet(f)
                    .sort("timestamp")
                    .group_by_dynamic("timestamp", every="45m")
                    .agg(
                        [
                            pl.col("bid").last().alias(f"close_{asset}"),
                            pl.col("ask").last().alias(f"ask_{asset}"),
                            (pl.col("ask").mean() - pl.col("bid").mean()).alias(f"spread_{asset}"),
                        ]
                    )
                    .collect()
                )
                chunks.append(df_chunk)
            except Exception as e:
                print(f"Error reading {f}: {e}")

        if not chunks:
            continue

        try:
            full_df = pl.concat(chunks)
            final_df = (
                full_df.sort("timestamp")
                .group_by_dynamic("timestamp", every="45m")
                .agg(
                    [
                        pl.col(f"close_{asset}").last(),
                        pl.col(f"ask_{asset}").last(),
                        pl.col(f"spread_{asset}").mean(),
                    ]
                )
            )

            final_df.write_parquet(target_path)
            print(f"Saved {asset} ({len(final_df)} bars)")

            del chunks, full_df, final_df
            gc.collect()
        except Exception as e:
            print(f"Error reducing {asset}: {e}")


if __name__ == "__main__":
    build_all_45m_chunked()
