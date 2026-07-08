#!/usr/bin/env python3
"""Test Dukascopy index symbols ONE AT A TIME with delays to avoid rate limiting."""

import asyncio
from datetime import datetime, UTC
from tick_vault import download_range

TEST_SYMBOLS = [
    "DJI", "US30", "NDX", "NAS100", "SPX", "US500",
    "UK100", "DEU30", "GER40", "JPN225",
]

async def test_symbol(sym):
    try:
        await download_range(sym, start=datetime(2024, 1, 2, tzinfo=UTC), end=datetime(2024, 1, 3, tzinfo=UTC))
        print(f"  ✅ {sym}: DATA FOUND")
        return sym, True
    except Exception as e:
        msg = str(e)
        if "403" in msg or "Forbidden" in msg:
            print(f"  ❌ {sym}: BLOCKED (403)")
        elif "404" in msg or "Not Found" in msg:
            print(f"  ❌ {sym}: NO DATA (404)")
        elif "503" in msg:
            print(f"  ⚠️  {sym}: RATE LIMITED (503)")
        else:
            print(f"  ❌ {sym}: {type(e).__name__}: {msg[:60]}")
        return sym, False

async def main():
    print("Testing Dukascopy index symbols (one at a time, 5s delay)...")
    results = []
    for sym in TEST_SYMBOLS:
        result = await test_symbol(sym)
        results.append(result)
        await asyncio.sleep(5)  # delay between symbols
    print("\nResults:")
    for sym, ok in results:
        print(f"  {sym}: {'FOUND' if ok else 'NOT FOUND / BLOCKED'}")

if __name__ == "__main__":
    asyncio.run(main())
