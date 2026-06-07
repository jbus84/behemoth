# scripts/era_scalp/crypto_feature_concepts.py
"""Flow-centric feature operators for crypto cross-sectional PUCT boosting.

Each concept appends ONE feature column (length n_bars) to `feats` inside
build_features(ctx). All templates use causal cumulative/shifted windows.
np only.
"""
from __future__ import annotations

# name → causal feature code template (appended to `feats`)
CRYPTO_FEATURE_TAXONOMY: dict[str, str] = {
    # trailing moving average of raw OFI
    "ofi_ma": (
        "    _x = np.nan_to_num(ctx.col('ofi'))\n"
        "    _c = np.cumsum(_x)\n"
        "    _w = {w}\n"
        "    _o = np.full(n, np.nan)\n"
        "    for t in range(n):\n"
        "        lo = t - _w + 1\n"
        "        if lo >= 0:\n"
        "            _o[t] = (_c[t] - (_c[lo-1] if lo > 0 else 0.0)) / _w\n"
        "    feats.append(_o)\n"
    ),
    # change in OFI over w bars (flow momentum)
    "ofi_diff": (
        "    _x = np.nan_to_num(ctx.col('ofi'))\n"
        "    _w = {w}\n"
        "    _d = np.full(n, np.nan)\n"
        "    _d[_w:] = _x[_w:] - _x[:-_w]\n"
        "    feats.append(_d)\n"
    ),
    # second difference (flow acceleration)
    "ofi_accel": (
        "    _x = np.nan_to_num(ctx.col('ofi'))\n"
        "    _w = {w}\n"
        "    _d1 = np.full(n, np.nan)\n"
        "    _d1[_w:] = _x[_w:] - _x[:-_w]\n"
        "    _a = np.full(n, np.nan)\n"
        "    _a[2*_w:] = _d1[2*_w:] - _d1[_w:-_w]\n"
        "    feats.append(_a)\n"
    ),
    # OFI MA normalized by trailing volume
    "ofi_vol_norm": (
        "    _x = np.nan_to_num(ctx.col('ofi'))\n"
        "    _v = np.nan_to_num(ctx.col('vol')) + 1e-12\n"
        "    _cx = np.cumsum(_x); _cv = np.cumsum(_v)\n"
        "    _w = {w}\n"
        "    _o = np.full(n, np.nan)\n"
        "    for t in range(n):\n"
        "        lo = t - _w + 1\n"
        "        if lo >= 0:\n"
        "            _sx = _cx[t] - (_cx[lo-1] if lo > 0 else 0.0)\n"
        "            _sv = _cv[t] - (_cv[lo-1] if lo > 0 else 0.0)\n"
        "            _o[t] = _sx / (_sv + 1e-9)\n"
        "    feats.append(_o)\n"
    ),
    # price momentum: cumulative return over w bars
    "return_mom": (
        "    _r = np.nan_to_num(ctx.col('return_1h'))\n"
        "    _c = np.cumsum(_r)\n"
        "    _w = {w}\n"
        "    _m = np.full(n, np.nan)\n"
        "    for t in range(n):\n"
        "        lo = t - _w + 1\n"
        "        if lo >= 0:\n"
        "            _m[t] = _c[t] - (_c[lo-1] if lo > 0 else 0.0)\n"
        "    feats.append(_m)\n"
    ),
    # volume regime: trailing volume mean
    "vol_regime": (
        "    _v = np.nan_to_num(ctx.col('vol'))\n"
        "    _c = np.cumsum(_v)\n"
        "    _w = {w}\n"
        "    _vr = np.full(n, np.nan)\n"
        "    for t in range(n):\n"
        "        lo = t - _w + 1\n"
        "        if lo >= 0:\n"
        "            _vr[t] = (_c[t] - (_c[lo-1] if lo > 0 else 0.0)) / _w\n"
        "    feats.append(_vr)\n"
    ),
    # OFI × return momentum interaction
    "ofi_x_mom": (
        "    _o = np.nan_to_num(ctx.col('ofi'))\n"
        "    _r = np.nan_to_num(ctx.col('return_1h'))\n"
        "    _co = np.cumsum(_o); _cr = np.cumsum(_r)\n"
        "    _w = {w}\n"
        "    _x = np.full(n, np.nan)\n"
        "    for t in range(n):\n"
        "        lo = t - _w + 1\n"
        "        if lo >= 0:\n"
        "            _so = (_co[t] - (_co[lo-1] if lo > 0 else 0.0)) / _w\n"
        "            _sr = (_cr[t] - (_cr[lo-1] if lo > 0 else 0.0)) / _w\n"
        "            _x[t] = _so * _sr\n"
        "    feats.append(_x)\n"
    ),
    # OFI × volume regime interaction
    "ofi_x_vol": (
        "    _o = np.nan_to_num(ctx.col('ofi'))\n"
        "    _v = np.nan_to_num(ctx.col('vol'))\n"
        "    _co = np.cumsum(_o); _cv = np.cumsum(_v)\n"
        "    _w = {w}\n"
        "    _x = np.full(n, np.nan)\n"
        "    for t in range(n):\n"
        "        lo = t - _w + 1\n"
        "        if lo >= 0:\n"
        "            _so = (_co[t] - (_co[lo-1] if lo > 0 else 0.0)) / _w\n"
        "            _sv = (_cv[t] - (_cv[lo-1] if lo > 0 else 0.0)) / _w\n"
        "            _x[t] = _so * _sv\n"
        "    feats.append(_x)\n"
    ),
}

CRYPTO_FEATURE_SKELETON = (
    "def build_features(ctx):\n"
    "    n = ctx.n_bars\n"
    "    feats = []\n"
    "{body}"
    "    if not feats:\n"
    "        feats.append(np.zeros(n))\n"
    "    return np.column_stack(feats)\n"
)


def crypto_composition_to_source(skeleton: str, operators, params=None) -> str:
    """Render a composition into build_features(ctx) source."""
    params = params or {}
    if not isinstance(operators, dict):
        operators = {}
    body = ""
    for slot, concept in operators.items():
        tmpl = CRYPTO_FEATURE_TAXONOMY.get(concept if isinstance(concept, str) else "")
        if tmpl is None:
            continue
        w = int((params.get(slot, {}) or {}).get("w", 20)) if isinstance(params.get(slot), dict) else int(params.get("w", 20))
        body += tmpl.replace("{w}", str(max(2, w)))
    return CRYPTO_FEATURE_SKELETON.format(body=body or "    feats.append(np.zeros(n))\n")


CRYPTO_SEED_COMPOSITIONS: dict[str, dict] = {
    "flow_raw": {
        "skeleton": "default",
        "operators": {"a": "ofi_ma"},
        "params": {"w": 24},
    },
    "flow_momentum": {
        "skeleton": "default",
        "operators": {"a": "ofi_ma", "b": "return_mom", "c": "ofi_x_mom"},
        "params": {"w": 24},
    },
    "deep_flow": {
        "skeleton": "default",
        "operators": {
            "a": "ofi_ma", "b": "ofi_diff", "c": "ofi_accel",
            "d": "ofi_vol_norm", "e": "return_mom", "f": "vol_regime",
            "g": "ofi_x_mom", "h": "ofi_x_vol",
        },
        "params": {"w": 24},
    },
}
