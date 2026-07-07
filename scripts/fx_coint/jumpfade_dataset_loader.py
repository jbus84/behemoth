"""Production dataset loader for the idiosyncratic jump-fade signal ("the metaloader").

Consolidates the ad hoc /tmp scripts from the 2026-07-07 investigation into one
reusable, tested module:
  - systematic, bug-free currency-leg decomposition (the AUDCAD sign bug found and
    fixed in jumpfade_metamodel.py is structurally impossible here -- see
    cross_legs())
  - month-by-month real-tick cost computation (bounded memory, not "load all 96
    months at once" which caused OOM kills during the investigation)
  - parametrized tick_root, so pointing this at IC Markets data (once available via
    scripts/download_mt5_ticks.py) instead of the HistData archive is a one-line
    change, not a rebuild

See project memory `project_fx_idiosyncratic_jump_fade` for the full history of
findings this consolidates: EURUSD is the only pair confirmed to survive real-tick
execution end to end; the session2 (12-18h UTC) x top-z-tercile interaction is the
leading refined candidate; GBPUSD's plain z>4 rule is cost-sensitive (fails on
HistData-measured spread, flips positive under IC-Markets-Raw-tier cost assumptions,
unconfirmed against real data).
"""

from __future__ import annotations

import datetime
import glob

import numpy as np
import polars as pl

from scripts.fx_coint.eurusd_cusum_probe import load_5m

H = 24  # 120min horizon, the validated default throughout this investigation
BIPOWER_WINDOW = 24
COMMISSION_BPS = 0.60  # $6/100k RT, the default used throughout; override per broker

USD_QUOTE = {"EUR", "GBP", "AUD", "NZD"}  # quoted as XXXUSD (X price in USD directly)
USD_BASE = {"JPY", "CHF", "CAD"}  # quoted as USDXXX (USD price in X)
USD_MAJORS = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD"]
USD_SIGN = {"EURUSD": -1, "GBPUSD": -1, "AUDUSD": -1, "NZDUSD": -1,
            "USDJPY": +1, "USDCHF": +1, "USDCAD": +1}


def _price_in_usd_leg(ccy: str) -> tuple[str, int]:
    if ccy in USD_QUOTE:
        return f"{ccy}USD", +1
    if ccy in USD_BASE:
        return f"USD{ccy}", -1
    raise ValueError(f"unknown currency {ccy!r} -- not in USD_QUOTE or USD_BASE")


def cross_legs(pair: str) -> list[tuple[str, int]]:
    """Systematic, bug-free leg decomposition for any 6-char cross AAABBB.
    cross_price = price_in_usd(AAA) / price_in_usd(BBB), so log-return =
    strength[AAA] - strength[BBB]. Verified against every pair tested in the
    2026-07-07 investigation (this is the corrected version of the formula that
    had a sign bug for AUDCAD in the original jumpfade_metamodel.py)."""
    base, quote = pair[:3], pair[3:]
    b_sym, b_sign = _price_in_usd_leg(base)
    q_sym, q_sign = _price_in_usd_leg(quote)
    return [(b_sym, b_sign), (q_sym, -q_sign)]


def _usd_proxy_for(target: str) -> pl.DataFrame:
    others = [m for m in USD_MAJORS if m != target]
    frames = []
    for s in others:
        d5 = load_5m(s).with_columns((pl.col("mid").log().diff() * USD_SIGN[s]).alias(f"u_{s}"))
        frames.append(d5.select("bucket", f"u_{s}"))
    out = frames[0]
    for f in frames[1:]:
        out = out.join(f, on="bucket", how="inner")
    return out.with_columns(pl.mean_horizontal([f"u_{s}" for s in others]).alias("common_proxy"))


def _leg_proxy_for(legs: list[tuple[str, int]]) -> pl.DataFrame:
    frames = []
    for sym, sign in legs:
        d5 = load_5m(sym).with_columns((pl.col("mid").log().diff() * sign).alias(f"l_{sym}"))
        frames.append(d5.select("bucket", f"l_{sym}"))
    out = frames[0].join(frames[1], on="bucket", how="inner")
    return out.with_columns(pl.sum_horizontal([f"l_{s}" for s, _ in legs]).alias("common_proxy"))


