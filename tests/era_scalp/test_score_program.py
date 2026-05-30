import numpy as np

from scripts.era_scalp.score_program import ScalpScorer, ScalpSplitData

NAMES = ["spread_z", "vel_z_h1", "vel_pips_h1", "bar_return_sign", "hour_utc"]


def _split(n=200, seed=0):
    rng = np.random.default_rng(seed)
    return ScalpSplitData(
        X=rng.standard_normal((n, len(NAMES))),
        names=list(NAMES),
        hour=(np.arange(n) % 24).astype(float),
        y_fwd=rng.standard_normal(n),
        cost=np.full(n, 0.4),
        test_month=np.array(["2025-01"] * (n // 2) + ["2025-02"] * (n - n // 2)),
    )


def test_scorer_runs_causal_program():
    scorer = ScalpScorer(splits={"validation": _split()}, thresholds=[0.5, 1.0])
    score, logs = scorer.score("def signal(ctx):\n    return ctx.col('vel_z_h1')\n", "validation")
    assert np.isfinite(score)


def test_scorer_rejects_noncausal():
    scorer = ScalpScorer(splits={"validation": _split()}, thresholds=[0.5, 1.0])
    fwd = ("def signal(ctx):\n"
           "    x = ctx.col('vel_z_h1').copy()\n"
           "    x[:-1] = (x[:-1] + x[1:]) / 2.0\n"
           "    return x\n")
    score, logs = scorer.score(fwd, "validation")
    assert score == -1e6 and "causal" in logs.lower()
