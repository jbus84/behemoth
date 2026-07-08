"""Cross-sectional microstructure anomaly probe on 1m FX data.

Core idea: FX pairs move together via common USD factor. Anomalies = pairs that deviate
from the cross-sectional state. Bet on convergence (mean-reversion of the deviation).

All 21 pairs, 2018-2025. Rigorous causal construction. No look-ahead.
"""
import glob, os, warnings
import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore")

DATA_DIR = "/Users/danielfisher/repositories/behemoth/data/tick_bars"
PAIRS = sorted([os.path.basename(f).replace("_1m_flow.parquet", "")
                for f in glob.glob(f"{DATA_DIR}/*_1m_flow.parquet")])
print(f"Pairs: {len(PAIRS)} -> {PAIRS}")

COST_BPS = 0.70
HOLD_BARS = 5  # 5-minute hold
MIN_EVENTS = 500


def load_all_pairs():
    """Load all pairs into aligned 1m panel."""
    frames = {}
    for p in PAIRS:
        df = pd.read_parquet(f"{DATA_DIR}/{p}_1m_flow.parquet").sort_values("bucket")
        df = df.rename(columns={"bucket": "t", "mid": p})
        df = df.set_index("t")[[p, "n_ticks"]]
        df[f"{p}_ret"] = np.log(df[p]).diff() * 1e4
        frames[p] = df

    # Align on common timestamps
    idx = frames[PAIRS[0]].index
    for p in PAIRS[1:]:
        idx = idx.intersection(frames[p].index)
    idx = pd.DatetimeIndex(sorted(idx))
    print(f"Common timestamps: {len(idx)} ({idx.min()} to {idx.max()})")

    panel = pd.DataFrame(index=idx)
    rets = pd.DataFrame(index=idx)
    ticks = pd.DataFrame(index=idx)
    for p in PAIRS:
        panel[p] = frames[p].loc[idx, p]
        rets[p] = frames[p][f"{p}_ret"].reindex(idx)
        ticks[p] = frames[p]["n_ticks"].reindex(idx)

    # Drop first bar (NaN ret)
    panel = panel.iloc[1:]
    rets = rets.iloc[1:]
    ticks = ticks.iloc[1:]
    idx = idx[1:]
    return panel, rets, ticks, idx


def build_xs_features(rets, ticks, idx):
    """Build cross-sectional anomaly features per minute."""
    # Cross-sectional median return (common factor proxy)
    xs_med = rets.median(axis=1)
    xs_mean = rets.mean(axis=1)
    xs_std = rets.std(axis=1).clip(lower=1e-6)

    # Cross-sectional median tick intensity
    tick_med = ticks.median(axis=1)
    tick_std = ticks.std(axis=1).clip(lower=1e-6)

    features = {}
    for p in PAIRS:
        # Deviation from cross-sectional median (anomaly signal)
        dev = rets[p] - xs_med
        dev_z = dev / xs_std

        # Tick intensity deviation
        tick_dev = (ticks[p] - tick_med) / tick_std

        # Rolling stats for each pair
        r = rets[p]
        vol_20 = r.rolling(20).std().clip(lower=1e-6)
        vol_60 = r.rolling(60).std().clip(lower=1e-6)
        ret_5 = r.rolling(5).sum()
        ret_20 = r.rolling(20).sum()

        # Pair-specific vol rank vs historical
        vol_rank = (vol_20 - vol_20.rolling(240).mean()) / vol_20.rolling(240).std().clip(lower=1e-6)

        features[p] = pd.DataFrame({
            "t": idx,
            "ret": r.values,
            "xs_med": xs_med.values,
            "xs_std": xs_std.values,
            "dev": dev.values,
            "dev_z": dev_z.values,
            "tick_dev": tick_dev.values,
            "vol_20": vol_20.values,
            "vol_60": vol_60.values,
            "ret_5": ret_5.values,
            "ret_20": ret_20.values,
            "hour": idx.hour,
            "minute": idx.minute,
            "dayofweek": idx.dayofweek,
        })
    return features