def build_full_idio_population(symbol: str) -> pl.DataFrame:
    """Build the FULL idiosyncratic jump population for a symbol, with NO z-threshold
    applied (caller filters afterward) -- includes bucket, ret, abs_z, idio_share,
    diurnal_scale, hh, common, idio. USD-factor decomposition for the 7 USD majors,
    leg-implied decomposition for any other cross."""
    df = load_5m(symbol)
    df = df.with_columns(
        pl.col("mid").log().diff().alias("ret"),
        (pl.col("bucket").dt.hour() * 2 + (pl.col("bucket").dt.minute() >= 30).cast(pl.Int32)).alias("hh"),
    )
    df = df.with_columns(pl.col("ret").abs().alias("abs_ret"))
    df = df.with_columns(pl.col("abs_ret").shift(1).over("hh").alias("shifted"))
    df = df.with_columns(
        pl.col("shifted").cum_sum().over("hh").alias("_cs"),
        pl.col("shifted").is_not_null().cum_sum().over("hh").alias("_n"),
    )
    df = df.with_columns((pl.col("_cs") / pl.col("_n")).alias("diurnal_scale"))
    df = df.filter(pl.col("_n") >= 30).filter(pl.col("diurnal_scale") > 0)

    abs_ret_np = df["abs_ret"].to_numpy()
    n = len(abs_ret_np)
    bp_sigma = np.full(n, np.nan)
    w = BIPOWER_WINDOW
    for i in range(w + 1, n):
        window = abs_ret_np[i - w:i]
        bp = np.mean(window[1:] * window[:-1]) * (np.pi / 2)
        bp_sigma[i] = np.sqrt(bp) if bp > 0 else np.nan
    df = df.with_columns(pl.Series("bp_sigma", bp_sigma))
    df = df.with_columns((pl.col("ret") / pl.col("bp_sigma")).alias("lm_z"))
    df = df.with_columns((pl.col("mid").log().shift(-H) - pl.col("mid").log()).alias(f"fwd_{H}"))

    valid = df.filter(pl.col("bp_sigma").is_not_null() & pl.col(f"fwd_{H}").is_not_null())
    if symbol in USD_MAJORS:
        proxy = _usd_proxy_for(symbol)
        sign = USD_SIGN[symbol]
        v = valid.join(proxy.select("bucket", "common_proxy"), on="bucket", how="inner")
        v = v.with_columns((sign * pl.col("common_proxy")).alias("common"))
    else:
        proxy = _leg_proxy_for(cross_legs(symbol))
        v = valid.join(proxy.select("bucket", "common_proxy"), on="bucket", how="inner")
        v = v.with_columns(pl.col("common_proxy").alias("common"))

    v = v.with_columns((pl.col("ret") - pl.col("common")).alias("idio"))
    v = v.filter(pl.col("idio").abs() > pl.col("common").abs())  # idiosyncratic-only
    v = v.with_columns(
        pl.col("lm_z").abs().alias("abs_z"),
        (pl.col("idio").abs() / (pl.col("idio").abs() + pl.col("common").abs() + 1e-12)).alias("idio_share"),
        (pl.col("bucket").dt.hour() // 6).alias("session_q"),
    )
    return v


def _month_tick_paths(tick_root: str, sym: str, year: int, month: int) -> list[str]:
    paths = []
    for y, m in [(year, month), (year, month + 1) if month < 12 else (year + 1, 1)]:
        files = glob.glob(f"{tick_root}/{sym}/{sym}_{y}{m:02d}_ticks.parquet")
        if files:
            paths.append(files[0])
    return paths


def build_expanded_realtick_dataset(
    symbol: str,
    z_min: float = 1.5,
    tick_root: str = "/Users/danielfisher/Desktop/tick",
    commission_bps: float = COMMISSION_BPS,
    horizon_min: int = 120,
) -> pl.DataFrame:
    """Build the real-tick-costed training dataset for a symbol: every idiosyncratic
    event with abs_z > z_min, real spread looked up at the actual entry/exit tick
    (not a flat average), processed month-by-month for bounded memory. Point
    `tick_root` at ~/Desktop/tick_icmarkets (once populated via
    scripts/download_mt5_ticks.py) to use real IC Markets spread data instead of
    HistData -- no other code changes needed.

    Returns columns: bucket, year, hh, session_q, abs_z, idio_share, diurnal_scale,
    gross_bps, cost_bps, net_bps, win.
    """
    idio = build_full_idio_population(symbol)
    idio = idio.filter(pl.col("abs_z") > z_min)
    idio = idio.with_columns(pl.col("bucket").dt.year().alias("year"), pl.col("bucket").dt.month().alias("month"))

    year_months = sorted({(r["year"], r["month"]) for r in idio.select("year", "month").to_dicts()})
    out_rows = []
    for y, m in year_months:
        paths = _month_tick_paths(tick_root, symbol, y, m)
        if not paths:
            continue
        ticks = pl.concat([pl.scan_parquet(p).select("timestamp", "spread", "mid") for p in paths]).sort("timestamp").collect()
        ts = ticks["timestamp"].to_numpy()
        spreads = ticks["spread"].to_numpy()
        mids = ticks["mid"].to_numpy()

        month_events = idio.filter((pl.col("year") == y) & (pl.col("month") == m))
        cols = ["bucket", "ret", "abs_z", "idio_share", "diurnal_scale", "hh", "session_q", "year"]
        for r in month_events.select(cols).to_dicts():
            t0 = r["bucket"]
            if t0.tzinfo is None:
                t0 = t0.replace(tzinfo=datetime.timezone.utc)
            sgn = np.sign(r["ret"])
            if sgn == 0:
                continue
            entry_t = np.datetime64(t0) + np.timedelta64(5, "m")
            exit_t = entry_t + np.timedelta64(horizon_min, "m")
            idx_e = np.searchsorted(ts, entry_t, side="left")
            idx_x = np.searchsorted(ts, exit_t, side="left")
            if idx_e >= len(ts) or idx_x >= len(ts):
                continue
            if abs((ts[idx_e] - entry_t) / np.timedelta64(1, "s")) > 90:
                continue
            if abs((ts[idx_x] - exit_t) / np.timedelta64(1, "s")) > 90:
                continue
            gross = -sgn * np.log(mids[idx_x] / mids[idx_e]) * 1e4
            cost = (spreads[idx_e] / mids[idx_e] * 1e4 + spreads[idx_x] / mids[idx_x] * 1e4) / 2 + commission_bps
            net_bps = gross - cost
            out_rows.append({
                "bucket": t0, "year": r["year"], "hh": r["hh"], "session_q": r["session_q"],
                "abs_z": r["abs_z"], "idio_share": r["idio_share"], "diurnal_scale": r["diurnal_scale"],
                "gross_bps": gross, "cost_bps": cost, "net_bps": net_bps, "win": net_bps > 0,
            })
        del ticks, ts, spreads, mids

    return pl.DataFrame(out_rows)
