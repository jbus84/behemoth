import argparse
import asyncio
import gc
import logging
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import numpy as np
import tick_vault.config
import tick_vault.download_worker
import tick_vault.fetcher
from dateutil.relativedelta import relativedelta
from tick_vault import download_range, read_tick_data
from tick_vault.fetcher import RetryableError

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("tick_vault_downloader")

DEFAULT_SYMBOLS = ["EURUSD", "GBPUSD", "AUDUSD", "USDCAD", "USDJPY", "USDCHF"]
GLOBAL_START_DATE = datetime(2018, 1, 1, tzinfo=UTC)

OUT_DIR = Path("/Users/danielfisher/Desktop/dukascopy_ticks")
TICKVAULT_CACHE = Path("/Users/danielfisher/Desktop/tickvault_ticks")
LOCK_FILE = TICKVAULT_CACHE / "download_tick_vault.lock"
NEW_YORK_TZ = ZoneInfo("America/New_York")


def is_fx_market_open(dt: datetime) -> bool:
    """True if FX markets are open with DST-aware New York session boundaries."""
    dt_utc = _normalize_utc(dt)
    close_utc, reopen_utc = get_session_bounds_utc(dt_utc)
    return not (close_utc <= dt_utc < reopen_utc)


def _normalize_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _friday_close_for_week(dt: datetime) -> datetime:
    dt_utc = _normalize_utc(dt)
    dt_ny = dt_utc.astimezone(NEW_YORK_TZ)
    days_to_friday = 4 - dt_ny.weekday()
    target = (dt_ny + relativedelta(days=days_to_friday)).replace(
        hour=17,
        minute=0,
        second=0,
        microsecond=0,
    )
    return target.astimezone(UTC)


def get_session_bounds_utc(dt: datetime) -> tuple[datetime, datetime]:
    """Return the UTC close and reopen bounds for the trading week containing dt."""
    close_utc = _friday_close_for_week(dt)
    reopen_utc = (close_utc.astimezone(NEW_YORK_TZ) + relativedelta(days=2)).astimezone(UTC)
    return close_utc, reopen_utc


def get_fetchable_end(now: datetime) -> datetime:
    """Return the latest timestamp that should be considered fetchable right now."""
    now_utc = _normalize_utc(now)
    if is_fx_market_open(now_utc):
        return now_utc
    close_utc, reopen_utc = get_session_bounds_utc(now_utc)
    if now_utc < reopen_utc:
        return close_utc
    return now_utc


def is_expected_weekend_gap(prev_ts: datetime, next_ts: datetime) -> bool:
    prev_utc = _normalize_utc(prev_ts)
    next_utc = _normalize_utc(next_ts)
    close_utc, reopen_utc = get_session_bounds_utc(prev_utc)
    close_window_start = close_utc - relativedelta(minutes=5)
    reopen_window_end = reopen_utc + relativedelta(minutes=5)
    return (
        close_window_start <= prev_utc <= close_utc and reopen_utc <= next_utc <= reopen_window_end
    )


def find_first_market_gap(path: Path) -> datetime:
    """Scan a parquet file for gaps > 2 hours during market hours."""
    import pandas as pd

    try:
        # Load timestamps
        df = pd.read_parquet(path, columns=["timestamp"])
        if df.empty:
            return None

        # Compute diffs
        df["diff"] = df["timestamp"].diff().dt.total_seconds()

        # Threshold: 2 hours (7200 seconds)
        gap_threshold = 7200
        gaps = df[df["diff"] > gap_threshold].copy()

        if gaps.empty:
            return None

        # Check if the gap started during market hours
        # Note: df["diff"] at index i is the gap BETWEEN i-1 and i
        # So the gap started at timestamp[i-1]
        for idx in gaps.index:
            prev_ts = df.loc[idx - 1, "timestamp"].to_pydatetime()
            next_ts = df.loc[idx, "timestamp"].to_pydatetime()
            if prev_ts.tzinfo is None:
                prev_ts = prev_ts.replace(tzinfo=UTC)
            if next_ts.tzinfo is None:
                next_ts = next_ts.replace(tzinfo=UTC)

            if is_expected_weekend_gap(prev_ts, next_ts):
                continue

            if is_fx_market_open(prev_ts) and is_fx_market_open(next_ts):
                return prev_ts

        return None
    except Exception:
        return None


def get_parquet_info(path: Path) -> tuple[datetime, float]:
    """Read the last timestamp and mid price from a parquet file."""
    import pandas as pd

    try:
        # We read the last row to get continuity
        df = pd.read_parquet(path, columns=["timestamp", "bid", "ask"])
        if df.empty:
            return None, None
        last_row = df.iloc[-1]
        last_ts_pd = last_row["timestamp"]
        # Ensure it's aware
        if hasattr(last_ts_pd, "tzinfo") and last_ts_pd.tzinfo is None:
            last_ts = last_ts_pd.tz_localize("UTC").to_pydatetime()
        else:
            last_ts = last_ts_pd.to_pydatetime()

        mid = (last_row["bid"] + last_row["ask"]) / 2.0
        return last_ts, mid
    except Exception:
        return None, None


