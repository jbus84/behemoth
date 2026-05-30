import numpy as np

from scripts.era.score_program import ProgramScorer, SplitData


def _split():
    n = 300
    rng = np.random.RandomState(1)
    r = rng.randn(n, 6)
    # craft a reverting target: y_fwd opposes the target's idiosyncratic move
    z = (r[:, 0] - r[:, 1:].mean(1)) / (r[:, 1:].std(1) + 1e-9)
    y = -np.sign(z) * np.abs(rng.randn(n)) * (-1)  # so fading z is profitable
    months = np.array([f"2025-{1 + (i % 6):02d}" for i in range(n)])
    return SplitData(
        r=r,
        names=list("ABCDEF"),
        target="A",
        usd_sign=-1,
        y_fwd=y,
        cost=np.full(n, 0.1),
        test_month=months,
    )


LOO = (
    "def residual(ctx):\n t=ctx.target_col(); p=ctx.peers()\n return (t-p.mean(1))/(p.std(1)+1e-9)"
)


def test_score_runs_and_is_finite():
    sc = ProgramScorer(splits={"train": _split()}, thresholds=[1.0, 1.5, 2.0])
    score, logs = sc.score(LOO, "train")
    assert np.isfinite(score)


def test_bad_program_returns_floor():
    sc = ProgramScorer(splits={"train": _split()}, thresholds=[1.0])
    score, logs = sc.score("def residual(ctx):\n import os\n return 1", "train")
    assert score <= -1e3 and "static_check" in logs
