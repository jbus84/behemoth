import polars as pl
import time
import os
from macro_arbiter import MacroArbiter
from signal_logger import SignalLogger

def run_dry_run_simulation(dataset_path, simulated_delay=0.0):
    print(f"\n>>> STARTING DRY RUN SIMULATION (Source: {dataset_path}) <<<")
    
    # 1. Initialize Components
    arbiter = MacroArbiter()
    logger = SignalLogger(filename="dry_run_signals.json")
    
    if not os.path.exists(dataset_path):
        print("Dataset not found.")
        return

    # 2. Load Data (Simulate Live Feed)
    print("Loading data stream...")
    df = pl.read_parquet(dataset_path)
    
    # 3. Process Signals (Simulate Algorithm Cycle)
    print("Executing MacroArbiter Core...")
    t0 = time.time()
    df_signals = arbiter.calculate_signals(df)
    t1 = time.time()
    print(f"Core Processing Time: {t1-t0:.4f}s")
    
    # 4. Extract Events
    events = df_signals.filter(pl.col("combined_signal").is_not_null())
    
    print(f"Generated {len(events)} signals.")
    print("Dispatching to Signal Logger...")
    
    # 5. Simulate Dispatch Loop
    count = 0
    start_time = time.time()
    
    # We will simulate "processing" them
    for row in events.iter_rows(named=True):
        strategy_raw = row["combined_signal"]
        
        # Parse Strategy & Side
        if "LONG" in strategy_raw:
            direction = "BUY"
            strategy_name = strategy_raw.replace("_LONG", "")
        else:
            direction = "SELL"
            strategy_name = strategy_raw.replace("_SHORT", "")
            
        timestamp = str(row["timestamp"])
        price = row["NSXUSD_mid"]
        
        # Log Event
        logger.log_signal(
            strategy=strategy_name,
            action=direction,
            symbol="NSXUSD",
            price=price,
            timestamp=timestamp,
            metadata={
                "macro_energy": row["macro_energy"],
                "vol_30m": row["vol"],
                "consensus_up": row["consensus_up"],
                "consensus_down": row["consensus_down"]
            }
        )
        count += 1
        if simulated_delay > 0:
            time.sleep(simulated_delay)
        
    print(f"\n>>> DRY RUN COMPLETE <<<")
    print(f"Logged {count} events to logs/dry_run_signals.json")
    
    # Verify we caught Silence Trap signals
    silence_count = events.filter(pl.col("combined_signal").str.contains("SILENCE")).height
    print(f"Silence Trap Signals: {silence_count}")
    print(f"Paradox Signals:      {events.filter(pl.col('combined_signal').str.contains('PARADOX')).height}")

if __name__ == "__main__":
    # Use 2025 data (most relevant)
    path = "graph_dataset_1m_2025.parquet"
    if not os.path.exists(path):
        # Fallback to 2024
        path = "graph_dataset_1m_2024.parquet"
        
    if os.path.exists(path):
        run_dry_run_simulation(path)
    else:
        print("No dataset found.")