def evaluate_filter(features, filter_fn, label=""):
    """Evaluate a cross-sectional filter across all pairs."""
    all_pnls = []
    all_gross = []
    pair_stats = []
    n_events_total = 0

    for p in PAIRS:
        f = features[p].dropna()
        mask = filter_fn(f)
        if mask.sum() < MIN_EVENTS:
            continue

        ev = f[mask].copy()
        # CAUSAL forward return: ret[t+1] .. ret[t+HOLD_BARS]
        ev["fwd"] = f["ret"].rolling(HOLD_BARS).sum().shift(-HOLD_BARS).reindex(ev.index).values
        ev = ev.dropna(subset=["fwd"])
        if len(ev) < MIN_EVENTS:
            continue

        # Signal: bet on convergence of deviation (if dev positive, expect negative fwd)
        pos = -np.sign(ev["dev"])
        # Or bet on continuation? We test both by evaluating sign separately below
        pnl = pos * ev["fwd"] - COST_BPS
        gross = (pos * ev["fwd"]).mean()
        net = pnl.mean()
        tstat, pval = stats.ttest_1samp(pnl, popmean=0)
        hit = (pnl > 0).mean()

        pair_stats.append({
            "pair": p,
            "n": len(ev),
            "gross": gross,
            "net": net,
            "tstat": tstat,
            "pval": pval,
            "hit": hit,
        })
        all_pnls.extend(pnl.tolist())
        all_gross.extend((pos * ev["fwd"]).tolist())
        n_events_total += len(ev)

    if len(all_pnls) < MIN_EVENTS:
        return None

    all_pnls = np.array(all_pnls)
    pooled_net = all_pnls.mean()
    pooled_t, pooled_p = stats.ttest_1samp(all_pnls, popmean=0)
    pooled_hit = (all_pnls > 0).mean()

    return {
        "label": label,
        "n_pairs": len(pair_stats),
        "n_events": n_events_total,
        "pooled_gross": np.mean(all_gross),
        "pooled_net": pooled_net,
        "pooled_tstat": pooled_t,
        "pooled_pval": pooled_p,
        "pooled_hit": pooled_hit,
        "pair_stats": pair_stats,
    }


def test_both_directions(features, mask_fn, label):
    """Test convergence (revert) AND continuation for a given filter."""
    results = []
    for direction in ["converge", "continue"]:
        def make_pos_fn(d):
            if d == "converge":
                return lambda ev: -np.sign(ev["dev"])
            else:
                return lambda ev: np.sign(ev["dev"])

        pos_fn = make_pos_fn(direction)
        res = evaluate_filter_directional(features, mask_fn, pos_fn, f"{label}_{direction}")
        if res:
            results.append(res)
    return results


def evaluate_filter_directional(features, mask_fn, pos_fn, label):
    """Evaluate with explicit position function."""
    all_pnls = []
    all_gross = []
    pair_stats = []
    n_events_total = 0

    for p in PAIRS:
        f = features[p].dropna()
        mask = mask_fn(f)
        if mask.sum() < MIN_EVENTS:
            continue

        ev = f[mask].copy()
        ev["fwd"] = f["ret"].rolling(HOLD_BARS).sum().shift(-HOLD_BARS).reindex(ev.index).values
        ev = ev.dropna(subset=["fwd"])
        if len(ev) < MIN_EVENTS:
            continue

        pos = pos_fn(ev)
        pnl = pos * ev["fwd"] - COST_BPS
        gross = (pos * ev["fwd"]).mean()
        net = pnl.mean()
        tstat, pval = stats.ttest_1samp(pnl, popmean=0)
        hit = (pnl > 0).mean()

        pair_stats.append({
            "pair": p,
            "n": len(ev),
            "gross": gross,
            "net": net,
            "tstat": tstat,
            "pval": pval,
            "hit": hit,
        })
        all_pnls.extend(pnl.tolist())
        all_gross.extend((pos * ev["fwd"]).tolist())
        n_events_total += len(ev)

    if len(all_pnls) < MIN_EVENTS:
        return None

    all_pnls = np.array(all_pnls)
    pooled_net = all_pnls.mean()
    pooled_t, pooled_p = stats.ttest_1samp(all_pnls, popmean=0)
    pooled_hit = (all_pnls > 0).mean()

    return {
        "label": label,
        "n_pairs": len(pair_stats),
        "n_events": n_events_total,
        "pooled_gross": np.mean(all_gross),
        "pooled_net": pooled_net,
        "pooled_tstat": pooled_t,
        "pooled_pval": pooled_p,
        "pooled_hit": pooled_hit,
        "pair_stats": pair_stats,
    }


# ---- Run ----
print("\nLoading data...")
panel, rets, ticks, idx = load_all_pairs()
print("Building features...")
features = build_xs_features(rets, ticks, idx)

# Define anomaly filters
filters = []

# 1. Extreme deviation from cross-sectional median (>1.5σ)
filters.append((lambda f: f["dev_z"].abs() > 1.5, "dev_z_1.5"))

