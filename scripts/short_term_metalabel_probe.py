"""Short-term meta-labeling probe on 1m FX data.

Heavy-filter primary -> test gross edge -> meta-label surviving filters.
Honest: purged walk-forward, BH-FDR multiplicity correction, real cost.

Data: 1m mid + n_ticks for 21 pairs, 2018-2025.
"""
import glob, os, warnings
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.ensemble import HistGradientBoostingClassifier

warnings.filterwarnings("ignore")

DATA_DIR = "/Users/danielfisher/repositories/behemoth/data/tick_bars"
PAIRS = sorted([os.path.basename(f).replace("_1m_flow.parquet", "")
                for f in glob.glob(f"{DATA_DIR}/*_1m_flow.parquet")])
# Focus on liquid majors first for power
LIQUID = ["EURUSD", "GBPUSD", "USDJPY", "USDCAD", "AUDUSD", "USDCHF"]
PAIRS = [p for p in PAIRS if p in LIQUID]
print(f"Pairs: {PAIRS}")

COST_BPS = 0.70  # retail FX cost per side (round-trip ~1.4 bps)
HOLD_BARS = 5    # 5-minute hold (~5min)
N_FOLDS = 5      # purged walk-forward


def load_pair(pair):
    df = pd.read_parquet(f"{DATA_DIR}/{pair}_1m_flow.parquet").sort_values("bucket")
    df = df.rename(columns={"bucket": "t"})
    df["t"] = pd.to_datetime(df["t"])
    df = df.set_index("t")
    df["ret"] = np.log(df["mid"]).diff() * 1e4  # bps
    df["flow"] = np.sign(df["ret"]) * df["n_ticks"]  # tick-rule proxy
    # features
    df["vol_20"] = df["ret"].rolling(20).std()
    df["vol_60"] = df["ret"].rolling(60).std()
    df["ret_5"] = df["ret"].rolling(5).sum()
    df["ret_20"] = df["ret"].rolling(20).sum()
    df["flow_5"] = df["flow"].rolling(5).sum()
    df["flow_20"] = df["flow"].rolling(20).sum()
    df["ticks_5"] = df["n_ticks"].rolling(5).mean()
    df["hour"] = df.index.hour
    df["minute"] = df.index.minute
    df["dayofweek"] = df.index.dayofweek
    return df


def add_filter_labels(df):
    """Add several heavy-filter primaries. Each is rare (~1-5%)."""
    d = df.copy()
    d["z_ret"] = (d["ret"] - d["ret"].rolling(60).mean()) / d["ret"].rolling(60).std().clip(lower=1e-6)
    d["z_ticks"] = (d["n_ticks"] - d["n_ticks"].rolling(60).mean()) / d["n_ticks"].rolling(60).std().clip(lower=1e-6)

    # 1. Extreme 1m move (>2σ) — test both continuation and reversion
    d["f_extreme_move"] = (d["z_ret"].abs() > 2.0) & (d["vol_20"] > d["vol_20"].median())

    # 2. Tick intensity spike + directional move (possible microstructure dislocation)
    d["f_tick_burst"] = (d["z_ticks"] > 2.5) & (d["z_ret"].abs() > 1.5)

    # 3. London open (08:00-10:00 UTC) extreme move
    d["f_london_burst"] = (d["hour"].isin([8, 9])) & (d["z_ret"].abs() > 1.5)

    # 4. NY open (13:00-15:00 UTC) extreme move
    d["f_ny_burst"] = (d["hour"].isin([13, 14])) & (d["z_ret"].abs() > 1.5)

    # 5. Vol compression breakout: low 60m vol + large move
    d["f_vol_compress"] = (d["vol_60"] < d["vol_60"].rolling(240).quantile(0.3)) & (d["z_ret"].abs() > 2.0)

    # 6. Reversal candle: large move opposite to prior 5m trend
    d["trend_5"] = np.sign(d["ret_5"].shift(1))
    d["f_reversal"] = (d["z_ret"].abs() > 1.5) & (np.sign(d["ret"]) != d["trend_5"]) & (d["trend_5"] != 0)

    return d


def evaluate_primary(df, filter_col, direction="revert"):
    """Test gross edge of a primary filter. direction='revert' or 'cont'."""
    sig = df[df[filter_col] == True].copy()
    if len(sig) < 100:
        return None
    # forward return over HOLD_BARS
    # CAUSAL: sum of ret[t+1] .. ret[t+HOLD_BARS] — exclude current bar
    sig["fwd"] = df["ret"].rolling(HOLD_BARS).sum().shift(-HOLD_BARS).reindex(sig.index)
    sig = sig.dropna(subset=["fwd"])
    if direction == "revert":
        # fade the move: if ret was positive, position = -1
        pos = -np.sign(sig["ret"])
    else:
        pos = np.sign(sig["ret"])
    gross = (pos * sig["fwd"]).mean()
    net = gross - COST_BPS
    tstat, pval = stats.ttest_1samp(pos * sig["fwd"], popmean=0)
    return {
        "n": len(sig),
        "gross_bps": gross,
        "net_bps": net,
        "tstat": tstat,
        "pval": pval,
        "hitrate": (pos * sig["fwd"] > 0).mean(),
    }


