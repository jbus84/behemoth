"""
BoostLSS Reversion-OCO Meta-Labeler.

Two-stage pipeline:

  Stage 1 — GaussianLSS WFO (reversion_straddle.py)
    Identifies high-vol 1h bars where price is likely to spike and revert.

  Stage 2 — Meta-labeler (this script)
    Trains a HistGradientBoostingClassifier on tick-exact trade outcomes
    to predict P(TP) for each candidate trade.  Only trades where the
    classifier assigns P(TP) >= threshold are taken.

Key finding (3-pair tick-exact validation, ~12k OOS trades):
  OOS AUC = 0.83–0.86 across EURUSD / AUDUSD / GBPJPY.
  At threshold=0.55 (keep ~73% of trades):
    gross flips from −0.49 → +3.36 bps  (tick-exact, real bid/ask fills)
    maker net: −1.52 → +2.50 bps        (commission 0.70 bps RT, spread on SL only)
    annual ≈ 835 bps/pair (vs −690 unfiltered)

  Dominant features: oc (open-to-close of trigger bar), rng_norm, sigma_bps.
  Interpretation: momentum bars (close near high/low) fail; indecision bars
  (large range but close near open) revert cleanly.

Tick-exact fill model:
  Entry  — OCO straddle: both a sell-limit at (close + entry_k×sigma) and a buy-limit at
            (close − entry_k×sigma) placed simultaneously; whichever fills first is the trade.
            Short fills when BID >= level; long fills when ASK <= level.
  TP     — limit back to original close; fills when ASK <= close (short) or BID >= close (long)
  SL     — stop-market at entry ± sl_k×sigma; fills at mid on first tick past level
  Cost (held trade)  — commission 0.70 bps RT; spread added only on SL exits (~15% of trades)
  Cost (rejected)    — immediate market close: commission 0.70 bps RT + spread (Option B)

Option B post-fill filter:
  Every fill is scored by the meta-labeler.  If prob_tp >= threshold: hold to TP/SL.
  If prob_tp < threshold: close immediately at market, paying spread + commission.
  The "B all-in/fill" metric in the summary is the true all-in P&L per fill including
  both held and rejected trades.

Usage::

    # Tick-exact backtest + meta-label training on all pairs:
    uv run python scripts/boostlss_xs/meta_label_straddle.py \\
        --data-dir /path/to/tick_bars \\
        --tick-dir /path/to/raw_ticks \\
        --output-dir /tmp/meta_label_out \\
        [--pairs EURUSD GBPJPY ...] \\
        [--threshold 0.55] \\
        [--entry-k 0.5] [--tp-k 0.5] [--sl-k 1.0] [--hold-hours 8] [--sig-thresh 1.5]
"""
from __future__ import annotations

import argparse
import glob
import os
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

# ── Constants ────────────────────────────────────────────────────────────────

_USD_SIGN: dict[str, int] = {
    "USDJPY": 1, "USDCAD": 1, "USDCHF": 1,
    "EURUSD": -1, "GBPUSD": -1, "AUDUSD": -1, "NZDUSD": -1,
}
_SPREAD_BPS: dict[str, float] = {
    "EURUSD": 0.275, "GBPUSD": 0.699, "USDJPY": 0.432,
    "USDCAD": 0.885, "USDCHF": 1.020, "AUDUSD": 1.456,
    "EURAUD": 1.371, "EURCHF": 1.049, "EURGBP": 0.998,
    "EURJPY": 0.625, "EURNZD": 1.815,
    "GBPAUD": 1.671, "GBPCHF": 1.622, "GBPJPY": 1.146, "GBPNZD": 2.383,
    "AUDCAD": 2.202, "AUDJPY": 0.862, "AUDNZD": 1.863,
    "CADJPY": 1.218, "CHFJPY": 1.278, "NZDUSD": 1.758,
}
_DEFAULT_PAIRS: list[str] = [
    "EURUSD", "GBPUSD", "USDJPY", "USDCAD", "USDCHF", "AUDUSD",
    "EURAUD", "EURCHF", "EURGBP", "EURJPY", "EURNZD",
    "GBPAUD", "GBPCHF", "GBPJPY", "GBPNZD",
    "AUDCAD", "AUDJPY", "AUDNZD",
    "CADJPY", "CHFJPY", "NZDUSD",
]
_COMMISSION_RT: float = 0.70
_FEAT_COLS: list[str] = [
    "sigma_bps", "hour", "dow", "direction",
    "ret_norm", "mom_1", "mom_4", "mom_24",
    "rng_norm", "nt_norm", "oc", "rv", "live_spread",
]
_ROLL_N   = 200
_N_FOLDS  = 5
_MAX_TRAIN = 20_000


