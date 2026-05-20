#!/usr/bin/env python3
"""Mine high-count gross-positive opportunities from tick-bar datasets.

Purpose:
- Build broad candidate libraries for downstream ML filtering.
- Keep selection criterion simple: high annualized fills + positive gross expectancy.
- Keep directional and OCO-straddle opportunity types separate.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

try:
    import yaml
except Exception:
    yaml = None  # type: ignore[assignment]

# Put the repo root on sys.path so the `scripts.*` imports below resolve when
# this file is run directly (`python scripts/run_tick_opportunity_mining.py`),
# not only when imported as a package under pytest.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.candidate_fills import (  # noqa: E402  # sys.path bootstrap above
    candidate_id,
    expand_fills,
    write_candidate_fills,
)
from scripts.mining_family import (  # noqa: E402  # sys.path bootstrap above
    FAMILY_REGISTRY,
    resolve_families,
)
from scripts.mining_random_baseline import (  # noqa: E402  # sys.path bootstrap
    random_entry_baseline,
)

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
    "baseline_seed": 12345,
    "baseline_draws": 200,
    "out_dir": "data/analysis/tick_opportunity_mining",
    "report_out": "docs/analysis/eurusd_tick_opportunity_mining_report.md",
}

CANDIDATE_SCHEMA_VERSION = "4.0"
SELECTION_PASS_BASIS = "train_only"
QUALITY_TIER_BASIS = "train_only"
EXPLICIT_BAR_SCHEMA_COLUMNS = [
    "open_bid",
    "high_bid",
    "low_bid",
    "close_bid",
    "high_ask",
    "close_ask",
    "spread",
]
LEGACY_AMBIGUOUS_BAR_COLUMNS = {"open", "high", "low", "close", "ask"}


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


def _schema_source_label(path: str | Path | None) -> str:
    if path is None:
        return "bar frame"
    return Path(path).name


def require_explicit_bar_schema(
    columns: list[str] | pd.Index | set[str],
    *,
    path: str | Path | None = None,
) -> None:
    cols = {str(c) for c in columns}
    legacy = sorted(LEGACY_AMBIGUOUS_BAR_COLUMNS & cols)
    if legacy:
        raise ValueError(
            f"{_schema_source_label(path)} legacy ambiguous bar schema unsupported: {legacy}"
        )


def load_bar_frame(
    frame: pd.DataFrame,
    *,
    path: str | Path | None = None,
    required: list[str] | None = None,
) -> pd.DataFrame:
    out = frame.copy()
    require_explicit_bar_schema(out.columns, path=path)
    need = list(required) if required is not None else list(EXPLICIT_BAR_SCHEMA_COLUMNS)
    miss = [c for c in need if c not in out.columns]
    if miss:
        raise ValueError(f"{_schema_source_label(path)} missing explicit bar schema columns: {miss}")
    return out


def read_explicit_bar_parquet(
    path: Path,
    *,
    columns: list[str] | None = None,
    required: list[str] | None = None,
) -> pd.DataFrame:
    try:
        frame = pd.read_parquet(path, columns=columns).copy() if columns is not None else pd.read_parquet(path).copy()
    except Exception:
        frame = pd.read_parquet(path).copy()
    return load_bar_frame(frame, path=path, required=required)


def _prepare_frame(path: Path, *, symbol: str, horizons: list[int]) -> pd.DataFrame:
    req = EXPLICIT_BAR_SCHEMA_COLUMNS + [
        "cost_est_pips",
        "range_pips",
        "hour_utc",
        "spread_z",
        "tick_rate_z",
        "vel_cost_units_h1",
    ]
    d = load_bar_frame(pd.read_parquet(path).copy(), path=path, required=req)
    d["close_ts"] = pd.to_datetime(d["close_ts"], utc=True, errors="coerce")
    d = d[d["close_ts"].notna()].sort_values("close_ts").reset_index(drop=True)
    if d.empty:
        return d

    pip = float(_pip_size(symbol))
    d["open_bid"] = _safe_numeric(d["open_bid"])
    d["high_bid"] = _safe_numeric(d["high_bid"])
    d["low_bid"] = _safe_numeric(d["low_bid"])
    d["close_bid"] = _safe_numeric(d["close_bid"])
    d["high_ask"] = _safe_numeric(d["high_ask"])
    d["close_ask"] = _safe_numeric(d["close_ask"])
    d["cost_est_pips"] = _safe_numeric(d["cost_est_pips"])
    d["range_pips"] = _safe_numeric(d["range_pips"])
    d["hour_utc"] = _safe_numeric(d["hour_utc"])
    d["spread_z"] = _safe_numeric(d["spread_z"]).fillna(0.0)
    d["tick_rate_z"] = _safe_numeric(d["tick_rate_z"]).fillna(0.0)
    d["vel_cost_units_h1"] = _safe_numeric(d["vel_cost_units_h1"]).fillna(0.0)

    if "vel_pips_h1" in d.columns:
        d["ret1_pips"] = _safe_numeric(d["vel_pips_h1"]).fillna(0.0)
    else:
        d["ret1_pips"] = ((d["close_bid"] - d["close_bid"].shift(1)) / pip).fillna(0.0)
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

    for col in [
        "tick_burst_score",
        "quote_revision_rate_z",
        "directional_persistence_8",
        "signed_flow_24",
        "vol_cluster_score",
    ]:
        if col in d.columns:
            d[col] = _safe_numeric(d[col]).fillna(0.0)
        else:
            d[col] = 0.0
    if "session_marker" in d.columns:
        d["session_marker"] = d["session_marker"].fillna("unknown")
    else:
        d["session_marker"] = "unknown"

    d["year"] = d["close_ts"].dt.year.astype(int)
    for h in sorted(set(int(x) for x in horizons if int(x) > 0)):
        col = f"y_fwd_pips_h{h}"
        if col not in d.columns:
            d[col] = ((d["close_bid"].shift(-h) - d["open_bid"].shift(-1)) / pip).astype(float)
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
        # Microstructure regime cuts: train-derived q70, consistent with the
        # cost/range/vel regimes, so each selects a stable ~top-30% of bars.
        # An absent column defaults to +inf so the regime is empty, never all.
        "tick_burst_q70": (
            float(train["tick_burst_score"].quantile(0.70))
            if "tick_burst_score" in train.columns
            else float("inf")
        ),
        "quote_rev_q70": (
            float(train["quote_revision_rate_z"].quantile(0.70))
            if "quote_revision_rate_z" in train.columns
            else float("inf")
        ),
        "vol_cluster_q70": (
            float(train["vol_cluster_score"].quantile(0.70))
            if "vol_cluster_score" in train.columns
            else float("inf")
        ),
    }


def _regime_masks(test: pd.DataFrame, q: dict[str, float]) -> list[tuple[str, np.ndarray]]:
    h = test["hour_utc"]
    c = test["cost_est_pips"]
    r = test["range_pips"]
    v = test["vel_abs_cost_units_h1"]
    n = len(test)
    tick_burst = (
        test["tick_burst_score"].to_numpy(dtype=float)
        if "tick_burst_score" in test.columns
        else np.zeros(n, dtype=float)
    )
    quote_rev = (
        test["quote_revision_rate_z"].to_numpy(dtype=float)
        if "quote_revision_rate_z" in test.columns
        else np.zeros(n, dtype=float)
    )
    persist = (
        test["directional_persistence_8"].to_numpy(dtype=float)
        if "directional_persistence_8" in test.columns
        else np.zeros(n, dtype=float)
    )
    vol_cluster = (
        test["vol_cluster_score"].to_numpy(dtype=float)
        if "vol_cluster_score" in test.columns
        else np.zeros(n, dtype=float)
    )
    return [
        ("all", np.ones(n, dtype=bool)),
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
        # --- microstructure regimes (causal, lagged signals) ---
        # tick_burst/quote_rev/vol_cluster use a train-derived q70 cut so each
        # selects a stable ~top-30% of bars. directional_persistence_8 keeps a
        # fixed +/-6 cut: a bounded integer count where the threshold is
        # interpretable and distribution-independent.
        ("high_intensity", (tick_burst >= q["tick_burst_q70"])),
        ("high_activity", (quote_rev >= q["quote_rev_q70"])),
        ("persistent_flow", (persist >= 6)),
        ("negative_flow", (persist <= -6)),
        ("high_vol_cluster", (vol_cluster >= q["vol_cluster_q70"])),
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



def _oco_precompute_candidates(
    frame: pd.DataFrame,
    *,
    symbol: str,
    horizon: int,
    barrier_pips: float,
) -> dict[str, np.ndarray]:
    load_bar_frame(
        frame,
        required=["close_bid", "low_bid", "high_ask", "close_ask"],
    )
    close_bid = pd.to_numeric(frame["close_bid"], errors="coerce").to_numpy(dtype=float)
    low_bid = pd.to_numeric(frame["low_bid"], errors="coerce").to_numpy(dtype=float)
    high_ask = pd.to_numeric(frame["high_ask"], errors="coerce").to_numpy(dtype=float)
    close_ask = pd.to_numeric(frame["close_ask"], errors="coerce").to_numpy(dtype=float)
    hlf = pd.to_numeric(frame["hl_first"], errors="coerce").fillna(0.0).to_numpy(dtype=float)

    h = int(horizon)
    n_eff = len(frame) - 2 * h
    if n_eff <= 100:
        return {}

    pip = float(_pip_size(symbol))
    k = float(barrier_pips)
    inf = h + 1
    i0 = np.arange(n_eff, dtype=np.int64)
    buy_ref = close_ask[i0]
    sell_ref = close_bid[i0]
    valid = np.isfinite(buy_ref) & np.isfinite(sell_ref)
    i0 = i0[valid]
    buy_ref = buy_ref[valid]
    sell_ref = sell_ref[valid]
    up_thr = buy_ref + k * pip
    dn_thr = sell_ref - k * pip
    up_step = np.full(len(i0), inf, dtype=np.int32)
    dn_step = np.full(len(i0), inf, dtype=np.int32)
    any_up = np.zeros(len(i0), dtype=bool)
    any_dn = np.zeros(len(i0), dtype=bool)
    for s in range(1, h + 1):
        idx = i0 + int(s)
        hu = high_ask[idx] >= up_thr
        hd = low_bid[idx] <= dn_thr
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
    touch_step = np.minimum(up_step, dn_step).astype(float)
    touch_step[~decided] = np.nan
    gross = np.full(len(i0), np.nan, dtype=float)
    touch_i = np.minimum(up_step, dn_step).astype(np.int64, copy=False)
    entry_i = i0 + touch_i
    exit_i = i0 + touch_i + int(h)
    ok = decided & (exit_i < len(close_bid))
    if np.any(ok):
        ok_idx = np.flatnonzero(ok)
        exit_price_use = np.where(
            side[ok_idx] == -1,
            close_ask[exit_i[ok_idx]],
            close_bid[exit_i[ok_idx]],
        )
        entry_price_use = np.where(
            side[ok_idx] == -1,
            close_bid[entry_i[ok_idx]],
            close_ask[entry_i[ok_idx]],
        )
        num_ok = np.isfinite(exit_price_use) & np.isfinite(entry_price_use)
        use = ok_idx[num_ok]
        if len(use) > 0:
            gross[use] = side[use].astype(float) * (
                (exit_price_use[num_ok] - entry_price_use[num_ok]) / pip
            )
    # Return fields are partitioned by when they become knowable:
    #   decision-time (safe to filter the candidate universe on):
    #     i0       — signal bar index
    #     decided  — a barrier was touched within the horizon (live expires
    #                un-touched scans, so the traded population matches)
    #     side     — first-touch direction (live enters the side that touches)
    #   labelling-only (require forward information — outcome/metrics ONLY,
    #   MUST NOT be used to filter the candidate universe):
    #     gross                 — enter-at-touch, hold-h-bars P&L
    #     both_touched_lookahead — both barriers touched within the horizon
    #     touch_step            — bars from signal to first touch
    return {
        "i0": i0,
        "gross": gross,
        "side": side,
        "both_touched_lookahead": both,
        "decided": decided,
        "touch_step": touch_step,
    }


def _oco_asymmetric_precompute(
    frame: pd.DataFrame,
    *,
    symbol: str,
    horizon: int,
    up_pips: float,
    down_pips: float,
) -> dict[str, np.ndarray]:
    """First-touch precompute with independently-sized up and down barriers.

    Identical algorithm to _oco_precompute_candidates; only the two barrier
    thresholds differ. With up_pips == down_pips the output is identical to
    the symmetric engine.
    """
    load_bar_frame(
        frame,
        required=["close_bid", "low_bid", "high_ask", "close_ask"],
    )
    close_bid = pd.to_numeric(frame["close_bid"], errors="coerce").to_numpy(dtype=float)
    low_bid = pd.to_numeric(frame["low_bid"], errors="coerce").to_numpy(dtype=float)
    high_ask = pd.to_numeric(frame["high_ask"], errors="coerce").to_numpy(dtype=float)
    close_ask = pd.to_numeric(frame["close_ask"], errors="coerce").to_numpy(dtype=float)
    hlf = pd.to_numeric(frame["hl_first"], errors="coerce").fillna(0.0).to_numpy(dtype=float)

    h = int(horizon)
    n_eff = len(frame) - 2 * h
    if n_eff <= 100:
        return {}

    pip = float(_pip_size(symbol))
    inf = h + 1
    i0 = np.arange(n_eff, dtype=np.int64)
    buy_ref = close_ask[i0]
    sell_ref = close_bid[i0]
    valid = np.isfinite(buy_ref) & np.isfinite(sell_ref)
    i0 = i0[valid]
    buy_ref = buy_ref[valid]
    sell_ref = sell_ref[valid]
    up_thr = buy_ref + float(up_pips) * pip
    dn_thr = sell_ref - float(down_pips) * pip
    up_step = np.full(len(i0), inf, dtype=np.int32)
    dn_step = np.full(len(i0), inf, dtype=np.int32)
    any_up = np.zeros(len(i0), dtype=bool)
    any_dn = np.zeros(len(i0), dtype=bool)
    for s in range(1, h + 1):
        idx = i0 + int(s)
        hu = high_ask[idx] >= up_thr
        hd = low_bid[idx] <= dn_thr
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
    touch_step = np.minimum(up_step, dn_step).astype(float)
    touch_step[~decided] = np.nan
    gross = np.full(len(i0), np.nan, dtype=float)
    touch_i = np.minimum(up_step, dn_step).astype(np.int64, copy=False)
    entry_i = i0 + touch_i
    exit_i = i0 + touch_i + int(h)
    ok = decided & (exit_i < len(close_bid))
    if np.any(ok):
        ok_idx = np.flatnonzero(ok)
        exit_price_use = np.where(
            side[ok_idx] == -1,
            close_ask[exit_i[ok_idx]],
            close_bid[exit_i[ok_idx]],
        )
        entry_price_use = np.where(
            side[ok_idx] == -1,
            close_bid[entry_i[ok_idx]],
            close_ask[entry_i[ok_idx]],
        )
        num_ok = np.isfinite(exit_price_use) & np.isfinite(entry_price_use)
        use = ok_idx[num_ok]
        if len(use) > 0:
            gross[use] = side[use].astype(float) * (
                (exit_price_use[num_ok] - entry_price_use[num_ok]) / pip
            )
    return {
        "i0": i0,
        "gross": gross,
        "side": side,
        "both_touched_lookahead": both,
        "decided": decided,
        "touch_step": touch_step,
    }


def _run_length(frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Per-bar consecutive same-sign run of ret1_pips.

    Returns (run_len, run_sign): run_len[i] counts consecutive preceding bars
    (including i) with the same non-zero sign of ret1_pips; run_sign[i] is
    that sign (+1/-1, or 0 when ret1_pips is zero, which also resets the run).
    """
    ret = pd.to_numeric(frame["ret1_pips"], errors="coerce").to_numpy(dtype=float)
    sign = np.sign(np.nan_to_num(ret)).astype(np.int8)
    n = len(sign)
    if n == 0:
        return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int8)
    change = np.empty(n, dtype=bool)
    change[0] = True
    change[1:] = sign[1:] != sign[:-1]
    starts = np.where(change, np.arange(n), 0)
    last_start = np.maximum.accumulate(starts)
    run_len = (np.arange(n) - last_start + 1).astype(np.int64)
    run_len[sign == 0] = 0
    return run_len, sign


