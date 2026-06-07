"""Holdout-test combined guard + momentum overlay on 2025.
Train overlay params on 2020-2024, test on 2025.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from scripts.research.crypto_flow_overlays import (
    RETAIL_MAKER,
    cost_per_turn,
)
from scripts.research.crypto_flow_overlays import (
    drawdown_guard as apply_guard,
)
from scripts.research.crypto_flow_overlays import (
    metrics as _metrics,
)
from scripts.research.crypto_flow_overlays import (
    momentum_stop as apply_mom_stop,
)
from scripts.research.crypto_flow_xs_broad import backtest

CACHE_PERP = "/tmp/crypto_broad_perp.parquet"
H = 48


def run_net(perp: pd.DataFrame, w: int, h: int, k: int, years: tuple, fm: dict, signal: str = "flow6") -> pd.Series:
    r = backtest(perp, w, h, k, years, fm, signal=signal)
    net = r["gross"] - r["turn"] * cost_per_turn(fm) + r["fund_pnl"]
    idx = pd.DatetimeIndex(r["dates"]).tz_localize(None)
    return pd.Series(net, index=idx)


def metrics(s: pd.Series) -> dict:
    return _metrics(s, H)


def main() -> None:
    perp = pd.read_parquet(CACHE_PERP)
    perp = perp[(perp["dt"] >= "2020-01-01") & (perp["dt"] < "2025-06-01")]
    perp = perp.sort_values(["symbol", "dt"])
    bar_counts = perp.groupby("symbol").size()
    keep_syms = bar_counts[bar_counts >= 5000].index.tolist()
    perp = perp[perp["symbol"].isin(keep_syms)].copy()

    fm_retail = dict(RETAIL_MAKER)
    train_years = tuple(range(2020, 2025))
    test_years = (2025,)

    s_train = run_net(perp, 24, 48, 5, train_years, fm_retail)
    s_test = run_net(perp, 24, 48, 5, test_years, fm_retail)

    # grid search guard + mom_stop on train
    best = None
    best_score = -np.inf
    guard_grid = [(-0.10, -0.20, 0.25), (-0.15, -0.25, 0.5), (-0.08, -0.15, 0.25)]
    mom_grid = [(3, -0.02, 0.5), (5, -0.03, 0.5), (3, -0.03, 0.25), (5, -0.02, 0.5)]

    for g in guard_grid:
        for m in mom_grid:
            g_s = apply_guard(s_train, *g)
            comb = apply_mom_stop(g_s, *m)
            mm = metrics(comb)
            score = mm["sharpe"] - 3.0 * abs(mm["max_dd"])
            if score > best_score:
                best_score = score
                best = (g, m, mm)

    g_best, m_best, m_train = best
    print(f"Train best: guard={g_best}  mom_stop={m_best}")
    print(f"  Train Sharpe={m_train['sharpe']:.2f}  maxDD={m_train['max_dd']:.1%}  final={m_train['final']:.2f}x")

    # test
    g_test = apply_guard(s_test, *g_best)
    comb_test = apply_mom_stop(g_test, *m_best)
    m_test = metrics(comb_test)
    baseline_test = metrics(s_test)

    print(f"\nHoldout baseline : Sharpe={baseline_test['sharpe']:.2f}  maxDD={baseline_test['max_dd']:.1%}  final={baseline_test['final']:.2f}x")
    print(f"Holdout combined : Sharpe={m_test['sharpe']:.2f}  maxDD={m_test['max_dd']:.1%}  final={m_test['final']:.2f}x")

    # also test the naive full-history params on holdout for comparison
    g_naive = apply_guard(s_test, -0.10, -0.20, 0.25)
    comb_naive = apply_mom_stop(g_naive, 3, -0.02, 0.5)
    m_naive = metrics(comb_naive)
    print(f"Holdout naive    : Sharpe={m_naive['sharpe']:.2f}  maxDD={m_naive['max_dd']:.1%}  final={m_naive['final']:.2f}x")

    out = Path("docs/analysis") / f"{pd.Timestamp.now(tz='UTC').strftime('%Y-%m-%d')}_crypto_flow_holdout_combined.md"
    lines = [
        "# Combined overlay holdout test (2025)\n\n",
        "- Train guard + momentum-stop grid on 2020-2024\n",
        f"- Best train: guard={g_best}  mom_stop={m_best}\n\n",
        "| variant | Sharpe | maxDD | final | pos/neg days |\n",
        "|---------|--------|-------|-------|-------------|\n",
        f"| baseline (2025) | {baseline_test['sharpe']:+.2f} | {baseline_test['max_dd']:.1%} | {baseline_test['final']:.2f}x | {baseline_test['pos']}/{baseline_test['neg']} |\n",
        f"| trained combined (2025) | {m_test['sharpe']:+.2f} | {m_test['max_dd']:.1%} | {m_test['final']:.2f}x | {m_test['pos']}/{m_test['neg']} |\n",
        f"| naive combined (2025) | {m_naive['sharpe']:+.2f} | {m_naive['max_dd']:.1%} | {m_naive['final']:.2f}x | {m_naive['pos']}/{m_naive['neg']} |\n",
    ]
    out.write_text("".join(lines))
    print(f"\nWrote → {out}")


if __name__ == "__main__":
    main()
