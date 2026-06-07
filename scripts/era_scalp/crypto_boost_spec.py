"""Crypto cross-sectional flow boosting as a RunSpec for the unified ERA engine.

A node renders to build_features(ctx) (sandboxed, causality-probed). crypto_boost_spec
closes over the train panel: run_program builds features per symbol, pools them, trains a
single CatBoost, and returns per-symbol predictions as a (n_bars, n_symbols) matrix.
score_frame cross-sectionally z-scores predictions, forms dollar-neutral proportional
weights, and computes portfolio net = gross − turnover×cost.
"""
from __future__ import annotations

import hashlib
import random as _random
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.era_scalp.boosting_sandbox import causality_probe as _bf_causality
from scripts.era_scalp.boosting_sandbox import run_program as _bf_run
from scripts.era_scalp.boosting_scorer import complexity_penalty, train_predict
from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.crypto_feature_concepts import (
    CRYPTO_FEATURE_TAXONOMY,
    CRYPTO_SEED_COMPOSITIONS,
    crypto_composition_to_source,
)
from scripts.era_scalp.era_engine import RunSpec, engine_verdict, run_search_rich, score_program

# ── base feature names expected in per-symbol FeatureContext ──────────
_CRYPTO_BASE_NAMES = ["ofi", "close", "vol", "return_1h"]


@dataclass
class CryptoPanel:
    """Aligned per-pair arrays sharing a single time index."""

    symbols: list[str]
    dt: pd.DatetimeIndex
    close: dict[str, np.ndarray]
    ofi: dict[str, np.ndarray]
    vol: dict[str, np.ndarray]
    return_1h: dict[str, np.ndarray]
    test_month: np.ndarray
    hour_utc: np.ndarray | None = None

    @property
    def n_bars(self) -> int:
        return len(self.dt)


def build_crypto_panel(path: str | Path) -> CryptoPanel:
    """Load cached crypto panel parquet and build per-pair aligned arrays."""
    p = pd.read_parquet(path)
    if "dt" not in p.columns:
        ts = p["ts"].astype("int64")
        p["dt"] = pd.to_datetime(
            np.where(ts < 100_000_000_000_000, ts * 1_000_000, ts * 1000), utc=True
        )
    p = p.sort_values(["symbol", "dt"]).reset_index(drop=True)
    symbols = sorted(p["symbol"].unique())
    close_w = p.pivot(index="dt", columns="symbol", values="close")
    ofi_w = p.pivot(index="dt", columns="symbol", values="ofi")
    vol_w = p.pivot(index="dt", columns="symbol", values="vol")
    dt_idx = close_w.index
    close = {s: close_w[s].to_numpy(float) for s in symbols if s in close_w.columns}
    ofi = {s: ofi_w[s].to_numpy(float) for s in symbols if s in ofi_w.columns}
    vol = {s: vol_w[s].to_numpy(float) for s in symbols if s in vol_w.columns}
    return_1h: dict[str, np.ndarray] = {}
    for s in symbols:
        if s not in close:
            continue
        c = close[s]
        r = np.full_like(c, np.nan, dtype=float)
        r[1:] = (c[1:] - c[:-1]) / np.maximum(np.abs(c[:-1]), 1e-12)
        return_1h[s] = r
    test_month = dt_idx.strftime("%Y-%m").to_numpy()
    hour_utc = dt_idx.hour.to_numpy().astype(float)
    return CryptoPanel(
        symbols=symbols,
        dt=dt_idx,
        close=close,
        ofi=ofi,
        vol=vol,
        return_1h=return_1h,
        test_month=test_month,
        hour_utc=hour_utc,
    )


def _filter_panel(panel: CryptoPanel, mask: np.ndarray) -> CryptoPanel:
    """Return a CryptoPanel with rows filtered by a boolean mask."""
    return CryptoPanel(
        symbols=panel.symbols,
        dt=panel.dt[mask],
        close={s: arr[mask] for s, arr in panel.close.items()},
        ofi={s: arr[mask] for s, arr in panel.ofi.items()},
        vol={s: arr[mask] for s, arr in panel.vol.items()},
        return_1h={s: arr[mask] for s, arr in panel.return_1h.items()},
        test_month=panel.test_month[mask],
        hour_utc=None if panel.hour_utc is None else panel.hour_utc[mask],
    )


