#!/usr/bin/env python3
"""Tick-exact contract check for reduced OCO shortlist predictions."""

from __future__ import annotations

import argparse
import re
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
    "pred_path": "data/analysis/tick_opportunity_mining/wfo_m3to1_oco_fullcap/EURUSD_oco_monthly_predictions.parquet",
    "shortlist_state_csv": "data/analysis/tick_opportunity_mining/reduced_core/EURUSD_oco_reduced_states.csv",
    "locked_quantile": 0.9,
    "selection_mode": "auto",  # auto|exec_flag|monthly_quantile
    "family_required": "oco_first_touch_clean",
    "oco_hold_mode": "from_touch",  # from_touch|from_start
    "oco_include_no_touch": True,
    "sample_rows_per_combo": 0,
    "abs_tol_pips": 1e-9,
    "min_exact_match_rate": 0.999,
    "min_pos_label_match_rate": 0.999,
    "out_summary_csv": "data/analysis/tick_opportunity_mining/reduced_core/EURUSD_oco_tick_exact_summary.csv",
    "out_monthly_csv": "data/analysis/tick_opportunity_mining/reduced_core/EURUSD_oco_tick_exact_monthly.csv",
    "out_state_csv": "data/analysis/tick_opportunity_mining/reduced_core/EURUSD_oco_tick_exact_state.csv",
    "report_out": "docs/analysis/eurusd_oco_tick_exact_shortlist_report.md",
}


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
    if str(getattr(args, "config", "")).strip():
        cfg.update(_load_yaml(Path(str(args.config))))
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


def _parse_barrier_from_state(state_id: str) -> float:
    m = re.search(r"k([0-9]+(?:\.[0-9]+)?)$", str(state_id))
    if not m:
        raise ValueError(f"cannot parse barrier from state_id={state_id!r}")
    return float(m.group(1))


def _parse_uid_cols(uids: pd.Series) -> pd.DataFrame:
    parts = uids.astype(str).str.split("|", n=4, expand=True)
    if parts.shape[1] != 5:
        raise ValueError("candidate_uid split failed")
    out = pd.DataFrame(index=uids.index)
    out["library"] = parts[0].astype(str)
    out["symbol"] = parts[1].astype(str).str.upper()
    out["bar_ticks"] = pd.to_numeric(parts[2], errors="coerce").astype("Int64")
    out["horizon"] = pd.to_numeric(
        parts[3].astype(str).str.replace(r"^[hH]", "", regex=True), errors="coerce"
    ).astype("Int64")
    out["state_id"] = parts[4].astype(str)
    return out


def _normalize_shortlist_states(states: pd.DataFrame, *, symbol: str) -> pd.DataFrame:
    x = states.copy()
    if "symbol" in x.columns:
        x = x[x["symbol"].astype(str).str.upper() == str(symbol).upper()].copy()
    if "test_month" in x.columns:
        months = x["test_month"].dropna().astype(str).str.strip()
        months = months[(months != "") & (months.str.lower() != "nan")]
        if not months.empty:
            latest_month = sorted(months.unique().tolist())[-1]
            x = x[x["test_month"].astype(str).str.strip() == latest_month].copy()
    return x


def _default_shortlist_candidates(symbol: str) -> list[Path]:
    s = str(symbol).upper().strip()
    sl = s.lower()
    return [
        Path(
            f"data/analysis/tick_opportunity_mining/reduced_core_rolling/{s}_oco_reduced_state_schedule.csv"
        ),
        Path(f"configs/research/governance/oco/{sl}_oco_allowed_states.csv"),
        Path(f"data/analysis/tick_opportunity_mining/reduced_core/{s}_oco_reduced_states.csv"),
    ]