def get_missing_months(
    symbol: str, out_dir: Path, end_date: datetime
) -> list[tuple[datetime, datetime]]:
    """Scan history and return a list of (start, end) ranges that need filling."""
    ranges_to_fill: list[tuple[datetime, datetime]] = []
    current = GLOBAL_START_DATE.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    sym_dir = out_dir / symbol

    now = datetime.now(tz=UTC)
    current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    fetchable_end = get_fetchable_end(now)

    while current <= end_date:
        yyyymm = current.strftime("%Y%m")
        out_path = sym_dir / f"{symbol}_{yyyymm}_ticks.parquet"
        month_end = min(current + relativedelta(months=1), end_date)

        if not out_path.exists():
            ranges_to_fill.append((current, month_end))
        elif current >= current_month_start:
            # Current month: check for gaps, then append up to fetchable_end
            first_gap = find_first_market_gap(out_path)
            if first_gap:
                logger.info(
                    f"[{symbol}] [{yyyymm}] Detected missing data hole starting at {first_gap}. Refilling..."
                )
                ranges_to_fill.append((first_gap, min(month_end, fetchable_end)))
            else:
                last_ts, _ = get_parquet_info(out_path)
                if last_ts:
                    fill_start = last_ts + relativedelta(microseconds=1000)
                    if fill_start < fetchable_end:
                        ranges_to_fill.append((fill_start, min(month_end, fetchable_end)))
        else:
            # Historical month: check for unexpected gaps, then suspicious early endings
            first_gap = find_first_market_gap(out_path)
            if first_gap:
                logger.info(
                    f"[{symbol}] [{yyyymm}] Detected missing data hole starting at {first_gap}. Refilling..."
                )
                ranges_to_fill.append((first_gap, month_end))
            else:
                last_ts, _ = get_parquet_info(out_path)
                if last_ts and is_fx_market_open(last_ts):
                    close_utc, _ = get_session_bounds_utc(last_ts)
                    boundary_tolerance = relativedelta(minutes=5)
                    near_month_end = last_ts + boundary_tolerance >= month_end
                    near_session_close = last_ts + boundary_tolerance >= close_utc
                    if last_ts < close_utc and not near_month_end and not near_session_close:
                        logger.info(
                            f"[{symbol}] [{yyyymm}] File ends early ({last_ts.time()}) on a market day. Refilling..."
                        )
                        ranges_to_fill.append(
                            (last_ts + relativedelta(microseconds=1000), month_end)
                        )

        current += relativedelta(months=1)

    return [(start, end) for start, end in ranges_to_fill if start < end]


