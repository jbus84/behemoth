from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.era_scalp.bayes_edge import edge_verdict
from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.fade_seeds import FADE_SEED_PROGRAMS
from scripts.era_scalp.load_splits import _pip_size, build_trade_splits
from scripts.era_scalp.sandbox import run_program
from scripts.era_scalp.trade_harness import evaluate_trades

DIRECTIONS = {"fade": 1.0, "continue": -1.0}
GRID_Q = [0.90, 0.95, 0.99]
GRID_H = [100, 200, 400]
MIN_TRADES = 200
MIN_MONTHS_SEL = 6


def dev_signal(split_data) -> np.ndarray:
    """The fixed fair-dislocation dev (fair_fade seed) on a split's feature context."""
    ctx = FeatureContext(X=split_data.X, names=split_data.names, hour=split_data.hour)
    sig, err, _ = run_program(FADE_SEED_PROGRAMS["fair_fade"], ctx, required_fn="signal")
    if err is not None:
        raise RuntimeError(f"dev_signal failed: {err}")
    return sig


def cell_net(signal: np.ndarray, split_data, symbol: str, direction: str,
             q: float, h: int) -> pd.DataFrame:
    """Trade frame for one (direction, q, h) cell. direction in {'fade','continue'}."""
    sgn = DIRECTIONS[direction]
    return evaluate_trades(sgn * np.asarray(signal, float), split_data.mid, split_data.cost,
                           split_data.test_month, _pip_size(symbol), q, h)


def diagnostics(net_frame: pd.DataFrame) -> dict:
    """De-inflated panel: trade count, month count, month-hit-rate, trade-weighted raw mean."""
    n = int(len(net_frame))
    if n == 0:
        return {"n_trades": 0, "n_months": 0, "month_hit": 0.0, "raw_mean": float("nan")}
    g = net_frame.groupby("test_month")["net"].mean()
    return {
        "n_trades": n,
        "n_months": int(g.shape[0]),
        "month_hit": float((g > 0).mean()),
        "raw_mean": float(net_frame["net"].mean()),
    }


def credibility(net_frame: pd.DataFrame, seed: int = 0, fast: bool = False) -> dict | None:
    """Single-symbol monthly posterior summary {p_positive, mean, lo, hi}, or None if too thin.

    fast=True uses short chains for the validation selection sweep (ranking only)."""
    kw = {"num_warmup": 300, "num_samples": 300} if fast else {}
    try:
        post = edge_verdict({"_": net_frame}, seed=seed, **kw)
    except ValueError:
        return None
    return post.pooled


def select_on_validation(signal: np.ndarray, split_data, symbol: str) -> dict | None:
    """Pick the (direction, q, h) maximising the lower credible bound among cells passing the
    sample guard (>= MIN_TRADES trades, >= MIN_MONTHS_SEL months) on the validation split."""
    best = None
    for direction in DIRECTIONS:
        for q in GRID_Q:
            for h in GRID_H:
                frame = cell_net(signal, split_data, symbol, direction, q, h)
                diag = diagnostics(frame)
                if diag["n_trades"] < MIN_TRADES or diag["n_months"] < MIN_MONTHS_SEL:
                    continue
                cred = credibility(frame, fast=True)
                if cred is None:
                    continue
                val = {**cred, **diag}
                cand = {"direction": direction, "q": q, "h": h, "val": val}
                key = (val["lo"], val["raw_mean"])
                if best is None or key > (best["val"]["lo"], best["val"]["raw_mean"]):
                    best = cand
    return best


def confirm_on_holdout(signal: np.ndarray, split_data, symbol: str, choice: dict) -> dict:
    """Evaluate the validation-chosen (direction,q,h) on the holdout; full diagnostics + posterior."""
    frame = cell_net(signal, split_data, symbol, choice["direction"], choice["q"], choice["h"])
    cred = credibility(frame, fast=False) or {"p_positive": float("nan"), "mean": float("nan"),
                                              "lo": float("nan"), "hi": float("nan")}
    return {"direction": choice["direction"], "q": choice["q"], "h": choice["h"],
            "val": choice.get("val"), "holdout": {**cred, **diagnostics(frame)}}


def sweep(symbols: list[str], tv_dir: str = "data/analysis/tick_velocity") -> list[dict]:
    """Per symbol: build splits once, dev signal once per split, select on validation, confirm on holdout."""
    from pathlib import Path
    results = []
    for sym in symbols:
        sp = build_trade_splits(sym, Path(tv_dir) / f"{sym}_100tick_velocity.parquet", embargo=max(GRID_H))
        sig_v = dev_signal(sp["validation"])
        choice = select_on_validation(sig_v, sp["validation"], sym)
        if choice is None:
            results.append({"symbol": sym, "admissible": False})
            continue
        sig_h = dev_signal(sp["holdout"])
        conf = confirm_on_holdout(sig_h, sp["holdout"], sym, choice)
        results.append({"symbol": sym, "admissible": True, **conf})
    return results


def _fmt(results: list[dict]) -> str:
    lines = ["# ERA per-symbol edge sweep — validation-selected, holdout-confirmed\n",
             "| symbol | dir | q | h | holdout P(edge>0) | post mean | raw mean | n_trades | n_months | month_hit |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        if not r.get("admissible"):
            lines.append(f"| {r['symbol']} | — | — | — | no admissible validation setting | | | | | |")
            continue
        h = r["holdout"]
        lines.append(
            f"| {r['symbol']} | {r['direction']} | {r['q']} | {r['h']} | {h['p_positive']:.3f} | "
            f"{h['mean']:+.3f} | {h['raw_mean']:+.3f} | {h['n_trades']} | {h['n_months']} | "
            f"{h['month_hit']:.2f} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    import argparse
    from pathlib import Path
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="EURUSD,GBPUSD,AUDUSD,USDCHF,USDJPY")
    ap.add_argument("--tv-dir", default="data/analysis/tick_velocity")
    ap.add_argument("--out", default="/tmp/era_fade/per_symbol_sweep.md")
    args = ap.parse_args()
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    results = sweep(symbols, tv_dir=args.tv_dir)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(_fmt(results))
    print(f"wrote {args.out}")
    for r in results:
        print(r["symbol"], "—", "no setting" if not r.get("admissible")
              else f"{r['direction']} q{r['q']} h{r['h']} P={r['holdout']['p_positive']:.3f} "
                   f"raw={r['holdout']['raw_mean']:+.2f} hit={r['holdout']['month_hit']:.2f}")


if __name__ == "__main__":
    main()
