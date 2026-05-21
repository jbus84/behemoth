#!/usr/bin/env python3
"""
Parallel download script for multiple symbols.
Runs each symbol download in a separate process for true parallelism.
"""

import argparse
import asyncio
import subprocess
import sys
from pathlib import Path

DEFAULT_SYMBOLS = ["EURUSD", "GBPUSD", "AUDUSD", "USDCAD", "USDJPY", "USDCHF"]


def run_symbol_download(symbol: str, force: bool = False) -> subprocess.Popen:
    """Launch a download process for a single symbol."""
    cmd = [
        sys.executable,
        "scripts/download_tick_vault_data.py",
        "--symbols", symbol,
    ]
    if force:
        cmd.append("--force")

    log_file = Path(f"/tmp/download_{symbol.lower()}.log")

    return subprocess.Popen(
        cmd,
        stdout=open(log_file, "w"),
        stderr=subprocess.STDOUT,
    )


async def main():
    parser = argparse.ArgumentParser(description="Download tick data for multiple symbols in parallel")
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS, help="Symbols to download")
    parser.add_argument("--force", action="store_true", help="Force re-download")
    parser.add_argument("--max-concurrent", type=int, default=3, help="Max concurrent downloads (default: 3)")

    args = parser.parse_args()

    symbols = args.symbols
    max_concurrent = args.max_concurrent

    print(f"Starting parallel download for: {', '.join(symbols)}")
    print(f"Max concurrent: {max_concurrent}")

    # Run downloads in batches
    processes = []
    for i in range(0, len(symbols), max_concurrent):
        batch = symbols[i:i + max_concurrent]
        print(f"\nStarting batch: {', '.join(batch)}")

        # Start batch
        batch_processes = []
        for symbol in batch:
            proc = run_symbol_download(symbol, args.force)
            batch_processes.append((symbol, proc))
            processes.append((symbol, proc))

        # Wait for batch to complete
        for symbol, proc in batch_processes:
            proc.wait()
            print(f"  {symbol}: Done (exit code: {proc.returncode})")

    print("\nAll downloads complete!")

    # Print summary
    print("\nSummary:")
    for symbol, proc in processes:
        status = "✅" if proc.returncode == 0 else "❌"
        print(f"  {status} {symbol}")


if __name__ == "__main__":
    asyncio.run(main())