def build_crypto_splits(
    path: str | Path,
    *,
    train_years=(2022, 2023),
    validation_years=(2024,),
    holdout_years=(2025,),
) -> dict[str, CryptoPanel]:
    """Build train / validation / holdout CryptoPanels by year filter."""
    panel = build_crypto_panel(path)
    out: dict[str, CryptoPanel] = {}
    for name, years in [
        ("train", train_years),
        ("validation", validation_years),
        ("holdout", holdout_years),
    ]:
        mask = panel.dt.year.isin(years).to_numpy()
        out[name] = _filter_panel(panel, mask)
    return out


def _halve_panel(panel: CryptoPanel) -> tuple[CryptoPanel, CryptoPanel]:
    """Split a CryptoPanel in half by time -> (V1, V2)."""
    n = panel.n_bars
    m = n // 2

    def _sl(sl: slice) -> CryptoPanel:
        return _filter_panel(panel, np.zeros(n, bool))

    # Build boolean masks for first and second half
    m1 = np.zeros(n, bool)
    m1[:m] = True
    m2 = np.zeros(n, bool)
    m2[m:] = True
    return _filter_panel(panel, m1), _filter_panel(panel, m2)


def _sanitize(comp):
    """Sanitise a composition dict for crypto concepts."""
    if not isinstance(comp, dict):
        return {"skeleton": "default", "operators": {}, "params": {"w": 24}}
    ops = comp.get("operators", {})
    ops = {k: v for k, v in ops.items() if isinstance(v, str) and v in CRYPTO_FEATURE_TAXONOMY}
    return {"skeleton": "default", "operators": ops, "params": comp.get("params", {"w": 24})}


def mutate_composition(parent, score, logs, idea, *, cache_dir=None, seed=0):
    """Deterministic mutation: add/swap/drop one feature operator."""
    rng = _random.Random(hash((repr(parent), seed)) & 0xFFFFFFFF)
    comp = _sanitize(parent)
    ops = dict(comp["operators"])
    concepts = list(CRYPTO_FEATURE_TAXONOMY)
    action = rng.choice(["add", "swap", "drop"]) if ops else "add"
    if action == "add":
        ops[f"s{len(ops)}"] = rng.choice(concepts)
    elif action == "swap" and ops:
        ops[rng.choice(list(ops))] = rng.choice(concepts)
    elif action == "drop" and len(ops) > 1:
        del ops[rng.choice(list(ops))]
    w = int(comp["params"].get("w", 24))
    params = {"w": max(2, w + rng.choice([-8, 0, 8]))}
    return {"skeleton": "default", "operators": ops, "params": params}, 0.5


def recombine_compositions(comp_a, score_a, comp_b, score_b, *, cache_dir=None):
    """Union the two parents' operators (favouring the higher-scoring parent's window)."""
    a, b = _sanitize(comp_a), _sanitize(comp_b)
    ops = {**a["operators"], **b["operators"]}
    params = a["params"] if score_a >= score_b else b["params"]
    return {"skeleton": "default", "operators": ops, "params": params}, 0.5


# ── run_program helpers ───────────────────────────────────────────────

def _symbol_feature_context(panel: CryptoPanel, symbol: str) -> FeatureContext:
    """Build a FeatureContext for one symbol from the panel."""
    X = np.column_stack([
        panel.ofi[symbol],
        panel.close[symbol],
        panel.vol[symbol],
        panel.return_1h[symbol],
    ])
    return FeatureContext(X=X, names=list(_CRYPTO_BASE_NAMES),
                          hour=None if panel.hour_utc is None else panel.hour_utc)


def _build_features_matrix(panel: CryptoPanel, src: str, timeout: float) -> tuple[np.ndarray | None, str | None]:
    """Run build_features per symbol and return stacked (n_bars * n_sym, n_feat) matrix.
    Returns (None, err) on failure."""
    mats = []
    for sym in panel.symbols:
        ctx = _symbol_feature_context(panel, sym)
        feats, err, _ = _bf_run(src, ctx, timeout=timeout, required_fn="build_features")
        if err is not None:
            return None, err
        feats = np.asarray(feats, float)
        if feats.ndim != 2 or feats.shape[0] != ctx.n_bars:
            return None, f"shape mismatch for {sym}: {feats.shape}"
        mats.append(feats)
    return np.concatenate(mats, axis=0), None


