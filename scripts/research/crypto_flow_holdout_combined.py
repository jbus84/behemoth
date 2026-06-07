"""Holdout-test combined guard + momentum overlay on 2025.
Train overlay params on 2020-2024, test on 2025.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path
from itertools import product

from scripts.research.crypto_flow_xs_broad import backtest

CACHE_PERP = "/tmp/crypto_broad_perp.parquet"


def run_net(perp: pd.DataFrame, w: int, h: int, k: int, years: tuple, fm: dict, signal: str = "flow6") -> pd.Series:
    r = backtest(perp, w, h, k, years, fm, signal=signal)
    spread = fm.get("spread_bps", 2.0) / 1e4
    rebate = fm.get("maker_rebate_bps", 2.0) / 1e4
    taker_fee = fm.get("taker_fee_bps", 5.0) / 1e4
    queue_pos = fm.get("queue_pos", 0.0)
    adv = fm.get("adv_bps", 0.0) / 1e4
    p_fill_base = fm.get("p_fill_base", 1.0)
    p_fill = max(0.05, p_fill_base * (1 - queue_pos))
    cost_per_turn = p_fill * (spread - rebate + adv) + (1 - p_fill) * (spread + taker_fee)
    net = r["gross"] - r["turn"] * cost_per_turn + r["fund_pnl"]
    idx = pd.DatetimeIndex(r["dates"]).tz_localize(None)
    return pd.Series(net, index=idx)


def apply_guard(s: pd.Series, soft: float, hard: float, soft_scale: float) -> pd.Series:
    cum = (1 + s).cumprod()
    scale = pd.Series(1.0, index=s.index)
    peak = cum.iloc[0]
    for i in range(len(cum)):
        peak = max(peak, cum.iloc[i])
        dd = (cum.iloc[i] - peak) / peak
        if dd <= hard:
            scale.iloc[i] = 0.0
        elif dd <= soft:
            scale.iloc[i] = soft_scale
    return s * scale


def apply_mom_stop(s: pd.Series, window: int, threshold: float, scale: float) -> pd.Series:
    cum_ret = (1 + s).cumprod()
    rolling_ret = cum_ret.pct_change(window).reindex(s.index).fillna(0)
    sc = pd.Series(1.0, index=s.index)
    sc[rolling_ret < threshold] = scale
    return s * sc


def metrics(s: pd.Series) -> dict:
    cum = (1 + s).cumprod()
    dd = (cum - cum.cummax()) / cum.cummax()
    return {
        "sharpe": s.mean() / s.std() * np.sqrt(365) if s.std() > 0 else 0.0,
        "max_dd": dd.min(),
        "final": cum.iloc[-1],
        "vol_ann": s.std() * np.sqrt(365),
        "pos_days": int((s > 0).sum()),
        "neg_days": int((s < 0).sum()),
    }


def main() -> None:
    perp = pd.read_parquet(CACHE_PERP)
    perp = perp[(perp["dt"] >= "2020-01-01") & (perp["dt"] < "2025-06-01")]
    perp = perp.sort_values(["symbol", "dt"])
    bar_counts = perp.groupby("symbol").size()
    keep_syms = bar_counts[bar_counts >= 5000].index.tolist()
    perp = perp[perp["symbol"].isin(keep_syms)].copy()

    fm_retail = {
        "name": "retail_maker", "spread_bps": 2.0, "maker_rebate_bps": 2.0,
        "taker_fee_bps": 5.0, "queue_pos": 0.0, "adv_bps": 0.0, "p_fill_base": 1.0,
    }
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
        f"- Train guard + momentum-stop grid on 2020-2024\n",
        f"- Best train: guard={g_best}  mom_stop={m_best}\n\n",
        "| variant | Sharpe | maxDD | final | pos/neg days |\n",
        "|---------|--------|-------|-------|-------------|\n",
        f"| baseline (2025) | {baseline_test['sharpe']:+.2f} | {baseline_test['max_dd']:.1%} | {baseline_test['final']:.2f}x | {baseline_test['pos_days']}/{baseline_test['neg_days']} |\n",
        f"| trained combined (2025) | {m_test['sharpe']:+.2f} | {m_test['max_dd']:.1%} | {m_test['final']:.2f}x | {m_test['pos_days']}/{m_test['neg_days']} |\n",
        f"| naive combined (2025) | {m_naive['sharpe']:+.2f} | {m_naive['max_dd']:.1%} | {m_naive['final']:.2f}x | {m_naive['pos_days']}/{m_naive['neg_days']} |\n",
    ]
    out.write_text("".join(lines))
    print(f"\nWrote → {out}")


if __name__ == "__main__":
    main()
