"""Stage-3: broadened crypto cross-sectional flow with full gauntlet.

Expands the futures-native probe to ~59 liquid USDT perps and 2020-2025 history,
then runs the full verdict gauntlet (Bayesian P(edge>0), temporal-robustness,
block-bootstrap CI, DSR) to test whether more breadth + history pushes DSR
toward 0.95.

Usage:
    uv run python -m scripts.research.crypto_flow_xs_broad
"""
from __future__ import annotations

import concurrent.futures as cf
import io
import urllib.request
import zipfile
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

# ── universe ──────────────────────────────────────────────────────────
SYMS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "SOLUSDT",
    "DOGEUSDT", "DOTUSDT", "LTCUSDT", "LINKUSDT", "AVAXUSDT", "ATOMUSDT",
    "ETCUSDT", "BCHUSDT", "TRXUSDT", "XLMUSDT", "NEARUSDT", "FILUSDT",
    "AAVEUSDT", "UNIUSDT", "DASHUSDT", "ZECUSDT", "ALGOUSDT", "XMRUSDT",
    "ICPUSDT", "HBARUSDT", "1000SHIBUSDT", "CHZUSDT", "CRVUSDT", "GRTUSDT",
    "1INCHUSDT", "SNXUSDT", "COMPUSDT", "MKRUSDT", "YFIUSDT", "SUSHIUSDT",
    "COTIUSDT", "RUNEUSDT", "KAVAUSDT", "ROSEUSDT", "DYDXUSDT", "CELRUSDT",
    "LRCUSDT", "SKLUSDT", "BATUSDT", "ENJUSDT", "MANAUSDT", "SANDUSDT",
    "AXSUSDT", "GALAUSDT", "ICXUSDT", "ZILUSDT", "XTZUSDT", "KSMUSDT",
    "EGLDUSDT", "THETAUSDT", "FTMUSDT", "CELOUSDT", "NEOUSDT",
]
MONTHS = (
    [f"{y}-{m:02d}" for y in (2020, 2021, 2022, 2023, 2024) for m in range(1, 13)]
    + [f"2025-{m:02d}" for m in range(1, 6)]
)

PERP_BASE = "https://data.binance.vision/data/futures/um/monthly/klines/{s}/1h/{s}-1h-{mo}.zip"
FUND_BASE = "https://data.binance.vision/data/futures/um/monthly/fundingRate/{s}/{s}-fundingRate-{mo}.zip"

CACHE_PERP = "/tmp/crypto_broad_perp.parquet"
CACHE_FUND = "/tmp/crypto_broad_fund.parquet"
BARS_PER_YEAR = 24 * 365

# ── data ingest ───────────────────────────────────────────────────────

