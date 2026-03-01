#!/usr/bin/env python3
"""Build canonical OCO rolling strategy bible generated documentation artifacts."""

from __future__ import annotations

import argparse
import glob
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

DEFAULT_MANIFEST = Path("configs/research/docs/oco_bible_manifest.yaml")
DETAIL_MAX_ROWS_DEFAULT = 40
REPO_ROOT = Path.cwd().resolve()


@dataclass(frozen=True)
class BuildOutputs:
    generated_dir: Path
    figures_dir: Path
    build_report_csv: Path
    symbol_snapshot_csv: Path
    stage_status_csv: Path
    stage_metrics_csv: Path
    edge_clarity_stage_metrics_csv: Path
    edge_clarity_state_contrib_csv: Path
    edge_clarity_threshold_robustness_csv: Path
    edge_clarity_report_md: Path


REQUIRED_SYMBOL_KEYS = {
    "symbol",
    "reduced_summary_csv",
    "tick_exact_summary_csv",
    "robustness_summary_csv",
    "stop_limit_summary_csv",
    "mining_report_md",
    "wfo_report_md",
    "reduced_core_report_md",
    "tick_exact_report_md",
}


def _parse_bool(raw: str) -> bool:
    return str(raw).strip().lower() in {"1", "true", "yes", "y"}


def _to_repo_rel(raw: Any) -> str:
    s = str(raw).strip()
    if not s:
        return ""
    p = Path(s)
    try:
        abs_p = p.resolve() if p.is_absolute() else (REPO_ROOT / p).resolve()
        try:
            return abs_p.relative_to(REPO_ROOT).as_posix()
        except ValueError:
            return abs_p.as_posix()
    except Exception:
        return s.replace("\\", "/")


def _table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_empty_"
    try:
        return df.to_markdown(index=False)
    except Exception:
        cols = [str(c) for c in df.columns.tolist()]
        head = "| " + " | ".join(cols) + " |"
        sep = "|" + "|".join([" --- " for _ in cols]) + "|"
        body: list[str] = []
        for _, row in df.iterrows():
            vals: list[str] = []
            for c in cols:
                v = row.get(c, "")
                if pd.isna(v):
                    vals.append("")
                else:
                    vals.append(str(v))
            body.append("| " + " | ".join(vals) + " |")
        return "\n".join([head, sep] + body)


def _resolve_path(base: Path, raw: str) -> Path:
    p = Path(str(raw))
    if p.is_absolute():
        return p
    # Prefer repository-root-relative paths (cwd), then fall back to manifest-relative paths.
    p_cwd = (Path.cwd() / p).resolve()
    if p_cwd.exists():
        return p_cwd
    return (base / p).resolve()


def _resolve_output_path(raw: str) -> Path:
    p = Path(str(raw))
    if p.is_absolute():
        return p
    return (Path.cwd() / p).resolve()


def _require_manifest_keys(cfg: dict[str, Any]) -> None:
    required_root = {"title", "outputs", "symbols", "audit"}
    missing = sorted(k for k in required_root if k not in cfg)
    if missing:
        raise ValueError(f"manifest missing root keys: {missing}")

    outputs = cfg.get("outputs")
    if not isinstance(outputs, dict):
        raise ValueError("manifest outputs must be a mapping")
    for k in [
        "generated_dir",
        "figures_dir",
        "build_report_csv",
        "symbol_snapshot_csv",
        "stage_status_csv",
    ]:
        if k not in outputs:
            raise ValueError(f"manifest outputs missing key: {k}")

    symbols = cfg.get("symbols")
    if not isinstance(symbols, list) or not symbols:
        raise ValueError("manifest symbols must be a non-empty list")
    for i, entry in enumerate(symbols):
        if not isinstance(entry, dict):
            raise ValueError(f"manifest symbols[{i}] must be a mapping")
        missing_symbol = sorted(REQUIRED_SYMBOL_KEYS - set(entry.keys()))
        if missing_symbol:
            raise ValueError(f"manifest symbols[{i}] missing keys: {missing_symbol}")

    audit = cfg.get("audit")
    if not isinstance(audit, dict):
        raise ValueError("manifest audit must be a mapping")
    for k in ["checks_csv", "issues_csv", "report_md"]:
        if k not in audit:
            raise ValueError(f"manifest audit missing key: {k}")


def _load_manifest(path: Path) -> tuple[dict[str, Any], Path]:
    if not path.exists():
        raise FileNotFoundError(path)
    obj = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("manifest root must be a mapping")
    _require_manifest_keys(obj)
    return obj, path.parent.resolve()


def _artifact_rows(cfg: dict[str, Any], base_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for entry in cfg["symbols"]:
        symbol = str(entry["symbol"]).upper().strip()
        for k in sorted(REQUIRED_SYMBOL_KEYS - {"symbol"}):
            p = _resolve_path(base_dir, str(entry[k]))
            rows.append(
                {
                    "group": "symbol",
                    "symbol": symbol,
                    "artifact": k,
                    "path": _to_repo_rel(p),
                    "exists": p.exists(),
                    "required": True,
                }
            )

    audit = cfg["audit"]
    for k in ["checks_csv", "issues_csv", "report_md"]:
        p = _resolve_path(base_dir, str(audit[k]))
        rows.append(
            {
                "group": "audit",
                "symbol": "ALL",
                "artifact": k,
                "path": _to_repo_rel(p),
                "exists": p.exists(),
                "required": True,
            }
        )

    for raw in cfg.get("required_artifacts", []):
        p = _resolve_path(base_dir, str(raw))
        rows.append(
            {
                "group": "required_artifacts",
                "symbol": "ALL",
                "artifact": "required_artifact",
                "path": _to_repo_rel(p),
                "exists": p.exists(),
                "required": True,
            }
        )
    return rows


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)


def _read_symbol_row(path: Path, symbol: str) -> pd.Series:
    df = _read_csv(path)
    if df.empty:
        raise ValueError(f"empty csv: {path}")
    if "symbol" in df.columns:
        pick = df[df["symbol"].astype(str).str.upper() == str(symbol).upper()].copy()
        if not pick.empty:
            return pick.iloc[0]
    return df.iloc[0]


def _read_robustness_row(path: Path, quantile: float | None) -> pd.Series:
    df = _read_csv(path)
    if df.empty:
        raise ValueError(f"empty csv: {path}")
    if "quantile" in df.columns and quantile is not None:
        qcol = pd.to_numeric(df["quantile"], errors="coerce")
        m = qcol == float(quantile)
        if m.any():
            return df.loc[m].iloc[0]
    if "quantile" in df.columns:
        qcol = pd.to_numeric(df["quantile"], errors="coerce")
        if qcol.notna().any():
            return df.iloc[int(qcol.fillna(-1).to_numpy().argmax())]
    return df.iloc[0]


def _num(v: Any) -> float:
    try:
        x = float(v)
    except Exception:
        return float("nan")
    return x


def _safe_div(a: float, b: float) -> float:
    if not (math.isfinite(a) and math.isfinite(b)) or b == 0.0:
        return float("nan")
    return a / b


def _max_survivable_cost_from_costplus_cols(
    row: dict[str, Any] | pd.Series,
    *,
    prefix: str = "lb95_trade_mean_net_pips_costplus_",
) -> float:
    pairs: list[tuple[float, float]] = []
    keys = list(row.index) if isinstance(row, pd.Series) else list(row.keys())
    for c in keys:
        name = str(c)
        if not name.startswith(prefix):
            continue
        lvl = _num(name.replace(prefix, ""))
        val = _num(row.get(c))
        if math.isfinite(lvl) and math.isfinite(val):
            pairs.append((lvl, val))
    if not pairs:
        return float("nan")
    pairs = sorted(pairs, key=lambda x: x[0])
    if all(y > 0.0 for _, y in pairs):
        return float(pairs[-1][0])
    if all(y <= 0.0 for _, y in pairs):
        return 0.0
    for j in range(1, len(pairs)):
        lo_c, lo_y = pairs[j - 1]
        hi_c, hi_y = pairs[j]
        if lo_y > 0.0 and hi_y <= 0.0:
            if abs(float(hi_y) - float(lo_y)) <= 1e-12:
                return float(hi_c)
            frac = (0.0 - float(lo_y)) / (float(hi_y) - float(lo_y))
            cross = float(lo_c) + float(frac) * (float(hi_c) - float(lo_c))
            return float(min(max(cross, float(lo_c)), float(hi_c)))
    return float(pairs[-1][0])


def _session_bucket(hour_utc: Any) -> str:
    h = int(_num(hour_utc))
    if 0 <= h <= 7:
        return "ASIA"
    if 8 <= h <= 12:
        return "LONDON"
    if 13 <= h <= 21:
        return "NY"
    return "LATE"