def _double_touch_precompute(
    frame: pd.DataFrame,
    *,
    symbol: str,
    sweep_dir: str,
    a_pips: float,
    b_pips: float,
    window_A: int,
    window_B: int,
    h2: int,
) -> dict[str, np.ndarray]:
    """Anchored two-stage sweep engine.

    For each regime entry bar i0: place an A-barrier a_pips in the sweep_dir
    direction from i0's signal close; find the first touch within window_A
    bars (tA). Then place a B-barrier b_pips in the OPPOSITE direction from
    the A-barrier price; find the first touch within window_B bars of tA
    (tB). Continuation gross is the signed h2-bar return from tB in the
    B-direction. Look-ahead-free: entry conditioning is i0 only; tA, tB and
    the continuation window are all strictly forward of i0.
    """
    load_bar_frame(
        frame,
        required=["close_bid", "low_bid", "high_ask", "close_ask"],
    )
    close_bid = pd.to_numeric(frame["close_bid"], errors="coerce").to_numpy(dtype=float)
    low_bid = pd.to_numeric(frame["low_bid"], errors="coerce").to_numpy(dtype=float)
    high_ask = pd.to_numeric(frame["high_ask"], errors="coerce").to_numpy(dtype=float)
    close_ask = pd.to_numeric(frame["close_ask"], errors="coerce").to_numpy(dtype=float)

    wA, wB, h = int(window_A), int(window_B), int(h2)
    n = len(frame)
    n_eff = n - (wA + wB + h)
    if n_eff <= 100:
        return {}

    pip = float(_pip_size(symbol))
    up = str(sweep_dir).strip().lower() == "up"

    i0 = np.arange(n_eff, dtype=np.int64)
    sig = close_ask[i0] if up else close_bid[i0]
    valid = np.isfinite(sig)
    i0 = i0[valid]
    sig = sig[valid]

    # Stage 1: A-barrier in the sweep direction.
    a_price = sig + a_pips * pip if up else sig - a_pips * pip
    inf_a = wA + 1
    a_step = np.full(len(i0), inf_a, dtype=np.int32)
    for s in range(1, wA + 1):
        idx = i0 + int(s)
        hit = high_ask[idx] >= a_price if up else low_bid[idx] <= a_price
        first = (a_step == inf_a) & hit
        a_step[first] = int(s)
    a_touched = a_step <= wA
    tA = i0 + a_step.astype(np.int64)

    # Stage 2: B-barrier b_pips OPPOSITE the A-barrier price.
    b_price = a_price - b_pips * pip if up else a_price + b_pips * pip
    inf_b = wB + 1
    b_step = np.full(len(i0), inf_b, dtype=np.int32)
    for s in range(1, wB + 1):
        idx = tA + int(s)
        # idx stays in-bounds: tA <= i0+wA+1 and i0 <= n_eff-1, so
        # idx <= n_eff-1 + wA + 1 + wB = n - h <= n - 1.
        hit = low_bid[idx] <= b_price if up else high_ask[idx] >= b_price
        first = a_touched & (b_step == inf_b) & hit
        b_step[first] = int(s)
    decided = a_touched & (b_step <= wB)
    tB = tA + b_step.astype(np.int64)

    # Continuation: signed h2-bar return from tB in the B-direction.
    exit_i = tB + h
    gross = np.full(len(i0), np.nan, dtype=float)
    ok = decided & (exit_i < n)
    if np.any(ok):
        ok_idx = np.flatnonzero(ok)
        if up:
            # B is down -> continuation bet is short.
            entry_price = close_bid[tB[ok_idx]]
            exit_price = close_ask[exit_i[ok_idx]]
            g = (entry_price - exit_price) / pip
        else:
            # B is up -> continuation bet is long.
            entry_price = close_ask[tB[ok_idx]]
            exit_price = close_bid[exit_i[ok_idx]]
            g = (exit_price - entry_price) / pip
        num_ok = np.isfinite(entry_price) & np.isfinite(exit_price)
        gross[ok_idx[num_ok]] = g[num_ok]

    return {
        "i0": i0,
        "decided": decided,
        "gross": gross,
        "t_a_step": np.where(a_touched, a_step, -1).astype(np.int64),
        "t_b_step": np.where(decided, b_step, -1).astype(np.int64),
    }


