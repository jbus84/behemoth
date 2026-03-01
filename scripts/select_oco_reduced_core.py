#!/usr/bin/env python3
"""Select a compact, justifiable OCO reduced core from full-cap WFO predictions."""

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
    "overlap_corr_max": 0.85,
    "max_states": 12,
    "min_states": 4,
    "min_state_avg_rows": 200,
    "min_positive_months": 8,
    "capacity_floor_monthly": 3000,
    "bootstrap_paths": 1200,
    "seed": 42,
    "out_state_csv": "data/analysis/tick_opportunity_mining/reduced_core/EURUSD_oco_reduced_states.csv",
    "out_monthly_csv": "data/analysis/tick_opportunity_mining/reduced_core/EURUSD_oco_reduced_monthly_gate.csv",
    "report_out": "docs/analysis/eurusd_oco_reduced_core_selection_report.md",
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
    if str(getattr(args, "config", "")).strip():
        cfg.update(_load_yaml(Path(str(args.config))))
    for k, v in vars(args).items():
        if k == "config":
            continue
        if v is not None:
            cfg[k] = v
    return cfg


def _bootstrap_lb95(vals: np.ndarray, *, paths: int, seed: int) -> float:
    x = np.asarray(vals, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) == 0 or int(paths) <= 0:
        return float("nan")
    rng = np.random.default_rng(int(seed))
    n = len(x)
    draws: list[np.ndarray] = []
    batch = 250
    for i in range(0, int(paths), batch):
        b = min(batch, int(paths) - i)
        idx = rng.integers(0, n, size=(b, n))
        draws.append(x[idx].mean(axis=1))
    m = np.concatenate(draws) if draws else np.array([], dtype=float)
    if len(m) == 0:
        return float("nan")
    return float(np.quantile(m, 0.05))


def _parse_candidate_uid(uid: str) -> tuple[str, str, int, int, str]:
    # library|symbol|bar_ticks|hX|state_id
    toks = str(uid).split("|", 4)
    if len(toks) != 5:
        raise ValueError(f"bad candidate_uid: {uid}")
    lib, symbol, bt, htxt, state_id = toks
    h = int(str(htxt).lstrip("hH"))
    return str(lib), str(symbol).upper(), int(bt), int(h), str(state_id)


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
    raise ValueError(f"cannot parse barrier_pips from row state_id={sid!r} regime_desc={txt!r}")


def _select_month_q(d: pd.DataFrame, q: float) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    for m, g in d.groupby("test_month", sort=True):
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