def _resolve_shortlist_state_csv(raw_path: str | None, *, symbol: str) -> Path:
    raw = str(raw_path or "").strip()
    p = Path(raw) if raw else None
    default_p = Path(DEFAULTS["shortlist_state_csv"])
    if p is not None and p.exists() and p != default_p:
        return p
    for cand in _default_shortlist_candidates(symbol):
        if cand.exists():
            return cand
    if p is not None:
        return p
    return _default_shortlist_candidates(symbol)[0]


def _select_month_q(d: pd.DataFrame, q: float) -> pd.DataFrame:
    out: list[pd.DataFrame] = []
    for _m, g in d.groupby("test_month", sort=True):
        thr = float(np.quantile(g["pred_prob"].to_numpy(dtype=float), float(q)))
        x = g[g["pred_prob"] >= thr].copy()
        x["threshold"] = float(thr)
        out.append(x)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def _select_events(d: pd.DataFrame, *, q: float, mode: str) -> pd.DataFrame:
    m = str(mode).strip().lower()
    if m not in {"auto", "exec_flag", "monthly_quantile"}:
        raise ValueError("selection_mode must be auto|exec_flag|monthly_quantile")
    if m in {"auto", "exec_flag"} and "selected_exec" in d.columns:
        x = d[pd.to_numeric(d["selected_exec"], errors="coerce").fillna(0).astype(int) == 1].copy()
        if "threshold_exec" in d.columns:
            x["threshold"] = pd.to_numeric(x["threshold_exec"], errors="coerce")
        if m == "exec_flag" or (m == "auto" and not x.empty):
            return x
    return _select_month_q(d, q=q)


