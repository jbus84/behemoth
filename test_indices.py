import asyncio
from datetime import datetime, UTC
from tick_vault import download_range

async def test():
    for sym in ['DJI', 'NDX', 'SPX', 'UK100', 'DEU30', 'JPN225']:
        try:
            await download_range(sym, start=datetime(2024, 1, 2, tzinfo=UTC), end=datetime(2024, 1, 3, tzinfo=UTC))
            print(f'{sym}: OK')
        except Exception as e:
            print(f'{sym}: {type(e).__name__}: {str(e)[:60]}')
        await asyncio.sleep(5)

asyncio.run(test())
