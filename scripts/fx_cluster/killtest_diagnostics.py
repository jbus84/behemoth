"""Diagnostics for the kill-test: characterise WHY the verdict landed where it did.

Mirrors killtest.run() but prints the decomposition the thin report can't: train/test
sizes, the full train cluster-label distribution (incl. noise), each train cluster's
both-side stats and the selection gate it failed, and the OOS behaviour of EVERY
non-noise train cluster (not just the selected ones). Run as a module:

    uv run python -m scripts.fx_cluster.killtest_diagnostics
"""

from __future__ import annotations

import numpy as np
import polars as pl

from scripts.fx_cluster import config
from scripts.fx_cluster.bars import load_bars
from scripts.fx_cluster.cluster import Clusterer
from scripts.fx_cluster.embed import Embedder
from scripts.fx_cluster.killtest import _feature_cols, _finite_rows, assemble_points
from scripts.fx_cluster.score import score_clusters


def main() -> None:
    bars = {p: load_bars(p) for p in config.POOL_PAIRS}
    pts = assemble_points(bars)
    fcols = _feature_cols(pts)
    pts = _finite_rows(pts, fcols)

    train = pts.filter((pl.col("bucket") >= config.TRAIN_START) & (pl.col("bucket") < config.TRAIN_END))
    test = pts.filter((pl.col("bucket") >= config.TEST_START) & (pl.col("bucket") < config.TEST_END))
    print(f"features: {len(fcols)}  {fcols}")
    print(f"train rows: {train.height}  test rows: {test.height}")

    emb = Embedder().fit(train.select(fcols).to_numpy())
    clu = Clusterer().fit(emb.transform(train.select(fcols).to_numpy()))
    labels = clu.labels_

    uniq, counts = np.unique(labels, return_counts=True)
    print("\ntrain cluster label distribution (label: n, %):")
    for lab, n in zip(uniq, counts):
        tag = "NOISE" if lab == -1 else f"cl{lab}"
        print(f"  {tag:>7}: {n:>7}  {100*n/len(labels):5.1f}%")
    n_real = int((uniq != -1).sum())
    print(f"non-noise clusters: {n_real}  (min_cluster_size={config.HDBSCAN_MIN_CLUSTER_SIZE}, "
          f"min_samples={config.HDBSCAN_MIN_SAMPLES})")

    train_scored = train.with_columns(pl.Series("cluster", labels))
    report = score_clusters(train_scored, cost_bps=config.COMMISSION_BPS_RT)

    test_labels, _ = clu.predict(emb.transform(test.select(fcols).to_numpy()))
    test_scored = test.with_columns(pl.Series("cluster", test_labels))

    # aggregate decomposition across all scored clusters
    n_pos_train = sum(1 for r in report if r["mean_net"] > 0)
    n_persist = sum(1 for r in report if r["mfe_mae"] >= config.PERSIST_MIN_MFE_MAE)
    best_p = min((r["pvalue"] for r in report), default=float("nan"))
    mfe_lo = min((r["mfe_mae"] for r in report), default=float("nan"))
    mfe_hi = max((r["mfe_mae"] for r in report), default=float("nan"))
    print("\nAGGREGATE over scored clusters:")
    print(f"  scored={len(report)}  train_net>0: {n_pos_train}  "
          f"pass_persistence(mfe/mae>={config.PERSIST_MIN_MFE_MAE}): {n_persist}  "
          f"best_boot_p={best_p:.3f}  mfe/mae range=[{mfe_lo:.2f},{mfe_hi:.2f}]")

    print("\nper train cluster — selection gate + OOS:")
    print(f"  margin>{config.SELECT_MARGIN_BPS}bps, mfe/mae>={config.PERSIST_MIN_MFE_MAE}, "
          f"hold>={config.PERSIST_MIN_HOLD_BARS}, FDR alpha={config.FDR_ALPHA}")
    for r in report:
        gate = []
        if not r["mean_net"] > config.SELECT_MARGIN_BPS:
            gate.append("FAIL margin")
        if not r["mfe_mae"] >= config.PERSIST_MIN_MFE_MAE:
            gate.append("FAIL persist(mfe/mae)")
        if not r["median_hold"] >= config.PERSIST_MIN_HOLD_BARS:
            gate.append("FAIL persist(hold)")
        gatestr = ", ".join(gate) if gate else "PASS pre-FDR"
        cl = r["cluster"]
        sub = test_scored.filter(pl.col("cluster") == cl)
        col = "ret_long" if r["side"] == 1 else "ret_short"
        fin = sub.filter(pl.col(col).is_finite())
        oos_mean = float(fin[col].mean()) if fin.height else float("nan")
        oos_win = float((fin[col] > 0).mean()) if fin.height else float("nan")
        print(
            f"  cl{cl} side{r['side']:+d} n={r['n']:>6} "
            f"train_net={r['mean_net']:+.3f} win={r['win_rate']:.2f} p={r['pvalue']:.3f} "
            f"mfe/mae={r['mfe_mae']:.2f} hold={r['median_hold']:.0f} | {gatestr} "
            f"|| OOS n={fin.height:>5} net={oos_mean:+.3f} win={oos_win:.2f}"
        )


if __name__ == "__main__":
    main()
