"""Can the ideas from the conversation (USD-factor commonality, session split, CUSUM)
improve on the plain AUDUSD jump-fade-120min signal (the one survivor after real-cost WFO)?

Three conditioning filters, each testing one of the discussed ideas, on top of the same
fixed rule (fade Lee-Mykland-flagged jumps, z>4, over 120min / 24x5m bars):

  1. USD-factor commonality -- split each AUDUSD jump into how much of the move is
     explained by a broad-USD proxy (built from the other 5 majors, USD-leg-adjusted)
     vs AUD-idiosyncratic. Hypothesis: idiosyncratic (AUD-specific liquidity/flow) jumps
     mean-revert more cleanly than broad-USD-driven jumps (which may be information, not
     noise, and shouldn't be faded as hard).
  2. Half-hour session bucket -- does restricting to the highest-jump-rate session hours
     improve hit quality, or is it uniform across the day.
  3. CUSUM alignment -- does it matter whether the jump occurs WITH the prevailing CUSUM
     trend (breakout/continuation regime) vs AGAINST it (exhaustion/climax regime)?

Real Pepperstone Razor cost throughout (0.1pip AUDUSD spread + 0.60bps commission = 0.744bps RT,
same as cusum_jump_fade_wfo.py). Reports full-sample + half-split for each cut, same causal-
stability bar as before. This is now three additional cuts on the same in-sample data on top
of the pair/horizon search already done -- multiplicity is compounding, flagged explicitly at
the end, not swept under the rug.
"""

from __future__ import annotations

import numpy as np
import polars as pl

from scripts.fx_coint.eurusd_cusum_probe import add_features, load_5m

H = 24  # 120min
COST_BPS = 0.744  # AUDUSD real Razor cost (0.1pip + 0.60bps commission), from cusum_jump_fade_wfo.py
OTHER_MAJORS = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD"]
# sign so that +1 = "this pair's return reflects USD strengthening"
USD_SIGN = {"EURUSD": -1, "GBPUSD": -1, "USDJPY": +1, "USDCHF": +1, "USDCAD": +1}


def fade_stats(fwd: np.ndarray, ret_sign: np.ndarray) -> tuple[float, float, float, int]:
    fade = fwd * ret_sign * -1
    n = len(fade)
    if n < 20:
        return float("nan"), float("nan"), float("nan"), n
    gross_bps = float(fade.mean()) * 1e4
    net_bps = gross_bps - COST_BPS
    se = fade.std() / np.sqrt(n)
    t = float(fade.mean() / se) if se > 0 else float("nan")
    return gross_bps, net_bps, t, n


def report_split(valid: pl.DataFrame, label_col: str, labels: list) -> None:
    for lab in labels:
        sub = valid.filter(pl.col(label_col) == lab)
        fwd = sub[f"fwd_{H}"].to_numpy()
        sgn = sub["ret"].sign().to_numpy()
        gross, net, t, n = fade_stats(fwd, sgn)
        mid = len(sub) // 2
        sub_sorted = sub.sort("bucket")
        first = sub_sorted.head(mid)
        second = sub_sorted.tail(len(sub_sorted) - mid)
        _, net1, t1, n1 = fade_stats(first[f"fwd_{H}"].to_numpy(), first["ret"].sign().to_numpy())
        _, net2, t2, n2 = fade_stats(second[f"fwd_{H}"].to_numpy(), second["ret"].sign().to_numpy())
        print(f"  {label_col}={lab!r:20s} n={n:5d}  gross={gross:+7.3f}  net={net:+7.3f}  t={t:+6.2f}"
              f"   | half1 net={net1:+6.3f}(t{t1:+.2f},n{n1})  half2 net={net2:+6.3f}(t{t2:+.2f},n{n2})")


def build_usd_proxy() -> pl.DataFrame:
    frames = []
    for sym in OTHER_MAJORS:
        d5 = load_5m(sym).with_columns((pl.col("mid").log().diff() * USD_SIGN[sym]).alias(f"usdret_{sym}"))
        frames.append(d5.select("bucket", f"usdret_{sym}"))
    out = frames[0]
    for f in frames[1:]:
        out = out.join(f, on="bucket", how="inner")
    ret_cols = [f"usdret_{s}" for s in OTHER_MAJORS]
    out = out.with_columns(pl.mean_horizontal(ret_cols).alias("usd_proxy_ret"))
    return out.select("bucket", "usd_proxy_ret")


def session_check(symbol: str, cost_bps: float) -> None:
    """Independent check: does restricting to the top-third active-session hours
    (derived from THIS symbol's own jump frequency, not borrowed from AUDUSD) help
    a pair that either decayed (GBPUSD) or was flat (EURUSD) on the plain rule?"""
    global COST_BPS
    saved = COST_BPS
    COST_BPS = cost_bps
    df = load_5m(symbol)
    df = add_features(df)
    valid = df.filter(
        pl.col("bp_sigma").is_not_null() & pl.col("is_jump") & pl.col(f"fwd_{H}").is_not_null()
    ).with_columns(
        (pl.col("bucket").dt.hour() * 2 + (pl.col("bucket").dt.minute() >= 30).cast(pl.Int32)).alias("hh")
    )
    counts = valid.group_by("hh").agg(pl.len().alias("cnt")).sort("cnt", descending=True)
    top_hh = set(counts.head(16)["hh"].to_list())
    valid = valid.with_columns(pl.col("hh").is_in(top_hh).alias("is_top_session"))
    print(f"\n=== {symbol}: independent session-filter check (cost={cost_bps:.3f}bps) ===")
    print("  baseline (all hours):")
    fwd = valid[f"fwd_{H}"].to_numpy()
    sgn = valid["ret"].sign().to_numpy()
    gross, net, t, n = fade_stats(fwd, sgn)
    print(f"    n={n}  gross={gross:+.3f}  net={net:+.3f}  t={t:+.2f}")
    report_split(valid, "is_top_session", [True, False])
    COST_BPS = saved


