#!/usr/bin/env python3
"""Select directional states with strict rolling month-by-month selection.

Simplified from OCO reduced-core rolling:
- No stop-limit execution mode
- No barrier filtering
- No overlap correlation / divergence checks
- No max_states/min_states or stability gates
- family_keep optional (empty = keep all families)
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
    "candidate_csv": "data/analysis/tick_opportunity_mining/EURUSD_directional_candidates.csv",
    "pred_path": "data/analysis/tick_opportunity_mining/wfo_m3to1_directional_fullcap/EURUSD_directional_monthly_predictions.parquet",
    "family_keep": "",
    "horizon_keep": "5,6",
    "locked_quantile": 0.9,
    "state_train_months": 2,
    "min_train_months": 1,
    "min_state_avg_rows": 20.0,
    "min_positive_months_train": 1,
    "require_lb95_trade_gt0": True,
    "bootstrap_paths": 1000,
    "seed": 42,
    "capacity_floor_monthly": 200.0,
    "capacity_floor_annual": 500.0,
    "out_state_schedule_csv": "data/analysis/tick_opportunity_mining/directional_rolling/EURUSD_directional_state_schedule.csv",
    "out_monthly_csv": "data/analysis/tick_opportunity_mining/directional_rolling/EURUSD_directional_monthly.csv",
    "out_summary_csv": "data/analysis/tick_opportunity_mining/directional_rolling/EURUSD_directional_summary.csv",
    "report_out": "docs/analysis/eurusd_directional_reduced_rolling_report.md",
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
    try:
        bar_ticks = int(bt)
        horizon = int(str(htxt).lstrip("hH"))
    except ValueError:
        return "", "", -1, -1, uid
    return str(lib), str(symbol).upper(), bar_ticks, horizon, str(state_id)


def _select_month_q(d: pd.DataFrame, q: float) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    for _, g in d.groupby("test_month", sort=True):
        thr = float(np.quantile(g["pred_prob"].to_numpy(dtype=float), float(q)))
        x = g[g["pred_prob"] >= thr].copy()
        x["threshold"] = float(thr)
        parts.append(x)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


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


NO_TRADE_STATE_COLS = [
    "symbol", "bar_ticks", "horizon", "state_id", "family",
    "regime_desc",
]


def _write_no_trade_outputs(
    cfg: dict[str, Any], symbol: str, reason: str
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    schedule = pd.DataFrame(columns=NO_TRADE_STATE_COLS)
    monthly = pd.DataFrame()
    summary = pd.DataFrame([{"symbol": symbol, "status": "NO_TRADE", "reason": reason}])

    out_sched = Path(str(cfg["out_state_schedule_csv"]))
    out_month = Path(str(cfg["out_monthly_csv"]))
    out_sum = Path(str(cfg["out_summary_csv"]))
    for path in (out_sched, out_month, out_sum):
        path.parent.mkdir(parents=True, exist_ok=True)
    schedule.to_csv(out_sched, index=False)
    monthly.to_csv(out_month, index=False)
    summary.to_csv(out_sum, index=False)

    out_states = out_sched.with_name(
        out_sched.name.replace("_state_schedule.csv", "_states.csv")
    )
    out_states.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(columns=NO_TRADE_STATE_COLS).to_csv(out_states, index=False)

    report_out = Path(str(cfg["report_out"]))
    report_out.parent.mkdir(parents=True, exist_ok=True)
    report_out.write_text(
        f"# {symbol} Directional Rolling Selection\n\n"
        f"## Outcome: NO_TRADE\n\n{reason}\n",
        encoding="utf-8",
    )
    print(f"no-trade: {symbol} — {reason}")
    for path in (out_sched, out_states, out_month, out_sum, report_out):
        print(f"wrote: {path}")
    return schedule, monthly, summary


def run(cfg: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    symbol = str(cfg["symbol"]).upper().strip()
    family_keep = {f.strip() for f in str(cfg.get("family_keep", "")).split(",") if f.strip()}
    horizon_keep = set(_parse_ints(str(cfg["horizon_keep"])))
    q = float(cfg["locked_quantile"])
    state_train_months = int(cfg["state_train_months"])
    min_train_months = int(cfg["min_train_months"])
    min_state_avg_rows = float(cfg["min_state_avg_rows"])
    min_positive_months_train = int(cfg["min_positive_months_train"])
    require_lb95_trade_gt0 = bool(cfg["require_lb95_trade_gt0"])
    bootstrap_paths = int(cfg["bootstrap_paths"])
    seed = int(cfg["seed"])
    capacity_floor_monthly = float(cfg["capacity_floor_monthly"])
    capacity_floor_annual = float(cfg["capacity_floor_annual"])

    try:
        c = pd.read_csv(str(cfg["candidate_csv"])).copy()
    except (pd.errors.EmptyDataError, FileNotFoundError, OSError):
        c = pd.DataFrame()
    try:
        p = pd.read_parquet(str(cfg["pred_path"])).copy()
    except Exception:
        # Empty/malformed parquet from upstream ML pipeline = no-trade condition
        p = pd.DataFrame()
    raw_candidates_empty = c.empty
    raw_predictions_empty = p.empty

    if raw_candidates_empty or raw_predictions_empty:
        out_sched = Path(str(cfg["out_state_schedule_csv"]))
        out_month = Path(str(cfg["out_monthly_csv"]))
        out_sum = Path(str(cfg["out_summary_csv"]))
        for path in (out_sched, out_month, out_sum):
            path.parent.mkdir(parents=True, exist_ok=True)

        schedule_empty = pd.DataFrame(columns=NO_TRADE_STATE_COLS)
        monthly_empty = pd.DataFrame()
        _reason = (
            "No candidates available"
            if raw_candidates_empty and raw_predictions_empty
            else "No predictions available"
            if raw_predictions_empty
            else "No candidates available"
        )
        summary_empty = pd.DataFrame([{"symbol": symbol, "status": "NO_TRADE", "reason": _reason}])

        schedule_empty.to_csv(out_sched, index=False)
        monthly_empty.to_csv(out_month, index=False)
        summary_empty.to_csv(out_sum, index=False)

        print(f"wrote: {out_sched}")
        print(f"wrote: {out_month}")
        print(f"wrote: {out_sum}")

        report_out = Path(str(cfg["report_out"]))
        report_out.parent.mkdir(parents=True, exist_ok=True)
        report_out.write_text(
            f"# {symbol} Directional Rolling Selection\n\n"
            f"## Outcome: NO_TRADE\n\n"
            f"{_reason}\n",
            encoding="utf-8",
        )
        print(f"wrote: {report_out}")
        return schedule_empty, monthly_empty, summary_empty

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
    p = p[(p["library"] == "directional") & (p["symbol"] == symbol)].copy()
    p["test_month"] = p["test_month"].astype(str)

    c["symbol"] = c["symbol"].astype(str).str.upper()
    c["bar_ticks"] = pd.to_numeric(c["bar_ticks"], errors="coerce").astype("Int64")
    c["horizon"] = pd.to_numeric(c["horizon"], errors="coerce").astype("Int64")
    c = c[
        (c["symbol"] == symbol)
        & (c["horizon"].isin(list(horizon_keep)))
    ].copy()
    if family_keep:
        c = c[c["family"].astype(str).isin(family_keep)].copy()

    if c.empty:
        if raw_candidates_empty:
            return _write_no_trade_outputs(
                cfg, symbol, "candidate CSV is empty — nothing mined"
            )
        raise RuntimeError(
            "candidate filter empty: candidate CSV has rows but none match "
            f"family_keep={sorted(family_keep)!r} / horizon_keep — "
            "config mismatch, not a no-trade outcome"
        )

    key_cols = ["symbol", "bar_ticks", "horizon", "state_id"]
    meta_cols = key_cols + ["family", "regime_desc"]
    c_meta = c[meta_cols].drop_duplicates()
    p = p.merge(c_meta, on=key_cols, how="inner")
    if p.empty:
        if raw_predictions_empty:
            return _write_no_trade_outputs(
                cfg, symbol, "predictions parquet is empty — WFO produced no rows"
            )
        raise RuntimeError(
            "no predictions left after candidate metadata merge: predictions "
            "parquet has rows but none join the candidate universe — stale or "
            "mismatched predictions, not a no-trade outcome"
        )

    selected_all = _select_month_q(p, q=q)
    if selected_all.empty:
        return _write_no_trade_outputs(
            cfg, symbol,
            "no candidate cleared the selection quantile — true negative",
        )
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
                    "mean_gross_pips": np.nan,
                    "mean_signal_pips": np.nan,
                    "median_gross_pips": np.nan,
                    "pos_rate": np.nan,
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
                    "mean_gross_pips": np.nan,
                    "mean_signal_pips": np.nan,
                    "median_gross_pips": np.nan,
                    "pos_rate": np.nan,
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
        ]
        state_rows: list[dict[str, Any]] = []
        for j, (k, g) in enumerate(train.groupby(state_group_cols, sort=False), start=1):
            mon = g.groupby("test_month", as_index=False).agg(
                signal_rows=("target_gross_pips", "size"),
                mean_signal=("target_gross_pips", "mean"),
            )
            gg = pd.to_numeric(g["target_gross_pips"], errors="coerce").to_numpy(dtype=float)
            mm = mon["mean_signal"].to_numpy(dtype=float)
            lb_t = _bootstrap_lb95(gg, paths=bootstrap_paths, seed=seed + i * 1000 + j * 7)

            gate = True
            if require_lb95_trade_gt0:
                gate = gate and (lb_t > 0.0)
            gate = gate and (float(mon["signal_rows"].mean()) >= min_state_avg_rows)
            gate = gate and (int(np.sum(mm > 0.0)) >= min_positive_months_train)

            state_rows.append(
                {
                    "symbol": k[0],
                    "bar_ticks": int(k[1]),
                    "horizon": int(k[2]),
                    "state_id": str(k[3]),
                    "family": str(k[4]),
                    "regime_desc": str(k[5]),
                    "train_rows": int(len(g)),
                    "train_months_count": int(mon["test_month"].nunique()),
                    "train_avg_month_rows": float(mon["signal_rows"].mean()),
                    "train_mean_gross_pips": float(np.mean(gg)) if len(gg) else np.nan,
                    "train_median_gross_pips": float(np.median(gg)) if len(gg) else np.nan,
                    "train_pos_rate": float(np.mean(gg > 0.0)) if len(gg) else np.nan,
                    "train_positive_months": int(np.sum(mm > 0.0)),
                    "train_lb95_trade_mean_gross_pips": float(lb_t),
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
                    "mean_gross_pips": np.nan,
                    "mean_signal_pips": np.nan,
                    "median_gross_pips": np.nan,
                    "pos_rate": np.nan,
                    "status": "no_states",
                }
            )
            continue

        s = s.sort_values(
            [
                "gate_pass",
                "train_lb95_trade_mean_gross_pips",
                "train_mean_gross_pips",
                "train_avg_month_rows",
            ],
            ascending=[False, False, False, False],
        ).reset_index(drop=True)
        s["state_key"] = (
            s["state_id"].astype(str)
            + "|"
            + pd.to_numeric(s["bar_ticks"], errors="coerce").fillna(-1).astype(int).astype(str)
            + "|"
            + pd.to_numeric(s["horizon"], errors="coerce").fillna(-1).astype(int).astype(str)
        )

        pass_keys = set(s[s["gate_pass"]]["state_key"].astype(str).tolist())
        if not pass_keys:
            monthly_rows.append(
                {
                    "symbol": symbol,
                    "test_month": str(month),
                    "train_months": ",".join(train_months),
                    "states_selected": 0,
                    "rows": 0,
                    "signal_rows": 0,
                    "mean_gross_pips": np.nan,
                    "mean_signal_pips": np.nan,
                    "median_gross_pips": np.nan,
                    "pos_rate": np.nan,
                    "status": "no_gate_states",
                }
            )
            continue

        selected_state_df = s[s["state_key"].astype(str).isin(pass_keys)].copy()
        selected_state_df["selected_rank"] = np.arange(1, len(selected_state_df) + 1)

        test = selected_all[
            (selected_all["test_month"] == str(month))
            & (selected_all["state_key"].astype(str).isin(pass_keys))
        ].copy()
        trd = pd.to_numeric(test["target_gross_pips"], errors="coerce").to_numpy(dtype=float)
        signal_rows = int(len(test))
        mean_gross = float(np.mean(trd)) if len(trd) else np.nan
        mean_signal = float(np.mean(trd)) if len(trd) else np.nan
        median_gross = float(np.median(trd)) if len(trd) else np.nan
        pos_rate = float(np.mean(trd > 0.0)) if len(trd) else np.nan

        monthly_rows.append(
            {
                "symbol": symbol,
                "test_month": str(month),
                "train_months": ",".join(train_months),
                "states_selected": int(len(pass_keys)),
                "rows": int(signal_rows),
                "signal_rows": int(signal_rows),
                "mean_gross_pips": float(mean_gross),
                "mean_signal_pips": float(mean_signal),
                "median_gross_pips": float(median_gross),
                "pos_rate": float(pos_rate),
                "status": "ok" if signal_rows > 0 else "no_test_rows",
            }
        )

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
                    "train_rows": int(r["train_rows"]),
                    "train_months_count": int(r["train_months_count"]),
                    "train_avg_month_rows": float(r["train_avg_month_rows"]),
                    "train_mean_gross_pips": float(r["train_mean_gross_pips"])
                    if np.isfinite(r["train_mean_gross_pips"])
                    else np.nan,
                    "train_median_gross_pips": float(r["train_median_gross_pips"])
                    if np.isfinite(r["train_median_gross_pips"])
                    else np.nan,
                    "train_pos_rate": float(r["train_pos_rate"])
                    if np.isfinite(r["train_pos_rate"])
                    else np.nan,
                    "train_positive_months": int(r["train_positive_months"]),
                    "train_lb95_trade_mean_gross_pips": float(
                        r["train_lb95_trade_mean_gross_pips"]
                    ),
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
    overall_lb95_month = (
        _bootstrap_lb95(ok_vals, paths=bootstrap_paths, seed=seed + 999) if len(ok_vals) else np.nan
    )
    annualized_rows = _annualized_from_monthly_rows(ok)
    avg_month_rows = (
        float(pd.to_numeric(ok["rows"], errors="coerce").mean()) if not ok.empty else 0.0
    )

    summary = pd.DataFrame(
        [
            {
                "symbol": symbol,
                "locked_quantile": q,
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
                "positive_months": int(np.nansum(ok_vals > 0.0)) if len(ok_vals) else 0,
                "avg_month_rows": float(avg_month_rows),
                "annualized_rows": float(annualized_rows),
                "capacity_floor_monthly": capacity_floor_monthly,
                "capacity_floor_annual": capacity_floor_annual,
                "capacity_pass_monthly_or_annual": bool(
                    (avg_month_rows >= capacity_floor_monthly)
                    or (annualized_rows >= capacity_floor_annual)
                ),
            }
        ]
    )

    out_sched = Path(str(cfg["out_state_schedule_csv"]))
    out_month = Path(str(cfg["out_monthly_csv"]))
    out_sum = Path(str(cfg["out_summary_csv"]))
    for path in (out_sched, out_month, out_sum):
        path.parent.mkdir(parents=True, exist_ok=True)

    state_cols = ["symbol", "bar_ticks", "horizon", "state_id", "family", "regime_desc"]
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
    states.to_csv(out_sched.with_name(out_sched.name.replace("_state_schedule.csv", "_states.csv")), index=False)
    monthly.to_csv(out_month, index=False)
    summary.to_csv(out_sum, index=False)

    report_lines: list[str] = []
    report_lines.append(f"# {symbol} Directional Rolling Selection")
    report_lines.append("")
    report_lines.append("## Setup")
    report_lines.append(f"- family_keep: `{','.join(sorted(family_keep)) or '(all)'}`")
    report_lines.append(f"- horizon_keep: `{sorted(horizon_keep)}`")
    report_lines.append(f"- locked_quantile: `{q}`")
    report_lines.append(f"- state_train_months: `{state_train_months}`")
    report_lines.append(f"- min_train_months: `{min_train_months}`")
    report_lines.append(f"- min_state_avg_rows: `{min_state_avg_rows}`")
    report_lines.append(f"- min_positive_months_train: `{min_positive_months_train}`")
    report_lines.append(f"- require_lb95_trade_gt0: `{require_lb95_trade_gt0}`")
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
    report_lines.append("## State Schedule (Top Rows)")
    report_lines.append(_table(schedule.head(80)))
    report_lines.append("")

    report_out = Path(str(cfg["report_out"]))
    report_out.parent.mkdir(parents=True, exist_ok=True)
    report_out.write_text("\n".join(report_lines), encoding="utf-8")

    print(f"wrote: {out_sched}")
    print(f"wrote: {out_month}")
    print(f"wrote: {out_sum}")
    print(f"wrote: {report_out}")
    return schedule, monthly, summary


def main() -> None:
    p = argparse.ArgumentParser(description="Leakage-safe rolling directional selector")
    p.add_argument("--config", default=None)
    p.add_argument("--symbol", default=None)
    p.add_argument("--candidate-csv", default=None)
    p.add_argument("--pred-path", default=None)
    p.add_argument("--family-keep", default=None)
    p.add_argument("--horizon-keep", default=None)
    p.add_argument("--locked-quantile", type=float, default=None)
    p.add_argument("--state-train-months", type=int, default=None)
    p.add_argument("--min-train-months", type=int, default=None)
    p.add_argument("--min-state-avg-rows", type=float, default=None)
    p.add_argument("--min-positive-months-train", type=int, default=None)
    p.add_argument("--require-lb95-trade-gt0", default=None)
    p.add_argument("--bootstrap-paths", type=int, default=None)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--capacity-floor-monthly", type=float, default=None)
    p.add_argument("--capacity-floor-annual", type=float, default=None)
    p.add_argument("--out-state-schedule-csv", default=None)
    p.add_argument("--out-monthly-csv", default=None)
    p.add_argument("--out-summary-csv", default=None)
    p.add_argument("--report-out", default=None)
    args = p.parse_args()

    cfg = _merge_config(args)
    for b in [
        "require_lb95_trade_gt0",
    ]:
        if isinstance(cfg.get(b), str):
            cfg[b] = str(cfg[b]).strip().lower() in {"1", "true", "yes", "y"}
    run(cfg)


if __name__ == "__main__":
    main()
