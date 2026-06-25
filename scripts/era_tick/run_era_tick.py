"""ERA-PUCT search over the tick-momentum signal — targeting rare, high-amplitude rides.

The thesis we are testing (user): the money is in the *handful of huge trends ridden far*, not
in trading often. So selectivity is a feature, not a bug. We therefore:
  - search at HIGH conviction quantiles (grid_q ~0.9-0.99) so only the strongest states fire;
  - judge on DAY-ROBUSTNESS (mean-across-days - z*SE): a strategy must be profitable across
    MANY distinct days, which is exactly what separates a real low-frequency edge from a
    2-lucky-days mirage. The floor is on min DAYS (not trades/day).

Modes:
  --symbols A,B,...  seed-only cross-symbol board (no LLM): day-robust LB + gross/cost per symbol.
  --symbol X --budget N   full PUCT search on X (qwen writer); reports top programs on a large
                          held-out day block.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.era.llm import propose_program, recombine_program
from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.era_engine import RunSpec, run_era_search, score_program
from scripts.era_scalp.sandbox import causality_probe, run_program
from scripts.era_tick.era_exec import ExitParams, evaluate_full, make_score_frame
from scripts.era_tick.era_panel import build_split
from scripts.era_tick.era_seeds import BRANCH_TAGS, IDEAS, SEED_PROGRAMS, TICK_RULES

GRID_Q = [0.90, 0.97, 0.99]  # high quantiles = only the strongest conviction fires
GRID_H = [3000]  # long max-hold: let big trends run
RAW_COST_REF = 0.22
_CACHE = ".era_tick_cache"


def _weekdays(start: str, n: int, skip: int = 0) -> list[str]:
    days = pd.bdate_range(start=start, periods=n + skip + 30)
    return [d.strftime("%Y-%m-%d") for d in days][skip : skip + n]


def _make_spec(symbol: str, score_frame, *, with_writer: bool) -> RunSpec:
    def ctx_factory(split):
        return FeatureContext(X=split.X, names=split.names, hour=split.hour)

    propose = recombine = None
    if with_writer:
        cache = Path(_CACHE) / symbol
        propose = lambda ps, sc, lg, idea: propose_program(  # noqa: E731
            ps, sc, lg, idea, cache, rules=TICK_RULES
        )
        recombine = lambda a, sa, b, sb: recombine_program(  # noqa: E731
            a, sa, b, sb, cache, rules=TICK_RULES
        )

    return RunSpec(
        name=symbol,
        required_fn="signal",
        run_program=run_program,
        causality_probe=causality_probe,
        context_factory=ctx_factory,
        score_frame=score_frame,
        grid_q=list(GRID_Q),
        grid_h=list(GRID_H),
        aggregate="robust",
        seed_programs=dict(SEED_PROGRAMS),
        branch_tags=dict(BRANCH_TAGS),
        ideas=list(IDEAS),
        propose=propose,
        recombine=recombine,
    )


def _decompose(src: str, spec: RunSpec, split, ep: ExitParams, markup: float) -> dict:
    """Honest gross/cost/net decomposition + day stats for one program on one split."""
    ctx = spec.context_factory(split)
    out, err, _ = run_program(src, ctx, timeout=spec.timeout, required_fn="signal")
    if err is not None:
        return {
            "n": 0,
            "days": 0,
            "gross/trade": np.nan,
            "cost/trade": np.nan,
            "net/trade": np.nan,
            "day_lb": np.nan,
        }
    best = None
    for q in GRID_Q:
        df = evaluate_full(out, split, q, GRID_H[0], exit_params=ep, markup_pips=markup)
        if df.empty:
            continue
        per_day = df.groupby("test_month")["net"].mean()
        lb = (
            per_day.mean() - 1.645 * per_day.std(ddof=1) / np.sqrt(len(per_day))
            if len(per_day) > 1
            else np.nan
        )
        row = {
            "q": q,
            "n": len(df),
            "days": df["test_month"].nunique(),
            "gross/trade": round(df["gross"].mean(), 4),
            "cost/trade": round(df["cost"].mean(), 4),
            "net/trade": round(df["net"].mean(), 4),
            "day_lb": round(lb, 4) if np.isfinite(lb) else np.nan,
        }
        if best is None or (
            np.isfinite(row["day_lb"]) and row["day_lb"] > best.get("day_lb", -1e9)
        ):
            best = row
    return best or {
        "n": 0,
        "days": 0,
        "gross/trade": np.nan,
        "cost/trade": np.nan,
        "net/trade": np.nan,
        "day_lb": np.nan,
    }


def _cross_symbol(symbols: list[str], val_days: list[str], ep: ExitParams, markup: float) -> None:
    print(f"=== seed-only cross-symbol ({len(val_days)} days) ===")
    rows = []
    for sym in symbols:
        try:
            split = build_split(sym, val_days)
        except ValueError:
            continue
        min_days = max(8, int(0.4 * len(set(val_days))))
        sf = make_score_frame(exit_params=ep, markup_pips=markup, min_trades=15, min_days=min_days)
        spec = _make_spec(sym, sf, with_writer=False)
        best_seed, best_val = None, -1e9
        for name, src in SEED_PROGRAMS.items():
            v, _m, _se, _lg = score_program(src, spec, split)
            if v > best_val:
                best_val, best_seed = v, name
        dec = _decompose(SEED_PROGRAMS[best_seed], spec, split, ep, markup)
        rows.append({"symbol": sym, "best_seed": best_seed, "val_score": round(best_val, 4), **dec})
    df = pd.DataFrame(rows).sort_values("val_score", ascending=False)
    print(df.to_string(index=False))
    print(f"\nday_lb>0 = profitable across days at the best q (raw cost ref ~{RAW_COST_REF}p).")


def _search(symbol: str, val_days, hold_days, budget, ep, markup) -> None:
    val = build_split(symbol, val_days)
    hold = build_split(symbol, hold_days)
    min_days = max(8, int(0.4 * len(set(val_days))))
    sf = make_score_frame(exit_params=ep, markup_pips=markup, min_trades=15, min_days=min_days)
    spec = _make_spec(symbol, sf, with_writer=budget > 0)
    print(
        f"=== ERA search {symbol}: budget={budget}, val={len(set(val_days))}d hold={len(set(hold_days))}d ==="
    )
    nodes = run_era_search(spec, {"validation": val, "holdout": hold}, budget=budget)
    ranked = sorted([n for n in nodes if n.score > -1e6 + 1], key=lambda n: n.score, reverse=True)
    print(f"{len(nodes)} programs, {len(ranked)} admissible. Top by val day-robust LB:")
    rows = []
    for nd in ranked[:8]:
        h = _decompose(str(nd.payload), spec, hold, ep, markup)
        rows.append(
            {
                "branch": nd.branch,
                "val_lb": round(nd.score, 4),
                "hold_n": h["n"],
                "hold_days": h["days"],
                "hold_gross/t": h["gross/trade"],
                "hold_net/t": h["net/trade"],
                "hold_day_lb": h["day_lb"],
            }
        )
    print(pd.DataFrame(rows).to_string(index=False))


def main() -> None:
    p = argparse.ArgumentParser(description="ERA-PUCT tick-momentum search")
    p.add_argument("--symbol", default="EURUSD")
    p.add_argument("--symbols", default="", help="comma list -> seed-only cross-symbol board")
    p.add_argument("--budget", type=int, default=0)
    p.add_argument("--start", default="2024-03-01")
    p.add_argument("--val-days", type=int, default=20)
    p.add_argument("--hold-days", type=int, default=40)
    p.add_argument("--markup", type=float, default=0.0)
    args = p.parse_args()

    ep = ExitParams()
    val_days = _weekdays(args.start, args.val_days)
    if args.symbols:
        _cross_symbol(
            [s.strip().upper() for s in args.symbols.split(",")], val_days, ep, args.markup
        )
        return
    hold_days = _weekdays(args.start, args.hold_days, skip=args.val_days)
    _search(args.symbol, val_days, hold_days, args.budget, ep, args.markup)


if __name__ == "__main__":
    main()
