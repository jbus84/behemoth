"""Stage-2a: crypto cross-sectional order-flow EXECUTION viability (research probe).

Tests whether turnover reduction + breadth (32 pairs) lets the validated gross OFI signal
clear cost. Verdict: no — gross (~1 bp) stays far below taker cost (~4 bp); maker is only
marginally positive at zero adverse selection (t≈0.4) and breakeven under 50% adverse
selection. Findings: docs/analysis/2026-06-07_crypto_flow_xs_exec_findings.md.

Network/data-dependent (reads /tmp/crypto_panel_ext.parquet from the 32-pair ingest); not
unit-tested. Run: `uv run python -m scripts.research.crypto_flow_xs_exec`.
"""
from __future__ import annotations

from itertools import product

import numpy as np
import pandas as pd

PANEL = "/tmp/crypto_panel_ext.parquet"
BARS_PER_YEAR = 24 * 365


def load() -> pd.DataFrame:
    p = pd.read_parquet(PANEL)
    ts = p["ts"].astype("int64")  # 2025 Binance klines use microsecond ts -> unit-detect
    p["dt"] = pd.to_datetime(np.where(ts < 100_000_000_000_000, ts * 1_000_000, ts * 1000), utc=True)
    return p[(p["dt"] >= "2022-01-01") & (p["dt"] < "2025-06-01")].sort_values(["symbol", "dt"])


def backtest(p: pd.DataFrame, w: int, h: int, k: int | None, scheme: str, years: tuple[int, ...]):
    """Return (gross[], turnover[], dates) for a dollar-neutral XS flow long/short.

    scheme='topk' (long top-k +1/k, short bottom-k -1/k) or 'proportional' (w ∝ XS z-score).
    Causal flow = w-bar rolling mean of OFI; non-overlapping rebalance every h bars.
    """
    flow = p.assign(flow=p.groupby("symbol", group_keys=False)["ofi"]
                    .transform(lambda x: x.rolling(w, min_periods=max(3, w // 2)).mean()))
    close = flow.pivot(index="dt", columns="symbol", values="close")
    floww = flow.pivot(index="dt", columns="symbol", values="flow")
    fwd = close.shift(-h) / close - 1
    idx = floww.index[floww.index.year.isin(years)][::h]
    kk = k or 3
    prevw = pd.Series(0.0, index=floww.columns)
    gross, turn, dates = [], [], []
    for t in idx:
        s = floww.loc[t].dropna()
        ft = fwd.loc[t]
        s = s[s.index.isin(ft.index[ft.notna()])]
        if len(s) < 2 * kk:
            continue
        if scheme == "topk":
            o = s.sort_values()
            w_ = pd.Series(0.0, index=floww.columns)
            w_[o.index[:kk]] = -1.0 / kk
            w_[o.index[-kk:]] = 1.0 / kk
        else:
            z = (s - s.mean()) / (s.std() + 1e-12)
            w_ = (z / (z.abs().sum() + 1e-12)).reindex(floww.columns).fillna(0.0)
        gross.append(float((w_ * fwd.loc[t].reindex(w_.index).fillna(0)).sum()))
        turn.append(float((w_ - prevw).abs().sum()))
        dates.append(t)
        prevw = w_
    return np.array(gross), np.array(turn), pd.DatetimeIndex(dates)


def metrics(gross, turn, dates, h, fee_bps, adv=0.0):
    cost = turn * fee_bps / 1e4
    net = gross * (1 - adv) - cost
    if len(net) < 5:
        return None
    mo = pd.Series(net, index=dates).groupby(dates.to_period("M")).sum()
    t = net.mean() / (net.std(ddof=1) / np.sqrt(len(net)) + 1e-12)
    sharpe = (net.mean() / (net.std() + 1e-12)) * np.sqrt(BARS_PER_YEAR / h)
    return {"n": len(net), "gross": gross.mean() * 1e4, "cost": cost.mean() * 1e4,
            "net": net.mean() * 1e4, "t": float(t), "posM": float((mo > 0).mean()),
            "sharpe": float(sharpe)}


def main() -> None:
    p = load()
    tv = (2022, 2023, 2024)
    print(f"{'config':34s} {'gross':>7s} {'cost':>6s} {'net':>7s} {'t':>6s} {'posM':>5s} {'Shrp':>6s}")
    rows = []
    for w, h, scheme in product((6, 24), (6, 12, 24, 48), ("topk", "proportional")):
        ks = (3, 5, 8) if scheme == "topk" else (None,)
        for k in ks:
            g, tu, d = backtest(p, w, h, k, scheme, tv)
            m = metrics(g, tu, d, h, 7.5)  # taker = gating
            if not m:
                continue
            name = f"w{w} h{h} {scheme}" + (f" k{k}" if k else "")
            rows.append((name, w, h, k, scheme, m))
            print(f"{name:34s} {m['gross']:+7.2f} {m['cost']:6.2f} {m['net']:+7.2f} "
                  f"{m['t']:+6.2f} {m['posM']:5.0%} {m['sharpe']:+6.2f}")
    rows.sort(key=lambda r: r[5]["net"], reverse=True)
    name, w, h, k, scheme, _ = rows[0]
    print(f"\nBest by taker net (train+val): {name}\nHOLDOUT 2025 (read once):")
    g, tu, d = backtest(p, w, h, k, scheme, (2025,))
    for fee, adv, lbl in ((7.5, 0.0, "taker"), (1.0, 0.0, "maker adv0"), (1.0, 0.5, "maker adv.5")):
        m = metrics(g, tu, d, h, fee, adv)
        print(f"  {lbl:12s} gross={m['gross']:+.2f} cost={m['cost']:.2f} net={m['net']:+.2f} "
              f"t={m['t']:+.2f} posM={m['posM']:.0%} sharpe={m['sharpe']:+.2f}")


if __name__ == "__main__":
    main()
