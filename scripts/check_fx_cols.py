
import polars as pl

DATA_PATH = "data/pairs_1h_real/pairs_fx_1h_real.parquet"

def check_cols():
    try:
        df = pl.read_parquet(DATA_PATH)
        print("Columns:", df.columns)
    except Exception as e:
        print(e)

if __name__ == "__main__":
    check_cols()
