import argparse
import asyncio
import gc
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx
import numpy as np
from dateutil.relativedelta import relativedelta

import tick_vault.config
import tick_vault.download_worker
import tick_vault.fetcher
from tick_vault import download_range, read_tick_data
from tick_vault.fetcher import RetryableError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("tick_vault_downloader")

DEFAULT_SYMBOLS = ["EURUSD", "GBPUSD", "AUDUSD", "USDCAD", "USDJPY", "USDCHF"]
START_DATE = datetime(2018, 1, 1, tzinfo=UTC)

OUT_DIR = Path("/Users/danielfisher/Desktop/dukascopy_ticks")
TICKVAULT_CACHE = "/Users/danielfisher/Desktop/tickvault_ticks"


async def process_symbol(symbol: str, end_date: datetime):
    logger.info(f"========== Processing {symbol} ==========")
    
    # 1. Download missing chunks using tick_vault
    logger.info(f"[{symbol}] Downloading raw data from {START_DATE.date()} to {end_date.date()}...")
    await download_range(
        symbol=symbol,
        start=START_DATE,
        end=end_date,
        proxies=None,
    )

    # 2. Extract into Parquet format, month by month
    logger.info(f"[{symbol}] Converting to canonical Parquet schemas...")
    
    # Set internal tick_vault logger to WARNING to avoid massive log aggregation in memory
    logging.getLogger("tick_vault").setLevel(logging.WARNING)
    
    current = START_DATE.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    sym_dir = OUT_DIR / symbol
    sym_dir.mkdir(parents=True, exist_ok=True)
    
    while current < end_date:
        next_month = current + relativedelta(months=1)
        month_end = min(next_month, end_date)
        
        yyyymm = current.strftime("%Y%m")
        out_path = sym_dir / f"{symbol}_{yyyymm}_ticks.parquet"
        
        if out_path.exists():
            logger.info(f"[{symbol}] {yyyymm} Parquet already exists, skipping.")
            current = next_month
            continue

        try:
            logger.info(f"[{symbol}] Extracting data for {yyyymm}...")
            df = read_tick_data(
                symbol=symbol,
                start=current,
                end=month_end,
                strict=False,
                show_progress=False
            )
        except ValueError as ve:
            # Handle specific known exceptions (e.g. no data in db) cleanly
            logger.warning(f"[{symbol}] Missing data or read failed for {yyyymm}: {ve}")
            current = next_month
            continue
        except Exception as e:
            logger.warning(f"[{symbol}] Failed to read data for {yyyymm}: {e}")
            current = next_month
            continue
            
        if df is None or df.empty:
            logger.info(f"[{symbol}] No data found for {yyyymm}.")
            current = next_month
            continue
            
        # Parse into canonical schema (Memory Optimized)
        df.rename(columns={"time": "timestamp"}, inplace=True)
        df["mid"] = (df["bid"] + df["ask"]) / 2.0
        df["spread"] = df["ask"] - df["bid"]
        
        df["log_return"] = (
            np.log(df["mid"] / df["mid"].shift(1))
            .replace([np.inf, -np.inf], np.nan)
            .fillna(0.0)
        )
        
        # Enforce canonical schema ordering and drop extra columns
        # We use a selection list to avoid a full copy if possible
        canonical_cols = ["timestamp", "bid", "ask", "mid", "spread", "log_return"]
        
        df[canonical_cols].to_parquet(out_path, index=False)
        logger.info(f"[{symbol}] Saved {len(df)} ticks to {out_path.name}")
        
        # Explicitly release memory
        del df
        gc.collect()
        
        current = next_month


async def main():
    p = argparse.ArgumentParser(description="Quickly pull down tick data and save as canonical parquets.")
    p.add_argument("--symbols", type=str, default=",".join(DEFAULT_SYMBOLS), help="Comma-separated symbols")
    p.add_argument("--out-dir", type=str, default=str(OUT_DIR), help="Output directory for parquets")
    p.add_argument("--cache-dir", type=str, default=TICKVAULT_CACHE, help="Base directory for tick_vault cache")
    args = p.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",")]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Reload config and propagate to all modules
    target_config_values = {
        'base_directory': Path(args.cache_dir),
        'worker_per_proxy': 5,
        'fetch_max_retry_attempts': 10,
        'fetch_base_retry_delay': 2.0,
        'worker_queue_timeout': 7200.0,
    }
    
    # 1. Update the official CONFIG object
    tick_vault.config.reload_config(**target_config_values)
    new_config_obj = tick_vault.config.CONFIG
    
    # 2. Force propagation to all modules that might have done `from .config import CONFIG`
    for module_name, module in sys.modules.items():
        if module_name.startswith("tick_vault") and hasattr(module, "CONFIG"):
            logger.info(f"Propagating new CONFIG to {module_name}")
            setattr(module, "CONFIG", new_config_obj)

    # 3. Robust Monkey-patch for _fetch to treat Protocol Errors as retryable
    original_fetch = tick_vault.fetcher._fetch

    async def patched_fetch(client, url):
        from tick_vault.fetcher import FetchError
        try:
            return await original_fetch(client, url)
        except RuntimeError as e:
            if "Protocol error" in str(e):
                msg = f"!!! INTERCEPTED PROTOCOL ERROR for {url} !!! Mapping to RetryableError for internal retry loop."
                print(msg) 
                logger.warning(msg)
                raise RetryableError(str(e)) from e
            
            # tick_vault bug: _fetch has a bare 'except Exception as e:' that catches its own 
            # FetchError subclasses (like RetryableError from 503s) and wraps them in RuntimeError.
            if e.__cause__ and isinstance(e.__cause__, FetchError):
                msg = f"!!! UNWRAPPED {type(e.__cause__).__name__} BUG for {url} !!! Restoring original error for retry loop."
                print(msg)
                logger.warning(msg)
                raise e.__cause__
                
            raise

    tick_vault.fetcher._fetch = patched_fetch
    
    # Ensure any module that might have imported _fetch specifically also gets the patch
    for module_name, module in sys.modules.items():
        if module_name.startswith("tick_vault") and hasattr(module, "_fetch"):
            if getattr(module, "_fetch") == original_fetch:
                logger.info(f"Patching _fetch reference in {module_name}")
                setattr(module, "_fetch", patched_fetch)
    
    # 4. Patch AsyncClient for timeout and resilience
    class PatchedAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs.setdefault('timeout', httpx.Timeout(30.0, connect=10.0, read=30.0))
            kwargs.setdefault('follow_redirects', True)
            super().__init__(*args, **kwargs)

    tick_vault.download_worker.AsyncClient = PatchedAsyncClient
    
    end_date = datetime.now(tz=UTC)
    
    for symbol in symbols:
        while True:
            try:
                await process_symbol(symbol, end_date)
                break
            except KeyboardInterrupt:
                logger.info("Download stopped by user.")
                return
            except Exception as e:
                wait_time = 120
                logger.error(f"[{symbol}] Top-level process failed: {e}. Retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)

    logger.info("All symbols processed successfully!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Program interrupted.")