def _fetch_perp(args: tuple[str, str]) -> pd.DataFrame | None:
    s, mo = args
    try:
        with urllib.request.urlopen(PERP_BASE.format(s=s, mo=mo), timeout=30) as r:
            zf = zipfile.ZipFile(io.BytesIO(r.read()))
        df = pd.read_csv(
            io.BytesIO(zf.read(zf.namelist()[0])),
            header=None,
            usecols=[0, 4, 5, 9],
            names=["ts", "close", "vol", "tbv"],
        )
        df = df[pd.to_numeric(df["ts"], errors="coerce").notna()].copy()
        for c in ["ts", "close", "vol", "tbv"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df["symbol"] = s
        return df
    except Exception:
        return None


def ingest_perp(syms: list[str] | None = None, months: list[str] | None = None) -> pd.DataFrame:
    syms = syms or SYMS
    months = months or MONTHS
    tasks = [(s, mo) for s in syms for mo in months]
    ok, fail = 0, 0
    with cf.ThreadPoolExecutor(max_workers=16) as ex:
        out = []
        for r in ex.map(_fetch_perp, tasks):
            if r is not None and len(r):
                out.append(r)
                ok += 1
            else:
                fail += 1
    print(f"  perp download: {ok} files ok, {fail} missing/failed")
    p = pd.concat(out, ignore_index=True)
    ts = p["ts"].astype("int64")
    p["dt"] = pd.to_datetime(
        np.where(ts < 100_000_000_000_000, ts * 1_000_000, ts * 1000), utc=True
    )
    p["ofi"] = (2 * p["tbv"] - p["vol"]) / p["vol"].replace(0, np.nan)
    p = p.sort_values(["symbol", "dt"]).reset_index(drop=True)
    p.to_parquet(CACHE_PERP)
    return p


def _fetch_funding(args: tuple[str, str]) -> pd.DataFrame | None:
    s, mo = args
    try:
        with urllib.request.urlopen(FUND_BASE.format(s=s, mo=mo), timeout=30) as r:
            zf = zipfile.ZipFile(io.BytesIO(r.read()))
        df = pd.read_csv(
            io.BytesIO(zf.read(zf.namelist()[0])),
            usecols=["calc_time", "funding_interval_hours", "last_funding_rate"],
        )
        df["symbol"] = s
        return df
    except Exception:
        return None


def ingest_funding(syms: list[str] | None = None, months: list[str] | None = None) -> pd.DataFrame:
    syms = syms or SYMS
    months = months or MONTHS
    tasks = [(s, mo) for s in syms for mo in months]
    ok, fail = 0, 0
    with cf.ThreadPoolExecutor(max_workers=16) as ex:
        out = []
        for r in ex.map(_fetch_funding, tasks):
            if r is not None and len(r):
                out.append(r)
                ok += 1
            else:
                fail += 1
    print(f"  funding download: {ok} files ok, {fail} missing/failed")
    p = pd.concat(out, ignore_index=True)
    p["dt"] = pd.to_datetime(p["calc_time"].astype("int64") * 1_000_000, utc=True)
    p = p.sort_values(["symbol", "dt"]).reset_index(drop=True)
    p.to_parquet(CACHE_FUND)
    return p


# ── feature engineering ───────────────────────────────────────────────

def build_features(p: pd.DataFrame) -> pd.DataFrame:
    g = p.groupby("symbol", group_keys=False)
    p["flow6"] = g["ofi"].transform(lambda x: x.rolling(6, min_periods=3).mean())
    p["flow24"] = g["ofi"].transform(lambda x: x.rolling(24, min_periods=8).mean())
    return p


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


# ── backtest engine (vectorised) ──────────────────────────────────────

def backtest(
    p: pd.DataFrame,
    w: int,
    h: int,
    k: int,
    years: tuple[int, ...],
    fee_model: dict,
    signal: str = "flow6",
    use_funding_signal: bool = False,
) -> dict:
    flow = p.assign(flow=p.groupby("symbol", group_keys=False)["ofi"]
                    .transform(lambda x: x.rolling(w, min_periods=max(3, w // 2)).mean()))
    close = flow.pivot(index="dt", columns="symbol", values="close")
    floww = flow.pivot(index="dt", columns="symbol", values="flow")
    fwd = close.shift(-h) / close - 1

    if use_funding_signal and "fund_bps" in flow.columns:
        fund_w = flow.pivot(index="dt", columns="symbol", values="fund_bps")
        fund_z = fund_w.sub(fund_w.mean(axis=1), axis=0).div(fund_w.std(axis=1) + 1e-12, axis=0)
        floww = floww.add(fund_z.mul(-1.0), fill_value=0.0)

    idx = floww.index[floww.index.year.isin(years)][::h]
    symbols = floww.columns.tolist()
    n_sym = len(symbols)
    flow_arr = floww.to_numpy(float)
    fwd_arr = fwd.to_numpy(float)
    fund_arr = None
    if "fund_bps" in flow.columns:
        fund_arr = flow.pivot(index="dt", columns="symbol", values="fund_bps").to_numpy(float)
    ts_map = {t: i for i, t in enumerate(floww.index)}
    rebalance_rows = np.array([ts_map[t] for t in idx if t in ts_map], dtype=int)

    spread = fee_model.get("spread_bps", 2.0) / 1e4
    rebate = fee_model.get("maker_rebate_bps", 0.2) / 1e4
    taker_fee = fee_model.get("taker_fee_bps", 7.5) / 1e4
    queue_pos = fee_model.get("queue_pos", 0.3)
    adv = fee_model.get("adv_bps", 0.5) / 1e4
    p_fill_base = fee_model.get("p_fill_base", 0.85)
    p_fill = max(0.05, p_fill_base * (1 - queue_pos))
    p_fill * (spread - rebate + adv) + (1 - p_fill) * (spread + taker_fee)
    n_periods = h / 8.0

    gross, turn, fund_pnl, dates_out = [], [], [], []
    prevw = np.zeros(n_sym)

    for r in rebalance_rows:
        s = flow_arr[r, :]
        f = fwd_arr[r, :]
        valid = np.isfinite(s) & np.isfinite(f)
        n_valid = int(valid.sum())
        k_eff = min(k, n_valid // 2)
        if k_eff < 1:
            continue

        s_valid = s[valid]
        order = np.argsort(s_valid)
        valid_idx = np.where(valid)[0]
        bot = valid_idx[order[:k_eff]]
        top = valid_idx[order[-k_eff:]]

        w_ = np.zeros(n_sym)
        w_[bot] = -1.0 / k_eff
        w_[top] = 1.0 / k_eff

        g = float(np.nansum(w_ * f))
        fund_carry = 0.0
        if fund_arr is not None:
            rates = fund_arr[r, :]
            mask = np.isfinite(rates) & (np.abs(w_) > 1e-12)
            fund_carry = float(np.nansum(w_[mask] * rates[mask])) * n_periods / 1e4

        gross.append(g)
        turn.append(float(np.nansum(np.abs(w_ - prevw))))
        fund_pnl.append(fund_carry)
        dates_out.append(floww.index[r])
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

    mo = pd.Series(net, index=dates.tz_localize(None)).groupby(dates.tz_localize(None).to_period("M")).sum()
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


# ── gauntlet ─────────────────────────────────────────────────────────

def _monthly_net_series(net: np.ndarray, dates: pd.DatetimeIndex) -> pd.Series:
    s = pd.Series(net, index=dates.tz_localize(None))
    return s.groupby(s.index.to_period("M")).sum()


def bayesian_p_positive(monthly_net: np.ndarray, seed: int = 0,
                        num_warmup: int = 500, num_samples: int = 500) -> dict:
    """Simple Bayesian P(edge>0) on monthly net returns."""
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
    """Block-bootstrap CI on monthly mean net."""
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


def temporal_verdict(net: np.ndarray, dates: pd.DatetimeIndex,
                     n_windows: int = 4, seed: int = 0) -> dict:
    """Split into n_windows and fit per-window hierarchical model."""
    import jax
    import jax.numpy as jnp
    import numpyro
    import numpyro.distributions as dist
    from numpyro.infer import MCMC, NUTS

    mo = _monthly_net_series(net, dates)
    y = mo.to_numpy(float)
    if len(y) < n_windows * 2:
        return {"status": "insufficient", "p_positive": float("nan"),
                "worst_window_p_positive": float("nan")}

    # split into roughly equal windows
    split_idx = np.array_split(np.arange(len(y)), n_windows)
    window_means = [np.mean(y[idx]) for idx in split_idx if len(idx) > 0]
    window_ns = [len(idx) for idx in split_idx if len(idx) > 0]
    n_w = len(window_means)

    def _model(y_obs, n_obs, n_w_):
        mu = numpyro.sample("mu", dist.Normal(0.0, 0.5))
        tau = numpyro.sample("tau", dist.HalfNormal(0.5))
        sigma = numpyro.sample("sigma", dist.HalfNormal(1.0))
        nu = numpyro.sample("nu", dist.Gamma(2.0, 0.1))
        with numpyro.plate("windows", n_w_):
            z = numpyro.sample("z", dist.Normal(0.0, 1.0))
        mu_w = numpyro.deterministic("mu_w", mu + tau * z)
        se = sigma / jnp.sqrt(n_obs)
        numpyro.sample("obs", dist.StudentT(nu, mu_w, se), obs=y_obs)

    numpyro.set_host_device_count(2)
    mcmc = MCMC(NUTS(_model), num_warmup=400, num_samples=400,
                num_chains=2, chain_method="sequential", progress_bar=False)
    mcmc.run(jax.random.PRNGKey(seed),
             y_obs=jnp.asarray(window_means), n_obs=jnp.asarray(window_ns, float), n_w_=n_w)
    s = mcmc.get_samples()
    mu = np.asarray(s["mu"])
    mu_w = np.asarray(s["mu_w"])
    window_p = (mu_w > 0).mean(axis=0)
    return {
        "status": "ok",
        "p_positive": float((mu > 0).mean()),
        "worst_window_p_positive": float(window_p.min()),
        "frac_windows_positive": float((mu_w.mean(axis=0) > 0).mean()),
    }


def dsr_prob(net: np.ndarray, dates: pd.DatetimeIndex,
             trial_nets: list[np.ndarray], trial_dates: list[pd.DatetimeIndex]) -> float:
    """Deflated Sharpe probability: winner vs expected best-of-N noise."""
    from statistics import NormalDist

    mo_winner = _monthly_net_series(net, dates).to_numpy(float)
    winner_mean = float(mo_winner.mean())
    winner_se = float(mo_winner.std(ddof=1) / np.sqrt(len(mo_winner)))

    trial_means = []
    for tn, td in zip(trial_nets, trial_dates):
        mo = _monthly_net_series(tn, td).to_numpy(float)
        if len(mo) > 1:
            trial_means.append(float(mo.mean()))
    arr = np.asarray([m for m in trial_means if np.isfinite(m)], dtype=float)
    n = int(arr.size)
    if n < 2 or winner_se <= 0 or not np.isfinite(winner_mean):
        return float("nan")
    trial_std = float(arr.std(ddof=1))
    if trial_std <= 0:
        return float("nan")
    # expected max of n zero-mean normals with SD=trial_std
    gamma = 0.5772156649015329
    nd = NormalDist()
    z1 = nd.inv_cdf(1.0 - 1.0 / n)
    z2 = nd.inv_cdf(1.0 - 1.0 / (n * np.e))
    sr0 = trial_std * ((1.0 - gamma) * z1 + gamma * z2)
    z = (winner_mean - sr0) / winner_se
    return float(NormalDist().cdf(z))


def run_gauntlet(net: np.ndarray, dates: pd.DatetimeIndex,
                 trial_nets: list[np.ndarray], trial_dates: list[pd.DatetimeIndex],
                 label: str) -> dict:
    print(f"\n=== GAUNTLET: {label} ===")
    mo = _monthly_net_series(net, dates)
    print(f"Monthly observations: {len(mo)}  mean={mo.mean():+.3f}  std={mo.std():.3f}")

    bayes = bayesian_p_positive(mo.to_numpy(float))
    print(f"Bayesian P(edge>0) = {bayes['p_positive']:.3f}  mean={bayes['mean']:+.3f}  94% CI=[{bayes['lo']:+.3f}, {bayes['hi']:+.3f}]")

    boot = block_bootstrap_ci(net, dates)
    print(f"Block-bootstrap 90% CI = [{boot['lo']:+.3f}, {boot['hi']:+.3f}]")

    temp = temporal_verdict(net, dates)
    if temp["status"] == "ok":
        print(f"Temporal: P(edge>0)={temp['p_positive']:.3f}  worst_window={temp['worst_window_p_positive']:.3f}  frac_pos={temp['frac_windows_positive']:.1%}")
    else:
        print("Temporal: insufficient data")

    dsr = dsr_prob(net, dates, trial_nets, trial_dates)
    print(f"DSR = {dsr:.3f}")

    return {
        "bayesian": bayes,
        "bootstrap": boot,
        "temporal": temp,
        "dsr": dsr,
    }


# ── main ────────────────────────────────────────────────────────────

def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--no-download", action="store_true", help="Use cached parquets only")
    args = ap.parse_args()

    # load or ingest
    if args.no_download and Path(CACHE_PERP).exists():
        perp = pd.read_parquet(CACHE_PERP)
    else:
        print(f"Downloading perp klines for {len(SYMS)} symbols × {len(MONTHS)} months …")
        perp = ingest_perp()
        print(f"  cached → {CACHE_PERP}  ({len(perp):,} rows)")

    if args.no_download and Path(CACHE_FUND).exists():
        fund = pd.read_parquet(CACHE_FUND)
    else:
        print(f"Downloading funding rates for {len(SYMS)} symbols × {len(MONTHS)} months …")
        fund = ingest_funding()
        print(f"  cached → {CACHE_FUND}  ({len(fund):,} rows)")

    # filter to symbols with at least 1 year of data
    perp = perp[(perp["dt"] >= "2020-01-01") & (perp["dt"] < "2025-06-01")]
    perp = build_features(perp.sort_values(["symbol", "dt"]))
    perp = attach_funding(perp, fund)

    # drop symbols with < 5000 bars (too thin)
    bar_counts = perp.groupby("symbol").size()
    keep_syms = bar_counts[bar_counts >= 5000].index.tolist()
    perp = perp[perp["symbol"].isin(keep_syms)].copy()
    print(f"\nSymbols after thinning (≥5000 bars): {len(keep_syms)}")
    for sym in keep_syms:
        print(f"  {sym}: {bar_counts[sym]} bars")

    fund_coverage = perp["fund_bps"].notna().mean()
    print(f"\nFunding coverage: {fund_coverage:.1%}  mean fund8h={perp['fund_bps'].mean():.4f} bps")

    tv = (2020, 2021, 2022, 2023, 2024)
    ho = (2025,)

    fee_models = [
        {"name": "taker",      "spread_bps": 2.0, "maker_rebate_bps": 0.0, "taker_fee_bps": 7.5, "queue_pos": 1.0, "adv_bps": 0.0,  "p_fill_base": 0.0},
        {"name": "maker_best", "spread_bps": 2.0, "maker_rebate_bps": 0.2, "taker_fee_bps": 7.5, "queue_pos": 0.0, "adv_bps": 0.0,  "p_fill_base": 1.0},
        {"name": "maker_good", "spread_bps": 2.0, "maker_rebate_bps": 0.2, "taker_fee_bps": 7.5, "queue_pos": 0.2, "adv_bps": 0.3,  "p_fill_base": 0.9},
        {"name": "maker_real", "spread_bps": 2.0, "maker_rebate_bps": 0.2, "taker_fee_bps": 7.5, "queue_pos": 0.4, "adv_bps": 0.6,  "p_fill_base": 0.8},
        {"name": "maker_pess", "spread_bps": 2.0, "maker_rebate_bps": 0.2, "taker_fee_bps": 7.5, "queue_pos": 0.6, "adv_bps": 1.0,  "p_fill_base": 0.7},
    ]

    print(f"\n{'config':46s} {'gross':>7s} {'cost':>6s} {'fund':>5s} {'net':>7s} {'t':>6s} {'posM':>5s} {'Shrp':>6s} {'legs':>5s}")
    rows = []
    for w, h in product((6, 24), (6, 12, 24)):
        for k in (3, 5, 8):
            for fm in fee_models:
                r = backtest(perp, w, h, k, tv, fm, signal="flow6")
                m = metrics(r["gross"], r["turn"], r["fund_pnl"], r["dates"], h, fm)
                if not m:
                    continue
                name = f"w{w} h{h} k{k} {fm['name']}"
                rows.append((name, w, h, k, fm, r, m))
                print(f"{name:46s} {m['gross']:+7.2f} {m['cost']:6.2f} {m['fund_pnl']:5.2f} {m['net']:+7.2f} "
                      f"{m['t']:+6.2f} {m['posM']:5.0%} {m['sharpe']:+6.2f} {m['legs']:5d}")

    if not rows:
        print("ERROR: no valid backtest results.")
        return

    rows.sort(key=lambda r: r[6]["net"] if r[6] else -1e9, reverse=True)
    best = rows[0]
    name, w, h, k, fm_best, r_best, m_best = best
    print(f"\nBest by net (train+val): {name}")

    # collect all train+val net series for DSR trial pool
    trial_nets, trial_dates = [], []
    for _, _, _, _, fm_, r_, m_ in rows:
        if m_ and len(r_["gross"]) > 0:
            spread = fm_.get("spread_bps", 2.0) / 1e4
            rebate = fm_.get("maker_rebate_bps", 0.2) / 1e4
            taker_fee = fm_.get("taker_fee_bps", 7.5) / 1e4
            queue_pos = fm_.get("queue_pos", 0.3)
            adv = fm_.get("adv_bps", 0.5) / 1e4
            p_fill_base = fm_.get("p_fill_base", 0.85)
            p_fill = max(0.05, p_fill_base * (1 - queue_pos))
            cost_per_turn = p_fill * (spread - rebate + adv) + (1 - p_fill) * (spread + taker_fee)
            cost = r_["turn"] * cost_per_turn
            net = r_["gross"] - cost + r_["fund_pnl"]
            trial_nets.append(net)
            trial_dates.append(r_["dates"])

    # holdout
    print("\nHOLDOUT 2025 (read once) for best config:")
    holdout_results = {}
    for fm in fee_models:
        r = backtest(perp, w, h, k, ho, fm, signal="flow6")
        m = metrics(r["gross"], r["turn"], r["fund_pnl"], r["dates"], h, fm)
        if not m:
            continue
        holdout_results[fm["name"]] = (r, m)
        print(f"  {fm['name']:12s} gross={m['gross']:+.2f} cost={m['cost']:+.2f} fund={m['fund_pnl']:+.2f} "
              f"net={m['net']:+.2f} t={m['t']:+.2f} posM={m['posM']:.0%} sharpe={m['sharpe']:+.2f} legs={m['legs']}")

    # gauntlet on best holdout maker scenario
    for fm_name in ["maker_best", "maker_good", "taker"]:
        if fm_name not in holdout_results:
            continue
        r, m = holdout_results[fm_name]
        if len(r["gross"]) < 5:
            continue
        # compute net series for gauntlet
        spread = m['cost'] / (r["turn"].mean() * 1e4) * 1e4  # rough reconstruction
        # actually use the fee model directly
        holdout_results[fm_name][1]  # not used
        # compute cost per turn from fee model
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
        run_gauntlet(net_series, r["dates"], trial_nets, trial_dates,
                     label=f"{fm_name} holdout w{w} h{h} k{k}")

    # write findings
    out_path = Path("docs/analysis") / f"{pd.Timestamp.now(tz='UTC').strftime('%Y-%m-%d')}_crypto_flow_broad_findings.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Crypto cross-sectional flow — Stage-3 broadened universe + gauntlet\n",
        f"Date: {pd.Timestamp.now(tz='UTC').strftime('%Y-%m-%d %H:%M UTC')}\n",
        "## Method\n",
        f"- Data: Binance USD-M perp 1h klines ({len(keep_syms)} symbols, 2020–2025).\n",
        "- Funding: real 8h funding rates, as-of joined per symbol.\n",
        f"- Signal: causal {w}-bar rolling OFI.\n",
        f"- Book: concentrated top-{k}/bottom-{k} dollar-neutral, rebalanced every {h} bars.\n",
        "- Gauntlet: Bayesian P(edge>0), temporal-robustness, block-bootstrap CI, DSR.\n",
        "\n## Best config (train+val 2020-2024)\n",
        f"- `{name}`\n",
        "\n## Holdout 2025\n",
    ]
    for fm in fee_models:
        if fm["name"] not in holdout_results:
            continue
        _, m = holdout_results[fm["name"]]
        lines.append(f"- **{fm['name']}**: net={m['net']:+.2f} bps  t={m['t']:+.2f}  posM={m['posM']:.0%}  legs={m['legs']}\n")
    lines.append("\n## Verdict\n")
    lines.append("- More breadth + history applied. See gauntlet results above.\n")
    out_path.write_text("".join(lines))
    print(f"\nWrote findings → {out_path}")


if __name__ == "__main__":
    main()
