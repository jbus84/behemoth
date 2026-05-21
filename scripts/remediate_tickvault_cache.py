#!/usr/bin/env python3
"""Remove stale metadata entries from tick_vault cache so missing files can be re-downloaded."""

import argparse
import sqlite3
from pathlib import Path


def _bi5_path(cache_root: Path, symbol: str, ts: int) -> Path:
    """Reconstruct the expected .bi5 path from a Unix timestamp."""
    from datetime import UTC, datetime
    dt = datetime.fromtimestamp(ts, tz=UTC)
    return (
        cache_root
        / "downloads"
        / symbol
        / f"{dt.year:04d}"
        / f"{dt.month:02d}"
        / f"{dt.day:02d}"
        / f"{dt.hour:02d}h_ticks.bi5"
    )


def remediate_symbol(db_path: Path, cache_root: Path, symbol: str, dry_run: bool = True) -> int:
    table = f"symbol_{symbol}"
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")

    # Find timestamps in DB that have no .bi5 file on disk
    cursor = conn.execute(f"SELECT timestamp FROM {table}")
    stale = []
    for (ts,) in cursor:
        bi5 = _bi5_path(cache_root, symbol, ts)
        if not bi5.exists():
            stale.append(ts)

    if stale:
        print(f"  {symbol}: {len(stale):,} stale metadata entries found")
        if not dry_run:
            placeholders = ",".join("?" * len(stale))
            conn.execute(f"DELETE FROM {table} WHERE timestamp IN ({placeholders})", stale)
            conn.commit()
            print(f"  {symbol}: deleted {len(stale):,} stale entries")
    else:
        print(f"  {symbol}: no stale entries")

    conn.close()
    return len(stale)


def main() -> None:
    p = argparse.ArgumentParser(description="Remediate tickvault cache by removing stale metadata DB entries")
    p.add_argument("--cache-dir", default="/Users/danielfisher/Desktop/tickvault_ticks", help="Tick vault cache root")
    p.add_argument("--symbols", default="EURUSD,GBPUSD,AUDUSD,USDCAD,USDJPY,USDCHF", help="Comma-separated symbols")
    p.add_argument("--dry-run", action="store_true", default=True, help="Show what would be deleted without deleting")
    p.add_argument("--confirm", action="store_true", help="Actually delete stale entries (requires --confirm)")
    args = p.parse_args()

    cache_root = Path(args.cache_dir)
    db_path = cache_root / "metadata.db"
    symbols = [s.strip().upper() for s in args.symbols.split(",")]

    if not db_path.exists():
        print(f"Metadata DB not found: {db_path}")
        return

    dry_run = not args.confirm
    if dry_run:
        print("DRY RUN mode — no changes will be made. Use --confirm to delete.")

    total = 0
    for symbol in symbols:
        total += remediate_symbol(db_path, cache_root, symbol, dry_run=dry_run)

    print(f"\nTotal stale entries: {total:,}")
    if dry_run and total > 0:
        print("\nTo delete these entries and enable re-download, run with --confirm")


if __name__ == "__main__":
    main()
