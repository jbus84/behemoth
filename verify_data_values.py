import polars as pl
import os

def check_values():
    p = "/Users/danielfisher/repositories/behemoth/graph_dataset_1m_2025.parquet"
    if os.path.exists(p):
        df = pl.read_parquet(p)
        mean_price = df["close"].mean()
        print(f"Mean Price in 2025: {mean_price:.2f}")
        
        if mean_price > 15000:
            print("Verdict: This is NASDAQ (NSX).")
        elif mean_price > 4000 and mean_price < 7000:
            print("Verdict: This is S&P 500 (SPX).")
        else:
            print("Verdict: Unknown Asset.")

if __name__ == "__main__":
    check_values()
