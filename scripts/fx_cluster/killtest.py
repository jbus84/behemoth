"""Kill-test orchestrator (spec section 6.1): single causal split, train-only fit,
OOS assignment, simulate selected clusters, write the GO/NO-GO report."""

from __future__ import annotations

import numpy as np
import polars as pl

from scripts.fx_cluster import config
from scripts.fx_cluster.bars import load_bars
from scripts.fx_cluster.cluster import Clusterer
from scripts.fx_cluster.embed import Embedder
from scripts.fx_cluster.features import build_features
from scripts.fx_cluster.labels import build_labels
from scripts.fx_cluster.score import score_clusters, select_clusters


def add_block_index(df: pl.DataFrame, block_days: int = config.BLOCK_DAYS) -> pl.DataFrame:
    """0-based time-block index (block_days-day blocks from the first bucket)."""
    epoch_day = pl.col("bucket").dt.epoch(time_unit="s") // 86400
    return df.with_columns(
        ((epoch_day - epoch_day.min()) // block_days).cast(pl.Int64).alias("block")
    )


def assemble_points(bars: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """Join the causal feature matrix to the triple-barrier labels on (pair, bucket)."""
    feats, _names = build_features(bars)
    label_frames = []
    for p, b in bars.items():
        lab = build_labels(b.sort("bucket")).select(
            "bucket", "ret_long", "ret_short", "mfe", "mae", "hold_bars"
        ).with_columns(pl.lit(p).alias("pair"))
        label_frames.append(lab)
    labels = pl.concat(label_frames)
    pts = feats.join(labels, on=["pair", "bucket"], how="inner")
    return add_block_index(pts)


def _feature_cols(pts: pl.DataFrame) -> list[str]:
    drop = {"pair", "bucket", "block", "ret_long", "ret_short", "mfe", "mae", "hold_bars"}
    return [c for c in pts.columns if c not in drop]


def _finite_rows(pts: pl.DataFrame, cols: list[str]) -> pl.DataFrame:
    """Keep only rows whose feature columns are all finite (UMAP cannot take NaN/inf)."""
    return pts.filter(pl.all_horizontal([pl.col(c).is_finite() for c in cols]))


def run(write_report: bool = True) -> list[dict]:
    bars = {p: load_bars(p) for p in config.POOL_PAIRS}
    pts = assemble_points(bars)
    fcols = _feature_cols(pts)
    pts = _finite_rows(pts, fcols)

    train = pts.filter((pl.col("bucket") >= config.TRAIN_START) & (pl.col("bucket") < config.TRAIN_END))
    test = pts.filter((pl.col("bucket") >= config.TEST_START) & (pl.col("bucket") < config.TEST_END))

    emb = Embedder().fit(train.select(fcols).to_numpy())
    clu = Clusterer().fit(emb.transform(train.select(fcols).to_numpy()))

    train_scored = train.with_columns(pl.Series("cluster", clu.labels_))
    report = score_clusters(train_scored, cost_bps=config.COMMISSION_BPS_RT)
    selection = select_clusters(report)

    test_labels, _strengths = clu.predict(emb.transform(test.select(fcols).to_numpy()))
    test_scored = test.with_columns(pl.Series("cluster", test_labels))

    oos = []
    for sel in selection:
        sub = test_scored.filter(pl.col("cluster") == sel["cluster"])
        col = "ret_long" if sel["side"] == 1 else "ret_short"
        finite = sub.filter(pl.col(col).is_finite())
        rets = finite[col].to_numpy()
        if len(rets) == 0:
            continue
        per_year = (
            finite.with_columns(pl.col("bucket").dt.year().alias("yr"))
            .group_by("yr").agg(pl.col(col).mean().alias("m"))
        )
        oos.append({
            "cluster": int(sel["cluster"]), "side": int(sel["side"]), "n_oos": len(rets),
            "oos_mean_net": float(np.mean(rets)), "oos_win": float((rets > 0).mean()),
            "pos_years": int((per_year["m"] > 0).sum()), "n_years": per_year.height,
        })

    if write_report:
        _write_report(report, selection, oos)
    return oos


def _write_report(report: list[dict], selection: list[dict], oos: list[dict]) -> None:
    lines = ["# FX Cluster Kill-Test Report", ""]
    lines.append(f"Pool pairs: {', '.join(config.POOL_PAIRS)} (USDJPY held out).")
    lines.append(f"Train {config.TRAIN_START:%Y-%m} .. {config.TRAIN_END:%Y-%m}, "
                 f"Test {config.TEST_START:%Y-%m} .. {config.TEST_END:%Y-%m}.")
    lines.append(f"Cost floor ~{config.COMMISSION_BPS_RT} bps commission + crossed spread.")
    lines.append("")
    lines.append(f"Train clusters scored: {len(report)}; selected: {len(selection)}.")
    lines.append("")
    lines.append("## OOS performance of selected clusters")
    lines.append("")
    lines.append("| cluster | side | n_oos | oos_mean_net (bps) | win | pos_years/total |")
    lines.append("|---|---|---|---|---|---|")
    for o in oos:
        lines.append(f"| {o['cluster']} | {o['side']} | {o['n_oos']} | "
                     f"{o['oos_mean_net']:.3f} | {o['oos_win']:.2f} | {o['pos_years']}/{o['n_years']} |")
    survivors = [o for o in oos if o["oos_mean_net"] > config.SELECT_MARGIN_BPS
                 and o["pos_years"] >= max(1, o["n_years"] - 1)]
    verdict = "GO" if survivors else "NO_GO"
    lines += ["", f"## Verdict: {verdict}", ""]
    if survivors:
        lines.append(f"{len(survivors)} cluster(s) clear cost with margin and are stable OOS.")
    else:
        lines.append("No cluster shows an OOS-stable, cost-net edge. Cheap NO_GO.")
    with open(config.REPORT_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")


def main() -> None:
    oos = run(write_report=True)
    print(f"Selected clusters survived OOS check: {len(oos)}; report -> {config.REPORT_PATH}")


if __name__ == "__main__":
    main()
