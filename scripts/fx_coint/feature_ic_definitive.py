"""Definitive feature-IC study — every tick-native feature class vs the N-bar
triple-barrier target, under ONE consistent protocol.

Consolidates IC that was scattered across six separate scans (ffd_feature_scan,
complementary_feature_scan, asymmetry_family_scan, deprado_feature_scan,
tickbar_native_features, engineered_lag_features), each of which used a different
target, control, horizon, and bar type — so the numbers were never comparable.

Scope (tick-bar table only): 1000-tick bars, pooled 5 ex-JPY majors. Features =
all classes computable natively on tick bars:
  - engineered-lag (16)            : reused from engineered_lag_features.build
  - tick-native microstructure     : quote_revisions, tick_burst, bar_return_sign,
                                      hl_pos_delta_tick, high/low_pos_tick, spread,
                                      tick_volume, abs_ibm
  - De Prado price-only (Ch17/18)  : adf_sup, cusum_csw, smt_exp, ent_sign
Flow/OFI, USD-residual, session, and De Prado Ch19 micro (vpin/kyle_t/...) need
flow bars (flow_ofi/n_ticks) and are out of scope for the tick-bar table.

Target: N-bar triple-barrier first-touch return, vol-scaled symmetric barriers
(1.0 * vol * sqrt(N)), swept over N in {1,5,10,20,30,50,100}. Events sampled once
per symbol and reused across N for comparability.

Per (feature x N), pooled over the 5 majors, reports:
  raw_ic     : Spearman IC of feature vs first-touch return
  partial_ic : partial IC controlling for ffd_0.1 (content orthogonal to reversion)
  oos_ic     : chrono 70/30 per-symbol HELD-OUT test IC (raw feature, no model)
  sign       : per-symbol raw-IC sign consistency (k/5)
  nov_ic     : non-overlap IC (every N-th event in time) — overlap-inflation guard
Significance is deliberately NOT reported (project decision: OOS is the arbiter).

Usage: uv run python scripts/fx_coint/feature_ic_definitive.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))
from deprado_feature_scan import adf_sup, cusum_csw, plugin_entropy_sign, smt_exp  # noqa: E402
from engineered_lag_features import build as build_eng  # noqa: E402
from triple_barrier import triple_barrier_core  # noqa: E402

DATA = "/Users/danielfisher/repositories/behemoth/data/tick_bars"
POOL = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF"]
SUFFIX = "1000tick"
N_GRID = [1, 5, 10, 20, 30, 50, 100]
N_EVENTS = 40000
TRAIN_FRAC = 0.70
CONTROL = "ffd_0.1"
MICRO = ["quote_revisions", "tick_burst", "bar_return_sign", "hl_pos_delta_tick",
         "high_pos_tick", "low_pos_tick", "spread", "tick_volume"]


def build_all(sym: str):
    """Reuse the engineered-lag build (16 feats + intra_bar_mom/hl_pos_frac) and
    extend with the remaining tick-native microstructure columns and the De Prado
    price-only structural/entropy features. Same timestamp sort order throughout."""
    logp, f, vol, bph = build_eng(sym)
    df = pd.read_parquet(f"{DATA}/{sym}_{SUFFIX}.parquet")
    t = pd.DatetimeIndex(pd.to_datetime(df["timestamp"])).tz_localize(None).astype("datetime64[ns]")
    o = np.argsort(t.view("int64"))
    for c in MICRO:
        f[c] = df[c].to_numpy()[o].astype(float)
    f["abs_ibm"] = np.abs(f["intra_bar_mom"])
    # De Prado price-only (Ch17 structural break + Ch18 entropy on the ffd-return sign)
    sp = pd.Series(logp)
    f["adf_sup"] = adf_sup(sp).to_numpy()
    f["cusum_csw"] = cusum_csw(sp).abs().to_numpy()
    f["smt_exp"] = smt_exp(sp).to_numpy()
    ffd_diff = pd.Series(np.diff(f[CONTROL], prepend=np.nan))
    f["ent_sign"] = plugin_entropy_sign(ffd_diff).to_numpy()
    return logp, f, vol, bph


def partial_ic(x, y, z):
    rxy = stats.spearmanr(x, y)[0]
    rxz = stats.spearmanr(x, z)[0]
    ryz = stats.spearmanr(y, z)[0]
    den = np.sqrt(max(1 - rxz**2, 1e-9) * max(1 - ryz**2, 1e-9))
    return (rxy - rxz * ryz) / den


def _tb_target(logp, vol, ev, n_tb):
    entry = ev + 1
    vert = np.minimum(entry + n_tb, len(logp) - 1)
    _, y, _, _ = triple_barrier_core(logp, entry, vert, 1.0 * vol[entry] * np.sqrt(n_tb))
    return y


def main():
    rng = np.random.default_rng(0)
    cache = {s: build_all(s) for s in POOL}
    # one event set per symbol, reused across all N
    evset = {}
    for s in POOL:
        logp, f, vol, bph = cache[s]
        n = len(logp)
        warm = int(96 * bph) + 60
        idx = np.arange(warm, n - max(N_GRID) - 3)
        idx = idx[np.isfinite(vol[idx + 1]) & (vol[idx + 1] > 0)]
        evset[s] = np.sort(rng.choice(idx, min(N_EVENTS, len(idx)), replace=False))

    feats = [k for k in cache[POOL[0]][1] if k != CONTROL]
    records = []
    for n_tb in N_GRID:
        targ = {s: _tb_target(cache[s][0], cache[s][2], evset[s], n_tb) for s in POOL}
        for fn in feats:
            raws, parts, oos, novs = [], [], [], []
            for s in POOL:
                _, f, _, _ = cache[s]
                ev = evset[s]
                x, y, z = f[fn][ev], targ[s], f[CONTROL][ev]
                ok = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
                x, y, z = x[ok], y[ok], z[ok]
                if len(x) < 500 or np.unique(x).size < 5:
                    continue
                raws.append(stats.spearmanr(x, y)[0])
                parts.append(partial_ic(x, y, z))
                cut = int(len(x) * TRAIN_FRAC)            # events are time-sorted
                if len(x) - cut > 200:
                    oos.append(stats.spearmanr(x[cut:], y[cut:])[0])
                xo, yo = x[::n_tb], y[::n_tb]              # non-overlap stride
                if len(xo) > 200:
                    novs.append(stats.spearmanr(xo, yo)[0])
            if len(parts) < 5:
                continue
            raws, parts = np.array(raws), np.array(parts)
            records.append(dict(
                feature=fn, N=n_tb,
                raw_ic=raws.mean(), partial_ic=parts.mean(),
                oos_ic=np.mean(oos) if oos else np.nan,
                sign=int((np.sign(raws) == np.sign(raws.mean())).sum()),
                nov_ic=np.mean(novs) if novs else np.nan))

    res = pd.DataFrame(records)
    # robustness gate, computed at EVERY N (not just 30):
    #   sign>=4/5 majors, non-overlap IC shares sign with partial IC, |partial|>0.004
    res["robust"] = (res["sign"] >= 4) & (np.sign(res["nov_ic"]) == np.sign(res["partial_ic"])) \
        & (res["partial_ic"].abs() > 0.004)
    out_dir = Path("reports/feature_ic_definitive")
    out_dir.mkdir(parents=True, exist_ok=True)
    res.to_csv(out_dir / "ic_records.csv", index=False)

    pd.set_option("display.width", 200, "display.max_rows", 400,
                  "display.float_format", lambda x: f"{x:8.4f}")
    print("=" * 100)
    print(f"DEFINITIVE FEATURE-IC STUDY — {SUFFIX}, pooled {len(POOL)} ex-JPY majors, "
          f"N-bar TB target, {N_EVENTS} events/sym")
    print("  control for partial IC = ffd_0.1 | sign = k/5 majors | OOS = chrono 30% holdout")
    print("=" * 100)
    for col in ["raw_ic", "partial_ic", "oos_ic"]:
        m = res.pivot(index="feature", columns="N", values=col)
        m = m.reindex(m.abs().max(axis=1).sort_values(ascending=False).index)
        print(f"\n--- {col}  (feature x N) ---")
        print(m.to_string())
    # robustness gate per N
    for n_tb in N_GRID:
        rN = res[n_tb == res.N].copy()
        rN = rN.reindex(rN.partial_ic.abs().sort_values(ascending=False).index)
        rob = rN[rN.robust]
        print(f"\n--- ROBUST @ N={n_tb} (sign>=4/5, non-overlap same sign, |partial|>0.004): "
              f"{len(rob)} features ---")
        if len(rob):
            print(rob[["feature", "raw_ic", "partial_ic", "oos_ic", "sign", "nov_ic"]].to_string(index=False))
    print(f"\nrecords -> {out_dir / 'ic_records.csv'}")


if __name__ == "__main__":
    main()
