"""Standalone funding-carry book for crypto USD-M perps.

Signal = recent funding-rate rank.  Goes long the most negative funding
(receives funding when rate < 0) and short the most positive funding
(receives funding when rate > 0).  Dollar-neutral, rebalanced every h bars.

Reuses cached broad-run data (`/tmp/crypto_broad_*.parquet`) if available.

Usage:
    uv run python -m scripts.research.crypto_funding_carry
"""
from __future__ import annotations

import argparse
import os
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

CACHE_PERP = "/tmp/crypto_broad_perp.parquet"
CACHE_FUND = "/tmp/crypto_broad_fund.parquet"
BARS_PER_YEAR = 24 * 365


def attach_funding(p: pd.DataFrame, fund: pd.DataFrame) -> pd.DataFrame:
    fund = fund.copy()
    fund["fund_bps"] = fund["last_funding_rate"] * 1e4
    fund = fund.sort_values(["symbol", "dt"])
    fund["fund_bps"] = fund.groupby("symbol")["fund_bps"].ffill()
    p = p.sort_values(["symbol", "dt"])
    merged = []
    for sym, grp in p.groupby("symbol", sort=False):
        fsub = fund[fund["symbol"] == sym][["dt", "fund_bps"]].copy()
        if fsub.empty:
            grp = grp.copy()
            grp["fund_bps"] = np.nan
            merged.append(grp)
            continue
        fsub = fsub.sort_values("dt")
        grp = grp.copy().sort_values("dt")
        idx = np.searchsorted(fsub["dt"].values, grp["dt"].values, side="right") - 1
        idx = np.clip(idx, 0, len(fsub) - 1)
        grp["fund_bps"] = fsub["fund_bps"].iloc[idx].values
        merged.append(grp)
    return pd.concat(merged, ignore_index=True).sort_values(["symbol", "dt"])


