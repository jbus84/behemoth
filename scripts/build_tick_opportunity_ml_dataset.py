#!/usr/bin/env python3
"""Build ML-ready event datasets from mined tick opportunity candidates."""

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

try:
    from scripts.run_tick_opportunity_mining import (
        _directional_family_states,
        _parse_ints,
        _pip_size,
        _prepare_frame,
        _quantiles,
        _regime_masks,
    )
except ModuleNotFoundError:
    from run_tick_opportunity_mining import (  # type: ignore
        _directional_family_states,
        _parse_ints,
        _pip_size,
        _prepare_frame,
        _quantiles,
        _regime_masks,
    )


DEFAULTS: dict[str, Any] = {
    "symbol": "EURUSD",
    "dataset_dir": "data/analysis/tick_velocity",
    "candidate_dir": "data/analysis/tick_opportunity_mining",
    "train_years": "2022,2023,2024",
    "test_year": 2025,
    "selection_required": True,
    "min_quality_tier": "C",  # A|B|C|D
    "max_candidates_per_library": 120,
    "max_events_per_candidate": 20000,
    "oco_include_no_touch": True,
    "oco_hold_mode": "from_touch",  # from_touch|from_start
    "out_dir": "data/analysis/tick_opportunity_mining/ml_ready",
    "report_out": "docs/analysis/eurusd_tick_opportunity_ml_ready_report.md",
}

TIER_RANK = {"D": 0, "C": 1, "B": 2, "A": 3}


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


def _parse_barrier_pips(row: pd.Series) -> float:
    txt = str(row.get("regime_desc", ""))
    if "barrier=" in txt:
        try:
            return float(txt.split("barrier=")[-1].strip())
        except Exception:
            pass
    sid = str(row.get("state_id", ""))
    m = re.search(r"__k([0-9]+(?:\\.[0-9]+)?)$", sid)
    if m:
        return float(m.group(1))
    raise ValueError(f"Cannot parse barrier from row state_id={sid!r} regime_desc={txt!r}")


def _sample_positions(pos: np.ndarray, max_events: int) -> np.ndarray:
    if int(max_events) <= 0 or len(pos) <= int(max_events):
        return pos
    picks = np.linspace(0, len(pos) - 1, num=int(max_events), dtype=int)
    return pos[picks]


def _sample_positions_balanced(
    *,
    all_pos: np.ndarray,
    trade_pos: np.ndarray,
    max_events: int,
) -> np.ndarray:
    if int(max_events) <= 0 or len(all_pos) <= int(max_events):
        return all_pos
    trade = np.asarray(np.intersect1d(all_pos, trade_pos, assume_unique=False), dtype=np.int64)
    if len(trade) >= int(max_events):
        return _sample_positions(trade, int(max_events))
    out = list(trade.tolist())
    remaining = int(max_events) - len(out)
    all_set = set(all_pos.tolist())
    tr_set = set(trade.tolist())
    no_touch = np.array(sorted(all_set - tr_set), dtype=np.int64)
    if remaining > 0 and len(no_touch) > 0:
        out.extend(_sample_positions(no_touch, remaining).tolist())
    if len(out) < int(max_events):
        rest = np.array(sorted(all_set - set(out)), dtype=np.int64)
        if len(rest) > 0:
            out.extend(_sample_positions(rest, int(max_events) - len(out)).tolist())
    return np.array(sorted(out[: int(max_events)]), dtype=np.int64)


def _ensure_quality_cols(d: pd.DataFrame) -> pd.DataFrame:
    out = d.copy()
    if "quality_tier" not in out.columns:
        out["quality_tier"] = np.where(out.get("selection_pass", False), "C", "D")
    out["quality_tier"] = (
        out["quality_tier"].astype(str).str.upper().map(lambda x: x if x in TIER_RANK else "D")
    )
    if "quality_score" not in out.columns:
        out["quality_score"] = out["quality_tier"].map(TIER_RANK).astype(int)
    return out