def _labels_bps(panel: CryptoPanel, horizon: int) -> np.ndarray:
    """Stacked forward-return labels in bps for all symbols: (n_bars * n_sym,)."""
    labels = []
    for sym in panel.symbols:
        c = panel.close[sym]
        n = len(c)
        y = np.full(n, np.nan)
        if n > horizon:
            y[: n - horizon] = (c[horizon:] - c[: n - horizon]) / c[: n - horizon] * 1e4
        labels.append(y)
    return np.concatenate(labels)


def crypto_boost_spec(
    train_panel: CryptoPanel,
    *,
    horizon: int = 6,
    grid_q=None,
    complexity_per_feat: float = 0.02,
    seed: int = 0,
    timeout: float = 20.0,
    seed_only: bool = False,
    k_folds: int = 4,
    embargo: int = 50,
    fee_bps: float = 7.5,
) -> RunSpec:
    """RunSpec for crypto cross-sectional flow boosting.

    Trains one CatBoost on pooled per-symbol features from train_panel.
    Predicts per-symbol on the panel passed at runtime.  score_frame forms a
    dollar-neutral proportional portfolio, rebalancing every `horizon` bars.
    """
    grid_q = grid_q or [0.80, 0.90, 0.95]
    y_train = _labels_bps(train_panel, horizon)
    _cache: dict[str, np.ndarray] = {}

    def run_program(src, ctx, timeout=timeout, required_fn="build_features"):
        if not isinstance(ctx, CryptoPanel):
            return None, f"expected CryptoPanel, got {type(ctx).__name__}", ""
        # 1) features on scored panel
        Xpred, err = _build_features_matrix(ctx, src, timeout)
        if err is not None:
            return None, err, ""
        n_sym = len(ctx.symbols)
        n_bars = ctx.n_bars
        # 2) train (cached by src): features on train + CatBoost fit
        key = hashlib.sha1(src.encode()).hexdigest()
        if key not in _cache:
            Xtr, terr = _build_features_matrix(train_panel, src, timeout)
            if terr is not None:
                return None, terr, ""
            _cache[key] = Xtr
        Xtr = _cache[key]
        try:
            preds_flat = train_predict(Xtr, y_train, Xpred, seed=seed,
                                       k_folds=k_folds, embargo=embargo)
        except Exception as e:
            return None, f"catboost: {e}", ""
        # Reshape back to (n_bars, n_symbols)
        preds = preds_flat.reshape(n_bars, n_sym)
        n_feat = Xpred.shape[1] // n_sym if n_sym > 0 else 0
        return preds, None, f"n_feat={n_feat}"

    def causality_probe(src, ctx, out, required_fn="build_features"):
        if not isinstance(ctx, CryptoPanel):
            return False, f"expected CryptoPanel, got {type(ctx).__name__}"
        for sym in ctx.symbols:
            sctx = _symbol_feature_context(ctx, sym)
            feats, err, _ = _bf_run(src, sctx, timeout=timeout, required_fn=required_fn)
            if err is not None:
                return False, f"feature exec {sym}: {err}"
            ok, reason = _bf_causality(src, sctx, feats, required_fn=required_fn)
            if not ok:
                return False, f"causality {sym}: {reason}"
        return True, "ok"

    def context_factory(split):
        return split

    def score_frame(out, split, q, h):
        """Cross-sectional proportional portfolio scorer.

        out: (n_bars, n_symbols) predictions
        split: CryptoPanel
        q: conviction quantile threshold
        h: forward horizon / rebalance frequency (bars)
        """
        panel = split
        symbols = panel.symbols
        n_sym = len(symbols)
        n = panel.n_bars
        preds = np.asarray(out, float)
        if preds.shape != (n, n_sym):
            return pd.DataFrame({"net": np.array([]), "test_month": np.array([])})

        # Forward fractional returns per symbol
        fwd = np.full((n, n_sym), np.nan)
        for i, sym in enumerate(symbols):
            c = panel.close[sym]
            if n > h:
                fwd[: n - h, i] = (c[h:] - c[: n - h]) / np.maximum(c[: n - h], 1e-12)

        # Cross-sectional z-score per bar
        z = np.full_like(preds, np.nan)
        for t in range(n):
            row = preds[t, :]
            fin = np.isfinite(row)
            if fin.sum() < 3:
                continue
            m = float(np.nanmedian(row))
            sd = float(np.nanstd(row)) + 1e-12
            z[t, :] = (row - m) / sd

        # Conviction threshold
        abs_z = np.abs(z)
        fin_mask = np.isfinite(abs_z)
        if fin_mask.sum() < 2:
            return pd.DataFrame({"net": np.array([]), "test_month": np.array([])})
        thr = float(np.nanquantile(abs_z[fin_mask], q))

        # Proportional weights, rebalance every h bars
        gross_list, cost_list, net_list, months = [], [], [], []
        prev_w = np.zeros(n_sym)
        for t in range(0, n - h, h):
            if not np.any(fin_mask[t]):
                continue
            w = np.where(fin_mask[t] & (abs_z[t] >= thr), z[t], 0.0)
            w = np.clip(w, -1.0, 1.0)
            w = w - w.mean()  # dollar-neutral
            abs_sum = np.abs(w).sum()
            if abs_sum < 1e-12:
                continue
            w = w / abs_sum  # unit gross exposure
            # Forward return (fractional)
            g = 0.0
            for i in range(n_sym):
                if np.isfinite(fwd[t, i]):
                    g += w[i] * fwd[t, i]
            # Turnover and cost
            turn = float(np.abs(w - prev_w).sum())
            cost = turn * fee_bps / 1e4
            net = g - cost
            net_bps = net * 1e4
            net_list.append(net_bps)
            gross_list.append(g * 1e4)
            cost_list.append(cost * 1e4)
            months.append(str(panel.test_month[t]))
            prev_w = w

        if not net_list:
            return pd.DataFrame({"net": np.array([]), "test_month": np.array([])})
        return pd.DataFrame({
            "net": np.array(net_list, float),
            "gross": np.array(gross_list, float),
            "cost": np.array(cost_list, float),
            "test_month": np.array(months),
        })

    return RunSpec(
        name=f"crypto_flow_h{horizon}",
        required_fn="build_features",
        run_program=(None if seed_only else run_program),
        causality_probe=causality_probe,
        context_factory=context_factory,
        score_frame=score_frame,
        grid_q=list(grid_q),
        grid_h=[horizon],
        aggregate="robust",
        atomic_mode=True,
        seed_compositions=dict(CRYPTO_SEED_COMPOSITIONS),
        render_payload=lambda comp: crypto_composition_to_source(
            "default", _sanitize(comp)["operators"], _sanitize(comp).get("params", {})
        ),
        branch_tags={k: k for k in CRYPTO_SEED_COMPOSITIONS},
        propose_atomic=mutate_composition,
        recombine_atomic=recombine_compositions,
        ideas=["Compose causal flow features (OFI momentum, acceleration, vol-normalised, "
               "price momentum, volume regime, interactions) for a cross-sectional crypto portfolio."],
    )


