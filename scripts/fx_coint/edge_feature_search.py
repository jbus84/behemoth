"""Two-track edge-based feature search (Stage 1 screen).

Replaces IC as the search objective with edge-leaning statistics, after this
project established that IC robustness != tradeable P&L. Per role:
  direction : |return|-weighted directional IC (emphasises big-money events)
  magnitude : IC of feature vs |return| (rank move size -> select cost-clearers)
  condition : tercile net-bps spread of the base fade P&L (interaction value)
Survivors are confirmed by marginal net-bps lift in pnl_walkforward (Stage 2).

No modelling: all combinations are simple non-fit rules.

Usage: uv run python scripts/fx_coint/edge_feature_search.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))
from feature_ic_definitive import build_all  # noqa: E402
from triple_barrier import triple_barrier_core  # noqa: E402

POOL = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF"]
N_EVENTS = 40000
BASE = "ffd_0.1"          # ffd control kept for reference
SELECTOR = "ffd_zvol20"   # the fixed-base signal (direction + magnitude)
OUT_DIR = Path("reports/edge_feature_search")


def _finite_pair(a, b):
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    ok = np.isfinite(a) & np.isfinite(b)
    return a[ok], b[ok]


def weighted_directional_ic(feat: np.ndarray, ret: np.ndarray) -> float:
    """Weighted rank correlation of feat vs ret, weights ∝ |ret|.

    Uses weighted Pearson correlation of the rank-transformed series, so large
    moves (which dominate P&L) dominate the statistic. Returns 0.0 if degenerate.
    """
    f, r = _finite_pair(feat, ret)
    if f.size < 10:
        return 0.0
    w = np.abs(r)
    if w.sum() == 0:
        return 0.0
    fr = stats.rankdata(f)
    rr = stats.rankdata(r)

    def wmean(x):
        return np.sum(w * x) / np.sum(w)

    fm, rm = wmean(fr), wmean(rr)
    cov = wmean((fr - fm) * (rr - rm))
    vf = wmean((fr - fm) ** 2)
    vr = wmean((rr - rm) ** 2)
    den = np.sqrt(vf * vr)
    return float(cov / den) if den > 0 else 0.0


def magnitude_ic(feat: np.ndarray, ret: np.ndarray) -> float:
    """Spearman IC of feat vs |ret| — does the feature rank move size?"""
    f, r = _finite_pair(feat, ret)
    if f.size < 10 or np.unique(f).size < 3:
        return 0.0
    return float(stats.spearmanr(f, np.abs(r))[0])


def tercile_netbps_spread(base_pnl: np.ndarray, gate: np.ndarray) -> dict:
    """Net-bps spread of base P&L across terciles of `gate`. Judged in net-bps
    (cost cancels in the spread), not IC — the project's central lesson."""
    p = np.asarray(base_pnl, dtype=float)
    g = np.asarray(gate, dtype=float)
    ok = np.isfinite(p) & np.isfinite(g)
    p, g = p[ok], g[ok]
    if p.size < 30:
        return {"unc": float("nan"), "t_means": [float("nan")] * 3,
                "best_lift": float("nan"), "best_tercile": -1}
    unc = float(p.mean())
    q1, q2 = np.quantile(g, [1 / 3, 2 / 3])
    # Guard: if gate has no variance, q1 and q2 will be equal, making terciles
    # degenerate (all NaNs). Return the sentinel value.
    if np.isclose(q1, q2):
        return {"unc": unc, "t_means": [float("nan")] * 3,
                "best_lift": float("nan"), "best_tercile": -1}
    masks = [g <= q1, (g > q1) & (g <= q2), g > q2]
    t_means = [float(p[m].mean()) if m.sum() > 10 else float("nan") for m in masks]
    lifts = [tm - unc for tm in t_means]
    best = int(np.nanargmax(lifts))
    return {"unc": unc, "t_means": t_means,
            "best_lift": float(lifts[best]), "best_tercile": best}


