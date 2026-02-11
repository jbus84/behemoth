import os

import numpy as np
import pandas as pd

from behemoth.core.guardrail import apply_loss_streak_guardrail
from behemoth.core.metrics import sharpe_daily, sharpe_daily_active, sharpe_trade
from services.api.settings import settings

PIPELINE_PATHS = {
    "m5": os.getenv("PIPELINE_M5_PATH", "data/events/events_m5_8yr_v3_mom.csv"),
    "m15": os.getenv("PIPELINE_M15_PATH", "data/events/events_m15_8yr_v3_mom.csv"),
}


def _max_dd(pnls: np.ndarray) -> float:
    if len(pnls) == 0:
        return 0.0
    curve = np.cumsum(pnls)
    peak = np.maximum.accumulate(curve)
    return float((curve - peak).min())


def _metrics(pnls: np.ndarray, ts: np.ndarray) -> dict:
    if len(pnls) == 0:
        return {
            "trades": 0,
            "win_rate": 0.0,
            "mean_pnl": 0.0,
            "total_pnl": 0.0,
            "max_dd": 0.0,
            "sharpe": 0.0,
            "sharpe_active": 0.0,
            "sharpe_trade": 0.0,
        }
    raw_trades = int(len(pnls))
    win_rate = float((pnls > 0).mean() * 100.0)
    mean_pnl = float(np.mean(pnls))
    total_pnl = float(np.sum(pnls))

    # aggregate same-timestamp trades for dd/sharpe stability
    if len(ts) == len(pnls) and len(ts) > 0:
        df = pd.DataFrame({"ts": ts, "pnl": pnls})
        agg = df.groupby("ts")["pnl"].sum().reset_index()
        ts_agg = agg["ts"].to_numpy()
        pnls_agg = agg["pnl"].to_numpy()
    else:
        ts_agg = ts
        pnls_agg = pnls

    return {
        "trades": raw_trades,
        "win_rate": win_rate,
        "mean_pnl": mean_pnl,
        "total_pnl": total_pnl,
        "max_dd": _max_dd(pnls_agg),
        "sharpe": float(sharpe_daily(pnls_agg, ts_agg)),
        "sharpe_active": float(sharpe_daily_active(pnls_agg, ts_agg)),
        "sharpe_trade": float(sharpe_trade(pnls_agg, ts_agg)),
    }


def _compute_exit_ts(df: pd.DataFrame, bar_minutes: int) -> np.ndarray:
    if "exit_ts" in df.columns:
        return df["exit_ts"].astype("int64").to_numpy()
    if "timestamp" not in df.columns or "duration_bars" not in df.columns:
        # fall back to a zero-filled array to preserve length
        return np.zeros(len(df), dtype="int64")
    bar_ns = int(pd.Timedelta(minutes=bar_minutes).value)
    durations = df["duration_bars"].astype(int)
    timeout_adjust = (durations >= 500).astype(int)
    return (df["timestamp"].astype("int64") + ((durations - timeout_adjust) * bar_ns)).to_numpy()


def _load_pipeline(path: str, bar_minutes: int) -> pd.DataFrame:
    df = pd.read_csv(path)
    if df.empty or "pnl_bps" not in df.columns:
        return pd.DataFrame()
    if "exit_ts" not in df.columns:
        df = df.copy()
        df["exit_ts"] = _compute_exit_ts(df, bar_minutes)
    if "timestamp" in df.columns:
        df = df.sort_values("timestamp")
    return df


def _apply_guardrail_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    cols = [c for c in ("pair", "exit_ts", "pnl_bps") if c in df.columns]
    base = df[cols].copy()
    return apply_loss_streak_guardrail(
        base,
        loss_threshold=settings.guardrail_loss_threshold,
        loss_streak=settings.guardrail_loss_streak,
        cooldown_days=settings.guardrail_cooldown_days,
    )


def compute_summary(path: str, bar_minutes: int, guardrail: bool = False) -> dict:
    df = _load_pipeline(path, bar_minutes)
    if df.empty:
        return _metrics(np.array([]), np.array([]))
    if guardrail:
        df = _apply_guardrail_df(df)
    pnls = df["pnl_bps"].to_numpy()
    ts = df["exit_ts"].to_numpy()
    return _metrics(pnls, ts)


def summary_for_bar(bar: str, guardrail: bool = False) -> dict:
    if bar not in PIPELINE_PATHS:
        raise ValueError(f"Unknown bar: {bar}")
    bar_minutes = 5 if bar == "m5" else 15
    return compute_summary(PIPELINE_PATHS[bar], bar_minutes, guardrail=guardrail)


