#!/usr/bin/env python3
"""Select OCO reduced core with strict rolling month-by-month state selection.

This is the leakage-safe alternative to post-hoc reduced-core filtering:
- For each test month M, select states using only prior train months.
- Apply selected states to month M events only.
"""

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
    "candidate_csv": "data/analysis/tick_opportunity_mining/EURUSD_oco_candidates.csv",
    "pred_path": "data/analysis/tick_opportunity_mining/wfo_2025_m3to1_oco_fullcap/EURUSD_oco_monthly_predictions.parquet",
    "family_keep": "oco_first_touch_clean",
    "barrier_keep": "2,3",
    "horizon_keep": "5,6",
    "locked_quantile": 0.9,
    "selection_mode": "auto",  # auto|exec_flag|monthly_quantile
    "execution_mode": "gross",  # gross|stop_limit
    "stop_limit_detail_csv": "",
    "stop_limit_cap_pips": 1.2,
    "stop_limit_slippage_mode": "full_overshoot",  # full_overshoot|none
    "stop_limit_min_fill_rate": 0.0,
    "stop_limit_require_match_rate": 0.95,
    "state_train_months": 3,
    "min_train_months": 3,
    "overlap_corr_max": 0.85,
    "max_states": 12,
    "min_states": 4,
    "min_state_avg_rows": 200.0,
    "min_positive_months_train": 2,
    "strict_gate_only": True,
    "overlap_divergence_max": 0.40,
    "require_lb95_trade_gt0": True,
    "require_lb95_month_gt0": True,
    "bootstrap_paths": 600,
    "seed": 42,
    "capacity_floor_monthly": 3000.0,
    "capacity_floor_annual": 5000.0,
    "max_state_churn": 0.45,
    "max_top_state_share": 0.35,
    "max_state_hhi": 0.25,
    "enforce_state_stability_gates": False,
    "out_state_schedule_csv": "data/analysis/tick_opportunity_mining/reduced_core_rolling/EURUSD_oco_reduced_state_schedule.csv",
    "out_state_csv": "data/analysis/tick_opportunity_mining/reduced_core/EURUSD_oco_reduced_states.csv",
    "out_monthly_csv": "data/analysis/tick_opportunity_mining/reduced_core_rolling/EURUSD_oco_reduced_monthly.csv",
    "out_summary_csv": "data/analysis/tick_opportunity_mining/reduced_core_rolling/EURUSD_oco_reduced_summary.csv",
    "out_state_churn_csv": "",
    "report_out": "docs/analysis/eurusd_oco_reduced_core_rolling_report.md",
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


def _parse_ints(raw: str) -> list[int]:
    return [int(x.strip()) for x in str(raw).split(",") if x.strip()]


def _parse_floats(raw: str) -> list[float]:
    return [float(x.strip()) for x in str(raw).split(",") if x.strip()]


def _bootstrap_lb95(vals: np.ndarray, *, paths: int, seed: int) -> float:
    x = np.asarray(vals, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) == 0 or int(paths) <= 0:
        return float("nan")
    rng = np.random.default_rng(int(seed))
    n = len(x)
    draws: list[np.ndarray] = []
    batch = 200
    for i in range(0, int(paths), batch):
        b = min(batch, int(paths) - i)
        idx = rng.integers(0, n, size=(b, n))
        draws.append(x[idx].mean(axis=1))
    m = np.concatenate(draws) if draws else np.array([], dtype=float)
    if len(m) == 0:
        return float("nan")
    return float(np.quantile(m, 0.05))


def _parse_candidate_uid(uid: str) -> tuple[str, str, int, int, str]:
    toks = str(uid).split("|", 4)
    if len(toks) != 5:
        raise ValueError(f"bad candidate_uid: {uid!r}")
    lib, symbol, bt, htxt, state_id = toks
    horizon = int(str(htxt).lstrip("hH"))
    return str(lib), str(symbol).upper(), int(bt), horizon, str(state_id)


def _parse_barrier_row(row: pd.Series) -> float:
    if "barrier_pips" in row and pd.notna(row.get("barrier_pips", np.nan)):
        try:
            return float(row["barrier_pips"])
        except Exception:
            pass
    txt = str(row.get("regime_desc", ""))
    if "barrier=" in txt:
        try:
            return float(txt.split("barrier=")[-1].strip())
        except Exception:
            pass
    sid = str(row.get("state_id", ""))
    m = re.search(r"k([0-9]+(?:\.[0-9]+)?)$", sid)
    if m:
        return float(m.group(1))
    raise ValueError(f"cannot parse barrier from row state_id={sid!r}")


def _select_month_q(d: pd.DataFrame, q: float) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    for _, g in d.groupby("test_month", sort=True):
        thr = float(np.quantile(g["pred_prob"].to_numpy(dtype=float), float(q)))
        x = g[g["pred_prob"] >= thr].copy()
        x["threshold"] = float(thr)
        parts.append(x)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


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


def _table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_empty_"
    try:
        return df.to_markdown(index=False)
    except ImportError:
        return "```\n" + df.to_string(index=False) + "\n```"


def _annualized_from_monthly_rows(monthly: pd.DataFrame) -> float:
    if monthly.empty:
        return 0.0
    return float(pd.to_numeric(monthly["rows"], errors="coerce").mean()) * 12.0


