#!/usr/bin/env python3
"""Download HistData tick ZIPs and convert to canonical parquet tick files.

Output schema per month:
- timestamp (UTC)
- bid
- ask
- mid
- spread
- log_return
"""

from __future__ import annotations

import argparse
import io
import re
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import timedelta, timezone
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

BASE_URL = "https://www.histdata.com"
DOWNLOAD_PAGE = (
    BASE_URL
    + "/download-free-forex-historical-data/?/ascii/tick-data-quotes/{symbol}/{year}/{month}/"
)
GET_ENDPOINT = BASE_URL + "/get.php"
SOURCE_TZ_POLICIES = {"america_new_york", "fixed_est", "as_utc_legacy"}


@dataclass(frozen=True)
class DownloadForm:
    tk: str
    date: str
    datemonth: str
    platform: str
    timeframe: str
    fxpair: str


def _parse_months(raw: str) -> list[str]:
    months = [m.strip() for m in str(raw).split(",") if m.strip()]
    out: list[str] = []
    for m in months:
        if not re.fullmatch(r"\d{6}", m):
            raise ValueError(f"bad month (expected YYYYMM): {m}")
        out.append(m)
    return out


def _parse_symbols(raw: str) -> list[str]:
    syms = [s.strip().upper() for s in str(raw).split(",") if s.strip()]
    for s in syms:
        if not re.fullmatch(r"[A-Z0-9]{6,10}", s):
            raise ValueError(f"bad symbol token: {s}")
    return syms


def _extract_hidden_value(html: str, name: str) -> str:
    pat = rf'name="{re.escape(name)}"[^>]*value="([^"]*)"'
    m = re.search(pat, html, flags=re.IGNORECASE)
    if not m:
        raise ValueError(f"failed to parse hidden field: {name}")
    return m.group(1).strip()


def _fetch_download_form(opener, symbol: str, yyyymm: str) -> DownloadForm:
    y = yyyymm[:4]
    m = str(int(yyyymm[4:6]))
    url = DOWNLOAD_PAGE.format(symbol=symbol.lower(), year=y, month=m)
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with opener.open(req, timeout=60) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    return DownloadForm(
        tk=_extract_hidden_value(html, "tk"),
        date=_extract_hidden_value(html, "date"),
        datemonth=_extract_hidden_value(html, "datemonth"),
        platform=_extract_hidden_value(html, "platform"),
        timeframe=_extract_hidden_value(html, "timeframe"),
        fxpair=_extract_hidden_value(html, "fxpair"),
    )


def _download_zip(opener, *, form: DownloadForm, referer: str) -> bytes:
    payload = urlencode(
        {
            "tk": form.tk,
            "date": form.date,
            "datemonth": form.datemonth,
            "platform": form.platform,
            "timeframe": form.timeframe,
            "fxpair": form.fxpair,
        }
    ).encode("utf-8")
    req = Request(
        GET_ENDPOINT,
        data=payload,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": referer,
        },
        method="POST",
    )
    with opener.open(req, timeout=120) as resp:
        blob = resp.read()
    if len(blob) < 4 or blob[:2] != b"PK":
        text = blob[:400].decode("utf-8", errors="replace")
        raise RuntimeError(f"non-zip response from HistData: {text!r}")
    return blob


def _infer_csv_member(names: Iterable[str], *, symbol: str, yyyymm: str) -> str:
    expected = f"DAT_ASCII_{symbol.upper()}_T_{yyyymm}.csv"
    for n in names:
        if n.upper() == expected.upper():
            return n
    for n in names:
        if str(n).lower().endswith(".csv"):
            return n
    raise FileNotFoundError(f"no CSV member in HistData ZIP for {symbol} {yyyymm}")


def _parse_source_tz_policy(raw: str) -> str:
    v = str(raw).strip().lower()
    if v not in SOURCE_TZ_POLICIES:
        allowed = ",".join(sorted(SOURCE_TZ_POLICIES))
        raise ValueError(f"invalid --source-tz-policy={raw!r}; allowed={allowed}")
    return v


def _convert_histdata_timestamps(raw: pd.Series, *, source_tz_policy: str) -> pd.Series:
    ts_naive = pd.to_datetime(raw, format="%Y%m%d %H%M%S%f", errors="coerce")
    policy = _parse_source_tz_policy(source_tz_policy)
    if policy == "as_utc_legacy":
        return ts_naive.dt.tz_localize("UTC")

    if policy == "fixed_est":
        source_tz = timezone(timedelta(hours=-5))
    else:
        source_tz = ZoneInfo("America/New_York")

    try:
        localized = ts_naive.dt.tz_localize(
            source_tz,
            ambiguous="infer",
            nonexistent="shift_forward",
        )
    except Exception:
        # Fallback path for ambiguous periods where sequence-based inference fails.
        localized = ts_naive.dt.tz_localize(
            source_tz,
            ambiguous=False,
            nonexistent="shift_forward",
        )
    return localized.dt.tz_convert("UTC")


