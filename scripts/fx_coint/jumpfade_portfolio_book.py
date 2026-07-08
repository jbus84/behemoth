"""Pool the meta-model-filtered jump-fade trades across all 11 hardened-core pairs into
one actual portfolio return series (not just pooled model training) -- equal-risk
sleeves (each pair gets 1/11 of book capital), daily aggregation, annualized Sharpe.

This is the step that was missing: jumpfade_metamodel.py pools pairs to TRAIN one model
and reports pooled trade-level net bps/t-stat, but never builds a calendar-time book the
way project_fx_engineered_book.py combined its reversion sleeves. The earlier naive
per-bar equal-weight pooling attempt (aud_family_jumpfade_combine.py) washed the edge
out because it blended heterogeneous-vol pairs bar-by-bar; this aggregates to DAILY
per-pair returns first (avoiding within-pair overlap double-counting) then equal-weights
across the 11 sleeves, which is closer to how a real book would actually be run.

Uses the same purged expanding-window walk-forward as jumpfade_metamodel.py --no-hour
(the trusted version), collecting OOS (test-year-only) filtered and unfiltered trades
with their bucket timestamps to build the book.
"""

from __future__ import annotations

import numpy as np
import polars as pl
from catboost import CatBoostClassifier

from scripts.fx_coint.jumpfade_metamodel import CORE_PAIRS, build_pair

FEAT_COLS = ["abs_z", "idio_share", "diurnal_scale"]


def main() -> None:
    print("Building pooled feature set...")
    frames = [build_pair(sym) for sym in CORE_PAIRS]
    pooled = pl.concat(frames).sort("bucket")

    years = sorted(pooled["year"].unique().to_list())
    test_years = years[3:]

    oos_rows = []
    for test_y in test_years:
        train = pooled.filter(pl.col("year") < test_y)
        test = pooled.filter(pl.col("year") == test_y)
        if train.height < 500 or test.height < 50:
            continue
        X_train = train.select(FEAT_COLS + ["pair"]).to_pandas()
        y_train = train["win"].to_numpy().astype(int)
        X_test = test.select(FEAT_COLS + ["pair"]).to_pandas()
        model = CatBoostClassifier(iterations=200, depth=4, learning_rate=0.05,
                                    cat_features=["pair"], verbose=False, random_seed=42)
        model.fit(X_train, y_train)
        p_win = model.predict_proba(X_test)[:, 1]
        test_out = test.select("bucket", "pair", "net_bps").with_columns(pl.Series("p_win", p_win))
        oos_rows.append(test_out)

    oos = pl.concat(oos_rows).sort("bucket")
    print(f"total OOS events: {oos.height}  ({oos['bucket'].min()} -> {oos['bucket'].max()})")

    def build_daily_book(df: pl.DataFrame, label: str) -> np.ndarray:
        daily_per_pair = (
            df.with_columns(pl.col("bucket").dt.date().alias("date"))
            .group_by(["date", "pair"])
            .agg(pl.col("net_bps").sum().alias("day_net_bps"))
        )
        # pivot to date x pair, missing = 0 (no trade that pair that day)
        wide = daily_per_pair.pivot(on="pair", index="date", values="day_net_bps").sort("date")
        wide = wide.fill_null(0.0)
        pair_cols = [c for c in wide.columns if c != "date"]
        n_sleeves = len(pair_cols)
        book_daily = wide.select(pair_cols).to_numpy().sum(axis=1) / n_sleeves / 1e4  # bps -> fraction
        mean_d, std_d = book_daily.mean(), book_daily.std()
        sharpe = mean_d / std_d * np.sqrt(252) if std_d > 0 else float("nan")
        ann_return = mean_d * 252
        print(f"\n{label}: {len(book_daily)} trading days, {n_sleeves} sleeves")
        print(f"  daily mean={mean_d*1e4:+.4f}bps  daily std={std_d*1e4:.4f}bps")
        print(f"  annualized return={ann_return*100:+.3f}%  annualized Sharpe={sharpe:+.2f}")
        cum = np.cumprod(1 + book_daily)
        max_dd = np.min(cum / np.maximum.accumulate(cum) - 1)
        print(f"  max drawdown={max_dd*100:.2f}%  final cumulative return={100*(cum[-1]-1):+.2f}%")
        return book_daily

    print("\n=== UNFILTERED book (every flagged jump, equal-risk sleeves) ===")
    build_daily_book(oos, "unfiltered")

    print("\n=== META-MODEL FILTERED book (P>0.5 only) ===")
    filtered = oos.filter(pl.col("p_win") > 0.5)
    build_daily_book(filtered, "filtered")

    print("\n=== pairwise daily-return correlation across sleeves (filtered book) ===")
    daily_per_pair = (
        filtered.with_columns(pl.col("bucket").dt.date().alias("date"))
        .group_by(["date", "pair"]).agg(pl.col("net_bps").sum().alias("day_net_bps"))
    )
    wide = daily_per_pair.pivot(on="pair", index="date", values="day_net_bps").sort("date").fill_null(0.0)
    pair_cols = [c for c in wide.columns if c != "date"]
    corr = wide.select(pair_cols).to_pandas().corr()
    print(corr.round(2).to_string())
    off_diag = corr.to_numpy()[~np.eye(len(pair_cols), dtype=bool)]
    print(f"\nmean pairwise correlation: {off_diag.mean():+.3f}  max: {off_diag.max():+.3f}")


if __name__ == "__main__":
    main()
