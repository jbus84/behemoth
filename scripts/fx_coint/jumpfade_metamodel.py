"""Meta-labeling on the hardened idiosyncratic-jump-fade core (11 pairs that survived
real-cost verification + full-search multiplicity correction, see
project_fx_idiosyncratic_jump_fade memory).

Rule sets the side (fade the flagged LM jump, unchanged). This layer's job is ONLY to
learn which flagged jumps are worth taking -- same pattern as project_fx_metalabeling.py
(rule=side, ML=filter/size), the one place ML has already added value in this project.

Features per event (all known before the trade): |z| jump magnitude, idio_share
(continuous 0-1, replaces the earlier hard idiosyncratic/common threshold), pair
(categorical), hour of day, day of week, local diurnal vol level.

Target: net fade return > 0 (binary).

Validation: purged expanding-window walk-forward by calendar year, pooled across all
11 pairs. Train on years < Y, predict on year Y only, compare filtered (P>0.5) vs
unfiltered net bps/t-stat on the SAME held-out year. No pair/year is ever in both train
and test.
"""

from __future__ import annotations

import numpy as np
import polars as pl
from catboost import CatBoostClassifier

from scripts.fx_coint.eurusd_cusum_probe import add_features, load_5m

H = 24
USD_MAJORS = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD"]
USD_SIGN = {"EURUSD": -1, "GBPUSD": -1, "AUDUSD": -1, "NZDUSD": -1, "USDJPY": +1, "USDCHF": +1, "USDCAD": +1}

CROSS_LEGS = {
    # AUDCAD = AUDUSD * USDCAD (AUD-in-USD times USD-in-CAD), so both legs are +1 --
    # this was previously miscoded as -1 on USDCAD (found in a 2026-07-07 red-team
    # pass); AUDCAD is UNCONDITIONED_VALIDATED so the bug never affected which trades
    # were included, only corrupted the idio_share FEATURE value fed to the model for
    # AUDCAD's rows.
    "AUDCAD": [("AUDUSD", +1), ("USDCAD", +1)],
    "AUDNZD": [("AUDUSD", +1), ("NZDUSD", -1)],
    "GBPJPY": [("GBPUSD", +1), ("USDJPY", +1)],
    "CHFJPY": [("USDCHF", -1), ("USDJPY", +1)],
    "GBPAUD": [("GBPUSD", +1), ("AUDUSD", -1)],
    "EURJPY": [("EURUSD", +1), ("USDJPY", +1)],
}

# real / best-available cost per pair, bps RT (see memory for sourcing)
COST_BPS = {
    "EURUSD": 0.689, "GBPUSD": 0.755, "USDCHF": 1.031, "AUDUSD": 0.744,
    "AUDCAD": 1.361, "AUDNZD": 1.803, "NZDUSD": 1.07,
    "GBPJPY": 0.77, "CHFJPY": 0.79, "GBPAUD": 1.15, "EURJPY": 0.92,
}
CORE_PAIRS = list(COST_BPS)
JPY_PAIRS = {"GBPJPY", "CHFJPY", "EURJPY"}

# pairs whose standalone validation was on the FULL unconditioned population (no
# idio-split needed -- their raw jump population already showed the edge broadly)
UNCONDITIONED_VALIDATED = {"AUDCAD", "AUDNZD", "NZDUSD"}
# everyone else was validated specifically on the idio_share>0.5 subset -- the
# meta-model must be pre-restricted to that population, not asked to rediscover the
# hard filter itself from the full (mostly common-driven, no-edge) population


def usd_proxy_for(target: str) -> pl.DataFrame:
    others = [m for m in USD_MAJORS if m != target]
    frames = []
    for sym in others:
        d5 = load_5m(sym).with_columns((pl.col("mid").log().diff() * USD_SIGN[sym]).alias(f"u_{sym}"))
        frames.append(d5.select("bucket", f"u_{sym}"))
    out = frames[0]
    for f in frames[1:]:
        out = out.join(f, on="bucket", how="inner")
    return out.with_columns(pl.mean_horizontal([f"u_{s}" for s in others]).alias("common_proxy"))


def leg_proxy_for(legs: list[tuple[str, int]]) -> pl.DataFrame:
    frames = []
    for sym, sign in legs:
        d5 = load_5m(sym).with_columns((pl.col("mid").log().diff() * sign).alias(f"l_{sym}"))
        frames.append(d5.select("bucket", f"l_{sym}"))
    out = frames[0].join(frames[1], on="bucket", how="inner")
    cols = [f"l_{sym}" for sym, _ in legs]
    return out.with_columns(pl.sum_horizontal(cols).alias("common_proxy"))


