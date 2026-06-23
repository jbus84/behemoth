"""Target predictability report card — funnel orchestration.

Two-stage funnel per target: Stage C (well-posedness) gates Stage A (bracketed
intrinsic ceiling). A target failing C hard is flagged ill-posed and Stage A is
skipped to save compute (override with run_ceiling_on_illposed=True).

CLI: `uv run python scripts/fx_coint/target_report.py`
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from target_ceiling import ceiling_bracket, lag_embedding  # noqa: E402
from target_wellposedness import (  # noqa: E402
    class_balance,
    effective_n,
    label_noise,
    regime_stability,
    temporal_concentration,
)
from triple_barrier import vertical_idx  # noqa: E402

DATA = "/Users/danielfisher/repositories/behemoth/data/tick_bars"
POOL = ["EURUSD", "GBPUSD"]
DATASETS = {"15m_time": "15m_flow", "1000tick": "1000tick"}
HORIZONS_NS = {"1h": 3600_000_000_000, "6h": 6 * 3600_000_000_000}


@dataclass
class ReportCard:
    name: str
    kind: str
    wellposed: dict
    wellposed_verdict: str
    ceiling: dict | None
    ceiling_verdict: str


def wellposedness_verdict(wp: dict, min_overlap: float = 0.1,
                          max_concentration: float = 0.8) -> str:
    if wp.get("overlap_ratio", 1.0) < min_overlap:
        return "ill-posed"
    if wp.get("top1pct_share", 0.0) > max_concentration:
        return "ill-posed"
    ent = wp.get("entropy", float("nan"))
    if np.isfinite(ent) and ent < 0.1:
        return "ill-posed"
    return "well-posed"


def score_target(name, kind, labels, signal, day_index, split_idx, X, y_ceiling,
                 t1, *, barrier_args=None, run_ceiling_on_illposed=False,
                 rng=None) -> ReportCard:
    wp = {}
    wp.update(effective_n(labels))
    wp.update(temporal_concentration(signal, day_index))
    wp.update(class_balance(labels, kind))
    wp.update(regime_stability(labels, split_idx, kind))
    if barrier_args is not None:
        wp.update(label_noise(barrier_args["logp"], barrier_args["ev"],
                              barrier_args["vert"], barrier_args["width"],
                              barrier_args["perturb"]))
    verdict = wellposedness_verdict(wp)
    if verdict == "ill-posed" and not run_ceiling_on_illposed:
        return ReportCard(name, kind, wp, verdict, None, "skipped")
    cb = ceiling_bracket(X, y_ceiling, t1, kind, rng=rng)
    cv = "signal" if (np.isfinite(cb["lower_p"]) and cb["lower_p"] < 0.05) \
        else "null-indistinguishable"
    return ReportCard(name, kind, wp, verdict, cb, cv)


def build_continuous_target(ts, logp, horizon_ns):
    n = len(ts)
    idx = np.arange(n)
    t1 = vertical_idx(ts, idx, horizon_ns)
    labels = (logp[t1] - logp) * 1e4                       # forward return bps
    signal = labels
    day_index = (ts // (86_400 * 1_000_000_000)).astype("int64")
    r = np.diff(logp, prepend=logp[0])
    X = lag_embedding(r, lags=(1, 5, 20, 60))
    return labels, signal, day_index, t1, X


def _load(sym, suffix):
    import pandas as pd
    df = pd.read_parquet(f"{DATA}/{sym}_{suffix}.parquet")
    if "mid" in df.columns:
        mid = df["mid"].to_numpy()
        t = pd.to_datetime(df["bucket"])
    else:
        mid = ((df["close_bid"] + df["close_ask"]) / 2).to_numpy()
        t = pd.to_datetime(df["timestamp"])
    t = pd.DatetimeIndex(t).tz_localize(None).astype("datetime64[ns]")
    o = np.argsort(t.view("int64"))
    return t.view("int64").astype("int64")[o], np.log(mid[o])


def main():
    rows = []
    for ds_label, suffix in DATASETS.items():
        for h_label, h_ns in HORIZONS_NS.items():
            sym = POOL[0]
            try:
                ts, logp = _load(sym, suffix)
            except FileNotFoundError:
                print(f"skip {sym} {suffix}: not found")
                continue
            labels, signal, day_index, t1, X = build_continuous_target(ts, logp, h_ns)
            card = score_target(
                f"{sym}/{ds_label}/{h_label}", "continuous",
                labels=labels, signal=signal, day_index=day_index,
                split_idx=len(ts) // 2, X=X, y_ceiling=labels, t1=t1,
                rng=np.random.default_rng(0))
            rows.append(card)
    rows.sort(key=lambda c: (c.ceiling or {}).get("lower_z", -1e9), reverse=True)
    print(f"\n{'target':28s} {'wp':>10s} {'ovlp':>6s} {'conc':>6s} "
          f"{'lowerIC':>8s} {'p':>6s} {'z':>6s} {'MI':>6s}  ceiling")
    for c in rows:
        cb = c.ceiling or {}
        print(f"{c.name:28s} {c.wellposed_verdict:>10s} "
              f"{c.wellposed.get('overlap_ratio', float('nan')):6.2f} "
              f"{c.wellposed.get('top1pct_share', float('nan')):6.2f} "
              f"{cb.get('lower', float('nan')):8.3f} {cb.get('lower_p', float('nan')):6.2f} "
              f"{cb.get('lower_z', float('nan')):6.2f} {cb.get('mi', float('nan')):6.3f}  "
              f"{c.ceiling_verdict}")


if __name__ == "__main__":
    main()