def _recompute_first_touch(
    *,
    close: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    hlf: np.ndarray,
    idx: np.ndarray,
    horizon: int,
    barrier_pips: float,
    pip: float,
    hold_mode: str,
    include_no_touch: bool,
) -> dict[str, np.ndarray]:
    n = len(idx)
    expected = np.full(n, np.nan, dtype=float)
    side = np.zeros(n, dtype=np.int8)
    decided = np.zeros(n, dtype=bool)
    both = np.zeros(n, dtype=bool)
    clean = np.zeros(n, dtype=bool)
    map_ok = np.zeros(n, dtype=bool)

    h = int(horizon)
    k = float(barrier_pips)
    mode = str(hold_mode).strip().lower()
    if mode not in {"from_touch", "from_start"}:
        raise ValueError("oco_hold_mode must be from_touch|from_start")
    req = (2 * h) if mode == "from_touch" else h
    valid = (idx >= 0) & ((idx + req) < len(close))
    if not np.any(valid):
        return {
            "expected_gross_pips": expected,
            "expected_side": side,
            "expected_decided": decided,
            "expected_both_window": both,
            "expected_clean": clean,
            "map_ok": map_ok,
        }
    i = idx[valid].astype(np.int64, copy=False)
    ref = close[i]
    num_ok = np.isfinite(ref)
    if mode == "from_start":
        ex = close[i + h]
        num_ok = num_ok & np.isfinite(ex)
    if not np.any(num_ok):
        return {
            "expected_gross_pips": expected,
            "expected_side": side,
            "expected_decided": decided,
            "expected_both_window": both,
            "expected_clean": clean,
            "map_ok": map_ok,
        }
    i = i[num_ok]
    map_pos = np.flatnonzero(valid)[num_ok]
    map_ok[map_pos] = True
    ref = ref[num_ok]
    if mode == "from_start":
        ex = ex[num_ok]
        ret = (ex - ref) / float(pip)

    up_thr = ref + k * float(pip)
    dn_thr = ref - k * float(pip)
    inf = h + 1
    up_step = np.full(len(i), inf, dtype=np.int32)
    dn_step = np.full(len(i), inf, dtype=np.int32)
    any_up = np.zeros(len(i), dtype=bool)
    any_dn = np.zeros(len(i), dtype=bool)
    for s in range(1, h + 1):
        j = i + int(s)
        hu = high[j] >= up_thr
        hd = low[j] <= dn_thr
        set_up = (up_step == inf) & hu
        set_dn = (dn_step == inf) & hd
        up_step[set_up] = int(s)
        dn_step[set_dn] = int(s)
        any_up |= hu
        any_dn |= hd

    side_v = np.zeros(len(i), dtype=np.int8)
    side_v[up_step < dn_step] = 1
    side_v[dn_step < up_step] = -1
    same = (up_step == dn_step) & (up_step <= h)
    if np.any(same):
        z = np.flatnonzero(same)
        tie_idx = i[z] + up_step[z].astype(np.int64, copy=False)
        tie_hlf = hlf[tie_idx]
        side_v[z[tie_hlf > 0.0]] = 1
        side_v[z[tie_hlf < 0.0]] = -1

    decided_v = side_v != 0
    both_v = any_up & any_dn
    clean_v = decided_v & (~both_v)
    gross_v = np.full(len(i), np.nan, dtype=float)
    if mode == "from_start":
        gross_v[decided_v] = side_v[decided_v].astype(float) * ret[decided_v] - float(k)
    else:
        touch_i = np.minimum(up_step, dn_step).astype(np.int64, copy=False)
        exit_i = i + touch_i + int(h)
        ok = decided_v & (exit_i < len(close))
        if np.any(ok):
            ok_idx = np.flatnonzero(ok)
            ex_ok = close[exit_i[ok_idx]]
            num2 = np.isfinite(ex_ok) & np.isfinite(ref[ok_idx])
            use = ok_idx[num2]
            if len(use) > 0:
                gross_v[use] = side_v[use].astype(float) * (
                    (close[exit_i[use]] - ref[use]) / float(pip)
                ) - float(k)

    expected_v = (
        np.zeros(len(i), dtype=float)
        if bool(include_no_touch)
        else np.full(len(i), np.nan, dtype=float)
    )
    if bool(include_no_touch):
        ok = np.isfinite(gross_v) & decided_v
        expected_v[ok] = gross_v[ok]
    else:
        expected_v[decided_v] = gross_v[decided_v]

    expected[map_pos] = expected_v
    side[map_pos] = side_v
    decided[map_pos] = decided_v
    both[map_pos] = both_v
    clean[map_pos] = clean_v

    return {
        "expected_gross_pips": expected,
        "expected_side": side,
        "expected_decided": decided,
        "expected_both_window": both,
        "expected_clean": clean,
        "map_ok": map_ok,
    }


def _metrics(d: pd.DataFrame, *, abs_tol: float) -> dict[str, float | int]:
    if d.empty:
        return {
            "rows_selected": 0,
            "rows_mapped": 0,
            "rows_verified": 0,
            "mean_abs_err_pips": float("nan"),
            "p99_abs_err_pips": float("nan"),
            "max_abs_err_pips": float("nan"),
            "exact_match_rate": float("nan"),
            "sign_match_rate": float("nan"),
            "pos_label_match_rate": float("nan"),
            "clean_violation_count": 0,
            "both_window_count": 0,
            "undecided_count": 0,
        }
    x = d.copy()
    target = pd.to_numeric(x["target_gross_pips"], errors="coerce").to_numpy(dtype=float)
    expected = pd.to_numeric(x["expected_gross_pips"], errors="coerce").to_numpy(dtype=float)
    mapped = x["map_ok"].astype(bool).to_numpy()
    finite = np.isfinite(target) & np.isfinite(expected)
    err = np.abs(target - expected)
    exact = finite & (err <= float(abs_tol))
    sign = finite & (np.sign(target) == np.sign(expected))
    if "target_gross_pos" in x.columns:
        tgt_pos = (
            pd.to_numeric(x["target_gross_pos"], errors="coerce").fillna(0).astype(int).to_numpy()
        )
    else:
        tgt_pos = (target > 0.0).astype(int)
    exp_pos = (expected > 0.0).astype(int)
    pos_ok = finite & (tgt_pos == exp_pos)
    exp_dec = x["expected_decided"].astype(bool).to_numpy()
    exp_clean = x["expected_clean"].astype(bool).to_numpy()
    exp_both = x["expected_both_window"].astype(bool).to_numpy()
    return {
        "rows_selected": int(len(x)),
        "rows_mapped": int(np.sum(mapped)),
        "rows_verified": int(np.sum(finite)),
        "mean_abs_err_pips": float(np.mean(err[finite])) if np.any(finite) else float("nan"),
        "p99_abs_err_pips": float(np.quantile(err[finite], 0.99))
        if np.any(finite)
        else float("nan"),
        "max_abs_err_pips": float(np.max(err[finite])) if np.any(finite) else float("nan"),
        "exact_match_rate": float(np.mean(exact[finite])) if np.any(finite) else float("nan"),
        "sign_match_rate": float(np.mean(sign[finite])) if np.any(finite) else float("nan"),
        "pos_label_match_rate": float(np.mean(pos_ok[finite])) if np.any(finite) else float("nan"),
        "clean_violation_count": int(np.sum(mapped & exp_dec & (~exp_clean))),
        "both_window_count": int(np.sum(mapped & exp_both)),
        "undecided_count": int(np.sum(mapped & (~exp_dec))),
    }