def base_fade_pnl(logp: np.ndarray, vol: np.ndarray, ev: np.ndarray, n_tb: int) -> np.ndarray:
    """First-touch return (in bps) aligned to ev.

    The caller forms the fade P&L as ``-sign(signal) * base_fade_pnl(...)``.
    Barriers: symmetric ±1.0 * vol[entry] * sqrt(n_tb); vertical at entry+n_tb.
    """
    entry = ev + 1
    vert = np.minimum(entry + n_tb, len(logp) - 1)
    width = 1.0 * vol[entry] * np.sqrt(n_tb)
    _, ret, _, _ = triple_barrier_core(logp, entry, vert, width)
    return ret


def screen(n_grid: tuple[int, ...] = (30, 50)) -> pd.DataFrame:
    """Stage-1 screen: 3-role stats for every feature × N combination.

    Returns one row per (feature, N) with columns:
    feature, N, dir_wic, mag_ic, cond_lift, cond_tercile, sign_dir.
    """
    rng = np.random.default_rng(0)
    cache = {s: build_all(s) for s in POOL}
    evset = {}
    for s in POOL:
        logp, f, vol, bph = cache[s]
        n = len(logp)
        warm = int(96 * bph) + 60
        idx = np.arange(warm, n - max(n_grid) - 3)
        idx = idx[np.isfinite(vol[idx + 1]) & (vol[idx + 1] > 0)]
        evset[s] = np.sort(rng.choice(idx, min(N_EVENTS, len(idx)), replace=False))
    feats = [k for k in cache[POOL[0]][1] if k != SELECTOR]
    rows = []
    for n_tb in n_grid:
        per = {}
        for s in POOL:
            logp, f, vol, bph = cache[s]
            ev = evset[s]
            ret = base_fade_pnl(logp, vol, ev, n_tb)
            base_pnl = -np.sign(f[SELECTOR][ev]) * ret
            per[s] = (f, ev, ret, base_pnl)
        for fn in feats:
            wics, migs, lifts, terc = [], [], [], []
            for s in POOL:
                f, ev, ret, base_pnl = per[s]
                x = f[fn][ev]
                wics.append(weighted_directional_ic(x, ret))
                migs.append(magnitude_ic(x, ret))
                cs = tercile_netbps_spread(base_pnl, x)
                lifts.append(cs["best_lift"])
                terc.append(cs["best_tercile"])
            wics = np.array(wics)
            rows.append(dict(
                feature=fn, N=n_tb,
                dir_wic=float(np.nanmean(wics)),
                mag_ic=float(np.nanmean(migs)),
                cond_lift=float(np.nanmean(lifts)),
                cond_tercile=int(np.round(np.nanmean(terc))),
                sign_dir=int((np.sign(wics) == np.sign(np.nanmean(wics))).sum()),
            ))
    return pd.DataFrame(rows)


def survivors(screen_df: pd.DataFrame, top_k: int = 5) -> dict:
    """Pick top-k features per role from the N=50 screen rows.

    Direction role requires sign_dir >= 4 (majority of 5 symbols agree).
    Returns {"direction": [...], "magnitude": [...], "conditioner": [...]}.
    """
    d = screen_df[screen_df.N == 50].copy()
    out: dict[str, list[str]] = {}
    dir_ok = d[d.sign_dir >= 4]
    out["direction"] = (
        dir_ok.reindex(dir_ok.dir_wic.abs().sort_values(ascending=False).index)
        .head(top_k)
        .feature.tolist()
    )
    out["magnitude"] = (
        d.reindex(d.mag_ic.abs().sort_values(ascending=False).index)
        .head(top_k)
        .feature.tolist()
    )
    out["conditioner"] = (
        d.reindex(d.cond_lift.sort_values(ascending=False).index)
        .head(top_k)
        .feature.tolist()
    )
    return out