def run_crypto_boost_search(
    splits: dict[str, CryptoPanel],
    *,
    budget: int = 12,
    seed: int = 0,
    cache_dir: str = ".crypto_boost_cache",
    complexity_per_feat: float = 0.02,
    k_folds: int = 4,
    embargo: int = 50,
    horizon: int = 6,
    grid_q=None,
    fee_bps: float = 7.5,
) -> dict:
    """PUCT crypto flow search: select on V1, confirm on V2, holdout once."""
    v1, v2 = _halve_panel(splits["validation"])
    spec = crypto_boost_spec(
        splits["train"],
        horizon=horizon, grid_q=grid_q,
        complexity_per_feat=complexity_per_feat, seed=seed,
        k_folds=k_folds, embargo=embargo, fee_bps=fee_bps,
    )
    nodes = run_search_rich(spec, {"validation": v1}, budget=budget, seed=seed,
                            cache_dir=cache_dir)

    def penalised(n):
        comp = _sanitize(getattr(n, "payload", {}))
        nf = len(comp["operators"])
        return n.score - complexity_penalty(nf, complexity_per_feat)

    ranked = sorted([n for n in nodes if n.score > -1e6 + 1], key=penalised, reverse=True)
    if not ranked:
        return {"survivor": None, "holdout": None}
    best = ranked[0]
    src = spec.render_payload(best.payload)
    v2_val, _, _, _ = score_program(src, spec, v2)
    verdict = engine_verdict(spec, [best], {"validation": v1, "holdout": splits.get("holdout")},
                             top_k=1)
    return {
        "survivor": {
            "branch": best.branch,
            "val_v1": float(best.score),
            "val_v1_penalised": float(penalised(best)),
            "val_v2": float(v2_val),
            "n_feat": len(_sanitize(best.payload)["operators"]),
            "src": src,
        },
        "holdout": verdict[0] if verdict else None,
    }
