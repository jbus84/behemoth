"""Regression signal hunt at 1/2/3/4h on FX majors, scored vs real-cost break-even IC.

Usage:
    uv run python scripts/fx_coint/reg_signal_hunt.py --freq all --symbol all
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from scipy.stats import spearmanr, t as _t_dist
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

PAIRS = ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCHF", "USDCAD"]
COST_BPS = {"EURUSD": 0.64, "GBPUSD": 0.63, "USDJPY": 0.80,
            "USDCAD": 0.97, "USDCHF": 1.05, "AUDUSD": 1.06}
FREQS = ["1h", "2h", "3h", "4h"]
FREQ_MINUTES = {"1h": 60, "2h": 120, "3h": 180, "4h": 240}
FEATURE_COLS = ["r_1", "mom_short", "mom_long", "rvol_24", "hour"]


def build_freq_bars(
    df_1m: pl.DataFrame, freq: str, session: tuple[int, int] = (7, 21)
) -> pd.DataFrame:
    t = df_1m.sort("bucket").with_columns(
        pl.col("mid").log().diff().alias("lr1"),
        pl.col("bucket").dt.truncate(freq).alias("bf"),
    )
    bars = (
        t.group_by("bf")
        .agg(
            pl.col("mid").last(),
            pl.col("n_ticks").sum(),
            (pl.col("lr1").std() * 1e4).alias("rvol_bps"),
        )
        .rename({"bf": "bucket"})
        .sort("bucket")
        .to_pandas()
    )
    bars["bucket"] = pd.to_datetime(bars["bucket"])
    # Apply session filter BEFORE computing contig so that contig reflects
    # true adjacency in the returned frame
    hour = bars["bucket"].dt.hour
    keep = (hour >= session[0]) & (hour < session[1]) & (bars["bucket"].dt.dayofweek < 5)
    bars = bars[keep].reset_index(drop=True)
    # Now compute contig on the filtered frame
    step = np.timedelta64(FREQ_MINUTES[freq], "m")
    prev = bars["bucket"].shift(1).to_numpy()
    bars["contig"] = (bars["bucket"].to_numpy() - prev) == step
    bars.loc[0, "contig"] = False
    return bars


def build_panel(bars: pd.DataFrame, vol_lookback: int = 24) -> pd.DataFrame:
    b = bars.reset_index(drop=True)
    mid = b["mid"].to_numpy()
    r = np.empty(len(b))
    r[0] = np.nan
    r[1:] = (np.log(mid[1:]) - np.log(mid[:-1])) * 1e4
    # break returns across non-contiguous bars
    r[~b["contig"].to_numpy()] = np.nan
    rs = pd.Series(r)

    feats = pd.DataFrame({"bucket": b["bucket"]})
    feats["r_1"] = rs.to_numpy()
    feats["mom_short"] = rs.rolling(5, min_periods=3).sum().to_numpy()
    feats["mom_long"] = rs.rolling(18, min_periods=9).sum().shift(5).to_numpy()
    feats["rvol_24"] = rs.rolling(vol_lookback, min_periods=vol_lookback // 2).std().shift(1).to_numpy()
    feats["hour"] = b["bucket"].dt.hour.astype(float).to_numpy()
    feats["sigma_h"] = feats["rvol_24"]  # trailing vol, known at decision time

    ret_next = rs.shift(-1).to_numpy()  # forward 1-bar return
    feats["ret_next_bps"] = ret_next
    feats["target_z"] = ret_next / feats["sigma_h"].to_numpy()

    finite = np.isfinite(feats[FEATURE_COLS].to_numpy()).all(axis=1)
    finite &= np.isfinite(feats["target_z"].to_numpy())
    finite &= feats["sigma_h"].to_numpy() > 0

    result = feats[finite]

    # Drop rows that come immediately after an index gap to preserve shift relationships
    if len(result) > 1:
        result_idx = result.index.to_numpy()
        gaps = np.where(np.diff(result_idx) != 1)[0] + 1  # +1 to get the row after the gap
        result = result.drop(result.index[gaps])

    return result.reset_index(drop=True)


def breakeven_ic(cost_bps: float, sigma_h_bps: float) -> float:
    return cost_bps / sigma_h_bps


def fit_and_eval(
    panel: pd.DataFrame, cost_bps: float, purge: int = 1, alpha: float = 1.0
) -> dict:
    n = len(panel)
    split = int(n * 0.7)
    train = panel.iloc[:split]
    test = panel.iloc[split + purge:]
    Xtr = train[FEATURE_COLS].to_numpy()
    Xte = test[FEATURE_COLS].to_numpy()
    ytr = train["target_z"].to_numpy()
    yte = test["target_z"].to_numpy()

    scaler = StandardScaler().fit(Xtr)
    model = Ridge(alpha=alpha).fit(scaler.transform(Xtr), ytr)
    pred_z = model.predict(scaler.transform(Xte))

    sigma_te = test["sigma_h"].to_numpy()
    pred_bps = pred_z * sigma_te
    actual_bps = test["ret_next_bps"].to_numpy()
    ic = spearmanr(pred_z, yte).statistic if len(yte) > 2 else float("nan")
    sigma_med = float(np.median(sigma_te))
    ic_star = breakeven_ic(cost_bps, sigma_med)
    return {
        "n_test": len(yte),
        "ic": float(ic),
        "ic_star": float(ic_star),
        "clears": bool(ic > ic_star),
        "pred_bps": pred_bps,
        "actual_bps": actual_bps,
        "hours": test["hour"].to_numpy(),
        "sigma_med": sigma_med,
    }


def eval_rules(
    pred_bps: np.ndarray, actual_bps: np.ndarray, cost_bps: float, size_cap: float = 3.0
) -> dict:
    pred = np.asarray(pred_bps, float)
    act = np.asarray(actual_bps, float)
    n = len(pred)

    net_a = float(np.mean(np.sign(pred) * act) - cost_bps) if n else float("nan")

    scale = np.median(np.abs(pred))
    if scale > 0:
        w = np.clip(pred / scale, -size_cap, size_cap)
        net_b = float(np.mean(w * act) - np.mean(np.abs(w)) * cost_bps)
    else:
        net_b = float("nan")

    gate = np.abs(pred) > cost_bps
    if gate.sum() > 0:
        net_c = float(np.mean(np.sign(pred[gate]) * act[gate] - cost_bps))
    else:
        net_c = float("nan")

    return {
        "netA": net_a,
        "netB": net_b,
        "netC": net_c,
        "n_trades_C": int(gate.sum()),
        "n_bars": n,
    }


def ic_pvalue(ic: float, n: int) -> float:
    if n <= 2 or not np.isfinite(ic) or abs(ic) >= 1.0:
        return float("nan")
    tstat = ic * np.sqrt((n - 2) / (1 - ic * ic))
    return float(2 * _t_dist.sf(abs(tstat), df=n - 2))


def bh_reject(pvals: list[float], q: float = 0.10) -> list[bool]:
    p = np.asarray(pvals, float)
    m = len(p)
    order = np.argsort(p)
    thresh = q * (np.arange(1, m + 1)) / m
    passed = p[order] <= thresh
    reject = np.zeros(m, bool)
    if passed.any():
        kmax = np.max(np.where(passed)[0])
        reject[order[: kmax + 1]] = True
    return reject.tolist()


def ic_by_hour(
    pred_bps: np.ndarray, actual_bps: np.ndarray, hours: np.ndarray
) -> dict[int, float]:
    out: dict[int, float] = {}
    for h in np.unique(hours).astype(int):
        m = hours == h
        if m.sum() >= 30:
            out[int(h)] = float(spearmanr(pred_bps[m], actual_bps[m]).statistic)
    return out


def run_cell(sym: str, freq: str) -> dict | None:
    src = _REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"
    if not src.exists():
        return None
    df_1m = pl.read_parquet(src)
    bars = build_freq_bars(df_1m, freq)
    panel = build_panel(bars)
    if len(panel) < 200:
        return None
    cost = COST_BPS[sym]
    res = fit_and_eval(panel, cost_bps=cost)
    rules = eval_rules(res["pred_bps"], res["actual_bps"], cost_bps=cost)
    return {
        "symbol": sym,
        "freq": freq,
        "n_test": res["n_test"],
        "ic": res["ic"],
        "ic_star": res["ic_star"],
        "clears": res["clears"],
        "pval": ic_pvalue(res["ic"], res["n_test"]),
        "netA": rules["netA"],
        "netB": rules["netB"],
        "netC": rules["netC"],
        "n_trades_C": rules["n_trades_C"],
        "sigma_med": res["sigma_med"],
        "_eval": res,  # retained for IC-by-hour printing in main()
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="all", choices=PAIRS + ["all"])
    ap.add_argument("--freq", default="all", choices=FREQS + ["all"])
    args = ap.parse_args()
    syms = PAIRS if args.symbol == "all" else [args.symbol]
    freqs = FREQS if args.freq == "all" else [args.freq]

    rows = [r for s in syms for f in freqs if (r := run_cell(s, f)) is not None]
    if not rows:
        print("No cells produced (missing data?).")
        return
    rej = bh_reject([r["pval"] for r in rows], q=0.10)
    for r, sig in zip(rows, rej):
        r["bh_sig"] = sig

    hdr = f"{'pair':>7} {'freq':>4} {'N':>6} {'IC':>7} {'IC*':>7} {'clr':>4} {'BH':>3} {'netA':>7} {'netB':>7} {'netC':>7} {'nC':>6}"
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(f"{r['symbol']:>7} {r['freq']:>4} {r['n_test']:>6} {r['ic']:>7.4f} "
              f"{r['ic_star']:>7.4f} {str(r['clears']):>4} {str(r['bh_sig']):>3} "
              f"{r['netA']:>+7.3f} {r['netB']:>+7.3f} {r['netC']:>+7.3f} {r['n_trades_C']:>6}")

    for r in rows:
        if r["clears"]:
            e = r["_eval"]
            curve = ic_by_hour(e["pred_bps"], e["actual_bps"], e["hours"])
            print(f"\nIC-by-hour {r['symbol']} {r['freq']}: "
                  + " ".join(f"{h}:{v:+.3f}" for h, v in sorted(curve.items())))


if __name__ == "__main__":
    main()