def main() -> None:
    import matplotlib  # noqa: PLC0415

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # noqa: PLC0415, E402

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from pnl_walkforward import marginal_lift  # noqa: PLC0415, E402

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    res = screen()
    res.to_csv(OUT_DIR / "screen.csv", index=False)

    pd.set_option("display.width", 200, "display.float_format", lambda x: f"{x:8.4f}")
    for role, col in [
        ("DIRECTION (|ret|-weighted IC)", "dir_wic"),
        ("MAGNITUDE (IC vs |ret|)", "mag_ic"),
        ("CONDITIONING (tercile net-bps lift)", "cond_lift"),
    ]:
        print(f"\n=== {role} — top by |{col}| ===")
        for n_tb in sorted(res.N.unique()):
            d = res[n_tb == res.N].copy()
            d = d.reindex(d[col].abs().sort_values(ascending=False).index).head(8)
            print(f"-- N={n_tb} --")
            print(d[["feature", col, "sign_dir"]].to_string(index=False))
    print(f"\nscreen -> {OUT_DIR / 'screen.csv'}")

    surv = survivors(res)

    rng = np.random.default_rng(0)
    cache = {s: build_all(s) for s in POOL}
    evset: dict[str, np.ndarray] = {}
    for s in POOL:
        logp, f, vol, bph = cache[s]
        n = len(logp)
        warm = int(96 * bph) + 60
        idx = np.arange(warm, n - 53)
        idx = idx[np.isfinite(vol[idx + 1]) & (vol[idx + 1] > 0)]
        evset[s] = np.sort(rng.choice(idx, min(N_EVENTS, len(idx)), replace=False))

    # Build lookup: feature -> dir_wic at N=50 (for orient resolution in direction role)
    n50 = res[res.N == 50].set_index("feature")

    crows = []
    for role, feats in surv.items():
        for fn in feats:
            for n_tb in (50, 30):
                if role == "direction":
                    dir_wic_50 = float(n50.loc[fn, "dir_wic"]) if fn in n50.index else 1.0
                    orient = float(np.sign(dir_wic_50)) if dir_wic_50 != 0.0 else 1.0
                    m = marginal_lift(cache, evset, n_tb, fn, role, orient=orient)
                else:
                    m = marginal_lift(cache, evset, n_tb, fn, role)
                crows.append(dict(role=role, feature=fn, N=n_tb, **m))

    conf = pd.DataFrame(crows)
    conf.to_csv(OUT_DIR / "confirm.csv", index=False)

    c50 = conf[conf.N == 50]
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(
        [f"{r['role'][:3]}:{r['feature']}" for _, r in c50.iterrows()],
        c50["lift"].to_numpy(),
        color="steelblue",
    )
    ax.axhline(0, color="k", linewidth=1)
    ax.set_ylabel("net-bps lift over base (N=50)")
    ax.tick_params(axis="x", labelrotation=80, labelsize=7)
    ax.set_title("Edge-feature confirm — marginal net-bps lift (walk-forward non-overlap)")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "net_lift.png", dpi=110)
    plt.close(fig)

    lines = [
        "# Edge-Based Feature Search — Report",
        "",
        "Two-track (direction, magnitude) + conditioning lens. Stage-1 screen "
        "(|ret|-weighted dir IC / IC vs |ret| / tercile net-bps spread) -> Stage-2 "
        "marginal net-bps lift over the fixed base (fade ffd_zvol20 x top-decile "
        "|ffd_zvol20|), walk-forward non-overlap, cost 1.0bps.",
        "",
        "**No modelling.** All combinations are simple non-fit rules. Full "
        "higher-order non-linear interaction discovery (HistGBM importance under a "
        "P&L objective) is the deferred next phase.",
        "",
        "## Confirm — marginal net-bps lift (N=50)",
        "",
        "![net lift](net_lift.png)",
        "",
        c50.sort_values("lift", ascending=False)[
            ["role", "feature", "lift", "cand_net", "base_net", "folds_pos"]
        ].to_markdown(index=False),
    ]
    (OUT_DIR / "REPORT.md").write_text("\n".join(lines) + "\n")
    print(f"report -> {OUT_DIR / 'REPORT.md'}")


if __name__ == "__main__":
    main()