def _default_out_state_csv(symbol: str) -> Path:
    s = str(symbol).upper().strip()
    if s == "EURUSD":
        return Path(
            "data/analysis/tick_opportunity_mining/reduced_core/EURUSD_oco_reduced_states.csv"
        )
    if s == "GBPUSD":
        return Path(
            "data/analysis/tick_opportunity_mining/reduced_core_gbpusd/GBPUSD_oco_reduced_states.csv"
        )
    return Path(
        f"data/analysis/tick_opportunity_mining/reduced_core_{s.lower()}/{s}_oco_reduced_states.csv"
    )


def _prepare_execution_frame(
    selected: pd.DataFrame, cfg: dict[str, Any]
) -> tuple[pd.DataFrame, dict[str, float]]:
    mode = str(cfg.get("execution_mode", "gross")).strip().lower()
    if mode not in {"gross", "stop_limit"}:
        raise ValueError("execution_mode must be gross|stop_limit")

    out = selected.copy()
    out["__filled"] = 1
    out["__pnl_signal"] = pd.to_numeric(out["target_gross_pips"], errors="coerce")
    out["__pnl_trade"] = pd.to_numeric(out["target_gross_pips"], errors="coerce")
    meta = {
        "mode": mode,
        "match_rate": 1.0,
        "fill_rate": float(np.mean(out["__filled"])) if len(out) else float("nan"),
    }
    if mode == "gross":
        return out, meta

    detail_csv = str(cfg.get("stop_limit_detail_csv", "")).strip()
    if not detail_csv:
        raise ValueError("stop_limit_detail_csv is required when execution_mode=stop_limit")
    dpath = Path(detail_csv)
    if not dpath.exists():
        raise FileNotFoundError(f"stop_limit_detail_csv not found: {dpath}")

    d = pd.read_csv(
        dpath,
        usecols=["close_ts", "candidate_uid", "touch_found_tick", "overshoot_tick_pips"],
    ).copy()
    d["close_ts"] = pd.to_datetime(d["close_ts"], utc=True, errors="coerce")
    d["candidate_uid"] = d["candidate_uid"].astype(str)
    d["touch_found_tick"] = (
        pd.to_numeric(d["touch_found_tick"], errors="coerce").fillna(0).astype(int)
    )
    d["overshoot_tick_pips"] = pd.to_numeric(d["overshoot_tick_pips"], errors="coerce")
    d = d.dropna(subset=["close_ts"]).copy()
    d = d.sort_values(["candidate_uid", "close_ts"]).drop_duplicates(
        subset=["candidate_uid", "close_ts"],
        keep="last",
    )

    out["close_ts"] = pd.to_datetime(out["close_ts"], utc=True, errors="coerce")
    out["candidate_uid"] = out["candidate_uid"].astype(str)
    out = out.merge(
        d,
        on=["candidate_uid", "close_ts"],
        how="left",
        validate="many_to_one",
    )
    matched = out["touch_found_tick"].notna().mean() if len(out) else 1.0
    req_match = float(cfg.get("stop_limit_require_match_rate", 0.95))
    if matched < req_match:
        raise RuntimeError(
            f"stop-limit detail match_rate too low: {matched:.4f} < required {req_match:.4f}"
        )

    cap = float(cfg.get("stop_limit_cap_pips", 1.2))
    found = pd.to_numeric(out["touch_found_tick"], errors="coerce").fillna(0).astype(int) == 1
    overs = pd.to_numeric(out["overshoot_tick_pips"], errors="coerce")
    filled = found & overs.notna() & (overs <= cap)
    out["__filled"] = filled.astype(int)

    gross = pd.to_numeric(out["target_gross_pips"], errors="coerce")
    slip_mode = str(cfg.get("stop_limit_slippage_mode", "full_overshoot")).strip().lower()
    if slip_mode not in {"full_overshoot", "none"}:
        raise ValueError("stop_limit_slippage_mode must be full_overshoot|none")
    trade = gross - overs if slip_mode == "full_overshoot" else gross
    out["__pnl_trade"] = trade.where(filled, np.nan)
    out["__pnl_signal"] = trade.where(filled, 0.0)

    meta = {
        "mode": mode,
        "match_rate": float(matched),
        "fill_rate": float(np.mean(out["__filled"])) if len(out) else float("nan"),
    }
    return out, meta