# 2. Extreme deviation + high tick intensity (dislocation with activity)
filters.append((lambda f: (f["dev_z"].abs() > 1.5) & (f["tick_dev"].abs() > 1.5), "dev_tick_double"))

# 3. Extreme deviation during low vol (signal stands out in calm)
filters.append((lambda f: (f["dev_z"].abs() > 1.5) & (f["vol_20"] < f["vol_20"].rolling(60).quantile(0.3)), "dev_lowvol"))

# 4. Extreme deviation during high vol (momentum vs anomaly)
filters.append((lambda f: (f["dev_z"].abs() > 1.5) & (f["vol_20"] > f["vol_20"].rolling(60).quantile(0.7)), "dev_hivol"))

# 5. Pair moves opposite to its own 5m trend (local + XS double anomaly)
filters.append((lambda f: (f["dev_z"].abs() > 1.5) & (np.sign(f["ret"]) != np.sign(f["ret_5"].shift(1))) & (f["ret_5"].shift(1).abs() > 0), "dev_local_reverse"))

# 6. Tick burst + deviation (microstructure dislocation)
filters.append((lambda f: (f["dev_z"].abs() > 1.5) & (f["tick_dev"] > 2.0), "dev_tickburst"))

# 7. London/NY open deviation
filters.append((lambda f: (f["dev_z"].abs() > 1.5) & (f["hour"].isin([8,9,13,14])), "dev_session"))

# 8. Broad market move + one pair lags (all move but one)
filters.append((lambda f: (f["dev_z"].abs() > 1.0) & (f["xs_std"] > f["xs_std"].rolling(20).quantile(0.8)), "dev_broadmove"))

# 9. Vol compression breakout + deviation
filters.append((lambda f: (f["dev_z"].abs() > 1.5) & (f["vol_60"] < f["vol_60"].rolling(120).quantile(0.3)), "dev_volcompress"))

# 10. Extreme deviation (>2.0σ) — rarer, sharper
filters.append((lambda f: f["dev_z"].abs() > 2.0, "dev_z_2.0"))

# 11. Moderate deviation (1.0-1.5σ) — more events
filters.append((lambda f: (f["dev_z"].abs() > 1.0) & (f["dev_z"].abs() <= 1.5), "dev_z_1.0_1.5"))

all_results = []
for mask_fn, label in filters:
    print(f"\n--- Testing {label} ---")
    for direction in ["converge", "continue"]:
        if direction == "converge":
            pos_fn = lambda ev: -np.sign(ev["dev"])
        else:
            pos_fn = lambda ev: np.sign(ev["dev"])

        res = evaluate_filter_directional(features, mask_fn, pos_fn, f"{label}_{direction}")
        if res is None:
            print(f"  {direction}: insufficient events")
            continue
        print(f"  {direction}: n_pairs={res['n_pairs']} n_events={res['n_events']} "
              f"gross={res['pooled_gross']:.4f} net={res['pooled_net']:.4f} "
              f"t={res['pooled_tstat']:.2f} p={res['pooled_pval']:.4f} hit={res['pooled_hit']:.3f}")
        all_results.append(res)

# ---- Summary ----
print("\n\n========== SUMMARY ==========")
print(f"Tested {len(filters)} filters × 2 directions = {len(all_results)} configurations")

survivors = [r for r in all_results if r["pooled_tstat"] > 1.5 and r["pooled_net"] > 0]
print(f"Surviving t>1.5 + net>0: {len(survivors)}")

if survivors:
    print("\n--- Survivors ---")
    for r in survivors:
        print(f"  {r['label']}: n_pairs={r['n_pairs']} n={r['n_events']} net={r['pooled_net']:.4f} t={r['pooled_tstat']:.2f} hit={r['pooled_hit']:.3f}")
else:
    print("\nNo configurations survived t>1.5 + net>0.")

# Best by t-stat
if all_results:
    best = max(all_results, key=lambda r: r["pooled_tstat"])
    print(f"\nBest by t-stat: {best['label']} net={best['pooled_net']:.4f} t={best['pooled_tstat']:.2f}")

# Show per-pair breakdown for most promising
print("\n--- Per-pair breakdown for best candidate ---")
if all_results:
    best2 = max([r for r in all_results if r["pooled_net"] > -0.5], key=lambda r: r["pooled_tstat"], default=None)
    if best2:
        print(f"Filter: {best2['label']}")
        for ps in best2["pair_stats"][:10]:
            print(f"  {ps['pair']}: n={ps['n']} net={ps['net']:.4f} t={ps['tstat']:.2f} hit={ps['hit']:.3f}")
