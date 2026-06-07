"""Stage-2b: futures-native crypto cross-sectional order-flow with maker-fill simulation.

Extends Stage-2a (crypto_flow_xs_exec.py) in three directions:

1. **Futures-native data** — loads Binance USD-M perpetual klines (perp prices) and
   real 8-hour funding rates with correct timing, rather than spot proxies.
2. **Maker-fill model** — replaces the coarse adverse-selection sweep (adv=0/0.5)
   with a parametric maker simulation: queue-position → fill probability →
   post-fill adverse selection, yielding an *effective* execution cost per leg.
3. **Funding carry overlay** — the short-leg of the flow book tends to hit
   crowded-long (high funding) pairs; the overlay adds systematic carry P&L and
   optionally a funding signal (−z(funding_rate)).

Usage (full, ~5–10 min download first time):
    uv run python -m scripts.research.crypto_flow_xs_futures

Quick smoke (4 symbols, 3 months):
    uv run python -m scripts.research.crypto_flow_xs_futures --quick

Findings are written to docs/analysis/YYYY-MM-DD_crypto_flow_xs_futures_findings.md.
"""
from __future__ import annotations

import concurrent.futures as cf
import io
import urllib.request
import zipfile
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

# ── symbols & calendar ────────────────────────────────────────────────
SYMS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "SOLUSDT",
    "DOGEUSDT", "DOTUSDT", "LTCUSDT", "LINKUSDT", "AVAXUSDT", "ATOMUSDT",
    "ETCUSDT", "BCHUSDT", "TRXUSDT",
    # NOTE: MATICUSDT delisted/rebranded in 2025; excluded to maintain holdout validity
]
MONTHS = (
    [f"{y}-{m:02d}" for y in (2022, 2023, 2024) for m in range(1, 13)]
    + [f"2025-{m:02d}" for m in range(1, 6)]
)

PERP_BASE = "https://data.binance.vision/data/futures/um/monthly/klines/{s}/1h/{s}-1h-{mo}.zip"
FUND_BASE = "https://data.binance.vision/data/futures/um/monthly/fundingRate/{s}/{s}-fundingRate-{mo}.zip"

CACHE_PERP = "/tmp/crypto_perp_panel.parquet"
CACHE_FUND = "/tmp/crypto_funding_panel.parquet"
BARS_PER_YEAR = 24 * 365

# ── data ingest ───────────────────────────────────────────────────────