# ── Feature engineering ──────────────────────────────────────────────────────

def _causal_roll(x: np.ndarray, w: int) -> tuple[np.ndarray, np.ndarray]:
    n = len(x)
    nm = np.full(n, np.nan)
    ns = np.full(n, np.nan)
    cs  = np.nancumsum(np.where(np.isnan(x), 0.0, x))
    cs2 = np.nancumsum(np.where(np.isnan(x), 0.0, x ** 2))
    ok  = np.nancumsum(~np.isnan(x))
    for i in range(w, n):
        cnt = min(int(ok[i]), w)
        if cnt < 2:
            continue
        s0  = cs[i - w]  if i >= w else 0.0
        s20 = cs2[i - w] if i >= w else 0.0
        mu  = (cs[i] - s0) / cnt
        var = max((cs2[i] - s20) / cnt - mu ** 2, 0.0)
        nm[i] = mu
        ns[i] = np.sqrt(var) if var > 0 else 1e-9
    return nm, ns


def build_1h_features(sym: str, data_dir: str) -> dict:
    raw = pl.read_parquet(os.path.join(data_dir, f"{sym}_1m_flow.parquet")).sort("bucket")
    h1 = (
        raw.with_columns(pl.col("bucket").dt.truncate("1h").alias("g"))
        .group_by("g")
        .agg([
            pl.col("mid").last().alias("mid"),
            pl.col("mid").max().alias("hh"),
            pl.col("mid").min().alias("ll"),
            pl.col("mid").first().alias("op"),
            pl.col("n_ticks").sum().alias("nt"),
        ])
        .sort("g")
        .rename({"g": "ts"})
    )
    sign = _USD_SIGN.get(sym, 1)
    lm   = h1["mid"].log().to_numpy()
    n    = len(lm)
    ret  = np.full(n, np.nan)
    ret[1:] = np.diff(lm) * 1e4 * sign
    vals = ret[~np.isnan(ret)]
    mad  = max(float(np.median(np.abs(vals - np.median(vals)))), 1e-9)
    vs   = ret / mad

    rm, rs = _causal_roll(vs, _ROLL_N)
    ret_norm = np.where(rs > 0, (vs - rm) / rs, np.nan)
    cv = np.nancumsum(np.where(np.isnan(vs), 0.0, vs))

    def _ms(lag: int, w: int) -> np.ndarray:
        out = np.full(n, np.nan)
        for i in range(lag + w, n):
            out[i] = cv[i - lag] - (cv[i - lag - w] if i - lag - w >= 0 else 0.0)
        return out

    rng_bps  = (h1["hh"].to_numpy() - h1["ll"].to_numpy()) / h1["mid"].to_numpy() * 1e4
    rr, rrr  = _causal_roll(rng_bps, _ROLL_N)
    rng_norm = np.where(rrr > 0, (rng_bps - rr) / rrr, np.nan)
    nt       = h1["nt"].to_numpy().astype(float)
    nr, nrs  = _causal_roll(nt, _ROLL_N)
    nt_norm  = np.where(nrs > 0, (nt - nr) / nrs, np.nan)
    oc       = np.log(h1["mid"].to_numpy() / h1["op"].to_numpy()) * 1e4 * sign
    rv_rm, _ = _causal_roll(vs ** 2, _ROLL_N)
    rv       = np.sqrt(np.maximum(rv_rm, 0.0))
    tsp      = pd.DatetimeIndex(h1["ts"].to_numpy())

    feat_df = pd.DataFrame({
        "ts":       [str(t) for t in h1["ts"].to_numpy()],
        "mid":      h1["mid"].to_numpy(),
        "ret_norm": ret_norm,
        "mom_1":    _ms(1, 1),
        "mom_4":    _ms(1, 4),
        "mom_24":   _ms(1, 24),
        "rng_norm": rng_norm,
        "nt_norm":  nt_norm,
        "oc":       oc,
        "rv":       rv,
        "hour":     tsp.hour,
        "dow":      tsp.dayofweek,
    })
    X = np.column_stack([
        ret_norm, _ms(1,1), _ms(1,4), _ms(1,24),
        rng_norm, nt_norm, oc, rv,
        np.sin(2*np.pi*tsp.hour/24), np.cos(2*np.pi*tsp.hour/24),
        np.sin(2*np.pi*tsp.dayofweek/5), np.cos(2*np.pi*tsp.dayofweek/5),
    ]).astype(np.float32)
    return {
        "ts": h1["ts"].to_numpy(), "mid": h1["mid"].to_numpy(),
        "vs": vs, "mad": mad, "X": X, "feat_df": feat_df, "raw": raw,
    }


