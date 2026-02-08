#!/usr/bin/env python3
"""
M5 1-step-ahead exploration (MOM/REV) with stateful per-bar samples.

Trains two regressors per strategy:
- target_pnl_1b (next bar)
- target_pnl_3b (next 3 bars)

Favorability methods:
- weighted: 0.7 * pred_1b + 0.3 * pred_3b
- meta: regressor on pred_1b/pred_3b (+ regime features) -> combo target

Evaluation simulates exits by closing a trade when the favorability score <= 0.

Outputs:
- data/analysis/m5_1step_model_metrics.csv
- data/analysis/m5_1step_trading_metrics.csv
- data/analysis/m5_1step_monthly.csv
- data/analysis/m5_1step_session.csv
- data/analysis/m5_1step_symbol.csv
"""

from __future__ import annotations

import argparse
import os
from typing import Iterable

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor, Pool

DATA_PATH = "data/meta_model/events_m5_8yr_v3_1step_dual.csv"
OUT_DIR = "data/analysis"

WEIGHT_1B = 0.7
WEIGHT_3B = 0.3

CATEGORICAL_FEATURES = ["active_leg", "side"]
NUMERIC_FEATURES = [
    "z_entry",
    "z_velocity",
    "z_lag1",
    "z_lag2",
    "z_lag3",
    "dz_lag1",
    "dz_lag2",
    "spread_std",
    "beta_stability",
    "beta",
    "beta_lag1",
    "beta_lag2",
    "signal_beta_lookback",
    "hedge_beta_lookback",
    "beta_mismatch",
    "vol_ratio",
    "correlation_500",
    "trend_strength",
    "hour",
    "day_of_week",
    "ret_X_1h",
    "ret_Y_1h",
    "ret_X_16b",
    "ret_Y_16b",
    "atr_ratio",
    "entry_atr",
    "vol_regime",
]
FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES

META_FEATURES = [
    "pred_1b",
    "pred_3b",
    "vol_ratio",
    "correlation_500",
    "trend_strength",
    "vol_regime",
]

REG_PARAMS = dict(
    iterations=1200,
    depth=7,
    learning_rate=0.03,
    loss_function="RMSE",
    verbose=False,
    random_seed=42,
)

META_PARAMS = dict(
    iterations=800,
    depth=5,
    learning_rate=0.05,
    loss_function="RMSE",
    verbose=False,
    random_seed=42,
)

SESSIONS = [
    ("Asia", 0, 7),
    ("London", 7, 13),
    ("New_York", 13, 21),
    ("Late", 21, 24),
]


def _reg_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    if len(y_true) == 0:
        return dict(mae=0.0, r2=0.0, sign_acc=0.0)
    mae = float(np.mean(np.abs(y_true - y_pred)))
    denom = float(np.sum((y_true - y_true.mean()) ** 2))
    r2 = 1.0 - float(np.sum((y_true - y_pred) ** 2)) / denom if denom > 1e-12 else 0.0
    sign_acc = float((np.sign(y_true) == np.sign(y_pred)).mean() * 100.0)
    return dict(mae=mae, r2=r2, sign_acc=sign_acc)


def _max_dd(pnl: np.ndarray) -> float:
    if len(pnl) == 0:
        return 0.0
    curve = np.cumsum(pnl)
    peak = np.maximum.accumulate(curve)
    return float((curve - peak).min())


def _aggregate_trades(df: pd.DataFrame, group_cols: Iterable[str]) -> pd.DataFrame:
    rows = []
    for keys, grp in df.groupby(list(group_cols)):
        pnl = grp["pnl_bps"].to_numpy()
        ts = grp["entry_timestamp"].to_numpy()
        order = np.argsort(ts)
        pnl = pnl[order]

        row = {
            "trades": int(len(pnl)),
            "win_rate": float((pnl > 0).mean() * 100.0) if len(pnl) else 0.0,
            "mean_pnl": float(pnl.mean()) if len(pnl) else 0.0,
            "total_pnl": float(pnl.sum()) if len(pnl) else 0.0,
            "max_dd": _max_dd(pnl),
        }
        if isinstance(keys, tuple):
            for k, v in zip(group_cols, keys):
                row[k] = v
        else:
            row[next(iter(group_cols))] = keys
        rows.append(row)
    return pd.DataFrame(rows)