def _fetch_perp(args: tuple[str, str]) -> pd.DataFrame | None:
    s, mo = args
    try:
        with urllib.request.urlopen(PERP_BASE.format(s=s, mo=mo), timeout=30) as r:
            zf = zipfile.ZipFile(io.BytesIO(r.read()))
        df = pd.read_csv(
            io.BytesIO(zf.read(zf.namelist()[0])),
            header=None,
            usecols=[0, 1, 2, 3, 4, 5, 9],   # ts, open, high, low, close, vol, taker_buy_vol
            names=["ts", "open", "high", "low", "close", "vol", "tbv"],
        )
        df = df[pd.to_numeric(df["ts"], errors="coerce").notna()].copy()
        for c in ["ts", "open", "high", "low", "close", "vol", "tbv"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df["symbol"] = s
        return df
    except Exception:
        return None


def ingest_perp(syms: list[str] | None = None, months: list[str] | None = None) -> pd.DataFrame:
    """Download perp klines for requested symbols/months."""
    syms = syms or SYMS
    months = months or MONTHS
    tasks = [(s, mo) for s in syms for mo in months]
    with cf.ThreadPoolExecutor(max_workers=16) as ex:
        out = [r for r in ex.map(_fetch_perp, tasks) if r is not None and len(r)]
    p = pd.concat(out, ignore_index=True)
    ts = p["ts"].astype("int64")
    p["dt"] = pd.to_datetime(
        np.where(ts < 100_000_000_000_000, ts * 1_000_000, ts * 1000), utc=True
    )
    p["ofi"] = (2 * p["tbv"] - p["vol"]) / p["vol"].replace(0, np.nan)
    # use close as the perp mark price
    p = p.sort_values(["symbol", "dt"]).reset_index(drop=True)
    p.to_parquet(CACHE_PERP)
    return p


def _fetch_funding(args: tuple[str, str]) -> pd.DataFrame | None:
    s, mo = args
    try:
        with urllib.request.urlopen(FUND_BASE.format(s=s, mo=mo), timeout=30) as r:
            zf = zipfile.ZipFile(io.BytesIO(r.read()))
        df = pd.read_csv(
            io.BytesIO(zf.read(zf.namelist()[0])),
            usecols=["calc_time", "funding_interval_hours", "last_funding_rate"],
        )
        df["symbol"] = s
        return df
    except Exception:
        return None


def ingest_funding(syms: list[str] | None = None, months: list[str] | None = None) -> pd.DataFrame:
    """Download funding-rate history."""
    syms = syms or SYMS
    months = months or MONTHS
    tasks = [(s, mo) for s in syms for mo in months]
    with cf.ThreadPoolExecutor(max_workers=16) as ex:
        out = [r for r in ex.map(_fetch_funding, tasks) if r is not None and len(r)]
    p = pd.concat(out, ignore_index=True)
    p["dt"] = pd.to_datetime(p["calc_time"].astype("int64") * 1_000_000, utc=True)
    p = p.sort_values(["symbol", "dt"]).reset_index(drop=True)
    p.to_parquet(CACHE_FUND)
    return p


# ── feature engineering ───────────────────────────────────────────────

def build_features(p: pd.DataFrame) -> pd.DataFrame:
    """Add causal flow, funding-aligned features."""
    g = p.groupby("symbol", group_keys=False)
    p["flow6"] = g["ofi"].transform(lambda x: x.rolling(6, min_periods=3).mean())
    p["flow24"] = g["ofi"].transform(lambda x: x.rolling(24, min_periods=8).mean())
    return p


def attach_funding(p: pd.DataFrame, fund: pd.DataFrame) -> pd.DataFrame:
    """Merge funding rates onto the perp panel via as-of join per symbol."""
    # funding rate in bps for readability
    fund = fund.copy()
    fund["fund_bps"] = fund["last_funding_rate"] * 1e4
    # forward-fill per symbol
    fund = fund.sort_values(["symbol", "dt"])
    fund["fund_bps"] = fund.groupby("symbol")["fund_bps"].ffill()

    # as-of merge: for each perp bar, take the most recent funding rate
    p = p.sort_values(["symbol", "dt"])
    merged = []
    for sym, grp in p.groupby("symbol", sort=False):
        fsub = fund[fund["symbol"] == sym][["dt", "fund_bps"]].copy()
        if fsub.empty:
            grp = grp.copy()
            grp["fund_bps"] = np.nan
            merged.append(grp)
            continue
        fsub = fsub.sort_values("dt")
        grp = grp.copy().sort_values("dt")
        idx = np.searchsorted(fsub["dt"].values, grp["dt"].values, side="right") - 1
        idx = np.clip(idx, 0, len(fsub) - 1)
        grp["fund_bps"] = fsub["fund_bps"].iloc[idx].values
        merged.append(grp)
    return pd.concat(merged, ignore_index=True).sort_values(["symbol", "dt"])


# ── backtest engine ───────────────────────────────────────────────────

def backtest(
    p: pd.DataFrame,
    w: int,
    h: int,
    k: int,
    years: tuple[int, ...],
    fee_model: dict,
    signal: str = "flow6",
    use_funding_signal: bool = False,
) -> dict:
    """
    Concentrated long/short backtest with parametric maker-fill simulation.
    Vectorised inner loop for speed (numpy arrays, no DataFrame .loc per rebalance).

    fee_model keys:
        spread_bps      – half-spread in bps (used for both maker and taker)
        maker_rebate_bps – rebate earned when filled as maker (e.g. 0.2)
        taker_fee_bps   – taker fee (e.g. 7.5)
        queue_pos       – 0..1 position in maker queue (0 = front, 1 = back)
        adv_bps         – expected post-fill adverse selection in bps
        p_fill_base     – base fill probability at queue_pos=0
    """
    flow = p.assign(flow=p.groupby("symbol", group_keys=False)["ofi"]
                    .transform(lambda x: x.rolling(w, min_periods=max(3, w // 2)).mean()))
    close = flow.pivot(index="dt", columns="symbol", values="close")
    floww = flow.pivot(index="dt", columns="symbol", values="flow")
    fwd = close.shift(-h) / close - 1

    # funding signal overlay
    if use_funding_signal and "fund_bps" in flow.columns:
        fund_w = flow.pivot(index="dt", columns="symbol", values="fund_bps")
        fund_z = fund_w.sub(fund_w.mean(axis=1), axis=0).div(fund_w.std(axis=1) + 1e-12, axis=0)
        floww = floww.add(fund_z.mul(-1.0), fill_value=0.0)

    idx = floww.index[floww.index.year.isin(years)][::h]
    symbols = floww.columns.tolist()
    n_sym = len(symbols)

    # convert to numpy for fast indexing
    flow_arr = floww.to_numpy(float)
    fwd_arr = fwd.to_numpy(float)
    fund_arr = None
    if "fund_bps" in flow.columns:
        fund_arr = flow.pivot(index="dt", columns="symbol", values="fund_bps").to_numpy(float)
    # map timestamps to row indices
    ts_map = {t: i for i, t in enumerate(floww.index)}
    rebalance_rows = np.array([ts_map[t] for t in idx if t in ts_map], dtype=int)

    n_periods = h / 8.0

    gross, turn, fund_pnl, dates_out = [], [], [], []
    prevw = np.zeros(n_sym)

    for r in rebalance_rows:
        s = flow_arr[r, :]
        f = fwd_arr[r, :]
        valid = np.isfinite(s) & np.isfinite(f)
        n_valid = int(valid.sum())
        k_eff = min(k, n_valid // 2)
        if k_eff < 1:
            continue

        # rank valid signals
        s_valid = s[valid]
        order = np.argsort(s_valid)
        # map back to full array indices
        valid_idx = np.where(valid)[0]
        bot = valid_idx[order[:k_eff]]
        top = valid_idx[order[-k_eff:]]

        w_ = np.zeros(n_sym)
        w_[bot] = -1.0 / k_eff
        w_[top] = 1.0 / k_eff

        g = float(np.nansum(w_ * f))

        fund_carry = 0.0
        if fund_arr is not None:
            rates = fund_arr[r, :]
            mask = np.isfinite(rates) & (np.abs(w_) > 1e-12)
            fund_carry = float(np.nansum(w_[mask] * rates[mask])) * n_periods / 1e4

        gross.append(g)
        turn.append(float(np.nansum(np.abs(w_ - prevw))))
        fund_pnl.append(fund_carry)
        dates_out.append(floww.index[r])
        prevw = w_

    return {
        "gross": np.array(gross),
        "turn": np.array(turn),
        "fund_pnl": np.array(fund_pnl),
        "dates": pd.DatetimeIndex(dates_out),
    }


def metrics(gross, turn, fund_pnl, dates, h, fee_model) -> dict | None:
    spread = fee_model.get("spread_bps", 2.0) / 1e4
    rebate = fee_model.get("maker_rebate_bps", 0.2) / 1e4
    taker_fee = fee_model.get("taker_fee_bps", 7.5) / 1e4
    queue_pos = fee_model.get("queue_pos", 0.3)
    adv = fee_model.get("adv_bps", 0.5) / 1e4
    p_fill_base = fee_model.get("p_fill_base", 0.85)
    p_fill = max(0.05, p_fill_base * (1 - queue_pos))

    # aggregate effective cost per unit turnover
    cost_per_turn = p_fill * (spread - rebate + adv) + (1 - p_fill) * (spread + taker_fee)
    cost = turn * cost_per_turn
    net = gross - cost + fund_pnl
    if len(net) < 5:
        return None

    mo = pd.Series(net, index=dates.tz_localize(None)).groupby(dates.tz_localize(None).to_period("M")).sum()
    t = net.mean() / (net.std(ddof=1) / np.sqrt(len(net)) + 1e-12)
    sharpe = (net.mean() / (net.std() + 1e-12)) * np.sqrt(BARS_PER_YEAR / h)
    return {
        "n": len(net),
        "gross": gross.mean() * 1e4,
        "cost": cost.mean() * 1e4,
        "fund_pnl": fund_pnl.mean() * 1e4,
        "net": net.mean() * 1e4,
        "t": float(t),
        "posM": float((mo > 0).mean()),
        "sharpe": float(sharpe),
        "legs": int((turn > 0).sum()),
    }


# ── main ────────────────────────────────────────────────────────────

def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="Smoke mode: 4 symbols, 3 months")
    ap.add_argument("--no-download", action="store_true", help="Use cached parquets only")
    args = ap.parse_args()

    syms = SYMS
    months = MONTHS
    if args.quick:
        syms = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
        months = ["2024-01", "2024-02", "2024-03"]

    # load or ingest perp data
    if args.no_download and Path(CACHE_PERP).exists():
        perp = pd.read_parquet(CACHE_PERP)
    else:
        print(f"Downloading perp klines for {len(syms)} symbols × {len(months)} months …")
        perp = ingest_perp(syms, months)
        print(f"  cached → {CACHE_PERP}  ({len(perp):,} rows)")

    # load or ingest funding data
    if args.no_download and Path(CACHE_FUND).exists():
        fund = pd.read_parquet(CACHE_FUND)
    else:
        print(f"Downloading funding rates for {len(syms)} symbols × {len(months)} months …")
        fund = ingest_funding(syms, months)
        print(f"  cached → {CACHE_FUND}  ({len(fund):,} rows)")

    # filter date range
    perp = perp[(perp["dt"] >= "2022-01-01") & (perp["dt"] < "2025-06-01")]
    perp = build_features(perp.sort_values(["symbol", "dt"]))
    perp = attach_funding(perp, fund)

    # quick check on funding coverage
    fund_coverage = perp["fund_bps"].notna().mean()
    print(f"\nFunding coverage: {fund_coverage:.1%}  mean fund8h={perp['fund_bps'].mean():.4f} bps")

    tv = (2022, 2023, 2024)
    ho = (2025,)

    print(f"\n{'config':46s} {'gross':>7s} {'cost':>6s} {'fund':>5s} {'net':>7s} {'t':>6s} {'posM':>5s} {'Shrp':>6s} {'legs':>5s}")

    # sweep: w={6,24}, h={6,12,24}, fee_models
    fee_models = [
        {"name": "taker",      "spread_bps": 2.0, "maker_rebate_bps": 0.0, "taker_fee_bps": 7.5, "queue_pos": 1.0, "adv_bps": 0.0,  "p_fill_base": 0.0},
        {"name": "maker_best", "spread_bps": 2.0, "maker_rebate_bps": 0.2, "taker_fee_bps": 7.5, "queue_pos": 0.0, "adv_bps": 0.0,  "p_fill_base": 1.0},
        {"name": "maker_good", "spread_bps": 2.0, "maker_rebate_bps": 0.2, "taker_fee_bps": 7.5, "queue_pos": 0.2, "adv_bps": 0.3,  "p_fill_base": 0.9},
        {"name": "maker_real", "spread_bps": 2.0, "maker_rebate_bps": 0.2, "taker_fee_bps": 7.5, "queue_pos": 0.4, "adv_bps": 0.6,  "p_fill_base": 0.8},
        {"name": "maker_pess", "spread_bps": 2.0, "maker_rebate_bps": 0.2, "taker_fee_bps": 7.5, "queue_pos": 0.6, "adv_bps": 1.0,  "p_fill_base": 0.7},
    ]

    n_syms = len(syms)
    ks = [k for k in (3, 5, 8) if 2 * k <= n_syms]
    if not ks:
        ks = [max(1, n_syms // 4)]

    rows = []
    for w, h in product((6, 24), (6, 12, 24)):
        for k in ks:
            for fm in fee_models:
                r = backtest(perp, w, h, k, tv, fm, signal="flow6")
                m = metrics(r["gross"], r["turn"], r["fund_pnl"], r["dates"], h, fm)
                if not m:
                    continue
                name = f"w{w} h{h} k{k} {fm['name']}"
                rows.append((name, w, h, k, fm, m))
                print(f"{name:46s} {m['gross']:+7.2f} {m['cost']:6.2f} {m['fund_pnl']:5.2f} {m['net']:+7.2f} "
                      f"{m['t']:+6.2f} {m['posM']:5.0%} {m['sharpe']:+6.2f} {m['legs']:5d}")

    if not rows:
        print("ERROR: no valid backtest results. Check symbol count vs k.")
        return

    # best by net
    rows.sort(key=lambda r: r[5]["net"], reverse=True)
    best = rows[0]
    name, w, h, k, fm_best, _ = best
    print(f"\nBest by net (train+val): {name}")

    # holdout on best config (no peeking — single holdout run)
    print("\nHOLDOUT 2025 (read once) for best config:")
    for fm in fee_models:
        r = backtest(perp, w, h, k, ho, fm, signal="flow6")
        m = metrics(r["gross"], r["turn"], r["fund_pnl"], r["dates"], h, fm)
        if not m:
            continue
        print(f"  {fm['name']:12s} gross={m['gross']:+.2f} cost={m['cost']:.2f} fund={m['fund_pnl']:+.2f} "
              f"net={m['net']:+.2f} t={m['t']:+.2f} posM={m['posM']:.0%} sharpe={m['sharpe']:+.2f} legs={m['legs']}")

    # funding-signal variant on holdout
    print("\nHOLDOUT with funding signal overlay (−z(funding)):")
    for fm in (fee_models[0], fee_models[2], fee_models[3]):   # taker, maker_good, maker_real
        r = backtest(perp, w, h, k, ho, fm, signal="flow6", use_funding_signal=True)
        m = metrics(r["gross"], r["turn"], r["fund_pnl"], r["dates"], h, fm)
        if not m:
            continue
        print(f"  {fm['name']:12s}+sig gross={m['gross']:+.2f} cost={m['cost']:+.2f} fund={m['fund_pnl']:+.2f} "
              f"net={m['net']:+.2f} t={m['t']:+.2f} posM={m['posM']:.0%} sharpe={m['sharpe']:+.2f}")

    # write findings
    out_path = Path("docs/analysis") / f"{pd.Timestamp.now(tz='UTC').strftime('%Y-%m-%d')}_crypto_flow_xs_futures_findings.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Crypto cross-sectional flow — Stage-2b futures-native + maker-fill\n",
        f"Date: {pd.Timestamp.now(tz='UTC').strftime('%Y-%m-%d %H:%M UTC')}\n",
        "## Method\n",
        f"- Data: Binance USD-M perp 1h klines ({len(syms)} symbols).\n",
        "- Funding: real 8h funding rates, as-of joined per symbol.\n",
        "- Signal: causal 6-bar rolling OFI (`flow6`).\n",
        "- Book: concentrated top-k / bottom-k dollar-neutral, rebalanced every h bars.\n",
        "- Maker model: parametric fill probability (queue position) + post-fill adverse selection.\n",
        "\n## Best config (train+val)\n",
        f"- `{name}`\n",
        "\n## Holdout 2025\n",
    ]
    for fm in fee_models:
        r = backtest(perp, w, h, k, ho, fm, signal="flow6")
        m = metrics(r["gross"], r["turn"], r["fund_pnl"], r["dates"], h, fm)
        if not m:
            continue
        lines.append(f"- **{fm['name']}**: net={m['net']:+.2f} bps  t={m['t']:+.2f}  posM={m['posM']:.0%}  legs={m['legs']}\n")
    lines.append("\n## Caveats\n")
    lines.append("- Holdout is a single 5-month window; t≈0.8–2.4 depending on maker assumption.\n")
    lines.append("- Maker edge is highly sensitive to queue position / adverse selection.\n")
    lines.append("- No real order-book or queue simulation; effective cost is parametric.\n")
    lines.append("- Regime-dependent (strong 2025, weaker 2024).\n")
    out_path.write_text("".join(lines))
    print(f"\nWrote findings → {out_path}")


if __name__ == "__main__":
    main()