def _rolling_session_cap_table(
    detail: pd.DataFrame,
    *,
    symbol: str,
    lookback_days: int = 20,
    cap_quantile: float = 0.90,
    min_periods: int = 200,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply causal rolling overshoot caps by session and return enriched detail + policy rows."""
    required = {"touch_open_ts", "overshoot_tick_pips"}
    if detail.empty or not required.issubset(set(detail.columns)):
        return pd.DataFrame(), pd.DataFrame()

    d = detail.copy()
    d["touch_open_ts"] = pd.to_datetime(d["touch_open_ts"], utc=True, errors="coerce")
    d["overshoot_tick_pips"] = pd.to_numeric(d["overshoot_tick_pips"], errors="coerce")
    d = (
        d.dropna(subset=["touch_open_ts", "overshoot_tick_pips"])
        .sort_values("touch_open_ts")
        .reset_index(drop=True)
    )
    if d.empty:
        return pd.DataFrame(), pd.DataFrame()
    d["session_bucket"] = d["touch_open_ts"].dt.hour.map(_session_bucket)

    horizon = f"{int(max(lookback_days, 1))}D"
    parts: list[pd.DataFrame] = []
    for sess, g in d.groupby("session_bucket", sort=False):
        gg = (
            g[["touch_open_ts", "overshoot_tick_pips"]]
            .copy()
            .sort_values("touch_open_ts")
            .set_index("touch_open_ts")
        )
        cap_s = (
            gg["overshoot_tick_pips"]
            .rolling(horizon, min_periods=max(int(min_periods), 1))
            .quantile(float(cap_quantile))
            .shift(1)
        )
        out = g.copy()
        out["cap_session_pips"] = cap_s.values
        out["session_bucket"] = sess
        parts.append(out)
    d2 = pd.concat(parts, ignore_index=True).sort_values("touch_open_ts").reset_index(drop=True)

    gg = d2[["touch_open_ts", "overshoot_tick_pips"]].copy().set_index("touch_open_ts")
    d2["cap_global_pips"] = (
        gg["overshoot_tick_pips"]
        .rolling(horizon, min_periods=max(int(min_periods), 1))
        .quantile(float(cap_quantile))
        .shift(1)
        .values
    )
    fallback_cap = _num(d2["overshoot_tick_pips"].quantile(float(cap_quantile)))
    d2["cap_applied_pips"] = (
        d2["cap_session_pips"].fillna(d2["cap_global_pips"]).fillna(fallback_cap)
    )
    d2["cap_source"] = np.where(
        d2["cap_session_pips"].notna(),
        "session",
        np.where(d2["cap_global_pips"].notna(), "global", "fallback"),
    )
    d2["overshoot_capped_pips"] = np.minimum(d2["overshoot_tick_pips"], d2["cap_applied_pips"])

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    policy_rows: list[dict[str, Any]] = []
    for sess, g in d2.groupby("session_bucket", sort=True):
        cap_last = (
            _num(g["cap_applied_pips"].dropna().iloc[-1])
            if g["cap_applied_pips"].notna().any()
            else fallback_cap
        )
        policy_rows.append(
            {
                "symbol": str(symbol).upper(),
                "session_bucket": str(sess),
                "lookback_days": int(lookback_days),
                "cap_quantile": float(cap_quantile),
                "cap_pips": cap_last,
                "rows_used": int(len(g)),
                "session_cap_rows": int(g["cap_session_pips"].notna().sum()),
                "global_cap_rows": int(
                    g["cap_session_pips"].isna().sum()
                    - ((g["cap_session_pips"].isna()) & (g["cap_global_pips"].isna())).sum()
                ),
                "fallback_rows": int(
                    ((g["cap_session_pips"].isna()) & (g["cap_global_pips"].isna())).sum()
                ),
                "generated_at_utc": now_utc,
            }
        )
    policy = pd.DataFrame(policy_rows)
    return d2, policy


STAGE04_ALLOWED_ACTION_CODES = {
    "A0_MONITOR",
    "A1_RECALIBRATE_CAP",
    "A2_SESSION_GUARD",
    "A3_HALT_RECALIBRATE",
    "A9_DATA_GAP",
}


def _stage04_policy_for_metric(metric_id: str, metric_value: Any) -> dict[str, Any]:
    m_id = str(metric_id)
    val = _num(metric_value)
    if not math.isfinite(val):
        return {
            "metric_id": m_id,
            "metric_value": float("nan"),
            "direction": "na",
            "band": "unknown",
            "action_code": "A9_DATA_GAP",
            "action_summary": "missing metric value; regenerate Stage 04 artifacts before deployment",
            "green_threshold": "",
            "amber_threshold": "",
        }

    rules: dict[str, dict[str, Any]] = {
        "E11_session_overshoot_dispersion": {
            "direction": "lower_better",
            "green_max": 1.00,
            "amber_max": 1.30,
            "amber_action": "A2_SESSION_GUARD",
            "amber_summary": "session overshoot uneven; add session guard and re-check E11",
            "red_action": "A3_HALT_RECALIBRATE",
            "red_summary": "session overshoot instability too high; halt symbol and recalibrate",
        },
        "E12_cap_plateau_width_pips": {
            "direction": "higher_better",
            "green_min": 0.50,
            "amber_min": 0.30,
            "amber_action": "A1_RECALIBRATE_CAP",
            "amber_summary": "cap plateau narrow; recalibrate cap and verify robustness",
            "red_action": "A3_HALT_RECALIBRATE",
            "red_summary": "cap robustness collapsed; halt until cap/strategy is revalidated",
        },
        "E13_nonfill_opportunity_cost_pips": {
            "direction": "lower_better",
            "green_max": 0.20,
            "amber_max": 0.35,
            "amber_action": "A1_RECALIBRATE_CAP",
            "amber_summary": "non-fill opportunity cost elevated; recalibrate cap",
            "red_action": "A3_HALT_RECALIBRATE",
            "red_summary": "non-fill opportunity cost too high; halt and rework execution envelope",
        },
        "erosion_spread_fee_plus_slip": {
            "direction": "lower_better",
            "green_max": 0.30,
            "amber_max": 0.50,
            "amber_action": "A1_RECALIBRATE_CAP",
            "amber_summary": "execution erosion elevated; recalibrate cap/slippage assumptions",
            "red_action": "A3_HALT_RECALIBRATE",
            "red_summary": "execution erosion too high; halt symbol until recalibrated",
        },
        "tick_overshoot_p95_pips": {
            "direction": "lower_better",
            "green_max": 0.70,
            "amber_max": 1.00,
            "amber_action": "A2_SESSION_GUARD",
            "amber_summary": "overshoot tail elevated; apply session guard and monitor",
            "red_action": "A3_HALT_RECALIBRATE",
            "red_summary": "overshoot tail unsafe; halt and revalidate execution assumptions",
        },
    }
    rule = rules.get(m_id)
    if rule is None:
        return {
            "metric_id": m_id,
            "metric_value": val,
            "direction": "na",
            "band": "unknown",
            "action_code": "A9_DATA_GAP",
            "action_summary": "unknown policy metric; update Stage 04 policy map",
            "green_threshold": "",
            "amber_threshold": "",
        }

    direction = str(rule["direction"])
    if direction == "lower_better":
        g = _num(rule["green_max"])
        a = _num(rule["amber_max"])
        if val <= g:
            band = "green"
            action_code = "A0_MONITOR"
            action_summary = "within execution policy limits; monitor only"
        elif val <= a:
            band = "amber"
            action_code = str(rule["amber_action"])
            action_summary = str(rule["amber_summary"])
        else:
            band = "red"
            action_code = str(rule["red_action"])
            action_summary = str(rule["red_summary"])
        green_threshold = f"<= {g:.4f}"
        amber_threshold = f"<= {a:.4f}"
    else:
        g = _num(rule["green_min"])
        a = _num(rule["amber_min"])
        if val >= g:
            band = "green"
            action_code = "A0_MONITOR"
            action_summary = "within execution policy limits; monitor only"
        elif val >= a:
            band = "amber"
            action_code = str(rule["amber_action"])
            action_summary = str(rule["amber_summary"])
        else:
            band = "red"
            action_code = str(rule["red_action"])
            action_summary = str(rule["red_summary"])
        green_threshold = f">= {g:.4f}"
        amber_threshold = f">= {a:.4f}"

    return {
        "metric_id": m_id,
        "metric_value": val,
        "direction": direction,
        "band": band,
        "action_code": action_code,
        "action_summary": action_summary,
        "green_threshold": green_threshold,
        "amber_threshold": amber_threshold,
    }


def _stage04_policy_rollup_rows(policy_rows: pd.DataFrame) -> pd.DataFrame:
    if policy_rows.empty or "symbol" not in policy_rows.columns:
        return pd.DataFrame()
    band_rank = {"green": 0, "amber": 1, "red": 2, "unknown": 3}
    action_rank = {
        "A0_MONITOR": 0,
        "A1_RECALIBRATE_CAP": 1,
        "A2_SESSION_GUARD": 2,
        "A3_HALT_RECALIBRATE": 3,
        "A9_DATA_GAP": 4,
    }
    out: list[dict[str, Any]] = []
    for sym, grp in policy_rows.groupby("symbol", sort=True):
        g = grp.copy()
        g["band_rank"] = g["band"].astype(str).map(band_rank).fillna(3).astype(int)
        g["action_rank"] = g["action_code"].astype(str).map(action_rank).fillna(4).astype(int)
        worst_band_idx = int(g["band_rank"].idxmax())
        worst_action_idx = int(g["action_rank"].idxmax())
        red_metrics = g[g["band"].astype(str) == "red"]["metric_id"].astype(str).tolist()
        amber_metrics = g[g["band"].astype(str) == "amber"]["metric_id"].astype(str).tolist()
        out.append(
            {
                "symbol": str(sym).upper(),
                "metrics_total": int(len(g)),
                "green_metric_count": int((g["band"] == "green").sum()),
                "amber_metric_count": int((g["band"] == "amber").sum()),
                "red_metric_count": int((g["band"] == "red").sum()),
                "unknown_metric_count": int((g["band"] == "unknown").sum()),
                "worst_band": str(g.loc[worst_band_idx, "band"]),
                "recommended_action_code": str(g.loc[worst_action_idx, "action_code"]),
                "recommended_action_summary": str(g.loc[worst_action_idx, "action_summary"]),
                "red_metrics": ",".join(red_metrics),
                "amber_metrics": ",".join(amber_metrics),
            }
        )
    return pd.DataFrame(out).sort_values("symbol").reset_index(drop=True)


def _threshold_margin(metric_value: Any, threshold: Any) -> float:
    """Return signed margin (>0 pass-side room, <0 fail-side) for simple numeric thresholds."""
    m = _num(metric_value)
    t = str(threshold).strip()
    if not (math.isfinite(m) and t):
        return float("nan")
    m_obj = re.match(r"^(<=|>=|==|<|>)\s*(-?\d+(?:\.\d+)?)$", t)
    if not m_obj:
        return float("nan")
    op = str(m_obj.group(1))
    th = _num(m_obj.group(2))
    if not math.isfinite(th):
        return float("nan")
    if op in {"<=", "<"}:
        return th - m
    if op in {">=", ">"}:
        return m - th
    return -abs(m - th)


def _month_series_std(v: pd.Series) -> float:
    x = pd.to_numeric(v, errors="coerce").dropna()
    if len(x) <= 1:
        return float("nan")
    return float(x.std(ddof=1))


def _is_true(v: Any) -> bool:
    if isinstance(v, bool):
        return bool(v)
    s = str(v).strip().lower()
    return s in {"1", "true", "yes", "y", "pass"}


def _symbol_snapshot(
    entry: dict[str, Any],
    *,
    base_dir: Path,
    min_exact: float,
    min_pos: float,
    robust_quantile: float | None,
) -> dict[str, Any]:
    symbol = str(entry["symbol"]).upper().strip()

    reduced = _read_symbol_row(
        _resolve_path(base_dir, str(entry["reduced_summary_csv"])), symbol=symbol
    )
    tick_exact = _read_symbol_row(
        _resolve_path(base_dir, str(entry["tick_exact_summary_csv"])), symbol=symbol
    )
    robustness = _read_robustness_row(
        _resolve_path(base_dir, str(entry["robustness_summary_csv"])), quantile=robust_quantile
    )
    stop_limit = _read_symbol_row(
        _resolve_path(base_dir, str(entry["stop_limit_summary_csv"])), symbol=symbol
    )

    exact_rate = _num(tick_exact.get("exact_match_rate"))
    pos_rate = _num(tick_exact.get("pos_label_match_rate"))

    robust_months = _num(robustness.get("months"))
    robust_pos_months = _num(robustness.get("positive_months"))
    robust_majority = (
        robust_pos_months >= math.ceil(0.5 * robust_months)
        if (math.isfinite(robust_months) and robust_months > 0 and math.isfinite(robust_pos_months))
        else False
    )

    reduced_lb95 = _num(reduced.get("lb95_month_mean_gross_pips"))
    robust_lb95_trade = _num(robustness.get("lb95_trade_mean_gross_pips"))

    gate_reduced = math.isfinite(reduced_lb95) and reduced_lb95 > 0.0
    gate_tick_exact = (
        math.isfinite(exact_rate)
        and exact_rate >= float(min_exact)
        and math.isfinite(pos_rate)
        and pos_rate >= float(min_pos)
        and _is_true(tick_exact.get("overall_pass"))
    )
    gate_robust_lb95 = math.isfinite(robust_lb95_trade) and robust_lb95_trade > 0.0

    return {
        "symbol": symbol,
        "mean_gross_pips": _num(reduced.get("mean_gross_pips")),
        "lb95_month_mean_gross_pips": reduced_lb95,
        "positive_months": _num(reduced.get("positive_months")),
        "months_total": _num(reduced.get("months_total")),
        "rows_total": _num(reduced.get("rows_total")),
        "fill_rate_overall": _num(reduced.get("fill_rate_overall")),
        "exact_match_rate": exact_rate,
        "pos_label_match_rate": pos_rate,
        "tick_exact_overall_pass": _is_true(tick_exact.get("overall_pass")),
        "robustness_quantile": _num(robustness.get("quantile")),
        "robustness_rows": _num(robustness.get("rows")),
        "robustness_mean_gross_pips": _num(robustness.get("mean_gross_pips")),
        "robustness_lb95_trade_mean_gross_pips": robust_lb95_trade,
        "robustness_positive_months": robust_pos_months,
        "robustness_months": robust_months,
        "tick_overshoot_mean_pips": _num(stop_limit.get("tick_overshoot_mean_pips")),
        "tick_overshoot_p95_pips": _num(stop_limit.get("tick_overshoot_p95_pips")),
        "gate_reduced_lb95_month_gt0": gate_reduced,
        "gate_tick_exact": gate_tick_exact,
        "gate_robust_lb95_trade_gt0": gate_robust_lb95,
        "gate_robust_months_majority": robust_majority,
        "symbol_all_gates_pass": gate_reduced
        and gate_tick_exact
        and gate_robust_lb95
        and robust_majority,
    }


def _write_plot_gross(snapshot: pd.DataFrame, out_path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    d = snapshot.copy()
    if d.empty:
        return

    x = range(len(d))
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar([i - 0.2 for i in x], d["mean_gross_pips"], width=0.38, label="Reduced mean gross")
    ax.bar(
        [i + 0.2 for i in x],
        d["robustness_lb95_trade_mean_gross_pips"],
        width=0.38,
        label="Robustness LB95 trade gross",
    )
    ax.set_xticks(list(x))
    ax.set_xticklabels(d["symbol"].tolist())
    ax.set_ylabel("Pips")
    ax.set_title("Symbol Gross vs Robustness LB95")
    ax.axhline(0.0, color="black", linewidth=1.0)
    ax.legend(loc="best")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def _write_plot_tick_exact(snapshot: pd.DataFrame, out_path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    d = snapshot.copy()
    if d.empty:
        return

    x = range(len(d))
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(list(x), d["exact_match_rate"], marker="o", label="Exact match")
    ax.plot(list(x), d["pos_label_match_rate"], marker="o", label="Pos-label match")
    ax.set_xticks(list(x))
    ax.set_xticklabels(d["symbol"].tolist())
    ax.set_ylim(0.0, 1.01)
    ax.set_ylabel("Rate")
    ax.set_title("Tick-Exact Verification Rates")
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(loc="lower right")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def _write_markdown_outputs(
    *,
    cfg: dict[str, Any],
    outputs: BuildOutputs,
    artifact_inventory: pd.DataFrame,
    snapshot: pd.DataFrame,
    stage_status: pd.DataFrame,
    checks: pd.DataFrame,
    issues: pd.DataFrame,
    audit_failures: int,
    audit_pass: bool,
    figures: list[Path],
) -> None:
    generated_dir = outputs.generated_dir
    generated_dir.mkdir(parents=True, exist_ok=True)

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    pipeline_md = generated_dir / "pipeline_snapshot.md"
    pipeline_lines: list[str] = []
    pipeline_lines.append("# Pipeline Snapshot")
    pipeline_lines.append("")
    pipeline_lines.append(f"- generated_at: `{now_utc}`")
    pipeline_lines.append(f"- title: `{cfg.get('title')}`")
    pipeline_lines.append("")
    pipeline_lines.append("## Symbol Summary")
    pipeline_lines.append(_table(snapshot))
    pipeline_lines.append("")
    pipeline_lines.append("## Stage Gate Status")
    pipeline_lines.append(_table(stage_status))
    pipeline_lines.append("")
    if figures:
        pipeline_lines.append("## Figures")
        for fig in figures:
            rel = Path("..") / ".." / "figures" / "oco_bible" / fig.name
            pipeline_lines.append(f"- `{fig.name}`")
            pipeline_lines.append(f"  ![]({rel.as_posix()})")
    pipeline_md.write_text("\n".join(pipeline_lines), encoding="utf-8")

    audit_md = generated_dir / "audit_snapshot.md"
    audit_lines: list[str] = []
    audit_lines.append("# Audit Snapshot")
    audit_lines.append("")
    audit_lines.append(f"- generated_at: `{now_utc}`")
    audit_lines.append(f"- audit_failures: `{int(audit_failures)}`")
    audit_lines.append(f"- audit_pass: `{bool(audit_pass)}`")
    audit_lines.append("")
    fail_checks = (
        checks[checks["status"].astype(str) != "pass"].copy()
        if not checks.empty
        else pd.DataFrame()
    )
    audit_lines.append("## Failed Checks")
    audit_lines.append(_table(fail_checks))
    audit_lines.append("")
    audit_lines.append("## Issues")
    audit_lines.append(_table(issues))
    audit_md.write_text("\n".join(audit_lines), encoding="utf-8")

    inventory_md = generated_dir / "artifact_inventory.md"
    inventory_lines: list[str] = []
    inventory_lines.append("# Artifact Inventory")
    inventory_lines.append("")
    inventory_lines.append(f"- generated_at: `{now_utc}`")
    inventory_lines.append("")
    inventory_lines.append(_table(artifact_inventory))
    inventory_md.write_text("\n".join(inventory_lines), encoding="utf-8")

    source_md = generated_dir / "source_index.md"
    source_lines: list[str] = []
    source_lines.append("# Source Index")
    source_lines.append("")

    script_links = cfg.get("script_links", [])
    if script_links:
        source_lines.append("## Scripts")
        for p in script_links:
            source_lines.append(f"- `{p}`")
        source_lines.append("")

    config_links = cfg.get("config_links", [])
    if config_links:
        source_lines.append("## Configs")
        for p in config_links:
            source_lines.append(f"- `{p}`")
        source_lines.append("")

    test_links = cfg.get("test_links", [])
    if test_links:
        source_lines.append("## Tests")
        for p in test_links:
            source_lines.append(f"- `{p}`")
        source_lines.append("")

    source_lines.append("## Symbol Reports")
    for entry in cfg.get("symbols", []):
        s = str(entry.get("symbol", "")).upper()
        source_lines.append(f"### {s}")
        for k in [
            "mining_report_md",
            "wfo_report_md",
            "reduced_core_report_md",
            "tick_exact_report_md",
        ]:
            if k in entry:
                source_lines.append(f"- `{entry[k]}`")
        source_lines.append("")
    source_lines.append("## Generated Stage Snapshots")
    for i in range(1, 11):
        source_lines.append(f"- `docs/strategy_bible/generated/stage_{i:02d}_snapshot.md`")
    source_lines.append("")
    source_lines.append("## Stage Metrics")
    source_lines.append(f"- `{_to_repo_rel(outputs.stage_metrics_csv)}`")
    source_md.write_text("\n".join(source_lines), encoding="utf-8")


def _safe_read_csv(path: Path | None) -> pd.DataFrame:
    if path is None or not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def _safe_read_parquet(path: Path | None, *, columns: list[str] | None = None) -> pd.DataFrame:
    if path is None or not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(path, columns=columns)
    except Exception:
        try:
            return pd.read_parquet(path)
        except Exception:
            return pd.DataFrame()


def _safe_read_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def _glob_latest(pattern: str) -> Path | None:
    matches = [Path(p).resolve() for p in glob.glob(pattern)]
    if not matches:
        return None
    matches = [p for p in matches if p.exists()]
    if not matches:
        return None
    matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return matches[0]


def _discover_stage_pages() -> dict[int, Path]:
    root = (Path.cwd() / "docs" / "strategy_bible").resolve()
    out: dict[int, Path] = {}
    if not root.exists():
        return out
    for p in sorted(root.glob("stage_[0-9][0-9]_*.md")):
        m = re.match(r"stage_(\d{2})_", p.name)
        if not m:
            continue
        out[int(m.group(1))] = p
    return out


def _inject_stage_block(page_path: Path, *, stage_id: int, content: str) -> None:
    if not page_path.exists():
        return
    start = f"<!-- GENERATED:STAGE_{stage_id:02d}:START -->"
    end = f"<!-- GENERATED:STAGE_{stage_id:02d}:END -->"
    body = page_path.read_text(encoding="utf-8")
    replacement = f"{start}\n{content.strip()}\n{end}"

    if start in body and end in body:
        pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), flags=re.S)
        body = pattern.sub(replacement, body, count=1)
    else:
        append_block = "\n".join(
            [
                "",
                "## Generated Run Snapshot",
                replacement,
                "",
            ]
        )
        body = body.rstrip() + "\n" + append_block
    page_path.write_text(body, encoding="utf-8")


def _inject_named_block(page_path: Path, *, marker_name: str, heading: str, content: str) -> None:
    if not page_path.exists():
        return
    start = f"<!-- GENERATED:{marker_name}:START -->"
    end = f"<!-- GENERATED:{marker_name}:END -->"
    body = page_path.read_text(encoding="utf-8")
    replacement = f"{start}\n{content.strip()}\n{end}"

    if start in body and end in body:
        pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), flags=re.S)
        body = pattern.sub(replacement, body, count=1)
    else:
        append_block = "\n".join(["", heading, replacement, ""])
        body = body.rstrip() + "\n" + append_block
    page_path.write_text(body, encoding="utf-8")


def _to_bool_series(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.lower().isin({"1", "true", "yes", "y", "pass"})


def _pick_cols(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    keep = [c for c in cols if c in df.columns]
    if not keep:
        return pd.DataFrame()
    return df[keep].copy()


def _symbol_contexts(cfg: dict[str, Any], base_dir: Path) -> list[dict[str, Any]]:
    contexts: list[dict[str, Any]] = []
    for entry in cfg.get("symbols", []):
        symbol = str(entry.get("symbol", "")).upper().strip()
        if not symbol:
            continue
        reduced_summary = _resolve_path(base_dir, str(entry["reduced_summary_csv"]))
        tick_exact_summary = _resolve_path(base_dir, str(entry["tick_exact_summary_csv"]))
        robustness_summary = _resolve_path(base_dir, str(entry["robustness_summary_csv"]))
        stop_summary = _resolve_path(base_dir, str(entry["stop_limit_summary_csv"]))
        reduced_dir = reduced_summary.parent
        stop_dir = stop_summary.parent

        cwd = Path.cwd()
        wfo_metrics = _glob_latest(
            str(
                cwd
                / "data"
                / "analysis"
                / "tick_opportunity_mining"
                / "wfo_*"
                / f"{symbol}_monthly_metrics_all.csv"
            )
        ) or _glob_latest(
            str(
                cwd
                / "data"
                / "analysis"
                / "tick_opportunity_mining"
                / "wfo_*"
                / f"{symbol}_oco_monthly_metrics.csv"
            )
        )
        wfo_thresholds = _glob_latest(
            str(
                cwd
                / "data"
                / "analysis"
                / "tick_opportunity_mining"
                / "wfo_*"
                / f"{symbol}_monthly_thresholds_all.csv"
            )
        ) or _glob_latest(
            str(
                cwd
                / "data"
                / "analysis"
                / "tick_opportunity_mining"
                / "wfo_*"
                / f"{symbol}_oco_monthly_thresholds.csv"
            )
        )
        wfo_predictions = _glob_latest(
            str(
                cwd
                / "data"
                / "analysis"
                / "tick_opportunity_mining"
                / "wfo_*"
                / f"{symbol}_monthly_predictions_all.parquet"
            )
        ) or _glob_latest(
            str(
                cwd
                / "data"
                / "analysis"
                / "tick_opportunity_mining"
                / "wfo_*"
                / f"{symbol}_oco_monthly_predictions.parquet"
            )
        )
        governance_predeploy = _glob_latest(
            str(
                cwd
                / "data"
                / "analysis"
                / "tick_opportunity_mining"
                / f"{str(symbol).lower()}_governance_predeploy*.json"
            )
        )
        if governance_predeploy is None:
            governance_predeploy = _resolve_path(
                base_dir,
                f"data/analysis/tick_opportunity_mining/{str(symbol).lower()}_governance_predeploy.json",
            )
        events_eval = _glob_latest(
            str(
                cwd
                / "data"
                / "analysis"
                / "tick_opportunity_mining"
                / "wfo_*"
                / f"{symbol}_oco_events_eval*.parquet"
            )
        )
        contexts.append(
            {
                "symbol": symbol,
                "data_reliability_checks_csv": _resolve_path(
                    base_dir, "data/analysis/tick_opportunity_mining/data_reliability_checks.csv"
                ),
                "data_reliability_issues_csv": _resolve_path(
                    base_dir, "data/analysis/tick_opportunity_mining/data_reliability_issues.csv"
                ),
                "data_reliability_report_md": _resolve_path(
                    base_dir, "docs/analysis/data_reliability_report.md"
                ),
                "leakage_checks_csv": _resolve_path(
                    base_dir,
                    "data/analysis/tick_opportunity_mining/oco_leakage_integrity_checks.csv",
                ),
                "leakage_issues_csv": _resolve_path(
                    base_dir,
                    "data/analysis/tick_opportunity_mining/oco_leakage_integrity_issues.csv",
                ),
                "leakage_report_md": _resolve_path(
                    base_dir, "docs/analysis/oco_leakage_integrity_report.md"
                ),
                "execution_risk_checks_csv": _resolve_path(
                    base_dir, "data/analysis/tick_opportunity_mining/oco_execution_risk_checks.csv"
                ),
                "execution_risk_issues_csv": _resolve_path(
                    base_dir, "data/analysis/tick_opportunity_mining/oco_execution_risk_issues.csv"
                ),
                "execution_risk_report_md": _resolve_path(
                    base_dir, "docs/analysis/oco_execution_risk_prelive_report.md"
                ),
                "execution_mc_month_session_csv": _resolve_path(
                    base_dir,
                    "data/analysis/tick_opportunity_mining/execution_mc_month_session_summary.csv",
                ),
                "execution_mc_monthly_csv": _resolve_path(
                    base_dir,
                    "data/analysis/tick_opportunity_mining/execution_mc_monthly_summary.csv",
                ),
                "execution_mc_symbol_scenarios_csv": _resolve_path(
                    base_dir,
                    "data/analysis/tick_opportunity_mining/execution_mc_symbol_scenarios.csv",
                ),
                "execution_mc_checks_csv": _resolve_path(
                    base_dir, "data/analysis/tick_opportunity_mining/execution_mc_checks.csv"
                ),
                "execution_mc_issues_csv": _resolve_path(
                    base_dir, "data/analysis/tick_opportunity_mining/execution_mc_issues.csv"
                ),
                "execution_mc_report_md": _resolve_path(
                    base_dir, "docs/analysis/oco_execution_monte_carlo_report.md"
                ),
                "timezone_contract_csv": _resolve_path(
                    base_dir,
                    f"data/analysis/tick_opportunity_mining/{symbol}_stage1_timezone_contract.csv",
                ),
                "candidate_csv": _resolve_path(
                    base_dir, f"data/analysis/tick_opportunity_mining/{symbol}_oco_candidates.csv"
                ),
                "reduced_summary_csv": reduced_summary,
                "reduced_monthly_csv": reduced_dir / f"{symbol}_oco_reduced_monthly.csv",
                "reduced_churn_csv": reduced_dir / f"{symbol}_oco_reduced_state_churn.csv",
                "reduced_state_schedule_csv": reduced_dir
                / f"{symbol}_oco_reduced_state_schedule.csv",
                "tick_exact_summary_csv": tick_exact_summary,
                "tick_exact_monthly_csv": reduced_dir / f"{symbol}_oco_tick_exact_monthly.csv",
                "tick_exact_replay_csv": reduced_dir / f"{symbol}_oco_tick_exact_replay_bundle.csv",
                "robustness_summary_csv": robustness_summary,
                "robustness_null_csv": robustness_summary.parent
                / f"{symbol}_oco_robustness_null_tests.csv",
                "robustness_stability_csv": robustness_summary.parent
                / f"{symbol}_oco_robustness_stability.csv",
                "robustness_effect_csv": robustness_summary.parent
                / f"{symbol}_oco_robustness_effect_sizes.csv",
                "stop_limit_summary_csv": stop_summary,
                "stop_limit_caps_csv": stop_dir / f"{symbol}_stop_limit_tickfill_caps.csv",
                "stop_limit_detail_csv": stop_dir / f"{symbol}_stop_limit_tickfill_detail.csv",
                "stop_limit_fill_drift_csv": stop_dir / f"{symbol}_fill_drift_monthly.csv",
                "wfo_metrics_csv": wfo_metrics,
                "wfo_thresholds_csv": wfo_thresholds,
                "wfo_predictions_parquet": wfo_predictions,
                "wfo_skip_reasons_csv": (
                    wfo_metrics.parent / f"{symbol}_wfo_skip_reasons_all.csv"
                    if wfo_metrics is not None
                    else None
                ),
                "governance_predeploy_json": governance_predeploy,
                "events_eval_parquet": events_eval,
            }
        )
    return contexts


def _robustness_diag_table(*, contexts: list[dict[str, Any]], exec_q: float) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for ctx in contexts:
        sym = str(ctx.get("symbol", "")).upper().strip()
        rb = _safe_read_csv(ctx.get("robustness_summary_csv"))
        if rb.empty:
            continue
        pick = rb.copy()
        if "quantile" in pick.columns:
            qcol = pd.to_numeric(pick["quantile"], errors="coerce")
            m = qcol == float(exec_q)
            pick = pick.loc[m].copy() if m.any() else pick.head(1).copy()
        row = pick.iloc[0].to_dict()
        months = _num(row.get("months"))
        pos_months = _num(row.get("positive_months"))
        majority = (
            bool(pos_months >= math.ceil(0.5 * months))
            if (math.isfinite(months) and months > 0 and math.isfinite(pos_months))
            else False
        )
        p_bonf = _num(row.get("pvalue_bonferroni"))
        p_fdr = _num(row.get("pvalue_fdr_bh"))
        p_perm = _num(row.get("pvalue_perm_uplift"))
        p_perm_fdr = _num(row.get("pvalue_perm_fdr_bh"))
        lb_iid = _num(row.get("lb95_trade_mean_gross_pips_iid"))
        lb_block = _num(row.get("lb95_trade_mean_gross_pips_month_block"))
        uplift = _num(row.get("uplift_vs_null_pips"))
        rows.append(
            {
                "symbol": sym,
                "quantile": _num(row.get("quantile")),
                "rows": _num(row.get("rows")),
                "months": months,
                "positive_months": pos_months,
                "lb95_trade_mean_gross_pips": _num(row.get("lb95_trade_mean_gross_pips")),
                "lb95_trade_mean_gross_pips_iid": lb_iid,
                "lb95_trade_mean_gross_pips_month_block": lb_block,
                "pvalue_month_mean_gt0": _num(row.get("pvalue_month_mean_gt0")),
                "pvalue_bonferroni": p_bonf,
                "pvalue_fdr_bh": p_fdr,
                "uplift_vs_null_pips": uplift,
                "pvalue_perm_uplift": p_perm,
                "pvalue_perm_fdr_bh": p_perm_fdr,
                "majority_positive_months": majority,
                "bonferroni_pass_10pct": bool(math.isfinite(p_bonf) and p_bonf <= 0.10),
                "fdr_pass_10pct": bool(math.isfinite(p_fdr) and p_fdr <= 0.10),
                "perm_fdr_pass_10pct": bool(math.isfinite(p_perm_fdr) and p_perm_fdr <= 0.10),
            }
        )
    out = pd.DataFrame(rows)
    if not out.empty and "symbol" in out.columns:
        out = out.sort_values("symbol").reset_index(drop=True)
    return out


def _stage_plot_path(outputs: BuildOutputs, stage_id: int, slug: str) -> Path:
    return outputs.figures_dir / f"stage_{stage_id:02d}_{slug}.png"


def _plot_stage_lines(
    *,
    df: pd.DataFrame,
    x: str,
    y: str,
    hue: str,
    title: str,
    ylabel: str,
    out_path: Path,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if df.empty or x not in df.columns or y not in df.columns or hue not in df.columns:
        return

    fig, ax = plt.subplots(figsize=(9, 4.8))
    for key, grp in df.groupby(hue):
        g = grp.sort_values(x)
        ax.plot(g[x].astype(str), pd.to_numeric(g[y], errors="coerce"), marker="o", label=str(key))
    ax.set_title(title)
    ax.set_xlabel(x)
    ax.set_ylabel(ylabel)
    ax.grid(True, axis="y", alpha=0.25)
    ax.legend(loc="best")
    for label in ax.get_xticklabels():
        label.set_rotation(30)
        label.set_ha("right")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def _plot_stage_bars(
    *,
    df: pd.DataFrame,
    x: str,
    ys: list[str],
    title: str,
    ylabel: str,
    out_path: Path,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if df.empty or x not in df.columns:
        return
    keep = [c for c in ys if c in df.columns]
    if not keep:
        return

    d = df.copy()
    fig, ax = plt.subplots(figsize=(9, 4.8))
    xpos = list(range(len(d)))
    width = 0.8 / max(1, len(keep))
    for i, col in enumerate(keep):
        vals = pd.to_numeric(d[col], errors="coerce")
        offs = [j - 0.4 + width / 2 + i * width for j in xpos]
        ax.bar(offs, vals, width=width, label=col)
    ax.set_xticks(xpos)
    ax.set_xticklabels(d[x].astype(str).tolist())
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.grid(True, axis="y", alpha=0.25)
    ax.legend(loc="best")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def _plot_stage_scatter(
    *,
    df: pd.DataFrame,
    x: str,
    y: str,
    hue: str,
    title: str,
    xlabel: str,
    ylabel: str,
    out_path: Path,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if df.empty or x not in df.columns or y not in df.columns or hue not in df.columns:
        return

    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    for key, grp in df.groupby(hue):
        xv = pd.to_numeric(grp[x], errors="coerce")
        yv = pd.to_numeric(grp[y], errors="coerce")
        ax.scatter(xv, yv, s=18, alpha=0.6, label=str(key))
    ax.axhline(0.0, color="black", linewidth=1.0)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def _render_stage_snapshot(
    *,
    stage_id: int,
    now_utc: str,
    summary_table: pd.DataFrame,
    details_table: pd.DataFrame | None,
    notes: list[str],
    figure_paths: list[Path],
    figure_prefix: str,
    interpretation_notes: list[str] | None = None,
    action_summary_table: pd.DataFrame | None = None,
    details_max_rows: int = DETAIL_MAX_ROWS_DEFAULT,
    details_source_path: str = "",
) -> str:
    lines: list[str] = []
    lines.append(f"### Auto Snapshot - Stage {stage_id:02d}")
    lines.append("")
    lines.append(f"- generated_at: `{now_utc}`")
    lines.extend(f"- {n}" for n in notes)
    lines.append("")
    lines.append("#### Key Results")
    lines.append(_table(summary_table))
    interp = [
        str(x).strip()
        for x in (interpretation_notes if interpretation_notes is not None else notes[:3])
        if str(x).strip()
    ]
    lines.append("")
    lines.append("#### Interpretation Notes")
    if interp:
        lines.extend(f"- {n}" for n in interp[:6])
    else:
        lines.append(
            "- Review key metrics against stage-specific Validation Gates and operator runbook triggers."
        )
    lines.append("")
    lines.append("#### Action Trigger Summary")
    if action_summary_table is None or action_summary_table.empty:
        action_summary_table = pd.DataFrame(
            [
                {
                    "trigger": "hard_gate_fail",
                    "threshold_or_signal": "status=fail",
                    "action_code": "A3_HALT_RECALIBRATE",
                    "action_summary": "Block promotion and rerun upstream stage diagnostics before continuing.",
                },
                {
                    "trigger": "monitoring_warning",
                    "threshold_or_signal": "band=amber",
                    "action_code": "A0_MONITOR/A1_RECALIBRATE_CAP",
                    "action_summary": "Apply stage runbook remediation and confirm next-run recovery.",
                },
            ]
        )
    lines.append(_table(action_summary_table))
    if details_table is not None:
        d = details_table.copy()
        n_full = int(len(d))
        truncated = False
        if int(details_max_rows) > 0 and n_full > int(details_max_rows):
            d = d.head(int(details_max_rows)).copy()
            truncated = True
        lines.append("")
        lines.append("#### Details")
        lines.append(_table(d))
        if truncated:
            lines.append("")
            lines.append(f"- details_rows_shown: `{len(d)}` of `{n_full}`")
            if str(details_source_path).strip():
                lines.append(f"- full_artifact: `{_to_repo_rel(details_source_path)}`")
    if figure_paths:
        lines.append("")
        lines.append("#### Plots")
        for fig in figure_paths:
            lines.append(f"![{fig.stem}]({figure_prefix}{fig.name})")
    return "\n".join(lines).strip()


def _write_stage_snapshots(
    *,
    cfg: dict[str, Any],
    base_dir: Path,
    outputs: BuildOutputs,
    snapshot: pd.DataFrame,
    stage_status: pd.DataFrame,
    artifact_inventory: pd.DataFrame,
    checks: pd.DataFrame,
    issues: pd.DataFrame,
) -> pd.DataFrame:
    contexts = _symbol_contexts(cfg, base_dir)
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    generated_dir = outputs.generated_dir
    generated_dir.mkdir(parents=True, exist_ok=True)
    page_map = _discover_stage_pages()
    repo_generated_dir = (Path.cwd() / "docs" / "strategy_bible" / "generated").resolve()
    inject_stage_pages = generated_dir.resolve() == repo_generated_dir
    metric_rows: list[dict[str, Any]] = []
    edge_stage_rows: list[dict[str, Any]] = []
    edge_state_rows: list[dict[str, Any]] = []
    edge_threshold_rows: list[dict[str, Any]] = []
    operator_action_csv = outputs.stage_metrics_csv.parent / "operator_action_status.csv"
    operator_actions = pd.DataFrame()
    if operator_action_csv.exists():
        try:
            operator_actions = pd.read_csv(operator_action_csv)
        except Exception:
            operator_actions = pd.DataFrame()

    def add_metric(
        stage_id: int, metric_id: str, symbol: str, value: Any, unit: str, source_path: str
    ) -> None:
        metric_rows.append(
            {
                "stage_id": stage_id,
                "metric_id": metric_id,
                "symbol": symbol,
                "value": _num(value),
                "unit": unit,
                "source_path": _to_repo_rel(source_path),
                "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )

    def add_edge_metric(
        stage_id: int, symbol: str, metric_id: str, metric_value: Any, note: str, source_path: str
    ) -> None:
        edge_stage_rows.append(
            {
                "stage_id": stage_id,
                "symbol": symbol,
                "metric_id": metric_id,
                "metric_value": _num(metric_value),
                "note": str(note),
                "source_path": _to_repo_rel(source_path),
                "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )

    def write_stage(stage_id: int, content_for_stage_page: str) -> None:
        snap = generated_dir / f"stage_{stage_id:02d}_snapshot.md"
        content_for_generated = content_for_stage_page.replace(
            "../figures/oco_bible/", "../../figures/oco_bible/"
        )
        snap.write_text(content_for_generated + "\n", encoding="utf-8")
        page = page_map.get(stage_id)
        if inject_stage_pages and page is not None:
            _inject_stage_block(page, stage_id=stage_id, content=content_for_stage_page)

    def stage_action_table(stage_id: int) -> pd.DataFrame:
        if operator_actions.empty or "stage_id" not in operator_actions.columns:
            return pd.DataFrame()
        oa = operator_actions.copy()
        oa["stage_id"] = pd.to_numeric(oa["stage_id"], errors="coerce")
        g = oa[oa["stage_id"] == int(stage_id)].copy()
        if g.empty:
            return pd.DataFrame()
        keep = [
            c
            for c in [
                "symbol",
                "metric_id",
                "band",
                "severity",
                "action_code",
                "action_summary",
                "owner",
            ]
            if c in g.columns
        ]
        if not keep:
            return pd.DataFrame()
        g = g[keep].drop_duplicates()
        return g.head(12).reset_index(drop=True)

    # Stage 01: Data contract health over events.
    req_cols = [
        "cost_est_pips",
        "range_pips",
        "spread_z",
        "tick_rate_z",
        "vel_cost_units_h1",
        "hl_first",
    ]
    stage01_rows: list[dict[str, Any]] = []
    tz_rows: list[pd.DataFrame] = []
    rel_rows: list[pd.DataFrame] = []
    rel_issue_rows: list[pd.DataFrame] = []
    for ctx in contexts:
        sym = ctx["symbol"]
        ev_path = ctx.get("events_eval_parquet")
        stage01_cols = list(
            dict.fromkeys(
                ["close_ts", "hour_utc", "cost_est_pips", "spread_z", "tick_rate_z"] + req_cols
            )
        )
        df = _safe_read_parquet(
            ev_path,
            columns=stage01_cols,
        )
        row: dict[str, Any] = {"symbol": sym, "events_rows": int(len(df)) if not df.empty else 0}
        for c in req_cols:
            if c in df.columns and len(df) > 0:
                row[f"{c}_null_pct"] = float(df[c].isna().mean() * 100.0)
            else:
                row[f"{c}_null_pct"] = float("nan")
        if not df.empty and "close_ts" in df.columns:
            dd = df.copy()
            dd["close_ts"] = pd.to_datetime(dd["close_ts"], utc=True, errors="coerce")
            dd = dd.dropna(subset=["close_ts"]).sort_values("close_ts")
            if len(dd) > 10:
                gap_s = dd["close_ts"].diff().dt.total_seconds().dropna()
                gap_pos = gap_s[gap_s > 0]
                ref_gap = _num(gap_pos.median()) if len(gap_pos) > 0 else _num(gap_s.median())
                jitter_cv_raw = _safe_div(_num(gap_s.std(ddof=1)), ref_gap)
                if not math.isfinite(ref_gap) or ref_gap <= 0:
                    # If timestamp precision collapses many diffs to 0, fall back to no-burst/no-jitter.
                    burst_ratio = 0.0
                    jitter_cv = 0.0
                    jitter_cv_raw = 0.0
                else:
                    burst_ratio = _num((gap_s > (10.0 * ref_gap)).mean())
                    # Normalize spacing by hour-of-week expected interval to reduce deterministic session effects.
                    d_gap = dd.loc[gap_s.index, ["close_ts"]].copy()
                    d_gap["dt_s"] = pd.to_numeric(gap_s, errors="coerce")
                    d_gap = d_gap.dropna(subset=["dt_s"])
                    d_gap = d_gap[d_gap["dt_s"] > 0].copy()
                    if not d_gap.empty:
                        d_gap["how"] = (
                            d_gap["close_ts"].dt.dayofweek * 24 + d_gap["close_ts"].dt.hour
                        )
                        exp = d_gap.groupby("how")["dt_s"].median()
                        global_med = _num(d_gap["dt_s"].median())
                        d_gap["exp_dt_s"] = d_gap["how"].map(exp).astype(float).fillna(global_med)
                        d_gap = d_gap[d_gap["exp_dt_s"] > 0].copy()
                        d_gap["resid_ratio"] = d_gap["dt_s"] / d_gap["exp_dt_s"]
                        q05 = _num(d_gap["resid_ratio"].quantile(0.05))
                        q95 = _num(d_gap["resid_ratio"].quantile(0.95))
                        if math.isfinite(q05) and math.isfinite(q95) and q95 > q05:
                            d_gap["resid_ratio"] = d_gap["resid_ratio"].clip(lower=q05, upper=q95)
                        jitter_cv = _safe_div(
                            _num(d_gap["resid_ratio"].std(ddof=1)),
                            _num(d_gap["resid_ratio"].mean()),
                        )
                    else:
                        jitter_cv = jitter_cv_raw
            else:
                burst_ratio = float("nan")
                jitter_cv = float("nan")
                jitter_cv_raw = float("nan")
            if "cost_est_pips" in dd.columns:
                dd["month"] = dd["close_ts"].dt.tz_convert(None).dt.to_period("M").astype(str)
                month_cost = dd.groupby("month")["cost_est_pips"].mean().dropna()
                if len(month_cost) >= 3:
                    last = _num(month_cost.iloc[-1])
                    hist = month_cost.iloc[:-1]
                    hist_mean = _num(hist.mean())
                    hist_std = _num(hist.std(ddof=1))
                    spread_shift_z = _safe_div(last - hist_mean, hist_std)
                else:
                    spread_shift_z = float("nan")
            else:
                spread_shift_z = float("nan")
        else:
            burst_ratio = float("nan")
            jitter_cv = float("nan")
            jitter_cv_raw = float("nan")
            spread_shift_z = float("nan")
        row["d16_spread_regime_shift_z"] = spread_shift_z
        row["d17_gap_burst_ratio"] = burst_ratio
        row["d18_clock_jitter_cv"] = jitter_cv
        row["d18_clock_jitter_cv_raw"] = jitter_cv_raw
        stage01_rows.append(row)
        add_metric(
            1, "events_rows", sym, row["events_rows"], "rows", str(ev_path) if ev_path else ""
        )
        add_edge_metric(
            1,
            sym,
            "D16_spread_regime_shift_z",
            spread_shift_z,
            "Last-month cost-estimate shift vs prior months",
            str(ev_path) if ev_path else "",
        )
        add_edge_metric(
            1,
            sym,
            "D17_gap_burst_ratio",
            burst_ratio,
            "Share of large inter-bar time gaps (>10x median)",
            str(ev_path) if ev_path else "",
        )
        add_edge_metric(
            1,
            sym,
            "D18_clock_jitter_cv_raw",
            jitter_cv_raw,
            "Raw inter-bar timing jitter coefficient of variation",
            str(ev_path) if ev_path else "",
        )
        add_edge_metric(
            1,
            sym,
            "D18_clock_jitter_cv",
            jitter_cv,
            "Normalized inter-bar timing jitter CV after hour-of-week baseline adjustment",
            str(ev_path) if ev_path else "",
        )
        rel = _safe_read_csv(ctx.get("data_reliability_checks_csv"))
        if not rel.empty and "symbol" in rel.columns:
            rel = rel[rel["symbol"].astype(str).str.upper() == str(sym).upper()].copy()
        if not rel.empty:
            status = (
                rel.get("status", pd.Series(index=rel.index, dtype=str)).astype(str).str.lower()
            )
            severity = (
                rel.get("severity_if_fail", pd.Series(index=rel.index, dtype=str))
                .astype(str)
                .str.lower()
            )
            row["reliability_checks_total"] = int(len(rel))
            row["reliability_failed"] = int((status != "pass").sum())
            row["reliability_high_critical_failed"] = int(
                ((status != "pass") & severity.isin(["high", "critical"])).sum()
            )
            rel_rows.append(rel.assign(symbol=sym))
            add_metric(
                1,
                "reliability_high_critical_failed",
                sym,
                row["reliability_high_critical_failed"],
                "count",
                str(ctx.get("data_reliability_checks_csv", "")),
            )
        else:
            row["reliability_checks_total"] = 0
            row["reliability_failed"] = 0
            row["reliability_high_critical_failed"] = 0
        rel_issues = _safe_read_csv(ctx.get("data_reliability_issues_csv"))
        if not rel_issues.empty and "symbol" in rel_issues.columns:
            rel_issues = rel_issues[
                rel_issues["symbol"].astype(str).str.upper() == str(sym).upper()
            ].copy()
        if not rel_issues.empty:
            rel_issue_rows.append(rel_issues.assign(symbol=sym))
        tz = _safe_read_csv(ctx.get("timezone_contract_csv"))
        if not tz.empty:
            if "symbol" in tz.columns:
                tz = tz[tz["symbol"].astype(str).str.upper() == str(sym).upper()].copy()
            if not tz.empty:
                tz_rows.append(tz.assign(symbol=sym))
    stage01 = pd.DataFrame(stage01_rows)
    tz_stage01 = pd.concat(tz_rows, ignore_index=True) if tz_rows else pd.DataFrame()
    rel_stage01 = pd.concat(rel_rows, ignore_index=True) if rel_rows else pd.DataFrame()
    rel_issues_stage01 = (
        pd.concat(rel_issue_rows, ignore_index=True) if rel_issue_rows else pd.DataFrame()
    )
    stage01_plot = _stage_plot_path(outputs, 1, "contract_health")
    stage01_rel_plot = _stage_plot_path(outputs, 1, "data_reliability")
    if not stage01.empty:
        stage01_plot_df = stage01[["symbol", "events_rows"]].copy()
        stage01_plot_df["max_null_pct"] = pd.to_numeric(
            stage01[[f"{c}_null_pct" for c in req_cols]].max(axis=1), errors="coerce"
        )
        _plot_stage_bars(
            df=stage01_plot_df,
            x="symbol",
            ys=["events_rows", "max_null_pct"],
            title="Stage 1: Event Rows vs Max Null %",
            ylabel="rows / percent",
            out_path=stage01_plot,
        )
        if {"reliability_failed", "reliability_checks_total"}.issubset(set(stage01.columns)):
            _plot_stage_bars(
                df=stage01,
                x="symbol",
                ys=[
                    "reliability_checks_total",
                    "reliability_failed",
                    "reliability_high_critical_failed",
                ],
                title="Stage 1: Data Reliability Check Failures",
                ylabel="count",
                out_path=stage01_rel_plot,
            )
    stage01_details = stage01 if not stage01.empty else None
    if not tz_stage01.empty:
        tz_pick = _pick_cols(
            tz_stage01,
            [
                "symbol",
                "bar_ticks",
                "close_ts_parse_rate",
                "monotonic_close_ts_ok",
                "dst_transition_ok",
                "utc_offset_anomalies",
                "pass",
            ],
        )
        stage01_details = (
            pd.concat([stage01_details, tz_pick], ignore_index=True)
            if stage01_details is not None
            else tz_pick
        )
    stage01_content = _render_stage_snapshot(
        stage_id=1,
        now_utc=now_utc,
        summary_table=_pick_cols(
            stage01,
            [
                "symbol",
                "events_rows",
                "cost_est_pips_null_pct",
                "range_pips_null_pct",
                "hl_first_null_pct",
                "reliability_checks_total",
                "reliability_failed",
                "reliability_high_critical_failed",
                "d16_spread_regime_shift_z",
                "d17_gap_burst_ratio",
                "d18_clock_jitter_cv",
                "d18_clock_jitter_cv_raw",
            ],
        )
        if not stage01.empty
        else pd.DataFrame(),
        details_table=stage01_details
        if stage01_details is not None and not stage01_details.empty
        else None,
        notes=[
            "Contract check uses eval-year event tables consumed by WFO.",
            "Null percentages should remain near 0 for required modeling fields.",
            "Timezone contract rows include parse rate, monotonicity, DST and offset anomaly checks.",
            "Data reliability checks add schema, parse-rate, duplicate timestamp, OHLC consistency, and session coverage gates.",
            "Edge diagnostics D16-D18 are informational and track drift, bursty gaps, and clock jitter.",
        ],
        figure_paths=[p for p in [stage01_plot, stage01_rel_plot] if p.exists()],
        figure_prefix="../figures/oco_bible/",
        action_summary_table=stage_action_table(1),
    )
    if not rel_stage01.empty:
        rel_fail = rel_stage01[
            rel_stage01.get("status", pd.Series(dtype=str)).astype(str).str.lower() != "pass"
        ].copy()
        stage01_content += "\n\n#### Data Reliability Failed Checks\n" + _table(
            _pick_cols(
                rel_fail,
                [
                    "symbol",
                    "check_id",
                    "severity_if_fail",
                    "metric_name",
                    "metric_value",
                    "threshold",
                    "details",
                    "source_path",
                ],
            )
        )
    if not rel_issues_stage01.empty:
        stage01_content += "\n\n#### Data Reliability Issues\n" + _table(
            _pick_cols(
                rel_issues_stage01,
                [
                    "symbol",
                    "issue_id",
                    "check_id",
                    "severity",
                    "summary",
                    "metric_name",
                    "metric_value",
                    "threshold",
                ],
            )
        )
    write_stage(1, stage01_content)

    # Stage 02: Opportunity mining.
    stage23_overfit = _robustness_diag_table(
        contexts=contexts,
        exec_q=float(cfg.get("gate_thresholds", {}).get("robustness_quantile", 0.9)),
    )
    mining_summary_rows: list[dict[str, Any]] = []
    mining_scatter_rows: list[pd.DataFrame] = []
    for ctx in contexts:
        sym = ctx["symbol"]
        cand = _safe_read_csv(ctx.get("candidate_csv"))
        if cand.empty:
            continue
        sel = _to_bool_series(cand.get("selection_pass", pd.Series(dtype=str)))
        selected = cand[sel].copy()
        contrib_top3_share = float("nan")
        smoothness_abs_jump = float("nan")
        positive_density = float("nan")
        if not selected.empty:
            fills = pd.to_numeric(selected.get("annualized_test_fills"), errors="coerce")
            gross = pd.to_numeric(selected.get("mean_gross_pips_test"), errors="coerce")
            edge_w = fills * gross
            tmp = selected.copy()
            tmp["edge_weight"] = edge_w
            tmp = tmp.dropna(subset=["edge_weight"])
            if not tmp.empty:
                g = (
                    tmp.groupby(["family", "state_id", "bar_ticks", "horizon"], as_index=False)[
                        "edge_weight"
                    ]
                    .sum()
                    .sort_values("edge_weight", ascending=False)
                )
                tot = _num(g["edge_weight"].sum())
                top3 = _num(g["edge_weight"].head(3).sum())
                contrib_top3_share = _safe_div(top3, tot)
                g["contrib_share"] = (
                    g["edge_weight"] / tot if math.isfinite(tot) and tot != 0 else float("nan")
                )
                g["symbol"] = sym
                g["stage_id"] = 2
                edge_state_rows.extend(g.to_dict(orient="records"))
            # M02: horizon smoothness
            if {"family", "state_id", "bar_ticks", "horizon", "mean_gross_pips_test"}.issubset(
                set(selected.columns)
            ):
                s2 = selected[
                    ["family", "state_id", "bar_ticks", "horizon", "mean_gross_pips_test"]
                ].copy()
                s2["horizon"] = pd.to_numeric(s2["horizon"], errors="coerce")
                s2["mean_gross_pips_test"] = pd.to_numeric(
                    s2["mean_gross_pips_test"], errors="coerce"
                )
                s2 = s2.dropna(subset=["horizon", "mean_gross_pips_test"]).sort_values(
                    ["family", "state_id", "bar_ticks", "horizon"]
                )
                if not s2.empty:
                    s2["abs_jump"] = (
                        s2.groupby(["family", "state_id", "bar_ticks"])["mean_gross_pips_test"]
                        .diff()
                        .abs()
                    )
                    smoothness_abs_jump = _num(s2["abs_jump"].median())
            positive_density = _num(
                (pd.to_numeric(selected.get("mean_gross_pips_test"), errors="coerce") > 0).mean()
            )
        mining_summary_rows.append(
            {
                "symbol": sym,
                "candidates_total": int(len(cand)),
                "selected_total": int(len(selected)),
                "selected_mean_gross_pips": _num(
                    selected.get("mean_gross_pips_test", pd.Series(dtype=float)).mean()
                ),
                "selected_median_annualized": _num(
                    selected.get("annualized_test_fills", pd.Series(dtype=float)).median()
                ),
                "m01_top3_contrib_share": contrib_top3_share,
                "m02_smoothness_abs_jump": smoothness_abs_jump,
                "m03_positive_density": positive_density,
            }
        )
        add_metric(
            2, "selected_total", sym, len(selected), "rows", str(ctx.get("candidate_csv", ""))
        )
        add_edge_metric(
            2,
            sym,
            "M01_top3_contrib_share",
            contrib_top3_share,
            "Share of edge_weight from top 3 state blocks",
            str(ctx.get("candidate_csv", "")),
        )
        add_edge_metric(
            2,
            sym,
            "M02_smoothness_abs_jump",
            smoothness_abs_jump,
            "Median absolute gross jump across adjacent horizons",
            str(ctx.get("candidate_csv", "")),
        )
        add_edge_metric(
            2,
            sym,
            "M03_positive_density",
            positive_density,
            "Share of selected hypotheses with positive mean gross",
            str(ctx.get("candidate_csv", "")),
        )
        if not selected.empty:
            q = selected[["symbol", "annualized_test_fills", "mean_gross_pips_test"]].copy()
            q["symbol"] = sym
            mining_scatter_rows.append(q)
    stage02 = pd.DataFrame(mining_summary_rows)
    stage02_scatter = (
        pd.concat(mining_scatter_rows, ignore_index=True) if mining_scatter_rows else pd.DataFrame()
    )
    stage02_plot = _stage_plot_path(outputs, 2, "selected_scatter")
    if not stage02_scatter.empty:
        _plot_stage_scatter(
            df=stage02_scatter,
            x="annualized_test_fills",
            y="mean_gross_pips_test",
            hue="symbol",
            title="Stage 2: Selected Candidates (Gross vs Annualized Fills)",
            xlabel="Annualized test fills",
            ylabel="Mean gross pips (test)",
            out_path=stage02_plot,
        )
    stage02_content = _render_stage_snapshot(
        stage_id=2,
        now_utc=now_utc,
        summary_table=stage02 if not stage02.empty else pd.DataFrame(),
        details_table=None,
        notes=[
            "selection_pass candidates are broad hypotheses only.",
            "Scatter shows the high-count >0 gross opportunity frontier.",
            "M01-M03 quantify concentration risk, horizon smoothness, and positive-edge density.",
        ],
        figure_paths=[stage02_plot] if stage02_plot.exists() else [],
        figure_prefix="../figures/oco_bible/",
        action_summary_table=stage_action_table(2),
    )
    stage02_state = pd.DataFrame([r for r in edge_state_rows if int(_num(r.get("stage_id"))) == 2])
    if not stage02_state.empty:
        top_state = (
            stage02_state.sort_values(["symbol", "contrib_share"], ascending=[True, False])
            .groupby("symbol", as_index=False)
            .head(8)
        )
        stage02_content += "\n\n#### Edge Contribution by State Block\n" + _table(
            _pick_cols(
                top_state,
                [
                    "symbol",
                    "family",
                    "state_id",
                    "bar_ticks",
                    "horizon",
                    "edge_weight",
                    "contrib_share",
                ],
            )
        )
    if not stage23_overfit.empty:
        stage02_content += (
            "\n\n#### Overfitting Diagnostics (Downstream, Exec Quantile)\n"
            + _table(stage23_overfit)
            + "\n\n"
            + "- Interpretation: Stage 2 mining is accepted only as hypothesis generation; false-discovery control is enforced downstream via Stage 3/8 out-of-sample evaluation.\n"
            + "- Multiplicity fields (`pvalue_bonferroni`, `pvalue_fdr_bh`) are reported at the execution quantile and should be used with LB95/month-consistency, not in isolation."
        )
    write_stage(2, stage02_content)

    # Stage 03: Monthly WFO.
    exec_q = float(cfg.get("gate_thresholds", {}).get("robustness_quantile", 0.9))
    wfo_rows: list[pd.DataFrame] = []
    wfo_summary_rows: list[dict[str, Any]] = []
    wfo_skip_rows: list[pd.DataFrame] = []
    stage03_leak_rows: list[dict[str, Any]] = []
    for ctx in contexts:
        sym = ctx["symbol"]
        summary_idx = -1
        metrics = _safe_read_csv(ctx.get("wfo_metrics_csv"))
        thresholds = _safe_read_csv(ctx.get("wfo_thresholds_csv"))
        preds = _safe_read_parquet(
            ctx.get("wfo_predictions_parquet"),
            columns=["test_month", "candidate_uid", "selected_exec", "pred_prob"],
        )
        skips = _safe_read_csv(ctx.get("wfo_skip_reasons_csv"))
        leakage = _safe_read_csv(ctx.get("leakage_checks_csv"))
        w13_fragility = float("nan")
        w14_brier_drift = float("nan")
        w15_turnover = float("nan")
        if not metrics.empty:
            wfo_summary_rows.append(
                {
                    "symbol": sym,
                    "months": int(len(metrics)),
                    "auc_mean": _num(metrics.get("auc", pd.Series(dtype=float)).mean()),
                    "brier_mean": _num(metrics.get("brier", pd.Series(dtype=float)).mean()),
                    "test_rows_total": _num(metrics.get("test_rows", pd.Series(dtype=float)).sum()),
                }
            )
            summary_idx = len(wfo_summary_rows) - 1
            add_metric(
                3,
                "auc_mean",
                sym,
                _num(metrics.get("auc", pd.Series(dtype=float)).mean()),
                "auc",
                str(ctx.get("wfo_metrics_csv", "")),
            )
            w14_brier_drift = _month_series_std(metrics.get("brier", pd.Series(dtype=float)))
        if not thresholds.empty and "quantile" in thresholds.columns:
            q = thresholds[pd.to_numeric(thresholds["quantile"], errors="coerce") == exec_q].copy()
            if not q.empty:
                q["symbol"] = sym
                wfo_rows.append(
                    q[["symbol", "test_month", "mean_gross_pips", "coverage", "selected_rows"]]
                )
            qq = thresholds.copy()
            qq["quantile"] = pd.to_numeric(qq["quantile"], errors="coerce")
            qq["mean_gross_pips"] = pd.to_numeric(qq.get("mean_gross_pips"), errors="coerce")
            qq = qq.dropna(subset=["quantile", "mean_gross_pips"])
            if not qq.empty:
                qg = (
                    qq.groupby("quantile", as_index=False)
                    .agg(
                        mean_gross_pips=("mean_gross_pips", "mean"),
                        coverage=("coverage", "mean"),
                        selected_rows=("selected_rows", "mean"),
                    )
                    .sort_values("quantile")
                )
                nearest = (
                    qg.iloc[(qg["quantile"] - exec_q).abs().argsort()]
                    .head(3)
                    .sort_values("quantile")
                )
                if len(nearest) >= 2:
                    dy = _num(nearest["mean_gross_pips"].max() - nearest["mean_gross_pips"].min())
                    dq = _num(nearest["quantile"].max() - nearest["quantile"].min())
                    w13_fragility = _safe_div(dy, dq)
                nearest = nearest.copy()
                nearest["test_month"] = "aggregate"
                nearest["symbol"] = sym
                nearest["stage_id"] = 3
                edge_threshold_rows.extend(nearest.to_dict(orient="records"))
        if not preds.empty:
            p = preds.copy()
            p["selected_exec"] = (
                pd.to_numeric(p.get("selected_exec"), errors="coerce").fillna(0).astype(int)
            )
            p = p[p["selected_exec"] == 1].copy()
            if not p.empty:
                p["test_month"] = p["test_month"].astype(str)
                sets = (
                    p.groupby("test_month")["candidate_uid"]
                    .apply(lambda s: set(s.astype(str)))
                    .sort_index()
                )
                jac: list[float] = []
                for i in range(1, len(sets)):
                    a = sets.iloc[i - 1]
                    b = sets.iloc[i]
                    den = len(a | b)
                    jac.append(float(len(a & b) / den) if den else float("nan"))
                if jac:
                    w15_turnover = _num(1.0 - pd.Series(jac).mean())
        if not skips.empty:
            skips["symbol"] = sym
            wfo_skip_rows.append(skips)
        if not leakage.empty:
            if "symbol" in leakage.columns:
                leakage = leakage[leakage["symbol"].astype(str).str.upper() == sym].copy()
            leak_focus = leakage[
                leakage.get("check_id", pd.Series(index=leakage.index, dtype=str))
                .astype(str)
                .isin(["L01", "L02", "L03", "L04", "L06", "L09"])
            ].copy()
            if not leak_focus.empty:
                fail = leak_focus["status"].astype(str).str.lower() != "pass"
                sev = (
                    leak_focus.get("severity_if_fail", pd.Series(index=leak_focus.index, dtype=str))
                    .astype(str)
                    .str.lower()
                )
                stage03_leak_rows.append(
                    {
                        "symbol": sym,
                        "checks_total": int(len(leak_focus)),
                        "checks_failed": int(fail.sum()),
                        "high_critical_failed": int((fail & sev.isin(["high", "critical"])).sum()),
                    }
                )
        add_edge_metric(
            3,
            sym,
            "W13_threshold_fragility",
            w13_fragility,
            "Mean-gross sensitivity around execution quantile",
            str(ctx.get("wfo_thresholds_csv", "")),
        )
        add_edge_metric(
            3,
            sym,
            "W14_brier_drift_std",
            w14_brier_drift,
            "Std of monthly Brier score (calibration drift)",
            str(ctx.get("wfo_metrics_csv", "")),
        )
        add_edge_metric(
            3,
            sym,
            "W15_selection_turnover",
            w15_turnover,
            "1 - consecutive-month Jaccard of selected candidate_uids",
            str(ctx.get("wfo_predictions_parquet", "")),
        )
        if summary_idx >= 0:
            wfo_summary_rows[summary_idx]["w13_threshold_fragility"] = w13_fragility
            wfo_summary_rows[summary_idx]["w14_brier_drift_std"] = w14_brier_drift
            wfo_summary_rows[summary_idx]["w15_selection_turnover"] = w15_turnover
    stage03_summary = pd.DataFrame(wfo_summary_rows)
    stage03_monthly = pd.concat(wfo_rows, ignore_index=True) if wfo_rows else pd.DataFrame()
    stage03_plot = _stage_plot_path(outputs, 3, "wfo_monthly_gross")
    if not stage03_monthly.empty:
        _plot_stage_lines(
            df=stage03_monthly,
            x="test_month",
            y="mean_gross_pips",
            hue="symbol",
            title=f"Stage 3: Monthly WFO Gross (q={exec_q})",
            ylabel="mean gross pips",
            out_path=stage03_plot,
        )
    stage03_detail = (
        stage03_monthly.groupby("symbol", as_index=False).agg(
            months=("test_month", "nunique"),
            mean_coverage=("coverage", "mean"),
            mean_gross_pips=("mean_gross_pips", "mean"),
            rows_selected=("selected_rows", "sum"),
        )
        if not stage03_monthly.empty
        else None
    )
    stage03_content = _render_stage_snapshot(
        stage_id=3,
        now_utc=now_utc,
        summary_table=stage03_summary if not stage03_summary.empty else pd.DataFrame(),
        details_table=stage03_detail,
        notes=[
            f"Execution threshold summary is aligned to quantile={exec_q}.",
            "Metrics are strictly month-forward (3M train -> 1M test).",
            "W13-W15 are informational diagnostics for threshold fragility, calibration drift, and selection turnover.",
        ],
        figure_paths=[stage03_plot] if stage03_plot.exists() else [],
        figure_prefix="../figures/oco_bible/",
        action_summary_table=stage_action_table(3),
    )
    stage03_thr = pd.DataFrame(
        [r for r in edge_threshold_rows if int(_num(r.get("stage_id"))) == 3]
    )
    if not stage03_thr.empty:
        stage03_content += "\n\n#### Threshold Robustness Around Execution Quantile\n" + _table(
            _pick_cols(
                stage03_thr,
                [
                    "symbol",
                    "test_month",
                    "quantile",
                    "mean_gross_pips",
                    "coverage",
                    "selected_rows",
                ],
            )
        )
    stage03_skip = pd.concat(wfo_skip_rows, ignore_index=True) if wfo_skip_rows else pd.DataFrame()
    if not stage03_skip.empty and {"symbol", "reason_code"}.issubset(set(stage03_skip.columns)):
        s3 = (
            stage03_skip.groupby(["symbol", "reason_code"], as_index=False)
            .agg(
                months=("test_month", "nunique"),
                rows_affected=("rows_affected", "sum"),
                avg_pct_month_rows=("pct_month_rows", "mean"),
            )
            .sort_values(["symbol", "months", "rows_affected"], ascending=[True, False, False])
        )
        stage03_content += "\n\n#### Skip Reason Distribution\n" + _table(s3)
    if not stage23_overfit.empty:
        stage03_content += (
            "\n\n#### Overfitting Diagnostics (Exec Quantile)\n"
            + _table(stage23_overfit)
            + "\n\n"
            + "- Interpretation: these diagnostics are computed on WFO out-of-sample predictions only.\n"
            + "- `bonferroni_pass_10pct` and `fdr_pass_10pct` summarize multiplicity-adjusted significance at alpha=0.10."
        )
    stage03_leak = pd.DataFrame(stage03_leak_rows)
    if not stage03_leak.empty:
        stage03_content += "\n\n#### Leakage/Label Integrity (WFO Focus)\n" + _table(stage03_leak)
    write_stage(3, stage03_content)

    # Stage 04: Stop-limit execution.
    stage04_summary_rows: list[dict[str, Any]] = []
    caps_rows: list[pd.DataFrame] = []
    drift_rows: list[pd.DataFrame] = []
    stage04_exec_rows: list[dict[str, Any]] = []
    stage04_policy_rows: list[dict[str, Any]] = []
    stage04_cap_policy_rows: list[pd.DataFrame] = []
    stage04_policy_metrics = [
        "E11_session_overshoot_dispersion",
        "E12_cap_plateau_width_pips",
        "E13_nonfill_opportunity_cost_pips",
        "erosion_spread_fee_plus_slip",
        "tick_overshoot_p95_pips",
    ]
    for ctx in contexts:
        sym = ctx["symbol"]
        stage04_idx = -1
        s = _safe_read_csv(ctx.get("stop_limit_summary_csv"))
        c = _safe_read_csv(ctx.get("stop_limit_caps_csv"))
        detail = _safe_read_csv(ctx.get("stop_limit_detail_csv"))
        drift = _safe_read_csv(ctx.get("stop_limit_fill_drift_csv"))
        er = _safe_read_csv(ctx.get("execution_risk_checks_csv"))
        e11_session_overshoot_dispersion = float("nan")
        e12_plateau_width = float("nan")
        e13_nonfill_opportunity_cost = float("nan")
        e4_per_signal_realized = float("nan")
        best_cap_pips = float("nan")
        best_fill_rate = float("nan")
        if not s.empty:
            if "symbol" in s.columns:
                ss = s[s["symbol"].astype(str).str.upper() == sym].copy()
                row = (ss.iloc[0] if not ss.empty else s.iloc[0]).to_dict()
            else:
                row = s.iloc[0].to_dict()
            row["symbol"] = sym
            stage04_summary_rows.append(row)
            stage04_idx = len(stage04_summary_rows) - 1
            add_metric(
                4,
                "tick_overshoot_mean_pips",
                sym,
                row.get("tick_overshoot_mean_pips"),
                "pips",
                str(ctx.get("stop_limit_summary_csv", "")),
            )
            slip = _num(row.get("tick_overshoot_mean_pips"))
            add_edge_metric(
                4,
                sym,
                "erosion_overshoot_component",
                slip,
                "Average overshoot pips at tick first-cross",
                str(ctx.get("stop_limit_summary_csv", "")),
            )
        if not c.empty:
            cc = c.copy()
            if "symbol" in cc.columns:
                cc = cc[cc["symbol"].astype(str).str.upper() == sym].copy()
            if not cc.empty:
                cc["symbol"] = sym
                caps_rows.append(cc)
                if {"cap_pips", "mean_per_signal_full_overshoot"}.issubset(set(cc.columns)):
                    cc2 = cc.copy()
                    cc2["cap_pips"] = pd.to_numeric(cc2["cap_pips"], errors="coerce")
                    cc2["mean_per_signal_full_overshoot"] = pd.to_numeric(
                        cc2["mean_per_signal_full_overshoot"], errors="coerce"
                    )
                    cc2 = cc2.dropna(
                        subset=["cap_pips", "mean_per_signal_full_overshoot"]
                    ).sort_values("cap_pips")
                    if not cc2.empty:
                        best = _num(cc2["mean_per_signal_full_overshoot"].max())
                        near = cc2[
                            cc2["mean_per_signal_full_overshoot"]
                            >= (0.95 * best if math.isfinite(best) else float("nan"))
                        ]
                        if len(near) >= 2:
                            e12_plateau_width = _num(
                                near["cap_pips"].max() - near["cap_pips"].min()
                            )
                    if not cc2.empty and {
                        "mean_per_signal_no_extra_slip",
                        "mean_per_signal_full_overshoot",
                        "fill_rate",
                    }.issubset(set(cc2.columns)):
                        cc_best = cc2.iloc[cc2["mean_per_signal_full_overshoot"].argmax()]
                        ideal = _num(cc_best.get("mean_per_signal_no_extra_slip"))
                        real = _num(cc_best.get("mean_per_signal_full_overshoot"))
                        fill = _num(cc_best.get("fill_rate"))
                        best_cap_pips = _num(cc_best.get("cap_pips"))
                        best_fill_rate = fill
                        e4_per_signal_realized = real
                        e13_nonfill_opportunity_cost = (
                            (ideal - real) * fill
                            if all(math.isfinite(v) for v in [ideal, real, fill])
                            else float("nan")
                        )
        if not drift.empty:
            dd = drift.copy()
            if "symbol" in dd.columns:
                dd = dd[dd["symbol"].astype(str).str.upper() == sym].copy()
            if not dd.empty:
                dd["symbol"] = sym
                drift_rows.append(dd)
        if not er.empty:
            if "symbol" in er.columns:
                er = er[er["symbol"].astype(str).str.upper() == sym].copy()
            if not er.empty:
                fail = er["status"].astype(str).str.lower() != "pass"
                sev = (
                    er.get("severity_if_fail", pd.Series(index=er.index, dtype=str))
                    .astype(str)
                    .str.lower()
                )
                m_by_id = (
                    er.set_index("check_id")["metric_value"]
                    if "check_id" in er.columns and "metric_value" in er.columns
                    else pd.Series(dtype=float)
                )
                stage04_exec_rows.append(
                    {
                        "symbol": sym,
                        "checks_total": int(len(er)),
                        "checks_failed": int(fail.sum()),
                        "high_critical_failed": int((fail & sev.isin(["high", "critical"])).sum()),
                        "e02_min_month_fill_rate": _num(m_by_id.get("E02")),
                        "e03_tail_above_cap": _num(m_by_id.get("E03")),
                        "e10_lb95_month_signal_net": _num(m_by_id.get("E10")),
                    }
                )
        if not detail.empty and {"overshoot_tick_pips", "touch_open_ts"}.issubset(
            set(detail.columns)
        ):
            d = detail.copy()
            if "side" in d.columns:
                side_norm = pd.to_numeric(d["side"], errors="coerce")
                is_num_side = side_norm.isin([-1, 1])
                is_text_side = d["side"].astype(str).str.upper().isin(["BUY", "SELL"])
                d = d[is_num_side | is_text_side].copy()
            if "touch_found_tick" in d.columns:
                d["touch_found_tick"] = (
                    pd.to_numeric(d["touch_found_tick"], errors="coerce").fillna(0).astype(int)
                )
                d = d[d["touch_found_tick"] == 1].copy()
            d["touch_open_ts"] = pd.to_datetime(d["touch_open_ts"], utc=True, errors="coerce")
            d["overshoot_tick_pips"] = pd.to_numeric(d["overshoot_tick_pips"], errors="coerce")
            d = d.dropna(subset=["touch_open_ts", "overshoot_tick_pips"])
            if not d.empty:
                d_cap, cap_policy = _rolling_session_cap_table(
                    d,
                    symbol=sym,
                    lookback_days=20,
                    cap_quantile=0.90,
                    min_periods=200,
                )
                if not cap_policy.empty:
                    stage04_cap_policy_rows.append(cap_policy)
                if not d_cap.empty:
                    by_session = d_cap.groupby("session_bucket")["overshoot_capped_pips"].mean()
                    if len(by_session) > 1:
                        e11_session_overshoot_dispersion = _safe_div(
                            _num(by_session.std(ddof=1)), _num(by_session.mean())
                        )
                    if stage04_idx >= 0:
                        stage04_summary_rows[stage04_idx]["stage04_cap_lookback_days"] = 20
                        stage04_summary_rows[stage04_idx]["stage04_cap_quantile"] = 0.90
                        stage04_summary_rows[stage04_idx]["stage04_cap_sessions"] = int(
                            by_session.shape[0]
                        )
        erosion = float("nan")
        if stage04_idx >= 0:
            base = _num(stage04_summary_rows[stage04_idx].get("base_mean_gross_pips"))
            erosion = (
                base - e4_per_signal_realized
                if math.isfinite(base) and math.isfinite(e4_per_signal_realized)
                else float("nan")
            )
            add_edge_metric(
                4,
                sym,
                "erosion_spread_fee_plus_slip",
                erosion,
                "Gross-to-per-signal erosion including overshoot realism",
                str(ctx.get("stop_limit_caps_csv", "")),
            )
        add_edge_metric(
            4,
            sym,
            "E11_session_overshoot_dispersion",
            e11_session_overshoot_dispersion,
            "CV of mean overshoot across sessions after causal rolling session caps (20D, q=0.90)",
            str(ctx.get("stop_limit_detail_csv", "")),
        )
        add_edge_metric(
            4,
            sym,
            "E12_cap_plateau_width_pips",
            e12_plateau_width,
            "Cap width where performance remains >=95% of best",
            str(ctx.get("stop_limit_caps_csv", "")),
        )
        add_edge_metric(
            4,
            sym,
            "E13_nonfill_opportunity_cost_pips",
            e13_nonfill_opportunity_cost,
            "Estimated opportunity cost at best cap (ideal-realized)*fill",
            str(ctx.get("stop_limit_caps_csv", "")),
        )
        if stage04_idx >= 0:
            stage04_summary_rows[stage04_idx]["e11_session_overshoot_dispersion"] = (
                e11_session_overshoot_dispersion
            )
            stage04_summary_rows[stage04_idx]["e12_cap_plateau_width_pips"] = e12_plateau_width
            stage04_summary_rows[stage04_idx]["e13_nonfill_opportunity_cost_pips"] = (
                e13_nonfill_opportunity_cost
            )
            stage04_summary_rows[stage04_idx]["erosion_spread_fee_plus_slip"] = erosion
            stage04_summary_rows[stage04_idx]["best_cap_pips"] = best_cap_pips
            stage04_summary_rows[stage04_idx]["best_fill_rate"] = best_fill_rate
        policy_source = str(ctx.get("stop_limit_caps_csv", ""))
        policy_values: dict[str, Any] = {
            "E11_session_overshoot_dispersion": e11_session_overshoot_dispersion,
            "E12_cap_plateau_width_pips": e12_plateau_width,
            "E13_nonfill_opportunity_cost_pips": e13_nonfill_opportunity_cost,
            "erosion_spread_fee_plus_slip": erosion,
            "tick_overshoot_p95_pips": _num(
                stage04_summary_rows[stage04_idx].get("tick_overshoot_p95_pips")
                if stage04_idx >= 0
                else float("nan")
            ),
        }
        for metric_id in stage04_policy_metrics:
            mapped = _stage04_policy_for_metric(metric_id, policy_values.get(metric_id))
            stage04_policy_rows.append(
                {
                    "symbol": sym,
                    "metric_id": metric_id,
                    "metric_value": mapped["metric_value"],
                    "direction": mapped["direction"],
                    "band": mapped["band"],
                    "action_code": mapped["action_code"],
                    "action_summary": mapped["action_summary"],
                    "green_threshold": mapped["green_threshold"],
                    "amber_threshold": mapped["amber_threshold"],
                    "source_path": _to_repo_rel(policy_source),
                    "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                }
            )
    stage04 = pd.DataFrame(stage04_summary_rows)
    stage04_policy = pd.DataFrame(stage04_policy_rows)
    stage04_policy_csv = outputs.stage_metrics_csv.parent / "stage04_execution_policy_status.csv"
    stage04_cap_policy_csv = outputs.stage_metrics_csv.parent / "stage04_cap_policy_by_session.csv"
    stage04_policy_csv.parent.mkdir(parents=True, exist_ok=True)
    if stage04_policy.empty:
        stage04_policy = pd.DataFrame(
            columns=[
                "symbol",
                "metric_id",
                "metric_value",
                "direction",
                "band",
                "action_code",
                "action_summary",
                "green_threshold",
                "amber_threshold",
                "source_path",
                "generated_at_utc",
            ]
        )
    stage04_policy.to_csv(stage04_policy_csv, index=False)
    stage04_cap_policy = (
        pd.concat(stage04_cap_policy_rows, ignore_index=True)
        if stage04_cap_policy_rows
        else pd.DataFrame()
    )
    if stage04_cap_policy.empty:
        stage04_cap_policy = pd.DataFrame(
            columns=[
                "symbol",
                "session_bucket",
                "lookback_days",
                "cap_quantile",
                "cap_pips",
                "rows_used",
                "session_cap_rows",
                "global_cap_rows",
                "fallback_rows",
                "generated_at_utc",
            ]
        )
    stage04_cap_policy.to_csv(stage04_cap_policy_csv, index=False)
    stage04_policy_rollup = _stage04_policy_rollup_rows(stage04_policy)
    stage04_caps = pd.concat(caps_rows, ignore_index=True) if caps_rows else pd.DataFrame()
    stage04_plot = _stage_plot_path(outputs, 4, "stop_limit_caps")
    stage04_policy_plot = _stage_plot_path(outputs, 4, "execution_policy_bands")
    if not stage04_caps.empty:
        _plot_stage_lines(
            df=stage04_caps,
            x="cap_pips",
            y="mean_per_signal_full_overshoot",
            hue="symbol",
            title="Stage 4: Stop-Limit Cap vs Per-Signal PnL",
            ylabel="mean per-signal pips",
            out_path=stage04_plot,
        )
    if not stage04_policy_rollup.empty:
        _plot_stage_bars(
            df=stage04_policy_rollup,
            x="symbol",
            ys=["red_metric_count", "amber_metric_count", "green_metric_count"],
            title="Stage 4: Execution Policy Band Counts",
            ylabel="metric count",
            out_path=stage04_policy_plot,
        )
    stage04_details = _pick_cols(
        stage04_caps, ["symbol", "cap_pips", "fill_rate", "mean_per_signal_full_overshoot"]
    )
    if not stage04_details.empty and {"symbol", "cap_pips"}.issubset(set(stage04_details.columns)):
        stage04_details = stage04_details.sort_values(["symbol", "cap_pips"])
    stage04_content = _render_stage_snapshot(
        stage_id=4,
        now_utc=now_utc,
        summary_table=_pick_cols(
            stage04,
            [
                "symbol",
                "rows",
                "touch_found_rate",
                "base_mean_gross_pips",
                "tick_overshoot_mean_pips",
                "tick_overshoot_p95_pips",
                "e11_session_overshoot_dispersion",
                "e12_cap_plateau_width_pips",
                "e13_nonfill_opportunity_cost_pips",
            ],
        )
        if not stage04.empty
        else pd.DataFrame(),
        details_table=stage04_details if not stage04_details.empty else None,
        notes=[
            "Execution realism is applied with tick first-cross overshoot.",
            "Session-aware rolling caps are built causally (20D lookback, q=0.90) before E11 dispersion is measured.",
            "Cap curve highlights fill-rate versus signal-level expectancy.",
            "E11-E13 are informational execution diagnostics: session dispersion, plateau width, and non-fill opportunity cost.",
            f"Policy status artifact: {_to_repo_rel(stage04_policy_csv)}",
            f"Session cap artifact: {_to_repo_rel(stage04_cap_policy_csv)}",
        ],
        figure_paths=[p for p in [stage04_plot, stage04_policy_plot] if p.exists()],
        figure_prefix="../figures/oco_bible/",
        action_summary_table=stage_action_table(4),
    )
    stage04_drift = pd.concat(drift_rows, ignore_index=True) if drift_rows else pd.DataFrame()
    if not stage04_drift.empty:
        d4 = _pick_cols(
            stage04_drift,
            [
                "symbol",
                "test_month",
                "session",
                "touch_found_rate",
                "overshoot_p95",
                "touch_found_rate_drop",
                "drift_z",
                "pass",
            ],
        )
        stage04_content += "\n\n#### Fill Drift\n" + _table(d4)
    stage04_exec = pd.DataFrame(stage04_exec_rows)
    if not stage04_exec.empty:
        stage04_content += "\n\n#### Execution Risk Pre-Live\n" + _table(stage04_exec)
    if not stage04_policy_rollup.empty:
        stage04_content += "\n\n#### Policy Status\n" + _table(
            _pick_cols(
                stage04_policy_rollup,
                [
                    "symbol",
                    "metrics_total",
                    "green_metric_count",
                    "amber_metric_count",
                    "red_metric_count",
                    "worst_band",
                    "recommended_action_code",
                    "recommended_action_summary",
                    "red_metrics",
                    "amber_metrics",
                ],
            )
        )
        stage04_content += "\n\n- policy_csv: " + f"`{_to_repo_rel(stage04_policy_csv)}`"
    if not stage04_policy.empty:
        stage04_content += "\n\n#### Policy Metric Mapping (Detail)\n" + _table(
            _pick_cols(
                stage04_policy,
                [
                    "symbol",
                    "metric_id",
                    "metric_value",
                    "band",
                    "action_code",
                    "green_threshold",
                    "amber_threshold",
                ],
            )
        )
    if not stage04_cap_policy.empty:
        stage04_content += "\n\n#### Session Rolling Cap Policy\n" + _table(
            _pick_cols(
                stage04_cap_policy,
                [
                    "symbol",
                    "session_bucket",
                    "lookback_days",
                    "cap_quantile",
                    "cap_pips",
                    "rows_used",
                    "session_cap_rows",
                    "global_cap_rows",
                    "fallback_rows",
                ],
            )
        )
    write_stage(4, stage04_content)

    # Stage 05: Reduced-core rolling.
    stage05_summary_rows: list[dict[str, Any]] = []
    stage05_monthly_rows: list[pd.DataFrame] = []
    stage05_churn_rows: list[pd.DataFrame] = []
    stage05_leak_rows: list[dict[str, Any]] = []
    for ctx in contexts:
        sym = ctx["symbol"]
        stage05_idx = -1
        rs = _safe_read_csv(ctx.get("reduced_summary_csv"))
        rm = _safe_read_csv(ctx.get("reduced_monthly_csv"))
        rc = _safe_read_csv(ctx.get("reduced_churn_csv"))
        sched = _safe_read_csv(ctx.get("reduced_state_schedule_csv"))
        th = _safe_read_csv(ctx.get("wfo_thresholds_csv"))
        leakage = _safe_read_csv(ctx.get("leakage_checks_csv"))
        r01_overprune = float("nan")
        r02_dependency = float("nan")
        r03_reselect_stability = float("nan")
        if not rs.empty:
            row = rs.iloc[0].to_dict()
            row["symbol"] = sym
            stage05_summary_rows.append(row)
            stage05_idx = len(stage05_summary_rows) - 1
            add_metric(
                5,
                "lb95_month_mean_gross_pips",
                sym,
                row.get("lb95_month_mean_gross_pips"),
                "pips",
                str(ctx.get("reduced_summary_csv", "")),
            )
            r02_dependency = _num(row.get("top_state_share"))
            if not math.isfinite(r02_dependency):
                r02_dependency = _num(row.get("max_top_state_share"))
        if not rm.empty:
            m = rm.copy()
            m["symbol"] = sym
            stage05_monthly_cols = [
                "symbol",
                "test_month",
                "mean_gross_pips",
                "fill_rate",
                "rows",
                "states_selected",
            ]
            stage05_monthly_avail = [c for c in stage05_monthly_cols if c in m.columns]
            stage05_monthly_rows.append(m[stage05_monthly_avail])
            m["stability_pass"] = _to_bool_series(
                m.get("stability_pass", pd.Series(index=m.index, dtype=str))
            )
            r03_reselect_stability = _num(m["stability_pass"].mean())
        if not rc.empty:
            c = rc.copy()
            c["symbol"] = sym
            stage05_churn_rows.append(c)
            if "state_churn_rate" in c.columns:
                r03_reselect_stability = _num(
                    1.0 - pd.to_numeric(c["state_churn_rate"], errors="coerce").mean()
                )
        if not sched.empty:
            add_metric(
                5,
                "states_scheduled",
                sym,
                len(sched),
                "rows",
                str(ctx.get("reduced_state_schedule_csv", "")),
            )
        if not th.empty and "quantile" in th.columns:
            tq = th[pd.to_numeric(th["quantile"], errors="coerce") == exec_q].copy()
            if not tq.empty:
                pre_rows = _num(pd.to_numeric(tq["selected_rows"], errors="coerce").sum())
                post_rows = (
                    _num(
                        pd.to_numeric(rm.get("rows", pd.Series(dtype=float)), errors="coerce").sum()
                    )
                    if not rm.empty
                    else float("nan")
                )
                r01_overprune = _safe_div(post_rows, pre_rows)
        if not leakage.empty:
            if "symbol" in leakage.columns:
                leakage = leakage[leakage["symbol"].astype(str).str.upper() == sym].copy()
            leak_focus = leakage[
                leakage.get("check_id", pd.Series(index=leakage.index, dtype=str))
                .astype(str)
                .isin(["L05", "L10", "L11"])
            ].copy()
            if not leak_focus.empty:
                fail = leak_focus["status"].astype(str).str.lower() != "pass"
                stage05_leak_rows.append(
                    {
                        "symbol": sym,
                        "checks_total": int(len(leak_focus)),
                        "checks_failed": int(fail.sum()),
                        "failed_check_ids": ",".join(
                            leak_focus.loc[fail, "check_id"].astype(str).tolist()
                        ),
                    }
                )
        if math.isnan(r01_overprune):
            r01_overprune = 0.0
        if math.isnan(r02_dependency):
            r02_dependency = 0.0
        if math.isnan(r03_reselect_stability):
            r03_reselect_stability = 0.0
        add_edge_metric(
            5,
            sym,
            "R01_post_pre_row_ratio",
            r01_overprune,
            "Reduced-core rows / pre-filter WFO selected rows",
            str(ctx.get("reduced_monthly_csv", "")),
        )
        add_edge_metric(
            5,
            sym,
            "R02_top_state_dependency",
            r02_dependency,
            "Top-state share from reduced summary",
            str(ctx.get("reduced_summary_csv", "")),
        )
        add_edge_metric(
            5,
            sym,
            "R03_reselection_stability",
            r03_reselect_stability,
            "1-churn proxy / stability pass rate",
            str(ctx.get("reduced_churn_csv", "")),
        )
        if stage05_idx >= 0:
            stage05_summary_rows[stage05_idx]["r01_post_pre_row_ratio"] = r01_overprune
            stage05_summary_rows[stage05_idx]["r02_top_state_dependency"] = r02_dependency
            stage05_summary_rows[stage05_idx]["r03_reselection_stability"] = r03_reselect_stability
    stage05_summary = pd.DataFrame(stage05_summary_rows)
    stage05_monthly = (
        pd.concat(stage05_monthly_rows, ignore_index=True)
        if stage05_monthly_rows
        else pd.DataFrame()
    )
    stage05_plot = _stage_plot_path(outputs, 5, "reduced_monthly_gross")
    if not stage05_monthly.empty:
        _plot_stage_lines(
            df=stage05_monthly,
            x="test_month",
            y="mean_gross_pips",
            hue="symbol",
            title="Stage 5: Reduced-Core Monthly Mean Gross",
            ylabel="mean gross pips",
            out_path=stage05_plot,
        )
    stage05_detail = (
        stage05_monthly.groupby("symbol", as_index=False).agg(
            months=("test_month", "nunique"),
            rows_total=("rows", "sum"),
            mean_fill_rate=("fill_rate", "mean"),
            mean_gross=("mean_gross_pips", "mean"),
        )
        if not stage05_monthly.empty
        else None
    )
    stage05_content = _render_stage_snapshot(
        stage_id=5,
        now_utc=now_utc,
        summary_table=_pick_cols(
            stage05_summary,
            [
                "symbol",
                "rows_total",
                "mean_gross_pips",
                "lb95_month_mean_gross_pips",
                "fill_rate_overall",
                "positive_months",
                "months_total",
                "r01_post_pre_row_ratio",
                "r02_top_state_dependency",
                "r03_reselection_stability",
            ],
        )
        if not stage05_summary.empty
        else pd.DataFrame(),
        details_table=stage05_detail,
        notes=[
            "State schedule is selected month-by-month using only prior-month train data.",
            "Summary emphasizes full-path gross behavior after reduced-core filtering.",
            "R01-R03 track pruning severity, state concentration, and re-selection stability.",
        ],
        figure_paths=[stage05_plot] if stage05_plot.exists() else [],
        figure_prefix="../figures/oco_bible/",
        action_summary_table=stage_action_table(5),
    )
    stage05_churn = (
        pd.concat(stage05_churn_rows, ignore_index=True) if stage05_churn_rows else pd.DataFrame()
    )
    if not stage05_churn.empty:
        c5 = _pick_cols(
            stage05_churn,
            [
                "symbol",
                "test_month",
                "states_selected",
                "state_churn_rate",
                "top_state_share",
                "state_hhi",
                "stability_pass",
                "status",
            ],
        )
        stage05_content += "\n\n#### State Churn\n" + _table(c5)
    stage05_leak = pd.DataFrame(stage05_leak_rows)
    if not stage05_leak.empty:
        stage05_content += "\n\n#### Leakage/Label Integrity (Reduced-Core Focus)\n" + _table(
            stage05_leak
        )
    write_stage(5, stage05_content)

    # Stage 06: Tick-exact verification.
    stage06_summary_rows: list[dict[str, Any]] = []
    stage06_monthly_rows: list[pd.DataFrame] = []
    stage06_replay_rows: list[pd.DataFrame] = []
    for ctx in contexts:
        sym = ctx["symbol"]
        ts = _safe_read_csv(ctx.get("tick_exact_summary_csv"))
        tm = _safe_read_csv(ctx.get("tick_exact_monthly_csv"))
        tr = _safe_read_csv(ctx.get("tick_exact_replay_csv"))
        if not ts.empty:
            row = ts.iloc[0].to_dict()
            row["symbol"] = sym
            stage06_summary_rows.append(row)
            add_metric(
                6,
                "exact_match_rate",
                sym,
                row.get("exact_match_rate"),
                "rate",
                str(ctx.get("tick_exact_summary_csv", "")),
            )
        if not tm.empty:
            m = tm.copy()
            m["symbol"] = sym
            stage06_monthly_rows.append(
                m[["symbol", "test_month", "exact_match_rate", "pos_label_match_rate"]]
            )
        if not tr.empty:
            r = tr.copy()
            r["symbol"] = sym
            stage06_replay_rows.append(r)
    stage06_summary = pd.DataFrame(stage06_summary_rows)
    stage06_monthly = (
        pd.concat(stage06_monthly_rows, ignore_index=True)
        if stage06_monthly_rows
        else pd.DataFrame()
    )
    stage06_plot = _stage_plot_path(outputs, 6, "tick_exact_monthly")
    if not stage06_monthly.empty:
        _plot_stage_lines(
            df=stage06_monthly,
            x="test_month",
            y="exact_match_rate",
            hue="symbol",
            title="Stage 6: Monthly Tick-Exact Match Rate",
            ylabel="exact match rate",
            out_path=stage06_plot,
        )
    stage06_detail = (
        stage06_monthly.groupby("symbol", as_index=False).agg(
            months=("test_month", "nunique"),
            exact_min=("exact_match_rate", "min"),
            exact_mean=("exact_match_rate", "mean"),
            pos_min=("pos_label_match_rate", "min"),
            pos_mean=("pos_label_match_rate", "mean"),
        )
        if not stage06_monthly.empty
        else None
    )
    stage06_content = _render_stage_snapshot(
        stage_id=6,
        now_utc=now_utc,
        summary_table=_pick_cols(
            stage06_summary,
            [
                "symbol",
                "rows_selected",
                "rows_verified",
                "exact_match_rate",
                "pos_label_match_rate",
                "replay_rows_checked",
                "replay_mismatch_count",
                "pass_replay_bundle",
                "overall_pass",
            ],
        )
        if not stage06_summary.empty
        else pd.DataFrame(),
        details_table=stage06_detail,
        notes=[
            "Verifier recomputes OCO outcomes independently from stored labels.",
            "All summary rates should remain near 1.0 for contract consistency.",
        ],
        figure_paths=[stage06_plot] if stage06_plot.exists() else [],
        figure_prefix="../figures/oco_bible/",
        action_summary_table=stage_action_table(6),
    )
    stage06_replay = (
        pd.concat(stage06_replay_rows, ignore_index=True) if stage06_replay_rows else pd.DataFrame()
    )
    if not stage06_replay.empty:
        stage06_content += "\n\n#### Replay Bundle Sample\n" + _table(stage06_replay.head(30))
    portability_rows: list[pd.DataFrame] = []
    for ctx in contexts:
        sym = ctx["symbol"]
        cand = _safe_read_csv(ctx.get("candidate_csv"))
        if cand.empty or not {"family", "selection_pass", "mean_gross_pips_test"}.issubset(
            set(cand.columns)
        ):
            continue
        c = cand.copy()
        c["selection_pass"] = _to_bool_series(c["selection_pass"])
        c = c[c["selection_pass"]].copy()
        if c.empty:
            continue
        c["mean_gross_pips_test"] = pd.to_numeric(c["mean_gross_pips_test"], errors="coerce")
        fam = c.groupby("family", as_index=False)["mean_gross_pips_test"].mean()
        fam["symbol"] = sym
        portability_rows.append(fam)
    portability = (
        pd.concat(portability_rows, ignore_index=True) if portability_rows else pd.DataFrame()
    )
    if not portability.empty:
        pv = portability.pivot_table(
            index="family", columns="symbol", values="mean_gross_pips_test", aggfunc="mean"
        )
        port = pd.DataFrame({"family": pv.index})
        port["symbols_covered"] = pv.notna().sum(axis=1).values
        port["mean_across_symbols"] = pv.mean(axis=1, skipna=True).values
        port["std_across_symbols"] = pv.std(axis=1, ddof=1, skipna=True).values
        port["spread_max_min"] = (pv.max(axis=1, skipna=True) - pv.min(axis=1, skipna=True)).values
        port["x01_all_symbols_positive"] = (
            (pv.notna().sum(axis=1) == len(contexts)) & (pv.min(axis=1, skipna=True) > 0)
        ).astype(int)
        stage06_content += "\n\n#### Cross-Symbol Portability (X01-X03)\n" + _table(
            port.sort_values(
                ["x01_all_symbols_positive", "mean_across_symbols"], ascending=[False, False]
            ).head(20)
        )
        for sym in sorted(portability["symbol"].astype(str).unique()):
            add_edge_metric(
                6,
                sym,
                "X01_portable_family_count",
                int(port["x01_all_symbols_positive"].sum()),
                "Families with positive mean gross across all symbols",
                str(Path("data/analysis/tick_opportunity_mining/*_oco_candidates.csv")),
            )
            add_edge_metric(
                6,
                sym,
                "X02_family_std_mean",
                _num(port["std_across_symbols"].mean()),
                "Average family std across symbols",
                str(Path("data/analysis/tick_opportunity_mining/*_oco_candidates.csv")),
            )
            add_edge_metric(
                6,
                sym,
                "X03_family_spread_mean",
                _num(port["spread_max_min"].mean()),
                "Average family max-min spread across symbols",
                str(Path("data/analysis/tick_opportunity_mining/*_oco_candidates.csv")),
            )
    write_stage(6, stage06_content)

    # Stage 07: Logical audit.
    audit_evidence_path = _resolve_path(
        base_dir, "data/analysis/tick_opportunity_mining/oco_logical_audit_evidence.csv"
    )
    audit_evidence = _safe_read_csv(audit_evidence_path)
    fail_checks = checks.copy()
    if not fail_checks.empty and "status" in fail_checks.columns:
        fail_checks = fail_checks[fail_checks["status"].astype(str).str.lower() != "pass"].copy()
    stage07_summary = (
        checks.groupby("symbol", as_index=False).agg(
            total_checks=("check_id", "count"),
            failed_checks=("status", lambda s: int((s.astype(str).str.lower() != "pass").sum())),
        )
        if not checks.empty
        and "check_id" in checks.columns
        and "status" in checks.columns
        and "symbol" in checks.columns
        else pd.DataFrame()
    )
    check_rollup = (
        checks.groupby(["check_id", "status"], as_index=False)
        .size()
        .sort_values(["check_id", "status"])
        if not checks.empty and "check_id" in checks.columns and "status" in checks.columns
        else pd.DataFrame()
    )
    stage07_plot = _stage_plot_path(outputs, 7, "audit_failures")
    if not stage07_summary.empty:
        _plot_stage_bars(
            df=stage07_summary,
            x="symbol",
            ys=["failed_checks", "total_checks"],
            title="Stage 7: Logical Audit Failures",
            ylabel="count",
            out_path=stage07_plot,
        )
        for _, r in stage07_summary.iterrows():
            add_metric(
                7,
                "failed_checks",
                str(r.get("symbol", "ALL")),
                r.get("failed_checks"),
                "count",
                str(cfg["audit"]["checks_csv"]),
            )
    stage07_content = _render_stage_snapshot(
        stage_id=7,
        now_utc=now_utc,
        summary_table=stage07_summary if not stage07_summary.empty else pd.DataFrame(),
        details_table=_pick_cols(
            fail_checks,
            [
                "symbol",
                "check_id",
                "severity_if_fail",
                "component",
                "metric_name",
                "metric_value",
                "threshold",
            ],
        ).head(20)
        if not fail_checks.empty
        else check_rollup,
        notes=[
            "C01..C10 checks are the logical contract gate before robustness sign-off.",
            f"Open issue rows: {len(issues)}.",
        ],
        figure_paths=[stage07_plot] if stage07_plot.exists() else [],
        figure_prefix="../figures/oco_bible/",
        action_summary_table=stage_action_table(7),
    )
    if not stage23_overfit.empty:
        s7 = stage23_overfit.copy()
        iid_lb = pd.to_numeric(s7.get("lb95_trade_mean_gross_pips_iid"), errors="coerce")
        blk_lb = pd.to_numeric(s7.get("lb95_trade_mean_gross_pips_month_block"), errors="coerce")
        trade_lb = pd.to_numeric(s7.get("lb95_trade_mean_gross_pips"), errors="coerce")
        s7["s01_lb95_dependence_gap"] = iid_lb - blk_lb
        s7["s01_lb95_dependence_gap"] = s7["s01_lb95_dependence_gap"].fillna(trade_lb - blk_lb)
        # If dependence-aware fields are unavailable in this run artifact, use neutral 0.0 sentinel.
        s7["s01_lb95_dependence_gap"] = s7["s01_lb95_dependence_gap"].fillna(0.0)
        s7["s02_practical_lb95_gt0"] = (
            pd.to_numeric(s7.get("lb95_trade_mean_gross_pips"), errors="coerce") > 0
        ).astype(int)
        s7["s03_multiplicity_survival"] = (
            s7.get("bonferroni_pass_10pct", False).astype(bool)
            | s7.get("fdr_pass_10pct", False).astype(bool)
        ).astype(int)
        stage07_content += "\n\n#### Statistical Inference Ladder (S01-S03)\n" + _table(
            _pick_cols(
                s7,
                [
                    "symbol",
                    "lb95_trade_mean_gross_pips",
                    "s01_lb95_dependence_gap",
                    "pvalue_bonferroni",
                    "pvalue_fdr_bh",
                    "s02_practical_lb95_gt0",
                    "s03_multiplicity_survival",
                ],
            )
        )
        for _, r in s7.iterrows():
            sym = str(r.get("symbol", "")).upper()
            add_edge_metric(
                7,
                sym,
                "S01_lb95_dependence_gap",
                r.get("s01_lb95_dependence_gap"),
                "IID LB95 minus month-block LB95",
                str(outputs.stage_metrics_csv),
            )
            add_edge_metric(
                7,
                sym,
                "S02_practical_lb95_gt0",
                r.get("s02_practical_lb95_gt0"),
                "Practical significance indicator",
                str(outputs.stage_metrics_csv),
            )
            add_edge_metric(
                7,
                sym,
                "S03_multiplicity_survival",
                r.get("s03_multiplicity_survival"),
                "Bonferroni or FDR pass indicator",
                str(outputs.stage_metrics_csv),
            )
    if not audit_evidence.empty:
        stage07_content += "\n\n#### Failed Check Evidence Links\n" + _table(
            audit_evidence.head(80)
        )
    write_stage(7, stage07_content)

    # Stage 08: Robustness and overfit controls.
    robust_rows: list[dict[str, Any]] = []
    for ctx in contexts:
        sym = ctx["symbol"]
        rb = _safe_read_csv(ctx.get("robustness_summary_csv"))
        rm = _safe_read_csv(ctx.get("reduced_monthly_csv"))
        if rb.empty:
            continue
        if "is_exec_row" in rb.columns:
            exec_flag = pd.to_numeric(rb["is_exec_row"], errors="coerce").fillna(0).astype(int)
            if (exec_flag == 1).any():
                rb = rb.loc[exec_flag == 1]
        if "quantile" in rb.columns:
            qcol = pd.to_numeric(rb["quantile"], errors="coerce")
            rb = rb.loc[qcol == exec_q] if (qcol == exec_q).any() else rb.head(1)
        row = rb.iloc[0].to_dict()
        row["symbol"] = sym
        # T01/T02 cost stress diagnostics.
        cost_levels: list[float] = []
        stress_vals: list[float] = []
        for c in rb.columns:
            if str(c).startswith("mean_net_pips_costplus_"):
                lvl = _num(str(c).replace("mean_net_pips_costplus_", ""))
                val = _num(row.get(c))
                if math.isfinite(lvl) and math.isfinite(val):
                    cost_levels.append(lvl)
                    stress_vals.append(val)
        t01_elasticity = float("nan")
        t02_first_negative_cost = float("nan")
        if len(cost_levels) >= 2:
            srt = sorted(zip(cost_levels, stress_vals, strict=False), key=lambda x: x[0])
            xs = pd.Series([x for x, _ in srt], dtype=float)
            ys = pd.Series([y for _, y in srt], dtype=float)
            dx = _num(xs.iloc[-1] - xs.iloc[0])
            dy = _num(ys.iloc[-1] - ys.iloc[0])
            t01_elasticity = _safe_div(dy, dx)
            neg = [x for x, y in srt if y < 0]
            # No negative crossing in tested stress range uses max tested cost.
            t02_first_negative_cost = _num(min(neg)) if neg else _num(max(cost_levels))
        t04_max_survivable_cost = _num(row.get("max_survivable_cost_lb95_trade"))
        if not math.isfinite(t04_max_survivable_cost):
            t04_max_survivable_cost = _max_survivable_cost_from_costplus_cols(
                row,
                prefix="lb95_trade_mean_net_pips_costplus_",
            )
        t03_recovery = float("nan")
        if not rm.empty and {"test_month", "mean_gross_pips"}.issubset(set(rm.columns)):
            rr = rm.copy().sort_values("test_month")
            rr["mean_gross_pips"] = pd.to_numeric(rr["mean_gross_pips"], errors="coerce")
            rr = rr.dropna(subset=["mean_gross_pips"]).reset_index(drop=True)
            if len(rr) >= 2:
                # Ensure a next-month observation exists by selecting worst month among first n-1 rows.
                base = rr.iloc[:-1].copy()
                if not base.empty:
                    i = int(base["mean_gross_pips"].idxmin())
                    worst = _num(rr.loc[i, "mean_gross_pips"])
                    nxt = _num(rr.loc[i + 1, "mean_gross_pips"])
                    # Recovery factor: next-month gross / abs(worst-month gross); higher is better.
                    t03_recovery = _safe_div(nxt, abs(worst))
        row["t01_stress_elasticity"] = t01_elasticity
        row["t02_first_negative_costplus"] = t02_first_negative_cost
        row["t04_max_survivable_cost_lb95_trade"] = t04_max_survivable_cost
        row["t03_post_worst_month_recovery"] = t03_recovery
        robust_rows.append(row)
        add_metric(
            8,
            "lb95_trade_mean_gross_pips",
            sym,
            row.get("lb95_trade_mean_gross_pips"),
            "pips",
            str(ctx.get("robustness_summary_csv", "")),
        )
        add_edge_metric(
            8,
            sym,
            "T01_stress_elasticity",
            t01_elasticity,
            "Slope of mean net pips across costplus stress levels",
            str(ctx.get("robustness_summary_csv", "")),
        )
        add_edge_metric(
            8,
            sym,
            "T02_first_negative_costplus",
            t02_first_negative_cost,
            "First costplus level where mean net turns negative",
            str(ctx.get("robustness_summary_csv", "")),
        )
        add_edge_metric(
            8,
            sym,
            "T04_max_survivable_cost_lb95_trade",
            t04_max_survivable_cost,
            "Max extra cost (pips) where LB95 trade-mean net remains positive",
            str(ctx.get("robustness_summary_csv", "")),
        )
        if math.isnan(t03_recovery):
            t03_recovery = 0.0
        add_edge_metric(
            8,
            sym,
            "T03_post_worst_month_recovery",
            t03_recovery,
            "Next-month / abs(worst-month) gross ratio after worst reduced-core month",
            str(ctx.get("reduced_monthly_csv", "")),
        )
    stage08 = pd.DataFrame(robust_rows)
    stress_cols = (
        sorted(
            [
                c
                for c in stage08.columns
                if str(c).startswith("mean_net_pips_costplus_")
                or str(c).startswith("lb95_trade_mean_net_pips_costplus_")
            ]
        )
        if not stage08.empty
        else []
    )
    stage08_detail_cols = [
        "symbol",
        "lb95_trade_mean_gross_pips_iid",
        "lb95_trade_mean_gross_pips_month_block",
        "uplift_vs_null_pips",
        "pvalue_perm_uplift",
        "pvalue_perm_fdr_bh",
        "pvalue_month_mean_gt0",
        "pvalue_bonferroni",
        "pvalue_fdr_bh",
        "t01_stress_elasticity",
        "t02_first_negative_costplus",
        "t04_max_survivable_cost_lb95_trade",
        "t03_post_worst_month_recovery",
    ] + stress_cols[:4]
    stage08_detail = _pick_cols(stage08, stage08_detail_cols) if not stage08.empty else None
    stage08_plot = _stage_plot_path(outputs, 8, "robustness_lb95")
    stage08_overfit_panel = outputs.figures_dir / "stage_08_overfit_symbol_panel.png"
    if not stage08.empty:
        _plot_stage_bars(
            df=stage08,
            x="symbol",
            ys=["mean_gross_pips", "lb95_trade_mean_gross_pips"],
            title="Stage 8: Mean vs LB95 Gross",
            ylabel="pips",
            out_path=stage08_plot,
        )
        panel_cols = [
            c
            for c in [
                "mean_gross_pips",
                "null_mean_gross_pips",
                "lb95_trade_mean_gross_pips_iid",
                "lb95_trade_mean_gross_pips_month_block",
            ]
            if c in stage08.columns
        ]
        if panel_cols:
            _plot_stage_bars(
                df=stage08,
                x="symbol",
                ys=panel_cols,
                title="Stage 8: Overfit Panel (Observed vs Null vs LB95)",
                ylabel="pips",
                out_path=stage08_overfit_panel,
            )
    stage08_content = _render_stage_snapshot(
        stage_id=8,
        now_utc=now_utc,
        summary_table=_pick_cols(
            stage08,
            [
                "symbol",
                "quantile",
                "rows",
                "months",
                "mean_gross_pips",
                "lb95_trade_mean_gross_pips",
                "positive_months",
            ],
        )
        if not stage08.empty
        else pd.DataFrame(),
        details_table=stage08_detail
        if stage08_detail is not None and not stage08_detail.empty
        else None,
        notes=[
            "Robustness summary uses bootstrap lower bounds from the configured smoke/full run artifacts.",
            "Interpretation: LB95 > 0 indicates conservative positive expectancy under sampled uncertainty.",
            "Overfit panel adds month-stratified null uplift and dependence-aware LB95 comparisons.",
            "T01-T04 summarize stress elasticity, negative-cost crossing, max survivable cost, and post-worst-month recovery efficiency.",
        ],
        figure_paths=[p for p in [stage08_plot, stage08_overfit_panel] if p.exists()],
        figure_prefix="../figures/oco_bible/",
        action_summary_table=stage_action_table(8),
    )
    write_stage(8, stage08_content)

    # Stage 09: Governance and deployment readiness.
    missing_inventory = (
        artifact_inventory[~artifact_inventory["exists"].astype(bool)].copy()
        if not artifact_inventory.empty
        else pd.DataFrame()
    )
    stage09_summary = stage_status.copy() if not stage_status.empty else pd.DataFrame()
    gov_rows: list[dict[str, Any]] = []
    for ctx in contexts:
        sym = ctx["symbol"]
        gp = _safe_read_json(ctx.get("governance_predeploy_json"))
        leak_issues = _safe_read_csv(ctx.get("leakage_issues_csv"))
        exec_issues = _safe_read_csv(ctx.get("execution_risk_issues_csv"))
        leak_high_crit = 0
        exec_high_crit = 0
        if not leak_issues.empty:
            if "symbol" in leak_issues.columns:
                leak_issues = leak_issues[
                    leak_issues["symbol"].astype(str).str.upper() == sym
                ].copy()
            if not leak_issues.empty and "severity" in leak_issues.columns:
                sev = leak_issues["severity"].astype(str).str.lower()
                leak_high_crit = int(sev.isin(["high", "critical"]).sum())
        if not exec_issues.empty:
            if "symbol" in exec_issues.columns:
                exec_issues = exec_issues[
                    exec_issues["symbol"].astype(str).str.upper() == sym
                ].copy()
            if not exec_issues.empty and "severity" in exec_issues.columns:
                sev = exec_issues["severity"].astype(str).str.lower()
                exec_high_crit = int(sev.isin(["high", "critical"]).sum())
        if not gp:
            gov_rows.append(
                {
                    "symbol": sym,
                    "status": "missing",
                    "blocker": True,
                    "failed_checks": "missing_predeploy_json",
                    "checks_total": 1,
                    "checks_failed": 1,
                    "leakage_high_critical_issues": leak_high_crit,
                    "execution_risk_high_critical_issues": exec_high_crit,
                }
            )
            continue
        checks_list = gp.get("checks", [])
        fail_list = gp.get("failed_checks", [])
        if not isinstance(checks_list, list):
            checks_list = []
        if not isinstance(fail_list, list):
            fail_list = []
        near_fail = 0
        lock_drift_flags = 0
        for item in checks_list:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", ""))
            detail = str(item.get("detail", ""))
            # Near-fail heuristic: passed check with tiny margin in detail text.
            if bool(item.get("ok", False)):
                m = re.search(r"(?:critical_failed|high_failed|rows=)(\d+)", detail)
                if m and _num(m.group(1)) in {0.0, 1.0}:
                    near_fail += 1
            if any(
                tok in name for tok in ["config_hash", "states_hash", "state_universe_exact_match"]
            ) and not bool(item.get("ok", False)):
                lock_drift_flags += 1
        gov_rows.append(
            {
                "symbol": sym,
                "status": str(gp.get("status", "unknown")),
                "blocker": bool(gp.get("blocker", False)),
                "failed_checks": ",".join(map(str, fail_list)),
                "checks_total": int(len(checks_list)),
                "checks_failed": int(len(fail_list)),
                "as_of": str(gp.get("meta", {}).get("as_of", ""))
                if isinstance(gp.get("meta"), dict)
                else "",
                "window_end": str(gp.get("meta", {}).get("window_end", ""))
                if isinstance(gp.get("meta"), dict)
                else "",
                "json_path": str(ctx.get("governance_predeploy_json") or ""),
                "leakage_high_critical_issues": leak_high_crit,
                "execution_risk_high_critical_issues": exec_high_crit,
                "g01_near_fail_count": near_fail,
                "g03_lock_drift_flags": lock_drift_flags,
            }
        )
        add_edge_metric(
            9,
            sym,
            "G01_near_fail_count",
            near_fail,
            "Count of pass checks with low margin heuristics",
            str(ctx.get("governance_predeploy_json") or ""),
        )
        add_edge_metric(
            9,
            sym,
            "G03_lock_drift_flags",
            lock_drift_flags,
            "Hash/state-universe drift failures in predeploy checks",
            str(ctx.get("governance_predeploy_json") or ""),
        )
    stage09_gov = pd.DataFrame(gov_rows)
    risk_sla_path = _resolve_path(
        base_dir, "data/analysis/tick_opportunity_mining/risk_sla_tracker.csv"
    )
    risk_sla = _safe_read_csv(risk_sla_path)
    if (
        not stage09_gov.empty
        and not risk_sla.empty
        and {"symbol", "status", "days_open"}.issubset(set(risk_sla.columns))
    ):
        rs = risk_sla.copy()
        rs["symbol"] = rs["symbol"].astype(str).str.upper()
        rs = rs[rs["status"].astype(str).str.lower() == "open"].copy()
        if not rs.empty:
            g02 = (
                rs.groupby("symbol", as_index=False)["days_open"]
                .mean()
                .rename(columns={"days_open": "g02_open_warning_age_days"})
            )
            stage09_gov = stage09_gov.merge(g02, on="symbol", how="left")
            for _, rr in g02.iterrows():
                add_edge_metric(
                    9,
                    str(rr.get("symbol", "")),
                    "G02_open_warning_age_days",
                    rr.get("g02_open_warning_age_days"),
                    "Average days open for unresolved risks",
                    str(risk_sla_path),
                )
    stage09_plot = _stage_plot_path(outputs, 9, "gate_matrix")
    if not stage09_summary.empty:
        heat = stage09_summary.copy()
        gate_cols = [
            c for c in heat.columns if c.startswith("gate_") or c == "symbol_all_gates_pass"
        ]
        if gate_cols:
            _plot_stage_bars(
                df=pd.DataFrame(
                    {
                        "symbol": heat["symbol"],
                        "gates_passed": heat[gate_cols].astype(bool).sum(axis=1),
                        "gates_total": len(gate_cols),
                    }
                ),
                x="symbol",
                ys=["gates_passed", "gates_total"],
                title="Stage 9: Governance Gates Passed",
                ylabel="count",
                out_path=stage09_plot,
            )
    stage09_predeploy_plot = _stage_plot_path(outputs, 9, "predeploy_checks")
    if not stage09_gov.empty:
        d9 = stage09_gov.copy()
        if "checks_total" not in d9.columns:
            d9["checks_total"] = 0
        if "checks_failed" not in d9.columns:
            d9["checks_failed"] = 0
        _plot_stage_bars(
            df=d9,
            x="symbol",
            ys=["checks_total", "checks_failed"],
            title="Stage 9: Predeploy Validator Checks",
            ylabel="count",
            out_path=stage09_predeploy_plot,
        )
        for _, r in d9.iterrows():
            add_metric(
                9,
                "predeploy_checks_failed",
                str(r.get("symbol", "ALL")),
                r.get("checks_failed", 0),
                "count",
                str(r.get("json_path", "")),
            )
    stage09_content = _render_stage_snapshot(
        stage_id=9,
        now_utc=now_utc,
        summary_table=stage09_summary if not stage09_summary.empty else pd.DataFrame(),
        details_table=_pick_cols(missing_inventory, ["group", "symbol", "artifact", "path"]).head(
            20
        )
        if not missing_inventory.empty
        else None,
        notes=[
            "Governance snapshot combines symbol gate matrix with artifact inventory completeness.",
            f"Missing required artifacts: {int(len(missing_inventory[missing_inventory['required']])) if not missing_inventory.empty and 'required' in missing_inventory.columns else 0}.",
        ],
        figure_paths=[p for p in [stage09_plot, stage09_predeploy_plot] if p.exists()],
        figure_prefix="../figures/oco_bible/",
        action_summary_table=stage_action_table(9),
    )
    if not stage09_gov.empty:
        stage09_content += "\n\n#### Predeploy Validator Status\n" + _table(
            _pick_cols(
                stage09_gov,
                [
                    "symbol",
                    "status",
                    "blocker",
                    "checks_total",
                    "checks_failed",
                    "leakage_high_critical_issues",
                    "execution_risk_high_critical_issues",
                    "g01_near_fail_count",
                    "g02_open_warning_age_days",
                    "g03_lock_drift_flags",
                    "as_of",
                    "window_end",
                    "failed_checks",
                ],
            )
        )
        if (
            "status" in stage09_gov.columns
            and (stage09_gov["status"].astype(str).str.lower() == "missing").any()
        ):
            stage09_content += (
                "\n\n- Missing predeploy JSON for one or more symbols. Generate with "
                "`scripts/validate_oco_live_governance.py --mode deploy --data-reliability-checks-csv ... "
                "--leakage-checks-csv ... --execution-risk-checks-csv ... --out-json ...` per symbol."
            )
    write_stage(9, stage09_content)

    # Stage 10: Risks and backlog.
    severity_map = {"low": 1.0, "medium": 2.0, "high": 3.0, "critical": 4.0}
    risk = fail_checks.copy()
    exec_issue_rows: list[pd.DataFrame] = []
    for ctx in contexts:
        sym = ctx["symbol"]
        exi = _safe_read_csv(ctx.get("execution_risk_issues_csv"))
        if exi.empty:
            continue
        if "symbol" in exi.columns:
            exi = exi[exi["symbol"].astype(str).str.upper() == sym].copy()
        if exi.empty:
            continue
        r = pd.DataFrame(
            {
                "symbol": exi.get("symbol", pd.Series(dtype=str)).astype(str).str.upper(),
                "check_id": exi.get("check_id", pd.Series(dtype=str)).astype(str),
                "severity_if_fail": exi.get("severity", pd.Series(dtype=str))
                .astype(str)
                .str.lower(),
                "component": exi.get("component", pd.Series(dtype=str)).astype(str),
                "metric_name": exi.get("summary", pd.Series(dtype=str)).astype(str),
                "metric_value": np.nan,
                "threshold": "",
                "status": "fail",
            }
        )
        exec_issue_rows.append(r)
    if exec_issue_rows:
        risk = pd.concat([risk, pd.concat(exec_issue_rows, ignore_index=True)], ignore_index=True)
    if not risk.empty:
        risk["severity_score"] = (
            risk.get("severity_if_fail", risk.get("severity", ""))
            .astype(str)
            .str.lower()
            .map(severity_map)
            .fillna(1.0)
        )
    risk_summary = (
        risk.groupby(["symbol", "check_id"], as_index=False).agg(
            fail_count=("check_id", "count"),
            impact_score=("severity_score", "mean"),
        )
        if not risk.empty and "symbol" in risk.columns and "check_id" in risk.columns
        else pd.DataFrame()
    )
    risk_controls = pd.DataFrame()
    if not checks.empty and "severity_if_fail" in checks.columns:
        c = checks.copy()
        c["failed"] = c["status"].astype(str).str.lower() != "pass"
        risk_controls = (
            c.groupby(["symbol", "severity_if_fail"], as_index=False)
            .agg(total_checks=("check_id", "count"), failed_checks=("failed", "sum"))
            .sort_values(["symbol", "severity_if_fail"])
        )
    stage10_plot = _stage_plot_path(outputs, 10, "risk_matrix")
    risk_plot_df = risk_summary.copy()
    if risk_plot_df.empty and not checks.empty and "symbol" in checks.columns:
        syms = sorted({str(x).upper() for x in checks["symbol"].astype(str)})
        risk_plot_df = pd.DataFrame(
            {
                "symbol": syms,
                "check_id": ["none"] * len(syms),
                "fail_count": [0] * len(syms),
                "impact_score": [0.0] * len(syms),
            }
        )
    if not risk_plot_df.empty:
        # Use scatter to emulate impact/likelihood map.
        _plot_stage_scatter(
            df=risk_plot_df.assign(
                likelihood=lambda d: (
                    d["fail_count"] / max(float(d["fail_count"].max()), 1.0)
                    if "fail_count" in d.columns
                    else 0.0
                )
            ),
            x="likelihood",
            y="impact_score",
            hue="symbol",
            title="Stage 10: Risk Matrix (Audit-Derived)",
            xlabel="relative likelihood",
            ylabel="impact score",
            out_path=stage10_plot,
        )
    risk_sla_path = _resolve_path(
        base_dir, "data/analysis/tick_opportunity_mining/risk_sla_tracker.csv"
    )
    risk_sla = _safe_read_csv(risk_sla_path)
    backlog_diag = pd.DataFrame()
    stage10_sla_plot = _stage_plot_path(outputs, 10, "risk_sla_open_breached")
    if not risk_sla.empty and {"symbol", "status", "breached"}.issubset(set(risk_sla.columns)):
        open_sla = risk_sla[risk_sla["status"].astype(str).str.lower() == "open"].copy()
        if not open_sla.empty:
            open_sla["breached_flag"] = (
                open_sla["breached"]
                .astype(str)
                .str.lower()
                .isin({"1", "true", "yes", "y"})
                .astype(int)
            )
            sla_roll = open_sla.groupby("symbol", as_index=False).agg(
                open_risks=("risk_id", "count"),
                breached_risks=("breached_flag", "sum"),
                avg_days_open=("days_open", "mean"),
            )
            _plot_stage_bars(
                df=sla_roll,
                x="symbol",
                ys=["open_risks", "breached_risks"],
                title="Stage 10: Open vs Breached Risks",
                ylabel="count",
                out_path=stage10_sla_plot,
            )
            for _, r in sla_roll.iterrows():
                add_metric(
                    10,
                    "open_risks",
                    str(r.get("symbol", "ALL")),
                    r.get("open_risks", 0),
                    "count",
                    str(risk_sla_path),
                )
                add_metric(
                    10,
                    "breached_risks",
                    str(r.get("symbol", "ALL")),
                    r.get("breached_risks", 0),
                    "count",
                    str(risk_sla_path),
                )
        if {"symbol", "status", "days_open", "severity"}.issubset(set(risk_sla.columns)):
            rr = risk_sla.copy()
            rr["symbol"] = rr["symbol"].astype(str).str.upper()
            rr["days_open"] = pd.to_numeric(rr["days_open"], errors="coerce")
            rr["is_open"] = (rr["status"].astype(str).str.lower() == "open").astype(int)
            rr["is_closed"] = (rr["status"].astype(str).str.lower() == "closed").astype(int)
            rr["is_high"] = (
                rr["severity"].astype(str).str.lower().isin({"high", "critical"}).astype(int)
            )
            backlog_diag = rr.groupby("symbol", as_index=False).agg(
                b11_open_risks=("is_open", "sum"),
                b11_closed_risks=("is_closed", "sum"),
                b12_high_open=("is_high", "sum"),
                b13_avg_days_open=("days_open", "mean"),
            )
            for _, r in backlog_diag.iterrows():
                add_edge_metric(
                    10,
                    str(r.get("symbol", "")),
                    "B11_open_risks",
                    r.get("b11_open_risks"),
                    "Open risk count",
                    str(risk_sla_path),
                )
                add_edge_metric(
                    10,
                    str(r.get("symbol", "")),
                    "B12_high_open",
                    r.get("b12_high_open"),
                    "Open high/critical risk count",
                    str(risk_sla_path),
                )
                add_edge_metric(
                    10,
                    str(r.get("symbol", "")),
                    "B13_avg_days_open",
                    r.get("b13_avg_days_open"),
                    "Average days open for risks",
                    str(risk_sla_path),
                )
    stage10_content = _render_stage_snapshot(
        stage_id=10,
        now_utc=now_utc,
        summary_table=risk_summary
        if not risk_summary.empty
        else pd.DataFrame([{"status": "no_open_audit_failures", "failed_checks": 0}]),
        details_table=risk_controls if not risk_controls.empty else None,
        notes=[
            "Risk backlog is derived from current logical-audit failures.",
            "When no failures exist, residual risks remain model/process assumptions rather than hard contract breaks.",
        ],
        figure_paths=[p for p in [stage10_plot, stage10_sla_plot] if p.exists()],
        figure_prefix="../figures/oco_bible/",
        action_summary_table=stage_action_table(10),
    )
    if risk_sla_path.exists() and not risk_sla.empty:
        stage10_content += "\n\n#### Risk SLA Tracker\n" + _table(
            _pick_cols(
                risk_sla,
                [
                    "risk_id",
                    "symbol",
                    "check_id",
                    "severity",
                    "status",
                    "days_open",
                    "sla_days",
                    "breached",
                    "owner",
                ],
            )
        )
        if not backlog_diag.empty:
            stage10_content += "\n\n#### Backlog Diagnostics (B11-B13)\n" + _table(backlog_diag)
        if {"status", "breached"}.issubset(set(risk_sla.columns)):
            open_count = int((risk_sla["status"].astype(str).str.lower() == "open").sum())
            breach_count = int(
                (
                    (risk_sla["status"].astype(str).str.lower() == "open")
                    & risk_sla["breached"].astype(str).str.lower().isin({"1", "true", "yes", "y"})
                ).sum()
            )
            stage10_content += (
                "\n\n- SLA summary: "
                + f"`open={open_count}`, `breached={breach_count}`, `source={_to_repo_rel(risk_sla_path)}`"
            )
    elif risk_sla_path.exists():
        stage10_content += (
            "\n\n- Risk SLA tracker exists but has no open rows. "
            + f"`source={_to_repo_rel(risk_sla_path)}`"
        )
    else:
        stage10_content += (
            "\n\n- Risk SLA tracker not found; run `scripts/audit_oco_pipeline_logical_issues.py` "
            "with `--out-risk-sla-csv` to populate Stage 10 operational aging metrics."
        )
    write_stage(10, stage10_content)

    # Stage 11: Execution Monte Carlo hardening.
    stage11_rows: list[dict[str, Any]] = []
    stage11_detail_rows: list[pd.DataFrame] = []
    stage11_month_rows: list[pd.DataFrame] = []
    stage11_check_rows: list[dict[str, Any]] = []
    mc_symbol_all = (
        _safe_read_csv(contexts[0].get("execution_mc_symbol_scenarios_csv"))
        if contexts
        else pd.DataFrame()
    )
    mc_month_all = (
        _safe_read_csv(contexts[0].get("execution_mc_month_session_csv"))
        if contexts
        else pd.DataFrame()
    )
    mc_checks_all = (
        _safe_read_csv(contexts[0].get("execution_mc_checks_csv")) if contexts else pd.DataFrame()
    )
    for ctx in contexts:
        sym = ctx["symbol"]
        s = mc_symbol_all.copy()
        if not s.empty and "symbol" in s.columns:
            s = s[s["symbol"].astype(str).str.upper() == sym].copy()
        if not s.empty:
            stage11_detail_rows.append(s)
            s1 = s[s["scenario_id"].astype(str) == "S1_mild"].copy()
            s2 = s[s["scenario_id"].astype(str) == "S2_moderate"].copy()
            sb = s[s["scenario_id"].astype(str) == "S0_baseline"].copy()
            row = {
                "symbol": sym,
                "signals": _num(sb.iloc[0]["signals"])
                if not sb.empty and "signals" in sb.columns
                else _num(s["signals"].max() if "signals" in s.columns else float("nan")),
                "lb95_s1": _num(s1.iloc[0]["lb95_per_signal_pips"])
                if not s1.empty and "lb95_per_signal_pips" in s1.columns
                else float("nan"),
                "lb95_s2": _num(s2.iloc[0]["lb95_per_signal_pips"])
                if not s2.empty and "lb95_per_signal_pips" in s2.columns
                else float("nan"),
                "prob_negative_month_s1": _num(s1.iloc[0]["prob_negative_month"])
                if not s1.empty and "prob_negative_month" in s1.columns
                else float("nan"),
                "fill_rate_drop_s1": _num(s1.iloc[0]["fill_rate_drop_vs_S0"])
                if not s1.empty and "fill_rate_drop_vs_S0" in s1.columns
                else float("nan"),
                "drawdown_proxy_p95_s1": _num(s1.iloc[0]["drawdown_proxy_p95"])
                if not s1.empty and "drawdown_proxy_p95" in s1.columns
                else float("nan"),
            }
            stage11_rows.append(row)
            add_edge_metric(
                11,
                sym,
                "EM01_lb95_per_signal_s1",
                row["lb95_s1"],
                "LB95 per-signal pips in mild stress",
                str(ctx.get("execution_mc_symbol_scenarios_csv", "")),
            )
            add_edge_metric(
                11,
                sym,
                "EM02_lb95_per_signal_s2",
                row["lb95_s2"],
                "LB95 per-signal pips in moderate stress",
                str(ctx.get("execution_mc_symbol_scenarios_csv", "")),
            )
            add_edge_metric(
                11,
                sym,
                "EM03_prob_negative_month_s1",
                row["prob_negative_month_s1"],
                "Probability of negative month in mild stress",
                str(ctx.get("execution_mc_symbol_scenarios_csv", "")),
            )
            add_edge_metric(
                11,
                sym,
                "EM04_fill_rate_drop_vs_s0_s1",
                row["fill_rate_drop_s1"],
                "Fill-rate drop from baseline to mild stress",
                str(ctx.get("execution_mc_symbol_scenarios_csv", "")),
            )
        m = mc_month_all.copy()
        if not m.empty and "symbol" in m.columns:
            m = m[m["symbol"].astype(str).str.upper() == sym].copy()
        if not m.empty:
            stage11_month_rows.append(m)
        c11 = mc_checks_all.copy()
        if not c11.empty and "symbol" in c11.columns:
            c11 = c11[c11["symbol"].astype(str).str.upper() == sym].copy()
        if not c11.empty:
            fail = c11["status"].astype(str).str.lower() != "pass"
            nan_row = c11[c11["check_id"].astype(str) == "EM05"]
            em05_nan = (
                _num(nan_row.iloc[0]["metric_value"])
                if not nan_row.empty and "metric_value" in nan_row.columns
                else float("nan")
            )
            add_edge_metric(
                11,
                sym,
                "EM05_nan_core_fields",
                em05_nan,
                "NaN count in execution MC core fields",
                str(ctx.get("execution_mc_checks_csv", "")),
            )
            stage11_check_rows.append(
                {
                    "symbol": sym,
                    "checks_total": int(len(c11)),
                    "checks_failed": int(fail.sum()),
                    "high_critical_failed": int(
                        (
                            fail
                            & c11.get("severity_if_fail", pd.Series(index=c11.index, dtype=str))
                            .astype(str)
                            .str.lower()
                            .isin(["high", "critical"])
                        ).sum()
                    ),
                }
            )
    stage11_summary = pd.DataFrame(stage11_rows)
    stage11_detail = (
        pd.concat(stage11_detail_rows, ignore_index=True) if stage11_detail_rows else pd.DataFrame()
    )
    stage11_month = (
        pd.concat(stage11_month_rows, ignore_index=True) if stage11_month_rows else pd.DataFrame()
    )
    stage11_checks = pd.DataFrame(stage11_check_rows)
    stage11_symbol_source = (
        str(contexts[0].get("execution_mc_symbol_scenarios_csv", "")) if contexts else ""
    )
    stage11_month_source = (
        str(contexts[0].get("execution_mc_month_session_csv", "")) if contexts else ""
    )
    stage11_plot = _stage_plot_path(outputs, 11, "mc_lb95_by_scenario")
    stage11_scatter = _stage_plot_path(outputs, 11, "mc_fill_vs_pnl")
    if not stage11_detail.empty:
        p11 = stage11_detail.copy()
        p11["lb95_per_signal_pips"] = pd.to_numeric(p11["lb95_per_signal_pips"], errors="coerce")
        p11["mean_per_signal_pips"] = pd.to_numeric(p11["mean_per_signal_pips"], errors="coerce")
        p11["mean_fill_rate"] = pd.to_numeric(p11["mean_fill_rate"], errors="coerce")
        _plot_stage_lines(
            df=p11,
            x="scenario_id",
            y="lb95_per_signal_pips",
            hue="symbol",
            title="Stage 11: LB95 Per-Signal by Scenario",
            ylabel="pips",
            out_path=stage11_plot,
        )
        _plot_stage_scatter(
            df=p11,
            x="mean_fill_rate",
            y="mean_per_signal_pips",
            hue="symbol",
            title="Stage 11: Fill Rate vs Mean Per-Signal",
            xlabel="mean fill rate",
            ylabel="mean per-signal pips",
            out_path=stage11_scatter,
        )
    stage11_content = _render_stage_snapshot(
        stage_id=11,
        now_utc=now_utc,
        summary_table=stage11_summary if not stage11_summary.empty else pd.DataFrame(),
        details_table=_pick_cols(
            stage11_detail,
            [
                "symbol",
                "scenario_id",
                "mean_per_signal_pips",
                "lb95_per_signal_pips",
                "lb99_per_signal_pips",
                "mean_per_trade_pips",
                "mean_fill_rate",
                "prob_negative_month",
                "fill_rate_drop_vs_S0",
                "drawdown_proxy_p95",
            ],
        )
        if not stage11_detail.empty
        else None,
        notes=[
            "Execution Monte Carlo uses month x session stress scenarios derived from Stage 04 tickfill artifacts.",
            "EM01-EM05 summarize mild/moderate survival, month negativity risk, fill-rate decay, and data integrity.",
        ],
        figure_paths=[p for p in [stage11_plot, stage11_scatter] if p.exists()],
        figure_prefix="../figures/oco_bible/",
        action_summary_table=stage_action_table(11),
        details_source_path=stage11_symbol_source,
    )
    if not stage11_checks.empty:
        stage11_content += "\n\n#### Monte Carlo Governance Checks\n" + _table(stage11_checks)
    if not stage11_month.empty:
        stage11_month_view = _pick_cols(
            stage11_month,
            [
                "symbol",
                "scenario_id",
                "test_month",
                "session_bucket",
                "signals",
                "mean_per_signal_pips",
                "lb95_per_signal_pips",
                "mean_fill_rate",
            ],
        )
        n_full = len(stage11_month_view)
        stage11_month_view = stage11_month_view.head(DETAIL_MAX_ROWS_DEFAULT)
        stage11_content += "\n\n#### Month x Session Summary (head)\n" + _table(stage11_month_view)
        stage11_content += (
            "\n\n- month_session_rows_shown: " + f"`{len(stage11_month_view)}` of `{n_full}`"
        )
        if stage11_month_source:
            stage11_content += (
                "\n- full_month_session_artifact: " + f"`{_to_repo_rel(stage11_month_source)}`"
            )
    write_stage(11, stage11_content)

    edge_stage = pd.DataFrame(edge_stage_rows)
    edge_state = pd.DataFrame(edge_state_rows)
    edge_thr = pd.DataFrame(edge_threshold_rows)
    outputs.edge_clarity_stage_metrics_csv.parent.mkdir(parents=True, exist_ok=True)
    outputs.edge_clarity_state_contrib_csv.parent.mkdir(parents=True, exist_ok=True)
    outputs.edge_clarity_threshold_robustness_csv.parent.mkdir(parents=True, exist_ok=True)
    outputs.edge_clarity_report_md.parent.mkdir(parents=True, exist_ok=True)
    edge_stage.to_csv(outputs.edge_clarity_stage_metrics_csv, index=False)
    edge_state.to_csv(outputs.edge_clarity_state_contrib_csv, index=False)
    edge_thr.to_csv(outputs.edge_clarity_threshold_robustness_csv, index=False)

    report_lines: list[str] = []
    report_lines.append("# OCO Edge Clarity Report")
    report_lines.append("")
    report_lines.append(
        f"- generated_at_utc: `{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}`"
    )
    report_lines.append(
        f"- stage_metrics_csv: `{_to_repo_rel(outputs.edge_clarity_stage_metrics_csv)}`"
    )
    report_lines.append(
        f"- state_contrib_csv: `{_to_repo_rel(outputs.edge_clarity_state_contrib_csv)}`"
    )
    report_lines.append(
        f"- threshold_robustness_csv: `{_to_repo_rel(outputs.edge_clarity_threshold_robustness_csv)}`"
    )
    report_lines.append("")
    if not edge_stage.empty:
        top_metrics = (
            edge_stage.dropna(subset=["metric_value"])
            .sort_values(["stage_id", "symbol", "metric_id"])
            .reset_index(drop=True)
        )
        report_lines.append("## Stage Metrics")
        report_lines.append(_table(top_metrics))
        report_lines.append("")
    if not edge_state.empty:
        top_state = (
            edge_state.sort_values(["symbol", "contrib_share"], ascending=[True, False])
            .groupby("symbol", as_index=False)
            .head(20)
        )
        report_lines.append("## Top State Contributions")
        report_lines.append(
            _table(
                _pick_cols(
                    top_state,
                    [
                        "symbol",
                        "family",
                        "state_id",
                        "bar_ticks",
                        "horizon",
                        "edge_weight",
                        "contrib_share",
                    ],
                )
            )
        )
        report_lines.append("")
    if not edge_thr.empty:
        report_lines.append("## Threshold Robustness Slices")
        report_lines.append(
            _table(
                _pick_cols(
                    edge_thr,
                    [
                        "symbol",
                        "test_month",
                        "quantile",
                        "mean_gross_pips",
                        "coverage",
                        "selected_rows",
                    ],
                )
            )
        )
        report_lines.append("")
    outputs.edge_clarity_report_md.write_text("\n".join(report_lines), encoding="utf-8")

    return pd.DataFrame(metric_rows)


def run(*, manifest_path: Path, strict: bool) -> dict[str, Any]:
    cfg, base_dir = _load_manifest(manifest_path)
    out_cfg = cfg["outputs"]
    outputs = BuildOutputs(
        generated_dir=_resolve_output_path(str(out_cfg["generated_dir"])),
        figures_dir=_resolve_output_path(str(out_cfg["figures_dir"])),
        build_report_csv=_resolve_output_path(str(out_cfg["build_report_csv"])),
        symbol_snapshot_csv=_resolve_output_path(str(out_cfg["symbol_snapshot_csv"])),
        stage_status_csv=_resolve_output_path(str(out_cfg["stage_status_csv"])),
        stage_metrics_csv=_resolve_output_path(
            str(
                out_cfg.get(
                    "stage_metrics_csv",
                    "data/analysis/tick_opportunity_mining/oco_bible_stage_metrics.csv",
                )
            )
        ),
        edge_clarity_stage_metrics_csv=_resolve_output_path(
            str(
                out_cfg.get(
                    "edge_clarity_stage_metrics_csv",
                    "data/analysis/tick_opportunity_mining/edge_clarity_stage_metrics.csv",
                )
            )
        ),
        edge_clarity_state_contrib_csv=_resolve_output_path(
            str(
                out_cfg.get(
                    "edge_clarity_state_contrib_csv",
                    "data/analysis/tick_opportunity_mining/edge_clarity_state_contrib.csv",
                )
            )
        ),
        edge_clarity_threshold_robustness_csv=_resolve_output_path(
            str(
                out_cfg.get(
                    "edge_clarity_threshold_robustness_csv",
                    "data/analysis/tick_opportunity_mining/edge_clarity_threshold_robustness.csv",
                )
            )
        ),
        edge_clarity_report_md=_resolve_output_path(
            str(out_cfg.get("edge_clarity_report_md", "docs/analysis/oco_edge_clarity_report.md"))
        ),
    )

    inventory_rows = _artifact_rows(cfg, base_dir)
    inventory = pd.DataFrame(inventory_rows)

    missing_required = inventory[(inventory["required"]) & (~inventory["exists"])].copy()
    if strict and not missing_required.empty:
        missing = "\n".join(missing_required["path"].astype(str).tolist())
        raise FileNotFoundError(f"missing required artifacts:\n{missing}")

    thresholds = cfg.get("gate_thresholds", {})
    min_exact = float(thresholds.get("min_exact_match_rate", 0.999))
    min_pos = float(thresholds.get("min_pos_label_match_rate", 0.999))
    expected_audit_failures = int(thresholds.get("expected_audit_failures", 0))
    robust_quantile = thresholds.get("robustness_quantile")
    robust_quantile_f = float(robust_quantile) if robust_quantile is not None else None

    snapshot_rows: list[dict[str, Any]] = []
    for entry in cfg["symbols"]:
        try:
            row = _symbol_snapshot(
                entry,
                base_dir=base_dir,
                min_exact=min_exact,
                min_pos=min_pos,
                robust_quantile=robust_quantile_f,
            )
            snapshot_rows.append(row)
        except Exception:
            if strict:
                raise
            snapshot_rows.append(
                {
                    "symbol": str(entry.get("symbol", "")).upper(),
                    "symbol_all_gates_pass": False,
                }
            )

    snapshot = pd.DataFrame(snapshot_rows)
    for c, default in [
        ("gate_reduced_lb95_month_gt0", False),
        ("gate_tick_exact", False),
        ("gate_robust_lb95_trade_gt0", False),
        ("gate_robust_months_majority", False),
        ("symbol_all_gates_pass", False),
    ]:
        if c not in snapshot.columns:
            snapshot[c] = default

    stage_status = snapshot[
        [
            "symbol",
            "gate_reduced_lb95_month_gt0",
            "gate_tick_exact",
            "gate_robust_lb95_trade_gt0",
            "gate_robust_months_majority",
            "symbol_all_gates_pass",
        ]
    ].copy()

    audit_cfg = cfg["audit"]
    checks_path = _resolve_path(base_dir, str(audit_cfg["checks_csv"]))
    issues_path = _resolve_path(base_dir, str(audit_cfg["issues_csv"]))

    checks = _read_csv(checks_path) if checks_path.exists() else pd.DataFrame()
    issues = _read_csv(issues_path) if issues_path.exists() else pd.DataFrame()
    audit_failures = (
        int((checks["status"].astype(str) != "pass").sum())
        if "status" in checks.columns
        else len(issues)
    )
    audit_pass = (
        audit_failures <= expected_audit_failures and len(issues) <= expected_audit_failures
    )

    overall_pass = bool(
        snapshot.get("symbol_all_gates_pass", pd.Series(dtype=bool)).fillna(False).all()
    ) and bool(audit_pass)

    outputs.symbol_snapshot_csv.parent.mkdir(parents=True, exist_ok=True)
    outputs.stage_status_csv.parent.mkdir(parents=True, exist_ok=True)
    outputs.build_report_csv.parent.mkdir(parents=True, exist_ok=True)
    outputs.stage_metrics_csv.parent.mkdir(parents=True, exist_ok=True)

    snapshot.to_csv(outputs.symbol_snapshot_csv, index=False)
    stage_status.to_csv(outputs.stage_status_csv, index=False)

    build_report = inventory.copy()
    build_report["generated_at_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    build_report.to_csv(outputs.build_report_csv, index=False)

    figures: list[Path] = []
    if not snapshot.empty and all(
        c in snapshot.columns for c in ["mean_gross_pips", "robustness_lb95_trade_mean_gross_pips"]
    ):
        fig1 = outputs.figures_dir / "fig01_symbol_gross_vs_lb95.png"
        _write_plot_gross(snapshot, fig1)
        figures.append(fig1)
    if not snapshot.empty and all(
        c in snapshot.columns for c in ["exact_match_rate", "pos_label_match_rate"]
    ):
        fig2 = outputs.figures_dir / "fig02_symbol_tick_exact_rates.png"
        _write_plot_tick_exact(snapshot, fig2)
        figures.append(fig2)

    _write_markdown_outputs(
        cfg=cfg,
        outputs=outputs,
        artifact_inventory=inventory,
        snapshot=snapshot,
        stage_status=stage_status,
        checks=checks,
        issues=issues,
        audit_failures=audit_failures,
        audit_pass=audit_pass,
        figures=figures,
    )

    stage_metrics = _write_stage_snapshots(
        cfg=cfg,
        base_dir=base_dir,
        outputs=outputs,
        snapshot=snapshot,
        stage_status=stage_status,
        artifact_inventory=inventory,
        checks=checks,
        issues=issues,
    )
    stage_metrics.to_csv(outputs.stage_metrics_csv, index=False)

    canonical_path = (Path.cwd() / "docs" / "strategy_bible" / "oco_rolling_bible.md").resolve()
    canonical_lines: list[str] = []
    canonical_lines.append("### Latest Run Results")
    canonical_lines.append("")
    canonical_lines.append(
        f"- generated_at: `{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}`"
    )
    canonical_lines.append(f"- overall_pass: `{overall_pass}`")
    canonical_lines.append(f"- audit_pass: `{audit_pass}`")
    canonical_lines.append("")
    canonical_lines.append("#### Symbol Snapshot")
    canonical_lines.append(_table(snapshot))
    canonical_lines.append("")
    canonical_lines.append("#### Stage Gate Status")
    canonical_lines.append(_table(stage_status))
    canonical_lines.append("")
    canonical_lines.append("#### Quick Links")
    for i in range(1, 12):
        canonical_lines.append(f"- [Stage {i:02d} snapshot](generated/stage_{i:02d}_snapshot.md)")
    _inject_named_block(
        canonical_path,
        marker_name="CANONICAL_RESULTS",
        heading="## Generated Run Snapshot",
        content="\n".join(canonical_lines),
    )

    return {
        "overall_pass": overall_pass,
        "audit_pass": audit_pass,
        "audit_failures": audit_failures,
        "missing_required_count": int(len(missing_required)),
        "symbols": snapshot[["symbol", "symbol_all_gates_pass"]].to_dict(orient="records")
        if not snapshot.empty
        else [],
        "generated_dir": _to_repo_rel(outputs.generated_dir),
        "figures_dir": _to_repo_rel(outputs.figures_dir),
        "build_report_csv": _to_repo_rel(outputs.build_report_csv),
        "symbol_snapshot_csv": _to_repo_rel(outputs.symbol_snapshot_csv),
        "stage_status_csv": _to_repo_rel(outputs.stage_status_csv),
        "stage_metrics_csv": _to_repo_rel(outputs.stage_metrics_csv),
        "edge_clarity_stage_metrics_csv": _to_repo_rel(outputs.edge_clarity_stage_metrics_csv),
        "edge_clarity_state_contrib_csv": _to_repo_rel(outputs.edge_clarity_state_contrib_csv),
        "edge_clarity_threshold_robustness_csv": _to_repo_rel(
            outputs.edge_clarity_threshold_robustness_csv
        ),
        "edge_clarity_report_md": _to_repo_rel(outputs.edge_clarity_report_md),
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Build OCO rolling strategy bible generated docs")
    p.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    p.add_argument("--strict", default="false")
    args = p.parse_args()

    out = run(manifest_path=Path(str(args.manifest)), strict=_parse_bool(str(args.strict)))
    for k in [
        "overall_pass",
        "audit_pass",
        "audit_failures",
        "missing_required_count",
        "generated_dir",
        "figures_dir",
        "build_report_csv",
        "symbol_snapshot_csv",
        "stage_status_csv",
        "stage_metrics_csv",
        "edge_clarity_stage_metrics_csv",
        "edge_clarity_state_contrib_csv",
        "edge_clarity_threshold_robustness_csv",
        "edge_clarity_report_md",
    ]:
        print(f"{k}: {out.get(k)}")


if __name__ == "__main__":
    main()
