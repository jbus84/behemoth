# scripts/era_scalp/feature_concepts.py
"""Literature-seeded feature operators for the PUCT-built boosting search.

Each concept is a causal code template that appends ONE feature column (length n_bars)
to the list `feats` inside build_features(ctx). All templates use cumulative / shifted
windows so a row at t depends only on rows <= t (passes the causality probe). np only.
"""
from __future__ import annotations

# name -> (causal feature code template appended to `feats`)
FEATURE_CONCEPT_TAXONOMY: dict[str, str] = {
    # signed order-flow imbalance over a trailing window (Cont-Kukanov-Stoikov)
    "signed_flow_imbalance": (
        "    _x = np.nan_to_num(ctx.col('signed_flow_24'))\n"
        "    _c = np.cumsum(_x)\n"
        "    _w = {w}\n"
        "    _sf = np.full(n, np.nan)\n"
        "    for t in range(n):\n"
        "        lo = t - _w + 1\n"
        "        if lo >= 0:\n"
        "            _sf[t] = _c[t] - (_c[lo-1] if lo > 0 else 0.0)\n"
        "    feats.append(_sf)\n"
    ),
    # realized-range volatility regime (Parkinson-style), trailing mean of range_pips
    "range_vol_regime": (
        "    _r = np.nan_to_num(ctx.col('range_pips'))\n"
        "    _c = np.cumsum(_r)\n"
        "    _w = {w}\n"
        "    _rv = np.full(n, np.nan)\n"
        "    for t in range(n):\n"
        "        lo = t - _w + 1\n"
        "        if lo >= 0:\n"
        "            _rv[t] = (_c[t] - (_c[lo-1] if lo > 0 else 0.0)) / _w\n"
        "    feats.append(_rv)\n"
    ),
    # path-dependent reversal: trailing cumulative velocity (mean-reversion signal)
    "trailing_reversal": (
        "    _v = np.nan_to_num(ctx.col('vel_pips_h1'))\n"
        "    _c = np.cumsum(_v)\n"
        "    _w = {w}\n"
        "    _tr = np.full(n, np.nan)\n"
        "    for t in range(n):\n"
        "        lo = t - _w + 1\n"
        "        if lo >= 0:\n"
        "            _tr[t] = -(_c[t] - (_c[lo-1] if lo > 0 else 0.0))\n"
        "    feats.append(_tr)\n"
    ),
    # quote-revision intensity scaled by spread (Easley-O'Hara info flow)
    "quote_revision_intensity": (
        "    _q = np.nan_to_num(ctx.col('quote_revision_rate_z'))\n"
        "    _s = np.nan_to_num(ctx.col('spread_pips')) + 1e-9\n"
        "    feats.append(_q / _s)\n"
    ),
    # liquidity proxy: tick volume z trailing mean
    "liquidity_state": (
        "    _tv = np.nan_to_num(ctx.col('tick_volume'))\n"
        "    _c = np.cumsum(_tv)\n"
        "    _w = {w}\n"
        "    _ls = np.full(n, np.nan)\n"
        "    for t in range(n):\n"
        "        lo = t - _w + 1\n"
        "        if lo >= 0:\n"
        "            _ls[t] = (_c[t] - (_c[lo-1] if lo > 0 else 0.0)) / _w\n"
        "    feats.append(_ls)\n"
    ),
    # --- deep scan additions (literature-grounded, causal) ---
    # OFI acceleration: change in signed flow over w bars (flow regime shift)
    "flow_acceleration": (
        "    _x = np.nan_to_num(ctx.col('signed_flow_24'))\n"
        "    _w = {w}\n"
        "    _d = np.full(n, np.nan)\n"
        "    _d[_w:] = _x[_w:] - _x[:-_w]\n"
        "    feats.append(_d)\n"
    ),
    # vol-normalised OFI (Deep-OFI stresses stationary inputs)
    "vol_normalized_flow": (
        "    _x = np.nan_to_num(ctx.col('signed_flow_24'))\n"
        "    _r = np.nan_to_num(ctx.col('range_pips'))\n"
        "    _cx = np.cumsum(_x); _cr = np.cumsum(_r)\n"
        "    _w = {w}\n"
        "    _o = np.full(n, np.nan)\n"
        "    for t in range(n):\n"
        "        lo = t - _w + 1\n"
        "        if lo >= 0:\n"
        "            _sx = _cx[t] - (_cx[lo-1] if lo > 0 else 0.0)\n"
        "            _sr = _cr[t] - (_cr[lo-1] if lo > 0 else 0.0)\n"
        "            _o[t] = _sx / (_sr + 1e-9)\n"
        "    feats.append(_o)\n"
    ),
    # trading-intensity-scaled OFI (short-horizon gains)
    "intensity_weighted_flow": (
        "    _x = np.nan_to_num(ctx.col('signed_flow_24'))\n"
        "    _i = np.nan_to_num(ctx.col('tick_rate_z'))\n"
        "    feats.append(_x * _i)\n"
    ),
    # multi-horizon momentum (return persistence across horizons)
    "momentum_h5": "    feats.append(np.nan_to_num(ctx.col('vel_z_h5')))\n",
    "momentum_h10": "    feats.append(np.nan_to_num(ctx.col('vel_z_h10')))\n",
    # jump indicator: short move vs trailing range (self-exciting jumps)
    "jump_indicator": (
        "    _v = np.abs(np.nan_to_num(ctx.col('vel_pips_h1')))\n"
        "    _r = np.nan_to_num(ctx.col('range_pips'))\n"
        "    _cr = np.cumsum(_r)\n"
        "    _w = {w}\n"
        "    _j = np.full(n, np.nan)\n"
        "    for t in range(n):\n"
        "        lo = t - _w + 1\n"
        "        if lo >= 0:\n"
        "            _mr = (_cr[t] - (_cr[lo-1] if lo > 0 else 0.0)) / _w\n"
        "            _j[t] = _v[t] / (_mr + 1e-9)\n"
        "    feats.append(_j)\n"
    ),
    # volatility-cluster regime (GARCH-like conditioning)
    "vol_cluster": "    feats.append(np.nan_to_num(ctx.col('vol_cluster_score')))\n",
    # directional persistence (trend autocorrelation proxy)
    "directional_persistence": "    feats.append(np.nan_to_num(ctx.col('directional_persistence_8')))\n",
    # intrabar momentum (within-bar drift)
    "intra_bar_momentum_feat": "    feats.append(np.nan_to_num(ctx.col('intra_bar_momentum')))\n",
    # microprice position: where close sits in the bar range (reversion anchor)
    "microprice_position": "    feats.append(np.nan_to_num(ctx.col('hl_pos_frac')))\n",
    # spread / liquidity regime (cost & toxicity state)
    "spread_regime": "    feats.append(np.nan_to_num(ctx.col('spread_z')))\n",
    # tick-burst toxicity (informed-flow proxy; Easley-O'Hara VPIN-like)
    "burst_toxicity": "    feats.append(np.nan_to_num(ctx.col('tick_burst_score')))\n",
    # flow x persistence interaction (informed directional flow)
    "flow_persistence_interaction": (
        "    _f = np.nan_to_num(ctx.col('signed_flow_24'))\n"
        "    _p = np.nan_to_num(ctx.col('directional_persistence_8'))\n"
        "    feats.append(_f * _p)\n"
    ),
}