def _pullback_precompute(
    frame: pd.DataFrame,
    *,
    symbol: str,
    impulse_dir: str,
    m_pips: float,
    r_frac: float,
    window_I: int,
    window_P: int,
    window_R: int,
    h: int,
) -> dict[str, np.ndarray]:
    """Anchored four-stage pullback-continuation engine.

    For each regime entry bar i0: place an impulse barrier m_pips in the
    impulse_dir direction from i0's signal close; find the first touch within
    window_I bars (tI). The impulse extreme pI is the barrier price itself.
    Place a pullback barrier r_frac*m_pips from pI in the OPPOSITE direction;
    find the first touch within window_P bars of tI (tP). Place a resumption
    barrier back at pI; find the first touch within window_R bars of tP (tR).
    Continuation gross is the signed h-bar return from tR in the impulse
    direction. Look-ahead-free: entry conditioning is i0 only; tI, tP, tR and
    the continuation window are all strictly forward of i0.
    """
    load_bar_frame(
        frame,
        required=["close_bid", "low_bid", "high_ask", "close_ask"],
    )
    close_bid = pd.to_numeric(frame["close_bid"], errors="coerce").to_numpy(dtype=float)
    low_bid = pd.to_numeric(frame["low_bid"], errors="coerce").to_numpy(dtype=float)
    high_ask = pd.to_numeric(frame["high_ask"], errors="coerce").to_numpy(dtype=float)
    close_ask = pd.to_numeric(frame["close_ask"], errors="coerce").to_numpy(dtype=float)

    wI, wP, wR, hh = int(window_I), int(window_P), int(window_R), int(h)
    n = len(frame)
    # i0 upper bound reserves room for the worst-case forward index across all
    # three scans plus the continuation horizon. The +2 covers the inf-padded
    # steps of i0 bars that never complete an earlier stage (tI <= i0+wI+1,
    # tP <= tI+wP+1), so every index read below stays in-bounds unconditionally.
    n_eff = n - (wI + wP + wR + hh + 2)
    if n_eff <= 100:
        return {}

    pip = float(_pip_size(symbol))
    up = str(impulse_dir).strip().lower() == "up"

    i0 = np.arange(n_eff, dtype=np.int64)
    sig = close_ask[i0] if up else close_bid[i0]
    valid = np.isfinite(sig)
    i0 = i0[valid]
    sig = sig[valid]

    # Stage 1: impulse barrier in the impulse direction.
    i_price = sig + m_pips * pip if up else sig - m_pips * pip
    inf_i = wI + 1
    i_step = np.full(len(i0), inf_i, dtype=np.int32)
    for s in range(1, wI + 1):
        idx = i0 + int(s)
        hit = high_ask[idx] >= i_price if up else low_bid[idx] <= i_price
        first = (i_step == inf_i) & hit
        i_step[first] = int(s)
    i_touched = i_step <= wI
    tI = i0 + i_step.astype(np.int64)

    # Stage 2: pullback barrier r_frac*m_pips OPPOSITE the impulse extreme pI.
    # Note: p_price is anchored to the impulse barrier (ask-space for up), but
    # touched via the opposite-side quote (low_bid for up). This ~1-spread
    # offset is intrinsic to measuring a retracement on the opposite side.
    p_price = (
        i_price - r_frac * m_pips * pip if up else i_price + r_frac * m_pips * pip
    )
    inf_p = wP + 1
    p_step = np.full(len(i0), inf_p, dtype=np.int32)
    for s in range(1, wP + 1):
        idx = tI + int(s)
        hit = low_bid[idx] <= p_price if up else high_ask[idx] >= p_price
        first = i_touched & (p_step == inf_p) & hit
        p_step[first] = int(s)
    p_touched = i_touched & (p_step <= wP)
    tP = tI + p_step.astype(np.int64)

    # Stage 3: resumption barrier back at the impulse extreme pI.
    inf_r = wR + 1
    r_step = np.full(len(i0), inf_r, dtype=np.int32)
    for s in range(1, wR + 1):
        idx = tP + int(s)
        hit = high_ask[idx] >= i_price if up else low_bid[idx] <= i_price
        first = p_touched & (r_step == inf_r) & hit
        r_step[first] = int(s)
    decided = p_touched & (r_step <= wR)
    tR = tP + r_step.astype(np.int64)

    # Continuation: signed h-bar return from tR in the impulse direction.
    exit_i = tR + hh
    gross = np.full(len(i0), np.nan, dtype=float)
    ok = decided & (exit_i < n)
    if np.any(ok):
        ok_idx = np.flatnonzero(ok)
        if up:
            # Up-impulse -> continuation bet is long.
            entry_price = close_ask[tR[ok_idx]]
            exit_price = close_bid[exit_i[ok_idx]]
            g = (exit_price - entry_price) / pip
        else:
            # Down-impulse -> continuation bet is short.
            entry_price = close_bid[tR[ok_idx]]
            exit_price = close_ask[exit_i[ok_idx]]
            g = (entry_price - exit_price) / pip
        num_ok = np.isfinite(entry_price) & np.isfinite(exit_price)
        gross[ok_idx[num_ok]] = g[num_ok]

    return {
        "i0": i0,
        "decided": decided,
        "gross": gross,
        "t_i_step": np.where(i_touched, i_step, -1).astype(np.int64),
        "t_p_step": np.where(p_touched, p_step, -1).astype(np.int64),
        "t_r_step": np.where(decided, r_step, -1).astype(np.int64),
    }


