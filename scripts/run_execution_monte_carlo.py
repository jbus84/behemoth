#!/usr/bin/env python3
"""Execution Monte Carlo (month x session) for OCO stop-limit realism.

This script builds stress scenarios from Stage 04 tickfill artifacts and emits:
- month x session scenario summaries
- symbol x scenario aggregates
- markdown report
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    latency_shift_pips: float
    spread_add_pips: float
    fill_decay: float


SCENARIOS: tuple[Scenario, ...] = (
    Scenario("S0_baseline", latency_shift_pips=0.0, spread_add_pips=0.0, fill_decay=0.0),
    Scenario("S1_mild", latency_shift_pips=0.05, spread_add_pips=0.05, fill_decay=0.01),
    Scenario("S2_moderate", latency_shift_pips=0.10, spread_add_pips=0.10, fill_decay=0.03),
    Scenario("S3_severe", latency_shift_pips=0.20, spread_add_pips=0.20, fill_decay=0.06),
)


def _table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_empty_"
    try:
        return df.to_markdown(index=False)
    except Exception:
        return "```\n" + df.to_string(index=False) + "\n```"


def _parse_symbols(raw: str) -> list[str]:
    return [x.strip().upper() for x in str(raw).split(",") if x.strip()]


def _num_series(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def _dt_utc(s: pd.Series) -> pd.Series:
    try:
        return pd.to_datetime(s, utc=True, errors="coerce", format="mixed")
    except TypeError:
        return pd.to_datetime(s, utc=True, errors="coerce")


def _session_bucket(hour_utc: int) -> str:
    h = int(hour_utc)
    if 0 <= h <= 7:
        return "ASIA"
    if 8 <= h <= 12:
        return "LONDON"
    if 13 <= h <= 21:
        return "NY"
    return "LATE"


def _best_cap_for_symbol(caps: pd.DataFrame, symbol: str) -> float:
    c = caps.copy()
    if "symbol" in c.columns:
        c = c[c["symbol"].astype(str).str.upper() == str(symbol).upper()].copy()
    if c.empty:
        raise ValueError(f"no cap rows for {symbol}")
    c["mean_per_signal_full_overshoot"] = _num_series(c["mean_per_signal_full_overshoot"])
    c["cap_pips"] = _num_series(c["cap_pips"])
    c = c.dropna(subset=["cap_pips", "mean_per_signal_full_overshoot"]).copy()
    if c.empty:
        raise ValueError(f"cap rows invalid for {symbol}")
    best_idx = int(c["mean_per_signal_full_overshoot"].idxmax())
    return float(c.loc[best_idx, "cap_pips"])


def _prepare_detail(detail: pd.DataFrame) -> pd.DataFrame:
    d = detail.copy()
    d["touch_open_ts"] = _dt_utc(d["touch_open_ts"])
    d["target_gross_pips"] = _num_series(d["target_gross_pips"])
    d["overshoot_tick_pips"] = _num_series(d["overshoot_tick_pips"])
    d["touch_found_tick"] = _num_series(d["touch_found_tick"]).fillna(0).astype(int)
    d = d.dropna(subset=["touch_open_ts", "target_gross_pips"]).copy()
    d["test_month"] = d["touch_open_ts"].dt.strftime("%Y-%m")
    d["hour_utc"] = d["touch_open_ts"].dt.hour.astype(int)
    d["session_bucket"] = d["hour_utc"].map(_session_bucket)
    return d


def _normal_draws(
    rng: np.random.Generator,
    *,
    mean: float,
    sd: float,
    size: int,
    min_value: float | None = None,
    max_value: float | None = None,
) -> np.ndarray:
    if not (np.isfinite(mean) and np.isfinite(sd)) or size <= 0:
        return np.full(max(size, 0), np.nan, dtype=float)
    if sd <= 0:
        out = np.full(size, mean, dtype=float)
    else:
        out = rng.normal(loc=mean, scale=sd, size=size).astype(float)
    if min_value is not None:
        out = np.maximum(out, float(min_value))
    if max_value is not None:
        out = np.minimum(out, float(max_value))
    return out


def _simulate_symbol_scenario(
    *,
    detail: pd.DataFrame,
    scenario: Scenario,
    cap_pips: float,
    iterations: int,
    seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    d = detail.copy()

    cap_eff = max(float(cap_pips) - float(scenario.latency_shift_pips), 0.0)
    touch = (d["touch_found_tick"] == 1) & d["overshoot_tick_pips"].notna()
    cap_fill = touch & (d["overshoot_tick_pips"] <= cap_eff)

    overs = d["overshoot_tick_pips"].fillna(np.inf).to_numpy(dtype=float)
    gross = d["target_gross_pips"].to_numpy(dtype=float)
    cap_fill_np = cap_fill.to_numpy(dtype=bool)
    fill_decay_keep = max(0.0, 1.0 - float(scenario.fill_decay))
    q = np.where(cap_fill_np, fill_decay_keep, 0.0).astype(float)

    # Additional slip above cap plus spread/latency add-ons.
    extra_slip = float(scenario.spread_add_pips) + np.where(
        cap_fill_np, np.maximum(0.0, overs - cap_eff), 0.0
    )
    pnl_pre = np.where(cap_fill_np, gross - extra_slip, 0.0).astype(float)

    d["q_keep"] = q
    d["pnl_pre"] = pnl_pre

    group_cols = ["test_month", "session_bucket"]
    group_rows: list[dict[str, Any]] = []
    month_draw_rows: list[dict[str, Any]] = []

    # Keep per-month draws to compute symbol-level month negativity and drawdown proxy.
    month_draw_map: dict[str, np.ndarray] = {}
    month_fill_map: dict[str, np.ndarray] = {}
    month_n_map: dict[str, int] = {}

    for (month, session), g in d.groupby(group_cols, sort=True):
        n = int(len(g))
        if n <= 0:
            continue
        pnl_g = g["pnl_pre"].to_numpy(dtype=float)
        q_g = g["q_keep"].to_numpy(dtype=float)

        mu_signal = float(np.mean(pnl_g * q_g))
        # x = pnl_pre * Bernoulli(q)
        ex2 = float(np.mean((pnl_g**2) * q_g))
        var_signal = max(ex2 - (mu_signal**2), 0.0)
        sd_mean_signal = float(np.sqrt(var_signal / max(n, 1)))

        mean_fill_rate = float(np.mean(q_g))
        var_fill_count = float(np.sum(q_g * (1.0 - q_g)))
        sd_fill_count = float(np.sqrt(max(var_fill_count, 0.0)))
        mean_fill_count = float(np.sum(q_g))

        mean_signal_draws = _normal_draws(rng, mean=mu_signal, sd=sd_mean_signal, size=iterations)
        sum_draws = mean_signal_draws * float(n)
        fill_count_draws = _normal_draws(
            rng,
            mean=mean_fill_count,
            sd=sd_fill_count,
            size=iterations,
            min_value=0.0,
            max_value=float(n),
        )
        fill_rate_draws = np.where(n > 0, fill_count_draws / float(n), np.nan)
        trade_draws = np.where(fill_count_draws > 1e-9, sum_draws / fill_count_draws, 0.0)

        group_rows.append(
            {
                "test_month": str(month),
                "session_bucket": str(session),
                "signals": n,
                "cap_pips": float(cap_pips),
                "mean_per_signal_pips": float(np.mean(mean_signal_draws)),
                "lb95_per_signal_pips": float(np.quantile(mean_signal_draws, 0.05)),
                "lb99_per_signal_pips": float(np.quantile(mean_signal_draws, 0.01)),
                "mean_per_trade_pips": float(np.mean(trade_draws)),
                "mean_fill_rate": float(np.mean(fill_rate_draws)),
                "scenario_id": scenario.scenario_id,
            }
        )

        month_n_map[str(month)] = int(month_n_map.get(str(month), 0) + n)
        month_draw_map[str(month)] = (
            month_draw_map.get(str(month), np.zeros(iterations, dtype=float)) + sum_draws
        )
        month_fill_map[str(month)] = (
            month_fill_map.get(str(month), np.zeros(iterations, dtype=float)) + fill_count_draws
        )

    for month in sorted(month_draw_map.keys()):
        n_total = int(month_n_map.get(month, 0))
        if n_total <= 0:
            continue
        sum_draws = month_draw_map[month]
        fill_draws = month_fill_map[month]
        per_signal = sum_draws / float(n_total)
        fill_rate = fill_draws / float(n_total)
        per_trade = np.where(fill_draws > 1e-9, sum_draws / fill_draws, 0.0)
        month_draw_rows.append(
            {
                "test_month": month,
                "signals": n_total,
                "scenario_id": scenario.scenario_id,
                "mean_per_signal_pips": float(np.mean(per_signal)),
                "lb95_per_signal_pips": float(np.quantile(per_signal, 0.05)),
                "lb99_per_signal_pips": float(np.quantile(per_signal, 0.01)),
                "mean_per_trade_pips": float(np.mean(per_trade)),
                "mean_fill_rate": float(np.mean(fill_rate)),
                "prob_negative_month": float(np.mean(per_signal < 0.0)),
            }
        )

    # Symbol-level aggregation.
    if month_draw_map:
        months = sorted(month_draw_map.keys())
        total_n = int(sum(month_n_map[m] for m in months))
        total_sum_draws = np.zeros(iterations, dtype=float)
        total_fill_draws = np.zeros(iterations, dtype=float)
        month_matrix = []
        for m in months:
            month_sum = month_draw_map[m]
            month_fill = month_fill_map[m]
            month_signal = month_sum / float(max(month_n_map[m], 1))
            month_matrix.append(month_signal)
            total_sum_draws += month_sum
            total_fill_draws += month_fill
        month_arr = (
            np.vstack(month_matrix) if month_matrix else np.zeros((0, iterations), dtype=float)
        )
        total_signal = total_sum_draws / float(max(total_n, 1))
        total_trade = np.where(total_fill_draws > 1e-9, total_sum_draws / total_fill_draws, 0.0)
        total_fill_rate = total_fill_draws / float(max(total_n, 1))
        worst_month = (
            np.min(month_arr, axis=0) if month_arr.size else np.zeros(iterations, dtype=float)
        )
        symbol_summary = pd.DataFrame(
            [
                {
                    "scenario_id": scenario.scenario_id,
                    "signals": total_n,
                    "months": len(months),
                    "cap_pips": float(cap_pips),
                    "mean_per_signal_pips": float(np.mean(total_signal)),
                    "lb95_per_signal_pips": float(np.quantile(total_signal, 0.05)),
                    "lb99_per_signal_pips": float(np.quantile(total_signal, 0.01)),
                    "mean_per_trade_pips": float(np.mean(total_trade)),
                    "mean_fill_rate": float(np.mean(total_fill_rate)),
                    "prob_negative_month": float(np.mean(month_arr < 0.0))
                    if month_arr.size
                    else float("nan"),
                    "drawdown_proxy_p95": float(np.quantile(worst_month, 0.05)),
                }
            ]
        )
    else:
        symbol_summary = pd.DataFrame(
            [
                {
                    "scenario_id": scenario.scenario_id,
                    "signals": 0,
                    "months": 0,
                    "cap_pips": float(cap_pips),
                    "mean_per_signal_pips": float("nan"),
                    "lb95_per_signal_pips": float("nan"),
                    "lb99_per_signal_pips": float("nan"),
                    "mean_per_trade_pips": float("nan"),
                    "mean_fill_rate": float("nan"),
                    "prob_negative_month": float("nan"),
                    "drawdown_proxy_p95": float("nan"),
                }
            ]
        )

    return pd.DataFrame(group_rows), pd.DataFrame(month_draw_rows), symbol_summary


def run_for_symbol(
    *,
    symbol: str,
    detail_path: Path,
    caps_path: Path,
    iterations: int,
    seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    detail = pd.read_csv(detail_path).copy()
    caps = pd.read_csv(caps_path).copy()
    d = _prepare_detail(detail)
    cap = _best_cap_for_symbol(caps, symbol)

    grp_parts: list[pd.DataFrame] = []
    mon_parts: list[pd.DataFrame] = []
    sym_parts: list[pd.DataFrame] = []
    for i, scenario in enumerate(SCENARIOS):
        g, m, s = _simulate_symbol_scenario(
            detail=d,
            scenario=scenario,
            cap_pips=cap,
            iterations=int(iterations),
            seed=int(seed) + 1000 * i + (abs(hash(symbol)) % 997),
        )
        if not g.empty:
            g["symbol"] = symbol
            grp_parts.append(g)
        if not m.empty:
            m["symbol"] = symbol
            mon_parts.append(m)
        if not s.empty:
            s["symbol"] = symbol
            sym_parts.append(s)
    return (
        pd.concat(grp_parts, ignore_index=True) if grp_parts else pd.DataFrame(),
        pd.concat(mon_parts, ignore_index=True) if mon_parts else pd.DataFrame(),
        pd.concat(sym_parts, ignore_index=True) if sym_parts else pd.DataFrame(),
    )


def _write_report(
    *,
    out_path: Path,
    symbols: list[str],
    iterations: int,
    seed: int,
    month_session: pd.DataFrame,
    symbol_scen: pd.DataFrame,
) -> None:
    lines: list[str] = []
    lines.append("# OCO Execution Monte Carlo Report")
    lines.append("")
    lines.append(
        f"- generated_at_utc: `{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}`"
    )
    lines.append(f"- symbols: `{','.join(symbols)}`")
    lines.append(f"- iterations: `{int(iterations)}`")
    lines.append(f"- seed: `{int(seed)}`")
    lines.append("")
    lines.append("## Scenarios")
    scen_df = pd.DataFrame([s.__dict__ for s in SCENARIOS])
    lines.append(_table(scen_df))
    lines.append("")
    lines.append("## Symbol Scenario Summary")
    lines.append(
        _table(
            symbol_scen.sort_values(["symbol", "scenario_id"])
            if not symbol_scen.empty
            else symbol_scen
        )
    )
    lines.append("")
    lines.append("## Month x Session Summary (head)")
    if month_session.empty:
        lines.append("_empty_")
    else:
        lines.append(
            _table(
                month_session.sort_values(
                    ["symbol", "scenario_id", "test_month", "session_bucket"]
                ).head(120)
            )
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser(description="Execution Monte Carlo for OCO stop-limit artifacts")
    p.add_argument("--symbols", default="EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD")
    p.add_argument(
        "--detail-dir", default="data/analysis/tick_opportunity_mining/stop_limit_tickfill_fullcap"
    )
    p.add_argument(
        "--caps-dir", default="data/analysis/tick_opportunity_mining/stop_limit_tickfill_fullcap"
    )
    p.add_argument("--out-dir", default="data/analysis/tick_opportunity_mining")
    p.add_argument("--iterations", type=int, default=2000)
    p.add_argument("--seed", type=int, default=20260227)
    p.add_argument("--write-draws", action="store_true")
    args = p.parse_args()

    symbols = _parse_symbols(args.symbols)
    detail_dir = Path(str(args.detail_dir))
    caps_dir = Path(str(args.caps_dir))
    out_dir = Path(str(args.out_dir))

    month_session_parts: list[pd.DataFrame] = []
    monthly_parts: list[pd.DataFrame] = []
    symbol_parts: list[pd.DataFrame] = []
    for sym in symbols:
        detail_path = detail_dir / f"{sym}_stop_limit_tickfill_detail.csv"
        caps_path = caps_dir / f"{sym}_stop_limit_tickfill_caps.csv"
        if not detail_path.exists():
            raise FileNotFoundError(detail_path)
        if not caps_path.exists():
            raise FileNotFoundError(caps_path)
        g, m, s = run_for_symbol(
            symbol=sym,
            detail_path=detail_path,
            caps_path=caps_path,
            iterations=int(args.iterations),
            seed=int(args.seed),
        )
        if not g.empty:
            month_session_parts.append(g)
        if not m.empty:
            monthly_parts.append(m)
        if not s.empty:
            symbol_parts.append(s)

    month_session = (
        pd.concat(month_session_parts, ignore_index=True) if month_session_parts else pd.DataFrame()
    )
    monthly = pd.concat(monthly_parts, ignore_index=True) if monthly_parts else pd.DataFrame()
    symbol_scenarios = (
        pd.concat(symbol_parts, ignore_index=True) if symbol_parts else pd.DataFrame()
    )

    if not symbol_scenarios.empty:
        base = symbol_scenarios[symbol_scenarios["scenario_id"] == "S0_baseline"][
            ["symbol", "mean_fill_rate"]
        ].rename(columns={"mean_fill_rate": "base_fill_rate"})
        symbol_scenarios = symbol_scenarios.merge(base, on="symbol", how="left")
        symbol_scenarios["fill_rate_drop_vs_S0"] = (
            symbol_scenarios["base_fill_rate"] - symbol_scenarios["mean_fill_rate"]
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    month_session_csv = out_dir / "execution_mc_month_session_summary.csv"
    monthly_csv = out_dir / "execution_mc_monthly_summary.csv"
    symbol_csv = out_dir / "execution_mc_symbol_scenarios.csv"
    report_md = Path("docs/analysis/oco_execution_monte_carlo_report.md")

    month_session.to_csv(month_session_csv, index=False)
    monthly.to_csv(monthly_csv, index=False)
    symbol_scenarios.to_csv(symbol_csv, index=False)
    _write_report(
        out_path=report_md,
        symbols=symbols,
        iterations=int(args.iterations),
        seed=int(args.seed),
        month_session=month_session,
        symbol_scen=symbol_scenarios,
    )

    if args.write_draws:
        # Store compact per-month draws proxy as observed monthly summary table.
        # Full raw draw tensors are intentionally not persisted by default.
        monthly.to_parquet(out_dir / "execution_mc_draws.parquet", index=False)

    print(f"wrote: {month_session_csv}")
    print(f"wrote: {monthly_csv}")
    print(f"wrote: {symbol_csv}")
    print(f"wrote: {report_md}")


if __name__ == "__main__":
    main()
