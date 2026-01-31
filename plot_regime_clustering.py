import polars as pl
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import os

def plot_clustering():
    idx_name = "NSXUSD"
    input_file = f"full_year_dataset_{idx_name}.parquet"
    
    if not os.path.exists(input_file):
        print(f"Dataset {input_file} not found.")
        return
        
    df = pl.read_parquet(input_file)
    
    # Filter for Golden Zone (Neg Correlation < -0.2)
    golden_df = df.filter(pl.col("regime_corr_1h") < -0.2)
    
    # Convert to Pandas for plotting
    gdf = golden_df.select("timestamp").to_pandas()
    gdf['timestamp'] = pd.to_datetime(gdf['timestamp'])
    
    # 1. Daily Clustering (Time Series)
    daily_counts = gdf.resample('D', on='timestamp').size()
    
    # 2. Intraday Clustering (Hour of Day)
    intraday_counts = gdf.groupby(gdf['timestamp'].dt.hour).size()
    
    # Create Plot
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))
    
    # Plot 1: Daily Timeline
    ax1.bar(daily_counts.index, daily_counts.values, color='#1f77b4', alpha=0.7)
    ax1.set_title('Daily Frequency of "Golden Zone" Opportunities (2025)', fontsize=14)
    ax1.set_ylabel('Trade Count', fontsize=12)
    ax1.grid(True, alpha=0.3)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%b'))
    
    # Plot 2: Intraday Distribution
    ax2.bar(intraday_counts.index, intraday_counts.values, color='#ff7f0e', alpha=0.7)
    ax2.set_title('Intraday Clustering (London/NY Session Check)', fontsize=14)
    ax2.set_xlabel('Hour of Day (UTC)', fontsize=12)
    ax2.set_ylabel('Total Trade Count', fontsize=12)
    ax2.set_xticks(range(0, 24))
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    output_path = "docs/regime_clustering_2025.png"
    plt.savefig(output_path)
    print(f"Clustering plot saved to {output_path}")
    
    # Text Analysis
    print("\n--- Clustering Analysis ---")
    print(f"Most Active Month: {daily_counts.resample('M').sum().idxmax().strftime('%B')}")
    print(f"Most Active Hour (UTC): {intraday_counts.idxmax()}:00")
    print(f"Zero-Trade Days: {(daily_counts == 0).sum()} / {len(daily_counts)}")

if __name__ == "__main__":
    plot_clustering()