def _assign_quality_tier(df: pd.DataFrame, *, library: str) -> pd.DataFrame:
    """Assign quality tiers (A/B/C/D) from look-ahead-free train metrics only.

    This avoids test-metric leakage into quality_score, which downstream
    consumers (e.g. build_tick_opportunity_ml_dataset) use for ranking.
    """
    if df.empty:
        return df
    out = df.copy()
    mean_g = pd.to_numeric(out["mean_gross_pips_train"], errors="coerce").fillna(-np.inf)
    med_g = pd.to_numeric(out["median_gross_pips_train"], errors="coerce").fillna(-np.inf)
    tc = pd.to_numeric(out["train_count"], errors="coerce").fillna(0.0)
    sel = out["selection_pass"].astype(bool)

    if str(library).lower() == "directional":
        a = (mean_g >= 0.25) & (med_g >= 0.05) & (tc >= 40000)
        b = (mean_g >= 0.10) & (med_g >= 0.0) & (tc >= 20000)
    else:
        a = (mean_g >= 1.0) & (med_g >= 0.3) & (tc >= 40000)
        b = (mean_g >= 0.40) & (med_g >= 0.1) & (tc >= 20000)
    tier = np.where(a, "A", np.where(b, "B", np.where(sel, "C", "D")))
    out["quality_tier"] = tier
    out["quality_score"] = np.where(
        tier == "A",
        3,
        np.where(tier == "B", 2, np.where(tier == "C", 1, 0)),
    ).astype(int)
    return out


