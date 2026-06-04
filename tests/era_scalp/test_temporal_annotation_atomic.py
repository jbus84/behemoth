import numpy as np

from scripts.era_scalp.load_splits import WHITELIST, TradeSplitData
from scripts.era_scalp.run_era_eur import temporal_annotation


def _split(n, months, seed=0):
    rng = np.random.default_rng(seed)
    return TradeSplitData(
        X=rng.standard_normal((n, len(WHITELIST))), names=list(WHITELIST),
        hour=(np.arange(n) % 24).astype(float),
        mid=1.0 + np.cumsum(rng.standard_normal(n)) * 1e-4,
        cost=np.full(n, 0.2), test_month=np.array(months), spread_pips=np.full(n, 0.2),
    )


def test_temporal_annotation_handles_atomic_dict_payload_fair_mode():
    # In atomic mode the node payload is a COMPOSITION DICT, not a source string.
    # This used to crash with TypeError (ast.parse(dict)); must render + run as estimate_fair.
    months = []
    for m in ["2023-11", "2023-12", "2024-01", "2024-02"]:
        months += [m] * 600
    sp = {"train": _split(1200, months[:1200], 1), "validation": _split(1200, months[1200:], 2)}
    comp = {"skeleton": "base_plus_correction",
            "operators": {"base": "slow_ewma", "correction": "roll_bounce", "combination": "additive_blend"},
            "params": {"alpha": 0.05, "mult": 0.5, "w_base": 1.0, "w_corr": -1.0, "w_cal": 0.0}}
    v = temporal_annotation(comp, sp, "EURUSD", fair_price_mode=True, min_trades=30,
                            num_warmup=100, num_samples=100, num_chains=1)
    assert v is None or ("status" in v)     # the point: it MUST NOT raise


def test_temporal_annotation_string_directional_still_works():
    months = []
    for m in ["2023-11", "2023-12", "2024-01", "2024-02"]:
        months += [m] * 500
    sp = {"train": _split(1000, months[:1000], 5), "validation": _split(1000, months[1000:], 6)}
    src = "def signal(ctx):\n    return ctx.col('vel_pips_h1')\n"
    v = temporal_annotation(src, sp, "EURUSD", fair_price_mode=False, min_trades=30,
                            num_warmup=100, num_samples=100, num_chains=1)
    assert v is None or ("status" in v)