def _simulate_trades(df: pd.DataFrame, score_col: str | None) -> pd.DataFrame:
    trades = []
    for trade_id, grp in df.groupby("trade_id"):
        grp = grp.sort_values("bar_offset")
        entry_ts = grp["trade_entry_ts"].iloc[0]
        entry_hour = int(grp["hour"].iloc[0])
        entry_dow = int(grp["day_of_week"].iloc[0])
        pair = grp["pair"].iloc[0]
        strat = grp["strategy_type"].iloc[0]

        exit_row = grp.iloc[-1]
        exit_reason = "band_exit"
        if score_col is not None and score_col in grp.columns:
            for _, row in grp.iterrows():
                score = row[score_col]
                if pd.isna(score):
                    continue
                if score <= 0:
                    exit_row = row
                    exit_reason = "score_exit"
                    break

        pnl = float(exit_row["pnl_bps"])
        duration = int(exit_row["bar_offset"]) + 1
        trades.append(
            {
                "trade_id": trade_id,
                "strategy_type": strat,
                "pair": pair,
                "entry_timestamp": entry_ts,
                "entry_hour": entry_hour,
                "entry_day_of_week": entry_dow,
                "duration_bars": duration,
                "pnl_bps": pnl,
                "exit_reason": exit_reason,
            }
        )
    return pd.DataFrame(trades)


def _add_sessions(df: pd.DataFrame) -> pd.DataFrame:
    def full_session(h: int) -> str:
        for name, start, end in SESSIONS:
            if start <= h < end:
                return name
        return "Unknown"

    out = df.copy()
    out["session"] = out["entry_hour"].map(full_session)
    return out


def _fit_regressor(train: pd.DataFrame, test: pd.DataFrame, target: str) -> tuple[CatBoostRegressor, list[str]]:
    use_features = [f for f in FEATURES if f in train.columns]
    cat_idx = [train[use_features].columns.get_loc(c) for c in CATEGORICAL_FEATURES if c in use_features]

    model = CatBoostRegressor(**REG_PARAMS)
    model.fit(
        Pool(train[use_features], train[target], cat_features=cat_idx),
        eval_set=Pool(test[use_features], test[target], cat_features=cat_idx),
        early_stopping_rounds=80,
    )
    return model, use_features