# ── WFO GaussianLSS ──────────────────────────────────────────────────────────

def fit_wfo_gaussian(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    from boostlss_py import BoostLssModel, PyFamily, PyTreeLearner  # type: ignore[import]

    n, n_feat = X.shape
    sg_oos    = np.full(n, np.nan)
    fold_size = n // (_N_FOLDS + 1)
    for fi in range(_N_FOLDS):
        tr_end   = fold_size * (fi + 1)
        te_start = tr_end + 8
        te_end   = min(te_start + fold_size, n)
        if te_end <= te_start:
            break
        ok  = ~(np.isnan(X[:tr_end]).any(axis=1) | np.isnan(y[:tr_end]))
        idx = np.where(ok)[0]
        if len(idx) > _MAX_TRAIN:
            idx = np.random.default_rng(42 + fi).choice(idx, _MAX_TRAIN, replace=False)
            idx.sort()
        if len(idx) < 200:
            continue
        model = BoostLssModel(PyFamily("GaussianLSS"), mstop=200, step_length=0.1)
        for p in ["mu", "sigma"]:
            model.add_learner(p, PyTreeLearner(feature_indices=list(range(n_feat)), max_depth=3))
        model.fit(X[idx].astype(np.float64), y[idx].astype(np.float64))
        sg_oos[te_start:te_end] = np.array(
            model.predict(X[te_start:te_end].astype(np.float64), "sigma"))
    return sg_oos


# ── Tick-exact simulation ────────────────────────────────────────────────────

def _load_month_pair(sym: str, tick_dir: str, ym: str) -> tuple | None:
    """Load one YYYYMM month of tick data. Returns None if missing."""
    files = sorted(glob.glob(os.path.join(tick_dir, sym, f"{sym}_{ym}*.parquet")))
    if not files:
        return None
    dfs = [pl.read_parquet(f, columns=["timestamp", "bid", "ask", "mid"]) for f in files]
    df  = pl.concat(dfs).sort("timestamp")
    ts  = df["timestamp"].cast(pl.Datetime("us")).to_numpy().astype("datetime64[us]")
    return ts, df["bid"].to_numpy(), df["ask"].to_numpy(), df["mid"].to_numpy()


def simulate_tick_exact(
    bar_ts: np.ndarray,
    bar_mid: float,
    sigma_bps: float,
    tick_ts: np.ndarray,
    tick_bid: np.ndarray,
    tick_ask: np.ndarray,
    tick_mid: np.ndarray,
    entry_k: float,
    tp_k: float,
    sl_k: float,
    hold_hours: int,
) -> tuple[str, float, float, int, np.datetime64 | None]:
    """
    True simultaneous-OCO tick-exact reversion for a single bar.

    Both legs are live at the same time:
      Upper leg (fade-short): limit sell at close + entry_k×sigma  → fills when BID >= level
      Lower leg (fade-long):  limit buy  at close - entry_k×sigma  → fills when ASK <= level

    Whichever leg the market reaches first determines direction.  If neither leg fills within
    hold_hours the trade is 'no_fill'.

    Exit rules (after entry fill):
      TP short: ASK <= original_close      (buying back at limit)
      TP long:  BID >= original_close      (selling at limit)
      SL:       mid crosses sl_level       (stop-market, taker)
      TB:       hold_hours expires with no exit

    Returns:
      (outcome, gross_bps, fill_spread_bps, direction, fill_ts)
      outcome    ∈ {'tp', 'sl', 'tb', 'no_fill', 'none'}
      direction  ∈ {+1 fade-short, -1 fade-long, 0 no fill}
      fill_ts    — datetime64[us] of the entry fill tick, or None if no fill
    """
    eg     = entry_k * sigma_bps
    sl_gap = sl_k * sigma_bps

    t0   = bar_ts.astype("datetime64[us]")
    tend = t0 + np.timedelta64(hold_hours, "h")
    lo   = np.searchsorted(tick_ts, t0,   side="right")
    hi   = np.searchsorted(tick_ts, tend,  side="right")
    if hi <= lo:
        return "none", 0.0, 0.0, 0, None

    bid_w  = tick_bid[lo:hi]
    ask_w  = tick_ask[lo:hi]
    mid_w  = tick_mid[lo:hi]
    ts_w   = tick_ts[lo:hi]
    c0     = bar_mid

    upper_entry = c0 * (1 + eg / 1e4)
    lower_entry = c0 * (1 - eg / 1e4)

    # Scan for whichever leg the market reaches first.
    entry_idx = None
    direction = 0
    for j in range(len(bid_w)):
        upper_hit = bid_w[j] >= upper_entry
        lower_hit = ask_w[j] <= lower_entry
        if upper_hit and lower_hit:
            # Both levels touched on the same tick (gap open / wide spread).
            # Treat as no_fill — ambiguous which would have been resting first.
            return "no_fill", 0.0, 0.0, 0, None
        if upper_hit:
            entry_idx = j
            direction = 1
            break
        if lower_hit:
            entry_idx = j
            direction = -1
            break

    if entry_idx is None:
        return "no_fill", 0.0, 0.0, 0, None

    fill_spread = (ask_w[entry_idx] - bid_w[entry_idx]) / mid_w[entry_idx] * 1e4
    fill_ts     = ts_w[entry_idx]

    if direction == 1:   # fade-short: sold at upper_entry
        fill_price = upper_entry
        sl_level   = fill_price * (1 + sl_gap / 1e4)
        tp_level   = c0
        for j in range(entry_idx + 1, len(ask_w)):
            if ask_w[j] <= tp_level:
                return "tp", (fill_price - ask_w[j]) / fill_price * 1e4, fill_spread, direction, fill_ts
            if mid_w[j] >= sl_level:
                return "sl", (fill_price - mid_w[j]) / fill_price * 1e4, fill_spread, direction, fill_ts
        return "tb", 0.0, fill_spread, direction, fill_ts

    else:   # fade-long: bought at lower_entry
        fill_price = lower_entry
        sl_level   = fill_price * (1 - sl_gap / 1e4)
        tp_level   = c0
        for j in range(entry_idx + 1, len(bid_w)):
            if bid_w[j] >= tp_level:
                return "tp", (bid_w[j] - fill_price) / fill_price * 1e4, fill_spread, direction, fill_ts
            if mid_w[j] <= sl_level:
                return "sl", (mid_w[j] - fill_price) / fill_price * 1e4, fill_spread, direction, fill_ts
        return "tb", 0.0, fill_spread, direction, fill_ts


# ── 1m fill-existence pre-filter ─────────────────────────────────────────────

def _has_fill_1m(
    i: int,
    ts_arr: np.ndarray,
    mid_arr: np.ndarray,
    sigma_bps: float,
    m1_ts: np.ndarray,
    m1_mid: np.ndarray,
    entry_k: float,
    hold_hours: int,
) -> bool:
    """
    Fast 1m-mid pre-filter: returns True if either OCO leg would fill within
    hold_hours based on 1m bar closes.  Used only to skip loading tick data for
    bars that clearly won't trade.  Direction is NOT derived here — the true
    simultaneous-OCO direction comes from simulate_tick_exact (tick bid/ask).
    """
    eg   = entry_k * sigma_bps
    t0   = ts_arr[i].astype("datetime64[us]")
    lo   = np.searchsorted(m1_ts, t0, side="right")
    mids = m1_mid[lo : lo + hold_hours * 60]
    if len(mids) == 0:
        return False
    c0    = mid_arr[i]
    moves = (mids - c0) / c0 * 1e4
    return any(abs(m) >= eg for m in moves)


# ── Per-pair tick-exact backtest ──────────────────────────────────────────────

def run_tick_backtest(
    sym: str,
    data_dir: str,
    tick_dir: str,
    entry_k: float = 0.5,
    tp_k: float    = 0.5,
    sl_k: float    = 1.0,
    hold_hours: int  = 8,
    sig_thresh: float = 1.5,
    verbose: bool   = True,
) -> pd.DataFrame:
    """
    Full tick-exact non-overlapping backtest for one symbol.
    Returns a DataFrame with one row per trade (including tick-exact outcome and features).
    """
    if verbose:
        print(f"  {sym}: building features + WFO...", flush=True)

    d   = build_1h_features(sym, data_dir)
    X   = d["X"]
    ts  = d["ts"]
    mid = d["mid"]
    vs  = d["vs"]
    mad = d["mad"]
    raw = d["raw"]
    feat_df = d["feat_df"]
    n   = len(ts)

    y = np.full(n, np.nan)
    y[:-1] = vs[1:]
    sg_oos = fit_wfo_gaussian(X, y)
    sbps   = np.clip(sg_oos * mad, 0.0, 200.0)

    m1_ts  = raw["bucket"].to_numpy().astype("datetime64[us]")
    m1_mid = raw["mid"].to_numpy()

    spread_med = _SPREAD_BPS.get(sym, 1.5)
    comm       = _COMMISSION_RT

    # Build candidate list using 1m pre-filter (checks if any fill likely; no direction used).
    # Blocked window is conservatively anchored to bar timestamp here; the precise
    # fill-time block is applied below using the actual tick fill timestamp.
    candidates: list[tuple[int, np.datetime64, float]] = []
    blocked_until = np.datetime64("1970", "us")
    for i in range(n):
        if np.isnan(sg_oos[i]) or sg_oos[i] <= sig_thresh:
            continue
        t_i = ts[i].astype("datetime64[us]")
        if t_i < blocked_until:
            continue
        if not _has_fill_1m(i, ts, mid, sbps[i], m1_ts, m1_mid, entry_k, hold_hours):
            continue
        candidates.append((i, t_i, sbps[i]))
        blocked_until = t_i + np.timedelta64(hold_hours, "h")

    if verbose:
        print(f"  {sym}: {len(candidates)} candidates → streaming tick data month-by-month...",
              flush=True)

    # Group candidates by the tick month(s) they need (bar month + possibly next month)
    rows: list[dict] = []
    cur_ym: str = ""
    cur_ticks: tuple | None = None

    # Second pass: non-overlap re-enforced on fill timestamps (not bar timestamps).
    # The pre-filter blocked_until above may admit a candidate whose previous trade
    # actually filled late (up to ~60min into the bar); we re-check here with the
    # precise fill time once tick data resolves it.
    blocked_until_tick  = np.datetime64("1970", "us")
    spread_fallback_n   = 0   # tracks how often fill_spread is implausible

    for i, t_i, sigma_bps_i in candidates:
        # Skip if still inside a previous trade's hold window (fill-time anchored).
        if t_i < blocked_until_tick:
            continue

        bar_dt  = pd.Timestamp(t_i)
        bar_ym  = bar_dt.strftime("%Y%m")
        # Trade window extends up to hold_hours forward — may spill into next month
        end_ym  = (bar_dt + pd.Timedelta(hours=hold_hours)).strftime("%Y%m")

        # Load month if changed
        if bar_ym != cur_ym:
            if bar_ym == end_ym:
                cur_ticks = _load_month_pair(sym, tick_dir, bar_ym)
            else:
                # Window spans two months — load and concat both
                m1 = _load_month_pair(sym, tick_dir, bar_ym)
                m2 = _load_month_pair(sym, tick_dir, end_ym)
                if m1 and m2:
                    cur_ticks = (
                        np.concatenate([m1[0], m2[0]]),
                        np.concatenate([m1[1], m2[1]]),
                        np.concatenate([m1[2], m2[2]]),
                        np.concatenate([m1[3], m2[3]]),
                    )
                else:
                    cur_ticks = m1 or m2
            cur_ym = bar_ym

        if cur_ticks is None:
            continue
        tick_ts, tick_bid, tick_ask, tick_mid = cur_ticks

        # True simultaneous-OCO: direction discovered from tick bid/ask.
        outcome, gross, fill_spread, direction, fill_ts = simulate_tick_exact(
            ts[i], mid[i], sigma_bps_i,
            tick_ts, tick_bid, tick_ask, tick_mid,
            entry_k, tp_k, sl_k, hold_hours,
        )
        if outcome in ("none", "no_fill"):
            continue

        # Block from actual fill time (not bar open time) to prevent overlap.
        if fill_ts is not None:
            blocked_until_tick = fill_ts + np.timedelta64(hold_hours, "h")

        # fill_spread: actual bid-ask at entry tick. Fall back to pair median if implausible.
        fill_spread_raw = fill_spread
        if fill_spread <= 0 or fill_spread > 50:
            fill_spread = spread_med
            spread_fallback_n += 1

        # Live spread: median of ~40 ticks around bar open (meta-label feature only)
        lo = max(np.searchsorted(tick_ts, t_i) - 20, 0)
        sp_arr = ((tick_ask - tick_bid) / tick_mid * 1e4)[lo : lo + 40]
        sp_arr = sp_arr[(sp_arr > 0) & (sp_arr < 100)]
        live_sp = float(np.median(sp_arr)) if len(sp_arr) > 0 else spread_med

        # TP: both legs limit orders → commission only.
        # SL: stop-market taker exit → commission + spread.
        # TB: time-barrier = market exit at expiry → commission + spread (same as SL).
        maker_cost = comm if outcome == "tp" else comm + fill_spread
        taker_cost = comm + fill_spread

        rows.append({
            "sym":             sym,
            "ts":              str(ts[i]),
            "outcome":         outcome,
            "direction":       direction,
            "gross":           gross,
            "maker_net":       gross - maker_cost,
            "taker_net":       gross - taker_cost,
            "sigma_bps":       sigma_bps_i,
            "live_spread":     live_sp,
            "spread_bps":      spread_med,
            "fill_spread":     fill_spread,
            "fill_spread_raw": fill_spread_raw,  # pre-fallback; NaN/0/outlier → implausible tick
        })

    df = pd.DataFrame(rows)
    if len(df) > 0:
        # Merge 1h features for meta-labeling
        df = df.merge(feat_df[["ts"] + [c for c in _FEAT_COLS
                                         if c not in ("sigma_bps","direction","live_spread")]],
                      on="ts", how="left")
    if verbose:
        n_trades  = len(df)
        tp_r      = (df.outcome == "tp").mean() if n_trades else 0
        fallback_r = spread_fallback_n / n_trades if n_trades else 0
        warn = "  ⚠ HIGH FALLBACK RATE" if fallback_r > 0.05 else ""
        print(f"  {sym}: {n_trades} trades  gross={df.gross.mean():+.3f}  "
              f"maker_net={df.maker_net.mean():+.3f}  TP%={tp_r:.1%}  "
              f"spread_fallback={fallback_r:.1%}{warn}", flush=True)
    return df


# ── Meta-labeler WFO ─────────────────────────────────────────────────────────

def fit_meta_label_wfo(df: pd.DataFrame) -> pd.DataFrame:
    """
    Train a HistGradientBoostingClassifier in causal WFO on tick-exact outcomes.
    Adds 'prob_tp' column to df; returns only OOS rows.
    """
    df = df.dropna(subset=_FEAT_COLS).copy()
    df["label"] = (df.outcome == "tp").astype(int)
    X  = df[_FEAT_COLS].values
    y  = df.label.values
    n  = len(df)
    fs = n // (_N_FOLDS + 1)

    oos_prob = np.full(n, np.nan)
    aucs: list[float] = []
    for fi in range(_N_FOLDS):
        tr_end   = fs * (fi + 1)
        te_start = tr_end
        te_end   = min(te_start + fs, n)
        if te_end <= te_start:
            break
        clf = HistGradientBoostingClassifier(max_iter=200, max_depth=4, random_state=42)
        clf.fit(X[:tr_end], y[:tr_end])
        oos_prob[te_start:te_end] = clf.predict_proba(X[te_start:te_end])[:, 1]
        auc = roc_auc_score(y[te_start:te_end], oos_prob[te_start:te_end])
        aucs.append(auc)

    mask = ~np.isnan(oos_prob)
    df_oos = df[mask].copy()
    df_oos["prob_tp"] = oos_prob[mask]
    df_oos["mean_auc"] = float(np.mean(aucs))
    return df_oos


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="BoostLSS reversion-OCO meta-labeler (tick-exact)")
    p.add_argument("--data-dir",   default="/Users/danielfisher/repositories/behemoth/data/tick_bars")
    p.add_argument("--tick-dir",   default="/Users/danielfisher/Desktop/tick")
    p.add_argument("--output-dir", default="/tmp/meta_label_out")
    p.add_argument("--pairs",      nargs="+", default=_DEFAULT_PAIRS)
    p.add_argument("--threshold",  type=float, default=0.55)
    p.add_argument("--entry-k",    type=float, default=0.5)
    p.add_argument("--tp-k",       type=float, default=0.5)
    p.add_argument("--sl-k",       type=float, default=1.0)
    p.add_argument("--hold-hours", type=int,   default=8)
    p.add_argument("--sig-thresh", type=float, default=1.5)
    return p.parse_args()


