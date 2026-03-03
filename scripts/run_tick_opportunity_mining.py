#!/usr/bin/env python3
"""Mine high-count gross-positive opportunities from tick-bar datasets.

Purpose:
- Build broad candidate libraries for downstream ML filtering.
- Keep selection criterion simple: high annualized fills + positive gross expectancy.
- Keep directional and OCO-straddle opportunity types separate.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

try:
    import yaml
except Exception:
    yaml = None  # type: ignore[assignment]


DEFAULTS: dict[str, Any] = {
    "symbol": "EURUSD",
    "dataset_dir": "data/analysis/tick_velocity",
    "bar_ticks_grid": "100,1000,2000",
    "horizons": "1,2,3,4,5,6",
    "train_years": "2022,2023,2024",
    "test_year": 2025,
    "min_annual_fills": 5000.0,
    "gross_metric": "mean",
    "library_type": "separate",  # separate|directional|oco
    "barrier_grid_pips": "2,3,5,8,10",
    "out_dir": "data/analysis/tick_opportunity_mining",
    "report_out": "docs/analysis/eurusd_tick_opportunity_mining_report.md",
}


def _parse_ints(raw: str) -> list[int]:
    return [int(x.strip()) for x in str(raw).split(",") if x.strip()]


def _parse_floats(raw: str) -> list[float]:
    return [float(x.strip()) for x in str(raw).split(",") if x.strip()]


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    if yaml is None:
        raise RuntimeError("PyYAML required for --config")
    obj = yaml.safe_load(path.read_text(encoding="utf-8"))
    if obj is None:
        return {}
    if not isinstance(obj, dict):
        raise ValueError(f"Config root must be mapping: {path}")
    return dict(obj)


def _merge_config(args: argparse.Namespace) -> dict[str, Any]:
    cfg = dict(DEFAULTS)
    cfg_path = getattr(args, "config", "")
    if str(cfg_path).strip():
        cfg.update(_load_yaml(Path(str(cfg_path))))
    for k, v in vars(args).items():
        if k == "config":
            continue
        if v is not None:
            cfg[k] = v
    return cfg


def _pip_size(symbol: str) -> float:
    s = str(symbol).upper().strip()
    if s.endswith("JPY"):
        return 0.01
    if s.startswith("XAU"):
        return 0.1
    if s.startswith("XAG"):
        return 0.01
    return 0.0001


def _annualized_count(n: int, ts: pd.Series) -> float:
    if n <= 0:
        return 0.0
    t = pd.to_datetime(ts, utc=True, errors="coerce").dropna()
    if t.empty:
        return float(n)
    days = max((t.max() - t.min()).total_seconds() / 86400.0, 1.0)
    return float(n) * 365.25 / days


def _safe_numeric(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").astype(float)


def _prepare_frame(path: Path, *, symbol: str, horizons: list[int]) -> pd.DataFrame:
    d = pd.read_parquet(path).copy()
    d["close_ts"] = pd.to_datetime(d["close_ts"], utc=True, errors="coerce")
    d = d[d["close_ts"].notna()].sort_values("close_ts").reset_index(drop=True)
    if d.empty:
        return d

    req = [
        "open",
        "high",
        "low",
        "close",
        "cost_est_pips",
        "range_pips",
        "hour_utc",
        "spread_z",
        "tick_rate_z",
        "vel_cost_units_h1",
    ]
    miss = [c for c in req if c not in d.columns]
    if miss:
        raise ValueError(f"{path.name} missing columns: {miss}")

    pip = float(_pip_size(symbol))
    d["open"] = _safe_numeric(d["open"])
    d["high"] = _safe_numeric(d["high"])
    d["low"] = _safe_numeric(d["low"])
    d["close"] = _safe_numeric(d["close"])
    d["cost_est_pips"] = _safe_numeric(d["cost_est_pips"])
    d["range_pips"] = _safe_numeric(d["range_pips"])
    d["hour_utc"] = _safe_numeric(d["hour_utc"])
    d["spread_z"] = _safe_numeric(d["spread_z"]).fillna(0.0)
    d["tick_rate_z"] = _safe_numeric(d["tick_rate_z"]).fillna(0.0)
    d["vel_cost_units_h1"] = _safe_numeric(d["vel_cost_units_h1"]).fillna(0.0)

    if "vel_pips_h1" in d.columns:
        d["ret1_pips"] = _safe_numeric(d["vel_pips_h1"]).fillna(0.0)
    else:
        d["ret1_pips"] = ((d["close"] - d["close"].shift(1)) / pip).fillna(0.0)
    if "vel_z_h1" in d.columns:
        d["ret_z"] = _safe_numeric(d["vel_z_h1"])
    else:
        std = d["ret1_pips"].rolling(96, min_periods=24).std(ddof=0).shift(1)
        d["ret_z"] = d["ret1_pips"] / std.replace(0.0, np.nan)
    d["ret_abs_z"] = d["ret_z"].abs().fillna(0.0)
    d["vel_abs_cost_units_h1"] = d["vel_cost_units_h1"].abs().fillna(0.0)

    if "hl_first" in d.columns:
        d["hl_first"] = _safe_numeric(d["hl_first"]).fillna(0.0)
    else:
        d["hl_first"] = 0.0
    if "hl_first_mean_24" in d.columns:
        d["hl_first_mean_24"] = _safe_numeric(d["hl_first_mean_24"]).fillna(0.0)
    else:
        d["hl_first_mean_24"] = d["hl_first"].rolling(24, min_periods=8).mean().shift(1).fillna(0.0)
    if "hl_pos_frac_mean_24" in d.columns:
        d["hl_pos_frac_mean_24"] = _safe_numeric(d["hl_pos_frac_mean_24"]).fillna(0.0)
    else:
        d["hl_pos_frac_mean_24"] = 0.0

    d["year"] = d["close_ts"].dt.year.astype(int)
    for h in sorted(set(int(x) for x in horizons if int(x) > 0)):
        col = f"y_fwd_pips_h{h}"
        if col not in d.columns:
            d[col] = ((d["close"].shift(-h) - d["open"].shift(-1)) / pip).astype(float)
        else:
            d[col] = _safe_numeric(d[col])
    return d.replace([np.inf, -np.inf], np.nan)


def _quantiles(train: pd.DataFrame) -> dict[str, float]:
    return {
        "cost_q30": float(train["cost_est_pips"].quantile(0.30)),
        "cost_q50": float(train["cost_est_pips"].quantile(0.50)),
        "rng_q70": float(train["range_pips"].quantile(0.70)),
        "rng_q80": float(train["range_pips"].quantile(0.80)),
        "shock_q60": float(train["ret_abs_z"].quantile(0.60)),
        "shock_q70": float(train["ret_abs_z"].quantile(0.70)),
        "shock_q80": float(train["ret_abs_z"].quantile(0.80)),
        "vel_q70": float(train["vel_abs_cost_units_h1"].quantile(0.70)),
        "vel_q80": float(train["vel_abs_cost_units_h1"].quantile(0.80)),
        "spread_q70": float(train["spread_z"].quantile(0.70)),
        "tick_q30": float(train["tick_rate_z"].quantile(0.30)),
    }


def _regime_masks(test: pd.DataFrame, q: dict[str, float]) -> list[tuple[str, np.ndarray]]:
    h = test["hour_utc"]
    c = test["cost_est_pips"]
    r = test["range_pips"]
    v = test["vel_abs_cost_units_h1"]
    return [
        ("all", np.ones(len(test), dtype=bool)),
        ("low_cost_q30", (c <= q["cost_q30"]).to_numpy(dtype=bool)),
        ("low_cost_q50", (c <= q["cost_q50"]).to_numpy(dtype=bool)),
        ("high_range_q70", (r >= q["rng_q70"]).to_numpy(dtype=bool)),
        ("high_range_q80", (r >= q["rng_q80"]).to_numpy(dtype=bool)),
        ("high_abs_vel_q70", (v >= q["vel_q70"]).to_numpy(dtype=bool)),
        ("high_abs_vel_q80", (v >= q["vel_q80"]).to_numpy(dtype=bool)),
        ("london", h.isin([7, 8, 9, 10, 11]).to_numpy(dtype=bool)),
        ("ny_overlap", h.isin([13, 14, 15, 16]).to_numpy(dtype=bool)),
        ("asia", h.isin([0, 1, 2, 3, 4, 5]).to_numpy(dtype=bool)),
        (
            "low_cost_q30_and_high_range_q70",
            ((c <= q["cost_q30"]) & (r >= q["rng_q70"])).to_numpy(dtype=bool),
        ),
        (
            "low_cost_q30_and_high_abs_vel_q70",
            ((c <= q["cost_q30"]) & (v >= q["vel_q70"])).to_numpy(dtype=bool),
        ),
    ]


def _directional_family_states(
    test: pd.DataFrame, q: dict[str, float]
) -> list[tuple[str, np.ndarray, np.ndarray]]:
    ret1 = test["ret1_pips"].to_numpy(dtype=float)
    ret_sign = np.sign(ret1).astype(np.int8)
    shock = test["ret_abs_z"].to_numpy(dtype=float)
    spread_z = test["spread_z"].to_numpy(dtype=float)
    tick_z = test["tick_rate_z"].to_numpy(dtype=float)
    rng = test["range_pips"].to_numpy(dtype=float)
    vel = test["vel_abs_cost_units_h1"].to_numpy(dtype=float)
    hlf = test["hl_first"].to_numpy(dtype=float)
    hlf24 = test["hl_first_mean_24"].to_numpy(dtype=float)
    hour = test["hour_utc"].to_numpy(dtype=float)

    out: list[tuple[str, np.ndarray, np.ndarray]] = []
    shock70 = shock >= q["shock_q70"]
    shock60 = shock >= q["shock_q60"]
    shock80 = shock >= q["shock_q80"]
    out.append(("shock_follow", (shock70 & (ret_sign != 0)), ret_sign))
    out.append(("shock_revert", (shock70 & (ret_sign != 0)), (-ret_sign).astype(np.int8)))
    out.append(
        (
            "liquidity_revert",
            (shock70 & (ret_sign != 0) & (spread_z >= q["spread_q70"]) & (tick_z <= q["tick_q30"])),
            (-ret_sign).astype(np.int8),
        )
    )
    out.append(
        (
            "vol_expand_follow",
            (ret_sign != 0) & (rng >= q["rng_q70"]) & (vel >= q["vel_q70"]) & shock60,
            ret_sign,
        )
    )
    out.append(
        (
            "session_london_follow",
            (ret_sign != 0) & shock60 & np.isin(hour, [7, 8, 9, 10, 11]),
            ret_sign,
        )
    )
    out.append(
        (
            "session_ny_overlap_follow",
            (ret_sign != 0) & shock60 & np.isin(hour, [13, 14, 15, 16]),
            ret_sign,
        )
    )
    out.append(("path_follow", (np.abs(hlf) > 0.0) & shock60, np.sign(hlf).astype(np.int8)))
    out.append(("path_revert", (np.abs(hlf) > 0.0) & shock60, (-np.sign(hlf)).astype(np.int8)))
    out.append(
        ("path_persist_24", (np.abs(hlf24) >= 0.20) & shock60, np.sign(hlf24).astype(np.int8))
    )
    out.append(("shock_extreme_revert", (shock80 & (ret_sign != 0)), (-ret_sign).astype(np.int8)))
    return out


def _metric_from_gross(gross: np.ndarray) -> dict[str, float]:
    vals = np.asarray(gross, dtype=float)
    vals = vals[np.isfinite(vals)]
    if len(vals) == 0:
        return {
            "mean_gross_pips_test": float("nan"),
            "median_gross_pips_test": float("nan"),
            "gross_std_test": float("nan"),
            "hit_rate_gross_test": float("nan"),
        }
    return {
        "mean_gross_pips_test": float(np.mean(vals)),
        "median_gross_pips_test": float(np.median(vals)),
        "gross_std_test": float(np.std(vals, ddof=0)),
        "hit_rate_gross_test": float(np.mean(vals > 0.0)),
    }


def _assign_quality_tier(df: pd.DataFrame, *, library: str) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    mean_g = pd.to_numeric(out["mean_gross_pips_test"], errors="coerce").fillna(-np.inf)
    hit = pd.to_numeric(out["hit_rate_gross_test"], errors="coerce").fillna(0.0)
    std = pd.to_numeric(out["gross_std_test"], errors="coerce").fillna(np.inf)
    annual = pd.to_numeric(out["annualized_test_fills"], errors="coerce").fillna(0.0)
    both = pd.to_numeric(out.get("both_window_rate", np.nan), errors="coerce").fillna(1.0)
    sel = out["selection_pass"].astype(bool)

    if str(library).lower() == "directional":
        a = (mean_g >= 0.25) & (hit >= 0.52) & (std <= 6.0) & (annual >= 10000.0)
        b = (mean_g >= 0.10) & (hit >= 0.505) & (std <= 8.0) & (annual >= 5000.0)
    else:
        a = (mean_g >= 1.0) & (hit >= 0.55) & (both <= 0.55) & (annual >= 10000.0)
        b = (mean_g >= 0.40) & (hit >= 0.52) & (both <= 0.70) & (annual >= 5000.0)
    tier = np.where(a, "A", np.where(b, "B", np.where(sel, "C", "D")))
    out["quality_tier"] = tier
    out["quality_score"] = np.where(
        tier == "A",
        3,
        np.where(tier == "B", 2, np.where(tier == "C", 1, 0)),
    ).astype(int)
    return out


def _directional_candidates(
    *,
    train: pd.DataFrame,
    test: pd.DataFrame,
    symbol: str,
    bar_ticks: int,
    horizons: list[int],
    min_annual_fills: float,
    gross_metric: str,
) -> pd.DataFrame:
    q = _quantiles(train)
    regimes = _regime_masks(test, q)
    families = _directional_family_states(test, q)
    rows: list[dict[str, Any]] = []

    train_q = _quantiles(train)
    train_regimes = _regime_masks(train, train_q)
    train_families = _directional_family_states(train, train_q)
    train_regime_map = {k: v for k, v in train_regimes}
    train_family_map = {k: (m, s) for k, m, s in train_families}

    ts_test = pd.to_datetime(test["close_ts"], utc=True, errors="coerce")
    for h in horizons:
        ycol = f"y_fwd_pips_h{h}"
        if ycol not in test.columns:
            continue
        y_test = pd.to_numeric(test[ycol], errors="coerce").to_numpy(dtype=float)
        y_train = (
            pd.to_numeric(train[ycol], errors="coerce").to_numpy(dtype=float)
            if ycol in train.columns
            else np.full(len(train), np.nan)
        )
        valid_test = np.isfinite(y_test)
        valid_train = np.isfinite(y_train)
        if h > 0:
            valid_test[-h:] = False
            valid_train[-h:] = False

        for fam, fam_mask, fam_side in families:
            fam_mask = np.asarray(fam_mask, dtype=bool)
            fam_side = np.asarray(fam_side, dtype=np.int8)
            tfm, tside = train_family_map[fam]
            tfm = np.asarray(tfm, dtype=bool)
            tside = np.asarray(tside, dtype=np.int8)
            for regime_name, regime_mask in regimes:
                reg = np.asarray(regime_mask, dtype=bool)
                m = valid_test & fam_mask & reg & (fam_side != 0)
                n = int(np.sum(m))
                if n <= 0:
                    continue
                gross = fam_side[m].astype(float) * y_test[m]
                tmask = valid_train & tfm & train_regime_map[regime_name] & (tside != 0)
                train_gross = tside[tmask].astype(float) * y_train[tmask]
                train_vals = train_gross[np.isfinite(train_gross)]
                annual = _annualized_count(n, ts_test[m])
                stats = _metric_from_gross(gross)
                mean_train = float(np.mean(train_vals)) if len(train_vals) > 0 else float("nan")
                median_train = float(np.median(train_vals)) if len(train_vals) > 0 else float("nan")
                metric_val = (
                    stats["mean_gross_pips_test"]
                    if str(gross_metric).lower() == "mean"
                    else stats["median_gross_pips_test"]
                )
                rows.append(
                    {
                        "symbol": symbol,
                        "bar_ticks": int(bar_ticks),
                        "horizon": int(h),
                        "family": fam,
                        "state_id": f"{fam}__{regime_name}",
                        "regime_desc": regime_name,
                        "train_count": int(np.sum(tmask)),
                        "test_count": int(n),
                        "annualized_test_fills": float(annual),
                        "mean_gross_pips_train": mean_train,
                        "mean_gross_pips_test": stats["mean_gross_pips_test"],
                        "median_gross_pips_train": median_train,
                        "median_gross_pips_test": stats["median_gross_pips_test"],
                        "gross_std_test": stats["gross_std_test"],
                        "hit_rate_gross_test": stats["hit_rate_gross_test"],
                        "both_window_rate": float("nan"),
                        "p_up_first": float("nan"),
                        "ml_ready_target_type": "directional_sign",
                        "selection_pass": bool(
                            np.isfinite(metric_val)
                            and metric_val > 0.0
                            and annual >= float(min_annual_fills)
                        ),
                    }
                )
    return pd.DataFrame(rows)


def _oco_candidates(
    *,
    train: pd.DataFrame,
    test: pd.DataFrame,
    symbol: str,
    bar_ticks: int,
    horizons: list[int],
    barrier_grid_pips: list[float],
    min_annual_fills: float,
    gross_metric: str,
) -> pd.DataFrame:
    q = _quantiles(train)
    regimes = _regime_masks(test, q)
    train_q = _quantiles(train)
    train_regimes = _regime_masks(train, train_q)
    {k: np.asarray(v, dtype=bool) for k, v in train_regimes}

    pip = float(_pip_size(symbol))
    close_test = pd.to_numeric(test["close"], errors="coerce").to_numpy(dtype=float)
    high_test = pd.to_numeric(test["high"], errors="coerce").to_numpy(dtype=float)
    low_test = pd.to_numeric(test["low"], errors="coerce").to_numpy(dtype=float)
    hlf_test = pd.to_numeric(test["hl_first"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    ts_test = pd.to_datetime(test["close_ts"], utc=True, errors="coerce")

    close_train = pd.to_numeric(train["close"], errors="coerce").to_numpy(dtype=float)
    high_train = pd.to_numeric(train["high"], errors="coerce").to_numpy(dtype=float)
    low_train = pd.to_numeric(train["low"], errors="coerce").to_numpy(dtype=float)
    hlf_train = pd.to_numeric(train["hl_first"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    ts_train = pd.to_datetime(train["close_ts"], utc=True, errors="coerce")

    rows: list[dict[str, Any]] = []
    train_cache: dict[tuple[int, float, str, str], tuple[int, float, float]] = {}
    for h in horizons:
        h = int(h)
        for stage, dct in [
            ("test", (close_test, high_test, low_test, hlf_test, ts_test, regimes)),
            ("train", (close_train, high_train, low_train, hlf_train, ts_train, train_regimes)),
        ]:
            close, high, low, hlf, ts, reg_list = dct
            n_eff = len(close) - h - 1
            if n_eff <= 100:
                continue
            i0 = np.arange(n_eff, dtype=np.int64)
            ref = close[i0]
            ex = close[i0 + h]
            valid = np.isfinite(ref) & np.isfinite(ex)
            i0 = i0[valid]
            ref = ref[valid]
            ex = ex[valid]
            ret = (ex - ref) / pip
            reg_masks = [(name, np.asarray(mask, dtype=bool)[i0]) for name, mask in reg_list]

            for k in barrier_grid_pips:
                k = float(k)
                up_thr = ref + k * pip
                dn_thr = ref - k * pip
                inf = h + 1
                up_step = np.full(len(i0), inf, dtype=np.int32)
                dn_step = np.full(len(i0), inf, dtype=np.int32)
                any_up = np.zeros(len(i0), dtype=bool)
                any_dn = np.zeros(len(i0), dtype=bool)
                for s in range(1, h + 1):
                    idx = i0 + int(s)
                    hu = high[idx] >= up_thr
                    hd = low[idx] <= dn_thr
                    set_up = (up_step == inf) & hu
                    set_dn = (dn_step == inf) & hd
                    up_step[set_up] = int(s)
                    dn_step[set_dn] = int(s)
                    any_up |= hu
                    any_dn |= hd
                side = np.zeros(len(i0), dtype=np.int8)
                side[up_step < dn_step] = 1
                side[dn_step < up_step] = -1
                same = (up_step == dn_step) & (up_step <= h)
                if np.any(same):
                    same_idx = np.flatnonzero(same)
                    tie_idx = i0[same_idx] + up_step[same_idx].astype(np.int64)
                    tie_hlf = hlf[tie_idx]
                    side[same_idx[tie_hlf > 0]] = 1
                    side[same_idx[tie_hlf < 0]] = -1
                decided = side != 0
                both = any_up & any_dn
                touch = np.minimum(up_step, dn_step).astype(float)
                touch[~decided] = np.nan

                gross_all = side.astype(float) * ret - k
                for reg_name, reg_mask in reg_masks:
                    for fam, fam_mask in [
                        ("first_touch", decided & reg_mask),
                        ("first_touch_clean", decided & reg_mask & (~both)),
                    ]:
                        if stage == "test":
                            n = int(np.sum(fam_mask))
                            if n <= 0:
                                continue
                            gross = gross_all[fam_mask]
                            stats = _metric_from_gross(gross)
                            annual = _annualized_count(n, ts.iloc[i0[fam_mask]])
                            metric_val = (
                                stats["mean_gross_pips_test"]
                                if str(gross_metric).lower() == "mean"
                                else stats["median_gross_pips_test"]
                            )
                            rows.append(
                                {
                                    "symbol": symbol,
                                    "bar_ticks": int(bar_ticks),
                                    "horizon": int(h),
                                    "family": f"oco_{fam}",
                                    "state_id": f"oco_{fam}__{reg_name}__k{int(round(k))}",
                                    "regime_desc": f"{reg_name};barrier={k:.1f}",
                                    "train_count": -1,  # filled in later
                                    "test_count": int(n),
                                    "annualized_test_fills": float(annual),
                                    "mean_gross_pips_train": float("nan"),  # filled in later
                                    "mean_gross_pips_test": stats["mean_gross_pips_test"],
                                    "median_gross_pips_train": float("nan"),  # filled in later
                                    "median_gross_pips_test": stats["median_gross_pips_test"],
                                    "gross_std_test": stats["gross_std_test"],
                                    "hit_rate_gross_test": stats["hit_rate_gross_test"],
                                    "both_window_rate": float(np.mean(both[reg_mask]))
                                    if np.any(reg_mask)
                                    else float("nan"),
                                    "p_up_first": float(np.mean(side[fam_mask] > 0.0)),
                                    "ml_ready_target_type": "oco_expand",
                                    "selection_pass": bool(
                                        np.isfinite(metric_val)
                                        and metric_val > 0.0
                                        and annual >= float(min_annual_fills)
                                    ),
                                    "_tmp_regime": reg_name,
                                    "_tmp_family": fam,
                                    "_tmp_k": float(k),
                                }
                            )
                        else:
                            # keep train metrics keyed for joining after test pass
                            pass

                if stage == "train":
                    for reg_name, reg_mask in reg_masks:
                        for fam, fam_mask in [
                            ("first_touch", decided & reg_mask),
                            ("first_touch_clean", decided & reg_mask & (~both)),
                        ]:
                            gross = gross_all[fam_mask]
                            vals = gross[np.isfinite(gross)]
                            train_cache[(int(h), float(k), reg_name, fam)] = (
                                int(np.sum(fam_mask)),
                                float(np.mean(vals)) if len(vals) > 0 else float("nan"),
                                float(np.median(vals)) if len(vals) > 0 else float("nan"),
                            )

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    # Attach train stats from cache built during the train stage.
    train_count: list[int] = []
    mean_train: list[float] = []
    median_train: list[float] = []
    for _, r in out.iterrows():
        key = (int(r["horizon"]), float(r["_tmp_k"]), str(r["_tmp_regime"]), str(r["_tmp_family"]))
        tr = train_cache.get(key, (0, float("nan"), float("nan")))
        train_count.append(int(tr[0]))
        mean_train.append(float(tr[1]))
        median_train.append(float(tr[2]))
    out["train_count"] = np.array(train_count, dtype=int)
    out["mean_gross_pips_train"] = np.array(mean_train, dtype=float)
    out["median_gross_pips_train"] = np.array(median_train, dtype=float)
    out = out.drop(
        columns=[c for c in ["_tmp_regime", "_tmp_family", "_tmp_k"] if c in out.columns]
    )
    return out


def _save_report(
    *,
    report_out: Path,
    cfg: dict[str, Any],
    directional: pd.DataFrame,
    oco: pd.DataFrame,
    summary: pd.DataFrame,
) -> None:
    lines: list[str] = []
    lines.append("# Tick Opportunity Mining Report")
    lines.append("")
    lines.append("## Setup")
    lines.append(f"- symbol: `{cfg['symbol']}`")
    lines.append(f"- bar_ticks_grid: `{cfg['bar_ticks_grid']}`")
    lines.append(f"- horizons: `{cfg['horizons']}`")
    lines.append(f"- train_years: `{cfg['train_years']}`")
    lines.append(f"- test_year: `{cfg['test_year']}`")
    lines.append(f"- min_annual_fills: `{float(cfg['min_annual_fills']):.1f}`")
    lines.append(f"- inclusion_metric: `{cfg['gross_metric']}`")
    lines.append("")

    def _top_table(df: pd.DataFrame, n: int = 20) -> str:
        if df.empty:
            return "_empty_"
        cols = [
            "bar_ticks",
            "horizon",
            "family",
            "state_id",
            "quality_tier",
            "annualized_test_fills",
            "mean_gross_pips_test",
            "median_gross_pips_test",
            "gross_std_test",
            "hit_rate_gross_test",
            "selection_pass",
        ]
        x = df.sort_values(
            ["selection_pass", "annualized_test_fills", "mean_gross_pips_test"],
            ascending=[False, False, False],
        ).head(n)
        try:
            return x[cols].to_markdown(index=False)
        except Exception:
            return "```text\n" + x[cols].to_string(index=False) + "\n```"

    lines.append("## Directional Top")
    lines.append(_top_table(directional))
    lines.append("")
    lines.append("## OCO Top")
    lines.append(_top_table(oco))
    lines.append("")

    if not summary.empty:
        lines.append("## Selection Summary")
        try:
            lines.append(summary.to_markdown(index=False))
        except Exception:
            lines.append("```text\n" + summary.to_string(index=False) + "\n```")
        lines.append("")

    report_out.parent.mkdir(parents=True, exist_ok=True)
    report_out.write_text("\n".join(lines), encoding="utf-8")


def run(cfg: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    symbol = str(cfg["symbol"]).upper().strip()
    dataset_dir = Path(str(cfg["dataset_dir"]))
    bar_ticks_grid = _parse_ints(str(cfg["bar_ticks_grid"]))
    horizons = _parse_ints(str(cfg["horizons"]))
    train_years = set(_parse_ints(str(cfg["train_years"])))
    test_year = int(cfg["test_year"])
    min_annual_fills = float(cfg["min_annual_fills"])
    gross_metric = str(cfg["gross_metric"]).strip().lower()
    library_type = str(cfg["library_type"]).strip().lower()
    barrier_grid = _parse_floats(str(cfg["barrier_grid_pips"]))
    if gross_metric not in {"mean", "median"}:
        raise ValueError("gross_metric must be mean|median")
    if library_type not in {"separate", "directional", "oco"}:
        raise ValueError("library_type must be separate|directional|oco")

    directional_parts: list[pd.DataFrame] = []
    oco_parts: list[pd.DataFrame] = []

    for bt in bar_ticks_grid:
        path = dataset_dir / f"{symbol}_{int(bt)}tick_velocity.parquet"
        if not path.exists():
            print(f"skip {bt}: missing {path}")
            continue
        d = _prepare_frame(path, symbol=symbol, horizons=horizons)
        train = d[d["year"].isin(train_years)].copy().reset_index(drop=True)
        test = d[d["year"] == int(test_year)].copy().reset_index(drop=True)
        if train.empty or test.empty:
            print(f"skip {bt}: empty split (train/test)")
            continue
        if library_type in {"separate", "directional"}:
            directional_parts.append(
                _directional_candidates(
                    train=train,
                    test=test,
                    symbol=symbol,
                    bar_ticks=int(bt),
                    horizons=horizons,
                    min_annual_fills=min_annual_fills,
                    gross_metric=gross_metric,
                )
            )
        if library_type in {"separate", "oco"}:
            oco_parts.append(
                _oco_candidates(
                    train=train,
                    test=test,
                    symbol=symbol,
                    bar_ticks=int(bt),
                    horizons=horizons,
                    barrier_grid_pips=barrier_grid,
                    min_annual_fills=min_annual_fills,
                    gross_metric=gross_metric,
                )
            )
        print(f"ok {symbol} {bt}tick")

    directional = (
        pd.concat(directional_parts, ignore_index=True) if directional_parts else pd.DataFrame()
    )
    oco = pd.concat(oco_parts, ignore_index=True) if oco_parts else pd.DataFrame()
    if not directional.empty:
        directional = _assign_quality_tier(directional, library="directional")
    if not oco.empty:
        oco = _assign_quality_tier(oco, library="oco")

    frames = []
    if not directional.empty:
        frames.append(directional.assign(library="directional"))
    if not oco.empty:
        frames.append(oco.assign(library="oco"))
    summary_rows: list[dict[str, Any]] = []
    if frames:
        all_df = pd.concat(frames, ignore_index=True)
        for lib, g in all_df.groupby("library", sort=True):
            total = len(g)
            passed = int(g["selection_pass"].sum())
            summary_rows.append(
                {
                    "library": str(lib),
                    "rows_total": int(total),
                    "rows_pass": int(passed),
                    "pass_rate": float(passed / max(total, 1)),
                    "mean_annualized_fills_all": float(
                        pd.to_numeric(g["annualized_test_fills"], errors="coerce").mean()
                    ),
                    "mean_annualized_fills_pass": float(
                        pd.to_numeric(
                            g.loc[g["selection_pass"], "annualized_test_fills"], errors="coerce"
                        ).mean()
                    )
                    if passed > 0
                    else float("nan"),
                    "mean_gross_all": float(
                        pd.to_numeric(g["mean_gross_pips_test"], errors="coerce").mean()
                    ),
                    "mean_gross_pass": float(
                        pd.to_numeric(
                            g.loc[g["selection_pass"], "mean_gross_pips_test"], errors="coerce"
                        ).mean()
                    )
                    if passed > 0
                    else float("nan"),
                    "tier_a_rows": int((g.get("quality_tier", "") == "A").sum())
                    if "quality_tier" in g.columns
                    else 0,
                    "tier_b_rows": int((g.get("quality_tier", "") == "B").sum())
                    if "quality_tier" in g.columns
                    else 0,
                    "tier_c_rows": int((g.get("quality_tier", "") == "C").sum())
                    if "quality_tier" in g.columns
                    else 0,
                }
            )
    summary = pd.DataFrame(summary_rows)
    return directional, oco, summary


def main() -> None:
    p = argparse.ArgumentParser(
        description="Mine high-count gross-positive tick-bar opportunities for ML filtering"
    )
    p.add_argument("--config", default=None)
    p.add_argument("--symbol", default=None)
    p.add_argument("--dataset-dir", default=None)
    p.add_argument("--bar-ticks-grid", default=None)
    p.add_argument("--horizons", default=None)
    p.add_argument("--train-years", default=None)
    p.add_argument("--test-year", type=int, default=None)
    p.add_argument("--min-annual-fills", type=float, default=None)
    p.add_argument("--gross-metric", default=None)
    p.add_argument("--library-type", default=None)
    p.add_argument("--barrier-grid-pips", default=None)
    p.add_argument("--out-dir", default=None)
    p.add_argument("--report-out", default=None)
    args = p.parse_args()

    cfg = _merge_config(args)
    directional, oco, summary = run(cfg)

    out_dir = Path(str(cfg["out_dir"]))
    out_dir.mkdir(parents=True, exist_ok=True)
    symbol = str(cfg["symbol"]).upper().strip()

    d_path = out_dir / f"{symbol}_directional_candidates.csv"
    o_path = out_dir / f"{symbol}_oco_candidates.csv"
    s_path = out_dir / f"{symbol}_candidate_summary.csv"
    directional.to_csv(d_path, index=False)
    oco.to_csv(o_path, index=False)
    summary.to_csv(s_path, index=False)
    print(f"wrote: {d_path}")
    print(f"wrote: {o_path}")
    print(f"wrote: {s_path}")

    report_out = Path(str(cfg["report_out"]))
    _save_report(report_out=report_out, cfg=cfg, directional=directional, oco=oco, summary=summary)
    print(f"wrote: {report_out}")


if __name__ == "__main__":
    main()
