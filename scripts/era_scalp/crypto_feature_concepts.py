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
    # Amihud illiquidity: trailing mean of |return|/dollar-volume (Cakici 2024)
    "amihud_illiq": (
        "    _r = np.abs(np.nan_to_num(ctx.col('return_1h')))\n"
        "    _dv = np.nan_to_num(ctx.col('close')) * np.nan_to_num(ctx.col('vol')) + 1e-9\n"
        "    _il = _r / _dv\n"
        "    _c = np.cumsum(_il)\n"
        "    _w = {w}\n"
        "    _o = np.full(n, np.nan)\n"
        "    for t in range(n):\n"
        "        lo = t - _w + 1\n"
        "        if lo >= 0:\n"
        "            _o[t] = (_c[t] - (_c[lo-1] if lo > 0 else 0.0)) / _w\n"
        "    feats.append(_o)\n"
    ),
    # realized volatility: trailing std of returns (cumsum-based)
    "realized_vol": (
        "    _r = np.nan_to_num(ctx.col('return_1h'))\n"
        "    _c1 = np.cumsum(_r); _c2 = np.cumsum(_r*_r)\n"
        "    _w = {w}\n"
        "    _o = np.full(n, np.nan)\n"
        "    for t in range(n):\n"
        "        lo = t - _w + 1\n"
        "        if lo >= 0:\n"
        "            _s1 = _c1[t] - (_c1[lo-1] if lo > 0 else 0.0)\n"
        "            _s2 = _c2[t] - (_c2[lo-1] if lo > 0 else 0.0)\n"
        "            _m = _s1 / _w\n"
        "            _o[t] = np.sqrt(max(_s2/_w - _m*_m, 0.0))\n"
        "    feats.append(_o)\n"
    ),
    # downside semi-volatility: trailing std of negative returns
    "downside_vol": (
        "    _r = np.nan_to_num(ctx.col('return_1h'))\n"
        "    _rn = np.minimum(_r, 0.0)\n"
        "    _c2 = np.cumsum(_rn*_rn)\n"
        "    _w = {w}\n"
        "    _o = np.full(n, np.nan)\n"
        "    for t in range(n):\n"
        "        lo = t - _w + 1\n"
        "        if lo >= 0:\n"
        "            _o[t] = np.sqrt((_c2[t] - (_c2[lo-1] if lo > 0 else 0.0)) / _w)\n"
        "    feats.append(_o)\n"
    ),
    # return skewness (lottery/skewness factor), trailing window
    "ret_skew": (
        "    _r = np.nan_to_num(ctx.col('return_1h'))\n"
        "    _c1 = np.cumsum(_r); _c2 = np.cumsum(_r*_r); _c3 = np.cumsum(_r*_r*_r)\n"
        "    _w = {w}\n"
        "    _o = np.full(n, np.nan)\n"
        "    for t in range(n):\n"
        "        lo = t - _w + 1\n"
        "        if lo >= 0:\n"
        "            _m = (_c1[t] - (_c1[lo-1] if lo > 0 else 0.0)) / _w\n"
        "            _m2 = (_c2[t] - (_c2[lo-1] if lo > 0 else 0.0)) / _w\n"
        "            _m3 = (_c3[t] - (_c3[lo-1] if lo > 0 else 0.0)) / _w\n"
        "            _var = _m2 - _m*_m\n"
        "            if _var > 1e-18:\n"
        "                _o[t] = (_m3 - 3*_m*_m2 + 2*_m**3) / (_var**1.5)\n"
        "    feats.append(_o)\n"
    ),
    # dollar volume (size/liquidity proxy): trailing mean of close*vol
    "dollar_vol": (
        "    _dv = np.nan_to_num(ctx.col('close')) * np.nan_to_num(ctx.col('vol'))\n"
        "    _c = np.cumsum(_dv)\n"
        "    _w = {w}\n"
        "    _o = np.full(n, np.nan)\n"
        "    for t in range(n):\n"
        "        lo = t - _w + 1\n"
        "        if lo >= 0:\n"
        "            _o[t] = (_c[t] - (_c[lo-1] if lo > 0 else 0.0)) / _w\n"
        "    feats.append(_o)\n"
    ),
    # volume shock: current volume vs trailing mean volume
    "vol_shock": (
        "    _v = np.nan_to_num(ctx.col('vol'))\n"
        "    _c = np.cumsum(_v)\n"
        "    _w = {w}\n"
        "    _o = np.full(n, np.nan)\n"
        "    for t in range(n):\n"
        "        lo = t - _w + 1\n"
        "        if lo >= 0:\n"
        "            _ma = (_c[t] - (_c[lo-1] if lo > 0 else 0.0)) / _w\n"
        "            _o[t] = _v[t] / (_ma + 1e-12)\n"
        "    feats.append(_o)\n"
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


# NOTE: research factors (amihud_illiq/realized_vol/downside_vol/ret_skew/dollar_vol/vol_shock)
# remain in the taxonomy but are NOT seeded — empirically they DEGRADE the hourly model
# (val IC 0.0076 flow-only -> 0.0008 with factors; they are monthly-horizon factors). Seeds stay flow-focused.
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
