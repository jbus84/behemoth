#!/usr/bin/env python3
"""
Causal walk-forward sweep: lower-Z rules + hard ML bad-trade gate.

This script evaluates family mixes under a moderate low-Z regime and promotes
candidates with strict single-day DD-first gates.
"""

from __future__ import annotations

import argparse
import itertools
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.report_strategy_fx_comm_multi_tf import (  # noqa: E402
    OIL_LINKED_PAIRS,
    PAIR_WHITELIST_BASE,
    _apply_guardrail,
    _derive_risk_bps,
    _filter_pairs_by_sharpe,
    _metrics_with_risk,
)
from scripts.sweep_strategy_families import (  # noqa: E402
    FAMILY_LIBRARY,
    _build_pair_states,
    _generate_family_trades,
)


def _parse_grid(s: str) -> list[float]:
    return [float(x.strip()) for x in str(s).split(",") if x.strip()]


def _parse_str_grid(s: str) -> list[str]:
    return [x.strip().upper() for x in str(s).split(",") if x.strip()]


def _parse_mixes(s: str, short_families: list[str], long_families: list[str]) -> list[dict[str, str]]:
    raw = str(s).strip()
    if raw.lower() in {"all", "*"}:
        return [{"m5": a, "m15": b, "m60": c} for a, b, c in itertools.product(short_families, short_families, long_families)]

    mixes: list[dict[str, str]] = []
    parts = [x.strip() for x in raw.split(";") if x.strip()]
    for part in parts:
        m: dict[str, str] = {}
        for tok in [z.strip() for z in part.split(",") if z.strip()]:
            if "=" not in tok:
                raise ValueError(f"Invalid mix token: {tok}")
            tf, fam = tok.split("=", 1)
            tf = tf.strip().lower()
            fam = fam.strip().upper()
            if tf not in {"m5", "m15", "m60"}:
                raise ValueError(f"Unsupported timeframe in mix: {tf}")
            m[tf] = fam
        if set(m.keys()) != {"m5", "m15", "m60"}:
            raise ValueError(f"Mix must include m5,m15,m60: {part}")
        mixes.append(m)
    if not mixes:
        mixes.append({"m5": "MOM_BURST", "m15": "REV_EXHAUSTION", "m60": "MOM_PERSIST"})
    return mixes


def _mix_id(m: dict[str, str]) -> str:
    return f"m5_{m['m5'].lower()}__m15_{m['m15'].lower()}__m60_{m['m60'].lower()}"


def _candidate_id(mix: dict[str, str], z_enter: float, z_stop: float, hold_mult: float) -> str:
    return f"{_mix_id(mix)}__ze{z_enter:.2f}_zs{z_stop:.2f}_hm{hold_mult:.2f}"


def _year_bounds_ns(year: int) -> tuple[int, int]:
    start = pd.Timestamp(year=year, month=1, day=1, tz="UTC")
    end = pd.Timestamp(year=year + 1, month=1, day=1, tz="UTC")
    return int(start.value), int(end.value)


def _make_folds(start_year: int, end_year: int, embargo_days: int) -> list[dict]:
    folds: list[dict] = []
    emb_ns = int(pd.Timedelta(days=embargo_days).value)
    for y in range(start_year, end_year + 1):
        t0, t1 = _year_bounds_ns(y)
        folds.append({
            "year": y,
            "train_end": int(t0 - emb_ns),
            "test_start": int(t0),
            "test_end": int(t1),
        })
    return folds


def _norm01(s: pd.Series) -> pd.Series:
    x = pd.to_numeric(s, errors="coerce").astype(float)
    lo = float(x.min())
    hi = float(x.max())
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return pd.Series(np.full(len(x), 0.5, dtype=float), index=x.index)
    return (x - lo) / (hi - lo)


def _feature_matrix(df: pd.DataFrame) -> pd.DataFrame:
    ts = pd.to_datetime(df["timestamp"], unit="ns", utc=True)
    num = pd.DataFrame(
        {
            "abs_z": pd.to_numeric(df["z_score"], errors="coerce").abs(),
            "z_velocity": pd.to_numeric(df.get("z_velocity", np.nan), errors="coerce"),
            "z_accel": pd.to_numeric(df.get("z_accel", np.nan), errors="coerce"),
            "duration_bars": pd.to_numeric(df.get("duration_bars", np.nan), errors="coerce"),
            "max_hold_bars": pd.to_numeric(df.get("max_hold_bars", np.nan), errors="coerce"),
            "entry_hour_utc": ts.dt.hour.astype(float),
            "entry_dow_utc": ts.dt.dayofweek.astype(float),
        },
        index=df.index,
    )
    cat = pd.DataFrame(
        {
            "pair": df["pair"].astype(str),
            "timeframe": df["timeframe"].astype(str),
            "side": df["side"].astype(str),
            "active_leg": df["active_leg"].astype(str),
            "strategy_family": df.get("strategy_family", "NA").astype(str),
        },
        index=df.index,
    )
    out = pd.concat([num, pd.get_dummies(cat, drop_first=False, dtype=float)], axis=1)
    return out.fillna(0.0)