def _to_parquet(
    blob: bytes,
    *,
    symbol: str,
    yyyymm: str,
    out_path: Path,
    source_tz_policy: str,
) -> int:
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        csv_name = _infer_csv_member(zf.namelist(), symbol=symbol, yyyymm=yyyymm)
        with zf.open(csv_name) as fp:
            df = pd.read_csv(
                fp,
                header=None,
                names=["datetime_raw", "bid", "ask", "volume"],
                usecols=[0, 1, 2],
                dtype={0: "string", 1: "float64", 2: "float64"},
            )
    if df.empty:
        out = pd.DataFrame(columns=["timestamp", "bid", "ask", "mid", "spread", "log_return"])
        out.to_parquet(out_path, index=False)
        return 0

    ts = _convert_histdata_timestamps(df["datetime_raw"], source_tz_policy=source_tz_policy)
    out = pd.DataFrame(
        {
            "timestamp": ts,
            "bid": pd.to_numeric(df["bid"], errors="coerce"),
            "ask": pd.to_numeric(df["ask"], errors="coerce"),
        }
    )
    out = (
        out.dropna(subset=["timestamp", "bid", "ask"])
        .sort_values("timestamp")
        .reset_index(drop=True)
    )
    out["mid"] = (out["bid"] + out["ask"]) / 2.0
    out["spread"] = out["ask"] - out["bid"]
    out["log_return"] = (
        np.log(out["mid"] / out["mid"].shift(1)).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    )
    out.to_parquet(out_path, index=False)
    return int(len(out))


def main() -> None:
    p = argparse.ArgumentParser(description="Download HistData ticks and convert to parquet")
    p.add_argument("--symbols", required=True, help="comma-separated symbols, e.g. EURUSD,GBPUSD")
    p.add_argument(
        "--months", required=True, help="comma-separated YYYYMM values, e.g. 202601,202602"
    )
    p.add_argument("--tick-root", default="/Users/danielfisher/Desktop/tick")
    p.add_argument("--skip-existing", default="true", help="true|false")
    p.add_argument(
        "--source-tz-policy",
        default="america_new_york",
        choices=sorted(SOURCE_TZ_POLICIES),
        help=(
            "Interpretation policy for HistData raw timestamps before UTC conversion: "
            "america_new_york (DST-aware), fixed_est (UTC-5 constant), as_utc_legacy."
        ),
    )
    args = p.parse_args()

    symbols = _parse_symbols(args.symbols)
    months = _parse_months(args.months)
    tick_root = Path(str(args.tick_root))
    skip_existing = str(args.skip_existing).strip().lower() in {"1", "true", "yes", "y"}
    source_tz_policy = _parse_source_tz_policy(str(args.source_tz_policy))

    cookie_jar = CookieJar()
    opener = build_opener(HTTPCookieProcessor(cookie_jar))

    total_rows = 0
    written = 0
    skipped = 0
    for symbol in symbols:
        sym_dir = tick_root / symbol
        sym_dir.mkdir(parents=True, exist_ok=True)
        for yyyymm in months:
            out_path = sym_dir / f"{symbol}_{yyyymm}_ticks.parquet"
            if skip_existing and out_path.exists():
                print(f"skip existing: {out_path}")
                skipped += 1
                continue

            referer = DOWNLOAD_PAGE.format(
                symbol=symbol.lower(), year=yyyymm[:4], month=str(int(yyyymm[4:6]))
            )
            form = _fetch_download_form(opener, symbol, yyyymm)
            if form.datemonth != yyyymm or form.fxpair.upper() != symbol:
                print(
                    f"warn: form mismatch for {symbol} {yyyymm}: "
                    f"datemonth={form.datemonth}, fxpair={form.fxpair}"
                )
            blob = _download_zip(opener, form=form, referer=referer)
            rows = _to_parquet(
                blob,
                symbol=symbol,
                yyyymm=yyyymm,
                out_path=out_path,
                source_tz_policy=source_tz_policy,
            )
            print(f"wrote {out_path} rows={rows}")
            total_rows += int(rows)
            written += 1

    print(
        f"done symbols={len(symbols)} months={len(months)} written={written} "
        f"skipped={skipped} total_rows={total_rows} source_tz_policy={source_tz_policy}"
    )


if __name__ == "__main__":
    main()