def backtest(
    p: pd.DataFrame,
    fund_window: int,
    h: int,
    k: int,
    years: tuple[int, ...],
    fee_model: dict,
) -> dict:
    # compute rolling funding signal per symbol
    g = p.groupby("symbol", group_keys=False)
    p["fund_roll"] = g["fund_bps"].transform(
        lambda x: x.rolling(fund_window, min_periods=max(1, fund_window // 2)).mean()
    )

    close = p.pivot(index="dt", columns="symbol", values="close")
    fundw = p.pivot(index="dt", columns="symbol", values="fund_roll")
    fwd = close.shift(-h) / close - 1

    idx = fundw.index[fundw.index.year.isin(years)][::h]
    symbols = fundw.columns.tolist()
    n_sym = len(symbols)
    fund_arr = fundw.to_numpy(float)
    fwd_arr = fwd.to_numpy(float)
    raw_fund_arr = p.pivot(index="dt", columns="symbol", values="fund_bps").to_numpy(float)
    ts_map = {t: i for i, t in enumerate(fundw.index)}
    rebalance_rows = np.array([ts_map[t] for t in idx if t in ts_map], dtype=int)

    spread = fee_model.get("spread_bps", 2.0) / 1e4
    rebate = fee_model.get("maker_rebate_bps", 0.2) / 1e4
    taker_fee = fee_model.get("taker_fee_bps", 7.5) / 1e4
    queue_pos = fee_model.get("queue_pos", 0.3)
    adv = fee_model.get("adv_bps", 0.5) / 1e4
    p_fill_base = fee_model.get("p_fill_base", 0.85)
    p_fill = max(0.05, p_fill_base * (1 - queue_pos))
    cost_per_turn = p_fill * (spread - rebate + adv) + (1 - p_fill) * (spread + taker_fee)

    gross, turn, fund_pnl, dates_out = [], [], [], []
    prevw = np.zeros(n_sym)

    for r in rebalance_rows:
        s = fund_arr[r, :]
        f = fwd_arr[r, :]
        valid = np.isfinite(s) & np.isfinite(f)
        n_valid = int(valid.sum())
        k_eff = min(k, n_valid // 2)
        if k_eff < 1:
            continue

        s_valid = s[valid]
        order = np.argsort(s_valid)  # most negative first
        valid_idx = np.where(valid)[0]
        bot = valid_idx[order[:k_eff]]   # most negative funding → long
        top = valid_idx[order[-k_eff:]]  # most positive funding → short

        w_ = np.zeros(n_sym)
        w_[bot] = 1.0 / k_eff
        w_[top] = -1.0 / k_eff

        g = float(np.nansum(w_ * f))

        # funding accrued over next h bars: sum raw_fund_arr[r+1:r+h+1, :] / 8
        # each 8h rate appears on 8 consecutive bars, so sum/8 = number-of-periods * rate
        fund_carry = 0.0
        if r + h + 1 <= len(raw_fund_arr):
            rates = raw_fund_arr[r + 1 : r + h + 1, :]
            # each column: sum / 8.0 = total funding periods * rate
            total_fund = np.nansum(rates, axis=0) / 8.0
            mask = np.isfinite(total_fund) & (np.abs(w_) > 1e-12)
            # funding pnl = -weight * total_fund / 1e4  (negative because positive rate + positive weight = you pay)
            fund_carry = float(np.nansum(-w_[mask] * total_fund[mask])) / 1e4
        else:
            # tail: approximate with entry rate * n_periods
            n_periods = h / 8.0
            rates = raw_fund_arr[r, :]
            mask = np.isfinite(rates) & (np.abs(w_) > 1e-12)
            fund_carry = float(np.nansum(-w_[mask] * rates[mask])) * n_periods / 1e4

        gross.append(g)
        turn.append(float(np.nansum(np.abs(w_ - prevw))))
        fund_pnl.append(fund_carry)
        dates_out.append(fundw.index[r])
        prevw = w_

    return {
        "gross": np.array(gross),
        "turn": np.array(turn),
        "fund_pnl": np.array(fund_pnl),
        "dates": pd.DatetimeIndex(dates_out),
    }


def metrics(gross, turn, fund_pnl, dates, h, fee_model) -> dict | None:
    spread = fee_model.get("spread_bps", 2.0) / 1e4
    rebate = fee_model.get("maker_rebate_bps", 0.2) / 1e4
    taker_fee = fee_model.get("taker_fee_bps", 7.5) / 1e4
    queue_pos = fee_model.get("queue_pos", 0.3)
    adv = fee_model.get("adv_bps", 0.5) / 1e4
    p_fill_base = fee_model.get("p_fill_base", 0.85)
    p_fill = max(0.05, p_fill_base * (1 - queue_pos))
    cost_per_turn = p_fill * (spread - rebate + adv) + (1 - p_fill) * (spread + taker_fee)
    cost = turn * cost_per_turn
    net = gross - cost + fund_pnl
    if len(net) < 5:
        return None

    mo = pd.Series(net, index=dates.tz_localize(None)).groupby(
        dates.tz_localize(None).to_period("M")
    ).sum()
    t = net.mean() / (net.std(ddof=1) / np.sqrt(len(net)) + 1e-12)
    sharpe = (net.mean() / (net.std() + 1e-12)) * np.sqrt(BARS_PER_YEAR / h)
    return {
        "n": len(net),
        "gross": gross.mean() * 1e4,
        "cost": cost.mean() * 1e4,
        "fund_pnl": fund_pnl.mean() * 1e4,
        "net": net.mean() * 1e4,
        "t": float(t),
        "posM": float((mo > 0).mean()),
        "sharpe": float(sharpe),
        "legs": int((turn > 0).sum()),
    }


def _monthly_net_series(net: np.ndarray, dates: pd.DatetimeIndex) -> pd.Series:
    s = pd.Series(net, index=dates.tz_localize(None))
    return s.groupby(s.index.to_period("M")).sum()


def bayesian_p_positive(monthly_net: np.ndarray, seed: int = 0,
                        num_warmup: int = 500, num_samples: int = 500) -> dict:
    import jax
    import jax.numpy as jnp
    import numpyro
    import numpyro.distributions as dist
    from numpyro.infer import MCMC, NUTS

    y = jnp.asarray(monthly_net, dtype=float)
    n = len(y)
    if n < 3:
        return {"p_positive": float("nan"), "mean": float("nan"),
                "lo": float("nan"), "hi": float("nan")}

    def _model(y_obs):
        mu = numpyro.sample("mu", dist.Normal(0.0, 0.5))
        sigma = numpyro.sample("sigma", dist.HalfNormal(1.0))
        nu = numpyro.sample("nu", dist.Gamma(2.0, 0.1))
        numpyro.sample("obs", dist.StudentT(nu, mu, sigma), obs=y_obs)

    numpyro.set_host_device_count(2)
    mcmc = MCMC(NUTS(_model), num_warmup=num_warmup, num_samples=num_samples,
                num_chains=2, chain_method="sequential", progress_bar=False)
    mcmc.run(jax.random.PRNGKey(seed), y_obs=y)
    s = mcmc.get_samples()
    mu = np.asarray(s["mu"])
    return {
        "p_positive": float((mu > 0).mean()),
        "mean": float(mu.mean()),
        "lo": float(np.percentile(mu, 3.0)),
        "hi": float(np.percentile(mu, 97.0)),
    }


def block_bootstrap_ci(net: np.ndarray, dates: pd.DatetimeIndex,
                       block_months: int = 3, n_bootstrap: int = 2000, ci: float = 0.90) -> dict:
    mo = _monthly_net_series(net, dates)
    arr = mo.to_numpy(float)
    if len(arr) < block_months + 2:
        return {"mean": float(mo.mean()), "lo": float("nan"), "hi": float("nan")}

    n_blocks = max(1, len(arr) // block_months)
    means = []
    rng = np.random.default_rng(0)
    for _ in range(n_bootstrap):
        idx = rng.integers(0, n_blocks, size=n_blocks) * block_months
        sample = []
        for i in idx:
            sample.extend(arr[i:min(i + block_months, len(arr))])
        means.append(np.mean(sample))
    means = np.array(means)
    alpha = (1 - ci) / 2
    return {
        "mean": float(mo.mean()),
        "lo": float(np.percentile(means, alpha * 100)),
        "hi": float(np.percentile(means, (1 - alpha) * 100)),
    }


def run_gauntlet(net: np.ndarray, dates: pd.DatetimeIndex, label: str) -> dict:
    print(f"\n=== GAUNTLET: {label} ===")
    mo = _monthly_net_series(net, dates)
    print(f"Monthly observations: {len(mo)}  mean={mo.mean():+.3f}  std={mo.std():.3f}")

    bayes = bayesian_p_positive(mo.to_numpy(float))
    print(f"Bayesian P(edge>0) = {bayes['p_positive']:.3f}  mean={bayes['mean']:+.3f}  94% CI=[{bayes['lo']:+.3f}, {bayes['hi']:+.3f}]")

    boot = block_bootstrap_ci(net, dates)
    print(f"Block-bootstrap 90% CI = [{boot['lo']:+.3f}, {boot['hi']:+.3f}]")
    return {"bayesian": bayes, "bootstrap": boot}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-download", action="store_true", help="Use cached parquets")
    args = ap.parse_args()

    if args.no_download and Path(CACHE_PERP).exists():
        perp = pd.read_parquet(CACHE_PERP)
    else:
        # reuse the broad-run downloader if needed; for now require cache
        raise SystemExit("Cached broad-run data not found. Run crypto_flow_xs_broad first.")

    if args.no_download and Path(CACHE_FUND).exists():
        fund = pd.read_parquet(CACHE_FUND)
    else:
        raise SystemExit("Cached broad-run funding not found. Run crypto_flow_xs_broad first.")

    perp = perp[(perp["dt"] >= "2020-01-01") & (perp["dt"] < "2025-06-01")]
    perp = perp.sort_values(["symbol", "dt"])
    perp = attach_funding(perp, fund)

    # thin to symbols with ≥5000 bars
    bar_counts = perp.groupby("symbol").size()
    keep_syms = bar_counts[bar_counts >= 5000].index.tolist()
    perp = perp[perp["symbol"].isin(keep_syms)].copy()
    print(f"Symbols: {len(keep_syms)}")
    print(f"Funding coverage: {perp['fund_bps'].notna().mean():.1%}  mean fund8h={perp['fund_bps'].mean():.4f} bps")

    tv = (2020, 2021, 2022, 2023, 2024)
    ho = (2025,)

    fee_models = [
        {"name": "taker",      "spread_bps": 2.0, "maker_rebate_bps": 0.0, "taker_fee_bps": 7.5, "queue_pos": 1.0, "adv_bps": 0.0,  "p_fill_base": 0.0},
        {"name": "maker_best", "spread_bps": 2.0, "maker_rebate_bps": 0.2, "taker_fee_bps": 7.5, "queue_pos": 0.0, "adv_bps": 0.0,  "p_fill_base": 1.0},
        {"name": "maker_good", "spread_bps": 2.0, "maker_rebate_bps": 0.2, "taker_fee_bps": 7.5, "queue_pos": 0.2, "adv_bps": 0.3,  "p_fill_base": 0.9},
        {"name": "maker_real", "spread_bps": 2.0, "maker_rebate_bps": 0.2, "taker_fee_bps": 7.5, "queue_pos": 0.4, "adv_bps": 0.6,  "p_fill_base": 0.8},
        {"name": "maker_pess", "spread_bps": 2.0, "maker_rebate_bps": 0.2, "taker_fee_bps": 7.5, "queue_pos": 0.6, "adv_bps": 1.0,  "p_fill_base": 0.7},
    ]

    print(f"\n{'config':52s} {'gross':>7s} {'cost':>6s} {'fund':>6s} {'net':>7s} {'t':>6s} {'posM':>5s} {'Shrp':>6s} {'legs':>5s}")
    rows = []
    for fund_window, h in product((1, 8, 24, 72), (8, 24, 48, 72)):
        for k in (3, 5, 8):
            for fm in fee_models:
                r = backtest(perp, fund_window, h, k, tv, fm)
                m = metrics(r["gross"], r["turn"], r["fund_pnl"], r["dates"], h, fm)
                if not m:
                    continue
                name = f"fw{fund_window:02d} h{h:02d} k{k} {fm['name']}"
                rows.append((name, fund_window, h, k, fm, r, m))
                print(f"{name:52s} {m['gross']:+7.2f} {m['cost']:6.2f} {m['fund_pnl']:6.2f} {m['net']:+7.2f} "
                      f"{m['t']:+6.2f} {m['posM']:5.0%} {m['sharpe']:+6.2f} {m['legs']:5d}")

    if not rows:
        print("ERROR: no valid backtest results.")
        return

    rows.sort(key=lambda r: r[6]["net"] if r[6] else -1e9, reverse=True)
    best = rows[0]
    name, fw, h, k, fm_best, r_best, m_best = best
    print(f"\nBest by net (train+val): {name}")

    # holdout for best config
    print(f"\nHOLDOUT 2025 for best config:")
    holdout_results = {}
    for fm in fee_models:
        r = backtest(perp, fw, h, k, ho, fm)
        m = metrics(r["gross"], r["turn"], r["fund_pnl"], r["dates"], h, fm)
        if not m:
            continue
        holdout_results[fm["name"]] = (r, m)
        print(f"  {fm['name']:12s} gross={m['gross']:+.2f} cost={m['cost']:+.2f} fund={m['fund_pnl']:+.2f} "
              f"net={m['net']:+.2f} t={m['t']:+.2f} posM={m['posM']:.0%} sharpe={m['sharpe']:+.2f} legs={m['legs']}")

    # gauntlet on holdout maker scenarios
    for fm_name in ["maker_best", "maker_good", "taker"]:
        if fm_name not in holdout_results:
            continue
        r, m = holdout_results[fm_name]
        if len(r["gross"]) < 5:
            continue
        fm_ = next(f for f in fee_models if f["name"] == fm_name)
        s = fm_.get("spread_bps", 2.0) / 1e4
        reb = fm_.get("maker_rebate_bps", 0.2) / 1e4
        tf = fm_.get("taker_fee_bps", 7.5) / 1e4
        qp = fm_.get("queue_pos", 0.3)
        adv_ = fm_.get("adv_bps", 0.5) / 1e4
        pfb = fm_.get("p_fill_base", 0.85)
        pf = max(0.05, pfb * (1 - qp))
        cpt = pf * (s - reb + adv_) + (1 - pf) * (s + tf)
        net_series = r["gross"] - r["turn"] * cpt + r["fund_pnl"]
        run_gauntlet(net_series, r["dates"], label=f"{fm_name} holdout fw{fw} h{h} k{k}")

    # write findings
    out_path = Path("docs/analysis") / f"{pd.Timestamp.now(tz='UTC').strftime('%Y-%m-%d')}_crypto_funding_carry_findings.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Crypto standalone funding-carry — findings\n",
        f"Date: {pd.Timestamp.now(tz='UTC').strftime('%Y-%m-%d %H:%M UTC')}\n",
        f"## Method\n",
        f"- Data: Binance USD-M perp 1h ({len(keep_syms)} symbols, 2020–2025).\n",
        f"- Signal: rolling mean of 8h funding rate over {fw} bars.\n",
        f"- Book: concentrated top-{k}/bottom-{k} dollar-neutral, rebalanced every {h} bars.\n",
        f"- Long most negative funding (receives when rate < 0); short most positive (receives when rate > 0).\n",
        f"\n## Best config (train+val 2020-2024)\n",
        f"- `{name}`\n",
        f"\n## Holdout 2025\n",
    ]
    for fm in fee_models:
        if fm["name"] not in holdout_results:
            continue
        _, m = holdout_results[fm["name"]]
        lines.append(f"- **{fm['name']}**: net={m['net']:+.2f} bps  t={m['t']:+.2f}  posM={m['posM']:.0%}  legs={m['legs']}\n")
    lines.append("\n## Verdict\n")
    lines.append("- See gauntlet results above.\n")
    out_path.write_text("".join(lines))
    print(f"\nWrote findings → {out_path}")


if __name__ == "__main__":
    main()