def _label_quantile(train_df: pd.DataFrame, test_df: pd.DataFrame, pt_q: float, sl_q: float) -> tuple[pd.Series, pd.Series, dict[str, tuple[float, float]]]:
    barriers: dict[str, tuple[float, float]] = {}
    for tf, sub in train_df.groupby("timeframe", sort=True):
        pos = sub.loc[sub["pnl_bps"] > 0.0, "pnl_bps"]
        neg = sub.loc[sub["pnl_bps"] < 0.0, "pnl_bps"].abs()
        pt = float(pos.quantile(pt_q)) if len(pos) else 1.0
        sl = float(neg.quantile(sl_q)) if len(neg) else 1.0
        barriers[str(tf)] = (max(pt, 1e-6), max(sl, 1e-6))

    def _apply(df: pd.DataFrame) -> pd.Series:
        y = np.full(len(df), -1, dtype=int)
        for i, row in enumerate(df.itertuples(index=False)):
            tf = str(row.timeframe)
            pt, sl = barriers.get(tf, (1.0, 1.0))
            pnl = float(row.pnl_bps)
            if pnl <= -sl:
                y[i] = 1
            elif pnl >= pt:
                y[i] = 0
            else:
                y[i] = -1
        return pd.Series(y, index=df.index, dtype="int64")

    return _apply(train_df), _apply(test_df), barriers


def _time_split(df: pd.DataFrame, labeled_mask: pd.Series, cal_frac: float) -> tuple[pd.Series, pd.Series]:
    frac = float(np.clip(cal_frac, 0.0, 0.5))
    idx = df.index[labeled_mask].to_numpy()
    if len(idx) < 200:
        return labeled_mask.copy(), pd.Series(False, index=df.index)
    ordered = df.loc[idx].sort_values(["exit_ts", "timestamp"]).index.to_numpy()
    cut = int(round(len(ordered) * (1.0 - frac)))
    cut = max(50, min(cut, len(ordered) - 50))
    tr = set(ordered[:cut].tolist())
    ca = set(ordered[cut:].tolist())
    train_mask = df.index.to_series().isin(tr)
    cal_mask = df.index.to_series().isin(ca)
    return train_mask, cal_mask


def _fit_calibrator(method: str, p_raw_cal: np.ndarray, y_cal: np.ndarray):
    m = str(method).lower()
    if len(y_cal) < 100 or len(np.unique(y_cal)) < 2:
        return lambda p: np.clip(p, 0.0, 1.0), "none"
    if m == "isotonic":
        iso = IsotonicRegression(out_of_bounds="clip")
        iso.fit(p_raw_cal, y_cal)
        return lambda p: np.clip(iso.predict(np.asarray(p, dtype=float)), 0.0, 1.0), "isotonic"
    if m in {"platt", "sigmoid"}:
        lr = LogisticRegression(solver="lbfgs", max_iter=200)
        lr.fit(p_raw_cal.reshape(-1, 1), y_cal.astype(int))
        return (
            lambda p: np.clip(lr.predict_proba(np.asarray(p, dtype=float).reshape(-1, 1))[:, 1], 0.0, 1.0),
            "platt",
        )
    return lambda p: np.clip(p, 0.0, 1.0), "none"