def run(cfg: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    symbol = str(cfg["symbol"]).upper().strip()
    family_keep = str(cfg["family_keep"]).strip()
    barrier_keep = set(_parse_floats(str(cfg["barrier_keep"])))
    horizon_keep = set(_parse_ints(str(cfg["horizon_keep"])))
    q = float(cfg["locked_quantile"])
    selection_mode = str(cfg.get("selection_mode", DEFAULTS["selection_mode"]))
    overlap_corr_max = float(cfg["overlap_corr_max"])
    max_states = int(cfg["max_states"])
    min_states = int(cfg["min_states"])
    min_state_avg_rows = float(cfg["min_state_avg_rows"])
    min_positive_months = int(cfg["min_positive_months"])
    bootstrap_paths = int(cfg["bootstrap_paths"])
    seed = int(cfg["seed"])

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
        raise RuntimeError("no predictions left after merging filtered candidate metadata")

    selected = _select_events(p, q=q, mode=selection_mode)
    if selected.empty:
        raise RuntimeError("selection empty (selection_mode/quantile)")

    state_group_cols = [
        "symbol",
        "bar_ticks",
        "horizon",
        "state_id",
        "family",
        "regime_desc",
        "barrier_pips",
    ]
    rows: list[dict[str, Any]] = []
    for i, (k, g) in enumerate(selected.groupby(state_group_cols, sort=False), start=1):
        mon = g.groupby("test_month", as_index=False).agg(
            rows=("target_gross_pips", "size"), mean_gross=("target_gross_pips", "mean")
        )
        gg = g["target_gross_pips"].to_numpy(dtype=float)
        mm = mon["mean_gross"].to_numpy(dtype=float)
        lb_t = _bootstrap_lb95(gg, paths=bootstrap_paths, seed=seed + i * 7)
        lb_m = _bootstrap_lb95(mm, paths=bootstrap_paths, seed=seed + i * 13)
        rows.append(
            {
                "symbol": k[0],
                "bar_ticks": int(k[1]),
                "horizon": int(k[2]),
                "state_id": str(k[3]),
                "family": str(k[4]),
                "regime_desc": str(k[5]),
                "barrier_pips": float(k[6]),
                "rows": int(len(g)),
                "months": int(mon["test_month"].nunique()),
                "avg_month_rows": float(mon["rows"].mean()),
                "mean_gross_pips": float(np.mean(gg)),
                "median_gross_pips": float(np.median(gg)),
                "pos_rate": float(np.mean(gg > 0.0)),
                "positive_months": int(np.sum(mm > 0.0)),
                "lb95_trade_mean_gross_pips": float(lb_t),
                "lb95_month_mean_gross_pips": float(lb_m),
            }
        )
    s = pd.DataFrame(rows)
    s["gate_pass"] = (
        (s["lb95_trade_mean_gross_pips"] > 0.0)
        & (s["lb95_month_mean_gross_pips"] > 0.0)
        & (s["positive_months"] >= int(min_positive_months))
        & (s["avg_month_rows"] >= float(min_state_avg_rows))
    )
    s = s.sort_values(
        [
            "gate_pass",
            "lb95_month_mean_gross_pips",
            "lb95_trade_mean_gross_pips",
            "mean_gross_pips",
            "avg_month_rows",
        ],
        ascending=[False, False, False, False, False],
    ).reset_index(drop=True)

    # Overlap pruning on monthly selected-row count vectors.
    piv = (
        selected.groupby(["state_id", "test_month"], as_index=False)
        .size()
        .pivot(index="state_id", columns="test_month", values="size")
        .fillna(0.0)
    )
    corr = piv.T.corr() if not piv.empty else pd.DataFrame()

    selected_ids: list[str] = []
    selected_corrmax: dict[str, float] = {}
    cand_order = s["state_id"].astype(str).tolist()
    pass_ids = set(s[s["gate_pass"]]["state_id"].astype(str).tolist())
    # Select from gate-pass states only. Fallback to non-pass only if
    # we cannot reach min_states.
    cand_order = [x for x in cand_order if x in pass_ids]
    if not cand_order:
        cand_order = s["state_id"].astype(str).tolist()
    for sid in cand_order:
        if len(selected_ids) >= int(max_states):
            break
        if sid in selected_ids:
            continue
        if not selected_ids:
            selected_ids.append(sid)
            selected_corrmax[sid] = 0.0
            continue
        cvals = [
            float(corr.loc[sid, t])
            for t in selected_ids
            if (sid in corr.index and t in corr.columns)
        ]
        cvals = [x for x in cvals if np.isfinite(x)]
        cmax = float(np.max(cvals)) if cvals else 0.0
        if cmax <= float(overlap_corr_max) or len(selected_ids) < int(min_states):
            selected_ids.append(sid)
            selected_corrmax[sid] = cmax
    if len(selected_ids) < int(min_states):
        for sid in s["state_id"].astype(str).tolist():
            if sid not in selected_ids:
                selected_ids.append(sid)
                selected_corrmax[sid] = float("nan")
            if len(selected_ids) >= int(min_states):
                break

    keep = s[s["state_id"].astype(str).isin(selected_ids)].copy()
    keep["selected_rank"] = (
        keep["state_id"].astype(str).map({sid: i + 1 for i, sid in enumerate(selected_ids)})
    )
    keep["overlap_corr_max"] = keep["state_id"].astype(str).map(selected_corrmax).fillna(np.nan)
    keep = keep.sort_values("selected_rank").reset_index(drop=True)

    # Portfolio monthly gate with reduced set at locked quantile.
    red = p[p["state_id"].astype(str).isin(set(keep["state_id"].astype(str)))].copy()
    month_rows: list[dict[str, Any]] = []
    for m, g in red.groupby("test_month", sort=True):
        x = _select_events(g, q=q, mode=selection_mode)
        gg = x["target_gross_pips"].to_numpy(dtype=float)
        month_rows.append(
            {
                "test_month": str(m),
                "rows": int(len(x)),
                "mean_gross_pips": float(np.mean(gg)) if len(gg) else float("nan"),
                "median_gross_pips": float(np.median(gg)) if len(gg) else float("nan"),
                "pos_rate": float(np.mean(gg > 0.0)) if len(gg) else float("nan"),
                "threshold": float(
                    pd.to_numeric(
                        x.get("threshold", pd.Series(dtype=float)), errors="coerce"
                    ).mean()
                )
                if ("threshold" in x.columns and len(x))
                else float("nan"),
            }
        )
    monthly = pd.DataFrame(month_rows).sort_values("test_month").reset_index(drop=True)
    avg_rows = float(monthly["rows"].mean()) if not monthly.empty else 0.0
    monthly_positive = int((monthly["mean_gross_pips"] > 0.0).sum()) if not monthly.empty else 0
    capacity_pass = avg_rows >= float(cfg["capacity_floor_monthly"])

    out_state_csv = Path(str(cfg["out_state_csv"]))
    out_state_csv.parent.mkdir(parents=True, exist_ok=True)
    keep.to_csv(out_state_csv, index=False)
    out_monthly_csv = Path(str(cfg["out_monthly_csv"]))
    out_monthly_csv.parent.mkdir(parents=True, exist_ok=True)
    monthly.to_csv(out_monthly_csv, index=False)

    lines: list[str] = []
    lines.append("# EURUSD OCO Reduced-Core Selection")
    lines.append("")
    lines.append("## Setup")
    lines.append(f"- family_keep: `{family_keep}`")
    lines.append(f"- barrier_keep: `{sorted(barrier_keep)}`")
    lines.append(f"- horizon_keep: `{sorted(horizon_keep)}`")
    lines.append(f"- locked_quantile: `{q}`")
    lines.append(f"- selection_mode: `{selection_mode}`")
    lines.append(f"- overlap_corr_max: `{overlap_corr_max}`")
    lines.append(f"- max_states: `{max_states}`")
    lines.append(f"- min_states: `{min_states}`")
    lines.append("")
    lines.append("## Selected States")
    lines.append(keep.to_markdown(index=False) if not keep.empty else "_empty_")
    lines.append("")
    lines.append("## Reduced Portfolio Monthly")
    lines.append(monthly.to_markdown(index=False) if not monthly.empty else "_empty_")
    lines.append("")
    lines.append("## Reduced Portfolio Gate")
    lines.append(f"- avg_month_rows: `{avg_rows:.2f}`")
    lines.append(f"- monthly_positive_count: `{monthly_positive}`")
    lines.append(f"- capacity_floor_monthly: `{float(cfg['capacity_floor_monthly']):.2f}`")
    lines.append(f"- capacity_pass: `{capacity_pass}`")
    lines.append("")
    report_out = Path(str(cfg["report_out"]))
    report_out.parent.mkdir(parents=True, exist_ok=True)
    report_out.write_text("\n".join(lines), encoding="utf-8")

    print(f"wrote: {out_state_csv}")
    print(f"wrote: {out_monthly_csv}")
    print(f"wrote: {report_out}")
    return keep, monthly


def main() -> None:
    p = argparse.ArgumentParser(description="Select reduced, overlap-controlled OCO core")
    p.add_argument("--config", default=None)
    p.add_argument("--symbol", default=None)
    p.add_argument("--candidate-csv", default=None)
    p.add_argument("--pred-path", default=None)
    p.add_argument("--family-keep", default=None)
    p.add_argument("--barrier-keep", default=None)
    p.add_argument("--horizon-keep", default=None)
    p.add_argument("--locked-quantile", type=float, default=None)
    p.add_argument("--selection-mode", default=None)
    p.add_argument("--overlap-corr-max", type=float, default=None)
    p.add_argument("--max-states", type=int, default=None)
    p.add_argument("--min-states", type=int, default=None)
    p.add_argument("--min-state-avg-rows", type=float, default=None)
    p.add_argument("--min-positive-months", type=int, default=None)
    p.add_argument("--capacity-floor-monthly", type=float, default=None)
    p.add_argument("--bootstrap-paths", type=int, default=None)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--out-state-csv", default=None)
    p.add_argument("--out-monthly-csv", default=None)
    p.add_argument("--report-out", default=None)
    args = p.parse_args()
    cfg = _merge_config(args)
    run(cfg)


if __name__ == "__main__":
    main()