def _stamp_candidate_contract(df: pd.DataFrame) -> pd.DataFrame:
    """Stamp causal-selection contract metadata for downstream strict validation."""
    if df.empty:
        return df
    out = df.copy()
    out["candidate_schema_version"] = CANDIDATE_SCHEMA_VERSION
    out["selection_pass_basis"] = SELECTION_PASS_BASIS
    out["quality_tier_basis"] = QUALITY_TIER_BASIS
    return out


def _build_summary(
    directional: pd.DataFrame, oco: pd.DataFrame, no_touch: pd.DataFrame
) -> pd.DataFrame:
    frames = []
    if not directional.empty:
        frames.append(directional.assign(library="directional"))
    if not oco.empty:
        frames.append(oco.assign(library="oco"))
    if not no_touch.empty:
        frames.append(no_touch.assign(library="no_touch"))
    summary_rows: list[dict[str, Any]] = []
    if frames:
        all_df = pd.concat(frames, ignore_index=True)
        for lib, g in all_df.groupby("library", sort=True):
            total = len(g)
            passed = int(g["selection_pass"].sum()) if "selection_pass" in g else 0
            summary_rows.append({
                "library": str(lib),
                "rows_total": int(total),
                "rows_pass": int(passed),
                "pass_rate": float(passed / max(total, 1)),
                "mean_gross_all": float(
                    pd.to_numeric(g["mean_gross_pips_test"], errors="coerce").mean()),
                "mean_baseline_z": float(
                    pd.to_numeric(g["random_baseline_z"], errors="coerce").mean()),
            })
    return pd.DataFrame(summary_rows)