FEATURE_SKELETON = (
    "def build_features(ctx):\n"
    "    n = ctx.n_bars\n"
    "    feats = []\n"
    "{body}"
    "    if not feats:\n"
    "        feats.append(np.zeros(n))\n"
    "    return np.column_stack(feats)\n"
)


def composition_to_features_source(skeleton: str, operators, params=None) -> str:
    """Render a composition into build_features(ctx) source. `operators` maps slot->concept
    (slot names are arbitrary; only the concept values matter). `params` may set window `w`
    per slot (default 20)."""
    params = params or {}
    if not isinstance(operators, dict):
        operators = {}
    body = ""
    for slot, concept in operators.items():
        tmpl = FEATURE_CONCEPT_TAXONOMY.get(concept if isinstance(concept, str) else "")
        if tmpl is None:
            continue
        w = int((params.get(slot, {}) or {}).get("w", 20)) if isinstance(params.get(slot), dict) else int(params.get("w", 20))
        body += tmpl.replace("{w}", str(max(2, w)))
    return FEATURE_SKELETON.format(body=body or "    feats.append(np.zeros(n))\n")


FEATURE_SEED_COMPOSITIONS: dict[str, dict] = {
    "flow_vol": {
        "skeleton": "default",
        "operators": {"a": "signed_flow_imbalance", "b": "range_vol_regime"},
        "params": {"w": 24},
    },
    "reversal_liquidity": {
        "skeleton": "default",
        "operators": {"a": "trailing_reversal", "b": "liquidity_state", "c": "quote_revision_intensity"},
        "params": {"w": 16},
    },
    # deep seed spanning OFI / momentum / vol-regime / microstructure (literature mix)
    "deep_microstructure": {
        "skeleton": "default",
        "operators": {
            "a": "vol_normalized_flow", "b": "flow_acceleration", "c": "intensity_weighted_flow",
            "d": "momentum_h5", "e": "momentum_h10", "f": "jump_indicator",
            "g": "vol_cluster", "h": "directional_persistence", "i": "microprice_position",
            "j": "burst_toxicity", "k": "flow_persistence_interaction",
        },
        "params": {"w": 24},
    },
}
