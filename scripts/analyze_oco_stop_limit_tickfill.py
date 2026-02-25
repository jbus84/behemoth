#!/usr/bin/env python3
"""Estimate stop-limit behavior using first-crossing raw ticks on touch bars.

For selected OCO events (typically q=0.9 exec-selected rows), this script:
1) Reconstructs touch-bar side and barrier from bar data.
2) Finds the first tick crossing inside the touch bar window.
3) Computes tick-level overshoot (pips) and cap-based stop-limit fill metrics.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def _pip_size(symbol: str) -> float:
    s = str(symbol).upper().strip()
    if s.endswith("JPY"):
        return 0.01
    if s.startswith("XAU"):
        return 0.1
    if s.startswith("XAG"):
        return 0.01
    return 0.0001


def _parse_candidate_uid(uid: str) -> tuple[int, int, str]:
    # library|symbol|bar_ticks|hX|state_id
    toks = str(uid).split("|", 4)
    if len(toks) != 5:
        raise ValueError(f"bad candidate_uid: {uid!r}")
    bt = int(toks[2])
    h = int(str(toks[3]).lstrip("hH"))
    state_id = str(toks[4])
    return bt, h, state_id


def _parse_barrier_from_state(state_id: str) -> float:
    m = re.search(r"k([0-9]+(?:\.[0-9]+)?)$", str(state_id))
    if not m:
        return float("nan")
    return float(m.group(1))


def _oco_touch_arrays(
    *,
    close: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    hlf: np.ndarray,
    horizon: int,
    barrier_pips: float,
    pip: float,
) -> dict[str, np.ndarray] | None:
    h = int(horizon)
    n_eff = len(close) - 2 * h
    if n_eff <= 100:
        return None
    i0 = np.arange(n_eff, dtype=np.int64)
    ref = close[i0]
    valid = np.isfinite(ref)
    i0 = i0[valid]
    ref = ref[valid]
    k = float(barrier_pips)
    up_thr = ref + k * float(pip)
    dn_thr = ref - k * float(pip)

    inf = h + 1
    up_step = np.full(len(i0), inf, dtype=np.int32)
    dn_step = np.full(len(i0), inf, dtype=np.int32)
    for s in range(1, h + 1):
        j = i0 + int(s)
        hu = high[j] >= up_thr
        hd = low[j] <= dn_thr
        up_step[(up_step == inf) & hu] = int(s)
        dn_step[(dn_step == inf) & hd] = int(s)

    side = np.zeros(len(i0), dtype=np.int8)
    side[up_step < dn_step] = 1
    side[dn_step < up_step] = -1

    same = (up_step == dn_step) & (up_step <= h)
    if np.any(same):
        z = np.flatnonzero(same)
        tie_idx = i0[z] + up_step[z].astype(np.int64, copy=False)
        tie_hlf = hlf[tie_idx]
        side[z[tie_hlf > 0.0]] = 1
        side[z[tie_hlf < 0.0]] = -1

    decided = side != 0
    touch_step = np.minimum(up_step, dn_step).astype(float)
    touch_step[~decided] = np.nan
    return {"i0": i0, "ref": ref, "side": side, "decided": decided, "touch_step": touch_step}


def _rebuild_touch_events(
    *,
    symbol: str,
    pred_path: Path,
    velocity_dir: Path,
    use_exec_selected: bool,
    quantile: float,
) -> pd.DataFrame:
    use_cols = ["close_ts", "candidate_uid", "target_gross_pips", "pred_prob"]
    if use_exec_selected:
        use_cols.append("selected_exec")
    try:
        d = pd.read_parquet(pred_path, columns=use_cols).copy()
    except Exception:
        # Fallback for files without optional selection columns.
        d = pd.read_parquet(pred_path, columns=["close_ts", "candidate_uid", "target_gross_pips", "pred_prob"]).copy()
    d["close_ts"] = pd.to_datetime(d["close_ts"], utc=True, errors="coerce")
    d["target_gross_pips"] = pd.to_numeric(d["target_gross_pips"], errors="coerce")
    d = d.dropna(subset=["close_ts", "candidate_uid", "target_gross_pips"]).copy()

    if use_exec_selected and "selected_exec" in d.columns:
        sel = pd.to_numeric(d["selected_exec"], errors="coerce").fillna(0).astype(int)
        d = d[sel == 1].copy()
    else:
        # Fallback: monthly quantile selection.
        d["test_month"] = d["close_ts"].dt.strftime("%Y-%m")
        out: list[pd.DataFrame] = []
        for _, g in d.groupby("test_month", sort=True):
            p = pd.to_numeric(g["pred_prob"], errors="coerce")
            g2 = g[p.notna()].copy()
            if g2.empty:
                continue
            thr = float(np.quantile(pd.to_numeric(g2["pred_prob"], errors="coerce").to_numpy(dtype=float), float(quantile)))
            out.append(g2[pd.to_numeric(g2["pred_prob"], errors="coerce") >= thr].copy())
        d = pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=d.columns)

    if d.empty:
        return pd.DataFrame()

    parsed = d["candidate_uid"].astype(str).map(_parse_candidate_uid)
    d["bar_ticks"] = parsed.map(lambda x: x[0]).astype(int)
    d["horizon"] = parsed.map(lambda x: x[1]).astype(int)
    d["state_id"] = parsed.map(lambda x: x[2]).astype(str)
    d["barrier_pips"] = d["state_id"].map(_parse_barrier_from_state)
    d = d[np.isfinite(pd.to_numeric(d["barrier_pips"], errors="coerce"))].copy()
    d["barrier_pips"] = pd.to_numeric(d["barrier_pips"], errors="coerce")

    pip = float(_pip_size(symbol))
    events: list[pd.DataFrame] = []
    for bt, g_bt in d.groupby("bar_ticks", sort=True):
        vpath = velocity_dir / f"{symbol}_{int(bt)}tick_velocity.parquet"
        if not vpath.exists():
            continue
        bars = pd.read_parquet(vpath, columns=["timestamp", "close_ts", "close", "high", "low", "hl_first"]).copy()
        bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True, errors="coerce")
        bars["close_ts"] = pd.to_datetime(bars["close_ts"], utc=True, errors="coerce")
        bars = bars.dropna(subset=["timestamp", "close_ts"]).sort_values("close_ts").reset_index(drop=True)
        bars["idx"] = np.arange(len(bars), dtype=np.int64)

        g = g_bt.merge(bars[["close_ts", "idx"]], on="close_ts", how="inner")
        if g.empty:
            continue

        close = pd.to_numeric(bars["close"], errors="coerce").to_numpy(dtype=float)
        high = pd.to_numeric(bars["high"], errors="coerce").to_numpy(dtype=float)
        low = pd.to_numeric(bars["low"], errors="coerce").to_numpy(dtype=float)
        hlf = pd.to_numeric(bars["hl_first"], errors="coerce").fillna(0.0).to_numpy(dtype=float)

        for (h, k), g_hk in g.groupby(["horizon", "barrier_pips"], sort=False):
            prep = _oco_touch_arrays(close=close, high=high, low=low, hlf=hlf, horizon=int(h), barrier_pips=float(k), pip=pip)
            if prep is None:
                continue
            pos_map = np.full(len(bars), -1, dtype=np.int64)
            pos_map[prep["i0"]] = np.arange(len(prep["i0"]), dtype=np.int64)

            idx = g_hk["idx"].to_numpy(dtype=np.int64)
            keep = (idx >= 0) & (idx < len(pos_map))
            idx = idx[keep]
            if len(idx) == 0:
                continue
            g2 = g_hk.iloc[np.flatnonzero(keep)].copy()
            j = pos_map[idx]
            keep2 = j >= 0
            if not np.any(keep2):
                continue
            idx = idx[keep2]
            g2 = g2.iloc[np.flatnonzero(keep2)].copy()
            j = j[keep2]

            decided = prep["decided"][j]
            side = prep["side"][j]
            touch_step = prep["touch_step"][j]
            ref = close[idx]
            touch_idx = idx + np.nan_to_num(touch_step, nan=0.0).astype(np.int64)

            use = decided & np.isfinite(touch_step) & (touch_idx >= 0) & (touch_idx < len(bars))
            if not np.any(use):
                continue
            iu = np.flatnonzero(use)
            g3 = g2.iloc[iu].copy()
            side3 = side[iu].astype(np.int8)
            ref3 = ref[iu].astype(float)
            touch_idx3 = touch_idx[iu].astype(np.int64)
            k3 = float(k)
            barrier_px = ref3 + side3.astype(float) * (k3 * pip)

            g3["side"] = side3
            g3["touch_idx"] = touch_idx3
            g3["touch_open_ts"] = bars["timestamp"].to_numpy()[touch_idx3]
            g3["touch_close_ts"] = bars["close_ts"].to_numpy()[touch_idx3]
            g3["barrier_px"] = barrier_px
            events.append(
                g3[
                    [
                        "close_ts",
                        "candidate_uid",
                        "target_gross_pips",
                        "bar_ticks",
                        "horizon",
                        "barrier_pips",
                        "side",
                        "barrier_px",
                        "touch_open_ts",
                        "touch_close_ts",
                    ]
                ].copy()
            )
    return pd.concat(events, ignore_index=True) if events else pd.DataFrame()


def _first_cross_overshoot_month(
    *,
    month_events: pd.DataFrame,
    tick_file: Path,
    pip: float,
) -> pd.DataFrame:
    ticks = pd.read_parquet(tick_file, columns=["timestamp", "bid"]).copy()
    ticks["timestamp"] = pd.to_datetime(ticks["timestamp"], utc=True, errors="coerce")
    ticks["bid"] = pd.to_numeric(ticks["bid"], errors="coerce")
    ticks = ticks.dropna(subset=["timestamp", "bid"]).sort_values("timestamp").reset_index(drop=True)
    if ticks.empty or month_events.empty:
        x = month_events.copy()
        x["touch_found_tick"] = 0
        x["overshoot_tick_pips"] = np.nan
        return x

    ts_ns = ticks["timestamp"].astype("int64").to_numpy(dtype=np.int64)
    px = ticks["bid"].to_numpy(dtype=float)

    starts_ns = pd.to_datetime(month_events["touch_open_ts"], utc=True, errors="coerce").astype("int64").to_numpy(dtype=np.int64)
    ends_ns = pd.to_datetime(month_events["touch_close_ts"], utc=True, errors="coerce").astype("int64").to_numpy(dtype=np.int64)
    side = pd.to_numeric(month_events["side"], errors="coerce").fillna(0).astype(int).to_numpy(dtype=np.int8)
    barrier = pd.to_numeric(month_events["barrier_px"], errors="coerce").to_numpy(dtype=float)

    left_idx = np.searchsorted(ts_ns, starts_ns, side="left")
    right_idx = np.searchsorted(ts_ns, ends_ns, side="right")

    found = np.zeros(len(month_events), dtype=np.int8)
    overs = np.full(len(month_events), np.nan, dtype=float)
    for i in range(len(month_events)):
        if not np.isfinite(barrier[i]) or side[i] == 0:
            continue
        li = int(left_idx[i])
        ri = int(right_idx[i])
        if ri <= li:
            continue
        seg = px[li:ri]
        if side[i] > 0:
            hit = np.flatnonzero(seg >= barrier[i])
            if len(hit) > 0:
                found[i] = 1
                overs[i] = (seg[int(hit[0])] - barrier[i]) / float(pip)
        else:
            hit = np.flatnonzero(seg <= barrier[i])
            if len(hit) > 0:
                found[i] = 1
                overs[i] = (barrier[i] - seg[int(hit[0])]) / float(pip)

    out = month_events.copy()
    out["touch_found_tick"] = found
    out["overshoot_tick_pips"] = overs
    return out


def _summary_stats(x: np.ndarray) -> dict[str, float]:
    v = np.asarray(x, dtype=float)
    v = v[np.isfinite(v)]
    if len(v) == 0:
        return {k: float("nan") for k in ["mean", "median", "p90", "p95", "p99", "max"]}
    return {
        "mean": float(np.mean(v)),
        "median": float(np.median(v)),
        "p90": float(np.quantile(v, 0.90)),
        "p95": float(np.quantile(v, 0.95)),
        "p99": float(np.quantile(v, 0.99)),
        "max": float(np.max(v)),
    }


def _cap_sweep(d: pd.DataFrame, caps: list[float]) -> pd.DataFrame:
    rows: list[dict[str, float]] = []
    gross = pd.to_numeric(d["target_gross_pips"], errors="coerce").to_numpy(dtype=float)
    ov = pd.to_numeric(d["overshoot_tick_pips"], errors="coerce").to_numpy(dtype=float)
    found = pd.to_numeric(d["touch_found_tick"], errors="coerce").fillna(0).astype(int).to_numpy(dtype=int) == 1

    for c in caps:
        fill = found & np.isfinite(ov) & (ov <= float(c))
        fill_rate = float(np.mean(fill)) if len(fill) else float("nan")
        if np.any(fill):
            g = gross[fill]
            o = ov[fill]
            # optimistic: no extra slippage beyond trigger fill (entry at barrier)
            mean_gross_no_slip = float(np.mean(g))
            # conservative: pay full measured overshoot
            mean_net_full_overshoot = float(np.mean(g - o))
            mean_per_signal_no_slip = mean_gross_no_slip * fill_rate
            mean_per_signal_full_overshoot = mean_net_full_overshoot * fill_rate
        else:
            mean_gross_no_slip = float("nan")
            mean_net_full_overshoot = float("nan")
            mean_per_signal_no_slip = float("nan")
            mean_per_signal_full_overshoot = float("nan")
        rows.append(
            {
                "cap_pips": float(c),
                "fill_rate": float(fill_rate),
                "mean_gross_filled_no_extra_slip": float(mean_gross_no_slip),
                "mean_net_filled_full_overshoot": float(mean_net_full_overshoot),
                "mean_per_signal_no_extra_slip": float(mean_per_signal_no_slip),
                "mean_per_signal_full_overshoot": float(mean_per_signal_full_overshoot),
            }
        )
    return pd.DataFrame(rows)


def run_symbol(
    *,
    symbol: str,
    pred_path: Path,
    velocity_dir: Path,
    tick_root: Path,
    caps: list[float],
    use_exec_selected: bool,
    quantile: float,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    events = _rebuild_touch_events(
        symbol=symbol,
        pred_path=pred_path,
        velocity_dir=velocity_dir,
        use_exec_selected=bool(use_exec_selected),
        quantile=float(quantile),
    )
    if events.empty:
        return events, pd.DataFrame(), {"symbol": symbol, "rows": 0}

    pip = float(_pip_size(symbol))
    events["touch_month"] = pd.to_datetime(events["touch_open_ts"], utc=True, errors="coerce").dt.strftime("%Y%m")

    out_parts: list[pd.DataFrame] = []
    for m, g in events.groupby("touch_month", sort=True):
        tick_file = tick_root / symbol / f"{symbol}_{str(m)}_ticks.parquet"
        if not tick_file.exists():
            x = g.copy()
            x["touch_found_tick"] = 0
            x["overshoot_tick_pips"] = np.nan
            out_parts.append(x)
            continue
        out_parts.append(_first_cross_overshoot_month(month_events=g, tick_file=tick_file, pip=pip))
    out = pd.concat(out_parts, ignore_index=True) if out_parts else events.assign(touch_found_tick=0, overshoot_tick_pips=np.nan)
    # Normalize touch month from final UTC touch_open_ts so downstream joins/audits are stable.
    out["touch_open_ts"] = pd.to_datetime(out["touch_open_ts"], utc=True, errors="coerce")
    out["touch_close_ts"] = pd.to_datetime(out["touch_close_ts"], utc=True, errors="coerce")
    out["touch_month"] = out["touch_open_ts"].dt.strftime("%Y%m")

    overs = pd.to_numeric(out["overshoot_tick_pips"], errors="coerce").to_numpy(dtype=float)
    stats = _summary_stats(overs)
    found = pd.to_numeric(out["touch_found_tick"], errors="coerce").fillna(0).astype(int).to_numpy(dtype=int)
    base_gross = float(pd.to_numeric(out["target_gross_pips"], errors="coerce").mean())
    summary = {
        "symbol": symbol,
        "rows": int(len(out)),
        "touch_found_rate": float(np.mean(found == 1)) if len(out) else float("nan"),
        "base_mean_gross_pips": base_gross,
        "tick_overshoot_mean_pips": float(stats["mean"]),
        "tick_overshoot_median_pips": float(stats["median"]),
        "tick_overshoot_p90_pips": float(stats["p90"]),
        "tick_overshoot_p95_pips": float(stats["p95"]),
        "tick_overshoot_p99_pips": float(stats["p99"]),
    }
    sweep = _cap_sweep(out, caps)
    return out, sweep, summary


def main() -> None:
    p = argparse.ArgumentParser(description="Tick first-crossing stop-limit analysis for OCO events")
    p.add_argument("--symbols", default="EURUSD,GBPUSD")
    p.add_argument("--pred-paths", default="")
    p.add_argument("--velocity-dir", default="data/analysis/tick_velocity")
    p.add_argument("--tick-root", default="/Users/danielfisher/Desktop/tick")
    p.add_argument("--caps", default="0.5,0.8,1.0,1.2,1.5,2.0")
    p.add_argument("--use-exec-selected", default="true")
    p.add_argument("--quantile", type=float, default=0.9)
    p.add_argument("--out-dir", default="data/analysis/tick_opportunity_mining/stop_limit_tickfill")
    p.add_argument("--report-out", default="docs/analysis/oco_stop_limit_tickfill_report.md")
    args = p.parse_args()

    symbols = [x.strip().upper() for x in str(args.symbols).split(",") if x.strip()]
    caps = [float(x.strip()) for x in str(args.caps).split(",") if x.strip()]
    velocity_dir = Path(str(args.velocity_dir))
    tick_root = Path(str(args.tick_root))
    out_dir = Path(str(args.out_dir))
    out_dir.mkdir(parents=True, exist_ok=True)
    use_exec_selected = str(args.use_exec_selected).strip().lower() in {"1", "true", "yes", "y"}

    pred_paths_raw = [x.strip() for x in str(args.pred_paths).split(",") if x.strip()]
    pred_map: dict[str, Path] = {}
    if pred_paths_raw:
        if len(pred_paths_raw) != len(symbols):
            raise ValueError("--pred-paths must match --symbols length when provided")
        pred_map = {symbols[i]: Path(pred_paths_raw[i]) for i in range(len(symbols))}
    else:
        defaults = {
            "EURUSD": Path("data/analysis/tick_opportunity_mining/wfo_2025_m3to1_oco_fullcap/EURUSD_oco_monthly_predictions.parquet"),
            "GBPUSD": Path("data/analysis/tick_opportunity_mining/wfo_2025_m3to1_oco_fullcap_gbpusd/GBPUSD_oco_monthly_predictions.parquet"),
        }
        for s in symbols:
            if s not in defaults:
                raise ValueError(f"Provide --pred-paths for symbol {s}")
            pred_map[s] = defaults[s]

    summary_rows: list[dict[str, Any]] = []
    cap_rows: list[pd.DataFrame] = []
    for s in symbols:
        pred_path = pred_map[s]
        if not pred_path.exists():
            raise FileNotFoundError(f"missing predictions: {pred_path}")
        detail, sweep, summary = run_symbol(
            symbol=s,
            pred_path=pred_path,
            velocity_dir=velocity_dir,
            tick_root=tick_root,
            caps=caps,
            use_exec_selected=use_exec_selected,
            quantile=float(args.quantile),
        )
        detail_path = out_dir / f"{s}_stop_limit_tickfill_detail.csv"
        sweep_path = out_dir / f"{s}_stop_limit_tickfill_caps.csv"
        detail.to_csv(detail_path, index=False)
        sweep.insert(0, "symbol", s)
        sweep.to_csv(sweep_path, index=False)
        summary_rows.append(summary)
        cap_rows.append(sweep)
        print(f"wrote: {detail_path}")
        print(f"wrote: {sweep_path}")

    summary_df = pd.DataFrame(summary_rows)
    caps_df = pd.concat(cap_rows, ignore_index=True) if cap_rows else pd.DataFrame()
    summary_csv = out_dir / "summary.csv"
    caps_csv = out_dir / "caps_all.csv"
    summary_df.to_csv(summary_csv, index=False)
    caps_df.to_csv(caps_csv, index=False)
    print(f"wrote: {summary_csv}")
    print(f"wrote: {caps_csv}")

    lines: list[str] = []
    def _table(df: pd.DataFrame) -> str:
        if df.empty:
            return "_empty_"
        try:
            return df.to_markdown(index=False)
        except ImportError:
            return "```\n" + df.to_string(index=False) + "\n```"

    lines.append("# OCO Stop-Limit Tick-First-Crossing Analysis")
    lines.append("")
    lines.append("## Setup")
    lines.append(f"- symbols: `{','.join(symbols)}`")
    lines.append(f"- use_exec_selected: `{bool(use_exec_selected)}`")
    lines.append(f"- quantile fallback: `{float(args.quantile)}`")
    lines.append(f"- caps (pips): `{','.join(str(x) for x in caps)}`")
    lines.append("")
    lines.append("## Tick Overshoot Summary")
    lines.append(_table(summary_df))
    lines.append("")
    lines.append("## Stop-Limit Cap Sweep")
    lines.append(_table(caps_df))
    lines.append("")
    report_out = Path(str(args.report_out))
    report_out.parent.mkdir(parents=True, exist_ok=True)
    report_out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote: {report_out}")


if __name__ == "__main__":
    main()