def run(cfg: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    symbol = str(cfg["symbol"]).upper().strip()
    family_keep = str(cfg["family_keep"]).strip()
    barrier_keep = set(_parse_floats(str(cfg["barrier_keep"])))
    horizon_keep = set(_parse_ints(str(cfg["horizon_keep"])))
    q = float(cfg["locked_quantile"])
    selection_mode = str(cfg.get("selection_mode", DEFAULTS["selection_mode"]))
    state_train_months = int(cfg["state_train_months"])
    min_train_months = int(cfg["min_train_months"])
    overlap_corr_max = float(cfg["overlap_corr_max"])
    max_states = int(cfg["max_states"])
    min_states = int(cfg["min_states"])
    min_state_avg_rows = float(cfg["min_state_avg_rows"])
    min_positive_months_train = int(cfg["min_positive_months_train"])
    strict_gate_only = bool(cfg.get("strict_gate_only", True))
    overlap_divergence_max = float(cfg.get("overlap_divergence_max", 0.40))
    min_fill_rate = float(cfg.get("stop_limit_min_fill_rate", 0.0))
    max_state_churn = float(cfg.get("max_state_churn", DEFAULTS["max_state_churn"]))
    max_top_state_share = float(cfg.get("max_top_state_share", DEFAULTS["max_top_state_share"]))
    max_state_hhi = float(cfg.get("max_state_hhi", DEFAULTS["max_state_hhi"]))
    enforce_state_stability_gates = bool(
        cfg.get("enforce_state_stability_gates", DEFAULTS["enforce_state_stability_gates"])
    )
    require_lb95_trade_gt0 = bool(cfg["require_lb95_trade_gt0"])
    require_lb95_month_gt0 = bool(cfg["require_lb95_month_gt0"])
    bootstrap_paths = int(cfg["bootstrap_paths"])
    seed = int(cfg["seed"])
    capacity_floor_monthly = float(cfg["capacity_floor_monthly"])
    capacity_floor_annual = float(cfg["capacity_floor_annual"])

    c = pd.read_csv(str(cfg["candidate_csv"])).copy()
    p = pd.read_parquet(str(cfg["pred_path"])).copy()
    p = p.dropna(subset=["candidate_uid", "pred_prob", "target_gross_pips", "test_month"]).copy()
    p["pred_prob"] = pd.to_numeric(p["pred_prob"], errors="coerce")
    p["target_gross_pips"] = pd.to_numeric(p["target_gross_pips"], errors="coerce")
    p = p.dropna(subset=["pred_prob", "target_gross_pips"]).copy()

    parsed = p["candidate_uid"].astype(str).map(_parse_candidate_uid)
    p["library"] = parsed.map(lambda x: x[0])
    p["symbol"] = parsed.map(lambda x: x[1])
    p["bar_ticks"] = parsed.map(lambda x: x[2])
    p["horizon"] = parsed.map(lambda x: x[3])
    p["state_id"] = parsed.map(lambda x: x[4])
    p = p[(p["library"] == "oco") & (p["symbol"] == symbol)].copy()
    p["test_month"] = p["test_month"].astype(str)

    c["symbol"] = c["symbol"].astype(str).str.upper()
    c["bar_ticks"] = pd.to_numeric(c["bar_ticks"], errors="coerce").astype("Int64")
    c["horizon"] = pd.to_numeric(c["horizon"], errors="coerce").astype("Int64")
    if "barrier_pips" not in c.columns:
        c["barrier_pips"] = c.apply(_parse_barrier_row, axis=1)
    c["barrier_pips"] = pd.to_numeric(c["barrier_pips"], errors="coerce")
    c = c[
        (c["symbol"] == symbol)
        & (c["family"].astype(str) == family_keep)
        & (c["barrier_pips"].isin(list(barrier_keep)))
        & (c["horizon"].isin(list(horizon_keep)))
    ].copy()
    if c.empty:
        raise RuntimeError("candidate filter empty")

    key_cols = ["symbol", "bar_ticks", "horizon", "state_id"]
    meta_cols = key_cols + ["family", "regime_desc", "barrier_pips"]
    c_meta = c[meta_cols].drop_duplicates()
    p = p.merge(c_meta, on=key_cols, how="inner")
    if p.empty:
        raise RuntimeError("no predictions left after candidate metadata merge")

    selected_all = _select_events(p, q=q, mode=selection_mode)
    if selected_all.empty:
        raise RuntimeError("selection empty (selection_mode/quantile)")
    selected_all["test_month"] = selected_all["test_month"].astype(str)
    selected_all["state_key"] = (
        selected_all["state_id"].astype(str)
        + "|"
        + pd.to_numeric(selected_all["bar_ticks"], errors="coerce")
        .fillna(-1)
        .astype(int)
        .astype(str)
        + "|"
        + pd.to_numeric(selected_all["horizon"], errors="coerce").fillna(-1).astype(int).astype(str)
    )
    selected_all, exec_meta = _prepare_execution_frame(selected_all, cfg)

    months = sorted(selected_all["test_month"].unique().tolist())
    if months:
        last_m = months[-1]
        y, m = map(int, last_m.split("-"))
        m += 1
        if m > 12:
            m = 1
            y += 1
        next_m = f"{y:04d}-{m:02d}"
        months.append(next_m)

    sched_rows: list[dict[str, Any]] = []
    monthly_rows: list[dict[str, Any]] = []
    prev_selected_keys: set[str] | None = None

    for i, month in enumerate(months):
        train_start = max(0, i - state_train_months)
        train_months = months[train_start:i]
        if len(train_months) < int(min_train_months):
            monthly_rows.append(
                {
                    "symbol": symbol,
                    "test_month": str(month),
                    "train_months": ",".join(train_months),
                    "states_selected": 0,
                    "rows": 0,
                    "signal_rows": 0,
                    "fill_rate": np.nan,
                    "mean_gross_pips": np.nan,
                    "mean_signal_pips": np.nan,
                    "median_gross_pips": np.nan,
                    "pos_rate": np.nan,
                    "state_churn_rate": np.nan,
                    "top_state_share": np.nan,
                    "state_hhi": np.nan,
                    "stability_pass": np.nan,
                    "status": "warmup_skip",
                }
            )
            continue

        train = selected_all[selected_all["test_month"].isin(train_months)].copy()
        if train.empty:
            monthly_rows.append(
                {
                    "symbol": symbol,
                    "test_month": str(month),
                    "train_months": ",".join(train_months),
                    "states_selected": 0,
                    "rows": 0,
                    "signal_rows": 0,
                    "fill_rate": np.nan,
                    "mean_gross_pips": np.nan,
                    "mean_signal_pips": np.nan,
                    "median_gross_pips": np.nan,
                    "pos_rate": np.nan,
                    "state_churn_rate": np.nan,
                    "top_state_share": np.nan,
                    "state_hhi": np.nan,
                    "stability_pass": np.nan,
                    "status": "no_train_rows",
                }
            )
            continue

        state_group_cols = [
            "symbol",
            "bar_ticks",
            "horizon",
            "state_id",
            "family",
            "regime_desc",
            "barrier_pips",
        ]
        state_rows: list[dict[str, Any]] = []
        for j, (k, g) in enumerate(train.groupby(state_group_cols, sort=False), start=1):
            mon = g.groupby("test_month", as_index=False).agg(
                signal_rows=("__pnl_signal", "size"),
                filled_rows=("__filled", "sum"),
                mean_signal=("__pnl_signal", "mean"),
            )
            gg_signal = pd.to_numeric(g["__pnl_signal"], errors="coerce").to_numpy(dtype=float)
            gg_trade = pd.to_numeric(g["__pnl_trade"], errors="coerce").to_numpy(dtype=float)
            gg_trade = gg_trade[np.isfinite(gg_trade)]
            mm = mon["mean_signal"].to_numpy(dtype=float)
            lb_t = _bootstrap_lb95(gg_signal, paths=bootstrap_paths, seed=seed + i * 1000 + j * 7)
            lb_m = _bootstrap_lb95(mm, paths=bootstrap_paths, seed=seed + i * 1000 + j * 13)
            fill_rate_train = float(
                np.mean(pd.to_numeric(g["__filled"], errors="coerce").fillna(0).astype(int))
            )

            gate = True
            if require_lb95_trade_gt0:
                gate = gate and (lb_t > 0.0)
            if require_lb95_month_gt0:
                gate = gate and (lb_m > 0.0)
            gate = gate and (float(mon["filled_rows"].mean()) >= min_state_avg_rows)
            gate = gate and (int(np.sum(mm > 0.0)) >= min_positive_months_train)
            gate = gate and (fill_rate_train >= min_fill_rate)

            state_rows.append(
                {
                    "symbol": k[0],
                    "bar_ticks": int(k[1]),
                    "horizon": int(k[2]),
                    "state_id": str(k[3]),
                    "family": str(k[4]),
                    "regime_desc": str(k[5]),
                    "barrier_pips": float(k[6]),
                    "train_rows": int(len(g)),
                    "train_months_count": int(mon["test_month"].nunique()),
                    "train_avg_month_rows": float(mon["filled_rows"].mean()),
                    "train_mean_gross_pips": float(np.mean(gg_trade)) if len(gg_trade) else np.nan,
                    "train_mean_signal_pips": float(np.mean(gg_signal)),
                    "train_median_gross_pips": float(np.median(gg_trade))
                    if len(gg_trade)
                    else np.nan,
                    "train_pos_rate": float(np.mean(gg_signal > 0.0)),
                    "train_positive_months": int(np.sum(mm > 0.0)),
                    "train_lb95_trade_mean_gross_pips": float(lb_t),
                    "train_lb95_month_mean_gross_pips": float(lb_m),
                    "train_fill_rate": float(fill_rate_train),
                    "gate_pass": bool(gate),
                }
            )

        s = pd.DataFrame(state_rows)
        if s.empty:
            monthly_rows.append(
                {
                    "symbol": symbol,
                    "test_month": str(month),
                    "train_months": ",".join(train_months),
                    "states_selected": 0,
                    "rows": 0,
                    "signal_rows": 0,
                    "fill_rate": np.nan,
                    "mean_gross_pips": np.nan,
                    "mean_signal_pips": np.nan,
                    "median_gross_pips": np.nan,
                    "pos_rate": np.nan,
                    "state_churn_rate": np.nan,
                    "top_state_share": np.nan,
                    "state_hhi": np.nan,
                    "stability_pass": np.nan,
                    "status": "no_states",
                }
            )
            continue

        s = s.sort_values(
            [
                "gate_pass",
                "train_lb95_month_mean_gross_pips",
                "train_lb95_trade_mean_gross_pips",
                "train_mean_signal_pips",
                "train_avg_month_rows",
            ],
            ascending=[False, False, False, False, False],
        ).reset_index(drop=True)
        s["state_key"] = (
            s["state_id"].astype(str)
            + "|"
            + pd.to_numeric(s["bar_ticks"], errors="coerce").fillna(-1).astype(int).astype(str)
            + "|"
            + pd.to_numeric(s["horizon"], errors="coerce").fillna(-1).astype(int).astype(str)
        )

        dep = train.groupby(["state_key", "test_month"], as_index=False).agg(
            activity=("__filled", "sum"),
            pnl_signal=("__pnl_signal", "mean"),
        )
        piv_act = dep.pivot(index="state_key", columns="test_month", values="activity").fillna(0.0)
        piv_pnl = dep.pivot(index="state_key", columns="test_month", values="pnl_signal")
        corr_act = piv_act.T.corr() if not piv_act.empty else pd.DataFrame()
        corr_pnl = piv_pnl.T.corr() if not piv_pnl.empty else pd.DataFrame()

        selected_keys: list[str] = []
        selected_corr_max: dict[str, float] = {}
        selected_div_max: dict[str, float] = {}
        pass_keys = set(s[s["gate_pass"]]["state_key"].astype(str).tolist())
        candidate_order = [x for x in s["state_key"].astype(str).tolist() if x in pass_keys]
        if not candidate_order and strict_gate_only:
            monthly_rows.append(
                {
                    "symbol": symbol,
                    "test_month": str(month),
                    "train_months": ",".join(train_months),
                    "states_selected": 0,
                    "rows": 0,
                    "signal_rows": 0,
                    "fill_rate": np.nan,
                    "mean_gross_pips": np.nan,
                    "mean_signal_pips": np.nan,
                    "median_gross_pips": np.nan,
                    "pos_rate": np.nan,
                    "state_churn_rate": np.nan,
                    "top_state_share": np.nan,
                    "state_hhi": np.nan,
                    "stability_pass": np.nan,
                    "status": "no_gate_states",
                }
            )
            continue
        if not candidate_order:
            candidate_order = s["state_key"].astype(str).tolist()

        for sk in candidate_order:
            if len(selected_keys) >= max_states:
                break
            if sk in selected_keys:
                continue
            if not selected_keys:
                selected_keys.append(sk)
                selected_corr_max[sk] = 0.0
                selected_div_max[sk] = 0.0
                continue
            cvals: list[float] = []
            dvals: list[float] = []
            for t in selected_keys:
                cp = (
                    float(corr_pnl.loc[sk, t])
                    if (sk in corr_pnl.index and t in corr_pnl.columns)
                    else np.nan
                )
                ca = (
                    float(corr_act.loc[sk, t])
                    if (sk in corr_act.index and t in corr_act.columns)
                    else np.nan
                )
                if np.isfinite(cp):
                    cvals.append(abs(cp))
                if np.isfinite(cp) and np.isfinite(ca):
                    dvals.append(abs(cp - ca))
            cmax = float(np.max(cvals)) if cvals else 0.0
            dmax = float(np.max(dvals)) if dvals else 0.0
            if cmax <= overlap_corr_max and dmax <= overlap_divergence_max:
                selected_keys.append(sk)
                selected_corr_max[sk] = cmax
                selected_div_max[sk] = dmax

        if len(selected_keys) < min_states and not strict_gate_only:
            for sk in s["state_key"].astype(str).tolist():
                if sk not in selected_keys:
                    selected_keys.append(sk)
                    selected_corr_max[sk] = float("nan")
                    selected_div_max[sk] = float("nan")
                if len(selected_keys) >= min_states:
                    break

        rank_map = {sk: idx + 1 for idx, sk in enumerate(selected_keys)}
        selected_state_df = s[s["state_key"].astype(str).isin(set(selected_keys))].copy()
        selected_state_df["selected_rank"] = (
            selected_state_df["state_key"].astype(str).map(rank_map)
        )
        selected_state_df["overlap_corr_max"] = (
            selected_state_df["state_key"].astype(str).map(selected_corr_max).fillna(np.nan)
        )
        selected_state_df["overlap_div_max"] = (
            selected_state_df["state_key"].astype(str).map(selected_div_max).fillna(np.nan)
        )
        selected_state_df = selected_state_df.sort_values("selected_rank").reset_index(drop=True)

        test = selected_all[
            (selected_all["test_month"] == str(month))
            & (selected_all["state_key"].astype(str).isin(set(selected_keys)))
        ].copy()
        sig = pd.to_numeric(test["__pnl_signal"], errors="coerce").to_numpy(dtype=float)
        trd = pd.to_numeric(test["__pnl_trade"], errors="coerce").to_numpy(dtype=float)
        trd = trd[np.isfinite(trd)]
        filled_rows = int(
            pd.to_numeric(test["__filled"], errors="coerce").fillna(0).astype(int).sum()
        )
        signal_rows = int(len(test))
        fill_rate = float(filled_rows / signal_rows) if signal_rows > 0 else np.nan
        state_counts = (
            test.groupby("state_key", as_index=False)
            .agg(rows=("candidate_uid", "size"))
            .sort_values("rows", ascending=False)
            .reset_index(drop=True)
        )
        shares = (
            pd.to_numeric(state_counts["rows"], errors="coerce").to_numpy(dtype=float)
            / max(float(signal_rows), 1.0)
            if signal_rows > 0 and not state_counts.empty
            else np.array([], dtype=float)
        )
        top_share = float(np.max(shares)) if len(shares) else np.nan
        state_hhi = float(np.sum(shares * shares)) if len(shares) else np.nan
        selected_now = set(selected_keys)
        if prev_selected_keys is None:
            churn = 0.0
        else:
            u = selected_now.union(prev_selected_keys)
            inter = selected_now.intersection(prev_selected_keys)
            churn = float(1.0 - (len(inter) / max(len(u), 1)))
        stability_pass = bool(
            (not np.isfinite(churn) or churn <= max_state_churn)
            and (not np.isfinite(top_share) or top_share <= max_top_state_share)
            and (not np.isfinite(state_hhi) or state_hhi <= max_state_hhi)
        )
        month_status = "ok" if signal_rows > 0 else "no_test_rows"
        if enforce_state_stability_gates and signal_rows > 0 and not stability_pass:
            month_status = "stability_gate_fail"
            filled_rows = 0
            signal_rows = 0
            fill_rate = np.nan
            trd = np.array([], dtype=float)
            sig = np.array([], dtype=float)

        monthly_rows.append(
            {
                "symbol": symbol,
                "test_month": str(month),
                "train_months": ",".join(train_months),
                "states_selected": int(len(selected_keys)),
                "rows": int(filled_rows),
                "signal_rows": int(signal_rows),
                "fill_rate": float(fill_rate),
                "mean_gross_pips": float(np.mean(trd)) if len(trd) else np.nan,
                "mean_signal_pips": float(np.mean(sig)) if len(sig) else np.nan,
                "median_gross_pips": float(np.median(trd)) if len(trd) else np.nan,
                "pos_rate": float(np.mean(sig > 0.0)) if len(sig) else np.nan,
                "state_churn_rate": float(churn),
                "top_state_share": float(top_share) if np.isfinite(top_share) else np.nan,
                "state_hhi": float(state_hhi) if np.isfinite(state_hhi) else np.nan,
                "stability_pass": bool(stability_pass),
                "status": month_status,
            }
        )
        prev_selected_keys = selected_now

        for _, r in selected_state_df.iterrows():
            sched_rows.append(
                {
                    "symbol": symbol,
                    "test_month": str(month),
                    "train_months": ",".join(train_months),
                    "selected_rank": int(r["selected_rank"]),
                    "state_id": str(r["state_id"]),
                    "state_key": str(r["state_key"]),
                    "bar_ticks": int(r["bar_ticks"]),
                    "horizon": int(r["horizon"]),
                    "family": str(r["family"]),
                    "regime_desc": str(r["regime_desc"]),
                    "barrier_pips": float(r["barrier_pips"]),
                    "overlap_corr_max": float(r["overlap_corr_max"])
                    if np.isfinite(r["overlap_corr_max"])
                    else np.nan,
                    "overlap_div_max": float(r["overlap_div_max"])
                    if np.isfinite(r["overlap_div_max"])
                    else np.nan,
                    "train_rows": int(r["train_rows"]),
                    "train_months_count": int(r["train_months_count"]),
                    "train_avg_month_rows": float(r["train_avg_month_rows"]),
                    "train_mean_gross_pips": float(r["train_mean_gross_pips"])
                    if np.isfinite(r["train_mean_gross_pips"])
                    else np.nan,
                    "train_mean_signal_pips": float(r["train_mean_signal_pips"]),
                    "train_lb95_trade_mean_gross_pips": float(
                        r["train_lb95_trade_mean_gross_pips"]
                    ),
                    "train_lb95_month_mean_gross_pips": float(
                        r["train_lb95_month_mean_gross_pips"]
                    ),
                    "train_positive_months": int(r["train_positive_months"]),
                    "train_fill_rate": float(r["train_fill_rate"]),
                    "gate_pass": bool(r["gate_pass"]),
                }
            )

    schedule = (
        pd.DataFrame(sched_rows)
        .sort_values(["test_month", "selected_rank", "state_id"])
        .reset_index(drop=True)
        if sched_rows
        else pd.DataFrame()
    )
    monthly = pd.DataFrame(monthly_rows).sort_values("test_month").reset_index(drop=True)

    ok = monthly[monthly["status"] == "ok"].copy()
    ok_vals = pd.to_numeric(ok["mean_gross_pips"], errors="coerce").to_numpy(dtype=float)
    ok_sig_vals = pd.to_numeric(ok["mean_signal_pips"], errors="coerce").to_numpy(dtype=float)
    overall_lb95_month = (
        _bootstrap_lb95(ok_vals, paths=bootstrap_paths, seed=seed + 999) if len(ok_vals) else np.nan
    )
    overall_lb95_month_signal = (
        _bootstrap_lb95(ok_sig_vals, paths=bootstrap_paths, seed=seed + 1199)
        if len(ok_sig_vals)
        else np.nan
    )
    annualized_rows = _annualized_from_monthly_rows(ok)
    avg_month_rows = (
        float(pd.to_numeric(ok["rows"], errors="coerce").mean()) if not ok.empty else 0.0
    )
    avg_month_signal_rows = (
        float(pd.to_numeric(ok["signal_rows"], errors="coerce").mean()) if not ok.empty else 0.0
    )
    fill_rate_overall = (
        float(
            pd.to_numeric(ok["rows"], errors="coerce").sum()
            / max(pd.to_numeric(ok["signal_rows"], errors="coerce").sum(), 1.0)
        )
        if not ok.empty
        else np.nan
    )

    summary = pd.DataFrame(
        [
            {
                "symbol": symbol,
                "locked_quantile": q,
                "selection_mode": selection_mode,
                "execution_mode": str(cfg.get("execution_mode", "gross")).strip().lower(),
                "state_train_months": state_train_months,
                "months_total": int(len(months)),
                "months_scored": int(len(ok)),
                "rows_total": int(pd.to_numeric(ok["rows"], errors="coerce").sum())
                if not ok.empty
                else 0,
                "signal_rows_total": int(pd.to_numeric(ok["signal_rows"], errors="coerce").sum())
                if not ok.empty
                else 0,
                "mean_gross_pips": float(
                    np.average(
                        pd.to_numeric(ok["mean_gross_pips"], errors="coerce"),
                        weights=np.maximum(pd.to_numeric(ok["rows"], errors="coerce"), 1.0),
                    )
                )
                if not ok.empty
                else np.nan,
                "monthly_mean_gross_pips": float(np.nanmean(ok_vals)) if len(ok_vals) else np.nan,
                "lb95_month_mean_gross_pips": float(overall_lb95_month)
                if np.isfinite(overall_lb95_month)
                else np.nan,
                "mean_signal_pips": float(
                    np.average(
                        pd.to_numeric(ok["mean_signal_pips"], errors="coerce"),
                        weights=np.maximum(pd.to_numeric(ok["signal_rows"], errors="coerce"), 1.0),
                    )
                )
                if not ok.empty
                else np.nan,
                "monthly_mean_signal_pips": float(np.nanmean(ok_sig_vals))
                if len(ok_sig_vals)
                else np.nan,
                "lb95_month_mean_signal_pips": float(overall_lb95_month_signal)
                if np.isfinite(overall_lb95_month_signal)
                else np.nan,
                "positive_months": int(np.nansum(ok_vals > 0.0)) if len(ok_vals) else 0,
                "positive_months_signal": int(np.nansum(ok_sig_vals > 0.0))
                if len(ok_sig_vals)
                else 0,
                "avg_month_rows": float(avg_month_rows),
                "avg_month_signal_rows": float(avg_month_signal_rows),
                "fill_rate_overall": float(fill_rate_overall)
                if np.isfinite(fill_rate_overall)
                else np.nan,
                "annualized_rows": float(annualized_rows),
                "capacity_floor_monthly": capacity_floor_monthly,
                "capacity_floor_annual": capacity_floor_annual,
                "capacity_pass_monthly_or_annual": bool(
                    (avg_month_rows >= capacity_floor_monthly)
                    or (annualized_rows >= capacity_floor_annual)
                ),
                "max_state_churn": max_state_churn,
                "max_top_state_share": max_top_state_share,
                "max_state_hhi": max_state_hhi,
                "stability_months_pass": int(
                    pd.to_numeric(ok.get("stability_pass", pd.Series(dtype=float)), errors="coerce")
                    .fillna(0)
                    .astype(int)
                    .sum()
                )
                if not ok.empty
                else 0,
            }
        ]
    )

    churn_df = (
        monthly[
            [
                "symbol",
                "test_month",
                "states_selected",
                "state_churn_rate",
                "top_state_share",
                "state_hhi",
                "stability_pass",
                "status",
            ]
        ].copy()
        if not monthly.empty
        else pd.DataFrame()
    )

    out_sched = Path(str(cfg["out_state_schedule_csv"]))
    out_state_raw = str(cfg.get("out_state_csv", "")).strip()
    if out_state_raw:
        out_state = Path(out_state_raw)
    else:
        if out_sched.name.endswith("_state_schedule.csv"):
            out_state = out_sched.with_name(
                out_sched.name.replace("_state_schedule.csv", "_states.csv")
            )
        else:
            out_state = out_sched.with_name(f"{symbol}_oco_reduced_states.csv")
    out_month = Path(str(cfg["out_monthly_csv"]))
    out_sum = Path(str(cfg["out_summary_csv"]))
    out_churn_raw = str(cfg.get("out_state_churn_csv", "")).strip()
    out_churn = (
        Path(out_churn_raw)
        if out_churn_raw
        else out_month.with_name(out_month.name.replace("_monthly.csv", "_state_churn.csv"))
    )
    out_sched.parent.mkdir(parents=True, exist_ok=True)
    out_state.parent.mkdir(parents=True, exist_ok=True)
    out_month.parent.mkdir(parents=True, exist_ok=True)
    out_sum.parent.mkdir(parents=True, exist_ok=True)
    out_churn.parent.mkdir(parents=True, exist_ok=True)
    state_cols = [
        "symbol",
        "bar_ticks",
        "horizon",
        "state_id",
        "family",
        "barrier_pips",
        "regime_desc",
    ]
    if not schedule.empty:
        states = (
            schedule[state_cols]
            .drop_duplicates()
            .sort_values(["symbol", "bar_ticks", "horizon", "state_id"])
            .reset_index(drop=True)
        )
    else:
        states = pd.DataFrame(columns=state_cols)
    schedule.to_csv(out_sched, index=False)
    states.to_csv(out_state, index=False)
    monthly.to_csv(out_month, index=False)
    summary.to_csv(out_sum, index=False)
    churn_df.to_csv(out_churn, index=False)

    report_lines: list[str] = []
    report_lines.append(f"# {symbol} OCO Reduced-Core Rolling Selection")
    report_lines.append("")
    report_lines.append("## Setup")
    report_lines.append(f"- family_keep: `{family_keep}`")
    report_lines.append(f"- barrier_keep: `{sorted(barrier_keep)}`")
    report_lines.append(f"- horizon_keep: `{sorted(horizon_keep)}`")
    report_lines.append(f"- locked_quantile: `{q}`")
    report_lines.append(f"- selection_mode: `{selection_mode}`")
    report_lines.append(f"- execution_mode: `{exec_meta['mode']}`")
    if exec_meta["mode"] == "stop_limit":
        report_lines.append(f"- stop_limit_detail_csv: `{cfg.get('stop_limit_detail_csv')}`")
        report_lines.append(f"- stop_limit_cap_pips: `{cfg.get('stop_limit_cap_pips')}`")
        report_lines.append(f"- stop_limit_slippage_mode: `{cfg.get('stop_limit_slippage_mode')}`")
        report_lines.append(f"- stop_limit_match_rate: `{exec_meta.get('match_rate', np.nan):.6f}`")
        report_lines.append(
            f"- stop_limit_fill_rate_selected: `{exec_meta.get('fill_rate', np.nan):.6f}`"
        )
    report_lines.append(f"- state_train_months: `{state_train_months}`")
    report_lines.append(f"- min_train_months: `{min_train_months}`")
    report_lines.append(f"- overlap_corr_max: `{overlap_corr_max}`")
    report_lines.append(f"- overlap_divergence_max: `{overlap_divergence_max}`")
    report_lines.append(f"- max_state_churn: `{max_state_churn}`")
    report_lines.append(f"- max_top_state_share: `{max_top_state_share}`")
    report_lines.append(f"- max_state_hhi: `{max_state_hhi}`")
    report_lines.append(f"- enforce_state_stability_gates: `{enforce_state_stability_gates}`")
    report_lines.append(f"- max_states/min_states: `{max_states}/{min_states}`")
    report_lines.append(f"- strict_gate_only: `{strict_gate_only}`")
    report_lines.append("")
    report_lines.append("## Summary")
    report_lines.append(_table(summary))
    report_lines.append("")
    report_lines.append("## Reduced State Universe")
    report_lines.append(_table(states))
    report_lines.append("")
    report_lines.append("## Monthly Portfolio")
    report_lines.append(_table(monthly))
    report_lines.append("")
    report_lines.append("## State Stability")
    report_lines.append(_table(churn_df))
    report_lines.append("")
    report_lines.append("## State Schedule (Top Rows)")
    report_lines.append(_table(schedule.head(80)))
    report_lines.append("")

    report_out = Path(str(cfg["report_out"]))
    report_out.parent.mkdir(parents=True, exist_ok=True)
    report_out.write_text("\n".join(report_lines), encoding="utf-8")

    print(f"wrote: {out_sched}")
    print(f"wrote: {out_state}")
    print(f"wrote: {out_month}")
    print(f"wrote: {out_sum}")
    print(f"wrote: {out_churn}")
    print(f"wrote: {report_out}")
    return schedule, monthly, summary


def main() -> None:
    p = argparse.ArgumentParser(description="Leakage-safe rolling reduced-core OCO selector")
    p.add_argument("--config", default=None)
    p.add_argument("--symbol", default=None)
    p.add_argument("--candidate-csv", default=None)
    p.add_argument("--pred-path", default=None)
    p.add_argument("--family-keep", default=None)
    p.add_argument("--barrier-keep", default=None)
    p.add_argument("--horizon-keep", default=None)
    p.add_argument("--locked-quantile", type=float, default=None)
    p.add_argument("--selection-mode", default=None)
    p.add_argument("--execution-mode", default=None)
    p.add_argument("--stop-limit-detail-csv", default=None)
    p.add_argument("--stop-limit-cap-pips", type=float, default=None)
    p.add_argument("--stop-limit-slippage-mode", default=None)
    p.add_argument("--stop-limit-min-fill-rate", type=float, default=None)
    p.add_argument("--stop-limit-require-match-rate", type=float, default=None)
    p.add_argument("--state-train-months", type=int, default=None)
    p.add_argument("--min-train-months", type=int, default=None)
    p.add_argument("--overlap-corr-max", type=float, default=None)
    p.add_argument("--max-states", type=int, default=None)
    p.add_argument("--min-states", type=int, default=None)
    p.add_argument("--min-state-avg-rows", type=float, default=None)
    p.add_argument("--min-positive-months-train", type=int, default=None)
    p.add_argument("--strict-gate-only", default=None)
    p.add_argument("--overlap-divergence-max", type=float, default=None)
    p.add_argument("--require-lb95-trade-gt0", default=None)
    p.add_argument("--require-lb95-month-gt0", default=None)
    p.add_argument("--bootstrap-paths", type=int, default=None)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--capacity-floor-monthly", type=float, default=None)
    p.add_argument("--capacity-floor-annual", type=float, default=None)
    p.add_argument("--max-state-churn", type=float, default=None)
    p.add_argument("--max-top-state-share", type=float, default=None)
    p.add_argument("--max-state-hhi", type=float, default=None)
    p.add_argument("--enforce-state-stability-gates", default=None)
    p.add_argument("--out-state-schedule-csv", default=None)
    p.add_argument("--out-state-csv", default=None)
    p.add_argument("--out-monthly-csv", default=None)
    p.add_argument("--out-summary-csv", default=None)
    p.add_argument("--out-state-churn-csv", default=None)
    p.add_argument("--report-out", default=None)
    args = p.parse_args()

    cfg = _merge_config(args)
    for b in [
        "strict_gate_only",
        "require_lb95_trade_gt0",
        "require_lb95_month_gt0",
        "enforce_state_stability_gates",
    ]:
        if isinstance(cfg.get(b), str):
            cfg[b] = str(cfg[b]).strip().lower() in {"1", "true", "yes", "y"}
    run(cfg)


if __name__ == "__main__":
    main()
