import numpy as np

from scripts.fx_coint.target_report import (
    ReportCard,
    score_target,
    wellposedness_verdict,
)


def test_wellposedness_verdict_flags_overlap_collapse():
    assert wellposedness_verdict({"overlap_ratio": 0.02, "top1pct_share": 0.1,
                                  "entropy": 0.9}) == "ill-posed"


def test_wellposedness_verdict_flags_concentration():
    assert wellposedness_verdict({"overlap_ratio": 0.5, "top1pct_share": 0.95,
                                  "entropy": 0.9}) == "ill-posed"


def test_wellposedness_verdict_passes_clean_target():
    assert wellposedness_verdict({"overlap_ratio": 0.5, "top1pct_share": 0.2,
                                  "entropy": 0.9}) == "well-posed"


def test_wellposedness_verdict_flags_low_entropy():
    assert wellposedness_verdict({"overlap_ratio": 0.5, "top1pct_share": 0.2,
                                  "entropy": 0.05}) == "ill-posed"


def test_score_target_illposed_runs_ceiling_when_overridden():
    n = 2000
    rng = np.random.default_rng(0)
    # AR(1) phi 0.99 label -> overlap collapse -> ill-posed
    y = np.zeros(n)
    eps = rng.standard_normal(n)
    for i in range(1, n):
        y[i] = 0.99 * y[i - 1] + eps[i]
    X = np.random.default_rng(1).standard_normal((n, 2))
    card = score_target("ar1", "continuous", labels=y, signal=y,
                        day_index=np.arange(n) // 10, split_idx=n // 2,
                        X=X, y_ceiling=y, t1=np.arange(n) + 1,
                        run_ceiling_on_illposed=True,
                        rng=np.random.default_rng(3))
    assert card.wellposed_verdict == "ill-posed"
    assert card.ceiling is not None
    assert card.ceiling_verdict in ("signal", "null-indistinguishable")


def test_score_target_illposed_skips_ceiling():
    n = 2000
    rng = np.random.default_rng(0)
    # AR(1) phi 0.99 label -> overlap collapse -> ill-posed
    y = np.zeros(n)
    eps = rng.standard_normal(n)
    for i in range(1, n):
        y[i] = 0.99 * y[i - 1] + eps[i]
    X = np.random.default_rng(1).standard_normal((n, 2))
    card = score_target("ar1", "continuous", labels=y, signal=y,
                        day_index=np.arange(n) // 10, split_idx=n // 2,
                        X=X, y_ceiling=y, t1=np.arange(n) + 1)
    assert isinstance(card, ReportCard)
    assert card.wellposed_verdict == "ill-posed"
    assert card.ceiling is None
    assert card.ceiling_verdict == "skipped"


def test_score_target_wellposed_runs_ceiling_and_finds_signal():
    n = 3000
    rng = np.random.default_rng(2)
    r = rng.standard_normal(n)
    from scripts.fx_coint.target_ceiling import lag_embedding
    X = lag_embedding(r, lags=(1, 2))
    # Deviation from brief: the brief used y = roll(r, -1) + noise, but that is
    # the FUTURE of a random walk and is unpredictable from past lags X, so
    # ceiling_bracket never finds signal (lower_p ~ 0.3-0.9, verified across
    # seeds 0-9). Use a target that genuinely depends on the features instead,
    # which is what "well-posed -> ceiling runs -> signal detected" must test.
    y = 2.0 * X[:, 0] + 0.01 * rng.standard_normal(n)
    y[-1] = np.nan
    card = score_target("learnable", "continuous", labels=r, signal=r,
                        day_index=np.arange(n) // 10, split_idx=n // 2,
                        X=X, y_ceiling=y, t1=np.arange(n) + 1,
                        rng=np.random.default_rng(3))
    assert card.wellposed_verdict == "well-posed"
    assert card.ceiling is not None
    assert card.ceiling_verdict == "signal"