def _fit_predict_bad_prob(
    tr_short: pd.DataFrame,
    te_short: pd.DataFrame,
    y_tr: pd.Series,
    calibration_method: str,
    calibration_frac: float,
    random_state: int,
) -> dict:
    X = _feature_matrix(pd.concat([tr_short, te_short], ignore_index=False))
    X_tr = X.loc[tr_short.index]
    X_te = X.loc[te_short.index]
    labeled = (y_tr != -1)
    if int(labeled.sum()) < 200 or len(np.unique(y_tr[labeled].astype(int).to_numpy())) < 2:
        raise RuntimeError("Not enough labeled rows with two classes.")

    model_mask, cal_mask = _time_split(tr_short, labeled, cal_frac=calibration_frac)
    if len(np.unique(y_tr.loc[model_mask].astype(int).to_numpy())) < 2:
        model_mask = labeled.copy()
        cal_mask = pd.Series(False, index=tr_short.index)

    model = HistGradientBoostingClassifier(
        max_depth=4,
        learning_rate=0.05,
        max_iter=300,
        min_samples_leaf=80,
        random_state=int(random_state),
    )
    model.fit(X_tr.loc[model_mask], y_tr.loc[model_mask].astype(int))

    p_raw_tr = model.predict_proba(X_tr)[:, 1].astype(float)
    p_raw_te = model.predict_proba(X_te)[:, 1].astype(float)
    p_cal_tr = p_raw_tr.copy()
    p_cal_te = p_raw_te.copy()
    eff = "none"

    brier_raw = np.nan
    brier_cal = np.nan
    logloss_raw = np.nan
    logloss_cal = np.nan

    if calibration_method != "none" and int(cal_mask.sum()) >= 100:
        y_cal = y_tr.loc[cal_mask].astype(int).to_numpy()
        p_raw_cal = p_raw_tr[cal_mask.to_numpy()]
        cal_fn, eff = _fit_calibrator(calibration_method, p_raw_cal=p_raw_cal, y_cal=y_cal)
        p_cal_tr = cal_fn(p_raw_tr)
        p_cal_te = cal_fn(p_raw_te)
        p_cal_cal = cal_fn(p_raw_cal)
        brier_raw = float(brier_score_loss(y_cal, np.clip(p_raw_cal, 1e-6, 1 - 1e-6)))
        brier_cal = float(brier_score_loss(y_cal, np.clip(p_cal_cal, 1e-6, 1 - 1e-6)))
        logloss_raw = float(log_loss(y_cal, np.clip(p_raw_cal, 1e-6, 1 - 1e-6)))
        logloss_cal = float(log_loss(y_cal, np.clip(p_cal_cal, 1e-6, 1 - 1e-6)))

    return {
        "proba_raw_tr": pd.Series(np.clip(p_raw_tr, 0.0, 1.0), index=tr_short.index),
        "proba_raw_te": pd.Series(np.clip(p_raw_te, 0.0, 1.0), index=te_short.index),
        "proba_cal_tr": pd.Series(np.clip(p_cal_tr, 0.0, 1.0), index=tr_short.index),
        "proba_cal_te": pd.Series(np.clip(p_cal_te, 0.0, 1.0), index=te_short.index),
        "calibration_method": eff,
        "brier_raw": brier_raw,
        "brier_cal": brier_cal,
        "logloss_raw": logloss_raw,
        "logloss_cal": logloss_cal,
    }


def _pair_keep_set(train_guard_df: pd.DataFrame, cutoff: float) -> set[str]:
    if train_guard_df.empty:
        return set()
    out: set[str] = set()
    for pair, sub in train_guard_df.groupby("pair", sort=True):
        m = _metrics_with_risk(sub, risk_bps=_derive_risk_bps(sub, fallback=100.0))
        if float(m["sharpe"]) >= float(cutoff):
            out.add(str(pair))
    if not out:
        out = set(train_guard_df["pair"].astype(str).unique().tolist())
    return out


def _apply_pair_keep(df: pd.DataFrame, pair_keep: set[str]) -> pd.DataFrame:
    if not pair_keep:
        return df.copy()
    return df[df["pair"].astype(str).isin(pair_keep)].copy().reset_index(drop=True)


def _select_threshold_train(
    tr_short: pd.DataFrame,
    tr_long: pd.DataFrame,
    p_bad_tr: pd.Series,
    threshold_grid: list[float],
    pair_keep: set[str],
    risk_bps: float,
    min_sharpe_retention: float,
    min_annualized_retention: float,
) -> tuple[float, pd.DataFrame]:
    rows = []

    base_guard = _apply_pair_keep(_apply_guardrail(pd.concat([tr_short, tr_long], ignore_index=True)), pair_keep)
    base_m = _metrics_with_risk(base_guard, risk_bps=risk_bps)

    for thr in threshold_grid:
        kept_short = tr_short[p_bad_tr <= float(thr)].copy()

        ml_only = pd.concat([kept_short, tr_long], ignore_index=True).sort_values(["timestamp", "pair"]).reset_index(drop=True)
        combined = _apply_pair_keep(_apply_guardrail(ml_only), pair_keep)
        m = _metrics_with_risk(combined, risk_bps=risk_bps)

        worst_day_impr = float(m["worst_single_day_bps"] - base_m["worst_single_day_bps"])
        sharpe_ret = float(m["sharpe"] / max(1e-9, base_m["sharpe"])) if base_m["sharpe"] > 0 else 0.0
        ann_ret = float(m["annualized_bps_calendar"] / max(1e-9, base_m["annualized_bps_calendar"])) if base_m["annualized_bps_calendar"] > 0 else 0.0

        eligible = (
            (worst_day_impr >= 0.0)
            and (sharpe_ret >= float(min_sharpe_retention))
            and (ann_ret >= float(min_annualized_retention))
            and (m["trades"] > 200)
        )
        rows.append(
            {
                "threshold": float(thr),
                "eligible": bool(eligible),
                "worst_day_improvement_bps": worst_day_impr,
                "sharpe_retention": sharpe_ret,
                "annualized_retention": ann_ret,
                **m,
            }
        )

    grid = pd.DataFrame(rows)
    if grid.empty:
        return float(threshold_grid[0]), grid

    grid["score"] = (
        0.60 * _norm01(grid["worst_day_improvement_bps"])
        + 0.20 * _norm01(grid["sharpe"])
        + 0.20 * _norm01(grid["annualized_bps_calendar"])
    )

    cand = grid[grid["eligible"]].copy()
    if cand.empty:
        cand = grid.copy()

    best = cand.sort_values(
        ["score", "worst_day_improvement_bps", "sharpe", "annualized_bps_calendar"],
        ascending=[False, False, False, False],
    ).iloc[0]
    return float(best["threshold"]), grid