def trend_check(symbol: str, cost_bps: float) -> None:
    """Independent check: does the with-trend/against-trend CUSUM-alignment split
    (sign of jump z vs sign of trailing 12-bar mean z) hold up on another pair?"""
    global COST_BPS
    saved = COST_BPS
    COST_BPS = cost_bps
    df = load_5m(symbol)
    df = add_features(df)
    v3 = df.sort("bucket").with_columns(
        pl.col("z").shift(1).rolling_mean(window_size=12, min_samples=6).alias("trend_z")
    )
    v3 = v3.filter(pl.col("bp_sigma").is_not_null() & pl.col("is_jump") & pl.col(f"fwd_{H}").is_not_null())
    v3 = v3.with_columns((pl.col("z").sign() == pl.col("trend_z").sign()).alias("jump_with_trend"))
    print(f"\n=== {symbol}: independent CUSUM/trend-alignment check (cost={cost_bps:.3f}bps) ===")
    print("  baseline (all jumps):")
    fwd = v3[f"fwd_{H}"].to_numpy()
    sgn = v3["ret"].sign().to_numpy()
    gross, net, t, n = fade_stats(fwd, sgn)
    print(f"    n={n}  gross={gross:+.3f}  net={net:+.3f}  t={t:+.2f}")
    report_split(v3, "jump_with_trend", [True, False])
    COST_BPS = saved


def main() -> None:
    df = load_5m("AUDUSD")
    df = add_features(df)
    valid = df.filter(
        pl.col("bp_sigma").is_not_null() & pl.col("is_jump") & pl.col(f"fwd_{H}").is_not_null()
    )
    print(f"total AUDUSD jump bars: {valid.height}")

    print("\n--- baseline (no conditioning) ---")
    fwd = valid[f"fwd_{H}"].to_numpy()
    sgn = valid["ret"].sign().to_numpy()
    gross, net, t, n = fade_stats(fwd, sgn)
    print(f"  n={n}  gross={gross:+.3f}  net={net:+.3f}  t={t:+.2f}")

    # --- 1. USD-factor commonality ---
    usd = build_usd_proxy()
    v1 = valid.join(usd, on="bucket", how="inner")
    # predicted AUDUSD move from broad USD factor: AUDUSD is itself -USD_sign convention
    # (AUDUSD up = USD weak), so predicted_from_usd = -usd_proxy_ret
    v1 = v1.with_columns((-pl.col("usd_proxy_ret")).alias("common_component"))
    v1 = v1.with_columns((pl.col("ret") - pl.col("common_component")).alias("idio_component"))
    v1 = v1.with_columns(
        (pl.col("common_component").abs() > pl.col("idio_component").abs()).alias("is_common_driven")
    )
    print("\n--- 1. USD-factor commonality: is the jump mostly common-USD-driven or AUD-idiosyncratic? ---")
    report_split(v1, "is_common_driven", [True, False])

    # --- 2. session bucket: best vs rest ---
    v2 = valid.with_columns(
        (pl.col("bucket").dt.hour() * 2 + (pl.col("bucket").dt.minute() >= 30).cast(pl.Int32)).alias("hh")
    )
    # rank buckets by jump count as a proxy for "active" session hours (top third vs rest)
    counts = v2.group_by("hh").agg(pl.len().alias("cnt")).sort("cnt", descending=True)
    top_hh = set(counts.head(16)["hh"].to_list())  # top third of 48 buckets by jump frequency
    v2 = v2.with_columns(pl.col("hh").is_in(top_hh).alias("is_top_session"))
    print("\n--- 2. session bucket: top-third-by-jump-frequency hours vs rest ---")
    report_split(v2, "is_top_session", [True, False])

    # --- 3. CUSUM alignment: jump WITH prevailing trend vs AGAINST it (climax) ---
    # cusum_mag as stored is max(s_pos, -s_neg) i.e. always >=0; need signed cusum to know direction.
    # Recompute signed cusum state at the jump bar's position using s_pos - (-s_neg) proxy via sign of z's
    # recent run: use sign of the mean of the preceding 12 bars' z as "prevailing trend" direction.
    # trailing 12-bar mean z (causal, excludes current bar) computed via polars rolling
    v3 = valid.sort("bucket").with_columns(
        pl.col("z").shift(1).rolling_mean(window_size=12, min_samples=6).alias("trend_z")
    )
    v3 = v3.filter(pl.col("bp_sigma").is_not_null() & pl.col("is_jump") & pl.col(f"fwd_{H}").is_not_null())
    v3 = v3.with_columns((pl.col("z").sign() == pl.col("trend_z").sign()).alias("jump_with_trend"))
    print("\n--- 3. CUSUM/trend alignment: jump WITH prevailing 12-bar trend vs AGAINST it (climax) ---")
    report_split(v3, "jump_with_trend", [True, False])

    print("\n[caveat: 3 additional cuts tried on the same in-sample AUDUSD data on top of the "
          "5-pair x 3-horizon search already done -- treat any cell here as a lead requiring "
          "independent confirmation (different symbol/period), not a finding]")

    session_check("GBPUSD", cost_bps=0.755)
    session_check("EURUSD", cost_bps=0.689)
    trend_check("GBPUSD", cost_bps=0.755)
    trend_check("EURUSD", cost_bps=0.689)


if __name__ == "__main__":
    main()