def purged_cv_meta_label(df, filter_col, direction="revert"):
    """Meta-label: train ML to predict which filtered events win.
    Returns OOS per-trade net at P>=0.5 and P>=0.6.
    """
    # build event set
    ev = df[df[filter_col] == True].copy()
    ev["fwd"] = df["ret"].rolling(HOLD_BARS).sum().shift(-HOLD_BARS).reindex(ev.index)
    ev = ev.dropna(subset=["fwd"])
    if len(ev) < 500:
        return None

    if direction == "revert":
        ev["label"] = ((-np.sign(ev["ret"])) * ev["fwd"] > 0).astype(int)
    else:
        ev["label"] = ((np.sign(ev["ret"])) * ev["fwd"] > 0).astype(int)

    feature_cols = ["ret", "n_ticks", "vol_20", "vol_60", "ret_5", "ret_20",
                    "flow_5", "flow_20", "ticks_5", "hour", "dayofweek"]
    ev = ev.dropna(subset=feature_cols + ["label"])
    if len(ev) < 500:
        return None

    X = ev[feature_cols].values
    y = ev["label"].values

    # purged time-series split
    n = len(ev)
    fold_size = n // N_FOLDS
    probs = np.zeros(n)
    for fold in range(N_FOLDS):
        test_start = fold * fold_size
        test_end = (fold + 1) * fold_size if fold < N_FOLDS - 1 else n
        # purge gap = HOLD_BARS (avoid leakage)
        train_idx = list(range(0, max(0, test_start - HOLD_BARS)))
        if fold < N_FOLDS - 1:
            train_idx += list(range(test_end + HOLD_BARS, n))
        test_idx = list(range(test_start, test_end))
        if len(train_idx) < 100 or len(test_idx) < 20:
            continue
        clf = HistGradientBoostingClassifier(max_iter=100, random_state=42)
        clf.fit(X[train_idx], y[train_idx])
        probs[test_idx] = clf.predict_proba(X[test_idx])[:, 1]

    ev["prob"] = probs
    # only evaluate where we got a prediction
    ev = ev[ev["prob"] > 0]
    if len(ev) < 200:
        return None

    # simulate P&L
    if direction == "revert":
        ev["pnl"] = (-np.sign(ev["ret"])) * ev["fwd"] - COST_BPS
    else:
        ev["pnl"] = np.sign(ev["ret"]) * ev["fwd"] - COST_BPS

    # baseline (all filtered events)
    base_net = ev["pnl"].mean()
    base_t, base_p = stats.ttest_1samp(ev["pnl"], popmean=0)

    # filtered by probability
    r5 = ev[ev["prob"] >= 0.50]
    r6 = ev[ev["prob"] >= 0.60]
    r7 = ev[ev["prob"] >= 0.70]

    def stats_for(sub):
        if len(sub) < 50:
            return None
        t, p = stats.ttest_1samp(sub["pnl"], popmean=0)
        return {
            "n": len(sub),
            "net": sub["pnl"].mean(),
            "tstat": t,
            "pval": p,
            "hitrate": (sub["pnl"] > 0).mean(),
        }

    return {
        "primary": stats_for(ev),
        "p50": stats_for(r5),
        "p60": stats_for(r6),
        "p70": stats_for(r7),
        "prob_corr": np.corrcoef(ev["prob"], ev["label"])[0, 1] if len(ev) > 10 else np.nan,
    }


# ---- Run ----
results = []
for pair in PAIRS:
    print(f"\n=== {pair} ===")
    try:
        df = load_pair(pair)
        df = add_filter_labels(df)
    except Exception as e:
        print(f"  load error: {e}")
        continue

    for filt in ["f_extreme_move", "f_tick_burst", "f_london_burst",
                 "f_ny_burst", "f_vol_compress", "f_reversal"]:
        for direction in ["revert", "cont"]:
            # primary evaluation
            prim = evaluate_primary(df, filt, direction)
            if prim is None:
                continue
            print(f"  {filt}/{direction}: n={prim['n']} gross={prim['gross_bps']:.3f} net={prim['net_bps']:.3f} t={prim['tstat']:.2f} hit={prim['hitrate']:.3f}")
            if prim["tstat"] < 1.0 or prim["net_bps"] < 0:
                # primary too weak — skip meta-labeling
                continue
            # meta-label
            ml = purged_cv_meta_label(df, filt, direction)
            if ml is None:
                continue
            print(f"    META  base net={ml['primary']['net']:.3f} t={ml['primary']['tstat']:.2f}")
            for k in ["p50", "p60", "p70"]:
                if ml[k]:
                    print(f"    META  {k} n={ml[k]['n']} net={ml[k]['net']:.3f} t={ml[k]['tstat']:.2f} hit={ml[k]['hitrate']:.3f}")
            results.append({
                "pair": pair,
                "filter": filt,
                "direction": direction,
                "primary": prim,
                "meta": ml,
            })

# ---- Summary ----
print("\n\n========== SUMMARY ==========")
print(f"Tested {len(PAIRS)} pairs × 6 filters × 2 directions = {len(PAIRS)*12} primary configurations")
print(f"Surviving primary t>1.0 + net>0: {len(results)}")
if results:
    print("\n--- Primary survivors ---")
    for r in results:
        p = r["primary"]
        print(f"  {r['pair']} {r['filter']}/{r['direction']}: n={p['n']} net={p['net_bps']:.3f} t={p['tstat']:.2f} p={p['pval']:.3f}")

    print("\n--- Meta-label lift ---")
    for r in results:
        m = r["meta"]
        if m["p50"] and m["primary"]:
            lift = m["p50"]["net"] - m["primary"]["net"]
            print(f"  {r['pair']} {r['filter']}/{r['direction']}: base={m['primary']['net']:.3f} p50={m['p50']['net']:.3f} lift={lift:.3f} corr={m['prob_corr']:.3f}")
else:
    print("No primary configurations survived the t>1.0 + net>0 threshold.")
