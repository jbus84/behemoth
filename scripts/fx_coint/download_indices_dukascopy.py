#!/usr/bin/env python3
"""Download 6 index CFDs from Dukascopy via tick_vault for 2018-2025.

Unique symbols (avoiding duplicates):
- DJI    = Dow Jones / US30
- NDX    = NASDAQ-100 / NAS100
- SPX    = S&P 500 / US500
- UK100  = FTSE 100
- DEU30  = DAX / GER40
- JPN225 = Nikkei 225
"""

import asyncio
from datetime import datetime, UTC
from tick_vault import download_range

SYMBOLS = ["DJI", "NDX", "SPX", "UK100", "DEU30", "JPN225"]
START = datetime(2018, 1, 1, tzinfo=UTC)
END = datetime(2025, 12, 31, tzinfo=UTC)

async def main():
    for sym in SYMBOLS:
        print(f"\n=== Downloading {sym} ({START.date()} to {END.date()}) ===")
        try:
            await download_range(sym, start=START, end=END)
            print(f"  ✅ {sym}: DONE")
        except Exception as e:
            print(f"  ❌ {sym}: {type(e).__name__}: {str(e)[:120]}")
        # 15s delay between symbols to stay polite
        await asyncio.sleep(15)
    print("\nAll downloads complete!")

if __name__ == "__main__":
    asyncio.run(main())
