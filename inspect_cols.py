import polars as pl
try:
    df = pl.read_parquet("/Users/danielfisher/repositories/behemoth/graph_dataset_1m_2023.parquet", n_rows=5)
    print("Columns:", df.columns)
except Exception as e:
    print(e)
