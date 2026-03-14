import asyncio
import tick_vault.config
import tick_vault.fetcher
from tick_vault.fetcher import fetch_with_retry, RetryableError, FetchError

original_fetch = tick_vault.fetcher._fetch

async def patched_fetch(client, url):
    try:
        return await original_fetch(client, url)
    except RuntimeError as e:
        if "Protocol error" in str(e):
            print("Mapping protocol error to Retryable")
            raise RetryableError(str(e)) from e
            
        # Fix for the bug: tick_vault wraps its own exceptions
        if e.__cause__ and isinstance(e.__cause__, FetchError):
            print(f"Unwrapping {type(e.__cause__).__name__} from RuntimeError")
            raise e.__cause__
            
        raise

# Make sure it works
async def test():
    class MockResponse:
        status_code = 503
        headers = {}
        content = b""

    class MockClient:
        async def get(self, url):
            return MockResponse()

    client = MockClient()
    
    tick_vault.fetcher._fetch = patched_fetch
    
    tick_vault.fetcher.CONFIG.fetch_max_retry_attempts = 1
    tick_vault.fetcher.CONFIG.fetch_base_retry_delay = 0.1
    
    try:
        await fetch_with_retry(client, "http://test")
        print("Wait, it passed?")
    except RuntimeError as e:
        print(f"Failed with RuntimeError: {e}")

asyncio.run(test())