def _option_b_net_per_fill(df: pd.DataFrame, threshold: float) -> float:
    """
    Option B (post-fill filter) P&L per fill, accounting for rejected-trade exit cost.

    Every fill triggers the meta-labeler:
      accepted (prob_tp >= threshold) → hold to TP/SL, net = maker_net
      rejected (prob_tp <  threshold) → close immediately at market,
                                        net = -(spread_bps + commission_rt)
    Returns the per-fill average net across ALL fills.
    """
    accepted = df[df.prob_tp >= threshold]
    rejected = df[df.prob_tp < threshold]
    spread_col = "fill_spread" if "fill_spread" in df.columns else "spread_bps"
    reject_cost = rejected[spread_col] + _COMMISSION_RT
    total_net = accepted["maker_net"].sum() + (-reject_cost).sum()
    return float(total_net / len(df)) if len(df) else 0.0


def _print_summary(df: pd.DataFrame, threshold: float) -> None:
    print(f"\n{'═'*70}")
    print(f"META-LABEL RESULTS  threshold={threshold}")
    print(f"{'═'*70}")

    filtered = df[df.prob_tp >= threshold]
    rejected = df[df.prob_tp < threshold]
    spread_col = "fill_spread" if "fill_spread" in df.columns else "spread_bps"
    reject_cost_avg = (rejected[spread_col] + _COMMISSION_RT).mean() if len(rejected) else 0.0
    ob_net = _option_b_net_per_fill(df, threshold)

    # Spread fallback audit — fires when fill_spread was <=0 or >50 bps
    if "fill_spread_raw" in df.columns:
        n_fallback = ((df.fill_spread_raw <= 0) | (df.fill_spread_raw > 50)).sum()
        fallback_r = n_fallback / len(df)
        warn = "  ⚠ HIGH — cost model may be inaccurate" if fallback_r > 0.05 else "  OK"
        print(f"\n── Spread fallback audit ──")
        print(f"  Implausible fill_spread (≤0 or >50 bps): {n_fallback}/{len(df)} = {fallback_r:.1%}{warn}")
        if fallback_r > 0.05:
            by_pair = df.groupby("sym").apply(
                lambda g: ((g.fill_spread_raw <= 0) | (g.fill_spread_raw > 50)).mean()
            ).sort_values(ascending=False)
            print("  Per-pair fallback rates (top offenders):")
            for sym, r in by_pair[by_pair > 0.01].items():
                print(f"    {sym}: {r:.1%}")

    print("\n── Pooled ──")
    for label, sub in [("All (unfiltered)", df), (f"Filtered P≥{threshold}", filtered)]:
        if len(sub) == 0:
            continue
        print(f"  {label:<28}  n={len(sub):>5}  kept={len(sub)/len(df):>5.1%}  "
              f"gross={sub.gross.mean():>+7.3f}  maker_net={sub.maker_net.mean():>+7.3f}  "
              f"TP%={sub.label.mean():>5.1%}  AUC={sub.mean_auc.mean():.3f}")
    print(f"\n  Option B all-in (per fill, incl. rejected exit cost={reject_cost_avg:.2f} bps): "
          f"{ob_net:>+7.3f} bps")

    print(f"\n── By pair (filtered P≥{threshold}, Option B all-in per fill) ──")
    print(f"  {'Pair':<8}  {'n_all':>6}  {'kept%':>6}  {'Spread':>7}  "
          f"{'Maker net':>10}  {'Reject cost':>12}  {'B all-in':>9}  {'TP%':>7}  {'AUC':>6}")
    for sym, g_all in df.groupby("sym"):
        g = g_all[g_all.prob_tp >= threshold]
        r = g_all[g_all.prob_tp < threshold]
        if len(g_all) == 0:
            continue
        sp = g_all.spread_bps.iloc[0]
        kept = len(g) / len(g_all)
        rc = (r[spread_col] + _COMMISSION_RT).mean() if len(r) else sp + _COMMISSION_RT
        b_net = (g["maker_net"].sum() + (-rc * len(r))) / len(g_all)
        print(f"  {sym:<8}  {len(g_all):>6}  {kept:>5.1%}  {sp:>7.3f}  "
              f"{g['maker_net'].mean() if len(g) else 0:>+10.3f}  {-rc:>+12.3f}  "
              f"{b_net:>+9.3f}  {g['label'].mean() if len(g) else 0:>6.1%}  "
              f"{g_all.mean_auc.mean():>6.3f}")

    print("\n── By year (Option B all-in, pooled) ──")
    df2 = df.copy()
    df2["year"] = df2.ts.str[:4]
    df2["option_b_net"] = df2.apply(
        lambda r: r["maker_net"] if r["prob_tp"] >= threshold
        else -(r["spread_bps"] + _COMMISSION_RT), axis=1
    )
    for yr, g in df2.groupby("year"):
        print(f"  {yr}  n={len(g):>5}  option_b_net={g.option_b_net.mean():>+6.3f}  "
              f"win%={(g.option_b_net > 0).mean():.3f}")

    print("\n── Threshold sweep — Option B all-in per fill (pooled OOS) ──")
    print(f"  {'Thresh':>7}  {'n_all':>6}  {'kept%':>6}  {'maker_net (kept)':>17}  "
          f"{'B all-in/fill':>14}  {'TP% (kept)':>11}")
    for thr in [0.0, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85]:
        sub = df[df.prob_tp >= thr]
        if len(sub) < 100:
            break
        b = _option_b_net_per_fill(df, thr)
        print(f"  {thr:>7.2f}  {len(df):>6}  {len(sub)/len(df):>5.1%}  "
              f"{sub.maker_net.mean():>+17.3f}  {b:>+14.3f}  {sub.label.mean():>10.1%}")