def _load_comparator(path: Path, mix_id: str) -> dict[str, float]:
    if not path.exists():
        raise FileNotFoundError(f"Missing comparator summary: {path}")
    df = pd.read_csv(path)
    if "variant" in df.columns:
        df = df[df["variant"].astype(str) == "meta_tb_promoted"].copy()
    if mix_id:
        sub = df[df["mix_id"].astype(str) == str(mix_id)].copy()
        if not sub.empty:
            row = sub.iloc[0]
            return row.to_dict()
    row = df.sort_values(["sharpe", "annualized_bps_calendar"], ascending=[False, False]).iloc[0]
    return row.to_dict()


def main() -> None:
    p = argparse.ArgumentParser(description="Low-Z + ML hard gate walk-forward sweep.")
    p.add_argument("--exclude-oil", action="store_true", default=True)
    p.add_argument("--short-families", default="MOM_PERSIST,MOM_BURST,REV_EXHAUSTION")
    p.add_argument("--long-families", default="MOM_PERSIST,REV_EXHAUSTION")
    p.add_argument("--mixes", default="all")

    p.add_argument("--z-enter-grid", default="1.2,1.4,1.6")
    p.add_argument("--z-stop-grid", default="2.4,2.8")
    p.add_argument("--hold-mult-grid", default="0.7,0.9")

    p.add_argument("--min-gap-m5", type=int, default=20)
    p.add_argument("--min-gap-m15", type=int, default=16)
    p.add_argument("--min-gap-m60", type=int, default=8)

    p.add_argument("--start-test-year", type=int, default=2020)
    p.add_argument("--end-test-year", type=int, default=2025)
    p.add_argument("--embargo-days", type=int, default=5)

    p.add_argument("--pt-quantile", type=float, default=0.60)
    p.add_argument("--sl-quantile", type=float, default=0.60)

    p.add_argument("--pbad-threshold-grid", default="0.35,0.45,0.55,0.65")
    p.add_argument("--calibration-method", default="isotonic", choices=["isotonic", "platt", "none"])
    p.add_argument("--calibration-frac", type=float, default=0.20)

    p.add_argument("--pair-sharpe-cutoff", type=float, default=0.30)
    p.add_argument("--max-candidates", type=int, default=24)
    p.add_argument("--top-k", type=int, default=5)

    p.add_argument("--promote-single-day-improve-frac", type=float, default=0.25)
    p.add_argument("--promote-time-reduction-frac", type=float, default=0.30)
    p.add_argument("--promote-sharpe-retention", type=float, default=0.70)
    p.add_argument("--promote-annualized-retention", type=float, default=0.60)

    p.add_argument("--comparator-summary", default="data/analysis/meta_tb_mixed_no_oil_allmix_summary.csv")
    p.add_argument("--comparator-mix-id", default="m5_mom__m15_mom__m60_rev")

    p.add_argument("--random-state", type=int, default=42)
    p.add_argument("--out-prefix", default="lowz_ml_hardgate")
    args = p.parse_args()

    pair_whitelist = list(PAIR_WHITELIST_BASE)
    if args.exclude_oil:
        pair_whitelist = [x for x in pair_whitelist if x not in OIL_LINKED_PAIRS]

    short_families = _parse_str_grid(args.short_families)
    long_families = _parse_str_grid(args.long_families)
    for f in list(set(short_families + long_families)):
        if f not in FAMILY_LIBRARY:
            raise ValueError(f"Unsupported family: {f}")

    mixes = _parse_mixes(args.mixes, short_families=short_families, long_families=long_families)

    z_enter_grid = _parse_grid(args.z_enter_grid)
    z_stop_grid = _parse_grid(args.z_stop_grid)
    hold_mult_grid = _parse_grid(args.hold_mult_grid)
    thr_grid = _parse_grid(args.pbad_threshold_grid)

    print("Building states...")
    state_cache = {
        "m5": _build_pair_states("m5", pair_whitelist=pair_whitelist, vel_lookback=20),
        "m15": _build_pair_states("m15", pair_whitelist=pair_whitelist, vel_lookback=20),
        "m60": _build_pair_states("m60", pair_whitelist=pair_whitelist, vel_lookback=20),
    }

    # Build per-timeframe/family/parameter cache once.
    spec_cache: dict[tuple[str, str, float, float, float], pd.DataFrame] = {}
    min_gap_by_tf = {"m5": int(args.min_gap_m5), "m15": int(args.min_gap_m15), "m60": int(args.min_gap_m60)}

    families_used = set(short_families + long_families)
    for tf in ["m5", "m15", "m60"]:
        for fam in sorted(families_used):
            for ze, zs, hm in itertools.product(z_enter_grid, z_stop_grid, hold_mult_grid):
                key = (tf, fam, float(ze), float(zs), float(hm))
                spec = replace(
                    FAMILY_LIBRARY[fam],
                    z_enter=float(ze),
                    z_stop=float(zs),
                    hold_mult=float(hm),
                    min_gap=int(min_gap_by_tf[tf]),
                )
                df = _generate_family_trades(tf, spec, state_cache[tf])
                df["z_enter"] = float(ze)
                df["z_stop"] = float(zs)
                df["hold_mult"] = float(hm)
                spec_cache[key] = df

    # Candidate prefilter by rules-only quality.
    candidates: list[dict] = []
    for mix in mixes:
        for ze, zs, hm in itertools.product(z_enter_grid, z_stop_grid, hold_mult_grid):
            cid = _candidate_id(mix, float(ze), float(zs), float(hm))
            m5 = spec_cache[("m5", mix["m5"], float(ze), float(zs), float(hm))]
            m15 = spec_cache[("m15", mix["m15"], float(ze), float(zs), float(hm))]
            m60 = spec_cache[("m60", mix["m60"], float(ze), float(zs), float(hm))]

            short = pd.concat([m5, m15], ignore_index=True)
            full = pd.concat([short, m60], ignore_index=True).sort_values(["timestamp", "pair"]).reset_index(drop=True)
            if full.empty or short.empty:
                continue

            risk_bps = _derive_risk_bps(full, fallback=100.0)
            base_guard = _apply_guardrail(full)
            base_guard = _filter_pairs_by_sharpe(base_guard, cutoff=float(args.pair_sharpe_cutoff))
            m = _metrics_with_risk(base_guard, risk_bps=risk_bps)

            candidates.append(
                {
                    "candidate_id": cid,
                    "mix_id": _mix_id(mix),
                    "m5_family": mix["m5"],
                    "m15_family": mix["m15"],
                    "m60_family": mix["m60"],
                    "z_enter": float(ze),
                    "z_stop": float(zs),
                    "hold_mult": float(hm),
                    "prefilter_trades": int(m["trades"]),
                    "prefilter_sharpe": float(m["sharpe"]),
                    "prefilter_ann_bps": float(m["annualized_bps_calendar"]),
                    "prefilter_worst_day_bps": float(m["worst_single_day_bps"]),
                }
            )

    cand_df = pd.DataFrame(candidates)
    if cand_df.empty:
        raise RuntimeError("No candidates produced any trades.")

    cand_df["prefilter_score"] = (
        0.5 * _norm01(cand_df["prefilter_worst_day_bps"])
        + 0.25 * _norm01(cand_df["prefilter_sharpe"])
        + 0.25 * _norm01(cand_df["prefilter_ann_bps"])
    )
    cand_df = cand_df.sort_values(["prefilter_score", "prefilter_sharpe"], ascending=[False, False]).head(int(args.max_candidates)).reset_index(drop=True)

    folds = _make_folds(args.start_test_year, args.end_test_year, args.embargo_days)

    fold_rows: list[dict] = []
    threshold_rows: list[dict] = []
    ablation_rows: list[dict] = []
    scored_rows: list[pd.DataFrame] = []
    oos_rows: list[pd.DataFrame] = []

    summary_rows: list[dict] = []

    for c in cand_df.itertuples(index=False):
        ze = float(c.z_enter)
        zs = float(c.z_stop)
        hm = float(c.hold_mult)

        m5 = spec_cache[("m5", c.m5_family, ze, zs, hm)]
        m15 = spec_cache[("m15", c.m15_family, ze, zs, hm)]
        m60 = spec_cache[("m60", c.m60_family, ze, zs, hm)]

        short_all = pd.concat([m5, m15], ignore_index=True).sort_values(["timestamp", "pair"]).reset_index(drop=True)
        long_all = m60.sort_values(["timestamp", "pair"]).reset_index(drop=True)
        if short_all.empty:
            continue

        short_all.index = np.arange(len(short_all))
        long_all.index = np.arange(len(long_all))
        risk_bps = _derive_risk_bps(pd.concat([short_all, long_all], ignore_index=True), fallback=100.0)

        cand_oos_combined: list[pd.DataFrame] = []

        for fold in folds:
            tr_short = short_all[short_all["exit_ts"] < fold["train_end"]].copy()
            te_short = short_all[(short_all["exit_ts"] >= fold["test_start"]) & (short_all["exit_ts"] < fold["test_end"])].copy()
            tr_long = long_all[long_all["exit_ts"] < fold["train_end"]].copy()
            te_long = long_all[(long_all["exit_ts"] >= fold["test_start"]) & (long_all["exit_ts"] < fold["test_end"])].copy()

            if len(tr_short) < 1200 or te_short.empty:
                continue

            y_tr, y_te, _ = _label_quantile(tr_short, te_short, pt_q=float(args.pt_quantile), sl_q=float(args.sl_quantile))
            if int((y_tr != -1).sum()) < 500:
                continue

            try:
                fit = _fit_predict_bad_prob(
                    tr_short=tr_short,
                    te_short=te_short,
                    y_tr=y_tr,
                    calibration_method=args.calibration_method,
                    calibration_frac=float(args.calibration_frac),
                    random_state=int(args.random_state + fold["year"] + int(100 * ze + 10 * zs + hm * 100)),
                )
            except RuntimeError:
                continue

            train_base = _apply_guardrail(pd.concat([tr_short, tr_long], ignore_index=True))
            pair_keep = _pair_keep_set(train_base, cutoff=float(args.pair_sharpe_cutoff))

            best_thr, thr_grid_df = _select_threshold_train(
                tr_short=tr_short,
                tr_long=tr_long,
                p_bad_tr=fit["proba_cal_tr"],
                threshold_grid=thr_grid,
                pair_keep=pair_keep,
                risk_bps=risk_bps,
                min_sharpe_retention=0.50,
                min_annualized_retention=0.40,
            )

            for r in thr_grid_df.itertuples(index=False):
                threshold_rows.append(
                    {
                        "candidate_id": c.candidate_id,
                        "fold_year": int(fold["year"]),
                        "threshold": float(r.threshold),
                        "eligible": bool(r.eligible),
                        "score": float(r.score),
                        "worst_day_improvement_bps": float(r.worst_day_improvement_bps),
                        "sharpe_retention": float(r.sharpe_retention),
                        "annualized_retention": float(r.annualized_retention),
                        "trades": int(r.trades),
                        "sharpe": float(r.sharpe),
                        "annualized_bps_calendar": float(r.annualized_bps_calendar),
                        "worst_single_day_bps": float(r.worst_single_day_bps),
                    }
                )

            keep_te = fit["proba_cal_te"] <= float(best_thr)

            # rules-only
            rules_only = _apply_pair_keep(_apply_guardrail(pd.concat([te_short, te_long], ignore_index=True)), pair_keep)
            m_rules = _metrics_with_risk(rules_only, risk_bps=risk_bps)

            # ml-only
            ml_short = te_short.loc[keep_te].copy()
            ml_only = pd.concat([ml_short, te_long], ignore_index=True).sort_values(["timestamp", "pair"]).reset_index(drop=True)
            m_ml_only = _metrics_with_risk(ml_only, risk_bps=risk_bps)

            # combined
            combined = _apply_pair_keep(_apply_guardrail(ml_only), pair_keep)
            m_combined = _metrics_with_risk(combined, risk_bps=risk_bps)

            for variant, mm in [
                ("rules_only", m_rules),
                ("ml_only", m_ml_only),
                ("combined", m_combined),
            ]:
                ablation_rows.append(
                    {
                        "candidate_id": c.candidate_id,
                        "fold_year": int(fold["year"]),
                        "variant": variant,
                        "threshold": float(best_thr),
                        "calibration_method": str(fit["calibration_method"]),
                        "cal_brier_raw": fit["brier_raw"],
                        "cal_brier_cal": fit["brier_cal"],
                        "cal_logloss_raw": fit["logloss_raw"],
                        "cal_logloss_cal": fit["logloss_cal"],
                        **mm,
                    }
                )

            fold_rows.append(
                {
                    "candidate_id": c.candidate_id,
                    "mix_id": c.mix_id,
                    "fold_year": int(fold["year"]),
                    "threshold": float(best_thr),
                    "rules_trades": int(m_rules["trades"]),
                    "rules_sharpe": float(m_rules["sharpe"]),
                    "rules_annualized_bps": float(m_rules["annualized_bps_calendar"]),
                    "rules_worst_single_day_bps": float(m_rules["worst_single_day_bps"]),
                    "combined_trades": int(m_combined["trades"]),
                    "combined_sharpe": float(m_combined["sharpe"]),
                    "combined_annualized_bps": float(m_combined["annualized_bps_calendar"]),
                    "combined_worst_single_day_bps": float(m_combined["worst_single_day_bps"]),
                }
            )

            score_df = te_short[["pair", "timeframe", "strategy_type", "strategy_family", "timestamp", "exit_ts", "pnl_bps", "duration_bars"]].copy()
            score_df["candidate_id"] = c.candidate_id
            score_df["mix_id"] = c.mix_id
            score_df["fold_year"] = int(fold["year"])
            score_df["z_enter"] = ze
            score_df["z_stop"] = zs
            score_df["hold_mult"] = hm
            score_df["pbad_threshold"] = float(best_thr)
            score_df["p_bad_raw"] = fit["proba_raw_te"].to_numpy(dtype=float)
            score_df["p_bad_calibrated"] = fit["proba_cal_te"].to_numpy(dtype=float)
            score_df["ml_keep_flag"] = keep_te.to_numpy(dtype=bool)
            score_df["tb_label_proxy"] = y_te.to_numpy(dtype=int)
            scored_rows.append(score_df)

            out = combined.copy()
            out["candidate_id"] = c.candidate_id
            out["mix_id"] = c.mix_id
            out["fold_year"] = int(fold["year"])
            out["variant"] = "combined"
            out["z_enter"] = ze
            out["z_stop"] = zs
            out["hold_mult"] = hm
            out["pbad_threshold"] = float(best_thr)
            oos_rows.append(out)
            cand_oos_combined.append(out)

        if cand_oos_combined:
            agg = pd.concat(cand_oos_combined, ignore_index=True)
            mm = _metrics_with_risk(agg, risk_bps=_derive_risk_bps(agg, fallback=100.0))
            summary_rows.append(
                {
                    "candidate_id": c.candidate_id,
                    "mix_id": c.mix_id,
                    "m5_family": c.m5_family,
                    "m15_family": c.m15_family,
                    "m60_family": c.m60_family,
                    "z_enter": ze,
                    "z_stop": zs,
                    "hold_mult": hm,
                    **mm,
                }
            )

    if not summary_rows:
        raise RuntimeError("No candidate produced valid OOS rows.")

    summary = pd.DataFrame(summary_rows)
    comparator = _load_comparator(ROOT / args.comparator_summary, mix_id=str(args.comparator_mix_id))

    comp_sharpe = float(comparator.get("sharpe", np.nan))
    comp_ann = float(comparator.get("annualized_bps_calendar", np.nan))
    comp_worst = float(comparator.get("worst_single_day_bps", comparator.get("max_daily_dd_bps", np.nan)))
    comp_time = float(comparator.get("time_in_market_pct", np.nan))

    if not np.isfinite(comp_time):
        comp_time = float(summary.sort_values(["sharpe", "annualized_bps_calendar"], ascending=[False, False]).iloc[0]["time_in_market_pct"])

    summary["comparator_mix_id"] = str(comparator.get("mix_id", ""))
    summary["comparator_sharpe"] = comp_sharpe
    summary["comparator_annualized_bps"] = comp_ann
    summary["comparator_worst_single_day_bps"] = comp_worst
    summary["comparator_time_in_market_pct"] = comp_time

    summary["delta_sharpe"] = summary["sharpe"] - comp_sharpe
    summary["delta_annualized_bps"] = summary["annualized_bps_calendar"] - comp_ann
    summary["delta_worst_single_day_bps"] = summary["worst_single_day_bps"] - comp_worst
    summary["delta_time_in_market_pct"] = summary["time_in_market_pct"] - comp_time

    summary["single_day_dd_improve_frac"] = np.where(abs(comp_worst) > 1e-9, summary["delta_worst_single_day_bps"] / abs(comp_worst), 0.0)
    summary["time_reduction_frac"] = np.where(comp_time > 1e-9, (comp_time - summary["time_in_market_pct"]) / comp_time, 0.0)
    summary["sharpe_retention_frac"] = np.where(comp_sharpe > 1e-9, summary["sharpe"] / comp_sharpe, 0.0)
    summary["annualized_retention_frac"] = np.where(comp_ann > 1e-9, summary["annualized_bps_calendar"] / comp_ann, 0.0)

    # lightweight per-timeframe trade count gates
    oos_all = pd.concat(oos_rows, ignore_index=True) if oos_rows else pd.DataFrame()
    per_tf_counts = oos_all.groupby(["candidate_id", "timeframe"]).size().rename("tf_trades").reset_index() if not oos_all.empty else pd.DataFrame(columns=["candidate_id", "timeframe", "tf_trades"])
    tf_min_ok = {}
    for cid, sub in per_tf_counts.groupby("candidate_id"):
        tf_min_ok[cid] = bool((sub["tf_trades"] >= 250).all())

    summary["per_tf_trade_gate"] = summary["candidate_id"].map(lambda x: tf_min_ok.get(x, False))

    summary["eligible"] = (
        (summary["single_day_dd_improve_frac"] >= float(args.promote_single_day_improve_frac))
        & (summary["time_reduction_frac"] >= float(args.promote_time_reduction_frac))
        & (summary["sharpe_retention_frac"] >= float(args.promote_sharpe_retention))
        & (summary["annualized_retention_frac"] >= float(args.promote_annualized_retention))
        & (summary["trades"] >= 1500)
        & (summary["per_tf_trade_gate"])
    )

    summary["score"] = (
        0.45 * _norm01(summary["single_day_dd_improve_frac"])
        + 0.25 * _norm01(summary["time_reduction_frac"])
        + 0.20 * _norm01(summary["sharpe"])
        + 0.10 * _norm01(summary["annualized_bps_calendar"])
    )

    ranked = summary.sort_values(["eligible", "score", "single_day_dd_improve_frac", "sharpe"], ascending=[False, False, False, False]).reset_index(drop=True)
    ranked["rank"] = np.arange(1, len(ranked) + 1)

    selected = ranked[ranked["eligible"]].copy()
    if selected.empty:
        selected = ranked.head(max(1, int(args.top_k))).copy()
    else:
        selected = selected.head(max(1, int(args.top_k))).copy()

    selected_ids = set(selected["candidate_id"].astype(str).tolist())

    selected_trades = oos_all[oos_all["candidate_id"].astype(str).isin(selected_ids)].copy() if not oos_all.empty else pd.DataFrame()
    if not selected_trades.empty:
        selected_trades["variant"] = "lowz_ml_hardgate_selected"
        selected_trades = selected_trades.merge(
            selected[["candidate_id", "rank", "score", "eligible"]],
            on="candidate_id",
            how="left",
        )

    out_dir = ROOT / "data" / "analysis"
    out_dir.mkdir(parents=True, exist_ok=True)

    fold_path = out_dir / f"{args.out_prefix}_fold_metrics.csv"
    thr_path = out_dir / f"{args.out_prefix}_threshold_grid.csv"
    abl_path = out_dir / f"{args.out_prefix}_ablation.csv"
    scored_path = out_dir / f"{args.out_prefix}_oos_scored_trades.csv"
    oos_path = out_dir / f"{args.out_prefix}_oos_trades.csv"
    sum_path = out_dir / f"{args.out_prefix}_summary.csv"
    rank_path = out_dir / f"{args.out_prefix}_ranking.csv"
    sel_path = out_dir / f"{args.out_prefix}_selected_trades.csv"

    pd.DataFrame(fold_rows).to_csv(fold_path, index=False)
    pd.DataFrame(threshold_rows).to_csv(thr_path, index=False)
    pd.DataFrame(ablation_rows).to_csv(abl_path, index=False)
    (pd.concat(scored_rows, ignore_index=True) if scored_rows else pd.DataFrame()).to_csv(scored_path, index=False)
    oos_all.to_csv(oos_path, index=False)
    summary.to_csv(sum_path, index=False)
    ranked.to_csv(rank_path, index=False)
    selected_trades.to_csv(sel_path, index=False)

    print("Comparator:")
    print({
        "mix_id": comparator.get("mix_id", ""),
        "sharpe": comp_sharpe,
        "annualized_bps_calendar": comp_ann,
        "worst_single_day_bps": comp_worst,
        "time_in_market_pct": comp_time,
    })
    print("\nTop ranked:")
    show_cols = [
        "rank",
        "candidate_id",
        "trades",
        "mean_pnl_per_trade_bps",
        "sharpe",
        "annualized_bps_calendar",
        "worst_single_day_bps",
        "single_day_dd_improve_frac",
        "time_in_market_pct",
        "time_reduction_frac",
        "eligible",
        "score",
    ]
    print(ranked[show_cols].head(max(5, int(args.top_k))).to_string(index=False))
    print("\nSaved:")
    print(f"- {fold_path}")
    print(f"- {thr_path}")
    print(f"- {abl_path}")
    print(f"- {scored_path}")
    print(f"- {oos_path}")
    print(f"- {sum_path}")
    print(f"- {rank_path}")
    print(f"- {sel_path}")


if __name__ == "__main__":
    main()