def summary_from_db(db, bar: str, guardrail: bool = False) -> dict:
    from .models import Position

    rows = db.query(Position).filter(Position.pnl_bps.isnot(None)).all()
    if not rows:
        return _metrics(np.array([]), np.array([]))

    df = pd.DataFrame(
        [
            {
                "pair": r.pair,
                "exit_ts": int(pd.Timestamp(r.exit_ts).value) if r.exit_ts is not None else None,
                "pnl_bps": r.pnl_bps,
            }
            for r in rows
            if r.pnl_bps is not None and r.exit_ts is not None
        ]
    )
    if df.empty:
        return _metrics(np.array([]), np.array([]))
    if guardrail:
        df = _apply_guardrail_df(df)
    return _metrics(df["pnl_bps"].to_numpy(), df["exit_ts"].to_numpy())


def _filter_pipeline_to_db(
    pipe: pd.DataFrame,
    db_positions: pd.DataFrame,
    tol_ns: int,
    match_pair: bool,
) -> pd.DataFrame:
    if pipe.empty or db_positions.empty:
        return pipe.iloc[:0]
    db_positions = db_positions.sort_values("exit_ts")
    pipe = pipe.sort_values("exit_ts")

    if match_pair:
        out_rows = []
        for pair, sub in pipe.groupby("pair"):
            db_sub = db_positions[db_positions["pair"] == pair]
            if db_sub.empty:
                continue
            target = db_sub["exit_ts"].to_numpy()
            idx = np.searchsorted(target, sub["exit_ts"].to_numpy())
            keep = []
            for i, ts in enumerate(sub["exit_ts"].to_numpy()):
                candidates = []
                if idx[i] < len(target):
                    candidates.append(abs(target[idx[i]] - ts))
                if idx[i] > 0:
                    candidates.append(abs(target[idx[i] - 1] - ts))
                if candidates and min(candidates) <= tol_ns:
                    keep.append(True)
                else:
                    keep.append(False)
            out_rows.append(sub.loc[keep])
        if not out_rows:
            return pipe.iloc[:0]
        return pd.concat(out_rows, ignore_index=True)

    target = db_positions["exit_ts"].to_numpy()
    idx = np.searchsorted(target, pipe["exit_ts"].to_numpy())
    keep = []
    for i, ts in enumerate(pipe["exit_ts"].to_numpy()):
        candidates = []
        if idx[i] < len(target):
            candidates.append(abs(target[idx[i]] - ts))
        if idx[i] > 0:
            candidates.append(abs(target[idx[i] - 1] - ts))
        keep.append(bool(candidates and min(candidates) <= tol_ns))
    return pipe.loc[keep]


def compare_pipeline_to_db(
    db,
    bar: str,
    tol_mean: float = 1e-6,
    tol_total: float = 1e-6,
    tol_max_dd: float = 1e-6,
    tol_sharpe: float = 1e-6,
    tol_sharpe_active: float = 1e-6,
    tol_sharpe_trade: float = 1e-6,
    tol_win_rate: float = 1e-6,
    match_ts: bool = False,
    ts_tolerance_ns: int = 0,
    match_pair: bool = False,
    guardrail: bool = False,
) -> dict:
    bar_minutes = 5 if bar == "m5" else 15
    pipe_df = _load_pipeline(PIPELINE_PATHS[bar], bar_minutes)

    from .models import Position

    rows = db.query(Position).filter(Position.pnl_bps.isnot(None)).all()
    db_df = pd.DataFrame(
        [
            {
                "pair": r.pair,
                "exit_ts": int(pd.Timestamp(r.exit_ts).value) if r.exit_ts is not None else None,
                "pnl_bps": r.pnl_bps,
            }
            for r in rows
            if r.pnl_bps is not None and r.exit_ts is not None
        ]
    )
    if guardrail:
        pipe_df = _apply_guardrail_df(pipe_df)
        db_df = _apply_guardrail_df(db_df)
    if match_ts:
        pipe_df = _filter_pipeline_to_db(pipe_df, db_df, ts_tolerance_ns, match_pair)

    pipe = (
        _metrics(pipe_df["pnl_bps"].to_numpy(), pipe_df["exit_ts"].to_numpy())
        if not pipe_df.empty
        else _metrics(np.array([]), np.array([]))
    )
    dbm = (
        _metrics(db_df["pnl_bps"].to_numpy(), db_df["exit_ts"].to_numpy())
        if not db_df.empty
        else _metrics(np.array([]), np.array([]))
    )
    return {
        "pipeline": pipe,
        "db": dbm,
        "delta": {
            "trades": dbm["trades"] - pipe["trades"],
            "mean_pnl": dbm["mean_pnl"] - pipe["mean_pnl"],
            "total_pnl": dbm["total_pnl"] - pipe["total_pnl"],
            "max_dd": dbm["max_dd"] - pipe["max_dd"],
            "sharpe": dbm["sharpe"] - pipe["sharpe"],
            "sharpe_active": dbm["sharpe_active"] - pipe["sharpe_active"],
            "sharpe_trade": dbm["sharpe_trade"] - pipe["sharpe_trade"],
            "win_rate": dbm["win_rate"] - pipe["win_rate"],
        },
        "within_tolerance": (
            abs(dbm["mean_pnl"] - pipe["mean_pnl"]) <= tol_mean
            and abs(dbm["total_pnl"] - pipe["total_pnl"]) <= tol_total
            and abs(dbm["max_dd"] - pipe["max_dd"]) <= tol_max_dd
            and abs(dbm["sharpe"] - pipe["sharpe"]) <= tol_sharpe
            and abs(dbm["sharpe_active"] - pipe["sharpe_active"]) <= tol_sharpe_active
            and abs(dbm["sharpe_trade"] - pipe["sharpe_trade"]) <= tol_sharpe_trade
            and abs(dbm["win_rate"] - pipe["win_rate"]) <= tol_win_rate
        ),
    }