def _select_candidates(
    d: pd.DataFrame,
    *,
    symbol: str,
    selection_required: bool,
    min_quality_tier: str,
    max_candidates: int,
) -> pd.DataFrame:
    if d.empty:
        return d
    x = _ensure_quality_cols(d)
    x = x[x["symbol"].astype(str).str.upper() == str(symbol).upper()].copy()
    if bool(selection_required) and "selection_pass" in x.columns:
        x = x[x["selection_pass"].astype(bool)].copy()
    min_rank = TIER_RANK.get(str(min_quality_tier).upper().strip(), 1)
    x = x[x["quality_tier"].map(TIER_RANK) >= int(min_rank)].copy()
    x = x.sort_values(
        ["quality_score", "annualized_test_fills", "mean_gross_pips_test"],
        ascending=[False, False, False],
    ).reset_index(drop=True)
    if int(max_candidates) > 0:
        x = x.head(int(max_candidates)).copy()
    return x


def _feature_cols(df: pd.DataFrame) -> list[str]:
    cols = [
        "cost_est_pips",
        "range_pips",
        "ret1_pips",
        "ret_z",
        "ret_abs_z",
        "vel_cost_units_h1",
        "vel_abs_cost_units_h1",
        "spread_z",
        "tick_rate_z",
        "hour_utc",
        "hl_first",
        "hl_first_mean_24",
        "hl_pos_frac_mean_24",
    ]
    return [c for c in cols if c in df.columns]