def _list_process_commands() -> list[str]:
    result = subprocess.run(
        ["ps", "-ax", "-o", "command="],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def should_clear_stale_lock(lock_path: Path) -> bool:
    if not lock_path.exists():
        return False
    commands = _list_process_commands()
    return not any("scripts/download_tick_vault_data.py" in cmd for cmd in commands)


def _handle_existing_lock(lock_path: Path, force: bool) -> None:
    if not lock_path.exists() or force:
        return
    try:
        if should_clear_stale_lock(lock_path):
            logger.warning("Removing stale lockfile %s", lock_path)
            lock_path.unlink()
            return
    except Exception as exc:
        logger.warning("Could not verify stale lockfile %s: %s", lock_path, exc)
    logger.error(
        "Lockfile %s exists. Another instance might be running. Use --force to override.", lock_path
    )
    sys.exit(1)


async def process_symbol(symbol: str, end_date: datetime, out_dir: Path):
    logger.info(f"========== Processing {symbol} ==========")

    fill_ranges = get_missing_months(symbol, out_dir, end_date)

    if not fill_ranges:
        logger.info(f"[{symbol}] Data up to date. Skipping.")
        return

    logger.info(f"[{symbol}] Identified {len(fill_ranges)} ranges needing attention.")

    # Process each range: Download then Upsert
    logger.info(f"[{symbol}] Starting incremental fill...")

    # Set internal tick_vault logger to WARNING
    logging.getLogger("tick_vault").setLevel(logging.WARNING)

    sym_dir = out_dir / symbol
    sym_dir.mkdir(parents=True, exist_ok=True)

    for fill_start, fill_end in fill_ranges:
        month_start = fill_start.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        yyyymm = month_start.strftime("%Y%m")
        out_path = sym_dir / f"{symbol}_{yyyymm}_ticks.parquet"

        # 1. Download specifically for this gap
        logger.info(f"[{symbol}] [{yyyymm}] Downloading range [{fill_start} -> {fill_end}]...")
        await download_range(
            symbol=symbol,
            start=fill_start,
            end=fill_end,
            proxies=None,
        )

        # 2. Read new ticks
        try:
            new_df = read_tick_data(
                symbol=symbol, start=fill_start, end=fill_end, strict=False, show_progress=False
            )
        except Exception as e:
            logger.warning(f"[{symbol}] [{yyyymm}] Read failed: {e}")
            continue

        if new_df is None or new_df.empty:
            logger.info(f"[{symbol}] [{yyyymm}] No new data found for this range.")
            continue

        # 3. Merge with existing data if present
        new_df.rename(columns={"time": "timestamp"}, inplace=True)
        import pandas as pd

        if out_path.exists():
            try:
                existing_df = pd.read_parquet(out_path)
                df = pd.concat([existing_df, new_df], ignore_index=True)
                df.sort_values("timestamp", inplace=True)
                df.drop_duplicates(subset=["timestamp"], inplace=True)
            except Exception as e:
                logger.warning(f"[{symbol}] [{yyyymm}] Failed to merge with existing data: {e}")
                df = new_df
        else:
            df = new_df

        # 4. Recalculate features
        df["mid"] = (df["bid"] + df["ask"]) / 2.0
        df["spread"] = df["ask"] - df["bid"]
        df["log_return"] = (
            np.log(df["mid"] / df["mid"].shift(1)).replace([np.inf, -np.inf], np.nan).fillna(0.0)
        )

        # Enforce canonical schema ordering
        canonical_cols = ["timestamp", "bid", "ask", "mid", "spread", "log_return"]
        df[canonical_cols].to_parquet(out_path, index=False)
        logger.info(f"[{symbol}] [{yyyymm}] Range filled. Final count: {len(df)}")

        # Release memory
        del df
        gc.collect()


async def main():
    p = argparse.ArgumentParser(
        description="Quickly pull down tick data and save as canonical parquets."
    )
    p.add_argument(
        "--symbols", type=str, default=",".join(DEFAULT_SYMBOLS), help="Comma-separated symbols"
    )
    p.add_argument(
        "--out-dir", type=str, default=str(OUT_DIR), help="Output directory for parquets"
    )
    p.add_argument(
        "--cache-dir",
        type=str,
        default=str(TICKVAULT_CACHE),
        help="Base directory for tick_vault cache",
    )
    p.add_argument("--force", action="store_true", help="Ignore lockfile and force run")
    args = p.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",")]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    lock_file = cache_dir / "download_tick_vault.lock"
    _handle_existing_lock(lock_file, args.force)

    # Create lockfile
    lock_file.touch()
    try:
        # Reload config and propagate to all modules
        target_config_values = {
            "base_directory": cache_dir,
            "worker_per_proxy": 5,
            "fetch_max_retry_attempts": 10,
            "fetch_base_retry_delay": 2.0,
            "worker_queue_timeout": 7200.0,
        }

        tick_vault.config.reload_config(**target_config_values)
        new_config_obj = tick_vault.config.CONFIG

        for module_name, module in sys.modules.items():
            if module_name.startswith("tick_vault") and hasattr(module, "CONFIG"):
                # logger.info(f"Propagating new CONFIG to {module_name}")
                module.CONFIG = new_config_obj

        # Monkey-patch for _fetch to treat Protocol Errors as retryable
        original_fetch = tick_vault.fetcher._fetch

        async def patched_fetch(client, url):
            from tick_vault.fetcher import FetchError

            try:
                return await original_fetch(client, url)
            except RuntimeError as e:
                if "Protocol error" in str(e):
                    logger.warning(
                        f"!!! INTERCEPTED PROTOCOL ERROR for {url} !!! Mapping to RetryableError."
                    )
                    raise RetryableError(str(e)) from e

                if e.__cause__ and isinstance(e.__cause__, FetchError):
                    raise e.__cause__
                raise

        tick_vault.fetcher._fetch = patched_fetch
        for module_name, module in sys.modules.items():
            if (
                module_name.startswith("tick_vault")
                and hasattr(module, "_fetch")
                and module._fetch == original_fetch
            ):
                module._fetch = patched_fetch

        # Patch AsyncClient
        class PatchedAsyncClient(httpx.AsyncClient):
            def __init__(self, *args, **kwargs):
                kwargs.setdefault("timeout", httpx.Timeout(30.0, connect=10.0, read=30.0))
                kwargs.setdefault("follow_redirects", True)
                super().__init__(*args, **kwargs)

        tick_vault.download_worker.AsyncClient = PatchedAsyncClient

        end_date = datetime.now(tz=UTC)

        for symbol in symbols:
            retries = 3
            while retries > 0:
                try:
                    await process_symbol(symbol, end_date, out_dir)
                    break
                except KeyboardInterrupt:
                    logger.info("Download stopped by user.")
                    return
                except Exception as e:
                    retries -= 1
                    wait_time = 300
                    logger.error(
                        f"[{symbol}] Top-level process failed: {e}. Retries left: {retries}. Waiting {wait_time}s..."
                    )
                    if retries > 0:
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(f"[{symbol}] Max retries reached. Skipping symbol.")

        logger.info("All symbols processed successfully!")
    finally:
        # Remove lockfile
        if lock_file.exists():
            lock_file.unlink()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Program interrupted.")
