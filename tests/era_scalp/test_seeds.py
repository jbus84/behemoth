import numpy as np

from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.sandbox import causality_probe, run_program
from scripts.era_scalp.seeds import BASELINE_SEED_NAMES, RESEARCH_IDEAS, SEED_PROGRAMS

NAMES = ["spread_z", "spread_pips", "tick_volume", "tick_rate_z", "tick_burst_score",
         "bar_return_sign", "vel_pips_h1", "vel_z_h1", "vel_z_h2", "vel_z_h5",
         "vel_z_h10", "hour_utc", "signed_flow_24", "directional_persistence_8",
         "intra_bar_momentum", "quote_revision_rate_z", "vol_cluster_score",
         "slip_proxy_pips", "hl_pos_frac", "range_pips"]


def _ctx(n=400, seed=1):
    rng = np.random.default_rng(seed)
    X = rng.standard_normal((n, len(NAMES)))
    X[:, NAMES.index("bar_return_sign")] = np.sign(X[:, NAMES.index("bar_return_sign")])
    X[:, NAMES.index("tick_volume")] = np.abs(X[:, NAMES.index("tick_volume")]) * 50 + 1
    return FeatureContext(X=X, names=list(NAMES), hour=(np.arange(n) % 24).astype(float))


def test_expected_seeds_present():
    for name in ("ofi_flow", "ofi_multihorizon", "ou_sscore", "roll_bounce_fade",
                 "hawkes_cont", "spread_gated_flow", "signed_flow_momentum",
                 "quote_revision_flow", "persistence_conditional", "noise_reversion",
                 "vol_cluster_gate", "range_exhaustion"):
        assert name in SEED_PROGRAMS
    for b in BASELINE_SEED_NAMES:
        assert b in SEED_PROGRAMS


def test_all_seeds_run_and_are_causal():
    ctx = _ctx()
    bad = []
    for name, src in SEED_PROGRAMS.items():
        sig, err, _ = run_program(src, ctx)
        if err is not None:
            bad.append(f"{name}: {err}")
            continue
        ok, reason = causality_probe(src, ctx, sig)
        if not ok:
            bad.append(f"{name}: {reason}")
    assert not bad, "; ".join(bad)


def test_research_ideas_cite_modern_streams():
    blob = " ".join(RESEARCH_IDEAS).lower()
    for kw in ["ornstein", "hawkes", "order flow", "multi-horizon", "half-life",
               "signed_flow_24", "quote_revision_rate_z", "directional_persistence_8",
               "slip_proxy_pips", "vol_cluster_score", "hl_pos_frac"]:
        assert kw in blob, f"missing idea keyword: {kw}"