if __name__ == "__main__":
    args = _parse_args()
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)

    tick_dfs: list[pd.DataFrame] = []
    for sym in args.pairs:
        flow_path = os.path.join(args.data_dir, f"{sym}_1m_flow.parquet")
        tick_path = os.path.join(args.tick_dir, sym)
        if not os.path.exists(flow_path) or not os.path.isdir(tick_path):
            print(f"  {sym}: missing data, skipping")
            continue
        df_sym = run_tick_backtest(
            sym=sym, data_dir=args.data_dir, tick_dir=args.tick_dir,
            entry_k=args.entry_k, tp_k=args.tp_k, sl_k=args.sl_k,
            hold_hours=args.hold_hours, sig_thresh=args.sig_thresh,
        )
        if len(df_sym) == 0:
            continue
        tick_dfs.append(df_sym)

    if not tick_dfs:
        print("No data found.")
        raise SystemExit(1)

    all_raw = pd.concat(tick_dfs, ignore_index=True)
    raw_path = os.path.join(args.output_dir, "tick_exact_raw.csv")
    all_raw.to_csv(raw_path, index=False)

    print("\nFitting meta-labeler (per-pair causal WFO)...", flush=True)
    oos_dfs: list[pd.DataFrame] = []
    for sym, g in all_raw.groupby("sym"):
        print(f"  {sym}...", flush=True)
        try:
            oos_dfs.append(fit_meta_label_wfo(g.copy()))
        except Exception as e:
            print(f"  {sym}: meta-label failed — {e}")

    if not oos_dfs:
        print("Meta-labeling produced no results.")
        raise SystemExit(1)

    result = pd.concat(oos_dfs, ignore_index=True)
    out_path = os.path.join(args.output_dir, "meta_label_trades.csv")
    result.to_csv(out_path, index=False)
    print(f"\nTrade log → {out_path}")
    _print_summary(result, args.threshold)