def _fit_meta_model(train: pd.DataFrame, test: pd.DataFrame, target: str) -> CatBoostRegressor:
    use_features = [f for f in META_FEATURES if f in train.columns]
    model = CatBoostRegressor(**META_PARAMS)
    model.fit(
        Pool(train[use_features], train[target]),
        eval_set=Pool(test[use_features], test[target]),
        early_stopping_rounds=80,
    )
    return model


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", choices=["MOM", "REV", "BOTH"], default="BOTH")
    args = parser.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    df = pd.read_csv(DATA_PATH)

    if "timestamp" not in df.columns or "trade_id" not in df.columns:
        raise RuntimeError("Dataset missing timestamp or trade_id.")

    ts = pd.to_datetime(df["timestamp"].astype("int64"), unit="ns", utc=True, errors="coerce")
    df["year"] = ts.dt.year

    entry_ts = pd.to_datetime(df["trade_entry_ts"].astype("int64"), unit="ns", utc=True, errors="coerce")
    df["entry_month"] = entry_ts.dt.strftime("%Y-%m")

    strategies = ["MOM", "REV"] if args.strategy == "BOTH" else [args.strategy]
    model_rows = []
    trading_rows = []
    monthly_rows = []
    session_rows = []
    symbol_rows = []

    for strat in strategies:
        data = df[df["strategy_type"] == strat].copy()
        train = data[data["year"] <= 2023].copy()
        test = data[data["year"] >= 2024].copy()

        # Fit per-side models
        train_pred = train.copy()
        test_pred = test.copy()
        train_pred["pred_1b"] = np.nan
        train_pred["pred_3b"] = np.nan
        test_pred["pred_1b"] = np.nan
        test_pred["pred_3b"] = np.nan

        for side in ["LONG", "SHORT"]:
            train_side = train_pred[(train_pred["side"] == side) & train_pred["target_pnl_1b"].notna()].copy()
            test_side = test_pred[(test_pred["side"] == side) & test_pred["target_pnl_1b"].notna()].copy()
            if len(train_side) >= 1000 and len(test_side) >= 500:
                reg_1b, feat_1b = _fit_regressor(train_side, test_side, "target_pnl_1b")
                train_side["pred_1b"] = reg_1b.predict(train_side[feat_1b])
                test_side["pred_1b"] = reg_1b.predict(test_side[feat_1b])
                train_pred.loc[train_side.index, "pred_1b"] = train_side["pred_1b"].to_numpy()
                test_pred.loc[test_side.index, "pred_1b"] = test_side["pred_1b"].to_numpy()

                m_train_1b = _reg_metrics(train_side["target_pnl_1b"].to_numpy(), train_side["pred_1b"].to_numpy())
                m_test_1b = _reg_metrics(test_side["target_pnl_1b"].to_numpy(), test_side["pred_1b"].to_numpy())
                model_rows.append({"strategy": strat, "side": side, "target": "pnl_1b", "split": "train", **m_train_1b})
                model_rows.append({"strategy": strat, "side": side, "target": "pnl_1b", "split": "test", **m_test_1b})

            train_side_3b = train_pred[(train_pred["side"] == side) & train_pred["target_pnl_3b"].notna()].copy()
            test_side_3b = test_pred[(test_pred["side"] == side) & test_pred["target_pnl_3b"].notna()].copy()
            if len(train_side_3b) >= 1000 and len(test_side_3b) >= 500:
                reg_3b, feat_3b = _fit_regressor(train_side_3b, test_side_3b, "target_pnl_3b")
                train_side_3b["pred_3b"] = reg_3b.predict(train_side_3b[feat_3b])
                test_side_3b["pred_3b"] = reg_3b.predict(test_side_3b[feat_3b])
                train_pred.loc[train_side_3b.index, "pred_3b"] = train_side_3b["pred_3b"].to_numpy()
                test_pred.loc[test_side_3b.index, "pred_3b"] = test_side_3b["pred_3b"].to_numpy()

                m_train_3b = _reg_metrics(train_side_3b["target_pnl_3b"].to_numpy(), train_side_3b["pred_3b"].to_numpy())
                m_test_3b = _reg_metrics(test_side_3b["target_pnl_3b"].to_numpy(), test_side_3b["pred_3b"].to_numpy())
                model_rows.append({"strategy": strat, "side": side, "target": "pnl_3b", "split": "train", **m_train_3b})
                model_rows.append({"strategy": strat, "side": side, "target": "pnl_3b", "split": "test", **m_test_3b})

        # Favorability scores
        train_pred["score_weighted"] = WEIGHT_1B * train_pred["pred_1b"] + WEIGHT_3B * train_pred["pred_3b"]
        test_pred["score_weighted"] = WEIGHT_1B * test_pred["pred_1b"] + WEIGHT_3B * test_pred["pred_3b"]

        # Meta-model
        train_pred["target_combo"] = WEIGHT_1B * train_pred["target_pnl_1b"] + WEIGHT_3B * train_pred["target_pnl_3b"]
        test_pred["target_combo"] = WEIGHT_1B * test_pred["target_pnl_1b"] + WEIGHT_3B * test_pred["target_pnl_3b"]

        test_pred["score_meta"] = np.nan

        for side in ["LONG", "SHORT"]:
            meta_train = train_pred[
                (train_pred["side"] == side)
                & train_pred["pred_1b"].notna()
                & train_pred["pred_3b"].notna()
                & train_pred["target_combo"].notna()
            ].copy()
            meta_test = test_pred[
                (test_pred["side"] == side)
                & test_pred["pred_1b"].notna()
                & test_pred["pred_3b"].notna()
                & test_pred["target_combo"].notna()
            ].copy()
            if len(meta_train) < 1000 or len(meta_test) < 500:
                continue

            meta_model = _fit_meta_model(meta_train, meta_test, "target_combo")
            use_meta = [f for f in META_FEATURES if f in meta_train.columns]
            meta_train["score_meta"] = meta_model.predict(meta_train[use_meta])
            meta_test["score_meta"] = meta_model.predict(meta_test[use_meta])

            test_pred.loc[meta_test.index, "score_meta"] = meta_test["score_meta"].to_numpy()

            m_meta_train = _reg_metrics(meta_train["target_combo"].to_numpy(), meta_train["score_meta"].to_numpy())
            m_meta_test = _reg_metrics(meta_test["target_combo"].to_numpy(), meta_test["score_meta"].to_numpy())
            model_rows.append({"strategy": strat, "side": side, "target": "meta_pnl", "split": "train", **m_meta_train})
            model_rows.append({"strategy": strat, "side": side, "target": "meta_pnl", "split": "test", **m_meta_test})

        # Trading metrics (test only): simulate exits per trade
        for method, score_col in [("baseline", None), ("weighted", "score_weighted"), ("meta", "score_meta")]:
            trades = _simulate_trades(test_pred, score_col)
            if trades.empty:
                continue

            trades["entry_timestamp"] = pd.to_datetime(trades["entry_timestamp"], unit="ns", utc=True, errors="coerce")
            trades["entry_month"] = trades["entry_timestamp"].dt.strftime("%Y-%m")
            trades = _add_sessions(trades)

            base = _aggregate_trades(trades, ["strategy_type"])
            base["strategy"] = strat
            base["method"] = method
            trading_rows.append(base)

            monthly = _aggregate_trades(trades, ["entry_month"])
            monthly["strategy"] = strat
            monthly["method"] = method
            monthly_rows.append(monthly)

            session = _aggregate_trades(trades, ["session"])
            session["strategy"] = strat
            session["method"] = method
            session_rows.append(session)

            symbol = _aggregate_trades(trades, ["pair"])
            symbol["strategy"] = strat
            symbol["method"] = method
            symbol_rows.append(symbol)

    model_df = pd.DataFrame(model_rows)
    trading_df = pd.concat(trading_rows, ignore_index=True) if trading_rows else pd.DataFrame()
    monthly_df = pd.concat(monthly_rows, ignore_index=True) if monthly_rows else pd.DataFrame()
    session_df = pd.concat(session_rows, ignore_index=True) if session_rows else pd.DataFrame()
    symbol_df = pd.concat(symbol_rows, ignore_index=True) if symbol_rows else pd.DataFrame()

    model_df.to_csv(os.path.join(OUT_DIR, "m5_1step_model_metrics.csv"), index=False)
    trading_df.to_csv(os.path.join(OUT_DIR, "m5_1step_trading_metrics.csv"), index=False)
    monthly_df.to_csv(os.path.join(OUT_DIR, "m5_1step_monthly.csv"), index=False)
    session_df.to_csv(os.path.join(OUT_DIR, "m5_1step_session.csv"), index=False)
    symbol_df.to_csv(os.path.join(OUT_DIR, "m5_1step_symbol.csv"), index=False)

    print("Saved:")
    print("- data/analysis/m5_1step_model_metrics.csv")
    print("- data/analysis/m5_1step_trading_metrics.csv")
    print("- data/analysis/m5_1step_monthly.csv")
    print("- data/analysis/m5_1step_session.csv")
    print("- data/analysis/m5_1step_symbol.csv")


if __name__ == "__main__":
    main()