def _attach_directional_side_columns(
    frame: pd.DataFrame, *, horizons: list[int], q: dict[str, float] | None = None
) -> pd.DataFrame:
    """Materialise per-bar `_dir_side_h{h}` columns used by DirectionalFamily.

    The side is the sign convention from _directional_family_states applied
    per bar: +1 when the regime's directional bias is long, -1 short, 0 when
    undefined. Computed here once so the family hooks stay pure index math.

    Note: overlapping family states are merged with first-wins semantics
    (np.where(fm & (side == 0), fs, side)). The resulting `state_id` is
    generic (`directional__{regime}__h{h}`) rather than family-specific
    (e.g. `shock_follow__all__h1`), collapsing all directional states into
    a single per-regime candidate row.
    """
    out = frame.copy()
    if q is None:
        q = _quantiles(frame)
    for h in horizons:
        # _directional_family_states is horizon-agnostic; the side array is
        # identical across horizons, but each family param_grid isolates by h.
        side = np.zeros(len(frame), dtype=np.int8)
        for _fam, fam_mask, fam_side in _directional_family_states(frame, q):
            fm = np.asarray(fam_mask, dtype=bool)
            fs = np.asarray(fam_side, dtype=np.int8)
            side = np.where(fm & (side == 0), fs, side).astype(np.int8)
        out[f"_dir_side_h{h}"] = side
    return out