def _build_directional_events(
    *,
    split_name: str,
    df: pd.DataFrame,
    q_fit: dict[str, float],
    cands: pd.DataFrame,
    max_events_per_candidate: int,
) -> pd.DataFrame:
    if df.empty or cands.empty:
        return pd.DataFrame()
    features = _feature_cols(df)
    regime_map = {name: np.asarray(mask, dtype=bool) for name, mask in _regime_masks(df, q_fit)}
    fam_map = {
        name: (np.asarray(mask, dtype=bool), np.asarray(side, dtype=np.int8))
        for name, mask, side in _directional_family_states(df, q_fit)
    }

    ts = pd.to_datetime(df["close_ts"], utc=True, errors="coerce")
    rows: list[pd.DataFrame] = []
    for _, r in cands.iterrows():
        fam = str(r["family"])
        regime = str(r["regime_desc"])
        h = int(r["horizon"])
        ycol = f"y_fwd_pips_h{h}"
        if fam not in fam_map or regime not in regime_map or ycol not in df.columns:
            continue
        m_fam, side = fam_map[fam]
        m_reg = regime_map[regime]
        y = pd.to_numeric(df[ycol], errors="coerce").to_numpy(dtype=float)
        valid = np.isfinite(y)
        if h > 0:
            valid[-h:] = False
        mask = valid & m_fam & m_reg & (side != 0)
        pos = np.flatnonzero(mask)
        if len(pos) == 0:
            continue
        pos = _sample_positions(pos, int(max_events_per_candidate))
        gross = side[pos].astype(float) * y[pos]
        chunk = df.iloc[pos][features].copy()
        chunk["close_ts"] = ts.iloc[pos].to_numpy()
        chunk["split"] = str(split_name)
        chunk["library"] = "directional"
        chunk["symbol"] = str(r["symbol"])
        chunk["bar_ticks"] = int(r["bar_ticks"])
        chunk["horizon"] = int(h)
        chunk["family"] = fam
        chunk["state_id"] = str(r["state_id"])
        chunk["regime_desc"] = regime
        chunk["quality_tier"] = str(r["quality_tier"])
        chunk["quality_score"] = int(r["quality_score"])
        chunk["annualized_test_fills"] = float(r["annualized_test_fills"])
        chunk["mean_gross_pips_test"] = float(r["mean_gross_pips_test"])
        chunk["target_gross_pips"] = gross
        chunk["target_gross_pos"] = (gross > 0.0).astype(int)
        chunk["target_abs_gross_pips"] = np.abs(gross)
        chunk["candidate_uid"] = (
            chunk["library"]
            + "|"
            + chunk["symbol"]
            + "|"
            + chunk["bar_ticks"].astype(str)
            + "|h"
            + chunk["horizon"].astype(str)
            + "|"
            + chunk["state_id"]
        )
        rows.append(chunk)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def _oco_precompute(
    df: pd.DataFrame,
    *,
    horizon: int,
    barrier_pips: float,
    pip: float,
    hold_mode: str,
) -> dict[str, np.ndarray]:
    close = pd.to_numeric(df["close"], errors="coerce").to_numpy(dtype=float)
    high = pd.to_numeric(df["high"], errors="coerce").to_numpy(dtype=float)
    low = pd.to_numeric(df["low"], errors="coerce").to_numpy(dtype=float)
    hlf = pd.to_numeric(df["hl_first"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    h = int(horizon)
    mode = str(hold_mode).strip().lower()
    if mode not in {"from_touch", "from_start"}:
        raise ValueError("oco_hold_mode must be from_touch|from_start")
    n_eff = (len(df) - 2 * h) if mode == "from_touch" else (len(df) - h - 1)
    if n_eff <= 100:
        return {}
    i0 = np.arange(n_eff, dtype=np.int64)
    ref = close[i0]
    valid = np.isfinite(ref)
    i0 = i0[valid]
    ref = ref[valid]

    k = float(barrier_pips)
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
    touch_step = np.minimum(up_step, dn_step).astype(float)
    touch_step[~decided] = np.nan
    gross = np.full(len(i0), np.nan, dtype=float)
    if mode == "from_start":
        ex = close[i0 + h]
        ret = (ex - ref) / pip
        gross[decided] = side[decided].astype(float) * ret[decided] - k
    else:
        touch_i = np.minimum(up_step, dn_step).astype(np.int64, copy=False)
        exit_i = i0 + touch_i + int(h)
        ok = decided & (exit_i < len(close))
        if np.any(ok):
            ok_idx = np.flatnonzero(ok)
            ex_ok = close[exit_i[ok_idx]]
            num_ok = np.isfinite(ex_ok) & np.isfinite(ref[ok_idx])
            use = ok_idx[num_ok]
            if len(use) > 0:
                gross[use] = side[use].astype(float) * ((close[exit_i[use]] - ref[use]) / pip) - k
    return {
        "i0": i0,
        "gross": gross,
        "side": side,
        "both": both,
        "decided": decided,
        "touch_step": touch_step,
    }


def _build_oco_events(
    *,
    split_name: str,
    df: pd.DataFrame,
    q_fit: dict[str, float],
    cands: pd.DataFrame,
    max_events_per_candidate: int,
    symbol: str,
    hold_mode: str,
    include_no_touch: bool,
) -> pd.DataFrame:
    if df.empty or cands.empty:
        return pd.DataFrame()
    regimes = {name: np.asarray(mask, dtype=bool) for name, mask in _regime_masks(df, q_fit)}
    features = _feature_cols(df)
    ts = pd.to_datetime(df["close_ts"], utc=True, errors="coerce")
    pip = float(_pip_size(symbol))

    unique_hk = sorted(
        {(int(r["horizon"]), float(_parse_barrier_pips(r))) for _, r in cands.iterrows()}
    )
    cache: dict[tuple[int, float], dict[str, np.ndarray]] = {}
    for h, k in unique_hk:
        prep = _oco_precompute(
            df, horizon=int(h), barrier_pips=float(k), pip=pip, hold_mode=hold_mode
        )
        if prep:
            cache[(int(h), float(k))] = prep

    rows: list[pd.DataFrame] = []
    for _, r in cands.iterrows():
        fam = str(r["family"])
        regime_txt = str(r["regime_desc"])
        regime = regime_txt.split(";")[0].strip()
        if regime not in regimes:
            continue
        h = int(r["horizon"])
        k = float(_parse_barrier_pips(r))
        ck = cache.get((h, k))
        if ck is None:
            continue
        i0 = ck["i0"]
        reg0 = regimes[regime][i0]
        if fam == "oco_first_touch":
            base = ck["decided"]
        elif fam == "oco_first_touch_clean":
            base = ck["decided"] & (~ck["both"])
        else:
            continue
        tradable = base & reg0 & np.isfinite(ck["gross"])
        if bool(include_no_touch):
            arm = reg0
            pos0 = np.flatnonzero(arm)
        else:
            pos0 = np.flatnonzero(tradable)
        if len(pos0) == 0:
            continue
        if bool(include_no_touch):
            pos0 = _sample_positions_balanced(
                all_pos=pos0,
                trade_pos=np.flatnonzero(tradable),
                max_events=int(max_events_per_candidate),
            )
        else:
            pos0 = _sample_positions(pos0, int(max_events_per_candidate))
        idx = i0[pos0]
        gross = np.zeros(len(pos0), dtype=float) if bool(include_no_touch) else ck["gross"][pos0]
        touch_event = tradable[pos0].astype(int)
        if bool(include_no_touch):
            gsrc = ck["gross"][pos0]
            ok = np.isfinite(gsrc) & (touch_event == 1)
            gross[ok] = gsrc[ok]
        chunk = df.iloc[idx][features].copy()
        chunk["close_ts"] = ts.iloc[idx].to_numpy()
        chunk["split"] = str(split_name)
        chunk["library"] = "oco"
        chunk["symbol"] = str(r["symbol"])
        chunk["bar_ticks"] = int(r["bar_ticks"])
        chunk["horizon"] = int(h)
        chunk["family"] = fam
        chunk["state_id"] = str(r["state_id"])
        chunk["regime_desc"] = regime_txt
        chunk["quality_tier"] = str(r["quality_tier"])
        chunk["quality_score"] = int(r["quality_score"])
        chunk["annualized_test_fills"] = float(r["annualized_test_fills"])
        chunk["mean_gross_pips_test"] = float(r["mean_gross_pips_test"])
        chunk["barrier_pips"] = float(k)
        # Do not emit post-outcome path fields (first_touch_side/both_window/touch_step)
        # in ML-ready tables to prevent accidental forward leakage during training.
        chunk["touch_event"] = touch_event
        chunk["target_gross_pips"] = gross
        chunk["target_gross_pos"] = (gross > 0.0).astype(int)
        chunk["target_abs_gross_pips"] = np.abs(gross)
        chunk["candidate_uid"] = (
            chunk["library"]
            + "|"
            + chunk["symbol"]
            + "|"
            + chunk["bar_ticks"].astype(str)
            + "|h"
            + chunk["horizon"].astype(str)
            + "|"
            + chunk["state_id"]
        )
        rows.append(chunk)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def run(cfg: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    symbol = str(cfg["symbol"]).upper().strip()
    dataset_dir = Path(str(cfg["dataset_dir"]))
    candidate_dir = Path(str(cfg["candidate_dir"]))
    train_years = set(_parse_ints(str(cfg["train_years"])))
    test_year = int(cfg["test_year"])
    selection_required = bool(cfg["selection_required"])
    min_quality_tier = str(cfg["min_quality_tier"]).upper().strip()
    max_candidates = int(cfg["max_candidates_per_library"])
    max_events = int(cfg["max_events_per_candidate"])
    oco_hold_mode = str(cfg.get("oco_hold_mode", DEFAULTS["oco_hold_mode"])).strip().lower()
    include_no_touch = bool(cfg.get("oco_include_no_touch", DEFAULTS["oco_include_no_touch"]))
    if oco_hold_mode not in {"from_touch", "from_start"}:
        raise ValueError("oco_hold_mode must be from_touch|from_start")

    d_path = candidate_dir / f"{symbol}_directional_candidates.csv"
    o_path = candidate_dir / f"{symbol}_oco_candidates.csv"
    dir_cands = _select_candidates(
        pd.read_csv(d_path) if d_path.exists() else pd.DataFrame(),
        symbol=symbol,
        selection_required=selection_required,
        min_quality_tier=min_quality_tier,
        max_candidates=max_candidates,
    )
    oco_cands = _select_candidates(
        pd.read_csv(o_path) if o_path.exists() else pd.DataFrame(),
        symbol=symbol,
        selection_required=selection_required,
        min_quality_tier=min_quality_tier,
        max_candidates=max_candidates,
    )

    if dir_cands.empty and oco_cands.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    needed_bar_ticks = sorted(
        set(
            pd.to_numeric(
                pd.concat(
                    [
                        dir_cands.get("bar_ticks", pd.Series(dtype=int)),
                        oco_cands.get("bar_ticks", pd.Series(dtype=int)),
                    ],
                    ignore_index=True,
                ),
                errors="coerce",
            )
            .dropna()
            .astype(int)
            .tolist()
        )
    )
    directional_parts: list[pd.DataFrame] = []
    oco_parts: list[pd.DataFrame] = []
    for bt in needed_bar_ticks:
        path = dataset_dir / f"{symbol}_{int(bt)}tick_velocity.parquet"
        if not path.exists():
            print(f"skip {bt}: missing {path}")
            continue
        hset = sorted(
            set(
                pd.to_numeric(
                    pd.concat(
                        [
                            dir_cands.loc[dir_cands["bar_ticks"] == bt, "horizon"]
                            if not dir_cands.empty
                            else pd.Series(dtype=int),
                            oco_cands.loc[oco_cands["bar_ticks"] == bt, "horizon"]
                            if not oco_cands.empty
                            else pd.Series(dtype=int),
                        ],
                        ignore_index=True,
                    ),
                    errors="coerce",
                )
                .dropna()
                .astype(int)
                .tolist()
            )
        )
        if not hset:
            continue
        d = _prepare_frame(path, symbol=symbol, horizons=hset)
        train = d[d["year"].isin(train_years)].copy().reset_index(drop=True)
        test = d[d["year"] == int(test_year)].copy().reset_index(drop=True)
        if train.empty or test.empty:
            continue
        q_fit = _quantiles(train)

        dc = (
            dir_cands[dir_cands["bar_ticks"] == bt].copy()
            if not dir_cands.empty
            else pd.DataFrame()
        )
        oc = (
            oco_cands[oco_cands["bar_ticks"] == bt].copy()
            if not oco_cands.empty
            else pd.DataFrame()
        )

        if not dc.empty:
            directional_parts.append(
                _build_directional_events(
                    split_name="train",
                    df=train,
                    q_fit=q_fit,
                    cands=dc,
                    max_events_per_candidate=max_events,
                )
            )
            directional_parts.append(
                _build_directional_events(
                    split_name="test",
                    df=test,
                    q_fit=q_fit,
                    cands=dc,
                    max_events_per_candidate=max_events,
                )
            )
        if not oc.empty:
            oco_parts.append(
                _build_oco_events(
                    split_name="train",
                    df=train,
                    q_fit=q_fit,
                    cands=oc,
                    max_events_per_candidate=max_events,
                    symbol=symbol,
                    hold_mode=oco_hold_mode,
                    include_no_touch=include_no_touch,
                )
            )
            oco_parts.append(
                _build_oco_events(
                    split_name="test",
                    df=test,
                    q_fit=q_fit,
                    cands=oc,
                    max_events_per_candidate=max_events,
                    symbol=symbol,
                    hold_mode=oco_hold_mode,
                    include_no_touch=include_no_touch,
                )
            )
        print(f"ok {symbol} {bt}tick")

    directional = (
        pd.concat(directional_parts, ignore_index=True) if directional_parts else pd.DataFrame()
    )
    oco = pd.concat(oco_parts, ignore_index=True) if oco_parts else pd.DataFrame()

    summary_rows: list[dict[str, Any]] = []
    for lib, d in [("directional", directional), ("oco", oco)]:
        if d.empty:
            summary_rows.append(
                {
                    "library": lib,
                    "rows": 0,
                    "candidates": 0,
                    "train_rows": 0,
                    "test_rows": 0,
                    "mean_target_gross_pips": float("nan"),
                    "target_pos_rate": float("nan"),
                }
            )
            continue
        summary_rows.append(
            {
                "library": lib,
                "rows": int(len(d)),
                "candidates": int(d["candidate_uid"].nunique()),
                "train_rows": int((d["split"] == "train").sum()),
                "test_rows": int((d["split"] == "test").sum()),
                "mean_target_gross_pips": float(
                    pd.to_numeric(d["target_gross_pips"], errors="coerce").mean()
                ),
                "target_pos_rate": float(
                    pd.to_numeric(d["target_gross_pos"], errors="coerce").mean()
                ),
            }
        )
    return directional, oco, pd.DataFrame(summary_rows)


def _write_report(
    *,
    report_out: Path,
    cfg: dict[str, Any],
    directional: pd.DataFrame,
    oco: pd.DataFrame,
    summary: pd.DataFrame,
) -> None:
    lines: list[str] = []
    lines.append("# Tick Opportunity ML Dataset Build")
    lines.append("")
    lines.append("## Setup")
    lines.append(f"- symbol: `{cfg['symbol']}`")
    lines.append(f"- train_years: `{cfg['train_years']}`")
    lines.append(f"- test_year: `{cfg['test_year']}`")
    lines.append(f"- selection_required: `{bool(cfg['selection_required'])}`")
    lines.append(f"- min_quality_tier: `{cfg['min_quality_tier']}`")
    lines.append(f"- max_candidates_per_library: `{int(cfg['max_candidates_per_library'])}`")
    lines.append(f"- max_events_per_candidate: `{int(cfg['max_events_per_candidate'])}`")
    lines.append(f"- oco_hold_mode: `{cfg.get('oco_hold_mode', DEFAULTS['oco_hold_mode'])}`")
    lines.append(
        f"- oco_include_no_touch: `{bool(cfg.get('oco_include_no_touch', DEFAULTS['oco_include_no_touch']))}`"
    )
    lines.append("")

    if not summary.empty:
        lines.append("## Summary")
        try:
            lines.append(summary.to_markdown(index=False))
        except Exception:
            lines.append("```text\n" + summary.to_string(index=False) + "\n```")
        lines.append("")

    def _top(df: pd.DataFrame, n: int = 20) -> str:
        if df.empty:
            return "_empty_"
        cols = [
            "split",
            "bar_ticks",
            "horizon",
            "family",
            "state_id",
            "quality_tier",
            "target_gross_pips",
            "target_gross_pos",
        ]
        x = df.sort_values(
            ["split", "quality_score", "target_abs_gross_pips"], ascending=[True, False, False]
        ).head(n)
        try:
            return x[cols].to_markdown(index=False)
        except Exception:
            return "```text\n" + x[cols].to_string(index=False) + "\n```"

    lines.append("## Directional Sample")
    lines.append(_top(directional))
    lines.append("")
    lines.append("## OCO Sample")
    lines.append(_top(oco))
    lines.append("")

    report_out.parent.mkdir(parents=True, exist_ok=True)
    report_out.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser(
        description="Build ML-ready event datasets from tick opportunity candidates"
    )
    p.add_argument("--config", default=None)
    p.add_argument("--symbol", default=None)
    p.add_argument("--dataset-dir", default=None)
    p.add_argument("--candidate-dir", default=None)
    p.add_argument("--train-years", default=None)
    p.add_argument("--test-year", type=int, default=None)
    p.add_argument("--selection-required", default=None)
    p.add_argument("--min-quality-tier", default=None)
    p.add_argument("--max-candidates-per-library", type=int, default=None)
    p.add_argument("--max-events-per-candidate", type=int, default=None)
    p.add_argument("--oco-include-no-touch", default=None)
    p.add_argument("--oco-hold-mode", default=None)
    p.add_argument("--out-dir", default=None)
    p.add_argument("--report-out", default=None)
    args = p.parse_args()

    cfg = _merge_config(args)
    if isinstance(cfg.get("selection_required"), str):
        cfg["selection_required"] = str(cfg["selection_required"]).strip().lower() in {
            "1",
            "true",
            "yes",
            "y",
        }
    if isinstance(cfg.get("oco_include_no_touch"), str):
        cfg["oco_include_no_touch"] = str(cfg["oco_include_no_touch"]).strip().lower() in {
            "1",
            "true",
            "yes",
            "y",
        }

    directional, oco, summary = run(cfg)

    out_dir = Path(str(cfg["out_dir"]))
    out_dir.mkdir(parents=True, exist_ok=True)
    symbol = str(cfg["symbol"]).upper().strip()

    d_par = out_dir / f"{symbol}_directional_ml_events.parquet"
    o_par = out_dir / f"{symbol}_oco_ml_events.parquet"
    s_csv = out_dir / f"{symbol}_ml_dataset_summary.csv"
    directional.to_parquet(d_par, index=False)
    oco.to_parquet(o_par, index=False)
    summary.to_csv(s_csv, index=False)
    print(f"wrote: {d_par}")
    print(f"wrote: {o_par}")
    print(f"wrote: {s_csv}")

    report_out = Path(str(cfg["report_out"]))
    _write_report(report_out=report_out, cfg=cfg, directional=directional, oco=oco, summary=summary)
    print(f"wrote: {report_out}")


if __name__ == "__main__":
    main()