def build_pair(sym: str) -> pl.DataFrame:
    df = load_5m(sym)
    df = add_features(df)
    valid = df.filter(pl.col("bp_sigma").is_not_null() & pl.col("is_jump") & pl.col(f"fwd_{H}").is_not_null())

    if sym in USD_MAJORS:
        proxy = usd_proxy_for(sym)
        sign = USD_SIGN[sym]
        v = valid.join(proxy.select("bucket", "common_proxy"), on="bucket", how="inner")
        v = v.with_columns((sign * pl.col("common_proxy")).alias("common"))
    else:
        proxy = leg_proxy_for(CROSS_LEGS[sym])
        v = valid.join(proxy.select("bucket", "common_proxy"), on="bucket", how="inner")
        v = v.with_columns(pl.col("common_proxy").alias("common"))

    v = v.with_columns((pl.col("ret") - pl.col("common")).alias("idio"))
    v = v.with_columns(
        (pl.col("idio").abs() / (pl.col("idio").abs() + pl.col("common").abs() + 1e-12)).alias("idio_share")
    )
    cost = COST_BPS[sym]
    v = v.with_columns(
        (pl.col(f"fwd_{H}") * pl.col("ret").sign() * -1 * 1e4 - cost).alias("net_bps"),
        pl.col("lm_z").abs().alias("abs_z"),
        pl.col("bucket").dt.hour().alias("hour"),
        pl.col("bucket").dt.weekday().alias("dow"),
        pl.col("bucket").dt.year().alias("year"),
        pl.lit(sym).alias("pair"),
    )
    v = v.with_columns((pl.col("net_bps") > 0).alias("win"))
    if sym not in UNCONDITIONED_VALIDATED:
        v = v.filter(pl.col("idio_share") > 0.5)
    return v.select("bucket", "pair", "year", "hour", "dow", "abs_z", "idio_share", "diurnal_scale", "net_bps", "win")


def main() -> None:
    print("Building pooled feature set across 11 hardened pairs...")
    frames = [build_pair(sym) for sym in CORE_PAIRS]
    pooled = pl.concat(frames).sort("bucket")
    print(f"pooled n={pooled.height}")
    for sym in CORE_PAIRS:
        print(f"  {sym:8s} n={pooled.filter(pl.col('pair')==sym).height}")

    years = sorted(pooled["year"].unique().to_list())
    test_years = years[3:]  # first 3 years = minimum training burn-in
    import sys
    feat_cols = ["abs_z", "idio_share", "diurnal_scale"] if "--no-hour" in sys.argv else ["abs_z", "idio_share", "diurnal_scale", "hour", "dow"]

    all_unfiltered, all_filtered = [], []
    print("\n-- purged expanding-window walk-forward, year by year --")
    for test_y in test_years:
        train = pooled.filter(pl.col("year") < test_y)
        test = pooled.filter(pl.col("year") == test_y)
        if train.height < 500 or test.height < 50:
            continue

        X_train = train.select(feat_cols + ["pair"]).to_pandas()
        y_train = train["win"].to_numpy().astype(int)
        X_test = test.select(feat_cols + ["pair"]).to_pandas()

        model = CatBoostClassifier(
            iterations=200, depth=4, learning_rate=0.05, cat_features=["pair"],
            verbose=False, random_seed=42,
        )
        model.fit(X_train, y_train)
        p_win = model.predict_proba(X_test)[:, 1]

        net_all = test["net_bps"].to_numpy()
        net_filtered = net_all[p_win > 0.5]
        all_unfiltered.append(net_all)
        all_filtered.append(net_filtered)

        m_all, n_all = net_all.mean(), len(net_all)
        m_filt, n_filt = (net_filtered.mean() if len(net_filtered) else float("nan")), len(net_filtered)
        print(f"  {test_y}  unfiltered n={n_all:5d} net={m_all:+.3f}bps  |  "
              f"P>0.5 filtered n={n_filt:5d} ({100*n_filt/max(n_all,1):.0f}%) net={m_filt:+.3f}bps")

    all_unf = np.concatenate(all_unfiltered)
    all_filt = np.concatenate([a for a in all_filtered if len(a)])
    t_unf = all_unf.mean() / (all_unf.std() / np.sqrt(len(all_unf)))
    t_filt = all_filt.mean() / (all_filt.std() / np.sqrt(len(all_filt))) if len(all_filt) else float("nan")
    print("\nTOTAL OOS (all test years pooled):")
    print(f"  unfiltered      n={len(all_unf):6d}  net={all_unf.mean():+.3f}bps  t={t_unf:+.2f}")
    print(f"  P>0.5 filtered  n={len(all_filt):6d}  net={all_filt.mean():+.3f}bps  t={t_filt:+.2f}")

    # feature importance from the LAST fold's model, for a qualitative read
    print("\nFeature importance (last fold's model):")
    for name, imp in sorted(zip(feat_cols + ["pair"], model.get_feature_importance()), key=lambda x: -x[1]):
        print(f"  {name:14s} {imp:6.2f}")


if __name__ == "__main__":
    main()