def compare_predictions_to_pipeline(bar: str, pair: str, ts_tolerance_ns: int = 0) -> dict:
    from .predict import generate_mom_events_for_pair

    bar_minutes = 5 if bar == "m5" else 15
    pipe_df = _load_pipeline(PIPELINE_PATHS[bar], bar_minutes)
    if pipe_df.empty:
        return {"error": "pipeline empty"}

    pipe_pair = pipe_df[pipe_df.get("pair") == pair] if "pair" in pipe_df.columns else pipe_df
    if "strategy_type" in pipe_pair.columns:
        pipe_pair = pipe_pair[pipe_pair["strategy_type"] == "MOM"]

    if pipe_pair.empty:
        return {"error": "pair not found in pipeline"}

    api_events = generate_mom_events_for_pair(bar, pair)
    api_df = pd.DataFrame(api_events)
    if api_df.empty:
        return {"error": "api returned no events"}

    # Match by entry_ts within tolerance
    pipe_pair = pipe_pair.sort_values("timestamp")
    pipe_pair = pipe_pair.assign(entry_ts=pipe_pair["timestamp"].astype("int64"))
    api_df = api_df.sort_values("entry_ts")

    matched = 0
    exit_diff = []
    pnl_diff = []

    pipe_entries = pipe_pair["entry_ts"].to_numpy()
    api_entries = api_df["entry_ts"].to_numpy()

    idx = np.searchsorted(pipe_entries, api_entries)
    for i, entry in enumerate(api_entries):
        candidates = []
        if idx[i] < len(pipe_entries):
            candidates.append(pipe_entries[idx[i]])
        if idx[i] > 0:
            candidates.append(pipe_entries[idx[i] - 1])
        if not candidates:
            continue
        closest = min(candidates, key=lambda x: abs(x - entry))
        if abs(closest - entry) <= ts_tolerance_ns:
            matched += 1
            pipe_row = pipe_pair[pipe_pair["entry_ts"] == closest].iloc[0]
            pipe_exit = pipe_row.get("exit_ts")
            if pd.isna(pipe_exit):
                pipe_exit = int(pipe_row["entry_ts"])
            api_row = api_df.iloc[i]
            exit_diff.append(abs(int(api_row["exit_ts"]) - int(pipe_exit)))
            pnl_diff.append(abs(float(api_row["pnl_bps"]) - float(pipe_row["pnl_bps"])))

    match_rate = matched / max(len(pipe_entries), 1)
    return {
        "pair": pair,
        "bar": bar,
        "pipeline_trades": int(len(pipe_entries)),
        "api_trades": int(len(api_entries)),
        "matched": matched,
        "match_rate": match_rate,
        "exit_ts_max_diff_ns": int(max(exit_diff)) if exit_diff else None,
        "pnl_mean_abs_diff": float(np.mean(pnl_diff)) if pnl_diff else None,
    }
