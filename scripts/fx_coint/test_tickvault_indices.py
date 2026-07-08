#!/usr/bin/env python3
"""Test Dukascopy symbol names for indices via tick_vault."""

import asyncio
from datetime import datetime, UTC
from tick_vault import download_range

# Possible Dukascopy symbol names for indices
TEST_SYMBOLS = [
    "DJI",      # Dow Jones / US30
    "US30",     # Alternative
    "NDX",      # NASDAQ-100
    "NAS100",   # Alternative
    "SPX",      # S&P 500
    "US500",    # Alternative
    "UK100",    # FTSE 100
    "DEU30",    # DAX / GER40
    "GER40",    # Alternative
    "JPN225",   # Nikkei 225
]

async def test_symbol(sym):
    try:
        await download_range(sym, start=datetime(2024, 1, 1, tzinfo=UTC), end=datetime(2024, 1, 2, tzinfo=UTC))
        print(f"  ✅ {sym}: SUCCESS")
        return sym, True
    except Exception as e:
        print(f"  ❌ {sym}: {type(e).__name__}: {str(e)[:80]}")
        return sym, False

async def main():
    print("Testing Dukascopy index symbol names...")
    results = await asyncio.gather(*[test_symbol(s) for s in TEST_SYMBOLS])
    print("\nResults:")
    for sym, ok in results:
        print(f"  {sym}: {'FOUND' if ok else 'NOT FOUND'}")

if __name__ == "__main__":
    asyncio.run(main())
