"""Build a real-tick-costed, expanded-population (z>1.5, not the hard z>4 jump gate)
training dataset for EURUSD, processed month-by-month to keep memory bounded (loading
all 96 months of tick data at once is what killed the earlier full-population run).

Output: parquet with bucket, year, hh, abs_z, idio_share, diurnal_scale, net_bps, win
-- ready to feed into a purged walk-forward CatBoost meta-model.
"""

from __future__ import annotations

import datetime
import glob

import numpy as np
import polars as pl

COMMISSION = 0.60
Z_MIN = 1.5
H = 24
SYM = "EURUSD"


def month_tick_path(sym: str, year: int, month: int) -> str:
    files = glob.glob(f"/Users/danielfisher/Desktop/tick/{sym}/{sym}_{year}{month:02d}_ticks.parquet")
    return files[0] if files else ""


def main() -> None:
    idio = pl.read_parquet("/tmp/eurusd_full_idio.parquet")
    idio = idio.with_columns(
        (pl.col("idio").abs() / (pl.col("idio").abs() + pl.col("common").abs() + 1e-12)).alias("idio_share")
    )
    idio = idio.filter(pl.col("abs_z") > Z_MIN)
    idio = idio.with_columns(pl.col("bucket").dt.year().alias("year"), pl.col("bucket").dt.month().alias("month"))
    print(f"expanded population: n={idio.height}")

    year_months = sorted({(r["year"], r["month"]) for r in idio.select("year", "month").to_dicts()})
    print(f"months to process: {len(year_months)}")

    out_rows = []
    for y, m in year_months:
        this_path = month_tick_path(SYM, y, m)
        ny, nm = (y, m + 1) if m < 12 else (y + 1, 1)
        next_path = month_tick_path(SYM, ny, nm)
        paths = [p for p in [this_path, next_path] if p]
        if not paths:
            continue
        ticks = pl.concat([pl.scan_parquet(p).select("timestamp", "spread", "mid") for p in paths]).sort("timestamp").collect()
        ts = ticks["timestamp"].to_numpy()
        spreads = ticks["spread"].to_numpy()
        mids = ticks["mid"].to_numpy()

        month_events = idio.filter((pl.col("year") == y) & (pl.col("month") == m))
        for r in month_events.select("bucket", "ret", "abs_z", "idio_share", "diurnal_scale", "hh", "year").to_dicts():
            t0 = r["bucket"]
            if t0.tzinfo is None:
                t0 = t0.replace(tzinfo=datetime.timezone.utc)
            sgn = np.sign(r["ret"])
            if sgn == 0:
                continue
            entry_t = np.datetime64(t0) + np.timedelta64(5, "m")
            exit_t = entry_t + np.timedelta64(120, "m")
            idx_e = np.searchsorted(ts, entry_t, side="left")
            idx_x = np.searchsorted(ts, exit_t, side="left")
            if idx_e >= len(ts) or idx_x >= len(ts):
                continue
            if abs((ts[idx_e] - entry_t) / np.timedelta64(1, "s")) > 90:
                continue
            if abs((ts[idx_x] - exit_t) / np.timedelta64(1, "s")) > 90:
                continue
            gross = -sgn * np.log(mids[idx_x] / mids[idx_e]) * 1e4
            cost = (spreads[idx_e] / mids[idx_e] * 1e4 + spreads[idx_x] / mids[idx_x] * 1e4) / 2 + COMMISSION
            net_bps = gross - cost
            out_rows.append({
                "bucket": t0, "year": r["year"], "hh": r["hh"], "abs_z": r["abs_z"],
                "idio_share": r["idio_share"], "diurnal_scale": r["diurnal_scale"],
                "gross_bps": gross, "cost_bps": cost,
                "net_bps": net_bps, "win": net_bps > 0,
            })
        del ticks, ts, spreads, mids
        print(f"  {y}-{m:02d}: {len(out_rows)} total events so far", flush=True)

    out = pl.DataFrame(out_rows)
    out.write_parquet("/tmp/eurusd_expanded_realtick_dataset.parquet")
    print(f"\nDONE: {out.height} events with real-tick net_bps, saved to /tmp/eurusd_expanded_realtick_dataset.parquet")


if __name__ == "__main__":
    main()
