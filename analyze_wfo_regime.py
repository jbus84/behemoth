import argparse
import os

import lightgbm as lgb
import numpy as np
import pandas as pd
import polars as pl


def run_wfo(
    idx_name: str,
    train_months: int = 3,
    test_months: int = 1,
    prob_threshold: float = 0.20,
    corr_threshold: float = -0.20,
):
    input_file = f"full_year_dataset_{idx_name}.parquet"
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"{input_file} not found")

    df = pl.read_parquet(input_file).drop_nulls()
    df = df.with_columns(pl.col("timestamp").dt.strftime("%Y-%m").alias("month"))

    df_pd = df.to_pandas()

    fx_pairs = ["EURUSD", "GBPUSD", "USDCHF", "USDJPY"]
    mapping = {name: i for i, name in enumerate(fx_pairs)}
    df_pd["fx_pair_code"] = df_pd["fx_pair"].map(mapping).fillna(-1).astype(int)

    features = ["fx_ret_5s", "idx_vol_30s", "spread", "hour", "regime_corr_1h", "fx_pair_code"]
    months = sorted(df_pd["month"].unique())

    if len(months) < (train_months + test_months):
        raise ValueError("Not enough months for the requested WFO configuration.")

    results = []
    total_trades = 0
    total_wins = 0

    for i in range(train_months, len(months) - test_months + 1):
        train_m = months[i - train_months : i]
        test_m = months[i : i + test_months]

        train_df = df_pd[df_pd["month"].isin(train_m)]
        test_df = df_pd[df_pd["month"].isin(test_m)]

        if len(train_df) == 0 or len(test_df) == 0:
            continue

        X_train = train_df[features]
        y_train = train_df["target_trend"].values

        clf = lgb.LGBMClassifier(
            n_estimators=200,
            learning_rate=0.03,
            max_depth=6,
            verbose=-1,
            importance_type="gain",
            random_state=42,
        )
        clf.fit(X_train, y_train, categorical_feature=["fx_pair_code"])

        y_prob = clf.predict_proba(test_df[features])[:, 1]

        trade_mask = (
            (test_df["regime_corr_1h"] < corr_threshold)
            & (test_df["fx_ret_5s"].abs() >= 2.0)
            & (y_prob <= prob_threshold)
        )

        trades = test_df[trade_mask]
        trade_count = len(trades)
        win_count = int((trades["target_trend"] == 0).sum())
        win_rate = (win_count / trade_count) if trade_count > 0 else np.nan

        results.append(
            {
                "train_months": ",".join(train_m),
                "test_months": ",".join(test_m),
                "trades": trade_count,
                "wins": win_count,
                "win_rate": win_rate,
            }
        )

        total_trades += trade_count
        total_wins += win_count

    results_df = pd.DataFrame(results)
    overall_win_rate = (total_wins / total_trades) if total_trades > 0 else np.nan

    print(f"\n--- Rolling WFO Summary ({idx_name}) ---")
    print(f"Train Window: {train_months} months | Test Window: {test_months} months")
    print(f"Rule: corr < {corr_threshold}, |fx_ret_5s| >= 2bps, P(Trend) <= {prob_threshold}")
    print(f"Total Trades: {total_trades}")
    print(f"Total Wins:   {total_wins}")
    print(f"Win Rate:     {overall_win_rate:.2%}")
    print("\nPer-Fold Results:")
    with pd.option_context("display.max_rows", None, "display.max_columns", None):
        print(results_df)


def main():
    parser = argparse.ArgumentParser(description="Rolling WFO evaluation for regime-based FX->Index model.")
    parser.add_argument("--idx", default="NSXUSD", help="Index symbol (e.g., NSXUSD)")
    parser.add_argument("--train-months", type=int, default=3)
    parser.add_argument("--test-months", type=int, default=1)
    parser.add_argument("--prob-threshold", type=float, default=0.20)
    parser.add_argument("--corr-threshold", type=float, default=-0.20)
    args = parser.parse_args()

    run_wfo(
        idx_name=args.idx,
        train_months=args.train_months,
        test_months=args.test_months,
        prob_threshold=args.prob_threshold,
        corr_threshold=args.corr_threshold,
    )


if __name__ == "__main__":
    main()
