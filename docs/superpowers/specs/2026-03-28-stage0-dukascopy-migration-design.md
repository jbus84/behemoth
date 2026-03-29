# Stage 0 Dukascopy Migration

## Goal

Replace the HistData tick download in `onboard_symbol.py` Stage 0a with the Dukascopy downloader (`download_tick_vault_data.py`), and fix the timestamp mode in Stages 0b/0c to handle Dukascopy's tz-naive UTC parquets.

## Architecture

Single-file change to `scripts/onboard_symbol.py`. No modifications to the download, tick-bar, or velocity scripts themselves.

## Changes

### Stage 0a: Download ticks

Replace the `download_histdata_ticks.py` invocation with `download_tick_vault_data.py --symbols {symbol}`.

The Dukascopy downloader is incremental and idempotent — it auto-detects gaps from `GLOBAL_START_DATE` (2018-01-01) to present and only fetches what's missing. The `months` parameter from `onboard_symbol.py` is not passed to the downloader.

The skip-existing check (lines 78-84) is simplified: since the downloader handles its own gap detection, we only need to check whether the symbol directory has any parquet files at all, or just always run the downloader (it's a no-op when data is complete). We'll keep a simple skip check but make it force-aware.

Before:
```python
_uv_run(
    "download_histdata_ticks.py",
    "--symbols", symbol,
    "--months", months,
    "--tick-root", str(TICK_ROOT),
    dry_run=dry_run,
    label="Stage 0a: Download HistData ticks",
)
```

After:
```python
_uv_run(
    "download_tick_vault_data.py",
    "--symbols", symbol,
    "--out-dir", str(TICK_ROOT),
    *(["--force"] if force else []),
    dry_run=dry_run,
    label="Stage 0a: Download Dukascopy ticks",
)
```

The skip-existing logic (checking latest month parquet) is removed — the downloader handles this internally. The `--force` flag maps to the downloader's `--force` (ignore lockfile).

### Stage 0b: Build global tick bars

Add `--timestamp-mode utc_naive` to the `build_global_tick_bars.py` invocation. Dukascopy parquets have tz-naive UTC timestamps; `utc_naive` mode tags them as UTC without conversion.

### Stage 0c: Build velocity dataset

Add `--timestamp-mode utc_naive` to the `build_tick_velocity_dataset.py` invocation. This is used when `--auto-build-bars` rebuilds bars from raw ticks.

### Docstring and module docstring

- `stage_0_data()` docstring: "Download ticks from HistData" → "Download ticks from Dukascopy"
- Module docstring: "Runs every step from HistData tick download" → "Runs every step from Dukascopy tick download"

## What Does Not Change

- `download_tick_vault_data.py` — no modifications
- `download_histdata_ticks.py` — left in place (unused, can be removed later)
- `build_global_tick_bars.py` — already supports `utc_naive` mode
- `build_tick_velocity_dataset.py` — already supports `utc_naive` mode
- All downstream stages (1-14) — tick bar output schema is identical
- `TICK_ROOT` constant — already points to `~/Desktop/dukascopy_ticks/`

## Testing

- `make onboard-symbol SYMBOL=EURUSD MONTHS=201801-202602 --dry-run` prints the correct Dukascopy command
- Stage 0b no longer fails with `timestamp_mode=as_utc requires timezone-aware UTC timestamps`