def _save_report(
    *,
    report_out: Path,
    cfg: dict[str, Any],
    directional: pd.DataFrame,
    oco: pd.DataFrame,
    no_touch: pd.DataFrame,
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
    lines.append("## No-Touch Top")
    lines.append(_top_table(no_touch))
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


def _mine_frame_pair(
    *,
    train: pd.DataFrame,
    test: pd.DataFrame,
    symbol: str,
    bar_ticks: int,
    cfg: dict[str, Any],
    family_names: list[str],
    baseline_seed: int,
    baseline_draws: int,
    min_annual_fills: float,
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    """Mine candidate rows for one (train, test) frame pair across the given
    families. Returns per-family lists of candidate row dicts, before quality
    tiering and contract stamping. Used by run() per bar-ticks velocity file
    and directly by the microstructure-regime contract tests."""
    horizons = _parse_ints(str(cfg["horizons"]))
    per_family_rows: dict[str, list[dict[str, Any]]] = {n: [] for n in family_names}
    fill_rows: list[dict[str, Any]] = []
    train_q = _quantiles(train)
    train = _attach_directional_side_columns(train, horizons=horizons, q=train_q)
    test = _attach_directional_side_columns(test, horizons=horizons, q=train_q)
    train_regimes = _regime_masks(train, train_q)
    train_regime_map = {name: mask for name, mask in train_regimes}
    for fam_name in family_names:
        family = FAMILY_REGISTRY[fam_name]
        rng = np.random.default_rng(baseline_seed)
        test_regimes = _regime_masks(test, train_q)
        for params in family.param_grid(cfg):
            params = {**params, "symbol": symbol, "bar_ticks": int(bar_ticks)}

            # OCO-specific precompute for both_window_rate / p_up_first
            oco_prep_test: dict[str, Any] | None = None
            oco_prep_train: dict[str, Any] | None = None
            if fam_name == "oco_first_touch":
                oco_prep_test = _oco_precompute_candidates(
                    test, symbol=symbol,
                    horizon=int(params.get("horizon", 0)),
                    barrier_pips=float(params.get("barrier_pips", 0.0)),
                )
                oco_prep_train = _oco_precompute_candidates(
                    train, symbol=symbol,
                    horizon=int(params.get("horizon", 0)),
                    barrier_pips=float(params.get("barrier_pips", 0.0)),
                )

            for regime_name, regime_mask in test_regimes:
                entries = family.entry_indices(test, np.asarray(regime_mask, bool), params)
                n = int(len(entries))
                if n <= 0:
                    continue
                gross_raw = np.asarray(family.measure_gross(test, entries, params), float)
                gross = gross_raw[np.isfinite(gross_raw)]
                if gross.size == 0:
                    continue
                cand_ev = float(np.mean(gross))

                # Train metrics
                train_entries = family.entry_indices(
                    train, np.asarray(train_regime_map[regime_name], bool), params
                )
                train_n = int(len(train_entries))
                train_gross_raw = np.asarray(family.measure_gross(train, train_entries, params), float)
                train_gross = train_gross_raw[np.isfinite(train_gross_raw)]
                mean_train = float(np.mean(train_gross)) if train_gross.size > 0 else float("nan")
                median_train = float(np.median(train_gross)) if train_gross.size > 0 else float("nan")

                # Microstructure stats (train only)
                if train_n > 0:
                    if "tick_burst_score" in train.columns:
                        tick_burst_vals = train["tick_burst_score"].to_numpy(dtype=float)[train_entries]
                        mean_tick_burst = float(np.mean(tick_burst_vals))
                    else:
                        mean_tick_burst = float("nan")
                    if "directional_persistence_8" in train.columns:
                        persist_vals = train["directional_persistence_8"].to_numpy(dtype=float)[train_entries]
                        mean_flow_persist = float(np.mean(persist_vals))
                    else:
                        mean_flow_persist = float("nan")
                    if "vol_cluster_score" in train.columns:
                        vol_cluster_vals = train["vol_cluster_score"].to_numpy(dtype=float)[train_entries]
                        mean_vol_cluster = float(np.mean(vol_cluster_vals))
                    else:
                        mean_vol_cluster = float("nan")
                    if "session_marker" in train.columns:
                        session_vals = train["session_marker"].iloc[train_entries]
                        session_coverage = session_vals.value_counts(normalize=True).to_dict()
                    else:
                        session_coverage = {}
                else:
                    mean_tick_burst = float("nan")
                    mean_flow_persist = float("nan")
                    mean_vol_cluster = float("nan")
                    session_coverage = {}

                base = random_entry_baseline(
                    family, test, params,
                    n_entries=n, n_draws=baseline_draws, rng=rng,
                    candidate_gross_ev=cand_ev,
                )

                # OCO-specific fields
                both_window_rate = float("nan")
                both_window_rate_train = float("nan")
                p_up_first = float("nan")
                if fam_name == "oco_first_touch":
                    if oco_prep_test:
                        i0 = np.asarray(oco_prep_test["i0"], dtype=np.int64)
                        decided = np.asarray(oco_prep_test["decided"], dtype=bool)
                        both = np.asarray(oco_prep_test["both_touched_lookahead"], dtype=bool)
                        side = np.asarray(oco_prep_test["side"], dtype=np.int8)
                        reg = np.asarray(regime_mask, dtype=bool)[i0]
                        if np.any(reg):
                            both_window_rate = float(np.mean(both[reg]))
                            fam_mask = decided & reg
                            if np.any(fam_mask):
                                p_up_first = float(np.mean(side[fam_mask] > 0.0))
                    if oco_prep_train:
                        i0t = np.asarray(oco_prep_train["i0"], dtype=np.int64)
                        botht = np.asarray(oco_prep_train["both_touched_lookahead"], dtype=bool)
                        regt = np.asarray(train_regime_map[regime_name], dtype=bool)[i0t]
                        decidedt = np.asarray(oco_prep_train["decided"], dtype=bool)
                        if np.any(regt & decidedt):
                            both_window_rate_train = float(np.mean(botht[regt]))

                # selection_pass
                if fam_name in (
                    "directional", "double_touch", "pullback", "no_touch"
                ):
                    train_annual = (
                        _annualized_count(
                            train_n,
                            pd.to_datetime(train["close_ts"], utc=True, errors="coerce").iloc[train_entries],
                        )
                        if train_n > 0
                        else 0.0
                    )
                    selection_pass = bool(
                        np.isfinite(mean_train)
                        and mean_train > 0.0
                        and train_annual >= float(min_annual_fills)
                    )
                else:
                    selection_pass = bool(
                        np.isfinite(mean_train)
                        and mean_train > 0.0
                        and train_n >= 500
                    )

                library_type = str(cfg.get("library_type", "separate"))
                cid = candidate_id(
                    symbol, library_type, fam_name, int(bar_ticks),
                    int(params.get("horizon", 0)), regime_name, params,
                )
                near_miss = bool(
                    np.isfinite(mean_train)
                    and mean_train > 0.0
                    and not selection_pass
                )
                if selection_pass or near_miss:
                    identity = {
                        "candidate_id": cid,
                        "symbol": symbol,
                        "family": fam_name,
                        "library_type": library_type,
                        "bar_ticks": int(bar_ticks),
                        "horizon": int(params.get("horizon", 0)),
                        "regime": regime_name,
                        "selection_pass": bool(selection_pass),
                        "near_miss": near_miss,
                    }
                    fill_rows.extend(expand_fills(
                        test, entries, gross_raw,
                        split="test", identity=identity,
                    ))
                    fill_rows.extend(expand_fills(
                        train, train_entries, train_gross_raw,
                        split="train", identity=identity,
                    ))

                row = {
                    "candidate_id": cid,
                    "symbol": symbol,
                    "bar_ticks": int(bar_ticks),
                    "horizon": int(params.get("horizon", 0)),
                    "test_count": n,
                    "mean_gross_pips_test": cand_ev,
                    "median_gross_pips_test": float(np.median(gross)),
                    "gross_std_test": float(np.std(gross, ddof=0)),
                    "hit_rate_gross_test": float(np.mean(gross > 0.0)),
                    "annualized_test_fills": _annualized_count(
                        n, pd.to_datetime(test["close_ts"], utc=True,
                                          errors="coerce").iloc[entries]),
                    "train_count": train_n,
                    "mean_gross_pips_train": mean_train,
                    "median_gross_pips_train": median_train,
                    "both_window_rate": both_window_rate,
                    "both_window_rate_train": both_window_rate_train,
                    "p_up_first": p_up_first,
                    "mean_tick_burst_train": mean_tick_burst,
                    "mean_flow_persistence_train": mean_flow_persist,
                    "mean_vol_cluster_train": mean_vol_cluster,
                    "session_coverage": session_coverage,
                    "selection_pass": selection_pass,
                    **family.candidate_metadata(regime_name, params),
                    **base,
                }
                per_family_rows[fam_name].append(row)
    return per_family_rows, fill_rows


def run(
    cfg: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, list[dict[str, Any]]]:
    symbol = str(cfg["symbol"]).upper().strip()
    dataset_dir = Path(str(cfg["dataset_dir"]))
    bar_ticks_grid = _parse_ints(str(cfg["bar_ticks_grid"]))
    horizons = _parse_ints(str(cfg["horizons"]))
    train_years = set(_parse_ints(str(cfg["train_years"])))
    test_year = int(cfg["test_year"])
    min_annual_fills = float(cfg["min_annual_fills"])
    gross_metric = str(cfg["gross_metric"]).strip().lower()
    library_type = str(cfg["library_type"]).strip().lower()
    if gross_metric not in {"mean", "median"}:
        raise ValueError("gross_metric must be mean|median")
    if library_type not in {
        "all", "separate", "directional", "directional_run",
        "oco", "oco_asymmetric",
        "double_touch", "pullback", "no_touch",
    }:
        raise ValueError(
            "library_type must be "
            "all|separate|directional|directional_run|"
            "oco|oco_asymmetric|"
            "double_touch|pullback|no_touch"
        )

    family_names = resolve_families(library_type)
    baseline_seed = int(cfg.get("baseline_seed", 12345))
    baseline_draws = int(cfg.get("baseline_draws", 200))

    per_family_rows: dict[str, list[dict[str, Any]]] = {n: [] for n in family_names}
    all_fills: list[dict[str, Any]] = []

    if not dataset_dir.exists():
        raise FileNotFoundError(
            f"mining input directory does not exist: {dataset_dir}\n"
            "Stage 0 data has not been built. Run "
            "`make rebuild-all MONTHS=...` to build the velocity dataset "
            "before mining."
        )

    files_found = 0
    for bt in bar_ticks_grid:
        path = dataset_dir / f"{symbol}_{int(bt)}tick_velocity.parquet"
        if not path.exists():
            print(f"skip {bt}: missing {path}")
            continue
        files_found += 1
        d = _prepare_frame(path, symbol=symbol, horizons=horizons)
        train = d[d["year"].isin(train_years)].copy().reset_index(drop=True)
        test = d[d["year"] == int(test_year)].copy().reset_index(drop=True)
        if train.empty or test.empty:
            print(f"skip {bt}: empty split (train/test)")
            continue

        pair_rows, pair_fills = _mine_frame_pair(
            train=train, test=test, symbol=symbol, bar_ticks=int(bt),
            cfg=cfg, family_names=family_names,
            baseline_seed=baseline_seed, baseline_draws=baseline_draws,
            min_annual_fills=min_annual_fills,
        )
        for fam_name, fam_rows in pair_rows.items():
            per_family_rows[fam_name].extend(fam_rows)
        all_fills.extend(pair_fills)
        print(f"ok {symbol} {bt}tick")

    if files_found == 0:
        raise FileNotFoundError(
            f"no velocity files found for {symbol} in {dataset_dir} "
            f"(expected {symbol}_<ticks>tick_velocity.parquet). "
            "Run `make rebuild-all MONTHS=...` to build Stage 0 data."
        )

    directional = pd.DataFrame(
        per_family_rows.get("directional", [])
        + per_family_rows.get("directional_run", [])
        + per_family_rows.get("double_touch", [])
        + per_family_rows.get("pullback", [])
    )
    oco = pd.DataFrame(per_family_rows.get("oco_first_touch", []))
    oco_asymmetric = pd.DataFrame(per_family_rows.get("oco_asymmetric", []))
    no_touch = pd.DataFrame(per_family_rows.get("no_touch", []))
    if not directional.empty:
        directional = _assign_quality_tier(directional, library="directional")
        directional = _stamp_candidate_contract(directional)
    if not oco.empty:
        oco = _assign_quality_tier(oco, library="oco")
        oco = _stamp_candidate_contract(oco)
    if not oco_asymmetric.empty:
        oco_asymmetric = _assign_quality_tier(oco_asymmetric, library="oco")
        oco_asymmetric = _stamp_candidate_contract(oco_asymmetric)
    if not no_touch.empty:
        no_touch = _assign_quality_tier(no_touch, library="no_touch")
        no_touch = _stamp_candidate_contract(no_touch)
    summary = _build_summary(directional, oco, no_touch)
    return directional, oco, oco_asymmetric, no_touch, summary, all_fills


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
    p.add_argument("--baseline-seed", type=int, default=None)
    p.add_argument("--baseline-draws", type=int, default=None)
    p.add_argument("--out-dir", default=None)
    p.add_argument("--report-out", default=None)
    args = p.parse_args()

    cfg = _merge_config(args)
    directional, oco, oco_asymmetric, no_touch, summary, fills = run(cfg)

    out_dir = Path(str(cfg["out_dir"]))
    out_dir.mkdir(parents=True, exist_ok=True)
    symbol = str(cfg["symbol"]).upper().strip()

    d_path = out_dir / f"{symbol}_directional_candidates.csv"
    o_path = out_dir / f"{symbol}_oco_candidates.csv"
    oa_path = out_dir / f"{symbol}_oco_asymmetric_candidates.csv"
    nt_path = out_dir / f"{symbol}_no_touch_candidates.csv"
    s_path = out_dir / f"{symbol}_candidate_summary.csv"
    directional.to_csv(d_path, index=False)
    oco.to_csv(o_path, index=False)
    oco_asymmetric.to_csv(oa_path, index=False)
    no_touch.to_csv(nt_path, index=False)
    summary.to_csv(s_path, index=False)
    fills_path = write_candidate_fills(fills, out_dir, symbol)
    print(f"wrote: {d_path}")
    print(f"wrote: {o_path}")
    print(f"wrote: {oa_path}")
    print(f"wrote: {nt_path}")
    print(f"wrote: {s_path}")
    print(f"wrote: {fills_path}")

    report_out = Path(str(cfg["report_out"]))
    _save_report(
        report_out=report_out, cfg=cfg, directional=directional,
        oco=oco, no_touch=no_touch, summary=summary,
    )
    print(f"wrote: {report_out}")


if __name__ == "__main__":
    main()