def run(cfg: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    symbol = str(cfg.get("symbol", DEFAULTS["symbol"])).upper().strip()
    abs_tol = float(cfg.get("abs_tol_pips", DEFAULTS["abs_tol_pips"]))
    q = float(cfg.get("locked_quantile", DEFAULTS["locked_quantile"]))
    selection_mode = str(cfg.get("selection_mode", DEFAULTS["selection_mode"]))
    family_required = str(cfg.get("family_required", DEFAULTS["family_required"])).strip()
    oco_hold_mode = str(cfg.get("oco_hold_mode", DEFAULTS["oco_hold_mode"])).strip().lower()
    oco_include_no_touch = bool(cfg.get("oco_include_no_touch", DEFAULTS["oco_include_no_touch"]))
    if oco_hold_mode not in {"from_touch", "from_start"}:
        raise ValueError("oco_hold_mode must be from_touch|from_start")
    sample_rows_per_combo = int(cfg.get("sample_rows_per_combo", DEFAULTS["sample_rows_per_combo"]))
    pip = float(_pip_size(symbol))

    shortlist_path = _resolve_shortlist_state_csv(
        str(cfg.get("shortlist_state_csv", DEFAULTS["shortlist_state_csv"])),
        symbol=symbol,
    )
    states = pd.read_csv(shortlist_path).copy()
    states = _normalize_shortlist_states(states, symbol=symbol)
    need_state = {"bar_ticks", "horizon", "state_id"}
    miss_state = [c for c in need_state if c not in states.columns]
    if miss_state:
        raise ValueError(f"shortlist state csv missing columns: {miss_state}")
    if "family" in states.columns and family_required:
        states = states[states["family"].astype(str) == family_required].copy()
    states["bar_ticks"] = pd.to_numeric(states["bar_ticks"], errors="coerce").astype("Int64")
    states["horizon"] = pd.to_numeric(states["horizon"], errors="coerce").astype("Int64")
    states = states.dropna(subset=["bar_ticks", "horizon", "state_id"]).copy()
    if states.empty:
        raise RuntimeError(f"shortlist state table empty after filtering: {shortlist_path}")
    if "barrier_pips" not in states.columns:
        states["barrier_pips"] = states["state_id"].astype(str).map(_parse_barrier_from_state)

    preds = pd.read_parquet(str(cfg.get("pred_path", DEFAULTS["pred_path"]))).copy()
    req = {"candidate_uid", "close_ts", "test_month", "pred_prob", "target_gross_pips"}
    miss = [c for c in req if c not in preds.columns]
    if miss:
        raise ValueError(f"predictions parquet missing columns: {miss}")
    uid_cols = _parse_uid_cols(preds["candidate_uid"])
    preds["uid_library"] = uid_cols["library"]
    preds["symbol"] = uid_cols["symbol"]
    preds["bar_ticks"] = uid_cols["bar_ticks"]
    preds["horizon"] = uid_cols["horizon"]
    preds["state_id"] = uid_cols["state_id"]
    lib_col = "library" if "library" in preds.columns else "uid_library"
    preds = preds[
        (preds[lib_col].astype(str) == "oco") & (preds["symbol"].astype(str) == symbol)
    ].copy()
    preds["close_ts"] = pd.to_datetime(preds["close_ts"], utc=True, errors="coerce")
    preds["pred_prob"] = pd.to_numeric(preds["pred_prob"], errors="coerce")
    preds["target_gross_pips"] = pd.to_numeric(preds["target_gross_pips"], errors="coerce")
    preds = preds.dropna(
        subset=["close_ts", "pred_prob", "target_gross_pips", "bar_ticks", "horizon", "state_id"]
    ).copy()
    preds["bar_ticks"] = preds["bar_ticks"].astype(int)
    preds["horizon"] = preds["horizon"].astype(int)
    states["bar_ticks"] = states["bar_ticks"].astype(int)
    states["horizon"] = states["horizon"].astype(int)

    key = ["bar_ticks", "horizon", "state_id"]
    meta = states[key + ["barrier_pips"]].drop_duplicates()
    d = preds.merge(meta, on=key, how="inner")
    if d.empty:
        raise RuntimeError("no rows left after shortlist merge")

    d = _select_events(d, q=q, mode=selection_mode)
    if d.empty:
        raise RuntimeError("selection empty (selection_mode/quantile)")

    if sample_rows_per_combo > 0:
        sampled: list[pd.DataFrame] = []
        for _, g in d.groupby(["test_month", "bar_ticks", "horizon", "state_id"], sort=False):
            if len(g) <= sample_rows_per_combo:
                sampled.append(g)
                continue
            take = np.linspace(0, len(g) - 1, num=sample_rows_per_combo, dtype=int)
            sampled.append(g.iloc[take].copy())
        d = pd.concat(sampled, ignore_index=True) if sampled else pd.DataFrame()
        if d.empty:
            raise RuntimeError("sampling removed all rows")

    d = d.sort_values(["bar_ticks", "close_ts", "horizon", "state_id"]).reset_index(drop=True)
    d["expected_gross_pips"] = np.nan
    d["expected_side"] = 0
    d["expected_decided"] = False
    d["expected_both_window"] = False
    d["expected_clean"] = False
    d["map_ok"] = False

    dataset_dir = Path(str(cfg.get("dataset_dir", DEFAULTS["dataset_dir"])))
    for bt_val, gb in d.groupby("bar_ticks", sort=True):
        bt = int(bt_val)
        path = dataset_dir / f"{symbol}_{bt}tick_velocity.parquet"
        if not path.exists():
            raise FileNotFoundError(path)
        bars = pd.read_parquet(
            path, columns=["close_ts", "close", "high", "low", "hl_first"]
        ).copy()
        bars["close_ts"] = pd.to_datetime(bars["close_ts"], utc=True, errors="coerce")
        bars = bars.dropna(subset=["close_ts"]).sort_values("close_ts").reset_index(drop=True)
        close = pd.to_numeric(bars["close"], errors="coerce").to_numpy(dtype=float)
        high = pd.to_numeric(bars["high"], errors="coerce").to_numpy(dtype=float)
        low = pd.to_numeric(bars["low"], errors="coerce").to_numpy(dtype=float)
        hlf = pd.to_numeric(bars["hl_first"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        idx_map = pd.Series(np.arange(len(bars), dtype=np.int64), index=bars["close_ts"])
        idx_map = idx_map[~idx_map.index.duplicated(keep="first")]
        bt_index = gb.index
        for (h_val, k_val), g in gb.groupby(["horizon", "barrier_pips"], sort=False):
            h, k = int(h_val), float(k_val)
            gi = g.index
            mapped = idx_map.reindex(g["close_ts"]).to_numpy(dtype=float)
            idx = np.full(len(g), -1, dtype=np.int64)
            m_ok = np.isfinite(mapped)
            idx[m_ok] = mapped[m_ok].astype(np.int64, copy=False)
            out = _recompute_first_touch(
                close=close,
                high=high,
                low=low,
                hlf=hlf,
                idx=idx,
                horizon=int(h),
                barrier_pips=float(k),
                pip=float(pip),
                hold_mode=oco_hold_mode,
                include_no_touch=oco_include_no_touch,
            )
            d.loc[gi, "expected_gross_pips"] = out["expected_gross_pips"]
            d.loc[gi, "expected_side"] = out["expected_side"]
            d.loc[gi, "expected_decided"] = out["expected_decided"]
            d.loc[gi, "expected_both_window"] = out["expected_both_window"]
            d.loc[gi, "expected_clean"] = out["expected_clean"]
            d.loc[gi, "map_ok"] = out["map_ok"]
        d.loc[bt_index, "bar_ticks"] = bt

    summary_row = _metrics(d, abs_tol=abs_tol)
    summary = pd.DataFrame([summary_row])
    summary["symbol"] = symbol
    summary["locked_quantile"] = float(q)
    summary["oco_hold_mode"] = oco_hold_mode
    summary["oco_include_no_touch"] = oco_include_no_touch
    min_exact = float(cfg.get("min_exact_match_rate", DEFAULTS["min_exact_match_rate"]))
    min_pos = float(cfg.get("min_pos_label_match_rate", DEFAULTS["min_pos_label_match_rate"]))
    summary["min_exact_match_rate"] = min_exact
    summary["min_pos_label_match_rate"] = min_pos
    summary["pass_exact_match"] = summary["exact_match_rate"] >= min_exact
    summary["pass_pos_label_match"] = summary["pos_label_match_rate"] >= min_pos
    summary["pass_clean"] = summary["clean_violation_count"] <= 0
    summary["overall_pass"] = (
        summary["pass_exact_match"] & summary["pass_pos_label_match"] & summary["pass_clean"]
    )
    summary = summary[
        [
            "symbol",
            "locked_quantile",
            "oco_hold_mode",
            "oco_include_no_touch",
            "rows_selected",
            "rows_mapped",
            "rows_verified",
            "mean_abs_err_pips",
            "p99_abs_err_pips",
            "max_abs_err_pips",
            "exact_match_rate",
            "sign_match_rate",
            "pos_label_match_rate",
            "clean_violation_count",
            "both_window_count",
            "undecided_count",
            "min_exact_match_rate",
            "min_pos_label_match_rate",
            "pass_exact_match",
            "pass_pos_label_match",
            "pass_clean",
            "overall_pass",
        ]
    ]

    state_rows: list[dict[str, Any]] = []
    for k_val, g in d.groupby(["bar_ticks", "horizon", "state_id"], sort=True):
        k = k_val
        m = _metrics(g, abs_tol=abs_tol)
        state_rows.append(
            {
                "bar_ticks": int(k[0]),
                "horizon": int(k[1]),
                "state_id": str(k[2]),
                **m,
            }
        )
    state = (
        pd.DataFrame(state_rows)
        .sort_values(["bar_ticks", "horizon", "state_id"])
        .reset_index(drop=True)
    )

    month_rows: list[dict[str, Any]] = []
    for m, g in d.groupby("test_month", sort=True):
        x = _metrics(g, abs_tol=abs_tol)
        month_rows.append({"test_month": str(m), **x})
    monthly = pd.DataFrame(month_rows).sort_values("test_month").reset_index(drop=True)

    out_summary_csv = Path(str(cfg.get("out_summary_csv", DEFAULTS["out_summary_csv"])))
    out_summary_csv.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(out_summary_csv, index=False)
    out_monthly_csv = Path(str(cfg.get("out_monthly_csv", DEFAULTS["out_monthly_csv"])))
    out_monthly_csv.parent.mkdir(parents=True, exist_ok=True)
    monthly.to_csv(out_monthly_csv, index=False)
    out_state_csv = Path(str(cfg.get("out_state_csv", DEFAULTS["out_state_csv"])))
    out_state_csv.parent.mkdir(parents=True, exist_ok=True)
    state.to_csv(out_state_csv, index=False)

    lines: list[str] = []
    lines.append("# OCO Tick-Exact Shortlist Verification")
    lines.append("")
    lines.append("## Setup")
    lines.append(f"- symbol: `{symbol}`")
    lines.append(f"- family_required: `{family_required}`")
    lines.append(f"- locked_quantile: `{q}`")
    lines.append(f"- selection_mode: `{selection_mode}`")
    lines.append(f"- oco_hold_mode: `{oco_hold_mode}`")
    lines.append(f"- oco_include_no_touch: `{oco_include_no_touch}`")
    lines.append(f"- abs_tol_pips: `{abs_tol}`")
    lines.append(f"- shortlist_state_csv: `{shortlist_path}`")
    lines.append("")
    lines.append("## Summary")
    lines.append(summary.to_markdown(index=False) if not summary.empty else "_empty_")
    lines.append("")
    lines.append("## By State")
    lines.append(state.to_markdown(index=False) if not state.empty else "_empty_")
    lines.append("")
    lines.append("## By Month")
    lines.append(monthly.to_markdown(index=False) if not monthly.empty else "_empty_")
    lines.append("")
    report_out = Path(str(cfg.get("report_out", DEFAULTS["report_out"])))
    report_out.parent.mkdir(parents=True, exist_ok=True)
    report_out.write_text("\n".join(lines), encoding="utf-8")

    print(f"wrote: {out_summary_csv}")
    print(f"wrote: {out_monthly_csv}")
    print(f"wrote: {out_state_csv}")
    print(f"wrote: {report_out}")
    return summary, state, monthly


def main() -> None:
    p = argparse.ArgumentParser(
        description="Verify reduced OCO shortlist with tick-exact first-touch replay"
    )
    p.add_argument("--config", default=None)
    p.add_argument("--symbol", default=None)
    p.add_argument("--dataset-dir", default=None)
    p.add_argument("--pred-path", default=None)
    p.add_argument("--shortlist-state-csv", default=None)
    p.add_argument("--locked-quantile", type=float, default=None)
    p.add_argument("--selection-mode", default=None)
    p.add_argument("--family-required", default=None)
    p.add_argument("--oco-hold-mode", default=None)
    p.add_argument("--oco-include-no-touch", default=None)
    p.add_argument("--sample-rows-per-combo", type=int, default=None)
    p.add_argument("--abs-tol-pips", type=float, default=None)
    p.add_argument("--min-exact-match-rate", type=float, default=None)
    p.add_argument("--min-pos-label-match-rate", type=float, default=None)
    p.add_argument("--out-summary-csv", default=None)
    p.add_argument("--out-monthly-csv", default=None)
    p.add_argument("--out-state-csv", default=None)
    p.add_argument("--report-out", default=None)
    args = p.parse_args()
    cfg = _merge_config(args)
    if isinstance(cfg.get("oco_include_no_touch"), str):
        cfg["oco_include_no_touch"] = str(cfg["oco_include_no_touch"]).strip().lower() in {
            "1",
            "true",
            "yes",
            "y",
        }
    run(cfg)


if __name__ == "__main__":
    main()
