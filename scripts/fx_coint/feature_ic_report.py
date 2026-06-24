"""Build the complete report (plots + markdown) for the definitive feature-IC
study. Reads the records CSV produced by feature_ic_definitive.py and writes
plots + REPORT.md into reports/feature_ic_definitive/.

Separated from the (slow) study so the report can be regenerated cheaply.

Usage:
  uv run python scripts/fx_coint/feature_ic_definitive.py   # produces ic_records.csv
  uv run python scripts/fx_coint/feature_ic_report.py        # produces plots + REPORT.md
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

OUT = Path("reports/feature_ic_definitive")
TOP_K = 10  # features to draw on the line plots (by max |partial_ic| across N)


def _line(df, value, title, fname, feats):
    fig, ax = plt.subplots(figsize=(9, 5.5))
    for f in feats:
        sub = df[df.feature == f].sort_values("N")
        ax.plot(sub["N"], sub[value], marker="o", label=f, linewidth=1.6)
    ax.axhline(0, color="k", linewidth=0.8, alpha=0.6)
    ax.set_xscale("log")
    ax.set_xticks(sorted(df["N"].unique()))
    ax.get_xaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
    ax.set_xlabel("triple-barrier window N (bars, log scale)")
    ax.set_ylabel(value)
    ax.set_title(title)
    ax.legend(fontsize=8, ncol=2)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / fname, dpi=110)
    plt.close(fig)


def _heatmap(mat, title, fname, cmap, center_zero=True):
    fig, ax = plt.subplots(figsize=(8, 0.34 * len(mat) + 1.5))
    vmax = np.nanmax(np.abs(mat.to_numpy())) if center_zero else np.nanmax(mat.to_numpy())
    vmin = -vmax if center_zero else 0
    im = ax.imshow(mat.to_numpy(), aspect="auto", cmap=cmap, vmin=vmin, vmax=vmax)
    ax.set_xticks(range(len(mat.columns)))
    ax.set_xticklabels(mat.columns)
    ax.set_yticks(range(len(mat.index)))
    ax.set_yticklabels(mat.index, fontsize=8)
    ax.set_xlabel("N")
    ax.set_title(title)
    fig.colorbar(im, ax=ax, fraction=0.025)
    fig.tight_layout()
    fig.savefig(OUT / fname, dpi=110)
    plt.close(fig)


def _bar(counts, fname):
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar([str(n) for n in counts.index], counts.to_numpy(), color="steelblue")
    for x, v in enumerate(counts.to_numpy()):
        ax.text(x, v + 0.05, str(int(v)), ha="center", fontsize=9)
    ax.set_xlabel("N")
    ax.set_ylabel("# robust features")
    ax.set_title("Robust features per TB window (gate: sign>=4/5, non-overlap same sign, |partial|>0.004)")
    fig.tight_layout()
    fig.savefig(OUT / fname, dpi=110)
    plt.close(fig)


def _md_table(df, cols):
    head = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join("---" for _ in cols) + " |"
    rows = []
    for _, r in df.iterrows():
        cells = [f"{r[c]:.4f}" if isinstance(r[c], float) else str(r[c]) for c in cols]
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join([head, sep, *rows])


def main():
    res = pd.read_csv(OUT / "ic_records.csv")
    n_grid = sorted(res["N"].unique())
    top_feats = (res.groupby("feature")["partial_ic"].apply(lambda s: s.abs().max())
                 .sort_values(ascending=False).head(TOP_K).index.tolist())

    _line(res, "partial_ic", "Partial IC vs ffd_0.1, by TB window", "partial_ic_vs_N.png", top_feats)
    _line(res, "oos_ic", "OOS test IC (chrono 30% holdout), by TB window", "oos_ic_vs_N.png", top_feats)
    _line(res, "raw_ic", "Raw pooled IC, by TB window", "raw_ic_vs_N.png", top_feats)

    pmat = res.pivot(index="feature", columns="N", values="partial_ic")
    pmat = pmat.reindex(pmat.abs().max(axis=1).sort_values(ascending=False).index)
    _heatmap(pmat, "Partial IC (feature x N)", "partial_ic_heatmap.png", "RdBu_r")

    rmat = res.pivot(index="feature", columns="N", values="robust").reindex(pmat.index).astype(float)
    _heatmap(rmat, "Robust flag (feature x N)", "robust_heatmap.png", "Greens", center_zero=False)

    counts = res[res.robust].groupby("N")["feature"].count().reindex(n_grid).fillna(0)
    _bar(counts, "robust_count_vs_N.png")

    # markdown report
    lines = [
        "# Definitive Feature-IC Study — Report",
        "",
        "**Setup:** 1000-tick bars, pooled 5 ex-JPY majors, N-bar triple-barrier target "
        "(vol-scaled symmetric barriers `1.0*vol*sqrt(N)`), 40k events/symbol. "
        "Partial IC controls for `ffd_0.1`; sign = k/5 majors; OOS = chrono 30% holdout; "
        "non-overlap IC = every N-th event. Significance deliberately not reported (OOS is the arbiter).",
        "",
        "## Robust features per N",
        "",
        "![robust count](robust_count_vs_N.png)",
        "",
        "## IC vs window",
        "",
        "![partial IC](partial_ic_vs_N.png)",
        "",
        "![OOS IC](oos_ic_vs_N.png)",
        "",
        "![raw IC](raw_ic_vs_N.png)",
        "",
        "## Heatmaps",
        "",
        "![partial heatmap](partial_ic_heatmap.png)",
        "",
        "![robust heatmap](robust_heatmap.png)",
        "",
        "## Robustness gate by N",
        "",
    ]
    for n in n_grid:
        rN = res[(n == res.N) & res.robust].copy()
        rN = rN.reindex(rN.partial_ic.abs().sort_values(ascending=False).index)
        lines.append(f"### N = {n} — {len(rN)} robust")
        lines.append("")
        if len(rN):
            lines.append(_md_table(rN, ["feature", "raw_ic", "partial_ic", "oos_ic", "sign", "nov_ic"]))
        else:
            lines.append("_none_")
        lines.append("")
    (OUT / "REPORT.md").write_text("\n".join(lines) + "\n")
    print(f"report -> {OUT / 'REPORT.md'}")
    print("plots ->", ", ".join(sorted(p.name for p in OUT.glob("*.png"))))


if __name__ == "__main__":
    main()
