"""Probe: WHY did HDBSCAN return only 2 clusters with zero noise?

Fits UMAP once at 8-D and once at 2-D on the train features, then sweeps HDBSCAN
cluster_selection_method (eom vs leaf) x min_cluster_size, reporting cluster count
and noise %. Also characterises what the default-config 2 clusters separate (the
features whose per-cluster means differ most). Run:

    uv run python -m scripts.fx_cluster.cluster_param_probe
"""

from __future__ import annotations

import hdbscan
import numpy as np
import polars as pl
import umap

from scripts.fx_cluster import config
from scripts.fx_cluster.bars import load_bars
from scripts.fx_cluster.killtest import _feature_cols, _finite_rows, assemble_points


def _summary(labels: np.ndarray) -> str:
    uniq, counts = np.unique(labels, return_counts=True)
    n_noise = int(counts[uniq == -1].sum()) if (uniq == -1).any() else 0
    n_clusters = int((uniq != -1).sum())
    biggest = sorted((c for u, c in zip(uniq, counts) if u != -1), reverse=True)[:5]
    return (f"clusters={n_clusters:>4}  noise={100*n_noise/len(labels):5.1f}%  "
            f"top5_sizes={biggest}")


def main() -> None:
    bars = {p: load_bars(p) for p in config.POOL_PAIRS}
    pts = assemble_points(bars)
    fcols = _feature_cols(pts)
    pts = _finite_rows(pts, fcols)
    train = pts.filter((pl.col("bucket") >= config.TRAIN_START) & (pl.col("bucket") < config.TRAIN_END))
    X = train.select(fcols).to_numpy()
    print(f"train rows={X.shape[0]} features={X.shape[1]}")

    print("\nfitting UMAP 8-D (current config) ...")
    z8 = umap.UMAP(n_components=8, n_neighbors=config.UMAP_N_NEIGHBORS,
                   min_dist=config.UMAP_MIN_DIST, random_state=config.RANDOM_SEED).fit_transform(X)
    print("fitting UMAP 2-D ...")
    z2 = umap.UMAP(n_components=2, n_neighbors=config.UMAP_N_NEIGHBORS,
                   min_dist=config.UMAP_MIN_DIST, random_state=config.RANDOM_SEED).fit_transform(X)

    embeds = {"8D": z8, "2D": z2, "raw15D": X}
    for mcs in (400, 100, 30):
        for method in ("eom", "leaf"):
            for name, Z in embeds.items():
                lab = hdbscan.HDBSCAN(min_cluster_size=mcs, min_samples=config.HDBSCAN_MIN_SAMPLES,
                                      cluster_selection_method=method).fit_predict(Z)
                print(f"  mcs={mcs:>3} {method:>4} {name:>6}: {_summary(lab)}")

    # characterise the default (8D, eom, mcs=400) 2-cluster split
    print("\nwhat do the default 2 clusters separate? (per-cluster z-feature means)")
    lab = hdbscan.HDBSCAN(min_cluster_size=400, min_samples=config.HDBSCAN_MIN_SAMPLES,
                          cluster_selection_method="eom").fit_predict(z8)
    tdf = train.with_columns(pl.Series("cl", lab))
    for cl in sorted(set(lab) - {-1}):
        sub = tdf.filter(pl.col("cl") == cl)
        means = {c: round(float(sub[c].mean()), 2) for c in fcols}
        top = sorted(means.items(), key=lambda kv: -abs(kv[1]))[:5]
        print(f"  cl{cl} n={sub.height}: dominant features {top}")


if __name__ == "__main__":
    main()
